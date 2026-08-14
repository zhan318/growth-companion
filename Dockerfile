# ═══════════════════════════════════════════
#  阶段 1：构建前端（React + Vite）
# ═══════════════════════════════════════════
FROM node:22-alpine AS frontend-builder
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --silent
COPY frontend/ ./
RUN npm run build
# 产物：/frontend/dist/

# ═══════════════════════════════════════════
#  阶段 2：运行时镜像（Python 后端 + 前端静态文件）
# ═══════════════════════════════════════════
FROM python:3.11-slim

WORKDIR /app

# 系统依赖（chromadb 需要 C++ 运行时）
RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 后端代码
COPY . .

# 前端构建产物
COPY --from=frontend-builder /frontend/dist/ ./frontend/dist/

# 挂载数据卷（知识库文档、SQLite、Chroma 持久化）
VOLUME ["/app/knowledge/docs", "/app/memory", "/app/knowledge/chroma_db"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
