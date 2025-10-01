# -*- coding: utf-8 -*-
import os
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional, List, Tuple, Type

import pandas as pd
from loguru import logger
from pydantic import BaseModel, Field, create_model


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
ArgumentType = base_module.ArgumentType\n\n\n"""


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

    @abstractmethod
    def run(self, params: Dict[str, Any], inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        pass

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
            if prop_def.type == ArgumentType.INT:
                field_type = int
                default = prop_def.default if prop_def.default != "" else 0
            elif prop_def.type == ArgumentType.FLOAT:
                field_type = float
                default = prop_def.default if prop_def.default != "" else 0.0
            elif prop_def.type == ArgumentType.BOOL:
                field_type = bool
                default = prop_def.default if prop_def.default != "" else False
            else:
                field_type = str
                default = prop_def.default if prop_def.default != "" else ""

            fields[prop_name] = (field_type, default)

        return create_model(f"{cls.__name__}Params", **fields)