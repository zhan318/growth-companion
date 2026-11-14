# GitHub OAuth 冒烟测试报告

> 生成时间：2026-11-12 15:26
> 目标服务：http://127.0.0.1:8000
> 结果：**3/3 通过（100.0%）**

## 明细

| # | 用例 | 路径 | 状态码 | 耗时ms | 结果 | 备注 |
|---|---|---|---|---|---|---|
| 1 | 登录-跳转授权页 | `/auth/github/login` | 307 | 14.1 | PASS | client_id=Ov23li7LZOWE… scope=read:user user:email state=764 |
| 2 | 回调-缺授权码 | `/auth/github/callback` | 400 | 1.9 | PASS |  |
| 3 | 回调-无效授权码 | `/auth/github/callback?code=…` | 401 | 1088.1 | PASS |  |

## 未覆盖（需手动/单独测）

- 未配置 `GITHUB_CLIENT_ID` → 501（需单独起清空该变量的服务）
- 真实 code → access_token → userinfo → JWT 完整链路（需浏览器授权一次）
