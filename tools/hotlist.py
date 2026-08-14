"""热榜工具：获取各平台今日热门内容

提供同步（get_hotlist）与异步（get_hotlist_async）两个版本。
"""

import os

import httpx

from tools import registry
from utils.logger import get_logger

logger = get_logger(__name__)

_TIMEOUT = 10.0
# 允许测试时用环境变量覆盖上游地址（性能测试 mock 用），默认走真实服务
_GITHUB_API_BASE = os.getenv("GITHUB_API_BASE", "https://api.github.com")
_WEIBO_HOT_URL = os.getenv("WEIBO_HOT_URL", "https://weibo.com/ajax/side/hotSearch")
_BAIDU_HOT_URL = os.getenv("BAIDU_HOT_URL", "https://top.baidu.com/api/board?tab=realtime")
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _fetch_json(url: str) -> dict | None:
    """通用 GET 请求 + JSON 解析（同步）"""
    headers = {"User-Agent": _USER_AGENT}
    try:
        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException:
        logger.warning("请求超时 %s", url)
    except httpx.HTTPStatusError as e:
        logger.warning("请求返回 %s: %s", e.response.status_code, url)
    except Exception as e:
        logger.error("请求失败 %s: %s", url, e)
    return None


async def _fetch_json_async(url: str) -> dict | None:
    """通用 GET 请求 + JSON 解析（异步）"""
    headers = {"User-Agent": _USER_AGENT}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException:
        logger.warning("请求超时 %s", url)
    except httpx.HTTPStatusError as e:
        logger.warning("请求返回 %s: %s", e.response.status_code, url)
    except Exception as e:
        logger.error("请求失败 %s: %s", url, e)
    return None


def _build_github_url() -> str:
    """构造 GitHub AI 趋势搜索 URL"""
    from datetime import datetime, timedelta

    since = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    ai_topics = [
        "artificial-intelligence",
        "machine-learning",
        "llm",
        "generative-ai",
        "deep-learning",
        "chatgpt",
        "langchain",
        "transformer",
    ]
    topic_query = "+".join(f"topic:{t}" for t in ai_topics)
    return (
        f"{_GITHUB_API_BASE}/search/repositories"
        f"?q={topic_query}+created:>{since}"
        f"&sort=stars&order=desc&per_page=5"
    )


def _parse_github(data: dict | None) -> list[dict]:
    if not data:
        return []
    return [
        {"title": repo["full_name"],
         "url": repo["html_url"],
         "desc": (repo.get("description") or "")[:80],
         "hot": f"\u2b50 {repo['stargazers_count']} stars"}
        for repo in data.get("items", [])
    ]


def _parse_weibo(data: dict | None) -> list[dict]:
    if not data:
        return []
    realtime = data.get("data", {}).get("realtime", [])
    return [
        {"title": item.get("word", ""),
         "url": f"https://s.weibo.com/weibo?q={item.get('word', '')}",
         "desc": "",
         "hot": f"\u706b {item.get('hot_num', '')}"}
        for item in realtime[:25]
    ]


def _parse_baidu(data: dict | None) -> list[dict]:
    if not data:
        return []
    results = data.get("data", {}).get("cards", [])
    items = []
    for card in results:
        for item in card.get("content", []):
            items.append({
                "title": item.get("word", item.get("query", "")),
                "url": item.get("url", "") or item.get("link", ""),
                "desc": item.get("desc", "")[:60],
                "hot": f"\u706b {item.get('hotScore', '')}",
            })
    return items[:25]


# platform → (展示名, URL 构造器, 解析器)
_PLATFORM_CONFIG = {
    "github": ("GitHub", lambda: _build_github_url(), _parse_github),
    "weibo": ("微博", lambda: _WEIBO_HOT_URL, _parse_weibo),
    "baidu": ("百度", lambda: _BAIDU_HOT_URL, _parse_baidu),
}


def _format_output(platform_name: str, items: list[dict]) -> str:
    if not items:
        return f"{platform_name} 热榜暂时获取不到数据，请稍后重试"

    lines = [f"\U0001f525 {platform_name}热榜 TOP {len(items)}\n"]
    for i, item in enumerate(items, 1):
        title = item["title"]
        hot = item.get("hot", "")
        hot_str = f" [{hot}]" if hot else ""
        lines.append(f"{i:2d}. {title}{hot_str}")
        desc = item.get("desc", "")
        if desc:
            lines.append(f"    \u21b3 {desc}")
    return "\n".join(lines)


@registry.register(
    description="获取各平台今日热榜/热搜。GitHub 模式只搜 AI/机器学习/大模型 相关热门仓库（TOP 5）。也支持 weibo(微博热搜)、baidu(百度热搜)"
)
def get_hotlist(platform: str = "github") -> str:
    """获取指定平台的今日热榜内容（同步版）。

    GitHub 模式现已限定为 AI 相关项目（按 topic 标签 + stars 排序）。

    Args:
        platform: 平台名称，github | weibo | baidu。默认 github。
    """
    platform = platform.lower().strip()

    if platform not in _PLATFORM_CONFIG:
        supported = ", ".join(_PLATFORM_CONFIG.keys())
        return f"不支持的平台: {platform}，当前支持: {supported}"

    platform_name, url_builder, parser = _PLATFORM_CONFIG[platform]
    try:
        data = _fetch_json(url_builder())
        items = parser(data)
    except Exception as e:
        logger.error("获取 %s 热榜失败: %s", platform, e)
        return f"获取 {platform_name} 热榜失败: {e}"

    return _format_output(platform_name, items)


@registry.register_async(
    description="获取各平台今日热榜/热搜。GitHub 模式只搜 AI/机器学习/大模型 相关热门仓库（TOP 5）。也支持 weibo(微博热搜)、baidu(百度热搜)"
)
async def get_hotlist_async(platform: str = "github") -> str:
    """获取指定平台的今日热榜内容（异步版，Agent.arun 使用）。

    Args:
        platform: 平台名称，github | weibo | baidu。默认 github。
    """
    platform = platform.lower().strip()

    if platform not in _PLATFORM_CONFIG:
        supported = ", ".join(_PLATFORM_CONFIG.keys())
        return f"不支持的平台: {platform}，当前支持: {supported}"

    platform_name, url_builder, parser = _PLATFORM_CONFIG[platform]
    try:
        data = await _fetch_json_async(url_builder())
        items = parser(data)
    except Exception as e:
        logger.error("获取 %s 热榜失败: %s", platform, e)
        return f"获取 {platform_name} 热榜失败: {e}"

    return _format_output(platform_name, items)
