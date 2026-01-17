import json
import os
import time
import traceback
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal, QTimer, Qt, QRectF, QRunnable, pyqtSlot
from PyQt5.QtGui import QImage, QPainter
from PyQt5.QtWidgets import QProgressDialog, QApplication, QGraphicsProxyWidget, QLabel

from app.scan_components import ComponentScanner
from app.utils.utils import serialize_for_json, deserialize_from_json
from .logger import get_logger
from .utils import WorkflowLoader
from ..widgets.message_manager import MessageManager

logger = get_logger("CanvasIO")


# ────────────────────────────────
# 辅助类：用于在线程间传递结果
# ────────────────────────────────
class FinishLoadingWorker(QObject):
    finished = pyqtSignal(object, object)  # (restored_data: dict | None, target_env: str | None)


class FinishLoadingTask(QRunnable):
    def __init__(self, graph, runtime_data, node_status_data, env_manager, worker: FinishLoadingWorker):
        super().__init__()
        self.graph = graph
        self.runtime_data = runtime_data
        self.node_status_data = node_status_data
        self.env_manager = env_manager
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
                column_select = ns.get("column_select", {}) or {}
                status_str = ns.get("node_states", "unrun") or "unrun"

                input_vals = deserialize_from_json(node_inputs)
                output_vals = deserialize_from_json(node_outputs)

                restored[node.id] = {
                    "input_values": input_vals,
                    "output_values": output_vals,
                    "column_select": column_select,
                    "status_str": status_str,
                }

            self.worker.finished.emit(restored, target_env)

        except Exception as e:
            logger.error(f"FinishLoadingTask failed: {traceback.format_exc()}")
            self.worker.finished.emit(None, None)


# ────────────────────────────────
# 主类：CanvasIO
# ────────────────────────────────
class CanvasIO(QObject):
    canvas_saved = pyqtSignal(Path)

    def __init__(self, graph, env_manager, global_variables, parent):
        super().__init__(parent)
        self.graph = graph
        self.env_manager = env_manager
        self.global_variables = global_variables
        self.parent = parent
        self.node_status = parent.node_status

    def save_full_workflow(self, file_path, show_info=True):
        graph_data = self.graph.serialize_session()
        for node_data in graph_data["nodes"].values():
            node_data["custom"].pop("global_variable", None)

        runtime = {
            "environment": self.env_manager.env_combo.currentData(),
            "environment_exe": self.env_manager.get_current_python_exe(),
            "node_id2stable_key": {},
            "node_states": {},
            "node_inputs": {},
            "node_outputs": {},
            "column_select": {}
        }
        for node in self.graph.all_nodes():
            node_comp_cls = ComponentScanner().get_component(getattr(node, 'FULL_PATH', 'unknown'))
            stable_key = f"{node_comp_cls.uuid}||{node.name()}" if node_comp_cls else f"unknown||{node.name()}"
            runtime["node_id2stable_key"][node.id] = stable_key
            runtime["node_states"][stable_key] = self.node_status.get(node.id, "unrun")
            runtime["node_inputs"][stable_key] = getattr(node, '_input_values', {})
            runtime["node_outputs"][stable_key] = getattr(node, '_output_values', {})
            runtime["column_select"][stable_key] = getattr(node, 'column_select', {})

        full_data = {
            "version": "1.0",
            "graph": graph_data,
            "runtime": runtime,
            "global_variable": self.global_variables.serialize()
        }
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        time.sleep(0.1)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(serialize_for_json(full_data), f, indent=2, ensure_ascii=False)

        QTimer.singleShot(100, lambda: self.do_generate_thumbnail(file_path))
        if show_info:
            MessageManager.success("保存成功", "工作流保存成功！", self.parent)

    def do_generate_thumbnail(self, workflow_path):
        """在主线程中安全生成缩略图（临时替换 WebEngineView）"""

        scene = self.graph.viewer().scene()
        chart_widgets_backup = {}

        try:
            for node in self.graph.all_nodes():
                if node.model.type_.startswith("visualize"):
                    view = node.view
                    for item in view.childItems():
                        if isinstance(item, QGraphicsProxyWidget):
                            proxy = item
                            original_widget = proxy.widget()
                            if original_widget and hasattr(original_widget, 'view') and hasattr(original_widget.view, 'page'):
                                placeholder = QLabel("[图表预览]")
                                placeholder.setAlignment(Qt.AlignCenter)
                                placeholder.setStyleSheet("""
                                    background: #2a2a2a;
                                    color: #aaa;
                                    border: 1px solid #444;
                                """)
                                chart_widgets_backup[proxy] = original_widget
                                proxy.setWidget(placeholder)

            rect = QRectF()
            for node in self.graph.all_nodes():
                item_rect = node.view.sceneBoundingRect()
                rect = rect.united(item_rect)

            if rect.isEmpty():
                image = QImage(800, 600, QImage.Format_ARGB32)
                image.fill(Qt.white)
            else:
                rect.adjust(-100, -100, 90, 90)
                image = QImage(rect.size().toSize(), QImage.Format_ARGB32)
                image.fill(Qt.white)
                painter = QPainter(image)
                scene.render(painter, target=QRectF(image.rect()), source=rect)
                painter.end()

            base_name = os.path.splitext(os.path.splitext(workflow_path)[0])[0]
            png_path = base_name + ".png"
            image.save(png_path, "PNG")
            self._on_thumbnail_generated(png_path)

        except Exception as e:
            logger.error(f"缩略图生成失败: {e}")
            return ""
        finally:
            for proxy, original_widget in chart_widgets_backup.items():
                proxy.setWidget(original_widget)

    def _on_thumbnail_generated(self, png_path):
        if png_path:
            logger.info(f"✅ 预览图已保存: {png_path}")
            self.parent.canvas_saved.emit(self.parent.file_path)

    def load_full_workflow(self, file_path):
        self.workflow_loader = WorkflowLoader(file_path, self.graph, self.parent.node_type_map)
        self.workflow_loader.finished.connect(
            lambda gd, rd, ns, gv: self._on_workflow_loaded(gd, rd, ns, gv))
        self.workflow_loader.start()

    def _on_workflow_loaded(self, graph_data, runtime_data, node_status_data, global_variable):
        try:
            self.global_variables.deserialize(global_variable)
            nodes_data = graph_data.get("nodes", {})
            total_nodes = len(nodes_data)
            if total_nodes == 0:
                self.graph.deserialize_session(graph_data)
                self._start_finish_loading(runtime_data, node_status_data)
                return

            progress = QProgressDialog("正在加载节点...", "取消", 0, total_nodes, self.parent)
            progress.setWindowModality(Qt.WindowModal)
            progress.setWindowTitle("加载中")
            progress.setCancelButton(None)
            progress.setAutoClose(True)
            progress.setMinimumDuration(0)
            progress.setValue(0)

            original_add_node = self.graph.add_node
            count = [0]

            def patched_add_node(node, pos=None, inherite_graph_style=True):
                result = original_add_node(node, pos, False, False, inherite_graph_style)
                count[0] += 1
                progress.setValue(count[0])
                QApplication.processEvents()
                return result

            self.graph.add_node = patched_add_node
            try:
                self.graph.deserialize_session(graph_data)
            finally:
                self.graph.add_node = original_add_node
                progress.close()

            self._start_finish_loading(runtime_data, node_status_data)
        except Exception as e:
            logger.error(f"❌ 加载失败: {traceback.format_exc()}")
            MessageManager.error("加载失败", f"工作流加载失败: {str(e)}", self.parent)

    def _start_finish_loading(self, runtime_data, node_status_data):
        worker = FinishLoadingWorker()
        worker.finished.connect(self._on_finish_loading_in_main_thread)

        task = FinishLoadingTask(
            graph=self.graph,
            runtime_data=runtime_data,
            node_status_data=node_status_data,
            env_manager=self.env_manager,
            worker=worker
        )
        task.setAutoDelete(True)
        task.worker_ref = worker  # 防止 worker 被 GC

        self.parent.thread_pool.start(task)

    @pyqtSlot(object, object)
    def _on_finish_loading_in_main_thread(self, restored_data, target_env):
        if restored_data is None:
            MessageManager.error("加载失败", "工作流后处理失败！", self.parent)
            return

        # --- 主线程 UI 更新 ---
        if target_env:
            for i in range(self.env_manager.env_combo.count()):
                if self.env_manager.env_combo.itemData(i) == target_env:
                    self.env_manager.env_combo.setCurrentIndex(i)
                    break

        from app.nodes.status_node import NodeStatus
        for node in self.graph.all_nodes():
            data = restored_data.get(node.id)
            if not data:
                continue
            node._input_values = data["input_values"]
            node._output_values = data["output_values"]
            node.column_select = data["column_select"]
            status_str = data["status_str"]
            status_enum = getattr(NodeStatus, f"NODE_STATUS_{status_str.upper()}", NodeStatus.NODE_STATUS_UNRUN)
            self.node_status[node.id] = status_enum
            if hasattr(node, 'status'):
                node.status = status_enum

        self.parent._node_id_cache = {node.id: node for node in self.graph.all_nodes()}
        self.parent._node_id_cache_valid = True
        self.parent.create_name_label()
        self.parent._delayed_fit_view()
        MessageManager.success("加载成功", "工作流加载成功！", self.parent)