from NodeGraphQt import NodeBaseWidget
from PyQt5.QtWidgets import QComboBox
from Qt import QtWidgets, QtCore
from qfluentwidgets import CheckBox, ComboBox


class ComboBoxWidget(QtWidgets.QWidget):
    """节点内选择框（在 QGraphicsProxyWidget 中可靠弹出）"""
    valueChanged = QtCore.Signal(str)

    def __init__(self, items=[]):
        super().__init__()
        self.items = list(items) if items else []
        self._value = self.items[0] if self.items else ""
        self.combobox = QComboBox(self)
        self.combobox.setMaxVisibleItems(12)
        if self.items:
            self.combobox.addItems(self.items)
            self.combobox.setCurrentText(self._value)
        self.combobox.currentIndexChanged.connect(self._on_index_changed)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.combobox)

    def _on_index_changed(self, index):
        self._value = self.combobox.currentText()
        self.valueChanged.emit(self._value)

    def get_value(self):
        return self._value

    def set_value(self, value):
        if value not in self.items and value is not None:
            # 动态补充选项，避免无法设置
            self.items.append(value)
            self.combobox.addItem(value)
        self._value = value or ""
        self.combobox.setCurrentText(self._value)


class FluentComboProxy(ComboBox):
    """
    使用 qfluentwidgets.ComboBox 的外观，但弹出使用原生顶层 QFrame + QListView，
    以保证在 QGraphicsProxyWidget / NodeGraphQt 场景中能正常显示。
    """
    def __init__(self, parent=None):
        # 先初始化成员，防止父类构造期间触发事件访问未定义属性
        self._popup = None
        self._list_view = None
        self._closing = False
        super().__init__(parent)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

    def _ensure_popup(self):
        if self._popup is not None:
            return
        popup = QtWidgets.QFrame(None)
        popup.setWindowFlags(QtCore.Qt.Popup | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint)
        popup.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        popup.setObjectName("FluentComboPopup")

        layout = QtWidgets.QVBoxLayout(popup)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(0)

        view = QtWidgets.QListView(popup)
        view.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        view.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        view.setFrameShape(QtWidgets.QFrame.NoFrame)
        view.setMinimumWidth(max(140, self.width()))
        layout.addWidget(view)

        # 样式（尽量贴近 Fluent）
        popup.setStyleSheet(
            """
            #FluentComboPopup { background: rgba(255,255,255,0.98); border-radius: 8px; }
            QListView { padding: 4px; outline: none; }
            QListView::item { height: 28px; padding-left: 10px; }
            QListView::item:selected { background: #E6F0FF; }
            """
        )

        view.clicked.connect(self._on_item_clicked)
        popup.installEventFilter(self)
        popup.setFocusProxy(view)
        self._popup = popup
        self._list_view = view

    def showPopup(self):
        # 构造自定义弹出窗口
        self._ensure_popup()
        # 重建模型，保持与当前条目同步
        try:
            items = [self.itemText(i) for i in range(self.count())]
        except Exception:
            items = []
        model = QtCore.QStringListModel(items, self._popup)
        self._list_view.setModel(model)
        # 同步尺寸与位置
        w = max(self.width(), self._list_view.minimumWidth())
        self._popup.resize(w, min(240, max(120, self.count() * 28 + 12)))
        global_pos = self.mapToGlobal(self.rect().bottomLeft())
        self._popup.move(global_pos)
        # 同步当前选中项
        current = self.currentIndex()
        if current >= 0:
            m = self._list_view.model()
            if m is not None:
                self._list_view.setCurrentIndex(m.index(current, 0))
        self._popup.show()
        self._popup.raise_()
        self._popup.activateWindow()
        self._list_view.setFocus(QtCore.Qt.PopupFocusReason)

    def hidePopup(self):
        if self._popup and self._popup.isVisible():
            self._closing = True
            self._popup.hide()
            self._closing = False

    def eventFilter(self, obj, event):
        popup = getattr(self, "_popup", None)
        if obj is popup and popup is not None:
            et = event.type()
            if et in (QtCore.QEvent.FocusOut, QtCore.QEvent.WindowDeactivate):
                self.hidePopup()
            elif et == QtCore.QEvent.MouseButtonPress:
                if not popup.rect().contains(event.pos()):
                    self.hidePopup()
        return super().eventFilter(obj, event)

    def _on_item_clicked(self, index):
        self.setCurrentIndex(index.row())
        self.hidePopup()

    # 确保在图形场景中点击时可靠触发弹出
    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            QtCore.QTimer.singleShot(0, self.showPopup)
            event.accept()
            return
        super().mousePressEvent(event)


class ComboBoxWidgetWrapper(NodeBaseWidget):
    def __init__(self, parent=None, name="", label="", items=[]):
        super().__init__(parent)
        self.set_name(name)
        self.set_label(label)
        widget = ComboBoxWidget(items=items)
        self.set_custom_widget(widget)
        widget.valueChanged.connect(self.on_value_changed)

    def get_value(self):
        return self.get_custom_widget().get_value()

    def set_value(self, value):
        self.get_custom_widget().set_value(value)


