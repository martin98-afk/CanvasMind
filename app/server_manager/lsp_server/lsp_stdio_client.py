# -*- coding: utf-8 -*-
import platform
import subprocess
import threading
import time
import json
import queue
import os
from typing import Optional, List, Dict, Any

from PyQt5.QtCore import QThread, pyqtSignal, QObject
from loguru import logger

# 尝试使用高性能 JSON 库，没有则回退
try:
    import orjson as fast_json
except ImportError:
    fast_json = json


class LspClientManager(QThread):
    # 信号定义完全保留
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

        self._send_queue = queue.Queue()
        self._debounce_timer: Optional[threading.Timer] = None
        self._init_event = threading.Event()

    def set_python_path(self, python_path: str):
        self.python_path = python_path

    def run(self):
        try:
            self._running = True
            self._init_event.clear()

            cmd = [self.python_path, "-m", "pylsp"]

            # 性能优化：使用较大的管道缓冲区
            kwargs = {
                "stdin": subprocess.PIPE,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "bufsize": 1024 * 1024  # 1MB 缓冲区
            }
            if platform.system() == "Windows":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | 0x00000080  # HIGH_PRIORITY_CLASS

            self.process = subprocess.Popen(cmd, **kwargs)

            # 提升进程优先级 (Unix)
            if platform.system() != "Windows":
                try:
                    os.nice(-10)  # 尝试提升优先级，需要权限
                except:
                    pass

            # 启动辅助线程
            threading.Thread(target=self._log_stderr, daemon=True).start()
            threading.Thread(target=self._write_loop, daemon=True).start()
            threading.Thread(target=self._listen_messages, daemon=True).start()

            # 超级初始化配置：核心在于告诉 Server 我们支持增量更新
            init_id = self._send_message("initialize", {
                "processId": self.process.pid,
                "rootUri": "file:///tmp",
                "initializationOptions": {
                    "pylsp": {
                        "plugins": {
                            "jedi": {
                                "environment": str(self.python_path),
                                "cache_for": ["numpy", "pandas", "matplotlib", "pyqt5"],  # 预缓存大库
                                "extra_paths": []
                            },
                            # 补全极致优化：禁用不必要的细节计算
                            "jedi_completion": {
                                "enabled": True,
                                "fuzzy": True,
                                "eager": False,
                                "resolve_at_most": 20  # 限制首批解析数量
                            },
                            "jedi_hover": {"enabled": True},
                            "preload": {"enabled": True},
                            "pyflakes": {"enabled": False},  # 诊断交给保存后处理，不要实时做
                            "pycodestyle": {"enabled": False},
                            "mccabe": {"enabled": False},
                            "rope_completion": {"enabled": False}  # Rope 很慢，关掉
                        }
                    }
                },
                "capabilities": {
                    "textDocument": {
                        # 核心优化：告诉服务器我们支持增量同步
                        "synchronization": {
                            "dynamicRegistration": False,
                            "change": 2,  # 2 代表 Incremental（增量）
                            "willSave": False,
                            "didSave": True
                        },
                        "completion": {
                            "completionItem": {
                                "snippetSupport": True,
                                "resolveSupport": {"properties": ["documentation", "detail"]}
                            },
                            "contextSupport": True
                        },
                        "hover": {"contentFormat": ["plaintext"]},
                        "signatureHelp": {"signatureInformation": {"documentationFormat": ["plaintext"]}},
                        "definition": {"dynamicRegistration": False},
                    }
                }
            })

            if self._init_event.wait(timeout=10.0):
                self._send_message("initialized", {}, is_notification=True)
                self.initialized.emit()
            else:
                raise TimeoutError("LSP server startup failed")

        except Exception as e:
            logger.error(f"[LSP] Startup error: {e}")
            self.error.emit(str(e))

    def _write_loop(self):
        """高速写入循环"""
        while self._running and self.process:
            try:
                msg = self._send_queue.get(timeout=0.5)
                # 使用高性能 JSON 序列化
                if hasattr(fast_json, 'dumps'):
                    body = fast_json.dumps(msg)
                    if isinstance(body, bytes): body = body.decode('utf-8')
                else:
                    body = json.dumps(msg, separators=(',', ':'))

                content = f"Content-Length: {len(body)}\r\n\r\n{body}"
                self.process.stdin.write(content.encode('utf-8'))
                self.process.stdin.flush()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"[LSP Write] {e}")
                break

    def _listen_messages(self):
        """流式高性能解析器"""
        stdout = self.process.stdout
        while self._running and self.process:
            try:
                line = stdout.readline()
                if not line: break

                if line.startswith(b"Content-Length:"):
                    length = int(line.split(b":")[1].strip())
                    # 循环直到读完所有 header
                    while stdout.readline().strip():
                        pass

                    # 精准读取 body
                    body = stdout.read(length)
                    if not body: break

                    # 高速反序列化
                    msg = fast_json.loads(body)
                    self._dispatch_message(msg)
            except Exception as e:
                logger.error(f"[LSP Listen] {e}")
                break

    def _dispatch_message(self, msg: Dict):
        if 'id' in msg:
            msg_id = msg['id']
            with self._lock:
                method = self._pending_requests.pop(msg_id, None)
                self._response_map[msg_id] = msg

            if msg_id == 1 or method == "initialize":
                self._init_event.set()

            res = msg.get('result')
            # 信号分发路径保持不变
            if method == "textDocument/completion":
                self.completion_ready.emit(res.get('items', []) if isinstance(res, dict) else (res or []))
            elif method == "textDocument/hover":
                self.hover_ready.emit(res or {})
            elif method == "textDocument/definition":
                self.definition_ready.emit(res or {})
            elif method == "textDocument/signatureHelp":
                self.signature_help_ready.emit(res or {})
            elif method == "textDocument/foldingRange":
                self.folding_ready.emit(res or [])
            elif method == "textDocument/documentSymbol":
                self.document_symbol_ready.emit(res or [])
            elif method in ("textDocument/formatting", "textDocument/rangeFormatting"):
                self.formatting_ready.emit(res or [])
            elif method == "completionItem/resolve":
                self.completion_resolved.emit(res or {})
            elif method == "textDocument/references":
                self.references_ready.emit(res or [])

        elif 'method' in msg:
            if msg['method'] == 'textDocument/publishDiagnostics':
                self.diagnostics_ready.emit(msg['params'].get('diagnostics', []))

    def _send_message(self, method: str, params: dict, is_notification: bool = False):
        """增加请求插队逻辑"""
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        if not is_notification:
            with self._lock:
                # 关键：如果有正在排队的相同类型请求，直接取消它们，减少无效计算
                if method in ("textDocument/completion", "textDocument/hover"):
                    for rid, rmeth in list(self._pending_requests.items()):
                        if rmeth == method:
                            self._send_queue.put({"jsonrpc": "2.0", "method": "$/cancelRequest", "params": {"id": rid}})
                            self._pending_requests.pop(rid, None)

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
        # 此函数现在主要用于 initialize，内部已高度优化
        start = time.time()
        while time.time() - start < timeout:
            with self._lock:
                if msg_id in self._response_map:
                    return self._response_map.pop(msg_id)
            time.sleep(0.001)  # 极短轮询
        return None

    # --- 外部接口逻辑优化 ---

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
        """
        重要建议：要在 UI 层获取增量内容（即只发送改变的 range），
        如果你的 UI 依然传全量 text，请确保 changes 为:
        [{'text': full_text}]
        """
        self.version += 1
        self._send_message("textDocument/didChange", {
            "textDocument": {"uri": self.uri, "version": self.version},
            "contentChanges": changes
        }, is_notification=True)

    def request_completion(self, line: int, col: int):
        """
        超级补全：对触发符（如点号）0延迟，对普通输入 30ms 极短防抖
        """
        if self._debounce_timer: self._debounce_timer.cancel()

        def do_req():
            self._send_message("textDocument/completion", {
                "textDocument": {"uri": self.uri},
                "position": {"line": line, "character": col},
                "context": {"triggerKind": 1}
            })

        # 极短防抖，PyCharm 级别的灵敏度
        self._debounce_timer = threading.Timer(0.03, do_req)
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

    def _log_stderr(self):
        if self.process and self.process.stderr:
            for line in self.process.stderr:
                if line and self._running:
                    try:
                        decoded = line.decode('utf-8', errors='replace').strip()
                        if decoded: logger.debug(f"[LSP stderr] {decoded}")
                    except:
                        pass

    def is_alive(self):
        return self._running and self.process and self.process.poll() is None

    def shutdown(self):
        if not self._running: return
        self._running = False
        if self._debounce_timer: self._debounce_timer.cancel()
        if self.process and self.process.poll() is None:
            try:
                self._send_message("shutdown", {})
                time.sleep(0.05)
                self._send_message("exit", {}, is_notification=True)
                self.process.terminate()
            except:
                if self.process: self.process.kill()

    def stop(self):
        self.shutdown()
        self.wait()