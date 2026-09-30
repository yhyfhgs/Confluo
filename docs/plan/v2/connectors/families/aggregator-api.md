---
title: aggregator_api 族：聚合器与学科库 API
status: draft
owner: opus5.5-primary
updated: 2026-09-30
---

# aggregator_api 族：聚合器与学科库 API

> 本文回答：聚合器与学科库的文档化 API（Europe PMC、INSPIRE、zbMATH Open、PubMed、PMC、DataCite、CORE 等）按什么族接口、清单字段、一致性套件与卡片接入，预算怎样记账、限速头怎样归一。结论：本族在 [ConnectorContract v1](../contract.md) 之上只加 `batch_lookup`、`query(PushdownQuery)`、`window` 与 `BudgetModel`，外加网关侧的 `RateLimitState`；28 个新写连接器中 P0 七张完整卡、P1 十张紧凑卡，其余只占总表一行；四个 v1 桥接连接器（OpenAlex、S2、Unpaywall、Crossref REST）的卡片在 [v1-bridge](v1-bridge.md)，本文只写目标形态。

## 要点

- **范围**：一源一连接器，文档化 REST、SPARQL 或 MCP；快照归 [bulk_snapshot](bulk-snapshot.md)，OAI 端点归 [oai_pmh](oai-pmh.md) 实例。
- **族接口**：`batch_lookup`（装箱、按 ID 对齐）、`query`（只翻译 SCD 声明的谓词）、`window`（逼近上限即拆窗）、`estimate_cost`。
- **预算**：沿用契约 `budget.unit`，补 `window`、`lanes`、`cost_model`、`shared_with`，提议加 `token`（CORE）；一个上游身份一个账户，禁止多 key 叠加（HC-10）。
- **限速头**：九种方言由网关按 `rate_dialect` 归一，只能收紧，与文档矛盾取严。
- **族套件** FS-AGG-01…FS-AGG-10，重点是"过滤生效"与"静默零"（Europe PMC `INDEX_DATE`、SCOAP3 日期参数实测静默返回 0 或全量）。
- **阻断的 P0**：`pubmed_eutils`（robots）以合成 fixture 做到 CL1 后待命、通道 deny（同[实施计划](../implementation-plan.md) W1）；`dblp_sparql` 待 D-050 核验，CL1 待命；`zbmath_open_api`（条款闸门）确认前录不到 REST fixture，停 CL0（U-10）；三者不阻塞 W1，上游变化写在各卡 §13。
- **用户侧元数据查询**：`nasa_ads_api`、`orcid_api`、`alphaxiv_mcp`、`lens_api` 在契约 v1 没有对应协议，只保留 W3u/W4u 占位、停在 CL0（待拍板 P-13，§2.7）。

## 1. 本族回答什么与适用边界

- **回答**：按 ID 补全（`lookup`）、查远端（`search`）、按日期窗口收新论文（`increment`、`enumerate`）时，怎样以最少请求、最低费用、不越过配额取到结构化元数据。`locate_fulltext` 只产 `oa_link` 或 `open_in_tab`；不做 `snapshot_import`。
- **分界**：[bulk_snapshot](bulk-snapshot.md) 管同源快照（`openalex_snapshot`、`pubmed_baseline`、`pmc_s3` 等），全量回填先走快照；[oai_pmh](oai-pmh.md) 管 zbMATH、DOAJ、PMC、HAL 的 OAI 端点（INSPIRE OAI 只是候选实例，待拍板）；[crossref_delegated](crossref-delegated.md) 是委托引擎，与 `crossref_rest` 共用一个账户；[site_special](site-special.md) 管单站 API（bioRxiv、PLOS、OSF、eLife）；[official_tdm_api](official-tdm-api.md) 管用户 key 的全文 API。
- **执行位置**：多数 `platform`；`nasa_ads_api`、`lens_api`、`alphaxiv_mcp`、`orcid_api` 为 `user`（§2.7）。

## 2. 族专有接口

通用部分（`PlatformConnector`、`RequestSpec`、`Step`、`CursorEnvelope`、错误矩阵、`FulltextOption`）见 [contract](../contract.md)。

### 2.1 协议

```python
# 设计伪代码 —— PlatformConnector 之上的族专有部分
class AggregatorApi(PlatformConnector):
    def batch_lookup(self, ids: list[Identifier], ctx: PlanCtx
                     ) -> Generator[RequestSpec, Step, TaskOutcome]: ...   # 按清单 batch 装箱；逐项隔离
    def query(self, q: PushdownQuery, ctx: PlanCtx
              ) -> Generator[RequestSpec, Step, TaskOutcome]: ...          # q 已由 04 按 SCD 放宽
    def window(self, w: DateWindow, ctx: PlanCtx
               ) -> Generator[RequestSpec, Step, TaskOutcome]: ...         # 逼近 result_cap 时二分拆窗
    def estimate_cost(self, endpoint_id: str, n_requests: int) -> CostEstimate: ...  # 纯函数
```

`plan()` 按 operation 分派；连接器不算预算余量，账本不足时网关不发请求、回送 `budget_exhausted`，连接器在页边界结束。`estimate_cost` 进 SCD 的 `cost` 块，供 [04 路由](../../04-retrieval-and-routing.md#路由选哪些源)使用。

### 2.2 PushdownQuery

```python
# 设计伪代码
@dataclass(frozen=True)
class PushdownQuery:
    endpoint_id: str
    text: KwExpr | None              # 只含 SCD kw.* 声明的形式
    filters: tuple[Predicate, ...]   # filter.date.* / venue / topic / type / oa / license / entity / relation
    sort: SortKey | None
    limit: int                       # ≤ 端点分页上限
    relaxed: tuple[RelaxNote, ...]   # 04 记录的放宽，供 U3 能力提示
    residual: tuple[Predicate, ...]  # 本地残差复核，连接器不看
```

- SCD 为 `none` 的能力出现在 `text` 或 `filters` 即 `config`（契约违例），不静默丢弃；Crossref 不声明 `search`（main 03）。
- `emulated` 由连接器拆请求再取并集，SCD 写上限与成本倍数：OpenAlex 单个 filter 的 OR 值 ≤100（长稿，未复核）；INSPIRE 单查询 ≤10,000 条须拆窗（见卡片）。本族保证 `native` 必下推、`none` 永不下推（FS-AGG-07），放宽的属性测试归 04。

### 2.3 batch_lookup

- 清单 `batch`：`max_ids`、`max_url_bytes`、`max_body_bytes`、`id_param`、`alignment ∈ by_id | positional_with_null`（S2 `/paper/batch` 对未知 ID 返回 null 元素 [https://api.semanticscholar.org/graph/v1/swagger.json, 2026-09-30]）。ID 先规范化再去重；缺项产出 `PageSignals.not_found`，不算 `parse`。
- 上限：S2 ≤500 id、≤10 MB（长稿，未复核）；v1 的 URL ≤2000 字符只是工程惯例（`_MAX_URL_CHARS`，`git show archive/v1:src/paper_crawler/adapters/openalex/adapter.py`）；其余未核，从 100 起步。

### 2.4 预算模型 BudgetModel

预算是 [D-055](../../../decision-log.md)"全局配额账本"的一个账户：令牌桶管"多快"，账本管"窗口内总量"。

```python
# 设计伪代码 —— 契约 endpoints[].budget 的族扩展
@dataclass(frozen=True)
class BudgetModel:
    account: str                  # 如 openalex.usd；一个上游身份一个账户（HC-10）
    unit: Literal["usd", "request", "key_rps", "ip_quota", "bytes", "token"]   # token 为本族提议
    window: Window                # utc_day | rolling_300s | fixed_5s | minute | month
    ceiling: Decimal              # 书面上限，带 evidence
    planned_daily: Decimal        # 共用账户之和 ≤ 日折算上限 × 0.8
    lanes: Mapping[Lane, float]   # interactive / harvest / enrich 份额
    cost_model: Mapping[str, Decimal]   # endpoint_id → 单价
    shared_with: tuple[str, ...]
```

| unit | 来源（账户维） | 书面上限 | 耗尽处置 |
|---|---|---|---|
| `usd` | OpenAlex（部署 key） | UTC 日：免费 key $1、无 key $0.10；列表 $0.10/千次、搜索 $1/千次、单实体免费 [https://help.openalex.org/access/example-costs/, 2026-09-30] | 交互道占 80%，80% 抬影子价格，100% 当日退出交互路由（[04](../../04-retrieval-and-routing.md#稳定性工程)）；enrich 只用免费单实体，不经 API 收割 |
| `key_rps` | S2、NCBI（部署 key） | S2 1 RPS 全端点；NCBI 有 key 10 rps（出处见 §5.1 与 `pubmed_eutils`） | 只排队，全 worker 一桶 |
| `ip_quota` | INSPIRE、OpenCitations、DataCite、HF、Wikidata（出口 IP） | 15 次/5 s；180 次/min；识别档 1,000 次/5 min；匿名 500 次/5 min；每 60 s 处理时间 ≤60 s、5 并发（出处见各卡与 §5） | 窗口内停发；429 全账户退避（§2.5） |
| `token` | CORE（部署 key） | 个人 1,000 token/日，复杂查询 3–5 token（见卡片） | 页边界停，延到下一窗口 |
| `request` | Unpaywall（部署邮箱）；ADS（用户 token） | 10 万次/日（◐二手）；ADS search 5,000/日（见卡片） | 同上；ADS 在用户侧计，不进平台账本 |

- **记账**：网关按 `cost_model` 预扣，再以服务端余量校正，取更紧者；指标 `connector_budget_used{account}` 由网关发出。不按用户开 key、不叠加 key、不轮换出口 IP（[HC-10](../../08-compliance-security-privacy.md#合规硬约束hc)）；personal 部署见契约 P-8。
- **共用**：`crossref_rest` 与 `crossref_delegated` 共用 `crossref.mailto`；`pubmed_eutils`、`pmc_bioc`、`pubtator3_api`、`icite_api` 先按共用 `ncbi.key` 取严（iCite 在 NIH 主机 `icite.od.nih.gov`，是否同一身份待核，U-7）。

### 2.5 限速头归一 RateLimitState

网关按 `endpoints[].rate_dialect` 解析响应头；连接器在 `PageSignals.rate_headers` 只读到归一值，不参与调度。

```python
# 设计伪代码
@dataclass(frozen=True)
class RateLimitState:
    dialect: str
    scope: Literal["ip", "key", "email", "user", "unknown"]
    unit: Literal["request", "usd", "token", "record"]
    limit: Decimal | None; remaining: Decimal | None; window_s: int | None
    reset_at: datetime | None        # UTC 绝对时刻
    retry_after_s: float | None; concurrency_limit: int | None
    pool: str | None                 # Crossref x-api-pool
    cost_last: Decimal | None        # OpenAlex 单次费用
```

| rate_dialect | 来源 | 头与换算（2026-09-30 实测或文档，URL 见各卡与 §5.1） |
|---|---|---|
| `crossref_pool` | crossref | `x-api-pool`、`x-rate-limit-limit`、`x-rate-limit-interval`、`x-concurrency-limit`；公告的 `x-rate-limit-type` 仍缺 |
| `openalex_usd` | openalex | `x-ratelimit-remaining-usd`、`x-ratelimit-cost-usd`、`x-ratelimit-reset`（到 UTC 午夜的秒数）、`meta.cost_usd` |
| `ietf_draft` | hf_papers | `RateLimit: "api";r=…;t=…`、`RateLimit-Policy: "fixed window";"api";q=500;w=300` |
| `x_ratelimit_epoch` | nasa_ads_scix | `X-RateLimit-Limit/Remaining/Reset`，Reset 为 UTC 时间戳 |
| `x_ratelimit_iso` | core | `X-RateLimit-Limit/Remaining`（文档写作 `X-RateLimitRemaining`，解析容错）、`X-RateLimit-Retry-After` 为 ISO 时间戳 |
| `lens_monthly` | lens | 每分钟与每月的请求余量、每月记录余量、`…-retry-after-seconds` |
| `used_count` | openaire | `x-ratelimit-limit`、`x-ratelimit-used`（匿名实测 limit 7199，与文档匿名 60 次/h 不符） |
| `retry_after_only` | wikidata、inspire_hep | 只在 429 时给 `Retry-After`（Wikidata）或 `X-RateLimit-*`（INSPIRE 只声明头名，429 时取值未核） |
| `none` | europe_pmc、datacite、icite、osti_gov、econbiz | 无头，只靠书面值与 429 |

规则：头值高于书面上限时忽略，低于时下调令牌桶（AIMD 只降不超）；与文档矛盾取严并告警（OpenAIRE 按 60 次/h）；头名按方言表匹配，新头只记录；任一 worker 收到 429，整个账户先按 `retry_after_s`、再按 `reset_at` 退避，都没有才退避到窗口结束（契约 §7"按头退避"；OpenAlex 预算耗尽走 §2.6 的 `budget_exhausted`）。用户侧来源（ADS、Lens）由执行器复用同一解析库，结果不回平台。

### 2.6 状态码覆盖与身份参数

契约 `status_overrides` 在本族的已知行（每行配 fixture 与一条 `upstream_facts`；`plan_required`、`terms_gate` 是本族提议的 `config` 子码，契约未列，U-2）：

| 来源 | 触发 | error_class | 依据 |
|---|---|---|---|
| openalex | 429 且体含 "Plan upgrade required"（付费过滤） | `config`（`plan_required`，不重试） | 实测 [https://api.openalex.org/works?filter=from_created_date:2026-09-28, 2026-09-30] |
| openalex | 429 且 `remaining-usd` ≤0；402 | `budget_exhausted` | [https://help.openalex.org/api-reference/authentication, 2026-09-30]；402 为 v1 所见，未核，核实并有 fixture 前不登记 |
| s2 | 无 key 时 404 | runner 见 `AuthRef` 缺失即 `config`，不发请求 | v1 教训 L15、L21 |
| unpaywall | 404；422 | 404 进 `legit_status`、产出 `PageSignals.not_found`（非 error_class）；422（缺 email）为 `config` | §5.1；422 为长稿实测 |
| zbmath_open | 307 到条款页或返回 HTML | `config`（`terms_gate`），不自动"同意" | 实测 [https://api.zbmath.org/, 2026-09-30] |
| scoap3_repo | 出现 401 | 不设覆盖：匿名按契约默认 `challenge` 从严；启用伙伴 token（`auth: deployment/*`）后默认即 `config` | 伙伴页称须注册 token [https://repo.scoap3.org/partners, 2026-09-30]；401 未实测 |
| nasa_ads_scix | 401（无效 token） | `auth_expired`（用户侧执行器判定） | 401 语义未逐字核 [https://github.com/adsabs/adsabs-dev-api, 2026-09-30]；合成 fixture |

身份参数 `mailto`（Crossref、DataCite）、`email`（Unpaywall）、`tool`/`email`（NCBI）是部署身份：建议 `identity_param{name, from: deployment_contact}` 由网关注入，RequestSpec 中出现即 `config`（U-2）。

### 2.7 用户侧连接器

`nasa_ads_api`、`lens_api`、`alphaxiv_mcp`、`orcid_api` 的凭证是个人 token 或 OAuth，只能 `exec_side: user`，结果归用户私域（[08 执行位置与凭证](../../08-compliance-security-privacy.md#执行位置与凭证)）。契约 v1 的 `RecipeProvider` 只产 `FulltextRecipe`，本族建议新增 `QueryRecipe`：约束同 FulltextRecipe（封闭步骤、占位符只在头部、字面量主机、`limits` 只能更严），结果不回传平台、不进跨用户统计。定案前（U-1，即契约待拍板 P-13）四者停在 CL0，实施计划只保留 W3u/W4u 波次占位。

## 3. 实例与清单字段

本族默认不用 `ConnectorInstance`；`impl` 默认 `mapper`，需要拆窗、装箱或多端点编排取 `custom_plan`，理由写在卡片 §13。契约通用字段之外增加：

```yaml
# 设计伪代码 —— registry/connectors/inspire_rest.yaml 的本族字段（节选）
endpoints:
  - endpoint_id: inspire_hep.literature_search
    request_class: rest                 # 上游池类；INSPIRE 不分池
    rate_dialect: retry_after_only
    budget: {account: inspire.ip, unit: ip_quota, window: fixed_5s, ceiling: 15, planned_daily: 2000,
             lanes: {harvest: 0.7, interactive: 0.2, enrich: 0.1}, evidence: ev_inspire_rate}
    result_cap: {max_results_per_query: 10000, window_split: bisect_by_date, min_window: PT1H}   # 小时精度未核
    filter_effect_probe: {query: "du>{yesterday}", expect: "0 < hits < total"}
    incr_fields: {first_seen: null, last_modified: du}
    field_rights: {whitelist_ref: inspire_cc0_fields}   # 名单未核
```

| 字段 | 含义与 lint |
|---|---|
| `rate_dialect` | §2.5 方言名；必填，`none` 须附"无头"证据 |
| `budget` 扩展 | §2.4 的 `window`、`lanes`、`cost_model`、`shared_with`；`account` 全库唯一对应一个身份 |
| `batch` | §2.3 装箱规格；有批量 LOOKUP 时必填，无证据取保守值 |
| `result_cap` | 单查询上限与拆窗策略；分页有上限时必填 |
| `filter_effect_probe` | 窄窗口命中须 >0 且小于全量；有过滤时必填；编译为一条 `canary_query` 探针 |
| `incr_fields` | `first_seen` 与 `last_modified` 分开声明，至少一个非空 |
| `identity_param` | 部署身份参数名；值不得出现在清单与 fixture |
| `same_origin_as` | 同源来源（Unpaywall 与 OpenAlex），许可投票算一票 |
| `field_rights` | 字段级许可白名单；有字段级限制时必填 |

## 4. 族一致性套件

通用契约测试见 [conformance-and-testing](../conformance-and-testing.md)；本族另加以下规则，离线回放，按"连接器 × fixture"参数化；编号按[一致性文档](../conformance-and-testing.md) §1.2 口径写作 `FS-AGG-NN`。

| rule_id | 断言 | 必备 fixture |
|---|---|---|
| FS-AGG-01 过滤生效 | 窄窗口命中 >0 且显著小于全量，否则 `empty_body/count_drop` 或 `config` | 窄窗口与全量计数；反例 EPMC、SCOAP3 |
| FS-AGG-02 拆窗 | 命中 ≥ `result_cap` 时二分，子窗并集等于真值 | 合成"恰好 10,000"页 |
| FS-AGG-03 批量对齐 | 不超装箱上限；按 `alignment` 回配；未知 ID 为 `not_found` | 含 null 槽或缺项的批 |
| FS-AGG-04 预算 | 账本不足不发请求、页边界停、游标不越过已提交页 | 耗尽与计费头样本 |
| FS-AGG-05 方言 | 各 `rate_dialect` 解析结果等于黄金值；高于书面上限的头被忽略 | 每方言一份头 |
| FS-AGG-06 覆盖表 | `status_overrides` 每行命中预期 `error_class` | 每行一个 |
| FS-AGG-07 下推 | `native` 谓词必进请求，`none` 永不出现 | 由 SCD 生成的查询 |
| FS-AGG-08 身份与凭证 | 请求与 fixture 无身份参数值、key、邮箱 | 全部 |
| FS-AGG-09 同源 | `same_origin_as` 在许可投票中只算一票 | 同 DOI 的两源样本 |
| FS-AGG-10 静默零 | 工作日日窗命中 0：该页不给 `next_cursor`（水位不动），由 `canary_query` 判 `empty_body/count_drop` 并告警，连接器不自判错误类 | 工作日零命中样本 |

## 5. 连接器清单总表

以第一阶段清单为准：新写 28 个，另 4 个 v1 桥接以本族为目标（§5.1）。当前 CL 均为"—"，均无 v1 复用；`impl` 见卡片（P2 默认 mapper，用户侧 `recipe_provider` + `declarative`）；用户侧元数据查询 4 个（`nasa_ads_api`、`orcid_api`、`alphaxiv_mcp`、`lens_api`）契约 v1 无对应协议，只保留波次占位、停在 CL0（待拍板 P-13）；P0 完整卡、P1 紧凑卡、其余按需补卡；人日为清单粗估；波次同 [implementation-plan](../implementation-plan.md)，用户侧记 W3u/W4u（同矩阵），P1 平台侧分 V3、V5 两批。

| connector_id | 服务来源 | 优先级 | 波次 | exec | 人日 | 前置依赖 | 目标 CL |
|---|---|---|---|---|---:|---|---|
| [`europe_pmc_rest`](#europe_pmc_rest) | europe_pmc | P0 | W0 | platform | 2 | EBI 交互用量约定 | CL3（V1） |
| [`inspire_rest`](#inspire_rest) | inspire_hep | P0 | W1 | platform | 2 | — | CL3（V1） |
| [`zbmath_open_api`](#zbmath_open_api) | zbmath_open | P0 | W1 | platform | 2 | FIZ 书面确认；⚑SA ⚑COMM | CL3（V1；确认前停 CL0，U-10） |
| [`pubmed_eutils`](#pubmed_eutils) | pubmed | P0 | W1 | platform | 1.5 | ⚑ROBOTS；D-049 接受并登记例外 | CL1 待命（确认后 CL3） |
| [`pmc_bioc`](#pmc_bioc) | pmc | P0 | W1 | platform | 1.5 | 不用 E-utilities | CL3（V1） |
| [`hf_papers_api`](#hf_papers_api) | hf_papers | P0 信号层 | W1 | platform | 1.5 | ⚑RECHECK（商用、长期缓存） | CL3（V1） |
| [`dblp_sparql`](#dblp_sparql) | dblp | P0 快照形态 | W1 | platform | 1 | D-050 核验端点 | CL1 待命（核验后 CL3） |
| [`core_api`](#core_api) | core | P1 | W3 | platform | 2 | ⚑LIC ⚑COMM，许可前不启用 | CL3（V3；许可前 CL0） |
| [`datacite_rest`](#datacite_rest) | datacite、lipics_drops | P1 | W3 | platform | 2 | — | CL3（V3） |
| [`doaj_api`](#doaj_api) | doaj | P1 | W3 | platform | 1.5 | — | CL3（V3） |
| [`econbiz_api`](#econbiz_api) | econbiz | P1 | W3 | platform | 1.5 | 条款禁大规模复制 | CL3（V3） |
| [`icite_api`](#icite_api) | icite | P1 | W3 | platform | 1 | ⚑RECHECK | CL3（V5） |
| [`nasa_ads_api`](#nasa_ads_api) | nasa_ads_scix | P1 | W3u | user | 1.5 | ⚑DRIFT；U-1；扩展或 pc-agent | CL0（待拍板 P-13） |
| [`opencitations_api`](#opencitations_api) | opencitations | P1 | W3 | platform | 1.5 | — | CL3（V3） |
| [`orcid_api`](#orcid_api) | orcid | P1 | W3u | user（修正） | 1.5 | ⚑ROBOTS ⚑COMM；U-1；V3 账号 | CL0（待拍板 P-13） |
| [`pubtator3_api`](#pubtator3_api) | pubtator3 | P1 | W3 | platform | 1 | ⚑RECHECK | CL3（V5） |
| [`scoap3_api`](#scoap3_api) | scoap3_repo | P1 | W3 | platform | 1.5 | 伙伴 token | CL3（V5） |
| `alphaxiv_mcp` | alphaxiv | P2 | W4u | user | 1 | 许可未取得；MCP 用户自连；U-1 | CL0（待拍板 P-13） |
| `fraser_api` | fraser | P2 | W4 | platform | 1.5 | ⚑RECHECK；接口未核；Crawl-delay 10 | CL2+ 按需 |
| `hal_api` | hal | P2 | W4 | platform | 1.5 | ⚑ROBOTS；OAI 非商用（U-9）；先经 CORE、OpenAlex | CL2+ 按需 |
| `jstage_webapi` | jstage | P2 登记 | 不排 | platform | 2 | ⚑COMM；来源为登记 | CL0 |
| `open_policy_finder_api` | open_policy_finder | P2 | W4 | platform | 1 | ⚑COMM；新 API 2026-02-11，内容 CC BY-NC-ND | CL2+ 按需 |
| `openaire_api` | openaire | P2 | W4 | platform | 1.5 | 头与文档矛盾，按 60 次/h | CL2+ 按需 |
| `osti_api` | osti_gov | P2 | W4 | platform | 1.5 | ⚑RECHECK；`entry_date` 语义未核 | CL2+ 按需 |
| `pubchem_pug_rest` | pubchem | P2 | W4 | platform | 1.5 | ⚑ROBOTS（`/rest/pug/` 禁） | CL2+ 确认后 |
| `scielo_articlemeta` | scielo | P2 登记 | 不排 | platform | 2 | 来源为登记；接口未复核 | CL0 |
| `wikidata_sparql` | wikidata | P2 | W4 | platform | 1.5 | UA 合规；限额见 §2.4 | CL2+ 按需 |
| `lens_api` | lens | metadata-only | W4u | user | 1 | 用户机构 token；须展示 Lens 标志；U-1 | CL0（待拍板 P-13） |

P2 事实出处（2026-09-30 核对）：[wikidata](https://www.mediawiki.org/wiki/Wikidata_Query_Service/User_Manual)、[openaire](https://graph.openaire.eu/docs/apis/terms/)、[hal](https://api.archives-ouvertes.fr/docs/oai)、[osti](https://www.osti.gov/api/v1/docs)、[open_policy_finder](https://openpolicyfinder.jisc.ac.uk/whats-new)、[fraser](https://fraser.stlouisfed.org/api-documentation)、[lens](https://docs.api.lens.org/)；pubchem 为 robots 实测；alphaxiv、scielo、jstage 未复核。

### 5.1 v1 桥接连接器在本族的目标形态

卡片在 [v1-bridge](v1-bridge.md)；这里只写移植后的形态，供移植卡对照。

| connector_id | 目标形态 | 关键事实 |
|---|---|---|
| [`openalex_api`](v1-bridge.md#openalex_api) | `work_single`（免费）、`works_list`（$0.0001/次）、`works_search`（$0.001/次）；`per_page` ≤100；只做 lookup 与 enrich，增量靠快照与 Crossref；`count` 探针盯 `meta.count` | `per_page=200` 已标弃用 [https://help.openalex.org/api/paging/, 2026-09-30]；`from_created_date` 返回 429；`meta.count` 4 天少约 62.7 万（原因未核）；快照带 `deleted_ids` [https://help.openalex.org/access/snapshot/, 2026-09-30] |
| [`s2_api`](v1-bridge.md#s2_api) | `s2.key` 1 RPS 共用；优先 `/paper/batch` 与 bulk search；无 key 不发请求；嵌入与 TLDR 走 `s2_datasets` | 匿名共享 1000 RPS [https://www.semanticscholar.org/product/api, 2026-09-30]；许可可随时终止、商用未明示 [https://www.semanticscholar.org/product/api/license, 2026-09-30] |
| [`unpaywall_api`](v1-bridge.md#unpaywall_api) | 兼容层：OpenAlex 无 OA 位置时才补查；`email` 走 `identity_param`；`same_origin_as: openalex` | 已并入 OpenAlex、"不退役"，只含 Crossref DOI [https://help.openalex.org/access/unpaywall/, 2026-09-30] |
| [`crossref_rest`](v1-bridge.md#crossref_rest) | 与 `crossref_delegated` 共用 `crossref.mailto` 与 `crossref_pool`；请求类 `single`、`array`（对应 `x-api-pool`，与 [crossref-delegated](crossref-delegated.md) 同）；SCD 不声明 `search` | 单条 public 5/s、polite 10/s，列表 1/s、3/s，按邮箱计限 [https://community.crossref.org/t/refining-rest-api-limits-for-improved-stability-and-reliability/16137, 2026-09-30]；分池生效日期两说（2026-07-21 与 2025-12-01），待核 |

移植沿用同一 `connector_id`（同 [v1-bridge](v1-bridge.md) 口径：桥接为 0.x，移植升 1.0.0，`impl` 改为 `mapper` 或 `custom_plan`）；与契约"bridge 转 CLX、id 永不复用"的衔接未定，若须另立 id 则原生连接器另取名（U-3）。

## 6. 连接器卡片

共同约定：owner 与 backup_owner 待指派（P0 两人在岗）；`contract_version` 1；`connector_version` 从 0.1.0 起，`migrate_cursor` 首版无；`lifecycle` active；当前 CL 均为 —；`review_every` 按卡片模板（P0 月看健康、季复核卡片，P1 季复核）；无持久游标的不适用 `late_path`、`window_max`；水位类未写 `ordered` 的一律 `false`、区间 `[from, until]`，整窗完成后推进。

### europe_pmc_rest

**1 身份**：`impl` mapper；目标 CL3（V1）；服务 `europe_pmc`；W0 参考连接器。

**2 通道与操作**（platform）：metadata `enumerate`、`lookup`、`search`；latest `increment`；fulltext `locate_fulltext`。EBI 用量约定前 `lookup`、`search` 不进交互路由（[名录已知缺口](../../../../catalog/source-directory.md#已知缺口)）。

**3 上游接口事实**：`search` 实测 `version` 6.9，`FIRST_IDATE:2026-09-29` 命中 1,785；长稿的修订增量 `INDEX_DATE:[…]` 命中 0 且不报错 [https://www.ebi.ac.uk/europepmc/webservices/rest/search, 2026-09-30]。`pageSize` ≤1,000（二手）；无认证；限速数值未公布（未核），无限速头。robots `Crawl-Delay: 10`、不禁 REST [https://www.ebi.ac.uk/robots.txt, 2026-09-30]；文档页对抓取 403；bulk 主机 robots 全禁（归 `europe_pmc_bulk`）。

**4 请求声明**：`europe_pmc.search`（rest，`www.ebi.ac.uk`）；令牌桶全平台最小间隔 10 s；账户 `epmc.requests`；`rate_dialect: none`；Expectation JSON、root `resultList`，空结果只在游标末页合法。

**5 游标与增量**：`date_watermark`，`FIRST_IDATE`，粒度日，`overlap` P2D，`window_max` P1D，`lag_bound` 未核，`until` 固定为 UTC 昨日；`late_path` 先取 `weekly_index_backfill`（每周回看 14 天），bulk 获确认后改 `snapshot_reconcile`（契约示例取后者）；`cursorMark` 只进 `continuation`；删除无通知；撤稿看 `pubTypeList`（取值未核）。

**6 映射**：mapper `epmc_json`；`source_key` = `source` + `id`；`pmid`、`pmcid`、`doi`（版本级）、`ppr`；PPR 为 preprint，作者手稿为 am，带 `journalInfo` 为 vor；摘要经 `classify_rights()`：MED 默认 B 类，CC 单篇 open（[03 摘要补齐链](../../03-sources-and-corpus-pipeline.md#摘要补齐链)）。

**7 SCD**：`incr.since`、`kw.bool`、`kw.field.section.*`、`filter.entity.*`、`filter.relation.*`、`filter.license` native（后五项未复核）；每页 1,000；成本 0。

**8 合规**：文档化 API；robots 允许；OA 子集以外内容不得自动批量下载（二手）；上限 metadata、latest `background`，交互待 EBI，非 OA 全文 `link_only`。

**9 全文**：OA 且许可在白名单时产 `oa_link`，其余 `open_in_tab`。

**10 测试**：首页、末页空结果、撤稿记录、工作日零命中负例；黄金 MED、PMC、PPR；FS-AGG-01、FS-AGG-10；`cursorMark` 失效重启后并集不变。

**11 探针与替补**：`epmc.structure`、`epmc.silent_zero`、`epmc.robots`、周命中 `count`；静默零即停推水位。替补 `crossref_delegated` → `openalex_api` → `pubmed_eutils`（确认后）。

**12 运维**：新鲜度 ≤48 h；SLO `p0_latest`；告警：零命中、`version` 变化、首次 429。

**13 已知坑与待决**：修订增量字段未知（与长稿不同）；`email` 参数现状未核；同篇多 `source` 按 `source` + `id` 去重。

### inspire_rest

**1 身份**：`impl` custom_plan（拆窗）；目标 CL3（V1）；服务 `inspire_hep`；W1。

**2 通道与操作**（platform）：metadata `enumerate`、`lookup`、`search`；latest `increment`；无全文。

**3 上游接口事实**：每 IP 每 5 s 15 次，超额 429；`size` ≤1,000，单查询 ≤10,000；多数元数据 CC0，"restrictions apply to some fields" [https://github.com/inspirehep/rest-api-doc, 2026-09-30]。`q=du>2026-09-28` 命中 3,377，记录带 `created`、`updated`；正常响应无 `X-RateLimit-*` [https://inspirehep.net/api/literature, 2026-09-30]。OAI（`deletedRecord=no`）作回填替补 [https://inspirehep.net/api/oai2d?verb=Identify, 2026-09-30]；robots 不禁 API 路径 [https://inspirehep.net/robots.txt, 2026-09-30]。

**4 请求声明**：`inspire_hep.literature_search`、`inspire_hep.literature_record`（`inspirehep.net`）共用 `inspire.ip`；起步取上限 1/3；`rate_dialect: retry_after_only`；`fields=` 只取白名单字段。

**5 游标与增量**：`date_watermark`，`du`，粒度日，`overlap` P1D，`window_max` P1D；≥10,000 二分（小时精度未核，不行则该日走 OAI）；`late_path: none`；`created` 区分新论文与修订；`deleted` 字段未核。

**6 映射**：`source_key` = `control_number`；DOI（版本级）、arXiv id、recid（`work_assertion`）；只有 arXiv 为 preprint，有期刊信息为 vor；白名单外字段不进共享层；摘要按 `abstracts[].source` 定权利。

**7 SCD**：`kw.bool`、`filter.date.updated`、`sort.recency` native；`id.lookup.{doi, arxiv, inspire}`；成本 0。

**8 合规**：文档化；robots 允许；字段级限制待核；上限 metadata、latest `background`，交互 `on_demand`。

**9 全文**：无。

**10 测试**：首页、末页、429、单条、合成"恰好 10,000"页；黄金：期刊文章、仅预印本、会议论文；FS-AGG-02、FS-AGG-05。

**11 探针与替补**：`canary_query`（`du>昨日` >0）、`structure`（`links` 键与上限）、`robots`。替补 `arxiv_oai` → `crossref_delegated` → `scoap3_api`。

**12 运维**：新鲜度 ≤36 h；429 率与拆窗次数进 O2。

**13 已知坑与待决**：超上限静默截断；被拒也计额（长稿）；`dois` 可指向非 HEP 期刊；与长稿不同：OAI 可用、robots 禁止项增多；OAI 回填须先在 oai_pmh 补 `inspire_hep` 实例（清单未列，见 [oai-pmh](oai-pmh.md) 候选实例）。

### zbmath_open_api

**1 身份**：`impl` mapper；目标 CL3（V1，同实施计划）；FIZ 书面确认是 G1 前提，确认前停在 CL0（U-10）；服务 `zbmath_open`；W1。

**2 通道与操作**（platform）：metadata `lookup`、`search`；latest 由 oai_pmh 实例承担；无全文。

**3 上游接口事实**：REST 根路径返回"Terms & Conditions"同意页，`/openapi.json` 返回 307 [https://api.zbmath.org/, 2026-09-30]；条款 2021-06 版授权"develop and test software applications"，数据 CC BY-SA，"reasonable rate"无数值 [https://api.zbmath.org/static/terms-and-conditions.html, 2026-09-30]；OAI `deletedRecord` no、秒级 [https://oai.zbmath.org/v1/?verb=Identify, 2026-09-30]；KG dump 约半年一版，归 `zbmath_kg_dump` [https://arxiv.org/html/2609.00969, 2026-09-30]。

**4 请求声明**：`zbmath_open.document`、`zbmath_open.search`（`api.zbmath.org`，307 不跟随）；账户 `zbmath.ip`，串行、间隔 1 s（建议值）；`rate_dialect: none`；收到 HTML 即 `config`（本族提议子码 `terms_gate`，契约未列，U-2）。

**5 游标与增量**：无持久游标；增量见 [oai-pmh 族](oai-pmh.md)。

**6 映射**：zbMATH id（作品级）、DOI（版本级）、MSC 码（码表 CC BY-NC-SA，默认不加载）；`field_rights` 标 ShareAlike；评论不进共享层。

**7 SCD**：`id.lookup.{doi, zbmath}`、`filter.topic.msc`（未复核）；成本 0。

**8 合规**：`robots.txt` 返回 307，口径待复核（U-8）；⚑SA ⚑COMM；上限：FIZ 书面确认前 `deny`，确认后 `on_demand`。

**9 全文**：无。

**10 测试**：条款页 HTML 负例；REST JSON 在闸门机制确认后录制；FS-AGG-06。

**11 探针与替补**：`tos_hash`（条款页与 307 目标）、`structure`。替补 `crossref_delegated` → `oai_pmh`（`centre_mersenne_numdam` 实例）→ `arxiv_oai`。

**12 运维**：只计补查成功率。

**13 已知坑与待决**："develop and test"是否覆盖生产收割与再分发须 FIZ 确认；禁止自动"同意"；与长稿不同：条款闸门、`deletedRecord=no`。

### pubmed_eutils

**1 身份**：`impl` custom_plan（ESearch→EFetch 两步与 `WebEnv` 编排）；目标 CL3（D-049 接受并登记例外后）；服务 `pubmed`；W1，阻断期以合成 fixture 做到 CL1 后待命（同实施计划）。

**2 通道与操作**（platform）：metadata `lookup`、`search`（`on_demand`）；latest `increment` 只在 NCBI 书面确认后，主增量走 `pubmed_baseline`；无全文。

**3 上游接口事实**：无 key 每 IP 超 3 rps 报错，有 key 10 rps [https://ncbiinsights.ncbi.nlm.nih.gov/2017/11/02/new-api-keys-for-the-e-utilities, 2026-09-30]；eutils 主机 robots `Disallow: /`（实测）；文档页返回 reCAPTCHA [https://www.ncbi.nlm.nih.gov/books/NBK25497/, 2026-09-30]；`tool`/`email` 与 key 跨 IP 合并计为长稿说法，未复核；2027 baseline 新增 `IndexingMethod="NotIndexed"` [https://www.nlm.nih.gov/rss/auto/PubMedNews.rss, 2026-09-30]。

**4 请求声明**：`pubmed.esearch`、`pubmed.efetch`（POST 批）、`pubmed.esummary`（`eutils.ncbi.nlm.nih.gov`）；账户 `ncbi.key`（起步 ≤3 rps）；`identity_param` 为 `tool`、`email`；错误元素写法未核。

**5 游标与增量**：`date_watermark`，`[crdt]`，粒度日，`overlap` P2D，`window_max` P1D，`late_path: none`；`WebEnv` 只进 `continuation`；ESearch 上限未核，按 FS-AGG-02 拆窗；修订与删除由 `pubmed_baseline` 的 updatefiles 承担。

**6 映射**：与 `pubmed_baseline` 共用 mapper `pubmed_xml` 与黄金；撤稿与勘误写 `status_claims`；摘要默认 B 类；"Courtesy of NLM"由来源字段渲染（HC-24）。

**7 SCD**：`kw.bool`、`filter.date.created` native；`id.lookup.pmid`。

**8 合规**：⚑ROBOTS；D-049 接受前连按需也不做（[03 各学科接入计划](../../03-sources-and-corpus-pipeline.md#各学科接入计划)），上限 `deny`；接受且登记例外附表后 `lookup` 为 `on_demand`；后台须书面确认（PolicyOverride ≤12 个月，HC-31）。

**9 全文**：无。

**10 测试**：ESearch、EFetch 批（含撤稿与 `NotIndexed`）、超速错误体（确认后录）；FS-AGG-02、FS-AGG-06、FS-AGG-08。

**11 探针与替补**：`robots`（放宽只提"待评审"）、`structure`（DTD 与枚举）；文档页不设自动探针。替补 `europe_pmc_rest`（`source=MED`）。

**12 运维**：确认后新鲜度 ≤48 h；年初 MeSH 重标引预留额度。

**13 已知坑与待决**：任何探针与调研代理不得访问 NCBI 文档页；与长稿不同：2026 baseline 1 月 30 日才发布。

### pmc_bioc

**1 身份**：`impl` mapper；目标 CL3（V1）；服务 `pmc`；W1。

**2 通道与操作**（platform）：metadata `lookup`（ID Converter 互转 PMID、PMCID、DOI；BioC 取结构化 OA 文本）；fulltext `locate_fulltext`；增量归 `pmc_s3` 与 oai_pmh 实例。

**3 上游接口事实**：自动化只许 S3、OAI-PMH、E-utilities、BioC、ID Converter、Citation Exporter [https://pmc.ncbi.nlm.nih.gov/tools/developers/, 2026-09-30]；OA Web Service 2026-08-25 下线、旧 FTP 已删 [https://pmc.ncbi.nlm.nih.gov/tools/oa-service/, 2026-09-30]；pmc 主机 robots `Allow: /api/`、`/tools/`，`Crawl-delay: 1` [https://pmc.ncbi.nlm.nih.gov/robots.txt, 2026-09-30]；BioC 主机限速与 robots 未核。

**4 请求声明**：`pmc.idconv`（批，`pmc.ncbi.nlm.nih.gov`）、`pmc.bioc`（`www.ncbi.nlm.nih.gov`）；间隔 1 s；账户 `ncbi.key`（共用，U-7）；`rate_dialect: none`；不声明 E-utilities。

**5 游标与增量**：无持久游标。

**6 映射**：PMCID + 版本（版本级）、PMID、DOI；`license_code` 的 `TDM` 值不可再分发 [https://pmc-oa-opendata.s3.amazonaws.com/README.txt, 2026-09-30]；`is_retracted` 写 `status_claims`；BioC 文本只在许可白名单内且 `features.oa_shared_cache` 打开时入共享层（HC-05）。

**7 SCD**：`id.lookup.{pmid, pmcid, doi}`；批量上限未核；成本 0。

**8 合规**：BioC 主机 robots 在 CL0 出口前补证据；上限 `on_demand` 与 enrich；再分发须保持最新、只分发许可允许的数据。

**9 全文**：许可允许时产 `oa_link`，其余 `open_in_tab`。

**10 测试**：ID Converter 批（含未知 ID）、BioC JSON、非商用与 `TDM` 样本；FS-AGG-03、FS-AGG-08、FS-AGG-09。

**11 探针与替补**：`structure`、`robots`（两主机）、`deprecation`。替补 `pmc_s3`、`europe_pmc_rest`。

**12 运维**：SLO 以补查成功率计。

**13 已知坑与待决**：长稿与 v1 基于 OA Web Service、`oa_file_list.csv` 的写法失效；`license_code=TDM` 为新值。

### hf_papers_api

**1 身份**：`impl` mapper；目标 CL3（V1）；服务 `hf_papers`（信号层）；W1。

**2 通道与操作**（platform）：`increment`（`daily_papers?date=`）、`lookup`（`/api/papers/{arxiv_id}`）、`search`（`on_demand`）；只产信号。

**3 上游接口事实**：端点含 `/api/daily_papers`、`/api/papers`（cursor 在 `Link` 头）、`/api/papers/search` [https://huggingface.co/.well-known/openapi.md, 2026-09-30]；5 分钟固定窗：匿名每 IP 500、免费用户 1,000 [https://huggingface.co/docs/hub/rate-limits, 2026-09-30]；search 50 次/5 min（长稿，未复核）；实测头 `ratelimit: "api";r=499;t=279` [https://huggingface.co/api/daily_papers?limit=1, 2026-09-30]；ToS 版本两说（二手）。

**4 请求声明**：`hf_papers.daily_papers`、`hf_papers.paper`、`hf_papers.papers_search`（`huggingface.co`）；账户 `hf.ip` 或部署级 token（`AuthRef`）；search 设子额度；`rate_dialect: ietf_draft`。

**5 游标与增量**：`date_watermark`，日期分区，`overlap` P7D（信号按日回刷），`window_max` P1D，`late_path: none`；cursor 只进 `continuation`。

**6 映射**：以 arXiv id 为键，只取信号；不存 HF `summary`；不单独建 Work。

**7 SCD**：`id.lookup.arxiv`、`sort.recency`、关键词 `native_approx`。

**8 合规**：robots 允许；⚑RECHECK，建议复核前信号只作内部排序特征、缓存 ≤7 天、不展示原始计数（U-6）。

**9 全文**：无。

**10 测试**：`daily_papers` 页、`/api/papers` 页（含 Link 头）、单篇、429；FS-AGG-05。

**11 探针与替补**：`structure`、`count`（`q=` 值）、`tos_hash`；无替补，缺失时推荐降级。

**12 运维**：新鲜度 ≤24 h。

**13 已知坑与待决**：新增 `/api/papers`（与长稿不同）；SDK `list_papers` 实为 search。

### dblp_sparql

**1 身份**：`impl` mapper；目标 CL3（V1）；服务 `dblp`；W1，D-050 核验前停 CL1 待命（同实施计划）。

**2 通道与操作**（platform）：`lookup`（DOI 或标题到 dblp key）、`search`（固定模板，`on_demand`）；增量归 `dblp_drops_snapshot`。

**3 上游接口事实**：`https://sparql.dblp.org/sparql`（QLever），日更 KG 包可自建镜像 [https://sparql.dblp.org/download/, 2026-09-30]；CC0；robots `Crawl-delay: 10`、`Allow: /sparql` [https://sparql.dblp.org/robots.txt, 2026-09-30]；限速为二手说法，超时与上限未核；主站 robots 全禁并具名禁 Claude 类 UA [https://dblp.org/robots.txt, 2026-09-30]。

**4 请求声明**：`dblp.sparql_template`（`sparql.dblp.org`）；账户 `dblp.ip`，间隔 10 s；只许登记模板，参数只替换字面量。

**5 游标与增量**：无。

**6 映射**：dblp key、DOI（版本级）；venue 只作 `work_assertion`。

**7 SCD**：`id.lookup.{doi, dblp}`；标题检索 `emulated`（未核）。

**8 合规**：[D-050](../../../decision-log.md) 允许核验后的 SPARQL；主站零访问；上限 `on_demand`。

**9 全文**：无。

**10 测试**：每模板一份结果与空结果；FS-AGG-07。

**11 探针与替补**：`robots`、`canary_query`（已知 DOI 命中）。替补 `dblp_drops_snapshot`；建议优先评估自建镜像（零外部请求）。

**12 运维**：SLO 以补查成功率计。

**13 已知坑与待决**：自建镜像后可降为本地 join（待决）。

### core_api

**1–2 身份与通道**：mapper；目标 CL3（V3），许可前停在 CL0（同实施计划）；服务 `core`；W3；platform `lookup`、`search`（`on_demand`），`locate_fulltext` 排在 OpenAlex、Unpaywall 之后。

**3 上游事实**：匿名 100 token/日（无全文）、个人 1,000/日（25 次/min）、学术 5,000/日；复杂查询 3–5 token；结果集 ≤10,000，更大用 scroll [https://api.core.ac.uk/docs/v3, 2026-09-30]；重试头实测为 ISO 时间戳；文档页对自动化 403。

**5、8 游标与合规**：无游标（`updatedDate` 区间语法未核）；⚑LIC ⚑COMM，许可前不启用（HC-23，[03 SourceSpec](../../03-sources-and-corpus-pipeline.md#sourcespec-v2三条通道与合规证据)）；致谢按 HC-24。

**10–11 测试与探针**：未认证响应、scroll、429；FS-AGG-04、FS-AGG-05；探针只读 API 头；替补 `openalex_api`、`unpaywall_api`。

### datacite_rest

**1–2 身份与通道**：mapper；目标 CL3（V3）；服务 `datacite`、`lipics_drops`（10.4230，也可归 crossref_delegated 的 DataCite 变体，见[该族](crossref-delegated.md)）；W3；platform `lookup`、`enumerate`、`increment`。

**3 上游事实**：5 分钟滚动窗按 IP：认证 3,000、识别 1,000、匿名 500，持续批量建议 300–500；无限速头 [https://support.datacite.org/docs/rate-limit, 2026-09-30]；`page[size]` ≤1,000，cursor 跟随 `links.next` [https://support.datacite.org/docs/pagination, 2026-09-30]。

**5、8 游标与合规**：`date_watermark`，`query=updated:[a TO b]`，`overlap` PT24H；CC0（长稿）；按 ≤400 次/5 min 规划；`identity_param: mailto`。

**10–11 测试与探针**：cursor 页、429、`affiliation=true` 记录；FS-AGG-01、FS-AGG-02；`structure`、`deprecation`（GraphQL，长稿）；替补 `datacite_annual_file`。

### doaj_api

**1–2 身份与通道**：mapper；目标 CL3（V3）；服务 `doaj`；W3；platform `lookup`、`search`（OA 期刊白名单与文章）。

**3 上游事实**：API v4，禁通配、正则、模糊；全路由 2 req/s、突发排队 5 [https://doaj.org/api/v4/docs, 2026-09-30]；OAI 普通用户最长 30 天更新 [https://doaj.org/docs/oai-pmh/, 2026-09-30]；分页上限未核。

**5、8 游标与合规**：无游标（增量交 OAI 实例与 `doaj_csv`）；CC0（长稿）；`on_demand` 与 enrich。

**10–11 测试与探针**：期刊、文章、429；FS-AGG-07；`structure`（API 版本号）；替补 `doaj_csv`。

### econbiz_api

**1–2 身份与通道**：mapper；目标 CL3（V3）；服务 `econbiz`；W3；platform `lookup`、`search`（`on_demand`），不做 `enumerate`。

**3 上游事实**：无配额但可变；"not supposed to be used to copy content … at large scale" [https://api.econbiz.de/doc, 2026-09-30]；字段表无 `econbiz_created`，有 `econbiz_modified` 等 [https://api.econbiz.de/v1/fields, 2026-09-30]。

**5、8 游标与合规**：无游标，长稿 `econbiz_created` 增量作废；`on_demand`；批量须先联系 ZBW。

**10–11 测试与探针**：search、record、`/fields`；FS-AGG-01；`structure`；替补 `repec_redif`、`crossref_delegated`。

### icite_api

**1–2 身份与通道**：mapper；目标 CL3（V5）；服务 `icite`；W3；platform enrich `lookup`（按 PMID 取 RCR 与被引数）。

**3 上游事实**：`/api/pubs?pmids=` 返回 200、无限速头（实测 2026-09-30）；文档页 401；限速、许可、批量上限未核。

**5、8 游标与合规**：无游标；⚑RECHECK，派生指标先不共享（待确认）；暂按 `ncbi.key` 共用取严（U-7）。

**10–11 测试与探针**：批响应（含未知 PMID）；FS-AGG-03；`structure`；替补 `opencitations_api`。

### nasa_ads_api

**1–2 身份与通道**：`kind: recipe_provider`、`impl: declarative`（`QueryRecipe`，U-1）；契约 v1 无用户侧元数据查询协议，停在 CL0（待拍板 P-13，原目标 CL3）；服务 `nasa_ads_scix`；W3u（占位）；user 侧用本人 token 做 `lookup`、`search`，结果归私域。

**3 上游事实**：Bearer 用户 token；每端点日配额（search 5,000，UTC 午夜重置），头 `X-RateLimit-*` [https://github.com/adsabs/adsabs-dev-api, 2026-09-30]；`rows` ≤2,000、big query 每日 100 次（同一仓库 Search_API 笔记本）；SciX 最迟 2027-02 完成切换（二手），基址是否迁移未核。

**5、8 游标与合规**：无游标；凭证只在扩展或 pc-agent（D-054）；⚑DRIFT；平台不代查。

**10–11 测试与探针**：合成 fixture（响应与头、401、429）；FS-AGG-05；平台只做 `deprecation`（基址重定向）；替补 `arxiv_oai`、`inspire_rest`。

### opencitations_api

**1–2 身份与通道**：mapper；目标 CL3（V3）；服务 `opencitations`；W3；platform enrich `lookup`（引用、被引与计数）。

**3 上游事实**：Index REST v2，每 IP 180 次/min，可选 `authorization` token [https://api.opencitations.net/index/v2, 2026-09-30]；dump 无增量包 [https://download.opencitations.net/, 2026-09-30]；CC0（长稿）。

**5、8 游标与合规**：无游标；按 ≤1 次/s 规划；token 若用为部署 `AuthRef`。

**10–11 测试与探针**：`citations`、`citation-count`；FS-AGG-03；`canary_query`（已知 DOI 被引 >0）；替补 `opencitations_dump`、`openalex_api`（两者被引数不一致，交叉校验）。

### orcid_api

**1–2 身份与通道**：`kind: recipe_provider`、`impl: declarative`（OAuth，U-1）；契约 v1 无用户侧元数据查询协议，停在 CL0（待拍板 P-13，原目标 CL3）；服务 `orcid`；W3u（占位）；**exec_side 修正为 user**（清单原为 platform）；只读用户本人记录，平台只用 `orcid_public_data_file`。

**3 上游事实**：匿名 12 req/s、每 IP 2.5 万次/日 [https://info.orcid.org/ufaqs/what-are-the-api-limits/, 2026-09-30]；凭证发给个人、禁持续轮询、不得用于产生收入的产品 [https://info.orcid.org/public-client-terms-of-service/, 2026-09-30]；`pub.orcid.org` robots 全禁（实测）。

**5、8 游标与合规**：无游标；⚑ROBOTS ⚑COMM（HC-23）；平台侧 `deny`；OAuth 仍须注册 client，而 Public API 凭证发给个人：用户自带个人 client 还是部署方走 Member API 未定（U-5）。

**10–11 测试与探针**：合成 works 列表、503、配额封禁；`robots`、`tos_hash`；替补 `orcid_public_data_file`。

### pubtator3_api

**1–2 身份与通道**：mapper；目标 CL3（V5）；服务 `pubtator3`；W3；platform enrich `lookup`（按 PMID 取实体注释）。

**3 上游事实**：官方页 JS 渲染未读到 [https://www.ncbi.nlm.nih.gov/research/pubtator3/api, 2026-09-30]；长稿记 `publications/export/biocjson?pmids=`；≤3 rps 为二手；许可与 robots 未核。

**5、8 游标与合规**：无游标；⚑RECHECK，确认前低频 `on_demand`（≤1 rps），派生注释不共享。

**10–11 测试与探针**：合成 biocjson 批；FS-AGG-03；`structure`；替补 `europe_pmc_rest`（`filter.entity.*`）。

### scoap3_api

**1–2 身份与通道**：mapper；目标 CL3（V5）；服务 `scoap3_repo`；W3；platform `enumerate`、`lookup`、`increment`、`locate_fulltext`（CC BY 文件在 CERN S3）。

**3 上游事实**：`/api/records/` 匿名 200，`count` 87,758；`record_creation_date__gte` 被静默忽略（实测 2026-09-30）；伙伴页称须注册 token [https://repo.scoap3.org/partners, 2026-09-30]；robots 返回前端页，等同无 robots。

**5、8 游标与合规**：`date_watermark`，`created`，本地截断到水位（默认排序未核）；文章 CC BY、元数据 CC0；建议先注册伙伴 token 再 `background`。

**10–11 测试与探针**：列表、单记录、401 负例；FS-AGG-01（当前为反例）；`structure`（出现 401 即切 token）；替补 `arxiv_oai`、`inspire_rest`。`dois` 与 `arxiv_eprints` 互相混入，mapper 须清洗。

## 7. 本族风险、坑与待决

1. **静默失效**：过滤无效时返回 0 或全量且不报错（Europe PMC、SCOAP3），靠 FS-AGG-01、FS-AGG-10 兜住。
2. **文档不可机读**：Europe PMC 403、NCBI reCAPTCHA、CORE 403、iCite 401，PubTator3 与 ADS 为 JS 渲染；探针以 API 实测为主，文档复读走人工季度流程。
3. **计费与门控**：OpenAlex 付费过滤 429、402 语义未核、`meta.count` 下降原因不明。
4. **书面确认阻断**：NCBI、FIZ、EBI（交互用量）；V0 发函名单须含三家。
5. **与长稿不同处**（供实施计划汇总）：Europe PMC `INDEX_DATE`；PMC OA Web Service 与 FTP；zbMATH 条款闸门与 `deletedRecord=no`；EconBiz 无 `econbiz_created`；INSPIRE OAI；HF `/api/papers`；OpenAlex `per_page`、付费过滤、`deleted_ids`；SCOAP3 认证口径。

## 怎么验收

- 总表列全本族 28 个新写连接器，4 个桥接指向 [v1-bridge](v1-bridge.md)；卡片标题只含 connector_id，且只在本族出现。
- 7 张 P0 卡 13 节齐全，§4 写明 `hosts_touched` 与 `budget` 账户，§5 写明 `late_path`、`window_max` 或声明不适用；10 张 P1 紧凑卡含框架要求的七项。
- 清单 lint：§3 字段按规则必填；共用账户的 `planned_daily` 之和 ≤ 上限的 80%。
- 离线 CI：FS-AGG-01…FS-AGG-10 与通用契约测试全绿（CL1）。
- 预算演练：`openalex.usd` 到 80%、100% 时行为符合 04；INSPIRE 429 触发全账户退避。
- 与 03、08 一致：平台侧无个人凭证；用户侧四者 `exec_side: user`，契约 v1 停在 CL0（P-13）；被阻断通道上限为 `deny`。

## 未决事项

- **U-1** 用户侧元数据查询配方 `QueryRecipe`（四个用户侧连接器）；契约 v1 只有 `FulltextRecipe`，不新增协议；列为契约待拍板 P-13，四者在 v1 停在 CL0。
- **U-2** `identity_param`（网关注入部署联系邮箱）、`budget.unit` 加 `token`、`config` 子码 `plan_required` 与 `terms_gate` 是否进契约（契约 §7 现只列 `config/undeclared_host`）。
- **U-3** 桥接移植后沿用 connector_id 升 MAJOR，还是转 CLX 后另取名。
- **U-4** 桥接卡片暂归 [v1-bridge](v1-bridge.md)；若改放本族，§5.1 扩成卡片。
- **U-5** `orcid_api` 的 `exec_side` 由 platform 改为 user；OAuth client 归属（用户个人 Public client 或部署方 Member API）。
- **U-6** HF 信号在 ToS 复核前的展示与缓存口径。
- **U-7** `pubmed_eutils`、`pmc_bioc`、`pubtator3_api`、`icite_api` 是否共用一个身份与账户（iCite 不属 NCBI）。
- **U-8** zbMATH `robots.txt` 307 的 RFC 9309 口径；FIZ 书面确认。
- **U-9** `hal_api` 补 ⚑COMM（OAI 条款不得商用）；Europe PMC 修订增量字段与 EBI 用量约定。
- **U-10** `zbmath_open_api` 波次与目标以实施计划为准（W1，V1 出口 CL3）；但 REST 闸门机制与 FIZ 书面确认之前录不到 JSON fixture、G1 无法签字，实际停在 CL0；已请实施计划把它列入闸门类。
- **U-11** 本文约 51KB（卡片标签统一后分段增加），超出族文档 45KB 目标；本轮只并重复句、不删卡片，实现期把 §2 类型定义与 §2.5 方言表拆为附录。

更细的材料：`git show v2-drafts:docs/plan/v2/03-sources-and-corpus-pipeline.md`（§4.4 SCD 示例、§5.3–5.4 族与专有接口、§7.9 新写汇总、§14.1 v1 去向）；`git show v2-drafts:docs/catalog/source-directory.md`（§3 总表）；[支持名录](../../../../catalog/source-directory.md)；[连接器矩阵](../../../../catalog/connector-matrix.md)。
