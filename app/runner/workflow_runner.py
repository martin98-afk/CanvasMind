import base64
import io
import json
import pickle
import sys
import traceback
import uuid
import warnings

warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from pyarrow import feather
from loguru import logger
from collections import defaultdict, deque
from pathlib import Path
from threading import Lock

# 确保能导入你的组件
sys.path.append(str(Path(__file__).parent.parent))
from scan_components import scan_components
from runner.component_executor import run_component_in_subprocess
from components.base import GlobalVariableContext
from runner.expression_engine import ExpressionEngine


# --- (deserialize_from_json 函数保持不变) ---
def deserialize_from_json(obj):
    if isinstance(obj, dict):
        if obj.get("__type__") == "DataFrame" and obj.get("format") == "feather_base64":
            try:
                binary_data = base64.b64decode(obj["data"])
                buffer = io.BytesIO(binary_data)
                table = feather.read_table(buffer)
                df = table.to_pandas()
                return df
            except Exception as e:
                logger.info(f"DataFrame Feather deserialization failed: {e}")
                return obj
        elif obj.get("__type__") == "DataFrame":
            try:
                df = pd.DataFrame(obj["data"], columns=obj["columns"])
                df.index = obj["index"]
                return df
            except Exception:
                return obj  # 降级
        elif obj.get("__type__") == "Series":
            df_temp = deserialize_from_json({**obj, "__type__": "DataFrame", "format": "feather_base64"})
            if isinstance(df_temp, pd.DataFrame) and len(df_temp.columns) == 1:
                return df_temp.iloc[:, 0]
            return obj
        elif obj.get("__type__") == "LargeList":
            format_type = obj.get("format", "pickle_binary")  # 默认为 pickle
            original_type = obj.get("original_type", "list")
            if format_type == "numpy_binary":
                try:
                    binary_data = base64.b64decode(obj["data"])
                    buffer = io.BytesIO(binary_data)
                    arr = np.load(buffer, allow_pickle=False)
                    result = arr.tolist()
                    if original_type == "tuple":
                        result = tuple(result)
                    return result
                except Exception as e:
                    logger.info(f"LargeList numpy deserialization failed: {e}")
                    return obj
            elif format_type == "pickle_binary":
                try:
                    binary_data = base64.b64decode(obj["data"])
                    buffer = io.BytesIO(binary_data)
                    result = pickle.load(buffer)
                    if original_type == "tuple" and not isinstance(result, tuple):
                        result = tuple(result)
                    elif original_type == "list" and not isinstance(result, list):
                        result = list(result)
                    return result
                except Exception as e:
                    logger.info(f"LargeList pickle deserialization failed: {e}")
                    return obj
            else:
                logger.info(f"Unknown LargeList format: {format_type}")
                return obj
        elif obj.get("__type__") == "ndarray":
            format_type = obj.get("format", "list")  # 默认为旧格式
            if format_type == "npy_base64":
                try:
                    binary_data = base64.b64decode(obj["data"])
                    buffer = io.BytesIO(binary_data)
                    arr = np.load(buffer, allow_pickle=False)
                    return arr
                except Exception as e:
                    logger.info(f"ndarray binary deserialization failed: {e}")
                    return obj
            elif format_type == "list":
                try:
                    return np.array(obj["data"], dtype=obj["dtype"])
                except Exception as e:
                    logger.info(f"ndarray list deserialization failed: {e}")
                    return obj
            else:
                logger.info(f"Unknown ndarray format: {format_type}")
                return obj
        elif "__type__" in obj and "__data__" in obj:
            return obj["__data__"]
        else:
            return {k: deserialize_from_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [deserialize_from_json(v) for v in obj]
    else:
        return obj


# --- (update_global_variable, build_execution_graph, build_internal_graph, execute_branch_node_internal, execute_loop_node_with_branches, execute_iterate_node_with_branches, _evaluate_condition_with_engine, evaludate_model_inputs 函数保持不变) ---
def update_global_variable(node, output):
    variable_changed = False
    for port in output:
        if f"{node['name']}_{port}" in global_variable["node_vars"]:
            if global_variable["node_vars"][f"{node['name']}_{port}"]["update_policy"] == "更新":
                global_variable["node_vars"][f"{node['name']}_{port}"]["value"] = output[port]
                variable_changed = True
            elif global_variable["node_vars"][f"{node['name']}_{port}"]["update_policy"] == "追加":
                variable_changed = True
                current_value = global_variable["node_vars"][f"{node['name']}_{port}"]["value"]
                value = output[port]
                try:
                    if isinstance(current_value, list):
                        if isinstance(value, list):
                            update_value = current_value + value
                        else:
                            update_value = current_value + [value]
                    elif isinstance(current_value, dict):
                        if isinstance(value, dict):
                            update_value = {**current_value, **value}
                    else:
                        update_value = [current_value, value]
                except Exception as e:
                    update_value = value
                global_variable["node_vars"][f"{node['name']}_{port}"]["value"] = update_value
    if variable_changed:
        expr_engine.update_global_vars(GlobalVariableContext(**global_variable))


def build_execution_graph(nodes, graph_data):
    loop_nodes = {nid for nid, n in nodes.items() if n.get("is_loop_node") or n.get("is_iterate_node")}
    internal_nodes = set()
    for nid, n in nodes.items():
        if n.get("is_loop_node") or n.get("is_iterate_node"):
            internal_nodes.update(n.get("internal_nodes", []))
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
    graph = defaultdict(list)
    in_degree = {nid: 0 for nid in internal_nodes}
    for conn in graph_data["connections"]:
        out_id, in_id = conn["out"][0], conn["in"][0]
        if out_id in internal_nodes and in_id in internal_nodes:
            graph[out_id].append(in_id)
            in_degree[in_id] += 1
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


def execute_branch_node_internal(branch_node, input_data, execute_all_matches=False):
    local_vars = {"input_input": input_data}
    output_dict = {}
    selected_ports = []
    for cond in branch_node.get("conditions", []):
        expr = cond.get("expr", "").strip()
        port_name = cond.get("name")
        if not expr or not port_name:
            continue
        try:
            if expr_engine.is_pure_expression_block(expr):
                result = expr_engine.evaluate_expression_block(expr, local_vars)
                if result:
                    selected_ports.append(port_name)
                    if not execute_all_matches:
                        break
        except Exception as e:
            logger.warning(f"表达式评估失败 {expr}: {e}")
            continue
    if not selected_ports and branch_node.get("enable_else", False):
        selected_ports.append("else")
    if selected_ports:
        for port in selected_ports:
            output_dict[port] = input_data
    return selected_ports, output_dict


def execute_loop_node_with_branches(loop_node, all_nodes, graph_data, input_data, runtime_data, disabled_nodes=None):
    # 获取内部节点
    internal_ids = loop_node["internal_nodes"]
    internal_nodes = {nid: all_nodes[nid] for nid in internal_ids if nid in all_nodes}
    # 找到输入/输出代理节点
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
    # 构建内部拓扑图
    internal_order = build_internal_graph(execute_nodes, graph_data)

    # 循环执行 - 根据不同模式执行
    if loop_node.get("loop_mode", "count") == "count":
        # count模式：执行固定次数
        results = []
        current_data = input_data
        for i in range(min(loop_node.get("loop_nums", 5), loop_node.get("max_iterations", 100))):
            # 注入当前项到输入代理
            input_proxy_outputs = {"output": current_data}
            internal_outputs = {input_proxy["node_id"]: input_proxy_outputs}
            # 执行内部节点，支持分支和并行-回合逻辑
            internal_outputs, internal_disabled_nodes = execute_internal_nodes_with_branches(
                execute_nodes, internal_order, graph_data, input_proxy, output_proxy,
                current_data, runtime_data, internal_outputs, disabled_nodes.copy() if disabled_nodes else set()
            )
            # 获取输出代理的值
            input_port_values = []
            for conn in graph_data["connections"]:
                if conn["in"][0] == output_proxy["node_id"]:
                    out_nid, out_port = conn["out"]
                    var_name = f"node_vars_{execute_nodes[out_nid]['name'].replace(' ', '_')}_{out_port}"
                    if var_name in internal_outputs:
                        val = internal_outputs[var_name]
                        if val is not None:
                            input_port_values.append(val)
            current_data = input_port_values[0] if len(input_port_values) == 1 else input_port_values
            results.append(current_data)
        return {"outputs": results[-1] if results else None}, internal_disabled_nodes
    elif loop_node.get("loop_mode", "count") == "condition":
        # condition模式：先执行，再根据条件判断是否继续
        current_data = input_data
        results = []
        for i in range(loop_node.get("max_iterations", 100)):
            # 注入当前项到输入代理
            input_proxy_outputs = {"output": current_data}
            internal_outputs = {input_proxy["node_id"]: input_proxy_outputs}
            # 执行内部节点，支持分支和并行-回合逻辑
            internal_outputs, internal_disabled_nodes = execute_internal_nodes_with_branches(
                execute_nodes, internal_order, graph_data, input_proxy, output_proxy,
                current_data, runtime_data, internal_outputs, disabled_nodes.copy() if disabled_nodes else set()
            )
            # 获取输出代理的值
            input_port_values = []
            for conn in graph_data["connections"]:
                if conn["in"][0] == output_proxy["node_id"]:
                    out_nid, out_port = conn["out"]
                    var_name = f"node_vars_{execute_nodes[out_nid]['name'].replace(' ', '_')}_{out_port}"
                    if var_name in internal_outputs:
                        val = internal_outputs[var_name]
                        if val is not None:
                            input_port_values.append(val)
            current_data = input_port_values[0] if len(input_port_values) == 1 else input_port_values
            results.append(current_data)
            # 检查循环条件
            should_continue = _evaluate_condition_with_engine(
                loop_node.get("loop_condition", ""), current_data, runtime_data, internal_outputs, i + 1, "condition",
                loop_node.get("max_iterations", 100)
            )
            if not should_continue:
                break
        return {"outputs": results[-1] if results else None}, internal_disabled_nodes
    elif loop_node.get("loop_mode", "count") == "while":
        # while模式：先判断条件，再执行（如果条件为真）
        current_data = input_data
        results = []
        for i in range(loop_node.get("max_iterations", 100)):
            # 检查循环条件
            should_continue = _evaluate_condition_with_engine(
                loop_node.get("loop_condition", ""), current_data, runtime_data, {}, i + 1, "while",
                loop_node.get("max_iterations", 100)
            )
            if not should_continue:
                break
            # 注入当前项到输入代理
            input_proxy_outputs = {"output": current_data}
            internal_outputs = {input_proxy["node_id"]: input_proxy_outputs}
            # 执行内部节点，支持分支和并行-回合逻辑
            internal_outputs, internal_disabled_nodes = execute_internal_nodes_with_branches(
                execute_nodes, internal_order, graph_data, input_proxy, output_proxy,
                current_data, runtime_data, internal_outputs, disabled_nodes.copy() if disabled_nodes else set()
            )
            # 获取输出代理的值
            input_port_values = []
            for conn in graph_data["connections"]:
                if conn["in"][0] == output_proxy["node_id"]:
                    out_nid, out_port = conn["out"]
                    var_name = f"node_vars_{execute_nodes[out_nid]['name'].replace(' ', '_')}_{out_port}"
                    if var_name in internal_outputs:
                        val = internal_outputs[var_name]
                        if val is not None:
                            input_port_values.append(val)
            current_data = input_port_values[0] if len(input_port_values) == 1 else input_port_values
            results.append(current_data)
        return {"outputs": results[-1] if results else None}, internal_disabled_nodes
    else:
        raise ValueError(f"未知的循环模式: {loop_node.get('loop_mode')}")


def execute_iterate_node_with_branches(iterate_node, all_nodes, graph_data, input_data, runtime_data,
                                       disabled_nodes=None):
    # ... (保持原有逻辑不变，但需要传递 disabled_nodes)
    # 修复点：仅当 input_data 为空时，才使用预制参数
    if not input_data:
        input_data = iterate_node["input_values"].get("inputs", [])
    if not isinstance(input_data, (list, tuple)):
        input_data = [input_data]

    # 获取内部节点
    internal_ids = iterate_node["internal_nodes"]
    internal_nodes = {nid: all_nodes[nid] for nid in internal_ids if nid in all_nodes}
    # 找到输入/输出代理节点
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
        raise ValueError("迭代体缺少输入/输出代理节点")

    # 构建内部拓扑图
    internal_order = build_internal_graph(execute_nodes, graph_data)

    # 迭代执行
    results = []
    total_disabled_nodes = disabled_nodes.copy() if disabled_nodes else set()
    for item in input_data:
        # 注入当前项到输入代理
        input_proxy_outputs = {"output": item}
        internal_outputs = {input_proxy["node_id"]: input_proxy_outputs}
        # 执行内部节点，支持分支和并行-回合逻辑
        internal_outputs, internal_disabled_nodes = execute_internal_nodes_with_branches(
            execute_nodes, internal_order, graph_data, input_proxy, output_proxy,
            item, runtime_data, internal_outputs, total_disabled_nodes
        )
        # 获取输出代理的值
        input_port_values = []
        for conn in graph_data["connections"]:
            if conn["in"][0] == output_proxy["node_id"]:
                out_nid, out_port = conn["out"]
                var_name = f"node_vars_{execute_nodes[out_nid]['name'].replace(' ', '_')}_{out_port}"
                if var_name in internal_outputs:
                    val = internal_outputs[var_name]
                    if val is not None:
                        input_port_values.append(val)
        result = input_port_values[0] if len(input_port_values) == 1 else input_port_values
        results.append(result)
        # 合并本次迭代产生的禁用节点
        total_disabled_nodes.update(internal_disabled_nodes)

    return {"outputs": results}, total_disabled_nodes


def _evaluate_condition_with_engine(condition_expr, current_data, runtime_data, internal_outputs,
                                    current_index=0, loop_mode="count", max_iterations=100):
    if not condition_expr:
        return False
    try:
        temp_vars = {
            'data': current_data,
            'result': current_data,
            'current_index': current_index,
            'current_iteration': current_index,
            'iteration_count': current_index + 1,
            'loop_mode': loop_mode,
            'max_iterations': max_iterations,
            'runtime_data': runtime_data,
        }
        if internal_outputs:
            temp_vars.update(internal_outputs)
        result = expr_engine.evaluate_expression_block(condition_expr, temp_vars)
        if isinstance(result, str) and result.startswith('[ExprError:'):
            logger.warning(f"条件表达式评估失败: {condition_expr}, 错误: {result}")
            return False
        return bool(result)
    except Exception as e:
        logger.warning(f"条件表达式评估异常: {condition_expr}, 错误: {e}")
        return False


def evaludate_model_inputs(inputs, params):
    input_vars = {}
    for k, v in inputs.items():
        safe_key = f"input_{k}"
        input_vars[safe_key] = v

    params = {k: expr_engine.evaluate_template(v, local_vars=input_vars) for k, v in params.items()}
    inputs = {k: expr_engine.evaluate_template(v, local_vars=input_vars) for k, v in inputs.items()}
    return inputs, params


# --- 修改后的 get_downstream_nodes 函数 ---
def get_downstream_nodes(start_node_id, connections, all_node_ids, specific_port=None, downstream_cache=None):
    """
    获取从指定节点的指定输出端口开始的所有下游节点（包括间接连接的）
    :param start_node_id: 起始节点ID
    :param connections: 连接列表
    :param all_node_ids: 所有节点ID集合
    :param specific_port: 特定的输出端口名，如果提供，则只追踪从此端口出发的连接
    :param downstream_cache: 缓存字典，键为 (start_node_id, specific_port)
    :return: 下游节点集合
    """
    cache_key = (start_node_id, specific_port)
    if downstream_cache is not None and cache_key in downstream_cache:
        return downstream_cache[cache_key]

    downstream = set()
    visited = set()
    queue = deque([start_node_id])

    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        # 找到所有从此节点（和端口）输出的连接
        for conn in connections:
            if conn["out"][0] == current:
                if specific_port is None or conn["out"][1] == specific_port:
                    target_node = conn["in"][0]
                    if target_node in all_node_ids and target_node not in visited:
                        downstream.add(target_node)
                        queue.append(target_node)

    if downstream_cache is not None:
        downstream_cache[cache_key] = downstream
    return downstream


# --- 修改后的 execute_internal_nodes_with_branches 函数 ---
def execute_internal_nodes_with_branches(execute_nodes, internal_order, graph_data, input_proxy, output_proxy,
                                         input_data, runtime_data, initial_outputs=None, disabled_nodes=None):
    """
    执行内部节点，支持分支节点和并行-回合逻辑
    :param disabled_nodes: 传入的禁用节点集合，用于初始化和判断
    """
    if initial_outputs is None:
        initial_outputs = {}
    if disabled_nodes is None:
        disabled_nodes = set()

    input_proxy_outputs = {"output": input_data}
    internal_outputs = initial_outputs.copy()
    internal_outputs[input_proxy["node_id"]] = input_proxy_outputs

    active_branch_outputs = {}

    # 为了高效查找，预计算每个分支节点未激活端口的下游节点
    for nid in execute_nodes:
        n = execute_nodes[nid]
        if n.get("is_branch_node", False):
            all_port_names = {cond.get("name") for cond in n.get("conditions", [])}
            if n.get("enable_else", False):
                all_port_names.add("else")

    for nid in internal_order:
        n = execute_nodes[nid]

        # --- 新增：检查上游节点状态以决定是否跳过 ---
        upstream_nodes = set()
        for conn in graph_data["connections"]:
            if conn["in"][0] == nid:
                upstream_nodes.add(conn["out"][0])
        # 从上游节点中移除输入代理（它总是有效的）
        upstream_nodes.discard(input_proxy["node_id"])

        # 如果所有上游节点都已被禁用，则当前节点也应被禁用
        if upstream_nodes and all(up_node in disabled_nodes for up_node in upstream_nodes):
            disabled_nodes.add(nid)
            # 为所有输出端口设置 None
            node_name = n["name"].replace(" ", "_")
            for port_name in n.get("output_ports", []):  # 假设节点定义了 output_ports
                var_name = f"node_vars_{node_name}_{port_name}"
                internal_outputs[var_name] = None
            logger.info(f"内部节点 {n['name']} 因所有上游节点被禁用而被跳过。")
            continue  # 跳过执行

        # --- 聚合输入 ---
        input_port_values = defaultdict(list)
        for conn in graph_data["connections"]:
            if conn["in"][0] == nid:
                out_nid, out_port = conn["out"]
                in_port = conn["in"][1]
                if out_nid not in execute_nodes:  # 输入代理
                    val = input_proxy_outputs.get(out_port)
                else:
                    node_name = execute_nodes[out_nid]["name"].replace(" ", "_")
                    var_name = f"node_vars_{node_name}_{out_port}"
                    val = internal_outputs.get(var_name)
                input_port_values[in_port].append(val)

        node_inputs = {}
        for port, val in n["input_values"].items():
            val = project_dir / val if isinstance(val, str) and val.startswith("inputs/") else val
            node_inputs[port] = val

        for port, vals in input_port_values.items():
            if len(vals) == 1:
                node_inputs[port] = node_inputs[port] if isinstance(vals[0], str) and vals[
                    0] == "upload_file_placeholder" else vals[0]
            else:
                node_inputs[port] = vals

        if n.get("is_branch_node", False):
            input_val = next(iter(node_inputs.values()), None)
            execute_all_matches = n.get("execute_all_matches", False)
            selected_ports, output = execute_branch_node_internal(n, input_val, execute_all_matches)

            # --- 新增：处理未激活端口及其下游节点 ---
            all_port_names = {cond.get("name") for cond in n.get("conditions", [])}
            if n.get("enable_else", False):
                all_port_names.add("else")

            # 记录激活的分支端口
            if selected_ports:
                for port in selected_ports:
                    branch_var_name = f"node_vars_{n['name'].replace(' ', '_')}_{port}"
                    internal_outputs[branch_var_name] = output[port]
                active_branch_outputs[n["node_id"]] = selected_ports if execute_all_matches else selected_ports[0]
                logger.info(f"内部分支节点 {n['name']} 激活端口: {selected_ports}")

                # 计算未激活的端口
                unselected_ports = all_port_names - set(selected_ports)
                logger.info(f"内部分支节点 {n['name']} 未激活端口: {unselected_ports}")

                # 找到未激活端口的下游节点并加入禁用集合
                for unselected_port in unselected_ports:
                    downstream_for_unselected = get_downstream_nodes(n["node_id"], graph_data["connections"],
                                                                     set(execute_nodes.keys()),
                                                                     specific_port=unselected_port)
                    disabled_nodes.update(downstream_for_unselected)
                    logger.info(
                        f"将分支节点 {n['name']} 端口 '{unselected_port}' 的下游节点 {list(downstream_for_unselected)} 标记为禁用。")
            else:
                logger.info(f"内部分支节点 {n['name']} 没有激活任何端口")
                # 如果没有激活任何端口，理论上所有输出端口的下游都应被禁用
                for unselected_port in all_port_names:
                    downstream_for_unselected = get_downstream_nodes(n["node_id"], graph_data["connections"],
                                                                     set(execute_nodes.keys()),
                                                                     specific_port=unselected_port)
                    disabled_nodes.update(downstream_for_unselected)
                    logger.info(
                        f"将无激活分支节点 {n['name']} 端口 '{unselected_port}' 的下游节点 {list(downstream_for_unselected)} 标记为禁用。")

        else:
            # 执行普通节点（如果未被禁用）
            if nid not in disabled_nodes:
                node_inputs, node_params = evaludate_model_inputs(node_inputs, n["params"])
                logger.info(f"执行内部节点: {n['name']}")
                logger.info(f"输入: {node_inputs}")
                logger.info(f"参数: {node_params}")
                output = run_component_in_subprocess(
                    comp_class=n["class"],
                    file_path=n["file_path"],
                    params=node_params,
                    inputs=node_inputs,
                    global_variable=global_variable
                )
                update_global_variable(n, output)
                logger.info(f"输出: {output}")
                node_name = n["name"].replace(" ", "_")
                for port_name, port_value in (output or {}).items():
                    var_name = f"node_vars_{node_name}_{port_name}"
                    internal_outputs[var_name] = port_value
            else:
                # 节点已被禁用，但仍需为其输出变量设置 None
                logger.info(f"跳过执行内部节点（已禁用）: {n['name']}")
                node_name = n["name"].replace(" ", "_")
                for port_name in n.get("output_ports", []):  # 假设节点定义了 output_ports
                    var_name = f"node_vars_{node_name}_{port_name}"
                    internal_outputs[var_name] = None

    return internal_outputs, disabled_nodes  # 返回更新后的禁用集合


# --- 修改后的 execute_workflow 函数 ---
def execute_workflow(file_path, external_inputs=None, result_path=None, **kwargs):
    global logger
    global global_variable
    global expr_engine
    global runtime_data
    global project_dir
    logger = kwargs.get("logger", logger)
    workflow_path = Path(file_path)
    project_dir = workflow_path.parent.absolute()

    with open(workflow_path, 'r', encoding='utf-8') as f:
        full_data = deserialize_from_json(json.load(f))
    graph_data = full_data["graph"]
    runtime_data = full_data.get("runtime", {})
    global_variable = runtime_data.get("global_variable", {})
    global_ctx = GlobalVariableContext(**global_variable)
    expr_engine = ExpressionEngine(global_vars_context=global_ctx)

    spec_path = project_dir / "project_spec.json"
    project_spec = {}
    if spec_path.exists():
        with open(spec_path, 'r', encoding='utf-8') as f:
            project_spec = json.load(f)

    component_map, file_map = scan_components(components_dir=project_dir / "components", logger=logger)

    nodes = {}
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
        params = node_data["custom"].get("params", {})
        input_values = node_data["custom"].get("input_values", {})
        nodes[node_id] = {
            "node_id": node_id,
            "class": comp_cls,
            "file_path": file_path_comp,
            "name": node_data["name"],
            "params": params,
            "input_values": input_values,
            "is_loop_node": is_loop_node,
            "is_iterate_node": is_iterate_node,
            "internal_nodes": node_data["custom"].get("internal_nodes", []),
            "is_branch_node": is_branch_node,
            "conditions": node_data["custom"]["params"].get("conditions", []),
            "enable_else": node_data["custom"]["params"].get("enable_else", False),
            "execute_all_matches": node_data["custom"]["params"].get("execute_all_matches", False),
            "loop_mode": node_data["custom"]["params"].get("loop_mode", "count"),
            "loop_condition": node_data["custom"]["params"].get("loop_condition", ""),
            "loop_nums": node_data["custom"]["params"].get("loop_nums", 5),
            "max_iterations": node_data["custom"]["params"].get("max_iterations", 100),
            "global_variable": node_data["custom"]["params"].get("global_variable", {}),
            "output_ports": [p["name"] for p in node_data.get("outputs", [])]  # 添加输出端口列表
        }

    if external_inputs and "inputs" in project_spec:
        for input_key, cfg in project_spec["inputs"].items():
            if input_key in external_inputs:
                node_id = cfg["node_id"]
                if node_id in nodes:
                    value = external_inputs[input_key]
                    if cfg["type"] == "组件超参数":
                        nodes[node_id]["params"][cfg["param_name"]] = value
                    else:
                        nodes[node_id]["input_values"][cfg["port_name"]] = value

    execution_order, loop_nodes, internal_nodes = build_execution_graph(nodes, graph_data)
    outputs_lock = Lock()

    # --- 新增：初始化禁用节点集合 ---
    disabled_nodes = set()

    # 预计算每个分支节点未激活端口的下游节点（用于外部流程）
    branch_downstream_cache = {}
    for node_id in execution_order:
        node = nodes[node_id]
        if node.get("is_branch_node", False):
            all_port_names = {cond.get("name") for cond in node.get("conditions", [])}
            if node.get("enable_else", False):
                all_port_names.add("else")
            for port_name in all_port_names:
                downstream_for_port = get_downstream_nodes(node_id, graph_data["connections"], set(nodes.keys()),
                                                           specific_port=port_name,
                                                           downstream_cache=branch_downstream_cache)

    active_branch_outputs = {}
    node_outputs = {}

    for node_id in execution_order:
        node = nodes[node_id]

        # --- 新增：检查上游节点状态以决定是否跳过 ---
        upstream_nodes = set()
        for conn in graph_data["connections"]:
            if conn["in"][0] == node_id:
                upstream_nodes.add(conn["out"][0])
        # 从上游节点中移除全局变量等特殊输入（如果有的话），这里假设只考虑直接节点连接

        if upstream_nodes and all(up_node in disabled_nodes for up_node in upstream_nodes):
            disabled_nodes.add(node_id)
            # 为所有输出端口设置 None
            node_name = node["name"].replace(" ", "_")
            for port_name in node.get("output_ports", []):
                var_name = f"node_vars_{node_name}_{port_name}"
                node_outputs[node_id] = node_outputs.get(node_id, {})
                node_outputs[node_id][port_name] = None
            logger.info(f"节点 {node['name']} 因所有上游节点被禁用而被跳过。")
            continue  # 跳过执行

        # --- 聚合输入逻辑 ---
        node_inputs = {}
        stable_key = runtime_data.get("node_id2stable_key", {}).get(node_id, "")
        column_select = runtime_data.get("column_select", {}).get(stable_key, {})
        for port_name, cols in column_select.items():
            if cols:
                node_inputs[f"{port_name}_column_select"] = cols

        input_port_values = defaultdict(list)
        for conn in graph_data["connections"]:
            if conn["in"][0] == node_id:
                out_nid, out_port = conn["out"]
                in_port = conn["in"][1]
                with outputs_lock:
                    if out_nid in node_outputs:
                        val = node_outputs[out_nid].get(out_port)
                        input_port_values[in_port].append(val)

        for port, val in node["input_values"].items():
            val = project_dir / val if isinstance(val, str) and val.startswith("inputs/") else val
            node_inputs[port] = val

        for port, vals in input_port_values.items():
            if len(vals) == 1:
                node_inputs[port] = node_inputs[port] if isinstance(vals[0], str) and vals[
                    0] == "upload_file_placeholder" else vals[0]
            else:
                node_inputs[port] = vals

        if node["is_loop_node"]:
            output, loop_disabled_nodes = execute_loop_node_with_branches(
                node, nodes, graph_data, [item for item in node_inputs.values()][0], runtime_data,
                disabled_nodes  # 需要修改 execute_loop_node_with_branches 以接收和返回 disabled_nodes
            )
            # 合并循环内部产生的禁用节点
            disabled_nodes.update(loop_disabled_nodes)
            node_outputs[node_id] = output

        elif node["is_iterate_node"]:
            output, iter_disabled_nodes = execute_iterate_node_with_branches(
                node, nodes, graph_data, [item for item in node_inputs.values()][0], runtime_data,
                disabled_nodes  # 需要修改 execute_iterate_node_with_branches 以接收和返回 disabled_nodes
            )
            # 合并迭代内部产生的禁用节点
            disabled_nodes.update(iter_disabled_nodes)
            node_outputs[node_id] = output

        elif node["is_branch_node"]:
            input_val = next(iter(node_inputs.values()), None)
            execute_all_matches = node.get("execute_all_matches", False)
            selected_ports, output = execute_branch_node(node, input_val, execute_all_matches)
            node_outputs[node_id] = output

            if selected_ports:
                active_branch_outputs[node_id] = selected_ports if execute_all_matches else selected_ports[0]
                logger.info(f"分支节点 {node['name']} 激活端口: {selected_ports}")

                # --- 新增：处理未激活端口及其下游节点 ---
                all_port_names = {cond.get("name") for cond in node.get("conditions", [])}
                if node.get("enable_else", False):
                    all_port_names.add("else")
                unselected_ports = all_port_names - set(selected_ports)
                logger.info(f"分支节点 {node['name']} 未激活端口: {unselected_ports}")

                for unselected_port in unselected_ports:
                    # 获取此未激活端口的下游节点
                    downstream_for_unselected = get_downstream_nodes(node_id, graph_data["connections"],
                                                                     set(nodes.keys()), specific_port=unselected_port)
                    # 将这些节点加入禁用集合
                    disabled_nodes.update(downstream_for_unselected)
                    logger.info(
                        f"将分支节点 {node['name']} 端口 '{unselected_port}' 的下游节点 {list(downstream_for_unselected)} 标记为禁用。")
            else:
                logger.info(f"分支节点 {node['name']} 没有激活任何端口")
                # 如果没有激活任何端口，理论上所有输出端口的下游都应被禁用
                all_port_names = {cond.get("name") for cond in node.get("conditions", [])}
                if node.get("enable_else", False):
                    all_port_names.add("else")
                for unselected_port in all_port_names:
                    downstream_for_unselected = get_downstream_nodes(node_id, graph_data["connections"],
                                                                     set(nodes.keys()), specific_port=unselected_port)
                    disabled_nodes.update(downstream_for_unselected)
                    logger.info(
                        f"将无激活分支节点 {node['name']} 端口 '{unselected_port}' 的下游节点 {list(downstream_for_unselected)} 标记为禁用。")

        else:
            # 执行普通节点（如果未被禁用）
            if node_id not in disabled_nodes:
                node_inputs, node_params = evaludate_model_inputs(node_inputs, node["params"])
                try:
                    logger.info(f"执行节点: {node['name']}")
                    logger.info(f"输入: {node_inputs}")
                    output = run_component_in_subprocess(
                        comp_class=node["class"],
                        file_path=node["file_path"],
                        params=node_params,
                        inputs=node_inputs,
                        global_variable=global_variable,
                        logger=logger
                    )
                    update_global_variable(node, output)
                    logger.info(f"输出: {output}")
                    node_outputs[node_id] = output or {}
                except Exception as e:
                    logger.error(f"节点执行失败 {node['name']}: {traceback.format_exc()}")
                    raise e
            else:
                # 节点已被禁用，但仍需为其输出变量设置 None
                logger.info(f"跳过执行节点（已禁用）: {node['name']}")
                node_outputs[node_id] = {port: None for port in node.get("output_ports", [])}

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
        final_outputs = node_outputs

    logger.info(f"最终输出: {final_outputs}")
    result_path = result_path if result_path else project_dir / "result.pkl"
    with open(result_path, 'wb') as f:
        pickle.dump(final_outputs, f)


# --- (execute_branch_node 函数保持不变) ---
def execute_branch_node(branch_node, input_data, execute_all_matches=False):
    local_vars = {"input_input": input_data}
    output_dict = {}
    selected_ports = []
    for cond in branch_node.get("conditions", []):
        expr = cond.get("expr", "").strip()
        port_name = cond.get("name")
        if not expr or not port_name:
            continue
        try:
            if expr_engine.is_pure_expression_block(expr):
                result = expr_engine.evaluate_expression_block(expr, local_vars)
                if result:
                    selected_ports.append(port_name)
                    if not execute_all_matches:
                        break
        except Exception as e:
            logger.warning(f"表达式评估失败 {expr}: {e}")
            continue
    if not selected_ports and branch_node.get("enable_else", False):
        selected_ports.append("else")
    if selected_ports:
        for port in selected_ports:
            output_dict[port] = input_data
    return selected_ports, output_dict


if __name__ == "__main__":
    logger.remove()
    NODE_ID = uuid.uuid4().hex
    (Path(__file__).parent.parent / "run.log").unlink(missing_ok=True)
    (Path(__file__).parent.parent / "result.pkl").unlink(missing_ok=True)
    log_handler_id = logger.add(
        Path(__file__).parent.parent / "run.log",
        level="INFO",
        encoding='utf-8',
        enqueue=True,
        rotation="10 MB",
        retention=3
    )
    logger = logger.bind(node_id=NODE_ID)
    external_input_file = Path(__file__).parent.parent / "input.pkl"
    if external_input_file.exists():
        with open(external_input_file, "rb") as f:
            external_inputs = pickle.load(f)
    else:
        external_inputs = None
    execute_workflow(
        Path(__file__).parent.parent / "model.workflow.json",
        external_inputs=external_inputs,
        logger=logger,
    )