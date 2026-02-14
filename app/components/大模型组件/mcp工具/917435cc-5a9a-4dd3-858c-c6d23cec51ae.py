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


class MCPToolDiscoveryComponent(BaseComponent):
    name = "MCP工具发现"
    category = "大模型组件/mcp工具"
    description = "连接MCP服务器并返回工具字典（tool_name → schema 映射）"
    requirements = "fastmcp>=2.3.0"
    
    inputs = [
        PortDefinition(name="mcp_config", label="MCP配置", type=ArgumentType.JSON),
    ]
    outputs = [
        PortDefinition(name="tools_dict", label="工具字典", type=ArgumentType.JSON),
        PortDefinition(name="tool_names", label="工具名称列表", type=ArgumentType.JSON),
        PortDefinition(name="mcp_metadata", label="MCP元数据", type=ArgumentType.JSON),
    ]
    
    properties = {
        "mcp_auth_token": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="MCP认证Token (Bearer)",
        ),
        "timeout": PropertyDefinition(
            type=PropertyType.INT,
            default=30,
            label="发现超时(秒)",
        ),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def run(self, params, inputs):
        """执行工具发现并返回字典格式（所有导入在函数内）"""
        # === 所有导入严格放在函数开头 ===
        import json as json_lib
        import asyncio
        import sys
        import time
        import os
        import copy
        
        # 1. 获取并验证配置
        mcp_config = getattr(inputs, 'mcp_config', None)
        
        if not mcp_config:
            raise RuntimeError("未提供MCP配置")
        
        # 2. 深拷贝配置避免污染
        config_copy = copy.deepcopy(mcp_config)
        
        # 3. 修复URL空格问题（递归）
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
        
        fix_url_spaces(config_copy)
        
        # 4. 注入认证Token（三重优先级）
        auth_token = getattr(params, 'mcp_auth_token', "").strip()
        if not auth_token:
            auth_token = os.environ.get("MCP_SERVER_TOKEN", "").strip()
        
        if auth_token:
            servers = config_copy.get("mcpServers", {})
            injected = []
            for name, server_config in servers.items():
                if not server_config.get("disabled") and (server_config.get("transport") == "http" or server_config.get("url")):
                    headers = server_config.setdefault("headers", {})
                    if "Authorization" not in headers and "authorization" not in headers:
                        headers["Authorization"] = f"Bearer {auth_token}"
                        injected.append(name)
            if injected:
                self.logger.info(f"已为MCP服务器注入Bearer Token: {', '.join(injected)}")
        
        # 5. 导入fastmcp并发现工具
        try:
            from fastmcp import Client
        except ImportError as e:
            raise RuntimeError(
                f"fastmcp库未安装或版本过低: {e}. 请运行: pip install 'fastmcp>=2.3.0'"
            ) from e
        
        # 6. 异步发现工具（自动管理连接上下文）
        async def _discover_tools():
            client = Client(config_copy)
            async with client:  # 自动建立连接
                tools = await asyncio.wait_for(
                    client.list_tools(),
                    timeout=float(getattr(params, 'timeout', 30))
                )
            return tools
        
        # 7. 处理事件循环（Windows兼容）
        try:
            raw_tools = asyncio.run(_discover_tools())
        except RuntimeError as e:
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                raw_tools = loop.run_until_complete(_discover_tools())
            else:
                raise
        except asyncio.TimeoutError:
            raise RuntimeError(f"MCP工具发现超时（{params.timeout}s）")
        except Exception as e:
            raise RuntimeError(f"MCP工具发现失败: {str(e)}") from e
        
        # 8. 转换为字典格式 {tool_name: openai_schema}
        tools_dict = {}
        tool_names = []
        
        for idx, tool in enumerate(raw_tools):
            try:
                # 统一提取工具属性（兼容字典/对象）
                if isinstance(tool, dict):
                    tool_name = tool.get("name", f"tool_{idx}")
                    description = tool.get("description", "")
                    input_schema = tool.get("inputSchema")
                else:
                    tool_name = getattr(tool, "name", f"tool_{idx}")
                    description = getattr(tool, "description", "")
                    input_schema = getattr(tool, "inputSchema", None)
                
                # 清理工具名
                tool_name = str(tool_name).strip()
                if not tool_name:
                    tool_name = f"tool_{idx}"
                    self.logger.warning(f"工具 {idx} 名称为空，使用回退名: {tool_name}")
                
                # 严格构建OpenAI兼容的parameters
                parameters = {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
                
                if isinstance(input_schema, dict):
                    props = input_schema.get("properties")
                    if isinstance(props, dict):
                        # 过滤非法属性名（OpenAI要求属性名符合JSON Schema）
                        safe_props = {}
                        for prop_key, prop_val in props.items():
                            if isinstance(prop_key, str) and prop_key:
                                safe_props[prop_key] = prop_val
                        parameters["properties"] = safe_props
                    
                    req = input_schema.get("required")
                    if isinstance(req, list):
                        # 过滤非字符串/整数的required项
                        parameters["required"] = [
                            str(r) for r in req 
                            if isinstance(r, (str, int)) and str(r).strip()
                        ]
                
                # 构建OpenAI工具schema
                openai_schema = {
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": str(description).strip(),
                        "parameters": parameters
                    }
                }
                
                # 检查重复工具名（添加后缀避免覆盖）
                original_name = tool_name
                counter = 1
                while tool_name in tools_dict:
                    tool_name = f"{original_name}_{counter}"
                    counter += 1
                    self.logger.warning(f"工具名重复，重命名为: {tool_name}")
                
                tools_dict[tool_name] = openai_schema
                tool_names.append(tool_name)
                
                self.logger.debug(
                    f"注册工具: {tool_name} | 参数: {list(parameters['properties'].keys())}"
                )
            
            except Exception as e:
                self.logger.warning(f"工具 {idx} 转换失败: {e}")
                continue
        
        # 9. 构建MCP元数据
        mcp_metadata = {
            "original_config": config_copy,
            "auth_injected": bool(auth_token),
            "discovery_timestamp": time.time(),
            "discovery_time_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "tool_count": len(tools_dict),
            "tool_names": tool_names,
            "server_names": list(config_copy.get("mcpServers", {}).keys())
        }
        
        self.logger.info(f"✓ 成功发现 {len(tools_dict)} 个MCP工具: {tool_names}")
        
        # 10. 返回结果
        return {
            "tools_dict": tools_dict,           # {tool_name: schema}
            "tool_names": tool_names,           # ["tool1", "tool2", ...]
            "mcp_metadata": mcp_metadata        # 用于重建连接
        }
