---
title: 来源 × 连接器矩阵
status: draft
owner: opus5.5-primary
updated: 2026-09-30
---

# 来源 × 连接器矩阵

> 本文回答：名录里每个来源由哪个连接器接、在哪个波次接、要做到哪个一致性等级（CL）。结论：169 个非排除来源由第一阶段清单的 89 个连接器承接，撤销 2 个不能启用的用户侧连接器后在册 87 个（其中 NBER 两个暂停）；104 行目标 CL3、21 行 CL2+、38 行停在 CL0（登记 35、待 P-13 3）；5 行"支持但无连接器"和 NBER 暂停列入待拍板；187 行与名录逐行核对，id、七类、状态、闸门、支持零差异。

## 要点

- **分工**：[来源支持名录](source-directory.md)回答"接不接、怎么接"；本表回答"由哪个连接器接、什么时候、做到什么等级"。本表不改名录结论，分歧写在[逐行核对](#逐行核对与对-e-清单的修正)与[未决事项](#未决事项)。
- **上下游**：[接口契约 v1](../plan/v2/connectors/contract.md)、[一致性与测试](../plan/v2/connectors/conformance-and-testing.md)、[连接器总览](../plan/v2/connectors/README.md)；"连接器"列链到 `families/<family>.md` 的卡片；波次以[实施计划](../plan/v2/connectors/implementation-plan.md)为准回写本表。
- **连接器**：族核心 4（`crossref_delegated`、`oai_pmh`、`feed`、`atypon_user`）、新写 65、v1 桥接 20，合计 89；撤销 `ieee_xplore_user`、`cambridge_core_user` 后在册 87。在册中 `nber_site`、`nber_conference_pages` 暂停，5 个只服务登记行、停在 CL0；用户侧元数据查询 `nasa_ads_api`、`orcid_api`、`lens_api`、`alphaxiv_mcp` 与 `openreview_api` 用户侧（本人 token 查询）在契约 v1 无对应协议，保留波次占位、停在 CL0（待拍板 P-13）。
- **波次**：连接器构建波次 W0 5、W1 13、W2 16、W3 34（平台侧 24 + W3u 10）、W4 12（平台侧 10 + W4u 2），已回写实施计划的调整；W3u/W4u 为用户侧通道（计入 W3、W4，依赖 V3 的扩展或 pc-agent），记法同实施计划。
- **按裁定改动**（均列入待拍板，名录不动）：撤销上述 2 个连接器，IEEE、Cambridge 全文改外链；`orcid_api` 改为用户侧 OAuth；NBER 通道两侧都标"停"（nber.org 零自动化）；`aps` 全量用户侧通道未排期，待许可。

## 约定

**列缩写**：

|列|含义与取值|
|---|---|
|来源|`source_id`，与名录一致|
|族|主族：第一条元数据通道所用连接器的族。XD `crossref_delegated`、AG `aggregator_api`、OAI `oai_pmh`、FD `feed`、BK `bulk_snapshot`、PF `platform_family`、TDM `official_tdm_api`、SS `site_special`、V1 `v1_bridge`（反查表中 V1→X 表示移植目标族）、— 暂无通道|
|连接器|该行最费工的连接器（第一阶段 E 清单口径），链到卡片；XD、OAI、FD 为族引擎，AT、SC 为 `atypon_user`、`silverchair_user` 族配方；— 为暂无连接器|
|元 / 新 / 全|三通道路径，简写同上；本＝"连接器"列那个；其余写 connector_id；经x＝由来源 x 的连接器代收；OA链＝OA 定位链；自OA＝本源平台侧 OA 全文（逐篇过许可闸）；外＝仅外链；同元＝同元数据通道或无增量；用?＝用户侧但连接器未定；旁路(…)＝经他源旁路；后缀"停"＝暂停|
|码|行级工作量：零（只登记）、配（族实例或复用他行连接器）、新（新写）、桥（经 v1_bridge）、缺（暂无连接器）|
|执|exec_side：P 平台、U 用户侧、M 两侧都有、— 无；契约只有 platform、user，连接器级 M 指同一 id 前缀下 PlatformConnector 与 RecipeProvider 两个清单，状态见卡片 §2|
|状态|v2_status：P0/P1/P2（括号为名录限定语）；mo0/mo1/mo2/mo 为 `metadata-only（P0/P1/P2/未标）`|
|支|support_tier：支＝支持，登＝登记|
|波|该行各通道上线波次，多个用 + 连接；带 u 的是用户侧通道（W3u/W4u）；— 为登记或暂无连接器；停＝全部通道暂停；暂停、未排期的通道不写|
|CL|该行通道须达到的一致性等级：CL3、CL2+（至少 CL2，生产口径待拍板 P-4）、CL0（登记，或待 P-13）、—（无连接器或暂停）|
|前置|闸门（⚑，括号为范围）；用户侧通道的 V3 依赖不再重复；AI禁＝Atypon 站点具名 AI 爬虫禁令，法务结论前只给"在出版社打开 + 一键保存"；T&C禁＝NBER 条款禁未经许可的自动访问，nber.org 两侧全部暂停、只给"在出版社打开"，待许可；P-13＝用户侧元数据查询，契约 v1 停在 CL0，波次为占位；△＝上游有重大变化；†＝本表撤销其用户侧连接器；‡＝支持但无连接器|

**波次规则**（落实框架规则）：

- 登记行不排波次、不运行连接器；不接入的 18 行无波次。
- `v2-P0` 与 `metadata-only（P0）` 的平台侧通道：参考连接器 `arxiv_oai`、`europe_pmc_rest` 所在行为 W0；族引擎与 AG、SS、OAI、FD 连接器为 W1；BK、V1 与其余为 W2。`crossref_delegated` 本身在 W0 打通全链，名录行从 W1 起按 ISSN、前缀等批量配置。
- `v2-P1` 与 `metadata-only（P1）` 为 W3；`v2-P2`、`metadata-only（P2）` 与未标优先级为 W4。
- 用户侧通道：P0、P1 为 W3u，P2 为 W4u。"经x"代收的行按代收连接器的族计，不早于本行优先级。
- 已回写[实施计划](../plan/v2/connectors/implementation-plan.md#波次归属调整)的调整：`crossref_rest`、`oai_pmh` 提到 W0，`unpaywall_api` 提到 W2，`econsoc_fulltext`、`openreview_api` 只排用户侧 W3u（平台侧并入族实例或待 ⚑ACCT）；`nber_site`、`nber_conference_pages` 暂停，书面许可前不排波次；P-13 的 4 个保留占位、停在 CL0。

**目标 CL**：P0 平台侧通道 V1 出口达 CL3、用户侧 V3 出口；P1 分 V3、V5 两批达 CL3（按 [09](../plan/v2/09-roadmap-and-milestones.md) 与实施计划）；P2 按需 CL2 以上；`metadata-only` 只要求元数据通道；登记与待 P-13 的 4 个连接器停在 CL0。晋级条件见[一致性与测试](../plan/v2/connectors/conformance-and-testing.md)。

## 数字概览

非排除 169 行（支持 134、登记 35），不接入 18 行。

|维度|计数（行）|
|---|---|
|主族|XD 89、AG 25、V1 15、BK 12、SS 9、OAI 6、FD 3、无通道 10|
|码（E 清单 → 本表）|零 66→68、配 22、新 50→48、桥 21、缺 10|
|执（E 清单 → 本表）|P 132→133、M 24→23、U 3、无 10；有用户侧通道的行 27→26|
|起始波次|W0 3、W1 29、W2 7、W3 64、W4 21、只有用户侧 4（W3u 2、W4u 2）、停 1、— 40（登记 35、缺 5）|
|目标 CL|CL3 104、CL2+ 21、CL0 38（登记 35、P-13 3）、— 6（缺 5、`nber_conferences` 暂停）|

|维度|计数（连接器，共 89）|
|---|---|
|所属族（桥接计 V1）|AG 28、V1 20、SS 19、BK 16、PF 2、XD 1、OAI 1、FD 1、TDM 1|
|构建波次|W0 5、W1 13、W2 16、W3 34（平台侧 24、W3u 10）、W4 12（平台侧 10、W4u 2）、—（只服务登记行）5、停 2、撤销 2|
|目标 CL|CL3 65、CL2+ 10、CL0 10（只服务登记行 5、P-13 5，含 `openreview_api` 用户侧）、— 4（撤销 2；停 2，族卡记"CL0（暂停）"）|

**与名录"数字概览"逐项核对**：

|项|名录|本表|说明|
|---|---|---|---|
|行数、分层、支持分级、非排除状态、排除类|187；134/35/18；36/63/44/26；13/2/3|同|逐行一致|
|闸门|66 行；ROBOTS 10、ACCT 2、COMM 17、LIC 3、BUDGET 1、DRIFT 9、RECHECK 27、SA 2|同|repec、hal 建议补 ⚑COMM，待拍板，本表未加|
|Crossref 委托|92|93|XD 直接服务 92 行，另有 `ssrn` 经 `ssrn_crossref`（桥接，目标族 XD）；名录的 92 是长稿字面计数，漏了写作"同 biorxiv"的 `medrxiv`|
|只需登记 / 需源专用或按源配置|66 / 93|68 / 91|`ieee_xplore`、`cambridge_core` 撤销用户侧连接器后只剩 Crossref 委托|
|经 v1_bridge|21 行，20 个 adapter|同|`nber_site` 服务 `nber_wp`、`nber_conferences` 两行|
|暂无 connector|10|10|另有 `nber_conferences` 通道全部暂停|
|用户侧执行|27|26|减 `ieee_xplore`、`cambridge_core`，加 `orcid`；另 `ams`、`assa_meetings`、`iza_dp` 名录全文列写"用户侧私有"而长稿只有平台侧（第一阶段按此计 30），本表不设连接器|

## 主表

每行一个非排除来源，按名录七类分节、节内顺序同名录。

### M1 出版与托管主体（69 行）

|来源|族|连接器|元|新|全|码|执|状态|支|波|CL|前置|
|---|---|---|---|---|---|---|---|---|---|---|---|---|
|elsevier_sd|XD|[elsevier_tdm][]|XD|XD|本|桥|M|P0|支|W1+W3u|CL3|⚑COMM △|
|wiley|XD|[wiley_tdm][]|XD|XD|本+AT|桥|M|P0|支|W1+W3u|CL3|⚑COMM AI禁|
|springer_link|XD|[springer_nature_api][]|XD+本|XD|本|新|M|P0|支|W1+W3u|CL3|⚑COMM|
|nature_portfolio|XD|[springer_nature_api][]|XD|XD+FD|本|配|M|P0|支|W1+W3u|CL3|⚑COMM|
|oup_academic|XD|[SC][]|XD|XD|SC|桥|M|P0|支|W1+W3u|CL3|—|
|cambridge_core|XD|[XD][]|XD|XD|外|零|P|P1|支|W3|CL3|⚑COMM †|
|tandf_online|XD|[AT][]|XD|XD|AT|零|M|P1|支|W3+W3u|CL3|⚑COMM AI禁|
|sage_journals|XD|[AT][]|XD|XD|AT|零|M|P1|支|W3+W3u|CL3|⚑COMM ⚑RECHECK AI禁|
|annual_reviews|XD|[XD][]|XD|XD|OA链|零|P|P1|支|W3|CL3|—|
|mdpi|XD|[OAI][]|XD+OAI|XD|OA链|配|P|P1|支|W3|CL3|—|
|frontiers|XD|[FD][]|XD|XD+FD|OA链|配|P|P1|支|W3|CL3|—|
|plos|SS|[plos_search_api][]|本+XD|本|自OA|新|P|P1|支|W3|CL3|—|
|cshl_press|XD|[XD][]|XD|XD|OA链|零|P|P2|支|W4|CL2+|—|
|hogrefe|XD|[XD][]|XD|XD|外|零|P|mo2|登|—|CL0|—|
|ucpress_online|XD|[XD][]|XD|XD|OA链|零|P|P2|登|—|CL0|⚑RECHECK|
|edp_sciences|XD|[XD][]|XD|XD|OA链|零|P|P1|支|W3|CL3|—|
|world_scientific|XD|[XD][]|XD|XD|外|零|P|mo2|登|—|CL0|—|
|degruyter_brill|XD|[XD][]|XD|XD|外|零|P|mo1|支|W3|CL3|—|
|msp|XD|[XD][]|XD|XD|外|零|P|P1|支|W3|CL3|—|
|intl_press|XD|[XD][]|XD|XD|外|零|P|P2|支|W4|CL2+|⚑RECHECK|
|uchicago_journals|XD|[AT][]|XD|XD|AT|零|M|P1|支|W3+W3u|CL3|AI禁|
|mit_press_direct|XD|[XD][]|XD|XD|经acl_anthology|零|P|mo1|支|W3|CL3|—|
|emerald_insight|XD|[XD][]|XD|XD|外|零|P|mo2|登|—|CL0|⚑DRIFT|
|pm_research|XD|[XD][]|XD|XD|外|零|P|P2|登|—|CL0|⚑RECHECK|
|iospress_faia|XD|[XD][]|XD|XD|OA链|零|P|P1|支|W3|CL3|⚑COMM|
|now_publishers|XD|[XD][]|XD|XD|外|零|P|mo2|登|—|CL0|⚑DRIFT ⚑RECHECK|
|peerj|XD|[XD][]|XD|XD|OA链|零|P|P2|登|—|CL0|—|
|f1000_platforms|XD|[XD][]|XD+经europe_pmc|XD+经europe_pmc|OA链|零|P|P2|登|—|CL0|—|
|aaas_science|XD|[FD][]|XD|XD+FD|OA链+用?|配|M|P1|支|W3|CL3|—|
|royal_society|XD|[XD][]|XD|XD|OA链+用?|零|M|P1|支|W3|CL3|—|
|apa_psycnet|XD|[XD][]|XD|XD|外|零|P|mo2|支|W4|CL2+|—|
|aps|SS|[aps_harvest][]|本+XD|XD|本|新|M|P0|支|W1（全量用户侧未排期，待许可）|CL3|⚑LIC(仅全量)|
|iop|XD|[XD][]|XD|XD|OA链+外|零|P|mo0|支|W1|CL3|△|
|aip|XD|[SC][]|XD|XD|SC|零|M|P1|支|W3+W3u|CL3|—|
|optica|XD|[XD][]|XD|XD|OA链+外|零|P|P1|支|W3|CL3|—|
|acs|XD|[XD][]|XD|XD|外|零|P|mo0|支|W1|CL3|△|
|rsc|XD|[XD][]|XD|XD|OA链|零|P|P1|支|W3|CL3|⚑DRIFT|
|ams|XD|[XD][]|XD|XD|外+用?|零|P|P1|支|W3|CL3|—|
|siam|XD|[FD][]|XD|XD+FD|AT|配|M|P1|支|W3+W3u|CL3|AI禁|
|ems_press|XD|[XD][]|XD|XD|OA链|零|P|P1|支|W3|CL3|—|
|acm_dl|XD|[XD][]|XD|XD|外|零|P|mo1|支|W3|CL3|—|
|ieee_xplore|XD|[XD][]|XD|XD|外|零|P|P1|支|W3|CL3|⚑COMM †|
|informs_pubsonline|XD|[AT][]|XD|XD|AT|零|M|P0|支|W1+W3u|CL3|AI禁|
|aom_journals|XD|[AT][]|XD|XD|AT|零|M|P0|支|W1+W3u|CL3|AI禁|
|aea_journals|XD|[aea_fulltext_user][]|XD|XD|本|桥|M|P0|支|W1+W3u|CL3|—|
|econsoc_journals|XD|[econsoc_fulltext][]|XD+OAI|XD|本|桥|M|P0|支|W1+W3u|CL3|—|
|aaa_pubs|XD|[SC][]|XD|XD|SC|零|M|P1|支|W3+W3u|CL3|—|
|sfn_journals|XD|[XD][]|XD|XD|OA链|零|P|P1|支|W3|CL3|⚑COMM|
|acl_anthology|V1|[acl_anthology_xml][]|本|本|自OA|桥|P|P0|支|W2|CL3|—|
|aaai_ojs|V1|[aaai_ojs_oai][]|本+XD|本|外|桥|P|P0|支|W1+W2|CL3|—|
|usenix|SS|[usenix_sessions][]|本|本|外|新|P|P1|支|W3|CL3|—|
|isca_archive|XD|[isca_archive_pages][]|XD+本|XD+本|外|新|P|P1|支|W3|CL3|—|
|spie_dl|XD|[XD][]|XD|XD|外|零|P|mo|登|—|CL0|—|
|ais_icis|XD|[XD][]|XD|XD|外|零|P|P2|支|W4|CL2+|—|
|scipost|XD|[FD][]|XD|XD+FD|OA链|配|P|P1|支|W3|CL3|—|
|project_euclid|XD|[XD][]|XD|XD|OA链+外|零|P|P1|支|W3|CL3|—|
|centre_mersenne_numdam|XD|[OAI][]|XD+OAI|XD+OAI|OA链|配|P|P1|支|W3|CL3|—|
|episciences|XD|[OAI][]|XD+OAI|XD+OAI|OA链|配|P|P2|登|—|CL0|⚑RECHECK|
|geoscienceworld|XD|[SC][]|XD|XD|SC|零|M|P2|支|W4+W4u|CL2+|⚑RECHECK|
|openreview|V1|[openreview_api][]|本停|本停|外|桥|M|P0|支|W3u 占位|CL0（待 P-13）|⚑ACCT △|
|pmlr|V1|[pmlr_volumes][]|本|本|外|桥|P|P0|支|W2|CL3|—|
|cvf_open_access|V1|[cvf_open_access_pages][]|本|本|外|桥|P|P0|支|W2|CL3|△|
|lipics_drops|AG|[datacite_rest][]|本+OAI|本+OAI|自OA|配|P|P1|支|W3|CL3|—|
|ceur_ws|SS|[ceur_ws_volumes][SS5]|本|本|外|新|P|P2|登|—|CL0|⚑RECHECK|
|pos_sissa|XD|[XD][]|XD+经inspire_hep|XD+经inspire_hep|OA链|零|P|P2|登|—|CL0|—|
|sciengine|XD|[XD][]|XD|XD|外|零|P|mo2|支|W4|CL2+|⚑RECHECK|
|jstage|AG|[jstage_webapi][AG5]|本|本|OA链|新|P|P2|登|—|CL0|⚑COMM|
|scielo|AG|[scielo_articlemeta][AG5]|本|本|OA链|新|P|P2|登|—|CL0|—|
|redalyc|—|—|旁路(OpenAlex/Crossref/DOAJ)|同元|OA链|缺|—|mo|登|—|CL0|—|

### M2 标识与注册（6 行）

|来源|族|连接器|元|新|全|码|执|状态|支|波|CL|前置|
|---|---|---|---|---|---|---|---|---|---|---|---|---|
|crossref|V1|[crossref_rest][]|本+crossref_annual_file|本+crossref_annual_file|—|桥|P|P0|支|W0+W2|CL3|△|
|wikidata|AG|[wikidata_sparql][AG5]|本+wikidata_dump|本+wikidata_dump|—|新|P|P2|支|W4|CL2+|—|
|open_policy_finder|AG|[open_policy_finder_api][AG5]|本|同元|—|新|P|P2|支|W4|CL2+|⚑COMM|
|orcid|AG|[orcid_api][]|本+orcid_public_data_file|同元|—|新|M|P1|支|W3+W3u|CL3|⚑ROBOTS ⚑COMM △ P-13|
|ror|BK|[ror_dump][]|本|本|—|新|P|P1|支|W3|CL3|△|
|datacite|AG|[datacite_rest][]|本+datacite_annual_file|本+datacite_annual_file|—|新|P|P1|支|W3|CL3|—|

### L1a 期刊与会议（28 行，另 3 行不接入）

|来源|族|连接器|元|新|全|码|执|状态|支|波|CL|前置|
|---|---|---|---|---|---|---|---|---|---|---|---|---|
|pnas|XD|[FD][]|XD|XD+FD|OA链|配|P|P0|支|W1|CL3|—|
|mit_smr|XD|[XD][]|XD|XD|外|零|P|mo2|登|—|CL0|⚑DRIFT|
|ccs_chemistry|XD|[XD][]|XD|XD|OA链|零|P|P2|登|—|CL0|—|
|misq|XD|[SC][]|XD|XD|SC|零|M|P1|支|W3+W3u|CL3|—|
|quantum_journal|XD|[FD][]|XD|XD+FD|OA链|配|P|P2|登|—|CL0|—|
|annals_math|XD|[XD][]|XD|XD|外|零|P|mo|支|W4|CL2+|—|
|elife|XD|[elife_api][]|XD+本|FD+XD|自OA|新|P|P1|支|W3|CL3|⚑ROBOTS(仅API)|
|jmlr|FD|[jmlr_volumes][]|FD+本|FD+本|自OA|新|P|P0|支|W1|CL3|—|
|tmlr|SS|[tmlr_list][]|本+经openreview停|本+经openreview停|外|新|P|P0|支|W1|CL3|⚑ACCT|
|jair|XD|[XD][]|XD|XD|OA链|零|P|P1|支|W3|CL3|—|
|wulixb|XD|[XD][]|XD|XD|未核|零|P|P2|支|W4|CL2+|⚑RECHECK|
|pvldb|XD|[pvldb_volumes][]|XD+本|XD|自OA|新|P|P1|支|W3|CL3|⚑COMM|
|neurips_proceedings|V1|[neurips_proceedings_pages][]|本+XD|本|外|桥|P|P0|支|W1+W2|CL3|—|
|ecva|SS|[ecva_papers][]|本+经springer_link|同元|外|新|P|P1|支|W3|CL3|—|
|ijcai_proceedings|XD|[ijcai_proceedings_pages][]|XD+本|XD|外|新|P|P0|支|W1|CL3|—|
|ndss|XD|[XD][]|XD|XD|外|零|P|P1|支|W3|CL3|—|
|rss_proceedings|SS|[rss_proceedings_volumes][SS5]|本|本|外|新|P|P2|登|—|CL0|⚑RECHECK|
|mlsys_proceedings|—|—|—|—|OA链|缺|—|P2|登|—|CL0|⚑RECHECK|
|aamas_ifaamas|XD|[XD][]|XD|XD|外|零|P|P2|登|—|CL0|—|
|cogsci_proceedings|OAI|[OAI][]|OAI|OAI|自OA|配|P|P1|支|W3|CL3|—|
|psb_proceedings|BK|[pubmed_baseline][]|经pubmed|经pubmed|未核|零|P|P2|登|—|CL0|⚑RECHECK|
|assa_meetings|SS|[assa_program][]|本|本|用?|新|P|P1|支|W3|CL3|—|
|nber_conferences|V1|[nber_site][]|本停+nber_conference_pages停|本停+nber_conference_pages停|未核|桥|P|P1|支|停|—|△|
|wfa_meeting|—|—|经ssrn|同元|外|缺|—|mo|支|—|—|‡|
|sfs_cavalcade|—|—|—|—|—|缺|—|mo|支|—|—|‡|
|efa_meeting|—|—|—|—|未核|缺|—|P2|支|—|—|⚑RECHECK ‡|
|aom_proceedings|XD|[XD][]|XD|XD|外|零|P|P2|支|W4|CL2+|—|
|sed_meetings|BK|[repec_redif][]|经repec|经repec|未核|零|P|P2|登|—|CL0|⚑RECHECK △|

### L1b 预印本与工作论文（31 行）

|来源|族|连接器|元|新|全|码|执|状态|支|波|CL|前置|
|---|---|---|---|---|---|---|---|---|---|---|---|---|
|arxiv|V1|[arxiv_oai][]|本|本|OA链+外|桥|P|P0|支|W0|CL3|△|
|chemrxiv|XD|[XD][]|XD|XD|OA链|零|P|P0|支|W1|CL3|⚑DRIFT|
|biorxiv|XD|[biorxiv_api][]|XD+本|XD+FD|OA链|新|P|P0|支|W1|CL3|⚑DRIFT △|
|medrxiv|XD|[biorxiv_api][]|XD+本|XD+FD|OA链|配|P|P0|支|W1|CL3|⚑DRIFT △|
|psyarxiv|XD|[osf_api][]|XD+经europe_pmc+本|XD+经europe_pmc|OA链|新|P|P0|支|W1|CL3|⚑ROBOTS(OSF)|
|osf_preprints|XD|[XD][]|XD|XD|OA链|零|P|P1|支|W3|CL3|—|
|socarxiv|XD|[XD][]|XD|XD|OA链|零|P|P1|支|W3|CL3|—|
|research_square|XD|[XD][]|XD+经europe_pmc|XD+经europe_pmc|OA链|零|P|P1|支|W3|CL3|—|
|preprints_org|XD|[XD][]|XD+经europe_pmc|XD+经europe_pmc|OA链|零|P|P1|支|W3|CL3|—|
|authorea|XD|[XD][]|XD+经europe_pmc|XD+经europe_pmc|未核|零|P|P2|登|—|CL0|—|
|ess_open_archive|XD|[XD][]|XD|XD|未核|零|P|P2|登|—|CL0|—|
|eartharxiv|XD|[eartharxiv_janeway][SS5]|XD+本|XD|未核|新|P|P2|登|—|CL0|—|
|optica_open|XD|[XD][]|XD|XD|未核|零|P|P2|登|—|CL0|—|
|techrxiv|XD|[XD][]|XD|XD|OA链|零|P|P1|支|W3|CL3|—|
|iacr_eprint|OAI|[OAI][]|OAI|FD|外|配|P|mo1|支|W3|CL3|⚑ROBOTS △|
|eccc|—|—|—|—|OA链|缺|—|P2|登|—|CL0|⚑RECHECK|
|ssrn|V1|[ssrn_crossref][]|本|本|外|桥|P|mo0|支|W2|CL3|⚑DRIFT △|
|chinaxiv|—|—|—|—|OA链|缺|—|P2（观察）|登|—|CL0|⚑RECHECK|
|paper_edu_cn|—|—|—|—|OA链|缺|—|P2（暂缓）|登|—|CL0|⚑RECHECK|
|nber_wp|XD|[nber_site][]|XD+经repec|FD停|本停|桥|M|P0|支|W1+W2|CL3|⚑LIC(仅周更文件) △ T&C禁|
|cepr_dp|BK|[repec_redif][]|经repec|经repec|外|零|P|mo|登|—|CL0|△|
|iza_dp|BK|[repec_redif][]|经repec|经repec|外|零|P|P1|支|W3|CL3|△|
|fed_board_wp|XD|[FD][]|XD|FD|未核|配|P|P1|支|W3|CL3|—|
|ecb_wp|FD|[FD][]|FD|FD|未核|配|P|P1|支|W3|CL3|—|
|bis_wp|FD|[FD][]|FD|FD|未核|配|P|P1|支|W3|CL3|—|
|imf_wp|XD|[XD][]|XD+经repec|XD+经repec|未核|零|P|P1|支|W3|CL3|△|
|worldbank_prwp|SS|[worldbank_dr_api][]|本|本|未核|新|P|P1|支|W3|CL3|—|
|hbs_wp|XD|[ssrn_crossref][]|经ssrn|经ssrn|外|零|P|mo2|登|—|CL0|—|
|mpra|BK|[repec_redif][]|经repec|经repec|外|零|P|mo2|登|—|CL0|△|
|cesifo_wp|BK|[repec_redif][]|经repec|经repec|未核|零|P|P2|登|—|CL0|⚑RECHECK △|
|other_cb_wp|XD|[FD][]|XD+FD+经repec|XD+FD+经repec|未核|配|P|P2|登|—|CL0|⚑RECHECK △|

### L1c 长尾一级产出（0 行）

本类暂无来源行（候选见[候选来源](source-candidates.md)）。

### L2a 文献库与学科仓储（21 行，另 6 行不接入）

|来源|族|连接器|元|新|全|码|执|状态|支|波|CL|前置|
|---|---|---|---|---|---|---|---|---|---|---|---|---|
|europe_pmc|AG|[europe_pmc_rest][]|本+europe_pmc_bulk|本|OA链|新|P|P0|支|W0+W2|CL3|⚑ROBOTS(bulk) △|
|pubmed|BK|[pubmed_baseline][]|本+pubmed_eutils|本+pubmed_eutils|—|新|P|P0|支|W1+W2|CL3|⚑ROBOTS|
|inspire_hep|AG|[inspire_rest][]|本|本|外|新|P|P0|支|W1|CL3|—|
|nasa_ads_scix|AG|[nasa_ads_api][]|本|本|外|新|U|P1|支|W3u|CL0|⚑DRIFT P-13|
|zbmath_open|AG|[zbmath_open_api][]|本+OAI+zbmath_kg_dump|本+OAI+zbmath_kg_dump|外|新|P|P0|支|W1+W2|CL3|⚑SA ⚑COMM(MSC)|
|pubchem|AG|[pubchem_pug_rest][AG5]|本|同元|—|新|P|P2|支|W4|CL2+|⚑ROBOTS|
|eudml|OAI|[OAI][]|OAI|OAI|外|配|P|P2|支|W4|CL2+|⚑RECHECK|
|repec|V1|[repec_redif][]|本|本|外|桥|P|P0|支|W2|CL3|△|
|econbiz|AG|[econbiz_api][]|本|本|外|新|P|P1|支|W3|CL3|—|
|dblp|V1|[dblp_drops_snapshot][]|本+dblp_sparql|本+dblp_sparql|外|桥|P|P0（快照形态）|支|W1+W2|CL3|—|
|cinii_research|BK|[cinii_resourcesync][BK5]|本|同元|外|新|P|P2|支|W4|CL2+|⚑ROBOTS(OpenSearch)|
|zenodo|OAI|[OAI][]|OAI|OAI|未核|配|P|P2|支|W4|CL2+|△|
|hal|AG|[hal_api][AG5]|本+OAI|本+OAI|OA链|新|P|P2|支|W4|CL2+|⚑ROBOTS △|
|pmc|BK|[pmc_s3][]|本+OAI+pmc_bioc|同元|本+OAI+pmc_bioc|新|P|P0|支|W1+W2|CL3|⚑ROBOTS(E-util) △|
|psycharchives|OAI|[OAI][]|OAI|OAI|OA链|配|P|P2|支|W4|CL2+|—|
|scoap3_repo|AG|[scoap3_api][]|本|同元|本|新|P|P1|支|W3|CL3|—|
|osti_gov|AG|[osti_api][AG5]|本|本|未核|新|P|P2|支|W4|CL2+|⚑RECHECK|
|econstor|OAI|[OAI][]|OAI|OAI|OA链|配|P|P1|支|W3|CL3|—|
|ssoar|—|—|旁路(CORE/OpenAlex)|同元|OA链|缺|—|mo|支|—|—|⚑RECHECK ‡|
|jstor|XD|[XD][]|XD|XD|外|零|P|mo2|支|W4|CL2+|—|
|fraser|AG|[fraser_api][AG5]|本|本|未核|新|P|P2|支|W4|CL2+|⚑RECHECK|

### L2b 检索引擎与聚合项目（14 行，另 8 行不接入）

|来源|族|连接器|元|新|全|码|执|状态|支|波|CL|前置|
|---|---|---|---|---|---|---|---|---|---|---|---|---|
|openalex|V1|[openalex_api][]|本+openalex_snapshot|本+openalex_snapshot|OA链|桥|P|P0|支|W2|CL3|⚑BUDGET △|
|s2|V1|[s2_api][]|本+s2_datasets|本+s2_datasets|OA链|桥|P|P1|支|W3|CL3|⚑COMM|
|openaire|BK|[openaire_graph_dump][BK5]|本+openaire_api|同元|外|新|P|P2|支|W4|CL2+|—|
|lens|AG|[lens_api][AG5]|本|同元|—|新|U|mo|支|W4u|CL0|P-13|
|core|AG|[core_api][]|本|同元|本|新|P|P1|支|W3|CL3|⚑LIC ⚑COMM|
|unpaywall|V1|[unpaywall_api][]|—|—|本|桥|P|P1|支|W2|CL3|—|
|doaj|AG|[doaj_api][]|本+OAI+doaj_csv|同元|OA链|新|P|P1|支|W3|CL3|△|
|fatcat_ia_scholar|—|—|—|—|未核|缺|—|mo|支|—|—|‡|
|pubtator3|AG|[pubtator3_api][]|本|同元|—|新|P|P1|支|W3|CL3|⚑RECHECK|
|icite|AG|[icite_api][]|本|同元|—|新|P|P1|支|W3|CL3|⚑RECHECK|
|opencitations|AG|[opencitations_api][]|本+opencitations_dump|本+opencitations_dump|—|新|P|P1|支|W3|CL3|—|
|hf_papers|AG|[hf_papers_api][]|本|本|—|新|P|P0（信号层）|支|W1|CL3|⚑RECHECK(仅商用条款)|
|pwc_archive|BK|[pwc_archive_import][]|本|同元|—|新|P|P1|支|W3|CL3|⚑SA|
|alphaxiv|AG|[alphaxiv_mcp][AG5]|本|同元|外|新|U|P2|支|W4u|CL0|P-13|

## 支持但无连接器与上游重大变化

### 支持但无连接器（5 行）

名录定为"支持"，长稿却无通道或连接器。本表不排波次、CL 记"—"，处置见未决 4（会议标签人工维护、链接来源另定契约）。

|来源|名录"怎么接"|名录"全文"|闸门|
|---|---|---|---|
|`wfa_meeting`|经 SSRN 版本关联|仅外链（经 SSRN）|—|
|`sfs_cavalcade`|人工维护会议标签|无（robots 禁止）|—|
|`efa_meeting`|待复勘|未核|⚑RECHECK|
|`ssoar`|经 CORE/OpenAlex 旁路|OA，仅外链|⚑RECHECK|
|`fatcat_ia_scholar`|仅作链接来源|IA 存档副本链接|—|

### 上游有重大变化的来源

事实摘自第一阶段逐源调研（2026-09-30 实测与一手文档），逐条出处见卡片 §3 与[实施计划](../plan/v2/connectors/implementation-plan.md#上游变化风险)，下表只留计划未收的主出处。

|来源|变化|本批处置|卡片|
|---|---|---|---|
|`nber_wp`、`nber_conferences`|T&C 2026-08-01 起禁止未经许可的自动访问与数据挖掘|nber.org 全部主机零自动化，平台侧与用户侧都暂停；元数据经 Crossref 10.3386 与 RePEc `nbr:nberwo`；影响 P0 验收口径，待拍板|[nber_site][]、[nber_conference_pages][]|
|`arxiv`|`arxiv.org` 禁 `/api`、`export.arxiv.org` 全禁 [https://arxiv.org/robots.txt, 2026-09-30]；OAI 主机 robots 404 [https://oaipmh.arxiv.org/robots.txt, 2026-09-30]|平台侧只用 OAI-PMH（arXivRaw）；SCD 不声明 search|[arxiv_oai][]|
|`openalex`|`from_created_date` 实测 429 "Plan upgrade required"；per_page ≤100、按量付费、快照带 `deleted_ids`（见卡片）|增量用季度快照 + `updated_date` 分区 + Crossref 兜底；API 只做 lookup 与 enrich，进美元预算|[openalex_api][]、[openalex_snapshot][]|
|`pmc`|OA Web Service 2026-08-25 下线，旧 FTP 已删|用 S3 `pmc-oa-opendata`、OAI-PMH、BioC；E-utilities 仍 ⚑ROBOTS|[pmc_s3][]、[pmc_bioc][]|
|`europe_pmc`|`INDEX_DATE` 增量静默返回 0（实测，2026-09-30）；bulk 主机 robots 全禁（见卡片）|只用 `FIRST_IDATE` 日窗，加"静默零"探针；bulk 待 EBI 书面确认|[europe_pmc_rest][]、[europe_pmc_bulk][]|
|`orcid`|Public API 凭证发给个人、禁持续轮询、不得用于营收产品（见卡片）；`pub.orcid.org` robots 全禁 [https://pub.orcid.org/robots.txt, 2026-09-30]|平台侧只用年度 CC0 文件；`orcid_api` 改用户侧 OAuth，契约 v1 停在 CL0（P-13）|[orcid_public_data_file][]、[orcid_api][]|
|`crossref`|按请求类分池、按 mailto 限流（见卡片）；分池生效日期 2025-12-01 与 2026-07-21 两说，待核|令牌桶"凭证"维含部署 mailto，全平台集中限速；`/members` 按列表池估算，待核|[crossref_delegated][]、[crossref_rest][]|
|`repec` 及其代收行|数据默认非商用（见卡片）|建议补 ⚑COMM，待拍板|[repec_redif][]|
|`hal`|OAI 条款不得商用|建议补 ⚑COMM，待拍板|[hal_api][AG5]|
|`iop`|2026-07 T&DM 政策：API、feed、MCP、agent 另签协议（见卡片）|维持零自动化，只经 Crossref|[crossref_delegated][]|
|`openreview`|匿名 `/notes` 返回 403 ChallengeRequiredError [https://api2.openreview.net/notes, 2026-09-30]；ToS 禁第三方代用户访问（见卡片）|平台侧继续停用；用户 token 只在扩展或 pc-agent|[openreview_api][]|
|`biorxiv`、`medrxiv`|新 DOI 前缀 10.64898；medRxiv 出现 version "0"（见卡片）|两个前缀都登记；加 schema 漂移探针|[biorxiv_api][]|
|`ssrn`|约 75% 记录的 license 指向 USPTO 页面（见卡片）|映射为保留所有权利，不共享|[ssrn_crossref][]|
|其他|ROR v1 已 410；Zenodo exporter 在 robots 禁止的 `/api` 下；IACR robots 放宽；DOAJ OAI 滞后可达 30 天，ACS robots 由 403 变 200，ScienceDirect robots 对我们的 UA 403；CVF 对部分 UA 403（原因未核）|照实写进卡片；闸门只降不升，放宽类只提"待评审"|[ror_dump][]、[doaj_api][]、[oai_pmh][]、[cvf_open_access_pages][]、[elsevier_tdm][]|

## 不接入（18 行）

平台对这些来源零自动化，无连接器、无波次；理由详见[名录排除清单](source-directory.md#排除清单)。

|来源|状态|原因|
|---|---|---|
|`pirate_sources`|excluded|盗版影子库，项目红线|
|`google_scholar`|excluded|无 API，robots 与 ToS 禁止自动查询；只接受用户导出后上传|
|`base`|excluded|API 须 IP 白名单、robots 全禁、有工作量证明挑战；覆盖经 CORE、OpenAIRE、OpenAlex 间接获得|
|`dimensions`|excluded|只对非商业科学计量研究免费|
|`scopus`|excluded|按用例授权；用户可自带 key 在本人私域富化|
|`web_of_science`|excluded|订阅加使用政策；用户可自带 key|
|`microsoft_academic`|excluded|2021 年底关停，只兼容 `mag` 外部 ID|
|`scirate`|excluded|robots.txt 在挑战门之后|
|`paper_copilot`|excluded|GitHub 数据没有许可|
|`conf_virtual_sites`|excluded|数据在 robots 禁区与未文档化接口里|
|`informs_annual`|excluded|只有摘要级程序，没有论文|
|`hbp_hbr`|excluded|Crossref 查无该刊，无可枚举 DOI|
|`econlit`|excluded|订阅书目，无公开 API 与数据许可|
|`mathscinet`|link-only|robots 基本全禁，按 MR 号外链|
|`cas_scifinder`|link-only|条款禁止脚本批量抽取与 AI 用途|
|`cnki`|user-import-only|robots 全禁，无开放 API；只收用户导出题录|
|`wanfang`|user-import-only|检索子域 WAF 拦截，无开放 API|
|`cqvip`|user-import-only|robots 部分禁止，无开放 API|

长稿给 `scopus`、`web_of_science` 写的"可选 aggregator_api 用户侧"本批不设连接器，不列入计划。

## 连接器反查表

89 个 connector_id，顺序同 E 清单（按最高服务优先级、再按族）。"波"：首个为构建波次，其后为接入后续来源行的波次。服务来源先列直接出现在其通道里的行，再列名录写"经 x"、由它代收的行。CL 为所承接通道的目标（P-13 见约定）；桥接 id 移植、并入实例或拆分后转 CLX。

|#|连接器|族|执|波|CL|服务来源（直接；经代收；多于 1 个注数目）|
|---:|---|---|---|---|---|---|
|1|[crossref_delegated][]|XD|P|W0+W1+W3+W4|CL3|92：主表元、新两列含 XD 的行；经代收 ecva|
|2|[feed][]|FD|P|W1+W3|CL3|17：nature_portfolio frontiers aaas_science siam scipost pnas quantum_journal elife jmlr biorxiv medrxiv iacr_eprint nber_wp fed_board_wp ecb_wp bis_wp other_cb_wp|
|3|[oai_pmh][]|OAI|P|W0+W1+W3+W4|CL3|15：mdpi econsoc_journals centre_mersenne_numdam episciences lipics_drops cogsci_proceedings iacr_eprint zbmath_open eudml zenodo hal pmc psycharchives econstor doaj|
|4|[atypon_user][]|PF|U|W3u|CL3|7：wiley tandf_online sage_journals uchicago_journals siam informs_pubsonline aom_journals|
|5|[aaai_ojs_oai][]|V1→OAI|P|W2|CL3|aaai_ojs|
|6|[acl_anthology_xml][]|V1→SS|P|W2|CL3|acl_anthology|
|7|[aea_fulltext_user][]|V1→SS|U|W3u|CL3|aea_journals|
|8|[arxiv_oai][]|V1→OAI|P|W0|CL3|arxiv|
|9|[crossref_rest][]|V1→AG|P|W0|CL3|crossref|
|10|[cvf_open_access_pages][]|V1→SS|P|W2|CL3|cvf_open_access|
|11|[dblp_drops_snapshot][]|V1→BK|P|W2|CL3|dblp|
|12|[econsoc_fulltext][]|V1→SS|M|W3u|CL3|econsoc_journals|
|13|[elsevier_tdm][]|V1→TDM|U|W3u|CL3|elsevier_sd|
|14|[nber_site][]|V1→SS|M|停|—|2：nber_conferences nber_wp|
|15|[neurips_proceedings_pages][]|V1→SS|P|W2|CL3|neurips_proceedings|
|16|[openalex_api][]|V1→AG|P|W2|CL3|openalex|
|17|[openreview_api][]|V1→SS|M|W3u 占位|CL0（用户侧待 P-13）|openreview；经代收 tmlr|
|18|[pmlr_volumes][]|V1→SS|P|W2|CL3|pmlr|
|19|[repec_redif][]|V1→BK|P|W2|CL3|repec；经代收 8：sed_meetings nber_wp cepr_dp iza_dp imf_wp mpra cesifo_wp other_cb_wp|
|20|[silverchair_user][]|V1→PF|U|W3u+W4u|CL3|5：oup_academic aip aaa_pubs geoscienceworld misq|
|21|[wiley_tdm][]|V1→TDM|U|W3u|CL3|wiley|
|22|[dblp_sparql][]|AG|P|W1|CL3|dblp|
|23|[europe_pmc_rest][]|AG|P|W0|CL3|europe_pmc；经代收 5：f1000_platforms psyarxiv research_square preprints_org authorea|
|24|[hf_papers_api][]|AG|P|W1|CL3|hf_papers|
|25|[inspire_rest][]|AG|P|W1|CL3|inspire_hep；经代收 pos_sissa|
|26|[pmc_bioc][]|AG|P|W1|CL3|pmc|
|27|[pubmed_eutils][]|AG|P|W1|CL3|pubmed|
|28|[zbmath_open_api][]|AG|P|W1|CL3|zbmath_open|
|29|[crossref_annual_file][]|BK|P|W2|CL3|crossref|
|30|[europe_pmc_bulk][]|BK|P|W2|CL3|europe_pmc|
|31|[openalex_snapshot][]|BK|P|W2|CL3|openalex|
|32|[pmc_s3][]|BK|P|W2|CL3|pmc|
|33|[pubmed_baseline][]|BK|P|W2|CL3|pubmed；经代收 psb_proceedings|
|34|[zbmath_kg_dump][]|BK|P|W2|CL3|zbmath_open|
|35|[springer_nature_api][]|TDM|U|W3u|CL3|2：springer_link nature_portfolio|
|36|[aps_harvest][]|SS|P|W1|CL3|aps|
|37|[biorxiv_api][]|SS|P|W1|CL3|2：biorxiv medrxiv|
|38|[ijcai_proceedings_pages][]|SS|P|W1|CL3|ijcai_proceedings|
|39|[jmlr_volumes][]|SS|P|W1|CL3|jmlr|
|40|[osf_api][]|SS|P|W1|CL3|psyarxiv|
|41|[tmlr_list][]|SS|P|W1|CL3|tmlr|
|42|[ssrn_crossref][]|V1→XD|P|W2|CL3|ssrn；经代收 2：wfa_meeting hbs_wp|
|43|[s2_api][]|V1→AG|P|W3|CL3|s2|
|44|[unpaywall_api][]|V1→AG|P|W2|CL3|unpaywall|
|45|[core_api][]|AG|P|W3|CL3|core|
|46|[datacite_rest][]|AG|P|W3|CL3|2：lipics_drops datacite|
|47|[doaj_api][]|AG|P|W3|CL3|doaj|
|48|[econbiz_api][]|AG|P|W3|CL3|econbiz|
|49|[icite_api][]|AG|P|W3|CL3|icite|
|50|[nasa_ads_api][]（P-13）|AG|U|W3u|CL0|nasa_ads_scix|
|51|[opencitations_api][]|AG|P|W3|CL3|opencitations|
|52|[orcid_api][]（P-13）|AG|U|W3u|CL0|orcid|
|53|[pubtator3_api][]|AG|P|W3|CL3|pubtator3|
|54|[scoap3_api][]|AG|P|W3|CL3|scoap3_repo|
|55|[datacite_annual_file][]|BK|P|W3|CL3|datacite|
|56|[doaj_csv][]|BK|P|W3|CL3|doaj|
|57|[opencitations_dump][]|BK|P|W3|CL3|opencitations|
|58|[orcid_public_data_file][]|BK|P|W3|CL3|orcid|
|59|[pwc_archive_import][]|BK|P|W3|CL3|pwc_archive|
|60|[ror_dump][]|BK|P|W3|CL3|ror|
|61|[s2_datasets][]|BK|P|W3|CL3|s2|
|62|[assa_program][]|SS|P|W3|CL3|assa_meetings|
|63|[cambridge_core_user][]（撤销†）|PF|U|撤销|—|cambridge_core|
|64|[ecva_papers][]|SS|P|W3|CL3|ecva|
|65|[elife_api][]|SS|P|W3|CL3|elife|
|66|[ieee_xplore_user][]（撤销†）|SS|U|撤销|—|ieee_xplore|
|67|[isca_archive_pages][]|SS|P|W3|CL3|isca_archive|
|68|[nber_conference_pages][]|SS|P|停|—|nber_conferences|
|69|[plos_search_api][]|SS|P|W3|CL3|plos|
|70|[pvldb_volumes][]|SS|P|W3|CL3|pvldb|
|71|[usenix_sessions][]|SS|P|W3|CL3|usenix|
|72|[worldbank_dr_api][]|SS|P|W3|CL3|worldbank_prwp|
|73|[alphaxiv_mcp][AG5]（P-13）|AG|U|W4u|CL0|alphaxiv|
|74|[fraser_api][AG5]|AG|P|W4|CL2+|fraser|
|75|[hal_api][AG5]|AG|P|W4|CL2+|hal|
|76|[jstage_webapi][AG5]|AG|P|—|CL0|jstage|
|77|[open_policy_finder_api][AG5]|AG|P|W4|CL2+|open_policy_finder|
|78|[openaire_api][AG5]|AG|P|W4|CL2+|openaire|
|79|[osti_api][AG5]|AG|P|W4|CL2+|osti_gov|
|80|[pubchem_pug_rest][AG5]|AG|P|W4|CL2+|pubchem|
|81|[scielo_articlemeta][AG5]|AG|P|—|CL0|scielo|
|82|[wikidata_sparql][AG5]|AG|P|W4|CL2+|wikidata|
|83|[cinii_resourcesync][BK5]|BK|P|W4|CL2+|cinii_research|
|84|[openaire_graph_dump][BK5]|BK|P|W4|CL2+|openaire|
|85|[wikidata_dump][BK5]|BK|P|W4|CL2+|wikidata|
|86|[ceur_ws_volumes][SS5]|SS|P|—|CL0|ceur_ws|
|87|[eartharxiv_janeway][SS5]|SS|P|—|CL0|eartharxiv|
|88|[rss_proceedings_volumes][SS5]|SS|P|—|CL0|rss_proceedings|
|89|[lens_api][AG5]（P-13）|AG|U|W4u|CL0|lens|

[crossref_delegated]: ../plan/v2/connectors/families/crossref-delegated.md#crossref_delegated
[feed]: ../plan/v2/connectors/families/feed.md#feed
[oai_pmh]: ../plan/v2/connectors/families/oai-pmh.md#oai_pmh
[atypon_user]: ../plan/v2/connectors/families/platform-family.md#atypon_user
[aaai_ojs_oai]: ../plan/v2/connectors/families/oai-pmh.md#aaai_ojs_oai
[acl_anthology_xml]: ../plan/v2/connectors/families/site-special.md#acl_anthology_xml
[aea_fulltext_user]: ../plan/v2/connectors/families/site-special.md#aea_fulltext_user
[arxiv_oai]: ../plan/v2/connectors/families/oai-pmh.md#arxiv_oai
[crossref_rest]: ../plan/v2/connectors/families/v1-bridge.md#crossref_rest
[cvf_open_access_pages]: ../plan/v2/connectors/families/site-special.md#cvf_open_access_pages
[dblp_drops_snapshot]: ../plan/v2/connectors/families/v1-bridge.md#dblp_drops_snapshot
[econsoc_fulltext]: ../plan/v2/connectors/families/site-special.md#econsoc_fulltext
[elsevier_tdm]: ../plan/v2/connectors/families/official-tdm-api.md#elsevier_tdm
[nber_site]: ../plan/v2/connectors/families/site-special.md#nber_site
[neurips_proceedings_pages]: ../plan/v2/connectors/families/site-special.md#neurips_proceedings_pages
[openalex_api]: ../plan/v2/connectors/families/v1-bridge.md#openalex_api
[openreview_api]: ../plan/v2/connectors/families/site-special.md#openreview_api
[pmlr_volumes]: ../plan/v2/connectors/families/site-special.md#pmlr_volumes
[repec_redif]: ../plan/v2/connectors/families/v1-bridge.md#repec_redif
[silverchair_user]: ../plan/v2/connectors/families/platform-family.md#silverchair_user
[wiley_tdm]: ../plan/v2/connectors/families/official-tdm-api.md#wiley_tdm
[dblp_sparql]: ../plan/v2/connectors/families/aggregator-api.md#dblp_sparql
[europe_pmc_rest]: ../plan/v2/connectors/families/aggregator-api.md#europe_pmc_rest
[hf_papers_api]: ../plan/v2/connectors/families/aggregator-api.md#hf_papers_api
[inspire_rest]: ../plan/v2/connectors/families/aggregator-api.md#inspire_rest
[pmc_bioc]: ../plan/v2/connectors/families/aggregator-api.md#pmc_bioc
[pubmed_eutils]: ../plan/v2/connectors/families/aggregator-api.md#pubmed_eutils
[zbmath_open_api]: ../plan/v2/connectors/families/aggregator-api.md#zbmath_open_api
[crossref_annual_file]: ../plan/v2/connectors/families/bulk-snapshot.md#crossref_annual_file
[europe_pmc_bulk]: ../plan/v2/connectors/families/bulk-snapshot.md#europe_pmc_bulk
[openalex_snapshot]: ../plan/v2/connectors/families/bulk-snapshot.md#openalex_snapshot
[pmc_s3]: ../plan/v2/connectors/families/bulk-snapshot.md#pmc_s3
[pubmed_baseline]: ../plan/v2/connectors/families/bulk-snapshot.md#pubmed_baseline
[zbmath_kg_dump]: ../plan/v2/connectors/families/bulk-snapshot.md#zbmath_kg_dump
[springer_nature_api]: ../plan/v2/connectors/families/official-tdm-api.md#springer_nature_api
[aps_harvest]: ../plan/v2/connectors/families/site-special.md#aps_harvest
[biorxiv_api]: ../plan/v2/connectors/families/site-special.md#biorxiv_api
[ijcai_proceedings_pages]: ../plan/v2/connectors/families/site-special.md#ijcai_proceedings_pages
[jmlr_volumes]: ../plan/v2/connectors/families/site-special.md#jmlr_volumes
[osf_api]: ../plan/v2/connectors/families/site-special.md#osf_api
[tmlr_list]: ../plan/v2/connectors/families/site-special.md#tmlr_list
[ssrn_crossref]: ../plan/v2/connectors/families/v1-bridge.md#ssrn_crossref
[s2_api]: ../plan/v2/connectors/families/v1-bridge.md#s2_api
[unpaywall_api]: ../plan/v2/connectors/families/v1-bridge.md#unpaywall_api
[core_api]: ../plan/v2/connectors/families/aggregator-api.md#core_api
[datacite_rest]: ../plan/v2/connectors/families/aggregator-api.md#datacite_rest
[doaj_api]: ../plan/v2/connectors/families/aggregator-api.md#doaj_api
[econbiz_api]: ../plan/v2/connectors/families/aggregator-api.md#econbiz_api
[icite_api]: ../plan/v2/connectors/families/aggregator-api.md#icite_api
[nasa_ads_api]: ../plan/v2/connectors/families/aggregator-api.md#nasa_ads_api
[opencitations_api]: ../plan/v2/connectors/families/aggregator-api.md#opencitations_api
[orcid_api]: ../plan/v2/connectors/families/aggregator-api.md#orcid_api
[pubtator3_api]: ../plan/v2/connectors/families/aggregator-api.md#pubtator3_api
[scoap3_api]: ../plan/v2/connectors/families/aggregator-api.md#scoap3_api
[datacite_annual_file]: ../plan/v2/connectors/families/bulk-snapshot.md#datacite_annual_file
[doaj_csv]: ../plan/v2/connectors/families/bulk-snapshot.md#doaj_csv
[opencitations_dump]: ../plan/v2/connectors/families/bulk-snapshot.md#opencitations_dump
[orcid_public_data_file]: ../plan/v2/connectors/families/bulk-snapshot.md#orcid_public_data_file
[pwc_archive_import]: ../plan/v2/connectors/families/bulk-snapshot.md#pwc_archive_import
[ror_dump]: ../plan/v2/connectors/families/bulk-snapshot.md#ror_dump
[s2_datasets]: ../plan/v2/connectors/families/bulk-snapshot.md#s2_datasets
[assa_program]: ../plan/v2/connectors/families/site-special.md#assa_program
[cambridge_core_user]: ../plan/v2/connectors/families/platform-family.md#cambridge_core_user
[ecva_papers]: ../plan/v2/connectors/families/site-special.md#ecva_papers
[elife_api]: ../plan/v2/connectors/families/site-special.md#elife_api
[ieee_xplore_user]: ../plan/v2/connectors/families/site-special.md#ieee_xplore_user
[isca_archive_pages]: ../plan/v2/connectors/families/site-special.md#isca_archive_pages
[nber_conference_pages]: ../plan/v2/connectors/families/site-special.md#nber_conference_pages
[plos_search_api]: ../plan/v2/connectors/families/site-special.md#plos_search_api
[pvldb_volumes]: ../plan/v2/connectors/families/site-special.md#pvldb_volumes
[usenix_sessions]: ../plan/v2/connectors/families/site-special.md#usenix_sessions
[worldbank_dr_api]: ../plan/v2/connectors/families/site-special.md#worldbank_dr_api
[AG5]: ../plan/v2/connectors/families/aggregator-api.md#5-连接器清单总表
[BK5]: ../plan/v2/connectors/families/bulk-snapshot.md#5-连接器清单总表
[SS5]: ../plan/v2/connectors/families/site-special.md#5-连接器清单总表
[XD]: ../plan/v2/connectors/families/crossref-delegated.md#crossref_delegated
[OAI]: ../plan/v2/connectors/families/oai-pmh.md#oai_pmh
[FD]: ../plan/v2/connectors/families/feed.md#feed
[AT]: ../plan/v2/connectors/families/platform-family.md#atypon_user
[SC]: ../plan/v2/connectors/families/platform-family.md#silverchair_user

## 逐行核对与对 E 清单的修正

- **名录核对**：脚本逐行比对名录与 E 清单 187 行的 id、七类、状态、闸门（含范围）、支持、"怎么接"、"全文"，全部一致；本表 169 + 18 行再对名录，id、七类、顺序、状态、闸门、支持零差异（9 行闸门范围缩写）。
- **本表与 E 清单对不上的行**（均按裁定，名录未改）：
  - `ieee_xplore`：撤销 `ieee_xplore_user`。注册表 lint 12 规定 `ieee_xplore`、`acs`、`acm_dl` 的全文通道只能 `link_out` 或 `none`，不得引用任何 FulltextRecipe，并对应 [08](../plan/v2/08-compliance-security-privacy.md) HC-27；全文改外链。
  - `cambridge_core`：撤销 `cambridge_core_user`。长稿 03 §7.9 规定无官方 API 的出版商除 Crossref 外不写取回代码、用户侧才走平台族配方；robots.txt 被 CF 挑战，按 RFC 9309 视为全禁，配方签发门恒假（platform-family 卡建议 `link_only`）；全文改外链。
  - `orcid`：`orcid_api` 由平台侧改为用户侧 OAuth（执 P→M）。
  - `nber_wp`：`feed`（back.nber.org RSS）与 `nber_site` 平台侧、用户侧全部标"停"，只留 Crossref、经 repec 代收，全文只外链（见未决 3）；`nber_conferences`：两条通道都在 nber.org，全部暂停。
  - `nasa_ads_scix`、`lens`、`alphaxiv`：`RecipeProvider` 只产 `FulltextRecipe`，行级 CL 随 P-13 记 CL0；`orcid` 的平台侧年度文件仍 CL3。
  - `openreview`、`tmlr`：⚑ACCT 解除前 `openreview_api` 平台侧停用（匿名 `/notes` 403），只排用户侧 W3u，`tmlr` 的"经openreview"随之停，与族卡、实施计划一致。
  - `wfa_meeting`：E 清单记 connector_id 为代收的 `ssrn_crossref`，码却为"缺"；本表按"支持但无连接器"处理。
- **卡片链接**：一个 id 只链一处卡片（见未决 9）；P2 与登记连接器不单独成卡，链到该族"连接器清单总表"；80 个引用式链接定义的锚点已逐个对照族文档（校验脚本只查行内链接）。

## 维护方式

- 实现期由注册表生成：行来自 `registry/sources/<source_id>.yaml`，服务关系来自 `registry/connectors/<connector_id>.yaml` 的 `serves[]`，波次来自实施计划，CL 取 `conformance.target` 与 `declared`；数字不手改，与名录同一次提交更新。
- 生成器检查：每个支持行至少有一个在册连接器，否则标 ‡ 并进待拍板；每个 connector_id 在反查表恰好出现一次、只有一张卡片、锚点存在；主表与反查表的服务关系互逆；数字概览与名录的差异逐项有说明。
- 运行态（`cl_effective`、health、配额、暂停）不写回本表，只在运维台显示。
- 本批由脚本从 E 清单生成（脚本不入库）；名录状态与闸门的变更按[名录维护规则](source-directory.md#名录怎么维护)审批后重新生成本表。

## 怎么验收

- 169 个非排除行与 18 个不接入行同名录逐行一致（id、七类、状态、闸门、支持），核对差异为 0。
- 每个非排除行有连接器或明确标记（‡、停、登记）；89 个 connector_id 在反查表各出现一次，撤销项附理由。
- "连接器"列与反查表的链接落到族文档里的 `### <connector_id>` 卡片，P2 与只服务登记行的 17 个落到该族"连接器清单总表"。
- 数字概览与名录的每处差异都有说明；波次与 CL 与实施计划、一致性文档一致，调整项在实施计划里列出。
- ≤45 KiB，frontmatter 与相对链接通过校验。

## 未决事项

1. **撤销两个用户侧连接器**：名录全文列仍写"用户侧私有"；IEEE 是否允许打开后一键保存（IEEE 禁止私有派生）；Cambridge 在 robots 可读后是否改用 platform_family 配方；名录复勘时概览数字 66/93/27 是否改为 68/91/26。
2. **ORCID**：`orcid_api` 改用户侧 OAuth（长稿为"P（用户授权）"），平台侧只用年度文件。
3. **NBER**：`nber_conferences` 无可用通道，降为登记还是等书面许可；`nber_wp` 的 v2-P0 验收口径；用户侧单篇取回是否同样受 T&C 约束。本表按裁定记 `nber_site` 平台侧与用户侧全部暂停、取得书面许可前不排波次，与 site-special、feed、v1-bridge 一致；实施计划已同步（W3 34 = 24 + W3u 10，另为 `nber_site` 预留 1.5 人日，许可前不开工）。
4. **支持但无连接器 5 行**：降为登记，或补连接器与"无连接器支持行"的契约。
5. **登记行**：不运行任何连接器、停在 CL0，证据过期只标 `review_overdue`、不触发降级，lint 证据时效只对"支持"生效（D-073 的细化）。
6. **口径**：Crossref 委托 92 与 93；DataCite 委托归族（`lipics_drops`）；央行 RSS 是 feed profile 还是新连接器、`other_cb_wp` 是否拆行；6 行"仅信号"feed 是否算"需要配置"；`ams`、`assa_meetings`、`iza_dp` 有无用户侧单篇通道。
7. **CL2+ 的含义**取决于 CL2 在生产的口径（P-4：限 `on_demand` 或 deny）。
8. **repec、hal 补 ⚑COMM**，经 repec 代收的行连带。
9. **一卡一 id**：本表链接即卡片位置（`cambridge_core_user` 在 platform-family，`ieee_xplore_user` 墓碑在 site-special），其他族文档只留指向行；当前无重复标题，由生成器持续检查。
10. **混合连接器**：`econsoc_fulltext`、`nber_site`、`openreview_api` 执 M，按裁定解释为两个清单（见约定"执"）；本表各记一个 id，清单命名待契约与实施计划定。
11. **P-13**：契约 v1.x 是否增加用户侧元数据查询配方 `QueryRecipe`；通过则 `nasa_ads_api`、`orcid_api` 随 V3 批次一、`lens_api`、`alphaxiv_mcp` 随 W4 晋级，否决则转 CLX 或改外链。
12. **APS 全量**：名录全文含全量 Harvest 用户侧通道（⚑LIC），计划与族卡都未排期，本表只排 OA 子集 W1；全量 token 属用户授权还是平台许可两说（见 [aps_harvest][] 卡）。

更细的材料：长稿通道明细见 `git show v2-drafts:docs/catalog/source-directory.md`，lint 12 与 §7.9 见 `git show v2-drafts:docs/plan/v2/03-sources-and-corpus-pipeline.md`，卡片见 `docs/plan/v2/connectors/families/`。
