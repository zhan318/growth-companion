# -*- coding: utf-8 -*-
"""检索层评测：Recall@K / 命中率（零成本，不调用 LLM）

评测对象：Obsidian RAG 的真实检索路径（语义检索 + 关键词兜底合并去重），
与 knowledge/pipeline.query_obsidian 的检索部分完全一致。

用法（在项目根目录）：
    .venv/Scripts/python eval/eval_retrieval.py [--k 3] [--limit 25]
输出：
    reports/retrieval-report.md   —— 评测报告（可直接进简历）
"""

import argparse
import json
import sys
from pathlib import Path

# 项目根目录加入 import 路径（脚本在 eval/ 下运行）
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import OBSIDIAN_COLLECTION, OBSIDIAN_VAULT_DIR
from knowledge.pipeline import _keyword_fallback
from knowledge.vector_store import get_vector_store


def rel_of(doc, vault) -> str:
    """从 Document 元数据还原 vault 相对路径（统一为正斜杠）"""
    meta = doc.metadata or {}
    if meta.get("rel_path"):
        return str(meta["rel_path"]).replace("\\", "/")
    src = str(meta.get("source", ""))
    try:
        return str(Path(src).resolve().relative_to(Path(vault).resolve())).replace("\\", "/")
    except Exception:
        return Path(src).name


def merged_retrieval(question: str, vault: str, k: int):
    """模拟 query_obsidian 的检索路径：语义为主 + 关键词兜底，合并去重"""
    store = get_vector_store(OBSIDIAN_COLLECTION)
    semantic = store.search(question, k=k)
    keyword = _keyword_fallback(question, vault, top_n=5)
    seen, docs = set(), []
    for d in (*semantic, *keyword):
        key = d.page_content.strip()
        if key and key not in seen:
            seen.add(key)
            docs.append(d)
    return semantic, keyword, docs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=3, help="检索 top-k（默认 3，与 KNOWLEDGE_RETRIEVE_TOP_K 一致）")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条（0 = 全部）")
    args = ap.parse_args()

    golden_path = Path(__file__).resolve().parent / "golden_set.jsonl"
    items = [json.loads(l) for l in golden_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.limit:
        items = items[: args.limit]

    vault = OBSIDIAN_VAULT_DIR
    print(f"Golden 集: {len(items)} 条 | top-k={args.k} | vault={vault}")

    results = []  # {q, expected, category, sem_hit, merged_hit, top3_hit, sem_top, merged_top}
    for it in items:
        expected = [str(e).replace("\\", "/") for e in it["expected_docs"]]
        semantic, keyword, merged = merged_retrieval(it["question"], vault, args.k)
        sem_rels = [rel_of(d, vault) for d in semantic]
        merged_rels = [rel_of(d, vault) for d in merged]
        sem_hit = any(any(e == r or r.endswith("/" + e) for e in expected) for r in sem_rels)
        merged_hit = any(any(e == r or r.endswith("/" + e) for e in expected) for r in merged_rels)
        top3_hit = any(any(e == r or r.endswith("/" + e) for e in expected) for r in merged_rels[:3])
        results.append({
            "q": it["question"], "expected": expected, "category": it["category"],
            "sem_hit": sem_hit, "merged_hit": merged_hit, "top3_hit": top3_hit,
            "sem_top": sem_rels[:3], "merged_top": merged_rels[:3],
            "n_sem": len(semantic), "n_merged": len(merged),
        })

    n = len(results)
    valid = [r for r in results if r["expected"]]          # 期望有文档的（计入命中率）
    nin = [r for r in results if not r["expected"]]        # 不在库（预期 0 命中，防幻觉项）
    nv = len(valid)
    sem_hit = sum(r["sem_hit"] for r in valid)
    merged_hit = sum(r["merged_hit"] for r in valid)
    top3_hit = sum(r["top3_hit"] for r in valid)
    kw_extra = sum(1 for r in valid if r["merged_hit"] and not r["sem_hit"])
    nin_found = sum(1 for r in nin if r["merged_hit"])     # 越界检出 = 可能诱发幻觉

    print(f"\n===== 汇总（有效样本 {nv} 条，不含 not_in_kb {len(nin)} 条）=====")
    print(f"语义检索命中率:      {sem_hit}/{nv} = {sem_hit/nv:.1%}")
    print(f"合并后命中率(总):    {merged_hit}/{nv} = {merged_hit/nv:.1%}")
    print(f"Recall@K(前{args.k}条命中): {top3_hit}/{nv} = {top3_hit/nv:.1%}")
    print(f"关键词兜底额外救回:  {kw_extra} 条（语义漏检、兜底命中）")
    print(f"not_in_kb 越界检出:  {nin_found}/{len(nin)} 条（应全部为 0）")

    print("\n===== 按类别 =====")
    from collections import defaultdict
    by_cat = defaultdict(lambda: [0, 0])
    for r in valid:
        by_cat[r["category"]][0] += r["merged_hit"]
        by_cat[r["category"]][1] += 1
    for c, (h, t) in sorted(by_cat.items()):
        print(f"  {c:<12} {h}/{t} = {h/t:.1%}")

    print("\n===== 失败案例（有期望文档但合并后未命中）=====")
    fails = [r for r in valid if not r["merged_hit"]]
    if not fails:
        print("  无 —— 全部命中 ✅")
    for r in fails:
        print(f"  Q: {r['q']}")
        print(f"     期望: {r['expected']}")
        print(f"     实际 top: {r['merged_top'][:3]}")

    print(f"\n===== not_in_kb（防幻觉项，预期 0 命中）=====")
    for r in nin:
        print(f"  Q: {r['q']} → 检出 {r['n_merged']} 条: {r['merged_top'][:2]}")

    # ── 写报告 ──
    report = Path(__file__).resolve().parent / "reports" / "retrieval-report.md"
    lines = [
        "# RAG 检索层评测报告",
        "",
        f"> 生成时间：{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"> 评测集：eval/golden_set.jsonl（有效 {nv} 条 + not_in_kb {len(nin)} 条）| top-k = {args.k}",
        f"> 检索路径：语义检索（Chroma, top-{args.k}）+ 关键词兜底（标题 n-gram + 内容弱匹配）合并去重",
        "",
        "## 总指标（有效样本）",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        f"| 语义检索单独命中率 | {sem_hit}/{nv} = {sem_hit/nv:.1%} |",
        f"| **合并后命中率** | **{merged_hit}/{nv} = {merged_hit/nv:.1%}** |",
        f"| Recall@{args.k}（前 {args.k} 条内命中） | {top3_hit}/{nv} = {top3_hit/nv:.1%} |",
        f"| 关键词兜底额外救回 | {kw_extra} 条 |",
        f"| not_in_kb 越界检出 | {nin_found}/{len(nin)} 条（应全部为 0） |",
        "",
        "## 按类别（合并后命中率）",
        "",
        "| 类别 | 命中/总数 | 命中率 |",
        "|---|---|---|",
    ]
    for c, (h, t) in sorted(by_cat.items()):
        lines.append(f"| {c} | {h}/{t} | {h/t:.1%} |")
    lines += ["", "## 失败案例分析", ""]
    if not fails:
        lines.append("无失败案例，全部命中 ✅")
    for r in fails:
        lines += [
            f"**Q: {r['q']}**（类别: {r['category']}）",
            f"- 期望文档: {r['expected']}",
            f"- 实际检索到: {r['merged_top'][:3]}",
            "",
        ]
    lines += ["## not_in_kb 明细（防幻觉项）", ""]
    for r in nin:
        lines.append(f"- Q: {r['q']} → 检出 {r['n_merged']} 条")
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告已写入: {report}")


if __name__ == "__main__":
    main()
