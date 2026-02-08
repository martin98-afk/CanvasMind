# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, QPoint, QTimer
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QApplication, QSizePolicy
from qfluentwidgets import (ScrollArea, SettingCardGroup, SimpleCardWidget,
                            SwitchSettingCard, RangeSettingCard, OptionsSettingCard, InfoBar)

from app.utils.utils import get_icon


class CanvasSettingPopup(QWidget):
    """画布设置弹窗 - 修复对齐与失去焦点消失问题"""

    def __init__(self, parent, config):
        super().__init__(parent)
        self.cfg = config
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)  # 单次触发
        self._save_timer.setInterval(500)  # 延迟 500ms 保存 (可根据需求调整)
        self._save_timer.timeout.connect(self._perform_save_to_disk)  # 绑定真实保存函数
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
        """
        配置改变时的槽函数（轻量级）。
        只触发内存更新信号和重置保存计时器，不进行磁盘 IO。
        """
        self._save_timer.start()

    def _perform_save_to_disk(self):
        """
        【内部方法】真正执行磁盘写入操作。
        由计时器触发，避免 IO 阻塞 UI。
        """
        try:
            self.cfg.save_config()
            # 可选：如果你想在控制台看保存时机，取消下面注释
            # print("✅ 配置已写入硬盘")
        except Exception as e:
            print(f"❌ 保存配置失败: {e}")
            # 如果保存失败，可以弹个窗提示
            InfoBar.error(
                title=self.tr("保存失败"),
                content=str(e),
                parent=self,
                duration=3000
            )

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
        self.nodeResizeMemoryCard = SwitchSettingCard(
            get_icon("画布"),
            self.tr("缩放记忆"),
            configItem=self.cfg.canvas_resize_memory,
            parent=group
        )
        self.nodeResizeMemoryCard.checkedChanged.connect(self.onConfigChanged)
        self.NodeProxyCard = RangeSettingCard(
            self.cfg.node_proxy_size,
            get_icon("画布"),
            self.tr("绘制距离"),
            parent=group
        )
        self.NodeProxyCard.valueChanged.connect(self.onConfigChanged)
        self.nodeAnimationCard = SwitchSettingCard(
            get_icon("画布"),
            self.tr("节点动画"),
            configItem=self.cfg.node_animation,
            parent=group
        )
        self.nodeAnimationCard.checkedChanged.connect(self.onConfigChanged)
        self.autoCollapseCard = SwitchSettingCard(
            get_icon("画布"),
            self.tr("Proxy模式自动收缩"),
            configItem=self.cfg.canvas_auto_collapse,
            parent=group
        )
        self.autoCollapseCard.checkedChanged.connect(self.onConfigChanged)

        self.showGridCard = OptionsSettingCard(self.cfg.canvas_grid_mode, get_icon("画布"), "显示网格",
                                               texts=["线网格", "点网格", "无网格"], parent=group)
        self.pipelayoutCard = OptionsSettingCard(self.cfg.canvas_pipelayout, get_icon("画布"), "连线类型",
                                                 texts=["直线", "曲线", "折线"], parent=group)
        self.canvasFontCard = OptionsSettingCard(self.cfg.canvas_font_type, get_icon("画布"), "字体设置",
                                                 texts=self.cfg.canvas_font_type.options, parent=group)

        self.showGridCard.optionChanged.connect(self.onConfigChanged)
        self.pipelayoutCard.optionChanged.connect(self.onConfigChanged)
        self.canvasFontCard.optionChanged.connect(self.onConfigChanged)

        group.addSettingCard(self.nodeResizeMemoryCard)
        group.addSettingCard(self.NodeProxyCard)
        group.addSettingCard(self.nodeAnimationCard)
        group.addSettingCard(self.autoCollapseCard)
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