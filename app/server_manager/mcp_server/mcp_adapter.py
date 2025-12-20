# mcp_adapter.py
import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any

from loguru import logger

from app.utils.utils import serialize_for_json


class McpWorkflowTool:
    """MCP 工作流适配器，用于将 MCP 工作流转换为 runner 可用的格式"""

    def __init__(self, project_dir: Path, python_executable: str = ""):
        self.project_dir = Path(project_dir).resolve()
        spec_path = self.project_dir / "project_spec.json"
        if not spec_path.exists():
            raise ValueError(f"project_spec.json not found in {project_dir}")

        with open(spec_path, 'r', encoding='utf-8') as f:
            self.spec = json.load(f)  # 注意：这里先不反序列化，只读原始 JSON
        with open(self.project_dir / "model.workflow.json", 'r', encoding='utf-8') as f:
            full_data = json.load(f)
        runtime = full_data.get("runtime", {})
        self.name = self.project_dir.name
        self.description = f"低代码导出工作流: {self.spec.get('graph_name', self.project_dir.name)}"  # 或留空，MCP 允许无描述

        # 获取运行时 Python 路径
        self.python_executable = python_executable or runtime.get("environment_exe")
        if not Path(self.python_executable).exists():
            raise RuntimeError(f"Python executable not found: {self.python_executable}")

    def get_input_schema(self) -> Dict[str, Any]:
        properties = {}
        required = []  # 注意：你的 spec 没有 required 字段，可默认非必填

        for key, cfg in self.spec.get("inputs", {}).items():
            fmt = cfg.get("format", "TEXT")
            # 使用 display_name 作为描述，fallback 到 key
            desc = cfg.get("display_name", key)

            if fmt in ["TEXT", "LONGTEXT", "JSON"]:
                schema = {"type": "string", "description": desc}
            elif fmt == "INT":
                schema = {"type": "integer", "description": desc}
            elif fmt == "FLOAT":
                schema = {"type": "number", "description": desc}
            elif fmt == "BOOL":
                schema = {"type": "boolean", "description": desc}
            elif fmt in ["FILE", "IMAGE", "EXCEL", "UPLOAD"]:
                schema = {
                    "type": "string",
                    "format": "data-url",
                    "description": desc
                }
            elif fmt.startswith("ARRAY"):
                # 你的 format 是 "ARRAY"，没有具体类型，保守用 string[]
                schema = {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": desc
                }
            else:
                # 未知格式默认为 string
                schema = {"type": "string", "description": desc}

            # 你的 spec 没有 required 字段，所以不加到 required 列表
            # 如果未来支持，可加 cfg.get("required", False)
            properties[key] = schema

        return {
            "type": "object",
            "properties": properties,
            # 注意：required 可以为空列表，表示所有参数可选
            "required": required
        }

        return {"type": "object", "properties": properties, "required": required}

    def _prepare_inputs(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """将 MCP 输入转为 runner 可接收的 external_inputs（含临时文件路径）"""
        external_inputs = {}
        temp_files = []  # 用于后续清理（可选）

        for key, cfg in self.spec.get("inputs", {}).items():
            value = args.get(key)
            fmt = cfg.get("format", "TEXT")

            if value is None and not cfg.get("required", False):
                external_inputs[key] = None
                continue

            if fmt in ["FILE", "IMAGE", "EXCEL", "UPLOAD"]:
                if isinstance(value, str):
                    if Path(value).exists():
                        tmp_path = value
                    else:
                        if value.startswith("data:"):
                            b64_part = value.split(",", 1)[1] if "," in value else value
                        else:
                            b64_part = value
                        binary_data = base64.b64decode(b64_part)
                        suffix = self._guess_suffix(fmt)
                        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                            tmp.write(binary_data)
                            tmp_path = tmp.name
                else:
                    raise ValueError(f"File input {key} must be base64 string")

                external_inputs[key] = tmp_path
                temp_files.append(tmp_path)  # 记录以便清理
            else:
                external_inputs[key] = value

        # 将 temp_files 存入 external_inputs 的隐藏字段（用于 runner 清理）
        external_inputs["__temp_files__"] = temp_files
        return external_inputs

    def _guess_suffix(self, fmt: str) -> str:
        mapping = {"IMAGE": ".png", "EXCEL": ".xlsx"}
        return mapping.get(fmt, "")

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """通过子进程执行工作流，返回 JSON 结果"""
        try:
            # 1. 准备输入
            external_inputs = self._prepare_inputs(args)

            # 2. 写入 input.pkl（放在项目目录，供子进程读取）
            input_path = self.project_dir / "input.pkl"
            with open(input_path, "wb") as f:
                # 注意：这里不反序列化 spec，只传原始输入
                import pickle
                pickle.dump(external_inputs, f)

            # 3. 启动子进程（使用指定 Python 环境）
            runner_script = self.project_dir / "runner" / "workflow_runner.py"
            cmd = [self.python_executable, str(runner_script)]

            logger.info(f"Launching subprocess: {' '.join(cmd)}")
            proc = subprocess.run(
                cmd,
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=300,
                encoding='utf-8',
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            # 4. 检查子进程是否成功
            if proc.returncode != 0:
                stderr_str = proc.stderr.decode('utf-8', errors='replace') if proc.stderr else "No stderr"
                logger.error(f"Subprocess failed: {stderr_str}")
                raise RuntimeError(f"Workflow subprocess failed: {stderr_str[:500]}...")

            # 5. 读取结果
            result_path = self.project_dir / "result.pkl"
            if not result_path.exists():
                raise RuntimeError("result.pkl not generated by workflow")

            with open(result_path, "rb") as f:
                outputs = pickle.load(f)

            # 6. 序列化为 JSON 兼容格式
            return serialize_for_json(outputs)

        except subprocess.TimeoutExpired:
            raise RuntimeError("Workflow execution timed out (5 minutes)")
        except Exception as e:
            logger.exception("MCP tool execution failed")
            raise RuntimeError(f"Execution error: {str(e)}")
        finally:
            # 清理临时文件（input.pkl, result.pkl, 上传文件等）
            for f in [self.project_dir / "input.pkl", self.project_dir / "result.pkl"]:
                if f.exists():
                    try:
                        os.remove(f)
                    except:
                        pass

            # 清理上传的临时文件
            if "external_inputs" in locals():
                for tmp_file in external_inputs.get("__temp_files__", []):
                    try:
                        os.remove(tmp_file)
                    except:
                        pass