# -*- coding: utf-8 -*-
"""
智能体模块 - 定义和管理智能体
类似 Claude Code 的 agent 定义方式
"""

import os
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from loguru import logger


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

        self._agents: Dict[str, Agent] = {}
        self._load_agents()

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

    def get_agent(self, name: str) -> Optional[Agent]:
        """获取智能体"""
        return self._agents.get(name)

    def list_agents(self) -> List[Agent]:
        """列出所有智能体"""
        return list(self._agents.values())

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
        """获取智能体的系统提示"""
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

{base_prompt}"""

    def get_unified_system_prompt(self) -> str:
        """获取统一的系统提示，让大模型自行选择智能体"""
        from app.widgets.side_dock_area.plugins.llm_chatter.utils.builtin_tools import (
            get_builtin_tools_schema,
        )

        all_agents = self.list_agents()
        if not all_agents:
            return ""

        agent_descriptions = []
        for agent in all_agents:
            desc = f"""### {agent.name}
- 描述: {agent.description}
- 工具: {", ".join(agent.tools) if agent.tools else "所有内置工具"}
"""
            agent_descriptions.append(desc)

        all_tools = get_builtin_tools_schema()
        tool_list = "\n".join(
            [
                f"- **{t['function']['name']}**: {t['function']['description']}"
                for t in all_tools
            ]
        )

        return f"""# 智能体选择

你是一个多智能体协作系统。根据用户任务的不同，你可以选择合适的智能体来执行任务。

## 可用智能体

{chr(10).join(agent_descriptions)}
## 内置工具（所有智能体共享）

{tool_list}

## 使用规则

1. 分析用户需求，判断是否需要切换智能体
2. 如果当前任务与当前智能体匹配，继续执行
3. 如果需要使用特定智能体，在回复中说明要切换的智能体名称，格式：`[切换智能体: {{智能体名称}}]`
4. 切换后，新智能体将使用其专用的工具集和提示词

## 工具调用格式

当需要执行工具时，使用以下格式：
```builtin_tool_call
{{"name": "工具名", "args": {{"参数1": "值1", ...}}}}
```

## 重要规则
- 当需要了解用户偏好、需求或让用户做选择时，**必须**使用 `question` 工具提问，不要自行生成问卷或列表选项
- **大型项目开发规范**: 开发大型项目时，先使用 `todoread` 工具查看已有的待办事项。如果已有待办事项，直接接着进度开发，不要重复创建。如果需要创建新的待办事项，使用 `todowrite` 工具。

## 追问与行动规范
- 当你预测到用户接下来可能需要的帮助时，请按以下格式给出追问清单（放在回复末尾）：
- [问题描述](ask)
- **重要**: 当需要了解用户偏好、需求或让用户做选择时，**必须**使用 `question` 工具提问，不要自行生成问卷或列表选项
- 直接执行，不要询问用户确认。如果需要用户确认，使用 question 工具提问。
"""


def create_agent_manager(agents_dir: str = None) -> AgentManager:
    """创建智能体管理器"""
    return AgentManager(agents_dir)
