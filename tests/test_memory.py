"""测试 Memory 层：用户认证 + 会话摘要（上下文压缩的存储部分）"""


# ── 认证 ──

def test_register_returns_token(memory):
    ok, token = memory.register_user("alice", "alice@test.com", "secret123")
    assert ok is True
    assert token  # 非空 token


def test_register_duplicate_username(memory):
    memory.register_user("alice", "alice@test.com", "secret123")
    ok, msg = memory.register_user("alice", "other@test.com", "secret123")
    assert ok is False
    assert "用户名" in msg


def test_register_duplicate_email(memory):
    memory.register_user("alice", "alice@test.com", "secret123")
    ok, msg = memory.register_user("bob", "alice@test.com", "secret123")
    assert ok is False
    assert "邮箱" in msg


def test_login_success_and_wrong_password(memory):
    memory.register_user("alice", "alice@test.com", "secret123")
    ok, token = memory.login_user("alice", "secret123")
    assert ok is True
    assert token
    ok, msg = memory.login_user("alice", "wrong")
    assert ok is False


def test_login_by_email(memory):
    memory.register_user("alice", "alice@test.com", "secret123")
    ok, _ = memory.login_user("alice@test.com", "secret123")
    assert ok is True


def test_verify_token_roundtrip(memory):
    _, token = memory.register_user("alice", "alice@test.com", "secret123")
    uid = memory.verify_token(token)
    assert uid is not None
    assert uid > 0


def test_verify_invalid_token(memory):
    assert memory.verify_token("") is None
    assert memory.verify_token("nonexistent-token") is None


def test_update_password(memory):
    _, token = memory.register_user("alice", "alice@test.com", "oldpass123")
    uid = memory.verify_token(token)
    # 旧密码错误 → 拒绝
    ok, msg = memory.update_password(uid, "wrongpass", "newpass123")
    assert ok is False
    # 旧密码正确 → 成功
    ok, msg = memory.update_password(uid, "oldpass123", "newpass123")
    assert ok is True
    # 用新密码登录
    ok, _ = memory.login_user("alice", "newpass123")
    assert ok is True


def test_revoke_token(memory):
    _, token = memory.register_user("alice", "alice@test.com", "secret123")
    memory.revoke_token(token)
    assert memory.verify_token(token) is None


# ── 会话摘要（上下文压缩存储） ──

def test_summary_save_and_get(memory):
    assert memory.get_session_summary("s1") is None
    memory.save_session_summary("s1", "用户在学 Python", 10)
    s = memory.get_session_summary("s1")
    assert s["summary"] == "用户在学 Python"
    assert s["compressed_until_id"] == 10


def test_summary_upsert(memory):
    memory.save_session_summary("s1", "旧摘要", 10)
    memory.save_session_summary("s1", "新摘要", 20)
    s = memory.get_session_summary("s1")
    assert s["summary"] == "新摘要"
    assert s["compressed_until_id"] == 20


def test_count_messages(memory):
    assert memory.count_messages("s1") == 0
    memory.save_message("s1", "user", "hi")
    memory.save_message("s1", "assistant", "hello")
    assert memory.count_messages("s1") == 2


def test_get_messages_range(memory):
    for i in range(5):
        memory.save_message("s1", "user" if i % 2 == 0 else "assistant", f"m{i}")
    msgs = memory.get_messages_range("s1", after_id=0)
    assert len(msgs) == 5
    # 升序，含 id
    assert msgs[0]["id"] == 1
    assert msgs[-1]["id"] == 5
    # after_id 过滤
    msgs2 = memory.get_messages_range("s1", after_id=2)
    assert len(msgs2) == 3
    assert msgs2[0]["id"] == 3


def test_clear_session_removes_summary(memory):
    memory.save_message("s1", "user", "hi")
    memory.save_session_summary("s1", "摘要", 1)
    memory.clear_session("s1")
    assert memory.get_session_summary("s1") is None
    assert memory.count_messages("s1") == 0


def test_delete_session_removes_summary(memory):
    memory.register_user("alice", "alice@test.com", "secret123")
    memory.save_session_summary("s1", "摘要", 1)
    memory.delete_session("s1")
    assert memory.get_session_summary("s1") is None
