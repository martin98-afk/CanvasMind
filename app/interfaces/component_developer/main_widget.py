# -*- coding: utf-8 -*-
import json
import traceback
import uuid
from pathlib import Path

from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtWidgets import (
    QWidget, QTableWidgetItem
)
from loguru import logger

from app.interfaces.component_developer.llm_context import LLMContextProvider
from app.interfaces.component_developer.utils.component_history_manager import ComponentHistoryManager
from app.interfaces.component_developer.utils.message_manager import MessageManager
from app.interfaces.component_developer.utils.storage_manager import ComponentStorageManager
from app.interfaces.component_developer.utils.sync_code_to_ui import SyncCodeToUI
from app.interfaces.component_developer.utils.sync_ui_to_code import SyncUItoCode
from app.interfaces.component_developer.widgets.ui_setup import ComponentDevelopUISetUp
from app.scan_components import ComponentUsageTracker
from app.templates.component_templates.base import DEFAULT_NODE_TEMPLATE


class ComponentDeveloperPage(QWidget):
    """组件开发主界面（已修复双向同步问题）"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ComponentDeveloperWidget")
        self.home = parent
        self.package_manager = self.home.package_manager
        self.llm_context_provider = LLMContextProvider(self)
        self.ui_manager = ComponentDevelopUISetUp(self)
        self.ui_manager.setup_ui()
        # ✅ 双向同步
        self.sync_ui_to_code = SyncUItoCode(self)
        self.sync_code_to_ui = SyncCodeToUI(self)
        self.storage_manager = ComponentStorageManager(self)
        self._connect_signals()

    @property
    def history_table(self):
        return self.ui_manager.history_table

    @property
    def history_tool(self):
        return self.ui_manager.history_tool

    @property
    def llm_chatter(self):
        return self.ui_manager.llm_chatter

    @property
    def code_editor(self):
        return self.ui_manager.code_editor

    @property
    def component_tree(self):
        return self.ui_manager.component_tree

    @property
    def context_register(self):
        return self.llm_context_provider.context_register

    @property
    def component_info(self):
        return self.ui_manager.side_dock_area.get_tool_instance("组件属性面板")

    @property
    def name_edit(self):
        return self.component_info.name_edit

    @property
    def category_edit(self):
        return self.component_info.category_edit

    @property
    def description_edit(self):
        return self.component_info.description_edit

    @property
    def requirements_edit(self):
        return self.component_info.requirements_edit

    @property
    def input_port_editor(self):
        return self.component_info.input_port_editor

    @property
    def output_port_editor(self):
        return self.component_info.output_port_editor

    @property
    def property_editor(self):
        return self.component_info.property_editor
    
    @property
    def current_component_file(self):
        return self.storage_manager._current_component_file

    @property
    def current_template_code(self):
        return self.ui_manager._current_template_code

    def save_component_by_full_path(self, full_path: str, new_code: str):
        return self.storage_manager.save_component_by_full_path(full_path, new_code)

    def apply_component_info_to_code(self, code: str, component_info: dict):
        return self.sync_ui_to_code.apply_component_info_to_code(code, component_info)

    def analyze_code_for_requirements(self):
        return self.sync_code_to_ui._analyze_code_for_requirements()

    def sync_basic_info_to_code(self):
        return self.sync_ui_to_code._sync_basic_info_to_code()

    def load_component(self, full_path=None, component=None, uuid=None):
        return self.storage_manager._load_component(full_path, component, uuid)

    def save_component(self, delete_original_file=True):
        return self.storage_manager._save_component(delete_original_file)

    def _connect_signals(self):
        self.history_table.itemDoubleClicked.connect(self._load_history_code)
        self.history_table.itemChanged.connect(self._on_history_description_changed)
        self.llm_chatter.insertResponse.connect(self._handle_insert_code_from_llm)
        self.llm_chatter.createResponse.connect(self._handle_create_component_from_llm)
        self.component_tree.component_selected.connect(self.storage_manager._load_component)
        self.component_tree.component_created.connect(self.storage_manager._on_component_created)
        self.component_tree.component_pasted.connect(self.storage_manager._on_component_pasted)
        self.input_port_editor.ports_changed.connect(self.sync_ui_to_code._sync_ports_to_code)
        self.output_port_editor.ports_changed.connect(self.sync_ui_to_code._sync_ports_to_code)
        self.property_editor.properties_changed.connect(self.sync_ui_to_code._on_property_changed)
        self.code_editor.code_changed.connect(self.sync_code_to_ui._on_code_text_changed)
        # ✅ 保留 UI → 代码 实时同步（但修复同步逻辑）
        self.code_editor.code_editor.installEventFilter(self)
        for widget in [self.name_edit, self.category_edit, self.description_edit, self.requirements_edit]:
            widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.FocusOut:
            if obj in [self.name_edit, self.category_edit, self.description_edit, self.requirements_edit]:
                # ✅ 用户结束编辑，立即同步到代码
                self.sync_basic_info_to_code()
        return super().eventFilter(obj, event)

    def _handle_insert_code_from_llm(self, code: str):
        editor = self.code_editor.code_editor
        cursor = editor.textCursor()
        cursor.insertText(code)
        editor.setTextCursor(cursor)
        MessageManager.success("已插入代码", "", self)

    def _handle_create_component_from_llm(self, code: str):
        if not code.strip():
            MessageManager.warning("代码为空，无法创建组件", "", self)
            return
        self.code_editor.set_code(code)
        info = self._extract_component_info_from_code_str(code)
        self._create_new_component(info)
        self.code_editor.suspend_sync()
        try:
            self.code_editor.replace_text_preserving_view(code.strip())
            self._current_component_code = code.strip()
        finally:
            self.code_editor.resume_sync()
        try:
            self._save_component(delete_original_file=False)
            self.side_dock_area.switch_to("组件属性面板")
            MessageManager.success(f"已创建并保存组件：{info['name']}", "", self)
        except Exception as e:
            MessageManager.error(f"保存失败：{str(e)}", "请检查代码语法", self)

    def update_usage_table(self, uuid):
        usage_records = ComponentUsageTracker().get_usage(uuid)
        usage_list = [
            {
                "canvas_name": str(rec.canvas_path.stem).split(".workflow")[0],
                "canvas_path": rec.canvas_path,
                "node_name": rec.node_name,
                "version": rec.version
            }
            for rec in usage_records
        ]
        try:
            self.history_tool.strategy_changed.disconnect(self._on_usage_strategy_changed)
        except TypeError:
            pass
        self.history_tool.strategy_changed.connect(self._on_usage_strategy_changed)
        if self.history_tool:
            self.history_tool.update_usage_table(usage_list)

    def _on_usage_strategy_changed(self, canvas_path: str, node_name: str, strategy: str):
        try:
            canvas_file = Path(canvas_path)
            with open(canvas_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            nodes = data.get("graph", {}).get("nodes", {})
            target_node_id = None
            runtime = data.get("runtime", {})
            node_id2stable_key = runtime.get("node_id2stable_key", {})
            for node_id, node_data in nodes.items():
                if node_data.get("name") == node_name:
                    stable_key = node_id2stable_key.get(node_id, "")
                    full_path = stable_key.split("||")[0] if "||" in stable_key else ""
                    target_node_id = node_id
                    break
            if not target_node_id:
                MessageManager.warning("未找到对应节点", "", self)
                return
            new_version = "latest" if strategy == "同步" else strategy
            nodes[target_node_id].setdefault("custom", {})["version"] = new_version
            with open(canvas_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            MessageManager.success(f"已更新 {node_name} 的版本策略为 {new_version}", "", self)
        except Exception as e:
            logger.error(traceback.format_exc())
            MessageManager.error(f"更新策略失败: {e}", "", self)

    def reset_edit(self):
        self.component_info.clear_all()
        self.code_editor.set_code(DEFAULT_NODE_TEMPLATE)
        self.storage_manager._current_component_file = None
        self.component_tree.set_current_editing_component(None)

    def _load_history_list(self, component_file_path: Path):
        self.history_table.setRowCount(0)
        histories = ComponentHistoryManager.load_histories(component_file_path)
        for history in reversed(histories):
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)
            version_item = QTableWidgetItem(history['version'])
            version_item.setFlags(version_item.flags() & ~Qt.ItemIsEditable)
            self.history_table.setItem(row, 0, version_item)
            time_item = QTableWidgetItem(history['timestamp'])
            time_item.setFlags(time_item.flags() & ~Qt.ItemIsEditable)
            self.history_table.setItem(row, 1, time_item)
            desc = history.get('description', '')
            desc_item = QTableWidgetItem(desc)
            self.history_table.setItem(row, 2, desc_item)

    def _load_history_code(self, item):
        row = item.row()
        if self.current_component_file:
            histories = ComponentHistoryManager.load_histories(self.current_component_file)
            if 0 <= row < len(histories):
                history_data = histories[len(histories) - 1 - row]
                if history_data and 'code' in history_data:
                    code = history_data['code']
                    self.code_editor.replace_text_preserving_view(code)
                    logger.info(f"已加载历史版本: {history_data['version']} - {history_data['timestamp']}")
                else:
                    logger.error("历史记录数据不完整，无法加载代码。")
            else:
                logger.error("无效的历史记录行。")
        else:
            logger.error("当前没有加载的组件文件，无法加载历史代码。")

    def _on_history_description_changed(self, item):
        if not self.current_component_file or item.column() != 2:
            return
        row = item.row()
        new_desc = item.text()
        histories = ComponentHistoryManager.load_histories(self.current_component_file)
        real_index = len(histories) - 1 - row
        if 0 <= real_index < len(histories):
            histories[real_index]['description'] = new_desc
            history_file = ComponentHistoryManager.get_history_file_path(self.current_component_file)
            try:
                with open(history_file, 'w', encoding='utf-8') as f:
                    json.dump(histories, f, ensure_ascii=False, indent=4)
            except Exception as e:
                logger.error(f"保存说明失败: {e}")
                MessageManager.error("保存说明失败", str(e), self)