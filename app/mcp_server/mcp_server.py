import json
import sys
import traceback
from typing import Dict, Any, List

# 假设你已实现 McpWorkflowTool（来自上文）
from mcp_adapter import McpWorkflowTool


class MinimalMcpServer:
    def __init__(self):
        self.tools: Dict[str, McpWorkflowTool] = {}

    def add_tool(self, tool: McpWorkflowTool):
        self.tools[tool.name] = tool

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        method = request.get("method")
        req_id = request.get("id")

        if method == "initialize":
            # 返回工具列表
            tool_definitions = []
            for name, tool in self.tools.items():
                tool_definitions.append({
                    "name": name,
                    "description": tool.description,
                    "inputSchema": tool.get_input_schema()
                })
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": tool_definitions}
                }
            }

        elif method == "call":
            tool_name = request["params"]["name"]
            arguments = request["params"]["arguments"]

            if tool_name not in self.tools:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": f"Tool '{tool_name}' not found"}
                }

            try:
                result = self.tools[tool_name].execute(arguments)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32000, "message": str(e)}
                }

        elif method == "shutdown":
            return {"jsonrpc": "2.0", "id": req_id, "result": None}

        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method '{method}' not supported"}
            }

    def run_stdio(self):
        """通过 stdin/stdout 与 MCP 客户端通信"""
        try:
            while True:
                line = sys.stdin.readline()
                if not line:
                    break

                try:
                    request = json.loads(line.strip())
                    response = self.handle_request(request)
                    # MCP 要求每条消息一行（newline-delimited JSON）
                    print(json.dumps(response, ensure_ascii=False), flush=True)
                except json.JSONDecodeError:
                    # 忽略无效 JSON
                    pass
        except KeyboardInterrupt:
            pass


# ===== 启动示例 =====
if __name__ == "__main__":
    server = MinimalMcpServer()

    # 动态加载所有导出项目
    import os
    from pathlib import Path

    exports_dir = Path(r"D:\work\WorkFlowGUI\canvas_files\projects")
    for project_dir in exports_dir.iterdir():
        if project_dir.is_dir() and (project_dir / "project_spec.json").exists():
            try:
                tool = McpWorkflowTool(project_dir)
                server.add_tool(tool)
                print(f"✅ Registered tool: {tool.name}", file=sys.stderr)
            except Exception as e:
                traceback.print_exc()
                print(f"❌ Failed to load {project_dir}: {e}", file=sys.stderr)

    print("🚀 MCP Server ready (waiting for requests on stdin)...", file=sys.stderr)
    server.run_stdio()