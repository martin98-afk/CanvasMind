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


class DingTalkConfig(BaseComponent):
    name = "钉钉配置"
    category = "消息推送"
    description = "设置钉钉机器人凭证到全局环境"
    
    properties = {
        "config_key": PropertyDefinition(
            type=PropertyType.TEXT,
            default="CM_DINGTALK_CONF",
            label="配置名",
        ),
        "token": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="Token/Webhook",
        ),
        "secret": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="加签密钥 (Secret)",
        ),
    }

    def run(self, params, inputs=None):

        token = params.get("token", "").strip()
        secret = params.get("secret", "").strip()

        if not token:
            return {"status": "Skipped (No Token)"}

        config_data = {
            "token": token,
            "secret": secret
        }

        # 将配置写入全局变量
        self.emit_message(
            method="add_custom_to_global_variable",
            params={params.config_key: config_data}
        )
    