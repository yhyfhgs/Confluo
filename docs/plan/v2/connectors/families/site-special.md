---
title: 专站族 site_special：族规范与连接器卡片
status: draft
owner: opus5.5-primary
updated: 2026-09-30
---

# 专站族 site_special：族规范与连接器卡片

> 本文回答：有官方 API 或官方结构化页面、又不归其他八族的专站，连接器在[通用契约](../contract.md)之上还要声明什么、怎样测、怎样防结构漂移，本族 28 个 connector_id 各自的事实、游标、映射、合规、探针与替补。结论：本族只加三件东西——`StructureContract`（依赖的字段、选择器或 JSON 路径，逐条配 fixture）、结构漂移探针加按会期设期望计数的 `canary_query`、无 Crawl-delay 且无文档限额主机的保守自定限速 `self_rate`；OpenReview 平台侧继续停用，用户 token 只留在扩展或 pc-agent；nber.org 全部主机零自动化；"免费阅读但未声明开放许可"的全文只给外链。

## 要点

- **适用边界**：官方 API 或官方结构化页面，且 robots 允许、结构稳定、无挑战门（长稿简报 R2-12）；否则只走 Crossref 与外链。
- **族专有件**：`StructureContract` 让页面改版成为响亮的 `parse` 失败；`Edition` 日历驱动 `canary_query`；`self_rate` 给 robots 404 主机定保守礼貌。
- **规模**：P0 14 个（新写 6、v1 桥接 8，完整 13 节）、P1 11 个（紧凑卡 9 张；`ieee_xplore_user` 撤销，只留墓碑锚点；`cambridge_core_user` 撤销，卡片在 [platform-family](platform-family.md#cambridge_core_user)，本文只留总表指向行）、P2 登记 3 个；`hf_papers_api`、`scoap3_api` 的卡片在 [aggregator-api](aggregator-api.md)。桥接连接器卡片写在移植目标族，[v1-bridge](v1-bridge.md) 只写桥接期条款。
- **拒绝信号统一归 `challenge`**：CVF 对部分 UA 的 403、OpenReview 403 `ChallengeRequiredError`、Cloudflare 挑战页，不重试、不换 UA、冷却 24 小时。
- **与长稿不同**（F 调研 2026-09-30 实测）：PMLR 有卷级 `feed.xml`；bioRxiv `/details` 已恢复；NBER T&C（2026-08-01）禁一切未经许可的自动访问；QE 主机证书过期；OpenReview 上出现 NeurIPS 2026 新分轨名（proceedings 站命名未核）。

## 1. 本族回答什么与适用边界

本族承接"一站一模块"：出版商或预印本服务器自有 API（bioRxiv、PLOS、eLife、World Bank D&R、APS Harvest OA 集；OpenReview、OSF 待书面确认）、会议与论文集官方静态页（PMLR、CVF、NeurIPS、IJCAI、JMLR、TMLR 列表、USENIX、ECVA、ISCA、PVLDB）、官方数据仓库（ACL Anthology）与会议程序页（ASSA）；另承载 v1 桥接中去向为解散或暂停的 `aea_fulltext_user`、`econsoc_fulltext`、`nber_site` 的卡片。

| 相邻族 | 分界 |
|---|---|
| [crossref-delegated](crossref-delegated.md) | DOI 在 Crossref 的元数据走委托；本族只补分轨、摘要、许可、站内编号或 Crossref 未覆盖的年份 |
| [feed](feed.md) | RSS 归 feed 实例（如 `jmlr.xml`）；本族做卷页、论文页与对账 |
| [oai-pmh](oai-pmh.md) | 任何 OAI-PMH 端点都是 oai_pmh 实例（AAAI OJS、TE、QE） |
| [aggregator-api](aggregator-api.md) | 聚合器与学科库的 API；单一站点自有 API 归本族 |
| [bulk-snapshot](bulk-snapshot.md) | 官方快照与年度文件；ACL 数据仓库按 commit 增量，归本族 |
| [platform-family](platform-family.md)、[official-tdm-api](official-tdm-api.md) | 托管平台配方与用户 key 全文 API；APS 全量 Harvest 按长稿归后者（归属两说待核，未决 9） |

不适用：robots 被挑战（Cambridge Core）、平台层禁接（IEEE，HC-27）、ToS 禁自动化（NBER）。见 [03 连接器九族](../../03-sources-and-corpus-pipeline.md#连接器九族与执行位置)、[08 robots 与 ToS](../../08-compliance-security-privacy.md#robots-与-tos-统一政策)。

## 2. 族专有接口

通用部分（`PlatformConnector`、`RequestSpec`、`Expectation`、`PageSignals`、七种游标、15 个 `error_class`、`status_overrides`、`ProbeSpec`、`FulltextOption`）见 [contract](../contract.md)。

### 2.1 StructureContract 与 Edition

```python
# 设计伪代码 —— site_special 在 ConnectorContract v1 之上的专有部分
@dataclass(frozen=True)
class FieldRule:
    field: str                # RawRecord.payload 的键，如 "title"、"pdf_url"、"track"
    locator_kind: Literal["css", "xpath", "jsonpath", "xml_path", "meta_name", "rss_elem", "bibtex_field"]
    locator: str              # 'dt.ptitle > a'、'$.collection[*].doi'、'citation_title'
    cardinality: Literal["one", "many", "optional"]
    required: bool            # 缺失即 ParseError，整页不提交
    min_hit_ratio: float = 1.0
    enum: Literal["open", "strict"] | None = None   # open 未知值照收并告警；strict 未知值隔离该条
    normalize: tuple[str, ...] = ()   # 封闭词表：strip、collapse_ws、http_to_https、split_authors、
                                      #   year_only、unescape_html、mathml_to_text、trim_trailing_newline
@dataclass(frozen=True)
class StructureContract:
    contract_id: str          # "<connector_id>/<endpoint_id>@<rev>"
    endpoint_id: str; doc_kind: Literal["html", "json", "xml", "rss", "bibtex"]
    item_locator: str; item_key: tuple[str, ...]; fields: tuple[FieldRule, ...]
    min_items: int; max_items: int | None
    fingerprint: str          # 字段集合 + 结构路径骨架哈希（不含文本）
    fixtures: tuple[str, ...] # 四类 fixture id
@dataclass(frozen=True)
class Edition:                # 届次或卷；由实例日历与已提交游标纯函数推出
    key: str; state: Literal["expected", "open", "closed"]
    opens_after: date | None  # 早于此日零请求
    expected_count: tuple[int, int] | None   # 官方录用数或上届 ±30%
@dataclass(frozen=True)
class StructureSignal:        # PageSignals 的类型化扩展，由 apply_contract 产出
    contract_id: str; items: int; field_hits: Mapping[str, float]
    unknown_enum_values: Mapping[str, tuple[str, ...]]; fingerprint_now: str

class SiteSpecialConnector(PlatformConnector):
    structure_contracts: Mapping[str, StructureContract]   # endpoint_id → 契约
    def editions(self, inst: ConnectorInstance, ctx: PlanCtx) -> tuple[Edition, ...]: ...
    # parse 先调 SDK 的 apply_contract(resp, sc) -> (items, StructureSignal)：required 缺失、
    # items < min_items 或命中率不足 → ParseError（整页隔离，游标不动）
```

届次规则：`expected` 在 `opens_after` 前零请求；上线后 `open`，每周最多重列一次；连续 30 天无变化且计数在期望区间即 `closed`，之后只在季度对账时重列。

### 2.2 结构漂移探针与 canary_query

- `structure` 探针：每个 StructureContract 一条，每周取正常页同一 URL，比对 `fingerprint`、命中率与条目数；红灯冻结晋级，连续 3 次（契约初值）端点降级。
- `canary_query`：每个 `open` 届次一条，断言计数在 `expected_count` 内；骤降判 `empty_body/count_drop`，切替补链。
- 变异 fixture：SDK 从正常页合成"删一个 required 选择器""改条目根 class"的样本，只证明失败是响亮的，不入黄金。
- 每个触达主机有 `robots` 探针（存全文哈希）：变严立即降级，变松只告警（[03 策略引擎与漂移探针](../../03-sources-and-corpus-pipeline.md#策略引擎与漂移探针)）。

### 2.3 robots 404 主机的保守自定限速 self_rate

robots.txt 返回 4xx 按 RFC 9309 视为无限制（5xx、网络错误、robots 被挑战视为全禁）。无限制不等于不礼貌：凡"无 Crawl-delay、无文档限额"的主机，端点必须声明 `self_rate`，网关取它与上游声明的较严者。

```yaml
# 设计伪代码 —— ConnectorManifest.endpoints[].self_rate（数值为设计取值，未核）
self_rate:
  basis: robots_404        # robots_404 | robots_no_delay | undocumented_api | crawl_delay | documented
  min_interval_s: 5        # 族下限：静态页 5 s；无文档限额的 API 1 s；有 Crawl-delay 取其值
  concurrency: 1
  daily_cap: 3000          # 单主机日硬顶，按最大届次条目数 × 1.2 估
  lanes: [harvest]         # interactive 只允许 lookup 单条
  backoff: {on: [429, 503], honor_retry_after: true, factor: 2, recover_after_h: 24}
```

v1 同类站点为 30 次/分、并发 1；本族下限 12 次/分。平台 UA 固定 `Confluo/<ver> (+<部署方说明页>; mailto:<部署方联系邮箱>)`，被拦截不换 UA。

### 2.4 状态码覆盖与挑战标记（族默认）

| 情况 | error_class | 处置 |
|---|---|---|
| 静态站 403（HTML） | `challenge` | 不换 UA；请求与落点主机冷却 24h |
| 403 JSON `ChallengeRequiredError` | `challenge` | 不访问 `challengeUrl` |
| 200 含 CF 挑战标记（`cf-chl`、"Just a moment"） | `challenge`（`fake_success`） | 同上 |
| 200、0 条目、届次 `open` | `parse`（`apply_contract` 按 `min_items` 判；JSON 端点的空体先由网关按 Expectation 判 `empty_body`） | v1 cvf 教训：列表页无合法空态 |
| 404、届次 `expected` | 非错误（该端点 `legit_status` 含 404） | 合法未上线，不推进游标 |
| 429、带 `Retry-After` 的 503 | `rate_limited` | 按 `Retry-After` 退避，间隔翻倍，24h 后恢复 |
| TLS 证书失效 | `transient` | 探针告警，不降低校验 |

每行在 `status_overrides` 中配一个 fixture（CT-05）。

### 2.5 删除语义与 tombstone 纪律

清单声明 `deletion_semantics ∈ {state_field, snapshot_diff, list_diff, none}`（F4 调研建议 `persistent、transient、state_field、snapshot_diff、none`；本族不涉 OAI 的前两值，另加 `list_diff`，须契约评审收录，见未决 11）。`list_diff` 站点只在"`closed` 届次连续两次完整重列都缺该条、两次 `structure` 探针为绿、计数在期望区间"时产出 tombstone；解析失败永不产生 tombstone。有显式字段的（ACL `retracted`、OpenReview `venueid`）写 `status_claims`。

### 2.6 全文

- 逐篇或按年代有开放许可的（JMLR、ACL 按年代许可、PLOS、eLife、APS OA 集中的 CC BY 文章、bioRxiv 逐篇）产出 `oa_link`，带 `license` 与 `basis`；进共享缓存只经许可白名单，且共享 OA 缓存默认关（D-045）。
- "免费阅读但未声明开放许可"（PMLR、CVF、NeurIPS、IJCAI、USENIX、ECVA、ISCA、OpenReview）只产出 `open_in_tab`。
- 本族不产出 `user_fetch`；用户侧全文归 platform-family 与 official-tdm-api。

## 3. 实例与清单字段

ConnectorManifest 本族增加：

| 字段 | 含义与 lint |
|---|---|
| `structure_contracts[]` | 每个被 parse 的端点一份；缺失即 CL0 不过 |
| `endpoints[].self_rate` | §2.3；无 Crawl-delay 且无文档限额的主机必填，不低于族下限 |
| `editions` | `{calendar ∈ instance/feed/menu_page/api, open_poll_days, close_after_days, expected_count_rule}`；有届次的站点必填 |
| `license_rules[]` | 按年代或载荷路径，如 ACL `year < 2016 → CC-BY-NC-SA-3.0`；每条配黄金 NormRecord |
| `deletion_semantics` | §2.5；必填 |
| `challenge_markers[]` | 站点特有挑战标记，叠加族默认；每条配 fixture |

ConnectorInstance 本族字段：`venues[]`（站内会议代码 → venue_id）、`edition_calendar`、`track_map`（开放枚举）、`crossref_container_titles`（前缀共用时按 container-title 分流，如 10.52202 由 NeurIPS 与 ISPM 等共用、10.24963 由 IJCAI 与 KR 共用）。CVF、USENIX、ACL 的多个会议列在同一实例内。

## 4. 族一致性套件

`FS-SS-NN`，按"实例 × fixture"参数化，与 CT-01…CT-12 一起构成 CL1（[conformance-and-testing](../conformance-and-testing.md)）。

| rule_id | 断言 |
|---|---|
| FS-SS-01 | 被 parse 的端点都有 StructureContract；每条 FieldRule 在正常页命中；mapper 读的键 ⊆ `fields` |
| FS-SS-02 | 变异 fixture 一律 `parse`，游标不动、零 tombstone |
| FS-SS-03 | `open` 届次 0 条目为 `parse`（清单显式声明 `empty: legit` 并配 fixture 的端点除外，如 PMLR 已建未填的卷）；`expected` 届次 404 合法且不推进 |
| FS-SS-04 | CF 页、403 HTML、`ChallengeRequiredError` 归 `challenge`，正文不交 parse，重试 0 |
| FS-SS-05 | 无 Crawl-delay、无文档限额的主机都有 `self_rate` 且不低于族下限 |
| FS-SS-06 | open 枚举未知值照收并进 StructureSignal；strict 未知值只隔离该条 |
| FS-SS-07 | 每个 `open` 届次有 `canary_query`；骤降 fixture 判 `empty_body/count_drop` |
| FS-SS-08 | `license_rules` 每条有黄金（如 ACL 2015、2016 各一）；NC 的 `commercial_ok=false` 由 `classify_rights()` 得出 |
| FS-SS-09 | 未声明许可的站点只产出 `open_in_tab` |
| FS-SS-10 | 规范化幂等：`norm(norm(x)) == norm(x)`（属性测试） |
| FS-SS-11 | `list_diff` 的 tombstone 只在 §2.5 条件下产生 |
| FS-SS-12 | `allowed_hosts` 不含本族禁用主机：nber.org 各主机、dblp.org、www.biorxiv.org、api.osf.io 与 api.elifesciences.org（书面确认前）、api2.openreview.net 与 api.openreview.net（平台侧停用期）、econometricsociety.org、pubs.aeaweb.org、www.cambridge.org、ieeexplore.ieee.org |

每个 StructureContract 的四类 fixture（正常页、空页或 200 空体、限流或错误、边界）：平台侧端点只经 staging 网关录制；用户侧与书面确认前的主机只用合成 fixture（未决 13）；HTML 中的摘要按 B 类换等长合成文本。

## 5. 连接器清单总表

人日为 E 清单粗估（未核）；CL 当前全部为"—"（未建清单），表中写目标。波次规则与调整项见 [implementation-plan](../implementation-plan.md)，W3 括号内为批次（V3 或 V5）。

| connector_id | 来源（数） | 优先级 | 波次 | exec_side | 人日 | v1 复用 | 前置依赖 | CL 目标 |
|---|---|---|---|---|---|---|---|---|
| `openreview_api` | openreview（1） | P0 | 平台侧停用；用户侧 W3u（token 只在端侧） | mixed | 1.5 | openreview | ⚑ACCT；V3 | 平台侧 CL0（未确认即 V2 出口 CLX）；用户侧待定（本人 token 查询随 P-13，见未决 4） |
| `acl_anthology_xml` | acl_anthology（1） | P0 | W2，V2 出口前移植 | platform | 1 | acl_anthology | git 经网关 | CL3（V1 出口） |
| `pmlr_volumes` | pmlr（1） | P0 | W2 | platform | 0.5 | pmlr | — | CL3 |
| `cvf_open_access_pages` | cvf_open_access（1） | P0 | W2 | platform | 0.5 | cvf | 平台 UA 实测 | CL3 |
| `neurips_proceedings_pages` | neurips_proceedings（1） | P0 | W2 | platform | 1 | neurips_proceedings | — | CL3 |
| `ijcai_proceedings_pages` | ijcai_proceedings（1） | P0 | W1 | platform | 1 | — | crossref_delegated | CL3 |
| `jmlr_volumes` | jmlr（1） | P0 | W1 | platform | 1 | — | feed 实例 | CL3 |
| `tmlr_list` | tmlr（1） | P0 | W1 | platform | 1 | — | ⚑ACCT 仅约束 OpenReview 详情 | CL3 |
| `aps_harvest` | aps（1） | P0 | W1（OA 集） | platform | 2 | — | ⚑LIC 仅全量 | CL3 |
| `biorxiv_api` | biorxiv、medrxiv（2） | P0 | W1 | platform | 2 | — | ⚑DRIFT | CL3 |
| `osf_api` | psyarxiv（1） | P0 | W1，确认前不实现 | platform | 2 | — | ⚑ROBOTS 书面确认 | 确认前 CL0 |
| `aea_fulltext_user` | aea_journals（1） | P0 | W3 | user | 1 | aea | V3 | CL1 回放 → V2 出口 CLX；用户侧通道随承接配方在 V3 出口达 CL3（矩阵记此值） |
| `econsoc_fulltext` | econsoc_journals（1） | P0 | W3，只做用户侧 | mixed | 1 | econsoc | V3 | CL1 回放 → V2 出口 CLX；用户侧通道随承接配方在 V3 出口达 CL3（矩阵记此值） |
| `nber_site` | nber_wp、nber_conferences（2） | P0 | 暂停（平台侧与用户侧），取得 NBER 书面许可前不排波次（待拍板） | mixed | 1.5 | nber | NBER 书面许可；法务 | CL0（暂停） |
| `assa_program` | assa_meetings（1） | P1 | W3（V3） | platform | 1.5 | — | — | CL3 |
| `ecva_papers` | ecva（1） | P1 | W3（V5） | platform | 1 | — | — | CL3 |
| `elife_api` | elife（1） | P1 | W3（V5） | platform | 1 | — | ⚑ROBOTS 仅 API | CL3 |
| `isca_archive_pages` | isca_archive（1） | P1 | W3（V5） | platform | 1 | — | — | CL3 |
| `nber_conference_pages` | nber_conferences（1） | P1 | 暂停，取得 NBER 书面许可前不排波次（待拍板） | platform | 1.5 | — | NBER 书面许可 | CL0（暂停） |
| `plos_search_api` | plos（1） | P1 | W3（V5） | platform | 2 | — | — | CL3 |
| `pvldb_volumes` | pvldb（1） | P1 | W3（V5） | platform | 1 | — | ⚑COMM | CL3 |
| `usenix_sessions` | usenix（1） | P1 | W3（V5） | platform | 1.5 | — | — | CL3 |
| `worldbank_dr_api` | worldbank_prwp（1） | P1 | W3（V3） | platform | 1.5 | — | 许可待核 | CL3 |
| `cambridge_core_user` | cambridge_core（1） | P1 | 撤销（待拍板确认 link_only） | user | — | — | 卡片见 [platform-family](platform-family.md#cambridge_core_user) | — |
| `ieee_xplore_user` | ieee_xplore（1） | P1 | 撤销（待拍板确认 link_only） | user | — | — | 见[墓碑](#ieee_xplore_user) | — |
| `ceur_ws_volumes` | ceur_ws（1） | P2 登记 | 不排 | platform | 1 | — | ⚑RECHECK；robots 禁 `/temp/`、`/ftp/` [https://ceur-ws.org/robots.txt, 2026-09-30] | CL0，按需补卡 |
| `eartharxiv_janeway` | eartharxiv（1） | P2 登记 | 不排 | platform | 1.5 | — | robots 无禁令 [https://eartharxiv.org/robots.txt, 2026-09-30]；API 未测 | CL0，按需补卡 |
| `rss_proceedings_volumes` | rss_proceedings（1） | P2 登记 | 不排 | platform | 1 | — | ⚑RECHECK；robots 无 Disallow [https://roboticsproceedings.org/robots.txt, 2026-09-30] | CL0，按需补卡 |
| `hf_papers_api` | hf_papers | P0 信号层 | W1 | — | — | — | 卡片见 [aggregator-api](aggregator-api.md#hf_papers_api) | — |
| `scoap3_api` | scoap3_repo | P1 | W3（V5） | — | — | — | 卡片见 [aggregator-api](aggregator-api.md#scoap3_api) | — |

登记级三行不运行任何通道，证据过期只标 `review_overdue`。暂停与撤销统一写法：暂停 = CL0、不排波次、待许可（待拍板）；撤销 = 不建清单、待拍板确认 `link_only`。`exec_side` 记 `mixed` 的连接器按契约拆成两个清单：PlatformConnector 与 RecipeProvider（同一 connector_id 前缀，id 待契约与矩阵定），各自状态写在卡片 §2（如 `openreview_api` 平台侧停用、用户侧 token 只在端侧）；W3u 为用户侧通道的波次记法（依赖 V3 扩展或 pc-agent，同 [implementation-plan](../implementation-plan.md)）。`hf_papers_api`、`scoap3_api` 在长稿 §5.3 列在本族，按清单归 aggregator_api。

## 6. 连接器卡片

**族默认（卡内未写即按此）**：`contract_version` 1；`connector_version` 从 0.1.0 起；`lifecycle` active；owner 与 backup_owner 由 implementation-plan 指派（P0 两人）；enumerate、increment 走 harvest，locate_fulltext 走 enrich，lookup 走 interactive；Expectation 与状态码按 §2.4，`self_rate` 按 §2.3；fixture 四类加变异 fixture，黄金覆盖每种权利类；探针含每主机 `robots`、`tos_hash`（卡内声明零自动化或停用期零请求的主机除外），每个契约的 `structure`，每个 `open` 届次的 `canary_query`；新鲜度为届次上线后静态页 ≤3 天、API ≤1 天（设计取值）；`review_every`：P0 月看健康、季复核卡片，P1 季复核；本族平台侧不声明 `search`；SCD 批量单位即届次、卷或日窗。卡内端点名为简写，完整 `endpoint_id` 按契约写作 `<source_id>.<name>`（如 `pmlr.volume_page`）；§4 的 `hosts_touched` 并集等于 `allowed_hosts`，即卡片 §3 标注 robots 的站点主机；`budget` 为 `{account: <source_id>.requests, unit: request, ceiling: self_rate.daily_cap}`（免费站点，无美元账户）。§5 水位类游标 `lag_bound` 未核、`late_path: snapshot_reconcile`（`closed` 届次季度对账）、`window_max` P14D（设计取值），卡内另写的除外；新写连接器 `migrate_cursor` 为"首版无"；桥接移植改变游标 kind 的（`acl_anthology_xml`、`pmlr_volumes`、`cvf_open_access_pages`、`neurips_proceedings_pages`）升 `connector_version` MAJOR，声明"重置 + 回填窗口"（按届次全量重列，靠 `(source_id, source_key)` 去重）。

**6.1 P0（完整 13 节）**

### openreview_api

| 节 | 内容 |
|---|---|
| 1 身份 | impl v1_bridge（replay_only），v1 `openreview` 的移植目标；平台侧 paused（桥接只回放，服务账号未确认则 V2 出口转 CLX，见 v1-bridge）；用户侧形态待定（未决 4）；serves `openreview`（兼 `tmlr` 详情），venue 取自 `active_venues`（1,082 个，动态） |
| 2 通道与操作 | 平台侧 metadata、latest 全停，上限 `link_only`（D-052）；用户侧本人查询在扩展或 pc-agent 内执行，token 不出端；fulltext 只 `open_in_tab` |
| 3 上游接口事实 | API v2 `api2.openreview.net`，v1 逐步下线 [https://docs.openreview.net/getting-started/using-the-api, 2026-09-30]；匿名 `/notes` 403 `ChallengeRequiredError`、匿名 `/groups?id=active_venues` 200；两套限流头：`x-ratelimit-*`（reset 为 epoch 秒）、`ratelimit-*`（`ratelimit-policy: 180;w=60`，reset 为相对秒），长稿另见 `20;w=60` [https://api2.openreview.net/groups?id=active_venues, 2026-09-30]；`/notes` 有 `mintmdate`（毫秒）、`sort`、`after`、`trash` [https://api2.openreview.net/docs/api.yml, 2026-09-30]；ToS 一人一号、不得授权第三方代用，元数据 CC0 [https://openreview.net/legal/terms, 2026-09-30] |
| 4–7 请求、游标、映射、SCD | 平台侧 `endpoints: []`、`allowed_hosts: []`、不声明 SCD，U3、U7 提示"平台侧暂停，由 arXiv 与 dblp 快照兜底"；用户侧本地 `date_watermark`（`mintmdate`，重叠 ≥1 小时，按 `(id, tmdate)` 去重），结果只进本人私域（HC-01、HC-04）；`venueid` 迁到 withdrawn、rejected → `status_claims`（长稿，未复核）；403 → `challenge` |
| 8 合规 | ⚑ACCT；第三方代用条款 → token 不经平台服务器；不访问 `/profiles*` 与 `challengeUrl`；书面确认后另起卡评审平台通道 |
| 9 全文 | `open_in_tab`（forum 与 PDF） |
| 10 测试 | 用户侧 fixture 手写合成：`active_venues`（两套头）、`notes` 一页、`trash`、403 |
| 11 探针与替补 | 停用期零请求（匿名探针见未决 5）；替补 `arxiv_oai` → `dblp_drops_snapshot` → forum 外链 |
| 12 运维 | 无平台 SLO；用户侧结果与回执不进任何跨用户统计，运维台不显示用户侧成功率（08），健康只靠维护者合成检查（契约 P-7） |
| 13 已知坑与待决 | v1 把 403 当 AUTH_EXPIRED、token 用 Cookie 头，均作废；`openreview-py` 只用解析部分（契约 P-2）；OpenReview 上 NeurIPS 2026 出现新分轨名（`Evaluations_and_Datasets_Track` 等）；登录后限额未核 |

### acl_anthology_xml

| 节 | 内容 |
|---|---|
| 1 身份 | impl v1_bridge → custom_plan；serves `acl_anthology` 全部 venue（v1 只注册 EMNLP） |
| 2 通道与操作 | metadata、latest：`enumerate`、`increment`（commit 差集）、`lookup`（Anthology ID 或 DOI，本地 join 零网络）、`probe`；fulltext：`locate_fulltext` |
| 3 上游接口事实 | 数据在 GitHub `data/xml` 与 `data/json/people.json`，官方途径为 `acl-anthology` 包 [https://aclanthology.org/faq/api/, 2026-09-30]；包 1.3.3 [https://pypi.org/project/acl-anthology, 2026-09-30]；`data/xml` 最近提交 2026-09-29 [https://github.com/acl-org/acl-anthology, 2026-09-30]；`anthology+abstracts.bib.gz` 约 42 MB [https://aclanthology.org/anthology+abstracts.bib.gz, 2026-09-30]；robots 404 [https://aclanthology.org/robots.txt, 2026-09-30]；`paper` 可含 `revision`、`erratum`、`retracted`、`removed` [https://github.com/acl-org/acl-anthology/blob/master/data/xml/schema.rnc, 2026-09-30]；2016 年起 CC BY 4.0，此前 CC BY-NC-SA 3.0 [https://aclanthology.org/faq/api/, 2026-09-30] |
| 4 请求声明 | `repo_head`（日 1 次）、`repo_fetch`（request_class `bulk_transfer`，未决 2）、`bib_gz`（HEAD + `If-Modified-Since`，探针用）；XML 根 `collection`；`self_rate` 5 s、日顶 50 |
| 5 游标与增量 | `repo_commit{repo, commit_sha, path: data/xml}`；运行固定目标 SHA，逐卷解析，全部提交后推进；卷文件删除（排除改名）→ 该卷 tombstone |
| 6 映射 | Anthology ID、DOI 10.18653 为作品级；`revision` → `version_claim{stage: vor, seq}`；`erratum` → 关系；`retracted` → 撤稿；`removed` → tombstone；许可按 `license_rules`；小修正只以 commit 出现，按载荷变化处理 |
| 7 SCD | `lookup` 按 anthology_id、doi 原生；每日 1–3 次请求 |
| 8 合规 | robots 404、官方数据仓库 → `background`；商用开关开启时 2016 年前内容不共享 |
| 9 全文 | `oa_link` 带年代许可；只有 CC BY 的可进共享缓存 |
| 10 测试 | 正常：一卷 XML、`people.json` 片段；空：无变化 diff；错误：GitHub 429、5xx；边界：四种状态元素、卷文件改名、2015 与 2016 各一卷 |
| 11 探针与替补 | `structure`（schema.rnc 哈希、包大版本）、`deprecation`（仓库迁移）、`count`；替补 Crossref 10.18653（无摘要）→ `dblp_drops_snapshot` |
| 12 运维 | 提交后 ≤2 天；会期内 HEAD 7 天不变告警 |
| 13 已知坑与待决 | 桥接期沿用 v1 `git/trees` 与 raw XML（见 v1-bridge），移植后改 `repo_commit`；包自带 HTTP，只用解析部分（P-2）；升 custom_plan：git 传输与卷级 diff 超出声明式词表 |

### pmlr_volumes

| 节 | 内容 |
|---|---|
| 1 身份 | impl v1_bridge → mapper；serves `pmlr`（ICML、COLT、AISTATS、UAI 等；v1 只注册 ICML） |
| 2 通道与操作 | metadata、latest：`enumerate`、`increment`、`probe`；`lookup` 按 URL；fulltext：`open_in_tab` |
| 3 上游接口事实 | 卷级 RSS `feed.xml` 326 个 item，每个是一卷 [https://proceedings.mlr.press/feed.xml, 2026-09-30]；ICML 2026 未上线（最近 v267 ICML 2025）[https://proceedings.mlr.press/, 2026-09-30]；robots 404 [https://proceedings.mlr.press/robots.txt, 2026-09-30]；卷页含论文列表与 BibTeX（长稿 2026-09-26，未复核）；无 DOI；每卷另有 GitHub 仓库（未核） |
| 4 请求声明 | `volumes_feed`（`min_items` 100）、`volume_page`、`volume_bib`（这两个端点声明 `empty: legit`、`min_items` 0：已建未填的卷为合法空卷，沿用 v1，覆盖 §2.4 族默认并配 fixture；+30 天仍空由 `canary_query` 告警）；`self_rate` 5 s、日顶 2,000 |
| 5 游标与增量 | 发现 `guid_set`（feed 卷 URL）；每卷 `guid_set`，+7、+30 天各重列后 `closed`；feed 滚出不算删除；`list_diff` |
| 6 映射 | 键 `pmlr:v{N}:{slug}`；`stage: vor`；许可 unknown → 摘要不共享展示，卡片优先 arXiv 摘要；卷 → venue 按 feed `description` 与 `track_map` |
| 7 SCD | `lookup` 按 URL |
| 8 合规 | robots 404、静态页、无挑战门 → metadata `background` |
| 9 全文 | `open_in_tab` |
| 10 测试 | 正常：feed、卷页、BibTeX；空：已建未填的卷；错误：503、403；边界：卷号不连续（v335、v338 空缺） |
| 11 探针与替补 | `structure`、`count`（feed item 数单调）、`canary_query`（ICML 卷按会期出现）；替补 `arxiv_oai` → `dblp_drops_snapshot` |
| 12 运维 | ICML 会后 60 天无卷告警 |
| 13 已知坑与待决 | **与长稿不同**：`feed.xml` 取代"首页 diff + 卷号探测"；契约 §6 把 PMLR 列为 `seq` 例子，本卡改用 `guid_set`；ICML 2026 缺卷造成新鲜度缺口 |

### cvf_open_access_pages

| 节 | 内容 |
|---|---|
| 1 身份 | impl v1_bridge → mapper；serves `cvf_open_access`（CVPR、ICCV、WACV；ECCV 归 `ecva_papers`） |
| 2 通道与操作 | metadata、latest：`enumerate`、`increment`、`probe`；`lookup` 按论文页；fulltext：`open_in_tab` |
| 3 上游接口事实 | `/menu` 列 CVPR2013–2026、ICCV2013–2025（奇数年）、WACV2020–2026 [https://openaccess.thecvf.com/menu, 2026-09-30]；列表 `/{CONF}{year}?day=all`，论文页含摘要与 BibTeX（长稿，未复核）；robots 404 [https://openaccess.thecvf.com/robots.txt, 2026-09-30]；自定 UA 200、某通用抓取工具 UA 403，原因未核（F4 实测，2026-09-30）；正式版 DOI 在 IEEE（10.1109，晚 2–6 个月，名录口径） |
| 4 请求声明 | `menu`、`edition_list`（按日落地页时再取 `?day=all`）、`paper_page`；403 → `challenge`；`empty: error`；`self_rate` 5 s、日顶 5,000 |
| 5 游标与增量 | 发现 `guid_set`（`/menu` 届次）；每届 `guid_set`（论文路径）；`list_diff` |
| 6 映射 | 键 `cvf:{CONF}{year}:{path}`；`version_claim{stage: am}`，依据页面"与录用版一致、正式版在 IEEE"的说明（长稿，未复核）；IEEE DOI 经 crossref_delegated 建 vor 关系；版权归作者 → 摘要 B 类 |
| 7 SCD | 每届 2 + N 次请求 |
| 8 合规 | robots 404、无挑战门（上线前以平台 UA 实测）→ `background`；403 即 `challenge`，不换 UA |
| 9 全文 | `open_in_tab` |
| 10 测试 | 正常：`/menu`、`?day=all` 列表、论文页；空：0 条目列表（期望 `parse`）；错误：403 HTML；边界：按日落地页、新增年份 |
| 11 探针与替补 | `structure`、`count`（`/menu` 年份集合）、`canary_query`（每届计数 vs 录用数）；替补 `arxiv_oai` → IEEE Crossref |
| 12 运维 | 出现 403 即告警 |
| 13 已知坑与待决 | UA 相关 403 原因不明；workshop 页是否纳入未定；v1 `quirks.list_mode` 改为两个 `item_locator` 版本 |

### neurips_proceedings_pages

| 节 | 内容 |
|---|---|
| 1 身份 | impl v1_bridge → mapper；serves `neurips_proceedings` |
| 2 通道与操作 | metadata、latest：`enumerate`、`increment`、`probe`；`lookup` 按论文 hash；fulltext：`open_in_tab`；DOI 对齐由 crossref_delegated 完成 |
| 3 上游接口事实 | 年页 `paper_files/paper/{year}`；2025 年页含 `vol38-main-conference` 与 64 个 `data-track="creative_ai_track"` 条目 [https://proceedings.neurips.cc/paper_files/paper/2025, 2026-09-30]；robots 404 [https://proceedings.neurips.cc/robots.txt, 2026-09-30]；论文页 `citation_doi` 为 10.52202（长稿，未复核）；该前缀与其他会议共用：2026-08-01 起 6,112 条，NeurIPS 38 占 5,823、ISPM2026 占 287 [https://api.crossref.org/prefixes/10.52202/works, 2026-09-30] |
| 4 请求声明 | `year_page`、`paper_page`；`data-track` 为 open 枚举；`self_rate` 5 s、日顶 7,000 |
| 5 游标与增量 | 发现 `seq{key: year, probe_ahead: 1}`；每年 `guid_set`（论文 hash）；`list_diff` |
| 6 映射 | 键 `neurips:{year}:{hash}`；DOI 按 container-title 过滤后作作品级 ID；`data-track` → venue track，未知值照收并告警；`stage: vor`；许可未声明 → 摘要 B 类 |
| 7 SCD | 每年 1 + N 次请求 |
| 8 合规 | robots 404、无挑战门 → `background` |
| 9 全文 | `open_in_tab` |
| 10 测试 | 正常：年页、卷页、Creative AI 页、带 `citation_doi` 的论文页；空：未上线年份 404；错误：503；边界：未知 `data-track` |
| 11 探针与替补 | `structure`；`count`（分轨集合与各轨数量）；`canary_query`（主会计数）；替补 `arxiv_oai` |
| 12 运维 | DOI 晚约 8 个月（长稿名录，未复核），经 crossref_delegated 回填 |
| 13 已知坑与待决 | v1 `(era, track)` 闭表会漏收新分轨，改 open 枚举；2026 年分轨命名与上线时间未核 |

### ijcai_proceedings_pages

| 节 | 内容 |
|---|---|
| 1 身份 | 新写，impl mapper；serves `ijcai_proceedings`（兼 KR） |
| 2 通道与操作 | metadata：`enumerate`、`increment` 补 Crossref 缺的字段与 2017 年前年份；latest 主通道是 crossref_delegated；fulltext：`open_in_tab` |
| 3 上游接口事实 | 年页 `/proceedings/{y}/`，2026 年 972 个 PDF 链接、© IJCAI [https://www.ijcai.org/proceedings/2026/, 2026-09-30]；robots `Crawl-delay: 10`、禁 `/search/` [https://www.ijcai.org/robots.txt, 2026-09-30]；Crossref 10.24963 自 2017 年起、与 KR 共用：2026 年 IJCAI-35 972 + KR 111 [https://api.crossref.org/prefixes/10.24963/works, 2026-09-30] |
| 4 请求声明 | `year_page`；`self_rate{basis: crawl_delay, min_interval_s: 10}`、日顶 1,500 |
| 5 游标与增量 | 发现 `seq{key: year}`；每年 `guid_set`（PDF 链接）；`list_diff` |
| 6 映射 | 键 `ijcai:{year}:{paper_no}`；有 DOI 时以 DOI 为作品级 ID；IJCAI 与 KR 分流在 crossref_delegated 实例；© IJCAI → 摘要 B 类 |
| 7 SCD | 每年 1 次请求 |
| 8 合规 | robots 允许年页 → `background` |
| 9 全文 | `open_in_tab` |
| 10 测试 | 正常：2026 年页；空：未上线年份；错误：503；边界：2017 年前旧页（结构未核） |
| 11 探针与替补 | `structure`、`canary_query`（PDF 数 vs Crossref IJCAI 计数）；替补 crossref_delegated → `dblp_drops_snapshot` |
| 12 运维 | 族默认 |
| 13 已知坑与待决 | 2017 年前页面未勘察；分轨字段是否在年页可得未核 |

### jmlr_volumes

| 节 | 内容 |
|---|---|
| 1 身份 | 新写，impl mapper；serves `jmlr` |
| 2 通道与操作 | metadata：`enumerate`（卷页对账）、`lookup`（论文页 `citation_*`）；latest 由 feed 实例 `jmlr.xml` 承担；fulltext：`oa_link` |
| 3 上游接口事实 | RSS `jmlr.xml` 205 个 item，`link` 为 http、`pubDate` 只有年份、`author` 为逗号拼接、`description` 为摘要 [https://www.jmlr.org/jmlr.xml, 2026-09-30]；robots 404 [https://www.jmlr.org/robots.txt, 2026-09-30]；论文页 `citation_*`、PDF 首页 "License: CC-BY 4.0"（长稿，未复核）；无 DOI |
| 4 请求声明 | `volume_page`（`/papers/v{N}/`）、`paper_page`；`self_rate` 5 s、日顶 1,000 |
| 5 游标与增量 | 当年卷 `guid_set`（论文 URL，规范化为 https）；往年卷 `closed`，季度对账；`pubDate` 不能做水位 |
| 6 映射 | 键 `jmlr:v{vol}:{id}`；作者取 `citation_author`；CC BY 4.0 → 摘要 A 类；`stage: vor` |
| 7 SCD | `lookup` 按论文 URL |
| 8 合规 | robots 404、官方页 → `background` |
| 9 全文 | `oa_link`（CC BY 4.0，须署名） |
| 10 测试 | 正常：卷页、论文页；空：新卷未填；错误：S3 `NoSuchKey` 式 404（长稿）；边界：http 链接、MLOSS 栏目 |
| 11 探针与替补 | `structure`、`count`（RSS item 数与字段集合）；替补 feed 实例 → `dblp_drops_snapshot` |
| 12 运维 | RSS 出现后 ≤1 天补全 |
| 13 已知坑与待决 | 许可依据来自长稿，CL0 出口前复核 |

### tmlr_list

| 节 | 内容 |
|---|---|
| 1 身份 | 新写，impl mapper；serves `tmlr` |
| 2 通道与操作 | metadata、latest：`increment`（列表差集）；fulltext：`open_in_tab`；不触碰 OpenReview |
| 3 上游接口事实 | `/tmlr/papers/` 去重得 4,788 个 forum 链接（长稿 4,767）[https://www.jmlr.org/tmlr/papers/, 2026-09-30]；jmlr.org robots 404；无 DOI；认证标签在 OpenReview（未核） |
| 4 请求声明 | `list_page`；`min_items` 4,000；`self_rate` 5 s，日 1 次 |
| 5 游标与增量 | `guid_set`（forum id）；`deletion_semantics: none`（撤稿标识未见，未核） |
| 6 映射 | 作品级键 `openreview:{forum_id}`；标题与作者取列表（字段未核）；经 identify 与 arXiv 匹配；许可未声明 |
| 7 SCD | 单页全量 |
| 8 合规 | JMLR 官方页、无 robots；⚑ACCT 只约束 OpenReview 详情 |
| 9 全文 | `open_in_tab`（forum） |
| 10 测试 | 正常：列表页；空：0 链接（期望 `parse`）；错误：503；边界：重复链接、forum id 格式变化 |
| 11 探针与替补 | `structure`、`count`（链接数单调）；替补 `arxiv_oai` → `dblp_drops_snapshot` |
| 12 运维 | 日更 |
| 13 已知坑与待决 | Featured、Survey 等认证标签在书面确认前拿不到 |

### aps_harvest

| 节 | 内容 |
|---|---|
| 1 身份 | 新写，impl custom_plan；serves `aps`（Physical Review 系列）；全量 Harvest 长稿记为用户授权，[official-tdm-api](official-tdm-api.md) 写一行指向；F3 认为全量 token 属平台许可、不应出现在用户侧，两说待核（未决 9） |
| 2 通道与操作 | metadata：`enumerate`、`increment`（OA 集）、`lookup`（DOI）；latest 主通道 crossref_delegated（10.1103）；fulltext：`locate_fulltext` |
| 3 上游接口事实 | `GET /v2/journals/articles`、`/{id}`、`/{id}/accepted_fulltext`；参数 `from`、`until`、`date`（默认 modified，可 published）、`journals`、`set=openaccess`、`per_page` ≤100；OA 集免认证，否则 Bearer、授权 IP 或 CHORUS 头；必须跟随 `Link` 头分页 [https://harvest.aps.org/docs/harvest-api, 2026-09-30]；限速未写，站点靠 Cloudflare 与 429/503 控速（F5）；harvest 主机 robots 404（F3 实测，2026-09-30）；同一两天窗口 modified 约 3,986 篇、published 约 88 篇（`per_page=1` 读总页数，F3 实测）；期刊站 ToS 第 5 条禁系统化下载 [https://journals.aps.org/info/terms.html, 2026-09-30] |
| 4 请求声明 | `oa_published`、`oa_modified`（周对账）、`article_by_doi`（只查已在 OA 集见过的 DOI，非 OA 文章的 401 是文档化语义，不作挑战探测）；根 `data`；OA 集上的 401、403 按 `challenge`；`self_rate{basis: undocumented_api, min_interval_s: 1}` |
| 5 游标与增量 | 新文 `date_watermark{field: published, granularity: day}`，重叠 1 天，`bounds [from, until]`；修订 `oa_modified` 独立 scope，`window_max` 7 天；删除表示未核 |
| 6 映射 | DOI（不透明后缀）为作品级 ID；arXiv 号建关系；许可逐篇取 `rights.licenses[].url`；摘要 MathML 经 `mathml_to_text`；PhySH 入主题；`stage: vor` |
| 7 SCD | `lookup` 按 DOI 原生；每页 ≤100 |
| 8 合规 | OA 集：文档化 API、robots 404 → `background`；Harvest 与期刊站 ToS 的关系待核（未决 9）；⚑LIC 只约束全量 |
| 9 全文 | CC BY 文章 `oa_link`，其余 `open_in_tab`；平台不调 `accepted_fulltext` |
| 10 测试 | 正常：OA 列表首页（含 `Link` 头）、CC BY 单篇；空：无新文窗口；错误：OA 列表 401（期望 `challenge`）、429；边界：`rel="last"` 末页、修订潮、MathML |
| 11 探针与替补 | `structure`（`Link` 头、`data` 包装、`rights` 结构、`per_page` 上限）、`tos_hash`、Content-Signal 出现；替补 crossref_delegated → `scoap3_api` → `arxiv_oai` |
| 12 运维 | modified 计数突增 10 倍告警 |
| 13 已知坑与待决 | 新文必须用 `published`（修订量约 45 倍）；升 custom_plan：`Link` 头分页不在四种 paginator 内（未决 12）且有两个 scope；robots 注释提到 CF Content-Signal `ai-train=no`，正文未见，待复核 |

### biorxiv_api

| 节 | 内容 |
|---|---|
| 1 身份 | 新写，impl custom_plan；serves `biorxiv`、`medrxiv`（实例参数 `server`） |
| 2 通道与操作 | metadata 补充：`increment`、`lookup`（DOI）；主通道 crossref_delegated（10.64898 + 10.1101，限 posted-content）；fulltext：`locate_fulltext` |
| 3 上游接口事实 | `/details/[server]/[interval]/[cursor]/[format]` 每次 30 条，`/pubs`、`/publisher` 每次 100 条 [https://api.biorxiv.org/, 2026-09-30]；无限速头、API 主机 robots 404 [https://api.biorxiv.org/robots.txt, 2026-09-30]；www 主机 Crawl-delay 7、具名禁 ClaudeBot、curl 等 [https://www.biorxiv.org/robots.txt, 2026-09-30]；2025-12-01 起新前缀 10.64898 [https://connect.biorxiv.org/news/2025/11/18/preprint_dois, 2026-09-30]；medRxiv 出现 `version "0"`、`type "PUBLISHAHEADOFPRINT"` [https://api.biorxiv.org/details/medrxiv/2026-09-28/2026-09-28/0/json, 2026-09-30]；S3 月包不作再分发源 [https://www.biorxiv.org/tdm, 2026-09-30] |
| 4 请求声明 | `details_window`、`pubs_window`、`details_doi`；根 `collection`，`total` 按字符串容错，0 条且无"无结果"消息 → `empty_body`；`self_rate` 1 s；`allowed_hosts` 只有 `api.biorxiv.org` |
| 5 游标与增量 | `date_watermark{field: date, granularity: day}`，重叠 3 天，按 `(doi, version)` 去重；页内偏移只进 `continuation`；整窗完成后推进 |
| 6 映射 | DOI 作品级，`version` → `version_claim{stage: preprint, seq}`；`license` 经 `license_alias`；`published` → 正式版关系；`version`、`type` 为 strict 枚举，异常值只隔离该条（FS-SS-06）并记入 `StructureSignal.unknown_enum_values` 供漂移探针读取，7 天后按 DOI 重查 |
| 7 SCD | `lookup` 按 DOI 原生 |
| 8 合规 | API 主机 robots 404 → `background`；`jatsxml` 在 www 主机，不取；⚑DRIFT |
| 9 全文 | 按逐篇许可 `oa_link` 或经 Europe PMC；no-reuse 只 `open_in_tab` |
| 10 测试 | 正常：两个 server 各一页；空：无新稿日；错误：200 空体；边界：`version "0"`、未知 `type`、新旧前缀各一 |
| 11 探针与替补 | `count`（昨日 `total` 与 Crossref 同日 posted-content 之比）、`structure`（字段集合、每页 30 条、取值集合）；替补 crossref_delegated（`member:54368`）→ Europe PMC |
| 12 运维 | 比值偏离 ±30% 告警 |
| 13 已知坑与待决 | **与长稿不同**：`/details` 已恢复（长稿记 200 空体）；medRxiv 异常值疑为迁移期状态外泄；升 custom_plan：隔离后按 DOI 重查（未决 3） |

### osf_api

| 节 | 内容 |
|---|---|
| 1 身份 | 新写，impl mapper；serves `psyarxiv`（OSF API 补字段）；书面确认前只建 CL0 清单、不实现 |
| 2 通道与操作 | 确认后 metadata 补充 `increment`、`lookup`；主通道始终是 crossref_delegated（10.31234）与经 Europe PMC |
| 3 上游接口事实 | `api.osf.io` robots `Disallow: /` [https://api.osf.io/robots.txt, 2026-09-30]；文档未读到，端点沿用长稿 `/v2/preprints/`、`filter[date_created]`（未核）；源码默认 `non-cookie-auth 100/hour`、`user 10000/day`、`MAX_PAGE_SIZE 100` [https://raw.githubusercontent.com/CenterForOpenScience/osf.io/develop/api/base/settings/defaults.py, 2026-09-30]，生产值未核 |
| 4–7 请求、游标、映射、SCD | 确认前不声明；确认后 `preprints_window`（`auth: deployment/osf_pat`）、`date_watermark{field: date_created}`，版本级 DOI `_vN` → `version_claim{stage: preprint, seq}` |
| 8 合规 | ⚑ROBOTS，HC-31：后台批量须书面确认，按需单篇须先登记 D-049 例外附表 |
| 9 全文 | 不产出（经 OA 链） |
| 10 测试 | 确认后录四类 fixture |
| 11–12 探针、替补、运维 | 确认前零请求；替补 crossref_delegated → Europe PMC |
| 13 已知坑与待决 | 确认拿不到即废止，`psyarxiv` 降为只需登记（E 清单 ④）；`date_modified` 可否过滤未核；implementation-plan 记"停在 CL1 待命"，但 staging 录制本身是真实请求、受 robots 全禁约束，确认前只能用文档示例合成 fixture 达 CL1（未决 13） |

### aea_fulltext_user

| 节 | 内容 |
|---|---|
| 1 身份 | v1_bridge（v1 `aea`），去向解散（主去向加 `v1.parts`，见 v1-bridge）；serves `aea_journals` |
| 2 通道与操作 | 元数据与最新：crossref_delegated（10.1257，按 ISSN）；全文：平台侧 `RENDER_PAGE` 废止，只留用户侧 |
| 3 上游接口事实 | 期刊无 RSS（论坛答复，二手）；pubs.aeaweb.org 为 Atypon 模板，`Crawl-delay: 1`，`*` 禁 `/action`、`/rss`、`/search`（F6 实测 robots，2026-09-30）；长稿 §14.1 记全文域名恒为 CF 挑战 |
| 4–7 请求、游标、映射、SCD | 不声明；用户侧候选并入 `atypon_user` 实例；JEP 钻石 OA 由 Crossref 许可判定 |
| 8–9 合规与全文 | 平台侧 `link_only`；JEP `oa_link`；其余由 `atypon_user` 配方产出 `user_fetch`（单篇显式，D-053、HC-32；本连接器不产出），或 `open_in_tab` |
| 10–12 测试、探针、运维 | v1 fixture 经桥接回放一次后退役；无平台探针与 SLO；替补 `open_in_tab` |
| 13 已知坑与待决 | 去向两说：C 调研"全文转用户侧"与长稿 §14.1"link_only"，待用户侧实测（未决 8） |

### econsoc_fulltext

| 节 | 内容 |
|---|---|
| 1 身份 | v1_bridge（v1 `econsoc`），去向解散；serves `econsoc_journals`（ECMA、TE、QE） |
| 2 通道与操作 | TE、QE → oai_pmh 实例；ECMA → crossref_delegated（10.3982），保持 D-028 分段；ECMA 受限全文 → 用户侧 Wiley 配方 |
| 3 上游接口事实 | TE OAI：earliest 2006-03-02、`deletedRecord no` [https://econtheory.org/ojs/index.php/te/oai?verb=Identify, 2026-09-30]；QE OAI 当日 "certificate has expired" [https://qeconomics.org/ojs/index.php/qe/oai?verb=Identify, 2026-09-30]；econometricsociety.org 对 ClaudeBot、GPTBot 等具名全禁（F6 实测 robots） |
| 4–7 请求、游标、映射、SCD | 不声明；v1 平台侧取 `/doi/{DOI}` 落地页废止；`deletedRecord no` 须季度全量对账；ECMA 按单篇 `license` 分流 |
| 8–9 合规与全文 | econometricsociety.org 零自动化；TE、QE `oa_link`；ECMA 有 CC 许可的 `oa_link`，其余由用户侧配方产出 `user_fetch`（本连接器不产出）或 `open_in_tab` |
| 10–12 测试、探针、运维 | v1 fixture 回放一次后退役；QE TLS 证书探针在 oai_pmh 实例；替补 Crossref 10.3982 |
| 13 已知坑与待决 | **与长稿不同**：QE 证书过期，是否临时未核 |

### nber_site

| 节 | 内容 |
|---|---|
| 1 身份 | v1_bridge（v1 `nber`），去向暂停；serves `nber_wp`、`nber_conferences` |
| 2 通道与操作 | 平台侧与用户侧均暂停（CL0），取得 NBER 书面许可前不排波次（待拍板）；nber.org 全部主机零自动化；元数据经 crossref_delegated（10.3386）与 `repec_redif`（`RePEc:nbr:nberwo`）；RSS 增量暂停；全文只 `open_in_tab` |
| 3 上游接口事实 | T&C 2026-08-01 禁止未经许可以任何 robot、spider 或自动手段访问，并禁 data mining [https://www.nber.org/terms-and-conditions, 2026-09-30]；政策页已无机器人放行条款 [https://nber.org/policies.html, 2026-09-30]；RePEc 系列最新 w35832 [https://ideas.repec.org/s/nbr/nberwo.html, 2026-09-30]；Crossref 10.3386 无摘要、无许可（F6 实测） |
| 4–7 请求、游标、映射、SCD | `endpoints: []`；nber.org、back.nber.org、data.nber.org 不在任何 `allowed_hosts`；摘要与 JEL 从 RePEc 补 |
| 8–9 合规与全文 | ToS 禁自动化 → `link_only`；扩展单篇取回是否冲突待法务（未决 6）；不用匿名每年 3 篇额度（D-014） |
| 10–12 测试、探针、运维 | v1 RSS 解析 fixture 只作 feed 族样本；nber.org 不设任何自动探针（T&C 禁 monitoring，`tos_hash` 也不例外），条款由人工按 `review_every` 复核并记证据；`count` 只看 Crossref 10.3386 周新增（经 crossref_delegated）；替补 Crossref 10.3386 → RePEc |
| 13 已知坑与待决 | **与长稿不同**：长稿"Crossref + RSS 增量"与"18 个月后开放"不再成立（后者未核）；影响 v2-P0 验收口径，列入待拍板 |

**6.2 P1（紧凑卡）**

### assa_program

**1 身份**：serves `assa_meetings`；新写，mapper，W3（V3）。**2 通道与操作**：`enumerate` 程序页 → `presented_at` 事件与 JEL，不产生新版本；全文 `open_in_tab`。**3 上游接口事实**：程序在 aeaweb.org，robots 只禁 GPTBot、Amazonbot [https://www.aeaweb.org/robots.txt, 2026-09-30]；assaweb.org robots 连接失败（未核）；session 带 JEL 与主办学会、论文页有作者与摘要（长稿，未复核）。**5 游标与增量**：`seq{key: meeting_year}` 加每年 `guid_set`。**8 合规**：robots 允许；ToS 未核，CL0 出口前复核；作者上传的 Preview PDF 不取。**10 测试**：程序页、论文页、未发布、session 取消。**11 探针与替补**：`structure`、`canary_query`（session 数对上届 ±30%）；替补人工会议标签。

### ecva_papers

**1 身份**：serves `ecva`；新写，mapper，W3（V5）。**2 通道与操作**：`enumerate`；正式版经 springer_link 的 Crossref；全文 `open_in_tab`。**3 上游接口事实**：`papers.php` 单页只有 2018、2020、2022、2024，ECCV 2026 未上线 [https://www.ecva.net/papers.php, 2026-09-30]；robots 无 `*` 规则 [https://www.ecva.net/robots.txt, 2026-09-30]；许可未声明。**5 游标与增量**：`guid_set`，`list_diff`。**8 合规**：`background`，`self_rate` 5 s。**10 测试**：单页、空、错误、新届出现。**11 探针与替补**：`structure`、`canary_query`；替补 Crossref（LNCS）→ `arxiv_oai`。

### elife_api

**1 身份**：serves `elife`；新写，mapper，W3（V5）。**2 通道与操作**：metadata 主通道 crossref_delegated，latest 为 feed 实例；本连接器补 eLife Assessment（significance 5 级 × strength 6 级）与 reviewed preprint 关系。**3 上游接口事实**（长稿 2026-09-26，未复核）：API `/articles`、`/reviewed-preprints`，API 主机 robots `Disallow: /`；GitHub `elife-article-xml` JATS 语料；全部 CC BY 或 CC0。**5 游标与增量**：确认前用 GitHub 语料 `repo_commit`（传输同未决 2），确认后 API `date_watermark`。**8 合规**：⚑ROBOTS 仅 API（HC-31）。**10 测试**：JATS 一篇、Assessment 各档、空 diff、撤稿通知。**11 探针与替补**：`robots`、`structure`；替补 crossref_delegated → Europe PMC。

### isca_archive_pages

**1 身份**：serves `isca_archive`；新写，mapper，W3（V5）。**2 通道与操作**：补 Crossref 10.21437（无摘要）；全文 `open_in_tab`。**3 上游接口事实**：robots 仍 `Disallow: /interspeech_2026/`、`/tmp/` [https://www.isca-archive.org/robots.txt, 2026-09-30]，禁区按年变化。**5 游标与增量**：`seq{key: year}` 加每年 `guid_set`；被禁年份只收 Crossref。**8 合规**：robots 变松只告警，解禁后重排队须人工评审。**10 测试**：往年年页、被禁年份（期望 `policy_denied/robots`）、空、错误。**11 探针与替补**：`robots`（全文哈希）、`structure`；替补 crossref_delegated。

### nber_conference_pages

**1 身份**：serves `nber_conferences`；去向暂停，同 `nber_site`（T&C 同样约束会议页与议程 [https://www.nber.org/terms-and-conditions, 2026-09-30]）。书面许可前，会议标签由人工维护，`presented_at` 经人工 PR 进注册表；不建端点、不录 fixture、不设自动探针（含 `tos_hash`），条款人工复核。

### plos_search_api

**1 身份**：serves `plos`；新写，mapper，W3（V5）。**2 通道与操作**：`increment`（`publication_date` 日窗）；全文 `oa_link`（CC BY，个别 CC0，摘要 A 类）。**3 上游接口事实**（长稿 2026-09-26，未复核）：Search API（Solr，无 key）10 次/分、300 次/时、7,200 次/日、≤5 并发、≤100 行，超限封 IP；站点 Crawl-delay 30 s；allofplos 全量 XML。**5 游标与增量**：`date_watermark{field: publication_date, granularity: day}`，重叠 2 天。**8 合规**：`background`；`self_rate{basis: documented, min_interval_s: 24, daily_cap: 3600}`，只用文档额度的一半（受时额约束：300 次/时的一半即 150 次/时，间隔 24 s；7 s 会超过时额）。**10 测试**：一页、空日、429（`rate_limited`）、封禁页（`challenge`）、跨页边界。**11 探针与替补**：`count`（日计数 vs Crossref）、`structure`；替补 crossref_delegated。

### pvldb_volumes

**1 身份**：serves `pvldb`；新写，mapper，W3（V5）。**2 通道与操作**：主通道 crossref_delegated（10.14778，摘要 100%）；本连接器从卷页取 vldb.org 的 PDF 链接。**3 上游接口事实**：卷页首次超时、重试后 200 [https://www.vldb.org/pvldb/volumes/19/, 2026-09-30]；robots 本轮未取到（长稿 404）；CC BY-NC-ND 4.0；Crossref link 指向有 CF 的 ACM 镜像（长稿）。**5 游标与增量**：`seq{key: volume}` 加每期 `guid_set`。**8 合规**：⚑COMM，商用开关开启即停共享；只取 vldb.org。**10 测试**：卷页、空期、超时、期内增补。**11 探针与替补**：`robots`（CL0 出口前补取）、`structure`；替补 crossref_delegated。

### usenix_sessions

**1 身份**：serves `usenix`（Security、OSDI、NSDI、FAST）；新写，mapper，W3（V5）。**2 通道与操作**：`enumerate` technical-sessions 页与论文页 `citation_*`；无 DOI，以 dblp key 为锚；全文 `open_in_tab`。**3 上游接口事实**：robots `Crawl-delay: 10`，禁 `/publications/proceedings`、`/search` [https://www.usenix.org/robots.txt, 2026-09-30]；录用即挂 prepub PDF，许可未声明（长稿）。**5 游标与增量**：每届 `guid_set`。**8 合规**：只访问 `/conference/<event>/technical-sessions` 与论文页，`self_rate` 10 s。**10 测试**：会话页、论文页、未公布、prepub 转正式。**11 探针与替补**：`structure`、`canary_query`；替补 `dblp_drops_snapshot`。

### worldbank_dr_api

**1 身份**：serves `worldbank_prwp`；新写，mapper，W3（V3）。**2 通道与操作**：`increment`；全文 `open_in_tab`（许可待核）。**3 上游接口事实**：D&R API v3 `search.worldbank.org/api/v3/wds`，文档未写认证、限速与许可 [https://documents.worldbank.org/en/publication/documents-reports/api, 2026-09-30]；PRWP `total 11388`，`display_title` 带尾随换行、`abstracts` 为 `{cdata!}`、`url` 为 http；按 `last_modified_date` 排序不单调 [https://search.worldbank.org/api/v3/wds?format=json&docty_exact=Policy%20Research%20Working%20Paper&rows=3&sort=last_modified_date&order=desc, 2026-09-30]。**5 游标与增量**：`date_watermark{field: docdt, granularity: day}`，重叠 7 天。**8 合规**：API 主机 robots 404（F6 实测，2026-09-30）→ `background`，`self_rate` 1 s；OKR 不用；许可二手说法为 CC BY-NC 3.0 IGO（未核），以逐篇字段为准，确认前摘要不共享。**10 测试**：一页、空窗、错误、尾随换行与 `cdata!`。**11 探针与替补**：`count`（`total` 周环比）、`structure`；替补 RePEc（句柄未核）。

### ieee_xplore_user

撤销（待拍板确认 `link_only`）：用户侧全文取回违反 HC-27 与注册表 lint 12，不建清单。IEEE 只取元数据（经 crossref_delegated，10.1109，无摘要），全文只外链；依据：key 须人工审批，ToU 限单次查询呈现、禁批量、禁用于 AI 训练 [https://developer.ieee.org/API_Terms_of_Use2, 2026-09-30]。本标题只作矩阵锚点。

## 7. 本族风险、坑与待决

- **静默结构漂移**：HTML 改版常表现为 0 条目或字段错位；靠 required 规则、命中率、`empty: error`、变异 fixture 与 tombstone 纪律兜住。
- **UA 相关拒绝**：CVF 对部分 UA 403；平台 UA 上线前在 staging 实测，被拦即 `challenge`，走替补。
- **新鲜度缺口**：ICML 2026 未上 PMLR、ECCV 2026 未上 ECVA、OpenReview 平台侧停用，最新 CS 会议靠 arXiv 与 dblp 快照；U7 透明说明。
- **上游变化**交计划代理汇总；**未复核事实**（PLOS、eLife、ASSA 论文页、USENIX 许可、PVLDB robots）CL0 出口前逐条复核。

## 怎么验收

- P0 卡 13 节齐全，P1 卡含身份、通道、事实、游标、合规、测试、探针与替补；卡内未写的 `hosts_touched`、`budget`、`late_path`、`window_max`、`migrate_cursor`、`review_every` 由 §6 族默认补足，清单生成的卡片与之一致；`families/site-special.md#<connector_id>` 全部可解析（含已撤销的 `ieee_xplore_user` 墓碑锚点；`cambridge_core_user` 的卡片与锚点在 platform-family）。
- 被 parse 的端点都有 StructureContract 与四类 fixture；FS-SS-01…12 与 CT-01…12 在无网沙箱全过。
- 无 Crawl-delay、无文档限额的主机都有 `self_rate`；`status_overrides` 每行有 fixture，挑战类回放为 `challenge`、重试 0。
- 与 03、08、D-049、D-052、D-053 一致：OpenReview 平台侧无端点；FS-SS-12 所列主机（nber.org 各主机、dblp.org、确认前的 api.osf.io 与 api.elifesciences.org 等）不在任何 `allowed_hosts`；未声明许可的站点不产出 `oa_link`；本族连接器不产出 `user_fetch`。
- 波次与 [implementation-plan](../implementation-plan.md) 一致（`nber_site` 除外：本文按暂停口径不排，见未决 6）：W1 6 个、W2 4 个、W3 11 个（含 `openreview_api`、`aea_fulltext_user`、`econsoc_fulltext` 的用户侧 W3u）、不排 3 个，撤销 2 个、暂停 2 个（`nber_site`、`nber_conference_pages`，均 CL0）。

## 未决事项

1. `self_rate` 族下限（静态页 5 s、无文档 API 1 s）与各卡日顶为设计取值（未核），待拍板。
2. git 仓库（ACL、eLife JATS）经网关的传输：`bulk_transfer` 走 git smart HTTP（含 POST），还是按 commit 下载归档；github.com、api.github.com、raw.githubusercontent.com 的路径级 robots 判定本批未取（未核），CL0 出口前补取，被禁即改用官方 bib.gz 或 Crossref。
3. strict 枚举的记录级隔离与契约"increment 遇非合法结果停在安全点"的关系：本文按"页合法、单条隔离、7 天后按 DOI 重查"写，须契约评审认可。
4. 用户侧元数据查询（OpenReview 本人 token）不在 FulltextRecipe 步骤枚举内：与 [contract](../contract.md#待拍板) 待拍板 P-13（`QueryRecipe`）一并定；契约 v1 不新增协议，拍板前用户侧元数据查询停在 CL0，OpenReview 只给 `open_in_tab`。
5. OpenReview 停用期是否允许匿名 `active_venues` 日 1 次探针；默认不允许。
6. NBER：`nber_site`、`nber_conference_pages` 平台侧与用户侧一律暂停（CL0），取得 NBER 书面许可前不排波次（待拍板）；用户侧扩展单篇取回是否与 T&C 冲突另待法务，此前只给 `open_in_tab`。implementation-plan 的 CN-7 仍把 `nber_site` 列入 W3u 用户侧 11 个，待其按暂停口径改。
7. `cambridge_core_user`、`ieee_xplore_user` 已撤销（待拍板确认 `link_only`；矩阵、implementation-plan 同步）；`cambridge_core_user` 的卡片只在 platform-family，本文不再有其标题；Cambridge 日后是否以 platform-family 用户侧配方恢复待定（其 robots 被挑战，按 RFC 9309 视为全禁）。
8. `aea_fulltext_user` 全文去向：并入 `atypon_user`，还是 `link_only`；[platform-family](platform-family.md) 目前没有 pubs.aeaweb.org 实例行，并入前须补。
9. APS Harvest OA 集与期刊站 ToS 第 5 条的关系是否须书面确认；全量 Harvest 属用户授权（长稿、official-tdm-api）还是平台许可（F3），两说待核。
10. `list_diff` tombstone 的"连续两次"与季度对账频率待 V1 实测校准。
11. `StructureSignal` 与清单字段 `structure_contracts`、`self_rate`、`editions`、`license_rules`、`deletion_semantics`、`challenge_markers` 须契约评审收录。
12. `Link` 头分页（APS）不在四种 paginator 内：加 `link_next`，还是保持升 custom_plan。
13. robots 全禁主机（`osf_api`、`elife_api` 的 API）在书面确认前能否以合成 fixture 达 CL1，还是停在 CL0；与 implementation-plan 的"CL1 待命"口径对齐。
14. 篇幅约 60KB，超出族文档 45KB 目标（§6 卡片约 36KB）；不删信息的压缩须改写卡片表格，或把 P1 紧凑卡与撤销锚点移到附页，属结构调整，待集成代理定。
15. [03](../../03-sources-and-corpus-pipeline.md#连接器九族与执行位置) 把 site_special 定为 platform；表中 `openreview_api`、`econsoc_fulltext`、`nber_site`（mixed）与 `aea_fulltext_user`（user）的用户侧部分须按契约的 `RecipeProvider` 另立清单或并入 platform-family，connector_id 由契约与矩阵统一定（implementation-plan"混合连接器拆分"）。
16. 卡片小节标签形式（P0 用表格行、P1 用 `**1 身份**：`）与其他族不一；按[卡片模板](../connector-card-template.md)，V0 起统一为 `card render` 的输出（目标形式 `**1 身份**：`）；§6 的三级标题只写 connector_id，分组用粗体行。

更细的材料：`git show v2-drafts:docs/plan/v2/03-sources-and-corpus-pipeline.md`（§5.3–5.4、§7.9、§14.1、§15.1、§15.5）；[通用契约](../contract.md)、[一致性与测试](../conformance-and-testing.md)、[来源名录](../../../../catalog/source-directory.md#已知缺口)、[决策日志](../../../decision-log.md)、[路线图 V1](../../09-roadmap-and-milestones.md#v1-语料底座与-p0-来源)。
