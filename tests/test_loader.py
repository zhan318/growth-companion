"""测试知识库文档加载器的隐私排除逻辑 is_path_excluded"""

from knowledge.loader import is_path_excluded


def test_exact_filename_match():
    assert is_path_excluded("工具与配置/API.md", ["API.md"]) is True


def test_exact_relative_path_match():
    assert is_path_excluded("secret/api.md", ["secret/api.md"]) is True


def test_folder_segment_match():
    # 文件夹段匹配：.trash 回收站目录整体排除
    assert is_path_excluded(".trash/旧笔记.md", [".trash"]) is True


def test_wildcard_prefix_match():
    # API* 前缀通配：覆盖 API密钥.md 等任何以 API 开头的文件名
    assert is_path_excluded("工具与配置/API密钥.md", ["API*"]) is True


def test_wildcard_contains_match():
    # *账密* 包含通配：匹配任意含「账密」的文件名
    assert is_path_excluded("工具与配置/obsidian账密及限量词条.md", ["*账密*"]) is True


def test_wildcard_no_false_positive():
    # 通配不误伤正常笔记
    assert is_path_excluded("工具与配置/某个正常笔记.md", ["*密钥*"]) is False


def test_exact_no_false_positive():
    # 精确匹配不误伤：API.md 不等于 MyAPI.md
    assert is_path_excluded("MyAPI.md", ["API.md"]) is False


def test_empty_excludes():
    assert is_path_excluded("任意.md", []) is False


def test_none_of_patterns_match():
    assert is_path_excluded("普通笔记.md", ["API*", "*密钥*", "*账密*"]) is False
