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
from typing import Dict, List, Optional
from pathlib import Path
import json

from loguru import logger


@dataclass
class AgentInfo:
    """智能体信息"""
    id: str  # 唯一标识，如 "developer_1"
    name: str  # 显示名称，如 "开发者1"
    session_id: str  # 绑定的会话ID
    role_type: str  # 角色类型：coordinator, developer, designer, tester, custom
    prompt: str  # 角色提示词
    color: str  # 颜色，如 "#4EC9B0"
    status: str = "idle"  # idle / busy / done
    progress: int = 0  # 进度 0-100
    task: str = ""  # 当前任务描述
    workdir: str = ""  # 工作产物目录
    created_at: str = ""  # 创建时间

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

            # 创建工作目录
            self._ensure_workdir(agent.workdir)

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

    def _ensure_workdir(self, workdir: str) -> None:
        """确保工作目录存在"""
        try:
            Path(workdir).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"[AgentRegistry] Failed to create workdir {workdir}: {e}")

    def reset(self):
        """重置注册表（用于测试）"""
        with self._lock:
            self._agents.clear()
            self._session_to_agent.clear()
            self._type_counters.clear()


def get_agent_registry() -> AgentRegistry:
    """获取全局 AgentRegistry 实例"""
    return AgentRegistry.get_instance()
