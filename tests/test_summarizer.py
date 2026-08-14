"""测试上下文压缩器（滚动摘要）的边界逻辑，mock 掉 LLM 调用"""

from types import SimpleNamespace

from memory import summarizer


def _fake_chat_response(content):
    msg = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=msg)
    return SimpleNamespace(choices=[choice])


def test_is_tool_noise():
    # 工具调用中间结果（[tool_name] 前缀）应被过滤
    assert summarizer._is_tool_noise({"role": "assistant", "content": "[weather] 晴"}) is True
    assert summarizer._is_tool_noise({"role": "assistant", "content": "[get_hotlist] ..."}) is True
    # 正常对话不应被过滤
    assert summarizer._is_tool_noise({"role": "assistant", "content": "今天天气不错"}) is False
    # 用户消息即使带 [ 也不该被过滤
    assert summarizer._is_tool_noise({"role": "user", "content": "[疑问] 你好"}) is False


def test_compress_skips_when_below_threshold(memory):
    # 消息数不足阈值 → 不触发压缩（返回 False，且不调 LLM）
    for i in range(5):
        memory.save_message("s1", "user", f"msg{i}")
    assert summarizer.compress_if_needed("s1", memory) is False


def test_compress_builds_and_saves_summary(memory, monkeypatch):
    # 构造超过阈值的历史（14 条 > 12）
    for i in range(14):
        role = "user" if i % 2 == 0 else "assistant"
        memory.save_message("s1", role, f"内容{i}")

    # mock chat：返回固定摘要
    monkeypatch.setattr(
        "chatbot.chatbot.chat",
        lambda messages, **kwargs: _fake_chat_response("用户在学习 Python 和 RAG"),
    )

    assert summarizer.compress_if_needed("s1", memory) is True

    s = memory.get_session_summary("s1")
    assert s is not None
    assert s["summary"] == "用户在学习 Python 和 RAG"
    # 压缩边界 = 14 - KEEP_RECENT(5) = 第 9 条
    assert s["compressed_until_id"] == 14 - summarizer.KEEP_RECENT


def test_compress_excludes_tool_noise(memory, monkeypatch):
    # 14 条消息（> 12 阈值），工具噪声穿插在前 9 条（属于会被压缩的范围）
    history = [
        ("user", "正常0"),
        ("assistant", "[weather] 晴 25度"),
        ("user", "正常1"),
        ("assistant", "正常回复1"),
        ("user", "正常2"),
        ("assistant", "[get_hotlist] 榜单"),
        ("user", "正常3"),
        ("assistant", "正常回复3"),
        ("user", "正常4"),
        ("assistant", "正常回复4"),
        ("user", "正常5"),
        ("assistant", "正常回复5"),
        ("user", "正常6"),
        ("assistant", "正常回复6"),
    ]
    for role, content in history:
        memory.save_message("s1", role, content)

    captured = {}

    def fake_chat(messages, **kwargs):
        # 抓取传给 LLM 的 prompt，检查是否排除了工具噪声
        captured["prompt"] = messages[0]["content"]
        return _fake_chat_response("摘要")

    monkeypatch.setattr("chatbot.chatbot.chat", fake_chat)
    summarizer.compress_if_needed("s1", memory)
    # 工具噪声不应出现在摘要 prompt 里
    assert "[weather]" not in captured["prompt"]
    assert "[get_hotlist]" not in captured["prompt"]


def test_compress_merges_old_summary(memory, monkeypatch):
    # 已有旧摘要，再压缩新对话时应把旧摘要一并传给 LLM
    memory.save_session_summary("s1", "旧摘要：用户之前学过并发", 3)
    for i in range(4, 16):
        memory.save_message("s1", "user", f"msg{i}")

    captured = {}

    def fake_chat(messages, **kwargs):
        captured["prompt"] = messages[0]["content"]
        return _fake_chat_response("合并后的摘要")

    monkeypatch.setattr("chatbot.chatbot.chat", fake_chat)
    summarizer.compress_if_needed("s1", memory)
    assert "旧摘要" in captured["prompt"]
