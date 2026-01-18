# -*- coding: utf-8 -*-
import base64
import os
import pickle
import tempfile
import uuid

from PyQt5.QtCore import Qt, QPoint, QPointF, QByteArray, QBuffer
from PyQt5.QtGui import (
    QImage, QPixmap, QPainter, QPen, QColor, QMouseEvent,
    QKeyEvent, QCursor
)
from PyQt5.QtWidgets import QWidget, QScrollArea
from qfluentwidgets import MessageBoxBase, SubtitleLabel, BodyLabel

from app.plugins.base import InteractivePlugin
from app.utils.utils import ssh_send_file


class UndoCommand:
    """简单的撤销命令类，存储图像状态"""

    def __init__(self, image: QImage):
        self.image = image.copy()


class MaskCanvas(QWidget):
    """
    专业级蒙版绘制控件 (ComfyUI Style)
    功能：无限缩放/移动、撤销/重做、画笔/橡皮、自定义蒙版颜色
    """

    def __init__(self, base64_image: str = None, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        # --- 核心数据 ---
        self.original_pixmap = None
        self.mask_image = None

        # --- 视图变换参数 ---
        self.scale_factor = 1.0
        self.offset = QPointF(0, 0)
        self.min_scale = 0.1
        self.max_scale = 20.0

        # --- 交互状态 ---
        self.is_drawing = False
        self.is_panning = False
        self.last_mouse_pos = QPoint()
        self.draw_mode = "brush"  # brush / eraser

        # --- 工具设置 ---
        self.brush_size = 30
        self.mask_color = QColor(255, 0, 100, 120)  # ComfyUI 风格的紫红色半透明
        self.show_mask = True

        # --- 撤销/重做栈 ---
        self.undo_stack = []
        self.redo_stack = []
        self.max_history = 20

        # --- 初始化加载 ---
        if base64_image:
            self.load_base64_image(base64_image)
        else:
            # 默认占位（如果未提供图片）
            self.resize(512, 512)

    def load_base64_image(self, base64_str: str):
        """加载 Base64 图片并初始化画布"""
        try:
            if "," in base64_str:
                base64_str = base64_str.split(",")[-1]
            image_data = base64.b64decode(base64_str)
            self.original_pixmap = QPixmap()
            self.original_pixmap.loadFromData(image_data)

            # 初始化 mask (ARGB32 Premultiplied 性能更好)
            self.mask_image = QImage(self.original_pixmap.size(), QImage.Format_ARGB32_Premultiplied)
            self.mask_image.fill(Qt.transparent)

            # 初始视图自适应
            self.fit_to_view()
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.update()
        except Exception as e:
            print(f"Error loading image: {e}")

    # ==========================================
    # 视图控制 (Zoom & Pan)
    # ==========================================
    def fit_to_view(self):
        """将图片自适应显示在窗口中心"""
        if not self.original_pixmap:
            return
        img_w = self.original_pixmap.width()
        img_h = self.original_pixmap.height()
        win_w = self.width()
        win_h = self.height()

        scale_w = win_w / img_w
        scale_h = win_h / img_h
        self.scale_factor = min(scale_w, scale_h) * 0.9  # 留一点边距

        # 居中计算
        center_x = (win_w - img_w * self.scale_factor) / 2
        center_y = (win_h - img_h * self.scale_factor) / 2
        self.offset = QPointF(center_x, center_y)

    def map_to_image(self, widget_pos: QPoint) -> QPointF:
        """将窗口坐标映射回图片像素坐标"""
        return (QPointF(widget_pos) - self.offset) / self.scale_factor

    # ==========================================
    # 绘制事件 (Paint)
    # ==========================================
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # 绘制背景 (棋盘格，表示透明)
        self.draw_checkerboard(painter)

        if not self.original_pixmap:
            painter.drawText(self.rect(), Qt.AlignCenter, "No Image Loaded")
            return

        # 应用变换矩阵 (Zoom & Pan)
        painter.translate(self.offset)
        painter.scale(self.scale_factor, self.scale_factor)

        # 1. 绘制原图
        painter.drawPixmap(0, 0, self.original_pixmap)

        # 2. 绘制蒙版层 (Overlay)
        if self.show_mask:
            # 简单方法：Mask Image 实际上保存的是 ARGB。
            painter.drawImage(0, 0, self.mask_image)

        # 3. 绘制笔刷预览 (只有在不绘制时显示圆圈，防止延迟)
        if self.underMouse() and not self.is_panning:
            painter.setPen(QPen(Qt.white, 1 / self.scale_factor, Qt.SolidLine))  # 保持线条细度
            painter.setBrush(Qt.NoBrush)

            # 获取鼠标在图片系的位置
            local_pos = self.map_to_image(self.mapFromGlobal(QCursor.pos()))

            # 绘制圆圈
            radius = self.brush_size / 2
            painter.drawEllipse(local_pos, radius, radius)

            # 再画一个黑色轮廓增强对比度
            painter.setPen(QPen(Qt.black, 1 / self.scale_factor, Qt.DashLine))
            painter.drawEllipse(local_pos, radius, radius)

    def draw_checkerboard(self, painter):
        """绘制透明背景棋盘格"""
        bg_color2 = QColor(160, 160, 160)
        # 简单绘制全屏背景，不做复杂的视差滚动，提高性能
        painter.fillRect(self.rect(), bg_color2)
        # 若需要更精细的背景可在此扩展，但对于大图蒙版，纯灰底通常更护眼

    # ==========================================
    # 交互事件 (Mouse & Key)
    # ==========================================
    def wheelEvent(self, event):
        """滚轮缩放"""
        zoom_in = event.angleDelta().y() > 0
        multiplier = 1.15 if zoom_in else 1 / 1.15

        new_scale = self.scale_factor * multiplier
        new_scale = max(self.min_scale, min(new_scale, self.max_scale))

        # 以鼠标为中心缩放
        mouse_pos = event.pos()
        # 公式: offset = mouse - (mouse - old_offset) * (new_scale / old_scale)
        delta = QPointF(mouse_pos) - self.offset
        self.offset = QPointF(mouse_pos) - delta * (new_scale / self.scale_factor)
        self.scale_factor = new_scale

        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        self.last_mouse_pos = event.pos()

        # 中键 或 (空格+左键) -> 平移
        if event.button() == Qt.MiddleButton or (
                event.button() == Qt.LeftButton and event.modifiers()):
            self.is_panning = True
            self.setCursor(Qt.ClosedHandCursor)
            return

        # 左键/右键 -> 绘制
        if event.button() in (Qt.LeftButton, Qt.RightButton):
            if not self.original_pixmap: return

            # 保存当前状态到撤销栈
            self.push_undo()

            self.is_drawing = True
            self.draw_mode = "eraser" if event.button() == Qt.RightButton else "brush"

            img_pos = self.map_to_image(event.pos())
            self.paint_on_mask(img_pos)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        current_pos = event.pos()

        if self.is_panning:
            delta = current_pos - self.last_mouse_pos
            self.offset += QPointF(delta)
            self.last_mouse_pos = current_pos
            self.update()
            return

        if self.is_drawing:
            # 插值绘制线条，防止快速移动断层
            start_pos = self.map_to_image(self.last_mouse_pos)
            end_pos = self.map_to_image(current_pos)
            self.paint_line_on_mask(start_pos, end_pos)
            self.last_mouse_pos = current_pos
            self.update()
        else:
            # 仅更新光标位置
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MiddleButton or self.is_panning:
            self.is_panning = False
            self.setCursor(Qt.ArrowCursor)

        if event.button() in (Qt.LeftButton, Qt.RightButton):
            self.is_drawing = False

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()

        # 笔刷大小调整 [ ]
        if key == Qt.Key_BracketLeft:
            self.brush_size = max(1, self.brush_size - 5)
            self.update()
        elif key == Qt.Key_BracketRight:
            self.brush_size = min(500, self.brush_size + 5)
            self.update()

        # 撤销/重做 (Ctrl+Z, Ctrl+Y/Shift+Z)
        elif event.modifiers() & Qt.ControlModifier:
            if key == Qt.Key_Z:
                self.undo()
            elif key == Qt.Key_Y or (key == Qt.Key_Z and event.modifiers() & Qt.ShiftModifier):
                self.redo()

        # 功能快捷键
        elif key == Qt.Key_C:
            self.clear_mask()
        elif key == Qt.Key_F:  # Fill
            self.fill_mask()
        elif key == Qt.Key_M:  # Toggle Visibility
            self.show_mask = not self.show_mask
            self.update()
        elif key == Qt.Key_S:  # Switch Color (方便在亮色/暗色图上切换)
            current = self.mask_color
            if current.red() > 100:  # 如果是红粉色，切成半透明黑
                self.mask_color = QColor(0, 0, 0, 150)
            else:
                self.mask_color = QColor(255, 0, 100, 120)
        elif key == Qt.Key_R:  # Reset View
            self.fit_to_view()
            self.update()

    # ==========================================
    # 绘制逻辑 (Mask Manipulation)
    # ==========================================
    def paint_on_mask(self, pos: QPointF):
        """画一个点"""
        painter = QPainter(self.mask_image)
        painter.setRenderHint(QPainter.Antialiasing, True)

        if self.draw_mode == "brush":
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.mask_color)
            painter.drawEllipse(pos, self.brush_size / 2, self.brush_size / 2)
        else:  # Eraser
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.setPen(Qt.NoPen)
            painter.setBrush(Qt.transparent)  # 任何颜色都行，关键是 CompositionMode_Clear
            painter.drawEllipse(pos, self.brush_size / 2, self.brush_size / 2)

        painter.end()

    def paint_line_on_mask(self, start: QPointF, end: QPointF):
        """画线条（解决快速移动断触问题）"""
        painter = QPainter(self.mask_image)
        painter.setRenderHint(QPainter.Antialiasing, True)

        pen_color = self.mask_color if self.draw_mode == "brush" else QColor(0, 0, 0, 0)
        mode = QPainter.CompositionMode_SourceOver if self.draw_mode == "brush" else QPainter.CompositionMode_Clear

        painter.setCompositionMode(mode)
        pen = QPen(pen_color, self.brush_size, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(start, end)
        painter.end()

    # ==========================================
    # 撤销/重做逻辑
    # ==========================================
    def push_undo(self):
        if self.mask_image:
            # 限制栈大小
            if len(self.undo_stack) >= self.max_history:
                self.undo_stack.pop(0)
            self.undo_stack.append(UndoCommand(self.mask_image))
            self.redo_stack.clear()  # 新的操作会清空重做栈

    def undo(self):
        if self.undo_stack:
            command = self.undo_stack.pop()
            self.redo_stack.append(UndoCommand(self.mask_image))
            self.mask_image = command.image.copy()
            self.update()

    def redo(self):
        if self.redo_stack:
            command = self.redo_stack.pop()
            self.undo_stack.append(UndoCommand(self.mask_image))
            self.mask_image = command.image.copy()
            self.update()

    def clear_mask(self):
        self.push_undo()
        self.mask_image.fill(Qt.transparent)
        self.update()

    def fill_mask(self):
        self.push_undo()
        self.mask_image.fill(self.mask_color)
        self.update()

    # ==========================================
    # 输出
    # ==========================================
    def get_mask_base64(self) -> str:
        """提取 Mask 的 Base64（仅 Alpha 通道，转为黑白 PNG）"""
        alpha_img = self.mask_image.convertToFormat(QImage.Format_Grayscale8)
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QBuffer.WriteOnly)
        alpha_img.save(buffer, "PNG")
        buffer.close()
        b64 = bytes(byte_array.toBase64()).decode("utf-8")
        return f"data:image/png;base64,{b64}"


class MaskDrawDialog(MessageBoxBase):
    """
    自适应动态表单对话框，用于人工干预
    """
    def __init__(self, title: str, image: str, parent=None):
        super().__init__(parent)
        self.inputs = {}
        self.image = image
        # 1. 标题
        self.titleLabel = SubtitleLabel(title)
        self.viewLayout.addWidget(self.titleLabel)

        # 3. 动态根据 schema 生成表单
        self._setup_ui()
        # 设置对话框宽度
        self.widget.setMinimumWidth(800)
        self.widget.setMinimumHeight(700)

    def _add_shortcut_hint(self):
        hint_text = (
            "<b>快捷键说明:</b><br>"
            "• 左键拖动：绘制蒙版 • CTRL+Z：撤销 ; • [ ]：调整笔刷大小; • C：清空; S: 切换笔刷颜色;<br>"
        )
        hint_label = BodyLabel(hint_text)
        hint_label.setStyleSheet("font-size: 11px; color: #888;")
        self.viewLayout.addWidget(hint_label)

    def _setup_ui(self):
        self._add_shortcut_hint()
        canvas = MaskCanvas(self.image)
        scroll = QScrollArea()
        scroll.setWidget(canvas)
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(400)
        self.viewLayout.addWidget(scroll)
        self.inputs["mask"] = (canvas, "get_mask_base64")  # ← 注意方法名

    def get_result(self):
        """解析所有控件的值并返回字典"""
        result = {}
        for field_name, (widget, getter_name) in self.inputs.items():
            getter = getattr(widget, getter_name)
            # 处理可调用对象或直接属性
            val = getter() if callable(getter) else getter
            result[field_name] = val
        return result


class DrawMaskPlugin(InteractivePlugin):
    plugin_id = "draw_mask"  # 对应 method: "ui.ask"

    def handle(self, node, params, msg=None):
        title = params.get("title", "人工干预")
        response_file = params.get("response_file")
        image = params.get("schema").get("image")

        env_data = getattr(node.parent_window, 'env_data', None)
        is_ssh = env_data and env_data.get('type') == 'ssh'

        def on_confirmed(result_data):
            if is_ssh:
                temp_path = os.path.join(tempfile.gettempdir(), f"ask_{uuid.uuid4().hex}.pkl")
                with open(temp_path, 'wb') as f:
                    pickle.dump(result_data, f)
                ssh_send_file(env_data, temp_path, response_file)
                if os.path.exists(temp_path): os.remove(temp_path)
            else:
                os.makedirs(os.path.dirname(response_file), exist_ok=True)
                with open(response_file, 'wb') as f:
                    pickle.dump(result_data, f)

        # 创建并显示对话框
        dialog = MaskDrawDialog(title, image, node.parent_window)
        dialog.yesButton.setText("确认并继续")
        dialog.cancelButton.hide()

        if dialog.exec():
            # 用户点击了“确认”
            result_data = dialog.get_result()
            on_confirmed(result_data)