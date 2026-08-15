# RAG 生成层评测报告（LLM-as-a-Judge）

> 生成时间：2026-08-15 17:08
> 评测集：25 条 | 裁判：DeepSeek（指标对齐 RAGAS）
> 链路：检索（语义+关键词兜底）→ DeepSeek 生成 → Judge 打分

## 总体指标

| 指标 | 平均分 |
|---|---|
| faithfulness（忠实度） | 0.83 |
| answer_relevancy（相关性） | 0.94 |
| correctness（正确度） | 0.80 |
| hallucination（幻觉率，越低越好） | 0.11 |

## Verdict 分布

| 判定 | 数量 |
|---|---|
| correct | 14 |
| partial | 3 |
| refused | 6 |
| wrong | 2 |

## 逐条明细

| 问题 | 类别 | verdict | faithful | relevancy | correct | halluc |
|---|---|---|---|---|---|---|
| 快速排序的代码实现是怎么写的？ | direct | correct | 1.0 | 1.0 | 1.0 | 0.0 |
| 十大经典排序算法都有哪些？ | direct | partial | 0.8 | 0.9 | 0.5 | 0.2 |
| 堆排序的原理是什么？ | direct | correct | 0.95 | 1.0 | 1.0 | 0.0 |
| Python 中 is 和 == 有什么区别？ | direct | correct | 1.0 | 1.0 | 1.0 | 0.0 |
| Python 的类方法、静态方法、实例方法有什么区别？ | direct | correct | 1.0 | 1.0 | 1.0 | 0.0 |
| 零基础学 Python 有哪些学习资源？ | direct | correct | 1.0 | 1.0 | 1.0 | 0.0 |
| 学程序过程中遇到单词 self 是什么意思？ | direct | correct | 1.0 | 1.0 | 1.0 | 0.0 |
| 输入字体突然变成繁体字怎么切换回来？ | direct | refused | 1.0 | 0.8 | 0.0 | 0.0 |
| 知识库的 embedding 用的什么模型？ | direct | correct | 1.0 | 1.0 | 1.0 | 0.0 |
| Agent 项目的模拟面试功能是怎么工作的？ | direct | correct | 1.0 | 1.0 | 1.0 | 0.0 |
| 我的 Agent 项目在并发性能上做了哪些优化？ | reasoning | wrong | 0.0 | 1.0 | 0.0 | 1.0 |
| 项目里是怎么保证知识库隐私安全的？ | reasoning | correct | 0.95 | 1.0 | 0.8 | 0.0 |
| 为什么选择本地 embedding 而不是调用云端 AP | reasoning | correct | 0.95 | 1.0 | 0.95 | 0.05 |
| RAG 检索效果不好应该怎么排查和优化？ | reasoning | partial | 0.5 | 0.8 | 0.3 | 0.0 |
| 项目的整体架构和技术栈是什么？ | cross | correct | 1.0 | 1.0 | 1.0 | 0.0 |
| 我的项目有哪些性能测试数据？ | cross | partial | 0.55 | 1.0 | 0.6 | 0.45 |
| 我的项目有什么亮点可以写进简历？ | cross | correct | 1.0 | 1.0 | 1.0 | 0.0 |
| 中文场景下 RAG 为什么召回率低？我做了什么改进？ | cross | refused | 0.0 | 0.0 | 0.0 | 0.0 |
| 归并排序的时间复杂度是多少？ | direct | correct | 1.0 | 1.0 | 1.0 | 0.0 |
| agent 学习路线应该怎么规划？ | direct | correct | 0.95 | 1.0 | 0.9 | 0.05 |
| 美联储加息对中国股市有什么影响？ | not_in_kb | refused | 1.0 | 1.0 | 1.0 | 0.0 |
| 2026 年世界杯冠军是哪个队？ | not_in_kb | refused | 1.0 | 1.0 | 1.0 | 0.0 |
| 帮我推荐一款适合新手的咖啡机 | not_in_kb | refused | 1.0 | 1.0 | 1.0 | 0.0 |
| 帮我写一个 Django 博客项目 | not_in_kb | refused | 1.0 | 1.0 | 1.0 | 0.0 |
| 英语单词 yield 在编程里是什么意思？ | direct | wrong | 0.0 | 1.0 | 1.0 | 1.0 |