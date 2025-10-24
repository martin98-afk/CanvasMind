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
    name = "工具调用"
    category = "大模型组件"
    description = "将已导出的模型做为工具的形式进行调用，并获取运行结果"
    requirements = ""
    inputs = [
        PortDefinition(name="project_name", label="项目名称", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
        PortDefinition(name="input", label="项目输入", type=ArgumentType.JSON, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output1", label="输出1", type=ArgumentType.TEXT),
    ]
    properties = {
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import json
        runner_path = pathlib.Path(__file__).parent.parent.parent/ "runner" / "workflow_runner.py"
        spec = importlib.util.spec_from_file_location("base", str(runner_path))
        runner_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner_module)

        # 导入所需项目
        execute_workflow = runner_module.execute_workflow
        try:
            # 获取输入参数
            project_name = inputs.project_name

            if not project_name:
                return {"output1": "错误: 请提供项目名称"}

            # 解析输入数据
            external_inputs = inputs.input

            # 构建项目路径 (假设项目在当前工作目录下的项目文件夹中)
            project_path = pathlib.Path(project_name)

            # 检查项目是否存在
            if not project_path.exists():
                return {"output1": f"错误: 项目路径不存在: {project_path}"}

            # 构建工作流文件路径 (假设工作流文件名为 model.workflow.json)
            workflow_file = project_path / "model.workflow.json"
            if not workflow_file.exists():
                return {"output1": f"错误: 工作流文件不存在: {workflow_file}"}

            # 调用执行函数
            result = execute_workflow(
                str(workflow_file),
                external_inputs=external_inputs,
                logger=self.logger
            )

            # 将结果转换为字符串返回
            if isinstance(result, (dict, list)):
                result_str = json.dumps(result, ensure_ascii=False, indent=2)
            else:
                result_str = str(result)

            return {"output1": result_str}

        except Exception as e:
            import traceback
            error_msg = f"执行失败: {str(e)}\n{traceback.format_exc()}"
            return {"output1": error_msg}
