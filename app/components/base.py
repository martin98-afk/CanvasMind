# -*- coding: utf-8 -*-
import ast
import base64
import io
import json
import os
import pickle
import re
import shutil
import sys
import time
import traceback
import types
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
base_path = Path(__file__).parent.parent / "base.py" if (Path(__file__).parent.parent / "base.py").exists() else Path(__file__).parent.parent.parent / "base.py"
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


# ==================== 组件基础端口、属性设置 ====================
class ConnectionType(str, Enum):
    """连接类型"""
    SINGLE = "单输入"
    MULTIPLE = "多输入"


class PropertyType(str, Enum):
    """属性类型"""
    TEXT = "文本"
    MULTILINE = "多行文本"
    LONGTEXT = "长文本"
    FILE = "文件选择"
    INT = "整数"
    FLOAT = "浮点数"
    RANGE = "范围"
    BOOL = "复选框"
    CHOICE = "下拉框"
    VARIABLE = "动态变量"
    DYNAMICFORM = "动态表单"
    DYNAMICTREE = "动态树"


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
    description: str = ""

    class Config:
        # 允许递归引用
        arbitrary_types_allowed = True


class ArgumentType(str, Enum):
    """参数类型"""
    TEXT = "文本"
    INT = "整数"
    FLOAT = "浮点数"
    BOOL = "布尔值"
    ARRAY = "列表/ARRAY"
    CSV = "csv"
    JSON = "json"
    EXCEL = "excel"
    OBJECT = "内存对象"
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
    description: str = ""

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
class ModelMixin(BaseModel):
    """为输入模型添加 .get() 和 [] 访问方法，兼容字典用法"""

    class Config:
        # 允许模型接收定义之外的字段
        extra = 'allow'

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


class NodeVariable(BaseModel):
    value: Any = None
    update_policy: Optional[str] = "固定"


class GlobalVariableContext(BaseModel):
    """全局变量上下文管理器，支持点号和路径访问"""
    env: ExecutionEnvironment = Field(default_factory=ExecutionEnvironment)
    custom: OrderedDict[str, CustomVariable] = Field(default_factory=OrderedDict)
    node_vars: OrderedDict[str, NodeVariable] = Field(default_factory=OrderedDict)
    input: OrderedDict[str, Any] = Field(default_factory=OrderedDict)  # 每个节点的临时输入，不作为常驻变量

    def __init__(self, **data):
        super().__init__(**data)
        # 初始化默认 Python 环境变量（仅当 metadata 为空时）
        self.deserialize(data)
        if not self.env.metadata:
            self.env.metadata.update(DEFAULT_PYTHON_ENV_VARS)

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def is_variable_name(cls, name: str) -> bool:
        """判断 name 是否为变量名"""
        if isinstance(name, str):
            return name.startswith("custom.") or name.startswith("node_vars.") or name.startswith("env.") or name.startswith("input.")
        else:
            return False

    def set(self, key: str, value: Any) -> None:
        """设置自定义变量"""
        if key not in self.custom:
            self.custom[key] = CustomVariable(value=value)
        else:
            self.custom[key].value = value

    def set_output(self, node_name: str, output_name: str, output_value: Any, policy: str="更新"):
        self.node_vars[f"{node_name}__{output_name}"] = NodeVariable(
            value=output_value, update_policy=policy
        )

    def delete_output(self, node_name: str, output_name: str=None):
        """如果不指定output_name则清除该节点所有节点变量"""
        if output_name is None:
            new_node_vars = OrderedDict()

            for key, var_obj in self.node_vars.items():
                if key.startswith(node_name):
                    continue
                else:
                    # 不需要修改的变量原样保留
                    new_node_vars[key] = var_obj

            # 更新原始变量字典
            self.node_vars = new_node_vars
        else:
            self.node_vars.pop(f"{node_name}__{output_name}", None)

    def is_output_in_node_vars(self, node_name: str, output_name: str):
        return f"{node_name}__{output_name}" in self.node_vars

    def rename_node_vars(self, old_name: str, new_name: str) -> Tuple[List[str], List[str]]:
        """
        重命名节点相关的变量，并返回重命名的键列表。

        Returns:
            tuple: (old_keys_list, new_keys_list)
        """
        # 构造精确前缀，防止误匹配（例如防止 Node1 匹配到 Node11）
        old_prefix = f"{old_name}__"
        new_prefix = f"{new_name}__"

        old_name_list = []
        new_name_list = []

        # 使用 OrderedDict 重新构建以保持顺序，并避免遍历时修改的错误
        new_node_vars = OrderedDict()

        for key, var_obj in self.node_vars.items():
            if key.startswith(old_prefix):
                # 生成新键名（仅替换第一个匹配到的前缀）
                new_key = key.replace(old_prefix, new_prefix, 1)

                # 记录变更
                old_name_list.append(f"node_vars.{key}")
                new_name_list.append(f"node_vars.{new_key}")

                # 存入新字典
                new_node_vars[new_key] = var_obj
            else:
                # 不需要修改的变量原样保留
                new_node_vars[key] = var_obj

        # 更新原始变量字典
        self.node_vars = new_node_vars

        return old_name_list, new_name_list

    def clear_node_vars(self, name: str):
        # 增加对 key 是否存在的检查，防止 KeyError
        if name not in self.node_vars:
            return

        val = self.node_vars[name].value
        if isinstance(val, (list, dict, tuple, set)):
            # 注意：tuple 是不可变的，不能 clear()，建议统一设为 None 或对应的空类型
            if isinstance(val, tuple):
                self.node_vars[name].value = ()
            else:
                val.clear()
        elif isinstance(val, str):
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
        # 临时inputs解析
        inputs_data = data.get("inputs", {})
        for k, v in inputs_data.items():
            self.input[k] = NodeVariable(value=v)

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
        if name in {"env", "custom", "node_vars", "input"}:
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

        elif root == "input":
            if subpath in self.input:
                return self.input[subpath].value
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
            if path in self.input:
                return self.input[path].value
            raise KeyError(f"Key '{path}' not found")


# ======= 构造pydantic输入、参数解析 ========

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
        elif field_def.type == PropertyType.VARIABLE:
            ft = Union[dict, list, str]
        else:
            ft = Any
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

    def __init__(self,
                 node_id: Optional[str] = None,
                 workflow_path: Optional[str] = None,
                 logger_instance=None,
                 component_instance=None,
                 ):
        self.node_id = node_id or "default_node"
        self.workflow_path = workflow_path
        self.logger = logger_instance or logger
        self.result_dir = Path("./result").resolve()
        self.result_dir.mkdir(parents=True, exist_ok=True)
        self.component_instance = component_instance

    # --- 辅助方法：生成唯一文件名 ---
    def _get_save_path(self, output_name: str, prefix: str, extension: str) -> Path:
        """
        生成唯一的存储路径，解决同节点多端口覆盖问题。
        逻辑：./result/{prefix}_{node_id}_{output_name}_{now}.{ext}
        """
        # 1. 处理 {{now}} 逻辑
        filename = output_name
        if "{{now}}" in filename:
            filename = filename.replace("{{now}}", datetime.now().strftime("%Y%m%d%H%M%S"))

        # 2. 清理非法字符
        filename = re.sub(r'[\\/*?:"<>|]', '_', filename)

        # 3. 组合文件名 (前缀 + 节点ID + 端口名)
        # 确保 output_name 本身如果不带扩展名，则补上 extension
        final_filename = f"{prefix}_{self.node_id}_{filename}"
        if not final_filename.lower().endswith(extension.lower()):
            final_filename += extension

        return self.result_dir / final_filename

    # --- 输入数据处理 ---

    def read_input_data(self, input_name: str, input_value: Any, input_type: ArgumentType) -> Any:
        """根据输入类型读取数据，增强鲁棒性"""
        # 1. 统一空值处理
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

        # 2. 路径增强解析逻辑 (针对文件/图像)
        if (input_type.is_file() or input_type.is_image()) and isinstance(input_value, str):
            if not Path(input_value).exists():
                input_value = input_value.replace("\\", "/")
                path_obj = Path(input_value)
                file_name = path_obj.name

                # 尝试多个可能的相对路径进行溯源
                search_candidates = []
                try:
                    # 逻辑1: 基于原路径的 stem 寻找
                    stem_node_id = path_obj.parent.parent.stem
                    if stem_node_id:
                        search_candidates.append(Path(f"../{stem_node_id}/upload") / file_name)
                        search_candidates.append(Path(f"../{stem_node_id}/result") / file_name)
                except:
                    pass

                # 逻辑2: 默认的 inputs 和当前 result 目录
                search_candidates.append(Path("inputs") / file_name)
                search_candidates.append(self.result_dir / file_name)

                # 逻辑3: 基于 workflow_path 溯源
                if self.workflow_path:
                    try:
                        base_path = Path(self.workflow_path).parent.parent.parent
                        search_candidates.append(base_path / input_value)
                    except:
                        pass

                # 执行查找
                for candidate in search_candidates:
                    if candidate.exists():
                        input_value = str(candidate.resolve())
                        break

        # 3. 分类型解析
        try:
            if input_type == ArgumentType.TEXT:
                return str(input_value)
            elif input_type == ArgumentType.INT:
                return int(float(input_value))  # 兼容 "1.0"
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
            elif input_type == ArgumentType.OBJECT:
                return self._fetch_from_memory(input_value)
            else:
                return input_value
        except Exception as e:
            self.logger.error(f"读取输入 '{input_name}'（类型: {input_type}）失败: {e}")
            raise ComponentError(f"读取输入 {input_name} 失败: {str(e)}", "INPUT_READ_ERROR") from e

    def _read_array_data(self, input_name: str, data: Any) -> Union[list, np.ndarray]:
        if isinstance(data, np.ndarray): return data
        if isinstance(data, (list, tuple)):
            try:
                return np.array(data)
            except:
                return list(data)
        if isinstance(data, str):
            try:
                parsed = ast.literal_eval(data)
                if isinstance(parsed, (list, tuple)):
                    return np.array(parsed)
                return parsed
            except:
                return data
        return data

    def _read_csv_data(self, data: Any) -> pd.DataFrame:
        if isinstance(data, (pd.DataFrame, pd.Series)):
            return data

        path = Path(data)
        if path.is_file():
            try:
                # 尝试使用 PyArrow 读取，速度通常快 5-10 倍
                from pyarrow import csv as pa_csv
                return pa_csv.read_csv(str(path)).to_pandas()
            except ImportError:
                self.logger.warning("未检测到 pyarrow，回退至 Pandas 原生读取")
                return pd.read_csv(str(path))
            except Exception as e:
                # 处理格式不兼容等问题（例如某些特殊的编码或分隔符）
                self.logger.warning(f"PyArrow 读取 CSV 失败 ({e})，回退至 Pandas 原生读取")
                return pd.read_csv(str(path))

        raise ComponentError(f"CSV 文件不存在: {path}")

    def _read_json_data(self, data: Any) -> Union[dict, list, str]:
        if data is None or (isinstance(data, str) and not data.strip()): return {}
        if isinstance(data, (dict, list)): return data
        if isinstance(data, (str, Path)):
            path = Path(data)
            if path.is_file():
                with open(path, 'r', encoding='utf-8') as f: return json.load(f)
            try:
                return json.loads(data)
            except:
                try:
                    parsed = ast.literal_eval(data)
                    if isinstance(parsed, (dict, list)): return parsed
                    return data
                except:
                    return data
        return data

    def _read_excel_data(self, data: Any) -> Union[pd.DataFrame, dict]:
        if isinstance(data, pd.DataFrame): return data
        if isinstance(data, (str, Path)) and os.path.exists(data):
            return pd.read_excel(data, sheet_name=None)
        raise ComponentError(f"Excel文件不存在: {data}")

    def _read_sklearn_model(self, data: Any) -> Any:
        if isinstance(data, (str, Path)) and os.path.exists(data):
            with open(data, 'rb') as f: return pickle.load(f)
        raise ComponentError(f"无法读取sklearn模型: {data}")

    def _read_torch_model(self, data: Any) -> Any:
        torch = self._get_torch()
        if isinstance(data, (str, Path)) and os.path.exists(data):
            # 兼容 torch.export 或常规 load
            try:
                with open(data, 'rb') as f:
                    return torch.export.load(f)
            except:
                return torch.load(data)
        raise ComponentError(f"无法读取torch模型: {data}")

    def _read_image_data(self, data: Any) -> Image.Image:
        if isinstance(data, (str, Path)) and os.path.exists(data):
            return Image.open(data)
        if isinstance(data, Image.Image): return data
        if isinstance(data, np.ndarray): return Image.fromarray(data.astype('uint8'))
        if isinstance(data, bytes): return Image.open(io.BytesIO(data))
        raise ComponentError(f"无法读取图像数据: {type(data)}")

    def _read_file_data(self, data: Any) -> Path:
        """返回文件路径，如果是内容则存入临时文件"""
        if isinstance(data, (str, Path)) and os.path.exists(data):
            return str(data)
        dst = self.result_dir / f"input_file_{datetime.now().strftime('%H%M%S')}.bin"
        if isinstance(data, bytes):
            dst.write_bytes(data)
        else:
            dst.write_text(str(data), encoding='utf-8')
        return dst

    def _fetch_from_memory(self, ref_str: str) -> Any:
        """
        从内存中获取对象。
        支持两种格式：
        1. INSTANCE_{node_id}.attr  -> 从驻留的组件实例中取
        2. DATA_{node_id}.attr      -> 从独立的数据容器中取 (当组件不驻留时)
        """
        if not isinstance(ref_str, str) or "." not in ref_str:
            self.logger.warning(f"无效的内存引用格式: {ref_str}")
            return ref_str

        try:
            object_name, attr_name = ref_str.split('.', 1)

            # 解析 node_id
            # 兼容 INSTANCE_xxx 和 DATA_xxx 两种前缀
            if object_name.startswith("INSTANCE_"):
                node_id = object_name.replace("INSTANCE_", "")
            elif object_name.startswith("DATA_"):
                node_id = object_name.replace("DATA_", "")
            else:
                # 尝试通过正则提取最后的ID部分 (备用逻辑)
                node_id = object_name.split("_")[-1]

            module_key = f"dynamic_mod_{node_id}"

            # 1. 检查模块是否存在
            if module_key in sys.modules:
                module = sys.modules[module_key]
                # 2. 获取宿主对象 (Instance 或 DataContainer)
                host_object = getattr(module, object_name, None)

                if host_object:
                    if hasattr(host_object, attr_name):
                        obj = getattr(host_object, attr_name)
                        # self.logger.info(f"成功从内存加载: {ref_str}")
                        return obj
                    else:
                        self.logger.error(f"对象 {object_name} 中不存在属性 {attr_name}")
                else:
                    self.logger.error(f"模块 {module_key} 中未找到对象 {object_name}")
            else:
                self.logger.error(f"内存中未找到模块 {module_key} (可能是节点未运行或数据已丢失)")

            return None

        except Exception as e:
            self.logger.error(f"解析内存对象失败: {e}")
            raise ComponentError(f"解析内存对象失败: {e}")

    def _process_multiple_inputs(self, input_name: str, input_values: List[Any], input_type: ArgumentType) -> List[Any]:
        if input_values is None: return []
        return [self.read_input_data(input_name, val, input_type) for val in input_values]

    # --- 输出数据处理 ---

    def store_output_data(self, output_name: str, output_value: Any, output_type: ArgumentType) -> Any:
        """根据输出类型存储数据"""
        try:
            if output_value is None: return None

            if output_type == ArgumentType.TEXT:
                return str(output_value)
            elif output_type == ArgumentType.INT:
                return int(output_value)
            elif output_type == ArgumentType.FLOAT:
                return float(output_value)
            elif output_type == ArgumentType.ARRAY:
                return output_value
            elif output_type == ArgumentType.CSV:
                return self._store_csv_data(output_value)
            elif output_type == ArgumentType.JSON:
                return self._store_json_data(output_value)
            elif output_type == ArgumentType.EXCEL:
                return self._store_excel_data(output_value, output_name)
            elif output_type == ArgumentType.SKLEARNMODEL:
                return self._store_sklearn_model(output_value, output_name)
            elif output_type == ArgumentType.TORCHMODEL:
                return self._store_torch_model(output_value, output_name)
            elif output_type == ArgumentType.IMAGE:
                return self._store_image_data(output_value, output_name)
            elif output_type == ArgumentType.FILE:
                return self._store_file_data(output_value, output_name)
            elif output_type == ArgumentType.OBJECT:
                return self._store_to_memory(output_name, output_value)
            else:
                return output_value
        except Exception as e:
            self.logger.error(f"存储输出 '{output_name}' 失败: {e}")
            raise ComponentError(f"存储输出 {output_name} 失败: {str(e)}", "OUTPUT_STORE_ERROR")

    def _store_csv_data(self, data: pd.DataFrame) -> Union[pd.DataFrame, str, Path]:
        """存储CSV数据"""
        if isinstance(data, (pd.DataFrame, pd.Series)):
            return data
        elif isinstance(data, (str, Path)):
            if os.path.exists(data):
                try:
                    # 尝试使用 PyArrow 读取，速度通常快 5-10 倍
                    from pyarrow import csv as pa_csv
                    return pa_csv.read_csv(str(data)).to_pandas()
                except ImportError:
                    self.logger.warning("未检测到 pyarrow，回退至 Pandas 原生读取")
                    return pd.read_csv(str(data))
            else:
                # 如果是CSV字符串
                import io
                return pd.read_csv(io.StringIO(data))
        else:
            raise ComponentError(f"无法存储CSV数据: {type(data)}")

    def _store_json_data(self, data: Any) -> Any:
        """存储JSON数据（直接返回）"""
        return data

    def _store_excel_data(self, data: Any, output_name: str) -> str:
        file_path = self._get_save_path(output_name, "data", ".xlsx")
        if isinstance(data, pd.DataFrame):
            data.to_excel(file_path, index=False)
        elif isinstance(data, dict):
            with pd.ExcelWriter(file_path) as writer:
                for sheet, df in data.items():
                    if isinstance(df, pd.DataFrame):
                        df.to_excel(writer, sheet_name=sheet, index=False)
        return str(file_path)

    def _store_sklearn_model(self, model: Any, output_name: str) -> str:
        file_path = self._get_save_path(output_name, "model", ".pkl")
        with open(file_path, 'wb') as f:
            pickle.dump(model, f)
        return str(file_path)

    def _store_torch_model(self, model: Any, output_name: str) -> str:
        torch = self._get_torch()
        file_path = self._get_save_path(output_name, "model", ".pt2")
        try:
            with open(file_path, 'wb') as f:
                torch.export.save(model, f)
        except:
            torch.save(model, str(file_path))
        return str(file_path)

    def _store_image_data(self, image: Any, output_name: str) -> str:
        """存储图像数据，解决同节点多图像端口覆盖问题"""
        if isinstance(image, np.ndarray):
            # 鲁棒性：处理可能存在的浮点图或大位深图
            if image.dtype != np.uint8:
                if image.max() <= 1.0: image = image * 255
                image = image.astype(np.uint8)
            image = Image.fromarray(image)
        elif isinstance(image, str) and os.path.exists(image) and image.endswith((".png", ".jpg", ".jpeg")):
            try:
                image = Image.open(image)
            except:
                self.logger.error(f"无法打开图像文件: {image}")
        # base64字符串
        elif isinstance(image, str) and len(image) % 4 == 0 and len(image) > 200:
            try:
                image = base64.b64decode(image)
                image = Image.open(io.BytesIO(image))
            except:
                pass
        elif isinstance(image, bytes):
            image = Image.open(io.BytesIO(image))

        if not isinstance(image, Image.Image):
            raise ComponentError(f"无效的图像存储类型: {type(image)}")

        file_path = self._get_save_path(output_name, "image", ".png")
        image.save(file_path, 'PNG')
        return str(file_path)

    def _store_file_data(self, data: Any, output_name: str) -> str:
        """通用文件存储，保留原有 {{now}} 逻辑"""
        # 自动推断扩展名
        # 获取输出自带后缀
        if "." in output_name:
            ext = output_name.split(".")[-1]
        else:
            ext = ".dat"
            if isinstance(data, str):
                ext = ".txt"
            elif isinstance(data, bytes):
                ext = ".bin"

        file_path = self._get_save_path(output_name, "file", ext)

        if isinstance(data, (str, Path)) and os.path.exists(data):
            shutil.copy2(data, file_path)
        elif isinstance(data, bytes):
            file_path.write_bytes(data)
        else:
            file_path.write_text(str(data), encoding='utf-8')
        return str(file_path)

    def _store_to_memory(self, output_name: str, value: Any) -> str:
        """
        将对象存入内存。
        策略：
        1. 如果组件开启了驻留(IS_MEMORY_RESIDENT=True)，直接挂载到组件实例上。
        2. 如果组件未驻留，则强制创建一个模块和数据容器来存放此对象。
        """

        module_key = f"dynamic_mod_{self.node_id}"
        instance_name = f"INSTANCE_{self.node_id}"
        data_container_name = f"DATA_{self.node_id}"

        target_obj = None
        target_obj_name = ""

        # 步骤 1: 确保模块存在于 sys.modules
        if module_key in sys.modules:
            module = sys.modules[module_key]
        else:
            # 如果模块不存在（说明组件脚本里没存，或者 is_memory_resident=False）
            # 我们手动创建一个模块作为“数据仓库”
            module = types.ModuleType(module_key)
            sys.modules[module_key] = module
            # self.logger.debug(f"已为数据存储创建独立模块: {module_key}")

        # 步骤 2: 确定挂载目标 (组件实例 OR 独立数据容器)

        # 优先尝试获取现有的组件实例
        if hasattr(module, instance_name):
            target_obj = getattr(module, instance_name)
            target_obj_name = instance_name
        else:
            # 如果没有组件实例，则使用/创建独立的数据容器
            if hasattr(module, data_container_name):
                target_obj = getattr(module, data_container_name)
            else:
                # 创建一个简单的对象作为容器
                target_obj = types.SimpleNamespace()
                setattr(module, data_container_name, target_obj)

            target_obj_name = data_container_name

        # 步骤 3: 挂载数据
        # 属性名加个前缀防止冲突，或者直接用 output_name
        attr_name = f"out_{output_name}"
        setattr(target_obj, attr_name, value)

        # 步骤 4: 返回引用字符串 (格式: 对象名.属性名)
        ref_str = f"{target_obj_name}.{attr_name}"

        self.logger.info(f"对象已存入内存: {ref_str} (模块: {module_key})")
        return ref_str

    def _get_torch(self):
        """懒加载 torch"""
        if not hasattr(self, "_torch_cache"):
            try:
                import torch
                self._torch_cache = torch
            except ImportError:
                raise ComponentError("环境缺失 torch 库", "MISSING_LIB")
        return self._torch_cache


# ========= 组件基类  =========
class BaseComponent(ABC):
    """所有自定义组件的基类。

    继承此类并实现 `run` 方法来定义组件逻辑。组件支持自动参数校验、
    进度推送、人工干预请求以及数据预览。

    Attributes:
        name (str): 组件显示名称。
        category (str): 组件分类（如：数据处理、机器学习）。
        description (str): 组件功能描述。
        inputs (List[PortDefinition]): 输入端口列表。
        outputs (List[PortDefinition]): 输出端口列表。
        properties (Dict[str, PropertyDefinition]): UI 属性配置。
    """
    name: str = ""
    category: str = ""
    description: str = ""
    requirements: str = ""
    inputs: List[PortDefinition] = []
    outputs: List[PortDefinition] = []
    properties: Dict[str, PropertyDefinition] = {}
    logger: logger = logger
    global_variable: GlobalVariableContext = GlobalVariableContext()

    @abstractmethod
    def run(self, params: BaseModel, inputs: BaseModel = None) -> Dict[str, Any]:
        """"组件的核心执行逻辑。

        Args:
            params: 经过校验的属性参数对象。可以通过 `params.key` 或 `params['key']` 访问。
            inputs: 经过校验的输入端口数据对象。可以通过 `inputs.port_name` 访问。

        Returns:
            Dict[str, Any]: 字典格式的输出结果，Key 必须与 `outputs` 定义的端口名一致。

        Example:
            >>> def run(self, params, inputs):
            >>>     data = inputs.input_data
            >>>     threshold = params.threshold
            >>>     return {"output_data": data[data > threshold]}
        """
        pass

    @classmethod
    def get_inputs(cls) -> List[Tuple[str, str, str, ArgumentType]]:
        """返回输入端口定义：[('port_name', 'Port Label')]"""
        return [(port.name, port.label, port.connection, port.type, port.description) for port in cls.inputs]

    @classmethod
    def get_outputs(cls) -> List[Tuple[str, str, ArgumentType]]:
        """返回输出端口定义：[('port_name', 'Port Label')]"""
        return [(port.name, port.label, port.type, port.description) for port in cls.outputs]

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
                # 动态创建 Literal 类型
                field_type = str
                choices = prop_def.choices
                # 默认值逻辑：优先用 default，没定义则用第一个选项，再没有则为空字符串
                if prop_def.default is not None and prop_def.default != "":
                    default_val = prop_def.default
                elif choices:
                    default_val = choices[0]
                else:
                    default_val = ""
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
            elif prop_def.type == PropertyType.DYNAMICTREE:
                field_type = Dict[str, Any]
                # 使用 Field 并指定默认工厂为 dict
                fields[prop_name] = (field_type, Field(default_factory=dict))
                default_val = {}
            elif prop_def.type == PropertyType.VARIABLE:
                field_type = Any
                default_val = ""
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
    def emit_message(self, method: str, params: Dict[str, Any], level=MessageLevel.INFO, extra={}):
        """发送自定义协议消息至 UI 端。

        Args:
            method: 方法标识符，如 'stream.output', 'global_variable.clear'
            params: 参数负载字典
            level: 消息严重等级
        """
        msg = ComponentMessage(
            method=method,
            params=params,
            extra=extra
        )
        # 通过 stdout 发送加密/编码后的 JSON，防止业务日志干扰
        print(f"{PROGRESS_MARKER}{msg.json()}", flush=True)

    def emit_interactive_message(
            self, method: str, params: Dict[str, Any], level=MessageLevel.INFO, extra={}) -> Any:
        """在组件执行过程中请求人工干预。此方法会阻塞线程直到用户提交。

        Args:
            title (str): 弹窗标题。
            message (str): 给用户的提示信息。
            schema (Dict[str, Any], optional): 动态表单定义，用于收集用户输入，样例："text": {"label": "生成文本确认", "default": "测试文本"}。

        Returns:
            Any: 用户在 UI 界面提交的数据。

        Raises:
            ComponentError: 人工干预超时或读取结果失败。
        """
        request_id = str(uuid.uuid4())
        # 获取当前运行目录，这个目录在 execute 脚本中会被设置到环境变量
        run_dir = Path(".").resolve() / "jrpc_response" / self.node_id
        response_path = run_dir / f"response_{request_id}.pkl"

        # 1. 发送指令给 UI (通过日志流)
        emit_messages = {
            "request_id": request_id,
            "response_file": str(response_path),
        }
        emit_messages.update(params)
        self.emit_message(method, emit_messages, level=level, extra=extra)

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
        self.emit_message("ui.progress", {"value": percent, "text": status_text})

    def send_preview(self, data_type: str, payload: Any):
        """快捷方式：发送数据预览"""
        self.emit_message("data.preview", {"type": data_type, "data": payload})

    # ---------------- 变量解析逻辑 ----------------
    def _resolve_value(self, key, value: Any, prop_type: PropertyType) -> Any:
        """解析值：支持普通变量解析和 DYNAMICFORM 内部变量解析"""

        # 1. 处理 DYNAMICFORM (数据结构为 List[Dict])
        if prop_type == PropertyType.DYNAMICFORM and isinstance(value, list):
            resolved_list = []
            for item in value:
                if isinstance(item, dict):
                    schema = self.properties.get(key).schema
                    new_item = {
                        k: self._resolve_value(k, v, schema.get(k).type)
                        for k, v in item.items()
                    }
                    resolved_list.append(new_item)
                else:
                    resolved_list.append(item)
            return resolved_list

        # 2. 处理普通变量引用 (例如 "custom.my_var" 或 "node_vars.node1__out")
        if isinstance(value, str) and GlobalVariableContext.is_variable_name(value):
            try:
                # 获取原始值
                resolved = self.global_variable.get(value)
                # 3. 根据定义的属性类型进行二次强制转换（增强鲁棒性）
                if prop_type == PropertyType.INT:
                    # 先转 float 再转 int，处理变量里存了 "1.0" 的情况
                    return int(float(str(resolved).strip()))
                elif prop_type in [PropertyType.FLOAT, PropertyType.RANGE]:
                    return float(str(resolved).strip())
                elif prop_type == PropertyType.BOOL:
                    if isinstance(resolved, str):
                        return resolved.lower() in ("true", "1", "yes", "on")
                    return bool(resolved)
                elif prop_type == PropertyType.DYNAMICTREE:
                    return json.loads(resolved) if isinstance(resolved, str) else resolved
                elif prop_type == PropertyType.VARIABLE:
                    # VARIABLE 类型特殊，通常返回 [变量名, 实际值]
                    return [value, resolved]
                else:
                    # 文本或其他类型直接返回解析后的对象
                    return resolved
            except (KeyError, ValueError, TypeError) as e:
                self.logger.warning(f"变量 {value} 解析失败，将使用原值。错误: {e}")
                return value

        return value

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
        self.data_handler = DataHandler(
            node_id=node_id, workflow_path=workflow_path, logger_instance=self.logger, component_instance=self
        )
        try:
            if global_vars is not None:
                self.global_variable.deserialize(global_vars)
            # 在校验前解析 params 中的动态变量引用
            # 遍历 params，根据定义尝试将字符串转为数值
            for key, val in params.items():
                if key in self.properties:
                    params[key] = self._resolve_value(key, val, self.properties[key].type)
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