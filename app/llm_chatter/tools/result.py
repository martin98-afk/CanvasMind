from typing import Any


class ToolResult:
    def __init__(self, success: bool, content: Any = None, error: str = None):
        self.success = success
        self.content = content
        self.error = error

    def to_dict(self) -> dict:
        if self.success:
            return {"success": True, "content": self.content}
        return {"success": False, "error": self.error}

    def __str__(self):
        if self.success:
            return str(self.content)
        return f"[Error] {self.error}"
