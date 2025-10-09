# -*- coding: utf-8 -*-
import json
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QSplitter, QFrame, QVBoxLayout, QDialog, QScrollArea, QWidget
from qfluentwidgets import (
    LineEdit, SpinBox, DoubleSpinBox, CheckBox,
    PrimaryPushButton, BodyLabel, StrongBodyLabel,
    CardWidget, VBoxLayout, TextEdit, setFont
)
import requests


class ServiceRequestDialog(QDialog):
    def __init__(self, project_path, service_url, parent=None):
        super().__init__(parent)
        self.project_path = project_path
        self.service_url = service_url
        self.spec = self._load_spec()
        self.input_widgets = {}

        self.setWindowTitle(f"服务请求 - {os.path.basename(project_path)}")
        self.resize(960, 600)
        self._setup_ui()

    def _load_spec(self):
        spec_path = os.path.join(self.project_path, "project_spec.json")
        with open(spec_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)
        # 分割器
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(8)
        splitter.setStyleSheet("QSplitter::handle { background: #3c3c40; }")

        # === 左侧：参数区域 ===
        left_frame = QFrame()
        left_frame.setStyleSheet("QFrame { background: transparent; }")
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        # 参数标题
        param_title = StrongBodyLabel("请求参数")
        setFont(param_title, 14)
        left_layout.addWidget(param_title)

        # 滚动区域（避免参数多时溢出）
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll_content = QWidget()
        scroll_layout = VBoxLayout(scroll_content)
        scroll_layout.setSpacing(12)
        scroll_layout.setContentsMargins(0, 0, 0, 0)

        # 动态生成参数卡片
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

        # 发送按钮（固定在底部）
        self.send_btn = PrimaryPushButton("发送请求")
        self.send_btn.setFixedHeight(36)
        self.send_btn.clicked.connect(self._send_request)
        left_layout.addWidget(self.send_btn)

        # === 右侧：结果区域 ===
        right_frame = QFrame()
        right_frame.setStyleSheet("QFrame { background: transparent; }")
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

        # 添加到分割器
        splitter.addWidget(left_frame)
        splitter.addWidget(right_frame)
        splitter.setSizes([480, 480])  # 960 总宽，各占一半

        main_layout.addWidget(splitter)

    def _create_param_card(self, key, cfg):
        """创建单个参数卡片"""
        card = CardWidget()
        card.setFixedHeight(80)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # 参数名
        name_label = StrongBodyLabel(key)
        setFont(name_label, 12)
        layout.addWidget(name_label)

        # 输入控件
        default_val = cfg.get("current_value")
        widget = self._create_input_widget(key, default_val)
        widget.setFixedHeight(32)
        layout.addWidget(widget)
        self.input_widgets[key] = widget

        return card

    def _create_input_widget(self, key, default_val):
        """根据默认值类型创建输入控件"""
        if isinstance(default_val, bool):
            cb = CheckBox()
            cb.setChecked(default_val)
            return cb
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
            le.setPlaceholderText("输入值")
            le.setClearButtonEnabled(True)
            return le

    def _send_request(self):
        """发送请求到微服务"""
        try:
            payload = {}
            for key, widget in self.input_widgets.items():
                if isinstance(widget, CheckBox):
                    value = widget.isChecked()
                elif isinstance(widget, (SpinBox, DoubleSpinBox)):
                    value = widget.value()
                else:  # LineEdit
                    value = widget.text()
                    if value.startswith(('{', '[')):
                        try:
                            value = json.loads(value)
                        except:
                            pass
                payload[key] = value

            response = requests.post(
                self.service_url,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()

            formatted = json.dumps(result, indent=2, ensure_ascii=False)
            self.result_text.setPlainText(formatted)

        except Exception as e:
            error_msg = f"请求失败:\n{str(e)}"
            self.result_text.setPlainText(error_msg)