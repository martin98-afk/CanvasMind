# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional, Callable
import os

from loguru import logger

from app.components.base import GlobalVariableContext, ArgumentType, resource_path


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

    def cleanup(self, ctx) -> None:
        """清理执行环境 - 可被覆盖"""
        try:
            import shutil

            shutil.rmtree(ctx.run_dir, ignore_errors=True)
        except Exception as e:
            logger.warning(f"清理执行目录失败: {e}")

    def read_result(self, ctx):
        """读取执行结果"""
        from app.utils.utils import _safe_load_pickle

        if ctx.result_path and ctx.result_path.exists():
            return _safe_load_pickle(ctx.result_path)
        return None

    def read_error(self, ctx):
        """读取错误信息"""
        from app.utils.utils import _safe_load_pickle

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
