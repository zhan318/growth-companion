"""LLM 适配器：支持多模型动态切换（同步 + 异步双通道）"""

from abc import ABC, abstractmethod

from openai import AsyncOpenAI, OpenAI

from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    GLM_API_KEY,
    GLM_BASE_URL,
    GLM_MODEL,
    QWEN_API_KEY,
    QWEN_BASE_URL,
    QWEN_MODEL,
)
from utils.logger import get_logger

logger = get_logger(__name__)


class BaseLLM(ABC):
    """LLM 基类：统一 chat 接口（同步 + 异步）"""

    @abstractmethod
    def chat(self, messages, tools=None, tool_choice="auto"):
        ...

    @abstractmethod
    def chat_stream(self, messages, tools=None, tool_choice="auto"):
        """流式调用（同步），返回迭代器"""
        ...

    @abstractmethod
    async def achat(self, messages, tools=None, tool_choice="auto"):
        """异步调用（AsyncOpenAI），不阻塞事件循环"""
        ...

    @abstractmethod
    async def achat_stream(self, messages, tools=None, tool_choice="auto"):
        """异步流式调用，返回异步迭代器"""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """模型显示名称（前端展示用）"""
        ...


class DeepSeekAdapter(BaseLLM):
    """DeepSeek 官方 API（同步 + 异步双客户端）"""

    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        self.client = OpenAI(api_key=api_key or DEEPSEEK_API_KEY, base_url=base_url or DEEPSEEK_BASE_URL)
        self.aclient = AsyncOpenAI(api_key=api_key or DEEPSEEK_API_KEY, base_url=base_url or DEEPSEEK_BASE_URL)
        self.model = model or DEEPSEEK_MODEL

    @property
    def display_name(self) -> str:
        return "DeepSeek"

    def chat(self, messages, tools=None, tool_choice="auto"):
        kwargs = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        return self.client.chat.completions.create(**kwargs)

    def chat_stream(self, messages, tools=None, tool_choice="auto"):
        kwargs = {"model": self.model, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        return self.client.chat.completions.create(**kwargs)

    async def achat(self, messages, tools=None, tool_choice="auto"):
        kwargs = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        return await self.aclient.chat.completions.create(**kwargs)

    async def achat_stream(self, messages, tools=None, tool_choice="auto"):
        kwargs = {"model": self.model, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        return await self.aclient.chat.completions.create(**kwargs)


class OpenAICompatibleAdapter(BaseLLM):
    """通用 OpenAI 兼容适配器（同步 + 异步双客户端）"""

    def __init__(self, model_name: str, api_key: str, base_url: str, label: str = ""):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.aclient = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model_name
        self._label = label or model_name

    @property
    def display_name(self) -> str:
        return self._label

    def chat(self, messages, tools=None, tool_choice="auto"):
        kwargs = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        return self.client.chat.completions.create(**kwargs)

    def chat_stream(self, messages, tools=None, tool_choice="auto"):
        kwargs = {"model": self.model, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        return self.client.chat.completions.create(**kwargs)

    async def achat(self, messages, tools=None, tool_choice="auto"):
        kwargs = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        return await self.aclient.chat.completions.create(**kwargs)

    async def achat_stream(self, messages, tools=None, tool_choice="auto"):
        kwargs = {"model": self.model, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        return await self.aclient.chat.completions.create(**kwargs)


# ===== 预设模型列表 =====
# 键名供前端传参用；每个厂商各自独立的 key / base_url / model（均来自 config，可用 .env 覆盖）
# default_base_url / default_model：用户级 key 未填 base_url/model 时的回退默认值
MODEL_PRESETS = {
    "deepseek": {
        "factory": lambda: DeepSeekAdapter(),
        "label": "DeepSeek",
        "role": "通用助手",
        "api_key": DEEPSEEK_API_KEY,
        "default_base_url": DEEPSEEK_BASE_URL,
        "default_model": DEEPSEEK_MODEL,
    },
    "glm": {
        "factory": lambda: OpenAICompatibleAdapter(
            model_name=GLM_MODEL,
            api_key=GLM_API_KEY,
            base_url=GLM_BASE_URL,
            label="智谱 GLM",
        ),
        "label": "智谱 GLM",
        "role": "创意写作",
        "api_key": GLM_API_KEY,
        "default_base_url": GLM_BASE_URL,
        "default_model": GLM_MODEL,
    },
    "qwen": {
        "factory": lambda: OpenAICompatibleAdapter(
            model_name=QWEN_MODEL,
            api_key=QWEN_API_KEY,
            base_url=QWEN_BASE_URL,
            label="通义千问",
        ),
        "label": "通义千问",
        "role": "逻辑分析",
        "api_key": QWEN_API_KEY,
        "default_base_url": QWEN_BASE_URL,
        "default_model": QWEN_MODEL,
    },
}


def get_available_models() -> list[dict]:
    """返回模型列表（前端展示用），并标注每个模型是否已配置 key（available）"""
    result = []
    for key, preset in MODEL_PRESETS.items():
        result.append({
            "id": key,
            "label": preset["label"],
            "role": preset["role"],
            "available": bool(preset.get("api_key")),  # 是否已配置 key
        })
    return result


def create_llm(provider: str = "deepseek", user_key: dict = None) -> BaseLLM:
    """根据 provider 创建对应的 LLM 适配器。

    user_key 非空（dict: {api_key, base_url?, model?}）时优先用用户级密钥覆盖，
    实现「前端每个用户填自己的 key」，base_url/model 缺省回退该厂商默认。
    """
    provider = (provider or "deepseek").lower().strip()

    preset = MODEL_PRESETS.get(provider)
    if preset is None:
        logger.warning("不支持的模型: %s，回退到 deepseek", provider)
        provider = "deepseek"
        preset = MODEL_PRESETS[provider]

    # ── 用户级 key 优先 ──
    if user_key and user_key.get("api_key"):
        api_key = user_key["api_key"]
        base_url = user_key.get("base_url") or preset["default_base_url"]
        model = user_key.get("model") or preset["default_model"]
        if provider == "deepseek":
            llm = DeepSeekAdapter(api_key=api_key, base_url=base_url, model=model)
        else:
            llm = OpenAICompatibleAdapter(
                model_name=model, api_key=api_key, base_url=base_url, label=preset["label"]
            )
        logger.info("LLM(用户级key): %s (%s)", preset["label"], provider)
        return llm

    # ── 全局 config key ── 未配置对应厂商 key 时，回退到 deepseek，避免用空 key 调用直接报错
    if not preset.get("api_key"):
        logger.warning("模型 %s 未配置 API Key（全局与用户级均无），回退到 deepseek", provider)
        provider = "deepseek"
        preset = MODEL_PRESETS[provider]

    llm = preset["factory"]()
    logger.info("LLM: %s (%s)", preset["label"], provider)
    return llm


def chat(messages, tools=None, tool_choice="auto", provider: str = "deepseek", user_key: dict = None):
    """对外接口（同步）：支持每次请求指定模型与用户级 key"""
    llm = create_llm(provider, user_key)
    return llm.chat(messages, tools, tool_choice)


def chat_stream(messages, tools=None, tool_choice="auto", provider: str = "deepseek", user_key: dict = None):
    """对外接口（同步流式）"""
    llm = create_llm(provider, user_key)
    return llm.chat_stream(messages, tools, tool_choice)


async def achat(messages, tools=None, tool_choice="auto", provider: str = "deepseek", user_key: dict = None):
    """对外接口（异步）：Agent.arun 使用，不阻塞事件循环"""
    llm = create_llm(provider, user_key)
    return await llm.achat(messages, tools, tool_choice)


async def achat_stream(messages, tools=None, tool_choice="auto", provider: str = "deepseek", user_key: dict = None):
    """对外接口（异步流式）"""
    llm = create_llm(provider, user_key)
    return await llm.achat_stream(messages, tools, tool_choice)
