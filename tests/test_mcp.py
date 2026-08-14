"""测试 MCP 客户端：配置加载、结果格式化、工具注册（不实际启动进程）"""

from types import SimpleNamespace

from mcp_client import MCPManager, _format_result, register_mcp_tools


def test_load_config_missing(tmp_path):
    m = MCPManager(config_path=str(tmp_path / "nonexist.json"))
    assert m.load_config() == {}


def test_load_config_parses(tmp_path):
    p = tmp_path / "mcp.json"
    p.write_text(
        '{"mcpServers": {"fs": {"command": "npx", "args": ["-y", "x"]}}}',
        encoding="utf-8",
    )
    m = MCPManager(config_path=str(p))
    cfg = m.load_config()
    assert "fs" in cfg["mcpServers"]
    assert cfg["mcpServers"]["fs"]["command"] == "npx"


def test_format_result_text():
    item = SimpleNamespace(text="文件内容", data=None)
    result = SimpleNamespace(content=[item], isError=False)
    assert _format_result(result) == "文件内容"


def test_format_result_error_flag():
    item = SimpleNamespace(text="权限不足", data=None)
    result = SimpleNamespace(content=[item], isError=True)
    assert "错误" in _format_result(result)


def test_format_result_empty():
    result = SimpleNamespace(content=[], isError=False)
    assert "空结果" in _format_result(result)


def test_register_mcp_tools(monkeypatch):
    from tools import ToolRegistry

    fake_registry = ToolRegistry()
    monkeypatch.setattr("tools.registry", fake_registry)

    class FakeManager:
        def list_tools(self):
            return [{
                "server": "fs",
                "name": "read_file",
                "description": "读取文件",
                "schema": {"type": "object", "properties": {"path": {"type": "string"}}},
            }]

        def call_tool(self, server, name, args):
            return f"called {server}.{name} with {args}"

    count = register_mcp_tools(FakeManager())
    assert count == 1
    assert "mcp_fs_read_file" in fake_registry.tools
    # 工具可正常调用，参数正确透传
    result = fake_registry.tools["mcp_fs_read_file"](path="/a/b.txt")
    assert "read_file" in result
    assert "/a/b.txt" in result
    # schema 已注册
    assert len(fake_registry.schemas) == 1
    assert fake_registry.schemas[0]["function"]["name"] == "mcp_fs_read_file"
