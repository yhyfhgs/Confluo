---
title: 连接器实施计划
status: draft
owner: opus5.5-primary
updated: 2026-09-30
---

# 连接器实施计划

> 本文回答：[契约](contract.md)与[一致性等级](conformance-and-testing.md)定稿后，连接器按什么顺序、在哪个里程碑、花多少人日、怎么并行、做到哪一级 CL，哪些外部确认挡路。结论：分五个波次，W0 在 V0 用三个参考连接器打通全链，W1、W2 在 V1 把 P0 平台侧做到 CL3，W3 在 V3、V5 两批交付用户侧通道与 P1，W4 在 V5 以后按需升级。逐连接器粗估 125.5 人日（含不排期的 CL0 7.5 与 `nber_site` 预留 1.5），加框架卡、晋级卡与 V1-T4、T5 余项后排期部分约 156 人日，比长稿对应任务卡的 68 人日多约 88，列入未决事项。

## 要点

- **清单**：以第一阶段来源清单的 89 个连接器为准（族核心 4、新写 65、v1 桥接 20）。与矩阵一致撤销 `ieee_xplore_user`、`cambridge_core_user`（理由见波次归属调整），在册 87 个；再暂停 `nber_site`、`nber_conference_pages`（NBER 书面许可前平台侧与用户侧都不排波次），余 85 个：80 个排入 W0–W4，5 个停在 CL0 不排波次；`nber_site` 另留 1.5 人日预算，许可前不开工。
- **波次**：W0 5 个 10.0 人日，W1 13 个 20.0，W2 16 个 21.0，W3 34 个 47.5（平台侧 24 分 V3、V5 两批，用户侧 W3u 10；另 `nber_site` 预留 1.5），W4 12 个 18.0（平台侧 10，用户侧 W4u 2）；只服务登记来源的 5 个停在 CL0（7.5），不排波次。用户侧通道的波次记作 W3u/W4u（依赖 V3 的扩展或 pc-agent），与[矩阵](../../../catalog/connector-matrix.md)同一记法。
- **出口用 CL 表述**：P0 平台侧 V1 出口达 CL3，闸门未开的停在 CL1 待命；用户侧 P0 通道 V3 出口达 CL3，或按法务结论只给外链；P1 两批分别在 V3、V5 出口达 CL3；P2 按需 CL2 以上。
- **关键路径**：V0 发函 → W0 参考连接器 CL1 → W1、W2 在 staging 连续 14 天 → V1 出口；W2 须在 V1 第 5 周前达 CL1。
- **v1 复用**：20 个桥接 23.0 人日，按 SOP D 上限重写要 40，约省 17。去向按 [v1-bridge 族](families/v1-bridge.md) §1.1 的六值：`platform_bridge` 7（唯一在生产跑 v1 代码，V2 出口前移植，见 CN-6），`family_config` 5，`snapshot_rewrite` 1（`dblp_drops_snapshot`），`user_side` 5，`paused` 2（`openreview_api`、`nber_site` 的平台部分），`retired` 0（部分废止写在 `v1.parts`）。
- **对账**：V0–V1 连接器工作 77.5 人日对长稿 42；全程 155.75 对 68。不改 09 的数字，差额进未决事项。

## 口径与前提

- 清单与粗估取自第一阶段来源清单：新写按 [03 SOP D](../03-sources-and-corpus-pipeline.md#新增来源-sop-与成本目标) 取 1–2 人日，桥接 0.5–2，族核心 1.5–3（未核）。逐源事实见[连接器矩阵](../../../catalog/connector-matrix.md)与各族文档。
- SOP D 的 ≤2 人日只算到 CL1 加卡片；CL2 的 staging 天数按日历另计；CL3 所需 runbook、SLO、告警与演练另立晋级包 CN-8。
- CL 进入门、保持条件与三道门 G1 合规（CL0 出口，第二人复核）、G2 技术（CL1 → CL2）、G3 上线（CL2 → CL3）见 [conformance-and-testing](conformance-and-testing.md)。人日口径同 [09](../09-roadmap-and-milestones.md)。

## 波次 W0–W4

用户侧通道（`exec_side: user`）的波次记作 W3u/W4u：构建排在 W3、W4，但依赖 V3 的浏览器扩展或 pc-agent；矩阵按来源行标 W3u/W4u，本文按连接器计入 W3、W4 的个数（W3 34 = 平台侧 24 + W3u 10，`nber_site` 只留预算不计入；W4 12 = 平台侧 10 + W4u 2）。

### W0 契约与参考连接器（V0）

- 目标：冻结契约 v1，立起 SDK、一致性套件与 fixture 工具，用参考连接器走通"SourceSpec → Manifest → plan → 网关 → parse → normalize → 卡片"。
- 范围：参考连接器 `crossref_delegated`、`arxiv_oai`、`europe_pmc_rest`；前置件 `crossref_rest`、`oai_pmh`（引擎最小集，`arxiv_oai` 是首个实例）。覆盖三族、两种游标 kind（`date_watermark`、`oai_datestamp`）与三种续取令牌（Crossref cursor、OAI resumptionToken、`cursorMark`，只进 `PageSignals.continuation`，不持久化）。
- 前置：D-074、D-075 裁决；V0-T7 注册表 schema、V0-T9 策略引擎骨架、V0-T10 网关骨架（record 模式由 CN-3 补上）、V0-T3 发函。
- 产出：CN-1…CN-4；5 张完整卡片；参考连接器走查记录，作同族样板。
- 出口：5 个达 CL1；每个在 staging 经网关完成一次小额度 dry-run，FetchLog 带 `decision_id`，robots 判定先于首个请求；卡片由 manifest 生成且与 lint 一致。
- 估算：连接器 10.0 + 框架 12（CN-1 3、CN-2 5、CN-3 4）= 22 人日。CN-2 待 CN-1 的 schema 定稿即开工，与其 lint 部分并行；三个参考连接器在 CN-2 可用后并行，CL1 验收等 CN-3。

### W1 P0 元数据与最新论文（V1 前半）

- 目标：P0 平台侧族引擎与高价值专用连接器达 CL1，尽早进入 staging 计天。
- 范围（13 个）：`feed`；aggregator_api `inspire_rest`、`zbmath_open_api`、`dblp_sparql`、`hf_papers_api`、`pmc_bioc`、`pubmed_eutils`；site_special `biorxiv_api`（兼 medrxiv）、`aps_harvest`、`jmlr_volumes`、`tmlr_list`、`ijcai_proceedings_pages`、`osf_api`。另做 P0 零代码登记与配置（nature_portfolio、pnas 的 feed，medrxiv 复用 `biorxiv_api`）。
- 前置：W0 出口；V1-T1 网关礼貌、V1-T2 策略接入、V1-T8 调度与游标。
- 出口：12 个达 CL1，`zbmath_open_api` 在 FIZ 书面确认前录不到 fixture、停在 CL0；无闸门的 9 个（含 `pmc_bioc`，其卡片不声明 E-utilities）在 V1 第 3 周前进入 CL2 计天，V1 出口达 CL3。`pubmed_eutils`、`osf_api` 受 ⚑ROBOTS（以合成 fixture 做到 CL1，口径见 site-special 未决 13），`dblp_sparql` 待 D-050 核验，都停在 CL1 待命，通道保持 deny 或 link_only；`aps_harvest` 只做 OA 子集。
- 估算：20.0 人日；按族分两条泳道，并行规则见分工与并行。

### W2 快照、桥接与其余 P0（V1 后半）

- 目标：导入底座快照，把 v1 平台侧 adapter 包进契约，补齐 P0 替补链。
- 范围（16 个）：bulk_snapshot `crossref_annual_file`、`openalex_snapshot`、`pmc_s3`、`europe_pmc_bulk`、`pubmed_baseline`、`zbmath_kg_dump`、`dblp_drops_snapshot`、`repec_redif`；桥接 `acl_anthology_xml`、`aaai_ojs_oai`、`pmlr_volumes`、`cvf_open_access_pages`、`neurips_proceedings_pages`、`openalex_api`、`ssrn_crossref`、`unpaywall_api`。
- 前置：W0 出口；V1-T4 余项（桥接垫片）；`repec_redif` 先扩 ReDIF handle 映射，其 rsync/FTP 经网关的传输方式待拍板（见 v1-bridge 族）；`openalex_api` 接美元预算（V1-T18）。
- 出口：16 个最晚 V1 第 5 周达 CL1；无闸门的 11 个在 V1 出口达 CL3；`dblp_drops_snapshot` 待 D-050 解除 D-037 出列，之前停在 CL1 待命；`crossref_annual_file`（S3 请求方付费）、`repec_redif`（rsync/FTP）在 bulk-snapshot 待拍板 1 通过前停在 CL1 待命；`openalex_snapshot` 完成兴趣并集子集导入（09 的 V1 出口条件）；`europe_pmc_bulk`、`pubmed_baseline` 停在 CL1 待命；每个桥接写明 `v1.destiny` 与 `sunset_by`（≤ V2 出口）。
- 估算：21.0 人日，另 CN-8 在 V1 8.5 人日。快照导入受发布节奏与磁盘约束，一条泳道串行；桥接卡互不依赖，可全并行。

### W3 用户侧与 P1（V3 批次一，V5 批次二）

- 批次一（V3，24 个，35.5 人日；另 `nber_site` 预留 1.5）：
  - 用户侧 CN-7（10 个，另 `nber_site` 预留，合计 16.5）：`atypon_user`、`silverchair_user`、`elsevier_tdm`、`wiley_tdm`、`springer_nature_api` 5 个 RecipeProvider 达 CL3；`aea_fulltext_user`、`econsoc_fulltext` 按 [site-special 卡](families/site-special.md)解散（桥接 V2 出口转 CLX），工作量用于把用户侧并入承接配方，其通道随承接配方达 CL3（矩阵按通道记 CL3）；`openreview_api`（用户侧为本人 token 查询，D-052）、`nasa_ads_api`、`orcid_api` 是用户侧元数据查询，契约 v1 没有对应协议：只保留 W3u 占位、只做清单与卡片、停在 CL0，是否增加 `QueryRecipe` 待拍板 P-13。混合执行的只做用户侧部分。`nber_site` 按 [site-special 卡](families/site-special.md#nber_site)去向暂停；用户侧取回待法务与 NBER 许可，1.5 人日暂列，否决即转 CLX。
  - P1 平台侧（V3-T15 扩大，14 个，20.5）：`worldbank_dr_api`、`econbiz_api`、`assa_program`、`opencitations_api`、`opencitations_dump`、`doaj_api`、`doaj_csv`、`datacite_rest`、`datacite_annual_file`、`ror_dump`、`s2_api`、`s2_datasets`、`core_api`、`orcid_public_data_file`；央行 feed 实例随行。
- 批次二（V5，V5-T17 扩大，10 个，12.0）：`plos_search_api`、`elife_api`、`scoap3_api`、`pubtator3_api`、`icite_api`、`usenix_sessions`、`ecva_papers`、`pwc_archive_import`、`isca_archive_pages`、`pvldb_volumes`。
- 前置：V3-T7 扩展、V3-T8 pc-agent、V3-T9 凭证库；用户侧 CL2 的合成检查口径经 08 认可（P-7）；法务对扩展代发单篇的结论；S2 key 与 CORE 许可。
- 出口：用户侧 P0 通道 V3 出口达 CL3；具名 AI 爬虫禁令站点在法务结论前只给"在出版社打开 + 一键保存"，配方停在 CL1。P1 两批分别在 V3、V5 出口达 CL3，许可未到的 `core_api` 与待 P-13 的 `nasa_ads_api`、`orcid_api` 停在 CL0。P1 是泳道任务，不占关键路径评审容量。

### W4 P2 与按需升级（V5 以后）

- 范围（12 个，18.0）：`hal_api`、`openaire_api`、`openaire_graph_dump`、`wikidata_sparql`、`wikidata_dump`、`open_policy_finder_api`、`pubchem_pug_rest`、`cinii_resourcesync`、`osti_api`、`fraser_api`、`lens_api`、`alphaxiv_mcp`。
- 前置：维护点数有余量（V7 部分由 V7-T9 承载）；`hal_api`、`pubchem_pug_rest`、`cinii_resourcesync` 须 robots 书面确认；`lens_api`、`alphaxiv_mcp` 依赖用户侧执行器，且同属用户侧元数据查询，契约 v1 停在 CL0（P-13）。
- 出口：按需达 CL2 以上，`metadata-only` 只要求元数据通道。按申请量与核心 venue 数排序，一次只开余量内的卡。

### 不排波次

- 只服务登记来源、停在 CL0（5 个，7.5）：`ceur_ws_volumes`、`jstage_webapi`、`scielo_articlemeta`、`rss_proceedings_volumes`、`eartharxiv_janeway`；来源升为"支持"后按 W4 处理。
- 撤销或暂停：`ieee_xplore_user`、`cambridge_core_user`、`nber_conference_pages`。零代码行（只登记 68、实例配置 22）不单列，随优先级进入各波次。

### 波次归属调整

| connector_id | 规则所得 | 调整为 | 理由 |
|---|---|---|---|
| `crossref_rest` | W2 | W0 | `crossref_delegated` 依赖其请求声明 |
| `oai_pmh` | W1 | W0 | `arxiv_oai` 是引擎首个实例；W0 只交最小集 |
| `unpaywall_api` | W3 | W2 | OA 定位须有 ≥2 条同能力通道（AC-V1.21）；桥接只需 0.5 人日 |
| `lens_api`、`alphaxiv_mcp` | W3 或 W4 | W4 | 用户侧且为 metadata-only（未标）或 P2，两条规则取较晚者 |
| `econsoc_fulltext`、`openreview_api` | W3 | W3，只做用户侧 | 平台侧：econsoc 并入族实例；openreview 按 D-052 停用，待 ⚑ACCT；openreview 用户侧为本人 token 查询，待 P-13，停在 CL0 |
| `nber_site` | W3 | 暂停，不排波次 | NBER T&C（2026-08-01）禁止未经许可的自动访问；平台侧与用户侧都待书面许可（待拍板），只留 1.5 人日预算 |
| `orcid_api` | W3（平台） | W3（用户侧） | 公共 API 凭证发给个人、禁持续轮询；平台只用年度文件 |
| P1 平台侧 24 个 | W3（V2–V3） | V3、V5 两批 | 09 的 V5 交付含"P1 来源第二批"，按 main |
| `ieee_xplore_user` | W3 | 撤销 | HC-27 与 lint 12：IEEE 全文只外链 |
| `cambridge_core_user` | W3 | 撤销 | 官方无 API、TDM 限非商用；robots.txt 被 CF 挑战，按 RFC 9309 视为全禁（矩阵口径，含用户侧）；全文外链 |
| `nber_conference_pages` | W3 | 暂停 | nber.org 全部主机零自动化 |
| `nasa_ads_api`、`orcid_api`、`lens_api`、`alphaxiv_mcp` | W3u、W4u 达 CL3 或 CL2+ | 保留波次占位，停在 CL0 | 契约 v1 无用户侧元数据查询协议，待 P-13 |

## 里程碑对应表

| 里程碑 | 波次 | 连接器交付 | 连接器出口 |
|---|---|---|---|
| V0 | W0 | D-074、D-075 裁决；CN-1…CN-4 | 5 个 CL1，各经网关 dry-run 一次 |
| V1 | W1、W2 | 29 个（含 `unpaywall_api`）；P0 零代码登记；CN-5、CN-8 | 无闸门的 P0 平台侧 CL3；闸门类 CL1 待命；桥接有去向与期限 |
| V2 | W2 收尾 | CN-6 桥接移植；SCD 由路由器与健全放宽消费 | 平台侧桥接全部移植或转 CLX；14 日新鲜度观测覆盖 W0–W2 |
| V3 | W3 批次一 | CN-7 用户侧 10 个；P1 批次一 14 个；运维台最小集（V3-T10） | 用户侧 P0 通道 CL3 或只外链；批次一 CL3（待 P-13 的 3 个与待 CORE 许可的 `core_api` 除外，后者停在 CL0）；首次季度复核完成 |
| V4 | — | 不新增连接器 | 已达等级的保持条件不失效 |
| V5 | W3 批次二 | P1 批次二 10 个；用户侧全文界面（V5-T11） | 批次二 CL3；回执五类与原因码六类在界面全覆盖 |
| V6 | W4 | 按需升级 | — |
| V7 | W4 | V7-T9 名录扩展；O2 详情、O5 灰度、O6 预算界面（同 [connector-ui](connector-ui.md)） | P2 按需 CL2 以上，维护点数不超余量 |

## 工作量汇总

### 按族与波次（个数 / 人日）

| 族（桥接按目标族） | W0 | W1 | W2 | W3 | W4 | CL0 | 合计 |
|---|---:|---:|---:|---:|---:|---:|---:|
| crossref_delegated | 1 / 3.0 | — | 1 / 0.5 | — | — | — | 2 / 3.5 |
| oai_pmh | 2 / 3.5 | — | 1 / 0.5 | — | — | — | 3 / 4.0 |
| feed | — | 1 / 1.5 | — | — | — | — | 1 / 1.5 |
| aggregator_api | 2 / 3.5 | 6 / 9.5 | 2 / 1.5 | 11 / 16.0 | 9 / 12.0 | 2 / 4.0 | 32 / 46.5 |
| bulk_snapshot | — | — | 8 / 15.5 | 7 / 9.0 | 3 / 6.0 | — | 18 / 30.5 |
| site_special | — | 6 / 9.0 | 4 / 3.0 | 11 / 14.0 | — | 3 / 3.5 | 24 / 29.5 |
| platform_family | — | — | — | 2 / 3.5 | — | — | 2 / 3.5 |
| official_tdm_api | — | — | — | 3 / 5.0 | — | — | 3 / 5.0 |
| **合计** | 5 / 10.0 | 13 / 20.0 | 16 / 21.0 | 34 / 47.5 | 12 / 18.0 | 5 / 7.5 | 85 / 124.0 |

另 `nber_site`（site_special）预留 1.5 人日，许可前不开工，不计入上表个数；连同预留共 125.5 人日。

按类型：族核心 4 个 8.5，桥接 20 个 23.0（含 `nber_site` 预留 1.5），新写 62 个 94.0。桥接目标族取第一阶段清单；v1-bridge 族对 `aea_fulltext_user`、`econsoc_fulltext`、`nber_site` 另有并入或拆分建议，定稿后重排。

### SOP 口径、框架卡与 v1 复用

- **SOP A** 只登记 68 行 × ≤30 分钟，约 4.3 人日；**SOP B** 8 个 OAI 端点，约 0.5；**SOP C** 14 行（feed 11 行、复用他行连接器 3 行）× ≤0.5，约 7.0；**SOP D** 新写 62 个 94.0（均 1.5）。
- **框架与晋级卡**：CN-1 3、CN-2 5、CN-3 4、CN-6 2.5、CN-8 17.25（0.25 人日 × 69 个以 CL3 为目标的连接器，含闸门待命者、待 P-13 的 3 个与 `nber_site` 预留，本文估计，未核），合计 31.75。
- **v1 复用**：桥接省约 17 人日；OAI 信封核、Crossref 两轴枚举、标识符规范化、`ChallengeDetector` 与各站 parse 模块可直接复用，主要压低 W0。v1 的 182 个 fixture 以 `provenance: v1_import` 只供桥接回放与移植对拍；CL1 四类 fixture 须经 staging 网关重录或按合成件登记，黄金改写为 NormRecord。

### 与 09 和长稿任务卡对账

| 里程碑 | 长稿卡（人日） | 本计划（人日） | 差 |
|---|---|---|---:|
| V0 | 无逐连接器卡（V0-T7、T9、T10、T12 属底座；T12 的录制工具迁移由 CN-3 承接，人日不调） | W0 22，其中 15 自 V1 前移（CN-2 5、CN-4 10） | +22 |
| V1 | V1-T4 8、T5 6、T6 22、T7 6，共 42 | V1-T4 余项 3、V1-T5 余项 3、W1 20.0、W2 21.0、CN-8 8.5，共 55.5 | +13.5 |
| V2 | 无 | CN-6 2.5 | +2.5 |
| V3 | V3-T15 10 | P1 平台侧 20.5、CN-7 16.5、CN-8 6.25，共 43.25 | +33.25 |
| V5 | V5-T17 8 | 12.0、CN-8 2.5，共 14.5 | +6.5 |
| V7 | V7-T9 8 | W4 18.0 | +10.0 |
| **合计** | 68 | 155.75 | **+87.75** |

- 另有零代码约 11.8 人日（多随名录维护），CL0 的 7.5 不排期。
- 差额来源：快照族长稿一张卡 6 人日，逐源 8 个要 15.5；长稿把用户侧配方算进 V3-T7、T8 的执行器；P1 长稿两卡按来源列 16 项，本计划按连接器计 24 个。
- 若照此执行：09 的 V0 由 62 变为 84 人日，V1 由 125 变为约 138.5 人日。本文不改 09 的数字，见未决事项。

## 连接器任务卡清单

沿用长稿编号的卡只写范围变化（原文见文末长稿路径）；新卡用 CN 编号，分支 `connector/<id>`。

| 卡 | 范围 | 人日 | 依赖 | 验收 |
|---|---|---:|---|---|
| V0-T3 | 发函增补：EBI 同时问 bulk 与用量；NBER 问会议页与周更文件许可 | 3 | D-049 | AC-V0.11 |
| CN-1 | ConnectorManifest schema、6 条连接器 lint、卡片生成 | 3 | V0-T7 | manifest 全过 schema 与 lint；卡片重生成差异 0 |
| CN-2 | SDK 与 runner：两种协议、核心类型、`Step` 生成器、`CursorEnvelope`、15 类 error_class、依赖禁表 | 5 | CN-1、V0-T10 | 通用契约测试 CT-01、CT-02、CT-03、CT-10 通过；无网沙箱内导入禁表库即失败 |
| CN-3 | 通用 12 条契约测试（实例 × fixture 参数化）；网关 record 模式、脱敏与扫描；开发命令链；承接 V0-T12 的录制工具迁移 | 4 | CN-2 | 缺 fixture、缺乱序反例、黄金变而版本未升都报失败；扫描拦截 key、cookie、邮箱 |
| CN-4 | W0 的 5 个到 CL1 | 10 | CN-1…CN-3 | 见 W0 出口；AC-V1.22 的 7 日窗口 fixture 在此录制 |
| V1-T4 | 余项：SCD 由 `describe()` 生成、九族基类、桥接网关垫片 | 3 | CN-2 | AC-V1.15 |
| V1-T5 | 余项：venue 多键归一、零代码 A/B 工具与首批 10 个接入 | 3 | CN-4 | AC-V1.16、AC-V1.17 |
| V1-T6 | W1 的 13 个 | 20 | CN-4、V1-T8 | AC-V1.18、AC-V1.19 |
| V1-T7 | W2 的 8 个快照 | 15.5 | CN-4 | AC-V1.25 |
| CN-5 | W2 的 8 个桥接 | 5.5 | V1-T4 | AC-V1.15 的平台侧部分（口径见未决事项）；v1 fixture 回放通过 |
| CN-8 | CL3 晋级包：runbook（游标迁移、重置加回填、合规预案）、SLO 与告警、替补与急停演练、owner 与 backup_owner | 0.25/个 | CL2 | AC-V1.21；演练记录齐全 |
| CN-6 | 桥接移植：`platform_bridge` 7 个中的 `acl_anthology_xml`、`pmlr_volumes`、`cvf_open_access_pages`、`neurips_proceedings_pages`、`openalex_api` 改为声明式 plan；`repec_redif`、`unpaywall_api` 随目标族在 W2 直接写成快照或声明式（不另计）；其余桥接在 W0、W2 已直接写成族实例或快照 | 2.5 | CN-5 | v1 fixture 与近 14 天样本 shadow 等价；桥接转 CLX |
| CN-7 | W3 的 10 个用户侧连接器（5 个 RecipeProvider 达 CL3、2 个解散并入承接配方；`openreview_api` 用户侧、`nasa_ads_api`、`orcid_api` 待 P-13，只做清单与卡片）与 `nber_site` 预留 | 16.5 | V3-T7、T8、T9 | AC-V3.17…V3.19；配方对抗 fixture 全拒 |
| V3-T10 | 运维台最小集：O7、O3 只读、O4、简版 O1；O5、O6 走 CLI | 6 | V3-T1 | AC-V3.24…V3.26 |
| V3-T15 | 扩为 P1 批次一 14 个 | 20.5 | V1-T4 | 批次一 CL3 |
| V5-T17 | 扩为 P1 批次二 10 个 | 12 | V1-T4 | 批次二 CL3 |
| V7-T9 | 名录扩展与 W4 按需升级 | 18 | 维护余量 | P2 按需 CL2 以上 |

## 外部依赖与决策门

"最晚时点"指赶上所在里程碑出口 CL3 的时点；过期不阻塞出口，受影响连接器停在 CL1 待命。

| 依赖 | 影响连接器 | 最晚时点 | 缺失时 |
|---|---|---|---|
| NCBI 书面确认 | `pubmed_eutils`、`pubmed_baseline`（连带 `psb_proceedings`；`pmc_bioc` 不用 E-utilities，不受此闸） | V1 第 3 周 | 元数据由 `europe_pmc_rest` 与 `crossref_delegated` 承接，PMC 走 `pmc_s3` 与 OAI |
| EBI 书面确认（bulk、用量） | `europe_pmc_bulk`；`europe_pmc_rest` 参与交互联邦 | V1 第 5 周 | bulk 不做；REST 只做后台日窗收割，检索完整性报告标缺源 |
| OpenReview 服务账号（⚑ACCT） | `openreview_api` 平台侧、`tmlr_list` 详情补全 | V1 前 | 按 D-052 由 arXiv、dblp 快照与外链兜底 |
| OSF 书面确认 | `osf_api` | V1 第 3 周 | 不做，PsyArXiv 只走 Crossref |
| FIZ 书面确认（⚑SA ⚑COMM） | `zbmath_open_api` | V1 第 3 周 | 停在 CL0，数学元数据由 `zbmath_kg_dump` 与 Crossref 承担 |
| CORE 许可（⚑LIC ⚑COMM） | `core_api` | V3 | 不启用；OA 定位由 OpenAlex 与 Unpaywall 承担 |
| NBER 许可 | `nber_site` 平台侧、`nber_conference_pages`、周更元数据文件 | V1 前 | 元数据经 Crossref 10.3386 与 RePEc `nbr:nberwo`；会议标签人工维护，经 PR 进注册表 |
| APS Harvest 全量许可（⚑LIC） | `aps_harvest` 全量 | V1 出口 | 只做 OA 子集加 Crossref |
| 法务：扩展代发单篇 | `atypon_user`、`silverchair_user`、`nber_site` 用户侧 | V3 扩展开发前 | 只给"在出版社打开 + 一键保存"；nber.org 只给"在出版社打开" |
| 法务：B 类摘要 | 所有产出摘要的映射 | V1 相应任务前 | 从严，摘要记 `publisher_copyright`，不进共享派生 |
| DG-Q4 与 D-049 | 全部 ⚑ROBOTS 连接器 | V0 出口 | 后台批量等书面确认，按需单篇等例外附表 |
| DG-Q1 商用 | 带 ⚑COMM 的连接器（如 `s2_*`、`core_api`、三个 TDM API） | V1-T13 开工前确认默认，最晚 V5 公开内测前定案 | 默认非商用；开关演练见 AC-V1.13 |
| DG-Q3 付费档 | `openalex_api` 预算、`crossref_delegated` 容量 | V7 或预算告警 | 快照底座加兴趣并集，API 只做 lookup |
| D-050、D-051、D-052 | `dblp_*`、`ssrn_crossref`、`openreview_api` | V1 前 | 维持暂停或只外链 |

## 上游变化风险

相对长稿（2026-09-26/27），实测 2026-09-30。放宽类变化只进复核队列，闸门不自动降低。

| 来源 | 变化 | 处置 |
|---|---|---|
| NBER | T&C 2026-08-01 禁止未经许可的自动访问与数据挖掘 [https://www.nber.org/terms-and-conditions, 2026-09-30] | nber.org 零自动化，RSS 增量暂停；v2-P0 验收口径待拍板 |
| arXiv | export 主机 robots 全禁，arxiv.org 禁 `/api`，OAI 主机 robots 404 [https://export.arxiv.org/robots.txt, 2026-09-30] | `arxiv_oai` 只用 OAI 与 arXivRaw，SCD 不声明 search |
| OpenAlex | `per_page` 支持上限 100（200 仍被接受但已标弃用）；`from_created_date` 实测返回 429 "Plan upgrade required"；按量付费；快照带 `deleted_ids` [https://help.openalex.org/access/pricing/, 2026-09-30] | 季度快照加 `updated_date` 分区加 Crossref 兜底；API 只做 lookup 并进预算；加计数骤降探针 |
| PMC | OA Web Service 2026-08-25 下线，旧 FTP 已删 [https://pmc.ncbi.nlm.nih.gov/about/new-in-pmc/, 2026-09-30] | 改用 `pmc_s3`、OAI、BioC；E-utilities 仍受 ⚑ROBOTS |
| Europe PMC | `INDEX_DATE` 增量静默返回 0，修订增量字段待核 [https://www.ebi.ac.uk/europepmc/webservices/rest/search, 2026-09-30 实测]；bulk 主机 robots 全禁 [https://ftp.ebi.ac.uk/robots.txt, 2026-09-30] | 只用 `FIRST_IDATE` 日窗，加"静默零"探针；bulk 等 EBI |
| ORCID | 公共 API 凭证发给个人、禁持续轮询、不得用于营收产品；`pub.orcid.org` robots 全禁 [https://info.orcid.org/public-client-terms-of-service/, 2026-09-30] | 平台只用年度 CC0 文件，OAuth 只在用户侧 |
| Crossref | 按请求类分池、按 mailto 限流；分池生效日期两说，待核：2026-07-21 起（F1，社区公告）[https://community.crossref.org/t/refining-rest-api-limits-for-improved-stability-and-reliability/16137, 2026-09-30]；2025-12-01 起分池、2026-07-21 起再按 mailto（G，官方博文）[https://crossref.org/blog/announcing-changes-to-rest-api-rate-limits/, 2026-09-30] | 令牌桶"凭证"维含部署 mailto，集中限速；`/members` 按列表池估 |
| RePEc | 数据默认非商用 [https://ideas.repec.org/getdata.html, 2026-09-30] | 建议 `repec_redif` 补 ⚑COMM，代收来源连带 |
| HAL | OAI 文档写明不得商用抽取数据 [https://api.archives-ouvertes.fr/docs/oai, 2026-09-30] | 建议 `hal_api` 补 ⚑COMM |
| IOP | 2026-07 T&DM 政策：API、feed、MCP、agent 一律另签协议 [https://ioppublishing.org/?p=149832, 2026-09-30] | 零自动化，只经 Crossref |
| OpenReview | 匿名 `/notes` 返回 403 ChallengeRequiredError；ToS 禁止授权第三方代用 [https://openreview.net/legal/terms, 2026-09-30] | 平台侧继续停用；用户 token 不经平台转发 |
| bioRxiv、medRxiv | 2025-12-01 起新 DOI 前缀 10.64898；medRxiv 有 version "0" [https://connect.biorxiv.org/news/2025/11/18/preprint_dois, 2026-09-30] | 两个前缀都登记；加 schema 漂移探针 |
| SSRN | 2026-08-01 以来新建的 10.2139 记录中 75.1% 的 license 指向 USPTO 版权说明页（Crossref 分面实测）[https://api.crossref.org/prefixes/10.2139/works?filter=from-created-date:2026-08-01&rows=0&facet=license:*,type-name:*, 2026-09-30] | 映射为保留所有权利，不共享 |
| 其他 | ROR v1 已 410 [https://ror.org/blog/2025-06-11-v1-sunset/, 2026-09-30]；DOAJ OAI 对非付费用户滞后可达 30 天 [https://doaj.org/docs/oai-pmh/, 2026-09-30]；Zenodo exporter 位于 robots 所禁 `/api` [https://zenodo.org/robots.txt, 2026-09-30]；CVF 对部分 UA 403（原因未核）；IACR、ACS robots 放宽 [https://eprint.iacr.org/robots.txt, 2026-09-30] [https://pubs.acs.org/robots.txt, 2026-09-30]；ScienceDirect robots 对实测 UA 403，因 UA 或出口未核 [https://www.sciencedirect.com/robots.txt, 2026-09-30] | 各卡照实写；CVF 不换 UA，被拦即 `challenge` |

## 分工与并行

- **角色**：主 agent 任 controller；每族 owner 加 backup_owner，P0 两人在岗。V1 三条泳道：A aggregator_api 与 bulk_snapshot，B oai_pmh、site_special 与 feed，C CN 卡、v1_bridge 与晋级包。
- **参考连接器先行**：W0 三个是全局样板；W1 各族第一个（`feed`、`inspire_rest`、`biorxiv_api`）经独立评审后才开同族并行卡。
- **fixture 录制窗口**：只经 staging 网关 record 模式，G1 签字后才能录；每周两个窗口按主机预算分批录；闸门未开的主机只写合成 fixture（`provenance` 标合成并写原因），确认到达后补录。
- **评审门排期**：G1 每周两次（作者不兼任复核人）；G2 每周一次；G3 在 V1 第 7–8 周集中一批，V3、V5 出口前各一批。合规、安全类卡双评审。
- **日历约束**：W1、W2 进入 staging 计天的时点见上，第 8 周完成 G3；任何卡滑期都直接压缩 14 天计天窗口。
- **维护余量**：维护点数按 `impl` 计（契约评审团建议值，未核），W4 升级只在余量内放行。

## 怎么验收

- **清单自洽**：脚本核对每个 connector_id 恰属一个波次或标明"CL0 / 撤销 / 暂停"，各表人日之和一致。
- **波次出口**：CI 由 manifest 的 `conformance.rules` 推出可达最高 CL，与本文出口逐条比对；闸门类以"CL1 且通道模式为 deny 或 link_only"判为待命达标。
- **里程碑挂钩**：V1 看 AC-V1.15…V1.25（AC-V1.15 只含平台侧 12 个桥接件，见未决事项）；V3 看 AC-V3.17…V3.19、AC-V3.24…V3.26；V5 看 AC-V5.31、AC-V5.32。
- **重估**：W1 结束时用 AC-V1.18 实测的中位耗时重算 W2–W4，写进 V1 里程碑报告。

## 未决事项

- **W0 放哪**：留在 V0（V0 增 22 人日，其中 15 自 V1 前移），或作为 V1 开头两周。建议留在 V0，顺带验证 V0-T9、T10 的骨架。
- **人日差额**：155.75 对 68 人日。建议 SOP 口径作上限；P1、P2 泳道按长稿预算封顶，超出即削范围；W1 后按实测校准，09 数字等 V0 出口重估时再改。
- **V1 出口口径**：框架要求 P0 平台侧全部 CL3；日历不够时，建议改为"元数据与最新论文主干 CL3，其余 CL2"，须用户确认。V1 对外无服务，CL3 的 G3 与 rollout 以哪个部署为"生产"，待与 [conformance-and-testing](conformance-and-testing.md) 统一。
- **AC-V1.15 口径**：09 V1 与 AC-V1.15 要 20 个 v1 adapter 在 V1 过契约测试；本文 V1 只做平台侧 12 个（W0 2、W2 10），其余 8 个（转用户侧 5、暂停 2、`s2_api`）在 V3。二选一：V1 为这 8 个补只回放的桥接清单（约 2 人日，未核），或把 V1 口径改为 12 个。用户侧桥接的 `sunset_by` 三族已统一为 V2 出口（platform-family PF-Q5）。
- **P1 时点**：框架写 P1 在 V2–V3 达 CL3，09 写 V5 交付 P1 第二批；本文按 09 分两批。
- **NBER**：零自动化后 `nber_wp`（v2-P0）的验收口径与 `nber_conferences`（v2-P1）的会议标签来源；`nber_site` 用户侧取回是否开工（等法务与 NBER 许可）；`nber_conference_pages` 暂停还是废止。
- **混合连接器拆分**：契约分 PlatformConnector 与 RecipeProvider，`econsoc_fulltext`、`nber_site`、`openreview_api` 可能各拆两个 manifest，connector_id 由契约与矩阵统一定。
- **清单修正**：`cambridge_core_user` 已随矩阵撤销，日后是否以 platform_family 配方恢复待定；`orcid_api` 改为用户侧。v1-bridge 族表的波次已与本文、矩阵一致（`ssrn_crossref` W2、`crossref_rest` W0）。
- **P-13 用户侧元数据查询**：`nasa_ads_api`、`orcid_api`、`lens_api`、`alphaxiv_mcp` 与 `openreview_api` 用户侧在契约 v1 停在 CL0；若 v1.x 增加 `QueryRecipe`，前两个随 V3 批次一、后两个随 W4 晋级，CN-7、CN-8 的人日照此增减；否决则四者转 CLX 或改外链，矩阵与 aggregator-api 族表同步。
- **OpenCitations**：长稿 V1-T16 在 V1 用 OpenCitations，本文按 P1 放 V3；`opencitations_dump` 是否前移到 W2。
- **登记与"支持但无连接器"**：登记来源不运行连接器、证据过期只标 `review_overdue`（细化 D-073）；`wfa_meeting`、`sfs_cavalcade`、`efa_meeting`、`ssoar`、`fatcat_ia_scholar` 降为登记还是补连接器，见 [README](README.md)。
- **CL 相关**：契约待拍板 P-4（CL2 生产口径）、P-7（用户侧 CL2 检验）、P-11（CL3 引擎新增实例的 staging 天数）。
- **⚑COMM 补标**：RePEc、HAL 是否补 ⚑COMM（本批不改名录）。

---

更细的材料：`families/` 下九篇族文档；长稿任务卡与 AC 见 `git show v2-drafts:docs/plan/v2/09-roadmap-and-milestones.md`，SOP 与 v1 去向见 `git show v2-drafts:docs/plan/v2/03-sources-and-corpus-pipeline.md` 的 §13、§14.1。
