# -*- coding: utf-8 -*-
import os
import re
import shutil
import traceback
from pathlib import Path
import pandas as pd
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QListWidgetItem, QWidget, QFileDialog, QStackedWidget
from loguru import logger
from qfluentwidgets import (CardWidget, PushButton, ListWidget, SegmentedWidget,
                            FluentIcon, InfoBar, TransparentToolButton, RoundMenu, Action,
                            CaptionLabel, ToggleToolButton, SmoothScrollArea, BodyLabel)
from qfluentwidgets.components.widgets.card_widget import CardSeparator, SimpleCardWidget

from app.components.base import ArgumentType
from app.utils.utils import get_icon, canvas_file_dump_path
from app.widgets.side_dock_area.plugins.property_panel.variable_tree import VariableTreeWidget, VariableDetailPopup


class PortWidget(QWidget):
    """
    完全修复版：支持控件复用、CSV列选择、文件上传。
    """

    def __init__(self, main_window, parent_panel, node, port_info_func,
                 copy_as_expression_func, add_func, delete_func, is_in_func, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.parent_panel = parent_panel
        self.node = node
        self.port_info_func = port_info_func
        self.copy_as_expression_func = copy_as_expression_func
        self.add_output_to_global_func = add_func
        self.delete_output_from_global_func = delete_func
        self.is_in_global_func = is_in_func

        # --- 控件池与缓存 ---
        self._input_cards = []
        self._output_cards = []
        self._text_edit_widgets = {}
        self._added_keys = set()  # 记录 SegmentedWidget 已添加的项

        self._setup_skeleton()
        self.refresh(node)

    def _setup_skeleton(self):
        """初始化 UI 框架"""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.segmented_widget = SegmentedWidget(self)
        self.main_layout.addWidget(self.segmented_widget)

        self.stacked_widget = QStackedWidget(self)

        # 输入页
        self.input_page = QWidget()
        self.input_layout = QVBoxLayout(self.input_page)
        self.input_layout.setContentsMargins(10, 10, 10, 10)
        self.input_layout.setSpacing(8)
        self.input_scroll = self.parent_panel.set_scrollbar(self.input_page)

        # 输出页
        self.output_page = QWidget()
        self.output_layout = QVBoxLayout(self.output_page)
        self.output_layout.setContentsMargins(10, 10, 10, 10)
        self.output_layout.setSpacing(8)
        self.output_scroll = self.parent_panel.set_scrollbar(self.output_page)

        self.stacked_widget.addWidget(self.input_scroll)
        self.stacked_widget.addWidget(self.output_scroll)
        self.main_layout.addWidget(self.stacked_widget)

        self.segmented_widget.currentItemChanged.connect(self._on_segmented_changed)

    def _on_segmented_changed(self, item_key):
        idx = 0 if item_key == 'input' else 1
        self.stacked_widget.setCurrentIndex(idx)

    def refresh(self, node):
        """增量刷新端口数据"""
        self.node = node
        if not hasattr(self.node, '_input_values'): self.node._input_values = {}
        if not hasattr(self.node, 'column_select'): self.node.column_select = {}

        input_infos = self.port_info_func(node, is_input=True)
        output_infos = self.port_info_func(node, is_input=False)

        self._update_segments(len(input_infos) > 0, len(output_infos) > 0)
        self._sync_port_cards(input_infos, self._input_cards, self.input_layout, is_output=False)
        self._sync_port_cards(output_infos, self._output_cards, self.output_layout, is_output=True)

    def _update_segments(self, has_in, has_out):
        self.segmented_widget.blockSignals(True)
        if has_in and 'input' not in self._added_keys:
            self.segmented_widget.addItem('input', '输入端口')
            self._added_keys.add('input')
        if has_out and 'output' not in self._added_keys:
            self.segmented_widget.addItem('output', '输出端口')
            self._added_keys.add('output')

        if not self.segmented_widget.currentRouteKey():
            if has_in:
                self.segmented_widget.setCurrentItem('input')
            elif has_out:
                self.segmented_widget.setCurrentItem('output')
        self.segmented_widget.blockSignals(False)

    def _sync_port_cards(self, port_infos, card_cache, layout, is_output):
        for i in range(max(len(port_infos), len(card_cache))):
            if i < len(port_infos):
                p_name, p_label, p_type = port_infos[i]
                if i < len(card_cache):
                    card = card_cache[i]
                    card.show()
                else:
                    card = self._create_port_card(is_output)
                    card_cache.append(card)
                    layout.insertWidget(layout.count(), card)
                self._update_card_data(card, p_name, p_label, p_type, is_output)
            elif i < len(card_cache):
                card_cache[i].hide()

    def _create_port_card(self, is_output):
        card = SimpleCardWidget(self)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(8, 8, 8, 8)

        t_lay = QHBoxLayout()
        title_label = CaptionLabel()
        title_label.setWordWrap(True)
        t_lay.addWidget(title_label, 1)

        btn_container = QHBoxLayout()
        t_lay.addLayout(btn_container)
        lay.addLayout(t_lay)
        lay.addWidget(CardSeparator(card))

        tree = VariableTreeWidget(parent=self.main_window)
        lay.addWidget(tree, 1)

        extra_container = QVBoxLayout()
        lay.addLayout(extra_container)

        card.ui = {'title_label': title_label, 'tree': tree, 'btn_container': btn_container,
                   'extra_container': extra_container, 'global_btn': None, 'browse_btn': None}

        browse_btn = TransparentToolButton(icon=get_icon("放大"), parent=card)
        browse_btn.setFixedSize(QSize(26, 20))
        card.ui['btn_container'].addWidget(browse_btn)
        card.ui['browse_btn'] = browse_btn

        if is_output:
            gb = ToggleToolButton(icon=get_icon("Global"), parent=card)
            gb.setFixedSize(QSize(26, 26))
            card.ui['btn_container'].insertWidget(0, gb)
            card.ui['global_btn'] = gb
            card.setContextMenuPolicy(Qt.CustomContextMenu)
        return card

    def _update_card_data(self, card, p_name, p_label, p_type, is_output):
        ui = card.ui
        ui['title_label'].setText(f"• {p_label} ({p_name}): {p_type.value}")

        data = "暂无数据"
        if is_output:
            data = getattr(self.node, '_output_values', {}).get(p_name)
            if data is None:
                try:
                    data = self.node.model.get_property(p_name)
                except:
                    data = "暂无数据"
        else:
            input_port = self.node.get_input(p_name)
            connected = input_port.connected_ports() if input_port else []
            if len(connected) == 1:
                upstream = connected[0]
                data = upstream.node().get_output_value(upstream.name())
            elif connected:
                data = [up.node().get_output_value(up.name()) for up in connected]

        filtered_data = data
        if not is_output and p_type == ArgumentType.CSV:
            # 处理 CSV 字符串路径转 DataFrame
            if isinstance(data, str) and Path(data).is_file() and data.endswith('.csv'):
                try:
                    data = pd.read_csv(data, nrows=5)
                except:
                    pass
            filtered_data = self._get_current_input_value(p_name, data)

        ui['tree'].set_data(filtered_data, p_name)
        self._text_edit_widgets[p_name] = ui['tree']

        try:
            ui['browse_btn'].clicked.disconnect()
        except:
            pass
        ui['browse_btn'].clicked.connect(lambda: self._show_detail_popup(filtered_data, p_label, ui['browse_btn']))

        if is_output and ui['global_btn']:
            ui['global_btn'].blockSignals(True)
            ui['global_btn'].setChecked(self.is_in_global_func(self.node, p_name))
            ui['global_btn'].blockSignals(False)
            try:
                ui['global_btn'].clicked.disconnect()
            except:
                pass
            ui['global_btn'].clicked.connect(
                lambda: self.handle_global_variable(self.node, p_name, ui['global_btn'].isChecked()))
            try:
                card.customContextMenuRequested.disconnect()
            except:
                pass
            card.customContextMenuRequested.connect(lambda pos: self._show_context_menu(card, p_name, pos))

        self._refresh_extra_area(card, p_name, p_type, data, is_output)

    def _show_detail_popup(self, data, label, btn):
        popup = VariableDetailPopup(parent=self)
        popup.set_data(data, name=f"{label} 详情")
        popup.show_at_left_of(btn)

    def _refresh_extra_area(self, card, p_name, p_type, data, is_output):
        container = card.ui['extra_container']
        while container.count():
            item = container.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        if p_type == ArgumentType.UPLOAD and is_output:
            self._add_upload_widget_to_layout(p_name, container)
        elif p_type == ArgumentType.CSV and not is_output:
            if isinstance(data, pd.DataFrame) and not data.empty:
                self._add_column_selector_widget_to_layout(p_name, data, container)

    # ========================
    # 核心：修复缺失的 CSV 列选择逻辑
    # ========================
    def _add_column_selector_widget_to_layout(self, port_name, data, layout):
        if not isinstance(data, pd.DataFrame) or data.empty: return
        columns = list(data.columns)
        if not columns: return

        column_card = CardWidget(self)
        column_card.setMaximumHeight(200)
        column_card.setMinimumHeight(200)

        node_id = self.node.id
        port_identifier = f"{node_id}_{port_name}"
        if not hasattr(self.parent_panel, '_column_selector_card_expanded'):
            self.parent_panel._column_selector_card_expanded = {}
        self.parent_panel._column_selector_card_expanded.setdefault(port_identifier, False)

        card_layout = QVBoxLayout(column_card)
        card_layout.setContentsMargins(4, 4, 4, 4)
        card_layout.setSpacing(0)

        title_btn_layout = QHBoxLayout()
        title_btn_layout.addWidget(BodyLabel("   CSV列选择:"))
        title_btn_layout.addStretch()

        # 全选/清空
        def select_all():
            list_widget.blockSignals(True)
            for i in range(list_widget.count()): list_widget.item(i).setCheckState(Qt.Checked)
            list_widget.blockSignals(False)
            _on_selection_changed()

        def clear_all():
            list_widget.blockSignals(True)
            for i in range(list_widget.count()): list_widget.item(i).setCheckState(Qt.Unchecked)
            list_widget.blockSignals(False)
            _on_selection_changed()

        def toggle_expand():
            is_exp = not self.parent_panel._column_selector_card_expanded[port_identifier]
            self.parent_panel._column_selector_card_expanded[port_identifier] = is_exp
            if is_exp:
                h = list_widget.count() * 40 + 50
                column_card.setFixedHeight(min(h, 600))
                expand_btn.setIcon(get_icon("缩小"))
            else:
                column_card.setFixedHeight(200)
                expand_btn.setIcon(get_icon("放大"))

        select_all_btn = TransparentToolButton(icon=get_icon("全选"), parent=self)
        clear_btn = TransparentToolButton(icon=get_icon("取消选择"), parent=self)
        expand_btn = TransparentToolButton(icon=get_icon("放大"), parent=self)

        select_all_btn.clicked.connect(select_all)
        clear_btn.clicked.connect(clear_all)
        expand_btn.clicked.connect(toggle_expand)

        for b in [select_all_btn, clear_btn, expand_btn]: title_btn_layout.addWidget(b)
        card_layout.addLayout(title_btn_layout)

        list_widget = ListWidget(self)
        for col in columns:
            item = QListWidgetItem(col)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            # 恢复之前的勾选状态
            saved = self.node.column_select.get(port_name, columns)
            item.setCheckState(Qt.Checked if col in saved else Qt.Unchecked)
            list_widget.addItem(item)

        def _on_selection_changed():
            selected = [list_widget.item(i).text() for i in range(list_widget.count())
                        if list_widget.item(i).checkState() == Qt.Checked]
            self.node.column_select[port_name] = selected
            if port_name in self._text_edit_widgets:
                self._text_edit_widgets[port_name].set_data(data[selected] if selected else pd.DataFrame(), port_name)

        list_widget.itemChanged.connect(_on_selection_changed)
        card_layout.addWidget(list_widget)
        layout.addWidget(column_card)

    def _get_current_input_value(self, port_name, original_data):
        selected_columns = self.node.column_select.get(port_name, [])
        if selected_columns and isinstance(original_data, pd.DataFrame):
            try:
                return original_data[selected_columns] if len(selected_columns) > 1 else original_data[
                    selected_columns[0]]
            except:
                return original_data
        return original_data

    def _add_upload_widget_to_layout(self, port_name, layout):
        btn = PushButton("📁 上传文件", self)
        btn.clicked.connect(lambda: self._select_upload_file(port_name))
        layout.addWidget(btn)

    def _select_upload_file(self, port_name):
        curr = self.node._output_values.get(port_name, "")
        file_path, _ = QFileDialog.getOpenFileName(self, "上传文件", os.path.dirname(curr) if curr else "",
                                                   "All Files (*)")
        if not file_path: return

        src = Path(file_path)
        upload_root = canvas_file_dump_path() / "workflows" / self.main_window.workflow_name / "uploads" / self.node.persistent_id
        upload_root.mkdir(exist_ok=True, parents=True)
        pattern = r'[^\w\.-]'
        dst = upload_root / f"{re.sub(pattern, '_', src.stem)}{src.suffix}"

        try:
            shutil.copy2(src, dst)
            self.node._output_values[port_name] = str(dst)
            InfoBar.success("上传成功", f"保存至：{dst.name}", parent=self.main_window)
            if port_name in self._text_edit_widgets:
                self._text_edit_widgets[port_name].set_data(str(dst), port_name)
        except Exception as e:
            InfoBar.error("上传失败", str(e), parent=self.main_window)

    def handle_global_variable(self, node, port_name, is_checked):
        if is_checked:
            self.add_output_to_global_func(node, port_name)
        else:
            self.delete_output_from_global_func(node, port_name)

    def _show_context_menu(self, card, p_name, pos):
        menu = RoundMenu(parent=self)
        menu.addAction(Action(FluentIcon.COPY, "复制为表达式", triggered=lambda:
        self.copy_as_expression_func("node_vars", f"{self.node.name()}__{p_name}")))
        menu.exec_(card.mapToGlobal(pos))