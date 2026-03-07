# -*- coding: utf-8 -*-
"""
长期记忆管理模块 - 处理用户偏好和会话记忆
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from loguru import logger


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
                    return data
            except Exception as e:
                logger.error(f"[MemoryManager] Failed to load memory: {e}")

        return self._get_default_memory()

    def _get_default_memory(self) -> Dict:
        """获取默认记忆结构"""
        return {
            "version": "1.0",
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

    def get_user_memories(self) -> List[Dict]:
        """获取用户记忆列表"""
        memory_data = self.load_memory()
        return memory_data.get("user_memories", [])

    def add_user_memory(self, content: str) -> bool:
        """添加用户偏好记忆"""
        if not content:
            return False

        try:
            memory_data = self.load_memory()
            user_memories = memory_data.get("user_memories", [])

            memory_exists = any(
                (isinstance(mem, dict) and mem.get("content", "") == content)
                or (mem == content)
                for mem in user_memories
            )

            if not memory_exists:
                user_memories.append(
                    {
                        "content": content,
                        "enabled": True,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )
                memory_data["user_memories"] = user_memories[-20:]
                return self.save_memory(memory_data)

            return True
        except Exception as e:
            logger.error(f"[MemoryManager] Failed to add user memory: {e}")
            return False

    def update_user_memories(self, memories: List[Dict]) -> bool:
        """更新用户记忆列表"""
        try:
            memory_data = self.load_memory()
            memory_data["user_memories"] = memories
            return self.save_memory(memory_data)
        except Exception as e:
            logger.error(f"[MemoryManager] Failed to update user memories: {e}")
            return False

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

    def get_context_string(self) -> str:
        """获取格式化后的记忆上下文字符串"""
        memory_data = self.load_memory()
        topics = memory_data.get("topics", [])
        user_memories = memory_data.get("user_memories", [])

        lines = []
        lines.append("## 长期记忆摘要")

        enabled_memories = []
        disabled_memories = []
        for m in user_memories:
            if isinstance(m, dict):
                content = m.get("content", "")
                enabled = m.get("enabled", True)
                if content:
                    if enabled:
                        enabled_memories.append(content)
                    else:
                        disabled_memories.append(content)
            elif isinstance(m, str) and m:
                enabled_memories.append(m)

        if enabled_memories:
            lines.append("【用户偏好】：")
            for i, mem in enumerate(enabled_memories[-10:], 1):
                lines.append(f"{i}. {mem}")
            lines.append("")

        if disabled_memories:
            lines.append(f"【历史记忆】（已禁用，供参考）：")
            for mem in disabled_memories[-5:]:
                lines.append(f"- {mem}")
            lines.append("")

        if topics:
            recent_topics = topics[-5:]
            topic_names = [
                t.get("topic", "") if isinstance(t, dict) else str(t)
                for t in recent_topics
            ]
            topic_names = [t for t in topic_names if t]
            if topic_names:
                lines.append(f"【最近讨论主题】{', '.join(topic_names)}")

        if not topics and not user_memories:
            lines.append("暂无长期记忆，系统将逐步积累用户偏好与会话要点。")

        lines.append("")
        lines.append("请根据以上用户偏好和记忆信息，在回复中保持一致性并体现个性化。")
        return "\n".join(lines)

    def set_canvas_name(self, canvas_name: str):
        """设置画布名称（切换工作区时调用）"""
        self._canvas_name = canvas_name
        self._ensure_memory_file()
