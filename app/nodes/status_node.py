# -*- coding: utf-8 -*-
from dataclasses import dataclass

from loguru import logger

from app.nodes.base_node import BasicNodeWithGlobalProperty


@dataclass
class NodeStatus:
    """节点状态枚举类"""
    NODE_STATUS_UNRUN = "unrun"  # 未运行
    NODE_STATUS_PENDING = "pending"  # 等待运行
    NODE_STATUS_RUNNING = "running"  # 运行中
    NODE_STATUS_SUCCESS = "success"  # 运行成功
    NODE_STATUS_LAST_SUCCESS = "last_success"  # 上次运行成功（枯萎色）用来在运行时区分哪些是之前运行成功的，哪些是当前运行成功的
    NODE_STATUS_FAILED = "failed"  # 运行失败
    NODE_STATUS_DISABLED = "disabled"  # 节点被禁用


@dataclass
class NodeStatusColors:
    # 状态色 (R, G, B)
    # 莫兰迪色系：降低了鲜艳度，增加了灰色调，视觉更舒适
    SUCCESS = (39, 174, 96)     # 翡翠绿 (深绿但透亮)
    # 枯叶色：一种低饱和度的枯黄/褐色，代表“过往的成功”
    LAST_SUCCESS = (139, 115, 85)  # 枯叶色 (Withered Leaf)
    RUNNING = (41, 128, 185)    # 伯利兹蓝 (稳重的专业蓝)
    FAILED = (192, 57, 43)      # 茜草红 (深沉的警示红)
    PENDING = (127, 140, 141)   # 凉石灰 (冷色调灰)
    DISABLED = (44, 62, 80)     # 湿沥青 (近乎黑的深蓝灰)
    DEFAULT = (32, 32, 35)      # 默认背景色

# ----------------------------
# 自定义节点类（支持状态显示）- 淡色版本
# ----------------------------
class NoStatusNode(BasicNodeWithGlobalProperty):
    """支持状态显示的基节点类 - 使用淡色背景确保白色文字清晰"""
    def __init__(self, qgraphics_item=None):
        super().__init__(qgraphics_item)
        self._status = NodeStatus.NODE_STATUS_UNRUN
        self._original_color = self.color()  # 保存原始颜色
        self._update_status_color()

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        self._status = value
        self._update_status_color()

    def _update_status_color(self):
        """根据状态更新节点颜色（使用淡色）"""
        self.view.draw_node()


class StatusNode(BasicNodeWithGlobalProperty):
    """支持状态显示的基节点类 - 使用淡色背景确保白色文字清晰"""
    def __init__(self, qgraphics_item=None):
        super().__init__(qgraphics_item)
        self._status = self.get_property("_status") or NodeStatus.NODE_STATUS_UNRUN
        self._original_color = self.color()  # 保存原始颜色
        self._update_status_color()

    @property
    def status(self):
        return self.get_property("_status") or NodeStatus.NODE_STATUS_UNRUN

    @status.setter
    def status(self, value):
        self._status = value
        self.set_property("_status", value)
        self._update_status_color()

    def _update_status_color(self):
        """
        根据状态更新节点外观。
        不仅仅是修改 color，还会触发重绘，使 Header 的辉光发生变化。
        """
        # 映射表提升性能
        status_map = {
            NodeStatus.NODE_STATUS_UNRUN: self._original_color,
            NodeStatus.NODE_STATUS_DISABLED: NodeStatusColors.DISABLED,
            NodeStatus.NODE_STATUS_RUNNING: NodeStatusColors.RUNNING,
            NodeStatus.NODE_STATUS_SUCCESS: NodeStatusColors.SUCCESS,
            NodeStatus.NODE_STATUS_LAST_SUCCESS: NodeStatusColors.LAST_SUCCESS,  # 应用枯叶色
            NodeStatus.NODE_STATUS_FAILED: NodeStatusColors.FAILED,
            NodeStatus.NODE_STATUS_PENDING: NodeStatusColors.PENDING
        }

        target_color = status_map.get(self._status, self._original_color)

        # 将颜色应用到 properties 中 (NodeGraphQt 的 color 属性)
        # 这样 paint 函数可以实时获取到
        self.set_color(*target_color)

        # 强制更新边框颜色作为辅助醒目提醒 (可选)
        if self._status == NodeStatus.NODE_STATUS_FAILED:
            self.border_color = (255, 0, 0, 255)  # 只有失败时才给醒目的红框
        elif self._status == NodeStatus.NODE_STATUS_LAST_SUCCESS:
            # 枯叶状态可以给一个稍微暗淡的边框
            self.border_color = (100, 90, 70, 255)
        else:
            self.border_color = (46, 57, 66, 255)  # 恢复默认边框