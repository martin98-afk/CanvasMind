# /app/interfaces/canvas_interface/environment_manager.py
from PyQt5.QtCore import QTimer, Qt
from app.interfaces.canvas_interaface.utils.logger import get_logger
from app.interfaces.canvas_interaface.widgets.message_manager import MessageManager

logger = get_logger("EnvironmentManager")

class EnvironmentManager:
    def __init__(self, parent):
        self.parent = parent
        self.env_combo = None

    def create_environment_selector(self):
        from PyQt5.QtWidgets import QWidget, QHBoxLayout
        from qfluentwidgets import TransparentToolButton, ComboBox
        container = QWidget(self.parent.canvas_widget)
        container.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        container.move(0, 5)
        layout = QHBoxLayout(container)
        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 0)

        label = TransparentToolButton()
        label.setText("环境:")
        label.setFixedSize(50, 30)

        self.env_combo = ComboBox(container)
        self.env_combo.setFixedWidth(140)
        self.load_env_combos()
        self.env_combo.currentIndexChanged.connect(self.parent.on_environment_changed)

        layout.addWidget(label)
        layout.addWidget(self.env_combo)
        layout.addStretch()
        container.setLayout(layout)
        container.show()
        self.parent.env_selector_container = container

    def load_env_combos(self):
        self.env_combo.clear()
        if hasattr(self.parent.parent, 'package_manager') and self.parent.parent.package_manager:
            envs = self.parent.parent.package_manager.mgr.list_envs()
            for env in envs:
                self.env_combo.addItem(env, userData=env)

    def on_environment_changed(self):
        current_text = self.env_combo.currentText()
        QTimer.singleShot(0, self.parent.connect_ipython_kernel)
        self.parent.env_changed.emit(
            str(self.parent.parent.package_manager.mgr.get_python_exe(self.env_combo.currentData()))
        )
        MessageManager.info("环境切换", f"当前运行环境: {current_text}", self.parent)

    def get_current_python_exe(self):
        current_data = self.env_combo.currentData()
        if (hasattr(self.parent.parent, 'package_manager') and
            self.parent.parent.package_manager and current_data):
            try:
                return str(self.parent.parent.package_manager.mgr.get_python_exe(current_data))
            except Exception as e:
                MessageManager.error("错误", f"获取环境 {current_data} 的Python路径失败: {str(e)}", self.parent)
                return None
        return None