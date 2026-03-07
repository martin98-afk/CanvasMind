# -*- coding: utf-8 -*-
import sys
import json
import uuid
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
from runner.scan_components import scan_components


def find_workflow_json(canvas_path):
    """查找画布的 workflow.json 文件"""
    canvas_folder = Path(canvas_path)
    if canvas_folder.is_file():
        return canvas_folder
    for f in canvas_folder.glob("*.workflow.json"):
        return f
    return canvas_folder / f"{canvas_folder.name}.workflow.json"


def add_node(canvas_path, component_full_path, node_name=None, x=None, y=None):
    """添加节点到画布"""
    workflow_path = find_workflow_json(canvas_path)
    if not workflow_path.exists():
        return {"error": f"Canvas not found: {canvas_path}"}

    with open(workflow_path, "r", encoding="utf-8") as f:
        workflow = json.load(f)

    components_dir = APP_DIR / "components"
    comp_map, file_map = scan_components(str(components_dir))

    component_class = None
    file_path = ""

    if component_full_path in comp_map:
        component_class = comp_map[component_full_path]
        file_path = str(file_map.get(component_full_path, ""))
        if file_path:
            file_path = Path(file_path).stem

    if node_name is None:
        if component_class:
            node_name = getattr(
                component_class, "name", component_full_path.split("/")[-1]
            )
        else:
            node_name = component_full_path.split("/")[-1]

    node_id = f"0x{uuid.uuid4().hex[:12]}"
    position = [x or 100.0, y or 100.0]

    input_ports = []
    output_ports = []

    if component_class:
        for port in getattr(component_class, "inputs", []):
            input_ports.append(
                {"name": port.name, "multi_connection": False, "display_name": True}
            )
        for port in getattr(component_class, "outputs", []):
            output_ports.append(
                {"name": port.name, "multi_connection": True, "display_name": True}
            )

    node_data = {
        "type_": f"dynamic.StatusDynamicNode_{file_path}"
        if file_path
        else "dynamic.DYNAMIC_CODE",
        "icon": "",
        "name": node_name,
        "color": [139, 115, 85, 255],
        "border_color": [74, 84, 85, 255],
        "text_color": [255, 255, 255, 180],
        "disabled": False,
        "selected": False,
        "visible": True,
        "width": 0.0,
        "height": 0.0,
        "pos": position,
        "layout_direction": 0,
        "port_deletion_allowed": True,
        "subgraph_session": {},
        "input_ports": input_ports,
        "output_ports": output_ports,
        "custom": {
            "persistent_id": str(uuid.uuid4()),
            "_collapsed": False,
            "_exec_mode": "subprocess",
            "_data_select": {},
            "version": "latest",
            "FULL_PATH": component_full_path,
            "FILE_PATH": file_path if file_path else None,
        },
        "output_values": {},
    }

    workflow["graph"]["nodes"][node_id] = node_data

    with open(workflow_path, "w", encoding="utf-8") as f:
        json.dump(workflow, f, ensure_ascii=False, indent=2)

    return {
        "id": node_id,
        "name": node_name,
        "path": component_full_path,
        "pos": position,
        "ports": {
            "in": [p["name"] for p in input_ports],
            "out": [p["name"] for p in output_ports],
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="添加节点")
    parser.add_argument("--canvas-path", required=True, help="画布路径")
    parser.add_argument("--component", required=True, help="组件路径")
    parser.add_argument("--node-name", help="节点名称")
    parser.add_argument("--x", type=float, help="X 坐标")
    parser.add_argument("--y", type=float, help="Y 坐标")
    args = parser.parse_args()

    result = add_node(args.canvas_path, args.component, args.node_name, args.x, args.y)
    print(json.dumps(result, ensure_ascii=False, indent=2))
