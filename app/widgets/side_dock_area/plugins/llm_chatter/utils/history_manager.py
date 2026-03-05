import os
import json
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

from app.utils.utils import serialize_for_json, deserialize_from_json


def merge_session_messages(messages: List[Dict]) -> List[Dict]:
    """
    合并一轮对话：
    - user 消息保留
    - 同一 round_id 的 assistant + tool 消息合并成一条
    - 删除 tool_calls 和 tool_results（不需要存给 API）
    - 跳过 tool 消息
    """
    if not messages:
        return []

    merged = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        role = msg.get("role")

        if role == "system":
            merged.append(msg.copy())
            i += 1
            continue

        if role == "user":
            merged.append(msg.copy())
            i += 1
            continue

        if role == "assistant":
            final_content = msg.get("content", "")
            current_round_id = msg.get("round_id")

            j = i + 1
            while j < len(messages):
                next_msg = messages[j]
                next_role = next_msg.get("role")
                next_round_id = next_msg.get("round_id")

                if next_role == "assistant" and next_round_id == current_round_id:
                    if next_msg.get("content"):
                        final_content = next_msg.get("content", "")
                    j += 1
                elif next_role == "tool" and next_round_id == current_round_id:
                    j += 1
                elif next_role == "assistant" and next_round_id is None:
                    final_content = next_msg.get("content", "")
                    j += 1
                else:
                    break

            merged_msg = {
                "role": "assistant",
                "content": final_content,
                "timestamp": msg.get("timestamp"),
            }

            merged.append(merged_msg)
            i = j
            continue

        if role == "tool":
            i += 1
            continue

        merged.append(msg.copy())
        i += 1

    return merged


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
                            item["title"] = item.get("topic_summary", "新对话")
                        if "last_time" not in item:
                            item["last_time"] = item.get("messages", [{}])[-1].get(
                                "timestamp", "未知"
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

        last_msg_time = merged_messages[-1].get(
            "timestamp", datetime.now().strftime("%Y-%m-%d %H:%M")
        )
        if not title:
            for msg in merged_messages:
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        content = "\n".join(
                            [
                                item.get("text", "")
                                for item in content
                                if item.get("type") == "text"
                            ]
                        )
                    title = content[:30].strip() or "新对话"
                    break
            else:
                title = "新对话"

        self._history_sessions.insert(
            0,
            {
                "title": title,
                "last_time": last_msg_time,
                "messages": merged_messages,
                "message_count": self._count_conversation_pairs(merged_messages),
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
            merged_messages = merge_session_messages(messages)
            last_msg_time = merged_messages[-1].get(
                "timestamp", datetime.now().strftime("%Y-%m-%d %H:%M")
            )
            self._history_sessions[index]["messages"] = merged_messages
            self._history_sessions[index]["last_time"] = last_msg_time
            self._history_sessions[index]["message_count"] = (
                self._count_conversation_pairs(merged_messages)
            )
            self._save_to_disk()
