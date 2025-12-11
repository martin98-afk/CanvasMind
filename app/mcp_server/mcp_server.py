# -*- coding: utf-8 -*-
import sys
from mcp import Server
from mcp_adapter import McpWorkflowTool

def create_mcp_server(project_dirs: List[str]) -> Server:
    server = Server("lowcode-mcp-server")
    for p in project_dirs:
        tool = McpWorkflowTool(Path(p))
        server.add_tool(
            name=tool.name,
            description=tool.description,
            input_schema=tool.get_input_schema(),
            handler=lambda args, t=tool: t.execute(args)
        )
    return server

if __name__ == "__main__":
    # 从命令行读取导出目录列表
    project_dirs = sys.argv[1:] or ["./exports/tool1", "./exports/tool2"]
    server = create_mcp_server(project_dirs)
    server.run_stdio()  # 或 run_tcp(host="127.0.0.1", port=3000)