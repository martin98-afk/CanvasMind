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


class MessagePusher(BaseComponent):
    name = "消息推送执行"
    category = "消息推送"
    description = "支持多目标推送：自动识别配置类型（钉钉/飞书）并推送消息，支持图片上传（需Gitee配置）"
    requirements = "numpy,pillow,requests"

    inputs = [
        PortDefinition(name="image", label="推送base64图像", type=ArgumentType.TEXT, connection=ConnectionType.MULTIPLE),
        PortDefinition(name="message", label="推送消息内容", type=ArgumentType.JSON, connection=ConnectionType.SINGLE),
    ]

    outputs = [
        PortDefinition(name="log", label="日志", type=ArgumentType.TEXT),
    ]

    properties = {
        "title": PropertyDefinition(
            type=PropertyType.TEXT,
            default="CanvasMind 通知",
            label="消息标题",
        ),
        "content": PropertyDefinition(
            type=PropertyType.MULTILINE,
            default="任务已完成",
            label="附加文本内容",
        ),
        "push_configs": PropertyDefinition(
            type=PropertyType.DYNAMICFORM,
            label="推送配置列表",
            schema={
                "config": PropertyDefinition(
                    type=PropertyType.VARIABLE,
                    default="全局变量",
                    label="选择配置变量",
                    description="选择由配置节点生成的全局变量 (如 CM_DINGTALK_CONF)",
                ),
            }
        ),
    }

    # === 辅助函数区域 ===
    def _has_value(self, v):
        if v is None: return False
        if isinstance(v, bool): return v
        if isinstance(v, str): return len(v.strip()) > 0
        try:
            if hasattr(v, "size"): return int(v.size) > 0
            if hasattr(v, "__len__"): return len(v) > 0
        except: pass
        return True

    def _tensor_to_bytes(self, tensor):
        """将任意图像格式转为PNG Bytes"""
        import io
        import numpy as np
        from PIL import Image
        if isinstance(tensor, Image.Image):
            buffered = io.BytesIO()
            tensor.save(buffered, format="PNG")
            return buffered.getvalue()

        array = None
        if isinstance(tensor, np.ndarray):
            if tensor.ndim == 4 and tensor.shape[0] == 1: array = tensor[0]
            elif tensor.ndim == 3: array = tensor
            
            if array is not None:
                if (array.dtype == np.float32 or array.dtype == np.float64) and array.max() <= 1.0:
                    array = array * 255.0
                array = np.clip(array, 0, 255).astype(np.uint8)
        
        elif hasattr(tensor, "detach"): # Torch tensor
             return self._tensor_to_bytes(tensor.detach().cpu().numpy())

        if array is None: return None
        image = Image.fromarray(array)
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        return buffered.getvalue()

    def _upload_gitee(self, image_base64, config):
        import base64
        import uuid
        import requests
        if not config: return None, "No Gitee Config"
        token, owner, repo = config.get("token"), config.get("owner"), config.get("repo")
        if not (token and owner and repo): return None, "Gitee info missing"

        try:
            filename = f"{uuid.uuid4().hex}.png"
            path = config.get("path", "images").strip("/")
            full_path = f"{path}/{filename}" if path else filename
            url = f"https://gitee.com/api/v5/repos/{owner}/{repo}/contents/{full_path}"
            
            data = {
                "access_token": token,
                "content": image_base64,
                "message": "CanvasMind Upload",
                "branch": config.get("branch", "master")
            }
            res = requests.post(url, data=data, timeout=30)
            if res.status_code == 201:
                return res.json().get("content", {}).get("download_url"), None
            return None, f"Status {res.status_code}"
        except Exception as e:
            return None, str(e)

    def _send_dingtalk(self, config, title, content, img_urls):
        import json
        import urllib.request
        import urllib.parse
        import hashlib
        import base64
        import time
        import hmac
        
        webhook = config.get("dd_webhook")
        secret = config.get("secret")
        
        url = webhook
        if secret:
            ts = str(round(time.time() * 1000))
            string_to_sign = '{}\n{}'.format(ts, secret).encode('utf-8')
            hmac_code = hmac.new(secret.encode('utf-8'), string_to_sign, digestmod=hashlib.sha256).digest()
            sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
            url = f"{url}&timestamp={ts}&sign={sign}" if "?" in url else f"{url}?timestamp={ts}&sign={sign}"

        md = f"### {title}\n\n{content}"
        for u in img_urls:
            if u: md += f"\n\n![img]({u})"

        data = {"msgtype": "markdown", "markdown": {"title": title, "text": md}}
        try:
            req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=10) as f:
                res = json.loads(f.read().decode())
                return "OK" if res.get("errcode") == 0 else f"Fail: {res.get('errmsg')}"
        except Exception as e:
            return f"Error: {e}"

    def _send_feishu(self, config, title, content, img_urls):
        import json
        import urllib.request
        import urllib.parse
        import hashlib
        import base64
        import time
        import hmac
        
        webhook = config.get("fs_webhook")
        secret = config.get("secret")
        data = {}
        if img_urls:
            actions = [{"tag": "button", "text": {"tag": "plain_text", "content": f"查看图片 {i+1}"}, "url": u, "type": "primary"} for i, u in enumerate(img_urls) if u]
            data = {
                "msg_type": "interactive",
                "card": {
                    "header": {"title": {"tag": "plain_text", "content": title}, "template": "blue"},
                    "elements": [{"tag": "div", "text": {"tag": "plain_text", "content": content}}, {"tag": "action", "actions": actions}]
                }
            }
        else:
            data = {"msg_type": "text", "content": {"text": f"{title}\n{content}"}}

        if secret:
            ts = str(int(time.time()))
            string_to_sign = '{}\n{}'.format(ts, secret)
            sign = base64.b64encode(hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()).decode('utf-8')
            data["timestamp"], data["sign"] = ts, sign

        try:
            req = urllib.request.Request(webhook, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=10) as f:
                res = json.loads(f.read().decode())
                return "OK" if res.get("code") == 0 else f"Fail: {res.get('msg')}"
        except Exception as e:
            return f"Error: {e}"

    def run(self, params, inputs=None):
        import json
        trigger = inputs.get("image")
        message_content = inputs.get("message")
        title = params.get("title", "通知")
        if isinstance(message_content, dict) or isinstance(message_content, list):
            message_content = json.dumps(message_content, indent=2, ensure_ascii=False)
        content = params.get("content", "") + "\n\n" + message_content
        
        # 1. 检查触发源
        if not self._has_value(trigger):
            return {"log": "Skip (Empty Trigger)"}

        # 2. 解析配置列表
        # dynamic form 返回的是一个列表，每个对象包含我们定义的 schema 属性
        config_list = []
        if params.push_configs:
            # 过滤掉空的配置
            config_list = [item.config for item in params.push_configs if item.config]
        
        if not config_list:
            return {"log": "No push configurations provided in the list."}
        logs = []

        # 3. 识别配置类型
        gitee_conf = None
        push_targets = []

        for conf in config_list:
            conf = conf[1]
            if not isinstance(conf, dict):
                continue
            
            # 根据字典的 key 特征识别配置类型
            if "owner" in conf and "repo" in conf and "token" in conf:
                gitee_conf = conf # 找到 Gitee 配置
            elif "fs_webhook" in conf:
                push_targets.append({"type": "feishu", "config": conf})
            elif "dd_webhook" in conf:
                push_targets.append({"type": "dingtalk", "config": conf})
        # 4. 处理内容与图片 (转换为 Bytes)
        extra_text = []
        image_bytes_list = []
        img_urls = []

        for img in trigger:
            if gitee_conf:
                self.logger.info(f"Uploading images to Gitee...")
                url, err = self._upload_gitee(img, gitee_conf)
                if url: 
                    img_urls.append(url)
                else: 
                    logs.append(f"Gitee Upload Fail: {err}")
            else:
                logs.append("Skipped Upload (Images found but no Gitee Config)")

        # 6. 遍历所有推送目标进行推送
        if not push_targets:
            logs.append("No valid DingTalk or Feishu configs found.")
            
        for idx, target in enumerate(push_targets):
            t_type = target["type"]
            t_conf = target["config"]
            res = "Unknown"
            
            if t_type == "dingtalk":
                res = self._send_dingtalk(t_conf, title, content, img_urls)
                logs.append(f"DingTalk[{idx}]: {res}")
            elif t_type == "feishu":
                res = self._send_feishu(t_conf, title, content, img_urls)
                logs.append(f"Feishu[{idx}]: {res}")

        log_str = "\n".join(logs)
        self.logger.info(f"Push Result: {log_str}")
        return {"log": log_str}