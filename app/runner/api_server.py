# api_server.py（优化版）
import argparse
import base64
import io
import json
import pickle
import subprocess
import sys
import tempfile
import time

import pyarrow as pa
from pathlib import Path
from typing import Dict, Any, Optional, List

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, UploadFile, File
from loguru import logger
from pyarrow import feather
from pydantic import BaseModel, create_model

sys.path.append(str(Path(__file__).parent))
from runner.workflow_runner import execute_workflow, deserialize_from_json

PROJECT_DIR = Path(__file__).parent
SPEC_PATH = PROJECT_DIR / "project_spec.json"

if not SPEC_PATH.exists():
    raise RuntimeError("project_spec.json 未找到！")

with open(SPEC_PATH, 'r', encoding='utf-8') as f:
    project_spec = deserialize_from_json(json.load(f))


def serialize_for_json(obj, large_list_threshold=1000):
    """递归将对象转换为 JSON 可序列化格式"""
    if isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return obj
    elif isinstance(obj, pd.DataFrame):
        try:
            # 使用 BytesIO 作为虚拟文件
            buffer = io.BytesIO()
            # 写入 feather 格式
            table = pa.Table.from_pandas(obj)
            feather.write_feather(table, buffer, compression='zstd')  # zstd 压缩率高
            # 获取二进制数据并编码
            buffer.seek(0)
            binary_data = buffer.read()
            encoded_data = base64.b64encode(binary_data).decode('utf-8')

            return {
                "__type__": "DataFrame",
                "data": encoded_data,
                "format": "feather_base64",
                "shape": obj.shape  # 便于调试
            }
        except Exception as e:
            logger.error(f"DataFrame Feather serialization failed: {e}")
    elif isinstance(obj, pd.Series):
        try:
            df_temp = obj.to_frame()
            return serialize_for_json(df_temp)
        except Exception:
            return f"<Series {len(obj)}> (无法序列化)"
    elif isinstance(obj, np.ndarray):
        try:
            # 将 ndarray 转换为二进制格式 (bytes)
            buffer = io.BytesIO()
            np.save(buffer, obj, allow_pickle=False)  # allow_pickle=False 更安全
            binary_data = buffer.getvalue()
            # 将二进制数据编码为 base64 字符串
            encoded_data = base64.b64encode(binary_data).decode('utf-8')

            return {
                "__type__": "ndarray",
                "data": encoded_data,  # 存储 base64 编码的二进制数据
                "dtype": str(obj.dtype),
                "shape": obj.shape,  # 存储形状信息，便于调试或验证
                "format": "npy_base64"  # 标记格式
            }
        except Exception as e:
            print(f"ndarray binary serialization failed: {e}")
            # 降级：如果二进制方式失败，再尝试 tolist
            try:
                return {
                    "__type__": "ndarray",
                    "data": obj.tolist(),
                    "dtype": str(obj.dtype),
                    "format": "list"  # 标记为降级格式
                }
            except Exception as e2:
                print(f"ndarray list serialization also failed: {e2}")
                return f"<ndarray {obj.shape} {obj.dtype}> (无法序列化)"
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif hasattr(obj, 'serialize') and callable(getattr(obj, 'serialize')):
        # 如果对象自己有 serialize 方法（如你的 ArgumentType）
        try:
            return obj.serialize()
        except:
            return str(obj)
    elif hasattr(obj, '__dict__'):
        # 通用对象：保存类名和 __dict__
        try:
            return {
                "__type__": f"{obj.__class__.__module__}.{obj.__class__.__name__}",
                "__data__": serialize_for_json(obj.__dict__)
            }
        except Exception:
            return str(obj)
    else:
        # 其他类型：尝试转为字符串
        try:
            json.dumps(obj)  # 测试是否可序列化
            return obj
        except (TypeError, ValueError):
            return str(obj)


def get_pydantic_type(format_str: str, schema_def: Optional[Dict] = None):
    """根据 format 和 schema 返回 Pydantic 类型"""
    if format_str == "TEXT":
        return str
    elif format_str == "LONGTEXT":
        return str
    elif format_str == "INT":
        return int
    elif format_str == "FLOAT":
        return float
    elif format_str == "BOOL":
        return bool
    elif format_str == "JSON":
        return dict
    elif format_str == "ARRAY[TEXT]":
        return List[str]
    elif format_str == "ARRAY[INT]":
        return List[int]
    elif format_str == "ARRAY[FLOAT]":
        return List[float]
    elif format_str == "ARRAY[JSON]":
        return List[dict]
    elif format_str == "ARRAY[BOOL]":
        return List[bool]
    elif format_str.startswith("ARRAY"):
        return List[Any]
    elif format_str in ["FILE", "EXCEL", "SKLEARNMODEL", "TORCHMODEL", "UPLOAD", "IMAGE"]:
        return UploadFile  # 文件类型用 UploadFile
    elif format_str == "DYNAMICFORM" and schema_def:
        # 为 DYNAMICFORM 动态创建嵌套模型
        nested_fields = {}
        for field_name, field_def in schema_def.items():
            field_type = get_pydantic_type(field_def.get("type", "TEXT"))
            nested_fields[field_name] = (field_type, ...)
        NestedModel = create_model(f"DynamicForm_{id(schema_def)}", **nested_fields)
        return List[NestedModel]
    elif format_str == "RANGE":
        return float  # 或 int，但统一用 float 更安全
    else:
        return str


def is_file_type(format_str: str) -> bool:
    """判断是否为文件类型"""
    return format_str in ["FILE", "EXCEL", "SKLEARNMODEL", "TORCHMODEL", "UPLOAD", "IMAGE"]


# === 构建 InputModel ===
input_fields = {}
input_file_map = {}  # 记录哪些字段是文件

for key, cfg in project_spec.get("inputs", {}).items():
    fmt = cfg.get("format", "TEXT")
    schema_def = cfg.get("schema", None)

    if is_file_type(fmt):
        input_fields[key] = (Optional[UploadFile], File(None))
        input_file_map[key] = True
    else:
        pydantic_type = get_pydantic_type(fmt, schema_def)
        # 非必填（允许 None）
        input_fields[key] = (Optional[pydantic_type], None)
        input_file_map[key] = False

InputModel = create_model("InputModel", **input_fields)


class OutputModel(BaseModel):
    result: Dict[str, Any]


app = FastAPI(
    title="导出的工作流微服务",
    description="由可视化工作流自动生成的 API 服务",
    version="1.0"
)


@app.post("/run", response_model=OutputModel)
async def run_workflow(input: InputModel):
    try:
        external_inputs = {}

        for key, cfg in project_spec.get("inputs", {}).items():
            value = getattr(input, key)

            if input_file_map.get(key, False) and value is not None:
                # 保存上传文件
                suffix = Path(value.filename).suffix if value.filename else ""
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    content = await value.read()
                    tmp.write(content)
                    tmp_path = tmp.name
                external_inputs[key] = tmp_path
            else:
                external_inputs[key] = value
        with open("input.pkl", "wb") as f:
            pickle.dump(external_inputs, f)
        with open("model.workflow.json", 'r', encoding='utf-8') as f:
            full_data = json.load(f)
        runtime_data = full_data.get("runtime", {})
        python_executable = runtime_data.get("environment_exe", sys.executable)
        proc = subprocess.Popen(
            [python_executable, Path(__file__).parent / "runner" / "workflow_runner.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            encoding='utf-8'
        )
        while proc.poll() is None:
            time.sleep(1)

        # 获取原始 outputs（dict）
        with open(Path(__file__).parent / "result.pkl", "rb") as f:
            outputs = pickle.load(f)

        # 判断是否为 MCP 调用（通过 header 或 query param）
        is_mcp = (
                request.headers.get("x-mcp") == "true" or
                "mcp" in str(request.url.query).lower()
        )

        if is_mcp:
            # MCP 格式：content: [{type: "text", text: JSON字符串}]
            result_str = json.dumps(serialize_for_json(outputs), ensure_ascii=False, default=str)
            return JSONResponse({
                "content": [{"type": "text", "text": result_str}]
            })
        else:
            # 传统格式（兼容你现有的测试）
            return {"result": serialize_for_json(outputs)}

    except Exception as e:
        logger.exception("工作流执行失败")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/spec")
def get_spec():
    return project_spec


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000, help="服务端口")
    parser.add_argument("--python", type=str, default=None, help="画布运行python环境")
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="info")