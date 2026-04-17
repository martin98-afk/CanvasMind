# -*- coding: utf-8 -*-
from PyQt5.QtCore import QPropertyAnimation, QEasingCurve, QRect, QTimer
from PyQt5.QtWidgets import QWidget


class StaggerAnimator:
    def __init__(self, widget, index=0, delay_ms=50, duration=200):
        self.widget = widget
        self.index = index
        self.delay_ms = delay_ms
        self.duration = duration
        self.anim = None

    def start(self):
        self.widget.setGraphicsEffect(None)
        from PyQt5.QtGui import QGraphicsOpacityEffect

        effect = QGraphicsOpacityEffect(self.widget)
        self.widget.setGraphicsEffect(effect)
        effect.setOpacity(0)

        def animate():
            self.anim = QPropertyAnimation(effect, b"opacity")
            self.anim.setDuration(self.duration)
            self.anim.setStartValue(0)
            self.anim.setEndValue(1)
            self.anim.setEasingCurve(QEasingCurve.OutCubic)
            self.anim.start()

        QTimer.singleShot(self.delay_ms * self.index, animate)

    def stop(self):
        if self.anim and self.anim.state() == QPropertyAnimation.Running:
            self.anim.stop()


def animate_widget_in(widget, direction="left", duration=300):
    from PyQt5.QtGui import QGraphicsOpacityEffect, QTransform
    from PyQt5.QtCore import QPoint

    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)

    start_x = 30 if direction == "left" else -30
    start_pos = widget.pos() + QPoint(start_x, 0)

    widget.move(start_pos)
    effect.setOpacity(0)

    opacity_anim = QPropertyAnimation(effect, b"opacity")
    opacity_anim.setDuration(duration)
    opacity_anim.setStartValue(0)
    opacity_anim.setEndValue(1)
    opacity_anim.setEasingCurve(QEasingCurve.OutCubic)

    pos_anim = QPropertyAnimation(widget, b"pos")
    pos_anim.setDuration(duration)
    pos_anim.setStartValue(start_pos)
    pos_anim.setEndValue(widget.pos())
    pos_anim.setEasingCurve(QEasingCurve.OutCubic)

    def cleanup():
        widget.setGraphicsEffect(None)

    opacity_anim.finished.connect(cleanup)
    opacity_anim.start()
    pos_anim.start()

    return opacity_anim, pos_anim


def animate_widget_out(widget, direction="right", duration=200):
    from PyQt5.QtGui import QGraphicsOpacityEffect
    from PyQt5.QtCore import QPoint

    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    effect.setOpacity(1)

    end_x = -30 if direction == "left" else 30
    end_pos = widget.pos() + QPoint(end_x, 0)

    opacity_anim = QPropertyAnimation(effect, b"opacity")
    opacity_anim.setDuration(duration)
    opacity_anim.setStartValue(1)
    opacity_anim.setEndValue(0)
    opacity_anim.setEasingCurve(QEasingCurve.InCubic)

    def cleanup():
        widget.setGraphicsEffect(None)

    opacity_anim.finished.connect(cleanup)
    opacity_anim.start()

    return opacity_anim


def fade_in(widget, duration=200):
    from PyQt5.QtGui import QGraphicsOpacityEffect

    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    effect.setOpacity(0)

    anim = QPropertyAnimation(effect, b"opacity")
    anim.setDuration(duration)
    anim.setStartValue(0)
    anim.setEndValue(1)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.start()

    def cleanup():
        if widget.graphicsEffect() == effect:
            widget.setGraphicsEffect(None)

    anim.finished.connect(cleanup)
    return anim


def fade_out(widget, duration=200):
    from PyQt5.QtGui import QGraphicsOpacityEffect

    if not widget.graphicsEffect():
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    else:
        effect = widget.graphicsEffect()

    anim = QPropertyAnimation(effect, b"opacity")
    anim.setDuration(duration)
    anim.setStartValue(1)
    anim.setEndValue(0)
    anim.setEasingCurve(QEasingCurve.InCubic)
    anim.start()
    return anim
