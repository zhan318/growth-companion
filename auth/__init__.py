"""认证模块：封装用户注册、登录、token 验证"""

import httpx

from memory.memory import Memory

_memory = Memory()


# ═══════════════════════════════════════════
#  GitHub OAuth2.0
# ═══════════════════════════════════════════

GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"


def github_get_auth_url(client_id: str, redirect_uri: str, state: str = "") -> str:
    """生成 GitHub OAuth 授权地址。"""
    from urllib.parse import urlencode

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "read:user user:email",
        "state": state,
    }
    return f"{GITHUB_AUTH_URL}?{urlencode(params)}"


def github_exchange_code(code: str, client_id: str, client_secret: str) -> str | None:
    """用 authorization code 换 access token。"""

    resp = httpx.post(
        GITHUB_TOKEN_URL,
        json={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
        },
        headers={"Accept": "application/json"},
        timeout=10,
    )
    if resp.status_code != 200:
        return None
    data = resp.json()
    return data.get("access_token")


def github_get_user(access_token: str) -> dict | None:
    """通过 access token 获取 GitHub 用户信息（含主邮箱）。"""

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    # 先拿基本信息
    user_resp = httpx.get(GITHUB_USER_URL, headers=headers, timeout=10)
    if user_resp.status_code != 200:
        return None
    user_data = user_resp.json()
    # GitHub 的 user 接口不一定返回 email（如果设为隐私），需单独请求
    email = user_data.get("email", "")
    if not email:
        emails_resp = httpx.get(GITHUB_EMAILS_URL, headers=headers, timeout=10)
        if emails_resp.status_code == 200:
            for e in emails_resp.json():
                if e.get("primary") and e.get("verified"):
                    email = e["email"]
                    break
            if not email and emails_resp.json():
                email = emails_resp.json()[0].get("email", "")
    return {
        "github_id": str(user_data.get("id", "")),
        "username": user_data.get("login", ""),
        "email": email,
        "display_name": user_data.get("name") or user_data.get("login", ""),
        "avatar_url": user_data.get("avatar_url", ""),
    }


def github_login(github_id: str, username: str, email: str,
                 display_name: str, avatar_url: str = "") -> tuple[bool, str]:
    """GitHub OAuth 登录/注册，返回 (成功?, token 或错误消息)"""
    return _memory.github_login_or_create_user(
        github_id, username, email, display_name, avatar_url,
    )


def register(username: str, email: str, password: str) -> tuple[bool, str]:
    """注册新用户，返回 (成功?, token或错误消息)"""
    return _memory.register_user(username, email, password)


def login(username: str, password: str) -> tuple[bool, str]:
    """用户登录，返回 (成功?, token或错误消息)"""
    return _memory.login_user(username, password)


def logout(token: str):
    """登出：吊销 token"""
    _memory.revoke_token(token)


def verify_token(token: str) -> int | None:
    """验证 token，返回 user_id 或 None"""
    return _memory.verify_token(token)


def get_user_info(user_id: int) -> dict | None:
    """获取用户信息"""
    return _memory.get_user_info(user_id)


def update_display_name(user_id: int, new_name: str) -> bool:
    """更新显示名称"""
    return _memory.update_display_name(user_id, new_name)


def update_password(user_id: int, old_password: str, new_password: str) -> tuple[bool, str]:
    """修改密码"""
    return _memory.update_password(user_id, old_password, new_password)


def get_user_sessions_list(user_id: int) -> list:
    """获取用户会话列表"""
    return _memory.get_user_sessions(user_id)


def create_new_session(user_id: int, label: str = "") -> str:
    """创建新会话"""
    return _memory.create_session(user_id, label)


def delete_user_session(user_id: int, session_id: str) -> bool:
    """删除会话（仅当会话属于该用户）。返回是否成功删除"""
    sessions = _memory.get_user_sessions(user_id)
    if not any(s["session_id"] == session_id for s in sessions):
        return False
    _memory.delete_session(session_id)
    return True


def get_default_session(user_id: int) -> str | None:
    """获取用户的默认 session_id"""
    return _memory.get_user_default_session(user_id)


def get_session_history(user_id: int, session_id: str, limit: int = 200) -> list | None:
    """获取指定 session 的历史消息（先验证归属，返回 None 表示无权或不存在）"""
    sessions = _memory.get_user_sessions(user_id)
    if not any(s["session_id"] == session_id for s in sessions):
        return None
    return _memory.load_history(session_id, limit=limit)
