"""文本切片 —— 基于 LangChain Text Splitter"""


from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from utils.logger import get_logger

from .config import config

logger = get_logger(__name__)


class Chunker:
    """切片器，封装 LangChain 的 RecursiveCharacterTextSplitter"""

    def __init__(self, chunk_size: int | None = None, chunk_overlap: int | None = None):
        self.chunk_size = chunk_size or config.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or config.CHUNK_OVERLAP

        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n## ", "\n### ", "\n#### ", "\n", ".", "。", "!", "！", "?", "？", " "],
            length_function=len,
        )

    def _build_header(self, metadata: dict) -> str:
        """构造 chunk 的来源标题头：「# 文件名」+「库内相对路径」。

        背景：纯代码/纯英文笔记（如 十大排序/快速排序.md）的正文里没有中文标题，
        导致 BM25 字面匹配不到、dense 也缺少语义锚点，中文提问必然检索失败。
        把标题与路径前置进 chunk 文本后，两路检索同时受益。

        Args:
            metadata: Document.metadata，优先用 rel_path，缺失时回落到 source 文件名

        Returns:
            形如 "# 快速排序\n十大排序/快速排序.md"；信息不足时返回空串
        """
        rel = (metadata or {}).get("rel_path") or ""
        src = (metadata or {}).get("source") or ""
        # 统一为正斜杠，保证 Windows 反斜杠路径也能被 BM25 正常分词
        path_str = str(rel).replace("\\", "/") if rel else Path(src).name
        if not path_str:
            return ""
        return f"# {Path(path_str).stem}\n{path_str}"

    def split_documents(self, documents: list[Document]) -> list[Document]:
        """对 Document 列表执行切片，并为每个 chunk 前置来源标题头。

        逐文档切片（而非整批），确保一个文件切成多片时**每一片**都带标题。
        """
        chunks: list[Document] = []
        for doc in documents:
            header = self._build_header(doc.metadata or {})
            parts = self._splitter.split_documents([doc])
            for c in parts:
                if header and not c.page_content.startswith(header):
                    c.page_content = f"{header}\n\n{c.page_content}"
                chunks.append(c)
        logger.info("切片完成: %d → %d 个片段", len(documents), len(chunks))
        return chunks

    def split_text(self, text: str) -> list[str]:
        """对纯文本执行切片"""
        return self._splitter.split_text(text)


def get_chunker() -> Chunker:
    return Chunker()
