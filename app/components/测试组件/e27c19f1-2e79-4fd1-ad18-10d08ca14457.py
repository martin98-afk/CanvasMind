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


class Component(BaseComponent):
    name = "逻辑判断"
    category = "测试组件"
    description = ""
    requirements = ""
    
    # 固定三个变量输入（可扩展）
    inputs = [
        PortDefinition(name="var1", label="变量1", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
        PortDefinition(name="var2", label="变量2", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
        PortDefinition(name="var3", label="变量3", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    
    outputs = [
        PortDefinition(name="output", label="判断结果", type=ArgumentType.BOOL),
    ]
    
    properties = {
        "conditions": PropertyDefinition(
            type=PropertyType.DYNAMICFORM,
            label="",
            schema={
                "取反": PropertyDefinition(
                    type=PropertyType.CHOICE,
                    default=" ",
                    label="选择变量",
                    choices=["/", "not"]
                ),
                "变量": PropertyDefinition(
                    type=PropertyType.TEXT,
                    default="var1",
                    label="选择变量",
                ),
                "操作符": PropertyDefinition(
                    type=PropertyType.CHOICE,
                    default="==",
                    label="比较操作符",
                    choices=[">", "<", "==", ">=", "<=", "!="]
                ),
                "常量": PropertyDefinition(
                    type=PropertyType.TEXT,
                    default="0",
                    label="常量值",
                ),
            }
        ),
        "组合方式": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="and",
            label="条件组合逻辑",
            choices=["and", "or"]
        ),
        "整体取反": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="最终结果取反",
        ),
    }

    def run(self, params, inputs = None):
        self.logger.info(params)
        # 检查是否有未连接但被使用的变量
        conditions = params.get("conditions", [])
        if not conditions:
            # 无条件时默认为 True
            final_result = True
        else:
            results = []
            for cond in conditions:
                var_val = cond.get("变量", "var1")
                op = cond.get("操作符", "==")
                const_str = str(cond.get("常量", "0")).strip()
                negate = cond.get("取反", "")
                const_val = const_str
                self.logger.info(const_val)
                self.logger.info(var_val)
                
                # 执行比较
                try:
                    if op == ">":
                        res = var_val > const_val
                        self.logger.info(res)
                    elif op == "<":
                        res = var_val < const_val
                        self.logger.info(res)
                    elif op == "==":
                        res = var_val == const_val
                    elif op == ">=":
                        res = var_val >= const_val
                    elif op == "<=":
                        res = var_val <= const_val
                    elif op == "!=":
                        res = var_val != const_val
                    else:
                        raise ValueError(f"不支持的操作符: {op}")
                except Exception as e:
                    raise RuntimeError(f"条件计算出错: {e}")

                # 单条件取反
                self.logger.info(bool(negate))
                if negate == "not":
                    res = not res

                results.append(res)
                
            self.logger.info(results)
            # 组合所有条件
            combine_mode = params.get("组合方式", "and")
            if combine_mode == "and":
                final_result = all(results)
            else:  # "or"
                final_result = any(results)

        # 整体取反
        if bool(params.get("整体取反", False)):
            final_result = not final_result

        return {"output": final_result}
