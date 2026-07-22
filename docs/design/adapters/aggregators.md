---
title: Adapter 设计 · 聚合元数据源（Crossref/DBLP/OpenAlex/S2/Unpaywall/CORE）
status: approved
owner: fable5
updated: 2026-07-23
---

# Adapter · `aggregators`（五源 committed + core 保留的合册实现级详设）

> 本文档覆盖 `crossref` / `dblp` / `openalex` / `s2` / `unpaywall` 五个 **Phase 3 committed** adapter 与 `core`（**Phase 3 范围外，本期不实现**）。它们是 D-005「元数据主干」的执行者，接口小而同构、合册设计、分别实现。
> 勘察依据：[research/site-survey/metadata-apis.md](../../research/site-survey/metadata-apis.md)（[LIVE] 2026-07-20，含 [2026-07-22 增量复核](../../research/site-survey/metadata-apis.md)）、[aggregators-unpaywall-dblp-core.md](../../research/site-survey/aggregators-unpaywall-dblp-core.md)（[LIVE] 2026-07-20，2026-07-22 小修）。
> 接口冻结件依据：[plan/phase3-implementation-plan.md §2](../../plan/phase3-implementation-plan.md)（MergeEngine / VenueSpec 分离语义 / 无 FETCH 契约 / 在线预算）；数据模型：[design/06 §2/§3/§5](../06-data-model.md)。
> **本稿是 Phase 3 五源 adapter 开工的详设硬门禁**（双评审 approved 前 T3~T6 不开工，plan §2 门禁）。

## 1. 定位与分工

| adapter | family | capabilities | 分工（D-005 修订版） | Phase 3 |
|---|---|---|---|---|
| `crossref` | aggregator | DISCOVER, ENUMERATE | **期刊主干**：ISSN+日期枚举卷期与 DOI 清单；期刊 watch 增量（`from-index-date`） | ✅ committed（T3） |
| `dblp` | aggregator | DISCOVER, ENUMERATE | **会议主干**：conf 卷 XML 目录；VenueEra 历史回填（D-012） | ✅ committed（T4） |
| `openalex` | aggregator | （不声明；无 ENUMERATE/SEARCH/FETCH） | 补充层（**enrich 通道**，§5.3）：摘要倒排重建、OA 链接、topics（**信用计费 ⚡**） | ✅ committed（T6） |
| `s2` | aggregator | （不声明；无 ENUMERATE/SEARCH/FETCH） | 次级补充（**enrich 通道**，§5.4）：引用图、TLDR、fieldsOfStudy（**需 key**） | ✅ committed（T6） |
| `unpaywall` | aggregator | RESOLVE | OA 副本发现（按 DOI，`no_entitlement` 兜底） | ✅ committed（T5） |
| `core` | aggregator | （不声明） | 次级 OA 兜底 | ⛔ **Phase 3 范围外，不实现**（§5.6） |

- **能力面修订（2026-07-22，D1）**：`crossref`/`dblp`/`openalex`/`s2` **均不声明 SEARCH**。此前草案给 crossref/openalex/s2 标 SEARCH、给 dblp 隐含 search API——现全部收回：
  - **dblp 去 SEARCH 是合规修订**：DBLP `/search/**` 属 robots 禁区（§3），venue 枚举只走 `/db/**` 卷 XML + dump，**无 search 路径**。
  - **crossref/openalex/s2 去 SEARCH 是接口对齐**：冻结 `SourceAdapter` 协议无 `search()` 方法、Phase 3 无消费方（沿 arxiv.md §1 先例）；订阅命中经 **enumerate + 本地过滤**（`Selector.filter_expr`）达成，DSL→字段级下推统一推迟 Phase 6（AC-6.4）。
  - **openalex/s2 去 ENUMERATE（2026-07-22 修订清单 A-B2）**：二者实为 ingest 后的 DOI 批查富化、非枚举源——capabilities 收回 ENUMERATE，两源均**不含 ENUMERATE/SEARCH/FETCH**；改经 duck-typed `enrich_batch` 可选接口 + `crawler enrich` 驱动（§5.3 机制），**不参与 pull 六阶段主流程、无任何 AC 依赖**（AC-3.5 五刊全史由 crossref 独立完成）。
- 五源**均无 FETCH**（不下载全文，plan §2-3）：unpaywall RESOLVE 产 `AssetPlan(url_strategy="direct", auth_needed="none")` 交通用 fetcher；crossref/dblp 枚举产 PaperStub 流，openalex/s2 经 `enrich_batch` 产 PaperStub 流（§5.3，非枚举）。
- **元数据/全文分工**：五源仅承担元数据与 OA 定位；全文取回归通用 fetcher（Phase 4 认证站点另计）。

## 2. 站点勘察摘要（关键数字）

> 全部 [LIVE] 2026-07-20 + 2026-07-22 增量复核；漂移项见 §9 修订记录。

- **Crossref**（无漂移）：`api.crossref.org/journals/{issn}/works` + `filter=from-pub-date,until-pub-date`；polite pool（UA 内 mailto）实测 `X-Rate-Limit-Limit:10`/`Interval:1s`，动态读头遵守；`rows≤1000`+`offset≤10000`，深翻 `cursor=*`→`next-cursor`；增量 `from-index-date`；`rows=0` 只取计数。QJE 0033-5533 全史 `total-results=6655`、2024 年 46（[LIVE] 2026-07-22）。
- **DBLP**（D1 漂移）：`dblp.org/db/conf/{acr}/{acr}{year}.xml` 结构化卷目录（`inproceedings@key`、`author@pid`、`pages`、`ee@type` 官方外链、`crossref`）；conf key 命名不规则（`nips2023` 404）须从 `/db/conf/{acr}/`（303→index.html）发现；robots **`Crawl-delay:4`**、`/search`+`/rec/xml` **禁区**；重活用 `dblp.xml.gz` dump（CC0，`/xml/` 目录含 `.md5`）。
- **OpenAlex ⚡**（D4 新增观测）：2026-02-13 起取消免费 polite pool，改 API key + 信用计费（无 key 1000 credits/天、free key 10000/天；filter 查询 1 credit、`search=` 10 credits）；`/venues`→`/sources`、`/concepts`→`/topics` 改名；`from_created/updated_date` Premium 门控。**匿名 `works?filter=doi:` 仍返 200 + `meta.cost_usd:0.0001`**（可实时核销预算）。
- **Semantic Scholar**（D2 漂移）：`api.semanticscholar.org/graph/v1`；有 key 统一 1 req/s；**无 key 单请求被受理但返 404 "not found"（连已收录 DOI 亦然），非 429**——生产必须申请 key（R 类风险，申请周期）。
- **Unpaywall**（D5 精度修订）：`api.unpaywall.org/v2/{doi}?email=`，100k/天；无搜索端点（必须先有 DOI）；`version` 全拼 `publishedVersion` 等；`best_oa_location.url_for_pdf` 可为 null。独立快照已停发（OpenAlex 吸收）。
- **CORE**（D3 清账，范围外）：`api.core.ac.uk/v3/`；token 制（未认证 100/日·10/分，注册 1,000/日·25/分）；本次复核无 Cloudflare 挑战门。

## 3. 合规红线（AC-0.5 / AGENTS §6.3）

> robots 复核结论逐源记录（[LIVE] 2026-07-22，六源 `/robots.txt` 实测）。

| 主机 | `/robots.txt` | 结论 | 对本设计的约束 |
|---|---|---|---|
| `api.crossref.org` | 404（JSON `route-not-found`） | 无 robots 限制 | 依动态 `X-Rate-Limit` 头限速（§4） |
| `dblp.org` | 200 | **有实质约束** | 见下框 |
| `api.openalex.org` | 404 | 无 robots 限制 | 依 credit 预算护栏（§4） |
| `api.semanticscholar.org` | 404 | 无 robots 限制 | 依 1 req/s（有 key） |
| `api.unpaywall.org` | 422（网关要 email，无 crawl 指令） | 视作无 crawl 限制 | 依 5 req/s < 100k/日 |
| `api.core.ac.uk` | 200（仅 content-signal 样板，无 UA/Disallow/Crawl-delay） | 无 crawl 指令 | 范围外，不实现 |

> **DBLP robots 红线（D1，高优先）**
> - `Crawl-delay: 4` → **限速 ≥4s/req**（此前草案「1 req/2s」**作废**；依据由「FAQ 建议」升级为「robots 强约束」）。
> - `Disallow: /search`、`/search/publ`、`/rec/{xml,bib,ris,nt,rdf}`、`/db/indices`、`/cgi-bin`、`//` → **DBLP search API 与 per-record `/rec/xml` 列禁区**。
> - `Allow: /db`、`/pid`、`/pers`、`/rec`、`/xml` → 卷目录 `/db/conf/**/*.xml` 与 dump `/xml/dblp.xml.gz` **属允许区**，主枚举机制不受影响。
> - **能力面结论**：`dblp` capabilities **不含 SEARCH**；venue 枚举**只走 `/db/**` 结构化 XML + dump**，绝不经 search API。

- 五源统一 **UA 带 mailto**（Crossref polite pool 硬要求；D-014 全局约定；plan Global Constraints「五源客户端一律带」）。
- 无盗版源、无 CAPTCHA 求解、无凭证入 git（AC-0.1~0.4）；OpenAlex/S2 的 key、Unpaywall 的 email 经 config 注入（家目录/环境变量，仓库外，沿 openreview token 先例）。
- **Unpaywall `email` 日志脱敏缺口（2026-07-22 修订清单 B-B4；T5 先决步骤）**：Unpaywall 把 email 走 URL 查询参数 `?email=<addr>`（§5.5），而 `http.py` 对**每一次**请求（含重定向跳）无条件 `log_event(url=str(url))`、`obslog.redact()` 强制过 `url`——但现有脱敏键正则 `_SENSITIVE_KEYS`（`obslog.py`）**不含 `email` 模式**（OpenAlex `api_key`/S2 `x-api-key` 均能命中、安全脱敏，唯 unpaywall email 会明文写入 jsonl）。**T5 实现顺序硬约束**：先扩展 obslog 脱敏正则（`email=[^&]+` → `email=<redacted>`，即把 `email` 并入 `_SENSITIVE_KEYS`、复用既有 `_QUERY_STYLE` 分支）+ 补脱敏单测，**再**实现 unpaywall adapter。AC-0.4 字面只列 cookie/token 未含 email，故非字面 AC-0.4 违规，但属本详设应给出的「Unpaywall email 凭证纪律」显式条款。

## 4. 限速与预算表（重制，每行带出处）

| 源 | 默认策略 | 出处 | 标注 |
|---|---|---|---|
| crossref | 动态读 `X-Rate-Limit-*` 头，**上限 5 req/s 起步**（远离 polite pool 实测 10/1s） | 响应头 `X-Rate-Limit-Limit:10`/`Interval:1s` | [LIVE] 2026-07-22 |
| dblp | **≥4s/req**，并发 1 | robots `Crawl-delay:4` | [LIVE] 2026-07-22 |
| openalex | **每日 credit 预算 + `meta.cost_usd` 实时核销**（见下）；100 req/s 硬顶下远离 | 2026-02 计费制；响应 `meta.cost_usd` | [LIVE]/[DOCS] |
| s2 | 1 req/s（有 key）；**无 key → `config` 不重试** | 官方（有 key 全端点 1/s） | [DOCS] |
| unpaywall | 5 req/s 且日总量 < 100k | 官方 | [DOCS] |
| core | （范围外）未认证 10/分·100/日；注册 25/分·1,000/日 | [DOCS] token 制 | [DOCS] |

- 每源 `default_rate` 带 `source_note`（`types.RatePolicy` 强制；上表出处入 note）。限速器为 pipeline `acquire_and_wait` 依 `default_rate` 强制 + HttpClient 每请求 `acquire`（沿 arxiv C4 修复先例：adapter 内部翻页每页一请求也走限速，不绕过）。

### OpenAlex 预算实时核销机制（D4，设计伪代码）

> 用响应实报的 `meta.cost_usd` 做**精确核销**，取代「按查询类型本地估算 credit」——不同查询开销不一，服务端实报更准。

```
# 设计伪代码（非可运行）
config: openalex.daily_budget_usd   # 保守默认，如 0.50（≈ 无 key 5000 credits 的一半量级）
state:  <config-home>/state/openalex-budget.json = {"date": "YYYY-MM-DD(UTC)", "spent_usd": float}
        # 家目录、仓库外（AGENTS §6.4）；原子 read-modify-write；date 滚动即重置 spent_usd=0

请求前:  若 state.spent_usd >= daily_budget_usd → 熔断
           raise CrawlerError(rate_limited, detail="openalex daily budget exhausted; resets next UTC day")
响应后:  spent += float(resp.meta.cost_usd or 0); 持久化 state
服务端 402/credit 耗尽: 同样熔断（rate_limited 特化，明日恢复），报告提示
运维:    月度账单核对以 state.spent_usd 累计为准（§10）
```

- **[PENDING·T6 确认]** 状态持久化载体（config-home JSON vs 库内小表）与跨进程并发下的原子性，随 T6 实现细化；Phase 3 最小实现可 run-scoped 累计 + 落 config-home JSON。

## 5. 逐源实现级设计

> 每源覆盖：端点与参数（含分页）/ 请求头 / 响应字段→PaperStub 映射 / 错误映射（对齐 HttpClient 冻结错误类）/ healthcheck / fixture 清单。字段映射目标见 [06 §5](../06-data-model.md)；DOI 一律经 `ids.normalize_doi()`（plan §2-1）。

### 5.1 crossref（期刊主干，T3；AC-3.5 载体）

**端点与参数**

| 用途 | 端点 | 关键参数 |
|---|---|---|
| 枚举卷期/清单 | `GET /journals/{issn}/works` | `filter=from-pub-date:YYYY-MM-DD,until-pub-date:YYYY-MM-DD`；`rows`≤1000；`cursor=*`（深翻） |
| 计数 | 同上 `rows=0` | 只读 `message.total-results`（`paper_count_claimed` 源） |
| 增量 watch | 同上 | `filter=from-index-date:YYYY-MM-DD`（官方推荐重收割游标） |
| healthcheck | `GET /works/{doi}` | 单 DOI，比对 `title[0]` |

- **分页机制（cursor，断点续拉）**：首请求 `cursor=*` → 读 `message.next-cursor`（elasticsearch scroll token）→ 下一请求以该值为 `cursor` → 直至 `items` 为空。`offset` 路径仅用于 `≤10000` 浅翻，深翻一律 cursor。**token 契约**：cursor 值不持久化、不跨任务复用；中断续拉时按 `(issn, from, until)` 窗口**重建** `cursor=*` 从头（幂等，identifier 去重天然保证无重复入库）。

**请求头**：UA `PaperCrawler/<ver> (personal research; mailto:<email>)`（mailto 硬要求→polite pool 10/1s）。

**响应字段 → PaperStub 映射**

| PaperStub 字段 | JSON 路径 | 缺失时行为 |
|---|---|---|
| title | `items[].title[0]`（数组取 [0]） | 空数组 → **跳过该记录 + `parse` 观测告警**（★裁决 2026-07-22：title 是 06 `paper.title NOT NULL`；占位符标题会污染 `title_norm` 弱信号匹配面，对合并引擎是毒数据——宁缺勿污，不占位） |
| identifier(doi) | `items[].DOI` → `normalize_doi()` | 无 DOI 则该 stub 无强合并锚点（罕见于期刊） |
| pub_date | `published-print`→`published-online`→`issued` 的 `date-parts`（首个非空族） | 全缺 → null |
| volume/issue | `items[].volume` / `items[].issue`（文本，容 'S1' 特刊） | null（不阻塞） |
| abstract | `items[].abstract`（JATS，常缺 ~70% 无） | null（06 §5 约定不阻塞入库） |
| authors | `items[].author[]`（`given`/`family`/`sequence`/`ORCID`） | 空 → 无 authorship |
| paper_count_claimed | `message.total-results`（窗口计数） | — |

- source provenance tag = `"crossref"`（§6）。**VenueSpec 分离语义落地**（plan §2-2，crossref 是第一消费者）：`metadata_source=crossref` 的期刊 venue，`issn` 必填（D-015）；registry 校验 metadata_source 值须是已注册 aggregator id。

**错误映射**（对齐 HttpClient 冻结错误类）

| 现象 | error_class | 说明 |
|---|---|---|
| 429 / `X-Rate-Limit` 触顶 | `rate_limited` | 读 Retry-After 入 detail（观测）；pipeline 退避 |
| cursor 过期 / scroll 失效 | `transient` | 按窗口重建 `cursor=*` 续拉 |
| 4xx（filter 语法/ISSN 非法） | `config` | 请求构造缺陷，响亮停机不重试 |
| 5xx | `transient` | 固定退避重试 |
| `total-results>0` 但 items 空解析 0 条 | `parse` | canary 标红 |

**healthcheck**：`GET /works/{固定DOI}` → 比对**空白规整化 title[0]**（非纯计数——`total-results` 随出版增长会漂）。**[PENDING]** 固定 DOI 及其真值实现期捕获（UPDATE_GOLDEN）。

**fixture 清单**：①正常卷期列表 JSON（含 `title[]` 数组、多 author）②空结果（`total-results:0`，合法空）③429 + `X-Rate-Limit-*`/`Retry-After` 头（头随 body 落盘）④cursor 两页续拉（第一页含 `next-cursor`、第二页 items 空）。

### 5.2 dblp（会议主干，T4）

**端点与参数**

| 用途 | 端点 | 说明 |
|---|---|---|
| 卷 key 发现 | `GET /db/conf/{acr}/`（303→`index.html`） | 解析卷链接得实际 key（命名不规则，`nips2023` 404） |
| 枚举卷 | `GET /db/conf/{acr}/{acr}{year}.xml` | 结构化卷目录，**无分页**（逐卷整取一次 XML） |
| 历史回填 | `GET /xml/dblp.xml.gz`（+ `.md5`） | 一次性 dump（CC0）；backfill 走此而非在线逐卷 |

- **分页**：无。dblp 逐卷一次性整取（单卷 XML，规模随卷内 `inproceedings` 数变化；`icml2023.xml` 勘察 [LIVE] 2026-07-20 实测 HTTP 200，字节数未计量）；大规模历史走 dump（获取策略阶梯）。**禁区**：search API、`/rec/xml` 不访问（§3）。

**请求头**：UA + mailto（统一）。

**响应字段 → PaperStub 映射**（`inproceedings` 元素）

| PaperStub 字段 | XML 路径 | 缺失时行为 |
|---|---|---|
| identifier(dblp) | `inproceedings/@key`（如 `conf/icml/AamandACINS23`） | dblp 主锚点，恒有 |
| identifier(doi) | **本条 `inproceedings/ee`**（`@type` 官方外链）中提取 doi.org URL → `normalize_doi()`（**仅 paper 级 ee，见下护栏**） | 非 DOI 外链（如 mlr.press）则不产 doi，仅记 `ee` 入 meta |
| title | `inproceedings/title` | 罕缺 |
| pub_date | `inproceedings/year` | 年级精度 |
| volume/issue | 卷 key（`crossref` 元素如 `conf/icml/2023`） | — |
| abstract | 无（DBLP 无摘要） | 恒 null（补充层补） |
| authors | `author[]`（`@pid` 稳定作者 id） | — |
| pages / meta | `pages`（如 `1-18`）→ `meta.pages` | — |
| paper_count_claimed | 卷内 `inproceedings` 计数 | — |

- **`ee`→DOI 同源护栏（paper 级限定，2026-07-22 修订清单 A-C3）**：`ee` 回填 DOI **仅限 paper 级**——即**该 `inproceedings` 记录自身**的 `ee` 官方外链（与单条论文一对一）。**判定规则**：仅当 `ee` 挂在 `inproceedings` 元素自身、且指向 doi.org 单篇 DOI 时才产 `(doi,…)` identifier；**容器/卷级 DOI 一律不产 identifier**——`proceedings` 卷首 `ee`、全卷式 DOI（如 `10.1007/978-…` 指向整本 LNCS 卷）、以及 `inproceedings/crossref` 所引的 proceedings 容器均**不算**（crossproceedings 引用不产 DOI identifier）。**毒性缘由**：`(scheme,value)` 全局唯一（06 §2），一个容器 DOI 被整卷多篇提取即把全卷论文**误强合并成一条 paper**（错 DOI 比缺 DOI 危害大，延续 neurips「防跨源早合并」告诫）。
- source provenance tag = `"dblp"`（仅 **dblp 写入的字段**带 dblp provenance/优先级）；`ee` 回填的 DOI identifier 是**所有权中性的全局合并锚点**（任何知该 DOI 的源贡献同一锚点，不入字段级优先级表；§6）。

**错误映射**

| 现象 | error_class | 说明 |
|---|---|---|
| 卷 key 404 | `gone` → 回 `/db/conf/{acr}/` 重发现**一次** | 再失败 → `parse`（命名超预期） |
| 429 + Retry-After | `rate_limited` | ≥4s 限速下罕见 |
| 5xx / 连接错 | `transient` | 退避重试 |
| XML 解析失败 / 非法结构 | `parse` | canary 标红 |
| 空卷（合法无记录） | —（非错误） | 解析为空序列正常完成（沿 arxiv `noRecordsMatch` 先例）|

**healthcheck**：`GET /db/conf/icml/icml2023.xml` → 断言 200 + 首条 `inproceedings@key` 存在 + 记录数 ≥ 阈值；比对**空白规整化首条 title**（抗 flake）。

**fixture 清单**：①正常卷 XML（多 `inproceedings`，含 `ee@type`、`author@pid`、`pages`）②空卷 XML（合法空）③404 卷 key 响应 ④`/db/conf/{acr}/` 索引页 HTML（卷发现路径）。

### 5.3 openalex（补充层，T6；信用计费 ⚡）

**补充层 enrich 通道机制（openalex/s2 共用，2026-07-22 修订清单 A-B2）**

openalex/s2 **不承担枚举**（capabilities 已收回 ENUMERATE，§1；两源均不含 ENUMERATE/SEARCH/FETCH），**不参与 pull 六阶段主流程、无任何 AC 依赖它们**（AC-3.5 五刊全史由 crossref 独立完成）。二者是 ingest 之后的**补充富化层**，经独立通道运行：

- **duck-typed 可选接口** `enrich_batch(self, dois: Sequence[str]) -> list[PaperStub]`：**不进** `SourceAdapter` 冻结协议（五方法 `discover_timeline`/`enumerate_issue`/`resolve_assets`/`fetch_asset`/`healthcheck` 保持不变），沿 **`HttpClientConsumer` 可选协议先例**（`adapter.py`：`@runtime_checkable` Protocol 立于冻结协议之外，`bind_http_client` 以 `isinstance` 甄别、不实现者静默跳过）——运行期 duck-typed 甄别，**无该方法的 adapter 不参与 enrich**。
- **驱动路径 = 新 CLI `crawler enrich [--venue ID] [--source openalex|s2]`**：扫 DB 中带 `doi` identifier 的 paper → 分批（openalex 按 `filter=doi:` OR 拼批查、s2 `POST /paper/batch` ≤500 id/批）→ 每命中产 `PaperStub` 经 `MergeEngine.ingest(stub, source=…)` 回注。字段级来源优先级收敛（plan §2-1，openalex/s2 位阶低于 crossref/dblp）**天然实现「补缺不覆盖」**：新值仅写现值为空、或本源优先级严格高于现值来源的字段，不推翻高优先源既有值。
- **预算护栏在 enrich 循环内生效**：openalex 每响应 `meta.cost_usd` 实时核销（§4 熔断），s2 有 key 1 req/s；无 key 的 s2 不发请求（各源 healthcheck 详述）。

**端点与参数**

| 用途 | 端点 | 说明 |
|---|---|---|
| 按 DOI 批查（补摘要/OA） | `GET /works?filter=doi:{doi}`（可 OR 拼多 DOI） | 1 credit/查；读 `meta.cost_usd` 核销 |
| 单条 | `GET /works/W{id}` | 避免 URL-in-path（代理归一风险，§2） |
| 分页 | `per-page`≤200；`cursor=*`→`meta.next_cursor` | 深翻 |

- **角色**：enrich 通道（见本节机制块）——按 DOI 批查重建摘要倒排 + OA 链接，经 `enrich_batch` 产 stub 回注 `MergeEngine.ingest`。受 §4 credit 预算熔断约束。

**请求头**：UA + mailto（mailto 已 no-op，但统一带）；有 key 时 `api_key` 参数注入（config，仓库外）。

**响应字段 → PaperStub 映射**

| PaperStub 字段 | JSON 路径 | 缺失时行为 |
|---|---|---|
| abstract | `abstract_inverted_index`（**倒排索引，ingest 内重建为纯文本**） | null |
| identifier(openalex) | `id`（`W…`，剥 URL 前缀取裸 id） | 恒有 |
| identifier(doi) | `doi`（裸或 `https://doi.org/…`）→ `normalize_doi()` | 无则不产 |
| OA（meta） | `open_access.{is_oa,oa_status,oa_url}`、`best_oa_location.pdf_url` | → `meta` / OA 定位 |
| title / authors | `title` / `authorships[]` | — |

- source provenance tag = `"openalex"`。倒排索引重建（`{token:[pos,...]}`→按 pos 排序拼串）在 ingest 完成（06 §5 约定）。

**错误映射**

| 现象 | error_class | 说明 |
|---|---|---|
| 402 / credit 耗尽 | `rate_limited` **特化** | 当日预算熔断，明日恢复（报告提示；§4 机制） |
| 429 | `rate_limited` | 硬顶远离，罕见 |
| 4xx（filter 语法） | `config` | 请求缺陷 |
| 5xx | `transient` | 退避 |
| 倒排索引畸形 / 解析失败 | `parse` | — |

- **匿名仍 200 并计费计量**（未硬拦）；预算熔断靠 `meta.cost_usd` 累计而非状态码。

**healthcheck**：openalex **匿名即可探测**（1 credit，[LIVE]），有 key/匿名均走固定查询 `GET /works/W{固定id}` → 比对**空白规整化 title**。**canary SKIP 约定**（与 s2 §5.4 统一）：openalex source 未配置/停用时 `raise NotImplementedError("openalex 未配置")` → `crawler canary` 现有语义显示 SKIP（精确复用 `canary.py` 的 `NotImplementedError`→skip 分支，零 canary 改动）。**[PENDING]** 固定 W-id 及真值实现期捕获。

**fixture 清单**：①正常 works 页（含 `abstract_inverted_index`、`meta.cost_usd`）②空结果（`count:0`，如不存在 DOI）③402 credit 耗尽响应 ④倒排索引畸形 → `parse`。

### 5.4 s2（次级补充，T6；需 key）

**端点与参数**

| 用途 | 端点 | 说明 |
|---|---|---|
| 批查（引用/TLDR） | `POST /graph/v1/paper/batch`（body ≤500 id，`&fields=`） | 主批量通道 |
| 单条 | `GET /graph/v1/paper/DOI:{doi}?fields=…` | 稀疏返回，须显式 `fields` |

- **角色**：enrich 通道（见 §5.3 机制块）——按 DOI `POST /paper/batch` 补引用计数/TLDR/fieldsOfStudy，经 `enrich_batch` 产 stub 回注 `MergeEngine.ingest`。**生产必须 key**（无 key 实质不可用，D2）。

**请求头**：UA + mailto；有 key 时 `x-api-key` 头注入（config，仓库外）。

**响应字段 → PaperStub 映射**

| PaperStub 字段 | JSON 路径 | 缺失时行为 |
|---|---|---|
| identifier(s2) | `paperId` | 恒有（命中时） |
| identifier(doi) | `externalIds.DOI` → `normalize_doi()` | 无则不产 |
| citations（meta） | `citationCount` → `meta` | null |
| tldr（meta） | `tldr.text` → `meta` | null |
| fieldsOfStudy（meta） | `fieldsOfStudy` / `s2FieldsOfStudy` → `meta` | null |
| OA（meta） | `openAccessPdf.{url,status,license}` | null |

- source provenance tag = `"s2"`。

**错误映射（D2 口径修订）**

| 现象 | error_class | 说明 |
|---|---|---|
| **未配置 key** | enrich 请求路径→`config`（**直接判定，不靠状态码推断**）；healthcheck 路径→`NotImplementedError`（→canary SKIP，见 healthcheck） | 无 key 现症状=404 "not found"（连已收录 DOI 亦然），**不是 429**；enrich 路径不重试、提示申请 key |
| 有 key 超速 429 | `rate_limited` | 1 req/s |
| 404 not-found（有 key，真缺） | `gone`（单条场景） | 与「无 key」区分：靠 **key 存在性预判**，非状态码 |
| 4xx（fields 语法） | `config` | — |
| 5xx | `transient` | — |

**healthcheck**：**无 key → `raise NotImplementedError("s2 key 未配置")`** → `crawler canary` 现有语义显示 SKIP（精确复用 `canary.py` 的 `NotImplementedError`→skip 分支，零 canary 改动；**纠正原「无 key→config」**——config 会被 canary 判为 unhealthy、每周误触 test-plan §4「连续 2 周 DRIFT→降级」误报，评审 B-C3）。**有 key** → `GET /paper/DOI:{固定DOI}?fields=title` 比对规整化 title，不靠 429/404 判活。**[PENDING]** 固定 DOI 真值实现期捕获（需 key）。

**fixture 清单**：①正常 batch 响应（`citationCount`/`tldr`/`fieldsOfStudy`）②未命中（404 "not found"）③有 key 429 → `rate_limited` ④无 key 场景（合成，验证「不靠状态码判 key 缺失」路径）。

### 5.5 unpaywall（OA 副本发现，T5；RESOLVE）

**端点与参数**

| 用途 | 端点 | 说明 |
|---|---|---|
| 单 DOI resolve | `GET /v2/{doi}?email=<addr>`（**email 必填**，网关 422 兜底） | 无 key；勘察 [LIVE] 2026-07-22 已验证端点 |

- **无搜索端点**：必须先有 DOI 清单（来自 crossref/dblp）。**触发条件**：`no_entitlement` 兜底，或 VenueSpec 声明 OA-fallback 优先。

**请求头**：UA + mailto（email 走查询参数 `?email=`）。

**响应字段 → AssetPlan / Asset 映射（D5）**

| 目标 | JSON 路径 | 规则 |
|---|---|---|
| Asset.version | `best_oa_location.version` | **精确串** `submittedVersion`/`acceptedVersion`/`publishedVersion`（全拼）；submitted/accepted **标注「非正式版」** |
| AssetPlan.url | `best_oa_location.url_for_pdf` | 非空 → `AssetPlan(kind=pdf, url_strategy="direct", auth_needed="none")` |
| **回退链**（`url_for_pdf` 为 null） | 遍历 `oa_locations[]` 找首个带 `url_for_pdf` 的项 | 命中 → 产 AssetPlan；对应 version 同法映射 |
| **landing 兜底** | `best_oa_location.url_for_landing_page` | **仅记 `meta.oa_landing_url`，不产 AssetPlan**（无 PDF 直链不下载 landing 页） |
| OA 状态（meta/报告） | `is_oa`、`oa_status`(gold/green/hybrid/bronze/closed) | 命中率报告统计维度 |

- unpaywall **不产 identifier**（RESOLVE only，以输入 DOI 为键）；不参与字段级来源优先级收敛。
- **OA 命中率报告**（T5 DoD 第二项）：DOI 清单输入 → **逐 DOI `GET /v2/{doi}` 循环**（**无批量端点**——`POST /v2/dois` 从勘察到详设全程未 [LIVE] 验证响应结构，B-B3 裁决删除；单查形态勘察 [LIVE] 已验证；5 req/s 限速下 100 DOI ≈ 20s，报告场景可行）→ 聚合 `{总数, is_oa 数, 各 oa_status 计数, 有 pdf 直链数, 仅 landing 数}` 的 markdown 表。

**错误映射**

| 现象 | error_class | 说明 |
|---|---|---|
| 422（缺 email） | `config` | 请求构造缺陷（我方漏注入 email） |
| 404（DOI 不存在） | `gone` | 该 DOI 无 unpaywall 记录 |
| 429 | `rate_limited` | 5 req/s |
| 5xx | `transient` | — |
| JSON 解析失败 | `parse` | — |

**healthcheck**：`GET /v2/{固定gold-DOI}?email=` → 比对 `is_oa`+`oa_status`。锚点 `10.1371/journal.pmed.0020124` → `is_oa:true`、`oa_status:"gold"`（[LIVE] 2026-07-22）。

**fixture 清单**：①正常 OA 响应（gold、`url_for_pdf:null`、`version:"publishedVersion"`、`oa_locations` 多条 — 触发回退链）②closed（`is_oa:false`，无 AssetPlan）③404 坏 DOI ④422 缺 email。

### 5.6 core（Phase 3 范围外，不实现）

> **本节仅存档口径，Phase 3 不落 adapter**（development-plan 五源字面；plan「范围只减不增」）。

- v3 端点族：`/v3/search/works`、`/v3/works/{id}`、`/v3/works/{id}/download`、`/v3/recommend`；查询语言 `field:value`（`doi:`/`title:`/`fullText:`/`yearPublished:`）。
- 限速 token 制（未认证 100/日·10/分；注册 1,000/日·25/分；简单 1 token、复杂 3–5）。定位：次级 OA 兜底（Unpaywall 之后），其直接托管全文可救活死链 green OA。
- 若未来纳入：capabilities `RESOLVE, SEARCH`；实现前用真 key 复核限速与 Cloudflare 态势。

## 6. 与合并引擎的交互面（plan §2-1 / 06 §3）

> 五源产出的 PaperStub 汇入 `MergeEngine.ingest(stub, source=…)`（plan §2-1 冻结）。本节冻结 adapter 侧的 identifier scheme、source 标记、DOI 归一入口，与 unpaywall 的 Asset.version 映射。

**identifier scheme 命名（对齐 06 §2 开放枚举 `doi|arxiv|…|openalex|s2|dblp|…`）**

| 源 | 产出 identifier | value 归一 |
|---|---|---|
| crossref | `(doi, DOI)` | `normalize_doi()` |
| dblp | `(dblp, @key)` + `(doi, ee 中 DOI)` | key 原样；DOI 经 `normalize_doi()` |
| openalex | `(openalex, W…)` + `(doi, doi)` | W-id 裸值；DOI 经 `normalize_doi()` |
| s2 | `(s2, paperId)` + `(doi, externalIds.DOI)` | paperId 原样；DOI 经 `normalize_doi()` |
| unpaywall | 无（RESOLVE，以输入 DOI 为键） | — |

- **DOI 归一唯一入口**：所有 DOI 写入前经 `ids.normalize_doi()`（小写化、剥 `https://doi.org/`、`doi:` 前缀）——crossref/unpaywall/dblp ee 回填/openalex/s2 共用（plan §2-1）。identifier `(scheme,value)` 全局唯一 → 天然强合并锚点（AC-3.1）。
- **identifier 产出的「同源著作」判界（2026-07-22 修订清单 A-C4，评审 A 专项论证）**：identifier 产出由**是否指称同一著作**（same-work）支配，**非**由「谁铸造/注册该 id」支配。dblp `inproceedings` 记录**即该已刊会议论文本身**、其 `ee` 官方 doi.org 链接是**该同一论文自己的 DOI**（同源）→ 产 `(doi,…)` identifier 作跨源合并锚点（AC-3.1 必要条件）；区别于 arxiv `journal_ref/doi`、neurips 内嵌 arxiv/openreview id——那些指向**异源著作**（预印本 DOI 指其已刊正式版，两条 paper 经 `preprint_of` 相连而不合并，D-007）→ **仅入 `meta`、不产 identifier**（neurips「防跨源早合并」先例）。dblp 虽非 DOI 注册本源（Crossref/DataCite 代出版社铸造），但 `ee` 是其人工策展的同源身份断言 → 产锚点与该先例不冲突。
- **`PaperStub.meta` 值类型冻结（2026-07-22 修订清单 A-C1）**：`meta: tuple[tuple[str, str], ...]`（types.py 冻结，值须 `str`）——非字符串结构一律 `json.dumps` 序列化后入 meta（s2 `citationCount`(int)/`fieldsOfStudy`(list)/`openAccessPdf`(dict)、openalex OA 结构等），消费方自行 `json.loads` 反序列化；标量可 `str()`，结构必 `json.dumps`。

**source 优先级标记（字段级来源收敛，AC-3.4 基石）**

- 各源写字段时携带 provenance tag：crossref→`"crossref"`、dblp→`"dblp"`、openalex→`"openalex"`、s2→`"s2"`。unpaywall 不写元数据字段（只产 Asset），不入此收敛。
- **字段级来源优先级（plan §2-1 / D-021 已冻结，★W0 仲裁 2026-07-22）**：`official > crossref > dblp > openalex > s2 > heuristic`（**已含 dblp 级**）。理由（D-021 决策 3）：Crossref 为 DOI 注册源头（出版社存缴）元数据居先；DBLP 人工策展（CC0）质量高于 openalex/s2 机器聚合层，低于出版社直连 crossref。dblp（会议主干、paper 级 `ee` 回填 DOI）的字段据此有确定优先级——此前草案「未列 dblp／[UNRESOLVED] 待仲裁」的表述**已作废**（该位次已由 D-021 定裁，位置与原建议一致）。

**VenueSpec 分离语义**（plan §2-2，纯附加）：`metadata_source: str | None`（默认 None=沿用 adapter 自身；对齐 plan §2-2——现冻结 types.py 为必填 `str`，本字段松弛为可选 `str | None` 属有意的纯附加变更）；声明值须是已注册 aggregator id；期刊 kind + `metadata_source=crossref` 时 issn 必填。

## 7. D-019 锚点表（外源比对类验收，五源各 ≥1 行）

> 沿 D-019 模式：锚点快照人工核准入 `tests/fixtures/<src>/…-anchor.json`，验收判定=系统输出与快照全等（UPDATE_GOLDEN 纪律 + records 留痕）。种子值 [LIVE] 直接入表，未测项留 [PENDING] 结构。

| 源 | 锚点定义 | 种子值 | 状态 |
|---|---|---|---|
| crossref | `{issn, total_all, total_year:{Y:n}, sample_doi, note}` | QJE `0033-5533`：`total_all=6655`（T7 实跑 `crawler timeline qje` 逐年 facet 计数之和 = 6655，= 锚点下限，2026-07-23；随出版增长故验收判据为 `≥6655`）、`total_2024=46`（闭合年，稳定，实跑一致）；`sample_doi=10.1038/nature14539`（= §5.1 healthcheck 固定 DOI）→ 规整化 `title[0]=`**"Deep learning"**（[LIVE] 2026-07-23 捕获，`_HEALTHCHECK_TITLE` UPDATE_GOLDEN 候选）；`note`=「total_all 随出版增长、非稳定锚；验收以 total_2024 闭合年为准」 | [LIVE] 2026-07-23（T7 AC-3.5 实跑；`sample_doi` title 真值已捕获，adapter golden 化留 UPDATE_GOLDEN）|
| dblp | `{slug, year, record_count, note}` | `conf/icml/icml2023`：`record_count=1828`（T7 实跑 `parse_volume_xml` 卷内 `inproceedings` 计数 = 1828，2026-07-23；首条 key `conf/icml/AamandACINS23`；与审查实测一致）；`note`=「真实届记录数随年份增长，本行锚定 icml2023 单卷」 | [LIVE] 2026-07-23 |
| openalex | `{filter, count, cost_usd, note}` | `works?filter=doi:10.1257/aer.20221079`→`count:0`（**负锚点**，该 DOI 三源证实不存在）、`cost_usd:0.0001`；**正锚点** [PENDING]（需一确证收录 DOI 的 count） | 部分 [LIVE] |
| s2 | `{query, expected_present, note}` | `DOI:{固定DOI}`：有 key→命中；无 key→404 not-found。真值 **[PENDING]**（需 key 验证） | [PENDING] |
| unpaywall | `{doi, is_oa, oa_status, oa_locations_n, version, url_for_pdf, note}` | `10.1371/journal.pmed.0020124`：`is_oa:true`、`oa_status:"gold"`、`oa_locations:4`、`version:"publishedVersion"`、`url_for_pdf:null` | [LIVE] 2026-07-22（2026-07-23 T7 复核：五字段全一致，`test_unpaywall_smoke` PASS）|

- dblp 锚点表**同时服务 AC-2.1 及 Stage B 各 adapter 的外源比对**（D-019：DBLP 卷数是 iclr/pmlr/cvf/acl/neurips/aaai 完整性验收的外源真值提供者）。

## 8. 测试与验收

- **T1 单元**：
  - 各源 **DSL→URL 编译**用例表（filter 参数拼装：crossref 日期族、openalex `filter=doi:` OR 拼、s2 `fields=`、dblp 卷 URL 构造）。
  - **字段映射**：crossref `title[0]`/日期族选择/author 结构；openalex 倒排索引重建；dblp `ee` DOI 提取（doi.org vs 非 DOI 外链）；unpaywall version 精确串 + `url_for_pdf` null 回退链。
  - **DOI 规范化**：`normalize_doi()` 大小写/前缀剥离/边界矩阵。
- **T3 fixture（逐 error_class 对应表，2026-07-22 修订清单 B-C4）**：下表把每源 §5 错误映射的每个 error_class 落到覆盖它的 fixture（①②③④ = §5 各源已列清单，⑤⑥⑦ = 据本表**需补**的合成件）。真实响应脱敏，golden 重录 `UPDATE_GOLDEN=1` + 人工过目（plan fixture 纪律）；429 响应头随 body 落盘。**全部 error_class 均可离线合成覆盖**——无 live-only、无法离线覆盖的类（4xx/5xx/429/parse 皆可构造响应件）。「≥4」是**下限非上限**（test-plan §6：每个 FAILED error_class ≥1 用例证明触发路径；已实现 pmlr/aaai/acl 目录普遍 10+ 件）。

  | 源 | error_class（§5 映射行） | 覆盖 fixture | 备注 |
  |---|---|---|---|
  | crossref | rate_limited (429) | ③ 429+`X-Rate-Limit`/`Retry-After` | 头随 body 落盘 |
  | crossref | transient (cursor 过期) | ④ cursor 续拉（+过期 cursor 变体） | 窗口重建路径 |
  | crossref | config (4xx filter/ISSN) | ⑤ 4xx 非法 filter/ISSN | 合成需补 |
  | crossref | transient (5xx) | ⑥ 5xx | 合成需补 |
  | crossref | parse (total>0 items 空) | ⑦ total-results>0 但 items 空 | 合成需补，canary 标红 |
  | crossref | 正常/空（非错误） | ① 正常卷期列表 / ② 空结果 (total:0) | — |
  | dblp | gone→parse (404 卷 key) | ③ 404 卷 key + ④ 索引页 HTML | 404→重发现一次→再失败 parse |
  | dblp | rate_limited (429) | ⑤ 429+Retry-After | 合成需补（≥4s 下罕见） |
  | dblp | transient (5xx/连接错) | ⑥ 5xx | 合成需补 |
  | dblp | parse (XML 非法结构) | ⑦ 畸形 XML | 合成需补，canary 标红 |
  | dblp | 空卷/正常（非错误） | ② 空卷 XML / ① 正常卷 XML | — |
  | openalex | rate_limited 特化 (402 credit 耗尽) | ③ 402 credit 耗尽 | 预算熔断 |
  | openalex | rate_limited (429) | ⑤ 429 变体 | 合成需补（硬顶远离） |
  | openalex | config (4xx filter) | ⑥ 4xx filter 语法 | 合成需补 |
  | openalex | transient (5xx) | ⑦ 5xx | 合成需补 |
  | openalex | parse (倒排畸形) | ④ 倒排索引畸形 | — |
  | openalex | 正常/空（非错误） | ① 正常 works / ② 空结果 count:0 | — |
  | s2 | config (无 key，enrich 路径) | ④ 无 key 场景（合成） | 验证不靠状态码判 key 缺失；healthcheck 路径 `NotImplementedError`（§5.4） |
  | s2 | rate_limited (有 key 429) | ③ 有 key 429 | 1 req/s |
  | s2 | gone (404 有 key 真缺) | ② 未命中 404 "not found" | 靠 key 存在性预判区分 |
  | s2 | config (4xx fields 语法) | ⑤ 4xx fields | 合成需补 |
  | s2 | transient (5xx) | ⑥ 5xx | 合成需补 |
  | s2 | 正常（非错误） | ① 正常 batch | — |
  | unpaywall | config (422 缺 email) | ④ 422 缺 email | 我方漏注入 |
  | unpaywall | gone (404 DOI 不存在) | ③ 404 坏 DOI | — |
  | unpaywall | rate_limited (429) | ⑤ 429 | 合成需补（5 req/s） |
  | unpaywall | transient (5xx) | ⑥ 5xx | 合成需补 |
  | unpaywall | parse (JSON 失败) | ⑦ 畸形 JSON | 合成需补 |
  | unpaywall | 正常/closed（非错误） | ① 正常 OA (gold, 回退链) / ② closed | — |
- **T4 集成**：①crossref **cursor 断点续拉**（注入 `next-cursor` 中断 → 重建窗口续拉，无重复无遗漏）②openalex **credit 熔断**（`meta.cost_usd` 累计触顶 → `rate_limited` 特化）③dblp 404→索引重发现一次。
- **T5 在线冒烟**（每源 `MAX_REAL_REQUESTS ≤ 5`，Phase 总预算 ≤100，plan §2-4）：
  - crossref：healthcheck 1 + 单窗口枚举首页 1（≤2）。
  - dblp：单卷 XML 1（≥4s 间隔）（≤1）。
  - openalex：单 filter 查 1（读 `cost_usd`）（≤1）。
  - s2：**按 key 存在性 skip**（无 key → pytest `skipif` 不发请求；canary 层则 `NotImplementedError`→SKIP，§5.4；诚实标注）（≤1）。
  - unpaywall：单已知金色 DOI 1（≤1）。
  - 每源 `tests/online/test_<src>_smoke.py`（`-m online`，socket 禁网护栏外）。
- **AC 对账口径**：
  - **AC-3.5**（五刊零爬取枚举全史）：crossref T3+T7；篇数与 `paper_count_claimed`（=`total-results`）差异逐刊解释入验收记录。
  - **AC-3.1**（跨源强合并）：同 DOI 经 arXiv 与 crossref 两路注入 → 1 paper ≥2 identifier（T1 + T3 双路实数据）。
  - **AC-3.4**（字段级来源收敛，顺序无关）：判定 owner 在 **T1**（Hypothesis 属性测试 **≥200 examples**，多源随机顺序注入 → canonical dump 逐行一致，plan §4 T1）；本文档仅负责各源产出**正确标注 provenance 的 PaperStub 流**（§6 优先级表），不承载 AC-3.4 判据本身。
  - **AC-2.1**（DBLP 对账口径）：dblp 锚点表为 iclr 等 timeline 完整性的外源真值（D-019 传递）；本源提供锚点，AC-2.1 判定在 openreview/各 Stage B adapter。
- 聚合源解析/映射模块覆盖 ≥90%（对齐 adapter 解析器纪律，plan 门禁）。

## 9. 修订记录（2026-07-22 增量复核落地，doc-conventions §5）

| # | 日期 | 修订 | 依据 |
|---|---|---|---|
| 1 | 2026-07-22 | **dblp 限速 `1 req/2s` → `≥4s/req`**（robots `Crawl-delay:4` 强约束，非 FAQ 建议） | 增量复核 D1 [LIVE] |
| 2 | 2026-07-22 | **dblp 能力面去 SEARCH**；`/search/**`、`/rec/xml` 声明 robots 禁区；venue 枚举只走 `/db/**` XML + dump | 增量复核 D1 [LIVE] |
| 3 | 2026-07-22 | crossref/openalex/s2 **收回 SEARCH**（接口对齐：协议无 `search()`、Phase 3 无消费方；沿 arxiv.md §1 先例） | plan §2 接口冻结 + arxiv 先例 |
| 4 | 2026-07-22 | **S2 无 key 检测口径**：未配置 key 直接 `config`，不靠状态码（现症状 404 not-found，非 429）；healthcheck 按 key 存在性预判 | 增量复核 D2 [LIVE] |
| 5 | 2026-07-22 | **OpenAlex `meta.cost_usd` 实时预算核销机制**新增（取代纯本地 credit 估算）；402 与预算熔断统一 `rate_limited` 特化 | 增量复核 D4 [LIVE] |
| 6 | 2026-07-22 | **Unpaywall version 精确串** `publishedVersion` 等 + `url_for_pdf` 空值回退链（遍历 `oa_locations[]`；landing 仅记 meta） | 增量复核 D5 [LIVE] |
| 7 | 2026-07-22 | **CORE ⚠ 清账**：token 制数字替换「~5/10s」；显式标注 Phase 3 范围外不实现 | 增量复核 D3 [DOCS] |
| 8 | 2026-07-22 | 全文从 80 行合册草案扩写为实现级详设（逐源端点/映射/错误/healthcheck/fixture + 合并交互面 + D-019 锚点 + 测试验收） | 本次 W0 扩写任务 |
| 9 | 2026-07-22 | **双评审 REJECT → 修订清单落地**：§6/§10 引 D-021 清除假 [UNRESOLVED] 优先级、改用冻结表 `official>crossref>dblp>openalex>s2>heuristic`（A-B1/B-B2）；openalex/s2 **收回 ENUMERATE** + 补 duck-typed `enrich_batch` 可选接口与 `crawler enrich` 驱动通道（A-B2）；unpaywall **删 `POST /v2/dois`**、OA 报告改**单 DOI GET 循环**（B-B3）；§3 补 unpaywall email 日志脱敏 **T5 先决条款**（B-B4）；补 `meta` str→str 约定（A-C1）/dblp `ee` **paper 级护栏**（A-C3）/**同源著作**判界（A-C4）/`auth_needed` 勘误（A-C5）/删无源 ~519KB（A-C6）；§8 补 **AC-3.4** 行（B-C1）+ **逐 error_class fixture 表**（B-C4）+ 总预算 ≤100 同步；§5.3/5.4 healthcheck **`NotImplementedError`→canary SKIP**（B-C3）；§7 crossref 锚点补 schema（B-C5） | 双评审 REJECT + controller 裁决 |
| 10 | 2026-07-23 | **§7 D-019 锚点 T7 实跑回填**：crossref QJE `total_all=6655`(=下限) / `total_2024=46` 实跑确认、`sample_doi=10.1038/nature14539` title 真值 **"Deep learning"** 捕获（UPDATE_GOLDEN 候选）；dblp `icml2023.record_count=1828` [LIVE] 落定（首 key `conf/icml/AamandACINS23`）；unpaywall 金锚点五字段复核一致。§10 [UNRESOLVED] 相应销项。证据：[records/2026-07-23-ac35-acceptance.md](../../testing/records/2026-07-23-ac35-acceptance.md) | T7 AC-3.5 在线实跑（授权真实网络，33/50 请求台账） |

## 10. 风险与维护

- **OpenAlex 计费制是最大外部变化源**（2026-02 才改制，政策可能续演）：预算护栏（`meta.cost_usd` 实时核销）+ 月度账单核对（以 `state.spent_usd` 累计为准）列入运维；免费额度进一步收紧则降级路径 = Crossref + S2 补摘要（plan §6 风险①，设计已备）。
- **S2 key 审批趋严**（2024-11 起）：Phase 3 开工前预申请（plan 依赖项）；未到则在线层 skip 门控（不阻塞离线 DoD）。
- **DBLP dump 月度 DOI 快照**（`10.4230/dblp.xml.YYYY-MM-01`，Dagstuhl DROPS）为可复现研究提供固定锚——backfill 记录所用快照版本 + md5 校验。
- **canary 存在性纪律**：合成/锚点 canary 必须先实证存在性（Phase 2「合成假设是盲区源」+ 本次 `10.1257/aer.20221079` 三源不存在教训）。
- **[UNRESOLVED] 残留**：①openalex/s2 healthcheck 固定样本真值（§5，[PENDING] 需 credit/key）②openalex 正锚点、s2 需 key 锚点（§7 [PENDING]）③OpenAlex 预算状态持久化载体（§4，T6 确认）。（原「dblp 字段级优先级位次」已由 **D-021 定裁**移除；**crossref healthcheck 真值 "Deep learning" 与 dblp icml2023=1828 已由 T7 AC-3.5 实跑捕获销项**——2026-07-23 §9 修订 #10，crossref adapter `_HEALTHCHECK_TITLE` golden 化留 UPDATE_GOLDEN，非本次范围。）
