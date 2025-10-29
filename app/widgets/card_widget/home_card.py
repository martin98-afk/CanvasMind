# coding:utf-8
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout

from qfluentwidgets import IconWidget, TextWrap, FlowLayout, CardWidget

from app.widgets.basic_widget.style_sheet import StyleSheet


class HomeCard(CardWidget):
    """ Sample card """

    def __init__(self, icon, title, content, routeKey, index, triggered, parent=None):
        super().__init__(parent=parent) # 必须首先调用父类构造函数
        self.index = index
        self.routekey = routeKey
        # 保存传入的 triggered 回调函数
        self.triggered_callback = triggered

        self.iconWidget = IconWidget(icon, self)
        self.titleLabel = QLabel(title, self)
        self.contentLabel = QLabel(TextWrap.wrap(content, 35, False)[0], self)

        self.hBoxLayout = QHBoxLayout(self)
        self.vBoxLayout = QVBoxLayout()

        self.setFixedSize(360, 90)
        self.iconWidget.setFixedSize(48, 48)

        self.hBoxLayout.setSpacing(28)
        self.hBoxLayout.setContentsMargins(20, 0, 0, 0)
        self.vBoxLayout.setSpacing(2)
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.setAlignment(Qt.AlignVCenter)

        self.hBoxLayout.setAlignment(Qt.AlignVCenter)
        self.hBoxLayout.addWidget(self.iconWidget)
        self.hBoxLayout.addLayout(self.vBoxLayout)
        self.vBoxLayout.addStretch(1)
        self.vBoxLayout.addWidget(self.titleLabel)
        self.vBoxLayout.addWidget(self.contentLabel)
        self.vBoxLayout.addStretch(1)

        # 设置鼠标悬停指针为手型，提供视觉反馈
        self.setCursor(Qt.PointingHandCursor)

        self.titleLabel.setObjectName('titleLabel')
        self.contentLabel.setObjectName('contentLabel')

    def mousePressEvent(self, event):
        """重写鼠标按下事件，触发回调函数"""
        if event.button() == Qt.LeftButton and self.triggered_callback:
            # 调用保存的回调函数
            self.triggered_callback()
        # 调用父类的 mousePressEvent 以保持原有行为（如焦点、样式变化等）
        super().mousePressEvent(event)


class HomeCardView(QWidget):
    """ Sample card view """

    def __init__(self, title: str, parent=None):
        super().__init__(parent=parent)
        self.titleLabel = QLabel(title, self)
        self.vBoxLayout = QVBoxLayout(self)
        self.flowLayout = FlowLayout()

        self.vBoxLayout.setContentsMargins(36, 0, 36, 0)
        self.vBoxLayout.setSpacing(10)
        self.flowLayout.setContentsMargins(0, 0, 0, 0)
        self.flowLayout.setHorizontalSpacing(12)
        self.flowLayout.setVerticalSpacing(12)

        self.vBoxLayout.addWidget(self.titleLabel)
        self.vBoxLayout.addLayout(self.flowLayout, 1)

        self.titleLabel.setObjectName('viewTitleLabel')
        StyleSheet.SAMPLE_CARD.apply(self)

    def addSampleCard(self, icon, title, content, routeKey, index, triggered=None):
        """ add sample card """
        # 创建 HomeCard 实例时，将当前的 HomeCardView (self) 作为 parent 传递
        card = HomeCard(icon, title, content, routeKey, index, triggered, self)
        self.flowLayout.addWidget(card)
