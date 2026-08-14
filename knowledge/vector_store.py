"""向量存储 —— 基于 LangChain Chroma 封装"""

from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever

from utils.logger import get_logger

from .config import config
from .embeddings import get_embedding

logger = get_logger(__name__)


class VectorStore:
    """向量数据库封装（支持多 collection 隔离，如 knowledge_base 与 obsidian）"""

    def __init__(self, collection_name: str | None = None):
        self.collection_name = collection_name or config.COLLECTION_NAME
        persist_dir = Path(config.VECTOR_DB_DIR)
        persist_dir.mkdir(parents=True, exist_ok=True)

        embedding = get_embedding()
        self._store = Chroma(
            collection_name=self.collection_name,
            embedding_function=embedding,
            persist_directory=str(persist_dir),
        )
        self._retriever: VectorStoreRetriever | None = None
        logger.info("向量库[%s]初始化完成, 文档数=%d", self.collection_name, self._store._collection.count())

    # ── 写入 ──

    def add_documents(self, documents: list[Document]) -> int:
        """批量写入文档"""
        ids = self._store.add_documents(documents)
        logger.info("向量库写入 %d 条", len(documents))
        # 清除缓存检索器
        self._retriever = None
        return len(ids)

    # ── 检索 ──

    def get_retriever(self, k: int | None = None) -> VectorStoreRetriever:
        """获取 LangChain Retriever"""
        if self._retriever is None or k:
            self._retriever = self._store.as_retriever(
                search_kwargs={"k": k or config.RETRIEVE_TOP_K},
            )
        return self._retriever

    def search(self, query: str, k: int | None = None) -> list[Document]:
        """语义检索，返回 Document 列表"""
        retriever = self.get_retriever(k)
        docs = retriever.invoke(query)
        return docs

    # ── 底层访问（供增量索引使用）──

    def get(self, ids=None, include=None):
        """获取已有文档的 ids / metadatas，用于增量索引对比。"""
        kwargs = {}
        if ids is not None:
            kwargs["ids"] = ids
        if include is not None:
            kwargs["include"] = include
        return self._store.get(**kwargs)

    def delete(self, ids):
        """按 id 删除文档（增量索引时移除变更/删除的文件）。"""
        if ids:
            self._store.delete(ids)
            self._retriever = None

    def add_documents_with_ids(self, documents: list[Document], ids):
        """带确定性 id 写入，便于增量更新与去重。"""
        self._store.add_documents(documents, ids=ids)
        self._retriever = None
        logger.info("向量库[%s]写入 %d 条", self.collection_name, len(documents))

    # ── 管理 ──

    def count(self) -> int:
        return self._store._collection.count()

    def delete_all(self):
        # 删除旧 collection
        self._store.delete_collection()
        self._retriever = None
        # 重建 Chroma 实例
        embedding = get_embedding()
        self._store = Chroma(
            collection_name=self.collection_name,
            embedding_function=embedding,
            persist_directory=str(Path(config.VECTOR_DB_DIR)),
        )
        logger.info("向量库[%s]已清空并重建", self.collection_name)


_store_instances: dict[str, VectorStore] = {}


def get_vector_store(name: str | None = None) -> VectorStore:
    """按 collection 名获取（或创建）向量库实例；默认返回 knowledge_base。"""
    key = name or config.COLLECTION_NAME
    if key not in _store_instances:
        _store_instances[key] = VectorStore(collection_name=key)
    return _store_instances[key]
