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
    name = "工具调用"
    category = "项目执行"
    description = "将已导出的模型项目作为工具调用，接收项目名称和输入数据，通过运行工作流脚本执行模型任务，返回结果和运行日志，输入为项目路径和JSON格式数据，输出为JSON格式结果和文本日志，无额外参数。"
    requirements = ""
    inputs = [
        PortDefinition(name="project_name", label="项目名称", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
        PortDefinition(name="input", label="项目输入", type=ArgumentType.JSON, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="result", label="工具运行结果", type=ArgumentType.JSON),
        PortDefinition(name="log", label="工具运行日志", type=ArgumentType.TEXT),
    ]
    properties = {
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import os
        import json
        import sys
        import subprocess
        import pickle
        import time
        from pathlib import Path

        try:
            # 获取输入参数
            project_path = Path(inputs.project_name)
            runner_path = project_path / "runner" / "workflow_runner.py"
            # 解析输入数据
            external_inputs = inputs.input
            with open(project_path / "input.pkl", "wb") as f:
                pickle.dump(external_inputs, f)
            # 检查项目是否存在
            if not project_path.exists():
                return {"output1": f"错误: 项目路径不存在: {project_path}"}

            # 构建工作流文件路径 (假设工作流文件名为 model.workflow.json)
            workflow_file = project_path / "model.workflow.json"
            if not workflow_file.exists():
                return {"output1": f"错误: 工作流文件不存在: {workflow_file}"}

            with open(workflow_file, 'r', encoding='utf-8') as f:
                full_data = json.load(f)
            runtime_data = full_data.get("runtime", {})
            python_executable = runtime_data.get("environment_exe", sys.executable)
            proc = subprocess.Popen(
                [python_executable, runner_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                encoding='utf-8'
            )
            while proc.poll() is None:
                time.sleep(1)
            if not (project_path / "result.pkl").exists():
                return {
                    "result": "",
                    "log": open(project_path / "run.log", 'r', encoding="utf-8").read()
                }
            with open(project_path / "result.pkl", "rb") as f:
                outputs = pickle.load(f)

            return {
                "result": outputs,
                "log": open(project_path / "run.log", 'r', encoding="utf-8").read()
            }

        except Exception as e:
            import traceback
            error_msg = f"执行失败: {str(e)}\n{traceback.format_exc()}"
            return {"result": "", "log": error_msg}
