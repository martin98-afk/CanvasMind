# === 执行脚本模板（模块级常量，避免重复拼接）===
_EXECUTION_SCRIPT_TEMPLATE = '''# -*- coding: utf-8 -*-
import sys
import os
import pickle
import importlib.util
import traceback
from loguru import logger

class FileLogHandler:
    def __init__(self, log_file_path, node_id):
        self.log_file_path = log_file_path
        self.node_id = node_id
        self.handler_id = logger.add(
            self._file_sink,
            level="INFO",
            enqueue=True,
            filter=lambda r: r["extra"].get("node_id") == self.node_id
        )

    def _file_sink(self, message):
        record = message.record
        timestamp = record["time"].strftime("%Y-%m-%d %H:%M:%S")
        msg = f"[{{timestamp}}] {{record['function']}}-{{record['line']}} {{record['level'].name}}: {{record['message']}}\\n"
        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(msg)

    def __getattr__(self, name):
        return getattr(logger.bind(node_id=self.node_id), name)

try:
    spec = importlib.util.spec_from_file_location("{class_name}", r"{file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    comp_class = getattr(module, "{class_name}")

    with open(r"{params_path}", 'rb') as f:
        params, inputs = pickle.load(f)

    comp_instance = comp_class()
    comp_instance.logger = FileLogHandler(r"{log_file_path}", "{node_id}")

    if inputs:
        output = comp_instance.execute(params, inputs)
    else:
        output = comp_instance.execute(params)

    comp_instance.logger.success("节点执行完成")
    with open(r"{result_path}", 'wb') as f:
        pickle.dump(output, f)
    sys.exit(0)

except ImportError as e:
    error_info = {{"error": str(e), "traceback": traceback.format_exc(), "type": "ImportError"}}
    with open(r"{error_path}", 'wb') as f:
        pickle.dump(error_info, f)
    print(f"EXECUTION_IMPORT_ERROR: {{e}}", flush=True)
    sys.exit(1)

except Exception as e:
    error_info = {{"error": str(e), "traceback": traceback.format_exc(), "type": "Other"}}
    with open(r"{error_path}", 'wb') as f:
        pickle.dump(error_info, f)
    print(f"EXECUTION_ERROR: {{e}}", flush=True)
    sys.exit(1)
'''
