# execution_context.py
import threading
from typing import Optional

class ExecutionContext:
    def __init__(self):
        self._cancel_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # ✅ 初始为“继续”状态！
        self._is_paused_val = False  # 仅用于 UI 查询，不用于逻辑判断

    def cancel(self):
        self._cancel_event.set()

    def pause(self):
        self._pause_event.clear()
        self._is_paused_val = True

    def resume(self):
        self._pause_event.set()
        self._is_paused_val = False

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def is_paused(self) -> bool:
        return self._is_paused_val

    def check_cancel(self) -> bool:
        return self.is_cancelled()

    def wait_if_paused(self):
        """
        安全等待：支持在暂停状态下被取消
        """
        while not self._pause_event.is_set():
            if self._cancel_event.is_set():
                return  # 立即退出
            # 短暂等待，避免忙等，同时保持响应性
            self._pause_event.wait(timeout=0.05)  # 50ms 轮询