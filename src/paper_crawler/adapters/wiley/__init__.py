"""Wiley Online Library adapter 包（design/adapters/wiley.md，实现级；plan §4 T-wiley / D-024）。

`auth_gated` family，capabilities `RESOLVE | FETCH`——TDM API 优先（`GET api.wiley.com/
onlinelibrary/tdm/v1/articles/{DOI}` + `Wiley-TDM-Client-Token` 头 → 全文 PDF）。enumerate
走 crossref（DOI 前缀 `10.1111`/`10.1002`/`10.3982`）。服务金融第一刊 JF、计量第一刊
Econometrica 等（wiley.md §1）。

- `parse`：DOI 前缀路由 / TDM URL 构造 / `%PDF` 轻校验的零网络纯函数。
- `adapter`：`WileyAdapter`——TDM 客户端（真实 HTTP）+ token 门控 skip（无 token →
  resolve/fetch `AuthRequired`、healthcheck `NotImplementedError`→canary SKIP，s2 先例）
  + 双窗口限速（单桶 `RatePolicy(rpm=5, burst=3)`，wiley.md §4）+ 错误映射透传
  `HttpClient` 冻结类。

**token 门控 skip（D-024）**：Wiley TDM token 自助可得但 entitlement 受机构订阅约束；现状
config/env 无 token → 离线 DoD（resolve/fetch 逻辑 + 双窗口限速 + 错误映射单测）先行；live
FETCH / runbook 门控在 token 存在性之后（token 到位即活）。

**Wiley-TDM-Client-Token 头凭证隔离**：有 token 时经**专属** `HttpClient`（携该头）注入，
绝不复用跨 adapter 共享的 client——否则该头会随其它域的请求外泄（沿 openreview cookie /
s2 `x-api-key` 专属 client 先例；装配侧的 `_bind_wiley_token_client` CLI 接线属 token 到位后
的已知 union 点，不在本包交付面）。
"""
