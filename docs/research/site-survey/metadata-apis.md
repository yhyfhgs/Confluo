---
title: 站点勘察：元数据 API（Crossref / OpenAlex / Semantic Scholar）
status: approved
owner: fable5
updated: 2026-07-20
---

# 站点勘察 · 元数据聚合 API

> 来源：subagent 于 2026-07-20 实测（含 live API 调用读响应头）。⚡ 标记的是与训练知识/旧文档冲突的时效性发现。

## ⚡ 关键时效性发现（直接影响 D-005 架构选择）

**OpenAlex 于 2026-02-13 取消免费 polite pool，改为强制 API key + 信用计费制**：
- 无 key：1000 credits/天（$0.10）；免费 key：10000 credits/天（$1.00）；硬顶 100 req/s。
- 计费（实测响应头）：单条 ID 查询 0 credit；filter 列表查询 1 credit；`search=` 全文查询 10 credits；PDF 下载 100 credits。
- `mailto=` 已成 no-op；`/venues`→`/sources` 改名；`/concepts` 弃用转 `/topics`。
- **含义**：旧"OpenAlex 免费 10 万/天 polite pool"知识**已失效**。→ 元数据主干改以 **Crossref（仍免费 polite pool）为第一，OpenAlex 降为补充**（摘要、OA 链接、概念），按信用预算受控使用。

## Crossref（元数据主干首选）

- Base `https://api.crossref.org`；`/journals/{issn}/works`、`/works/{doi}`、`/works`。**168,248 刊**、184.6M works（实测计数）。
- **按 ISSN + 日期枚举期刊全史**（实测可用）：`/journals/{issn}/works?filter=from-pub-date:2024-01-01,until-pub-date:2024-01-31`。日期族含 `from-index-date`（官方推荐用于增量重收割）、from/until-{pub,online-pub,print-pub,deposit,created,posted,accepted}-date。
- 限速（实测响应头，动态）：public pool 5 req/s 并发 1；**polite pool（mailto= 参数或 UA 内 mailto）10 req/s 并发 3**；读 `X-Rate-Limit-*` 头动态遵守，勿硬编码。付费 Crossref Plus 有 SLA 池。
- TDM：`link[]` 字段带 `intended-application`(text-mining/similarity-checking/…)；`has-full-text` ~70.5%、`full-text.application:text-mining` ~38.2%（实测），但**多数需出版商 click-through/订阅**，link 存在≠免费可取。
- 分页：`rows`≤1000 + `offset`≤10000；深翻用 `cursor=*`→`next-cursor`。`rows=0` 只取计数。
- 认证：免费无需。格式 JSON。
- **结论**：期刊 discover/enumerate 的 canonical 源；无关键词需求场景完美（按 ISSN+日期）。

## OpenAlex（补充层，受信用预算约束）

- Base `https://api.openalex.org`；`/works`、`/sources`。
- venue 过滤：`filter=primary_location.source.id:S...` 或 `locations.source.issn:...`；日期 `from/to_publication_date`（免费），`from_created/updated_date`（**Premium 门控**——增量同步受限）。
- OA 字段（实测）：`open_access.{is_oa,oa_status,oa_url}`、`best_oa_location.pdf_url`、`locations[]`——**OA 副本发现能力强于 Crossref**。
- 分页 `per-page`≤200；`cursor=*`→`next_cursor` 无限深。
- **结论**：用于①补 Crossref 缺的摘要（倒排索引重建）；②OA 全文链接发现（与 Unpaywall 并列）；③topic 概念检索。按 credit 计费，watch 高频场景慎用 `search=`（10 credits/次）。

## Semantic Scholar（次级补充）

- Base `api.semanticscholar.org/graph/v1`（+`/datasets/v1`、`/recommendations/v1`）。214M 论文。
- 端点：`/paper/search`（≤1000 结果）、`/paper/search/bulk`（1000/页，token 续，≤10M）、`/paper/batch`（POST ≤500 id）、`/snippet/search`（全文片段）。
- venue 过滤：`venue=` **模糊名/ISO4 缩写 OR 匹配**（非 id 精确，弱于 OpenAlex）；日期 `year=2016-2020`、`publicationDateOrYear`。
- **限速**：有 key 统一 **1 req/s**（全端点）；无 key 池实测立即 429——**生产必须申请 key**，且 2024-11 起免费邮箱/第三方 key 审批趋严，需预留申请周期。
- 稀疏返回：默认只回 paperId+title，需 `&fields=`。全文 `openAccessPdf{url,status,license}`。Datasets 周度快照（当前 release 2026-07-14）含 s2orc_v2 全文（16M）。
- `github.com/allenai/s2-folks` 已 2025-01 归档只读。
- **结论**：补充引用图、TLDR、fieldsOfStudy；venue 归一化差需清洗；bulk 分析用 Datasets 快照。

## 三源分工结论（并入 D-005）

| 用途 | 首选 | 备选 |
|---|---|---|
| 期刊卷期+论文清单枚举 | **Crossref**（ISSN+日期，免费） | OpenAlex（source.id） |
| 会议卷枚举 | **DBLP**（conf XML） | OpenAlex/S2 |
| 摘要补全 | OpenAlex（倒排重建） | S2 |
| OA 全文副本发现 | Unpaywall + OpenAlex best_oa_location | CORE |
| 增量 watch（期刊） | Crossref from-index-date | — |
| 引用/TLDR/领域标签 | Semantic Scholar | OpenAlex topics |

所有源统一：读响应头动态限速；UA 带 mailto；结果按 (scheme,value) 去重入库。
