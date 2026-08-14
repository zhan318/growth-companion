"""向量记忆：基于 ChromaDB 的对话历史语义检索

与 knowledge 共用 ChromaDB 实例，但使用独立的 collection。
"""

import os
from pathlib import Path

import chromadb

from utils.logger import get_logger

logger = get_logger(__name__)

# 独立于知识库的持久化目录和 collection 名称
# 允许测试时用环境变量覆盖存储目录（性能测试隔离用），默认 memory/vector_memory_db
_VECTOR_MEMORY_DIR = Path(os.getenv("VECTOR_MEMORY_DIR", str(Path(__file__).parent / "vector_memory_db")))
_COLLECTION_NAME = "conversation_memory"


class VectorMemory:
    """向量记忆：将对话历史转为向量存储，支持语义检索"""

    def __init__(self):
        _VECTOR_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(str(_VECTOR_MEMORY_DIR))
        self._collection = self._client.get_or_create_collection(
            name=_COLLECTION_NAME,
        )
        logger.info("向量记忆初始化完成，历史片段数=%d", self._collection.count())

    # ── 写入 ──

    def add_turn(self, session_id: str, user_msg: str, assistant_msg: str):
        """存储一轮对话

        Args:
            session_id: 会话 ID
            user_msg: 用户消息
            assistant_msg: AI 回复
        """
        content = f"用户：{user_msg}\nAI：{assistant_msg}"
        doc_id = f"{session_id}_{self._collection.count()}"

        self._collection.add(
            documents=[content],
            ids=[doc_id],
            metadatas=[{
                "session_id": session_id,
                "user": user_msg[:200],
            }],
        )
        logger.debug("已存储对话轮次: %s", doc_id)

    # ── 检索 ──

    def search(self, query: str, session_id: str | None = None, k: int = 3) -> list[dict[str, str]]:
        """检索与 query 最相关的历史对话

        Args:
            query: 用户问题
            session_id: 可选，限定会话
            k: 返回条数

        Returns:
            [{content, session_id, user}, ...]
        """
        if self._collection.count() == 0:
            return []

        where = {"session_id": session_id} if session_id else None
        results = self._collection.query(
            query_texts=[query],
            n_results=k,
            where=where,
        )

        items = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                items.append({
                    "content": doc,
                    "session_id": meta.get("session_id", ""),
                    "user": meta.get("user", ""),
                })
        return items

    # ── 管理 ──

    def count(self) -> int:
        return self._collection.count()

    def clear_session(self, session_id: str):
        """清空指定会话的记忆"""
        if self._collection.count() == 0:
            return
        results = self._collection.get(where={"session_id": session_id})
        if results["ids"]:
            self._collection.delete(ids=results["ids"])
            logger.info("已清空会话记忆: %s, 共 %d 条", session_id, len(results["ids"]))


# 全局单例
_memory: VectorMemory | None = None


def get_vector_memory() -> VectorMemory:
    global _memory
    if _memory is None:
        _memory = VectorMemory()
    return _memory
