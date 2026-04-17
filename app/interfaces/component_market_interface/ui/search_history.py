# -*- coding: utf-8 -*-
import json
import os
from pathlib import Path


class SearchHistoryManager:
    _instance = None

    MAX_HISTORY = 10

    def __init__(self):
        self._history_file = Path(__file__).parent / "search_history.json"
        self._history = self._load_history()

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = SearchHistoryManager()
        return cls._instance

    def _load_history(self):
        try:
            if self._history_file.exists():
                with open(self._history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def _save_history(self):
        try:
            with open(self._history_file, "w", encoding="utf-8") as f:
                json.dump(self._history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add(self, query):
        if not query or len(query.strip()) < 1:
            return
        query = query.strip()
        if query in self._history:
            self._history.remove(query)
        self._history.insert(0, query)
        self._history = self._history[: self.MAX_HISTORY]
        self._save_history()

    def get_history(self):
        return list(self._history)

    def remove(self, query):
        if query in self._history:
            self._history.remove(query)
            self._save_history()

    def clear(self):
        self._history = []
        self._save_history()


search_history = SearchHistoryManager.instance
