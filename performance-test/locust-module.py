"""三模块（模拟面试/MBTI/数据看板）并发压测 locustfile

场景（--tags 选择）：
- mbti        MBTI 接口并发：questions/analyze/history/export
- interview   模拟面试并发：chat(面试模式) + save + finish
- dashboard   数据看板并发：stats

运行示例：
    locust -f locust-module.py --headless -u 10 --spawn-rate 2 --run-time 60s --tags mbti
    locust -f locust-module.py --headless -u 30 --spawn-rate 3 --run-time 60s --tags interview

环境变量：
    BASE_URL   后端地址（默认 http://127.0.0.1:8000）
    TOKEN      JWT token（默认 None，则 on_start 时登录）
    USERNAME/PASSWORD 登录凭据
"""

import json
import os
import time
import uuid

from locust import HttpUser, between, events, tag, task

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")
TOKEN = os.getenv("TOKEN", "")
USERNAME = os.getenv("USERNAME", "perf_user_final")
PASSWORD = os.getenv("PASSWORD", "perf_test_pass123")
# 场景选择：MODULE=mbti|interview|dashboard，只激活目标类（避免无关类被实例化报错）
MODULE = os.getenv("MODULE", "")


def _active(mod: str) -> bool:
    return not MODULE or MODULE == mod

MBTI_ANSWERS = [1] * 32  # 32 题全选 A（合法值）


def _auth_headers(token: str) -> dict:
    return {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}


def _login(client, username: str, password: str) -> str:
    resp = client.post("/auth/login", json={"username": username, "password": password})
    data = resp.json()
    if resp.status_code != 200 or not data.get("token"):
        raise RuntimeError(f"登录失败: HTTP {resp.status_code} {data}")
    return data["token"]


class MBTIUser(HttpUser):
    abstract = not _active("mbti")
    """MBTI 模块并发用户：混合访问 4 个接口（analyze 权重高，模拟真实作答流程）"""

    wait_time = between(0.5, 2)
    host = BASE_URL
    tags = {"mbti"}

    def on_start(self):
        self.token = TOKEN or _login(self.client, USERNAME, PASSWORD)
        self.headers = _auth_headers(self.token)

    @tag("mbti")
    @task(3)
    def analyze(self):
        self.client.post("/mbti/analyze", json={"ideal_role": "后端工程师", "answers": MBTI_ANSWERS},
                         headers=self.headers, name="POST /mbti/analyze")

    @tag("mbti")
    @task(1)
    def questions(self):
        self.client.get("/mbti/questions", headers=self.headers, name="GET /mbti/questions")

    @tag("mbti")
    @task(1)
    def history(self):
        self.client.get("/mbti/history", headers=self.headers, name="GET /mbti/history")

    @tag("mbti")
    @task(1)
    def export(self):
        self.client.post("/mbti/export", json={"mbti": "ESTJ", "ideal_role": "后端工程师"},
                         headers=self.headers, name="POST /mbti/export")


class InterviewUser(HttpUser):
    abstract = not _active("interview")
    """模拟面试并发用户：面试对话（重量）+ 保存记录 + 结束归档"""

    wait_time = between(0.5, 2)
    host = BASE_URL
    tags = {"interview"}

    def on_start(self):
        self.token = TOKEN or _login(self.client, USERNAME, PASSWORD)
        self.headers = _auth_headers(self.token)
        # 每用户创建专属会话（真实场景；自定义 session 需先注册进 user_sessions，否则 save/finish 403）
        resp = self.client.post("/user/sessions", headers=self.headers)
        data = resp.json() if resp.status_code == 200 else {}
        self.sid = data.get("session_id", "u4_default")

    @tag("interview")
    @task(3)
    def interview_chat(self):
        msg = "请出一道 Python 面试题" if time.time() % 2 < 1 else "我会用列表推导式回答"
        self.client.post("/chat", json={"message": msg, "session_id": self.sid,
                                        "model_provider": "deepseek", "mode": "interview"},
                         headers=self.headers, name="POST /chat (面试模式)")

    @tag("interview")
    @task(1)
    def finish(self):
        self.client.post("/interview/finish", json={"session_id": self.sid},
                         headers=self.headers, name="POST /interview/finish")

    @tag("interview")
    @task(1)
    def save(self):
        self.client.post("/interview/save", json={"session_id": self.sid},
                         headers=self.headers, name="POST /interview/save")


class DashboardUser(HttpUser):
    abstract = not _active("dashboard")
    """数据看板并发用户：stats 只读接口（纯数据库聚合）"""

    wait_time = between(0.2, 1)
    host = BASE_URL
    tags = {"dashboard"}

    def on_start(self):
        self.token = TOKEN or _login(self.client, USERNAME, PASSWORD)
        self.headers = _auth_headers(self.token)

    @tag("dashboard")
    @task(1)
    def stats(self):
        self.client.get("/dashboard/stats", headers=self.headers, name="GET /dashboard/stats")
