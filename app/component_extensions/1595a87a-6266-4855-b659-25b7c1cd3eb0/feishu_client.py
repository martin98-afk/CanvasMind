# -*- coding: utf-8 -*-
import os
import json
import requests
import uuid
import re

# === 常量定义 ===
TYPE_ALIASES = {
    "string": "text", "rich_text": "text", "float": "number", "int": "number",
    "datetime": "date", "time": "date", "文本": "text", "富文本": "text",
    "邮箱": "email", "邮件": "email", "数字": "number", "数值": "number",
    "单选": "single_select", "多选": "multi_select", "日期": "date", "时间": "date",
    "复选框": "checkbox", "勾选": "checkbox", "人员": "user", "用户": "user",
    "电话": "phone", "手机": "phone", "链接": "url", "网址": "url", "附件": "attachment",
}

class FeishuBitableClient:
    def __init__(self, app_id, app_secret):
        self.app_id = app_id
        self.app_secret = app_secret
        self._token_cache = None

    def get_token(self):
        if self._token_cache:
            return self._token_cache
        if not (self.app_id and self.app_secret):
            return None
        
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        data = {"app_id": self.app_id, "app_secret": self.app_secret}
        try:
            res = requests.post(url, json=data, timeout=20)
            token = res.json().get("tenant_access_token")
            if token:
                self._token_cache = token
            return token
        except Exception as e:
            print(f"[FeishuClient] Token error: {e}")
            return None
    
    def headers(self):
        t = self.get_token()
        return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"} if t else {}

    def resolve_app_token(self, token_input, table_id=None):
        """解析 App Token，支持 Wiki 链接"""
        if not token_input: return token_input
        s = token_input.strip()
        
        # 处理 Wiki URL
        if "/wiki/" in s:
            try:
                parts = s.split("/wiki/")
                if len(parts) > 1:
                    wiki_token = parts[1].split("?")[0].split("/")[0]
                    node_token = self._get_wiki_node_info(wiki_token)
                    if node_token: return node_token
            except:
                pass
        return s

    def _get_wiki_node_info(self, wiki_token):
        t = self.get_token()
        if not t: return None
        url = "https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node"
        params = {"token": wiki_token}
        headers = {"Authorization": f"Bearer {t}"}
        try:
            res = requests.get(url, params=params, headers=headers, timeout=10)
            j = res.json()
            if j.get("code") == 0:
                node = j.get("data", {}).get("node", {})
                if node.get("obj_type") == "bitable":
                    return node.get("obj_token")
        except:
            pass
        return None

    def list_fields_map(self, app_token, table_id):
        headers = self.headers()
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
        try:
            res = requests.get(url, headers=headers, timeout=20)
            j = res.json()
            items = j.get("data", {}).get("items", [])
            name_to_id = {}
            for it in items:
                name_to_id[it.get("field_name")] = it.get("field_id")
            return name_to_id
        except:
            return {}

    def create_field(self, app_token, table_id, field_name, field_type="text"):
        headers = self.headers()
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
        
        # 类型映射
        type_map = {
            "text": 1, "number": 2, "single_select": 3, "multi_select": 4, 
            "date": 5, "checkbox": 7, "user": 11, "phone": 13, "url": 15, "attachment": 17
        }
        mapped_type = TYPE_ALIASES.get(field_type, field_type)
        type_code = type_map.get(mapped_type, 1)

        payload = {"field_name": field_name, "type": type_code}
        # 附件类型传 property 会报错
        if type_code != 17: payload["property"] = {}

        try:
            res = requests.post(url, json=payload, headers=headers, timeout=20)
            return res.status_code, res.text
        except Exception as e:
            return 0, str(e)

    def ensure_fields(self, app_token, table_id, required_fields):
        """确保字段存在，不存在则创建"""
        existing_map = self.list_fields_map(app_token, table_id)
        existing_names = set(existing_map.keys())
        
        created_logs = []
        for f in required_fields:
            name = f["name"]
            ftype = f.get("type", "text")
            if name not in existing_names:
                code, _ = self.create_field(app_token, table_id, name, ftype)
                if code in (200, 201):
                    created_logs.append(f"Created Field: {name}")
                else:
                    created_logs.append(f"Failed to Create Field: {name}")
        return created_logs

    def upload_attachment(self, app_token, image_bytes, filename=None):
        t = self.get_token()
        if not t: return None
        if not filename: filename = f"{uuid.uuid4().hex}.png"
        
        url = "https://open.feishu.cn/open-apis/drive/v1/medias/upload_all"
        headers = {"Authorization": f"Bearer {t}"}
        files = {"file": (filename, image_bytes, "image/png")}
        data = {
            "file_name": filename, 
            "parent_type": "bitable_image", 
            "parent_node": app_token, 
            "size": str(len(image_bytes))
        }
        try:
            res = requests.post(url, headers=headers, files=files, data=data, timeout=30)
            if res.status_code == 200:
                return res.json().get("data", {}).get("file_token")
        except Exception as e:
            print(f"Upload error: {e}")
        return None

    def create_record(self, app_token, table_id, fields, view_id=None):
        headers = self.headers()
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"
        body = {"fields": fields}
        if view_id: body["view_id"] = view_id
        
        try:
            res = requests.post(url, json=body, headers=headers, timeout=30)
            return res.status_code, res.json()
        except Exception as e:
            return 0, str(e)

    @staticmethod
    def coerce_value(field_type, value):
        """简单的值类型转换"""
        ft = TYPE_ALIASES.get(field_type, field_type)
        if ft == "number":
            try:
                if isinstance(value, (int, float)): return value
                s = str(value).strip().replace(",", "")
                return float(s) if "." in s else int(s)
            except:
                return None
        elif ft == "checkbox":
            return str(value).lower() in ("true", "1", "yes", "on")
        elif ft == "text" or ft == "url":
             return str(value)
        return value