# 新增 LSP 客户端管理器
import subprocess
from pylspclient import LspClient, ReadPipe, WritePipe
from PyQt5.QtCore import QThread, pyqtSignal

class LspClientManager(QThread):
    completion_ready = pyqtSignal(list)  # [(label, kind, detail, documentation), ...]
    diagnostics_ready = pyqtSignal(list)
    initialized = pyqtSignal()

    def __init__(self, python_path=None, parent=None):
        super().__init__(parent)
        self.python_path = python_path or sys.executable
        self.lsp_client = None
        self.process = None
        self.version = 0
        self.uri = "file:///tmp/inline.py"

    def run(self):
        # 启动 pylsp
        cmd = [self.python_path, "-m", "pylsp"]
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        read_pipe = ReadPipe(self.process.stdout)
        write_pipe = WritePipe(self.process.stdin)
        self.lsp_client = LspClient(read_pipe, write_pipe)

        # 初始化
        self.lsp_client.initialize(
            processId=self.process.pid,
            rootUri="file:///tmp",
            capabilities={
                "textDocument": {
                    "completion": {"completionItem": {"documentationFormat": ["plaintext"]}},
                    "publishDiagnostics": {}
                }
            },
            initializationOptions={
                "pylsp": {
                    "plugins": {
                        "jedi_completion": {"enabled": True},
                        "pycodestyle": {"enabled": False},
                        "pyflakes": {"enabled": True}
                    }
                }
            }
        )
        self.lsp_client.initialized()
        self.initialized.emit()

    def open_document(self, text: str):
        self.version += 1
        self.lsp_client.didOpen({
            "textDocument": {
                "uri": self.uri,
                "languageId": "python",
                "version": self.version,
                "text": text
            }
        })

    def change_document(self, text: str):
        self.version += 1
        self.lsp_client.didChange({
            "textDocument": {"uri": self.uri, "version": self.version},
            "contentChanges": [{"text": text}]
        })

    def request_completion(self, line: int, col: int):
        try:
            result = self.lsp_client.completion({
                "textDocument": {"uri": self.uri},
                "position": {"line": line, "character": col}
            })
            items = result.get("items", []) if result else []
            completions = []
            for item in items:
                label = item.get("label", "")
                kind = item.get("kind", 0)  # 1=Text, 2=Method, 3=Function, 5=Field, 7=Class...
                detail = item.get("detail", "")
                doc = item.get("documentation", "")
                completions.append((label, kind, detail, doc))
            self.completion_ready.emit(completions)
        except Exception as e:
            print(f"[LSP] Completion error: {e}")

    def shutdown(self):
        if self.lsp_client:
            self.lsp_client.shutdown()
            self.lsp_client.exit()
        if self.process:
            self.process.terminate()
            self.process.wait()