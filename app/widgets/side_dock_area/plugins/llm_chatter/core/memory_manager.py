# -*- coding: utf-8 -*-
"""
长期记忆管理模块 - 处理用户偏好和会话记忆
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from loguru import logger

from openai import OpenAI

from app.widgets.side_dock_area.plugins.llm_chatter.utils.retry_helper import (
    create_api_call_with_retry,
)


MEMORY_CATEGORIES = {
    "agent_identity": "【智能体自身身份记忆】",
    "user_identity": "【用户身份记忆】",
    "task_preference": "【用户任务偏好】",
    "task_taboos": "【任务忌讳】",
}

MEMORY_CATEGORY_SUMMARIES = {
    "agent_identity": "关于智能体自身角色、能力边界的认知",
    "user_identity": "关于用户身份、背景、角色的认知",
    "task_preference": "关于用户处理任务的习惯、方式偏好",
    "task_taboos": "用户明确指出不能做的事、禁忌或雷区",
}


class MemoryManagerCore:
    """长期记忆管理器核心类"""

    def __init__(self, canvas_name: str = "default"):
        self._canvas_name = canvas_name
        self._memory_file: Optional[Path] = None
        self._ensure_memory_file()

    def _ensure_memory_file(self):
        """确保记忆文件存在"""
        try:
            canvas_name = self._canvas_name or "default"
            memory_dir = Path("canvas_files") / "workflows" / canvas_name
            memory_dir.mkdir(parents=True, exist_ok=True)
            self._memory_file = memory_dir / "soul.md"
        except Exception as e:
            logger.error(f"[MemoryManager] Failed to create memory file: {e}")

    @property
    def memory_file(self) -> Optional[Path]:
        return self._memory_file

    def load_memory(self) -> Dict:
        """加载记忆数据"""
        if self._memory_file and self._memory_file.exists():
            try:
                with open(self._memory_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "user_memories" not in data:
                        data["user_memories"] = []
                    normalized_memories = []
                    for memory in data.get("user_memories", []):
                        normalized = self._normalize_memory_entry(memory)
                        if normalized:
                            normalized_memories.append(normalized)
                    data["user_memories"] = normalized_memories
                    return data
            except Exception as e:
                logger.error(f"[MemoryManager] Failed to load memory: {e}")

        return self._get_default_memory()

    def _get_default_memory(self) -> Dict:
        """获取默认记忆结构"""
        return {
            "version": "2.0",
            "user_profile": {
                "name": "",
                "preferences": {},
                "communication_style": "",
                "expertise_level": "",
            },
            "topics": [],
            "conversation_patterns": [],
            "key_insights": [],
            "user_memories": [],
            "total_conversations": 0,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_updated": "",
        }

    def _normalize_memory_entry(self, memory: Any) -> Optional[Dict]:
        if isinstance(memory, str):
            content = memory.strip()
            if not content:
                return None
            return {
                "content": content,
                "enabled": True,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "confidence": 0.7,
                "source": "legacy",
                "last_used_at": "",
                "category": "task_preference",
            }

        if not isinstance(memory, dict):
            return None

        content = str(memory.get("content", "")).strip()
        if not content:
            return None

        normalized = dict(memory)
        normalized["content"] = content
        normalized.setdefault("enabled", True)
        normalized.setdefault("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        normalized.setdefault("confidence", 0.8)
        normalized.setdefault("source", "manual")
        normalized.setdefault("last_used_at", "")
        normalized.setdefault("conflict_group", "")
        normalized.setdefault("category", "task_preference")
        if normalized["category"] not in MEMORY_CATEGORIES:
            normalized["category"] = "task_preference"
        return normalized

    def _normalize_content_key(self, content: str) -> str:
        return " ".join(str(content or "").strip().lower().split())

    def _memory_sort_key(self, memory: Dict) -> tuple:
        confidence = float(memory.get("confidence", 0.5) or 0.5)
        recency = memory.get("last_used_at") or memory.get("timestamp", "")
        enabled = 1 if memory.get("enabled", True) else 0
        return (enabled, confidence, recency)

    def _resolve_conflicts(
        self,
        memories: List[Dict],
        new_entry: Dict,
    ) -> List[Dict]:
        conflict_group = str(new_entry.get("conflict_group", "") or "").strip()
        if not conflict_group:
            return memories

        updated = []
        for memory in memories:
            if memory.get(
                "conflict_group", ""
            ) == conflict_group and self._normalize_content_key(
                memory.get("content", "")
            ) != self._normalize_content_key(new_entry.get("content", "")):
                item = dict(memory)
                item["enabled"] = False
                updated.append(item)
            else:
                updated.append(memory)
        return updated

    def save_memory(self, memory_data: Dict) -> bool:
        """保存记忆数据"""
        try:
            if not self._memory_file:
                return False

            memory_data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            with open(self._memory_file, "w", encoding="utf-8") as f:
                json.dump(memory_data, f, ensure_ascii=False, indent=2)

            logger.info(f"[MemoryManager] Memory saved successfully")
            return True
        except Exception as e:
            logger.error(f"[MemoryManager] Failed to save memory: {e}")
            return False

    def get_topics(self) -> List[Dict]:
        """获取主题列表"""
        memory_data = self.load_memory()
        return memory_data.get("topics", [])

    def add_topic(self, topic: str, reason: str = "") -> bool:
        """添加新主题"""
        try:
            memory_data = self.load_memory()
            existing_topics = memory_data.get("topics", [])

            topic_entry = {
                "topic": topic,
                "reason": reason,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            topic_exists = any(t.get("topic") == topic for t in existing_topics)
            if not topic_exists:
                existing_topics.append(topic_entry)
                memory_data["topics"] = existing_topics[-20:]

            memory_data["total_conversations"] = (
                memory_data.get("total_conversations", 0) + 1
            )

            return self.save_memory(memory_data)
        except Exception as e:
            logger.error(f"[MemoryManager] Failed to add topic: {e}")
            return False

    def get_user_memories(self, memory_data: Optional[Dict] = None) -> List[Dict]:
        """获取用户记忆列表"""
        if memory_data is None:
            memory_data = self.load_memory()
        memories = memory_data.get("user_memories", [])
        memories = [m for m in memories if self._normalize_memory_entry(m)]
        memories.sort(key=self._memory_sort_key, reverse=True)
        return memories

    def add_user_memory(
        self,
        content: str,
        *,
        source: str = "assistant",
        confidence: float = 0.8,
        conflict_group: str = "",
        category: str = "task_preference",
    ) -> bool:
        """添加用户偏好记忆"""
        if not content:
            return False

        if category not in MEMORY_CATEGORIES:
            category = "task_preference"

        try:
            memory_data = self.load_memory()
            user_memories = self.get_user_memories()
            normalized_key = self._normalize_content_key(content)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            for index, memory in enumerate(user_memories):
                if (
                    self._normalize_content_key(memory.get("content", ""))
                    != normalized_key
                ):
                    continue
                updated = dict(memory)
                updated["enabled"] = True
                updated["source"] = source or updated.get("source", "assistant")
                updated["confidence"] = max(
                    float(updated.get("confidence", 0.0) or 0.0),
                    float(confidence or 0.0),
                )
                updated["last_used_at"] = now
                if conflict_group:
                    updated["conflict_group"] = conflict_group
                updated["category"] = category
                user_memories[index] = updated
                memory_data["user_memories"] = user_memories[-50:]
                return self.save_memory(memory_data)

            new_entry = {
                "content": content.strip(),
                "enabled": True,
                "timestamp": now,
                "confidence": float(confidence or 0.8),
                "source": source or "assistant",
                "last_used_at": now,
                "conflict_group": conflict_group or "",
                "category": category,
            }
            user_memories = self._resolve_conflicts(user_memories, new_entry)
            user_memories.append(new_entry)
            user_memories.sort(key=self._memory_sort_key, reverse=True)
            memory_data["user_memories"] = user_memories[:50]
            return self.save_memory(memory_data)
        except Exception as e:
            logger.error(f"[MemoryManager] Failed to add user memory: {e}")
            return False

    def update_user_memories(self, memories: List[Dict]) -> bool:
        """更新用户记忆列表"""
        try:
            memory_data = self.load_memory()
            normalized_memories = []
            for memory in memories:
                normalized = self._normalize_memory_entry(memory)
                if normalized:
                    normalized_memories.append(normalized)
            memory_data["user_memories"] = normalized_memories
            return self.save_memory(memory_data)
        except Exception as e:
            logger.error(f"[MemoryManager] Failed to update user memories: {e}")
            return False

    def search_memories(
        self,
        query: str = "",
        *,
        include_disabled: bool = False,
        limit: int = 10,
        memory_data: Optional[Dict] = None,
    ) -> List[Dict]:
        query_terms = [
            part for part in self._normalize_content_key(query).split() if part
        ]
        memories = self.get_user_memories(memory_data)
        results = []
        for memory in memories:
            if not include_disabled and not memory.get("enabled", True):
                continue
            content_key = self._normalize_content_key(memory.get("content", ""))
            if query_terms and not all(term in content_key for term in query_terms):
                continue
            results.append(memory)
        results.sort(key=self._memory_sort_key, reverse=True)
        return results[:limit]

    def format_memories_for_prompt(
        self,
        memories: List[Dict],
        *,
        title: str = "长期记忆摘要",
        include_disabled: bool = False,
    ) -> str:
        lines = [f"## {title}", ""]

        categorized: Dict[str, List[tuple]] = {cat: [] for cat in MEMORY_CATEGORIES}
        disabled: List[tuple] = []

        for memory in memories:
            normalized = self._normalize_memory_entry(memory)
            if not normalized:
                continue
            category = normalized.get("category", "task_preference")
            if category not in MEMORY_CATEGORIES:
                category = "task_preference"
            payload = (
                float(normalized.get("confidence", 0.5) or 0.5),
                normalized.get("last_used_at") or normalized.get("timestamp", ""),
                normalized.get("source", "manual"),
                normalized.get("content", ""),
            )
            if normalized.get("enabled", True):
                categorized[category].append(payload)
            elif include_disabled:
                disabled.append(payload)

        for cat_key in MEMORY_CATEGORIES:
            categorized[cat_key].sort(reverse=True)

        has_any_memory = False
        for cat_key, cat_title in MEMORY_CATEGORIES.items():
            items = categorized.get(cat_key, [])
            if not items:
                continue
            has_any_memory = True
            lines.append(f"### {cat_title}")
            lines.append(f"*{MEMORY_CATEGORY_SUMMARIES.get(cat_key, '')}*")
            for idx, (confidence, _, source, content) in enumerate(items, 1):
                lines.append(f"{idx}. ({source}, conf={confidence:.2f}) {content}")
            lines.append("")

        if include_disabled and disabled:
            lines.append("### 【冲突/禁用记忆，仅供参考】")
            for confidence, _, source, content in disabled[:5]:
                lines.append(f"- ({source}, conf={confidence:.2f}) {content}")
            lines.append("")

        if not has_any_memory:
            lines.append("暂无长期记忆，系统将逐步积累用户偏好与会话要点。")
            lines.append("")

        lines.append("请优先遵循高置信度且最近使用的记忆。")
        return "\n".join(lines)

    def touch_memories(
        self, contents: List[str], memory_data: Optional[Dict] = None
    ) -> bool:
        normalized_keys = {
            self._normalize_content_key(content)
            for content in contents or []
            if self._normalize_content_key(content)
        }
        if not normalized_keys:
            return False

        try:
            if memory_data is None:
                memory_data = self.load_memory()
            changed = False
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            updated_memories = []
            for memory in memory_data.get("user_memories", []):
                normalized = self._normalize_memory_entry(memory)
                if not normalized:
                    continue
                if (
                    self._normalize_content_key(normalized.get("content", ""))
                    in normalized_keys
                ):
                    normalized["last_used_at"] = now
                    changed = True
                updated_memories.append(normalized)
            if not changed:
                return False
            memory_data["user_memories"] = updated_memories
            return self.save_memory(memory_data)
        except Exception as e:
            logger.error(f"[MemoryManager] Failed to touch memories: {e}")
            return False

    def consolidate_from_messages(
        self,
        messages: List[Dict],
        llm_config: Dict[str, Any],
        *,
        max_items: int = 3,
    ) -> List[Dict]:
        user_messages = [m for m in messages if m.get("role") == "user"]
        if not user_messages:
            return []

        transcript = []
        for msg in messages[-12:]:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                content = "\n".join(text_parts)
            transcript.append(f"[{role}] {str(content)[:1000]}")

        existing = self.get_user_memories()[:12]
        existing_text = "\n".join(
            f"- [{item.get('category', 'task_preference')}] {item.get('content', '')}"
            for item in existing if item.get("content")
        )

        category_list = "\n".join(
            f"- {k}: {v.replace('【', '').replace('】', '')}" for k, v in MEMORY_CATEGORIES.items()
        )

        prompt = (
            "请从下面的会话中提炼最多 3 条适合写入长期记忆的内容。\n"
            "只保留稳定的用户偏好、项目约束、明确纠正、长期决策。\n"
            "不要提炼一次性任务细节，不要重复已有记忆。\n\n"
            "**记忆分类说明**：\n"
            f"{category_list}\n\n"
            "输出 JSON 数组，每项格式为 "
            '{"content":"...","category":"分类key","confidence":0.0-1.0,"source":"session","conflict_group":"可选"}。\n\n'
            f"【已有记忆】\n{existing_text or '无'}\n\n"
            f"【近期会话】\n{chr(10).join(transcript)}"
        )

        api_key = llm_config.get("API_KEY", "").strip()
        base_url = llm_config.get("API_URL") or None
        auth_type = str(llm_config.get("认证方式", "bearer") or "bearer").lower()
        model = str(llm_config.get("模型名称", "gpt-4o"))

        client = OpenAI(
            api_key=api_key if api_key and auth_type != "none" else "dummy",
            base_url=base_url,
            timeout=60.0,
        )

        def create_task():
            return client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1200,
            )

        try:
            resp = create_api_call_with_retry(client, create_task)
            raw = (resp.choices[0].message.content or "").strip()
            start = raw.find("[")
            end = raw.rfind("]")
            if start == -1 or end == -1 or end <= start:
                return []
            parsed = json.loads(raw[start : end + 1])
        except Exception as e:
            logger.warning(f"[MemoryManager] Consolidation failed: {e}")
            return []

        results = []
        for item in parsed[:max_items]:
            normalized = self._normalize_memory_entry(item)
            if not normalized:
                continue
            normalized["source"] = item.get("source", "session")
            normalized["confidence"] = float(item.get("confidence", 0.8) or 0.8)
            normalized["conflict_group"] = str(item.get("conflict_group", "") or "")
            category = str(item.get("category", "task_preference") or "task_preference")
            if category not in MEMORY_CATEGORIES:
                category = "task_preference"
            normalized["category"] = category
            results.append(normalized)
        return results

    def clear_memory(self) -> bool:
        """清空记忆"""
        try:
            if self._memory_file and self._memory_file.exists():
                self._memory_file.unlink()
            logger.info("[MemoryManager] Memory cleared")
            return True
        except Exception as e:
            logger.error(f"[MemoryManager] Failed to clear memory: {e}")
            return False

    def get_context_string(self, query: str = "", limit: int = 8) -> str:
        """获取格式化后的记忆上下文字符串"""
        memory_data = self.load_memory()
        topics = memory_data.get("topics", [])
        if query:
            selected_memories = self.search_memories(
                query, include_disabled=False, limit=limit, memory_data=memory_data
            )
            if not selected_memories:
                selected_memories = self.get_context_memories(
                    limit=limit, memory_data=memory_data
                )
        else:
            selected_memories = self.get_context_memories(
                limit=limit, memory_data=memory_data
            )
        if selected_memories:
            self.touch_memories(
                [item.get("content", "") for item in selected_memories],
                memory_data=memory_data,
            )
        lines = [self.format_memories_for_prompt(selected_memories)]
        if topics:
            recent_topics = topics[-5:]
            topic_names = [
                t.get("topic", "") if isinstance(t, dict) else str(t)
                for t in recent_topics
            ]
            topic_names = [t for t in topic_names if t]
            if topic_names:
                lines.append(f"【最近讨论主题】{', '.join(topic_names)}")

        return "\n".join(lines)

    def get_context_memories(
        self, limit: int = 8, memory_data: Optional[Dict] = None
    ) -> List[Dict]:
        return self.search_memories(
            "", include_disabled=False, limit=limit, memory_data=memory_data
        )

    def set_canvas_name(self, canvas_name: str):
        """设置画布名称（切换工作区时调用）"""
        self._canvas_name = canvas_name
        self._ensure_memory_file()
