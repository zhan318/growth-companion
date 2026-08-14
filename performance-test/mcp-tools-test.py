"""边界2：MCP filesystem 工具逐个直测（v2：绝对路径）"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp_client import get_mcp_manager

ROOT = "D:/tmp/mcp-test-dir"


def main():
    mcp = get_mcp_manager()
    mcp.start(timeout=30)

    tools = mcp.list_tools()
    print(f"== 已注册 {len(tools)} 个 MCP 工具 ==")

    cases = [
        ("list_directory", {"path": ROOT}, "列目录"),
        ("read_file", {"path": f"{ROOT}/测试.md"}, "读文件"),
        ("search_files", {"path": ROOT, "pattern": "*.md"}, "搜索文件"),
        ("directory_tree", {"path": ROOT}, "目录树"),
        ("get_file_info", {"path": f"{ROOT}/测试.md"}, "文件信息"),
        ("list_allowed_directories", {}, "允许目录列表"),
    ]

    print("\n== 读/查操作 ==")
    for tool_name, args, label in cases:
        result = mcp.call_tool("filesystem", tool_name, args)
        text = str(result)[:250].replace("\n", " | ")
        print(f"[{label}] {tool_name}: {text}")

    print("\n== 写操作（测试目录内）==")
    write_result = mcp.call_tool("filesystem", "write_file", {
        "path": f"{ROOT}/写入测试.md", "content": "# 边界2测试\n写入成功",
    })
    print(f"[写入] write_file: {str(write_result)[:150]}")

    read_back = mcp.call_tool("filesystem", "read_file", {"path": f"{ROOT}/写入测试.md"})
    print(f"[读回] read_file: {str(read_back)[:150]}")

    create_dir = mcp.call_tool("filesystem", "create_directory", {"path": f"{ROOT}/新目录"})
    print(f"[建目录] create_directory: {str(create_dir)[:150]}")

    move_result = mcp.call_tool("filesystem", "move_file", {
        "source": f"{ROOT}/写入测试.md", "destination": f"{ROOT}/改名后.md",
    })
    print(f"[移动] move_file: {str(move_result)[:150]}")

    edit_result = mcp.call_tool("filesystem", "edit_file", {
        "path": f"{ROOT}/改名后.md", "edits": [{"oldText": "写入成功", "newText": "编辑成功"}],
    })
    print(f"[编辑] edit_file: {str(edit_result)[:150]}")

    # 越界访问验证（安全边界）
    print("\n== 越界访问（应被拒绝）==")
    escape = mcp.call_tool("filesystem", "read_file", {"path": "C:/Windows/win.ini"})
    print(f"[越界读] read_file C:/Windows: {str(escape)[:150]}")
    escape2 = mcp.call_tool("filesystem", "write_file", {
        "path": "D:/agent/obsidian/知识库/越界测试.md", "content": "不应写入",
    })
    print(f"[越界写] write_file 真实vault: {str(escape2)[:150]}")

    print("\n== 最终测试目录内容 ==")
    final = mcp.call_tool("filesystem", "directory_tree", {"path": ROOT})
    print(str(final)[:400])

    mcp.servers.clear()
    print("\n✅ MCP 工具验证完成")


if __name__ == "__main__":
    main()
