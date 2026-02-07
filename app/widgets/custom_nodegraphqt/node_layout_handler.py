import collections


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
    def auto_layout(graph, spacing=(100, 50)):
        """智能拓扑自动布局：基于层级感知的全自动整理"""
        nodes = graph.selected_nodes()
        if not nodes: return
        graph._undo_stack.beginMacro("Auto Layout Flow")
        groups = NodeLayoutHandler._get_connected_groups(nodes)

        current_y_offset = 0
        for group in groups:
            node_to_level = {}

            def get_level(n):
                if n in node_to_level: return node_to_level[n]
                inputs = []
                for port in n.inputs().values():
                    inputs.extend([p.node() for p in port.connected_ports() if p.node() in group])
                level = 0 if not inputs else max(get_level(i_n) for i_n in inputs) + 1
                node_to_level[n] = level
                return level

            levels = collections.defaultdict(list)
            for n in group: levels[get_level(n)].append(n)

            curr_x = 0
            group_top = current_y_offset
            for l in sorted(levels.keys()):
                level_nodes = levels[l]
                curr_y = group_top
                max_w = 0
                for n in level_nodes:
                    rect = n.view.boundingRect()
                    n.set_pos(curr_x, curr_y)
                    curr_y += rect.height() + spacing[1]
                    max_w = max(max_w, rect.width())
                curr_x += max_w + spacing[0]

            # 为下一个子图计算垂直偏移，防止重叠
            group_bottom = max(n.pos()[1] + n.view.boundingRect().height() for n in group)
            current_y_offset = group_bottom + spacing[1] * 2

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