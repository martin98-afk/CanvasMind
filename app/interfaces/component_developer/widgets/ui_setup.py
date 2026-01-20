# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout
from qfluentwidgets import TransparentToolButton, FluentIcon, RoundMenu, Action, BodyLabel, \
    TransparentDropDownToolButton, MessageBox

from app.interfaces.component_developer.constants import HIDE_SPLITTER_SIZES, DEFAULT_SPLITTER_SIZES
from app.interfaces.component_developer.utils.message_manager import MessageManager
from app.interfaces.component_developer.widgets.component_develop_tree import ComponentTreePanel
from app.templates.component_templates import DEFAULT_NODE_TEMPLATE, default_templates
from app.utils.utils import get_icon
from app.widgets.basic_widget.splitter import ModernSplitter
from app.widgets.code_editor.code_editer import CodeEditorWidget
from app.widgets.side_dock_area.side_dock_area import SideDockArea


class ComponentDevelopUISetUp:

    def __init__(self, parent):
        self.parent = parent

    # --- ui构建 ---
    def setup_ui(self):
        layout = QHBoxLayout(self.parent)
        layout.setContentsMargins(0, 0, 0, 0)
        # 左侧：组件树和开发区域
        self.splitter = ModernSplitter(Qt.Horizontal)
        self.component_tree_panel = ComponentTreePanel(self.parent)
        self.component_tree = self.component_tree_panel.tree
        self.splitter.addWidget(self.component_tree_panel)
        # 代码编辑框
        code_widget = QWidget(self.parent)
        code_layout = QVBoxLayout(code_widget)
        code_layout.setContentsMargins(0, 0, 0, 0)
        self.code_editor = CodeEditorWidget(self.parent, self.parent.package_manager.get_current_python_exe())
        save_layout = QHBoxLayout()
        code_btn = TransparentToolButton(get_icon("代码执行"), parent=self.parent)
        code_btn.setIconSize(QSize(20, 25))
        code_btn.setFixedSize(20, 25)
        save_layout.addWidget(code_btn)

        # 国际化标签
        save_layout.addWidget(BodyLabel(self.parent.tr("组件代码:")))

        template_dropdown = TransparentDropDownToolButton(FluentIcon.ALIGNMENT, parent=self.parent)
        self._current_template_code = DEFAULT_NODE_TEMPLATE
        menu = RoundMenu(parent=template_dropdown)

        # 模板名称翻译处理（假设 default_templates 的 key 可以在翻译文件中找到匹配）
        for template_name in default_templates.keys():
            action = Action(
                self.parent.tr(template_name),
                triggered=lambda checked=False, name=template_name,
                                 code=default_templates[template_name]: self._switch_template(name, code)
            )
            menu.addAction(action)

        template_dropdown.setMenu(menu)
        save_layout.addWidget(template_dropdown)
        save_layout.addStretch()

        run_btn = TransparentToolButton(FluentIcon.PLAY, parent=self.parent)
        run_btn.clicked.connect(self._run_component_code)
        save_layout.addWidget(run_btn)

        save_btn = TransparentToolButton(FluentIcon.SAVE, parent=self.parent)
        save_btn.clicked.connect(lambda: self._save_component(True))

        cancel_btn = TransparentToolButton(FluentIcon.CLOSE, parent=self.parent)
        cancel_btn.clicked.connect(self._cancel_edit)

        save_layout.addWidget(save_btn)
        save_layout.addWidget(cancel_btn)
        code_layout.addLayout(save_layout)
        code_layout.addWidget(self.code_editor, stretch=1)
        self.splitter.addWidget(code_widget)

        # 右侧：组件属性（"组件开发" 国际化）
        self.side_dock_area = SideDockArea(self.parent, "组件开发")

        # 工具实例名称国际化
        self._llm_chatter = self.side_dock_area.get_tool_instance("大模型对话")
        self._llm_chatter.set_system_prompt(self.parent.llm_context_provider.system_prompt)

        self.splitter.addWidget(self.side_dock_area)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes(DEFAULT_SPLITTER_SIZES)
        layout.addWidget(self.splitter)
        layout.addWidget(self.side_dock_area.tool_panel)

    @property
    def history_table(self):
        return self.side_dock_area.get_tool_instance("组件历史管理").history_table

    @property
    def history_tool(self):
        return self.side_dock_area.get_tool_instance("组件历史管理")

    @property
    def llm_chatter(self):
        return self._llm_chatter

    def hide_splitter(self):
        self.splitter.setSizes(HIDE_SPLITTER_SIZES)
        self.splitter.update()

    def show_splitter(self):
        self.splitter.setSizes(DEFAULT_SPLITTER_SIZES)
        self.splitter.update()

    # 按钮绑定函数
    def _save_component(self, delete_original_file=True):
        return self.parent.save_component(delete_original_file)

    def _cancel_edit(self):
        # 国际化弹窗文字
        title = self.parent.tr("确认")
        content = self.parent.tr("确定要取消编辑吗？未保存的更改将丢失。")
        w = MessageBox(title, content, self.parent.window())

        if w.exec():
            self.parent.component_info.clear_all()
            self.code_editor.set_code(DEFAULT_NODE_TEMPLATE)
            self._current_component_file = None
            self.component_tree.set_current_editing_component(None)

    def _switch_template(self, template_name, template_code):
        self._current_template_code = template_code
        self.code_editor.replace_text_preserving_view(template_code)
        self._current_component_code = template_code
        # 国际化消息提示
        msg = self.parent.tr("已切换到模板: {}").format(template_name)
        MessageManager.success(msg, "", self.parent)

    def _run_component_code(self):
        # 切换到对应的面板（国际化 Key）
        self.side_dock_area.switch_to("多终端调试面板")

        local_import = """# -*- coding: utf-8 -*-
try:
    from app.components.base import *
except:
    from _internal.app.components.base import *
"""
        current_code = local_import + self.code_editor.get_code()
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