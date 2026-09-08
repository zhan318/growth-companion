import asyncio
import json

from chatbot.chatbot import achat, achat_stream, chat, chat_stream
from memory.memory import Memory
from memory.vector_memory import get_vector_memory
from tools import registry
from utils.logger import get_logger

logger = get_logger(__name__)

MAX_TOOL_ROUNDS = 5
RECENT_HISTORY_LIMIT = 5
VECTOR_MEMORY_K = 3


# 系统提示词（不变部分，每次 Agent 初始化拼接 vault 元数据）
_BASE_SYSTEM_PROMPT = (
    "你是「成长智伴」— 你对用户的 Obsidian 笔记库中的内容了如指掌。\n"
    "你的首要职责：当用户问及任何可能与他的个人笔记、学习记录、项目文档、读书摘抄相关的问题时，"
    "必须先调用 search_obsidian_notes 检索笔记，再基于检索结果回答。\n"
    "\n"
    "【路由规则（严格遵循）】\n"
    "1. 涉及个人/学习/工作/笔记内容 → 必须先调 search_obsidian_notes"
    "（包括但不限于：学习方法、读书笔记、项目经验、面试题、编程笔记、外语学习、个人规划等）\n"
    "2. 用户要求查看某篇具体笔记原文 → 调 read_obsidian_note\n"
    "3. 用户要求创建/写/记录新笔记 → write_obsidian_note\n"
    "   （包括但不限于：帮我写一篇笔记、记录到知识库、新建笔记、保存这段内容等）\n"
    "4. 模拟面试/面试练习/考考我 → mock_interview\n"
    "   （从疑难总结中出题，可指定主题如 Python、并发、RAG 等；调用后逐题向用户提问）\n"
    "5. 知识库文档（上传的 PDF/TXT/MD 等非 Obsidian 资料） → knowledge_search\n"
    "6. 需要最新互联网信息/新闻/网页 → web_search\n"
    "7. 数学计算 → calculator\n"
    "8. 天气查询 → get_weather（需要城市名）\n"
    "9. AI热榜/热搜 → get_hotlist（GitHub 仅搜 AI/大模型/机器学习相关 TOP 5）\n"
    "10. 纯粹的寒暄、问候、闲聊 → 直接回答，不需要调工具\n"
    "\n"
    "【Obsidian 笔记检索是最高优先级】\n"
    "- 宁可多搜一次，不要遗漏。不确定是否该搜时，搜。\n"
    "- 检索结果相关但不完全匹配时：如实展示笔记内容，说明差异，让用户判断是否有用。\n"
    "- 检索结果确实无关时：明确告知「你的笔记库中暂未找到相关内容」，不要编造。\n"
    "- 你绝不能用通用常识替代笔记内容来回答关于用户个人事务的问题。\n"
    "\n"
    "【回答风格】\n"
    "- 简洁、直接、像朋友聊天。\n"
    "- 如果引用了笔记内容，自然提及（如「你的《xxx》笔记里提到……」），让用户感受到你确实认识他的笔记。\n"
    "- 不要机械地列出所有功能，只在需要时调用对应工具。\n"
    "- 用中文回答。"
)

# 面试模式追加的引导（用户进入模拟面试时注入）
_INTERVIEW_GUIDE = (
    "【你现在处于模拟面试模式，扮演面试官】\n"
    "用户进入这个页面就是要被面试，不是来聊别的。\n"
    "无论用户输入什么（主题、词、句子、字母），第一步必须立即调用 mock_interview 工具开始出题。\n"
    "\n"
    "禁止行为：\n"
    "- 禁止检索知识库（search_obsidian_notes / read_obsidian_note）\n"
    "- 禁止反问用户想往哪个方向走\n"
    "- 禁止先寒暄、确认主题、答疑\n"
    "- 禁止直接回答用户问的知识本身\n"
    "\n"
    "只做一件事：调 mock_interview 出第一题。出题后等用户回答，给简短点评，再出下一题。\n"
    "用中文出题。"
)


def _build_system_prompt() -> str:
    """构建完整 system prompt：基础提示词 + vault 元数据（让 Agent 知道笔记库有什么）"""
    try:
        from knowledge.pipeline import get_vault_metadata
        meta = get_vault_metadata()
    except Exception:
        meta = {"configured": False, "note_count": 0}

    parts = [_BASE_SYSTEM_PROMPT]

    if meta.get("configured"):
        parts.append("\n【你的 Obsidian 笔记库概况】")
        parts.append("笔记总数：{} 篇".format(meta.get("note_count", 0)))
        folders = meta.get("folders", [])
        if folders:
            parts.append("文件夹：{}".format("、".join(folders)))
        recent = meta.get("recent_notes", [])
        if recent:
            parts.append("最近修改的笔记：")
            for r in recent:
                parts.append("  · {}（{}）".format(r["name"], r["folder"]))
        parts.append("（以上为笔记库概况，供你了解有哪些话题可查。具体内容请调用 search_obsidian_notes 检索。）")
    else:
        parts.append("\n【注意】Obsidian 笔记库尚未配置。"
                      "如果用户问到个人笔记相关内容，请告知用户需要先在 .env 中设置 OBSIDIAN_VAULT_DIR。")

    # 动态注入已注册的 MCP 工具引导（若连接了外部 MCP server）
    mcp_guide = _build_mcp_guide()
    if mcp_guide:
        parts.append(mcp_guide)

    return "\n".join(parts)


def _build_mcp_guide() -> str:
    """检测 registry 中 mcp_ 前缀的工具，生成 MCP 工具使用引导。"""
    try:
        mcp_names = [n for n in registry.tools if n.startswith("mcp_")]
    except Exception:
        mcp_names = []
    if not mcp_names:
        return ""
    lines = [
        "\n【已连接的外部 MCP 工具（优先使用）】",
        "你当前可通过 MCP 协议调用以下外部工具（以 mcp_ 开头）：",
    ]
    for n in sorted(mcp_names):
        lines.append("  · " + n)
    lines.append(
        "当用户要求操作文件系统、读写目录、抓取网页等操作时，"
        "优先调用这些 mcp_ 开头的工具，而不是用别的工具替代或直接说做不到。"
    )
    return "\n".join(lines)


class Agent:

    def __init__(self, session_id: str = "default_session"):
        self.name = "MyAgent"
        self.session_id = session_id
        self.memory = Memory()
        self.vector_memory = get_vector_memory()

        self.messages = [{"role": "system", "content": _build_system_prompt()}]

        # 数据库写队列（攒批落库，减少写放大）
        self._pending_db_writes: list[tuple[str, str]] = []

        # 面试模式状态：跟踪当前题号 + 是否第一轮 + 面试主题（后续出题都用这个）
        self._interview_index: int = 0
        self._interview_first: bool = True
        self._interview_topic: str = ""

        # ── 加载历史：最近 N 条 + 向量检索相关历史 ──
        recent = self.memory.load_history(session_id, limit=RECENT_HISTORY_LIMIT)
        self.messages.extend(recent)
        logger.info("已加载最近 %d 条历史", len(recent))

        logger.info("Agent 初始化完成, session=%s", session_id)

    # ── 消息管理 ──

    def _init_db_queue(self):
        """初始化本会话的数据库写队列（批量落库，减少写放大）。"""
        self._pending_db_writes: list[tuple[str, str]] = []

    def add_user_message(self, content):
        self.messages.append({"role": "user", "content": content})
        self._pending_db_writes.append(("user", content))

    def add_assistant_message(self, content):
        self.messages.append({"role": "assistant", "content": content})
        self._pending_db_writes.append(("assistant", content))

    def add_tool_messages(self, tool_name, result):
        truncated = str(result)[:500] + ("..." if len(str(result)) > 500 else "")
        self._pending_db_writes.append(("assistant", f"[{tool_name}] {truncated}"))

    def flush_messages(self):
        """把本轮攒批的消息一次性写入数据库（单事务）。

        在 run/arun 结束时调用。相比逐条 save_message，
        一轮对话 N 条消息从 N 次 commit 降为 1 次，高并发下显著减少 SQLite 写锁竞争。
        """
        if not getattr(self, "_pending_db_writes", None):
            return
        try:
            self.memory.save_messages_batch(self.session_id, self._pending_db_writes)
        except Exception as e:
            logger.error("批量保存消息失败: %s", e)
        finally:
            self._pending_db_writes = []

    # ── 核心执行 ──

    def _execute_tool(self, tool_call) -> str:
        tool_name = tool_call.function.name
        try:
            tool_args = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            logger.warning("工具参数解析失败: %s", tool_call.function.arguments)
            return "工具参数解析失败"

        logger.info("执行工具: %s, 参数=%s", tool_name, tool_args)

        tool_func = registry.tools.get(tool_name)
        if tool_func is None:
            logger.warning("未知工具: %s", tool_name)
            return f"工具 {tool_name} 不存在"

        try:
            result = tool_func(**tool_args)
            logger.info("工具 %s 返回成功", tool_name)
            return str(result)
        except Exception as e:
            logger.error("工具 %s 执行失败: %s", tool_name, e)
            return f"工具执行失败: {str(e)}"

    async def _aexecute_tool(self, tool_call) -> str:
        """异步执行工具（Agent.arun 使用）。

        优先调用 registry 中的 async 版本（httpx.AsyncClient，真正异步）；
        若无 async 版（如纯计算/本地读文件工具），用 asyncio.to_thread 放入线程池，
        避免同步阻塞事件循环。
        """
        tool_name = tool_call.function.name
        try:
            tool_args = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            logger.warning("工具参数解析失败: %s", tool_call.function.arguments)
            return "工具参数解析失败"

        logger.info("执行工具(异步): %s, 参数=%s", tool_name, tool_args)

        async_tool = registry.async_tools.get(tool_name)
        sync_tool = registry.tools.get(tool_name)
        if async_tool is None and sync_tool is None:
            logger.warning("未知工具: %s", tool_name)
            return f"工具 {tool_name} 不存在"

        try:
            if async_tool is not None:
                result = await async_tool(**tool_args)
            else:
                result = await asyncio.to_thread(sync_tool, **tool_args)
            logger.info("工具 %s 返回成功", tool_name)
            return str(result)
        except Exception as e:
            logger.error("工具 %s 执行失败: %s", tool_name, e)
            return f"工具执行失败: {str(e)}"

    def _load_context(self, model_provider: str = "deepseek", user_key: dict | None = None,
                      mode: str = "workspace"):
        """重建基础上下文：system prompt + 会话摘要 + 最近原始历史。

        每次 run 从干净状态开始，避免 messages 无限膨胀；
        同时在此触发「上下文压缩」——若会话消息数超过阈值，把旧对话压成摘要。
        """
        system_msg = self.messages[0]  # 第一条始终是 system prompt
        self.messages = [system_msg]

        # 面试模式：紧跟主 prompt 注入面试官引导
        if mode == "interview":
            self.messages.append({"role": "system", "content": _INTERVIEW_GUIDE})
            logger.info("面试模式：已注入面试官引导")

        # 1. 触发上下文压缩（消息数超阈值时，静默失败不阻塞）
        try:
            from memory.summarizer import compress_if_needed
            compress_if_needed(self.session_id, self.memory, model_provider, user_key)
        except Exception as e:
            logger.warning("上下文压缩失败: %s", e)

        # 2. 注入会话摘要（若有）
        try:
            summary = self.memory.get_session_summary(self.session_id)
            if summary and summary.get("summary"):
                self.messages.append({
                    "role": "system",
                    "content": "【以下是你们之前对话的摘要，帮助你了解上下文】\n" + summary["summary"],
                })
        except Exception as e:
            logger.warning("加载会话摘要失败: %s", e)

        # 3. 最近原始历史
        recent = self.memory.load_history(self.session_id, limit=RECENT_HISTORY_LIMIT)
        self.messages.extend(recent)

    def run(self, message, model_provider: str = "deepseek", user_id: int = None,
            mode: str = "workspace"):
        # 若有 user_id，优先取该用户为该模型配置的密钥（用户级 key 覆盖全局配置）
        user_key = self.memory.get_user_llm_key(user_id, model_provider) if user_id else None
        user_key = user_key if (user_key and user_key.get("api_key")) else None
        # ── 重建基础上下文：system + 摘要 + 最近历史（含触发压缩）──
        self._load_context(model_provider, user_key, mode=mode)

        logger.info("用户输入: %s", message)
        self.add_user_message(message)

        try:
            return self._run_impl(message, model_provider, user_key, mode)
        finally:
            # 本轮消息统一落库（单事务，减少写放大）
            self.flush_messages()

    def _run_impl(self, message, model_provider, user_key, mode):
        """run() 的实际逻辑体（由 run 包裹 flush）"""

        # ── 面试模式：第一轮直接出题（跳过 LLM 自由回答，保证一题一答）──
        if mode == "interview" and self._interview_first:
            self._interview_first = False
            mock_result = registry.tools.get("mock_interview")(message, self._interview_index)
            self._interview_index += 1
            answer = (
                f"好，我们开始「{message}」的模拟面试。我会一题一题出，你答完发「下一题」我就点评并出下一题。\n\n"
                f"{mock_result}"
            )
            self.add_assistant_message(answer)
            logger.info("面试模式首轮：直接出题（index=%d）", self._interview_index - 1)
            return answer

        # 面试模式：插入强信号 system 消息，把用户输入明确标记为面试主题
        if mode == "interview":
            self.messages.append({
                "role": "system",
                "content": (
                    f"用户当前输入的是「{message}」。按规则，"
                    "你必须立即调用 mock_interview 工具对这一主题出第一题，"
                    "不要再反问用户、不要检索知识库、不要寒暄。"
                ),
            })

        # ── 向量检索相关历史记忆（面试模式跳过，避免历史对话干扰出题）──
        if mode == "interview":
            logger.info("面试模式：跳过向量记忆检索")
        else:
            try:
                related = self.vector_memory.search(
                    message, session_id=self.session_id, k=VECTOR_MEMORY_K,
                )
                if related:
                    context_lines = ["以下是你与用户的相关历史对话（供参考）："]
                    for i, item in enumerate(related, 1):
                        context_lines.append("---\n[历史对话 {}]\n{}".format(i, item["content"]))
                    self.messages.append({
                        "role": "system",
                        "content": "\n".join(context_lines),
                    })
                    logger.info("向量记忆检索到 %d 条相关历史", len(related))
            except Exception as e:
                logger.warning("向量记忆检索失败: %s", e)

        # ── ReAct 多轮循环（Reasoning → Action → Observation）──
        # Reasoning：LLM 基于当前上下文推理并决定是否调用工具
        # Action：执行 LLM 选择的工具
        # Observation：把工具结果作为新观察追加回 messages，进入下一轮推理
        for round_num in range(MAX_TOOL_ROUNDS):
            response = chat(
                self.messages,
                tools=registry.schemas,
                tool_choice="auto",
                provider=model_provider,
                user_key=user_key,
            )
            choice = response.choices[0]
            finish_reason = choice.finish_reason

            if finish_reason != "tool_calls":
                answer = choice.message.content
                # 面试模式：LLM 点评（用户答题的回答）后，Agent 自动调 mock_interview 出下一题
                # 这样保证"一题一答"节奏，不依赖 LLM 记得调工具
                if mode == "interview":
                    mock_result = registry.tools.get("mock_interview")(self._interview_topic, self._interview_index)
                    self._interview_index += 1
                    answer = f"{answer}\n---\n{mock_result}"
                    logger.info("面试模式：点评后出下一题（index=%d, topic=%s）", self._interview_index - 1, self._interview_topic)
                self.add_assistant_message(answer)
                logger.info("回答（第%d轮）: %s", round_num + 1, answer[:100])

                # ── 将本轮回合存入向量记忆 ──
                try:
                    self.vector_memory.add_turn(self.session_id, message, answer)
                except Exception as e:
                    logger.warning("向量记忆写入失败: %s", e)

                return answer

            # ── 执行工具调用 ──
            tool_calls = choice.message.tool_calls
            logger.info(
                "第%d轮工具调用, 数量=%d, 工具=%s",
                round_num + 1,
                len(tool_calls),
                [tc.function.name for tc in tool_calls],
            )
            self.messages.append(choice.message.model_dump())

            for tool_call in tool_calls:
                result = self._execute_tool(tool_call)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })
                self.add_tool_messages(tool_call.function.name, result)

        # 超过最大轮数
        logger.warning("达到最大工具调用轮数 %d", MAX_TOOL_ROUNDS)
        final_response = chat(
            self.messages,
            tools=registry.schemas,
            tool_choice="none",
            provider=model_provider,
            user_key=user_key,
        )
        final_answer = final_response.choices[0].message.content
        self.add_assistant_message(final_answer)
        return final_answer

    async def arun(self, message, model_provider: str = "deepseek", user_id: int = None,
                   mode: str = "workspace"):
        """异步执行（Agent 全链路异步，不阻塞事件循环）。

        与 run() 逻辑一致，但：
        - LLM 调用用 AsyncOpenAI（achat）
        - 工具执行优先 async 版，无则 to_thread
        - 上下文加载（SQLite/Chroma）用 to_thread 放入线程池
        """
        # 若有 user_id，优先取该用户为该模型配置的密钥（用户级 key 覆盖全局配置）
        user_key = self.memory.get_user_llm_key(user_id, model_provider) if user_id else None
        user_key = user_key if (user_key and user_key.get("api_key")) else None
        # ── 重建基础上下文：system + 摘要 + 最近历史（含触发压缩）──
        await asyncio.to_thread(self._load_context, model_provider, user_key, mode)

        logger.info("用户输入: %s", message)
        self.add_user_message(message)

        try:
            return await self._arun_impl(message, model_provider, user_key, mode)
        finally:
            # 本轮消息统一落库（单事务，减少写放大）
            self.flush_messages()

    async def _arun_impl(self, message, model_provider, user_key, mode):
        """arun() 的实际逻辑体（由 arun 包裹 flush）"""
        # ── 面试模式：第一轮直接出题（跳过 LLM 自由回答，保证一题一答）──
        if mode == "interview" and self._interview_first:
            self._interview_first = False
            mock_result = await asyncio.to_thread(
                registry.tools.get("mock_interview"), message, self._interview_index,
            )
            self._interview_index += 1
            answer = (
                f"好，我们开始「{message}」的模拟面试。我会一题一题出，你答完发「下一题」我就点评并出下一题。\n\n"
                f"{mock_result}"
            )
            self.add_assistant_message(answer)
            logger.info("面试模式首轮：直接出题（index=%d）", self._interview_index - 1)
            return answer

        # 面试模式：插入强信号 system 消息，把用户输入明确标记为面试主题
        if mode == "interview":
            self.messages.append({
                "role": "system",
                "content": (
                    f"用户当前输入的是「{message}」。按规则，"
                    "你必须立即调用 mock_interview 工具对这一主题出第一题，"
                    "不要再反问用户、不要检索知识库、不要寒暄。"
                ),
            })

        # ── 向量检索相关历史记忆（面试模式跳过，避免历史对话干扰出题）──
        if mode == "interview":
            logger.info("面试模式：跳过向量记忆检索")
        else:
            try:
                related = await asyncio.to_thread(
                    self.vector_memory.search, message, self.session_id, VECTOR_MEMORY_K,
                )
                if related:
                    context_lines = ["以下是你与用户的相关历史对话（供参考）："]
                    for i, item in enumerate(related, 1):
                        context_lines.append("---\n[历史对话 {}]\n{}".format(i, item["content"]))
                    self.messages.append({
                        "role": "system",
                        "content": "\n".join(context_lines),
                    })
                    logger.info("向量记忆检索到 %d 条相关历史", len(related))
            except Exception as e:
                logger.warning("向量记忆检索失败: %s", e)

        # ── ReAct 多轮循环（异步版）──
        for round_num in range(MAX_TOOL_ROUNDS):
            response = await achat(
                self.messages,
                tools=registry.schemas,
                tool_choice="auto",
                provider=model_provider,
                user_key=user_key,
            )
            choice = response.choices[0]
            finish_reason = choice.finish_reason

            if finish_reason != "tool_calls":
                answer = choice.message.content
                # 面试模式：LLM 点评后，Agent 自动调 mock_interview 出下一题
                if mode == "interview":
                    mock_result = await asyncio.to_thread(
                        registry.tools.get("mock_interview"), self._interview_topic, self._interview_index,
                    )
                    self._interview_index += 1
                    answer = f"{answer}\n---\n{mock_result}"
                    logger.info("面试模式：点评后出下一题（index=%d, topic=%s）", self._interview_index - 1, self._interview_topic)
                self.add_assistant_message(answer)
                logger.info("回答（第%d轮）: %s", round_num + 1, answer[:100])

                # ── 将本轮回合存入向量记忆（fire-and-forget：不阻塞响应返回，减少关键路径写等待）──
                try:
                    asyncio.get_running_loop().create_task(
                        asyncio.to_thread(self.vector_memory.add_turn, self.session_id, message, answer)
                    )
                except Exception as e:
                    logger.warning("向量记忆写入失败: %s", e)

                return answer

            # ── 执行工具调用（异步）──
            tool_calls = choice.message.tool_calls
            logger.info(
                "第%d轮工具调用, 数量=%d, 工具=%s",
                round_num + 1,
                len(tool_calls),
                [tc.function.name for tc in tool_calls],
            )
            self.messages.append(choice.message.model_dump())

            for tool_call in tool_calls:
                result = await self._aexecute_tool(tool_call)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })
                self.add_tool_messages(tool_call.function.name, result)

        # 超过最大轮数
        logger.warning("达到最大工具调用轮数 %d", MAX_TOOL_ROUNDS)
        final_response = await achat(
            self.messages,
            tools=registry.schemas,
            tool_choice="none",
            provider=model_provider,
            user_key=user_key,
        )
        final_answer = final_response.choices[0].message.content
        self.add_assistant_message(final_answer)
        return final_answer

    def run_stream(self, message, model_provider: str = "deepseek", user_id: int = None,
                   mode: str = "workspace"):
        """流式执行：tool calling 阶段非流式，最终回答流式输出。

        Yields:
            dict: {"type": "token", "content": str} | {"type": "done", "content": str}
        """
        # 若有 user_id，优先取该用户为该模型配置的密钥（用户级 key 覆盖全局配置）
        user_key = self.memory.get_user_llm_key(user_id, model_provider) if user_id else None
        user_key = user_key if (user_key and user_key.get("api_key")) else None
        # ── 重建基础上下文：system + 摘要 + 最近历史（含触发压缩）──
        self._load_context(model_provider, user_key, mode=mode)

        logger.info("用户输入: %s", message)
        self.add_user_message(message)

        # 外层包装：生成器耗尽或关闭时统一 flush（确保消息落库）
        try:
            yield from self._run_stream_impl(message, model_provider, user_key, mode)
        finally:
            self.flush_messages()

    def _run_stream_impl(self, message, model_provider, user_key, mode):
        """run_stream() 的实际生成器（由 run_stream 包裹 flush）"""

        # 面试模式：插入强信号 system 消息，把用户输入明确标记为面试主题
        if mode == "interview":
            self.messages.append({
                "role": "system",
                "content": (
                    f"用户当前输入的是「{message}」。按规则，"
                    "你必须立即调用 mock_interview 工具对这一主题出第一题，"
                    "不要再反问用户、不要检索知识库、不要寒暄。"
                ),
            })

        # ── 向量检索相关历史记忆 ──
        try:
            related = self.vector_memory.search(
                message, session_id=self.session_id, k=VECTOR_MEMORY_K,
            )
            if related:
                context_lines = ["以下是你与用户的相关历史对话（供参考）："]
                for i, item in enumerate(related, 1):
                    context_lines.append(
                        "---\n[历史对话 {}]\n{}".format(i, item["content"])
                    )
                self.messages.append({
                    "role": "system",
                    "content": "\n".join(context_lines),
                })
                logger.info("向量记忆检索到 %d 条相关历史", len(related))
        except Exception as e:
            logger.warning("向量记忆检索失败: %s", e)

        # ── 面试模式首轮：跳过 LLM 循环，直接出题（一题一答的核心）──
        if mode == "interview" and self._interview_first:
            self._interview_first = False
            self._interview_topic = message  # 保存主题，后续轮都按这个出题
            mock_result = registry.tools.get("mock_interview")(self._interview_topic, self._interview_index)
            self._interview_index += 1
            collected = (
                f"好，我们开始「{message}」的模拟面试。我会一题一题出，你答完发「下一题」我就点评并出下一题。\n\n"
                f"{mock_result}"
            )
            self.add_assistant_message(collected)
            logger.info("面试模式首轮：直接出题（index=%d）", self._interview_index - 1)
            yield {"type": "token", "content": collected}
            yield {"type": "done", "content": collected}
            return

        # ── ReAct 多轮循环（工具调用阶段非流式，最终回答流式）──
        for round_num in range(MAX_TOOL_ROUNDS):
            response = chat(
                self.messages,
                tools=registry.schemas,
                tool_choice="auto",
                provider=model_provider,
                user_key=user_key,
            )
            choice = response.choices[0]
            finish_reason = choice.finish_reason

            if finish_reason != "tool_calls":
                # ── 最终回答：流式输出 ──
                try:
                    stream = chat_stream(
                        self.messages,
                        tools=registry.schemas,
                        tool_choice="none",
                        provider=model_provider,
                        user_key=user_key,
                    )
                    for chunk in stream:
                        delta = chunk.choices[0].delta.content or ""
                        if delta:
                            collected += delta
                            yield {"type": "token", "content": delta}
                except Exception as e:
                    logger.error("流式调用失败: %s", e)
                    # fallback: 非流式重试
                    try:
                        fallback = chat(
                            self.messages,
                            tools=registry.schemas,
                            tool_choice="none",
                            provider=model_provider,
                            user_key=user_key,
                        )
                        collected = fallback.choices[0].message.content or ""
                        if collected:
                            yield {"type": "token", "content": collected}
                    except Exception as e2:
                        logger.error("非流式回退也失败: %s", e2)
                        collected = f"（抱歉，处理您的问题时出错了：{e2}）"
                        yield {"type": "token", "content": collected}

                # 面试模式：LLM 点评后，Agent 自动调 mock_interview 出下一题（保证一题一答）
                # 注意：传原主题 self._interview_topic，不是用户当前输入
                if mode == "interview":
                    mock_result = registry.tools.get("mock_interview")(self._interview_topic, self._interview_index)
                    self._interview_index += 1
                    next_block = f"\n---\n{mock_result}"
                    collected += next_block
                    yield {"type": "token", "content": next_block}
                    logger.info("面试模式：点评后出下一题（index=%d, topic=%s）", self._interview_index - 1, self._interview_topic)

                # 如果流式没有返回任何内容，用非流式兜底
                if not collected:
                    try:
                        fallback = chat(
                            self.messages,
                            tools=registry.schemas,
                            tool_choice="none",
                            provider=model_provider,
                            user_key=user_key,
                        )
                        collected = fallback.choices[0].message.content or ""
                    except Exception as e2:
                        collected = f"（抱歉，处理您的问题时出错了：{e2}）"
                    if collected:
                        yield {"type": "token", "content": collected}

                self.add_assistant_message(collected)
                logger.info("回答完成（第%d轮）, 共 %d 字符", round_num + 1, len(collected))

                # ── 存入向量记忆 ──
                try:
                    self.vector_memory.add_turn(self.session_id, message, collected)
                except Exception as e:
                    logger.warning("向量记忆写入失败: %s", e)

                yield {"type": "done", "content": collected}
                return

            # ── 工具调用 ──
            tool_calls = choice.message.tool_calls
            logger.info(
                "第%d轮工具调用, 数量=%d, 工具=%s",
                round_num + 1,
                len(tool_calls),
                [tc.function.name for tc in tool_calls],
            )
            self.messages.append(choice.message.model_dump())

            for tool_call in tool_calls:
                result = self._execute_tool(tool_call)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })
                self.add_tool_messages(tool_call.function.name, result)

        # 超过最大轮数，非流式兜底
        logger.warning("达到最大工具调用轮数 %d", MAX_TOOL_ROUNDS)
        final_response = chat(
            self.messages,
            tools=registry.schemas,
            tool_choice="none",
            provider=model_provider,
            user_key=user_key,
        )
        final_answer = final_response.choices[0].message.content
        self.add_assistant_message(final_answer)
        yield {"type": "done", "content": final_answer}

    async def arun_stream(self, message, model_provider: str = "deepseek", user_id: int = None,
                          mode: str = "workspace"):
        """异步流式执行（Agent 全链路异步，不阻塞事件循环）。

        与 run_stream() 逻辑一致，但：
        - LLM 调用用 AsyncOpenAI（achat / achat_stream）
        - 工具执行优先 async 版，无则 to_thread
        - 上下文加载 / 向量记忆用 to_thread 放入线程池

        Yields:
            dict: {"type": "token", "content": str} | {"type": "done", "content": str}
        """
        # 若有 user_id，优先取该用户为该模型配置的密钥（用户级 key 覆盖全局配置）
        user_key = self.memory.get_user_llm_key(user_id, model_provider) if user_id else None
        user_key = user_key if (user_key and user_key.get("api_key")) else None
        # ── 重建基础上下文：system + 摘要 + 最近历史（含触发压缩）──
        await asyncio.to_thread(self._load_context, model_provider, user_key, mode)

        logger.info("用户输入: %s", message)
        self.add_user_message(message)

        # 外层包装：异步生成器耗尽或关闭时统一 flush（确保消息落库）
        try:
            async for event in self._arun_stream_impl(message, model_provider, user_key, mode):
                yield event
        finally:
            self.flush_messages()

    async def _arun_stream_impl(self, message, model_provider, user_key, mode):
        """arun_stream() 的实际异步生成器（由 arun_stream 包裹 flush）"""
        # 面试模式：插入强信号 system 消息，把用户输入明确标记为面试主题
        if mode == "interview":
            self.messages.append({
                "role": "system",
                "content": (
                    f"用户当前输入的是「{message}」。按规则，"
                    "你必须立即调用 mock_interview 工具对这一主题出第一题，"
                    "不要再反问用户、不要检索知识库、不要寒暄。"
                ),
            })

        # ── 向量检索相关历史记忆 ──
        try:
            related = await asyncio.to_thread(
                self.vector_memory.search, message, self.session_id, VECTOR_MEMORY_K,
            )
            if related:
                context_lines = ["以下是你与用户的相关历史对话（供参考）："]
                for i, item in enumerate(related, 1):
                    context_lines.append(
                        "---\n[历史对话 {}]\n{}".format(i, item["content"])
                    )
                self.messages.append({
                    "role": "system",
                    "content": "\n".join(context_lines),
                })
                logger.info("向量记忆检索到 %d 条相关历史", len(related))
        except Exception as e:
            logger.warning("向量记忆检索失败: %s", e)

        # ── 面试模式首轮：跳过 LLM 循环，直接出题（一题一答的核心）──
        if mode == "interview" and self._interview_first:
            self._interview_first = False
            self._interview_topic = message  # 保存主题，后续轮都按这个出题
            mock_result = await asyncio.to_thread(
                registry.tools.get("mock_interview"), self._interview_topic, self._interview_index,
            )
            self._interview_index += 1
            collected = (
                f"好，我们开始「{message}」的模拟面试。我会一题一题出，你答完发「下一题」我就点评并出下一题。\n\n"
                f"{mock_result}"
            )
            self.add_assistant_message(collected)
            logger.info("面试模式首轮：直接出题（index=%d）", self._interview_index - 1)
            yield {"type": "token", "content": collected}
            yield {"type": "done", "content": collected}
            return

        # ── ReAct 多轮循环（工具调用阶段非流式，最终回答流式）──
        for round_num in range(MAX_TOOL_ROUNDS):
            response = await achat(
                self.messages,
                tools=registry.schemas,
                tool_choice="auto",
                provider=model_provider,
                user_key=user_key,
            )
            choice = response.choices[0]
            finish_reason = choice.finish_reason

            if finish_reason != "tool_calls":
                # ── 最终回答：流式输出 ──
                collected = ""
                try:
                    stream = await achat_stream(
                        self.messages,
                        tools=registry.schemas,
                        tool_choice="none",
                        provider=model_provider,
                        user_key=user_key,
                    )
                    async for chunk in stream:
                        delta = chunk.choices[0].delta.content or ""
                        if delta:
                            collected += delta
                            yield {"type": "token", "content": delta}
                except Exception as e:
                    logger.error("流式调用失败: %s", e)
                    # fallback: 非流式重试
                    try:
                        fallback = await achat(
                            self.messages,
                            tools=registry.schemas,
                            tool_choice="none",
                            provider=model_provider,
                            user_key=user_key,
                        )
                        collected = fallback.choices[0].message.content or ""
                        if collected:
                            yield {"type": "token", "content": collected}
                    except Exception as e2:
                        logger.error("非流式回退也失败: %s", e2)
                        collected = f"（抱歉，处理您的问题时出错了：{e2}）"
                        yield {"type": "token", "content": collected}

                # 面试模式：LLM 点评后，Agent 自动调 mock_interview 出下一题（保证一题一答）
                if mode == "interview":
                    mock_result = await asyncio.to_thread(
                        registry.tools.get("mock_interview"), self._interview_topic, self._interview_index,
                    )
                    self._interview_index += 1
                    next_block = f"\n---\n{mock_result}"
                    collected += next_block
                    yield {"type": "token", "content": next_block}
                    logger.info("面试模式：点评后出下一题（index=%d, topic=%s）", self._interview_index - 1, self._interview_topic)

                # 如果流式没有返回任何内容，用非流式兜底
                if not collected:
                    try:
                        fallback = await achat(
                            self.messages,
                            tools=registry.schemas,
                            tool_choice="none",
                            provider=model_provider,
                            user_key=user_key,
                        )
                        collected = fallback.choices[0].message.content or ""
                    except Exception as e2:
                        collected = f"（抱歉，处理您的问题时出错了：{e2}）"
                    if collected:
                        yield {"type": "token", "content": collected}

                self.add_assistant_message(collected)
                logger.info("回答完成（第%d轮）, 共 %d 字符", round_num + 1, len(collected))

                # ── 存入向量记忆（fire-and-forget：不阻塞流式响应收尾）──
                try:
                    asyncio.get_running_loop().create_task(
                        asyncio.to_thread(self.vector_memory.add_turn, self.session_id, message, collected)
                    )
                except Exception as e:
                    logger.warning("向量记忆写入失败: %s", e)

                yield {"type": "done", "content": collected}
                return

            # ── 工具调用（异步）──
            tool_calls = choice.message.tool_calls
            logger.info(
                "第%d轮工具调用, 数量=%d, 工具=%s",
                round_num + 1,
                len(tool_calls),
                [tc.function.name for tc in tool_calls],
            )
            self.messages.append(choice.message.model_dump())

            for tool_call in tool_calls:
                result = await self._aexecute_tool(tool_call)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })
                self.add_tool_messages(tool_call.function.name, result)

        # 超过最大轮数，非流式兜底
        logger.warning("达到最大工具调用轮数 %d", MAX_TOOL_ROUNDS)
        final_response = await achat(
            self.messages,
            tools=registry.schemas,
            tool_choice="none",
            provider=model_provider,
            user_key=user_key,
        )
        final_answer = final_response.choices[0].message.content
        self.add_assistant_message(final_answer)
        yield {"type": "done", "content": final_answer}

    def clear_memory(self):
        self.memory.clear_session(self.session_id)
        self.vector_memory.clear_session(self.session_id)
        self.messages = [{"role": "system", "content": _build_system_prompt()}]
        logger.info("记忆已清除, session=%s", self.session_id)
