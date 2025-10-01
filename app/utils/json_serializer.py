# -*- coding: utf-8 -*-
import numpy as np


def output_serializable(obj):
    """将对象转换为 JSON 可序列化的格式"""
    if isinstance(obj, np.ndarray):
        return obj.tolist()  # 转换为 Python list
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, dict):
        return {key: output_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [output_serializable(item) for item in obj]
    else:
        return obj