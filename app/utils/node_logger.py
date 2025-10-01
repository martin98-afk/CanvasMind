# -*- coding: utf-8 -*-
import os
import tempfile

from loguru import logger


class NodeLogHandler:
    """Loguru 节点日志处理器 - 支持文件日志"""

    def __init__(self, node_id: str, log_callback, use_file_logging=False):
        self.node_id = node_id
        self.log_callback = log_callback
        self.handler_id = None
        self.file_handler_id = None
        self.use_file_logging = use_file_logging
        self.log_file_path = None

        # 如果使用文件日志，则创建临时日志文件
        if self.use_file_logging:
            self.log_file_path = os.path.join(tempfile.mkdtemp(), f"node_{node_id}.log")

        self.logger = logger.bind(node_id=self.node_id)  # 提前 bind
        self.add_handler()

    def _log_sink(self, message):
        """Loguru 日志接收器"""
        record = message.record
        if record["extra"].get("node_id") != self.node_id:
            return  # 忽略其他节点的日志
        timestamp = record["time"].strftime("%Y-%m-%d %H:%M:%S")
        function = record["function"]
        line = record["line"]
        level = record["level"].name
        msg = record["message"]

        formatted_msg = f"[{timestamp}] {function}-{line} {level}: {msg}"
        self.log_callback(self.node_id, formatted_msg)

    def _file_sink(self, message):
        """文件日志接收器"""
        record = message.record
        if record["extra"].get("node_id") != self.node_id:
            return  # 忽略其他节点的日志
        timestamp = record["time"].strftime("%Y-%m-%d %H:%M:%S")
        function = record["function"]
        line = record["line"]
        level = record["level"].name
        msg = record["message"]

        formatted_msg = f"[{timestamp}] {function}-{line} {level}: {msg}\n"

        # 将日志写入文件
        if self.log_file_path:
            with open(self.log_file_path, 'a', encoding='utf-8') as f:
                f.write(formatted_msg)

    def get_logger(self):
        """获取节点专用的 logger"""
        return self.logger

    def add_handler(self):
        """添加日志处理器"""
        # 添加控制台处理器
        self.handler_id = logger.add(
            self._log_sink,
            level="INFO",
            enqueue=True,
            filter=lambda record: "node_id" in record["extra"]
        )

        # 如果使用文件日志，添加文件处理器
        if self.use_file_logging:
            self.file_handler_id = logger.add(
                self._file_sink,
                level="INFO",
                enqueue=True,
                filter=lambda record: "node_id" in record["extra"]
            )

    def remove_handler(self):
        """移除日志处理器"""
        if self.handler_id is not None:
            logger.remove(self.handler_id)
        if self.file_handler_id is not None:
            logger.remove(self.file_handler_id)

    def get_log_file_path(self):
        """获取日志文件路径"""
        return self.log_file_path

    def read_log_file(self):
        """读取日志文件内容"""
        if self.log_file_path and os.path.exists(self.log_file_path):
            with open(self.log_file_path, 'r', encoding='utf-8') as f:
                return f.read()
        return ""

    def cleanup(self):
        """清理日志文件"""
        if self.log_file_path and os.path.exists(self.log_file_path):
            try:
                os.remove(self.log_file_path)
                # 尝试删除临时目录（如果为空）
                temp_dir = os.path.dirname(self.log_file_path)
                if os.path.exists(temp_dir):
                    try:
                        os.rmdir(temp_dir)
                    except OSError:
                        pass  # 目录不为空，跳过删除
            except Exception:
                pass  # 忽略删除失败
        self.remove_handler()