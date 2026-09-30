---
title: 连接器接口契约 v1（ConnectorContract v1）
status: draft
owner: opus5.5-primary
updated: 2026-09-30
---

# 连接器接口契约 v1（ConnectorContract v1）

> 本文回答：一个 Confluo 连接器必须声明什么、能做什么、不能做什么，执行器与出站网关怎样驱动它，游标、错误、映射、版本怎样统一。结论：连接器是"注入上下文的纯函数 + 执行器驱动的生成器"，只做三件事——声明请求（RequestSpec）、解析响应（Page）、规范化映射（NormRecord）；不发 HTTP、不持凭证、不写审计、不判策略。本文把 `git show v2-drafts:docs/plan/v2/03-sources-and-corpus-pipeline.md` §5.2"非接口冻结"的通用协议补全并冻结为 v1（ADR 草案 D-074，见[决策日志](../../decision-log.md)）。与 main 上 [02](../02-architecture.md)、[03](../03-sources-and-corpus-pipeline.md)、[05](../05-data-platform.md)、[08](../08-compliance-security-privacy.md)、[09](../09-roadmap-and-milestones.md) 只细化不矛盾；与长稿或 05 DDL 相抵之处列在"待拍板"。总览见 [README](README.md)。

## 要点

1. 三层声明：`SourceSpec`（来源与合规证据）、`ConnectorManifest`（技术事实与能力，新增）、`ConnectorInstance`（零代码实例）；证据只存一处；Manifest 不含运行态。
2. 两种协议：`PlatformConnector`（`plan/parse/normalize/describe/probes`）与 `RecipeProvider`（只产 `FulltextRecipe` 数据）；平台 worker 只加载 platform 清单。
3. 执行模型：`plan()` 是生成器，网关执行 RequestSpec，执行器 `parse` 后先落库再回送 `Step`；游标只在安全提交点同事务原子推进。
4. 策略双判定：任务准入一次，网关逐请求复核 `decision_id + engine_version + inputs_epoch`；漂移在页边界停。
5. 违规写法在类型、CI、网关三层都不成立。
6. 游标七种 kind；`error_class` 15 个各有唯一判定者、处置矩阵与责任方；`policy_denied` 与 `disabled` 分开记账。
7. 映射永远是带 `mapper_version` 的代码，只输出带 `basis` 的声明；权利由共享 `classify_rights()` 计算，未知即不共享。
8. 三个版本号；`scd_version` 归 `contract_version`；变更走 `shadow → canary → full`。
9. 代码阶梯 `instance < declarative < mapper < custom_plan < v1_bridge`，默认最低级；声明式只管请求形状。
10. `v1_bridge` 是有到期日的过渡：仍全部经网关、受策略判定，V2 出口前移植或退役。

## 1. 定位与不变量

继承 [03 连接器九族与执行位置](../03-sources-and-corpus-pipeline.md#连接器九族与执行位置)、[02 出站网关](../02-architecture.md#出站网关egress-gateway)、[08 执行位置与凭证](../08-compliance-security-privacy.md#执行位置与凭证) 与 D-046、D-049、D-053、D-054、D-055 的全部硬边界，不放宽任何一条。连接器只做三件事：声明请求、解析响应、规范化映射；另有两个纯声明：`describe()` 给 SCD 静态部分，`probes()` 给探针清单。

**禁止事项**（F1–F6、F9、F10 运行时命中即 `config`，CI 与网关双重拦截；F7、F8 由契约测试拦截）：

| # | 禁止 | 拦截层 |
|---|---|---|
| F1 | 自己发 HTTP、开 socket，导入 HTTP、浏览器自动化、TLS 指纹、验证码类库 | CI 依赖禁表 + 无网沙箱；worker 无公网路由 |
| F2 | RequestSpec 带 UA、Cookie、Authorization、Referer、已知 key 头或 `personal_params` 参数 | `AllowedHeader` 白名单 + lint |
| F3 | 持有或引用用户凭证；平台包定义用户凭证类型 | `AuthRef` 只有 `deployment/*` + import 规则 |
| F4 | 自标 robots 豁免、自查或改写策略决定、设置 `traffic_class` | RequestSpec 无此类字段；网关不采信自报 |
| F5 | 访问 `allowed_hosts` 之外的主机或红线 URL（盗版源、`scholar.google.*`、arXiv `/e-print/`、`/src/`） | lint 红线扫描 + 网关白名单与红线禁表 |
| F6 | 写审计、自带指标、自记日志 | 网关写 FetchLog；runner 发指标 |
| F7 | 读系统时钟、随机、环境变量、文件、全局可变状态 | 零 I/O 契约测试 |
| F8 | 跳过出错页、越过未落库数据推进游标、按"本页最大值"推进 | 安全提交点规则 + 游标属性测试 |
| F9 | 换 UA 或指纹重试被拒请求；求解挑战 | UA 只由网关写（§12）；挑战即冷却 |
| F10 | 平台向端侧下发代码；配方内自由 HTTP 步骤 | 配方 schema 封闭 + PolicyBundle 签名 |

## 2. 三层声明与 ConnectorManifest

| 层 | 文件 | 管什么 | 不管什么 |
|---|---|---|---|
| `SourceSpec` | `registry/sources/<source_id>.yaml`（03 已定义） | 三通道、合规证据、`v2_status`、`support_tier`、替补链 | 端点技术细节 |
| `ConnectorManifest` | `registry/connectors/<connector_id>.yaml`（新增） | 族、契约版本、Operation × 通道、端点与请求类、限速与预算、游标类型、映射版本、fixture 与探针、一致性声明、owner | 合规证据（按 `source_id` 引用）；任何运行态（rollout、`cl_effective`、health、急停只在 ops 层） |
| `ConnectorInstance` | `registry/instances/<family>/<instance>.yaml`（长稿已定义） | base URL、OAI 参数、族引擎已登记的 quirk 旗标 | Python 钩子、未登记怪癖 |

**ConnectorManifest 字段**（均必填，除非注明）：

| 字段 | 取值与规则 |
|---|---|
| `connector_id` | snake_case，全局唯一，永不复用 |
| `kind` | `platform_connector` / `recipe_provider`；须与 `exec_side` 一致（lint） |
| `family`、`exec_side` | 九族之一；`platform` / `user` |
| `impl` | `instance` / `declarative` / `mapper` / `custom_plan` / `v1_bridge`（§15） |
| `contract_version`、`connector_version` | 整数（本版 1）；semver |
| `serves[]` | `source_id` 列表；SourceSpec 各通道的 `connector` 反向指向本 id |
| `operations[]` | `{operation, channel}`；`search` 只在 SCD 声明 native/emulated 时出现 |
| `endpoints[]` | 见下表 |
| `mappers[]`（platform） | `{mapper_id, mapper_version, identifiers_emitted[]}` |
| `allowed_hosts[]` | = 各 `endpoints[].hosts_touched` 并集；lint 校验相等且 ⊆ SourceSpec 各通道 hosts；网关白名单由此生成 |
| `upstream_facts[]` | `{fact, url, verified_at, grade ∈ primary|secondary, by, probe}`；只记技术事实，每条映射到一个探针 |
| `probes[]`、`fixtures[]` | `ProbeSpec` 列表；fixture id，四类各至少一个 |
| `fixture_policy` | `{recorded_via ∈ staging_gateway|handwritten_synthetic, rerecord_after}` |
| `conformance` | `{declared, target, rules{<rule_id>: done|exempt{reason, approved_by}|todo}, compliance_signoff[2]}`；`declared` 只经 PR 上调 |
| `ops` | `{owner, backup_owner, points, review_every, slo}`；P0 两人 |
| `lifecycle` | `{state ∈ active|deprecated|retired, upstream_sunset, sunset_by}` |
| `v1`（仅 `v1_bridge`） | `{adapter, destiny, mode, port_target, sunset_by, parts[]}`（§17；取值以 [v1-bridge 族](families/v1-bridge.md) §1 为准） |

**`endpoints[]` 每项**：

| 字段 | 说明 |
|---|---|
| `endpoint_id`、`request_class` | `<source_id>.<name>`，对应一份 SCD；上游池类（如 Crossref `single`/`array`），与平台内 `traffic_class` 无关 |
| `method`、`path_template`、`hosts_touched[]` | 模板只用封闭占位词表（§15）；`hosts_touched` 含重定向落点、CDN、bulk 主机，每个都须有 robots 条目 |
| `auth` | `AuthRef` 或 `null` |
| `paginator` | `{kind ∈ cursor|token|offset|page, …}`（§15） |
| `expect` | `Expectation`（§3） |
| `status_overrides[]` | "状态码 → error_class"覆盖表 `{status, error_class, reason, fact_ref, fixture}`，每行配一条 `upstream_facts` 与一个 fixture（如 openreview 匿名 403 `ChallengeRequiredError` → `challenge`、openalex 付费过滤 429 `Plan upgrade required` → 按事实声明而非 `rate_limited`、s2 无 key 404 → 非 `gone`；F1/F4 实测，2026-09-30）；未覆盖的按 §7 默认 |
| `source_key_rule`、`volatile_fields[]` | 同源各端点同键；易变字段不入 `payload_sha256` |
| `personal_params[]` | 禁止出现的参数名（key、token、email 等） |
| `cursor` | `{kind, schema, ordered, ordered_by?, ordered_fixture?, bounds, overlap, granularity, lag_bound, late_path, window_max}`（§6） |
| `budget` | `{account, unit ∈ usd|request|key_rps|ip_quota|bytes, ceiling, evidence, planned_daily}`；多连接器可共享账户 |

```yaml
# 设计伪代码 —— registry/connectors/europe_pmc_rest.yaml（节选示意，数值以卡片为准；无任何运行态字段）
connector_id: europe_pmc_rest
kind: platform_connector
family: aggregator_api
exec_side: platform
impl: mapper
contract_version: 1
connector_version: 1.0.0
serves: [europe_pmc]
operations: [{operation: increment, channel: latest}, {operation: lookup, channel: metadata}]
endpoints:
  - endpoint_id: europe_pmc.search
    request_class: rest
    method: GET
    path_template: "/europepmc/webservices/rest/search"
    hosts_touched: [www.ebi.ac.uk]
    auth: null
    paginator: {kind: token, param: cursorMark, path: "$.nextCursorMark", page_size: 1000}
    expect: {content_types: [application/json], min_bytes: 64, root: "$.resultList", empty: legit, legit_status: [200]}
    source_key_rule: "$.id"
    volatile_fields: ["$.citedByCount"]
    personal_params: [email, api_key]
    cursor: {kind: date_watermark, schema: 1, ordered: false, bounds: "[from, until]", overlap: P2D,
             granularity: day, lag_bound: "未核", late_path: snapshot_reconcile, window_max: P1D}
    budget: {account: epmc.requests, unit: request, ceiling: {min_interval_s: 10}, evidence: ev_epmc_rate_2026-09-30, planned_daily: 400}
mappers: [{mapper_id: epmc_json, mapper_version: 1, identifiers_emitted: [doi, pmid, pmcid, ppr]}]
allowed_hosts: [www.ebi.ac.uk]
upstream_facts: [{fact: "INDEX_DATE 增量静默返回 0，只用 FIRST_IDATE 日窗", url: "https://www.ebi.ac.uk/europepmc/webservices/rest/search", verified_at: 2026-09-30, grade: primary, by: "@a", probe: epmc.silent_zero}]
probes: [epmc.robots, epmc.silent_zero, epmc.structure]
fixtures: [epmc.normal_page, epmc.empty_legit, epmc.rate_limited, epmc.last_page]
conformance: {declared: CL0, target: CL3, rules: {}, compliance_signoff: []}
ops: {owner: "@a", backup_owner: "@b", points: 1, review_every: P90D, slo: p0_latest}
lifecycle: {state: active, upstream_sunset: null, sunset_by: null}
```

## 3. 核心类型

```python
# 设计伪代码 —— frozen dataclass；字段顺序即规范
AllowedHeader = Literal["Accept", "Accept-Encoding", "If-None-Match", "If-Modified-Since", "Content-Type"]
class AuthRef(str): ...                  # 仅 "deployment/<credential_id>"；网关注入，连接器只引用

@dataclass(frozen=True)
class Expectation:
    content_types: tuple[str, ...]; min_bytes: int = 1; root: str | None = None
    empty: Literal["error", "legit"] = "error"                # 空结果是端点事实还是错误
    fake_success: tuple[tuple[str, ErrorClass], ...] = ()     # ("Rate exceeded.", "rate_limited")
    legit_status: frozenset[int] = frozenset({200})           # LOOKUP 端点可为 {200, 404}；带条件头的端点可含 304
                                                              # 304 是无体合法响应：网关不做 content_types、min_bytes、empty、fake_success 检查
    magic: bytes | None = None                                # 用户侧配方复用（%PDF）

@dataclass(frozen=True)
class RequestSpec:
    endpoint_id: str; request_class: str; method: Literal["GET", "HEAD", "POST"]
    url: str; params: Mapping[str, str]; headers: Mapping[AllowedHeader, str]
    auth: AuthRef | None; expect: Expectation; idempotency_key: str   # key 由 SDK 计算
    stream: bool = False                 # 大文件：网关流式落冷存储、自写 Range 续传，Response.body 为空、只回 blob
    # 刻意没有：user_agent、cookies、robots_*、traffic_class、decision

@dataclass(frozen=True)
class Response:                          # 网关产物；已过挑战、空体、伪成功检测
    status: int; headers: Mapping[str, str]; body: bytes; final_url: str; final_host: str
    fetched_at: datetime; cache_hit: bool; attempt: int; terminal: bool
    error_class: ErrorClass | None; reason: str | None   # reason 放 §7 子码（如 stale_decision、cooldown）
    blob: BlobRef | None = None          # 仅 stream=True：网关已校验字节数与 sha256，不符即 integrity 终止

@dataclass(frozen=True)
class BlobRef: uri: str; sha256: bytes; bytes: int; expected_sha256: bytes | None   # 冷存储对象，连接器不可直接读
@dataclass(frozen=True)
class SnapshotChunk: blob: BlobRef; file_id: str; offset: int; n: int; data: bytes   # runner 按记录边界确定性切块后喂给 parse_chunk()

@dataclass(frozen=True)
class PageSignals:
    n_records: int; total_hint: int | None; legit_empty: bool; not_found: tuple[str, ...]
    continuation: str | None; continuation_expires_at: datetime | None   # 令牌只在运行内使用
    rate_headers: Mapping[str, str]; deprecation: str | None; response_date: datetime | None
    n_quarantined: int = 0               # 本页或本块内被逐条跳过的坏记录数（bulk 隔离率对账用）

@dataclass(frozen=True)
class RawRecord:
    source_id: str; source_key: str; kind: Literal["upsert", "tombstone", "presence"]   # presence 只用于在场对账：sink 写在场表、累计缺席计数，连续缺席达阈值才产出 tombstone
    channel: Literal["metadata", "latest"]; provenance: Literal["harvest", "snapshot", "federated"]
    endpoint_id: str; payload: bytes | Mapping; payload_sha256: bytes; fetched_at: datetime
    order_value: str | None              # 游标字段取值，供有序性断言

@dataclass(frozen=True)
class Page: records: tuple[RawRecord, ...]; next_cursor: Cursor | None; signals: PageSignals
@dataclass(frozen=True)
class Step: resp: Response; page: Page | None; error_class: ErrorClass | None = None   # page 为 None = 非合法结果，只能在安全点结束；error_class 为 parse 判定的类（如 cursor_expired）
@dataclass(frozen=True)
class CursorEnvelope: scope_key: str; cursor: Cursor; schema: int; rev: int   # kind 见 §6

OperationInput = LookupInput | SearchInput | EnumerateInput | IncrementInput | SnapshotInput | ProbeInput   # 各类型定义紧随其后
@dataclass(frozen=True)
class LookupInput: identifiers: tuple[Identifier, ...]          # 04 联邦 LOOKUP 的标识符批
@dataclass(frozen=True)
class SearchInput: query: PushdownQuery; limit: int               # 只含 SCD 声明可下推的谓词（aggregator_api §2.2）
@dataclass(frozen=True)
class EnumerateInput: window: tuple[datetime, datetime]; mode: Literal["harvest", "reconcile"] = "harvest"   # [from, until)；reconcile = 在场对账
@dataclass(frozen=True)
class IncrementInput: mode: str = "normal"   # 族内维护模式（如 crossref 的 weekly_backfill、corrections），取值由族文档枚举并经清单 lint
@dataclass(frozen=True)
class SnapshotInput: release_id: str; union_filter: UnionFilter   # 兴趣并集过滤（05）
@dataclass(frozen=True)
class ProbeInput: probe: ProbeSpec                                 # ProbeSpec 见后文

@dataclass(frozen=True)
class ConnectorTask:                     # 无 user_id；plan_key 只作缓存与审计键
    task_id: str; operation: Operation; source_id: str; channel: str; scope_key: str
    cursor: CursorEnvelope | None
    payload: OperationInput | None      # 按 operation 取对应类型：lookup→LookupInput、search→SearchInput、enumerate→EnumerateInput、
                                        # snapshot_import→SnapshotInput、probe→ProbeInput；increment 为 IncrementInput 或 None（None 即 normal）；
                                        # locate_fulltext 不经 plan()，由 locate_fulltext(VersionView) 直接取输入。plan() 只从这里取输入、不做隐藏 I/O
    decision_ref: DecisionRef            # {decision_id, engine_version, inputs_epoch}
    budget: TaskBudget                   # {max_requests, max_pages, deadline}
    lane: Literal["interactive", "harvest", "enrich"]; plan_key: str | None

@dataclass(frozen=True)
class TaskOutcome:
    status: Literal["completed", "partial", "stopped", "denied", "failed"]   # partial = 按预算在安全点停下，不算错
    error_class: ErrorClass | None = None; reason: str | None = None; committed: CursorEnvelope | None = None
    next_cursor: Cursor | None = None    # 生成器可在终局带回游标（无分页的 feed 等），runner 原子落库后再返回
    pages: int = 0; records: int = 0; requests: int = 0; restarts: int = 0; cost_usd: Decimal = Decimal(0)   # 计数由 runner 账本覆盖（§5）

@dataclass(frozen=True)
class ExecCtx:
    task_id: str; decision_id: str; traffic_class: Literal["background_batch", "on_demand"]
    connector_ref: str; plan_key: str | None                 # "<connector_id>@<connector_version>"
@dataclass(frozen=True)
class EgressEnvelope:                    # runner 生成，连接器不可见；指标、审计、急停、预算都按信封计
    ctx: ExecCtx; source_id: str; channel: str; operation: Operation
    rollout: Literal["shadow", "canary", "full"]; request: RequestSpec
    deadline: datetime                   # 任务剩余截止时间，网关对流式下载按此中止并保留已下字节供续传

@dataclass(frozen=True)
class AccessDecision:                    # 策略引擎产物，只由网关与 runner 读
    decision_id: str; source_id: str; channel: str; operation: Operation
    mode: Mode; allowed: bool; needs_confirmation: bool
    caps: ModeCaps                       # 该 mode 下的操作与通道上限，runner 注入 PlanCtx.mode_caps
    robots_basis: Literal["none", "api_conflict", "written_confirmation"]
    exception_refs: tuple[str, ...]; hosts_allowed: frozenset[str]; min_interval_s: float
    engine_version: int; inputs_epoch: int; valid_until: datetime   # ≤ 24h

class PlanCtx:  now: datetime; instance: ConnectorInstance | None; scd: Mapping[str, SCD]; mode_caps: ModeCaps
class ParseCtx: now: datetime; endpoint: EndpointDecl; instance: ConnectorInstance | None
class MapCtx:   now: datetime; granularity_table: Mapping; license_alias: Mapping; doi_family: Mapping
                mapper_config: Mapping           # 清单中该 mapper 的静态配置（如 v1 桥接的 stage_default、meta_keep），不含凭证
class LocateCtx: now: datetime; instance: ConnectorInstance | None; mode_caps: ModeCaps   # locate_fulltext 专用，同样纯函数
```

`SCD`、`ProbeSpec`、`FulltextOption`、`FulltextRecipe`、`EffectiveStatus` 见 §9–§13；`Identifier`、`PushdownQuery` 见 [aggregator_api](families/aggregator-api.md) §2.2，`UnionFilter` 与 `TaskBudget`、`DecisionRef` 的存储见 05，`ModeCaps` 与 `Mode` 见 08 的策略引擎；`NormRecord` 字段以 05 `corpus.norm_record` 与长稿 §10.6 为准，本文只约束映射规则（§8）。

## 4. Operation 与策略判定点

| Operation | 语义 | 输入 → 输出 | 判定时点 | 默认 lane → traffic_class |
|---|---|---|---|---|
| `enumerate` | 回填某 venue、前缀或集合在某窗口内的全部记录 | scope_key、window → Page 流、`window_set` 进度 | 任务准入 | harvest → background_batch |
| `increment` | 按游标取增量（WatchKey 驱动，04 编译） | CursorEnvelope → Page 流、推进后的游标 | 任务准入 | harvest → background_batch |
| `lookup` | 按标识符取记录（04 联邦 LOOKUP） | 标识符 → Page（`provenance=federated`） | 联邦计划时取 (source, channel, op) 缓存决定 | interactive → on_demand；enrich 补查 → background_batch |
| `search` | 远端检索，仅 SCD 声明 native/emulated 的端点 | 谓词 → Page（federated） | 同 lookup | interactive → on_demand |
| `snapshot_import` | 官方快照或年度文件导入 | release、union_filter → RawRecord 流（snapshot）、`snapshot_release` 游标 | 任务准入；bulk 流按续传分段复核 | harvest → background_batch |
| `locate_fulltext` | 给一个 Version 产出全文选项 | VersionView → `FulltextOption[]` | 平台侧 enrich 准入；用户侧签发 RetrievalIntent 时，verdict 随候选项签名下发，端侧只能再收紧 | enrich → background_batch |
| `probe` | 漂移与结构探针 | ProbeSpec → 探针结果（只写 ops） | 探针调度时 | harvest → background_batch |

**双判定**：① 任务准入：策略引擎 `decide()` 一次，落 05 `ops.policy_snapshot`，产出 `AccessDecision`；`allowed=false` 即 `denied`，零请求。② 网关逐请求复核：`decision_id` 存在、`engine_version` 等于当前、`inputs_epoch` 等于该 (source, channel) 当前值、`now ≤ valid_until`；再自做主机白名单与 SSRF、红线、`exec_side=user` 拒绝、robots 先行、kill switch、冷却与熔断、缓存、令牌桶（顺序按 02）。不符即 `policy_denied/stale_decision` 等子码，runner 在页边界停、游标不越过已提交页、重新准入一次。

- `inputs_epoch` 是每个 (source, channel) 的单调计数：注册表 PR、PolicyOverride、漂移告警、冷却、商用开关、kill switch、CL 变化都递增；不用全局 `policy_version`（任一 PR 会使全部任务失效）。
- `lane` 由调度方给出（对应 02 三道舱壁），`traffic_class` 由 runner 按 `lane` 盖章，连接器不可设置；`request_class` 保留上游池义。
- CL 作结构性上限 `cap_conformance`：CL0/CL1 在生产为 deny（只许回放与 dry-run），CLX deny，CL3 不设限，CL2 见待拍板 P-4。
- **robots 语义**（细化 02"取不到视同全禁"）：按 RFC 9309 §2.3.1，robots.txt 4xx（unavailable）视为无限制；5xx、网络错误、robots.txt 本身被挑战（unreachable）视为全禁；不采用 RFC 的 30 天放宽，只重试 robots 抓取本身；缓存 ≤24 小时，重定向每跳重查。

## 5. 执行模型

```python
# 设计伪代码 —— 两种协议
class PlatformConnector(Protocol):       # kind: platform_connector
    manifest: ConnectorManifest
    def describe(self, spec: SourceSpec, instance: ConnectorInstance | None) -> list[SCD]: ...
    def plan(self, task: ConnectorTask, ctx: PlanCtx) -> Generator[RequestSpec, Step, TaskOutcome]: ...
    def parse(self, resp: Response, ctx: ParseCtx) -> Page: ...             # 纯函数；失败抛 ParseError(error_class=parse|cursor_expired …)
    def normalize(self, raw: RawRecord, ctx: MapCtx) -> NormRecord: ...     # 纯函数；带 mapper_version
    def locate_fulltext(self, v: VersionView, ctx: LocateCtx) -> list[FulltextOption]: ...
    def probes(self, spec: SourceSpec, instance: ConnectorInstance | None) -> list[ProbeSpec]: ...
    def migrate_cursor(self, old: CursorEnvelope) -> CursorEnvelope: ...   # 游标 MAJOR 变更时必须提供

class RecipeProvider(Protocol):          # kind: recipe_provider；exec_side 恒为 user；没有 plan()
    manifest: ConnectorManifest
    def recipes(self, spec: SourceSpec, instance: ConnectorInstance | None) -> list[FulltextRecipe]: ...
    def locate_fulltext(self, v: VersionView, ctx: LocateCtx) -> list[FulltextOption]: ...   # 只产 tdm_api / user_fetch

# 设计伪代码 —— 平台侧 runner；HTTP 完全交给网关；每页数据与游标同事务落库
def run(task, c: PlatformConnector, gw, policy, sink, clock) -> TaskOutcome:
    readmitted = False
    while True:                                                      # 外层只为 stale_decision 重新准入一次
        decision = policy.decide(task)                               # 判定 ①
        if not decision.allowed:                                     # needs_confirmation 单独成类，进 O4 队列（§7）
            return TaskOutcome(status="denied", error_class="needs_confirmation" if decision.needs_confirmation else "policy_denied", ...)
        ctx = PlanCtx(now=clock.frozen(), instance=..., scd=..., mode_caps=decision.caps)
        exec_ctx = ExecCtx(task.task_id, decision.decision_id, traffic_class_of(task.lane), ref(c), task.plan_key)
        drive = run_bridge if c.manifest.impl == "v1_bridge" else _drive   # 桥接运行器见 v1-bridge 族 §2.2，出口语义相同
        outcome = drive(task, c, gw, sink, clock, ctx, exec_ctx, rollout_of(c, task))   # rollout 取连接器灰度状态（O5）
        if outcome.reason == "stale_decision" and not readmitted:    # inputs_epoch 或 engine_version 变了：从已提交游标重新准入
            readmitted, task = True, replace(task, cursor=sink.last(task)); continue
        return outcome

def _drive(task, c, gw, sink, clock, ctx, exec_ctx, rollout) -> TaskOutcome:
    gen, step, acct = c.plan(task, ctx), None, RunnerAccount(task.budget, clock)   # 请求、页、记录计数与截止时间归 runner，时钟注入
    def stop(outcome):                                               # 所有非正常结束都经这里：关生成器、按 runner 账本汇总
        gen.close(); return acct.finalize(replace(outcome, committed=sink.last(task)), gw.ledger(exec_ctx))
    while True:
        try: req = gen.send(step) if step else next(gen)
        except StopIteration as done:                                # 状态取生成器，计数与 cost_usd 取 runner 与网关账本
            out = done.value
            if out.next_cursor is not None: sink.commit_cursor(task, out.next_cursor)   # 终局游标（如 feed 的 guid_set、ETag）按 rev 比较交换落库
            return acct.finalize(replace(out, committed=sink.last(task)), gw.ledger(exec_ctx))
        if acct.exhausted():                              # max_requests / max_pages / deadline：在页边界停
            return stop(TaskOutcome(status="partial", error_class="budget_exhausted", ...))
        resp = gw.execute(EgressEnvelope(exec_ctx, task.source_id, task.channel, task.operation, rollout, req, deadline=task.budget.deadline))   # 判定 ②
        acct.count_request(resp)                                     # 每次尝试都计数，含 gone、失败与 304
        if resp.error_class == "gone" and task.operation in ("lookup", "search", "probe"):
            step = Step(resp, None, "gone"); continue                # 逐项标记未命中，plan() 继续其余请求（§7）
        if resp.terminal:                                            # challenge / policy_denied / budget_exhausted / disabled …
            return stop(TaskOutcome(status=outcome_of(resp.error_class),   # 按 §7 矩阵：budget_exhausted 为 partial，其余 stopped
                                    error_class=resp.error_class, reason=resp.reason, ...))
        pctx = ParseCtx(ctx.now, endpoint_of(req), ctx.instance)
        if req.stream:                                               # 流式：按记录边界切块，逐块 parse_chunk、按块提交、按块查预算
            for chunk in split_chunks(resp.blob, resumed_from=sink.last(task)):   # 从 part_offsets 记录的偏移续切
                if acct.exhausted():
                    return stop(TaskOutcome(status="partial", error_class="budget_exhausted", ...))
                if (v := gw.revalidate(exec_ctx)) is not None:       # 块边界复核判定 ②，返回同 Response 的 (error_class, reason)；不发网络请求
                    return stop(TaskOutcome(status=outcome_of(v.error_class), error_class=v.error_class, reason=v.reason, ...))
                try: page = c.parse_chunk(chunk, pctx)
                except ParseError as e:
                    sink.quarantine(task, resp); return stop(TaskOutcome(status="stopped", error_class=e.error_class, ...))
                sink.commit_page(task, page); acct.count_page(page)
            step = Step(resp, Page(records=(), next_cursor=None, signals=PageSignals.streamed(resp.blob)))   # 记录已按块提交：回送合法空页，plan() 继续下一个文件
            continue
        try: page = c.parse(resp, pctx)
        except ParseError as e:
            if e.error_class == "parse":                             # 隔离该页；只有 lookup/search/probe 可继续，其余停在安全点（§7）
                sink.quarantine(task, resp)
                if task.operation not in ("lookup", "search", "probe"):
                    return stop(TaskOutcome(status="stopped", error_class="parse", ...))
            step = Step(resp, None, e.error_class); continue         # 可恢复类（如 cursor_expired）回送 plan() 处理重启
        sink.commit_page(task, page)   # 同事务：source_record upsert + CursorEnvelope 按 rev 比较交换；失败整页回滚
        acct.count_page(page); step = Step(resp, page)
```

**流式导入**（`snapshot_import`）：`plan()` 对大文件发 `stream=True` 的请求，收到的 `Step.resp.blob` 由 runner 按记录边界切成 `SnapshotChunk`，逐块调用纯函数 `parse_chunk(chunk, ctx) -> Page` 并按块提交（游标 `snapshot_release.parts_done` 记到块），连接器不读文件、不开网络；族内其余类型（`SnapshotSpec`、`ImportLedger` 等）见 [bulk-snapshot](families/bulk-snapshot.md)。

规则：生成器不持久化，崩溃或超时后从已提交的 `CursorEnvelope` 重新 `plan()`；`plan/parse/normalize/describe` 纯函数，冻结的 `ctx.now`、实例、SCD、模式上限经 `PlanCtx/ParseCtx/MapCtx` 注入，`idempotency_key`、`payload_sha256` 由 SDK 计算；连接器只能追加有类型的 `PageSignals`，不能改 `EgressEnvelope`；非合法结果（`Step.page is None`）时 `increment/enumerate/snapshot_import` 一律停在最后安全点，只有 `lookup/search/probe` 可逐项隔离后继续；同一 `scope_key` 同一时刻只有一个任务在跑（长稿 §10.3 的同键串行）。

## 6. 游标

`Cursor` 是带 `kind` 的联合，外层 `CursorEnvelope{scope_key, cursor, schema, rev}` 落 05 的 jsonb 列；resumptionToken、cursorMark、deep cursor 只进 `PageSignals.continuation`，不持久化。

| kind | 字段（设计伪代码） | 典型来源 | 推进单位 |
|---|---|---|---|
| `date_watermark` | `field, value, granularity ∈ day|second, overlap, until_fixed` | Crossref `created`、EPMC `FIRST_IDATE`、INSPIRE | 有序端点逐页；无序端点整窗完成 |
| `oai_datestamp` | 同上 + `set, metadata_prefix` | arXiv、PMC、DSpace/EPrints/Invenio 实例 | 整段 ListRecords 完成后推进到 `until`（取 `responseDate`） |
| `guid_set` | `guids: frozenset[str], window_started_at, first_seen_at{guid: datetime}, etag, last_modified, last_poll_at, last_window_n` | RSS/Atom（ECB、BIS、JMLR） | 每次完整 feed 读取 |
| `seq` | `key, value, probe_ahead` | PMLR 卷号、NeurIPS 年页 | 单个序号完成 |
| `snapshot_release` | `release_id, checksum, parts_done[], part_offsets{file_id: record_offset}` | OpenAlex 季度快照、DROPS dblp | 每个块（未完成文件记 `part_offsets`，整文件完成后移入 `parts_done`） |
| `repo_commit` | `repo, commit_sha, path` | ACL Anthology 数据仓库 | 单个 commit |
| `window_set` | `completed[(from, until)], pending[(from, until)]` | 回填、`late_path` 对账 | 单个窗口完成 |

1. **安全提交点**：`Page.next_cursor` 只在两种情况下非空——清单 `ordered: true` 且 `ordered_by` 有 `ordered_fixture`（含乱序反例）验证；或本页是窗口/列表末页。否则为 `None`，整段完成后由 runner 推进到 `until`。
2. **原子推进**：`commit_page` 同事务 upsert `source_record` 并按 `rev` 比较交换，失败整页回滚；策略失效与预算耗尽都在页边界停，游标不越过已提交页。
3. **水位类必填**：`overlap`（重叠回看，裁定补充称 `lookback`）、`granularity`、`bounds`（开闭区间，如 `[from, until)`）、`lag_bound`（上游可见滞后，证据或"未核"）、`late_path ∈ weekly_index_backfill|snapshot_reconcile|none`、`window_max`；运行开始固定 `until`，完成后推进到 `until`；每次从 `cursor − overlap` 起，靠 `(source_id, source_key)` 去重。
4. **乱序**：无序端点（OAI-PMH 不保证按 datestamp 返回）只在整段完成后推进；`ordered_fixture` 是声明 `ordered: true` 的必备件。
5. **续取令牌过期**：`cursor_expired` 从本次运行窗口起点重启 ≤2 次，超次 `stopped` 并告警"切小窗口"；`window_max` 须在令牌 TTL 内可取完（Zenodo 令牌 2 分钟 [https://developers.zenodo.org/, 2026-09-30]、InvenioRDM 默认 1 分钟且过期返回 422 [https://inveniordm.docs.cern.ch/reference/oai_pmh/, 2026-09-30]；eScholarship 24 小时只见长稿 §10.4，未核）。
6. **删除与撤稿**：上游删除产出 `RawRecord(kind=tombstone)`，只置 `deleted_upstream`，不删 Work；feed 条目滚出窗口不算删除；撤稿、撤回、更正是 `NormRecord.status_claims`，经 identify 写 `work_status_event`。
7. **迁移**：游标 kind 或编码变更 = `connector_version` MAJOR，须提供纯函数 `migrate_cursor`，或在卡片 §5 声明"重置 + 回填窗口"。

## 7. 错误矩阵

`error_class` 全集 15 个，每类只有一个判定者（唯一例外 `empty_body`：网关与探针按 reason 分工）；责任方 ∈ `upstream | config | code | policy`（记账用，决定谁开工单）。"停"= 停在最后安全点。

| error_class | 判定者 | 重试 | 任务结果 | 降级与告警 | 责任方 |
|---|---|---|---|---|---|
| `transient` | 网关 | 单请求 ≤3 次尝试 | 耗尽后 stopped | 熔断计数 | upstream |
| `rate_limited` | 网关（含伪 200） | 按头退避，不计失败 | 超 deadline 则 partial | AIMD 下调 | upstream |
| `challenge` | 网关；用户侧执行器用同一判定库（HC-29） | 0；正文不交 parse | stopped（终止） | 请求主机与最终落点主机都冷却 24h；告警 | upstream |
| `gone` | 网关（404/410） | 0 | lookup 逐项标记；列表端点 stopped | 列表端点记漂移 | upstream |
| `parse` | `parse` 抛 ParseError | 0 | stopped，隔离该页 | 结构探针标红；连续 3 次（初值）端点降级 | code |
| `integrity` | 用户侧执行器；平台侧流式下载由网关（字节数与校验和） | 重下 1 次 | 回执 `error` | 配方健康只来自维护者合成检查（P-7）与用户自愿工单 | upstream |
| `auth_expired` | 用户侧执行器 | 0 | 回执 `error` | U2 提示重新授权 | config |
| `no_entitlement` | 用户侧执行器 | 0 | 回执 `no_entitlement` | 原因码 `needs_entitlement` | policy |
| `config` | 加载期 lint / 网关路由 | 0 | 不入队；运行中命中即 stopped | 阻断发布；告警 | config |
| `policy_denied` | 策略引擎 / 网关 | 永不 | denied 或页边界 stopped | 审计；`stale_decision` 重新准入一次 | policy |
| `needs_confirmation` | 策略引擎 | 永不 | denied，零请求 | 进 O4 队列 | policy |
| `empty_body` | 网关按 Expectation；探针（`canary_query`、`count`）判 `count_drop` | 0 | stopped | 端点降级、切替补链 | upstream（Expectation 误判归 code） |
| `budget_exhausted` | 配额账本（含 OpenAlex 美元额度头 `x-ratelimit-remaining-usd`，F1 2026-09-30） | 下一预算窗口 | partial | O6；不计入健康 | config |
| `cursor_expired` | `parse`（`badResumptionToken` 等） | 从窗口起点重启 ≤2 次 | 超次 stopped | 告警"切小窗口" | upstream（`window_max` 过大归 config） |
| `disabled` | ops 急停 / health suspended / lifecycle retired | 0；不冷却 | stopped，游标不动 | 不计错误率；owner 可解除 | config |

- **401/403**：`auth: deployment/*` 端点归 `config`（停、告警、不冷却）；其余不明 401/403 一律按 `challenge` 从严，除非 `status_overrides` 凭 `upstream_facts` 声明了该端点文档化的语义（如配额、匿名拒绝）。状态码因源而异一律走覆盖表，连接器代码不自映射状态码。
- **子码**：`policy_denied/{stale_decision, redline, user_channel, kill_switch, robots}`、`config/undeclared_host`、`challenge/cooldown`、`empty_body/count_drop`。合规 kill switch 用 `policy_denied/kill_switch`（进审计，恢复须双人）；运维停用用 `disabled`（不进合规审计）。
- `policy_denied`、`needs_confirmation`、`challenge` 永不重试；未知错误隔离、不重试（fail-closed）。
- 用户侧回执五类 `ok`、`no_entitlement`、`challenge`、`handed_to_user`、`error`；"为什么没有全文"原因码六类 `no_legal_oa`、`needs_entitlement`、`publisher_only`、`challenge`、`paused_by_source_rules`、`error`，每类都带"在出版社打开"（文案见 [connector-ui](connector-ui.md)）。

## 8. NormRecord 映射契约

`normalize(raw, MapCtx) -> NormRecord` 永远是带 `mapper_version` 的代码（不做映射 DSL），配黄金 NormRecord。

| 规则 | 内容 |
|---|---|
| 只输出声明 | 标识符粒度查注册表粒度表（含 `doi_family` 前缀映射），mapper 不自报 |
| `version_claim` | `{stage ∈ preprint|am|vor|wp|unknown, seq, basis}` |
| 许可 | 原串 + 经 `license_alias` 归一的码；不确定即 `unknown` |
| 权利 | HC-07 字段（`rights_class`、`display_level_max`、`shareable`、`commercial_ok`）由共享 `classify_rights()` 计算，mapper 不得直接给出；未知即不共享（HC-05） |
| `basis` | 许可、权利、版本、关系四类字段都带载荷路径 |
| `work_assertion` | OpenAlex W、S2 corpusId 等聚合器 id 只作作品断言，不作强标识符 |
| `identifiers_emitted` | 输出方案 ⊆ 清单声明；黄金覆盖每个方案 |
| `payload_sha256` | 规范化载荷（JSON 键排序、XML C14N）去掉 `volatile_fields` 后计算；原载荷照存 |
| tombstone | 只含标识符与 `deleted_upstream` |

## 9. SCD

`describe(sourcespec, manifest, instance) -> SCD` 是纯函数；技术事实以 manifest 为准，`describe()` 只补 emulated 能力；输出带 `derived_from{sourcespec_sha256, manifest_sha256, connector_version}`，CI 重生成后差异须为 0。静态 SCD 只含生命周期 `active|deprecated`；health、实测限额、滞后、暂停只写 ops，由 04 的单一访问器叠加，叠加只能收紧（谓词只降级、上限只变小、成本只变高）。`scd_version` 归 `contract_version` 管，不是第四个版本号。Crossref 在 SCD 中写死不声明 `search`（main 03/04 口径，长稿 04 `works_query` 服务 SEARCH 的写法作废）。

## 10. 探针

```python
# 设计伪代码
@dataclass(frozen=True)
class ProbeSpec:
    probe_id: str
    kind: Literal["robots", "tos_hash", "tdmrep", "structure", "deprecation", "canary_query", "count"]
    target: str                      # endpoint_id 或 host
    schedule: str                    # ISO 8601 周期
    expectation: Mapping             # 如 {"n_records_min": 30, "per": "session"}
    on_fail: Literal["alert", "freeze_promotion", "degrade_endpoint"]
```

每条 `upstream_facts` 映射到一个探针；探针请求同样经网关、调度时取 decision；结果只写 ops，经 `EffectiveStatus` 合成。`canary` 一词只指发布阶段，探针类叫 `canary_query`。技术事实过期只冻结 CL 晋级并告警，不改策略模式；合规证据过期走 03 的 `review_overdue`。HTML 类 `site_special` 必须有 `structure` 探针加按会期设期望计数的 `canary_query`；`canary_query`（已知答案）与 `count`（基线）两类探针的计数骤降都记 `empty_body/count_drop`。

## 11. 全文：FulltextOption 与 FulltextRecipe 的边界

```python
# 设计伪代码
@dataclass(frozen=True)
class FulltextOption:
    kind: Literal["oa_link", "tdm_api", "user_fetch", "open_in_tab"]   # 02 的四值；03 六级候选映射进 kind + 排序
    url: str; version_claim: VersionClaim; license: LicenseClaim; basis: str
    recipe_ref: tuple[str, int] | None   # (recipe_id, version)；只有 tdm_api / user_fetch 有
```

平台侧 `locate_fulltext` 只产选项，永不代取受限全文。`FulltextRecipe` 是数据，平台不向端侧下发代码：

| 约束 | 规则 |
|---|---|
| 步骤 | 封闭枚举 `request`、`resolve`、`entitlement_probe`、`download`、`expect`、`extract_link`；schema `additionalProperties: false` |
| 凭证占位符 | `{user_secret:<name>}` 只许出现在 `request.headers`，该步 `allowed_host` 是字面量 HTTPS 主机；确需 query 传 key 的须标 `secret_in_query` 并经评审 |
| `expect`、`limits` | 复用 `Expectation`（含 `magic`）；`limits` 只能比 08 更严（间隔 ≥6 s、日 ≤200） |
| `on_challenge` | 固定常量 `stop_then_open_in_tab` |
| 签发 | 随 PolicyBundle 签名、绑定实例主机；过期只剩 `open_in_tab` |
| 判定库 | 用户侧执行器复用网关同一套 robots 与挑战判定库（HC-29） |
| 禁止 | 执行下发 JS、填表单、点验证码或同意按钮、并发、白名单外主机、读无关 cookie |

## 12. 凭证与审计

- 部署级凭证只以 `AuthRef(deployment/<credential_id>)` 引用，网关注入，每个上游一个身份（HC-10）；UA 只由网关写 `Confluo/<ver> (+<部署方说明页>; mailto:<部署方联系邮箱>)`，上游拒绝时不换 UA，被拦即 `challenge`。
- 令牌桶五元组 `(source, host, request_class, credential, egress_ip)` 的"凭证"维含部署 mailto 身份（Crossref 按 mailto 限流 [https://community.crossref.org/t/refining-rest-api-limits-for-improved-stability-and-reliability/16137, 2026-07-21 公告，F1 2026-09-30 核对]；分池起始 F1 写 2026-07-21、G 写 2025-12-01，两说待核）。
- robots 例外只出自 D-049 附表或 PolicyOverride；`robots_exception_ref` 由网关写、非空；`api_conflict` 只放 on_demand。
- 每次出站尝试（含拒、重试、挑战、超时）由网关在 FetchLog 写恰好一行，连接器不写审计。字段：`fetch_id, at, decision_id, inputs_epoch, task_id, connector_ref, operation, traffic_class, source_id, channel, endpoint_id, upstream_class, host, path_template, params_digest, status, bytes, duration_ms, wait_ms, attempt, error_class, reason, robots_verdict, robots_snapshot_sha, robots_basis, robots_exception_ref, ua_version, egress_ip_id, cache_hit`；`upstream_class` 即 `request_class`（P-1 改名后与 `traffic_class` 并列）；不含 `user_id` 与查询原文（SEARCH 只存 `params_digest`）；凭证回显与日志一律脱敏。
- 录制器在网关（record 模式）：fixture 本质是 (RequestSpec, Response) 对，只经 staging 网关 dry-run 录制并自动脱敏；连接器侧不 monkeypatch HTTP 库。

## 13. 可观测性与 EffectiveStatus

指标由 runner 与网关统一发出：`connector_requests_total{connector_id, endpoint_id, error_class, rollout}`、`connector_parse_quarantine_total`、`connector_cursor_lag_seconds`、`connector_cursor_expired_restarts_total`、`connector_payload_change_ratio`、`connector_license_unknown_ratio`、`connector_budget_used{account}`、`connector_probe_status{probe}`；标签不放 user、WatchKey、venue、查询；venue 级新鲜度写 `ops.harvest_run`。`health ∈ {healthy, degraded, suspended, disabled, retired}`（来自 SLI、探针、急停）与 `policy_mode`（来自策略引擎）分离，合成 `EffectiveStatus{cl_declared, cl_effective, health, policy_mode, reasons[]}`，按 (connector, endpoint, channel) 计算，是路由与 U1/U7/O1 的唯一状态来源。用户侧回执不进任何跨用户统计（08），运维台不显示用户侧成功率；配方健康只来自维护者合成检查（P-7）与用户自愿工单，若要聚合回执须另立 ADR（见未决事项）。

## 14. 版本与兼容

| 版本号 | 何时升 | 兼容要求 |
|---|---|---|
| `contract_version`（整数） | 协议不兼容时 | runner 同时兼容 N 与 N−1；`scd_version` 随之 |
| `connector_version`（semver） | MAJOR：请求语义、游标 kind 或编码、`serves` 删减；MINOR：新端点或新 Operation；PATCH：其余 | 游标变更须 `migrate_cursor` 或声明"重置 + 回填窗口" |
| `mapper_version`（按 `mapper_id` 递增） | 任一黄金输出变化 | PR 附新旧 mapper 字段级 diff 并更新黄金 |

发布阶段 `shadow`（并跑只比差异、不落库）→ `canary`（≤10% 实例或 WatchKey）→ `full`，是 ops 层状态，不进 YAML；配方版本随 PolicyBundle 签名。弃用：`lifecycle.state=deprecated` 后，`upstream_sunset` 距到期 ≤90 天须备好替补或迁移卡；`retired` 即 CLX，移出路由，保留清单、fixture、黄金与来历；`connector_id` 永不复用。

## 15. 声明式与代码的边界

`impl` 阶梯默认最低可行级，上调一级须在卡片 §13 写理由。

| 级 | 允许 | 止于 |
|---|---|---|
| `instance` | 只打开族引擎已登记的 quirk 旗标（每个旗标有 fixture） | 实例 YAML |
| `declarative` | 路径模板 + `paginator` + `cursor` + `Expectation` + `request_class` + `budget` | RawRecord；映射复用族 mapper |
| `mapper` | 上一级 + 本连接器的 `normalize` 代码 | NormRecord |
| `custom_plan` | 上一级 + 自写 `plan()`（仍是生成器、仍纯函数） | 全部协议 |
| `v1_bridge` | 包装 v1 adapter（§17） | 过渡 |

路径模板封闭占位词表：`{instance.base_url}`、`{instance.site_host}`、`{cursor.from}`、`{cursor.until}`、`{set}`、`{token}`、`{page}`、`{offset}`、`{id}`、`{doi}`、`{prefix}`、`{issn}`、`{member}`、`{query}`；无 Jinja、无条件、无表达式，超出词表即升 `custom_plan`。`paginator` 四种：`cursor{param, path, first}`、`token{param, path, page_size}`、`offset{param, page_size, max}`、`page{param, page_size, max}`。新怪癖进族引擎或升 `site_special`；不允许实例级 Python 钩子；`normalize` 永远是代码。

## 16. 安全规则与静态检查

| 检查 | 内容 | 阶段 |
|---|---|---|
| 依赖禁表 | 连接器包不得导入 `requests`、`httpx`、`aiohttp`、`urllib3`、`curl_cffi`、`cloudscraper`、`playwright`、`selenium`、`undetected-chromedriver`、`tls-client`、`scholarly` 等 HTTP、浏览器自动化、TLS 指纹与验证码类库；第三方客户端库只用解析部分（待拍板 P-2） | CI import 规则 |
| 连接器 lint（6 条，CL0 门） | ① `allowed_hosts` 每个主机有 robots 条目；② 无凭证头、无 `personal_params`；③ 无红线 URL；④ `kind` 与 `exec_side` 一致；⑤ 每端点有 `Expectation`；⑥ 每条技术事实有证据 | CI |
| 注册表 lint 13 条（编号 L1…L13，见[一致性文档](conformance-and-testing.md) §1.2） | 沿用长稿 §3.8，含 lint 9（盗版源与 Google Scholar 只能 `excluded`）与 lint 12（IEEE、ACS、ACM 的全文通道只能 `link_out`/`none` 且不得引用配方；模板与配方不得出现 arXiv `/e-print/`、`/src/`） | CI |
| 无网沙箱 | 契约测试在无网络命名空间运行；socket、时钟、环境、文件替换为抛错 | CI |
| fixture 扫描 | key、cookie、邮箱、受版权正文 | CI |
| 网关运行时 | 主机白名单 + SSRF（每跳）、红线禁表先于 robots、UA 只由网关写、worker 无公网路由、kill switch 三级（连接器 / 来源 / 主机）即时生效、双人恢复 | 运行时 |

## 17. v1_bridge 过渡条款

- 桥接期允许 v1 adapter 经网关垫片发请求：垫片把 v1 HttpClient 调用改写为 RequestSpec 交网关，仍全部经网关、可审计、受策略双判定、受依赖禁表约束（v1 传输层被替换）；但不满足"声明式 plan"要求，`impl` 恒为 `v1_bridge`。
- 每个被包装的 adapter 独立 manifest，含 `v1{adapter, destiny ∈ platform_bridge|family_config|snapshot_rewrite|user_side|paused|retired, mode ∈ platform|replay_only|pc_agent, port_target, sunset_by, parts[]}`（`mode: platform` 只许 `destiny: platform_bridge`；部分废止写在 `parts`）；限期 V2 出口前移植到对应族或退役。
- 可到 CL3；过 `sunset_by` 自动降 CL2 并开移植卡；移植完成判据是 v1 fixture 与近 N 天样本上 shadow 等价，随后 bridge 转 CLX。
- platform 模式静态禁用 `fetch_asset`；pc_agent 模式只许随 pc-agent 签名发布的代码，平台不下发代码，仍须签名 RetrievalIntent；本批默认不用，启用走待拍板。
- 20 个 v1 adapter 的去向见 [v1-bridge 族](families/v1-bridge.md) 与[实施计划](implementation-plan.md)。

## 18. 与九族的关系

族文档在本契约之上定义族专有接口、实例字段、族一致性套件与逐连接器卡片：[aggregator-api](families/aggregator-api.md)、[oai-pmh](families/oai-pmh.md)、[feed](families/feed.md)、[crossref-delegated](families/crossref-delegated.md)、[bulk-snapshot](families/bulk-snapshot.md)、[platform-family](families/platform-family.md)、[official-tdm-api](families/official-tdm-api.md)、[site-special](families/site-special.md)、[v1-bridge](families/v1-bridge.md)。族专有接口不得放宽本文任何规则；`official_tdm_api` 与用户侧 `platform_family` 只实现 `RecipeProvider`；用户侧的元数据查询连接器（aggregator_api 的 `nasa_ads_api`、`lens_api`、`alphaxiv_mcp`、`orcid_api`）本版没有对应协议，见未决事项。来源 × 连接器矩阵见 [connector-matrix](../../../catalog/connector-matrix.md)，卡片模板见 [connector-card-template](connector-card-template.md)。

## 怎么验收

映射到 [conformance-and-testing.md](conformance-and-testing.md) §3 的通用契约测试 CT-01…CT-12（CL1 门）：

| 本文条款 | 检查 |
|---|---|
| §1 F1、F7 | CT-01 零 I/O；依赖禁表；无网沙箱 |
| §5 纯函数、§8 映射 | CT-02 同 fixture、同 `ctx.now` 两次运行逐字节相同；CT-06 黄金覆盖每个方案、权利类、tombstone 与撤稿 |
| §3、§4 无 user 上下文 | CT-03 不同用户上下文下 RequestSpec 序列相同 |
| §6 游标 | CT-04 乱序、崩溃注入、令牌过期属性测试；CT-09 `ordered_by` 附乱序反例 |
| §2 `status_overrides`、§3 Expectation | CT-05 矩阵每行、Expectation 每个分支至少一个 fixture |
| §9 SCD | CT-07 `describe()` 重生成差异为 0 |
| §14 版本 | CT-08 版本门（黄金变而 `mapper_version` 未升、游标编码变而 MAJOR 未升即失败；`migrate_cursor` 有旧样本测试） |
| §7、§12 | CT-10 无凭证头、无 `personal_params`、robots 例外只来自 decision、挑战即终止重试 0、伪成功与空体归类正确；CT-11 本连接器黄金决策行 |
| §16 | CT-12 fixture 扫描；连接器 lint LC-01…LC-06（CL0 门，依次对应 §16 的 ①–⑥） |
| §2 三层分工 | lint：`allowed_hosts` = 并集且 ⊆ SourceSpec hosts；Manifest 无运行态字段；证据不复制 |

同键串行、幂等提交、令牌桶键属于 runner 与网关的不变式，在平台 PR 中测试。

## 待拍板

编号沿用评审团清单：P-1 05 `ops.fetch_log.request_class` 列改名 `traffic_class`；P-2 长稿 §5.6 复用的 openreview-py、metapub、acl-anthology 自带 HTTP，只用解析部分或替换传输层；P-3 05 `ops.watch_key` 缺 `rev`，且无 enumerate 与快照导入按 `scope_key` 的进度表；P-4 CL2 生产口径（限 on_demand 或 deny）；P-5 `rights_class` M1–M25 与来源七类 M1/M2 撞名，03 `abstract_rights` 与 08 权利字段缺对照表，本文只引用不定义；P-6 端侧日上限计数键按平台还是按域；P-7 用户侧配方维护者本人凭证的合成检查口径须 08 认可；P-8 personal 部署里同一把 S2/OpenAlex key 的凭证分类；P-9 `norm_record.mapper_version` 存储格式 `"<mapper_id>@<n>"`（05 为 text）；P-10 载荷清除后 mapper 升级无法重算，LOOKUP 重取或接受混合版本并在 `provenance` 标注。P-11（CL3 族引擎新增实例的 staging 天数）与 P-12（维护点数与复核节奏数值）归[一致性文档](conformance-and-testing.md)。P-13（本批追加）：是否在契约 v1.x 增加 `QueryRecipe`（用户侧元数据查询配方）；v1 不新增协议，相关 4 个连接器停在 CL0（见未决事项）。本文新增：`endpoints[].status_overrides` 作为状态码覆盖表落点（裁定补充要求"按请求类声明"，本文按端点声明，端点唯一对应一个 `request_class`）；`overlap` 与 `lookback` 取 `overlap` 为字段名；`v1.destiny` 六值与 `v1.mode`、`port_target`、`parts` 采用 v1-bridge 族文档的命名（该文档已请契约确认）。

## 未决事项

- `lag_bound` 多数来源尚无证据，卡片先写"未核"，CL2 观测期补。
- `PlanCtx.mode_caps` 的具体字段（每任务请求上限、并发、时段）待实施计划 W0 与 02 舱壁份额对齐。
- `Response.headers` 白名单（哪些上游头对连接器可见）待网关详设；本文只要求不含 Set-Cookie 与凭证回显。
- `ProbeSpec.expectation` 的 schema 按探针类分别定义，归一致性文档。
- `health=suspended` 的 SLI 阈值（触发 `disabled` 的边界）待 CL3 runbook 定义；本文只定语义。
- 用户侧元数据查询配方（aggregator-api 族提议的 `QueryRecipe`，U-1）：契约 v1 不新增协议，`RecipeProvider` 只产 `FulltextRecipe`；`nasa_ads_api`、`lens_api`、`alphaxiv_mcp`、`orcid_api` 与 `openreview_api` 的用户侧（本人 token 查询，D-052）在 v1 停在 CL0，实施计划只保留波次占位，是否在 v1.x 增加 `QueryRecipe` 列为待拍板 P-13。
- 回执聚合：按配方版本聚合用户侧回执（即使 ≥`k_cf`）与 08"回执不进任何跨用户统计"冲突，v1 不做；如需要，须新 ADR 并经 08 评审。
- 已收录进本文的族提议：`RawRecord.kind=presence`（§3）、`RequestSpec.stream`、`Response.blob`、`BlobRef`、`SnapshotChunk`（§3、§5）、平台侧 `integrity` 由网关判字节与校验和（§7）、`snapshot_release.part_offsets`（§6）、`guid_set` 的条件请求字段（§6）、`IncrementInput.mode`（§3）、304 规则（§3 `Expectation`）。仍待 V0 裁定：05 的在场表存放、bulk 记录数对账的归类、`request_class=bulk_object`；aggregator-api 的 `config` 子码 `terms_gate`、`plan_required` 与 `budget.unit=token`；feed 的 `on_gap` 替补对账触发与调度提示（`TaskOutcome` 目前不带调度提示）。
- 族核心连接器的 `impl` 记法：`crossref_delegated` 记 `custom_plan`（引擎级），`oai_pmh`、`feed` 记 `instance`；V0 统一为"族核心记引擎自身的级别、实例记 `instance`"。
- §2 的 `europe_pmc_rest` 清单示例与族卡片在 `connector_version`、`source_key_rule`、`late_path` 上有出入，实现以族卡片为准。
- 责任方维度的取值是本文裁量：`auth_expired`、`disabled`、`budget_exhausted` 记 config，`no_entitlement` 记 policy，待评审确认。
- InvenioRDM 令牌过期返回 HTTP 422（F2）：由网关 `status_overrides` 还是 `parse` 判 `cursor_expired`，须保持单一判定者，W0 定。
- `LocateCtx` 与 `VersionView` 的字段未在本文定义，待 W0 与 03 身份模型对齐。
- 篇幅约 55 KB，超出设计类 ≤25 KB 目标与 45 KB 上限；本轮只合并明显重复，实现期把类型定义（§3）与字段表（§2 清单字段、§6 游标表、§7 错误矩阵）拆为附录，不删规则。

更细的材料：`git show v2-drafts:docs/plan/v2/03-sources-and-corpus-pipeline.md`（§5、§10.2–10.8、§12.4、§13、§15）；[README](README.md)；[实施计划](implementation-plan.md)。
