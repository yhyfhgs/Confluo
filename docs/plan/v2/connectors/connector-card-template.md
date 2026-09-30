---
title: 连接器卡片模板
status: draft
owner: opus5.5-primary
updated: 2026-09-30
---

# 连接器卡片模板

> 本文回答：每个连接器的卡片写什么、写多细、哪些由清单生成、评审时核什么。结论：卡片固定 13 节，标题是只含 `connector_id` 的三级标题；§1、2、4、5、7、10–12 由 ConnectorManifest 经 `card render` 生成，人只写 §3 上游事实、§8 合规与 §13 已知坑，§6、§9 生成骨架加一句人工说明；P0 写完整卡，P1 写紧凑卡，P2 与登记只占一行。模板中的示例取 `europe_pmc_rest`，数值为示意。

## 要点

- **标题规则**：`### <connector_id>`，标题里不加任何别的文字；一个 `connector_id` 只在一个族文档里有卡片，跨族连接器在主族写卡，另一族只写一行指向。
- **生成为主**：卡片与清单不一致即 lint 失败；人写的三节承载不能机读的判断与证据。
- **三种粒度**：P0 完整 13 节；P1 紧凑卡（§1–3、5、8、10、11 必写，其余合并一段）；P2 与登记一行，注明"按需补卡"。
- **事实带出处**：每条上游事实写 `[URL, 核对日期]`；未核实写"未核"，二手材料写"二手"，两份材料不一致时两说并列并标"待核"。

## 1. 填写说明

- **来源**：先填 `registry/sources/<source_id>.yaml`（SourceSpec）与 `registry/connectors/<connector_id>.yaml`（ConnectorManifest），再运行 `card render` 生成卡片骨架；族实例的参数在 `registry/instances/<family>/<instance>.yaml`。
- **生成节**：§1、2、4、5、7、10、11、12 全部由清单生成，不手改；要改就改清单（§1 波次取自实施计划，§11 替补链与 §12 runbook 链接取自 SourceSpec 与运维文档，同样不手改）。
- **半生成节**：§6 由 `mappers[]` 与标识符注册表生成粒度表，人补一句 Version 依据与权利默认值；§9 由 `operations[]` 生成 FulltextOption 列表，人补一句配方要点。
- **手写节**：§3 上游接口事实、§8 合规、§13 已知坑与待决。§8 只摘要并链接 SourceSpec 证据，不复制证据正文（合规证据只存一处）。
- **运行态不进卡片**：生效等级 `cl_effective`、health、rollout 阶段与急停只在运维控制台看；卡片只写目标与声明等级。
- **伪代码**：卡片里的 YAML 或代码片段一律标"设计伪代码"。
- **节标题**：序号加固定文字（`**1 身份**` … `**13 已知坑与待决**`），文字与顺序不变；推荐加粗段落或列表（`1. **身份**`、`- **1 身份**`），现有族文档也有四级标题写法（`#### 1 身份`），V0 起统一为 `card render` 的输出。唯一的链接目标是三级标题的 `connector_id`，例如矩阵链接 `families/aggregator-api.md#europe_pmc_rest`。

## 2. 完整卡（P0）

复制下面整块，删去尖括号说明，保留字段名。每个字段后的"例"是一行填写示例（`europe_pmc_rest`，示意）。

```markdown
### <connector_id>

**1 身份**
- connector_id / family / kind：<snake_case> / <九族之一> / <platform_connector|recipe_provider>（例：europe_pmc_rest / aggregator_api / platform_connector）
- impl：<instance|declarative|mapper|custom_plan|v1_bridge>，默认最低可行级，上调理由写 §13（例：mapper）
- contract_version / connector_version：<整数> / <semver>（例：1 / 0.1.0）
- conformance：声明 <CL0–CL3|CLX> → 目标 <CL>；严格度 <high|low>（CI 推导）（例：CL0 → CL3，high）
- owner / backup_owner：<人> / <人>，P0 必须两人（例：<维护者甲> / <维护者乙>）
- lifecycle：<active|deprecated|retired>，upstream_sunset <日期|无>（例：active，无）
- serves：<source_id 列表>；venue 范围 <全部|清单>（例：europe_pmc；全部）
- 波次：<W0–W4；用户侧通道记 W3u/W4u>（例：W0 参考连接器）

**2 通道与操作**

| Operation | metadata | latest | fulltext |
|---|---|---|---|
| <enumerate…probe> | <✓/—> | <✓/—> | <✓/—> |

- exec_side：<platform|user>（例：platform；metadata 做 enumerate、lookup、search，latest 做 increment，fulltext 只做 locate_fulltext）

**3 上游接口事实**
- 协议与端点：<…> [URL, 核对日期]（例：REST `search`、`cursorMark` 分页 [https://www.ebi.ac.uk/europepmc/webservices/rest/search, 2026-09-30]）
- 认证：<无|部署级 key（AuthRef deployment/*）|用户 key（只见于 recipe_provider）>（例：无）
- 限速与配额：<数值> [URL, 日期] 或"未核"（例：官方未公布，未核；robots `Crawl-Delay: 10` [https://www.ebi.ac.uk/robots.txt, 2026-09-30]）
- 分页与增量字段：<…>（例：`FIRST_IDATE` 日窗可用；`INDEX_DATE` 命中 0 且不报错，2026-09-30 实测）
- bulk 与快照：<…>（例：有，主机 robots 全禁，⚑ROBOTS（仅 bulk），归 `europe_pmc_bulk`）

**4 请求声明**
- endpoint_id / request_class / method：<…>（例：europe_pmc.search / rest / GET）
- hosts_touched → allowed_hosts：<主机列表>，并集须 ⊆ SourceSpec 通道主机（例：www.ebi.ac.uk）
- 令牌桶五元组：source / host / request_class / 凭证 / 出口 IP（例：europe_pmc / www.ebi.ac.uk / rest / 无凭证 / 由网关分配）
- Expectation：content_types、min_bytes、root、empty、fake_success、legit_status、magic（例：application/json，root `resultList`，empty=legit）
- status_overrides：<状态码 → error_class>，每行配 upstream_facts 与 fixture（例：无，用默认表）
- budget：<account, unit, ceiling, evidence, planned_daily | 无>（例：`epmc.requests` / request / 全平台最小间隔 10 s / robots `Crawl-Delay` / 未定）

**5 游标与增量**
- cursor.kind：<date_watermark|oai_datestamp|guid_set|seq|snapshot_release|repo_commit|window_set>（例：date_watermark，字段 firstIndexDate）
- ordered / ordered_by / ordered_fixture：<true|false> / <字段> / <fixture id>（例：false，整窗完成后推进）
- overlap / granularity / bounds：<…>（例：P2D / 日 / 闭区间）
- lag_bound / late_path / window_max：<证据或未核> / <weekly_index_backfill|snapshot_reconcile|none> / <…>（例：未核 / weekly_index_backfill，bulk 获确认后改 snapshot_reconcile / P1D）
- 重启语义：<从已提交 CursorEnvelope 重新 plan；continuation 不持久化>（例：`cursorMark` 只进 PageSignals）
- 删除与撤稿：<tombstone 来源；status_claims 来源>（例：删除无通知；撤稿看 `pubTypeList`（取值未核）写 status_claims）
- migrate_cursor：<纯函数 | 重置 + 回填窗口 | 首版无>（例：首版无）

**6 映射**
- mapper_id@mapper_version：<…>（例：epmc_json@1）
- identifiers_emitted 与粒度：<方案 → 版本级|作品级>（例：pmid、pmcid、doi、ppr，粒度查标识符注册表）
- source_key_rule / volatile_fields：<…>（例：`source` + `id` / `citedByCount`）
- version_claim 依据：<stage 与 basis>（例：`source=PPR` → preprint）
- 许可与摘要权利：原串 + license_alias；权利经 classify_rights，默认 unknown；许可、权利、版本、关系四类字段带 basis（例：MED 摘要默认 B 类，CC 单篇为 open）

**7 SCD**
- 可下推谓词与支持等级：<native|emulated|none>（例：日期范围 native、DOI 精确 native）
- 排序键 / 分页上限 / 批量上限：<…>（例：无 / 以 cursorMark 为准 / pageSize ≤1000，长稿值，未复核）
- 成本模型：<请求数、美元或无>（例：按请求数）

**8 合规**
- 策略引擎输入：文档化 API、bulk、逐主机 robots、ToS、TDM/AI 保留，各给结论并链接 SourceSpec 证据（例：文档化 API；`www.ebi.ac.uk` robots 不禁 REST；OA 子集以外不得批量下载，二手）
- 各操作上限模式：<Operation → deny|link_only|user_side|on_demand|background>（例：metadata、latest 为 background；交互 lookup、search 待 EBI 约定；非 OA 全文 link_only）
- 闸门标记 / 商用门控 / 所需书面确认：<…>（例：来源闸门 ⚑ROBOTS（仅 bulk）由 `europe_pmc_bulk` 承担，本连接器无闸门 / 未核 / EBI 交互用量约定）

**9 全文**
- FulltextOption：<oa_link|tdm_api|user_fetch|open_in_tab>（例：OA 子集给 oa_link，其余 open_in_tab）
- FulltextRecipe 要点：<占位符只在 request.headers；allowed_host；limits> 或"无"（例：无）

**10 测试**
- fixture：<四类与必备件的 fixture id>（例：core 首页、末页空结果、撤稿记录、工作日零命中负例）
- 契约测试：<CT 规则状态，exempt 附理由与批准人>（例：CT-01…CT-12 done；族套件 FS-AGG-01、FS-AGG-10）
- 黄金 NormRecord：<覆盖的标识符方案与权利类>（例：MED、PMC、PPR 各一）
- 属性测试要点：<…>（例：日窗重叠去重、闭区间边界日）

**11 探针与替补**
- ProbeSpec：<probe_id, kind ∈ robots|tos_hash|tdmrep|structure|deprecation|canary_query|count, target, schedule, expectation, on_fail ∈ alert|freeze_promotion|degrade_endpoint>（例：epmc.silent_zero（canary_query，昨日 FIRST_IDATE 命中 >0）；epmc.structure（structure，version 与字段集合）；epmc.robots（robots））
- 降级处置：<…>（例：静默零即停推水位并告警）
- 替补链：<同能力通道>（例：crossref_delegated → openalex_api → pubmed_eutils（确认后））

**12 运维**
- 新鲜度目标 / SLO / 告警：<…>（例：新鲜度 ≤48 小时，设计值）
- runbook：<链接>；review_every：<P0 月看健康、季复核卡片；P1 季；P2 半年，数值未核（P-12）>（例：P90D）
- 维护点数：<按 impl 计，数值未核>（例：1）

**13 已知坑与待决**
- <与长稿或调研不同之处、impl 上调理由、待拍板项>（例：`INDEX_DATE` 静默返回 0，改用 FIRST_IDATE 并加"静默零"探针）
```

## 3. 紧凑卡与一行

**P1 紧凑卡**：§1、2、3、5、8、10、11 按完整卡写；§4、6、7、9、12、13 合并为一段"其余"，写与族默认不同之处。

```markdown
### <connector_id>

**1 身份**：……

**2 通道与操作**：……

**3 上游接口事实**：……

**5 游标与增量**：……

**8 合规**：……

**10 测试**：……

**11 探针与替补**：……

**其余**：<请求声明、映射、SCD、全文、运维与已知坑中与族默认不同之处；无则写"同族默认">
```

**P2 与登记**：在族文档 §5 的连接器清单总表里占一行（列与总表表头一致），不建卡片标题。

```markdown
| <connector_id> | <服务来源数> | <最高优先级> | <波次> | <exec_side> | <代码量级> | <v1 复用> | <前置依赖> | <当前 CL> → <目标 CL>（按需补卡） |
```

升级为 P1 或 P0 时补卡，并把表格行改成链接到卡片。

## 4. 与 ConnectorManifest、SourceSpec 的对应

| 卡片 | ConnectorManifest | SourceSpec 或其他 |
|---|---|---|
| §1 身份 | `connector_id`、`family`、`kind`、`impl`、`exec_side`、`contract_version`、`connector_version`、`serves`、`conformance.{declared, target}`、`ops.{owner, backup_owner}`、`lifecycle` | 服务来源的 `source_id`；波次见实施计划 |
| §2 通道与操作 | `operations[]`（Operation × channel） | 通道定义与 `exec_side` 一致（lint） |
| §3 上游事实 | `upstream_facts[{fact, url, verified_at, grade, by, probe}]` | — |
| §4 请求声明 | `endpoints[].{endpoint_id, request_class, method, path_template, hosts_touched, auth, paginator, expect, status_overrides, budget}`、`allowed_hosts` | 通道主机集合（`allowed_hosts` ⊆） |
| §5 游标 | `endpoints[].cursor.{kind, schema, ordered, ordered_by, ordered_fixture, bounds, overlap, granularity, lag_bound, late_path, window_max}`；`migrate_cursor` 在代码中 | — |
| §6 映射 | `mappers[{mapper_id, mapper_version, identifiers_emitted}]`、`endpoints[].{source_key_rule, volatile_fields}` | 许可策略；权利由 `classify_rights()` 计算 |
| §7 SCD | 由 `describe()` 生成，带 `derived_from` | SourceSpec 与实例共同输入 |
| §8 合规 | 只按 `source_id` 引用 | robots、ToS、TDMRep、Content-Signal、AI 爬虫规则、许可、商用门控、证据；名录闸门 |
| §9 全文 | `operations[]` 中的 `locate_fulltext`；RecipeProvider 的配方引用 | fulltext 通道 |
| §10 测试 | `fixtures[]`、`fixture_policy`、`conformance.rules` | — |
| §11 探针与替补 | `probes[]` | 替补链（注册表 lint L6） |
| §12 运维 | `ops.{points, review_every, slo}` | runbook 链接 |
| §13 | 手写 | v1_bridge 另列 `v1.{adapter, destiny, mode, port_target, sunset_by, parts}` |

字段全集与类型以 [contract](contract.md) 为准。

## 5. 评审核对清单

1. 标题只含 `connector_id`，全库唯一；跨族连接器另一族只有一行指向。
2. `card render` 重生成无差异；生成节没有手改。
3. §3 每条事实有 `[URL, 核对日期]` 或"未核"；与调研或长稿不一致处两说并列，并写进 §13。
4. §4 `hosts_touched` 并集等于 `allowed_hosts`，且 ⊆ SourceSpec 通道主机；请求声明里没有 UA、Cookie、凭证头与 `personal_params`。
5. §5 水位类游标的 `overlap`、`granularity`、`bounds`、`lag_bound`、`late_path`、`window_max` 齐全；游标编码变更配 `migrate_cursor` 或"重置 + 回填"。
6. §6 权利默认 `unknown`；mapper 不直接给 `shareable`；Version 声明有 basis。
7. §8 逐操作写出上限模式；闸门与[支持名录](../../../catalog/source-directory.md)一致；放宽类上游变化只写"待评审"，不自动放宽。
8. §9 平台不代取受限全文；配方占位符只在 `request.headers`。
9. §10 覆盖四类 fixture 与必备件；每条 `exempt` 有理由与批准人（[一致性规范](conformance-and-testing.md)）。
10. §11 每条 `upstream_facts` 有探针；P0 有替补链。
11. §12 P0 有两名维护人；`review_every` 已填。
12. §13 写明 `impl` 上调理由与待拍板项。

## 怎么验收

- 九篇族文档的卡片都用本模板：P0 完整 13 节，P1 紧凑卡，P2 与登记一行；[连接器矩阵](../../../catalog/connector-matrix.md)的锚点链接全部能解析。
- V0 起，`card render` 生成的卡片与仓库一致，lint 校验生成节与清单相同。

## 未决事项

- 生成节与手写节的划分沿用契约评审团裁定；§6、§9 的"半生成"是本文补充。
- 维护点数与复核节奏数值未核（P-12）。
- `card render`、`scaffold` 等命令名由 V0 冻结；§1 波次、§11 替补链、§12 runbook 不在 ConnectorManifest 内，渲染时的取数来源随之确定。
- 族文档现有加粗段落、列表与四级标题三种节标题写法，§5 总表的列也不一（如 aggregator-api 无"v1 复用"、site-special 无"当前 CL"），V0 起以 `card render` 输出与上面九列统一。
- 样例数值取自 [aggregator-api](families/aggregator-api.md#europe_pmc_rest) 的 `europe_pmc_rest` 卡；[contract](contract.md) 清单示例的 `source_key_rule`（`$.id`）与 `late_path`（取 bulk 确认后的 `snapshot_reconcile`）与之不同，以族卡片为准。

---

更细的材料：[contract](contract.md)、[一致性与测试规范](conformance-and-testing.md)、[README](README.md)；v1 设计模板 `git show archive/v1:docs/design/adapters/README.md`；长稿 `git show v2-drafts:docs/plan/v2/03-sources-and-corpus-pipeline.md`（§3 SourceSpec、§4 SCD、§5 协议、§13 SOP）。
