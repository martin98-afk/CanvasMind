# -*- coding: utf-8 -*-
import sys
import os
import json
import logging
from typing import Optional, List, Dict, Callable

from PyQt5.QtCore import QObject, QProcess, QSocketNotifier, pyqtSignal, QTimer
from PyQt5.QtWidgets import QApplication
import zmq
from zmq import Context
import psutil


class LspClientZMQManager(QObject):
    # === 保持你原来的信号接口 ===
    initialized = pyqtSignal()
    completion_ready = pyqtSignal(list)
    diagnostics_ready = pyqtSignal(list)
    folding_ready = pyqtSignal(list)
    server_error = pyqtSignal(str)
    server_down = pyqtSignal()

    def __init__(self, python_path: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.python_path = python_path or sys.executable
        self._uri = "file:///tmp/editor.py"
        self.context = Context()
        self.zmq_out_socket = self.context.socket(zmq.PAIR)  # 发给 transport
        self.zmq_in_socket = self.context.socket(zmq.PAIR)   # 从 transport 收
        self.zmq_out_port = self.zmq_out_socket.bind_to_random_port("tcp://127.0.0.1")
        self.zmq_in_port = self.zmq_in_socket.bind_to_random_port("tcp://127.0.0.1")

        self.transport_process = None
        self.notifier = None
        self._request_seq = 1
        self._request_callbacks: Dict[int, Callable] = {}
        self._initialized = False
        self.stdio_pid = None

    def start(self):
        """兼容你原来的 .start() 调用"""
        # 启动 transport 进程（内联 transport 逻辑，避免外部脚本依赖）
        self.transport_process = QProcess(self)
        transport_script = os.path.join(os.path.dirname(__file__), "lsp_transport.py")
        if not os.path.exists(transport_script):
            self.server_error.emit(f"Transport script not found: {transport_script}")
            return

        cmd = [
            sys.executable, "-u", transport_script,
            str(self.zmq_in_port),   # transport 的 in（主进程发）
            str(self.zmq_out_port),  # transport 的 out（主进程收）
            self.python_path
        ]
        self.transport_process.setProcessChannelMode(QProcess.SeparateChannels)
        self.transport_process.start(cmd[0], cmd[1:])
        self.transport_process.finished.connect(self._on_transport_finished)

        # 监听 ZMQ 消息
        fd = self.zmq_in_socket.getsockopt(zmq.FD)
        self.notifier = QSocketNotifier(fd, QSocketNotifier.Read, self)
        self.notifier.activated.connect(self._on_message_received)

        # 延迟发送 initialize（等 transport 启动）
        QTimer.singleShot(200, self._send_initialize)

    def _on_transport_finished(self):
        self.server_down.emit()
        if self.notifier:
            self.notifier.setEnabled(False)
        self.context.destroy()

    def _send_initialize(self):
        params = {
            "processId": os.getpid(),
            "rootUri": "file:///tmp",
            "initializationOptions": {
                "pylsp": {
                    "plugins": {
                        "jedi_completion": {"enabled": True},
                        "pyflakes": {"enabled": True},
                        "folding": {"enabled": True},
                        "pycodestyle": {"enabled": True}
                    }
                }
            },
            "capabilities": {
                "textDocument": {
                    "completion": {
                        "completionItem": {
                            "documentationFormat": ["plaintext"],
                            "snippetSupport": True,
                            "insertTextMode": 2
                        }
                    },
                    "publishDiagnostics": {},
                    "foldingRange": {}
                }
            },
            "trace": "off"
        }
        self._send_request("initialize", params, self._on_initialize_response)

    def _send_request(self, method: str, params: dict, callback: Callable):
        msg_id = self._request_seq
        self._request_seq += 1
        self._request_callbacks[msg_id] = callback
        msg = {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params}
        try:
            self.zmq_out_socket.send_pyobj(msg)
        except Exception as e:
            self.server_error.emit(f"ZMQ send error: {e}")

    def _send_notification(self, method: str, params: dict):
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        try:
            self.zmq_out_socket.send_pyobj(msg)
        except Exception as e:
            self.server_error.emit(f"ZMQ notification error: {e}")

    def _on_initialize_response(self, response):
        if response and "result" in response:
            self._send_notification("initialized", {})
            self._send_notification("textDocument/didOpen", {
                "textDocument": {
                    "uri": self._uri,
                    "languageId": "python",
                    "version": 1,
                    "text": ""
                }
            })
            self._initialized = True
            self.initialized.emit()
        else:
            error = response.get("error", {}).get("message", "Initialize failed") if response else "No response"
            self.server_error.emit(f"Initialize error: {error}")

    def _on_message_received(self):
        self.notifier.setEnabled(False)
        try:
            while True:
                try:
                    msg = self.zmq_in_socket.recv_pyobj(zmq.NOBLOCK)
                    if "method" in msg:
                        self._handle_notification(msg)
                    elif "id" in msg:
                        callback = self._request_callbacks.pop(msg["id"], None)
                        if callback:
                            callback(msg)
                except zmq.Again:
                    break
        except Exception as e:
            logging.error(f"ZMQ receive error: {e}")
        finally:
            self.notifier.setEnabled(True)

    def _handle_notification(self, msg):
        method = msg["method"]
        params = msg.get("params", {})
        if method == "textDocument/publishDiagnostics":
            diagnostics = params.get("diagnostics", [])
            self.diagnostics_ready.emit(diagnostics)

    # === 公共 API（完全兼容你原来的调用）===
    def open_document(self, text: str):
        """兼容旧接口"""
        self.change_document(text)

    def change_document(self, text: str):
        if not self._initialized:
            return
        self._send_notification("textDocument/didChange", {
            "textDocument": {"uri": self._uri, "version": 1},
            "contentChanges": [{"text": text}]
        })

    def request_completion(self, line: int, col: int):
        if not self._initialized:
            return

        def on_response(response):
            if response and "result" in response:
                items = response["result"]
                if isinstance(items, dict) and "items" in items:
                    items = items["items"]
                self.completion_ready.emit(items or [])

        self._send_request("textDocument/completion", {
            "textDocument": {"uri": self._uri},
            "position": {"line": line, "character": col}
        }, on_response)

    def request_folding_ranges(self, uri: str = None):
        """兼容旧接口（忽略 uri）"""
        if not self._initialized:
            return

        def on_response(response):
            if response and "result" in response:
                self.folding_ready.emit(response["result"] or [])

        self._send_request("textDocument/foldingRange", {
            "textDocument": {"uri": self._uri}
        }, on_response)

    def shutdown(self):
        if self.transport_process and self.transport_process.state() == QProcess.Running:
            self._send_request("shutdown", {}, lambda r: self._send_exit())
            QTimer.singleShot(1000, self._force_kill)

    def _send_exit(self):
        self._send_notification("exit", {})
        if self.transport_process:
            self.transport_process.waitForFinished(1000)

    def _force_kill(self):
        if self.transport_process and self.transport_process.state() == QProcess.Running:
            self.transport_process.kill()
        self.context.destroy()