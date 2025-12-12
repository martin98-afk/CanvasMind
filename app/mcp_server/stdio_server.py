# mcp_server.py
import json
import sys
from pathlib import Path

from loguru import logger

from app.mcp_server.mcp_adapter import McpWorkflowTool


class GlobalMcpServer:
    def __init__(self, exports_dir: Path):
        self.exports_dir = exports_dir
        self.tools = {}  # name -> McpWorkflowTool
        self._load_tools()

    def _load_tools(self):
        self.tools.clear()
        if not self.exports_dir.exists():
            return
        for p in self.exports_dir.iterdir():
            if p.is_dir() and (p / "project_spec.json").exists():
                try:
                    tool = McpWorkflowTool(p)
                    self.tools[tool.name] = tool
                except Exception as e:
                    logger.error(f"[MCP] Skip invalid tool {p}: {e}", file=sys.stderr)

    def handle_initialize(self, req_id):
        tool_list = []
        for name, tool in self.tools.items():
            tool_list.append({
                "name": name,
                "description": tool.description,
                "inputSchema": tool.get_input_schema()
            })
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": tool_list}
            }
        }

    def handle_call(self, req_id, name, args):
        if name not in self.tools:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": f"Tool '{name}' not found"}
            }
        try:
            result = self.tools[name].execute(args)
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

    def run_stdio(self):
        print("[MCP Server] 已加载工具:", list(self.tools.keys()), file=sys.stderr)
        for line in sys.stdin:
            try:
                req = json.loads(line.strip())
                method = req.get("method")
                req_id = req.get("id")
                if method == "initialize":
                    resp = self.handle_initialize(req_id)
                elif method == "call":
                    resp = self.handle_call(req_id, req["params"]["name"], req["params"]["arguments"])
                elif method == "shutdown":
                    resp = {"jsonrpc": "2.0", "id": req_id, "result": None}
                    print(json.dumps(resp))
                    break
                else:
                    continue
                print(json.dumps(resp, ensure_ascii=False), flush=True)
            except:
                pass


if __name__ == "__main__":
    exports_dir = Path(__file__).parent / "exports"
    server = GlobalMcpServer(exports_dir)
    server.run_stdio()