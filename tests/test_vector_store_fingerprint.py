"""vector_store 指纹校验（BUG-4）单测

用假 Embedding 替代真实模型：不下载模型、不加载 BGE，秒级完成。
覆盖四种场景：
  1. 空 collection 首次打开即写入指纹
  2. 历史库（无指纹）探测维度后回填，且保留原有 metadata 键
  3. 指纹里的模型名与当前配置不一致 → 拒绝
  4. 已存向量维度与当前模型不一致 → 拒绝
"""

import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from knowledge import vector_store as vs


class FakeEmbeddings(Embeddings):
    """维度可控的假嵌入：向量值无意义，只关心维度"""

    def __init__(self, dim: int):
        self._dim = dim

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.01] * self._dim for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.01] * self._dim


@pytest.fixture
def fake_env(monkeypatch, tmp_path):
    """把向量库目录、嵌入模型、模型标识全部替换掉，避免真实依赖"""

    def _apply(dim: int = 8, model: str = "fake-model-v1"):
        monkeypatch.setattr(vs.config, "VECTOR_DB_DIR", str(tmp_path))
        monkeypatch.setattr(vs, "get_embedding", lambda: FakeEmbeddings(dim))
        monkeypatch.setattr(vs, "get_embedding_model_id", lambda: model)

    return _apply


def test_empty_collection_writes_fingerprint(fake_env):
    fake_env()
    store = vs.VectorStore("tbl")
    meta = store._store._collection.metadata or {}
    assert meta["embedding_model"] == "fake-model-v1"
    assert meta["embedding_dimension"] == 8
    assert meta["fingerprint_version"] == vs.FINGERPRINT_VERSION


def test_legacy_collection_is_backfilled(fake_env):
    fake_env()
    store = vs.VectorStore("legacy")
    store.add_documents([Document(page_content="hello", metadata={})])
    # 抹掉指纹，模拟历史库（现有生产库 metadata 就是 None）
    store._store._collection.modify(metadata={"legacy": "yes"})

    reopened = vs.VectorStore("legacy")
    meta = reopened._store._collection.metadata or {}
    assert meta["embedding_model"] == "fake-model-v1"
    assert meta["embedding_dimension"] == 8
    assert meta["legacy"] == "yes"  # 原有 metadata 键必须保留


def test_model_mismatch_raises(fake_env):
    fake_env()
    vs.VectorStore("mismatch")
    vs.VectorStore("mismatch")._store._collection.modify(
        metadata={"embedding_model": "old-model", "embedding_dimension": 8}
    )
    with pytest.raises(ValueError, match="old-model"):
        vs.VectorStore("mismatch")


def test_dimension_mismatch_raises(fake_env):
    fake_env(dim=8)
    store = vs.VectorStore("dims")
    store.add_documents([Document(page_content="x", metadata={})])
    # 抹掉指纹，走「探测已存向量维度」这条历史库路径
    store._store._collection.modify(metadata={"legacy": "yes"})

    # 换成维度不同的模型，模拟「换 embedding 却没重建索引」
    fake_env(dim=16, model="other-model")
    with pytest.raises(ValueError, match="8 维"):
        vs.VectorStore("dims")
