# -- coding: utf-8 --
from collections import OrderedDict

from PyQt5 import QtCore
from PyQt5.QtCore import (Qt, QPropertyAnimation, QRect, QParallelAnimationGroup, QEasingCurve, pyqtProperty,
                          pyqtSignal, QTimer, QRectF, QLineF)
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QFont, QPainterPath
from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QWidget, QSizePolicy, QFrame, QGraphicsOpacityEffect,
                             QScrollArea)
from qfluentwidgets import SmoothScrollArea, StrongBodyLabel, IconWidget, FluentIcon, TransparentToolButton

# 保持业务相关的引用
from app.components.base import ArgumentType
from app.nodes.backdrop_node import ControlFlowBackdrop
from app.scan_components import ComponentScanner
from app.widgets.side_dock_area.plugins.property_panel.flow_control_panel import FlowControlPanelWidget
from app.widgets.side_dock_area.plugins.property_panel.global_panel import GlobalPanelWidget
from app.widgets.side_dock_area.plugins.property_panel.node_list_panel import NodeListPanelWidget
from app.widgets.side_dock_area.plugins.property_panel.node_panel import NodePanelWidget


class FuturisticCard(QFrame):
    closed = pyqtSignal(object)

    def __init__(self, parent=None, title="Unknown Node", icon=FluentIcon.DEVELOPER_TOOLS):
        super().__init__(parent)
        self.is_active = False
        self._custom_opacity = 1.0
        self._last_rect = QRect()
        self._border_path = QPainterPath()
        # 缓存扫描线，避免每帧重复创建对象
        self._cached_scan_lines = []

        self.COLOR_ACTIVE_TOP = QColor("#00a2ff")
        self.COLOR_INACTIVE_TOP = QColor("#666666")
        self.COLOR_SIDE = QColor("#2d2d2d")
        self.COLOR_TEXT_DIM = QColor("#828282")

        self.BG_ACTIVE = QColor("#1e1e1e")
        self.BG_INACTIVE = QColor("#141414")

        self.SCAN_LINE_PEN = QPen(QColor(255, 255, 255, 5), 1)

        self.setAttribute(Qt.WA_StyledBackground, True)
        # 性能优化：禁用系统自动背景清除，因为paintEvent会处理，减少重绘闪烁
        self.setAttribute(Qt.WA_NoSystemBackground, True)

        self.setObjectName("PropertyCard")
        self.setStyleSheet("QWidget#PropertyCard { background: transparent; border: none; }")

        self.card_layout = QVBoxLayout(self)
        self.card_layout.setContentsMargins(0, 0, 0, 0)
        self.card_layout.setSpacing(0)

        self.header_hud = QWidget()
        self.header_hud.setFixedHeight(40)
        header_layout = QHBoxLayout(self.header_hud)
        header_layout.setContentsMargins(18, 0, 10, 0)

        try:
            self.icon_widget = IconWidget(icon, self.header_hud)
        except Exception as e:
            self.icon_widget = IconWidget(FluentIcon.DEVELOPER_TOOLS, self.header_hud)
        self.icon_widget.setFixedSize(18, 18)
        self.title_label = StrongBodyLabel(title, self.header_hud)
        self.title_label.setFont(QFont("Segoe UI Semibold", 13))

        self.close_btn = TransparentToolButton(FluentIcon.CLOSE, self.header_hud)
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet("""
            TransparentToolButton { border-radius: 4px; padding: 4px; }
            TransparentToolButton:hover { background-color: rgba(255, 60, 60, 0.2); }
        """)

        self.close_btn_opacity = QGraphicsOpacityEffect(self.close_btn)
        self.close_btn.setGraphicsEffect(self.close_btn_opacity)
        self.close_btn.clicked.connect(lambda: self.closed.emit(self))

        header_layout.addWidget(self.icon_widget)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.close_btn)
        self.card_layout.addWidget(self.header_hud)

        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(4, 2, 4, 4)
        self.card_layout.addWidget(self.content_area, 1)

    @pyqtProperty(float)
    def cardOpacity(self):
        return self._custom_opacity

    @cardOpacity.setter
    def cardOpacity(self, v):
        self._custom_opacity = 1.0
        self.update()

    def set_title(self, title):
        self.title_label.setText(title)

    def set_active(self, active: bool, level: int = 0, animate: bool = True):
        self.is_active = active
        text_color = self.COLOR_ACTIVE_TOP if active else self.COLOR_TEXT_DIM
        self.title_label.setStyleSheet(f"color: {text_color.name()};")
        self.update()

    def paintEvent(self, event):
        # 性能优化：大幅优化绘图逻辑
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        current_rect = self.rect()
        rect_f = QRectF(current_rect)
        r = 14.0

        # 仅当尺寸发生变化时重新计算路径和线条，避免每帧重复计算
        if self._last_rect != current_rect:
            w, h = current_rect.width(), current_rect.height()

            # 1. 重新生成边框路径
            self._border_path = QPainterPath()
            self._border_path.moveTo(0, r)
            self._border_path.arcTo(0, 0, r * 2, r * 2, 180, -90)
            self._border_path.lineTo(w - r, 0)
            self._border_path.arcTo(w - r * 2, 0, r * 2, r * 2, 90, -90)
            self._border_path.lineTo(w, h)
            self._border_path.lineTo(0, h)
            self._border_path.closeSubpath()

            # 2. 重新生成扫描线缓存 (性能关键点：避免在循环中调用 drawLine)
            self._cached_scan_lines = [
                QLineF(0, y, w, y)
                for y in range(0, h, 10)
            ]

            self._last_rect = current_rect

        # 绘制背景
        p.fillPath(self._border_path, QBrush(self.BG_ACTIVE if self.is_active else self.BG_INACTIVE))

        # 批量绘制扫描线 (比循环调用快得多)
        p.setPen(self.SCAN_LINE_PEN)
        p.drawLines(self._cached_scan_lines)

        # 绘制顶部高亮装饰
        top_pen = QPen(self.COLOR_ACTIVE_TOP if self.is_active else self.COLOR_INACTIVE_TOP, 2)
        p.setPen(top_pen)
        # 注意：这里直接使用计算好的数值，减少对象创建
        w_f = rect_f.width()
        p.drawArc(QtCore.QRectF(0, 0, r * 2, r * 2), 1440, 1440)  # 90*16, 90*16
        p.drawLine(QtCore.QPointF(r, 0), QtCore.QPointF(w_f - r, 0))
        p.drawArc(QtCore.QRectF(w_f - r * 2, 0, r * 2, r * 2), 0, 1440)  # 0*16, 90*16

        # 绘制侧边装饰
        side_pen = QPen(self.COLOR_SIDE, 1)
        p.setPen(side_pen)
        h_f = rect_f.height()
        p.drawLine(QtCore.QPointF(0, r), QtCore.QPointF(0, h_f))
        p.drawLine(QtCore.QPointF(w_f, r), QtCore.QPointF(w_f, h_f))

    def cleanup(self):
        """主动断开所有引用，辅助 GC 回收"""
        # 1. 尝试调用内部逻辑控件的清理方法（如果有线程需要停止）
        if self._logic and hasattr(self._logic, 'cleanup'):
            try:
                self._logic.cleanup()
            except Exception:
                pass

        # 2. 断开所有信号连接
        try:
            self.closed.disconnect()
        except TypeError:
            pass  # 可能已经断开了

        # 3. 移除内容控件
        if self._logic:
            self.content_layout.removeWidget(self._logic)
            self._logic.deleteLater()
            self._logic = None

        # 4. 断开对业务对象（Node）的引用
        self._node_ref = None

        # 5. 清理缓存的大对象
        self._cached_scan_lines = []


class PropertyPanel(QWidget):
    def __init__(self, main_window, parent=None, max_history=3, header_height=40):
        super().__init__(parent)
        self.main_window = main_window
        self._max_history = max_history
        self._header_reveal_h = header_height

        self.setMinimumWidth(280)
        self.setMinimumHeight(250)

        self._node_panel_cache = OrderedDict()
        self._max_cache_size = 50
        self._history_stack = []
        self._allowed_update = False
        self._global_panel_built = False
        self.current_node = None

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._on_resize_timeout)
        self._is_resizing = False

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("UltimatePropertyPanel")
        self.setStyleSheet("#UltimatePropertyPanel { background-color: transparent; }")

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.stage = QWidget()
        self.main_layout.addWidget(self.stage)

        self.node_list_panel_widget = None
        self.flow_control_panel_widget = None
        self.node_panel_widget = None
        self.global_panel_widget = None

        self.anim_group = QParallelAnimationGroup(self)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(300, lambda: self._sync_stack_layout(animate=False))

    def closeEvent(self, event):
        """面板关闭时，清理所有资源"""
        self._clear_node_layout()
        # 即使是全局变量面板，在整个 App 关闭或 Panel 销毁时也应该清理
        if self.global_panel_widget:
            # 如果 GlobalPanel 有线程或特定资源，这里也应该调用清理
            if hasattr(self.global_panel_widget, 'close'):
                self.global_panel_widget.close()
            self.global_panel_widget = None

        self.anim_group.stop()
        self.anim_group.clear()
        super().closeEvent(event)

    def update_properties(self, node):
        if not self._allowed_update:
            return

        if node is None:
            cache_key = "GLOBAL_DASHBOARD"
        elif isinstance(node, list):
            cache_key = "MULTI_LIST_VIEW"
        else:
            cache_key = node.name()

        if cache_key in self._node_panel_cache:
            target_card = self._node_panel_cache[cache_key]
        else:
            target_card = self._create_card_widget(node, cache_key)
            if not target_card:
                return
            self._node_panel_cache[cache_key] = target_card
            target_card.installEventFilter(self)
            target_card.closed.connect(self._close_card)

            if len(self._node_panel_cache) > self._max_cache_size:
                # 优化缓存剔除：绝不剔除全局变量
                for k in list(self._node_panel_cache.keys()):
                    if k != "GLOBAL_DASHBOARD":
                        c = self._node_panel_cache.pop(k)
                        if c in self._history_stack: self._history_stack.remove(c)
                        c.deleteLater()
                        break

        if target_card in self._history_stack:
            self._history_stack.remove(target_card)
        self._history_stack.append(target_card)

        # 修改淘汰逻辑：如果超过最大数量，只移除最早的“非全局变量”卡片
        normal_cards = [c for c in self._history_stack if getattr(c, '_node_ref', None) is not None]
        if len(normal_cards) > self._max_history:
            for i in range(len(self._history_stack)):
                candidate = self._history_stack[i]
                if getattr(candidate, '_node_ref', None) is not None:
                    self._history_stack.pop(i)
                    candidate.hide()
                    break

        self._refresh_card_content(target_card, node, cache_key)
        self.current_node = node if not isinstance(node, list) else None
        self._sync_stack_layout(animate=True)

    def _close_card(self, card):
        # 全局变量卡片（node_ref 为 None）禁止关闭逻辑
        if getattr(card, '_node_ref', None) is None:
            return

        if card not in self._history_stack:
            return

        is_active = (self._history_stack[-1] == card)
        self._history_stack.remove(card)
        card.hide()

        if is_active:
            if self._history_stack:
                next_card = self._history_stack[-1]
                self.update_properties(getattr(next_card, '_node_ref', None))
            else:
                self.update_properties(None)
        else:
            self._sync_stack_layout(animate=True)

    def _sync_stack_layout(self, animate=True):
        if self._is_resizing and animate:
            return
        if animate:
            self.anim_group.stop()
            self.anim_group.clear()

        self.stage.setUpdatesEnabled(False)
        w, h = self.stage.width(), self.stage.height()
        if w <= 10: w, h = self.width(), self.height()

        stack_count = len(self._history_stack)
        for i, card in enumerate(self._history_stack):
            card.show()
            if animate:
                card.raise_()

            level = (stack_count - 1) - i
            card.set_active(level == 0, level, animate=animate)
            target_y = i * self._header_reveal_h
            target_rect = QRect(0, target_y, w, h - target_y)

            if animate:
                anim = QPropertyAnimation(card, b"geometry")
                anim.setDuration(400)
                anim.setStartValue(card.geometry())
                anim.setEndValue(target_rect)
                curve = QEasingCurve.OutCubic if level == 0 else QEasingCurve.OutQuart
                anim.setEasingCurve(curve)
                self.anim_group.addAnimation(anim)
            else:
                card.setGeometry(target_rect)

        if animate and self.anim_group.animationCount() > 0:
            self.anim_group.start()

        self.stage.setUpdatesEnabled(True)

    def resizeEvent(self, event):
        self._is_resizing = True
        new_w = event.size().width()
        for card in self._history_stack:
            if card.isVisible():
                curr_geo = card.geometry()
                card.setGeometry(curr_geo.x(), curr_geo.y(), new_w, curr_geo.height())
        self._resize_timer.start(50)
        super().resizeEvent(event)

    def _on_resize_timeout(self):
        self._is_resizing = False
        self._sync_stack_layout(animate=False)

    def eventFilter(self, obj, event):
        if event.type() == event.MouseButtonPress:
            btn = obj.findChild(TransparentToolButton)
            if btn and obj.childAt(event.pos()) == btn:
                return False

            if obj in self._history_stack and self._history_stack[-1] != obj:
                if 0 <= event.pos().y() <= self._header_reveal_h:
                    self.update_properties(getattr(obj, '_node_ref', None))
                    return True
        return super().eventFilter(obj, event)

    def _create_card_widget(self, node, key):
        title, icon = self._get_metadata(node, key)
        card = FuturisticCard(self.stage, title=title, icon=icon)

        if key == "GLOBAL_DASHBOARD":
            # 优化点：去掉关闭按钮
            card.close_btn.hide()
            self.global_panel_widget = GlobalPanelWidget(self.main_window, self, card.content_layout)
            card._logic = self.global_panel_widget
            card._is_logic_class = True
        else:
            if key == "MULTI_LIST_VIEW":
                logic = NodeListPanelWidget(self.main_window, self, node)
            elif isinstance(node, ControlFlowBackdrop):
                logic = FlowControlPanelWidget(self.main_window, self, node)
            else:
                logic = NodePanelWidget(self.main_window, self, node)
            card.content_layout.addWidget(logic)
            card._logic = logic
            card._is_logic_class = False

        card._node_ref = node
        return card

    def _refresh_card_content(self, card, node, key):
        new_title, _ = self._get_metadata(node, key)
        card.set_title(new_title)

        if getattr(card, "_is_logic_class", False):
            card._logic.build_ui()
            self._global_panel_built = True
        else:
            if key == "MULTI_LIST_VIEW":
                self.node_list_panel_widget = card._logic
            elif isinstance(node, ControlFlowBackdrop):
                self.flow_control_panel_widget = card._logic
            else:
                self.node_panel_widget = card._logic

            if hasattr(card._logic, 'update_data'):
                card._logic.update_data(node)
            elif hasattr(card._logic, 'build_ui'):
                card._logic.build_ui(node)

    def _get_metadata(self, node, key):
        if key == "GLOBAL_DASHBOARD": return "全局变量", FluentIcon.GLOBE
        if key == "MULTI_LIST_VIEW": return f"连通图列表", FluentIcon.IOT
        if isinstance(node, ControlFlowBackdrop):
            return node.NODE_NAME, FluentIcon.SYNC
        return node.name(), getattr(node.view, "icon", FluentIcon.INFO)

    def set_scrollbar(self, widget):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setStyleSheet("background-color: transparent;")
        scroll.setStyleSheet("""
        QScrollArea { background-color: transparent; border: none; }
        QScrollBar:vertical { background: transparent; width: 6px; margin-right: 2px; }
        QScrollBar::handle:vertical { background: rgba(120, 120, 120, 150); border-radius: 4px; }
        QScrollBar::add-line, QScrollBar::sub-line { height: 0px; }
        """)
        scroll.setWidget(widget)
        return scroll

    def get_port_info(self, node, is_input=True):
        full_path = getattr(node, 'FULL_PATH', None)
        if full_path and hasattr(self.main_window, 'component_map'):
            comp_cls = self.main_window.component_map.get(full_path)
            if comp_cls:
                comp_ports = getattr(comp_cls, 'inputs' if is_input else 'outputs', [])
                return [(p.name, p.label, p.type.value) for p in comp_ports]
        try:
            if is_input:
                port_config = node.get_property("input_ports")
            else:
                port_config = node.get_property("output_ports")
            return [
                (port.get("name"), port.get("name"), port.get("type"))
                for port in port_config
            ]
        except:
            pass
        return [(p.name(), p.name(), ArgumentType.JSON.value) for p in
                (node.input_ports() if is_input else node.output_ports())]

    def get_node_description(self, node):
        if hasattr(node, 'description'):
            return node.description
        if not node or "StatusDynamicNode_" not in node.model.type_:
            return ""
        comp_cls = ComponentScanner().get_component_by_uuid(node.uuid)
        return comp_cls.description if comp_cls else ""

    def _on_global_variables_changed(self, var_type, var_name, action):
        if self.global_panel_widget:
            self.global_panel_widget.on_global_variables_changed(var_type, var_name, action)

    def _refresh_node_vars_page(self):
        if self.global_panel_widget:
            self.global_panel_widget._refresh_node_vars_page()

    def _copy_as_expression(self, prefix, var_name):
        if self.global_panel_widget:
            self.global_panel_widget.copy_as_expression(prefix, var_name)

    def _add_output_to_global_variable(self, node, port_name):
        self.global_panel_widget.add_output_to_global_var(self.main_window, node, port_name)

    def _delete_output_from_global_variable(self, node, port_name):
        if self.global_panel_widget:
            self.global_panel_widget.delete_output_from_global_var(self.main_window, node, port_name)

    def _is_output_in_global_variable(self, node, port_name):
        if not self._global_panel_built:
            self.update_properties(None)
        return self.global_panel_widget.is_output_in_global_var(self.main_window, node, port_name)

    def update_node_list_content(self):
        if self.node_list_panel_widget:
            self.node_list_panel_widget.update_node_list_content()

    def get_current_execution_order(self):
        return self.node_list_panel_widget.get_current_order() if self.node_list_panel_widget else []

    def reset_current_components(self):
        if self.node_list_panel_widget: self.node_list_panel_widget.reset_components()

    def set_allowed_update(self, allowed: bool):
        self._allowed_update = allowed

    def pop_node_layout(self, key):
        if key in self._node_panel_cache:
            self._node_panel_cache[key].closed.disconnect()
            self._close_card(self._node_panel_cache.pop(key))

    def _clear_node_layout(self):
        # 优化销毁逻辑，确保无内存残留，但保留全局变量卡片
        for key, card in list(self._node_panel_cache.items()):
            if key == "GLOBAL_DASHBOARD":
                continue
            card.closed.disconnect()
            card.deleteLater()
            self._node_panel_cache.pop(key)

        # history 只保留全局变量
        self._history_stack = [c for c in self._history_stack if getattr(c, '_node_ref', None) is None]