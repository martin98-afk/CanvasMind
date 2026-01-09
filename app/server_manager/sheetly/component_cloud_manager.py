# -*- coding: utf-8 -*-
import httpx
import json
import os
from loguru import logger
from datetime import datetime
from typing import List, Dict, Optional

from app.utils.config import Settings


class ComponentCloudManager:
    """使用 Sheety 连接谷歌 Sheets 进行云端组件管理，支持备份与还原"""

    # API 地址
    BASE_URL = "https://api.sheety.co/fe7b5d36457f54901b6078c05196e0a0/云组件库/sheet1"

    def __init__(self):
        self.client = httpx.Client(timeout=20.0)  # 增加超时时间
        self.config = Settings.get_instance()
        self.user = self.config.user_name.value
        self.headers = {"Content-Type": "application/json"}

    def _get_now_time(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # --- 基础 CRUD 功能 ---

    def fetch_all(self) -> List[Dict]:
        """获取云端所有组件"""
        try:
            response = self.client.get(self.BASE_URL)
            response.raise_for_status()
            data = response.json().get("sheet1", [])
            logger.info(f"成功从云端获取 {len(data)} 个组件")
            return data
        except Exception as e:
            logger.error(f"获取云端组件失败: {e}")
            return []

    def add_component(self, comp_id, name, category, description, requirements, version, source_code):
        """添加新组件到云端"""
        now = self._get_now_time()
        data = {
            "sheet1": {
                "组件id": comp_id,
                "组件名称": name,
                "组件类别": category,
                "组件描述": description,
                "工具包需求": requirements,
                "最后修改人": self.user,
                "最后修改时间": now,
                "创建人": self.user,
                "创建时间": now,
                "版本号": version,
                "组件源码": source_code
            }
        }
        try:
            response = self.client.post(self.BASE_URL, json=data, headers=self.headers)
            response.raise_for_status()
            logger.success(f"组件 {name} 已成功同步至云端")
            return response.json()
        except Exception as e:
            logger.error(f"添加组件失败: {e}")
            return None

    def update_component(self, sheety_row_id: int, update_fields: Dict):
        """更新云端组件（需提供 Sheety 内部 row_id）"""
        update_fields["最后修改人"] = self.user
        update_fields["最后修改时间"] = self._get_now_time()

        payload = {"sheet1": update_fields}
        try:
            response = self.client.put(f"{self.BASE_URL}/{sheety_row_id}", json=payload, headers=self.headers)
            response.raise_for_status()
            logger.success(f"组件行 {sheety_row_id} 更新成功")
            return True
        except Exception as e:
            logger.error(f"更新组件失败: {e}")
            return False

    def delete_component(self, sheety_row_id: int):
        """从云端删除组件"""
        try:
            response = self.client.delete(f"{self.BASE_URL}/{sheety_row_id}")
            if response.status_code == 204:
                logger.warning(f"组件行 {sheety_row_id} 已从云端删除")
                return True
            return False
        except Exception as e:
            logger.error(f"删除组件失败: {e}")
            return False

    # --- 搜索与定位功能 ---

    def find_by_comp_id(self, custom_id: str) -> Optional[Dict]:
        """通过自定义的 '组件id' 查找，返回完整信息（包含 id 供修改使用）"""
        all_data = self.fetch_all()
        for item in all_data:
            if str(item.get("组件id")) == str(custom_id):
                return item
        return None

    def search_components(self, keyword: str, field: str = "组件名称") -> List[Dict]:
        """
        灵活搜索
        :param keyword: 关键词
        :param field: 搜索字段（组件名称、组件类别、最后修改人等）
        """
        all_data = self.fetch_all()
        return [item for item in all_data if keyword.lower() in str(item.get(field, "")).lower()]

    # --- 备份与还原功能 (重点) ---

    def backup_to_local(self, file_path: str = "component_backup.json"):
        """将云端所有数据备份到本地 JSON 文件"""
        data = self.fetch_all()
        if not data:
            logger.warning("云端数据为空，取消备份")
            return False

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            logger.success(f"云端数据已成功备份至: {os.path.abspath(file_path)}")
            return True
        except Exception as e:
            logger.error(f"本地备份失败: {e}")
            return False

    def restore_from_local(self, file_path: str, overwrite: bool = False):
        """
        从本地 JSON 文件还原数据到云端
        :param file_path: 备份文件路径
        :param overwrite: 是否先清空云端再还原 (慎用)
        """
        if not os.path.exists(file_path):
            logger.error(f"备份文件 {file_path} 不存在")
            return False

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                local_data = json.load(f)

            if overwrite:
                logger.info("正在清空云端数据以准备完全还原...")
                self.clear_cloud()

            logger.info(f"开始还原 {len(local_data)} 个组件到云端...")
            for item in local_data:
                # 排除 Sheety 自动生成的 id 字段，避免冲突
                self.add_component(
                    comp_id=item.get("组件id"),
                    name=item.get("组件名称"),
                    category=item.get("组件类别"),
                    description=item.get("组件描述"),
                    requirements=item.get("工具包需求"),
                    version=item.get("版本号"),
                    source_code=item.get("组件源码")
                )
            logger.success("数据还原任务完成")
            return True
        except Exception as e:
            logger.error(f"还原失败: {e}")
            return False

    def clear_cloud(self):
        """清空云端所有组件 (危险操作)"""
        all_data = self.fetch_all()
        if not all_data:
            return

        logger.warning(f"准备删除云端共 {len(all_data)} 条记录...")
        for item in all_data:
            # Sheety 的 id 是每一行的唯一标识
            self.delete_component(item["id"])
        logger.info("云端数据已清空")

    def sync_local_to_cloud(self, local_components: List[Dict]):
        """
        增量同步：云端没有的则添加，有的则更新
        :param local_components: 本地组件列表
        """
        cloud_data = self.fetch_all()
        # 建立 业务ID 到 SheetyID 的映射
        cloud_mapping = {str(item["组件id"]): item["id"] for item in cloud_data}

        for lc in local_components:
            cid = str(lc.get("组件id"))
            if cid in cloud_mapping:
                # 更新
                logger.info(f"组件 {cid} 已存在，正在执行更新...")
                self.update_component(cloud_mapping[cid], lc)
            else:
                # 新增
                logger.info(f"组件 {cid} 不存在，正在新增...")
                self.add_component(
                    lc["组件id"], lc["组件名称"], lc["组件类别"],
                    lc["组件描述"], lc["工具包需求"], lc["版本号"], lc["组件源码"]
                )