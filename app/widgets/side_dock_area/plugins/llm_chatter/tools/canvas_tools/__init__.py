"""
Canvas Tools - 画布调试工具，供 LLM 在画布场景下调用
"""

from typing import List, Dict, Any, Optional

from app.widgets.side_dock_area.plugins.llm_chatter.tools.result import ToolResult


class CanvasTools:
    def __init__(self, graph, node_operations, parent):
        self.graph = graph
        self.node_operations = node_operations
        self.parent = parent

    def _find_node_by_name(self, node_name: str):
        for node in self.graph.all_nodes():
            if node.name() == node_name:
                return node
        return None

    def canvas_run_node(self, mode: str, node_name: str = None) -> ToolResult:
        """
        运行画布节点

        Args:
            mode: 运行模式 - "node"(运行单个节点), "to"(运行到指定节点),
                  "from"(从指定节点开始), "subgraph"(运行所在子图), "workflow"(运行整个画布)
            node_name: 节点名称（mode 为 node/to/from/subgraph 时必填）
        """
        if mode not in ("node", "to", "from", "subgraph", "workflow"):
            return ToolResult(False, error=f"无效的运行模式: {mode}")

        if mode != "workflow" and not node_name:
            return ToolResult(False, error=f"mode={mode} 时必须指定 node_name")

        if mode == "workflow":
            self.parent.run_workflow()
            return ToolResult(True, content="已触发：运行整个画布")

        node = self._find_node_by_name(node_name)
        if not node:
            return ToolResult(False, error=f"未找到节点: {node_name}")

        if mode == "node":
            self.parent.run_node(node)
            return ToolResult(True, content=f"已触发：运行节点 [{node_name}]")
        elif mode == "to":
            self.parent.run_to(node)
            return ToolResult(True, content=f"已触发：运行到节点 [{node_name}]")
        elif mode == "from":
            self.parent.run_from(node)
            return ToolResult(True, content=f"已触发：从节点 [{node_name}] 开始运行")
        elif mode == "subgraph":
            self.parent.run_subgraph(node)
            return ToolResult(True, content=f"已触发：运行节点 [{node_name}] 所在子图")

        return ToolResult(False, error="未知的运行模式")

    def canvas_get_logs(
        self, node_name: str, log_type: str = "historical"
    ) -> ToolResult:
        """
        获取节点日志

        Args:
            node_name: 节点名称
            log_type: 日志类型 - "historical"(历史日志，从 buffer 或文件读取),
                     "current"(本轮运行日志，从 LogToolWindow 获取)
        """
        node = self._find_node_by_name(node_name)
        if not node:
            return ToolResult(False, error=f"未找到节点: {node_name}")

        if not hasattr(node, "get_logs"):
            return ToolResult(False, error=f"节点 [{node_name}] 不支持获取日志")

        if log_type == "current":
            logs = self._get_current_run_logs(node)
        else:
            logs = node.get_logs()

        if not logs:
            return ToolResult(True, content=f"[{node_name}] {log_type} 日志为空")
        return ToolResult(True, content=f"[{node_name}] {log_type} 日志:\n{logs}")

    def _get_current_run_logs(self, node) -> str:
        run_id = getattr(node, "_current_run_id", None)
        if not run_id:
            return "当前无运行中的日志"

        log_window = getattr(self.parent, "log_window", None)
        if not log_window or not hasattr(log_window, "run_cards"):
            return f"无法获取 run_id={run_id} 的当前日志"

        card = log_window.run_cards.get(run_id)
        if not card:
            return f"未找到 run_id={run_id} 的日志卡片"

        log_text_edit = getattr(card, "log_text", None)
        if not log_text_edit:
            return f"日志卡片无文本内容"

        return log_text_edit.toPlainText() or f"run_id={run_id} 日志为空"

    def canvas_modify_and_run(self, node_name: str, code: str) -> ToolResult:
        """
        修改节点代码并运行

        Args:
            node_name: 节点名称
            code: 新的代码内容
        """
        node = self._find_node_by_name(node_name)
        if not node:
            return ToolResult(False, error=f"未找到节点: {node_name}")

        if not hasattr(node, "current_code"):
            return ToolResult(False, error=f"节点 [{node_name}] 不支持代码修改")

        try:
            node.current_code = code
            node._debug_enabled = True
            self.parent.run_node(node)
            node._debug_enabled = False
            return ToolResult(True, content=f"已更新代码并运行节点 [{node_name}]")
        except Exception as e:
            return ToolResult(False, error=f"修改代码并运行失败: {str(e)}")

    def canvas_list_nodes(self) -> ToolResult:
        """列出画布所有节点"""
        nodes = self.graph.all_nodes()
        if not nodes:
            return ToolResult(True, content="画布上没有节点")

        lines = ["画布节点列表:"]
        for node in nodes:
            name = node.name()
            node_type = "未知"
            if hasattr(node, "FULL_PATH"):
                node_type = node.FULL_PATH.split("/")[0]
            lines.append(f"  - {name} ({node_type})")

        return ToolResult(True, content="\n".join(lines))


def get_canvas_tools_schema() -> List[Dict]:
    """获取画布工具的 schema 定义"""
    return [
        {
            "type": "function",
            "function": {
                "name": "canvas_run_node",
                "description": "运行画布节点，支持多种运行模式",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "mode": {
                            "type": "string",
                            "description": "运行模式: node(运行单个节点), to(运行到指定节点), from(从指定节点开始), subgraph(运行所在子图)",
                            "enum": ["node", "to", "from", "subgraph"],
                        },
                        "node_name": {
                            "type": "string",
                            "description": "节点名称（mode 为 node/to/from/subgraph 时必填）",
                        },
                    },
                    "required": ["mode"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "canvas_get_logs",
                "description": "获取节点的运行日志",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "node_name": {"type": "string", "description": "节点名称"},
                        "log_type": {
                            "type": "string",
                            "description": "日志类型: historical(历史日志), current(本轮运行日志)",
                            "enum": ["historical", "current"],
                        },
                    },
                    "required": ["node_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "canvas_modify_and_run",
                "description": "修改节点代码并立即运行",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "node_name": {"type": "string", "description": "节点名称"},
                        "code": {"type": "string", "description": "新的代码内容"},
                    },
                    "required": ["node_name", "code"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "canvas_list_nodes",
                "description": "列出画布上的所有节点",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]
