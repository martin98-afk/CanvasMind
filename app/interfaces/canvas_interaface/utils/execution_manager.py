import threading
import time
from dataclasses import dataclass, Field, field
from typing import Any, List, Optional

from PyQt5.QtCore import QObject, pyqtSignal
from loguru import logger


@dataclass
class ExecutionRecord:
    execution_id: str
    canvas_name: str
    trigger_type: str
    start_time: float
    end_time: Optional[float] = None
    status: str = "running"  # running, success, failed, cancelled
    input_data: Any = None
    output_data: dict = field(default_factory=dict)
    error_msg: Optional[str] = None


class ExecutionSignal(QObject):
    execution_updated = pyqtSignal()


class ExecutionManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ExecutionManager, cls).__new__(cls)
                cls._instance.signal = ExecutionSignal()
                cls._instance._records = {}  # { execution_id: ExecutionRecord }
                cls._instance._max_history = 1000  # 限制内存占用
            return cls._instance

    def create_record(self, exec_id, canvas_name, trigger_type, input_data=None) -> str:
        record = ExecutionRecord(
            execution_id=exec_id,
            canvas_name=canvas_name,
            trigger_type=trigger_type,
            start_time=time.time(),
            input_data=input_data
        )
        self._records[exec_id] = record
        # 简单清理旧数据
        if len(self._records) > self._max_history:
            oldest_key = next(iter(self._records))
            del self._records[oldest_key]
        self.signal.execution_updated.emit()
        return exec_id

    def update_record(self, exec_id, status, output_data=None, error_msg=None):
        if exec_id in self._records:
            record = self._records[exec_id]
            record.status = status
            record.end_time = time.time()
            if output_data is not None:
                record.output_data = output_data
            if error_msg is not None:
                record.error_msg = error_msg
            self.signal.execution_updated.emit()
            logger.info(f"执行完成: {exec_id} | 状态: {status}")

    def clear_records(self):
        self._records.clear()

    def add_output_data(self, exec_id, output_data):
        if exec_id in self._records:
            record = self._records[exec_id]
            record.output_data.update(output_data)

    def get_record(self, exec_id) -> Optional[ExecutionRecord]:
        return self._records.get(exec_id)

    def get_all_records(self) -> List[ExecutionRecord]:
        return list(self._records.values())