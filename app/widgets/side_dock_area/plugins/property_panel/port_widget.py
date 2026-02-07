# -*- coding: utf-8 -*-
import orjson
import pandas as pd
import json
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

        # CSV 轻量预览处理
        filtered_data = data
        if not is_output and p_type == ArgumentType.CSV:
            if isinstance(data, str) and data.lower().endswith('.csv'):
                try:
                    # 使用同步读取，由于 nrows=5 且通常是本地路径，阻塞感极低
                    # 若追求极致，此处也可改为异步，但会增加树组件渲染的复杂度
                    if os.path.exists(data):
                        filtered_data = pd.read_csv(data, nrows=5)
                except:
                    pass
            filtered_data = self._get_current_input_value(p_name, filtered_data)

        ui['tree'].set_data(filtered_data, p_name)
        self._text_edit_widgets[p_name] = ui['tree']

        # 重新绑定按钮信号 (防止闭包引用旧数据)
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

        self._refresh_card_actions(card, p_name, p_label, p_type, is_output)
        self._refresh_extra_area(card, p_name, p_type, data, is_output)

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

    def _apply_history_selection(self, port_name, file_path):
        """将历史记录中的文件应用到节点"""
        if not os.path.exists(file_path):
            InfoBar.error("错误", "该历史文件已不存在", parent=self.main_window)
            return

        self.node.set_output_value(port_name, file_path)
        try:
            self.node.model.add_property(f"{port_name}_upload", file_path)
        except:
            self.node.model.set_property(f"{port_name}_upload", file_path)

        if port_name in self._text_edit_widgets:
            self._text_edit_widgets[port_name].set_data(file_path, port_name)

        InfoBar.success("已选择", f"已切换至: {os.path.basename(file_path)}", parent=self.main_window)

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

    def _refresh_extra_area(self, card, p_name, p_type, data, is_output):
        container = card.ui['extra_container']
        while container.count():
            item = container.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        if not is_output and isinstance(data, pd.DataFrame) and not data.empty:
            self._add_column_selector_widget_to_layout(p_name, data, container)

    def _add_column_selector_widget_to_layout(self, port_name, data, layout):
        """CSV 列选择器组件"""
        if not isinstance(data, pd.DataFrame) or data.empty: return
        columns = list(data.columns)

        column_card = CardWidget(self)
        column_card.setFixedHeight(200)

        port_id = f"{self.node.id}_{port_name}"
        if not hasattr(self.parent_panel, '_column_selector_expanded'):
            self.parent_panel._column_selector_expanded = {}
        self.parent_panel._column_selector_expanded.setdefault(port_id, False)

        card_layout = QVBoxLayout(column_card)
        card_layout.setContentsMargins(4, 4, 4, 4)
        card_layout.setSpacing(0)

        title_lay = QHBoxLayout()
        title_lay.addWidget(BodyLabel("   CSV列选择:"))
        title_lay.addStretch()

        # 定义操作
        def update_view():
            selected = [list_widget.item(i).text() for i in range(list_widget.count()) if
                        list_widget.item(i).checkState() == Qt.Checked]
            self.node.set_property("_column_select", self.node.get_property("_column_select") | {port_name: selected})
            if port_name in self._text_edit_widgets:
                self._text_edit_widgets[port_name].set_data(data[selected] if selected else pd.DataFrame(), port_name)

        def set_all(state):
            list_widget.blockSignals(True)
            for i in range(list_widget.count()): list_widget.item(i).setCheckState(state)
            list_widget.blockSignals(False)
            update_view()

        def toggle_expand():
            is_exp = not self.parent_panel._column_selector_expanded[port_id]
            self.parent_panel._column_selector_expanded[port_id] = is_exp
            column_card.setFixedHeight(min(list_widget.count() * 40 + 50, 600) if is_exp else 200)
            expand_btn.setIcon(get_icon("缩小" if is_exp else "放大"))

        # 按钮构建
        select_all_btn = TransparentToolButton(icon=get_icon("全选"), parent=self)
        clear_btn = TransparentToolButton(icon=get_icon("取消选择"), parent=self)
        expand_btn = TransparentToolButton(icon=get_icon("放大"), parent=self)

        select_all_btn.clicked.connect(lambda: set_all(Qt.Checked))
        clear_btn.clicked.connect(lambda: set_all(Qt.Unchecked))
        expand_btn.clicked.connect(toggle_expand)

        for b in [select_all_btn, clear_btn, expand_btn]: title_lay.addWidget(b)
        card_layout.addLayout(title_lay)

        list_widget = ListWidget(self)
        for col in columns:
            item = QListWidgetItem(col)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            saved = self.node.get_property("_column_select").get(port_name, columns)
            item.setCheckState(Qt.Checked if col in saved else Qt.Unchecked)
            list_widget.addItem(item)

        list_widget.itemChanged.connect(update_view)
        card_layout.addWidget(list_widget)
        layout.addWidget(column_card)

    def _get_current_input_value(self, port_name, original_data):
        selected = self.node.get_property("_column_select").get(port_name, [])
        if selected and isinstance(original_data, pd.DataFrame):
            try:
                return original_data[selected] if len(selected) > 1 else original_data[selected[0]]
            except:
                return original_data
        return original_data

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
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存历史记录失败: {e}")