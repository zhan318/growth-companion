# HTTP 层冒烟测试报告

> 生成时间：2026-11-11 21:54
> 目标服务：http://127.0.0.1:8000
> 结果：**30/30 通过（100.0%）**

## 明细

| # | 用例 | 方法 | 路径 | 状态码 | 耗时ms | 结果 | 备注 |
|---|---|---|---|---|---|---|---|
| 1 | 健康检查 | GET | `/health` | 200 | 41.6 | PASS |  |
| 2 | 注册 | POST | `/auth/register` | 200 | 242.5 | PASS |  |
| 3 | 未授权访问 | GET | `/user/profile` | 401 | 31.7 | PASS |  |
| 4 | 登录-错误密码 | POST | `/auth/login` | 401 | 230.8 | PASS |  |
| 5 | 登录-正确密码 | POST | `/auth/login` | 200 | 270.5 | PASS |  |
| 6 | 读取资料 | GET | `/user/profile` | 200 | 24.2 | PASS |  |
| 7 | 更新资料 | PUT | `/user/profile` | 200 | 44.5 | PASS |  |
| 8 | 修改密码-旧密码错误 | PUT | `/user/password` | 400 | 472.8 | PASS |  |
| 9 | 列出 LLM keys | GET | `/user/llm-keys` | 200 | 27.5 | PASS |  |
| 10 | 保存 LLM key | PUT | `/user/llm-keys` | 200 | 11.8 | PASS |  |
| 11 | 删除 LLM key | DELETE | `/user/llm-keys/deepseek` | 200 | 47.5 | PASS |  |
| 12 | 模型列表 | GET | `/models` | 200 | 12.1 | PASS |  |
| 13 | MBTI 题目 | GET | `/mbti/questions` | 200 | 28.7 | PASS |  |
| 14 | MBTI 分析 | POST | `/mbti/analyze` | 200 | 4142.8 | PASS |  |
| 15 | MBTI 历史 | GET | `/mbti/history` | 200 | 28.8 | PASS |  |
| 16 | 创建会话 | POST | `/user/sessions` | 200 | 30.7 | PASS |  |
| 17 | 会话列表 | GET | `/user/sessions` | 200 | 31.8 | PASS |  |
| 18 | 会话改名 | PATCH | `/user/sessions/u8_ba163fbe3af1` | 200 | 12.6 | PASS |  |
| 19 | 会话消息 | GET | `/user/sessions/u8_ba163fbe3af1/messages` | 200 | 53.1 | PASS |  |
| 20 | 笔记保存 | POST | `/notes/save` | 200 | 14.7 | PASS |  |
| 21 | 数据看板 | GET | `/dashboard/stats` | 200 | 88.5 | PASS |  |
| 22 | Obsidian 状态 | GET | `/obsidian/status` | 200 | 25.8 | PASS |  |
| 23 | 上传文档 | POST | `/knowledge/upload` | 200 | 17.8 | PASS |  |
| 24 | 上传文档索引 | POST | `/knowledge/index` | 200 | 19009.5 | PASS |  |
| 25 | 上传文档查询 | POST | `/knowledge/query` | 200 | 3741.2 | PASS |  |
| 26 | 对话-整段 | POST | `/chat` | 200 | 2154.2 | PASS |  |
| 27 | 对话-流式(SSE) | POST | `/chat/stream` | 200 | 4270.3 | PASS | 首字 3868ms / 19 事件 / 64 字 |
| 28 | 删除会话 | DELETE | `/user/sessions/u8_ba163fbe3af1` | 200 | 21.8 | PASS |  |
| 29 | 登出 | POST | `/auth/logout` | 200 | 63.8 | PASS |  |
| 30 | 登出后访问 | GET | `/user/profile` | 401 | 19.1 | PASS |  |

## 未覆盖（需单独测）

- `/interview/save|finish|weakness`：会写 vault 归档文件，且需真实面试会话
- `/mbti/export`：会写 vault
- `/obsidian/index`：全量重建约 2 分钟
- GitHub OAuth：需浏览器跳转
- 前端 UI、Docker 部署、并发性能

## 说明

- 冒烟创建了测试用户 `smoke_5011cebf`（无删除用户接口，会留在库中）
- 测试笔记与上传文件已自动清理
- SSE 首字延迟：3868ms
