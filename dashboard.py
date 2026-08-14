"""数据看板统计：聚合知识库、面试、MBTI、会话等使用数据"""

from pathlib import Path

from utils.logger import get_logger

logger = get_logger(__name__)

_INTERVIEW_DIR = "模拟面试/面试记录"


def count_interview_records(vault: str) -> int:
    """统计面试记录文件数。"""
    if not vault:
        return 0
    record_dir = Path(vault) / _INTERVIEW_DIR
    if not record_dir.is_dir():
        return 0
    return len(list(record_dir.glob("*.md")))


def get_stats(memory, user_id: int) -> dict:
    """聚合用户的使用数据，返回看板所需统计。

    Returns:
        {"notes_count", "interview_count", "mbti_count", "session_count", "mbti_history"}
    """
    from config import OBSIDIAN_VAULT_DIR

    # 笔记数：复用 vault 元数据扫描（已排除 API.md 等隐私文件）
    notes_count = 0
    try:
        from knowledge.pipeline import get_vault_metadata
        meta = get_vault_metadata()
        notes_count = meta.get("note_count", 0) if meta.get("configured") else 0
    except Exception as e:
        logger.warning("获取笔记数失败: %s", e)

    interview_count = count_interview_records(OBSIDIAN_VAULT_DIR)

    mbti_count = memory.count_mbti_results(user_id)
    sessions = memory.get_user_sessions(user_id)
    mbti_history = memory.get_mbti_history(user_id, limit=10)

    return {
        "notes_count": notes_count,
        "interview_count": interview_count,
        "mbti_count": mbti_count,
        "session_count": len(sessions),
        "mbti_history": mbti_history,
    }
