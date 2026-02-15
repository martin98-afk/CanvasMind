# /app/interfaces/canvas_interface/exporter.py
import json
import shutil
import traceback
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QImage, QPainter

from app.nodes.backdrop_node import ControlFlowBackdrop
from app.templates.readme_template import DETAILED_README
from app.utils.config import Settings
from app.utils.utils import serialize_for_json, topological_sort, resource_path
from app.widgets.dialog_widget.project_export_dialog import ProjectExportFlowDialog
from .logger import get_logger
from app.interfaces.canvas_interaface.widgets.message_manager import MessageManager

logger = get_logger("Exporter")


class CanvasExporter:
    def __init__(self, parent, component_map, file_map, execution_order=None):
        self.parent = parent
        self.component_map = component_map
        self.file_map = file_map
        self.execution_order = execution_order
        self.config = Settings.get_instance()

    def export_selected_nodes_as_project(self):
        try:
            nodes_to_export = self.parent.graph.selected_nodes() or self.parent.graph.all_nodes()
            execution_order = self.execution_order or topological_sort(nodes_to_export)

            if not nodes_to_export:
                MessageManager.warning("导出失败", "选中的节点无效（只有分组节点）！", self.parent)
                return
            # 过滤注释节点
            execution_order = [node for node in execution_order if not node.type_== "general.StickyNote"]
            nodes_to_export = [node for node in nodes_to_export if not node.type_== "general.StickyNote"]
            # 收集候选输入/输出
            candidate_inputs = self._collect_inputs(execution_order)
            candidate_outputs = self._collect_outputs(execution_order)
            # 构建依赖
            used_components = {node.FULL_PATH for node in nodes_to_export}
            requirements = set()
            for fp in used_components:
                cls = self.component_map.get(fp)
                if cls and hasattr(cls, 'requirements'):
                    req_str = cls.requirements
                    if req_str:
                        requirements.update(pkg.strip() for pkg in req_str.split(',') if pkg.strip())
            requirements.update(self.config.default_packages.value)

            # 构造markdown输入、输出端口信息
            def generate_markdown(input: list, output: list):
                input_desc = ""
                for i, inp in enumerate(input):
                    input_desc += (f"- 参数{i + 1}：{inp['custom_key']}\n   "
                                   f"- 参数描述：{inp.get('param_desc') or inp.get('port_desc')}\n   "
                                   f"- 参数格式：{inp['format']}\n   "
                                   f"- 参数格式描述：{inp['format_desc']}\n   "
                                   f"- 参数参考样例输入：{str(inp['current_value'])[:300]}\n   "
                                   f"- 所属组件名：{inp['node_name']}\n   "
                                   f"- 组件参数类型：{inp['type']}\n\n")
                output_desc = ""
                for i, out in enumerate(output):
                    output_desc += (f"- 输出{i + 1}：{out['custom_key']}\n   "

                                    f"- 输出描述：{out.get('output_desc')}\n   "
                                    f"- 输出格式：{out['format']}\n   "
                                    f"- 输出格式描述：{out['format_desc']}\n   "
                                    f"- 所属组件名：{out['node_name']}\n   "
                                    f"- 组件参数类型：{out['type']}\n\n")

                initial_readme = DETAILED_README.format(
                    project_name_placeholder=self.parent.workflow_name,
                    original_canvas=self.parent.workflow_name,
                    export_time=export_time,
                    input_desc=input_desc,
                    output_desc=output_desc,
                    component_names="\n".join(["- " + Path(fp).stem for fp in used_components]),
                    conn_count=len(self.parent.graph.serialize_session().get("connections", []))
                )
                return initial_readme

            # README
            export_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 弹出流程对话框
            flow_dialog = ProjectExportFlowDialog(
                candidate_items=candidate_inputs + candidate_outputs,
                parent=self.parent,
                project_name=self.parent.workflow_name,
                requirements='\n'.join(sorted(requirements)) if requirements else "# 无依赖",
                readme_func=generate_markdown
            )

            if not flow_dialog.exec():
                logger.info("用户取消了项目导出流程")
                return

            selected_inputs = flow_dialog.get_selected_inputs()
            selected_outputs = flow_dialog.get_selected_outputs()
            project_name = flow_dialog.get_project_name()
            final_readme = flow_dialog.get_readme_content()
            final_requirements = flow_dialog.get_requirements()

            if not project_name:
                MessageManager.warning("导出失败", "项目名不能为空！", self.parent)
                return

            # 导出目录
            export_path = Path(self.config.project_paths.value[0]) / project_name
            export_path.mkdir(parents=True, exist_ok=True)
            components_dir = export_path / "components"
            component_extensions_dir = export_path / "component_extensions"
            inputs_dir = export_path / "inputs"
            components_dir.mkdir(parents=True, exist_ok=True)
            inputs_dir.mkdir(parents=True, exist_ok=True)

            # 复制组件
            component_path_map = {}
            for fp in used_components:
                if fp in self.file_map:
                    src = Path(self.file_map[fp])
                    uuid = src.stem
                    # 同步拷贝组件扩展资源
                    src_extension_path = Path(resource_path(f"app/component_extensions/{uuid}"))
                    if src_extension_path.exists():
                        shutil.copytree(src_extension_path, component_extensions_dir / uuid, dirs_exist_ok=True)
                    if src.exists():
                        try:
                            rel = src.relative_to(src.parent.parent)
                        except ValueError:
                            rel = src.name
                        dst = components_dir / rel
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dst)
                        component_path_map[str(src)] = ("components" / rel).as_posix()

            # 导出节点数据
            serialized_export_nodes = self.parent.graph._serialize(nodes_to_export)
            for node in nodes_to_export:
                params = node.model.custom_properties
                reserved_keys = node.model.properties.keys()
                if node.FULL_PATH.startswith("代码执行/"):
                    params["run_script"] = node.format_code()
                exported_params = {
                    self._process_key_for_export(k, reserved_keys): self._process_value_for_export(v, inputs_dir)
                    for k, v in params.items()
                    if k not in ("global_variable", "_collapse", "version")
                }
                current_inputs = self._collect_node_inputs(node, inputs_dir)
                serialized_export_nodes["nodes"][node.id]["custom"].update(exported_params)
                serialized_export_nodes["nodes"][node.id]["input_values"] = serialize_for_json(current_inputs)
                if isinstance(node, ControlFlowBackdrop):
                    serialized_export_nodes["nodes"][node.id]["custom"]["internal_nodes"] = [n.id for n in node.nodes()]
            # 导出连接
            original_conns = serialized_export_nodes.get("connections")
            node_ids = {n.id for n in nodes_to_export}
            if original_conns:
                new_conns = [c for c in original_conns if c["out"][0] in node_ids and c["in"][0] in node_ids]
            else:
                new_conns = []
            serialized_export_nodes["connections"] = new_conns
            # 构建 project_spec.json
            project_spec = {"version": "1.0", "graph_name": project_name, "inputs": {}, "outputs": {}}
            for i, item in enumerate(selected_inputs):
                key = item.get("custom_key", f"input_{i}")
                project_spec["inputs"][key] = item
            for i, item in enumerate(selected_outputs):
                key = item.get("custom_key", f"output_{i}")
                project_spec["outputs"][key] = {
                    "node_id": item["node_id"],
                    "node_name": item["node_name"],
                    "output_name": item["output_name"],
                    "format": item["format"]
                }

            # 保存文件
            (export_path / "model.workflow.json").write_text(
                json.dumps(serialize_for_json({
                    "graph": serialized_export_nodes,
                    "runtime": {
                        "environment": self.parent.env_combo.currentData(),
                        "environment_exe": self.parent.get_current_python_exe(),
                        "execution_order": [(n.id, n.name()) for n in execution_order],
                    },
                    "candidate_inputs": candidate_inputs,  # 可选：保留候选列表供参考
                    "candidate_outputs": candidate_outputs  # 可选：保留候选列表供参考
                }), ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

            (export_path / "project_spec.json").write_text(
                json.dumps(project_spec, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            # === 生成并保存 MCP 实例脚本 ===
            mcp_code = self._generate_mcp_instance_code(project_spec)
            (export_path / "mcp_instance.py").write_text(mcp_code, encoding="utf-8")

            (export_path / "requirements.txt").write_text(final_requirements, encoding="utf-8")
            (export_path / "README.md").write_text(final_readme, encoding="utf-8")

            # 复制 runner
            runner_src = Path(resource_path("app")) / "runner"
            if runner_src.exists():
                shutil.copytree(str(runner_src), str(export_path / "runner"), dirs_exist_ok=True)
            base_src = Path(resource_path("app")) / "components" / "base.py"
            if base_src.exists():
                shutil.copy(str(base_src), str(components_dir / "base.py"))
            for file in ["run.py", "scan_components.py", "api_server.py"]:
                src = export_path / "runner" / file
                if src.exists():
                    shutil.move(str(src), str(export_path / file))

            self._generate_selected_nodes_thumbnail(export_path)
            MessageManager.success("导出成功", f"模型项目已导出到:\n{export_path}", self.parent)

        except Exception as e:
            logger.error(traceback.format_exc())
            MessageManager.error("导出失败", f"错误: {str(e)}", self.parent)

    def _collect_inputs(self, nodes):
        inputs = []
        for node in nodes:
            cls = self.component_map.get(node.FULL_PATH)
            # 收集输入端口连接的上游节点名和端口名
            port_dict = defaultdict(list)
            for input_port in node.input_ports():
                port_name = input_port.name()
                connected = input_port.connected_ports()
                for connect_pipe in connected:
                    port_dict[port_name].append((connect_pipe.node().name(), connect_pipe.name()))
            # 超参数
            for prop_name, val in node.model.custom_properties.items():
                if cls is None:
                    continue
                prop_def = cls.properties.get(prop_name)
                if not prop_def:
                    continue
                item = {
                    "type": "组件超参数",
                    "node_id": node.id,
                    "node_name": node.name(),
                    "param_name": prop_name,
                    "param_desc": prop_def.label,
                    "current_value": str(val)[:300],
                    "display_name":
                        f"{prop_name}({prop_def.label})",
                    "format": getattr(prop_def, 'type', None).name if prop_def else "TEXT",
                    "format_desc": prop_def.type.value if prop_def else "文本",
                }
                if prop_def.type.name == "RANGE":
                    item.update({"min": float(prop_def.min), "max": float(prop_def.max), "step": float(prop_def.step)})
                elif prop_def.type.name == "DYNAMICFORM" and prop_def.schema:
                    item["schema"] = {k: {"type": v.type.name if v else "TEXT"} for k, v in prop_def.schema.items()}
                inputs.append(item)
            # 输入端口
            node.model.inputs.keys()
            for port in node.input_ports():
                port_name = port.name()
                port_desc = ""
                port_type = "TEXT"
                port_type_desc = ""
                if cls is not None and hasattr(cls, 'inputs'):
                    for inp in cls.inputs:
                        if inp.name == port_name:
                            port_type = inp.type.name
                            port_type_desc = inp.type.value
                            port_desc = inp.label
                            break
                elif node.FULL_PATH.startswith("代码执行/"):
                    input_ports = node.model.custom_properties['input_ports']
                    for inp in input_ports:
                        if inp["name"] == port_name:
                            port_type = inp["type"]
                            break
                if port.multi_connection():
                    port_type = f"ARRAY[{port_type}]"
                connected = port.connected_ports()
                if connected:
                    if len(connected) == 1:
                        val = connected[0].node()._output_values.get(connected[0].name())
                    else:
                        val = [up.node()._output_values.get(up.name()) for up in connected]
                else:
                    val = getattr(node, '_input_values', {}).get(port_name, None)
                inputs.append({
                    "type": "组件输入",
                    "node_id": node.id,
                    "node_name": node.name(),
                    "port_name": port_name,
                    "port_desc": port_desc,
                    "current_value": str(val)[:300],
                    "display_name": (f"{port_name}" if not port_desc else f"{port_name}({port_desc})") +
                        "".join([f" <- {val[0]}:{val[1]}" for val in port_dict.get(port_name, [])]),
                    "format": port_type,
                    "format_desc": port_type_desc
                })
        return inputs

    def _collect_outputs(self, nodes):
        """获取导出项目的输出参数候选"""
        outputs = []
        for node in nodes:
            # 收集输出端口连接的下游节点名和端口名
            port_dict = defaultdict(list)
            for output_port in node.output_ports():
                port_name = output_port.name()
                connected = output_port.connected_ports()
                for connect_pipe in connected:
                    port_dict[port_name].append((connect_pipe.node().name(), connect_pipe.name()))
            output_ports = node.model.outputs.keys()
            cls = self.component_map.get(node.FULL_PATH)
            for out_name in output_ports:
                out_type = "TEXT"
                out_type_desc = ""
                out_desc = ""
                if hasattr(cls, 'outputs'):
                    for out in cls.outputs:
                        if out.name == out_name:
                            out_type = out.type.name
                            out_type_desc = out.type.value
                            out_desc = out.label
                            break
                port_suffix = "".join([f" -> {val[0]}:{val[1]}" for val in port_dict.get(out_name, [])])
                outputs.append({
                    "type": "组件输出",
                    "node_id": node.id,
                    "node_name": node.name(),
                    "output_name": out_name,
                    "output_desc": out_desc,
                    "display_name": (f"{out_name}" if not out_desc else f"{out_name}({out_desc})") + port_suffix,
                    "format": out_type,
                    "format_desc": out_type_desc
                })
        return outputs

    def _process_key_for_export(self, key, reserved_keys):
        if key.startswith("_") and key[1:] in reserved_keys:
            key = key[1:]
        return key

    def _process_value_for_export(self, value, inputs_dir: Path):
        if isinstance(value, str):
            p = Path(value)
            if p.exists():
                dst = inputs_dir / p.name
                if not dst.exists():
                    shutil.copy2(p, dst)
                return (Path("inputs") / p.name).as_posix()
        elif isinstance(value, dict):
            return {k: self._process_value_for_export(v, inputs_dir) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._process_value_for_export(v, inputs_dir) for v in value]
        return value

    def _collect_node_inputs(self, node, inputs_dir):
        inputs = {}
        for port in node.input_ports():
            port_name = port.name()
            connected = port.connected_ports()
            if connected:
                if len(connected) == 1:
                    val = connected[0].node()._output_values.get(connected[0].name())
                    inputs[port_name] = self._process_value_for_export(val, inputs_dir)
                else:
                    inputs[port_name] = [
                        self._process_value_for_export(up.node()._output_values.get(up.name()), inputs_dir) for up in
                        connected]
            else:
                val = getattr(node, '_input_values', {}).get(port_name, None)
                inputs[port_name] = self._process_value_for_export(val, inputs_dir)
        return inputs

    def _generate_selected_nodes_thumbnail(self, export_path: Path):
        """为选中的节点生成缩略图并保存到 export_path 下（如 preview.png）"""
        try:
            selected = self.parent.graph.selected_nodes()
            if not selected:
                return
            scene = self.parent.graph.viewer().scene()
            rect = QRectF()
            for node in selected:
                item_rect = node.view.sceneBoundingRect()
                rect = rect.united(item_rect)
            if rect.isEmpty():
                return
            # 扩展边距
            rect.adjust(-25, -25, 25, 25)
            # 创建图像
            image = QImage(rect.size().toSize(), QImage.Format_ARGB32)
            image.fill(Qt.white)
            painter = QPainter(image)
            # 渲染选中区域
            scene.render(painter, target=QRectF(image.rect()), source=rect)
            painter.end()
            # 保存为 preview.png
            preview_path = export_path / "preview.png"
            image.save(str(preview_path), "PNG")
            logger.info(f"✅ 子图预览图已保存: {preview_path}")
        except Exception as e:
            logger.error(f"预览图生成失败: {e}")
            MessageManager.warning("预览图", f"生成失败: {str(e)}", self.parent)

    def _generate_mcp_instance_code(self, project_spec):
        import json
        graph_name = project_spec.get("graph_name", "未命名工作流")

        # --- 1. 构建全信息描述文档 (塞入 description) ---
        doc_lines = [
            f"工具名称: {graph_name}",
            "描述: 此工具由可视化画布导出，用于执行特定的 AI/数据工作流任务。",
            "",
            "=== 输入参数详细定义 ==="
        ]

        input_args = []
        for key, info in project_spec.get("inputs", {}).items():
            node_name = info.get("node_name", "未知节点")
            p_desc = info.get("param_desc") or info.get("port_desc") or "无描述"
            fmt = info.get("format", "TEXT")
            fmt_desc = info.get("format_desc", "")

            # 塞入文档
            doc_lines.append(f"- 参数字段: {key}")
            doc_lines.append(f"  来自节点: {node_name}")
            doc_lines.append(f"  功能描述: {p_desc}")
            doc_lines.append(f"  数据格式: {fmt} ({fmt_desc})")
            doc_lines.append(f"  参考数据: {info.get('current_value')}")
            doc_lines.append("")

            # 构造 Pydantic 参数
            safe_key = f"{key}_param" if key in ("input", "type", "id") else key
            input_args.append(f'    {safe_key}: str = Field(default={json.dumps(info.get("current_value"))}, description="输入字段: {key}")')

        doc_lines.append("=== 输出结果结构预览 ===")
        for ok, ov in project_spec.get("outputs", {}).items():
            node_name = ov.get("node_name", "未知节点")
            doc_lines.append(f"- 输出字段: {ok}")
            doc_lines.append(f"  来自节点: {node_name}")
            doc_lines.append(f"  数据格式: {ov.get('format', 'TEXT')}")

        full_description = "\n".join(doc_lines)

        # 参数映射逻辑
        mapping_str = ", ".join([f'"{k}": {f"{k}_param" if k in ("input", "type", "id") else k}' for k in
                                 project_spec["inputs"].keys()])

        # --- 2. 生成代码模板 ---
        template = f'''# -*- coding: utf-8 -*-
import traceback
import json, httpx, os
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from pydantic import Field

# 动态地址文件
CUR_DIR = Path(__file__).parent
URL_FILE = CUR_DIR / "service_url.txt"

mcp = FastMCP("{graph_name}-Server")

def get_api_url():
    if not URL_FILE.exists():
        raise RuntimeError("【错误】服务未上线。请在画布管理界面点击'上线'按钮。")
    return URL_FILE.read_text(encoding="utf-8").strip()

@mcp.tool(
    name="run_{"".join([c if c.isalnum() else "_" for c in graph_name]).lower()}",
    title="{graph_name}",
    description={json.dumps(full_description, ensure_ascii=False)}
)
async def execute_task({", ".join(input_args)}):
    """
    {graph_name} 的核心执行工具。
    """
    # 组装请求
    payload = {{{mapping_str}}}
    payload = {{k: v for k, v in payload.items() if v is not None}}

    try:
        target_url = get_api_url()
        async with httpx.AsyncClient(timeout=300.0) as client:
            # 这里的 params={{"mcp": "true"}} 会触发你 api_server.py 里的 MCP 返回逻辑
            resp = await client.post(target_url, json=payload, params={{"mcp": "true"}})
            resp.raise_for_status()
            return json.dumps(resp.json(), indent=2, ensure_ascii=False)
    except Exception as e:
        return f"执行失败: {{traceback.format_exc()}}"

if __name__ == "__main__":
    mcp.run()
'''
        return template