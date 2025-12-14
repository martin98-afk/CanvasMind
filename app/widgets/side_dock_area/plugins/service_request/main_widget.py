# -*- coding: utf-8 -*-
import json
import os
from PyQt5.QtCore import Qt, QThreadPool
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QWidget, QLabel
from qfluentwidgets import (
    LineEdit, SpinBox, DoubleSpinBox, CheckBox,
    PrimaryPushButton, BodyLabel, StrongBodyLabel,
    CardWidget, VBoxLayout, TextEdit, setFont, SmoothScrollArea
)

from app.widgets.dialog_widget.service_request_dialog import RequestWorker
from app.widgets.basic_widget.splitter import ModernSplitter
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition
from app.utils.utils import get_icon


class ServiceTestTool(ToolWindow):
    name = "项目服务测试"
    icon = get_icon("API测试")
    default_position = DockPosition.TOP
    thread_pool = QThreadPool.globalInstance()
    project_path = None
    service_url = None
    spec = {"inputs": {}}
    input_widgets = {}

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(16)

        self.splitter = ModernSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter)

        # === 左侧：参数区域 ===
        self.left_frame = QFrame()
        self.left_frame.setStyleSheet("border: none; background: transparent;")
        self.left_layout = QVBoxLayout(self.left_frame)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(12)

        self.param_title = StrongBodyLabel("请求参数")
        setFont(self.param_title, 14)
        self.left_layout.addWidget(self.param_title)

        self.scroll_area = SmoothScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("border: none; background: transparent;")
        self.scroll_content = QWidget()
        self.scroll_layout = VBoxLayout(self.scroll_content)
        self.scroll_layout.setSpacing(12)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_content.setLayout(self.scroll_layout)
        self.scroll_area.setWidget(self.scroll_content)
        self.left_layout.addWidget(self.scroll_area)

        self.send_btn = PrimaryPushButton("发送请求")
        self.send_btn.setFixedHeight(36)
        self.send_btn.clicked.connect(self._send_request)
        self.left_layout.addWidget(self.send_btn)

        # === 右侧：结果区域 ===
        self.right_frame = QFrame()
        self.right_layout = QVBoxLayout(self.right_frame)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setSpacing(12)

        self.result_title = StrongBodyLabel("响应结果")
        setFont(self.result_title, 14)
        self.right_layout.addWidget(self.result_title)

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
        self.right_layout.addWidget(self.result_text)

        self.splitter.addWidget(self.left_frame)
        self.splitter.addWidget(self.right_frame)
        self.splitter.setSizes([250, 250])

        # 初始状态：未加载
        self._show_offline_message()

    def _load_spec(self, project_path):
        spec_path = os.path.join(project_path, "project_spec.json")
        try:
            with open(spec_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {"inputs": {}}

    def _clear_inputs(self):
        """清空左侧参数区域"""
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.input_widgets.clear()

    def _show_offline_message(self):
        """显示服务未上线提示"""
        self._clear_inputs()
        self.send_btn.setEnabled(False)
        hint = BodyLabel("项目微服务未上线")
        hint.setStyleSheet("color: #ff9800;")
        hint.setAlignment(Qt.AlignCenter)
        self.scroll_layout.addWidget(hint)
        self.result_text.setPlainText("")
        self.result_text.setPlaceholderText("服务未上线，无法发送请求")

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

    def refresh(self, project_path, service_url=None):
        """
        刷新工具内容

        Args:
            project_path (str): 项目路径
            service_url (str, optional): 服务地址。若为 None，显示未上线提示。
        """
        self.project_path = project_path
        self.service_url = service_url

        if service_url:
            # 服务已上线：加载参数
            self.spec = self._load_spec(project_path)
            self._clear_inputs()
            inputs = self.spec.get("inputs", {})
            if not inputs:
                empty_label = BodyLabel("无输入参数")
                empty_label.setAlignment(Qt.AlignCenter)
                self.scroll_layout.addWidget(empty_label)
            else:
                for key, cfg in inputs.items():
                    card = self._create_param_card(key, cfg)
                    self.scroll_layout.addWidget(card)
            self.scroll_layout.addStretch()
            self.send_btn.setEnabled(True)
            self.result_text.setPlaceholderText("发送请求后，结果将显示在这里...")
        else:
            # 服务未上线
            self._show_offline_message()

    def _send_request(self):
        if not self.service_url:
            return

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
                    except (ValueError, TypeError):
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
        except (ValueError, TypeError):
            formatted = str(result)
        self.result_text.setPlainText(formatted)

    def _on_request_error(self, error_msg):
        self._restore_button()
        self.result_text.setPlainText(f"❌ 请求失败:\n{error_msg}")

    def _restore_button(self):
        self.send_btn.setEnabled(True)
        self.send_btn.setText("发送请求")