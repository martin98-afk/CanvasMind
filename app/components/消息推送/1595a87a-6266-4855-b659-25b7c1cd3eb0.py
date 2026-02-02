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
    description = "向飞书多维表格写入数据，支持JSON Key提取、自动创建列和上传图片"
    requirements = "requests,numpy,pillow,feishu_client"

    inputs = [
        PortDefinition(name="trigger", label="触发数据 (JSON/Object)", type=ArgumentType.JSON),
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
                    label="列类型",
                    choices=["文本", "数字", "单选", "多选", "日期", "复选框", "人员", "电话", "链接", "附件"]
                ),
                "source_type": PropertyDefinition(
                    type=PropertyType.CHOICE,
                    default="JSON Key",
                    label="值来源",
                    description="JSON Key: 从输入字典提取; 自动: 智能提取图片或文本; 固定值: 使用下方内容",
                    choices=["JSON Key", "触发数据(自动)", "固定值"]
                ),
                "fixed_value": PropertyDefinition(
                    type=PropertyType.TEXT,
                    default="",
                    label="固定值内容",
                    description="仅在选择'固定值'时生效",
                ),
            }
        ),
    }

    # --- Helpers ---
    def _tensor_to_bytes(self, tensor):
        import io
        import numpy as np
        from PIL import Image
        
        # 1. 已经是 bytes
        if isinstance(tensor, (bytes, bytearray)): return tensor
        
        # 2. PIL Image
        if isinstance(tensor, Image.Image):
            buf = io.BytesIO()
            tensor.save(buf, format="PNG")
            return buf.getvalue()
        
        array = None
        # 3. Torch Tensor / Numpy
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
        """从 trigger 中智能提取(用于自动模式)"""
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

    def _get_value_by_key(self, data, key):
        """支持点号索引的字典取值，例如 data.info.name"""
        if not key: return None
        if not isinstance(data, dict): return None
        
        # 简单的一层取值
        if key in data:
            return data[key]
            
        # 尝试支持 data.key.subkey
        keys = key.split('.')
        current = data
        try:
            for k in keys:
                if isinstance(current, dict):
                    current = current.get(k)
                else:
                    return None
            return current
        except:
            return None

    def run(self, params, inputs=None):
        try:
            from .feishu_client import FeishuBitableClient, TYPE_ALIASES
        except ImportError:
            from feishu_client import FeishuBitableClient, TYPE_ALIASES

        # 1. 获取全局配置
        app_conf = getattr(self.global_variable, "CM_FEISHU_CONF", None)
        if not app_conf:
            return {"log": "Error: Missing Feishu App Config (Add Config Node first)"}
        
        client = FeishuBitableClient(app_conf["app_id"], app_conf["app_secret"])
        
        # 2. 解析参数
        raw_app_token = params.get("app_token", "").strip()
        table_id = params.get("table_id", "").strip()
        view_id = params.get("view_id", "").strip()
        
        if not (raw_app_token and table_id):
            return {"log": "Error: Missing App Token or Table ID"}

        app_token = client.resolve_app_token(raw_app_token, table_id)
        
        # 触发数据
        trigger = inputs.get("trigger")
        
        # 预处理自动模式的数据（懒加载：只在用到自动模式时才算）
        trig_imgs_cache = None
        trig_text_cache = None
        
        # 3. 构建写入数据
        record_fields = {}
        fields_def_list = [] 
        mappings = [m for m in params.fields_mapping if m.name] if params.fields_mapping else []
        logs = []

        for m in mappings:
            fname = m.name
            ftype = m.type
            source = m.source_type
            
            # 记录定义
            fields_def_list.append({"name": fname, "type": ftype})
            
            norm_type = TYPE_ALIASES.get(ftype, "text")
            val_to_write = None

            # === 核心逻辑：根据来源获取数据 ===
            if source == "固定值":
                val_to_write = m.fixed_value
                
            elif source == "JSON Key":
                # 从 JSON 中提取
                key_name = m.key
                raw_val = self._get_value_by_key(trigger, key_name)
                
                if raw_val is not None:
                    # 判断提取出来的是图片还是文本
                    if norm_type == "attachment":
                        # 尝试转图片
                        img_bytes = self._tensor_to_bytes(raw_val)
                        if img_bytes:
                            val_to_write = [img_bytes] # 附件需要列表
                        elif isinstance(raw_val, list):
                             # 可能是图片列表
                             val_to_write = []
                             for item in raw_val:
                                 b = self._tensor_to_bytes(item)
                                 if b: val_to_write.append(b)
                        else:
                             # 无法转图片，可能是图片URL字符串
                             val_to_write = raw_val 
                    else:
                        # 普通文本/数字
                        val_to_write = raw_val

            elif source == "触发数据(自动)":
                # 使用旧逻辑：全量提取
                if trig_imgs_cache is None:
                    trig_imgs_cache, trig_text_cache = self._extract_trigger_data(trigger)
                
                if norm_type == "attachment":
                    val_to_write = trig_imgs_cache if trig_imgs_cache else None
                else:
                    val_to_write = trig_text_cache

            # === 数据写入准备 ===
            if val_to_write is not None:
                if norm_type == "attachment":
                    # 处理附件上传
                    final_tokens = []
                    
                    # 统一转为列表处理
                    items_to_upload = val_to_write if isinstance(val_to_write, list) else [val_to_write]
                    
                    for item in items_to_upload:
                        if isinstance(item, (bytes, bytearray)):
                            # 是二进制流，上传
                            ft = client.upload_attachment(app_token, item)
                            if ft: final_tokens.append({"file_token": ft})
                        elif isinstance(item, str) and item.startswith("http"):
                             # 是URL，目前飞书API写入附件不支持直接传URL，这里作为文本处理或跳过
                             # 或者如果列类型兼容，可以作为文本写入。但在 attachment 类型下需要 file_token
                             # 这里简单略过 URL
                             pass 
                             
                    if final_tokens:
                        record_fields[fname] = final_tokens
                        logs.append(f"Field[{fname}]: {len(final_tokens)} attachments")
                else:
                    # 普通类型
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

        return {"log": "\n\n".join(logs)}