from PyQt5 import QtWidgets, QtCore, QtGui


class CanvasMinimap(QtWidgets.QGraphicsView):
    def __init__(self, target_viewer, parent=None):
        super(CanvasMinimap, self).__init__(target_viewer.scene(), parent)
        self.target_viewer = target_viewer  # 关联的主画布 CustomNodeViewer

        # 1. 基础外观设置
        self.setFixedSize(200, 150)  # 缩略图固定大小
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setStyleSheet("border: 1px solid rgba(255, 255, 255, 30); background: rgba(20, 20, 20, 150);")
        self.setInteractive(False)  # 禁用默认 Item 交互，我们自己处理点击

        # 2. 视口矩形（缩略图里那个红框）
        self.viewer_rect_item = QtWidgets.QGraphicsRectItem()
        self.viewer_rect_item.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 100), 2))
        self.viewer_rect_item.setZValue(1e9)  # 永远在最顶层
        self.scene().addItem(self.viewer_rect_item)

        # 3. 开启定时刷新，确保缩略图和主图同步
        self._refresh_timer = QtCore.QTimer(self)
        self._refresh_timer.timeout.connect(self.update_view)
        self._refresh_timer.start(50)  # 20fps 刷新率

    def update_view(self):
        if not self.isVisible() or not self.target_viewer:
            return

        # 让缩略图始终展示整个场景的内容
        rect = self.scene().itemsBoundingRect()
        if not rect.isEmpty():
            self.fitInView(rect, QtCore.Qt.KeepAspectRatio)

        # 更新红框位置：计算主视口在场景中的坐标范围
        # mapToScene 获取主视口四个角对应的场景坐标
        v_rect = self.target_viewer.viewport().rect()
        scene_rect = self.target_viewer.mapToScene(v_rect).boundingRect()
        self.viewer_rect_item.setRect(scene_rect)

    # --- 交互逻辑：点击缩略图移动主画布 ---
    def mousePressEvent(self, event):
        self._pan_to_pos(event.pos())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & QtCore.Qt.LeftButton:
            self._pan_to_pos(event.pos())
        super().mouseMoveEvent(event)

    def _pan_to_pos(self, pos):
        # 将缩略图上的点击位置映射回场景坐标
        scene_pos = self.mapToScene(pos)
        # 让主画布中心移动到该场景坐标
        self.target_viewer.centerOn(scene_pos)