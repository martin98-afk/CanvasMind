from typing import Optional, List, Dict

from PyQt5.QtCore import pyqtSignal, QObject

from app.server_manager.lsp_server.in_develop.lsp_manager import LspProcessManager


# ==============================
# 每个文档的会话（每个编辑器一个）
# ==============================
class LspDocumentSession(QObject):
    completion_ready = pyqtSignal(list)
    diagnostics_ready = pyqtSignal(list)
    folding_ready = pyqtSignal(list)
    formatting_ready = pyqtSignal(list)
    hover_ready = pyqtSignal(dict)
    definition_ready = pyqtSignal(list)
    references_ready = pyqtSignal(list)
    document_symbol_ready = pyqtSignal(list)
    completion_resolved = pyqtSignal(dict)

    def __init__(self, python_path: str, uri: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.python_path = python_path
        self.uri = uri
        self.version = 0
        self._is_open = False
        self._lsp_manager = LspProcessManager(python_path)
        if self._lsp_manager.is_alive():
            self._lsp_manager.start_lsp(self.python_path)
        self._lsp_manager.register_session(self)

    def is_lsp_alive(self):
        return self._lsp_manager.is_alive()

    def open(self, text: str):
        if self._is_open:
            return
        self.version = 1
        self._is_open = True
        self._lsp_manager._send_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": self.uri,
                "languageId": "python",
                "version": self.version,
                "text": text
            }
        })

    def change(self, text: str):
        if not self._is_open:
            return
        self.version += 1
        self._lsp_manager._send_notification("textDocument/didChange", {
            "textDocument": {"uri": self.uri, "version": self.version},
            "contentChanges": [{"text": text}]
        })

    def change_delta(self, changes: List[Dict]):
        if not self._is_open:
            return
        self.version += 1
        self._lsp_manager._send_notification("textDocument/didChange", {
            "textDocument": {"uri": self.uri, "version": self.version},
            "contentChanges": changes
        })

    def close(self):
        if not self._is_open:
            return
        self._lsp_manager._send_notification("textDocument/didClose", {
            "textDocument": {"uri": self.uri}
        })
        self._is_open = False
        self._lsp_manager.unregister_session(self.uri)

    def _on_diagnostics(self, diagnostics: list):
        self.diagnostics_ready.emit(diagnostics)

    def _make_callback(self, signal):
        def callback(msg):
            if 'error' in msg:
                err = msg['error'].get('message', 'LSP request failed')
                
                return
            result = msg.get('result', [])
            signal.emit(result)
        return callback

    def request_completion(self, line: int, col: int):
        self._lsp_manager._send_request("textDocument/completion", {
            "textDocument": {"uri": self.uri},
            "position": {"line": line, "character": col}
        }, self._make_completion_callback())

    def _make_completion_callback(self):
        def callback(msg):
            if 'error' in msg:
                err = msg['error'].get('message', 'Completion failed')
                return
            result = msg.get('result')
            items = []
            if result is not None:
                if isinstance(result, dict) and 'items' in result:
                    items = result['items']
                elif isinstance(result, list):
                    items = result
            self.completion_ready.emit(items)
        return callback

    def request_completion_resolve(self, item: dict):
        self._lsp_manager._send_request("completionItem/resolve", item, self._make_callback(self.completion_resolved))

    def request_folding_ranges(self):
        self._lsp_manager._send_request("textDocument/foldingRange", {
            "textDocument": {"uri": self.uri}
        }, self._make_callback(self.folding_ready))

    def request_hover(self, line: int, col: int):
        self._lsp_manager._send_request("textDocument/hover", {
            "textDocument": {"uri": self.uri},
            "position": {"line": line, "character": col}
        }, self._make_callback(self.hover_ready))

    def request_definition(self, line: int, col: int):
        self._lsp_manager._send_request("textDocument/definition", {
            "textDocument": {"uri": self.uri},
            "position": {"line": line, "character": col}
        }, self._make_callback(self.definition_ready))

    def request_references(self, line: int, col: int):
        self._lsp_manager._send_request("textDocument/references", {
            "textDocument": {"uri": self.uri},
            "position": {"line": line, "character": col},
            "context": {"includeDeclaration": True}
        }, self._make_callback(self.references_ready))

    def request_symbol(self):
        self._lsp_manager._send_request("textDocument/documentSymbol", {
            "textDocument": {"uri": self.uri}
        }, self._make_callback(self.document_symbol_ready))

    def request_formatting(self):
        self._lsp_manager._send_request("textDocument/formatting", {
            "textDocument": {"uri": self.uri},
            "options": {"tabSize": 4, "insertSpaces": True}
        }, self._make_callback(self.formatting_ready))

    def request_range_formatting(self, start_line, start_col, end_line, end_col):
        self._lsp_manager._send_request("textDocument/rangeFormatting", {
            "textDocument": {"uri": self.uri},
            "range": {
                "start": {"line": start_line, "character": start_col},
                "end": {"line": end_line, "character": end_col}
            },
            "options": {"tabSize": 4, "insertSpaces": True}
        }, self._make_callback(self.formatting_ready))