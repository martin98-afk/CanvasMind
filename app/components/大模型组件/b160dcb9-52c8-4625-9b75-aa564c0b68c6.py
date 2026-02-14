# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
base_path = Path(__file__).parent.parent / "base.py" if (Path(__file__).parent.parent / "base.py").exists() else Path(__file__).parent.parent.parent / "base.py"
spec = importlib.util.spec_from_file_location("base", str(base_path))
base_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base_module)

# 导入所需项目
BaseComponent = base_module.BaseComponent
PortDefinition = base_module.PortDefinition
PropertyDefinition = base_module.PropertyDefinition
PropertyType = base_module.PropertyType
ArgumentType = base_module.ArgumentType
ConnectionType = base_module.ConnectionType



class MCPToolCallingAgentComponent(BaseComponent):
    name = "MCP工具调用智能体"
    category = "大模型组件"
    description = "使用预发现的MCP工具字典执行推理（输出历史不含工具调用中间过程）"
    requirements = "openai,fastmcp>=2.3.0,orjson"
    
    inputs = [
        PortDefinition(name="input_data", label="用户输入", type=ArgumentType.TEXT),
        PortDefinition(name="history", label="对话历史", type=ArgumentType.JSON),
        PortDefinition(name="tools_dict", label="工具字典", type=ArgumentType.JSON),
        PortDefinition(name="mcp_metadata", label="MCP元数据", type=ArgumentType.JSON),
    ]
    outputs = [
        PortDefinition(name="response", label="最终回复", type=ArgumentType.TEXT),
        PortDefinition(name="raw_output", label="原始响应", type=ArgumentType.JSON),
        PortDefinition(name="history", label="更新后历史", type=ArgumentType.JSON),
        PortDefinition(name="tool_calls", label="工具调用记录", type=ArgumentType.JSON),
    ]
    
    properties = {
        "model": PropertyDefinition(
            type=PropertyType.VARIABLE,
            default="全局变量",
            label="模型参数",
        ),
        "system_prompt": PropertyDefinition(
            type=PropertyType.LONGTEXT,
            default="""你是一个强大的AI助手，可以调用外部工具解决复杂问题。请根据需要主动调用合适的工具。""",
            label="系统提示词",
        ),
        "temperature": PropertyDefinition(
            type=PropertyType.RANGE,
            default="0.7",
            label="温度（随机性）",
            min=0.0,
            max=1.0,
            step=0.1,
        ),
        "max_tokens": PropertyDefinition(
            type=PropertyType.INT,
            default=2000,
            label="最大生成长度",
        ),
        "max_tool_rounds": PropertyDefinition(
            type=PropertyType.INT,
            default=5,
            label="最大工具调用轮数",
            min=1,
            max=10,
        ),
        "tool_timeout": PropertyDefinition(
            type=PropertyType.INT,
            default=30,
            label="单次工具调用超时(秒)",
            min=5,
            max=120,
        ),
        "enable_tools": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="启用工具调用",
        ),
        "intervent": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="结果干预",
        ),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._client_cache = {}

    def _get_tools_list(self, tools_dict):
        if not tools_dict or not isinstance(tools_dict, dict):
            return []
        return list(tools_dict.values())

    def _execute_tool_call(self, tool_name: str, arguments: dict, mcp_metadata: dict) -> dict:
        import asyncio
        import sys
        import time
        import hashlib
        import json as json_lib
        
        config = mcp_metadata.get("original_config", {})
        config_hash = hashlib.md5(json_lib.dumps(config, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        
        if config_hash not in self._client_cache:
            try:
                from fastmcp import Client
                self._client_cache[config_hash] = Client(config)
            except ImportError as e:
                return {
                    "success": False,
                    "error": f"fastmcp未安装: {e}",
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "timestamp": time.time()
                }
        
        client = self._client_cache[config_hash]
        
        async def _call():
            try:
                async with client:
                    result = await asyncio.wait_for(
                        client.call_tool(tool_name, arguments),
                        timeout=float(self.params.tool_timeout)
                    )
                content = result.get("content", str(result)) if isinstance(result, dict) else str(result)
                return {
                    "success": True,
                    "content": content,
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "timestamp": time.time()
                }
            except asyncio.TimeoutError:
                return {
                    "success": False,
                    "error": f"工具 '{tool_name}' 超时（{self.params.tool_timeout}s）",
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "timestamp": time.time()
                }
            except Exception as e:
                error_msg = str(e)
                if "not connected" in error_msg.lower():
                    error_msg = "MCP客户端连接错误"
                return {
                    "success": False,
                    "error": f"工具 '{tool_name}' 失败: {error_msg}",
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "timestamp": time.time()
                }
        
        try:
            return asyncio.run(_call())
        except RuntimeError as e:
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                return loop.run_until_complete(_call())
            raise

    def _parse_history(self, history_input):
        import json as json_lib
        if not history_input:
            return []
        if isinstance(history_input, str):
            try:
                return json_lib.loads(history_input)
            except json_lib.JSONDecodeError:
                return []
        return history_input if isinstance(history_input, list) else []

    def _clean_history_for_output(self, history):
        """仅用于最终输出：移除所有工具调用相关消息"""
        clean = []
        for msg in history:
            if not isinstance(msg, dict):
                continue
            
            role = msg.get("role", "")
            if role == "user":
                clean.append(msg)
            elif role == "assistant":
                # 仅保留不含工具调用的纯文本回复
                if "tool_calls" not in msg and "function_call" not in msg and msg.get("content"):
                    clean.append({
                        "role": "assistant",
                        "content": msg["content"]
                    })
            # 显式跳过 role="tool" 的消息
        return clean

    def run(self, params, inputs):
        self.params, self.inputs = params, inputs
        # === 所有导入严格放在函数开头 ===
        import json as json_lib
        import orjson
        from openai import OpenAI
        
        # 1. 获取工具和元数据
        tools_dict = getattr(inputs, 'tools_dict', None)
        mcp_metadata = getattr(inputs, 'mcp_metadata', None)
        
        if params.enable_tools and (not tools_dict or not mcp_metadata):
            self.logger.warning("⚠️ 未提供工具字典或MCP元数据，降级为普通聊天模式")
            params.enable_tools = False
        
        # 2. 准备输入
        user_input = (inputs.input_data.strip() if inputs and inputs.input_data else "") or "你好"
        raw_history = getattr(inputs, 'history', None)
        history = self._parse_history(raw_history)
        # === 核心修复：推理时使用完整历史（含工具调用）===
        # ❌ 错误做法：messages_for_inference = _clean_history(history) + [user_input]
        # ✅ 正确做法：直接使用原始历史（模型需要看到工具调用结果才能决策）
        messages_for_inference = [{"role": "system", "content": params.system_prompt}]
        messages_for_inference.extend(history)  # ✅ 完整历史（可能含之前的tool_calls/tool）
        messages_for_inference.append({"role": "user", "content": user_input})
        
        # 3. 模型配置
        model_config = params.model[1]
        api_key = model_config.get("API_KEY", "").strip()
        api_url = model_config.get("API_URL", "").strip() or "https://api.openai.com/v1"
        model_name = model_config.get("模型名称", "gpt-4o").strip()
        
        client = OpenAI(api_key=api_key, base_url=api_url)
        
        # 4. 工具调用主循环
        tool_calls_log = []
        max_rounds = int(params.max_tool_rounds)
        current_round = 0
        final_reply = ""
        
        while current_round < max_rounds:
            current_round += 1
            
            tools_list = self._get_tools_list(tools_dict if params.enable_tools else {})
            tools_arg = tools_list if tools_list else None
            
            # 调用模型（使用完整历史）
            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=messages_for_inference,  # ✅ 完整上下文
                    temperature=float(params.temperature),
                    max_tokens=int(params.max_tokens),
                    tools=tools_arg,
                    tool_choice="auto" if tools_arg else None
                )
                message = response.choices[0].message
                
            except Exception as e:
                raise RuntimeError(f"❌ 模型调用失败: {str(e)}") from e
            
            # 无工具调用 → 返回最终答案
            if not message.tool_calls:
                final_reply = message.content.strip() if message.content else ""
                messages_for_inference.append({"role": "assistant", "content": final_reply})
                break
            
            # 保存含tool_calls的assistant消息
            messages_for_inference.append(message)
            
            # 执行工具调用
            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                try:
                    arguments = orjson.loads(tool_call.function.arguments)
                except Exception as e:
                    arguments = {}
                    self.logger.warning(f"⚠️ 参数解析失败 ({func_name}): {e}")
                
                tool_result = self._execute_tool_call(func_name, arguments, mcp_metadata)
                tool_calls_log.append(tool_result)
                
                # 构建tool response（添加到推理历史，供下一轮模型决策）
                tool_response = {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": func_name,
                    "content": (
                        tool_result["content"] if tool_result["success"] 
                        else f"❌ {tool_result['error']}"
                    )
                }
                messages_for_inference.append(tool_response)  # ✅ 关键：让模型看到工具结果
            
            # 安全终止
            recent_calls = tool_calls_log[-len(message.tool_calls):] if message.tool_calls else []
            if recent_calls and all(not call["success"] for call in recent_calls):
                final_reply = "⚠️ 所有工具调用失败"
                messages_for_inference.append({"role": "assistant", "content": final_reply})
                break
        else:
            final_reply = message.content.strip() if message.content else "⚠️ 已达到最大工具调用轮数"
            messages_for_inference.append({"role": "assistant", "content": final_reply})
        
        # 5. 人工干预
        if getattr(params, 'intervent', False):
            try:
                final_reply = self.emit_interactive_message(
                    method="ask_user",
                    params={
                        "title": "✅ 确认结果",
                        "message": "",
                        "schema": {"reply": {"label": "回复", "default": final_reply, "type": "textarea"}}
                    }
                ).get("reply", final_reply)
            except Exception as e:
                self.logger.warning(f"⚠️ 人工干预失败: {e}")
        
        # === 6. 关键：仅在最终输出时清洗历史（不影响推理）===
        # 6.1 清洗原始输入历史（移除可能残留的工具调用）
        clean_input_history = self._clean_history_for_output(history)
        
        # 6.2 构建当前轮次的纯净对话
        current_turn = [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": final_reply}
        ]
        
        # 6.3 合并为输出历史
        output_history = clean_input_history + current_turn
        
        # 7. 返回结果
        return {
            "response": final_reply,
            "raw_output": response.model_dump() if 'response' in locals() else {},
            "history": output_history,  # ✅ 纯净输出（不含工具调用）
            "tool_calls": tool_calls_log  # 完整工具调用记录（用于调试）
        }

    def teardown(self):
        self._client_cache.clear()
        super().teardown()