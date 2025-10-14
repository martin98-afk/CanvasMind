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
            flat[f"node_{k}"] = v

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

    def is_template_expression(self, value: str) -> bool:
        """
        判断是否为模板表达式（包含 {{...}}）
        """
        return isinstance(value, str) and '{{' in value and '}}' in value

    def evaluate_template(self, template: str) -> str:
        """
        处理模板字符串，替换 {{ expression }} 为实际值
        例如: "Hello {{ env_user_id }}!" → "Hello alice!"
        """
        if not self.is_template_expression(template):
            return template

        def replace_match(match):
            expr = match.group(1).strip()
            if not expr:
                return ""
            result = self.evaluate(expr)
            return str(result) if result is not None else ""

        # 替换所有 {{ ... }} 表达式
        return re.sub(r'\{\{\s*(.*?)\s*\}\}', replace_match, template)

    def get_available_variables(self) -> Dict[str, Any]:
        """获取所有可用变量（用于 UI 提示）"""
        return {
            k: v for k, v in self.interp.symtable.items()
            if not callable(v) and not k.startswith('_')
        }