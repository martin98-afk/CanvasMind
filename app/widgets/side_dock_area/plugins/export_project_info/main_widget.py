# -*- coding: utf-8 -*-
import json
import os
from pathlib import Path

from PyQt5.QtWidgets import QVBoxLayout
from qfluentwidgets import BodyLabel, TextEdit, SubtitleLabel
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
        project_path = Path(project_path) if isinstance(project_path, str) else project_path
        self.spec = self._load_spec(project_path)
        # 清空旧内容
        while self.main_layout.count():
            item = self.main_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

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