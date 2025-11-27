from datetime import datetime
from typing import Dict, List, Optional
from PyQt5.QtCore import QObject


class ChatSession:
    def __init__(self, name: str = None, messages: Optional[List[Dict]] = None):
        self.name = name or f"对话 {datetime.now().strftime('%m-%d %H:%M')}"
        self.messages: List[Dict[str, str]] = messages.copy() if messages is not None else []

    def get_context_messages(self) -> List[Dict[str, str]]:
        return self.messages.copy()

    def add_assistant_message(self, content: str):
        self.messages.append({
            "role": "assistant",
            "content": content,
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    def add_user_message(self, content: str, params: dict = None):
        self.messages.append({
            "role": "user",
            "content": content,
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "params": params or {}
        })


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
        self.sessions[self.current_index] = ChatSession(messages=messages.copy())