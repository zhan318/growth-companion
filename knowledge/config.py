"""知识库配置：切片策略、检索参数、模型选择"""

import os


class KnowledgeConfig:
    """所有知识库配置项，可通过环境变量覆盖"""

    # ── 文档目录 ──
    DOCS_DIR: str = os.getenv(
        "KNOWLEDGE_DOCS_DIR",
        os.path.join(os.path.dirname(__file__), "docs"),
    )

    # ── 向量数据库持久化目录 ──
    VECTOR_DB_DIR: str = os.getenv(
        "KNOWLEDGE_VECTOR_DB_DIR",
        os.path.join(os.path.dirname(__file__), "chroma_db"),
    )

    # ── 文本切片 ──
    CHUNK_SIZE: int = int(os.getenv("KNOWLEDGE_CHUNK_SIZE", "500"))
    CHUNK_OVERLAP: int = int(os.getenv("KNOWLEDGE_CHUNK_OVERLAP", "50"))

    # ── 检索 ──
    # 最终送 LLM 的上下文条数
    RETRIEVE_TOP_K: int = int(os.getenv("KNOWLEDGE_RETRIEVE_TOP_K", "3"))
    # 召回池大小：dense / BM25 各自召回条数，经 RRF 融合后交精排筛选。
    # 需大于 RETRIEVE_TOP_K，才有「宽召回 + 严精排」两阶段检索的意义。
    RETRIEVE_RECALL_N: int = int(os.getenv("KNOWLEDGE_RETRIEVE_RECALL_N", "20"))
    # 精排开关：模型不可用时可一键回退（关闭后行为与改造前一致）
    RERANK_ENABLED: bool = os.getenv("KNOWLEDGE_RERANK_ENABLED", "true").lower() != "false"

    # ── Embedding 模型 ──
    # 可选: "default" (ChromaDB内置, 英文优化) | "sentence-transformers" (本地中文模型) | "deepseek"
    # 默认用本地中文模型：all-MiniLM-L6-v2 对中文 query 几乎失效（dense 命中率实测 4.8%）
    EMBEDDING_MODEL: str = os.getenv("KNOWLEDGE_EMBEDDING", "sentence-transformers")
    # sentence-transformers 具体模型名（BGE 中文小模型，512 维，CPU 可跑）
    EMBEDDING_ST_MODEL: str = os.getenv(
        "KNOWLEDGE_EMBEDDING_ST_MODEL", "BAAI/bge-small-zh-v1.5"
    )

    # ── 向量数据库 ──
    # 可选: "chroma" | "faiss" (预留)
    VECTOR_STORE_TYPE: str = os.getenv("KNOWLEDGE_VECTOR_STORE", "chroma")

    # ── Collection 名称 ──
    COLLECTION_NAME: str = "knowledge_base"


# 全局单例
config = KnowledgeConfig()
