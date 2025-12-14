# mcp_server.py
import base64
import io
import json
import os
import pickle
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Any, List

import numpy as np
import pandas as pd
import pyarrow as pa
from pyarrow import feather
from loguru import logger

# ------------------ 序列化逻辑 ------------------

def serialize_for_json(obj, large_list_threshold=1000):
    """递归将对象转换为 JSON 可序列化格式，支持 ndarray / DataFrame / 大列表"""
    if isinstance(obj, dict):
        return {k: serialize_for_json(v, large_list_threshold) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        if len(obj) > large_list_threshold:
            try:
                arr = np.array(obj)
                if arr.dtype.kind in 'biufc':  # 基本数值类型
                    buffer = io.BytesIO()
                    np.save(buffer, arr, allow_pickle=False)
                    return {
                        "__type__": "LargeList",
                        "data": base64.b64encode(buffer.getvalue()).decode('utf-8'),
                        "dtype": str(arr.dtype),
                        "format": "numpy_binary",
                        "original_type": "list" if isinstance(obj, list) else "tuple"
                    }
            except Exception:
                pass
            # fallback to string
            return str(obj)[:500] + "..." if len(str(obj)) > 500 else str(obj)
        else:
            return [serialize_for_json(v, large_list_threshold) for v in obj]
    elif isinstance(obj, pd.DataFrame):
        try:
            buffer = io.BytesIO()
            table = pa.Table.from_pandas(obj)
            feather.write_feather(table, buffer, compression='zstd')
            return {
                "__type__": "DataFrame",
                "data": base64.b64encode(buffer.getvalue()).decode('utf-8'),
                "format": "feather_base64",
                "shape": obj.shape
            }
        except Exception as e:
            logger.warning(f"DataFrame serialization failed: {e}")
            return f"<DataFrame {obj.shape}>"
    elif isinstance(obj, pd.Series):
        return serialize_for_json(obj.to_frame())
    elif isinstance(obj, np.ndarray):
        try:
            buffer = io.BytesIO()
            np.save(buffer, obj, allow_pickle=False)
            return {
                "__type__": "ndarray",
                "data": base64.b64encode(buffer.getvalue()).decode('utf-8'),
                "dtype": str(obj.dtype),
                "shape": obj.shape,
                "format": "npy_base64"
            }
        except Exception:
            return obj.tolist()  # safe fallback
    elif isinstance(obj, (np.integer, np.floating, np.bool_)):
        return obj.item()
    elif hasattr(obj, '__dict__'):
        try:
            return {
                "__type__": f"{obj.__class__.__module__}.{obj.__class__.__name__}",
                "__data__": serialize_for_json(obj.__dict__, large_list_threshold)
            }
        except Exception:
            return str(obj)
    else:
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)


# ------------------ 工具执行器 ------------------

class McpWorkflowTool:
    name: str

    def __init__(self, project_dir: Path, python_executable: str = ""):
        self.project_dir = Path(project_dir).resolve()
        spec_path = self.project_dir / "project_spec.json"
        if not spec_path.exists():
            raise ValueError(f"project_spec.json not found in {project_dir}")

        with open(spec_path, 'r', encoding='utf-8') as f:
            self.spec = json.load(f)

        with open(self.project_dir / "model.workflow.json", 'r', encoding='utf-8') as f:
            full_data = json.load(f)
        runtime = full_data.get("runtime", {})
        self.name = self.project_dir.name
        self.description = f"低代码导出工作流: {self.spec.get('graph_name', self.name)}"
        self.python_executable = python_executable or runtime.get("environment_exe")
        if not Path(self.python_executable).exists():
            raise RuntimeError(f"Python executable not found: {self.python_executable}")

    def get_input_schema(self) -> Dict[str, Any]:
        properties = {}
        for key, cfg in self.spec.get("inputs", {}).items():
            fmt = cfg.get("format", "TEXT")
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
                schema = {"type": "string", "format": "data-url", "description": desc}
            elif fmt.startswith("ARRAY"):
                schema = {"type": "array", "items": {"type": "string"}, "description": desc}
            else:
                schema = {"type": "string", "description": desc}
            properties[key] = schema
        return {"type": "object", "properties": properties, "required": []}

    def _prepare_inputs(self, args: Dict[str, Any], temp_dir: Path) -> Dict[str, Any]:
        external_inputs = {}
        temp_files = []
        for key, cfg in self.spec.get("inputs", {}).items():
            value = args.get(key)
            fmt = cfg.get("format", "TEXT")
            if value is None and not cfg.get("required", False):
                external_inputs[key] = None
                continue
            if fmt in ["FILE", "IMAGE", "EXCEL", "UPLOAD"]:
                if isinstance(value, str):
                    b64_part = value.split(",", 1)[1] if "," in value else value
                    binary_data = base64.b64decode(b64_part)
                else:
                    raise ValueError(f"File input {key} must be base64 string")
                suffix = {"IMAGE": ".png", "EXCEL": ".xlsx"}.get(fmt, "")
                tmp_path = temp_dir / f"input_{key}{suffix}"
                tmp_path.write_bytes(binary_data)
                external_inputs[key] = str(tmp_path)
                temp_files.append(str(tmp_path))
            else:
                external_inputs[key] = value
        external_inputs["__temp_files__"] = temp_files
        return external_inputs

    def execute(self, args: Dict[str, Any]) -> Any:
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            external_inputs = self._prepare_inputs(args, temp_dir)

            # 使用临时目录存放 input/result
            input_path = self.project_dir / "input.pkl"
            result_path = self.project_dir / "result.pkl"

            with open(input_path, "wb") as f:
                pickle.dump(external_inputs, f)

            runner_script = self.project_dir / "runner" / "workflow_runner.py"
            cmd = [str(self.python_executable), str(runner_script)]

            logger.info(f"Launching subprocess: {cmd}")
            proc = subprocess.run(
                cmd,
                cwd=self.project_dir,
                env={**os.environ, "MCP_INPUT_PATH": str(input_path), "MCP_RESULT_PATH": str(result_path)},
                capture_output=True,
                text=False,  # 二进制模式，避免编码问题
                timeout=300,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            if proc.returncode != 0:
                stderr_str = proc.stderr.decode('utf-8', errors='replace') if proc.stderr else "No stderr"
                logger.error(f"Subprocess failed: {stderr_str}")
                raise RuntimeError(f"Workflow failed: {stderr_str[:500]}...")

            if not result_path.exists():
                raise RuntimeError("result.pkl not generated")

            with open(result_path, "rb") as f:
                outputs = pickle.load(f)

            return serialize_for_json(outputs)


# ------------------ MCP 服务器 ------------------

class GlobalMcpServer:
    def __init__(self, exports_dir: Path):
        self.exports_dir = exports_dir
        self.tools: Dict[str, McpWorkflowTool] = {}
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
                    logger.error(f"Skip invalid tool {p.name}: {e}")

    def handle_initialize(self, req_id):
        tools_obj = {
            name: {
                "description": tool.description,
                "inputSchema": tool.get_input_schema()
            }
            for name, tool in self.tools.items()
        }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "CanvasMind MCP Server", "version": "1.0"},
                "capabilities": {"tools": tools_obj}
            }
        }

    def handle_call(self, req_id, name: str, args: Dict[str, Any]):
        if name not in self.tools:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Tool '{name}' not found"}
            }
        try:
            result = self.tools[name].execute(args)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "toolResult", "toolResult": result}]
                }
            }
        except subprocess.TimeoutExpired:
            error_msg = "Workflow execution timed out (5 minutes)"
            logger.error(error_msg)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": error_msg}
            }
        except Exception as e:
            error_msg = f"Execution error: {str(e)}"
            logger.exception("MCP tool execution failed")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": error_msg}
            }

    def handle_ping(self, req_id):
        return {"jsonrpc": "2.0", "id": req_id, "result": "pong"}

    def run_stdio(self):
        logger.info(f"[MCP Server] 已加载工具: {list(self.tools.keys())}")
        try:
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                try:
                    req = json.loads(line)
                    method = req.get("method")
                    req_id = req.get("id")
                    if method == "initialize":
                        resp = self.handle_initialize(req_id)
                    elif method == "call":
                        resp = self.handle_call(req_id, req["params"]["name"], req["params"]["arguments"])
                    elif method == "ping":
                        resp = self.handle_ping(req_id)
                    elif method == "shutdown":
                        resp = {"jsonrpc": "2.0", "id": req_id, "result": None}
                        print(json.dumps(resp), flush=True)
                        return
                    else:
                        continue
                    print(json.dumps(resp, ensure_ascii=False, separators=(',', ':')), flush=True)
                except Exception as e:
                    logger.exception("Failed to handle request")
                    # 不返回错误（防止崩溃），但可选返回 JSON-RPC 错误
                    pass
        except KeyboardInterrupt:
            return


# ------------------ 启动 ------------------

if __name__ == "__main__":
    exports_dir = Path(r"D:\work\CanvasMind\canvas_files\projects")
    server = GlobalMcpServer(exports_dir)
    server.run_stdio()