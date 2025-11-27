import os
import json
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path


class HistoryManager:
    def __init__(self, canvas_name: str):
        self.canvas_name = canvas_name
        self.history_dir = Path("canvas_files") / "llm_history"
        self.history_file = self.history_dir / f"{canvas_name}.json"
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self._history_sessions: List[Dict] = self._load_history()

    def _load_history(self) -> List[Dict]:
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 确保必要字段存在
                    for item in data:
                        if 'title' not in item:
                            item['title'] = '未命名对话'
                        if 'last_time' not in item:
                            item['last_time'] = item.get('messages', [{}])[-1].get('timestamp', '未知')
                    return data
            except Exception:
                pass
        return []

    def save_session(self, messages: List[Dict], title: str = None):
        if not messages:
            return
        last_msg_time = messages[-1].get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M'))
        if not title:
            # 简单提取用户首条消息前30字作为标题
            for msg in messages:
                if msg.get('role') == 'user':
                    title = msg.get('content', '')[:30].strip() or '新对话'
                    break
            else:
                title = '新对话'

        self._history_sessions.insert(0, {
            'title': title,
            'last_time': last_msg_time,
            'messages': messages
        })
        self._save_to_disk()

    def _save_to_disk(self):
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(self._history_sessions, f, ensure_ascii=False, indent=2)

    def get_history_list(self) -> List[Dict]:
        return self._history_sessions

    def delete_history(self, index: int):
        if 0 <= index < len(self._history_sessions):
            self._history_sessions.pop(index)
            self._save_to_disk()

    def get_session_by_index(self, index: int) -> Optional[List[Dict]]:
        if 0 <= index < len(self._history_sessions):
            return self._history_sessions[index]['messages']
        return None

    def update_session(self, index: int, messages: List[Dict]):
        """更新指定历史会话的内容"""
        if 0 <= index < len(self._history_sessions):
            # 保留原 title，只更新 messages 和 last_time
            last_msg_time = messages[-1].get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M'))
            self._history_sessions[index]['messages'] = messages
            self._history_sessions[index]['last_time'] = last_msg_time
            self._save_to_disk()