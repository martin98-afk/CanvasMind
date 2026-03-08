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


def get_builtin_nodes():
    """获取内置节点"""
    builtin_nodes = [
        {
            "full_path": "触发器/触发器",
            "category": "触发器",
            "name": "触发器",
            "description": "支持手动、Webhook、定时触发。数据由 Runner 统一管理。",
            "type_": "general.trigger",
            "inputs": [{"name": "input", "label": "输入", "multi_connection": True}],
            "outputs": [{"name": "output", "label": "输出", "multi_connection": True}],
        },
        {
            "full_path": "控制流/条件分支",
            "category": "控制流",
            "name": "条件分支",
            "description": "根据条件执行不同的分支",
            "type_": "control_flow.ControlFlowBranchNode",
            "inputs": [
                {"name": "input", "label": "输入", "multi_connection": True},
                {
                    "name": "branch1_condition",
                    "label": "分支1条件",
                    "multi_connection": False,
                },
                {
                    "name": "branch2_condition",
                    "label": "分支2条件",
                    "multi_connection": False,
                },
            ],
            "outputs": [
                {"name": "branch1", "label": "分支1", "multi_connection": True},
                {"name": "branch2", "label": "分支2", "multi_connection": True},
                {"name": "else", "label": "否则", "multi_connection": True},
            ],
        },
        {
            "full_path": "代码执行/代码编辑",
            "category": "代码执行",
            "name": "代码编辑",
            "description": "动态代码执行节点，支持编写 Python 代码",
            "type_": "dynamic.DYNAMIC_CODE",
            "inputs": [{"name": "input1", "label": "输入1", "multi_connection": False}],
            "outputs": [
                {"name": "html", "label": "HTML输出", "multi_connection": True}
            ],
        },
        {
            "full_path": "可视化/多媒体展示节点",
            "category": "可视化",
            "name": "多媒体展示节点",
            "description": "展示图片、视频、HTML等多媒体内容",
            "type_": "visualize.MediaNode",
            "inputs": [{"name": "data", "label": "数据", "multi_connection": True}],
            "outputs": [],
        },
        {
            "full_path": "通用/注释节点",
            "category": "通用",
            "name": "注释节点",
            "description": "用于添加注释和说明的节点",
            "type_": "general.StickyNote",
            "inputs": [],
            "outputs": [],
        },
        {
            "full_path": "控制流/循环迭代",
            "category": "控制流",
            "name": "循环迭代",
            "description": "循环迭代处理数据",
            "type_": "control_flow.LoopNode",
            "inputs": [
                {"name": "input", "label": "输入", "multi_connection": True},
                {"name": "iterable", "label": "迭代数据", "multi_connection": False},
            ],
            "outputs": [
                {"name": "output", "label": "输出", "multi_connection": True},
                {"name": "iteration", "label": "迭代项", "multi_connection": True},
                {"name": "index", "label": "索引", "multi_connection": True},
            ],
        },
        {
            "full_path": "控制流/并行执行",
            "category": "控制流",
            "name": "并行执行",
            "description": "并行执行多个分支",
            "type_": "control_flow.ParallelNode",
            "inputs": [{"name": "input", "label": "输入", "multi_connection": True}],
            "outputs": [
                {"name": "output1", "label": "输出1", "multi_connection": True},
                {"name": "output2", "label": "输出2", "multi_connection": True},
                {"name": "output3", "label": "输出3", "multi_connection": True},
            ],
        },
        {
            "full_path": "数据/变量节点",
            "category": "数据",
            "name": "变量节点",
            "description": "定义和管理变量",
            "type_": "data.VariableNode",
            "inputs": [{"name": "input", "label": "输入", "multi_connection": True}],
            "outputs": [{"name": "output", "label": "输出", "multi_connection": True}],
        },
    ]
    return builtin_nodes


def find_components(category=None, search=None, limit=None):
    """查找组件 - 返回精简格式"""
    results = []

    # 1. 获取内置节点
    builtin = get_builtin_nodes()

    for node in builtin:
        if category and category != node["category"]:
            continue
        if search:
            search_lower = search.lower()
            if (
                search_lower not in node["name"].lower()
                and search_lower not in node["description"].lower()
                and search_lower not in node["category"].lower()
            ):
                continue
        # 精简输出
        results.append(
            {
                "path": node["full_path"],
                "cat": node["category"],
                "desc": node["description"],
                "in": [p["name"] for p in node.get("inputs", [])],
                "out": [p["name"] for p in node.get("outputs", [])],
            }
        )

    # 2. 获取自定义组件
    components_dir = APP_DIR / "components"
    if components_dir.exists():
        comp_map, file_map = scan_components(str(components_dir))

        for full_path, component_class in comp_map.items():
            category_name, name = (
                full_path.split("/", 1) if "/" in full_path else ("未分类", full_path)
            )

            if category and category != category_name:
                continue
            if search:
                search_lower = search.lower()
                desc = getattr(component_class, "description", "")
                if (
                    search_lower not in name.lower()
                    and search_lower not in desc.lower()
                ):
                    continue

            inputs = [p.name for p in getattr(component_class, "inputs", [])]
            outputs = [p.name for p in getattr(component_class, "outputs", [])]

            # 精简输出
            results.append(
                {
                    "path": full_path,
                    "cat": category_name,
                    "desc": getattr(component_class, "description", "")[:100],
                    "in": inputs,
                    "out": outputs,
                }
            )

    if limit:
        results = results[:limit]

    return {"total": len(results), "items": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="列出组件")
    parser.add_argument("--category", help="按类别筛选")
    parser.add_argument("--search", help="关键词搜索")
    parser.add_argument("--limit", type=int, help="限制数量")
    args = parser.parse_args()

    result = find_components(
        category=args.category, search=args.search, limit=args.limit
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
