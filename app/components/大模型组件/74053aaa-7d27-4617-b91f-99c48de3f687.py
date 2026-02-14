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


class FastMCPToolAgentComponent(BaseComponent):
    name = "FastMCP工具调用智能体(直接输入mcp配置)"
    category = "大模型组件"
    description = "原生支持HTTP MCP服务的专业工具调用智能体（使用fastmcp库，所有导入延迟加载）"
    requirements = "openai,fastmcp>=2.3.0,orjson"
    
    inputs = [
        PortDefinition(name="input_data", label="用户输入", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
        PortDefinition(name="history", label="对话历史", type=ArgumentType.JSON, connection=ConnectionType.SINGLE),
        PortDefinition(name="mcp_config", label="MCP配置", type=ArgumentType.JSON, connection=ConnectionType.SINGLE),
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
            default="""你是一个强大的AI助手，可以调用外部知识库工具解决复杂问题。请根据需要主动调用合适的工具。""",
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
        "enable_mcp": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="启用MCP工具调用",
        ),
        "mcp_auth_token": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="MCP认证Token (Bearer)",
            description="留空则从全局变量 MCP_SERVER_TOKEN 读取",
        ),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._fastmcp_client = None  # fastmcp.Client 实例
        self._available_tools = []
        self._tool_schemas = []
        self._mcp_initialized = False
        self._mcp_config_raw = None

    def setup(self):
        """组件初始化：仅缓存工具列表，不保持连接（符合fastmcp设计）"""
        # === 所有导入严格放在函数内 ===
        import os
        import asyncio
        import sys
        
        try:
            from fastmcp import Client
        except ImportError as e:
            self.logger.warning(f"fastmcp库未安装: {e}")
            self.logger.warning("请运行: pip install 'fastmcp>=2.3.0'")
            self.params.enable_mcp = False
            return
        
        if self._mcp_initialized:
            return
            
        if not self.params.enable_mcp:
            self.logger.info("MCP工具调用已手动禁用")
            return

        try:
            # 1. 获取并修复MCP配置
            mcp_config = getattr(self.inputs, 'mcp_config', None)
            if not mcp_config:
                self.logger.warning("未提供MCP配置")
                self.params.enable_mcp = False
                return
            
            # 2. 修复URL空格问题
            def fix_url_spaces(obj):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if k == "url" and isinstance(v, str):
                            obj[k] = v.strip()
                        elif isinstance(v, (dict, list)):
                            fix_url_spaces(v)
                elif isinstance(obj, list):
                    for item in obj:
                        fix_url_spaces(item)
            
            fix_url_spaces(mcp_config)
            self._mcp_config = mcp_config  # 保存配置用于后续重建
            
            # 3. 注入认证Token
            auth_token = getattr(self.params, 'mcp_auth_token', "").strip()
            if not auth_token:
                auth_token = os.environ.get("MCP_SERVER_TOKEN", "").strip()
            
            if auth_token:
                servers = mcp_config.get("mcpServers", {})
                for server_config in servers.values():
                    if not server_config.get("disabled") and (server_config.get("transport") == "http" or server_config.get("url")):
                        headers = server_config.setdefault("headers", {})
                        if "Authorization" not in headers and "authorization" not in headers:
                            headers["Authorization"] = f"Bearer {auth_token}"
            
            # 4. 创建Client实例（不立即连接）
            client = Client(mcp_config)
            
            # 5. 临时进入上下文获取工具列表（关键：用完即退出）
            async def _get_tools():
                async with client:  # 临时连接
                    tools = await client.list_tools()
                return tools  # 退出上下文后client仍可复用
            
            # 处理Windows事件循环
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    raise RuntimeError("嵌套事件循环")
            except RuntimeError:
                pass
            
            try:
                tools = asyncio.run(_get_tools())
            except RuntimeError as e:
                if sys.platform == "win32":
                    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    tools = loop.run_until_complete(_get_tools())
                else:
                    raise
            
            self._fastmcp_client = client
            self._available_tools = tools or []
            
            # === 6. 严格修复tools schema（核心：确保符合OpenAI规范）===
            self._tool_schemas = []
            for idx, tool in enumerate(self._available_tools):
                try:
                    # 统一提取工具属性
                    if isinstance(tool, dict):
                        tool_name = tool.get("name", f"tool_{idx}")
                        description = tool.get("description", "")
                        input_schema = tool.get("inputSchema")
                    else:
                        tool_name = getattr(tool, "name", f"tool_{idx}")
                        description = getattr(tool, "description", "")
                        input_schema = getattr(tool, "inputSchema", None)
                    
                    # 严格构建OpenAI兼容的parameters
                    parameters = {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                    
                    if isinstance(input_schema, dict):
                        props = input_schema.get("properties")
                        if isinstance(props, dict):
                            parameters["properties"] = props
                        
                        req = input_schema.get("required")
                        if isinstance(req, list):
                            parameters["required"] = [str(r) for r in req if isinstance(r, (str, int))]
                    
                    # 构建完整工具定义
                    openai_tool = {
                        "type": "function",
                        "function": {
                            "name": str(tool_name).strip() or f"tool_{idx}",
                            "description": str(description).strip(),
                            "parameters": parameters
                        }
                    }
                    
                    self._tool_schemas.append(openai_tool)
                    self.logger.debug(f"注册工具: {openai_tool['function']['name']}")
                    
                except Exception as e:
                    self.logger.warning(f"工具 {idx} 转换失败: {e}")
                    continue
            
            # 7. 更新UI选项
            choices = [tool["function"]["name"] for tool in self._tool_schemas]
            
            self._mcp_initialized = True
            self.logger.info(f"FastMCP初始化成功，注册 {len(self._tool_schemas)} 个有效工具: {choices}")
            
        except Exception as e:
            self.logger.error(f"FastMCP初始化失败: {str(e)}", exc_info=True)
            self._cleanup_mcp()
            self.params.enable_mcp = False
            self.logger.info("降级为普通聊天模式")

    def _cleanup_mcp(self):
        """清理fastmcp连接（导入在函数内）"""
        if self._fastmcp_client is not None:
            import asyncio
            import sys
            
            async def _cleanup():
                if self._fastmcp_client is not None:
                    await self._fastmcp_client.__aexit__(None, None, None)
            
            try:
                asyncio.run(_cleanup())
            except RuntimeError as e:
                if sys.platform == "win32":
                    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(_cleanup())
                # 其他异常忽略（避免阻塞teardown）
            except Exception as e:
                self.logger.warning(f"FastMCP连接清理异常: {e}")
            finally:
                self._fastmcp_client = None
        
        self._available_tools = []
        self._tool_schemas = []
        self._mcp_initialized = False

    def _execute_tool_call(self, tool_name: str, arguments: dict) -> dict:
        """执行工具调用（关键：每次调用自动进入async with上下文）"""
        import asyncio
        import sys
        import time
        
        if not self._fastmcp_client or not self._mcp_initialized:
            return {
                "success": False,
                "error": "MCP客户端未初始化",
                "tool_name": tool_name,
                "arguments": arguments,
                "timestamp": time.time()
            }

        async def _call():
            try:
                # === 核心修复：每次调用都进入async with上下文 ===
                async with self._fastmcp_client:  # 自动建立/复用连接
                    result = await asyncio.wait_for(
                        self._fastmcp_client.call_tool(tool_name, arguments),
                        timeout=float(self.params.tool_timeout)
                    )
                
                # 处理结果
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
                    "error": f"工具 {tool_name} 超时（{self.params.tool_timeout}s）",
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "timestamp": time.time()
                }
            except Exception as e:
                # 捕获连接错误并提供明确提示
                if "not connected" in str(e).lower() or "context manager" in str(e).lower():
                    return {
                        "success": False,
                        "error": "工具调用失败: 客户端未连接。请确保在async with上下文中调用（已自动修复）",
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "timestamp": time.time()
                    }
                return {
                    "success": False,
                    "error": f"工具 {tool_name} 失败: {str(e)}",
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
        """安全解析历史记录"""
        import json
        
        if not history_input:
            return []
        if isinstance(history_input, str):
            try:
                return json.loads(history_input)
            except json.JSONDecodeError:
                return []
        return history_input if isinstance(history_input, list) else []

    def run(self, params, inputs):
        """主执行逻辑（所有导入在函数开头）"""
        self.params, self.inputs = params, inputs
        # === 所有导入集中在此处 ===
        import orjson
        from openai import OpenAI
        
        # 1. 确保MCP已初始化
        if params.enable_mcp and not self._mcp_initialized:
            self.setup()
        
        # 2. 准备输入
        user_input = (inputs.input_data.strip() if inputs and inputs.input_data else "") or "你好"
        history = self._parse_history(getattr(inputs, 'history', None))
        
        # 3. 构建消息历史
        messages = [{"role": "system", "content": params.system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_input})
        
        # 4. 获取模型配置
        model_config = params.model[1]
        api_key = model_config.get("API_KEY", "").strip()
        api_url = model_config.get("API_URL", "").strip() or "https://api.openai.com/v1"
        model_name = model_config.get("模型名称", "gpt-4o").strip()
        
        client = OpenAI(api_key=api_key, base_url=api_url)
        
        # 5. 工具调用主循环
        tool_calls_log = []
        max_rounds = int(params.max_tool_rounds)
        current_round = 0
        final_reply = ""
        
        while current_round < max_rounds:
            current_round += 1
            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=float(params.temperature),
                    max_tokens=int(params.max_tokens),
                    tools=self._tool_schemas  or None,
                    tool_choice="auto" if self._available_tools else None
                )
                message = response.choices[0].message
                
            except Exception as e:
                raise RuntimeError(f"模型调用失败: {str(e)}") from e
            
            # 无工具调用
            if not message.tool_calls:
                final_reply = message.content.strip() if message.content else ""
                messages.append({"role": "assistant", "content": final_reply})
                break
            
            # 保存assistant消息
            messages.append(message)
            
            # 执行工具调用
            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                try:
                    arguments = orjson.loads(tool_call.function.arguments)
                except Exception as e:
                    arguments = {}
                    self.logger.warning(f"参数解析失败 ({func_name}): {e}")
                
                tool_result = self._execute_tool_call(func_name, arguments)
                tool_calls_log.append(tool_result)
                
                tool_response = {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": func_name,
                    "content": (
                        tool_result["content"] if tool_result["success"] 
                        else f"❌ 工具调用失败: {tool_result['error']}"
                    )
                }
                messages.append(tool_response)
            
            # 安全终止
            recent_calls = tool_calls_log[-len(message.tool_calls):] if message.tool_calls else []
            if recent_calls and all(not call["success"] for call in recent_calls):
                final_reply = "⚠️ 所有工具调用失败，无法继续处理请求。请检查MCP服务器状态或认证配置。"
                messages.append({"role": "assistant", "content": final_reply})
                break
        else:
            final_reply = message.content.strip() if message.content else "⚠️ 已达到最大工具调用轮数。"
            messages.append({"role": "assistant", "content": final_reply})
        
        # 6. 人工干预
        if params.intervent:
            try:
                final_reply = self.emit_interactive_message(
                    method="ask_user",
                    params={
                        "title": "请确认生成结果",
                        "message": "",
                        "schema": {
                            "reply": {
                                "label": "最终回复",
                                "default": final_reply,
                                "type": "textarea"
                            }
                        }
                    }
                ).get("reply", final_reply)
                if messages and messages[-1]["role"] == "assistant":
                    messages[-1]["content"] = final_reply
            except Exception as e:
                self.logger.warning(f"人工干预失败: {e}")
        
        # 7. 返回结果
        return {
            "response": final_reply,
            "raw_output": response.model_dump() if 'response' in locals() else {},
            "history": messages[1:],
            "tool_calls": tool_calls_log
        }

    def teardown(self):
        """组件销毁（清理资源）"""
        self._cleanup_mcp()
        super().teardown()