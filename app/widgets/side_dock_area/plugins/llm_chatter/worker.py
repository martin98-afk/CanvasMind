# -*- coding: utf-8 -*-
import os
from typing import Dict, Any, List

from PyQt5.QtCore import QThread, pyqtSignal


# -------------------- AI Worker --------------------
class OpenAIChatWorker(QThread):
    content_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    finished_with_content = pyqtSignal(str)  # 可选：返回完整回复

    def __init__(self, messages: List[Dict], llm_config: Dict):
        super().__init__()
        self.messages = messages
        self.llm_config = llm_config
        self.full_response = ""
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def _check_cancel(self) -> bool:
        return self._is_cancelled

    def run(self):
        try:
            from openai import OpenAI

            api_key = self.llm_config.get("API_KEY", "")
            base_url = self.llm_config.get("API_URL") or None
            model = self.llm_config.get("模型名称", "gpt-4o")
            temperature = self.llm_config.get("温度", 0.7)
            max_tokens = self.llm_config.get("最大Token", 2048)
            enable_thinking = self.llm_config.get("是否思考", True)

            client = OpenAI(api_key=api_key, base_url=base_url)

            stream = client.chat.completions.create(
                model=model,
                messages=self.messages,  # ← 关键：传入完整上下文
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )

            self.full_response = ""
            for chunk in stream:
                if self._is_cancelled:
                    return
                if chunk.choices and chunk.choices[0].delta.content is not None:
                    content = chunk.choices[0].delta.content
                    self.full_response += content
                    self.content_received.emit(content)

            self.finished_with_content.emit(self.full_response)

        except Exception as e:
            self.error_occurred.emit(f"[错误] {str(e)}")