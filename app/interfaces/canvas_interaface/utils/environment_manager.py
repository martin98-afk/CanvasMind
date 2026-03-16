# /app/interfaces/canvas_interface/environment_manager.py
from app.interfaces.canvas_interaface.utils.logger import get_logger
from app.interfaces.canvas_interaface.utils.message_manager import MessageManager
try:
    from PyQt5 import sip
except Exception:
    import sip

logger = get_logger("EnvironmentManager")

class EnvironmentManager:
    def __init__(self, parent):
        self.parent = parent
        self.init = False
        self.env_data = None
        self.env_combo = self.parent.env_combo
        # 新增、删除环境时，重新加载环境列表
        self.parent.parent.package_manager.env_changed.connect(self.load_env_combos)

    def load_env_combos(self, env_data=None):
        if not self.env_combo or sip.isdeleted(self.env_combo):
            return
        envs = self.parent.parent.package_manager.get_all_environments()
        self.env_combo.clear()
        for env in envs:
            self.env_combo.addItem(env["name"], userData=env)
        if env_data and env_data in envs:
            self.env_combo.setCurrentText(env_data.get("name"))
        else:
            self.env_combo.setCurrentText(self.parent.config.current_env_selected.value)
        self.env_data = self.env_combo.currentData()
        if not self.init:
            self.parent.ipython_kernel.start_kernel(self.env_data)
            self.env_combo.currentIndexChanged.connect(self.on_environment_changed)
            self.init = True

    def on_environment_changed(self):
        current_text = self.env_combo.currentText()
        # 获取userData
        self.env_data = self.env_combo.currentData()
        self.parent.ipython_kernel.start_kernel(self.env_data)
        self.parent.env_changed.emit(self.env_data.get("path"))
        self.parent.dependency_checker.run_check()
        self.parent.ui_manager.reset_env_buttons_state()
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
