# -*- coding: utf-8 -*-
from pathlib import Path
from uuid import uuid4

from qfluentwidgets import ConfigSerializer, ConfigItem, QConfig, OptionsValidator, BoolValidator, FolderListValidator, \
    RangeValidator, OptionsConfigItem, ConfigValidator, RangeConfigItem
from enum import Enum

from app.utils.utils import resource_path
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
    # 版本信息
    current_version = "v0.2.9"
    user_name = ConfigItem("General", "UserName", str(uuid4().hex))
    # 通用设置
    auto_check_update = ConfigItem("General", "AutoCheckUpdate", True, BoolValidator())

    # 版本管理设置
    patch_platform = ConfigItem("Patch", "Platform", "github", OptionsValidator([p.value for p in PatchPlatform]))

    # GitHub 配置
    github_repo = ConfigItem("Patch", "GitHub/Repo", "martin98-afk/CanvasMind")
    github_token = ConfigItem("Patch", "GitHub/Token", "")

    # ========== 画布路径 ==========
    workflow_paths = ConfigItem(
        "Workflow",
        "Paths", ["./canvas_files/workflows"],
        ListValidator()
    )
    # ========== 项目路径 ==========
    project_paths = ConfigItem(
        "Project",
        "Paths", ["./canvas_files/projects"],
        ListValidator()
    )

    # ========== 画布运行设置 ==========
    node_run_timeout_toggle = ConfigItem("CanvasRun", "RunTimeoutToggle", False, BoolValidator())
    node_run_timeout = RangeConfigItem("CanvasRun", "RunTimeout", 300, RangeValidator(120, 3000))
    run_parallel = ConfigItem("CanvasRun", "RunParallel", True, BoolValidator())
    run_parallel_max_workers = RangeConfigItem("CanvasRun", "RunParallelMaxWorkers", 2, RangeValidator(1, 10))

    # ========== 画布自动保存设置 ==========
    canvas_auto_save = ConfigItem("CanvasIO", "AutoSave", True, BoolValidator())
    canvas_auto_save_interval = RangeConfigItem("CanvasIO", "AutoSaveInterval", 60, RangeValidator(15, 300))

    # ========== 画布显示设置 ==========
    canvas_grid_mode = OptionsConfigItem("CanvasDisplay", "ShowGrid", "线网格",
                                         OptionsValidator(["线网格", "点网格", "无网格"]))
    node_proxy_size = RangeConfigItem("CanvasDisplay", "NodeProxySize", 120, RangeValidator(70, 300))
    canvas_grid_size = ConfigItem("CanvasDisplay", "GridSize", 20, RangeValidator(10, 30))
    canvas_pipelayout = OptionsConfigItem("CanvasDisplay", "PipeLayout", "折线",
                                          OptionsValidator(["直线", "曲线", "折线"]))
    canvas_font_type = OptionsConfigItem(
        "CanvasDisplay",
        "FontType",
        "Segoe UI",  # 默认值改为现代 UI 常用的 Segoe UI
        OptionsValidator([
            "Segoe UI",  # Windows 标准现代化字体
            "Arial",  # 最通用的无衬线字体
            "Roboto",  # 谷歌风格，现代感强
            "Inter",  # 很多 UI 设计师的首选 (ComfyUI 风格)
            "Consolas",  # 等宽字体，有科技感/代码感
            "Microsoft YaHei"  # 微软雅黑的英文名，确保中文显示依然美观
        ])
    )
    canvas_direction = OptionsConfigItem("CanvasDisplay", "Direction", "水平", OptionsValidator(["水平", "垂直"]))

    # ========== 画布快捷组件 ==========

    # 快捷组件
    quick_components = ConfigItem(
        "Canvas",
        "QuickComponents",
        [],  # 默认值
        serializer=QuickComponentsSerializer()
    )

    # ========== 运行环境管理配置 ==========
    python_versions = ConfigItem(
        "Package",
        "PythonVersions", ["3.9", "3.10", "3.11", "3.12", "3.13", "3.14"],
        ListValidator()
    )
    miniconda_version = ConfigItem("Package", "MinicondaVersion", "23.11.0")
    mirrors = ConfigItem(
        "Package", "Mirrors", ["https://pypi.tuna.tsinghua.edu.cn/simple"], ListValidator()
    )
    # 默认要安装的包列表
    default_packages = ConfigItem(
        "Package",
        "DefaultPackages",
        [
            "pyzmq", "loguru", "pydantic", "pandas", "Pillow", "fastapi",
            "uvicorn", "python-lsp-server[all]", "asteval", "wcwidth",
            "pyarrow", "ipykernel", "matplotlib", "pyecharts", "mcp"
        ],
        ListValidator()
    )
    current_env_selected = ConfigItem("Package", "EnvSelected", "")

    # ========== 大模型对话默认配置 ==========
    llm_model = ConfigItem("LLM", "Model", "qwen/qwen3-30b-a3b-2507")
    llm_api_key = ConfigItem("LLM", "APIKey", "")
    llm_api_base = ConfigItem("LLM", "APIBase", "http://127.0.0.1:1234/v1")
    llm_max_tokens = ConfigItem("LLM", "MaxTokens", 2048, RangeValidator(1024, 40960))
    llm_temperature = ConfigItem("LLM", "Temperature", 0.7, RangeValidator(0, 1))
    llm_enable_thinking = ConfigItem("LLM", "EnableThinking", True, BoolValidator())

    # ========== 云组件库API ==========
    STEIN_URL = ConfigItem("CloudAPI", "Stein", "https://api.steinhq.com/v1/storages/69606496affba40a6237b4c2/sheet1")
    SHEETY_URL = ConfigItem("CloudAPI", "Sheety", "https://api.sheety.co/fe7b5d36457f54901b6078c05196e0a0/云组件库/sheet1")

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_instance(cls):
        """获取配置实例（单例模式）"""
        if cls._instance is None:
            cls._instance = cls()
            CONFIG_FILE = resource_path("../app.config")
            try:
                cls._instance.load(CONFIG_FILE)
            except:
                # 首次运行，保存默认配置
                cls._instance.save(CONFIG_FILE)
                print(f"✅ 已创建默认配置文件: {CONFIG_FILE}")
        return cls._instance

    @classmethod
    def save_config(cls):
        """保存配置"""
        if cls._instance:
            cls._instance.save()