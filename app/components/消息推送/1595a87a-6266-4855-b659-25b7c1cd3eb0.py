# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
base_path = Path(__file__).parent.parent / "base.py" if (Path(__file__).parent.parent / "base.py").exists() else Path(__file__).parent.parent.parent / "base.py"
spec = importlib.util.spec_from_file_location("base", str(base_path))
base_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base_module)

# 导入所需项目
BaseComponent = base_module.BaseComponent
PortDefinition = base_module.PortDefinition
PropertyDefinition = base_module.PropertyDefinition
PropertyType = base_module.PropertyType
ArgumentType = base_module.ArgumentType
ConnectionType = base_module.ConnectionType


class FeishuBitablePush(BaseComponent):
    name = "飞书表格写入"
    category = "消息推送"
    description = "向飞书多维表格写入数据，支持自动创建列和上传图片"
    requirements = "requests,numpy,pillow,feishu_client"

    inputs = [
        PortDefinition(name="trigger", label="触发数据 (Any)", type=ArgumentType.TEXT),
    ]

    outputs = [
        PortDefinition(name="log", label="日志", type=ArgumentType.TEXT),
    ]

    properties = {
        "app_token": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="App Token",
            description="多维表格的 token (或 wiki 链接)",
        ),
        "table_id": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="Table ID",
            description="数据表的 ID",
        ),
        "view_id": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="View ID (可选)",
        ),
        "auto_create_fields": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="自动创建缺少的列",
        ),
        "fields_mapping": PropertyDefinition(
            type=PropertyType.DYNAMICFORM,
            label="字段映射",
            description="定义要写入的列名、类型以及值来源",
            schema={
                "name": PropertyDefinition(
                    type=PropertyType.TEXT,
                    default="",
                    label="列名称",
                ),
                "type": PropertyDefinition(
                    type=PropertyType.CHOICE,
                    default="文本",
                    label="类型",
                    choices=["文本", "数字", "单选", "多选", "日期", "复选框", "人员", "电话", "链接", "附件"]
                ),
                "source_type": PropertyDefinition(
                    type=PropertyType.CHOICE,
                    default="触发数据",
                    label="值来源",
                    choices=["触发数据", "固定值"]
                ),
                "fixed_value": PropertyDefinition(
                    type=PropertyType.TEXT,
                    default="",
                    label="固定值内容 (可选)",
                ),
            }
        ),
    }

    # --- Helpers ---
    def _tensor_to_bytes(self, tensor):
        import io
        import numpy as np
        from PIL import Image
        if isinstance(tensor, bytes): return tensor
        if isinstance(tensor, Image.Image):
            buf = io.BytesIO()
            tensor.save(buf, format="PNG")
            return buf.getvalue()
        
        array = None
        if hasattr(tensor, "cpu") and hasattr(tensor, "numpy"):
            tensor = tensor.detach().cpu().numpy()
        
        if isinstance(tensor, np.ndarray):
            # Handle batch
            if tensor.ndim == 4 and tensor.shape[0] == 1: array = tensor[0]
            elif tensor.ndim == 3: array = tensor
            
            if array is not None:
                if array.dtype in (np.float32, np.float64) and array.max() <= 1.0:
                    array = array * 255.0
                array = np.clip(array, 0, 255).astype(np.uint8)
        
        if array is None: return None
        return self._tensor_to_bytes(Image.fromarray(array))

    def _extract_trigger_data(self, trigger):
        """从 trigger 中提取图片列表和文本"""
        
        imgs = []
        texts = []
        
        def _proc(item):
            b = self._tensor_to_bytes(item)
            if b: imgs.append(b)
            else: texts.append(str(item))

        if isinstance(trigger, (list, tuple)):
            for x in trigger: _proc(x)
        else:
            _proc(trigger)
        
        return imgs, "\n".join(texts)

    def run(self, params, inputs=None):
        from feishu_client import FeishuBitableClient, TYPE_ALIASES
        # 1. 获取全局配置
        app_conf = getattr(self.global_variable, "CM_FEISHU_APP_CONF", None)
        if not app_conf:
            return {"log": "Error: Missing Feishu App Config (Add Config Node first)"}
        
        client = FeishuBitableClient(app_conf["app_id"], app_conf["app_secret"])
        
        # 2. 解析参数
        raw_app_token = params.get("app_token", "").strip()
        table_id = params.get("table_id", "").strip()
        view_id = params.get("view_id", "").strip()
        
        if not (raw_app_token and table_id):
            return {"log": "Error: Missing App Token or Table ID"}

        # 解析 Wiki Token
        app_token = client.resolve_app_token(raw_app_token, table_id)
        
        trigger = inputs.get("trigger")
        # 提取触发数据
        trig_imgs, trig_text = self._extract_trigger_data(trigger)
        
        # 3. 构建写入数据
        record_fields = {}
        fields_def_list = [] # 用于 ensure_fields
        
        # 获取用户定义的映射
        mappings = []
        if params.fields_mapping:
            mappings = [m for m in params.fields_mapping if m.name]
            
        logs = []

        for m in mappings:
            fname = m.name
            ftype = m.type
            source = m.source_type
            
            # 记录定义供自动创建使用
            fields_def_list.append({"name": fname, "type": ftype})
            
            norm_type = TYPE_ALIASES.get(ftype, "text")
            val_to_write = None

            # 获取原始值
            if source == "固定值":
                val_to_write = m.fixed_value
            else:
                # 触发数据
                if norm_type == "attachment":
                    if trig_imgs:
                        val_to_write = trig_imgs # 传递 bytes 列表
                    else:
                        val_to_write = None
                else:
                    val_to_write = trig_text

            # 处理特定类型的写入逻辑
            if val_to_write is not None:
                if norm_type == "attachment":
                    # 上传附件
                    if isinstance(val_to_write, list):
                        tokens = []
                        for ib in val_to_write:
                            ft = client.upload_attachment(app_token, ib)
                            if ft: tokens.append({"file_token": ft})
                        if tokens:
                            record_fields[fname] = tokens
                            logs.append(f"Field[{fname}]: {len(tokens)} images uploaded")
                else:
                    # 普通类型转换
                    clean_val = client.coerce_value(ftype, val_to_write)
                    if clean_val is not None:
                        record_fields[fname] = clean_val

        # 4. 自动创建列
        if params.get("auto_create_fields", True) and fields_def_list:
            create_res = client.ensure_fields(app_token, table_id, fields_def_list)
            logs.extend(create_res)

        # 5. 写入记录
        if record_fields:
            status, res_json = client.create_record(app_token, table_id, record_fields, view_id)
            if status in (200, 201) and res_json.get("code") == 0:
                logs.append("Record Created OK")
            else:
                logs.append(f"Create Fail: {res_json}")
        else:
            logs.append("No valid fields to write")

        return {"log": " | ".join(logs)}