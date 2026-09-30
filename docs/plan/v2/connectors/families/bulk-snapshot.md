---
title: 批量快照族（bulk_snapshot）规范与连接器卡片
status: draft
owner: opus5.5-primary
updated: 2026-09-30
---

# 批量快照族：`bulk_snapshot`

本文回答：官方快照、年度或月度文件、周更数据集与 dump 怎样安全、可续、可对账地导入本地底座；族引擎在契约之上多了什么，16 个本族连接器的上游事实、游标、合规与测试要点。结论：本族统一为"发现 → manifest 闸 → 经网关流式下载并校验 → 按兴趣并集子集导入 → 逐文件计数对账 → 删除日志 → 提交"七步，游标按 release 与文件粒度断点续传；P0 六个（`openalex_snapshot`、`pmc_s3`、`zbmath_kg_dump` 可先行；`crossref_annual_file` 待传输方式拍板、`pubmed_baseline`、`europe_pmc_bulk` 待书面确认，之前停在 CL1 且只用合成 fixture），P1 七个写紧凑卡，P2 三个按需补卡；DROPS dblp 与 RePEc ReDIF 的主卡在 v1-bridge，本文给出它们移植后的本族形态。

## 要点

- 本族连接器不发 HTTP：发现请求与文件下载都经出站网关（流式模式、不进 TTL 缓存、断点续传由网关做）；bulk 主机自己的 robots 另判（`host_robots_required = True`；bulk 主机 robots 全禁即 `needs_confirmation`，见长稿 `git show v2-drafts:docs/plan/v2/08-compliance-security-privacy.md` §4.2 R6）。通用协议见 [连接器接口契约 v1](../contract.md)。
- **manifest 闸**：release 未通过版本、完整性、主机、许可、规模、结构、容量与预算七项检查（MG-1…MG-7），不下载数据文件；robots 由网关逐请求判定。
- **逐文件计数对账**：字节、校验和、记录数与上游声明一致，导入 + 过滤 + 隔离 = 解析总数；字节与校验和不一致由网关判 `integrity`（契约 §7），记录数不一致由对账停机；重下一次仍不一致即停。
- **删除日志**：只有上游删除日志或确定性整版键差集产出 tombstone，只置 `deleted_upstream`，不删 Work；撤稿走 `status_claims`。
- **兴趣并集子集导入**：按 [03 本地底座](../../03-sources-and-corpus-pipeline.md#语料流水线与-enrich) 只导入命中子集；语料只记 `interest_union_version`。
- **断点续传**：游标 `snapshot_release` 按契约记 `release_id、checksum、parts_done[]、part_offsets{}`，按块提交、按块续传；release 在运行开始时固定，上游中途换版即放弃重开，不混用两版。
- **非 HTTP 传输**（rsync、FTP、BitTorrent）与 S3 请求方付费签名不在现有网关能力内，列入待拍板；默认只用 HTTPS 通道。

## 1. 本族回答什么、适用边界

**回答**：一个来源有没有官方发布、可整包取得、许可允许的文件形态数据；有，就用本族做底座回填、增量文件应用与对账。

| 相邻族 | 分界 |
|---|---|
| `aggregator_api` | 在线 API 做 `lookup`、`search`、按需补拉；本族做整版导入。同一来源常两者并存（OpenAlex、DataCite、OpenCitations、S2、ORCID）。 |
| `crossref_delegated` | 最新论文主通道；`crossref_annual_file` 只做全史回填与迟到记录对账（见 [crossref-delegated.md](crossref-delegated.md#crossref_delegated)）。 |
| `oai_pmh` | 记录级协议收割（PMC OAI、zbMATH OAI、DOAJ OAI）；本族是文件级。ResourceSync（CiNii）属本族。 |
| `v1_bridge` | `dblp_drops_snapshot`、`repec_redif` 桥接期卡片在 [v1-bridge.md](v1-bridge.md)，移植目标是本族，形态见 §6.4。 |

**不做**：代取受限全文；对外再分发快照原文件；在快照上做关键词检索（走 04 本地索引）。PMC S3 全文只有白名单许可的进共享层（08 许可闸）。

## 2. 族专有接口

```python
# 设计伪代码 —— bulk_snapshot 族专有部分（通用协议、Step、CursorEnvelope、错误矩阵见 ../contract.md）
@dataclass(frozen=True)
class SnapshotFile:
    file_id: str                       # release 内相对路径，如 "data/works/updated_date=2026-09-01/part_000.gz"
    url: str                           # 字面 HTTPS URL，主机 ∈ allowed_hosts
    bytes: int | None
    checksum: Checksum | None          # {algo ∈ md5|sha256|etag, value}
    record_count: int | None           # 上游给出时必须对账
    role: Literal["data", "delete_log", "manifest", "readme", "license"]
    partition: str | None              # 如 updated_date、年份

@dataclass(frozen=True)
class SnapshotSpec:
    release_id: str                    # "2026-09-23"、"pubmed26"、"dblp-2026-09-01"、HF revision sha
    discovered_via: str                # 取值同 §3 的 snapshot.discover
    published_at: date | None
    files: tuple[SnapshotFile, ...]
    expected_total: int | None
    license: LicenseClaim              # 原串 + basis；与上一版的哈希比较
    supersedes: str | None
    increment_of: str | None           # 增量文件（PubMed updatefile、S2 diff）所基于的 release

class BulkSnapshot(PlatformConnector):
    host_robots_required = True
    def plan(self, task, ctx: PlanCtx) -> Generator[RequestSpec, Step, TaskOutcome]:
        if task.operation == "probe":                         # ProbeInput：只发 manifest、LIST 等发现请求
            return (yield from self._probe(task.payload.probe, ctx))
        inp: SnapshotInput = task.payload                     # snapshot_import：release_id 与 union_filter 只从这里取
        cur = task.cursor.cursor if task.cursor else None     # snapshot_release{release_id, checksum, parts_done, part_offsets}
        spec = yield from self.discover(inp.release_id, ctx)  # 小请求：manifest、DataCite DOI 列表、S3 LIST、目录清单
        if spec is None: return stopped("config", "release_not_found")
        verdict = self.manifest_gate(spec, prev=cur)          # 纯函数，§2.1；prev 为已提交游标（含 parts_done、part_offsets，可判是否整版完成）
        if verdict.noop: return completed()
        if not verdict.ok: return stopped(verdict.error_class, verdict.reason)
        for f in spec.files:
            if cur and f.file_id in cur.parts_done: continue  # 已完成文件跳过；未完成文件由 runner 按 part_offsets 续切
            step = yield stream_request(f)                    # stream=True；Range 续传由网关写，连接器不写 Range
            if step.page is None: return stop_at_last_safe_point(step)
        return completed(next_cursor=release_done(spec))    # runner 只在 ImportLedger 对账（§2.2）通过后提交此终局游标，否则 stopped/integrity
    def discover(self, release_id, ctx) -> Generator[RequestSpec, Step, SnapshotSpec | None]: ...
        # Zenodo 托管的不用 zenodo.org/api（robots 禁）
    def manifest_gate(self, spec: SnapshotSpec, prev: SnapshotReleaseCursor | None) -> GateVerdict: ...   # 纯函数，§2.1
    def subset_filter(self, union: UnionFilter) -> SubsetFilter: ...   # 纯函数，把契约 SnapshotInput.union_filter 编译为本源可判键；runner 调用后放进 ParseCtx.subset
    def parse_chunk(self, chunk: SnapshotChunk, ctx: ParseCtx) -> Page: ...
        # runner 按记录边界切块喂入；只产出命中 ctx.subset 的记录（未命中计 filtered_out）；连接器不读文件、不开网络；单条坏记录由本函数跳过并计入 PageSignals.n_quarantined，
        # 整块结构不符才抛 ParseError（runner 停在上一个已提交块）
    def reconcile(self, ledger: ImportLedger, spec: SnapshotSpec) -> ReconcileReport: ...  # §2.2；ImportLedger 由 runner/ingestor 维护，不进连接器输入
```

### 2.1 manifest 闸（`manifest_gate`，七项全过才下载数据文件）

| 项 | 检查 | 不过时 |
|---|---|---|
| MG-1 版本 | `release_id` 新于已提交版；相同且 `parts_done` 覆盖全部文件、`part_offsets` 为空才算整版已提交 | 整版已提交即 `completed`（空操作）；同版未完成则续传 |
| MG-2 完整 | 每个数据文件有 URL；上游提供字节数、校验和、记录数的，全部齐 | 闸返回不通过（`GateVerdict`），不下载；下载后的字节与校验和由网关判 `integrity`（契约 §7） |
| MG-3 主机 | 全部文件主机 ∈ `allowed_hosts` | 闸不生成请求；若仍有未声明主机的请求，由网关路由判 `config/undeclared_host`（契约 §7 的判定者） |
| MG-4 许可 | 许可声明与上一版哈希一致 | 停在门前，交策略引擎重判（可能为 `needs_confirmation`）；变严自动降级，变宽只提"待评审" |
| MG-5 规模 | 总记录数、总字节与上一版比，骤降超阈值（建议 10%，未核） | 由发现后立即运行的 `count` 探针判定 `empty_body/count_drop`，停并告警 |
| MG-6 结构 | 抽样文件头与字段集合指纹匹配 mapper 期望 | 闸不通过、结构探针告警；下载后不符由 `parse_chunk` 抛 ParseError 判 `parse` |
| MG-7 容量 | 冷存储余量、请求方付费预算足够 | 配额账本判定 `budget_exhausted`，停 |

### 2.2 逐文件计数对账与删除日志

- `ImportLedger` 每文件一行：`file_id、bytes_expected/actual、checksum_ok、records_declared、records_parsed、imported、filtered_out、quarantined、tombstones、committed_at`（本批新增，落 05 ops 域）。
- 文件级：字节与校验和一致；有声明记录数的须 `records_parsed == records_declared`；`imported + filtered_out + quarantined == records_parsed`；各块 `PageSignals.n_quarantined` 之和的隔离率超阈值（建议 0.01%，未核）即停并告警（归 `parse`）。
- release 级：各文件之和等于 `expected_total`（有则比）；对账报告进 `ops.harvest_run`，O2 可见。
- 删除：只认两类证据——上游删除日志（OpenAlex `deleted_ids.csv.gz`、PubMed `DeleteCitation`、S2 diffs 的删除文件）与确定性整版键差集（dblp key、RePEc handle：导入时产出契约 `RawRecord(kind="presence")`，由 sink 累计缺席，连续两版缺失才产出 tombstone，连接器不读上一版键集）；年度全量文件（DataCite、ORCID、Crossref）的缺失只记 `absent_in_release` 观测，不产出 tombstone。

### 2.3 兴趣并集子集导入

- `subset_filter()` 把 [03](../../03-sources-and-corpus-pipeline.md#语料流水线与-enrich) 的 InterestUnion 编译为本源可判的键：OpenAlex 用 source id、topic、作者；Crossref 年度文件用 ISSN、前缀、member；PubMed 用 ISSN 与 NLM 刊号；DataCite 用前缀与 client；dblp 用 venue key 与作者 PID；RePEc 用系列句柄。
- 小型全量源（ROR、DOAJ 期刊 CSV）整版导入。
- 细粒度键（作者、引文邻域）只来自公开种子或 ≥`k_cf` 用户共有的键（HC-30）；私有导入的题录永不作过滤键。
- 并集增长：优先在冷存储的最近一版上重扫（不重下），体量小时可用在线 API 补拉并计入预算；并集收缩不删已入库 work。

### 2.4 断点续传与游标

- `Cursor.kind = snapshot_release`，字段按契约 `{release_id, checksum, parts_done[], part_offsets{file_id: record_offset}}`：每块提交即推进未完成文件的 `part_offsets`，整文件完成后移入 `parts_done`，崩溃后从块偏移续切；增量文件序列用 `seq`（PubMed updatefile 编号），HF 数据集用 `repo_commit`。
- 文件不可变、切块确定，因此声明 `ordered_by: file_offset`（配乱序反例 fixture）后可按块提交；运行开始固定 `release_id`，校验和变化或上游换版即放弃本次、从新版重开。
- 下载中断：网关按 Range 续传，每次尝试在 FetchLog 写一行；单请求 ≤3 次尝试（契约 `transient` 默认）仍失败即停在已提交文件。

## 3. 实例与清单字段

本族多为"每源一个导入器"（`impl: mapper`，发现逻辑复杂的升 `custom_plan`）；ConnectorManifest 增加 `snapshot` 块（本批新增）：

| 字段 | 说明 |
|---|---|
| `snapshot.discover` | `manifest`、`datacite_doi`、`s3_list`、`dir_listing`、`hf_api`、`release_api`（S2、figshare）、`resourcesync` 之一，附字面 URL |
| `snapshot.cadence` / `expected_next` | 发布节奏与下次预期日期（探针据此判"过期未发"） |
| `snapshot.release_id_pattern` / `files_glob` | 版本号与文件名模式 |
| `snapshot.checksum` / `record_count_source` | 校验算法；记录数来自 manifest、DataCite `sizes` 或无 |
| `snapshot.delete_log` | 删除证据类型：`file`、`key_diff`、`none` |
| `snapshot.subset_keys` / `full_import` | 子集键类型；小型源 `full_import: true` |
| `snapshot.transport` | `https`（默认）；`s3_requester_pays`、`rsync`、`ftp` 须待拍板通过 |
| `snapshot.retention` | 冷存储保留期，由 05 定 |

本族对契约的补充汇总在未决事项。

## 4. 族一致性套件

在通用契约测试 CT-01…CT-12（见 [一致性与测试](../conformance-and-testing.md)）之上：

| 编号 | 断言 |
|---|---|
| FS-BS-01 | `manifest_gate` 纯函数；MG-1…MG-7 每项各有一个失败 fixture |
| FS-BS-02 | 在任意文件、任意块边界注入崩溃，重跑后导入集合与一次跑完相同，游标不越过未提交块 |
| FS-BS-03 | 下载中断续传：模拟 Range 续传与校验和不符，归类为 `transient` 或 `integrity` |
| FS-BS-04 | 逐文件对账：记录数少一条、多一条、重复一条三种情形都被发现 |
| FS-BS-05 | 删除日志：tombstone 只置 `deleted_upstream`；年度文件缺失不产出 tombstone；键差集须连续两版 |
| FS-BS-06 | 子集过滤：同一 InterestUnion 版本两次导入结果相同；过滤键不含任何私有题录 |
| FS-BS-07 | 中途换版：第二个 release 出现时本次放弃，不混用 |
| FS-BS-08 | 许可变化：manifest 许可哈希变化即停在 MG-4 |
| FS-BS-09 | 连接器不读文件、不写 Range、不持凭证（只以 `AuthRef(deployment/*)` 引用） |
| FS-BS-10 | 预签名 URL 的签名参数不进 FetchLog 明文（只记 `params_digest`） |

fixture 用"截断样本"：manifest 全文加每个文件的前若干条记录与最后一条，附上游原始校验和；受 robots 禁止、尚未书面确认的主机只用按公开文档手写的合成 fixture，不录制。

## 5. 连接器清单总表

| connector_id | 来源 | 最高优先级 | 波次 | exec_side | 代码量级（E 粗估） | v1 复用 | 前置依赖 | 当前 / 目标 CL |
|---|---|---|---|---|---|---|---|---|
| [`openalex_snapshot`](#openalex_snapshot) | `openalex` | v2-P0 | W2 | platform | 2 人日 | — | 冷存储容量（05） | 未建 / CL3（V1） |
| [`crossref_annual_file`](#crossref_annual_file) | `crossref` | v2-P0 | W2 | platform | 2 | — | 传输方式待拍板 1（S3 请求方付费） | 未建 / CL1（待拍板 1 通过后 CL3） |
| [`pmc_s3`](#pmc_s3) | `pmc` | v2-P0 | W2 | platform | 2 | — | 许可闸 | 未建 / CL3（V1） |
| [`pubmed_baseline`](#pubmed_baseline) | `pubmed` | v2-P0 | W2 | platform | 2 | — | ⚑ROBOTS：NCBI 书面确认 + D-049 附表 | 未建 / CL1（确认后 CL3） |
| [`europe_pmc_bulk`](#europe_pmc_bulk) | `europe_pmc` | v2-P0 | W2 | platform | 2 | — | ⚑ROBOTS（仅 bulk）：EBI 书面确认 | 未建 / CL1（确认后 CL3） |
| [`zbmath_kg_dump`](#zbmath_kg_dump) | `zbmath_open` | v2-P0 | W2 | platform | 1.5 | — | ⚑SA ⚑COMM | 未建 / CL3（V1） |
| [`datacite_annual_file`](#datacite_annual_file) | `datacite` | v2-P1 | W3 | platform | 1.5 | — | 文件托管位置未核 | 未建 / CL3（V3） |
| [`doaj_csv`](#doaj_csv) | `doaj` | v2-P1 | W3 | platform | 0.5 | — | — | 未建 / CL3（V3） |
| [`opencitations_dump`](#opencitations_dump) | `opencitations` | v2-P1 | W3 | platform | 1.5 | — | — | 未建 / CL3（V3） |
| [`orcid_public_data_file`](#orcid_public_data_file) | `orcid` | v2-P1 | W3 | platform | 1.5 | — | ⚑ROBOTS ⚑COMM（API 通道） | 未建 / CL3（V3） |
| [`pwc_archive_import`](#pwc_archive_import) | `pwc_archive` | v2-P1 | W3 | platform | 1 | — | ⚑SA | 未建 / CL3（V5） |
| [`ror_dump`](#ror_dump) | `ror` | v2-P1 | W3 | platform | 1 | — | — | 未建 / CL3（V3） |
| [`s2_datasets`](#s2_datasets) | `s2` | v2-P1 | W3 | platform | 2 | — | ⚑COMM；部署 key | 未建 / CL3（V3） |
| `cinii_resourcesync` | `cinii_research` | v2-P2 | W4 | platform | 2 | — | ⚑ROBOTS（仅 OpenSearch） | 按需补卡 |
| `openaire_graph_dump` | `openaire` | v2-P2 | W4 | platform | 2 | — | Zenodo 发现方式 | 按需补卡 |
| `wikidata_dump` | `wikidata` | v2-P2 | W4 | platform | 2 | — | 子集规模 | 按需补卡 |
| `dblp_drops_snapshot` | `dblp` | v2-P0（快照形态） | W2 | platform | 桥接 2 | v1 `dblp` 解析函数 | 解除 D-037 出列须新 ADR（D-050） | 主卡在 [v1-bridge.md](v1-bridge.md#dblp_drops_snapshot)；形态见 §6.4 |
| `repec_redif` | `repec` | v2-P0 | W2 | platform | 桥接 2 | v1 `repec/parse.py` | 扩 handle 映射；rsync 传输待拍板 | 主卡在 [v1-bridge.md](v1-bridge.md#repec_redif)；形态见 §6.4 |

`openalex_snapshot` 是 V1 出口条件；[实施计划](../implementation-plan.md) 保持 W2（V1 后半），V1 出口前完成子集导入。

## 6. 连接器卡片

**6.1 P0（完整 13 节）**

全部卡片共同身份项：`kind: platform_connector`、`contract_version: 1`、`connector_version: 0.1.0`（未发布）、`lifecycle: active`、当前 CL 未建、owner 与 backup_owner 待指派（P0 须两人）；`lane: harvest`，runner 盖章 `traffic_class: background_batch`。下列卡片只写不同处。

### openalex_snapshot

**1 身份**：`impl: mapper`；目标 CL3（V1 出口）；服务 `openalex`；波次 W2。

**2 通道与操作**：metadata 与 latest（季度对账）× `snapshot_import`、`probe`；`exec_side: platform`。

**3 上游接口事实**：季度公共快照，每年 1、4、7、10 月第二个周三发布；约 6.26 亿条；JSON Lines（gzip）约 745 GB，其中 works 约 615 GB，Parquet 约 770 GB；位置 `s3://openalex/data/`，匿名 `--no-sign-request`，无下载费用；按 `updated_date` 分区；works 目录自 2026-09-23 版起带 `deleted_ids.csv.gz`；旧合并实体在冻结的 `legacy-data/` [https://help.openalex.org/access/snapshot/, 2026-09-30]。付费日快照在 `openalex-snapshots` 桶，需 API key，不用。数据 CC0（长稿 §2.2.2，未复核）。下一版 2026-10-14（长稿）。各实体 manifest 含文件 URL、`content_length`、`record_count`（未核）。API `meta.count` 2026-09-30 为 326,610,013，较 2026-09-26 的 327,236,598 少约 62.7 万，原因未核 [https://api.openalex.org/works?per_page=1&select=id,publication_date, 2026-09-30]。

**4 请求声明**：`endpoint_id` `openalex.s3_manifest`（每实体一个字面 URL，如 `…/data/works/manifest`，路径未核）、`openalex.s3_object`（流式 GET 分区文件）、`openalex.s3_list`（`?list-type=2&prefix=` 只用于发现新分区与删除日志）；`request_class: bulk_object`；主机 `openalex.s3.amazonaws.com`（robots 未核，按 RFC 9309 判读）；`Expectation`：manifest `application/json`、`min_bytes` > 0；对象 `magic` 为 gzip；令牌桶 (`openalex`, S3 主机, `bulk_object`, 匿名, 出口 IP) 与 API 预算桶分开。

**5 游标与增量**：`snapshot_release{release_id=发布日期, checksum=manifest 哈希, parts_done[]}`；增量 = 新版中 `updated_date` 晚于上版截止的分区 + 删除日志；首次导入全量扫描一次后只处理新分区（分区语义以 manifest 为准，未核）；季度间的新论文由 `crossref_delegated` 与 `openalex_api` 承担。

**6 映射**：`mapper_id: openalex_work`；OpenAlex W id 只作 `work_assertion`，不作身份主键；DOI、PMID、PMCID、arXiv id 作标识符；摘要为倒排索引（法律原因不给明文），`abstract_rights` 按来源默认 `unknown`；许可字段常为空，未知即不共享；`is_retracted` → `status_claims`；`corpus` 字段（core、expansion）入观测；`version_claim` 按 `primary_location.version`（未核）给出，不确定即 `unknown`。

**7 SCD**：无在线谓词；子集键 source id、topic、作者、DOI 前缀；成本 = 冷存储与下载时间（无美元成本）。

**8 合规**：文档化 bulk 是；CC0（长稿，未复核）；TDM/AI 保留未见（未核）；上限模式 `background`；无需书面确认；与 ⚑BUDGET 无关（快照不计费）。

**9 全文**：不产出全文；`best_oa_location` 只作 OA 候选声明交给 OA 层。

**10 测试**：fixture：manifest 全文、一个分区文件截断样本、`deleted_ids.csv.gz` 样本、`legacy-data` 合并样例、结构变更（新增或删除字段，如 `host_venue` 已移除）；黄金 NormRecord：带倒排摘要、`is_retracted`、无许可；属性：FS-BS-02、FS-BS-05。

**11 探针与替补**：`deprecation`：弃用页日期 [https://help.openalex.org/api/deprecations/, 2026-09-30]；`count`：manifest 总数与 API `meta.count` 走势；`structure`：分区最新日期、字段集合；`expected_next` 过期 7 天告警。替补：`crossref_annual_file` 加 `crossref_delegated`；OpenAlex API 按美元预算补拉。

**12 运维**：新鲜度目标：发布后 ≤14 天完成子集导入（建议，未核）；告警：MG-5、MG-6、删除日志缺失；runbook：分区语义或桶路径变化、容量不足收紧 `floor`；每月看健康、每季复核卡片。

**13 已知坑与待决**：①分区是按 `updated_date` 还是按发布批次，manifest 结构未逐字核；②`deleted_ids` 只从 2026-09-23 版起有，更早的删除须靠整版差集；③`meta.count` 短期下降原因未核；④冷存储体量与保留期由 05 定。

### crossref_annual_file

**1 身份**：`impl: declarative`（映射复用 `crossref_work`，发现、闸与切块由族引擎做）；目标 CL3；服务 `crossref`；波次 W2。

**2 通道与操作**：metadata（全史回填）与 latest（迟到记录对账）× `snapshot_import`、`probe`；platform。

**3 上游接口事实**：年度公共数据文件 2026-03-17 发布，近 1.8 亿条，压缩 208 GB，JSON-lines；分发经 Academic Torrents（DOI `10.13003/nggf-vt1j`）或 AWS 请求方付费；较上年新增 1,270 万条，摘要 +15%、ORCID +20%、ROR +250%，首次包含 Retraction Watch 撤稿 [https://www.crossref.org/blog/2026-public-data-file-now-available/, 2026-09-30]。Metadata Plus 快照为付费服务（长稿，不用）。书目事实 CC0 口径，摘要保留出版方版权（长稿 C8）。

**4 请求声明**：拟用 `transport: s3_requester_pays`（HTTPS + SigV4，由网关以 `AuthRef(deployment/aws_requester_pays)` 签名，费用进美元预算，数额未核），待拍板 1 通过前不可用；桶与主机未核；BitTorrent 不用；`request_class: bulk_object`；`Expectation`：gzip `magic`、字节数与上游清单一致。

**5 游标与增量**：`snapshot_release{release_id=年份}`；每年一次；导入后对 `crossref_delegated` 各委托的 L 之外区间做 DOI 差集，补入迟到记录（该族 `late_path` 声明为 `weekly_index_backfill`，L 之外由本连接器兜底）。

**6 映射**：复用 `crossref_work` mapper（与 `crossref_delegated` 同一 `mapper_id`，保证同 DOI 两路结果一致）；子集键 ISSN、前缀、member。

**7 SCD**：无在线谓词；成本 = 请求方付费流量（未核）与冷存储。

**8 合规**：文档化 bulk 是；上限 `background`；摘要为 B 类待法务，按最严处理；无需书面确认。

**9 全文**：不产出。

**10 测试**：fixture：文件清单、截断样本（含撤稿、多许可、JATS 摘要）；契约：与 `crossref_delegated` 同 DOI 的黄金 NormRecord 字节相同；FS-BS-04。

**11 探针与替补**：`count` 按 `snapshot.expected_next`（每年 3 月前后，未核）判过期未发；`deprecation`：博客与分发页；替补：OpenAlex 快照。

**12 运维**：一年一次，导入窗口内暂停对应委托的补漏任务避免重复；每季复核卡片。

**13 已知坑与待决**：传输方式待拍板；请求方付费金额与账号归属未核；年度文件截止日与增量窗口的衔接须在 V0 实测。

### pmc_s3

**1 身份**：`impl: custom_plan`（inventory 差集与逐篇对象，超出声明式词表）；目标 CL3；服务 `pmc`；波次 W2。

**2 通道与操作**：metadata × `snapshot_import`、`increment`、`probe`；fulltext（仅许可白名单）× `locate_fulltext`（按 PMCID 给出 S3 对象位置）；platform。

**3 上游接口事实**：PMC 只允许经 Cloud Service、OAI-PMH、E-utilities、BioC、ID Converter 等官方服务自动化取内容："Systematic retrieval (or bulk retrieval) of articles through any other automated process is prohibited" [https://pmc.ncbi.nlm.nih.gov/tools/developers/, 2026-09-30]；S3 `pmc-oa-opendata`（匿名，AWS Open Data 赞助）[https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/, 2026-09-30]；约 800 万文章版本，各在 `PMC{id}.{version}/` 下，含 JATS XML、TXT、元数据 JSON（许可、`is_manuscript`、版本、`LastModifiedDate`、MD5）；每日 inventory、保留 30 天、滞后于桶状态；覆盖 OA 子集（商用与非商用许可）、Author Manuscript、Historical OCR [README https://pmc-oa-opendata.s3.amazonaws.com/README.txt, 2026-09-30]。OA Web Service 2026-08-25 下线，旧 FTP 于 2026-08-24 那周删除 [https://pmc.ncbi.nlm.nih.gov/tools/oa-service/, 2026-09-30]。README 条款：只再分发许可允许的数据，保持最新或显著声明非最新，不得用 PMC 标识或暗示背书。

**4 请求声明**：`pmc.s3_inventory`（每日 inventory manifest）、`pmc.s3_list_recent`（近期前缀直接 LIST，弥补 inventory 滞后）、`pmc.s3_object_json`、`pmc.s3_object_xml`；主机 `pmc-oa-opendata.s3.amazonaws.com`（robots 未核）；`Expectation`：JSON 元数据含 `license` 键，XML `magic` 为 `<?xml`。

**5 游标与增量**：`snapshot_release{release_id=inventory 日期}`；增量 = 相邻两份 inventory 的对象差集（新增、ETag 变化、消失）；消失的版本对象产出 tombstone（须连续两份 inventory 缺失）；键为 PMCID + 版本。

**6 映射**：`mapper_id: pmc_jats`；PMCID 版本级、PMID 与 DOI 作品级；`version_claim`：`is_manuscript=true` → `am`，其余按 JATS `article-type` 判定（预印本为 `preprint`），不确定即 `unknown`；许可来自元数据 JSON 的 `license_code`，经 `classify_rights()`，只有 CC BY、BY-SA、CC0、公有领域（NC 仅非商业部署）可进共享 OA 缓存，`license_code=TDM`（作者手稿）不进；`is_retracted` → `status_claims` [README，同 §3]。

**7 SCD**：无在线谓词；成本 = 逐篇对象数（约 800 万）与 inventory 体积。

**8 合规**：文档化 bulk 是；S3 路径不受 `pmc.ncbi.nlm.nih.gov` robots 约束，E-utilities 仍受 ⚑ROBOTS（不在本连接器）；上限 `background`；全文进共享层受许可闸与 `features.oa_shared_cache`（默认关）双重约束。

**9 全文**：平台侧只对许可白名单内的版本产出 `FulltextOption{kind: oa_link}`，basis 为元数据 JSON 的许可字段；其余只给"在出版社打开"。

**10 测试**：fixture：CC BY 与非商用许可各一份元数据 JSON、inventory 片段、对象消失样例；黄金：`am` 与 `vor` 各一；FS-BS-05、FS-BS-10。

**11 探针与替补**：`structure`：S3 前缀结构与 JSON 键集合；`count`：inventory 生成时间与对象数；`deprecation`：`/tools/developers/` 服务清单。替补：`oai_pmh` 的 PMC 实例（`pmc_fm`，3 rps，不作全量）、`pmc_bioc`（⚑ROBOTS 限制）。

**12 运维**：新鲜度目标 inventory 生成后 ≤48 小时（建议，未核）；runbook：撤回与更新须在共享层同步，否则声明"非最新"。

**13 已知坑与待决**：`impl: custom_plan` 的理由：inventory 差集加近期 LIST 超出声明式词表；inventory 滞后；删除只能对账发现；按版本存放；v1 或长稿任何沿用旧 FTP `oa_package`、`oa_file_list.csv` 的逻辑已失效。

### pubmed_baseline

**1 身份**：`impl: mapper`；目标 CL3，书面确认前停在 CL1；服务 `pubmed`；波次 W2（阻塞）。

**2 通道与操作**：metadata 与 latest × `snapshot_import`（baseline）、`increment`（updatefiles）、`probe`；platform。

**3 上游接口事实**：`https://ftp.ncbi.nlm.nih.gov/pubmed/baseline/`（年度全量）与 `/pubmed/updatefiles/`（每日，含新增、修订、删除，同日可有多个）；须先载 baseline 再按编号顺序载 updatefiles；修订与删除替换本地记录；每个文件附 MD5；DTD `pubmed_250101`；条款在 README.txt，下载即视为接受 [https://pubmed.ncbi.nlm.nih.gov/download/, 2026-09-30]。2026 baseline 为 `pubmed26n0001`–`1334`，首个 updatefile `pubmed26n1335`，2026-01-30 才发布；2027 baseline 在 `IndexingMethod` 新增 `NotIndexed`，DTD 不变 [https://www.nlm.nih.gov/rss/auto/PubMedNews.rss, 2026-09-30]。`ftp.ncbi.nlm.nih.gov/robots.txt` 为 `Disallow: /` [https://ftp.ncbi.nlm.nih.gov/robots.txt, 2026-09-30]。

**4 请求声明**：`pubmed.dir_listing`、`pubmed.baseline_file`、`pubmed.update_file`、`pubmed.md5_file`；主机 `ftp.ncbi.nlm.nih.gov`；`Expectation`：gzip `magic`，MD5 一致。

**5 游标与增量**：baseline 用 `snapshot_release{release_id=pubmed26}`；updatefiles 用 `seq`（文件编号，严格顺序，不可跳号）；年度切换（`26n` → `27n`）时编号重置，执行"新 baseline 全量对账 + 旧 update 停用"；`DeleteCitation` 产出 tombstone。

**6 映射**：`mapper_id: pubmed_xml`；PMID 作品级；摘要部分受版权（B 类），按最严；撤稿与更正来自 `CommentsCorrections` → `status_claims`；未知枚举值（如 `NotIndexed`）不得导致解析失败。

**7 SCD**：无在线谓词；子集键 ISSN、NLM 刊号。

**8 合规**：⚑ROBOTS：主机全禁，与文档化 bulk 冲突；NCBI 书面确认并登记 D-049 附表前判定为 `needs_confirmation`（R6），零请求并进 O4 队列，连 dry-run 录制也不做；确认后上限 `background`；NLM 条款要求致谢与保持最新。

**9 全文**：不产出。

**10 测试**：确认前只用按公开文档手写的合成 fixture：小 updatefile（含 `PubmedArticle`、`DeleteCitation`）、撤稿记录、`NotIndexed` 样例、README 与 `.md5`；确认后经 staging 网关重录。

**11 探针与替补**：`robots`：两个 NCBI 主机；`structure`：文件名模式、DTD 版本、新枚举值；替补：`europe_pmc_rest`（`SRC:MED`）承担后台增量。

**12 运维**：确认后新鲜度目标 updatefile 发布后 ≤24 小时（建议）；年度切换 runbook。

**13 已知坑与待决**：书面确认是 V1 排期关键路径；年度切换与发布延迟；文档页被 reCAPTCHA 拦截，漂移只能靠探针与人工复读。

### europe_pmc_bulk

**1 身份**：`impl: mapper`；目标 CL3，确认前停在 CL1；服务 `europe_pmc`；波次 W2（阻塞）。

**2 通道与操作**：metadata（OA 子集）× `snapshot_import`、`probe`；platform。

**3 上游接口事实**：OA 子集等位于 `ftp.ebi.ac.uk/pub/databases/pmc/`（长稿，未复核）；`https://ftp.ebi.ac.uk/robots.txt` 为 `User-agent: *` / `Disallow: /` [https://ftp.ebi.ac.uk/robots.txt, 2026-09-30]；频率与规模未核；开发者页称不允许以自动化方式批量下载 OA 子集以外的内容（搜索摘要，二手）。REST 通道不受此限，由 `europe_pmc_rest` 承担（只用 `FIRST_IDATE` 日窗）。

**4 请求声明**：`europe_pmc.dir_listing`、`europe_pmc.oa_file`；主机 `ftp.ebi.ac.uk`；具体文件结构未核，确认后补。

**5 游标与增量**：`snapshot_release`（按目录发布批次，未核）。

**6 映射**：文件格式未核；若为 JATS XML 则复用 `pmc_jats`，不能直接复用 `europe_pmc_rest` 的 JSON mapper；许可逐篇。

**7 SCD**：无。

**8 合规**：⚑ROBOTS（仅 bulk）：EBI 书面确认前 `needs_confirmation`（同 R6，零请求）；确认后 `background`；非 OA 全文只外链。

**9 全文**：确认后只对许可白名单内的 OA 文章产出 `oa_link`。

**10 测试**：确认前只用合成 fixture；确认后录制。

**11 探针与替补**：`robots`：`ftp.ebi.ac.uk`；替补：`europe_pmc_rest` 与 `pmc_s3`。

**12 运维**：确认前不调度；每季复核书面确认进展。

**13 已知坑与待决**：是否仍需要本连接器（`pmc_s3` 已覆盖 PMC OA 子集）待评审；可降为 P1 或登记。

### zbmath_kg_dump

**1 身份**：`impl: mapper`；目标 CL3；服务 `zbmath_open`；波次 W2。

**2 通道与操作**：metadata（全量回填）× `snapshot_import`、`probe`；日常增量由 `oai_pmh` 的 zbMATH 实例承担；platform。

**3 上游接口事实**：zbMATH Open Knowledge Graph 的 RDF 全量 dump 发布在 Zenodo（`https://doi.org/10.5281/zenodo.21497975`），"approximately twice per year"更新，另有公开 SPARQL；约 3,400 万实体、1.68 亿三元组，覆盖 1763–2026，基于 2025-12 的 API 快照构建；CC BY-SA 4.0 [https://arxiv.org/html/2609.00969, 2026-09-30]。API 条款：数据按 CC-BY-SA 使用，抽取时不得移除版权声明（2021-06 条款）。`zenodo.org/robots.txt` 禁 `/search`、`/api`，Crawl-delay 10，`/oai2d` 允许 [https://zenodo.org/robots.txt, 2026-09-30]。dump 与 OAI 的字段映射未核。

**4 请求声明**：发现走 DataCite（`api.datacite.org/dois` 查概念 DOI 的新版本，Zenodo DOI 由 DataCite 登记）或 `zenodo.org/oai2d`，不用 `zenodo.org/api`；下载 `zenodo.org/records/{id}/files/{name}`（该路径不在 robots 禁区，据前缀推断，未核），遵守 Crawl-delay 10。

**5 游标与增量**：`snapshot_release{release_id=Zenodo 版本 DOI}`；约半年一次；与 OAI 增量按 zbMATH id 合并，dump 只做全量对账（OAI `deletedRecord=no`，删除靠整版键差集，连续两版）。

**6 映射**：`mapper_id: zbmath_kg_rdf`；zbMATH id、DOI、MSC 分类；CC BY-SA → 派生数据集受 ShareAlike 约束，`commercial_ok` 按许可计算；MSC 码表另受 ⚑COMM。

**7 SCD**：无在线谓词；成本 = RDF 体积（未核）。

**8 合规**：⚑SA：派生共享须同许可；⚑COMM：商用部署前复核 MSC 码表许可；上限 `background`。

**9 全文**：不产出（zbMATH 只外链）。

**10 测试**：fixture：Zenodo 版本元数据（经 DataCite）、RDF 截断样本、与 OAI 同一记录的对照；黄金：带 MSC 的记录。

**11 探针与替补**：`count`：Zenodo 最新版本号；`robots`：`zenodo.org`；替补：`oai_pmh` zbMATH 实例、`zbmath_open_api`。

**12 运维**：每半年一次；每季复核卡片。

**13 已知坑与待决**：dump 与 OAI 字段对照未核；Zenodo 发现方式依赖 DataCite 关系字段（`IsNewVersionOf`，未核）；API 条款授权措辞为 "develop and test software applications"，对 OAI 生产收割是否足够待 FIZ 书面确认（第一阶段调研）。

**6.2 P1（紧凑卡）**

### datacite_annual_file

**1 身份 / 2 通道**：服务 `datacite`；`impl: declarative`（映射复用 `datacite_rest`）；metadata 与 latest × `snapshot_import`；platform；W3；目标 CL3。

**3 上游事实**：年度公共数据文件，CC0，2025 版 2026-01-06 生成；月度文件限会员（长稿 C41，未复核）；托管位置与校验方式未核。REST 通道（`datacite_rest`）限额见 [crossref-delegated.md §2.4](crossref-delegated.md#24-datacite-变体)。

**5 游标**：`snapshot_release{年份}`；年度缺失不产出 tombstone；年内增量交 `datacite_rest`（`query=updated:[…]`）。

**8 合规**：CC0；`background`。

**10 测试**：文件清单与截断样本；arXiv（`10.48550`）、Zenodo、LIPIcs DOI 各一条黄金记录。

**11 探针与替补**：年度发布日期；替补 `datacite_rest`。其余节：映射复用 `datacite_rest` 的 mapper。

### doaj_csv

**1 身份 / 2 通道**：服务 `doaj`；`impl: mapper`（CSV 期刊映射）；metadata（期刊白名单）× `snapshot_import`；platform；W3。

**3 上游事实**：期刊 CSV 可直接下载；全量 dump 须邮件申请、逐案批准 [https://doaj.org/docs/public-data-dump/, 2026-09-30]；API 全部路由 2 req/s [https://doaj.org/api/v4/docs, 2026-09-30]；元数据 CC0（长稿 C47）。

**5 游标**：`snapshot_release{下载日期 + sha256}`；整版导入（`full_import: true`），期刊移出列表记 `absent_in_release`。

**8 合规**：CC0；`background`；只作 OA 期刊白名单与期刊信号。

**10 测试**：CSV 截断样本、列名变化反例。

**11 探针与替补**：CSV 列集合；替补 `doaj_api`、DOAJ OAI（滞后可达 30 天）。

### opencitations_dump

**1 身份 / 2 通道**：服务 `opencitations`；`impl: mapper`；metadata（引文边）× `snapshot_import`；platform；W3。

**3 上游事实**：Meta 2026-06-27 版（CSV 8.4 GB 等，Zenodo）；Index 2026-07-28 版约 25.59 亿引用（CSV 36 GB，figshare）；无增量包；CC0 [https://download.opencitations.net/, 2026-09-30]。

**5 游标**：`snapshot_release{Index 版本}`；整版替换，只导入两端之一在语料内的边（子集键 = 已入库 DOI 与 OMID）。

**8 合规**：CC0；`background`。

**10 测试**：CSV 截断样本；与 OpenAlex 被引数不一致的样例（长稿 C46）。

**11 探针与替补**：下载页最新发布日期；替补 `opencitations_api`（每 IP 180 次/分）、OpenAlex `referenced_works`。

### orcid_public_data_file

**1 身份 / 2 通道**：服务 `orcid`；`impl: mapper`；metadata（作者身份）× `snapshot_import`；platform；W3。

**3 上游事实**：年度公共数据文件 CC0、不附使用条件，托管 figshare，每年 10 月前后发布（官方页 ◐）；2025 版 figshare 30375589；2026 版预计 2026-10，未核 [https://info.orcid.org/what-is-orcid/services/annual-data-files/, 2026-09-30，◐]。Public API 凭证发给个人、禁持续轮询、不得用于营收产品 [https://info.orcid.org/public-client-terms-of-service/, 2026-09-30]；`pub.orcid.org` robots 全禁 [https://pub.orcid.org/robots.txt, 2026-09-30]。

**5 游标**：`snapshot_release{年份}`；子集键只取公开种子与 ≥`k_cf` 的作者键；缺失不产出 tombstone。

**8 合规**：平台侧只用本文件；API 通道只在用户侧 OAuth（`orcid_api`，归属待拍板）；名录 ⚑COMM 针对 API 条款，文件为 CC0，是否对文件通道解除 ⚑COMM 只提"待评审"，不自动放宽。

**10 测试**：figshare 文件清单、截断样本（多作品、私有字段缺省）。

**11 探针与替补**：figshare 新版本、条款页日期；无平台侧替补。

### pwc_archive_import

**1 身份 / 2 通道**：服务 `pwc_archive`；`impl: mapper`；metadata（论文—代码—数据集链接）× `snapshot_import`；platform；W3。

**3 上游事实**：Hugging Face `pwc-archive` 下 7 个数据集；`papers-with-abstracts` 的 `lastModified` 为 2026-08-17，并非冻结；6 个标 CC BY-SA 4.0，`pwc-paper-redirects` 许可标签只有 `cc` [https://huggingface.co/api/datasets?author=pwc-archive, 2026-09-30]。

**5 游标**：`repo_commit{repo=数据集, commit_sha=revision}`；revision 变化即重导。

**8 合规**：⚑SA：派生数据集受 ShareAlike 约束；`background`。

**10 测试**：每个数据集的截断样本与 revision 元数据。

**11 探针与替补**：各数据集 `lastModified`；无替补。

### ror_dump

**1 身份 / 2 通道**：服务 `ror`；`impl: mapper`；metadata（机构）× `snapshot_import`；platform；W3。

**3 上游事实**：Zenodo（DOI `10.5281/zenodo.6347574`），CC0，"通常至少每月一次"，JSON + CSV；自 2.0（2025-12-16）起文件名不带版本号；v1 已下线，`/v1/` 返回 410 [https://ror.readme.io/docs/data-dump, 2026-09-30]。官方建议用 Zenodo API 探测新版，与 `zenodo.org` robots 禁 `/api` 冲突，本族改用 DataCite 查询概念 DOI 的新版本。

**5 游标**：`snapshot_release{Zenodo 版本 DOI}`；整版导入；`status` 为 inactive、withdrawn 的机构写 `status_claims`，不产出 tombstone。

**8 合规**：CC0；`background`。

**10 测试**：v2 schema 样本、410 反例、文件名模式变化反例。

**11 探针与替补**：Zenodo 最新版本（经 DataCite）、文件名模式；替补 ROR v2 API（每 IP 2,000 次/5 分钟）只做 `affiliation` 匹配兜底。

### s2_datasets

**1 身份 / 2 通道**：服务 `s2`；`impl: custom_plan`（release 与 diff 编排）；metadata 与 latest（嵌入、TLDR）× `snapshot_import`、`increment`；platform；W3。

**3 上游事实**：release 列表最新 2026-09-22，此前 2026-09-17、2026-09-09，约周更 [https://api.semanticscholar.org/datasets/v1/release/, 2026-09-30]；下载链接须 key，为临时预签名 URL；diffs 列出要插入或替换与要删除的文件（S2 教程，长稿）；papers、abstracts、citations、tldrs、s2orc_v2 为 ODC-BY，嵌入为 Apache-2.0（长稿 C26）；API 许可禁止重新打包、分发 API，S2 Data 另按随附许可（举例含 CC BY-NC），商用未明文允许或禁止 [https://www.semanticscholar.org/product/api/license, 2026-09-30]。

**5 游标**：首次 `snapshot_release`，其后 `seq`（release 对）应用 diffs；删除文件产出 tombstone。

**8 合规**：⚑COMM；部署 key 以 `AuthRef(deployment/s2_key)` 引用；预签名 URL 主机须在 `allowed_hosts` 字面登记（主机名未核）；签名参数只进 `params_digest`。

**10 测试**：release 列表、diff 清单、截断样本；FS-BS-10。

**11 探针与替补**：release 节奏、许可页日期；替补 `s2_api`（全局 1 RPS）与 OpenAlex。

**6.3 P2（按需补卡）**

`cinii_resourcesync`（ResourceSync）、`openaire_graph_dump`（Zenodo 全图 dump，DOI `10.5281/zenodo.3516917`，CC BY 4.0，长稿，未复核）、`wikidata_dump`（dump 子集，CC0）只在 §5 总表占一行，按需补卡；补卡时同样过 manifest 闸与 BS 套件，Zenodo 托管的一律经 DataCite 发现。

### 6.4 桥接连接器的本族目标形态（主卡在 v1-bridge）

#### 目标形态：DROPS dblp 月度快照（承接 `dblp_drops_snapshot`）

- 事实：XML 月度快照 DOI `10.4230/dblp.xml.YYYY-MM-01`，DataCite 共 152 条；2026-09-01 版 1,099,942,087 字节、12,928,181 条、`cc0-1.0`；上两期 12,846,217、12,751,652 条 [https://api.datacite.org/dois?query=id:10.4230/dblp.xml.*, 2026-09-30]；下载 `https://drops.dagstuhl.de/storage/artifacts/dblp/xml/2026/dblp-2026-09-01.xml.gz`，同路径 `.md5` 存在；DROPS robots 只禁 `/api/*`、`/metadata/*/*`、`/entities/*/metadata/*`，未禁 `/storage/` [https://drops.dagstuhl.de/robots.txt, 2026-09-30]。`dblp.org` robots 全禁且具名禁止 Claude 类 UA，本项目任何组件不访问 dblp 主站（D-050）。
- 形态：发现经 DataCite；MG-2 用 DataCite `sizes` 与 `.md5`；流式 iterparse；游标 `snapshot_release{YYYY-MM-01}`；删除 = 相邻两版 dblp key 差集（连续两版缺失）；产出 venue 与届目录、作者 PID；v1 `parse_volume_xml` 可复用（推断）。探针：DataCite 最新快照日期超 40 天告警，`Content-Length` 与 `sizes` 一致。替补：RDF 月度快照（`10.4230/dblp.rdf.ntriples.*`）或自建 QLever 镜像；小查询由 `dblp_sparql`。

#### 目标形态：RePEc ReDIF 批量同步（承接 `repec_redif`）

- 事实：rsync 模块 `rsync://rsync.repec.org/RePEc-ReDIF/`、`RePEc-AMF`、`RePEc-OAI-DC`、`CitEc-AMF`，更新频率与礼仪未写 [http://rsync.repec.org/, 2026-09-30]；集中 ReDIF 另有 FTP；OAI `oai.repec.org` 实测 502，不作主通道；IDEAS API 不公开；"Non-commercial use assumed"，强烈不建议抓网站 [https://ideas.repec.org/getdata.html, 2026-09-30]。
- 形态：镜像只取目标系列（已核 `nbr:nberwo`、`cpr:ceprdp`、`iza:izadps`、`ecb:ecbwps`、`imf:imfwpa`；`pra:mprapa`、`ces:ceswps` 为长稿值）；游标 `snapshot_release{同步时间 + 文件清单哈希}`；记录级用 ReDIF `Creation-Date`、`Revision-Date`（规范，未复核）；删除 = 模板连续两次同步缺失；handle 映射保持单射（D-036），扩展系列须另立 ADR。NBER 零自动化后，`nbr:nberwo` 只经 RePEc 中央档案取得，不访问任何 `nber.org` 主机（v1 曾读 `repec.nber.org`、`www2.nber.org`，已不适用）。
- 阻塞：rsync、FTP 不在网关现有能力内（见未决事项）；⚑COMM 建议补标（待拍板），经 RePEc 代收的来源连带。

## 7. 本族风险、坑与待决

- **体量**：OpenAlex 单版约 750 GB，Crossref 年度 208 GB，PMC 约 800 万对象；容量预算归 05，超出先收紧 `floor`。
- **托管平台的 robots**：Zenodo 禁 `/api`，S3 桶主机的 robots 状态未核；每个 bulk 主机都要 robots 条目（连接器 lint），未确认前不调度。
- **校验信息不齐**：OpenCitations、DOAJ、DataCite 年度文件未见官方校验和（未核），只能对账字节数与记录数，MG-2 须允许"上游未提供"并在卡片注明。
- **许可混合**：同一快照内记录级许可不同（PMC、OpenAlex 位置），共享层一律按记录级许可闸处理；ShareAlike 源（zbMATH、PwC）的派生数据集须单独标注。
- **节奏漂移**：PubMed 2026 baseline 延到 1 月底；ROR 文件名规则变化；`expected_next` 过期只告警，不改策略模式。

## 怎么验收

- CL0：清单、卡片与证据齐，每个 bulk 主机有 robots 条目，lint 通过，合规字段经第二人复核。
- CL1：FS-BS-01…FS-BS-10 与 CT-01…CT-12 在离线 CI 全过；每个 P0 连接器有 manifest、截断样本、删除样例与结构变更反例四类 fixture，阻塞主机只用合成 fixture。
- CL2：staging 经网关各完成一次完整导入与一次断点续传演练，零 robots 违例、零未声明主机，逐文件对账全绿。
- V1 出口：`openalex_snapshot`（及待拍板 1 通过时的 `crossref_annual_file`）按兴趣并集完成首版子集导入；起步语料规模在 03 的 100–300 万 work 目标内；删除日志清理可复现。

## 未决事项

- **待拍板 1**：网关是否支持非 HTTP 传输（rsync、FTP）与 S3 请求方付费签名；不支持时 `repec_redif` 改用 HTTPS 可得的档案、`crossref_annual_file` 只能等 AWS 通道或放弃年度文件改用 OpenAlex 快照回填。BitTorrent 建议不支持。
- **待拍板 2**：`europe_pmc_bulk` 是否保留（`pmc_s3` 已覆盖 PMC OA 子集）。
- **待拍板 3**：ORCID 年度 CC0 文件通道是否解除 ⚑COMM；RePEc 是否补 ⚑COMM（RePEc 声明 "Non-commercial use assumed"）。
- **需 05 增补**：`ImportLedger` 与按 `scope_key` 的快照进度表、冷存储保留期（契约待拍板 P-3）。
- **流式原语已入 [契约](../contract.md) §3、§5**：`RequestSpec.stream`、`Response.blob`、`BlobRef`、`SnapshotChunk`、`parse_chunk` 与平台侧 `integrity` 判定者（网关）。**其余待在契约中确认**：`SnapshotSpec`、`SnapshotFile`、`ImportLedger`、`GateVerdict`、`SubsetFilter`、`ReconcileReport`；Manifest `snapshot.*`；`request_class: bulk_object`；runner 判记录数的归类；观测值 `absent_in_release`；受 robots 阻塞主机只用 `fixture_policy.recorded_via: handwritten_synthetic`（写明原因）能否达 CL1，待一致性文档确认。

更细的材料：`git show v2-drafts:docs/plan/v2/03-sources-and-corpus-pipeline.md`（§5.3–5.4 族表与专有接口、§10.5 本地底座与兴趣并集伪代码、§7.9 新写 connector 汇总、§14.1 v1 去向）；[03 语料流水线](../../03-sources-and-corpus-pipeline.md#语料流水线与-enrich)；[支持名录](../../../../catalog/source-directory.md)。
