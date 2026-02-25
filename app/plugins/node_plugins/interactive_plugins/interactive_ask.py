# -*- coding: utf-8 -*-
import os
from typing import Any, Dict

from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QScrollArea,
    QFormLayout,
    QWidget,
    QDialog,
    QSizePolicy,
    QHBoxLayout,
    QVBoxLayout,
    QFrame,
    QFileDialog,
)
from qfluentwidgets import (
    MessageBoxBase,
    SubtitleLabel,
    BodyLabel,
    ComboBox,
    DoubleSpinBox,
    SpinBox,
    LineEdit,
    TextEdit,
    SwitchButton,
    TransparentToolButton,
    CaptionLabel,
    StrongBodyLabel,
    SmoothScrollArea,
)

from app.plugins.node_plugins.base import InteractivePlugin
from app.utils.utils import get_icon

# 模拟 SSHRemoteFileDialog，如果没有则定义为空
try:
    from app.widgets.dialog_widget.ssh_remote_file_dialog import SSHRemoteFileDialog
except ImportError:
    SSHRemoteFileDialog = None


# ==============================================================================
# 1. 优化后的文件选择控件
# ==============================================================================
class FileSelectWidget(QFrame):
    """优化后的文件选择控件：增加边框反馈和更好的布局"""

    valueChanged = pyqtSignal(str)

    def __init__(self, parent=None, default_ext="", is_remote=False):
        super().__init__(parent)
        self._path = ""
        self._is_folder_mode = default_ext.lower() == "folder"
        self.is_remote = is_remote

        # 设置样式
        self.setObjectName("FileSelectWidget")
        self.setStyleSheet("""
            #FileSelectWidget {
                color: white;
                border: 1px solid rgba(0, 0, 0, 15);
                border-radius: 6px;
                background-color: rgba(255, 255, 255, 10);
            }
            #FileSelectWidget:hover {
                border: 1px solid rgba(0, 0, 0, 30);
                background-color: rgba(255, 255, 255, 20);
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        # 输入框：移除边框以嵌入容器
        self.path_edit = LineEdit(self)
        self.path_edit.setPlaceholderText(
            self.tr("选择文件夹...") if self._is_folder_mode else self.tr("选择文件...")
        )
        self.path_edit.setStyleSheet(
            "LineEdit { border: none; background: transparent; color: white}"
        )
        self.path_edit.textChanged.connect(self._on_text_changed)

        # 清空按钮
        self.btn_clear = TransparentToolButton(get_icon("清空参数"), self)
        self.btn_clear.setFixedSize(28, 28)
        self.btn_clear.setToolTip(self.tr("清空"))
        self.btn_clear.clicked.connect(lambda: self.set_value(""))
        self.btn_clear.setVisible(False)

        # 浏览按钮
        icon_name = "文件夹" if self._is_folder_mode else "文件选择"
        self.btn_browse = TransparentToolButton(get_icon(icon_name), self)
        self.btn_browse.setFixedSize(28, 28)
        self.btn_browse.clicked.connect(self._handle_browse)

        layout.addWidget(self.path_edit)
        layout.addWidget(self.btn_clear)
        layout.addWidget(self.btn_browse)

    def _handle_browse(self):
        # 逻辑保持不变，但增加 UI 反馈
        main_win = self.window()
        env_data = getattr(main_win, "env_data", {})
        is_ssh = env_data.get("type") == "ssh"

        if is_ssh and SSHRemoteFileDialog:
            dialog = SSHRemoteFileDialog(
                env_data=env_data,
                selection_mode="folder" if self._is_folder_mode else "file",
                parent=main_win,
            )
            if dialog.exec_() == QDialog.Accepted:
                self.set_value(dialog.get_selected_result())
        else:
            if self._is_folder_mode:
                path = QFileDialog.getExistingDirectory(
                    self, "选择目录", self._path or os.getcwd()
                )
            else:
                path, _ = QFileDialog.getOpenFileName(
                    self, "选择文件", self._path or os.getcwd()
                )
            if path:
                self.set_value(path)

    def _on_text_changed(self, text):
        self._path = text
        self.btn_clear.setVisible(bool(text))
        self.valueChanged.emit(text)

    def set_value(self, value):
        self.path_edit.setText(value or "")
        self.path_edit.setCursorPosition(len(value or ""))

    def get_value(self):
        return self.path_edit.text()


# ==============================================================================
# 2. 优化后的干预对话框
# ==============================================================================
class InterventionDialog(MessageBoxBase):
    """
    自适应动态表单对话框
    优化点：使用了 StrongBodyLabel，增加了 HelpText 支持，优化了滚动区域，支持必填项标记
    """

    def __init__(
        self, title: str, message: str, schema: dict, main_window=None, parent=None
    ):
        super().__init__(parent)
        self.schema = schema
        self.main_window = main_window or parent
        self.field_widgets: Dict[str, Any] = {}

        # 1. 头部美化
        self.titleLabel = SubtitleLabel(title)
        self.viewLayout.addWidget(self.titleLabel)

        if message:
            self.msgLabel = BodyLabel(message)
            self.msgLabel.setTextColor(QColor(100, 100, 100))
            self.msgLabel.setWordWrap(True)
            self.viewLayout.addWidget(self.msgLabel)

        self.viewLayout.addSpacing(10)

        # 2. 使用平滑滚动区域
        self.scroll_area = SmoothScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.viewport().setStyleSheet("background-color: transparent;")

        self.container = QWidget()
        self.form_layout = QFormLayout(self.container)
        self.form_layout.setContentsMargins(0, 0, 15, 0)
        self.form_layout.setSpacing(15)
        self.form_layout.setLabelAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.scroll_area.setWidget(self.container)
        self.viewLayout.addWidget(self.scroll_area)

        # 3. 动态构建
        self._build_form()

        # 4. 设置窗口
        self.widget.setMinimumWidth(650)
        self.widget.setMaximumHeight(800)

    def _build_form(self):
        for field_id, info in self.schema.items():
            label_text = info.get("label", field_id)
            is_required = info.get("required", False)
            description = info.get("description", "")

            # 创建标签容器（支持必填星号和描述文字）
            label_container = QWidget()
            label_vbox = QVBoxLayout(label_container)
            label_vbox.setContentsMargins(0, 4, 0, 0)
            label_vbox.setSpacing(2)

            display_name = f"{label_text} *" if is_required else label_text
            field_label = StrongBodyLabel(display_name)
            label_vbox.addWidget(field_label)

            if description:
                desc_label = CaptionLabel(description)
                desc_label.setTextColor(QColor(120, 120, 120))
                desc_label.setWordWrap(True)
                label_vbox.addWidget(desc_label)

            # 创建控件
            widget = self._create_control(field_id, info)
            self.field_widgets[field_id] = widget

            self.form_layout.addRow(label_container, widget)

    def _create_control(self, field_id, info) -> QWidget:
        t = info.get("type", "text")
        default = info.get("default")

        if t == "file":
            w = FileSelectWidget(default_ext=info.get("ext", ""))
            w.set_value(str(default) if default else "")
            return w

        elif t == "choice":
            w = ComboBox()
            w.addItems(info.get("choices", []))
            if default:
                w.setCurrentText(str(default))
            w.setMinimumWidth(200)
            return w

        elif t == "bool":
            w = SwitchButton()
            w.setChecked(bool(default))
            # 让开关居左显示，不填满行
            container = QWidget()
            h_layout = QHBoxLayout(container)
            h_layout.setContentsMargins(0, 0, 0, 0)
            h_layout.addWidget(w)
            h_layout.addStretch()
            # 存入 widget 引用，方便取值
            container.inner_widget = w
            return container

        elif t == "int" or t == "float":
            w = SpinBox() if t == "int" else DoubleSpinBox()
            w.setRange(info.get("min", -999999), info.get("max", 999999))
            if t == "float":
                w.setDecimals(info.get("decimals", 2))
            w.setValue(default if default is not None else 0)
            w.setMinimumWidth(150)
            return w

        elif t == "long_text":
            w = TextEdit()
            w.setPlaceholderText(info.get("placeholder", ""))
            w.setText(str(default) if default else "")
            w.setFixedHeight(100)
            return w

        else:  # text
            w = LineEdit()
            w.setPlaceholderText(info.get("placeholder", ""))
            w.setText(str(default) if default else "")
            return w

    def get_result(self) -> Dict[str, Any]:
        res = {}
        for fid, widget in self.field_widgets.items():
            # 提取逻辑优化
            if isinstance(widget, FileSelectWidget):
                val = widget.get_value()
            elif hasattr(widget, "inner_widget"):  # 处理带容器的 SwitchButton
                val = widget.inner_widget.isChecked()
            elif isinstance(widget, ComboBox):
                val = widget.currentText()
            elif isinstance(widget, (SpinBox, DoubleSpinBox)):
                val = widget.value()
            elif isinstance(widget, TextEdit):
                val = widget.toPlainText()
            elif isinstance(widget, LineEdit):
                val = widget.text()
            else:
                val = None
            res[fid] = val
        return res


# ==============================================================================
# 3. 插件定义
# ==============================================================================
class AskPlugin(InteractivePlugin):
    plugin_id = "ask_user"
    plugin_name = "人工干预"
    plugin_desc = "将节点中的指定信息发送给 UI 侧用于人工确认和修改（支持文件选择）"

    plugin_template = """result = self.emit_interactive_message(
    method="ask_user",
    params={
        "title": "数据核对与修正", 
        "message": "请核对以下解析结果，如有错误请修正后继续。",
        "schema": {
            "output_path": {"type": "file", "label": "输出文件路径", "ext": ".txt", "default": "/data/output/result.txt"},
            "is_correct": {"type": "bool", "label": "确认无误", "default": True},
            "confidence": {"type": "float", "label": "置信度", "default": 0.95, "min": 0.0, "max": 1.0},
            "category": {"type": "choice", "label": "分类", "choices": ["A 类", "B 类", "C 类"], "default": "A 类"},
            "count": {"type": "int", "label": "数量", "default": 1, "min": 0},
            "remark": {"type": "text", "label": "备注说明", "default": ""},
            "detail_log": {"type": "long_text", "label": "详细日志", "default": ""}
        }
    }
)
"""

    def operate(self, node, params, msg=None):
        title = params.get("title", "人工干预")
        message = params.get("message", "")
        schema = params.get("schema", {})

        # 获取主窗口引用 (关键：FileSelectWidget 需要它来访问 env_data)
        parent_window = getattr(node, "parent_window", None)

        # 创建对话框 - 同时传递 parent 和 main_window
        dialog = InterventionDialog(
            title, message, schema, main_window=parent_window, parent=parent_window
        )

        # 自定义按钮文本
        dialog.yesButton.setText("确认提交")
        dialog.cancelButton.setText("取消")

        # 显示对话框并等待结果
        if dialog.exec_() == QDialog.Accepted:
            return dialog.get_result()
        else:
            # 用户取消或关闭对话框
            return None
