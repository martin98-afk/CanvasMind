from PyQt5.QtWidgets import QListWidgetItem
from qfluentwidgets import ListWidget


class InternalNodeList(ListWidget):

    STATUS_TEXT_MAP = {
        "running": "🟡 运行中",
        "success": "🟢 成功",
        "failed": "🔴 失败",
        "unrun": "⚪ 未运行",
        "pending": "🔵 待运行"
    }

    def __init__(self, status_liist, node_name_list, parent):
        super().__init__(parent)

        if not node_name_list:
            self.addItem(QListWidgetItem("暂无内部节点"))
        else:
            for status, name in zip(status_liist, node_name_list):
                status_text = self.STATUS_TEXT_MAP.get(status)
                item_text = f"{status_text} - {name}"
                item = QListWidgetItem(item_text)
                self.addItem(item)

    def update_content(self, new_status_list, new_name_list):
        """更新列表内容而不重建UI"""
        if len(new_status_list) != self.count() or len(new_name_list) != self.count():
            # 如果数量不同，需要重建
            self._rebuild_items(new_status_list, new_name_list)
            return

        # 更新现有项的文本和状态
        for i in range(self.count()):
            item = self.item(i)
            if item:
                widget = self.itemWidget(item)
                if widget and hasattr(widget, 'setText'):
                    # 假设widget有setText方法来更新内容
                    widget.setText(f"{new_status_list[i]} {new_name_list[i]}")

    def update_item_status(self, index, new_status):
        """更新特定项的状态"""
        if 0 <= index < self.count():
            item = self.item(index)
            if item:
                widget = self.itemWidget(item)
                if widget and hasattr(widget, 'update_status'):
                    widget.update_status(new_status)