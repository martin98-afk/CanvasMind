# -*- coding: utf-8 -*-
import json
import os
import pickle
import re
import uuid
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import List, Tuple, Type, Union
from typing import Any, Dict, Optional

from pandas import DataFrame
from pydantic import BaseModel, Field
from enum import Enum

import numpy as np
import pandas as pd
from PIL import Image
from loguru import logger
from pydantic import create_model


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
import pathlib
base_path = pathlib.Path(__file__).parent.parent / "base.py"
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


# ==================== 工具函数 ====================

def _get_node_temp_dir(node_id: Optional[str]) -> Path:
    """获取节点专属临时目录"""
    if not node_id:
        # 无 node_id 时回退到系统临时目录（兼容旧逻辑）
        import tempfile
        return Path(tempfile.mkdtemp())

    base_dir = Path("temp_runs") / "nodes" / node_id
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
    custom: Dict[str, CustomVariable] = Field(default_factory=dict)
    node_vars: Dict[str, NodeVariable] = Field(default_factory=dict)

    def __init__(self, **data):
        super().__init__(**data)
        # 初始化默认 Python 环境变量（仅当 metadata 为空时）
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

    def set_output(self, node_id: str, output_name: str, output_value: Any, policy: str="固定"):
        self.node_vars[f"{node_id}_{output_name}"] = NodeVariable(
            value=output_value, update_policy=policy
        )

    def to_dict(self) -> Dict[str, Any]:
        """兼容旧逻辑：返回扁平字典（仅 custom 变量）"""
        return {k: v.value for k, v in self.custom.items()} | self.env.get_all_env_vars() | {k: v.value for k, v in self.node_vars.items()}

    def serialize(self):
        return {
            "env": self.env.dict(),
            "custom": {k: v.dict() for k, v in self.custom.items()},
            "node_vars": {k: v.dict() for k, v in self.node_vars.items()}
        }

    def deserialize(self, data):
        history_env = data.get("env", {})
        self.env.metadata = self.env.metadata | history_env.get("metadata", {})
        self.env.user_id = history_env.get("user_id")
        self.env.canvas_id = history_env.get("canvas_id")
        self.env.session_id = history_env.get("session_id")
        self.env.run_id = history_env.get("run_id")
        self.custom = {k: CustomVariable(**v) for k, v in data.get("custom", {}).items()}
        self.node_vars = {
            k: NodeVariable(**v) if isinstance(v, dict) else NodeVariable(value=v)
            for k, v in data.get("node_vars", {}).items()
        }

    def get(self, key: str, default=None) -> Any:
        if not isinstance(key, str):
            return default

        try:
            return self[key]  # 复用 __getitem__ 的全部逻辑
        except KeyError:
            return default

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
    VARIABLE = "全局变量"
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


class ModelMixin:
    """为输入模型添加 .get() 和 [] 访问方法，兼容字典用法"""

    def get(self, key: str, default=None):
        """
        类似 dict.get()：
        - 如果字段存在且不为 None，返回值
        - 如果字段不存在或值为 None，返回 default
        """
        if hasattr(self, key):
            value = getattr(self, key)
            return value if value is not None else default
        return default

    def __getitem__(self, key: str):
        """
        支持 item["key"] 语法
        - 如果字段存在且不为 None，返回值
        - 如果字段不存在或值为 None，抛出 KeyError（与 dict 行为一致）
        """
        if hasattr(self, key):
            value = getattr(self, key)
            if value is not None:
                return value
        raise KeyError(key)

    def __contains__(self, key: str) -> bool:
        """支持 "key" in item 语法"""
        return hasattr(self, key) and getattr(self, key) is not None


class ComponentError(Exception):
    """组件执行错误"""

    def __init__(self, message: str, error_code: str = "COMPONENT_ERROR"):
        self.message = message
        self.error_code = error_code
        super().__init__(message)


class BaseComponent(ABC):
    """所有组件必须继承此类"""
    # 组件配置（子类需要定义）
    name: str = ""
    category: str = ""
    description: str = ""
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
                # 使用 Literal 限制选项
                from typing import Literal
                choices = prop_def.choices or ["option1"]
                # 动态创建 Literal 类型
                field_type = Literal[tuple(choices)]  # type: ignore
                default_val = prop_def.default if prop_def.default in choices else choices[0]
            elif prop_def.type == PropertyType.RANGE:
                field_type = float if isinstance(prop_def.step, float) else int
                default_val = _parse_default_value(prop_def.default, field_type)
                fields[prop_name] = (field_type, Field(default=default_val, ge=prop_def.min, le=prop_def.max))
            elif prop_def.type == PropertyType.DYNAMICFORM:
                # 创建嵌套模型，并用 List[Model] 表示
                item_model = _create_dynamic_form_model(prop_name, prop_def.schema or {})
                field_type = List[item_model]  # type: ignore
                default_val = []  # 默认空列表

            else:  # TEXT 等
                field_type = str
                default_val = prop_def.default if prop_def.default != "" else ""

            # 使用 Field 确保默认值正确
            fields[prop_name] = (field_type, Field(default=default_val))

        model_name = f"{cls.__name__}Params"
        base_classes = (ModelMixin, BaseModel)
        return create_model(model_name, __base__=base_classes, **fields)

    # ---------------- 输入数据读取 ----------------
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
            elif input_type == ArgumentType.FILE:
                return self._read_file_data(input_value)
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
                return np.array(data, dtype=object)
            except Exception as e:
                self.logger.debug(f"输入 {input_name} 无法转为 np.ndarray，回退到 list: {e}")
                return list(data)
        if isinstance(data, str):
            try:
                import ast
                parsed = ast.literal_eval(data)
                if isinstance(parsed, (list, tuple)):
                    try:
                        return np.array(parsed, dtype=object)
                    except Exception as e:
                        self.logger.debug(f"字符串解析后无法转为 ndarray，回退到 list: {e}")
                        return list(parsed)
                else:
                    return [parsed]  # 单个值也视为数组
            except (ValueError, SyntaxError):
                return [data]  # 无法解析的字符串作为单元素
        return [data]  # 兜底：包装为单元素列表

    def _read_csv_data(self, data: Union[str, Path, pd.DataFrame]) -> pd.DataFrame:
        """读取CSV数据"""
        if isinstance(data, pd.DataFrame):
            return data
        elif isinstance(data, (str, Path)):
            if os.path.exists(data):
                return pd.read_csv(data)
            else:
                # 如果是CSV字符串
                import io
                return pd.read_csv(io.StringIO(data))
        else:
            raise ComponentError(f"无法读取CSV数据: {type(data)}")

    def _read_json_data(self, data: Union[str, dict, list, Path]) -> Union[dict, list]:
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
                    # 尝试修复单引号（仅当明显是 dict/list 字符串时）
                    if data.strip().startswith(("{", "[")) and data.strip().endswith(("}", "]")):
                        try:
                            fixed = data.replace("'", '"')
                            return json.loads(fixed)
                        except Exception:
                            pass
                    self.logger.warning(f"JSON 输入无法解析: {data[:100]}...")
                    raise ComponentError(f"无效 JSON 数据: {type(data)}", "JSON_PARSE_ERROR")
        else:
            raise ComponentError(f"不支持的 JSON 输入类型: {type(data)}", "JSON_TYPE_ERROR")

    def _read_excel_data(self, data: Union[str, Path, pd.DataFrame]) -> pd.DataFrame:
        """读取Excel数据"""
        if isinstance(data, pd.DataFrame):
            return data
        elif isinstance(data, (str, Path)):
            if os.path.exists(data):
                return pd.read_excel(data)
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
        torch = _get_torch()
        if isinstance(data, (str, Path)) and os.path.exists(data):
            return torch.jit.load(data)
        else:
            raise ComponentError(f"无法读取torch模型: {data}")

    def _read_image_data(self, data: Union[str, Path]) -> Any:
        """读取图像数据"""
        from PIL import Image
        if isinstance(data, (str, Path)) and os.path.exists(data):
            return Image.open(data)
        else:
            raise ComponentError(f"无法读取图像数据: {data}")

    def _read_file_data(self, data: Union[str, Path]) -> str:
        file_path = Path(data)
        if not file_path.exists():
            raise ComponentError(f"文件不存在: {file_path}", "FILE_NOT_FOUND")

        try:
            return file_path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            try:
                return file_path.read_text(encoding='gbk')
            except UnicodeDecodeError:
                return file_path.read_bytes().decode('utf-8', errors='ignore')

    def _process_multiple_inputs(self, input_name: str, input_values: List[Any], input_type: ArgumentType) -> List[Any]:
        if not isinstance(input_values, (list, tuple)):
            input_values = [input_values]
        return [
            self.read_input_data(input_name, val, input_type)
            for val in input_values
        ]

    # ---------------- 输出数据存储 ----------------
    def store_output_data(self, output_name: str, output_value: Any, output_type: ArgumentType, node_id: str = None) -> Any:
        """根据输出类型存储数据，支持按 node_id 持久化"""
        try:
            if output_type == ArgumentType.TEXT:
                return str(output_value) if output_value is not None else ""
            elif output_type == ArgumentType.INT:
                return int(output_value) if output_value is not None else 0
            elif output_type == ArgumentType.FLOAT:
                return float(output_value) if output_value is not None else 0.0
            elif output_type == ArgumentType.ARRAY:
                if isinstance(output_value, np.ndarray):
                    return output_value.tolist()
                return output_value
            elif output_type == ArgumentType.CSV:
                return self._store_csv_data(output_value)
            elif output_type == ArgumentType.JSON:
                return self._store_json_data(output_value)
            elif output_type == ArgumentType.EXCEL:
                return self._store_excel_data(output_value, node_id)
            elif output_type == ArgumentType.SKLEARNMODEL:
                return self._store_sklearn_model(output_value, node_id)
            elif output_type == ArgumentType.TORCHMODEL:
                return self._store_torch_model(output_value, node_id)
            elif output_type == ArgumentType.IMAGE:
                return self._store_image_data(output_value, node_id)
            elif output_type == ArgumentType.FILE:
                return self._store_file_data(output_value, node_id)
            else:
                return output_value
        except Exception as e:
            raise ComponentError(f"存储输出 {output_name} 失败: {str(e)}", "OUTPUT_STORE_ERROR")

    def _store_csv_data(self, data: pd.DataFrame) -> Union[DataFrame, str, Path]:
        """存储CSV数据"""
        if isinstance(data, pd.DataFrame):
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

    def _store_excel_data(self, data: pd.DataFrame) -> Union[DataFrame, str, Path]:
        """存储Excel数据"""
        import io
        if isinstance(data, pd.DataFrame):
            return data
        elif isinstance(data, (str, Path)):
            if os.path.exists(data):
                return pd.read_excel(data)
            else:
                return pd.read_excel(io.StringIO(data))
        else:
            raise ComponentError(f"无法存储Excel数据: {type(data)}")

    def _store_sklearn_model(self, model: Any, node_id: str = None) -> str:
        """存储sklearn模型到节点专属目录"""
        temp_dir = _get_node_temp_dir(node_id)
        model_path = temp_dir / f"model_{uuid.uuid4().hex}.pkl"
        with open(model_path, 'wb') as f:
            pickle.dump(model, f)
        return str(model_path)

    def _store_torch_model(self, model: Any, node_id: str = None) -> str:
        """存储torch模型到节点专属目录"""
        torch = _get_torch()
        if torch is None:
            raise ComponentError("torch 未安装", "MISSING_DEPENDENCY")
        temp_dir = _get_node_temp_dir(node_id)
        model_path = temp_dir / f"model_{uuid.uuid4().hex}.pth"
        scripted_model = torch.jit.script(model)
        scripted_model.save(str(model_path))
        return str(model_path)

    def _store_image_data(self, image: Any, node_id: str = None) -> str:
        """存储图像数据到节点专属目录"""
        if isinstance(image, np.ndarray):
            image = Image.fromarray(image)
        elif not isinstance(image, Image.Image):
            raise ComponentError(f"无法存储图像数据: {type(image)}")
        temp_dir = _get_node_temp_dir(node_id)
        image_path = temp_dir / f"image_{uuid.uuid4().hex}.png"
        image.save(image_path, 'PNG')
        return str(image_path)

    def _store_file_data(self, data: str, node_id: str = None) -> str:
        """存储文件数据到节点专属目录"""
        temp_dir = _get_node_temp_dir(node_id)
        file_path = temp_dir / f"file_{uuid.uuid4().hex}.txt"
        file_path.write_text(str(data), encoding='utf-8')
        return str(file_path)

    # ---------------- 执行包装器 ----------------
    def execute(
            self,
            params: Dict[str, Any],
            inputs: Optional[Dict[str, Any]] = None,
            global_vars: Dict[str, Any] = None,
            node_id: str = None
    ) -> Dict[str, Any]:
        """执行组件，包含错误处理和数据类型转换"""
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
                            validated_inputs[port.name] = self._process_multiple_inputs(
                                port.name, inputs[port.name], port.type
                            )
                        else:
                            validated_inputs[port.name] = self.read_input_data(
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
                raise ComponentError(f"组件输出缺少必需的端口: {missing_outputs}", "OUTPUT_VALIDATION_ERROR")

            # ✅ 关键：传递 node_id 给 store_output_data
            stored_result = {}
            for port in self.outputs:
                if port.name in result:
                    stored_result[port.name] = self.store_output_data(
                        port.name, result[port.name], port.type, node_id=node_id
                    )

            return stored_result

        except ImportError as e:
            self.logger.error(f"环境安装包缺失: {e}")
            raise e

        except Exception as e:
            import traceback
            error_msg = f"组件执行失败: {traceback.format_exc()}"
            raise ComponentError(error_msg, "EXECUTION_ERROR")


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
        else:
            ft = str

        default_val = _parse_default_value(field_def.default, ft)
        fields[field_name] = (ft, default_val)

    model_name = f"{name}Item"
    base_classes = (ModelMixin, BaseModel)
    return create_model(model_name, __base__=base_classes, **fields)
