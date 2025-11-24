# -*- coding: utf-8 -*-
import importlib.util
import pathlib
base_path = pathlib.Path(__file__).parent.parent / "base.py"
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


class Component(BaseComponent):
    name = "测试大模型效果"
    category = "测试组件"
    description = ""
    requirements = "openai"
    inputs = [
        PortDefinition(name="input1", label="输入内容", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output1", label="输出结果", type=ArgumentType.TEXT),
    ]
    properties = {
        "model": PropertyDefinition(
            type=PropertyType.VARIABLE,
            default="",
            label="大模型配置",
        )
    }
    
    def run(self, params, inputs=None):
        """
        组件执行主函数
        
        Args:
            params: 组件属性参数 (来自UI配置)
            inputs: 上游组件输入数据 (key=输入端口名, value=输入值)
    
        Returns:
            dict: 输出数据 (key=输出端口名, value=输出值)
    
        Raises:
            Exception: 组件执行失败时抛出异常
        """
        from openai import OpenAI
        
        try:
            # --- 1. 输入参数校验 ---
            if not inputs or "input1" not in inputs or not inputs["input1"]:
                raise ValueError("输入参数 'input1' 不能为空")
    
            # --- 2. 获取并校验大模型配置 ---
            model_config_key = params.model
            if not model_config_key:
                raise ValueError("未指定大模型配置项")
    
            model_config = self.global_variable.get(model_config_key)
            self.logger.info(f"当前大模型配置：{model_config}")
            if not model_config:
                raise ValueError(f"大模型配置 '{model_config_key}' 不存在于全局变量中")
    
            required_fields = ["模型名称", "API_URL"]
            for field in required_fields:
                if not model_config.get(field):
                    raise ValueError(f"大模型配置中缺少必要字段: '{field}'")
    
            # --- 3. 配置参数提取与默认值填充 ---
            model_name = model_config.get("模型名称", "").strip()
            api_url = model_config.get("API_URL", "").strip()
            api_key = model_config.get("API_KEY", "").strip()
            temperature = float(model_config.get("温度", 0.7))
            max_tokens = int(model_config.get("最大Token", 2048))
            system_prompt = model_config.get("系统提示", "").strip()
    
            if not model_name:
                raise ValueError("模型名称不能为空")
            if not api_url:
                raise ValueError("API URL 不能为空")
            if not api_key:
                self.logger.warning("API_KEY 为空，部分服务可能拒绝请求（如OpenAI）")
    
            user_input = inputs.input1.strip()
    
            # --- 4. 初始化客户端（兼容本地/线上模型）---
            client = OpenAI(
                api_key=api_key,
                base_url=api_url
            )
    
            # 构造消息列表
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": user_input})
    
            # --- 5. 调用大模型 ---
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=300  # 设置超时，避免阻塞
            )
    
            # --- 6. 解析并校验输出 ---
            completion = response.choices[0].message.content.strip()
    
            # --- 7. 返回结果 ---
            return {
                "output1": completion
            }
    
        except Exception as e:
            # 记录完整错误上下文，便于调试
            import traceback
            self.logger.error(f"【大模型分类器】执行失败 | 配置: {params.model} | 输入: {inputs.input1} | 错误: {str(e)}\n{traceback.format_exc()}")
            raise Exception(f"组件执行失败: {str(e)}")


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={"prop1": "test"},
        inputs={"input1": "output"},
        node_id="测试模型",
        show_input_types = True,
        show_output_types = True,
        show_execution_time = True,
        global_vars = {}
    )
    print(result)
