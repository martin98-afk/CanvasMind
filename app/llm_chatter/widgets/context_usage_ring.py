from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import (
    QWidget,
)


class ContextUsageRing(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._percent = 0
        self._ring_color = QColor("#5aa9ff")
        self._track_color = QColor(255, 255, 255, 40)
        self.setFixedSize(18, 18)
        self.setToolTip("上下文占用：0%")

    def set_usage(
        self,
        percent: int,
        used_tokens: int,
        budget_tokens: int,
        compaction: dict = None,
    ):
        self._percent = max(0, min(100, int(percent)))
        if self._percent >= 90:
            self._ring_color = QColor("#ff6b6b")
        elif self._percent >= 70:
            self._ring_color = QColor("#f6c453")
        else:
            self._ring_color = QColor("#5aa9ff")

        tooltip_lines = [
            "当前上下文占用",
            f"已用: {used_tokens} tokens",
            f"预算: {budget_tokens} tokens",
            f"占比: {self._percent}%",
        ]
        compaction = compaction or {}
        if compaction.get("active"):
            tooltip_lines.extend(
                [
                    "",
                    "已启用上下文压缩",
                    f"类型: {compaction.get('kind', '') or 'plain'}",
                    f"压缩条数: {compaction.get('summarized_count', 0)}",
                    f"保留条数: {compaction.get('kept_count', 0)}",
                ]
            )
            note = str(compaction.get("note", "") or "").strip()
            if note:
                tooltip_lines.append(note)

        self.setToolTip("\n".join(tooltip_lines))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(2, 2, -2, -2)
        start_angle = 90 * 16
        span_angle = int(-360 * 16 * (self._percent / 100.0))

        track_pen = QPen(self._track_color, 2.2)
        painter.setPen(track_pen)
        painter.drawArc(rect, 0, 360 * 16)

        ring_pen = QPen(self._ring_color, 2.2)
        painter.setPen(ring_pen)
        painter.drawArc(rect, start_angle, span_angle)
