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
from runner.workflow_runner import execute_workflow, deserialize_from_json

# --- 配置与初始化 ---
PROJECT_DIR = Path(__file__).parent
SPEC_PATH = PROJECT_DIR / "project_spec.json"
WORKFLOW_JSON_PATH = PROJECT_DIR / "model.workflow.json"

if not SPEC_PATH.exists():
    raise RuntimeError("project_spec.json 未找到！")

with open(SPEC_PATH, 'r', encoding='utf-8') as f:
    project_spec = deserialize_from_json(json.load(f))


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
        outputs = await asyncio.to_thread(
            execute_workflow, WORKFLOW_JSON_PATH, external_inputs, return_result=True, logger=request_logger
        )

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