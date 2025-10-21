# -*- coding: utf-8 -*-
import re
from typing import Any, Dict, Optional
from asteval import Interpreter
from datetime import datetime
import json


class ExpressionEngine:
    """
    安全的表达式引擎，支持：
    - 全局变量自动注入（env / custom / node_vars）
    - {{ ... }} 模板语法
    - 自定义安全函数
    - 沙箱执行（无文件/网络访问）
    """

    def __init__(self, global_vars_context=None):
        """
        :param global_vars_context: GlobalVariableContext 实例
        """
        self.interp = Interpreter(max_time=2.0)  # 2秒超时防止死循环

        # 注入全局变量（展平为字典）
        if global_vars_context is not None:
            flat_vars = self._flatten_global_vars(global_vars_context)
            self.interp.symtable.update(flat_vars)

        # 注册安全函数
        self._register_functions()

    def _flatten_global_vars(self, ctx) -> Dict[str, Any]:
        """将 GlobalVariableContext 展平为字典，带作用域前缀"""
        flat = {}

        # 环境变量 -> env_xxx
        env_vars = ctx.env.get_all_env_vars()
        for k, v in env_vars.items():
            flat[f"env_{k}"] = v

        # 自定义变量 -> custom_xxx
        for k, var_obj in ctx.custom.items():
            flat[f"custom_{k}"] = var_obj.value

        # 节点输出变量 -> node_xxx
        for k, v in ctx.node_vars.items():
            flat[f"node_vars_{k}"] = v

        return flat

    def _register_functions(self):
        """注册安全函数到解释器"""
        safe_functions = {
            # 类型转换
            'str': str,
            'int': int,
            'float': float,
            'bool': bool,
            'len': len,

            # JSON 处理
            'json_loads': json.loads,
            'json_dumps': json.dumps,

            # 时间函数
            'now': lambda: datetime.now().isoformat(),
            'timestamp': lambda: int(datetime.now().timestamp()),

            # 字符串处理
            'upper': lambda s: s.upper() if isinstance(s, str) else s,
            'lower': lambda s: s.lower() if isinstance(s, str) else s,
            'strip': lambda s: s.strip() if isinstance(s, str) else s,

            # 数学函数（asteval 已内置部分，这里显式暴露）
            'abs': abs,
            'round': round,
            'min': min,
            'max': max,
        }
        self.interp.symtable.update(safe_functions)

    def evaluate(self, expr: str) -> Any:
        """
        计算单个表达式
        :param expr: 表达式字符串，如 "env_user_id" 或 "custom_threshold * 2"
        :return: 计算结果或错误字符串
        """
        if not expr or not isinstance(expr, str):
            return expr

        try:
            result = self.interp.eval(expr)
            # asteval 可能返回 numpy 类型，转为 Python 原生类型
            if hasattr(result, 'item'):
                return result.item()
            return result
        except Exception as e:
            return f"[ExprError: {str(e)}]"

    def is_pure_expression_block(self, value: str) -> bool:
        """
        判断是否为纯表达式块：整个字符串就是一个 $...$，无其他内容
        示例:
            "$input.age > 18$" → True
            "路径: $file$"      → False
            "$a$ and $b$"       → False（多个表达式）
        """
        if not isinstance(value, str):
            return False
        # 必须以 $ 开头，以 $ 结尾，且只有一对 $
        stripped = value.strip()
        if not (stripped.startswith('$') and stripped.endswith('$')):
            return False
        # 检查中间是否还有 $
        inner = stripped[1:-1]
        return '$' not in inner

    def is_template_expression(self, value: str) -> bool:
        """判断是否包含任何 $...$ 表达式"""
        return isinstance(value, str) and '$' in value and re.search(r'\$[^$]*\$', value) is not None

    def evaluate_expression_block(self, expr_block: str, local_vars: Optional[Dict[str, Any]] = None) -> Any:
        """
        评估纯表达式块（如 "$input.age > 18$"），返回原始 Python 值（bool/int/str 等）
        :param expr_block: 完整的表达式块字符串，如 "$input.age > 18$"
        :param local_vars: 局部变量
        :return: 表达式计算结果（原始类型）
        """
        if not self.is_pure_expression_block(expr_block):
            raise ValueError("Not a pure expression block")

        # 提取内部表达式
        inner_expr = expr_block.strip()[1:-1].strip()

        # 展平点语法（如 input.age → input_age）
        safe_expr = re.sub(r'\b(env|custom|node_vars|input)\.(.*?)', r'\1_\2', inner_expr)
        # 将空格和 - 转换为下划线
        # safe_expr = re.sub(r'\s+|-', '_', safe_expr)
        # 合并符号表
        temp_symtable = dict(self.interp.symtable)
        if local_vars:
            temp_symtable.update(local_vars)

        try:
            interp_temp = Interpreter(max_time=2.0)
            interp_temp.symtable.update(temp_symtable)
            result = interp_temp.eval(safe_expr)
            if hasattr(result, 'item'):
                result = result.item()
            return result
        except Exception as e:
            # 在条件判断中，错误表达式应视为 False
            return f"[ExprError: {str(e)}]"

    def evaluate_template(self, template: str, local_vars: Optional[Dict[str, Any]] = None) -> str:
        """
        仅处理混合模板（非纯表达式块），返回字符串
        """
        if not self.is_template_expression(template):
            return template

        # 如果是纯表达式块，应使用 evaluate_expression_block，这里 fallback 为字符串
        if self.is_pure_expression_block(template):
            result = self.evaluate_expression_block(template, local_vars)
            return str(result) if result is not None else ""

        # 否则处理混合模板
        temp_symtable = dict(self.interp.symtable)
        if local_vars:
            temp_symtable.update(local_vars)

        def replace_match(match):
            expr = match.group(1).strip()
            if not expr:
                return ""
            safe_expr = re.sub(r'\b(env|custom|node_vars|input)\.([a-zA-Z_][a-zA-Z0-9_]*)', r'\1_\2', expr)
            try:
                interp_temp = Interpreter(max_time=2.0)
                interp_temp.symtable.update(temp_symtable)
                result = interp_temp.eval(safe_expr)
                if hasattr(result, 'item'):
                    result = result.item()
                return str(result) if result is not None else ""
            except Exception as e:
                return f"[ExprError: {str(e)}]"

        return re.sub(r'\$([^$]*)\$', replace_match, template)

    def get_available_variables(self) -> Dict[str, Any]:
        """获取所有可用变量（用于 UI 提示）"""
        return {
            k: v for k, v in self.interp.symtable.items()
            if not callable(v) and not k.startswith('_')
        }