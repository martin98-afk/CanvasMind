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


class SmartTextSplitter(BaseComponent):
    name = "智能文本分片器"
    category = "数据处理"
    description = "根据最大 token 长度对长文本进行智能分片，保留段落结构并支持重叠控制，适用于大模型输入预处理。"
    requirements = ""
    inputs = [
        PortDefinition(name="text", label="输入文本", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="chunks", label="分片结果", type=ArgumentType.ARRAY),
    ]
    properties = {
        "overlap_ratio": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.05,
            label="重叠比例",
        ),
        "min_chunk_size": PropertyDefinition(
            type=PropertyType.INT,
            default=500,
            label="最小分片长度",
        ),
        "max_tokens": PropertyDefinition(
            type=PropertyType.RANGE,
            default="5000.0",
            label="最大 token 长度",
            min=3000.0,
            max=8000.0,
            step=1000.0,
        ),
    }
    def run(self, params, inputs=None):
        """
        智能分片主逻辑：
        - 按段落切分
        - 控制每片 token 数量
        - 支持重叠区域
        - 去重与合并
        Args:
            text (str): 输入长文本
            max_tokens (int): 每片最大 token 数（估算值）
        Returns:
            dict: {"chunks": ["片1", "片2", ...]}
        """
        import re
        from typing import List
        # 获取输入
        text = inputs.text
        max_tokens = int(params.max_tokens)
        overlap_ratio = float(params.overlap_ratio)
        min_chunk_size = int(params.min_chunk_size)
        # 估算 token 数（中文 ≈ 1 字 ≈ 2 tokens）
        def estimate_tokens(txt: str) -> int:
            return len(txt) // 2
        # 段落切分（保留换行）
        paragraphs = re.split(r'(\n\s*\n)', text)
        chunks = []
        current_chunk = ""
        overlap_chars = int(max_tokens * overlap_ratio * 2)  # 保守估算字符数
        for para in paragraphs:
            if not para.strip():
                continue
            test_chunk = current_chunk + para
            if estimate_tokens(test_chunk) <= max_tokens:
                current_chunk = test_chunk
            else:
                if current_chunk:
                    # 保存当前块
                    chunks.append(current_chunk)
                    # 重叠部分保留
                    overlap_start = max(0, len(current_chunk) - overlap_chars)
                    current_chunk = current_chunk[overlap_start:] + para
                else:
                    # 若当前为空，直接切分长段落
                    parts = self._split_long_paragraph(para, max_tokens)
                    chunks.extend(parts[:-1])
                    current_chunk = parts[-1] if parts else ""
        # 添加最后一块
        if current_chunk:
            chunks.append(current_chunk)
        # 去重处理（避免重复）
        deduped = []
        for chunk in chunks:
            if not deduped or chunk.strip() != deduped[-1].strip():
                deduped.append(chunk)
        # 过滤过短分片
        filtered_chunks = []
        for chunk in deduped:
            if len(chunk.strip()) >= min_chunk_size:
                filtered_chunks.append(chunk)
            else:
                # 合并到前一块
                if filtered_chunks:
                    filtered_chunks[-1] += chunk
                else:
                    filtered_chunks.append(chunk)
        return {"chunks": filtered_chunks}
    
    def _split_long_paragraph(self, para: str, max_tokens: int):
        """将长段落按句子切分，避免超长"""
        import re
        
        def estimate_tokens(text: str) -> int:
            # 粗略估算：中文 1 字 ≈ 2 tokens，英文 1 字 ≈ 1.3 tokens，保守取 len//2
            return len(text) // 2
        
        
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
    
    
if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = SmartTextSplitter()
    result = model.debug(
        params={
            "overlap_ratio": 0.1,
            "min_chunk_size": 5,
            "max_tokens": 3000
        },
        inputs={
            "text": "这是第一段内容。这是第二段内容，包含多个句子。第三段开始，用于测试分片效果。第四段较长，用于验证重叠控制。第五段较短，应被合并。",
            
        },
        global_vars={},
        node_id="test_splitter",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)