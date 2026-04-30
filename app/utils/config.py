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
            CONFIG_FILE = "app.config"
            try:
                cls._instance.load(CONFIG_FILE)
            except:
                logger.exception("无法加载配置文件")
        return cls._instance

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
    current_version = "v0.4.7"
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

    # ========== 大模型对话默认配置 ==========
    llm_model = ConfigItem("LLM", "Model", "qwen/qwen3-30b-a3b-2507")
    llm_api_key = ConfigItem("LLM", "APIKey", "")
    llm_api_base = ConfigItem("LLM", "APIBase", "http://127.0.0.1:1234/v1")
    llm_max_tokens = ConfigItem("LLM", "MaxTokens", 2048, RangeValidator(1024, 400960))
    llm_temperature = ConfigItem("LLM", "Temperature", 0.7, RangeValidator(0, 1))
    # 保存的免费/自定义服务商配置
    llm_saved_providers = ConfigItem("LLM", "SavedProviders",
                                     {
                                         "MiniMax (月之暗面)": {
                                             "模型名称": "MiniMax-M2.7",
                                             "API_URL": "https://api.minimax.chat/v1",
                                             "API_KEY": "sk-cp-YECP4gj2VZt7NxgUYww5Shn5FXBqb8aSIQDD0zMUoLzx10y4KEAYFKHqrmGhmx5Cxt9KV030zSXvyhDyqVs_0n-R2djEgYx6fzMs46T6gf3HooJdS5c4_Kk",
                                             "温度": 0.71,
                                             "最大Token": 208524,
                                             "获取地址": False
                                         }
                                     }
                                     )
    # 最近选择的模型
    llm_selected_model = ConfigItem("LLM", "SelectedModel", "MiniMax (月之暗面)")
    # 启用的技能列表
    llm_enabled_skills = ConfigItem("LLM", "EnabledSkills", ["gk-optimizer"])
    # 智能体完成通知
    llm_notify_enabled = ConfigItem("LLM", "NotifyEnabled", True, BoolValidator())
    # 通知提示音类型
    llm_notify_sound = OptionsConfigItem(
        "LLM",
        "NotifySound",
        "beep",
        OptionsValidator(["beep", "short", "none"]),
    )
    # 全局字体设置
    llm_font_family = ConfigItem("LLM", "FontFamily", "Segoe UI")

    # ========== LLM API 服务配置 ==========
    llm_api_enabled = ConfigItem("LLM", "APIEnabled", False, BoolValidator())
    llm_api_port = RangeConfigItem(
        "LLM", "APIPort", 8765, RangeValidator(1024, 65535)
    )

    # ========== 云组件库API ==========
    SERPAPI_KEY = ConfigItem(
        "CloudAPI",
        "SerpAPI",
        "42e2b2817bf48352d3caa227212ebb82d6f8839cdd39b304c68cf58b42961c27",
    )
