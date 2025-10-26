# -*- coding: utf-8 -*-
from typing import List

from PyQt5.QtCore import pyqtSignal, QSize, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QSizePolicy
from qfluentwidgets import ToolButton, FluentIcon, PushButton, qconfig, ExpandSettingCard, ConfigItem, MessageBoxBase, \
    LineEdit, Dialog, ConfigValidator, Theme, setTheme, MessageBox


class ListValidator(ConfigValidator):
    """ Folder list validator """

    def validate(self, value):
        return True

    def correct(self, value: List[str]):

        return value


class PackageItem(QWidget):
    """ Package item """

    removed = pyqtSignal(QWidget)

    def __init__(self, package: str, parent=None):
        super().__init__(parent=parent)
        self.package = package
        self.hBoxLayout = QHBoxLayout(self)
        self.packageLabel = QLabel(package, self)
        self.removeButton = ToolButton(FluentIcon.CLOSE, self)

        self.removeButton.setFixedSize(39, 29)
        self.removeButton.setIconSize(QSize(12, 12))

        self.setFixedHeight(53)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.hBoxLayout.setContentsMargins(48, 0, 60, 0)
        self.hBoxLayout.addWidget(self.packageLabel, 0, Qt.AlignLeft)
        self.hBoxLayout.addSpacing(16)
        self.hBoxLayout.addStretch(1)
        self.hBoxLayout.addWidget(self.removeButton, 0, Qt.AlignRight)
        self.hBoxLayout.setAlignment(Qt.AlignVCenter)

        # Set object name to apply theme-aware color style
        self.packageLabel.setObjectName('titleLabel')

        self.removeButton.clicked.connect(
            lambda: self.removed.emit(self))


class PackageListSettingCard(ExpandSettingCard):
    """ Package list setting card """

    packageChanged = pyqtSignal(list)

    def __init__(self, icon: QIcon, configItem: ConfigItem, title: str, content: str = None, parent=None, home=None):
        """
        Parameters
        ----------
        configItem: RangeConfigItem
            configuration item operated by the card

        title: str
            the title of card

        content: str
            the content of card

        parent: QWidget
            parent widget
        """
        self.home = home
        super().__init__(icon, title, content, parent)  # 使用书架图标表示包管理
        self.title= title
        self.configItem = configItem
        self.addPackageButton = PushButton(self.tr('添加'), self, FluentIcon.ADD)

        self.packages = qconfig.get(configItem).copy()  # type:List[str]
        self.__initWidget()

    def __initWidget(self):
        self.addWidget(self.addPackageButton)

        # initialize layout
        self.viewLayout.setSpacing(0)
        self.viewLayout.setAlignment(Qt.AlignTop)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        for package in self.packages:
            self.__addPackageItem(package)

        self.addPackageButton.clicked.connect(self.__showPackageInputDialog)

    def __showPackageInputDialog(self):
        """ show package input dialog """
        w = MessageBox(self.title, "", self.home)
        w.contentLabel.hide()

        lineEdit = LineEdit(w)
        lineEdit.setFixedWidth(300)
        lineEdit.setPlaceholderText(self.tr('Enter package name (e.g., requests, numpy==1.21.0)'))

        w.vBoxLayout.insertWidget(1, lineEdit, 0, Qt.AlignCenter)
        w.yesButton.setText("保存")
        w.cancelButton.setText("取消")

        if w.exec():
            package = lineEdit.text().strip()
            if package and package not in self.packages:
                self.__addPackageItem(package)
                self.packages.append(package)
                qconfig.set(self.configItem, self.packages)
                self.packageChanged.emit(self.packages)

    def __addPackageItem(self, package: str):
        """ add package item """
        item = PackageItem(package, self.view)
        item.removed.connect(self.__showConfirmDialog)
        self.viewLayout.addWidget(item)
        item.show()
        self._adjustViewSize()

    def __showConfirmDialog(self, item: PackageItem):
        """ show confirm dialog """
        title = self.tr('Are you sure you want to remove the package?')
        content = self.tr("If you remove the ") + f'"{item.package}"' + \
                  self.tr(" package from the list, it will no longer appear in the list.")
        w = Dialog(title, content, self.window())
        w.yesSignal.connect(lambda: self.__removePackage(item))
        w.exec_()

    def __removePackage(self, item: PackageItem):
        """ remove package """
        if item.package not in self.packages:
            return

        self.packages.remove(item.package)
        self.viewLayout.removeWidget(item)
        item.deleteLater()
        self._adjustViewSize()

        self.packageChanged.emit(self.packages)
        qconfig.set(self.configItem, self.packages)