# -*- coding: utf-8 -*-
from pathlib import Path

from qfluentwidgets import ConfigSerializer, ConfigItem, QConfig, OptionsValidator, BoolValidator, FolderListValidator, \
    RangeValidator, OptionsConfigItem
from enum import Enum


class PatchPlatform(Enum):
    GITHUB = "github"
    GITEE = "gitee"
    GITCODE = "gitcode"


class Settings(QConfig):
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_instance(cls):
        return cls()

    # 通用设置
    auto_check_update = ConfigItem("General", "AutoCheckUpdate", True, BoolValidator())

    # 版本管理设置
    patch_platform = ConfigItem("Patch", "Platform", "github", OptionsValidator([p.value for p in PatchPlatform]))

    # GitHub 配置
    github_repo = ConfigItem("Patch", "GitHub/Repo", "yourname/yourrepo")
    github_token = ConfigItem("Patch", "GitHub/Token", "")

    # Gitee 配置
    gitee_repo = ConfigItem("Patch", "Gitee/Repo", "yourname/yourrepo")
    gitee_token = ConfigItem("Patch", "Gitee/Token", "")

    # GitCode 配置（如有）
    gitcode_repo = ConfigItem("Patch", "GitCode/Repo", "yourname/yourrepo")

    # ========== 新增：画布路径 ==========
    workflow_paths = ConfigItem(
        "Workflow",
        "Paths", [Path(__file__).parent.parent.parent / Path("workflows")],
        FolderListValidator()
    )
    # ========== 新增：项目路径 ==========
    project_paths = ConfigItem(
        "Project",
        "Paths", [Path(__file__).parent.parent.parent / Path("projects")],
        FolderListValidator()
    )

    # ========== 新增：画布设置 ==========
    canvas_show_grid = ConfigItem("Canvas", "ShowGrid", True, BoolValidator())
    canvas_grid_size = ConfigItem("Canvas", "GridSize", 20, RangeValidator(10, 30))
    canvas_auto_save = ConfigItem("Canvas", "AutoSave", True, BoolValidator())
    canvas_auto_save_interval = ConfigItem("Canvas", "AutoSaveInterval", 60, RangeValidator(60, 120))
    canvas_pipelayout = OptionsConfigItem("Canvas", "PipeLayout", "折线",
                                            OptionsValidator(["直线", "曲线", "折线"]))
    canvas_default_zoom = OptionsConfigItem("Canvas", "DefaultZoom", "100%",
                                     OptionsValidator(["50%", "75%", "100%", "125%", "150%"]))