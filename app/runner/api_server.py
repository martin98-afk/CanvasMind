import base64
import asyncio
import base64
import io
import json
import os
import sys
import tempfile
import traceback
import uuid
from pathlib import Path
from threading import Lock
from typing import Any, Optional, List

import numpy as np
import orjson
import pandas as pd
import pyarrow as pa
from fastapi import FastAPI, HTTPException, UploadFile, File, Request, BackgroundTasks
from loguru import logger
from pyarrow import feather
from pydantic import create_model
from starlette.responses import Response

# --- 导入你的原有逻辑函数 ---
# 假设这些函数在 runner/workflow_runner.py 中，确保路径正确
sys.path.append(str(Path(__file__).parent))
from runner.workflow_runner import (
    deserialize_from_json, scan_components, build_execution_graph,
    get_downstream_nodes, execute_branch_node, evaluate_model_inputs,
    evaluate_model_params, run_component_in_subprocess, update_global_variable,
    GlobalVariableContext, ExpressionEngine
)

# --- 配置与初始化 ---
PROJECT_DIR = Path(__file__).parent
SPEC_PATH = PROJECT_DIR / "project_spec.json"
WORKFLOW_JSON_PATH = PROJECT_DIR / "model.workflow.json"

if not SPEC_PATH.exists():
    raise RuntimeError("project_spec.json 未找到！")

with open(SPEC_PATH, 'r', encoding='utf-8') as f:
    project_spec = deserialize_from_json(json.load(f))

# 预扫描组件，避免每次请求都扫磁盘
cached_component_map, cached_file_map = scan_components(components_dir=PROJECT_DIR / "components", logger=logger)


# --- 序列化优化 ---
def serialize_for_json(obj):
    """极致优化的序列化逻辑"""
    if isinstance(obj, pd.DataFrame):
        buffer = io.BytesIO()
        table = pa.Table.from_pandas(obj)
        feather.write_feather(table, buffer, compression='zstd')
        return {
            "__type__": "DataFrame",
            "data": base64.b64encode(buffer.getvalue()).decode('utf-8'),
            "format": "feather_base64"
        }
    elif isinstance(obj, np.ndarray):
        buffer = io.BytesIO()
        np.save(buffer, obj, allow_pickle=False)
        return {
            "__type__": "ndarray",
            "data": base64.b64encode(buffer.getvalue()).decode('utf-8'),
            "dtype": str(obj.dtype),
            "shape": obj.shape,
            "format": "npy_base64"
        }
    elif isinstance(obj, (np.integer, np.floating, np.bool_)):
        return obj.item()
    elif isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [serialize_for_json(x) for x in obj]
    elif hasattr(obj, 'serialize') and callable(obj.serialize):
        return obj.serialize()
    else:
        try:
            # 尝试用 orjson 测试基本类型
            orjson.dumps(obj)
            return obj
        except:
            return str(obj)


# --- Pydantic 模型动态构建 ---
def get_pydantic_type(format_str: str):
    mapping = {
        "INT": int, "FLOAT": float, "BOOL": bool,
        "JSON": dict, "ARRAY": list, "TEXT": str, "LONGTEXT": str
    }
    return mapping.get(format_str.split('[')[0], str)


def is_file_type(format_str: str) -> bool:
    return format_str in ["FILE", "EXCEL", "SKLEARNMODEL", "TORCHMODEL", "UPLOAD", "IMAGE"]


input_fields = {}
input_file_map = {}
for key, cfg in project_spec.get("inputs", {}).items():
    fmt = cfg.get("format", "TEXT")
    if is_file_type(fmt):
        input_fields[key] = (Optional[UploadFile], File(None))
        input_file_map[key] = True
    else:
        input_fields[key] = (Optional[get_pydantic_type(fmt)], None)
        input_file_map[key] = False

InputModel = create_model("InputModel", **input_fields)


# --- 核心执行引擎（重构版，去除全局变量依赖） ---
def execute_workflow_optimized(external_inputs=None, logger_in=logger):
    """
    完全在内存中运行的工作流逻辑。
    消除了 global 变量，通过局部变量保证线程安全。
    """
    workflow_path = WORKFLOW_JSON_PATH
    with open(workflow_path, 'r', encoding='utf-8') as f:
        full_data = deserialize_from_json(json.load(f))

    graph_data = full_data["graph"]
    runtime_data = full_data.get("runtime", {})
    execution_order_raw = runtime_data.get("execution_order", None)

    # 局部上下文
    local_global_variable = runtime_data.get("global_variable", {})
    global_ctx = GlobalVariableContext(**local_global_variable)
    local_expr_engine = ExpressionEngine(global_vars_context=global_ctx)

    # 使用预缓存的组件
    component_map, file_map = cached_component_map, cached_file_map

    nodes = {}
    for node_id, node_data in graph_data["nodes"].items():
        stable_key = runtime_data.get("node_id2stable_key", {}).get(node_id)
        if not stable_key: continue

        full_path = stable_key.split("||")[0]
        comp_cls = component_map.get(full_path, node_data["type_"])
        file_path_comp = file_map.get(full_path)

        params = node_data["custom"].get("params", {})
        input_values = node_data["custom"].get("input_values", {})

        nodes[node_id] = {
            "node_id": node_id,
            "persistent_id": params.get("persistent_id"),
            "exec_mode": params.get("_exec_mode"),
            "class": comp_cls,
            "file_path": file_path_comp,
            "name": node_data["name"],
            "params": params,
            "input_values": input_values,
            "is_loop_node": (node_data.get("type_") == "control_flow.ControlFlowLoopNode"),
            "is_iterate_node": (node_data.get("type_") == "control_flow.ControlFlowIterateNode"),
            "is_branch_node": (node_data.get("type_") == "control_flow.ControlFlowBranchNode"),
            "output_ports": node_data.get("output_ports", []),
            "multi_input": node_data.get("input_ports_multi", {}),
            "conditions": node_data["custom"]["params"].get("conditions", [])
        }

    # 注入外部输入
    if external_inputs:
        for input_key, cfg in project_spec.get("inputs", {}).items():
            if input_key in external_inputs:
                node_id = cfg["node_id"]
                if node_id in nodes:
                    val = external_inputs[input_key]
                    if cfg["type"] == "组件超参数":
                        nodes[node_id]["params"][cfg["param_name"]] = val
                    else:
                        nodes[node_id]["input_values"][cfg["port_name"]] = val

    execution_order, _, _ = build_execution_graph(nodes, graph_data, execution_order_raw)

    node_outputs = {}
    disabled_nodes = set()
    outputs_lock = Lock()

    for node_id in execution_order:
        if node_id in disabled_nodes: continue

        node = nodes[node_id]

        # 聚合输入
        node_inputs = {}
        local_vars_for_inputs = {}

        # 处理连接
        for conn in graph_data["connections"]:
            if conn["in"][0] == node_id:
                out_nid, out_port = conn["out"]
                in_port = conn["in"][1]
                upstream_name = nodes[out_nid]["name"].replace(" ", "_")

                with outputs_lock:
                    val = node_outputs.get(out_nid, {}).get(out_port)

                if node["multi_input"].get(in_port):
                    if in_port not in node_inputs: node_inputs[in_port] = []
                    node_inputs[in_port].append(val)
                else:
                    node_inputs[in_port] = val

                local_vars_for_inputs[f"input_{upstream_name}__{out_port}"] = val

        # 执行节点 (简化演示，实际应包含你的分支/循环逻辑)
        if node["is_branch_node"]:
            # ... 调用你原有的 branch 处理 ...
            # 这里为了篇幅省略，逻辑与你提供的相同，但使用局部变量
            pass
        else:
            evaluated_inputs = evaluate_model_inputs(node_inputs, local_vars=local_vars_for_inputs)
            evaluated_params = evaluate_model_params(node["params"], local_vars=local_vars_for_inputs)

            logger_in.info(f"Running node: {node['name']}")
            output = run_component_in_subprocess(
                comp_class=node["class"],
                node_id=node["persistent_id"],
                file_path=node["file_path"],
                params=evaluated_params,
                inputs=evaluated_inputs,
                global_variable=local_global_variable,
                logger=logger_in
            )
            node_outputs[node_id] = output or {}

    # 提取最终输出
    final_results = {}
    for out_key, out_cfg in project_spec.get("outputs", {}).items():
        nid, p_name = out_cfg["node_id"], out_cfg["output_name"]
        final_results[out_key] = node_outputs.get(nid, {}).get(p_name)

    return final_results


# --- FastAPI 接口 ---
app = FastAPI(title="极速优化版工作流服务")


class OrjsonResponse(Response):
    media_type = "application/json"

    def render(self, content: Any) -> bytes:
        return orjson.dumps(content, option=orjson.OPT_SERIALIZE_NUMPY)


def cleanup_temp_files(file_paths: List[str]):
    for path in file_paths:
        try:
            if os.path.exists(path):
                os.remove(path)
                logger.debug(f"已清理临时文件: {path}")
        except Exception as e:
            logger.error(f"清理失败: {path}, {e}")


@app.post("/run", response_class=OrjsonResponse)
async def run_workflow(request: Request, input_data: InputModel, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    temp_files = []

    try:
        # 1. 准备输入
        external_inputs = {}
        for key, cfg in project_spec.get("inputs", {}).items():
            val = getattr(input_data, key)
            if input_file_map.get(key) and val:
                suffix = Path(val.filename).suffix
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    content = await val.read()
                    tmp.write(content)
                    tmp_path = tmp.name
                external_inputs[key] = tmp_path
                temp_files.append(tmp_path)
            else:
                external_inputs[key] = val

        # 2. 异步运行同步函数 (不阻塞主线程)
        # 传入局部 logger 以便追踪请求
        request_logger = logger.bind(task_id=task_id)
        outputs = await asyncio.to_thread(execute_workflow_optimized, external_inputs, request_logger)

        # 3. 序列化转换
        serialized_result = serialize_for_json(outputs)

        # 4. 后台清理
        if temp_files:
            background_tasks.add_task(cleanup_temp_files, temp_files)

        # 5. MCP 兼容
        is_mcp = request.headers.get("x-mcp") == "true" or "mcp" in str(request.url.query).lower()
        if is_mcp:
            return {
                "content": [{"type": "text", "text": orjson.dumps(serialized_result).decode()}]
            }

        return {"result": serialized_result}

    except Exception as e:
        logger.error(f"任务 {task_id} 失败: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, access_log=True)