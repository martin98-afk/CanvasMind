# -*- coding: utf-8 -*-
import json
import os
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from PyQt5.QtCore import Qt, QObject, pyqtSignal, QThreadPool, QRunnable
from PyQt5.QtWidgets import QSplitter, QFrame, QVBoxLayout, QDialog, QScrollArea, QWidget, QMessageBox
from qfluentwidgets import (
    LineEdit, SpinBox, DoubleSpinBox, CheckBox,
    PrimaryPushButton, BodyLabel, StrongBodyLabel,
    CardWidget, VBoxLayout, TextEdit, setFont
)
import requests


# === 异步任务封装 ===
class RequestWorker(QRunnable):
    def __init__(self, url, payload, timeout=300):
        super().__init__()
        self.url = url
        self.payload = payload
        self.timeout = timeout
        self.signals = RequestSignals()

    def run(self):
        try:
            response = requests.post(
                self.url,
                json=self.payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()
            self.signals.success.emit(result)
        except requests.exceptions.Timeout:
            self.signals.error.emit("请求超时，请检查网络或服务状态。")
        except requests.exceptions.ConnectionError:
            self.signals.error.emit("无法连接到服务，请确认服务是否运行。")
        except requests.exceptions.HTTPError as e:
            self.signals.error.emit(f"HTTP 错误: {e.response.status_code} - {e.response.reason}")
        except ValueError:  # 包括 JSONDecodeError
            self.signals.error.emit("服务返回了无效的 JSON 格式。")
        except Exception as e:
            self.signals.error.emit(f"未知错误: {str(e)}")


class RequestSignals(QObject):
    success = pyqtSignal(object)
    error = pyqtSignal(str)


class ServiceRequestDialog(QDialog):
    def __init__(self, project_path, service_url, parent=None):
        super().__init__(parent)
        self.project_path = project_path
        self.service_url = service_url
        self.spec = self._load_spec()
        self.input_widgets = {}
        self.thread_pool = QThreadPool.globalInstance()  # 使用全局线程池

        self.setWindowTitle(f"服务请求 - {os.path.basename(project_path)}")
        self.resize(960, 600)
        self._setup_ui()

    def _load_spec(self):
        spec_path = os.path.join(self.project_path, "project_spec.json")
        try:
            with open(spec_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "加载错误", f"无法加载项目配置：\n{str(e)}")
            return {"inputs": {}}

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(8)
        splitter.setStyleSheet("QSplitter::handle { background: #3c3c40; }")

        # === 左侧：参数区域 ===
        left_frame = QFrame()
        left_frame.setStyleSheet("QFrame { background: transparent; }")
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        param_title = StrongBodyLabel("请求参数")
        setFont(param_title, 14)
        left_layout.addWidget(param_title)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
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

        splitter.addWidget(left_frame)
        splitter.addWidget(right_frame)
        splitter.setSizes([480, 480])
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
            le.setPlaceholderText("输入值（支持 JSON）")
            le.setClearButtonEnabled(True)
            return le

    def _send_request(self):
        # 1. 收集参数
        payload = {}
        for key, widget in self.input_widgets.items():
            if isinstance(widget, CheckBox):
                value = widget.isChecked()
            elif isinstance(widget, (SpinBox, DoubleSpinBox)):
                value = widget.value()
            else:  # LineEdit
                text = widget.text().strip()
                if not text:
                    value = ""
                elif text.startswith(('{', '[')):
                    try:
                        value = json.loads(text)
                    except json.JSONDecodeError:
                        value = text  # 保留原始字符串
                else:
                    value = text
            payload[key] = value

        # 2. 禁用按钮，显示加载状态
        self.send_btn.setEnabled(False)
        self.send_btn.setText("请求中...")
        self.result_text.setPlaceholderText("正在发送请求，请稍候...")

        # 3. 启动异步任务
        worker = RequestWorker(self.service_url, payload, timeout=30)  # 缩短超时更合理
        worker.signals.success.connect(self._on_request_success)
        worker.signals.error.connect(self._on_request_error)
        self.thread_pool.start(worker)

    def _on_request_success(self, result):
        self._restore_button()
        try:
            formatted = json.dumps(result, indent=2, ensure_ascii=False)
        except Exception:
            formatted = str(result)
        self.result_text.setPlainText(formatted)

    def _on_request_error(self, error_msg):
        self._restore_button()
        self.result_text.setPlainText(f"❌ 请求失败:\n{error_msg}")

    def _restore_button(self):
        self.send_btn.setEnabled(True)
        self.send_btn.setText("发送请求")