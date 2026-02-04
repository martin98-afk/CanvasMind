# -*- coding: utf-8 -*-
import requests
import json
import base64
import zipfile
import io
import os
from typing import List, Dict, Optional, Tuple

from loguru import logger


class GiteeAdapter:
    def __init__(self, access_token: str, owner: str, repo: str, backup_dir: str = "storage", index_path="index.json"):
        """
        :param backup_dir: 在仓库中存放 zip 包的目录名
        """
        self.access_token = access_token
        self.owner = owner
        self.repo = repo
        self.backup_dir = backup_dir.strip("/")
        self.index_path = index_path
        self.base_url = f"https://gitee.com/api/v5/repos/{owner}/{repo}/contents"

    # --- 内部工具方法 ---

    def _get_gitee_file(self, path: str) -> Tuple[Optional[bytes], Optional[str]]:
        """获取文件内容和 SHA"""
        url = f"{self.base_url}/{path}"
        resp = requests.get(url, params={"access_token": self.access_token})
        if resp.status_code == 200:
            data = resp.json()
            if not data:
                return None, None
            return base64.b64decode(data["content"]), data["sha"]
        return None, None

    def _pack_component(self, entry_file: str, resource_dir: str) -> bytes:
        """将入口文件和文件夹打包成 zip 字节流"""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # 写入入口文件
            if os.path.exists(entry_file):
                zf.write(entry_file, os.path.basename(entry_file))

            # 写入资源文件夹
            if os.path.exists(resource_dir):
                for root, dirs, files in os.walk(resource_dir):
                    for file in files:
                        full_path = os.path.join(root, file)
                        # 保持相对路径结构
                        rel_path = os.path.relpath(full_path, os.path.dirname(resource_dir))
                        zf.write(full_path, rel_path)
        return buffer.getvalue()

    # --- BaseAdapter 接口实现 ---

    def fetch_all(self, search_query: Optional[Dict] = None) -> List[Dict]:
        """查询 index.json 中的组件列表"""
        content, _ = self._get_gitee_file(self.index_path)
        if not content:
            return []

        data_list = json.loads(content.decode("utf-8"))
        if search_query:
            return [
                item for item in data_list
                if all(item.get(k) == v for k, v in search_query.items())
            ]
        return data_list

    def _upload_to_gitee(self, path: str, content_bytes: bytes, sha: str = None, message: str = "") -> bool:
        """ 核心修复：自动判断 POST(新增) 或 PUT(更新) """
        url = f"{self.base_url}/{path}"
        payload = {
            "access_token": self.access_token,
            "content": base64.b64encode(content_bytes).decode("utf-8"),
            "message": message or f"update {path}"
        }

        if sha:
            # 如果有 sha，说明文件已存在，必须用 PUT 更新
            payload["sha"] = sha
            resp = requests.put(url, json=payload)
            action = "更新"
        else:
            # 没有 sha，说明是新文件，用 POST 创建
            resp = requests.post(url, json=payload)
            action = "创建"

        if resp.status_code not in [200, 201]:
            logger.error(f"Gitee {action}文件失败: {path} | 状态码: {resp.status_code} | 响应: {resp.text}")
            return False
        return True

    def add(self, data: Dict) -> bool:
        """ 备份组件：自动处理覆盖逻辑 """
        unique_id = data["unique_id"]
        zip_filename = f"{self.backup_dir}/{unique_id}.zip"

        # 1. 打包
        zip_bytes = self._pack_component(data["entry_file"], data["resource_dir"])

        # 2. 【核心修复】先尝试获取云端 ZIP 文件的 SHA，用于覆盖上传
        _, zip_sha = self._get_gitee_file(zip_filename)

        # 3. 上传 ZIP（如果 zip_sha 存在则会自动走 PUT 更新流程）
        success = self._upload_to_gitee(zip_filename, zip_bytes, zip_sha, f"Backup/Update zip for {unique_id}")
        if not success:
            return False

        # 4. 更新 index.json 索引
        # 同样的道理，index.json 也必须先拿 sha 才能更新
        index_content, index_sha = self._get_gitee_file(self.index_path)
        index_list = json.loads(index_content.decode("utf-8")) if index_content else []

        # 替换旧索引记录
        new_list = [i for i in index_list if i.get("unique_id") != unique_id]
        metadata = {k: v for k, v in data.items() if k not in ["entry_file", "resource_dir"]}
        metadata["zip_path"] = zip_filename
        new_list.append(metadata)

        return self._upload_to_gitee(
            self.index_path,
            json.dumps(new_list, ensure_ascii=False, indent=4).encode("utf-8"),
            index_sha,
            "Update index with component: " + unique_id
        )

    def download(self, unique_id: str, extract_to: str) -> bool:
        """下载并解压组件"""
        zip_path = f"{self.backup_dir}/{unique_id}.zip"
        zip_bytes, _ = self._get_gitee_file(zip_path)
        if not zip_bytes:
            print("未找到备份文件")
            return False

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            zf.extractall(extract_to)
        return True

    def delete(self, unique_id: str) -> bool:
        """删除备份及索引"""
        # 1. 从 index 移除
        index_content, index_sha = self._get_gitee_file(self.index_path)
        if index_content:
            index_list = json.loads(index_content.decode("utf-8"))
            new_list = [i for i in index_list if i["unique_id"] != unique_id]
            self._upload_to_gitee(self.index_path, json.dumps(new_list).encode("utf-8"), index_sha,
                                  f"Delete {unique_id} from index")

        # 2. 删除 zip 文件
        zip_path = f"{self.backup_dir}/{unique_id}.zip"
        url = f"{self.base_url}/{zip_path}"
        _, zip_sha = self._get_gitee_file(zip_path)
        if zip_sha:
            requests.delete(url, params={"access_token": self.access_token, "sha": zip_sha, "message": "Delete zip"})
        return True

    def update(self, unique_id: str, data: Dict) -> bool:
        # 在这个逻辑下，update 和 add 行为一致（覆盖上传）
        data["unique_id"] = unique_id
        return self.add(data)


if __name__ == "__main__":
    # 测试
    adapter = GiteeAdapter(
        "a5dcb6e2e7776143b7a7e7685a1f33a3",
        "dingmama123141",
        "canvas-mind-components",
        "backup_components"
    )
    print(
        adapter.add(
            {
                "unique_id": "1e382445-94c2-45a6-a534-c11961e8c481",
                "name": "测试组件",
                "entry_file": r"D:\work\CanvasMind\app\components\comfyui节点\LTX模型适配\1e382445-94c2-45a6-a534-c11961e8c481.py",
                "resource_dir": r"D:\work\CanvasMind\app\component_extensions\1e382445-94c2-45a6-a534-c11961e8c481",
                "version": "1.0.0"
            }
        )
    )