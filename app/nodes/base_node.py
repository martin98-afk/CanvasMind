import uuid
from NodeGraphQt import NodeObject
from loguru import logger

from app.utils.node_logger import NodeLogHandler
from app.widgets.dialog_widget.component_log_message_box import LogMessageBox


class BasicNodeWithGlobalProperty(NodeObject):
    """
    所有业务节点的基类
    """

    def __init__(self, qgraphics_item=None):
        super().__init__(qgraphics_item)
        self.parent_window = None
        self._output_values = {}
        self._input_values = {}
        self.column_select = {}
        self._node_logs = ""
        self._realtime_logs = ""

        self.model.add_property("global_variable", {})
        self.model.add_property("persistent_id", str(uuid.uuid4()))

    @property
    def persistent_id(self):
        return self.model.get_property("persistent_id")

    @property
    def global_variable(self):
        return self.model.get_property("global_variable")

    # ===========================日志处理=================================================
    def init_logger(self):
        self.log_capture = NodeLogHandler(self.persistent_id, self._log_message, use_file_logging=True)

    def _log_message(self, node_id, message):
        """处理实时日志：追加到内存变量，并推送到已连接的日志窗口"""
        if isinstance(message, str) and message.strip():
            if not message.endswith('\n'):
                message += '\n'
            # 1. 追加到内存变量 (保持原有逻辑)
            self._realtime_logs += message

            # 2. 推送到日志窗口 (新增逻辑)
            if hasattr(self, 'log_capture') and self.log_capture and self.log_capture.log_window:
                try:
                    # 直接调用 LogMessageBox 的 add_log_entry 方法
                    self.log_capture.log_window.add_log_entry(message)
                    print(f"[DEBUG] BasicNode: Sent message to log window: {message[:30]}...")  # 调试信息
                except Exception as e:
                    print(f"Error sending log to window from _log_message: {e}")

    def get_logs(self):
        """从持久化日志文件读取内容（最多5000行）"""
        if not hasattr(self, "log_capture"):
            self.init_logger()
        try:
            return self.log_capture.read_log_file()
        except Exception as e:
            logger.warning(f"读取日志失败: {e}")
            return "日志读取失败。"

    def show_logs(self):
        log_content = self.get_logs()
        w = LogMessageBox(log_content, self.parent_window)

        self.log_capture.set_log_window(w)
        # ---
        w.show()

    def set_output_value(self, port_name, value):
        self._output_values[port_name] = value

    def clear_output_value(self):
        self._output_values = {}

    def get_output_value(self, port_name):
        return self._output_values.get(port_name)