# -*- coding: utf-8 -*-
from typing import List

from PyQt5.QtCore import pyqtSignal, QSize, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QRadioButton,
)
from qfluentwidgets import (
    ToolButton,
    FluentIcon,
    PushButton,
    qconfig,
    ExpandSettingCard,
    ConfigItem,
    MessageBoxBase,
    LineEdit,
    Dialog,
    ConfigValidator,
    Theme,
    setTheme,
    MessageBox,
    ComboBox,
    PrimaryPushButton,
)


class ListValidator(ConfigValidator):
    """Folder list validator"""

    def validate(self, value):
        return True

    def correct(self, value: List[str]):
        return value


class FontItem(QWidget):
    """Font item with radio button for selection and remove button"""

    removed = pyqtSignal(QWidget)
    selected = pyqtSignal(QWidget)

    def __init__(self, font: str, is_selected: bool, parent=None):
        super().__init__(parent=parent)
        self.font = font
        self.hBoxLayout = QHBoxLayout(self)
        self.radioButton = QRadioButton(self)
        self.fontLabel = QLabel(font, self)
        self.removeButton = ToolButton(FluentIcon.CLOSE, self)

        self.removeButton.setFixedSize(39, 29)
        self.removeButton.setIconSize(QSize(12, 12))
        self.radioButton.setFixedSize(32, 29)

        self.setFixedHeight(53)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.hBoxLayout.setContentsMargins(48, 0, 60, 0)
        self.hBoxLayout.addWidget(self.radioButton, 0, Qt.AlignLeft)
        self.hBoxLayout.addWidget(self.fontLabel, 0, Qt.AlignLeft)
        self.hBoxLayout.addSpacing(16)
        self.hBoxLayout.addStretch(1)
        self.hBoxLayout.addWidget(self.removeButton, 0, Qt.AlignRight)
        self.hBoxLayout.setAlignment(Qt.AlignVCenter)

        self.fontLabel.setObjectName("titleLabel")
        self.radioButton.setChecked(is_selected)

        self.radioButton.setStyleSheet("""
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border-radius: 8px;
                border: 2px solid #8e8e8e;
                background-color: transparent;
            }
            QRadioButton::indicator:checked {
                border: 2px solid #0078d4;
                background-color: #0078d4;
            }
        """)

        self.removeButton.clicked.connect(lambda: self.removed.emit(self))
        self.radioButton.toggled.connect(
            lambda checked: self.selected.emit(self) if checked else None
        )


class FontListSettingCard(ExpandSettingCard):
    """Font list setting card with add, remove and select functionality"""

    fontChanged = pyqtSignal(list)
    fontSelectedChanged = pyqtSignal(str)

    def __init__(
        self,
        icon: QIcon,
        fontListItem: ConfigItem,
        fontSelectedItem: ConfigItem,
        title: str,
        content: str = None,
        parent=None,
        home=None,
    ):
        """
        Parameters
        ----------
        fontListItem: ConfigItem
            configuration item for font list

        fontSelectedItem: ConfigItem
            configuration item for selected font

        title: str
            the title of card

        content: str
            the content of card

        parent: QWidget
            parent widget
        """
        self.home = home
        super().__init__(icon, title, content, parent)
        self.title = title
        self.fontListItem = fontListItem
        self.fontSelectedItem = fontSelectedItem
        self.addFontButton = PushButton(self.tr("添加字体"), self, FluentIcon.ADD)

        self.fonts = qconfig.get(fontListItem).copy()
        self.currentFont = qconfig.get(fontSelectedItem)
        self.__initWidget()

    def __initWidget(self):
        self.addWidget(self.addFontButton)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setAlignment(Qt.AlignTop)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)

        self.headerLabel = QLabel(self.tr("当前字体: ") + self.currentFont, self.view)
        self.headerLabel.setObjectName("contentLabel")
        self.viewLayout.addWidget(self.headerLabel)

        for font in self.fonts:
            self.__addFontItem(font)

        self.addFontButton.clicked.connect(self.__showFontInputDialog)

    def __showFontInputDialog(self):
        """show font input dialog"""
        w = MessageBox(self.tr("添加字体"), "", self.home)
        w.contentLabel.hide()

        lineEdit = LineEdit(w)
        lineEdit.setFixedWidth(300)
        lineEdit.setPlaceholderText(self.tr("输入字体名称 (e.g., Microsoft YaHei)"))

        w.vBoxLayout.insertWidget(1, lineEdit, 0, Qt.AlignCenter)
        w.yesButton.setText(self.tr("保存"))
        w.cancelButton.setText(self.tr("取消"))

        if w.exec():
            font = lineEdit.text().strip()
            if font and font not in self.fonts:
                self.__addFontItem(font)
                self.fonts.append(font)
                qconfig.set(self.fontListItem, self.fonts)
                self.fontChanged.emit(self.fonts)

    def __addFontItem(self, font: str):
        """add font item"""
        is_selected = font == self.currentFont
        item = FontItem(font, is_selected, self.view)
        item.removed.connect(self.__showConfirmDialog)
        item.selected.connect(lambda i: self.__selectFont(i))
        self.viewLayout.addWidget(item)
        item.show()
        self._adjustViewSize()

    def __showConfirmDialog(self, item: FontItem):
        """show confirm dialog"""
        title = self.tr("确定要删除这个字体吗?")
        content = (
            self.tr('删除 "') + f"{item.font}" + self.tr('" 后将不再出现在列表中。')
        )
        w = Dialog(title, content, self.window())
        w.yesSignal.connect(lambda: self.__removeFont(item))
        w.exec_()

    def __removeFont(self, item: FontItem):
        """remove font"""
        if item.font not in self.fonts:
            return

        self.fonts.remove(item.font)
        self.viewLayout.removeWidget(item)
        item.deleteLater()
        self._adjustViewSize()

        self.fontChanged.emit(self.fonts)
        qconfig.set(self.fontListItem, self.fonts)

        if self.currentFont == item.font and self.fonts:
            self.__updateSelectedFont(self.fonts[0])

    def __selectFont(self, item: FontItem):
        """select font as current"""
        for i in range(self.viewLayout.count()):
            w = self.viewLayout.itemAt(i).widget()
            if isinstance(w, FontItem) and w != item:
                w.radioButton.setChecked(False)
        item.radioButton.setChecked(True)
        self.__updateSelectedFont(item.font)

    def __updateSelectedFont(self, font: str):
        """update selected font"""
        if font not in self.fonts:
            return

        self.currentFont = font
        qconfig.set(self.fontSelectedItem, font)
        qconfig.save()
        self.headerLabel.setText(self.tr("当前字体: ") + font)
        self.fontSelectedChanged.emit(font)


class PackageItem(QWidget):
    """Package item"""

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

        self.packageLabel.setObjectName("titleLabel")

        self.removeButton.clicked.connect(lambda: self.removed.emit(self))


class SkillItem(QWidget):
    """Skill item with enable switch"""

    enabled_changed = pyqtSignal(str, bool)

    def __init__(self, name: str, description: str, is_enabled: bool, parent=None):
        super().__init__(parent=parent)
        self.setStyleSheet("background-color: transparent;")
        self.name = name
        self.hBoxLayout = QHBoxLayout(self)
        self.nameLabel = QLabel(name, self)
        self.descLabel = QLabel(description, self)
        from qfluentwidgets import SwitchButton

        self.switch = SwitchButton(self)

        self.nameLabel.setFixedWidth(140)
        self.nameLabel.setObjectName("titleLabel")
        self.descLabel.setStyleSheet("color: #888888; font-size: 12px;")
        self.descLabel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.switch.setOnText("")
        self.switch.setOffText("")
        self.switch.setChecked(is_enabled)

        self.setFixedHeight(53)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.hBoxLayout.setContentsMargins(16, 0, 16, 0)
        self.hBoxLayout.addWidget(self.nameLabel, 0, Qt.AlignLeft)
        self.hBoxLayout.addWidget(self.descLabel, 1, Qt.AlignLeft)
        self.hBoxLayout.addWidget(self.switch, 0, Qt.AlignRight)
        self.hBoxLayout.setAlignment(Qt.AlignVCenter)

        self.switch.checkedChanged.connect(
            lambda checked: self.enabled_changed.emit(self.name, checked)
        )


class SkillListSettingCard(ExpandSettingCard):
    """Skill list setting card with enable/disable switches"""

    skillsChanged = pyqtSignal(list)

    def __init__(
        self,
        icon: QIcon,
        configItem: ConfigItem,
        title: str,
        content: str = None,
        parent=None,
        home=None,
    ):
        self.home = home
        super().__init__(icon, title, content, parent)
        self.title = title
        self.configItem = configItem
        self.enabled_skills = (
            qconfig.get(configItem).copy() if qconfig.get(configItem) else []
        )
        self._discover_skills()
        self.__initWidget()

    def _discover_skills(self):
        from pathlib import Path
        import yaml

        skills_dirs = [
            Path(__file__).parent.parent.parent
            / "llm_chatter"
            / "skills",
            Path.home() / ".agents" / "skills",
            Path("canvas_files") / "skills",
        ]

        self.all_skills = []
        seen_names = set()  # 按路径优先级去重，保留首次出现的同名技能
        for skills_dir in skills_dirs:
            if not skills_dir.exists():
                continue
            for skill_dir in skills_dir.iterdir():
                if not skill_dir.is_dir():
                    continue
                if skill_dir.name.startswith("_") or skill_dir.name.startswith("."):
                    continue

                skill_file = skill_dir / "SKILL.md"
                if not skill_file.exists():
                    skill_file = skill_dir / "skill.md"
                if not skill_file.exists():
                    continue

                try:
                    content = skill_file.read_text(encoding="utf-8")
                    name = skill_dir.name
                    description = ""

                    if content.startswith("---"):
                        try:
                            frontmatter = content.split("---", 2)[1]
                            meta = yaml.safe_load(frontmatter)
                            if meta:
                                name = meta.get("name", skill_dir.name)
                                description = meta.get("description", "")
                        except Exception:
                            pass

                    # 按优先级去重，保留 index 最小的同名技能
                    if name in seen_names:
                        continue
                    seen_names.add(name)

                    self.all_skills.append({"name": name, "description": description})
                except Exception:
                    continue

    def __initWidget(self):
        self.viewLayout.setSpacing(0)
        self.viewLayout.setAlignment(Qt.AlignTop)
        self.viewLayout.setContentsMargins(8, 0, 8, 0)

        self.refreshButton = PushButton("重新检测", self, FluentIcon.SYNC)
        self.refreshButton.setCursor(Qt.PointingHandCursor)
        self.refreshButton.clicked.connect(self._refresh_skills)
        self.addWidget(self.refreshButton)

        header_widget = QWidget(self.view)
        header_widget.setStyleSheet("background-color: transparent;")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(16, 8, 16, 8)

        header_title = QLabel("技能名称", header_widget)
        header_title.setFixedWidth(140)
        header_title.setStyleSheet(
            "color: #888888; font-size: 12px; font-weight: bold;"
        )

        header_desc = QLabel("描述", header_widget)
        header_desc.setStyleSheet("color: #888888; font-size: 12px; font-weight: bold;")

        header_state = QLabel("启用", header_widget)
        header_state.setFixedWidth(80)
        header_state.setStyleSheet(
            "color: #888888; font-size: 12px; font-weight: bold;"
        )
        header_state.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        header_layout.addWidget(header_title)
        header_layout.addWidget(header_desc, 1)
        header_layout.addWidget(header_state)

        self.viewLayout.addWidget(header_widget)

        for skill in self.all_skills:
            self._add_skill_item(skill["name"], skill["description"])

        self._adjustViewSize()

    def _refresh_skills(self):
        self._discover_skills()
        # 从后往前遍历，只移除 SkillItem 类型的 widgets
        for i in reversed(range(self.viewLayout.count())):
            item = self.viewLayout.itemAt(i)
            widget = item.widget()
            if isinstance(widget, SkillItem):
                self.viewLayout.removeItem(item)
                widget.deleteLater()
        for skill in self.all_skills:
            self._add_skill_item(skill["name"], skill["description"])
        self._adjustViewSize()

    def _add_skill_item(self, name: str, description: str):
        is_enabled = name in self.enabled_skills
        item = SkillItem(name, description, is_enabled, self.view)
        item.enabled_changed.connect(self._on_skill_enabled_changed)
        self.viewLayout.addWidget(item)
        item.show()
        self._adjustViewSize()

    def _on_skill_enabled_changed(self, name: str, enabled: bool):
        if enabled and name not in self.enabled_skills:
            self.enabled_skills.append(name)
        elif not enabled and name in self.enabled_skills:
            self.enabled_skills.remove(name)

        qconfig.set(self.configItem, self.enabled_skills)
        self.skillsChanged.emit(self.enabled_skills)


class PackageListSettingCard(ExpandSettingCard):
    """Package list setting card"""

    packageChanged = pyqtSignal(list)

    def __init__(
        self,
        icon: QIcon,
        configItem: ConfigItem,
        title: str,
        content: str = None,
        parent=None,
        home=None,
    ):
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
        self.title = title
        self.configItem = configItem
        self.addPackageButton = PushButton(self.tr("添加"), self, FluentIcon.ADD)

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
        """show package input dialog"""
        w = MessageBox(self.title, "", self.home)
        w.contentLabel.hide()

        lineEdit = LineEdit(w)
        lineEdit.setFixedWidth(300)
        lineEdit.setPlaceholderText(
            self.tr("Enter package name (e.g., requests, numpy==1.21.0)")
        )

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
        """add package item"""
        item = PackageItem(package, self.view)
        item.removed.connect(self.__showConfirmDialog)
        self.viewLayout.addWidget(item)
        item.show()
        self._adjustViewSize()

    def __showConfirmDialog(self, item: PackageItem):
        """show confirm dialog"""
        title = self.tr("Are you sure you want to remove the package?")
        content = (
            self.tr("If you remove the ")
            + f'"{item.package}"'
            + self.tr(" package from the list, it will no longer appear in the list.")
        )
        w = Dialog(title, content, self.window())
        w.yesSignal.connect(lambda: self.__removePackage(item))
        w.exec_()

    def __removePackage(self, item: PackageItem):
        """remove package"""
        if item.package not in self.packages:
            return

        self.packages.remove(item.package)
        self.viewLayout.removeWidget(item)
        item.deleteLater()
        self._adjustViewSize()

        self.packageChanged.emit(self.packages)
        qconfig.set(self.configItem, self.packages)
