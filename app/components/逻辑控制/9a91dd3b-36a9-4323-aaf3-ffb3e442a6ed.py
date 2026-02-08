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


class Component(BaseComponent):
    name = "等待指定时间"
    category = "逻辑控制"
    description = "在流程中暂停执行，等待指定秒数"
    requirements = ""
    inputs = [
        PortDefinition(
            name="trigger",
            label="触发信号",
            type=ArgumentType.INT,
            connection=ConnectionType.SINGLE
        )
    ]
    outputs = [
        PortDefinition(
            name="completed",
            label="执行完成",
            type=ArgumentType.TEXT,
            connection=ConnectionType.SINGLE
        )
    ]
    properties = {
        "seconds": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=5.0,
            label="等待时间（秒）",
        ),
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import time

        # 获取等待时间（秒）
        wait_time = float(inputs.trigger or params.seconds)

        # 记录开始时间
        self.logger.info(f"开始等待 {wait_time} 秒...")

        # 等待指定时间
        time.sleep(wait_time)

        # 输出完成信号
        self.logger.info("等待结束，继续执行流程")
        return {
            "completed": f"等待完成，已等待 {wait_time} 秒"
        }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={"seconds": "3.5"},
        inputs={"trigger": "开始等待"},
        node_id="test_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True,
        global_vars={}
    )
    print(result)
