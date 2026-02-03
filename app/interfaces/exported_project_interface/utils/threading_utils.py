# -*- coding: utf-8 -*-
import json
import os
import traceback
from pathlib import Path
from typing import List

from PyQt5.QtCore import QThread, pyqtSignal
from loguru import logger
from watchfiles import watch

from app.server_manager.mcp_server.mcp_adapter import McpWorkflowTool


# --- 新增：Watchfiles 监听线程 ---
class WatchfilesThread(QThread):
    projects_changed = pyqtSignal(list)  # [(change_type, path_str), ...]

    def __init__(self, watch_dirs: List[Path], parent=None):
        super().__init__(parent)
        self.watch_dirs = [str(p.resolve()) for p in watch_dirs]
        self._stop = False

    def run(self):
        try:
            for changes in watch(*self.watch_dirs, stop_event=None):
                if self._stop:
                    break
                # 只关注 model.workflow.json
                filtered = []
                for change_type, path in changes:
                    if os.path.basename(path) in ("model.workflow.json", "preview.png"):
                        logger.info(f"[Watchfiles] {change_type}: {path}")
                        filtered.append((change_type, path))
                if filtered:
                    self.projects_changed.emit(filtered)
        except Exception as e:
            logger.exception(f"Watchfiles error: {e}")

    def stop(self):
        self._stop = True


class ProjectRunnerThread(QThread):
    finished = pyqtSignal(dict, str)
    error = pyqtSignal(str)

    def __init__(self, project_path, parent=None):
        super().__init__(parent)
        self.project_path = project_path
        workflow_path = os.path.join(project_path, "model.workflow.json")
        if not os.path.exists(workflow_path):
            raise FileNotFoundError(f"未找到 model.workflow.json: {workflow_path}")
        with open(workflow_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            self.python_exe = data.get("runtime", {}).get("environment_exe")
            if not self.python_exe:
                raise ValueError("model.workflow.json 中未指定 environment_exe")

    def run(self):
        try:
            # 2. 执行 MCP 工具
            tool = McpWorkflowTool(self.project_path)
            outputs = tool.execute({})

            # 3. 模拟日志（可选）
            log_content = "✅ MCP 工具执行成功\n" + json.dumps(outputs, indent=2, ensure_ascii=False)

            self.finished.emit(outputs, log_content)

        except Exception as e:
            self.error.emit(traceback.format_exc())