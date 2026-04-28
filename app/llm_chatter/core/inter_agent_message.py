# -*- coding: utf-8 -*-
"""
InterAgentMessage - 身份间消息结构与消息队列管理

管理智能体之间的消息传递，支持：
- 消息持久化到 SQLite
- 队列管理（自动/手动触发）
- 消息状态跟踪
"""

import json
import threading
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

from loguru import logger

from app.llm_chatter.core.agent_registry import get_agent_registry


@dataclass
class InterAgentMessage:
    """身份间消息"""
    id: str  # 消息ID
    from_agent: str  # 发送者ID
    from_session: str  # 发送者会话ID
    to_agent: str  # 接收者ID
    content: str  # 消息内容
    need_callback: bool  # 是否需要回调
    created_at: str  # 创建时间
    status: str = "pending"  # pending / delivered / processed

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "InterAgentMessage":
        return cls(**data)


class MessageQueue:
    """消息队列管理器"""

    def __init__(self):
        self._queue: List[InterAgentMessage] = []
        self._lock = threading.Lock()

    def enqueue(self, message: InterAgentMessage) -> None:
        """将消息加入队列"""
        with self._lock:
            self._queue.append(message)
            logger.info(f"[MessageQueue] Enqueued: {message.id} -> {message.to_agent}")

    def dequeue(self, session_id: str, agent_id: str = None) -> Optional[InterAgentMessage]:
        """取出指定会话的消息（如果存在）"""
        with self._lock:
            agent_reg = get_agent_registry()
            for i, msg in enumerate(self._queue):
                # 优先通过 agent_id 匹配
                if agent_id:
                    if msg.to_agent == agent_id:
                        return self._queue.pop(i)
                    continue

                # 如果没有指定 agent_id，则通过 session_id 匹配
                target_agent = agent_reg.get_agent(msg.to_agent)
                if target_agent and target_agent.session_id == session_id:
                    return self._queue.pop(i)
            return None

    def peek(self, session_id: str, agent_id: str = None) -> List[InterAgentMessage]:
        """查看指定会话的所有消息（不移除）"""
        with self._lock:
            agent_reg = get_agent_registry()
            result = []
            for msg in self._queue:
                # 优先通过 agent_id 匹配
                if agent_id:
                    if msg.to_agent == agent_id:
                        result.append(msg)
                    continue

                # 如果没有指定 agent_id，则通过 session_id 匹配
                target_agent = agent_reg.get_agent(msg.to_agent)
                if target_agent and target_agent.session_id == session_id:
                    result.append(msg)
            return result

    def update_status(self, message_id: str, status: str) -> bool:
        """更新消息状态"""
        with self._lock:
            for msg in self._queue:
                if msg.id == message_id:
                    msg.status = status
                    return True
            return False

    def clear(self) -> None:
        """清空队列"""
        with self._lock:
            self._queue.clear()


class InterAgentMessageManager:
    """身份间消息管理器"""

    _instance: Optional["InterAgentMessageManager"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._queue = MessageQueue()
        self._message_store_path = Path("canvas_files/agents/messages")
        self._message_store_path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_instance(cls) -> "InterAgentMessageManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def send_message(
        self,
        from_agent: str,
        from_session: str,
        to_agent: str,
        content: str,
        need_callback: bool = False,
    ) -> InterAgentMessage:
        """发送消息给目标智能体"""
        message = InterAgentMessage(
            id=str(uuid.uuid4()),
            from_agent=from_agent,
            from_session=from_session,
            to_agent=to_agent,
            content=content,
            need_callback=need_callback,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            status="pending",
        )

        # 加入队列
        self._queue.enqueue(message)

        # 持久化消息
        self._persist_message(message)

        return message

    def broadcast_message(
        self,
        from_agent: str,
        from_session: str,
        to_agents: List[str],
        content: str,
    ) -> List[InterAgentMessage]:
        """广播消息给多个智能体"""
        messages = []
        for to_agent in to_agents:
            msg = self.send_message(
                from_agent=from_agent,
                from_session=from_session,
                to_agent=to_agent,
                content=content,
                need_callback=False,
            )
            messages.append(msg)
        return messages

    def deliver_message(self, message_id: str) -> bool:
        """投递消息（状态变为 delivered）"""
        return self._queue.update_status(message_id, "delivered")

    def process_message(self, message_id: str) -> bool:
        """处理消息（状态变为 processed）"""
        return self._queue.update_status(message_id, "processed")

    def get_pending_messages(self, session_id: str, agent_id: str = None) -> List[InterAgentMessage]:
        """获取指定会话的待处理消息"""
        messages = self._queue.peek(session_id, agent_id)
        return [m for m in messages if m.status == "pending"]

    def pop_message(self, session_id: str, agent_id: str = None) -> Optional[InterAgentMessage]:
        """弹出指定会话的消息"""
        return self._queue.dequeue(session_id, agent_id)

    def _persist_message(self, message: InterAgentMessage) -> None:
        """持久化消息到文件"""
        try:
            msg_file = self._message_store_path / f"{message.id}.json"
            with open(msg_file, "w", encoding="utf-8") as f:
                json.dump(message.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[InterAgentMessage] Persist failed: {e}")

    def load_messages_for_session(self, session_id: str) -> List[InterAgentMessage]:
        """从持久化存储加载指定会话的消息"""
        messages = []
        agent_reg = get_agent_registry()
        target_agent = agent_reg.get_agent_by_session(session_id)

        if not target_agent:
            return messages

        for msg_file in self._message_store_path.glob("*.json"):
            try:
                with open(msg_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("to_agent") == target_agent.id:
                        messages.append(InterAgentMessage.from_dict(data))
            except Exception:
                continue

        return messages


def get_message_manager() -> InterAgentMessageManager:
    """获取全局消息管理器实例"""
    return InterAgentMessageManager.get_instance()
