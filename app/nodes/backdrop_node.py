# -*- coding: utf-8 -*-
from collections import OrderedDict

from NodeGraphQt import BackdropNode, Port
from NodeGraphQt.base.commands import NodeVisibleCmd
from NodeGraphQt.constants import PortTypeEnum
from NodeGraphQt.errors import PortError
from PyQt5.QtWidgets import QUndoCommand
from qtpy import QtCore

from app.nodes.status_node import StatusNode
from app.utils.utils import draw_square_port, resource_path, topological_sort
from app.widgets.custom_nodegraphqt.custom_backdrop_item import ControlFlowBackdropNodeItem


# ──────────────── Undo/Redo Command ────────────────

class ResizeBackdropCommand(QUndoCommand):
    """支持撤销/重做的 backdrop 尺寸调整命令"""

    def __init__(self, backdrop, old_pos, old_size, new_pos, new_size, description="Resize Backdrop"):
        super().__init__(description)
        self.backdrop = backdrop
        self.old_pos = old_pos
        self.old_size = old_size
        self.new_pos = new_pos
        self.new_size = new_size

    def undo(self):
        self.backdrop.view.setPos(*self.old_pos)
        self.backdrop.view.width = self.old_size[0]
        self.backdrop.view.height = self.old_size[1]
        self.backdrop.view.update()

    def redo(self):
        self.backdrop.view.setPos(*self.new_pos)
        self.backdrop.view.width = self.new_size[0]
        self.backdrop.view.height = self.new_size[1]
        self.backdrop.view.update()


# ──────────────── Backdrop Node ────────────────

class ControlFlowBackdrop(BackdropNode, StatusNode):
    """
    支持控制流的增强型 Backdrop
    - 智能包含：需显著重叠 + 延迟确认
    - 自动移除完全脱离的节点
    - 支持 Undo/Redo
    """
    TYPE: str
    ICON_PATH: str
    category = "控制流"
    __identifier__ = 'control_flow'
    NODE_NAME = '控制流区域'
    FULL_PATH = f"{category}/{NODE_NAME}"

    def __init__(self):
        BackdropNode.__init__(self, ControlFlowBackdropNodeItem)
        self.set_icon(self.ICON_PATH)
        self._inputs = []
        self._outputs = []
        self._output_values = {}
        self._input_values = {}
        self._contained_nodes = set()  # 已确认包含的节点 ID
        self._pending_nodes = {}  # {node_id: QTimer} —— 待确认的节点
        self._overlap_threshold = 0.4  # 40% 重叠才视为“进入”
        self._confirm_delay_ms = 300  # 延迟 300ms 确认
        self._remove_threshold = 0.1  # <10% 视为“脱离”

        # === 优化新增内部变量 (不影响原有逻辑调用) ===
        self._is_manually_resizing = False  # 标记是否处于手动调整中
        self._resize_timer = QtCore.QTimer()  # 性能防抖定时器
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._perform_auto_resize_with_undo)

        # === 初始化端口 ===
        self.add_input("inputs", multi_input=True, display_name=True)
        self.add_output("outputs", display_name=True)

        # === 添加属性 ===
        self.model.add_property("current_index", 0)
        self.model.add_property("current_key", "")
        self.model.add_property("loop_nums", 5)
        self.model.add_property("max_iterations", 1000)
        self.model.add_property("loop_condition", "")
        self.model.add_property("loop_mode", "count")  # count, condition, while

        # 延迟初始化自动管理
        QtCore.QTimer.singleShot(0, self._setup_auto_management)

    def _setup_auto_management(self):
        if not self.graph:
            return

        # 连接 view 销毁信号
        try:
            self.view.destroyed.connect(self._on_view_destroyed)
        except AttributeError:
            pass

        scene = self.graph.scene()
        if scene and not hasattr(self, '_scene_connected'):
            try:
                scene.changed.connect(self._on_scene_changed)
                self._scene_connected = True
            except (TypeError, RuntimeError):
                pass

        self._perform_auto_resize_with_undo()

    def _on_view_destroyed(self):
        """清理所有 pending timers"""
        for timer in self._pending_nodes.values():
            timer.stop()
        self._pending_nodes.clear()
        if hasattr(self, '_resize_timer'):
            self._resize_timer.stop()

    def _on_scene_changed(self, region=None):
        """场景变化时动态管理节点归属"""
        if not self.graph:
            return

        # 优化：检查当前是否正在手动拉伸该 Backdrop，若是则跳过自动调整以免冲突
        if self.view.itemChange(self.view.ItemPositionChange, None) and self.view.isSelected():
            return

        # 清理已销毁节点的 pending timer
        for nid in list(self._pending_nodes.keys()):
            if self.graph.get_node_by_id(nid) is None:
                timer = self._pending_nodes.pop(nid)
                timer.stop()

        # 检查所有节点
        nodes_changed = False
        for node in self.graph.all_nodes():
            if node is self:
                continue

            is_significantly_inside = self._is_node_significantly_inside(node, self._overlap_threshold)

            if is_significantly_inside:
                if node.id not in self._pending_nodes and node.id not in self._contained_nodes:
                    timer = QtCore.QTimer()
                    timer.setSingleShot(True)
                    timer.timeout.connect(lambda nid=node.id: self._confirm_node_inclusion(nid))
                    self._pending_nodes[node.id] = timer
                    self._pending_nodes[node.id].start(self._confirm_delay_ms)
                    nodes_changed = True
                elif node.id in self._contained_nodes:
                    # 已经在内部的节点移动，也需要触发 resize 检查，但使用防抖
                    nodes_changed = True
            else:
                if node.id in self._pending_nodes:
                    self._pending_nodes[node.id].stop()
                    del self._pending_nodes[node.id]
                    nodes_changed = True

        # 如果有节点变动或在内部移动，启动防抖计时器
        if nodes_changed:
            self._resize_timer.start(50)  # 50ms 防抖，避免拖拽时卡顿

        # 检查是否需要移除已脱离的节点
        self._check_for_removals()

    def _is_node_significantly_inside(self, node, node_threshold=0.3, backdrop_threshold=0.2):
        if node.type_ in ("control_flow.CustomPortInputNode", "control_flow.CustomPortOutputNode"):
            return False

        backdrop_rect = self._get_backdrop_scene_rect()
        node_rect = self._get_node_scene_rect(node)

        # 优先级1：中心点判断 (最符合直觉)
        if backdrop_rect.contains(node_rect.center()):
            return True

        # 优先级2：交集面积
        intersect = backdrop_rect.intersected(node_rect)
        if intersect.isEmpty():
            return False

        overlap_area = intersect.width() * intersect.height()
        node_area = node_rect.width() * node_rect.height()

        # 只要节点有一半进入，或者 Backdrop 被节点填满
        if node_area > 0 and (overlap_area / node_area) >= node_threshold:
            return True

        return False

    def _confirm_node_inclusion(self, node_id):
        try:
            _ = self.view.scenePos()
        except RuntimeError:
            if node_id in self._pending_nodes:
                self._pending_nodes[node_id].stop()
                del self._pending_nodes[node_id]
            return

        if node_id in self._pending_nodes:
            del self._pending_nodes[node_id]

        node = self.graph.get_node_by_id(node_id)
        if not node:
            return

        if self._is_node_significantly_inside(node, self._overlap_threshold):
            self._contained_nodes.add(node_id)
            self._perform_auto_resize_with_undo()

    def _check_for_removals(self):
        """检查并移除已脱离的节点"""
        current_contained = set()
        removed_any = False
        for node in self._get_currently_contained_nodes():
            if (not self._is_node_significantly_inside(node, self._remove_threshold)
                    and node.id not in self._pending_nodes):
                self._remove_node_and_cleanup(node)
                removed_any = True
            else:
                current_contained.add(node)

        self._contained_nodes = {n.id for n in current_contained}
        if removed_any:
            self._resize_timer.start(50)

    def _perform_auto_resize_with_undo(self, padding=40, min_width=150, min_height=100):
        """执行带 undo 支持的自动 resize"""
        if not self.graph:
            return

        # 过滤有效节点
        nodes_to_include = []
        for node in self.graph.all_nodes():
            if node is self: continue
            if node.type_ in ("control_flow.CustomPortInputNode", "control_flow.CustomPortOutputNode"):
                continue
            if node.id in self._contained_nodes or self._is_node_significantly_inside(node, self._overlap_threshold):
                nodes_to_include.append(node)

        if not nodes_to_include:
            # 如果没有节点，保持最小尺寸或当前尺寸，不强行缩放
            return

        # 计算包围盒
        min_x = min(n.view.scenePos().x() for n in nodes_to_include)
        min_y = min(n.view.scenePos().y() for n in nodes_to_include)
        max_x = max(n.view.scenePos().x() + n.view.width for n in nodes_to_include)
        max_y = max(n.view.scenePos().y() + n.view.height for n in nodes_to_include)

        new_width = max(max_x - min_x + 2 * padding, min_width)
        new_height = max(max_y - min_y + 2 * padding, min_height)
        new_pos = (min_x - padding, min_y - padding)

        # 获取旧状态
        old_pos = (self.view.scenePos().x(), self.view.scenePos().y())
        old_size = (self.view.width, self.view.height)

        # 容差检查：变化小于2像素不触发撤销栈，防止噪音
        pos_changed = abs(old_pos[0] - new_pos[0]) > 2 or abs(old_pos[1] - new_pos[1]) > 2
        size_changed = abs(old_size[0] - new_width) > 2 or abs(old_size[1] - new_height) > 2

        if pos_changed or size_changed:
            command = ResizeBackdropCommand(
                self, old_pos, old_size, new_pos, (new_width, new_height)
            )
            self.graph.undo_stack().push(command)
            self.graph.viewer().force_update()

        # 同步 ID 记录
        self._contained_nodes = {n.id for n in nodes_to_include}

    # ──────────────── 几何辅助方法 ────────────────

    def _get_backdrop_scene_rect(self):
        try:
            pos = self.view.scenePos()
            return QtCore.QRectF(pos.x(), pos.y(), self.view.width, self.view.height)
        except RuntimeError:
            return QtCore.QRectF()

    def _get_node_scene_rect(self, node):
        pos = node.view.scenePos()
        return QtCore.QRectF(pos.x(), pos.y(), node.view.width, node.view.height)

    def _get_currently_contained_nodes(self):
        nodes = []
        for nid in list(self._contained_nodes):
            node = self.graph.get_node_by_id(nid)
            if node is not None:
                nodes.append(node)
        return nodes

    # ──────────────── 节点移除与清理 ────────────────

    def _remove_node_and_cleanup(self, node):
        if node.id not in self._contained_nodes:
            return

        self._contained_nodes.discard(node.id)

        input_proxy, output_proxy, _ = self.get_nodes()

        if input_proxy:
            for out_port in input_proxy.output_ports():
                for conn in list(out_port.connected_ports()):
                    if conn.node() == node:
                        out_port.disconnect_from(conn)

        if output_proxy:
            for in_port in output_proxy.input_ports():
                for conn in list(in_port.connected_ports()):
                    if conn.node() == node:
                        in_port.disconnect_from(conn)

    def set_property(self, name, value, push_undo=True):
        if self.get_property(name) == value:
            return

        if name == 'visible':
            if self.graph:
                undo_cmd = NodeVisibleCmd(self, value)
                if push_undo:
                    self.graph.undo_stack().push(undo_cmd)
                else:
                    undo_cmd.redo()
                return
        elif name == 'disabled':
            ports = self.view.inputs + self.view.outputs
            for port in ports:
                for pipe in port.connected_pipes:
                    pipe.update()
        super(BackdropNode, self).set_property(name, value, push_undo)

    def set_disabled(self, mode=False):
        self.set_property('disabled', mode)

    def nodes(self):
        return self._get_currently_contained_nodes()

    # ──────────────── 以下业务逻辑保持完全不变 ────────────────

    def get_nodes(self):
        execute_nodes = []
        input_proxy, output_proxy = None, None
        for node in self.nodes():
            if node.type_ == "control_flow.ControlFlowInputPort":
                input_proxy = node
            elif node.type_ == "control_flow.ControlFlowOutputPort":
                output_proxy = node
            else:
                execute_nodes.append(node)
        return input_proxy, output_proxy, topological_sort(execute_nodes)

    def add_input(self, name='input', multi_input=False, display_name=True, color=None, locked=False,
                  painter_func=None):
        if name in self.inputs().keys():
            raise ValueError(f'输入端口 "{name}" 已存在')
        view = self.view.add_input(name, multi_input, display_name, locked, painter_func=draw_square_port)
        if color:
            view.color = color
            view.border_color = [min(255, max(0, i + 80)) for i in color]
        port = Port(self, view)
        port.model.type_ = PortTypeEnum.IN.value
        port.model.name = name
        port.model.display_name = display_name
        port.model.multi_connection = multi_input
        port.model.locked = locked
        self._inputs.append(port)
        self.model.inputs[port.name()] = port.model
        return port

    def add_output(self, name='output', multi_output=True, display_name=True, color=None, locked=False,
                   painter_func=None):
        if name in self.outputs().keys():
            raise ValueError(f'输出端口 "{name}" 已存在')
        view = self.view.add_output(name, multi_output, display_name, locked)
        if color:
            view.color = color
            view.border_color = [min(255, max(0, i + 80)) for i in color]
        port = Port(self, view)
        port.model.type_ = PortTypeEnum.OUT.value
        port.model.name = name
        port.model.display_name = display_name
        port.model.multi_connection = multi_output
        port.model.locked = locked
        self._outputs.append(port)
        self.model.outputs[port.name()] = port.model
        return port

    def connected_output_nodes(self):
        nodes = OrderedDict()
        for p in self.output_ports():
            nodes[p] = [cp.node() for cp in p.connected_ports()]
        return nodes

    def input_ports(self):
        return self._inputs

    def output_ports(self):
        return self._outputs

    def inputs(self):
        return {p.name(): p for p in self._inputs}

    def outputs(self):
        return {p.name(): p for p in self._outputs}

    def accepted_port_types(self, port):
        ports = self._inputs + self._outputs
        if port not in ports: raise PortError('Node does not contain port "{}"'.format(port))
        return self.graph.model.port_accept_connection_types(self.type_, port.type_(), port.name())

    def rejected_port_types(self, port):
        ports = self._inputs + self._outputs
        if port not in ports: raise PortError('Node does not contain port "{}"'.format(port))
        return self.graph.model.port_reject_connection_types(self.type_, port.type_(), port.name())

    def on_input_connected(self, in_port, out_port):
        pass

    def on_input_disconnected(self, in_port, out_port):
        pass

    def set_output_value(self, value):
        self._output_values = {self._outputs[0].name(): value}

    def get_output_value(self, name):
        return self._output_values.get(name) if self._output_values else None

    def get_input(self, port):
        if isinstance(port, int): return self._inputs[port] if port < len(self._inputs) else None
        return self.inputs().get(port)

    def get_output(self, port):
        if isinstance(port, int): return self._outputs[port] if port < len(self._outputs) else None
        return self.outputs().get(port)

    def set_icon(self, icon=None):
        self.set_property('icon', icon)


class ControlFlowLoopNode(ControlFlowBackdrop):
    category = "控制流"
    NODE_NAME = "循环控制流区域"
    TYPE = "loop"
    FULL_PATH = f"{category}/{NODE_NAME}"
    ICON_PATH = ":/icons/无限"


class ControlFlowIterateNode(ControlFlowBackdrop):
    category = "控制流"
    NODE_NAME = "迭代控制流区域"
    TYPE = "iterate"
    FULL_PATH = f"{category}/{NODE_NAME}"
    ICON_PATH = ":/icons/更新"