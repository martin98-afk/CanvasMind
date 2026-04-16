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


class WeComPusher(BaseComponent):
    """企业微信消息推送执行组件"""
    name = "企业微信推送"
    category = "消息推送"
    description = "向企业微信群机器人推送消息，支持文本、Markdown、图片、文件等多种消息类型"
    requirements = "numpy,pillow,requests"

    inputs = [
        PortDefinition(
            name="images",
            label="图片数据",
            type=ArgumentType.ARRAY,
            connection=ConnectionType.MULTIPLE,
            description="要推送的图片，支持 base64/PIL Image/numpy array/torch tensor",
        ),
        PortDefinition(
            name="content",
            label="消息内容",
            type=ArgumentType.JSON,
            description="JSON格式的消息内容",
        ),
    ]

    outputs = [
        PortDefinition(name="log", label="日志", type=ArgumentType.TEXT),
        PortDefinition(name="success", label="是否成功", type=ArgumentType.BOOL),
    ]

    properties = {
        "msg_type": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="text",
            label="消息类型",
            description="选择要发送的消息类型",
            choices=["text", "markdown", "markdown_v2", "image", "news", "file"]
        ),
        "title": PropertyDefinition(
            type=PropertyType.TEXT,
            default="CanvasMind 通知",
            label="消息标题",
            description="用于图文消息的标题",
        ),
        "content": PropertyDefinition(
            type=PropertyType.MULTILINE,
            default="任务已完成",
            label="消息内容",
            description="消息主体内容，支持 Markdown 语法（text/markdown类型时）",
        ),
        "url": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="跳转链接",
            description="图文消息的跳转链接",
        ),
        "picurl": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="图片URL",
            description="图文消息的封面图片URL",
        ),
        "config": PropertyDefinition(
            type=PropertyType.VARIABLE,
            default="全局变量",
            label="选择配置变量",
            description="选择由企业微信配置节点生成的全局变量",
        ),
    }

    def _bytes_to_base64_md5(self, data: bytes) -> tuple:
        """将字节数据转换为 base64 编码和 md5 哈希"""
        return base64.b64encode(data).decode("utf-8"), hashlib.md5(data).hexdigest()

    def _tensor_to_bytes(self, tensor) -> bytes:
        """将各种格式的图片数据转换为字节"""
        # 1. 已经是 bytes
        if isinstance(tensor, (bytes, bytearray)):
            return bytes(tensor)

        # 2. PIL Image
        if isinstance(tensor, Image.Image):
            buf = io.BytesIO()
            tensor.save(buf, format="PNG")
            return buf.getvalue()

        # 3. 尝试转换为 numpy
        try:
            if hasattr(tensor, "cpu") and hasattr(tensor, "numpy"):
                tensor = tensor.detach().cpu().numpy()
        except Exception:
            pass

        if isinstance(tensor, np.ndarray):
            array = None
            # Handle batch
            if tensor.ndim == 4 and tensor.shape[0] == 1:
                array = tensor[0]
            elif tensor.ndim == 3:
                array = tensor

            if array is not None:
                if array.dtype in (np.float32, np.float64) and array.max() <= 1.0:
                    array = array * 255.0
                array = np.clip(array, 0, 255).astype(np.uint8)
                return self._tensor_to_bytes(Image.fromarray(array))

        return None

    def _upload_media(self, webhook: str, file_bytes: bytes, file_type: str = "file") -> str:
        """上传文件到企业微信，获取 media_id"""
        import requests

        # 从 webhook URL 中提取 key
        key = None
        if "key=" in webhook:
            key = webhook.split("key=")[1].split("&")[0]

        if not key:
            raise ValueError("无法从 webhook URL 中提取 key")

        upload_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/upload_media?key={key}&type={file_type}"

        files = {"media": (f"file_{uuid.uuid4().hex}", file_bytes)}
        try:
            resp = requests.post(upload_url, files=files, timeout=30)
            result = resp.json()
            if result.get("media_id"):
                return result["media_id"]
            raise Exception(f"Upload failed: {result}")
        except Exception as e:
            raise Exception(f"Media upload error: {e}")

    def _send_request(self, webhook: str, payload: dict) -> dict:
        """发送请求到企业微信"""
        import urllib.request

        try:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                webhook,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return {"errcode": -1, "errmsg": str(e)}

    def run(self, params, inputs=None):
        # 1. 获取配置
        config_var = params.get("config", "CM_WECOM_CONF")
        conf = getattr(self.global_variable, config_var, None)

        if not conf:
            return {"log": f"Error: Missing WeCom Config ({config_var})", "success": False}

        webhook = conf.get("webhook")
        if not webhook:
            return {"log": "Error: No webhook in config", "success": False}

        # 2. 构建消息
        msg_type = params.get("msg_type", "text")
        content = params.get("content", "")
        title = params.get("title", "CanvasMind 通知")
        url = params.get("url", "")
        picurl = params.get("picurl", "")

        # 如果有输入内容，覆盖默认内容
        input_content = inputs.get("content")
        if input_content is not None:
            if isinstance(input_content, dict):
                content = input_content.get("content", content)
                if input_content.get("title"):
                    title = input_content["title"]
                if input_content.get("url"):
                    url = input_content["url"]
                if input_content.get("picurl"):
                    picurl = input_content["picurl"]
            elif isinstance(input_content, str):
                content = input_content

        # 3. 构建消息体
        payload = {"msgtype": msg_type}

        if msg_type == "text":
            # 文本消息
            payload["text"] = {
                "content": content,
            }

        elif msg_type == "markdown":
            # Markdown 消息
            payload["markdown"] = {
                "content": content,
            }

        elif msg_type == "markdown_v2":
            # Markdown V2 消息（更丰富的格式）
            payload["markdown_v2"] = {
                "content": content,
            }

        elif msg_type == "image":
            # 图片消息
            images = inputs.get("images", [])
            if images:
                img_bytes = self._tensor_to_bytes(images[0])
                if img_bytes:
                    base64_data, md5_hash = self._bytes_to_base64_md5(img_bytes)
                    payload["image"] = {
                        "base64": base64_data,
                        "md5": md5_hash,
                    }
                else:
                    return {"log": "Error: Failed to convert image", "success": False}
            else:
                return {"log": "Error: No image provided", "success": False}

        elif msg_type == "news":
            # 图文消息
            articles = [{
                "title": title,
                "description": content,
                "url": url,
                "picurl": picurl,
            }]
            payload["news"] = {"articles": articles}

        elif msg_type == "file":
            # 文件消息
            images = inputs.get("images", [])
            if images:
                img_bytes = self._tensor_to_bytes(images[0])
                if img_bytes:
                    try:
                        media_id = self._upload_media(webhook, img_bytes, "file")
                        payload["file"] = {"media_id": media_id}
                    except Exception as e:
                        return {"log": f"Error: File upload failed - {e}", "success": False}
                else:
                    return {"log": "Error: Failed to process file", "success": False}
            else:
                return {"log": "Error: No file provided", "success": False}

        # 4. 发送消息
        logs = []
        result = self._send_request(webhook, payload)

        if result.get("errcode") == 0:
            logs.append(f"WeCom Push OK ({msg_type})")
            logs.append(f"Content: {content[:100]}...")
            return {"log": "\n".join(logs), "success": True}
        else:
            logs.append(f"Push Failed: {result.get('errmsg', 'Unknown error')}")
            return {"log": "\n".join(logs), "success": False}