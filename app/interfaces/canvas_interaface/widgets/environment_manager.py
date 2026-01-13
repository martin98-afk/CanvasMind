# /app/interfaces/canvas_interface/environment_manager.py
from PyQt5.QtCore import QTimer, Qt
from app.interfaces.canvas_interaface.utils.logger import get_logger
from app.interfaces.canvas_interaface.widgets.message_manager import MessageManager

logger = get_logger("EnvironmentManager")

class EnvironmentManager:
    def __init__(self, parent):
        self.parent = parent
        self.env_data = None

    def load_env_combos(self):
        self.env_combo = self.parent.env_combo
        self.env_combo.clear()
        if hasattr(self.parent.parent, 'package_manager') and self.parent.parent.package_manager:
            envs = self.parent.parent.package_manager.get_all_environments()
            for env in envs:
                self.env_combo.addItem(env["name"], userData=env)
            self.env_combo.setCurrentText(self.parent.config.current_env_selected.value)
            self.env_data = self.env_combo.currentData()

    def on_environment_changed(self):
        current_text = self.env_combo.currentText()
        # 获取userData
        self.env_data = self.env_combo.currentData()
        QTimer.singleShot(0, self.parent.connect_kernel)
        self.parent.env_changed.emit(self.env_data.get("path"))
        self.parent.dependency_checker.run_check()
        MessageManager.info("环境切换", f"当前运行环境: {current_text}", self.parent)

    def get_current_python_exe(self):
        current_data = self.env_combo.currentData()
        if (hasattr(self.parent.parent, 'package_manager') and
            self.parent.parent.package_manager and current_data):
            try:
                return current_data.get("path")
            except Exception as e:
                MessageManager.error("错误", f"获取环境 {current_data} 的Python路径失败: {str(e)}", self.parent)
                return None
        return None