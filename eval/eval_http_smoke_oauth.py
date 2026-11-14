"""GitHub OAuth 冒烟测试（自动化能覆盖的部分）

背景：OAuth 完整 happy path 的授权码 code 只能在 GitHub 网页上点「授权」生成，
      脚本无法替代。本脚本覆盖不依赖真实 code 的用例，完整链路需浏览器手动授权。

覆盖用例：
  1. /auth/github/login 正常态 → 302，Location 指向 github.com/authorize，参数正确
  2. /auth/github/callback 缺 code → 400「缺少授权码」
  3. /auth/github/callback 假 code → 401「GitHub 授权失败」（GitHub 对无效 code 返回 404）

未覆盖（需手动）：
  - 未配置 CLIENT_ID → 501（需单独起一个清空 GITHUB_CLIENT_ID 的服务）
  - 真实 code → token → userinfo → JWT 完整链路

用法：
    .venv/Scripts/python eval/eval_http_smoke_oauth.py [--base-url http://127.0.0.1:8000]
输出：
    eval/reports/http-smoke-oauth-report.md
"""

import argparse
import contextlib
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

with contextlib.suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8")


class OAuthSmoke:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self.client = httpx.Client(timeout=60.0, follow_redirects=False)
        self.results: list[dict] = []

    def _record(self, name, path, status, ms, ok, note=""):
        self.results.append({
            "name": name, "path": path, "status": status, "ms": round(ms, 1),
            "ok": ok, "note": note,
        })
        flag = "PASS" if ok else "FAIL"
        print(f"  [{flag}] {name:<26} {path:<40} {status} {ms:6.0f}ms {note}")

    def run(self):
        print(f"目标服务: {self.base}\n")

        # 1. login 正常态 → 302 + Location 参数正确
        t0 = time.perf_counter()
        r = self.client.get(self.base + "/auth/github/login")
        ms = (time.perf_counter() - t0) * 1000
        ok = False
        note = ""
        if r.status_code in (301, 302, 303, 307, 308):
            loc = r.headers.get("location", "")
            parsed = urlparse(loc)
            qs = parse_qs(parsed.query)
            has_host = parsed.netloc == "github.com" and "/login/oauth/authorize" in parsed.path
            cid = qs.get("client_id", [""])[0]
            redirect = qs.get("redirect_uri", [""])[0]
            scope = qs.get("scope", [""])[0]
            state = qs.get("state", [""])[0]
            ok = (
                has_host
                and cid != ""
                and redirect != ""
                and "read:user" in scope
                and state != ""
            )
            note = f"client_id={cid[:12]}… scope={scope} state={state}"
            if not ok:
                note = f"参数异常: host={has_host} redirect={redirect} " + note
        else:
            note = f"期望重定向实为 {r.status_code}: {r.text[:80]}"
        self._record("登录-跳转授权页", "/auth/github/login", r.status_code, ms, ok, note)

        # 2. callback 缺 code → 400
        t0 = time.perf_counter()
        r = self.client.get(self.base + "/auth/github/callback")
        ms = (time.perf_counter() - t0) * 1000
        ok = r.status_code == 400
        self._record("回调-缺授权码", "/auth/github/callback", r.status_code, ms, ok,
                     "" if ok else r.text[:80])

        # 3. callback 假 code → 401（GitHub 对无效 code 返回 404 → exchange 返回 None）
        t0 = time.perf_counter()
        r = self.client.get(self.base + "/auth/github/callback?code=fake_code_123&state=abc")
        ms = (time.perf_counter() - t0) * 1000
        ok = r.status_code == 401
        note = "" if ok else f"实为 {r.status_code}: {r.text[:100]}"
        self._record("回调-无效授权码", "/auth/github/callback?code=…", r.status_code, ms, ok, note)

    def report(self):
        n = len(self.results)
        passed = sum(1 for x in self.results if x["ok"])
        failed = [x for x in self.results if not x["ok"]]
        print(f"\n===== 汇总（{n} 项）=====")
        print(f"通过 {passed}/{n} = {passed / n:.1%}" if n else "无用例")
        for x in failed:
            print(f"  FAIL: {x['name']} → {x['status']} {x['note']}")

        lines = [
            "# GitHub OAuth 冒烟测试报告",
            "",
            f"> 生成时间：{time.strftime('%Y-%m-%d %H:%M')}",
            f"> 目标服务：{self.base}",
            f"> 结果：**{passed}/{n} 通过（{passed / n:.1%}）**" if n else "> 结果：无用例",
            "",
            "## 明细",
            "",
            "| # | 用例 | 路径 | 状态码 | 耗时ms | 结果 | 备注 |",
            "|---|---|---|---|---|---|---|",
        ]
        for i, x in enumerate(self.results, 1):
            lines.append(
                f"| {i} | {x['name']} | `{x['path']}` | {x['status']} | {x['ms']} "
                f"| {'PASS' if x['ok'] else 'FAIL'} | {x['note'][:60]} |"
            )
        lines += [
            "",
            "## 未覆盖（需手动/单独测）",
            "",
            "- 未配置 `GITHUB_CLIENT_ID` → 501（需单独起清空该变量的服务）",
            "- 真实 code → access_token → userinfo → JWT 完整链路（需浏览器授权一次）",
            "",
        ]
        out = ROOT / "eval" / "reports" / "http-smoke-oauth-report.md"
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
        print(f"服务未启动：{args.base_url}\n先运行：.venv/Scripts/python -m uvicorn api:app --port 8000")
        sys.exit(1)

    s = OAuthSmoke(args.base_url)
    try:
        s.run()
    finally:
        s.report()
        s.client.close()


if __name__ == "__main__":
    main()
