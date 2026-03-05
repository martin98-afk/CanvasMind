import collections

from PyQt5 import QtCore

from app.widgets.custom_nodegraphqt.control_flow_item import ControlFlowBackdropNodeItem


class NodeLayoutHandler:
    @staticmethod
    def _get_connected_groups(nodes):
        """核心：通过拓扑连接将节点划分为独立的子图组"""
        if not nodes: return []
        node_set = set(nodes)
        visited = set()
        groups = []
        for node in nodes:
            if node in visited: continue
            group = []
            queue = collections.deque([node])
            visited.add(node)
            while queue:
                curr = queue.popleft()
                group.append(curr)
                neighbors = []
                # 遍历输入输出端口获取连接的节点
                if not hasattr(curr, 'inputs') or curr.inputs() is None: continue
                for port in curr.inputs().values():
                    neighbors.extend([p.node() for p in port.connected_ports()])
                for port in curr.outputs().values():
                    neighbors.extend([p.node() for p in port.connected_ports()])
                for n in neighbors:
                    if n in node_set and n not in visited:
                        visited.add(n)
                        queue.append(n)
            groups.append(group)
        return groups

    @staticmethod
    def align_nodes(graph, mode='left'):
        """智能对齐：分子图独立对齐，考虑节点视觉边界"""
        nodes = graph.selected_nodes()
        if len(nodes) < 2: return
        graph._undo_stack.beginMacro(f"Smart Align {mode}")
        groups = NodeLayoutHandler._get_connected_groups(nodes)

        for group in groups:
            if len(group) < 2: continue
            # 获取包含宽高信息的 rect 数据
            rects = [(n, n.pos(), n.view.boundingRect()) for n in group]

            if mode == 'left':
                target_x = min(r[1][0] for r in rects)
                for n, pos, _ in rects: n.set_pos(target_x, pos[1])
            elif mode == 'right':
                target_x = max(r[1][0] + r[2].width() for r in rects)
                for n, pos, r in rects: n.set_pos(target_x - r.width(), pos[1])
            elif mode == 'top':
                target_y = min(r[1][1] for r in rects)
                for n, pos, _ in rects: n.set_pos(pos[0], target_y)
            elif mode == 'bottom':
                target_y = max(r[1][1] + r[2].height() for r in rects)
                for n, pos, r in rects: n.set_pos(pos[0], target_y - r.height())
            elif mode == 'center_h':
                avg_y = sum(r[1][1] + r[2].height() / 2 for r in rects) / len(rects)
                for n, pos, r in rects: n.set_pos(pos[0], avg_y - r.height() / 2)
        graph._undo_stack.endMacro()

    @staticmethod
    def distribute_nodes(graph, direction='horizontal'):
        """
        智能化分布：核心优化！
        不再全选后统一分布，而是识别每个子图，在子图内部节点之间执行等距分布。
        """
        nodes = graph.selected_nodes()
        if not nodes: return
        graph._undo_stack.beginMacro(f"Smart Distribute {direction}")

        groups = NodeLayoutHandler._get_connected_groups(nodes)
        for group in groups:
            if len(group) < 3: continue  # 分布至少需要3个节点才有意义

            if direction == 'horizontal':
                # 按中心 X 坐标排序
                group.sort(key=lambda n: n.pos()[0] + n.view.boundingRect().width() / 2)
                start_x = group[0].pos()[0]
                end_x = group[-1].pos()[0]
                if start_x == end_x: continue

                step = (end_x - start_x) / (len(group) - 1)
                for i, n in enumerate(group):
                    n.set_pos(start_x + i * step, n.pos()[1])

            elif direction == 'vertical':
                # 按中心 Y 坐标排序
                group.sort(key=lambda n: n.pos()[1] + n.view.boundingRect().height() / 2)
                start_y = group[0].pos()[1]
                end_y = group[-1].pos()[1]
                if start_y == end_y: continue

                step = (end_y - start_y) / (len(group) - 1)
                for i, n in enumerate(group):
                    n.set_pos(n.pos()[0], start_y + i * step)

        graph._undo_stack.endMacro()

    @staticmethod
    def _resize_container_to_content(container_node, padding=(50, 80)):
        """
        根据内部节点的位置自动调整容器节点的大小和位置
        :param container_node: ControlFlowBackdrop 实例
        :param padding: (水平边距, 垂直边距) 垂直边距通常要大一些以容纳 Header
        """
        # 获取后端存储的子节点对象列表
        child_nodes = container_node.nodes()
        if not child_nodes:
            return

        # 计算子节点的包围盒
        min_x, min_y = float('inf'), float('inf')
        max_x, max_y = float('-inf'), float('-inf')

        for child in child_nodes:
            # 访问 View 获取几何信息
            pos = child.view.pos()
            rect = child.view.boundingRect()

            min_x = min(min_x, pos.x())
            min_y = min(min_y, pos.y())
            max_x = max(max_x, pos.x() + rect.width())
            max_y = max(max_y, pos.y() + rect.height())

        # 计算新的几何参数
        # 顶部预留更多空间给标题栏 (Header)
        header_height = 45.0

        new_x = min_x - padding[0]
        new_y = min_y - padding[1]
        new_w = (max_x - min_x) + (padding[0] * 2)
        new_h = (max_y - min_y) + padding[1] + padding[0]  # 底部加 padding[0] 保持对称

        # 应用到容器节点 Item
        # 注意：NodeGraphQt 的 node.set_pos 会触发信号，直接操作 view 可能更底层
        container_node.set_pos(new_x, new_y)

        # 调整大小 (BackdropNode 通常通过 view 的 width/height 属性控制)
        container_node.view.width = new_w
        container_node.view.height = new_h
        container_node.view.update()

    @staticmethod
    def auto_layout(graph, nodes=None, spacing=(100, 50)):
        """
        智能拓扑自动布局（支持递归容器与子图）
        :param graph: NodeGraph 对象
        :param nodes: 指定要布局的节点列表（Node对象），若为None则使用选中节点
        :param spacing: (水平间距, 垂直间距)
        """
        # 1. 确定操作目标节点
        target_nodes = nodes if nodes is not None else graph.selected_nodes()
        if not target_nodes: return

        # 仅在最顶层调用时开启 Undo 宏
        is_root_call = (nodes is None)
        if is_root_call:
            graph._undo_stack.beginMacro("Auto Layout Hierarchical")

        # =========================================
        # 第一步：处理容器节点（递归布局 + 自动缩放）
        # =========================================
        # 识别容器：这里检查是否有 nodes() 方法且不为空，或者基于类型判断
        # 建议 import 你的 ControlFlowBackdrop 类进行 isinstance 判断
        # from your_app import ControlFlowBackdrop

        # 这里为了通用，假设拥有 nodes() 方法的即为容器
        containers = [n for n in target_nodes if hasattr(n, 'nodes') and callable(n.nodes)]

        # 收集所有子节点 ID，用于稍后从当前层级排除
        all_internal_node_ids = set()

        for container in containers:
            # 获取内部节点 (Node Objects)
            internal_nodes = container.nodes()
            if not internal_nodes:
                continue

            # --- 递归核心 ---
            # 先对内部节点进行自动布局
            NodeLayoutHandler.auto_layout(graph, nodes=internal_nodes, spacing=spacing)

            # --- 自动适配 ---
            # 内部排好后，撑大容器
            NodeLayoutHandler._resize_container_to_content(container)

            # 记录 ID
            for child in internal_nodes:
                all_internal_node_ids.add(child.id)

        # =========================================
        # 第二步：准备当前层级的布局
        # =========================================
        # 排除掉那些已经被包含在容器内部的节点
        # 容器本身 (ControlFlowBackdrop) 会作为“大节点”参与当前层级排布
        layout_nodes = [n for n in target_nodes if n.id not in all_internal_node_ids]

        if not layout_nodes:
            if is_root_call: graph._undo_stack.endMacro()
            return

        # =========================================
        # 第三步：执行当前层级的拓扑布局
        # =========================================
        groups = NodeLayoutHandler._get_connected_groups(layout_nodes)

        # 按 Y 轴排序，保证视觉上的自上而下
        groups.sort(key=lambda g: min(n.pos()[1] for n in g))

        last_group_bottom = None

        for group in groups:
            # 记录当前组排布前的旧位置，用于计算位移 Delta
            # Key: Node Object, Value: (x, y)
            original_positions = {n: n.pos() for n in group}

            # --- 确定锚点 ---
            orig_x = min(n.pos()[0] for n in group)
            orig_y = min(n.pos()[1] for n in group)

            # 避让上一组
            if last_group_bottom is not None:
                if orig_y < last_group_bottom + spacing[1] * 2:
                    orig_y = last_group_bottom + spacing[1] * 2

            # --- 计算层级 (Level) ---
            node_to_level = {}

            def get_level(n):
                if n in node_to_level: return node_to_level[n]
                inputs = []
                if n.inputs() is None: return 0
                for port in n.inputs().values():
                    # 仅关注当前组内的连接
                    inputs.extend([p.node() for p in port.connected_ports() if p.node() in group])
                level = 0 if not inputs else max(get_level(i_n) for i_n in inputs) + 1
                node_to_level[n] = level
                return level

            levels = collections.defaultdict(list)
            for n in group:
                levels[get_level(n)].append(n)

            # --- 执行坐标设置 ---
            curr_x = orig_x
            current_group_max_y = orig_y

            for l in sorted(levels.keys()):
                level_nodes = levels[l]
                # 同一层级内按 Y 坐标排序
                level_nodes.sort(key=lambda x: x.pos()[1])

                curr_y = orig_y
                max_w = 0
                for n in level_nodes:
                    # 获取节点尺寸（如果是容器，此时已经是撑大后的尺寸了）
                    rect = n.view.boundingRect()

                    new_pos_x = curr_x
                    new_pos_y = curr_y

                    # 1. 设置节点新位置
                    n.set_pos(new_pos_x, new_pos_y)

                    # 2. 【关键】处理容器内子节点的跟随移动
                    # 自动布局是绝对定位，如果容器移动了，需要手动把子节点也移过去
                    if hasattr(n, 'nodes') and callable(n.nodes):
                        old_pos = original_positions[n]
                        delta_x = new_pos_x - old_pos[0]
                        delta_y = new_pos_y - old_pos[1]

                        # 如果有显著位移
                        if abs(delta_x) > 0.1 or abs(delta_y) > 0.1:
                            for child in n.nodes():
                                current_child_pos = child.pos()
                                child.set_pos(current_child_pos[0] + delta_x,
                                              current_child_pos[1] + delta_y)

                    # 更新布局游标
                    node_bottom = curr_y + rect.height()
                    if node_bottom > current_group_max_y:
                        current_group_max_y = node_bottom

                    curr_y += rect.height() + spacing[1]
                    max_w = max(max_w, rect.width())

                curr_x += max_w + spacing[0]

            last_group_bottom = current_group_max_y

        if is_root_call:
            graph._undo_stack.endMacro()

    @staticmethod
    def snap_to_grid(graph, grid_size=20):
        nodes = graph.selected_nodes()
        graph._undo_stack.beginMacro("Snap to Grid")
        for n in nodes:
            curr_pos = n.pos()
            n.set_pos(round(curr_pos[0] / grid_size) * grid_size, round(curr_pos[1] / grid_size) * grid_size)
        graph._undo_stack.endMacro()

    @staticmethod
    def toggle_nodes_collapse(graph):
        nodes = graph.selected_nodes()
        if not nodes: return
        target_state = sum(1 for n in nodes if n.view.is_collapsed) < (len(nodes) / 2)
        graph._undo_stack.beginMacro("Toggle Collapse")
        for n in nodes:
            if n.view.is_collapsed != target_state: n.view.toggle_collapse()
        graph._undo_stack.endMacro()