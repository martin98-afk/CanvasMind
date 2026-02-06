class NodeLayoutHandler:
    @staticmethod
    def get_selected_nodes(graph):
        return graph.selected_nodes()

    @staticmethod
    def align_nodes(graph, mode='left'):
        nodes = graph.selected_nodes()
        if len(nodes) < 2: return
        
        # 记录撤销操作
        graph._undo_stack.beginMacro(f"Align Nodes {mode}")
        
        # 获取所有坐标
        positions = [n.pos() for n in nodes]
        
        if mode == 'left':
            target_x = min(p[0] for p in positions)
            for n in nodes: n.set_pos(target_x, n.pos()[1])
        elif mode == 'right':
            # 注意：右对齐通常要考虑节点宽度
            target_x = max(n.pos()[0] + n.view.boundingRect().width() for n in nodes)
            for n in nodes: 
                new_x = target_x - n.view.boundingRect().width()
                n.set_pos(new_x, n.pos()[1])
        elif mode == 'top':
            target_y = min(p[1] for p in positions)
            for n in nodes: n.set_pos(n.pos()[0], target_y)
        elif mode == 'bottom':
            target_y = max(n.pos()[1] + n.view.boundingRect().height() for n in nodes)
            for n in nodes:
                new_y = target_y - n.view.boundingRect().height()
                n.set_pos(n.pos()[0], new_y)
        elif mode == 'center_h': # 水平居中
            center_y = sum(p[1] + n.view.boundingRect().height()/2 for n, p in zip(nodes, positions)) / len(nodes)
            for n in nodes:
                n.set_pos(n.pos()[0], center_y - n.view.boundingRect().height()/2)

        graph._undo_stack.endMacro()

    @staticmethod
    def distribute_nodes(graph, direction='horizontal'):
        nodes = graph.selected_nodes()
        if len(nodes) < 3: return
        
        graph._undo_stack.beginMacro(f"Distribute Nodes {direction}")
        
        if direction == 'horizontal':
            # 按 X 坐标排序
            nodes.sort(key=lambda n: n.pos()[0])
            start_x = nodes[0].pos()[0]
            end_node = nodes[-1]
            end_x = end_node.pos()[0]
            
            # 计算总间距
            total_width = end_x - start_x
            step = total_width / (len(nodes) - 1)
            
            for i, n in enumerate(nodes):
                n.set_pos(start_x + (i * step), n.pos()[1])
                
        elif direction == 'vertical':
            nodes.sort(key=lambda n: n.pos()[1])
            start_y = nodes[0].pos()[1]
            end_y = nodes[-1].pos()[1]
            step = (end_y - start_y) / (len(nodes) - 1)
            for i, n in enumerate(nodes):
                n.set_pos(n.pos()[0], start_y + (i * step))
                
        graph._undo_stack.endMacro()

    @staticmethod
    def snap_to_grid(graph, grid_size=20):
        nodes = graph.selected_nodes()
        graph._undo_stack.beginMacro("Snap to Grid")
        for n in nodes:
            curr_pos = n.pos()
            snapped_x = round(curr_pos[0] / grid_size) * grid_size
            snapped_y = round(curr_pos[1] / grid_size) * grid_size
            n.set_pos(snapped_x, snapped_y)
        graph._undo_stack.endMacro()

    @staticmethod
    def toggle_nodes_collapse(graph):
        nodes = graph.selected_nodes()
        if not nodes: return
        # 以第一个节点的状态为准进行反转
        target_state = not nodes[0].view.is_collapsed
        graph._undo_stack.beginMacro("Toggle Collapse")
        for n in nodes:
            # NodeGraphQt 原生 BaseNode 没暴露 toggle 接口，直接操作 view
            if n.view.is_collapsed != target_state:
                n.view.toggle_collapse()
        graph._undo_stack.endMacro()