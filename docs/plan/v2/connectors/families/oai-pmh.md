---
title: OAI-PMH 族规范与连接器卡片
status: draft
owner: opus5.5-primary
updated: 2026-09-30
---

# OAI-PMH 族（`oai_pmh`）

本文回答：任意 OAI-PMH 2.0 端点怎样用一个族引擎加零代码实例接入；arXiv、AAAI OJS 两个带专用配置的连接器怎样落在同一引擎上；resumptionToken 过期、删除对账、限速与漂移怎样处理。结论：族引擎移植 v1 `adapters/_oai.py` 信封核，按[连接器接口契约 v1](../contract.md)改成"声明请求 + 解析响应"；每个端点一份 `OaiInstance`，必须声明 `granularity`、`deleted_record`、`token_ttl_s`、`ordered_by_datestamp`；游标用 `oai_datestamp`，默认只在整段列表完成后推进到本次运行固定的 `until`；token 过期从本次窗口起点重启，最多 2 次；`persistent` 端点直接消费删除头，`transient` 与 `no` 端点周期性做 `ListIdentifiers` 在场对账，删除只置 `deleted_upstream`。本族 3 个连接器：族核心 `oai_pmh`（15 个来源的实例）、`arxiv_oai`（W0 参考连接器）、`aaai_ojs_oai`（v1 移植）。

## 要点

- 一个引擎、多份实例：新端点走 SOP B（≤30 分钟），实例只能打开本文 §3 登记的封闭 quirk 旗标；新怪癖进引擎或升 `site_special`（契约 §15）。
- OAI-PMH 不保证按 datestamp 返回，`ordered_by_datestamp` 默认 `false`：中间页照常落库，安全提交点只在末页出现；只有附乱序反例 fixture 验证过的实例才可逐页推进。
- 删除语义三种都有（与长稿不同，逐实例见 §3）：`persistent` 消费删除头，`transient/no` 必须配对账策略。
- token 寿命差异大（arXiv 按日、Zenodo 约 2 分钟、InvenioRDM 1 分钟），续页立即发出；`badResumptionToken` 归 `cursor_expired`（v1 记 TRANSIENT）。
- arXiv 平台侧只用 `oaipmh.arxiv.org` 的 OAI-PMH，只拉 `arXivRaw` 一种格式；查询 API 两个主机 robots 禁止，SCD 不声明 `search`。
- `responseDate` 不一定可信（arXiv Identify 被 CDN 缓存约 11.9 天），`until` 与 ctx.now 偏差过大即改取 ctx.now，并计漂移信号。
- 本族只收元数据与 OA 链接；共享 OA 全文走许可白名单（[03](../../03-sources-and-corpus-pipeline.md#语料流水线与-enrich)），CC 许可 arXiv e-print 能否单篇进共享缓存待拍板。

## 1 本族回答什么、适用边界

- **回答**：`ListRecords` 增量与回填、`GetRecord` 按需单篇、`ListIdentifiers` 在场对账、`Identify` 等探针；一律 `platform`，后台收割依策略（[03 九族](../../03-sources-and-corpus-pipeline.md#连接器九族与执行位置)）。
- **与 `platform_family` 的分界**：仓储软件族提供 `oai_defaults()` 默认路径与平台指纹，只在新实例预填与平台迁移探测时参与；收割、游标与映射都在本族（见 [platform-family](platform-family.md)）。
- **与 `crossref_delegated` 的分界**：同一来源常两条通道并存（AAAI OAI + Crossref 10.1609、Numdam OAI + Crossref 10.5802）；Crossref 为主时 OAI 只补 OA 链接、许可与缺失字段，两路 NormRecord 由 identify 合并（见 [crossref-delegated](crossref-delegated.md)）。
- **与 `bulk_snapshot` 的分界**：PMC S3（`pmc_s3`）、zBMATH KG dump（`zbmath_kg_dump`）承担全量与删除对账，本族对这两个来源只跑日常增量与补缺（见 [bulk-snapshot](bulk-snapshot.md)）。
- **与 `aggregator_api` 的分界**：同源 REST（`zbmath_open_api`、`doaj_api`、`hal_api`）归聚合族，一个连接器不混用两种协议。
- **与 `v1_bridge` 的关系**：`arxiv_oai`、`aaai_ojs_oai` 在第一阶段清单中为 bridge，去向是"移植为本族实例"，完整卡片在本文，[v1-bridge](v1-bridge.md) 写桥接期条款；桥接只作回放对拍，V2 出口前转 CLX。

## 2 族专有接口

通用类型（`RequestSpec`、`Expectation`、`Page`、`PageSignals`、`RawRecord`、`CursorEnvelope`、`Step`、`TaskOutcome` 等）以 [contract](../contract.md) 为准，本节只写本族在其上的专有部分。

```python
# 设计伪代码 —— oai_pmh 族专有部分（通用协议见 ../contract.md；字段名以契约为准）

@dataclass(frozen=True)
class OaiInstance:                         # registry/instances/oai_pmh/<instance>.yaml 的内存形态
    instance_id: str
    source_id: str
    base_url: str                          # 续页也用它，不用 Identify 声明的 baseURL
    metadata_prefix: str                   # arXivRaw / oai_dc / pmc_fm / dim / oai_datacite / oai_zb_preview …
    sets: list[str] | None                 # None = 整库；由 WatchKey 编译或 VenueSpec 给出，不硬编码逐年变化的 set
    granularity: Literal["day", "second"]   # 与契约 date_watermark 取值一致
    deleted_record: Literal["no", "transient", "persistent"]
    earliest_datestamp: str
    token_ttl_s: int | None                # None = 未核；arXiv 按 UTC 日界失效、Zenodo 约 120、InvenioRDM 默认 60
    ordered_by_datestamp: bool = False     # True 须附 ordered_fixture（含乱序反例）
    send_until: bool = False               # 增量默认不带 until（arXiv 官方建议）；回填窗口带 until
    page_size_hint: int | None = None      # 只用于估算与探针，以上游为准
    request_class: str = "oai"             # 同一上游全部端点共用一类，保证一个令牌桶（arXiv）
    reconcile: "ReconcilePolicy | None" = None   # deleted_record ∈ {transient, no} 时必填
    quirks: frozenset["OaiQuirk"] = frozenset()  # 封闭枚举，每个旗标配 fixture

class OaiQuirk(Enum):
    RESPONSE_DATE_UNTRUSTED = 1   # CDN 缓存（arXiv）：until 取 ctx.now，不取 responseDate
    HTTPS_CONTINUATION = 2        # Identify 声明 http、实际 https（Numdam）：续页强制用 base_url
    OFF_PEAK_BULK = 3             # PMC：美东工作日 05–21 时单任务 ≤100 次请求，超出在安全点 partial
    NO_OAI_DC = 4                 # 不提供规范要求的 oai_dc（INSPIRE 候选实例）
# 状态码语义（InvenioRDM 过期回 422）不做 quirk，按契约写进实例端点的 status_overrides

@dataclass(frozen=True)
class ReconcilePolicy:
    every: str                            # ISO 8601 周期，如 "P7D"、"P30D"
    via: str = "self"                     # "self" = 本实例 ListIdentifiers；否则写承担对账的 connector_id（pmc_s3、zbmath_kg_dump）
    absent_passes_to_tombstone: int = 2   # 连续两次"完整"对账都缺席才出墓碑

class OaiPmh(PlatformConnector):
    def plan(self, task: ConnectorTask, ctx: PlanCtx) -> Generator[RequestSpec, Step, TaskOutcome]:
        inst = ctx.instance
        if task.operation == "enumerate" and task.payload.mode == "reconcile":   # 模式来自 EnumerateInput，plan_key 只作缓存与审计键
            return (yield from self._reconcile(task, ctx))
        frm, sset = window_start(task.cursor, inst), set_of(task.scope_key)   # 水位 − overlap；set 取自 scope_key
        req_until = frozen_until(task, inst)           # send_until=False 时为 None（不带 until）
        until = req_until                              # 带 until 时推进到它，否则由 fix_until() 固定
        restarts = 0
        req = list_records(inst, frm, set_=sset, until=req_until)
        while req is not None:
            step = yield req
            if step.page is None:
                if step.error_class == "cursor_expired" and restarts < 2:   # parse 判定 badResumptionToken；InvenioRDM 422 的判定者待 W0 定（契约未决）
                    restarts += 1                      # 从本次窗口起点重启；已落库的页由 (source_id, source_key) 去重吸收
                    req = list_records(inst, frm, set_=sset, until=req_until)
                    continue
                return stop_at_last_safe_point(step)   # 其余非合法结果：停在上一个安全提交点，游标不动
            until = until or fix_until(step.page.signals.response_date, ctx.now, inst)
            token = step.page.signals.continuation     # resumptionToken 只在内存中，不持久化
            req = resume(inst, token) if token else None   # 立即续取
        return completed(next_cursor=oai_datestamp(until))  # 整段完成才推进
    # parse(resp, ctx)：信封核（移植 _oai.py）+ 按 metadata_prefix 注入的体层解析器；
    #   header status="deleted" → RawRecord(kind="tombstone")；ordered_by_datestamp=False 时中间页 next_cursor=None

def fix_until(response_date, now, inst):
    if OaiQuirk.RESPONSE_DATE_UNTRUSTED in inst.quirks or response_date is None:
        return truncate(now, inst.granularity)
    if abs(response_date - now) > timedelta(hours=1):   # 偏差过大：不信 responseDate，记漂移信号 oai_stale_response_date
        return truncate(now, inst.granularity)
    return truncate(min(response_date, now), inst.granularity)
```

**信封错误映射**（沿用 v1 `_oai.py`，一处改口径）：`noRecordsMatch` → 合法空页（`PageSignals.legit_empty`）；`badArgument`、`badVerb`、`cannotDisseminateFormat`、`noSetHierarchy` → `config`；`idDoesNotExist` → `gone`（只在 `GetRecord`）；`badResumptionToken` → `cursor_expired`（v1 为 TRANSIENT；InvenioRDM 的 422 经实例 `status_overrides` 声明为同类）；未知错误码与根元素不符 → `parse`。HTTP 503 + `Retry-After`（OAI 规范的流控）与 429 → `rate_limited`；Zenodo 在 200 响应上也带 `retry-after: 60`，本族要求网关只在 429/503 上按 `Retry-After` 退避（列入未决）。网关挑战检测先于解析，命中即 `challenge`，正文不交 parse。

**在场对账**（`transient` 与 `no` 实例）：

```python
# 设计伪代码 —— 在场对账；Operation = enumerate，scope_key = "oai:<instance>:<set|*>:reconcile"
def _reconcile(self, task, ctx):
    req = list_identifiers(ctx.instance, set_=set_of(task.scope_key))   # 不带 from：整段
    while req is not None:
        step = yield req
        if step.page is None:
            return stop_at_last_safe_point(step)                 # 被截断：不参与删除判定
        token = step.page.signals.continuation
        req = resume(ctx.instance, token) if token else None
    return completed()                                       # 只有 completed 计为完整对账
# parse 在对账模式下只产出 header 形态的 RawRecord(kind="presence")（本族对契约 RawRecord.kind 的补充提案）；
#   commit_page 只写在场表、不动 source_record 的载荷；header 带 status="deleted" 的直接出 tombstone。
# ingestor 侧 tombstone_by_absence(scope)：本地有、连续 absent_passes_to_tombstone 次完整对账都缺席的 source_key
#   → RawRecord(kind="tombstone")，只置 deleted_upstream，不删 Work；撤稿与更正仍走 status_claims。
```

## 3 实例与清单字段

**ConnectorInstance**（`registry/instances/oai_pmh/<instance>.yaml`）：必填 `instance_id`、`source_id`、`base_url`、`metadata_prefix`、`granularity`、`deleted_record`、`earliest_datestamp`、`token_ttl_s`（可为 `null` 并标"未核"）、`ordered_by_datestamp`、`request_class`、`budget{account, unit, ceiling{min_interval_s}, evidence}`（契约字段；并发上限与跨出口 IP 合计 `scope` 为本族补充）；`deleted_record ≠ persistent` 时必填 `reconcile`；可选 `sets`、`send_until`、`page_size_hint`、`quirks[]`、`mapper_id`（缺省用引擎的 `oai_dc` 映射）。首次接入先经网关跑 `Identify`、`ListMetadataFormats`、`ListSets`（G1 前只许这类自描述请求），把四元组（`baseURL`、`earliestDatestamp`、`deletedRecord`、`granularity`）与格式集合写进实例文件，作为结构探针基线；fixture 在 G1 签字后经 staging 网关录制。

**ConnectorManifest 的本族字段**：族引擎 `oai_pmh` 的 `endpoints[]` 按来源生成，每来源至多 6 个，`endpoint_id` 按契约写 `<source_id>.<name>`（同源多实例共用端点，路径 `{instance.base_url}`）：`oai_identify`、`oai_list_metadata_formats`、`oai_list_sets`、`oai_list_records`、`oai_list_identifiers`、`oai_get_record`（如 `econstor.oai_list_records`）；`paginator.kind = token`；`cursor.kind = oai_datestamp`（`list_records`）；对账端点无持久游标。`hosts_touched` 由实例文件的 `base_url` 主机生成，lint 校验 ⊆ 对应 SourceSpec 通道的 hosts；新增实例的 PR 同时提交重新生成的 manifest（与契约"allowed_hosts = 并集且 lint 相等"一致）。`Expectation`：`content_types ∈ {text/xml, application/xml}`、`root = OAI-PMH`、`min_bytes = 200`、`empty = error`（合法空只经 `noRecordsMatch`）、`legit_status = [200]`。XML 解析禁外部实体与实体扩展（defusedxml 口径）。

**实例清单**（名录来源 15 个 + 2 个专用连接器；事实为 [URL, 2026-09-30] 实测，标"长稿""未核"者除外；波次按框架规则，登记级不排）：

| 实例 | source_id | base_url | 格式 | 粒度 | 删除 | token / 页 | 限速与 robots | 优先级 · 波次 | 证据 |
|---|---|---|---|---|---|---|---|---|---|
| `arxiv` | `arxiv`（连接器 `arxiv_oai`） | `https://oaipmh.arxiv.org/oai` | `arXivRaw` | day | persistent | 按日过期，无 cursor/completeListSize | 全平台 ≥3 s、单连接；OAI 主机 robots 404 | P0 · W0 | [OAI 文档](https://info.arxiv.org/help/oa/index.html) |
| `aaai`、`icwsm` 等 9 个 | `aaai_ojs`（连接器 `aaai_ojs_oai`） | `https://ojs.aaai.org/index.php/<CONF>/oai` | `oai_dc` | second | persistent | 每页 100（OJS 默认） | 未文档；robots 只禁 `/cache/` | P0 · W2 | [Identify](https://ojs.aaai.org/index.php/AAAI/oai?verb=Identify) |
| `pmc` | `pmc` | `https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/` | `pmc_fm` | day | no | ListRecords 10 条/页、ListIdentifiers 50 | 3 rps、禁并发、`OFF_PEAK_BULK`；robots Crawl-delay 1、Allow `/api/` | P0 · W1（只补缺，对账 via `pmc_s3`） | [OAI 文档](https://pmc.ncbi.nlm.nih.gov/tools/oai/) |
| `zbmath` | `zbmath_open` | `https://oai.zbmath.org/v1/` | `oai_zb_preview` | second | no | 未核 | "合理速率"，建议 ≤1 rps 串行；robots 404 | P0 · W1（对账 via `zbmath_kg_dump`） | [Identify](https://oai.zbmath.org/v1/?verb=Identify) |
| `econsoc_te` | `econsoc_journals` | `https://econtheory.org/ojs/index.php/te/oai` | `oai_dc` | second | no | 每页 100（OJS 默认，未核） | robots 只禁 dotbot、bingbot | P0 · W1 | [Identify](https://econtheory.org/ojs/index.php/te/oai?verb=Identify) |
| `econsoc_qe` | `econsoc_journals` | `https://qeconomics.org/ojs/index.php/qe/oai` | `oai_dc` | 未核 | 未核 | 未核 | 2026-09-30 TLS 证书过期，探针转绿前不启用 | P0 · W1 | [Identify](https://qeconomics.org/ojs/index.php/qe/oai?verb=Identify) |
| `mdpi` | `mdpi` | `oai.mdpi.com`（长稿，未复核） | 未核 | 未核 | 未核 | 未核 | 未核 | P1 · W3 | 长稿名录 |
| `numdam` | `centre_mersenne_numdam` | `https://www.numdam.org/oai/` | `oai_dc`（另有 `eudml-article2`） | day | no | 未核 | robots Crawl-delay 2；`HTTPS_CONTINUATION` | P1 · W3 | [Identify](https://www.numdam.org/oai/?verb=Identify) |
| `drops` | `lipics_drops` | `https://drops.dagstuhl.de/oai` | 未核 | 未核 | transient | 未核 | robots 禁 `/api/*`、`/metadata/*/*`，OAI 路径未禁 | P1 · W3 | [Identify](https://drops.dagstuhl.de/oai?verb=Identify) |
| `escholarship_cogsci` | `cogsci_proceedings` | eScholarship OAI，`set=cognitivesciencesociety`（长稿） | 未核 | 未核 | 未核 | token 24 小时（长稿） | 未核 | P1 · W3 | 长稿，未复核 |
| `iacr` | `iacr_eprint` | `https://eprint.iacr.org/oai` | `oai_dc`（唯一） | second | persistent | 未核 | robots 已放宽为只禁 PDF 等；⚑ROBOTS 维持至评审，其间只 on_demand | metadata-only（P1）· W3 | [Identify](https://eprint.iacr.org/oai?verb=Identify) |
| `econstor` | `econstor` | `https://www.econstor.eu/oai/request`（DSpace ≤6 旧路径） | `dim` 或 `mods`（待 fixture 定） | second | transient | DSpace 默认 100（未核） | robots 只禁检索浏览页；元数据 CC0（Identify） | P1 · W3 | [Identify](https://www.econstor.eu/oai/request?verb=Identify) |
| `doaj_article` | `doaj` | `https://doaj.org/oai.article`（期刊 `/oai`） | `oai_doaj` | 未核 | 删除头自 2024-11（未核） | 未核 | 全路由 2 req/s；非付费用户更新滞后最长 30 天 | P1 · W3 | [DOAJ OAI](https://doaj.org/docs/oai-pmh/) |
| `zenodo` | `zenodo` | `https://zenodo.org/oai2d` | `oai_datacite` | second | no | 约 2 分钟、50 条/页；422 经 `status_overrides` 归 `cursor_expired` | OAI 30/min、`X-RateLimit-*`；`/api` 被 robots 禁（Crawl-delay 10），`/oai2d` 允许 | P2 · W4（只按 community set） | [开发者文档](https://developers.zenodo.org/) |
| `hal` | `hal` | `https://api.archives-ouvertes.fr/oai/hal/` | 未核 | 未核 | 未核 | 未核 | robots 禁 `/oai/` → 书面确认前不启用；OAI 页写"不得商用" | P2 · W4（受阻） | [HAL OAI](https://api.archives-ouvertes.fr/docs/oai) |
| `psycharchives` | `psycharchives` | `https://www.psycharchives.org/oai/request` | 未核 | second | transient | 未核 | Crawl-delay 2（长稿） | P2 · W4 | [Identify](https://www.psycharchives.org/oai/request?verb=Identify) |
| `eudml` | `eudml` | `https://eudml.org/oai/OAIHandler` | — | — | — | — | Identify 与 robots 均 403 → 不启用，⚑RECHECK | P2 · W4（受阻；替补 `numdam` 的 `eudml-article2`） | [Identify](https://eudml.org/oai/OAIHandler?verb=Identify) |
| `episciences` | `episciences` | 未核 | — | — | — | — | 未核 | 登记 · CL0，按需补卡 | 长稿 ⚠ |

表中每个"未核"项在实例 PR 时由 Identify 实测补齐；`token_ttl_s` 实测不到的，按"每页取回后立即续取"执行，并在 fixture 中录一次过期响应。

## 4 族一致性套件

在契约通用测试（见 [conformance-and-testing](../conformance-and-testing.md)）之外，本族连接器与每个实例还须通过下列族测试；套件按"实例 × fixture"参数化，新增实例不写新测试。

| rule_id | 断言 | 必备 fixture |
|---|---|---|
| `FS-OAI-01` 信封同构 | 全部实例的信封解析共用一套代码，6 个错误码映射如 §2 | 每实例：Identify、一页 ListRecords、`noRecordsMatch` |
| `FS-OAI-02` token 过期重启 | 每页注入 `badResumptionToken`（InvenioRDM 为 422）：从窗口起点重启 ≤2 次，并集等于真值，游标未越过末页 | 带 token 的中间页、过期响应 |
| `FS-OAI-03` 安全提交点 | `ordered_by_datestamp=false` 时只有末页 `next_cursor` 非空；为 `true` 的实例附乱序反例并通过契约游标属性测试 | 末页（空 token 元素）、乱序反例 |
| `FS-OAI-04` 粒度 | `from/until` 格式与实例 `granularity` 一致，day 实例不发时间部分 | 各粒度一页 |
| `FS-OAI-05` 删除 | persistent：删除头 → tombstone；transient/no：对账产出在场集合，只在连续两次完整对账缺席后出 tombstone；不完整对账不出墓碑 | 删除头、对账两轮（一轮被截断） |
| `FS-OAI-06` until 固定 | `responseDate` 滞后或超前 >1 小时时改用 ctx.now 并计 `oai_stale_response_date`；游标不回退 | arXiv Identify（带 CDN `age` 头） |
| `FS-OAI-07` 流控 | 503 + Retry-After 与 429 → `rate_limited`；200 上的 retry-after 不触发退避 | 503、Zenodo 200 响应头 |
| `FS-OAI-08` 续页主机 | 续页 URL 由 `base_url` 生成，不跟随 Identify 声明的 baseURL | Numdam Identify |
| `FS-OAI-09` XML 安全 | XXE、实体膨胀、超深嵌套的样本判 `parse`，不展开 | 合成恶意样本 |
| `FS-OAI-10` 结构基线 | Identify 四元组与格式集合和实例文件一致，否则结构探针失败 | Identify、ListMetadataFormats |
| `FS-OAI-11` 伪成功 | 声明了 `fake_success` 的实例（arXiv "Rate exceeded."）归 `rate_limited`，不当空页 | 合成文本体（上游样本未核） |

fixture 按长稿 §15.1 四类录制，只经 staging 网关；元数据 CC0 的实例（arXiv、IACR、EconStor）摘要可原样入库，其余换等长合成文本。

## 5 连接器清单总表

| connector_id | 服务来源数 | 最高优先级 | 波次 | exec_side | impl | 代码量级 | v1 复用 | 前置依赖 | 当前 → 目标 CL |
|---|---:|---|---|---|---|---|---|---|---|
| [`oai_pmh`](#oai_pmh) | 15 | v2-P0 | W0 骨架 / W1 实例 | platform | `instance`（引擎为族核心代码） | 族核心 2 人日（粗估） | `adapters/_oai.py` 227 行、`test_oai_envelope.py` | 契约 SDK（W0） | — → CL3（P0 实例 V1 出口；其余按波次） |
| [`arxiv_oai`](#arxiv_oai) | 1 | v2-P0 | W0 | platform | `mapper` | 1.5 人日（粗估） | v1 `arxiv`（925 行，fixture 11） | 族引擎骨架 | — → CL3（V1 出口） |
| [`aaai_ojs_oai`](#aaai_ojs_oai) | 1 | v2-P0 | W2（桥接类，按实施计划；可随引擎提前） | platform | `instance` | 0.5 人日（粗估） | v1 `aaai_ojs`（1152 行，fixture 12） | 族引擎 | — → CL3（V1 出口） |

人日为第一阶段清单粗估，未与 v2-drafts 任务卡核对；零代码实例另按 SOP B（≤30 分钟/实例）计。长稿任务卡 V1-T6 把 OAI 族引擎与 P0 新写连接器合并计 22 点，AC-V1.22 用 arXiv OAI 做 7 日增量回放。

## 6 连接器卡片

### oai_pmh

**1 身份**：`connector_id=oai_pmh`；族 `oai_pmh`；`contract_version=1`；`connector_version=0.1.0`（草案）；`impl=instance`（实例零代码，引擎本身是族核心代码）；`lifecycle=active`；CL 当前 —，目标 CL3（P0 实例在 V1 出口，P1 随 V3、V5 两批，P2 按需 ≥CL2；同实施计划）；owner、backup_owner 待指派（P0 两人）；服务来源 15 个（§3 表中除 `arxiv`、`aaai_ojs` 外各行）；venue 范围：各实例整库或 set；波次 W0 建引擎骨架（随 `arxiv_oai`），W1 起按实例优先级接入。

**2 通道与操作**：

| Operation | metadata | latest | fulltext | 说明 |
|---|---|---|---|---|
| `enumerate` | ✓ | — | — | 回填窗口 + 在场对账（`EnumerateInput.mode=reconcile`） |
| `increment` | ✓ | ✓ | — | 按 WatchKey 或实例 set 的日常增量 |
| `lookup` | ✓ | — | — | `GetRecord` 按需单篇，只对声明了 identifier 规则的实例 |
| `search` | — | — | — | 不声明；OAI 无关键词检索 |
| `snapshot_import` | — | — | — | 归 `bulk_snapshot` |
| `locate_fulltext` | — | — | ✓ | 只产 `oa_link`，见第 9 项 |
| `probe` | ✓ | ✓ | — | Identify、格式、set、robots |

exec_side 全部 `platform`。

**3 上游接口事实**：协议 OAI-PMH 2.0，6 个 verb，`from/until` 按实例粒度，`resumptionToken` 分页，删除语义由 Identify `deletedRecord` 声明；逐实例事实见 §3 表。仓储软件族默认：DSpace 7+ 为 `/server/oai/request`、默认每页 100 [https://raw.githubusercontent.com/DSpace/DSpace/main/dspace/config/crosswalks/oai/xoai.xml, 2026-09-30]，但 EconStor 仍用旧路径 `/oai/request`；InvenioRDM 为 `/oai2d`，token 默认 1 分钟、过期 422、不维护删除信息、建议 `ListIdentifiers` 对账 [https://inveniordm.docs.cern.ch/reference/oai_pmh/, 2026-09-30]；OJS 为各刊 `/oai`，默认 `oai_max_records = 100` [https://raw.githubusercontent.com/pkp/ojs/main/config.TEMPLATE.inc.php, 2026-09-30]；EPrints `/cgi/oai2`（长稿，未核）。认证：本族全部无认证；DOAJ 付费高级用户带 `api_key` 可即时更新，平台不用。bulk：无（快照归 `bulk_snapshot`）。

**4 请求声明**：6 个 `endpoint_id` 见 §3；`request_class` 默认 `oai`，同一上游只声明一类，令牌桶五元组 `(source, host, oai, 部署身份, 出口 IP)`；`rate` 取文档值（PMC 3 rps、Zenodo 30/min）或保守默认 ≥1 s、并发 1，robots `Crawl-delay` 由网关叠加取严；`hosts_touched` 由实例生成；`budget`：无美元成本，按请求数计入 `planned_daily`，W1 实测后填；`Expectation` 见 §3。续页请求标记为同一任务的连续请求，调度器不得把它排到慢队列之后（token 短寿命实例）。

**5 游标与增量**：`cursor.kind = oai_datestamp{field, value, granularity, overlap, until_fixed, set, metadata_prefix}`（契约字段）；`overlap`：day 实例 2 天（第一阶段调研建议）；second 实例 1 天（调研多数建议；另一份为 1 小时，两说待核，取保守值）；长稿 arXiv 为 1 天，见 `arxiv_oai` 已知坑；`ordered = false`（默认）；`bounds`：`from` 含、`until` 含（OAI 规范）；`lag_bound`：未核（DOAJ 最长 30 天）；`late_path = none`（datestamp 是最后修改时间，迟到修改会在下一窗口出现；DOAJ 另见未决）；`window_max`：回填按月，单窗口在 token 寿命或 UTC 日界内取不完时二分。重启语义：token 过期 → `cursor_expired` → 从窗口起点重启 ≤2 次 → 超次 `stopped` 并告警"切小窗口"。删除：persistent 消费删除头；transient/no 按 `reconcile` 策略。撤稿与更正不从 OAI 推断（除 arXiv 的版本注释，见其卡片）。完成后推进：整段列表完成才推进到 `until`。`migrate_cursor`：v1 `DateCursor` → 重置 + 回填 14 天（设计值）。

**6 映射**：引擎自带 `oai_dc` mapper（`mapper_id=oai_dc`），实例可换专用 mapper（`arXivRaw`、`pmc_fm`、`oai_datacite`、`dim`）。`source_key` = OAI identifier；标识符：`dc:identifier` 中的 DOI → `doi`（粒度查注册表 `doi_family`），URL → `landing_url`，仓储 handle（如 `10419/<n>`）→ `handle`；Version：仓储类默认 `version_claim.stage = unknown`，由实例 mapper 依 `dc:type` 或 `oaire:version` 给出，带 `basis`；许可：`dc:rights` 原串 + `license_alias` 归一，缺失即 `unknown`；摘要权利与共享字段一律由共享 `classify_rights()` 计算，mapper 不直接给出。元数据库级许可（EconStor、IACR、arXiv 为 CC0，zbMATH 为 CC BY-SA）写在 SourceSpec，不在 mapper 里硬编码。

**7 SCD**：可下推谓词：`set`（native，实例有 set 时）、`datestamp ≥ from`（native，按粒度）、`datestamp ≤ until`（native）；关键词、作者、标题：不支持（不做 emulated 检索）；排序键：无（不保证有序）；分页上限：以 token 为准，无 offset；批量上限：`GetRecord` 1 条/请求；成本模型：请求数 × 实例最小间隔，无美元成本。

**8 合规**：策略输入：文档化 API = OAI 端点（是）；bulk = 无；robots 逐主机（`hal` 的 `/oai/` 被禁 → deny，书面确认前不启用；`eudml` Identify 403 按契约不明 403 从严归 `challenge`，零自动化）；ToS：`hal` 不得商用、`zbmath_open` 条款授权措辞为"develop and test"（待确认）；TDM/AI 保留：本族实例未见（未逐一核 TDMRep）。模式上限：`enumerate/increment` = background，`lookup` = on_demand，`locate_fulltext` = link_only（oa_link），`search` = deny（不声明）；⚑ROBOTS 未解除的 `iacr_eprint` 只到 on_demand，不做后台增量（HC-31）。闸门：`iacr_eprint` ⚑ROBOTS、`zbmath_open` ⚑SA ⚑COMM（MSC 码表）、`hal` ⚑ROBOTS（建议补 ⚑COMM，待拍板）。商用门控：`platform.commercial=true` 时 `hal` 与 MSC 码表停用（D-045）。书面确认：HAL（robots 与商用两点）、zbMATH（生产性收割与共享层再分发）、IACR（⚑ROBOTS 降闸须按 D-049 评审）。

**9 全文**：`locate_fulltext` 只产 `FulltextOption{kind=oa_link, url, version_claim, license, basis}`，URL 取记录中的 OA 链接（DSpace bitstream、OJS galley、PMC 文章页）；许可白名单外（非 CC、未知）只外链；本族不产 `FulltextRecipe`，没有用户侧通道。

**10 测试**：四类 fixture 按 §4；契约测试 CT-01…CT-12 全过；黄金 NormRecord 覆盖 `doi`、`handle`、`landing_url` 三种标识符方案、CC0 与未知许可、tombstone；属性测试：乱序页、每页边界崩溃、每页 token 过期（`FS-OAI-02/03`）。

**11 探针与替补**：`robots`（每实例主机，日）；`structure`（Identify 四元组 + 格式集合 + set 列表摘要，周）；`count`（每实例日新增与 7 日均值比，骤降 → `empty_body/count_drop`）；`deprecation`（实例 base URL 3xx/404，日）；`tos_hash`（有条款页的实例：HAL、zbMATH）。降级：结构探针失败冻结 CL 晋级并告警；robots 收紧立即降级；5xx 连续 → 熔断。替补：各实例的 Crossref/DataCite 委托通道（Numdam 10.5802、TE 10.3982、DROPS DataCite 10.4230）、OpenAlex、Europe PMC（PMC）。

**12 运维**：新鲜度：P0 实例日更；SLO：每实例日增量任务成功率 ≥99%（设计值，未核）；告警：token 重启超次、`oai_stale_response_date`、对账连续 2 次不完整、实例 Identify 变化；runbook：切小窗口、token 过期、端点迁移（DSpace 6→7 路径）、证书过期（QE）；`review_every`：P0 月看健康、季复核卡片，P1 季，P2 半年；`points`：instance 0.1/实例（数值未核）。

**13 已知坑与待决**：①删除语义与长稿不同（DROPS transient；PMC、zbMATH、Numdam、TE、Zenodo 为 no，本轮新记）；②QE 证书过期；③DSpace 路径分两套；④DOAJ 最长滞后 30 天；⑤Zenodo 只按 community set；⑥`presence` 与在场表见未决事项。

### arxiv_oai

**1 身份**：`connector_id=arxiv_oai`；族 `oai_pmh`；`contract_version=1`；`connector_version=0.1.0`；`impl=mapper`（引擎实例 + `arXivRaw` 专用 mapper，上调理由见 §13）；`lifecycle=active`；CL 当前 —，目标 CL3（V1 出口）；owner、backup_owner 待指派；服务 `arxiv`；venue 范围：全部类目，set 由 WatchKey 编译（兴趣面大时退到 archive 级）；波次 W0（三个参考连接器之一）；v1 来历 `arxiv` adapter，去向"移植为本族实例 + 专用 mapper"，W0 直接移植，不经桥接运行（若 W0 推迟，按 v1_bridge 过渡条款短期桥接，V2 出口前完成）。

**2 通道与操作**：`enumerate`（metadata，回填）、`increment`（metadata + latest，日更）、`lookup`（`GetRecord`，on_demand）、`locate_fulltext`（oa_link）、`probe`；不声明 `search`、`snapshot_import`。exec_side `platform`。

**3 上游接口事实**：
- OAI-PMH base `https://oaipmh.arxiv.org/oai`，2025-03 重写，旧 `export.arxiv.org/oai2` 停用；格式 `oai_dc`、`arXiv`、`arXivRaw`；set 形如 `cs:cs:AI`、`physics:hep-th`、`physics` [https://info.arxiv.org/help/oa/index.html, 2026-09-30]。
- Identify：`earliestDatestamp=2005-09-16`、`deletedRecord=persistent`、`granularity=YYYY-MM-DD`；响应带 CDN `age: 1031121`，`responseDate` 为 2026-09-17 [https://oaipmh.arxiv.org/oai?verb=Identify, 2026-09-30]。
- resumptionToken 自 2025-03 起不再给总数与 cursor，按日过期；`from` 设为上次收割日、不带 `until`；datestamp 为最后修改时间；公告约为美东周日至周四 22:30 [https://info.arxiv.org/help/oa/index.html, 2026-09-30]。
- 限速：legacy API（含 OAI）每 3 秒至多 1 次、单连接，按"你控制的全部机器"合计；元数据 CC0 1.0 [https://info.arxiv.org/help/api/tou.html, 2026-09-30]；实测无限速响应头。
- robots：`oaipmh.arxiv.org/robots.txt` 404（RFC 9309 视为无限制）；`export.arxiv.org` `Disallow: /`；`arxiv.org` `Disallow: /api`、Crawl-delay 15 [https://export.arxiv.org/robots.txt, https://arxiv.org/robots.txt, https://oaipmh.arxiv.org/robots.txt, 2026-09-30]。
- `arXivRaw` 实测带 `<license>`、`<categories>`、逐版本 `<version>`（日期、大小、`source_type`），header `setSpec` 如 `q-fin:q-fin:PM` [https://oaipmh.arxiv.org/oai?verb=GetRecord&identifier=oai:arXiv.org:2401.00001&metadataPrefix=arXivRaw, 2026-09-30]。
- dataPolicy："Full-content harvesting not permitted (except by special arrangement)"（Identify）；S3 bulk 为 requester-pays 全文 [https://info.arxiv.org/help/bulk_data_s3.html, 2026-09-30]，不用。
- 429 与伪 200 "Rate exceeded."：长稿记录，官方文档未载，未核。DataCite DOI 10.48550：长稿，未复核。

**4 请求声明**：`endpoint_id`：`arxiv.oai_list_records`、`arxiv.oai_get_record`、`arxiv.oai_identify`、`arxiv.oai_list_sets`、`arxiv.oai_list_metadata_formats`；全部 `request_class = oai`（平台只用 OAI 这一种 legacy 接口，一类即一个桶）；`budget{account: arxiv.oai, unit: request, ceiling: {min_interval_s: 3}, planned_daily: W0 实测后填}`（无美元成本），并发 1，且跨出口 IP 合计（HC-06）——契约五元组含出口 IP 维，本源须折叠，列入未决；`hosts_touched = allowed_hosts = [oaipmh.arxiv.org]`；`Expectation{content_types:[text/xml], root: OAI-PMH, min_bytes: 200, empty: error, fake_success: [("Rate exceeded.", rate_limited)], legit_status:[200]}`；`personal_params`：无。

**5 游标与增量**：`oai_datestamp`，day；`overlap = 2 天`（日粒度 + 美东/UTC 跨日；长稿为 1 天）；`ordered = false`；`bounds`：`from` 含，请求不带 `until`（`send_until=false`），运行的 `until` 取 ctx.now 的 UTC 日（`RESPONSE_DATE_UNTRUSTED`）；`lag_bound`：公告（约 22:30 ET）后可取的滞后未核；`late_path = none`；`window_max`：增量 = 单个窗口；回填按月，单窗口须在同一 UTC 日内取完，否则二分。重启：token 按日失效，过期从原 `from` 重跑，不做断点续传，≤2 次。删除：persistent，删除头 → tombstone。撤回：arXiv 以新版本加注释表达，mapper 依最新版本注释给 `status_claims.withdrawn`（启发式，须 fixture）。推进：WatchKey 下全部 set 的整段列表完成后推进到 `until`。`migrate_cursor`：v1 按月虚拟桶 → 重置 + 回填 14 天（设计值）。

**6 映射**：`mapper_id = arxiv_raw`，`mapper_version = 1`。标识符：`arxiv:<id>`（作品级，不带版本）、`arxiv_version:<id>v<n>`（版本级）；`<doi>` 与 `<journal-ref>` → 关系声明"正式版"（`basis` 指向字段路径），不当本条 DOI；DataCite DOI 10.48550 未复核前不输出。Version：`version_claim{stage: preprint, seq: n, basis: /arXivRaw/version[@version]}`。日期：v1 日期 = 首次提交，datestamp 只作游标，不当发布日。类目：`<categories>` → 学科声明，主类目取第一项。许可：`<license>` URL 原串 + `license_alias`（CC BY、BY-SA、BY-NC-SA、CC0、arXiv 非独占分发许可）；缺失 → `unknown`。摘要权利：元数据 CC0（ToU），由 `classify_rights()` 据 SourceSpec 计算。`identifiers_emitted = [arxiv, arxiv_version]`。

**7 SCD**：`set`（native）、`datestamp ≥ from`（native，日）；不声明 `search`（查询 API 不入平台通道）；排序：无；分页：token，无总数；批量：`GetRecord` 1 条；成本：每请求 ≥3 s、并发 1，全平台共享。

**8 合规**：文档化 API：OAI（是）；bulk：S3（全文，不用）；robots：OAI 主机无限制，查询 API 主机禁止 → 平台侧不用；ToS：3 s 单连接、禁止规避、不得暗示背书、须致谢；TDM/AI：逐篇许可。模式上限：`enumerate/increment` = background，`lookup` = on_demand，`locate_fulltext` = link_only，`search` = deny。闸门：无。商用：元数据 CC0，不受限。书面确认：无（OAI）；若将来要用查询 API 或全文收割，须 arXiv 书面安排（dataPolicy）。

**9 全文**：`FulltextOption{kind: oa_link, url: https://arxiv.org/abs/<id>v<n>, version_claim: preprint vN, license, basis}`；非 CC 许可只外链（[03](../../03-sources-and-corpus-pipeline.md#语料流水线与-enrich)）。CC 许可 e-print 能否经共享 OA 缓存单篇取回，与 dataPolicy 冲突，列入未决；本连接器不请求 `/pdf/`、`/e-print/`、`/src/`。

**10 测试**：fixture：Identify（含 CDN 头）、`ListRecords arXivRaw` 首页、带 token 中间页、末页、删除头、`noRecordsMatch`（周末空窗）、token 过期、合成的伪 200 文本体；黄金 NormRecord：CC BY 单版本、非独占许可多版本（v1–v3）、带 `journal-ref` 与 DOI、撤回注释、`physics:` 前缀 set、删除 tombstone；契约与族套件全过；AC-V1.22 的 7 日增量回放（标识符召回 100%、重放后新增 0）。

**11 探针与替补**：`robots`（三个主机，日；查询 API 主机若放宽只提"待评审"，不自动启用）；`structure`（Identify 四元组、set 摘要、token 形态是否恢复 cursor，周）；`canary_query`（公告日新记录数，按日历：周日至周四、节假日表，零新增即告警）；`deprecation`（OAI 文档页哈希，周）。降级：挑战或连续 5xx → 冷却与熔断，新 arXiv 条目由 OpenAlex 快照（`updated_date` 分区，滞后长；`openalex_api` 不做增量）与 Crossref 中带 arXiv 关系的记录事后补齐；DataCite 10.48550 未核，暂不作替补。

**12 运维**：新鲜度：OAI 可取后 ≤2 小时进 FeedInbox（[03](../../03-sources-and-corpus-pipeline.md#语料流水线与-enrich)）；SLO：公告日增量成功率 ≥99%（设计值）；告警：公告日零新增、游标滞后 >36 小时、重启超次、`oai` 桶排队 >1 小时；runbook：token 过期切小窗口、伪 200 退避、CDN 陈旧、类目 set 改名；`review_every`：月看健康、季复核卡片；`points`：mapper 1（未核）。

**13 已知坑与待决**：①与长稿不同（第一阶段调研实测，2026-09-30）：`export.arxiv.org` robots 全禁、`arxiv.org` 禁 `/api`，查询 API 平台侧作废；token 按日过期且无 cursor；Identify 被 CDN 长缓存；②格式由长稿"`arXiv`，需要时 `arXivRaw`"改为只拉 `arXivRaw`（请求量减半）；③重叠由 1 天改 2 天；④429/伪 200 未核，fixture 只能合成；⑤出口 IP 维折叠须网关支持；⑥CC e-print 共享缓存与 dataPolicy 冲突待拍板；⑦`impl` 上调为 `mapper`：版本史、逐篇许可与类目超出 `oai_dc` 映射。

### aaai_ojs_oai

**1 身份**：`connector_id=aaai_ojs_oai`；族 `oai_pmh`；`contract_version=1`；`connector_version=0.1.0`；`impl=instance`（OJS 默认实例 + 引擎 `oai_dc` mapper）；`lifecycle=active`；CL 当前 —，目标 CL3（V1 出口，指移植后的实例；桥接形态 shadow 等价后转 CLX，见本文 §1）；owner、backup_owner 待指派；服务 `aaai_ojs`；venue 范围：同一 OJS 实例上的 AAAI、AIES、ICWSM、ICAPS、HCOMP、AIIDE、SoCS 等 9 个会议或刊，每个一个 `OaiInstance`；波次 W2（实施计划）；v1 来历 `aaai_ojs` adapter，去向"降为族实例配置"，`quirks.volume_map` 转为 VenueSpec 的 `editions.explicit`（长稿 §14.1）。

**2 通道与操作**：`enumerate`（metadata，按届回填）、`increment`（metadata + latest）、`locate_fulltext`（外链）、`probe`；`lookup` 不声明（DOI 元数据走 `crossref_delegated` 10.1609）；exec_side `platform`。

**3 上游接口事实**：每会议一个端点 `https://ojs.aaai.org/index.php/<CONF>/oai`；AAAI 端点 earliestDatestamp 2020-06-02T17:44:16Z、`deletedRecord=persistent`、秒粒度、OJS 3.3.0.22、支持 gzip/deflate；ICWSM 端点 earliest 2021-01-29、persistent；格式 `oai_dc, jats, marcxml, oai_marc, rfc1807`；set 按期刊与栏目（如 `AAAI:2023-11`），逐年变化 [https://ojs.aaai.org/index.php/AAAI/oai?verb=Identify, https://ojs.aaai.org/index.php/AAAI/oai?verb=ListSets, 2026-09-30]。限速未文档；robots 只 `Disallow: /cache/` [https://ojs.aaai.org/robots.txt, 2026-09-30]。每页 100（长稿，与 OJS 默认一致）。其余 7 个端点未逐一核。许可 © AAAI（非 CC）。AAAI-27 起在 OpenReview 评审（第一阶段调研）。

**4 请求声明**：4 个端点 `aaai_ojs.oai_list_records`、`.oai_identify`、`.oai_list_sets`、`.oai_list_metadata_formats`（9 个实例共用；persistent 不需 `oai_list_identifiers`；不声明 `lookup`）；`request_class = oai`；`budget{account: aaai_ojs.oai, unit: request, ceiling: {min_interval_s: 2}}`，并发 1，按主机（v1 为 30/分、并发 1）；`hosts_touched = [ojs.aaai.org]`；`Expectation` 用族默认；`budget` $0。

**5 游标与增量**：`oai_datestamp`，second；`overlap = 1 天`（第一阶段调研建议）；`ordered = false`；`send_until`：回填带、增量不带；`late_path = none`；`window_max`：按届或按月。token 寿命未核，按族规则即取即续、过期重启 ≤2 次。删除：persistent → tombstone，可同步撤稿删除。推进：整段完成推进到 `until`。`migrate_cursor`：v1 按卷分区缓存 → 重置 + 当届回填。

**6 映射**：引擎 `oai_dc` mapper；标识符：`dc:identifier` 中的 DOI（10.1609）与文章页 URL；venue 与届次由 VenueSpec `editions.explicit` 把 set 或卷期映射到届；Version：`vor`（会议论文集正式版，`basis` = 来源性质）；许可：`dc:rights` 原串（© AAAI）→ 非开放；摘要权利由 `classify_rights()` 按 publisher copyright 计算。`jats` 格式可能带摘要与机构（未核），V1 录 fixture 后评估是否换 mapper。

**7 SCD**：`set`（native，逐年变化，不硬编码）、`datestamp`（native，秒）；无检索、无排序；分页 token；成本按请求数。

**8 合规**：文档化协议通道；robots 允许；ToS 未核；无 TDMRep 证据（未核）。模式上限：`enumerate/increment` = background，`locate_fulltext` = link_only。闸门：无。商用：元数据可用，全文只外链。书面确认：无。

**9 全文**：`FulltextOption{kind: open_in_tab 或 oa_link}` 指向文章页；v1 把 `/view/` 换成 `/download/` 的直链规则保留为外链形态，平台不取 PDF（非 CC）。

**10 测试**：v1 fixture 12 个做回归对拍；新录 Identify、ListMetadataFormats、ListSets、带 token 的 ListRecords、删除头；黄金 NormRecord：主会论文、IAAI 栏目、删除 tombstone；族套件全过；与 Crossref 10.1609 的合并在 identify 黄金集中覆盖。

**11 探针与替补**：`structure`（Identify 的 OJS 版本号，升级到 3.4/3.5 可能改 set 与 jats 输出；earliestDatestamp；各端点可达性）；`count`（会期前后按届设期望）；`robots`。替补：Crossref 10.1609（摘要 100%，长稿）。

**12 运维**：新鲜度：论文集按届批量上线，日增量即可；SLO：会期窗口内上线后 24 小时入库（设计值）；告警：端点 404、OJS 升级；runbook：新增会议端点按 SOP B；`review_every`：季；`points`：instance 0.1（未核）。

**13 已知坑与待决**：①只核了 AAAI、ICWSM 两个端点，其余 7 个待 SOP B 逐一 Identify；②set 名是栏目 ID，逐年变化，靠 VenueSpec 映射；③REST API 匿名 403，不作健康信号（v1 经验）；④长稿 §14.1 写去向为 `platform_family/ojs` 实例，本文按第一阶段清单移入本族（收割在本族，OJS 默认路径由平台族提供）。

## 7 本族风险与坑

- **删除误判**（对账截断、上游临时缺条）→ 只认完整对账、连续两次缺席，墓碑只置 `deleted_upstream`。
- **短寿命 token 排队过期**（Zenodo、InvenioRDM）→ 续页即取、按实例独立桶、超次切窗。
- **条款漂移**：HAL、zbMATH、IACR 只降不升，放宽类进评审队列。

## 怎么验收

- 族套件 `FS-OAI-01–11` 与契约通用测试在离线 CI 全过（CL1）；每个 P0 实例四类 fixture 与黄金 NormRecord 齐全。
- `arxiv_oai` 7 日增量回放：标识符召回 100%、manifestation 重复 0、重放后新增 0（AC-V1.22）；token 过期注入下并集不变。
- staging 经网关真实运行 P0 实例 ≥14 天：零 robots 违例、零挑战、零未声明主机；arXiv 公告日 OAI 可取后 ≤2 小时进 FeedInbox。
- transient/no 实例完成至少两轮完整对账，误墓碑为 0（人工抽检）。

## 未决事项

- `RawRecord.kind = presence` 与在场表（05 `ops` 域）是本族补充提案，须契约与 05 确认；未确认前以 ingestor 旁路表实现。
- 网关只在 429/503 上按 `Retry-After` 退避（Zenodo 200 也带该头）：本族对网关的要求，待契约或网关设计确认。
- `until` 取值细化：契约 §6 写 `oai_datestamp` 推进到 `until`（取 `responseDate`）；本族加 `fix_until()`（CDN 缓存或偏差 >1 小时改取 ctx.now，记 `oai_stale_response_date`），须契约确认。卡片归属已与 [v1-bridge](v1-bridge.md) 对齐（该文只留桥接条款）。
- 判定者：信封错误 `badArgument` 等→`config`、`idDoesNotExist`→`gone` 由 parse 判定，契约 §7 的判定者是 lint/网关；建议 `idDoesNotExist` 走 `PageSignals.not_found`，其余待契约补 parse。InvenioRDM 的 422 本文按实例 `status_overrides`（网关）归 `cursor_expired`，与契约 §7 判定者 `parse` 须择一，W0 定（契约未决事项）。
- arXiv 令牌桶须跨出口 IP 合计：网关五元组对个别来源折叠出口 IP 维的声明方式（`budget.ceiling.scope = deployment`）待契约确认。
- CC 许可 arXiv e-print 能否单篇进共享 OA 缓存（Identify dataPolicy 写明不允许全文收割）——建议默认只外链，列入待拍板。
- 候选新实例（不在第一阶段清单，均待拍板，本批不改名录）：`ssoar`（`https://www.ssoar.info/OAIHandler/request`，transient，robots 404）可补"支持但无连接器"一行；`inspire_hep` 的 `https://inspirehep.net/api/oai2d`（`marcxml`、`oai_openaire`，no，无 `oai_dc`）作 `inspire_rest` 回填替补；IACR 的 ToSC、TCHES 两个 OJS 端点。
- IACR robots 已放宽：⚑ROBOTS 是否复评降闸，按 D-049 流程另议；HAL 建议补 ⚑COMM；zbMATH 条款措辞须 FIZ 书面确认。
- DOAJ OAI 最长滞后 30 天：DOAJ 的 latest 通道是否改由 `doaj_api` 承担，由 aggregator-api 族文档与矩阵定。

更细的材料：`git show v2-drafts:docs/plan/v2/03-sources-and-corpus-pipeline.md`（§5.3–§5.4、§7.9、§10.3、§14.1、§15.1）；逐源证据见 [支持名录](../../../../catalog/source-directory.md) 与[连接器矩阵](../../../../catalog/connector-matrix.md)。
