import json
import sys
import warnings
warnings.filterwarnings("ignore")

from collections import defaultdict, deque
from pathlib import Path
from loguru import logger
from threading import Lock

# 确保能导入你的组件
sys.path.append(str(Path(__file__).parent.parent))

from scan_components import scan_components
from runner.component_executor import run_component_in_subprocess


def build_execution_graph(nodes, graph_data):
    # 找出所有循环节点
    loop_nodes = {nid for nid, n in nodes.items() if n.get("is_loop_node") or n.get("is_iterate_node")}

    # 找出所有内部节点
    internal_nodes = set()
    for nid, n in nodes.items():
        if n.get("is_loop_node") or n.get("is_iterate_node"):
            internal_nodes.update(n.get("internal_nodes", []))

    # 只对非内部节点构建图
    executable_nodes = {nid for nid in nodes if nid not in internal_nodes}

    graph = defaultdict(list)
    in_degree = {nid: 0 for nid in executable_nodes}

    for conn in graph_data["connections"]:
        out_node_id = conn["out"][0]
        in_node_id = conn["in"][0]
        if out_node_id in executable_nodes and in_node_id in executable_nodes:
            graph[out_node_id].append(in_node_id)
            in_degree[in_node_id] += 1

    queue = deque([nid for nid in executable_nodes if in_degree[nid] == 0])
    order = []
    while queue:
        nid = queue.popleft()
        order.append(nid)
        for neighbor in graph[nid]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return order, loop_nodes, internal_nodes


def build_internal_graph(internal_nodes, graph_data):
    """构建循环体内部的拓扑排序"""
    graph = defaultdict(list)
    in_degree = {nid: 0 for nid in internal_nodes}

    for conn in graph_data["connections"]:
        out_id, in_id = conn["out"][0], conn["in"][0]
        if out_id in internal_nodes and in_id in internal_nodes:
            graph[out_id].append(in_id)
            in_degree[in_id] += 1

    # Kahn 算法
    queue = deque([nid for nid in internal_nodes if in_degree[nid] == 0])
    order = []
    while queue:
        nid = queue.popleft()
        order.append(nid)
        for neighbor in graph[nid]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) != len(internal_nodes):
        raise ValueError("循环体内部存在依赖环")
    return order


def build_node_inputs(node, graph_data, internal_outputs, global_outputs):
    """构建节点输入"""
    inputs = {}
    inputs.update(node.get("input_values", {}))

    for conn in graph_data["connections"]:
        if conn["in"][0] == node["node_id"]:
            out_nid, out_port = conn["out"]
            in_port = conn["in"][1]
            val = None
            if out_nid in internal_outputs:
                val = internal_outputs[out_nid].get(out_port)
            elif out_nid in global_outputs:
                val = global_outputs[out_nid].get(out_port)
            if val is not None:
                inputs[in_port] = val
    return inputs


def execute_loop_node(loop_node, all_nodes, graph_data, global_outputs, runtime_data, type="loop"):
    """执行一个循环控制流节点"""
    # 1. 获取输入数据（来自 inputs 端口）
    input_data = None
    for conn in graph_data["connections"]:
        if conn["in"][0] == loop_node["node_id"] and conn["in"][1] == "inputs":
            out_nid = conn["out"][0]
            if out_nid in global_outputs:
                input_data = global_outputs[out_nid].get(conn["out"][1])
                break

    if input_data is None:
        input_data = loop_node["input_values"].get("inputs", [])
    if not isinstance(input_data, (list, tuple)) and type == "loop":
        input_data = [input_data]

    # 2. 获取内部节点
    internal_ids = loop_node["internal_nodes"]
    internal_nodes = {nid: all_nodes[nid] for nid in internal_ids if nid in all_nodes}

    # 3. 找到输入/输出代理节点
    input_proxy = None
    output_proxy = None
    execute_nodes = {}

    for nid, n in internal_nodes.items():
        if n["class"] == "control_flow.ControlFlowInputPort":
            input_proxy = n
        elif n["class"] == "control_flow.ControlFlowOutputPort":
            output_proxy = n
        else:
            execute_nodes[nid] = n

    if not input_proxy or not output_proxy:
        raise ValueError("循环体缺少输入/输出代理节点")

    # 4. 构建内部拓扑图
    internal_order = build_internal_graph(execute_nodes, graph_data)

    # 5. 循环执行
    if type == "loop":
        results = []
        for item in input_data:
            # 注入当前项到输入代理
            input_proxy_outputs = {"output": item}  # 注意：端口名是 "output"
            internal_outputs = {input_proxy["node_id"]: input_proxy_outputs}

            # 执行内部节点
            for nid in internal_order:
                n = execute_nodes[nid]
                node_inputs = build_node_inputs(n, graph_data, internal_outputs, global_outputs)
                output = run_component_in_subprocess(
                    comp_class=n["class"],
                    file_path=n["file_path"],
                    params=n["params"],
                    inputs=node_inputs,
                    python_executable=runtime_data.get("environment_exe", sys.executable)
                )
                internal_outputs[nid] = output or {}

            input_port_values = []
            for conn in graph_data["connections"]:
                if conn["in"][0] == output_proxy["node_id"]:
                    out_nid, out_port = conn["out"]
                    if out_nid in internal_outputs:
                        val = internal_outputs[out_nid].get(out_port)
                        if val is not None:
                            input_port_values.append(val)
            results.append(input_port_values[0] if len(input_port_values) == 1 else input_port_values)
    else:
        loop_nums = loop_node["params"].get("loop_nums", 5)
        for i in range(loop_nums):
            # 构建输入数据
            input_proxy_outputs = {"output": input_data}  # 注意：端口名是 "output"
            internal_outputs = {input_proxy["node_id"]: input_proxy_outputs}

            # 构建内部拓扑图
            internal_order = build_internal_graph(execute_nodes, graph_data)

            # 执行内部节点
            for nid in internal_order:
                n = execute_nodes[nid]
                node_inputs = build_node_inputs(n, graph_data, internal_outputs, global_outputs)
                output = run_component_in_subprocess(
                    comp_class=n["class"],
                    file_path=n["file_path"],
                    params=n["params"],
                    inputs=node_inputs,
                    python_executable=runtime_data.get("environment_exe", sys.executable)
                )
                internal_outputs[nid] = output or {}

            input_port_values = []
            for conn in graph_data["connections"]:
                if conn["in"][0] == output_proxy["node_id"]:
                    out_nid, out_port = conn["out"]
                    if out_nid in internal_outputs:
                        val = internal_outputs[out_nid].get(out_port)
                        if val is not None:
                            input_port_values.append(val)
            input_data = input_port_values[0] if len(input_port_values) == 1 else input_port_values

        results = input_data

    return {"outputs": results}


def execute_workflow(file_path, external_inputs=None, python_executable=None):
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
        if full_path in component_map:
            comp_cls = component_map[full_path]
            file_path_comp = file_map.get(full_path)
        else:
            comp_cls = node_data["type_"]
            file_path_comp = None

        is_loop_node = (node_data.get("type_") == "control_flow.ControlFlowLoopNode")
        is_iterate_node = (node_data.get("type_") == "control_flow.ControlFlowIterateNode")
        # 直接使用 workflow 中的 params 和 input_values
        params = node_data["custom"].get("params", {})
        input_values = node_data["custom"].get("input_values", {})

        nodes[node_id] = {
            "node_id": node_id,
            "class": comp_cls,
            "file_path": file_path_comp,
            "name": node_data["name"],
            "params": params,
            "input_values": input_values,
            "is_loop_node": is_loop_node,  # ← 标记
            "is_iterate_node": is_iterate_node,
            "internal_nodes": node_data["custom"].get("internal_nodes", [])
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
    execution_order, loop_nodes, internal_nodes = build_execution_graph(nodes, graph_data)
    outputs_lock = Lock()
    # 7. 执行节点
    for node_id in execution_order:
        node = nodes[node_id]

        if node["is_loop_node"]:
            # ✅ 执行循环节点
            output = execute_loop_node(node, nodes, graph_data, node_outputs, runtime_data, type="loop")
            node_outputs[node_id] = output
        elif node["is_iterate_node"]:
            output = execute_loop_node(node, nodes, graph_data, node_outputs, runtime_data, type="iterate")
            node_outputs[node_id] = output
        else:
            # 构建输入字典（支持多输入端口聚合）
            node_inputs = {}

            # 先复制静态 input_values
            for port, val in node["input_values"].items():
                node_inputs[port] = val

            # 处理列选择
            stable_key = runtime_data.get("node_id2stable_key", {}).get(node_id, "")
            column_select = runtime_data.get("column_select", {}).get(stable_key, {})
            for port_name, cols in column_select.items():
                if cols:
                    node_inputs[f"{port_name}_column_select"] = cols

            # 聚合来自上游的输入（支持多连接）
            input_port_values = defaultdict(list)
            for conn in graph_data["connections"]:
                if conn["in"][0] == node_id:
                    out_nid, out_port = conn["out"]
                    in_port = conn["in"][1]
                    with outputs_lock:
                        if out_nid in node_outputs:
                            val = node_outputs[out_nid].get(out_port)
                            if val is not None:
                                input_port_values[in_port].append(val)

            # 合并：如果一个端口有多个输入，用列表；否则用单个值
            for port, vals in input_port_values.items():
                if len(vals) == 1:
                    node_inputs[port] = vals[0]
                else:
                    node_inputs[port] = vals  # 多输入端口自动为列表

            # 执行
            try:
                logger.info(f"执行节点: {node['name']}")
                output = run_component_in_subprocess(
                    comp_class=node["class"],
                    file_path=node["file_path"],
                    params=node["params"],
                    inputs=node_inputs,
                    python_executable=python_executable or runtime_data.get("environment_exe")
                )
                node_outputs[node_id] = output or {}
            except Exception as e:
                logger.error(f"节点执行失败 {node['name']}: {e}")
                raise e

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