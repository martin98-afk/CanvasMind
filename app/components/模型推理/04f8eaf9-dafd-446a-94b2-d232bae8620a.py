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
    name = "逻辑回归推理(csv)"
    category = "模型推理"
    description = "组件开发生成组件"
    requirements = "scikit-learn,matplotlib"
    inputs = [
        PortDefinition(name="feature", label="特征", type=ArgumentType.CSV),
        PortDefinition(name="model", label="模型", type=ArgumentType.SKLEARNMODEL),
    ]
    outputs = [
        PortDefinition(name="value", label="预测值", type=ArgumentType.ARRAY),
    ]
    properties = {
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        try:
            self.logger.info(inputs)
            from sklearn.linear_model import LogisticRegression
            import matplotlib

            # 读取数据
            feature = inputs.feature
            model = inputs.model
            self.logger.info(feature)
            # 训练模型
            result = model.predict(feature)
            # 预测示例（使用第一行数据）

            self.logger.info(f"Model predict: {result}")
            return {
                "value": result.tolist()
            }

        except Exception as e:
            self.logger.error(f"Error in LogisticRegressionComponent: {e}")
            raise e
