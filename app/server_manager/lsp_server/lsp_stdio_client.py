# -*- coding: utf-8 -*-
import platform
import subprocess
import sys
import threading
import time
from typing import Optional, List, Dict, Any

from PyQt5.QtCore import QThread, pyqtSignal, QObject
from loguru import logger
from pylspclient.json_rpc_endpoint import JsonRpcEndpoint


class LspClientManager(QThread):
    completion_ready = pyqtSignal(list)
    diagnostics_ready = pyqtSignal(list)
    folding_ready = pyqtSignal(list)
    formatting_ready = pyqtSignal(list)
    hover_ready = pyqtSignal(dict)
    definition_ready = pyqtSignal(dict)
    references_ready = pyqtSignal(list)
    document_symbol_ready = pyqtSignal(list)
    completion_resolved = pyqtSignal(dict)
    signature_help_ready = pyqtSignal(dict)
    initialized = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, python_path: Optional[str] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.python_path = python_path or sys.executable
        self.endpoint: Optional[JsonRpcEndpoint] = None
        self.process: Optional[subprocess.Popen] = None
        self.version = 0
        self.uri = "file:///tmp/editor.py"
        self._running = True
        self._msg_id = 1
        self._response_map: Dict[int, Any] = {}
        self._pending_requests: Dict[int, str] = {}
        self._lock = threading.Lock()
        self._notification_thread = None
        self._stderr_thread = None

    def run(self):
        try:
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

            self._stderr_thread = threading.Thread(target=self._log_stderr, daemon=True)
            self._stderr_thread.start()

            self.endpoint = JsonRpcEndpoint(self.process.stdin, self.process.stdout)

            self._notification_thread = threading.Thread(target=self._listen_messages, daemon=True)
            self._notification_thread.start()

            init_id = self._send_message("initialize", {
                "processId": self.process.pid,
                "rootUri": "file:///tmp",
                "initializationOptions": {
                    "pylsp": {
                        "plugins": {
                            'jedi': {
                                'environment': str(self.python_path),  # ← 必须是 python.exe 的完整路径
                                'extra_paths': []  # 如有额外路径可加
                            },
                            "jedi_completion": {"enabled": True, "fuzzy": True},
                            "jedi_definition": {"enabled": True},
                            "jedi_hover": {"enabled": True},
                            "jedi_signature_help": {"enabled": True},
                            "jedi_references": {"enabled": True},
                            "pyflakes": {"enabled": True},
                            "folding": {"enabled": True},
                            "pycodestyle": {"enabled": False},  # ← 关闭
                            "mccabe": {"enabled": False},       # ← 关闭
                            "preload": {"enabled": True}
                        }
                    }
                },
                "capabilities": {
                    "textDocument": {
                        "completionItem": {
                            "documentationFormat": ["plaintext"],
                            "snippetSupport": True,
                            "insertTextMode": 1,
                            "commitCharactersSupport": True
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
                        "documentFormattingProvider": True,
                        "documentRangeFormattingProvider": True,
                    }
                },
                "trace": "off"
            })

            response = self._wait_for_response(init_id, timeout=10.0)
            if not response:
                raise TimeoutError("Initialize timeout")

            self._send_message("initialized", {}, is_notification=True)
            self.initialized.emit()

        except Exception as e:
            logger.error(f"[LSP] Startup error: {e}")
            self.error.emit(str(e))

    def _log_stderr(self):
        if self.process and self.process.stderr:
            for line in self.process.stderr:
                if line:
                    decoded = line.decode('utf-8', errors='replace').strip()
                    if decoded:
                        logger.error(f"[LSP stderr] {decoded}")

    def _listen_messages(self):
        while self._running and self.process:
            try:
                msg = self.endpoint.recv_response()
                if msg is None:
                    break
                if 'id' in msg:
                    method = None
                    with self._lock:
                        method = self._pending_requests.pop(msg['id'], None)
                    if method == "textDocument/completion":
                        result = msg.get('result')
                        items = result.get('items', []) if isinstance(result, dict) else (result or [])
                        self.completion_ready.emit(items)
                    elif method == "textDocument/foldingRange":
                        self.folding_ready.emit(msg.get('result') or [])
                    elif method in ("textDocument/formatting", "textDocument/rangeFormatting"):
                        self.formatting_ready.emit(msg.get('result') or [])
                    elif method == "textDocument/definition":
                        self.definition_ready.emit(msg.get('result') or [])
                    elif method == "textDocument/references":
                        self.references_ready.emit(msg.get('result') or [])
                    elif method == "textDocument/documentSymbol":
                        self.document_symbol_ready.emit(msg.get('result') or [])
                    elif method == "textDocument/hover":
                        self.hover_ready.emit(msg.get('result') or {})
                    elif method == "completionItem/resolve":
                        self.completion_resolved.emit(msg.get('result', {}))
                    elif method == "textDocument/signatureHelp":
                        self.signature_help_ready.emit(msg.get('result', {}))
                    with self._lock:
                        self._response_map[msg['id']] = msg
                elif 'method' in msg and msg['method'] == 'textDocument/publishDiagnostics':
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
                # 丢弃同类高频请求
                if method in ("textDocument/completion", "textDocument/signatureHelp", "textDocument/hover"):
                    keys_to_remove = [k for k, v in self._pending_requests.items() if v == method]
                    for k in keys_to_remove:
                        self._pending_requests.pop(k, None)
                msg_id = self._msg_id
                self._msg_id += 1
                msg["id"] = msg_id
                self._pending_requests[msg_id] = method
            try:
                self.endpoint.send_request(msg)
            except Exception as e:
                logger.error(f"[LSP] Send error: {e}")
                return None
            return msg_id
        else:
            try:
                self.endpoint.send_request(msg)
            except Exception as e:
                logger.error(f"[LSP] Send notification error: {e}")
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
        self.version = 1
        self._send_message("textDocument/didOpen", {
            "textDocument": {"uri": self.uri, "languageId": "python", "version": self.version, "text": text}
        }, is_notification=True)

    def close_document(self):
        self._send_message("textDocument/didClose", {
            "textDocument": {"uri": self.uri}
        }, is_notification=True)

    def change_document_delta(self, changes: List[Dict]):
        self.version += 1
        self._send_message("textDocument/didChange", {
            "textDocument": {"uri": self.uri, "version": self.version},
            "contentChanges": changes
        }, is_notification=True)

    def request_completion(self, line: int, col: int):
        self._send_message("textDocument/completion", {
            "textDocument": {"uri": self.uri},
            "position": {"line": line, "character": col}
        })

    def request_completion_resolve(self, item: dict):
        # 清理非标准字段
        clean_item = {k: v for k, v in item.items() if k in {
            'label', 'kind', 'detail', 'documentation', 'insertText', 'filterText',
            'textEdit', 'additionalTextEdits', 'command', 'data', 'tags',
            'insertTextFormat', 'commitCharacters', 'preselect'
        }}
        self._send_message("completionItem/resolve", clean_item)

    def request_signature_help(self, line: int, col: int):
        self._send_message("textDocument/signatureHelp", {
            "textDocument": {"uri": self.uri},
            "position": {"line": line, "character": col}
        })

    def request_hover(self, line: int, col: int):
        self._send_message("textDocument/hover", {
            "textDocument": {"uri": self.uri},
            "position": {"line": line, "character": col}
        })

    def request_definition(self, line: int, col: int):
        self._send_message("textDocument/definition", {
            "textDocument": {"uri": self.uri},
            "position": {"line": line, "character": col}
        })

    def request_folding_ranges(self):
        self._send_message("textDocument/foldingRange", {"textDocument": {"uri": self.uri}})

    def request_formatting(self):
        self._send_message("textDocument/formatting", {
            "textDocument": {"uri": self.uri},
            "options": {"tabSize": 4, "insertSpaces": True}
        })

    def shutdown(self):
        if not self._running:
            return
        self._running = False
        if self.process and self.process.poll() is None:
            try:
                msg_id = self._send_message("shutdown", {})
                if msg_id is not None:
                    self._wait_for_response(msg_id, timeout=2.0)
                self._send_message("exit", {}, is_notification=True)
            except Exception:
                pass
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()

    def stop(self):
        self.shutdown()
        self.wait()