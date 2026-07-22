---
title: 站点勘察：元数据 API（Crossref / OpenAlex / Semantic Scholar）
status: approved
owner: fable5
updated: 2026-07-22
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

---

## 2026-07-22 增量复核（Phase 3 开工前）

> 复核性质：Phase 3 五源 adapter 开工前的 [LIVE] 增量实测（curl 读响应头），基线为本文档与 [aggregators-unpaywall-dblp-core.md](aggregators-unpaywall-dblp-core.md) 的 2026-07-20 勘察。本节为**跨源合并记录**（含 DBLP/Unpaywall/CORE，虽其主条目在姊妹勘察文档——该文档已就 DBLP robots/CORE 数字/Unpaywall version 同步小修）。标记：`[LIVE]`=本次实测；`[DOCS]`=文档页来源。

### 漂移项（原断言 → 新实测 → 影响）

| # | 项 | 原断言（2026-07-20） | 新实测（2026-07-22） | 对详设影响 |
|---|---|---|---|---|
| D1 | DBLP robots/限速 | 建议 1–2s 间隔（FAQ）；search API 作 venue 枚举备选机器接口 | robots.txt `Crawl-delay: 4`；`Disallow: /search,/search/publ,/rec/{xml,bib,ris,nt,rdf}`；`Allow: /db,/pid,/pers,/rec` [LIVE] | 限速升 **≥4s/req**（强约束，非建议）；**DBLP search API（`/search/**`）、per-record `/rec/xml` 列 robots 禁区**——venue 枚举只走 `/db/**` 结构化 XML + `dblp.xml.gz` dump；aggregators 能力面 **去 SEARCH** |
| D2 | S2 无 key 症状 | 无 key 池实测立即 429 | 无 key 单请求被受理返 **404 "not found"**（连已收录知名 DOI 亦 not-found），非 429 [LIVE] | 失败检测口径放宽：**未配置 key → 直接 config，不靠状态码推断**；healthcheck 不以 429/命中判 key 缺失 |
| D3 | CORE 限速 | 免费档 ~5 请求/10s（二手，⚠ 待复核） | token 制：未认证 **100 token/日·10/分**；注册免费 **1,000/日·25/分**；简单查询 1 token、复杂 3–5 [DOCS] | 清 ⚠ 标注填实测数字（CORE 仍 Phase 3 范围外，仅清账；本次 `/docs/v3` 与 `/robots.txt` 均 200，无 Cloudflare 挑战门复现） |
| D4 | OpenAlex 计费可观测量 | 计费制上线；本地 credit 估算护栏 | 匿名 `works?filter=doi:` 仍 **200**（非 401/402/429），`meta.cost_usd:0.0001` 直接可读；匿名未被硬拦 [LIVE] | 新增可用信号：适配器读 `meta.cost_usd` 做**实时预算核销**（优于纯本地估算）；印证计费方向、护栏方案不变 |
| D5 | Unpaywall version 精度 | version=submitted/accepted/published（简写） | 实测全拼 **`publishedVersion`**；`best_oa_location.url_for_pdf` 可为 **null**（landing 有、pdf 无）[LIVE] | Asset.version 用精确串 `submittedVersion/acceptedVersion/publishedVersion`；`url_for_pdf` 空须回退遍历 `oa_locations[]` 找带 pdf 项，否则 gold/publisher 场景漏 URL |

### 无漂移确认（关键断言仍成立）

- **Crossref 全部**：`/journals/{issn}/works` 端点形态、`X-Rate-Limit-Limit:10`/`X-Rate-Limit-Interval:1s` 头、`from/until-pub-date` 过滤、`cursor=*→next-cursor`、`total-results` 计数（QJE 0033-5533 全史 **6655**、2024 年 **46**；`title` 为数组印证 `title[0]` 映射）[LIVE]。
- **DBLP 卷 XML**：`/db/conf/{acr}/{acr}{year}.xml` 字段形态（`inproceedings@key`/`author@pid`/`pages`/`ee@type`/`crossref`/`url`）与 `dblp.xml.gz` dump 入口（`/xml/` 目录列 `dblp.xml.gz(.md5)`/`dblp.dtd`/`release/`）[LIVE]。
- **OpenAlex 改名/计费方向**：`/venues→/sources`、`/concepts→/topics`、key+credit 制方向 [LIVE 印证]。
- **Unpaywall 端点与字段主结构**：`/v2/{doi}?email=`、`is_oa`/`oa_status`(gold 枚举确认)/`best_oa_location`/`oa_locations[]` [LIVE]。

### 执行台账摘要

- **请求预算**：19 / 20（含 6 条 robots.txt：crossref/dblp/openalex/s2/unpaywall/core）。全 GET；UA 统一 `PaperCrawler/0.1 (site survey; personal research; mailto:…)`；无注册/登录/API key；无 token/凭证值入档；`curl -s -i --max-time 30`；最小请求间隔 **2.27s**（≥1.5s 红线全程满足）；无挑战门/验证码（CORE 亦正常 200）。诚实备注：一处 DBLP 请求间隔 3.90s 较发现的 `Crawl-delay:4` **欠 0.1s**（脚本固定 2s sleep + curl 时延凑成，未按现场发现的 crawl-delay 动态调整）——此偏差正是 D1 要求详设固化 **≥4s** 的现场佐证；所有 DBLP 命中路径均属 robots 允许区。
- **robots 复核（5 源）**：仅 DBLP 有实质约束（D1）；`api.crossref.org`/`api.openalex.org`/`api.semanticscholar.org` 的 `/robots.txt` 均 **404**（无限制），`api.unpaywall.org/robots.txt` **422**（网关对所有路径要 email 参数，无 crawl 指令，视作无 crawl 限制）。其余 4 源现行保守限速继续有效。
- **canary DOI 教训**：任务原指定的 canary `10.1257/aer.20221079` **经三源交叉证实不存在**（OpenAlex `count:0`；S2 `not found`；Unpaywall/Heroku 404）。教训：合成/锚点 canary 必须**先实证存在性再入 fixture**，否则站点的 "not-found" 会与"无 key / 端点故障 / 代理归一"混淆而误判——延续 Phase 2「合成假设是盲区源」教训。字段形态验证改用确证收录的金色 OA DOI `10.1371/journal.pmed.0020124`（Ioannidis 2005）复测。
- **一处不确定项**：匿名 `GET /works/https://doi.org/…`（URL-in-path 形态）→ 404，判定**不确定**（代理层很可能把 `https://` 的 `//` 归一为 `/`，到达 OpenAlex 的路径已非法）；不足以证明 OpenAlex 取消 DOI-URL-in-path。可靠匿名测试以 `works?filter=doi:` 形态为准（已 200）；单条 ID 取用建议走 `/works/W…` 或 `filter=doi:`。
