# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
base_path = Path(__file__).parent.parent / "base.py" if (Path(__file__).parent.parent / "base.py").exists() else Path(__file__).parent.parent.parent / "base.py"
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


class DynamicComponent(BaseComponent):
    name = "获取文件夹图像列表"
    category = "数据可视化"
    description = "显示指定文件夹下的所有图像，并显示图像列表"
    requirements = ""

    inputs = [
    ]
    outputs = [
        PortDefinition(name="image_list", label="图像列表", type=ArgumentType.ARRAY),
    ]
    properties = {
        "folder": PropertyDefinition(
            type=PropertyType.FILE,
            default="folder",
            label="待搜索文件夹",
        ),
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        from pathlib import Path
        dir_path = Path(params.folder)
        image_list = [file_path for file_path in dir_path.rglob("*.png")] + \
            [file_path for file_path in dir_path.rglob("*.jpg")] + \
            [file_path for file_path in dir_path.rglob("*.jpeg")]
        self.emit_message(
            method="display_image_gallery",
            params={"output": {"data": image_list, "data_type": "image_list"}},
        )
        return {
            "image_list": image_list
        }
