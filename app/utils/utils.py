# -*- coding: utf-8 -*-
import psutil
import base64
import json
import os
import pickle
import re
import sys
import time
from collections import defaultdict, deque
from typing import List, Optional, Union

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.feather as feather
import io

from pathlib import Path
from PyQt5 import QtGui, QtCore
from PyQt5.QtGui import QIcon
from loguru import logger

from app.utils.icon_name_map import ICON_NAME_TO_FILE

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
_ICON_CACHE = {}   # 缓存图标名 → QIcon 实例


def kill_proc_tree(pid):
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for child in children:
            child.kill()
        parent.kill()
        psutil.wait_procs(children + [parent], timeout=5)
    except psutil.NoSuchProcess:
        pass


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


def get_icon(icon_name: str) -> QIcon:
    """
    从 Qt 资源系统加载图标（高性能、无磁盘 I/O）

    Args:
        icon_name: 图标名（不含扩展名），如 "copy"

    Returns:
        QIcon 实例
    """
    if icon_name in _ICON_CACHE:
        return _ICON_CACHE[icon_name]

    # 1. 从映射表中找真实文件名
    filename = ICON_NAME_TO_FILE.get(icon_name)
    if filename:
        resource_path = f":/icons/{filename}"
        icon = QIcon(resource_path)
        # 可选：再做一次 null 检查（虽然理论上不会错）
        if not icon.isNull():
            _ICON_CACHE[icon_name] = icon
            return icon

    # 2. fallback 到 FluentIcon
    try:
        from qfluentwidgets import FluentIcon
        icon = FluentIcon.APPLICATION.icon()
        _ICON_CACHE[icon_name] = icon
        return icon
    except Exception:
        pass

    # 3. 最终 fallback
    return QIcon()


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
        try:
            return obj.serialize()
        except:
            return str(obj)
    else:
        # 其他类型：尝试转为字符串
        try:
            json.dumps(obj)  # 测试是否可序列化
            return obj
        except (TypeError, ValueError):
            return None


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


def _safe_equal(a, b):
    """Safely compare two values that may include numpy arrays."""
    if a is b:
        return True
    if type(a) != type(b):
        return False
    try:
        if a == b:
            return True
    except (ValueError, TypeError):
        pass

    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        return np.array_equal(a, b)

    return False


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


def _safe_load_pickle(path, timeout=5.0, retry_interval=0.05):
    """
    安全加载 pickle 文件：等待文件存在、非空、且可完整加载
    """
    start = time.time()
    while time.time() - start < timeout:
        if not path.exists():
            time.sleep(retry_interval)
            continue

        if path.stat().st_size == 0:
            time.sleep(retry_interval)
            continue

        try:
            with open(path, 'rb') as f:
                return pickle.load(f)
        except (EOFError, pickle.UnpicklingError):
            # 文件未写完或损坏，继续等待
            time.sleep(retry_interval)
            continue

    raise RuntimeError(f"无法加载结果文件: {path}")


def topological_sort(nodes: List, split_components: bool = False) -> Union[Optional[List], Optional[List[List]]]:
    """
    拓扑排序

    Args:
        nodes: 节点列表
        split_components: 是否将非连通图拆分为多个连通分量，每个分量内部进行拓扑排序

    Returns:
        如果 split_components 为 False: 返回整个图的拓扑排序列表，如果存在环则返回 None
        如果 split_components 为 True: 返回每个连通分量的拓扑排序列表组成的列表，如果存在环则返回 None
    """
    if not nodes:
        return [] if split_components else []

    # 为了确保顺序固定，先对节点进行排序
    sorted_nodes = sorted(nodes, key=lambda x: str(x.id) if hasattr(x, 'id') else str(x))

    in_degree = {node: 0 for node in sorted_nodes}
    graph_deps = defaultdict(list)
    graph_reverse_deps = defaultdict(list)  # 反向图，用于查找连通分量

    node_set = set(sorted_nodes)
    for node in sorted_nodes:
        if not hasattr(node, 'input_ports'):
            continue
        for input_port in node.input_ports():
            for upstream_out in input_port.connected_ports():
                upstream = get_port_node(upstream_out)
                if upstream in node_set:
                    graph_deps[upstream].append(node)
                    graph_reverse_deps[node].append(upstream)  # 添加反向边
                    in_degree[node] += 1

    def find_connected_components():
        """查找所有连通分量（无向图的连通分量）"""
        visited = set()
        components = []

        # 按照排序后的节点顺序遍历，确保连通分量发现的顺序固定
        for start_node in sorted_nodes:
            if start_node not in visited:
                # BFS 查找连通分量
                component = []
                queue = deque([start_node])
                visited.add(start_node)

                while queue:
                    current = queue.popleft()
                    component.append(current)

                    # 检查所有相邻节点（包括前驱和后继），按固定顺序处理
                    neighbors = []
                    neighbors.extend(graph_deps[current])
                    neighbors.extend(graph_reverse_deps[current])

                    # 对邻居节点排序以确保处理顺序固定
                    neighbors = sorted(neighbors, key=lambda x: str(x.id) if hasattr(x, 'id') else str(x))

                    for neighbor in neighbors:
                        if neighbor not in visited and neighbor in node_set:
                            visited.add(neighbor)
                            queue.append(neighbor)

                # 对连通分量内的节点排序以确保顺序固定
                component.sort(key=lambda x: str(x.id) if hasattr(x, 'id') else str(x))
                components.append(component)

        return components

    def topological_sort_single_component(component_nodes):
        """对单个连通分量进行拓扑排序"""
        component_in_degree = {node: 0 for node in component_nodes}

        # 重新计算连通分量内的入度
        for node in component_nodes:
            if not hasattr(node, 'input_ports'):
                continue
            for input_port in node.input_ports():
                for upstream_out in input_port.connected_ports():
                    upstream = get_port_node(upstream_out)
                    if upstream in component_nodes:
                        component_in_degree[node] += 1

        # 从队列中获取零入度节点时也要排序以确保顺序固定
        zero_in_degree_nodes = [n for n in component_nodes if component_in_degree[n] == 0]
        queue = deque(sorted(zero_in_degree_nodes, key=lambda x: str(x.id) if hasattr(x, 'id') else str(x)))

        execution_order = []

        while queue:
            # 从队列中取出节点时，确保每次处理的顺序一致
            n = queue.popleft()
            execution_order.append(n)

            # 获取邻居节点并排序以确保处理顺序固定
            neighbors = []
            for neighbor in graph_deps[n]:
                if neighbor in component_nodes:
                    neighbors.append(neighbor)

            # 排序邻居节点
            neighbors = sorted(neighbors, key=lambda x: str(x.id) if hasattr(x, 'id') else str(x))

            for neighbor in neighbors:
                component_in_degree[neighbor] -= 1
                if component_in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(execution_order) != len(component_nodes):
            return None  # 存在环

        return execution_order

    if split_components:
        # 按连通分量分别处理
        components = find_connected_components()
        result = []

        for component in components:
            component_order = topological_sort_single_component(component)
            if component_order is None:  # 某个连通分量内存在环
                return None
            result.append(component_order)

        return result
    else:
        # 传统拓扑排序，处理整个图
        # 对初始零入度节点排序以确保顺序固定
        zero_in_degree_nodes = [n for n in sorted_nodes if in_degree[n] == 0]
        queue = deque(sorted(zero_in_degree_nodes, key=lambda x: str(x.id) if hasattr(x, 'id') else str(x)))

        execution_order = []

        while queue:
            n = queue.popleft()
            execution_order.append(n)

            # 获取邻居节点并排序以确保顺序固定
            neighbors = []
            for neighbor in graph_deps[n]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    neighbors.append(neighbor)

            # 排序新变为零入度的节点
            neighbors = sorted(neighbors, key=lambda x: str(x.id) if hasattr(x, 'id') else str(x))

            for neighbor in neighbors:
                queue.append(neighbor)

        if len(execution_order) != len(sorted_nodes):
            return None  # 存在环

        return execution_order