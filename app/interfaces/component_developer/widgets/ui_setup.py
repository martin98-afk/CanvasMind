# -*- coding: utf-8 -*-
from pathlib import Path
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget
from loguru import logger
from qfluentwidgets import TransparentToolButton, FluentIcon, RoundMenu, Action, BodyLabel, \
    TransparentDropDownToolButton, MessageBox, SegmentedWidget

from app.interfaces.component_developer.constants import HIDE_SPLITTER_SIZES, DEFAULT_SPLITTER_SIZES
from app.interfaces.component_developer.utils.message_manager import MessageManager
from app.interfaces.component_developer.widgets.component_develop_tree import ComponentTreePanel
from app.interfaces.component_developer.widgets.editor_tab_manager import ComponentTabManager
from app.interfaces.component_developer.widgets.extension_file_manager import ExtensionFileManager
from app.templates.component_templates import DEFAULT_NODE_TEMPLATE, default_templates
from app.utils.utils import get_icon
from app.widgets.basic_widget.splitter import ModernSplitter
from app.widgets.code_editor.code_editer import CodeEditorWidget
from app.widgets.side_dock_area.side_dock_area import SideDockArea
from app.scan_components import resource_path


class ComponentDevelopUISetUp:

    def __init__(self, parent):
        self.parent = parent
        self.current_comp_uuid = None

    # --- ui构建 ---
    def setup_ui(self):
        layout = QHBoxLayout(self.parent)
        layout.setContentsMargins(0, 0, 0, 0)

        # ================= 左侧区域 (Segment + Stack) =================
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 5, 0, 0)

        # 1. 顶部切换条
        self.segment = SegmentedWidget(self.parent)
        self.segment.addItem("component_list", "组件列表")
        self.segment.addItem("extension_files", "扩展资源")

        # 【修复点 1】使用 currentItemChanged 信号
        self.segment.currentItemChanged.connect(self._on_segment_changed)

        left_layout.addWidget(self.segment)

        # 2. 堆叠窗口
        self.left_stack = QStackedWidget()

        # Page 1: 组件树
        self.component_tree_panel = ComponentTreePanel(self.parent)
        self.component_tree = self.component_tree_panel.tree
        # 绑定点击事件，用于辅助刷新
        self.component_tree.itemClicked.connect(self._on_component_tree_clicked)
        self.left_stack.addWidget(self.component_tree_panel)

        # Page 2: 扩展文件管理器
        self.file_manager = ExtensionFileManager(self.parent)
        self.file_manager.file_double_clicked.connect(self._on_file_open_request)
        self.left_stack.addWidget(self.file_manager)

        left_layout.addWidget(self.left_stack)

        # ================= 中间区域 (Toolbar + TabManager) =================
        middle_container = QWidget()
        middle_layout = QVBoxLayout(middle_container)
        middle_layout.setContentsMargins(0, 0, 0, 0)
        middle_layout.setSpacing(0)
        # 2. Tab 编辑器管理器 (替换原有的直接 CodeEditor)
        self.tab_manager = ComponentTabManager(self.parent)
        self.tab_manager.saveSignal.connect(lambda: self._save_component(True))
        self.tab_manager.runSignal.connect(self._run_component_code)
        self.tab_manager.cancelSignal.connect(self._cancel_edit)
        self.tab_manager.templateChangedSignal.connect(self._switch_template)
        # 初始化不可关闭的主代码编辑器
        self.code_editor = CodeEditorWidget(self.parent, self.parent.package_manager.get_current_python_exe())
        self.tab_manager.init_main_editor(self.code_editor, "未命名组件")
        middle_layout.addWidget(self.tab_manager)
        # 【兼容性挂载】将新组件挂载到 parent，防止旧代码报错
        self.parent.tab_manager = self.tab_manager
        # ================= 右侧区域 =================
        self.side_dock_area = SideDockArea(self.parent, "组件开发")
        self._llm_chatter = self.side_dock_area.get_tool_instance("大模型对话")
        self._llm_chatter.set_system_prompt(self.parent.llm_context_provider.system_prompt)

        # ================= 组装 Splitter =================
        self.splitter = ModernSplitter(Qt.Horizontal)
        self.splitter.addWidget(left_container)
        self.splitter.addWidget(middle_container)
        self.splitter.addWidget(self.side_dock_area)

        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes(DEFAULT_SPLITTER_SIZES)

        layout.addWidget(self.splitter)
        layout.addWidget(self.side_dock_area.tool_panel)

    # --- 辅助属性 ---

    @property
    def history_table(self):
        return self.side_dock_area.get_tool_instance("组件历史管理").history_table

    @property
    def history_tool(self):
        return self.side_dock_area.get_tool_instance("组件历史管理")

    @property
    def llm_chatter(self):
        return self._llm_chatter

    @property
    def current_segment_key(self):
        """【修复点 2】安全获取当前 Segment 的 Key"""
        if hasattr(self.segment, "currentItem"):
            item = self.segment.currentItem()
            if item:
                return item.routeKey()
        return "component_list"

    def hide_splitter(self):
        self.splitter.setSizes(HIDE_SPLITTER_SIZES)
        self.splitter.update()

    def show_splitter(self):
        self.splitter.setSizes(DEFAULT_SPLITTER_SIZES)
        self.splitter.update()

    # --- 逻辑联动函数 ---

    def _on_segment_changed(self, key):
        """Segment 切换回调"""
        # key 由 currentItemChanged 信号直接传递，类型为 str
        if key == "component_list":
            self.left_stack.setCurrentIndex(0)
        else:
            self.left_stack.setCurrentIndex(1)
            # 切换到文件视图时，尝试刷新路径
            if self.current_comp_uuid:
                self._update_file_manager_path(self.current_comp_uuid)

    def _on_component_tree_clicked(self, item, column):
        """点击组件树"""
        # 这里的核心逻辑其实由 StorageManager 加载组件时触发
        # 这里主要是为了防抖或者 UI 即时响应
        pass

    def _update_file_manager_path(self, uuid_str):
        """刷新文件管理器的路径"""
        if not uuid_str: return
        try:
            ext_path = Path(resource_path("app/component_extensions")) / uuid_str
            self.segment.setCurrentItem("extension_files")
            self.file_manager.set_root_path(str(ext_path))
        except Exception as e:
            logger.exception(f"Error updating file manager path: {e}")

    def _on_file_open_request(self, file_path):
        """左侧文件双击 -> 右侧 Tab 打开"""
        if self.tab_manager:
            self.tab_manager.open_file(file_path, self)

    # --- 按钮与功能函数 ---

    def _save_component(self, delete_original_file=True):
        """保存逻辑：区分主代码和扩展文件"""
        is_main, widget = self.tab_manager.get_current_editor_info()

        if is_main:
            # 如果是主代码 Tab，调用 Parent 的保存逻辑（存数据库/JSON）
            return self.parent.save_component(delete_original_file)
        elif hasattr(widget, "property_file_path"):
            # 如果是扩展文件，直接保存到磁盘
            try:
                # 检查是否是代码编辑器
                if hasattr(widget, "get_code"):
                    content = widget.get_code()
                    with open(widget.property_file_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    MessageManager.success(self.parent.tr("文件已保存"), str(widget.property_file_path), self.parent)
                else:
                    # 图片等只读资源忽略
                    pass
            except Exception as e:
                MessageManager.error(self.parent.tr("保存失败"), str(e), self.parent)

    def _cancel_edit(self):
        title = self.parent.tr("确认")
        content = self.parent.tr("确定要取消编辑吗？未保存的更改将丢失。")
        w = MessageBox(title, content, self.parent.window())

        if w.exec():
            self.parent.component_info.clear_all()
            self.code_editor.set_code(DEFAULT_NODE_TEMPLATE)
            self._current_component_file = None
            self.component_tree.set_current_editing_component(None)

            # 清理 Tab 和 重置左侧
            if hasattr(self.tab_manager, "close_all_non_main_tabs"):
                self.tab_manager.close_all_non_main_tabs()
            self.current_comp_uuid = None
            self.segment.setCurrentItem("component_list")

    def _switch_template(self, template_name, template_code):
        self._current_template_code = template_code
        self.code_editor.replace_text_preserving_view(template_code)
        self._current_component_code = template_code
        msg = self.parent.tr("已切换到模板: {}").format(template_name)
        MessageManager.success(msg, "", self.parent)

    def _run_component_code(self):
        self.side_dock_area.switch_to("多终端调试面板")

        # 始终运行 Main Code Editor 的代码
        local_import = """# -*- coding: utf-8 -*-
try:
    from app.components.base import *
except:
    from _internal.app.components.base import *
import sys
sys.path.insert(0, r"{extention_path}")
"""
        extention_path = rf"{(Path(resource_path('app/component_extensions')) / self.current_comp_uuid).resolve()}"

        current_code = local_import.format(extention_path=extention_path) + self.code_editor.get_code()
        if not current_code.strip():
            MessageManager.warning(self.parent.tr("代码编辑器为空，无法运行！"), "", self.parent)
            return

        current_console = self.side_dock_area.get_tool_instance("多终端调试面板").get_current_console()
        if current_console:
            current_console.execute_code(current_code)
        else:
            MessageManager.error(self.parent.tr("当前控制台未启动或无 kernel 客户端！"), "", self.parent)

    def destroy_all(self):
        """彻底销毁 UI 所有动态创建的内容，防止内存泄漏"""
        pass