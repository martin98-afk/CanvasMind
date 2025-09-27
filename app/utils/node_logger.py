from datetime import datetime

from loguru import logger


class NodeLogHandler:
    """Loguru 节点日志处理器"""

    def __init__(self, node_id: str, log_callback):
        self.node_id = node_id
        self.log_callback = log_callback
        self.logger = None
        self.handler_id = None

    def _log_sink(self, message):
        """Loguru 日志接收器"""
        # 提取消息内容（去除格式化）
        record = message.record
        timestamp = datetime.fromtimestamp(record["time"].timestamp()).strftime("%Y-%m-%d %H:%M:%S")
        level = record["level"].name
        msg = record["message"]

        formatted_msg = f"[{timestamp}] {level}: {msg}"
        self.log_callback(self.node_id, formatted_msg)

    def get_logger(self):
        """获取节点专用的 logger"""
        if self.logger is None:
            # 创建新的 logger 实例
            self.logger = logger.bind(node_id=self.node_id)
            # 添加处理器
            self.handler_id = self.logger.add(
                self._log_sink,
                level="DEBUG",
                format="{message}",
                enqueue=True  # 异步处理，避免阻塞
            )
        return self.logger

    def remove_handler(self):
        """移除日志处理器"""
        if self.logger and self.handler_id:
            self.logger.remove(self.handler_id)
            self.handler_id = None