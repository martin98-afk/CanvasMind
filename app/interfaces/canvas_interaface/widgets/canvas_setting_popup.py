# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, QPoint, pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QApplication, QSizePolicy
from qfluentwidgets import (ScrollArea, SettingCardGroup, SimpleCardWidget,
                            SwitchSettingCard, RangeSettingCard, OptionsSettingCard)

from app.utils.utils import get_icon


class CanvasSettingPopup(QWidget):
    """画布设置弹窗 - 修复对齐与失去焦点消失问题"""

    def __init__(self, parent, config):
        super().__init__(parent)
        self.cfg = config

        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 固定宽度，确保每次打开宽度一致
        self.WIN_WIDTH = 500
        self.setFixedWidth(self.WIN_WIDTH)

        self._init_ui()

    def _init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        self.container = SimpleCardWidget(self)
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(2, 2, 2, 2)

        self.scroll_area = ScrollArea(self.container)
        self.scroll_area.setWidgetResizable(True)  # 关键：允许内容跟随视口拉伸
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")

        self.scroll_content = QWidget()
        # 核心修复：设置内容部件的尺寸策略，确保水平方向充满
        self.scroll_content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.vBoxLayout = QVBoxLayout(self.scroll_content)
        self.vBoxLayout.setContentsMargins(15, 15, 15, 15)
        self.vBoxLayout.setSpacing(12)

        self.setup_canvas_run_settings()
        self.setup_canvas_io_settings()
        self.setup_canvas_display_settings()

        # 在底部添加弹簧，防止卡片数量少时上下间距过大
        self.vBoxLayout.addStretch(1)

        self.scroll_area.setWidget(self.scroll_content)
        self.container_layout.addWidget(self.scroll_area)
        self.main_layout.addWidget(self.container)

        self.container.setStyleSheet("""
            SimpleCardWidget {
                background-color: #2D2D2D;
                border: 1px solid #454545;
                border-radius: 12px;
            }
        """)

    def onConfigChanged(self):
        pass

    def setup_canvas_run_settings(self):
        group = SettingCardGroup("画布运行设置", self.scroll_content)
        cards = [
            SwitchSettingCard(get_icon("运行模式"), "启用节点超时", configItem=self.cfg.node_run_timeout_toggle,
                              parent=group),
            RangeSettingCard(self.cfg.node_run_timeout, get_icon("运行模式"), "超时时间", parent=group),
            SwitchSettingCard(get_icon("运行模式"), "启用并行运行", configItem=self.cfg.run_parallel, parent=group),
            RangeSettingCard(self.cfg.run_parallel_max_workers, get_icon("运行模式"), "并行度", parent=group)
        ]
        for card in cards:
            group.addSettingCard(card)
            # 绑定变更
            if hasattr(card, 'checkedChanged'): card.checkedChanged.connect(self.onConfigChanged)
            if hasattr(card, 'valueChanged'): card.valueChanged.connect(self.onConfigChanged)
        self.vBoxLayout.addWidget(group)

    def setup_canvas_io_settings(self):
        group = SettingCardGroup("画布保存设置", self.scroll_content)
        self.autoSaveCard = SwitchSettingCard(get_icon("自动保存"), "自动保存", configItem=self.cfg.canvas_auto_save,
                                              parent=group)
        self.autoSaveIntervalCard = RangeSettingCard(self.cfg.canvas_auto_save_interval, get_icon("自动保存"), "修改",
                                                     parent=group)

        self.autoSaveCard.checkedChanged.connect(self.onConfigChanged)
        self.autoSaveIntervalCard.valueChanged.connect(self.onConfigChanged)

        group.addSettingCard(self.autoSaveCard)
        group.addSettingCard(self.autoSaveIntervalCard)
        self.vBoxLayout.addWidget(group)

    def setup_canvas_display_settings(self):
        group = SettingCardGroup("画布显示设置", self.scroll_content)
        self.showGridCard = OptionsSettingCard(self.cfg.canvas_grid_mode, get_icon("画布"), "显示网格",
                                               texts=["线网格", "点网格", "无网格"], parent=group)
        self.pipelayoutCard = OptionsSettingCard(self.cfg.canvas_pipelayout, get_icon("画布"), "连线类型",
                                                 texts=["直线", "曲线", "折线"], parent=group)
        self.canvasFontCard = OptionsSettingCard(self.cfg.canvas_font_type, get_icon("画布"), "字体设置",
                                                 texts=self.cfg.canvas_font_type.options, parent=group)

        self.showGridCard.optionChanged.connect(self.onConfigChanged)
        self.pipelayoutCard.optionChanged.connect(self.onConfigChanged)
        self.canvasFontCard.optionChanged.connect(self.onConfigChanged)

        group.addSettingCard(self.showGridCard)
        group.addSettingCard(self.pipelayoutCard)
        group.addSettingCard(self.canvasFontCard)
        self.vBoxLayout.addWidget(group)

    def show_at_button(self, button):
        """精准对齐显示并解决坍缩"""
        # --- 核心修复：强制重新应用宽度约束 ---
        self.scroll_content.setFixedWidth(self.WIN_WIDTH - 10)  # 减去边距

        # 动态计算高度
        self.vBoxLayout.activate()  # 强制布局计算
        hint_h = self.vBoxLayout.sizeHint().height() + 80  # 80 是标题栏+边距
        total_height = min(600, hint_h)
        self.setFixedSize(self.WIN_WIDTH, total_height)

        # 计算位置
        btn_pos = button.mapToGlobal(QPoint(0, 0))

        # 目标：弹窗右下角 对齐 按钮右下角
        tx = btn_pos.x() + button.width() - self.width()
        ty = btn_pos.y() + button.height() - self.height()

        # 屏幕边缘修正
        screen = QApplication.primaryScreen().availableGeometry()
        tx = max(screen.left() + 5, min(tx, screen.right() - self.width() - 5))
        ty = max(screen.top() + 5, min(ty, screen.bottom() - self.height() - 5))

        self.move(tx, ty)

        # 显式触发显示逻辑
        self.show()
        self.raise_()
        self.activateWindow()

    def hideEvent(self, event):
        """隐藏时稍微清理，防止残留尺寸影响下次打开"""
        super().hideEvent(event)
        self.scroll_area.verticalScrollBar().setValue(0)