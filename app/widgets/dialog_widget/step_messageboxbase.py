# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QWidget, QStackedWidget
from qfluentwidgets import FluentStyleSheet, PrimaryPushButton, SubtitleLabel, PushButton  # 导入 SubtitleLabel
from qfluentwidgets import MaskDialogBase


class StepMessageBoxBase(MaskDialogBase):
    """
    通用的步骤式对话框基类。
    包含一个按钮组（用于导航和操作），一个步骤指示器（可选），和一个堆叠布局用于放置不同步骤的页面。
    """
    current_step_changed = pyqtSignal(int, str)  # 发射当前步骤索引和名称

    def __init__(self, parent=None, steps=None):
        """
        Args:
            parent: 父窗口
            steps: 一个列表，包含步骤信息，例如 [{"name": "step1", "title": "步骤1标题"}, ...]
                   如果为 None，则不使用步骤指示器。
        """
        super().__init__(parent=parent)

        # 按钮组
        self.buttonGroup = QFrame(self.widget)
        self.nextButton = PrimaryPushButton(self.tr('下一步'), self.buttonGroup)
        self.nextButton.setFixedWidth(150)
        self.backButton = PushButton(self.tr('上一步'), self.buttonGroup)
        self.backButton.setFixedWidth(150)
        self.okButton = PrimaryPushButton(self.tr('确认'), self.buttonGroup)
        self.okButton.setFixedWidth(150)
        self.cancelButton = PushButton(self.tr('取消'), self.buttonGroup)
        self.cancelButton.setFixedWidth(150)

        # 布局
        self.vBoxLayout = QVBoxLayout(self.widget)
        self.viewLayout = QVBoxLayout()  # 用于放置内容页面
        self.buttonLayout = QHBoxLayout(self.buttonGroup)

        # 步骤相关
        self.steps = steps or []
        self.step_indicator = None
        # 创建一个专门用于放置步骤指示器的容器
        self.step_indicator_container = QFrame(self.widget)
        self.step_indicator_layout = QHBoxLayout(self.step_indicator_container)
        # 设置容器的边距，使其与 viewLayout 的边距协调
        self.step_indicator_layout.setContentsMargins(24, 10, 24, 0)  # 左右与 viewLayout 一致，上下根据需要调整
        self.step_indicator_layout.setSpacing(10)  # 根据需要调整

        # 页面容器
        self.page_stack = QStackedWidget(self.widget)

        # 当前步骤
        self._current_step_index = 0  # *修改点2: 确保在需要前初始化*

        self.__initWidget()

    def __initWidget(self):
        self.__setQss()
        self.__initLayout()

        self.setShadowEffect(60, (0, 10), QColor(0, 0, 0, 50))
        self.setMaskColor(QColor(0, 0, 0, 76))

        self.backButton.setAttribute(Qt.WA_LayoutUsesWidgetRect)
        self.nextButton.setAttribute(Qt.WA_LayoutUsesWidgetRect)
        self.okButton.setAttribute(Qt.WA_LayoutUsesWidgetRect)
        self.cancelButton.setAttribute(Qt.WA_LayoutUsesWidgetRect)

        self.okButton.setAttribute(Qt.WA_MacShowFocusRect, False)
        self.nextButton.setAttribute(Qt.WA_MacShowFocusRect, False)

        self.nextButton.setFocus()
        self.buttonGroup.setFixedHeight(81)

        # 连接信号
        self.nextButton.clicked.connect(self._on_next_clicked)
        self.backButton.clicked.connect(self._on_back_clicked)
        self.okButton.clicked.connect(self._on_ok_clicked)
        self.cancelButton.clicked.connect(self._on_cancel_clicked)

        # *修改点3: 在所有部件创建后，初始化步骤指示器和按钮状态*
        if self.steps:
            # 使用 SubtitleLabel 或普通 BodyLabel
            self.step_indicator = SubtitleLabel(self._format_steps_title(), self.step_indicator_container)
            # self.step_indicator = BodyLabel(self._format_steps_title(), self.step_indicator_container) # 也可以用 BodyLabel
            self.step_indicator_layout.addWidget(self.step_indicator)  # 添加到容器布局
            self._update_step_indicator()
        self._update_button_states()

    def __initLayout(self):
        self._hBoxLayout.removeWidget(self.widget)
        self._hBoxLayout.addWidget(self.widget, 1, Qt.AlignCenter)

        self.vBoxLayout.setSpacing(0)  # 主布局间距为0
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)  # 主布局边距为0

        # 将步骤指示器容器添加到主布局，位于 viewLayout 之前
        if self.steps:
            self.vBoxLayout.addWidget(self.step_indicator_container)

        # viewLayout 保持原有的边距和内容
        self.vBoxLayout.addLayout(self.viewLayout, 1)  # 步骤内容
        self.vBoxLayout.addWidget(self.buttonGroup, 0, Qt.AlignBottom)

        self.viewLayout.setSpacing(12)
        self.viewLayout.setContentsMargins(24, 24, 24, 24)  # 保持原有的边距
        self.viewLayout.addWidget(self.page_stack)  # 添加页面堆叠

        self.buttonLayout.setSpacing(12)
        self.buttonLayout.setContentsMargins(24, 24, 24, 24)
        self.buttonLayout.addWidget(self.backButton, 0, Qt.AlignLeft)
        self.buttonLayout.addStretch(1)  # 添加弹性空间
        self.buttonLayout.addWidget(self.cancelButton, 0)
        self.buttonLayout.addWidget(self.nextButton, 0)
        self.buttonLayout.addWidget(self.okButton, 0)

    def __setQss(self):
        self.buttonGroup.setObjectName('buttonGroup')
        self.cancelButton.setObjectName('cancelButton')
        self.backButton.setObjectName('backButton')
        self.nextButton.setObjectName('nextButton')
        self.okButton.setObjectName('okButton')
        # 为步骤指示器容器设置对象名以便 QSS 定制
        if self.steps:
            self.step_indicator_container.setObjectName('stepIndicatorContainer')
            # self.step_indicator.setObjectName("stepIndicatorLabel") # 如果需要单独定制 label 样式
        FluentStyleSheet.DIALOG.apply(self)
        # *修改点5: 只有在存在指示器时才设置对象名和应用样式*
        # QSS 已通过 FluentStyleSheet.DIALOG.apply 应用，可以通过 objectName 定制

    def add_page(self, page_widget: QWidget):
        """向堆叠布局中添加一个步骤页面"""
        self.page_stack.addWidget(page_widget)

    def current_step_index(self):
        """获取当前步骤的索引"""
        return self._current_step_index

    def current_step_name(self):
        """获取当前步骤的名称（如果定义了步骤）"""
        if 0 <= self._current_step_index < len(self.steps):
            return self.steps[self._current_step_index].get("name", f"Step {self._current_step_index + 1}")
        return f"步骤 {self._current_step_index + 1}"

    def _format_steps_title(self):
        """格式化步骤标题字符串"""
        if not self.steps:
            return "Steps"
        titles = [step.get("title", step.get("name", f"Step {i + 1}")) for i, step in enumerate(self.steps)]
        current_title = titles[self._current_step_index] if 0 <= self._current_step_index < len(titles) else "Unknown"
        return f"步骤 {self._current_step_index + 1}/{len(titles)}: {current_title}"

    def _update_step_indicator(self):
        """更新步骤指示器的文本"""
        if self.step_indicator:
            self.step_indicator.setText(self._format_steps_title())

    def _update_button_states(self):
        """根据当前步骤更新按钮的可见性和启用状态"""
        total_steps = self.page_stack.count()

        # Back 按钮：非第一步时可见
        self.backButton.setVisible(self._current_step_index > 0)

        # Next 按钮：非最后一步时可见
        self.nextButton.setVisible(self._current_step_index < total_steps - 1)

        # OK 按钮：最后一步时可见
        self.okButton.setVisible(self._current_step_index == total_steps - 1)

        # 更新步骤指示器
        self._update_step_indicator()

        # 发射信号
        self.current_step_changed.emit(self._current_step_index, self.current_step_name())

    def _on_next_clicked(self):
        """处理下一步按钮点击"""
        if self._current_step_index < self.page_stack.count() - 1:
            # 这里可以添加验证逻辑，例如 self.validate_current_step()
            # if not self.validate_current_step():
            #     return # 阻止前进
            self._current_step_index += 1
            self.page_stack.setCurrentIndex(self._current_step_index)
            self._update_button_states()

    def _on_back_clicked(self):
        """处理上一步按钮点击"""
        if self._current_step_index > 0:
            self._current_step_index -= 1
            self.page_stack.setCurrentIndex(self._current_step_index)
            self._update_button_states()

    def _on_ok_clicked(self):
        """处理确定按钮点击"""
        # 这里可以添加最终验证逻辑
        # if not self.validate_final_data():
        #     return # 阻止关闭
        self.accept()

    def _on_cancel_clicked(self):
        """处理取消按钮点击"""
        self.reject()

    # --- 可重写方法 ---
    def validate_current_step(self) -> bool:
        """
        验证当前步骤的数据是否合法，以决定是否可以进入下一步。
        子类可以重写此方法。
        """
        return True

    def validate_final_data(self) -> bool:
        """
        验证最终数据是否合法，以决定是否可以关闭对话框。
        子类可以重写此方法。
        """
        return True
