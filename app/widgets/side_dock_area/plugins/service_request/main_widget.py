# -*- coding: utf-8 -*-
import json
import os

import requests
from PyQt5.QtCore import Qt, QObject, pyqtSignal, QThreadPool, QRunnable
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QWidget, QHBoxLayout, QFormLayout
from qfluentwidgets import (
    LineEdit, SpinBox, DoubleSpinBox, CheckBox,
    PrimaryPushButton, BodyLabel, StrongBodyLabel,
    CardWidget, VBoxLayout, TextEdit, setFont, SmoothScrollArea, SimpleCardWidget
)

from app.utils.utils import get_icon
from app.widgets.basic_widget.splitter import ModernSplitter
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition


class ServiceTestTool(ToolWindow):
    name = "项目服务测试"
    icon = get_icon("API测试")
    default_position = DockPosition.TOP  # ← 默认放在顶部
    _name_edit = None
    _category_edit = None
    _description_edit = None
    _requirements_edit = None
    _input_port_editor = None
    _output_port_editor = None
    _property_editor = None

    def setup_ui(self):
        info_layout = QVBoxLayout(self)
        info_layout.setContentsMargins(0, 0, 0, 0)
        # --- 基本信息卡片 ---
        basic_info_widget = SimpleCardWidget()
        basic_info_widget.setMinimumWidth(550)
        # 使用水平布局来并排放置信息和依赖
        basic_info_h_layout = QHBoxLayout(basic_info_widget)
        basic_info_h_layout.setContentsMargins(0, 0, 0, 0)  # 设置整体边距
        # 左侧：名称、分类、描述
        left_form_widget = QWidget(self)  # 容器用于左侧表单
        left_form_layout = QFormLayout(left_form_widget)
        self._name_edit = LineEdit()
        self._category_edit = LineEdit()
        self._description_edit = LineEdit()
        left_form_layout.addRow(BodyLabel("组件基本信息:"))
        left_form_layout.addRow(BodyLabel("组件名称:"), self._name_edit)
        left_form_layout.addRow(BodyLabel("组件分类:"), self._category_edit)
        left_form_layout.addRow(BodyLabel("组件描述:"), self._description_edit)
        # 右侧：依赖 requirements
        right_req_widget = QWidget(self)  # 容器用于右侧依赖
        right_req_layout = QVBoxLayout(right_req_widget)  # 垂直布局放标签和编辑器
        right_req_layout.addWidget(BodyLabel("组件依赖:"))  # 标签
        self._requirements_edit = TextEdit()  # 使用 qfluentwidgets 的 TextEdit
        self._requirements_edit.setFixedHeight(115)  # 设置固定高度，或使用 setMaximumHeight
        right_req_layout.addWidget(self._requirements_edit)  # 编辑器
        # 将左右两个容器添加到水平布局
        basic_info_h_layout.addWidget(left_form_widget)
        basic_info_h_layout.addWidget(right_req_widget)
        # 设置拉伸因子，让左侧稍微窄一些，右侧稍微宽一些，或者相等
        basic_info_h_layout.setStretch(0, 1)  # 左侧 (信息)
        basic_info_h_layout.setStretch(1, 1)  # 右侧 (依赖)
        info_layout.addWidget(basic_info_widget)


class RequestWorker(QRunnable):
    def __init__(self, url, payload, timeout=30):
        super().__init__()
        self.url = url
        self.payload = payload
        self.timeout = timeout
        self.signals = RequestSignals()

    def run(self):
        try:
            response = requests.post(self.url, json=self.payload, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
            self.signals.success.emit(result)
        except Exception as e:
            if isinstance(e, requests.exceptions.Timeout):
                msg = "请求超时，请检查网络或服务状态。"
            elif isinstance(e, requests.exceptions.ConnectionError):
                msg = "无法连接到服务，请确认服务是否运行。"
            elif isinstance(e, requests.exceptions.HTTPError):
                msg = f"HTTP 错误: {e.response.status_code} - {e.response.reason}"
            elif isinstance(e, ValueError):
                msg = "服务返回了无效的 JSON 格式。"
            else:
                msg = f"未知错误: {str(e)}"
            self.signals.error.emit(msg)


class RequestSignals(QObject):
    success = pyqtSignal(object)
    error = pyqtSignal(str)


class ServiceRequestWidget(QWidget):
    def __init__(self, project_path, service_url, parent=None):
        super().__init__(parent)
        self.project_path = project_path
        self.service_url = service_url
        self.spec = self._load_spec()
        self.input_widgets = {}
        self.thread_pool = QThreadPool.globalInstance()
        self._setup_ui()

    def _load_spec(self):
        spec_path = os.path.join(self.project_path, "project_spec.json")
        try:
            with open(spec_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {"inputs": {}}

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(16)

        splitter = ModernSplitter(Qt.Horizontal)

        # === 左侧：参数 ===
        left_frame = QFrame()
        left_frame.setStyleSheet("border: none; background: transparent;")
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        param_title = StrongBodyLabel("请求参数")
        setFont(param_title, 14)
        left_layout.addWidget(param_title)

        scroll_area = SmoothScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("border: none; background: transparent;")
        scroll_content = QWidget()
        scroll_layout = VBoxLayout(scroll_content)
        scroll_layout.setSpacing(12)
        scroll_layout.setContentsMargins(0, 0, 0, 0)

        inputs = self.spec.get("inputs", {})
        if not inputs:
            empty_label = BodyLabel("无输入参数")
            empty_label.setAlignment(Qt.AlignCenter)
            scroll_layout.addWidget(empty_label)
        else:
            for key, cfg in inputs.items():
                card = self._create_param_card(key, cfg)
                scroll_layout.addWidget(card)

        scroll_layout.addStretch()
        scroll_content.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_content)
        left_layout.addWidget(scroll_area)

        self.send_btn = PrimaryPushButton("发送请求")
        self.send_btn.setFixedHeight(36)
        self.send_btn.clicked.connect(self._send_request)
        left_layout.addWidget(self.send_btn)

        # === 右侧：结果 ===
        right_frame = QFrame()
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        result_title = StrongBodyLabel("响应结果")
        setFont(result_title, 14)
        right_layout.addWidget(result_title)

        self.result_text = TextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setPlaceholderText("发送请求后，结果将显示在这里...")
        self.result_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                border: 1px solid #3c3c40;
                border-radius: 6px;
                padding: 12px;
            }
        """)
        right_layout.addWidget(self.result_text)

        splitter.addWidget(left_frame)
        splitter.addWidget(right_frame)
        splitter.setSizes([250, 250])  # 适应右侧窄面板
        main_layout.addWidget(splitter)

    def _create_param_card(self, key, cfg):
        card = CardWidget()
        card.setFixedHeight(80)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        name_label = StrongBodyLabel(key)
        setFont(name_label, 12)
        layout.addWidget(name_label)

        default_val = cfg.get("current_value")
        widget = self._create_input_widget(key, default_val)
        widget.setFixedHeight(32)
        layout.addWidget(widget)
        self.input_widgets[key] = widget
        return card

    def _create_input_widget(self, key, default_val):
        if isinstance(default_val, bool):
            return CheckBox(checked=default_val)
        elif isinstance(default_val, int):
            sb = SpinBox()
            sb.setValue(default_val)
            sb.setRange(-999999, 999999)
            return sb
        elif isinstance(default_val, float):
            dsb = DoubleSpinBox()
            dsb.setValue(default_val)
            dsb.setRange(-999999.0, 999999.0)
            dsb.setDecimals(6)
            return dsb
        elif isinstance(default_val, str):
            le = LineEdit()
            le.setText(default_val)
            le.setClearButtonEnabled(True)
            return le
        else:
            le = LineEdit()
            le.setPlaceholderText("输入值（支持 JSON）")
            le.setClearButtonEnabled(True)
            return le

    def _send_request(self):
        payload = {}
        for key, widget in self.input_widgets.items():
            if isinstance(widget, CheckBox):
                value = widget.isChecked()
            elif isinstance(widget, (SpinBox, DoubleSpinBox)):
                value = widget.value()
            else:
                text = widget.text().strip()
                if not text:
                    value = ""
                elif text.startswith(('{', '[')):
                    try:
                        value = json.loads(text)
                    except:
                        value = text
                else:
                    value = text
            payload[key] = value

        self.send_btn.setEnabled(False)
        self.send_btn.setText("请求中...")
        self.result_text.setPlaceholderText("正在发送请求...")

        worker = RequestWorker(self.service_url, payload)
        worker.signals.success.connect(self._on_request_success)
        worker.signals.error.connect(self._on_request_error)
        self.thread_pool.start(worker)

    def _on_request_success(self, result):
        self._restore_button()
        try:
            formatted = json.dumps(result, indent=2, ensure_ascii=False)
        except:
            formatted = str(result)
        self.result_text.setPlainText(formatted)

    def _on_request_error(self, error_msg):
        self._restore_button()
        self.result_text.setPlainText(f"❌ 请求失败:\n{error_msg}")

    def _restore_button(self):
        self.send_btn.setEnabled(True)
        self.send_btn.setText("发送请求")