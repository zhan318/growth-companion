"""LLM 适配器：支持多模型动态切换（同步 + 异步双通道）"""

import re
from abc import ABC, abstractmethod

from openai import AsyncOpenAI, OpenAI

from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    FALLBACK_LLM_PROVIDER,
    GLM_API_KEY,
    GLM_BASE_URL,
    GLM_MODEL,
    LLM_PROVIDER,
    LLM_THINKING,
    LLM_THINKING_MAX_TOKENS,
    QWEN_API_KEY,
    QWEN_BASE_URL,
    QWEN_MODEL,
)
from utils.logger import get_logger

logger = get_logger(__name__)


# ═══════════════════════════════════════════
#  <think> 思考过程清洗
#  部分模型（如 glm-4.1v-thinking 系列）把思考过程以 <think>...</think>
#  混在正文 content 里返回（而不是像 GLM-4.5 那样放独立 reasoning_content 字段），
#  直接展示会把整段思考暴露给用户，需要在展示层之前剥掉。
# ═══════════════════════════════════════════

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_think(text: str) -> str:
    """非流式清洗：剥掉正文中完整的 <think>...</think> 段"""
    if not text:
        return text
    return _THINK_RE.sub("", text).lstrip()


class ThinkFilter:
    """流式清洗：状态机过滤 <think>...</think>，标签可能被 chunk 边界切开也能正确处理。

    对不含 <think> 的模型输出是直通的（仅极小的缓冲开销）。
    用法：每收到一段 delta 调 feed(delta)，取返回值展示；流结束后调 flush() 清空缓冲。
    """

    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self):
        self._in_think = False
        self._buf = ""

    def feed(self, text: str) -> str:
        self._buf += text
        out = []
        while self._buf:
            if self._in_think:
                idx = self._buf.find(self.CLOSE)
                if idx >= 0:
                    self._in_think = False
                    self._buf = self._buf[idx + len(self.CLOSE):]
                else:
                    # 只保留可能是 CLOSE 前缀的尾巴，其余都是思考内容，直接丢弃
                    keep = self._partial_suffix(self._buf, self.CLOSE)
                    self._buf = self._buf[len(self._buf) - keep:] if keep else ""
                    break
            else:
                idx = self._buf.find(self.OPEN)
                if idx >= 0:
                    out.append(self._buf[:idx])
                    self._in_think = True
                    self._buf = self._buf[idx + len(self.OPEN):]
                else:
                    # 末尾若是 OPEN 的前缀（标签被切开），先扣住不发
                    keep = self._partial_suffix(self._buf, self.OPEN)
                    emit = len(self._buf) - keep
                    if emit > 0:
                        out.append(self._buf[:emit])
                        self._buf = self._buf[emit:]
                    break
        return "".join(out)

    def flush(self) -> str:
        """流结束：缓冲里剩下的都是正常内容（不在思考态时）"""
        tail = "" if self._in_think else self._buf
        self._buf = ""
        return tail

    @staticmethod
    def _partial_suffix(buf: str, tag: str) -> int:
        """buf 尾部有多少字符恰好是 tag 的前缀（防止标签被切开后误放出半截标签）"""
        for k in range(min(len(buf), len(tag) - 1), 0, -1):
            if buf.endswith(tag[:k]):
                return k
        return 0


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

    # ── 深度思考（思维链）开关 ──
    # None = 不传参（沿用模型自身默认）；True/False = 显式开启/关闭
    thinking = None
    # 厂商特定的参数构造函数（由 MODEL_PRESETS 注入），None = 该厂商不支持
    _thinking_param = None

    def set_thinking(self, enabled: bool = None, thinking_param=None):
        """设置思考模式；thinking_param 为厂商特定的参数构造函数"""
        self.thinking = enabled
        self._thinking_param = thinking_param
        return self

    def _apply_thinking(self, kwargs: dict) -> dict:
        """把思考模式写入请求参数，并处理 max_tokens 联动。

        开启思考时必须放大 max_tokens：思考过程与正文共享输出额度，
        实测 GLM 在默认额度下会把正文挤成空字符串。
        """
        if self.thinking is None or self._thinking_param is None:
            return kwargs
        extra = self._thinking_param(self.thinking)
        if extra:
            kwargs["extra_body"] = {**kwargs.get("extra_body", {}), **extra}
        if self.thinking and "max_tokens" not in kwargs:
            kwargs["max_tokens"] = LLM_THINKING_MAX_TOKENS
        return kwargs


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
        return self.client.chat.completions.create(**self._apply_thinking(kwargs))

    def chat_stream(self, messages, tools=None, tool_choice="auto"):
        kwargs = {"model": self.model, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        return self.client.chat.completions.create(**self._apply_thinking(kwargs))

    async def achat(self, messages, tools=None, tool_choice="auto"):
        kwargs = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        return await self.aclient.chat.completions.create(**self._apply_thinking(kwargs))

    async def achat_stream(self, messages, tools=None, tool_choice="auto"):
        kwargs = {"model": self.model, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        return await self.aclient.chat.completions.create(**self._apply_thinking(kwargs))


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
        return self.client.chat.completions.create(**self._apply_thinking(kwargs))

    def chat_stream(self, messages, tools=None, tool_choice="auto"):
        kwargs = {"model": self.model, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        return self.client.chat.completions.create(**self._apply_thinking(kwargs))

    async def achat(self, messages, tools=None, tool_choice="auto"):
        kwargs = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        return await self.aclient.chat.completions.create(**self._apply_thinking(kwargs))

    async def achat_stream(self, messages, tools=None, tool_choice="auto"):
        kwargs = {"model": self.model, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        return await self.aclient.chat.completions.create(**self._apply_thinking(kwargs))


# ===== 各厂商「深度思考」开关的参数格式 =====
# 协议不统一：GLM 用 thinking.type；DeepSeek 官方 API 无此参数（传了会被忽略，不会报错）
# 千问 dashscope 用 enable_thinking，当前未配置 key，待启用时补这一行
THINKING_PARAMS = {
    "glm": lambda on: {"thinking": {"type": "enabled" if on else "disabled"}},
}

# ===== 预设模型列表 =====
# 键名供前端传参用；每个厂商各自独立的 key / base_url / model（均来自 config，可用 .env 覆盖）
# default_base_url / default_model：用户级 key 未填 base_url/model 时的回退默认值
MODEL_PRESETS = {
    "deepseek": {
        "factory": lambda model=None: DeepSeekAdapter(model=model),
        "label": "DeepSeek",
        "role": "通用助手",
        "api_key": DEEPSEEK_API_KEY,
        "default_base_url": DEEPSEEK_BASE_URL,
        "default_model": DEEPSEEK_MODEL,
        "thinking_param": THINKING_PARAMS.get("deepseek"),
    },
    "glm": {
        "factory": lambda model=None: OpenAICompatibleAdapter(
            model_name=model or GLM_MODEL,
            api_key=GLM_API_KEY,
            base_url=GLM_BASE_URL,
            label="智谱 GLM",
        ),
        "label": "智谱 GLM",
        "role": "创意写作",
        "api_key": GLM_API_KEY,
        "default_base_url": GLM_BASE_URL,
        "default_model": GLM_MODEL,
        "thinking_param": THINKING_PARAMS.get("glm"),
    },
    "qwen": {
        "factory": lambda model=None: OpenAICompatibleAdapter(
            model_name=model or QWEN_MODEL,
            api_key=QWEN_API_KEY,
            base_url=QWEN_BASE_URL,
            label="通义千问",
        ),
        "label": "通义千问",
        "role": "逻辑分析",
        "api_key": QWEN_API_KEY,
        "default_base_url": QWEN_BASE_URL,
        "default_model": QWEN_MODEL,
        "thinking_param": THINKING_PARAMS.get("qwen"),
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


def _resolve_provider(provider: str = None) -> str:
    """归一化 provider：缺省或非法时，依次回退 LLM_PROVIDER → FALLBACK_LLM_PROVIDER → deepseek"""
    for candidate in (provider, LLM_PROVIDER, FALLBACK_LLM_PROVIDER, "deepseek"):
        p = (candidate or "").strip().lower()
        if p in MODEL_PRESETS:
            if provider and p != str(provider).strip().lower():
                logger.warning("不支持的模型: %s，回退到 %s", provider, p)
            return p
    return "deepseek"


def _provider_with_key(provider: str) -> str:
    """目标 provider 未配置全局 key 时回退到兜底 provider，避免用空 key 调用直接报错"""
    if MODEL_PRESETS.get(provider, {}).get("api_key"):
        return provider
    fallback = _resolve_provider(FALLBACK_LLM_PROVIDER)
    logger.warning("模型 %s 未配置 API Key（全局与用户级均无），回退到 %s", provider, fallback)
    return fallback


def get_default_provider() -> str:
    """返回实际会生效的默认 provider（已考虑 key 是否配置），供 /models 下发给前端"""
    return _provider_with_key(_resolve_provider(None))


def create_llm(provider: str = None, user_key: dict = None, thinking: bool = None,
               model_name: str = None) -> BaseLLM:
    """根据 provider 创建对应的 LLM 适配器。

    provider 缺省时读 config.LLM_PROVIDER（全项目唯一默认配置源，可用 .env 覆盖）。
    user_key 非空（dict: {api_key, base_url?, model?}）时优先用用户级密钥覆盖，
    实现「前端每个用户填自己的 key」，base_url/model 缺省回退该厂商默认。
    thinking 为 None 时读 config.LLM_THINKING（默认关闭）。
    model_name 为本次请求显式指定的型号，优先级最高（用户级 key 的 model 次之）。
    """
    provider = _resolve_provider(provider)
    preset = MODEL_PRESETS[provider]
    # 请求级 > 全局默认
    thinking = LLM_THINKING if thinking is None else thinking
    model_name = (model_name or "").strip() or None

    # ── 用户级 key 优先 ──
    if user_key and user_key.get("api_key"):
        api_key = user_key["api_key"]
        base_url = user_key.get("base_url") or preset["default_base_url"]
        model = model_name or user_key.get("model") or preset["default_model"]
        if provider == "deepseek":
            llm = DeepSeekAdapter(api_key=api_key, base_url=base_url, model=model)
        else:
            llm = OpenAICompatibleAdapter(
                model_name=model, api_key=api_key, base_url=base_url, label=preset["label"]
            )
        logger.info("LLM(用户级key): %s/%s (%s)", preset["label"], model, provider)
        return llm.set_thinking(thinking, preset.get("thinking_param"))

    # ── 全局 config key ── 未配置对应厂商 key 时回退兜底 provider，避免用空 key 调用直接报错
    if not preset.get("api_key"):
        provider = _provider_with_key(provider)
        preset = MODEL_PRESETS[provider]

    llm = preset["factory"](model=model_name)
    logger.info("LLM: %s/%s (%s)", preset["label"], getattr(llm, "model", None) or getattr(llm, "model_name", None), provider)
    return llm.set_thinking(thinking, preset.get("thinking_param"))


def chat(messages, tools=None, tool_choice="auto", provider: str = None, user_key: dict = None,
         thinking: bool = None, model_name: str = None):
    """对外接口（同步）：支持每次请求指定模型、用户级 key 与思考模式"""
    llm = create_llm(provider, user_key, thinking, model_name)
    return llm.chat(messages, tools, tool_choice)


def chat_stream(messages, tools=None, tool_choice="auto", provider: str = None, user_key: dict = None,
                thinking: bool = None, model_name: str = None):
    """对外接口（同步流式）"""
    llm = create_llm(provider, user_key, thinking, model_name)
    return llm.chat_stream(messages, tools, tool_choice)


async def achat(messages, tools=None, tool_choice="auto", provider: str = None, user_key: dict = None,
                thinking: bool = None, model_name: str = None):
    """对外接口（异步）：Agent.arun 使用，不阻塞事件循环"""
    llm = create_llm(provider, user_key, thinking, model_name)
    return await llm.achat(messages, tools, tool_choice)


async def achat_stream(messages, tools=None, tool_choice="auto", provider: str = None, user_key: dict = None,
                       thinking: bool = None, model_name: str = None):
    """对外接口（异步流式）"""
    llm = create_llm(provider, user_key, thinking, model_name)
    return await llm.achat_stream(messages, tools, tool_choice)
