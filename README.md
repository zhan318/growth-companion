# 🧠 智能个人助手 · Python + DeepSeek + React

> 一个基于 **DeepSeek API**（兼容多种 OpenAI 格式模型）和 **FastAPI** 的知识库智能 Agent。具备用户认证、长期记忆、多会话隔离、RAG 知识库检索、自主工具调用（Function Calling）、流式输出，并附带 **React 聊天界面**。

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![DeepSeek](https://img.shields.io/badge/DeepSeek-API-orange.svg)](https://deepseek.com/)
[![React](https://img.shields.io/badge/React-19+-61DAFB.svg)](https://react.dev/)

---

## ✨ 功能特性

- 🔐 **用户认证**：注册 / 登录 / 登出，基于 SQLite + token 校验，多会话归属管理
- 💬 **多会话隔离**：每个用户拥有独立的会话列表，对话历史互不干扰
- 🤖 **Agent 架构**：模块化设计（Agent / Tools / Memory / Knowledge / LLM 适配层 解耦）
- 🔧 **Function Calling 自主决策**：DeepSeek 动态决定调用哪个工具、提取哪些参数
- 🧩 **装饰器工具注册**：`@registry.register()` 一行注册，自动生成 JSON Schema
- 🧮 **安全数学计算**：AST 白名单求值器，替代危险的 `eval()`
- 🧠 **双层记忆**：SQLite 持久化对话历史 + Chroma 向量记忆（语义检索补上下文）
- 📚 **RAG 知识库**：上传文档（PDF/TXT/MD）→ 切片 → 向量化 → 检索 → 生成答案
- 🌐 **多模型切换**：内置 DeepSeek，可切换智谱 GLM / 通义千问 / 零一万物（OpenAI 兼容）
- ⚡ **流式输出**：`/chat/stream` 基于 SSE 的打字机效果
- 🌐 **RESTful API**：FastAPI 提供完整接口，Swagger 交互文档（`/docs`）
- 🎨 **React 前端**：Vite + TypeScript + Tailwind CSS 聊天界面
- 📝 **结构化日志**：基于标准 logging，控制台彩色输出
- 🐳 **容器化就绪**：Dockerfile 一键部署

---

## 🗂️ 项目结构

```
智能个人助手/
├── api.py                      # FastAPI 服务入口（聊天 / 认证 / 知识库 / 用户接口）
├── app.py                      # 终端交互入口（CLI）
├── config.py                   # 全局配置：环境变量加载 + LLM 提供商配置
├── requirements.txt            # Python 依赖
├── Dockerfile                  # 容器化配置
├── render.yaml / vercel.json   # 部署配置
│
├── agent/
│   ├── agent.py                # Agent 调度器：消息管理 + 多轮 tool-calling + 记忆集成
│   └── __init__.py
│
├── chatbot/
│   └── chatbot.py              # LLM 适配层：BaseLLM 抽象 + DeepSeek/OpenAI 兼容适配器
│
├── tools/
│   ├── __init__.py             # ToolRegistry + @registry.register() 装饰器（自动生成 Schema）
│   ├── calculator.py           # 安全数学计算（AST 白名单）
│   ├── weather.py              # 天气查询（wttr.in）
│   ├── hotlist.py              # 今日热榜（GitHub 趋势 / 微博热搜 / 百度热搜）
│   ├── web_search.py          # 联网搜索（DuckDuckGo，无需 API Key）
│   └── rag_tool.py             # 知识库检索工具（接入 Agent 的 tool registry）
│
├── memory/
│   ├── memory.py               # SQLite 持久化（对话 / 用户 / token / 会话 四张表）
│   └── vector_memory.py        # Chroma 向量记忆：对话历史语义检索
│
├── knowledge/
│   ├── config.py               # 切片 / 检索 / Embedding / 向量库 配置
│   ├── loader.py               # 文档加载（TXT / MD / PDF，递归目录）
│   ├── chunker.py              # 文本切片（RecursiveCharacterTextSplitter）
│   ├── embeddings.py           # Embedding：Chroma 内置 / DeepSeek API 可切换
│   ├── vector_store.py         # 向量存储（LangChain + Chroma 封装）
│   ├── retriever.py            # 检索器（语义检索 + 上下文格式化）
│   └── pipeline.py             # RAG 主流程：index_documents() / query()
│
├── auth/
│   └── __init__.py             # 认证封装：注册 / 登录 / token 校验（基于 memory 层）
│
├── utils/
│   └── logger.py               # 日志模块（标准 logging + 彩色控制台）
│
├── tests/
│   ├── test_calculator.py      # 安全计算器测试（含注入防护）
│   └── test_tools.py           # 工具注册测试
│
└── frontend/                   # React 聊天界面
    ├── vite.config.ts          # Vite 配置（Tailwind + API 代理到 8000）
    ├── src/
    │   ├── App.tsx             # 聊天主界面（含认证 / 多会话）
    │   ├── index.css           # Tailwind 入口
    │   └── main.tsx            # React 入口
    └── package.json
```

---

## 🛠️ 技术栈

| 层 | 技术 |
|----|------|
| 后端框架 | Python 3.11+ + FastAPI + Uvicorn |
| 大模型 | DeepSeek API（OpenAI 兼容 SDK），可切换 GLM / Qwen / Yi |
| 向量检索 | ChromaDB |
| RAG 框架 | LangChain（langchain / langchain-community / langchain-chroma） |
| 持久化 | SQLite（对话/用户/会话） |
| 数据校验 | Pydantic |
| 前端框架 | React 19 + TypeScript |
| 构建工具 | Vite 8 |
| 样式 | Tailwind CSS 4 |
| 容器化 | Docker |

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

# 创建 .env 文件，填入你的 API Key
echo DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxx > .env
```

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

浏览器打开 http://localhost:5173 即可开始对话（Vite 已配置代理，将 `/chat`、`/auth`、`/knowledge`、`/user` 转发到后端 8000）。

### 4. 测试

```bash
# 在项目根目录运行
pytest
```

---

## 🔐 环境变量

在 `.env` 中配置（都有合理默认值，最少只需填 `DEEPSEEK_API_KEY`）：

```ini
# ── 主模型（DeepSeek）──
DEEPSEEK_API_KEY=sk-xxx
# DEEPSEEK_BASE_URL=https://api.deepseek.com
# DEEPSEEK_MODEL=deepseek-chat

# ── 切换 LLM 提供商 ──
# LLM_PROVIDER=deepseek          # deepseek | openai_compatible

# ── 通用 OpenAI 兼容（GLM / Qwen / Yi 等）──
# OPENAI_API_KEY=sk-xxx
# OPENAI_BASE_URL=https://...
# OPENAI_MODEL_NAME=xxx

# ── 知识库 / RAG ──
# KNOWLEDGE_DOCS_DIR=knowledge/docs
# KNOWLEDGE_CHUNK_SIZE=500
# KNOWLEDGE_CHUNK_OVERLAP=50
# KNOWLEDGE_RETRIEVE_TOP_K=3
# KNOWLEDGE_EMBEDDING=default     # default(Chroma 内置) | deepseek
```

默认 Embedding 使用 ChromaDB 内置的 `all-MiniLM-L6-v2`（无需额外 Key）；如将 `KNOWLEDGE_EMBEDDING=deepseek` 且配置了 `DEEPSEEK_API_KEY`，则改用 DeepSeek Embedding API。

---

## 🔌 API 一览

所有接口前缀即路径本身，文档见 `/docs`。

### 通用 / 健康检查
- `GET /` — 服务状态

### 认证
- `POST /auth/register` — 注册，返回 `token` 与 `session_id`
- `POST /auth/login` — 登录，返回 `token` 与 `session_id`
- `POST /auth/logout` — 登出（吊销 token，需 Bearer）

### 用户中心（需 Bearer）
- `GET /user/profile` — 获取当前用户信息
- `PUT /user/profile` — 修改显示名称
- `PUT /user/password` — 修改密码
- `GET /user/sessions` — 获取用户的会话列表
- `POST /user/sessions` — 创建新会话
- `GET /user/sessions/{session_id}/messages?limit=200` — 获取指定会话的历史消息（已验证归属，防越权）
- `DELETE /user/sessions/{session_id}` — 删除会话（验证归属，防越权）

### 聊天（需 Bearer）
- `POST /chat` — 非流式对话，body：`{ message, session_id, model_provider }`
- `POST /chat/stream` — 流式对话（SSE），返回 `data: {...}` 事件流

`model_provider` 取值：`deepseek`（默认）| `glm` | `qwen` | `yi`。

### 知识库（需 Bearer）
- `POST /knowledge/upload` — 上传文档（PDF/TXT/MD）
- `POST /knowledge/index` — 索引 `knowledge/docs/` 下所有文档到向量库
- `POST /knowledge/query` — 基于知识库生成回答

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

## 🧰 现有工具（Agent 自主调用）

| 工具 | 触发场景 | 调用示例 |
|------|---------|---------|
| `calculate` | 数学运算 | "计算 12345 × 678" |
| `get_weather` | 查询天气 | "今天郑州天气怎么样" |
| `get_hotlist` | 今日热榜 | "看看 GitHub 趋势" / "百度热搜" / "微博热搜" |
| `web_search` | 联网搜索最新资讯 / 新闻 / 网页 | "帮我搜一下最新的 AI 芯片新闻" |
| `knowledge_search` | 知识库内容 | "我们项目的部署流程是什么" |

### 加一个新工具

```python
from tools import registry

@registry.register(description="查询新闻")
def get_news(topic: str) -> str:
    """获取指定主题的最新新闻"""
    return f"{topic} 的最新新闻..."
```

装饰器自动解析参数类型、生成 Schema、注册到全局注册表。若工具需要接入 RAG，参考 `tools/rag_tool.py` 从 `knowledge.pipeline` 调用 `query()` 即可。

---

## 📚 知识库使用流程

1. 把文档放进 `knowledge/docs/`（支持 `.txt` / `.md` / `.pdf`）
2. 调用 `POST /knowledge/index` 完成切片与向量化（也可通过 `POST /knowledge/upload` 先上传）
3. 用户的提问若命中知识库，Agent 会自动调用 `knowledge_search` 生成基于文档的答案；也可直接调用 `POST /knowledge/query`

---

## 🐳 Docker 部署

```bash
docker build -t smart-personal-assistant .
docker run -p 8000:8000 smart-personal-assistant
```

也可参考项目根目录的 `render.yaml`（Render）与 `vercel.json`（Vercel）做平台部署。

---

## 🧪 测试

```bash
pytest
```

覆盖安全计算器（含 `__import__` / `open` / `eval` 注入防护）与工具注册逻辑。

---

## 📄 License

MIT License © 2026
