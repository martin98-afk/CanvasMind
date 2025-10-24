import json
import sys
import warnings
import loguru

warnings.filterwarnings("ignore")

from collections import defaultdict, deque
from pathlib import Path
from threading import Lock
import copy

# 确保能导入你的组件
sys.path.append(str(Path(__file__).parent.parent))

from scan_components import scan_components
from runner.component_executor import run_component_in_subprocess
from components.base import GlobalVariableContext
from runner.expression_engine import ExpressionEngine


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


def build_node_inputs(node, graph_data, internal_outputs):
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
            if val is not None:
                inputs[in_port] = val
    return inputs


def execute_loop_node(loop_node, all_nodes, graph_data, input_data, runtime_data, type="loop"):
    # 修复点：仅当 input_data 为空时，才使用预制参数
    if not input_data:
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
                node_inputs = build_node_inputs(n, graph_data, internal_outputs)
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
            # 优化：缓存内部拓扑图，避免重复计算
            # internal_order = build_internal_graph(execute_nodes, graph_data)  # 这里注释掉，因为已经在外面计算了

            # 执行内部节点
            for nid in internal_order:
                n = execute_nodes[nid]
                node_inputs = build_node_inputs(n, graph_data, internal_outputs)
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


def execute_branch_node(branch_node, input_data, expr_engine):
    # 2. 准备局部变量
    local_vars = {"input": input_data[0] if isinstance(input_data, (list, tuple)) and input_data else input_data}

    # 3. 初始化所有输出端口为 None
    output_dict = {}

    # 4. 评估条件
    selected_port = None
    for cond in branch_node.get("conditions", []):
        expr = cond.get("expr", "").strip()
        port_name = cond.get("name")  # 这就是输出端口名！
        if not expr or not port_name:
            continue

        try:
            if expr_engine.is_pure_expression_block(expr):
                result = expr_engine.evaluate_expression_block(expr, local_vars)
                if result:  # 真值判断
                    selected_port = port_name
                    break
        except Exception as e:
            logger.warning(f"表达式评估失败 {expr}: {e}")
            continue

    # 5. 处理 else（如果启用）
    if selected_port is None and branch_node.get("enable_else", False):
        selected_port = "else"  # 假设有一个叫 "else" 的输出端口

    # 6. 如果有选中端口，透传输入数据
    if selected_port is not None:
        # 透传 input_data（保持原始结构）
        output_dict[selected_port] = input_data[0] if isinstance(input_data,
                                                                 (list, tuple)) and input_data else input_data

    return selected_port, output_dict  # 例如: {"branch_true": 42} 或 {"else": [1,2,3]}


def get_downstream_nodes(start_node_id, connections, all_node_ids, downstream_cache=None):
    """获取从指定节点开始的所有下游节点（包括间接连接的）"""
    if downstream_cache is not None and start_node_id in downstream_cache:
        return downstream_cache[start_node_id]

    downstream = set()
    visited = set()
    queue = deque([start_node_id])

    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        # 找到所有从此节点输出的连接
        for conn in connections:
            if conn["out"][0] == current and conn["in"][0] in all_node_ids:
                target_node = conn["in"][0]
                if target_node not in visited:
                    downstream.add(target_node)
                    queue.append(target_node)

    # 缓存结果
    if downstream_cache is not None:
        downstream_cache[start_node_id] = downstream

    return downstream


def evaludate_model_inputs(engine, inputs, params):
    # === 构建 input_xxx 变量 ===
    input_vars = {}
    for k, v in inputs.items():
        # 将 input.port_name 转为 input_port_name（避免点号）
        safe_key = f"input_{k}"
        input_vars[safe_key] = v

    # === 递归求值 params，传入 input_vars ===
    def _evaluate_with_inputs(value, engine, input_vars_dict):
        if isinstance(value, str):
            return engine.evaluate_template(value, local_vars=input_vars_dict)
        elif isinstance(value, list):
            return [_evaluate_with_inputs(v, engine, input_vars_dict) for v in value]
        elif isinstance(value, dict):
            return {k: _evaluate_with_inputs(v, engine, input_vars_dict) for k, v in value.items()}
        else:
            return value

    params = {k: _evaluate_with_inputs(v, engine, input_vars) for k, v in params.items()}
    inputs = {k: _evaluate_with_inputs(v, engine, input_vars) for k, v in inputs.items()}
    return inputs, params


def execute_workflow(file_path, external_inputs=None, python_executable=None, **kwargs):
    """
    执行工作流（支持 project_spec.json 定义的接口）

    :param file_path: model.workflow.json 路径
    :param external_inputs: {"input_0": "hello", "input_1": 5}
    :return: {"output_0": ..., "output_1": ...}
    """
    global logger
    logger = kwargs.get("logger", loguru.logger)
    workflow_path = Path(file_path)
    project_dir = workflow_path.parent
    # 1. 加载工作流
    with open(workflow_path, 'r', encoding='utf-8') as f:
        full_data = json.load(f)
    graph_data = full_data["graph"]
    runtime_data = full_data.get("runtime", {})
    global_variable = runtime_data.get("global_variable", {})
    # 1. 反序列化全局变量
    global_ctx = GlobalVariableContext()
    global_ctx.deserialize(global_variable)
    # print(global_variable)  # 移除调试打印
    expr_engine = ExpressionEngine(global_vars_context=global_ctx)

    # 2. 加载 project_spec（如果有）
    spec_path = project_dir / "project_spec.json"
    project_spec = {}
    if spec_path.exists():
        with open(spec_path, 'r', encoding='utf-8') as f:
            project_spec = json.load(f)

    # 3. 扫描组件
    component_map, file_map = scan_components(components_dir=project_dir / "components", logger=logger)
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
        is_branch_node = (node_data.get("type_") == "control_flow.ControlFlowBranchNode")
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
            "internal_nodes": node_data["custom"].get("internal_nodes", []),
            "is_branch_node": is_branch_node,
            "conditions": node_data["custom"]["params"].get("conditions", []),
            "enable_else": node_data["custom"]["params"].get("enable_else", False),
            "global_variable": node_data["custom"]["params"].get("global_variable", {}),
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

    # 7. 执行节点 - 跟踪已激活的分支
    active_branch_outputs = {}  # 记录分支节点的激活端口
    skip_nodes = set()  # 记录需要跳过的节点

    # 性能优化：缓存下游节点信息
    downstream_cache = {}

    for node_id in execution_order:
        node = nodes[node_id]

        # 检查当前节点是否应该被跳过
        if node_id in skip_nodes:
            logger.info(f"跳过节点: {node['name']} (因为连接到未激活的分支)")
            continue

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
        upstream_branch_nodes = []  # 记录上游分支节点信息，用于优化判断

        for conn in graph_data["connections"]:
            if conn["in"][0] == node_id:
                out_nid, out_port = conn["out"]
                in_port = conn["in"][1]

                # 检查上游节点是否是分支节点且当前端口未被激活
                if out_nid in active_branch_outputs:
                    # 这个上游节点是分支节点，检查其输出端口是否被激活
                    active_port = active_branch_outputs[out_nid]
                    if out_port != active_port:
                        # 该端口未被激活，跳过当前节点
                        logger.info(f"节点 {node['name']} 连接到未激活的分支端口 {out_port}，跳过执行")
                        # 获取所有从这个连接的目标节点开始的下游节点，并加入跳过列表
                        downstream_nodes = get_downstream_nodes(
                            node_id, graph_data["connections"], set(nodes.keys()), downstream_cache)
                        skip_nodes.update(downstream_nodes)
                        skip_nodes.add(node_id)
                        upstream_branch_nodes = []  # 清空，因为已经决定跳过
                        break  # 跳出连接循环，跳过整个节点
                    else:
                        # 这个分支端口是激活的，记录用于后续处理
                        upstream_branch_nodes.append((out_nid, out_port))

                with outputs_lock:
                    if out_nid in node_outputs:
                        val = node_outputs[out_nid].get(out_port)
                        if val is not None:
                            input_port_values[in_port].append(val)

        # 如果当前节点被标记为跳过，继续下一个节点
        if node_id in skip_nodes:
            continue

        # 合并：如果一个端口有多个输入，用列表；否则用单个值
        for port, vals in input_port_values.items():
            if len(vals) == 1:
                node_inputs[port] = vals[0]
            else:
                node_inputs[port] = vals  # 多输入端口自动为列表

        if node["is_loop_node"]:
            # ✅ 执行循环节点
            output = execute_loop_node(
                node, nodes, graph_data, [item for item in node_inputs.values()][0], runtime_data, type="loop")
            node_outputs[node_id] = output
        elif node["is_iterate_node"]:
            output = execute_loop_node(
                node, nodes, graph_data, [item for item in node_inputs.values()][0], runtime_data, type="iterate")
            node_outputs[node_id] = output
        elif node["is_branch_node"]:
            # 提取输入值（假设只有一个输入端口）
            input_val = None
            if node_inputs:
                input_val = next(iter(node_inputs.values()))
            selected_port, output = execute_branch_node(node, input_val, expr_engine)
            node_outputs[node_id] = output

            # 记录激活的分支端口
            if selected_port is not None:
                active_branch_outputs[node_id] = selected_port
                logger.info(f"分支节点 {node['name']} 激活端口: {selected_port}")
            else:
                logger.info(f"分支节点 {node['name']} 没有激活任何端口")

                # 没有激活任何端口，跳过所有下游节点
                downstream_nodes = get_downstream_nodes(
                    node_id, graph_data["connections"], set(nodes.keys()), downstream_cache)
                skip_nodes.update(downstream_nodes)
        else:
            node_inputs, node_params = evaludate_model_inputs(expr_engine, node_inputs, node["params"])
            # 执行普通节点
            try:
                logger.info(f"执行节点: {node['name']}")
                logger.info(f"输入: {node_inputs}")
                output = run_component_in_subprocess(
                    comp_class=node["class"],
                    file_path=node["file_path"],
                    params=node["params"],
                    inputs=node_inputs,
                    global_variable=global_variable,
                    python_executable=python_executable or runtime_data.get("environment_exe"),
                    logger=logger
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