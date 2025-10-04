# -*- coding: utf-8 -*-
import sys
import os

# 添加当前目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from runner.workflow_runner import execute_workflow

if __name__ == "__main__":
    # 可以传入外部输入参数
    # inputs = {"node_id": {"input_port": "value"}}
    outputs = execute_workflow("model.workflow.json")
    print("模型执行完成，输出:")
    for node_id, output in outputs.items():
        print(f"  {node_id}: {output}")
