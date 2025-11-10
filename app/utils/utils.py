# -*- coding: utf-8 -*-
import ast
import base64
import json
import os
import pickle
import re
import sys
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.feather as feather
import io

from pathlib import Path
from PyQt5 import QtGui, QtCore
from PyQt5.QtGui import QIcon
from loguru import logger
from qfluentwidgets import FluentIcon


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


def resource_path(relative_path) -> str:
    """获取打包后资源文件的绝对路径"""
    if hasattr(sys, '_MEIPASS'):
        # 如果是打包后的环境
        base_path = sys._MEIPASS
    else:
        # 开发环境，直接使用当前路径
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def canvas_file_dump_path(dump_location: str = "canvas_files") -> Path:
    dump_path = Path(dump_location)
    dump_path.mkdir(parents=True, exist_ok=True)
    return dump_path


def get_port_node(port):
    """安全获取端口所属节点，兼容 property 和 method"""
    node = port.node
    return node() if callable(node) else node


def get_icon(icon_name):
    icons = {}
    relative_path = "icons"
    try:
        for name in os.listdir(resource_path(relative_path)):
            if name.endswith(".png"):
                icons[name[:-4]] = os.path.join(resource_path(relative_path), name)
            elif name.endswith(".svg"):
                icons[name[:-4]] = os.path.join(resource_path(relative_path), name)
            elif name.endswith(".ico"):
                icons[name[:-4]] = os.path.join(resource_path(relative_path), name)
            elif name.endswith(".jpg"):
                icons[name[:-4]] = os.path.join(resource_path(relative_path), name)

        return QIcon(icons.get(icon_name, "icons/icon_unknown.png"))
    except:
        return FluentIcon.APPLICATION


def serialize_for_json(obj, large_list_threshold=1000):
    """递归将对象转换为 JSON 可序列化格式"""
    if isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        # 检查是否是大型列表
        if len(obj) > large_list_threshold:
            try:
                # 尝试将列表转换为 numpy 数组，如果可能的话
                # 这适用于数值型列表
                try:
                    arr = np.array(obj)
                    if arr.ndim == 1:  # 确保是一维数组
                        buffer = io.BytesIO()
                        np.save(buffer, arr, allow_pickle=False)
                        binary_data = buffer.getvalue()
                        encoded_data = base64.b64encode(binary_data).decode('utf-8')

                        return {
                            "__type__": "LargeList",
                            "data": encoded_data,
                            "dtype": str(arr.dtype),
                            "format": "numpy_binary",
                            "original_type": "list" if isinstance(obj, list) else "tuple"
                        }
                except (ValueError, TypeError):
                    # 如果无法转换为 numpy 数组（例如包含混合类型），则使用 pickle
                    # pickle 通常比 tolist() 更高效，尤其是对于复杂对象
                    buffer = io.BytesIO()
                    pickle.dump(obj, buffer)
                    binary_data = buffer.getvalue()
                    encoded_data = base64.b64encode(binary_data).decode('utf-8')

                    return {
                        "__type__": "LargeList",
                        "data": encoded_data,
                        "format": "pickle_binary",
                        "original_type": "list" if isinstance(obj, list) else "tuple"
                    }
            except Exception as e:
                print(f"Large list/tuple serialization failed: {e}")
                # 降级：如果优化失败，回退到原始行为
                return [serialize_for_json(v, large_list_threshold) for v in obj]
        else:
            # 非大型列表，按常规方式处理
            return [serialize_for_json(v, large_list_threshold) for v in obj]
    elif isinstance(obj, pd.DataFrame):
        try:
            # 使用 BytesIO 作为虚拟文件
            buffer = io.BytesIO()
            # 写入 feather 格式
            table = pa.Table.from_pandas(obj)
            feather.write_feather(table, buffer, compression='zstd')  # zstd 压缩率高
            # 获取二进制数据并编码
            buffer.seek(0)
            binary_data = buffer.read()
            encoded_data = base64.b64encode(binary_data).decode('utf-8')

            return {
                "__type__": "DataFrame",
                "data": encoded_data,
                "format": "feather_base64",
                "shape": obj.shape  # 便于调试
            }
        except Exception as e:
            logger.error(f"DataFrame Feather serialization failed: {e}")
    elif isinstance(obj, pd.Series):
        try:
            df_temp = obj.to_frame()
            return serialize_for_json(df_temp)
        except Exception:
            return f"<Series {len(obj)}> (无法序列化)"
    elif isinstance(obj, np.ndarray):
        try:
            # 将 ndarray 转换为二进制格式 (bytes)
            buffer = io.BytesIO()
            np.save(buffer, obj, allow_pickle=False)  # allow_pickle=False 更安全
            binary_data = buffer.getvalue()
            # 将二进制数据编码为 base64 字符串
            encoded_data = base64.b64encode(binary_data).decode('utf-8')

            return {
                "__type__": "ndarray",
                "data": encoded_data,  # 存储 base64 编码的二进制数据
                "dtype": str(obj.dtype),
                "shape": obj.shape,  # 存储形状信息，便于调试或验证
                "format": "npy_base64"  # 标记格式
            }
        except Exception as e:
            print(f"ndarray binary serialization failed: {e}")
            # 降级：如果二进制方式失败，再尝试 tolist
            try:
                return {
                    "__type__": "ndarray",
                    "data": obj.tolist(),
                    "dtype": str(obj.dtype),
                    "format": "list"  # 标记为降级格式
                }
            except Exception as e2:
                print(f"ndarray list serialization also failed: {e2}")
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
        if obj.get("__type__") == "DataFrame" and obj.get("format") == "feather_base64":
            try:
                # 解码 base64
                binary_data = base64.b64decode(obj["data"])
                buffer = io.BytesIO(binary_data)
                # 读取 feather 格式
                table = feather.read_table(buffer)
                df = table.to_pandas()
                return df
            except Exception as e:
                print(f"DataFrame Feather deserialization failed: {e}")
                return obj
        elif obj.get("__type__") == "DataFrame":
            try:
                df = pd.DataFrame(obj["data"], columns=obj["columns"])
                df.index = obj["index"]
                return df
            except Exception:
                return obj  # 降级
        elif obj.get("__type__") == "Series":
            # 如果 Series 是通过转为 DataFrame 序列化的
            df_temp = deserialize_from_json({**obj, "__type__": "DataFrame", "format": "feather_base64"})
            if isinstance(df_temp, pd.DataFrame) and len(df_temp.columns) == 1:
                return df_temp.iloc[:, 0]
            return obj
        elif obj.get("__type__") == "LargeList":
            format_type = obj.get("format", "pickle_binary")  # 默认为 pickle
            original_type = obj.get("original_type", "list")
            if format_type == "numpy_binary":
                try:
                    binary_data = base64.b64decode(obj["data"])
                    buffer = io.BytesIO(binary_data)
                    arr = np.load(buffer, allow_pickle=False)
                    # 转回 Python 列表或元组
                    result = arr.tolist()
                    if original_type == "tuple":
                        result = tuple(result)
                    return result
                except Exception as e:
                    print(f"LargeList numpy deserialization failed: {e}")
                    return obj
            elif format_type == "pickle_binary":
                try:
                    binary_data = base64.b64decode(obj["data"])
                    buffer = io.BytesIO(binary_data)
                    result = pickle.load(buffer)
                    # 确保返回原始类型
                    if original_type == "tuple" and not isinstance(result, tuple):
                        result = tuple(result)
                    elif original_type == "list" and not isinstance(result, list):
                        result = list(result)
                    return result
                except Exception as e:
                    print(f"LargeList pickle deserialization failed: {e}")
                    return obj
            else:
                print(f"Unknown LargeList format: {format_type}")
                return obj
        elif obj.get("__type__") == "ndarray":
            format_type = obj.get("format", "list")  # 默认为旧格式
            if format_type == "npy_base64":
                try:
                    # 解码 base64 数据
                    binary_data = base64.b64decode(obj["data"])
                    buffer = io.BytesIO(binary_data)
                    # 从二进制数据加载 ndarray
                    arr = np.load(buffer, allow_pickle=False)
                    return arr
                except Exception as e:
                    print(f"ndarray binary deserialization failed: {e}")
                    return obj
            elif format_type == "list":
                # 兼容旧的 list 格式
                try:
                    return np.array(obj["data"], dtype=obj["dtype"])
                except Exception as e:
                    print(f"ndarray list deserialization failed: {e}")
                    return obj
            else:
                print(f"Unknown ndarray format: {format_type}")
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


def draw_square_port(painter, rect, info):
    """
    Custom paint function for drawing a Square shaped port.

    Args:
        painter (QtGui.QPainter): painter object.
        rect (QtCore.QRectF): port rect used to describe parameters needed to draw.
        info (dict): information describing the ports current state.
            {
                'port_type': 'in',
                'color': (0, 0, 0),
                'border_color': (255, 255, 255),
                'multi_connection': False,
                'connected': False,
                'hovered': False,
            }
    """
    painter.save()

    # mouse over port color.
    if info['hovered']:
        color = QtGui.QColor(14, 45, 59)
        border_color = QtGui.QColor(136, 255, 35, 255)
    # port connected color.
    elif info['connected']:
        color = QtGui.QColor(195, 60, 60)
        border_color = QtGui.QColor(200, 130, 70)
    # default port color
    else:
        color = QtGui.QColor(*info['color'])
        border_color = QtGui.QColor(*info['border_color'])

    pen = QtGui.QPen(border_color, 1.8)
    pen.setJoinStyle(QtCore.Qt.MiterJoin)

    painter.setPen(pen)
    painter.setBrush(color)
    painter.drawRect(rect)

    painter.restore()


def draw_special_outputport(painter, rect, info):
    """
    Custom paint function for drawing a circular (ellipse) shaped port in purple.

    Args:
        painter (QtGui.QPainter): painter object.
        rect (QtCore.QRectF): port rect used to describe parameters needed to draw.
        info (dict): information describing the ports current state.
            {
                'port_type': 'in',
                'color': (0, 0, 0),
                'border_color': (255, 255, 255),
                'multi_connection': False,
                'connected': False,
                'hovered': False,
            }
    """
    painter.save()

    # Define a base purple color (you can adjust as needed)
    DEFAULT_PURPLE = (128, 0, 128)  # RGB for purple

    # mouse over port color.
    if info['hovered']:
        color = QtGui.QColor(14, 45, 59)
        border_color = QtGui.QColor(136, 255, 35, 255)
    else:
        color = QtGui.QColor(*DEFAULT_PURPLE)
        border_color = QtGui.QColor(*info['border_color'])

    pen = QtGui.QPen(border_color, 1.8)
    pen.setJoinStyle(QtCore.Qt.MiterJoin)

    painter.setPen(pen)
    painter.setBrush(color)
    painter.drawEllipse(rect)  # Draw circle/ellipse instead of rectangle

    painter.restore()


def _evaluate_value_recursively(value, expr_engine):
    """
    递归处理任意结构的值，对字符串执行表达式求值。
    如果求值失败，保持原始字符串不变。
    """
    if isinstance(value, str):
        if expr_engine.is_template_expression(value):
            try:
                result = expr_engine.evaluate_template(value)
                # 如果结果是错误信息（如 [ExprError: ...]），保留原字符串
                if isinstance(result, str) and result.startswith("[Expr"):
                    return value  # 👈 关键：失败时返回原字符串
                return result
            except Exception:
                return value  # 👈 任何异常都返回原字符串
        return value
    elif isinstance(value, list):
        return [_evaluate_value_recursively(item, expr_engine) for item in value]
    elif isinstance(value, dict):
        return {k: _evaluate_value_recursively(v, expr_engine) for k, v in value.items()}
    else:
        return value