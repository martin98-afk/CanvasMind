# -*- coding: utf-8 -*-
"""
InterAgentMessage - 身份间消息结构与消息队列管理

管理智能体之间的消息传递，直接通过 agent_id 定位消息。
"""

import json
import threading
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional

from loguru import logger


@dataclass
class InterAgentMessage:
    """身份间消息"""
    id: str  # 消息ID
    from_agent: str  # 发送者ID
    from_agent_name: str  # 发送者名称
    from_agent_color: str  # 发送者颜色
    to_agent: str  # 接收者ID（唯一标识）
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

    def dequeue(self, agent_id: str) -> Optional[InterAgentMessage]:
        """取出指定 agent 的消息（如果存在）"""
        with self._lock:
            for i, msg in enumerate(self._queue):
                if msg.to_agent == agent_id:
                    return self._queue.pop(i)
            return None

    def peek(self, agent_id: str) -> List[InterAgentMessage]:
        """查看指定 agent 的所有消息（不移除）"""
        with self._lock:
            return [msg for msg in self._queue if msg.to_agent == agent_id]

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
        from_agent_name: str,
        from_agent_color: str,
        to_agent: str,
        content: str,
        need_callback: bool = False,
    ) -> InterAgentMessage:
        """发送消息给目标智能体"""
        message = InterAgentMessage(
            id=str(uuid.uuid4()),
            from_agent=from_agent,
            from_agent_name=from_agent_name,
            from_agent_color=from_agent_color,
            to_agent=to_agent,
            content=content,
            need_callback=need_callback,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            status="pending",
        )

        # 加入队列
        self._queue.enqueue(message)

        return message

    def broadcast_message(
        self,
        from_agent: str,
        from_agent_name: str,
        from_agent_color: str,
        to_agents: List[str],
        content: str,
    ) -> List[InterAgentMessage]:
        """广播消息给多个智能体"""
        messages = []
        for to_agent in to_agents:
            msg = self.send_message(
                from_agent=from_agent,
                from_agent_name=from_agent_name,
                from_agent_color=from_agent_color,
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

    def get_pending_messages(self, agent_id: str) -> List[InterAgentMessage]:
        """获取指定 agent 的待处理消息"""
        messages = self._queue.peek(agent_id)
        return [m for m in messages if m.status == "pending"]

    def pop_message(self, agent_id: str) -> Optional[InterAgentMessage]:
        """弹出指定 agent 的消息"""
        return self._queue.dequeue(agent_id)


def get_message_manager() -> InterAgentMessageManager:
    """获取全局消息管理器实例"""
    return InterAgentMessageManager.get_instance()
