"""成长智伴 - 工作台性能压测 locustfile

场景（通过 --tags 选择）：
- single      单工具基线 + 多工具并行（5:1 权重混合）
- stress      高并发阶梯：1/5/10/30/50 用户压 /chat
- soak        30 分钟长稳：中等并发持续压
- longsession 长会话多轮：同一 session 连续 20 轮
- hub         入口页辅助接口（会话/模型/看板）

运行示例：
    locust -f locustfile.py --headless -u 1 --spawn-rate 1 --run-time 60s --tags single
    locust -f locustfile.py --headless -u 50 --spawn-rate 5 --run-time 120s --tags stress

环境变量：
    BASE_URL     后端地址（默认 http://127.0.0.1:8000）
    TOKEN        JWT token（默认 None，则 on_start 时登录）
    USERNAME/PASSWORD 登录凭据（TOKEN 为空时使用）
    SESSION_ID   可选，指定 session（默认随机生成）
"""

import json
import os
import random
import time
import uuid
from pathlib import Path

from locust import HttpUser, between, events, tag, task

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")
TOKEN = os.getenv("TOKEN", "")
USERNAME = os.getenv("USERNAME", "perf_test_user")
PASSWORD = os.getenv("PASSWORD", "perf_test_pass123")

# 读取问题集
_Q_FILE = Path(__file__).parent / "test-questions.json"
with open(_Q_FILE, encoding="utf-8") as f:
    _Q = json.load(f)

# 各工具问题池
TOOL_QUESTIONS = _Q["tools"]
PARALLEL_QUESTIONS = _Q["parallel_multi_tool"]
LONG_SESSION_TURNS = _Q["long_session_turns"]

# 工具名 → 展示名
TOOL_LABELS = {k: v["label"] for k, v in TOOL_QUESTIONS.items()}


def _auth_headers(token: str) -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }


def _login(client, username: str, password: str) -> str:
    """登录并返回 token；失败抛异常（压测前先确保能登录）。"""
    resp = client.post("/auth/login", json={"username": username, "password": password})
    data = resp.json()
    if resp.status_code != 200 or not data.get("token"):
        raise RuntimeError(f"登录失败: HTTP {resp.status_code} {data}")
    return data["token"]


# ═══════════════════════════════════════════
#  单工具基线 / 高并发 / soak
# ═══════════════════════════════════════════

class WorkstationUser(HttpUser):
    """工作台用户：轮询 6 类工具问题，模拟真实日常使用。

    - tags=single：单工具基线 + 多工具并行（5:1 权重混合）
    - tags=stress：高并发阶梯（混合流量）
    - tags=soak：30 分钟长稳
    """

    wait_time = between(1, 3)
    host = BASE_URL
    tags = {"single", "stress", "soak"}

    def on_start(self):
        token = TOKEN
        if not token:
            token = _login(self.client, USERNAME, PASSWORD)
        self.token = token
        self.session_id = os.getenv("SESSION_ID") or f"perf_{uuid.uuid4().hex[:8]}"
        self.headers = _auth_headers(token)

    def _chat(self, message: str):
        """发 /chat 请求（name 用于 locust 分组统计）"""
        with self.client.post(
            "/chat",
            json={
                "message": message,
                "session_id": self.session_id,
                "model_provider": "deepseek",
                "mode": "workspace",
            },
            headers=self.headers,
            name="/chat",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")
            elif "reply" not in resp.json():
                resp.failure("响应缺少 reply 字段")

    @task(5)
    @tag("single", "stress", "soak")
    def single_tool_baseline(self):
        """单工具基线：随机挑一个工具的问题"""
        tool_name = random.choice(list(TOOL_QUESTIONS.keys()))
        question = random.choice(TOOL_QUESTIONS[tool_name]["questions"])
        self._chat(question)

    @task(1)
    @tag("single", "stress", "soak")
    def parallel_trigger(self):
        """触发多工具并行（mock LLM 一次返回多个 tool_calls）"""
        question = random.choice(PARALLEL_QUESTIONS)
        with self.client.post(
            "/chat",
            json={
                "message": question,
                "session_id": self.session_id,
                "model_provider": "deepseek",
                "mode": "workspace",
            },
            headers=self.headers,
            name="/chat-multi-tool",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")
            elif "reply" not in resp.json():
                resp.failure("响应缺少 reply 字段")


# ═══════════════════════════════════════════
#  长会话多轮场景
# ═══════════════════════════════════════════

class LongSessionUser(HttpUser):
    """长会话用户：一次完整跑 20 轮连续对话，观察上下文增长下的延迟/内存。

    注意：此场景每用户一个 session，任务间保持会话状态。
    """

    wait_time = between(2, 4)
    host = BASE_URL
    tags = {"longsession"}

    def on_start(self):
        token = TOKEN
        if not token:
            token = _login(self.client, USERNAME, PASSWORD)
        self.token = token
        self.session_id = os.getenv("SESSION_ID") or f"perf_long_{uuid.uuid4().hex[:8]}"
        self.headers = _auth_headers(token)
        self._turn_index = 0

    @task
    @tag("longsession")
    def long_session_turn(self):
        if self._turn_index >= len(LONG_SESSION_TURNS):
            # 一轮会话跑完，重置开新会话（继续观察）
            self._turn_index = 0
            self.session_id = f"perf_long_{uuid.uuid4().hex[:8]}"
        message = LONG_SESSION_TURNS[self._turn_index]
        self._turn_index += 1
        with self.client.post(
            "/chat",
            json={
                "message": message,
                "session_id": self.session_id,
                "model_provider": "deepseek",
                "mode": "workspace",
            },
            headers=self.headers,
            name="/chat",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")


# ═══════════════════════════════════════════
#  前端首屏探测（可选）：登录 + 会话列表 + 看板，模拟 hub 进入 chat 的 API 流量
# ═══════════════════════════════════════════

class HubEntryUser(HttpUser):
    """入口页用户：模拟 hub 页登录后的 API 调用序列（非 /chat 的辅助接口）"""

    wait_time = between(3, 6)
    host = BASE_URL
    tags = {"hub"}

    def on_start(self):
        token = TOKEN
        if not token:
            token = _login(self.client, USERNAME, PASSWORD)
        self.token = token
        self.headers = _auth_headers(token)

    @task(2)
    @tag("hub")
    def fetch_sessions(self):
        self.client.get("/user/sessions", headers=self.headers, name="/user/sessions")

    @task(2)
    @tag("hub")
    def fetch_models(self):
        self.client.get("/models", headers=self.headers, name="/models")

    @task(1)
    @tag("hub")
    def fetch_dashboard(self):
        self.client.get("/dashboard/stats", headers=self.headers, name="/dashboard/stats")

    @task(1)
    @tag("hub")
    def fetch_llm_keys(self):
        self.client.get("/user/llm-keys", headers=self.headers, name="/user/llm-keys")

    @task(1)
    @tag("hub")
    def health(self):
        self.client.get("/health", name="/health")
