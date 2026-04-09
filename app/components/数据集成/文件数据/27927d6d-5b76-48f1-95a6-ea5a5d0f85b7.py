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


class Component(BaseComponent):
    requirements = ""
    name = "文件上传"
    category = "数据集成/文件数据"
    description = "接收用户本地上传的文件，上传后文件会被复制到工作目录，并返回文件路径供下游节点使用；图片文件会自动触发预览显示"
    inputs = [
    ]
    outputs = [
        PortDefinition(name="file", label="文件", type=ArgumentType.UPLOAD),
    ]

    def run(self, params, inputs=None):
        """
        处理用户上传的文件
        - 获取上传文件的路径
        - 若为图片格式(png/jpg/jpeg)，自动通知主进程显示预览
        - 返回文件路径供后续节点使用
        """
        file_path = params.dict().get("file_upload")
        if file_path.endswith("png") or file_path.endswith("jpg") or file_path.endswith("jpeg"):
            # 使用特定格式通知主进程拦截
            self.emit_message(
                method="display_image",
                params={"file": file_path}
            )
        return {"file": file_path}
