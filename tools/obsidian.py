"""Obsidian 知识库工具 —— 检索、读取与写入用户个人笔记（遵守排除清单）"""

from pathlib import Path

from tools import registry
from utils.logger import get_logger

logger = get_logger(__name__)

MAX_RESULT_LENGTH = 2000
MAX_NOTE_LENGTH = 4000


def _resolve_note(note: str) -> Path | None:
    """将笔记名/路径解析为 vault 内的绝对路径。

    解析顺序：
      1. 绝对路径且文件存在
      2. 相对 vault 根的路径存在
      3. 按文件名（stem）在 vault 内递归查找 .md
    """
    from config import OBSIDIAN_VAULT_DIR

    vault = OBSIDIAN_VAULT_DIR
    if not vault:
        return None
    vault_path = Path(vault).resolve()
    p = Path(note)

    # 1. 绝对路径
    if p.is_absolute() and p.exists():
        return p
    # 2. 相对 vault 的路径
    rp = vault_path / note
    if rp.exists():
        return rp
    # 3. 按文件名查找
    target = p.stem if p.suffix else note
    matches = [
        f for f in vault_path.rglob("*.md")
        if f.stem == target and not f.name.startswith(".")
    ]
    if matches:
        return matches[0]
    return None


@registry.register(
    description="在用户的 Obsidian 个人知识库中检索并回答关于其笔记内容的问题"
                "（如学习方法、项目笔记、读书摘抄、个人资料等）。"
                "当用户询问自己的笔记、个人知识、或 vault 中的主题时使用。"
                "它与 knowledge_search 是两套独立的知识库，不要混用。"
)
def search_obsidian_notes(query: str) -> str:
    """在 Obsidian 知识库中语义检索并生成答案（同步版）。

    Args:
        query: 用户的问题或查询关键词
    """
    logger.info("Obsidian 检索工具被调用: %s", query)
    from knowledge.pipeline import query_obsidian

    result = query_obsidian(query)
    if len(result) > MAX_RESULT_LENGTH:
        result = result[:MAX_RESULT_LENGTH] + "\n\n[回答过长已截断]"
    return result


@registry.register_async(
    description="在用户的 Obsidian 个人知识库中检索并回答关于其笔记内容的问题"
                "（如学习方法、项目笔记、读书摘抄、个人资料等）。"
                "当用户询问自己的笔记、个人知识、或 vault 中的主题时使用。"
                "它与 knowledge_search 是两套独立的知识库，不要混用。"
)
async def search_obsidian_notes_async(query: str) -> str:
    """在 Obsidian 知识库中语义检索并生成答案（异步版，Agent.arun 使用）。

    Args:
        query: 用户的问题或查询关键词
    """
    logger.info("Obsidian 检索工具被调用(异步): %s", query)
    from knowledge.pipeline import query_obsidian_async

    result = await query_obsidian_async(query)
    if len(result) > MAX_RESULT_LENGTH:
        result = result[:MAX_RESULT_LENGTH] + "\n\n[回答过长已截断]"
    return result


@registry.register(
    description="读取某篇具体 Obsidian 笔记的原文内容。"
                "当用户明确提到某篇笔记名称（如「python之路」「prompt」）"
                "并想查看其具体内容时调用。"
                "注意：被排除清单保护的隐私文件（如存放 API Key 的文件）无法读取。"
)
def read_obsidian_note(note: str) -> str:
    """读取指定 Obsidian 笔记的原文。

    Args:
        note: 笔记名称或路径，例如 "python之路" 或 "外语学习/单词表.md"
    """
    logger.info("Obsidian 读取工具被调用: %s", note)
    from config import OBSIDIAN_EXCLUDE, OBSIDIAN_VAULT_DIR
    from knowledge.loader import is_path_excluded

    vault = OBSIDIAN_VAULT_DIR
    if not vault:
        return "Obsidian vault 未配置（请设置 OBSIDIAN_VAULT_DIR）。"

    candidate = _resolve_note(note)
    if candidate is None:
        return f"未找到笔记: {note}（检查名称或路径是否正确）"

    vault_path = Path(vault).resolve()
    try:
        rel = str(candidate.resolve().relative_to(vault_path))
    except Exception:
        rel = candidate.name
    if is_path_excluded(rel, OBSIDIAN_EXCLUDE):
        return "该文件被排除清单保护，无法读取（可能含敏感信息）。"

    try:
        content = candidate.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return f"读取笔记失败: {e}"
    if len(content) > MAX_NOTE_LENGTH:
        content = content[:MAX_NOTE_LENGTH] + "\n\n[笔记过长已截断]"
    return f"# {candidate.name}\n\n{content}"


def save_note_to_vault(note: str, content: str) -> dict:
    """把笔记写入 Obsidian vault（公共函数，Agent 工具与 HTTP 接口共用）。

    安全检查：路径必须在 vault 内，受排除清单保护。

    Returns:
        {"ok": bool, "message": str, "path": str}  # path 为 vault 内相对路径（失败时为空）
    """
    from config import OBSIDIAN_EXCLUDE, OBSIDIAN_VAULT_DIR
    from knowledge.loader import is_path_excluded

    vault = OBSIDIAN_VAULT_DIR
    if not vault:
        return {"ok": False, "message": "Obsidian vault 未配置（请设置 OBSIDIAN_VAULT_DIR）。", "path": ""}

    vault_path = Path(vault).resolve()
    # 自动补 .md
    p = vault_path / note
    if p.suffix != ".md":
        p = p.with_suffix(".md")

    # 安全检查：必须在 vault 内
    try:
        p = p.resolve()
        p.relative_to(vault_path)
    except ValueError:
        return {"ok": False, "message": f"禁止写入 vault 外的路径: {note}", "path": ""}
    except Exception as e:
        return {"ok": False, "message": f"路径解析失败: {e}", "path": ""}

    # 排除清单检查
    try:
        rel = str(p.relative_to(vault_path))
    except Exception:
        rel = p.name
    if is_path_excluded(rel, OBSIDIAN_EXCLUDE):
        return {"ok": False, "message": "该文件被排除清单保护，无法写入（可能含敏感路径）。", "path": ""}

    # 写入
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        existed = p.exists()
        p.write_text(content, encoding="utf-8")
        action = "更新" if existed else "创建"
        rel_path = str(p.relative_to(vault_path))
        return {
            "ok": True,
            "message": f"已{action} Obsidian 笔记: {p.name}",
            "path": rel_path,
        }
    except Exception as e:
        return {"ok": False, "message": f"写入笔记失败: {e}", "path": ""}


@registry.register(
    description="在 Obsidian 知识库中创建新笔记或覆盖已有笔记。"
                "当用户要求「帮我写一篇笔记」「新建一篇笔记」「记录到知识库」等时调用。"
                "写入路径限制在 Obsidian vault 内，受排除清单保护。"
)
def write_obsidian_note(note: str, content: str) -> str:
    """在 Obsidian vault 中写入笔记。

    Args:
        note: 笔记名称或路径，例如 "学习笔记/AI趋势" 或 "新想法"（自动添加 .md）
        content: 要写入的 Markdown 内容
    """
    logger.info("Obsidian 写入工具被调用: %s (%d 字符)", note, len(content))
    result = save_note_to_vault(note, content)
    if result["ok"]:
        return f"{result['message']}\n路径: {result['path']}\n大小: {len(content)} 字符"
    return result["message"]
