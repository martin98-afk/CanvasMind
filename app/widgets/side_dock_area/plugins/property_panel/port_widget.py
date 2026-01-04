# -*- coding: utf-8 -*-
import os
import re
import shutil
import traceback
from pathlib import Path
import pandas as pd
from PyQt5.QtCore import Qt, QSize, QTimer
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
    终极修复版：
    1. 修复：Tab 顺序错乱及状态丢失问题。
    2. 修复：切换节点后再切回时输出端口点击失效的问题。
    3. 优化：上传按钮移至卡片内部标题与树之间。
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

        self._input_cards = []
        self._output_cards = []
        self._text_edit_widgets = {}
        self.current_segment = None  # 记录当前选中的 Tab key

        self._setup_skeleton()
        self.refresh(node)

    def _setup_skeleton(self):
        """初始化 UI 框架"""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 1. 分段控件 (Tab)
        self.segmented_widget = SegmentedWidget(self)
        self.main_layout.addWidget(self.segmented_widget)

        # 2. 堆叠容器
        self.stacked_widget = QStackedWidget(self)

        # 准备输入页面
        self.input_page = QWidget()
        self.input_layout = QVBoxLayout(self.input_page)
        self.input_layout.setContentsMargins(10, 10, 10, 10)
        self.input_layout.setSpacing(8)
        self.input_scroll = self.parent_panel.set_scrollbar(self.input_page)

        # 准备输出页面
        self.output_page = QWidget()
        self.output_layout = QVBoxLayout(self.output_page)
        self.output_layout.setContentsMargins(10, 10, 10, 10)
        self.output_layout.setSpacing(8)
        self.output_scroll = self.parent_panel.set_scrollbar(self.output_page)

        self.stacked_widget.addWidget(self.input_scroll)
        self.stacked_widget.addWidget(self.output_scroll)
        self.main_layout.addWidget(self.stacked_widget)

        # 引用映射
        self.page_map = {
            'input': self.input_scroll,
            'output': self.output_scroll
        }

        self.segmented_widget.currentItemChanged.connect(self._on_segmented_changed)

    def _on_segmented_changed(self, item_key):
        """处理 Tab 切换并记录状态"""
        self.current_segment = item_key
        target_widget = self.page_map.get(item_key)
        if target_widget:
            self.stacked_widget.setCurrentWidget(target_widget)

    def _update_segments(self, has_in, has_out):
        """
        核心修复：
        1. 强制物理顺序：输入在前，输出在后。
        2. 状态记忆：重建后恢复之前的选中状态。
        """
        self.segmented_widget.blockSignals(True)

        # 彻底清空标签以保证物理顺序 (防止动态添加导致的乱序)
        # qfluentwidgets 的 SegmentedWidget 最好通过重新 add 来控制顺序
        try:
            # 这是一个强制清除法，确保界面重建
            for i in range(self.segmented_widget.count()):
                self.segmented_widget.removeWidget(self.segmented_widget.items[0])
            self.segmented_widget.items.clear()
        except:
            pass

        # 重新按固定顺序添加
        if has_in:
            self.segmented_widget.addItem('input', '输入端口')
        if has_out:
            self.segmented_widget.addItem('output', '输出端口')

        # 确定需要恢复的 Key
        target_key = self.current_segment
        if not target_key or (target_key == 'input' and not has_in) or (target_key == 'output' and not has_out):
            target_key = 'input' if has_in else ('output' if has_out else None)

        # 恢复选中并同步 StackedWidget (解决点不动的核心)
        if target_key:
            self.segmented_widget.setCurrentItem(target_key)
            self.stacked_widget.setCurrentWidget(self.page_map[target_key])
            self.current_segment = target_key

        self.segmented_widget.setVisible(has_in and has_out)
        self.segmented_widget.blockSignals(False)

    def refresh(self, node):
        """刷新入口"""
        self.node = node
        input_infos = self.port_info_func(node, is_input=True)
        output_infos = self.port_info_func(node, is_input=False)

        # 1. 刷新标签顺序及状态
        self._update_segments(len(input_infos) > 0, len(output_infos) > 0)

        # 2. 同步卡片内容 (增量更新)
        self._sync_port_cards(input_infos, self._input_cards, self.input_layout, is_output=False)
        self._sync_port_cards(output_infos, self._output_cards, self.output_layout, is_output=True)

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
        """创建卡片结构"""
        card = SimpleCardWidget(self)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        # 第一部分：标题
        t_lay = QHBoxLayout()
        title_label = CaptionLabel()
        title_label.setWordWrap(True)
        t_lay.addWidget(title_label, 1)

        btn_container = QHBoxLayout()
        t_lay.addLayout(btn_container)
        lay.addLayout(t_lay)
        lay.addWidget(CardSeparator(card))

        # 第二部分：新增 Action 区域 (用于放置上传按钮，介于标题和树之间)
        action_container = QVBoxLayout()
        action_container.setContentsMargins(0, 2, 0, 2)
        lay.addLayout(action_container)

        # 第三部分：变量树
        tree = VariableTreeWidget(parent=self.main_window)
        lay.addWidget(tree, 1)

        # 第四部分：额外组件区域 (如 CSV 选择器)
        extra_container = QVBoxLayout()
        lay.addLayout(extra_container)

        card.ui = {
            'title_label': title_label,
            'tree': tree,
            'btn_container': btn_container,
            'action_container': action_container,  # 上传按钮容器
            'extra_container': extra_container,
            'global_btn': None,
            'browse_btn': None
        }

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
        """刷新卡片业务数据"""
        ui = card.ui
        ui['title_label'].setText(f"• {p_label} ({p_name}): {p_type.value}")

        # 获取数据
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
            if isinstance(data, str) and Path(data).is_file() and data.endswith('.csv'):
                try:
                    data = pd.read_csv(data, nrows=5)
                except:
                    pass
            filtered_data = self._get_current_input_value(p_name, data)

        ui['tree'].set_data(filtered_data, p_name)
        self._text_edit_widgets[p_name] = ui['tree']

        # 绑定放大镜
        try:
            ui['browse_btn'].clicked.disconnect()
        except:
            pass
        ui['browse_btn'].clicked.connect(lambda: self._show_detail_popup(filtered_data, p_label, ui['browse_btn']))

        # 全局变量按钮
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

        # === 核心优化：在卡片内渲染上传按钮 (介于名和树之间) ===
        self._refresh_card_actions(card, p_name, p_label, p_type, is_output)

        # 刷新 Extra 区域 (CSV)
        self._refresh_extra_area(card, p_name, p_type, data, is_output)

    def _refresh_card_actions(self, card, p_name, p_label, p_type, is_output):
        """刷新卡片内的操作按钮 (上传按钮)"""
        container = card.ui['action_container']
        # 清理旧按钮
        while container.count():
            item = container.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        # 如果是上传类型且为输出端口，显示上传按钮
        if p_type == ArgumentType.UPLOAD and is_output:
            upload_btn = PushButton(FluentIcon.UP, f"上传文件到 {p_label}", self)
            upload_btn.setFixedHeight(30)
            upload_btn.clicked.connect(lambda: self._select_upload_file(p_name))
            container.addWidget(upload_btn)

    def _show_detail_popup(self, data, label, btn):
        popup = VariableDetailPopup(parent=self)
        popup.set_data(data, name=f"{label} 详情")
        popup.show_at_left_of(btn)

    def _refresh_extra_area(self, card, p_name, p_type, data, is_output):
        container = card.ui['extra_container']
        while container.count():
            item = container.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        if p_type == ArgumentType.CSV and not is_output:
            if isinstance(data, pd.DataFrame) and not data.empty:
                self._add_column_selector_widget_to_layout(p_name, data, container)

    def _add_column_selector_widget_to_layout(self, port_name, data, layout):
        if not isinstance(data, pd.DataFrame) or data.empty: return
        columns = list(data.columns)
        if not columns: return

        column_card = CardWidget(self)
        column_card.setFixedHeight(200)

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

    def _select_upload_file(self, port_name):
        """
        处理文件选择并上传。
        即使文件已存在，依然将路径同步到输出中。
        """
        curr = self.node._output_values.get(port_name, "")
        file_path, _ = QFileDialog.getOpenFileName(
            self, "上传文件", os.path.dirname(curr) if curr else "", "All Files (*)"
        )
        if not file_path:
            return

        src = Path(file_path)
        # 确保工作流上传目录存在
        upload_root = canvas_file_dump_path() / "workflows" / self.main_window.workflow_name / "uploads" / self.node.persistent_id
        upload_root.mkdir(exist_ok=True, parents=True)

        # 清理文件名并构建目标路径
        pattern = r'[^\w\.-]'
        dst = upload_root / f"{re.sub(pattern, '_', src.stem)}{src.suffix}"

        try:
            # 如果目标文件已存在且不是同一文件，copy2 会默认覆盖
            # 如果 src 和 dst 是同一个文件，会抛出 SameFileError
            shutil.copy2(src, dst)
        except shutil.SameFileError:
            # 如果是同一个文件，无需操作，视为成功
            pass
        except Exception as e:
            # 只有真正的 IO 报错（如权限拒绝、磁盘满）才拦截
            logger.error(f"文件上传过程中发生实质性错误: {traceback.format_exc()}")
            InfoBar.error("上传失败", f"无法处理文件: {str(e)}", parent=self.main_window)
            return

        # --- 关键修改：只要没发生实质性报错，就更新输出值 ---
        self.node._output_values[port_name] = str(dst)

        # 提示用户
        InfoBar.success("文件已就绪", f"路径已同步: {dst.name}", parent=self.main_window, duration=2000)

        # 实时同步更新属性面板里的预览树
        if port_name in self._text_edit_widgets:
            widget = self._text_edit_widgets[port_name]
            if hasattr(widget, 'set_data'):
                widget.set_data(str(dst), port_name)

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