# -*- coding: utf-8 -*-
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
ConnectionType = base_module.ConnectionType


class ConditionalNode(BaseComponent):
    name = "条件判断"
    category = "测试组件"
    description = "根据条件表达式决定执行哪个分支"

    inputs = [
        PortDefinition(name="condition_input", label="条件输入", type=ArgumentType.TEXT),
        PortDefinition(name="true_data", label="真分支数据", type=ArgumentType.TEXT),
        PortDefinition(name="false_data", label="假分支数据", type=ArgumentType.TEXT)
    ]

    outputs = [
        PortDefinition(name="true_output", label="真分支输出", type=ArgumentType.TEXT),
        PortDefinition(name="false_output", label="假分支输出", type=ArgumentType.TEXT),
        PortDefinition(name="condition_result", label="条件结果", type=ArgumentType.BOOL)
    ]

    properties = {
        "condition_expression": PropertyDefinition(
            type=PropertyType.TEXT,
            default="data['value'] > 0",
            label="条件表达式"
        ),
        "evaluation_mode": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="python",
            choices=["python", "simple"],
            label="评估模式"
        )
    }

    def run(self, params, inputs=None):
        condition_expr = params.condition_expression
        eval_mode = params.evaluation_mode

        # 准备评估上下文
        context = {"data": {}}
        if inputs:
            context["data"] = inputs
            # 也直接提供输入值
            for key, value in inputs.items():
                context[key] = value

        try:
            if eval_mode == "simple":
                # 简单模式：直接比较
                result = self._evaluate_simple_condition(condition_expr, context)
            else:
                # Python 模式：使用 eval
                result = self._evaluate_python_condition(condition_expr, context)

            # 根据结果选择输出
            if result:
                true_output = inputs.true_data if inputs else "True branch"
                false_output = None
            else:
                true_output = None
                false_output = inputs.false_data if inputs else "False branch"

            return {
                "true_output": true_output,
                "false_output": false_output,
                "condition_result": result
            }

        except Exception as e:
            return {
                "true_output": None,
                "false_output": None,
                "condition_result": False,
                "error": f"条件评估错误: {str(e)}"
            }

    def _evaluate_python_condition(self, expr, context):
        """使用 Python eval 评估条件"""
        # 安全的 eval - 限制内置函数
        safe_globals = {
            "__builtins__": {
                "len": len,
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "abs": abs,
                "max": max,
                "min": min,
                "sum": sum,
                "True": True,
                "False": False,
                "None": None
            }
        }
        safe_locals = context
        return bool(eval(expr, safe_globals, safe_locals))

    def _evaluate_simple_condition(self, expr, context):
        """简单条件评估（支持基本比较）"""
        # 解析简单表达式如 "value > 10" 或 "status == 'active'"
        parts = expr.strip().split()
        if len(parts) != 3:
            raise ValueError("简单条件格式: field operator value")

        field, operator, value_str = parts

        # 获取字段值
        if field in context:
            field_value = context[field]
        elif "data" in context and field in context["data"]:
            field_value = context["data"][field]
        else:
            raise ValueError(f"字段 '{field}' 不存在")

        # 转换值类型
        try:
            if value_str.lower() in ["true", "false"]:
                value = value_str.lower() == "true"
            elif value_str.isdigit():
                value = int(value_str)
            else:
                try:
                    value = float(value_str)
                except ValueError:
                    value = value_str.strip("'\"")
        except:
            value = value_str.strip("'\"")

        # 执行比较
        if operator == "==":
            return field_value == value
        elif operator == "!=":
            return field_value != value
        elif operator == ">":
            return field_value > value
        elif operator == "<":
            return field_value < value
        elif operator == ">=":
            return field_value >= value
        elif operator == "<=":
            return field_value <= value
        else:
            raise ValueError(f"不支持的操作符: {operator}")
