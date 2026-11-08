"""Cross-Encoder 精排：对 RRF 融合后的候选集做相关性打分，取最终 top-k。

设计要点：
- **懒加载**：首次调用才加载模型，不拖慢服务启动；
- **优雅降级**：模型缺失/加载失败时退化为「按原顺序截断」，检索功能不受影响；
- **可选阈值**：低于阈值的文档被丢弃，可用于「知识库无相关内容」的判定。

为什么需要它（本项目实测结论）：
RRF 只依据排名位置融合，看不懂内容。实测中「每日疑难总结」这类流水笔记因技术术语
密集、BM25 词面匹配分高，把真正回答问题的专题笔记挤出了 top-3。Cross-Encoder 直接
读 query 与文档内容算相关性，能纠正这类「词面匹配 ≠ 真正相关」的误判。
"""

from functools import lru_cache

from utils.logger import get_logger

logger = get_logger(__name__)

RERANK_MODEL = "BAAI/bge-reranker-base"
RERANK_MAX_LEN = 512


@lru_cache(maxsize=1)
def _get_model():
    """懒加载 CrossEncoder（进程内只加载一次）"""
    from sentence_transformers import CrossEncoder

    logger.info("加载精排模型: %s", RERANK_MODEL)
    return CrossEncoder(RERANK_MODEL, max_length=RERANK_MAX_LEN)


def rerank(query: str, docs: list, top_n: int = 3, threshold: float | None = None) -> list:
    """对候选文档精排，返回 top_n 条。

    Args:
        query: 用户查询
        docs: RRF 融合后的候选 Document 列表（建议 20~30 条）
        top_n: 最终返回条数（送 LLM 的上下文数量）
        threshold: 可选分数阈值，低于它的文档被丢弃

    Returns:
        精排后的 Document 列表；模型不可用时返回按原顺序的前 top_n 条。
    """
    if not docs:
        return []
    if len(docs) <= 1:
        return docs[:top_n]

    try:
        model = _get_model()
        scores = model.predict([(query, d.page_content) for d in docs])
    except Exception as e:
        # 模型未安装 / 下载失败 / 显存不足等：降级为原顺序，保证检索可用
        logger.warning("精排模型不可用，降级为原顺序截断: %s", e)
        return docs[:top_n]

    ranked = sorted(zip(docs, scores), key=lambda x: -float(x[1]))
    if threshold is not None:
        ranked = [(d, s) for d, s in ranked if float(s) >= threshold]
    return [d for d, _ in ranked[:top_n]]
