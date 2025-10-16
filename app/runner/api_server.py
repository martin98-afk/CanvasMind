# api_server.py（优化版）
import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, HTTPException, UploadFile, File
from loguru import logger
from pydantic import BaseModel, create_model

sys.path.append(str(Path(__file__).parent))
from runner.workflow_runner import execute_workflow

PROJECT_DIR = Path(__file__).parent
SPEC_PATH = PROJECT_DIR / "project_spec.json"

if not SPEC_PATH.exists():
    raise RuntimeError("project_spec.json 未找到！")

with open(SPEC_PATH, 'r', encoding='utf-8') as f:
    project_spec = json.load(f)


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

        outputs = execute_workflow(
            str(PROJECT_DIR / "model.workflow.json"),
            external_inputs=external_inputs,
            python_executable=args.python
        )
        logger.info(f"工作流执行成功，结果：{outputs}")
        return {"result": outputs}

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