"""RAG 知识库检索工具 —— 接入 Agent 的 tool_registry

提供同步（knowledge_search）与异步（knowledge_search_async）两个版本。
"""

from knowledge.pipeline import query as rag_query
from knowledge.pipeline import query_async as rag_query_async
from tools import registry
from utils.logger import get_logger

logger = get_logger(__name__)

MAX_RESULT_LENGTH = 1500  # 返回给 LLM 的最大字符数


def _truncate(result: str) -> str:
    """截断过长结果，防止 token 超出限制"""
    if len(result) > MAX_RESULT_LENGTH:
        return result[:MAX_RESULT_LENGTH] + "\n\n[回答过长已截断]"
    return result


@registry.register(
    description="在个人知识库中检索信息来回答专业问题。"
                "当用户询问知识库中的内容（如项目文档、公司流程、学习笔记等）时调用此工具。"
                "普通闲聊、查天气、做计算请使用其他对应工具。"
)
def knowledge_search(query: str) -> str:
    """从知识库中检索并生成答案（同步版）。

    Args:
        query: 用户的问题或查询关键词
    """
    logger.info("RAG 工具被调用: %s", query)
    return _truncate(rag_query(query))


@registry.register_async(
    description="在个人知识库中检索信息来回答专业问题。"
                "当用户询问知识库中的内容（如项目文档、公司流程、学习笔记等）时调用此工具。"
                "普通闲聊、查天气、做计算请使用其他对应工具。"
)
async def knowledge_search_async(query: str) -> str:
    """从知识库中检索并生成答案（异步版，Agent.arun 使用）。

    Args:
        query: 用户的问题或查询关键词
    """
    logger.info("RAG 工具被调用(异步): %s", query)
    result = await rag_query_async(query)
    return _truncate(result)
