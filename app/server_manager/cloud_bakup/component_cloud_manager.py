# -*- coding: utf-8 -*-
import json
import os
from loguru import logger
from datetime import datetime
from typing import List, Dict, Optional

from app.server_manager.cloud_bakup.adapters.sheety import SheetyAdapter
from app.server_manager.cloud_bakup.adapters.stein import SteinAdapter
from app.utils.config import Settings


class ComponentCloudManager:
    """组件云端管理器 (Stein 优先，Sheety 备用)"""

    STEIN_URL = "https://api.steinhq.com/v1/storages/69606496affba40a6237b4c2/sheet1"
    SHEETLY_URL = "https://api.sheety.co/fe7b5d36457f54901b6078c05196e0a0/云组件库/sheet1"

    def __init__(self):
        self.config = Settings.get_instance()
        self.user = self.config.user_name.value

        # 初始化两个适配器
        self.primary = SteinAdapter(self.STEIN_URL)
        self.backup = SheetyAdapter(self.SHEETLY_URL)

    def _get_now_time(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _execute(self, method_name: str, *args, **kwargs):
        """核心调度逻辑：优先 Stein，失败则试 Sheety"""
        try:
            method = getattr(self.primary, method_name)
            return method(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Stein 适配器执行 {method_name} 失败，尝试备用 Sheety: {e}")
            try:
                method = getattr(self.backup, method_name)
                return method(*args, **kwargs)
            except Exception as e2:
                logger.error(f"所有云端适配器均执行失败: {e2}")
                return None if method_name == "fetch_all" else False

    # --- 对外 API ---

    def fetch_all(self) -> List[Dict]:
        return self._execute("fetch_all") or []

    def add_component(self, comp_id, name, category, description, requirements, version, source_code):
        now = self._get_now_time()
        data = {
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
        return self._execute("add", data)

    def update_component(self, cloud_id: str, update_fields: Dict, is_row_id: bool = False):
        """
        :param cloud_id: 如果是 Stein，传 '组件id'；如果是 Sheety，传行号 'id'
        :param is_row_id: 是否是 Sheety 专用的行号
        """
        update_fields["最后修改人"] = self.user
        update_fields["最后修改时间"] = self._get_now_time()

        # 如果当前运行的是 Sheety 逻辑，且我们已知 row_id，直接调用
        return self._execute("update", cloud_id, update_fields)

    def delete_component(self, cloud_id: str):
        return self._execute("delete", cloud_id)

    def find_by_comp_id(self, comp_id: str) -> Optional[Dict]:
        """利用 Stein 的搜索能力"""
        results = self._execute("fetch_all", search_query={"组件id": comp_id})
        return results[0] if results else None

    # --- 高级功能 ---

    def backup_to_local(self, file_path: str = "component_backup.json"):
        data = self.fetch_all()
        if not data: return False
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            logger.success(f"已备份至: {file_path}")
            return True
        except Exception as e:
            logger.error(f"备份失败: {e}")
            return False

    def sync_local_to_cloud(self, local_components: List[Dict]):
        """增量同步逻辑"""
        cloud_data = self.fetch_all()
        # 建立 业务ID 到 云端原始对象 的映射
        # 注意：Sheety 需要存储内部 'id' 才能更新
        cloud_mapping = {str(item["组件id"]): item for item in cloud_data}

        for lc in local_components:
            cid = str(lc.get("组件id"))
            if cid in cloud_mapping:
                # 更新。如果是 Sheety 备用状态，需要取出内部 'id'
                internal_id = cloud_mapping[cid].get("id", cid)
                logger.info(f"同步更新: {cid}")
                self.update_component(internal_id, lc)
            else:
                logger.info(f"同步新增: {cid}")
                self.add_component(
                    lc["组件id"], lc["组件名称"], lc["组件类别"],
                    lc["组件描述"], lc["工具包需求"], lc["版本号"], lc["组件源码"]
                )