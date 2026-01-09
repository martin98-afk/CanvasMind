# -*- coding: utf-8 -*-
import ast
import io
import json
import os
import pickle
import re
import sys
import time
import traceback
import uuid
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional
from typing import List, Tuple, Type, Union, OrderedDict
from typing import Literal

import numpy as np
import pandas as pd
from PIL import Image
from loguru import logger
from pydantic import BaseModel, Field
from pydantic import create_model

PROGRESS_MARKER = "PROGRESS_UPDATE_JSON:"
ENV_RULES = {
    "user_id": {"type": str, "readonly": True},
    "canvas_id": {"type": str, "readonly": True},
    "session_id": {"type": str, "readonly": True},
    "run_id": {"type": str, "readonly": True},
    "TZ": {"type": str, "pattern": r"^[A-Za-z_+-/]+$", "default": "Asia/Shanghai"},
    "LANG": {"type": str, "pattern": r"^[a-z]{2}_[A-Z]{2}\.UTF-8$", "default": "en_US.UTF-8"},
    "LC_ALL": {"type": str, "pattern": r"^[a-z]{2}_[A-Z]{2}\.UTF-8$", "default": "en_US.UTF-8"},

    "OMP_NUM_THREADS": {"type": str, "pattern": r"^\d+$", "default": "1"},
    "MKL_NUM_THREADS": {"type": str, "pattern": r"^\d+$", "default": "1"},
    "OPENBLAS_NUM_THREADS": {"type": str, "pattern": r"^\d+$", "default": "1"},
    "NUMEXPR_NUM_THREADS": {"type": str, "pattern": r"^\d+$", "default": "1"},

    "CUDA_VISIBLE_DEVICES": {"type": str, "pattern": r"^(\d+)(,\s*\d+)*$|^$", "default": "0"},

    "PYTHONPATH": {"type": str, "default": "."},
    "PYTHONUNBUFFERED": {"type": str, "allowed": {"1"}, "default": "1"},
    "PYTHONIOENCODING": {"type": str, "default": "utf-8"},
    "PYTHONWARNINGS": {"type": str, "default": "ignore"},
}


DEFAULT_PYTHON_ENV_VARS = {
    k: v["default"] for k, v in ENV_RULES.items() if "default" in v
}

COMPONENT_IMPORT_CODE = """# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
base_path = Path(__file__).parent.parent / "base.py"
spec = importlib.util.spec_from_file_location("base", str(base_path))
base_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base_module)

# 导入所需项目
BaseComponent = base_module.BaseComponent
PortDefinition = base_module.PortDefinition
PropertyDefinition = base_module.PropertyDefinition
PropertyType = base_module.PropertyType
ArgumentType = base_module.ArgumentType
ConnectionType = base_module.ConnectionType\n\n\n"""


# ==================== 中间消息通信协议 ====================

class MessageLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class ComponentMessage(BaseModel):
    """标准通信协议模型"""
    v: str = "1.0"  # 协议版本，用于未来兼容性处理
    msg_id: str = Field(default_factory=lambda: str(uuid.uuid4()))  # 消息唯一ID
    timestamp: float = Field(default_factory=time.time)  # 时间戳

    # 核心路由字段
    method: str  # 模拟 RPC 方法名，如 "ui.progress" 或 "data.preview"
    params: Dict[str, Any] = {}  # 参数负载

    # 上下文元数据
    level: MessageLevel = MessageLevel.INFO
    extra: Optional[Dict[str, Any]] = None  # 预留扩展空间


# ==================== 工具函数 ====================

def resource_path(relative_path) -> str:
    """获取打包后资源文件的绝对路径"""
    if hasattr(sys, '_MEIPASS'):
        # 如果是打包后的环境
        base_path = sys._MEIPASS
    else:
        # 开发环境，直接使用当前路径
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def canvas_file_dump_path(dump_location: str = "canvas_files") -> Path:
    dump_path = Path(dump_location)
    dump_path.mkdir(parents=True, exist_ok=True)
    return dump_path


def _get_node_temp_dir(node_id: Optional[str]) -> Path:
    """获取节点专属临时目录"""
    base_dir = canvas_file_dump_path() / "node_workspace" / node_id
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def _get_torch():
    """懒加载 torch"""
    global _TORCH_AVAILABLE, _TORCH_MODULE
    if not hasattr(_get_torch, "_cache"):
        _get_torch._cache = None
        try:
            import torch
            _get_torch._cache = torch
        except ImportError:
            _get_torch._cache = None
    return _get_torch._cache


@contextmanager
def temporary_env(env_dict: Dict[str, str]):
    old_env = {}
    try:
        for k, v in env_dict.items():
            old_env[k] = os.environ.get(k)
            os.environ[k] = str(v)
        yield
    finally:
        for k in env_dict:
            if old_env[k] is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old_env[k]


def validate_env_value(key: str, value: Any) -> str:
    """根据 ENV_RULES 校验并转换值为字符串"""
    if value is None:
        return ""

    # 强制转为字符串（OS env 本质是 str）
    if not isinstance(value, str):
        value = str(value)

    rule = ENV_RULES.get(key)
    if not rule:
        # 未知变量：允许，但只接受简单字符串（无换行、无 shell 元字符）
        if not re.match(r"^[a-zA-Z0-9._/-]*$", value):
            raise ValueError(f"Unsafe custom env var '{key}': contains special characters")
        return value

    # 检查 readonly
    if rule.get("readonly"):
        raise PermissionError(f"Environment variable '{key}' is read-only")

    # 检查 allowed values
    if "allowed" in rule and value not in rule["allowed"]:
        raise ValueError(f"Invalid value for '{key}': {value}, allowed: {rule['allowed']}")

    # 检查正则 pattern
    if "pattern" in rule and not re.fullmatch(rule["pattern"], value):
        raise ValueError(f"Value for '{key}' does not match pattern: {rule['pattern']}")

    return value


# ==================== 执行环境 ====================
class ExecutionEnvironment(BaseModel):
    user_id: Optional[str] = None
    canvas_id: Optional[str] = None
    session_id: Optional[str] = None
    run_id: Optional[str] = None
    metadata: Dict[str, str] = Field(default_factory=dict)  # 注意：现在只存 str

    def get_all_env_vars(self) -> Dict[str, str]:
        result = self.metadata.copy()
        for field in ["user_id", "canvas_id", "session_id", "run_id"]:
            val = getattr(self, field)
            if val is not None:
                result[field] = val
        return result

    def set_env_var(self, key: str, value: Any):
        # 所有 env 变量最终都是字符串
        safe_value = validate_env_value(key, value)

        if key in ["user_id", "canvas_id", "session_id", "run_id"]:
            # 这些字段本身有 readonly 保护（通过 validate_env_value）
            setattr(self, key, safe_value or None)
        else:
            self.metadata[key] = safe_value

    def delete_env_var(self, key: str):
        if key in ["user_id", "canvas_id", "session_id", "run_id"]:
            setattr(self, key, None)
        else:
            self.metadata.pop(key, None)

    class Config:
        # 允许 setattr 触发校验（但我们自己在 set_env_var 中做了）
        validate_assignment = True


class CustomVariable(BaseModel):
    value: Any = None
    description: Optional[str] = None
    read_only: bool = False


class NodeVariable(BaseModel):
    value: Any = None
    update_policy: Optional[str] = "固定"


class GlobalVariableContext(BaseModel):
    env: ExecutionEnvironment = Field(default_factory=ExecutionEnvironment)
    custom: OrderedDict[str, CustomVariable] = Field(default_factory=OrderedDict)
    node_vars: OrderedDict[str, NodeVariable] = Field(default_factory=OrderedDict)

    def __init__(self, **data):
        super().__init__(**data)
        # 初始化默认 Python 环境变量（仅当 metadata 为空时）
        self.deserialize(data)
        if not self.env.metadata:
            self.env.metadata.update(DEFAULT_PYTHON_ENV_VARS)

    class Config:
        arbitrary_types_allowed = True

    def set(self, key: str, value: Any) -> None:
        """设置自定义变量"""
        if key not in self.custom:
            self.custom[key] = CustomVariable(value=value)
        else:
            self.custom[key].value = value

    def set_output(self, node_id: str, output_name: str, output_value: Any, policy: str="更新"):
        self.node_vars[f"{node_id}__{output_name}"] = NodeVariable(
            value=output_value, update_policy=policy
        )

    def delete_output(self, node_id: str, output_name: str):
        self.node_vars.pop(f"{node_id}__{output_name}", None)

    def is_output_in_node_vars(self, node_id: str, output_name: str):
        return f"{node_id}__{output_name}" in self.node_vars

    def clear_node_vars(self, name: str):
        if isinstance(self.node_vars[name].value, (list, dict, tuple, set)):
            self.node_vars[name].value.clear()
        elif isinstance(self.node_vars[name].value, str):
            self.node_vars[name].value = ""
        else:
            self.node_vars[name].value = None

    def get_vars(self, extra_keys: List[str] = []):
        all_vars = []
        env_vars = self.env.get_all_env_vars()
        for key in sorted(self.node_vars.keys()):
            all_vars.append(f"node_vars.{key}")
        for key in sorted(self.custom.keys()):
            all_vars.append(f"custom.{key}")
        for key in sorted(env_vars.keys()):
            all_vars.append(f"env.{key}")
        return extra_keys + all_vars

    def to_dict(self) -> Dict[str, Any]:
        """兼容旧逻辑：返回扁平字典（仅 custom 变量）"""
        return {k: v.value for k, v in self.custom.items()} | self.env.get_all_env_vars() | {k: v.value for k, v in self.node_vars.items()}

    def serialize(self):
        return {
            "env": self.env.dict(),
            "custom": {k: v.dict() for k, v in self.custom.items()},
            "custom_order": list(self.custom.keys()),  # 显式保存顺序
            "node_vars": {k: v.dict() for k, v in self.node_vars.items()},
            "node_vars_order": list(self.node_vars.keys()),  # 显式保存顺序
        }

    def deserialize(self, data):
        history_env = data.get("env", {})
        self.env.metadata = self.env.metadata | history_env.get("metadata", {})
        self.env.user_id = history_env.get("user_id")
        self.env.canvas_id = history_env.get("canvas_id")
        self.env.session_id = history_env.get("session_id")
        self.env.run_id = history_env.get("run_id")
        # custom
        custom_data = data.get("custom", {})
        custom_order = data.get("custom_order", [])
        # 按 custom_order 顺序重建 OrderedDict，缺失的键放在最后（或忽略）
        self.custom = OrderedDict()
        for k in custom_order:
            if k in custom_data:
                self.custom[k] = CustomVariable(**custom_data[k])
        # 可选：补充未在 order 中的键（兼容旧数据）
        for k, v in custom_data.items():
            if k not in self.custom:
                self.custom[k] = CustomVariable(**v)

        # node_vars 同理
        node_vars_data = data.get("node_vars", {})
        node_vars_order = data.get("node_vars_order", [])
        self.node_vars = OrderedDict()
        for k in node_vars_order:
            if k in node_vars_data:
                v = node_vars_data[k]
                self.node_vars[k] = NodeVariable(**v) if isinstance(v, dict) else NodeVariable(value=v)
        for k, v in node_vars_data.items():
            if k not in self.node_vars:
                self.node_vars[k] = NodeVariable(**v) if isinstance(v, dict) else NodeVariable(value=v)

    def get(self, key: str, default=None) -> Any:
        if not isinstance(key, str):
            return default

        try:
            return self[key]  # 复用 __getitem__ 的全部逻辑
        except KeyError:
            return default

    def __getattr__(self, name: str):
        """支持 global_variable.variable_name 这种点号访问方式"""
        # 检查是否是预定义的属性（如 env, custom, node_vars）
        if name in {"env", "custom", "node_vars"}:
            return getattr(self, name)

        # 尝试在 custom 变量中查找
        if name in self.custom:
            return self.custom[name].value

        # 尝试在 env 变量中查找
        env_all = self.env.get_all_env_vars()
        if name in env_all:
            return env_all[name]

        # 尝试在 node_vars 中查找
        if name in self.node_vars:
            return self.node_vars[name].value

        # 如果都找不到，抛出 AttributeError
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def __getitem__(self, path: str) -> Any:
        if not isinstance(path, str):
            raise KeyError("Path must be a string")

        if "." not in path:
            # 扁平回退（兼容旧用法）
            if path in self.custom:
                return self.custom[path].value
            env_all = self.env.get_all_env_vars()
            if path in env_all:
                return env_all[path]
            if path in self.node_vars:
                return self.node_vars[path].value
            raise KeyError(f"Key '{path}' not found")

        parts = path.split(".", 1)  # 只拆第一层：如 "env.TZ" → ["env", "TZ"]
        root, subpath = parts[0], parts[1]

        if root == "env":
            # 先查预定义字段
            if subpath in {"user_id", "canvas_id", "session_id", "run_id"}:
                val = getattr(self.env, subpath, None)
                if val is not None:
                    return val
            # 再查 metadata
            if subpath in self.env.metadata:
                return self.env.metadata[subpath]
            # 都没有则报错
            raise KeyError(f"env has no variable '{subpath}'")

        elif root == "custom":
            if subpath in self.custom:
                return self.custom[subpath].value
            else:
                raise KeyError(f"Custom variable '{subpath}' not found")

        elif root == "node_vars":
            if subpath in self.node_vars:
                return self.node_vars[subpath].value
            else:
                raise KeyError(f"Node variable '{subpath}' not found")

        else:
            # 不是标准前缀，尝试扁平查找（如直接 "TZ"）
            env_all = self.env.get_all_env_vars()
            if path in self.custom:
                return self.custom[path].value
            if path in env_all:
                return env_all[path]
            if path in self.node_vars:
                return self.node_vars[path].value
            raise KeyError(f"Key '{path}' not found")


class ConnectionType(str, Enum):
    """连接类型"""
    SINGLE = "单输入"
    MULTIPLE = "多输入"


class PropertyType(str, Enum):
    """属性类型"""
    TEXT = "文本"
    MULTILINE = "多行文本"
    LONGTEXT = "长文本"
    INT = "整数"
    FLOAT = "浮点数"
    RANGE = "范围"
    BOOL = "复选框"
    CHOICE = "下拉框"
    VARIABLE = "动态变量"
    DYNAMICFORM = "动态表单"


class PropertyDefinition(BaseModel):
    """属性定义"""
    type: PropertyType = PropertyType.TEXT
    default: Any = ""
    label: str = ""
    choices: List[str] = Field(default_factory=list)
    filter: str = "All Files (*)"  # 用于文件类型过滤
    schema: Optional[Dict[str, 'PropertyDefinition']] = Field(default=None)  # 表单内每个字段的定义
    min: float = Field(default=0.0, description="最小值")
    max: float = Field(default=100.0, description="最大值")
    step: float = Field(default=1.0, description="步长")

    class Config:
        # 允许递归引用
        arbitrary_types_allowed = True


class ArgumentType(str, Enum):
    """参数类型"""
    TEXT = "文本"
    INT = "整数"
    FLOAT = "浮点数"
    BOOL = "布尔值"
    ARRAY = "列表"
    CSV = "csv"
    JSON = "json"
    EXCEL = "excel"
    FILE = "文件"
    UPLOAD = "上传"
    SKLEARNMODEL = "sklearn模型"
    TORCHMODEL = "torch模型"
    IMAGE = "图片"

    # 验证是否是文件类型
    def is_file(self):
        return self in [ArgumentType.FILE, ArgumentType.EXCEL, ArgumentType.SKLEARNMODEL,
                        ArgumentType.TORCHMODEL, ArgumentType.UPLOAD]

    def is_number(self):
        return self in [ArgumentType.INT, ArgumentType.FLOAT]

    def is_array(self):
        return self in [ArgumentType.ARRAY]

    def is_bool(self):
        return self == ArgumentType.BOOL

    def is_image(self):
        return self == ArgumentType.IMAGE


class PortDefinition(BaseModel):
    """端口定义"""
    name: str
    label: str
    type: ArgumentType = ArgumentType.TEXT
    connection: ConnectionType = ConnectionType.SINGLE

# ======= 构造pydantic输入、参数解析 ========
class ModelMixin(BaseModel):
    """为输入模型添加 .get() 和 [] 访问方法，兼容字典用法"""

    def get(self, key: str, default=None):
        # 直接查 __dict__，不触发任何钩子
        if key in self.__dict__:
            value = self.__dict__[key]
            return value if value is not None else default
        return default

    def __getattr__(self, item: str):
        # get() 不再调用 hasattr，所以不会递归
        return self.get(item)

    def __getitem__(self, key: str):
        if key in self.__dict__:
            value = self.__dict__[key]
            if value is not None:
                return value
        raise KeyError(key)

    def __contains__(self, key: str) -> bool:
        return key in self.__dict__ and self.__dict__[key] is not None


def _parse_default_value(default_str: str, target_type: type) -> Any:
    """安全解析默认值"""
    if default_str == "" or default_str is None:
        if target_type == int:
            return 0
        elif target_type == float:
            return 0.0
        elif target_type == bool:
            return False
        else:
            return ""

    try:
        if target_type == int:
            return int(default_str)
        elif target_type == float:
            return float(default_str)
        elif target_type == bool and isinstance(default_str, str):
            return default_str.lower() in ("true", "1", "yes", "on")
        else:
            return str(default_str)
    except (ValueError, TypeError):
        # 转换失败，返回类型默认值
        return _parse_default_value("", target_type)


def _create_dynamic_form_model(name: str, schema: Dict[str, 'PropertyDefinition']) -> Type[BaseModel]:
    """为 DYNAMICFORM 创建嵌套模型"""
    fields = {}
    for field_name, field_def in schema.items():
        if field_def.type == PropertyType.INT:
            ft = int
        elif field_def.type == PropertyType.FLOAT:
            ft = float
        elif field_def.type == PropertyType.BOOL:
            ft = bool
        elif field_def.type == PropertyType.RANGE:
            ft = Union[int, float]
        else:
            ft = str
        default_val = _parse_default_value(field_def.default, ft)
        # 修改这里：使用 Field 包装默认值
        fields[field_name] = (ft, Field(default=default_val))
    model_name = f"{name}Item"
    base_classes = (ModelMixin, BaseModel)
    return create_model(model_name, __base__=base_classes, **fields)


# =============== 节点错误解析 =============
class ComponentError(Exception):
    """组件执行错误"""

    def __init__(self, message: str, error_code: str = "COMPONENT_ERROR"):
        self.message = message
        self.error_code = error_code
        super().__init__(message)


# --- 数据处理器类 ---
class DataHandler:
    """
    专门处理组件输入输出数据的类。
    负责根据类型读取输入和存储输出。
    """
    def __init__(self, node_id: Optional[str] = None, workflow_path: Optional[str] = None, logger_instance=logger):
        self.node_id = node_id
        self.workflow_path = workflow_path
        self.logger = logger_instance or logger
        # 可以在这里添加更多与数据处理相关的状态或配置

    def read_input_data(self, input_name: str, input_value: Any, input_type: ArgumentType) -> Any:
        """根据输入类型读取数据，增强鲁棒性"""
        # 统一空值处理
        if input_value is None or (isinstance(input_value, str) and input_value.strip() == ""):
            if input_type.is_file():
                raise ComponentError(f"输入 {input_name} 为空或路径无效", "INPUT_EMPTY_ERROR")
            elif input_type.is_number():
                return 0 if input_type == ArgumentType.INT else 0.0
            elif input_type.is_bool():
                return False
            elif input_type.is_array():
                return np.array([])
            else:
                return ""
        if (input_type.is_file() or input_type.is_image()) and not Path(input_value).exists():
            stem_node_id = Path(input_value).parent.parent.stem
            if (Path(f"../{stem_node_id}/upload") / Path(input_value).name).exists():
                input_value = str(Path(f"../{stem_node_id}/upload") / Path(input_value).name)
            elif (Path("inputs") / Path(input_value).name).exists():
                input_value = str(Path("inputs") / Path(input_value).name)
            elif (Path(self.workflow_path).parent.parent.parent / input_value).exists():
                input_value = str(Path(self.workflow_path).parent.parent.parent / input_value)

        try:
            if input_type == ArgumentType.TEXT:
                return str(input_value)
            elif input_type == ArgumentType.INT:
                return int(float(input_value))  # 兼容 "1.0" 字符串
            elif input_type == ArgumentType.FLOAT:
                return float(input_value)
            elif input_type == ArgumentType.BOOL:
                if isinstance(input_value, str):
                    return input_value.lower() in ("true", "1", "yes", "on")
                return bool(input_value)
            elif input_type == ArgumentType.ARRAY:
                return self._read_array_data(input_name, input_value)
            elif input_type == ArgumentType.CSV:
                return self._read_csv_data(input_value)
            elif input_type == ArgumentType.JSON:
                return self._read_json_data(input_value)
            elif input_type == ArgumentType.EXCEL:
                return self._read_excel_data(input_value)
            elif input_type == ArgumentType.SKLEARNMODEL:
                return self._read_sklearn_model(input_value)
            elif input_type == ArgumentType.TORCHMODEL:
                return self._read_torch_model(input_value)
            elif input_type == ArgumentType.IMAGE:
                return self._read_image_data(input_value)
            else:
                return input_value
        except Exception as e:
            self.logger.error(f"读取输入 '{input_name}'（类型: {input_type}）失败: {e}")
            raise ComponentError(f"读取输入 {input_name} 失败: {str(e)}", "INPUT_READ_ERROR") from e

    def _read_array_data(self, input_name: str, data: Any) -> Union[list, np.ndarray]:
        """安全解析数组输入，优先返回 np.ndarray，失败则回退到 list"""
        if isinstance(data, np.ndarray):
            return data
        if isinstance(data, (list, tuple)):
            try:
                # 使用 dtype=object 提高兼容性（允许混合类型）
                return np.array(data)
            except Exception as e:
                self.logger.debug(f"输入 {input_name} 无法转为 np.ndarray，回退到 list: {e}")
                return list(data)
        if isinstance(data, str):
            try:
                import ast
                parsed = ast.literal_eval(data)
                if isinstance(parsed, (list, tuple)):
                    try:
                        return np.array(parsed)
                    except Exception as e:
                        self.logger.debug(f"字符串解析后无法转为 ndarray，回退到 list: {e}")
                        return list(parsed)
                else:
                    return parsed  # 单个值也视为数组
            except (ValueError, SyntaxError):
                return data  # 无法解析的字符串作为单元素
        return data  # 兜底：包装为单元素列表

    def _read_csv_data(self, data: Union[str, Path, pd.DataFrame]) -> pd.DataFrame:
        """读取CSV数据。如果输入是字符串或路径，则必须是存在的文件。"""
        if isinstance(data, (pd.DataFrame, pd.Series)):
            return data
        elif isinstance(data, (str, Path)):
            path = Path(data)
            if path.is_file():
                return pd.read_csv(str(path))
            else:
                # 修复：不再尝试将不存在的路径作为 CSV 字符串解析
                raise ComponentError(f"CSV 文件不存在: {path}")
        else:
            raise ComponentError(f"无法读取CSV数据，不支持的类型: {type(data)}")

    def _read_json_data(self, data: Union[str, dict, list, Path]) -> Union[dict, list, str]:
        """读取JSON数据。如果输入是字符串或路径，则尝试作为文件、标准JSON或Python字面量解析。"""
        if data is None or (isinstance(data, str) and not data.strip()):
            return {}
        if isinstance(data, (dict, list)):
            return data
        elif isinstance(data, (str, Path)):
            path = Path(data)
            if path.is_file():
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                # 尝试标准 JSON
                try:
                    return json.loads(data)
                except json.JSONDecodeError:
                    self.logger.debug(f"标准JSON解析失败，尝试作为Python字面量解析: {data[:100]}...")
                    try:
                        # 使用 ast.literal_eval 安全解析 Python 字面量（如单引号字典、列表）
                        parsed = ast.literal_eval(data)
                        if isinstance(parsed, (dict, list)):
                            return parsed
                        else:
                            # 如果解析出来不是 dict 或 list，说明不是我们期望的 JSON 结构
                            self.logger.warning(f"解析出的数据不是字典或列表，而是 {type(parsed)}: {data}")
                            raise ComponentError(f"输入内容解析后不是有效的JSON结构: {data}", "JSON_PARSE_ERROR")
                    except (ValueError, SyntaxError):
                        # ast.literal_eval 也失败了
                        self.logger.warning(f"Python字面量解析也失败: {type(data)} {data[:100]}...")
                        return data
        else:
            raise ComponentError(f"不支持的 JSON 输入类型: {type(data)}", "JSON_TYPE_ERROR")

    def _read_excel_data(self, data: Union[str, Path, pd.DataFrame]) -> pd.DataFrame:
        """读取Excel数据"""
        if isinstance(data, pd.DataFrame):
            return data
        elif isinstance(data, dict):
            for key, value in data.items():
                if not isinstance(value, pd.DataFrame):
                    raise ComponentError(f"无法读取Excel数据字典，key: {key}, value: {type(value)}")
            return data
        elif isinstance(data, (str, Path)):
            if os.path.exists(data):
                return pd.read_excel(data, sheet_name=None)
            else:
                raise ComponentError(f"Excel文件不存在: {data}")
        else:
            raise ComponentError(f"无法读取Excel数据: {type(data)}")

    def _read_sklearn_model(self, data: Union[str, Path]) -> Any:
        """读取sklearn模型"""
        if isinstance(data, (str, Path)) and os.path.exists(data):
            with open(data, 'rb') as f:
                return pickle.load(f)
        else:
            raise ComponentError(f"无法读取sklearn模型: {data}")

    def _read_torch_model(self, data: Union[str, Path]) -> Any:
        """读取torch模型"""
        torch = self._get_torch()
        if isinstance(data, (str, Path)) and os.path.exists(data):
            with open(data, 'rb') as f:
                return torch.export.load(f)
        else:
            raise ComponentError(f"无法读取torch模型: {data}")

    def _read_image_data(self, data: Union[str, Path]) -> Any:
        """读取图像数据"""
        if isinstance(data, (str, Path)) and os.path.exists(data):
            return Image.open(data)
        elif isinstance(data, Image.Image):
            return data
        elif isinstance(data, np.ndarray):
            return Image.fromarray(data)
        elif isinstance(data, bytes):
            return Image.open(io.BytesIO(data))
        else:
            raise ComponentError(f"无法读取图像数据: {data}")

    def _read_file_data(self, data: Any) -> Path:
        """读取任意文件内容（路径、bytes、str），返回临时路径"""
        temp_dir = self._get_node_temp_dir()
        if isinstance(data, (str, Path)):
            path = Path(data)
            if path.is_file():
                # 如果是已存在的文件路径，直接返回（也可复制到 temp_dir 保持隔离）
                import shutil
                dst = temp_dir / path.name
                shutil.copy2(path, dst)
                return dst
            else:
                # 假设是文本内容，保存为 file.txt
                dst = temp_dir / "file.txt"
                dst.write_text(str(data), encoding='utf-8')
                return dst
        elif isinstance(data, bytes):
            dst = temp_dir / "file.bin"
            dst.write_bytes(data)
            return dst
        else:
            # 兜底：转为字符串保存
            dst = temp_dir / "file.txt"
            dst.write_text(str(data), encoding='utf-8')
            return dst

    def _process_multiple_inputs(self, input_name: str, input_values: List[Any], input_type: ArgumentType) -> List[Any]:
        if input_values is None:
            return []
        return [
            self.read_input_data(input_name, val, input_type)
            for val in input_values
        ]

    # --- 输出数据存储 ---
    def store_output_data(self, output_name: str, output_value: Any, output_type: ArgumentType) -> Any:
        """根据输出类型存储数据，支持按 node_id 持久化"""
        try:
            if output_type == ArgumentType.TEXT:
                return str(output_value) if output_value is not None else ""
            elif output_type == ArgumentType.INT:
                return int(output_value) if output_value is not None else 0
            elif output_type == ArgumentType.FLOAT:
                return float(output_value) if output_value is not None else 0.0
            elif output_type == ArgumentType.ARRAY:
                return output_value
            elif output_type == ArgumentType.CSV:
                return self._store_csv_data(output_value)
            elif output_type == ArgumentType.JSON:
                return self._store_json_data(output_value)
            elif output_type == ArgumentType.EXCEL:
                return self._store_excel_data(output_value)
            elif output_type == ArgumentType.SKLEARNMODEL:
                return self._store_sklearn_model(output_value)
            elif output_type == ArgumentType.TORCHMODEL:
                return self._store_torch_model(output_value)
            elif output_type == ArgumentType.IMAGE:
                return self._store_image_data(output_value)
            elif output_type == ArgumentType.FILE:
                return self._store_file_data(output_value, output_name)
            else:
                return output_value
        except Exception as e:
            raise ComponentError(f"存储输出 {output_name} 失败: {str(e)}", "OUTPUT_STORE_ERROR")

    def _store_csv_data(self, data: pd.DataFrame) -> Union[pd.DataFrame, str, Path]:
        """存储CSV数据"""
        if isinstance(data, (pd.DataFrame, pd.Series)):
            return data
        elif isinstance(data, (str, Path)):
            if os.path.exists(data):
                return pd.read_csv(data)
            else:
                # 如果是CSV字符串
                import io
                return pd.read_csv(io.StringIO(data))
        else:
            raise ComponentError(f"无法存储CSV数据: {type(data)}")

    def _store_json_data(self, data: Union[dict, list]) -> str:
        """存储JSON数据（直接返回）"""
        return data

    def _store_excel_data(self, data: pd.DataFrame) -> Union[dict[pd.DataFrame], str, Path]:
        """存储Excel数据"""
        import io
        if isinstance(data, pd.DataFrame):
            return data
        elif isinstance(data, (str, Path)):
            if os.path.exists(data):
                return pd.read_excel(data, sheet_name=None)
            else:
                return pd.read_excel(io.StringIO(data))
        else:
            raise ComponentError(f"无法存储Excel数据: {type(data)}")

    def _store_sklearn_model(self, model: Any) -> str:
        """存储sklearn模型到节点专属目录"""
        temp_dir = self._get_node_temp_dir()
        model_path = temp_dir / f"model_{self.node_id}.pkl"
        with open(model_path.resolve(), 'wb') as f:
            pickle.dump(model, f)
        return str(model_path)

    def _store_torch_model(self, model: Any) -> str:
        """存储torch模型到节点专属目录"""
        torch = self._get_torch()
        if torch is None:
            raise ComponentError("torch 未安装", "MISSING_DEPENDENCY")
        temp_dir = self._get_node_temp_dir()
        model_path = str(temp_dir / f"model_{self.node_id}.pt2")
        with open(model_path, 'wb') as f:
            torch.export.save(model, f)
        return model_path

    def _store_image_data(self, image: Any) -> str:
        """存储图像数据到节点专属目录"""
        if isinstance(image, np.ndarray):
            image = Image.fromarray(image)
        elif not isinstance(image, Image.Image):
            raise ComponentError(f"无法存储图像数据: {type(image)}")
        temp_dir = self._get_node_temp_dir()
        image_path = temp_dir / f"image_{self.node_id}.png"
        image.save(image_path.resolve(), 'PNG')
        return str(image_path)

    def _store_file_data(self, data: Any, output_name: str = "output_file") -> str:
        """存储任意文件数据，使用 output_name 作为文件名"""
        temp_dir = self._get_node_temp_dir()
        # 保留扩展名：如果 output_name 有后缀，直接用；否则尝试推断或默认 .bin
        filename = Path(output_name).name or "output_file"
        if "{{now}}" in filename:
            filename = filename.replace("{{now}}", datetime.now().strftime("%Y%m%d%H%M%S"))
        if "." not in filename:
            # 尝试推断扩展名（可选）
            if isinstance(data, str):
                filename += ".txt"
            elif isinstance(data, bytes):
                filename += ".bin"
            else:
                filename += ".dat"
        file_path = temp_dir / filename
        if isinstance(data, (str, Path)):
            path = Path(data)
            if path.is_file():
                import shutil
                shutil.copy2(path, file_path.resolve())
            else:
                file_path.write_text(str(data), encoding='utf-8')
        elif isinstance(data, bytes):
            file_path.write_bytes(data)
        else:
            # 兜底：转为字符串
            file_path.write_text(str(data), encoding='utf-8')
        return str(file_path)

    # --- 辅助方法 ---
    def _get_node_temp_dir(self) -> Path:
        """获取节点专属临时目录"""
        # 假设 canvas_file_dump_path 是一个全局函数或从其他地方导入
        # 这里简化处理，实际项目中需要正确引用
        if self.workflow_path is None:
            dump_path = Path("canvas_files") / "node_workspace" / (self.node_id or "default") / "results"
        else:
            dump_path = (Path(self.workflow_path) / "node_workspace" / (self.node_id or "default")) / "results"
        dump_path.mkdir(parents=True, exist_ok=True)
        return dump_path

    def _get_torch(self):
        """懒加载 torch"""
        if not hasattr(self, "_torch_cache"):
            self._torch_cache = None
            try:
                import torch
                self._torch_cache = torch
            except ImportError:
                self._torch_cache = None
        return self._torch_cache


# ========= 组件基类  =========
class BaseComponent(ABC):
    """所有组件必须继承此类"""
    # 组件配置（子类需要定义）
    name: str = ""
    category: str = ""
    description: str = ""
    requirements: str = ""
    inputs: List[PortDefinition] = []
    outputs: List[PortDefinition] = []
    properties: Dict[str, PropertyDefinition] = {}
    logger = logger
    global_variable: GlobalVariableContext = GlobalVariableContext()

    @abstractmethod
    def run(self, params: BaseModel, inputs: BaseModel = None) -> Dict[str, Any]:
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        pass

    @classmethod
    def get_inputs(cls) -> List[Tuple[str, str, str]]:
        """返回输入端口定义：[('port_name', 'Port Label')]"""
        return [(port.name, port.label, port.connection) for port in cls.inputs]

    @classmethod
    def get_outputs(cls) -> List[Tuple[str, str]]:
        """返回输出端口定义：[('port_name', 'Port Label')]"""
        return [(port.name, port.label) for port in cls.outputs]

    @classmethod
    def get_output_type(cls):
        return {port.name: port.type for port in cls.outputs}

    @classmethod
    def get_properties(cls) -> Dict[str, Dict[str, Any]]:
        return {
            prop_name: prop_def.dict(exclude_unset=True)
            for prop_name, prop_def in cls.properties.items()
        }

    @classmethod
    def validate_outputs(cls, outputs: Dict[str, Any]) -> bool:
        """验证输出是否包含所有必需的输出端口"""
        required_ports = [port.name for port in cls.outputs]
        for port in required_ports:
            if port not in outputs:
                return False
        return True

    # 输入输出数据模型
    @classmethod
    def get_input_model(cls) -> Type[BaseModel]:
        """动态创建输入数据模型，并支持 .get() 方法"""
        fields = {}
        for port in cls.inputs:
            # 所有输入端口都是可选的，默认 None
            fields[port.name] = (Any, None)

        # 创建模型，并混入 InputModelMixin
        model_name = f"{cls.__name__}Input"
        base_classes = (ModelMixin, BaseModel)
        return create_model(model_name, __base__=base_classes, **fields)

    @classmethod
    def get_output_model(cls) -> Type[BaseModel]:
        """动态创建输出数据模型"""
        fields = {}
        for port in cls.outputs:
            fields[port.name] = (Any, ...)  # 所有输出端口都是必需的
            # 创建模型，并混入 InputModelMixin
            model_name = f"{cls.__name__}Output"
            base_classes = (ModelMixin, BaseModel)
            return create_model(model_name, __base__=base_classes, **fields)

    @classmethod
    def get_params_model(cls) -> Type[BaseModel]:
        """动态创建参数模型（支持 CHOICE / DYNAMICFORM）"""
        fields: Dict[str, tuple] = {}

        for prop_name, prop_def in cls.properties.items():
            le, ge = None, None
            if prop_def.type == PropertyType.INT:
                field_type = int
                default_val = _parse_default_value(prop_def.default, int)

            elif prop_def.type == PropertyType.FLOAT:
                field_type = float
                default_val = _parse_default_value(prop_def.default, float)

            elif prop_def.type == PropertyType.BOOL:
                field_type = bool
                default_val = _parse_default_value(prop_def.default, bool)

            elif prop_def.type == PropertyType.CHOICE:
                choices = prop_def.choices
                # 动态创建 Literal 类型
                field_type = Literal[tuple(choices)]  # type: ignore
                default_val = prop_def.default if prop_def.default in choices else choices[0]
            elif prop_def.type == PropertyType.RANGE:
                field_type = float if isinstance(prop_def.step, float) else int
                default_val = _parse_default_value(prop_def.default, field_type)
                ge = prop_def.min
                le = prop_def.max
            elif prop_def.type == PropertyType.DYNAMICFORM:
                # 创建嵌套模型，并用 List[Model] 表示
                item_model = _create_dynamic_form_model(prop_name, prop_def.schema or {})
                field_type = List[item_model]  # type: ignore
                default_val = []  # 默认空列表

            else:  # TEXT 等
                field_type = str
                default_val = prop_def.default if prop_def.default != "" else ""

            # 使用 Field 确保默认值正确
            if le is not None:
                fields[prop_name] = (field_type, Field(default=default_val, le=le, ge=ge))
            else:
                fields[prop_name] = (field_type, Field(default=default_val))

        model_name = f"{cls.__name__}Params"
        base_classes = (ModelMixin, BaseModel)
        return create_model(model_name, __base__=base_classes, **fields)

    # ----------------中间结果流式返回----------------
    def emit_custom_message(self, method: str, params: Dict[str, Any], level=MessageLevel.INFO):
        """
        规范化的通信接口
        """
        msg = ComponentMessage(
            method=method,
            params=params,
            level=level
        )
        # 通过 stdout 发送加密/编码后的 JSON，防止业务日志干扰
        print(f"{PROGRESS_MARKER}{msg.json()}", flush=True)

    def ask_user(self, title: str, message: str, schema: Dict[str, Any] = None) -> Any:
        """
        人工干预接口
        """
        request_id = str(uuid.uuid4())
        # 获取当前运行目录，这个目录在 execute 脚本中会被设置到环境变量
        run_dir = canvas_file_dump_path() / "jrpc_response" / self.node_id
        response_path = run_dir / f"response_{request_id}.pkl"

        # 1. 发送指令给 UI (通过日志流)
        self.emit_custom_message("ui.ask", {
            "request_id": request_id,
            "title": title,
            "message": message,
            "schema": schema,
            "response_file": str(response_path) # 告知 UI 结果写到哪
        }, level=MessageLevel.WARNING)

        self.logger.info(f"等待人工干预 [ID: {request_id}]...")

        # 2. 轮询等待响应
        start_wait = time.time()
        while not response_path.exists():
            time.sleep(0.5)
            # 可选：增加一个总超时，防止进程永久挂起
            if time.time() - start_wait > 3600: # 1小时超时
                raise ComponentError("人工干预超时")

        # 3. 读取结果并清理
        try:
            with open(response_path, 'rb') as f:
                data = pickle.load(f)
            if response_path.exists():
                os.remove(response_path)
            return data
        except Exception as e:
            raise ComponentError(f"读取干预结果失败: {e}")

    def update_progress(self, percent: int, status_text: str = ""):
        """快捷方式：更新进度"""
        self.emit_custom_message("ui.progress", {"value": percent, "text": status_text})

    def send_preview(self, data_type: str, payload: Any):
        """快捷方式：发送数据预览"""
        self.emit_custom_message("data.preview", {"type": data_type, "data": payload})

    # ---------------- 执行包装器 ----------------
    def execute(
            self,
            params: Dict[str, Any],
            inputs: Optional[Dict[str, Any]] = None,
            global_vars: Dict[str, Any] = None,
            node_id: str = None,
            workflow_path: str = None
    ) -> Dict[str, Any]:
        """执行组件，包含错误处理和数据类型转换"""
        self.node_id = node_id
        self.data_handler = DataHandler(node_id=node_id, workflow_path=workflow_path, logger_instance=self.logger)
        try:
            if global_vars is not None:
                self.global_variable.deserialize(global_vars)
            params_model = self.get_params_model()
            validated_params = params_model(**params)
            input_model_cls = self.get_input_model()
            validated_inputs = {}
            if inputs:
                for port in self.inputs:
                    if port.name in inputs:
                        if port.connection == ConnectionType.MULTIPLE:
                            validated_inputs[port.name] = self.data_handler._process_multiple_inputs(
                                port.name, inputs[port.name], port.type
                            )
                        else:
                            validated_inputs[port.name] = self.data_handler.read_input_data(
                                port.name, inputs[port.name], port.type
                            )
                    if f"{port.name}_column_select" in inputs:
                        validated_inputs[port.name] = validated_inputs[port.name][inputs[f"{port.name}_column_select"]]

            validated_inputs = input_model_cls(**validated_inputs)
            safe_env = {
                k: str(v) for k, v in self.global_variable.env.get_all_env_vars().items()
                if v is not None
            }

            with temporary_env(safe_env):
                result = self.run(validated_params, validated_inputs)

            if not self.validate_outputs(result):
                missing_outputs = [port.name for port in self.outputs if port.name not in result]
                logger.warning(f"组件输出缺少必需的端口: {missing_outputs}", "OUTPUT_VALIDATION_ERROR")

            # ✅ 关键：传递 node_id 给 store_output_data
            stored_result = {}
            for port in self.outputs:
                if port.name in result:
                    stored_result[port.name] = self.data_handler.store_output_data(
                        port.name, result[port.name], port.type
                    )

            return stored_result

        except ImportError as e:
            raise ComponentError(f"环境安装包缺失: {e}", "MISSING_DEPENDENCY")

        except Exception as e:
            raise ComponentError(f"组件执行失败: {traceback.format_exc()}", "EXECUTION_ERROR")

    # ---------------- 组件调试专用方法 ----------------
    def debug(self,
              params: Dict[str, Any] = None,
              inputs: Dict[str, Any] = None,
              global_vars: Dict[str, Any] = None,
              node_id: str = str(uuid.uuid4()),
              show_input_types: bool = True,
              show_output_types: bool = True,
              show_execution_time: bool = True) -> Dict[str, Any]:
        """
        通用调试函数，用于测试组件运行效果

        Args:
            params: 组件参数，如果为None则使用默认值
            inputs: 输入数据，如果为None则使用默认值
            global_vars: 全局变量上下文
            node_id: 节点ID，用于临时文件存储
            show_input_types: 是否显示输入数据类型信息
            show_output_types: 是否显示输出数据类型信息
            show_execution_time: 是否显示执行时间

        Returns:
            Dict[str, Any]: 执行结果
        """
        import time

        # 设置默认参数
        if params is None:
            params = {}
            params_model = self.get_params_model()
            # 使用模型的默认值
            try:
                default_params = params_model()
                params = default_params.dict()
            except Exception:
                params = {}

        if inputs is None:
            inputs = {}
            # 为每个输入端口设置默认值
            for port in self.inputs:
                if port.type == ArgumentType.TEXT:
                    inputs[port.name] = ""
                elif port.type == ArgumentType.INT:
                    inputs[port.name] = 0
                elif port.type == ArgumentType.FLOAT:
                    inputs[port.name] = 0.0
                elif port.type == ArgumentType.BOOL:
                    inputs[port.name] = False
                elif port.type == ArgumentType.ARRAY:
                    inputs[port.name] = []
                elif port.type == ArgumentType.CSV:
                    inputs[port.name] = pd.DataFrame()
                elif port.type == ArgumentType.JSON:
                    inputs[port.name] = {}
                elif port.type == ArgumentType.EXCEL:
                    inputs[port.name] = pd.DataFrame()
                else:
                    inputs[port.name] = None

        # 显示输入信息
        if show_input_types:
            print("=" * 50)
            print("DEBUG: 输入数据信息")
            print("-" * 30)
            for port in self.inputs:
                input_data = inputs.get(port.name)
                print(f"输入端口 '{port.name}' ({port.label}):")
                print(f"  类型: {type(input_data)}")
                print(f"  值: {self._format_value(input_data)}")
                print(f"  期望类型: {port.type}")
                print()
            print("-" * 30)
            for property, prop_def in self.properties.items():
                input_param = params.get(property)
                print(f"参数 '{property}' ({prop_def.label}):")
                print(f"  类型: {type(input_param)}")
                print(f"  值: {self._format_value(input_param)}")
                print(f"  期望类型: {prop_def.type}")
                print()
            print("-" * 30)

        # 记录执行时间
        start_time = None
        if show_execution_time:
            start_time = time.time()

        try:
            print("DEBUG: 组件执行日志信息")
            # 执行组件
            result = self.execute(params, inputs, global_vars, node_id)
            print()
            print("-" * 30)
            print()
            if show_execution_time and start_time is not None:
                execution_time = time.time() - start_time
                print(f"执行时间: {execution_time:.4f} 秒")
                print()

            # 显示输出信息
            if show_output_types:
                print("DEBUG: 输出数据信息")
                print("-" * 30)
                for port in self.outputs:
                    if port.name in result:
                        output_data = result[port.name]
                        print(f"输出端口 '{port.name}' ({port.label}):")
                        print(f"  类型: {type(output_data)}")
                        print(f"  值: {self._format_value(output_data)}")
                        print(f"  期望类型: {port.type}")
                        print()

            print("=" * 50)
            print("DEBUG: 执行成功!")
            print(f"组件: {self.name}")
            print(f"输出: {result}")
            print("=" * 50)

            return result

        except Exception as e:
            print("=" * 50)
            print("DEBUG: 执行失败!")
            print(f"组件: {self.name}")
            print(f"错误: {str(e)}")
            print(f"错误类型: {type(e).__name__}")
            print("=" * 50)
            raise e

    def _format_value(self, value: Any, max_length: int = 100) -> str:
        """
        格式化值以便显示，避免过长的输出

        Args:
            value: 要格式化的值
            max_length: 最大显示长度

        Returns:
            str: 格式化后的字符串
        """
        if value is None:
            return "None"

        # 处理不同类型的值
        if isinstance(value, (str, int, float, bool)):
            str_val = str(value)
            if len(str_val) > max_length:
                return str_val[:max_length - 3] + "..."
            return str_val

        elif isinstance(value, (list, tuple)):
            if len(value) == 0:
                return f"{type(value).__name__}([])"
            elif len(value) <= 5:  # 小数组完整显示
                items = [self._format_value(item, max_length // 3) for item in value]
                return f"{type(value).__name__}({items})"
            else:  # 大数组只显示前几个
                items = [self._format_value(item, max_length // 3) for item in value[:5]]
                return f"{type(value).__name__}({items}... 共{len(value)}项)"

        elif isinstance(value, dict):
            if len(value) == 0:
                return "dict({})"
            elif len(value) <= 3:  # 小字典完整显示
                items = {k: self._format_value(v, max_length // 3) for k, v in value.items()}
                return f"dict({items})"
            else:  # 大字典只显示前几个
                items = {k: self._format_value(v, max_length // 3) for k, v in list(value.items())[:3]}
                return f"dict({{...}} 共{len(value)}项)"

        elif isinstance(value, pd.DataFrame):
            return f"DataFrame(shape={value.shape}, columns={list(value.columns)})"

        elif isinstance(value, np.ndarray):
            return f"ndarray(shape={value.shape}, dtype={value.dtype})"

        elif hasattr(value, '__class__'):
            # 其他对象显示类型和主要属性
            return f"{type(value).__name__} object"

        else:
            return f"{type(value).__name__}: {str(value)[:max_length]}"