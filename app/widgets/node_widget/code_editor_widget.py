from NodeGraphQt import NodeBaseWidget
from PyQt5.QtCore import QSize

from app.widgets.code_editer import CodeEditorWidget


class CodeEditorWidgetWrapper(NodeBaseWidget):
    def __init__(self, parent=None, name="", label="", default="", window=None):
        super().__init__(parent)
        self.set_name(name)
        self.set_label(label)
        self._editor = CodeEditorWidget(parent=window)
        self._editor.set_code(default)
        self._editor.code_changed.connect(self._on_code_changed)
        self.set_custom_widget(self._editor)

    def _on_code_changed(self):
        self.on_value_changed(self._editor.get_code())

    def get_value(self):
        return self._editor.get_code()

    def set_value(self, value):
        self._editor.set_code(value or "")

    # ✅ 关键：告诉 NodeGraphQt 这个控件需要更大空间
    def sizeHint(self):
        return QSize(600, 400)  # 宽 600，高 400