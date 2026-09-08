# 性能测试（工作台）

针对「成长智伴」工作台（chat 页 + 6 工具链路）的全面性能测试套件。

## 架构速览

```
performance-test/
├── run-all.sh              # 一键执行（mock 基线 + 可选真打）
├── locustfile.py           # 压测场景定义（tags: single/parallel/stress/soak/longsession）
├── test-questions.json     # 测试问题集（6 工具 × 3 问 + 多工具并行 + 长会话 20 轮）
├── resource-monitor.py     # psutil 资源监控（CPU/内存/连接/句柄 → CSV）
├── lighthouse-runner.sh    # 前端首屏（跑 3 次取中位数）
├── mock/
│   ├── mock_llm.py         # Mock LLM（OpenAI 兼容，含 tool_calls 路由）port 18001
│   └── mock_external.py    # Mock 外部 API（天气/搜索/热榜）port 18002
├── real-round/             # 最后一轮真打对比
└── reports/                # 报告 + 原始数据
```

## 核心设计决策

1. **Mock LLM + 最后一轮真打**：mock 测出「自己代码的真实瓶颈」（Agent 循环/工具/记忆/向量检索），真打测出「LLM 贡献的延迟」，两层数据相减即外部依赖开销。mock 期间**零 API 配额消耗**。
2. **工具级 URL 覆盖**（方案 A，最小侵入）：`tools/weather.py`、`web_search.py`、`hotlist.py` 支持环境变量覆盖上游 URL，默认行为不变；`api.py` 限流支持 `RATE_LIMIT_MAX` 环境变量覆盖（默认仍 30）。
3. **共享 token**：登录一次，所有压测用户复用，避开登录接口的 5 次/60s 敏感限流。

## 快速开始

```bash
# 0. 安装测试依赖（进项目 .venv，不污染系统）
./.venv/Scripts/python.exe -m pip install locust psutil

# 1. 跑全流程（mock 基线 + 最后一轮真打）
bash performance-test/run-all.sh

# 2. 跳过 30 分钟 soak（快速验证）
bash performance-test/run-all.sh --skip-soak

# 3. 只跑 mock，不消耗 LLM 配额
bash performance-test/run-all.sh --only-mock
```

## 手动分步执行（调试用）

```bash
# 1. 起 mock
./.venv/Scripts/python.exe -m uvicorn mock.mock_llm:app --port 18001 &
./.venv/Scripts/python.exe -m uvicorn mock.mock_external:app --port 18002 &

# 2. 起后端（环境变量覆盖 → mock）
DEEPSEEK_BASE_URL="http://127.0.0.1:18001/v1" \
WEATHER_API_URL="http://127.0.0.1:18002/wttr/{city}?format=j1" \
WEB_SEARCH_URL="http://127.0.0.1:18002/search/html" \
GITHUB_API_BASE="http://127.0.0.1:18002/github" \
WEIBO_HOT_URL="http://127.0.0.1:18002/weibo/ajax/side/hotSearch" \
BAIDU_HOT_URL="http://127.0.0.1:18002/top.baidu/api/board?tab=realtime" \
RATE_LIMIT_MAX=5000 \
./.venv/Scripts/python.exe -m uvicorn api:app --port 8000

# 3. 前端
cd frontend && npm run dev &

# 4. 登录拿 token
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/auth/login -H "Content-Type: application/json" \
  -d '{"username":"perf_test_user","password":"perf_test_pass123"}' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")

# 5. 单工具基线压测
BASE_URL=http://127.0.0.1:8000 TOKEN=$TOKEN \
./.venv/Scripts/python.exe -m locust -f locustfile.py --headless -u 1 -r 1 --run-time 2m \
  --tags single --html reports/single-tool-baseline.html

# 6. 资源监控（另开终端，配合长压测）
./.venv/Scripts/python.exe resource-monitor.py --out reports/raw/resource-soak.csv --pid <后端PID> --interval 5 --duration 1800

# 7. 前端首屏（另开终端）
npx lighthouse http://127.0.0.1:5173/ --only-categories=performance --output=json --output-path=reports/raw/lighthouse.json
```

## 场景说明

| tag | 场景 | 说明 |
|---|---|---|
| `single` | 单工具基线 | 6 类问题（天气/热榜/搜索/数学/Obsidian/面试）随机轮询，量 p50/p95/p99 |
| `parallel` | 多工具并行 | 一次消息触发多个 tool_calls（mock LLM 路由），测 Agent 多工具编排 |
| `stress` | 高并发阶梯 | 1/5/10/30/50 用户逐档压，找 QPS 拐点与错误率阈值 |
| `soak` | 30 分钟长稳 | 中等并发持续压，观察内存/连接数漂移（配合资源监控） |
| `longsession` | 长会话多轮 | 同一 session 连续 20 轮，观察上下文增长下的延迟变化 |

## 已知边界（报告需注明）

- **dev 模式 overhead**：uvicorn reload / vite dev 比生产慢 30-50%，报告标注。
- **Lighthouse 无登录态**：headless 无 token，测的是登录页首屏（SPA bundle 加载），不代表 hub 页内容渲染。
- **Mock 数据偏理想**：外部 API mock 返回 3-5 条固定结果，无真实网络抖动。
- **单机环境**：locust 与后端同机，压测端自身开销计入，高并发数据偏保守。
