from datetime import datetime
from loguru import logger


class NodeLogHandler:
    """Loguru 节点日志处理器"""

    def __init__(self, node_id: str, log_callback):
        self.node_id = node_id
        self.log_callback = log_callback
        self.handler_id = None
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

    def get_logger(self):
        """获取节点专用的 logger"""
        return self.logger

    def add_handler(self):
        """添加日志处理器"""
        # 添加处理器（只添加一次）
        self.handler_id = logger.add(
            self._log_sink,
            level="INFO",
            enqueue=True,
            filter=lambda record: "node_id" in record["extra"]
        )