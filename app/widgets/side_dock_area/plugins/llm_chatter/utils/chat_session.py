from datetime import datetime
from typing import Dict, List, Optional
from PyQt5.QtCore import QObject

from app.widgets.side_dock_area.plugins.llm_chatter.core.task_state import (
    TaskSessionState,
)


class ChatSession:
    def __init__(self, name: str = None, messages: Optional[List[Dict]] = None):
        self.name = name or f"对话 {datetime.now().strftime('%m-%d %H:%M')}"
        self.messages: List[Dict[str, str]] = (
            messages.copy() if messages is not None else []
        )
        self.topic_summary: str = ""
        self.created_at: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.last_updated: str = self.created_at
        self.message_count: int = len(self.messages)
        self.task_state = TaskSessionState()

    def get_context_messages(self) -> List[Dict[str, str]]:
        return self.messages.copy()

    def add_system_message(self, content: str):
        self.messages.append(
            {
                "role": "system",
                "content": content,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        self._update_timestamp()

    def add_assistant_message(self, content: str):
        self.messages.append(
            {
                "role": "assistant",
                "content": content,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        self._update_timestamp()

    def add_user_message(self, content: str, params: dict = None):
        self.messages.append(
            {
                "role": "user",
                "content": content,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "params": params or {},
            }
        )
        self._update_timestamp()

    def _update_timestamp(self):
        self.last_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.message_count = len(self.messages)

    def set_topic_summary(self, summary: str):
        self.topic_summary = summary

    def get_recent_messages(self, count: int = 10) -> List[Dict]:
        return self.messages[-count:] if self.messages else []

    def clear(self):
        self.messages.clear()
        self.topic_summary = ""
        self._update_timestamp()

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "messages": self.messages,
            "topic_summary": self.topic_summary,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "message_count": self.message_count,
            "task_state": {
                "current_agent": self.task_state.current_agent,
                "current_goal": self.task_state.current_goal,
                "stage": self.task_state.stage,
                "related_files": self.task_state.related_files,
                "todo_items": self.task_state.todo_items,
                "last_tool_name": self.task_state.last_tool_name,
                "last_tool_args": self.task_state.last_tool_args,
                "last_tool_result": self.task_state.last_tool_result,
                "last_tool_success": self.task_state.last_tool_success,
                "last_error": self.task_state.last_error,
                "verification_status": self.task_state.verification_status,
                "verification_summary": self.task_state.verification_summary,
            },
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ChatSession":
        session = cls(name=data.get("name"), messages=data.get("messages", []))
        session.topic_summary = data.get("topic_summary", "")
        session.created_at = data.get(
            "created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        session.last_updated = data.get("last_updated", session.created_at)
        session.message_count = len(session.messages)
        task_state_data = data.get("task_state", {})
        for field_name, value in task_state_data.items():
            if hasattr(session.task_state, field_name):
                setattr(session.task_state, field_name, value)
        return session


class SessionManager(QObject):
    def __init__(self):
        super().__init__()
        self.sessions: List[ChatSession] = []
        self.current_index = -1

    def create_new_session(self) -> ChatSession:
        session = ChatSession()
        self.sessions.append(session)
        self.current_index = len(self.sessions) - 1
        return session

    def get_current_session(self) -> Optional[ChatSession]:
        if 0 <= self.current_index < len(self.sessions):
            return self.sessions[self.current_index]
        return None

    def switch_to_session(self, index: int):
        if 0 <= index < len(self.sessions):
            self.current_index = index

    def get_session_names(self) -> List[str]:
        return [s.name for s in self.sessions]

    def set_session_from_messages(self, messages: List[Dict]):
        if self.current_index < 0:
            self.current_index = 0
        if self.current_index >= len(self.sessions):
            self.sessions.append(ChatSession(messages=messages.copy()))
        else:
            self.sessions[self.current_index] = ChatSession(messages=messages.copy())

    def set_current_session(self, session: ChatSession):
        if self.current_index < 0:
            self.sessions.append(session)
            self.current_index = len(self.sessions) - 1
            return
        if self.current_index >= len(self.sessions):
            self.sessions.append(session)
            self.current_index = len(self.sessions) - 1
            return
        self.sessions[self.current_index] = session

    def delete_session(self, index: int) -> bool:
        if 0 <= index < len(self.sessions):
            self.sessions.pop(index)
            if self.current_index >= len(self.sessions):
                self.current_index = len(self.sessions) - 1
            return True
        return False

    def get_all_sessions(self) -> List[ChatSession]:
        return self.sessions.copy()
