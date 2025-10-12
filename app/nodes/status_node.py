# -*- coding: utf-8 -*-
from dataclasses import dataclass

from NodeGraphQt import BaseNode
from Qt import Qt


@dataclass
class NodeStatus:
    """节点状态枚举类"""
    NODE_STATUS_UNRUN = "unrun"  # 未运行
    NODE_STATUS_PENDING = "pending"  # 等待运行
    NODE_STATUS_RUNNING = "running"  # 运行中
    NODE_STATUS_SUCCESS = "success"  # 运行成功
    NODE_STATUS_FAILED = "failed"  # 运行失败


# ----------------------------
# 自定义节点类（支持状态显示）- 淡色版本
# ----------------------------
class StatusNode(BaseNode):
    """支持状态显示的基节点类 - 使用淡色背景确保白色文字清晰"""
    def __init__(self):
        super().__init__()
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
        if self._status == NodeStatus.NODE_STATUS_UNRUN:
            # 恢复原始颜色
            self.set_color(*self._original_color)
        elif self._status == NodeStatus.NODE_STATUS_RUNNING:
            # 淡蓝色 - 运行中
            self.set_color(30, 60, 90)  # 深蓝底色，确保白字清晰
        elif self._status == NodeStatus.NODE_STATUS_SUCCESS:
            # 淡绿色 - 成功
            self.set_color(25, 70, 45)  # 深绿底色，确保白字清晰
        elif self._status == NodeStatus.NODE_STATUS_FAILED:
            # 淡红色 - 失败
            self.set_color(80, 30, 30)  # 深红底色，确保白字清晰
        elif self._status == NodeStatus.NODE_STATUS_PENDING:
            # 淡灰色 - 等待运行
            self.set_color(60, 60, 60)