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


class LongTextQA(BaseComponent):
    name = "长文档内容问答"
    category = "大模型组件"
    description = "根据长文本和用户指令，通过分片处理与大模型结合，实现对超长文档内容的精准问答；输入为长文本和自然语言指令，输出为结构化或摘要式回复，支持通过参数配置切片长度和大模型配置。"
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
        MAX_SUMMARY_ITEMS = 8
        import re
        import json
        from typing import List, Dict, Any
        import httpx
        model_config = params.model_configs[1]
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
            return len(text) // 2  # 保守估计，实际可用 tiktoken 替换

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
            overlap_chars = int(max_tokens * overlap_ratio * 2)
    
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
    
            deduped = []
            for c in chunks:
                if not deduped or c.strip() != deduped[-1].strip():
                    deduped.append(c)
            return deduped
    
        def _summarize_batch(results: List[Dict], instr: str) -> Dict:
            """
            将一批中间结果合并为一个结构化摘要。
            输入：List[Dict]，输出：Dict（保持相同 schema）
            """
            # 构建 prompt
            batch_json = json.dumps(results, ensure_ascii=False, indent=2)
            prompt = f"""你正在合并一组与用户指令相关的中间分析结果。
    用户原始指令：{instr}
    
    中间结果列表（每个元素来自一个文本片段）：
    {text_wrap_marker(batch_json)}
    
    请将这些结果**结构化合并**为一个统一的 JSON 对象。
    - 保留所有关键信息；
    - 合并同类项（如 list 合并、去重）；
    - 若为空，返回 {{}}；
    - **只输出 JSON，不要任何额外文本**。
    """
            try:
                resp = call_llm(prompt)
                return json.loads(resp.strip())
            except Exception:
                return {}
    
        def recursive_summarize(results: List[Dict], instr: str, max_items: int = MAX_SUMMARY_ITEMS) -> Dict:
            """
            递归聚合中间结果，避免一次性输入过大。
            """
            if len(results) <= max_items:
                return _summarize_batch(results, instr)
    
            # 分组聚合
            grouped = []
            for i in range(0, len(results), max_items):
                batch = results[i:i + max_items]
                summary = _summarize_batch(batch, instr)
                grouped.append(summary)
    
            # 递归处理上一层
            return recursive_summarize(grouped, instr, max_items)
    
        # ============= 主逻辑 =============
    
        # 解析 instruction（支持 JSON 格式传 api_key）
        try:
            instr_obj = json.loads(instruction)
            user_instruction = instr_obj.get("instruction", instruction)
        except:
            user_instruction = instruction
    
        total_tokens = estimate_tokens(file_text)
        if total_tokens <= params.token_per_chunk:
            prompt = f"""用户指令：{user_instruction}
    
    完整输入文本：
    {text_wrap_marker(file_text)}
    
    请直接生成完整、可用的回复（如解答、摘要等），不要解释过程，不要包含前缀。"""
            final_output = call_llm(prompt)
            return {"output": final_output.strip()}
    
        # 分片处理
        chunks = smart_split_text(file_text, params.token_per_chunk)
        intermediate_results = []
    
        for i, chunk in enumerate(chunks, 1):
            prompt = f"""你正在处理一个长文本的第 {i}/{len(chunks)} 片。
    用户原始指令：{user_instruction}
    
    当前文本片段：
    {text_wrap_marker(chunk)}
    
    请仅基于此片段，提取与指令相关的结构化中间结果。
    - 输出必须是纯 JSON 格式，无任何额外文本。
    - 若无相关信息，返回 {{}}。
    
    示例（根据指令变化）：
    {{"answers": [...], "contacts": [...], "summary": "..."}}"""
            try:
                resp = call_llm(prompt)
                result = json.loads(resp.strip())
                intermediate_results.append(result)
            except Exception:
                intermediate_results.append({})
    
        # 递归聚合（关键改进！）
        if not intermediate_results:
            return {"output": "未能从文档中提取相关信息。"}
    
        aggregated = recursive_summarize(intermediate_results, user_instruction, MAX_SUMMARY_ITEMS)
    
        # 最终生成
        final_prompt = f"""用户指令：{user_instruction}
    
    已聚合的结构化信息：
    {text_wrap_marker(json.dumps(aggregated, ensure_ascii=False, indent=2))}
    
    请基于以上信息，生成完整、可用的最终回复。
    """
        final_output = call_llm(final_prompt)
        return {"output": final_output.strip()}


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = LongTextQA()
    result = model.debug(
        params={"prop1": "test"},
        inputs={"file_text": "根据长文本和用户指令，通过分片处理与大模型结合，实现对超长文档内容的精准问答；输入为长文本和自然语言指令，输出为结构化或摘要式回复，支持通过参数配置切片长度和大模型配置。", "instruction": "总结文档内容"},
        node_id="测试模型",
        show_input_types = True,
        show_output_types = True,
        show_execution_time = True,
        global_vars = {}
    )
    print(result)
