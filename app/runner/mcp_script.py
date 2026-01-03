#!/usr/bin/env python3
import json
import httpx
from typing import Any, Dict, Optional
from mcp.server.fastmcp import FastMCP
from pydantic import Field

# 初始化 MCP Server
mcp = FastMCP("Workflow-Bridge")

# 本地微服务的地址
API_BASE_URL = "http://127.0.0.1:8000"


@mcp.tool()
async def execute_workflow(workflow_inputs: Dict[str, Any]) -> str:
    """
    执行本地工作流微服务。

    参数:
    - workflow_inputs: 一个字典，包含 project_spec.json 中定义的输入字段。
      例如: {"input_text": "hello", "threshold": 0.5}
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            # 这里的 workflow_inputs 会直接传给 FastAPI 的 InputModel
            # 注意：如果你的 FastAPI 期望的是扁平结构，直接传字典即可
            response = await client.post(
                f"{API_BASE_URL}/run",
                json=workflow_inputs,
                params={"mcp": "true"}  # 触发你代码中处理好的 MCP 逻辑
            )

            if response.status_code != 200:
                return f"错误: 远程服务返回了 {response.status_code} - {response.text}"

            data = response.json()

            # 处理你 FastAPI 中返回的特定 MCP 格式
            if "content" in data:
                # 如果 FastAPI 已经按 MCP 格式包装了
                return data["content"][0]["text"]
            else:
                # 否则返回原始结果的 JSON 字符串
                return json.dumps(data.get("result", data), indent=2, ensure_ascii=False)

        except Exception as e:
            return f"调用本地服务失败: {str(e)}"


@mcp.tool()
async def get_service_spec() -> str:
    """获取当前工作流服务的输入参数定义(Spec)"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_BASE_URL}/spec")
        return json.dumps(response.json(), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()