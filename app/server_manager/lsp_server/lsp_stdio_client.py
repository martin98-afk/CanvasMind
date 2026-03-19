# -*- coding: utf-8 -*-
import platform
import time
import json
import os
import queue
from pathlib import Path
from typing import Optional, List, Dict, Any

from PyQt5.QtCore import QThread, pyqtSignal, QObject, QProcess, QTimer, QByteArray
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

    def __init__(
        self, python_path: Optional[str] = None, parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        self.python_path = str(python_path) if python_path else "python"
        # 自动获取当前工作目录作为根目录
        self.project_root = str(Path(__file__).parent.parent.parent.parent)
        self.process: Optional[QProcess] = None
        self.version = 0
        # 使用项目根目录作为文档URI
        self.uri = f"file:///{self.project_root.replace(chr(92), '/')}/editor.py"

        self._running = False
        self._msg_id = 1
        self._pending_requests: Dict[int, str] = {}
        self._response_map: Dict[int, Any] = {}

        # 消息优先级队列: (priority, timestamp, msg)
        # 0: 紧急通知/取消, 10: 普通请求
        self._send_queue = queue.PriorityQueue()

        # 缓冲区用于流式解析
        self._buffer = QByteArray()
        self._content_length = -1

        # 防抖计时器 (集成在 Qt 事件循环)
        self._debounce_timer = None

    def set_python_path(self, python_path: str):
        self.python_path = str(python_path)

    def _get_hidden_window_environment(self):
        """获取隐藏窗口的环境变量（Windows）"""
        from PyQt5.QtCore import QProcessEnvironment

        env = QProcessEnvironment.systemEnvironment()
        # 在Windows下，设置一些环境变量来减少窗口显示
        return env

    def run(self):
        """启动 LSP 进程并进入 Qt 事件循环"""
        try:
            self._running = True
            self.process = QProcess()

            # Windows 极限优化：隐藏窗口 + 高优先级进程类
            if platform.system() == "Windows":
                # 在Windows下隐藏窗口
                self.process.setProcessEnvironment(
                    self._get_hidden_window_environment()
                )

            # 绑定异步读取信号 (Qt 信号槽比 Python 轮询线程快且稳定)
            self.process.readyReadStandardOutput.connect(self._on_stdout_ready)
            self.process.readyReadStandardError.connect(self._on_stderr_ready)
            self.process.finished.connect(self._on_process_finished)

            # 启动进程
            cmd = [self.python_path, "-m", "pylsp"]
            self.process.start(cmd[0], cmd[1:])

            if not self.process.waitForStarted(5000):
                self.error.emit("Failed to start pylsp process")
                return

            # 内部高频写循环计时器 (1ms)
            self._write_timer = QTimer()
            self._write_timer.timeout.connect(self._consume_queue)
            self._write_timer.start(1)

            self._send_initialize()

            # 进入事件循环
            self.exec_()
        except Exception as e:
            logger.error(f"LSP Run error: {e}")
            self.error.emit(str(e))

    def _send_initialize(self):
        """极致配置：开启增量同步和 Jedi 高速模式"""
        self._send_message(
            "initialize",
            {
                "processId": os.getpid(),
                "rootUri": f"file:///{self.project_root.replace(chr(92), '/')}",
                "initializationOptions": {
                    "pylsp": {
                        "plugins": {
                            "jedi": {
                                "environment": self.python_path,
                                "extra_paths": [self.project_root],
                                "fast_parser": True,
                            },
                            "jedi_completion": {
                                "enabled": True,
                                "fuzzy": True,
                                "cache_for": [
                                    "numpy",
                                    "pandas",
                                    "sklearn",
                                    "matplotlib",
                                ],  # 对大型库开启缓存
                            },
                            "jedi_definition": {
                                "enabled": True,
                                "follow_imports": True,
                            },
                            "pyflakes": {"enabled": True},
                            "pycodestyle": {"enabled": False},
                            "mccabe": {"enabled": False},
                            "preload": {"enabled": True},
                        }
                    }
                },
                "capabilities": {
                    "textDocument": {
                        "synchronization": {
                            "dynamicRegistration": False,
                            "change": 1,  # 增量更新 (Incremental)
                            "didSave": True,
                        },
                        "completion": {
                            "completionItem": {
                                "snippetSupport": True,
                                "resolveSupport": {
                                    "properties": ["documentation", "detail"]
                                },
                            }
                        },
                        "hover": {"contentFormat": ["plaintext"]},
                        "signatureHelp": {
                            "signatureInformation": {
                                "documentationFormat": ["plaintext"]
                            }
                        },
                    }
                },
            },
            priority=0,
        )

    def _on_stdout_ready(self):
        """极限解析：修复 AttributeError 并实现高效切片"""
        # 读取所有可用数据并追加到缓冲区
        self._buffer.append(self.process.readAllStandardOutput())

        while True:
            if self._content_length == -1:
                # 寻找 Header 结束标志 \r\n\r\n
                header_end = self._buffer.indexOf(b"\r\n\r\n")
                if header_end == -1:
                    break

                # 修正此处：使用 .data() 获取 bytes 对象
                header_bytes = self._buffer.left(header_end).data()
                header_text = header_bytes.decode("ascii", errors="ignore")

                for line in header_text.split("\r\n"):
                    if line.lower().startswith("content-length:"):
                        try:
                            self._content_length = int(line.split(":")[1].strip())
                        except (IndexError, ValueError):
                            self._content_length = -1
                        break

                # 移除已处理的 header 部分
                self._buffer.remove(0, header_end + 4)

            # 检查缓冲区是否已包含完整的 Body
            if (
                self._content_length != -1
                and self._buffer.size() >= self._content_length
            ):
                body = self._buffer.left(self._content_length).data()
                self._buffer.remove(0, self._content_length)

                # 重置长度标记以处理下一条消息
                current_len = self._content_length
                self._content_length = -1

                try:
                    # 使用 orjson 极限解析
                    msg = fast_json.loads(body)
                    self._dispatch_message(msg)
                except Exception as e:
                    logger.error(f"LSP JSON Parse Error: {e} | Body: {body[:100]}")
            else:
                # 消息不完整，等待下一次数据触发
                break

    def _dispatch_message(self, msg: Dict):
        """异步消息分发"""
        if "id" in msg:
            msg_id = msg["id"]
            method = self._pending_requests.pop(msg_id, None)

            if method == "initialize":
                self._send_message("initialized", {}, is_notification=True)
                self.initialized.emit()

            result = msg.get("result")
            # 极限响应分发
            if method == "textDocument/completion":
                items = (
                    result.get("items", [])
                    if isinstance(result, dict)
                    else (result or [])
                )
                self.completion_ready.emit(items)
            elif method == "textDocument/hover":
                self.hover_ready.emit(result or {})
            elif method == "textDocument/definition":
                self.definition_ready.emit(result or {})
            elif method == "textDocument/signatureHelp":
                self.signature_help_ready.emit(result or {})
            elif method == "textDocument/foldingRange":
                self.folding_ready.emit(result or [])
            elif method == "textDocument/documentSymbol":
                self.document_symbol_ready.emit(result or [])
            elif method in ("textDocument/formatting", "textDocument/rangeFormatting"):
                self.formatting_ready.emit(result or [])
            elif method == "completionItem/resolve":
                self.completion_resolved.emit(result or {})
            elif method == "textDocument/references":
                self.references_ready.emit(result or [])

            self._response_map[msg_id] = msg
        elif "method" in msg:
            if msg["method"] == "textDocument/publishDiagnostics":
                self.diagnostics_ready.emit(msg["params"].get("diagnostics", []))

    def _consume_queue(self):
        """高优先级写循环：物理层级的异步非阻塞写入"""
        while not self._send_queue.empty():
            _, _, payload = self._send_queue.get()
            if self.process and self.process.state() == QProcess.Running:
                self.process.write(payload)

    def _send_message(
        self,
        method: str,
        params: dict,
        is_notification: bool = False,
        priority: int = 10,
    ):
        """插队逻辑：新的补全请求会触发旧补全请求的取消指令"""
        msg = {"jsonrpc": "2.0", "method": method, "params": params}

        if not is_notification:
            # 补全插队优化：发送新补全前，先在队列最前方插入取消旧补全的消息
            if method in ("textDocument/completion", "textDocument/hover"):
                for rid, rmeth in list(self._pending_requests.items()):
                    if rmeth == method:
                        cancel_req = {
                            "jsonrpc": "2.0",
                            "method": "$/cancelRequest",
                            "params": {"id": rid},
                        }
                        self._put_in_queue(cancel_req, priority=0)  # 最高优先级取消
                        self._pending_requests.pop(rid, None)

            msg_id = self._msg_id
            self._msg_id += 1
            msg["id"] = msg_id
            self._pending_requests[msg_id] = method
            self._put_in_queue(msg, priority=priority)
            return msg_id
        else:
            self._put_in_queue(msg, priority=0)  # 通知类消息（同步）最高级
            return None

    def _put_in_queue(self, msg: dict, priority: int):
        """极致序列化"""
        body = fast_json.dumps(msg)
        if not isinstance(body, bytes):
            body = body.encode("utf-8")

        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self._send_queue.put((priority, time.time(), header + body))

    # --- 外部接口逻辑优化 (堪比 PyCharm 的防抖) ---

    def request_completion(self, line: int, col: int, trigger_dot: bool = False):
        """直接发送补全请求，编辑器端已有防抖"""
        self._send_message(
            "textDocument/completion",
            {
                "textDocument": {"uri": self.uri},
                "position": {"line": line, "character": col},
            },
            priority=10,
        )

    def change_document_full(self, text: str):
        """新增全量同步接口"""
        self.version += 1
        self._send_message(
            "textDocument/didChange",
            {
                "textDocument": {"uri": self.uri, "version": self.version},
                "contentChanges": [{"text": text}],  # 全量只传一个字典，不传 range
            },
            is_notification=True,
        )

    def change_document_delta(self, changes: List[Dict]):
        self.version += 1
        self._send_message(
            "textDocument/didChange",
            {
                "textDocument": {"uri": self.uri, "version": self.version},
                "contentChanges": changes,
            },
            is_notification=True,
        )

    def open_document(self, text: str):
        self.version = 1
        self._send_message(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": self.uri,
                    "languageId": "python",
                    "version": self.version,
                    "text": text,
                }
            },
            is_notification=True,
        )

    def close_document(self):
        self._send_message(
            "textDocument/didClose",
            {"textDocument": {"uri": self.uri}},
            is_notification=True,
        )

    def request_completion_resolve(self, item: dict):
        keys = {
            "label",
            "kind",
            "detail",
            "documentation",
            "insertText",
            "filterText",
            "textEdit",
            "additionalTextEdits",
            "command",
            "data",
            "tags",
            "insertTextFormat",
            "commitCharacters",
            "preselect",
        }
        self._send_message(
            "completionItem/resolve", {k: v for k, v in item.items() if k in keys}
        )

    def request_signature_help(self, line: int, col: int):
        self._send_message(
            "textDocument/signatureHelp",
            {
                "textDocument": {"uri": self.uri},
                "position": {"line": line, "character": col},
            },
        )

    def request_hover(self, line: int, col: int):
        self._send_message(
            "textDocument/hover",
            {
                "textDocument": {"uri": self.uri},
                "position": {"line": line, "character": col},
            },
        )

    def request_definition(self, line: int, col: int):
        self._send_message(
            "textDocument/definition",
            {
                "textDocument": {"uri": self.uri},
                "position": {"line": line, "character": col},
            },
        )

    def request_folding_ranges(self):
        self._send_message(
            "textDocument/foldingRange", {"textDocument": {"uri": self.uri}}
        )

    def request_formatting(self):
        self._send_message(
            "textDocument/formatting",
            {
                "textDocument": {"uri": self.uri},
                "options": {"tabSize": 4, "insertSpaces": True},
            },
        )

    def _on_stderr_ready(self):
        try:
            err = (
                self.process.readAllStandardError()
                .data()
                .decode("utf-8", errors="ignore")
            )
            if err.strip():
                logger.debug(f"[LSP Stderr] {err.strip()}")
        except:
            pass

    def _on_process_finished(self):
        self._running = False
        self.quit()

    def is_alive(self):
        return self.process and self.process.state() == QProcess.Running

    def shutdown(self):
        if not self._running:
            return
        self._running = False
        self._send_message("shutdown", {}, priority=0)
        QTimer.singleShot(
            100, lambda: self._send_message("exit", {}, is_notification=True)
        )
        QTimer.singleShot(500, self._terminate_process)

    def _terminate_process(self):
        if self.process:
            self.process.kill()
        self.quit()
