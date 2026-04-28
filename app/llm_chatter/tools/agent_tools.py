# -*- coding: utf-8 -*-
"""
协作工具 - 多智能体协作系统

提供以下工具：
- send_to_agent: 发送消息给指定身份
- broadcast_to_agents: 广播消息给多个身份
- list_agents: 查询团队成员状态
- get_work_outcomes: 获取工作产物
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

# 直接导入核心模块，避免通过 core/__init__.py 触发循环依赖
from app.llm_chatter.core.agent_registry import AgentRegistry, get_agent_registry
from app.llm_chatter.core.inter_agent_message import (
    InterAgentMessage,
    InterAgentMessageManager,
    get_message_manager,
)
from app.llm_chatter.tools.result import ToolResult


class AgentTools:
    """协作工具类"""

    def __init__(self, session_id: str, agent_id: str):
        self.session_id = session_id
        self.agent_id = agent_id
        self._registry = get_agent_registry()
        self._msg_manager = get_message_manager()

    def send_to_agent(
        self,
        agent: str,
        message: str,
        need_callback: bool = False,
    ) -> ToolResult:
        """
        发送消息给指定身份。

        发送完成后即可结束任务，无需等待对方回复（除非 need_callback=true）。
        """
        # 检查是否选择了身份
        if not self.agent_id:
            return ToolResult(False, error="当前未选择身份，无法使用协作功能。请先在标题栏选择身份。")

        # 处理 agent ID（可能传的是 agent_id 或 role_type）
        target_agent = self._resolve_agent(agent)
        if not target_agent:
            return ToolResult(False, error=f"未找到目标身份: {agent}，请先通过 list_agents() 查看可用身份")

        # 检查是否发给自己
        if target_agent.id == self.agent_id:
            return ToolResult(False, error="不能给自己发送消息")

        # 发送消息
        inter_msg = self._msg_manager.send_message(
            from_agent=self.agent_id,
            from_session=self.session_id,
            to_agent=target_agent.id,
            content=message,
            need_callback=need_callback,
        )

        # 更新发送者状态为忙碌（如果需要回调）
        if need_callback:
            self._registry.update_status(
                self.session_id,
                status="busy",
                task=f"等待 {target_agent.name} 回调"
            )

        logger.info(
            f"[AgentTools] send_to_agent: {self.agent_id} -> {target_agent.id}, "
            f"need_callback={need_callback}, msg_id={inter_msg.id}"
        )

        return ToolResult(
            True,
            content=f"成功发送消息给 '{agent}'。\n"
            f"消息ID: {inter_msg.id}\n"
            f"目标智能体将在空闲时处理。"
        )

    def broadcast_to_agents(
        self,
        agents: Optional[List[str]] = None,
        message: str = "",
    ) -> ToolResult:
        """
        广播消息给多个团队成员。

        agents: 目标身份ID列表，null 或空数组表示发给所有成员
        """
        if not message:
            return ToolResult(False, error="消息内容不能为空")

        # 获取所有智能体或指定的
        if agents:
            target_agents = []
            for agent_id in agents:
                resolved = self._resolve_agent(agent_id)
                if resolved:
                    target_agents.append(resolved)
                else:
                    logger.warning(f"[AgentTools] 未找到广播目标: {agent_id}")
        else:
            target_agents = [
                a for a in self._registry.list_agents()
                if a.id != self.agent_id
            ]

        if not target_agents:
            return ToolResult(False, error="没有可接收广播的团队成员")

        # 广播消息
        count = 0
        for target in target_agents:
            self._msg_manager.send_message(
                from_agent=self.agent_id,
                from_session=self.session_id,
                to_agent=target.id,
                content=message,
                need_callback=False,
            )
            count += 1

        logger.info(f"[AgentTools] broadcast_to_agents: 发送给 {count} 个成员")

        return ToolResult(
            True,
            content=f"成功广播消息给 {count} 个团队成员。"
        )

    def list_agents(self) -> ToolResult:
        """
        查询团队成员及其状态。

        用于了解谁空闲、谁忙碌，以便智能分配任务。
        """
        # 检查是否选择了身份
        if not self.agent_id:
            return ToolResult(
                False,
                error="当前未选择身份，无法使用协作功能。请先在标题栏选择身份。"
            )

        agents_data = self._registry.list_all_agents_with_status()

        if not agents_data:
            return ToolResult(
                True,
                content="当前没有团队成员。"
            )

        # 格式化输出（直接返回字符串）
        lines = ["## 团队成员\n"]
        for agent in agents_data:
            emoji = self._get_role_emoji(agent.get("id", ""))
            name = agent.get("name", agent.get("id", ""))
            status = agent.get("status", "unknown")
            status_text = {
                "idle": "空闲",
                "busy": "忙碌",
                "done": "完成"
            }.get(status, status)

            line = f"{emoji} **{name}** ({agent.get('id', '')})"
            if status == "busy":
                progress = agent.get("progress", 0)
                task = agent.get("task", "")
                line += f"\n   状态: {status_text}"
                if task:
                    line += f", 任务: {task}"
                if progress:
                    line += f", 进度: {progress}%"
            else:
                line += f"\n   状态: {status_text}"
            lines.append(line)

        return ToolResult(
            True,
            content="\n".join(lines),
        )

    def get_work_outcomes(self, agent_id: Optional[str] = None) -> ToolResult:
        """
        获取工作产物列表。

        agent_id: 智能体ID，如果为空则返回所有产物
        """
        outcomes = self._collect_outcomes(agent_id)

        if not outcomes:
            return ToolResult(
                True,
                content={
                    "outcomes": [],
                    "formatted": "当前没有工作产物。"
                }
            )

        # 格式化输出
        lines = ["## 工作产物\n"]
        for outcome in outcomes:
            lines.append(f"- **{outcome['name']}** ({outcome['type']})")
            lines.append(f"  - 智能体: {outcome['agent_name']}")
            lines.append(f"  - 路径: {outcome['path']}")
            if outcome.get("description"):
                lines.append(f"  - 描述: {outcome['description']}")
            lines.append("")

        formatted = "\n".join(lines)

        return ToolResult(
            True,
            content={
                "outcomes": outcomes,
                "formatted": formatted,
            }
        )

    def _resolve_agent(self, identifier: str) -> Optional[Dict]:
        """解析 agent 标识符（可能是 ID 或 role_type）"""
        # 直接按 ID 查找
        agent = self._registry.get_agent(identifier)
        if agent:
            return agent

        # 按 role_type 查找空闲的
        idle_agent = self._registry.find_idle_agent(identifier)
        if idle_agent:
            return idle_agent

        # 列出所有，找匹配的 name
        for agent in self._registry.list_agents():
            if agent.name == identifier or agent.id == identifier:
                return agent

        return None

    def _get_role_emoji(self, agent_id: str) -> str:
        """获取角色对应的 emoji"""
        emoji_map = {
            "coordinator": "🏛️",
            "developer": "👨‍💻",
            "designer": "🎨",
            "tester": "🔍",
        }
        # 提取 base role
        base_role = agent_id.split("_")[0] if "_" in agent_id else agent_id
        return emoji_map.get(base_role, "🤖")

    def _collect_outcomes(self, agent_id: Optional[str] = None) -> List[Dict]:
        """收集工作产物"""
        outcomes = []

        # 确定要查询哪些智能体
        if agent_id:
            agents = [self._registry.get_agent(agent_id)]
        else:
            agents = self._registry.list_agents()

        # 收集每个智能体的产物
        for agent in agents:
            if not agent:
                continue

            outcomes_dir = Path(agent.workdir)
            if not outcomes_dir.exists():
                continue

            metadata_file = outcomes_dir / "metadata.json"
            if metadata_file.exists():
                try:
                    with open(metadata_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        for outcome in data.get("outcomes", []):
                            outcome["agent_name"] = agent.name
                            outcomes.append(outcome)
                except Exception:
                    pass
            else:
                # 没有 metadata，列出目录下的文件
                for file_path in outcomes_dir.iterdir():
                    if file_path.name == "metadata.json":
                        continue
                    if file_path.is_file():
                        outcomes.append({
                            "id": file_path.stem,
                            "name": file_path.name,
                            "path": str(file_path),
                            "type": "file",
                            "agent_id": agent.id,
                            "agent_name": agent.name,
                            "description": "",
                        })

        return outcomes


def create_agent_tools(session_id: str, agent_id: str) -> AgentTools:
    """创建协作工具实例"""
    return AgentTools(session_id, agent_id)


def get_agent_tools_schema() -> List[Dict]:
    """获取协作工具的 schema 定义"""
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
                },
            },
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
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_agents",
                "description": "查询当前团队的所有成员及其工作状态。用于了解谁空闲、谁忙碌，以便智能分配任务。",
                "parameters": {
                    "type": "object",
                    "properties": {}
                },
            },
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
                },
            },
        },
    ]
