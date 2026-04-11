import time
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger
from app.widgets.side_dock_area.plugins.llm_chatter.tools.result import ToolResult


class CanvasTools:
    def __init__(self, workdir: Path):
        self.workdir = workdir

    def _get_webhook_manager(self):
        try:
            from app.plugins.trigger_plugins.webhook_trigger import WebhookManager

            return WebhookManager()
        except Exception as e:
            logger.warning(f"[CanvasTools] Failed to get WebhookManager: {e}")
            return None

    def _get_webhook_url(self) -> str:
        manager = self._get_webhook_manager()
        if manager:
            return f"http://{manager.host}:{manager.port}"
        return "http://localhost:5000"

    def list_canvases(self) -> ToolResult:
        try:
            import requests

            base_url = self._get_webhook_url()
            resp = requests.get(f"{base_url}/health", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return ToolResult(True, content=data)
            return ToolResult(
                False, error=f"Failed to get canvases: {resp.status_code}"
            )
        except Exception as e:
            return ToolResult(False, error=f"List canvases error: {str(e)}")

    def trigger_canvas(
        self,
        endpoint: str,
        data: dict = None,
        callback_url: str = None,
        timeout: int = 300,
    ) -> ToolResult:
        import requests

        try:
            base_url = self._get_webhook_url()
            payload = data or {}
            if callback_url:
                payload["callback_url"] = callback_url

            resp = requests.post(
                f"{base_url}/api/v1/trigger/{endpoint}", json=payload, timeout=10
            )
            if resp.status_code != 200:
                return ToolResult(
                    False, error=f"Trigger failed: {resp.status_code} - {resp.text}"
                )

            result = resp.json()
            task_id = result.get("task_id")
            if not task_id:
                return ToolResult(True, content=result)

            start_time = time.time()
            while time.time() - start_time < timeout:
                time.sleep(1)
                resp = requests.get(f"{base_url}/api/v1/result/{task_id}", timeout=5)
                if resp.status_code != 200:
                    continue
                result_data = resp.json()
                status = result_data.get("status")
                if status == "success":
                    return ToolResult(True, content=result_data)
                elif status in ("failed", "cancelled"):
                    return ToolResult(
                        False,
                        error=f"Canvas execution {status}: {result_data.get('error_msg', 'Unknown error')}",
                    )

            return ToolResult(False, error=f"Canvas execution timeout after {timeout}s")
        except Exception as e:
            return ToolResult(False, error=f"Trigger canvas error: {str(e)}")
