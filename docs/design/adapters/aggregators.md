---
title: Adapter 设计 · 聚合元数据源（Crossref/DBLP/OpenAlex/S2/Unpaywall/CORE/RePEc）
status: implemented
owner: fable5
updated: 2026-07-27
---

# Adapter · `aggregators`（五源 committed + core/repec 保留的合册实现级详设）

> 本文档覆盖 `crossref` / `dblp` / `openalex` / `s2` / `unpaywall` 五个 **Phase 3 committed** adapter 与 `core`（**Phase 3 范围外，本期不实现**）、`repec`（**enrich 通道，Phase 7 T8 落地**，§5.7；契约冻结见 [D-035](../../plan/decision-log.md)）。它们是 D-005「元数据主干」的执行者，接口小而同构、合册设计、分别实现。
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
| `repec` | aggregator | （不声明；无 ENUMERATE/SEARCH/FETCH） | enrich 通道（§5.7）：**JEL 分类** + wp↔published 版本关联；bulk 快照本地 join、**零网络** | 🕓 **Phase 7 T8**（D-027→D-035） |

- **`aggregator-enrich` 是档位描述、不是字段**：`family` 字段值域只有 `open_access` / `auth_gated` / `aggregator` 三枚（`tests/unit/test_adapter_loading.py::VALID_FAMILIES`），repec 与 openalex/s2 一样 `family = "aggregator"`；D-027 与本文档所称 `role: aggregator-enrich` 是**对其分工档位的文字描述**（"aggregator 里只做 enrich、不做枚举那一档"），registry/types 中**并无 `role` 字段**——registry role 声明式改造挂 P8（D-035 决策 1），勿据此措辞误以为已有该字段。

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

**限速与 timeline 粒度实现落地（T3，补记）**：动态读取 `X-Rate-Limit-*` 响应头在冻结 `HttpClient.get_bytes`（只回 body、不暴露响应头）下不可达，`default_rate` 落地为**静态 5 req/s 保守上限 + 429→`rate_limited` 退避**（Retry-After 读入 detail；★裁决 2026-07-22，T3）；`discover_timeline` **粒度=出版年**——Crossref `filter` 无卷期维度，volume/issue 不作枚举键，经 works 记录字段读入 meta（★裁决）。

**响应字段 → PaperStub 映射**

| PaperStub 字段 | JSON 路径 | 缺失时行为 |
|---|---|---|
| title | `items[].title[0]`（数组取 [0]） | 空数组 → **跳过该记录 + `parse` 观测告警**（★裁决 2026-07-22：title 是 06 `paper.title NOT NULL`；占位符标题会污染 `title_norm` 弱信号匹配面，对合并引擎是毒数据——宁缺勿污，不占位） |
| identifier(doi) | `items[].DOI` → `normalize_doi()` | 无 DOI → **跳过该记录**并计 `skipped_doiless` 观测（PaperStub 需 ≥1 identifier，无锚点无身份；罕见于期刊——实现口径 2026-07-23 终检对齐） |
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

**枚举卷响应 schema（双形态，回填 2026-07-26；事实来源=`adapters/dblp/parse.py` 模块 docstring「双 schema」专节 + 其测试 fixture）**：`GET /db/conf/{acr}/{slug}.xml`（在线卷页，`enumerate_issue`/`healthcheck` 实际请求路径）**根元素不是** `<dblp>`，而是 `<bht>`——每条 `proceedings`/`inproceedings` 记录被多包一层 `<r>`，外层还有 `<dblpcites>` 容器与一个人读 `<h1>` 标题（均非记录本身）：

```xml
<bht key="db/conf/icml/icml2023.bht" title="…">
  <h1>40th ICML 2023: Honolulu, HI, USA</h1>
  <dblpcites>
    <r><proceedings key="conf/icml/2023">…</proceedings></r>
    <r style="ee"><inproceedings key="conf/icml/AamandACINS23">…</inproceedings></r>
    …
  </dblpcites>
</bht>
```

（[LIVE] 2026-07-23 对 `https://dblp.org/db/conf/icml/icml2023.xml` 真实在线请求核实，HTTP 200 / `content-type: application/xml`；捕获件见 `tests/fixtures/dblp/raw/11_volume_xml_bht_schema_full_real_icml2023.xml`，逐字节未改动，含 1828 条 `inproceedings` + 1 条 `proceedings`，与 §7 D-019 锚点 `icml2023.record_count=1828` 同源）。**历史回填 `GET /xml/dblp.xml.gz` 用的是另一 schema**——根元素为 `<dblp>`，`proceedings`/`inproceedings` 是根的**直接子元素**（无 `<r>`/`<dblpcites>` 包装，`dblp.dtd` 描述的形态；示例见 `tests/fixtures/dblp/raw/04_volume_xml_dump_schema_normal.xml`）。下节"响应字段 → PaperStub 映射"的 XPath（如 `inproceedings/@key`）对两种 schema 同样有效——解析器（`parse_volume_xml`）统一按 `Element.iter(tag)`（任意深度递归查找）取记录，根元素校验放宽为 `{"bht","dblp"}` 两者皆合法，无需按 schema 分支实现。**初版实现教训（HIGH 阻断项，已修复）**：曾把 dump schema（`<dblp>` 直接子元素）误当成在线卷 XML 的 schema，导致 `enumerate_issue`/`healthcheck` 对任何真实卷 100% 解析失败（`root.tag != "dblp"` 早失败 + 直接子查询在 `<bht>` 下永远找不到记录）；本节回填此前仅见 `parse.py` docstring 与测试记录该真实结构，本文档未同步（2026-07-24 post-phase5-audit §5 处置）。

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

**healthcheck（★裁决 2026-07-23，T6 落地——收紧于本节原"匿名即可探测"表述，该表述已作废）**：与 s2（§5.4）**统一 key/配置门控**——未配置 key → `raise NotImplementedError("openalex key 未配置")` → `crawler canary` 现有语义显示 SKIP（精确复用 `canary.py` 的 `NotImplementedError`→skip 分支，零 canary 改动）；**有 key** → 固定查询 `GET /works/W{固定id}` → 比对**空白规整化 title**。**门控仅限 healthcheck 路径**，不影响 `enrich_batch`（enrich 通道仍可匿名运行、1 credit/查，§4「匿名仍 200 并计费计量」不变）。**理由**：`crawler canary` 可能被 cron/CI 高频调用，若健康检查也放行匿名真实请求，会在用户未申请/未打算使用该可选补充源时悄悄计入 openalex 每日 credit 消耗——故改为与 s2 一致的"未配置则 SKIP、不消费预算"（T6 卡片口径）。**[PENDING]** 固定 W-id 及真值（需 key）实现期捕获。

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

**healthcheck**：**无 key → `raise NotImplementedError("s2 key 未配置")`** → `crawler canary` 现有语义显示 SKIP（精确复用 `canary.py` 的 `NotImplementedError`→skip 分支，零 canary 改动；**纠正原「无 key→config」**——config 会被 canary 判为 unhealthy、每周误触 test-plan §4「连续 2 周 DRIFT→降级」误报，评审 B-C3）。**有 key** → `GET /paper/DOI:{固定DOI}?fields=title` 比对规整化 title，不靠 429/404 判活。**[PENDING]** 固定 DOI 真值实现期捕获（需 key）。**（★裁决 2026-07-23）**本门控现与 openalex（§5.3）统一表述——openalex healthcheck 同期收紧为同构 key 门控，取代其原"匿名即可探测"表述；统一理由=`crawler canary` 默认不因源未配置而消耗真实请求/预算，详见 §5.3。

**fixture 清单**：①正常 batch 响应（`citationCount`/`tldr`/`fieldsOfStudy`）②未命中（404 "not found"）③有 key 429 → `rate_limited` ④无 key 场景（合成，验证「不靠状态码判 key 缺失」路径）。

### 5.5 unpaywall（OA 副本发现，T5；RESOLVE）

**端点与参数**

| 用途 | 端点 | 说明 |
|---|---|---|
| 单 DOI resolve | `GET /v2/{doi}?email=<addr>`（**email 必填**，网关 422 兜底） | 无 key；勘察 [LIVE] 2026-07-22 已验证端点 |

- **无搜索端点**：必须先有 DOI 清单（来自 crossref/dblp）。**触发条件**：`no_entitlement` 兜底——实况订正 2026-07-26：`cli.py::_assemble_auth_seam`（`pull`/`grab` 唯二装配路径）对该总开关（`StageContext.oa_fallback`）**无条件**置 `True`，不存在"按 venue 声明优先"的第二触发路径；`VenueSpec`（`types.py`）schema 无任何 OA-fallback 相关字段，此前"或 VenueSpec 声明 OA-fallback 优先"为幻影字段表述，本次订正为实况（同批订正 [auth-framework.md §8.1](../auth-framework.md)、[ssrn.md §4.4](ssrn.md) 两处同源表述）。

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

### 5.7 repec（aggregator-enrich，**零网络本地 join**；Phase 7 T8 落地，契约冻结见 D-035）

> **本节是契约级设计，实现尚未落地**——`status: implemented` 覆盖的是 §5.1–§5.5 五源；repec 由
> [phase7-implementation-plan §4 T8](../../plan/phase7-implementation-plan.md) 承接，权威决策
> [D-035](../../plan/decision-log.md)，评估与探针实据见
> [research/enrich-eval-p6.md §2/§6.2](../../research/enrich-eval-p6.md)（approved）与
> [repec.md](../../research/site-survey/repec.md)（[LIVE] 2026-07-24）。实现级细节（ReDIF 字段全表、
> 上游文件命名）以 T8 实测为准，本节只冻结接口面与落盘契约。

**定位**：`family = "aggregator"`，分工档位＝"aggregator-enrich"（同 openalex/s2 一档，D-027；**该措辞是档位
描述、非字段**，见 §1 表下注）。capabilities **恒为空集**，不进 pull 六阶段；驱动路径＝`crawler enrich --source repec`。**独家增值＝JEL 分类 + wp↔published 版本关联**
（crossref/openalex/nber.org 三路皆缺，[LIVE 2026-07-24]）。

**与 §5.3/§5.4 两源的本质差异（这是本节存在的理由）**

| 面 | openalex / s2（§5.3/§5.4） | repec |
|---|---|---|
| 数据获取 | 按 DOI 在线批查（HTTP 往返） | **bulk 快照本地 join，全程零网络** |
| `domains` | 各自站点域 | **空元组 `()`**（结构性宣告无网络面） |
| 门控 | key / credit 预算 | 快照存在性与新鲜度 |
| 限速登记 | `limiter.register(domains[0], …)` | 无（装配处按空 domains 跳过） |
| 新鲜度 | 实时 | `manifest.fetched_at`（须进摘要行） |
| 幂等性 | 受上游变动影响 | 对固定快照是 `(dois, snapshot)` 的**纯函数** |
| healthcheck | 无 key → SKIP（怕消耗 credit） | 无快照 → SKIP；**有快照则零成本可高频探测** |

**取用通道与合规红线**

- **只走 bulk ReDIF**（探针 [LIVE 2026-07-26] 确证 `Classification-JEL` 与 `Publication-Status` 均在 bulk 面）；
  OAI-PMH 端点活但 `earliestDatestamp=2021-09-23` ⇒ 增量面只覆盖 2021-09 起，**全量必须 bulk 直连**。
- **零 HTML 硬红线**：绝不解析 `ideas.repec.org` / `econpapers.repec.org` 的 HTML 条目页（哪怕 robots 允许）
  ——RePEc 官方明文强烈不建议爬 HTML 并设隐私红线（AC-0.5 / AGENTS §6.3；同 §3 的其它红线同级）。
- 镜像：默认 `www2.nber.org`（探针 4/4 稳），`repec.nber.org` 备（1 次连接层失败，样本=1 不构成判罚）。
  **两域 robots 未核**（原勘察只覆盖 www/back）——**T8 首个动作是补两域 robots 核验**（plan §3 T8-robots
  ≤2 请求），不通过则停手上报。

**快照落盘契约**（`<config-home>/state/repec/`，经 `config.resolve_home()`，D-032 红线）

```
<config-home>/state/repec/
├── manifest.json        # {"schema":1,"archive":"nbr","series":["nberwo"],"mirror":…,
│                        #  "source_urls":[…],"fetched_at":"<UTC ISO8601>",
│                        #  "files":[{"name":…,"bytes":…,"sha256":…}],"record_count":N}
└── nbr/nberwo/…         # ReDIF 原样字节（上游文件命名与切分待 T8 实测，本契约不预设）
```

- **原样字节 + sha256 落盘**：ReDIF 是上游权威格式，本地解析口径可能随实现修正，保留原文才能不重新联网
  即可重解析。
- **取快照的网络面在 `src/` 之外**：`scripts/repec_snapshot.py`（不入包、不占门禁覆盖，沿 `scripts/` 先例）。
  唯一网络动作在 scripts 侧 ⇒ src 侧 `enrich_batch` 的"零网络"是**可被 socket 猴补机械证明的结构事实**。
  代价如实记：该脚本的镜像回退/校验逻辑无自动化测试，靠 T19 在线批人工核验。
- **失效语义**：快照**缺失** → `CrawlerError(CONFIG, …)` → 经既有 `_run_enrich_source` per-source 捕获记
  "提前终止"，不崩其它 source、不改退出码（与 s2 缺 key / openalex 熔断同构）；快照**过期**（>30 天，模块
  常量、不开 config 槽）→ **响亮 WARNING + 摘要行注记，继续运行**（对 enrich-eval §2.7 DoD② 字面的有意
  收窄，理由与记账见 D-035 决策 3；fable approved，附条件＝下条）。
- **警告须可操作（与缺失分支指引对称）**：过期 WARNING 必带 ①`fetched_at` 与**实际过期天数**、②**刷新命令
  一行提示**（`scripts/repec_snapshot.py` 的实际调用式），与缺失分支 `CrawlerError` 的指引同源同格式——只喊
  "过期了"而不给天数与修法，等于把响亮做成噪声。
- **不建派生索引**：3.6 万条量级，首次调用惰性全量解析入进程内 dict 即可（不建 `index.sqlite`、不入主库表）。

**`enrich_batch(dois)` 映射与观测**

| PaperStub 面 | 来源（ReDIF 字段） | 说明 |
|---|---|---|
| identifier(doi) | 入参 DOI | `10.3386/w{n}`／`t{n}` |
| identifier(repec) | `RePEc:nbr:nberwo:{n}` | **非跨源合并锚点**（跨源锚仍是 DOI）；入库后天然是 *RePEc 内部* 幂等锚点，须在 adapter 注释写清防误读 |
| meta.jel | `Classification-JEL` | 覆盖率 [LIVE]：1989=0% / 2000=87.4% / **2010 起=100%** |
| meta.published_in | `Publication-Status` | 原串直落，供 T10 `preprint_of` 建边消费（本节不建边） |
| title/authors/year/abstract | 同名 ReDIF 字段 | 照常产出——`SOURCE_PRIORITY` 最低位（`repec 1`）天然只补空，**无须实现特殊"只补不覆盖"逻辑** |

- **DOI↔handle 映射边界**：`10.3386/w{n}`／`t{n}` → `RePEc:nbr:nberwo:{n}` 的**纯语法映射**，复用
  `adapters/nber/parse.py` 既有 series 号归一（零模糊匹配、零启发式）。`t` 系列落哪个 series 段、期刊条目
  怎么 join **均未核实**（[推断] 不作依据）——T8 若实测 `t` 不落 `nberwo`，按实测**收窄**而非按推断扩张。
- **未命中三分观测（不静默丢弃）**：(a) DOI 非 `10.3386` 前缀＝结构性不可寻址；(b) 前缀符但快照无该
  handle＝覆盖缺口；(c) handle 命中但无 JEL＝增值为空。**三类各有计数并进摘要行**——openalex/s2 的"未命中"
  只有一种含义，此三分是 repec 专有的契约要求（审计 S1 原则）。
- **可寻址集合如实入档**：≈**3.6 万篇 NBER WP**；**SSRN 结构性为 0**（[LIVE]：442KB archives 全表无 "ssrn"
  串——SSRN 是 Elsevier 商业源、不在 RePEc）。即本通道覆盖面比同库 ssrn 语料（141 万 DOI）**小两个数量级**，
  这是接受该通道时已定价的事实。

**接入面改动清单（T8）**：`_ENRICH_SOURCES` → `("openalex","s2","repec")`；`_prepare_enrich_source` 补空
`domains` 守卫（与 `_register_rate_domains` 既有"空 domains 跳过"同构化）；`--source` help 文案；
`SOURCE_PRIORITY` 七位重编号（§6）+ **"六枚举"字样 5 处改口**（`merge.py:26/86/135`、`storage/repo.py:140`、
`subs/watch.py:200`；**`subs/model.py:19,172` 的"六源"是 DSL `SOURCE_FIELDS`、与优先级表无关，不得连坐**）；
`pyproject.toml` entry-points +1；两处测试断言——`tests/integration/test_cli_canary.py` 的
`_EXPECTED_CANARY_ADAPTER_IDS` 20→21，`tests/unit/test_adapter_loading.py:70` 的 `assert adapter.domains`
按网络面分类改判（`_ZERO_NETWORK_ADAPTERS = {"repec"}` 双向断言，**正向锁定零网络**而非豁免）；
`registry.py:330`「空 domains（畸形 adapter）」注释语义调和（enrich 源不进 registry 路由 ⇒ 该分支对 repec
不可达，代码与文案零改动，仅注释收窄）。**零 schema migration**（`identifier.scheme` 无 CHECK 约束）。

**fixture 清单**：①正常 ReDIF 记录（含 `Classification-JEL` + `Publication-Status`）②缺 JEL 的历史记录
③畸形/截断记录 → `parse` ④多记录切分 ⑤快照缺失 ⑥快照过期。另需 DOI↔handle 映射矩阵 ≥8 例、
`enrich_batch` 零网络专测（socket 猴补）、domains 空集断言。

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
| repec（§5.7，P7 T8） | `(repec, RePEc:nbr:nberwo:{n})` + `(doi, 入参 DOI)` | handle 原样；DOI 经 `normalize_doi()` |

- **DOI 归一唯一入口**：所有 DOI 写入前经 `ids.normalize_doi()`（小写化、剥 `https://doi.org/`、`doi:` 前缀）——crossref/unpaywall/dblp ee 回填/openalex/s2 共用（plan §2-1）。identifier `(scheme,value)` 全局唯一 → 天然强合并锚点（AC-3.1）。
- **identifier 产出的「同源著作」判界（2026-07-22 修订清单 A-C4，评审 A 专项论证）**：identifier 产出由**是否指称同一著作**（same-work）支配，**非**由「谁铸造/注册该 id」支配。dblp `inproceedings` 记录**即该已刊会议论文本身**、其 `ee` 官方 doi.org 链接是**该同一论文自己的 DOI**（同源）→ 产 `(doi,…)` identifier 作跨源合并锚点（AC-3.1 必要条件）；区别于 arxiv `journal_ref/doi`、neurips 内嵌 arxiv/openreview id——那些指向**异源著作**（预印本 DOI 指其已刊正式版，两条 paper 经 `preprint_of` 相连而不合并，D-007）→ **仅入 `meta`、不产 identifier**（neurips「防跨源早合并」先例）。dblp 虽非 DOI 注册本源（Crossref/DataCite 代出版社铸造），但 `ee` 是其人工策展的同源身份断言 → 产锚点与该先例不冲突。
- **`PaperStub.meta` 值类型冻结（2026-07-22 修订清单 A-C1）**：`meta: tuple[tuple[str, str], ...]`（types.py 冻结，值须 `str`）——非字符串结构一律 `json.dumps` 序列化后入 meta（s2 `citationCount`(int)/`fieldsOfStudy`(list)/`openAccessPdf`(dict)、openalex OA 结构等），消费方自行 `json.loads` 反序列化；标量可 `str()`，结构必 `json.dumps`。

**source 优先级标记（字段级来源收敛，AC-3.4 基石）**

- 各源写字段时携带 provenance tag：crossref→`"crossref"`、dblp→`"dblp"`、openalex→`"openalex"`、s2→`"s2"`、repec→`"repec"`（§5.7，P7 T8）。unpaywall 不写元数据字段（只产 Asset），不入此收敛。
- **字段级来源优先级（plan §2-1 / D-021 已冻结，★W0 仲裁 2026-07-22）**：`official > crossref > dblp > openalex > s2 > heuristic`（**已含 dblp 级**）。**[D-035 修订 D-021 决策 3，2026-07-27]** 表扩为七位并整体重编号以给 repec 腾出最低非-heuristic 位：`official 6 > crossref 5 > dblp 4 > openalex 3 > s2 2 > repec 1 > heuristic 0`（`s2 1` 与 `heuristic 0` 相邻无整数空位，插位必须重编号；provenance 落 `_field_src` 记的是**来源名字符串**非数值，故重编号对存量数据零影响）。repec 取最低位＝其重叠字段是二手面、而其独家增值（JEL/`Publication-Status`）三路皆缺 ⇒ 只补空即可全额兑现。理由（D-021 决策 3）：Crossref 为 DOI 注册源头（出版社存缴）元数据居先；DBLP 人工策展（CC0）质量高于 openalex/s2 机器聚合层，低于出版社直连 crossref。dblp（会议主干、paper 级 `ee` 回填 DOI）的字段据此有确定优先级——此前草案「未列 dblp／[UNRESOLVED] 待仲裁」的表述**已作废**（该位次已由 D-021 定裁，位置与原建议一致）。

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
| 11 | 2026-07-23 | **§5.1 补记 T3 限速/timeline 粒度实现落地**：X-Rate-Limit 动态读头在冻结 `HttpClient.get_bytes`（不暴露响应头）下不可达，落地为静态 5 req/s 保守上限 + 429 退避（★裁决 2026-07-22，T3）；timeline 粒度=出版年（Crossref filter 无卷期维度），volume/issue 经 works 记录读入 meta（★裁决） | T3 实现（`adapters/crossref/adapter.py` 模块 docstring） |
| 12 | 2026-07-23 | **§5.3/§5.4 healthcheck 措辞对齐 T6 实现**：openalex healthcheck 门控收紧为与 s2 统一"无 key → `NotImplementedError`→canary SKIP"，废止原"匿名即可探测"表述（★裁决 2026-07-23；理由=防 `crawler canary` 周期性高频调用时静默消耗 openalex 每日 credit 配额） | T6 实现（`adapters/openalex/adapter.py` 模块 docstring 自述"收紧于设计稿 §5.3"） |
| 13 | 2026-07-23 | **文档转正**：front matter `status: approved`→`implemented`（T1~T7 五源 adapter + 合并引擎全部合并落地；AC-3.5 在线实跑 PASS 建议，待 controller 终签） | Phase 3 收尾（[records/2026-07-23-ac35-acceptance.md](../../testing/records/2026-07-23-ac35-acceptance.md)） |
| 14 | 2026-07-26 | **§5.2 回填 dblp 真实枚举卷响应 schema**：在线卷页根元素 `<bht>`（记录嵌 `<dblpcites>/<r>` 两层包装）vs 历史 dump `<dblp>`（`proceedings`/`inproceedings` 为直接子元素）两形态并存，此前仅 `dblp/parse.py` 模块 docstring 与测试 fixture 记录该真实结构，本文档未同步回填（文档滞后修正，非实质设计变更） | Phase 6 F2（[2026-07-24-post-phase5-audit.md §5](../../reports/2026-07-24-post-phase5-audit.md)） |
| 15 | 2026-07-26 | **§5.5 幻影字段清账（非设计变更）**：删"或 VenueSpec 声明 OA-fallback 优先"——`VenueSpec` schema 从无该字段；实况是 `cli.py::_assemble_auth_seam` 对 OA-fallback 总开关无条件置位。同批订正 [auth-framework.md §8.1](../auth-framework.md)、[ssrn.md §4.4](ssrn.md) 两处同源表述 | P6-T10 收尾盘点发现 |
| 16 | 2026-07-27 | **新增 §5.7 `repec`（aggregator-enrich）契约级设计**：定位/与 §5.3-§5.4 的本质差异表（零网络 vs 在线批查）/bulk-only 与零 HTML 红线/`state/repec/` 快照落盘契约（布局+manifest+失效语义+网络面移出 src）/`enrich_batch` 映射与未命中三分观测/DOI↔handle 仅 NBER 语法映射边界/可寻址集合如实入档（≈3.6 万 NBER WP，SSRN 结构性为 0）/接入面改动清单/fixture 清单。同批：§1 分工表 +1 行、§6 identifier scheme 表 +1 行、§6 优先级表按 D-035 扩为七位重编号、H1 与 front matter 标题同步。**本节是契约级设计、实现未落地**（`status: implemented` 覆盖的仍是 §5.1–§5.5 五源），显式标注于节首。 | [D-035](../../plan/decision-log.md)（P7-T2 卡产出，独立审查 NEEDS_FIX→修复→fable 落章生效）；[enrich-eval-p6.md §2/§6.2 探针 GO](../../research/enrich-eval-p6.md)；[phase7-implementation-plan §4 T2/T8](../../plan/phase7-implementation-plan.md) |

## 10. 风险与维护

- **OpenAlex 计费制是最大外部变化源**（2026-02 才改制，政策可能续演）：预算护栏（`meta.cost_usd` 实时核销）+ 月度账单核对（以 `state.spent_usd` 累计为准）列入运维；免费额度进一步收紧则降级路径 = Crossref + S2 补摘要（plan §6 风险①，设计已备）。
- **S2 key 审批趋严**（2024-11 起）：Phase 3 开工前预申请（plan 依赖项）；未到则在线层 skip 门控（不阻塞离线 DoD）。
- **DBLP dump 月度 DOI 快照**（`10.4230/dblp.xml.YYYY-MM-01`，Dagstuhl DROPS）为可复现研究提供固定锚——backfill 记录所用快照版本 + md5 校验。
- **canary 存在性纪律**：合成/锚点 canary 必须先实证存在性（Phase 2「合成假设是盲区源」+ 本次 `10.1257/aer.20221079` 三源不存在教训）。
- **[UNRESOLVED] 残留**：①openalex/s2 healthcheck 固定样本真值（§5，[PENDING] 需 credit/key）②openalex 正锚点、s2 需 key 锚点（§7 [PENDING]）③OpenAlex 预算状态持久化载体（§4，T6 确认）。（原「dblp 字段级优先级位次」已由 **D-021 定裁**移除；**crossref healthcheck 真值 "Deep learning" 与 dblp icml2023=1828 已由 T7 AC-3.5 实跑捕获销项**——2026-07-23 §9 修订 #10，crossref adapter `_HEALTHCHECK_TITLE` golden 化留 UPDATE_GOLDEN，非本次范围。）
