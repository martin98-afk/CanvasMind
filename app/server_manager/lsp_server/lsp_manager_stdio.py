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
    # 异步信号：不再在 request_* 中阻塞等待
    completion_ready = pyqtSignal(list)       # List[CompletionItem]
    diagnostics_ready = pyqtSignal(list)      # List[Diagnostic]
    folding_ready = pyqtSignal(list)          # List[FoldingRange]
    formatting_ready = pyqtSignal(list)  # List[TextEdit]
    hover_ready = pyqtSignal(dict)  # hover content
    definition_ready = pyqtSignal(dict)  # location
    references_ready = pyqtSignal(list)
    document_symbols_ready = pyqtSignal(list)
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
        self._pending_requests: Dict[int, str] = {}  # msg_id -> method
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

            # Only initialize is allowed to block
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
            })

            response = self._wait_for_response(init_id, timeout=10.0)
            if not response:
                raise TimeoutError("Initialize timeout")

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
                        items = []
                        if result is not None:
                            if isinstance(result, dict) and 'items' in result:
                                items = result['items']
                            elif isinstance(result, list):
                                items = result
                        self.completion_ready.emit(items)
                    elif method == "textDocument/foldingRange":
                        result = msg.get('result') or []
                        self.folding_ready.emit(result)
                    elif method == "textDocument/formatting" or method == "textDocument/rangeFormatting":
                        edits = msg.get('result') or []
                        self.formatting_ready.emit(edits)
                    elif method == "textDocument/definition":
                        result = msg.get('result') or []
                        self.definition_ready.emit(result)
                    elif method == "textDocument/references":
                        result = msg.get('result') or []
                        self.references_ready.emit(result)
                    elif method == "textDocument/documentSymbol":
                        result = msg.get('result') or []
                        self.document_symbol_ready.emit(result)
                    elif method == "textDocument/hover":
                        result = msg.get('result') or []
                        self.hover_ready.emit(result)

                    # Optional: keep generic response for debug
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
        """Only used during initialization."""
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
            "textDocument": {
                "uri": self.uri,
                "languageId": "python",
                "version": self.version,
                "text": text
            }
        }, is_notification=True)

    def change_document(self, text: str):
        """Simple full-text replacement (for compatibility).
        For better performance, implement delta changes in the editor layer."""
        self.version += 1
        self._send_message("textDocument/didChange", {
            "textDocument": {"uri": self.uri, "version": self.version},
            "contentChanges": [{"text": text}]
        }, is_notification=True)

    def change_document_delta(self, changes: List[Dict]):
        """Efficient incremental update. Call this if your editor tracks edits.
        Example change:
        {
            "range": {"start": {"line": 1, "character": 2}, "end": {"line": 1, "character": 2}},
            "text": "new"
        }
        """
        self.version += 1
        self._send_message("textDocument/didChange", {
            "textDocument": {"uri": self.uri, "version": self.version},
            "contentChanges": changes
        }, is_notification=True)

    def request_symbol(self):
        """Non-blocking. Result arrives via `document_symbol_ready` signal."""
        self._send_message("textDocument/documentSymbol", {
            "textDocument": {"uri": self.uri}
        })

    def request_completion(self, line: int, col: int):
        """Non-blocking. Result arrives via `completion_ready` signal."""
        self._send_message("textDocument/completion", {
            "textDocument": {"uri": self.uri},
            "position": {"line": line, "character": col}
        })

    def request_folding_ranges(self):
        """Non-blocking. Result arrives via `folding_ready` signal."""
        self._send_message("textDocument/foldingRange", {
            "textDocument": {"uri": self.uri}
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

    def request_formatting(self):
        """Format entire document"""
        self._send_message("textDocument/formatting", {
            "textDocument": {"uri": self.uri},
            "options": {
                "tabSize": 4,
                "insertSpaces": True
            }
        })

    def request_range_formatting(self, start_line, start_col, end_line, end_col):
        """Format selected range"""
        self._send_message("textDocument/rangeFormatting", {
            "textDocument": {"uri": self.uri},
            "range": {
                "start": {"line": start_line, "character": start_col},
                "end": {"line": end_line, "character": end_col}
            },
            "options": {
                "tabSize": 4,
                "insertSpaces": True
            }
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
        # Join threads if needed (optional, daemon=True so not required)

    def stop(self):
        """Call this explicitly from main thread to shut down safely."""
        self.shutdown()
        self.wait()  # Waits for QThread to finish