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
    id: str  # 产物ID
    agent_id: str  # 所属智能体ID
    agent_name: str  # 所属智能体名称
    name: str  # 产物名称
    filename: str  # 文件名
    path: str  # 文件路径
    type: str  # file / directory
    size: int = 0  # 文件大小
    created_at: str = ""  # 创建时间
    description: str = ""  # 产物描述

    def to_dict(self) -> Dict:
        return asdict(self)


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
                results.append(outcome.to_dict())
        return results

    def get_all_outcomes(self) -> List[Dict]:
        """获取所有产物"""
        return [o.to_dict() for o in self._outcomes]

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

    def ensure_workdir(self, agent_id: str, session_id: str = None) -> Path:
        """确保工作目录存在"""
        if not session_id:
            # 尝试从 agent 获取 session_id
            try:
                from app.llm_chatter.core.agent_registry import get_agent_registry
                registry = get_agent_registry()
                agent = registry.get_agent(agent_id)
                if agent:
                    session_id = agent.session_id
            except Exception:
                pass

        if not session_id:
            logger.warning(f"[WorkOutcomeManager] Cannot determine session_id for {agent_id}")
            return self._base_dir

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

    def _get_session_id_from_path(self, file_path: str) -> Optional[str]:
        """从文件路径提取 session_id"""
        parts = Path(file_path).parts
        if "agents" in parts:
            idx = list(parts).index("agents")
            if idx + 1 < len(parts):
                return parts[idx + 1]
        return None

    def _save_metadata(self, agent_id: str) -> None:
        """保存 metadata.json"""
        try:
            # 找到 agent 对应的 session_id
            session_id = None
            for outcome in self._outcomes:
                if outcome.agent_id == agent_id:
                    session_id = self._get_session_id_from_path(outcome.path)
                    if session_id:
                        break

            if not session_id:
                # 尝试从 agent_registry 获取
                try:
                    from app.llm_chatter.core.agent_registry import get_agent_registry
                    registry = get_agent_registry()
                    agent = registry.get_agent(agent_id)
                    if agent:
                        session_id = agent.session_id
                except Exception:
                    pass

            if not session_id:
                logger.warning(f"[WorkOutcomeManager] Cannot find session_id for {agent_id}")
                return

            metadata_path = self._base_dir / session_id / "outcomes" / "metadata.json"
            metadata_path.parent.mkdir(parents=True, exist_ok=True)

            outcome_ids = self._agent_outcomes.get(agent_id, [])
            outcomes_data = []
            for outcome in self._outcomes:
                if outcome.id in outcome_ids:
                    outcomes_data.append(outcome.to_dict())

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

    def reset(self):
        """重置管理器（用于测试）"""
        with self._lock:
            self._outcomes.clear()
            self._agent_outcomes.clear()


def get_outcome_manager() -> WorkOutcomeManager:
    """获取全局工作产物管理器"""
    return WorkOutcomeManager.get_instance()
