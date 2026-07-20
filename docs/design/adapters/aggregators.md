---
title: Adapter 设计 · 聚合元数据源（Crossref/DBLP/OpenAlex/S2/Unpaywall/CORE）
status: review
owner: fable5
updated: 2026-07-20
---

# Adapter · `aggregators`（六个 aggregator 族 adapter 的合册设计）

> 本文档覆盖 `crossref` / `dblp` / `openalex` / `s2` / `unpaywall` / `core` 六个 adapter——它们是 D-005"元数据主干"的执行者，接口小而同构，合册设计、分别实现。
> 勘察依据：[research/site-survey/metadata-apis.md](../../research/site-survey/metadata-apis.md)、[aggregators-unpaywall-dblp-core.md](../../research/site-survey/aggregators-unpaywall-dblp-core.md)（[LIVE] 2026-07-20）。

## 1. 定位与分工

| adapter | family | capabilities | 分工（D-005 修订版） |
|---|---|---|---|
| `crossref` | aggregator | DISCOVER, ENUMERATE, SEARCH | **期刊主干**：ISSN+日期枚举卷期与 DOI 清单；期刊 watch 增量 |
| `dblp` | aggregator | DISCOVER, ENUMERATE | **会议主干**：conf XML 卷目录；VenueEra 历史回填（D-012） |
| `openalex` | aggregator | ENUMERATE, SEARCH | 补充层：摘要倒排重建、OA 链接、topics（**信用计费 ⚡**） |
| `s2` | aggregator | ENUMERATE, SEARCH | 次级补充：引用图、TLDR、fieldsOfStudy |
| `unpaywall` | aggregator | RESOLVE | OA 副本发现（按 DOI，no_entitlement 兜底） |
| `core` | aggregator | RESOLVE, SEARCH | 次级 OA 兜底（其托管全文可救死链 green OA） |

均无 FETCH（不下载全文；unpaywall/core 产出的 OA URL 交回通用 fetcher）。

## 2. 站点勘察摘要（关键数字，均 [LIVE] 2026-07-20）

- **Crossref**：`api.crossref.org/journals/{issn}/works` + `filter=from-pub-date,until-pub-date`；polite pool（mailto）10 req/s 并发 3，读 `X-Rate-Limit-*` 动态遵守；`rows≤1000`+`offset≤10000`，深翻用 `cursor=*`；增量推荐 `from-index-date`。
- **DBLP**：`dblp.org/db/conf/{acr}/{acr}{year}.xml` 结构化卷目录（含作者 PID、页码、`ee` 官方外链）；conf key 命名不规则（nips2023 404）须从索引页发现；建议 1–2s 间隔，重活用 `dblp.xml.gz` dump（CC0）。
- **OpenAlex ⚡**：2026-02-13 起取消免费 polite pool，改 API key + 信用计费（免费 key 10k credits/天；filter 查询 1 credit、`search=` 10 credits）；`/venues`→`/sources`、`/concepts`→`/topics` 已改名；`from_created/updated_date` 为 Premium 门控。
- **Semantic Scholar**：有 key 统一 1 req/s；无 key 实测即 429——**生产必须申请 key**（申请周期风险 R 类记录）；`venue=` 是模糊匹配，弱于 id 精确。
- **Unpaywall**：`/v2/{doi}?email=`，100k/天；无搜索端点（必须先有 DOI）；独立快照已停发（OpenAlex 吸收）。
- **CORE**：v3 API 免费 key ~5 请求/10s；站点本身有 Cloudflare（API 除外）⚠ 数字实现期复核。

## 3. 各阶段实现方案

- **discover_timeline（crossref）**：`/journals/{issn}/works?rows=0&facet=...` 或按年切片列出 volume/issue 结构 → Issue 行；期刊 watch=`from-index-date` 游标。
- **discover/enumerate（dblp）**：conf 索引页发现实际卷 key → 逐卷 XML 解析 inproceedings（含 `ee` DOI/官方链接回填 identifier）；`paper_count_claimed`=记录数。历史回填一次性批量走 dump 而非在线逐卷（获取策略阶梯）。
- **enumerate_issue（crossref）**：按 (issn, volume, issue) filter 拉 works → PaperStub（字段映射 design/06 §5）；缺摘要不阻塞。
- **补充（openalex/s2）**：ingest 后异步补全：openalex 按 DOI 批查摘要倒排索引重建；s2 按 DOI 批查（`/paper/batch` ≤500）取引用计数/TLDR。均受预算约束（openalex 每日 credit 预算配置；s2 1 req/s）。
- **resolve（unpaywall/core）**：输入 DOI → `best_oa_location.url_for_pdf`（版本 submitted/accepted/published 映射到 Asset.version 并**标注非正式版**）→ AssetPlan(`url_strategy=direct`, auth=none)。触发条件：`no_entitlement` 或 VenueSpec 声明 OA-fallback 优先。
- **search（crossref/openalex/s2）**：订阅 DSL 编译（design/09 §3 能力映射表）。
- **healthcheck**：各源固定已知查询（如 Crossref `/works/10.1016/j.jfineco...`）比对 title。

## 4. 限速与礼貌

| 源 | 默认策略 | 依据 |
|---|---|---|
| crossref | 动态读 X-Rate-Limit 头，上限 5 req/s 起步 | polite pool 官方（勘察实测） |
| dblp | 1 req/2s | 官方 FAQ 建议 1–2s |
| openalex | 按日 credit 预算（默认 2000/天）+ 100 req/s 硬顶下远离 | 计费制官方 |
| s2 | 1 req/s（有 key） | 官方 |
| unpaywall | 5 req/s 且日总量 <100k | 官方 |
| core | 1 req/10s | 免费档官方 ⚠ 复核 |

全部 UA/mailto 表明身份（Crossref polite pool 硬要求，D-014 全局约定）。

## 5. 失败模式映射

| 现象 | error_class |
|---|---|
| 429 / X-Rate-Limit 触顶 | `rate_limited`（读 Retry-After） |
| OpenAlex 402/credit 耗尽 | `rate_limited` 特化：当日预算熔断，明日恢复（报告提示） |
| S2 无 key 429 | `config`（提示申请 key，不重试） |
| DBLP 卷 key 404 | `gone`→回索引页重发现（一次），再失败 `parse` |
| Crossref cursor 过期 | `transient`（重建 cursor 续拉） |

## 6. Fixtures 与测试

- **T1 单元**：各源查询编译器（DSL→URL 参数用例表）；Crossref 字段映射（title[0]/日期族选择）；OpenAlex 倒排索引重建；DOI 规范化（大小写/前缀剥离）。
- **T3 fixture**：每源 ①正常列表页 JSON/XML ②空结果 ③限流响应（429+头）。
- **T4 集成**：分页游标断点续拉（cursor 注入中断）；credit 预算熔断。
- **T5 canary**：QJE 某年 Crossref 篇数已知答案；`conf/icml` 2023 卷 DBLP 记录数。
- **验收关联**：**AC-3.5**（含 QJE/JFE 5 刊零爬取枚举全史）、AC-3.1（跨源合并）、AC-2.1（DBLP 对账口径）。

## 7. 风险与维护

- **OpenAlex 计费制是最大外部变化源**（2026-02 才改制，政策可能继续演化）：预算护栏 + 月度账单核对列入运维；若免费额度进一步收紧，降级路径=Crossref+S2 补摘要；
- S2 key 审批趋严（2024-11 起）：Phase 3 开工前预申请（计划依赖项写入 development-plan Phase 3）；
- DBLP dump 月度 DOI 快照（10.4230/dblp.xml.YYYY-MM-01）为可复现研究提供固定锚——backfill 记录所用快照版本。
