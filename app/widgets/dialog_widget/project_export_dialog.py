# -*- coding: utf-8 -*-
from collections import defaultdict

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QVBoxLayout as VBoxLayout, QHBoxLayout, QLabel
from qfluentwidgets import (
    BodyLabel, TextEdit, InfoBar, CheckBox, ScrollArea, SubtitleLabel, StrongBodyLabel, CardWidget,
    PushButton, SegmentedWidget, LineEdit, SmoothScrollArea
)

from app.widgets.basic_widget.splitter import ModernSplitter
from app.widgets.dialog_widget.step_messageboxbase import StepMessageBoxBase


class ProjectExportFlowDialog(StepMessageBoxBase):
    """
    项目导出流程对话框：整合输入选择、输出选择和项目信息配置。
    """

    def __init__(self,
                 candidate_items,
                 parent=None,
                 current_selected_inputs=None,
                 current_selected_outputs=None,
                 project_name="",
                 requirements="",

                 readme_func=""):
        # 定义步骤
        steps = [
            {"name": "select_inputs", "title": "选择输入参数(未选择参数将用当前参数固化)"},
            {"name": "select_outputs", "title": "选择输出参数"},
            {"name": "project_info", "title": "项目信息"}
        ]
        super().__init__(parent=parent, steps=steps)
        self.widget.setFixedSize(800, 700)
        self.candidate_items = candidate_items
        self.current_selected_inputs = current_selected_inputs or {}
        self.current_selected_outputs = current_selected_outputs or {}
        self.project_name = project_name
        self.requirements = requirements
        self.readme_func = readme_func

        # --- 页面1: 输入选择 ---
        self.input_page = InputSelectionDialog(
            candidate_items=candidate_items,
            parent=self.widget,  # 使用 widget 作为父级，而不是 self
            current_selected_items=current_selected_inputs
        )
        self.add_page(self.input_page)

        # --- 页面2: 输出选择 ---
        # 提取输出项（根据你的数据结构，可能需要调整过滤逻辑）
        output_candidate_items = [item for item in candidate_items if item.get("type") == "组件输出"]  # 假设有个 type 字段标识
        self.output_page = OutputSelectionDialog(
            candidate_items=output_candidate_items,
            parent=self.widget,
            current_selected_items=current_selected_outputs
        )
        self.add_page(self.output_page)

        # --- 页面3: 项目信息 ---
        self.info_page = ProjectExportDialog(
            project_name=project_name,
            requirements=requirements,
            readme_func=readme_func,
            parent=self.widget,
            get_input_func = self.get_selected_inputs,
            get_output_func = self.get_selected_outputs
        )
        self.add_page(self.info_page)

        # 检查是否有输入项，决定是否跳过此步骤
        input_candidate_items = [item for item in candidate_items if item.get("type") in ["组件输入", "组件超参数"]]
        has_inputs = bool(input_candidate_items)
        if not has_inputs:
            self._skip_current_step()

        # 检查是否有输出项，决定是否跳过此步骤
        has_outputs = bool(output_candidate_items)
        if not has_outputs and self.current_step_index() == 1:  # 如果当前是输出步骤且无输出
            self._skip_current_step()

        # 更新按钮状态以反映跳过后的当前步骤
        self._update_button_states()

    def _skip_current_step(self):
        """跳过当前步骤，移动到下一步"""
        current_index = self.current_step_index()
        if current_index < self.page_stack.count() - 1:
            self._current_step_index += 1
            self.page_stack.setCurrentIndex(self._current_step_index)
            # 不调用 _update_button_states()，因为外部逻辑会处理

    def get_selected_inputs(self):
        """获取输入选择页面的数据"""
        return self.input_page.get_selected_items()

    def get_selected_outputs(self):
        """获取输出选择页面的数据"""
        return self.output_page.get_selected_items()

    def get_project_name(self):
        """获取项目信息页面的项目名称"""
        return self.info_page.get_project_name()

    def get_readme_content(self):
        """获取项目信息页面的 README 内容"""
        return self.info_page.get_readme_content()

    def get_requirements(self):
        """获取项目信息页面的 requirements 内容"""
        return self.info_page.get_requirements()

    # 可以重写 validate_final_data 来验证所有步骤的最终数据
    def validate_final_data(self) -> bool:
        # 例如，检查项目名是否为空
        project_name = self.get_project_name()
        if not project_name:
            InfoBar.warning("无效项目名", "项目名称不能为空", parent=self, duration=2000)
            return False
        # 可以添加其他验证逻辑
        return True


class InputSelectionDialog(QWidget):  # 继承 QWidget
    def __init__(self, candidate_items, parent=None, current_selected_items=None):
        super().__init__(parent)
        self.candidate_items = candidate_items
        self.current_selected_items = current_selected_items or {}
        self.item_widgets = []

        layout = VBoxLayout(self)  # 使用 self 作为父级
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # 分组
        input_ports = [item for item in candidate_items if item["type"] == "组件输入"]
        component_params = [item for item in candidate_items if item["type"] == "组件超参数"]

        input_groups = defaultdict(list)
        param_groups = defaultdict(list)
        for item in input_ports:
            input_groups[(item["node_id"], item["node_name"])].append(item)
        for item in component_params:
            param_groups[(item["node_id"], item["node_name"])].append(item)

        # 分段
        segmented_widget = SegmentedWidget(self)
        segmented_widget.addItem("ports", "输入端口")
        segmented_widget.addItem("params", "组件参数")
        segmented_widget.setCurrentItem("ports")
        layout.addWidget(segmented_widget)
        btn_layout = QHBoxLayout()
        select_all = PushButton('全选')
        deselect_all = PushButton('全不选')
        select_all.clicked.connect(lambda: self._set_all_checked(True))
        deselect_all.clicked.connect(lambda: self._set_all_checked(False))
        btn_layout.addWidget(select_all)
        btn_layout.addWidget(deselect_all)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.scroll_ports = self._create_grouped_scroll(input_groups, is_input=True)
        self.scroll_params = self._create_grouped_scroll(param_groups, is_input=True)

        layout.addWidget(self.scroll_ports, 1)
        layout.addWidget(self.scroll_params, 1)
        self.scroll_params.hide()

        segmented_widget.currentItemChanged.connect(
            lambda name: (
                self.scroll_ports.setVisible(name == "ports"),
                self.scroll_params.setVisible(name == "params")
            )
        )

    def _create_grouped_scroll(self, groups, is_input=True):
        scroll_area = SmoothScrollArea()
        scroll_widget = QWidget()
        scroll_widget.setAttribute(Qt.WA_TranslucentBackground)
        scroll_area.setAttribute(Qt.WA_TranslucentBackground)
        scroll_area.setStyleSheet("background: transparent; border: none;")
        scroll_widget.setStyleSheet("background: transparent;")

        layout = VBoxLayout(scroll_widget)
        layout.setSpacing(16)
        layout.setContentsMargins(0, 0, 0, 0)

        if not groups:
            layout.addWidget(StrongBodyLabel("暂无项目"))
        else:
            for (node_id, node_name), items in groups.items():
                card = CardWidget()
                card_layout = VBoxLayout(card)
                card_layout.setContentsMargins(16, 16, 16, 16)

                title = StrongBodyLabel(node_name)
                card_layout.addWidget(title)

                for idx, item in enumerate(items):
                    row = QWidget()
                    row_layout = QHBoxLayout(row)
                    row_layout.setContentsMargins(0, 0, 0, 0)

                    cb = CheckBox()

                    is_selected = False
                    custom_key = ""
                    for spec_key, spec_details in self.current_selected_items.items():
                        if (spec_details.get('node_id') == item.get('node_id') and
                                ((spec_details.get('param_name') and spec_details.get('param_name') == item.get(
                                    'param_name')) or
                                 (spec_details.get('port_name') and spec_details.get('port_name') == item.get(
                                     'port_name')))):
                            is_selected = True
                            custom_key = spec_details.get('custom_key', spec_key)
                            break

                    cb.setChecked(is_selected)

                    name_label = QLabel(item["display_name"])
                    name_label.setStyleSheet("font-size: 14px;")

                    key_edit = LineEdit()
                    key_edit.setFixedWidth(120)
                    if custom_key:
                        key_edit.setText(custom_key)
                    else:
                        default_key = item.get("port_name") or item.get("param_name")
                        key_edit.setText(default_key)
                    key_edit.setPlaceholderText("输入key")

                    key_edit.setEnabled(is_selected)
                    cb.stateChanged.connect(lambda state, w=key_edit: w.setEnabled(state == Qt.Checked))

                    row_layout.addWidget(cb)
                    row_layout.addWidget(name_label)
                    row_layout.addStretch()
                    row_layout.addWidget(QLabel("Key:"))
                    row_layout.addWidget(key_edit)

                    card_layout.addWidget(row)
                    self.item_widgets.append((cb, key_edit, item))

                layout.addWidget(card)

        layout.addStretch()
        scroll_widget.setLayout(layout)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        return scroll_area

    def _set_all_checked(self, checked):
        for cb, key_edit, _ in self.item_widgets:
            cb.setChecked(checked)
            key_edit.setEnabled(checked)

    def get_selected_items(self):
        selected = []
        for cb, key_edit, item in self.item_widgets:
            if cb.isChecked():
                item = item.copy()
                item["custom_key"] = key_edit.text().strip() or f"input_{len(selected)}"
                selected.append(item)
        return selected


class OutputSelectionDialog(QWidget):  # 继承 QWidget
    def __init__(self, candidate_items, parent=None, current_selected_items=None):
        super().__init__(parent)
        self.candidate_items = candidate_items
        self.current_selected_items = current_selected_items or {}
        self.item_widgets = []

        layout = VBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        btn_layout = QHBoxLayout()
        select_all = PushButton('全选')
        deselect_all = PushButton('全不选')
        select_all.clicked.connect(lambda: self._set_all_checked(True))
        deselect_all.clicked.connect(lambda: self._set_all_checked(False))
        btn_layout.addWidget(select_all)
        btn_layout.addWidget(deselect_all)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        groups = defaultdict(list)
        for item in candidate_items:
            groups[(item["node_id"], item["node_name"])].append(item)

        scroll_area = SmoothScrollArea()
        scroll_widget = QWidget()
        scroll_widget.setAttribute(Qt.WA_TranslucentBackground)
        scroll_area.setAttribute(Qt.WA_TranslucentBackground)
        scroll_area.setStyleSheet("background: transparent; border: none;")
        scroll_widget.setStyleSheet("background: transparent;")

        inner_layout = VBoxLayout(scroll_widget)
        inner_layout.setSpacing(16)
        inner_layout.setContentsMargins(0, 0, 0, 0)

        if not groups:
            inner_layout.addWidget(StrongBodyLabel("暂无输出"))
        else:
            for (node_id, node_name), items in groups.items():
                card = CardWidget()
                card_layout = VBoxLayout(card)
                card_layout.setContentsMargins(16, 16, 16, 16)

                title = StrongBodyLabel(node_name)
                card_layout.addWidget(title)

                for idx, item in enumerate(items):
                    row = QWidget()
                    row_layout = QHBoxLayout(row)
                    row_layout.setContentsMargins(0, 0, 0, 0)

                    cb = CheckBox()

                    is_selected = False
                    custom_key = ""
                    for spec_key, spec_details in self.current_selected_items.items():
                        if (spec_details.get('node_id') == item.get('node_id') and
                                spec_details.get('output_name') == item.get('output_name')):
                            is_selected = True
                            custom_key = spec_details.get('custom_key', spec_key)
                            break

                    cb.setChecked(is_selected)

                    name_label = QLabel(item["display_name"])
                    name_label.setStyleSheet("font-size: 14px;")

                    key_edit = LineEdit()
                    key_edit.setFixedWidth(120)
                    if custom_key:
                        key_edit.setText(custom_key)
                    else:
                        default_key = item.get("output_name")
                        key_edit.setText(default_key)
                    key_edit.setPlaceholderText("输出key")

                    key_edit.setEnabled(is_selected)
                    cb.stateChanged.connect(lambda state, w=key_edit: w.setEnabled(state == Qt.Checked))

                    row_layout.addWidget(cb)
                    row_layout.addWidget(name_label)
                    row_layout.addStretch()
                    row_layout.addWidget(QLabel("Key:"))
                    row_layout.addWidget(key_edit)

                    card_layout.addWidget(row)
                    self.item_widgets.append((cb, key_edit, item))

                inner_layout.addWidget(card)

        inner_layout.addStretch()
        scroll_widget.setLayout(inner_layout)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)

        layout.addWidget(scroll_area, 1)

    def _set_all_checked(self, checked):
        for cb, key_edit, _ in self.item_widgets:
            cb.setChecked(checked)
            key_edit.setEnabled(checked)

    def get_selected_items(self):
        selected = []
        for cb, key_edit, item in self.item_widgets:
            if cb.isChecked():
                item = item.copy()
                item["custom_key"] = key_edit.text().strip() or f"output_{len(selected)}"
                selected.append(item)
        return selected


class ProjectExportDialog(QWidget):  # 继承 QWidget
    """项目导出配置对话框：项目名 + requirements 预览 + README 编辑"""

    def __init__(self, project_name: str = "", requirements: str = "", readme_func=None,
                 parent=None, get_input_func=None, get_output_func=None):
        super().__init__(parent)
        self.parent = parent
        self.readme_func = readme_func
        self.get_input_func = get_input_func
        self.get_output_func = get_output_func
        layout = VBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.project_name_edit = LineEdit()
        self.project_name_edit.setText(project_name)
        self.project_name_edit.setPlaceholderText("请输入项目名称")
        self.project_name_edit.setClearButtonEnabled(True)

        # 左侧：requirements 预览（只读）
        self.req_label = BodyLabel("依赖包 (requirements.txt)")
        self.req_edit = TextEdit()
        self.req_edit.setPlainText(requirements)

        # 右侧：README 编辑
        self.readme_label = BodyLabel("项目说明 (README.md)")
        self.readme_edit = TextEdit()

        # 布局
        top_layout = VBoxLayout()
        top_layout.addWidget(self.project_name_edit)

        # 中间区域：左右分栏
        splitter = ModernSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        left_widget = QWidget()
        left_layout = VBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.req_label)
        left_layout.addWidget(self.req_edit)

        right_widget = QWidget()
        right_layout = VBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.readme_label)
        right_layout.addWidget(self.readme_edit)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([200, 300])  # 默认比例

        layout.addLayout(top_layout)
        layout.addWidget(splitter, stretch=1)

    def update_readme_preview(self):
        if self.readme_func:
            self.readme_edit.setPlainText(
                self.readme_func(self.get_input_func(), self.get_output_func())
            )

    def showEvent(self, event):
        super().showEvent(event)
        self.update_readme_preview()

    def get_project_name(self):
        return self.project_name_edit.text().strip()

    def get_readme_content(self):
        return self.readme_edit.toPlainText()

    def get_requirements(self):
        return self.req_edit.toPlainText()