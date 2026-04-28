# -*- coding: utf-8 -*-
"""
会话历史管理器 - 解决 issue #374

从 JSON 存储迁移到 SQLite 存储，提供：
- 原子性写入
- 并发支持
- 损坏隔离
- 增量更新
"""

import json
import uuid
import re
import os
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

from loguru import logger
from PyQt5.QtCore import QTimer

from app.utils.utils import serialize_for_json, deserialize_from_json
from app.llm_chatter.utils.message_content import (
    consolidate_messages,
    content_to_text,
)
from app.llm_chatter.utils.session_store import (
    SessionStore,
)


def merge_session_messages(messages: List[Dict]) -> List[Dict]:
    return consolidate_messages(messages or [])


def sanitize_filename(name: str) -> str:
    """移除文件名中不合法的字符"""
    return re.sub(r'[<>:"/\\|?*]', "_", name)


class HistoryManager:
    """
    会话历史管理器

    使用 SQLite 进行持久化存储，同时维护内存缓存以提高读取性能。
    """

    def __init__(self, canvas_name: str):
        self.canvas_name = canvas_name
        self.history_dir = Path("canvas_files") / "workflows" / canvas_name
        self.history_file = self.history_dir / "llm_history.json"
        self.archive_dir = Path("canvas_files") / "archived"
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        self._history_limit = 100
        self._save_timer: Optional[QTimer] = None
        self._save_delay_ms = 1000

        # SQLite 存储层
        self._session_store: Optional[SessionStore] = None
        self._use_sqlite = False

        # 内存缓存
        self._history_sessions: List[Dict] = []

        # 初始化存储
        self._init_storage()

    def _init_storage(self):
        """初始化存储层"""
        use_sqlite = os.environ.get("LLM_SESSION_SQLITE", "1") == "1"

        if use_sqlite:
            try:
                self._session_store = SessionStore(db_dir="canvas_files")
                if self._session_store.is_initialized:
                    self._use_sqlite = True
                    logger.info(f"[HistoryManager] SQLite 存储已启用: {self.canvas_name}")

                    # 从 SQLite 加载
                    self._history_sessions = self._session_store.load_sessions(
                        self.canvas_name, self._history_limit
                    )

                    # 检查是否需要迁移旧 JSON 数据
                    self._migrate_if_needed()

                    return
                else:
                    logger.warning("[HistoryManager] SQLite 初始化失败，回退 JSON")
            except Exception as e:
                logger.warning(f"[HistoryManager] SQLite 初始化异常: {e}")

        # 回退到 JSON 模式
        self._use_sqlite = False
        self._session_store = None
        self._history_sessions = self._load_history_from_json()
        logger.info(f"[HistoryManager] JSON 存储模式: {self.canvas_name}")

    def _migrate_if_needed(self):
        """迁移旧 JSON 数据到 SQLite（如果 SQLite 为空），迁移后删除 JSON"""
        if not self._session_store:
            return

        # 检查 SQLite 是否已有数据
        if self._session_store.get_session_count(self.canvas_name) > 0:
            return

        # 检查 JSON 文件是否存在
        if not self.history_file.exists():
            return

        # 迁移数据
        try:
            migrated = self._session_store.migrate_from_json(str(self.history_file))
            if migrated > 0:
                logger.info(f"[HistoryManager] 已迁移 {migrated} 条会话到 SQLite")

                # 删除 JSON 文件（迁移后不再使用）
                try:
                    self.history_file.unlink()
                    logger.info(f"[HistoryManager] 已删除 JSON 文件: {self.history_file}")
                except Exception as e:
                    logger.warning(f"[HistoryManager] 删除 JSON 文件失败: {e}")

                # 重新加载
                self._history_sessions = self._session_store.load_sessions(
                    self.canvas_name, self._history_limit
                )
        except Exception as e:
            logger.error(f"[HistoryManager] 迁移失败: {e}")

    def _load_history_from_json(self) -> List[Dict]:
        """从 JSON 文件加载（回退模式）"""
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = deserialize_from_json(json.load(f))
                    if not isinstance(data, list):
                        return []
                    return self._normalize_sessions(data)
            except Exception as e:
                logger.error(f"[HistoryManager] JSON 加载失败: {e}")
        return []

    def _normalize_sessions(self, data: List) -> List[Dict]:
        """规范化会话数据"""
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

    def save_session(
        self,
        messages: List[Dict],
        title: str = None,
        session_id: str = None,
        compaction_state: Dict = None,
        compaction_cache: Dict = None,
        system_prompt: str = None,
    ):
        """保存会话"""
        if not messages:
            return

        merged_messages = merge_session_messages(messages)
        session_record = self._build_session_record(
            merged_messages,
            title,
            session_id,
            compaction_state=compaction_state,
            compaction_cache=compaction_cache,
            system_prompt=system_prompt,
        )
        new_session_id = session_record["session_id"]

        # 更新内存缓存
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

        # 持久化
        self._persist_session(session_record)

    def _persist_session(self, session_record: Dict):
        """持久化单个会话（延迟保存）"""
        # 添加 canvas_id
        session_record["canvas_id"] = self.canvas_name

        if self._use_sqlite and self._session_store:
            # SQLite 模式：延迟保存，只保存当前会话
            self._schedule_save(session_record.get("session_id"))
        else:
            # JSON 模式
            self._save_to_disk_json()

    def _build_session_record(
        self,
        merged_messages: List[Dict],
        title: str = None,
        session_id: str = None,
        compaction_state: Dict = None,
        compaction_cache: Dict = None,
        system_prompt: str = None,
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
            "system_prompt": system_prompt or "",
        }

    def get_current_title(self, index: int) -> str:
        if 0 <= index < len(self._history_sessions):
            return self._history_sessions[index].get("title", "")
        return ""

    def update_session_title(self, index: int, new_title: str):
        if 0 <= index < len(self._history_sessions):
            self._history_sessions[index]["title"] = new_title
            session = self._history_sessions[index]
            session["canvas_id"] = self.canvas_name
            self._persist_session(session)

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

    def _save_to_disk_json(self):
        """保存到 JSON 文件（回退模式）"""
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

    def load_most_recently_updated_session(self) -> Optional[Dict]:
        """加载最近更新的会话"""
        if not self._history_sessions:
            return None
        most_recent = None
        most_recent_time = None
        for session in self._history_sessions:
            messages = session.get("messages", [])
            if not messages:
                continue
            last_updated = session.get("last_updated") or session.get("last_time") or ""
            if not most_recent_time or last_updated > most_recent_time:
                most_recent_time = last_updated
                most_recent = session
        return most_recent

    def get_history_list(self) -> List[Dict]:
        return self._history_sessions

    def archive_history(self, index: int) -> bool:
        """归档历史记录"""
        if 0 <= index < len(self._history_sessions):
            session = self._history_sessions[index]
            title = session.get("title", "未命名")
            last_time = session.get("last_time", datetime.now().strftime("%Y-%m-%d"))
            session_id = session.get("session_id", "unknown")

            safe_title = sanitize_filename(title[:50])
            date_str = (
                last_time[:10] if last_time else datetime.now().strftime("%Y-%m-%d")
            )
            filename = f"{date_str}_{safe_title}_{session_id}.json"

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

            # 从内存缓存移除
            self._history_sessions.pop(index)

            # 从 SQLite 删除
            if self._use_sqlite and self._session_store:
                self._session_store.delete_session(session_id)

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

    def find_index_by_session_id(self, session_id: str) -> Optional[int]:
        """根据 session_id 查找索引"""
        if not session_id:
            return None
        for i, session in enumerate(self._history_sessions):
            if session.get("session_id") == session_id:
                return i
        return None

    def get_session_by_session_id(self, session_id: str) -> Optional[Dict]:
        """根据 session_id 获取会话"""
        if not session_id:
            return None
        for session in self._history_sessions:
            if session.get("session_id") == session_id:
                return session
        return None

    def update_session(
        self,
        index: int,
        messages: List[Dict],
        compaction_state: Dict = None,
        compaction_cache: Dict = None,
        system_prompt: str = None,
    ):
        """更新会话"""
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
                system_prompt=(
                    system_prompt
                    if system_prompt is not None
                    else existing.get("system_prompt", "")
                ),
            )
            self._history_sessions[index] = updated
            self._schedule_save(existing.get("session_id"))

    def _schedule_save(self, session_id: str = None):
        """延迟保存会话，指定 session_id 时只保存该会话"""
        self._pending_save_session_id = session_id
        if self._save_timer is None:
            self._save_timer = QTimer.singleShot(self._save_delay_ms, self._do_save)

    def _do_save(self):
        """延迟保存会话"""
        if self._use_sqlite and self._session_store:
            # SQLite 模式下保存指定会话或所有会话
            pending_id = getattr(self, '_pending_save_session_id', None)
            logger.debug(f"[HistoryManager] 保存会话: pending_id={pending_id}, total={len(self._history_sessions)}")
            if pending_id:
                # 只保存指定会话
                for session in self._history_sessions:
                    if session.get("session_id") == pending_id:
                        session["canvas_id"] = self.canvas_name
                        self._session_store.save_session(session)
                        break
            else:
                # 保存所有会话
                for session in self._history_sessions:
                    session["canvas_id"] = self.canvas_name
                    self._session_store.save_session(session)
        else:
            self._save_to_disk_json()
        self._save_timer = None
        self._pending_save_session_id = None

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
                    return content[:max_len].strip() + (
                        "..." if len(content) > max_len else ""
                    )
        return ""

    def get_total_storage_size(self) -> int:
        """获取总存储大小"""
        if self._use_sqlite and self._session_store:
            # 估算 SQLite 数据库大小
            db_path = os.path.join("canvas_files", "sessions.db")
            if os.path.exists(db_path):
                return os.path.getsize(db_path)

        # JSON 模式
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
            "storage_mode": "sqlite" if self._use_sqlite else "json",
        }