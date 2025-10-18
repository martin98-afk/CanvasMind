# -*- coding: utf-8 -*-
import os
from pathlib import Path
from loguru import logger

# 全局配置
LOG_ROOT = Path("logs") / "nodes"
LOG_ROOT.mkdir(parents=True, exist_ok=True)
MAX_LOG_LINES = 5000


class NodeLogHandler:
    """Loguru 节点日志处理器 - 持久化日志，最多保留 5000 行"""

    def __init__(self, node_id: str, log_callback, use_file_logging=False):
        self.node_id = node_id
        self.log_callback = log_callback
        self.use_file_logging = use_file_logging
        self.handler_id = None
        self.file_handler_id = None

        # 持久化日志路径
        safe_node_id = "".join(c if c.isalnum() or c in "._-" else "_" for c in str(node_id))
        self.log_file_path = LOG_ROOT / f"node_{safe_node_id}.log"

        self.logger = logger.bind(node_id=self.node_id)
        self.add_handler()

    def _log_sink(self, message):
        """UI 回调日志接收器"""
        record = message.record
        if record["extra"].get("node_id") != self.node_id:
            return
        timestamp = record["time"].strftime("%Y-%m-%d %H:%M:%S")
        formatted_msg = f"[{timestamp}] {record['function']}-{record['line']} {record['level'].name}: {record['message']}"
        self.log_callback(self.node_id, formatted_msg)

    def _file_sink(self, message):
        """持久化文件日志接收器（带行数限制）"""
        record = message.record
        if record["extra"].get("node_id") != self.node_id:
            return

        timestamp = record["time"].strftime("%Y-%m-%d %H:%M:%S")
        formatted_msg = f"[{timestamp}] {record['function']}-{record['line']} {record['level'].name}: {record['message']}\n"

        try:
            # 1. 读取现有日志（最多 MAX_LOG_LINES - 1 行）
            existing_lines = []
            if self.log_file_path.exists():
                with open(self.log_file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    # 保留最后 (MAX_LOG_LINES - 1) 行
                    existing_lines = lines[-(MAX_LOG_LINES - 1):]

            # 2. 添加新日志
            all_lines = existing_lines + [formatted_msg]

            # 3. 写回（最多 MAX_LOG_LINES 行）
            with open(self.log_file_path, 'w', encoding='utf-8') as f:
                f.writelines(all_lines[-MAX_LOG_LINES:])

        except Exception as e:
            # 避免日志写入失败导致组件崩溃
            print(f"⚠️ 日志写入失败 ({self.log_file_path}): {e}")

    def get_logger(self):
        return self.logger

    def add_handler(self):
        self.handler_id = logger.add(
            self._log_sink,
            level="INFO",
            enqueue=True,
            filter=lambda r: r["extra"].get("node_id") == self.node_id
        )

        if self.use_file_logging:
            self.file_handler_id = logger.add(
                self._file_sink,
                level="INFO",
                enqueue=True,
                filter=lambda r: r["extra"].get("node_id") == self.node_id
            )

    def remove_handler(self):
        if self.handler_id is not None:
            logger.remove(self.handler_id)
        if self.file_handler_id is not None:
            logger.remove(self.file_handler_id)

    def get_log_file_path(self):
        return str(self.log_file_path)

    def read_log_file(self):
        if self.log_file_path.exists():
            try:
                with open(self.log_file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                print(lines)
                print(self.log_file_path)
                # 返回最近 5000 行
                return ''.join(lines[-5000:])
            except Exception:
                return ""
        return ""

    def cleanup(self):
        """清理日志文件（谨慎使用）"""
        try:
            self.log_file_path.unlink(missing_ok=True)
        except Exception:
            pass
        self.remove_handler()