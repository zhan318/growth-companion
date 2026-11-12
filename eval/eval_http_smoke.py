# -*- coding: utf-8 -*-
"""HTTP 层冒烟测试：把 e2e 没覆盖的接口全部走一遍

覆盖范围（与 eval_e2e.py 互补）：
  认证链  注册 / 登录（错误密码）/ 登出 / 登出后 token 失效
  用户    资料读写 / LLM key 增删查
  MBTI    题目 / 分析 / 历史
  会话    CRUD（创建 / 列出 / 改名 / 消息 / 删除）
  笔记    /notes/save 写盘（测试后删除文件）
  看板    /dashboard/stats
  RAG     obsidian 状态 / 上传文档全链路（upload → index → query → 清理）
  对话    /chat 整段响应、/chat/stream SSE（记录首字延迟、事件数、error 事件）

前提：服务已启动。推荐用提高限流的参数启动：
    RATE_LIMIT_MAX=5000 .venv/Scripts/python -m uvicorn api:app --port 8000
用法：
    .venv/Scripts/python eval/eval_http_smoke.py [--base-url http://127.0.0.1:8000]
输出：
    eval/reports/http-smoke-report.md

说明：冒烟会创建 1 个测试用户（用户名 smoke_xxxxxxxx，无删除用户接口，会留在库里）。
"""

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


class Smoke:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self.client = httpx.Client(timeout=180.0)
        self.token = ""
        self.results: list[dict] = []
        self.ctx: dict = {}

    # ── 记录 ──
    def _record(self, name: str, method: str, path: str, status, ms: float, ok: bool, note: str = ""):
        self.results.append({
            "name": name, "method": method, "path": path,
            "status": status, "ms": round(ms, 1), "ok": ok, "note": note,
        })
        flag = "PASS" if ok else "FAIL"
        print(f"  [{flag}] {name:<28} {method:<6} {path:<42} {status} {ms:6.0f}ms {note}")

    def req(self, name, method, path, expect=200, auth=True, **kwargs):
        headers = kwargs.pop("headers", {})
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        t0 = time.perf_counter()
        try:
            r = self.client.request(method, self.base + path, headers=headers, **kwargs)
            ms = (time.perf_counter() - t0) * 1000
            ok = r.status_code == expect
            note = "" if ok else r.text[:120].replace("\n", " ")
            self._record(name, method, path, r.status_code, ms, ok, note)
            return r
        except Exception as e:
            ms = (time.perf_counter() - t0) * 1000
            self._record(name, method, path, "EXC", ms, False, f"{type(e).__name__}: {e}"[:120])
            return None

    # ── 主流程 ──
    def run(self):
        print(f"目标服务: {self.base}\n")
        suffix = uuid.uuid4().hex[:8]
        username = f"smoke_{suffix}"
        password = "Smoke123456"
        self.ctx["username"] = username

        # 1. 健康检查
        self.req("健康检查", "GET", "/health", auth=False)

        # 2. 注册（拿到 token）
        r = self.req("注册", "POST", "/auth/register", auth=False,
                     json={"username": username, "email": f"{username}@test.local", "password": password})
        if r is not None and r.status_code == 200:
            self.token = r.json().get("token", "")
            self.ctx["user_id"] = r.json().get("user_id")
            self.ctx["session_id"] = r.json().get("session_id", "")

        # 3. 无 token 访问受保护接口
        self.req("未授权访问", "GET", "/user/profile", expect=401, auth=False)

        # 4. 错误密码登录
        self.req("登录-错误密码", "POST", "/auth/login", expect=401, auth=False,
                 json={"username": username, "password": "wrong-password"})

        # 5. 正确登录
        r = self.req("登录-正确密码", "POST", "/auth/login", auth=False,
                     json={"username": username, "password": password})
        if r is not None and r.status_code == 200:
            self.token = r.json().get("token", "") or self.token

        # 6-8. 用户资料
        self.req("读取资料", "GET", "/user/profile")
        self.req("更新资料", "PUT", "/user/profile", json={"display_name": "冒烟测试"})
        self.req("修改密码-旧密码错误", "PUT", "/user/password", expect=400,
                 json={"old_password": "bad", "new_password": "New123456"})

        # 9-11. LLM key 管理
        self.req("列出 LLM keys", "GET", "/user/llm-keys")
        self.req("保存 LLM key", "PUT", "/user/llm-keys",
                 json={"provider": "deepseek", "api_key": "sk-smoke-test-not-real"})
        self.req("删除 LLM key", "DELETE", "/user/llm-keys/deepseek")

        # 12. 模型列表
        self.req("模型列表", "GET", "/models")

        # 13-15. MBTI
        r = self.req("MBTI 题目", "GET", "/mbti/questions")
        n_q = len(r.json().get("questions", [])) if (r is not None and r.status_code == 200) else 0
        if n_q:
            self.req("MBTI 分析", "POST", "/mbti/analyze", expect=200, timeout=180,
                     json={"ideal_role": "Python 后端工程师", "answers": [0] * n_q})
        self.req("MBTI 历史", "GET", "/mbti/history")

        # 16-20. 会话 CRUD
        r = self.req("创建会话", "POST", "/user/sessions")
        sid = r.json().get("session_id") if (r is not None and r.status_code == 200) else ""
        self.ctx["new_session"] = sid
        self.req("会话列表", "GET", "/user/sessions")
        if sid:
            self.req("会话改名", "PATCH", f"/user/sessions/{sid}", json={"label": "冒烟测试会话"})
            self.req("会话消息", "GET", f"/user/sessions/{sid}/messages")

        # 21. 笔记保存（记录路径，收尾删除）
        note_title = f"smoke-{suffix}"
        r = self.req("笔记保存", "POST", "/notes/save",
                     json={"title": note_title, "content": "这是一条 HTTP 冒烟测试笔记。"})
        if r is not None and r.status_code == 200:
            self.ctx["note_path"] = r.json().get("path", "")

        # 22. 看板
        self.req("数据看板", "GET", "/dashboard/stats")

        # 23. Obsidian 状态
        self.req("Obsidian 状态", "GET", "/obsidian/status")

        # 24-26. 上传文档 RAG 全链路（刚才因维度不兼容坏掉的功能，重点回归）
        tmp_name = f"smoke-{suffix}.md"
        files = {"file": (tmp_name, "红蓝冒烟测试文档：本文档用于验证上传索引链路，关键词是「青绿色测试」。".encode("utf-8"), "text/markdown")}
        self.req("上传文档", "POST", "/knowledge/upload", files=files)
        self.req("上传文档索引", "POST", "/knowledge/index", timeout=180)
        self.req("上传文档查询", "POST", "/knowledge/query", timeout=180,
                 json={"question": "青绿色测试是什么"})

        # 27. 整段对话
        r = self.req("对话-整段", "POST", "/chat", timeout=180,
                     json={"message": "只回答一个数字：1+1 等于几？", "session_id": self.ctx.get("new_session") or "smoke_sess"})
        if r is not None and r.status_code == 200:
            self.ctx["chat_reply"] = (r.json().get("reply") or "")[:60]

        # 28. SSE 流式对话
        self.stream_chat()

        # 29. 删除会话（清理，需在登出前，登出后 token 会失效）
        if sid:
            self.req("删除会话", "DELETE", f"/user/sessions/{sid}")

        # 30. 登出 + token 失效验证
        self.req("登出", "POST", "/auth/logout")
        self.req("登出后访问", "GET", "/user/profile", expect=401)

    def stream_chat(self):
        """SSE 流式：记录首字延迟、事件数、是否出现 error 事件"""
        name, path = "对话-流式(SSE)", "/chat/stream"
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        payload = {"message": "用一句话介绍你自己", "session_id": self.ctx.get("new_session") or "smoke_sess"}
        t0 = time.perf_counter()
        first_ms = None
        events = 0
        error_evt = None
        chars = 0
        try:
            with self.client.stream("POST", self.base + path, json=payload, headers=headers, timeout=180) as r:
                if r.status_code != 200:
                    self._record(name, "POST", path, r.status_code, (time.perf_counter() - t0) * 1000, False, "非 200")
                    return
                for line in r.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    if first_ms is None:
                        first_ms = (time.perf_counter() - t0) * 1000
                    events += 1
                    try:
                        d = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    if d.get("type") == "error":
                        error_evt = d.get("content", "")
                    chars += len(str(d.get("content", "")))
            total_ms = (time.perf_counter() - t0) * 1000
            ok = events > 0 and not error_evt and chars > 0
            note = f"首字 {first_ms:.0f}ms / {events} 事件 / {chars} 字" if first_ms else "无事件"
            if error_evt:
                note = f"error 事件: {error_evt[:60]}"
            self.ctx["sse"] = {"first_ms": round(first_ms or 0), "events": events, "chars": chars}
            self._record(name, "POST", path, r.status_code, total_ms, ok, note)
        except Exception as e:
            self._record(name, "POST", path, "EXC", (time.perf_counter() - t0) * 1000, False, f"{type(e).__name__}: {e}"[:120])

    # ── 清理 ──
    def cleanup(self):
        print("\n清理测试产物…")
        try:
            from config import OBSIDIAN_VAULT_DIR
            note_path = self.ctx.get("note_path")
            if note_path and OBSIDIAN_VAULT_DIR:
                p = Path(OBSIDIAN_VAULT_DIR) / note_path
                if p.exists():
                    p.unlink()
                    print(f"  已删测试笔记: {note_path}")
        except Exception as e:
            print(f"  笔记清理失败: {e}")
        try:
            for f in Path("knowledge/docs").glob("smoke-*.md"):
                f.unlink()
                print(f"  已删上传测试文件: {f.name}")
        except Exception as e:
            print(f"  上传文件清理失败: {e}")

    # ── 报告 ──
    def report(self):
        n = len(self.results)
        passed = sum(1 for r in self.results if r["ok"])
        failed = [r for r in self.results if not r["ok"]]
        times = [r["ms"] for r in self.results if isinstance(r["ms"], (int, float))]

        print(f"\n===== 汇总（{n} 项）=====")
        print(f"通过 {passed}/{n} = {passed / n:.1%}")
        if failed:
            print("失败项：")
            for r in failed:
                print(f"  - {r['name']} ({r['method']} {r['path']}) → {r['status']} {r['note']}")
        if times:
            print(f"耗时: 中位数 {sorted(times)[len(times) // 2]:.0f}ms | 最大 {max(times):.0f}ms")
        if self.ctx.get("sse"):
            s = self.ctx["sse"]
            print(f"SSE: 首字 {s['first_ms']}ms / {s['events']} 事件 / {s['chars']} 字")

        lines = [
            "# HTTP 层冒烟测试报告",
            "",
            f"> 生成时间：{time.strftime('%Y-%m-%d %H:%M')}",
            f"> 目标服务：{self.base}",
            f"> 结果：**{passed}/{n} 通过（{passed / n:.1%}）**",
            "",
            "## 明细",
            "",
            "| # | 用例 | 方法 | 路径 | 状态码 | 耗时ms | 结果 | 备注 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for i, r in enumerate(self.results, 1):
            lines.append(
                f"| {i} | {r['name']} | {r['method']} | `{r['path']}` | {r['status']} "
                f"| {r['ms']} | {'PASS' if r['ok'] else 'FAIL'} | {r['note'][:60]} |"
            )
        if failed:
            lines += ["", "## 失败明细", ""]
            for r in failed:
                lines.append(f"- **{r['name']}** `{r['method']} {r['path']}` → {r['status']}：{r['note']}")
        lines += [
            "",
            "## 未覆盖（需单独测）",
            "",
            "- `/interview/save|finish|weakness`：会写 vault 归档文件，且需真实面试会话",
            "- `/mbti/export`：会写 vault",
            "- `/obsidian/index`：全量重建约 2 分钟",
            "- GitHub OAuth：需浏览器跳转",
            "- 前端 UI、Docker 部署、并发性能",
            "",
            "## 说明",
            "",
            f"- 冒烟创建了测试用户 `{self.ctx.get('username')}`（无删除用户接口，会留在库中）",
            "- 测试笔记与上传文件已自动清理",
            f"- SSE 首字延迟：{self.ctx.get('sse', {}).get('first_ms', 'n/a')}ms",
            "",
        ]
        out = ROOT / "eval" / "reports" / "http-smoke-report.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines), encoding="utf-8")
        print(f"\n报告已写入: {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = ap.parse_args()

    try:
        httpx.get(args.base_url + "/health", timeout=3)
    except Exception:
        print(f"服务未启动：{args.base_url}\n先运行：RATE_LIMIT_MAX=5000 .venv/Scripts/python -m uvicorn api:app --port 8000")
        sys.exit(1)

    s = Smoke(args.base_url)
    try:
        s.run()
    finally:
        s.cleanup()
        s.report()
        s.client.close()


if __name__ == "__main__":
    main()
