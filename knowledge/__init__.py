"""Knowledge Agent — 企业级 RAG 知识库模块

本模块实现完整的 RAG 流程：
文档加载 → 文本切片 → Embedding 向量化 → 向量存储 → 语义检索
不依赖 Agent，可独立使用。
"""

from .config import KnowledgeConfig
from .pipeline import index_documents, query
from .vector_store import get_vector_store

__all__ = [
    "query",
    "index_documents",
    "KnowledgeConfig",
    "get_vector_store",
]
