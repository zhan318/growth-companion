"""测试 Agent：工具调度（_execute_tool）与上下文加载（_load_context）"""

from types import SimpleNamespace

import pytest

from agent import agent as agent_mod


class FakeVectorMemory:
    """替代 chromadb 向量记忆，测试用空实现"""

    def search(self, *args, **kwargs):
        return []

    def add_turn(self, *args, **kwargs):
        pass

    def clear_session(self, *args, **kwargs):
        pass


@pytest.fixture
def patched_agent(monkeypatch, memory):
    """构造一个使用隔离数据库 + 假向量记忆的 Agent"""
    monkeypatch.setattr(agent_mod, "Memory", lambda: memory)
    monkeypatch.setattr(agent_mod, "get_vector_memory", lambda: FakeVectorMemory())
    return agent_mod.Agent(session_id="test_session")


def _tool_call(name, arguments):
    return SimpleNamespace(function=SimpleNamespace(name=name, arguments=arguments))


def test_execute_tool_calculator(patched_agent):
    result = patched_agent._execute_tool(
        _tool_call("calculate", '{"expression": "1+1"}')
    )
    assert "2" in result


def test_execute_tool_unknown(patched_agent):
    result = patched_agent._execute_tool(_tool_call("no_such_tool", "{}"))
    assert "不存在" in result


def test_execute_tool_bad_json(patched_agent):
    result = patched_agent._execute_tool(_tool_call("calculate", "not-json"))
    assert "参数解析失败" in result


def test_execute_tool_missing_arg(patched_agent):
    # calculate 需要 expression 参数，缺参应报错（被捕获，不抛异常）
    result = patched_agent._execute_tool(_tool_call("calculate", "{}"))
    assert "失败" in result or "错误" in result


def test_load_context_injects_summary(patched_agent, memory):
    # 预置：一条旧摘要 + 3 条历史消息
    memory.save_session_summary("test_session", "用户之前学过 Python 并发", 10)
    memory.save_message("test_session", "user", "第一条")
    memory.save_message("test_session", "assistant", "回复一")
    memory.save_message("test_session", "user", "第二条")

    patched_agent._load_context()

    # 上下文里应包含摘要 system 消息 + 最近历史
    contents = [m["content"] for m in patched_agent.messages]
    assert any("用户之前学过 Python 并发" in c for c in contents)
    assert any(c == "第一条" for c in contents)
    assert any(c == "回复一" for c in contents)
    # 第一条仍是 system prompt
    assert patched_agent.messages[0]["role"] == "system"


def test_load_context_without_summary(patched_agent, memory):
    memory.save_message("test_session", "user", "hi")
    patched_agent._load_context()
    # 没有摘要时不报错，且消息正常
    assert patched_agent.messages[0]["role"] == "system"
    assert any(m["content"] == "hi" for m in patched_agent.messages)


def test_clear_memory(patched_agent, memory):
    memory.save_message("test_session", "user", "hi")
    patched_agent.clear_memory()
    assert memory.count_messages("test_session") == 0
    assert memory.get_session_summary("test_session") is None
    assert len(patched_agent.messages) == 1  # 只剩 system prompt
