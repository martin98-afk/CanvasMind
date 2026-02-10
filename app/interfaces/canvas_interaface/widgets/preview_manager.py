# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, QRectF, QPoint, QTimer, QObject, QRect
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen, QFont, QFontMetrics, QLinearGradient, QPixmap
from PyQt5.QtWidgets import QWidget, QGraphicsDropShadowEffect, QApplication

from app.utils.utils import get_canvas_font


class NodePreviewCard(QWidget):
    """
    ComfyUI 风格的悬浮预览卡片
    特点：高性能绘图（非Widget堆叠）、自适应大小、磨砂玻璃感
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        # 数据缓存
        self._data = {}
        self._content_height = 0
        self._port_line_height = 18
        self._base_width = 320
        self._padding = 16

        # 字体缓存
        self.title_font = get_canvas_font(11, True)
        self.cat_font = get_canvas_font(9)
        self.desc_font = get_canvas_font(9)
        self.port_font = get_canvas_font(8)

        # 阴影效果
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(20)
        self.shadow.setColor(QColor(0, 0, 0, 150))
        self.shadow.setOffset(0, 4)
        self.setGraphicsEffect(self.shadow)

    def set_data(self, info: dict):
        """
        设置显示数据，info 结构参考:
        {
            'name': 'Node Name',
            'category': 'Category',
            'description': 'Description...',
            'inputs': [('type', 'name'), ...],
            'outputs': [('type', 'name'), ...]
        }
        """
        self._data = info
        self._calculate_layout()
        self.update()

    def _calculate_layout(self):
        """预计算高度，避免大片空白"""
        current_y = self._padding * 2 + 30  # 标题 + 类别区域

        # 描述文本高度计算
        desc = self._data.get('description', '')
        if desc:
            fm = QFontMetrics(self.desc_font)
            rect = fm.boundingRect(QRect(0, 0, self._base_width - self._padding * 2, 1000),
                                   Qt.TextWordWrap, desc)
            current_y += rect.height() + 10

        # 端口高度计算 (Input 和 Output 并排，取最大值)
        inputs = self._data.get('inputs', [])
        outputs = self._data.get('outputs', [])

        max_ports = max(len(inputs), len(outputs))

        if max_ports > 0:
            current_y += 10  # 分割线间距
            # 标题 "INPUTS" / "OUTPUTS"
            current_y += 15
            # 端口列表
            current_y += max_ports * self._port_line_height

        total_height = current_y + self._padding
        self.resize(self._base_width, int(total_height))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        w, h = self.width(), self.height()

        # 1. 绘制背景 (ComfyUI 深色磨砂风格)
        path = QPainterPath()
        path.addRoundedRect(QRectF(2, 2, w - 4, h - 4), 10, 10)

        # 渐变背景
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0, QColor(45, 45, 48, 245))
        grad.setColorAt(1, QColor(30, 30, 32, 250))

        painter.fillPath(path, grad)

        # 边框高亮 (顶部亮，底部暗，模拟光照)
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1.5))
        painter.drawPath(path)

        # 2. 绘制内容
        content_rect = QRect(self._padding, self._padding, w - self._padding * 2, h - self._padding * 2)
        y_cursor = self._padding + 4

        # --- 标题 ---
        painter.setPen(QColor(230, 230, 230))
        painter.setFont(self.title_font)
        painter.drawText(QRect(self._padding, y_cursor, int(content_rect.width()), 20),
                         Qt.AlignLeft | Qt.AlignTop, self._data.get('name', 'Unknown'))
        y_cursor += 22

        # --- 类别 ---
        painter.setPen(QColor(150, 150, 150))
        painter.setFont(self.cat_font)
        cat_rect = QRect(self._padding, y_cursor, int(content_rect.width()), 16)
        painter.drawText(cat_rect, Qt.AlignLeft, f"📁 {self._data.get('category', 'General')}")
        y_cursor += 20

        # --- 描述 ---
        desc = self._data.get('description', '')
        if desc:
            painter.setPen(QColor(180, 180, 180))
            painter.setFont(self.desc_font)
            fm = QFontMetrics(self.desc_font)
            desc_rect = fm.boundingRect(QRect(self._padding, y_cursor, int(content_rect.width()), 1000),
                                        Qt.TextWordWrap, desc)
            painter.drawText(desc_rect, Qt.AlignLeft | Qt.TextWordWrap, desc)
            y_cursor += desc_rect.height() + 10

        # --- 端口区域 ---
        inputs = self._data.get('inputs', [])
        outputs = self._data.get('outputs', [])
        input_types = self._data.get("input_sub_types", [None] * len(inputs))
        output_types = self._data.get("output_sub_types", [None] * len(outputs))

        if inputs or outputs:
            # 分割线
            painter.setPen(QPen(QColor(255, 255, 255, 20), 1))
            painter.drawLine(int(self._padding), int(y_cursor), int(w - self._padding), int(y_cursor))
            y_cursor += 10

            # 端口标题
            header_font = get_canvas_font(7, True)
            painter.setFont(header_font)
            if inputs:
                painter.setPen(QColor("#4ADE80"))  # Green
                painter.drawText(QRect(self._padding, y_cursor, int(w / 2), 12), Qt.AlignLeft, "INPUTS")
            if outputs:
                painter.setPen(QColor("#F87171"))  # Red
                painter.drawText(QRect(int(w / 2), y_cursor, int(w / 2 - self._padding), 12), Qt.AlignRight, "OUTPUTS")

            y_cursor += 15
            start_y_ports = y_cursor

            # === 辅助函数：仅计算胶囊宽度（不绘制）===
            def get_badge_width(text):
                if not text or not text.strip():
                    return 0
                badge_font = get_canvas_font(8, bold=True)
                fm_badge = QFontMetrics(badge_font)
                clean_text = text[:15].upper().strip()
                text_width = fm_badge.horizontalAdvance(clean_text)
                return text_width + 14  # 6px padding each side + 2px border

            # === 辅助函数：绘制胶囊（不返回宽度）===
            def draw_badge(painter, x, y, text, is_input):
                if not text or not text.strip():
                    return
                badge_font = get_canvas_font(8, bold=True)
                fm_badge = QFontMetrics(badge_font)
                clean_text = text[:15].upper().strip()
                text_width = fm_badge.horizontalAdvance(clean_text)
                badge_w = text_width + 14
                badge_h = 14

                # 颜色定义（与PortRow完全一致）
                border_color = QColor("#4ADE80") if is_input else QColor("#F87171")
                bg_color = QColor(74, 222, 128, 102) if is_input else QColor(248, 113, 113, 102)  # 0.4 opacity

                # 绘制圆角矩形
                painter.setPen(QPen(border_color, 1))
                painter.setBrush(bg_color)
                painter.drawRoundedRect(int(x), int(y), int(badge_w), int(badge_h), 4, 4)

                # 绘制文字
                painter.setPen(QColor(255, 255, 255))
                painter.setFont(badge_font)
                painter.drawText(QRect(int(x) + 6, int(y), int(badge_w) - 12, int(badge_h)),
                                 Qt.AlignCenter, clean_text)

            # === 绘制输入端口 (左侧) ===
            painter.setFont(self.port_font)
            for i, (inp_data, inp_type) in enumerate(zip(inputs[:10], input_types[:10])):
                # 安全提取类型和名称
                try:
                    p_type = str(inp_type)[:5] if inp_type else (
                        str(inp_data[-2].value) if hasattr(inp_data[-2], 'value') else str(inp_data[0]))
                except:
                    p_type = ""
                p_name = str(inp_data[1]) if len(inp_data) > 1 else str(inp_data[0])

                row_y = start_y_ports + i * self._port_line_height

                # 1. 圆点 (x = padding + 3, y = row_y + 5)
                painter.setBrush(QColor("#4ADE80"))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPoint(int(self._padding) + 3, int(row_y) + 5), 3, 3)

                # 2. 胶囊标签（圆点右侧 6px 间距）
                badge_w = get_badge_width(p_type)
                if badge_w > 0:
                    badge_x = self._padding + 3 + 3 + 6  # 圆点中心(3) + 半径(3) + 间距(6)
                    badge_y = row_y + 2  # 18px行高 - 14px胶囊 = 4px余量，上下各2px
                    draw_badge(painter, badge_x, badge_y, p_type, is_input=True)
                    text_x = badge_x + badge_w + 6  # 胶囊右侧 + 6px间距
                else:
                    text_x = self._padding + 12  # 无类型时直接从圆点右侧开始

                # 3. 端口名
                text_w = int(w / 2) - text_x - 10
                if text_w > 0:
                    painter.setPen(QColor(220, 220, 220))
                    painter.setFont(self.port_font)
                    painter.drawText(QRect(int(text_x), int(row_y), int(text_w), self._port_line_height),
                                     Qt.AlignLeft | Qt.AlignVCenter, p_name)

            # === 绘制输出端口 (右侧) ===
            for i, (out_data, out_type) in enumerate(zip(outputs[:10], output_types[:10])):
                # 安全提取类型和名称
                try:
                    p_type = str(out_type)[:5] if out_type else (
                        str(out_data[-2].value) if hasattr(out_data[-2], 'value') else str(out_data[0]))
                except:
                    p_type = ""
                p_name = str(out_data[1]) if len(out_data) > 1 else str(out_data[0])

                row_y = start_y_ports + i * self._port_line_height

                # 1. 圆点 (x = w - padding - 3, y = row_y + 5)
                painter.setBrush(QColor("#F87171"))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPoint(int(w - self._padding) - 3, int(row_y) + 5), 3, 3)

                # 2. 胶囊标签（圆点左侧 6px 间距）
                badge_w = get_badge_width(p_type)
                if badge_w > 0:
                    # 胶囊右边缘 = 圆点中心 - 6px间距 - 圆点半径(3px) = w - padding - 3 - 6 - 3 = w - padding - 12
                    badge_x = int(w - self._padding) - 12 - badge_w  # 胶囊左边缘
                    badge_y = row_y + 2
                    draw_badge(painter, badge_x, badge_y, p_type, is_input=False)
                    text_right = badge_x - 6  # 端口名右边界 = 胶囊左侧 - 6px间距
                else:
                    text_right = int(w - self._padding) - 12  # 无类型时直接到圆点左侧

                # 3. 端口名（右对齐）
                text_x = int(w / 2) + 10
                text_w = text_right - text_x
                if text_w > 0:
                    painter.setPen(QColor(220, 220, 220))
                    painter.setFont(self.port_font)
                    painter.drawText(QRect(int(text_x), int(row_y), int(text_w), self._port_line_height),
                                     Qt.AlignRight | Qt.AlignVCenter, p_name)


class ImagePreviewCard(QWidget):
    """
    【图片预览卡片】
    专门用于显示子图模板的截图
    特点：支持大图、保持比例、纯净展示
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._data = {}
        self._base_width = 400  # 图片预览默认宽一点
        self._padding = 12
        self._title_height = 30
        self.title_font = get_canvas_font(11, True)

        # 阴影
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(20)
        self.shadow.setColor(QColor(0, 0, 0, 150))
        self.shadow.setOffset(0, 4)
        self.setGraphicsEffect(self.shadow)

    def set_data(self, info: dict):
        """
        info: { 'name': str, 'image_path': str }
        """
        self._data = info
        self._calculate_layout()
        self.update()

    def _calculate_layout(self):
        img_path = self._data.get('image_path')
        if not img_path:
            self.resize(self._base_width, 100)
            return

        pix = QPixmap(img_path)
        if pix.isNull():
            self.resize(self._base_width, 100)
            return

        # 计算自适应高度
        # 限制图片最大宽高，避免遮挡整个屏幕
        max_img_w = 350
        max_img_h = 400

        available_w = min(self._base_width, max_img_w) - self._padding * 2

        # 按比例缩放
        scaled = pix.scaled(int(available_w), max_img_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        content_h = self._padding + self._title_height + scaled.height() + self._padding
        self.resize(int(available_w + self._padding * 2), int(content_h))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        w, h = self.width(), self.height()

        # 1. 背景
        path = QPainterPath()
        path.addRoundedRect(QRectF(2, 2, w - 4, h - 4), 10, 10)
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0, QColor(45, 45, 48, 250))  # 图片预览稍微不透明一点
        grad.setColorAt(1, QColor(30, 30, 32, 252))
        painter.fillPath(path, grad)
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1.5))
        painter.drawPath(path)

        # 2. 标题
        painter.setPen(QColor(230, 230, 230))
        painter.setFont(self.title_font)
        painter.drawText(QRect(self._padding, self._padding, w - self._padding * 2, 20),
                         Qt.AlignLeft | Qt.AlignVCenter, self._data.get('name', 'Preview'))

        # 3. 图片
        img_path = self._data.get('image_path')
        if img_path:
            pix = QPixmap(img_path)
            if not pix.isNull():
                y_start = self._padding + self._title_height
                available_w = w - self._padding * 2
                available_h = h - y_start - self._padding

                scaled = pix.scaled(int(available_w), int(available_h), Qt.KeepAspectRatio, Qt.SmoothTransformation)

                # 居中绘制
                x_offset = self._padding + (available_w - scaled.width()) / 2
                painter.drawPixmap(int(x_offset), int(y_start), scaled)


class PreviewManager(QObject):
    """
    【预览管理器】
    调度中心：根据数据类型，决定显示 NodeCard 还是 ImageCard
    """
    _instance = None

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = PreviewManager()
        return cls._instance

    def __init__(self):
        super().__init__()
        # 实例化两张卡片
        self._node_card = NodePreviewCard()
        self._image_card = ImagePreviewCard()

        # 当前正在显示的卡片引用
        self._active_card = None

        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._real_show)

        self._pending_data = None
        self._pending_pos = None

    def show_preview(self, data: dict, global_pos: QPoint, target_widget: QWidget, delay=350):
        """
        :param data:
            如果是节点: {'name':..., 'inputs':...}
            如果是图片: {'name':..., 'image_path':...}
        """
        # 如果正在显示且内容没变，跳过
        if self._active_card and self._active_card.isVisible() and self._pending_data == data:
            return

        self._pending_data = data
        self._pending_pos = global_pos

        # 重置定时器防抖
        self._timer.stop()
        if delay > 0:
            self._timer.start(delay)
        else:
            self._real_show()

    def hide_preview(self):
        self._timer.stop()
        if self._node_card.isVisible():
            self._node_card.hide()
        if self._image_card.isVisible():
            self._image_card.hide()
        self._active_card = None
        self._pending_data = None

    def _real_show(self):
        if not self._pending_data:
            return

        # 1. 决定使用哪张卡片
        if 'image_path' in self._pending_data:
            self._active_card = self._image_card
            self._node_card.hide()  # 确保另一张隐藏
        else:
            self._active_card = self._node_card
            self._image_card.hide()

        # 2. 设置数据 & 调整大小
        self._active_card.set_data(self._pending_data)

        # 3. 智能定位
        self._move_card_smartly(self._active_card, self._pending_pos)

        # 4. 显示
        self._active_card.show()

    def _move_card_smartly(self, card, pos):
        """计算位置，防止溢出屏幕"""
        screen_geo = QApplication.primaryScreen().availableGeometry()
        card_w, card_h = card.width(), card.height()

        x = pos.x() + 20
        y = pos.y() + 10

        # 右侧溢出 -> 放左侧
        if x + card_w > screen_geo.right():
            x = pos.x() - card_w - 40

        # 底部溢出 -> 向上提
        if y + card_h > screen_geo.bottom():
            y = screen_geo.bottom() - card_h - 10

        # 顶部溢出 -> 顶格
        if y < screen_geo.top():
            y = screen_geo.top() + 10

        # 左侧溢出 (极少情况) -> 顶格
        if x < screen_geo.left():
            x = screen_geo.left() + 10

        card.move(int(x), int(y))


# 全局快捷访问
def show_component_preview(data, pos, widget):
    PreviewManager.get_instance().show_preview(data, pos, widget)


def hide_component_preview():
    PreviewManager.get_instance().hide_preview()