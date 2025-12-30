# lsp_manager.py

import platform
import subprocess
import sys
import threading
import time
from typing import Optional, List, Dict, Callable

from PyQt5.QtCore import pyqtSignal, QObject, QMetaObject, Qt, Q_ARG
from loguru import logger
from pylspclient.json_rpc_endpoint import JsonRpcEndpoint


# ==============================
# 单例 LSP 进程管理器
# ==============================
class LspProcessManager(QObject):
    error = pyqtSignal(str)
    initialized = pyqtSignal()

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, python_path: Optional[str] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        if hasattr(self, '_initialized') and self._initialized:
            return
        self.python_path = python_path or sys.executable
        self.process: Optional[subprocess.Popen] = None
        self.endpoint: Optional[JsonRpcEndpoint] = None
        self._running = True
        self._msg_id = 1
        self._response_callbacks: Dict[int, Callable] = {}
        self._sessions: Dict[str, 'LspDocumentSession'] = {}  # uri → session
        self._lock = threading.Lock()
        self._notification_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._initialized_flag = False
        self._initialized = True  # 防止重复初始化

    def start_lsp(self, python_exe: Optional[str] = None):
        """启动 LSP 进程（只调用一次）"""
        if self._initialized_flag and self.python_path != python_exe:
            return
        try:
            cmd = [python_exe or self.python_path, "-m", "pylsp"]
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

            self._stderr_thread = threading.Thread(target=self._log_stderr, daemon=True)
            self._stderr_thread.start()

            self.endpoint = JsonRpcEndpoint(self.process.stdin, self.process.stdout)

            self._notification_thread = threading.Thread(target=self._listen_messages, daemon=True)
            self._notification_thread.start()

            # 发送 initialize
            init_id = self._send_request("initialize", {
                "processId": self.process.pid,
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
                        "foldingRange": {},
                        "hover": {"dynamicRegistration": False},
                        "signatureHelp": {
                            "signatureInformation": {
                                "documentationFormat": ["plaintext"]
                            }
                        },
                        "definitionProvider": True,
                        "referencesProvider": True,
                        "documentSymbolProvider": True,
                        "documentHighlightProvider": True,
                        "renameProvider": True,
                        "documentFormattingProvider": True,
                        "documentRangeFormattingProvider": True,
                    }
                },
                "trace": "off"
            }, self._on_initialize_response)

        except Exception as e:
            logger.error(f"[LSP] Startup error: {e}")
            QMetaObject.invokeMethod(self, "error", Qt.QueuedConnection, Q_ARG(str, str(e)))

    def restart_lsp(self):
        self.shutdown()
        self.start_lsp()

    def _on_initialize_response(self, msg):
        if 'error' in msg:
            err = msg['error'].get('message', 'Unknown error')
            QMetaObject.invokeMethod(self, "error", Qt.QueuedConnection, Q_ARG(str, err))
            return
        self._send_notification("initialized", {})
        self._initialized_flag = True
        QMetaObject.invokeMethod(self, "initialized", Qt.QueuedConnection)

    def register_session(self, session: 'LspDocumentSession'):
        with self._lock:
            self._sessions[session.uri] = session
            self.initialized.emit()

    def unregister_session(self, uri: str):
        with self._lock:
            self._sessions.pop(uri, None)

    def find_session_by_uri(self, uri: str) -> Optional['LspDocumentSession']:
        with self._lock:
            return self._sessions.get(uri)

    def _send_request(self, method: str, params: dict, callback: Optional[Callable] = None) -> int:
        with self._lock:
            msg_id = self._msg_id
            self._msg_id += 1
            if callback:
                self._response_callbacks[msg_id] = callback
        msg = {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params}
        try:
            self.endpoint.send_request(msg)
        except Exception as e:
            logger.error(f"[LSP] Send request error: {e}")
            if callback:
                # 模拟错误响应
                QMetaObject.invokeMethod(
                    self, "_invoke_callback",
                    Qt.QueuedConnection,
                    Q_ARG(object, callback),
                    Q_ARG(object, {"id": msg_id, "error": {"message": str(e)}})
                )
        return msg_id

    def _send_notification(self, method: str, params: dict):
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        try:
            self.endpoint.send_request(msg)
        except Exception as e:
            logger.error(f"[LSP] Send notification error: {e}")

    def _invoke_callback(self, callback, msg):
        """槽函数：确保 callback 在主线程调用"""
        callback(msg)

    def _listen_messages(self):
        while self._running and self.process:
            try:
                msg = self.endpoint.recv_response()
                if msg is None:
                    break
                if 'id' in msg:
                    with self._lock:
                        callback = self._response_callbacks.pop(msg['id'], None)
                    if callback:
                        QMetaObject.invokeMethod(
                            self, "_invoke_callback",
                            Qt.QueuedConnection,
                            Q_ARG(object, callback),
                            Q_ARG(object, msg)
                        )
                elif 'method' in msg:
                    if msg['method'] == 'textDocument/publishDiagnostics':
                        uri = msg['params']['uri']
                        diagnostics = msg['params'].get('diagnostics', [])
                        session = self.find_session_by_uri(uri)
                        if session:
                            session._on_diagnostics(diagnostics)
            except Exception as e:
                if self._running:
                    logger.error(f"[LSP] Listen error: {e}")
                break

    def _log_stderr(self):
        if self.process and self.process.stderr:
            for line in self.process.stderr:
                if line:
                    decoded = line.decode('utf-8', errors='replace').strip()
                    if decoded:
                        logger.error(f"[LSP stderr] {decoded}")

    def is_alive(self):
        return self.process and self.process.poll() is None

    def shutdown(self):
        if not self._running:
            return
        self._running = False
        if self.process and self.process.poll() is None:
            try:
                self._send_request("shutdown", {}, lambda _: None)
                time.sleep(0.1)
                self._send_notification("exit", {})
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                if self.process:
                    self.process.kill()
                    self.process.wait()
        # 清理
        self._sessions.clear()
        self._response_callbacks.clear()
        LspProcessManager._instance = None