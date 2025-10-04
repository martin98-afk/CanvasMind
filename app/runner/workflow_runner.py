# -*- coding: utf-8 -*-
# app/workflow_runner.py
import json
import sys
from pathlib import Path

# 确保能导入你的组件
sys.path.append(str(Path(__file__).parent.parent))

from app.scan_components import scan_components
from app.nodes.create_dynamic_node import create_node_class


def load_workflow_graph(file_path):
    """加载工作流图结构（不含 GUI）"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data["graph"]


def create_headless_nodes(graph_data, component_map):
    """创建无 GUI 的节点实例"""
    nodes = {}
    for node_id, node_data in graph_data["nodes"].items():
        full_path = node_data.get("custom", {}).get("FULL_PATH")
        if not full_path or full_path not in component_map:
            continue

        comp_cls = component_map[full_path]
        # 创建动态节点类（无 GUI）
        node_class = create_node_class(comp_cls, full_path, None)
        # 创建实例
        node = node_class()
        node.id = node_id
        node.name = node_data["name"]
        node._input_values = {}
        node._output_values = {}
        node.column_select = {}
        nodes[node_id] = node
    return nodes


def build_execution_graph(nodes, graph_data):
    """构建执行依赖图"""
    from collections import defaultdict, deque

    graph = defaultdict(list)
    in_degree = {nid: 0 for nid in nodes}

    for conn in graph_data["connections"]:
        out_node_id = conn["out"][0]
        in_node_id = conn["in"][0]
        if out_node_id in nodes and in_node_id in nodes:
            graph[out_node_id].append(in_node_id)
            in_degree[in_node_id] += 1

    # 拓扑排序
    queue = deque([nid for nid in nodes if in_degree[nid] == 0])
    order = []
    while queue:
        nid = queue.popleft()
        order.append(nid)
        for neighbor in graph[nid]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) != len(nodes):
        raise RuntimeError("工作流存在循环依赖！")
    return [nodes[nid] for nid in order]


def execute_workflow(file_path, inputs=None, python_exe=None):
    """
    执行工作流（无 GUI）
    :param file_path: .workflow.json 路径
    :param inputs: 外部输入，如 {"node1": {"file_input": "/path"}}
    :param python_exe: Python 解释器路径（用于子进程）
    :return: 最终输出字典
    """
    # 1. 加载组件
    component_map, _ = scan_components()

    # 2. 加载工作流
    with open(file_path, 'r', encoding='utf-8') as f:
        full_data = json.load(f)
    graph_data = full_data["graph"]
    runtime_data = full_data.get("runtime", {})

    # 3. 创建节点
    nodes = create_headless_nodes(graph_data, component_map)

    # 4. 注入外部输入
    if inputs:
        for node_id, input_dict in inputs.items():
            if node_id in nodes:
                nodes[node_id]._input_values.update(input_dict)

    # 5. 恢复运行时状态（如列选择）
    for node_id, node in nodes.items():
        if node_id in runtime_data.get("column_select", {}):
            node.column_select = runtime_data["column_select"][node_id]

    # 6. 构建执行顺序
    execution_order = build_execution_graph(nodes, graph_data)

    # 7. 逐个执行
    for node in execution_order:
        try:
            # 准备输入
            node_inputs = node._input_values.copy()
            # 从上游获取数据
            for input_port in getattr(node, 'input_ports', lambda: [])():
                # 简化：假设你知道如何获取上游输出
                pass  # 实际需根据连接关系填充

            # 执行节点
            result = node.execute_sync(node_inputs, None, python_exe=python_exe)
            node._output_values = result or {}
        except Exception as e:
            raise RuntimeError(f"节点 {node.name} 执行失败: {e}")

    # 8. 收集最终输出
    final_outputs = {}
    for node in execution_order:
        final_outputs[node.id] = node._output_values

    return final_outputs