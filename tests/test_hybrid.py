"""hybrid.py 纯函数单测：rrf_fusion / tokenize_chinese

这两个函数不依赖 langchain（hybrid.py 顶层只 import re + logger），
可脱离完整 RAG 链路独立验证。
"""

from knowledge.hybrid import rrf_fusion, tokenize_chinese


# ── rrf_fusion ─────────────────────────────────────────────

def test_rrf_fusion_basic():
    """两个列表融合：共同出现的 key 分数叠加，返回全部去重 key"""
    ranked = rrf_fusion([["a", "b"], ["b", "a"]], k=60)
    keys = [k for k, _ in ranked]
    assert len(ranked) == 2
    assert set(keys) == {"a", "b"}


def test_rrf_fusion_top1_priority():
    """同时出现在两个列表首位的 key 得分最高，排第一"""
    ranked = rrf_fusion([["x", "y"], ["x", "z"]], k=60)
    assert ranked[0][0] == "x"


def test_rrf_fusion_union():
    """只在一个列表出现的 key 也会保留（融合不丢 recall）"""
    ranked = rrf_fusion([["a"], ["b"]], k=60)
    assert set(k for k, _ in ranked) == {"a", "b"}


def test_rrf_fusion_top_n():
    """top_n 正确截断"""
    ranked = rrf_fusion([["a", "b", "c"], ["a", "c", "b"]], top_n=2)
    assert len(ranked) == 2


def test_rrf_fusion_empty():
    """空输入不报错"""
    assert rrf_fusion([]) == []
    assert rrf_fusion([[], []]) == []


def test_rrf_fusion_score_descending():
    """返回按融合分数降序"""
    ranked = rrf_fusion([["a", "b", "c"], ["c", "a", "b"]], k=60)
    scores = [s for _, s in ranked]
    assert scores == sorted(scores, reverse=True)


# ── tokenize_chinese ───────────────────────────────────────

def test_tokenize_empty():
    assert tokenize_chinese("") == []
    assert tokenize_chinese("   ") == []


def test_tokenize_chinese_returns_tokens():
    """中文输入应返回非空 token 列表（jieba 或 n-gram 降级均可）"""
    tokens = tokenize_chinese("快速排序的实现")
    assert isinstance(tokens, list)
    assert len(tokens) > 0


def test_tokenize_english_lowercase():
    """英文 token 小写化"""
    tokens = tokenize_chinese("Hello World")
    assert "hello" in tokens or "world" in tokens


def test_tokenize_filters_stopwords():
    """停用词（如「什么」）不应出现在 token 里"""
    tokens = tokenize_chinese("什么是排序")
    assert "什么" not in tokens
