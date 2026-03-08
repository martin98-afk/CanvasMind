# -*- coding: utf-8 -*-
"""
智能体模块 - 定义和管理 llm_chatter 的 agent 配置。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from loguru import logger


def get_available_skills() -> List[Dict]:
    """获取内置 skills 列表。"""
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
            continue

        try:
            content = skill_file.read_text(encoding="utf-8")
        except Exception:
            continue

        name = skill_dir.name
        description = ""
        if content.startswith("---"):
            try:
                frontmatter = content.split("---", 2)[1]
                meta = yaml.safe_load(frontmatter)
                if meta:
                    name = meta.get("name", name)
                    description = meta.get("description", "")
            except Exception:
                pass

        results.append({"name": name, "description": description})

    return results


@dataclass
class Agent:
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
    DEFAULT_TOOLS = ["Read", "Grep", "Glob", "Bash", "write", "edit"]

    def __init__(self, agents_dir: str = None):
        self.agents_dir = (
            Path(agents_dir) if agents_dir else Path(__file__).parent.parent / "agents"
        )
        self.sub_agents_dir = Path(__file__).parent.parent / "sub_agents"
        self._agents: Dict[str, Agent] = {}
        self._sub_agents: Dict[str, Agent] = {}
        self._load_agents()
        self._load_sub_agents()

    def _load_agents(self):
        if not self.agents_dir.exists():
            logger.warning(f"[AgentManager] Agents directory not found: {self.agents_dir}")
            return

        for yaml_file in self.agents_dir.glob("*.yaml"):
            try:
                data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                if data:
                    agent = Agent.from_dict(data)
                    self._agents[agent.name] = agent
                    logger.info(f"[AgentManager] Loaded agent: {agent.name}")
            except Exception as e:
                logger.error(f"[AgentManager] Failed to load {yaml_file}: {e}")

    def _load_sub_agents(self):
        if not self.sub_agents_dir.exists():
            logger.info(
                f"[AgentManager] Sub-agents directory not found: {self.sub_agents_dir}"
            )
            return

        for yaml_file in self.sub_agents_dir.glob("*.yaml"):
            try:
                data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                if data:
                    agent = Agent.from_dict(data)
                    self._sub_agents[agent.name] = agent
                    logger.info(f"[AgentManager] Loaded sub-agent: {agent.name}")
            except Exception as e:
                logger.error(f"[AgentManager] Failed to load {yaml_file}: {e}")

    def get_agent(self, name: str) -> Optional[Agent]:
        return self._agents.get(name) or self._sub_agents.get(name)

    def get_sub_agent(self, name: str) -> Optional[Agent]:
        return self._sub_agents.get(name)

    def list_agents(self) -> List[Agent]:
        return list(self._agents.values())

    def list_sub_agents(self) -> List[Agent]:
        return list(self._sub_agents.values())

    def get_agent_tools_schema(self, agent_name: str) -> List[Dict]:
        agent = self.get_agent(agent_name)
        if not agent:
            return []

        from app.widgets.side_dock_area.plugins.llm_chatter.utils.builtin_tools import (
            get_builtin_tools_schema,
        )

        all_tools = get_builtin_tools_schema()
        if not agent.tools:
            return all_tools

        tool_names_lower = [tool.lower() for tool in agent.tools]
        return [
            tool
            for tool in all_tools
            if tool["function"]["name"].lower() in tool_names_lower
        ]

    def get_agent_system_prompt(self, agent_name: str, base_prompt: str = "") -> str:
        agent = self.get_agent(agent_name)
        if not agent:
            return base_prompt

        global_contract = """
## Global Coding Contract
- 这是一个代码工作台，不是普通闲聊窗口。
- 优先围绕“相关文件、实施动作、验证方式、剩余风险”组织输出。
- 如果信息不够，不要猜，使用 `question`。
- 如果已经有 todo，优先沿用现有执行上下文。
- 回答要像工程师交付，不要像客服聊天。
""".strip()

        if agent.system_prompt:
            return "\n\n".join(
                part for part in [agent.system_prompt, global_contract, base_prompt] if part
            )

        fallback_prompt = f"""# {agent.name}
{agent.description}

## Available Tools
You may only use: {", ".join(agent.tools)}

{global_contract}
"""
        return "\n\n".join(part for part in [fallback_prompt, base_prompt] if part)


def create_agent_manager(agents_dir: str = None) -> AgentManager:
    return AgentManager(agents_dir)
