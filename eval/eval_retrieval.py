# -*- coding: utf-8 -*-
"""检索层评测：Recall@K / 命中率（零成本，不调用 LLM）

评测对象：Obsidian RAG 的真实检索路径（dense 语义检索 + BM25 稀疏检索 → RRF 融合），
与 knowledge/pipeline.retrieve_obsidian 完全一致（同一函数，不再复制一份）。

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

from config import OBSIDIAN_VAULT_DIR  # noqa: E402
from knowledge.pipeline import retrieve_obsidian  # noqa: E402


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


def hit(expected, rels) -> bool:
    """判断任一期望文档是否命中检索结果（按 rel_path 后缀匹配）"""
    return any(any(e == r or r.endswith("/" + e) for e in expected) for r in rels)


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

    results = []
    for it in items:
        expected = [str(e).replace("\\", "/") for e in it["expected_docs"]]
        dense, bm25, merged = retrieve_obsidian(it["question"], args.k)
        dense_rels = [rel_of(d, vault) for d in dense]
        bm25_rels = [rel_of(d, vault) for d in bm25]
        merged_rels = [rel_of(d, vault) for d in merged]
        results.append({
            "q": it["question"], "expected": expected, "category": it["category"],
            "dense_hit": hit(expected, dense_rels),
            "bm25_hit": hit(expected, bm25_rels),
            "merged_hit": hit(expected, merged_rels),
            "topk_hit": hit(expected, merged_rels[: args.k]),
            "merged_top": merged_rels[:3],
            "n_dense": len(dense), "n_bm25": len(bm25), "n_merged": len(merged),
        })

    n = len(results)
    valid = [r for r in results if r["expected"]]          # 期望有文档的（计入命中率）
    nin = [r for r in results if not r["expected"]]        # 不在库（预期 0 命中，防幻觉项）
    nv = len(valid)
    dense_hit = sum(r["dense_hit"] for r in valid)
    bm25_hit = sum(r["bm25_hit"] for r in valid)
    merged_hit = sum(r["merged_hit"] for r in valid)
    topk_hit = sum(r["topk_hit"] for r in valid)
    # BM25 额外救回：dense 漏检、融合后命中（说明稀疏检索补上了召回）
    bm25_extra = sum(1 for r in valid if r["merged_hit"] and not r["dense_hit"])
    nin_found = sum(1 for r in nin if r["merged_hit"])     # 越界检出 = 可能诱发幻觉

    print(f"\n===== 汇总（有效样本 {nv} 条，不含 not_in_kb {len(nin)} 条）=====")
    print(f"dense 语义检索命中率:  {dense_hit}/{nv} = {dense_hit/nv:.1%}")
    print(f"BM25 稀疏检索命中率:   {bm25_hit}/{nv} = {bm25_hit/nv:.1%}")
    print(f"RRF 融合后命中率(总):  {merged_hit}/{nv} = {merged_hit/nv:.1%}")
    print(f"Recall@{args.k}(前{args.k}条命中): {topk_hit}/{nv} = {topk_hit/nv:.1%}")
    print(f"BM25 额外救回:         {bm25_extra} 条（dense 漏检、融合命中）")
    print(f"not_in_kb 越界检出:    {nin_found}/{len(nin)} 条（应全部为 0）")

    print("\n===== 按类别 =====")
    from collections import defaultdict
    by_cat = defaultdict(lambda: [0, 0])
    for r in valid:
        by_cat[r["category"]][0] += r["merged_hit"]
        by_cat[r["category"]][1] += 1
    for c, (h, t) in sorted(by_cat.items()):
        print(f"  {c:<12} {h}/{t} = {h/t:.1%}")

    print("\n===== 失败案例（有期望文档但融合后未命中）=====")
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
        f"> 检索路径：dense 语义检索（Chroma, top-{args.k}）+ BM25 稀疏检索 → RRF 融合",
        "",
        "## 总指标（有效样本）",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        f"| dense 语义检索单独命中率 | {dense_hit}/{nv} = {dense_hit/nv:.1%} |",
        f"| BM25 稀疏检索单独命中率 | {bm25_hit}/{nv} = {bm25_hit/nv:.1%} |",
        f"| **RRF 融合后命中率** | **{merged_hit}/{nv} = {merged_hit/nv:.1%}** |",
        f"| Recall@{args.k}（前 {args.k} 条内命中） | {topk_hit}/{nv} = {topk_hit/nv:.1%} |",
        f"| BM25 额外救回 | {bm25_extra} 条（dense 漏检、融合命中） |",
        f"| not_in_kb 越界检出 | {nin_found}/{len(nin)} 条（应全部为 0） |",
        "",
        "## 按类别（融合后命中率）",
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
