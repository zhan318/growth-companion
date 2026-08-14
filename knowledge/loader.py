"""文档加载器 —— 基于 LangChain Loader"""

from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document

from utils.logger import get_logger

logger = get_logger(__name__)


class MarkdownLoader:
    """Markdown 文件加载"""

    def __init__(self, file_path: str):
        self.file_path = file_path

    def load(self) -> list[Document]:
        path = Path(self.file_path)
        content = path.read_text(encoding="utf-8", errors="ignore")
        return [Document(
            page_content=content,
            metadata={"source": str(path), "file_type": "md"},
        )]


# 加载器映射
_LOADER_MAP = {
    ".txt": TextLoader,
    ".md": MarkdownLoader,
    ".pdf": PyPDFLoader,
}


def load_document(file_path: str) -> list[Document]:
    """加载单个文件，自动识别格式"""
    suffix = Path(file_path).suffix.lower()
    loader_cls = _LOADER_MAP.get(suffix)
    if loader_cls is None:
        raise ValueError(f"不支持的文件格式: {suffix}，支持: {list(_LOADER_MAP.keys())}")

    loader = loader_cls(file_path)
    docs = loader.load()
    logger.info("已加载: %s → %d 页/段", file_path, len(docs))
    return docs


def load_directory(doc_dir: str) -> list[Document]:
    """递归加载目录下所有支持的文档"""
    all_docs: list[Document] = []
    base = Path(doc_dir)
    if not base.exists():
        logger.warning("目录不存在: %s", doc_dir)
        return all_docs

    for file_path in sorted(base.rglob("*")):
        if file_path.suffix.lower() not in _LOADER_MAP:
            continue
        if file_path.name.startswith("."):
            continue
        try:
            docs = load_document(str(file_path))
            all_docs.extend(docs)
        except Exception as e:
            logger.error("加载失败 %s: %s", file_path, e)

    logger.info("共加载 %d 个文档片段", len(all_docs))
    return all_docs


def is_path_excluded(rel_path: str, excludes) -> bool:
    """判断相对路径是否命中排除清单。

    匹配规则（任一满足即排除）：
      - 文件名等于某项（如 "API.md"）
      - 相对路径等于某项（如 "secret/api.md"）
      - 路径中包含某项作为文件夹名（如 ".trash"）
    """
    p = Path(rel_path)
    base = p.name
    parts = set(p.parts)
    return any(ex in (base, rel_path) or ex in parts for ex in excludes)
