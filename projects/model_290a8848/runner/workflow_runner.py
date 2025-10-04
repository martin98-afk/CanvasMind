# app/workflow_runner.py
import json
import sys
from pathlib import Path
from loguru import logger

# 确保能导入你的组件
sys.path.append(str(Path(__file__).parent.parent))

from scan_components import scan_components
from runner.component_executor import run_component_in_subprocess


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
    return order  # 返回节点ID列表


def execute_workflow(file_path, inputs=None):
    """
    执行工作流（支持导出的子图）

    :param file_path: 工作流文件路径
    :param inputs: 外部输入，格式: {"node_id": {"port_name": value}}
    :return: 节点输出字典
    """
    # 1. 加载组件和工作流
    component_map, file_map = scan_components()
    with open(file_path, 'r', encoding='utf-8') as f:
        full_data = json.load(f)
    graph_data = full_data["graph"]
    runtime_data = full_data.get("runtime", {})

    # 2. 构建节点映射
    nodes = {}
    node_outputs = {}  # 存储每个节点的输出
    node_inputs_history = {}  # 保存的历史输入值

    for node_id, node_data in graph_data["nodes"].items():
        stable_key = runtime_data.get("node_id2stable_key", {}).get(node_id)
        if not stable_key:
            continue
        full_path = stable_key.split("||")[0]
        if full_path not in component_map:
            logger.warning(f"组件未找到: {full_path}")
            continue

        comp_cls = component_map[full_path]
        file_path_comp = file_map.get(full_path)
        nodes[node_id] = {
            "node_id": node_id,
            "class": comp_cls,
            "file_path": file_path_comp,
            "name": node_data["name"],
            "params": runtime_data.get("node_properties", {}).get(stable_key, {})
        }

        # 保存历史输入值（关键！）
        node_inputs_history[node_id] = runtime_data.get("node_inputs", {}).get(stable_key, {})
        # 初始化输出为空
        node_outputs[node_id] = {}

    # 3. 构建执行顺序
    execution_order = build_execution_graph(nodes, graph_data)

    # 4. 逐个执行
    for node_id in execution_order:
        node = nodes[node_id]

        # ✅ 优先使用保存的历史输入值
        node_inputs = node_inputs_history.get(node_id, {}).copy()

        # 处理列选择
        column_select = runtime_data.get("column_select", {}).get(
            runtime_data.get("node_id2stable_key", {}).get(node_id, ""), {}
        )
        # 将列选择配置添加到 inputs 中（关键！）
        for port_name, cols in column_select.items():
            if cols:  # 只有当有列选择时才添加
                node_inputs[f"{port_name}_column_select"] = cols

        # 覆盖已连接端口的输入（如果上游节点在子图中）
        for conn in graph_data["connections"]:
            if conn["in"][0] == node_id:
                out_node_id = conn["out"][0]
                out_port_name = conn["out"][1]
                in_port_name = conn["in"][1]
                # 如果上游节点在当前子图中，使用其实际输出
                if out_node_id in node_outputs:
                    actual_output = node_outputs[out_node_id].get(out_port_name)
                    if actual_output is not None:
                        node_inputs[in_port_name] = actual_output

        # 注入外部输入（最高优先级）
        if inputs and node_id in inputs:
            node_inputs.update(inputs[node_id])

        # 执行组件
        try:
            logger.info(f"执行节点: {node['name']}")
            output = run_component_in_subprocess(
                comp_class=node["class"],
                file_path=node["file_path"],
                params=node["params"],
                inputs=node_inputs,
                python_executable=runtime_data.get("environment_exe", sys.executable)
            )
            logger.info(f"节点执行完成: {node['name']}")
            node_outputs[node_id] = output or {}
        except Exception as e:
            import traceback
            logger.error(f"节点执行失败 {node['name']}: {e}")
            logger.error(traceback.format_exc())
            # 继续执行其他节点（可选）

    return node_outputs


if __name__ == "__main__":
    file_path = sys.argv[1] if len(sys.argv) > 1 else "model.workflow.json"
    outputs = execute_workflow(file_path)
    print("工作流执行完成，输出:")
    for node_id, output in outputs.items():
        print(f"  {node_id}: {output}")