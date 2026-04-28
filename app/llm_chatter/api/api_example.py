# -*- coding: utf-8 -*-
"""
LLM Chatter API 使用示例

核心特性：
- 完全隔离的 API 调用（参考复制窗口的实现）
- 每个请求创建独立的 IsolatedChatContext
- 独立的 SessionManager、ToolExecutor、AgentManager
- API 调用与 UI 完全隔离，不会产生任何状态冲突
- 自动使用 UI 当前配置的模型
- 会话管理复用，数据持久化

API 文档：http://localhost:8765/docs

接口列表：
- GET  /sessions                    - 获取所有会话
- POST /sessions                    - 创建新会话
- GET  /sessions/{id}               - 获取会话详情
- DELETE /sessions/{id}              - 删除会话
- POST /sessions/{id}/chat/stream   - 流式对话（SSE）
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


def example_list_sessions():
    """获取所有会话列表"""
    response = httpx.get("http://localhost:8765/sessions", timeout=10.0)
    result = response.json()
    print("=== 会话列表 ===")
    sessions = result.get("sessions", [])
    if sessions:
        for s in sessions:
            print(f"  [{s['id'][:8]}...] {s['title']} ({s['message_count']} 条消息)")
    else:
        print("  (暂无会话)")
    print()


def example_create_session():
    """创建新会话"""
    response = httpx.post(
        "http://localhost:8765/sessions",
        json={"title": "API 测试会话"},
        timeout=10.0,
    )
    result = response.json()
    print("=== 创建会话 ===")
    print(f"Success: {result.get('success')}")
    if result.get('session'):
        session = result['session']
        print(f"Session ID: {session['id']}")
        print(f"Title: {session['title']}")
    print()
    return result.get("session", {}).get("id")


def example_get_session(session_id: str):
    """获取指定会话详情"""
    response = httpx.get(f"http://localhost:8765/sessions/{session_id}", timeout=10.0)
    result = response.json()
    print("=== 会话详情 ===")
    session = result.get("session", {})
    print(f"ID: {session['id']}")
    print(f"Title: {session['title']}")
    print(f"Messages: {len(session.get('messages', []))} 条")
    print()


def example_stream_chat(session_id: str):
    """流式对话（SSE）- 核心功能，复用 UI 对话逻辑
    
    支持：
    - 自动使用 UI 当前配置的模型
    - 完整工具调用能力
    - 实时流式响应
    - 会话自动保存
    """
    print("=== 流式对话 ===")
    print("-" * 40)
    
    with httpx.stream(
        "POST",
        f"http://localhost:8765/sessions/{session_id}/chat/stream",
        json={"message": "你好，请介绍一下你自己"},
        timeout=120.0,
    ) as response:
        full_content = ""
        
        for line in response.iter_lines():
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    event = data.get("event", "")
                    
                    if event == "content":
                        piece = data.get("data", {}).get("piece", "")
                        print(piece, end="", flush=True)
                        full_content += piece
                        
                    elif event == "tool_call_started":
                        tool_info = data.get("data", {})
                        print(f"\n\n[工具调用] {tool_info.get('tool_name')}", flush=True)
                        
                    elif event == "tool_result":
                        result_info = data.get("data", {})
                        print(f"[结果] {result_info.get('result', '')[:100]}...", flush=True)
                        
                    elif event == "error":
                        print(f"\n[错误] {data.get('data', {}).get('error')}")
                        break
                        
                    elif event == "complete":
                        print("\n")
                        print("-" * 40)
                        
                except json.JSONDecodeError:
                    continue
                    
    return full_content


def example_continue_chat(session_id: str):
    """继续对话（多轮）"""
    print("\n=== 继续对话 ===")
    print("-" * 40)
    
    with httpx.stream(
        "POST",
        f"http://localhost:8765/sessions/{session_id}/chat/stream",
        json={"message": "继续"},
        timeout=120.0,
    ) as response:
        for line in response.iter_lines():
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    event = data.get("event", "")
                    
                    if event == "content":
                        piece = data.get("data", {}).get("piece", "")
                        print(piece, end="", flush=True)
                    elif event == "error":
                        print(f"\n[错误] {data.get('data', {}).get('error')}")
                        break
                    elif event == "complete":
                        print("\n")
                        print("-" * 40)
                        
                except json.JSONDecodeError:
                    continue


def example_delete_session(session_id: str):
    """删除会话"""
    response = httpx.delete(
        f"http://localhost:8765/sessions/{session_id}",
        timeout=10.0,
    )
    result = response.json()
    print("=== 删除会话 ===")
    print(f"Success: {result.get('success')}")
    print(f"Message: {result.get('message')}")
    print()


def example_concurrent_chat(session_id: str):
    """并发对话测试 - 同时发送多个请求
    
    每个请求会创建独立的 ChatEngine 实例，互不干扰。
    """
    import concurrent.futures
    import threading
    
    results = {}
    counter = 0
    counter_lock = threading.Lock()
    
    def stream_chat(request_num: int) -> str:
        """单个请求"""
        with counter_lock:
            nonlocal counter
            counter += 1
            num = counter
        
        print(f"\n[请求 {num}] 开始...")
        content = ""
        
        try:
            with httpx.stream(
                "POST",
                f"http://localhost:8765/sessions/{session_id}/chat/stream",
                json={"message": f"你好，请回复「第{num}号请求」，简单介绍一下自己"},
                timeout=120.0,
            ) as response:
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            event = data.get("event", "")
                            if event == "content":
                                piece = data.get("data", {}).get("piece", "")
                                print(piece, end="", flush=True)
                                content += piece
                            elif event == "complete":
                                print("\n")
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            print(f"[请求 {num}] 错误: {e}")
        
        return content
    
    print("=" * 50)
    print("=== 并发对话测试 ===")
    print("同时发送 2 个请求...")
    print("=" * 50)
    
    # 并发执行
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(stream_chat, i) for i in range(1, 3)]
        concurrent.futures.wait(futures)
    
    print("\n所有请求完成！")


def example_get_current_config():
    """获取当前配置（自动使用 UI 配置）"""
    response = httpx.get("http://localhost:8765/config", timeout=10.0)
    result = response.json()
    print("=== 当前配置 ===")
    config = result.get("config", {})
    print(f"Model: {config.get('模型名称')}")
    print(f"API URL: {config.get('API_URL')}")
    print()


if __name__ == "__main__":
    print("=" * 50)
    print("LLM Chatter API 使用示例")
    print("(复用 UI 对话逻辑，支持并发)")
    print("=" * 50)

    # 健康检查
    try:
        example_health_check()
    except Exception as e:
        print(f"服务未运行: {e}")
        print("\n请确保 LLMChatter 窗口已打开，服务将自动启动。")
        exit(1)

    # 查看当前配置
    try:
        example_get_current_config()
    except Exception as e:
        print(f"获取配置失败: {e}")

    # 查看会话列表
    try:
        example_list_sessions()
    except Exception as e:
        print(f"获取会话列表失败: {e}")

    # 创建新会话
    session_id = None
    try:
        session_id = example_create_session()
    except Exception as e:
        print(f"创建会话失败: {e}")

    # 流式对话
    if session_id:
        try:
            example_stream_chat(session_id)
        except Exception as e:
            print(f"对话失败: {e}")
        
        # 继续对话
        try:
            example_continue_chat(session_id)
        except Exception as e:
            print(f"继续对话失败: {e}")
        
        # 并发测试（可选，取消注释运行）
        # try:
        #     example_concurrent_chat(session_id)
        # except Exception as e:
        #     print(f"并发测试失败: {e}")
        
        # 查看会话详情
        try:
            example_get_session(session_id)
        except Exception as e:
            print(f"获取会话详情失败: {e}")
        
        # 删除会话（测试用）
        try:
            example_delete_session(session_id)
        except Exception as e:
            print(f"删除会话失败: {e}")

    print("\n示例完成!")
