"""测试 MBTI 存档 + 数据看板统计"""

from dashboard import count_interview_records, get_stats


def test_save_and_get_mbti_result(memory):
    ok = memory.save_mbti_result(1, "INTJ", "后端开发", {"E": 5, "I": 3})
    assert ok is True
    history = memory.get_mbti_history(1)
    assert len(history) == 1
    assert history[0]["mbti"] == "INTJ"
    assert history[0]["ideal_role"] == "后端开发"
    assert history[0]["scores"] == {"E": 5, "I": 3}


def test_mbti_history_order(memory):
    memory.save_mbti_result(1, "INFP", "产品经理", {})
    memory.save_mbti_result(1, "INTJ", "后端", {})
    memory.save_mbti_result(1, "ENTJ", "管理者", {})
    history = memory.get_mbti_history(1)
    assert [h["mbti"] for h in history] == ["ENTJ", "INTJ", "INFP"]  # 最新在前
    assert memory.count_mbti_results(1) == 3


def test_count_interview_records(tmp_path):
    assert count_interview_records(str(tmp_path)) == 0
    record_dir = tmp_path / "模拟面试" / "面试记录"
    record_dir.mkdir(parents=True, exist_ok=True)
    (record_dir / "2026-08-13.md").write_text("记录1", encoding="utf-8")
    (record_dir / "2026-08-12.md").write_text("记录2", encoding="utf-8")
    assert count_interview_records(str(tmp_path)) == 2


def test_get_stats_aggregates(memory, tmp_path, monkeypatch):
    monkeypatch.setattr("config.OBSIDIAN_VAULT_DIR", str(tmp_path))
    # 造一个笔记 + 一个面试记录
    (tmp_path / "笔记.md").write_text("# 测试", encoding="utf-8")
    record_dir = tmp_path / "模拟面试" / "面试记录"
    record_dir.mkdir(parents=True, exist_ok=True)
    (record_dir / "2026-08-13.md").write_text("记录", encoding="utf-8")
    memory.save_mbti_result(1, "INTJ", "后端", {})
    memory.register_user("alice", "alice@test.com", "secret123")

    stats = get_stats(memory, 1)
    assert stats["interview_count"] == 1
    assert stats["mbti_count"] == 1
    assert stats["session_count"] >= 1
