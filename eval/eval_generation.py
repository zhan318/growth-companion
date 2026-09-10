# -*- coding: utf-8 -*-
"""生成层评测：LLM-as-a-Judge（指标对齐 RAGAS）

评测对象：Obsidian RAG 完整链路（检索 + DeepSeek 生成），
裁判：DeepSeek（更强的同一模型）按 rubric 打分。

指标（对齐 RAGAS 定义）：
- faithfulness（忠实度 0-1）：答案是否忠于检索到的上下文，有无幻觉
- answer_relevancy（0-1）：答案是否直接回应问题
- correctness（0-1）：结合 golden 答案要点判断正确/完整度
- hallucination（0-1）：幻觉比例（越高越差）
- verdict: correct / partial / wrong / refused（not_in_kb 期望 refused）

用法（在项目根目录）：
    .venv/Scripts/python eval/eval_generation.py [--limit 25] [--skip-generate]
输出：
    reports/generation-report.md + reports/answers.jsonl（人工抽检用）
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

from knowledge.pipeline import RAG_PROMPT, _format_context, retrieve_obsidian

JUDGE_SYSTEM = (
    "你是一名严格的 RAG 系统评测裁判。你会收到【问题】【检索到的上下文】【模型答案】【期望答案要点】。\n"
    "请从四个维度打分，每个维度 0 到 1（保留两位小数）：\n"
    "1. faithfulness：模型答案中的信息是否都能在上下文中找到依据。若答案包含了上下文中没有的信息（编造/幻觉），该项扣分。\n"
    "2. answer_relevancy：模型答案是否直接、完整地回应了问题，是否答非所问。\n"
    "3. correctness：结合期望答案要点，判断答案内容是否正确。\n"
    "4. hallucination：答案中编造信息（上下文无依据的断言）的比例，0=完全没有，1=大量编造。\n"
    "5. verdict：整体判定，只能是 correct / partial / wrong / refused 之一。"
    "refused 用于：知识库中确实没有相关信息、且模型如实说明没有而没有编造的情况（此时 hallucination 应为 0）。\n"
    "最后输出 JSON（不要输出其他内容）：\n"
    '{"faithfulness": 0.0, "answer_relevancy": 0.0, "correctness": 0.0, "hallucination": 0.0, "verdict": "correct", "reason": "一句话理由"}'
)

JUDGE_HUMAN = (
    "问题：{question}\n\n"
    "检索到的上下文：\n---\n{context}\n---\n\n"
    "模型答案：\n---\n{answer}\n---\n\n"
    "期望答案要点（可能为空）：\n---\n{points}\n---\n"
)


def build_llm():
    """构建评测用 judge 模型，跟随全项目默认 provider（config.LLM_PROVIDER）"""
    from chatbot.chatbot import MODEL_PRESETS, get_default_provider

    provider = get_default_provider()
    preset = MODEL_PRESETS[provider]
    print(f"评测 judge 模型: {preset['label']} ({provider})")
    return ChatOpenAI(
        model=preset["default_model"],
        api_key=preset["api_key"],
        base_url=preset["default_base_url"],
        temperature=0.2,
        timeout=90,
    )


def retrieve_context(question: str, k: int = 3) -> str:
    """与 query_obsidian 一致的检索路径（dense + BM25 → RRF），返回格式化 context"""
    _, _, docs = retrieve_obsidian(question, k)
    return _format_context(docs)


def generate(question: str, context: str) -> str:
    llm = build_llm()
    chain = RAG_PROMPT | llm | StrOutputParser()
    return chain.invoke({"context": context, "question": question})


def judge(question: str, context: str, answer: str, points: list) -> dict:
    llm = build_llm()
    resp = llm.invoke([
        {"role": "system", "content": JUDGE_SYSTEM},
        {"role": "user", "content": JUDGE_HUMAN.format(
            question=question, context=context[:4000], answer=answer, points="; ".join(points) or "（无，库外问题）"
        )},
    ])
    text = resp.content if hasattr(resp, "content") else str(resp)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {"parse_error": text[:200]}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"parse_error": text[:200]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条（0 = 全部）")
    ap.add_argument("--skip-generate", action="store_true", help="跳过生成，仅用已有 answers.jsonl 重新判分")
    args = ap.parse_args()

    golden_path = Path(__file__).resolve().parent / "golden_set.jsonl"
    items = [json.loads(l) for l in golden_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.limit:
        items = items[: args.limit]

    answers_path = Path(__file__).resolve().parent / "reports" / "answers.jsonl"
    answers_path.parent.mkdir(parents=True, exist_ok=True)

    done = {}
    if args.skip_generate and answers_path.exists():
        for l in answers_path.read_text(encoding="utf-8").splitlines():
            if l.strip():
                d = json.loads(l)
                done[d["question"]] = d

    print(f"生成层评测：{len(items)} 条（skip-generate={args.skip_generate}）")
    results = []
    with answers_path.open("a", encoding="utf-8") as f:
        for i, it in enumerate(items, 1):
            q = it["question"]
            print(f"[{i}/{len(items)}] {q[:30]}...", flush=True)
            if q in done:
                rec = done[q]
            else:
                context = retrieve_context(q)
                try:
                    answer = generate(q, context)
                except Exception as e:
                    answer = f"[生成失败] {e}"
                rec = {"question": q, "context": context, "answer": answer,
                       "expected_docs": it["expected_docs"], "answer_points": it["answer_points"],
                       "category": it["category"]}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
            score = judge(q, rec["context"], rec["answer"], rec["answer_points"])
            results.append({**rec, **score})

    def avg(key, subset=None):
        rs = [r for r in results if r.get(key) is not None and (subset is None or r["category"] == subset)]
        return sum(r[key] for r in rs) / len(rs) if rs else 0.0

    print("\n===== 生成层汇总 =====")
    print(f"faithfulness 平均:   {avg('faithfulness'):.2f}")
    print(f"answer_relevancy:    {avg('answer_relevancy'):.2f}")
    print(f"correctness 平均:    {avg('correctness'):.2f}")
    print(f"hallucination 平均:  {avg('hallucination'):.2f}")
    from collections import Counter
    verdicts = Counter(r.get("verdict", "unknown") for r in results)
    print(f"verdict 分布: {dict(verdicts)}")
    print("\n低分案例（correctness < 0.5 或 hallucination > 0.3）:")
    for r in results:
        if r.get("correctness", 1) < 0.5 or r.get("hallucination", 0) > 0.3:
            print(f"  Q: {r['question'][:40]}")
            print(f"     verdict={r.get('verdict')} corr={r.get('correctness')} hal={r.get('hallucination')}")
            print(f"     答案: {r['answer'][:120]}")

    report = Path(__file__).resolve().parent / "reports" / "generation-report.md"
    lines = [
        "# RAG 生成层评测报告（LLM-as-a-Judge）",
        "",
        f"> 生成时间：{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"> 评测集：{len(items)} 条 | 裁判：DeepSeek（指标对齐 RAGAS）",
        f"> 链路：检索（语义+关键词兜底）→ DeepSeek 生成 → Judge 打分",
        "",
        "## 总体指标",
        "",
        "| 指标 | 平均分 |",
        "|---|---|",
        f"| faithfulness（忠实度） | {avg('faithfulness'):.2f} |",
        f"| answer_relevancy（相关性） | {avg('answer_relevancy'):.2f} |",
        f"| correctness（正确度） | {avg('correctness'):.2f} |",
        f"| hallucination（幻觉率，越低越好） | {avg('hallucination'):.2f} |",
        "",
        "## Verdict 分布",
        "",
        "| 判定 | 数量 |",
        "|---|---|",
    ]
    for v, c in verdicts.items():
        lines.append(f"| {v} | {c} |")
    lines += ["", "## 逐条明细", "", "| 问题 | 类别 | verdict | faithful | relevancy | correct | halluc |", "|---|---|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['question'][:28]} | {r['category']} | {r.get('verdict')} | {r.get('faithfulness')} | {r.get('answer_relevancy')} | {r.get('correctness')} | {r.get('hallucination')} |")
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告已写入: {report}")
    print(f"答案存档: {answers_path}（供人工抽检）")


if __name__ == "__main__":
    main()
