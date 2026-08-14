"""面试记录归档：把一次模拟面试的对话整理成结构化 Markdown，写入 Obsidian

下次面试前，用户可以让 Agent 直接读取「模拟面试/面试记录/日期.md」回看上次的表现。
"""

from datetime import datetime
from pathlib import Path

from utils.logger import get_logger

logger = get_logger(__name__)

# Obsidian vault 内的归档目录（固定相对路径，天然限制在 vault 内）
_INTERVIEW_DIR = "模拟面试/面试记录"
# 薄弱点画像输出文件（每次生成覆盖更新，代表"当前"画像）
_WEAKNESS_FILE = "模拟面试/薄弱点画像.md"
# 单份面试记录最多喂给 LLM 的字符数（防超长）
_MAX_RECORD_CHARS = 2000
# 最多分析的面试记录份数（取最近的）
_MAX_RECORDS = 10

_WEAKNESS_PROMPT = (
    "你是一位面试分析师。以下是用户最近几次模拟面试的记录。\n"
    "请分析并输出一份「薄弱点画像」Markdown，格式如下：\n"
    "```\n"
    "## 反复出现的薄弱主题\n"
    "1. **（主题名）**（出现 N 次）\n"
    "   - 具体表现：……\n"
    "   - 复习建议：……\n"
    "\n"
    "## 整体趋势\n"
    "（进步 / 退步 / 稳定，一句话 + 依据）\n"
    "\n"
    "## 优先级复习清单\n"
    "- [ ] 1. ……（紧急程度：高）\n"
    "- [ ] 2. ……（紧急程度：中）\n"
    "```\n"
    "要求：\n"
    "- 只分析记录里真实出现的内容，不要编造\n"
    "- 薄弱主题按出现次数排序；没有明显薄弱点就如实说\n"
    "- 直接输出 Markdown 内容，不要额外解释\n"
)

# 单次面试的薄弱点分析提示词（保存时附加到面试记录中）
_SINGLE_WEAKNESS_PROMPT = (
    "你是一位面试分析师。以下是用户刚刚完成的一次模拟面试的问答记录。\n"
    "请分析本次面试，输出「薄弱点分析」Markdown，格式如下：\n"
    "```\n"
    "## 薄弱点分析\n"
    "1. **（薄弱主题）**\n"
    "   - 具体表现：……（引用本次回答中的实例）\n"
    "   - 改进建议：……\n"
    "\n"
    "## 待加强清单\n"
    "- [ ] 1. ……（紧急程度：高）\n"
    "```\n"
    "要求：\n"
    "- 只基于本次对话真实内容，不要编造；答得好的题不用列\n"
    "- 没有明显薄弱点就写「本次无明显薄弱点，继续保持」\n"
    "- 直接输出 Markdown 内容，不要额外解释\n"
)

_SUMMARY_PROMPT = (
    "你是一位面试记录整理助手。下面是用户与模拟面试 AI 的完整对话（面试官 vs 我）。\n"
    "请把对话整理成结构化的 Markdown 面试记录，格式如下：\n"
    "```\n"
    "## 面试主题\n"
    "（一句话概括这次面试的主题 / 考察范围）\n"
    "\n"
    "## 问答回顾\n"
    "### Q1. （面试官的问题）\n"
    "- **我的回答**：（用户当时的回答）\n"
    "- **点评/要点**：（这道题考察什么、答得如何、改进点）\n"
    "\n"
    "### Q2. （面试官的问题）\n"
    "- **我的回答**：\n"
    "- **点评/要点**：\n"
    "\n"
    "## 本次总结\n"
    "（2-3 句：整体表现、最需要注意的地方）\n"
    "```\n"
    "要求：\n"
    "- 只保留「面试官提问 → 我回答」的问答对，省略寒暄和闲聊\n"
    "- 点评要具体、有指导价值，不要空话\n"
    "- 直接输出整理好的 Markdown 内容，不要额外解释\n"
)


def _load_session_messages(memory, session_id: str) -> list[dict]:
    """读取会话的用户/助手消息，过滤工具调用噪音（[tool_name] 开头）。"""
    history = memory.load_history(session_id, limit=500)
    messages = []
    for m in history:
        if m["role"] == "assistant" and m["content"].startswith("["):
            continue  # 工具调用的中间结果，不是面试问答
        messages.append({"role": m["role"], "content": m["content"]})
    return messages


def _write_record_file(record: str) -> dict:
    """把整理好的记录写入 Obsidian 面试记录目录（同步/异步共用）。

    Returns:
        {"ok": True, "path": str, "filename": str, "preview": str}
        or {"ok": False, "error": str}
    """
    from config import OBSIDIAN_VAULT_DIR

    if not OBSIDIAN_VAULT_DIR:
        return {"ok": False, "error": "Obsidian vault 未配置（请设置 OBSIDIAN_VAULT_DIR）。"}

    vault = Path(OBSIDIAN_VAULT_DIR)
    target_dir = vault / _INTERVIEW_DIR
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return {"ok": False, "error": f"无法创建归档目录: {e}"}

    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"{today}.md"
    filepath = target_dir / filename

    block = (
        f"\n\n---\n\n"
        f"# 模拟面试记录 · {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"{record}\n"
    )

    try:
        existed = filepath.exists()
        with open(filepath, "a", encoding="utf-8") as f:
            # 新建文件时去掉开头的空行；追加时正常写
            f.write(block.lstrip("\n") if not existed else block)
    except Exception as e:
        return {"ok": False, "error": f"写入笔记失败: {e}"}

    rel_path = str(filepath.relative_to(vault))
    logger.info("面试记录已归档: %s（%s）", rel_path, "追加" if existed else "新建")
    return {
        "ok": True,
        "path": rel_path,
        "filename": filename,
        "preview": record[:200],
    }


def save_interview_record(session_id: str, memory, provider: str = "deepseek") -> dict:
    """归档一次面试，写入 Obsidian。

    Returns:
        {"ok": True, "path": str, "filename": str, "preview": str}
        or {"ok": False, "error": str}
    """
    from config import OBSIDIAN_VAULT_DIR

    if not OBSIDIAN_VAULT_DIR:
        return {"ok": False, "error": "Obsidian vault 未配置（请设置 OBSIDIAN_VAULT_DIR）。"}

    messages = _load_session_messages(memory, session_id)
    if len(messages) < 2:
        return {"ok": False, "error": "会话内容太少，没有可归档的面试问答。"}

    record = _build_record(messages, provider)
    if not record:
        # 降级：LLM 整理失败时保存原始问答（保证记录不丢失）
        logger.warning("LLM 整理失败，降级保存原始问答（session=%s）", session_id)
        lines = ["## 问答回顾（原始记录，未经 LLM 整理）\n"]
        for m in messages:
            role = "面试官" if m["role"] == "assistant" else "我"
            lines.append(f"### {role}\n{m['content']}\n")
        record = "\n".join(lines)

    return _write_record_file(record)


async def save_interview_record_async(session_id: str, memory, provider: str = "deepseek") -> dict:
    """异步版：归档一次面试，写入 Obsidian（LLM 调用不阻塞事件循环）。

    Returns:
        与 save_interview_record 相同结构
    """
    from config import OBSIDIAN_VAULT_DIR

    if not OBSIDIAN_VAULT_DIR:
        return {"ok": False, "error": "Obsidian vault 未配置（请设置 OBSIDIAN_VAULT_DIR）。"}

    messages = _load_session_messages(memory, session_id)
    if len(messages) < 2:
        return {"ok": False, "error": "会话内容太少，没有可归档的面试问答。"}

    record = await _build_record_async(messages, provider)
    if not record:
        # 降级：LLM 整理失败时保存原始问答（保证记录不丢失）
        logger.warning("LLM 整理失败（异步），降级保存原始问答（session=%s）", session_id)
        lines = ["## 问答回顾（原始记录，未经 LLM 整理）\n"]
        for m in messages:
            role = "面试官" if m["role"] == "assistant" else "我"
            lines.append(f"### {role}\n{m['content']}\n")
        record = "\n".join(lines)

    return _write_record_file(record)


def _dialog_from_messages(messages: list[dict]) -> str:
    """把会话消息转成「面试官/我：内容」的对话文本（同步/异步共用）"""
    lines = []
    for m in messages:
        role = "面试官" if m["role"] == "assistant" else "我"
        lines.append(f"{role}：{m['content']}")
    return "\n".join(lines)


def _build_record(messages: list[dict], provider: str = "deepseek") -> str | None:
    """调用 LLM 把对话整理成结构化面试记录。失败返回 None。"""
    from chatbot.chatbot import chat

    dialog = _dialog_from_messages(messages)

    try:
        resp = chat(
            [{"role": "system", "content": _SUMMARY_PROMPT},
             {"role": "user", "content": f"对话内容：\n{dialog}"}],
            provider=provider,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning("面试记录整理失败: %s", e)
        return None


async def _build_record_async(messages: list[dict], provider: str = "deepseek") -> str | None:
    """异步版：调用 LLM 把对话整理成结构化面试记录。失败返回 None。"""
    from chatbot.chatbot import achat

    dialog = _dialog_from_messages(messages)

    try:
        resp = await achat(
            [{"role": "system", "content": _SUMMARY_PROMPT},
             {"role": "user", "content": f"对话内容：\n{dialog}"}],
            provider=provider,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning("面试记录整理异步失败: %s", e)
        return None


def analyze_single_session(session_id: str, memory, provider: str = "deepseek") -> str | None:
    """分析单次面试的薄弱点（LLM 逐题判断回答质量）。

    Args:
        session_id: 面试会话 ID
        memory: Memory 实例
        provider: LLM provider

    Returns:
        薄弱点分析 Markdown 字符串；失败返回 None（不阻塞保存主流程）
    """
    from chatbot.chatbot import chat

    messages = _load_session_messages(memory, session_id)
    if len(messages) < 2:
        return None

    lines = []
    for m in messages:
        role = "面试官" if m["role"] == "assistant" else "我"
        lines.append(f"{role}：{m['content']}")
    dialog = "\n".join(lines)[:_MAX_RECORD_CHARS * 2]

    try:
        resp = chat(
            [{"role": "system", "content": _SINGLE_WEAKNESS_PROMPT},
             {"role": "user", "content": f"本次面试对话：\n{dialog}"}],
            provider=provider,
        )
        content = (resp.choices[0].message.content or "").strip()
        return content or None
    except Exception as e:
        logger.warning("单次面试薄弱点分析失败: %s", e)
        return None


async def analyze_single_session_async(session_id: str, memory, provider: str = "deepseek") -> str | None:
    """异步版：分析单次面试的薄弱点（不阻塞事件循环）。失败返回 None。"""
    from chatbot.chatbot import achat

    messages = _load_session_messages(memory, session_id)
    if len(messages) < 2:
        return None

    lines = []
    for m in messages:
        role = "面试官" if m["role"] == "assistant" else "我"
        lines.append(f"{role}：{m['content']}")
    dialog = "\n".join(lines)[:_MAX_RECORD_CHARS * 2]

    try:
        resp = await achat(
            [{"role": "system", "content": _SINGLE_WEAKNESS_PROMPT},
             {"role": "user", "content": f"本次面试对话：\n{dialog}"}],
            provider=provider,
        )
        content = (resp.choices[0].message.content or "").strip()
        return content or None
    except Exception as e:
        logger.warning("单次面试薄弱点分析异步失败: %s", e)
        return None


def save_interview_record_with_weakness(session_id: str, memory, provider: str = "deepseek") -> dict:
    """归档一次面试（含薄弱点分析章节），写入 Obsidian。

    相比 save_interview_record：在记录末尾附加「薄弱点分析」章节。
    薄弱点分析失败时不阻塞保存（降级为无分析章节）。

    Returns:
        与 save_interview_record 相同结构；ok=False 时 error 说明原因
    """
    result = save_interview_record(session_id, memory, provider)
    if not result.get("ok"):
        return result

    # 附加薄弱点分析（失败降级：记录已保存，仅提示）
    weakness = analyze_single_session(session_id, memory, provider)
    if weakness:
        try:
            from config import OBSIDIAN_VAULT_DIR
            filepath = Path(OBSIDIAN_VAULT_DIR) / result["path"]
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(f"\n{weakness}\n")
            result["preview"] = (result.get("preview") or "") + "…（含薄弱点分析）"
            result["has_weakness"] = True
            logger.info("薄弱点分析已附加: %s", result["path"])
        except Exception as e:
            logger.warning("薄弱点分析写入失败（记录已保存）: %s", e)
            result["has_weakness"] = False
    else:
        result["has_weakness"] = False

    return result


async def save_interview_record_with_weakness_async(session_id: str, memory, provider: str = "deepseek") -> dict:
    """异步版：归档一次面试（含薄弱点分析章节），写入 Obsidian（不阻塞事件循环）。

    薄弱点分析失败时不阻塞保存（降级为无分析章节）。
    """
    result = await save_interview_record_async(session_id, memory, provider)
    if not result.get("ok"):
        return result

    # 附加薄弱点分析（失败降级：记录已保存，仅提示）
    weakness = await analyze_single_session_async(session_id, memory, provider)
    if weakness:
        try:
            from config import OBSIDIAN_VAULT_DIR
            filepath = Path(OBSIDIAN_VAULT_DIR) / result["path"]
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(f"\n{weakness}\n")
            result["preview"] = (result.get("preview") or "") + "…（含薄弱点分析）"
            result["has_weakness"] = True
            logger.info("薄弱点分析已附加（异步）: %s", result["path"])
        except Exception as e:
            logger.warning("薄弱点分析写入失败（记录已保存）: %s", e)
            result["has_weakness"] = False
    else:
        result["has_weakness"] = False

    return result


def _load_records() -> tuple[Path, list[str]]:
    """读取面试记录目录下的所有记录文件，返回 (vault路径, 按日期排序的正文列表)。"""
    from config import OBSIDIAN_VAULT_DIR

    if not OBSIDIAN_VAULT_DIR:
        return Path(), []
    record_dir = Path(OBSIDIAN_VAULT_DIR) / _INTERVIEW_DIR
    if not record_dir.is_dir():
        return Path(OBSIDIAN_VAULT_DIR), []
    files = sorted(record_dir.glob("*.md"), reverse=True)[:_MAX_RECORDS]
    contents = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
            contents.append(text[:_MAX_RECORD_CHARS])
        except Exception as e:
            logger.warning("读取面试记录 %s 失败: %s", f.name, e)
    return Path(OBSIDIAN_VAULT_DIR), contents


def build_weakness_profile(provider: str = "deepseek") -> dict:
    """分析所有面试记录，生成「薄弱点画像」并写入 Obsidian。

    Returns:
        {"ok": True, "path": str, "preview": str, "record_count": int}
        or {"ok": False, "error": str}
    """
    from chatbot.chatbot import chat

    vault, records = _load_records()
    if not vault:
        return {"ok": False, "error": "Obsidian vault 未配置（请设置 OBSIDIAN_VAULT_DIR）。"}
    if not records:
        return {"ok": False, "error": "还没有面试记录，先保存几次面试再生成画像吧。"}

    materials = "\n\n===== 记录分隔 =====\n\n".join(
        f"【第 {i + 1} 份记录】\n{r}" for i, r in enumerate(records)
    )

    try:
        resp = chat(
            [{"role": "system", "content": _WEAKNESS_PROMPT},
             {"role": "user", "content": f"面试记录：\n{materials}"}],
            provider=provider,
        )
        profile = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning("薄弱点画像生成失败: %s", e)
        return {"ok": False, "error": "画像生成失败，请稍后重试。"}

    if not profile:
        return {"ok": False, "error": "画像内容为空，请重试。"}

    filepath = vault / _WEAKNESS_FILE
    try:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        content = (
            f"# 面试薄弱点画像\n\n"
            f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} ｜ "
            f"分析 {len(records)} 份面试记录\n\n"
            f"{profile}\n"
        )
        filepath.write_text(content, encoding="utf-8")
    except Exception as e:
        return {"ok": False, "error": f"写入笔记失败: {e}"}

    rel_path = str(filepath.relative_to(vault))
    logger.info("薄弱点画像已生成: %s（基于 %d 份记录）", rel_path, len(records))
    return {
        "ok": True,
        "path": rel_path,
        "preview": profile[:200],
        "record_count": len(records),
    }


async def build_weakness_profile_async(provider: str = "deepseek") -> dict:
    """异步版：分析所有面试记录，生成「薄弱点画像」并写入 Obsidian（不阻塞事件循环）。

    Returns:
        与 build_weakness_profile 相同结构
    """
    from chatbot.chatbot import achat

    vault, records = _load_records()
    if not vault:
        return {"ok": False, "error": "Obsidian vault 未配置（请设置 OBSIDIAN_VAULT_DIR）。"}
    if not records:
        return {"ok": False, "error": "还没有面试记录，先保存几次面试再生成画像吧。"}

    materials = "\n\n===== 记录分隔 =====\n\n".join(
        f"【第 {i + 1} 份记录】\n{r}" for i, r in enumerate(records)
    )

    try:
        resp = await achat(
            [{"role": "system", "content": _WEAKNESS_PROMPT},
             {"role": "user", "content": f"面试记录：\n{materials}"}],
            provider=provider,
        )
        profile = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning("薄弱点画像生成异步失败: %s", e)
        return {"ok": False, "error": "画像生成失败，请稍后重试。"}

    if not profile:
        return {"ok": False, "error": "画像内容为空，请重试。"}

    filepath = vault / _WEAKNESS_FILE
    try:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        content = (
            f"# 面试薄弱点画像\n\n"
            f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} ｜ "
            f"分析 {len(records)} 份面试记录\n\n"
            f"{profile}\n"
        )
        filepath.write_text(content, encoding="utf-8")
    except Exception as e:
        return {"ok": False, "error": f"写入笔记失败: {e}"}

    rel_path = str(filepath.relative_to(vault))
    logger.info("薄弱点画像已生成（异步）: %s（基于 %d 份记录）", rel_path, len(records))
    return {
        "ok": True,
        "path": rel_path,
        "preview": profile[:200],
        "record_count": len(records),
    }
