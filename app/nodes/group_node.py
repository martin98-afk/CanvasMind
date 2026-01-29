# -*- coding: utf-8 -*-
from NodeGraphQt import GroupNode
from NodeGraphQt.qgraphics.node_group import GroupNodeItem
from PyQt5 import QtCore, QtGui

from app.nodes.backdrop_node import ControlFlowBackdrop


# def create_group_node_class(graph, parent_window):
#
#     class CustomGroupNode(GroupNode):
#         __identifier__ = 'general'
#         NODE_NAME = 'GroupNode'
#
#         def __init__(self):
#             super(CustomGroupNode, self).__init__(qgraphics_item=GroupNodeItem)
#             self.set_color(50, 50, 50)  # 设置一个深色背景
#
#     return CustomGroupNode


class CustomGroupNode(ControlFlowBackdrop):
    """
    仿 ComfyUI 组节点
    - 包含 ControlFlowBackdrop 的所有自动吸附功能
    - 增加折叠逻辑
    - 增加端口动态管理菜单
    """
    __identifier__ = 'control_flow.GroupNode'
    NODE_NAME = 'Group'

    # 强制指定 View 类
    def __init__(self):
        # 这里的 super 调用很关键，它会初始化 ControlFlowBackdrop 的逻辑
        # 但是我们需要传入我们新的 GroupNodeItem
        super(ControlFlowBackdrop, self).__init__(GroupNodeItem)

        # 初始化 ControlFlowBackdrop 特有的属性
        self.set_icon(":/icons/folder.png")  # 假设有个文件夹图标
        self._is_collapsed = False
        self._expanded_geometry = (300, 300)  # 记录展开时的宽及高
        self._preview_path = None

        # 初始化端口 (Group 默认可能有一对端口)
        # self.add_input("in")
        # self.add_output("out")

        # 延迟初始化自动管理 (复用父类逻辑)
        QtCore.QTimer.singleShot(0, self._setup_auto_management)

    def on_view_created(self):
        """当 View 创建后，设置右键菜单"""
        # NodeGraphQt 允许通过 context menu 添加动作
        self.add_context_menu_action("Toggle Collapse", self.toggle_collapse)
        self.add_context_menu_action("Add Input Port", self.add_custom_input)
        self.add_context_menu_action("Add Output Port", self.add_custom_output)

    # --- 核心状态切换 ---

    def toggle_collapse(self):
        """切换折叠/展开状态"""
        self._is_collapsed = not self._is_collapsed

        # 1. 获取 View
        if not self.view: return

        scene = self.graph.scene()

        if self._is_collapsed:
            # === 执行折叠 ===
            # 记录当前尺寸
            self._expanded_geometry = (self.view.width, self.view.height)

            # 隐藏内部节点
            self._set_inner_nodes_visible(False)

            # 缩小自身 (设置为标准节点大小)
            self.view.width = 220
            self.view.height = 180

            # 强制更新 Item 状态 (显示预览图)
            pixmap = QtGui.QPixmap(self._preview_path) if self._preview_path else None
            self.view.set_collapsed_state(True, pixmap)

        else:
            # === 执行展开 ===
            # 恢复尺寸
            w, h = self._expanded_geometry
            self.view.width = w
            self.view.height = h

            # 显示内部节点
            self._set_inner_nodes_visible(True)

            # 更新 Item 状态
            self.view.set_collapsed_state(False)

            # 触发一次自动对齐以确保包含完整
            self._perform_auto_resize_with_undo()

    def _set_inner_nodes_visible(self, visible):
        """批量设置内部节点的可见性"""
        for node_id in self._contained_nodes:
            node = self.graph.get_node_by_id(node_id)
            if node:
                node.set_property('visible', visible)
                # 处理连接线：NodeGraphQt 会自动处理节点隐藏时的连线显示
                # 但如果为了视觉更完美，可以遍历 pipe 强制更新
                for port in node.input_ports() + node.output_ports():
                    for pipe in port.connected_pipes():
                        if visible:
                            pipe.show()
                        else:
                            # 只有当连接的目标也在组内时才完全隐藏？
                            # 通常隐藏节点后，Pipe 会自动隐藏或变淡
                            pass

    def set_preview_image(self, file_path):
        """设置预览图路径"""
        self._preview_path = file_path
        if self._is_collapsed and self.view:
            self.view.set_collapsed_state(True, QtGui.QPixmap(file_path))

    # --- 覆盖父类逻辑以保护折叠状态 ---

    def _perform_auto_resize_with_undo(self, padding=40, min_width=150, min_height=100):
        """覆写：如果处于折叠状态，禁止自动调整大小"""
        if self._is_collapsed:
            return
        super(GroupNode, self)._perform_auto_resize_with_undo(padding, min_width, min_height)

    def _check_for_removals(self):
        """覆写：如果处于折叠状态，禁止检测节点移除"""
        if self._is_collapsed:
            return
        super(GroupNode, self)._check_for_removals()

    def _on_scene_changed(self, region=None):
        """覆写：折叠时不响应场景变化"""
        if self._is_collapsed:
            return
        super(GroupNode, self)._on_scene_changed(region)

    # --- 端口动态添加 (ComfyUI 风格) ---

    def add_custom_input(self):
        """菜单回调：添加输入"""
        # 简单的弹窗让用户输入名称，或者自动命名
        # 这里简化为自动命名
        idx = len(self.input_ports())
        name = f"in_{idx}"
        self.add_input(name, multi_input=True)

    def add_custom_output(self):
        """菜单回调：添加输出"""
        idx = len(self.output_ports())
        name = f"out_{idx}"
        self.add_output(name, multi_output=True)