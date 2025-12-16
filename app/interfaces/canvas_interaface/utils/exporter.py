# /app/interfaces/canvas_interface/exporter.py
import json
import shutil
import traceback
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
                                   f"- 参数参考样例输入：{str(inp['current_value'])[:200]}\n   "
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
            inputs_dir = export_path / "inputs"
            components_dir.mkdir(parents=True, exist_ok=True)
            inputs_dir.mkdir(parents=True, exist_ok=True)

            # 复制组件
            component_path_map = {}
            for fp in used_components:
                if fp in self.file_map:
                    src = Path(self.file_map[fp])
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
            new_nodes_data = {}
            for node in nodes_to_export:
                params = node.model.custom_properties
                if node.FULL_PATH.startswith("代码执行/"):
                    params["run_script"] = node.format_code()
                exported_params = {k: self._process_value_for_export(v, inputs_dir) for k, v in params.items()}
                current_inputs = self._collect_node_inputs(node, inputs_dir)
                node_data = {
                    "name": node.name(),
                    "type_": node.type_,
                    "pos": node.pos(),
                    "input_ports_multi": {p.name(): p.model.multi_connection for p in node.input_ports()},
                    "custom": {
                        "FULL_PATH": node.FULL_PATH,
                        "FILE_PATH": component_path_map.get(self.file_map.get(node.FULL_PATH, ""), ""),
                        "params": exported_params,
                        "input_values": serialize_for_json(current_inputs)
                    }
                }
                if isinstance(node, ControlFlowBackdrop):
                    node_data["custom"]["internal_nodes"] = [n.id for n in node.nodes()]
                new_nodes_data[node.id] = node_data

            # 导出连接
            original_conns = self.parent.graph.serialize_session()["connections"]
            node_ids = {n.id for n in nodes_to_export}
            new_conns = [c for c in original_conns if c["out"][0] in node_ids and c["in"][0] in node_ids]

            # 构建 project_spec.json
            project_spec = {"version": "1.0", "graph_name": project_name, "inputs": {}, "outputs": {}}
            for i, item in enumerate(selected_inputs):
                key = item.get("custom_key", f"input_{i}")
                project_spec["inputs"][key] = item
            for i, item in enumerate(selected_outputs):
                key = item.get("custom_key", f"output_{i}")
                project_spec["outputs"][key] = {
                    "node_id": item["node_id"],
                    "output_name": item["output_name"],
                    "format": item["format"]
                }

            # 保存文件
            (export_path / "model.workflow.json").write_text(
                json.dumps(serialize_for_json({
                    "graph": {"nodes": new_nodes_data, "connections": new_conns},
                    "runtime": {
                        "environment": self.parent.env_combo.currentData(),
                        "environment_exe": self.parent.get_current_python_exe(),
                        "execution_order": [(n.id, n.name()) for n in execution_order],
                        "node_id2stable_key": {n.id: f"{n.FULL_PATH}||{n.name()}" for n in nodes_to_export},
                        "node_states": {f"{n.FULL_PATH}||{n.name()}": self.parent.node_status.get(n.id, "unrun") for n in nodes_to_export},
                        "node_outputs": {f"{n.FULL_PATH}||{n.name()}": serialize_for_json(getattr(n, '_output_values', {})) for n in nodes_to_export},
                        "column_select": {f"{n.FULL_PATH}||{n.name()}": getattr(n, 'column_select', {}) for n in nodes_to_export},
                        "global_variable": self.parent.global_variables.serialize()
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
            if not cls:
                continue
            # 超参数
            for prop_name, val in node.model.custom_properties.items():
                prop_def = cls.properties.get(prop_name)
                if not prop_def:
                    continue
                item = {
                    "type": "组件超参数",
                    "node_id": node.id,
                    "node_name": node.name(),
                    "param_name": prop_name,
                    "param_desc": prop_def.label,
                    "current_value": val,
                    "display_name": f"{node.name()} → {prop_name}",
                    "format": getattr(prop_def, 'type', None).name if prop_def else "TEXT",
                    "format_desc": prop_def.type.value if prop_def else "文本",
                }
                if prop_def.type.name == "RANGE":
                    item.update({"min": float(prop_def.min), "max": float(prop_def.max), "step": float(prop_def.step)})
                elif prop_def.type.name == "DYNAMICFORM" and prop_def.schema:
                    item["schema"] = {k: {"type": v.type.name if v else "TEXT"} for k, v in prop_def.schema.items()}
                inputs.append(item)
            # 输入端口
            for port in node.input_ports():
                port_name = port.name()
                port_desc = ""
                port_type = "TEXT"
                port_type_desc = ""
                if hasattr(cls, 'inputs'):
                    for inp in cls.inputs:
                        if inp.name == port_name:
                            port_type = inp.type.name
                            port_type_desc = inp.type.value
                            port_desc = inp.label
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
                    "current_value": val,
                    "display_name": f"{port_name} → {node.name()}",
                    "format": port_type,
                    "format_desc": port_type_desc
                })
        return inputs

    def _collect_outputs(self, nodes):
        outputs = []
        for node in nodes:
            outputs_dict = getattr(node, '_output_values', {})
            cls = self.component_map.get(node.FULL_PATH)
            for out_name, out_val in outputs_dict.items():
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
                outputs.append({
                    "type": "组件输出",
                    "node_id": node.id,
                    "node_name": node.name(),
                    "output_name": out_name,
                    "output_desc": out_desc,
                    "sample_value": str(out_val)[:50] + "..." if len(str(out_val)) > 50 else str(out_val),
                    "display_name": f"{node.name()} → {out_name}",
                    "format": out_type,
                    "format_desc": out_type_desc
                })
        return outputs

    def _process_value_for_export(self, value, inputs_dir: Path):
        if isinstance(value, str):
            p = Path(value)
            if p.is_file():
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
                    inputs[port_name] = [self._process_value_for_export(up.node()._output_values.get(up.name()), inputs_dir) for up in connected]
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