"""测试 Obsidian 笔记写入公共函数 save_note_to_vault"""

from tools.obsidian import save_note_to_vault


def test_save_note_basic(tmp_path, monkeypatch):
    monkeypatch.setattr("config.OBSIDIAN_VAULT_DIR", str(tmp_path))
    result = save_note_to_vault("工作台笔记/测试", "这是内容")
    assert result["ok"] is True
    assert (tmp_path / "工作台笔记" / "测试.md").exists()
    assert "测试.md" in result["path"]


def test_save_note_auto_adds_md(tmp_path, monkeypatch):
    monkeypatch.setattr("config.OBSIDIAN_VAULT_DIR", str(tmp_path))
    result = save_note_to_vault("无后缀", "内容")
    assert result["ok"] is True
    assert (tmp_path / "无后缀.md").exists()


def test_save_note_vault_not_configured(monkeypatch):
    monkeypatch.setattr("config.OBSIDIAN_VAULT_DIR", "")
    result = save_note_to_vault("note", "内容")
    assert result["ok"] is False
    assert "未配置" in result["message"]


def test_save_note_rejects_escape(tmp_path, monkeypatch):
    monkeypatch.setattr("config.OBSIDIAN_VAULT_DIR", str(tmp_path))
    # 尝试路径穿越逃出 vault
    result = save_note_to_vault("../逃逸", "内容")
    assert result["ok"] is False
    assert "vault 外" in result["message"] or "禁止" in result["message"]


def test_save_note_overwrites_existing(tmp_path, monkeypatch):
    monkeypatch.setattr("config.OBSIDIAN_VAULT_DIR", str(tmp_path))
    save_note_to_vault("note", "第一版")
    result = save_note_to_vault("note", "第二版")
    assert result["ok"] is True
    assert (tmp_path / "note.md").read_text(encoding="utf-8") == "第二版"
