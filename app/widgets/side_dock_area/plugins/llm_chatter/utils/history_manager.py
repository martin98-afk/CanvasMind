import os
import json
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

from app.utils.utils import serialize_for_json, deserialize_from_json


class HistoryManager:
    def __init__(self, canvas_name: str):
        self.canvas_name = canvas_name
        self.history_dir = Path("canvas_files") / "workflows" / canvas_name
        self.history_file = self.history_dir / f"llm_history.json"
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self._history_sessions: List[Dict] = self._load_history()
        self._topic_summaries: Dict[str, str] = {}

    def _load_history(self) -> List[Dict]:
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = deserialize_from_json(json.load(f))
                    for item in data:
                        if "title" not in item:
                            item["title"] = "未命名对话"
                        if "last_time" not in item:
                            item["last_time"] = item.get("messages", [{}])[-1].get(
                                "timestamp", "未知"
                            )
                        if "topic_summary" not in item:
                            item["topic_summary"] = ""
                        if "message_count" not in item:
                            item["message_count"] = len(item.get("messages", []))
                    return data
            except Exception:
                pass
        return []

    def save_session(self, messages: List[Dict], title: str = None):
        if not messages:
            return
        last_msg_time = messages[-1].get(
            "timestamp", datetime.now().strftime("%Y-%m-%d %H:%M")
        )
        if not title:
            for msg in messages:
                if msg.get("role") == "user":
                    title = msg.get("content", "")[:30].strip() or "新对话"
                    break
            else:
                title = "新对话"

        self._history_sessions.insert(
            0,
            {
                "title": title,
                "last_time": last_msg_time,
                "messages": messages,
                "topic_summary": "",
                "message_count": len(messages),
            },
        )
        self._save_to_disk()

    def get_current_title(self, index: int) -> str:
        if 0 <= index < len(self._history_sessions):
            return self._history_sessions[index]["title"]
        return ""

    def update_session_title(self, index: int, new_title: str):
        if 0 <= index < len(self._history_sessions):
            self._history_sessions[index]["title"] = new_title
            self._save_to_disk()

    def update_topic_summary(self, index: int, summary: str):
        if 0 <= index < len(self._history_sessions):
            self._history_sessions[index]["topic_summary"] = summary
            self._history_sessions[index]["message_count"] = len(
                self._history_sessions[index].get("messages", [])
            )
            self._save_to_disk()

    def get_topic_summary(self, index: int) -> str:
        if 0 <= index < len(self._history_sessions):
            return self._history_sessions[index].get("topic_summary", "")
        return ""

    def should_generate_summary(self, index: int) -> bool:
        if 0 <= index < len(self._history_sessions):
            session = self._history_sessions[index]
            msg_count = session.get("message_count", len(session.get("messages", [])))
            current_summary = session.get("topic_summary", "")
            return msg_count >= 4 and not current_summary
        return False

    def _save_to_disk(self):
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(
                serialize_for_json(self._history_sessions),
                f,
                ensure_ascii=False,
                indent=2,
            )

    def get_history_list(self) -> List[Dict]:
        return self._history_sessions

    def delete_history(self, index: int):
        if 0 <= index < len(self._history_sessions):
            self._history_sessions.pop(index)
            self._save_to_disk()

    def get_session_by_index(self, index: int) -> Optional[List[Dict]]:
        if 0 <= index < len(self._history_sessions):
            return self._history_sessions[index]["messages"]
        return None

    def update_session(self, index: int, messages: List[Dict]):
        if 0 <= index < len(self._history_sessions):
            last_msg_time = messages[-1].get(
                "timestamp", datetime.now().strftime("%Y-%m-%d %H:%M")
            )
            self._history_sessions[index]["messages"] = messages
            self._history_sessions[index]["last_time"] = last_msg_time
            self._history_sessions[index]["message_count"] = len(messages)
            self._save_to_disk()
