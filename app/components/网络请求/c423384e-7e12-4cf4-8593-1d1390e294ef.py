# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
base_path = Path(__file__).parent.parent / "base.py"
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


class HttpComponent(BaseComponent):
    name = "HTTP 请求客户端"
    category = "网络请求"
    description = "发送 HTTP 请求，支持动态配置请求体、请求头、查询参数，可自定义方法、认证、超时等"
    requirements = "httpx>=0.23.0"
    inputs = [
        PortDefinition(name="request_body", label="请求体", type=ArgumentType.JSON, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="response", label="响应结果", type=ArgumentType.JSON),
        PortDefinition(name="status_code", label="状态码", type=ArgumentType.INT),
        PortDefinition(name="headers", label="响应头", type=ArgumentType.JSON),
    ]

    properties = {
        "url": PropertyDefinition(
            type=PropertyType.TEXT,
            default="https://httpbin.org/get",
            label="请求地址",
        ),
        "method": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="GET",
            label="请求方法",
            choices=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"]
        ),
        "timeout": PropertyDefinition(
            type=PropertyType.INT,
            default=10,
            label="超时时间（秒）",
        ),
        "verify_ssl": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="验证 SSL 证书",
        ),
        "auth_type": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="None",
            label="认证方式",
            choices=["None", "Basic", "Bearer"]
        ),
        "auth_value": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="认证值（如用户名:密码 或 Token）",
        ),
        "headers": PropertyDefinition(
            type=PropertyType.DYNAMICFORM,
            label="请求头",
            schema={
                "key": PropertyDefinition(
                    type=PropertyType.TEXT,
                    default="",
                    label="键",
                ),
                "value": PropertyDefinition(
                    type=PropertyType.TEXT,
                    default="",
                    label="值",
                ),
            }
        ),
        "params": PropertyDefinition(
            type=PropertyType.DYNAMICFORM,
            label="请求参数",
            schema={
                "key": PropertyDefinition(
                    type=PropertyType.TEXT,
                    default="",
                    label="键",
                ),
                "value": PropertyDefinition(
                    type=PropertyType.TEXT,
                    default="",
                    label="值",
                ),
            }
        ),
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import httpx
        import json

        # 从 params 中获取各配置项
        url = params.url
        method = params.method
        timeout = float(params.timeout)
        verify_ssl = params.verify_ssl
        auth_type = params.auth_type
        auth_value = params.auth_value

        # 获取动态表单数据（headers、params、request_body）
        headers = {header.key:header.value for header in params.headers}
        params_query = {param.key:param.value for param in params.params}
        json_body = inputs.request_body

        # 认证处理
        auth = None
        if auth_type == "Basic":
            if ":" not in auth_value:
                raise ValueError("Basic 认证需要格式为 '用户名:密码'")
            username, password = auth_value.split(":", 1)
            auth = httpx.BasicAuth(username, password)
        elif auth_type == "Bearer":
            headers["Authorization"] = f"Bearer {auth_value}"
        # 其他认证方式（None）不处理

        # 发起请求
        try:
            response = httpx.request(
                method=method,
                url=url,
                json=json_body,
                params=params_query,
                headers=headers,
                auth=auth,
                timeout=timeout,
                verify=verify_ssl
            )
            response.raise_for_status()
        except httpx.RequestError as e:
            self.logger.error(f"请求失败: {e}")
            raise
        except httpx.HTTPStatusError as e:
            self.logger.error(f"HTTP 错误: {e.response.status_code} - {e.response.text}")
            raise

        # 返回结果
        return {
            "response": response.text,
            "status_code": response.status_code,
            "headers": dict(response.headers)
        }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")

    model = HttpComponent()
    result = model.debug(
        params={
            "url": "https://httpbin.org/post",
            "method": "POST",
            "timeout": "10",
            "verify_ssl": "True",
            "auth_type": "None",
            "auth_value": "",
            "headers": [{"key": "Content-Type", "value": "application/json"}, {"key": "X-API-Key", "value": "abc123"}],
            "params": [{"key": "page", "value": "1"}, {"key": "limit", "value": "10"}],
        },
        inputs={"request_body": {"name": "Alice", "age": 25}},
        global_vars={},
        node_id="test_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)
