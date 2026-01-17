# -*- coding: utf-8 -*-
import base64

from PyQt5.QtCore import Qt, QPoint, QPointF, QByteArray, QBuffer
from PyQt5.QtGui import (
    QImage, QPixmap, QPainter, QPen, QColor, QMouseEvent,
    QKeyEvent, QCursor
)
from PyQt5.QtWidgets import QWidget, QApplication, QVBoxLayout, QPushButton, QHBoxLayout


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
            # 使用 CompositionMode 实现高性能染色
            # 仅在需要重绘时才应该生成 overlay，为了性能，我们直接绘制 mask_image
            # 并利用 setCompositionMode 改变颜色是比较复杂的，这里用简易方案：
            # 绘制原始 mask_image (alpha通道)，然后用指定的颜色填充非透明区域

            # 方案：直接画 mask_image，但是在 mask 像素存在的地方画上 mask_color
            # 为了效率，我们可以在 paintEvent 外部维护一个 colored_mask，或者
            # 这里简单地使用 SourceOver 绘制 mask_image (假设 mask_image 已经是 colored)
            # 但为了橡皮擦方便，mask_image 存的是 Alpha 或 纯色。

            # ComfyUI 风格渲染：
            # 我们直接绘制 Mask Image，但需要在 Mask 上应用颜色。
            # 简单方法：Mask Image 实际上保存的是 ARGB。
            painter.drawImage(0, 0, self.mask_image)

        # 3. 绘制笔刷预览 (只有在不绘制时显示圆圈，防止延迟)
        # 需要反向变换笔刷大小以便在缩放后看起来大小一致?
        # 不，通常笔刷是相对于图片的像素大小 (ComfyUI逻辑)
        # 所以在 translate/scale 的上下文中绘制圆圈即可
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
        bg_color1 = QColor(200, 200, 200)
        bg_color2 = QColor(160, 160, 160)
        grid_size = 20

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
            # 颜色变了，需要重新渲染当前的mask图层颜色（稍微复杂，这里暂略，主要影响新画的笔触）
            # 简单做法：遍历像素太慢。通常应该把Mask存为只有Alpha的图，绘制时用颜色填充。
            # 为了演示方便，我们这里只改变后续笔刷颜色。若要实时改变已画颜色，需要重构 mask 存储方式为 Alpha8。

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


# ==========================================
# 测试代码
# ==========================================
if __name__ == "__main__":
    import sys

    # 创建一个测试用的 Base64 图片 (简单的红点图)
    # 实际使用时直接传入你的图片 base64
    img = QImage(800, 600, QImage.Format_RGB32)
    img.fill(QColor("gray"))
    p = QPainter(img)
    p.setBrush(Qt.blue)
    p.drawRect(200, 200, 400, 200)
    p.end()
    ba = QByteArray()
    buf = QBuffer(ba)
    img.save(buf, "PNG")
    b64_str = str(ba.toBase64(), 'utf-8')

    app = QApplication(sys.argv)

    window = QWidget()
    layout = QVBoxLayout(window)

    canvas = MaskCanvas(b64_str)

    # 添加说明
    info = QHBoxLayout()
    btn_clear = QPushButton("Clear (C)")
    btn_clear.clicked.connect(canvas.clear_mask)
    info.addWidget(btn_clear)
    info.addWidget(QPushButton("Zoom: Scroll"))
    info.addWidget(QPushButton("Pan: Middle / Space+Left"))
    info.addWidget(QPushButton("Size: [ ]"))
    info.addWidget(QPushButton("Undo: Ctrl+Z"))

    layout.addWidget(canvas)
    layout.addLayout(info)

    window.resize(1000, 800)
    window.show()

    sys.exit(app.exec_())