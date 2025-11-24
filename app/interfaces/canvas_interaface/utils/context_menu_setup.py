# /app/interfaces/canvas_interface/context_menu_setup.py
from PyQt5.QtCore import Qt
from qfluentwidgets import FluentIcon

def setup_context_menus(parent):
    graph_menu = parent.graph.get_context_menu('graph')
    graph_menu.add_command('运行工作流', parent.run_workflow, 'Ctrl+R')
    graph_menu.add_command('保存工作流', parent._save_via_dialog, 'Ctrl+S')
    graph_menu.add_separator()
    graph_menu.add_command('撤销', parent._undo, 'Ctrl+Z')
    graph_menu.add_command('重做', parent._redo, 'Ctrl+Y')
    graph_menu.add_command('自动布局', parent._auto_layout_selected, 'Ctrl+L')
    edit_menu = graph_menu.add_menu('编辑')
    edit_menu.add_command('全选', lambda graph: graph.select_all(), 'Ctrl+A')
    edit_menu.add_command('取消选择', lambda graph: graph.clear_selection(), 'Ctrl+D')
    edit_menu.add_command(
        '删除选中', lambda graph: (
            parent.delete_selected_nodes(graph),
            parent.property_panel.update_properties(None)
        ), 'Del'
    )

    nodes_menu = parent.graph.get_context_menu('nodes')
    special_nodes = [
        "dynamic.DYNAMIC_CODE",
        "control_flow.ControlFlowIterateNode",
        "control_flow.ControlFlowLoopNode",
        "control_flow.ControlFlowBranchNode"
    ]
    for node_type in special_nodes:
        nodes_menu.add_command('运行此节点', lambda graph, node: parent.run_node(node), node_type=node_type)
        nodes_menu.add_command('运行到此节点', lambda graph, node: parent.run_to_node(node), node_type=node_type)
        nodes_menu.add_command('从此节点开始运行', lambda graph, node: parent.run_from_node(node), node_type=node_type)
        nodes_menu.add_command('查看节点日志', lambda graph, node: node.show_logs(), node_type=node_type)
        nodes_menu.add_command('删除节点', lambda graph, node: parent.delete_node(node), node_type=node_type)