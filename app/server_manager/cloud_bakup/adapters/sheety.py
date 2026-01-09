import httpx
from typing import Optional, Dict, List

from app.server_manager.cloud_bakup.adapters.base import BaseAdapter


class SheetyAdapter(BaseAdapter):
    """Sheety 适配器 (备份，200次/月)"""
    def __init__(self, url: str):
        self.url = url
        self.sheet_name = "sheet1"

    def fetch_all(self, search_query: Optional[Dict] = None) -> List[Dict]:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(self.url)
            resp.raise_for_status()
            data = resp.json().get(self.sheet_name, [])
            if search_query:
                # Sheety 免费版不支持复杂搜索，需手动过滤
                for key, val in search_query.items():
                    data = [item for item in data if str(item.get(key)) == str(val)]
            return data

    def add(self, data: Dict) -> bool:
        payload = {self.sheet_name: data}
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(self.url, json=payload)
            return resp.status_code == 201

    def update(self, row_id: str, data: Dict) -> bool:
        # Sheety 更新必须使用行 ID (id)
        payload = {self.sheet_name: data}
        url = f"{self.url}/{row_id}"
        with httpx.Client(timeout=20.0) as client:
            resp = client.put(url, json=payload)
            return resp.status_code == 200

    def delete(self, row_id: str) -> bool:
        url = f"{self.url}/{row_id}"
        with httpx.Client(timeout=20.0) as client:
            resp = client.delete(url)
            return resp.status_code == 204