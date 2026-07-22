"""Elsevier ScienceDirect adapter 包（design/adapters/elsevier-sd.md；AC-4.1 载体）。

`auth_gated`/官方 API 档——elsevier robots 全禁 + 全站 TDMRep → 页面路线双重不可行 →
**API 唯一正道**（AGENTS §6）。能力 ``RESOLVE | FETCH``（enumerate 走 crossref，D-005）；
域 `api.elsevier.com`。服务 JFE/JET/JPubEco/JBF 等 15+ 刊（一 adapter 覆盖，NFR-1 杠杆）。

- `parse`：entitlement 端点响应判定 + error 封套观测（零网络 JSON 解析；⚠[DOCS] 字段名待
  T7b 真实 key 核验，BLOCKER-1）。
- `adapter`：`ElsevierScienceDirectAdapter`——resolve（entitlement 预检 → AssetPlan /
  no_entitlement）+ fetch（Article Retrieval API PDF/XML 流式落盘）+ healthcheck（无 key→
  NotImplementedError→SKIP / 有 key→entitlement 探测）+ 429 当日熔断（B-M2）。

**X-ELS-APIKey 头凭证隔离**：有 key 时经**专属** `HttpClient`（携 `X-ELS-APIKey`
+ 可选 `X-ELS-Insttoken` 头）注入，绝不复用跨 adapter 共享 client——否则携密头随其它域
（crossref/dblp/...）请求外泄（沿 openreview/s2 专属 client 先例）。装配期专属 client 构造归
auth-framework AuthManager（T5）；本包 `set_http_client`/`set_api_key` 暴露注入 seam。
"""
