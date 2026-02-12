# -*- coding: utf-8 -*-
import os
import pickle
import tempfile
import uuid

from app.utils.config import Settings
from app.utils.utils import ssh_send_file
from app.node_plugins.base import InteractivePlugin


class ClearVariablePlugin(InteractivePlugin):
    plugin_id = "create_next_node"  # 对应 method: "ui.ask"
    plugin_name = "新建下一个节点"
    plugin_desc = "在当前节点后创建指定节点"
    plugin_template = """self.emit_interactive_message(
            method="create_next_node",
            params={
                "key": "next_node_key"
            }
        )
    """

    def operate(self, node, params):
        node = node.parent_window.node_operations.create_next_node(params.get("key"))
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

        if Settings.get_instance().communication_method.value == "ZMQ通信":
            return node.persistent_id
        else:
            on_confirmed(node.persistent_id)