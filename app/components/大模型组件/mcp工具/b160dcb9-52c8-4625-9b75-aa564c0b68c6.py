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
    category = "大模型组件/mcp工具"
    description = "使用预发现的MCP工具字典执行推理（输出历史不含工具调用中间过程），支持超限强制总结"
    requirements = "openai,fastmcp>=2.3.0,orjson,nest_asyncio"
    
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
            default="""#### 1. 角色定义 (Role Definition)

你是一个拥有工具调用能力的智能助手。你的目标是根据用户请求，通过调用提供的函数（Tools）来获取信息，并最终向用户提供一个简洁、准确的总结性回答。


#### 2. 核心指令 (Core Instructions - **关键防死循环逻辑**)

请严格遵守以下执行流程：

1. **思考 (Thought)**: 在采取任何行动之前，先分析当前对话历史。
   - 问自己：我是否已经拥有了回答用户问题所需的所有信息？
   - 如果是 -> **必须停止调用工具**，直接生成最终回复。
   - 如果否 -> 思考缺少什么信息，并选择最合适的工具来获取。

2. **去重检查 (Duplicate Check)**:
   - **绝对禁止**使用相同的参数重复调用同一个工具，除非上一次调用返回了“超时”或“网络错误”。
   - 如果上一次工具调用返回了结果（即使是空结果或错误提示），**不要**再次尝试相同的操作。请尝试不同的参数，或者告知用户无法完成。

3. **停止条件 (Stop Condition)**:
   - 当工具返回的结果足以回答用户问题时，或者当你尝试了所有合理的工具/参数组合仍无法获取信息时，**必须停止调用**。
   - 此时，请根据已知信息生成最终回复，如果任务失败，请明确告知用户原因。

#### 3. 响应格式 (Response Protocol)

- 不要直接把工具返回的原始 JSON 数据扔给用户。
- 你必须将工具返回的数据**总结**为人类可读的自然语言。
- 如果需要进行多步操作，每一步结束后都要重新评估是否可以结束任务。

""",
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
        ),
        "tool_timeout": PropertyDefinition(
            type=PropertyType.INT,
            default=30,
            label="单次工具调用超时(秒)",
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
        import asyncio
        try:
            self._loop = asyncio.get_event_loop()
            if self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        except RuntimeError:  # 无当前循环
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
        
        # 应用 nest_asyncio 允许在运行中的循环中嵌套调用
        try:
            import nest_asyncio
            nest_asyncio.apply()
        except ImportError:
            pass

    def _get_tools_list(self, tools_dict):
        if not tools_dict or not isinstance(tools_dict, dict):
            return []
        return list(tools_dict.values())

    def _execute_tool_call(self, tool_name: str, arguments: dict, mcp_metadata: dict) -> dict:
        import asyncio
        import time
        import hashlib
        import json as json_lib
        
        config = mcp_metadata.get("original_config", {})
        config_str = json_lib.dumps(config, sort_keys=True, ensure_ascii=False)
        config_hash = hashlib.md5(config_str.encode()).hexdigest()
        
        # ===== 1. 获取或初始化客户端 =====
        if config_hash not in self._client_cache:
            try:
                from fastmcp import Client
                client = Client(config)
                # 存储客户端 + 连接状态 + 异步锁（防并发）
                self._client_cache[config_hash] = {
                    "client": client,
                    "connected": False,
                    "lock": asyncio.Lock()
                }
                self.logger.info(f"🆕 MCP客户端初始化 (hash: {config_hash[:8]})")
            except ImportError as e:
                return {
                    "success": False,
                    "error": f"fastmcp未安装: {e}",
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "timestamp": time.time()
                }
        
        client_info = self._client_cache[config_hash]
        client = client_info["client"]
        # =================================
        
        # ===== 2. 异步调用函数（在组件的统一事件循环中执行）=====
        async def _call():
            # 使用锁防止并发连接
            async with client_info["lock"]:
                # 检查连接状态（通过私有属性 _transport 判断，fastmcp 2.3+ 有效）
                if not client_info["connected"] or getattr(client, "_transport", None) is None:
                    self.logger.debug(f"🔌 建立MCP连接 (hash: {config_hash[:8]})")
                    await client.__aenter__()  # 手动建立连接
                    client_info["connected"] = True
                    self.logger.debug(f"✅ MCP连接建立成功")
            
            try:
                result = await asyncio.wait_for(
                    client.call_tool(tool_name, arguments),
                    timeout=float(self.params.tool_timeout)
                )
                content = "\n\n".join([item.text for item in result.content])
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
                    error_msg = "MCP客户端连接意外断开（可能服务崩溃）"
                    # 重置连接状态，下次调用会重建
                    client_info["connected"] = False
                return {
                    "success": False,
                    "error": f"工具 '{tool_name}' 失败: {error_msg}",
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "timestamp": time.time()
                }
        
        # ===== 3. 在组件的统一事件循环中执行（关键！避免循环漂移）=====
        return self._loop.run_until_complete(_call())

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
        import time
        self.params = params
        start_time = time.time()
        self.logger.info(f"🚀 MCP工具调用智能体开始执行 | 输入: '{inputs.input_data[:50]}...' | 工具启用: {params.enable_tools}")
        
        # === 所有导入严格放在函数开头 ===
        import sys
        import json as json_lib
        import orjson
        from openai import OpenAI
        original_stderr = sys.stderr
        try:
            sys.stderr = sys.__stderr__
            
            # 1. 获取工具和元数据
            tools_dict = getattr(inputs, 'tools_dict', None)
            mcp_metadata = getattr(inputs, 'mcp_metadata', None)
            self.logger.info(f"🔧 工具字典状态: {'✓ 有效' if tools_dict else '✗ 空'} | MCP元数据: {'✓ 有效' if mcp_metadata else '✗ 空'}")
            
            if params.enable_tools and (not tools_dict or not mcp_metadata):
                self.logger.warning("⚠️ 未提供工具字典或MCP元数据，降级为普通聊天模式")
                params.enable_tools = False
            
            # 2. 准备输入
            user_input = (inputs.input_data.strip() if inputs and inputs.input_data else "") or "你好"
            raw_history = getattr(inputs, 'history', None)
            history_parse_start = time.time()
            history = self._parse_history(raw_history)
            self.logger.info(f"📜 历史记录解析完成 ({time.time() - history_parse_start:.3f}s) | 消息数: {len(history)}")
            
            messages_for_inference = [{"role": "system", "content": params.system_prompt}]
            messages_for_inference.extend(history)
            messages_for_inference.append({"role": "user", "content": user_input})
            
            # 3. 模型配置
            model_config = params.model[1]
            api_key = model_config.get("API_KEY", "").strip()
            api_url = model_config.get("API_URL", "").strip() or "https://api.openai.com/v1"
            model_name = model_config.get("模型名称", "gpt-4o").strip()
            self.logger.info(f"🤖 模型配置: {model_name} | API: {api_url[:30]}... | 温度: {params.temperature} | MaxTokens: {params.max_tokens}")
            
            client = OpenAI(api_key=api_key[:5] + "*****" if api_key else "", base_url=api_url)  # 脱敏API_KEY
            
            # 4. 工具调用主循环
            tool_calls_log = []
            max_rounds = int(params.max_tool_rounds)
            current_round = 0
            final_reply = ""
            self.logger.info(f"🔄 启动工具调用循环 | 最大轮数: {max_rounds} | 单次超时: {params.tool_timeout}s")
            
            # 循环逻辑
            while current_round < max_rounds:
                current_round += 1
                round_start = time.time()
                self.logger.info(f"🔢 === 第 {current_round}/{max_rounds} 轮推理开始 ===")
                
                tools_list = self._get_tools_list(tools_dict if params.enable_tools else {})
                tools_arg = tools_list if tools_list else None
                self.logger.info(f"🛠️  可用工具数: {len(tools_list)}" if tools_list else "💬 本轮禁用工具调用")
                
                # 调用模型
                model_call_start = time.time()
                try:
                    self.logger.info(f"🧠 调用模型进行推理 (消息历史长度: {len(messages_for_inference)})")
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=messages_for_inference,
                        temperature=float(params.temperature),
                        max_tokens=int(params.max_tokens),
                        tools=tools_arg,
                        tool_choice="auto" if tools_arg else None
                    )
                    message = response.choices[0].message
                    self.logger.info(f"✅ 模型响应接收 ({time.time() - model_call_start:.3f}s) | 触发工具调用: {bool(message.tool_calls)}")
                    
                except Exception as e:
                    self.logger.exception(f"❌ 模型调用失败: {str(e)}")
                    raise RuntimeError(f"❌ 模型调用失败: {str(e)}") from e
                
                # 无工具调用 → 返回最终答案
                if not message.tool_calls:
                    final_reply = message.content.strip() if message.content else ""
                    messages_for_inference.append({"role": "assistant", "content": final_reply})
                    self.logger.info(f"🔚 无工具调用，生成最终回复 | 长度: {len(final_reply)}")
                    break
                
                # 保存含tool_calls的assistant消息
                messages_for_inference.append(message)
                self.logger.info(f"🔧 检测到 {len(message.tool_calls)} 个工具调用请求")
                
                # 执行工具调用
                for idx, tool_call in enumerate(message.tool_calls, 1):
                    func_name = tool_call.function.name
                    try:
                        arguments = orjson.loads(tool_call.function.arguments)
                        arg_summary = {k: str(v)[:20] + "..." if isinstance(v, str) and len(v) > 20 else v for k, v in list(arguments.items())[:3]}
                    except Exception as e:
                        arguments = {}
                        arg_summary = {}
                        self.logger.warning(f"⚠️ 参数解析失败 ({func_name}): {e}")
                    
                    self.logger.info(f"⚙️  执行工具 [{idx}/{len(message.tool_calls)}]: {func_name} | 参数概要: {arg_summary}")
                    tool_exec_start = time.time()
                    tool_result = self._execute_tool_call(func_name, arguments, mcp_metadata)
                    exec_duration = time.time() - tool_exec_start
                    
                    tool_calls_log.append(tool_result)
                    
                    if tool_result["success"]:
                        self.logger.info(f"✅ 工具 '{func_name}' 执行成功 ({exec_duration:.2f}s) | 内容预览: {str(tool_result['content'])[:100]}...")
                    else:
                        self.logger.error(f"❌ 工具 '{func_name}' 执行失败 ({exec_duration:.2f}s): {tool_result['error']}")
                    
                    # 构建tool response
                    tool_response = {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": func_name,
                        "content": tool_result["content"] if tool_result["success"] else f"❌ {tool_result['error']}"
                    }
                    messages_for_inference.append(tool_response)
                
                self.logger.info(f"⏱️  第 {current_round} 轮耗时: {time.time() - round_start:.3f}s")
            
            # === 循环结束后的强制总结 ===
            if not final_reply:
                self.logger.warning(f"⚠️ 达到最大轮数限制 ({max_rounds})，停止工具调用，强制生成总结")
                
                # 构造包含提示词的临时消息列表
                summary_messages = list(messages_for_inference)
                summary_messages.append({
                    "role": "user", 
                    "content": "已达到最大工具调用轮数限制。请根据目前已有的工具执行结果，对用户的问题进行总结性回答，不要尝试再次调用工具。"
                })
                
                try:
                    summary_start = time.time()
                    self.logger.info(f"📝 发起强制总结推理 (上下文长度: {len(summary_messages)})")
                    
                    summary_response = client.chat.completions.create(
                        model=model_name,
                        messages=summary_messages, # 使用带提示的消息列表
                        temperature=float(params.temperature),
                        max_tokens=int(params.max_tokens),
                        tools=None,      # 关键：禁用工具
                        tool_choice=None # 关键：禁用工具选择
                    )
                    final_reply = summary_response.choices[0].message.content
                    messages_for_inference.append({"role": "assistant", "content": final_reply})
                    
                    self.logger.info(f"✅ 强制总结完成 ({time.time() - summary_start:.3f}s) | 长度: {len(final_reply)}")
                except Exception as e:
                    final_reply = f"⚠️ 已达到最大工具调用次数，且无法生成总结: {str(e)}"
                    messages_for_inference.append({"role": "assistant", "content": final_reply})
                    self.logger.error(f"❌ 强制总结失败: {e}")

            # 5. 人工干预
            if getattr(params, 'intervent', False):
                self.logger.info("✋ 启动人工干预流程")
                try:
                    intervent_start = time.time()
                    original_reply = final_reply[:100] + "..." if len(final_reply) > 100 else final_reply
                    final_reply = self.emit_interactive_message(
                        method="ask_user",
                        params={
                            "title": "✅ 确认结果",
                            "message": "",
                            "schema": {"reply": {"label": "回复", "default": final_reply, "type": "textarea"}}
                        }
                    ).get("reply", final_reply)
                    if final_reply != original_reply:
                        self.logger.info(f"✏️  人工干预完成 ({time.time() - intervent_start:.2f}s) | 回复已修改")
                    else:
                        self.logger.info(f"⏭️ 人工干预完成 ({time.time() - intervent_start:.2f}s) | 保留原始回复")
                except Exception as e:
                    self.logger.exception(f"⚠️ 人工干预失败: {e}")
            
            # 6. 历史记录清洗
            clean_start = time.time()
            clean_input_history = self._clean_history_for_output(history)
            current_turn = [
                {"role": "user", "content": user_input},
                {"role": "assistant", "content": final_reply}
            ]
            output_history = clean_input_history + current_turn
            self.logger.info(f"🧹 历史清洗完成 ({time.time() - clean_start:.3f}s) | 原始: {len(history)} → 清洗后: {len(output_history)} 条消息")
            
            # 7. 返回结果
            total_duration = time.time() - start_time
            self.logger.info(f"✅ MCP工具调用智能体执行完成 | 总耗时: {total_duration:.3f}s | 工具调用: {len(tool_calls_log)} 次 | 回复长度: {len(final_reply)}")
            self.logger.debug(f"💬 最终回复预览: {final_reply[:100]}...")
            
            return {
                "response": final_reply,
                "raw_output": response.model_dump() if 'response' in locals() else {},
                "history": output_history,
                "tool_calls": tool_calls_log
            }
            
        except Exception as e:
            self.logger.exception(f"💥 MCP智能体执行异常: {str(e)}")
            raise
        finally:
            sys.stderr = original_stderr
            self.logger.info(f"🔚 MCP工具调用智能体执行结束 | 总耗时: {time.time() - start_time:.3f}s")

    def teardown(self):
        self._client_cache.clear()