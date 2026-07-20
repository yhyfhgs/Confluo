---
title: Adapter 设计 · PMLR
status: review
owner: fable5
updated: 2026-07-20
---

# Adapter · `pmlr`

## 1. 定位

- **family**: `open_access`
- **服务 venue**：ICML（2013+/v28+ 系统收录）、AISTATS、COLT（2013+ era）、UAI（2020+ era）、CoRL（2017+）
- **capabilities**: `DISCOVER | ENUMERATE | RESOLVE | FETCH`
- 多段 era 说明：COLT/UAI 早年在其他平台（D-012；era 路由见 design/08 §2），本 adapter 只服务 PMLR 时代。

## 2. 站点勘察摘要

来源：[research/site-survey/cs-ai-conferences.md](../../research/site-survey/cs-ai-conferences.md)（[LIVE] 2026-07-20）：

- 卷页 `proceedings.mlr.press/v{N}/`：静态 HTML，每卷 index 含全部论文条目与 **BibTeX 全量**；
- 单篇：`v{N}/{author}{yy}{suffix}.html`；PDF 直链在条目内（多为 `.../{id}/{id}.pdf`）；
- **卷号↔会议年份无规律**：初始映射表已入 [catalog/cs-ai-conferences.md](../../catalog/cs-ai-conferences.md)（ICML 2024→v235、COLT 2026→v336 等），写入各 VenueSpec `quirks.volume_map`，每年 track 探测新增；
- 全卷列表页 `proceedings.mlr.press/`（含全部 v1–v3xx 标题）是新卷探测源；
- 无认证、无 Cloudflare、无官方 API；AISTATS 2007–2016 部分老卷在旧域 jmlr.org/proceedings ⚠ 实现期核验重定向。

## 3. 各阶段实现方案

- **discover_timeline**：读 VenueSpec `quirks.volume_map` 直接产出 Issue(year→vol)（无网络）；`--refresh` 时抓全卷列表页 diff 出新卷候选（喂给 track，D-012）。
- **enumerate_issue**：抓 `v{N}/` 卷页 → 首选解析页内嵌 BibTeX（字段最全：title/authors/pages/pdf url）→ fallback HTML 条目解析；`paper_count_claimed`=页面条目数。identifier：`pmlr` scheme（`v235/abc24a`）。
- **resolve_assets**：从 bib/条目取 PDF 直链（`url_strategy=direct`）；部分卷有 supplementary（`-supp.pdf`）。
- **fetch_asset**：HttpFetcher 直取 + `%PDF` 校验。
- **healthcheck**：GET 全卷列表页 200 且含 "Volume"。

## 4. 限速与礼貌

- 默认 **1 req/2s，并发 1**（无官方声明 → NFR-4 保守默认）；卷页含全卷数据，一届≈1–2 个请求，天然低频；
- robots ⚠ 实现期复核（勘察未见限制性条目）。

## 5. 失败模式映射

| 现象 | error_class |
|---|---|
| 卷号未在 volume_map（新一届未登记） | `config`（提示走 track 流程） |
| 卷页 404（映射错误/未发布） | `gone` |
| BibTeX 解析 0 条但页面有条目 | `parse`（降级 HTML 解析并标红） |

## 6. Fixtures 与测试

- **T1 单元**：volume_map 路由（含缺年报错）；BibTeX 解析器（转义/Unicode 用例）。
- **T3 fixture**：①一个完整卷页快照 ②bib 解析 golden ③404 卷页。
- **T5 canary**：ICML 2024 (v235) 论文数已知答案；COLT era 路由（AC-8.1 关联）。
- **验收关联**：AC-2 系（pull icml --year 2024）；AC-8.1（COLT 三段 era）。

## 7. 风险与维护

- 主要维护成本=每年 volume_map 追加（track 探测器自动出候选，人工 confirm，D-012）；
- 站点极稳定（静态托管），腐化风险最低档；老卷旧域重定向关系一次性核验后固化在 quirks。
