# 多智能体协作系统 - 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现多智能体协作系统，支持多个具有不同角色的智能体在不同会话窗口中并行工作，通过消息传递机制相互协作完成任务。

**Architecture:** 
- 核心组件 `AgentRegistry` 作为单例管理全局身份注册表
- 每个会话窗口绑定一个 `AgentRole`，通过窗口属性 `agent_role` 关联
- 协作工具 (`send_to_agent`, `broadcast_to_agents`, `list_agents`, `get_work_outcomes`) 通过工具系统调用
- 跨身份消息通过消息队列管理，持久化到 SQLite

**Tech Stack:** Python, PyQt5, SQLite, threading

---

## 第一章：核心基础设施

### Task 1: 实现 AgentRegistry 身份注册表（单例）

**Files:**
- Create: `llm_chatter/core/agent_registry.py`

```python
# -*- coding: utf-8 -*-
"""
AgentRegistry - 全局身份注册表（单例模式）

管理所有会话窗口的身份注册，提供：
- 注册/注销身份
- 查询身份列表（含工作状态）
- 更新工作状态
- 智能路由（找空闲的同类型智能体）
"""

import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import json

from loguru import logger


@dataclass
class AgentInfo:
    """智能体信息"""
    id: str                    # 唯一标识，如 "developer_1"
    name: str                  # 显示名称，如 "开发者1"
    session_id: str             # 绑定的会话ID
    role_type: str              # 角色类型：coordinator, developer, designer, tester, custom
    prompt: str                 # 角色提示词
    color: str                  # 颜色，如 "#4EC9B0"
    status: str = "idle"        # idle / busy / done
    progress: int = 0           # 进度 0-100
    task: str = ""              # 当前任务描述
    workdir: str = ""           # 工作产物目录
    created_at: str = ""        # 创建时间
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "AgentInfo":
        return cls(**data)


class AgentRegistry:
    """全局身份注册表（单例）"""
    
    _instance: Optional["AgentRegistry"] = None
    _lock = threading.Lock()
    
    def __init__(self):
        self._agents: Dict[str, AgentInfo] = {}  # agent_id -> AgentInfo
        self._session_to_agent: Dict[str, str] = {}  # session_id -> agent_id
        self._type_counters: Dict[str, int] = {}  # role_type -> counter for ID generation
    
    @classmethod
    def get_instance(cls) -> "AgentRegistry":
        """获取单例实例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def register(
        self,
        session_id: str,
        agent_id: Optional[str] = None,
        role_type: str = "custom",
        name: str = "",
        prompt: str = "",
        color: str = "#888888",
        workdir: str = "",
    ) -> AgentInfo:
        """注册一个新身份"""
        with self._lock:
            # 如果已存在 session 对应的 agent，先注销
            if session_id in self._session_to_agent:
                old_agent_id = self._session_to_agent[session_id]
                self._agents.pop(old_agent_id, None)
            
            # 生成 agent_id
            if not agent_id:
                agent_id = self._generate_agent_id(role_type)
            
            # 创建 AgentInfo
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            agent = AgentInfo(
                id=agent_id,
                name=name or agent_id,
                session_id=session_id,
                role_type=role_type,
                prompt=prompt,
                color=color,
                status="idle",
                progress=0,
                task="",
                workdir=workdir or self._default_workdir(session_id),
                created_at=now,
            )
            
            self._agents[agent_id] = agent
            self._session_to_agent[session_id] = agent_id
            
            logger.info(f"[AgentRegistry] Registered: {agent_id} -> session {session_id}")
            return agent
    
    def unregister(self, session_id: str) -> bool:
        """注销身份"""
        with self._lock:
            agent_id = self._session_to_agent.pop(session_id, None)
            if agent_id:
                self._agents.pop(agent_id, None)
                logger.info(f"[AgentRegistry] Unregistered: {agent_id}")
                return True
            return False
    
    def get_agent(self, agent_id: str) -> Optional[AgentInfo]:
        """根据 ID 获取智能体"""
        return self._agents.get(agent_id)
    
    def get_agent_by_session(self, session_id: str) -> Optional[AgentInfo]:
        """根据 session_id 获取智能体"""
        agent_id = self._session_to_agent.get(session_id)
        return self._agents.get(agent_id) if agent_id else None
    
    def list_agents(self, role_type: Optional[str] = None) -> List[AgentInfo]:
        """列出所有智能体，可按角色类型过滤"""
        with self._lock:
            agents = list(self._agents.values())
            if role_type:
                agents = [a for a in agents if a.role_type == role_type]
            return agents
    
    def list_all_agents_with_status(self) -> List[Dict]:
        """列出所有智能体及其状态（用于 list_agents 工具返回）"""
        agents = self.list_agents()
        result = []
        for agent in agents:
            item = {
                "id": agent.id,
                "name": agent.name,
                "status": agent.status,
                "session_id": agent.session_id,
            }
            if agent.status == "busy":
                item["progress"] = agent.progress
                item["task"] = agent.task
            result.append(item)
        return result
    
    def update_status(
        self,
        session_id: str,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        task: Optional[str] = None,
    ) -> bool:
        """更新智能体状态"""
        agent = self.get_agent_by_session(session_id)
        if not agent:
            return False
        
        with self._lock:
            if status is not None:
                agent.status = status
            if progress is not None:
                agent.progress = progress
            if task is not None:
                agent.task = task
        
        return True
    
    def find_idle_agent(self, role_type: str) -> Optional[AgentInfo]:
        """查找空闲的同类型智能体（智能路由）"""
        with self._lock:
            idle_agents = [
                a for a in self._agents.values()
                if a.role_type == role_type and a.status == "idle"
            ]
            return idle_agents[0] if idle_agents else None
    
    def _generate_agent_id(self, role_type: str) -> str:
        """生成唯一的 agent_id"""
        counter = self._type_counters.get(role_type, 0) + 1
        self._type_counters[role_type] = counter
        
        if counter == 1:
            return role_type
        return f"{role_type}_{counter}"
    
    def _default_workdir(self, session_id: str) -> str:
        """生成默认的工作目录路径"""
        return f"canvas_files/agents/{session_id}/outcomes"
    
    def reset(self):
        """重置注册表（用于测试）"""
        with self._lock:
            self._agents.clear()
            self._session_to_agent.clear()
            self._type_counters.clear()


# 全局访问函数
def get_agent_registry() -> AgentRegistry:
    """获取全局 AgentRegistry 实例"""
    return AgentRegistry.get_instance()
```

- [ ] **Step 1: 创建文件 `llm_chatter/core/agent_registry.py`**

```python
# -*- coding: utf-8 -*-
"""
AgentRegistry - 全局身份注册表（单例模式）
"""

import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path
import json

from loguru import logger


@dataclass
class AgentInfo:
    """智能体信息"""
    id: str
    name: str
    session_id: str
    role_type: str
    prompt: str
    color: str
    status: str = "idle"
    progress: int = 0
    task: str = ""
    workdir: str = ""
    created_at: str = ""
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "AgentInfo":
        return cls(**data)


class AgentRegistry:
    """全局身份注册表（单例）"""
    
    _instance: Optional["AgentRegistry"] = None
    _lock = threading.Lock()
    
    def __init__(self):
        self._agents: Dict[str, AgentInfo] = {}
        self._session_to_agent: Dict[str, str] = {}
        self._type_counters: Dict[str, int] = {}
    
    @classmethod
    def get_instance(cls) -> "AgentRegistry":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def register(
        self,
        session_id: str,
        agent_id: Optional[str] = None,
        role_type: str = "custom",
        name: str = "",
        prompt: str = "",
        color: str = "#888888",
        workdir: str = "",
    ) -> AgentInfo:
        with self._lock:
            if session_id in self._session_to_agent:
                old_agent_id = self._session_to_agent[session_id]
                self._agents.pop(old_agent_id, None)
            
            if not agent_id:
                agent_id = self._generate_agent_id(role_type)
            
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            agent = AgentInfo(
                id=agent_id,
                name=name or agent_id,
                session_id=session_id,
                role_type=role_type,
                prompt=prompt,
                color=color,
                status="idle",
                progress=0,
                task="",
                workdir=workdir or self._default_workdir(session_id),
                created_at=now,
            )
            
            self._agents[agent_id] = agent
            self._session_to_agent[session_id] = agent_id
            
            logger.info(f"[AgentRegistry] Registered: {agent_id} -> session {session_id}")
            return agent
    
    def unregister(self, session_id: str) -> bool:
        with self._lock:
            agent_id = self._session_to_agent.pop(session_id, None)
            if agent_id:
                self._agents.pop(agent_id, None)
                logger.info(f"[AgentRegistry] Unregistered: {agent_id}")
                return True
            return False
    
    def get_agent(self, agent_id: str) -> Optional[AgentInfo]:
        return self._agents.get(agent_id)
    
    def get_agent_by_session(self, session_id: str) -> Optional[AgentInfo]:
        agent_id = self._session_to_agent.get(session_id)
        return self._agents.get(agent_id) if agent_id else None
    
    def list_agents(self, role_type: Optional[str] = None) -> List[AgentInfo]:
        with self._lock:
            agents = list(self._agents.values())
            if role_type:
                agents = [a for a in agents if a.role_type == role_type]
            return agents
    
    def list_all_agents_with_status(self) -> List[Dict]:
        agents = self.list_agents()
        result = []
        for agent in agents:
            item = {
                "id": agent.id,
                "name": agent.name,
                "status": agent.status,
                "session_id": agent.session_id,
            }
            if agent.status == "busy":
                item["progress"] = agent.progress
                item["task"] = agent.task
            result.append(item)
        return result
    
    def update_status(
        self,
        session_id: str,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        task: Optional[str] = None,
    ) -> bool:
        agent = self.get_agent_by_session(session_id)
        if not agent:
            return False
        
        with self._lock:
            if status is not None:
                agent.status = status
            if progress is not None:
                agent.progress = progress
            if task is not None:
                agent.task = task
        
        return True
    
    def find_idle_agent(self, role_type: str) -> Optional[AgentInfo]:
        with self._lock:
            idle_agents = [
                a for a in self._agents.values()
                if a.role_type == role_type and a.status == "idle"
            ]
            return idle_agents[0] if idle_agents else None
    
    def _generate_agent_id(self, role_type: str) -> str:
        counter = self._type_counters.get(role_type, 0) + 1
        self._type_counters[role_type] = counter
        if counter == 1:
            return role_type
        return f"{role_type}_{counter}"
    
    def _default_workdir(self, session_id: str) -> str:
        return f"canvas_files/agents/{session_id}/outcomes"
    
    def reset(self):
        with self._lock:
            self._agents.clear()
            self._session_to_agent.clear()
            self._type_counters.clear()


def get_agent_registry() -> AgentRegistry:
    return AgentRegistry.get_instance()
```

- [ ] **Step 2: 在 `llm_chatter/core/__init__.py` 中导出**

修改 `llm_chatter/core/__init__.py`，添加：
```python
from .agent_registry import AgentRegistry, AgentInfo, get_agent_registry
```

- [ ] **Step 3: 验证语法**

Run: `python -m py_compile llm_chatter/core/agent_registry.py`
Expected: 无输出（成功）

---

### Task 2: 实现 InterAgentMessage 消息结构与消息队列

**Files:**
- Create: `llm_chatter/core/inter_agent_message.py`

```python
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
    id: str                    # 消息ID
    from_agent: str            # 发送者ID
    from_session: str          # 发送者会话ID
    to_agent: str              # 接收者ID
    content: str               # 消息内容
    need_callback: bool        # 是否需要回调
    created_at: str             # 创建时间
    status: str = "pending"    # pending / delivered / processed
    
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
    
    def dequeue(self, session_id: str) -> Optional[InterAgentMessage]:
        """取出指定会话的消息（如果存在）"""
        with self._lock:
            for i, msg in enumerate(self._queue):
                # 找到目标会话的消息（通过 to_agent 匹配 session）
                agent_reg = get_agent_registry()
                target_agent = agent_reg.get_agent(msg.to_agent)
                if target_agent and target_agent.session_id == session_id:
                    return self._queue.pop(i)
            return None
    
    def peek(self, session_id: str) -> List[InterAgentMessage]:
        """查看指定会话的所有消息（不移除）"""
        with self._lock:
            agent_reg = get_agent_registry()
            result = []
            for msg in self._queue:
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
    
    def deliver_message(self, message_id: str) -> bool:
        """投递消息（状态变为 delivered）"""
        return self._queue.update_status(message_id, "delivered")
    
    def process_message(self, message_id: str) -> bool:
        """处理消息（状态变为 processed）"""
        return self._queue.update_status(message_id, "processed")
    
    def get_pending_messages(self, session_id: str) -> List[InterAgentMessage]:
        """获取指定会话的待处理消息"""
        return self._queue.peek(session_id)
    
    def pop_message(self, session_id: str) -> Optional[InterAgentMessage]:
        """弹出指定会话的消息"""
        return self._queue.dequeue(session_id)
    
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
```

- [ ] **Step 1: 创建文件 `llm_chatter/core/inter_agent_message.py`**

```python
# -*- coding: utf-8 -*-
"""
InterAgentMessage - 身份间消息结构与消息队列管理
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
    id: str
    from_agent: str
    from_session: str
    to_agent: str
    content: str
    need_callback: bool
    created_at: str
    status: str = "pending"
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "InterAgentMessage":
        return cls(**data)


class MessageQueue:
    def __init__(self):
        self._queue: List[InterAgentMessage] = []
        self._lock = threading.Lock()
    
    def enqueue(self, message: InterAgentMessage) -> None:
        with self._lock:
            self._queue.append(message)
            logger.info(f"[MessageQueue] Enqueued: {message.id} -> {message.to_agent}")
    
    def dequeue(self, session_id: str) -> Optional[InterAgentMessage]:
        with self._lock:
            agent_reg = get_agent_registry()
            for i, msg in enumerate(self._queue):
                target_agent = agent_reg.get_agent(msg.to_agent)
                if target_agent and target_agent.session_id == session_id:
                    return self._queue.pop(i)
            return None
    
    def peek(self, session_id: str) -> List[InterAgentMessage]:
        with self._lock:
            agent_reg = get_agent_registry()
            result = []
            for msg in self._queue:
                target_agent = agent_reg.get_agent(msg.to_agent)
                if target_agent and target_agent.session_id == session_id:
                    result.append(msg)
            return result
    
    def update_status(self, message_id: str, status: str) -> bool:
        with self._lock:
            for msg in self._queue:
                if msg.id == message_id:
                    msg.status = status
                    return True
            return False
    
    def clear(self) -> None:
        with self._lock:
            self._queue.clear()


class InterAgentMessageManager:
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
        self._queue.enqueue(message)
        self._persist_message(message)
        return message
    
    def deliver_message(self, message_id: str) -> bool:
        return self._queue.update_status(message_id, "delivered")
    
    def process_message(self, message_id: str) -> bool:
        return self._queue.update_status(message_id, "processed")
    
    def get_pending_messages(self, session_id: str) -> List[InterAgentMessage]:
        return self._queue.peek(session_id)
    
    def pop_message(self, session_id: str) -> Optional[InterAgentMessage]:
        return self._queue.dequeue(session_id)
    
    def _persist_message(self, message: InterAgentMessage) -> None:
        try:
            msg_file = self._message_store_path / f"{message.id}.json"
            with open(msg_file, "w", encoding="utf-8") as f:
                json.dump(message.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[InterAgentMessage] Persist failed: {e}")
    
    def load_messages_for_session(self, session_id: str) -> List[InterAgentMessage]:
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
    return InterAgentMessageManager.get_instance()
```

- [ ] **Step 2: 在 `llm_chatter/core/__init__.py` 中导出**

添加：
```python
from .inter_agent_message import InterAgentMessage, InterAgentMessageManager, get_message_manager
```

- [ ] **Step 3: 验证语法**

Run: `python -m py_compile llm_chatter/core/inter_agent_message.py`
Expected: 无输出（成功）

---

## 第二章：预制角色

### Task 4: 创建预制角色文件

**Files:**
- Create: `llm_chatter/agents/coordinator.md`
- Create: `llm_chatter/agents/developer.md`
- Create: `llm_chatter/agents/designer.md`
- Create: `llm_chatter/agents/tester.md`

- [ ] **Step 1: 创建 `llm_chatter/agents/coordinator.md`**

```markdown
---
description: 任务分解、协调各方、进度跟踪、决策
mode: primary
hidden: false
temperature: 0.3
steps: 50
permission:
  read: allow
  glob: allow
  grep: allow
  list: allow
  bash: allow
  write: allow
  edit: allow
  patch: allow
  todowrite: allow
  todoread: allow
  skill: allow
  task: allow
  webfetch: allow
  websearch: allow
---

# Role
你是一个项目统筹者，负责整体协调和决策。你的工作将直接被团队成员使用。

# Primary Goal
- 任务分解 - 将复杂任务拆分为可执行的子任务
- 协调各方 - 协调开发者、设计者、测试者的工作
- 进度跟踪 - 跟踪各成员的任务进度
- 决策 - 在关键节点做出决策

# Execution Workflow
1. 接收用户/上级的任务
2. 分析任务，拆分为子任务
3. 使用 send_to_agent 派发任务给合适的成员
4. 跟踪进度，协调冲突
5. 汇总结果，做出决策

# Hard Rules
- 所有任务必须通过 send_to_agent 派发
- 任务描述要清晰，包含输入输出要求
- 完成后如果 need_callback=true，必须回复发送方
- 重要决策需要记录到工作目录

# Important: Task Completion Summary
当你完成协调任务后，提供详细的进度报告，包含：
1. 已完成的工作
2. 进行中的工作
3. 遇到的问题和解决方案
4. 后续计划

总结报告将用于向上级汇报或协调团队。
```

- [ ] **Step 2: 创建 `llm_chatter/agents/developer.md`**

```markdown
---
description: 代码实现、功能开发、技术方案
mode: primary
hidden: false
temperature: 0.2
steps: 50
permission:
  read: allow
  glob: allow
  grep: allow
  list: allow
  bash: allow
  write: allow
  edit: allow
  patch: allow
  todowrite: allow
  todoread: allow
  skill: allow
  task: allow
  webfetch: allow
  websearch: allow
---

# Role
你是一个开发专家，负责代码实现、功能开发和制定技术方案。

# Primary Goal
- 代码实现 - 根据需求编写高质量代码
- 功能开发 - 实现完整的功能模块
- 技术方案 - 制定可行的技术实现方案

# Execution Workflow
1. 接收来自其他成员的任务（通过用户卡片显示）
2. 理解任务需求，查看相关文档/代码
3. 实现功能，输出到指定目录
4. 使用 send_to_agent 通知相关成员（测试、设计等）
5. 如需回调，使用 send_to_agent 回复发送方

# Hard Rules
- 所有工作产物必须保存到你的工作目录：`canvas_files/agents/{session_id}/outcomes/`
- 文件命名规范：序号_功能名，如 `01_登录模块.py`
- 完成重要功能后，使用 send_to_agent 通知相关成员
- 如需回调，使用 send_to_agent 回复发送方

# Important: Work Output
当你完成开发任务后，必须：
1. 将代码保存到工作目录
2. 在输出中明确文件路径
3. 通知相关的测试者或协调者

示例：
```
已完成登录模块开发，文件位置：
canvas_files/agents/{session_id}/outcomes/01_登录模块.py
请通知测试者进行测试。
```

# Progress Report Format
你可以在回复中包含进度更新，格式如下：
```
[进度更新] 60% - 正在实现登录验证逻辑
```
系统会自动解析并更新你的工作状态。
```

- [ ] **Step 3: 创建 `llm_chatter/agents/designer.md`**

```markdown
---
description: 界面设计、交互设计、视觉方案
mode: primary
hidden: false
temperature: 0.4
steps: 40
permission:
  read: allow
  glob: allow
  grep: allow
  list: allow
  bash: allow
  write: allow
  edit: allow
  patch: allow
  todowrite: allow
  todoread: allow
  skill: allow
  task: allow
  webfetch: allow
  websearch: allow
---

# Role
你是一个设计专家，负责界面设计、交互设计和视觉方案的制定。

# Primary Goal
- 界面设计 - 设计美观、易用的用户界面
- 交互设计 - 设计流畅的用户交互流程
- 视觉方案 - 制定统一的视觉风格和配色方案

# Execution Workflow
1. 接收来自其他成员的设计需求
2. 分析需求，理解业务场景
3. 创建设计文档或原型描述
4. 保存到工作目录
5. 使用 send_to_agent 通知相关成员

# Hard Rules
- 所有设计文档必须保存到你的工作目录：`canvas_files/agents/{session_id}/outcomes/`
- 设计文档要包含详细的尺寸、颜色、交互说明
- 完成设计后，使用 send_to_agent 通知开发者
- 如需回调，使用 send_to_agent 回复发送方

# Important: Design Output
当你完成设计任务后，必须：
1. 将设计文档保存到工作目录
2. 在输出中明确文件路径
3. 通知相关的开发者或协调者

示例：
```
已完成登录界面设计，文件位置：
canvas_files/agents/{session_id}/outcomes/01_登录界面设计.md
请开发者按照设计实现。
```

# Progress Report Format
你可以在回复中包含进度更新，格式如下：
```
[进度更新] 50% - 正在设计首页布局
```
系统会自动解析并更新你的工作状态。
```

- [ ] **Step 4: 创建 `llm_chatter/agents/tester.md`**

```markdown
---
description: 测试用例编写、Bug 发现、质量把关
mode: primary
hidden: false
temperature: 0.1
steps: 50
permission:
  read: allow
  glob: allow
  grep: allow
  list: allow
  bash: allow
  write: allow
  edit: allow
  patch: allow
  todowrite: allow
  todoread: allow
  skill: allow
  task: allow
  webfetch: deny
  websearch: deny
---

# Role
你是一个测试专家，负责测试用例编写、Bug 发现和质量把关。

# Primary Goal
- 测试用例 - 编写全面的测试用例
- Bug 发现 - 发现并描述问题
- 质量把关 - 确保交付质量

# Execution Workflow
1. 接收来自开发者或协调者的测试任务
2. 查看相关文件和需求
3. 编写测试用例或进行测试
4. 记录发现的问题
5. 使用 send_to_agent 反馈结果

# Hard Rules
- 测试报告必须保存到你的工作目录：`canvas_files/agents/{session_id}/outcomes/`
- Bug 描述要清晰，包含复现步骤
- 完成测试后，使用 send_to_agent 通知相关成员
- 如需回调，使用 send_to_agent 回复发送方

# Important: Test Output
当你完成测试任务后，必须：
1. 将测试报告保存到工作目录
2. 在输出中明确文件路径
3. 通知相关的开发者或协调者

示例：
```
测试完成，发现 1 个 Bug，文件位置：
canvas_files/agents/{session_id}/outcomes/01_测试报告.md
Bug: 验证码超时未处理
建议：增加超时错误提示
```

# Progress Report Format
你可以在回复中包含进度更新，格式如下：
```
[进度更新] 70% - 正在测试登录功能
```
系统会自动解析并更新你的工作状态。
```

- [ ] **Step 5: 验证文件创建**

Run: `dir llm_chatter\agents\*.md`
Expected: coordinator.md, developer.md, designer.md, tester.md

---

### Task 5: 实现角色配置与加载（复用现有 AgentManager）

**Files:**
- Create: `llm_chatter/core/role_config.py`
- Modify: `llm_chatter/core/agent.py` (添加角色配置加载)

- [ ] **Step 1: 创建 `llm_chatter/core/role_config.py`**

```python
# -*- coding: utf-8 -*-
"""
RoleConfig - 角色配置管理

管理预制角色和自定义角色，支持：
- 加载预制角色
- 保存/加载自定义角色
- 角色配置导出/导入
"""

import json
import threading
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path
import shutil

from loguru import logger

from app.llm_chatter.core.agent import Agent


@dataclass
class RoleConfig:
    """角色配置"""
    id: str                     # 角色 ID
    name: str                   # 显示名称
    role_type: str              # 角色类型：coordinator, developer, designer, tester, custom
    prompt: str                 # 提示词
    color: str                  # 颜色
    is_preset: bool = True      # 是否预制角色
    created_at: str = ""        # 创建时间
    updated_at: str = ""        # 更新时间
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "RoleConfig":
        return cls(**data)
    
    def to_markdown(self) -> str:
        """转换为 Markdown 格式（用于 AgentManager 加载）"""
        meta = {
            "description": self.name,
            "mode": "primary",
            "hidden": False,
            "temperature": 0.3,
            "color": self.color,
        }
        meta_yaml = "\n".join(f"{k}: {v}" for k, v in meta.items())
        return f"---\n{meta_yaml}\n---\n\n{self.prompt}"


class RoleConfigManager:
    """角色配置管理器"""
    
    _instance: Optional["RoleConfigManager"] = None
    _lock = threading.Lock()
    
    def __init__(self):
        self._roles: Dict[str, RoleConfig] = {}
        self._custom_roles_dir = Path("canvas_files/agents/custom_roles")
        self._custom_roles_dir.mkdir(parents=True, exist_ok=True)
        self._load_preset_roles()
        self._load_custom_roles()
    
    @classmethod
    def get_instance(cls) -> "RoleConfigManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def _load_preset_roles(self) -> None:
        """加载预制角色"""
        preset_files = {
            "coordinator": Path(__file__).parent.parent / "agents" / "coordinator.md",
            "developer": Path(__file__).parent.parent / "agents" / "developer.md",
            "designer": Path(__file__).parent.parent / "agents" / "designer.md",
            "tester": Path(__file__).parent.parent / "agents" / "tester.md",
        }
        
        for role_type, file_path in preset_files.items():
            if file_path.exists():
                try:
                    config = self._parse_role_file(file_path, role_type, is_preset=True)
                    self._roles[role_type] = config
                    logger.info(f"[RoleConfig] Loaded preset: {role_type}")
                except Exception as e:
                    logger.error(f"[RoleConfig] Failed to load {role_type}: {e}")
    
    def _load_custom_roles(self) -> None:
        """加载自定义角色"""
        for json_file in self._custom_roles_dir.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    config = RoleConfig.from_dict(data)
                    self._roles[config.id] = config
                    logger.info(f"[RoleConfig] Loaded custom: {config.id}")
            except Exception as e:
                logger.error(f"[RoleConfig] Failed to load {json_file}: {e}")
    
    def _parse_role_file(self, file_path: Path, role_type: str, is_preset: bool) -> RoleConfig:
        """解析角色 Markdown 文件"""
        import yaml
        
        content = file_path.read_text(encoding="utf-8")
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                meta = yaml.safe_load(parts[1]) or {}
                prompt = parts[2].strip()
            else:
                meta = {}
                prompt = content
        else:
            meta = {}
            prompt = content
        
        name = meta.get("description", role_type)
        color = meta.get("color", "#888888")
        
        return RoleConfig(
            id=role_type,
            name=name,
            role_type=role_type,
            prompt=prompt,
            color=color,
            is_preset=is_preset,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
    
    def get_role(self, role_id: str) -> Optional[RoleConfig]:
        """获取角色配置"""
        return self._roles.get(role_id)
    
    def list_roles(self, include_preset: bool = True, include_custom: bool = True) -> List[RoleConfig]:
        """列出所有角色"""
        result = []
        for role in self._roles.values():
            if role.is_preset and include_preset:
                result.append(role)
            elif not role.is_preset and include_custom:
                result.append(role)
        return result
    
    def save_custom_role(self, config: RoleConfig) -> bool:
        """保存自定义角色"""
        try:
            config.is_preset = False
            config.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if not config.created_at:
                config.created_at = config.updated_at
            
            self._roles[config.id] = config
            
            json_file = self._custom_roles_dir / f"{config.id}.json"
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(config.to_dict(), f, ensure_ascii=False, indent=2)
            
            logger.info(f"[RoleConfig] Saved custom role: {config.id}")
            return True
        except Exception as e:
            logger.error(f"[RoleConfig] Failed to save {config.id}: {e}")
            return False
    
    def delete_custom_role(self, role_id: str) -> bool:
        """删除自定义角色"""
        if role_id in self._roles:
            role = self._roles[role_id]
            if role.is_preset:
                return False
            
            del self._roles[role_id]
            
            json_file = self._custom_roles_dir / f"{role_id}.json"
            if json_file.exists():
                json_file.unlink()
            
            logger.info(f"[RoleConfig] Deleted custom role: {role_id}")
            return True
        return False
    
    def get_agent_prompt(self, role_id: str) -> str:
        """获取角色的完整提示词"""
        role = self.get_role(role_id)
        return role.prompt if role else ""


def get_role_config_manager() -> RoleConfigManager:
    """获取全局角色配置管理器"""
    return RoleConfigManager.get_instance()
```

- [ ] **Step 2: 在 `llm_chatter/core/__init__.py` 中导出**

添加：
```python
from .role_config import RoleConfig, RoleConfigManager, get_role_config_manager
```

- [ ] **Step 3: 验证语法**

Run: `python -m py_compile llm_chatter/core/role_config.py`
Expected: 无输出（成功）

---

## 第三章：协作工具

### Task 6: 实现 InterAgentTools 协作工具集

**Files:**
- Create: `llm_chatter/tools/inter_agent_tools.py`

- [ ] **Step 1: 创建 `llm_chatter/tools/inter_agent_tools.py`**

```python
# -*- coding: utf-8 -*-
"""
InterAgentTools - 身份间协作工具

提供智能体间通信的工具：
- send_to_agent: 发送消息给指定成员
- broadcast_to_agents: 广播消息给多个成员
- list_agents: 查询团队成员状态
- get_work_outcomes: 获取工作产物列表
"""

from typing import Dict, List, Optional, Any

from loguru import logger

from app.llm_chatter.core.agent_registry import get_agent_registry
from app.llm_chatter.core.inter_agent_message import get_message_manager
from app.llm_chatter.tools.result import ToolResult


class InterAgentTools:
    """身份间协作工具"""
    
    def __init__(self, session_id: str = "", agent_id: str = ""):
        self._session_id = session_id
        self._agent_id = agent_id
        self._agent_registry = get_agent_registry()
        self._message_manager = get_message_manager()
    
    def send_to_agent(
        self,
        agent: str,
        message: str,
        need_callback: bool = False,
    ) -> ToolResult:
        """发送消息给团队中的其他成员"""
        try:
            # 查找目标智能体
            target = self._agent_registry.get_agent(agent)
            if not target:
                # 尝试智能路由
                role_type = agent.rsplit("_", 1)[0] if "_" in agent else agent
                idle = self._agent_registry.find_idle_agent(role_type)
                if idle:
                    target = idle
                else:
                    return ToolResult(False, f"未找到智能体: {agent}")
            
            # 获取发送者信息
            from_agent = self._agent_id
            from_session = self._session_id
            
            if not from_agent:
                current = self._agent_registry.get_agent_by_session(self._session_id)
                if current:
                    from_agent = current.id
                    from_session = current.session_id
            
            # 发送消息
            msg = self._message_manager.send_message(
                from_agent=from_agent,
                from_session=from_session,
                to_agent=target.id,
                content=message,
                need_callback=need_callback,
            )
            
            logger.info(f"[InterAgentTools] Sent to {target.id}: {msg.id}")
            
            return ToolResult(
                True,
                content=f"成功发送消息给 '{target.name}' ({target.id})。\n"
                       f"消息ID: {msg.id}\n"
                       f"目标状态: {target.status}\n"
                       f"{'需要回调' if need_callback else '无需回调'}",
            )
            
        except Exception as e:
            logger.error(f"[InterAgentTools] send_to_agent failed: {e}")
            return ToolResult(False, f"发送消息失败: {str(e)}")
    
    def broadcast_to_agents(
        self,
        agents: Optional[List[str]] = None,
        message: str = "",
    ) -> ToolResult:
        """同时向多个团队成员广播消息"""
        try:
            if not message:
                return ToolResult(False, "消息内容不能为空")
            
            # 确定目标列表
            if not agents:
                all_agents = self._agent_registry.list_agents()
                target_ids = [a.id for a in all_agents if a.id != self._agent_id]
            else:
                target_ids = agents
            
            if not target_ids:
                return ToolResult(True, content="没有可发送的目标成员")
            
            results = []
            for agent_id in target_ids:
                result = self.send_to_agent(agent_id, message, need_callback=False)
                results.append(f"{agent_id}: {'成功' if result.success else '失败'}")
            
            return ToolResult(
                True,
                content=f"广播完成：\n" + "\n".join(results),
            )
            
        except Exception as e:
            logger.error(f"[InterAgentTools] broadcast_to_agents failed: {e}")
            return ToolResult(False, f"广播失败: {str(e)}")
    
    def list_agents(self) -> ToolResult:
        """查询当前团队的所有成员及其工作状态"""
        try:
            agents = self._agent_registry.list_all_agents_with_status()
            
            if not agents:
                return ToolResult(True, content="当前没有团队成员")
            
            lines = ["## 团队成员状态\n"]
            for agent in agents:
                status_icon = "🟢" if agent["status"] == "idle" else "🟡" if agent["status"] == "busy" else "✅"
                lines.append(f"{status_icon} **{agent['name']}** ({agent['id']})")
                lines.append(f"   状态: {agent['status']}")
                
                if agent["status"] == "busy":
                    progress = agent.get("progress", 0)
                    task = agent.get("task", "")
                    lines.append(f"   进度: {progress}%")
                    if task:
                        lines.append(f"   任务: {task}")
                lines.append("")
            
            return ToolResult(True, content="\n".join(lines))
            
        except Exception as e:
            logger.error(f"[InterAgentTools] list_agents failed: {e}")
            return ToolResult(False, f"查询失败: {str(e)}")
    
    def get_work_outcomes(self, agent_id: Optional[str] = None) -> ToolResult:
        """获取团队成员的工作产物列表"""
        try:
            from app.llm_chatter.utils.work_outcome_manager import get_outcome_manager
            
            outcome_manager = get_outcome_manager()
            
            if agent_id:
                outcomes = outcome_manager.get_outcomes_by_agent(agent_id)
            else:
                outcomes = outcome_manager.get_all_outcomes()
            
            if not outcomes:
                return ToolResult(True, content="暂无工作产物")
            
            lines = ["## 工作产物\n"]
            for outcome in outcomes:
                lines.append(f"📄 **{outcome['name']}** ({outcome['agent_name']})")
                lines.append(f"   路径: `{outcome['path']}`")
                if outcome.get("description"):
                    lines.append(f"   描述: {outcome['description']}")
                lines.append("")
            
            return ToolResult(True, content="\n".join(lines))
            
        except ImportError:
            return ToolResult(False, error="工作产物管理器未实现")
        except Exception as e:
            logger.error(f"[InterAgentTools] get_work_outcomes failed: {e}")
            return ToolResult(False, f"查询失败: {str(e)}")


def get_inter_agent_tools(session_id: str = "", agent_id: str = "") -> InterAgentTools:
    return InterAgentTools(session_id, agent_id)


# 获取工具 Schema（用于注册到工具系统）
def get_tools_schema() -> List[Dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "send_to_agent",
                "description": "发送消息给团队中的其他成员。发送完成后即可结束任务，无需等待对方回复（除非 need_callback=true）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent": {
                            "type": "string",
                            "description": "目标身份ID，从 list_agents() 获取，例如 'developer' 或 'developer_1'"
                        },
                        "message": {
                            "type": "string",
                            "description": "要发送的消息内容，应该清晰描述任务要求和期望结果"
                        },
                        "need_callback": {
                            "type": "boolean",
                            "description": "是否需要回调。true=任务完成后对方会回复你；false=对方自行决定后续行动，默认 false"
                        }
                    },
                    "required": ["agent", "message"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "broadcast_to_agents",
                "description": "同时向多个团队成员广播消息。例如：评审时向所有人征询意见，或通知所有人任务变更。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agents": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "目标身份ID列表。null 或空数组表示发给所有成员"
                        },
                        "message": {
                            "type": "string",
                            "description": "要广播的消息内容"
                        }
                    },
                    "required": ["message"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_agents",
                "description": "查询当前团队的所有成员及其工作状态。用于了解谁空闲、谁忙碌，以便智能分配任务。",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_work_outcomes",
                "description": "获取团队成员已完成的工作产物列表，包括文件路径和描述。用于查看其他智能体的工作成果。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "智能体ID，如果为空则返回所有产物"
                        }
                    }
                }
            }
        },
    ]
```

- [ ] **Step 2: 在 `llm_chatter/tools/__init__.py` 中导出**

修改 `llm_chatter/tools/__init__.py`，添加：
```python
from .inter_agent_tools import InterAgentTools, get_inter_agent_tools, get_tools_schema
```

- [ ] **Step 3: 验证语法**

Run: `python -m py_compile llm_chatter/tools/inter_agent_tools.py`
Expected: 无输出（成功）

---

## 第四章：工作产物管理

### Task 3: 实现 WorkOutcomeManager 工作产物管理器

**Files:**
- Create: `llm_chatter/utils/work_outcome_manager.py`

- [ ] **Step 1: 创建 `llm_chatter/utils/work_outcome_manager.py`**

```python
# -*- coding: utf-8 -*-
"""
WorkOutcomeManager - 工作产物管理器

管理智能体的工作产物，支持：
- 产物注册和追踪
- 产物清单持久化
- 按智能体/时间查询
"""

import json
import threading
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

from loguru import logger


@dataclass
class WorkOutcome:
    """工作产物"""
    id: str                # 产物ID
    agent_id: str          # 所属智能体ID
    agent_name: str        # 所属智能体名称
    name: str              # 产物名称
    filename: str          # 文件名
    path: str              # 文件路径
    type: str              # file / directory
    size: int = 0          # 文件大小
    created_at: str         # 创建时间
    description: str = ""   # 产物描述


class WorkOutcomeManager:
    """工作产物管理器"""
    
    _instance: Optional["WorkOutcomeManager"] = None
    _lock = threading.Lock()
    
    def __init__(self):
        self._outcomes: List[WorkOutcome] = []
        self._agent_outcomes: Dict[str, List[str]] = {}  # agent_id -> [outcome_ids]
        self._base_dir = Path("canvas_files/agents")
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._load_all()
    
    @classmethod
    def get_instance(cls) -> "WorkOutcomeManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def _load_all(self) -> None:
        """加载所有智能体的产物"""
        if not self._base_dir.exists():
            return
        
        for agent_dir in self._base_dir.iterdir():
            if not agent_dir.is_dir():
                continue
            
            metadata_file = agent_dir / "outcomes" / "metadata.json"
            if metadata_file.exists():
                try:
                    with open(metadata_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        for outcome_data in data.get("outcomes", []):
                            outcome = WorkOutcome(**outcome_data)
                            self._outcomes.append(outcome)
                            
                            if outcome.agent_id not in self._agent_outcomes:
                                self._agent_outcomes[outcome.agent_id] = []
                            self._agent_outcomes[outcome.agent_id].append(outcome.id)
                except Exception as e:
                    logger.warning(f"[WorkOutcomeManager] Failed to load {metadata_file}: {e}")
    
    def register_outcome(
        self,
        agent_id: str,
        agent_name: str,
        name: str,
        file_path: str,
        description: str = "",
    ) -> Optional[WorkOutcome]:
        """注册一个新的工作产物"""
        try:
            path = Path(file_path)
            if not path.exists():
                logger.warning(f"[WorkOutcomeManager] File not found: {file_path}")
                return None
            
            filename = path.name
            size = path.stat().st_size if path.is_file() else 0
            is_dir = path.is_dir()
            
            outcome = WorkOutcome(
                id=str(uuid.uuid4()),
                agent_id=agent_id,
                agent_name=agent_name,
                name=name,
                filename=filename,
                path=str(path.resolve()),
                type="directory" if is_dir else "file",
                size=size,
                created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                description=description,
            )
            
            self._outcomes.append(outcome)
            
            if agent_id not in self._agent_outcomes:
                self._agent_outcomes[agent_id] = []
            self._agent_outcomes[agent_id].append(outcome.id)
            
            self._save_metadata(agent_id)
            
            logger.info(f"[WorkOutcomeManager] Registered: {name} for {agent_id}")
            return outcome
            
        except Exception as e:
            logger.error(f"[WorkOutcomeManager] Failed to register: {e}")
            return None
    
    def get_outcomes_by_agent(self, agent_id: str) -> List[Dict]:
        """获取指定智能体的所有产物"""
        outcome_ids = self._agent_outcomes.get(agent_id, [])
        results = []
        for outcome in self._outcomes:
            if outcome.id in outcome_ids:
                results.append(outcome.__dict__)
        return results
    
    def get_all_outcomes(self) -> List[Dict]:
        """获取所有产物"""
        return [o.__dict__ for o in self._outcomes]
    
    def delete_outcome(self, outcome_id: str) -> bool:
        """删除产物"""
        for i, outcome in enumerate(self._outcomes):
            if outcome.id == outcome_id:
                agent_id = outcome.agent_id
                self._outcomes.pop(i)
                if agent_id in self._agent_outcomes:
                    self._agent_outcomes[agent_id].remove(outcome_id)
                self._save_metadata(agent_id)
                return True
        return False
    
    def _save_metadata(self, agent_id: str) -> None:
        """保存 metadata.json"""
        try:
            session_id = None
            for outcome in self._outcomes:
                if outcome.agent_id == agent_id:
                    path = Path(outcome.path)
                    parts = path.parts
                    if "agents" in parts:
                        idx = parts.index("agents")
                        if idx + 1 < len(parts):
                            session_id = parts[idx + 1]
                            break
            
            if not session_id:
                return
            
            metadata_path = self._base_dir / session_id / "outcomes" / "metadata.json"
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            
            outcome_ids = self._agent_outcomes.get(agent_id, [])
            outcomes_data = []
            for outcome in self._outcomes:
                if outcome.id in outcome_ids:
                    outcomes_data.append(outcome.__dict__)
            
            metadata = {
                "agent_id": agent_id,
                "session_id": session_id,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "outcomes": outcomes_data,
            }
            
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            logger.warning(f"[WorkOutcomeManager] Failed to save metadata: {e}")
    
    def ensure_workdir(self, agent_id: str, session_id: str) -> Path:
        """确保工作目录存在"""
        workdir = self._base_dir / session_id / "outcomes"
        workdir.mkdir(parents=True, exist_ok=True)
        
        metadata_path = workdir / "metadata.json"
        if not metadata_path.exists():
            metadata = {
                "agent_id": agent_id,
                "session_id": session_id,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "outcomes": [],
            }
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        return workdir


def get_outcome_manager() -> WorkOutcomeManager:
    return WorkOutcomeManager.get_instance()
```

- [ ] **Step 2: 在 `llm_chatter/utils/__init__.py` 中导出**

添加：
```python
from .work_outcome_manager import WorkOutcomeManager, WorkOutcome, get_outcome_manager
```

- [ ] **Step 3: 验证语法**

Run: `python -m py_compile llm_chatter/utils/work_outcome_manager.py`
Expected: 无输出（成功）

---

## 第五章：UI 集成

### Task 10: 实现标题栏角色选择器 RoleSelector

**Files:**
- Create: `llm_chatter/widgets/role_selector.py`
- Modify: `llm_chatter/main_widget.py` (添加角色选择器到标题栏)

- [ ] **Step 1: 创建 `llm_chatter/widgets/role_selector.py`**

```python
# -*- coding: utf-8 -*-
"""
RoleSelector - 标题栏角色选择器

在标题栏添加下拉框选择当前会话的角色身份
"""

from typing import List, Dict, Optional, Callable
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QComboBox, QLabel,
    QPushButton, QMenu, QAction, QStyledItemDelegate
)
from PyQt5.QtGui import QColor, QPalette
from qfluentwidgets import ComboBox, ToolButton, FluentIcon

from app.llm_chatter.core.agent_registry import get_agent_registry
from app.llm_chatter.core.role_config import get_role_config_manager


class RoleSelector(QWidget):
    """角色选择器组件"""
    
    roleChanged = pyqtSignal(str)  # 角色 ID 变化信号
    editRequested = pyqtSignal(str)  # 编辑请求信号
    
    # 默认颜色映射
    ROLE_COLORS = {
        "coordinator": "#4EC9B0",  # 青色
        "developer": "#569CD6",      # 蓝色
        "designer": "#DCDCAA",      # 黄色
        "tester": "#CE9178",         # 橙色
        "custom": "#888888",        # 灰色
    }
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_role_id = ""
        self._current_session_id = ""
        self._agent_registry = get_agent_registry()
        self._role_config_manager = get_role_config_manager()
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)
        
        # 角色标签
        self._role_label = QLabel("身份:", self)
        self._role_label.setStyleSheet("color: #aaaaaa; font-size: 12px;")
        layout.addWidget(self._role_label)
        
        # 角色下拉框
        self._combo = ComboBox(self)
        self._combo.setMinimumWidth(100)
        self._combo.currentTextChanged.connect(self._on_role_changed)
        layout.addWidget(self._combo)
        
        # 编辑按钮
        self._edit_btn = ToolButton(FluentIcon.EDIT, self)
        self._edit_btn.setFixedSize(26, 26)
        self._edit_btn.setToolTip("编辑角色")
        self._edit_btn.clicked.connect(self._on_edit_clicked)
        layout.addWidget(self._edit_btn)
        
        # 加载角色列表
        self._refresh_role_list()
    
    def _refresh_role_list(self):
        """刷新角色列表"""
        self._combo.blockSignals(True)
        self._combo.clear()
        
        # 添加预制角色
        preset_roles = self._role_config_manager.list_roles(
            include_preset=True, include_custom=False
        )
        for role in preset_roles:
            self._combo.addItem(role.name, role.id)
        
        # 添加分隔符后添加自定义角色
        custom_roles = self._role_config_manager.list_roles(
            include_preset=False, include_custom=True
        )
        if custom_roles:
            self._combo.insertSeparator(self._combo.count())
            for role in custom_roles:
                self._combo.addItem(role.name, role.id)
        
        self._combo.blockSignals(False)
    
    def _on_role_changed(self, text: str):
        """角色选择变化"""
        role_id = self._combo.currentData()
        if role_id and role_id != self._current_role_id:
            self._current_role_id = role_id
            self.roleChanged.emit(role_id)
            
            # 更新颜色
            color = self.ROLE_COLORS.get(role_id, "#888888")
            self._combo.setStyleSheet(f"""
                QComboBox {{
                    border: 1px solid {color}40;
                    border-radius: 4px;
                    padding: 2px 8px;
                    color: {color};
                }}
                QComboBox:hover {{
                    border: 1px solid {color};
                }}
            """)
    
    def _on_edit_clicked(self):
        """编辑按钮点击"""
        self.editRequested.emit(self._current_role_id)
    
    def set_current_role(self, role_id: str):
        """设置当前角色"""
        self._current_role_id = role_id
        index = self._combo.findData(role_id)
        if index >= 0:
            self._combo.blockSignals(True)
            self._combo.setCurrentIndex(index)
            self._combo.blockSignals(False)
            
            # 更新颜色
            color = self.ROLE_COLORS.get(role_id, "#888888")
            self._combo.setStyleSheet(f"""
                QComboBox {{
                    border: 1px solid {color}40;
                    border-radius: 4px;
                    padding: 2px 8px;
                    color: {color};
                }}
            """)
    
    def set_session_id(self, session_id: str):
        """设置会话 ID"""
        self._current_session_id = session_id
    
    def get_current_role(self) -> str:
        """获取当前角色 ID"""
        return self._combo.currentData() or ""
    
    def refresh(self):
        """刷新角色列表"""
        self._refresh_role_list()
```

- [ ] **Step 2: 修改 `llm_chatter/main_widget.py` 标题栏区域**

在 `setup_ui` 方法的 session_bar_layout 区域（约 540-583 行）添加角色选择器：

在标题标签后添加：
```python
# 添加角色选择器
from app.llm_chatter.widgets.role_selector import RoleSelector
self._role_selector = RoleSelector(self)
self._role_selector.roleChanged.connect(self._on_agent_role_changed)
left_layout.addWidget(self._role_selector)
```

添加处理方法：
```python
def _on_agent_role_changed(self, role_id: str):
    """角色变化时更新 agent 注册"""
    session_id = self._current_session_id
    if not session_id:
        return
    
    # 获取角色配置
    from app.llm_chatter.core.role_config import get_role_config_manager
    role_config_mgr = get_role_config_manager()
    role_config = role_config_mgr.get_role(role_id)
    
    if role_config:
        # 更新/注册 agent
        agent_reg = get_agent_registry()
        agent_reg.register(
            session_id=session_id,
            role_type=role_id,
            name=role_config.name,
            prompt=role_config.prompt,
            color=role_config.color,
        )
        
        # 更新当前 agent
        self._current_agent = role_id
        self._load_agent_tools()
```

- [ ] **Step 3: 验证语法**

Run: `python -m py_compile llm_chatter/widgets/role_selector.py`
Expected: 无输出（成功）

---

### Task 11: 实现角色编辑弹窗 RoleEditorDialog

**Files:**
- Create: `llm_chatter/widgets/role_editor_dialog.py`

- [ ] **Step 1: 创建 `llm_chatter/widgets/role_editor_dialog.py`**

```python
# -*- coding: utf-8 -*-
"""
RoleEditorDialog - 角色编辑弹窗

用于编辑和创建自定义角色
"""

from typing import Optional
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QTextEdit, QPushButton, QColorDialog,
    QDialog, QGroupBox, QFormLayout
)
from qfluentwidgets import (
    FluentWindow, PrimaryPushButton, PushButton,
    LineEdit, TextEdit, CardWidget
)

from app.llm_chatter.core.role_config import (
    RoleConfig, get_role_config_manager
)


class RoleEditorDialog(QDialog):
    """角色编辑弹窗"""
    
    roleSaved = pyqtSignal(str)  # 保存后的角色 ID
    
    def __init__(self, role_id: str = "", parent=None):
        super().__init__(parent)
        self._role_id = role_id
        self._role_config_manager = get_role_config_manager()
        self._original_role: Optional[RoleConfig] = None
        
        self._setup_ui()
        self._load_role()
    
    def _setup_ui(self):
        self.setWindowTitle("编辑角色")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        
        layout = QVBoxLayout(self)
        
        # 基本信息
        basic_group = QGroupBox("基本信息", self)
        basic_layout = QFormLayout(basic_group)
        
        self._id_edit = LineEdit(self)
        self._id_edit.setPlaceholderText("角色ID（英文，唯一）")
        basic_layout.addRow("ID:", self._id_edit)
        
        self._name_edit = LineEdit(self)
        self._name_edit.setPlaceholderText("显示名称")
        basic_layout.addRow("名称:", self._name_edit)
        
        self._color_btn = QPushButton("#888888", self)
        self._color_btn.setFixedWidth(80)
        self._color_btn.clicked.connect(self._on_color_clicked)
        basic_layout.addRow("颜色:", self._color_btn)
        
        layout.addWidget(basic_group)
        
        # 提示词
        prompt_group = QGroupBox("角色提示词", self)
        prompt_layout = QVBoxLayout(prompt_group)
        
        self._prompt_edit = TextEdit(self)
        self._prompt_edit.setPlaceholderText("输入角色的系统提示词...")
        self._prompt_edit.setMinimumHeight(200)
        prompt_layout.addWidget(self._prompt_edit)
        
        layout.addWidget(prompt_group)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self._cancel_btn = PushButton("取消", self)
        self._cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._cancel_btn)
        
        self._save_btn = PrimaryPushButton("保存", self)
        self._save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(self._save_btn)
        
        layout.addLayout(btn_layout)
    
    def _load_role(self):
        """加载角色配置"""
        if self._role_id:
            self._original_role = self._role_config_manager.get_role(self._role_id)
            if self._original_role:
                self._id_edit.setText(self._original_role.id)
                self._id_edit.setEnabled(False)  # ID 不可修改
                self._name_edit.setText(self._original_role.name)
                self._color_btn.setText(self._original_role.color)
                self._prompt_edit.setText(self._original_role.prompt)
                self.setWindowTitle(f"编辑角色 - {self._original_role.name}")
    
    def _on_color_clicked(self):
        """颜色选择"""
        from PyQt5.QtGui import QColor
        color = QColorDialog.getColor(
            QColor(self._color_btn.text()),
            self,
            "选择角色颜色"
        )
        if color.isValid():
            self._color_btn.setText(color.name())
    
    def _on_save(self):
        """保存角色"""
        role_id = self._id_edit.text().strip()
        name = self._name_edit.text().strip()
        color = self._color_btn.text()
        prompt = self._prompt_edit.toPlainText()
        
        if not role_id:
            self._id_edit.setFocus()
            return
        
        if not name:
            self._name_edit.setFocus()
            return
        
        # 确定角色类型
        role_type = "custom"
        preset_types = ["coordinator", "developer", "designer", "tester"]
        if role_id in preset_types:
            role_type = role_id
        
        # 创建/更新角色配置
        config = RoleConfig(
            id=role_id,
            name=name,
            role_type=role_type,
            prompt=prompt,
            color=color,
            is_preset=False,
        )
        
        if self._original_role:
            config.created_at = self._original_role.created_at
        
        if self._role_config_manager.save_custom_role(config):
            self.roleSaved.emit(role_id)
            self.accept()
        else:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "保存失败", "无法保存角色配置")

```

- [ ] **Step 2: 在 `llm_chatter/widgets/__init__.py` 中导出**

添加：
```python
from .role_editor_dialog import RoleEditorDialog
```

- [ ] **Step 3: 验证语法**

Run: `python -m py_compile llm_chatter/widgets/role_editor_dialog.py`
Expected: 无输出（成功）

---

### Task 12: 实现跨身份消息卡片样式

**Files:**
- Modify: `llm_chatter/widgets/message_card.py`

- [ ] **Step 1: 在 MessageCard 类中添加跨身份消息支持**

在 MessageCard 类中添加：

```python
class MessageCard(SimpleCardWidget):
    # ... 现有代码 ...
    
    # 跨身份消息颜色
    INTER_AGENT_BORDER_COLOR = "#569CD6"
    INTER_AGENT_BG_COLOR = "rgba(86, 156, 214, 0.1)"
    
    def set_inter_agent_message(self, from_agent: str, from_agent_name: str, color: str = None):
        """设置跨身份消息样式"""
        if color is None:
            color = self.INTER_AGENT_BORDER_COLOR
        
        # 更新边框样式
        self.setStyleSheet(f"""
            MessageCard {{
                border: 2px solid {color};
                border-radius: 8px;
                background-color: {self.INTER_AGENT_BG_COLOR};
            }}
        """)
        
        # 在标题栏添加来源信息
        # 需要找到标题区域并更新
        # ... 具体实现取决于现有 UI 结构
```

- [ ] **Step 2: 修改消息卡片创建逻辑**

在 `main_widget.py` 的消息创建逻辑中，判断是否来自其他智能体：

```python
def _append_message_card(self, role: str, content: str, **kwargs):
    """添加消息卡片"""
    # 检查是否跨身份消息
    from_agent = kwargs.get("from_agent", "")
    from_agent_name = kwargs.get("from_agent_name", "")
    source_color = kwargs.get("source_color", "")
    
    card = MessageCard(...)
    
    if from_agent and from_agent != self._current_agent:
        # 跨身份消息，使用特殊样式
        card.set_inter_agent_message(from_agent, from_agent_name, source_color)
    
    self._chat_layout.addWidget(card)
```

- [ ] **Step 3: 验证语法**

Run: `python -m py_compile llm_chatter/widgets/message_card.py`
Expected: 无输出（成功）

---

### Task 13: 修改窗口复制逻辑

**Files:**
- Modify: `llm_chatter/main_widget.py` (复制会话方法)

- [ ] **Step 1: 找到窗口复制方法**

在 `main_widget.py` 中找到 `_duplicate_session` 或类似的复制方法。

- [ ] **Step 2: 修改复制逻辑**

```python
def _duplicate_session(self):
    """复制会话窗口"""
    from app.llm_chatter.core.agent_registry import get_agent_registry
    
    # 获取当前会话和角色
    session = self.session_manager.get_current_session()
    current_agent = self._agent_registry.get_agent_by_session(session.session_id)
    
    # 创建新会话
    new_session = self.session_manager.create_new_session()
    
    # 如果有当前角色，复制角色并生成新 ID
    if current_agent:
        agent_reg = get_agent_registry()
        
        # 生成新 ID（自动递增）
        role_type = current_agent.role_type
        new_agent = agent_reg.register(
            session_id=new_session.session_id,
            role_type=role_type,
            name=current_agent.name + " (副本)",
            prompt=current_agent.prompt,
            color=current_agent.color,
        )
        
        # 创建工作目录
        from app.llm_chatter.utils.work_outcome_manager import get_outcome_manager
        outcome_mgr = get_outcome_manager()
        outcome_mgr.ensure_workdir(new_agent.id, new_session.session_id)
    
    # ... 其余复制逻辑
```

- [ ] **Step 3: 验证语法**

---

## 第六章：消息路由与注入

### Task 14: 实现消息队列自动投递

**Files:**
- Modify: `llm_chatter/main_widget.py` (消息检查和投递)

- [ ] **Step 1: 添加消息检查定时器**

在 `main_widget.py` 的 `__init__` 中添加：

```python
# 跨身份消息检查定时器
from PyQt5.QtCore import QTimer
self._inter_agent_check_timer = QTimer(self)
self._inter_agent_check_timer.timeout.connect(self._check_inter_agent_messages)
self._inter_agent_check_timer.start(5000)  # 每 5 秒检查一次
```

- [ ] **Step 2: 实现消息检查和投递**

```python
def _check_inter_agent_messages(self):
    """检查并投递跨身份消息"""
    if not self._window_active:
        return
    
    from app.llm_chatter.core.inter_agent_message import get_message_manager
    
    msg_manager = get_message_manager()
    
    # 获取当前会话的所有待处理消息
    pending = msg_manager.get_pending_messages(self._current_session_id)
    
    for msg in pending:
        # 自动投递到会话
        self._deliver_inter_agent_message(msg)
        
        # 更新状态为 delivered
        msg_manager.deliver_message(msg.id)
    
    if pending:
        self._refresh_chat_area()

def _deliver_inter_agent_message(self, message):
    """将跨身份消息投递到会话"""
    from app.llm_chatter.core.agent_registry import get_agent_registry
    
    agent_reg = get_agent_registry()
    from_agent = agent_reg.get_agent(message.from_agent)
    
    from_agent_name = from_agent.name if from_agent else message.from_agent
    from_color = from_agent.color if from_agent else "#888888"
    
    # 将消息作为用户消息添加到会话
    session = self.session_manager.get_current_session()
    session.add_user_message(
        content=message.content,
        from_agent=message.from_agent,
        from_agent_name=from_agent_name,
        source_color=from_color,
        need_callback=message.need_callback,
    )
    
    # 刷新显示
    self._refresh_chat_area()
    
    # 如果目标智能体空闲，自动处理
    if from_agent and from_agent.status == "idle":
        self._process_pending_messages()
```

- [ ] **Step 3: 在会话切换时检查消息**

在 `_switch_to_session` 方法中添加消息检查。

---

### Task 15: 实现消息队列手动触发

**Files:**
- Modify: `llm_chatter/main_widget.py` (用户手动触发消息处理)

- [ ] **Step 1: 添加手动处理按钮**

在 UI 中添加"处理消息"按钮，点击时触发 `_process_pending_messages`。

- [ ] **Step 2: 实现手动处理**

```python
def _process_pending_messages(self):
    """手动处理待处理消息"""
    from app.llm_chatter.core.inter_agent_message import get_message_manager
    
    msg_manager = get_message_manager()
    
    while True:
        msg = msg_manager.pop_message(self._current_session_id)
        if not msg:
            break
        
        # 将消息转为对话输入
        self.input_area.setText(f"[来自 {msg.from_agent}]: {msg.content}")
        # 用户可以发送或取消
```

---

### Task 16: 实现身份列表自动注入

**Files:**
- Modify: `llm_chatter/core/chat_engine.py` (system prompt 注入)
- Modify: `llm_chatter/tools/inter_agent_tools.py` (工具注册)

- [ ] **Step 1: 添加身份列表注入方法**

在 `ChatEngine` 类中添加：

```python
def _build_agent_context_injection(self) -> str:
    """构建身份列表注入内容"""
    from app.llm_chatter.core.agent_registry import get_agent_registry
    
    agent_reg = get_agent_registry()
    agents = agent_reg.list_all_agents_with_status()
    
    if not agents:
        return ""
    
    lines = ["## 团队成员", "以下是你当前团队的所有成员及其状态：", ""]
    
    for idx, agent in enumerate(agents, 1):
        status_icon = "🟢" if agent["status"] == "idle" else "🟡" if agent["status"] == "busy" else "✅"
        lines.append(f"{idx}. {status_icon} **{agent['name']}**")
        lines.append(f"   - ID: {agent['id']}")
        lines.append(f"   - 状态: {agent['status']}")
        
        if agent["status"] == "busy" and agent.get("progress"):
            lines.append(f"   - 进度: {agent['progress']}%")
            if agent.get("task"):
                lines.append(f"   - 任务: {agent['task']}")
        lines.append("")
    
    return "\n".join(lines)
```

- [ ] **Step 2: 在构建消息时注入**

在 `ChatEngine._build_messages` 方法中，在 system prompt 末尾添加身份列表。

- [ ] **Step 3: 注册协作工具到工具系统**

在 `ChatEngine` 初始化时，添加协作工具：

```python
# 注册协作工具
from app.llm_chatter.tools.inter_agent_tools import get_tools_schema, get_inter_agent_tools

def _get_current_agent_id(self) -> str:
    """获取当前 agent ID"""
    agent_reg = get_agent_registry()
    agent = agent_reg.get_agent_by_session(self._session_manager.get_current_session().session_id)
    return agent.id if agent else ""

# 在 send_message 时获取工具结果
def _get_inter_agent_tools_result(self, tool_name: str, arguments: dict):
    """处理协作工具调用"""
    session = self._session_manager.get_current_session()
    agent_id = self._get_current_agent_id()
    
    tools = get_inter_agent_tools(session.session_id, agent_id)
    
    if tool_name == "send_to_agent":
        return tools.send_to_agent(**arguments)
    elif tool_name == "broadcast_to_agents":
        return tools.broadcast_to_agents(**arguments)
    elif tool_name == "list_agents":
        return tools.list_agents()
    elif tool_name == "get_work_outcomes":
        return tools.get_work_outcomes(**arguments)
    
    return ToolResult(False, f"Unknown tool: {tool_name}")
```

- [ ] **Step 4: 验证语法**

Run: `python -m py_compile llm_chatter/core/chat_engine.py`
Expected: 无输出（成功）

---

## 实施计划总结

### 任务依赖关系

```
Task 1 (AgentRegistry) ──┬──► Task 2 (InterAgentMessage)
                        │
                        └──► Task 3 (WorkOutcomeManager)

Task 4-5 (角色配置) ─────┬──► Task 6 (InterAgentTools)
                        │
                        └──► Task 16 (消息注入)

Task 10-13 (UI) ─────────┬──► 需要先完成核心基础设施
                        │
                        └───► Task 14-15 (消息路由)
```

### 快速启动顺序

1. **第一批（核心）**: Task 1 → Task 2 → Task 3
2. **第二批（角色）**: Task 4 → Task 5 → Task 6
3. **第三批（UI）**: Task 10 → Task 11 → Task 12 → Task 13
4. **第四批（路由）**: Task 14 → Task 15 → Task 16

### 验证检查点

| 检查点 | 验证方式 |
|-------|---------|
| AgentRegistry | `get_agent_registry().register(...)` 能正常注册 |
| 消息发送 | `send_to_agent("developer", "test")` 能返回成功 |
| 角色选择 | UI 下拉框能选择并切换角色 |
| 消息投递 | 消息能正确显示在目标会话中 |
| 身份注入 | system prompt 包含团队成员列表 |

### 已知约束

1. 所有协作工具需要通过现有的工具系统注册
2. 消息持久化使用 JSON 文件，暂不依赖 SQLite
3. UI 修改需要与现有会话管理逻辑兼容
4. 工作目录创建需要确保 `canvas_files/agents/` 目录存在

---

**计划完成**

实施计划已全部写入 `docs/superpowers/plans/2025-01-09-multi-agent-implementation-plan.md`

---

**执行选项：**

1. **Subagent-Driven (推荐)** - 使用 `superpowers:subagent-driven-development` 逐任务执行
2. **Inline Execution** - 使用 `superpowers:executing-plans` 批量执行

你希望使用哪种执行方式？