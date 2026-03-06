# -*- coding: utf-8 -*-
"""
智能体模块 - 定义和管理智能体
类似 Claude Code 的 agent 定义方式
"""

import os
import json
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from loguru import logger


def get_available_skills() -> List[Dict]:
    """获取所有可用技能列表"""
    skills_dir = Path(__file__).parent.parent / "skills"
    if not skills_dir.exists():
        return []

    results = []
    for skill_dir in skills_dir.iterdir():
        if not skill_dir.is_dir():
            continue
        if skill_dir.name.startswith("_") or skill_dir.name.startswith("."):
            continue

        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            skill_file = skill_dir / "skill.md"
        if not skill_file.exists():
            skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue

        try:
            content = skill_file.read_text(encoding="utf-8")
            name = skill_dir.name
            description = ""

            if content.startswith("---"):
                try:
                    frontmatter, _ = content.split("---", 2)[1].split("---", 1)
                    meta = yaml.safe_load(frontmatter)
                    if meta:
                        name = meta.get("name", skill_dir.name)
                        description = meta.get("description", "")
                except Exception:
                    pass

            results.append({"name": name, "description": description})
        except Exception:
            continue

    return results


@dataclass
class Agent:
    """智能体定义"""

    name: str
    description: str
    tools: List[str] = field(default_factory=list)
    model: Optional[str] = None
    system_prompt: str = ""

    @classmethod
    def from_dict(cls, data: Dict) -> "Agent":
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            tools=data.get("tools", []),
            model=data.get("model"),
            system_prompt=data.get("system_prompt", ""),
        )

    def to_dict(self) -> Dict:
        result = {
            "name": self.name,
            "description": self.description,
            "tools": self.tools,
        }
        if self.model:
            result["model"] = self.model
        if self.system_prompt:
            result["system_prompt"] = self.system_prompt
        return result


class AgentManager:
    """智能体管理器 - 加载和管理智能体定义"""

    DEFAULT_TOOLS = ["Read", "Grep", "Glob", "Bash", "write", "edit"]

    def __init__(self, agents_dir: str = None):
        if agents_dir:
            self.agents_dir = Path(agents_dir)
        else:
            self.agents_dir = Path(__file__).parent.parent / "agents"

        self.sub_agents_dir = Path(__file__).parent.parent / "sub_agents"

        self._agents: Dict[str, Agent] = {}
        self._sub_agents: Dict[str, Agent] = {}
        self._load_agents()
        self._load_sub_agents()

    def _load_agents(self):
        """从 agents 目录加载所有智能体定义"""
        if not self.agents_dir.exists():
            logger.warning(
                f"[AgentManager] Agents directory not found: {self.agents_dir}"
            )
            return

        for yaml_file in self.agents_dir.glob("*.yaml"):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data:
                        agent = Agent.from_dict(data)
                        self._agents[agent.name] = agent
                        logger.info(f"[AgentManager] Loaded agent: {agent.name}")
            except Exception as e:
                logger.error(f"[AgentManager] Failed to load {yaml_file}: {e}")

    def _load_sub_agents(self):
        """从 sub_agents 目录加载子智能体定义"""
        if not self.sub_agents_dir.exists():
            logger.info(
                f"[AgentManager] Sub-agents directory not found: {self.sub_agents_dir}"
            )
            return

        for yaml_file in self.sub_agents_dir.glob("*.yaml"):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data:
                        agent = Agent.from_dict(data)
                        self._sub_agents[agent.name] = agent
                        logger.info(f"[AgentManager] Loaded sub-agent: {agent.name}")
            except Exception as e:
                logger.error(f"[AgentManager] Failed to load {yaml_file}: {e}")

    def get_agent(self, name: str) -> Optional[Agent]:
        """获取智能体（包括主智能体和子智能体）"""
        return self._agents.get(name) or self._sub_agents.get(name)

    def get_sub_agent(self, name: str) -> Optional[Agent]:
        """获取子智能体"""
        return self._sub_agents.get(name)

    def list_agents(self) -> List[Agent]:
        """列出所有智能体"""
        return list(self._agents.values())

    def list_sub_agents(self) -> List[Agent]:
        """列出所有子智能体"""
        return list(self._sub_agents.values())

    def get_agent_tools_schema(self, agent_name: str) -> List[Dict]:
        """获取智能体的工具 schema"""
        agent = self.get_agent(agent_name)
        if not agent:
            return []

        from app.widgets.side_dock_area.plugins.llm_chatter.utils.builtin_tools import (
            get_builtin_tools_schema,
        )

        all_tools = get_builtin_tools_schema()
        if not agent.tools:
            return all_tools

        tool_names_lower = [t.lower() for t in agent.tools]
        return [
            tool
            for tool in all_tools
            if tool["function"]["name"].lower() in tool_names_lower
        ]

    def get_agent_system_prompt(self, agent_name: str, base_prompt: str = "") -> str:
        """获取智能体的系统提示，自动加载相关技能"""
        agent = self.get_agent(agent_name)
        if not agent:
            return base_prompt

        if agent.system_prompt:
            return agent.system_prompt

        return f"""# {agent.name}
{agent.description}

## 可用工具
你只能使用以下工具：{", ".join(agent.tools)}

## 重要规则
- 当需要了解用户偏好、需求或让用户做选择时，**必须**使用 `question` 工具提问，不要自行生成问卷或列表
- 直接执行，不要询问用户确认。如果需要用户确认，使用 question 工具提问。
- **大型项目开发规范**: 开发大型项目时，先使用 `todoread` 工具查看已有的待办事项。如果已有待办事项，直接接着进度开发，不要重复创建。如果需要创建新的待办事项，使用 `todowrite` 工具。
- **技能查询**: 当遇到不熟悉的任务领域时（如生成PPT、PDF处理、文档编辑、设计等），使用 `list_skills` 工具查找是否有相关技能，如果有，使用 `skill` 工具加载该技能的专业经验。技能文档中可能包含特定的工作目录（workspace）要求，请在对应的目录下执行相关操作。如果没有找到合适的技能，使用 `skill` 工具加载 `find-skills` 技能来搜索外部技能市场（skills.sh）。

{base_prompt}"""


def create_agent_manager(agents_dir: str = None) -> AgentManager:
    """创建智能体管理器"""
    return AgentManager(agents_dir)
