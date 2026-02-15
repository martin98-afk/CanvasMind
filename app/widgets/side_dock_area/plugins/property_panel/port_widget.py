# -*- coding: utf-8 -*-
import orjson
import pandas as pd
import os
import re
import shutil
import traceback
from pathlib import Path
from PyQt5.QtCore import Qt, QSize, QThread, pyqtSignal, QObject, QPoint
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QListWidgetItem, QWidget, QFileDialog, QStackedWidget
from loguru import logger
from qfluentwidgets import (CardWidget, PushButton, ListWidget, SegmentedWidget,
                            FluentIcon, InfoBar, TransparentToolButton, RoundMenu, Action,
                            CaptionLabel, ToggleToolButton, BodyLabel, ProgressBar)
from qfluentwidgets.components.widgets.card_widget import CardSeparator, SimpleCardWidget

from app.components.base import ArgumentType
from app.utils.utils import get_icon
from app.widgets.side_dock_area.plugins.property_panel.variable_tree import VariableTreeWidget, VariableDetailPopup


# =================================================================
# 异步任务处理类：负责在后台执行耗时的文件复制操作
# =================================================================
class FileCopyWorker(QObject):
    """支持进度反馈的文件复制执行器"""
    progress = pyqtSignal(int)  # 进度百分比 (0-100)
    finished = pyqtSignal(bool, str, str)  # 成功标志, 目标路径, 错误信息

    def __init__(self, src: Path, dst: Path):
        super().__init__()
        self.src = src
        self.dst = dst
        self.buffer_size = 1024 * 512  # 512KB 缓冲区，让进度条滑动更丝滑

    def run(self):
        try:
            # 基础检查
            if not self.src.exists():
                self.finished.emit(False, "", "源文件不存在")
                return

            if self.src.resolve() == self.dst.resolve():
                self.progress.emit(100)
                self.finished.emit(True, str(self.dst), "")
                return

            total_size = self.src.stat().st_size
            if total_size == 0:
                # 处理空文件
                shutil.copy2(self.src, self.dst)
                self.progress.emit(100)
                self.finished.emit(True, str(self.dst), "")
                return

            copied_size = 0
            # 开始流式拷贝
            with open(self.src, 'rb') as fsrc:
                with open(self.dst, 'wb') as fdst:
                    while True:
                        buf = fsrc.read(self.buffer_size)
                        if not buf:
                            break
                        fdst.write(buf)
                        copied_size += len(buf)

                        # 计算百分比
                        percentage = int((copied_size / total_size) * 100)
                        self.progress.emit(percentage)

            # 复制元数据
            shutil.copystat(self.src, self.dst)
            self.finished.emit(True, str(self.dst), "")

        except Exception as e:
            logger.error(f"复制异常: {traceback.format_exc()}")
            self.finished.emit(False, "", str(e))


# =================================================================
# 主 UI 组件
# =================================================================
class PortWidget(QWidget):
    """
    终极优化版：
    1. 异步处理：文件上传不再卡顿 UI。
    2. 状态保护：任务期间禁用交互，完成后自动恢复。
    3. 资源管理：自动清理后台线程。
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

        # 线程池管理，防止 Worker 被提前垃圾回收
        self._active_threads = []
        self._input_cards = []
        self._output_cards = []
        self._text_edit_widgets = {}
        self.current_segment = None

        self._setup_skeleton()
        self.refresh(node)

    def _setup_skeleton(self):
        """构建 UI 基础框架"""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Tab 控制栏
        self.segmented_widget = SegmentedWidget(self)
        self.main_layout.addWidget(self.segmented_widget)

        # 页面容器
        self.stacked_widget = QStackedWidget(self)

        # 输入/输出滚动区域
        self.input_page = QWidget()
        self.input_layout = QVBoxLayout(self.input_page)
        self.input_layout.setContentsMargins(10, 10, 10, 10)
        self.input_layout.setSpacing(8)
        self.input_scroll = self.parent_panel.set_scrollbar(self.input_page)

        self.output_page = QWidget()
        self.output_layout = QVBoxLayout(self.output_page)
        self.output_layout.setContentsMargins(10, 10, 10, 10)
        self.output_layout.setSpacing(8)
        self.output_scroll = self.parent_panel.set_scrollbar(self.output_page)

        self.stacked_widget.addWidget(self.input_scroll)
        self.stacked_widget.addWidget(self.output_scroll)
        self.main_layout.addWidget(self.stacked_widget)

        self.page_map = {'input': self.input_scroll, 'output': self.output_scroll}
        self.segmented_widget.currentItemChanged.connect(self._on_segmented_changed)

    def _update_segments(self, has_in, has_out):
        """按需重建或切换 Tab，修复点击失效问题"""
        expected_keys = []
        if has_in: expected_keys.append('input')
        if has_out: expected_keys.append('output')

        current_keys = list(self.segmented_widget.items.keys())
        if current_keys != expected_keys:
            self.segmented_widget.blockSignals(True)
            for key in current_keys:
                self.segmented_widget.removeWidget(key)
            if has_in: self.segmented_widget.addItem('input', '输入端口')
            if has_out: self.segmented_widget.addItem('output', '输出端口')
            self.segmented_widget.blockSignals(False)

        target_key = self.current_segment if self.current_segment in expected_keys else (
            expected_keys[0] if expected_keys else None)

        if target_key:
            self.segmented_widget.blockSignals(True)
            self.segmented_widget.setCurrentItem(target_key)
            self.segmented_widget.blockSignals(False)
            self.current_segment = target_key
            self.stacked_widget.setCurrentWidget(self.page_map.get(target_key))

        self.segmented_widget.setVisible(has_in and has_out)

    def _on_segmented_changed(self, item_key):
        if not item_key: return
        self.current_segment = item_key
        self.stacked_widget.setCurrentWidget(self.page_map.get(item_key))

    def refresh(self, node):
        """刷新入口，由外部节点切换触发"""
        self.node = node
        input_infos = self.port_info_func(node, is_input=True) if hasattr(node, "input_ports") else []
        output_infos = self.port_info_func(node, is_input=False) if hasattr(node, "input_ports") else []

        self._update_segments(len(input_infos) > 0, len(output_infos) > 0)
        self._sync_port_cards(input_infos, self._input_cards, self.input_layout, is_output=False)
        self._sync_port_cards(output_infos, self._output_cards, self.output_layout, is_output=True)

    def _sync_port_cards(self, port_infos, card_cache, layout, is_output):
        """增量刷新卡片"""
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
        lay.setSpacing(4)

        t_lay = QHBoxLayout()
        title_label = CaptionLabel()
        title_label.setWordWrap(True)
        t_lay.addWidget(title_label, 1)
        btn_container = QHBoxLayout()
        t_lay.addLayout(btn_container)
        lay.addLayout(t_lay)
        lay.addWidget(CardSeparator(card))

        action_container = QVBoxLayout()
        action_container.setContentsMargins(0, 2, 0, 2)
        lay.addLayout(action_container)

        # 进度条占位 (默认隐藏)
        progress_bar = ProgressBar(card)
        progress_bar.setFixedHeight(4)
        progress_bar.hide()
        action_container.addWidget(progress_bar)

        tree = VariableTreeWidget(parent=self.main_window)
        lay.addWidget(tree, 1)

        extra_container = QVBoxLayout()
        lay.addLayout(extra_container)

        card.ui = {
            'title_label': title_label, 'tree': tree, 'btn_container': btn_container,
            'action_container': action_container, 'extra_container': extra_container,
            'progress_bar': progress_bar, # 记录进度条引用
            'global_btn': None, 'browse_btn': None
        }
        selector_btn = ToggleToolButton(FluentIcon.FILTER, card)
        selector_btn.setFixedSize(QSize(26, 20))
        selector_btn.setToolTip("显示/隐藏数据选择器")
        selector_btn.setChecked(False)
        selector_btn.hide()  # 默认隐藏
        card.ui['selector_btn'] = selector_btn
        card.ui['btn_container'].addWidget(selector_btn)  # 先添加，后续根据类型决定位置

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
        """填充/更新卡片业务数据"""
        ui = card.ui
        ui['title_label'].setText(f"• {p_label} ({p_name}): {p_type}")

        # 获取数据逻辑
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

        # ===== 新增：判断是否支持数据选择器 =====
        supports_selector = not is_output and p_type in [
            ArgumentType.CSV,
            ArgumentType.ARRAY,
            ArgumentType.JSON
        ]
        # =======================================

        # CSV 轻量预览处理（仅用于选择器内部，不影响主数据显示）
        raw_data_for_selector = data
        if supports_selector and p_type == ArgumentType.CSV:
            if isinstance(data, str) and data.lower().endswith('.csv'):
                try:
                    if os.path.exists(data):
                        raw_data_for_selector = pd.read_csv(data, nrows=100)  # 读取更多行供选择
                except:
                    pass

        # ===== 核心逻辑：根据选择器可见状态决定显示的数据 =====
        selector_visible = self._get_selector_visible(p_name) if supports_selector else False

        if supports_selector:
            # 显示选择器按钮
            ui['selector_btn'].show()
            ui['selector_btn'].blockSignals(True)
            ui['selector_btn'].setChecked(selector_visible)
            ui['selector_btn'].blockSignals(False)

            # 重新连接信号（防止重复连接）
            try:
                ui['selector_btn'].clicked.disconnect()
            except:
                pass
            ui['selector_btn'].clicked.connect(
                lambda checked, pn=p_name: self._toggle_selector(pn, checked)
            )

            # 决定显示给用户的数据：
            # - 选择器可见：显示过滤后的数据（应用_data_select）
            # - 选择器隐藏：显示原始全部数据（忽略过滤配置）
            display_data = self._get_current_input_value(p_name,
                                                         raw_data_for_selector) if selector_visible else raw_data_for_selector
        else:
            # 不支持选择器：隐藏按钮，显示原始数据
            if ui['selector_btn']:
                ui['selector_btn'].hide()
            display_data = data
        # =========================================================

        ui['tree'].set_data(display_data, p_name)
        self._text_edit_widgets[p_name] = ui['tree']

        # 重新绑定按钮信号 (防止闭包引用旧数据)
        try:
            ui['browse_btn'].clicked.disconnect()
        except:
            pass
        ui['browse_btn'].clicked.connect(lambda: self._show_detail_popup(display_data, p_label, ui['browse_btn']))

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

        self._refresh_card_actions(card, p_name, p_label, p_type, is_output)
        # 传递 selector_visible 状态给 extra_area
        self._refresh_extra_area(card, p_name, p_type, raw_data_for_selector, is_output, selector_visible)

    def _toggle_selector(self, port_name, visible):
        """切换数据选择器可见状态"""
        self._set_selector_visible(port_name, visible)
        # 只刷新当前节点，避免全局刷新导致闪烁
        self.refresh(self.node)

    def _refresh_card_actions(self, card, p_name, p_label, p_type, is_output):
        container = card.ui['action_container']
        for i in reversed(range(container.count())):
            item = container.itemAt(i)
            widget = item.widget()
            if widget and widget != card.ui['progress_bar']:
                widget.deleteLater()

        if p_type == ArgumentType.UPLOAD and is_output:
            # 创建水平布局容纳两个按钮
            h_layout = QHBoxLayout()
            h_layout.setSpacing(4)

            upload_btn = PushButton(FluentIcon.UP, f"上传文件到 {p_label}", self)
            upload_btn.setFixedHeight(30)
            upload_btn.clicked.connect(lambda: self._select_upload_file(p_name, upload_btn, card.ui['progress_bar']))

            # 历史按钮
            history_btn = TransparentToolButton(FluentIcon.HISTORY, self)
            history_btn.setFixedSize(30, 30)
            history_btn.setToolTip("历史上传记录")
            history_btn.clicked.connect(lambda: self._show_history_menu(p_name, history_btn))

            h_layout.addWidget(upload_btn, 1)
            h_layout.addWidget(history_btn)

            # 将水平布局添加到主容器（需要先包一层 QWidget 或直接添加布局）
            btn_group_widget = QWidget()
            btn_group_widget.setLayout(h_layout)
            container.addWidget(btn_group_widget)

    def _show_history_menu(self, port_name, btn):
        history = self._get_history()
        if not history:
            InfoBar.warning("提示", "暂无历史记录", parent=self.main_window, duration=1500)
            return

        menu = RoundMenu(parent=self)
        for path in history:
            file_name = os.path.basename(path)
            action = Action(FluentIcon.DOCUMENT, file_name, self)
            action.setToolTip(path)
            action.triggered.connect(lambda checked, p=path: self._apply_history_selection(port_name, p))
            menu.addAction(action)

        # --- 核心修改部分 ---
        # 1. 获取菜单建议的尺寸
        menu_width = menu.sizeHint().width()
        # 2. 计算偏移量：x = 按钮宽 - 菜单宽， y = 按钮高
        # 这样菜单的右边缘就会和按钮的右边缘重合
        offset_x = btn.width() - menu_width
        offset_y = btn.height()

        # 3. 映射到全局坐标并显示
        pos = btn.mapToGlobal(QPoint(offset_x, offset_y))
        menu.exec_(pos)

    def _get_selector_visible(self, port_name):
        """获取端口数据选择器的可见状态（默认不显示）"""
        visible_map = self.node.get_property("_data_selector_visible") or {}
        return visible_map.get(port_name, False)

    def _set_selector_visible(self, port_name, visible):
        """设置并持久化端口数据选择器的可见状态"""
        visible_map = self.node.get_property("_data_selector_visible") or {}
        visible_map[port_name] = visible
        self.node.set_property("_data_selector_visible", visible_map)

    def _apply_history_selection(self, port_name, file_path):
        """将历史记录中的文件应用到节点，自动清理无效记录"""
        if not os.path.exists(file_path):
            # 自动清理无效历史记录
            self._remove_from_history(file_path)
            InfoBar.warning(
                title="历史记录已更新",
                content=f"「{os.path.basename(file_path)}」\n文件不存在，已自动从历史中移除",
                parent=self.main_window,
                duration=2500
            )
            return  # 直接返回，不执行后续操作

        # 原有正常处理逻辑
        self.node.set_output_value(port_name, file_path)
        try:
            self.node.model.add_property(f"{port_name}_upload", file_path)
        except:
            self.node.model.set_property(f"{port_name}_upload", file_path)

        if port_name in self._text_edit_widgets:
            self._text_edit_widgets[port_name].set_data(file_path, port_name)

        InfoBar.success(
            "已选择",
            f"已切换至: {os.path.basename(file_path)}",
            parent=self.main_window,
            duration=2000
        )

    # =================================================================
    # 核心优化：异步文件选择与处理
    # =================================================================
    def _select_upload_file(self, port_name, btn, progress_bar):
        curr = self.node._output_values.get(port_name, "")
        file_path, _ = QFileDialog.getOpenFileName(
            self, "上传文件", os.path.dirname(curr) if curr else "", "All Files (*)"
        )
        if not file_path: return

        src = Path(file_path)
        workspace = getattr(self.main_window, 'file_path', Path(".")).parent / "workspace"
        upload_root = workspace / self.node.persistent_id / "upload"
        upload_root.mkdir(exist_ok=True, parents=True)

        pattern = r'[^\w\.-]'
        dst = upload_root / f"{re.sub(pattern, '_', src.stem)}{src.suffix}"

        # 1. UI 准备
        btn.setEnabled(False)
        progress_bar.setValue(0)
        progress_bar.show()

        # 2. 线程与 Worker 配置 (重点修复)
        thread = QThread(self)
        worker = FileCopyWorker(src, dst)
        worker.moveToThread(thread)

        # 将 worker 显式绑定到 thread 上，防止被垃圾回收
        thread.worker = worker

        # 3. 关联信号
        worker.progress.connect(progress_bar.setValue)

        def on_upload_finished(success, final_path, error_msg):
            progress_bar.hide()
            btn.setEnabled(True)

            if success:
                self.node.set_output_value(port_name, final_path)
                self._add_to_history(final_path)
                try:
                    self.node.model.add_property(f"{port_name}_upload", final_path)
                except:
                    self.node.model.set_property(f"{port_name}_upload", final_path)
                InfoBar.success("完成", f"{src.name} 上传成功", parent=self.main_window, duration=2000)
                if port_name in self._text_edit_widgets:
                    self._text_edit_widgets[port_name].set_data(final_path, port_name)
            else:
                InfoBar.error("上传失败", f"错误: {error_msg}", parent=self.main_window)

            # 4. 彻底销毁线程和对象
            thread.quit()
            thread.wait()
            if thread in self._active_threads:
                self._active_threads.remove(thread)
            worker.deleteLater()
            thread.deleteLater()

        worker.finished.connect(on_upload_finished)
        thread.started.connect(worker.run)

        # 记录线程引用
        self._active_threads.append(thread)
        thread.start()

    def _show_detail_popup(self, data, label, btn):
        popup = VariableDetailPopup(parent=self)
        popup.set_data(data, name=f"{label} 详情")
        popup.show_at_left_of(btn)

    def _refresh_extra_area(self, card, p_name, p_type, data, is_output, selector_visible=False):
        """智能刷新额外区域：根据数据类型和选择器可见状态动态显示"""
        container = card.ui['extra_container']
        while container.count():
            item = container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not selector_visible or is_output:
            return  # 不显示任何选择器

        # 根据数据类型添加对应的选择器
        if isinstance(data, pd.DataFrame) and not data.empty:
            self._add_column_selector_widget_to_layout(p_name, data, container)
        elif isinstance(data, (list, tuple)) and len(data) > 0:
            self._add_list_selector_widget_to_layout(p_name, data, container)
        elif isinstance(data, dict) and len(data) > 0:
            self._add_dict_selector_widget_to_layout(p_name, data, container)

    def _add_column_selector_widget_to_layout(self, port_name, data, layout):
        """CSV列选择器 - 统一使用 _data_select"""
        if not isinstance(data, pd.DataFrame) or data.empty:
            return

        columns = list(data.columns)
        column_card = CardWidget(self)
        column_card.setFixedHeight(200)

        port_id = f"{self.node.id}_{port_name}_csv"
        if not hasattr(self.parent_panel, '_selector_expanded'):
            self.parent_panel._selector_expanded = {}
        self.parent_panel._selector_expanded.setdefault(port_id, False)

        card_layout = QVBoxLayout(column_card)
        card_layout.setContentsMargins(4, 4, 4, 4)
        card_layout.setSpacing(0)

        title_lay = QHBoxLayout()
        title_lay.addWidget(BodyLabel("   CSV列选择:"))
        title_lay.addStretch()

        list_widget = ListWidget(self)

        def update_view():
            selected = [
                list_widget.item(i).text()
                for i in range(list_widget.count())
                if list_widget.item(i).checkState() == Qt.Checked
            ]
            data_select = self.node.get_property("_data_select")
            data_select[port_name] = {"type": "column", "columns": selected}
            self.node.set_property("_data_select", data_select)

            if port_name in self._text_edit_widgets:
                self._text_edit_widgets[port_name].set_data(
                    data[selected] if selected else pd.DataFrame(),
                    port_name
                )

        def set_all(state):
            list_widget.blockSignals(True)
            for i in range(list_widget.count()):
                list_widget.item(i).setCheckState(state)
            list_widget.blockSignals(False)
            update_view()

        def toggle_expand():
            is_exp = not self.parent_panel._selector_expanded[port_id]
            self.parent_panel._selector_expanded[port_id] = is_exp
            max_height = min(list_widget.count() * 40 + 50, 600)
            column_card.setFixedHeight(max_height if is_exp else 200)
            expand_btn.setIcon(get_icon("缩小" if is_exp else "放大"))

        select_all_btn = TransparentToolButton(icon=get_icon("全选"), parent=self)
        clear_btn = TransparentToolButton(icon=get_icon("取消选择"), parent=self)
        expand_btn = TransparentToolButton(icon=get_icon("放大"), parent=self)

        select_all_btn.clicked.connect(lambda: set_all(Qt.Checked))
        clear_btn.clicked.connect(lambda: set_all(Qt.Unchecked))
        expand_btn.clicked.connect(toggle_expand)

        for b in [select_all_btn, clear_btn, expand_btn]:
            title_lay.addWidget(b)
        card_layout.addLayout(title_lay)

        # 获取当前选择（默认全选）
        data_select = self.node.get_property("_data_select")
        saved = data_select.get(port_name, {}).get("columns", columns)  # 默认全选

        for col in columns:
            item = QListWidgetItem(col)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if col in saved else Qt.Unchecked)
            list_widget.addItem(item)

        list_widget.itemChanged.connect(update_view)
        card_layout.addWidget(list_widget)
        layout.addWidget(column_card)

        update_view()

    def _add_list_selector_widget_to_layout(self, port_name, data, layout):
        """列表索引选择器 - 统一使用 _data_select"""
        if not isinstance(data, (list, tuple)) or len(data) == 0:
            return

        list_card = CardWidget(self)
        list_card.setFixedHeight(200)

        port_id = f"{self.node.id}_{port_name}_list"
        if not hasattr(self.parent_panel, '_selector_expanded'):
            self.parent_panel._selector_expanded = {}
        self.parent_panel._selector_expanded.setdefault(port_id, False)

        card_layout = QVBoxLayout(list_card)
        card_layout.setContentsMargins(4, 4, 4, 4)
        card_layout.setSpacing(0)

        title_lay = QHBoxLayout()
        title_lay.addWidget(BodyLabel("   列表元素选择:"))
        title_lay.addStretch()

        list_widget = ListWidget(self)

        def update_view():
            selected_indices = [
                i for i in range(list_widget.count())
                if list_widget.item(i).checkState() == Qt.Checked
            ]
            data_select = self.node.get_property("_data_select")
            data_select[port_name] = {"type": "list", "indices": selected_indices}
            self.node.set_property("_data_select", data_select)

            filtered = self._filter_list_data(data, selected_indices)
            if port_name in self._text_edit_widgets:
                self._text_edit_widgets[port_name].set_data(filtered, port_name)

        def set_all(state):
            list_widget.blockSignals(True)
            for i in range(list_widget.count()):
                list_widget.item(i).setCheckState(state)
            list_widget.blockSignals(False)
            update_view()

        def toggle_expand():
            is_exp = not self.parent_panel._selector_expanded[port_id]
            self.parent_panel._selector_expanded[port_id] = is_exp
            max_height = min(list_widget.count() * 40 + 50, 600)
            list_card.setFixedHeight(max_height if is_exp else 200)
            expand_btn.setIcon(get_icon("缩小" if is_exp else "放大"))

        select_all_btn = TransparentToolButton(icon=get_icon("全选"), parent=self)
        clear_btn = TransparentToolButton(icon=get_icon("取消选择"), parent=self)
        expand_btn = TransparentToolButton(icon=get_icon("放大"), parent=self)

        select_all_btn.clicked.connect(lambda: set_all(Qt.Checked))
        clear_btn.clicked.connect(lambda: set_all(Qt.Unchecked))
        expand_btn.clicked.connect(toggle_expand)

        for b in [select_all_btn, clear_btn, expand_btn]:
            title_lay.addWidget(b)
        card_layout.addLayout(title_lay)

        # 默认全选
        data_select = self.node.get_property("_data_select")
        saved_indices = data_select.get(port_name, {}).get("indices")
        if saved_indices is None:
            saved_indices = list(range(min(len(data), 100)))

        display_limit = 100
        display_data = data[:display_limit] if len(data) > display_limit else data

        for idx, item in enumerate(display_data):
            preview = self._get_preview_value(item, max_len=40)
            item_text = f"[{idx}] {preview}"
            list_item = QListWidgetItem(item_text)
            list_item.setFlags(list_item.flags() | Qt.ItemIsUserCheckable)
            list_item.setCheckState(Qt.Checked if idx in saved_indices else Qt.Unchecked)
            list_widget.addItem(list_item)

        if len(data) > display_limit:
            tip_item = QListWidgetItem(f"... 共 {len(data)} 项，仅显示前 {display_limit} 项")
            tip_item.setFlags(tip_item.flags() & ~Qt.ItemIsEnabled)
            tip_item.setForeground(Qt.gray)
            list_widget.addItem(tip_item)

        list_widget.itemChanged.connect(update_view)
        card_layout.addWidget(list_widget)
        layout.addWidget(list_card)

        update_view()

    def _add_dict_selector_widget_to_layout(self, port_name, data, layout):
        """字典Key选择器 - 仅展示第一层key，与CSV/列表选择器UI完全一致"""
        if not isinstance(data, dict) or len(data) == 0:
            return

        dict_card = CardWidget(self)
        dict_card.setFixedHeight(200)

        port_id = f"{self.node.id}_{port_name}_dict"
        if not hasattr(self.parent_panel, '_selector_expanded'):
            self.parent_panel._selector_expanded = {}
        self.parent_panel._selector_expanded.setdefault(port_id, False)

        card_layout = QVBoxLayout(dict_card)
        card_layout.setContentsMargins(4, 4, 4, 4)
        card_layout.setSpacing(0)

        title_lay = QHBoxLayout()
        title_lay.addWidget(BodyLabel("   字典Key选择:"))
        title_lay.addStretch()

        list_widget = ListWidget(self)

        def update_view():
            selected_keys = [
                list_widget.item(i).data(Qt.UserRole)  # 存原始key（避免key是数字等非字符串）
                for i in range(list_widget.count())
                if list_widget.item(i).checkState() == Qt.Checked
            ]
            data_select = self.node.get_property("_data_select")
            data_select[port_name] = {"type": "dict", "keys": selected_keys}
            self.node.set_property("_data_select", data_select)

            # 预览：只保留选中的顶层key
            filtered = {k: v for k, v in data.items() if k in selected_keys} if selected_keys else {}
            if port_name in self._text_edit_widgets:
                self._text_edit_widgets[port_name].set_data(filtered, port_name)

        def set_all(state):
            list_widget.blockSignals(True)
            for i in range(list_widget.count()):
                list_widget.item(i).setCheckState(state)
            list_widget.blockSignals(False)
            update_view()

        def toggle_expand():
            is_exp = not self.parent_panel._selector_expanded[port_id]
            self.parent_panel._selector_expanded[port_id] = is_exp
            max_height = min(list_widget.count() * 40 + 50, 600)
            dict_card.setFixedHeight(max_height if is_exp else 200)
            expand_btn.setIcon(get_icon("缩小" if is_exp else "放大"))

        select_all_btn = TransparentToolButton(icon=get_icon("全选"), parent=self)
        clear_btn = TransparentToolButton(icon=get_icon("取消选择"), parent=self)
        expand_btn = TransparentToolButton(icon=get_icon("放大"), parent=self)

        select_all_btn.clicked.connect(lambda: set_all(Qt.Checked))
        clear_btn.clicked.connect(lambda: set_all(Qt.Unchecked))
        expand_btn.clicked.connect(toggle_expand)

        for b in [select_all_btn, clear_btn, expand_btn]:
            title_lay.addWidget(b)
        card_layout.addLayout(title_lay)

        # 获取已保存的选择，默认全选
        data_select = self.node.get_property("_data_select")
        saved_keys = data_select.get(port_name, {}).get("keys")
        if saved_keys is None:
            saved_keys = list(data.keys())  # 默认全选

        # 添加所有顶层key
        keys = list(data.keys())
        display_limit = 100
        display_keys = keys[:display_limit] if len(keys) > display_limit else keys

        for key in display_keys:
            preview = self._get_preview_value(data[key], max_len=30)
            item_text = f"{key}: {preview}"
            item = QListWidgetItem(item_text)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setData(Qt.UserRole, key)  # 存原始key（支持非字符串key）
            item.setCheckState(Qt.Checked if key in saved_keys else Qt.Unchecked)
            list_widget.addItem(item)

        if len(keys) > display_limit:
            tip_item = QListWidgetItem(f"... 共 {len(keys)} 个Key，仅显示前 {display_limit} 个")
            tip_item.setFlags(tip_item.flags() & ~Qt.ItemIsEnabled)
            tip_item.setForeground(Qt.gray)
            list_widget.addItem(tip_item)

        list_widget.itemChanged.connect(update_view)
        card_layout.addWidget(list_widget)
        layout.addWidget(dict_card)

        update_view()

    def _collect_checked_paths(self, item):
        paths = []
        for i in range(item.childCount()):
            child = item.child(i)
            node_data = child.data(0, Qt.UserRole) or {}
            path = node_data.get("path", [])
            if child.checkState(0) == Qt.Checked:
                paths.append(path)
                paths.extend(self._collect_checked_paths(child))
        return paths

    def _set_tree_item_state(self, item, state):
        item.setCheckState(0, state)
        for i in range(item.childCount()):
            self._set_tree_item_state(item.child(i), state)

    def _restore_tree_state(self, item, target_paths, current_path):
        is_exact = any(p == current_path for p in target_paths)
        has_child = any(len(p) > len(current_path) and p[:len(current_path)] == current_path for p in target_paths)

        if is_exact:
            item.setCheckState(0, Qt.Checked)
        elif has_child:
            item.setCheckState(0, Qt.PartiallyChecked)
        else:
            item.setCheckState(0, Qt.Unchecked)

        for i in range(item.childCount()):
            child = item.child(i)
            node_data = child.data(0, Qt.UserRole) or {}
            child_path = node_data.get("path", [])
            self._restore_tree_state(child, target_paths, child_path)

    def _count_visible_tree_items(self, item):
        count = 1
        if item.isExpanded():
            for i in range(item.childCount()):
                count += self._count_visible_tree_items(item.child(i))
        return count

    def _filter_list_data(self, data, indices):
        if not isinstance(data, (list, tuple)):
            return data
        if not indices:
            return []
        unique_indices = sorted(set(i for i in indices if 0 <= i < len(data)))
        result = [data[i] for i in unique_indices]
        return result if len(result) > 1 else (result[0] if result else None)

    def _get_current_input_value(self, port_name, original_data):
        data_select = self.node.get_property("_data_select")
        config = data_select.get(port_name, {})
        if not config:
            return original_data

        t = config.get("type")
        try:
            if t == "column" and isinstance(original_data, pd.DataFrame):
                cols = config.get("columns", [])
                return original_data[cols] if cols else original_data
            elif t == "list":
                return self._filter_list_data(original_data, config.get("indices", []))
            elif t == "dict":
                selected_keys = config.get("keys", [])
                if isinstance(original_data, dict):
                    return {k: v for k, v in original_data.items() if
                            k in selected_keys} if selected_keys else original_data
        except Exception as e:
            logger.warning(f"过滤失败 {port_name}: {e}")
        return original_data

    def _get_preview_value(self, value, max_len=40):
        try:
            if value is None:
                return "null"
            elif isinstance(value, (str, int, float, bool)):
                text = str(value)
            elif isinstance(value, (list, tuple)):
                text = f"[{len(value)} items]"
            elif isinstance(value, dict):
                text = f"{{{len(value)} keys}}"
            else:
                text = str(type(value).__name__)
            return (text[:max_len] + "...") if len(text) > max_len else text
        except:
            return "<preview error>"

    def handle_global_variable(self, node, port_name, is_checked):
        if is_checked:
            self.add_output_to_global_func(node, port_name)
        else:
            self.delete_output_from_global_func(node, port_name)

    def _show_context_menu(self, card, p_name, pos):
        menu = RoundMenu(parent=self)
        menu.addAction(Action(FluentIcon.COPY, "复制为表达式",
                              triggered=lambda: self.copy_as_expression_func("node_vars",
                                                                             f"{self.node.name()}__{p_name}")))
        menu.exec_(card.mapToGlobal(pos))

    def _get_history(self):
        """从 JSON 读取历史记录"""
        history_file = "canvas_files/upload_index.json"
        if not os.path.exists(history_file):
            return []
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                data = orjson.loads(f.read())
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"读取历史记录失败: {e}")
            return []

    def _add_to_history(self, file_path):
        """添加文件到历史记录 (去重并保留最近15条)"""
        os.makedirs("canvas_files", exist_ok=True)
        history_file = "canvas_files/upload_index.json"
        history = self._get_history()

        # 转换路径为字符串并去重
        file_path = str(file_path)
        if file_path in history:
            history.remove(file_path)

        history.insert(0, file_path)  # 新的排在前面
        history = history[:15]  # 限制数量

        try:
            with open(history_file, 'wb') as f:
                f.write(orjson.dumps(history, option=orjson.OPT_INDENT_2))
        except Exception as e:
            logger.error(f"保存历史记录失败: {e}")

    def _remove_from_history(self, file_path):
        """从历史记录中移除指定文件路径并持久化"""
        history = self._get_history()
        file_path = str(file_path)
        if file_path in history:
            history.remove(file_path)
            self._save_history(history)
            logger.info(f"已从历史记录中移除不存在的文件: {file_path}")

    def _save_history(self, history):
        """安全保存历史记录到JSON文件"""
        os.makedirs("canvas_files", exist_ok=True)
        history_file = "canvas_files/upload_index.json"
        try:
            # 使用orjson保持与读取一致的编码处理
            with open(history_file, 'wb') as f:
                f.write(orjson.dumps(history, option=orjson.OPT_INDENT_2))
        except Exception as e:
            logger.error(f"保存历史记录失败: {e}")