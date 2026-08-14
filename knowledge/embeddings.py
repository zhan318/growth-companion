"""Embedding 管理 —— 支持本地模型 / DeepSeek API"""


from langchain_core.embeddings import Embeddings

from utils.logger import get_logger

from .config import config

logger = get_logger(__name__)


class ChromaDefaultEmbeddings(Embeddings):
    """LangChain 适配器：包装 ChromaDB 内置的 all-MiniLM-L6-v2"""

    def __init__(self):
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
        self._fn = DefaultEmbeddingFunction()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._fn(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._fn([text])[0]


class DeepSeekEmbeddings(Embeddings):
    """DeepSeek Embedding API（OpenAI 兼容格式）"""

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = "deepseek-embedding"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        resp = self.client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in resp.data]

    def embed_query(self, text: str) -> list[float]:
        resp = self.client.embeddings.create(model=self.model, input=[text])
        return resp.data[0].embedding


def get_embedding() -> Embeddings:
    """工厂方法：根据配置选择 Embedding 模型"""
    model_type = config.EMBEDDING_MODEL

    if model_type == "deepseek":
        from config import DEEPSEEK_API_KEY
        if not DEEPSEEK_API_KEY:
            logger.warning("DEEPSEEK_API_KEY 未配置，回退到本地模型")
            return ChromaDefaultEmbeddings()
        logger.info("Embedding: DeepSeek API")
        return DeepSeekEmbeddings(api_key=DEEPSEEK_API_KEY)

    # default → ChromaDB 内置模型
    logger.info("Embedding: ChromaDB 内置 all-MiniLM-L6-v2")
    return ChromaDefaultEmbeddings()
