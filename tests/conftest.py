"""pytest 共享配置：统一 sys.path + 提供隔离的临时数据库 fixture"""

import sys
from pathlib import Path

import pytest

# 确保项目根目录在 sys.path（无论从哪个目录运行 pytest 都能 import 到项目模块）
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory.memory import Memory  # noqa: E402


@pytest.fixture
def memory(tmp_path):
    """返回一个使用临时数据库的 Memory 实例（测试间互不污染）。

    预置测试用户（id=1）：启用外键约束（foreign_keys=ON）后，
    mbti_results/user_sessions 等表引用 users.id，插入前必须存在对应用户。
    """
    db = tmp_path / "test_history.db"
    m = Memory(db_path=str(db))
    with m._connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, username, email) VALUES (1, 'test', 'test@test.local')"
        )
        # 预置默认会话：register_user 自增创建的用户 id>=2，
        # user 1 需自带 session 才满足 get_stats 的 session_count>=1 断言
        conn.execute(
            "INSERT OR IGNORE INTO user_sessions (user_id, session_id) VALUES (1, 'u1_default')"
        )
        conn.commit()
    return m
