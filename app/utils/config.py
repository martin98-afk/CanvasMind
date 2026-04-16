# -*- coding: utf-8 -*-
import json
import os
import sys
from copy import deepcopy
from enum import Enum
from uuid import uuid4

from loguru import logger
from qfluentwidgets import (
    ConfigSerializer,
    ConfigItem,
    QConfig,
    OptionsValidator,
    BoolValidator,
    RangeValidator,
    OptionsConfigItem,
    ConfigValidator,
    RangeConfigItem,
)

from app.widgets.card_widget.list_setting_card import ListValidator


class PatchPlatform(Enum):
    GITHUB = "github"
    GITEE = "gitee"
    GITCODE = "gitcode"


class ListDictValidator(ConfigValidator):
    def correct(self, value):
        if isinstance(value, list):
            return value
        return []


class QuickComponentsSerializer(ConfigSerializer):
    def serialize(self, value):
        return value  # list[dict] 是 JSON-safe

    def deserialize(self, value):
        if isinstance(value, list):
            return value
        return []


class Settings(QConfig):
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_instance(cls):
        """获取配置实例（单例模式）"""
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._init_side_dock_plugins()
            CONFIG_FILE = "app.config"
            try:
                cls._instance.load(CONFIG_FILE)
            except:
                logger.exception("无法加载配置文件")
            cls._instance._load_side_dock_plugin_states()
        return cls._instance

    def _init_side_dock_plugins(self):
        try:
            from app.widgets.side_dock_area.registry import SideDockRegistry

            SideDockRegistry.discover_plugins()
        except Exception as e:
            logger.error(f"[Settings] Failed to discover side dock plugins: {e}")

    def _load_side_dock_plugin_states(self):
        try:
            from app.widgets.side_dock_area.registry import SideDockRegistry

            saved_states = self.side_dock_plugins.value
            if saved_states:
                SideDockRegistry.load_states_from_config(saved_states)
        except Exception:
            pass

    @classmethod
    def save_config(cls):
        """保存配置"""
        pass

    def set(self, item, value, save=False, copy=True):
        """set the value of config item

        Parameters
        ----------
        item: ConfigItem
            config item

        value:
            the new value of config item

        save: bool
            whether to save the change to config file

        copy: bool
            whether to deep copy the new value
        """
        if item.value == value:
            return

        # deepcopy new value
        try:
            item.value = deepcopy(value) if copy else value
        except:
            item.value = value

        if save:
            self.save()

        if item.restart:
            self._cfg.appRestartSig.emit()

        if item is self._cfg.themeMode:
            self.theme = value
            self._cfg.themeChanged.emit(value)

        if item is self._cfg.themeColor:
            self._cfg.themeColorChanged.emit(value)

    def save(self):
        """save config"""
        # 确保目录存在
        self.file.parent.mkdir(parents=True, exist_ok=True)
        # 写入文件
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(self.toDict(), f, ensure_ascii=False, indent=4)

    # 版本信息
    current_version = "v0.4.4"
    user_name = ConfigItem("General", "UserName", str(uuid4().hex))
    # 通用设置
    auto_check_update = ConfigItem("General", "AutoCheckUpdate", True, BoolValidator())

    # 版本管理设置
    patch_platform = ConfigItem(
        "Patch",
        "Platform",
        "github",
        OptionsValidator([p.value for p in PatchPlatform]),
    )

    # GitHub 配置
    github_repo = ConfigItem("Patch", "GitHub/Repo", "martin98-afk/CanvasMind")
    github_token = ConfigItem("Patch", "GitHub/Token", "")

    # ========== 画布路径 ==========
    workflow_paths = ConfigItem(
        "Workflow", "Paths", ["./canvas_files/workflows"], ListValidator()
    )
    # ========== 项目路径 ==========
    project_paths = ConfigItem(
        "Project", "Paths", ["./canvas_files/projects"], ListValidator()
    )

    # ========== 画布运行设置 ==========
    node_run_timeout_toggle = ConfigItem(
        "CanvasRun", "RunTimeoutToggle", False, BoolValidator()
    )
    node_run_timeout = RangeConfigItem(
        "CanvasRun", "RunTimeout", 300, RangeValidator(120, 3000)
    )
    run_parallel = ConfigItem("CanvasRun", "RunParallel", True, BoolValidator())
    run_parallel_max_workers = RangeConfigItem(
        "CanvasRun", "RunParallelMaxWorkers", 2, RangeValidator(1, 10)
    )
    communication_method = OptionsConfigItem(
        "CanvasRun",
        "CommunicationMethod",
        "日志通信",
        OptionsValidator(["ZMQ通信", "日志通信"]),
    )
    # ========== 画布自动保存设置 ==========
    canvas_auto_save = ConfigItem("CanvasIO", "AutoSave", True, BoolValidator())
    canvas_auto_save_interval = RangeConfigItem(
        "CanvasIO", "AutoSaveInterval", 60, RangeValidator(15, 300)
    )

    # ========== 画布显示设置 ==========
    node_animation = ConfigItem(
        "CanvasDisplay", "NodeAnimation", False, BoolValidator()
    )
    canvas_resize_memory = ConfigItem(
        "CanvasDisplay", "ResizeMemory", True, BoolValidator()
    )
    canvas_auto_collapse = ConfigItem(
        "CanvasDisplay", "AutoCollapse", False, BoolValidator()
    )
    canvas_grid_mode = OptionsConfigItem(
        "CanvasDisplay",
        "ShowGrid",
        "线网格",
        OptionsValidator(["线网格", "点网格", "无网格"]),
    )
    canvas_pipe_width = RangeConfigItem(
        "CanvasDisplay", "PipeWidth", 4, RangeValidator(1, 10)
    )
    node_proxy_size = RangeConfigItem(
        "CanvasDisplay", "NodeProxySize", 120, RangeValidator(70, 300)
    )
    canvas_grid_size = ConfigItem(
        "CanvasDisplay", "GridSize", 20, RangeValidator(10, 30)
    )
    canvas_pipelayout = OptionsConfigItem(
        "CanvasDisplay",
        "PipeLayout",
        "折线",
        OptionsValidator(["直线", "曲线", "折线"]),
    )
    canvas_font_list = ConfigItem(
        "CanvasDisplay",
        "FontList",
        [
            "Segoe UI",
            "Inter",
            "Roboto",
            "Arial",
            "Helvetica",
            "Montserrat",
            "Consolas",
            "Fira Code",
            "JetBrains Mono",
            "Courier New",
            "Georgia",
            "Times New Roman",
            "Playfair Display",
            "Impact",
            "Comic Sans MS",
            "Copperplate",
            "Microsoft YaHei",
            "PingFang SC",
            "Noto Sans SC",
            "KaiTi",
        ],
        ListValidator(),
    )
    canvas_font_selected = ConfigItem(
        "CanvasDisplay",
        "FontSelected",
        "Segoe UI",
    )
    canvas_direction = OptionsConfigItem(
        "CanvasDisplay", "Direction", "水平", OptionsValidator(["水平", "垂直"])
    )

    # ========== 画布快捷组件 ==========

    # 快捷组件
    quick_components = ConfigItem(
        "Canvas",
        "QuickComponents",
        [],  # 默认值
        serializer=QuickComponentsSerializer(),
    )

    # ========== 运行环境管理配置 ==========
    python_versions = ConfigItem(
        "Package",
        "PythonVersions",
        ["3.9", "3.10", "3.11", "3.12", "3.13", "3.14"],
        ListValidator(),
    )
    miniconda_version = ConfigItem("Package", "MinicondaVersion", "23.11.0")
    mirrors = ConfigItem(
        "Package",
        "Mirrors",
        ["https://pypi.tuna.tsinghua.edu.cn/simple"],
        ListValidator(),
    )
    # 默认要安装的包列表
    default_packages = ConfigItem(
        "Package",
        "DefaultPackages",
        [
            "pyzmq",
            "loguru",
            "pydantic",
            "pandas",
            "Pillow",
            "fastapi",
            "uvicorn",
            "python-lsp-server[all]",
            "asteval",
            "wcwidth",
            "pyarrow",
            "ipykernel",
            "matplotlib",
            "pyecharts",
            "mcp",
        ],
        ListValidator(),
    )
    current_env_selected = ConfigItem("Package", "EnvSelected", "")

    # ========== 大模型对话默认配置 ==========
    llm_model = ConfigItem("LLM", "Model", "qwen/qwen3-30b-a3b-2507")
    llm_api_key = ConfigItem("LLM", "APIKey", "")
    llm_api_base = ConfigItem("LLM", "APIBase", "http://127.0.0.1:1234/v1")
    llm_max_tokens = ConfigItem("LLM", "MaxTokens", 2048, RangeValidator(1024, 400960))
    llm_temperature = ConfigItem("LLM", "Temperature", 0.7, RangeValidator(0, 1))
    llm_enable_thinking = ConfigItem("LLM", "EnableThinking", True, BoolValidator())
    # 保存的免费/自定义服务商配置
    llm_saved_providers = ConfigItem("LLM", "SavedProviders", {})
    # 最近选择的模型
    llm_selected_model = ConfigItem("LLM", "SelectedModel", "")
    # 启用的技能列表
    llm_enabled_skills = ConfigItem("LLM", "EnabledSkills", [])

    # ========== 侧边栏插件配置 ==========
    side_dock_plugins = ConfigItem("SideDock", "Plugins", {})

    # ========== 云组件库API ==========
    STEIN_URL = ConfigItem(
        "CloudAPI",
        "Stein",
        "https://api.steinhq.com/v1/storages/69606496affba40a6237b4c2/sheet1",
    )
    SHEETY_URL = ConfigItem(
        "CloudAPI",
        "Sheety",
        "https://api.sheety.co/fe7b5d36457f54901b6078c05196e0a0/云组件库/sheet1",
    )
    GITEE_REPO = ConfigItem("Patch", "Gitee/Repo", "canvas-mind-components")
    GITEE_TOKEN = ConfigItem("Patch", "Gitee/Token", "a5dcb6e2e7776143b7a7e7685a1f33a3")
    GITEE_OWNER = ConfigItem("Patch", "Gitee/Owner", "dingmama123141")
    SERPAPI_KEY = ConfigItem(
        "CloudAPI",
        "SerpAPI",
        "42e2b2817bf48352d3caa227212ebb82d6f8839cdd39b304c68cf58b42961c27",
    )
