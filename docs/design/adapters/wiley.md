---
title: Adapter 设计 · Wiley Online Library
status: review
owner: fable5
updated: 2026-07-21
---

# Adapter · `wiley`

## 1. 定位

- **family**: `auth_gated`（推荐档：**TDM API 优先**，页面 cookie 兜底——design/04 §3 第 1→2 档）
- **服务 venue**：Journal of Finance (JF)、Econometrica (ECMA)、RAND Journal、International Economic Review、Mathematical Finance、JEEA（部分年代）——金融第一刊与计量第一刊所在平台
- **capabilities**: `RESOLVE | FETCH`——enumerate 走 crossref（DOI 前缀 10.1111/10.1002/10.3982[ECMA]）。

## 2. 站点勘察摘要

来源：[research/site-survey/publisher-platforms-econfin.md](../../research/site-survey/publisher-platforms-econfin.md)（[LIVE] 2026-07-20）：

- 域：`onlinelibrary.wiley.com`；URL 模式（[LIVE] 实例）：期刊 `/journal/15406261`（ISSN 去连字符）；卷期 `/toc/15406261/2025/80/1`；文章 `/doi/10.1111/jofi.13477`（abs/full 变体）；PDF `/doi/pdf/10.1111/jofi.13424`（无权限跳登录墙）；
- **TDM API（端点已确认，转引官方支持页+官方 GitHub tdm-client）**：`GET https://api.wiley.com/onlinelibrary/tdm/v1/articles/{doi}` + 请求头 `Wiley-TDM-Client-Token`；返回 PDF；限机构订阅范围；**~3 req/s**；流程=个人账号→click-through TDM 协议→取 token（TDM@wiley.com）；⚠ 官方原文页被 Cloudflare 拦截未直接核验；
- 反爬（[LIVE]）：Cloudflare 通用质询（403）；robots.txt 宽松——AI 点名仅 GPTBot/Google-Extended，`*` 组仅路径级限制，孤立 `Crawl-delay: 1`（作用域含糊，保守起见遵守）；无 TDMRep；
- ECMA 特殊性：Econometric Society 拥有版权、Wiley 出版发行；学会官网（econsoc）有部分开放内容（TE/QE 全开放另走 `econsoc` adapter）；
- 认证：机构 SSO（"Institutional login"）/ 个人订阅。

## 3. 各阶段实现方案

- **resolve_assets**：DOI → 首选 AssetPlan(`url_strategy=api_call`, TDM endpoint)（token 已配置时）；fallback `/doi/pdf/...` 直链 + cookie（`url_strategy=direct`）。entitlement：TDM API 的 4xx 语义即预检；页面路径用落地页 "Get access" 面板启发式。
- **fetch_asset**：TDM：httpx + `Wiley-TDM-Client-Token` 头下载 PDF；页面路径：cookie jar 直取，被 Cloudflare 拦 → BrowserFetcher 同 context 兜底一次 → 仍失败 BLOCKED。
- **healthcheck**：TDM token 探测（已知有权 DOI HEAD）或账号页探针。
- **JF 特情**：AFA 会员个人订阅亦可（provider profile 可配 `wiley@afa`）；SSRN 常有 JF 接收稿先行版——ingest 的 preprint_of 关联高频场景（D-007）。

## 4. 限速与礼貌

- TDM API：条款速率 **~3 req/s 上限**（2026-07-20 勘察，转引口径）；本系统起步取 1 req/2s 保守，实测 429 行为后再调；
- 页面路径：**串行 1 req/6s + 日配额 200**（全局纪律）；
- TDM 条款要求（历史口径）：下载物仅本地挖掘用途、不再分发——与本系统红线天然一致（AC-0.1/需求§5）。

## 5. 失败模式映射

| 现象 | error_class |
|---|---|
| TDM 401（token 失效） | `auth_expired` → BLOCKED 提示重配 token |
| TDM 403（无该刊权限） | `no_entitlement` + Unpaywall/SSRN 版兜底 |
| TDM 429 | `rate_limited` |
| 页面 Cloudflare 挑战 | `challenge` → BLOCKED + 冷却 24h |
| PDF 魔数失败 | `integrity`(auth_leak) → healthcheck |

## 6. Fixtures 与测试

- **T1 单元**：DOI 前缀路由（10.1111/10.1002/10.3982 → 同 adapter）；TDM 响应/错误码判定表。
- **T3 fixture**：①TDM 成功响应（截断）②401/403/429 三态 ③页面 auth 四件套。
- **T6 runbook**：TDM token 申请→JF 单篇→token 失效演练（records 留痕）。
- **验收关联**：AC-4.1（JF/ECMA 单篇）、AC-4.3、AC-4.4。

## 7. 风险与维护

- TDM token 申请依赖机构订阅关系（Phase 4 前置外部依赖，预留申请周期）；
- Cloudflare 策略变化：canary 周检；页面兜底路径失效不算整体失效（TDM 为主干）；
- 勘察已并入（2026-07-20：TDM 端点/速率、robots、URL 实测）——可提交 approved 评审；剩余实现期事项：TDM 官方原文页复核（勘察时被 Cloudflare 拦截，仅转引口径）、token 申请。
