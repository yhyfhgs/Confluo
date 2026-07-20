---
title: Adapter 设计 · University of Chicago Press
status: review
owner: fable5
updated: 2026-07-20
---

# Adapter · `uchicago`

## 1. 定位

- **family**: `auth_gated`
- **服务 venue**：JPE (Journal of Political Economy)、JPE Micro/Macro（2023 新系列）、Journal of Labor Economics、Journal of Legal Studies 等 UChicago Press 刊
- **capabilities**: `RESOLVE | FETCH`——enumerate 走 crossref（DOI 前缀 10.1086；UChicago 页面难枚举是 design/02 §3"能力缺失即路由"的原型案例）。

## 2. 站点勘察摘要

来源：[research/site-survey/publisher-platforms-econfin.md](../../research/site-survey/publisher-platforms-econfin.md)（[LIVE] 2026-07-20）：

- 域：`www.journals.uchicago.edu`；**⚡ 平台栈已确认 = Atypon Literatum**（[LIVE] 证据：robots.txt 与 Wiley 高度同构 + 同款 Cloudflare 质询模板）→ 与 `informs` 同族，挂 `atypon_base` 基类；
- URL 模式（[LIVE] 实例）：期刊 `/journal/jpe`；卷期 **`/toc/jpe/{year}/{vol}/{issue}`（含年份**，如 `/toc/jpe/1896/4/3`）；文章 `/doi/full/10.1086/734341`（`/doi/abs/` 变体）；**PDF 走 `/doi/epdf/10.1086/{id}` 增强阅读器——本站不暴露纯静态 `/doi/pdf/` 直链**；
- robots.txt（[LIVE]）：AI 点名仅 GPTBot；孤立 `Crawl-delay: 1`（保守遵守）；TDMRep 生效（`tdm-reservation:1`）且显式 Allow 其 well-known 路径；
- 反爬（[LIVE]）：Cloudflare（含按路径动态触发的托管质询）；
- **合规要点**：UChicago 图书馆 TDM 指南明文——允许 text mining，但**自动化批量下载软件须事先向出版社申请许可** → 本 adapter 默认仅按需单篇/小批量（更低日配额），大批量前引导用户联系出版社（journalsupport@press.uchicago.edu）；
- 认证：Atypon 登录体系（Institutional Account 绑 Shibboleth Entity ID，InCommon 联邦）+ 个人订阅；开放内容：abstract 免费，少量 OA。

## 3. 各阶段实现方案

- **resolve_assets**：DOI → `/doi/epdf/10.1086/{suffix}` 阅读器页 AssetPlan（`url_strategy=render_page`——**修正：本站无静态 pdf 直链**，2026-07-20 勘察）；entitlement 启发式同 informs（购买面板特征）。
- **fetch_asset**：**BrowserFetcher 为主**：登录 context 打开 epdf 阅读器 → 嗅探阅读器加载的真实 PDF 资源 URL（同 context 内下载）或 `expect_download`；HttpFetcher 直取仅作尝试性首选（若嗅探出的资源 URL 可带 cookie 复用）。
- **healthcheck**：账号页探针或已知有权 DOI 的 epdf 页判定（登录态 + 阅读器加载成功）。
- 平台基类：**已确认 Atypon** → 与 `informs` 共享 `atypon_base` 解析基类（entitlement 判定/登录墙识别复用；PDF 出口两站不同：informs=静态 `/doi/pdf/`，uchicago=epdf 阅读器——基类留出 `pdf_exit_strategy` 钩子）。

## 4. 限速与礼貌

- **串行 1 req/6s + 日配额 200 + 工作时段窗**（全局纪律）；robots/TDM ⚠ 待并入。

## 5. 失败模式映射

同 informs 映射表（Atypon 族共性）：302→login=`auth_expired`；购买页=`no_entitlement`；挑战=`challenge`；HTML 伪装=`integrity`。

## 6. Fixtures 与测试

- **T1 单元**：DOI→pdf URL 构造；entitlement 判定。
- **T3 fixture**：auth 四件套（JPE 样本）。
- **T6 runbook**：真实凭证 JPE 单篇 + 过期演练。
- **验收关联**：AC-4.1/4.2/4.3；AC-3.5（JPE 可作枚举对照刊之一）。

## 7. 风险与维护

- 首要待办：平台栈核验（Atypon vs Silverchair）→ 决定基类挂载 → 更新本文档转 approved；
- JPE 2023 起衍生 JPE Micro / JPE Macro 两新刊：catalog 登记为独立 venue（各自 ISSN），同 adapter 服务；
- 小平台改版频率低，canary 月检足够（auth 族每周全检时顺带）。
