import platform
import subprocess
import sys
import threading
import time
from typing import Optional

from PyQt5.QtCore import QThread, pyqtSignal, QObject
from loguru import logger
from pylspclient.json_rpc_endpoint import JsonRpcEndpoint


class LspClientManager(QThread):
    completion_ready = pyqtSignal(list)    # List[CompletionItem]
    diagnostics_ready = pyqtSignal(list)   # List[Diagnostic]
    folding_ready = pyqtSignal(list)       # List[FoldingRange]
    initialized = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, python_path: Optional[str] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.python_path = python_path
        self.endpoint: Optional[JsonRpcEndpoint] = None
        self.process: Optional[subprocess.Popen] = None
        self.version = 0
        self.uri = "file:///tmp/editor.py"
        self._running = True
        self._msg_id = 1
        self._response_map = {}
        self._lock = threading.Lock()
        self._notification_thread = None
        self._stderr_thread = None

    def run(self):
        try:
            # 启动 pylsp
            cmd = [self.python_path, "-m", "pylsp"]
            kwargs = {}
            if platform.system() == "Windows":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **kwargs
            )

            # 启动 stderr 日志（用于调试）
            self._stderr_thread = threading.Thread(target=self._log_stderr, daemon=True)
            self._stderr_thread.start()

            self.endpoint = JsonRpcEndpoint(self.process.stdin, self.process.stdout)

            # 启动响应监听
            self._notification_thread = threading.Thread(target=self._listen_messages, daemon=True)
            self._notification_thread.start()

            # 发送 initialize
            init_id = self._send_message("initialize", {
                "processId": self.process.pid,
                "rootUri": "file:///tmp",
                "initializationOptions": {
                    "pylsp": {
                        "plugins": {
                            "jedi_completion": {"enabled": True},
                            "pyflakes": {"enabled": True},
                            "folding": {"enabled": True},          # ← 必须启用
                            "pycodestyle": {"enabled": True}       # ← folding 依赖它
                        }
                    }
                },
                "capabilities": {
                    "textDocument": {
                        "completion": {
                            "completionItem": {
                                "documentationFormat": ["plaintext"],
                                "snippetSupport": True,
                                "insertTextMode": 2  # AsIs
                            }
                        },
                        "publishDiagnostics": {},
                        "foldingRange": {}  # ← 声明支持
                    }
                },
                "trace": "off"
            })

            response = self._wait_for_response(init_id, timeout=10.0)
            if not response:
                raise TimeoutError("Initialize timeout")

            # ✅ 关键：立即发送 initialized + 空文档
            self._send_message("initialized", {}, is_notification=True)
            self._send_message("textDocument/didOpen", {
                "textDocument": {
                    "uri": self.uri,
                    "languageId": "python",
                    "version": 1,
                    "text": ""
                }
            }, is_notification=True)

            self.initialized.emit()

        except Exception as e:
            logger.error(f"[LSP] Startup error: {e}")
            self.error.emit(str(e))

    def _log_stderr(self):
        if self.process and self.process.stderr:
            for line in self.process.stderr:
                if line:
                    logger.error(f"[LSP stderr] {line.decode('utf-8', errors='replace').strip()}")

    def _listen_messages(self):
        while self._running and self.process:
            try:
                msg = self.endpoint.recv_response()
                if msg is None:
                    break
                if 'id' in msg:
                    with self._lock:
                        self._response_map[msg['id']] = msg
                elif 'method' in msg:
                    if msg['method'] == 'textDocument/publishDiagnostics':
                        diagnostics = msg['params'].get('diagnostics', [])
                        self.diagnostics_ready.emit(diagnostics)
            except Exception as e:
                if self._running:
                    logger.error(f"[LSP] Listen error: {e}")
                break

    def _send_message(self, method: str, params: dict, is_notification: bool = False):
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        if not is_notification:
            with self._lock:
                msg_id = self._msg_id
                self._msg_id += 1
                msg["id"] = msg_id
            self.endpoint.send_request(msg)
            return msg_id
        else:
            self.endpoint.send_request(msg)
            return None

    def _wait_for_response(self, msg_id: int, timeout: float = 5.0):
        start = time.time()
        while time.time() - start < timeout:
            with self._lock:
                if msg_id in self._response_map:
                    return self._response_map.pop(msg_id)
            time.sleep(0.01)
        return None

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
            msg_id = self._send_message("textDocument/completion", {
                "textDocument": {"uri": self.uri},
                "position": {"line": line, "character": col}
            })
            result = self._wait_for_response(msg_id, timeout=3.0)
            if result and 'result' in result:
                items = result['result'].get('items', []) if isinstance(result['result'], dict) else result['result']
                self.completion_ready.emit(items)
        except Exception as e:
            logger.error(f"[LSP] Completion error: {e}")

    def request_folding_ranges(self, uri: str):
        try:
            msg_id = self._send_message("textDocument/foldingRange", {
                "textDocument": {"uri": uri}
            })
            result = self._wait_for_response(msg_id, timeout=3.0)
            if result and 'result' in result:
                self.folding_ready.emit(result['result'] or [])
        except Exception as e:
            logger.error(f"[LSP] Folding error: {e}")

    def shutdown(self):
        self._running = False
        if self.process:
            try:
                # 发送 shutdown 请求
                msg_id = self._send_message("shutdown", {})
                self._wait_for_response(msg_id, timeout=2.0)
                self._send_message("exit", {}, is_notification=True)
            except:
                pass
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()

    def __del__(self):
        self.shutdown()