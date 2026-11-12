# 🧠 成长智伴 · Python + DeepSeek + React

> 一个以 **个人 Obsidian 笔记库**为核心知识源的成长智能体。基于 **FastAPI + DeepSeek**（兼容多家 OpenAI 格式模型）构建，具备用户认证、长期记忆、多会话隔离、RAG 知识库检索、自主工具调用（Function Calling）与流式输出，并附带 **React 前端**。在此基础上提供 **模拟面试 / MBTI 测试 / 数据看板** 三个成长向业务模块。

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![DeepSeek](https://img.shields.io/badge/DeepSeek-API-orange.svg)](https://deepseek.com/)
[![React](https://img.shields.io/badge/React-19+-61DAFB.svg)](https://react.dev/)

---

## ✨ 功能特性

### 🤖 Agent 与对话
- **Agent 架构**：Agent / Tools / Memory / Knowledge / LLM 适配层完全解耦
- **Function Calling 自主决策**：LLM 动态决定调用哪个工具、提取哪些参数
- **ReAct 多轮循环**：推理 → 执行工具 → 观察结果 → 再推理，默认上限 5 轮，超限强制收口
- **四通道执行**：`run`（同步）· `arun`（异步）· `run_stream`（同步流式）· `arun_stream`（异步流式）
- **三种对话模式**：工作台 / 模拟面试 / 知识库问答
- **智能会话标题**：首轮对话后异步生成 4–8 字标题，不阻塞响应
- **深度思考开关**：按厂商协议传 `thinking` 参数，并联动放大 `max_tokens`

### 📚 知识库（RAG）
- **Obsidian 笔记库 RAG**：直连本地 vault 建立独立索引，与上传文档知识库互不串味
- **增量索引**：确定性文档 ID + mtime 比对，只处理新增 / 变更 / 删除的文件
- **实时监视**：watchdog 变更即触发（未安装自动回退 5s 轮询），短时多次保存防抖合并
- **混合检索**：dense 语义检索 + BM25 关键词检索，RRF 融合排序
- **上传文档 RAG**：PDF / TXT / MD → 切片 → 向量化 → 检索 → 生成答案
- **笔记读写**：Agent 可检索、读取、创建 Obsidian 笔记（限制在 vault 内，受排除清单保护）

### 🧠 记忆
- **双层记忆**：SQLite 持久化对话历史 + Chroma 向量记忆（语义检索补上下文）
- **上下文压缩**：消息数超阈值自动滚动摘要，只保留最近原文，控制 token 成本
- **多会话隔离**：每个用户独立会话列表，历史读取 / 删除均校验归属

### 🎯 个人成长
- **模拟面试**：题库取自笔记库「疑难总结」，一题一答，答完点评并自动出下一题
- **面试归档**：整场对话整理成记录写入 Obsidian，并汇总生成「薄弱点画像」
- **MBTI 测试**：32 题加权计分，LLM 分析理想岗位适配度，结果存档支持历史对比
- **数据看板**：笔记数 / 面试次数 / MBTI 次数 / 会话数

### 🔐 账户与模型
- **双登录通道**：本地账号（bcrypt + JWT）与 GitHub OAuth2.0
- **用户级密钥**：每个用户可填写自己的 DeepSeek / GLM / Qwen Key，覆盖全局配置
- **多模型切换**：前端按 provider + 具体型号切换，未配 Key 时自动回退兜底厂商

### 🧩 工程
- **装饰器工具注册**：`@registry.register()` 一行注册，自动从函数签名生成 JSON Schema
- **MCP 客户端**：连接外部 MCP server（stdio），工具以 `mcp_` 前缀注入 Agent
- **安全计算**：AST 白名单求值器，替代危险的 `eval()`
- **限流 + 统一错误响应**：内存滑动窗口限流（敏感接口更严），全局异常处理器
- **结构化日志** · **容器化就绪** · **CI（ruff + pytest）**

---

## 🗂️ 项目结构

```
成长智伴/
├── api.py                      # FastAPI 服务入口（30+ 路由：认证/聊天/知识库/MBTI/面试/笔记/看板）
├── app.py                      # 终端交互入口（CLI）
├── config.py                   # 全局配置：环境变量 + LLM 厂商 + Obsidian + GitHub OAuth
├── mbti.py                     # MBTI：32 题题库 + 加权计分 + LLM 岗位适配分析
├── interview.py                # 模拟面试：记录归档 + 薄弱点画像生成
├── dashboard.py                # 数据看板统计
├── mcp_client.py               # MCP 客户端：连接外部 MCP server，注册 mcp_ 前缀工具
├── requirements.txt            # Python 依赖
├── pyproject.toml              # ruff / mypy / pytest 配置
├── Dockerfile                  # 两阶段容器化（构建前端 → 运行后端）
├── docker-compose.yml          # 编排配置（挂载 docs / memory / chroma / vault）
├── render.yaml / vercel.json   # 部署配置（Render / Vercel）
├── mcp_config.example.json     # MCP server 配置示例（实际配置写入 mcp_config.json）
├── request.http                # PyCharm HTTP Client 调试脚本
│
├── agent/
│   └── agent.py                # Agent 调度器：四通道 + ReAct 多轮 tool-calling + 记忆集成
│
├── chatbot/
│   └── chatbot.py              # LLM 适配层：BaseLLM 抽象 + 三厂 MODEL_PRESETS + <think> 清洗
│
├── tools/
│   ├── __init__.py             # ToolRegistry + @registry.register() 装饰器（自动生成 Schema）
│   ├── calculator.py           # 安全数学计算（AST 白名单）
│   ├── weather.py              # 天气查询（wttr.in，无需 Key）
│   ├── hotlist.py              # 今日热榜（GitHub 趋势 / 微博热搜 / 百度热搜）
│   ├── web_search.py           # 联网搜索（DuckDuckGo，无需 Key）
│   ├── rag_tool.py             # 上传文档知识库检索工具
│   ├── obsidian.py             # Obsidian 笔记：检索 / 读取 / 写入
│   └── mock_interview.py       # 模拟面试出题（题库取自 Obsidian 疑难总结）
│
├── memory/
│   ├── memory.py               # SQLite 七张表：对话/摘要/用户/token/会话/密钥/MBTI
│   ├── summarizer.py           # 上下文压缩：滚动摘要
│   └── vector_memory.py        # Chroma 向量记忆：对话历史语义检索
│
├── knowledge/
│   ├── config.py               # 切片 / 检索 / Embedding / 向量库 配置
│   ├── loader.py               # 文档加载（TXT / MD / PDF）+ 排除清单匹配
│   ├── chunker.py              # 文本切片（递归切分 + 标题注入）
│   ├── embeddings.py           # Embedding：Chroma 内置 / DeepSeek API 可切换
│   ├── vector_store.py         # 向量存储（LangChain + Chroma 封装，多 collection 单例）
│   ├── retriever.py            # 检索器 + 上下文格式化
│   ├── hybrid.py               # 混合检索：BM25 + 中文分词 + RRF 融合
│   ├── obsidian_watcher.py     # vault 文件监视（watchdog / 轮询回退）
│   └── pipeline.py             # RAG 主流程：index_documents / query / index_obsidian
│
├── auth/
│   └── __init__.py             # 认证封装 + GitHub OAuth2.0（基于 memory 层）
│
├── utils/
│   └── logger.py               # 日志模块（标准 logging + 彩色控制台）
│
├── tests/                      # 12 个测试文件 + conftest（约 78 个用例）
├── eval/                       # RAG 评测：golden set + 检索层指标 + 生成层 LLM-as-a-Judge
├── performance-test/           # locust 压测 + Lighthouse 前端测速 + 资源监控
│
└── frontend/                   # React 聊天界面
    ├── vite.config.ts          # Vite 配置（dev 端口 5173，代理到后端 8000）
    ├── src/
    │   ├── App.tsx             # 单页应用：认证/主页/聊天/个人/MBTI/看板 六个视图
    │   ├── InterviewExam.tsx   # 模拟面试考试式组件（setup / running / finished）
    │   ├── api.ts              # 请求封装（超时控制 + 统一错误）
    │   ├── markdown.tsx        # markdown-it + DOMPurify 双层过滤渲染
    │   ├── Button.tsx / Toast.tsx / ErrorBoundary.tsx
    │   ├── index.css           # Tailwind 入口
    │   └── main.tsx            # React 入口
    └── package.json
```

---

## 🏗️ 架构与关键设计

### 请求链路

```
浏览器（React SPA）
  │  SSE / JSON
  ▼
FastAPI（限流中间件 → 鉴权依赖 → 路由）
  │
  ▼
AgentPool（LRU，按 session_id 复用实例）
  │
  ▼
Agent 重建上下文：system prompt + 会话摘要 + 最近历史 + 向量记忆
  │
  ▼
ReAct 循环（≤5 轮）：LLM 决策 → 执行工具 → 结果回填 messages → 再推理
  │
  ▼
流式 / 一次性返回，本轮消息批量落库（单事务）
```

### 关键设计

| 设计 | 做法 | 解决的问题 |
|------|------|-----------|
| **四通道执行** | LLM 调用走 `AsyncOpenAI`；工具优先 async 版，无则 `asyncio.to_thread` 入线程池 | 同步调用阻塞事件循环，高并发下请求无法完成 |
| **混合检索** | dense 语义检索 + BM25 关键词检索，按 RRF（`k=60`）融合排序 | 本地 embedding 对中文召回弱，单路检索漏召回 |
| **增量索引** | `sha1(相对路径)` 作文档 ID，mtime 比对跳过未变文件，变更先删后写，消失则删 | 全量重索引开销大、频次受限 |
| **上下文压缩** | 消息数超阈值触发滚动摘要，记录压缩边界，只保留最近若干条原文 | messages 无限膨胀导致 token 成本失控 |
| **工具注册** | 装饰器从函数签名 + 类型注解推断 JSON Schema；async 版自动复用同名 schema | 手动维护 schema 与实现易脱节 |
| **多级降级** | embedding 远程失败回本地；watchdog 缺库回轮询；jieba 缺库回 n-gram 分词 | 可选依赖缺失时功能整体不可用 |
| **写入优化** | SQLite WAL + `busy_timeout` + 批量单事务落库 | 高并发下写锁竞争与写放大 |

---

## 🛠️ 技术栈

| 层 | 技术 |
|----|------|
| 后端框架 | Python 3.11+ + FastAPI + Uvicorn |
| 大模型 | DeepSeek / 智谱 GLM / 通义千问（OpenAI 兼容协议），支持用户级独立密钥 |
| RAG | LangChain + ChromaDB + rank-bm25 + jieba |
| 持久化 | SQLite（WAL）+ Chroma 向量库 |
| 认证 | PyJWT + bcrypt + GitHub OAuth2.0 |
| 外部工具 | MCP（stdio）、wttr.in、DuckDuckGo、GitHub / 微博 / 百度热榜 |
| 数据校验 | Pydantic v2 |
| 前端 | React 19 + TypeScript + Vite 8 + Tailwind CSS 4 + markdown-it + DOMPurify |
| 质量保障 | pytest（约 78 用例）+ ruff；locust 压测 + Lighthouse 前端测速 |
| 容器化 | Docker（两阶段构建） |

---

## 🚀 快速开始

### 1. 配置后端

```bash
# 创建虚拟环境（推荐 Python 3.11+）
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 创建 .env 文件，至少填入 LLM Key，并固定 JWT_SECRET
echo DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxx > .env
```

> ⚠️ 生产环境必须显式配置 `JWT_SECRET`。未配置时服务会用随机密钥启动，**重启后所有已签发 token 失效**（前端会 401）。

### 2. 启动后端

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

访问 http://127.0.0.1:8000/docs 查看 Swagger 文档。

> 所有需要登录态的接口都要求 `Authorization: Bearer <token>` 请求头（由 `/auth/register` 或 `/auth/login` 返回）。

### 3. 启动前端（新开一个终端）

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173 即可开始对话（Vite 已配置代理，将 `/chat`、`/auth`、`/knowledge`、`/user`、`/mbti`、`/interview`、`/notes`、`/dashboard`、`/obsidian`、`/models` 转发到后端 8000）。

### 4. 测试

```bash
# 在项目根目录运行
pytest
```

---

## 🔐 环境变量

在 `.env` 中配置（大部分有合理默认值，最少只需填一个 LLM Key）：

```ini
# ── 默认 LLM 提供商（唯一配置源：聊天 + RAG 问答 + 评测 + 前端默认选中）──
# 可选: deepseek | glm | qwen，改这一行即可全链路切换
LLM_PROVIDER=glm
# 兜底：LLM_PROVIDER 非法或对应厂商未配 Key 时回退到它
FALLBACK_LLM_PROVIDER=deepseek

# ── 深度思考（思维链）──
# 默认关闭：日常对话更快更省 token；开启时思考过程与正文共享 max_tokens
# LLM_THINKING=false
# LLM_THINKING_MAX_TOKENS=2048

# ── 主模型（DeepSeek）──
DEEPSEEK_API_KEY=sk-xxx
# DEEPSEEK_BASE_URL=https://api.deepseek.com
# DEEPSEEK_MODEL=deepseek-v4-flash

# ── 智谱 GLM ──
# GLM_API_KEY=your-zhipu-key-here
# GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
# GLM_MODEL=glm-4.5-air

# ── 通义千问 ──
# QWEN_API_KEY=your-dashscope-key-here
# QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
# QWEN_MODEL=qwen-turbo

# ── 安全（生产必配）──
# JWT_SECRET=               # 不配则每次启动随机生成，重启后旧 token 全部失效
# JWT_EXPIRE_HOURS=24

# ── Obsidian 笔记库（可选，不配则相关功能跳过）──
# OBSIDIAN_VAULT_DIR=D:/your/vault
# OBSIDIAN_COLLECTION=obsidian
# OBSIDIAN_EXCLUDE=API.md      # 排除清单：这些文件永不被索引或读取（逗号分隔）
# OBSIDIAN_WATCHER_ENABLED=true
# OBSIDIAN_WATCH_INTERVAL=5

# ── 知识库 / RAG ──
# KNOWLEDGE_DOCS_DIR=knowledge/docs
# KNOWLEDGE_CHUNK_SIZE=500
# KNOWLEDGE_CHUNK_OVERLAP=50
# KNOWLEDGE_RETRIEVE_TOP_K=3
# KNOWLEDGE_EMBEDDING=default  # default(Chroma 内置) | deepseek
# KNOWLEDGE_VECTOR_DB_DIR=knowledge/chroma_db

# ── GitHub OAuth2.0（可选）──
# GITHUB_CLIENT_ID=
# GITHUB_CLIENT_SECRET=
# GITHUB_REDIRECT_URI=http://127.0.0.1:8000/auth/github/callback

# ── 运行时调优 ──
# LOG_LEVEL=INFO               # 日志级别（DEBUG / INFO / WARNING / ERROR，非法值回退 INFO）
# RATE_LIMIT_MAX=30            # 每 60s 每 IP 每路径最大请求数（登录/注册固定 5 次）
# AGENT_POOL_MAX=200           # Agent 实例池 LRU 上限
# MEMORY_DB_PATH=memory/chat_history.db
# VECTOR_MEMORY_DIR=memory/vector_memory_db
# MCP_CONFIG_PATH=mcp_config.json
# FRONTEND_URL=http://localhost:5173   # GitHub 登录成功后的前端跳转地址
# ENVIRONMENT=production       # 标记为生产环境（JWT_SECRET 缺失时直接阻断启动）

# ── 外部数据源覆盖（一般不用改，压测 mock 时用）──
# WEATHER_API_URL=https://wttr.in/{city}?format=j1
# GITHUB_API_BASE=https://api.github.com
# WEIBO_HOT_URL=https://weibo.com/ajax/side/hotSearch
# BAIDU_HOT_URL=https://top.baidu.com/api/board?tab=realtime
```

默认 Embedding 使用 ChromaDB 内置的 `all-MiniLM-L6-v2`（无需额外 Key）；若将 `KNOWLEDGE_EMBEDDING=deepseek` 且配置了 `DEEPSEEK_API_KEY`，则改用 DeepSeek Embedding API。

---

## 🔌 API 一览

所有接口前缀即路径本身，交互文档见 `/docs`。除通用与认证接口外，其余均需 `Authorization: Bearer <token>`。

### 通用
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 服务状态 + Obsidian vault 概况 |
| GET | `/health` | 健康检查（数据库 + 向量库） |

### 认证
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/register` | 注册，返回 `token` 与 `session_id` |
| POST | `/auth/login` | 登录，返回 `token` 与 `session_id` |
| POST | `/auth/logout` | 登出（吊销 token） |
| GET | `/auth/github/login` | 跳转 GitHub 授权页 |
| GET | `/auth/github/callback` | GitHub 回调，成功后跳回前端并携带 token |

### 用户中心
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/user/profile` | 获取当前用户信息 |
| PUT | `/user/profile` | 修改显示名称 |
| PUT | `/user/password` | 修改密码 |
| GET | `/user/llm-keys` | 列出已配置的模型密钥（脱敏） |
| PUT | `/user/llm-keys` | 保存某厂商的用户级密钥 |
| DELETE | `/user/llm-keys/{provider}` | 删除某厂商密钥 |
| GET | `/models` | 模型列表：全局可用 / 用户已配 / 实际生效 + 型号目录 |

### 会话管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/user/sessions` | 会话列表（含预览与消息数） |
| POST | `/user/sessions` | 创建新会话 |
| PATCH | `/user/sessions/{session_id}` | 修改会话标题 |
| DELETE | `/user/sessions/{session_id}` | 删除会话（校验归属） |
| GET | `/user/sessions/{session_id}/messages` | 获取历史消息（校验归属） |

### 聊天
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat` | 非流式对话，body：`{ message, session_id, model_provider, mode, thinking, model }` |
| POST | `/chat/stream` | 流式对话（SSE），返回 `data: {...}` 事件流 |

`model_provider` 取值：`deepseek` | `glm` | `qwen`；`mode` 取值：`workspace` | `interview`。

### 知识库
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/knowledge/upload` | 上传文档（PDF / TXT / MD） |
| POST | `/knowledge/index` | 索引 `knowledge/docs/` 下所有文档 |
| POST | `/knowledge/query` | 基于上传文档知识库生成回答 |
| POST | `/obsidian/index` | 增量索引 Obsidian vault（`?force=true` 全量重建） |
| GET | `/obsidian/status` | 查看 vault 路径、排除清单与已索引切片数 |

### 个人成长
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/mbti/questions` | 获取 32 道测试题 |
| POST | `/mbti/analyze` | 提交答案 → 计算类型 + LLM 岗位适配分析 |
| GET | `/mbti/history` | 测试历史（观察类型稳定性） |
| POST | `/mbti/export` | 导出「我的 MBTI 档案.md」到 Obsidian |
| POST | `/interview/save` | 归档一次模拟面试记录到 Obsidian |
| POST | `/interview/finish` | 结束面试：归档记录 + 薄弱点分析（幂等） |
| POST | `/interview/weakness` | 汇总历史记录生成「薄弱点画像」 |
| POST | `/notes/save` | 把一段内容快捷保存为 Obsidian 笔记 |
| POST | `/notes/save-session` | 把整个会话导出为 Obsidian 笔记 |
| GET | `/dashboard/stats` | 使用数据看板统计 |

**调用示例：**

```bash
# 1. 注册拿到 token
TOKEN=$(curl -s -X POST "http://127.0.0.1:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","email":"a@b.com","password":"secret123"}' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")

# 2. 发起对话
curl -X POST "http://127.0.0.1:8000/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message":"今天 GitHub 有什么热门项目","session_id":"s1","model_provider":"deepseek"}'
```

---

## 🧰 Agent 工具箱

工具通过 `@registry.register()` 装饰器自动注册，schema 由函数签名生成。

| 工具 | 来源 | 触发场景 |
|------|------|---------|
| `calculate` | `calculator.py` | 数学运算（AST 白名单安全求值） |
| `get_weather` | `weather.py` | 查询天气（wttr.in，无需 Key） |
| `get_hotlist` | `hotlist.py` | GitHub 趋势 / 微博热搜 / 百度热搜 |
| `web_search` | `web_search.py` | 联网搜索最新资讯（DuckDuckGo，无需 Key） |
| `knowledge_search` | `rag_tool.py` | 检索上传文档知识库 |
| `search_obsidian_notes` | `obsidian.py` | 语义检索个人笔记库 |
| `read_obsidian_note` | `obsidian.py` | 读取指定笔记原文 |
| `mock_interview` | `mock_interview.py` | 模拟面试出题 |
| `mcp_{server}_{tool}` | `mcp_client.py` | 外部 MCP 工具（连接后动态注册） |

### 加一个新工具

```python
from tools import registry

@registry.register(description="查询新闻")
def get_news(topic: str) -> str:
    """获取指定主题的最新新闻"""
    return f"{topic} 的最新新闻..."
```

装饰器自动解析参数类型、生成 Schema、注册到全局注册表。如果需要异步版本（供 `Agent.arun` 使用），再加一个以 `_async` 结尾的协程函数并用 `@registry.register_async()` 注册，它会自动复用同名 schema：

```python
@registry.register_async(description="查询新闻")
async def get_news_async(topic: str) -> str:
    ...
```

---

## 📚 知识库使用流程

### 上传文档知识库
1. 把文档放进 `knowledge/docs/`（支持 `.txt` / `.md` / `.pdf`）
2. 调用 `POST /knowledge/index` 完成切片与向量化（也可通过 `POST /knowledge/upload` 先上传）
3. 提问命中时 Agent 会自动调用 `knowledge_search`；也可直接调用 `POST /knowledge/query`

### Obsidian 笔记库
1. 在 `.env` 中设置 `OBSIDIAN_VAULT_DIR` 指向 vault 目录
2. 服务启动时会自动检查并索引；也可手动调用 `POST /obsidian/index`
3. 之后 Agent 会在需要时自动调用 `search_obsidian_notes` / `read_obsidian_note`；写笔记则由 Agent 生成 Markdown 正文，用户用界面「存为笔记」按钮保存
4. vault 文件变更由监视器自动触发重索引（`OBSIDIAN_WATCHER_ENABLED=false` 可关闭）

> 排除清单（`OBSIDIAN_EXCLUDE`）中的文件永不被索引或读取，用于保护存放密钥等敏感信息的文件。

---

## 🔌 MCP 外部工具（可选）

复制 `mcp_config.example.json` 为 `mcp_config.json` 并按需修改，服务启动时会自动连接并注册工具：

```json
{
  "mcpServers": {
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "D:/your/vault"]
    }
  }
}
```

> 首次启动需下载 npx 包，因此连接超时设为 90s。MCP 连接失败不影响主服务，仅跳过外部工具（详见启动日志）。

---

## 📊 质量与性能

- **RAG 评测**：`eval/` 下含 golden set（问题 + 期望文档 + 答案要点），分两层评测——检索层（dense / BM25 / RRF 命中率，零成本）与生成层（LLM-as-a-Judge，指标对齐 RAGAS）。
- **压测**：`performance-test/` 下基于 locust（1–50 并发）+ Lighthouse（前端测速）+ 资源监控，含 mock LLM 与 mock 外部服务，避免压测期间真实调用第三方。
- **单测**：`tests/` 下 12 个测试文件，覆盖认证、记忆、Agent 工具执行、混合检索、切片、Obsidian 笔记落盘（含路径逃逸拒绝）、MBTI 计分、面试归档、看板聚合等。

---

## 🐳 Docker 部署

```bash
docker build -t growth-companion .
docker run -p 8000:8000 growth-companion
```

也可使用 `docker-compose up`（已配置 docs / memory / chroma / vault 目录挂载），或参考项目根目录的 `render.yaml`（Render）与 `vercel.json`（Vercel）做平台部署。

---

## 🧪 测试

```bash
pytest
```

覆盖用户注册 / 登录 / JWT、消息与摘要记忆、Agent ReAct 工具执行、工具注册表、安全计算器（含 `__import__` / `open` / `eval` 注入防护）、MBTI 加权计分、RRF 融合与中文分词、chunk 头部注入、Obsidian 笔记落盘与路径逃逸拒绝、MCP 配置、面试归档与薄弱点画像、看板聚合。

CI（`.github/workflows/ci.yml`）在 push / PR 时运行 `ruff check` 与 `pytest`。

---

## 📄 License

MIT License © 2026
