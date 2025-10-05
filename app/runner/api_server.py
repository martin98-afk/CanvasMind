# api_service.py（完整修正版）
import json
import sys
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional
import argparse  # ← 新增

from fastapi import FastAPI, HTTPException, UploadFile
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


def infer_type(value):
    if value is None:
        return str
    if isinstance(value, bool):
        return bool
    if isinstance(value, int):
        return int
    if isinstance(value, float):
        return float
    if isinstance(value, (list, dict)):
        return dict
    return str


input_fields = {}
input_is_file = {}

for key, cfg in project_spec.get("inputs", {}).items():
    default_val = cfg.get("current_value")
    field_type = infer_type(default_val)

    is_file = (
            isinstance(default_val, str) and
            default_val and
            any(default_val.endswith(ext) for ext in
                ('.txt', '.csv', '.json', '.onnx', '.pth', '.pt', '.bin', '.model', '.yaml', '.yml'))
    )
    input_is_file[key] = is_file

    if is_file:
        input_fields[key] = (Optional[UploadFile], None)
    else:
        input_fields[key] = (field_type, ... if field_type != str else None)

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

            if input_is_file.get(key, False) and value is not None:
                if hasattr(value, 'filename') and value.filename:
                    suffix = Path(value.filename).suffix
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                        content = await value.read()
                        tmp.write(content)
                        tmp_path = tmp.name
                    external_inputs[key] = tmp_path
                else:
                    external_inputs[key] = None
            else:
                external_inputs[key] = value

        outputs = execute_workflow(
            str(PROJECT_DIR / "model.workflow.json"),
            external_inputs=external_inputs
        )
        return {"result": outputs}

    except Exception as e:
        logger.exception("工作流执行失败")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/spec")
def get_spec():
    return project_spec


# === 支持命令行端口参数 ===
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000, help="服务端口")
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=args.port,
        log_level="info"
    )