# ═══════════════════════════════════════════
#  阶段 1：构建前端（React + Vite）
# ═══════════════════════════════════════════
FROM node:22-alpine AS frontend-builder
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
# 用国内镜像源：容器默认 registry.npmjs.org 在构建时走代理常被拦，本机 npm 同为 npmmirror
RUN npm ci --silent --registry=https://registry.npmmirror.com/
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
# 先装 CPU 版 torch：sentence-transformers 默认拉 CUDA 版（约 1GB+ 的 CUDA toolkit / cuDNN），
# 纯 CPU 容器完全用不上且镜像暴涨。先装 CPU torch 让依赖满足，后续不会再装 CUDA 版。
COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

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
