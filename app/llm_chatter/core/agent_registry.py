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
    id: str = ""  # 唯一标识，如 "coordinator_a1b2c3d4"
    name: str = ""  # 显示名称，如 "统筹者"
    role_type: str = ""  # 角色类型：coordinator, developer, designer, tester
    prompt: str = ""  # 角色提示词
    color: str = "#888888"  # 颜色
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
        agent_id: str,
        role_type: str = "",
        name: str = "",
        prompt: str = "",
        color: str = "#888888",
        workdir: str = "",
    ) -> AgentInfo:
        """注册一个新身份（agent_id 必须唯一且由调用方提供）"""
        with self._lock:
            # 如果已存在同名 agent，先注销
            if agent_id in self._agents:
                self._agents.pop(agent_id, None)

            # 创建 AgentInfo
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            agent = AgentInfo(
                id=agent_id,
                name=name or agent_id,
                role_type=role_type,
                prompt=prompt,
                color=color,
                status="idle",
                progress=0,
                task="",
                workdir=workdir,
                created_at=now,
            )

            self._agents[agent_id] = agent

            # 创建工作目录
            if workdir:
                self._ensure_workdir(workdir)

            logger.info(f"[AgentRegistry] Registered: {agent_id}")
            return agent

    def unregister(self, agent_id: str) -> bool:
        """注销身份"""
        with self._lock:
            if agent_id in self._agents:
                self._agents.pop(agent_id, None)
                logger.info(f"[AgentRegistry] Unregistered: {agent_id}")
                return True
            return False

    def get_agent(self, agent_id: str) -> Optional[AgentInfo]:
        """根据 ID 获取智能体"""
        return self._agents.get(agent_id)

    def list_agents(self, role_type: Optional[str] = None) -> List[AgentInfo]:
        """列出所有智能体，可按角色类型过滤"""
        with self._lock:
            agents = list(self._agents.values())
            if role_type:
                agents = [a for a in agents if a.role_type == role_type]
            return agents

    def list_all_agents_with_status(self) -> List[Dict]:
        """列出所有智能体及其状态"""
        agents = self.list_agents()
        return [
            {
                "id": agent.id,
                "name": agent.name,
                "status": agent.status,
                "role_type": agent.role_type,
            }
            for agent in agents
        ]

    def update_status(
        self,
        agent_id: str,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        task: Optional[str] = None,
    ) -> bool:
        """更新智能体状态"""
        agent = self.get_agent(agent_id)
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
        """查找空闲的同类型智能体"""
        with self._lock:
            idle_agents = [
                a for a in self._agents.values()
                if a.role_type == role_type and a.status == "idle"
            ]
            return idle_agents[0] if idle_agents else None

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
