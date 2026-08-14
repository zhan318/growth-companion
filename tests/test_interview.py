"""测试面试记录归档：消息加载过滤 + 写入 Obsidian（mock LLM + 临时 vault）"""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from interview import (
    _WEAKNESS_FILE,
    _load_session_messages,
    build_weakness_profile,
    save_interview_record,
)


def _fake_chat_response(content):
    msg = SimpleNamespace(content=content)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def test_load_session_messages_filters_tool_noise(memory):
    memory.save_message("s1", "user", "开始面试吧")
    memory.save_message("s1", "assistant", "[mock_interview] # 🎯 模拟面试问题")
    memory.save_message("s1", "user", "GIL 限制了多线程的什么？")
    memory.save_message("s1", "assistant", "答得不错，补充一点...")
    msgs = _load_session_messages(memory, "s1")
    assert len(msgs) == 3
    assert all(not m["content"].startswith("[") for m in msgs)


def test_save_interview_record_writes_file(memory, monkeypatch, tmp_path):
    # mock LLM 整理 + 指向临时 vault
    monkeypatch.setattr(
        "chatbot.chatbot.chat",
        lambda messages, **kwargs: _fake_chat_response("## 面试主题\nPython 并发\n## 问答回顾\n### Q1..."),
    )
    monkeypatch.setattr("config.OBSIDIAN_VAULT_DIR", str(tmp_path))

    memory.save_message("s1", "user", "面试我并发")
    memory.save_message("s1", "assistant", "GIL 是什么？")
    memory.save_message("s1", "user", "全局解释器锁")
    memory.save_message("s1", "assistant", "很好")

    result = save_interview_record("s1", memory)
    assert result["ok"] is True

    today = datetime.now().strftime("%Y-%m-%d")
    filepath = tmp_path / "模拟面试" / "面试记录" / f"{today}.md"
    assert filepath.exists()
    content = filepath.read_text(encoding="utf-8")
    assert "Python 并发" in content
    assert result["path"] == str(Path("模拟面试") / "面试记录" / f"{today}.md")


def test_save_interview_record_appends_same_day(memory, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "chatbot.chatbot.chat",
        lambda messages, **kwargs: _fake_chat_response("第二次面试的记录内容"),
    )
    monkeypatch.setattr("config.OBSIDIAN_VAULT_DIR", str(tmp_path))

    memory.save_message("s1", "user", "q")
    memory.save_message("s1", "assistant", "a")

    save_interview_record("s1", memory)
    filepath = tmp_path / "模拟面试" / "面试记录" / f"{datetime.now().strftime('%Y-%m-%d')}.md"
    size_1 = filepath.stat().st_size

    save_interview_record("s1", memory)
    size_2 = filepath.stat().st_size
    # 同一天第二次保存应追加到同一文件（文件变大，且只有一份）
    assert size_2 > size_1


def test_save_interview_record_rejects_empty_session(memory, tmp_path, monkeypatch):
    monkeypatch.setattr("config.OBSIDIAN_VAULT_DIR", str(tmp_path))
    result = save_interview_record("empty_session", memory)
    assert result["ok"] is False
    assert "太少" in result["error"]


# ── 薄弱点画像 ──

def _make_record_file(tmp_path, content: str):
    record_dir = tmp_path / "模拟面试" / "面试记录"
    record_dir.mkdir(parents=True, exist_ok=True)
    (record_dir / "2026-08-13.md").write_text(content, encoding="utf-8")


def test_weakness_no_records(memory, tmp_path, monkeypatch):
    monkeypatch.setattr("config.OBSIDIAN_VAULT_DIR", str(tmp_path))
    result = build_weakness_profile()
    assert result["ok"] is False
    assert "还没有面试记录" in result["error"]


def test_weakness_builds_profile(tmp_path, monkeypatch):
    _make_record_file(tmp_path, "## 面试主题\nPython 并发\nGIL 相关答得不全")

    monkeypatch.setattr(
        "chatbot.chatbot.chat",
        lambda messages, **kwargs: _fake_chat_response(
            "## 反复出现的薄弱主题\n1. **并发编程**（出现 2 次）"
        ),
    )
    monkeypatch.setattr("config.OBSIDIAN_VAULT_DIR", str(tmp_path))

    result = build_weakness_profile()
    assert result["ok"] is True
    assert result["record_count"] == 1

    filepath = tmp_path / _WEAKNESS_FILE
    assert filepath.exists()
    content = filepath.read_text(encoding="utf-8")
    assert "并发编程" in content
    assert "分析 1 份面试记录" in content


def test_weakness_overwrites_file(tmp_path, monkeypatch):
    _make_record_file(tmp_path, "记录内容A")

    calls = {"n": 0}

    def fake_chat(messages, **kwargs):
        calls["n"] += 1
        return _fake_chat_response(f"第 {calls['n']} 版画像")

    monkeypatch.setattr("chatbot.chatbot.chat", fake_chat)
    monkeypatch.setattr("config.OBSIDIAN_VAULT_DIR", str(tmp_path))

    build_weakness_profile()
    build_weakness_profile()

    filepath = tmp_path / _WEAKNESS_FILE
    content = filepath.read_text(encoding="utf-8")
    # 覆盖更新：最终内容是最新一版，且只有一个文件
    assert "第 2 版画像" in content
    assert "第 1 版画像" not in content
