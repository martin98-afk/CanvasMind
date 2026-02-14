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


class Component(BaseComponent):
    name = "MCP工具配置"
    category = "大模型组件"
    description = "配置MCP服务连接参数"
    requirements = ""
    
    inputs = [
    ]
    
    outputs = [
        PortDefinition(name="mcp_config", label="MCP配置", type=ArgumentType.JSON),
    ]
    
    properties = {
        "mcp_config": PropertyDefinition(
            type=PropertyType.DYNAMICFORM,
            label="MCP配置",
            schema={
                "name": PropertyDefinition(
                    type=PropertyType.TEXT,
                    default="",
                    label="工具名称",
                ),
                "url": PropertyDefinition(
                    type=PropertyType.TEXT,
                    default="http://localhost:8080",
                    label="服务地址",
                    description="MCP服务的HTTP/HTTPS地址",
                ),
                "type": PropertyDefinition(
                    type=PropertyType.CHOICE,
                    default="http",
                    label="协议类型",
                    description="MCP服务通信协议",
                    choices=["http", "stdio", "websocket"]
                ),
                "disabled": PropertyDefinition(
                    type=PropertyType.BOOL,
                    default=False,
                    label="禁用工具",
                    description="是否在运行时跳过此工具",
                ),
                "timeout": PropertyDefinition(
                    type=PropertyType.INT,
                    default=30,
                    label="超时时间(秒)",
                    description="请求超时时间（仅HTTP协议有效）",
                )
            }
        ),
    }

    def run(self, params, inputs=None):
        """
        生成MCP工具配置对象
        
        Args:
            params: 节点属性（来自UI）
            inputs: 上游输入（本节点无输入）
            
        Returns:
            dict: 包含mcp_config输出端口的配置字典
        """
        import json
        
        # 获取配置参数
        configs = params.get("mcp_config", {})
        mcp_configs = {}
        for config in configs:
            print(config.url, config.name)
                
            # 处理headers字符串
            try:
                headers = json.loads(config.get("headers", "{}"))
                if not isinstance(headers, dict):
                    raise ValueError("请求头必须是有效的JSON对象")
            except json.JSONDecodeError as e:
                raise ValueError(f"请求头格式错误: {str(e)}")
            
            # 构建标准化配置
            mcp_configs[config.name] = {
                "url": config["url"].strip(),
                "type": config["type"],
                "disabled": bool(config.get("disabled", False)),
                "timeout": int(config.get("timeout", 30)),
                "headers": headers
            }
        
        self.logger.info(f"生成MCP配置: {mcp_configs}")
        
        return {
            "mcp_config":  {
              "mcpServers": mcp_configs
            }
        }
