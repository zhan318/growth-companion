# RAG 评测体系（eval/）

对 Obsidian 知识库 RAG 的**效果评测**，与 `performance-test/`（性能评测）互补：
性能评测回答"快不快"，本目录回答"**答得对不对**"。

## 分层思路

```
golden_set.jsonl（评测集：问题 → 期望命中文档 → 期望答案要点）
        │
        ├─ eval_retrieval.py  第 1 层：检索层判定（代码算，零成本）
        │    指标：语义命中率 / 合并命中率 / Recall@K / not_in_kb 越界检出
        │
        └─ eval_generation.py 第 2 层：生成层判定（LLM-as-a-Judge）
             指标（对齐 RAGAS）：faithfulness / answer_relevancy / correctness / hallucination
```

分层的目的：**定位瓶颈归属**——检索层差改 embedding/分块/混合检索；
生成层差改 prompt/上下文。两层混在一起测，无法判断问题出在哪一环。

## 评测集（golden_set.jsonl）

每条约 5 个字段：

| 字段 | 说明 |
|---|---|
| question | 用户真实问题（从知识库实际内容出题） |
| expected_docs | 期望命中的文档相对路径（vault 相对） |
| answer_points | 期望答案要点（判分用） |
| category | direct（直接命中）/ reasoning（需推理）/ cross（跨文档）/ not_in_kb（不在库） |
| difficulty | easy / medium / hard |

**难度梯度设计**（面试可讲）：
- direct：问题与笔记标题/内容强相关，测基础检索
- reasoning：答案散落多篇笔记，需合并
- cross：跨主题联动
- not_in_kb：知识库里没有的，**测防幻觉**（系统应诚实拒绝而非编造）

**扩展方法**：翻自己的笔记，把真实会问的问题记下来；每类保持 10-20 条；
50 条起步、100 条更有统计意义。

## 运行方法（在项目根目录）

```bash
# 第 1 层：检索层（零成本，不调 LLM）
.venv/Scripts/python eval/eval_retrieval.py [--k 3] [--limit 25]

# 第 2 层：生成层（每条 2 次 DeepSeek 调用：生成 + 判分）
.venv/Scripts/python eval/eval_generation.py [--limit 25]

# 跳过生成、仅用已存档答案重新判分
.venv/Scripts/python eval/eval_generation.py --skip-generate
```

> 注：如环境注入了 HTTP_PROXY 且代理未启动，先 `unset HTTP_PROXY HTTPS_PROXY ALL_PROXY` 再运行。

## 产出

| 文件 | 内容 |
|---|---|
| reports/retrieval-report.md | 检索层报告：命中率、Recall@K、失败案例 |
| reports/generation-report.md | 生成层报告：faithfulness / relevancy / correctness / hallucination、verdict 分布 |
| reports/answers.jsonl | 全部问答存档（问题+上下文+答案），供**人工抽检**（人工抽 20-30 条校准 LLM 裁判） |

## 已知限制（面试答问准备）

1. **LLM-as-a-Judge 有裁判偏差**：DeepSeek 自我评价可能偏乐观，用人工抽检校准；
   更严格可用 GPT-4 等更强模型当裁判（换 `build_llm` 即可）。
2. **chunk 切分导致信息不完整**：长列表被分块切断会漏内容（如"十大排序"只答出 5 个），
   属分块策略问题，可增大 chunk size 或对列表类内容做结构化处理。
3. **关键词提取粒度过大（已修复 2026-08-15）**：`re.findall(r"[\u4e00-\u9fa5]{2,}")`
   会把无标点长句当单个 token → 已改为 2/3/4 字 n-gram 滑窗切词 + 内容命中计数加权，
   检索层命中率 85.7% → 100%（golden 集回归验证）。
4. **not_in_kb 也会检索到噪音文档**：库外问题同样会返回若干无关片段，需 prompt 严格约束
   生成层"无相关内容必须诚实说明"，这正是 golden 里 not_in_kb 类存在的意义。
