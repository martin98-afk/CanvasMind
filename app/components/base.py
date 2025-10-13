# -*- coding: utf-8 -*-
import json
import os
import pickle
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Tuple, Type, Union
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from enum import Enum

import numpy as np
import pandas as pd
from PIL import Image
from loguru import logger
from pydantic import create_model


DEFAULT_PYTHON_ENV_VARS = {
    "PYTHONPATH": ".",
    "PYTHONUNBUFFERED": "1",
    "PYTHONIOENCODING": "utf-8",
    "PYTHONWARNINGS": "ignore",
    "TZ": "Asia/Shanghai",
    "LANG": "en_US.UTF-8",
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "CUDA_VISIBLE_DEVICES": "0",
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


class VariableScope(str, Enum):
    GLOBAL = "global"
    CANVAS = "canvas"
    SESSION = "session"


class ExecutionEnvironment(BaseModel):
    # 预定义字段（保留类型提示）
    user_id: Optional[str] = None
    canvas_id: Optional[str] = None
    session_id: Optional[str] = None
    run_id: Optional[str] = None

    # 所有动态环境变量存储在这里
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def get_all_env_vars(self) -> Dict[str, Any]:
        """获取所有环境变量（预定义 + 动态）"""
        result = self.metadata.copy()
        # 添加预定义字段（非 None 值）
        for field in ["user_id", "canvas_id", "session_id", "run_id"]:
            val = getattr(self, field)
            if val is not None:
                result[field] = val
        return result

    def set_env_var(self, key: str, value: Any):
        """设置环境变量"""
        if key in ["user_id", "canvas_id", "session_id", "run_id"]:
            setattr(self, key, value)
        else:
            self.metadata[key] = value

    def delete_env_var(self, key: str):
        """删除环境变量"""
        if key in ["user_id", "canvas_id", "session_id", "run_id"]:
            setattr(self, key, None)
        else:
            self.metadata.pop(key, None)


class CustomVariable(BaseModel):
    value: Any = None
    description: Optional[str] = None
    scope: VariableScope = VariableScope.GLOBAL
    read_only: bool = False


class GlobalVariableContext(BaseModel):
    env: ExecutionEnvironment = Field(default_factory=ExecutionEnvironment)
    custom: Dict[str, CustomVariable] = Field(default_factory=dict)
    node_vars: Dict[str, Any] = Field(default_factory=dict)

    def __init__(self, **data):
        super().__init__(**data)
        # 初始化默认 Python 环境变量（仅当 metadata 为空时）
        if not self.env.metadata:
            self.env.metadata.update(DEFAULT_PYTHON_ENV_VARS)

    class Config:
        # 允许任意类型（因为 value 可能是 list/dict 等）
        arbitrary_types_allowed = True

    def get(self, key: str, default=None) -> Any:
        """兼容旧 dict 用法：global_vars.get('key')"""
        if key in self.custom:
            return self.custom[key].value
        return default

    def set(self, key: str, value: Any) -> None:
        """设置自定义变量（忽略只读检查，由业务层控制）"""
        if key not in self.custom:
            self.custom[key] = CustomVariable(value=value)
        else:
            self.custom[key].value = value

    def set_output(self, node_id: str, output_name: str, output_value: Any):
        self.node_vars[f"{node_id} {output_name}"] = output_value

    def to_dict(self) -> Dict[str, Any]:
        """兼容旧逻辑：返回扁平字典（仅 custom 变量）"""
        return {k: v.value for k, v in self.custom.items()} | self.env.get_all_env_vars() | self.node_vars


class ConnectionType(str, Enum):
    """连接类型"""
    SINGLE = "单输入"
    MULTIPLE = "多输入"


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
        if display_data is None or len(display_data) == 0:
            return display_data
        try:
            if self.is_file() and len(display_data) > 0:
                # FILE类型：显示文件路径选择
                display_data = {
                    "file_name": os.path.basename(display_data),
                    "file_type": self.value,
                    "file_path": display_data
                }
            elif self == ArgumentType.JSON and isinstance(display_data, str):
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
        except:
            logger.error(f"{self.value}序列化错误：{display_data}")

        return display_data


class PortDefinition(BaseModel):
    """端口定义"""
    name: str
    label: str
    type: ArgumentType = ArgumentType.TEXT
    connection: ConnectionType = ConnectionType.SINGLE


class InputModelMixin:
    """为输入模型添加 .get() 方法，兼容字典用法"""

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

    # 可选：支持 in 操作（如 "image" in inputs）
    def __contains__(self, key: str) -> bool:
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
        base_classes = (InputModelMixin, BaseModel)
        return create_model(model_name, __base__=base_classes, **fields)

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
        fields: Dict[str, tuple] = {"global_variable": (Dict, Field(default={}))}

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
        if len(data) == 0:
            return {}
        if isinstance(data, dict):
            return data
        elif isinstance(data, list):
            return data
        elif isinstance(data, str):
            if os.path.exists(data):
                with open(data, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                self.logger.info(data)
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
            validated_params = params_model(**params)
            input_model_cls = self.get_input_model()
            # 验证并读取输入数据
            validated_inputs = {}
            if inputs:
                for port in self.inputs:
                    if port.name in inputs:
                        if (port.connection == ConnectionType.SINGLE or
                                (port.connection == ConnectionType.MULTIPLE and not isinstance(inputs[port.name],
                                                                                               list))):
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

            validated_inputs = input_model_cls(**validated_inputs)
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