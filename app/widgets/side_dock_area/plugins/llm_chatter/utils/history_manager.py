import os
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

from PyQt5.QtCore import QTimer

from app.utils.utils import serialize_for_json, deserialize_from_json
from app.widgets.side_dock_area.plugins.llm_chatter.utils.message_content import (
    consolidate_messages,
    content_to_text,
)


def merge_session_messages(messages: List[Dict]) -> List[Dict]:
    return consolidate_messages(messages or [])


class HistoryManager:
    def __init__(self, canvas_name: str):
        self.canvas_name = canvas_name
        self.history_dir = Path("canvas_files") / "workflows" / canvas_name
        self.history_file = self.history_dir / f"llm_history.json"
        self.daily_dir = self.history_dir / "daily"
        self.latest_session_file = self.history_dir / "session_latest.json"
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.daily_dir.mkdir(parents=True, exist_ok=True)
        self._history_sessions: List[Dict] = self._load_history()
        self._topic_summaries: Dict[str, str] = {}
        self._daily_limit = 5
        self._history_limit = 100
        self._save_timer: Optional[QTimer] = None
        self._save_delay_ms = 2000

    def _load_history(self) -> List[Dict]:
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = deserialize_from_json(json.load(f))
                    for item in data:
                        fallback_ts = (
                            item.get("last_time")
                            or item.get("saved_at")
                            or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        )
                        item["messages"] = self._ensure_message_timestamps(
                            merge_session_messages(item.get("messages", [])),
                            fallback_ts,
                        )
                        if "title" not in item:
                            item["title"] = item.get("topic_summary", "新对话")
                        if "last_time" not in item:
                            item["last_time"] = self._extract_last_message_time(
                                item.get("messages", [])
                            )
                        if "message_count" not in item:
                            item["message_count"] = len(item.get("messages", []))
                    return data
            except Exception:
                pass
        return []

    def save_session(self, messages: List[Dict], title: str = None):
        if not messages:
            return

        merged_messages = merge_session_messages(messages)
        session_record = self._build_session_record(merged_messages, title)

        self._history_sessions.insert(0, session_record)
        self._history_sessions = self._history_sessions[: self._history_limit]
        self._save_to_disk()
        self._save_latest_and_daily(session_record)

    def _build_session_record(
        self, merged_messages: List[Dict], title: str = None, session_id: str = None
    ) -> Dict:
        now = datetime.now()
        saved_at = now.strftime("%Y-%m-%d %H:%M:%S")
        session_id = session_id or uuid.uuid4().hex[:8]

        merged_messages = self._ensure_message_timestamps(merged_messages, saved_at)
        last_msg_time = self._extract_last_message_time(merged_messages)
        if not title:
            for msg in merged_messages:
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        content = content_to_text(content)
                    title = content[:30].strip() or "新对话"
                    break
            else:
                title = "新对话"

        return {
            "session_id": session_id,
            "saved_at": saved_at,
            "title": title,
            "last_time": last_msg_time,
            "messages": merged_messages,
            "message_count": self._count_conversation_pairs(merged_messages),
        }

    def _save_latest_and_daily(self, session_record: Dict):
        try:
            with open(self.latest_session_file, "w", encoding="utf-8") as f:
                json.dump(
                    serialize_for_json(session_record),
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception:
            pass

        day_dir = self.daily_dir / datetime.now().strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        file_name = (
            f"session_{datetime.now().strftime('%H%M%S')}_"
            f"{session_record.get('session_id', 'unknown')}.json"
        )
        try:
            with open(day_dir / file_name, "w", encoding="utf-8") as f:
                json.dump(
                    serialize_for_json(session_record),
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception:
            pass

        daily_files = sorted(day_dir.glob("session_*.json"), key=lambda p: p.stat().st_mtime)
        if len(daily_files) > self._daily_limit:
            for old_file in daily_files[: len(daily_files) - self._daily_limit]:
                try:
                    old_file.unlink()
                except Exception:
                    pass

    def get_current_title(self, index: int) -> str:
        if 0 <= index < len(self._history_sessions):
            return self._history_sessions[index]["title"]
        return ""

    def update_session_title(self, index: int, new_title: str):
        if 0 <= index < len(self._history_sessions):
            self._history_sessions[index]["title"] = new_title
            self._save_to_disk()

    def update_topic_summary(self, index: int, summary: str):
        self.update_session_title(index, summary)

    def get_topic_summary(self, index: int) -> str:
        return self.get_current_title(index)

    def should_generate_summary(self, index: int) -> bool:
        if 0 <= index < len(self._history_sessions):
            session = self._history_sessions[index]
            messages = session.get("messages", [])
            user_count = sum(1 for msg in messages if msg.get("role") == "user")
            return user_count >= 1
        return False

    def _count_conversation_pairs(self, messages: List[Dict]) -> int:
        """计算对话轮数（用户消息数量）"""
        count = 0
        for msg in messages:
            if msg.get("role") == "user":
                count += 1
        return count

    def _save_to_disk(self):
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(
                serialize_for_json(self._history_sessions),
                f,
                ensure_ascii=False,
                indent=2,
            )

    def load_latest_session(self) -> Optional[Dict]:
        if not self.latest_session_file.exists():
            return None
        try:
            with open(self.latest_session_file, "r", encoding="utf-8") as f:
                data = deserialize_from_json(json.load(f))
                if isinstance(data, dict) and data.get("messages"):
                    fallback_ts = (
                        data.get("last_time")
                        or data.get("saved_at")
                        or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )
                    data["messages"] = self._ensure_message_timestamps(
                        merge_session_messages(data.get("messages", [])),
                        fallback_ts,
                    )
                    return data
        except Exception:
            return None
        return None

    def get_history_list(self) -> List[Dict]:
        return self._history_sessions

    def delete_history(self, index: int):
        if 0 <= index < len(self._history_sessions):
            self._history_sessions.pop(index)
            self._save_to_disk()

    def get_session_by_index(self, index: int) -> Optional[List[Dict]]:
        if 0 <= index < len(self._history_sessions):
            session = self._history_sessions[index]
            fallback_ts = (
                session.get("last_time")
                or session.get("saved_at")
                or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            return self._ensure_message_timestamps(
                merge_session_messages(session["messages"]),
                fallback_ts,
            )
        return None

    def update_session(self, index: int, messages: List[Dict]):
        if 0 <= index < len(self._history_sessions):
            merged_messages = merge_session_messages(messages)
            existing = self._history_sessions[index]
            updated = self._build_session_record(
                merged_messages,
                title=existing.get("title"),
                session_id=existing.get("session_id"),
            )
            self._history_sessions[index] = updated
            self._save_latest_and_daily(updated)
            self._schedule_save()

    def _schedule_save(self):
        if self._save_timer is None:
            self._save_timer = QTimer.singleShot(self._save_delay_ms, self._do_save)

    def _do_save(self):
        self._save_to_disk()
        self._save_timer = None

    def _extract_last_message_time(self, messages: List[Dict]) -> str:
        for msg in reversed(messages or []):
            timestamp = msg.get("timestamp")
            if timestamp:
                return timestamp
        return "未知"

    def _ensure_message_timestamps(
        self, messages: List[Dict], fallback_ts: str
    ) -> List[Dict]:
        normalized: List[Dict] = []
        last_seen_ts = fallback_ts
        for msg in messages or []:
            if not isinstance(msg, dict):
                continue
            copied = dict(msg)
            timestamp = copied.get("timestamp") or last_seen_ts
            if timestamp:
                copied["timestamp"] = timestamp
                last_seen_ts = timestamp
            normalized.append(copied)
        return normalized
