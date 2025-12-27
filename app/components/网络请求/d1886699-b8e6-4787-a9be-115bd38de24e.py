# -*- coding: utf-8 -*-
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
ConnectionType = base_module.ConnectionType


class JsonSchemaValidatorComponent(BaseComponent):
    name = "JSON Schema 校验"
    category = "网络请求"
    description = "对输入的 JSON 数据进行 Schema 校验，验证其结构与格式是否符合预定义规则"
    requirements = ""
    inputs = [
        PortDefinition(name="json_data", label="输入 JSON 数据", type=ArgumentType.JSON, connection=ConnectionType.SINGLE),
        PortDefinition(name="schema", label="校验 Schema", type=ArgumentType.JSON, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="valid", label="校验结果", type=ArgumentType.BOOL),
        PortDefinition(name="errors", label="校验错误信息", type=ArgumentType.ARRAY),
        PortDefinition(name="validated_data", label="通过校验的数据", type=ArgumentType.JSON),
    ]

    properties = {
        "strict_mode": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="严格模式",
        ),
        "allow_unknown": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="允许未知字段",
        ),
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import json
        from jsonschema import validate, ValidationError

        json_data = inputs.json_data
        schema = inputs.schema
        strict_mode = params.strict_mode
        allow_unknown = params.allow_unknown

        result = {
            "valid": True,
            "errors": [],
            "validated_data": None
        }

        try:
            # 验证数据是否为合法 JSON
            if not isinstance(json_data, dict):
                raise ValueError("输入数据必须是 JSON 对象")

            # 校验逻辑
            validate(
                instance=json_data,
                schema=schema,
                format_checker=None,
                cls=None,
                format=None,
                _required=True,
                _unknown=not allow_unknown if allow_unknown is not None else True
            )

            result["valid"] = True
            result["validated_data"] = json_data

        except ValidationError as e:
            result["valid"] = False
            result["errors"] = [str(e)]
            if strict_mode:
                self.logger.error(f"JSON 校验失败: {e}")
                raise
            else:
                self.logger.warning(f"JSON 校验失败（非严格模式）: {e}")

        except Exception as e:
            result["valid"] = False
            result["errors"] = [f"数据解析或校验异常: {str(e)}"]
            self.logger.error(f"校验过程异常: {e}")
            raise

        return result


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = JsonSchemaValidatorComponent()
    result = model.debug(
        params={
            "strict_mode": "True",
            "allow_unknown": "False"
        },
        inputs={
            "json_data": {"name": "张三", "age": 25, "email": "zhangsan@example.com"},
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "age": {"type": "integer", "minimum": 0},
                    "email": {"type": "string", "format": "email"}
                },
                "required": ["name", "age"]
            }
        },
        global_vars={},
        node_id="test_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)