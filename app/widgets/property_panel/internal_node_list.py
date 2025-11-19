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