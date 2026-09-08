import asyncio
import json
import os
import re
import shutil
import threading
import time
from collections import OrderedDict, defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel

from agent.agent import Agent
from auth import create_new_session as auth_create_session
from auth import delete_user_session as auth_delete_session
from auth import (
    get_default_session,
    github_exchange_code,
    github_get_auth_url,
    github_get_user,
    github_login,
    verify_token,
)
from auth import get_session_history as auth_get_session_history
from auth import get_user_info as auth_get_user_info
from auth import get_user_sessions_list as auth_get_sessions
from auth import login as auth_login
from auth import logout as auth_logout
from auth import register as auth_register
from auth import update_display_name as auth_update_display_name
from auth import update_password as auth_update_password
from chatbot.chatbot import get_available_models
from knowledge.pipeline import index_documents, index_obsidian
from knowledge.pipeline import query as rag_query
from memory.memory import Memory
from utils.logger import get_logger

logger = get_logger(__name__)

# 用户级 LLM 密钥存储（建表在 Memory.__init__ 中完成）
memory = Memory()

# ═══════════════════════════════════════════
#  统一错误响应格式
# ═══════════════════════════════════════════

def error_response(status_code: int, code: str, message: str, detail: str = "") -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "detail": detail or message,
            }
        },
    )


app = FastAPI(
    title="成长智伴 API",
    description="基于 DeepSeek + RAG 的智能 Agent 服务",
    version="1.0.0"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时自动索引 Obsidian + 启动文件监视器；关闭时清理资源"""
    from pathlib import Path

    from config import OBSIDIAN_VAULT_DIR

    # ── startup ──
    # 关键配置校验：JWT_SECRET 必须固定，否则重启后所有已签发 token 失效（前端 401）。
    # 生产环境直接阻断启动，本地开发仅告警（避免本地随手跑时被卡死）。
    from memory.memory import JWT_SECRET_CONFIGURED
    if not JWT_SECRET_CONFIGURED:
        _is_prod = bool(
            os.getenv("RENDER") or os.getenv("VERCEL")
            or os.getenv("ENVIRONMENT", "").lower() == "production"
        )
        if _is_prod:
            raise RuntimeError(
                "JWT_SECRET 未配置：生产环境必须显式设置 JWT_SECRET，"
                "否则每次启动都会随机生成密钥，重启后所有登录 token 失效。"
            )
        logger.warning(
            "JWT_SECRET 未在 .env 中配置，已使用随机生成的临时密钥；"
            "重启服务后所有已签发 token 将失效（前端会 401）。"
            "建议在 .env 固定 JWT_SECRET：python -c \"import secrets; print(secrets.token_hex(32))\""
        )

    if OBSIDIAN_VAULT_DIR and Path(OBSIDIAN_VAULT_DIR).exists():
        try:
            from config import OBSIDIAN_COLLECTION
            from knowledge.vector_store import get_vector_store
            store = get_vector_store(OBSIDIAN_COLLECTION)
            if store.count() == 0:
                logger.info("Obsidian collection 为空，启动时自动索引...")
                result = index_obsidian(force=False)
                logger.info(
                    "Obsidian 启动索引完成: %d 文件 / %d 切片",
                    result.get("indexed_files", 0), result.get("chunks", 0),
                )
        except Exception as e:
            logger.warning("Obsidian 启动自动索引失败（不影响主服务）: %s", e)
    try:
        from knowledge.obsidian_watcher import start_obsidian_watcher
        start_obsidian_watcher()
    except Exception as e:
        logger.warning("启动 Obsidian 监视器失败（不影响主服务）: %s", e)

    # ── 连接 MCP servers 并注册工具（若已配置 mcp_config.json）──
    try:
        from mcp_client import get_mcp_manager, register_mcp_tools
        mcp = get_mcp_manager()
        # 首次启动需下载 npx server 包，给足超时时间
        mcp.start(timeout=90)
        register_mcp_tools(mcp)
    except Exception as e:
        logger.warning("启动 MCP 客户端失败（不影响主服务）: %s", e)

    yield  # 应用运行中

    # ── shutdown ──
    pass


app.router.lifespan_context = lifespan

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════
#  请求日志中间件
# ═══════════════════════════════════════════

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000
    logger.info(
        "%s %s → %d (%.0fms)",
        request.method, request.url.path, response.status_code, duration_ms,
    )
    return response


# ═══════════════════════════════════════════
#  全局异常处理
# ═══════════════════════════════════════════

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.warning("HTTP异常 %d: %s %s", exc.status_code, request.method, request.url.path)
    return error_response(exc.status_code, "HTTP_ERROR", exc.detail)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("未处理异常 %s %s: %s", request.method, request.url.path, exc)
    return error_response(500, "INTERNAL_ERROR", "服务器内部错误", str(exc))


# ═══════════════════════════════════════════
#  Rate Limiting（内存实现，无需额外依赖）
# ═══════════════════════════════════════════

_rate_limit_store: dict[str, list] = defaultdict(list)
_RATE_LIMIT_WINDOW = 60       # 窗口（秒）
# 窗口内最大请求数（支持环境变量覆盖，性能测试时临时调高；默认 30）
_RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "30"))
_RATE_SENSITIVE_MAX = 5       # 敏感接口（登录/注册）窗口内最大请求数

_SENSITIVE_PATHS = {"/auth/login", "/auth/register"}


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window = _RATE_LIMIT_WINDOW
    max_req = _RATE_SENSITIVE_MAX if request.url.path in _SENSITIVE_PATHS else _RATE_LIMIT_MAX

    # 清理窗口外的旧记录
    key = f"{client_ip}:{request.url.path}"
    _rate_limit_store[key] = [t for t in _rate_limit_store[key] if now - t < window]

    if len(_rate_limit_store[key]) >= max_req:
        logger.warning("限流触发: %s %s", client_ip, request.url.path)
        return error_response(429, "RATE_LIMITED", "请求过于频繁，请稍后再试")

    _rate_limit_store[key].append(now)
    return await call_next(request)

# ═══════════════════════════════════════════
#  Agent 实例池（LRU 上限管理，防止无上限增长导致内存膨胀）
# ═══════════════════════════════════════════

_AGENT_POOL_MAX = int(os.getenv("AGENT_POOL_MAX", "200"))
_pool_lock = threading.Lock()


class AgentPool:
    """按 session_id 管理的 Agent 实例池（LRU 淘汰）。

    - 命中 session 时移到队尾（最近使用）
    - 超上限时淘汰最久未用的实例（队首）
    - 线程安全（FastAPI 并发请求）
    - 淘汰只释放内存中的实例壳，**不清任何数据**（历史在 SQLite，向量记忆在 Chroma）
    """

    def __init__(self, max_size: int = _AGENT_POOL_MAX):
        self._pool: OrderedDict[str, Agent] = OrderedDict()
        self.max_size = max(1, max_size)

    def get(self, session_id: str) -> Agent:
        with _pool_lock:
            agent = self._pool.get(session_id)
            if agent is not None:
                # 命中：标记为最近使用
                self._pool.move_to_end(session_id)
                return agent
            # 未命中：创建并加入
            agent = Agent(session_id)
            self._pool[session_id] = agent
            self._evict_if_needed()
            return agent

    def _evict_if_needed(self):
        """超出容量时淘汰最久未用的实例（不删除任何持久化数据）。"""
        while len(self._pool) > self.max_size:
            _, evicted = self._pool.popitem(last=False)  # 队首 = 最久未用
            logger.info("Agent 池淘汰实例: %s（当前 %d/%d）", evicted.session_id, len(self._pool), self.max_size)

    def size(self) -> int:
        with _pool_lock:
            return len(self._pool)

    def clear(self):
        """清空池（测试/运维用）"""
        with _pool_lock:
            self._pool.clear()


_agent_pool = AgentPool()


def get_agent(session_id: str) -> Agent:
    """按 session_id 获取或创建 Agent 实例（LRU 池，上限 _AGENT_POOL_MAX）"""
    return _agent_pool.get(session_id)


# ═══════════════════════════════════════════
#  数据模型
# ═══════════════════════════════════════════

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default_session"
    model_provider: str = "deepseek"
    mode: str = "workspace"  # workspace | interview


class LLMKeyRequest(BaseModel):
    """用户级 LLM 密钥：前端切换器用，每个用户可填自己的各厂商 key"""
    provider: str                       # deepseek | glm | qwen
    api_key: str
    base_url: str = ""                  # 可选，缺省用该厂商默认 base_url
    model: str = ""                     # 可选，缺省用该厂商默认模型


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    model_provider: str = "deepseek"


class AuthRegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class AuthLoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    success: bool
    message: str = ""
    token: str = ""
    session_id: str = ""
    user_id: int = 0


class UpdateProfileRequest(BaseModel):
    display_name: str


class UpdatePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class UserProfileResponse(BaseModel):
    id: int
    username: str
    email: str
    display_name: str
    created_at: str = ""


class KnowledgeQueryRequest(BaseModel):
    question: str


class KnowledgeQueryResponse(BaseModel):
    answer: str


class MBTIAnalyzeRequest(BaseModel):
    ideal_role: str
    answers: list[int]


class MBTIExportRequest(BaseModel):
    mbti: str
    ideal_role: str = ""
    analysis: str = ""
    scores: dict = {}


class InterviewSaveRequest(BaseModel):
    session_id: str


class NoteSaveRequest(BaseModel):
    title: str = ""
    content: str


class SessionUpdateRequest(BaseModel):
    label: str


class SessionSaveRequest(BaseModel):
    session_id: str


# ═══════════════════════════════════════════
#  通用接口
# ═══════════════════════════════════════════

# ═══════════════════════════════════════════
#  认证依赖
# ═══════════════════════════════════════════

async def get_current_user(authorization: str = Header("")):
    """从 Authorization header 解析用户"""
    if not authorization:
        raise HTTPException(status_code=401, detail="未提供认证信息")
    token = authorization.replace("Bearer ", "").strip()
    user_id = verify_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="token 无效或已过期")
    return user_id


# ═══════════════════════════════════════════
#  认证接口
# ═══════════════════════════════════════════

@app.post("/auth/register", response_model=AuthResponse)
async def register_endpoint(request: AuthRegisterRequest):
    """用户注册"""
    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    success, result = auth_register(request.username, request.email, request.password)
    if not success:
        raise HTTPException(status_code=400, detail=result)
    # result is token
    user_id = verify_token(result)
    session_id = get_default_session(user_id) or f"u{user_id}_default"
    return AuthResponse(success=True, token=result, session_id=session_id, user_id=user_id, message="注册成功")


@app.post("/auth/login", response_model=AuthResponse)
async def login_endpoint(request: AuthLoginRequest):
    """用户登录"""
    success, result = auth_login(request.username, request.password)
    if not success:
        raise HTTPException(status_code=401, detail=result)
    user_id = verify_token(result)
    session_id = get_default_session(user_id) or f"u{user_id}_default"
    return AuthResponse(success=True, token=result, session_id=session_id, user_id=user_id, message="登录成功")


@app.post("/auth/logout")
async def logout_endpoint(authorization: str = Header("")):
    """用户登出"""
    token = authorization.replace("Bearer ", "").strip()
    auth_logout(token)
    return {"success": True, "message": "已登出"}


# ========== GitHub OAuth2.0 登录 ==========

@app.get("/auth/github/login")
async def github_login_endpoint():
    """跳转到 GitHub 授权页面。"""
    from uuid import uuid4

    from config import GITHUB_CLIENT_ID, GITHUB_REDIRECT_URI

    if not GITHUB_CLIENT_ID:
        raise HTTPException(status_code=501, detail="GitHub OAuth 未配置（请在 .env 中设置 GITHUB_CLIENT_ID）")
    state = uuid4().hex[:16]
    url = github_get_auth_url(GITHUB_CLIENT_ID, GITHUB_REDIRECT_URI, state)
    return RedirectResponse(url)


@app.get("/auth/github/callback")
async def github_callback_endpoint(code: str = "", state: str = ""):
    """GitHub 回调：code → token → userinfo → 创建/登录用户 → 返回 JWT。"""
    from config import GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET

    if not code:
        raise HTTPException(status_code=400, detail="缺少授权码")
    # 1. code → access token
    access_token = github_exchange_code(code, GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET)
    if not access_token:
        raise HTTPException(status_code=401, detail="GitHub 授权失败")
    # 2. access token → user info
    user_info = github_get_user(access_token)
    if not user_info:
        raise HTTPException(status_code=401, detail="获取 GitHub 用户信息失败")
    # 3. 登录/创建用户
    ok, result = github_login(
        user_info["github_id"],
        user_info["username"],
        user_info["email"],
        user_info["display_name"],
        user_info["avatar_url"],
    )
    if not ok:
        raise HTTPException(status_code=500, detail=result)
    # 4. 重定向到前端，token 通过 URL 传递
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
    return RedirectResponse(f"{frontend_url}?github_token={result}")


# ========== 用户中心接口 ==========

@app.get("/user/profile", response_model=UserProfileResponse)
async def get_profile(user_id: int = Depends(get_current_user)):
    """获取当前用户信息"""
    info = auth_get_user_info(user_id)
    if info is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return UserProfileResponse(**info)


@app.put("/user/profile", response_model=dict)
async def update_profile(request: UpdateProfileRequest, user_id: int = Depends(get_current_user)):
    """修改显示名称"""
    if not request.display_name.strip():
        raise HTTPException(status_code=400, detail="显示名称不能为空")
    ok = auth_update_display_name(user_id, request.display_name.strip())
    if not ok:
        raise HTTPException(status_code=500, detail="修改失败")
    return {"success": True, "message": "名称已更新"}


@app.put("/user/password", response_model=dict)
async def update_password(request: UpdatePasswordRequest, user_id: int = Depends(get_current_user)):
    """修改密码"""
    if len(request.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码至少 6 位")
    ok, msg = auth_update_password(user_id, request.old_password, request.new_password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}


# ========== 用户级 LLM 密钥（前端切换器用） ==========

@app.get("/user/llm-keys")
async def list_user_llm_keys(user_id: int = Depends(get_current_user)):
    """获取当前用户已配置的模型密钥（脱敏，不返回真实 key）"""
    keys = memory.get_user_llm_keys(user_id)
    configured = [k["provider"] for k in keys]
    return {"keys": keys, "configured_providers": configured}


@app.put("/user/llm-keys")
async def save_user_llm_key(request: LLMKeyRequest, user_id: int = Depends(get_current_user)):
    """保存（更新）某模型的用户级密钥"""
    ok = memory.set_user_llm_key(
        user_id, request.provider, request.api_key, request.base_url or "", request.model or ""
    )
    if not ok:
        raise HTTPException(status_code=400, detail="provider 非法或未提供 api_key")
    return {"success": True, "provider": request.provider}


@app.delete("/user/llm-keys/{provider}")
async def delete_user_llm_key_endpoint(provider: str, user_id: int = Depends(get_current_user)):
    """删除某模型的用户级密钥"""
    ok = memory.delete_user_llm_key(user_id, provider)
    if not ok:
        raise HTTPException(status_code=404, detail="未找到该模型配置")
    return {"success": True, "provider": provider}


@app.get("/models")
async def list_models(user_id: int = Depends(get_current_user)):
    """返回所有模型及其配置状态：全局 available（.env 是否配 key）+ 用户已配，
    合并为 effective（true=真正用该模型，false=将静默回退 DeepSeek 兜底）。"""
    try:
        user_keys = memory.get_user_llm_keys(user_id)
        user_configured = {k["provider"] for k in user_keys}
    except Exception:
        user_configured = set()
    models = get_available_models()  # [{id,label,role,available}]
    result = []
    for m in models:
        uc = m["id"] in user_configured
        g_available = bool(m.get("available", False))
        result.append({
            "id": m["id"],
            "available": g_available,         # 全局 .env 是否配了 key
            "user_configured": uc,            # 该用户是否在前端填了自己的 key
            "effective": g_available or uc,   # 真正可用（不兜底）
        })
    return {"models": result}


# ========== MBTI 性格测试接口 ==========

@app.get("/mbti/questions")
async def mbti_questions(user_id: int = Depends(get_current_user)):
    """返回 MBTI 测试题库（32 道选择题，不含答案逻辑）"""
    from mbti import get_questions
    questions = get_questions()
    return {"questions": questions, "total": len(questions)}


@app.post("/mbti/analyze")
async def mbti_analyze(request: MBTIAnalyzeRequest, user_id: int = Depends(get_current_user)):
    """提交答案 → 计算 MBTI 类型 + LLM 分析理想岗位适配差异"""
    from mbti import analyze_fit_async, compute_mbti, get_questions

    ideal_role = request.ideal_role.strip()
    if not ideal_role:
        raise HTTPException(status_code=400, detail="请先输入理想岗位")
    total = len(get_questions())
    if not request.answers or len(request.answers) != total:
        raise HTTPException(status_code=400, detail=f"请完成全部 {total} 道题")

    mbti, scores = compute_mbti(request.answers)
    analysis = await analyze_fit_async(mbti, ideal_role)
    # 存档本次结果（供历史对比）
    try:
        memory.save_mbti_result(user_id, mbti, ideal_role, scores)
    except Exception as e:
        logger.warning("MBTI 结果存档失败: %s", e)
    return {
        "mbti": mbti,
        "scores": scores,
        "analysis": analysis,
    }


@app.get("/mbti/history")
async def mbti_history(user_id: int = Depends(get_current_user)):
    """返回用户的 MBTI 测试历史（最新在前），用于观察类型稳定性。"""
    history = memory.get_mbti_history(user_id)
    return {
        "history": history,
        "total": len(history),
    }


@app.post("/mbti/export")
async def mbti_export(request: MBTIExportRequest, user_id: int = Depends(get_current_user)):
    """把当前 MBTI 结果（含历史对比）写成「我的 MBTI 档案.md」存入 Obsidian。"""
    from datetime import datetime

    from tools.obsidian import save_note_to_vault

    history = memory.get_mbti_history(user_id)
    lines = [
        "# 我的 MBTI 档案",
        "",
        f"> 最近更新：{datetime.now().strftime('%Y-%m-%d %H:%M')} ｜ 共测试 {len(history)} 次",
        "",
        "## 最新结果",
        "",
        f"- **类型**：{request.mbti}",
    ]
    if request.ideal_role:
        lines.append(f"- **理想岗位**：{request.ideal_role}")
    if request.scores:
        detail = " ".join(f"{k}{v}" for k, v in request.scores.items())
        lines.append(f"- **各维度得分**：{detail}")
    if request.analysis:
        lines.append("")
        lines.append("### 岗位适配分析")
        lines.append("")
        lines.append(request.analysis)

    if history:
        lines.append("")
        lines.append("## 历史记录")
        lines.append("")
        lines.append("| 时间 | 类型 | 理想岗位 |")
        lines.append("|------|------|---------|")
        for h in history:
            lines.append(f"| {h['created_at'][:16]} | {h['mbti']} | {h['ideal_role'] or '-'} |")

    content = "\n".join(lines)
    result = save_note_to_vault("我的 MBTI 档案.md", content)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return {"ok": True, "path": result["path"]}


# ========== 模拟面试记录归档接口 ==========

@app.post("/interview/save")
async def interview_save(request: InterviewSaveRequest, user_id: int = Depends(get_current_user)):
    """把一次模拟面试的对话整理成记录，写入 Obsidian（模拟面试/面试记录/日期.md）。"""
    from interview import save_interview_record_async

    # 校验 session 归属：只能归档自己的会话
    if auth_get_session_history(user_id, request.session_id) is None:
        raise HTTPException(status_code=403, detail="无权访问该会话")

    result = await save_interview_record_async(request.session_id, memory)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "保存失败"))
    return result


@app.post("/interview/weakness")
async def interview_weakness(user_id: int = Depends(get_current_user)):
    """分析所有面试记录，生成「薄弱点画像」写入 Obsidian（模拟面试/薄弱点画像.md）。"""
    from interview import build_weakness_profile_async

    result = await build_weakness_profile_async()
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "生成失败"))
    return result


@app.post("/interview/finish")
async def interview_finish(request: InterviewSaveRequest, user_id: int = Depends(get_current_user)):
    """结束一次模拟面试：保存记录（含薄弱点分析）到 Obsidian。

    幂等设计：重复调用只追加新记录块；同一 session 可安全多次触发。
    """
    from interview import save_interview_record_with_weakness_async

    # 校验 session 归属：只能归档自己的会话
    if auth_get_session_history(user_id, request.session_id) is None:
        raise HTTPException(status_code=403, detail="无权访问该会话")

    result = await save_interview_record_with_weakness_async(request.session_id, memory)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "保存失败"))
    return result


# ========== 笔记快捷保存接口 ==========

@app.post("/notes/save")
async def notes_save(request: NoteSaveRequest, user_id: int = Depends(get_current_user)):
    """把一段内容（如助手回复）快捷保存为 Obsidian 笔记（工作台笔记/目录）。"""
    import re
    from datetime import datetime

    from tools.obsidian import save_note_to_vault

    content = request.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="内容为空，无法保存")

    title = request.title.strip()
    if not title:
        # 自动生成标题：取内容前 20 字，去掉换行和非法文件名字符
        title = re.sub(r'[\\/:*?"<>|\n\r]+', " ", content[:20]).strip() or "未命名"
    else:
        title = re.sub(r'[\\/:*?"<>|\n\r]+', " ", title).strip()

    result = save_note_to_vault(f"工作台笔记/{title}", content)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return {
        "ok": True,
        "title": title,
        "path": result["path"],
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


@app.post("/notes/save-session")
async def notes_save_session(request: SessionSaveRequest, user_id: int = Depends(get_current_user)):
    """把整个会话保存为 Obsidian 笔记（工作台笔记/会话存档）。

    内容为完整问答回顾 Markdown，标题取自会话 label，文件放入
    `工作台笔记/会话存档/` 目录。
    """
    import re
    from datetime import datetime

    from tools.obsidian import save_note_to_vault

    # 1. 校验归属 + 取会话信息
    sessions = memory.get_user_sessions(user_id)
    target = next((s for s in sessions if s["session_id"] == request.session_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="会话不存在或不属于当前用户")

    # 2. 取完整消息（正序）
    messages = memory.get_session_messages(request.session_id, limit=200)
    if not messages:
        raise HTTPException(status_code=400, detail="会话无内容，无法保存")

    # 3. 组装 Markdown：标题 + 元信息 + 问答列表
    label = (target.get("label") or "").strip() or "未命名会话"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    parts = [f"# {label}\n", f"> 会话存档 · {now} · 共 {len(messages)} 条\n"]
    for m in messages:
        role_label = "🤖 AI" if m.get("role") == "assistant" else "🙋 我"
        content = (m.get("content") or "").strip()
        if not content:
            continue
        parts.append(f"\n### {role_label}\n\n{content}\n")
    content_md = "\n".join(parts)

    # 4. 文件名：标题 + 时间，去除非法字符
    safe_label = re.sub(r'[\\/:*?"<>|\n\r]+', " ", label).strip() or "未命名"
    filename = f"会话存档/{safe_label} {datetime.now().strftime('%Y%m%d-%H%M')}"

    result = save_note_to_vault(f"工作台笔记/{filename}", content_md)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return {
        "ok": True,
        "session_id": request.session_id,
        "title": label,
        "path": result["path"],
        "saved_at": now,
        "msg_count": len(messages),
    }


# ========== 数据看板接口 ==========

@app.get("/dashboard/stats")
async def dashboard_stats(user_id: int = Depends(get_current_user)):
    """返回使用数据看板统计。"""
    from dashboard import get_stats
    return get_stats(memory, user_id)


# ========== 会话管理接口 ==========

@app.get("/user/sessions")
async def list_sessions(user_id: int = Depends(get_current_user)):
    """获取用户的所有会话"""
    sessions = auth_get_sessions(user_id)
    return {"sessions": sessions}


@app.post("/user/sessions")
async def create_session(user_id: int = Depends(get_current_user)):
    """创建新会话"""
    session_id = auth_create_session(user_id)
    return {"session_id": session_id, "label": "新对话", "msg_count": 0}


@app.delete("/user/sessions/{session_id}")
async def delete_session(session_id: str, user_id: int = Depends(get_current_user)):
    """删除会话（验证归属，防越权删除他人会话）"""
    ok = auth_delete_session(user_id, session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在或不属于当前用户")
    return {"success": True, "session_id": session_id}


@app.patch("/user/sessions/{session_id}")
async def update_session(session_id: str, request: SessionUpdateRequest,
                         user_id: int = Depends(get_current_user)):
    """修改会话标题（验证归属）"""
    label = (request.label or "").strip()
    if not label:
        raise HTTPException(status_code=400, detail="标题不能为空")
    ok = memory.update_session_label(user_id, session_id, label)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在或不属于当前用户")
    return {"ok": True, "session_id": session_id, "label": label}


@app.get("/user/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, limit: int = 200, user_id: int = Depends(get_current_user)):
    """获取指定会话的历史消息（已验证归属，防越权）"""
    history = auth_get_session_history(user_id, session_id, limit=limit)
    if history is None:
        raise HTTPException(status_code=404, detail="会话不存在或不属于当前用户")
    return {"session_id": session_id, "messages": history}


@app.get("/")
async def root():
    """服务状态 + Obsidian vault 概况"""
    from config import OBSIDIAN_VAULT_DIR
    from knowledge.pipeline import get_vault_metadata
    meta = get_vault_metadata()
    base = {
        "message": "成长智伴 服务运行中",
        "docs": "/docs",
        "status": "active",
    }
    if meta.get("configured"):
        base["obsidian"] = {
            "vault": OBSIDIAN_VAULT_DIR,
            "notes": meta.get("note_count", 0),
            "folders": meta.get("folders", []),
        }
    else:
        base["obsidian"] = {"configured": False, "hint": "在 .env 中设置 OBSIDIAN_VAULT_DIR 即可接入笔记库"}
    return base


@app.get("/health")
async def health_check():
    """标准健康检查（K8s/Docker 探活）。检查数据库和 Chroma 是否可用。"""
    checks = {"database": False, "chroma": False}
    try:
        conn = memory._connect()
        conn.execute("SELECT 1")
        conn.close()
        checks["database"] = True
    except Exception as e:
        checks["database"] = str(e)
    try:
        from knowledge.vector_store import get_vector_store
        store = get_vector_store("obsidian")
        store.count()
        checks["chroma"] = True
    except Exception as e:
        checks["chroma"] = str(e)

    all_ok = checks["database"] is True and checks["chroma"] is True
    return {
        "status": "healthy" if all_ok else "degraded",
        "checks": checks,
        "version": "1.0.0",
    }


# ═══════════════════════════════════════════
#  聊天接口（Agent）
# ═══════════════════════════════════════════

_DEFAULT_LABELS = {"", "default", "新对话"}


def _is_default_label(label: str) -> bool:
    """会话标题是否仍是默认值（未起标题，需要智能总结）"""
    return (label or "").strip() in _DEFAULT_LABELS


async def _auto_title_session(session_id: str, user_id: int, first_message: str):
    """首轮对话后异步为会话生成智能标题（fire-and-forget）。

    用 LLM 把首条用户消息总结为 4-8 字标题；失败/异常时降级取消息前 12 字。
    不阻塞 /chat 响应。
    """
    title = (first_message or "").strip()[:12] or "新对话"
    try:
        from chatbot.chatbot import chat as llm_chat
        resp = llm_chat(
            [{
                "role": "user",
                "content": (
                    f"为这段对话取一个 4-8 个字的简短标题，只输出标题本身，"
                    f"不要引号、不要解释、不要标点结尾：\n{first_message[:100]}"
                ),
            }],
            tools=None,
            tool_choice="none",
        )
        candidate = (resp.choices[0].message.content or "").strip().strip('"\'“”')
        candidate = re.sub(r"[\\/:*?\"<>|\n\r]+", " ", candidate).strip()
        if candidate and len(candidate) <= 30:
            title = candidate
    except Exception as e:
        logger.warning("智能标题生成失败，降级用消息前 12 字: %s", e)
    try:
        memory.update_session_label(user_id, session_id, title)
    except Exception as e:
        logger.warning("会话标题更新失败: %s", e)


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, user_id: int = Depends(get_current_user)):
    try:
        agent = get_agent(request.session_id)
        # 全链路异步执行（Agent.arun）：不阻塞事件循环，并发能力显著提升
        reply = await agent.arun(request.message, model_provider=request.model_provider,
                                 user_id=user_id, mode=request.mode)
        # 首轮对话后异步生成智能标题（fire-and-forget，不阻塞响应）
        if _is_default_label(memory.get_session_label(user_id, request.session_id)):
            asyncio.create_task(_auto_title_session(request.session_id, user_id, request.message))
        return ChatResponse(
            reply=reply,
            session_id=request.session_id,
            model_provider=request.model_provider,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent 处理失败: {str(e)}") from e


@app.post("/chat/stream")
async def chat_stream_endpoint(request: ChatRequest, user_id: int = Depends(get_current_user)):
    """流式聊天接口（SSE），打字机效果（异步全链路）"""
    agent = get_agent(request.session_id)

    async def event_generator():
        try:
            async for event in agent.arun_stream(request.message, model_provider=request.model_provider,
                                                 user_id=user_id, mode=request.mode):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ═══════════════════════════════════════════
#  知识库管理接口
# ═══════════════════════════════════════════

UPLOAD_DIR = Path("knowledge/docs")
ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf"}


@app.post("/knowledge/upload")
async def upload_document(file: UploadFile = File(...)):
    """上传文档到知识库（PDF/TXT/MD）"""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {suffix}，仅支持 {', '.join(ALLOWED_EXTENSIONS)}",
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_path = UPLOAD_DIR / file.filename

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}") from e

    return {
        "status": "success",
        "filename": file.filename,
        "path": str(file_path),
        "message": f"文件 {file.filename} 已上传，请调用 /knowledge/index 进行索引",
    }


@app.post("/knowledge/index")
async def index_knowledge():
    """索引 knowledge/docs/ 下的所有文档到向量库"""
    try:
        count = index_documents()
        return {
            "status": "success",
            "indexed_chunks": count,
            "message": f"索引完成，{count} 个切片已入库",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"索引失败: {str(e)}") from e


@app.post("/knowledge/query", response_model=KnowledgeQueryResponse)
async def query_knowledge(request: KnowledgeQueryRequest):
    """基于知识库生成回答"""
    try:
        answer = rag_query(request.question)
        return KnowledgeQueryResponse(answer=answer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}") from e


# ========== Obsidian 知识库接口（独立 collection，排除隐私文件）==========

@app.post("/obsidian/index")
async def index_obsidian_endpoint(force: bool = False):
    """增量索引 Obsidian vault 到独立向量集合（自动排除 OBSIDIAN_EXCLUDE 清单中的隐私文件）。

    - force=false：仅处理新增/变更/删除的文件（按 mtime 判断），效率高。
    - force=true：清空后全量重建（vault 大改后使用）。
    """
    try:
        result = index_obsidian(force=force)
        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result.get("message"))
        return {
            "status": "success",
            "result": result,
            "message": "Obsidian 索引完成：{} 文件 / {} 切片".format(
                result.get("indexed_files", 0), result.get("chunks", 0)
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"索引失败: {str(e)}") from e


@app.get("/obsidian/status")
async def obsidian_status():
    """查看 Obsidian 索引状态：vault 路径、排除清单、已索引切片数。"""
    from config import OBSIDIAN_COLLECTION, OBSIDIAN_EXCLUDE, OBSIDIAN_VAULT_DIR
    from knowledge.vector_store import get_vector_store

    try:
        store = get_vector_store(OBSIDIAN_COLLECTION)
        count = store.count()
    except Exception:
        count = -1
    return {
        "vault_dir": OBSIDIAN_VAULT_DIR,
        "collection": OBSIDIAN_COLLECTION,
        "excluded": OBSIDIAN_EXCLUDE,
        "indexed_chunks": count,
        "configured": bool(OBSIDIAN_VAULT_DIR),
    }


# ═══════════════════════════════════════════
#  生产模式：托管前端静态文件（仅当 frontend/dist/ 存在时）
# ═══════════════════════════════════════════

_FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """SPA fallback：非 API 路径返回前端 index.html"""
        file_path = _FRONTEND_DIST / full_path
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_FRONTEND_DIST / "index.html")
    logger.info("前端静态文件已挂载: %s", _FRONTEND_DIST)


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
