# -*- coding: utf-8 -*-
from pathlib import Path

from qfluentwidgets import ConfigSerializer, ConfigItem, QConfig, OptionsValidator, BoolValidator, FolderListValidator, \
    RangeValidator, OptionsConfigItem, ConfigValidator
from enum import Enum

from app.utils.utils import resource_path


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
            CONFIG_FILE = str(Path.cwd() / "app.config")
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
            CONFIG_FILE = str(Path.cwd() / "app.config")
            cls._instance.save(CONFIG_FILE)

    current_version = ConfigItem("General", "CurrentVersion", "v0.1.1-alpha")

    # 通用设置
    auto_check_update = ConfigItem("General", "AutoCheckUpdate", True, BoolValidator())

    # 版本管理设置
    patch_platform = ConfigItem("Patch", "Platform", "github", OptionsValidator([p.value for p in PatchPlatform]))

    # GitHub 配置
    github_repo = ConfigItem("Patch", "GitHub/Repo", "martin98-afk/CanvasMind")
    github_token = ConfigItem("Patch", "GitHub/Token", "")

    # Gitee 配置
    gitee_repo = ConfigItem("Patch", "Gitee/Repo", "yourname/yourrepo")
    gitee_token = ConfigItem("Patch", "Gitee/Token", "")

    # GitCode 配置（如有）
    gitcode_repo = ConfigItem("Patch", "GitCode/Repo", "yourname/yourrepo")

    # ========== 新增：画布路径 ==========
    workflow_paths = ConfigItem(
        "Workflow",
        "Paths", ["./workflows"],
        FolderListValidator()
    )
    # ========== 新增：项目路径 ==========
    project_paths = ConfigItem(
        "Project",
        "Paths", ["./projects"],
        FolderListValidator()
    )

    # ========== 新增：画布设置 ==========
    canvas_show_grid = ConfigItem("Canvas", "ShowGrid", True, BoolValidator())
    canvas_grid_size = ConfigItem("Canvas", "GridSize", 20, RangeValidator(10, 30))
    canvas_auto_save = ConfigItem("Canvas", "AutoSave", True, BoolValidator())
    canvas_auto_save_interval = ConfigItem("Canvas", "AutoSaveInterval", 60, RangeValidator(60, 120))
    canvas_pipelayout = OptionsConfigItem("Canvas", "PipeLayout", "折线",
                                            OptionsValidator(["直线", "曲线", "折线"]))
    canvas_direction = OptionsConfigItem("Canvas", "Direction", "水平",
                                          OptionsValidator(["水平", "垂直"]))
    canvas_default_zoom = OptionsConfigItem("Canvas", "DefaultZoom", "100%",
                                     OptionsValidator(["50%", "75%", "100%", "125%", "150%"]))
    # 快捷组件
    quick_components = ConfigItem(
        "Canvas",
        "QuickComponents",
        [],  # 默认值
        serializer=QuickComponentsSerializer()
    )