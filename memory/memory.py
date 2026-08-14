import os
import secrets
import sqlite3
from contextlib import suppress
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt as pyjwt

from utils.logger import get_logger

logger = get_logger(__name__)

# JWT 配置
_JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))
_JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

class Memory:
    def __init__(self, db_path: str = None):
        # 允许测试时用环境变量覆盖数据库路径（性能测试隔离用），默认 memory/chat_history.db
        self.db_path = db_path or os.getenv("MEMORY_DB_PATH", "memory/chat_history.db")
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        """统一 SQLite 连接工厂（生产级配置，长期有效）。

        - journal_mode=WAL：读写分离，读不阻塞写、写不阻塞读，显著降低并发写锁竞争
        - busy_timeout=5000：写锁被占时等待而非立即报错（database is locked）
        - synchronous=NORMAL：WAL 下崩溃安全性与性能的平衡点（官方推荐）
        - foreign_keys=ON：启用外键约束

        所有 SQLite 操作必须通过此工厂获取连接，不要直接 sqlite3.connect()。
        """
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,          -- 'user' 或 'assistant'
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_id ON conversations (session_id)")
            # 会话摘要表：存储"滚动摘要"，把旧对话压缩成一段文字，节省上下文 token
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_summaries (
                    session_id TEXT PRIMARY KEY,
                    summary TEXT NOT NULL,
                    compressed_until_id INTEGER NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # 用户表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL DEFAULT '',
                    display_name TEXT DEFAULT '',
                    github_id TEXT DEFAULT '',
                    avatar_url TEXT DEFAULT '',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # 迁移：旧表可能缺少 github 相关列
            for col, col_def in [
                ("github_id", "TEXT DEFAULT ''"),
                ("avatar_url", "TEXT DEFAULT ''"),
            ]:
                with suppress(sqlite3.OperationalError):
                    cursor.execute(
                        f"ALTER TABLE users ADD COLUMN {col} {col_def}"
                    )
            # 认证令牌表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auth_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token TEXT UNIQUE NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            # 迁移：旧表可能没有 expires_at 列
            with suppress(sqlite3.OperationalError):
                cursor.execute("ALTER TABLE auth_tokens ADD COLUMN expires_at DATETIME")
            # 用户会话映射表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    session_id TEXT NOT NULL UNIQUE,
                    label TEXT DEFAULT 'default',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            # 用户级 LLM 密钥表（前端切换器用，每个用户可填自己的各厂商 key）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_llm_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    provider TEXT NOT NULL,           -- deepseek | glm | qwen | yi
                    api_key TEXT NOT NULL,
                    base_url TEXT DEFAULT '',
                    model TEXT DEFAULT '',
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, provider),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            # MBTI 测试结果表（存档 + 多次对比）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mbti_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    mbti TEXT NOT NULL,
                    ideal_role TEXT DEFAULT '',
                    scores TEXT DEFAULT '',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            conn.commit()

    def save_message(self, session_id: str, role: str, content: str):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO conversations (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content)
            )
            conn.commit()

    def save_messages_batch(self, session_id: str, messages: list[tuple[str, str]]):
        """批量保存多条消息（单事务，显著减少写放大）。

        Args:
            session_id: 会话 ID
            messages: [(role, content), ...] 列表，按传入顺序落库

        相比逐条 save_message（每条一次 commit），批量写入把 N 次
        独立事务合并为 1 次，高并发下大幅降低 SQLite 写锁竞争。
        """
        if not messages:
            return
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                "INSERT INTO conversations (session_id, role, content) VALUES (?, ?, ?)",
                [(session_id, role, content) for role, content in messages],
            )
            conn.commit()

    def load_history(self, session_id: str, limit: int = 20) -> list[dict[str, str]]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT role, content FROM conversations"
                " WHERE session_id = ? AND role IN ('user', 'assistant')"
                " ORDER BY id DESC LIMIT ?",
                (session_id, limit)
            )
            rows = cursor.fetchall()
            return [{"role": row[0], "content": row[1]} for row in rows[::-1]]

    # ========== 会话摘要（上下文压缩） ==========

    def count_messages(self, session_id: str) -> int:
        """统计某会话的消息总数（用于判断是否触发压缩）"""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM conversations WHERE session_id = ?",
                (session_id,),
            )
            return cursor.fetchone()[0]

    def get_messages_range(self, session_id: str, after_id: int = 0,
                           limit: int = 200) -> list[dict]:
        """按时间顺序获取指定 id 之后的消息（含 id，供压缩定位边界）。

        Returns:
            [{"id": int, "role": str, "content": str}, ...]
        """
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, role, content FROM conversations"
                " WHERE session_id = ? AND id > ? AND role IN ('user', 'assistant')"
                " ORDER BY id ASC LIMIT ?",
                (session_id, after_id, limit),
            )
            return [
                {"id": r[0], "role": r[1], "content": r[2]}
                for r in cursor.fetchall()
            ]

    def get_session_summary(self, session_id: str) -> dict | None:
        """获取会话摘要，返回 {"summary": str, "compressed_until_id": int} 或 None"""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT summary, compressed_until_id FROM session_summaries WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return {"summary": row[0], "compressed_until_id": row[1]}

    def save_session_summary(self, session_id: str, summary: str, until_id: int):
        """保存会话摘要（upsert）"""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO session_summaries (session_id, summary, compressed_until_id, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(session_id) DO UPDATE SET
                    summary = excluded.summary,
                    compressed_until_id = excluded.compressed_until_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (session_id, summary, until_id),
            )
            conn.commit()

    def create_session(self, user_id: int, label: str = "") -> str:
        """创建新会话，返回 session_id"""
        import uuid
        session_id = f"u{user_id}_{uuid.uuid4().hex[:12]}"
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO user_sessions (user_id, session_id, label) VALUES (?, ?, ?)",
                (user_id, session_id, label or "新对话"),
            )
            conn.commit()
        return session_id

    def delete_session(self, session_id: str):
        """删除会话及其所有消息"""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM session_summaries WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM user_sessions WHERE session_id = ?", (session_id,))
            conn.commit()

    def clear_session(self, session_id: str):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM conversations WHERE session_id = ?",
                (session_id,)
            )
            cursor.execute(
                "DELETE FROM session_summaries WHERE session_id = ?",
                (session_id,)
            )
            conn.commit()

    # ========== 用户认证 ==========

    @staticmethod
    def _hash_password(password: str) -> str:
        """bcrypt 哈希密码（自动加盐）"""
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def _check_password(password: str, hashed: str) -> bool:
        """验证密码。

        守卫：空/非 bcrypt 格式的 hash（如 GitHub OAuth 创建的账号没有本地密码）
        直接返回 False，避免 bcrypt.checkpw 抛 ValueError（Invalid salt）导致 500。
        """
        if not hashed or not hashed.startswith("$2"):
            return False
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except (ValueError, TypeError):
            return False

    def _generate_jwt(self, user_id: int) -> tuple[str, str]:
        """生成 JWT token + 过期时间字符串，返回 (token, expires_at_iso)。

        带随机 jti（JWT ID），保证同一秒内多次签发 token 也不重复，
        避免 auth_tokens.token 的 UNIQUE 约束冲突。
        """
        import uuid

        now = datetime.now(UTC)
        exp = now + timedelta(hours=_JWT_EXPIRE_HOURS)
        token = pyjwt.encode(
            {"sub": str(user_id), "iat": now, "exp": exp, "jti": uuid.uuid4().hex},
            _JWT_SECRET,
            algorithm="HS256",
        )
        return token, exp.isoformat()

    def _decode_jwt(self, token: str) -> int | None:
        """解码 JWT，返回 user_id 或 None（过期/无效返回 None）。"""
        try:
            payload = pyjwt.decode(token, _JWT_SECRET, algorithms=["HS256"])
            return int(payload["sub"])
        except (pyjwt.ExpiredSignatureError, pyjwt.InvalidTokenError, KeyError, ValueError):
            return None

    def register_user(self, username: str, email: str, password: str) -> tuple[bool, str]:
        """注册新用户，返回 (成功?, 消息或token)"""
        password_hash = self._hash_password(password)
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                    (username, email, password_hash),
                )
                user_id = cursor.lastrowid
                # 创建默认 session
                default_session = f"u{user_id}_default"
                cursor.execute(
                    "INSERT INTO user_sessions (user_id, session_id) VALUES (?, ?)",
                    (user_id, default_session),
                )
                # 生成 JWT token
                token, expires_at = self._generate_jwt(user_id)
                cursor.execute(
                    "INSERT INTO auth_tokens (user_id, token, expires_at) VALUES (?, ?, ?)",
                    (user_id, token, expires_at),
                )
                conn.commit()
            return True, token
        except sqlite3.IntegrityError as e:
            msg = str(e)
            if "username" in msg:
                return False, "用户名已存在"
            if "email" in msg:
                return False, "邮箱已被注册"
            return False, "注册失败"

    def login_user(self, username: str, password: str) -> tuple[bool, str]:
        """用户登录，返回 (成功?, 消息或token)"""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, password_hash FROM users WHERE username = ? OR email = ?",
                (username, username),
            )
            row = cursor.fetchone()
            if row is None:
                return False, "用户名/邮箱或密码错误"
            user_id, pw_hash = row[0], row[1]
            if not self._check_password(password, pw_hash):
                return False, "用户名/邮箱或密码错误"
            # 生成 JWT token
            token, expires_at = self._generate_jwt(user_id)
            cursor.execute(
                "INSERT INTO auth_tokens (user_id, token, expires_at) VALUES (?, ?, ?)",
                (user_id, token, expires_at),
            )
            conn.commit()
        return True, token

    def github_login_or_create_user(
        self, github_id: str, username: str, email: str, display_name: str,
        avatar_url: str = "",
    ) -> tuple[bool, str]:
        """GitHub OAuth 登录：已有 github_id 直接登录，否则创建新用户。"""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE github_id = ?", (github_id,))
            row = cursor.fetchone()
            if row:
                user_id = row[0]
            else:
                safe_username = username
                cursor.execute("SELECT id FROM users WHERE username = ?", (safe_username,))
                if cursor.fetchone():
                    safe_username = f"{username}_{github_id}"
                safe_email = email or f"github_{github_id}@github.user"
                try:
                    cursor.execute(
                        "INSERT INTO users (username, email, password_hash,"
                        " display_name, github_id, avatar_url)"
                        " VALUES (?, ?, '', ?, ?, ?)",
                        (safe_username, safe_email, display_name, github_id, avatar_url),
                    )
                    user_id = cursor.lastrowid
                    cursor.execute(
                        "INSERT INTO user_sessions (user_id, session_id) VALUES (?, ?)",
                        (user_id, f"u{user_id}_default"),
                    )
                except sqlite3.IntegrityError:
                    return False, "用户名或邮箱冲突"
            token, expires_at = self._generate_jwt(user_id)
            cursor.execute(
                "INSERT INTO auth_tokens (user_id, token, expires_at) VALUES (?, ?, ?)",
                (user_id, token, expires_at),
            )
            conn.commit()
        return True, token

    def verify_token(self, token: str) -> int | None:
        """验证 token（JWT + 数据库双重校验，自动清理过期 token）。"""
        if not token:
            return None
        user_id = self._decode_jwt(token)
        if user_id is None:
            return None
        # 数据库校验（防止 token 已被吊销）
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT user_id FROM auth_tokens WHERE token = ?",
                (token,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        # 定期清理过期 token
        try:
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM auth_tokens WHERE expires_at IS NOT NULL AND expires_at < datetime('now')",
                )
                conn.commit()
        except Exception:
            pass
        return user_id

    def get_user_info(self, user_id: int) -> dict | None:
        """获取用户信息"""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, username, email, display_name, created_at FROM users WHERE id = ?",
                (user_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return {
                "id": row[0],
                "username": row[1],
                "email": row[2],
                "display_name": row[3] or row[1],
                "created_at": str(row[4]) if row[4] else "",
            }

    def update_display_name(self, user_id: int, new_name: str) -> bool:
        """更新显示名称"""
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET display_name = ? WHERE id = ?",
                    (new_name, user_id),
                )
                conn.commit()
                return True
        except Exception:
            return False

    def update_password(self, user_id: int, old_password: str, new_password: str) -> tuple[bool, str]:
        """修改密码：验证旧密码 -> 更新新密码（bcrypt）"""
        new_hash = self._hash_password(new_password)
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT password_hash FROM users WHERE id = ?",
                (user_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return False, "用户不存在"
            if not self._check_password(old_password, row[0]):
                return False, "旧密码错误"
            cursor.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (new_hash, user_id),
            )
            conn.commit()
            return True, "密码修改成功"

    def revoke_token(self, token: str):
        """登出：删除 token"""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))
            conn.commit()

    def get_user_default_session(self, user_id: int) -> str | None:
        """获取用户的默认 session_id"""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT session_id FROM user_sessions WHERE user_id = ? AND label = 'default'",
                (user_id,),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def get_user_sessions(self, user_id: int) -> list[dict]:
        """获取用户的所有 session 列表（含预览和消息数）"""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT s.session_id, s.label, s.created_at, (SELECT content FROM conversations WHERE session_id = s.session_id AND role = 'user' ORDER BY id DESC LIMIT 1) as last_msg, (SELECT COUNT(*) FROM conversations WHERE session_id = s.session_id) as msg_count FROM user_sessions s WHERE s.user_id = ? ORDER BY s.created_at DESC",
                (user_id,),
            )
            return [
                {
                    "session_id": r[0],
                    "label": r[1],
                    "created_at": str(r[2]) if r[2] else "",
                    "preview": (r[3] or "")[:60],
                    "msg_count": r[4] or 0,
                }
                for r in cursor.fetchall()
            ]

    def update_session_label(self, user_id: int, session_id: str, label: str) -> bool:
        """修改会话标题（校验用户归属）。"""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE user_sessions SET label = ? WHERE user_id = ? AND session_id = ?",
                (label, user_id, session_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_session_label(self, user_id: int, session_id: str) -> str:
        """获取会话标题（校验归属，不存在返回空串）。"""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT label FROM user_sessions WHERE user_id = ? AND session_id = ?",
                (user_id, session_id),
            )
            row = cursor.fetchone()
            return row[0] if row else ""

    def get_session_messages(self, session_id: str, limit: int = 200) -> list[dict]:
        """获取会话完整消息（正序：最早 → 最新）。

        注意：load_history 已通过 rows[::-1] 返回正序，这里不要再反转。
        """
        return self.load_history(session_id, limit=limit)

    # ========== 用户级 LLM 密钥 ==========

    def set_user_llm_key(self, user_id: int, provider: str, api_key: str,
                         base_url: str = "", model: str = "") -> bool:
        """保存（upsert）某用户的某厂商 LLM 密钥"""
        provider = (provider or "").lower().strip()
        if provider not in ("deepseek", "glm", "qwen", "yi"):
            return False
        if not api_key or not api_key.strip():
            return False
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO user_llm_keys (user_id, provider, api_key, base_url, model, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(user_id, provider) DO UPDATE SET
                        api_key = excluded.api_key,
                        base_url = excluded.base_url,
                        model = excluded.model,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (user_id, provider, api_key.strip(), base_url.strip(), model.strip()),
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error("保存用户 LLM key 失败: %s", e)
            return False

    def get_user_llm_key(self, user_id: int, provider: str) -> dict | None:
        """获取某用户某厂商的真实密钥（仅聊天调用内部使用，不外发）"""
        provider = (provider or "").lower().strip()
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT api_key, base_url, model FROM user_llm_keys WHERE user_id = ? AND provider = ?",
                (user_id, provider),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return {
                "api_key": row[0],
                "base_url": row[1] or "",
                "model": row[2] or "",
            }

    def get_user_llm_keys(self, user_id: int) -> list[dict]:
        """返回某用户已配置的所有厂商（脱敏，不返回真实 key）"""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT provider, api_key, base_url, model, updated_at FROM user_llm_keys WHERE user_id = ? ORDER BY provider",
                (user_id,),
            )
            result = []
            for r in cursor.fetchall():
                key = r[1] or ""
                masked = key[-4:] if len(key) >= 4 else "****"
                result.append({
                    "provider": r[0],
                    "api_key_masked": f"****{masked}",
                    "base_url": r[2] or "",
                    "model": r[3] or "",
                    "updated_at": str(r[4]) if r[4] else "",
                })
            return result

    def delete_user_llm_key(self, user_id: int, provider: str) -> bool:
        """删除某用户的某厂商密钥"""
        provider = (provider or "").lower().strip()
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM user_llm_keys WHERE user_id = ? AND provider = ?",
                (user_id, provider),
            )
            conn.commit()
            return cursor.rowcount > 0

    # ========== MBTI 测试结果存档 ==========

    def save_mbti_result(self, user_id: int, mbti: str, ideal_role: str,
                         scores: dict) -> bool:
        """保存一次 MBTI 测试结果（scores 存 JSON 字符串）"""
        import json

        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO mbti_results (user_id, mbti, ideal_role, scores)"
                    " VALUES (?, ?, ?, ?)",
                    (user_id, mbti, ideal_role, json.dumps(scores, ensure_ascii=False)),
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error("保存 MBTI 结果失败: %s", e)
            return False

    def get_mbti_history(self, user_id: int, limit: int = 20) -> list[dict]:
        """获取某用户的 MBTI 测试历史（最新在前）"""
        import json

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT mbti, ideal_role, scores, created_at FROM mbti_results"
                " WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            )
            result = []
            for r in cursor.fetchall():
                try:
                    scores = json.loads(r[2]) if r[2] else {}
                except Exception:
                    scores = {}
                result.append({
                    "mbti": r[0],
                    "ideal_role": r[1] or "",
                    "scores": scores,
                    "created_at": str(r[3]) if r[3] else "",
                })
            return result

    def count_mbti_results(self, user_id: int) -> int:
        """统计某用户 MBTI 测试次数"""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM mbti_results WHERE user_id = ?",
                (user_id,),
            )
            return cursor.fetchone()[0]
