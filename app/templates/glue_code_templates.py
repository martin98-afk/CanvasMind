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
        "output1": result
    }
'''

# ===== 胶水代码模板库 =====
GLUE_CODE_TEMPLATES = {
    "空白模板": DEFAULT_CODE_TEMPLATE.strip(),
    "人工干预": '''def run(self, params, inputs):
    # 逻辑处理...
    result = self.emit_interactive_message(
        method="ask_user",
        params={
            "title":"数据核对", 
            "message":"请核对以下解析结果是否正确",
            "schema":{
                "is_correct": {"type": "bool", "label": "结果正确", "default": True},
                "adjust_value": {"type": "float", "label": "修正偏差值", "default": 0.0},
                "choices": {"type": "choice", "choices": ["选项1", "选项2", "选项3"], "default": "选项1"},
                "text": {"label": "生成文本确认", "default": "测试文本"}
            }
        }
    )
    return {
        "output1": result
    }
''',
    "节点变量清理": '''def run(self, params, inputs=None):
    """
    params: {mode: "parse" 或 "serialize"}
    inputs: {"input_data": str 或 dict}
    """
    self.emit_message(
        method="clear_global_variable",
        params={
                "type": "node_vars",
                "value": "变量名"
            }
    )
''',
    "节点端口变量加入全局变量": '''def run(self, params, inputs=None):
    """
    params: {mode: "parse" 或 "serialize"}
    inputs: {"input_data": str 或 dict}
    """
    self.emit_message(
        method="add_output_to_global_variable",
        params={"value": "output1"}
    )
    return {"output1": "test"}
''',
    "节点端口变量移除全局变量": '''def run(self, params, inputs=None):
    """
    params: {mode: "parse" 或 "serialize"}
    inputs: {"input_data": str 或 dict}
    """
    self.emit_message(
        method="delete_output_from_global_variable",
        params={"value": "output1"}
    )
    return {"output1": "test"}
''',
    "实时结果使用示例": '''def run(self, params, inputs=None):
    """
    params: 节点属性（来自UI）
    inputs: 上游输入（key=输入端口名）
    return: 输出数据（key=输出端口名）
    """
    import time
    count = 0 
    while True:
        self.emit_message(
            method="stream.output",
            params={"output1": {"data": count, "data_type": "list"}},
            extra={"display": True} # 控制是否在节点上展示实时控件
        )
        count += 1
        time.sleep(1)
    return {
        "output1": result
    }
''',
    "JSON 解析/序列化": '''def run(self, params, inputs=None):
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
    }''',
    "按字段过滤列表": '''def run(self, params, inputs=None):
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
    }''',
    "字段重命名": '''def run(self, params, inputs=None):
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
    }''',
    "列出指定目录全部文件": '''def run(self, params, inputs=None):
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