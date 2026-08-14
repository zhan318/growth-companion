#!/usr/bin/env bash
# Lighthouse 前端首屏性能测试：跑 3 次取中位数
# 用法: bash lighthouse-runner.sh <url> <outdir>
set -euo pipefail

URL="${1:?需要 URL，如 http://127.0.0.1:5173}"
OUT="${2:?需要输出目录}"
mkdir -p "$OUT"

echo "== Lighthouse 首屏测试: $URL (跑 3 次取中位数) =="

# 检查 lighthouse 是否可用
if ! command -v lighthouse >/dev/null 2>&1; then
  echo "错误: 未找到 lighthouse，请先安装: npm install -g lighthouse"
  exit 1
fi

RUNS=3
for i in $(seq 1 $RUNS); do
  echo "--- 第 $i 次 ---"
  lighthouse "$URL" \
    --quiet \
    --chrome-flags="--headless --no-sandbox --disable-gpu" \
    --output=json \
    --output-path="$OUT/lighthouse-run$i.json" \
    --only-categories=performance \
    --throttling-method=provided 2>/dev/null || true
done

# 汇总三个结果的性能分 + 核心指标到 CSV
python - "$OUT" <<'PY'
import csv, json, sys, os
outdir = sys.argv[1]
rows = []
for i in range(1, 4):
    p = os.path.join(outdir, f"lighthouse-run{i}.json")
    if not os.path.exists(p):
        continue
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    audits = data.get("audits", {})
    def num(key):
        a = audits.get(key, {})
        v = a.get("numericValue")
        return round(v, 1) if v is not None else None
    rows.append({
        "run": i,
        "performance_score": round(data.get("categories", {}).get("performance", {}).get("score", 0) * 100, 1),
        "FCP_ms": num("first-contentful-paint"),
        "LCP_ms": num("largest-contentful-paint"),
        "TTI_ms": num("interactive"),
        "TBT_ms": num("total-blocking-time"),
        "CLS": num("cumulative-layout-shift"),
    })

# 取中位数
def median(vals):
    vs = sorted(v for v in vals if v is not None)
    if not vs:
        return None
    n = len(vs)
    return vs[n // 2] if n % 2 else (vs[n//2-1] + vs[n//2]) / 2

summary = {
    "runs": rows,
    "median": {k: median([r[k] for r in rows]) for k in rows[0] if k != "run"},
}
with open(os.path.join(outdir, "lighthouse-summary.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print("Lighthouse 汇总(中位数):")
for k, v in summary["median"].items():
    print(f"  {k}: {v}")
PY
