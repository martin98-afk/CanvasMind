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
from runner.scan_components import scan_components


def get_component_details(full_path):
    """获取组件详情"""
    components_dir = APP_DIR / "components"
    comp_map, file_map = scan_components(str(components_dir))

    if full_path not in comp_map:
        return {"error": f"Component not found: {full_path}"}

    component_class = comp_map[full_path]
    category, name = (
        full_path.split("/", 1) if "/" in full_path else ("未分类", full_path)
    )

    # 提取输入端口
    inputs = []
    for port in getattr(component_class, "inputs", []):
        inputs.append(
            {
                "name": port.name,
                "label": port.label,
                "type": str(port.type.value)
                if hasattr(port.type, "value")
                else str(port.type),
                "connection": str(port.connection.value)
                if hasattr(port.connection, "value")
                else str(port.connection),
            }
        )

    # 提取输出端口
    outputs = []
    for port in getattr(component_class, "outputs", []):
        outputs.append(
            {
                "name": port.name,
                "label": port.label,
                "type": str(port.type.value)
                if hasattr(port.type, "value")
                else str(port.type),
            }
        )

    # 提取属性
    properties = []
    for prop_name, prop_def in getattr(component_class, "properties", {}).items():
        properties.append(
            {
                "name": prop_name,
                "type": str(prop_def.type.value)
                if hasattr(prop_def.type, "value")
                else str(prop_def.type),
                "label": prop_def.label,
                "default": prop_def.default,
                "choices": prop_def.choices,
                "description": prop_def.description,
            }
        )

    return {
        "path": full_path,
        "cat": category,
        "name": name,
        "desc": getattr(component_class, "description", ""),
        "req": getattr(component_class, "requirements", ""),
        "in": inputs,
        "out": outputs,
        "props": properties,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="获取组件详情")
    parser.add_argument("--full-path", required=True, help="组件完整路径")
    args = parser.parse_args()

    result = get_component_details(args.full_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
