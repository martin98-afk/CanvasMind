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


def set_property(canvas_path, node_id, property_name, value):
    """设置节点属性"""
    workflow_path = find_workflow_json(canvas_path)
    if not workflow_path.exists():
        return {"error": f"Canvas not found: {canvas_path}"}

    with open(workflow_path, "r", encoding="utf-8") as f:
        workflow = json.load(f)

    if node_id not in workflow["graph"]["nodes"]:
        return {"error": f"Node not found: {node_id}"}

    # 尝试解析 JSON 值
    try:
        value = json.loads(value)
    except:
        pass

    node = workflow["graph"]["nodes"][node_id]
    # 属性存储在 custom.params 中
    if "params" not in node["custom"]:
        node["custom"]["params"] = {}
    node["custom"]["params"][property_name] = value

    with open(workflow_path, "w", encoding="utf-8") as f:
        json.dump(workflow, f, ensure_ascii=False, indent=2)

    return {"id": node_id, "prop": property_name, "val": value}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="设置节点属性")
    parser.add_argument("--canvas-path", required=True)
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--property", required=True)
    parser.add_argument("--value", required=True)
    args = parser.parse_args()

    result = set_property(args.canvas_path, args.node_id, args.property, args.value)
    print(json.dumps(result, ensure_ascii=False, indent=2))
