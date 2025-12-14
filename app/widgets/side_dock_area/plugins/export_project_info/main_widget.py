# -*- coding: utf-8 -*-
import json
import os

from PyQt5.QtWidgets import QVBoxLayout
from qfluentwidgets import BodyLabel, TextEdit
from spyder.plugins.variableexplorer.widgets.texteditor import TextEditor

from app.utils.utils import get_icon
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition


class ProjectInfoTool(ToolWindow):
    name = "项目基本信息"
    icon = get_icon("配置")
    default_position = DockPosition.TOP  # ← 默认放在顶部

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(16)

    def _load_spec(self, project_path):
        spec_path = os.path.join(project_path, "project_spec.json")
        try:
            with open(spec_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {"inputs": {}}

    def refresh(self, project_path):
        self.spec = self._load_spec(project_path)
        # 清空旧内容
        while self.main_layout.count():
            item = self.main_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 来源画布
        canvas = "—"
        spec_path = project_path / "project_spec.json"
        if spec_path.exists():
            try:
                with open(spec_path, 'r', encoding='utf-8') as f:
                    spec = json.load(f)
                canvas = spec.get('graph_name', '—')
            except:
                pass
        self.main_layout.addWidget(BodyLabel(f"来源画布：{canvas}"))

        # 端口
        inputs = outputs = []
        if spec_path.exists():
            try:
                with open(spec_path, 'r', encoding='utf-8') as f:
                    spec = json.load(f)
                inputs = list(spec.get('inputs', {}).keys())
                outputs = list(spec.get('outputs', {}).keys())
            except:
                pass
        ports_text = f"输入：{', '.join(inputs) if inputs else '—'}；输出：{', '.join(outputs) if outputs else '—'}"
        self.main_layout.addWidget(BodyLabel(f"端口：{ports_text}"))

        # 依赖
        deps = "—"
        req_path = project_path / "requirements.txt"
        if req_path.exists():
            try:
                with open(req_path, 'r', encoding='utf-8') as f:
                    pkgs = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                    deps = ", ".join(pkgs[:12])
                    if len(pkgs) > 12:
                        deps += f" +{len(pkgs) - 12}"
            except:
                pass
        self.main_layout.addWidget(BodyLabel(f"依赖包：{deps}"))
        self.main_layout.addStretch()
        md_path = project_path / "README.md"
        if md_path.exists():
            try:
                with open(md_path, 'r', encoding='utf-8') as f:
                    md_content = f.read()
            except:
                md_content = "—"
        md_description = TextEdit(self)
        md_description.setMarkdown(md_content)
        md_description.setReadOnly(True)
        self.main_layout.addWidget(md_description, 1)