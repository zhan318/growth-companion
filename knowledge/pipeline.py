"""RAG 完整流程 —— 检索 + DeepSeek 生成自然语言答案

index_documents()  加载 → 切片 → 向量化 → 存储
query()            检索 → Prompt → DeepSeek → 答案
"""

import hashlib
import re
import threading
from pathlib import Path

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import ChatOpenAI

from config import OBSIDIAN_COLLECTION, OBSIDIAN_EXCLUDE, OBSIDIAN_VAULT_DIR
from utils.logger import get_logger

from .chunker import Chunker
from .config import config
from .hybrid import invalidate_bm25
from .loader import is_path_excluded, load_directory
from .retriever import get_retriever
from .vector_store import get_vector_store

logger = get_logger(__name__)

# 索引与查询共享同一 Chroma collection，加锁避免并发读写冲突
# （文件监视器在后台线程触发重索引，可能与主请求的 RAG 查询并发）
_obsidian_index_lock = threading.Lock()


# ═══════════════════════════════════════════
#  RAG Prompt 模板
# ═══════════════════════════════════════════

RAG_PROMPT = ChatPromptTemplate.from_messages([
    ("system", (
        "你是一个基于知识库的智能助手。请严格根据以下\"上下文\"中的信息来回答问题。\n"
        "要求：\n"
        "1. 如果上下文中有相关答案，用简洁的中文回答\n"
        "2. 如果上下文与问题不严格匹配但有任何相关内容，请把相关内容如实展示给用户，"
        "并说明\"你的笔记里记录的是 X（而非你问的 Y），是否需要我进一步补充\"——"
        "切勿直接说\"知识库没有\"就结束，也不要凭空编造\n"
        "3. 只有在上下文完全无关时，才明确说\"知识库中没有相关信息\"，且不要编造\n"
        "4. 回答时不要提及\"根据上下文\"、\"根据提供的资料\"等字样，直接给出答案"
    )),
    ("human", (
        "上下文：\n"
        "---\n"
        "{context}\n"
        "---\n"
        "请根据以上上下文回答下面的问题：\n"
        "{question}"
    )),
])


# ═══════════════════════════════════════════
#  LangChain Chain：检索 → 生成
# ═══════════════════════════════════════════

def _format_context(docs):
    """将检索到的 Document 列表拼接为文本（供 knowledge 与 obsidian 共用）"""
    if not docs:
        return "（知识库中暂未找到相关内容）"
    parts = []
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source", "未知")
        parts.append(f"[片段{i} | 来源: {source}]\n{doc.page_content}")
    return "\n\n".join(parts)


def _resolve_default_provider() -> str:
    """取当前实际生效的默认 provider（已考虑 key 是否配置）"""
    from chatbot.chatbot import get_default_provider

    return get_default_provider()


def _build_llm(provider: str = None, temperature: float = 0.3) -> ChatOpenAI:
    """按全项目默认 provider 构建 LangChain ChatOpenAI。

    RAG 生成链路与聊天链路共用 config.LLM_PROVIDER 这一配置源，
    避免「前端选了 GLM、知识库问答却仍调 DeepSeek」的割裂。
    """
    from chatbot.chatbot import MODEL_PRESETS, get_default_provider

    provider = provider or get_default_provider()
    preset = MODEL_PRESETS[provider]
    logger.info("RAG 生成模型: %s (%s)", preset["label"], provider)
    return ChatOpenAI(
        model=preset["default_model"],
        api_key=preset["api_key"],
        base_url=preset["default_base_url"],
        temperature=temperature,
    )


def _build_chain():
    """构建 LCEL Chain：retrieve → context → prompt → llm → output"""
    llm = _build_llm()

    retriever = get_retriever().get_langchain_retriever()

    chain = (
        {"context": retriever | _format_context, "question": RunnablePassthrough()}
        | RAG_PROMPT
        | llm
        | StrOutputParser()
    )

    logger.info("RAG 生成链路初始化完成")
    return chain


# ═══════════════════════════════════════════
#  对外接口（不变）
# ═══════════════════════════════════════════

def index_documents(doc_dir: str | None = None) -> int:
    """索引文档：加载 → 切片 → 向量化 → 存储"""
    doc_dir = doc_dir or config.DOCS_DIR
    logger.info("开始索引: %s", doc_dir)

    docs = load_directory(doc_dir)
    if not docs:
        logger.warning("未找到文档")
        return 0

    chunker = Chunker()
    chunks = chunker.split_documents(docs)
    store = get_vector_store()
    store.add_documents(chunks)
    invalidate_bm25(config.COLLECTION_NAME)
    logger.info("索引完成: %d 个切片", len(chunks))
    return len(chunks)


_chain = None


def query(question: str) -> str:
    """RAG 查询：检索 → DeepSeek 生成自然语言答案（同步版）

    Args:
        question: 用户问题

    Returns:
        基于知识库生成的自然语言回答
    """
    global _chain

    # 首次调用自动索引
    store = get_vector_store()
    if store.count() == 0:
        logger.info("知识库为空，自动索引")
        n = index_documents()
        if n == 0:
            return "知识库中暂无内容，请先往 knowledge/docs/ 目录添加文档"

    # 构建 Chain（首次或 store 重建后）
    if _chain is None:
        _chain = _build_chain()

    try:
        answer = _chain.invoke(question)
        logger.info("RAG 生成完成")
        return answer
    except Exception as e:
        logger.error("RAG 生成失败: %s", e)
        return f"抱歉，处理您的问题时出错了：{e}"


async def query_async(question: str) -> str:
    """RAG 查询（异步版，Agent.arun 使用）。

    Chroma 检索与 LangChain chain.invoke 均为同步实现（无官方 async），
    故用 asyncio.to_thread 放进线程池，避免阻塞事件循环。
    """
    import asyncio
    return await asyncio.to_thread(query, question)


# ═══════════════════════════════════════════
#  Obsidian 知识库：独立 collection，与 knowledge/docs 隔离
# ═══════════════════════════════════════════

def index_obsidian(force: bool = False) -> dict:
    """公共入口：加锁后调用实际索引逻辑，避免与查询并发读写 Chroma 冲突。"""
    with _obsidian_index_lock:
        return _index_obsidian_impl(force)


def _index_obsidian_impl(force: bool = False) -> dict:
    """增量索引 Obsidian vault 到独立 collection。

    - 排除 OBSIDIAN_EXCLUDE 清单中的文件/文件夹（如存放 API Key 的 API.md），
      这些文件永不被向量化，保证隐私不外泄。
    - 按文件 mtime + 确定性 id 实现增量：未变更的文件跳过，变更/新增的更新，
      已删除的文件从向量库移除。force=True 时清空后全量重建。

    Returns:
        dict: {status, indexed_files, chunks, updated, deleted, skipped_excluded}
    """
    vault = OBSIDIAN_VAULT_DIR
    if not vault or not Path(vault).exists():
        return {"status": "error", "message": f"Obsidian vault 未配置或不存在: {vault}"}

    logger.info("开始索引 Obsidian: %s", vault)
    docs = load_directory(vault)

    # 排除隐私文件
    skipped = 0
    kept = []
    vault_path = Path(vault).resolve()
    for d in docs:
        try:
            rel = str(Path(d.metadata["source"]).resolve().relative_to(vault_path))
        except Exception:
            rel = Path(d.metadata["source"]).name
        if is_path_excluded(rel, OBSIDIAN_EXCLUDE):
            skipped += 1
            continue
        # 切片前先补全来源信息：Chunker 据此为每个 chunk 前置「标题 + 库内路径」
        d.metadata["rel_path"] = rel
        kept.append(d)
    docs = kept

    if not docs:
        return {
            "status": "error",
            "message": "vault 内无可索引的笔记（可能全部被排除清单过滤）",
            "skipped_excluded": skipped,
        }

    chunker = Chunker()
    chunks = chunker.split_documents(docs)

    # 为每块生成确定性 id（文件哈希 + 序号）并记录 mtime，支撑增量更新
    store = get_vector_store(OBSIDIAN_COLLECTION)
    desired: dict[str, dict] = {}
    for d in chunks:
        src = Path(d.metadata["source"]).resolve()
        rel = d.metadata["rel_path"]
        file_hash = hashlib.sha1(rel.encode("utf-8")).hexdigest()[:16]
        mtime = src.stat().st_mtime
        d.metadata["doc_id"] = file_hash
        d.metadata["mtime"] = mtime
        info = desired.setdefault(file_hash, {"ids": [], "docs": [], "mtime": mtime})
        idx = len(info["ids"])
        info["ids"].append(f"{file_hash}_{idx}")
        info["docs"].append(d)

    stats = {
        "indexed_files": 0,
        "chunks": 0,
        "updated": 0,
        "deleted": 0,
        "skipped_excluded": skipped,
    }

    if force:
        store.delete_all()
        for info in desired.values():
            store.add_documents_with_ids(info["docs"], info["ids"])
            stats["indexed_files"] += 1
            stats["chunks"] += len(info["ids"])
        stats["status"] = "success"
        invalidate_bm25(OBSIDIAN_COLLECTION)
        logger.info("Obsidian 全量索引完成: %d 文件 / %d 切片", stats["indexed_files"], stats["chunks"])
        return stats

    # 增量：对比已有 mtime
    try:
        existing = store.get(include=["metadatas"]) or {}
    except Exception:
        existing = {}
    exist_ids = existing.get("ids", []) or []
    exist_meta = existing.get("metadatas", []) or []
    old_by_doc: dict[str, list] = {}
    old_mtime: dict[str, float] = {}
    for _id, meta in zip(exist_ids, exist_meta, strict=False):
        doc_id = meta.get("doc_id")
        if not doc_id:
            continue
        old_by_doc.setdefault(doc_id, []).append(_id)
        old_mtime[doc_id] = meta.get("mtime", 0)

    # 删除已不存在的文件
    for doc_id, ids in old_by_doc.items():
        if doc_id not in desired:
            store.delete(ids)
            stats["deleted"] += 1

    # 新增 / 更新
    for doc_id, info in desired.items():
        if doc_id in old_by_doc and old_mtime.get(doc_id) == info["mtime"]:
            # 未变更，跳过
            stats["indexed_files"] += 1
            stats["chunks"] += len(info["ids"])
            continue
        if doc_id in old_by_doc:
            store.delete(old_by_doc[doc_id])
            stats["updated"] += 1
        store.add_documents_with_ids(info["docs"], info["ids"])
        stats["indexed_files"] += 1
        stats["chunks"] += len(info["ids"])

    stats["status"] = "success"
    invalidate_bm25(OBSIDIAN_COLLECTION)
    logger.info(
        "Obsidian 增量索引完成: 新增/更新 %d, 删除 %d, 跳过排除 %d",
        stats["updated"], stats["deleted"], stats["skipped_excluded"],
    )
    return stats


# ═══════════════════════════════════════════
#  关键词兜底：弥补 embedding（all-MiniLM-L6-v2 英文优化）对中文/短查询召回率低
# ═══════════════════════════════════════════

def _extract_keywords(text: str) -> list:
    """提取中英文关键词（去停用词），用于内容弱匹配。

    中文处理：连续中文段按 2/3/4 字 n-gram 滑窗切分，而非整体作单个 token。
    修复漏检：问"输入字体突然变成繁体字怎么切换回来"时，整段 15 字无法与笔记
    内容"变成繁体字：ctrl+shift+f"子串匹配；n-gram 后"繁体字""切换"等词可命中。
    """
    text = (text or "").lower()
    tokens = re.findall(r"[a-z]{2,}", text)
    for seg in re.findall(r"[\u4e00-\u9fa5]+", text):
        n = len(seg)
        for size in (4, 3, 2):
            if n >= size:
                tokens.extend(seg[i:i + size] for i in range(n - size + 1))
    stop = {
        "我们", "你们", "他们", "自己", "什么", "怎么", "如何", "为什么", "哪些", "这个",
        "那个", "这些", "那些", "已经", "可以", "应该", "需要", "知道", "想要", "希望",
        "目前", "没有", "不是", "就是", "还是", "并且", "或者", "关于", "对于", "学习",
        "过程", "遇到", "遇到过", "笔记", "内容", "直接", "记录", "担心", "试试", "告诉",
        "请问", "想问", "我想", "我的", "你的", "有没有", "一下", "一些", "之类", "让我",
        "看看", "帮我", "里面", "它们", "她们", "您",
        "输入", "字体", "变成", "回来", "突然", "请问", "帮我", "一下", "哪些",
    }
    seen = set()
    out = []
    for t in tokens:
        if t in stop or len(t) < 2:
            continue
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _title_overlap(query: str, title: str) -> int:
    """计算 query 与标题字面重叠度（基于 2~3 字中文/英文 n-gram 命中数）。

    不依赖分词库，纯子串匹配——对"提问词"命中"笔记标题"这种小 vault 场景非常有效。
    """
    q = re.sub(r"\s+", "", query or "")
    if not q or not title:
        return 0
    grams = set()
    for n in (2, 3):
        for i in range(len(q) - n + 1):
            grams.add(q[i:i + n])
    for w in re.findall(r"[a-z]{2,}", q.lower()):
        grams.add(w)
    return sum(1 for g in grams if g in title)


def _keyword_fallback(question: str, vault: str, top_n: int = 5) -> list:
    """关键词兜底：扫描 vault 笔记，按 query 与文件标题/内容的字面重叠度召回相关文件的全部 chunks。

    用于弥补 embedding 模型（all-MiniLM-L6-v2，英文优化）对中文/短查询召回率低的问题：
    当用户问"我学程序过程遇到哪些单词"时，semantic search 可能因 embedding 短板漏掉
    《学程序过程遇到的单词释义》这篇笔记，但标题字面重叠会稳定命中它。
    """
    from .loader import load_directory

    vault_path = Path(vault).resolve()
    try:
        docs = load_directory(vault)
    except Exception:
        return []

    # 按文件分组（文件名即标题，整篇召回更有意义）
    file_groups: dict = {}
    for d in docs:
        try:
            rel = str(Path(d.metadata["source"]).resolve().relative_to(vault_path))
        except Exception:
            rel = Path(d.metadata["source"]).name
        if is_path_excluded(rel, OBSIDIAN_EXCLUDE):
            continue
        file_groups.setdefault(rel, []).append(d)

    keywords = _extract_keywords(question)
    scored = []
    for rel, chunks in file_groups.items():
        title = Path(rel).stem
        score = float(_title_overlap(question, title))        # 标题命中权重最高
        if keywords:
            content_blob = "\n".join(c.page_content for c in chunks)
            hits = sum(1 for kw in keywords if kw in content_blob)
            if hits:
                score += min(0.3 * hits, 1.5)                 # 内容弱匹配：命中数加权（n-gram 后多词命中拉开差距）
        if score > 0:
            scored.append((score, chunks))

    scored.sort(key=lambda x: x[0], reverse=True)
    result = []
    for _, chunks in scored[:top_n]:
        result.extend(chunks)
    return result


def get_vault_metadata() -> dict:
    """扫描 Obsidian vault 元数据：笔记数量、文件夹结构、最近修改文件。
    供 Agent 构建 system prompt 时注入，让 LLM 知道笔记库有「什么话题」。
    不读取文件内容（隐私安全），仅统计文件名/路径/mtime。
    """
    vault = OBSIDIAN_VAULT_DIR
    result = {
        "configured": bool(vault and Path(vault).exists()),
        "vault_path": vault or "",
        "note_count": 0,
        "folders": [],
        "recent_notes": [],
    }
    if not result["configured"]:
        return result
    vault_path = Path(vault).resolve()
    try:
        all_md = []
        for f in vault_path.rglob("*.md"):
            rel = str(f.relative_to(vault_path))
            if is_path_excluded(rel, OBSIDIAN_EXCLUDE) or f.name.startswith("."):
                continue
            all_md.append(f)
        result["note_count"] = len(all_md)
        # 文件夹（去重、排序）
        folders = sorted(set(
            str(f.parent.relative_to(vault_path)) if str(f.parent.relative_to(vault_path)) != "." else "根目录"
            for f in all_md
        ))
        result["folders"] = folders
        # 最近修改的笔记（最多 8 篇）
        recent = sorted(all_md, key=lambda f: f.stat().st_mtime, reverse=True)[:8]
        result["recent_notes"] = [
            {
                "name": f.stem,
                "folder": str(f.parent.relative_to(vault_path)) if str(f.parent.relative_to(vault_path)) != "." else "根目录",
                "mtime": f.stat().st_mtime,
            }
            for f in recent
        ]
    except Exception as e:
        logger.warning("扫描 vault 元数据失败: %s", e)
        result["error"] = str(e)
    return result


# Obsidian RAG chain 缓存（避免每次 query 都新建 ChatOpenAI）
# _obsidian_llm_provider 记录缓存 LLM 对应的 provider：默认 provider 变了就自动重建
_obsidian_chain = None
_obsidian_llm = None
_obsidian_llm_provider = None


def retrieve_obsidian(question: str, k: int | None = None):
    """Obsidian 检索公共路径：dense 语义检索 + BM25 稀疏检索 → RRF 融合。

    返回 (dense_docs, bm25_docs, merged_docs)，供 query 与 eval 共用，
    避免多处重复检索逻辑（此前 query_obsidian / eval_retrieval / eval_generation 各写一份）。

    dense_docs / bm25_docs 供评测分层统计（单独命中率 vs 融合命中率），
    merged_docs 是最终送 LLM 的上下文。
    """
    from .hybrid import fuse_documents, get_bm25_retriever

    store = get_vector_store(OBSIDIAN_COLLECTION)
    top_k = k or config.RETRIEVE_TOP_K

    dense_docs = store.search(question, k=top_k)
    bm25_docs = get_bm25_retriever(store).search(question, k=top_k)
    merged = fuse_documents(dense_docs, bm25_docs, top_n=top_k)
    return dense_docs, bm25_docs, merged


def query_obsidian(question: str, k: int | None = None) -> str:
    """在 Obsidian 独立 collection 上做 RAG 检索并生成答案（同步版）。

    检索策略：dense 语义检索 + BM25 稀疏检索，经 RRF 融合后送 LLM，
    避免中文短查询因 embedding 短板漏掉明显相关的笔记。
    注意：被排除清单过滤的文件不会进入向量库，因此检索到的内容均不含隐私文件。
    """
    global _obsidian_chain, _obsidian_llm, _obsidian_llm_provider

    store = get_vector_store(OBSIDIAN_COLLECTION)
    if store.count() == 0:
        return "Obsidian 知识库尚未索引，请先调用 POST /obsidian/index 进行索引。"

    # 混合检索：dense 语义检索 + BM25 稀疏检索 → RRF 融合
    _, _, docs = retrieve_obsidian(question, k)

    if not docs:
        return "（Obsidian 中未找到相关内容）"

    context = _format_context(docs)
    provider = _resolve_default_provider()
    if _obsidian_llm is None or _obsidian_llm_provider != provider:
        _obsidian_llm = _build_llm(provider)
        _obsidian_llm_provider = provider
        _obsidian_chain = None  # LLM 变了，chain 也要重建
    if _obsidian_chain is None:
        _obsidian_chain = RAG_PROMPT | _obsidian_llm | StrOutputParser()
    try:
        answer = _obsidian_chain.invoke(
            {"context": context, "question": question}
        )
        return answer
    except Exception as e:
        logger.error("Obsidian RAG 生成失败: %s", e)
        return f"抱歉，处理您的问题时出错了：{e}"


async def query_obsidian_async(question: str, k: int | None = None) -> str:
    """在 Obsidian 独立 collection 上做 RAG 检索并生成答案（异步版，Agent.arun 使用）。

    与 query_obsidian 逻辑一致；Chroma/LCEL 均为同步实现，用 asyncio.to_thread 放入线程池。
    """
    import asyncio
    return await asyncio.to_thread(query_obsidian, question, k)
