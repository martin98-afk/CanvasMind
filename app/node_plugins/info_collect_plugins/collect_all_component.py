# -*- coding: utf-8 -*-
import os
import pickle
import tempfile
import uuid

from qfluentwidgets import (MessageBoxBase, SubtitleLabel, BodyLabel, ComboBox, CheckBox, DoubleSpinBox, SpinBox,
                            TextEdit)

from app.scan_components import ComponentScanner
from app.utils.config import Settings
from app.node_plugins.base import InteractivePlugin
from app.utils.utils import ssh_send_file


class AskPlugin(InteractivePlugin):
    plugin_id = "get_all_components"
    plugin_name = "获取当前所有组件信息"
    plugin_desc = "获取当前组件列表中的所有组件信息"
    plugin_template = """result = self.emit_interactive_message(
            method="get_all_components",
            params={}
        )
"""

    def handle(self, node, params, msg=None):
        response_file = params.get("response_file")

        env_data = getattr(node.parent_window, 'env_data', None)
        is_ssh = env_data and env_data.get('type') == 'ssh'

        def on_confirmed(result_data):
            if is_ssh:
                temp_path = os.path.join(tempfile.gettempdir(), f"ask_{uuid.uuid4().hex}.pkl")
                with open(temp_path, 'wb') as f:
                    pickle.dump(result_data, f)
                ssh_send_file(env_data, temp_path, response_file)
                if os.path.exists(temp_path): os.remove(temp_path)
            else:
                os.makedirs(os.path.dirname(response_file), exist_ok=True)
                with open(response_file, 'wb') as f:
                    pickle.dump(result_data, f)

        component_keys = list(ComponentScanner().get_components()[0].keys())
        if Settings.get_instance().communication_method.value == "ZMQ通信":
            return component_keys
        else:
            on_confirmed(component_keys)
        return None