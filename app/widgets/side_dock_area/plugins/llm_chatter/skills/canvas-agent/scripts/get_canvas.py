# -*- coding: utf-8 -*-
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


def find_workflow_json(canvas_path):
    canvas_folder = Path(canvas_path)
    for f in canvas_folder.glob("*.workflow.json"):
        return f
    return canvas_folder / f"{canvas_folder.name}.workflow.json"


def get_canvas(canvas_path):
    """获取画布信息 - 精简格式"""
    workflow_path = find_workflow_json(canvas_path)
    if not workflow_path.exists():
        return {"error": f"Canvas not found: {canvas_path}"}

    with open(workflow_path, "r", encoding="utf-8") as f:
        workflow = json.load(f)

    nodes = []
    for node_id, node_data in workflow["graph"]["nodes"].items():
        custom = node_data.get("custom", {})
        nodes.append(
            {
                "id": node_id,
                "name": node_data["name"],
                "path": custom.get("FULL_PATH", ""),
                "pos": node_data["pos"],
                "in": [p["name"] for p in node_data.get("input_ports", [])],
                "out": [p["name"] for p in node_data.get("output_ports", [])],
            }
        )

    return {
        "path": str(workflow_path),
        "nodes": nodes,
        "conns": workflow["graph"]["connections"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="获取画布信息")
    parser.add_argument("--canvas-path", required=True)
    args = parser.parse_args()

    result = get_canvas(args.canvas_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
