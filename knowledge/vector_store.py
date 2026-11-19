"""向量存储 —— 基于 LangChain Chroma 封装"""

from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever

from utils.logger import get_logger

from .config import config
from .embeddings import get_embedding, get_embedding_model_id

logger = get_logger(__name__)

# ── collection 指纹（BUG-4）──
# 向量本身不携带「由哪个模型生成」的信息。换了 embedding 模型（或维度变了）
# 却没重建索引时，检索会静默返回一堆毫不相关的结果，接口照常 200，极难定位。
# 因此在 collection metadata 里记录「模型标识 + 维度」，每次打开时校验。
FINGERPRINT_VERSION = "1"
_META_MODEL = "embedding_model"
_META_DIM = "embedding_dimension"
_META_VER = "fingerprint_version"


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
        self._ensure_embedding_fingerprint()
        logger.info("向量库[%s]初始化完成, 文档数=%d", self.collection_name, self._store._collection.count())

    # ── 指纹校验 ──

    def _ensure_embedding_fingerprint(self) -> None:
        """校验 collection 的 embedding 指纹；老库无指纹时探测维度并回填。

        三种情况：
        1. 已有指纹且与当前配置一致 → 放行；
        2. 已有指纹但不一致 → 直接抛 ValueError（必须重建索引）；
        3. 无指纹（历史库）→ 读一条已存向量比维度，一致则回填，不一致则抛错。
           只比维度是粗校验：同维度的不同模型识别不出来，但能拦住绝大多数事故
           （换模型换维度、误用英文模型 384 维等）。
        """
        col = self._store._collection
        meta = dict(col.metadata or {})
        model_id = get_embedding_model_id()
        dim = self._current_embedding_dimension()

        stored_model = meta.get(_META_MODEL)
        stored_dim = meta.get(_META_DIM)

        if stored_model is not None and stored_dim is not None:
            if str(stored_model) != model_id or int(stored_dim) != dim:
                raise ValueError(
                    f"向量库[{self.collection_name}]的 embedding 指纹与当前配置不一致："
                    f"索引由 {stored_model}({stored_dim}维) 生成，"
                    f"当前配置是 {model_id}({dim}维)。"
                    "换 embedding 模型后旧向量在新语义空间里无效，必须重建该 collection。"
                )
            return

        if self.count() == 0:
            # 空库：先写指纹，之后写入的向量必然来自当前模型
            self._write_fingerprint(meta, model_id, dim)
            return

        stored_probe = self._probe_stored_dimension()
        if stored_probe is None:
            logger.warning(
                "向量库[%s]无法探测已存向量维度，跳过指纹校验（检索仍可用）",
                self.collection_name,
            )
            return
        if stored_probe != dim:
            raise ValueError(
                f"向量库[{self.collection_name}]已存向量是 {stored_probe} 维，"
                f"当前 embedding 配置是 {model_id}({dim}维)，二者不兼容。"
                "请重建该 collection 后再使用（换模型必须重新索引）。"
            )
        self._write_fingerprint(meta, model_id, dim)
        logger.info(
            "向量库[%s]回填 embedding 指纹: %s(%d维)", self.collection_name, model_id, dim
        )

    def _current_embedding_dimension(self) -> int:
        """当前 embedding 的维度（优先读模型属性，避免多余编码）"""
        emb = self._store.embeddings
        dim = getattr(emb, "dimension", None)
        if dim is None:
            dim = len(emb.embed_query("dimension probe"))
        return int(dim)

    def _probe_stored_dimension(self) -> int | None:
        """读取库中第一条已存向量的维度；失败或空库返回 None"""
        try:
            res = self._store._collection.get(limit=1, include=["embeddings"])
        except Exception as e:
            logger.warning("探测向量维度失败: %s", e)
            return None
        embs = res.get("embeddings")
        if embs is None or len(embs) == 0:
            return None
        return int(len(embs[0]))

    def _write_fingerprint(self, base_meta: dict, model_id: str, dim: int) -> None:
        """把指纹合并进 collection metadata（保留原有键，如 hnsw:space）"""
        new_meta = dict(base_meta)
        new_meta[_META_MODEL] = model_id
        new_meta[_META_DIM] = dim
        new_meta[_META_VER] = FINGERPRINT_VERSION
        try:
            self._store._collection.modify(metadata=new_meta)
        except Exception as e:
            # 写不上指纹不影响检索，只是下次启动会重新探测
            logger.warning("写入 embedding 指纹失败（不影响检索）: %s", e)

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
        # 新 collection 是空的，重新写入指纹
        self._ensure_embedding_fingerprint()
        logger.info("向量库[%s]已清空并重建", self.collection_name)


_store_instances: dict[str, VectorStore] = {}


def get_vector_store(name: str | None = None) -> VectorStore:
    """按 collection 名获取（或创建）向量库实例；默认返回 knowledge_base。"""
    key = name or config.COLLECTION_NAME
    if key not in _store_instances:
        _store_instances[key] = VectorStore(collection_name=key)
    return _store_instances[key]
