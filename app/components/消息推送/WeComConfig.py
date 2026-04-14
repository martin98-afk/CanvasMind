# -*- coding: utf-8 -*-
"""
企业微信配置组件
用于设置企业微信机器人凭证到全局环境
"""
import importlib.util
from pathlib import Path

base_path = Path(__file__).parent.parent / "base.py" if (Path(__file__).parent.parent / "base.py").exists() else Path(__file__).parent.parent.parent / "base.py"
spec = importlib.util.spec_from_file_location("base", str(base_path))
base_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base_module)

# 导入所需项目
BaseComponent = base_module.BaseComponent
PropertyDefinition = base_module.PropertyDefinition
PropertyType = base_module.PropertyType


class WeComConfig(BaseComponent):
    """设置企业微信机器人凭证到全局环境"""
    name = "企业微信配置"
    category = "消息推送"
    description = "设置企业微信群机器人凭证到全局环境，支持Webhook方式推送消息"

    properties = {
        "config_key": PropertyDefinition(
            type=PropertyType.TEXT,
            default="CM_WECOM_CONF",
            label="配置名称",
            description="全局变量中的配置键名",
        ),
        "webhook": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="Webhook地址",
            description="企业微信群机器人的Webhook地址，格式：https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx",
        ),
    }

    def run(self, params, inputs=None):
        webhook = params.get("webhook", "").strip()

        if not webhook:
            return {"status": "Skipped (No Webhook)"}

        config_data = {
            "webhook": webhook,
        }

        self.emit_message(
            method="add_custom_to_global_variable",
            params={params.config_key: config_data}
        )

        return {"status": "OK", "webhook": webhook}