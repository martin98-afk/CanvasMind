# -*- coding: utf-8 -*-
"""
Token 估算模块 - 提供精确的 token 计数功能

支持多种模型编码:
- GPT-4, GPT-3.5 (cl100k_base)
- GPT-3 (r50k_base)
- Claude (cl100k_base)

自动降级到快速估算算法如果 tiktoken 不可用。
"""

import re
from functools import lru_cache
from typing import Dict, List, Optional, Union

# tiktoken 优先，否则降级
try:
    import tiktoken
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False
    tiktoken = None


# 编码映射
ENCODING_MAPPING = {
    # OpenAI 模型
    "gpt-4": "cl100k_base",
    "gpt-3.5-turbo": "cl100k_base",
    "gpt-3.5": "cl100k_base",
    "gpt-35-turbo": "cl100k_base",
    # Claude 模型 (使用相同编码)
    "claude": "cl100k_base",
    "claude-2": "cl100k_base",
    "claude-3": "cl100k_base",
    "claude-3-5": "cl100k_base",
    # GPT-3 及更早
    "gpt-3": "r50k_base",
    "davinci": "r50k_base",
    # 默认
    "default": "cl100k_base",
}


def _get_encoding_name(model: str = "gpt-4") -> str:
    """根据模型名称获取编码名称"""
    model = model.lower()
    for key, encoding in ENCODING_MAPPING.items():
        if key in model:
            return encoding
    return ENCODING_MAPPING["default"]


@lru_cache(maxsize=8)
def _get_encoder(encoding_name: str):
    """获取编码器实例 (带缓存)"""
    if not _TIKTOKEN_AVAILABLE:
        return None
    
    try:
        return tiktoken.get_encoding(encoding_name)
    except Exception:
        return None


def _fast_estimate_tokens(text: str) -> int:
    """
    快速估算算法 - 当 tiktoken 不可用时的降级方案
    
    基于 OpenAI 的经验公式 (保守估计):
    - 1 token ≈ 4 字符 (英文/混合)
    - 1 token ≈ 2 字符 (中文)
    - 使用 min() 避免过度估算
    
    适用于 tiktoken 不可用时的降级
    """
    if not text:
        return 0
    
    text_len = len(text)
    
    # 统计中文字符
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    non_chinese = text_len - chinese_chars
    
    # 中文每2字符算1 token，英文/其他每4字符算1 token
    # 同时与实际长度比较，取较小值保守估算
    estimated = chinese_chars // 2 + non_chinese // 4
    
    # 保守：确保不会超过原始文本长度太多
    # 对于中文，我们认为1:1是上限；对于英文，1:3是上限
    max_estimate = max(chinese_chars, non_chinese // 3)
    estimated = min(estimated, max_estimate)
    
    return max(1, estimated)


def _encode_with_tiktoken(text: str, model: str = "gpt-4") -> List[int]:
    """使用 tiktoken 编码文本为 token IDs"""
    encoder = _get_encoder(_get_encoding_name(model))
    if encoder:
        return encoder.encode(text, disallowed_special=())
    return None


def estimate_tokens(text: str, model: str = "gpt-4") -> int:
    """
    估算文本的 token 数量
    
    Args:
        text: 要估算的文本
        model: 模型名称 (用于选择编码)
    
    Returns:
        token 数量
    """
    if not text:
        return 0
    
    # 尝试使用 tiktoken
    encoder = _get_encoder(_get_encoding_name(model))
    if encoder:
        try:
            tokens = encoder.encode(text, disallowed_special=())
            return len(tokens)
        except Exception:
            pass
    
    # 降级到快速估算
    return _fast_estimate_tokens(text)


def count_messages_tokens(
    messages: List[Dict],
    model: str = "gpt-4",
    tools: Optional[List[Dict]] = None
) -> int:
    """
    计算消息列表的总 token 数
    
    OpenAI 消息格式费用计算:
    - 每条消息: 4 tokens (overhead)
    - role 字段: + tokens
    - content: + tokens
    - tool_calls: + tokens
    - tool_call_id: + tokens
    
    Args:
        messages: 消息列表
        model: 模型名称
        tools: 工具定义列表
    
    Returns:
        总 token 数
    """
    if not messages:
        return 0
    
    total = 0
    
    # 消息 overhead
    total += len(messages) * 4
    
    for msg in messages:
        role = msg.get("role", "")
        if role:
            total += estimate_tokens(role, model)
        
        # content 处理
        content = msg.get("content", "")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        total += estimate_tokens(item.get("text", ""), model)
                    elif item.get("type") == "image_url":
                        # 图片 token 估算 (简化版)
                        total += 85  # 图片基准开销
        elif content:
            total += estimate_tokens(content, model)
        
        # tool_calls 处理
        for tool_call in msg.get("tool_calls", []):
            if not isinstance(tool_call, dict):
                continue
            
            function = tool_call.get("function", {})
            total += 3  # tool_call overhead
            total += estimate_tokens(function.get("name", ""), model)
            total += estimate_tokens(function.get("arguments", "{}"), model)
        
        # tool_call_id 处理
        if msg.get("tool_call_id"):
            total += estimate_tokens(str(msg["tool_call_id"]), model)
    
    # 工具定义 tokens
    if tools:
        total += count_tools_tokens(tools, model)
    
    return total


def count_tools_tokens(tools: List[Dict], model: str = "gpt-4") -> int:
    """
    计算工具定义的总 token 数
    
    工具格式 (参考 OpenAI 文档):
    - type: 8 tokens
    - function: 14 tokens
    - name: + tokens
    - description: + tokens
    - parameters: + tokens
    """
    if not tools:
        return 0
    
    total = 0
    
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        
        tool_type = tool.get("type", "function")
        total += 8 if tool_type else 0
        
        function = tool.get("function", {})
        if function:
            total += 14
            
            name = function.get("name", "")
            if name:
                total += estimate_tokens(name, model)
            
            desc = function.get("description", "")
            if desc:
                total += estimate_tokens(desc, model)
            
            # parameters JSON string
            params = function.get("parameters")
            if params:
                params_str = str(params)
                total += estimate_tokens(params_str, model)
    
    return total


def count_response_tokens(
    prompt_tokens: int,
    model: str = "gpt-4",
    max_tokens: Optional[int] = None
) -> int:
    """
    计算响应可能的 token 数
    
    用于计算总费用/限制
    
    Args:
        prompt_tokens: 提示的 token 数
        model: 模型名称
        max_tokens: 最大生成 token 数
    
    Returns:
        估算的总 token 数
    """
    # 响应 overhead
    overhead = 3  # completion message overhead
    
    if max_tokens is not None:
        return prompt_tokens + overhead + max_tokens
    
    # 根据模型估算最大值
    limits = {
        "gpt-4": 8192,
        "gpt-4o": 16384,
        "gpt-3.5-turbo": 4096,
        "claude-3": 4096,
    }
    
    default_limit = limits.get(model.lower(), 4096)
    return prompt_tokens + overhead + default_limit


def truncate_text_to_token_limit(
    text: str,
    max_tokens: int,
    model: str = "gpt-4",
    suffix: str = "..."
) -> str:
    """
    将文本截断到指定的 token 限制
    
    Args:
        text: 原始文本
        max_tokens: 最大 token 数
        model: 模型名称
        suffix: 截断后缀
    
    Returns:
        截断后的文本
    """
    if not text:
        return text
    
    current_tokens = estimate_tokens(text, model)
    if current_tokens <= max_tokens:
        return text
    
    # 二分查找截断点
    left, right = 0, len(text)
    
    while left < right:
        mid = (left + right) // 2
        truncated = text[:mid]
        tokens = estimate_tokens(truncated, model)
        
        if tokens > max_tokens:
            right = mid - 1
        else:
            left = mid + 1
    
    result = text[:left]
    if suffix and left < len(text):
        # 保留 suffix 的空间
        suffix_tokens = estimate_tokens(suffix, model)
        available = max_tokens - suffix_tokens
        if available > 0:
            while estimate_tokens(result, model) > available:
                result = result[:-10]
            result += suffix
        else:
            result = suffix
    
    return result


class TokenCounter:
    """Token 计数器类 - 带状态和缓存"""
    
    def __init__(self, model: str = "gpt-4"):
        self.model = model
        self._cache: Dict[str, int] = {}
        self._cache_enabled = True
        self._miss_count = 0
        self._hit_count = 0
    
    def count(self, text: str, use_cache: bool = True) -> int:
        """计数 (带可选缓存)"""
        if not text:
            return 0
        
        if use_cache and self._cache_enabled:
            cache_key = hash(text)
            if cache_key in self._cache:
                self._hit_count += 1
                return self._cache[cache_key]
            self._miss_count += 1
        
        tokens = estimate_tokens(text, self.model)
        
        if use_cache and self._cache_enabled and self._miss_count < 100:
            self._cache[hash(text)] = tokens
        
        return tokens
    
    def count_messages(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None
    ) -> int:
        """计数消息列表"""
        return count_messages_tokens(messages, self.model, tools)
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        self._miss_count = 0
        self._hit_count = 0
    
    @property
    def cache_hit_rate(self) -> float:
        """缓存命中率"""
        total = self._hit_count + self._miss_count
        if total == 0:
            return 0.0
        return self._hit_count / total
    
    def enable_cache(self, enabled: bool = True):
        """启用/禁用缓存"""
        self._cache_enabled = enabled


# 全局默认实例
_default_counter: Optional[TokenCounter] = None


def get_default_counter(model: str = "gpt-4") -> TokenCounter:
    """获取默认的 TokenCounter 实例"""
    global _default_counter
    if _default_counter is None or _default_counter.model != model:
        _default_counter = TokenCounter(model)
    return _default_counter
