# -*- coding: utf-8 -*-
"""端到端 Agent 评测（e2e）：路由准确率 + 响应耗时 + 答案质量（LLM-as-a-Judge）

评测对象：Agent.run() 完整链路 —— 上下文组装 → ReAct 工具循环 → LLM 生成。
进程内直调（不起 HTTP 服务）；工具调用序列通过捕获 agent logger 获取，不改项目代码。

与 eval_retrieval / eval_generation 的分工：
  eval_retrieval  测「检索层准不准」（代码算，零成本）
  eval_generation 测「RAG 生成层答得好不好」（旁路固定 RAG 链路）
  eval_e2e        测「Agent 该调的工具调了没有 + 真链路耗时 + 答案质量」

数据源：
  eval/golden_set.jsonl  —— RAG 类 25 条（含 not_in_kb 防幻觉项）
  eval/e2e_cases.jsonl   —— 工具路由 / 笔记读写 / 闲聊类

用法（项目根目录）：
    .venv/Scripts/python eval/eval_e2e.py [--limit N] [--only rag|tool|chat|...]
输出：
    eval/reports/e2e-report.md
    eval/reports/e2e-answers.jsonl（全量存档，供人工抽检）

注意：真实调用 LLM（Agent 主链路 + Judge），会产生 API 费用。
每条用例独立 session（e2e_case_N），跑完自动清理向量记忆与测试笔记。
"""

import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

AGENT_LOGGER = "agent.agent"
SESSION_PREFIX = "e2e_case"
# write_note 用例的 Agent 实际写入位置不固定（模型可能写到 vault 根目录或指定子目录），清理时两处都查
TEST_NOTE_CANDIDATES = ["e2e-测试笔记.md", "AI学习/e2e-测试笔记.md"]

# ── 工具调用捕获：agent logger 里有「执行工具: <name>, 参数=...」记录 ──
class ToolCallCapture(logging.Handler):
    _PATS = [re.compile(r"执行工具(?:\(异步\))?: (\S+),")]

    def __init__(self):
        super().__init__()
        self.calls = []

    def emit(self, record):
        msg = record.getMessage()
        for p in self._PATS:
            m = p.search(msg)
            if m:
                self.calls.append(m.group(1))


def load_cases(only: str | None, limit: int) -> list[dict]:
    """golden 集 → RAG 类；e2e_cases.jsonl → 功能类。合并后按 --only / --limit 过滤。"""
    cases = []
    golden = ROOT / "eval" / "golden_set.jsonl"
    for line in golden.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        it = json.loads(line)
        oob = it["category"] == "not_in_kb"
        cases.append({
            "question": it["question"],
            "expected_tools": ["search_obsidian_notes"],
            "category": "rag_oob" if oob else "rag",
            "expect_refusal": oob,
            "note": "golden: " + it["category"],
            "source": "golden",
        })
    e2e = ROOT / "eval" / "e2e_cases.jsonl"
    for line in e2e.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        it = json.loads(line)
        cases.append({
            "question": it["question"],
            "expected_tools": it["expected_tools"],
            "category": it["category"],
            "expect_refusal": False,
            "note": it.get("note", ""),
            "source": "e2e",
        })
    if only:
        cases = [c for c in cases if c["category"] == only]
    if limit:
        cases = cases[:limit]
    return cases


def build_judge():
    """Judge 模型：跟随全项目默认 provider（与 eval_generation 同源）。"""
    from chatbot.chatbot import MODEL_PRESETS, get_default_provider
    from langchain_openai import ChatOpenAI

    provider = get_default_provider()
    preset = MODEL_PRESETS[provider]
    print(f"Judge 模型: {preset['label']} ({provider})")
    return ChatOpenAI(
        model=preset["default_model"],
        api_key=preset["api_key"],
        base_url=preset["default_base_url"],
        temperature=0,
        timeout=90,
    )


JUDGE_SYSTEM = (
    "你是 Agent 系统评测裁判。根据【问题】【回答】【工具调用记录】【预期行为】判定回答质量。\n"
    "【工具调用记录】由系统日志捕获，是事实依据——判断是否调用了工具，以它为准，"
    "不要以回答文本里有没有提到工具为准。\n"
    "verdict 只能是以下之一：\n"
    "correct：正确完成了预期行为\n"
    "partial：部分完成（答了但明显不完整或跑偏）\n"
    "wrong：答错、答非所问或编造\n"
    "refused_ok：预期为拒答，且回答诚实说明没有相关信息（不编造）\n"
    "refused_bad：应回答却拒答，或应拒答却编造\n"
    '只输出 JSON：{"verdict": "...", "reason": "一句话理由"}'
)

JUDGE_HUMAN = (
    "问题：{q}\n\n回答：\n---\n{a}\n---\n\n"
    "工具调用记录（日志捕获）：{tools}\n\n预期行为：{expect}"
)


def expect_desc(case: dict) -> str:
    cat = case["category"]
    if cat == "chat":
        return "闲聊输入，工具调用记录应为空，回答自然即可。"
    if cat == "rag":
        return "应调用 Obsidian 知识库检索工具（search_obsidian_notes），并根据检索到的笔记内容回答。"
    if cat == "rag_oob":
        return "该问题超出知识库范围，检索后应诚实说明没有相关信息，绝不允许编造；若调用联网搜索获取实时信息后如实说明结果，也算合格。"
    if cat == "read_note":
        return "应调用读取笔记工具（read_obsidian_note）返回笔记原文内容。"
    if cat == "write_note":
        return "应直接生成笔记 Markdown 正文作为回复（不调用任何工具），可提醒用户用界面「存为笔记」按钮保存。"
    tools = "、".join(case["expected_tools"])
    return f"应调用工具：{tools}，并基于工具返回结果回答。"


def judge_answer(llm, case: dict, answer: str, actual_tools: list[str]) -> tuple[str, str]:
    if llm is None:
        return "skip", "judge 未加载"
    tools_str = "、".join(actual_tools) if actual_tools else "（无工具调用）"
    prompt = JUDGE_HUMAN.format(q=case["question"], a=answer[:1500],
                                tools=tools_str, expect=expect_desc(case))
    try:
        resp = llm.invoke([
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": prompt},
        ])
        text = resp.content if hasattr(resp, "content") else str(resp)
    except Exception as e:
        return "judge_error", str(e)[:120]
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return "parse_error", text[:120]
    try:
        d = json.loads(m.group(0))
        return d.get("verdict", "parse_error"), d.get("reason", "")
    except json.JSONDecodeError:
        return "parse_error", text[:120]


def pct(values: list[float], q: float) -> float:
    vs = sorted(values)
    if not vs:
        return 0.0
    return vs[min(int(len(vs) * q), len(vs) - 1)]


def cleanup(idx_done: int):
    """清理向量记忆 + SQLite 会话历史 + 测试笔记。

    会话历史必须清理：Agent 初始化时会 load_history，残留历史会污染下一轮评测
    （模型会说「你问过一遍啦」直接复用旧答案，导致路由数据失真）。
    """
    try:
        from memory.memory import Memory
        mem = Memory()
        for i in range(1, idx_done + 1):
            sid = f"{SESSION_PREFIX}_{i}"
            mem.clear_session(sid)
        print(f"SQLite 会话历史已清理（{idx_done} 个）")
    except Exception as e:
        print(f"会话历史清理失败（不影响评测结果）: {e}")
    try:
        from memory.vector_memory import get_vector_memory
        vm = get_vector_memory()
        for i in range(1, idx_done + 1):
            vm.clear_session(f"{SESSION_PREFIX}_{i}")
        print("向量记忆已清理")
    except Exception as e:
        print(f"向量记忆清理失败（不影响评测结果）: {e}")
    try:
        from config import OBSIDIAN_VAULT_DIR
        if OBSIDIAN_VAULT_DIR:
            vault = Path(OBSIDIAN_VAULT_DIR)
            for rel in TEST_NOTE_CANDIDATES:
                p = vault / rel
                if p.exists():
                    p.unlink()
                    print(f"测试笔记已删除: {rel}")
    except Exception as e:
        print(f"测试笔记删除失败: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条（0=全部）")
    ap.add_argument("--only", type=str, default=None,
                    help="只跑某类：rag | rag_oob | tool | read_note | write_note | chat")
    ap.add_argument("--no-judge", action="store_true", help="跳过 Judge 判分（只测路由与耗时）")
    args = ap.parse_args()

    cases = load_cases(args.only, args.limit)
    if not cases:
        print("没有匹配的用例")
        return

    from agent.agent import Agent

    agent_logger = logging.getLogger(AGENT_LOGGER)
    judge_llm = None if args.no_judge else build_judge()

    answers_path = ROOT / "eval" / "reports" / "e2e-answers.jsonl"
    answers_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"用例总数: {len(cases)}")
    results = []
    try:
        with answers_path.open("a", encoding="utf-8") as f:
            for i, c in enumerate(cases, 1):
                print(f"[{i}/{len(cases)}] {c['category']:<10} {c['question'][:30]}...", flush=True)
                agent = Agent(session_id=f"{SESSION_PREFIX}_{i}")
                cap = ToolCallCapture()
                agent_logger.addHandler(cap)
                t0 = time.perf_counter()
                try:
                    answer = agent.run(c["question"], mode="workspace")
                except Exception as e:
                    answer = f"[运行失败] {type(e).__name__}: {e}"
                dt = time.perf_counter() - t0
                agent_logger.removeHandler(cap)

                actual = cap.calls
                if c["category"] == "chat":
                    route_hit = len(actual) == 0
                else:
                    route_hit = set(c["expected_tools"]).issubset(set(actual))

                verdict, reason = ("skip", "未判分") if args.no_judge else judge_answer(judge_llm, c, answer, actual)

                rec = {
                    "index": i,
                    "question": c["question"],
                    "category": c["category"],
                    "expected_tools": c["expected_tools"],
                    "actual_tools": actual,
                    "route_hit": route_hit,
                    "elapsed_sec": round(dt, 2),
                    "verdict": verdict,
                    "reason": reason,
                    "expect_refusal": c["expect_refusal"],
                    "source": c["source"],
                    "answer": answer,
                }
                results.append(rec)
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                flag = "OK " if (route_hit and verdict in ("correct", "refused_ok")) else "!! "
                print(f"    {flag}route={'HIT' if route_hit else 'MISS'} "
                      f"tools={actual or '[]'} {dt:.1f}s verdict={verdict}")
    finally:
        cleanup(len(cases))

    # ── 汇总 ──
    n = len(results)
    print(f"\n===== 汇总（{n} 条）=====")
    from collections import defaultdict
    by_cat = defaultdict(lambda: [0, 0])
    for r in results:
        by_cat[r["category"]][0] += 1 if r["route_hit"] else 0
        by_cat[r["category"]][1] += 1
    total_hit = sum(1 for r in results if r["route_hit"])
    print(f"路由总命中率: {total_hit}/{n} = {total_hit / n:.1%}")
    for cat, (h, t) in sorted(by_cat.items()):
        print(f"  {cat:<10} {h}/{t} = {h / t:.1%}")

    scored = [r for r in results if r["verdict"] not in ("skip",)]
    if scored:
        good = sum(1 for r in scored if r["verdict"] in ("correct", "refused_ok"))
        partial = sum(1 for r in scored if r["verdict"] == "partial")
        print(f"答案质量: correct={good} partial={partial} 其他={len(scored) - good - partial}"
              f"（综合得分 {((good + 0.5 * partial) / len(scored)):.1%}）")

    times = [r["elapsed_sec"] for r in results if r["elapsed_sec"] > 0]
    if times:
        print(f"耗时: 平均 {sum(times) / len(times):.1f}s | p50 {pct(times, 0.5):.1f}s | p95 {pct(times, 0.95):.1f}s")

    # ── 写报告 ──
    report = ROOT / "eval" / "reports" / "e2e-report.md"
    lines = [
        "# Agent 端到端评测报告（e2e）",
        "",
        f"> 生成时间：{time.strftime('%Y-%m-%d %H:%M')}",
        f"> 用例：{n} 条（golden RAG {sum(1 for r in results if r['source'] == 'golden')} 条"
        f" + 功能 {sum(1 for r in results if r['source'] == 'e2e')} 条）| Judge：跟随默认 provider",
        "> 链路：Agent.run() 进程内直调（上下文组装 → ReAct 工具循环 → 生成）",
        "",
        "## 路由准确率（按类别）",
        "",
        "| 类别 | 命中/总数 | 准确率 |",
        "|---|---|---|",
    ]
    for cat, (h, t) in sorted(by_cat.items()):
        lines.append(f"| {cat} | {h}/{t} | {h / t:.1%} |")
    lines += [
        f"| **总命中率** | **{total_hit}/{n}** | **{total_hit / n:.1%}** |",
        "",
        "## 答案质量（LLM-as-a-Judge）",
        "",
    ]
    if scored:
        lines += [
            f"- correct：{good} | partial：{partial} | wrong：{sum(1 for r in scored if r['verdict'] == 'wrong')}"
            f" | refused_ok：{sum(1 for r in scored if r['verdict'] == 'refused_ok')}"
            f" | refused_bad：{sum(1 for r in scored if r['verdict'] == 'refused_bad')}",
            f"- 综合得分：{(good + 0.5 * partial) / len(scored):.1%}",
        ]
    else:
        lines.append("- 本次未启用 Judge（--no-judge）")
    if times:
        lines += [
            "",
            "## 响应耗时（进程内，不含 HTTP 层）",
            "",
            f"- 平均 {sum(times) / len(times):.1f}s | p50 {pct(times, 0.5):.1f}s | p95 {pct(times, 0.95):.1f}s",
            "- 注意：含 LLM 网络延迟与工具外呼（天气/热搜/搜索走真实 API）",
        ]
    lines += ["", "## 逐条明细", "", "| # | 类别 | 预期工具 | 实际调用 | 路由 | 耗时s | verdict |", "|---|---|---|---|---|---|---|"]
    for r in results:
        lines.append(
            f"| {r['index']} | {r['category']} | {','.join(r['expected_tools']) or '（无）'} "
            f"| {','.join(r['actual_tools']) or '（无）'} | {'HIT' if r['route_hit'] else 'MISS'} "
            f"| {r['elapsed_sec']} | {r['verdict']} |"
        )
    misses = [r for r in results if not r["route_hit"]]
    if misses:
        lines += ["", "## 路由失败案例", ""]
        for r in misses:
            lines += [
                f"**Q: {r['question']}**（{r['category']}）",
                f"- 预期: {r['expected_tools'] or '不调工具'}；实际: {r['actual_tools'] or '未调用'}",
                f"- 答案摘要: {r['answer'][:100]}",
                "",
            ]
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告已写入: {report}")
    print(f"答案存档: {answers_path}")


if __name__ == "__main__":
    main()
