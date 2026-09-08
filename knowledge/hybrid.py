"""混合检索：BM25 稀疏检索 + dense 稠密检索 → RRF 融合。

参考 hitgate（BM25 + dense + Reciprocal Rank Fusion）针对中文笔记做适配：
- 中文分词用 jieba（不可用时降级到 2/3/4 字 n-gram，零依赖保证可跑）
- BM25 语料从向量库懒加载并内存缓存，索引重建后需调用 invalidate_bm25 失效

设计说明：
- rrf_fusion / tokenize_chinese 是纯函数，不依赖 langchain，可独立单测。
- Document 相关逻辑（fuse_documents / BM25Retriever）在函数内惰性 import，
  避免顶层 import langchain 拖累纯函数测试。
"""

from __future__ import annotations

import re

from utils.logger import get_logger

logger = get_logger(__name__)

# RRF 平滑常数（hitgate 同款：score = 1/(k+rank+1)）
RRF_K = 60

# 中文停用词（与旧 _extract_keywords 对齐，避免无意义 token 进 BM25）
_STOP = {
    "我们", "你们", "他们", "自己", "什么", "怎么", "如何", "为什么", "哪些", "这个",
    "那个", "这些", "那些", "已经", "可以", "应该", "需要", "知道", "想要", "希望",
    "目前", "没有", "不是", "就是", "还是", "并且", "或者", "关于", "对于", "学习",
    "过程", "遇到", "遇到过", "笔记", "内容", "直接", "记录", "担心", "试试", "告诉",
    "请问", "想问", "我想", "我的", "你的", "有没有", "一下", "一些", "之类", "让我",
    "看看", "帮我", "里面", "它们", "她们", "您",
    "输入", "字体", "变成", "回来", "突然", "哪些",
}


def tokenize_chinese(text: str) -> list[str]:
    """中文/英文混合分词，返回 BM25 可用的 token 列表。

    jieba 可用时用 jieba 分词（更准）；否则降级到 2/3/4 字滑窗 + 英文/数字词。
    """
    text = (text or "").strip()
    if not text:
        return []

    try:
        import jieba
        tokens = [t.strip().lower() for t in jieba.cut(text) if t.strip()]
        tokens = [t for t in tokens if t not in _STOP and len(t) > 1]
        if tokens:
            return tokens
    except ImportError:
        pass

    # 降级：中文 2/3/4 字滑窗 + 英文/数字词（不依赖分词库）
    seen: set[str] = set()
    out: list[str] = []
    for seg in re.findall(r"[\u4e00-\u9fa5]+", text):
        n = len(seg)
        for size in (4, 3, 2):
            if n >= size:
                for i in range(n - size + 1):
                    gram = seg[i:i + size]
                    if gram not in _STOP and gram not in seen:
                        seen.add(gram)
                        out.append(gram)
    for w in re.findall(r"[a-z0-9]{2,}", text.lower()):
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def rrf_fusion(ranked_lists, k: int = RRF_K, top_n=None):
    """对多个已排序（best-first）的 key 序列做 RRF 融合。

    Args:
        ranked_lists: list[list[key]]，每个子列表是 best-first 的可哈希 key 序列
        k: RRF 平滑常数
        top_n: 返回前 N 个（None = 全部）

    Returns:
        list[(key, score)]，按融合分数降序
    """
    scores: dict = {}
    for lst in ranked_lists:
        for rank, key in enumerate(lst):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    if top_n is not None:
        ranked = ranked[:top_n]
    return ranked


def fuse_documents(*doc_lists, k: int = RRF_K, top_n=None):
    """融合多个 Document 列表（用 page_content 作对齐 key），返回 Document 列表。

    同一内容在多个列表出现时，取最先出现的 Document（保留更完整的 metadata）。
    """
    from langchain_core.documents import Document

    doc_by_content: dict[str, Document] = {}
    for lst in doc_lists:
        for d in lst:
            doc_by_content.setdefault(d.page_content, d)
    merged = rrf_fusion(
        [[d.page_content for d in lst] for lst in doc_lists], k=k, top_n=top_n
    )
    return [doc_by_content[key] for key, _ in merged]


class BM25Retriever:
    """从向量库懒加载全部 chunk 构建 BM25 语料，内存缓存。"""

    def __init__(self, store):
        self._store = store
        self._docs: list | None = None
        self._bm25 = None

    def _ensure_loaded(self):
        if self._bm25 is not None:
            return
        from langchain_core.documents import Document

        data = self._store.get(include=["documents", "metadatas"])
        texts = data.get("documents") or []
        metas = data.get("metadatas") or []
        self._docs = [
            Document(page_content=t, metadata=m or {})
            for t, m in zip(texts, metas)
        ]
        if self._docs:
            from rank_bm25 import BM25Okapi
            self._bm25 = BM25Okapi([tokenize_chinese(d.page_content) for d in self._docs])
            logger.info("BM25 语料构建完成: %d 条 chunk", len(self._docs))

    def invalidate(self):
        self._docs = None
        self._bm25 = None

    def search(self, query: str, k: int = 5) -> list:
        """BM25 检索，返回分数 > 0 的 top-k Document 列表。"""
        self._ensure_loaded()
        if self._bm25 is None:
            return []
        tokens = tokenize_chinese(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        return [self._docs[i] for i in order[:k] if scores[i] > 0]


_bm25_cache: dict[str, BM25Retriever] = {}


def get_bm25_retriever(store) -> BM25Retriever:
    """按 collection 名获取（或创建）BM25 检索器。"""
    key = store.collection_name
    if key not in _bm25_cache:
        _bm25_cache[key] = BM25Retriever(store)
    return _bm25_cache[key]


def invalidate_bm25(collection_name: str | None = None):
    """索引重建后调用，清空对应 BM25 缓存；collection_name=None 清空全部。"""
    if collection_name:
        _bm25_cache.pop(collection_name, None)
    else:
        _bm25_cache.clear()
