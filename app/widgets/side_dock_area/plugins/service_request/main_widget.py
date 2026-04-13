# -*- coding: utf-8 -*-
import json
import os
import time
from PyQt5.QtCore import Qt, QThreadPool, QRegExp, QSize
from PyQt5.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat, QFont
from PyQt5.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
    QStackedWidget,
    QLabel,
    QSizePolicy,
    QTextEdit,
)
from qfluentwidgets import (
    LineEdit,
    SpinBox,
    DoubleSpinBox,
    CheckBox,
    SwitchButton,
    PrimaryPushButton,
    PushButton,
    BodyLabel,
    StrongBodyLabel,
    CardWidget,
    SegmentedWidget,
    InfoBar,
    InfoBarPosition,
    SmoothScrollArea,
    ToolButton,
    FluentIcon as FIF,
    TextEdit,
    ComboBox,
)

# 假设这些是你项目中的原有引用，保持不变
from app.widgets.dialog_widget.service_request_dialog import RequestWorker
from app.widgets.basic_widget.splitter import ModernSplitter
from app.widgets.side_dock_area.tool_window import (
    ToolWindow,
    DockPosition,
    DockCategory,
)
from app.utils.utils import get_icon


# --- JSON 语法高亮 (保持不变) ---
class JsonHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules = []
        fmt_key = QTextCharFormat()
        fmt_key.setForeground(QColor("#9CDCFE"))  # Key: Blue
        self.rules.append((QRegExp(r'"[^"\\]*":'), fmt_key))
        fmt_str = QTextCharFormat()
        fmt_str.setForeground(QColor("#CE9178"))  # String: Orange
        self.rules.append((QRegExp(r':\s*"[^"\\]*"'), fmt_str))
        fmt_num = QTextCharFormat()
        fmt_num.setForeground(QColor("#B5CEA8"))  # Number: Green
        self.rules.append((QRegExp(r":\s*-?\d+(\.\d+)?"), fmt_num))
        fmt_bool = QTextCharFormat()
        fmt_bool.setForeground(QColor("#569CD6"))  # Bool: Dark Blue
        self.rules.append((QRegExp(r":\s*(true|false|null)"), fmt_bool))

    def highlightBlock(self, text):
        for pattern, format in self.rules:
            expression = QRegExp(pattern)
            index = expression.indexIn(text)
            while index >= 0:
                length = expression.matchedLength()
                if expression.pattern().startswith(r":\s*"):
                    self.setFormat(
                        index + text[index:].find(text[index:].strip()[0]),
                        length,
                        format,
                    )
                else:
                    self.setFormat(index, length, format)
                index = expression.indexIn(text, index + length)


# --- 主工具类 ---
class ServiceTestTool(ToolWindow):
    name = "API 调试台"
    icon = get_icon("API测试")
    default_position = DockPosition.TOP
    CATEGORIES = [DockCategory.PROJECT]
    display_order = 20
    thread_pool = QThreadPool.globalInstance()

    def setup_ui(self):
        self.project_path = None
        self.service_url = None
        self.spec = {"inputs": {}}
        self.input_widgets = {}
        self.start_time = 0

        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # 1. 顶部地址栏 (精简版)
        self._init_top_bar(main_layout)

        # 2. 中间分割区域
        self.splitter = ModernSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter)

        # === 左侧：请求构建区 (Input) ===
        self.left_container = QWidget()
        self.left_layout = QVBoxLayout(self.left_container)
        self.left_layout.setContentsMargins(0, 0, 10, 0)
        self.left_layout.setSpacing(8)

        # 模式切换 Tabs (表单 vs JSON)
        self.input_mode_tabs = SegmentedWidget()
        self.input_mode_tabs.addItem("Json", "JSON 编辑")
        self.input_mode_tabs.addItem("Form", "表单填写")
        self.input_mode_tabs.setCurrentItem("Form")
        self.input_mode_tabs.currentItemChanged.connect(self._on_input_mode_changed)
        self.left_layout.addWidget(self.input_mode_tabs)

        # 堆叠窗口，用于切换不同视图
        self.input_stack = QStackedWidget()

        # --- Page 1: 表单模式 ---
        self.form_page = QWidget()
        form_layout = QVBoxLayout(self.form_page)
        form_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = SmoothScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("border: none; background: transparent;")
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setAlignment(Qt.AlignTop)
        self.scroll_layout.setSpacing(10)
        self.scroll_content.setLayout(self.scroll_layout)
        self.scroll_area.setWidget(self.scroll_content)
        form_layout.addWidget(self.scroll_area)

        # --- Page 2: JSON 模式 ---
        self.json_page = QWidget()
        json_layout = QVBoxLayout(self.json_page)
        json_layout.setContentsMargins(0, 0, 0, 0)

        # JSON 工具栏
        json_tools = QHBoxLayout()
        self.btn_format = PushButton("格式化")
        self.btn_format.setCursor(Qt.PointingHandCursor)
        self.btn_format.clicked.connect(self._format_json_input)
        self.btn_compact = PushButton("压缩")
        self.btn_compact.setCursor(Qt.PointingHandCursor)
        self.btn_compact.clicked.connect(self._compact_json_input)
        json_tools.addWidget(self.btn_format)
        json_tools.addWidget(self.btn_compact)
        json_tools.addStretch()

        # JSON 编辑器
        self.json_edit = TextEdit()
        self.json_edit.setPlaceholderText("在此处输入或粘贴 JSON Payload...")
        self.json_edit.setFont(QFont("Consolas", 10))
        self.json_highlighter = JsonHighlighter(self.json_edit.document())
        self.json_edit.setStyleSheet("""
            QTextEdit {
                background-color: #202020;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
                padding: 8px;
            }
        """)

        json_layout.addLayout(json_tools)
        json_layout.addWidget(self.json_edit)

        # 添加到 Stack
        self.input_stack.addWidget(self.form_page)  # index 0
        self.input_stack.addWidget(self.json_page)  # index 1

        self.left_layout.addWidget(self.input_stack)

        # === 右侧：响应结果区 (Output) ===
        self.right_container = QWidget()
        self.right_layout = QVBoxLayout(self.right_container)
        self.right_layout.setContentsMargins(10, 0, 0, 0)

        # 状态条
        top_res_layout = QHBoxLayout()
        title = StrongBodyLabel("Response")
        top_res_layout.addWidget(title)
        top_res_layout.addStretch()
        self.status_label = BodyLabel("Ready")
        self.status_label.setStyleSheet("color: #888;")
        top_res_layout.addWidget(self.status_label)
        self.right_layout.addLayout(top_res_layout)

        # 结果框
        self.result_text = TextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setFont(QFont("Consolas", 10))
        self.res_highlighter = JsonHighlighter(self.result_text.document())
        self.result_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #333;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        self.right_layout.addWidget(self.result_text)

        self.splitter.addWidget(self.left_container)
        self.splitter.addWidget(self.right_container)
        self.splitter.setSizes([350, 450])

        self._show_offline_message()

    def _init_top_bar(self, parent_layout):
        top_layout = QHBoxLayout()

        # POST 标签 (视觉强调)
        post_badge = QLabel("POST")
        post_badge.setStyleSheet("""
            QLabel {
                background-color: #FF9800;
                color: white;
                font-weight: bold;
                padding: 4px 10px;
                border-radius: 4px;
                font-size: 12px;
            }
        """)
        post_badge.setFixedSize(60, 32)
        post_badge.setAlignment(Qt.AlignCenter)
        top_layout.addWidget(post_badge)

        self.url_edit = LineEdit()
        self.url_edit.setPlaceholderText("服务地址 URL")
        self.url_edit.setReadOnly(
            True
        )  # 通常由refresh传入，设为只读避免误改，也可设为可写
        top_layout.addWidget(self.url_edit, 1)

        self.send_btn = PrimaryPushButton("发送请求")
        self.send_btn.setIcon(FIF.SEND_FILL)
        self.send_btn.setFixedWidth(120)
        self.send_btn.clicked.connect(self._send_request)
        top_layout.addWidget(self.send_btn)

        parent_layout.addLayout(top_layout)

    def _on_input_mode_changed(self, key):
        """切换输入模式时的逻辑"""
        if key == "Form":
            self.input_stack.setCurrentIndex(0)
            # 可选：从 JSON 解析回表单（比较复杂，这里暂不实现自动反向同步，
            # 或者是提示用户切换回表单会丢失 JSON 里的手动修改）
        else:
            # 切换到 JSON 模式：自动将表单数据同步过去
            form_data = self._get_data_from_form()
            self.json_edit.setPlainText(
                json.dumps(form_data, indent=4, ensure_ascii=False)
            )
            self.input_stack.setCurrentIndex(1)

    def _create_input_widget(self, key, cfg):
        """生成表单项，包含类型标签和输入框"""
        container = QWidget()
        container.setStyleSheet(
            "background-color: rgba(255, 255, 255, 0.03); border-radius: 6px;"
        )
        layout = QHBoxLayout(container)
        layout.setContentsMargins(12, 8, 12, 8)

        # 左侧：Key 和 类型提示
        v_layout = QVBoxLayout()
        v_layout.setSpacing(2)
        key_label = BodyLabel(key)
        key_label.setStyleSheet("font-weight: 600;")
        v_layout.addWidget(key_label)

        # 尝试推断类型
        val = cfg.get("current_value")
        type_str = "String"
        if isinstance(val, bool):
            type_str = "Boolean"
        elif isinstance(val, int):
            type_str = "Integer"
        elif isinstance(val, float):
            type_str = "Float"
        elif isinstance(val, (dict, list)):
            type_str = "Object/Array"

        type_label = QLabel(type_str)
        type_label.setStyleSheet("color: #666; font-size: 10px;")
        v_layout.addWidget(type_label)

        layout.addLayout(v_layout)
        layout.addStretch(1)

        # 右侧：控件
        widget = None
        if isinstance(val, bool):
            widget = SwitchButton()
            widget.setChecked(val)
            widget.setOnText("True")
            widget.setOffText("False")
        elif isinstance(val, int):
            widget = SpinBox()
            widget.setRange(-999999999, 999999999)
            widget.setValue(val)
            widget.setFixedWidth(140)
        elif isinstance(val, float):
            widget = DoubleSpinBox()
            widget.setRange(-1e9, 1e9)
            widget.setDecimals(4)
            widget.setValue(val)
            widget.setFixedWidth(140)
        else:
            widget = LineEdit()
            if isinstance(val, (dict, list)):
                widget.setText(json.dumps(val, ensure_ascii=False))
                widget.setPlaceholderText("JSON Object")
            else:
                widget.setText(str(val) if val is not None else "")
            widget.setFixedWidth(180)

        layout.addWidget(widget)
        self.input_widgets[key] = widget
        return container

    def refresh(self, project_path, service_url=None):
        self.project_path = project_path

        if service_url:
            self.service_url = service_url
            self.url_edit.setText(service_url)
            self.send_btn.setEnabled(True)
            self.status_label.setText("Idle")

            # 加载 Spec 生成表单
            self.spec = self._load_spec(project_path)
            self._clear_form()

            inputs = self.spec.get("inputs", {})
            if not inputs:
                self.scroll_layout.addWidget(BodyLabel("无参数"))
            else:
                for key, cfg in inputs.items():
                    w = self._create_input_widget(key, cfg)
                    self.scroll_layout.addWidget(w)

            self.scroll_layout.addStretch()

            # 默认切回表单模式，并初始化 JSON 视图
            self.input_mode_tabs.setCurrentItem("Form")
            # 预填充 JSON（方便用户直接点开看）
            self.json_edit.setPlainText(
                json.dumps(self._get_data_from_form(), indent=4, ensure_ascii=False)
            )

        else:
            self.service_url = None
            self._show_offline_message()

    def _get_data_from_form(self):
        """从表单控件提取数据"""
        payload = {}
        for key, widget in self.input_widgets.items():
            if isinstance(widget, (SwitchButton, CheckBox)):
                payload[key] = widget.isChecked()
            elif isinstance(widget, (SpinBox, DoubleSpinBox)):
                payload[key] = widget.value()
            elif isinstance(widget, LineEdit):
                text = widget.text().strip()
                # 尝试解析简单的 JSON 结构
                if text.startswith("{") or text.startswith("["):
                    try:
                        payload[key] = json.loads(text)
                    except:
                        payload[key] = text
                else:
                    payload[key] = text
        return payload

    def _get_current_payload(self):
        """根据当前 Tab 获取 Payload"""
        if self.input_mode_tabs.currentItem().text() == "表单填写":
            return self._get_data_from_form()
        else:
            # 从 JSON 编辑器获取
            try:
                text = self.json_edit.toPlainText()
                if not text.strip():
                    return {}
                return json.loads(text)
            except json.JSONDecodeError as e:
                raise ValueError(f"JSON 格式错误: {e}")

    def _format_json_input(self):
        try:
            text = self.json_edit.toPlainText()
            if text:
                obj = json.loads(text)
                self.json_edit.setPlainText(
                    json.dumps(obj, indent=4, ensure_ascii=False)
                )
        except:
            pass

    def _compact_json_input(self):
        try:
            text = self.json_edit.toPlainText()
            if text:
                obj = json.loads(text)
                self.json_edit.setPlainText(json.dumps(obj, ensure_ascii=False))
        except:
            pass

    def _send_request(self):
        if not self.service_url:
            return

        try:
            payload = self._get_current_payload()
        except ValueError as e:
            InfoBar.error(
                title="参数错误",
                content=str(e),
                position=InfoBarPosition.TOP,
                parent=self,
                duration=3000,
            )
            return

        self.send_btn.setEnabled(False)
        self.send_btn.setText("发送中...")
        self.status_label.setText("Sending...")
        self.start_time = time.time()

        # 强制更新一下 JSON 视图，确保两边一致（如果是在表单模式下发送）
        if self.input_mode_tabs.currentItem().text() == "表单填写":
            self.json_edit.setPlainText(
                json.dumps(payload, indent=4, ensure_ascii=False)
            )

        worker = RequestWorker(self.service_url, payload)
        worker.signals.success.connect(self._on_request_success)
        worker.signals.error.connect(self._on_request_error)
        self.thread_pool.start(worker)

    def _on_request_success(self, result):
        duration = (time.time() - self.start_time) * 1000
        self._restore_button()

        try:
            # 兼容 result 是字符串或字典的情况
            parsed = result if isinstance(result, (dict, list)) else json.loads(result)
            formatted = json.dumps(parsed, indent=4, ensure_ascii=False)
        except:
            formatted = str(result)

        self.result_text.setPlainText(formatted)

        # 假设 result 包含 status_code (如果 worker 只返回 body，可以只显示 200)
        status = getattr(result, "status_code", 200)
        color = "#198754" if 200 <= status < 300 else "#dc3545"
        self.status_label.setText(f"Status: {status} | Time: {duration:.0f}ms")
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")

    def _on_request_error(self, error_msg):
        self._restore_button()
        self.result_text.setPlainText(str(error_msg))
        self.status_label.setText("Error")
        self.status_label.setStyleSheet("color: #dc3545;")

    def _restore_button(self):
        self.send_btn.setEnabled(True)
        self.send_btn.setText("发送请求")

    def _clear_form(self):
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.input_widgets.clear()

    def _load_spec(self, project_path):
        # ... (保持原来的加载逻辑)
        spec_path = os.path.join(project_path, "project_spec.json")
        try:
            with open(spec_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {"inputs": {}}

    def _show_offline_message(self):
        self._clear_form()
        self.send_btn.setEnabled(False)
        self.url_edit.clear()
        self.result_text.clear()
        self.status_label.setText("Offline")
