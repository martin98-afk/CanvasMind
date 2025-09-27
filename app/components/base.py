"""
@author: mading
@license: (C) Copyright: LUCULENT Corporation Limited.
@contact: mading@luculent.net
@file: base.py
@time: 2025/9/26 15:02
@desc: 
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional, List, Tuple, Type

from loguru import logger
from pydantic import BaseModel, Field, create_model


class ArgumentType(str, Enum):
    TEXT = "text"
    TEXT_AREA = "text_area"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    CHOICE = "choice"
    FILE = "file"
    FOLDER = "folder"
    CSV = "csv"

    # 验证是否是文件类型
    def is_file(self):
        return self == ArgumentType.FILE or self == ArgumentType.FOLDER


class PropertyDefinition(BaseModel):
    """属性定义"""
    type: ArgumentType = ArgumentType.TEXT
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