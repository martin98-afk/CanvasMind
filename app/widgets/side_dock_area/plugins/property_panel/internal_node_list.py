# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import QListWidgetItem
from loguru import logger
from qfluentwidgets import ListWidget


class InternalNodeList(ListWidget):

    STATUS_TEXT_MAP = {
        "running": "🟡 运行中",
        "last_success": "🟤 成功过",
        "success": "🟢 成功",
        "failed": "🔴 失败",
        "unrun": "⚪ 未运行",
        "pending": "🔵 待运行",
        "disabled": "⚫ 禁用"
    }

    def __init__(self, status_list, node_name_list, parent=None):
        super().__init__(parent)
        self._status_list = list(status_list) if status_list else []
        self._name_list = list(node_name_list) if node_name_list else []
        self._rebuild_items()

    def _rebuild_items(self):
        """根据当前状态和名称列表重建列表项"""
        self.clear()
        if not self._name_list:
            self.addItem(QListWidgetItem("暂无内部节点"))
        else:
            for status, name in zip(self._status_list, self._name_list):
                status_text = self.STATUS_TEXT_MAP.get(status, "⚪ 未知")
                item_text = f"{status_text} - {name}"
                self.addItem(QListWidgetItem(item_text))

    def update_content(self, new_status_list, new_name_list):
        """更新列表内容，优先复用项以保持选中状态和滚动位置"""
        if len(new_status_list) != len(new_name_list):
            logger.warning("Status list and name list length mismatch")
            return

        new_status_list = list(new_status_list)
        new_name_list = list(new_name_list)

        # 保存当前选中行和滚动位置（提升 UX）
        current_row = self.currentRow()
        scroll_pos = self.verticalScrollBar().value()

        if len(new_status_list) != len(self._status_list):
            # 长度变化：重建
            self._status_list = new_status_list
            self._name_list = new_name_list
            self._rebuild_items()
        else:
            # 长度不变：逐项更新文本
            self._status_list = new_status_list
            self._name_list = new_name_list
            for i in range(len(new_status_list)):
                status_text = self.STATUS_TEXT_MAP.get(new_status_list[i], "⚪ 未知")
                item_text = f"{status_text} - {new_name_list[i]}"
                self.item(i).setText(item_text)

        # 尝试恢复选中状态和滚动位置
        if 0 <= current_row < self.count():
            self.setCurrentRow(current_row)
        self.verticalScrollBar().setValue(scroll_pos)

    def update_item_status(self, index, new_status):
        """更新特定项的状态（不推荐单独使用，建议用 update_content）"""
        if 0 <= index < len(self._status_list):
            self._status_list[index] = new_status
            status_text = self.STATUS_TEXT_MAP.get(new_status, "⚪ 未知")
            item_text = f"{status_text} - {self._name_list[index]}"
            if index < self.count():
                self.item(index).setText(item_text)

    def get_current_selected_row(self):
        """方便外部获取当前选中行"""
        return self.currentRow()

    def set_current_selected_row(self, row):
        """允许外部设置选中行"""
        if 0 <= row < self.count():
            self.setCurrentRow(row)