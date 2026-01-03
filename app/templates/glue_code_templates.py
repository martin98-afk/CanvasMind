DEFAULT_CODE_TEMPLATE = '''def run(self, params, inputs=None):
    """
    params: 节点属性（来自UI）
    inputs: 上游输入（key=输入端口名）
    return: 输出数据（key=输出端口名）
    """
    # 在这里编写你的组件逻辑
    input_data = inputs.get("input_data") if inputs else None
    param1 = params.get("param1", "default_value")
    # 处理逻辑
    result = f"处理结果: {input_data} + {param1}"
    return {
        "output": result
    }
'''

# ===== 胶水代码模板库 =====
GLUE_CODE_TEMPLATES = {
    "default": {
        "name": "空白模板",
        "code": DEFAULT_CODE_TEMPLATE.strip()
    },
    "variable_clear": {
        "name": "节点变量清理",
        "code": '''def run(self, params, inputs=None):
    """
    params: {mode: "parse" 或 "serialize"}
    inputs: {"input_data": str 或 dict}
    """
    self.emit_custom_message(
        method="global_variable.clear",
        params={
                "type": "node_vars",
                "value": "变量名"
            }
    )
'''
    },
    "node_variable_add": {
        "name": "节点端口变量加入全局变量",
        "code": '''def run(self, params, inputs=None):
    """
    params: {mode: "parse" 或 "serialize"}
    inputs: {"input_data": str 或 dict}
    """
    self.emit_custom_message(
        method="global_variable.add",
        params={"value": "output1"}
    )
    return {"output1": "test"}
'''
    },
    "node_variable_remove": {
        "name": "节点端口变量移除全局变量",
        "code": '''def run(self, params, inputs=None):
    """
    params: {mode: "parse" 或 "serialize"}
    inputs: {"input_data": str 或 dict}
    """
    self.emit_custom_message(
        method="global_variable.delete",
        params={"value": "output1"}
    )
    return {"output1": "test"}
'''
    },
    "stream_output": {
        "name": "实时结果使用示例",
        "code": '''def run(self, params, inputs=None):
    """
    params: 节点属性（来自UI）
    inputs: 上游输入（key=输入端口名）
    return: 输出数据（key=输出端口名）
    """
    import time
    count = 0 
    while True:
        self.emit_custom_message(
            method="stream.output",
            params={"output1": {"data": count, "data_type": "str"}}
        )
        count += 1
        time.sleep(1)
    return {
        "output1": result
    }
'''
    },
    "json_parse": {
        "name": "JSON 解析/序列化",
        "code": '''def run(self, params, inputs=None):
    """
    params: {mode: "parse" 或 "serialize"}
    inputs: {"input_data": str 或 dict}
    """
    import json
    input_data = inputs.get("input_data") if inputs else None
    mode = params.get("mode", "parse")

    if mode == "parse":
        try:
            output_data = json.loads(input_data) if isinstance(input_data, str) else input_data
        except Exception as e:
            output_data = {"error": str(e)}
    elif mode == "serialize":
        try:
            output_data = json.dumps(input_data, ensure_ascii=False, indent=2)
        except Exception as e:
            output_data = str(e)
    else:
        output_data = input_data

    return {
        "output_data": output_data
    }'''
    },
    "filter_list": {
        "name": "按字段过滤列表",
        "code": '''def run(self, params, inputs=None):
    """
    params: {field: "score", threshold: 80}
    inputs: {"input_data": list of dict}
    """
    input_data = inputs.get("input_data") or []
    field = params.get("field", "score")
    threshold = float(params.get("threshold", 0))

    if not isinstance(input_data, list):
        output_data = []
    else:
        output_data = [
            item for item in input_data
            if isinstance(item, dict) and item.get(field, float('-inf')) >= threshold
        ]

    return {
        "output_data": output_data
    }'''
    },
    "rename_fields": {
        "name": "字段重命名",
        "code": '''def run(self, params, inputs=None):
    """
    params: {mapping: {"old": "new"}}
    inputs: {"input_data": dict or list of dict}
    """
    input_data = inputs.get("input_data") or []
    mapping = params.get("mapping", {})

    if isinstance(input_data, list):
        output_data = [
            {mapping.get(k, k): v for k, v in item.items()}
            for item in input_data if isinstance(item, dict)
        ]
    elif isinstance(input_data, dict):
        output_data = {mapping.get(k, k): v for k, v in input_data.items()}
    else:
        output_data = input_data

    return {
        "output_data": output_data
    }'''
    },
    "listdir": {
        "name": "列出指定目录全部文件",
        "code": '''def run(self, params, inputs=None):
    """
    params: 节点属性（来自UI）
    inputs: 目标文件夹
    return: 文件地址里列表（key=输出端口名）
    """
    from pathlib import Path
    path = Path(inputs.input)
    projects = [str(p) for p in path.iterdir()]
    return {
        "output": projects
    }'''
    }
}