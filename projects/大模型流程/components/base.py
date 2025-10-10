# -*- coding: utf-8 -*-
import os
import json
import pickle
import re
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional, List, Tuple, Type, Union, Literal
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
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
    TEXT = "文本"
    LONGTEXT = "长文本"
    INT = "整数"
    FLOAT = "浮点数"
    RANGE = "范围"
    BOOL = "复选框"
    CHOICE = "下拉框"
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

    def serialize(self, display_data):
        if display_data is None:
            return display_data
        if self.is_file() and len(display_data) > 0:
            # FILE类型：显示文件路径选择
            display_data = {
                "file_name": os.path.basename(display_data),
                "file_type": self.value,
                "file_path": display_data
            }
        elif self == ArgumentType.JSON and len(display_data) > 0:
            display_data = json.loads(display_data)
        elif self.is_number():
            display_data = float(display_data)
        elif self.is_bool():
            display_data = bool(display_data)
        elif self.is_array() and isinstance(display_data, str):
            display_data = np.array(eval(display_data))
        elif self.is_array() and isinstance(display_data, list):
            display_data = np.array(display_data)
        elif self.is_image():
            display_data = Image.open(display_data)

        return display_data


class PortDefinition(BaseModel):
    """端口定义"""
    name: str
    label: str
    type: ArgumentType = ArgumentType.TEXT
    connection: Literal["single", "multi"] = "single"


class ComponentError(Exception):
    """组件执行错误"""
    def __init__(self, message: str, error_code: str = "COMPONENT_ERROR"):
        self.message = message
        self.error_code = error_code
        super().__init__(message)


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
    def get_inputs(cls) -> List[Tuple[str, str, str]]:
        """返回输入端口定义：[('port_name', 'Port Label')]"""
        return [(port.name, port.label, port.connection) for port in cls.inputs]

    @classmethod
    def get_outputs(cls) -> List[Tuple[str, str]]:
        """返回输出端口定义：[('port_name', 'Port Label')]"""
        return [(port.name, port.label) for port in cls.outputs]

    # @classmethod
    # def get_properties(cls) -> Dict[str, Dict[str, Any]]:
    #     """返回属性定义"""
    #     return {
    #         prop_name: prop_def.dict(exclude_unset=True)
    #         for prop_name, prop_def in cls.properties.items()
    #     }

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

        return create_model(f"{cls.__name__}Params", **fields)

    # ---------------- 输入数据读取 ----------------
    def read_input_data(self, input_name: str, input_value: Any, input_type: ArgumentType) -> Any:
        """根据输入类型读取数据"""
        try:
            if input_type == ArgumentType.TEXT:
                return str(input_value) if input_value is not None else ""
            elif input_type == ArgumentType.INT:
                return int(input_value) if input_value is not None else 0
            elif input_type == ArgumentType.FLOAT:
                return float(input_value) if input_value is not None else 0.0
            elif input_type == ArgumentType.ARRAY and isinstance(input_value, (list, tuple)):
                return np.array(input_value) if input_value is not None else 0.0
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
            raise ComponentError(f"读取输入 {input_name} 失败: {str(e)}", "INPUT_READ_ERROR")

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

    def _read_json_data(self, data: Union[str, dict, Path]) -> Union[dict, list]:
        """读取JSON数据"""
        if isinstance(data, dict):
            return data
        elif isinstance(data, list):
            return data
        elif isinstance(data, str):
            if os.path.exists(data):
                with open(data, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                # 如果是JSON字符串
                return json.loads(re.sub(r"'", '"', data))
        elif isinstance(data, Path):
            with open(data, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            raise ComponentError(f"无法读取JSON数据: {type(data)}")

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
        try:
            import torch
        except:
            pass
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
        """读取文件数据"""
        if isinstance(data, (str, Path)) and os.path.exists(data):
            try:
                with open(data, 'r', encoding='utf-8') as f:
                    return f.read()
            except UnicodeDecodeError as e:
                try:
                    with open(data, 'r', encoding='gbk') as f:
                        return f.read()
                except UnicodeDecodeError as e:
                    with open(data, 'rb') as f:
                        return f.read().decode('utf-8', 'ignore')
            except Exception as e:
                raise e
        else:
            raise ComponentError(f"无法读取文件数据: {data}")

    # ---------------- 输出数据存储 ----------------
    def store_output_data(self, output_name: str, output_value: Any, output_type: ArgumentType) -> Any:
        """根据输出类型存储数据"""
        try:
            if output_type == ArgumentType.TEXT:
                return str(output_value) if output_value is not None else ""
            elif output_type == ArgumentType.INT:
                return int(output_value) if output_value is not None else 0
            elif output_type == ArgumentType.FLOAT:
                return float(output_value) if output_value is not None else 0.0
            elif output_type == ArgumentType.ARRAY and isinstance(output_value, np.ndarray):
                return output_value.tolist() if output_value is not None else np.zeros(0)
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
                return self._store_file_data(output_value)
            else:
                return output_value
        except Exception as e:
            raise ComponentError(f"存储输出 {output_name} 失败: {str(e)}", "OUTPUT_STORE_ERROR")

    def _store_csv_data(self, data: pd.DataFrame) -> str:
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
        """存储JSON数据"""
        return data

    def _store_excel_data(self, data: pd.DataFrame) -> str:
        """存储Excel数据"""
        import io
        if isinstance(data, pd.DataFrame):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                data.to_excel(writer, index=False)
            return output.getvalue()
        elif isinstance(data, (str, Path)):
            if os.path.exists(data):
                return pd.read_excel(data)
            else:
                return pd.read_excel(io.StringIO(data))
        else:
            raise ComponentError(f"无法存储Excel数据: {type(data)}")

    def _store_sklearn_model(self, model: Any) -> str:
        """存储sklearn模型"""
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pkl') as tmp:
            with open(tmp.name, 'wb') as f:
                pickle.dump(model, f)
            return tmp.name

    def _store_torch_model(self, model: Any) -> str:
        """存储torch模型"""
        try:
            import torch
        except:
            pass
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pth') as tmp:
            # 使用torch.jit.script进行模型序列化
            scripted_model = torch.jit.script(model)
            scripted_model.save(tmp.name)
            return tmp.name

    def _store_image_data(self, image: Any) -> str:
        """存储图像数据"""
        # 如果是ndarray图像
        if isinstance(image, np.ndarray):
            image = Image.fromarray(image)
        elif isinstance(image, Image.Image):
            pass
        else:
            raise ComponentError(f"无法存储图像数据: {type(image)}")
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
            image.save(tmp.name, 'PNG')
            return tmp.name

    def _store_file_data(self, data: str) -> str:
        """存储文件数据"""
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8', suffix='.txt') as tmp:
            tmp.write(str(data))
            return tmp.name

    # ---------------- 执行包装器 ----------------
    def execute(self, params: Dict[str, Any], inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """执行组件，包含错误处理和数据类型转换"""
        try:
            # 验证参数
            params_model = self.get_params_model()
            validated_params = params_model(**params).dict()
            # 验证并读取输入数据
            validated_inputs = {}
            if inputs:
                for port in self.inputs:
                    if port.name in inputs:
                        if port.connection == "single":
                            validated_inputs[port.name] = self.read_input_data(
                                port.name, inputs[port.name], port.type
                            )
                        else:
                            validated_inputs[port.name] = [
                                self.read_input_data(port.name, input_data, port.type)
                                for input_data in inputs[port.name]
                            ]
                    if f"{port.name}_column_select" in inputs:
                        validated_inputs[port.name] = validated_inputs[port.name][inputs[f"{port.name}_column_select"]]

            # 执行组件逻辑
            result = self.run(validated_params, validated_inputs)

            # 验证输出
            if not self.validate_outputs(result):
                missing_outputs = [port.name for port in self.outputs if port.name not in result]
                raise ComponentError(f"组件输出缺少必需的端口: {missing_outputs}", "OUTPUT_VALIDATION_ERROR")

            # 存储输出数据
            stored_result = {}
            for port in self.outputs:
                if port.name in result:
                    stored_result[port.name] = self.store_output_data(
                        port.name, result[port.name], port.type
                    )

            return stored_result

        except ImportError as e:
            self.logger.error(f"环境安装包缺失: {e}")
            raise e

        except Exception as e:
            import traceback
            # 捕获其他错误并包装为组件错误
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

    return create_model(f"{name}Item", **fields)