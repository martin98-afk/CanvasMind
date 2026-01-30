import json
import os
import traceback
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSlot
from PyQt5.QtCore import pyqtSignal, QThread, QRectF, Qt, QRunnable
from PyQt5.QtGui import QPainter, QImage
from loguru import logger

from app.scan_components import ComponentScanner
from app.utils.utils import deserialize_from_json
from app.utils.utils import serialize_for_json


def get_node_uuid(full_path: str) -> str:
    node_comp_cls = ComponentScanner().get_component(full_path)
    if node_comp_cls:
        return node_comp_cls.uuid
    else:
        return "unknown"


# ────────────────────────────────
# 保存功能的辅助类（用于子线程）
# ────────────────────────────────
class SaveWorkerSignals(QObject):
    """保存任务的信号"""
    finished = pyqtSignal()
    error = pyqtSignal(str)


class SaveTask(QRunnable):
    """后台保存任务：负责耗时的序列化和IO操作"""

    def __init__(self, file_path, full_data):
        super().__init__()
        self.file_path = file_path
        self.full_data = full_data  # 这是一个纯 Python 字典，不包含任何 Qt 对象
        self.signals = SaveWorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            # 1. 确保目录存在
            Path(self.file_path).parent.mkdir(parents=True, exist_ok=True)

            # 2. 序列化数据 (耗时操作：处理 numpy, pandas 等转换)
            # 注意：serialize_for_json 不应访问任何 Qt 对象，只处理数据
            serialized_data = serialize_for_json(self.full_data)

            # 3. 写入文件 (IO 阻塞操作)
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(serialized_data, f, indent=2, ensure_ascii=False)

            self.signals.finished.emit()

        except Exception as e:
            err_msg = traceback.format_exc()
            logger.error(f"SaveTask failed: {err_msg}")
            self.signals.error.emit(str(e))


# ────────────────────────────────
# 加载辅助类
# ────────────────────────────────
class FinishLoadingWorker(QObject):
    finished = pyqtSignal(object, object)


class FinishLoadingTask(QRunnable):
    def __init__(self, graph, runtime_data, node_status_data, worker: FinishLoadingWorker):
        super().__init__()
        self.graph = graph
        self.runtime_data = runtime_data
        self.node_status_data = node_status_data
        self.worker = worker

    @pyqtSlot()
    def run(self):
        try:
            target_env = self.runtime_data.get("environment")

            restored = {}
            for node in self.graph.all_nodes():
                full_path = getattr(node, 'FULL_PATH', 'unknown')
                node_comp_cls = ComponentScanner().get_component(full_path)
                stable_key = f"{node_comp_cls.uuid}||{node.name()}" if node_comp_cls else f"unknown||{node.name()}"

                ns = self.node_status_data.get(stable_key, {})
                node_inputs = ns.get("node_inputs", {}) or {}
                node_outputs = ns.get("node_outputs", {}) or {}
                status_str = ns.get("node_states", "unrun") or "unrun"

                input_vals = deserialize_from_json(node_inputs)
                output_vals = deserialize_from_json(node_outputs)

                restored[node.id] = {
                    "input_values": input_vals,
                    "output_values": output_vals,
                    "status_str": status_str,
                }

            self.worker.finished.emit(restored, target_env)

        except Exception as e:
            logger.error(f"FinishLoadingTask failed: {traceback.format_exc()}")
            self.worker.finished.emit(None, None)


class ThumbnailGenerator(QThread):
    """异步生成缩略图的线程类"""
    finished = pyqtSignal(str)  # 发送生成的文件路径

    def __init__(self, graph, workflow_path):
        super().__init__()
        self.graph = graph
        self.workflow_path = workflow_path

    def run(self):
        """在后台线程中生成缩略图"""
        try:
            # 构造预览图路径：xxx.workflow.json → xxx.png
            base_name = os.path.splitext(os.path.splitext(self.workflow_path)[0])[0]  # 去掉 .workflow.json
            png_path = base_name + ".png"

            # 获取场景和边界
            scene = self.graph.viewer().scene()
            rect = QRectF()
            for node in self.graph.all_nodes():
                item_rect = node.view.sceneBoundingRect()
                rect = rect.united(item_rect)

            if rect.isEmpty():
                # 如果没有节点，创建一个空白图
                image = QImage(800, 600, QImage.Format_ARGB32)
                image.fill(Qt.white)
            else:
                # 扩展一点边距，避免裁剪
                rect.adjust(-100, -100, 90, 90)
                image = QImage(rect.size().toSize(), QImage.Format_ARGB32)
                image.fill(Qt.white)  # 背景设为白色（可选）

                painter = QPainter(image)
                # 将场景渲染到 QImage
                scene.render(painter, target=QRectF(image.rect()), source=rect)
                painter.end()

            # 保存图像
            image.save(png_path, "PNG")
            self.finished.emit(png_path)
        except Exception as e:
            logger.error(f"缩略图生成失败: {str(e)}")
            self.finished.emit("")


class WorkflowLoader(QThread):
    """异步加载工作流的线程类"""
    finished = pyqtSignal(dict, dict, dict, dict)  # graph_data, runtime_data, node_status_data

    def __init__(self, file_path, graph, node_uuid_map):
        super().__init__()
        self.file_path = file_path
        self.graph = graph
        self.node_uuid_map = node_uuid_map

    def run(self):
        """在后台线程中加载工作流"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                full_data = json.load(f)
            full_data = deserialize_from_json(full_data)

            graph_data = full_data.get("graph", {})
            runtime_data = full_data.get("runtime", {})
            global_variable = full_data.get("global_variable", {})
            # 准备节点状态数据
            node_status_data = {}
            nodes_data = graph_data.get("nodes", {})
            for index, (node_id, node_data) in enumerate(nodes_data.items()):
                node_type = node_data.get("type_", "")
                node_uuid = None
                if node_type in self.node_uuid_map.values():
                    for uuid, node_type_name in self.node_uuid_map.items():
                        if node_type_name == node_type:
                            node_uuid = uuid
                            break
                node_uuid = node_uuid or "unknown"
                node_name = node_data.get("name", "Unknown")
                stable_key = f"{node_uuid}||{node_name}"
                node_status_data[stable_key] = {
                    key: value.get(stable_key)
                    for key, value in runtime_data.items() if key not in ("environment", "environment_exe", "node_id2stable_key")
                }| {"custom_property": node_data.get("custom", {})}

            self.finished.emit(graph_data, runtime_data, node_status_data, global_variable)
        except Exception as e:
            traceback.print_exc()
            logger.error(f"工作流加载失败: {str(e)}")
            self.finished.emit({}, {}, {}, {})