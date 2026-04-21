"""
Canvas Tools - 画布调试工具，供 LLM 在画布场景下调用
"""

from typing import List, Dict, Optional, Any, cast
import time

from PyQt5.QtCore import QTimer

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

    def _serialize_port_links(
        self, node, port_getter_name: str, direction: str
    ) -> List[Dict[str, Any]]:
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

    def _get_input_port_values(self, node) -> Dict[str, Any]:
        result = {}
        input_ports_getter = getattr(node, "input_ports", None)
        if not callable(input_ports_getter):
            return result

        for port in input_ports_getter():
            port_name = port.name()
            value = None
            for connected_port in port.connected_ports():
                peer_node = connected_port.node()
                peer_output_values = getattr(peer_node, "_output_values", None)
                if peer_output_values:
                    peer_port_name = connected_port.name()
                    value = peer_output_values.get(peer_port_name)
                    break
            result[port_name] = value
        return result

    def _get_output_port_values(self, node) -> Dict[str, Any]:
        output_values = getattr(node, "_output_values", None)
        if output_values is None:
            return {}
        return dict(output_values)

    def _truncate_value(self, value: Any, max_length: int = 2000) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            if len(value) > max_length:
                return value[:max_length] + "...[truncated]"
            return value
        if isinstance(value, (list, dict)):
            try:
                import json

                json_str = json.dumps(value, ensure_ascii=False, default=str)
                if len(json_str) > max_length:
                    return json_str[:max_length] + "...[truncated]"
                return value
            except Exception:
                return str(value)[:max_length] + "...[truncated]"
        return value

    def _collect_node_snapshot(
        self,
        node,
        include_logs: bool = True,
        log_type: str = "historical",
        log_tail_chars: int = 4000,
        include_code: bool = False,
        include_input_data: bool = False,
        include_output_data: bool = False,
        data_truncation: int = 2000,
    ) -> Dict[str, Any]:
        component_path = getattr(node, "FULL_PATH", "") or ""
        properties = dict(getattr(node.model, "_custom_prop", {}) or {})
        code = properties.pop("_code", "")
        snapshot = {
            "node_name": node.name(),
            "node_id": properties.pop("persistent_id", None),
            "status": properties.pop("_status", None),
            "pos": [round(pos, 1) for pos in node.pos()],
            "node_type": component_path,
            "properties": properties,
            "inputs": self._serialize_port_links(node, "input_ports", "upstream"),
            "outputs": self._serialize_port_links(node, "output_ports", "downstream"),
        }
        if include_input_data:
            snapshot["input_data"] = {
                k: self._truncate_value(v, data_truncation)
                for k, v in self._get_input_port_values(node).items()
            }

        if include_output_data:
            snapshot["output_data"] = {
                k: self._truncate_value(v, data_truncation)
                for k, v in self._get_output_port_values(node).items()
            }
        if include_logs:
            logs = (
                self._get_current_run_logs(node)
                if log_type == "current"
                else node.get_logs()
            )
            snapshot["logs"] = self._tail_text(logs, log_tail_chars)
            snapshot["log_type"] = log_type

        if include_code:
            snapshot["_code"] = code

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
            self.parent.canvas_run_node_requested.emit(mode, "")
            return ToolResult(
                True,
                content={
                    "message": "已触发：运行整个画布",
                    "mode": mode,
                },
            )

        node = self._find_node_by_name(cast(str, node_name))
        if not node:
            return ToolResult(False, error=f"未找到节点: {node_name}")

        self.parent.canvas_run_node_requested.emit(mode, node_name)
        return ToolResult(
            True,
            content={
                "message": f"已触发：运行节点 [{node_name}]",
                "mode": mode,
                "node_name": node_name,
            },
        )

    def canvas_get_logs(self, node_name: str, log_type: str = "current") -> ToolResult:
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
            logs = node.get_logs()[-5000:]

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

    def canvas_nodes(self) -> ToolResult:
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

    def canvas_create_node(
        self,
        node_name: Optional[str] = None,
        position: Optional[Dict[str, float]] = None,
    ) -> ToolResult:
        """
        创建代码编辑节点

        Args:
            node_name: 可选，节点名称，默认自动生成
            position: 可选，节点位置 {"x": float, "y": float}，默认在画布中央
        """
        try:
            self.parent.canvas_create_node_requested.emit(
                node_name or "", position or {}
            )
            return ToolResult(
                True,
                content={
                    "message": f"已发送创建代码编辑节点请求: {node_name or '自动命名'}",
                    "node_name": node_name or "自动生成",
                },
            )
        except Exception as e:
            return ToolResult(False, error=f"创建节点失败: {str(e)}")

    def canvas_connect_nodes(
        self,
        connections: List[Dict],
    ) -> ToolResult:
        """
        连接两个节点的端口

        Args:
            connections: 连接列表，如 [{"from_node": "A", "from_port": "out", "to_node": "B", "to_port": "in"}]
        """
        if not isinstance(connections, list):
            return ToolResult(False, error="connections 必须是列表格式")

        try:
            self.parent.canvas_connect_nodes_requested.emit(connections)
            return ToolResult(
                True,
                content={
                    "message": f"已发送 {len(connections)} 个连接请求",
                    "connections": connections,
                },
            )
        except Exception as e:
            return ToolResult(False, error=f"连接失败: {str(e)}")

    def canvas_set_prop(
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
            self.parent.canvas_set_prop_requested.emit(node_name, properties)
            return ToolResult(
                True, content=f"已设置节点 [{node_name}] 的属性: {properties.keys()}"
            )
        except Exception as e:
            return ToolResult(False, error=f"设置节点属性失败: {str(e)}")

    def canvas_edit_prop(
        self,
        node_name: str,
        edits: List[Dict],
    ) -> ToolResult:
        """
        编辑节点属性中的字符串，支持多字符串替换

        Args:
            node_name: 节点名称
            edits: 替换列表，如 [{"property": "prompt", "old_str": "x", "new_str": "y"}]
        """
        node = self._find_node_by_name(node_name)
        if not node:
            return ToolResult(False, error=f"未找到节点: {node_name}")

        if not isinstance(edits, list):
            return ToolResult(False, error="edits 必须是列表格式")

        try:
            self.parent.canvas_edit_prop_requested.emit(node_name, edits)
            return ToolResult(
                True,
                content=f"已发送属性编辑请求到节点 [{node_name}]，共 {len(edits)} 个替换",
            )
        except Exception as e:
            return ToolResult(False, error=f"编辑节点属性失败: {str(e)}")
        
    def canvas_exec_state(
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
                records = sorted(
                    all_records,
                    key=lambda item: getattr(item, "start_time", 0),
                    reverse=True,
                )[: max(1, recent_limit)]

            content = {
                "canvas_name": getattr(self.parent, "workflow_name", None),
                "runner": {
                    "exec_env": self.parent.env_data,
                    "is_running": bool(getattr(runner, "_is_running", False))
                    if runner
                    else False,
                    "queue_size": len(getattr(runner, "_task_queue", []))
                    if runner
                    else 0,
                    "current_task_id": getattr(
                        getattr(runner, "_current_task", None), "task_id", None
                    )
                    if runner
                    else None,
                    "current_mode": getattr(
                        getattr(runner, "_current_task", None), "mode", None
                    )
                    if runner
                    else None,
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

    def canvas_get_variables(
        self,
        var_type: Optional[str] = None,
        include_values: bool = True,
    ) -> ToolResult:
        """
        获取画布全局变量

        Args:
            var_type: 可选，筛选类型 - "custom"(自定义变量)/"node_vars"(节点输出变量)/"env"(环境变量)，为空则返回所有
            include_values: 是否包含变量值，False 则只返回变量名列表
        """
        gv = self.parent.global_variables
        if not gv:
            return ToolResult(False, error="全局变量不可用")

        result = {}
        types_to_fetch = []
        if var_type is None:
            types_to_fetch = ["custom", "node_vars", "env"]
        elif var_type in ("custom", "node_vars", "env"):
            types_to_fetch = [var_type]
        else:
            return ToolResult(
                False, error=f"无效的变量类型: {var_type}，可选: custom/node_vars/env"
            )

        for vtype in types_to_fetch:
            if vtype == "custom":
                if include_values:
                    result["custom"] = {k: v.value for k, v in gv.custom.items()}
                else:
                    result["custom"] = list(gv.custom.keys())
            elif vtype == "node_vars":
                if include_values:
                    result["node_vars"] = {k: v.value for k, v in gv.node_vars.items()}
                else:
                    result["node_vars"] = list(gv.node_vars.keys())
            elif vtype == "env":
                result["env"] = gv.env.get_all_env_vars()

        return ToolResult(True, content=result)

    def canvas_snapshot(
        self,
        node_names: Optional[List[str]] = None,
        include_logs: bool = False,
        log_type: str = "historical",
        log_tail_chars: int = 2000,
        include_code: bool = False,
        include_input_data: bool = False,
        include_output_data: bool = False,
        data_truncation: int = 1000,
    ) -> ToolResult:
        if node_names is None:
            nodes = list(self.graph.all_nodes())
        else:
            nodes = []
            for name in node_names:
                node = self._find_node_by_name(name)
                if not node:
                    return ToolResult(False, error=f"未找到节点: {name}")
                nodes.append(node)

        try:
            snapshots = [
                self._collect_node_snapshot(
                    node,
                    include_logs=include_logs,
                    log_type=log_type,
                    log_tail_chars=log_tail_chars,
                    include_code=include_code,
                    include_input_data=include_input_data,
                    include_output_data=include_output_data,
                    data_truncation=data_truncation,
                )
                for node in nodes
            ]
            return ToolResult(
                True, content=snapshots if len(snapshots) > 1 else snapshots[0]
            )
        except Exception as e:
            return ToolResult(False, error=f"获取节点快照失败: {str(e)}")

    def canvas_set_variable(
        self,
        var_name: str,
        value: Any = None,
        var_type: str = "custom",
        from_node: Optional[str] = None,
        from_port: Optional[str] = None,
    ) -> ToolResult:
        """
        设置画布全局变量

        Args:
            var_name: 变量名（env/custom 类型时直接用作变量名，node_vars 时作为目标变量名）
            value: 变量值（var_type 为 custom/env 时使用）
            var_type: 变量类型 - "custom"(自定义变量)/"env"(环境变量)/"node_vars"(节点输出变量)
            from_node: 源节点名（var_type 为 node_vars 时必填）
            from_port: 源输出端口名（var_type 为 node_vars 时必填）
        """
        gv = self.parent.global_variables
        if not gv:
            return ToolResult(False, error="全局变量不可用")

        if var_type not in ("custom", "env", "node_vars"):
            return ToolResult(
                False, error=f"无效的变量类型: {var_type}，可选: custom/env/node_vars"
            )

        if var_type in ("custom", "env"):
            if value is None:
                return ToolResult(False, error=f"设置 {var_type} 变量时 value 不能为空")
            if var_type == "custom":
                gv.set(var_name, value)
            else:
                gv.env.set_env_var(var_name, value)
            return ToolResult(
                True,
                content={
                    "message": f"已设置 {var_type} 变量: {var_name}",
                    "var_type": var_type,
                    "var_name": var_name,
                    "value": self._truncate_value(value, 500),
                },
            )

        elif var_type == "node_vars":
            if not from_node or not from_port:
                return ToolResult(
                    False, error="设置 node_vars 变量时需要指定 from_node 和 from_port"
                )
            node = self._find_node_by_name(from_node)
            if not node:
                return ToolResult(False, error=f"未找到节点: {from_node}")
            output_values = getattr(node, "_output_values", None)
            if output_values is None:
                return ToolResult(
                    False, error=f"节点 {from_node} 还没有输出数据，请先运行该节点"
                )
            port_value = output_values.get(from_port)
            if port_value is None:
                return ToolResult(
                    False, error=f"节点 {from_node} 的输出端口 {from_port} 没有数据"
                )
            node_var_key = f"{from_node}__{from_port}"
            gv.set_output(from_node, from_port, port_value)
            return ToolResult(
                True,
                content={
                    "message": f"已设置节点输出变量: {var_name} -> {node_var_key}",
                    "var_type": var_type,
                    "var_name": var_name,
                    "source": {"node": from_node, "port": from_port},
                    "value": self._truncate_value(port_value, 500),
                },
            )


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
                            "description": "运行模式: node(运行单个节点), to(运行到指定节点), from(从指定节点开始), subgraph(运行节点所在子图), workflow(运行整个画布)",
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
                "name": "canvas_nodes",
                "description": "列出画布上的所有节点",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "canvas_create_node",
                "description": "创建代码编辑节点，用于编写自定义代码逻辑",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "node_name": {
                            "type": "string",
                            "description": "可选，节点名称，默认自动生成",
                        },
                        "position": {
                            "type": "object",
                            "description": '可选，节点位置，例如 {"x": 100, "y": 200}',
                            "properties": {
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                            },
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "canvas_connect_nodes",
                "description": "连接两个节点的端口，建立数据流，支持批量连接",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "connections": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "from_node": {
                                        "type": "string",
                                        "description": "输出节点名称",
                                    },
                                    "from_port": {
                                        "type": "string",
                                        "description": "输出端口名称",
                                    },
                                    "to_node": {
                                        "type": "string",
                                        "description": "输入节点名称",
                                    },
                                    "to_port": {
                                        "type": "string",
                                        "description": "输入端口名称",
                                    },
                                },
                                "required": [
                                    "from_node",
                                    "from_port",
                                    "to_node",
                                    "to_port",
                                ],
                            },
                            "description": '连接列表，如 [{"from_node": "A", "from_port": "out", "to_node": "B", "to_port": "in"}]',
                        },
                    },
                    "required": ["connections"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "canvas_exec_state",
                "description": "获取画布最近执行任务的状态、错误和问题节点，适合自动调试闭环中的验证阶段",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "可选，指定任务 ID",
                        },
                        "include_nodes": {
                            "type": "boolean",
                            "description": "是否附带 failed/running/pending 节点快照",
                        },
                        "include_logs": {
                            "type": "boolean",
                            "description": "是否在问题节点中附带日志摘要",
                        },
                        "log_tail_chars": {
                            "type": "integer",
                            "description": "日志尾部保留字符数",
                        },
                        "recent_limit": {
                            "type": "integer",
                            "description": "未指定 task_id 时返回最近几条记录",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "canvas_get_variables",
                "description": "获取画布全局变量，包括 custom(自定义变量)、node_vars(节点输出变量)、env(环境变量)。无需运行画布即可查看",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "var_type": {
                            "type": "string",
                            "description": "可选，筛选类型: custom/node_vars/env，为空则返回所有",
                            "enum": ["custom", "node_vars", "env"],
                        },
                        "include_values": {
                            "type": "boolean",
                            "description": "是否包含变量值，默认 True；False 则只返回变量名",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "canvas_set_variable",
                "description": "设置画布全局变量，支持 custom/env/node_vars 三种类型",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "var_name": {
                            "type": "string",
                            "description": "变量名（node_vars 时为存储的目标变量名）",
                        },
                        "value": {
                            "type": "Any",
                            "description": "变量值（custom/env 类型时使用）",
                        },
                        "var_type": {
                            "type": "string",
                            "description": "变量类型: custom(自定义变量)/env(环境变量)/node_vars(节点输出变量)",
                            "enum": ["custom", "env", "node_vars"],
                        },
                        "from_node": {
                            "type": "string",
                            "description": "源节点名（node_vars 类型时必填）",
                        },
                        "from_port": {
                            "type": "string",
                            "description": "源输出端口名（node_vars 类型时必填）",
                        },
                    },
                    "required": ["var_name", "var_type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "canvas_snapshot",
                "description": "获取节点信息快照，包含状态、属性、上下游连接。默认不包含日志和代码（节省 token），按需开启",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "node_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "节点名称列表，为空则查询所有节点",
                        },
                        "include_logs": {
                            "type": "boolean",
                            "description": "是否返回日志（默认 False，节省 token）",
                        },
                        "log_type": {
                            "type": "string",
                            "description": "日志类型: historical(历史日志), current(本轮运行日志)",
                            "enum": ["historical", "current"],
                        },
                        "log_tail_chars": {
                            "type": "integer",
                            "description": "日志尾部保留字符数（默认 2000）",
                        },
                        "include_code": {
                            "type": "boolean",
                            "description": "是否附带节点当前执行代码",
                        },
                        "include_input_data": {
                            "type": "boolean",
                            "description": "是否附带节点的输入数据",
                        },
                        "include_output_data": {
                            "type": "boolean",
                            "description": "是否附带节点的输出数据",
                        },
                        "data_truncation": {
                            "type": "integer",
                            "description": "输入/输出数据的最大字符数（默认 1000）",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "canvas_set_prop",
                "description": "设置节点的属性参数，如模型、温度、最大令牌等",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "node_name": {"type": "string", "description": "节点名称"},
                        "properties": {
                            "type": "object",
                            "description": '属性字典，如 {"temperature": 0.7, "max_tokens": 1000}',
                        },
                        "target": {
                            "type": "string",
                            "description": '可选，特殊目标 - "current_node"表示当前节点',
                        },
                    },
                    "required": ["node_name", "properties"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "canvas_edit_prop",
                "description": "编辑节点属性中的字符串，支持单字符串或多字符串替换，适合修改属性里的代码片段",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "node_name": {"type": "string", "description": "节点名称"},
                        "edits": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "property": {
                                        "type": "string",
                                        "description": "属性名",
                                    },
                                    "old_str": {
                                        "type": "string",
                                        "description": "要替换的旧字符串",
                                    },
                                    "new_str": {
                                        "type": "string",
                                        "description": "替换后的新字符串",
                                    },
                                },
                                "required": ["property", "old_str", "new_str"],
                            },
                            "description": '替换列表，如 [{"property": "prompt", "old_str": "x", "new_str": "y"}]',
                        },
                    },
                    "required": ["node_name", "edits"],
                },
            },
        }
    ]
