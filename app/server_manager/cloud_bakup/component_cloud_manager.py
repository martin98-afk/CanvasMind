# -*- coding: utf-8 -*-
import json
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
                # 兼容不同返回类型的默认值
                if method_name == "fetch_all":
                    return []
                return False

    # --- 对外 API ---

    def fetch_all(self) -> List[Dict]:
        return self._execute("fetch_all") or []

    def add_component(self, comp_id, name, category, description, requirements, version, source_code):
        """单条添加"""
        now = self._get_now_time()
        data = {
            "组件id": comp_id,
            "组件名称": name,
            "组件类别": category,
            "组件描述": description,
            "工具包需求": str(requirements),  # 确保是字符串防止解析错误
            "最后修改人": self.config.user_name.value,
            "最后修改时间": now,
            "创建人": self.config.user_name.value,
            "创建时间": now,
            "版本号": version,
            "组件源码": source_code
        }
        return self._execute("add", data)

    def add_batch(self, components: List[Dict]):
        """
        批量添加组件列表 (优化网络请求)
        :param components: 结构匹配本地缓存格式的列表
        """
        if not components:
            return True

        now = self._get_now_time()
        batch_data = []

        for lc in components:
            # 兼容 UI 传参和本地字典格式
            data = {
                "组件id": str(lc.get("uuid") or lc.get("组件id")),
                "组件名称": lc.get("name") or lc.get("组件名称"),
                "组件类别": lc.get("category") or lc.get("组件类别"),
                "组件描述": lc.get("desc") or lc.get("组件描述"),
                "工具包需求": str(lc.get("requirements") or lc.get("工具包需求", "[]")),
                "最后修改人": self.config.user_name.value,
                "最后修改时间": now,
                "创建人": self.config.user_name.value,
                "创建时间": now,
                "版本号": lc.get("version") or lc.get("版本号"),
                "组件源码": lc.get("source") or lc.get("组件源码")
            }
            batch_data.append(data)

        # Stein 适配器的 add 方法通常支持 Dict 或 List[Dict]
        # 如果适配器不支持列表，建议在适配器里做循环，但在这里统筹调度
        return self._execute("add", batch_data)

    def update_component(self, cloud_id: str, update_fields: Dict, is_row_id: bool = False):
        """
        :param cloud_id: 如果是 Stein，传 '组件id'；如果是 Sheety，传行号 'id'
        :param is_row_id: 是否是 Sheety 专用的行号
        """
        update_fields["最后修改人"] = self.config.user_name.value
        update_fields["最后修改时间"] = self._get_now_time()
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
        """增量同步逻辑 (优化批量上传)"""
        if not local_components:
            return True

        cloud_data = self.fetch_all()
        # 建立 业务ID 到 云端原始对象 的映射
        cloud_mapping = {str(item["组件id"]): item for item in cloud_data}

        to_add = []
        success_count = 0

        for lc in local_components:
            cid = str(lc.get("uuid") or lc.get("组件id"))
            if cid in cloud_mapping:
                # 已存在则同步更新（更新通常只能单条操作，受限于 API 设计）
                internal_id = cloud_mapping[cid].get("id", cid)
                # 提取更新字段，移除可能冲突的内部 id
                update_data = {
                    "组件名称": lc.get("name") or lc.get("组件名称"),
                    "组件描述": lc.get("desc") or lc.get("组件描述"),
                    "工具包需求": str(lc.get("requirements") or lc.get("工具包需求", "[]")),
                    "版本号": lc.get("version") or lc.get("版本号"),
                    "组件源码": lc.get("source") or lc.get("组件源码"),
                    "组件类别": lc.get("category") or lc.get("组件类别")
                }
                logger.info(f"同步更新: {cid}")
                if self.update_component(internal_id, update_data):
                    success_count += 1
            else:
                # 不存在则加入待批量新增列表
                to_add.append(lc)

        # 执行批量上传新增组件
        if to_add:
            logger.info(f"开始批量上传 {len(to_add)} 个新组件...")
            if self.add_batch(to_add):
                success_count += len(to_add)
                logger.success(f"批量上传完成")
            else:
                logger.error(f"批量上传失败")

        return success_count > 0