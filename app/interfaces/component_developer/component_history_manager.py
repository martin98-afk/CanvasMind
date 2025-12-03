# -*- coding: utf-8 -*-
import datetime
import json

from pathlib import Path
from loguru import logger
from packaging.version import Version

from app.utils.utils import canvas_file_dump_path


# --- 组件历史版本记录 ---
class ComponentHistoryManager:
    """管理组件的编辑历史记录"""
    HISTORY_DIR = canvas_file_dump_path() / "node_histories"
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE_SUFFIX = ".history.json"

    @staticmethod
    def get_history_file_path(component_file_path: Path) -> Path:
        """根据组件文件路径生成历史记录文件路径"""
        if not component_file_path or not component_file_path.suffix == '.py':
            return None
        return (ComponentHistoryManager.HISTORY_DIR /
                (component_file_path.stem + ComponentHistoryManager.HISTORY_FILE_SUFFIX))

    @staticmethod
    def save_history(
            component_file_path: Path,
            component_name: str,
            code: str,
            current_signature: dict = None
    ):
        history_file_path = ComponentHistoryManager.get_history_file_path(component_file_path)
        if not history_file_path:
            logger.error(f"无法为 {component_file_path} 生成历史记录文件路径")
            return

        histories = []
        if history_file_path.exists():
            try:
                with open(history_file_path, 'r', encoding='utf-8') as f:
                    histories = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError) as e:
                logger.error(f"读取历史记录文件失败: {e}")

        # 初始版本
        if not histories:
            version = "0.0.0"
            logger.info(f"首次保存组件 {component_name}，版本: {version}")
        else:
            last = histories[-1]
            if last.get("code") == code:
                logger.info("代码未改变，跳过保存历史记录。")
                return

            last_sig = last.get("signature", {})
            is_interface_changed = (current_signature != last_sig)

            try:
                last_ver = Version(last["version"])
            except:
                last_ver = Version("0.0.0")

            if is_interface_changed:
                version = f"{last_ver.major + 1}.0.0"
            else:
                version = f"{last_ver.major}.{last_ver.minor}.{last_ver.micro + 1}"

        # 构建新记录
        new_entry = {
            "version": version,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "component_name": component_name,
            "code": code,
            "signature": current_signature or {},
            "description": "初始版本" if not histories else "无"
        }
        histories.append(new_entry)

        # 保留最近 20 条（避免丢失大版本）
        histories = histories[-20:]

        try:
            with open(history_file_path, 'w', encoding='utf-8') as f:
                json.dump(histories, f, ensure_ascii=False, indent=4)
                logger.info(f"保存组件 {component_name} 历史记录成功，版本: {version}")
        except Exception as e:
            logger.error(f"保存历史记录失败: {e}")

        return version

    @staticmethod
    def load_histories(component_file_path: Path) -> list:
        """加载指定组件的历史记录列表"""
        history_file_path = ComponentHistoryManager.get_history_file_path(component_file_path)
        if not history_file_path or not history_file_path.exists():
            return []
        try:
            with open(history_file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"加载历史记录文件失败: {e}")
            return []

    @staticmethod
    def save_new_version(comp_cls, new_code: str):
        history_file = getattr(comp_cls, "_history_file", None)
        if not history_file or not history_file.exists():
            return

        with open(history_file, "r", encoding="utf-8") as f:
            records = json.load(f)

        # 生成新版本号
        last_ver = records[-1]["version"]
        if last_ver.startswith("V") and last_ver[1:].isdigit():
            next_ver = f"V{int(last_ver[1:]) + 1}"
        else:
            next_ver = f"V{len(records) + 1}"

        new_record = {
            "version": next_ver,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "component_name": comp_cls.name,
            "category": comp_cls.category,
            "code": new_code
        }
        records.append(new_record)

        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)