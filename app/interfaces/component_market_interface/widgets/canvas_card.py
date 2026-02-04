# -*- coding: utf-8 -*-
import os

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QHBoxLayout, QVBoxLayout, QLabel)
from qfluentwidgets import (CardWidget, PrimaryPushButton, FluentIcon, ToolButton,
                            CheckBox, BodyLabel, ImageLabel)


class CanvasCard(CardWidget):
    """ 新增：画布专用卡片 (显示图片) """
    action_signal = pyqtSignal(dict, str)
    delete_signal = pyqtSignal(dict)
    check_changed = pyqtSignal()

    def __init__(self, data: dict, mode: str, is_linked: bool, is_admin: bool, status_code: str, parent=None):
        super().__init__(parent)
        self.data = data
        self.mode = mode
        self.status_code = status_code
        self.setFixedSize(280, 240)  # 画布卡片稍大

        v_lay = QVBoxLayout(self)
        v_lay.setContentsMargins(10, 10, 10, 10)

        # 顶部
        top = QHBoxLayout()
        self.check_box = CheckBox()
        self.check_box.stateChanged.connect(self.check_changed.emit)

        # 状态标
        status_text = {
            "match": "已同步" if mode == "local" else "已下载",
            "diff": "有差异",
            "new": "云端新增",
            "unsynced": "未备份"
        }
        status_color = {
            "match": "#52c41a", "diff": "#faad14", "new": "#1890ff", "unsynced": "#8c8c8c"
        }
        self.badge = QLabel(status_text.get(status_code, ""))
        self.badge.setStyleSheet(
            f"background:{status_color.get(status_code)}; color:white; padding:2px 5px; border-radius:4px; font-size:10px;")

        top.addWidget(self.check_box)
        top.addStretch()
        top.addWidget(self.badge)
        v_lay.addLayout(top)

        # 图片预览
        self.img = ImageLabel()
        self.img.setFixedSize(258, 120)
        self.img.setBorderRadius(5)
        self.img.setScaledContents(True)
        img_path = data.get("image_path")
        if img_path and os.path.exists(img_path):
            self.img.setImage(img_path)
        else:
            self.img.setStyleSheet("background: #f0f0f0; color: #999;")
            self.img.setText("无预览图")
            self.img.setAlignment(Qt.AlignCenter)
        v_lay.addWidget(self.img)

        # 信息
        title = BodyLabel(data.get("画布名称", "未知"))
        title.setStyleSheet("font-weight:bold; font-size:14px;")
        v_lay.addWidget(title)

        sub = BodyLabel(f"Ver: {data.get('版本号', '1.0.0')}")
        sub.setStyleSheet("color:#888; font-size:11px;")
        v_lay.addWidget(sub)

        # 按钮
        btns = QHBoxLayout()
        self.act_btn = PrimaryPushButton()
        self.act_btn.setFixedHeight(28)
        self.act_btn.clicked.connect(lambda: self.action_signal.emit(data, mode))

        # 根据状态设置按钮文字
        if mode == "market":  # 云端库
            self.act_btn.setText("更新" if status_code == "diff" else "下载")
            self.act_btn.setIcon(FluentIcon.UPDATE if status_code == "diff" else FluentIcon.DOWNLOAD)
        else:  # 本地站
            self.act_btn.setText("推送" if is_linked else "上传")
            self.act_btn.setIcon(FluentIcon.UP if is_linked else FluentIcon.CLOUD)

        self.del_btn = ToolButton(FluentIcon.DELETE)
        self.del_btn.clicked.connect(lambda: self.delete_signal.emit(data))
        # 仅管理员在云端，或本地模式下允许删除
        self.del_btn.setVisible(is_admin if mode == "market" else False)

        btns.addStretch()
        btns.addWidget(self.act_btn)
        btns.addWidget(self.del_btn)
        v_lay.addLayout(btns)
