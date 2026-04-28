# -*- coding: utf-8 -*-
import base64
import heapq  # 使用堆来实现优先级队列
import io
import json
import os
import pickle
import re
import socket
import stat
import sys
import tarfile
import threading
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import List, Optional, Union

import psutil
from PyQt5.QtGui import QIcon, QFont
from loguru import logger

from app.utils.config import Settings

try:
    from pypinyin import pinyin, Style
except ImportError:
    pinyin = None

from app.utils.icon_name_map import ICON_NAME_TO_FILE

# ANSI 颜色代码映射
ANSI_COLOR_MAP = {
    "30": "#000000",  # 黑色
    "31": "#ff0000",  # 红色
    "32": "#00ff00",  # 绿色
    "33": "#ffff00",  # 黄色
    "34": "#0000ff",  # 蓝色
    "35": "#ff00ff",  # 紫色
    "36": "#00ffff",  # 青色
    "37": "#ffffff",  # 白色
    "90": "#808080",  # 亮黑
    "91": "#ff5555",  # 亮红
    "92": "#50fa7b",  # 亮绿
    "93": "#f1fa8c",  # 亮黄
    "94": "#8be9fd",  # 亮蓝
    "95": "#ff79c6",  # 亮紫
    "96": "#8be9fd",  # 亮青
    "97": "#ffffff",  # 亮白
}
_ICON_CACHE = {}  # 缓存图标名 → QIcon 实例


# 定义一个占位类，用于替代本地缺失的模块类
class MissingModulePlaceholder:
    def __init__(self, *args, **kwargs):
        pass

    def __setstate__(self, state):
        self.__dict__.update(state)


class SafeUnpickler(pickle.Unpickler):
    """自定义 Unpickler，当模块不存在时返回占位符而不是崩溃"""

    def find_class(self, module, name):
        try:
            return super().find_class(module, name)
        except ImportError:
            # 如果本地找不到 numpy 等模块，就返回一个占位类
            return MissingModulePlaceholder


def get_pinyin_search_keys(text):
    """生成拼音全拼和首字母缩写"""
    if not pinyin or not text:
        return ""
    # 提取首字母 (Style.FIRST_LETTER)
    first_letters = "".join([i[0][0] for i in pinyin(text, style=Style.FIRST_LETTER)])
    # 提取全拼 (Style.NORMAL)
    full_pinyin = "".join([i[0] for i in pinyin(text, style=Style.NORMAL)])
    return f"{first_letters} {full_pinyin} {text}".lower()


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
    text = re.sub(r"\x1b\[[0-9;]*[ABCDHfJKmnsu]", "", text)

    # 处理颜色代码
    def replace_ansi(match):
        codes = match.group(1).split(";")
        color = None
        bold = False

        for code in codes:
            if code in ANSI_COLOR_MAP:
                color = ANSI_COLOR_MAP[code]
            elif code == "1":
                bold = True

        if color:
            style = f"color: {color};"
            if bold:
                style += " font-weight: bold;"
            return f'<span style="{style}">'
        elif bold:
            return '<span style="font-weight: bold;">'
        else:
            return "<span>"

    # 替换 ANSI 开始序列 \x1b[...m
    text = re.sub(r"\x1b\[([0-9;]*)m", replace_ansi, text)

    # 替换 ANSI 结束序列 \x1b[0m 为 </span>
    text = re.sub(r"\x1b\[0m", "</span>", text)

    # 处理剩余的 ANSI 序列（清理）
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)

    # 转换换行符
    text = text.replace("\n", "<br>")

    return text


def ansi_to_rich_text(text):
    """
    将 ANSI 转换为 Qt Rich Text（备用方案）
    """
    return f"<pre style='font-family: Consolas, monospace;'>{ansi_to_html(text)}</pre>"


def resource_path(relative_path) -> str:
    """获取打包后资源文件的绝对路径"""
    if hasattr(sys, "_MEIPASS"):
        # 如果是打包后的环境
        base_path = sys._MEIPASS
    else:
        # 开发环境，直接使用当前路径
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def normalize_python_executable(exe_path: Optional[str]) -> Optional[str]:
    """
    规范化 Python 可执行路径，兼容 Windows 路径在 macOS/Linux 上的映射。
    """
    if not exe_path:
        return exe_path

    exe_path = os.path.expanduser(exe_path)
    if os.path.isabs(exe_path) and os.path.exists(exe_path):
        return os.path.normpath(exe_path)

    # 处理 Windows 风格路径
    cleaned = exe_path.replace("\\", "/")
    match = re.search(
        r"/envs/miniconda/envs/([^/]+)/python\.exe$", cleaned, re.IGNORECASE
    )
    if match:
        env_name = match.group(1)
        if getattr(sys, "frozen", False):
            base_root = Path(resource_path("."))
        else:
            base_root = Path(__file__).resolve().parents[2]
        env_root = base_root / "envs" / "miniconda" / "envs" / env_name
        candidate = env_root / ("python.exe" if os.name == "nt" else "bin/python")
        if candidate.exists():
            return str(candidate)

    # 如果是 Windows 的 python.exe，尝试转换为 *nix 的 bin/python
    if cleaned.endswith("/python.exe") and os.name != "nt":
        base = Path(cleaned[: -len("/python.exe")])
        candidate = base / "bin" / "python"
        if candidate.exists():
            return str(candidate)

    return os.path.normpath(exe_path)


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


def get_canvas_font(size=10, bold=False):
    try:
        font_family = Settings.get_instance().canvas_font_selected.value
    except Exception:
        font_family = "Segoe UI"

    font = QFont(font_family, size)
    if bold:
        font.setBold(True)
    return font


def get_unified_font(size=10, bold=False):
    """Get font with unified font family configured by user"""
    try:
        font_family = Settings.get_instance().canvas_font_selected.value
    except Exception:
        font_family = "Segoe UI"
    font = QFont(font_family, size)
    if bold:
        font.setBold(True)
    return font


def str_to_bool(value):
    """可靠的布尔值转换"""
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("true", "1", "yes", "on")


def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def serialize_for_json(obj, large_list_threshold=1000):
    """递归将对象转换为 JSON 可序列化格式"""
    if isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    elif hasattr(obj, "serialize") and callable(getattr(obj, "serialize")):
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
        return {k: deserialize_from_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [deserialize_from_json(v) for v in obj]
    else:
        return obj



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
        return {
            k: _evaluate_value_recursively(v, expr_engine) for k, v in value.items()
        }
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
            with open(path, "rb") as f:
                return pickle.load(f)
        except (EOFError, pickle.UnpicklingError):
            # 文件未写完或损坏，继续等待
            time.sleep(retry_interval)
            continue

    raise RuntimeError(f"无法加载结果文件: {path}")


def locate_node_by_name(graph, node_name):
    """根据全局变量名定位到对应的节点"""
    found_node = graph.get_node_by_name(node_name)
    # 如果 base 本身就在组里，直接返回
    if found_node:
        return found_node.name()
    parts = node_name.split("_")
    n = len(parts)

    # 从最细粒度（全拆成空格）到最粗（保留所有下划线）尝试
    for i in range(
        n - 1, 0, -1
    ):  # i 是保留原始下划线的起始索引（右侧 i 个部分保持原样）
        candidate = (
            " ".join(parts[: n - i]) + "_" + "_".join(parts[n - i :])
            if n - i > 0
            else "_".join(parts)
        )
        found_node = graph.get_node_by_name(candidate)
        if found_node:
            return found_node.name()

    # 如果上面都失败，尝试直接用空格替换所有下划线
    fallback = " ".join(parts)
    found_node = graph.get_node_by_name(fallback)
    if found_node:
        return found_node.name()


# 全局缓存
_TOPO_CACHE = {}
_TOPO_CACHE_LOCK = threading.RLock()


def get_node_visual_rank(node):
    """
    获取节点的视觉排序权重：从左到右，从上到下
    NodeGraphQt 的 node.pos() 返回 [x, y]
    """
    if hasattr(node, "pos"):
        pos = node.pos()
        return (pos[0], pos[1])  # 先比较 X (左->右)，再比较 Y (上->下)
    return (0, 0)


def get_graph_fingerprint(nodes: List, use_logic: bool) -> int:
    """
    计算图指纹。
    注意：现在包含了坐标，因为坐标改变会影响视觉排序结果。
    """
    state = []
    # 按照 ID 排序后再计算 hash，确保指纹唯一性
    for node in sorted(nodes, key=lambda x: x.id):
        node_state = [
            node.id,
            node.name(),
            tuple(node.pos()) if hasattr(node, "pos") else (0, 0),
        ]

        # 物理连接
        node_ids = {n.id for n in nodes}
        connections = []
        if hasattr(node, "input_ports"):
            for p in node.input_ports():
                for cp in p.connected_ports():
                    upstream = cp.node()
                    if upstream.id in node_ids:
                        connections.append(f"{upstream.id}->{p.name()}")
        node_state.append(tuple(sorted(connections)))

        # 逻辑依赖
        if use_logic and hasattr(node, "get_logical_inputs"):
            node_state.append(tuple(node.get_logical_inputs()))

        state.append(tuple(node_state))

    return hash(tuple(state))