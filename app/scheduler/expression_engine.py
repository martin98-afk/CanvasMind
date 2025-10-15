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

    def is_template_expression(self, value: str) -> bool:
        """
        判断是否为模板表达式（包含 {{...}}）
        """
        return isinstance(value, str) and re.search(r'\$[^$]*\$', value) is not None

    def evaluate_template(self, template: str, local_vars: Optional[Dict[str, Any]] = None) -> str:
        """
        处理模板字符串，支持临时局部变量（如 inputs）
        :param template: 模板字符串，如 "路径: $input.file_path$"
        :param local_vars: 临时变量字典，如 {"input_file_path": "/data.csv"}
        :return: 替换后的字符串
        """
        if not self.is_template_expression(template):
            return template

        # 创建临时符号表（局部变量优先）
        temp_symtable = dict(self.interp.symtable)  # 复制全局符号表
        if local_vars:
            temp_symtable.update(local_vars)

        def replace_match(match):
            expr = match.group(1).strip()
            if not expr:
                return ""
            # 将 expr 中的 input.xxx 转为 input_xxx（可选，也可直接允许点语法）
            # 但 asteval 不支持点语法（如 input.file），所以必须展平
            # 所以我们要求用户写 input_file_path，而不是 input.file_path
            # 或者在这里自动转换：把 input.xxx -> input_xxx
            safe_expr = re.sub(r'\b(env|custom|node_vars|input)\.([a-zA-Z_][a-zA-Z0-9_]*)', r'\1_\2', expr)
            try:
                # 使用临时符号表求值
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