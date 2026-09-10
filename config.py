"""全局配置：环境变量加载 + LLM 提供商配置"""

import os

from dotenv import load_dotenv

load_dotenv()


# ========== LLM 提供商配置 ==========
# 全项目默认 provider（唯一配置源）：
#   聊天主链路 / RAG 知识库问答 / 评测脚本 / 前端默认选中项 全部读这里，
#   换默认模型只改 .env 一行即可，不需要再改任何代码。
# 可选值: deepseek | glm | qwen
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "glm").strip().lower()
# 兜底 provider：LLM_PROVIDER 非法、或对应厂商未配置 API Key 时回退到此值
FALLBACK_LLM_PROVIDER = os.getenv("FALLBACK_LLM_PROVIDER", "deepseek").strip().lower()

# ========== 深度思考（思维链）开关 ==========
# 默认关闭：日常对话更快更省 token，且避免思考过程吃光 max_tokens 导致正文为空
# （实测 GLM 开启思考时，max_tokens 会被 reasoning 占满，返回 content 为空字符串）
LLM_THINKING = os.getenv("LLM_THINKING", "false").strip().lower() == "true"
# 开启思考时自动放大的输出上限：思考过程与正文共享 max_tokens，不放大极易返回空内容
LLM_THINKING_MAX_TOKENS = int(os.getenv("LLM_THINKING_MAX_TOKENS", "2048"))

# ========== 各厂商可用型号目录 ==========
# /models 接口下发给前端渲染「型号」下拉；每项: (型号ID, 说明)
# 默认型号 = 各厂商 GLM_MODEL / DEEPSEEK_MODEL / QWEN_MODEL（.env 可覆盖），不必是目录第一个
MODEL_CATALOG = {
    "glm": [
        ("glm-4.5-air", "轻量通用 · 对话/RAG 主力"),
        ("glm-4.1v-thinking-flashx", "视觉推理 · 支持看图（图传功能上线后用）"),
        ("glm-4.6", "旗舰文本 · 复杂推理/长文"),
        ("glm-5.3-flash", "新一代 · 高速"),
    ],
    "deepseek": [
        ("deepseek-v4-flash", "通用 · 快速"),
        ("deepseek-chat", "通用对话"),
    ],
    "qwen": [
        ("qwen-turbo", "通用 · 快速"),
    ],
}

# DeepSeek 配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

# 通用 OpenAI 兼容配置（保留向后兼容，LLM_PROVIDER=openai_compatible 时可用）
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")
OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "")

# ========== 第三方模型独立配置（前端切换器用，各厂商各自的 key）==========
# 智谱 GLM
GLM_API_KEY = os.getenv("GLM_API_KEY", "")
GLM_BASE_URL = os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")
GLM_MODEL = os.getenv("GLM_MODEL", "glm-4.5-air")

# 通义千问
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-turbo")

# ========== GitHub OAuth2.0 ==========
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
# 回调地址（本地开发默认 http://127.0.0.1:8000/auth/github/callback）
GITHUB_REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI", "http://127.0.0.1:8000/auth/github/callback")

# ========== Obsidian 知识库（用户个人笔记，独立 collection）==========
# vault 本地文件夹路径（含 .obsidian 目录即为有效 vault）
OBSIDIAN_VAULT_DIR = os.getenv("OBSIDIAN_VAULT_DIR", "")
# 独立向量集合名，与 knowledge/docs 隔离，避免知识库问答串味
OBSIDIAN_COLLECTION = os.getenv("OBSIDIAN_COLLECTION", "obsidian")
# 排除清单：这些文件/文件夹永不被索引或读取（隐私保护，如存放 API Key 的文件）
# 支持：文件名（API.md）、相对路径（secret/api.md）、文件夹名（.trash）
OBSIDIAN_EXCLUDE = [
    p.strip() for p in os.getenv("OBSIDIAN_EXCLUDE", "API.md").split(",") if p.strip()
]

# ========== Obsidian 实时文件监视器 ==========
# 是否启用自动重索引（vault 未配置时自动跳过）。设为 false 可关闭
OBSIDIAN_WATCHER_ENABLED = os.getenv("OBSIDIAN_WATCHER_ENABLED", "true").lower() != "false"
# 防抖/轮询间隔（秒）：watchdog 下为「变更后多久才重索引」的合并窗口；
# 轮询回退模式下为「每隔多少秒扫描一次」。默认 5 秒
OBSIDIAN_WATCH_INTERVAL = int(os.getenv("OBSIDIAN_WATCH_INTERVAL", "5"))
