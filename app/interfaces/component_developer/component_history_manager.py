# -*- coding: utf-8 -*-
import ast
import datetime
import json
import re
import shutil
import textwrap
import uuid
from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QSize
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QTableWidgetItem, QHeaderView,
    QFormLayout, QDialog, QTableWidget
)
from loguru import logger
from qfluentwidgets import (
    CardWidget, BodyLabel, LineEdit, PushButton,
    TableWidget, ComboBox, InfoBar, InfoBarPosition, MessageBox, FluentIcon, TextEdit, MessageBoxBase, SubtitleLabel,
    DoubleSpinBox, TransparentToolButton, SegmentedWidget, TransparentDropDownToolButton, Action, RoundMenu,
    SimpleCardWidget
)
from qfluentwidgets.window.stacked_widget import StackedWidget

from app.components.base import COMPONENT_IMPORT_CODE, PropertyType, ArgumentType, PropertyDefinition, ConnectionType
from app.scan_components import scan_components
from app.templates.component_templates import default_templates
from app.templates.component_templates.base import DEFAULT_NODE_TEMPLATE
from app.utils.utils import get_icon, canvas_file_dump_path
from app.widgets.ipython_console.ipython_console import IPythonConsoleManager  # 假设更新后的类名
from app.widgets.basic_widget.splitter import ModernSplitter
from app.widgets.ipython_console.variable_explorer import VariableExplorerWidget
from app.widgets.code_editor.code_editer import CodeEditorWidget
from app.widgets.node_widget.longtext_dialog import LongTextEditorDialog
from app.widgets.tree_widget.component_develop_tree import ComponentTreePanel


# --- 组件历史版本记录 ---
class ComponentHistoryManager:
    """管理组件的编辑历史记录"""
    HISTORY_DIR = canvas_file_dump_path() / "node_histories"
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE_SUFFIX = ".history.json"

    @staticmethod
    def get_history_file_path(component_file_path: Path) -> Path:
        """根据组件文件路径生成历史记录文件路径"""
        if not component_file_path or not component_file_path.suffix == '.py':
            return None
        return (ComponentHistoryManager.HISTORY_DIR /
                (component_file_path.name + ComponentHistoryManager.HISTORY_FILE_SUFFIX))

    @staticmethod
    def save_history(component_file_path: Path, component_name: str, code: str):
        """保存当前代码到历史记录，如果与上一版本相同则不保存"""
        history_file_path = ComponentHistoryManager.get_history_file_path(component_file_path)

        if not history_file_path:
            logger.error(f"无法为 {component_file_path} 生成历史记录文件路径")
            return
        histories = []
        if history_file_path.exists():
            try:
                with open(history_file_path, 'r', encoding='utf-8') as f:
                    histories = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError) as e:
                logger.error(f"读取历史记录文件失败: {e}")
        # 检查当前代码是否与最近一次保存的代码相同
        if histories and histories[-1].get('code') == code:
            logger.info("代码未改变，跳过保存历史记录。")
            return  # 如果代码相同，直接返回，不保存新版本
        # 生成版本号 (V + 递增数字)
        version_numbers = [int(h['version'][1:]) for h in histories if
                           h['version'].startswith('V') and h['version'][1:].isdigit()]
        next_version_num = max(version_numbers) + 1 if version_numbers else 1
        version = f"V{next_version_num}"
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        history_entry = {
            "version": version,
            "timestamp": timestamp,
            "component_name": component_name,
            "code": code  # 存储原始代码，不添加 COMPONENT_IMPORT_CODE
        }
        histories.append(history_entry)
        # 限制历史记录数量 (例如，只保留最近10条)
        max_histories = 10
        histories = histories[-max_histories:]
        try:
            with open(history_file_path, 'w', encoding='utf-8') as f:
                json.dump(histories, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"保存历史记录文件失败: {e}")

    @staticmethod
    def load_histories(component_file_path: Path) -> list:
        """加载指定组件的历史记录列表"""
        history_file_path = ComponentHistoryManager.get_history_file_path(component_file_path)
        if not history_file_path or not history_file_path.exists():
            return []
        try:
            with open(history_file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"加载历史记录文件失败: {e}")
            return []