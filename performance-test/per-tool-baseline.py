"""per-tool 工具级基线测量：6 个工具各发 N 次请求，统计 p50/p95/p99

用法：
    python per-tool-baseline.py --base http://127.0.0.1:8000 --token <token> --runs 10
    （加 --real 走真实环境时输出到 reports/raw/per-tool-real.csv）
"""

import argparse
import concurrent.futures
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

_Q = json.loads((Path(__file__).parent / "test-questions.json").read_text(encoding="utf-8"))


def send_chat(base, token, session_id, message, timeout=120):
    body = json.dumps({
        "message": message,
        "session_id": session_id,
        "model_provider": "deepseek",
        "mode": "workspace",
    }).encode()
    req = urllib.request.Request(
        f"{base}/chat", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        dur = (time.perf_counter() - t0) * 1000
        ok = resp.status == 200 and "reply" in data
        return {"ok": ok, "ms": dur, "status": resp.status}
    except Exception as e:
        return {"ok": False, "ms": (time.perf_counter() - t0) * 1000, "status": -1, "err": str(e)[:80]}


def run_tool(args, tool_name, questions, label):
    results = []
    for i in range(args.runs):
        q = questions[i % len(questions)]
        sid = f"perf_tool_{tool_name}_{i}_{int(time.time())}"
        r = send_chat(args.base, args.token, sid, q)
        results.append(r)
        time.sleep(0.3)  # 避免挤爆队列，每请求间隔
    ok_vals = [r["ms"] for r in results if r["ok"]]
    errs = [r for r in results if not r["ok"]]
    row = {
        "tool": tool_name, "label": label,
        "count": len(results), "ok": len(ok_vals), "fail": len(errs),
        "p50": round(statistics.median(ok_vals), 1) if ok_vals else None,
        "p95": round(sorted(ok_vals)[int(len(ok_vals) * 0.95) - 1], 1) if len(ok_vals) >= 20 else
               (round(sorted(ok_vals)[-1], 1) if ok_vals else None),
        "p99": round(sorted(ok_vals)[-1], 1) if ok_vals else None,
        "avg": round(statistics.mean(ok_vals), 1) if ok_vals else None,
        "min": round(min(ok_vals), 1) if ok_vals else None,
        "max": round(max(ok_vals), 1) if ok_vals else None,
    }
    print(f"  {label:16s} ok={row['ok']}/{row['count']} "
          f"avg={row['avg']}ms p50={row['p50']}ms p95={row['p95']}ms max={row['max']}ms")
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--token", required=True)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--out", default="reports/raw/per-tool-baseline.csv")
    args = parser.parse_args()

    tools = _Q["tools"]
    rows = []
    print(f"== per-tool 基线（每工具 {args.runs} 次）==")
    for name, cfg in tools.items():
        rows.append(run_tool(args, name, cfg["questions"], cfg["label"]))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("tool,label,count,ok,fail,p50,p95,p99,avg,min,max\n")
        for r in rows:
            f.write(",".join(str(r[k]) for k in
                             ["tool", "label", "count", "ok", "fail", "p50", "p95", "p99", "avg", "min", "max"]) + "\n")
    print(f"已写入 {out}")


if __name__ == "__main__":
    main()
