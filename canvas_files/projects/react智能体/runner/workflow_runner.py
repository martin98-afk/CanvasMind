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


def deserialize_from_json(obj):
    if isinstance(obj, dict):
        if obj.get("__type__") == "DataFrame" and obj.get("format") == "feather_base64":
            try:
                # 解码 base64
                binary_data = base64.b64decode(obj["data"])
                buffer = io.BytesIO(binary_data)
                # 读取 feather 格式
                table = feather.read_table(buffer)
                df = table.to_pandas()
                return df
            except Exception as e:
                print(f"DataFrame Feather deserialization failed: {e}")
                return obj
        elif obj.get("__type__") == "DataFrame":
            try:
                df = pd.DataFrame(obj["data"], columns=obj["columns"])
                df.index = obj["index"]
                return df
            except Exception:
                return obj  # 降级
        elif obj.get("__type__") == "Series":
            # 如果 Series 是通过转为 DataFrame 序列化的
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
                    # 转回 Python 列表或元组
                    result = arr.tolist()
                    if original_type == "tuple":
                        result = tuple(result)
                    return result
                except Exception as e:
                    print(f"LargeList numpy deserialization failed: {e}")
                    return obj
            elif format_type == "pickle_binary":
                try:
                    binary_data = base64.b64decode(obj["data"])
                    buffer = io.BytesIO(binary_data)
                    result = pickle.load(buffer)
                    # 确保返回原始类型
                    if original_type == "tuple" and not isinstance(result, tuple):
                        result = tuple(result)
                    elif original_type == "list" and not isinstance(result, list):
                        result = list(result)
                    return result
                except Exception as e:
                    print(f"LargeList pickle deserialization failed: {e}")
                    return obj
            else:
                print(f"Unknown LargeList format: {format_type}")
                return obj
        elif obj.get("__type__") == "ndarray":
            format_type = obj.get("format", "list")  # 默认为旧格式
            if format_type == "npy_base64":
                try:
                    # 解码 base64 数据
                    binary_data = base64.b64decode(obj["data"])
                    buffer = io.BytesIO(binary_data)
                    # 从二进制数据加载 ndarray
                    arr = np.load(buffer, allow_pickle=False)
                    return arr
                except Exception as e:
                    print(f"ndarray binary deserialization failed: {e}")
                    return obj
            elif format_type == "list":
                # 兼容旧的 list 格式
                try:
                    return np.array(obj["data"], dtype=obj["dtype"])
                except Exception as e:
                    print(f"ndarray list deserialization failed: {e}")
                    return obj
            else:
                print(f"Unknown ndarray format: {format_type}")
                return obj
        elif "__type__" in obj and "__data__" in obj:
            # 通用对象（通常不重建，只保留字典）
            return obj["__data__"]
        else:
            return {k: deserialize_from_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [deserialize_from_json(v) for v in obj]
    else:
        return obj


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


def build_node_inputs(node, graph_data, internal_outputs, execute_nodes, input_proxy):
    """构建节点输入"""
    inputs = {}
    inputs.update(node.get("input_values", {}))

    for conn in graph_data["connections"]:
        if conn["in"][0] == node["node_id"]:
            out_nid, out_port = conn["out"]
            in_port = conn["in"][1]
            val = None
            if out_nid in execute_nodes:
                val = internal_outputs.get(f"node_vars_{execute_nodes[out_nid]['name'].replace(' ', '_')}_{out_port}")
            elif out_nid == input_proxy["node_id"]:
                val = internal_outputs[out_nid]["output"]
            if val is not None:
                inputs[in_port] = val
    return inputs


def execute_branch_node_internal(branch_node, input_data, expr_engine, execute_all_matches=False):
    """
    内部分支节点执行函数，支持执行所有匹配分支或仅第一个匹配分支
    """
    # 准备局部变量
    local_vars = {"input_input": input_data[0] if isinstance(input_data, (list, tuple)) and input_data else input_data}

    # 初始化所有输出端口为 None
    output_dict = {}

    # 评估条件
    selected_ports = []

    for cond in branch_node.get("conditions", []):
        expr = cond.get("expr", "").strip()
        port_name = cond.get("name")  # 这就是输出端口名！
        if not expr or not port_name:
            continue

        try:
            if expr_engine.is_pure_expression_block(expr):
                result = expr_engine.evaluate_expression_block(expr, local_vars)
                if result:  # 真值判断
                    selected_ports.append(port_name)
                    if not execute_all_matches:  # 如果只执行第一个匹配分支，则跳出
                        break
        except Exception as e:
            logger.warning(f"表达式评估失败 {expr}: {e}")
            continue

    # 处理 else（如果启用）
    if not selected_ports and branch_node.get("enable_else", False):
        selected_ports.append("else")  # 假设有一个叫 "else" 的输出端口

    # 如果有选中端口，透传输入数据
    if selected_ports:
        for port in selected_ports:
            # 透传 input_data（保持原始结构）
            output_dict[port] = input_data[0] if isinstance(input_data,
                                                            (list, tuple)) and input_data else input_data

    return selected_ports, output_dict  # 例如: {"branch_true": 42} 或 {"else": [1,2,3]}


def execute_loop_node_with_branches(loop_node, all_nodes, graph_data, input_data, runtime_data, type="loop",
                                    engine=None):
    """
    优化的循环节点执行函数，支持内部分支节点
    """
    # 修复点：仅当 input_data 为空时，才使用预制参数
    if not input_data:
        input_data = loop_node["input_values"].get("inputs", [])

    # 获取循环模式和参数
    loop_mode = loop_node.get("loop_mode", "count")  # 默认为count模式
    loop_condition = loop_node.get("loop_condition", "")
    loop_nums = loop_node.get("loop_nums", 5)
    max_iterations = loop_node.get("max_iterations", 100)  # 防止无限循环

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
    if loop_mode == "count":
        # count模式：执行固定次数
        results = []
        current_data = input_data

        for i in range(min(loop_nums, max_iterations)):  # 限制最大迭代次数
            # 注入当前项到输入代理
            input_proxy_outputs = {"output": current_data}
            internal_outputs = {input_proxy["node_id"]: input_proxy_outputs}

            # 执行内部节点，支持分支和并行-回合逻辑
            internal_outputs = execute_internal_nodes_with_branches(
                execute_nodes, internal_order, graph_data, input_proxy, output_proxy,
                current_data, runtime_data, engine, internal_outputs
            )

            # 获取输出代理的值 - 使用正确的格式
            input_port_values = []
            for conn in graph_data["connections"]:
                if conn["in"][0] == output_proxy["node_id"]:
                    out_nid, out_port = conn["out"]
                    # 使用正确的格式获取输出
                    var_name = f"node_vars_{execute_nodes[out_nid]['name'].replace(' ', '_')}_{out_port}"
                    if var_name in internal_outputs:
                        val = internal_outputs[var_name]
                        if val is not None:
                            input_port_values.append(val)
            current_data = input_port_values[0] if len(input_port_values) == 1 else input_port_values
            results.append(current_data)

        return {"outputs": results[-1] if results else None}  # 返回最后一次执行的结果

    elif loop_mode == "condition":
        # condition模式：先执行，再根据条件判断是否继续
        current_data = input_data
        results = []

        for i in range(max_iterations):  # 限制最大迭代次数
            # 注入当前项到输入代理
            input_proxy_outputs = {"output": current_data}
            internal_outputs = {input_proxy["node_id"]: input_proxy_outputs}

            # 执行内部节点，支持分支和并行-回合逻辑
            internal_outputs = execute_internal_nodes_with_branches(
                execute_nodes, internal_order, graph_data, input_proxy, output_proxy,
                current_data, runtime_data, engine, internal_outputs
            )

            # 获取输出代理的值 - 使用正确的格式
            input_port_values = []
            for conn in graph_data["connections"]:
                if conn["in"][0] == output_proxy["node_id"]:
                    out_nid, out_port = conn["out"]
                    # 使用正确的格式获取输出
                    var_name = f"node_vars_{execute_nodes[out_nid]['name'].replace(' ', '_')}_{out_port}"
                    if var_name in internal_outputs:
                        val = internal_outputs[var_name]
                        if val is not None:
                            input_port_values.append(val)
            current_data = input_port_values[0] if len(input_port_values) == 1 else input_port_values
            results.append(current_data)

            # 检查循环条件 - 使用表达式引擎评估，添加循环相关参数
            should_continue = _evaluate_condition_with_engine(
                loop_condition, current_data, runtime_data, internal_outputs, engine, i + 1, loop_mode, max_iterations
            )
            if not should_continue:
                break

        return {"outputs": results[-1] if results else None}

    elif loop_mode == "while":
        # while模式：先判断条件，再执行（如果条件为真）
        current_data = input_data
        results = []

        for i in range(max_iterations):  # 限制最大迭代次数
            # 检查循环条件 - 使用表达式引擎评估，添加循环相关参数
            should_continue = _evaluate_condition_with_engine(
                loop_condition, current_data, runtime_data, {}, engine, i + 1, loop_mode, max_iterations
            )
            if not should_continue:
                break

            # 注入当前项到输入代理
            input_proxy_outputs = {"output": current_data}
            internal_outputs = {input_proxy["node_id"]: input_proxy_outputs}

            # 执行内部节点，支持分支和并行-回合逻辑
            internal_outputs = execute_internal_nodes_with_branches(
                execute_nodes, internal_order, graph_data, input_proxy, output_proxy,
                current_data, runtime_data, engine, internal_outputs
            )

            # 获取输出代理的值 - 使用正确的格式
            input_port_values = []
            for conn in graph_data["connections"]:
                if conn["in"][0] == output_proxy["node_id"]:
                    out_nid, out_port = conn["out"]
                    # 使用正确的格式获取输出
                    var_name = f"node_vars_{execute_nodes[out_nid]['name'].replace(' ', '_')}_{out_port}"
                    if var_name in internal_outputs:
                        val = internal_outputs[var_name]
                        if val is not None:
                            input_port_values.append(val)
            current_data = input_port_values[0] if len(input_port_values) == 1 else input_port_values
            results.append(current_data)

        return {"outputs": results[-1] if results else None}

    else:
        raise ValueError(f"未知的循环模式: {loop_mode}")


def execute_iterate_node_with_branches(iterate_node, all_nodes, graph_data, input_data, runtime_data, engine=None):
    """
    执行迭代节点，对可迭代input进行遍历
    """
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
    for item in input_data:
        # 注入当前项到输入代理
        input_proxy_outputs = {"output": item}
        internal_outputs = {input_proxy["node_id"]: input_proxy_outputs}

        # 执行内部节点，支持分支和并行-回合逻辑
        internal_outputs = execute_internal_nodes_with_branches(
            execute_nodes, internal_order, graph_data, input_proxy, output_proxy,
            item, runtime_data, engine, internal_outputs
        )

        # 获取输出代理的值 - 使用正确的格式
        input_port_values = []
        for conn in graph_data["connections"]:
            if conn["in"][0] == output_proxy["node_id"]:
                out_nid, out_port = conn["out"]
                # 使用正确的格式获取输出
                var_name = f"node_vars_{execute_nodes[out_nid]['name'].replace(' ', '_')}_{out_port}"
                if var_name in internal_outputs:
                    val = internal_outputs[var_name]
                    if val is not None:
                        input_port_values.append(val)
        result = input_port_values[0] if len(input_port_values) == 1 else input_port_values
        results.append(result)

    return {"outputs": results}


def execute_internal_nodes_with_branches(execute_nodes, internal_order, graph_data, input_proxy, output_proxy,
                                         input_data, runtime_data, engine, initial_outputs=None):
    """
    执行内部节点，支持分支节点和并行-回合逻辑
    """
    if initial_outputs is None:
        initial_outputs = {}
    engine.update_global_vars(GlobalVariableContext(**global_variable))
    # 注入当前项到输入代理
    input_proxy_outputs = {"output": input_data}  # 注意：端口名是 "output"
    internal_outputs = initial_outputs.copy()
    internal_outputs[input_proxy["node_id"]] = input_proxy_outputs

    # 记录分支激活状态和需要跳过的节点
    active_branch_outputs = {}  # 记录分支节点的激活端口
    skip_nodes = set()  # 记录需要跳过的节点

    # 性能优化：缓存下游节点信息
    downstream_cache = {}

    for nid in internal_order:
        n = execute_nodes[nid]

        # 检查当前节点是否应该被跳过
        if nid in skip_nodes:
            logger.info(f"跳过内部节点: {n['name']} (因为连接到未激活的分支)")
            continue

        # 构建输入字典
        node_inputs = build_node_inputs(n, graph_data, internal_outputs, execute_nodes, input_proxy)

        # 检查上游节点是否是分支节点且当前端口未被激活
        upstream_branch_nodes = []
        for conn in graph_data["connections"]:
            if conn["in"][0] == nid:
                out_nid, out_port = conn["out"]
                # 使用正确的格式查找上游输出
                if out_nid in active_branch_outputs:
                    # 这个上游节点是分支节点，检查其输出端口是否被激活
                    active_port = active_branch_outputs[out_nid]
                    if isinstance(active_port, list):  # execute_all_matches = True
                        if out_port not in active_port:
                            # 该端口未被激活，跳过当前节点
                            logger.info(f"内部节点 {n['name']} 连接到未激活的分支端口 {out_port}，跳过执行")
                            # 获取所有从这个连接的目标节点开始的下游节点，并加入跳过列表
                            downstream_nodes = get_downstream_nodes(
                                nid, graph_data["connections"], set(execute_nodes.keys()), downstream_cache)
                            skip_nodes.update(downstream_nodes)
                            skip_nodes.add(nid)
                            break  # 跳出连接循环，跳过整个节点
                        else:
                            upstream_branch_nodes.append((out_nid, out_port))
                    else:  # execute_all_matches = False
                        if out_port != active_port:
                            # 该端口未被激活，跳过当前节点
                            logger.info(f"内部节点 {n['name']} 连接到未激活的分支端口 {out_port}，跳过执行")
                            # 获取所有从这个连接的目标节点开始的下游节点，并加入跳过列表
                            downstream_nodes = get_downstream_nodes(
                                nid, graph_data["connections"], set(execute_nodes.keys()), downstream_cache)
                            skip_nodes.update(downstream_nodes)
                            skip_nodes.add(nid)
                            break  # 跳出连接循环，跳过整个节点
                        else:
                            upstream_branch_nodes.append((out_nid, out_port))

        # 如果当前节点被标记为跳过，继续下一个节点
        if nid in skip_nodes:
            continue

        if n.get("is_branch_node", False):
            # 提取输入值（假设只有一个输入端口）
            input_val = None
            if node_inputs:
                input_val = next(iter(node_inputs.values()))

            # 获取分支节点的 execute_all_matches 参数
            execute_all_matches = n.get("execute_all_matches", False)
            selected_ports, output = execute_branch_node_internal(n, input_val, engine, execute_all_matches)

            # 记录激活的分支端口 - 使用正确的格式
            if selected_ports:
                # 假设分支输出端口名
                for port in selected_ports:
                    branch_var_name = f"node_vars_{n['name'].replace(' ', '_')}_{port}"
                    internal_outputs[branch_var_name] = output[port]
                active_branch_outputs[n["node_id"]] = selected_ports if execute_all_matches else selected_ports[0]
                logger.info(f"内部分支节点 {n['name']} 激活端口: {selected_ports}")
            else:
                logger.info(f"内部分支节点 {n['name']} 没有激活任何端口")
                # 没有激活任何端口，跳过所有下游节点
                downstream_nodes = get_downstream_nodes(
                    nid, graph_data["connections"], set(execute_nodes.keys()), downstream_cache)
                skip_nodes.update(downstream_nodes)
        else:
            # 执行普通节点
            node_inputs, node_params = evaludate_model_inputs(engine, node_inputs, n["params"])
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
            for port in output:
                if f"{n['name']}_{port}" in global_variable["node_vars"]:
                    if global_variable["node_vars"][f"{n['name']}_{port}"]["update_policy"] == "更新":
                        global_variable["node_vars"][f"{n['name']}_{port}"]["value"] = output[port]
                    elif global_variable["node_vars"][f"{n['name']}_{port}"]["update_policy"] == "追加":
                        current_value = global_variable["node_vars"][f"{n['name']}_{port}"]["value"]
                        value = output[port]
                        try:
                            # --- 处理字符串 ---
                            if isinstance(current_value, list):
                                if isinstance(value, list):
                                    update_value = current_value + value
                                else:
                                    # 如果当前是列表，但新值不是列表，将新值作为一个元素追加
                                    update_value = current_value + [value]
                            # --- 处理字典 ---
                            elif isinstance(current_value, dict):
                                if isinstance(value, dict):
                                    # 合并字典，新值会覆盖同名键的旧值
                                    update_value = {**current_value, **value}
                            # --- 其他类型 ---
                            else:
                                # 对于其他类型，尝试直接相加，如果失败则覆盖
                                update_value = [current_value, value]
                        except Exception as e:
                            update_value = value
                        global_variable["node_vars"][f"{n['name']}_{port}"]["value"] = update_value

            logger.info(f"输出: {output}")

            # 对于内部节点，使用 node_vars_{节点名}_{端口名} 格式存储输出，以便在表达式引擎中使用
            node_name = n["name"].replace(" ", "_")  # 替换空格为下划线
            for port_name, port_value in (output or {}).items():
                var_name = f"node_vars_{node_name}_{port_name}"
                internal_outputs[var_name] = port_value

    return internal_outputs


def _evaluate_condition_with_engine(condition_expr, current_data, runtime_data, internal_outputs, engine,
                                    current_index=0, loop_mode="count", max_iterations=100):
    """使用表达式引擎评估条件表达式"""
    if not condition_expr:
        return False

    try:
        # 准备临时变量，这些变量将在表达式评估时可用
        temp_vars = {
            'data': current_data,  # 当前循环的数据
            'result': current_data,  # 同上（兼容别名）
            'current_index': current_index,  # 当前迭代索引
            'current_iteration': current_index,  # 当前迭代次数（从0开始）
            'iteration_count': current_index + 1,  # 当前迭代次数（从1开始）
            'loop_mode': loop_mode,  # 当前循环模式
            'max_iterations': max_iterations,  # 最大迭代次数
            'runtime_data': runtime_data,
        }

        # 添加内部节点的输出作为临时变量
        if internal_outputs:
            temp_vars.update(internal_outputs)

        result = engine.evaluate_expression_block(condition_expr, temp_vars)
        # 将结果转换为布尔值
        if isinstance(result, str) and result.startswith('[ExprError:'):
            logger.warning(f"条件表达式评估失败: {condition_expr}, 错误: {result}")
            return False  # 表达式错误时停止循环

        return bool(result)

    except Exception as e:
        logger.warning(f"条件表达式评估异常: {condition_expr}, 错误: {e}")
        return False  # 异常时停止循环以防止无限循环


def execute_branch_node(branch_node, input_data, expr_engine, execute_all_matches=False):
    """
    外部分支节点执行函数，支持执行所有匹配分支或仅第一个匹配分支
    """
    # 准备局部变量
    local_vars = {"input_input": input_data[0] if isinstance(input_data, (list, tuple)) and input_data else input_data}

    # 初始化所有输出端口为 None
    output_dict = {}

    # 评估条件
    selected_ports = []

    for cond in branch_node.get("conditions", []):
        expr = cond.get("expr", "").strip()
        port_name = cond.get("name")  # 这就是输出端口名！
        if not expr or not port_name:
            continue

        try:
            if expr_engine.is_pure_expression_block(expr):
                result = expr_engine.evaluate_expression_block(expr, local_vars)
                if result:  # 真值判断
                    selected_ports.append(port_name)
                    if not execute_all_matches:  # 如果只执行第一个匹配分支，则跳出
                        break
        except Exception as e:
            logger.warning(f"表达式评估失败 {expr}: {e}")
            continue

    # 处理 else（如果启用）
    if not selected_ports and branch_node.get("enable_else", False):
        selected_ports.append("else")  # 假设有一个叫 "else" 的输出端口

    # 如果有选中端口，透传输入数据
    if selected_ports:
        for port in selected_ports:
            # 透传 input_data（保持原始结构）
            output_dict[port] = input_data[0] if isinstance(input_data,
                                                            (list, tuple)) and input_data else input_data

    return selected_ports, output_dict  # 例如: {"branch_true": 42} 或 {"else": [1,2,3]}


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


def execute_workflow(file_path, external_inputs=None, result_path=None, **kwargs):
    """
    执行工作流（支持 project_spec.json 定义的接口）

    :param file_path: model.workflow.json 路径
    :param external_inputs: {"input_0": "hello", "input_1": 5}
    :return: {"output_0": ..., "output_1": ...}
    """
    global logger
    global global_variable
    logger = kwargs.get("logger", logger)
    workflow_path = Path(file_path)
    project_dir = workflow_path.parent.absolute()
    # 1. 加载工作流
    with open(workflow_path, 'r', encoding='utf-8') as f:
        full_data = deserialize_from_json(json.load(f))
    graph_data = full_data["graph"]
    runtime_data = full_data.get("runtime", {})
    # 导入全局变量
    global_variable = runtime_data.get("global_variable", {})
    # 1. 反序列化全局变量
    global_ctx = GlobalVariableContext(**global_variable)
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
            "execute_all_matches": node_data["custom"]["params"].get("execute_all_matches", False),  # 新增
            "loop_mode": node_data["custom"]["params"].get("loop_mode", "count"),  # 循环模式
            "loop_condition": node_data["custom"]["params"].get("loop_condition", ""),  # 循环条件
            "loop_nums": node_data["custom"]["params"].get("loop_nums", 5),  # 循环次数
            "max_iterations": node_data["custom"]["params"].get("max_iterations", 100),  # 最大迭代次数
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
            val = project_dir / val if isinstance(val, str) and val.startswith("inputs/") else val
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
                    if isinstance(active_port, list):  # execute_all_matches = True
                        if out_port not in active_port:
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
                            upstream_branch_nodes.append((out_nid, out_port))
                    else:  # execute_all_matches = False
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
            # ✅ 执行循环节点（支持内部分支和多种循环模式）
            output = execute_loop_node_with_branches(
                node, nodes, graph_data, [item for item in node_inputs.values()][0], runtime_data,
                type="loop", engine=expr_engine
            )
            node_outputs[node_id] = output
        elif node["is_iterate_node"]:
            # 执行迭代节点（对可迭代input进行遍历）
            output = execute_iterate_node_with_branches(
                node, nodes, graph_data, [item for item in node_inputs.values()][0], runtime_data,
                engine=expr_engine
            )
            node_outputs[node_id] = output
        elif node["is_branch_node"]:
            # 提取输入值（假设只有一个输入端口）
            input_val = None
            if node_inputs:
                input_val = next(iter(node_inputs.values()))

            # 获取 execute_all_matches 参数
            execute_all_matches = node.get("execute_all_matches", False)
            selected_ports, output = execute_branch_node(node, input_val, expr_engine, execute_all_matches)
            node_outputs[node_id] = output

            # 记录激活的分支端口
            if selected_ports:
                active_branch_outputs[node_id] = selected_ports if execute_all_matches else selected_ports[0]
                logger.info(f"分支节点 {node['name']} 激活端口: {selected_ports}")
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
                    params=node_params,
                    inputs=node_inputs,
                    global_variable=global_variable,
                    logger=logger
                )
                # 更新全局变量中的节点输出
                for port in output:
                    if f"{node['name']}_{port}" in global_variable["node_vars"]:
                        if global_variable["node_vars"][f"{node['name']}_{port}"]["update_policy"] == "更新":
                            global_variable["node_vars"][f"{node['name']}_{port}"]["value"] = output[port]
                        elif global_variable["node_vars"][f"{node['name']}_{port}"]["update_policy"] == "追加":
                            current_value = global_variable["node_vars"][f"{node['name']}_{port}"]["value"]
                            value = output[port]
                            try:
                                # --- 处理字符串 ---
                                if isinstance(current_value, list):
                                    if isinstance(value, list):
                                        update_value = current_value + value
                                    else:
                                        # 如果当前是列表，但新值不是列表，将新值作为一个元素追加
                                        update_value = current_value + [value]
                                # --- 处理字典 ---
                                elif isinstance(current_value, dict):
                                    if isinstance(value, dict):
                                        # 合并字典，新值会覆盖同名键的旧值
                                        update_value = {**current_value, **value}
                                # --- 其他类型 ---
                                else:
                                    # 对于其他类型，尝试直接相加，如果失败则覆盖
                                    update_value = [current_value, value]
                            except Exception as e:
                                update_value = value
                            global_variable["node_vars"][f"{node['name']}_{port}"]["value"] = update_value
                expr_engine.update_global_vars(GlobalVariableContext(**global_variable))
                logger.info(f"输出: {output}")
                node_outputs[node_id] = output or {}
            except Exception as e:
                logger.error(f"节点执行失败 {node['name']}: {traceback.format_exc()}")
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

    result_path = result_path if result_path else project_dir / "result.pkl"
    with open(result_path, 'wb') as f:
        pickle.dump(final_outputs, f)


if __name__ == "__main__":

    # ==================== 配置 ====================
    logger.remove()  # 禁用默认 handler
    NODE_ID = uuid.uuid4().hex
    (Path(__file__).parent.parent / "run.log").unlink(missing_ok=True)
    # 日志配置（与原逻辑一致）
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