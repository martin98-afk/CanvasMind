import json
import traceback
import os

from PyQt5.QtCore import pyqtSignal, QThread, QRectF, Qt
from PyQt5.QtGui import QPainter, QImage
from loguru import logger
from app.scan_components import ComponentScanner
from app.utils.utils import deserialize_from_json


def get_node_uuid(full_path: str) -> str:
    node_comp_cls = ComponentScanner().get_component(full_path)
    if node_comp_cls:
        return node_comp_cls.uuid
    else:
        return "unknown"


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