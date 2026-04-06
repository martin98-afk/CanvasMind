# -*- coding: utf-8 -*-
"""
Provider profile helpers.

These helpers intentionally derive capabilities from the application's
live provider config (`API_URL`, `模型名称`, `认证方式`) so the chatter layer
stays aligned with software-level provider settings.
"""

from typing import Any, Dict


PROVIDER_CAPABILITIES = {
    "anthropic": {
        "context_limit": 200000,
        "max_output_tokens": 8192,
        "supports_vision": True,
    },
    "openai": {
        "context_limit": 128000,
        "max_output_tokens": 16384,
        "supports_vision": True,
    },
    "gemini": {
        "context_limit": 1000000,
        "max_output_tokens": 8192,
        "supports_vision": True,
    },
    "dashscope": {
        "context_limit": 1000000,
        "max_output_tokens": 8192,
        "supports_vision": True,
    },
    "zhipu": {
        "context_limit": 128000,
        "max_output_tokens": 8192,
        "supports_vision": True,
    },
    "deepseek": {
        "context_limit": 64000,
        "max_output_tokens": 8192,
        "supports_vision": False,
    },
    "groq": {
        "context_limit": 128000,
        "max_output_tokens": 8192,
        "supports_vision": False,
    },
    "minimax": {
        "context_limit": 1000000,
        "max_output_tokens": 8192,
        "supports_vision": False,
    },
    "baidu_qianfan": {
        "context_limit": 128000,
        "max_output_tokens": 8192,
        "supports_vision": False,
    },
    "ollama": {
        "context_limit": 128000,
        "max_output_tokens": 8192,
        "supports_vision": True,
    },
    "lmstudio": {
        "context_limit": 128000,
        "max_output_tokens": 8192,
        "supports_vision": True,
    },
    "custom": {
        "context_limit": 128000,
        "max_output_tokens": 8192,
        "supports_vision": False,
    },
}


def detect_provider_family(llm_config: Dict[str, Any]) -> str:
    api_url = str(llm_config.get("API_URL", "") or "").lower()
    model = str(llm_config.get("模型名称", "") or "").lower()
    auth = str(llm_config.get("认证方式", "") or "").lower()

    if "anthropic" in api_url or model.startswith("claude"):
        return "anthropic"
    if "generativelanguage.googleapis.com" in api_url or model.startswith("gemini"):
        return "gemini"
    if "dashscope.aliyuncs.com" in api_url or model.startswith("qwen"):
        return "dashscope"
    if "bigmodel.cn" in api_url or model.startswith("glm"):
        return "zhipu"
    if "deepseek.com" in api_url or model.startswith("deepseek"):
        return "deepseek"
    if "api.groq.com" in api_url or "groq/" in model:
        return "groq"
    if "minimax" in api_url or model.startswith("minimax"):
        return "minimax"
    if "qianfan.baidubce.com" in api_url or auth == "bce":
        return "baidu_qianfan"
    if "localhost:11434" in api_url or auth == "none":
        return "ollama"
    if "localhost:1234" in api_url:
        return "lmstudio"
    if "api.openai.com" in api_url or model.startswith(("gpt-", "o1", "o3")):
        return "openai"
    return "custom"


def get_provider_profile(llm_config: Dict[str, Any]) -> Dict[str, Any]:
    family = detect_provider_family(llm_config)
    profile = dict(PROVIDER_CAPABILITIES.get(family, PROVIDER_CAPABILITIES["custom"]))
    profile["family"] = family
    profile["auth_type"] = str(llm_config.get("认证方式", "bearer") or "bearer").lower()
    return profile


def supports_vision(llm_config: Dict[str, Any]) -> bool:
    model = str(llm_config.get("模型名称", "") or "").lower()
    profile = get_provider_profile(llm_config)
    if any(marker in model for marker in ("vision", "vl", "4o", "llava", "gemma4")):
        return True
    return bool(profile.get("supports_vision", False))
