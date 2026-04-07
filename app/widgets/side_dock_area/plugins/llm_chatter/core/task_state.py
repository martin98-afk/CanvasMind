from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


CODING_STAGES = ["discover", "plan", "edit", "verify", "review", "summarize"]
STAGE_PROMPTS = {
    "discover": "## Active Stage: Discover\n"
    "Goal: Understand project structure, constraints, and relevant context.\n"
    "Expected tools: Read, Glob, Grep, Bash (for exploration).\n"
    "→ When context is sufficient, use switch_stage tool to transition to plan.",
    "plan": "## Active Stage: Plan\n"
    "Goal: Produce implementation path with files, risks, validation steps.\n"
    "Expected tools: Write a concrete plan using todo tool or analysis.\n"
    "→ When plan is solid, use switch_stage tool to transition to edit.",
    "edit": "## Active Stage: Edit\n"
    "Goal: Make focused changes, preserve local patterns, keep edits verifiable.\n"
    "Expected tools: write, edit.\n"
    "→ When changes are complete, use switch_stage tool to transition to verify.",
    "verify": "## Active Stage: Verify\n"
    "Goal: Run validation commands, explain failures concretely.\n"
    "Expected tools: Bash (pytest, test, compile, lint).\n"
    "→ When verification passes, use switch_stage tool to transition to review.",
    "review": "## Active Stage: Review\n"
    "Goal: Check for regressions, missing tests, weak assumptions.\n"
    "Expected tools: Read, Grep for inspection.\n"
    "→ When review is done, use switch_stage tool to transition to summarize.",
    "summarize": "## Active Stage: Summarize\n"
    "Goal: Compress work into concise handoff for next step.\n"
    "Expected tools: Final summary output.\n"
    "→ Task complete.",
}


def get_stage_prompt(stage: str) -> str:
    if stage not in CODING_STAGES:
        stage = "discover"
    return STAGE_PROMPTS[stage]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class TaskEvent:
    kind: str
    payload: Dict[str, Any]
    timestamp: str = field(default_factory=_now)


@dataclass
class TaskSessionState:
    current_agent: str = "plan"
    current_goal: str = ""
    stage: str = "discover"
    related_files: List[str] = field(default_factory=list)
    todo_items: List[Dict[str, Any]] = field(default_factory=list)
    last_tool_name: str = ""
    last_tool_args: Dict[str, Any] = field(default_factory=dict)
    last_tool_result: str = ""
    last_tool_success: Optional[bool] = None
    last_error: str = ""
    verification_status: str = "not_run"
    verification_summary: str = ""
    recent_events: List[TaskEvent] = field(default_factory=list)
    def set_goal(self, goal: str):
        goal = (goal or "").strip()
        if goal:
            self.current_goal = goal
            self.add_event("goal", {"goal": goal})

    def switch_agent(self, agent_name: str):
        if not agent_name:
            return
        self.current_agent = agent_name
        self.add_event("agent", {"agent": agent_name})

    def set_stage(self, stage: str, reason: str = ""):
        if stage not in CODING_STAGES:
            return
        if self.stage != stage:
            self.stage = stage
            self.add_event("stage", {"stage": stage, "reason": reason})

    def add_related_files(self, files: List[str]):
        changed = False
        for file_path in files or []:
            normalized = str(file_path).strip()
            if normalized and normalized not in self.related_files:
                self.related_files.append(normalized)
                changed = True
        if changed:
            self.related_files = self.related_files[-12:]
            self.add_event("files", {"files": self.related_files[-6:]})

    def update_todos(self, todos: List[Dict[str, Any]]):
        self.todo_items = todos or []
        self.add_event("todos", {"count": len(self.todo_items)})

    def update_tool_result(
        self,
        tool_name: str,
        args: Dict[str, Any],
        result: str,
        success: Optional[bool],
    ):
        self.last_tool_name = tool_name or ""
        self.last_tool_args = args or {}
        self.last_tool_result = (result or "").strip()[:4000]
        self.last_tool_success = success
        self.add_event(
            "tool",
            {
                "tool": self.last_tool_name,
                "success": success,
                "summary": self.last_tool_result[:300],
            },
        )

        files = []
        for key in ("filePath", "path"):
            value = self.last_tool_args.get(key)
            if isinstance(value, str) and value.strip():
                files.append(value.strip())
        staged_files = self.last_tool_args.get("files", [])
        if isinstance(staged_files, list):
            files.extend(
                [str(item).strip() for item in staged_files if str(item).strip()]
            )
        self.add_related_files(files)

    def update_verification(self, status: str, summary: str):
        self.verification_status = status
        self.verification_summary = (summary or "").strip()[:2000]
        self.add_event(
            "verification",
            {"status": status, "summary": self.verification_summary[:300]},
        )

    def record_error(self, error: str):
        self.last_error = (error or "").strip()[:2000]
        if self.last_error:
            self.add_event("error", {"error": self.last_error[:300]})

    def add_event(self, kind: str, payload: Dict[str, Any]):
        self.recent_events.append(TaskEvent(kind=kind, payload=payload))
        self.recent_events = self.recent_events[-12:]

    def infer_stage_from_turn(self, user_text: str):
        text = (user_text or "").lower()
        if not text.strip():
            return

        if any(token in text for token in ["test", "pytest", "验证", "检查", "运行"]):
            self.set_stage("verify", "user-request")
            return
        if any(token in text for token in ["review", "审查", "检查问题", "找bug"]):
            self.set_stage("review", "user-request")
            return
        if any(
            token in text
            for token in ["实现", "修改", "fix", "重构", "优化", "新增", "patch"]
        ):
            self.set_stage("edit", "user-request")
            return
        if any(token in text for token in ["plan", "分析", "设计", "方案", "思路"]):
            self.set_stage("plan", "user-request")
            return

        # 对多轮追问默认保持当前阶段，避免每次都回到 discover 重新搜索文件。
        follow_up_markers = [
            "继续",
            "然后",
            "再",
            "另外",
            "顺便",
            "基于上面",
            "根据上面",
            "刚才",
            "前面",
            "这里",
            "这个",
            "那个",
            "为什么",
            "怎么",
            "如何",
            "那就",
            "接着",
            "下一步",
        ]
        has_existing_context = bool(
            self.related_files
            or self.todo_items
            or self.last_tool_name
            or self.recent_events
        )
        if any(marker in text for marker in follow_up_markers) and has_existing_context:
            return

        # 已经有上下文时，普通追问默认进入 plan，而不是退回 discover。
        if has_existing_context:
            if self.stage == "discover":
                self.set_stage("plan", "preserve-context")
            return

        self.set_stage("discover", "default")

    def build_context_block(self) -> str:
        lines = ["## Current Coding Task State"]
        lines.append(
            f"you should follow the stage steps: discover -> plan -> edit -> verify -> review -> summarize to complete the task."
        )
        lines.append(f"- Agent: {self.current_agent or 'unknown'}")
        lines.append(f"- Stage: {self.stage}")
        lines.append(f"- Stage goal: {get_stage_prompt(self.stage)}")
        lines.append(f"- Goal: {self.current_goal or 'Not set'}")
        lines.append(f"- Verification: {self.verification_status}")
        if self.related_files or self.todo_items or self.last_tool_name:
            lines.append(
                "- Reuse existing session context first. Avoid re-scanning files unless the user changes scope or the current context is insufficient."
            )
        if self.related_files:
            lines.append("- Related files:")
            lines.extend(f"  - {item}" for item in self.related_files[-8:])
        if self.todo_items:
            lines.append("- Todo:")
            for todo in self.todo_items[-6:]:
                content = todo.get("content", "")
                status = todo.get("status", "pending")
                priority = todo.get("priority", "medium")
                lines.append(f"  - [{priority}/{status}] {content}")
        if self.last_tool_name:
            lines.append(f"- Last tool: {self.last_tool_name}")
            if self.last_tool_result:
                lines.append(f"- Last tool summary: {self.last_tool_result[:500]}")
        if self.verification_summary:
            lines.append(f"- Verification summary: {self.verification_summary[:500]}")
        if self.last_error:
            lines.append(f"- Last error: {self.last_error[:400]}")
        return "\n".join(lines)

    def build_event_digest(self) -> str:
        if not self.recent_events:
            return ""
        lines = [
            "## Current Execution Time",
            f"- {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            "## Recent Execution Digest",
        ]
        for event in self.recent_events[-8:]:
            lines.append(f"- {event.timestamp} [{event.kind}] {event.payload}")
        return "\n".join(lines) + "\n\n"
