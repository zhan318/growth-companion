"""测试工具注册表：注册、schema 生成、调用"""

from tools import registry


def test_registry_contains_expected_tools():
    names = set(registry.tools.keys())
    # 核心工具都应存在（数量会随功能增长，只断言必要的存在）
    for expected in (
        "calculate",
        "get_weather",
        "get_hotlist",
        "search_obsidian_notes",
        "read_obsidian_note",
        "write_obsidian_note",
        "mock_interview",
        "knowledge_search",
        "web_search",
    ):
        assert expected in names, f"缺少工具 {expected}"


def test_registry_generates_schemas():
    # schema 数量应与工具数量一致
    assert len(registry.schemas) == len(registry.tools)
    for schema in registry.schemas:
        assert schema["type"] == "function"
        assert "name" in schema["function"]
        assert "parameters" in schema["function"]


def test_calculator_invocation():
    assert "2" in registry.tools["calculate"]("1+1")


def test_schema_has_parameters_properties():
    # 每个 schema 的 parameters 都应包含 properties 字段
    for schema in registry.schemas:
        assert "properties" in schema["function"]["parameters"]
