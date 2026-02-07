# -*- coding: utf-8 -*-
from app.node_plugins.base import DisplayPlugin
from app.widgets.node_widget.display_widgets.progress_bar import ProgressBarWrapper


class ProgressDisplayPlugin(DisplayPlugin):
    plugin_id = "display_progress"
    plugin_name = "进度条展示插件"
    plugin_desc = "在节点上展示任务执行进度（0-100）"
    
    # 模板演示：data 传入整数或浮点数，也可以传入带状态的字典
    plugin_template = """self.emit_message(
            method="display_progress",
            params={"progress": {"data": {"current_value": 45, "min": 0, "max": 100}}}
        )
"""

    def render(self, node, port_name, data):
        """
        data: 期望是一个数值 (int/float) 或者是 {"value": 50, "text": "正在计算..."}
        """
        key = f"progress_{port_name}"

        if key not in node._inline_widgets:
            # 创建进度条包装器
            # PropertyType.PROGRESS 需要在你的 PropertyType 中定义，或者找个类似的
            widget = ProgressBarWrapper(
                parent=node.view,
                name=key, 
                default=int(data.get("current_value", 0)),
                min=int(data.get('min', 0)),
                max=int(data.get("max", 100)),
                window=node.parent_window
            )
            # 添加到节点的 Visual 标签页
            node._add_inline_widget(key, widget, tab='Visual')
        else:
            # 如果已存在，则更新值
            node._inline_widgets[key].set_value(int(data.get("current_value", 0)))