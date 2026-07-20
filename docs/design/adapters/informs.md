---
title: Adapter 设计 · INFORMS PubsOnline
status: review
owner: fable5
updated: 2026-07-20
---

# Adapter · `informs`

## 1. 定位

- **family**: `auth_gated`
- **服务 venue**：Management Science (mnsc)、Operations Research (opre)、M&SOM (msom)、Mathematics of OR (moor)、IJOC (ijoc)、Marketing Science (mksc) 等全部 INFORMS 刊（[catalog/or-ms-journals.md](../../catalog/or-ms-journals.md)）
- **capabilities**: `RESOLVE | FETCH`——**discover/enumerate 一律走 crossref**（D-005；pubsonline 有 Cloudflare/WAF，[LIVE] 云 IP 直接拒连，publishers-platforms.md §网络层现实）。

## 2. 站点勘察摘要

来源：[catalog/or-ms-journals.md](../../catalog/or-ms-journals.md)（INFORMS 系经 Crossref [LIVE] 核实 2026-07-20）+ 待并入出版社勘察 subagent 结果：

- 平台：`pubsonline.informs.org`，**Atypon** 平台族；DOI 前缀 10.1287；
- URL 模式（[LIVE]）：期刊主页 `/journal/{code}`；期目录 `/toc/{code}/{vol}/{issue}`；全期清单 `/loi/{code}`；文章 `/doi/full/10.1287/{code}.xxxx.xxxx`；**PDF `/doi/pdf/10.1287/...`（Atypon 规整直链）**；EPDF `/doi/epdf/...`；
- 反爬：Cloudflare/WAF（[LIVE] 多工具连接失败）——**用户住宅/校园网络 + 登录 session 下可达**（auth_gated 模块假设成立）；
- 认证：机构（Shibboleth/OpenAthens "Institutional Sign In"）+ 个人会员；robots/TDM 明文政策 ⚠ 待 subagent 勘察并入。

## 3. 各阶段实现方案

- **enumerate**：不做（crossref 按 ISSN；INFORMS 刊 Crossref 元数据质量高，卷期结构完整）。
- **resolve_assets**：DOI → `/doi/pdf/10.1287/{suffix}` 直链 AssetPlan（`url_strategy=direct` + cookie session）；entitlement 启发式：GET 文章页含 "Purchase" / "Log in" 面板且无全文节点 → `no_entitlement` 预判。
- **fetch_asset**：首选 HttpFetcher + storage_state 导出的 cookie jar（Atypon PDF 直链通常接受 cookie 直取）；被 WAF 拦截（403/挑战特征）→ 降级 BrowserFetcher 同 context 重试一次 → 仍失败 BLOCKED。`%PDF` 魔数 + >10KB 校验（design/04 §4 文件验证）。
- **healthcheck**：探针=账号页或已知有权 DOI 的 pdf HEAD（302→login 即 EXPIRED；挑战特征即 CHALLENGED）。

## 4. 限速与礼貌

- **串行 1 req/6s + 日配额 200 + 工作时段窗**（auth_gated 全局纪律 design/04 §4；⚠ 待 TDM 政策勘察后若有明文再调并注明出处）；
- 不并行多 session；机构订阅方违规批量下载会连累全校——本平台为 OR 域每日主力，纪律优先级最高；
- robots：遵守（具体条目待勘察并入）。

## 5. 失败模式映射

| 现象 | error_class |
|---|---|
| 302 → login / SSO 页 | `auth_expired` → 整批 BLOCKED |
| 200 但返回购买页 HTML | `no_entitlement`（文件验证兜底捕获） |
| Cloudflare 挑战 | `challenge` → BLOCKED + 冷却 24h |
| PDF <10KB 或非 %PDF | `integrity`(auth_leak) → healthcheck |

## 6. Fixtures 与测试

- **T1 单元**：DOI→pdf/epdf URL 构造；entitlement 启发式判定器（购买页/全文页特征）。
- **T3 fixture**：auth 四件套——已登录文章页 / 未登录跳转 / 无权限购买页 / 挑战页（登录态人工导出脱敏，test-plan §2）。
- **T6 runbook**：真实凭证 login→取 1 篇 MS→过期演练→重登（records 留痕）。
- **验收关联**：AC-4.1（MS 单篇）、AC-4.2（过期检出 ≤20 篇）、AC-4.4（日配额对账）、AC-5.4（POM 不路由到本 adapter）。

## 7. 风险与维护

- Atypon 平台族共性强（SAGE/UChicago 亦是/近似）——PDF 直链模式解析器可做族内基类复用，改版时一处修；
- WAF 策略变化是主要运行风险：canary 每周 healthcheck；连续 CHALLENGED 转人工勘察；
- ⚠ 待办：subagent 出版社勘察返回后并入 robots/TDM 条目，走 review→approved。
