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

import numpy as np
import pandas as pd
import paramiko
import psutil
import pyarrow as pa
import pyarrow.feather as feather
from PyQt5.QtGui import QIcon
from loguru import logger

try:
    from pypinyin import pinyin, Style
except ImportError:
    pinyin = None

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


def ssh_send_file(env_data, local_path, remote_path):
    """
    通用 SSH 文件发送函数
    :param env_data: 环境配置字典 (包含 host, port, user, pwd)
    :param local_path: 本地文件路径
    :param remote_path: 远程目标绝对路径
    :return: bool 是否发送成功
    """
    if not isinstance(env_data, dict) or env_data.get('type') != 'ssh':
        logger.error("无效的 SSH 环境配置")
        return False

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        # 1. 建立连接
        ssh.connect(
            hostname=env_data['host'],
            port=int(env_data.get('port', 22)),
            username=env_data['user'],
            password=env_data['pwd'],
            timeout=15
        )

        # 2. 处理路径与创建远程目录
        # 强制将路径转换为 Linux 风格
        remote_path = remote_path.replace('\\', '/')
        remote_dir = os.path.dirname(remote_path)

        # 使用 mkdir -p 一次性创建多级目录
        ssh.exec_command(f"mkdir -p {remote_dir}")

        # 3. SFTP 上传
        sftp = ssh.open_sftp()
        sftp.put(str(local_path), remote_path)

        sftp.close()
        logger.info(f"文件已成功发送至远程: {remote_path}")
        return True

    except Exception as e:
        logger.error(f"SSH 文件发送失败: {e}")
        return False
    finally:
        ssh.close()


def sftp_upload_dir(sftp, local_dir, remote_dir):
    for root, dirs, files in os.walk(local_dir):
        # 计算相对路径并创建远程目录
        rel_path = os.path.relpath(root, local_dir)
        target_dir = os.path.join(remote_dir, rel_path).replace("\\", "/")

        try:
            sftp.mkdir(target_dir)
        except IOError:  # 目录已存在
            pass

        for f in files:
            local_file = os.path.join(root, f)
            remote_file = os.path.join(target_dir, f).replace("\\", "/")
            sftp.put(local_file, remote_file)


def sftp_download_dir(sftp, remote_dir, local_dir, ssh=None):
    """
    通过 sftp 下载远程目录。
    如果文件数量超过 3 个，自动切换为打包传输模式以提高速度。
    """
    # 确保本地目录存在
    if not os.path.exists(local_dir):
        os.makedirs(local_dir)

    try:
        # 获取远程目录列表
        items = sftp.listdir_attr(remote_dir)

        # 如果提供了 ssh 对象，且目录项超过 3 个，则打包下载
        if ssh and len(items) > 3:
            # 1. 生成唯一的临时压缩包名
            temp_filename = f"transfer_{uuid.uuid4().hex}.tar.gz"
            remote_parent = os.path.dirname(remote_dir)
            dir_name = os.path.basename(remote_dir)
            remote_tar_path = f"/tmp/{temp_filename}"
            local_tar_path = os.path.join(local_dir, temp_filename)

            # 2. 远程打包 (-C 切换路径可以避免压缩包里包含多层父目录)
            # tar -czf 压缩包路径 -C 父目录 文件夹名
            cmd = f"tar -czf {remote_tar_path} -C {remote_parent} {dir_name}"
            stdin, stdout, stderr = ssh.exec_command(cmd)

            # 等待命令执行完成
            if stdout.channel.recv_exit_status() == 0:
                try:
                    # 3. 下载单文件压缩包
                    sftp.get(remote_tar_path, local_tar_path)

                    # 4. 本地解压
                    with tarfile.open(local_tar_path, "r:gz") as tar:
                        # 解压到 local_dir 的父目录，因为压缩包内已经含有了文件夹名
                        tar.extractall(path=os.path.dirname(local_dir))

                    # 5. 清理：删除本地和远程的压缩包
                    os.remove(local_tar_path)
                    ssh.exec_command(f"rm {remote_tar_path}")
                    return  # 打包任务完成，直接返回
                except Exception as e:
                    print(f"打包下载失败，回退到普通模式: {e}")
            else:
                print("远程打包失败，回退到普通模式")

        # --- 普通模式：递归下载 ---
        for item in items:
            remote_path = os.path.join(remote_dir, item.filename).replace('\\', '/')
            local_path = os.path.join(local_dir, item.filename)

            if stat.S_ISDIR(item.st_mode):
                # 如果是文件夹，递归调用
                sftp_download_dir(sftp, remote_path, local_path, ssh=ssh)
            else:
                try:
                    sftp.get(remote_path, local_path)
                except:
                    pass
    except Exception as e:
        print(f"SFTP 操作异常: {e}")


def replace_remote_paths(pkl_path, remote_root, local_root):
    """
    核心逻辑：使用 SafeUnpickler 加载，防止缺失 Numpy 导致崩溃
    """
    if not os.path.exists(pkl_path):
        return

    try:
        # 1. 以二进制读取文件
        with open(pkl_path, 'rb') as f:
            # 使用自定义的 SafeUnpickler
            unpickler = SafeUnpickler(f)
            data = unpickler.load()

        # 2. 统一路径格式
        rem_p = remote_root.replace('\\', '/')
        loc_p = local_root.replace('\\', '/').rstrip('/')

        def walk_and_replace(obj):
            if isinstance(obj, str):
                if rem_p in obj:
                    return obj.replace(rem_p, loc_p)
                return obj
            elif isinstance(obj, list):
                return [walk_and_replace(item) for item in obj]
            elif isinstance(obj, dict):
                return {k: walk_and_replace(v) for k, v in obj.items()}
            # 如果是占位类对象，尝试遍历它的内部属性（如果有路径存进属性里了）
            elif isinstance(obj, MissingModulePlaceholder):
                for k, v in obj.__dict__.items():
                    obj.__dict__[k] = walk_and_replace(v)
                return obj
            return obj

        new_data = walk_and_replace(data)

        # 3. 写回文件
        with open(pkl_path, 'wb') as f:
            pickle.dump(new_data, f)

    except Exception as e:
        logger.error(f"路径替换失败: {e}")


def get_pinyin_search_keys(text):
    """生成拼音全拼和首字母缩写"""
    if not pinyin or not text:
        return ""
    # 提取首字母 (Style.FIRST_LETTER)
    first_letters = "".join([i[0][0] for i in pinyin(text, style=Style.FIRST_LETTER)])
    # 提取全拼 (Style.NORMAL)
    full_pinyin = "".join([i[0] for i in pinyin(text, style=Style.NORMAL)])
    return f"{first_letters} {full_pinyin}".lower()


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


def str_to_bool(value):
    """可靠的布尔值转换"""
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("true", "1", "yes", "on")


def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


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


def locate_node_by_name(graph, node_name):
    """根据全局变量名定位到对应的节点"""
    found_node = graph.get_node_by_name(node_name)
    # 如果 base 本身就在组里，直接返回
    if found_node:
        return found_node.name()
    parts = node_name.split('_')
    n = len(parts)

    # 从最细粒度（全拆成空格）到最粗（保留所有下划线）尝试
    for i in range(n - 1, 0, -1):  # i 是保留原始下划线的起始索引（右侧 i 个部分保持原样）
        candidate = ' '.join(parts[:n - i]) + '_' + '_'.join(parts[n - i:]) if n - i > 0 else '_'.join(parts)
        found_node = graph.get_node_by_name(candidate)
        if found_node:
            return found_node.name()

    # 如果上面都失败，尝试直接用空格替换所有下划线
    fallback = ' '.join(parts)
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
    if hasattr(node, 'pos'):
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
            tuple(node.pos()) if hasattr(node, 'pos') else (0, 0)
        ]

        # 物理连接
        node_ids = {n.id for n in nodes}
        connections = []
        if hasattr(node, 'input_ports'):
            for p in node.input_ports():
                for cp in p.connected_ports():
                    upstream = cp.node()
                    if upstream.id in node_ids:
                        connections.append(f"{upstream.id}->{p.name()}")
        node_state.append(tuple(sorted(connections)))

        # 逻辑依赖
        if use_logic and hasattr(node, 'get_logical_inputs'):
            node_state.append(tuple(node.get_logical_inputs()))

        state.append(tuple(node_state))

    return hash(tuple(state))


def topological_sort(
        nodes: List,
        split_components: bool = False,
        use_logic: bool = True,
        use_cache: bool = True
) -> Union[Optional[List], Optional[List[List]]]:
    """
    增强版拓扑排序
    1. 支持物理+逻辑依赖
    2. 支持缓存
    3. 严格按视觉位置排序 (左->右, 上->下)
    """
    if not nodes:
        return [] if split_components else []
    # 过滤注释节点
    nodes = [node for node in nodes if not node.model.type_ == 'general.StickyNote']
    # 1. 缓存检查
    fingerprint = None
    if use_cache:
        fingerprint = get_graph_fingerprint(nodes, use_logic)
        cache_key = (fingerprint, split_components, use_logic)
        with _TOPO_CACHE_LOCK:
            if cache_key in _TOPO_CACHE:
                return _TOPO_CACHE[cache_key]

    # 2. 构建依赖图
    # 初始排序：在构建逻辑时，我们也按视觉顺序处理
    sorted_nodes = sorted(nodes, key=get_node_visual_rank)
    node_set = set(sorted_nodes)
    in_degree = {node: 0 for node in sorted_nodes}
    graph_deps = defaultdict(list)
    graph_reverse_deps = defaultdict(list)

    if use_logic:
        var_to_producer = {}
        for node in sorted_nodes:
            safe_node_name = re.sub(r'\s+', '_', node.name())
            if hasattr(node, 'output_ports'):
                for port in node.output_ports():
                    var_key = f"node_vars.{safe_node_name}__{port.name()}"
                    var_to_producer[var_key] = node

    for node in sorted_nodes:
        # A. 物理依赖
        if hasattr(node, 'input_ports'):
            for input_port in node.input_ports():
                for upstream_out in input_port.connected_ports():
                    upstream = upstream_out.node()
                    if upstream in node_set:
                        if node not in graph_deps[upstream]:
                            graph_deps[upstream].append(node)
                            graph_reverse_deps[node].append(upstream)
                            in_degree[node] += 1

        # B. 逻辑依赖
        if use_logic and hasattr(node, 'get_logical_inputs'):
            for input_name in node.get_logical_inputs():
                upstream = var_to_producer.get(input_name)
                if upstream and upstream in node_set and upstream != node:
                    if node not in graph_deps[upstream]:
                        graph_deps[upstream].append(node)
                        graph_reverse_deps[node].append(upstream)
                        in_degree[node] += 1

    # 3. 连通分量查找 (按视觉顺序发现分量)
    def find_connected_components():
        visited = set()
        components = []
        for start_node in sorted_nodes:  # 这里已经是按视觉排好序的
            if start_node not in visited:
                component = []
                queue = deque([start_node])
                visited.add(start_node)
                while queue:
                    current = queue.popleft()
                    component.append(current)
                    # 合并正向和反向边来找连通块
                    neighbors = list(set(graph_deps[current] + graph_reverse_deps[current]))
                    # 邻居也按视觉排序
                    neighbors.sort(key=get_node_visual_rank)
                    for neighbor in neighbors:
                        if neighbor not in visited and neighbor in node_set:
                            visited.add(neighbor)
                            queue.append(neighbor)
                # 分量内部初次排序
                component.sort(key=get_node_visual_rank)
                components.append(component)
        return components

    # 4. 拓扑排序核心算法 (使用优先级队列保证视觉顺序)
    def topo_process(target_nodes, current_in_degrees):
        target_set = set(target_nodes)
        # 使用 heapq 实现优先级队列
        # 存入格式: (visual_rank_tuple, node_object)
        # heapq 是最小堆，坐标越小优先级越高
        ready_queue = []

        for n in target_nodes:
            if current_in_degrees[n] == 0:
                heapq.heappush(ready_queue, (get_node_visual_rank(n), n))

        order = []
        while ready_queue:
            _, n = heapq.heappop(ready_queue)
            order.append(n)

            # 释放下游，并将新就绪的节点按坐标放入堆
            for neighbor in graph_deps[n]:
                if neighbor in target_set:
                    current_in_degrees[neighbor] -= 1
                    if current_in_degrees[neighbor] == 0:
                        heapq.heappush(ready_queue, (get_node_visual_rank(neighbor), neighbor))

        return order if len(order) == len(target_nodes) else None

    # 5. 执行
    if split_components:
        components = find_connected_components()
        results = []
        for comp in components:
            # 为每个连通分量计算入度
            comp_in_degree = {n: 0 for n in comp}
            c_set = set(comp)
            for u in comp:
                for v in graph_deps[u]:
                    if v in c_set: comp_in_degree[v] += 1

            sorted_comp = topo_process(comp, comp_in_degree)
            if sorted_comp is None: return None  # 有环
            results.append(sorted_comp)
        final_result = results
    else:
        final_result = topo_process(sorted_nodes, in_degree)

    # 6. 写入缓存
    if use_cache and fingerprint is not None:
        with _TOPO_CACHE_LOCK:
            if len(_TOPO_CACHE) > 100: _TOPO_CACHE.clear()
            _TOPO_CACHE[(fingerprint, split_components, use_logic)] = final_result

    return final_result