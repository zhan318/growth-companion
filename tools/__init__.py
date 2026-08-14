"""
工具注册模块
=========
通过 @registry.register() 装饰器自动注册工具函数并生成 JSON Schema。
避免手动维护 tool_schemas.py 和 registry.py 的重复工作。

用法:
    from tools import registry

    @registry.register(description="查询天气")
    def get_weather(city: str) -> str:
        ...

然后在外层使用:
    registry.tools    -> {"get_weather": <函数>}
    registry.schemas  -> [{"type": "function", "function": {...}}, ...]
"""

import inspect
from collections.abc import Callable
from typing import get_type_hints

# Python 类型 → JSON Schema 类型映射
_TYPE_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _infer_type(annotation) -> str:
    """从类型注解推断 JSON Schema type。"""
    if annotation is inspect.Parameter.empty:
        return "string"
    # 处理 Optional[str] → str
    origin = getattr(annotation, "__origin__", None)
    if origin is type(int | None):  # UnionType
        args = getattr(annotation, "__args__", ())
        real = [a for a in args if a is not type(None)]
        if real:
            return _TYPE_MAP.get(real[0], "string")
    return _TYPE_MAP.get(annotation, "string")


class ToolRegistry:
    """工具注册表：维护名称→函数映射 及 OpenAI function-calling schema。

    支持同步与异步两种注册：
    - register()        注册同步工具（Agent.run 同步路径使用）
    - register_async()  注册异步工具（Agent.arun 异步路径使用，并发不阻塞事件循环）
    两种注册共享同一份 schema（LLM 看到的能力描述不变）。
    """

    def __init__(self):
        self._tools: dict[str, Callable] = {}
        self._async_tools: dict[str, Callable] = {}
        self._schemas: list[dict] = []

    def _build_schema(self, func: Callable, tool_name: str, tool_desc: str) -> dict:
        """从函数签名生成 OpenAI function-calling schema（同步/异步共用）"""
        sig = inspect.signature(func)
        hints = get_type_hints(func) if hasattr(func, "__annotations__") else {}
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            # 排除 self / cls
            if param_name in ("self", "cls"):
                continue

            ann = hints.get(param_name, param.annotation)
            param_type = _infer_type(ann)

            prop = {
                "type": param_type,
                "description": f"参数 {param_name}",
            }

            # 有默认值 → 非 required，且可提供默认值提示
            if param.default is not inspect.Parameter.empty:
                if param.default is not None:
                    prop["default"] = param.default
            else:
                required.append(param_name)

            properties[param_name] = prop

        schema = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": tool_desc,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                },
            },
        }
        if required:
            schema["function"]["parameters"]["required"] = required
        return schema

    def register(
        self,
        name: str | None = None,
        description: str = "",
    ) -> Callable:
        """装饰器：注册一个同步工具函数。

        Args:
            name: 工具名称（默认使用函数名）
            description: 工具描述（默认使用函数 docstring）

        装饰器会自动从函数签名推断 JSON Schema。
        """
        def decorator(func: Callable) -> Callable:
            tool_name = name or func.__name__
            tool_desc = description or (func.__doc__ or "").strip()

            schema = self._build_schema(func, tool_name, tool_desc)
            self._tools[tool_name] = func
            self._schemas.append(schema)
            return func

        return decorator

    def register_async(
        self,
        name: str | None = None,
        description: str = "",
    ) -> Callable:
        """装饰器：注册一个异步工具函数（async def，供 Agent.arun 使用）。

        与 register() 共享 schema：LLM 可见的工具名与同步版一致，
        async 实现只是同一工具的异步执行版本，不额外暴露给 LLM。

        命名约定：异步函数名以 `_async` 结尾（如 `get_weather_async`），
        注册名自动去掉 `_async` 后缀（→ `get_weather`），与同步版同名复用 schema。
        """
        def decorator(func: Callable) -> Callable:
            tool_name = (name or func.__name__)
            # 去掉 _async 后缀，与同步版同名
            if tool_name.endswith("_async"):
                tool_name = tool_name[:-6]
            tool_desc = description or (func.__doc__ or "").strip()

            schema = self._build_schema(func, tool_name, tool_desc)
            # 若该名字的 schema 已存在（同步版注册过），不重复追加
            if not any(s["function"]["name"] == tool_name for s in self._schemas):
                self._schemas.append(schema)
            self._async_tools[tool_name] = func
            return func

        return decorator

    def register_manual(self, name: str, description: str,
                        parameters: dict, func: Callable) -> None:
        """手动注册一个工具（用于 MCP 等自带 JSON Schema 的外部工具）。

        Args:
            name: 工具名
            description: 工具描述
            parameters: OpenAI function 的 parameters（含 type/properties）
            func: 可调用对象
        """
        self._tools[name] = func
        self._schemas.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        })

    @property
    def tools(self) -> dict[str, Callable]:
        """工具名称 → 可调用对象（同步版）"""
        return dict(self._tools)

    @property
    def async_tools(self) -> dict[str, Callable]:
        """工具名称 → 异步可调用对象（async def，Agent.arun 使用）"""
        return dict(self._async_tools)

    @property
    def schemas(self) -> list[dict]:
        """OpenAI function-calling schema 列表"""
        return list(self._schemas)


# 全局注册表实例
registry = ToolRegistry()

# 导入工具模块（导入时执行装饰器，自动注册）
# 以下 import 均为副作用导入：触发 @registry.register() 装饰器，不直接使用名称
import knowledge  # noqa: E402, F401

from . import (  # noqa: E402
    calculator,  # noqa: E402, F401
    hotlist,  # noqa: E402, F401
    mock_interview,  # noqa: E402, F401
    obsidian,  # noqa: E402, F401
    rag_tool,  # noqa: E402, F401
    weather,  # noqa: E402, F401
    web_search,  # noqa: E402, F401
)
