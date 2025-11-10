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
    name = "文件列表压缩"
    category = "数据存储"
    description = "将多输入的文件、数据压缩为一个zip文件"
    requirements = ""
    inputs = [
        PortDefinition(name="paths", label="文件列表", type=ArgumentType.FILE, connection=ConnectionType.MULTIPLE),
    ]
    outputs = [
        PortDefinition(name="output.zip", label="输出1", type=ArgumentType.FILE),
    ]
    properties = {
    }
    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import zipfile
        from pathlib import Path
        from zipfile import ZipFile
        with ZipFile("output.zip", "w", zipfile.ZIP_DEFLATED) as zipf:
            for path in inputs.paths:
                file = Path(path)
                if file.is_file():
                    zipf.write(path, arcname=path.name)
                elif file.is_dir():
                    for sub_file in file.rglob("*"):
                        if sub_file.is_file():
                            zipf.write(sub_file, arcname=subfile.relateive_to(path.parent))
        file = open("output.zip", "rb")
        return {
            "output.zip": file.read()
        }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={"prop1": "test"},
        inputs={"paths": [r"D:\work\WorkFlowGUI\requirements.txt"]},
        node_id="测试模型",
        show_input_types = True,
        show_output_types = True,
        show_execution_time = True,
        global_vars = {}
    )
    print(result)
