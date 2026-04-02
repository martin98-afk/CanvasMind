# -*- coding: utf-8 -*-
"""
API调用重试辅助工具
"""

import time
from functools import wraps
from loguru import logger


def is_retriable_error(e):
    """检查错误是否应该重试"""
    from openai import RateLimitError, APIError, APIConnectionError, APITimeoutError

    is_rate_limit = isinstance(e, RateLimitError)
    is_server_overload = isinstance(e, APIError) and "2064" in str(e)
    is_connection_error = isinstance(e, APIConnectionError)
    is_timeout = isinstance(e, APITimeoutError)

    return is_rate_limit or is_server_overload or is_connection_error or is_timeout


def get_error_type_name(e):
    """获取错误类型名称"""
    from openai import RateLimitError, APIError, APIConnectionError, APITimeoutError

    if isinstance(e, RateLimitError):
        return "RateLimit"
    elif isinstance(e, APIError) and "2064" in str(e):
        return "ServerOverload"
    elif isinstance(e, APIConnectionError):
        return "Connection"
    elif isinstance(e, APITimeoutError):
        return "Timeout"
    return "Unknown"


def retry_on_api_error(max_retries=3, retry_delay=5, backoff_multiplier=1):
    """
    API调用重试装饰器

    Args:
        max_retries: 最大重试次数
        retry_delay: 基础重试延迟（秒）
        backoff_multiplier: 退避倍数，例如2表示5s, 10s, 20s

    Usage:
        @retry_on_api_error(max_retries=3, retry_delay=5)
        def make_api_call():
            return client.chat.completions.create(...)
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e

                    if not is_retriable_error(e):
                        raise

                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (backoff_multiplier**attempt)
                        error_type = get_error_type_name(e)
                        logger.warning(
                            f"[API] {error_type} error (code 2064: Server Overload), "
                            f"retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})"
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error(
                            f"[API] {get_error_type_name(e)} error failed after {max_retries} attempts"
                        )

            raise last_error

        return wrapper

    return decorator


def create_api_call_with_retry(client, create_func, max_retries=3, retry_delay=5):
    """
    执行带重试的API调用

    Args:
        client: OpenAI客户端
        create_func: 调用chat.completions.create的函数
        max_retries: 最大重试次数
        retry_delay: 基础重试延迟（秒）

    Returns:
        API响应对象
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            return create_func()
        except Exception as e:
            last_error = e

            if not is_retriable_error(e):
                raise

            if attempt < max_retries - 1:
                wait_time = retry_delay * (attempt + 1)
                error_type = get_error_type_name(e)
                logger.warning(
                    f"[API] {error_type} error (code 2064: Server Overload), "
                    f"retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(wait_time)
            else:
                logger.error(
                    f"[API] {error_type} error failed after {max_retries} attempts"
                )

    raise last_error
