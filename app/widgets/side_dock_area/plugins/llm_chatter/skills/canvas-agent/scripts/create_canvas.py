# -*- coding: utf-8 -*-
import os
import sys
import json
from pathlib import Path

# 动态计算项目路径
SCRIPT_DIR = Path(__file__).parent.absolute()
current = SCRIPT_DIR
while current.name != "app" and current.parent != current:
    current = current.parent
APP_DIR = current
PROJECT_DIR = APP_DIR.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(PROJECT_DIR))

import argparse


def create_canvas(name, description=""):
    """创建新画布 - workflows 格式"""
    workflows_dir = PROJECT_DIR / "canvas_files" / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)

    canvas_folder = workflows_dir / name
    canvas_folder.mkdir(parents=True, exist_ok=True)

    python_exe_name = "python.exe" if os.name == "nt" else "bin/python"
    workflow_json = {
        "graph": {
            "graph": {
                "layout_direction": 0,
                "acyclic": True,
                "pipe_collision": False,
                "pipe_slicing": True,
                "pipe_style": 1,
            },
            "nodes": {},
            "connections": [],
            "global_variables": {
                "env": {
                    "user_id": None,
                    "canvas_id": None,
                    "session_id": None,
                    "run_id": None,
                    "metadata": {
                        "TZ": "Asia/Shanghai",
                        "LANG": "en_US.UTF-8",
                        "LC_ALL": "en_US.UTF-8",
                        "OMP_NUM_THREADS": "1",
                        "MKL_NUM_THREADS": "1",
                        "OPENBLAS_NUM_THREADS": "1",
                        "NUMEXPR_NUM_THREADS": "1",
                        "CUDA_VISIBLE_DEVICES": "0",
                        "PYTHONPATH": ".",
                        "PYTHONUNBUFFERED": "1",
                        "PYTHONIOENCODING": "utf-8",
                        "PYTHONWARNINGS": "ignore",
                    },
                },
                "custom": {},
                "custom_order": [],
                "node_vars": {},
                "node_vars_order": [],
            },
        },
        "runtime": {
            "environment": {
                "name": "3.11",
                "type": "local",
                "path": str(
                    PROJECT_DIR / "envs" / "miniconda" / "envs" / "3.11" / python_exe_name
                ),
            }
        },
    }

    workflow_path = canvas_folder / f"{name}.workflow.json"
    with open(workflow_path, "w", encoding="utf-8") as f:
        json.dump(workflow_json, f, ensure_ascii=False, indent=2)

    return {
        "name": name,
        "path": str(canvas_folder),
        "workflow": str(workflow_path),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="创建画布")
    parser.add_argument("--name", required=True, help="画布名称")
    parser.add_argument("--description", default="", help="画布描述")
    args = parser.parse_args()

    result = create_canvas(args.name, args.description)
    print(json.dumps(result, ensure_ascii=False, indent=2))
