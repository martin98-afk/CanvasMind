# -*- coding: utf-8 -*-
import os
import sys

from PyQt5.QtGui import QIcon


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
