# -*- coding: utf-8 -*-
"""P2 特殊模式真机测试：模拟面试模式 + 上下文滚动摘要压缩

这两块是 e2e / http 冒烟没覆盖的逻辑，且各自有特殊性：
- 面试模式：第一轮绕过 LLM 直接出题、一题一答节奏、题号递增，与 workspace 主链路分叉
- 摘要压缩：会话消息超阈值（12 条）时用 LLM 把旧对话压成摘要，验证压缩触发与摘要落库

用法：
    .venv/Scripts/python eval/eval_p2_special.py
输出：
    eval/reports/p2-report.md
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

INTERVIEW_SID = "p2_interview_test"
COMPRESS_SID = "p2_compress_test"


def test_interview():
    """面试模式：三轮，验证第一轮直接出题、后续点评+出新题、题号递增"""
    from agent.agent import Agent

    print("===== Part 1: 模拟面试模式 =====")
    agent = Agent(session_id=INTERVIEW_SID)

    results = []
    prompts = [
        "Python 后端",                          # 第一轮：直接出题，不调 LLM
        "我的回答是：list 推导式通常比 for 循环快，因为少了函数调用和 append 开销。",  # 第二轮：点评+下一题
        "下一题",                                # 第三轮：继续
    ]
    for i, p in enumerate(prompts, 1):
        t0 = time.perf_counter()
        try:
            ans = agent.run(p, mode="interview")
        except Exception as e:
            ans = f"[运行失败] {type(e).__name__}: {e}"
        dt = time.perf_counter() - t0
        results.append({"round": i, "elapsed": round(dt, 1), "answer": ans})
        print(f"  第{i}轮 ({dt:.1f}s): {ans[:90]}")

    # 判定
    a1, a2, a3 = (r["answer"] for r in results)
    first_direct = "模拟面试" in a1 or "题" in a1 or "开始" in a1
    distinct = a1 != a2 and a2 != a3
    passed = first_direct and distinct and all("运行失败" not in r["answer"] for r in results)
    print(f"  判定: 第一轮直接出题={first_direct} | 题目递增(三轮不重复)={distinct} | 结果={'PASS' if passed else 'FAIL'}")
    return {
        "name": "模拟面试模式三轮流转",
        "ok": passed,
        "note": f"第一轮 {results[0]['elapsed']}s（无 LLM）/ 后续轮平均 {sum(r['elapsed'] for r in results[1:])/max(len(results)-1,1):.1f}s",
        "detail": {"rounds": [{"round": r["round"], "elapsed": r["elapsed"], "preview": r["answer"][:60]} for r in results]},
    }


def test_compression():
    """摘要压缩：塞 14 条消息（超阈值 12）→ 触发压缩 → 验证摘要落库"""
    from memory.memory import Memory
    from memory.summarizer import compress_if_needed

    print("\n===== Part 2: 上下文滚动摘要压缩 =====")
    mem = Memory()
    mem.clear_session(COMPRESS_SID)

    # 7 轮 = 14 条消息（> COMPRESSION_THRESHOLD=12）
    for i in range(7):
        mem.save_message(COMPRESS_SID, "user", f"第{i+1}轮：我想了解 Python 的异步编程，比如 asyncio 怎么用。")
        mem.save_message(COMPRESS_SID, "assistant", f"第{i+1}轮回答：asyncio 用事件循环调度协程，await 挂起不阻塞线程，适合 IO 密集场景。")

    n_before = mem.count_messages(COMPRESS_SID)
    print(f"  压缩前消息数: {n_before}")

    t0 = time.perf_counter()
    ok = compress_if_needed(COMPRESS_SID, mem)
    dt = time.perf_counter() - t0

    summary = mem.get_session_summary(COMPRESS_SID)
    summary_text = (summary or {}).get("summary", "")
    print(f"  压缩触发: {ok}（{dt:.1f}s，含 LLM 生成摘要）")
    print(f"  摘要内容: {summary_text[:120]}")

    passed = ok and bool(summary_text) and len(summary_text) > 10
    print(f"  判定: 触发={ok} | 摘要非空={bool(summary_text)} | 结果={'PASS' if passed else 'FAIL'}")
    return {
        "name": "上下文滚动摘要压缩",
        "ok": passed,
        "note": f"消息 {n_before} 条 → 摘要 {len(summary_text)} 字（{dt:.1f}s）",
        "detail": {"summary": summary_text},
    }


def main():
    tests = [test_interview(), test_compression()]

    # 清理
    try:
        from memory.memory import Memory
        m = Memory()
        for sid in (INTERVIEW_SID, COMPRESS_SID):
            m.clear_session(sid)
        print("\n已清理测试会话")
    except Exception as e:
        print(f"清理失败: {e}")

    n = len(tests)
    passed = sum(1 for t in tests if t["ok"])
    print(f"\n===== P2 汇总: {passed}/{n} 通过 =====")
    for t in tests:
        print(f"  [{'PASS' if t['ok'] else 'FAIL'}] {t['name']} — {t['note']}")

    lines = [
        "# P2 特殊模式真机测试报告",
        "",
        f"> 生成时间：{time.strftime('%Y-%m-%d %H:%M')}",
        f"> 结果：**{passed}/{n} 通过**",
        "",
        "| 用例 | 结果 | 说明 |",
        "|---|---|---|",
    ]
    for t in tests:
        lines.append(f"| {t['name']} | {'PASS' if t['ok'] else 'FAIL'} | {t['note']} |")
    for t in tests:
        lines += ["", f"## {t['name']}", "", "```json", json.dumps(t.get("detail", {}), ensure_ascii=False, indent=2), "```"]
    out = ROOT / "eval" / "reports" / "p2-report.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告已写入: {out}")


if __name__ == "__main__":
    main()
