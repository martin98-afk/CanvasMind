# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod
import filecmp
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Callable, Set
import os

from loguru import logger

from app.components.base import GlobalVariableContext, ArgumentType, resource_path
from app.utils.utils import _safe_load_pickle


class BaseExecutor(ABC):
    """执行器基类 - 定义执行接口"""

    @abstractmethod
    def execute(self, ctx) -> Dict[str, Any]:
        """执行并返回结果"""
        pass

    @abstractmethod
    def can_execute(self, ctx) -> bool:
        """检查是否可以执行"""
        pass

    def prepare_environment(self, ctx) -> None:
        """准备执行环境 - 可被覆盖"""
        ctx.run_dir.mkdir(parents=True, exist_ok=True)

    def sync_file_if_needed(self, src: Path, dst: Path) -> bool:
        """仅在目标缺失或内容变化时复制文件"""
        src = Path(src)
        dst = Path(dst)
        if not src.exists():
            return False

        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and dst.is_file() and filecmp.cmp(src, dst, shallow=False):
            return False

        shutil.copy2(src, dst)
        return True

    def sync_directory_if_needed(
        self, src_dir: Path, dst_dir: Path, protected: set = None
    ) -> bool:
        """同步目录内容，未变化文件跳过，已删除源文件会从目标移除"""
        src_dir = Path(src_dir)
        dst_dir = Path(dst_dir)
        if protected is None:
            protected = set()
        else:
            protected = set(protected)
        if not src_dir.exists():
            return False

        changed = False
        dst_dir.mkdir(parents=True, exist_ok=True)

        src_entries = {entry.name: entry for entry in src_dir.iterdir()}
        dst_entries = {entry.name: entry for entry in dst_dir.iterdir()}

        for name, dst_entry in dst_entries.items():
            if name in protected:
                continue
            src_entry = src_entries.get(name)
            if src_entry is not None:
                continue

            changed = True
            if dst_entry.is_dir():
                shutil.rmtree(dst_entry, ignore_errors=True)
            else:
                dst_entry.unlink(missing_ok=True)

        for name, src_entry in src_entries.items():
            dst_entry = dst_dir / name

            if src_entry.is_dir():
                if dst_entry.exists() and not dst_entry.is_dir():
                    dst_entry.unlink(missing_ok=True)
                    changed = True
                if self.sync_directory_if_needed(src_entry, dst_entry):
                    changed = True
                continue

            if dst_entry.exists() and not dst_entry.is_file():
                shutil.rmtree(dst_entry, ignore_errors=True)
                changed = True

            if self.sync_file_if_needed(src_entry, dst_entry):
                changed = True

        return changed

    def sync_node_extensions(self, ctx) -> bool:
        """按需同步节点扩展依赖目录"""
        node_uuid = getattr(ctx.node, "uuid", None)
        if not node_uuid:
            return False

        extension_dir = Path(resource_path("app/component_extensions")) / str(node_uuid)
        if not extension_dir.exists():
            return False

        workspace_dir = ctx.cache_path / "workspace" / ctx.node.persistent_id
        return self.sync_directory_if_needed(extension_dir, workspace_dir, {"upload", "result"})

    def cleanup(self, ctx) -> None:
        """清理执行环境 - 可被覆盖"""
        try:
            import shutil

            shutil.rmtree(ctx.run_dir, ignore_errors=True)
        except Exception as e:
            logger.warning(f"清理执行目录失败: {e}")

    def read_result(self, ctx):
        """读取执行结果"""
        if ctx.result_path and ctx.result_path.exists():
            return _safe_load_pickle(ctx.result_path)
        return None

    def read_error(self, ctx):
        """读取错误信息"""
        if ctx.error_path and ctx.error_path.exists():
            return _safe_load_pickle(ctx.error_path)
        return None

    def wait_for_result(self, ctx, max_wait_time: float = 3.0) -> bool:
        """等待执行结果"""
        import time

        retry_interval = 0.2
        elapsed_time = 0.0

        while elapsed_time < max_wait_time:
            if ctx.check_cancel and ctx.check_cancel():
                raise Exception("执行被用户取消")

            if self.read_result(ctx):
                return True

            error_info = self.read_error(ctx)
            if error_info:
                ctx.node._log_message(
                    ctx.node.persistent_id, error_info.get("traceback", "")
                )
                raise Exception(error_info.get("traceback", "未知错误"))

            time.sleep(retry_interval)
            elapsed_time += retry_interval

        return False

    def read_logs(self, ctx) -> None:
        """读取并处理日志"""
        if not ctx.log_file_path or not os.path.exists(ctx.log_file_path):
            return

        try:
            with open(ctx.log_file_path, "r", encoding="utf-8", errors="ignore") as lf:
                lf.seek(ctx.last_log_pos)
                new_content = lf.read()
                if new_content:
                    ctx.node._log_message(ctx.node.persistent_id, new_content)
                    ctx.last_log_pos = lf.tell()
        except Exception as e:
            pass

    def apply_outputs(self, ctx, output: Dict[str, Any]) -> None:
        """将输出应用到节点"""
        if output is None:
            return
        for port in ctx.comp_obj.outputs:
            if port.type != ArgumentType.UPLOAD:
                ctx.node.set_output_value(port.name, output.get(port.name))
            else:
                ctx.node.set_output_value(
                    port.name, ctx.node.model.get_property(f"{port.name}_upload")
                )
        ctx.node._sync_buffer_to_global()
