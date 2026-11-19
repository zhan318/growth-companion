"""Embedding 管理 —— 本地中文模型（默认）/ ChromaDB 内置英文模型

注意：DeepSeek 官方不提供 embedding 接口（只有 chat 模型），
因此本项目不提供任何远端 embedding 实现；向量化全部在本机完成。
"""


from functools import lru_cache

from langchain_core.embeddings import Embeddings

from utils.logger import get_logger

from .config import config

logger = get_logger(__name__)


class ChromaDefaultEmbeddings(Embeddings):
    """LangChain 适配器：包装 ChromaDB 内置的 all-MiniLM-L6-v2"""

    MODEL_ID = "all-MiniLM-L6-v2"
    DIMENSION = 384

    def __init__(self):
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
        self._fn = DefaultEmbeddingFunction()

    @property
    def dimension(self) -> int:
        """向量维度（供 collection 指纹校验使用，不需要真正编码）"""
        return self.DIMENSION

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._fn(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._fn([text])[0]


class SentenceTransformerEmbeddings(Embeddings):
    """本地中文语义模型（默认 BAAI/bge-small-zh-v1.5，512 维，CPU 友好）

    BGE 官方最佳实践：
    - 短查询检索长文档时，query 侧加检索指令前缀，可显著提升召回；
    - 向量做 L2 归一化（normalize_embeddings=True），配合 cosine 相似度。
    """

    QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        from sentence_transformers import SentenceTransformer
        logger.info("加载本地 embedding 模型: %s", model_name)
        self.model_name = model_name
        self._model = SentenceTransformer(model_name)

    @property
    def dimension(self) -> int:
        """向量维度（直接读模型配置，不需要真正编码）"""
        # sentence-transformers 6.x 改名为 get_embedding_dimension，兼容旧版本
        fn = getattr(self._model, "get_embedding_dimension", None)
        if fn is None:
            fn = self._model.get_sentence_embedding_dimension
        return int(fn())

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self._model.encode(
            [self.QUERY_INSTRUCTION + text], normalize_embeddings=True
        ).tolist()[0]


# 合法配置值白名单（显式列举，拒绝一切兜底）
#   sentence-transformers → 本地中文模型（默认推荐，BAAI/bge-small-zh-v1.5）
#   default               → ChromaDB 内置 all-MiniLM-L6-v2（英文模型，中文检索几乎失效，仅英文场景）
# 注意：deepseek 官方没有 embedding 接口，故不在白名单内。
_VALID_EMBEDDING_MODELS = frozenset({"sentence-transformers", "default"})


def validate_embedding_config() -> str:
    """校验 KNOWLEDGE_EMBEDDING 配置值，返回归一化后的值；非法即抛 ValueError。

    设计原则：配置写错必须「启动即失败」，绝不静默回退到英文模型 ——
    那会让中文检索悄悄失效，而接口照常返回答案，问题极难定位。
    本函数只做字符串校验，不加载模型，可在启动时零成本调用。
    """
    raw = (config.EMBEDDING_MODEL or "").strip().lower()
    if raw not in _VALID_EMBEDDING_MODELS:
        raise ValueError(
            f"KNOWLEDGE_EMBEDDING={config.EMBEDDING_MODEL!r} 不是合法值。"
            f"合法值: {sorted(_VALID_EMBEDDING_MODELS)}。"
            "（deepseek 官方无 embedding 接口，不能用于向量化）"
        )
    return raw


def get_embedding_model_id() -> str:
    """返回当前配置对应的 embedding 模型标识（不加载模型）。

    用于 collection 指纹校验：指纹记录「模型标识 + 维度」，
    换模型却没重建索引时启动即报错，而不是静默返回无关结果。
    """
    model_type = validate_embedding_config()
    if model_type == "sentence-transformers":
        return config.EMBEDDING_ST_MODEL
    return ChromaDefaultEmbeddings.MODEL_ID


@lru_cache(maxsize=1)
def get_embedding() -> Embeddings:
    """工厂方法：根据配置选择 Embedding 模型（非法配置直接抛错，不做兜底）。

    进程内只加载一次：多个 collection（knowledge_base / obsidian）共享同一份模型，
    避免每个 VectorStore 实例都往内存里塞一份 BGE（与 reranker 的 @lru_cache 同款做法）。
    返回对象无会话状态，可安全跨线程共享。
    """
    model_type = validate_embedding_config()

    if model_type == "sentence-transformers":
        logger.info("Embedding: sentence-transformers (%s)", config.EMBEDDING_ST_MODEL)
        return SentenceTransformerEmbeddings(config.EMBEDDING_ST_MODEL)

    # default → 显式选择 ChromaDB 内置英文模型
    logger.warning(
        "Embedding: ChromaDB 内置 all-MiniLM-L6-v2"
        "（英文模型，中文检索效果极差，仅建议英文场景使用）"
    )
    return ChromaDefaultEmbeddings()
