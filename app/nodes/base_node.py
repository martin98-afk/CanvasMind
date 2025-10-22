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
        """可选：仍保留内存日志用于实时滚动显示（如控制台面板）"""
        if isinstance(message, str) and message.strip():
            if not message.endswith('\n'):
                message += '\n'
            self._realtime_logs += message

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
        w.exec()

    def set_output_value(self, port_name, value):
        self._output_values[port_name] = value

    def clear_output_value(self):
        self._output_values = {}

    def get_output_value(self, port_name):
        return self._output_values.get(port_name)