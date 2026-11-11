# Agent 端到端评测报告（e2e）

> 生成时间：2026-11-11 15:55
> 用例：36 条（golden RAG 25 条 + 功能 11 条）| Judge：跟随默认 provider
> 链路：Agent.run() 进程内直调（上下文组装 → ReAct 工具循环 → 生成）

## 路由准确率（按类别）

| 类别 | 命中/总数 | 准确率 |
|---|---|---|
| chat | 3/3 | 100.0% |
| rag | 21/21 | 100.0% |
| rag_oob | 3/4 | 75.0% |
| read_note | 1/1 | 100.0% |
| tool | 6/6 | 100.0% |
| write_note | 1/1 | 100.0% |
| **总命中率** | **35/36** | **97.2%** |

## 答案质量（LLM-as-a-Judge）

- correct：31 | partial：3 | wrong：0 | refused_ok：0 | refused_bad：2
- 综合得分：90.3%

## 响应耗时（进程内，不含 HTTP 层）

- 平均 28.4s | p50 29.7s | p95 71.8s
- 注意：含 LLM 网络延迟与工具外呼（天气/热搜/搜索走真实 API）

## 逐条明细

| # | 类别 | 预期工具 | 实际调用 | 路由 | 耗时s | verdict |
|---|---|---|---|---|---|---|
| 1 | rag | search_obsidian_notes | search_obsidian_notes,search_obsidian_notes | HIT | 71.8 | correct |
| 2 | rag | search_obsidian_notes | search_obsidian_notes,search_obsidian_notes | HIT | 29.73 | correct |
| 3 | rag | search_obsidian_notes | search_obsidian_notes,search_obsidian_notes,read_obsidian_note,search_obsidian_notes | HIT | 44.02 | correct |
| 4 | rag | search_obsidian_notes | search_obsidian_notes,search_obsidian_notes | HIT | 31.87 | correct |
| 5 | rag | search_obsidian_notes | search_obsidian_notes,search_obsidian_notes | HIT | 36.41 | correct |
| 6 | rag | search_obsidian_notes | search_obsidian_notes,search_obsidian_notes | HIT | 22.86 | correct |
| 7 | rag | search_obsidian_notes | search_obsidian_notes,search_obsidian_notes | HIT | 26.79 | correct |
| 8 | rag | search_obsidian_notes | search_obsidian_notes | HIT | 12.99 | correct |
| 9 | rag | search_obsidian_notes | search_obsidian_notes,search_obsidian_notes,search_obsidian_notes,read_obsidian_note | HIT | 33.24 | correct |
| 10 | rag | search_obsidian_notes | search_obsidian_notes,search_obsidian_notes,search_obsidian_notes,search_obsidian_notes,search_obsidian_notes,search_obsidian_notes,search_obsidian_notes | HIT | 78.58 | correct |
| 11 | rag | search_obsidian_notes | search_obsidian_notes,search_obsidian_notes | HIT | 29.95 | correct |
| 12 | rag | search_obsidian_notes | search_obsidian_notes,search_obsidian_notes | HIT | 31.45 | correct |
| 13 | rag | search_obsidian_notes | search_obsidian_notes,search_obsidian_notes | HIT | 26.72 | correct |
| 14 | rag | search_obsidian_notes | search_obsidian_notes,search_obsidian_notes,search_obsidian_notes,search_obsidian_notes | HIT | 56.97 | correct |
| 15 | rag | search_obsidian_notes | search_obsidian_notes,search_obsidian_notes,read_obsidian_note | HIT | 33.14 | correct |
| 16 | rag | search_obsidian_notes | search_obsidian_notes,search_obsidian_notes | HIT | 33.43 | correct |
| 17 | rag | search_obsidian_notes | search_obsidian_notes,search_obsidian_notes,read_obsidian_note,read_obsidian_note,read_obsidian_note,read_obsidian_note,search_obsidian_notes,search_obsidian_notes | HIT | 57.48 | correct |
| 18 | rag | search_obsidian_notes | search_obsidian_notes,search_obsidian_notes,search_obsidian_notes | HIT | 46.98 | correct |
| 19 | rag | search_obsidian_notes | search_obsidian_notes,search_obsidian_notes | HIT | 41.07 | correct |
| 20 | rag | search_obsidian_notes | search_obsidian_notes,search_obsidian_notes,search_obsidian_notes,search_obsidian_notes | HIT | 54.99 | correct |
| 21 | rag_oob | search_obsidian_notes | search_obsidian_notes | HIT | 17.59 | refused_bad |
| 22 | rag_oob | search_obsidian_notes | web_search | MISS | 7.02 | refused_bad |
| 23 | rag_oob | search_obsidian_notes | search_obsidian_notes,search_obsidian_notes,web_search,web_search | HIT | 49.51 | correct |
| 24 | rag_oob | search_obsidian_notes | search_obsidian_notes,search_obsidian_notes,write_obsidian_note | HIT | 48.43 | partial |
| 25 | rag | search_obsidian_notes | search_obsidian_notes,search_obsidian_notes | HIT | 23.63 | correct |
| 26 | tool | get_weather | get_weather | HIT | 7.17 | correct |
| 27 | tool | calculate | calculate | HIT | 4.28 | correct |
| 28 | tool | get_hotlist | get_hotlist,web_search,get_hotlist | HIT | 14.14 | correct |
| 29 | tool | web_search | web_search | HIT | 6.77 | correct |
| 30 | tool | get_hotlist | get_hotlist,get_hotlist,web_search | HIT | 9.54 | partial |
| 31 | tool | calculate | calculate | HIT | 4.16 | correct |
| 32 | read_note | read_obsidian_note | read_obsidian_note,search_obsidian_notes | HIT | 16.48 | partial |
| 33 | write_note | write_obsidian_note | write_obsidian_note | HIT | 4.46 | correct |
| 34 | chat | （无） | （无） | HIT | 3.7 | correct |
| 35 | chat | （无） | （无） | HIT | 2.46 | correct |
| 36 | chat | （无） | （无） | HIT | 2.32 | correct |

## 路由失败案例

**Q: 2026 年世界杯冠军是哪个队？**（rag_oob）
- 预期: ['search_obsidian_notes']；实际: ['web_search']
- 答案摘要: 西班牙 🇪🇸 夺冠。

决赛 2026 年 7 月 19 日在新泽西 MetLife 体育场，西班牙加时赛 1-0 战胜卫冕冠军阿根廷（托雷斯第 106 分钟破门），时隔 16 年（2010 年后）再
