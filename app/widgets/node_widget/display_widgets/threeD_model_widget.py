# -*- coding: utf-8 -*-
import os

from qtpy import QtWidgets, QtCore

try:
    from PyQt5.Qt3DExtras import Qt3DWindow, QFirstPersonCameraController, QForwardRenderer, QOrbitCameraController
    from PyQt5.Qt3DCore import QEntity, QTransform
    from PyQt5.Qt3DRender import QMesh
    from PyQt5.QtGui import QVector3D, QColor

    HAS_3D = True
except ImportError:
    HAS_3D = False


class Model3DWidget(QtWidgets.QWidget):
    sizeHintChanged = QtCore.Signal()

    def __init__(self, parent=None, node=None):
        super().__init__(parent)
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        if not HAS_3D:
            self.layout.addWidget(QtWidgets.QLabel("Qt3D Not Installed"))
            return

        self.view = Qt3DWindow()
        self.container = self.createWindowContainer(self.view)
        self.layout.addWidget(self.container)

        # 基础场景设置
        self.root_entity = QEntity()
        self.view.setRootEntity(self.root_entity)
        self.view.defaultFrameGraph().setClearColor(QColor(40, 40, 40))

        # 摄像机控制
        self.camera = self.view.camera()
        self.camera.lens().setPerspectiveProjection(45.0, 16.0 / 9.0, 0.1, 1000.0)
        self.camera.setPosition(QVector3D(0, 0, 10.0))
        self.camera.setViewCenter(QVector3D(0, 0, 0))

        self.cam_controller = QOrbitCameraController(self.root_entity)
        self.cam_controller.setCamera(self.camera)

    def set_value(self, path):
        if not HAS_3D or not path or not os.path.exists(path):
            return

        # 清除旧模型并加载新模型
        self.mesh = QMesh()
        self.mesh.setSource(QtCore.QUrl.fromLocalFile(path))

        self.mesh_entity = QEntity(self.root_entity)
        self.mesh_entity.addComponent(self.mesh)
        # 这里还可以添加材质 (QMaterial)

        self.sizeHintChanged.emit()

    def sizeHint(self):
        return QtCore.QSize(300, 300)