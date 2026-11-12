# -*- coding: utf-8 -*-
"""HTTP 层「写盘接口」冒烟测试：补测会写 Obsidian vault 的接口

覆盖（现有 eval_http_smoke.py 跳过的 4 个写盘接口）：
  /mbti/export         写「我的 MBTI 档案.md」
  /interview/save      写「模拟面试/面试记录/日期.md」
  /interview/finish    写面试记录 + 薄弱点章节
  /interview/weakness  写「模拟面试/薄弱点画像.md」

前置数据链：注册 → 建会话 → /chat 造 ≥2 条消息 → /mbti/analyze 造历史。

副作用（测试后自动清理）：
  - vault 新增 3 个 md 文件（cleanup 删除；均不与用户已有数据冲突，见下方说明）
  - 消耗少量真实 LLM token（.env 的 deepseek / glm）
  - 测试用户留在库中（无删除用户接口，与现有冒烟一致）
  - 写入文件若被轮询索引扫入向量库，删文件后由下一次增量索引自愈

前提：服务已启动，推荐提高限流：
    RATE_LIMIT_MAX=5000 .venv/Scripts/python -m uvicorn api:app --port 8000
用法：
    .venv/Scripts/python eval/eval_http_smoke_writing.py [--base-url http://127.0.0.1:8000]
输出：
    eval/reports/http-smoke-writing-report.md
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

# 三个写盘产物的相对路径（vault 内），cleanup 按此删除
EXPORT_FILE = "我的 MBTI 档案.md"
INTERVIEW_DIR = "模拟面试/面试记录"
WEAKNESS_FILE = "模拟面试/薄弱点画像.md"


class WritingSmoke:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self.client = httpx.Client(timeout=180.0)
        self.token = ""
        self.results: list[dict] = []
        self.ctx: dict = {}

    # ── 记录 ──
    def _record(self, name, method, path, status, ms, ok, note=""):
        self.results.append({
            "name": name, "method": method, "path": path,
            "status": status, "ms": round(ms, 1), "ok": ok, "note": note,
        })
        flag = "PASS" if ok else "FAIL"
        print(f"  [{flag}] {name:<26} {method:<6} {path:<40} {status} {ms:6.0f}ms {note}")

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
        username = f"smokew_{suffix}"
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

        # 3. 建会话 + /chat 造 ≥2 条消息（interview/save 的前置）
        r = self.req("创建会话", "POST", "/user/sessions")
        sid = r.json().get("session_id") if (r is not None and r.status_code == 200) else ""
        self.ctx["session_id"] = sid
        if sid:
            self.req("对话造前置消息", "POST", "/chat",
                     json={"message": "请只回答一个数字：1+1 等于几？", "session_id": sid})

        # 4. MBTI 分析（造历史，供 export 含历史对比）+ export
        r = self.req("MBTI 题目", "GET", "/mbti/questions")
        n_q = len(r.json().get("questions", [])) if (r is not None and r.status_code == 200) else 0
        analyze = None
        if n_q:
            analyze = self.req("MBTI 分析", "POST", "/mbti/analyze",
                               json={"ideal_role": "Python 后端工程师", "answers": [0] * n_q})
        mbti = scores = analysis = None
        if analyze is not None and analyze.status_code == 200:
            mbti = analyze.json().get("mbti")
            scores = analyze.json().get("scores")
            analysis = analyze.json().get("analysis")
        self.req("MBTI 导出档案", "POST", "/mbti/export",
                 json={"mbti": mbti or "INTJ", "ideal_role": "Python 后端工程师",
                       "scores": scores or {}, "analysis": analysis or "（冒烟测试分析）"})

        # 5. 面试归档三接口（依赖第 3 步造的 session）
        self.req("面试记录保存", "POST", "/interview/save", json={"session_id": sid})
        self.req("面试结束归档", "POST", "/interview/finish", json={"session_id": sid})
        # weakness 依赖上两步已写出的面试记录文件
        self.req("薄弱点画像", "POST", "/interview/weakness")

        # 6. 负例：归档不存在的会话 → 应 403（归属校验）
        self.req("归档越权会话", "POST", "/interview/save", expect=403,
                 json={"session_id": "nonexistent-session"})

        # 7. 删除测试会话（清理，需在登出前）
        if sid:
            self.req("删除会话", "DELETE", f"/user/sessions/{sid}")

    # ── 清理 vault 写盘产物 ──
    def cleanup(self):
        print("\n清理测试产物…")
        try:
            from config import OBSIDIAN_VAULT_DIR
            if OBSIDIAN_VAULT_DIR:
                vault = Path(OBSIDIAN_VAULT_DIR)
                targets = [EXPORT_FILE, WEAKNESS_FILE]
                # 面试记录按日期文件删除（仅删今天生成的测试记录文件）
                today = time.strftime("%Y-%m-%d")
                targets.append(f"{INTERVIEW_DIR}/{today}.md")
                for rel in targets:
                    p = vault / rel
                    if p.exists():
                        p.unlink()
                        print(f"  已删: {rel}")
            else:
                print("  OBSIDIAN_VAULT_DIR 未配置，跳过文件清理")
        except Exception as e:
            print(f"  文件清理失败: {e}")

    # ── 报告 ──
    def report(self):
        n = len(self.results)
        passed = sum(1 for r in self.results if r["ok"])
        failed = [r for r in self.results if not r["ok"]]

        print(f"\n===== 汇总（{n} 项）=====")
        print(f"通过 {passed}/{n} = {passed / n:.1%}")
        if failed:
            print("失败项：")
            for r in failed:
                print(f"  - {r['name']} ({r['method']} {r['path']}) → {r['status']} {r['note']}")

        lines = [
            "# HTTP 层写盘接口冒烟报告",
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
            "## 副作用与清理",
            "",
            f"- 测试用户：`{self.ctx.get('username')}`（无删除用户接口，留在库中）",
            "- 写盘产物：`我的 MBTI 档案.md`、`模拟面试/面试记录/日期.md`、`模拟面试/薄弱点画像.md`（cleanup 已删除）",
            "- 测试会话已删除；LLM token 已消耗少量（deepseek/glm）",
            "- 若写盘文件被轮询索引扫入向量库，删文件后由下一次增量索引自动清理",
            "",
        ]
        out = ROOT / "eval" / "reports" / "http-smoke-writing-report.md"
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

    s = WritingSmoke(args.base_url)
    try:
        s.run()
    finally:
        s.cleanup()
        s.report()
        s.client.close()


if __name__ == "__main__":
    main()
