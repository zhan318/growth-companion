"""Mock LLM Server（OpenAI 兼容）

模拟 DeepSeek/OpenAI chat completions API，用于性能测试时替代真实 LLM：
- 根据用户消息关键词路由到对应工具调用（tool_calls），让 Agent 的 ReAct 循环真实走完
- 工具结果返回后，直接给出最终回答
- 支持非流式 + 流式（SSE）两种模式
- 支持可配置延迟，模拟真实 LLM 的耗时（默认 100-200ms 抖动）

用法：
    uvicorn mock_llm:app --port 18001
    或 python mock_llm.py
"""

import asyncio
import json
import os
import random
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="Mock LLM Server")

# 可配置的响应延迟（毫秒）
_BASE_LATENCY = int(os.getenv("MOCK_LLM_LATENCY_MS", "150"))


# ═══════════════════════════════════════════
#  工具路由：关键词 → (工具名, 参数构造器)
# ═══════════════════════════════════════════

def _route(message: str) -> list[dict]:
    """根据用户消息返回要调用的工具列表（可多工具并行）。"""
    msg = message.lower()

    calls = []

    # 多工具组合消息 → 同时触发多个工具（模拟 LLM 一次返回多个 tool_calls）
    if ("天气" in msg) and ("热榜" in msg or "热搜" in msg) and ("算" in msg) and ("搜索" in msg or "搜一下" in msg):
        calls = [
            {"name": "get_weather", "arguments": {"city": "北京"}},
            {"name": "get_hotlist", "arguments": {"platform": "github"}},
            {"name": "calculate", "arguments": {"expression": "1234*5678"}},
            {"name": "web_search", "arguments": {"query": "Python 并发 教程"}},
        ]
        return calls

    if "天气" in msg or "气温" in msg or "热不热" in msg:
        calls.append({"name": "get_weather", "arguments": {"city": "北京"}})
    if "热榜" in msg or "热搜" in msg or "热榜" in msg:
        platform = "weibo" if "微博" in msg else ("baidu" if "百度" in msg else "github")
        calls.append({"name": "get_hotlist", "arguments": {"platform": platform}})
    if "搜索" in msg or "搜一下" in msg or "查一下" in msg or "上网查" in msg:
        calls.append({"name": "web_search", "arguments": {"query": "Python asyncio 最佳实践"}})
    if "算" in msg or "计算" in msg or ("多少" in msg and any(c in msg for c in "0123456789+-*×÷")):
        calls.append({"name": "calculate", "arguments": {"expression": "1234*5678"}})
    if any(k in msg for k in ["笔记", "学习", "项目", "复习", "我最近学了", "知识库", "面试"]):
        if "面试" in msg:
            calls.append({"name": "mock_interview", "arguments": {"topic": "Python 并发"}})
        else:
            calls.append({"name": "search_obsidian_notes", "arguments": {"query": message}})

    return calls


def _mock_answer(message: str) -> str:
    """直接回答（不调用工具）时的 mock 回复。"""
    if any(k in message for k in ["你好", "hi", "hello", "嗨"]):
        return "你好！我是智能个人助手，有什么可以帮你的？"
    return (
        "这是 mock LLM 的回复。你的问题：「" + message + "」\n"
        "（当前处于性能测试模式，LLM 由本地 mock 服务替代。）"
    )


def _build_chunk_id() -> str:
    return "chatcmpl-" + uuid.uuid4().hex[:16]


def _build_response(message: str, has_tool_result: bool) -> dict:
    """构造 OpenAI chat completion 响应。

    - 若 messages 中已有 tool 结果 → 直接返回最终回答（finish_reason=stop）
    - 否则按路由返回 tool_calls（finish_reason=tool_calls）
    """
    now = int(time.time())
    base = {
        "id": _build_chunk_id(),
        "object": "chat.completion",
        "created": now,
        "model": os.getenv("MOCK_LLM_MODEL", "deepseek-chat"),
        "choices": [],
        "usage": {"prompt_tokens": 256, "completion_tokens": 128, "total_tokens": 384},
    }

    if has_tool_result:
        base["choices"] = [{
            "index": 0,
            "finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": "已根据工具结果整理回答：这是 mock LLM 基于工具返回数据生成的最终回复。",
            },
        }]
        return base

    tool_calls = _route(message)
    if tool_calls:
        choices = []
        for i, tc in enumerate(tool_calls):
            choices.append({
                "index": i,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_" + uuid.uuid4().hex[:12],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                        },
                    }],
                },
            })
        base["choices"] = [choices[0]]  # OpenAI 一次返回一个 message，里面可含多个 tool_calls
        base["choices"][0]["message"]["tool_calls"] = [
            {
                "id": "call_" + uuid.uuid4().hex[:12],
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                },
            }
            for tc in tool_calls
        ]
        return base

    base["choices"] = [{
        "index": 0,
        "finish_reason": "stop",
        "message": {"role": "assistant", "content": _mock_answer(message)},
    }]
    return base


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    stream = body.get("stream", False)

    # 取出用户最新消息
    user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user_msg = m.get("content", "")
            break

    # 判断是否已有工具结果（tool 角色消息）
    has_tool_result = any(m.get("role") == "tool" for m in messages)

    # 模拟 LLM 延迟
    delay_ms = _BASE_LATENCY + random.randint(0, 50)
    await asyncio.sleep(delay_ms / 1000)

    if stream:
        async def gen():
            resp = _build_response(user_msg, has_tool_result)
            content = resp["choices"][0]["message"].get("content") or ""
            if content:
                # 流式返回内容
                for i in range(0, len(content), 4):
                    chunk = {
                        "id": resp["id"],
                        "object": "chat.completion.chunk",
                        "created": resp["created"],
                        "model": resp["model"],
                        "choices": [{
                            "index": 0,
                            "delta": {"role": "assistant", "content": content[i:i+4]},
                            "finish_reason": None,
                        }],
                    }
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.01)
                final = {
                    "id": resp["id"],
                    "object": "chat.completion.chunk",
                    "created": resp["created"],
                    "model": resp["model"],
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                }
                yield f"data: {json.dumps(final, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            else:
                # 工具调用：一次性返回
                chunk = {
                    "id": resp["id"],
                    "object": "chat.completion.chunk",
                    "created": resp["created"],
                    "model": resp["model"],
                    "choices": [{
                        "index": 0,
                        "delta": resp["choices"][0]["message"],
                        "finish_reason": "tool_calls",
                    }],
                }
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    return JSONResponse(_build_response(user_msg, has_tool_result))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("mock_llm:app", host="127.0.0.1", port=int(os.getenv("MOCK_LLM_PORT", "18001")), log_level="warning")
