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


class LongTextQA(BaseComponent):
    name = "长文档内容问答"
    category = "大模型组件"
    description = ""
    requirements = "httpx"
    inputs = [
        PortDefinition(name="file_text", label="长文本", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
        PortDefinition(name="instruction", label="用户指令", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output", label="回复", type=ArgumentType.TEXT),
    ]
    properties = {
        "token_per_chunk": PropertyDefinition(
            type=PropertyType.RANGE,
            default="8658.5",
            label="切片长度",
            min=5000.0,
            max=15000.0,
            step=1000.0,
        ),
        "model_configs": PropertyDefinition(
            type=PropertyType.VARIABLE,
            default="全局变量",
            label="大模型配置",
        ),
    }
    def run(self, params, inputs=None):
        """
        根据长文本和用户指令，通过分片 + 大模型处理，返回完整回复。
    
        Args:
            file_text (str): 超长输入文本
            instruction (str): 用户自然语言指令
    
        Returns:
            dict: {"output": "完整回复字符串"}，可包含代码、摘要、结构化文本等
        """
        import re
        import json
        from typing import List, Dict, Any
        import httpx
        model_config = self.global_variable.get(params.model_configs)
        instruction = inputs.instruction
        file_text = inputs.file_text
        # ==================== 内部工具函数 ====================
    
        def call_llm(prompt: str) -> str:
            """
            调用大模型的接口。请在此处替换为你实际的大模型调用逻辑。
            """
            with httpx.Client(base_url=model_config.get("API_URL"), timeout=300) as client:
                resp = client.post(
                    url="/chat/completions",
                    json={
                        "model": model_config.get("模型名称"),
                        "messages": [{"role": "user", "content": prompt}],
                    }
                )
                resp.raise_for_status()
                data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return content
    
        def estimate_tokens(text: str) -> int:
            # 粗略估算：中文 1 字 ≈ 2 tokens，英文 1 字 ≈ 1.3 tokens，保守取 len//2
            return len(text) // 2
    
        def text_wrap_marker(text: str) -> str:
            return f"--- BEGIN INPUT ---\n{text}\n--- END INPUT ---"
    
        def _split_long_paragraph(para: str, max_tokens: int) -> List[str]:
            if estimate_tokens(para) <= max_tokens:
                return [para]
            sentences = re.split(r'([。！？.\n])', para)
            chunks = []
            current = ""
            for sent in sentences:
                if not sent.strip():
                    continue
                test = current + sent
                if estimate_tokens(test) <= max_tokens:
                    current = test
                else:
                    if current:
                        chunks.append(current)
                    current = sent
            if current:
                chunks.append(current)
            return chunks
    
        def smart_split_text(text: str, max_tokens: int, overlap_ratio: float = 0.05) -> List[str]:
            paragraphs = re.split(r'(\n\s*\n)', text)
            chunks = []
            current_chunk = ""
            overlap_chars = int(max_tokens * overlap_ratio * 2)  # 保守估计字符数
    
            for para in paragraphs:
                if not para.strip():
                    continue
                test_chunk = current_chunk + para
                if estimate_tokens(test_chunk) <= max_tokens:
                    current_chunk = test_chunk
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                        overlap_start = max(0, len(current_chunk) - overlap_chars)
                        current_chunk = current_chunk[overlap_start:] + para
                    else:
                        parts = _split_long_paragraph(para, max_tokens)
                        chunks.extend(parts[:-1])
                        current_chunk = parts[-1] if parts else ""
    
            if current_chunk:
                chunks.append(current_chunk)
    
            # 简单去重（避免重叠区重复）
            deduped = []
            for c in chunks:
                if not deduped or c.strip() != deduped[-1].strip():
                    deduped.append(c)
            return deduped
    
        def aggregate_intermediate_results(results: List[Dict]) -> Dict[str, Any]:
            aggregated = {}
            for res in results:
                if not isinstance(res, dict):
                    continue
                for key, value in res.items():
                    if isinstance(value, list):
                        aggregated.setdefault(key, []).extend(value)
                    elif isinstance(value, dict):
                        if key not in aggregated:
                            aggregated[key] = {}
                        aggregated[key].update(value)
                    else:
                        if key not in aggregated:
                            aggregated[key] = value
    
            # 去重 list
            for key, val in aggregated.items():
                if isinstance(val, list):
                    try:
                        aggregated[key] = list(dict.fromkeys(val))
                    except TypeError:
                        seen = set()
                        unique = []
                        for item in val:
                            rep = str(item)
                            if rep not in seen:
                                seen.add(rep)
                                unique.append(item)
                        aggregated[key] = unique
            return aggregated
    
        # ==================== 主逻辑 ====================
    
        MAX_TOKENS_PER_CHUNK = 10000  # 根据你的模型调整
        total_tokens = estimate_tokens(file_text)
    
        if total_tokens <= MAX_TOKENS_PER_CHUNK:
            # 无需分片
            prompt = f"""用户指令：{instruction}
    
    完整输入文本：
    {text_wrap_marker(file_text)}
    
    请直接生成完整、可用的回复（如代码、摘要等），不要解释过程，不要包含前缀。"""
            final_output = call_llm(prompt)
            return {"output": final_output.strip()}
    
        # 需要分片
        chunks = smart_split_text(file_text, MAX_TOKENS_PER_CHUNK)
        intermediate_results = []
        total = len(chunks)
    
        for i, chunk in enumerate(chunks, 1):
            prompt = f"""你正在处理一个长文本的第 {i}/{total} 片。
    用户原始指令：{instruction}
    
    当前文本片段：
    {text_wrap_marker(chunk)}
    
    请仅基于此片段，提取与指令相关的结构化中间结果。
    - 输出必须是纯 JSON 格式，无任何额外文本。
    - 若无相关信息，返回 {{}}。
    
    示例（根据指令变化）：
    {{"errors": [...], "variables": [...]}}
    """
            try:
                resp = call_llm(prompt)
                result = json.loads(resp.strip())
                intermediate_results.append(result)
            except Exception:
                intermediate_results.append({})
    
        aggregated = aggregate_intermediate_results(intermediate_results)
    
        final_prompt = f"""用户指令：{instruction}
    
    已聚合的结构化信息：
    {text_wrap_marker(json.dumps(aggregated, ensure_ascii=False, indent=2))}
    
    请基于以上信息，生成完整、可用的最终回复。
    - 若需生成代码，使用 PyQt5 和 qfluentwidgets，支持深色主题。
    - 确保代码可直接运行，包含必要 import。
    - 不要包含任何解释性文字（如“以下是代码”）。
    - 若指令不要求代码，则返回自然语言或结构化文本。
    """
        final_output = call_llm(final_prompt)
        return {"output": final_output.strip()}


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = LongTextQA()
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
