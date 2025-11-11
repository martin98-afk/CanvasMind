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
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QTableWidgetItem, QHeaderView,
    QFormLayout, QDialog, QTableWidget, QStackedWidget
)
from loguru import logger
from qfluentwidgets import (
    CardWidget, BodyLabel, LineEdit, PushButton,
    TableWidget, ComboBox, InfoBar, InfoBarPosition, MessageBox, FluentIcon, TextEdit, MessageBoxBase, SubtitleLabel,
    ToolButton, DoubleSpinBox, TransparentToolButton, SegmentedWidget
)
from qfluentwidgets.window.stacked_widget import StackedWidget

from app.components.base import COMPONENT_IMPORT_CODE, PropertyType, ArgumentType, PropertyDefinition, ConnectionType, \
    DEFAULT_NODE_TEMPLATE
from app.scan_components import scan_components
from app.utils.utils import get_icon, canvas_file_dump_path
from app.widgets.basic_widget.ipython_console import IPythonConsoleManager  # 假设更新后的类名
from app.widgets.basic_widget.style_sheet import StyleSheet
from app.widgets.basic_widget.variable_explorer import VariableExplorerWidget
from app.widgets.code_editer import CodeEditorWidget
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
            print(f"无法为 {component_file_path} 生成历史记录文件路径")
            return
        histories = []
        if history_file_path.exists():
            try:
                with open(history_file_path, 'r', encoding='utf-8') as f:
                    histories = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError) as e:
                print(f"读取历史记录文件失败: {e}")
        # 检查当前代码是否与最近一次保存的代码相同
        if histories and histories[-1].get('code') == code:
            print("代码未改变，跳过保存历史记录。")
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
            print(f"保存历史记录文件失败: {e}")

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
            print(f"加载历史记录文件失败: {e}")
            return []


class ComponentDeveloperWidget(QWidget):
    """组件开发主界面"""
    MODULE_TO_PACKAGE_MAP = {
        # 机器学习 / 计算机视觉
        'sklearn': 'scikit-learn',
        'skimage': 'scikit-image',
        'cv2': 'opencv-python',
        # 图像处理
        'PIL': 'Pillow',  # from PIL import Image
        # Web 解析
        'bs4': 'beautifulsoup4',
        # 配置与序列化
        'yaml': 'PyYAML',
        'dateutil': 'python-dateutil',  # from dateutil.parser import ...
        'jwt': 'PyJWT',  # import jwt
        # 加密
        'Crypto': 'pycryptodome',  # 注意：不是 pycrypto
        # 'Cryptodome': 'pycryptodomex',  # 如果用这个变体才需要
        # 串口通信
        'serial': 'pyserial',
        # Markdown 渲染
        'markdown': 'Markdown',  # 包名首字母大写
        # 文档解析
        'docx': 'python-docx',
        # Faker 数据生成
        'faker': 'Faker',  # 包名大写
        # 类型提示（可选）
        'typing_extensions': 'typing-extensions',  # 模块名下划线，包名中划线
        # TOML（第三方库）
        'tomli': 'tomli',
        'tomli_w': 'tomli-w',
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.home = parent
        self.setObjectName("ComponentDeveloperWidget")
        self._current_component_file = None
        self._current_component_code = ""  # 存储当前加载的代码
        self._setup_ui()
        self._connect_signals()
        self._load_existing_components()
        # --- 添加一个定时器用于延迟分析 ---
        self._analysis_timer = QTimer()
        self._analysis_timer.setSingleShot(True)
        self._analysis_timer.timeout.connect(self._analyze_code_for_requirements)
        # --- 添加一个标志，防止循环更新 ---
        self._updating_requirements_from_analysis = False

    def _setup_ui(self):
        StyleSheet.COMPONENT_DEVELOPER.apply(self)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        # 左侧：组件树和开发区域
        main_splitter = QSplitter(Qt.Horizontal)
        self_layout = QVBoxLayout(self)
        self_layout.setContentsMargins(0, 0, 0, 0)
        self_layout.setSpacing(0)
        # --- 修改：左侧：组件树 ---
        self.component_tree_panel = ComponentTreePanel(self)
        self.component_tree = self.component_tree_panel.tree  # 保留对 tree 的直接引用（如果已有代码依赖）
        main_splitter.addWidget(self.component_tree_panel)  # 将新的左侧容器添加到    主分割器
        # --- 修改结束 ---
        # 代码编辑框
        code_widget = QWidget(self)
        code_layout = QVBoxLayout(code_widget)
        code_layout.setContentsMargins(0, 0, 0, 0)
        # 代码编辑器
        self.code_editor = CodeEditorWidget(self, self.home.package_manager.get_current_python_exe())
        # 保存按钮
        save_layout = QHBoxLayout()
        code_btn = TransparentToolButton(get_icon("代码执行"), parent=self)
        code_btn.setIconSize(QSize(20, 25))
        code_btn.setFixedSize(20, 25)
        save_layout.addWidget(code_btn)
        save_layout.addWidget(BodyLabel("组件代码:"))
        # --- 新增结束 ---
        save_layout.addStretch()
        # --- 新增：运行按钮 ---
        run_btn = TransparentToolButton(FluentIcon.PLAY, parent=self)
        run_btn.clicked.connect(self._run_component_code)
        save_layout.addWidget(run_btn)
        save_btn = TransparentToolButton(FluentIcon.SAVE, parent=self)
        save_btn.clicked.connect(lambda: self._save_component(True))
        cancel_btn = TransparentToolButton(FluentIcon.CLOSE, parent=self)
        cancel_btn.clicked.connect(self._cancel_edit)
        save_layout.addWidget(save_btn)
        save_layout.addWidget(cancel_btn)
        code_layout.addLayout(save_layout)
        code_layout.addWidget(self.code_editor, stretch=1)
        main_splitter.addWidget(code_widget)
        # 右侧：组件属性
        right_widgets = QWidget(self)
        vBoxLayout = QVBoxLayout(right_widgets)
        vBoxLayout.setContentsMargins(0, 0, 0, 0)
        vBoxLayout.setSpacing(0)  # 可选：移除组件之间的间距（如果不需要）
        self.pivot = SegmentedWidget(self)
        self.stackedWidget = StackedWidget(self)
        # 组件属性
        info_interface = QWidget()
        info_layout = QVBoxLayout(info_interface)
        info_layout.setContentsMargins(0, 0, 0, 0)
        # --- 基本信息卡片 ---
        basic_info_widget = CardWidget()
        # 使用水平布局来并排放置信息和依赖
        basic_info_h_layout = QHBoxLayout(basic_info_widget)
        basic_info_h_layout.setContentsMargins(0, 0, 0, 0)  # 设置整体边距
        # 左侧：名称、分类、描述
        left_form_widget = QWidget(self)  # 容器用于左侧表单
        left_form_layout = QFormLayout(left_form_widget)
        self.name_edit = LineEdit()
        self.category_edit = LineEdit()
        self.description_edit = LineEdit()
        left_form_layout.addRow(BodyLabel("组件基本信息:"))
        left_form_layout.addRow(BodyLabel("组件名称:"), self.name_edit)
        left_form_layout.addRow(BodyLabel("组件分类:"), self.category_edit)
        left_form_layout.addRow(BodyLabel("组件描述:"), self.description_edit)
        # 右侧：依赖 requirements
        right_req_widget = QWidget(self)  # 容器用于右侧依赖
        right_req_layout = QVBoxLayout(right_req_widget)  # 垂直布局放标签和编辑器
        right_req_layout.addWidget(BodyLabel("组件依赖:"))  # 标签
        self.requirements_edit = TextEdit()  # 使用 qfluentwidgets 的 TextEdit
        self.requirements_edit.setFixedHeight(115)  # 设置固定高度，或使用 setMaximumHeight
        right_req_layout.addWidget(self.requirements_edit)  # 编辑器
        # 将左右两个容器添加到水平布局
        basic_info_h_layout.addWidget(left_form_widget)
        basic_info_h_layout.addWidget(right_req_widget)
        # 设置拉伸因子，让左侧稍微窄一些，右侧稍微宽一些，或者相等
        basic_info_h_layout.setStretch(0, 1)  # 左侧 (信息)
        basic_info_h_layout.setStretch(1, 1)  # 右侧 (依赖)
        info_layout.addWidget(basic_info_widget)
        # 端口编辑器（上下布局）
        port_splitter = QSplitter(Qt.Horizontal)
        # 输入输出端口编辑器
        self.input_port_editor = PortEditorWidget("input")
        self.output_port_editor = PortEditorWidget("output")
        port_splitter.addWidget(self.input_port_editor)
        port_splitter.addWidget(self.output_port_editor)
        port_splitter.setSizes([200, 100])  # 初始大小
        info_layout.addWidget(port_splitter, stretch=1)
        # 属性编辑器
        self.property_editor = PropertyEditorWidget(self)
        info_layout.addWidget(self.property_editor, stretch=1)
        self.addSubInterface(info_interface, "component_info", "组件属性", get_icon("配置"))

        # --- Debug 区域：包含 CollectionEditor 和 IPython Console --
        # 创建中央部件
        central_widget = QWidget(self)
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)

        # 创建Console管理器
        self.console_manager = IPythonConsoleManager(
            parent=self, package_manager=self.home.package_manager
        )

        # 创建变量浏览器
        self.var_explorer = VariableExplorerWidget(
            parent=self, kernel_manager=None  # 先不设置内核管理器
        )
        # 连接控制台和变量浏览器
        self.console_manager.tab_bar.currentChanged.connect(
            self._on_console_changed
        )

        # 初始化第一个控制台的内核管理器
        self._on_console_changed(0)

        # 创建垂直分割器
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.var_explorer)
        splitter.addWidget(self.console_manager)
        splitter.setSizes([300, 400])  # 变量浏览器较小，控制台较大

        central_layout.addWidget(splitter)
        self.addSubInterface(central_widget, "debug_interface", "组件调试", get_icon("调试"))

        # --- 新增：历史记录卡片 ---
        self.history_card = CardWidget(self)
        history_card_layout = QVBoxLayout(self.history_card)
        history_card_layout.setContentsMargins(10, 10, 10, 10)  # 设置内边距
        history_label = BodyLabel("编辑历史:")
        self.history_table = TableWidget(self)
        self.history_table.setColumnCount(2)  # 只显示版本和时间
        self.history_table.setHorizontalHeaderLabels(["版本", "保存时间"])
        self.history_table.verticalHeader().hide()
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.history_table.setSelectionBehavior(QTableWidget.SelectItems)
        self.history_table.setSelectionMode(QTableWidget.ContiguousSelection)
        # 设置版本列宽度自适应内容，时间列拉伸填充
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)  # 版本列
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)  # 时间列
        # 连接双击信号
        self.history_table.itemDoubleClicked.connect(self._load_history_code)
        history_card_layout.addWidget(history_label)
        history_card_layout.addWidget(self.history_table)
        self.addSubInterface(self.history_card, "history_card", "组件历史", FluentIcon.HISTORY)
        self.pivot.setCurrentItem("component_info")
        vBoxLayout.addWidget(self.pivot)
        vBoxLayout.addWidget(self.stackedWidget, 1)
        main_splitter.addWidget(right_widgets)
        # 先设置 stretch，让左侧可收缩
        main_splitter.setStretchFactor(0, 0)  # 左侧不拉伸
        main_splitter.setStretchFactor(1, 1)  # 中间拉伸
        main_splitter.setStretchFactor(2, 1)  # 右侧拉伸
        # 再设置一个“合理但小”的初始尺寸（避免 10 太小被忽略）
        main_splitter.setSizes([50, 450, 450])  # 50 比 10 更可能生效
        layout.addWidget(main_splitter)

    def _on_console_changed(self, index):
        """控制台切换时更新变量浏览器"""
        kernel_manager = self.console_manager.get_current_kernel_manager()
        if kernel_manager:
            self.var_explorer.set_kernel_manager(kernel_manager)
            self.var_explorer.start_auto_refresh()

    def _connect_signals(self):
        """连接信号"""
        self.component_tree.component_selected.connect(self._load_component)
        self.component_tree.component_created.connect(self._on_component_created)
        self.component_tree.component_pasted.connect(self._on_component_pasted)
        # 连接编辑器改变信号
        self.input_port_editor.ports_changed.connect(self._sync_ports_to_code)
        self.output_port_editor.ports_changed.connect(self._sync_ports_to_code)  # 修复：连接输出端口信号
        self.property_editor.properties_changed.connect(self._sync_properties_to_code)
        self.code_editor.code_changed.connect(self._on_code_text_changed)
        # 连接基本信息改变信号
        self.name_edit.textChanged.connect(self._sync_basic_info_to_code)
        self.category_edit.textChanged.connect(self._sync_basic_info_to_code)
        self.description_edit.textChanged.connect(self._sync_basic_info_to_code)
        self.requirements_edit.textChanged.connect(self._sync_basic_info_to_code)
        self.requirements_edit.textChanged.connect(self._on_requirements_text_changed)

    def addSubInterface(self, widget, objectName: str, text: str, icon: QIcon):
        widget.setObjectName(objectName)
        self.stackedWidget.addWidget(widget)
        # 使用全局唯一的 objectName 作为路由键
        self.pivot.addItem(
            routeKey=objectName,
            text=text,
            onClick=lambda: self.stackedWidget.setCurrentWidget(widget),
            icon=icon
        )

    def _load_existing_components(self):
        """加载现有组件"""
        try:
            component_map, file_map = scan_components()
            self.component_tree.load_components(component_map, file_map)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._show_error(f"加载组件失败: {e}")

    def _on_component_created(self, component_info):
        """组件创建回调"""
        self._create_new_component(component_info)
        self._save_component()

    def _on_component_pasted(self):
        """组件粘贴回调"""
        self._load_component(self.component_tree._copied_component)
        self._save_component(delete_original_file=False)

    def extract_class_source_from_file(self, file_path: Path, class_name: str) -> str:
        """从文件中提取指定类的源码（使用 ast）"""
        try:
            source_code = file_path.read_text(encoding='utf-8')
            source_lines = source_code.splitlines(keepends=True)
            start = len(COMPONENT_IMPORT_CODE.split("\n")) - 1
            return ''.join(source_lines[start:])
        except Exception as e:
            logger.warning(f"AST extraction failed for {file_path}:{class_name} - {e}")
        return ""

    def _load_component_filepath(self, component_path: Path):
        """根据文件路径重载组件"""
        file_map = {value: key for key, value in self.component_tree._file_map.items()}
        full_path = file_map.get(component_path)
        self._load_component(self.component_tree._components[full_path])

    def _load_component(self, component):
        """加载组件到编辑器"""
        try:
            # 基本信息
            self.name_edit.setText(getattr(component, 'name', ''))
            self.category_edit.setText(getattr(component, 'category', ''))
            self.description_edit.setText(getattr(component, 'description', ''))
            self.requirements_edit.setText(getattr(component, 'requirements', '').replace(',', '\n'))
            # 加载输入端口
            inputs = getattr(component, 'inputs', [])
            self.input_port_editor.set_ports([
                {
                    "name": port.name,
                    "label": port.label,
                    "type": getattr(port, 'type', ArgumentType.TEXT),
                    "connection": getattr(port, 'connection', ConnectionType.SINGLE),
                }
                for port in inputs
            ])
            # 加载输出端口
            outputs = getattr(component, 'outputs', [])
            self.output_port_editor.set_ports([
                {"name": port.name, "label": port.label, "type": getattr(port, 'type', 'text')}
                for port in outputs
            ])
            # 加载属性
            properties = getattr(component, 'properties', {})
            self.property_editor.set_properties(properties)
            # 加载代码
            try:
                source_file = getattr(component, '_source_file', None)
                source_code = self.extract_class_source_from_file(source_file, component.__name__)
                self._current_component_file = Path(source_file)
                self._current_component_code = source_code  # 存储当前加载的代码
                self.code_editor.set_code(source_code)
            except:
                # 如果无法获取源码，使用默认模板
                template = DEFAULT_NODE_TEMPLATE
                template = template.replace("Component", component.__name__)
                template = template.replace("我的组件", getattr(component, 'name', ''))
                template = template.replace("数据处理", getattr(component, 'category', ''))
                template = template.replace("这是一个示例组件", getattr(component, 'description', ''))
                self._current_component_code = template  # 存储当前加载的代码
                self.code_editor.replace_text_preserving_view(template)
                # 对于新建的，原始文件路径为 None
                self._current_component_file = None
            self._sync_basic_info_to_code()
            # --- 新增：加载历史记录列表 ---
            if self._current_component_file:
                self._load_history_list(self._current_component_file)
            else:
                self.history_table.setRowCount(0)  # 如果没有文件路径，清空历史列表
            # --- 新增结束 ---
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._show_error(f"加载组件失败: {str(e)}")

    def _create_new_component(self, component_info):
        """创建新组件"""
        self.name_edit.setText(component_info["name"])
        self.category_edit.setText(component_info["category"])
        self.description_edit.setText(component_info["description"])
        # 清空编辑器
        self.input_port_editor.set_ports([])
        self.output_port_editor.set_ports([])
        self.property_editor.set_properties({})
        # 生成代码模板
        template = DEFAULT_NODE_TEMPLATE
        template = template.replace("我的组件", component_info["name"])
        template = template.replace("数据处理", component_info["category"])
        template = template.replace("这是一个示例组件", component_info["description"])
        self._current_component_code = template  # 存储当前加载的代码
        self.code_editor.replace_text_preserving_view(template)
        # 对于新建的，原始文件路径为 None
        self._current_component_file = None
        current_code = self.code_editor.get_code()
        if not current_code.strip():
            return
        # 解析并更新基本信息
        updated_code = self._update_basic_info_in_code(
            current_code,
            self.name_edit.text(),
            self.category_edit.text(),
            self.description_edit.text(),
            self.requirements_edit.toPlainText().replace("\n", ",")
        )
        if updated_code != current_code:
            self.code_editor.suspend_sync()
            try:
                self.code_editor.replace_text_preserving_view(updated_code)
            finally:
                self.code_editor.resume_sync()

    def _run_component_code(self):
        """运行当前编辑器中的组件代码"""
        self.pivot.setCurrentItem("debug_interface")
        self.stackedWidget.setCurrentIndex(1)
        local_import = """# -*- coding: utf-8 -*-
try:
    from app.components.base import *
except:
    from _internal.app.components.base import *
"""
        current_code = local_import + self.code_editor.get_code()
        if not current_code.strip():
            self._show_warning("代码编辑器为空，无法运行！")
            return
        current_console = self.console_manager.get_current_console()
        if current_console:
            current_console.execute_code(current_code)
        else:
            self._show_error("当前控制台未启动或无 kernel 客户端！")

    def _sync_ports_to_code(self):
        """同步端口到代码"""
        try:
            # 获取当前代码
            current_code = self.code_editor.get_code()
            if not current_code.strip():
                return
            # 解析并更新端口定义
            updated_code = self._update_ports_in_code(
                current_code,
                self.input_port_editor.get_ports(),  # 修复：传入输入端口
                self.output_port_editor.get_ports()  # 修复：传入输出端口
            )
            # 更新代码编辑器（非破坏式，保持撤销/选择）
            if updated_code != current_code:
                self.code_editor.suspend_sync()
                try:
                    self.code_editor.replace_text_preserving_view(updated_code)
                finally:
                    self.code_editor.resume_sync()
        except Exception as e:
            print(f"同步端口到代码失败: {e}")

    def _sync_properties_to_code(self):
        """同步属性到代码"""
        try:
            # 获取当前代码
            current_code = self.code_editor.get_code()
            if not current_code.strip():
                return
            # 解析并更新属性定义
            updated_code = self._update_properties_in_code(
                current_code,
                self.property_editor.get_properties()
            )
            # 更新代码编辑器（非破坏式，保持撤销/选择）
            if updated_code != current_code:
                self.code_editor.suspend_sync()
                try:
                    self.code_editor.replace_text_preserving_view(updated_code)
                finally:
                    self.code_editor.resume_sync()
        except Exception as e:
            print(f"同步属性到代码失败: {e}")

    def _sync_basic_info_to_code(self):
        """同步基本信息到代码"""
        try:
            # 获取当前代码
            current_code = self.code_editor.get_code()
            if not current_code.strip():
                return
            # 解析并更新基本信息
            updated_code = self._update_basic_info_in_code(
                current_code,
                self.name_edit.text(),
                self.category_edit.text(),
                self.description_edit.text(),
                self.requirements_edit.toPlainText().replace("\n", ",")
            )
            # 更新代码编辑器（非破坏式，保持撤销/选择）
            if updated_code != current_code:
                self.code_editor.suspend_sync()
                try:
                    self.code_editor.replace_text_preserving_view(updated_code)
                finally:
                    self.code_editor.resume_sync()
        except Exception as e:
            print(f"同步基本信息到代码失败: {e}")

    def _update_ports_in_code(self, code, input_ports, output_ports):
        """更新代码中的端口定义"""
        lines = code.split('\n')
        new_lines = []
        i = 0
        inputs_replaced = False
        outputs_replaced = False
        while i < len(lines):
            line = lines[i]
            # 查找 inputs 或 outputs 定义的开始行
            if (not inputs_replaced and re.search(r'^\s*inputs\s*=\s*', line)
                    and ('[' in line or '[]' in line)):
                new_lines.append("    inputs = [")
                for port in input_ports:
                    new_lines.append(
                        f"        PortDefinition(name=\"{port['name']}\", label=\"{port['label']}\", "
                        f"type=ArgumentType.{port['type'].name}, "
                        f"connection=ConnectionType.{port.get('connection', ConnectionType.SINGLE.value).name}),")
                new_lines.append("    ]")
                inputs_replaced = True
                # 跳过原 inputs 定义的其余行
                if '[]' not in line:  # 如果不是空列表
                    bracket_count = line.count('[') - line.count(']')
                    j = i + 1
                    while j < len(lines) and bracket_count > 0:
                        bracket_count += lines[j].count('[') - lines[j].count(']')
                        j += 1
                    i = j
                else:  # 如果是空列表 [ ... ]
                    # 查找下一个非注释、非空白行，判断是否是 ] 结尾
                    j = i + 1
                    while j < len(lines) and (not lines[j].strip() or lines[j].strip().startswith('#')):
                        j += 1
                    if j < len(lines) and lines[j].strip() == ']':
                        i = j + 1
                    else:
                        i += 1  # 如果格式不标准，只跳过当前行
            elif (not outputs_replaced and re.search(r'^\s*outputs\s*=\s*', line) and
                  ('[' in line or '[]' in line)):
                new_lines.append("    outputs = [")
                for port in output_ports:
                    new_lines.append(
                        f"        PortDefinition(name=\"{port['name']}\", label=\"{port['label']}\", type=ArgumentType.{port['type'].name}),")
                new_lines.append("    ]")
                outputs_replaced = True
                # 跳过原 outputs 定义的其余行
                if '[]' not in line:  # 如果不是空列表
                    bracket_count = line.count('[') - line.count(']')
                    j = i + 1
                    while j < len(lines) and bracket_count > 0:
                        bracket_count += lines[j].count('[') - lines[j].count(']')
                        j += 1
                    i = j
                else:  # 如果是空列表 [ ... ]
                    # 查找下一个非注释、非空白行，判断是否是 ] 结尾
                    j = i + 1
                    while j < len(lines) and (not lines[j].strip() or lines[j].strip().startswith('#')):
                        j += 1
                    if j < len(lines) and lines[j].strip() == ']':
                        i = j + 1
                    else:
                        i += 1  # 如果格式不标准，只跳过当前行
            else:
                new_lines.append(line)
                i += 1
        # 如果代码中没有找到 inputs 或 outputs 行，则添加它们
        if not inputs_replaced:
            # 找到类定义开始后，插入空的 inputs 定义
            for idx, l in enumerate(new_lines):
                if l.strip().startswith('class ') and not any(
                        re.search(r'^\s*inputs\s*=\s*', ll) for ll in new_lines[idx:]):
                    new_lines.insert(idx + 1, "    inputs = []")
                    break
        if not outputs_replaced:
            # 找到类定义开始后，插入空的 outputs 定义
            for idx, l in enumerate(new_lines):
                if l.strip().startswith('class ') and not any(
                        re.search(r'^\s*outputs\s*=\s*', ll) for ll in new_lines[idx:]):
                    new_lines.insert(idx + 2, "    outputs = []")  # 假设 inputs 已存在或刚插入
                    break
        return '\n'.join(new_lines)

    def _update_properties_in_code(self, code, properties):
        """更新代码中的属性定义（兼容 dict 和 PropertyDefinition 对象，支持 RANGE / LONGTEXT）"""
        try:
            lines = code.split('\n')
            new_lines = []
            i = 0
            properties_replaced = False
            while i < len(lines):
                line = lines[i]
                if not properties_replaced and re.search(r'^\s*properties\s*=\s*', line) and (
                        '{' in line or '{}' in line):
                    new_lines.append("    properties = {")
                    for prop_name, prop_def in properties.items():
                        # ✅ 统一提取字段：兼容 dict 和对象
                        if isinstance(prop_def, dict):
                            prop_type = prop_def.get('type', PropertyType.TEXT)
                            default_value = prop_def.get('default', '')
                            label = prop_def.get('label', prop_name)
                            choices = prop_def.get('choices', [])
                            schema = prop_def.get('schema', {})
                            min_val = prop_def.get('min', 0)
                            max_val = prop_def.get('max', 100)
                            step_val = prop_def.get('step', 1)
                        else:
                            prop_type = getattr(prop_def, 'type', PropertyType.TEXT)
                            default_value = getattr(prop_def, 'default', '')
                            label = getattr(prop_def, 'label', prop_name)
                            choices = getattr(prop_def, 'choices', [])
                            schema = getattr(prop_def, 'schema', {})
                            min_val = getattr(prop_def, 'min', 0)
                            max_val = getattr(prop_def, 'max', 100)
                            step_val = getattr(prop_def, 'step', 1)
                        # 处理 DYNAMICFORM
                        if prop_type == PropertyType.DYNAMICFORM:
                            new_lines.append(f'        "{prop_name}": PropertyDefinition(')
                            new_lines.append(f'            type=PropertyType.DYNAMICFORM,')
                            new_lines.append(f'            label="{label}",')
                            if schema:
                                new_lines.append('            schema={')
                                for field_name, field_def in schema.items():
                                    if not isinstance(field_def, dict):
                                        field_def = field_def.dict()
                                    field_type = field_def.get('type', PropertyType.TEXT)
                                    field_default = field_def.get('default', '')
                                    field_label = field_def.get('label', field_name)
                                    field_choices = field_def.get('choices', [])
                                    new_lines.append(f'                "{field_name}": PropertyDefinition(')
                                    new_lines.append(f'                    type=PropertyType.{field_type.name},')
                                    if field_type == PropertyType.INT:
                                        fv = str(int(field_default)) if field_default else "0"
                                    elif field_type == PropertyType.FLOAT:
                                        fv = str(float(field_default)) if field_default else "0.0"
                                    elif field_type == PropertyType.BOOL:
                                        fv = "True" if str(field_default).lower() in ("true", "1", "yes") else "False"
                                    else:
                                        fv = f'"{field_default}"'
                                    new_lines.append(f'                    default={fv},')
                                    new_lines.append(f'                    label="{field_label}",')
                                    if field_type == PropertyType.CHOICE and field_choices:
                                        choices_str = ', '.join([f'"{c}"' for c in field_choices])
                                        new_lines.append(f'                    choices=[{choices_str}]')
                                    elif field_type == PropertyType.RANGE:
                                        new_lines.append(f'                    min={field_def.get("min", 0)},')
                                        new_lines.append(f'                    max={field_def.get("max", 100)},')
                                        new_lines.append(f'                    step={field_def.get("step", 1)}')
                                    new_lines.append('                ),')
                                new_lines.append('            }')
                            new_lines.append('        ),')
                        else:
                            # 普通类型（包括 RANGE / LONGTEXT）
                            if prop_type == PropertyType.INT:
                                dv = str(int(default_value)) if default_value else "0"
                            elif prop_type == PropertyType.FLOAT:
                                dv = str(float(default_value)) if default_value else "0.0"
                            elif prop_type == PropertyType.BOOL:
                                dv = "True" if str(default_value).lower() in ("true", "1", "yes") else "False"
                            elif prop_type == PropertyType.LONGTEXT:
                                # ✅ 使用三引号包裹长文本
                                if default_value:
                                    # 转义三引号（简单处理）
                                    safe_text = default_value.replace('"""', '\\"\\"\\"')
                                    # 使用 textwrap.dedent 保持缩进整洁
                                    dv = '"""' + textwrap.dedent(safe_text) + '"""'
                                else:
                                    dv = '""""""'  # 空三引号
                            else:
                                dv = f'"{default_value}"'
                            new_lines.append(f'        "{prop_name}": PropertyDefinition(')
                            new_lines.append(f'            type=PropertyType.{prop_type.name},')
                            new_lines.append(f'            default={dv},')
                            new_lines.append(f'            label="{label}",')
                            # CHOICE 的 choices
                            if prop_type == PropertyType.CHOICE and choices:
                                choices_str = ', '.join([f'"{c}"' for c in choices])
                                new_lines.append(f'            choices=[{choices_str}]')
                            # RANGE 的 min, max, step
                            if prop_type == PropertyType.RANGE:
                                new_lines.append(f'            min={min_val},')
                                new_lines.append(f'            max={max_val},')
                                new_lines.append(f'            step={step_val},')
                            new_lines.append('        ),')
                    new_lines.append("    }")
                    properties_replaced = True
                    # 跳过原 properties 块（略）
                    if '{}' not in line:
                        bracket_count = line.count('{') - line.count('}')
                        j = i + 1
                        while j < len(lines) and bracket_count > 0:
                            bracket_count += lines[j].count('{') - lines[j].count('}')
                            j += 1
                        i = j
                    else:
                        j = i + 1
                        while j < len(lines) and (not lines[j].strip() or lines[j].strip().startswith('#')):
                            j += 1
                        if j < len(lines) and lines[j].strip() == '}':
                            i = j + 1
                        else:
                            i += 1
                else:
                    new_lines.append(line)
                    i += 1
            # 如果未找到 properties，插入默认（略）
            if not properties_replaced:
                for idx, l in enumerate(new_lines):
                    if l.strip().startswith('class ') and not any(
                            re.search(r'^\s*properties\s*=\s*', ll) for ll in new_lines[idx:]):
                        new_lines.insert(idx + 3, "    properties = {}")
                        break
            return '\n'.join(new_lines)
        except Exception as e:
            print(f"_update_properties_in_code error: {e}")
            import traceback
            traceback.print_exc()
            return code

    def _update_basic_info_in_code(self, code, name, category, description, requirements):
        """更新代码中的基本信息"""
        try:
            lines = code.split('\n')
            new_lines = []
            for i, line in enumerate(lines):
                if re.search(r'^\s*name\s*=\s*', line):
                    new_lines.append(f'    name = "{name}"')
                elif re.search(r'^\s*category\s*=\s*', line):
                    new_lines.append(f'    category = "{category}"')
                elif re.search(r'^\s*description\s*=\s*', line):
                    new_lines.append(f'    description = "{description}"')
                elif re.search(r'^\s*requirements\s*=\s*', line):
                    new_lines.append(f'    requirements = "{requirements}"')
                else:
                    new_lines.append(line)
                if ("requirements" not in code and len(requirements) > 0 and i > 1 and
                        re.search(r'^\s*description\s*=\s*', line)):
                    new_lines.append(f'    requirements = "{requirements}"')
            return '\n'.join(new_lines)
        except:
            return code

    # --- 新增：代码文本改变时启动分析定时器 ---
    def _on_code_text_changed(self):
        # 如果当前正在根据分析更新 requirements，不要再次触发分析
        if not self._updating_requirements_from_analysis:
            self._analysis_timer.start(2000)  # 2秒后分析

    # --- 新增：requirements 文本改变时停止分析定时器 ---
    def _on_requirements_text_changed(self):
        self._analysis_timer.stop()

    def _analyze_code_for_requirements(self):
        code = self.code_editor.get_code()
        if not code.strip():
            return
        try:
            tree = ast.parse(code)
        except SyntaxError:
            print("代码语法错误，无法分析依赖。")
            return

        imported_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_modules.add(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_modules.add(node.module.split('.')[0])

        builtin_modules = set(
            ['__future__', 'abc', 'aifc', 'argparse', 'array', 'ast', 'asynchat', 'asyncio', 'asyncore', 'atexit',
             'audioop', 'base64', 'bdb', 'binascii', 'binhex', 'bisect', 'builtins', 'bz2', 'cProfile', 'calendar',
             'cgi', 'cgitb', 'chunk', 'cmath', 'cmd', 'code', 'codecs', 'codeop', 'collections', 'colorsys',
             'compileall', 'concurrent', 'configparser', 'contextlib', 'contextvars', 'copy', 'copyreg', 'crypt', 'csv',
             'ctypes', 'curses', 'dataclasses', 'datetime', 'dbm', 'decimal', 'difflib', 'dis', 'distutils', 'doctest',
             'email', 'encodings', 'ensurepip', 'enum', 'errno', 'faulthandler', 'fcntl', 'filecmp', 'fileinput',
             'fnmatch', 'formatter', 'fractions', 'ftplib', 'functools', 'gc', 'getopt', 'getpass', 'gettext', 'glob',
             'graphlib', 'grp', 'gzip', 'hashlib', 'heapq', 'hmac', 'html', 'http', 'idlelib', 'imaplib', 'imghdr',
             'imp', 'importlib', 'inspect', 'io', 'ipaddress', 'itertools', 'json', 'keyword', 'lib2to3', 'linecache',
             'locale', 'logging', 'lzma', 'mailbox', 'mailcap', 'marshal', 'math', 'mimetypes', 'mmap', 'modulefinder',
             'msilib', 'msvcrt', 'multiprocessing', 'netrc', 'nis', 'nntplib', 'ntpath', 'numbers', 'operator',
             'optparse', 'os', 'ossaudiodev', 'parser', 'pathlib', 'pdb', 'pickle', 'pickletools', 'pipes', 'pkgutil',
             'platform', 'plistlib', 'poplib', 'posix', 'posixpath', 'pprint', 'profile', 'pstats', 'pty', 'pwd',
             'py_compile', 'pyclbr', 'pydoc', 'queue', 'quopri', 'random', 're', 'readline', 'reprlib', 'resource',
             'rlcompleter', 'runpy', 'sched', 'secrets', 'select', 'selectors', 'shelve', 'shlex', 'shutil', 'signal',
             'site', 'smtpd', 'smtplib', 'sndhdr', 'socket', 'socketserver', 'spwd', 'sqlite3', 'sre', 'sre_compile',
             'sre_constants', 'sre_parse', 'ssl', 'stat', 'statistics', 'string', 'stringprep', 'struct', 'subprocess',
             'sunau', 'symbol', 'symtable', 'sys', 'sysconfig', 'syslog', 'tabnanny', 'tarfile', 'telnetlib',
             'tempfile', 'termios', 'test', 'textwrap', 'threading', 'time', 'timeit', 'tkinter', 'token', 'tokenize',
             'trace', 'traceback', 'tracemalloc', 'tty', 'turtle', 'turtledemo', 'types', 'typing', 'unicodedata',
             'unittest', 'urllib', 'uu', 'uuid', 'venv', 'warnings', 'wave', 'weakref', 'webbrowser', 'winreg',
             'winsound', 'wsgiref', 'xdrlib', 'xml', 'xmlrpc', 'zipapp', 'zipfile', 'zipimport', 'zlib', 'zoneinfo']
        )

        external_packages = imported_modules - builtin_modules
        resolved_packages = {
            self.MODULE_TO_PACKAGE_MAP.get(mod, mod)
            for mod in external_packages
        }

        current_text = self.requirements_edit.toPlainText()
        if not current_text.strip() and not resolved_packages:
            return  # 空代码 + 空依赖，无需更新

        # 解析当前依赖
        other_lines, package_lines = self._parse_requirements_lines(current_text)
        current_pkg_names = set(package_lines.keys())

        # 代码中需要的包（标准化）
        needed_pkgs = {pkg.lower() for pkg in resolved_packages}

        # 要保留的包行：代码中仍需要的
        kept_package_lines = [
            package_lines[pkg] for pkg in needed_pkgs if pkg in package_lines
        ]
        # 新增的包（无版本）
        new_pkgs = needed_pkgs - current_pkg_names
        new_package_lines = sorted([pkg for pkg in resolved_packages if pkg.lower() in new_pkgs])

        # 重建内容：其他行 + 保留的包 + 新包
        all_lines = other_lines + kept_package_lines + new_package_lines
        updated_text = '\n'.join(all_lines)

        # 避免无意义更新
        if updated_text == current_text:
            return

        # 更新 UI（保留你的光标逻辑）
        if not self._updating_requirements_from_analysis:
            self._updating_requirements_from_analysis = True
            code_cursor = self.code_editor.code_editor.textCursor()
            pos = code_cursor.position()
            self.requirements_edit.setPlainText(updated_text)
            code_cursor.setPosition(pos + len(updated_text) - len(current_text))
            self.code_editor.code_editor.setTextCursor(code_cursor)
            self._updating_requirements_from_analysis = False

    def _parse_requirements_lines(self, text):
        """
        返回 (保留的行列表, 包名集合)
        保留用户原始行（含版本、注释等），但记录其包名用于比对
        """
        lines = []
        package_lines = {}  # pkg_name_lower -> original_line
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                lines.append(line)  # 保留空行和注释
                continue
            # 提取包名
            match = re.match(r'^([a-zA-Z0-9._-]+)', stripped)
            if match:
                pkg_name = match.group(1).lower()
                # 如果同一个包出现多次，保留第一个（或最后一个，按需）
                if pkg_name not in package_lines:
                    package_lines[pkg_name] = line
                # 不立即加入 lines，稍后按需保留
            else:
                # 无法识别的行（如 -e .），保留
                lines.append(line)
        return lines, package_lines

    def _save_component(self, delete_original_file: bool = True):
        """保存组件"""
        try:
            # 验证基本信息
            name = self.name_edit.text().strip()
            category = self.category_edit.text().strip()
            if not name or not category:
                self._show_warning("请输入组件名称和分类！")
                return
            # 生成组件代码
            code = self.code_editor.get_code()
            if not code.strip():
                self._show_warning("请输入组件代码！")
                return
            # 保存到文件，传入原始文件路径
            # 注意：这里保存到文件时，如果代码开头没有 COMPONENT_IMPORT_CODE，会自动添加
            # 但保存到历史记录时，不添加
            self._save_component_to_file(category, name, code, self._current_component_file, delete_original_file)
            # --- 新增：保存历史记录 (不添加 COMPONENT_IMPORT_CODE) ---
            if self._current_component_file:
                # 直接使用编辑器中的代码，不修改
                ComponentHistoryManager.save_history(self._current_component_file, name, code)
                self._load_history_list(self._current_component_file)  # 保存后刷新历史列表
            # --- 新增结束 ---
            # 刷新组件树
            self.component_tree.refresh_components()
            self._show_success("组件保存成功！")
            # 重新加载当前组件
            self._load_component_filepath(self._current_component_file)
        except Exception as e:
            self._show_error(f"保存组件失败: {str(e)}")

    def _save_component_to_file(self, category, name, code, original_file_path=None, delete_original_file=True):
        """保存组件到文件，可选择性地删除原始文件"""
        # 确保目录存在
        components_dir = Path(__file__).parent.parent / Path("components") / category
        components_dir.mkdir(parents=True, exist_ok=True)
        # --- 删除原始文件 ---
        if delete_original_file and original_file_path and (components_dir / original_file_path.name).exists():
            # 删除原文件
            original_file_path.unlink()
            filepath = original_file_path
        elif delete_original_file and original_file_path and not (components_dir / original_file_path.name).exists():
            # 使用shutil将源文件移到新的组件目录
            shutil.move(str(original_file_path), str(components_dir))
            filepath = components_dir / original_file_path.name
        else:
            filename = f"{str(uuid.uuid4()).replace(' ', '_').lower()}.py"
            filepath = components_dir / filename

        # --- 检查并添加必要的导入语句 (仅保存到文件时) ---
        if not code.startswith("try:"):
            # 简单的检查，如果开头不是预期的导入，就添加
            code = COMPONENT_IMPORT_CODE + code

        # 写入新代码
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(code)
        self._current_component_file = filepath

    def _cancel_edit(self):
        """取消编辑"""
        w = MessageBox("确认", "确定要取消编辑吗？未保存的更改将丢失。", self.window())
        if w.exec():
            # 清空编辑器
            self.name_edit.clear()
            self.category_edit.clear()
            self.description_edit.clear()
            self.requirements_edit.clear()
            self.input_port_editor.set_ports([])
            self.output_port_editor.set_ports([])
            self.property_editor.set_properties({})
            self.code_editor.set_code(DEFAULT_NODE_TEMPLATE)
            self._current_component_file = None

    # --- 新增：加载历史记录列表 ---
    def _load_history_list(self, component_file_path: Path):
        """加载并显示指定组件的历史记录列表"""
        self.history_table.setRowCount(0)
        histories = ComponentHistoryManager.load_histories(component_file_path)
        # 反向排序，最新的在上面
        for history in reversed(histories):
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)
            # 版本号单元格现在不可编辑
            version_item = QTableWidgetItem(history['version'])
            # version_item.setFlags(version_item.flags() | Qt.ItemIsEditable) # 移除可编辑标志
            self.history_table.setItem(row, 0, version_item)
            # 时间单元格现在也不可编辑
            timestamp_item = QTableWidgetItem(history['timestamp'])
            # timestamp_item.setFlags(timestamp_item.flags() | Qt.ItemIsEditable) # 移除可编辑标志
            self.history_table.setItem(row, 1, timestamp_item)

    # --- 新增结束 ---
    # --- 新增：加载历史代码 ---
    def _load_history_code(self, item):
        """从历史记录列表项加载代码"""
        row = item.row()
        # 从表格中获取历史记录数据（这里简化为直接从加载的列表中取）
        # 为了更高效，可以将加载的历史记录存储在实例变量中
        # 但为了简单起见，这里直接从文件重新加载
        if self._current_component_file:
            histories = ComponentHistoryManager.load_histories(self._current_component_file)
            if 0 <= row < len(histories):
                history_data = histories[len(histories) - 1 - row]  # 因为列表是反向的
                if history_data and 'code' in history_data:
                    code = history_data['code']
                    # 使用 replace_text_preserving_view 以保持编辑器状态（如光标位置、滚动条等）
                    # 注意：加载历史代码时，它可能不包含 COMPONENT_IMPORT_CODE
                    self.code_editor.replace_text_preserving_view(code)
                    print(f"已加载历史版本: {history_data['version']} - {history_data['timestamp']}")
                    # 注意：加载历史代码后，通常不会自动更新 _current_component_file 指向的文件内容
                    # 如果需要，可以添加确认对话框询问用户是否要将此历史版本设为当前版本并保存
                else:
                    print("历史记录数据不完整，无法加载代码。")
            else:
                print("无效的历史记录行。")
        else:
            print("当前没有加载的组件文件，无法加载历史代码。")

    # --- 新增结束 ---
    def _show_warning(self, message):
        """显示警告信息"""
        InfoBar.warning(
            title='警告',
            content=message,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000,
            parent=self
        )

    def _show_error(self, message):
        """显示错误信息"""
        InfoBar.error(
            title='错误',
            content=message,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=5000,
            parent=self
        )

    def _show_success(self, message):
        """显示成功信息"""
        InfoBar.success(
            title='成功',
            content=message,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self
        )


# --- 端口编辑器（已修改）---
class PortEditorWidget(QWidget):
    """端口编辑器 - 支持动态添加删除"""
    ports_changed = pyqtSignal()

    def __init__(self, port_type="input", parent=None):
        super().__init__(parent)
        self.port_type = port_type
        layout = QVBoxLayout(self)
        # 表格：增加第4列
        self.table = TableWidget(self)
        if port_type == "input":
            self.table.setColumnCount(4)
            self.table.setHorizontalHeaderLabels(["端口名称", "端口标签", "端口类型", "连接方式"])
        else:
            self.table.setColumnCount(3)
            self.table.setHorizontalHeaderLabels(["端口名称", "端口标签", "端口类型"])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.itemChanged.connect(lambda item: self.ports_changed.emit())
        button_layout = QHBoxLayout()
        button_layout.addWidget(BodyLabel("输入端口:" if port_type == "input" else "输出端口:"))
        add_btn = ToolButton(FluentIcon.ADD, parent=self)
        add_btn.clicked.connect(lambda: self._add_port())
        remove_btn = ToolButton(FluentIcon.CLOSE, parent=self)
        remove_btn.clicked.connect(self._remove_port)
        button_layout.addWidget(add_btn)
        button_layout.addWidget(remove_btn)
        layout.addLayout(button_layout)
        layout.addWidget(self.table)

    def _add_port(self, port: dict = {}):
        row = self.table.rowCount()
        self.table.insertRow(row)
        name = port.get("name", f"input{row + 1}" if self.port_type == "input" else f"output{row + 1}")
        label = port.get("label", f"输入{row + 1}" if self.port_type == "input" else f"输出{row + 1}")
        port_type = port.get("type", ArgumentType.TEXT)
        self.table.setItem(row, 0, QTableWidgetItem(name))
        self.table.setItem(row, 1, QTableWidgetItem(label))
        type_combo = ComboBox()
        type_combo.setMaxVisibleItems(6)
        for item in ArgumentType:
            type_combo.addItem(item.value, userData=item)
        type_combo.setCurrentText(port_type.value)
        self.table.setCellWidget(row, 2, type_combo)
        type_combo.currentTextChanged.connect(lambda: self.ports_changed.emit())
        if self.port_type == "input":
            connection = port.get("connection", ConnectionType.SINGLE)
            conn_combo = ComboBox()
            conn_combo.addItems([ConnectionType.SINGLE.value, ConnectionType.MULTIPLE.value])
            conn_combo.setProperty("raw_values", [ConnectionType.SINGLE, ConnectionType.MULTIPLE])
            conn_combo.setCurrentIndex(0 if connection == ConnectionType.SINGLE else 1)
            self.table.setCellWidget(row, 3, conn_combo)
            conn_combo.currentIndexChanged.connect(lambda: self.ports_changed.emit())

    def _remove_port(self):
        selected_ranges = self.table.selectedRanges()
        if selected_ranges:
            rows = []
            for range_ in selected_ranges:
                rows.extend(range(range_.topRow(), range_.bottomRow() + 1))
            rows = sorted(set(rows), reverse=True)
            for row in rows:
                self.table.removeRow(row)
            self.ports_changed.emit()

    def get_ports(self):
        ports = []
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            label_item = self.table.item(row, 1)
            if not (name_item and label_item):
                continue
            type_widget = self.table.cellWidget(row, 2)
            port_type = type_widget.currentData() if type_widget else ArgumentType.TEXT
            conn_widget = self.table.cellWidget(row, 3)
            if conn_widget:
                raw_vals = [ConnectionType.SINGLE, ConnectionType.MULTIPLE]
                connection = raw_vals[conn_widget.currentIndex()]
            else:
                connection = ConnectionType.SINGLE
            ports.append({
                "name": name_item.text(),
                "label": label_item.text(),
                "type": port_type,
                "connection": connection
            })
        return ports

    def set_ports(self, ports):
        self.table.setRowCount(0)
        for port in ports:
            self._add_port(port)


# --- 属性编辑器 (未改动) ---
class PropertyEditorWidget(QWidget):
    """属性编辑器 - 支持动态添加删除"""
    properties_changed = pyqtSignal()  # 属性改变信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self._dynamic_form_schemas = {}  # 新增：存储每个动态表单的 schema
        self._choice_configs = {}
        self._range_configs = {}
        layout = QVBoxLayout(self)
        # 属性表格
        self.table = TableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["属性名", "标签", "类型", "默认值", "选项"])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.itemChanged.connect(lambda item: self.properties_changed.emit())
        button_layout = QHBoxLayout()
        button_layout.addWidget(BodyLabel("参数设置:"))
        add_btn = ToolButton(FluentIcon.ADD, parent=self)
        add_btn.clicked.connect(lambda: self._add_property())
        remove_btn = ToolButton(FluentIcon.CLOSE, parent=self)
        remove_btn.clicked.connect(self._remove_property)
        button_layout.addWidget(add_btn)
        button_layout.addWidget(remove_btn)
        layout.addLayout(button_layout)
        layout.addWidget(self.table)

    def _remove_property(self):
        """删除选中属性"""
        selected_ranges = self.table.selectedRanges()
        if selected_ranges:
            rows = []
            for range_ in selected_ranges:
                rows.extend(range(range_.topRow(), range_.bottomRow() + 1))
            rows = sorted(set(rows), reverse=True)
            for row in rows:
                self.table.removeRow(row)
            self.properties_changed.emit()

    def _add_property(self, prop_name: str = None, prop_def: PropertyType = None):
        """添加属性"""
        row = self.table.rowCount()
        self.table.insertRow(row)
        # 属性名
        name_item = QTableWidgetItem(prop_name if prop_name else f"prop{row + 1}")
        self.table.setItem(row, 0, name_item)
        # 标签
        label_item = QTableWidgetItem(getattr(prop_def, 'label', f"属性{row + 1}"))
        self.table.setItem(row, 1, label_item)
        # 类型
        type_combo = ComboBox()
        type_combo.setMaxVisibleItems(6)
        for item in PropertyType:
            type_combo.addItem(item.value, userData=item)
        type_combo.setCurrentText(getattr(prop_def, 'type', 'text'))
        self.table.setCellWidget(row, 2, type_combo)
        type_combo.currentTextChanged.connect(
            lambda text: self._on_type_changed(row)
        )
        # 默认值
        default_item = QTableWidgetItem(str(getattr(prop_def, 'default', '')))
        self.table.setItem(row, 3, default_item)
        # 替换原来的"选项"列：改为"操作"列
        action_widget = QWidget()
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(0, 0, 0, 0)
        if getattr(prop_def, 'type', PropertyType.TEXT) == PropertyType.DYNAMICFORM:
            edit_btn = PushButton("编辑表单")
            edit_btn.clicked.connect(lambda _, r=row: self._edit_dynamic_form(r))
            action_layout.addWidget(edit_btn)
            self.table.setCellWidget(row, 4, action_widget)
        elif getattr(prop_def, 'type', PropertyType.TEXT) == PropertyType.RANGE:
            edit_btn = PushButton("配置范围")
            # 从 prop_def 获取当前值并存储
            min_val = getattr(prop_def, 'min', 0)
            max_val = getattr(prop_def, 'max', 100)
            step_val = getattr(prop_def, 'step', 1)
            # 存储到内部字典
            if prop_name:
                self._range_configs[prop_name] = {'min': min_val, 'max': max_val, 'step': step_val}
            edit_btn.clicked.connect(lambda _, r=row: self._edit_range(r))
            action_layout.addWidget(edit_btn)
            self.table.setCellWidget(row, 4, action_widget)
        elif getattr(prop_def, 'type', PropertyType.TEXT) == PropertyType.LONGTEXT:
            btn = PushButton("编辑文本")
            btn.clicked.connect(lambda _, r=row: self._edit_long_text(r))
            self.table.setCellWidget(row, 4, btn)
        elif getattr(prop_def, 'type', PropertyType.TEXT) == PropertyType.CHOICE:
            edit_btn = PushButton("配置选项")
            choices = getattr(prop_def, 'choices', [])
            # 存储到内部字典
            if prop_name:
                self._choice_configs[prop_name] = choices
            edit_btn.clicked.connect(lambda _, r=row: self._edit_choice(r))
            action_layout.addWidget(edit_btn)
            self.table.setCellWidget(row, 4, action_widget)
        else:
            options_item = QTableWidgetItem("")
            options_item.setFlags(options_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 4, options_item)

    def _on_type_changed(self, row):
        type_widget = self.table.cellWidget(row, 2)
        if not type_widget:
            return
        prop_type = type_widget.currentData() or PropertyType.TEXT
        # ✅ 关键修复：同时清除 item 和 cell widget
        self.table.setItem(row, 4, None)  # 清除文本项
        self.table.setCellWidget(row, 4, None)  # 清除按钮等 widget
        if prop_type == PropertyType.CHOICE:
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(0, 0, 0, 0)
            btn = PushButton("配置选项")
            btn.clicked.connect(lambda _, r=row: self._edit_choice(r))
            action_layout.addWidget(btn)
            self.table.setCellWidget(row, 4, action_widget)
        elif prop_type == PropertyType.RANGE:
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(0, 0, 0, 0)
            btn = PushButton("配置范围")
            btn.clicked.connect(lambda _, r=row: self._edit_range(r))
            action_layout.addWidget(btn)
            self.table.setCellWidget(row, 4, action_widget)
        elif prop_type == PropertyType.LONGTEXT:
            btn = PushButton("编辑文本")
            btn.clicked.connect(lambda _, r=row: self._edit_long_text(r))
            self.table.setCellWidget(row, 4, btn)
        elif prop_type == PropertyType.DYNAMICFORM:
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(0, 0, 0, 0)
            btn = PushButton("编辑表单")
            btn.clicked.connect(lambda _, r=row: self._edit_dynamic_form(r))
            action_layout.addWidget(btn)
            self.table.setCellWidget(row, 4, action_widget)
        else:
            options_item = QTableWidgetItem("")
            options_item.setFlags(options_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 4, options_item)
        self.properties_changed.emit()

    def _edit_range(self, row):
        """编辑范围参数"""
        try:
            name_item = self.table.item(row, 0)
            if not name_item or not name_item.text().strip():
                InfoBar.warning("警告", "请先填写属性名", parent=self.parent, duration=2000)
                return
            prop_name = name_item.text()
            # 从内部存储获取当前值
            current_values = self._range_configs.get(prop_name, {'min': 0, 'max': 100, 'step': 1})
            dialog = RangeConfigDialog(
                current_values['min'],
                current_values['max'],
                current_values['step'],
                self.window()
            )
            if dialog.exec() == QDialog.Accepted:
                new_values = dialog.get_values()
                # 更新内部存储
                self._range_configs[prop_name] = new_values
                self.properties_changed.emit()
                InfoBar.success("成功", f"已保存范围配置: {prop_name}", parent=self.parent, duration=1500)
        except Exception as e:
            import traceback
            traceback.print_exc()
            InfoBar.error("错误", f"编辑失败: {str(e)}", parent=self.parent, duration=3000)

    def _edit_choice(self, row):
        """编辑下拉选项"""
        try:
            name_item = self.table.item(row, 0)
            if not name_item or not name_item.text().strip():
                InfoBar.warning("警告", "请先填写属性名", parent=self.parent, duration=2000)
                return
            prop_name = name_item.text()
            # 从内部存储获取当前值
            current_choices = self._choice_configs.get(prop_name, [])
            dialog = ChoiceConfigDialog(current_choices, self.window())
            if dialog.exec() == QDialog.Accepted:
                new_choices = dialog.get_choices()
                # 更新内部存储
                self._choice_configs[prop_name] = new_choices
                self.properties_changed.emit()
                InfoBar.success("成功", f"已保存下拉选项: {prop_name}", parent=self.parent, duration=1500)
        except Exception as e:
            import traceback
            traceback.print_exc()
            InfoBar.error("错误", f"编辑失败: {str(e)}", parent=self.parent, duration=3000)

    def get_properties(self):
        """获取属性数据（支持 DYNAMICFORM）"""
        properties = {}
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            label_item = self.table.item(row, 1)
            type_widget = self.table.cellWidget(row, 2)
            default_item = self.table.item(row, 3)
            if not (name_item and type_widget):
                continue
            prop_name = name_item.text()
            prop_type = type_widget.currentData() or PropertyType.TEXT
            default_value = default_item.text() if default_item else ""
            prop_dict = {
                "type": prop_type,
                "default": default_value,
                "label": label_item.text() if label_item else prop_name
            }
            if prop_type == PropertyType.CHOICE:
                # 从内部存储获取选项
                if prop_name in self._choice_configs:
                    prop_dict["choices"] = self._choice_configs[prop_name]
            elif prop_type == PropertyType.RANGE:
                # 从内部存储获取范围值
                if prop_name in self._range_configs:
                    prop_dict.update(self._range_configs[prop_name])
            elif prop_type == PropertyType.DYNAMICFORM:
                # 从内部存储读取 schema
                if prop_name in self._dynamic_form_schemas:
                    prop_dict["schema"] = self._dynamic_form_schemas[prop_name]
            properties[prop_name] = prop_dict
        return properties

    def set_properties(self, properties):
        """设置属性数据（支持 DYNAMICFORM）"""
        self.table.setRowCount(0)
        self._dynamic_form_schemas.clear()  # 清空旧 schema
        self._range_configs.clear()  # 清空范围配置
        self._choice_configs.clear()  # 清空下拉选项配置
        for prop_name, prop_def in properties.items():
            if isinstance(prop_def, dict):
                prop_def = PropertyDefinition(**prop_def)
            prop_type = getattr(prop_def, 'type', PropertyType.TEXT)
            if prop_type == PropertyType.DYNAMICFORM:
                # 保存 schema 到内部存储
                self._dynamic_form_schemas[prop_name] = getattr(prop_def, 'schema', {})
            elif prop_type == PropertyType.RANGE:
                # 保存范围配置到内部存储
                self._range_configs[prop_name] = {
                    'min': getattr(prop_def, 'min', 0),
                    'max': getattr(prop_def, 'max', 100),
                    'step': getattr(prop_def, 'step', 1)
                }
            elif prop_type == PropertyType.CHOICE:
                # 保存下拉选项到内部存储
                self._choice_configs[prop_name] = getattr(prop_def, 'choices', [])
            # 调用 _add_property（它会根据类型显示"编辑表单"按钮）
            self._add_property(prop_name, prop_def)

    def _edit_dynamic_form(self, row):
        """编辑动态表单结构"""
        try:
            name_item = self.table.item(row, 0)
            if not name_item or not name_item.text().strip():
                InfoBar.warning("警告", "请先填写属性名", parent=self.parent, duration=2000)
                return
            prop_name = name_item.text()
            current_schema = self._dynamic_form_schemas.get(prop_name, {})
            dialog = DynamicFormEditorDialog(current_schema, self.window())
            if dialog.exec() == QDialog.Accepted:
                new_schema = dialog.get_schema()
                self._dynamic_form_schemas[prop_name] = new_schema
                self.properties_changed.emit()
                InfoBar.success("成功", f"已保存表单结构: {prop_name}", parent=self.parent, duration=1500)
        except Exception as e:
            import traceback
            traceback.print_exc()
            InfoBar.error("错误", f"编辑失败: {str(e)}", parent=self.parent, duration=3000)

    def _edit_long_text(self, row):
        """编辑长文本"""
        try:
            name_item = self.table.item(row, 0)
            if not name_item or not name_item.text().strip():
                InfoBar.warning("警告", "请先填写属性名", parent=self.parent, duration=2000)
                return
            default_item = self.table.item(row, 3)
            current_text = default_item.text() if default_item else ""
            dialog = LongTextEditorDialog(current_text, self.window(), self.parent)
            if dialog.exec() == QDialog.Accepted:
                new_text = dialog.text_edit.toPlainText()
                if default_item:
                    default_item.setText(new_text)
                self.properties_changed.emit()
                InfoBar.success("成功", "长文本已更新", parent=self.parent, duration=1500)
        except Exception as e:
            import traceback
            traceback.print_exc()
            InfoBar.error("错误", f"编辑失败: {str(e)}", parent=self.parent, duration=3000)


class DynamicFormEditorDialog(MessageBoxBase):
    """动态表单编辑器对话框"""

    def __init__(self, schema: dict, parent=None):
        super().__init__(parent)
        self.widget.setMinimumSize(600, 400)
        self.schema = schema or {}
        self.editor = PropertyEditorWidget(self)
        self.editor.set_properties(self.schema)
        # 标题
        self.titleLabel = SubtitleLabel("编辑动态表单结构")
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.editor)

    def get_schema(self):
        """获取编辑后的 schema"""
        return self.editor.get_properties()


class RangeConfigDialog(MessageBoxBase):
    """范围配置对话框"""

    def __init__(self, min_val=0, max_val=100, step_val=1, parent=None):
        super().__init__(parent)
        self.widget.setMinimumSize(400, 200)
        # 标题
        self.titleLabel = SubtitleLabel("配置范围参数")
        self.viewLayout.addWidget(self.titleLabel)
        # 表单布局
        form_layout = QFormLayout()
        self.min_spin = DoubleSpinBox()
        self.min_spin.setRange(-999999, 999999)
        self.min_spin.setValue(min_val)
        form_layout.addRow("最小值:", self.min_spin)
        self.max_spin = DoubleSpinBox()
        self.max_spin.setRange(-999999, 999999)
        self.max_spin.setValue(max_val)
        form_layout.addRow("最大值:", self.max_spin)
        self.step_spin = DoubleSpinBox()
        self.step_spin.setRange(0.001, 999999)
        self.step_spin.setValue(step_val)
        self.step_spin.setDecimals(3)
        form_layout.addRow("步长:", self.step_spin)
        self.viewLayout.addLayout(form_layout)

    def get_values(self):
        return {
            'min': self.min_spin.value(),
            'max': self.max_spin.value(),
            'step': self.step_spin.value()
        }


class ChoiceConfigDialog(MessageBoxBase):
    """下拉框选项配置对话框（优化版：内联输入，不弹新窗）"""

    def __init__(self, choices=None, parent=None):
        super().__init__(parent)
        self.widget.setMinimumSize(500, 350)  # 稍微增加高度以容纳输入框
        self.choices = choices or []
        # 标题
        self.titleLabel = SubtitleLabel("配置下拉选项")
        self.viewLayout.addWidget(self.titleLabel)
        # 选项列表
        self.list_widget = TableWidget()  # 使用 TableWidget (虽然名字是list，但为了保持一致)
        self.list_widget.setColumnCount(1)
        self.list_widget.setHorizontalHeaderLabels(["选项"])
        self.list_widget.setRowCount(len(self.choices))
        for i, choice in enumerate(self.choices):
            self.list_widget.setItem(i, 0, QTableWidgetItem(choice))
        self.list_widget.verticalHeader().hide()
        self.list_widget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.viewLayout.addWidget(self.list_widget)
        # 输入框 + 按钮布局
        input_layout = QHBoxLayout()
        self.input_line = LineEdit()
        self.input_line.setPlaceholderText("输入新选项后点击“添加”")
        self.input_line.returnPressed.connect(self._add_choice)  # 回车也可添加
        input_layout.addWidget(self.input_line)
        self.add_btn = PushButton("添加")
        self.add_btn.clicked.connect(self._add_choice)
        input_layout.addWidget(self.add_btn)
        self.viewLayout.addLayout(input_layout)
        # 删除按钮（可单独一行或与添加同行，这里单独放更清晰）
        self.remove_btn = PushButton("删除选中")
        self.remove_btn.clicked.connect(self._remove_choice)
        self.viewLayout.addWidget(self.remove_btn)

    def _add_choice(self):
        text = self.input_line.text().strip()
        if text:
            row = self.list_widget.rowCount()
            self.list_widget.insertRow(row)
            self.list_widget.setItem(row, 0, QTableWidgetItem(text))
            self.input_line.clear()
            self.input_line.setFocus()  # 保持焦点，方便连续输入

    def _remove_choice(self):
        current_row = self.list_widget.currentRow()
        if current_row >= 0:
            self.list_widget.removeRow(current_row)

    def get_choices(self):
        choices = []
        for i in range(self.list_widget.rowCount()):
            item = self.list_widget.item(i, 0)
            if item:
                choices.append(item.text())
        return choices
