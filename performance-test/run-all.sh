#!/usr/bin/env bash
# ============================================================
#  智能个人助手 · 工作台性能测试一键执行
#  用法: bash run-all.sh [--skip-soak] [--only-mock]
#    --skip-soak  跳过 30 分钟 soak（只跑 quick 场景）
#    --only-mock  只跑 mock 基线，不跑最后一轮真打
# ============================================================
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"          # 项目根
TEST_DIR="$(cd "$(dirname "$0")" && pwd)"          # performance-test
REPORTS="$TEST_DIR/reports"
RAW="$REPORTS/raw"
CHARTS="$REPORTS/charts"
PY="$ROOT/.venv/Scripts/python.exe"
API_PORT=8000
FRONT_PORT=5173
MOCK_LLM_PORT=18001
MOCK_EXT_PORT=18002
LOG="$REPORTS/run-all.log"

SKIP_SOAK=0
ONLY_MOCK=0
for arg in "$@"; do
  case "$arg" in
    --skip-soak) SKIP_SOAK=1 ;;
    --only-mock) ONLY_MOCK=1 ;;
  esac
done

mkdir -p "$RAW" "$CHARTS"
echo "===== 工作台性能测试 $(date '+%Y-%m-%d %H:%M:%S') =====" | tee "$LOG"

# PID 管理
declare -a PIDS=()
cleanup() {
  echo "清理进程..."
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  pkill -f "mock_llm" 2>/dev/null || true
  pkill -f "mock_external" 2>/dev/null || true
  pkill -f "api:app" 2>/dev/null || true
  echo "清理完成" | tee -a "$LOG"
}
trap cleanup EXIT

# ── 0. 环境检查 ──
echo "── [0/7] 环境检查 ──" | tee -a "$LOG"
"$PY" -c "import locust, psutil, fastapi" 2>/dev/null || {
  echo "缺少依赖，安装中..." | tee -a "$LOG"
  "$PY" -m pip install -q locust psutil 2>&1 | tail -1
}
command -v npx >/dev/null 2>&1 || { echo "错误: 需要 Node/npx"; exit 1; }

# ── 1. 启动 mock 服务 ──
echo "── [1/7] 启动 mock 服务 (LLM:$MOCK_LLM_PORT 外部API:$MOCK_EXT_PORT) ──" | tee -a "$LOG"
cd "$TEST_DIR"
MOCK_LLM_LATENCY_MS="${MOCK_LLM_LATENCY_MS:-150}" \
  "$PY" -m uvicorn mock.mock_llm:app --host 127.0.0.1 --port $MOCK_LLM_PORT --log-level warning &
PIDS+=($!)
MOCK_EXTERNAL_LATENCY_MS="${MOCK_EXTERNAL_LATENCY_MS:-80}" \
  "$PY" -m uvicorn mock.mock_external:app --host 127.0.0.1 --port $MOCK_EXT_PORT --log-level warning &
PIDS+=($!)
sleep 2
curl -s "http://127.0.0.1:$MOCK_LLM_PORT/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"你好"}]}' >/dev/null && echo "mock LLM OK" | tee -a "$LOG" \
  || { echo "mock LLM 启动失败"; exit 1; }
curl -s "http://127.0.0.1:$MOCK_EXT_PORT/wttr/北京" >/dev/null && echo "mock external OK" | tee -a "$LOG" \
  || { echo "mock external 启动失败"; exit 1; }

# ── 2. 启动后端（环境变量覆盖：LLM→mock、外部API→mock、限流调高） ──
echo "── [2/7] 启动后端 (port $API_PORT, RATE_LIMIT_MAX=5000, LLM=mock) ──" | tee -a "$LOG"
cd "$ROOT"
DEEPSEEK_BASE_URL="http://127.0.0.1:$MOCK_LLM_PORT/v1" \
WEATHER_API_URL="http://127.0.0.1:$MOCK_EXT_PORT/wttr/{city}?format=j1" \
WEB_SEARCH_URL="http://127.0.0.1:$MOCK_EXT_PORT/search/html" \
GITHUB_API_BASE="http://127.0.0.1:$MOCK_EXT_PORT/github" \
WEIBO_HOT_URL="http://127.0.0.1:$MOCK_EXT_PORT/weibo/ajax/side/hotSearch" \
BAIDU_HOT_URL="http://127.0.0.1:$MOCK_EXT_PORT/top.baidu/api/board?tab=realtime" \
RATE_LIMIT_MAX=5000 \
OBSIDIAN_WATCHER_ENABLED=false \
  "$PY" -m uvicorn api:app --host 127.0.0.1 --port $API_PORT --log-level warning &
PIDS+=($!)
sleep 8
curl -s "http://127.0.0.1:$API_PORT/health" | head -c 200 && echo "" | tee -a "$LOG"

# ── 3. 注册/登录测试用户 ──
echo "── [3/7] 准备测试用户 ──" | tee -a "$LOG"
USER="perf_test_user"; PASS="perf_test_pass123"
curl -s -X POST "http://127.0.0.1:$API_PORT/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$USER\",\"email\":\"perf@test.local\",\"password\":\"$PASS\"}" >/dev/null 2>&1
TOKEN=$(curl -s -X POST "http://127.0.0.1:$API_PORT/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$USER\",\"password\":\"$PASS\"}" | "$PY" -c "import sys,json;print(json.load(sys.stdin).get('token',''))")
if [ -z "$TOKEN" ]; then
  echo "错误: 无法获取测试用户 token（后端未就绪？）" | tee -a "$LOG"
  exit 1
fi
echo "$TOKEN" > "$RAW/token.txt"
echo "token 已获取 ($(echo -n "$TOKEN" | wc -c) 字符)" | tee -a "$LOG"

# ── 4. 启动前端 dev ──
echo "── [4/7] 启动前端 dev (port $FRONT_PORT) ──" | tee -a "$LOG"
cd "$ROOT/frontend"
npm run dev -- --port $FRONT_PORT --strictPort > /dev/null 2>&1 &
PIDS+=($!)
sleep 6
curl -s -o /dev/null -w "前端 HTTP %{http_code}\n" "http://127.0.0.1:$FRONT_PORT/" | tee -a "$LOG"

# ── 5. Lighthouse 前端首屏 ──
echo "── [5/7] Lighthouse 前端首屏测试 ──" | tee -a "$LOG"
cd "$TEST_DIR"
npx --yes lighthouse "http://127.0.0.1:$FRONT_PORT/" \
  --quiet --chrome-flags="--headless --no-sandbox --disable-gpu" \
  --output=json --output-path="$RAW/lighthouse.json" \
  --only-categories=performance --throttling-method=provided >/dev/null 2>&1 \
  && echo "lighthouse 完成" | tee -a "$LOG" || echo "lighthouse 跳过（可能无 Chrome）" | tee -a "$LOG"

# ── 6. locust 压测场景 ──
export BASE_URL="http://127.0.0.1:$API_PORT"
export TOKEN
export USERNAME="$USER"
export PASSWORD="$PASS"
cd "$TEST_DIR"

run_locust() {
  local user_class="$1" users="$2" spawn="$3" runtime="$4" out="$5"
  echo "--- 场景 [${user_class}] users=$users runtime=$runtime ---" | tee -a "$LOG"
  "$PY" -m locust -f locustfile.py "$user_class" --headless -u "$users" --spawn-rate "$spawn" \
    --run-time "$runtime" --html "$out" \
    --host "$BASE_URL" >/dev/null 2>&1
  echo "  完成 → $out" | tee -a "$LOG"
}

echo "── [6/7] locust 压测 ──" | tee -a "$LOG"

# 6.1 单工具基线（1 用户，3 分钟，覆盖全部工具）
run_locust "WorkstationUser" 1 1 "3m" "$REPORTS/single-tool-baseline.html"

# 6.2 多工具并行（5 用户，2 分钟）
run_locust "WorkstationUser" 5 2 "2m" "$REPORTS/parallel-multi-tool.html"

# 6.3 高并发阶梯（1/5/10/30/50 → 每档 90 秒）
for users in 1 5 10 30 50; do
  run_locust "WorkstationUser" "$users" 2 "90s" "$REPORTS/stress-${users}u.html"
done

# 6.4 长会话多轮（10 用户，5 分钟，同一 session 连续对话）
run_locust "LongSessionUser" 10 3 "5m" "$REPORTS/long-session.html"

# 6.5 资源监控（配合 soak 并行跑）
if [ "$SKIP_SOAK" -eq 0 ]; then
  echo "--- 场景 [soak] 30 分钟 + 资源监控 ---" | tee -a "$LOG"
  BACKEND_PID=$(pgrep -f "uvicorn api:app" | head -1 || echo "")
  if [ -n "$BACKEND_PID" ]; then
    "$PY" resource-monitor.py --out "$RAW/resource-soak.csv" --pid "$BACKEND_PID" \
      --interval 5 --duration 1800 > /dev/null 2>&1 &
    PIDS+=($!)
  fi
  run_locust "WorkstationUser" 10 2 "30m" "$REPORTS/soak-30min.html"
fi

# ── 7. 真打对比（可选，消耗 LLM 配额）──
if [ "$ONLY_MOCK" -eq 0 ] && [ -n "${DEEPSEEK_API_KEY:-}" ]; then
  echo "── [7/7] 真打对比（真实 DeepSeek） ──" | tee -a "$LOG"
  cd "$ROOT"
  OBSIDIAN_WATCHER_ENABLED=false \
    "$PY" -m uvicorn api:app --host 127.0.0.1 --port 8001 --log-level warning &
  REAL_PID=$!
  sleep 8
  cd "$TEST_DIR"
  BASE_URL="http://127.0.0.1:8001" run_locust "single" 1 1 "2m" "$REPORTS/real-llm-single.html"
  kill "$REAL_PID" 2>/dev/null || true
else
  echo "── [7/7] 跳过真打对比（--only-mock 或未设 DEEPSEEK_API_KEY） ──" | tee -a "$LOG"
fi

echo "===== 全部完成 $(date '+%H:%M:%S') → 报告见 reports/ =====" | tee -a "$LOG"
