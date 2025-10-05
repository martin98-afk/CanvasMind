import json
import sys
from pathlib import Path
from loguru import logger

# 确保能导入你的组件
sys.path.append(str(Path(__file__).parent.parent))

from scan_components import scan_components
from runner.component_executor import run_component_in_subprocess


def build_execution_graph(nodes, graph_data):
    """构建执行依赖图（使用原始 node.id）"""
    from collections import defaultdict, deque

    graph = defaultdict(list)
    in_degree = {nid: 0 for nid in nodes}

    for conn in graph_data["connections"]:
        out_node_id = conn["out"][0]
        in_node_id = conn["in"][0]
        if out_node_id in nodes and in_node_id in nodes:
            graph[out_node_id].append(in_node_id)
            in_degree[in_node_id] += 1

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
    return order


def execute_workflow(file_path, external_inputs=None):
    """
    执行工作流（支持 project_spec.json 定义的接口）

    :param file_path: model.workflow.json 路径
    :param external_inputs: {"input_0": "hello", "input_1": 5}
    :return: {"output_0": ..., "output_1": ...}
    """
    workflow_path = Path(file_path)
    project_dir = workflow_path.parent

    # 1. 加载工作流
    with open(workflow_path, 'r', encoding='utf-8') as f:
        full_data = json.load(f)
    graph_data = full_data["graph"]
    runtime_data = full_data.get("runtime", {})

    # 2. 加载 project_spec（如果有）
    spec_path = project_dir / "project_spec.json"
    project_spec = {}
    if spec_path.exists():
        with open(spec_path, 'r', encoding='utf-8') as f:
            project_spec = json.load(f)

    # 3. 扫描组件
    component_map, file_map = scan_components()

    # 4. 构建节点执行数据（使用原始 node.id）
    nodes = {}  # key: node.id
    node_outputs = {}

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

        # 直接使用 workflow 中的 params 和 input_values
        params = node_data["custom"].get("params", {})
        input_values = node_data["custom"].get("input_values", {})

        nodes[node_id] = {
            "node_id": node_id,
            "class": comp_cls,
            "file_path": file_path_comp,
            "name": node_data["name"],
            "params": params,
            "input_values": input_values
        }

    # 5. ✅ 关键：用 external_inputs 覆盖 spec 指定的输入
    if external_inputs and "inputs" in project_spec:
        for input_key, cfg in project_spec["inputs"].items():
            if input_key in external_inputs:
                node_id = cfg["node_id"]
                if node_id in nodes:
                    value = external_inputs[input_key]
                    if cfg["type"] == "组件超参数":
                        nodes[node_id]["params"][cfg["param_name"]] = value
                    else:  # 组件输入
                        nodes[node_id]["input_values"][cfg["port_name"]] = value

    # 6. 构建执行顺序
    execution_order = build_execution_graph(nodes, graph_data)

    # 7. 执行节点
    for node_id in execution_order:
        node = nodes[node_id]
        node_inputs = node["input_values"].copy()

        # 处理列选择
        stable_key = runtime_data.get("node_id2stable_key", {}).get(node_id, "")
        column_select = runtime_data.get("column_select", {}).get(stable_key, {})
        for port_name, cols in column_select.items():
            if cols:
                node_inputs[f"{port_name}_column_select"] = cols

        # 覆盖已连接端口的输入（来自上游）
        for conn in graph_data["connections"]:
            if conn["in"][0] == node_id:
                out_node_id = conn["out"][0]
                out_port_name = conn["out"][1]
                in_port_name = conn["in"][1]
                if out_node_id in node_outputs:
                    actual_output = node_outputs[out_node_id].get(out_port_name)
                    if actual_output is not None:
                        node_inputs[in_port_name] = actual_output

        # 执行
        try:
            logger.info(f"执行节点: {node['name']}")
            output = run_component_in_subprocess(
                comp_class=node["class"],
                file_path=node["file_path"],
                params=node["params"],
                inputs=node_inputs,
                python_executable=runtime_data.get("environment_exe", sys.executable)
            )
            node_outputs[node_id] = output or {}
        except Exception as e:
            logger.error(f"节点执行失败 {node['name']}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            node_outputs[node_id] = {}

    # 8. ✅ 按 project_spec 提取最终输出
    final_outputs = {}
    if "outputs" in project_spec:
        for output_key, out_cfg in project_spec["outputs"].items():
            node_id = out_cfg["node_id"]
            output_name = out_cfg["output_name"]
            if node_id in node_outputs:
                final_outputs[output_key] = node_outputs[node_id].get(output_name)
            else:
                final_outputs[output_key] = None
    else:
        # 兼容老项目：返回所有节点输出
        final_outputs = node_outputs

    return final_outputs