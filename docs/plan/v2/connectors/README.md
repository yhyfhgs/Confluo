---
title: 连接器工作总览
status: draft
owner: opus5.5-primary
updated: 2026-09-30
---

# 连接器工作总览

> 本文回答：v2 的连接器按什么接口写、怎样证明合格、先写哪些、界面上怎样呈现，以及哪些事要你拍板。结论：把长稿 03 §5.2 的"非接口冻结"协议补全并冻结为 ConnectorContract v1；用一致性等级 CL0–CL3/CLX 管上线与降级；按波次 W0–W4 随里程碑推进；界面不新增一级入口，只在 07 的信息架构上做增量。全部为 draft，你评审后才成为实现依据；与 03、05、08 或 ADR 草案有冲突之处一律列在"待你拍板"，不直接改写原结论。

## 要点

1. **连接器是纯函数加生成器**：只声明 `RequestSpec`、解析响应、映射 `NormRecord`；不发 HTTP、不持凭证、不写审计，执行器驱动、出站网关执行。
2. **三层声明分工**：`SourceSpec` 管来源与合规证据，`ConnectorManifest` 管技术事实与能力，`ConnectorInstance` 管零代码实例；证据只存一处。
3. **违规写法在三层都不成立**：类型上没有 UA、Cookie、robots 字段，`AuthRef` 只有 `deployment/*`；CI 有依赖禁表、6 条连接器 lint 与无网沙箱；网关对未声明主机即拒、robots 先行、挑战即冷却。
4. **策略两次判定**：任务准入判一次，网关逐请求复核 `decision_id + inputs_epoch`；规则变化时在页边界停，游标不越过已提交页。
5. **游标类型化**（`CursorEnvelope`，七种 kind），只在安全提交点原子推进；上游删除不等于撤稿；易变字段不入哈希。
6. **15 个 `error_class`**（长稿 13 个加 `cursor_expired`、`disabled`）各有唯一判定者与处置；合规拒绝与运维停用分开记账。
7. **代码阶梯** `instance < declarative < mapper < custom_plan < v1_bridge`，默认取最低级；声明式只管请求形状，映射永远是带版本的代码。
8. **CL0–CL3 是会过期的证明**：每级有进入门与保持条件，失效自动下调，晋级只经 PR；第二人合规复核在 CL0 出口完成。
9. **fixture 只经 staging 网关录制并脱敏**，受版权正文不入库。
10. **健康与策略模式分离**，合成 `EffectiveStatus`，是路由与界面 U1、U7、O1 的唯一状态来源。

## 三个问题的入口

- **计划怎样丰富完善**：本文"要点"与"待你拍板"给结论与决定项；[implementation-plan](implementation-plan.md) 给波次、人日、依赖、风险与决策门；[09](../09-roadmap-and-milestones.md) 各里程碑已补"连接器工作流"的交付与出口。
- **各来源的接口怎样撰写与标准化**：接口本体在 [contract](contract.md)；合格标准与"写一个新连接器的步骤"（脚手架 → 登记与卡片 → 合规签核 → dry-run 录制 → 族套件 → 评审门 → 晋级）在 [conformance-and-testing](conformance-and-testing.md)；卡片格式在 [connector-card-template](connector-card-template.md)；逐族规范与逐连接器卡片在 `families/`；逐来源对应在[矩阵](../../../catalog/connector-matrix.md)。
- **接口相关的增量 UI**：设计在 [connector-ui](connector-ui.md)，可交互 [demo](../demo/connector-ui-demo.html)。

## 文档地图

| 文档 | 内容 | status |
|---|---|---|
| [README.md](README.md) | 本文：总览、关系、ADR 草案、待拍板 | draft |
| [contract.md](contract.md) | 连接器接口契约 v1：三层声明、核心类型、判定点、执行模型、游标、错误矩阵、映射、配方、审计与版本 | draft |
| [conformance-and-testing.md](conformance-and-testing.md) | 一致性等级 CL0–CL3/CLX、测试分层、12 条通用契约测试、fixture 政策、写一个新连接器的步骤、DoD 与评审门、CI 门禁 | draft |
| [connector-card-template.md](connector-card-template.md) | 卡片 13 节模板（逐字段附示例）、填写说明与核对清单 | draft |
| [implementation-plan.md](implementation-plan.md) | 波次 W0–W4、工作量、依赖与外部确认、分工、风险与上游变化、决策门 | draft |
| [connector-ui.md](connector-ui.md) | 接口相关增量 UI：用户面 U1–U7、运维面 O1–O7 | draft |
| [families/aggregator-api.md](families/aggregator-api.md) | 聚合器与学科库的文档化 API（OpenAlex、Europe PMC、INSPIRE 等） | draft |
| [families/oai-pmh.md](families/oai-pmh.md) | OAI-PMH 族引擎与实例（arXiv、PMC、EconStor 等） | draft |
| [families/feed.md](families/feed.md) | RSS、Atom、eTOC；多数只作新鲜度信号 | draft |
| [families/crossref-delegated.md](families/crossref-delegated.md) | 经 Crossref（或 DataCite）委托的期刊、WP 与预印本前缀 | draft |
| [families/bulk-snapshot.md](families/bulk-snapshot.md) | 官方快照与年度文件导入 | draft |
| [families/platform-family.md](families/platform-family.md) | 托管平台用户侧配方与仓储软件、OJS 实例 | draft |
| [families/official-tdm-api.md](families/official-tdm-api.md) | 用户本人 key 的出版商全文或 TDM API | draft |
| [families/site-special.md](families/site-special.md) | 有官方 API 或结构化页面的专站 | draft |
| [families/v1-bridge.md](families/v1-bridge.md) | v1 的 20 个生产 adapter 的包装、去向与退役时限 | draft |
| [connector-matrix.md](../../../catalog/connector-matrix.md) | 来源 × 连接器矩阵：169 个非排除来源逐行，18 个不接入来源简表 | draft |
| [connector-ui-demo.html](../demo/connector-ui-demo.html) | 增量 UI 的交互 demo（用户视图与运维视图，数据为示意） | — |

## 与现有设计的关系

- **[03](../03-sources-and-corpus-pipeline.md)**：本目录细化其"连接器九族与执行位置"与"新增来源 SOP 与成本目标"，不改结论。SOP 的合规、技术、上线三道门分别对应 CL0 出口、CL1→CL2、CL2→CL3；SOP D 的 ≤2 人日只计到 CL1 加卡片。
- **[02](../02-architecture.md) 与 [08](../08-compliance-security-privacy.md)**：出站网关、判定顺序与 HC-01 起的硬约束全部继承；平台侧不持用户凭证，PWA 也不收任何出版商、机构凭证或个人 key。
- **[05](../05-data-platform.md)**：`fetch_log`、`policy_snapshot`、`watch_key`、`norm_record` 的 DDL 以 05 长稿为准；契约需要的改动（P-1、P-3、P-9、P-10，以及 FetchLog 增列与 `policy_snapshot` 增 `engine_version`、`inputs_epoch`）列在待拍板第 8、9 条。
- **[07](../07-frontend-interaction.md)**：[connector-ui](connector-ui.md) 是 07 的增量，不新增一级 Tab；D-041 接受后随 07 转 approved。
- **[09](../09-roadmap-and-milestones.md)**：W0 对应 V0，W1、W2 对应 V1 前后半，W3 分 V3、V5 两批，W4 在 V5 以后；各里程碑的连接器交付与出口见 [implementation-plan](implementation-plan.md)。
- **名录**：[支持名录](../../../catalog/source-directory.md)的 `v2_status` 决定 CL 目标（P0 平台侧 V1 出口达 CL3，书面确认等闸门未开的停在 CL1 待命，用户侧 V3 出口；P1 按实施计划分 V3、V5 两批；P2 按需 CL2 以上）；[支持分级](../../../catalog/source-taxonomy.md#支持分级)为"登记"的来源停在 CL0。逐行对应见[矩阵](../../../catalog/connector-matrix.md)。
- **ADR**：D-074、D-075 补充 D-046（九族与 SourceSpec v2）、D-055（出站网关）与 D-073（支持分级），不取代它们；D-074 另细化 D-053、D-054 的类型约束；D-076 补充 D-041、D-053、D-054。

## ADR 草案

登记在 [ADR 登记](../../decision-log.md)，均为 proposed。

- **D-074 连接器接口契约 v1**：`PlatformConnector` 与 `RecipeProvider` 两种协议，`plan` 生成器回送 `Step`；Manifest 与 SourceSpec、Instance 分离；三个版本号；七种类型化游标；15 个 `error_class`；策略双判定取代全局 `policy_version`；新增 `traffic_class`；平台不向端侧下发代码；v1_bridge 过渡条款（经网关垫片发请求，V2 出口前移植或退役）。
- **D-075 一致性等级与上线门**：CL0–CL3/CLX 附进入门与保持条件，CL 同时是策略上限；12 条通用契约测试与族套件；四类 fixture 政策；DoD 与三道评审门，第二人复核前移到 CL0 出口。
- **D-076 接口相关增量 UI**：用户面"来源""我的连接"、可得性说明与取回回执；运维面控制台 O1–O7；凭证只在浏览器扩展或 pc-agent，PWA 不收凭证；降级透明，恢复双人。

## 待你拍板

涉及名录状态的只作为复勘建议，本批不改[支持名录](../../../catalog/source-directory.md)。括号里的 P-n 沿用评审团编号，P-1…P-10 与本批追加的 P-13 见 [contract](contract.md#待拍板)，P-11、P-12 见 [conformance-and-testing](conformance-and-testing.md#未决事项)。

1. **NBER 零自动化**：nber.org 条款 2026-08-01 起禁止未经许可的自动访问与数据挖掘，建议全部主机零请求，元数据经 Crossref 10.3386 与 RePEc，RSS 增量暂停。影响：`nber_wp` 的 v2-P0 验收口径与 `nber_conferences`（v2-P1）的会议标签，是否发函求许可。
2. **ORCID 只用年度 CC0 文件**：Public API 凭证发给个人、禁持续轮询，`pub.orcid.org` robots 全禁。影响：P1 通道从 API 改为 bulk，用户 OAuth 只在用户侧。
3. **RePEc、HAL 补 ⚑COMM**：RePEc 数据默认非商用，HAL 的 OAI 条款写明不得商用。影响：商用开关打开时连带停用经 RePEc 代收的来源与 HAL 实例。
4. **"支持"却无连接器的 5 行**：`wfa_meeting`、`sfs_cavalcade`、`efa_meeting`、`ssoar`、`fatcat_ia_scholar`，降为登记或补连接器。影响：支持口径与名录计数。
5. **登记来源不运行连接器**：停在 CL0、通道全部不启用；证据过期只标 `review_overdue`，lint 的证据时效规则只对"支持"生效。影响：细化 D-073，减少复核负担。
6. **CL2 的生产口径**（P-4）：限 `on_demand` 或改为 deny；另议已达 CL3 的族引擎新增实例在 staging 跑 ≥3 天（P-11）。影响：P2 来源能否按需上线、零代码实例的上线时长。
7. **v1_bridge 退役时限**：平台侧桥接在 V2 出口前移植到对应族或退役，过 `sunset_by` 自动降 CL2；转用户侧与暂停的 adapter 不在平台运行 v1 代码，用户侧部分随 W3 改写为配方；第三方客户端库（openreview-py、metapub 等）只用解析部分（P-2）。影响：W2 工作量与 V2 出口。
8. **05 DDL 增补**：`ops.fetch_log.request_class` 改名 `traffic_class`（P-1）；`ops.watch_key` 加 `rev` 并新增按 `scope_key` 的进度表（P-3）；`mapper_version` 存为 `"<mapper_id>@<n>"`（P-9）。评审团清单未编号的两处：契约 §12 的 FetchLog 比 05 `ops.fetch_log` 多出 `inputs_epoch`、`params_digest`、`robots_verdict`、`robots_snapshot_sha`、`ua_version`、`egress_ip_id` 等列；§4 的网关复核要求 `ops.policy_snapshot` 带 `engine_version`、`inputs_epoch`，并按 (source, channel) 维护 `inputs_epoch` 计数。影响：V0 的迁移脚本。
9. **mapper 升级后的旧记录**（P-10）：载荷与 `norm_record` 按留存期回收后无法重算，选 LOOKUP 重取或接受混合版本并在 `provenance` 标注。影响：映射修复能覆盖多少存量。
10. **权利标签对照**（P-5）：`rights_class` M1–M25 与来源七类 M1/M2 撞名，03 的 `abstract_rights` 与 08 的展示字段缺对照表。影响：契约只引用、不定义，须 08 统一。
11. **用户侧护栏、凭证分类与元数据查询协议**：端侧日上限按平台还是按域计数（P-6）；配方维护者用本人凭证做合成检查须 08 认可（P-7）；personal 部署里同一把 S2 或 OpenAlex key 的归类（P-8）；契约 v1 只有 `PlatformConnector` 与 `RecipeProvider`（只产 `FulltextRecipe`），不新增用户侧元数据查询协议：`nasa_ads_api`、`orcid_api`、`lens_api`、`alphaxiv_mcp` 与 `openreview_api` 用户侧（本人 token 查询）在 v1 停在 CL0，实施计划只保留波次占位（W3u、W4u），是否在契约 v1.x 增加 `QueryRecipe` 待拍板（P-13）。影响：V3 扩展与 pc-agent 的护栏与范围，V3 批次一的 CL3 计数。
12. **工作量口径**：[实施计划](implementation-plan.md#未决事项)估连接器工作排期部分约 156 人日（含框架与晋级卡，不含停在 CL0 的 7.5），比长稿对应任务卡的 68 人日多约 88，数值以实施计划为准；维护点数与复核节奏未核（P-12）。影响：09 的人日与排期（V0 由 62 变 84、V1 由 125 变约 138.5），建议 V0 出口按实测吞吐重估。

## 上游重大变化速览

均为 2026-09-30 实测或一手文档；处置与完整清单见 [implementation-plan](implementation-plan.md#上游变化风险) 的风险表与各族卡片"已知坑与待决"。

- **NBER**：条款禁止未经许可的一切自动访问 [https://www.nber.org/terms-and-conditions, 2026-09-30]；处置见待你拍板第 1 条。
- **arXiv**：`export.arxiv.org` robots 全禁、`arxiv.org` 禁 `/api`，OAI 主机 robots 为 404 [https://export.arxiv.org/robots.txt, 2026-09-30]；平台侧只用 OAI-PMH，SCD 不声明检索。
- **OpenAlex**：`from_created_date` 过滤返回 429 "Plan upgrade required"，`per_page` 上限 100 [https://api.openalex.org/works?filter=from_created_date:2026-09-28&per_page=1&select=id, 2026-09-30]；增量改靠季度快照、`updated_date` 分区与 Crossref 兜底，API 只做 lookup 并进美元预算。
- **PMC**：OA Web Service 2026-08-25 下线，旧 FTP 已删 [https://pmc.ncbi.nlm.nih.gov/tools/oa-service/, 2026-09-30]；改用 S3 `pmc-oa-opendata`、OAI-PMH 与 BioC。
- **Europe PMC**：`INDEX_DATE` 增量静默返回 0、不报错 [`https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=INDEX_DATE:[2026-09-28 TO 2026-09-29]&resultType=idlist&pageSize=1`, 2026-09-30]；只用 `FIRST_IDATE` 日窗，加"静默零"探针。
- **OpenReview**：匿名 `/notes` 返回 403 `ChallengeRequiredError` [https://api2.openreview.net/notes?invitation=ICLR.cc/2026/Conference/-/Submission&limit=1, 2026-09-30]；归 `challenge`，平台侧继续停用，用户 token 不经平台服务器。
- **Crossref**：按单条、列表分池并按 mailto 限流；分池起始日两说：2025-12-01 [https://crossref.org/blog/announcing-changes-to-rest-api-rate-limits/, 2026-09-30] 与 2026-07-21 [https://community.crossref.org/t/refining-rest-api-limits-for-improved-stability-and-reliability/16137, 2026-09-30]，待核。令牌桶的凭证维含部署 mailto，全平台集中限速。
- **bioRxiv / medRxiv**：2025-12-01 起新 DOI 前缀 10.64898，与 10.1101 并存 [https://connect.biorxiv.org/news/2025/11/18/preprint_dois, 2026-09-30]；两个前缀都登记，加 schema 漂移探针。

放宽类变化（如 IACR、ACS 的 robots）只提"待评审"，闸门只降不升。

## 怎么验收

- **文档**：本目录与矩阵的 frontmatter 齐全，相对链接无断链，[INDEX](../../../INDEX.md) 已登记；各篇命名与 [contract](contract.md) 一致（15 个 `error_class`、CL0–CL3/CLX、W0–W4 与用户侧 W3u/W4u、卡片 13 节）。
- **评审**：你确认 D-074…D-076 与上面的待拍板项后，contract 与 conformance-and-testing 转 review、approved，才作为 V0 的实现依据。
- **V0 出口**：注册表 13 条 lint 与 6 条连接器 lint 阻断合并；三个参考连接器（`crossref_delegated`、`arxiv_oai`、`europe_pmc_rest`）连同前置件 `crossref_rest`、`oai_pmh` 达 CL1，并经 staging 网关各跑通一次。
- **V1、V3、V5 出口**：`v2-P0` 平台侧通道达 CL3（V1），受书面确认、传输方式或 ADR 闸门的以"CL1 且通道为 deny 或 link_only"计待命达标（`zbmath_open_api` 确认前 CL0）；用户侧通道达 CL3（V3；待 P-13 的停 CL0，`nber_site` 暂停），具名禁止 AI 爬虫的站点在法务结论前只给"在出版社打开"；P1 两批分别在 V3、V5 出口达 CL3。逐项出口条件见 [implementation-plan](implementation-plan.md#里程碑对应表) 与 [conformance-and-testing](conformance-and-testing.md)。

## 未决事项

- 连接器清单：第一阶段 89 个（族核心 4、新写 65、v1 桥接 20），[矩阵](../../../catalog/connector-matrix.md)与实施计划撤销 `ieee_xplore_user`（HC-27、lint 12）与 `cambridge_core_user`（全文改外链）后在册 87 个，再暂停 `nber_site`、`nber_conference_pages`，余 85 个（80 个排入 W0–W4，5 个只服务登记来源、停在 CL0；用户侧通道的波次记作 W3u/W4u）；`nasa_ads_api`、`orcid_api`、`lens_api`、`alphaxiv_mcp` 与 `openreview_api` 用户侧保留波次占位但在契约 v1 停在 CL0（P-13）。`cambridge_core_user` 日后是否以 platform_family 用户侧配方恢复，待拍板；按裁定其卡片只留在 [platform-family](families/platform-family.md#cambridge_core_user)（写明撤销、建议 `link_only`），[site-special](families/site-special.md) 总表只留一行指向，`ieee_xplore_user` 在 site-special 只留墓碑说明。
- P1 时点：框架原定 `v2-P1` 在 V2–V3 达 CL3，实施计划、矩阵与 [conformance-and-testing](conformance-and-testing.md) 已按 09 改为 V3、V5 两批，请评审时确认。
- 篇幅：[contract](contract.md) 约 55KB，也超出 45KB 上限，[connector-ui](connector-ui.md) 与 [conformance-and-testing](conformance-and-testing.md) 略超设计类 ≤25KB 目标，[site-special](families/site-special.md) 等族文档与矩阵超出 45KB 上限；本轮接受，各篇"未决事项"注明实现期拆附录，不删规则。
- 人日、维护点数、staging 天数多为估计，未核，实现期校准。
- 上游事实两说并列之处（Crossref 分池日期、`/members` 路由归哪个池）待核，未择一。
- 本批不改支持名录、05 与 08；需要改动的都在"待你拍板"。
- 本批文档经 PR 合入 main，状态仍为 draft，待你逐篇评审。

---

更细的材料：`git show v2-drafts:docs/plan/v2/03-sources-and-corpus-pipeline.md`（§5、§10.2–10.8、§12.4、§15）；工作过程见 [session-018](../../../logs/2026-09-30-session-018.md)。
