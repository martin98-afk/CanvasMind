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


def list_canvases():
    """列出所有画布"""
    workflows_dir = PROJECT_DIR / "canvas_files" / "workflows"
    if not workflows_dir.exists():
        return {"items": []}

    items = []
    for folder in workflows_dir.iterdir():
        if folder.is_dir():
            wf_files = list(folder.glob("*.workflow.json"))
            if wf_files:
                items.append({"name": folder.name, "path": str(folder)})

    return {"total": len(items), "items": items}


if __name__ == "__main__":
    result = list_canvases()
    print(json.dumps(result, ensure_ascii=False, indent=2))
