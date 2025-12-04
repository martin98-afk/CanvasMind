# -*- coding: utf-8 -*-
from pathlib import Path

from qfluentwidgets import ConfigSerializer, ConfigItem, QConfig, OptionsValidator, BoolValidator, FolderListValidator, \
    RangeValidator, OptionsConfigItem, ConfigValidator
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
    # 版本信息
    current_version = "v0.1.9"

    # 通用设置
    auto_check_update = ConfigItem("General", "AutoCheckUpdate", True, BoolValidator())

    # 版本管理设置
    patch_platform = ConfigItem("Patch", "Platform", "github", OptionsValidator([p.value for p in PatchPlatform]))

    # GitHub 配置
    github_repo = ConfigItem("Patch", "GitHub/Repo", "martin98-afk/CanvasMind")
    github_token = ConfigItem("Patch", "GitHub/Token", "")

    # ========== 新增：画布路径 ==========
    workflow_paths = ConfigItem(
        "Workflow",
        "Paths", ["./canvas_files/workflows"],
        ListValidator()
    )
    # ========== 新增：项目路径 ==========
    project_paths = ConfigItem(
        "Project",
        "Paths", ["./canvas_files/projects"],
        ListValidator()
    )

    # ========== 新增：画布设置 ==========
    canvas_run_mode = OptionsConfigItem("Canvas", "RunMode", "ipython运行",
                                         OptionsValidator(["ipython运行", "subprocess运行"]))
    canvas_grid_mode = OptionsConfigItem("Canvas", "ShowGrid", "线网格",
                                            OptionsValidator(["线网格", "点网格", "无网格"]))
    canvas_grid_size = ConfigItem("Canvas", "GridSize", 20, RangeValidator(10, 30))
    canvas_auto_save = ConfigItem("Canvas", "AutoSave", True, BoolValidator())
    canvas_auto_save_interval = ConfigItem("Canvas", "AutoSaveInterval", 60, RangeValidator(60, 120))
    canvas_pipelayout = OptionsConfigItem("Canvas", "PipeLayout", "折线",
                                            OptionsValidator(["直线", "曲线", "折线"]))
    canvas_direction = OptionsConfigItem("Canvas", "Direction", "水平",
                                          OptionsValidator(["水平", "垂直"]))

    # ========== 新增：画布快捷组件 ==========

    # 快捷组件
    quick_components = ConfigItem(
        "Canvas",
        "QuickComponents",
        [],  # 默认值
        serializer=QuickComponentsSerializer()
    )

    # ========== 新增：运行环境管理配置 ==========
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
        ["loguru", "pydantic", "pandas", "Pillow", "fastapi", "uvicorn", "jedi", "asteval", "wcwidth", "pyarrow", "ipykernel", "matplotlib"],
        ListValidator()
    )

    # ========== 新增：大模型对话默认配置 ==========
    llm_model = ConfigItem("LLM", "Model", "qwen/qwen3-30b-a3b-2507")
    llm_api_key = ConfigItem("LLM", "APIKey", "")
    llm_api_base = ConfigItem("LLM", "APIBase", "http://127.0.0.1:1234/v1")
    llm_max_tokens = ConfigItem("LLM", "MaxTokens", 2048, RangeValidator(1024, 40960))
    llm_temperature = ConfigItem("LLM", "Temperature", 0.7, RangeValidator(0, 1))
    llm_enable_thinking = ConfigItem("LLM", "EnableThinking", True, BoolValidator())