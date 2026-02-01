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


class GiteeConfig(BaseComponent):
    name = "Gitee图床配置"
    category = "消息推送"
    description = "设置 Gitee 图床凭证到全局环境 (用于图片推送)"

    properties = {
        "config_key": PropertyDefinition(
            type=PropertyType.TEXT, default="CM_GITEE_CONF", label="配置名称"
        ),
        "token": PropertyDefinition(
            type=PropertyType.TEXT, default="", label="Gitee 私人令牌"
        ),
        "owner": PropertyDefinition(
            type=PropertyType.TEXT, default="", label="用户名/组织名"
        ),
        "repo": PropertyDefinition(
            type=PropertyType.TEXT, default="", label="仓库名"
        ),
        "path": PropertyDefinition(
            type=PropertyType.TEXT, default="images", label="存储路径"
        ),
        "branch": PropertyDefinition(
            type=PropertyType.TEXT, default="master", label="分支"
        )
    }

    def run(self, params, inputs=None):
        token = params.get("token", "").strip()
        if not token:
            return {"status": "Skipped (No Token)"}

        config_data = {
            "token": token,
            "owner": params.get("owner", "").strip(),
            "repo": params.get("repo", "").strip(),
            "path": params.get("path", "images").strip(),
            "branch": params.get("branch", "master").strip()
        }

        self.emit_message(
            method="add_custom_to_global_variable",
            params={params.config_key: config_data}
        )