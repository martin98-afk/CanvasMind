# -*- coding: utf-8 -*-
"""
LLM Chatter API 使用示例

启动服务后（自动启动），可以通过 HTTP 调用与大模型对话。

API 文档：http://localhost:8765/docs
"""
import json
import time

import httpx


def example_health_check():
    """健康检查"""
    response = httpx.get("http://localhost:8765/health", timeout=10.0)
    result = response.json()
    print("=== 健康检查 ===")
    print(f"Status: {result}")
    print()


def example_get_providers():
    """获取服务商列表"""
    response = httpx.get("http://localhost:8765/providers", timeout=10.0)
    result = response.json()
    print("=== 服务商列表 ===")
    for p in result.get("providers", []):
        print(f"  - {p.get('name')}")
    print()


def example_get_current_config():
    """获取当前配置"""
    response = httpx.get("http://localhost:8765/config", timeout=10.0)
    result = response.json()
    print("=== 当前配置 ===")
    config = result.get("config", {})
    print(f"Provider: {result.get('provider_name')}")
    print(f"Model: {config.get('模型名称')}")
    print(f"API URL: {config.get('API_URL')}")
    print()


def example_switch_provider():
    """切换服务商"""
    response = httpx.post(
        "http://localhost:8765/providers/switch",
        json={"provider_name": "硅基流动"},
        timeout=10.0,
    )
    result = response.json()
    print("=== 切换服务商 ===")
    print(f"Result: {result}")
    print()


def example_basic_chat():
    """简单聊天示例"""
    response = httpx.post(
        "http://localhost:8765/chat",
        json={
            "message": "你好，请介绍一下你自己",
        },
        timeout=60.0,
    )
    result = response.json()
    print("=== 简单聊天 ===")
    print(f"Success: {result.get('success')}")
    print(f"Content: {result.get('content', '')[:200]}")
    print(f"Usage: {result.get('usage')}")
    print()


def example_with_system_prompt():
    """带系统提示的聊天"""
    response = httpx.post(
        "http://localhost:8765/chat",
        json={
            "message": "今天天气怎么样？",
            "system_prompt": "你是一个天气助手，请用简短的语言回答。",
        },
        timeout=60.0,
    )
    result = response.json()
    print("=== 带系统提示 ===")
    print(f"Content: {result.get('content', '')}")
    print()


def example_with_history():
    """带历史消息的聊天（多轮对话）"""
    response = httpx.post(
        "http://localhost:8765/chat",
        json={
            "message": "继续",
            "history": [
                {"role": "user", "content": "帮我写一个排序算法"},
                {"role": "assistant", "content": "好的，这里是一个快速排序的实现..."},
            ],
        },
        timeout=60.0,
    )
    result = response.json()
    print("=== 多轮对话 ===")
    print(f"Content: {result.get('content', '')[:300]}")
    print()


def example_stream_chat():
    """流式聊天示例"""
    print("=== 流式聊天 ===")
    with httpx.stream(
        "POST",
        "http://localhost:8765/chat/stream",
        json={"message": "写一首关于春天的诗"},
        timeout=120.0,
    ) as response:
        for line in response.iter_lines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                if "content" in data:
                    print(data["content"], end="", flush=True)
                elif data.get("error"):
                    print(f"\nError: {data['error']}")
                    break
                elif line == "data: [DONE]":
                    break
    print("\n")


def example_tools_call():
    """带工具调用的聊天示例"""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "获取指定城市的天气",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "城市名称"},
                    },
                    "required": ["city"],
                },
            },
        }
    ]

    response = httpx.post(
        "http://localhost:8765/tools/call",
        json={
            "message": "北京今天天气如何？",
            "tools": tools,
        },
        timeout=60.0,
    )
    result = response.json()
    print("=== 工具调用 ===")
    print(f"Content: {result.get('content', '')}")
    print(f"Finish Reason: {result.get('finish_reason')}")
    print(f"Tool Calls: {result.get('tool_calls')}")
    print()


if __name__ == "__main__":
    print("=" * 50)
    print("LLM Chatter API 使用示例")
    print("=" * 50)

    # 健康检查
    try:
        example_health_check()
    except Exception as e:
        print(f"服务未运行或无法连接: {e}")
        print("\n服务将在 LLMChatter 窗口打开时自动启动。")
        exit(1)

    # 查看服务商列表
    try:
        example_get_providers()
    except Exception as e:
        print(f"获取服务商列表失败: {e}")

    # 查看当前配置
    try:
        example_get_current_config()
    except Exception as e:
        print(f"获取配置失败: {e}")

    # 基本聊天
    try:
        example_basic_chat()
    except Exception as e:
        print(f"聊天请求失败: {e}")

    # 流式聊天
    try:
        example_stream_chat()
    except Exception as e:
        print(f"流式聊天失败: {e}")

    print("示例完成!")