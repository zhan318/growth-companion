"""通用 stdio MCP 客户端：连接本地 MCP server，发现并调用工具。

设计：
- 后台线程持有专属 asyncio 事件循环 + MCP 会话，避免与 FastAPI 事件循环冲突；
- 主线程通过 run_coroutine_threadsafe 提交同步调用；
- 传输层抽象：当前实现 stdio，配置里 type 字段预留 http，切换不改调用方。

MCP 握手流程（JSON-RPC 2.0）：
  initialize → notifications/initialized → tools/list → tools/call
"""

import asyncio
import json
import os
import threading
from pathlib import Path

from utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_CONFIG = os.getenv("MCP_CONFIG_PATH", "mcp_config.json")
_CALL_TIMEOUT = 60.0


class MCPManager:
    """管理多个 MCP server 的连接与工具调用。"""

    def __init__(self, config_path: str = DEFAULT_CONFIG):
        self.config_path = config_path
        self.servers: dict[str, dict] = {}  # name -> {session, tools}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()

    # ── 配置 ──

    def load_config(self) -> dict:
        """加载 mcp_config.json。"""
        path = Path(self.config_path)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("读取 MCP 配置失败: %s", e)
            return {}

    # ── 生命周期 ──

    def start(self, timeout: float = 15.0):
        """后台线程启动事件循环，连接所有配置的 server。"""
        servers = self.load_config().get("mcpServers", {})
        if not servers:
            logger.info("未配置 MCP server，跳过连接")
            return

        self._thread = threading.Thread(
            target=self._run_loop, args=(servers,), daemon=True, name="mcp-manager",
        )
        self._thread.start()
        # 等待连接完成（或超时）
        self._ready.wait(timeout=timeout)
        if not self._ready.is_set():
            logger.warning("MCP server 连接超时（部分 server 可能未就绪）")

    def _run_loop(self, servers: dict):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        for name, cfg in servers.items():
            self._loop.create_task(self._serve_one(name, cfg))
        # 保持循环运行，处理后续工具调用（server 连接是常驻 task）
        self._loop.run_forever()

    async def _serve_one(self, name: str, cfg: dict):
        """常驻 task：连接单个 server 并保持会话存活。

        注意：stdio_client 的 async context 必须持续存活，不能手动
        __aenter__ 跨 await 边界退出（会触发 anyio cancel scope 错误），
        所以用 async with 完整包裹并在内部 await 永不返回的 Event 保持。
        """
        transport = (cfg.get("type") or "stdio").lower()
        if transport != "stdio":
            logger.warning("MCP server「%s」传输类型 %s 暂未实现，跳过", name, transport)
            self._ready.set()
            return

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=cfg["command"],
            args=cfg.get("args", []),
            env=cfg.get("env"),
        )
        try:
            async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                tools = tools_result.tools if hasattr(tools_result, "tools") else []
                self.servers[name] = {"session": session, "tools": tools}
                logger.info("MCP server「%s」已连接，%d 个工具", name, len(tools))
                self._ready.set()
                await asyncio.Event().wait()  # 保持连接存活直到进程退出
        except Exception as e:
            logger.warning("连接 MCP server「%s」失败: %s", name, e)
            self._ready.set()

    # ── 同步调用（线程安全） ──

    def _run_async(self, coro):
        if self._loop is None or not self._loop.is_running():
            return None
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=_CALL_TIMEOUT)
        except Exception as e:
            logger.error("MCP 调用异常: %s", e)
            return None

    def list_tools(self) -> list[dict]:
        """返回所有 server 的工具，供 Agent 注册。

        Returns:
            [{"server": name, "name": tool_name, "description": str, "schema": inputSchema}]
        """
        result = []
        for server, info in self.servers.items():
            for tool in info["tools"]:
                result.append({
                    "server": server,
                    "name": tool.name,
                    "description": getattr(tool, "description", "") or "",
                    "schema": getattr(tool, "input_schema", {}) or {},
                })
        return result

    def call_tool(self, server: str, name: str, arguments: dict) -> str:
        """同步调用某个 server 的某个工具，返回文本结果。"""
        info = self.servers.get(server)
        if info is None:
            return f"MCP server「{server}」未连接"

        async def _call():
            result = await info["session"].call_tool(name, arguments or {})
            return result

        result = self._run_async(_call())
        if result is None:
            return f"调用 MCP 工具 {name} 失败（超时或未连接）"
        return _format_result(result)

    def is_connected(self) -> bool:
        return len(self.servers) > 0


def _format_result(result) -> str:
    """把 CallToolResult 转成文本（优先 text，其次资源）。"""
    parts = []
    content = getattr(result, "content", None) or []
    for c in content:
        text = getattr(c, "text", None)
        if text:
            parts.append(text)
        else:
            data = getattr(c, "data", None)
            if data is not None:
                parts.append(str(data))
    if getattr(result, "isError", False):
        parts.append("[工具返回了错误]")
    return "\n".join(parts) if parts else "(空结果)"


# 全局单例
_manager: MCPManager | None = None


def get_mcp_manager() -> MCPManager:
    global _manager
    if _manager is None:
        _manager = MCPManager()
    return _manager


def register_mcp_tools(manager: MCPManager | None = None) -> int:
    """把 MCP 工具注册到 Agent 的工具注册表（名称前缀 mcp_{server}_{tool}）。

    Returns:
        注册的工具数量
    """
    from functools import partial

    from tools import registry

    manager = manager or get_mcp_manager()

    def _invoke(server: str, tool_name: str, **kwargs) -> str:
        return manager.call_tool(server, tool_name, kwargs)

    count = 0
    for tool in manager.list_tools():
        name = f"mcp_{tool['server']}_{tool['name']}"
        func = partial(_invoke, tool["server"], tool["name"])

        schema = tool.get("schema") or {}
        if schema.get("type") != "object":
            schema = {"type": "object", "properties": {}}
        registry.register_manual(name, tool.get("description", ""), schema, func)
        count += 1
    logger.info("已注册 %d 个 MCP 工具", count)
    return count
