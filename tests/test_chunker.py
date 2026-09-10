# -*- coding: utf-8 -*-
"""chunker 切片单测：验证每个 chunk 都前置「标题 + 库内路径」。

背景：纯代码/纯英文笔记正文里没有中文标题，导致中文提问时
BM25 字面匹配不到、dense 无语义锚点。标题头进 chunk 后两路检索同时受益。
"""

from langchain_core.documents import Document

from knowledge.chunker import Chunker


def test_header_with_rel_path():
    """有 rel_path 时，标题头为「# 文件名」+ 正斜杠相对路径"""
    c = Chunker()
    doc = Document(
        page_content="def quick_sort(arr): pass",
        metadata={"source": r"D:\vault\十大排序\快速排序.md", "rel_path": r"十大排序\快速排序.md"},
    )
    chunks = c.split_documents([doc])
    assert chunks, "应至少切出 1 个 chunk"
    assert chunks[0].page_content.startswith("# 快速排序\n十大排序/快速排序.md\n\n")
    assert "def quick_sort" in chunks[0].page_content


def test_header_fallback_to_filename():
    """无 rel_path 时（legacy docs 索引路径没有该字段），回落到 source 文件名"""
    c = Chunker()
    doc = Document(page_content="正文", metadata={"source": "/tmp/docs/笔记A.md"})
    chunks = c.split_documents([doc])
    assert chunks[0].page_content.startswith("# 笔记A\n笔记A.md\n\n")


def test_every_chunk_has_header():
    """一个文件切成多片时，每一片都要带标题头（不能只有第一片有）"""
    c = Chunker(chunk_size=60, chunk_overlap=0)
    body = "\n".join(f"第{i}行内容内容内容内容内容内容内容内容内容" for i in range(10))
    doc = Document(
        page_content=body,
        metadata={"source": "/vault/目录/长笔记.md", "rel_path": r"目录\长笔记.md"},
    )
    chunks = c.split_documents([doc])
    assert len(chunks) > 1, f"本用例需切成多片，实际 {len(chunks)} 片"
    for ch in chunks:
        assert ch.page_content.startswith("# 长笔记\n目录/长笔记.md\n\n"), ch.page_content[:40]


def test_empty_metadata_no_crash():
    """metadata 为空时不崩溃，且不加任何标题头"""
    c = Chunker()
    doc = Document(page_content="正文", metadata={})
    chunks = c.split_documents([doc])
    assert chunks[0].page_content == "正文"
