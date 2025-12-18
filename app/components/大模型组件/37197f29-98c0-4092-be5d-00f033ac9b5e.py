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


class Component(BaseComponent):
    name = "知识库检索增强"
    category = "大模型组件"
    description = "基于指定知识库，对输入问题进行语义检索并返回相关文档内容"
    requirements = "langchain,langchain_community"
    inputs = [
        PortDefinition(name="query", label="查询问题", type=ArgumentType.TEXT),
        PortDefinition(name="knowledge_base_id", label="知识库ID", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="context", label="检索结果", type=ArgumentType.TEXT),
        PortDefinition(name="documents", label="原始文档列表", type=ArgumentType.JSON),
    ]

    properties = {
        "top_k": PropertyDefinition(
            type=PropertyType.INT,
            label="返回结果数",
            default="3",
            min=1,
            max=10,
            step=1,
        ),
        "embedding_model": PropertyDefinition(
            type=PropertyType.CHOICE,
            label="嵌入模型",
            default="bge-small",
            choices=[
                "bge-small",
                "text-embedding-ada-002",
                "all-MiniLM-L6-v2"
            ],
        ),
        "use_rerank": PropertyDefinition(
            type=PropertyType.BOOL,
            label="启用重排序",
            default="True",
        ),
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import os
        from langchain_community.embeddings import HuggingFaceEmbeddings
        from langchain_community.vectorstores import FAISS
        from langchain.text_splitter import RecursiveCharacterTextSplitter
        from langchain.schema import Document
        import json

        query = inputs.get("query", "")
        knowledge_base_id = inputs.get("knowledge_base_id", params.get("knowledge_base_id", "default_kb"))
        top_k = int(params.get("top_k", 3))
        embedding_model_name = params.get("embedding_model", "bge-small")
        use_rerank = params.get("use_rerank", "True") == "True"

        # 模拟知识库路径
        kb_dir = f"./knowledge_bases/{knowledge_base_id}"
        if not os.path.exists(kb_dir):
            self.logger.error(f"知识库路径不存在: {kb_dir}")
            raise FileNotFoundError(f"知识库 {knowledge_base_id} 未找到")

        # 加载向量数据库
        try:
            db = FAISS.load_local(kb_dir, HuggingFaceEmbeddings(model_name=embedding_model_name), allow_dangerous_deserialization=True)
        except Exception as e:
            self.logger.error(f"加载向量库失败: {e}")
            raise

        # 检索
        try:
            docs = db.similarity_search(query, k=top_k)
        except Exception as e:
            self.logger.error(f"检索失败: {e}")
            raise

        # 提取文本内容
        context_texts = [doc.page_content for doc in docs]
        context = "\n\n".join(context_texts)

        # 原始文档信息（含元数据）
        raw_docs = []
        for doc in docs:
            raw_docs.append({
                "content": doc.page_content,
                "metadata": doc.metadata,
                "score": doc.metadata.get("score", 0.0)
            })

        # 重排序（可选）
        if use_rerank:
            # 简化模拟重排序逻辑
            raw_docs.sort(key=lambda x: x["score"], reverse=True)

        return {
            "context": context,
            "documents": json.dumps(raw_docs, ensure_ascii=False, indent=2)
        }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={
            "top_k": "3",
            "embedding_model": "bge-small",
            "use_rerank": "True",
        },
        inputs={
            "query": "什么是大模型？",
            "knowledge_base_id": "ai_knowledge",
        },
        global_vars={},
        node_id="test_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)
