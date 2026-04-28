# -*- coding: utf-8 -*-
"""
LLM Chatter API 模块

提供远程调用接口，复用 UI 对话逻辑。
"""

from app.llm_chatter.api.api_server import (
    LLMAPIService,
    get_llm_api_service,
    ensure_service_running,
    start_llm_api_service,
    stop_llm_api_service,
    is_service_running,
    open_docs,
)
from app.llm_chatter.api.api_session_handler import (
    APISessionHandler,
    APIHistoryManager,
    StreamContext,
)
from app.llm_chatter.api.api_isolated_context import (
    IsolatedChatContext,
    IsolatedContextRegistry,
)

__all__ = [
    # API Server
    "LLMAPIService",
    "get_llm_api_service",
    "ensure_service_running",
    "start_llm_api_service",
    "stop_llm_api_service",
    "is_service_running",
    "open_docs",
    # Session Handler
    "APISessionHandler",
    "APIHistoryManager",
    "StreamContext",
    # Isolated Context
    "IsolatedChatContext",
    "IsolatedContextRegistry",
]