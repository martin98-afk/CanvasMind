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
    id: str  # 角色 ID
    name: str  # 显示名称
    role_type: str  # 角色类型：coordinator, developer, designer, tester, custom
    prompt: str  # 提示词
    color: str  # 颜色
    is_preset: bool = True  # 是否预制角色
    created_at: str = ""  # 创建时间
    updated_at: str = ""  # 更新时间

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
        if not self._custom_roles_dir.exists():
            return

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
        """保存自定义角色或更新预制角色"""
        try:
            # 如果是预制角色，只更新提示词等，不改变预制属性
            original = self._roles.get(config.id)
            if original and original.is_preset:
                # 预制角色只允许修改 name, prompt, color
                config.is_preset = True
                config.created_at = original.created_at
            else:
                config.is_preset = False
                if not config.created_at:
                    config.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            config.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            self._roles[config.id] = config

            # 保存到文件（预制角色保存到预制目录，自定义角色保存到自定义目录）
            if config.is_preset:
                # 预制角色保存到 agents 目录
                preset_file = Path(__file__).parent.parent / "agents" / f"{config.id}.md"
                self._save_role_to_markdown(preset_file, config)
                logger.info(f"[RoleConfig] Updated preset role: {config.id}")
            else:
                # 自定义角色保存到 JSON 文件
                json_file = self._custom_roles_dir / f"{config.id}.json"
                with open(json_file, "w", encoding="utf-8") as f:
                    json.dump(config.to_dict(), f, ensure_ascii=False, indent=2)
                logger.info(f"[RoleConfig] Saved custom role: {config.id}")
            return True
        except Exception as e:
            logger.error(f"[RoleConfig] Failed to save {config.id}: {e}")
            return False

    def _save_role_to_markdown(self, file_path: Path, config: RoleConfig) -> None:
        """将角色配置保存为 Markdown 格式"""
        meta = {
            "name": config.name,
            "description": config.name,
            "mode": "primary",
            "color": config.color,
        }
        meta_yaml = "\n".join(f"{k}: {v}" for k, v in meta.items())
        content = f"---\n{meta_yaml}\n---\n\n{config.prompt}"
        file_path.write_text(content, encoding="utf-8")

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

    def get_role_list_for_ui(self) -> List[Dict]:
        """获取角色列表（用于 UI 下拉框）"""
        roles = self.list_roles()
        return [
            {
                "id": role.id,
                "name": role.name,
                "role_type": role.role_type,
                "color": role.color,
                "is_preset": role.is_preset,
            }
            for role in roles
        ]


def get_role_config_manager() -> RoleConfigManager:
    """获取全局角色配置管理器"""
    return RoleConfigManager.get_instance()
