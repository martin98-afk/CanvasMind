import json
import uuid
import re
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


def sanitize_filename(name: str) -> str:
    """移除文件名中不合法的字符"""
    return re.sub(r'[<>:"/\\|?*]', '_', name)


class HistoryManager:
    def __init__(self, canvas_name: str):
        self.canvas_name = canvas_name
        self.history_dir = Path("canvas_files") / "workflows" / canvas_name
        self.history_file = self.history_dir / f"llm_history.json"
        self.archive_dir = self.history_dir / "archived"
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self._history_sessions: List[Dict] = self._load_history()
        self._history_limit = 100
        self._save_timer: Optional[QTimer] = None
        self._save_delay_ms = 1000

    def _load_history(self) -> List[Dict]:
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = deserialize_from_json(json.load(f))
                    if not isinstance(data, list):
                        return []
                    normalized = []
                    seen_ids = set()
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        sid = item.get("session_id")
                        if sid and sid in seen_ids:
                            continue
                        if sid:
                            seen_ids.add(sid)
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
                        if "session_id" not in item:
                            item["session_id"] = uuid.uuid4().hex[:8]
                        item["compaction_state"] = dict(item.get("compaction_state") or {})
                        item["compaction_cache"] = dict(item.get("compaction_cache") or {})
                        normalized.append(item)
                    return normalized
            except Exception:
                pass
        return []

    def save_session(
        self,
        messages: List[Dict],
        title: str = None,
        session_id: str = None,
        compaction_state: Dict = None,
        compaction_cache: Dict = None,
    ):
        if not messages:
            return

        merged_messages = merge_session_messages(messages)
        session_record = self._build_session_record(
            merged_messages,
            title,
            session_id,
            compaction_state=compaction_state,
            compaction_cache=compaction_cache,
        )
        new_session_id = session_record["session_id"]

        existing_index = None
        for i, s in enumerate(self._history_sessions):
            if s.get("session_id") == new_session_id:
                existing_index = i
                break

        if existing_index is not None:
            self._history_sessions[existing_index] = session_record
        else:
            self._history_sessions.insert(0, session_record)

        self._history_sessions = self._history_sessions[: self._history_limit]
        self._save_to_disk()

    def _build_session_record(
        self,
        merged_messages: List[Dict],
        title: str = None,
        session_id: str = None,
        compaction_state: Dict = None,
        compaction_cache: Dict = None,
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
            "compaction_state": dict(compaction_state or {}),
            "compaction_cache": dict(compaction_cache or {}),
        }

    def get_current_title(self, index: int) -> str:
        if 0 <= index < len(self._history_sessions):
            return self._history_sessions[index].get("title", "")
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
        if not self._history_sessions:
            return None
        latest = self._history_sessions[0]
        if not latest.get("messages"):
            return None
        return latest

    def get_history_list(self) -> List[Dict]:
        return self._history_sessions

    def archive_history(self, index: int) -> bool:
        """将历史记录归档到单独的文件中"""
        if 0 <= index < len(self._history_sessions):
            session = self._history_sessions[index]
            title = session.get("title", "未命名")
            last_time = session.get("last_time", datetime.now().strftime("%Y-%m-%d"))
            session_id = session.get("session_id", "unknown")

            safe_title = sanitize_filename(title[:50])
            date_str = last_time[:10] if last_time else datetime.now().strftime("%Y-%m-%d")
            filename = f"{safe_title}_{date_str}_{session_id}.json"

            archive_file = self.archive_dir / filename
            try:
                with open(archive_file, "w", encoding="utf-8") as f:
                    json.dump(
                        serialize_for_json(session),
                        f,
                        ensure_ascii=False,
                        indent=2,
                    )
            except Exception:
                return False

            self._history_sessions.pop(index)
            self._save_to_disk()
            return True
        return False

    def get_session_by_index(self, index: int) -> Optional[List[Dict]]:
        if 0 <= index < len(self._history_sessions):
            session = self._history_sessions[index]
            fallback_ts = (
                session.get("last_time")
                or session.get("saved_at")
                or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            return self._ensure_message_timestamps(
                merge_session_messages(session.get("messages", [])),
                fallback_ts,
            )
        return None

    def get_session_id_by_index(self, index: int) -> Optional[str]:
        if 0 <= index < len(self._history_sessions):
            return self._history_sessions[index].get("session_id")
        return None

    def update_session(
        self,
        index: int,
        messages: List[Dict],
        compaction_state: Dict = None,
        compaction_cache: Dict = None,
    ):
        if 0 <= index < len(self._history_sessions):
            merged_messages = merge_session_messages(messages)
            existing = self._history_sessions[index]
            updated = self._build_session_record(
                merged_messages,
                title=existing.get("title"),
                session_id=existing.get("session_id"),
                compaction_state=(
                    compaction_state
                    if compaction_state is not None
                    else existing.get("compaction_state", {})
                ),
                compaction_cache=(
                    compaction_cache
                    if compaction_cache is not None
                    else existing.get("compaction_cache", {})
                ),
            )
            self._history_sessions[index] = updated
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

    def get_session_preview(self, index: int, max_len: int = 50) -> str:
        if 0 <= index < len(self._history_sessions):
            messages = self._history_sessions[index].get("messages", [])
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        content = content_to_text(content)
                    return content[:max_len].strip() + ("..." if len(content) > max_len else "")
        return ""

    def get_total_storage_size(self) -> int:
        total_size = 0
        if self.history_file.exists():
            try:
                total_size += self.history_file.stat().st_size
            except Exception:
                pass
        return total_size

    def get_memory_stats(self) -> Dict:
        total_messages = sum(s.get("message_count", 0) for s in self._history_sessions)
        total_chars = 0
        for session in self._history_sessions:
            for msg in session.get("messages", []):
                content = msg.get("content", "")
                if isinstance(content, list):
                    content = content_to_text(content)
                total_chars += len(content)
        return {
            "session_count": len(self._history_sessions),
            "total_messages": total_messages,
            "total_chars": total_chars,
            "storage_size": self.get_total_storage_size(),
        }
