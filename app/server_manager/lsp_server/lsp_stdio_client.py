# -*- coding: utf-8 -*-
import platform
import subprocess
import threading
import time
import json
import queue
from typing import Optional, List, Dict, Any

from PyQt5.QtCore import QThread, pyqtSignal, QObject
from loguru import logger


class LspClientManager(QThread):
    # 信号定义
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
        self.python_path = python_path
        self.process: Optional[subprocess.Popen] = None
        self.version = 0
        self.uri = "file:///tmp/editor.py"

        self._running = False
        self._msg_id = 1
        self._response_map: Dict[int, Any] = {}
        self._pending_requests: Dict[int, str] = {}
        self._lock = threading.Lock()

        # 优化引入：发送队列与读写线程
        self._send_queue = queue.Queue()
        self._debounce_timer: Optional[threading.Timer] = None
        self._init_event = threading.Event()

    def set_python_path(self, python_path: str):
        self.python_path = python_path

    def run(self):
        try:
            self._running = True
            self._init_event.clear()

            # 使用列表构建命令，确保路径包含空格也能正常运行
            cmd = [self.python_path, "-m", "pylsp"]

            kwargs = {
                "stdin": subprocess.PIPE,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "bufsize": 0  # 无缓冲模式
            }
            if platform.system() == "Windows":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            self.process = subprocess.Popen(cmd, **kwargs)

            # 启动辅助线程
            threading.Thread(target=self._log_stderr, daemon=True).start()
            threading.Thread(target=self._write_loop, daemon=True).start()
            threading.Thread(target=self._listen_messages, daemon=True).start()

            # 初始化 LSP Server
            init_id = self._send_message("initialize", {
                "processId": self.process.pid,
                "rootUri": "file:///tmp",
                "initializationOptions": {
                    "pylsp": {
                        "plugins": {
                            'jedi': {
                                'environment': str(self.python_path),
                                'extra_paths': []
                            },
                            "jedi_completion": {"enabled": True, "fuzzy": True},
                            "jedi_definition": {"enabled": True},
                            "jedi_hover": {"enabled": True},
                            "jedi_signature_help": {"enabled": True},
                            "jedi_references": {"enabled": True},
                            "pyflakes": {"enabled": True},
                            "folding": {"enabled": True},
                            "pycodestyle": {"enabled": False},
                            "mccabe": {"enabled": False},
                            "preload": {"enabled": True}
                        }
                    }
                },
                "capabilities": {
                    "textDocument": {
                        "completion": {
                            "completionItem": {
                                "documentationFormat": ["plaintext"],
                                "snippetSupport": True,
                                "insertTextMode": 1
                            }
                        },
                        "publishDiagnostics": {},
                        "hover": {"dynamicRegistration": False},
                        "signatureHelp": {"signatureInformation": {"documentationFormat": ["plaintext"]}},
                        "definitionProvider": True,
                        "referencesProvider": True,
                        "documentSymbolProvider": True,
                        "documentFormattingProvider": True,
                    }
                }
            })

            # 等待回包触发 _init_event
            if self._init_event.wait(timeout=15.0):
                self._send_message("initialized", {}, is_notification=True)
                self.initialized.emit()
            else:
                if self.process.poll() is not None:
                    raise RuntimeError("LSP process exited unexpectedly.")
                raise TimeoutError("LSP server initialize response timeout")

        except Exception as e:
            logger.error(f"[LSP] Startup error: {e}")
            self.error.emit(str(e))

    def _write_loop(self):
        """异步发送线程"""
        while self._running and self.process:
            try:
                msg = self._send_queue.get(timeout=1.0)
                json_str = json.dumps(msg, separators=(',', ':'))
                content = f"Content-Length: {len(json_str)}\r\n\r\n{json_str}"
                self.process.stdin.write(content.encode('utf-8'))
                self.process.stdin.flush()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"[LSP Write] Error: {e}")
                break

    def _listen_messages(self):
        """核心修复：健壮的 LSP 消息解析器"""
        while self._running and self.process:
            try:
                content_length = 0
                # 循环读取所有 Header，直到遇到空行 \r\n
                while True:
                    line = self.process.stdout.readline()
                    if not line: return
                    line_str = line.decode('utf-8').strip()
                    if not line_str:  # 空行代表 Header 结束
                        break
                    if line_str.lower().startswith("content-length:"):
                        content_length = int(line_str.split(":")[1].strip())

                if content_length > 0:
                    # 按照字节长度精准读取，防止 JSON 解析报错
                    body_bytes = self.process.stdout.read(content_length)
                    if not body_bytes: return

                    msg = json.loads(body_bytes.decode('utf-8'))
                    self._dispatch_message(msg)
            except Exception as e:
                if self._running:
                    logger.error(f"[LSP Listen] Error: {e}")
                break

    def _dispatch_message(self, msg: Dict):
        """消息分发与信号发射"""
        if 'id' in msg:
            msg_id = msg['id']
            method = None
            with self._lock:
                method = self._pending_requests.pop(msg_id, None)
                self._response_map[msg_id] = msg

            # 无论 ID 是多少，只要是 initialize 的回包就解锁
            if method == "initialize" or msg_id == 1:
                self._init_event.set()

            result = msg.get('result')
            if method == "textDocument/completion":
                items = result.get('items', []) if isinstance(result, dict) else (result or [])
                self.completion_ready.emit(items)
            elif method == "textDocument/foldingRange":
                self.folding_ready.emit(result or [])
            elif method in ("textDocument/formatting", "textDocument/rangeFormatting"):
                self.formatting_ready.emit(result or [])
            elif method == "textDocument/definition":
                self.definition_ready.emit(result or {})
            elif method == "textDocument/references":
                self.references_ready.emit(result or [])
            elif method == "textDocument/documentSymbol":
                self.document_symbol_ready.emit(result or [])
            elif method == "textDocument/hover":
                self.hover_ready.emit(result or {})
            elif method == "completionItem/resolve":
                self.completion_resolved.emit(result or {})
            elif method == "textDocument/signatureHelp":
                self.signature_help_ready.emit(result or {})

        elif 'method' in msg:
            if msg['method'] == 'textDocument/publishDiagnostics':
                diagnostics = msg['params'].get('diagnostics', [])
                self.diagnostics_ready.emit(diagnostics)

    def _send_message(self, method: str, params: dict, is_notification: bool = False):
        """带取消机制的消息发送"""
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        if not is_notification:
            with self._lock:
                # 顺滑逻辑：取消同类型的老请求
                if method in ("textDocument/completion", "textDocument/signatureHelp", "textDocument/hover"):
                    cancelled_ids = [k for k, v in self._pending_requests.items() if v == method]
                    for cid in cancelled_ids:
                        self._send_queue.put({"jsonrpc": "2.0", "method": "$/cancelRequest", "params": {"id": cid}})
                        self._pending_requests.pop(cid, None)

                msg_id = self._msg_id
                self._msg_id += 1
                msg["id"] = msg_id
                self._pending_requests[msg_id] = method
            self._send_queue.put(msg)
            return msg_id
        else:
            self._send_queue.put(msg)
            return None

    def _wait_for_response(self, msg_id: int, timeout: float = 5.0):
        start = time.time()
        while time.time() - start < timeout:
            with self._lock:
                if msg_id in self._response_map:
                    return self._response_map.pop(msg_id)
            time.sleep(0.005)
        return None

    def _log_stderr(self):
        if self.process and self.process.stderr:
            for line in self.process.stderr:
                if line:
                    decoded = line.decode('utf-8', errors='replace').strip()
                    if decoded: logger.debug(f"[LSP stderr] {decoded}")

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
        if self._debounce_timer: self._debounce_timer.cancel()

        def do_req():
            self._send_message("textDocument/completion", {
                "textDocument": {"uri": self.uri}, "position": {"line": line, "character": col}
            })

        self._debounce_timer = threading.Timer(0.05, do_req)
        self._debounce_timer.start()

    def request_completion_resolve(self, item: dict):
        keys = {'label', 'kind', 'detail', 'documentation', 'insertText', 'filterText', 'textEdit',
                'additionalTextEdits', 'command', 'data', 'tags', 'insertTextFormat', 'commitCharacters', 'preselect'}
        self._send_message("completionItem/resolve", {k: v for k, v in item.items() if k in keys})

    def request_signature_help(self, line: int, col: int):
        self._send_message("textDocument/signatureHelp", {
            "textDocument": {"uri": self.uri}, "position": {"line": line, "character": col}
        })

    def request_hover(self, line: int, col: int):
        self._send_message("textDocument/hover", {
            "textDocument": {"uri": self.uri}, "position": {"line": line, "character": col}
        })

    def request_definition(self, line: int, col: int):
        self._send_message("textDocument/definition", {
            "textDocument": {"uri": self.uri}, "position": {"line": line, "character": col}
        })

    def request_folding_ranges(self):
        self._send_message("textDocument/foldingRange", {"textDocument": {"uri": self.uri}})

    def request_formatting(self):
        self._send_message("textDocument/formatting", {
            "textDocument": {"uri": self.uri}, "options": {"tabSize": 4, "insertSpaces": True}
        })

    def is_alive(self):
        return self._running and self.process and self.process.poll() is None

    def shutdown(self):
        if not self._running: return
        self._running = False
        if self._debounce_timer: self._debounce_timer.cancel()
        if self.process and self.process.poll() is None:
            try:
                self._send_message("shutdown", {})
                time.sleep(0.1)
                self._send_message("exit", {}, is_notification=True)
                self.process.terminate()
                self.process.wait(timeout=1.0)
            except:
                if self.process: self.process.kill()

    def stop(self):
        self.shutdown()
        self.wait()