# -*- coding: utf-8 -*-
from typing import List, Dict, Optional

class BaseAdapter:
    """云端存储基类"""
    def fetch_all(self, search_query: Optional[Dict] = None) -> List[Dict]:
        raise NotImplementedError

    def add(self, data: Dict) -> bool:
        raise NotImplementedError

    def update(self, unique_id: str, data: Dict) -> bool:
        raise NotImplementedError

    def delete(self, unique_id: str) -> bool:
        raise NotImplementedError