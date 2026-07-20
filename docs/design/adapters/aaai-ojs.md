---
title: Adapter 设计 · AAAI OJS
status: review
owner: fable5
updated: 2026-07-20
---

# Adapter · `aaai_ojs`

## 1. 定位

- **family**: `open_access`
- **服务 venue**：AAAI（1980+）、AIES、HCOMP 等 AAAI 学会 OJS 平台出版物
- **capabilities**: `DISCOVER | ENUMERATE | RESOLVE | FETCH`

## 2. 站点勘察摘要

来源：[research/site-survey/cs-ai-conferences.md](../../research/site-survey/cs-ai-conferences.md)（[LIVE] 2026-07-20）：

- 平台：`ojs.aaai.org`（OJS 开源期刊系统）；`/index.php/AAAI/issue/archive` **默认只显示最新一届**——历史届需翻页参数或按卷直达 ⚠ 分页参数实现期核验；
- 覆盖 1980、1982–2026（个别年份存疑）；宣传站 aaai-{yy}.aaai.org 年年变（VenueEra 记录，D-012）；
- OJS 平台理论上有标准 **OAI-PMH**（`/index.php/AAAI/oai`）⚠ 未逐一验证——若可用则优先于页面解析（获取策略阶梯第 2 级）；
- 免费全文、无防护。

## 3. 各阶段实现方案

- **discover_timeline**：首选 OAI-PMH `ListSets`/`ListRecords`（若验证可用）；fallback：archive 页翻页解析 issue 清单（quirks 记录分页参数）。与 DBLP `conf/aaai` 卷清单交叉对账。
- **enumerate_issue**：首选 OAI-PMH 按 set/日期收割；fallback：issue TOC 页解析（OJS 结构规整：article 卡片含 title/authors/pdf 链接）。AAAI 每届多 track/卷（technical tracks），Issue.label 带 track。
- **resolve_assets**：OJS PDF 路由 `article/view/{id}/{galley}` → `article/download/{id}/{galley}`；`url_strategy=direct`。
- **fetch_asset**：HttpFetcher 直取。
- **healthcheck**：GET archive 页 200；OAI-PMH Identify 200（若启用）。

## 4. 限速与礼貌

- 默认 **1 req/2s，并发 1**（NFR-4；OJS 站点承载力一般，克制并发）；
- robots ⚠ 实现期复核；OAI-PMH 可用时批量走收割协议减少页面请求。

## 5. 失败模式映射

| 现象 | error_class |
|---|---|
| archive 分页参数失效（只见最新届） | `parse`（枚举完整性对账触发：DBLP 数 >> 入库数） |
| OAI-PMH 不可用/异常 XML | `transient`→连续失败降级页面路径 |
| galley 下载 404 | `gone` |

## 6. Fixtures 与测试

- **T1 单元**：OJS URL 构造（view/download/galley）；track 划分映射。
- **T3 fixture**：①archive 页（含分页）②issue TOC 页 ③OAI-PMH ListRecords 样本（若可用）。
- **T5 canary**：AAAI 2024 论文数与 DBLP 对账（±口径差）。
- **验收关联**：AC-2 系；完整性对账 design/08 §6（本 adapter 是"默认只显最新届"陷阱的主要受试者）。

## 7. 风险与维护

- 关键不确定点：OAI-PMH 可用性与 archive 分页参数——列入实现期首项勘察（本文档 status 停在 review 直至核验）；
- OJS 平台升级会改 URL 结构：fixture + canary 覆盖；AAAI-24 起论文量巨大（>2000/届），枚举分页与断点续爬压力测试列入 T4。
