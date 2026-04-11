"""
Canvas Tools - 画布调试工具，供 LLM 在画布场景下调用
"""
from typing import List, Dict, Optional, Any, cast
import time

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

    def _tail_text(self, text: str, max_chars: int = 4000) -> str:
        if not text:
            return ""
        return text[-max_chars:] if len(text) > max_chars else text

    def _get_runner(self):
        return getattr(self.parent, "canvas_runner", None)

    def _get_execution_manager(self):
        execution_record = getattr(self.parent, "execution_record", None)
        if not execution_record:
            return None
        if hasattr(execution_record, "get_all_records"):
            return execution_record
        if hasattr(execution_record, "execution_manager"):
            return execution_record.execution_manager
        if hasattr(execution_record, "manager"):
            return execution_record.manager
        return execution_record

    def _serialize_record(self, record) -> Dict[str, Any]:
        duration = None
        if getattr(record, "end_time", None) and getattr(record, "start_time", None):
            duration = round(record.end_time - record.start_time, 3)
        return {
            "task_id": getattr(record, "execution_id", None),
            "canvas_name": getattr(record, "canvas_name", None),
            "trigger_type": getattr(record, "trigger_type", None),
            "status": getattr(record, "status", None),
            "start_time": getattr(record, "start_time", None),
            "end_time": getattr(record, "end_time", None),
            "duration_seconds": duration,
            "error_msg": getattr(record, "error_msg", None),
            "output_data": getattr(record, "output_data", {}) or {},
            "input_data": getattr(record, "input_data", None),
        }

    def _serialize_port_links(self, node, port_getter_name: str, direction: str) -> List[Dict[str, Any]]:
        result = []
        port_getter = getattr(node, port_getter_name, None)
        if not callable(port_getter):
            return result

        for port in port_getter():
            links = []
            for connected_port in port.connected_ports():
                peer_node = connected_port.node()
                links.append(
                    {
                        "node_name": peer_node.name(),
                        "port_name": connected_port.name(),
                        "direction": direction,
                    }
                )
            result.append(
                {
                    "port_name": port.name(),
                    "port_type": getattr(port.model, "type_", None),
                    "links": links,
                }
            )
        return result

    def _collect_node_snapshot(
        self,
        node,
        include_logs: bool = True,
        log_type: str = "historical",
        log_tail_chars: int = 4000,
        include_code: bool = False,
    ) -> Dict[str, Any]:
        component_path = getattr(node, "FULL_PATH", "") or ""
        snapshot = {
            "node_name": node.name(),
            "node_id": getattr(node, "persistent_id", None),
            "status": getattr(node, "status", None),
            "node_type": component_path.split("/")[0] if component_path else "未知",
            "component_path": component_path or None,
            "debug_enabled": bool(getattr(node, "_debug_enabled", False)),
            "properties": dict(getattr(node.model, "_custom_prop", {}) or {}),
            "inputs": self._serialize_port_links(node, "input_ports", "upstream"),
            "outputs": self._serialize_port_links(node, "output_ports", "downstream"),
        }

        if include_logs:
            logs = self._get_current_run_logs(node) if log_type == "current" else node.get_logs()
            snapshot["logs"] = self._tail_text(logs, log_tail_chars)
            snapshot["log_type"] = log_type

        if include_code:
            get_component_code = getattr(node, "get_component_code", None)
            if callable(get_component_code):
                snapshot["code"] = self._tail_text(get_component_code(), 12000)

        return snapshot

    def canvas_run_node(self, mode: str, node_name: Optional[str] = None) -> ToolResult:
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
            runner = self._get_runner()
            if not runner:
                return ToolResult(False, error="CanvasRunner 不可用")
            task_id = runner.run_workflow()
            return ToolResult(
                True,
                content={
                    "message": "已触发：运行整个画布",
                    "task_id": task_id,
                    "mode": mode,
                },
            )

        node = self._find_node_by_name(cast(str, node_name))
        if not node:
            return ToolResult(False, error=f"未找到节点: {node_name}")

        if mode == "node":
            task_id = self.parent.run_node(node)
            return ToolResult(True, content={"message": f"已触发：运行节点 [{node_name}]", "task_id": task_id, "mode": mode, "node_name": node_name})
        elif mode == "to":
            task_id = self.parent.run_to(node)
            return ToolResult(True, content={"message": f"已触发：运行到节点 [{node_name}]", "task_id": task_id, "mode": mode, "node_name": node_name})
        elif mode == "from":
            task_id = self.parent.run_from(node)
            return ToolResult(True, content={"message": f"已触发：从节点 [{node_name}] 开始运行", "task_id": task_id, "mode": mode, "node_name": node_name})
        elif mode == "subgraph":
            task_id = self.parent.run_subgraph(node)
            return ToolResult(True, content={"message": f"已触发：运行节点 [{node_name}] 所在子图", "task_id": task_id, "mode": mode, "node_name": node_name})

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

        try:
            node.current_code = code
            node._debug_enabled = True
            task_id = self.parent.run_node(node)
            return ToolResult(
                True,
                content={
                    "message": f"已更新代码并运行节点 [{node_name}]",
                    "task_id": task_id,
                    "node_name": node_name,
                },
            )
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

    def canvas_set_node_property(
        self, node_name: str, properties: Dict, target: Optional[str] = None
    ) -> ToolResult:
        """
        设置节点属性参数

        Args:
            node_name: 节点名称
            properties: 属性字典，如 {"temperature": 0.7, "max_tokens": 1000}
            target: 可选，特殊目标 - "current_node"表示当前节点，
                   或者传入node_uuid字符串表示通过UUID定位节点
        """
        node = self._find_node_by_name(node_name)
        if not node:
            return ToolResult(False, error=f"未找到节点: {node_name}")

        try:
            for prop_name, prop_value in properties.items():
                node.set_property(prop_name, prop_value)
            return ToolResult(
                True, content=f"已设置节点 [{node_name}] 的属性: {properties}"
            )
        except Exception as e:
            return ToolResult(False, error=f"设置节点属性失败: {str(e)}")

    def canvas_get_node_property(
        self, node_name: str, property_names: Optional[List[str]] = None
    ) -> ToolResult:
        """
        查询节点当前参数

        Args:
            node_name: 节点名称
            property_names: 可选，属性名列表，如 ["temperature", "model"]
                          如果为空，则返回节点所有可读属性
        """
        node = self._find_node_by_name(node_name)
        if not node:
            return ToolResult(False, error=f"未找到节点: {node_name}")

        try:
            if property_names is None or len(property_names) == 0:
                all_props = {}
                if hasattr(node, "get_properties"):
                    all_props = node.get_properties()
                elif hasattr(node, "properties"):
                    all_props = node.properties or {}
                return ToolResult(
                    True, content=f"节点 [{node_name}] 所有属性:\n{all_props}"
                )

            result = {}
            for prop_name in property_names:
                value = node.get_property(prop_name)
                result[prop_name] = value
            return ToolResult(
                True, content=f"节点 [{node_name}] 属性:\n{result}"
            )
        except Exception as e:
            return ToolResult(False, error=f"查询节点属性失败: {str(e)}")

    def canvas_get_execution_state(
        self,
        task_id: Optional[str] = None,
        include_nodes: bool = True,
        include_logs: bool = False,
        log_tail_chars: int = 2000,
        recent_limit: int = 5,
    ) -> ToolResult:
        manager = self._get_execution_manager()
        runner = self._get_runner()
        if not manager:
            return ToolResult(False, error="ExecutionManager 不可用")

        try:
            records = []
            if task_id:
                record = manager.get_record(task_id)
                if not record:
                    return ToolResult(False, error=f"未找到任务记录: {task_id}")
                records = [record]
            else:
                all_records = manager.get_all_records()
                records = sorted(all_records, key=lambda item: getattr(item, "start_time", 0), reverse=True)[: max(1, recent_limit)]

            content = {
                "canvas_name": getattr(self.parent, "workflow_name", None),
                "runner": {
                    "is_running": bool(getattr(runner, "_is_running", False)) if runner else False,
                    "queue_size": len(getattr(runner, "_task_queue", [])) if runner else 0,
                    "current_task_id": getattr(getattr(runner, "_current_task", None), "task_id", None) if runner else None,
                    "current_mode": getattr(getattr(runner, "_current_task", None), "mode", None) if runner else None,
                    "timestamp": time.time(),
                },
                "records": [self._serialize_record(record) for record in records],
            }

            if include_nodes:
                node_snapshots = []
                for node in self.graph.all_nodes():
                    status = getattr(node, "status", None)
                    if status in {"failed", "running", "pending"}:
                        node_snapshots.append(
                            self._collect_node_snapshot(
                                node,
                                include_logs=include_logs,
                                log_tail_chars=log_tail_chars,
                            )
                        )
                content["active_or_problem_nodes"] = node_snapshots

            return ToolResult(True, content=content)
        except Exception as e:
            return ToolResult(False, error=f"获取执行状态失败: {str(e)}")

    def canvas_get_node_debug_snapshot(
        self,
        node_name: str,
        include_logs: bool = True,
        log_type: str = "historical",
        log_tail_chars: int = 4000,
        include_code: bool = False,
    ) -> ToolResult:
        node = self._find_node_by_name(node_name)
        if not node:
            return ToolResult(False, error=f"未找到节点: {node_name}")

        try:
            return ToolResult(
                True,
                content=self._collect_node_snapshot(
                    node,
                    include_logs=include_logs,
                    log_type=log_type,
                    log_tail_chars=log_tail_chars,
                    include_code=include_code,
                ),
            )
        except Exception as e:
            return ToolResult(False, error=f"获取节点调试快照失败: {str(e)}")


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
                            "description": "运行模式: node(运行单个节点), to(运行到指定节点), from(从指定节点开始), subgraph(运行所在子图), workflow(运行整个画布)",
                            "enum": ["node", "to", "from", "subgraph", "workflow"],
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
        {
            "type": "function",
            "function": {
                "name": "canvas_get_execution_state",
                "description": "获取画布最近执行任务的状态、错误和问题节点，适合自动调试闭环中的验证阶段",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "可选，指定任务 ID"},
                        "include_nodes": {"type": "boolean", "description": "是否附带 failed/running/pending 节点快照"},
                        "include_logs": {"type": "boolean", "description": "是否在问题节点中附带日志摘要"},
                        "log_tail_chars": {"type": "integer", "description": "日志尾部保留字符数"},
                        "recent_limit": {"type": "integer", "description": "未指定 task_id 时返回最近几条记录"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "canvas_get_node_debug_snapshot",
                "description": "获取节点调试快照，包含状态、属性、上下游连接、日志，可选附带当前组件代码",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "node_name": {"type": "string", "description": "节点名称"},
                        "include_logs": {"type": "boolean", "description": "是否返回日志"},
                        "log_type": {
                            "type": "string",
                            "description": "日志类型: historical(历史日志), current(本轮运行日志)",
                            "enum": ["historical", "current"],
                        },
                        "log_tail_chars": {"type": "integer", "description": "日志尾部保留字符数"},
                        "include_code": {"type": "boolean", "description": "是否附带节点当前执行代码"},
                    },
                    "required": ["node_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "canvas_set_node_property",
                "description": "设置节点的属性参数，如模型、温度、最大令牌等",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "node_name": {"type": "string", "description": "节点名称"},
                        "properties": {
                            "type": "object",
                            "description": "属性字典，如 {\"temperature\": 0.7, \"max_tokens\": 1000}",
                        },
                        "target": {
                            "type": "string",
                            "description": "可选，特殊目标 - \"current_node\"表示当前节点",
                        },
                    },
                    "required": ["node_name", "properties"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "canvas_get_node_property",
                "description": "查询节点当前的属性参数值",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "node_name": {"type": "string", "description": "节点名称"},
                        "property_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "可选，属性名列表，如 [\"temperature\", \"model\"]",
                        },
                    },
                    "required": ["node_name"],
                },
            },
        },
    ]
