"""Mock 外部 API Server（天气 / 搜索 / 热榜）

在性能测试中替代 wttr.in / DuckDuckGo / GitHub / 微博 / 百度 等外部服务。
返回与真实服务相同结构的数据，供项目内工具解析。

配合工具的「环境变量覆盖」机制使用（见 tools/weather.py、web_search.py、hotlist.py）：
- WEATHER_API_URL  → 指向本服务 /wttr/{city}
- WEB_SEARCH_URL   → 指向本服务 /search/html
- GITHUB_API_BASE  → 指向本服务 /github
- WEIBO_HOT_URL    → 指向本服务 /weibo/ajax/side/hotSearch
- BAIDU_HOT_URL    → 指向本服务 /top.baidu/api/board

用法：
    uvicorn mock_external:app --port 18002
    或 python mock_external.py
"""

import asyncio
import html as _html
import os
import random
import time

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI(title="Mock External API Server")

# 可配置的模拟外部延迟（毫秒）
_EXTERNAL_LATENCY = int(os.getenv("MOCK_EXTERNAL_LATENCY_MS", "80"))


async def _simulate_latency():
    """模拟外部网络延迟（50-120ms 抖动）"""
    await asyncio.sleep((_EXTERNAL_LATENCY + random.randint(0, 40)) / 1000)


# ═══════════════════════════════════════════
#  天气（模拟 wttr.in format=j1）
# ═══════════════════════════════════════════

@app.get("/wttr/{city}")
async def weather(city: str):
    await _simulate_latency()
    return JSONResponse({
        "current_condition": [{
            "temp_C": "28",
            "feelsLikeC": "30",
            "humidity": "62",
            "windSpeedKmph": "12",
            "winddir16Point": "SSE",
            "weatherDesc": [{"value": "Sunny"}],
        }],
        "nearest_area": [{"areaName": [{"value": city}]}],
    })


# ═══════════════════════════════════════════
#  网页搜索（模拟 DuckDuckGo HTML 页面）
# ═══════════════════════════════════════════

_SEARCH_RESULT_TPL = (
    '<div class="result">'
    '<a class="result__a" href="{url}">{title}</a>'
    '<a class="result__snippet" href="{url}">{snippet}</a>'
    "</div>"
)


@app.post("/search/html")
async def search(request: Request):
    await _simulate_latency()
    form = await request.form()
    q = form.get("q", "test")
    items = [
        {
            "title": f"{q} 结果一 - 示例标题",
            "url": f"https://example.com/1?q={q}",
            "snippet": f"关于 {q} 的示例描述文本，用于模拟搜索摘要。",
        },
        {
            "title": f"{q} 结果二 - 官方文档",
            "url": f"https://docs.example.com/{q}",
            "snippet": f"{q} 的官方文档和最佳实践介绍。",
        },
        {
            "title": f"{q} 结果三 - 社区讨论",
            "url": f"https://forum.example.com/t/{q}",
            "snippet": "社区开发者关于 " + q + " 的经验分享。",
        },
    ]
    body = "".join(
        _SEARCH_RESULT_TPL.format(url=it["url"], title=it["title"], snippet=it["snippet"])
        for it in items
    )
    return HTMLResponse(body)


# ═══════════════════════════════════════════
#  热榜：GitHub（模拟 api.github.com/search/repositories）
# ═══════════════════════════════════════════

@app.get("/github/search/repositories")
async def github_trending(request: Request):
    await _simulate_latency()
    return JSONResponse({
        "items": [
            {
                "full_name": "mock-org/mock-llm",
                "html_url": "https://github.com/mock-org/mock-llm",
                "description": "Mock LLM project for performance testing",
                "stargazers_count": 12345,
            },
            {
                "full_name": "mock-org/mock-rag",
                "html_url": "https://github.com/mock-org/mock-rag",
                "description": "Mock RAG framework",
                "stargazers_count": 9876,
            },
            {
                "full_name": "mock-org/mock-agent",
                "html_url": "https://github.com/mock-org/mock-agent",
                "description": "Mock AI agent toolkit",
                "stargazers_count": 5432,
            },
            {
                "full_name": "mock-org/mock-vector",
                "html_url": "https://github.com/mock-org/mock-vector",
                "description": "Mock vector database wrapper",
                "stargazers_count": 3210,
            },
            {
                "full_name": "mock-org/mock-search",
                "html_url": "https://github.com/mock-org/mock-search",
                "description": "Mock web search aggregator",
                "stargazers_count": 2100,
            },
        ]
    })


# ═══════════════════════════════════════════
#  热榜：微博（模拟 weibo.com/ajax/side/hotSearch）
# ═══════════════════════════════════════════

@app.get("/weibo/ajax/side/hotSearch")
async def weibo_hot():
    await _simulate_latency()
    realtime = [
        {"word": "AI 智能体新进展", "hot_num": "4500000"},
        {"word": "Python 3.14 发布", "hot_num": "3800000"},
        {"word": "大模型推理优化", "hot_num": "2900000"},
        {"word": "RAG 实践案例", "hot_num": "2100000"},
        {"word": "开源模型性能对比", "hot_num": "1800000"},
    ]
    return JSONResponse({"data": {"realtime": realtime}})


# ═══════════════════════════════════════════
#  热榜：百度（模拟 top.baidu.com/api/board）
# ═══════════════════════════════════════════

@app.get("/top.baidu/api/board")
async def baidu_hot():
    await _simulate_latency()
    cards = [{
        "content": [
            {"word": "百度热搜一", "hotScore": "5500000"},
            {"word": "百度热搜二", "hotScore": "4600000"},
            {"word": "百度热搜三", "hotScore": "3700000"},
        ]
    }]
    return JSONResponse({"data": {"cards": cards}})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("mock_external:app", host="127.0.0.1", port=int(os.getenv("MOCK_EXTERNAL_PORT", "18002")), log_level="warning")
