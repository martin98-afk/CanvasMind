# -*- coding: utf-8 -*-
import json
import pickle
import subprocess
import sys
import os
import time
from pathlib import Path

from loguru import logger

# 添加当前目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from runner.workflow_runner import execute_workflow, deserialize_from_json

if __name__ == "__main__":
    # 可以传入外部输入参数
    with open("model.workflow.json", 'r', encoding='utf-8') as f:
        full_data = deserialize_from_json(json.load(f))
    runtime_data = full_data.get("runtime", {})
    python_executable = runtime_data.get("environment_exe", sys.executable)
    proc = subprocess.Popen(
        [python_executable, Path(__file__).parent / "runner" / "workflow_runner.py"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        encoding='utf-8'
    )
    while proc.poll() is None:
        logger.info("等待模型执行完成...")
        time.sleep(1)
    with open(Path(__file__).parent / "result.pkl", "rb") as f:
        outputs = pickle.load(f)
    logger.info("模型执行完成，输出:")
    for node_id, output in outputs.items():
        logger.info(f"  {node_id}: {output}")