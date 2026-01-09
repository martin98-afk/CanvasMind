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

    def __init__(self):
        self.config = Settings.get_instance()
        self.user = self.config.user_name.value

        # 初始化两个适配器
        self.primary = SteinAdapter(self.config.STEIN_URL.value)
        self.backup = SheetyAdapter(self.config.SHEETY_URL.value)

    def update_adapter(self, new_stein: str, new_sheety: str):
        """切换适配器"""
        self.config.set(self.config.STEIN_URL, new_stein)
        self.config.set(self.config.SHEETY_URL, new_sheety)
        self.config.save_config()
        logger.info(f"已切换云端适配器: Stein: {new_stein}, Sheety: {new_sheety}")

        self.primary = SteinAdapter(new_stein)
        self.backup = SheetyAdapter(new_sheety)

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
            "工具包需求": str(requirements),
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
        """
        if not components:
            return True

        now = self._get_now_time()
        batch_data = []

        for lc in components:
            # 字段兼容与标准化
            data = {
                "组件id": str(lc.get("组件id") or lc.get("uuid")),
                "组件名称": lc.get("组件名称") or lc.get("name"),
                "组件类别": lc.get("组件类别") or lc.get("category"),
                "组件描述": lc.get("组件描述") or lc.get("desc"),
                "工具包需求": str(lc.get("工具包需求") or lc.get("requirements") or "[]"),
                "最后修改人": self.config.user_name.value,
                "最后修改时间": now,
                "创建人": lc.get("创建人") or self.config.user_name.value,
                "创建时间": lc.get("创建时间") or now,
                "版本号": lc.get("版本号") or lc.get("version"),
                "组件源码": lc.get("组件源码") or lc.get("source")
            }
            batch_data.append(data)

        return self._execute("add", batch_data)

    def update_component(self, comp_id: str, update_fields: Dict):
        """
        专业优化：利用 Stein 的 condition 机制按 组件id 匹配更新
        :param comp_id: 组件唯一业务 ID
        :param update_fields: 需要更新的字段字典
        """
        update_fields["最后修改人"] = self.config.user_name.value
        update_fields["最后修改时间"] = self._get_now_time()

        # 构建 Stein PUT 请求要求的格式
        payload = {
            "condition": {"组件id": str(comp_id)},
            "set": update_fields
        }
        # 这里的 update 在适配器层应处理 PUT 请求
        return self._execute("update", payload)

    def update_rows(self, condition: Dict, set_data: Dict, limit: Optional[int] = None):
        """
        专业功能：批量多行条件修改
        例如：{"condition": {"创建人": "martin"}, "set": {"版本号": "2.0.0"}}
        """
        set_data["最后修改人"] = self.config.user_name.value
        set_data["最后修改时间"] = self._get_now_time()

        payload = {
            "condition": condition,
            "set": set_data
        }
        if limit:
            payload["limit"] = limit

        return self._execute("update", payload)

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
        """
        增量同步逻辑
        权限规则：只有 martin98-afk 拥有覆盖更新权限，否则全部作为新记录 add_batch 上传
        """
        if not local_components:
            return True

        current_user = str(self.config.user_name.value)
        is_admin = (current_user == "martin98-afk")
        logger.info(f"执行同步 - 用户: {current_user} | 管理员权限: {is_admin}")

        cloud_data = self.fetch_all()
        cloud_mapping = {str(item["组件id"]): item for item in cloud_data}

        to_add = []
        success_count = 0

        for lc in local_components:
            # 统一取值
            cid = str(lc.get("组件id") or lc.get("uuid"))

            # 管理员权限：如果云端已存在，则调用优化的 update_component (PUT)
            if is_admin and cid in cloud_mapping:
                update_data = {
                    "组件名称": lc.get("组件名称") or lc.get("name"),
                    "组件描述": lc.get("组件描述") or lc.get("desc"),
                    "工具包需求": str(lc.get("工具包需求") or lc.get("requirements") or "[]"),
                    "版本号": lc.get("版本号") or lc.get("version"),
                    "组件源码": lc.get("组件源码") or lc.get("source"),
                    "组件类别": lc.get("组件类别") or lc.get("category")
                }
                logger.info(f"管理员正在更新组件: {cid}")
                if self.update_component(cid, update_data):
                    success_count += 1
            else:
                # 非管理员用户，或不存在的组件，全部存入待新增列表
                if not is_admin and cid in cloud_mapping:
                    logger.warning(f"组件 {cid} 已在云端存在，当前用户无权覆盖，将新建副本。")
                to_add.append(lc)

        # 批量上传新增部分
        if to_add:
            logger.info(f"开始为用户 {current_user} 批量上传 {len(to_add)} 个组件记录...")
            if self.add_batch(to_add):
                success_count += len(to_add)
                logger.success(f"批量上传成功")
            else:
                logger.error(f"批量上传失败")

        return success_count > 0