# -*- coding: utf-8 -*-
import os
from typing import Any, Dict

from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtWidgets import (QScrollArea, QFormLayout, QWidget, QDialog,
                             QSizePolicy, QHBoxLayout, QFileDialog)
from qfluentwidgets import (MessageBoxBase, SubtitleLabel, BodyLabel, ComboBox,
                            DoubleSpinBox, SpinBox, LineEdit, TextEdit,
                            SwitchButton, TransparentToolButton)

from app.plugins.node_plugins.base import InteractivePlugin
from app.utils.utils import get_icon
from app.widgets.dialog_widget.ssh_remote_file_dialog import SSHRemoteFileDialog


# ==============================================================================
# 1. 文件选择控件
# ==============================================================================
class FileSelectWidget(QWidget):
    """文件/文件夹选择控件，支持本地和 SSH 远程模式"""
    valueChanged = pyqtSignal(str)
    fixed_height = True

    def __init__(self, parent=None, default_ext="", get_port_func=None):
        super().__init__(parent)
        # parent 应为主窗口，用于获取 env_data 和 global_variables
        self.main_window = parent
        self._path = ""
        self._is_folder_mode = default_ext.lower() == "folder"

        self._file_filter = "All Files (*)"
        if not self._is_folder_mode and default_ext:
            ext = default_ext if default_ext.startswith('.') else f".{default_ext}"
            clean_ext = ext.replace('.', '')
            self._file_filter = f"{clean_ext.upper()} Files (*{ext});;All Files (*)"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 获取全局变量支持
        gv = getattr(self.main_window, 'global_variables', None) if self.main_window else None

        # 创建输入框
        self.path_edit = LineEdit(self)

        self.path_edit.textChanged.connect(self._on_text_changed)
        self.path_edit.setMinimumWidth(180)
        placeholder = "选择文件夹..." if self._is_folder_mode else "选择文件..."
        self.path_edit.setPlaceholderText(placeholder)

        # 清空按钮
        self.btn_clear = TransparentToolButton(get_icon("清空参数") if get_icon else None)
        self.btn_clear.setToolTip("清空路径")
        self.btn_clear.setFixedSize(32, 32)
        self.btn_clear.clicked.connect(self._on_clear)
        self.btn_clear.setVisible(False)

        # 浏览按钮
        self.btn_browse = TransparentToolButton(get_icon("文件选择") if get_icon else None)
        self.btn_browse.setIconSize(QSize(30, 30))
        self.btn_browse.setFixedSize(32, 32)
        self.btn_browse.setToolTip(placeholder)
        self.btn_browse.clicked.connect(self._on_browse)

        layout.addWidget(self.path_edit)
        layout.addWidget(self.btn_clear)
        layout.addWidget(self.btn_browse)

    def _on_browse(self):
        """核心逻辑：判断是本地还是远程"""
        if not self.main_window:
            return

        env_data = getattr(self.main_window, "env_data", {})
        is_ssh = env_data.get("type") == "ssh"

        # SSH 远程模式
        if is_ssh and SSHRemoteFileDialog:
            if not self._is_folder_mode:
                path = os.path.dirname(self._path) if self._path else ""
            else:
                path = self._path

            dialog = SSHRemoteFileDialog(
                env_data=env_data,
                selection_mode="folder" if self._is_folder_mode else "file",
                file_filter=self._file_filter,
                parent=self.main_window,
                initial_path=path
            )
            if dialog.exec_() == QDialog.Accepted:
                path = dialog.get_selected_result()
                if path:
                    self.set_value(path)
                    self.valueChanged.emit(path)
        else:
            # 本地模式
            start_dir = ""
            if self._path:
                if os.path.isdir(self._path):
                    start_dir = self._path
                elif os.path.isfile(self._path):
                    start_dir = os.path.dirname(self._path)
            if not start_dir:
                start_dir = os.getcwd()

            if self._is_folder_mode:
                dir_path = QFileDialog.getExistingDirectory(
                    self.main_window, "选择目录", start_dir,
                    QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
                )
                if dir_path:
                    self.set_value(dir_path)
                    self.valueChanged.emit(dir_path)
            else:
                file_path, _ = QFileDialog.getOpenFileName(
                    self.main_window, "选择文件", start_dir, self._file_filter
                )
                if file_path:
                    self.set_value(file_path)
                    self.valueChanged.emit(file_path)

    def _on_clear(self):
        self.set_value("")
        self.valueChanged.emit("")

    def _on_text_changed(self, text):
        self._path = text
        self.valueChanged.emit(text)

    def get_value(self):
        return self._path

    def set_value(self, value):
        self._path = value or ""
        self.path_edit.setText(self._path)
        if self._path:
            self.path_edit.setCursorPosition(len(self._path))
        self.btn_clear.setVisible(bool(self._path))

    def sizeHint(self):
        return QSize(240, 30)


# ==============================================================================
# 2. 干预对话框 (支持文件选择)
# ==============================================================================
class InterventionDialog(MessageBoxBase):
    """
    自适应动态表单对话框，用于人工干预
    优化点：支持滚动、表单布局、文件选择、数据校验
    """

    def __init__(self, title: str, message: str, schema: dict, main_window=None, parent=None):
        super().__init__(parent)
        self.schema = schema or {}
        # main_window 用于 FileSelectWidget 访问 env_data 和 global_variables
        self.main_window = main_window or parent
        self.field_widgets: Dict[str, Any] = {}
        self.field_types: Dict[str, str] = {}

        # 1. 标题
        self.titleLabel = SubtitleLabel(title)
        self.titleLabel.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        self.viewLayout.addWidget(self.titleLabel)

        # 2. 提示信息
        if message:
            self.messageLabel = BodyLabel(message)
            self.messageLabel.setWordWrap(True)
            self.messageLabel.setStyleSheet("margin-bottom: 15px;")
            self.viewLayout.addWidget(self.messageLabel)

        # 3. 滚动区域容器
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.form_container = QWidget()
        self.form_layout = QFormLayout()
        self.form_layout.setSpacing(5)
        self.form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.form_container.setLayout(self.form_layout)

        self.scroll_area.setWidget(self.form_container)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.viewport().setStyleSheet("background-color: transparent;")
        self.scroll_area.setStyleSheet("""
            QScrollArea { background-color: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 6px; margin-right: 2px; }
            QScrollBar::handle:vertical { background: rgba(120, 120, 120, 150); border-radius: 4px; }
            QScrollBar::add-line, QScrollBar::sub-line { height: 0px; }
        """)
        self.viewLayout.addWidget(self.scroll_area)

        # 4. 动态生成表单
        self._setup_dynamic_form()

        # 5. 对话框尺寸
        self.widget.setMinimumWidth(600)

    def _setup_dynamic_form(self):
        """根据 schema 动态创建表单控件"""
        for field_name, prop_def in self.schema.items():
            if not isinstance(prop_def, dict):
                continue

            label_text = prop_def.get("label", field_name)
            prop_type = prop_def.get("type", "text")
            default = prop_def.get("default")
            required = prop_def.get("required", False)

            if required:
                label_text += " *"

            # 文件选择控件需要 main_window 作为 parent 以访问 env_data
            widget_parent = self.main_window if prop_type == "file" else self
            widget = self._create_widget_by_type(prop_type, prop_def, default, parent=widget_parent)

            self.field_widgets[field_name] = widget
            self.field_types[field_name] = prop_type
            self.form_layout.addRow(label_text, widget)

    def _create_widget_by_type(self, prop_type: str, prop_def: dict, default: Any, parent=None) -> QWidget:
        """工厂方法：根据类型创建对应的 Fluent 控件"""

        # 文件选择类型
        if prop_type == "file":
            ext = prop_def.get("ext", "")
            widget = FileSelectWidget(parent=parent, default_ext=ext)
            if default:
                widget.set_value(str(default))
            return widget

        # 布尔型 -> 开关
        elif prop_type == "bool":
            widget = SwitchButton()
            widget.setChecked(bool(default) if default is not None else False)
            return widget

        # 选择型 -> 下拉框
        elif prop_type == "choice":
            widget = ComboBox()
            choices = prop_def.get("choices", [])
            widget.addItems(choices)
            if default and default in choices:
                widget.setCurrentText(default)
            elif choices:
                widget.setCurrentIndex(0)
            return widget

        # 数值型 -> 数字输入框
        elif prop_type == "int":
            widget = SpinBox()
            min_val = int(prop_def.get("min", -2147483648))
            max_val = int(prop_def.get("max", 2147483647))
            widget.setRange(min_val, max_val)
            widget.setValue(int(default) if default is not None else 0)
            return widget

        elif prop_type == "float":
            widget = DoubleSpinBox()
            min_val = float(prop_def.get("min", -1e9))
            max_val = float(prop_def.get("max", 1e9))
            widget.setRange(min_val, max_val)
            widget.setDecimals(prop_def.get("decimals", 2))
            widget.setValue(float(default) if default is not None else 0.0)
            return widget

        # 多行文本 -> TextEdit
        elif prop_type == "long_text":
            widget = TextEdit()
            widget.setPlaceholderText("请输入详细内容...")
            widget.setText(str(default) if default is not None else "")
            widget.setMaximumHeight(150)
            return widget

        # 默认单行文本 -> LineEdit
        else:
            widget = LineEdit()
            widget.setPlaceholderText(f"请输入{prop_def.get('label')}")
            widget.setText(str(default) if default is not None else "")
            return widget

    def get_result(self) -> Dict[str, Any]:
        """解析所有控件的值并返回字典，进行类型转换"""
        result = {}
        for field_name, widget in self.field_widgets.items():
            prop_type = self.field_types.get(field_name, "text")
            val = None

            try:
                # 专门处理 FileSelectWidget
                if isinstance(widget, FileSelectWidget):
                    val = widget.get_value()
                elif isinstance(widget, SwitchButton):
                    val = widget.isChecked()
                elif isinstance(widget, ComboBox):
                    val = widget.currentText()
                elif isinstance(widget, (SpinBox, DoubleSpinBox)):
                    val = widget.value()
                elif isinstance(widget, TextEdit):
                    val = widget.toPlainText()
                elif isinstance(widget, LineEdit):
                    val = widget.text()
                else:
                    val = str(widget)
            except Exception as e:
                print(f"Error getting value for {field_name}: {e}")
                val = None

            # 类型转换
            if val is not None and val != "":
                if prop_type == "int":
                    try:
                        val = int(val)
                    except (ValueError, TypeError):
                        pass
                elif prop_type == "float":
                    try:
                        val = float(val)
                    except (ValueError, TypeError):
                        pass
                elif prop_type == "bool":
                    val = bool(val)

            result[field_name] = val

        return result


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
        parent_window = getattr(node, 'parent_window', None)

        # 创建对话框 - 同时传递 parent 和 main_window
        dialog = InterventionDialog(
            title, message, schema,
            main_window=parent_window,
            parent=parent_window
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