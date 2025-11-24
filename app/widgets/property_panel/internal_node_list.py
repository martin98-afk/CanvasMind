from PyQt5.QtWidgets import QListWidgetItem
from loguru import logger
from qfluentwidgets import ListWidget


class InternalNodeList(ListWidget):

    STATUS_TEXT_MAP = {
        "running": "🟡 运行中",
        "success": "🟢 成功",
        "failed": "🔴 失败",
        "unrun": "⚪ 未运行",
        "pending": "🔵 待运行",
        "disabled": "⚫ 禁用"
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
        if len(new_status_list) != len(new_name_list):
            logger.warning("Status list and name list length mismatch")
            return
        try:
            current_count = self.count()

            if len(new_status_list) != current_count:
                # 数量变化，重建列表（保持简洁）
                self.clear()
                if not new_name_list:
                    self.addItem(QListWidgetItem("暂无内部节点"))
                else:
                    for status, name in zip(new_status_list, new_name_list):
                        status_text = self.STATUS_TEXT_MAP.get(status, "⚪ 未知")
                        item_text = f"{status_text} - {name}"
                        self.addItem(QListWidgetItem(item_text))
            else:
                # 数量相同，逐项更新文本
                for i in range(current_count):
                    status = new_status_list[i]
                    name = new_name_list[i]
                    status_text = self.STATUS_TEXT_MAP.get(status, "⚪ 未知")
                    item_text = f"{status_text} - {name}"
                    self.item(i).setText(item_text)
        except:
            logger.warning("Error updating internal node list")

    def update_item_status(self, index, new_status):
        """更新特定项的状态"""
        if 0 <= index < self.count():
            item = self.item(index)
            if item:
                widget = self.itemWidget(item)
                if widget and hasattr(widget, 'update_status'):
                    widget.update_status(new_status)