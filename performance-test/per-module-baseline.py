"""三模块（模拟面试/MBTI/数据看板）接口基线测量

用法：
    python per-module-baseline.py --token <token> [--runs 8] [--out reports/raw/module-baseline.csv] [--real]

--real 时用真实 DeepSeek（调用 /interview/*、/mbti/analyze 会走真实 LLM）
默认（无 --real）时后端 LLM 指向 mock（需后端已配 DEEPSEEK_BASE_URL=mock）
"""

import argparse
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8000"


def req(method, path, token, body=None, timeout=120):
    headers = {"Authorization": f"Bearer {token}"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            resp.read()
        dur = (time.perf_counter() - t0) * 1000
        return {"ok": True, "ms": dur, "status": resp.status}
    except Exception as e:
        return {"ok": False, "ms": (time.perf_counter() - t0) * 1000, "status": -1, "err": str(e)[:100]}


def create_interview_session(token, n_messages=2):
    """通过 /chat 往默认会话写入面试问答（interview/save、finish 需要 ≥2 条消息）"""
    sid = "u4_default"
    for i in range(n_messages):
        msg = "请出一道 Python 面试题" if i % 2 == 0 else "我会用 Python 列表推导式回答这个问题"
        r = req("POST", "/chat", token, {
            "message": msg,
            "session_id": sid,
            "model_provider": "deepseek",
            "mode": "interview",
        })
        if not r["ok"]:
            print(f"  [warn] 创建会话消息 {i} 失败: {r.get('err', r.get('status'))}")
    return sid


def run_case(args, name, label, method, path, token, body=None, sid=None):
    results = []
    for i in range(args.runs):
        b = body
        if sid and isinstance(b, dict) and b.get("__sid__"):
            b = {k: v for k, v in b.items() if k != "__sid__"}
            b["session_id"] = sid
        r = req(method, path, token, b)
        results.append(r)
        time.sleep(0.2)
    ok_vals = [r["ms"] for r in results if r["ok"]]
    errs = [r for r in results if not r["ok"]]
    row = {
        "module": name, "endpoint": label, "method": method, "path": path,
        "count": len(results), "ok": len(ok_vals), "fail": len(errs),
        "p50": round(statistics.median(ok_vals), 1) if ok_vals else None,
        "p95": round(sorted(ok_vals)[int(len(ok_vals) * 0.95) - 1], 1) if len(ok_vals) >= 20 else
               (round(sorted(ok_vals)[-1], 1) if ok_vals else None),
        "p99": round(sorted(ok_vals)[-1], 1) if ok_vals else None,
        "avg": round(statistics.mean(ok_vals), 1) if ok_vals else None,
        "min": round(min(ok_vals), 1) if ok_vals else None,
        "max": round(max(ok_vals), 1) if ok_vals else None,
    }
    err_detail = f"  fail={len(errs)} 首个错误: {errs[0].get('err')}" if errs else ""
    print(f"  {label:28s} ok={row['ok']}/{row['count']} avg={row['avg']}ms p50={row['p50']}ms p95={row['p95']}ms{err_detail}")
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", required=True)
    parser.add_argument("--runs", type=int, default=8)
    parser.add_argument("--out", default="performance-test/reports/raw/module-baseline.csv")
    parser.add_argument("--real", action="store_true", help="走真实 DeepSeek")
    args = parser.parse_args()

    token = args.token
    print(f"== 三模块基线（每接口 {args.runs} 次，{'真实 DeepSeek' if args.real else 'mock LLM'}）==")

    # 32 题 MBTI 答案（全选 A：合法值 1）
    mbti_answers = [1] * 32

    cases = [
        # ── MBTI ──
        ("MBTI", "GET /mbti/questions", "GET", "/mbti/questions", None),
        ("MBTI", "POST /mbti/analyze", "POST", "/mbti/analyze",
         {"ideal_role": "后端工程师", "answers": mbti_answers}),
        ("MBTI", "GET /mbti/history", "GET", "/mbti/history", None),
        ("MBTI", "POST /mbti/export", "POST", "/mbti/export",
         {"mbti": "ESTJ", "ideal_role": "后端工程师", "analysis": "适合技术管理", "scores": {"EI": 20, "SN": 15, "TF": 18, "JP": 22}}),
        # ── 数据看板 ──
        ("看板", "GET /dashboard/stats", "GET", "/dashboard/stats", None),
    ]

    rows = []
    for name, label, method, path, body in cases:
        rows.append(run_case(args, name, label, method, path, token, body))

    # ── 模拟面试（依赖真实会话消息）──
    print("  [setup] 创建面试会话（2 条消息）...")
    sid = create_interview_session(token)
    if not sid:
        print("  [fatal] 无法创建面试会话，跳过 interview 三接口")
    else:
        rows.append(run_case(args, "面试", "POST /interview/save", "POST", "/interview/save",
                             token, {"__sid__": True}, sid))
        rows.append(run_case(args, "面试", "POST /interview/finish", "POST", "/interview/finish",
                             token, {"__sid__": True}, sid))
        # weakness 是纯 LLM 文本生成（mock LLM 无纯文本响应，只返回 tool_call → 必 400）
        # 故仅在真打模式测；mock 模式下记录说明
        if args.real:
            rows.append(run_case(args, "面试", "POST /interview/weakness", "POST", "/interview/weakness",
                                 token, None))
        else:
            print("  POST /interview/weakness  跳过（mock LLM 无纯文本响应，仅真打模式可测）")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("module,endpoint,method,path,count,ok,fail,p50,p95,p99,avg,min,max\n")
        for r in rows:
            f.write(",".join(str(r[k]) for k in
                             ["module", "endpoint", "method", "path", "count", "ok", "fail",
                              "p50", "p95", "p99", "avg", "min", "max"]) + "\n")
    print(f"已写入 {out}")


if __name__ == "__main__":
    main()
