---
title: 运筹 / 管理科学 期刊清单
status: approved
owner: fable5
updated: 2026-07-20
---

# 运筹 / 管理科学（OR/MS）期刊

> 平台映射见 [publishers-platforms.md](publishers-platforms.md)。INFORMS 系数据经 subagent 于 2026-07-20 经 Crossref [LIVE] 核实；`pubsonline.informs.org` 本身部署 Cloudflare/WAF。

## INFORMS 平台（`informs` adapter，DOI 前缀 10.1287）

统一 URL 模式：主页 `/journal/{code}`、目录 `/toc/{code}/{vol}/{issue}`、当前期 `/toc/{code}/current`、全部期 `/loi/{code}`、文章 `/doi/full/10.1287/{code}.xxxx.xxxx`。

| id | 名称 | tier | code | Print ISSN | Online ISSN | metadata_source | auth |
|---|---|---|---|---|---|---|---|
| mnsc | Management Science | T1 | mnsc | 0025-1909 | 1526-5501 | crossref | institutional |
| opre | Operations Research | T1 | opre | 0030-364X | 1526-5463 | crossref | institutional |
| msom | Manufacturing & Service Operations Mgmt | T1 | msom | 1523-4614 | 1526-5498 | crossref | institutional |
| moor | Mathematics of Operations Research | T1 | moor | 0364-765X | 1526-5471 | crossref | institutional |
| ijoc | INFORMS Journal on Computing | T2 | ijoc | 0899-1499 ⚠(存疑,前身ORSA) | 1526-5528 | crossref | institutional |
| mksc | Marketing Science | T2 | mksc | 0732-2399 ⚠核验 | — | crossref | institutional |
| ijaa/orsc… | Organization Science、Information Systems Research 等其他 INFORMS 刊 | T3 | — | ⚠核验 | — | crossref | institutional |

> fulltext_source 全部 = `informs`；metadata_source 全部 = `crossref`（按 ISSN 枚举，避开 Cloudflare 页面）。

## 其他平台的 OR 期刊

| id | 名称 | tier | 平台/adapter | ISSN | DOI 前缀 | auth | 备注 |
|---|---|---|---|---|---|---|---|
| ejor | European Journal of Operational Research | T1 | elsevier_sd | 0377-2217 | 10.1016 | institutional | [LIVE]Cloudflare；RSS `rss.sciencedirect.com/publication/science/03772217`；PII URL |
| pom | Production and Operations Management | T1 | **sage** | 1059-1478 / 1937-5956 | **10.1177** | institutional | [LIVE]确认 SAGE 非 Wiley/INFORMS；`journals.sagepub.com/home/PAO` |
| mp | Mathematical Programming | T1 | springer | 0025-5610 | 10.1007 | institutional | Series A/B |
| annals_or | Annals of Operations Research | T2 | springer | 0254-5330 | 10.1007 | institutional | |
| math_prog_comp | Mathematical Programming Computation | T3 | springer | 1867-2949 | 10.1007 | institutional | |
| informs_ts | INFORMS Transactions on Education（OA） | T3 | informs | — | 10.1287 | none | 开放 |

## 元数据/枚举策略

- 全部走 `crossref` 按 ISSN 枚举卷期与论文清单（FR-02/04），**不爬 pubsonline/sciencedirect 页面做枚举**（Cloudflare + 反爬）；
- 全文（resolve/fetch）走各自 auth_gated adapter，须用户机构订阅；INFORMS/Elsevier/SAGE 均 Cloudflare，优先 API（Elsevier）或登录 session（INFORMS/SAGE）。
- OR/MS 领域作者常在 SSRN/arXiv(math.OC)/个人页自存——无机构订阅时经 Unpaywall/OpenAlex 找 OA 副本（AC-4.3）。

## 待核验清单（实现期用 Crossref/官网确认）

- IJOC 当前印刷 ISSN（Crossref 混杂 0899-1499/1091-9856/2326-3245）；
- Marketing Science、Organization Science 等 T2/T3 刊的 ISSN 与是否纳入范围（按用户实际需求决定 tier）。
