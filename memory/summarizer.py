"""对话历史压缩器（滚动摘要 / rolling summary）

解决「上下文无限膨胀」问题：当某个会话的消息数超过阈值时，
把较旧的对话用 LLM 压缩成一段摘要持久化，之后每次只携带：
    system prompt + 摘要 + 最近 N 条原始消息 + 向量检索的相关历史
从而在节省 token 的同时，尽量不丢失早期上下文。
"""

from utils.logger import get_logger

logger = get_logger(__name__)

# 触发压缩的消息数阈值（约 6 轮对话）
COMPRESSION_THRESHOLD = 12
# 压缩后仍保留的最近原始消息条数（与 Agent 的 RECENT_HISTORY_LIMIT 对齐）
KEEP_RECENT = 5

_SUMMARY_SYSTEM = (
    "你是一个对话记忆压缩助手。把对话历史压缩成简洁的中文摘要，"
    "只保留未来对话可能用到的信息：\n"
    "1. 用户关注的话题、正在做的项目\n"
    "2. 重要的结论、决定、待办事项\n"
    "3. 用户的偏好、习惯、个人背景\n"
    "4. 关键的名词、数字、日期\n"
    "要求：150 字以内，直接输出摘要内容，不要任何前缀说明。"
)


def _is_tool_noise(msg: dict) -> bool:
    """判断是否为工具调用的中间结果（应排除在摘要之外）"""
    return msg["role"] == "assistant" and msg["content"].startswith("[")


def compress_if_needed(session_id: str, memory, provider: str = "deepseek",
                       user_key: dict | None = None) -> bool:
    """若会话消息数超过阈值，则触发一次压缩。返回是否发生了压缩。

    失败时静默返回 False，绝不阻塞主流程。
    """
    try:
        if memory.count_messages(session_id) < COMPRESSION_THRESHOLD:
            return False
    except Exception as e:
        logger.warning("统计消息数失败: %s", e)
        return False

    return _build_summary(session_id, memory, provider, user_key)


def _build_summary(session_id: str, memory, provider: str,
                   user_key: dict | None) -> bool:
    """合并旧摘要 + 新增对话，生成新摘要并持久化。"""
    from chatbot.chatbot import chat

    current = memory.get_session_summary(session_id)
    old_summary = current["summary"] if current else ""
    after_id = current["compressed_until_id"] if current else 0

    # 读取 after_id 之后的所有消息（升序）
    messages = memory.get_messages_range(session_id, after_id=after_id, limit=500)
    # 去掉最近 KEEP_RECENT 条，剩下的才压缩（这 KEEP_RECENT 条会作为原始上下文保留）
    if len(messages) <= KEEP_RECENT:
        return False
    to_compress = messages[:-KEEP_RECENT]
    if not to_compress:
        return False

    # 拼成对话文本，跳过工具调用的中间结果
    lines = []
    for m in to_compress:
        if _is_tool_noise(m):
            continue
        role = "用户" if m["role"] == "user" else "助手"
        lines.append(f"{role}：{m['content']}")
    new_dialog = "\n".join(lines)
    if not new_dialog.strip():
        return False

    prompt_parts = [_SUMMARY_SYSTEM]
    if old_summary:
        prompt_parts.append(f"\n已有的旧摘要：\n{old_summary}")
    prompt_parts.append(f"\n新增对话：\n{new_dialog}")
    prompt_parts.append("\n请把旧摘要和新增对话合并，输出一段新的中文摘要。")

    try:
        resp = chat(
            [{"role": "system", "content": "\n".join(prompt_parts)}],
            provider=provider,
            user_key=user_key,
        )
        summary = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning("生成会话摘要失败: %s", e)
        return False

    if not summary:
        return False

    until_id = to_compress[-1]["id"]
    memory.save_session_summary(session_id, summary, until_id)
    logger.info(
        "会话 %s 上下文压缩完成: 压缩 %d 条消息 → 摘要 %d 字",
        session_id, len(to_compress), len(summary),
    )
    return True
