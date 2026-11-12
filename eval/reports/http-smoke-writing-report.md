# HTTP 层写盘接口冒烟报告

> 生成时间：2026-11-12 13:21
> 目标服务：http://127.0.0.1:8000
> 结果：**12/12 通过（100.0%）**

## 明细

| # | 用例 | 方法 | 路径 | 状态码 | 耗时ms | 结果 | 备注 |
|---|---|---|---|---|---|---|---|
| 1 | 健康检查 | GET | `/health` | 200 | 27.3 | PASS |  |
| 2 | 注册 | POST | `/auth/register` | 200 | 257.0 | PASS |  |
| 3 | 创建会话 | POST | `/user/sessions` | 200 | 17.6 | PASS |  |
| 4 | 对话造前置消息 | POST | `/chat` | 200 | 5209.0 | PASS |  |
| 5 | MBTI 题目 | GET | `/mbti/questions` | 200 | 21.1 | PASS |  |
| 6 | MBTI 分析 | POST | `/mbti/analyze` | 200 | 5781.8 | PASS |  |
| 7 | MBTI 导出档案 | POST | `/mbti/export` | 200 | 27.0 | PASS |  |
| 8 | 面试记录保存 | POST | `/interview/save` | 200 | 7230.2 | PASS |  |
| 9 | 面试结束归档 | POST | `/interview/finish` | 200 | 12037.3 | PASS |  |
| 10 | 薄弱点画像 | POST | `/interview/weakness` | 200 | 8367.5 | PASS |  |
| 11 | 归档越权会话 | POST | `/interview/save` | 403 | 27.2 | PASS |  |
| 12 | 删除会话 | DELETE | `/user/sessions/u9_7dd18b018138` | 200 | 27.9 | PASS |  |

## 副作用与清理

- 测试用户：`smokew_0191d26e`（无删除用户接口，留在库中）
- 写盘产物：`我的 MBTI 档案.md`、`模拟面试/面试记录/日期.md`、`模拟面试/薄弱点画像.md`（cleanup 已删除）
- 测试会话已删除；LLM token 已消耗少量（deepseek/glm）
- 若写盘文件被轮询索引扫入向量库，删文件后由下一次增量索引自动清理
