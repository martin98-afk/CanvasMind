from NodeGraphQt import NodeBaseWidget
from PyQt5.QtCore import QSize

from app.widgets.code_editer import CodeEditorWidget


class CodeEditorWidgetWrapper(NodeBaseWidget):
    def __init__(self, parent=None, name="", label="", default="", window=None):
        super().__init__(parent)
        self.set_name(name)
        self.set_label(label)
        self._editor = CodeEditorWidget(parent=window, python_exe=window.get_current_python_exe())
        window.env_changed.connect(self._editor.code_editor.set_jedi_environment)
        self._editor.setMinimumSize(800, 400)  # 足够大的编辑区域
        self._editor.set_code(default)
        self._editor.code_changed.connect(self._on_code_changed)
        self.set_custom_widget(self._editor)

    def _on_code_changed(self):
        self.on_value_changed(self._editor.get_code())

    def get_value(self):
        return self._editor.get_code()

    def set_value(self, value):
        self._editor.set_code(value or "")
