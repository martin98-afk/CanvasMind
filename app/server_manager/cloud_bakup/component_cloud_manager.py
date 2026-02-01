# -*- coding: utf-8 -*-
from pathlib import Path

from loguru import logger
from datetime import datetime
from typing import List, Dict, Optional

from app.server_manager.cloud_bakup.adapters.gitee import GiteeAdapter
from app.utils.config import Settings


class ComponentCloudManager:
    """组件云端管理器 (基于 Gitee ZIP + Index.json)"""

    def __init__(self):
        self.config = Settings.get_instance()

        # 初始化你提供的 GiteeAdapter
        # 配置项建议在 Settings 中定义好
        self.adapter = GiteeAdapter(
            access_token=self.config.GITEE_TOKEN.value,
            owner=self.config.GITEE_OWNER.value,
            repo=self.config.GITEE_REPO.value,
            backup_dir="backup_components"
        )

    def _get_now_time(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # --- 对外 API ---

    def fetch_all(self) -> List[Dict]:
        """获取云端所有组件的索引信息"""
        try:
            return self.adapter.fetch_all()
        except Exception as e:
            logger.error(f"Gitee 获取列表失败: {e}")
            return []

    def add_component(self, comp_id, name, category, description, requirements, version, entry_file, resource_dir):
        """
        单条添加/备份组件
        :param entry_file: 本地 Python 入口文件路径
        :param resource_dir: 本地资源文件夹路径
        """
        now = self._get_now_time()

        # 构造符合 GiteeAdapter.add 期望的数据结构
        data = {
            "unique_id": comp_id,  # Adapter 必须的字段
            "组件id": comp_id,  # 兼容你业务的旧字段
            "组件名称": name,
            "组件类别": category,
            "组件描述": description,
            "工具包需求": str(requirements),
            "最后修改人": self.config.user_name.value,
            "最后修改时间": now,
            "创建人": self.config.user_name.value,
            "创建时间": now,
            "版本号": version,
            # 以下是 Adapter 打包 ZIP 必须的文件路径
            "entry_file": entry_file,
            "resource_dir": resource_dir
        }

        try:
            return self.adapter.add(data)
        except Exception as e:
            logger.error(f"备份组件 {comp_id} 到 Gitee 失败: {e}")
            return False

    def update_component(self, comp_id: str, update_fields: Dict):
        """
        更新组件元数据信息
        注意：如果涉及到源码变更，建议直接调用 add_component 重新触发打包
        """
        # 1. 先拿到现有数据
        current_data = self.find_by_comp_id(comp_id)
        if not current_data:
            logger.warning(f"云端不存在组件 {comp_id}，无法更新")
            return False

        # 2. 更新字段
        current_data.update(update_fields)
        current_data["最后修改人"] = self.config.user_name.value
        current_data["最后修改时间"] = self._get_now_time()

        # 3. 如果 update_fields 里没传文件路径，我们需要从其他地方获取或者仅更新索引
        try:
            return self.adapter.update(comp_id, current_data)
        except Exception as e:
            logger.error(f"更新组件 {comp_id} 失败: {e}")
            return False

    def delete_component(self, comp_id: str):
        """删除云端备份（包括 ZIP 和索引记录）"""
        try:
            return self.adapter.delete(comp_id)
        except Exception as e:
            logger.error(f"从 Gitee 删除组件 {comp_id} 失败: {e}")
            return False

    def find_by_comp_id(self, comp_id: str) -> Optional[Dict]:
        """查询单个组件信息"""
        results = self.adapter.fetch_all(search_query={"unique_id": comp_id})
        return results[0] if results else None

    def download_component(self, comp_id, extract_to_root):
        """
        从云端下载并精准还原组件
        :param comp_id: 组件 UUID
        :param extract_to_root: 程序根目录 (resource_path(""))
        """
        try:
            import zipfile
            import io
            import shutil
            import os

            # 1. 先从云端获取元数据，确定组件类别
            info = self.find_by_comp_id(comp_id)
            if not info:
                logger.error(f"云端不存在组件 {comp_id} 的元数据")
                return False

            category = info.get("组件类别", "常规")

            # 2. 获取 ZIP 字节流
            zip_path = f"{self.adapter.backup_dir}/{comp_id}.zip"
            zip_bytes, _ = self.adapter._get_gitee_file(zip_path)
            if not zip_bytes:
                logger.error(f"云端未找到组件 {comp_id} 的 ZIP 包")
                return False

            # 3. 创建临时解压目录
            temp_dir = Path(extract_to_root) / "temp_extract"
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)

            # 4. 解压到临时目录
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                zf.extractall(temp_dir)

            # 5. 精准还原 Python 入口文件
            # 规则：ZIP 里的第一个 .py 文件移动到 app/components/{category}/{comp_id}.py
            target_comp_dir = Path(extract_to_root) / "app" / "components" / category
            target_comp_dir.mkdir(parents=True, exist_ok=True)

            # 在临时目录找打包进去的那个 py 文件
            py_files = list(temp_dir.glob("*.py"))
            if py_files:
                # 强制重命名为 uuid.py
                shutil.move(str(py_files[0]), str(target_comp_dir / f"{comp_id}.py"))

            # 6. 精准还原资源文件夹
            # 规则：除了那个 .py 文件，剩下的全是资源，移动到 app/component_extensions/{comp_id}/
            target_ext_dir = Path(extract_to_root) / "app" / "component_extensions"
            if (target_ext_dir / comp_id).exists():
                shutil.rmtree(target_ext_dir / comp_id)
            target_ext_dir.mkdir(parents=True, exist_ok=True)

            # 移动临时目录里剩下的所有文件/文件夹（除了刚才移走的py）
            for item in temp_dir.iterdir():
                if item.is_dir():
                    shutil.move(str(item), str(target_ext_dir / item.name))
                elif item.is_file():  # 理论上 py 已经移走了，这里剩下的是根目录的资源文件
                    shutil.move(str(item), str(target_ext_dir / item.name))

            # 7. 清理临时目录
            shutil.rmtree(temp_dir)
            logger.success(f"组件 {comp_id} 物理还原成功")
            return True

        except Exception as e:
            logger.error(f"还原组件 {comp_id} 失败: {e}")
            return False

    # --- 同步逻辑 ---

    def sync_local_to_cloud(self, local_components: List[Dict]):
        """
        增量同步逻辑
        """
        if not local_components:
            return True

        current_user = str(self.config.user_name.value)
        is_admin = (current_user == "martin98-afk")
        logger.info(f"执行同步 - 用户: {current_user} | 管理员权限: {is_admin}")

        cloud_data = self.fetch_all()
        cloud_mapping = {str(item["unique_id"]): item for item in cloud_data}

        success_count = 0

        for lc in local_components:
            cid = str(lc.get("unique_id") or lc.get("组件id") or lc.get("uuid"))

            # 如果是管理员，或者云端不存在，则允许备份
            if is_admin or cid not in cloud_mapping:
                logger.info(f"正在同步组件至 Gitee: {cid}")
                # 注意：lc 必须包含 entry_file 和 resource_dir 的路径
                res = self.add_component(
                    comp_id=cid,
                    name=lc.get("组件名称") or lc.get("name"),
                    category=lc.get("组件类别") or lc.get("category"),
                    description=lc.get("组件描述") or lc.get("desc"),
                    requirements=lc.get("工具包需求") or lc.get("requirements"),
                    version=lc.get("版本号") or lc.get("version"),
                    entry_file=lc.get("entry_file"),
                    resource_dir=lc.get("resource_dir")
                )
                if res: success_count += 1
            else:
                logger.warning(f"组件 {cid} 已存在，非管理员无权覆盖")

        return success_count > 0