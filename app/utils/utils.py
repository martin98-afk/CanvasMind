# -*- coding: utf-8 -*-
import json
import os
import re
import sys

import numpy as np
import pandas as pd
from PyQt5.QtGui import QIcon

# ANSI 颜色代码映射
ANSI_COLOR_MAP = {
    '30': '#000000',  # 黑色
    '31': '#ff0000',  # 红色
    '32': '#00ff00',  # 绿色
    '33': '#ffff00',  # 黄色
    '34': '#0000ff',  # 蓝色
    '35': '#ff00ff',  # 紫色
    '36': '#00ffff',  # 青色
    '37': '#ffffff',  # 白色
    '90': '#808080',  # 亮黑
    '91': '#ff5555',  # 亮红
    '92': '#50fa7b',  # 亮绿
    '93': '#f1fa8c',  # 亮黄
    '94': '#8be9fd',  # 亮蓝
    '95': '#ff79c6',  # 亮紫
    '96': '#8be9fd',  # 亮青
    '97': '#ffffff',  # 亮白
}


def ansi_to_html(text):
    """
    将 ANSI 颜色代码转换为 HTML span 标签
    """
    if not text:
        return ""

    # 移除光标控制序列（如 \x1b[2K）
    text = re.sub(r'\x1b\[[0-9;]*[ABCDHfJKmnsu]', '', text)

    # 处理颜色代码
    def replace_ansi(match):
        codes = match.group(1).split(';')
        color = None
        bold = False

        for code in codes:
            if code in ANSI_COLOR_MAP:
                color = ANSI_COLOR_MAP[code]
            elif code == '1':
                bold = True

        if color:
            style = f"color: {color};"
            if bold:
                style += " font-weight: bold;"
            return f'<span style="{style}">'
        elif bold:
            return '<span style="font-weight: bold;">'
        else:
            return '<span>'

    # 替换 ANSI 开始序列 \x1b[...m
    text = re.sub(r'\x1b\[([0-9;]*)m', replace_ansi, text)

    # 替换 ANSI 结束序列 \x1b[0m 为 </span>
    text = re.sub(r'\x1b\[0m', '</span>', text)

    # 处理剩余的 ANSI 序列（清理）
    text = re.sub(r'\x1b\[[0-9;]*m', '', text)

    # 转换换行符
    text = text.replace('\n', '<br>')

    return text


def ansi_to_rich_text(text):
    """
    将 ANSI 转换为 Qt Rich Text（备用方案）
    """
    return f"<pre style='font-family: Consolas, monospace;'>{ansi_to_html(text)}</pre>"

def resource_path(relative_path):
    """获取打包后资源文件的绝对路径"""
    if hasattr(sys, '_MEIPASS'):
        # 如果是打包后的环境
        base_path = sys._MEIPASS
    else:
        # 开发环境，直接使用当前路径
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)



def get_port_node(port):
    """安全获取端口所属节点，兼容 property 和 method"""
    node = port.node
    return node() if callable(node) else node


def get_icon(icon_name):
    icons = {}
    relative_path = "icons"
    for name in os.listdir(resource_path(relative_path)):
        if name.endswith(".png"):
            icons[name[:-4]] = os.path.join(resource_path(relative_path), name)

    return QIcon(icons.get(icon_name, "icons/icon_unknown.png"))


def serialize_for_json(obj):
    """递归将对象转换为 JSON 可序列化格式"""
    if isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [serialize_for_json(v) for v in obj]
    elif isinstance(obj, pd.DataFrame):
        # 方案1: 转为 records（列表 of 字典）
        try:
            return {
                "__type__": "DataFrame",
                "data": obj.to_dict(orient='records'),
                "columns": obj.columns.tolist(),
                "index": obj.index.tolist()
            }
        except Exception:
            # 如果包含不支持的类型（如 object），降级为字符串
            return f"<DataFrame {obj.shape}> (无法序列化)"
    elif isinstance(obj, pd.Series):
        try:
            return {
                "__type__": "Series",
                "data": obj.to_list(),
                "index": obj.index.tolist()
            }
        except Exception:
            return f"<Series {len(obj)}> (无法序列化)"
    elif isinstance(obj, np.ndarray):
        try:
            return {
                "__type__": "ndarray",
                "data": obj.tolist(),
                "dtype": str(obj.dtype)
            }
        except Exception:
            return f"<ndarray {obj.shape} {obj.dtype}> (无法序列化)"
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif hasattr(obj, 'serialize') and callable(getattr(obj, 'serialize')):
        # 如果对象自己有 serialize 方法（如你的 ArgumentType）
        try:
            return obj.serialize()
        except:
            return str(obj)
    elif hasattr(obj, '__dict__'):
        # 通用对象：保存类名和 __dict__
        try:
            return {
                "__type__": f"{obj.__class__.__module__}.{obj.__class__.__name__}",
                "__data__": serialize_for_json(obj.__dict__)
            }
        except Exception:
            return str(obj)
    else:
        # 其他类型：尝试转为字符串
        try:
            json.dumps(obj)  # 测试是否可序列化
            return obj
        except (TypeError, ValueError):
            return str(obj)


def deserialize_from_json(obj):
    if isinstance(obj, dict):
        if obj.get("__type__") == "DataFrame":
            try:
                df = pd.DataFrame(obj["data"], columns=obj["columns"])
                df.index = obj["index"]
                return df
            except Exception:
                return obj  # 降级
        elif obj.get("__type__") == "ndarray":
            try:
                return np.array(obj["data"], dtype=obj["dtype"])
            except Exception:
                return obj
        elif "__type__" in obj and "__data__" in obj:
            # 通用对象（通常不重建，只保留字典）
            return obj["__data__"]
        else:
            return {k: deserialize_from_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [deserialize_from_json(v) for v in obj]
    else:
        return obj