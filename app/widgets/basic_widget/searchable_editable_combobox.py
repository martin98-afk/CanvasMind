from PyQt5.QtCore import Qt, QStringListModel
from PyQt5.QtWidgets import QCompleter
from qfluentwidgets import EditableComboBox


class SearchableEditableComboBox(EditableComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)

        # 1. 使用私有变量名 _search_completer，避免覆盖基类的 completer() 方法
        self._search_completer = QCompleter(self)

        # 设置匹配模式为：包含匹配
        self._search_completer.setFilterMode(Qt.MatchContains)
        # 设置补全模式：弹出列表
        self._search_completer.setCompletionMode(QCompleter.PopupCompletion)
        self._search_completer.setCaseSensitivity(Qt.CaseInsensitive)

        # 2. 使用标准的 setCompleter 方法注册
        self.setCompleter(self._search_completer)

        # 内部维护一个纯文本列表用于同步
        self._item_texts = []

    def addItem(self, text: str, icon = None, userData=None):
        """重写单条添加"""
        super().addItem(text, icon, userData)
        # 去重处理（可选）
        if text not in self._item_texts:
            self._item_texts.append(text)
            self._update_completer_model()

    def addItems(self, texts: list):
        """重写批量添加"""
        super().addItems(texts)
        # 这里的 texts 应该是从 Scanner 获取的所有类型列表
        self._item_texts = list(set(self._item_texts + texts))
        self._update_completer_model()

    def _update_completer_model(self):
        """更新补全器的数据源"""
        model = QStringListModel(self._item_texts, self._search_completer)
        self._search_completer.setModel(model)

    def clear(self):
        """重写清空方法"""
        # 注意：qfluentwidgets 的 EditableComboBox.clear()
        # 内部可能只清空了菜单，我们也需要清空 LineEdit 内容和补全器
        super().clear()
        self._item_texts = []
        self._update_completer_model()
        self.setText("")