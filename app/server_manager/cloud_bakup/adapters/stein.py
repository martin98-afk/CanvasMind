import httpx
from typing import Optional, Dict, List

from app.server_manager.cloud_bakup.adapters.base import BaseAdapter


class SteinAdapter(BaseAdapter):
    """Stein 适配器 (优先，5000次/月)"""

    def __init__(self, url: str):
        self.url = url

    def fetch_all(self, search_query: Optional[Dict] = None) -> List[Dict]:
        params = {}
        if search_query:
            # Stein 支持 JSON 字符串搜索: ?search={"组件id":"xxx"}
            import json
            params["search"] = json.dumps(search_query)

        with httpx.Client(timeout=20.0) as client:
            resp = client.get(self.url, params=params)
            resp.raise_for_status()
            return resp.json()  # Stein 直接返回列表

    def add(self, data: Dict) -> bool:
        # Stein 接受对象数组: [ {...} ]
        with httpx.Client(timeout=20.0) as client:
            if not isinstance(data, list):
                data = [data]
            resp = client.post(self.url, json=data)
            return resp.status_code == 200

    def update(self, unique_id: str, data: Dict) -> bool:
        # Stein 使用 condition 匹配更新
        payload = {
            "condition": {"组件id": unique_id},
            "set": data
        }
        with httpx.Client(timeout=20.0) as client:
            resp = client.put(self.url, json=payload)
            return resp.status_code == 200

    def delete(self, unique_id: str) -> bool:
        payload = {"condition": {"组件id": unique_id}}
        with httpx.Client(timeout=20.0) as client:
            # 注意：某些 Stein 版本 DELETE 需要通过 request 或特定的 put 实现，标准为此格式
            resp = client.request("DELETE", self.url, json=payload)
            return resp.status_code == 200