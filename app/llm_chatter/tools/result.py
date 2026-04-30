from typing import Any


class ToolResult:
    def __init__(self, success: bool, content: Any = None, error: str = None):
        self.success = success
        self.content = content
        # 存储错误信息
        self.error = error

    def to_dict(self) -> dict:
        # 转换为字典
        if self.success:
            return {"success": True, "content": self.content}
        return {"success": False, "error": self.error}  # failure case

    def __str__(self):
        # 转换为字符串
        if self.success:
            return str(self.content)
        return f"[Error] {self.error}"

    def is_success(self) -> bool:
        return self.success
