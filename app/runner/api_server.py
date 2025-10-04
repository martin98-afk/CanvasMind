# -*- coding: utf-8 -*-
from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.responses import JSONResponse
import tempfile
import json

from app.runner.workflow_runner import execute_workflow

app = FastAPI()

@app.post("/run/{workflow_name}")
async def run_workflow_api(workflow_name: str, inputs: dict = None):
    try:
        result = execute_workflow(f"workflows/{workflow_name}.workflow.json", inputs)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)