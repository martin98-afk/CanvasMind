import os
import os
import traceback
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal, Qt, QRectF, pyqtSlot, QEventLoop
from PyQt5.QtGui import QImage, QPainter
from PyQt5.QtWidgets import QApplication, QGraphicsProxyWidget, QLabel, QProgressDialog

from app.scan_components import ComponentScanner
from .logger import get_logger
from .utils import WorkflowLoader, SaveTask, FinishLoadingWorker, FinishLoadingTask
from ..widgets.message_manager import MessageManager
from ..widgets.progress_overlay import ModernProgressOverlay

logger = get_logger("CanvasIO")


# ────────────────────────────────
# 主类：CanvasIO
# ────────────────────────────────
class CanvasIO(QObject):
    canvas_saved = pyqtSignal(Path)
    canvas_loaded = pyqtSignal(object)

    def __init__(self, graph, global_variables, parent):
        super().__init__(parent)
        self.canvas_env = None
        self.graph = graph
        self.global_variables = global_variables
        self.parent = parent
        self.node_status = parent.node_status
        self._save_progress = None  # 保存进度的遮罩引用

    def save_full_workflow(self, file_path, show_info=True):
        """
        优化后的保存流程：
        1. 主线程：提取数据 (Data Extraction)
        2. 子线程：序列化与写入 (Serialization & IO)
        3. 主线程：生成缩略图并提示 (Callback)
        """
        logger.info(f"开始准备保存数据: {file_path}")

        # [步骤1] 主线程提取数据
        # 必须在主线程执行，因为涉及访问 QGraphicsItem 等 UI 对象
        try:
            QApplication.processEvents()  # 强制刷新一下UI显示遮罩

            graph_data = self.graph.serialize_session()
            for node_data in graph_data["nodes"].values():
                node_data["custom"].pop("global_variable", None)

            runtime = {
                "environment": self.parent.environment_manager.env_combo.currentData(),
                "environment_exe": self.parent.environment_manager.get_current_python_exe(),
                "node_id2stable_key": {},
                "node_states": {},
                "node_inputs": {},
                "node_outputs": {},
                "column_select": {}
            }

            # 这一步循环通常很快，除非节点成千上万，否则不需要移出
            for node in self.graph.all_nodes():
                node_comp_cls = ComponentScanner().get_component(getattr(node, 'FULL_PATH', 'unknown'))
                stable_key = f"{node_comp_cls.uuid}||{node.name()}" if node_comp_cls else f"unknown||{node.name()}"
                runtime["node_id2stable_key"][node.id] = stable_key
                runtime["node_states"][stable_key] = self.node_status.get(node.id, "unrun")

                # 这里的 _input_values 可能很大，但这里只是引用传递，很快
                runtime["node_inputs"][stable_key] = getattr(node, '_input_values', {})
                runtime["node_outputs"][stable_key] = getattr(node, '_output_values', {})
                runtime["column_select"][stable_key] = getattr(node, 'column_select', {})

            full_data = {
                "version": "1.0",
                "graph": graph_data,
                "runtime": runtime,
                "global_variable": self.global_variables.serialize()
            }

        except Exception as e:
            if self._save_progress:
                self._save_progress.close()
            logger.error(f"保存前数据准备失败: {e}")
            MessageManager.error("保存失败", f"数据准备错误: {e}", self.parent)
            return

        # [步骤2] 启动子线程进行 JSON 序列化和 IO
        save_task = SaveTask(file_path, full_data)
        # 传递 show_info 参数给回调
        save_task.signals.finished.connect(lambda: self._on_save_finished(file_path, show_info))
        save_task.signals.error.connect(self._on_save_error)

        # 启动线程池
        self.parent.thread_pool.start(save_task)

    @pyqtSlot(str, bool)
    def _on_save_finished(self, file_path, show_info):
        """保存成功后的回调（主线程）"""
        try:
            # [步骤3] 生成缩略图 (必须在主线程，因为涉及 render)
            # 此时文件已保存完毕，UI 仍然被遮罩锁住
            self.do_generate_thumbnail(file_path)

            if show_info:
                MessageManager.success("保存成功", "工作流保存成功！", self.parent)

        except Exception as e:
            logger.error(f"保存后处理失败: {e}")
        finally:
            if self._save_progress:
                self._save_progress.close()
                self._save_progress = None

    @pyqtSlot(str)
    def _on_save_error(self, error_msg):
        """保存失败的回调"""
        if self._save_progress:
            self._save_progress.close()
            self._save_progress = None
        MessageManager.error("保存失败", f"写入文件错误: {error_msg}", self.parent)

    def do_generate_thumbnail(self, workflow_path):
        """在主线程中安全生成缩略图"""
        scene = self.graph.viewer().scene()
        chart_widgets_backup = {}

        try:
            # 临时替换复杂的控件为占位符，避免截图时崩溃或渲染错误
            for node in self.graph.all_nodes():
                if node.model.type_.startswith("visualize"):
                    view = node.view
                    for item in view.childItems():
                        if isinstance(item, QGraphicsProxyWidget):
                            proxy = item
                            original_widget = proxy.widget()
                            # 简单的 duck typing 检查
                            if original_widget and hasattr(original_widget, 'view'):
                                placeholder = QLabel("[图表预览]")
                                placeholder.setAlignment(Qt.AlignCenter)
                                placeholder.setStyleSheet("background: #2a2a2a; color: #aaa; border: 1px solid #444;")
                                chart_widgets_backup[proxy] = original_widget
                                proxy.setWidget(placeholder)

            # 计算包围盒
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
        finally:
            # 恢复原始控件
            for proxy, original_widget in chart_widgets_backup.items():
                proxy.setWidget(original_widget)

    def _on_thumbnail_generated(self, png_path):
        if png_path:
            logger.info(f"✅ 预览图已保存: {png_path}")
            self.parent.canvas_saved.emit(self.parent.file_path)

    # ────────────────────────────────
    # 加载逻辑保持原样，或者你也可以在这里做同样的优化
    # ────────────────────────────────
    def load_full_workflow(self, file_path):
        self.workflow_loader = WorkflowLoader(file_path, self.graph, self.parent.node_uuid_map)
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

            # ─────────────────────────────────────────────────────────────
            # 修改点 1：替换为你的 ModernProgressOverlay
            # ─────────────────────────────────────────────────────────────
            progress = ModernProgressOverlay(self.parent)
            progress.set_maximum(total_nodes)  # 设置最大值
            progress.set_text("正在加载节点...")

            # 设置为模态，防止用户点到底下的窗口（和原版 setWindowModality(Qt.WindowModal) 一样）
            progress.setWindowModality(Qt.WindowModal)
            progress.show()

            # 强制立即把进度条画出来，防止刚开始是个白框
            QApplication.processEvents()
            # ─────────────────────────────────────────────────────────────

            original_add_node = self.graph.add_node
            # 使用列表保持引用，和你原代码一致
            count = [0]

            def patched_add_node(node, pos=None, inherite_graph_style=True):
                # 执行原始添加逻辑
                result = original_add_node(node, pos, False, False, inherite_graph_style)

                count[0] += 1

                # ─────────────────────────────────────────────────────────────
                # 修改点 2：更新自定义控件并强制刷新
                # ─────────────────────────────────────────────────────────────
                progress.set_value(count[0])
                progress.set_text(f"正在加载节点 ({count[0]}/{total_nodes})...")  # 可选：更新文字

                # 【核心】自定义控件不像原生控件那么智能，
                # 如果 processEvents 不够，repaint() 是强制命令：“现在立刻重绘自己，别等了”
                progress.repaint()

                # 你的原版代码里就有这句，这句非常重要，千万保留！
                # 它让界面主循环有机会去处理上面的 repaint 请求
                QApplication.processEvents()
                # ─────────────────────────────────────────────────────────────

                return result

            self.graph.add_node = patched_add_node
            try:
                self.graph.deserialize_session(graph_data)
            finally:
                self.graph.add_node = original_add_node
                progress.close()  # 关闭自定义进度条

            self._start_finish_loading(runtime_data, node_status_data)

        except Exception as e:
            logger.error(f"❌ 加载失败: {traceback.format_exc()}")
            MessageManager.error("加载失败", f"工作流加载失败: {str(e)}", self.parent)
            # 确保异常时进度条也能关掉
            if 'progress' in locals():
                progress.close()

    def _start_finish_loading(self, runtime_data, node_status_data):
        worker = FinishLoadingWorker()
        worker.finished.connect(self._on_finish_loading_in_main_thread)

        task = FinishLoadingTask(
            graph=self.graph,
            runtime_data=runtime_data,
            node_status_data=node_status_data,
            worker=worker
        )
        task.setAutoDelete(True)
        # 必须持有引用，否则 signals 可能会在槽函数执行前被垃圾回收
        task.worker_ref = worker

        self.parent.thread_pool.start(task)

    @pyqtSlot(object, object)
    def _on_finish_loading_in_main_thread(self, restored_data, target_env):
        if restored_data is None:
            MessageManager.error("加载失败", "工作流后处理失败！", self.parent)
            return

        # --- 主线程 UI 更新 ---
        self.canvas_loaded.emit(target_env)
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
            # 每次加载时把上次成功的节点设置为枯黄色，用于区分
            if status_enum == NodeStatus.NODE_STATUS_SUCCESS:
                status_enum = NodeStatus.NODE_STATUS_LAST_SUCCESS
            self.node_status[node.id] = status_enum
            if hasattr(node, 'status'):
                node.status = status_enum

        self.parent._node_id_cache = {node.id: node for node in self.graph.all_nodes()}
        self.parent._node_id_cache_valid = True
        self.parent.create_name_label()
        self.parent._delayed_fit_view()
        MessageManager.success("加载成功", "工作流加载成功！", self.parent)