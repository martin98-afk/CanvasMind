# app/utils/quick_components.py
from PyQt5.QtCore import QObject, pyqtSignal
from pathlib import Path

from app.utils.utils import resource_path
from app.widgets.dialog_widget.add_quick_component_dialog import AddQuickComponentDialog
from app.utils.config import Settings  # ← 你的 Settings 是 QConfig


class QuickComponentManager(QObject):
    quick_components_changed = pyqtSignal()

    def __init__(self, parent_widget, component_map):
        super().__init__(parent_widget)
        self.parent = parent_widget
        self.component_map = component_map
        self.ICONS_DIR = Path(resource_path("icons"))
        self.config = Settings.get_instance()  # 单例

    def get_quick_components(self):
        return self.config.get(self.config.quick_components)

    def set_quick_components(self, value):
        self.config.set(self.config.quick_components, value)
        self.quick_components_changed.emit()

    def open_add_dialog(self):
        dialog = AddQuickComponentDialog(self.parent, self.component_map, self.ICONS_DIR)
        if dialog.exec():
            if dialog.validate():
                new_list = self.get_quick_components() + [{
                    "full_path": dialog.selected_full_path,
                    "icon_path": dialog.selected_icon_path
                }]
                self.set_quick_components(new_list)

    def remove_component(self, full_path):
        current = self.get_quick_components()
        new_list = [qc for qc in current if qc["full_path"] != full_path]
        self.set_quick_components(new_list)