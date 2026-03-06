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


def connect_nodes(canvas_path, from_node_id, from_port, to_node_id, to_port):
    """连接节点 - 使用正确的格式"""
    workflow_path = find_workflow_json(canvas_path)
    if not workflow_path.exists():
        return {"error": f"Canvas not found: {canvas_path}"}

    with open(workflow_path, "r", encoding="utf-8") as f:
        workflow = json.load(f)

    # 正确的连接格式：{"out": [node_id, port], "in": [node_id, port]}
    connection = {"out": [from_node_id, from_port], "in": [to_node_id, to_port]}

    if "connections" not in workflow["graph"]:
        workflow["graph"]["connections"] = []

    workflow["graph"]["connections"].append(connection)

    with open(workflow_path, "w", encoding="utf-8") as f:
        json.dump(workflow, f, ensure_ascii=False, indent=2)

    return {
        "from_node": from_node_id,
        "from_port": from_port,
        "to_node": to_node_id,
        "to_port": to_port,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="连接节点")
    parser.add_argument("--canvas-path", required=True)
    parser.add_argument("--from-node", required=True)
    parser.add_argument("--from-port", required=True)
    parser.add_argument("--to-node", required=True)
    parser.add_argument("--to-port", required=True)
    args = parser.parse_args()

    result = connect_nodes(
        args.canvas_path, args.from_node, args.from_port, args.to_node, args.to_port
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
