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


class LoopNode(BaseComponent):
    name = "循环控制器"
    category = "测试组件"
    description = "执行循环操作"

    inputs = [
        PortDefinition(name="initial_data", label="初始数据"),
        PortDefinition(name="condition", label="循环条件")
    ]

    outputs = [
        PortDefinition(name="loop_data", label="循环数据"),
        PortDefinition(name="final_result", label="最终结果")
    ]

    properties = {
        "max_iterations": PropertyDefinition(
            type=PropertyType.INT,
            default=10,
            label="最大迭代次数"
        ),
        "loop_condition": PropertyDefinition(
            type=PropertyType.TEXT,
            default="data['count'] < 5",
            label="循环条件表达式"
        )
    }

    def run(self, params, inputs=None):
        import ast
        import operator
        raise NotImplementedError("LoopNode.run() is not implemented")
        max_iter = int(params.max_iterations)
        condition_expr = params.loop_condition

        # 初始数据
        loop_data = inputs.initial_data if inputs else {"count": 0}
        condition = inputs.condition

        iteration = 0
        while iteration < max_iter and self._evaluate_condition(condition_expr, loop_data):
            # 这里需要执行循环体内的节点
            # 由于 NodeGraphQt 是 DAG（有向无环图），不能直接循环
            # 需要通过主程序来协调执行

            loop_data = self._execute_loop_body(loop_data)
            iteration += 1

            # 检查是否满足退出条件
            if not self._evaluate_condition(condition_expr, loop_data):
                break

        return {
            "loop_data": loop_data,
            "final_result": f"循环执行了 {iteration} 次"
        }

    def _evaluate_condition(self, expr, data):
        """安全地评估条件表达式"""
        try:
            # 使用 ast.literal_eval 或安全的表达式求值
            # 这里简化处理
            return eval(expr, {"__builtins__": {}}, {"data": data})
        except:
            return False

    def _execute_loop_body(self, data):
        """执行循环体 - 需要主程序协调"""
        # 这个方法需要与主程序通信来执行 Backdrop 内的节点
        # 具体实现见下面的主程序代码
        return data
