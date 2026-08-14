"""模拟面试工具 —— 从 Obsidian 疑难总结中提取问题，供 Agent 进行模拟面试"""

from pathlib import Path

from tools import registry
from utils.logger import get_logger

logger = get_logger(__name__)


def _get_quiz_summary_dir() -> Path | None:
    """获取疑难总结目录路径"""
    from config import OBSIDIAN_VAULT_DIR

    if not OBSIDIAN_VAULT_DIR:
        return None
    vault = Path(OBSIDIAN_VAULT_DIR)
    quiz_dir = vault / "AI学习" / "疑难总结"
    return quiz_dir if quiz_dir.exists() else None


def _parse_questions(content: str) -> list[dict]:
    """从 Markdown 内容中提取问题，按主题分组。

    返回: [{"topic": "Python 对象与 is 运算符", "questions": ["问题1", ...]}, ...]
    """
    topics = []
    current_topic = ""
    current_questions: list[str] = []

    lines = content.split("\n")
    for line in lines:
        stripped = line.strip()
        # 匹配 ## 或 # 标题作为主题，以及「主题：xxx」格式的行
        is_topic = (
            (stripped.startswith("## ") or stripped.startswith("# "))
            and not stripped.startswith("### ")
        ) or stripped.startswith("主题：")

        if is_topic:
            if current_topic and current_questions:
                topics.append({
                    "topic": current_topic,
                    "questions": current_questions,
                })
            # 去掉 # 号和空格
            current_topic = stripped.lstrip("#").strip()
            current_questions = []
        # 匹配 - 开头的列表项作为问题（支持中英文问号）
        elif line.strip().startswith("- ") and ("?" in line or "？" in line):
            q = line.strip()[2:].strip()
            if len(q) > 10:  # 过滤太短的
                current_questions.append(q)

    # 最后一个 topic
    if current_topic and current_questions:
        topics.append({
            "topic": current_topic,
            "questions": current_questions,
        })

    return topics


@registry.register(
    description=(
        "【面试模式主入口】开始/继续一场模拟面试。"
        "调用本工具就等于立刻出题，topic 是用户给的面试方向（可为空，按笔记库自动选题）。"
        "当用户说「模拟面试」「考考我」或进入面试模式输入主题时立即调用。"
    )
)
def mock_interview(topic: str = "", index: int = 0) -> str:
    """从疑难总结中获取面试问题。

    Args:
        topic: 面试主题关键词，如 "Python"、"并发"、"RAG"、"对象模型"、"排序" 等。
               空字符串表示返回所有主题。支持模糊匹配。
        index: 题号索引（0 = 第 1 题），用于"一题一答"模式。
               大于题库长度时返回"题库已答完"提示。

    Returns:
        index == 0 且 topic 为空：格式化所有主题的题目列表（兼容旧调用）
        index > 0 或单题模式：返回单题
    """
    quiz_dir = _get_quiz_summary_dir()
    if quiz_dir is None:
        return "未找到疑难总结目录（请确认 Obsidian vault 中有 AI学习/疑难总结/ 文件夹）。"

    # 读取所有 .md 文件（排除时间线）
    md_files = sorted(
        [f for f in quiz_dir.glob("*.md") if f.name != "时间线.md"],
        reverse=True,  # 最新的在前
    )

    if not md_files:
        return "疑难总结目录中暂无笔记。"

    all_topics: list[dict] = []
    for f in md_files:
        try:
            content = f.read_text(encoding="utf-8")
            all_topics.extend(_parse_questions(content))
        except Exception as e:
            logger.warning("读取 %s 失败: %s", f.name, e)

    if not all_topics:
        return "未能从疑难总结中提取到问题。"

    # 按主题筛选
    if topic:
        keyword = topic.lower()
        all_topics = [
            t for t in all_topics
            if keyword in t["topic"].lower()
        ]
        if not all_topics:
            available = _list_all_topics(md_files)
            return (
                f"未找到与「{topic}」相关的主题。\n"
                f"疑难总结中的主题有：\n{available}"
            )

    # 扁平化所有问题（按主题顺序），用于按 index 单题取出
    flat: list[dict] = []  # [{"topic": str, "question": str}, ...]
    for t in all_topics:
        for q in t["questions"]:
            flat.append({"topic": t["topic"], "question": q})

    # 单题模式（Agent 兜底走这条）
    if 0 <= index < len(flat):
        item = flat[index]
        return (
            f"## 面试题（第 {index + 1} 题 / 共 {len(flat)} 题）\n\n"
            f"**主题**：{item['topic']}\n\n"
            f"**问题**：{item['question']}"
        )
    if index >= len(flat) and flat:
        return f"题库已答完（共 {len(flat)} 题）。你可以换个主题或说「重新开始」。"

    # 格式化输出
    lines = ["# 🎯 模拟面试问题\n"]
    total = 0
    for t in all_topics:
        lines.append(f"## {t['topic']}")
        for j, q in enumerate(t["questions"], 1):
            lines.append(f"{j}. {q}")
            total += 1
        lines.append("")  # 主题间空行

    lines.append(f"---\n共 {len(all_topics)} 个主题，{total} 道题")
    return "\n".join(lines)


def _list_all_topics(md_files: list[Path]) -> str:
    """列出所有疑难总结中的主题"""
    topics = set()
    for f in md_files:
        try:
            content = f.read_text(encoding="utf-8")
            for line in content.split("\n"):
                if line.startswith("## ") and not line.startswith("### "):
                    topics.add(line[3:].strip())
        except Exception:
            pass
    return "\n".join(f"- {t}" for t in sorted(topics)) if topics else "（暂无）"
