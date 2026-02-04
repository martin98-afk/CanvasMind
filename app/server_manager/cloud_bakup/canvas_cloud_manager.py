# -*- coding: utf-8 -*-
import json
import shutil
import zipfile
import io
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from loguru import logger

from app.server_manager.cloud_bakup.adapters.gitee import GiteeAdapter
from app.utils.config import Settings


class CanvasCloudManager:
    """
    画布云端管理器
    - 独立索引文件: index_canvas.json
    - 存储目录: backup_canvases
    - 包含文件: .workflow.json + 预览图片
    """

    def __init__(self):
        self.config = Settings.get_instance()

        # 初始化 GiteeAdapter
        # 指定 index_path 为 "index_canvas.json"，保证数据隔离
        self.adapter = GiteeAdapter(
            access_token=self.config.GITEE_TOKEN.value,
            owner=self.config.GITEE_OWNER.value,
            repo=self.config.GITEE_REPO.value,
            backup_dir="backup_canvases",
            index_path="index_canvas.json"
        )

    def _get_now_time(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # --- 核心操作 ---

    def fetch_all(self) -> List[Dict]:
        """获取云端画布列表"""
        try:
            return self.adapter.fetch_all()
        except Exception as e:
            logger.error(f"获取云端画布列表失败: {e}")
            return []

    def add_canvas(self, meta_info: Dict, json_path: str, image_path: Optional[str]):
        """
        备份画布
        :param meta_info: 画布元数据字典
        :param json_path: 本地 json 文件绝对路径
        :param image_path: 本地图片文件绝对路径 (可为 None)
        """
        now = self._get_now_time()
        canvas_id = meta_info.get("id")

        # 构造画布专用的字段结构，不需要和组件保持一致
        data = {
            "unique_id": canvas_id,  # Adapter 必需的主键
            "canvas_id": canvas_id,
            "canvas_name": meta_info.get("name"),
            "category": meta_info.get("category", "默认"),
            "description": meta_info.get("description", ""),
            "version": meta_info.get("version", "1.0.0"),
            "author": self.config.user_name.value,
            "updated_at": now,
            "created_at": now,
            "data_type": "canvas",

            # --- 文件路径传递 ---
            "entry_file": json_path,  # 映射：主文件
            "resource_dir": image_path,  # 映射：资源文件(这里是单张图片)

            # 也可以保留原始语义键供前端展示使用
            "origin_json_name": Path(json_path).name,
            "origin_image_name": Path(image_path).name if image_path else ""
        }

        try:
            # 调用 Adapter 进行打包上传
            # Adapter 内部应当将 entry_file 和 resource_dir 指向的内容打包进 ZIP
            return self.adapter.add(data)
        except Exception as e:
            logger.exception(f"备份画布 {canvas_id} 失败: {e}")
            return False

    def delete_canvas(self, canvas_id: str):
        """删除云端备份"""
        try:
            return self.adapter.delete(canvas_id)
        except Exception as e:
            logger.error(f"删除画布 {canvas_id} 失败: {e}")
            return False

    def find_by_id(self, canvas_id: str) -> Optional[Dict]:
        results = self.adapter.fetch_all(search_query={"unique_id": canvas_id})
        return results[0] if results else None

    def download_canvas(self, canvas_id: str, target_root_dir: Path) -> bool:
        """
        还原画布到本地
        :param canvas_id: 画布ID
        :param target_root_dir: 本地存储根目录 (例如 Settings.workflow_paths[0])
        """
        try:
            # 1. 获取元数据
            info = self.find_by_id(canvas_id)
            if not info:
                logger.error(f"云端不存在画布信息: {canvas_id}")
                return False

            # 获取画布名称用于创建文件夹
            canvas_name = info.get("canvas_name", canvas_id)

            # 2. 下载 ZIP
            zip_path = f"{self.adapter.backup_dir}/{canvas_id}.zip"
            zip_bytes, _ = self.adapter._get_gitee_file(zip_path)
            if not zip_bytes:
                logger.error(f"下载画布 ZIP 失败: {zip_path}")
                return False

            # 3. 准备目标文件夹 (处理重名逻辑: Name -> Name_1 -> Name_2)
            target_folder = target_root_dir / canvas_name
            counter = 0
            base_name = canvas_name
            while target_folder.exists():
                counter += 1
                target_folder = target_root_dir / f"{base_name}_{counter}"

            target_folder.mkdir(parents=True, exist_ok=True)

            # 4. 解压到临时内存并写入
            # 注意：压缩包里通常是平铺的 json 和图片
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                for file_name in zf.namelist():
                    # 排除不需要的系统文件
                    if file_name.startswith("__") or file_name.startswith("."):
                        continue

                    source = zf.read(file_name)

                    # 还原逻辑：
                    # 如果是 JSON，确保文件名是 {folder_name}.workflow.json (为了适配 WorkflowGallery 的规范)
                    if file_name.endswith(".json"):
                        # 强制重命名为标准的画布文件名结构: 文件夹名.workflow.json
                        final_name = f"{target_folder.name}.workflow.json"
                        with open(target_folder / final_name, 'wb') as f:
                            f.write(source)

                    # 如果是图片，直接放进去
                    elif file_name.lower().endswith(('.png', '.jpg', '.jpeg')):
                        with open(target_folder / file_name, 'wb') as f:
                            f.write(source)

            # 5. 更新文件的修改时间为当前时间，以便在 Gallery 中排在最前
            now_ts = datetime.now().timestamp()
            for f in target_folder.iterdir():
                os.utime(f, (now_ts, now_ts))

            logger.success(f"画布已还原至: {target_folder}")
            return True

        except Exception as e:
            logger.error(f"还原画布异常: {e}")
            # 失败清理
            if 'target_folder' in locals() and target_folder.exists():
                shutil.rmtree(target_folder)
            return False

    def sync_local_to_cloud(self, local_items: List[Dict]):
        """
        批量同步入口
        """
        cloud_data = self.fetch_all()
        cloud_ids = {item["unique_id"] for item in cloud_data}

        success = 0
        for item in local_items:
            # 简单的增量策略：如果云端没有 ID 则上传
            # 也可以根据 updated_at 字段做更复杂的覆盖逻辑
            if item["meta"]["id"] not in cloud_ids:
                logger.info(f"正在上传新画布: {item['meta']['name']}")
                res = self.add_canvas(
                    meta_info=item["meta"],
                    json_path=str(item["json_path"]),
                    image_path=str(item["image_path"]) if item["image_path"] else None
                )
                if res: success += 1

        return success