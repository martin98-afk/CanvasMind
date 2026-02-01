# app/utils/quick_components.py
from PyQt5.QtCore import QObject, pyqtSignal

from app.interfaces.canvas_interaface.widgets.add_quick_component_dialog import AddQuickComponentPopup
from app.utils.config import Settings


class QuickComponentManager(QObject):
    quick_components_changed = pyqtSignal()

    def __init__(self, parent, component_map):
        """
        :param parent: 通常是 MainWindow 或 CanvasInterface
        :param component_map: 组件映射字典
        """
        super().__init__(parent)
        self.parent = parent
        self.component_map = component_map
        self.config = Settings.get_instance()

        # 保存 popup 的引用，防止被垃圾回收
        self._popup = None

    def get_quick_components(self):
        return self.config.get(self.config.quick_components)

    def set_quick_components(self, value):
        self.config.set(self.config.quick_components, value)
        self.config.save_config()
        self.quick_components_changed.emit()

    def open_add_dialog(self, target_widget=None):
        """
        打开添加组件的 Popup
        :param target_widget: 触发该弹窗的按钮 (QPushButton/ToolButton)，用于定位弹窗位置
        """
        # 如果已有弹窗在显示，先关闭它
        if self._popup:
            self._popup.close()
            self._popup = None

        # 实例化 Popup (注意：Popup 需要 parent 来依附)
        self._popup = AddQuickComponentPopup(self.parent, self.component_map)

        # === 关键修改：连接信号 ===
        # 当 Popup 点击确定并通过校验后，会发射 component_added 信号
        self._popup.component_added.connect(self._on_component_added)

        # 显示弹窗
        if target_widget:
            # 使用 Popup 特有的定位方法
            self._popup.show_at_button(target_widget)
        else:
            # 如果没有传按钮，回退到默认显示（通常在左上角或中心，看你具体实现）
            self._popup.show()

    def _on_component_added(self, full_path, icon_path):
        """
        槽函数：处理组件添加逻辑
        """
        # 获取当前列表
        current_list = self.get_quick_components()

        # 构造新数据
        new_item = {
            "full_path": full_path,
            "icon_path": icon_path
        }

        # 更新配置
        new_list = current_list + [new_item]
        self.set_quick_components(new_list)

        # (可选) 可以在这里打印日志或者显示成功的 InfoBar
        # from qfluentwidgets import InfoBar
        # InfoBar.success("成功", "快捷组件已添加", parent=self.parent)

    def remove_component(self, full_path):
        current = self.get_quick_components()
        new_list = [qc for qc in current if qc["full_path"] != full_path]
        self.set_quick_components(new_list)