# lsp_service_manager.py

import subprocess
import sys
import threading
from typing import Optional

from PyQt5.QtCore import QThread, pyqtSignal, QObject
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QTextEdit, QPushButton,
    QListWidget, QHBoxLayout, QLabel, QSplitter
)
from pylspclient.json_rpc_endpoint import JsonRpcEndpoint  # 你提供的版本


class LspClientManager(QThread):
    completion_ready = pyqtSignal(list)  # [(label, kind, detail, doc), ...]
    diagnostics_ready = pyqtSignal(list)
    initialized = pyqtSignal()

    def __init__(self, python_path: Optional[str] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.python_path = python_path or sys.executable
        self.endpoint: Optional[JsonRpcEndpoint] = None
        self.process: Optional[subprocess.Popen] = None
        self.version = 0
        self.uri = "file:///tmp/inline.py"
        self._running = True
        self._msg_id = 1
        self._response_map = {}
        self._lock = threading.Lock()

    def _send_message(self, method: str, params: dict, is_notification: bool = False):
        """发送 JSON-RPC 消息"""
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        if not is_notification:
            with self._lock:
                msg_id = self._msg_id
                self._msg_id += 1
                msg["id"] = msg_id
        self.endpoint.send_request(msg)
        return msg.get("id")

    def _wait_for_response(self, msg_id: int, timeout: float = 5.0):
        """等待特定 ID 的响应"""
        import time
        start = time.time()
        while time.time() - start < timeout:
            with self._lock:
                if msg_id in self._response_map:
                    return self._response_map.pop(msg_id)
            time.sleep(0.01)
        raise TimeoutError(f"Response for ID {msg_id} timed out")

    def run(self):
        try:
            # 启动 pylsp 子进程
            cmd = [self.python_path, "-m", "pylsp"]
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.endpoint = JsonRpcEndpoint(self.process.stdin, self.process.stdout)

            # 启动响应监听线程（处理 request 回复 和 notification）
            self._notification_thread = threading.Thread(target=self._listen_messages, daemon=True)
            self._notification_thread.start()

            # 发送 initialize
            init_id = self._send_message("initialize", {
                "processId": self.process.pid,
                "rootPath": None,
                "rootUri": "file:///tmp",
                "initializationOptions": {
                    "pylsp": {
                        "plugins": {
                            "jedi_completion": {"enabled": True},
                            "pycodestyle": {"enabled": False},
                            "pyflakes": {"enabled": True}
                        }
                    }
                },
                "capabilities": {
                    "textDocument": {
                        "completion": {"completionItem": {"documentationFormat": ["plaintext"]}},
                        "publishDiagnostics": {}
                    }
                },
                "trace": None,
                "workspaceFolders": None
            }, is_notification=False)

            response = self._wait_for_response(init_id)
            # 发送 initialized 通知
            self._send_message("initialized", {}, is_notification=True)

            self.initialized.emit()

        except Exception as e:
            print(f"[LSP] Startup error: {e}", flush=True)

    def _listen_messages(self):
        """监听所有 incoming 消息（response 和 notification）"""
        while self._running and self.process:
            try:
                msg = self.endpoint.recv_response()
                if msg is None:
                    break
                if 'id' in msg:  # 是 response
                    with self._lock:
                        self._response_map[msg['id']] = msg
                elif 'method' in msg:  # 是 notification
                    if msg['method'] == 'textDocument/publishDiagnostics':
                        diagnostics = msg['params'].get('diagnostics', [])
                        self.diagnostics_ready.emit(diagnostics)
            except Exception as e:
                if self._running:
                    print(f"[LSP] Listen error: {e}", flush=True)
                break

    def open_document(self, text: str):
        self.version += 1
        self._send_message("textDocument/didOpen", {
            "textDocument": {
                "uri": self.uri,
                "languageId": "python",
                "version": self.version,
                "text": text
            }
        }, is_notification=True)

    def change_document(self, text: str):
        self.version += 1
        self._send_message("textDocument/didChange", {
            "textDocument": {"uri": self.uri, "version": self.version},
            "contentChanges": [{"text": text}]
        }, is_notification=True)

    def request_completion(self, line: int, col: int):
        try:
            comp_id = self._send_message("textDocument/completion", {
                "textDocument": {"uri": self.uri},
                "position": {"line": line, "character": col}
            }, is_notification=False)

            result = self._wait_for_response(comp_id)
            items = result.get("result", {}).get("items", []) if result else []
            completions = []
            for item in items:
                label = item.get("label", "")
                kind = item.get("kind", 0)
                detail = item.get("detail", "")
                doc = item.get("documentation", "")
                if isinstance(doc, dict) and "value" in doc:
                    doc = doc["value"]
                completions.append((label, kind, detail, doc))
            self.completion_ready.emit(completions)
        except Exception as e:
            print(f"[LSP] Completion error: {e}", flush=True)

    def shutdown(self):
        self._running = False
        if self.endpoint and self.process:
            try:
                self._send_message("shutdown", {}, is_notification=False)
                self._send_message("exit", {}, is_notification=True)
            except Exception:
                pass
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()

    def __del__(self):
        self.shutdown()


# =============== DEMO ===============
class LspDemoWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LSP Client Demo (pylspclient >=1.0)")
        self.resize(900, 600)

        self.editor = QTextEdit()
        self.editor.setPlainText("import os\nos.")
        self.completion_button = QPushButton("Request Completion at Cursor")
        self.completion_list = QListWidget()
        self.diagnostics_list = QListWidget()

        self.completion_button.clicked.connect(self.on_request_completion)

        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Python Code:"))
        left_layout.addWidget(self.editor)
        left_layout.addWidget(self.completion_button)

        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("Completions:"))
        right_layout.addWidget(self.completion_list)
        right_layout.addWidget(QLabel("Diagnostics:"))
        right_layout.addWidget(self.diagnostics_list)

        splitter = QSplitter()
        left_widget = QWidget()
        left_widget.setLayout(left_layout)
        right_widget = QWidget()
        right_widget.setLayout(right_layout)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([500, 400])

        main_layout = QHBoxLayout()
        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

        # 启动 LSP
        self.lsp_manager = LspClientManager()
        self.lsp_manager.initialized.connect(self.on_lsp_ready)
        self.lsp_manager.completion_ready.connect(self.on_completion)
        self.lsp_manager.diagnostics_ready.connect(self.on_diagnostics)
        self.lsp_manager.start()

    def on_lsp_ready(self):
        text = self.editor.toPlainText()
        self.lsp_manager.open_document(text)

    def on_request_completion(self):
        cursor = self.editor.textCursor()
        line = cursor.blockNumber()
        col = cursor.positionInBlock()
        text = self.editor.toPlainText()
        self.lsp_manager.change_document(text)
        self.lsp_manager.request_completion(line, col)

    def on_completion(self, completions):
        self.completion_list.clear()
        for label, kind, detail, doc in completions[:15]:
            item_text = f"{label} ({detail})" if detail else label
            self.completion_list.addItem(item_text)

    def on_diagnostics(self, diagnostics):
        self.diagnostics_list.clear()
        if not diagnostics:
            self.diagnostics_list.addItem("✅ No issues")
        else:
            for diag in diagnostics:
                start = diag['range']['start']
                line = start['line'] + 1
                msg = f"L{line}: {diag['message']}"
                self.diagnostics_list.addItem(msg)

    def closeEvent(self, event):
        self.lsp_manager.shutdown()
        self.lsp_manager.wait()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = LspDemoWindow()
    window.show()
    sys.exit(app.exec_())