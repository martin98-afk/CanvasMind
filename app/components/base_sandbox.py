import os
import ast
import sys
import threading

import psutil
import builtins
import pandas as pd
import signal
# 沙箱相关导入
try:
    import resource  # Unix/Linux only
    HAS_RESOURCE = True
except ImportError:
    HAS_RESOURCE = False
    resource = None


from abc import ABC, abstractmethod
from contextlib import contextmanager
from enum import Enum
from typing import Dict, Any, Optional, List, Tuple, Type, Callable
from loguru import logger
from pydantic import BaseModel, Field, create_model


class PropertyType(str, Enum):
    """属性类型"""
    TEXT = "text"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    CHOICE = "choice"


class ArgumentType(str, Enum):
    """参数类型"""
    TEXT = "text"
    INT = "int"
    FLOAT = "float"
    FILE = "file"
    FOLDER = "folder"
    CSV = "csv"
    JSON = "json"
    BOOL = "bool"

    # 验证是否是文件类型
    def is_file(self):
        return self == ArgumentType.FILE or self == ArgumentType.FOLDER

    def to_dict(self, value):
        if self.is_file() and isinstance(value, str):
            return {"type": "File", "filename": os.path.basename(value), "path": value}
        elif self == ArgumentType.CSV and isinstance(value, pd.DataFrame):
            return {
                "type": "CSV",
                "shape": f"{value.shape[0]} rows, {value.shape[1]} columns",
                "columns": value.columns
            }
        else:
            return value


class PropertyDefinition(BaseModel):
    """属性定义"""
    type: PropertyType = PropertyType.TEXT
    default: Any = ""
    label: str = ""
    choices: List[str] = Field(default_factory=list)
    filter: str = "All Files (*)"  # 用于文件类型过滤


class PortDefinition(BaseModel):
    """端口定义"""
    name: str
    label: str
    type: ArgumentType = ArgumentType.TEXT


class SandboxConfig(BaseModel):
    """沙箱配置"""
    timeout: int = 600  # 执行超时时间（秒）
    memory_limit: int = 100 * 1024 * 1024  # 内存限制（字节）
    max_file_size: int = 10 * 1024 * 1024  # 最大文件大小（字节）
    allowed_modules: List[str] = Field(default_factory=list)  # 允许的模块
    blocked_modules: List[str] = Field(default_factory=list)  # 禁止的模块
    file_access_whitelist: List[str] = Field(default_factory=list)  # 文件访问白名单
    network_access: bool = False  # 是否允许网络访问


class SecurityViolation(Exception):
    """安全违规异常"""
    pass


class TimeoutThread:
    """跨平台超时线程类"""
    def __init__(self, timeout: int):
        self.timeout = timeout
        self.timer = None
        self.timed_out = threading.Event()


    def start_timer(self):
        """启动超时计时器"""
        self.timer = threading.Timer(self.timeout, self._timeout_handler)
        self.timer.daemon = True
        self.timer.start()


    def _timeout_handler(self):
        """超时处理函数"""
        self.timed_out.set()


    def cancel(self):
        """取消计时器"""
        if self.timer:
            self.timer.cancel()


    def is_timed_out(self):
        """检查是否超时"""
        return self.timed_out.is_set()


class ComponentSandbox:
    """组件沙箱安全执行器"""

    def __init__(self, config: SandboxConfig = None):
        self.config = config or SandboxConfig()
        self.allowed_builtins = {
            'len', 'str', 'int', 'float', 'bool', 'list', 'dict', 'tuple',
            'set', 'range', 'enumerate', 'zip', 'map', 'filter', 'sorted',
            'min', 'max', 'sum', 'abs', 'round', 'pow', 'print', 'repr',
            'isinstance', 'issubclass', 'type', 'hasattr', 'getattr',
            'setattr', 'delattr', 'callable', 'iter', 'next', 'slice',
            'property', 'staticmethod', 'classmethod', 'super', 'object',
            'Exception', 'ValueError', 'TypeError', 'KeyError', 'IndexError',
            'AttributeError', 'RuntimeError', 'NameError', 'ImportError',
            'OSError', 'IOError', 'StopIteration', 'ZeroDivisionError', '__import__'
        }

        # 危险模块列表
        self.dangerous_modules = {
            'os', 'sys', 'subprocess', 'socket', 'urllib', 'requests',
            'http.client', 'ftplib', 'smtplib', 'poplib', 'imaplib',
            'telnetlib', 'uuid', 'platform', 'subprocess32', 'commands',
            'pickle', 'cPickle', 'shelve', 'shelve', 'dbm', 'gdbm', 'dumbdbm',
            'anydbm', 'bsddb', 'dbhash', 'hashlib', 'hmac', 'crypt',
            'code', 'codeop', 'compileall', 'py_compile', 'imp', 'importlib',
            '__builtin__', '__builtins__', 'builtins', 'execfile', 'eval',
            'file', 'open', 'input', 'raw_input'
        }

    def _check_code_safety(self, code: str) -> bool:
        """检查代码安全性"""
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    module_name = node.module if isinstance(node, ast.ImportFrom) else node.names[0].name
                    if module_name in self.dangerous_modules:
                        raise SecurityViolation(f"危险模块导入: {module_name}")
                    if self.config.blocked_modules and module_name in self.config.blocked_modules:
                        raise SecurityViolation(f"被阻止的模块: {module_name}")
                    if self.config.allowed_modules and module_name not in self.config.allowed_modules:
                        raise SecurityViolation(f"未授权的模块: {module_name}")

                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in ['exec', 'eval', '__import__']:
                            raise SecurityViolation(f"危险函数调用: {node.func.id}")

            return True
        except SyntaxError:
            raise SecurityViolation("代码语法错误")
        except Exception as e:
            raise SecurityViolation(f"代码安全检查失败: {str(e)}")

    @contextmanager
    def _resource_limit(self):
        """资源限制上下文管理器 - 跨平台实现"""
        if HAS_RESOURCE and resource:
            old_limit = None
            if hasattr(resource, 'RLIMIT_AS'):
                old_limit = resource.getrlimit(resource.RLIMIT_AS)
                try:
                    resource.setrlimit(resource.RLIMIT_AS, (self.config.memory_limit, self.config.memory_limit))
                except (ValueError, OSError):
                    # 某些系统可能不支持设置内存限制
                    pass

            try:
                yield
            finally:
                if old_limit:
                    try:
                        resource.setrlimit(resource.RLIMIT_AS, old_limit)
                    except (ValueError, OSError):
                        pass
        else:
            # Windows 或不支持 resource 的系统
            # 使用线程监控内存使用
            initial_memory = psutil.Process().memory_info().rss
            yield

            # 检查内存使用是否超出限制
            current_memory = psutil.Process().memory_info().rss
            if current_memory - initial_memory > self.config.memory_limit:
                raise MemoryError(f"内存使用超出限制: {current_memory - initial_memory} > {self.config.memory_limit}")

    @contextmanager
    def _timeout_context(self):
        """跨平台超时控制上下文管理器"""
        if hasattr(signal, 'SIGALRM') and sys.platform != "win32":
            # Unix/Linux 平台使用信号方式
            def timeout_handler(signum, frame):
                raise TimeoutError("执行超时")

            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(self.config.timeout)

            try:
                yield
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        else:
            # Windows 平台使用线程方式实现超时
            timeout_thread = TimeoutThread(self.config.timeout)
            timeout_thread.start_timer()

            try:
                yield
            finally:
                timeout_thread.cancel()

            # 检查是否超时
            if timeout_thread.is_timed_out():
                raise TimeoutError("执行超时")

    def execute_with_sandbox(self, func: Callable, *args, **kwargs) -> Any:
        """在沙箱中执行函数"""
        with self._timeout_context(), self._resource_limit():
            # 保存原始环境
            original_builtins = dict(builtins.__dict__)

            try:
                # 限制内置函数
                restricted_builtins = {k: v for k, v in builtins.__dict__.items()
                                     if k in self.allowed_builtins}
                builtins.__dict__.clear()
                builtins.__dict__.update(restricted_builtins)

                # 执行函数
                result = func(*args, **kwargs)
                return result
            finally:
                # 恢复原始环境
                builtins.__dict__.clear()
                builtins.__dict__.update(original_builtins)


class BaseComponent(ABC):
    """所有组件必须继承此类"""
    # 组件配置（子类需要定义）
    name: str = "Unnamed Component"
    category: str = "General"
    description: str = ""
    inputs: List[PortDefinition] = []
    outputs: List[PortDefinition] = []
    properties: Dict[str, PropertyDefinition] = {}
    logger = logger

    # 沙箱配置
    sandbox_config: SandboxConfig = SandboxConfig()

    def __init__(self):
        self.sandbox = ComponentSandbox(self.sandbox_config)

    @abstractmethod
    def _run_internal(self, params: Dict[str, Any], inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        内部执行方法，子类需要实现
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        pass

    def run(self, params: Dict[str, Any], inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        安全执行组件逻辑
        """
        try:
            # 验证输入参数
            self._validate_inputs(params, inputs)

            # 在沙箱中执行
            result = self.sandbox.execute_with_sandbox(
                self._run_internal, params, inputs
            )

            # 验证输出
            if not self.validate_outputs(result):
                raise ValueError("输出验证失败：缺少必需的输出端口")

            return result

        except TimeoutError:
            raise RuntimeError(f"组件 {self.name} 执行超时 ({self.sandbox_config.timeout}秒)")
        except MemoryError:
            raise RuntimeError(f"组件 {self.name} 内存使用超出限制 ({self.sandbox_config.memory_limit} bytes)")
        except SecurityViolation as e:
            raise RuntimeError(f"组件 {self.name} 安全违规: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"组件 {self.name} 执行失败: {str(e)}")

    def _validate_inputs(self, params: Dict[str, Any], inputs: Optional[Dict[str, Any]] = None):
        """验证输入参数和数据"""
        # 验证参数类型
        for prop_name, prop_def in self.properties.items():
            if prop_name in params:
                value = params[prop_name]
                if prop_def.type == PropertyType.INT and not isinstance(value, int):
                    raise TypeError(f"参数 {prop_name} 应为整数类型")
                elif prop_def.type == PropertyType.FLOAT and not isinstance(value, (int, float)):
                    raise TypeError(f"参数 {prop_name} 应为浮点数类型")
                elif prop_def.type == PropertyType.BOOL and not isinstance(value, bool):
                    raise TypeError(f"参数 {prop_name} 应为布尔类型")

        # 验证输入端口
        if inputs:
            for input_name in inputs:
                if input_name not in [port.name for port in self.inputs]:
                    raise ValueError(f"未知的输入端口: {input_name}")

    @classmethod
    def get_inputs(cls) -> List[Tuple[str, str]]:
        """返回输入端口定义：[('port_name', 'Port Label')]"""
        return [(port.name, port.label) for port in cls.inputs]

    @classmethod
    def get_outputs(cls) -> List[Tuple[str, str]]:
        """返回输出端口定义：[('port_name', 'Port Label')]"""
        return [(port.name, port.label) for port in cls.outputs]

    @classmethod
    def get_properties(cls) -> Dict[str, Dict[str, Any]]:
        """返回属性定义"""
        return {
            prop_name: prop_def.dict(exclude_unset=True)
            for prop_name, prop_def in cls.properties.items()
        }

    @classmethod
    def validate_outputs(cls, outputs: Dict[str, Any]) -> bool:
        """验证输出是否包含所有必需的输出端口"""
        required_ports = [port.name for port in cls.outputs]
        if outputs is None:
            return True
        for port in required_ports:
            if port not in outputs:
                return False
        return True

    @classmethod
    def get_input_model(cls) -> Type[BaseModel]:
        """动态创建输入数据模型"""
        fields = {}
        for port in cls.inputs:
            fields[port.name] = (Any, None)  # 所有输入端口都是可选的
        return create_model(f"{cls.__name__}Input", **fields)

    @classmethod
    def get_output_model(cls) -> Type[BaseModel]:
        """动态创建输出数据模型"""
        fields = {}
        for port in cls.outputs:
            fields[port.name] = (Any, ...)  # 所有输出端口都是必需的
        return create_model(f"{cls.__name__}Output", **fields)

    @classmethod
    def get_params_model(cls) -> Type[BaseModel]:
        """动态创建参数模型"""
        fields = {}
        for prop_name, prop_def in cls.properties.items():
            if prop_def.type == PropertyType.INT:
                field_type = int
                default = prop_def.default if prop_def.default != "" else 0
            elif prop_def.type == PropertyType.FLOAT:
                field_type = float
                default = prop_def.default if prop_def.default != "" else 0.0
            elif prop_def.type == PropertyType.BOOL:
                field_type = bool
                default = prop_def.default if prop_def.default != "" else False
            else:
                field_type = str
                default = prop_def.default if prop_def.default != "" else ""

            fields[prop_name] = (field_type, default)

        return create_model(f"{cls.__name__}Params", **fields)

    def set_sandbox_config(self, config: SandboxConfig):
        """设置沙箱配置"""
        self.sandbox_config = config
        self.sandbox = ComponentSandbox(self.sandbox_config)