"""全局配置：环境变量加载 + LLM 提供商配置"""

import os

from dotenv import load_dotenv

load_dotenv()


# ========== LLM 提供商配置 ==========
# 可选值: deepseek | openai_compatible
# deepseek: 使用 DeepSeek 官方 API（默认，免费有额度）
# openai_compatible: 兼容 OpenAI SDK 的第三方模型（智谱/千问/零一等）
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")

# DeepSeek 配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# 通用 OpenAI 兼容配置（保留向后兼容，LLM_PROVIDER=openai_compatible 时可用）
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")
OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "")

# ========== 第三方模型独立配置（前端切换器用，各厂商各自的 key）==========
# 智谱 GLM
GLM_API_KEY = os.getenv("GLM_API_KEY", "")
GLM_BASE_URL = os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")
GLM_MODEL = os.getenv("GLM_MODEL", "glm-4-flash")

# 通义千问
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-turbo")

# 零一万物 Yi
YI_API_KEY = os.getenv("YI_API_KEY", "")
YI_BASE_URL = os.getenv("YI_BASE_URL", "https://api.lingyiwanwu.com/v1")
YI_MODEL = os.getenv("YI_MODEL", "yi-lightning")

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
