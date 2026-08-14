"""检索器 —— 基于 LangChain Retriever"""


from langchain_core.documents import Document

from utils.logger import get_logger

from .config import config
from .vector_store import VectorStore, get_vector_store

logger = get_logger(__name__)


class Retriever:
    """检索器：封装检索 + 格式化"""

    def __init__(self, store: VectorStore | None = None):
        self.store = store or get_vector_store()

    def search(self, query: str, k: int | None = None) -> list[Document]:
        """语义检索"""
        top_k = k or config.RETRIEVE_TOP_K
        docs = self.store.search(query, k=top_k)
        logger.info("检索 \"%s\" → %d 条结果", query, len(docs))
        return docs

    def get_langchain_retriever(self):
        """返回 LangChain Retriever 对象（供 Chain 使用）"""
        return self.store.get_retriever()

    def format_context(self, results: list[Document]) -> str:
        """将 Document 列表格式化为 LLM 上下文文本"""
        if not results:
            return ""

        lines = ["以下是知识库中与问题相关的内容：\n"]
        for i, doc in enumerate(results, 1):
            source = doc.metadata.get("source", "未知来源")
            lines.append(f"[{i}] 来源: {source}")
            lines.append(doc.page_content[:300])
            lines.append("")
        return "\n".join(lines)


_retriever: Retriever | None = None


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    return _retriever
