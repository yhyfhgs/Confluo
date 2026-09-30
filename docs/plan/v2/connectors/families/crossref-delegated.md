---
title: Crossref 委托族（crossref_delegated）规范与连接器卡片
status: draft
owner: opus5.5-primary
updated: 2026-09-30
---

# Crossref 委托族：`crossref_delegated`

本文回答：在 Crossref（或 DataCite）登记 DOI 的期刊、WP 与预印本前缀、论文集，怎样由一个族引擎零代码接入"元数据"与"最新论文"两条通道；族引擎在通用契约之上多了什么，实例怎么声明，要过哪些族测试，上游事实和坑在哪里。结论：本族只有一个平台侧连接器 `crossref_delegated`（族核心，v2-P0，W0 参考连接器之一），服务 92 行来源，覆盖名录核心 venue 行的约 92%（260/282）；三种委托（期刊 ISSN 集合；DOI 前缀，含 Crossref member 变体；论文集按 container-title 拆分）只走 Crossref 按路由的端点，不用全局 `/works` 的 filter 或 query 做后台收割，也不作关键词检索源；增量以 `from-created-date` 加 3 天重叠为主，每周 `from-index-date` 补漏并叠加创建时间下限，更晚的迟到记录交 `crossref_annual_file` 对账；DataCite 变体给出两种落法，归属列入待拍板。

## 要点

- 本族只声明请求、解析响应、映射 NormRecord；请求全部经出站网关发往 `api.crossref.org`，从不接触出版商主机。通用协议、类型与错误矩阵见 [连接器接口契约 v1](../contract.md)，本文只写族专有部分。
- venue 零代码：新期刊、新 WP 系列、新预印本前缀只改 VenueSpec 或本族实例 YAML（SOP A，≤30 分钟，见 [03 新增来源 SOP](../../03-sources-and-corpus-pipeline.md#新增来源-sop-与成本目标)）。
- 委托编译是纯函数：SourceSpec + VenueSpec + 实例 → `Delegation` 列表，每个 `Delegation` 是一个游标作用域（`scope_key`）。
- 请求类：`/journals/{issn}/works` 与 `/prefixes/{p}/works` 已实测归 single 池（公共池、无 mailto；polite 池未测）；`/members/{m}/works` 归池两说，按列表池（array）保守声明，标待核。
- 集中限速：Crossref 按邮箱计限，全平台共用部署 UA 中的一个 mailto 身份与一个令牌桶；不得用多邮箱扩额。
- 游标：`date_watermark`（created 轴，日粒度，重叠 3 天，窗口按月切）；`late_path = weekly_index_backfill`，L 之外交快照对账。
- Crossref 不删 DOI：本族不产出 tombstone；撤稿、更正、撤回由 `update-to` 转为 `status_claims`。
- 摘要默认按出版方版权处理（B 类待法务），许可以 `license[]` 原串加 `license_alias` 归一，权利由共享 `classify_rights()` 计算；SSRN 的 USPTO 链接不是许可。

## 1. 本族回答什么、适用边界

**回答**：一个来源的元数据与最新论文能否"按 DOI 登记机构的路由端点枚举"得到。能，就归本族，写实例不写代码。

**与相邻族的分界**：

| 相邻族或连接器 | 分工 |
|---|---|
| `crossref_rest`（v1 桥接，目标族 `aggregator_api`；卡片见 [v1-bridge.md](v1-bridge.md#crossref_rest)） | 按 DOI 的 `lookup`（`/works/{doi}`，single 池）与联邦补查；本族只做 `enumerate`、`increment`、`probe`。两者共用同一个 Crossref 令牌桶。 |
| `crossref_annual_file`（`bulk_snapshot`；见 [bulk-snapshot.md](bulk-snapshot.md#crossref_annual_file)） | 策展 venue 的全史回填与超出 L 的迟到记录对账；本族只管年度文件截止日之后的窗口。 |
| `datacite_rest`（`aggregator_api`；见 [aggregator-api.md](aggregator-api.md#datacite_rest)） | DataCite DOI 的查找与富化；DataCite 登记的 venue 枚举（LIPIcs `10.4230`）见 §2.4 的两种落法。 |
| `feed` | 只作新鲜度信号；本族是元数据主通道。NBER RSS 因 NBER T&C 2026-08-01 暂停，`nber_wp` 最新通道改由本族承担（待拍板，见未决事项）。 |
| `site_special` | venue 无 DOI 或 Crossref 覆盖不足（PMLR、CVF、JMLR）时由专站连接器承接；有 DOI 的届次仍以本族为元数据主源（如 IJCAI、NeurIPS 的 DOI 对齐）。 |
| `oai_pmh` | 同一来源同时有 OAI 与 Crossref 时，本族管 DOI 级书目事实，OAI 实例管全文位置与仓储特有字段。 |

**不做**：关键词检索（main 03/04 口径，SCD 不声明 `search`，长稿 04 中 `works_query` 服务 SEARCH 的写法作废）；全局 `/works?filter=` 或 `query` 后台收割（长稿 SI-02）；`locate_fulltext`（见卡片 §9）；访问出版商、SSRN、NBER 等任何站点主机。

## 2. 族专有接口

通用部分（`PlatformConnector` 的 `plan/parse/normalize/describe/probes`、`Step`、`CursorEnvelope`、错误分类）一律按 [契约](../contract.md)；下面只写本族多出的部分。

### 2.1 委托模型

```python
# 设计伪代码 —— crossref_delegated 族专有部分（通用协议见 ../contract.md）
DelegationKind = Literal["journal", "prefix", "member", "proceedings"]

@dataclass(frozen=True)
class Delegation:                          # 由 compile_delegations() 生成；一个 Delegation = 一个游标作用域
    delegation_id: str                     # = scope_key，如 "xref:journal:0027-8424"、"xref:prefix:10.2139:posted-content"
    registry: Literal["crossref", "datacite"]
    kind: DelegationKind
    keys: tuple[str, ...]                  # journal：全部历代 ISSN；prefix：DOI 前缀；member：member id；proceedings：前缀或 member
    type_filter: tuple[str, ...]           # 如 ("posted-content",)；空元组 = 不过滤
    container_titles: tuple[str, ...]      # 仅 proceedings：精确标题，只在本地拆分
    post_filters: tuple[PostFilterId, ...] # 封闭枚举，见 §2.3
    serves: SourceId                       # 审计与策略判定用的来源（如 elsevier_sd）
    venue_ids: tuple[VenueId, ...]

class CrossrefDelegated(PlatformConnector):
    def compile_delegations(self, spec: SourceSpec, venues: list[VenueView],
                            inst: DelegatedInstance) -> list[Delegation]: ...
        # 纯函数；同一 ISSN 被两个 venue 声明时 lint 失败（见 §3 lint 补充）；ISSN 历代变更全部展开
    def plan(self, task: ConnectorTask, ctx: PlanCtx) -> Generator[RequestSpec, Step, TaskOutcome]: ...
        # task.operation ∈ {enumerate, increment, probe}；task.scope_key = delegation_id
        # enumerate：窗口按月切（window_max = 1 月），每窗 cursor=* 深翻，窗口末页才给 next_cursor
        # increment：from-created-date = cursor.value − overlap(3d)，until 在首个请求前固定为 ctx.now 的日期
        # backfill（每周，increment 且 IncrementInput.mode = "weekly_backfill"）：from-index-date = 上周起点，
        #   且 from-created-date ≥ ctx.now − L（L 初值 30 天，未核）；结果按 DOI 去重吸收
        # corrections（每周，IncrementInput.mode = "corrections"）：同一路由端点加 update-type:retraction
        #   与 from-update-date，不打全局列表池
    def parse(self, resp: Response, ctx: ParseCtx) -> Page: ...
        # 解析 message.items；把 x-api-pool、x-rate-limit-limit/interval、x-concurrency-limit 放进 PageSignals.rate_headers
        # total-results = 0 且 status=ok → legit_empty；next-cursor 放 PageSignals.continuation（不持久化）
```

### 2.2 四类任务的请求形状

| 任务（operation / mode） | 过滤 | 排序与分页 | 频率 | 提交规则 |
|---|---|---|---|---|
| `increment`（默认） | `from-created-date:{cursor−3d}`、`until-created-date:{until}`，加 `type_filter` | `sort=created&order=asc`，`cursor=*`，`rows=1000` | 按 WatchKey 调度，P0 venue ≥ 每日 | 窗口末页提交；`ordered_by: created` 经乱序反例 fixture 验证后才允许页级提交 |
| `weekly_backfill` | `from-index-date:{上周一}` 且 `from-created-date:{now−L}` | 同上 | 每周一次 | 独立 `scope_key`（`<delegation_id>#backfill`）的 `window_set` 游标，逐窗提交；不推进 `increment` 的 `date_watermark` |
| `corrections` | `update-type:retraction`（及 correction、withdrawal，未核）加 `from-update-date:{上次}` | 同上 | 每周一次 | 同上（`<delegation_id>#corrections`） |
| `enumerate`（回填） | `from-created-date`、`until-created-date` 按月窗口 | 同上 | 新 venue 接入或策展回填时 | `window_set` 逐月窗口提交（契约 §4） |

- 上表过滤名与语义见 [Crossref tips, 2026-09-30](https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api/)：created 只含新建，update 含存缴变更，index 范围最大；翻页期间记录可能被重建索引，官方建议按时间切块。
- 放大实测只有一个样本：Nature Methods 自 2026-09-01，index 3,223、update 63、created 32（长稿 C12，2026-09-26，未复核）；补漏预算在 V0 实测后定。

### 2.3 post_filters（封闭枚举，每项配 fixture）

| PostFilterId | 用途 | 典型实例 |
|---|---|---|
| `split_by_container_title` | 同一前缀或 member 下多会、多刊共存时，按精确 container-title 在本地拆分；标题含逗号时 Crossref filter 报 `pair-list-form-invalid`，一律本地拆分（长稿 CS §2.1.4，未复核） | IJCAI 与 KR 共用前缀；AAAI OJS 的多个会议；Curran 代印的论文集 |
| `drop_components_and_chapters` | 丢弃 `component`、`book-chapter` 等非论文类型 | IMF `10.5089` |
| `owner_vs_string_prefix_check` | DOI 字符串前缀与 owner prefix 不一致时按 owner 判归属，防止同一前缀下期刊与预印本混收 | bioRxiv/medRxiv：旧 `10.1101`（也含 CSHL 期刊）与新 `10.64898` |
| `version_suffix_rule` | 把版本 DOI 后缀（`_vN`、`/vN`）解析为 `version_claim.seq`；DOI 粒度仍查注册表 `doi_family`（本批新增） | PsyArXiv `_vN`（长稿）；ChemRxiv `/vN`（长稿，本轮样例未核） |
| `ssrn_abstract_id` | 抽取 `abstract_id`；DOI 中缀不是 `ssrn.` 时不增补标识、只计观测（沿用 v1 护栏，本批新增为族级枚举） | SSRN `10.2139` |

实例只能打开已登记的旗标；新怪癖进引擎（附 fixture 与全实例回放）或升 `site_special`，不允许实例级 Python 钩子（契约"声明式与代码的边界"）。

### 2.4 DataCite 变体

长稿把 DataCite 变体放进本族（`registry: datacite`，用于 LIPIcs、arXiv DOI、dblp 快照 DOI）；来源清单调研（2026-09-30）把 `lipics_drops` 记为复用 `datacite_rest`。两种落法：

- **方案 A**：本连接器增加一组 DataCite 端点（`/dois?prefix=…&query=updated:[…]`，`page[cursor]` 跟随 `links.next`），`allowed_hosts` 增加 `api.datacite.org`。
- **方案 B（推荐）**：`Delegation` 模型与 post_filters 做成族库，`datacite_rest` 以"委托模式"复用；本连接器的 `allowed_hosts` 只有 `api.crossref.org`，两边令牌桶与预算互不混账。
- 两案共同点：DataCite 限额按 IP 的 5 分钟滚动窗，识别身份（UA 含邮箱）1,000 次、未识别 500、认证 3,000，超限 429，无限速头 [https://support.datacite.org/docs/rate-limit, 2026-09-30]；`page[size]` ≤1000，页码分页最多 10,000 条，cursor 分页跟随 `links.next` [https://support.datacite.org/docs/pagination, 2026-09-30]；arXiv（`10.48550`）只用于 DOI 映射，不作枚举（arXiv 走 `arxiv_oai`）；dblp 快照 DOI 只供 `bulk_snapshot` 发现新版本。

## 3. 实例与清单字段

**ConnectorInstance**：`registry/instances/crossref_delegated/<source_id>.yaml`，每个被服务来源一份；期刊级键优先来自 VenueSpec `identifiers`，实例只放来源级规则。

| 字段 | 必填 | 说明 |
|---|---|---|
| `serves` | 是 | 一个 `source_id` |
| `delegations[]` | 否 | 来源级委托（前缀、member、论文集）；期刊委托由 VenueSpec 的 `issn` 自动生成 |
| `delegations[].kind` / `keys` / `type_filter` / `container_titles` | 按 kind | 同 §2.1 |
| `post_filters` | 否 | 只能取 §2.3 已登记值 |
| `version_stage_default` | 否 | `vor`（期刊默认）、`preprint`、`wp`；posted-content 默认 `preprint` |
| `abstract_expected` | 否 | 预期摘要覆盖（如 NBER 为 0、Fed `10.17016` 约 99%，长稿），供计数探针与摘要补齐链 |
| `lag_bound_days` | 否 | 覆盖族默认 L（证据或"未核"） |

DOI 粒度不在实例里声明：按契约由注册表粒度表的 `doi_family` 前缀映射给出，PsyArXiv `10.31234`、ChemRxiv `10.26434` 登记为版本级，mapper 不自报。

**ConnectorManifest 本族特有字段**（通用字段见契约）：

- `family_params.upstream_bucket`: `crossref` —— 五元组令牌桶的"来源"维取上游 Crossref，不取被服务来源；被服务来源只进 FetchLog 与策略判定（本批新增字段）。
- mailto 身份：即网关 UA 中的部署联系邮箱（全平台一个，HC-10）；`mailto` 写入 `personal_params` 禁表，RequestSpec 出现该参数即 `config`，防多邮箱扩额。
- `family_params.plus_token`: `null` —— 默认不购买 Metadata Plus（main 03 默认假设）；启用时为 `AuthRef(deployment/crossref_plus)`，池名与限额随之变更须重跑契约测试。
- `endpoints[]`：见卡片 §4。

**lint 补充（族级，叠加注册表 13 条与连接器 6 条）**：
1. SourceSpec 中由本族承担的通道条目，其 `hosts` 只能是 `api.crossref.org`（方案 A 另加 `api.datacite.org`），出现出版商主机即失败；
2. 同一 ISSN、同一 (前缀, type_filter) 不得出现在两个 `Delegation`；
3. `proceedings` 必须带 `split_by_container_title` 与至少一个 `container_titles`；
4. `type_filter` 为空的前缀委托须在卡片 §13 写理由（防止期刊与预印本混收）。

## 4. 族一致性套件

在 [通用契约测试](../conformance-and-testing.md) CT-01…CT-12 之上，本族按"实例 × fixture"参数化，新增实例不写新测试：

| 编号 | 断言 | fixture |
|---|---|---|
| FS-XD-01 | `compile_delegations()` 纯函数，同输入字节级相同；ISSN 历代展开完整 | VenueSpec 样例（含 ISSN 变更） |
| FS-XD-02 | 每个 RequestSpec 的 `request_class` 与响应 `x-api-pool` 对账一致；不一致即失败 | 每端点各一页，含 `x-api-pool` 头 |
| FS-XD-03 | 窗口重叠与乱序：随机打乱页序、在每页边界注入崩溃与 `cursor_expired`，各次运行 DOI 并集等于真值，提交游标不越过未落库数据 | 同一月窗三页 + 乱序反例 |
| FS-XD-04 | 补漏任务不推进 `increment` 游标；补漏结果与增量结果重叠时 NormRecord 不变（幂等） | 补漏页与增量页含相同 DOI |
| FS-XD-05 | 每个 post_filter 幂等、与顺序无关；逗号标题只走本地拆分 | 含逗号 container-title 的论文集页 |
| FS-XD-06 | `owner_vs_string_prefix_check`：`10.1101` 下 CSHL 期刊文章不进预印本实例 | bioRxiv 混合页 |
| FS-XD-07 | 撤稿 `update-to` 产出 `status_claims`，不产出 tombstone | 撤稿通知记录 |
| FS-XD-08 | RequestSpec 无 `mailto`、`query`、全局 `/works` 列表路径 | 静态检查 |
| FS-XD-09 | 刊级错配（`/journals/1548-7091` 返回 Nature Chemical Biology，长稿 C11）被探针识别，不静默入库 | 错配页 |

## 5. 连接器清单总表

| connector_id | 服务来源数 | 最高优先级 | 波次 | exec_side | 代码量级 | v1 复用 | 前置依赖 | 当前 / 目标 CL |
|---|---:|---|---|---|---|---|---|---|
| [`crossref_delegated`](#crossref_delegated) | 92 | v2-P0 | W0 | platform | 族核心，粗估 3 人日（来源清单调研，未核） | 移植 v1 `adapters/crossref/`（796 行） | `crossref_rest`（共用请求声明与令牌桶，W0 同批）；部署 mailto 身份；网关五元组桶；V0 实测分池与补漏放大 | 未建 / CL3（V1 出口） |
| `ssrn_crossref` | 1 | metadata-only（P0） | W2 | platform | 桥接 0.5 人日 | v1 `ssrn` | D-051；新 ADR 取代 D-029/D-030 相关部分 | 桥接期卡片在 [v1-bridge.md](v1-bridge.md#ssrn_crossref)；移植为本族 `ssrn` 实例后转 CLX |
| `crossref_rest` | 1 | v2-P0 | W0（[实施计划](../implementation-plan.md)由 W2 提前） | platform | 桥接 1.5 人日 | v1 `crossref` | 与本族共用令牌桶 | 卡片在 [v1-bridge.md](v1-bridge.md#crossref_rest) |
| `datacite_rest` | 2 | v2-P1 | W3（V3） | platform | 新写 2 人日 | — | §2.4 方案选择 | 卡片在 [aggregator-api.md](aggregator-api.md#datacite_rest) |

**服务来源分布**（来源清单调研 92 行，含 medrxiv 展开；ssrn 经 `ssrn_crossref` 另计）：优先级 v2-P0 19、v2-P1 38、v2-P2 20、metadata-only 15；支持 72、登记 20；七类 M1 59、L1b 17、L1a 15、L2a 1。登记行只登记、不运行（CL0；该口径是对 D-073 的细化，列入待拍板）。

**承接的核心 venue**（来源清单调研的 `venues_core_rows`；全名录核心 venue 行 282，本族服务来源合计 260，约 92%；登记 venue 行 399/414）：

| 来源 | 优先级 | 核心 / 登记 venue 行 | 委托形态 |
|---|---|---:|---|
| `elsevier_sd` | v2-P0 | 42 / 72 | 期刊 ISSN |
| `wiley` | v2-P0 | 25 / 37 | 期刊 ISSN |
| `acm_dl` | metadata-only（P1） | 22 / 24 | 期刊 + 论文集（DOI 常在会前注册） |
| `springer_link` | v2-P0 | 21 / 32 | 期刊 ISSN（论文集丛书待核） |
| `nature_portfolio` | v2-P0 | 17 / 20 | 期刊 ISSN（RSS 仅信号） |
| `oup_academic` | v2-P0 | 15 / 20 | 期刊 ISSN |
| `ieee_xplore` | v2-P1 | 14 / 23 | 期刊 + 论文集（DOI 滞后 2–6 月） |
| `acs` | metadata-only（P0） | 9 / 11 | 期刊 ISSN |
| `sage_journals`、`sciengine` | v2-P1 / metadata-only（P2） | 8 / 16、8 / 3 | 期刊 ISSN |
| `aps`、`informs_pubsonline` | v2-P0 | 7 / 6、7 / 4 | 期刊 ISSN |

**P0 前缀与论文集实例**（值来自 2026-09-30 调研与长稿；标"长稿"者未复核）：

| 来源 | 委托 | type_filter | post_filters 与要点 |
|---|---|---|---|
| `ssrn`（经 `ssrn_crossref`） | prefix `10.2139`（single 池实测） | posted-content | `ssrn_abstract_id`；只用 created，posted 为 0 条（长稿）；2026-08-01 起 54,329 DOI、约 905 条/日 [https://api.crossref.org/prefixes/10.2139/works?filter=from-created-date:2026-08-01&rows=0&facet=license:*,type-name:*, 2026-09-30] |
| `nber_wp` | prefix `10.3386` | `report`（2026-06-01 起 576 个 DOI 全为 Report；样本无摘要、无 license）[https://api.crossref.org/works?filter=prefix:10.3386,from-created-date:2026-06-01&rows=2, 2026-09-30] | 摘要补齐链（RePEc）；RSS 暂停后兼任最新通道（待拍板） |
| `biorxiv`、`medrxiv` | member `54368`，或 prefix `10.64898` + `10.1101` | posted-content | `owner_vs_string_prefix_check`；`10.64898` 自 2025-12-01 用于全部新稿，Crossref 登记可能需 24 小时才可解析 [https://connect.biorxiv.org/news/2025/11/18/preprint_dois, 2026-09-30] |
| `chemrxiv` | prefix `10.26434` | posted-content | `version_suffix_rule`（`/vN`，未核）；平台迁 Wiley Research Exchange，日期两说 |
| `psyarxiv` | prefix `10.31234`（COS 共 23 个前缀，长稿） | posted-content | `version_suffix_rule`（`_vN`）；`doi_family` 登记为版本级 |
| `ijcai_proceedings` | prefix（与 KR 共用，值长稿） | — | `split_by_container_title` |
| `aaai_ojs` | prefix（多会共用，值长稿） | — | `split_by_container_title`；元数据与最新通道由 `aaai_ojs_oai`（桥接，移植为 `oai_pmh` 实例）承担，本族只补 DOI 级书目事实 |
| `neurips_proceedings` | Curran DOI 对齐（前缀未核） | — | 只作 DOI 对齐，元数据主源仍是专站 |

## 6. 连接器卡片

### crossref_delegated

**1 身份**：`connector_id: crossref_delegated`；族 `crossref_delegated`；`kind: platform_connector`；`impl: custom_plan`（族引擎；委托编译、补漏双过滤与 post_filters 超出声明式词表），被服务来源一律 `instance`；`contract_version: 1`；`connector_version: 0.1.0`（未发布）；`lifecycle: active`；CL 当前未建，W0 末达 CL1，V1 出口达 CL3；owner 与 backup_owner 待指派（P0 须两人）；服务 92 个 `source_id`（清单见 [连接器矩阵](../../../../catalog/connector-matrix.md)），venue 范围为全部带 `issn`、DOI 前缀或 member 标识的 VenueSpec；波次 W0（参考连接器），实例按来源优先级在 W1–W4 打开。

**2 通道与操作**：

| Operation | metadata | latest | fulltext |
|---|---|---|---|
| `enumerate` | ✓（回填，按月窗） | — | — |
| `increment` | ✓ | ✓（主通道） | — |
| `lookup` | 不支持（由 `crossref_rest`） | — | — |
| `search` | 不声明 | — | — |
| `locate_fulltext` | — | — | 不支持 |
| `probe` | ✓ | ✓ | — |

`exec_side: platform`；`lane: harvest`（`traffic_class` 由 runner 盖章为 `background_batch`）。

**3 上游接口事实**：

- REST/JSON，基址 `https://api.crossref.org`；路由资源 `/journals/{issn}/works`、`/members/{id}/works`、`/prefixes/{p}/works`；参数 `filter`、`select`、`rows`（≤1000）、`cursor`、`sort`/`order`、`facet` [https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api/, 2026-09-30]。
- 三个池：public（无认证）、polite（`mailto` 参数或 agent 头带邮箱）、Metadata Plus（`Crossref-Plus-API-Token`，付费）；官方建议带 mailto 并设 User-Agent [https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/, 2026-09-30]。
- 分池数值：single public 5/s、polite 10/s；array public 1/s、polite 3/s；[https://community.crossref.org/t/refining-rest-api-limits-for-improved-stability-and-reliability/16137, 2026-09-30]；并发 public 1、polite 3，Plus 150/s [https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/, 2026-09-30]。分池生效日期两说：一说 2026-07-21 起按请求类分池并按邮箱计限（社区公告）；一说 2025-12-01 起分池、2026-07 起再按 mailto 限流（博文） [https://crossref.org/blog/announcing-changes-to-rest-api-rate-limits/, 2026-09-30]，待核。access 页仍只写 5/10/150 不分请求类。
- 响应头：`x-rate-limit-limit`、`x-rate-limit-interval`、`x-api-pool`、`x-concurrency-limit`；公告提到的 `x-rate-limit-type` 实测仍无。实测 `/prefixes/10.2139/works`（带 filter 与 facet，URL 见 §5 SSRN 行）→ `public-single`，`/works?filter=prefix:10.3386,…` → `public-array` [https://api.crossref.org/works?filter=prefix:10.3386,from-created-date:2026-06-01&rows=2, 2026-09-30]；`/journals/{issn}/works` → `public-single` [https://api.crossref.org/journals/1548-7091/works?rows=0, 2026-09-30]；`/members/{m}/works` 长稿记 single、博文列为列表请求，实测 `/members/13/works` 遇 429 未能确认 [https://api.crossref.org/members/13/works?filter=from-created-date:2026-09-27&rows=0, 2026-09-30]，待核；polite 池头部未实测（未核）。
- 用多个邮箱规避限速不被允许，无效邮箱可能导致封禁 [https://community.crossref.org/t/refining-rest-api-limits-for-improved-stability-and-reliability/16137, 2026-09-30]。状态码：401 token 无效，403 人工封禁须联系支持，429 超限稍后重试 [access 页，同上]；`Retry-After` 文档未写（未核）。
- 深翻 `cursor=*` → `next-cursor`，返回条数少于 `rows` 即停 [tips 页，同上]；cursor 过期时间现行文档未写，旧文档与第三方称 5 分钟未用即过期（未核，按 5 分钟保守处理）。
- 删除：DOI 不删、无删除流（未核）；撤稿 `update-to`、`filter=update-type:retraction`，Retraction Watch 数据 2025-01-29 起进 API（长稿 C8，未复核）。Event Data API 2026-04-23 停用（长稿 C6），本族不用。

**4 请求声明**：

| endpoint_id | 路径模板 | request_class | paginator | 说明 |
|---|---|---|---|---|
| `crossref.journal_works` | `/journals/{issn}/works` | `single` | `cursor` | 每个 ISSN 一个请求序列，按 DOI 合并 |
| `crossref.prefix_works` | `/prefixes/{prefix}/works` | `single` | `cursor` | 前缀委托 |
| `crossref.member_works` | `/members/{member}/works` | `array`（保守，待核） | `cursor` | 仅兴趣集中的出版方或 bioRxiv 类 member |

- `hosts_touched = allowed_hosts = {api.crossref.org}`；`auth: null`（mailto 身份由网关写进 UA）；`select` 固定字段集以减小响应；`volatile_fields`：`indexed`、`is-referenced-by-count`、`reference-count`、`score`，不入 `payload_sha256`。
- 令牌桶五元组：(`crossref`, `api.crossref.org`, `single`|`array`, 部署 mailto 身份, 出口 IP)，全平台集中限速，与 `crossref_rest`、`ssrn_crossref` 共用。
- `Expectation`：`content_types = [application/json]`；`root = message.items`；`min_bytes` ≈ 100；`empty = legit`（`status=ok` 且 `total-results=0`）；`fake_success` 不设（`status≠ok` 的 200 体未见实例，未核；若出现由 `parse()` 抛 ParseError，`parse` 只有一个判定者）；`legit_status = [200]`。`status_overrides`（每行配 fixture）：429 → `rate_limited`；400 `validation-failure` → `config`；401 → `config`；403 → `challenge`（文档化为人工封禁，冷却 24 小时并告警）；5xx → `transient`。
- `budget`：`account: crossref_polite`，`unit: request`，`ceiling` 取响应头实时值，`planned_daily` 在 V0 实测后填（未核）。

**5 游标与增量**：`Cursor.kind = date_watermark`，`scope_key = delegation_id`；`ordered_by: created`（须 `ordered_fixture` 含乱序反例，验证前只在窗口末页提交）；`overlap: 3d`；`granularity: day`（更细粒度未核）；`bounds: [from, until]`（Crossref 日期过滤两端含，未核）；`lag_bound`: 未核（L 初值 30 天）；`late_path: weekly_index_backfill`，L 之外由 `crossref_annual_file` 与 OpenAlex 快照对账；`window_max: 1 月`。运行开始固定 `until`，完成后推进到 `until`；deep cursor 过期 → `cursor_expired`，从本窗起点重启 ≤2 次，超次 `stopped` 并告警"切小窗口"；策略失效或预算耗尽在页边界停。本族不产出 tombstone；撤稿、撤回、更正经 `corrections` 任务写 `status_claims`。游标编码变更须配 `migrate_cursor` 或"重置 + 回填窗口"。

**6 映射**：`mapper_id: crossref_work`，`identifiers_emitted = {doi, issn}`（ORCID、ROR 作为作者与机构属性）；DOI 小写并去前缀，沿用 v1 `ids.normalize_doi`；日期按语义分存 created、published-print、published-online、posted；`type` → 记录类别；标识符粒度查注册表 `doi_family`（多数作品级，PsyArXiv、ChemRxiv 版本级）；`version_claim`：journal-article → `vor`（basis `type`），posted-content → `preprint`（basis `type` + `subtype`），WP 前缀按实例 `version_stage_default=wp`，`seq` 由 `version_suffix_rule` 给出；`relation`（`is-preprint-of`、`has-preprint`、`is-version-of`）→ 版本关系声明；许可 = `license[]` 原串（含 `content-version`、`start`）经 `license_alias` 归一，权利由 `classify_rights()` 计算，mapper 不直接给 `shareable`；摘要（JATS）默认 `publisher_copyright`，未知即 `unknown` 不共享；SSRN 的 `https://www.uspto.gov/ip-policy/copyright-policy/copyright-basics` 映射为保留所有权利（非共享）；许可、权利、版本、关系四类字段带 `basis` 载荷路径。

**7 SCD**：可下推谓词 `from/until-created-date`（native）、`from-update-date`（native）、`from-index-date`（native，仅补漏）、`type`（native）、`update-type`（native，未复核）、`container-title`（emulated：本地拆分）；路由键 ISSN、前缀、member（native）；排序键 `created`；`rows ≤ 1000`，深翻只用 cursor（offset 上限未核）；不声明 `search` 与批量 `lookup`；成本模型按请求计（polite single 10/s、array 3/s 共享给全平台），补漏与更正任务单列预算。静态 SCD 由 `describe()` 从 manifest 生成，`derived_from` 比对差异为 0。

**8 合规**：策略引擎输入取 Crossref 主机信号：文档化 API 是；bulk 通道是（年度文件）；`api.crossref.org` robots 本批未复核（未核，由网关 robots 先行闸判定）；ToS 要求缓存、避免重复请求、不得多邮箱（tips 页与 2026-07-21 公告，见 §3）；TDM/AI 保留不适用于书目事实。书目元数据按事实（CC0 口径），摘要保留出版方或作者版权（长稿 C8）。各操作上限模式：`enumerate`、`increment` 为 `background`，`probe` 为 `background`。被服务来源叠加结构性上限：证据时效、`support_tier=登记` 不运行；⚑COMM 按名录定义只停用条款受限的那条通道（D-045），本族取的是 Crossref 书目事实，是否受被服务来源 ⚑COMM 约束由策略引擎按 SourceSpec 逐通道判定，本文不作放宽。无需书面确认；Metadata Plus 是否购买待询价（名录已知缺口）。

**9 全文**：不产出 `FulltextOption`，不下发配方。`license[]` 与 `link[]`（含 `intended-application: text-mining`）只作为声明交给 OA 层与用户侧配方排序（03 用户侧全文取回）；"在出版社打开"的 DOI 落地链接由 04/07 统一生成。平台永不请求 `link[]` 指向的出版商主机。

**10 测试**：四类 fixture（长稿 §15.1 分类）——正常页：`crossref.journal_works` 含 `next-cursor`、`crossref.prefix_works` posted-content、多条 `license` 与 JATS 摘要；空页：`total-results=0`；限流或错误：429、400 `validation-failure`、403；边界：窗口末页、cursor 过期、撤稿 `update-to`、ISSN 错配、`10.1101` 混合页、含逗号 container-title、SSRN 各种 license URL 各一条、medRxiv 异常 `version "0"` 不影响本族。契约测试：CT-01…CT-12 + FS-XD-01…FS-XD-09。黄金 NormRecord：DOI 作品级与版本级各一、每种权利类（CC BY、NC、保留所有权利、unknown）、撤稿 status_claim。属性测试：FS-XD-03 并集等价、补漏幂等、post_filter 与顺序无关。fixture 只经 staging 网关录制并脱敏，摘要换等长合成文本。

**11 探针与替补**：`structure`：`x-api-pool` 取值集合与各池 `x-rate-limit-limit`；`deprecation`：`x-rate-limit-type` 是否出现、access 页日期；`count`：每个 P0 委托固定过滤的 `total-results` 周计数（骤降归 `empty_body/count_drop`），index/created 放大比；`canary_query`：每个预印本前缀按 owner 与字符串前缀各查一次（前缀归属漂移）；`tos_hash`：tips 与 access 页。降级：探针红灯 ≤72 小时内修复，否则暂停受影响委托并启用替补。替补链：元数据 → OpenAlex API（`from_publication_date` 窗口，进美元预算）→ OpenAlex 季度快照与 `crossref_annual_file` 对账；生医预印本另有 Europe PMC `SRC:PPR`。

**12 运维**：新鲜度目标：新 DOI 创建后 ≤24 小时入库（main 03 设计目标）；SLO 建议 99% 的 P0 委托游标滞后 <36 小时（未核，V2 在线观测后定）；告警：429 比例、`cursor_expired` 重启数、`x-api-pool` 与 `request_class` 不一致、计数骤降、403；runbook：403 封禁（停、联系 Crossref 支持、核对 mailto 与 UA）、分池数值变化（改 manifest 书面值并重跑 FS-XD-02）、补漏预算超限（缩小 L 或降频）；`review_every`：P0 每月看健康、每季复核卡片；`points`：待一致性文档 P-12 定（未核）。

**13 已知坑与待决**：①分池生效日期两说，待核；②`/members` 归池两说，按 array 保守；③cursor 过期时间未核；④补漏放大只有一个样本，L 未实测；⑤刊级元数据错配（长稿 C11）；⑥出版商级摘要缺口（Elsevier 2025 年约 104 万篇仅 424 篇带摘要，长稿 C10），靠摘要补齐链；⑦SSRN 75.1% 记录的 license 指向 USPTO 页面，不是许可；Research Paper Series 已停、Data Feeds 2026-12 关闭（二手），Crossref 是唯一合规元数据来源；⑧bioRxiv 新前缀 `10.64898` 与 medRxiv 异常字段值；⑨ChemRxiv 平台迁移日期两说（2026-01-21 与 2026-03-09 新闻稿），旧 API 返回 CF 挑战，不得自动启用新 API；⑩`impl` 取 `custom_plan` 而非 `declarative` 的理由：委托编译与补漏双过滤超出路径模板词表。

## 7. 本族风险、坑与待决

- **单点上游**：本族承接约 92% 的核心 venue，Crossref 限额或政策变化会同时影响多数学科。缓解：集中限速、替补链两级、快照对账；Plus 采购作为生产 SLA 选项。
- **限额按邮箱计**：任何开发机、脚本若用同一部署邮箱直连 Crossref，会挤占生产预算；开发与 fixture 录制一律经 staging 网关（契约 fixture 政策）。
- **前缀归属漂移**：出版方转换平台或并购会改 owner prefix 与 member；`canary_query` 盯前缀归属，变化即降级该委托并开工单。
- **论文集拆分**：container-title 拼写变化会让论文漏进"未归类"；每届新会期须人工确认标题（SOP A 的核对步骤）。
- **更新类型覆盖**：`update-type` 取值（retraction 之外的 correction、withdrawal、expression_of_concern）未逐一核实；在 V0 以 fixture 固定。

## 怎么验收

- CL0：清单、卡片与证据齐；注册表 13 条、连接器 LC-01…LC-06 与 §3 族 lint 4 条通过；合规字段经第二人复核（CL0 出口条件）。
- CL1：FS-XD-01…FS-XD-09 与 CT-01…CT-12 在离线 CI 全过；每个 P0 实例有正常、空、错误、边界四类 fixture 与黄金 NormRecord。
- CL2：staging 经网关按当前策略许可的模式连续运行 ≥14 天，零 robots 违例、零挑战、零未声明主机；`x-api-pool` 与声明一致；合规复核仍有效；P0 委托游标滞后达卡片 §12 的 SLO 建议值（V0 实测后定）。
- V1 出口（CL3）：7 日增量回放零漏零重（03 V1 验收）；替补链演练一次；403 封禁与分池变化的 runbook 演练一次。

## 未决事项

- **待拍板 1**：DataCite 变体取方案 A 还是方案 B（§2.4；来源清单调研提出）。
- **待拍板 2**：NBER 零自动化后，`nber_wp` 最新通道改由本族 `10.3386` 的 created 水位承担，RePEc `nbr:nberwo` 作补充；影响 v2-P0 验收口径（NBER 条款 2026-08-01 起禁止未经许可的自动访问与数据挖掘）。
- **待拍板 3**：`ssrn_crossref` 桥接期结束后直接降为本族 `ssrn` 实例（来源清单调研建议），桥接只保留迁移测试。
- **待核**：分池生效日期、`/members` 归池、cursor 过期时间、polite 池头部、`update-type` 取值、L 与补漏预算（全部在 V0 实测）。
- **待契约确认**：`weekly_backfill`、`corrections` 已改由契约 `IncrementInput.mode` 区分；其 `window_set` 游标须落 05 按 `scope_key` 的进度表（契约待拍板 P-3）。
- **新增字段待在 [契约](../contract.md) 中确认**：`family_params.upstream_bucket`、`family_params.plus_token`、post_filter `version_suffix_rule` 与 `ssrn_abstract_id`、实例字段 `version_stage_default`、`abstract_expected`、`lag_bound_days`。

更细的材料：`git show v2-drafts:docs/plan/v2/03-sources-and-corpus-pipeline.md`（§5.3–5.4 族表与专有接口、§10.4 最新论文增量、§14.1 v1 去向）；[03 连接器九族](../../03-sources-and-corpus-pipeline.md#连接器九族与执行位置)；[支持名录](../../../../catalog/source-directory.md)。
