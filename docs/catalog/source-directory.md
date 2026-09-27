---
title: v2 来源支持名录
status: draft
owner: opus5.5-primary
updated: 2026-09-27
---

# v2 来源支持名录

> 名录回答四个问题：v2 支持哪些论文来源，每个来源的元数据与新论文怎么接，全文能做到哪一步，受哪些合规闸门约束。共 187 行，覆盖需求点名的全部学科，另补地学材料与中文/区域两组，这两组是主要缺口。多数出版商期刊不写代码，由 Crossref 委托收元数据；订阅全文只在用户侧由用户本人单篇取回，平台出口从不代用户访问出版商（见 D-053）。

来源模型见 [v2-03 来源模型图](../diagrams/v2-03-source-model.svg) 与 [03 来源接入与语料流水线](../plan/v2/03-sources-and-corpus-pipeline.md)，合规硬约束见 [08 合规、隐私、安全与内容治理](../plan/v2/08-compliance-security-privacy.md)。[v2-11 来源汇流概念图](../diagrams/v2-11-source-confluence.svg) 把本表每一行画成一条线，按主通道汇入统一语料，供对外介绍。

## 数字概览

- **总数 187 行**：L1 129 行（出版商 44、预印本与工作论文 30、期刊平台 24、会议平台 31）；L2 57 行（聚合 42、仓库 11、注册表 3、聚合兼仓储 1）；另有盗版源合并行 1 行。
- **非排除 169 行**：v2-P0 36、v2-P1 63、v2-P2 44、metadata-only 26（登记优先级 P0 3、P1 4、P2 10，未标 9）。
- **排除类 18 行**，平台零自动化：excluded 13、link-only 2、user-import-only 3。
- **接入工作量**：非排除的 169 行中，92 行的元数据或新论文通道用到 Crossref 委托；66 行只需登记，不写代码；93 行需要源专用或按源配置的 connector，其中 21 行经 `v1_bridge`（v1 adapter 包装层）复用 v1 全部 20 个 adapter；10 行暂无 connector（待复勘或经他源旁路）。
- **用户侧执行**：27 个非排除来源至少一条通道在用户侧，全是订阅全文、按用户 key 的 TDM 或 API，或用户自有 token。
- **闸门**：66 行带至少一个闸门，含义见下文约定。

按学科的覆盖（一个来源可标多个学科，各行之和大于 187；标"全"的来源只计入"跨学科"）：

| 学科组 | 来源 | 其中 v2-P0 | 评估 |
|---|---:|---:|---|
| 数学 | 24 | 6 | 主干较好：zbMATH Open、arXiv、EMS、Numdam；MathSciNet 只外链 |
| 物理 | 28 | 8 | 通道最丰富：arXiv、APS、INSPIRE、SCOAP3、ADS；IOP 站点零自动化 |
| 化学 | 14 | 5 | 最弱的理科：Crossref 摘要中位数 11%，ACS 只取元数据 |
| 生物 | 27 | 11 | L2 骨干最完整：Europe PMC、PubMed、PMC |
| 心理 | 22 | 9 | 依赖 Crossref，但 APA 期刊的摘要与参考文献覆盖都是 0% |
| 经济 | 34 | 9 | 最强之一：AEA、ECMA、NBER、RePEc；央行 WP 多有合规 RSS 或 API |
| 金融 | 25 | 7 | Top3 刊在 Wiley、Elsevier、OUP；WP 主要经 SSRN、NBER |
| 商业管理 | 27 | 6 | UTD24 中 21/24 刊在 Atypon 或 Silverchair 平台；INFORMS、AOM 为 P0 |
| CS-AI | 40 | 14 | P0 最多：OpenReview、ACL、PMLR、CVF、AAAI、IJCAI、dblp 快照；IEEE、ACM 只取元数据 |
| 地学材料 | 12 | 5 | 最薄：地学专属只有 3 行且全为 P2，材料没有专属来源 |
| 跨学科 | 41 | 3 | Crossref、OpenAlex 为主干；商业索引在平台层排除 |
| 中文/区域 | 12 | 0 | 没有 P0/P1：知网、万方、维普只能用户导入 |

## 约定

**层级类型**：L1 是论文出版或首发的地方，L2 负责汇总、登记与补全。Source 与 Venue 分离：本表按来源登记，期刊、会议等 venue 是独立实体，见 03。

| 类型 | 含义 | 行数 |
|---|---|---:|
| L1 出版商 `publisher` | 出版商与学会自营平台 | 44 |
| L1 预印本 `preprint` | 预印本服务器与工作论文系列（含央行与国际组织） | 30 |
| L1 期刊平台 `journal_platform` | 学会或专业期刊平台与过刊档案 | 24 |
| L1 会议平台 `conference_platform` | 会议论文集平台；经管会议记为"论文在某会报告过"的事件 | 31 |
| L2 聚合 `aggregator` | 跨学科与学科聚合器、OA 叠加层、社区信号层、商业索引 | 42 |
| L2 仓库 `repository` | 仓储与仓储聚合 | 11 |
| L2 注册表 `registry` | 身份、机构与 DOI 注册表 | 3 |

Europe PMC 兼属聚合与仓储，盗版源合并行不属任何层级，二者都放在 L2 聚合表。区域来源按类型分入各表，学科列带"区"。

**v2 状态**（`v2_status`）：

- `v2-P0`：首批必须接入，进入 V1 验收。
- `v2-P1`：首批之后的第一批。
- `v2-P2`：按需接入，由用户需求触发，证据可以不全。
- `metadata-only（Px）`：只收元数据，全文零自动化（外链、OA 链或用户侧单篇）；括号内是登记优先级。
- `link-only`：不收元数据，只按标识符生成外链。
- `user-import-only`：平台零自动化，只接受用户手动导出的题录。
- `excluded`：因红线、条款、授权或无通道而排除，调度器与路由器都不可选。

状态后的括号是限定语，如"信号层""快照形态""观察""暂缓"。

**闸门**：合规与运营约束标记，写在状态之后；只影响某条通道时，括号注明范围，如"⚑ROBOTS（仅 bulk）"。

| 标记 | 行数 | 含义与默认处置 |
|---|---:|---|
| ⚑ROBOTS | 10 | 文档化 API 或 bulk 主机与 robots 冲突，策略引擎标为待确认：后台批量须有书面确认，低频按需调用须先登记在 robots ADR（D-049）的例外附表 |
| ⚑ACCT | 2 | 要平台服务账号而条款要求一人一号，书面确认前只用用户本人 token（D-052） |
| ⚑COMM | 17 | 数据、API 或 TDM 条款限非商业或商用须另获许可，`platform.commercial=true` 时自动停用该通道（D-045） |
| ⚑LIC | 3 | 该通道须先取得数据许可，取得前不可用，其余通道不受影响 |
| ⚑BUDGET | 1 | 按量计费，进美元预算桶，超额时降级为快照或本地数据 |
| ⚑DRIFT | 9 | 平台迁移、端点异常或停办进行中，以替代通道为主，恢复后重勘 |
| ⚑RECHECK | 27 | 通道未核、站点不可达或 robots 不可读，启用前复勘；robots 不可读按零自动化处理 |
| ⚑SA | 2 | 数据为相同方式共享许可，派生数据集对外发布须沿用同一许可，须法务评估 |

**学科代码**：数 数学（含统计、概率）；物 物理与天文；化 化学；地材 地学与材料；生 生物、生命科学与医学；心 心理（含认知科学）；经 经济（含计量、发展、公共与政策）；金 金融（含量化金融）；管 商业与管理（含会计、营销、信息系统、运营与 OR；社会学、政治学只有简述，不在 v2.0 范围）；CS 计算机与 AI；全 跨学科、通用；区 中文/区域（横切标记，不算学科）。

**列怎么读**：

- **怎么接**：元数据与新论文的主通道。"Crossref 按 ISSN／按前缀／委托"指由通用的 Crossref 委托 connector 按刊 ISSN、DOI 前缀或其他键代收，不为该源写代码；"经 X"指由另一行来源代收；"RSS 仅信号"指 feed 只用来触发补全、不展示内容，官方 WP feed（ECB、BIS、JMLR 等）例外，可作主通道。
- **共享 OA**：OA 全文（来源自有通道或经 OA 定位链）逐篇过许可闸，许可允许再分发的进共享层，其余外链；许可未知一律不共享。共享缓存开关 `features.oa_shared_cache` 默认关闭，许可闸精度验证通过后才开。"限非商用"指 NC 许可，只在非商用部署共享。
- **用户侧私有**：订阅或授权全文只在用户显式触发时，由浏览器扩展或本地代理在用户本人会话中单篇取回，只存本人私域。robots 具名禁止 AI 爬虫的站点，在相关法律问题有结论前只给"在出版社打开 + 打开后一键保存"。
- **仅外链**：只给"在出版社打开"等外链。**无**：该源不提供全文。**许可待核**：可免费读，但再分发许可未确认，确认前外链。**未核／待复勘**：调研未能核实，启用前复勘。

## 总表

每节一张表，节内大体先高优先级、后长尾。通道描述高度压缩，实现任何 connector 之前，须回到完整草稿复核端点、限速与条款。

### L1 出版商（44 行）

| 来源 | 学科 | 怎么接 | 全文 | 状态 |
|---|---|---|---|---|
| Elsevier ScienceDirect（含 Cell Press） `elsevier_sd` | 数 物 化 地材 生 心 经 金 管 CS | Crossref 按 ISSN + PubMed | 用户侧私有 | v2-P0 ⚑COMM |
| Wiley Online Library `wiley` | 数 物 化 地材 生 心 经 金 管 | Crossref 按 ISSN | 用户侧私有 | v2-P0 ⚑COMM |
| Springer Nature Link（含 BMC、Palgrave） `springer_link` | 数 物 化 生 心 经 金 管 CS | Crossref；用户侧 SN API | 用户侧私有 | v2-P0 ⚑COMM |
| Nature Portfolio `nature_portfolio` | 物 化 地材 生 心 | Crossref 按 ISSN；RSS 仅信号 | 用户侧私有 | v2-P0 ⚑COMM |
| Oxford Academic（OUP） `oup_academic` | 数 物 生 心 经 金 管 | Crossref 按 ISSN | 用户侧私有 | v2-P0 |
| Cambridge Core `cambridge_core` | 数 物 心 经 金 管 | Crossref 按 ISSN | 用户侧私有 | v2-P1 ⚑COMM |
| Taylor & Francis Online `tandf_online` | 数 物 化 心 经 金 管 | Crossref 按 ISSN | 用户侧私有 | v2-P1 ⚑COMM |
| SAGE Journals `sage_journals` | 心 管 | Crossref 按 ISSN | 用户侧私有 | v2-P1 ⚑COMM ⚑RECHECK |
| Science / AAAS `aaas_science` | 全 | Crossref 按 ISSN；RSS 仅信号 | 共享 OA/用户侧私有 | v2-P1 |
| PNAS `pnas` | 全 | Crossref 按 ISSN；RSS 仅信号 | 共享 OA（经 PMC） | v2-P0 |
| Royal Society Publishing `royal_society` | 数 物 生 | Crossref 按 ISSN | 共享 OA/用户侧私有 | v2-P1 |
| Annual Reviews `annual_reviews` | 生 心 经 金 管 | Crossref 按 ISSN | 共享 OA | v2-P1 |
| MDPI `mdpi` | 数 物 化 地材 生 心 | Crossref + OAI-PMH | 共享 OA | v2-P1 |
| Frontiers `frontiers` | 生 心 | Crossref 按 ISSN；RSS 仅信号 | 共享 OA（经 PMC） | v2-P1 |
| PLOS `plos` | 生 心 | 官方 Search API + Crossref | 共享 OA | v2-P1 |
| APA PsycNet（APA 期刊） `apa_psycnet` | 心 管 | Crossref 按 ISSN；可用户导入 | 仅外链 | metadata-only（P2） |
| CSHL Press `cshl_press` | 生 | Crossref 按 ISSN | 共享 OA（经 PMC） | v2-P2 |
| Hogrefe `hogrefe` | 心 | Crossref 按 ISSN | 仅外链 | metadata-only（P2） |
| UC Press 期刊（Collabra: Psychology） `ucpress_online` | 心 | Crossref 按 ISSN | 共享 OA | v2-P2 ⚑RECHECK |
| American Physical Society（Physical Review） `aps` | 物 | APS Harvest + Crossref | 共享 OA/用户侧私有 | v2-P0 ⚑LIC（仅全量 Harvest） |
| IOP Publishing（含 AAS 天文刊） `iop` | 物 | Crossref 按 ISSN | 共享 OA（经他源） | metadata-only（P0） |
| AIP Publishing `aip` | 物 | Crossref 按 ISSN | 用户侧私有 | v2-P1 |
| Optica Publishing Group `optica` | 物 | Crossref 按 ISSN | 共享 OA | v2-P1 |
| EDP Sciences（A&A、EPJ WoC） `edp_sciences` | 物 | Crossref 按 ISSN | 共享 OA | v2-P1 |
| World Scientific `world_scientific` | 物 数 | Crossref 按 ISSN | 仅外链 | metadata-only（P2） |
| De Gruyter Brill `degruyter_brill` | 数 物 化 经 | Crossref 按 ISSN | 仅外链 | metadata-only（P1） |
| ACS Publications `acs` | 化 地材 | Crossref 按 ISSN | 仅外链 | metadata-only（P0） |
| Royal Society of Chemistry `rsc` | 化 | Crossref 按 ISSN | 共享 OA；订阅待重勘 | v2-P1 ⚑DRIFT |
| American Mathematical Society `ams` | 数 | Crossref 按 ISSN | 外链/用户侧私有 | v2-P1 |
| SIAM Publications Library `siam` | 数 CS | Crossref 按 ISSN；RSS 仅信号 | 用户侧私有 | v2-P1 |
| EMS Press `ems_press` | 数 | Crossref 按 ISSN | 共享 OA | v2-P1 |
| Mathematical Sciences Publishers `msp` | 数 | Crossref 按 ISSN | 仅外链 | v2-P1 |
| International Press `intl_press` | 数 | Crossref 按 ISSN | 仅外链 | v2-P2 ⚑RECHECK |
| UChicago Press Journals `uchicago_journals` | 经 管 | Crossref 按 ISSN | 用户侧私有 | v2-P1 |
| MIT Press Direct（REStat、TACL、CL） `mit_press_direct` | 经 CS | Crossref 按 ISSN | 外链；TACL 等经 ACL | metadata-only（P1） |
| Emerald Insight `emerald_insight` | 金 管 | Crossref 按 ISSN | 仅外链 | metadata-only（P2） ⚑DRIFT |
| PM Research（JPM 等） `pm_research` | 金 | Crossref 按 ISSN | 仅外链 | v2-P2 ⚑RECHECK |
| Harvard Business Review `hbp_hbr` | 管 | 无开放元数据通道 | 无 | excluded |
| MIT Sloan Management Review `mit_smr` | 管 | Crossref 按前缀 | 仅外链 | metadata-only（P2） ⚑DRIFT |
| ACM Digital Library `acm_dl` | CS | Crossref（DOI 常在会前注册） | 仅外链 | metadata-only（P1） |
| IEEE Xplore（含 CSDL） `ieee_xplore` | CS | Crossref（DOI 滞后 2–6 月） | 用户侧私有 | v2-P1 ⚑COMM |
| IOS Press FAIA（ECAI 等） `iospress_faia` | CS | Crossref 委托 | 共享 OA（限非商用） | v2-P1 ⚑COMM |
| now publishers（Foundations and Trends） `now_publishers` | CS | Crossref 按 ISSN | 仅外链 | metadata-only（P2） ⚑DRIFT ⚑RECHECK |
| CCS Chemistry（中国化学会） `ccs_chemistry` | 化 区 | Crossref 按 ISSN | 共享 OA | v2-P2 |

### L1 预印本与工作论文（30 行）

| 来源 | 学科 | 怎么接 | 全文 | 状态 |
|---|---|---|---|---|
| arXiv `arxiv` | 数 物 地材 生 经 金 CS | OAI-PMH，按类目收割 | CC 者共享，余外链 | v2-P0 |
| ChemRxiv `chemrxiv` | 化 地材 | Crossref 按前缀 | 共享 OA | v2-P0 ⚑DRIFT |
| bioRxiv `biorxiv` | 生 | Crossref 首选，原生 API 补充 | 共享 OA | v2-P0 ⚑DRIFT |
| medRxiv `medrxiv` | 生 心 | Crossref 首选，原生 API 补充 | 共享 OA | v2-P0 ⚑DRIFT |
| PsyArXiv `psyarxiv` | 心 | Crossref + Europe PMC | 共享 OA | v2-P0 ⚑ROBOTS（仅 OSF API） |
| OSF Preprints（其余社区） `osf_preprints` | 心 管 | Crossref 按前缀 | 共享 OA | v2-P1 |
| SocArXiv `socarxiv` | 经 管 | Crossref 按前缀 | 共享 OA | v2-P1 |
| Research Square `research_square` | 全 生 | Crossref + Europe PMC | 共享 OA | v2-P1 |
| Preprints.org `preprints_org` | 全 | Crossref + Europe PMC | 共享 OA | v2-P1 |
| Authorea Preprints `authorea` | 全 | Crossref + Europe PMC | 许可未知，不共享 | v2-P2 |
| ESS Open Archive `ess_open_archive` | 地材 | Crossref 按前缀 | 公开，许可待核 | v2-P2 |
| EarthArXiv `eartharxiv` | 地材 | Crossref + Janeway API | 公开，许可待核 | v2-P2 |
| Optica Open `optica_open` | 物 | Crossref 按前缀 | 公开，许可待核 | v2-P2 |
| TechRxiv `techrxiv` | CS | Crossref 按前缀 | 共享 OA | v2-P1 |
| IACR ePrint Archive `iacr_eprint` | CS | OAI-PMH；RSS 增量 | 仅外链 | metadata-only（P1） ⚑ROBOTS |
| ECCC `eccc` | CS | 待复勘 | OA（未核） | v2-P2 ⚑RECHECK |
| SSRN `ssrn` | 生 经 金 管 | Crossref 按前缀 | 仅外链 | metadata-only（P0） ⚑DRIFT |
| NBER Working Papers `nber_wp` | 经 金 | Crossref + RePEc；RSS 增量 | 用户侧私有 | v2-P0 ⚑LIC（仅周更元数据文件） |
| CEPR Discussion Papers `cepr_dp` | 经 金 | 经 RePEc 批量 | 仅外链 | metadata-only |
| IZA Discussion Papers `iza_dp` | 经 | 经 RePEc | 外链/用户侧私有 | v2-P1 |
| Fed Board FEDS / IFDP `fed_board_wp` | 经 金 | Crossref 按前缀；RSS 增量 | 免费，许可待核 | v2-P1 |
| ECB Working Paper Series `ecb_wp` | 经 金 | 官方 RSS（主通道） | 免费，许可待核 | v2-P1 |
| BIS Working Papers `bis_wp` | 经 金 | 官方 RSS（主通道） | 免费，许可待核 | v2-P1 |
| IMF Working Papers `imf_wp` | 经 金 | Crossref 按前缀 + RePEc | 免费，许可待核 | v2-P1 |
| World Bank Policy Research WP `worldbank_prwp` | 经 金 | 官方 D&R API | 免费，许可待核 | v2-P1 |
| HBS Working Papers `hbs_wp` | 管 | 经 SSRN/RePEc | 仅外链 | metadata-only（P2） |
| MPRA `mpra` | 经 | 经 RePEc | 仅外链 | metadata-only（P2） |
| CESifo Working Papers `cesifo_wp` | 经 | 经 RePEc | 免费（未核） | v2-P2 ⚑RECHECK |
| 其他央行与国际组织 WP（NY Fed、BoE、OECD 等） `other_cb_wp` | 经 金 | 经 RePEc/Crossref | 多为免费，许可待核 | v2-P2 ⚑RECHECK |
| ChinaXiv `chinaxiv` | 全 区 | robots 可读前不接 | OA 预印本 | v2-P2（观察） ⚑RECHECK |

### L1 期刊平台（24 行）

| 来源 | 学科 | 怎么接 | 全文 | 状态 |
|---|---|---|---|---|
| INFORMS PubsOnline `informs_pubsonline` | 管 | Crossref 按 ISSN | 用户侧私有 | v2-P0 |
| AOM Journals（AMJ、AMR 等） `aom_journals` | 管 | Crossref 按 ISSN | 用户侧私有 | v2-P0 |
| AEA Journals（AER、AEJ、JEL、JEP） `aea_journals` | 经 | Crossref 按 ISSN | 用户侧私有 | v2-P0 |
| Econometric Society（ECMA、TE、QE） `econsoc_journals` | 经 | Crossref + OAI-PMH | 共享 OA/用户侧私有 | v2-P0 |
| AAA Publications（TAR 等） `aaa_pubs` | 管 | Crossref 按 ISSN | 用户侧私有 | v2-P1 |
| MIS Quarterly `misq` | 管 | Crossref 按 ISSN | 用户侧私有 | v2-P1 |
| JSTOR（过刊档案） `jstor` | 全 | Crossref 按前缀 | 仅外链 | metadata-only（P2） |
| SciPost `scipost` | 物 | Crossref 按前缀；RSS 仅信号 | 共享 OA | v2-P1 |
| Quantum `quantum_journal` | 物 | Crossref 按 ISSN；RSS 仅信号 | 共享 OA（arXiv 版） | v2-P2 |
| Project Euclid（IMS、Duke Math. J. 等） `project_euclid` | 数 | Crossref 按 ISSN | 共享 OA | v2-P1 |
| Centre Mersenne / Numdam `centre_mersenne_numdam` | 数 | Crossref + OAI-PMH | 共享 OA | v2-P1 |
| Episciences `episciences` | 数 CS | Crossref 或 OAI（待核） | OA（未核） | v2-P2 ⚑RECHECK |
| Annals of Mathematics `annals_math` | 数 | Crossref 按 ISSN | 仅外链 | metadata-only |
| GeoScienceWorld `geoscienceworld` | 地材 | Crossref 按 ISSN（未测） | 用户侧私有 | v2-P2 ⚑RECHECK |
| eLife `elife` | 生 | Crossref；RSS 仅信号 | 共享 OA | v2-P1 ⚑ROBOTS（仅官方 API） |
| PeerJ `peerj` | 生 | Crossref 按 ISSN | 共享 OA（经 PMC） | v2-P2 |
| SfN（J Neurosci、eNeuro） `sfn_journals` | 生 | Crossref 按 ISSN | 共享 OA（限非商用） | v2-P1 ⚑COMM |
| F1000Research 等发表后评审平台 `f1000_platforms` | 生 全 | Europe PMC + Crossref | OA（未核） | v2-P2 |
| JMLR `jmlr` | CS | 官方 RSS + 卷页 | 共享 OA | v2-P0 |
| TMLR `tmlr` | CS | 经 OpenReview + 列表页 | 仅外链 | v2-P0 ⚑ACCT |
| JAIR `jair` | CS | Crossref 按前缀 | 共享 OA | v2-P1 |
| SciEngine（中国科学等） `sciengine` | 全 区 | Crossref 按 ISSN（未测） | 仅外链 | metadata-only（P2） ⚑RECHECK |
| 物理学报 `wulixb` | 物 区 | Crossref 按 ISSN（未测） | 未核 | v2-P2 ⚑RECHECK |
| J-STAGE `jstage` | 全 区 | 官方 WebAPI | OA 为主，各刊不同 | v2-P2 ⚑COMM |

### L1 会议平台（31 行）

| 来源 | 学科 | 怎么接 | 全文 | 状态 |
|---|---|---|---|---|
| OpenReview `openreview` | CS | 官方 API（服务账号待确认） | 仅外链 | v2-P0 ⚑ACCT |
| PMLR `pmlr` | CS | 卷页 + BibTeX | 仅外链 | v2-P0 |
| NeurIPS Proceedings `neurips_proceedings` | CS | 年/卷页 + Crossref | 仅外链 | v2-P0 |
| CVF Open Access（CVPR、ICCV、WACV） `cvf_open_access` | CS | 目录页 + 论文页 | 仅外链 | v2-P0 |
| ECVA（ECCV 开放版） `ecva` | CS | 列表页 + Crossref | 仅外链 | v2-P1 |
| ACL Anthology `acl_anthology` | CS | GitHub XML 与官方包 | 共享 OA（旧卷限非商用） | v2-P0 |
| AAAI OJS（AAAI、AIES、ICWSM 等） `aaai_ojs` | CS | OAI-PMH + Crossref | 仅外链 | v2-P0 |
| IJCAI Proceedings（兼 KR） `ijcai_proceedings` | CS | Crossref 按前缀 + 年页 | 仅外链 | v2-P0 |
| USENIX（Security、OSDI、NSDI、FAST） `usenix` | CS | 官网会话页 | 仅外链 | v2-P1 |
| NDSS Symposium `ndss` | CS | Crossref 按前缀 | 仅外链 | v2-P1 |
| PVLDB（VLDB） `pvldb` | CS | Crossref 按前缀 + 卷页 | 共享 OA（限非商用） | v2-P1 ⚑COMM |
| ISCA Archive（Interspeech 等） `isca_archive` | CS | Crossref 按前缀 + 年页 | 仅外链 | v2-P1 |
| Dagstuhl LIPIcs（DROPS） `lipics_drops` | CS 数 | DataCite + OAI-PMH | 共享 OA | v2-P1 |
| Robotics: Science and Systems `rss_proceedings` | CS | 官网卷页 | 仅外链 | v2-P2 ⚑RECHECK |
| MLSys Proceedings `mlsys_proceedings` | CS | 待复勘（评审在 OpenReview） | OA（未核） | v2-P2 ⚑RECHECK |
| CEUR Workshop Proceedings `ceur_ws` | CS | 官网卷页 | 仅外链 | v2-P2 ⚑RECHECK |
| IFAAMAS AAMAS Proceedings `aamas_ifaamas` | CS | Crossref 按前缀 | 仅外链 | v2-P2 |
| CogSci Proceedings `cogsci_proceedings` | 心 | eScholarship OAI-PMH | 共享 OA | v2-P1 |
| Pacific Symposium on Biocomputing `psb_proceedings` | 生 | 经 PubMed | 未核 | v2-P2 ⚑RECHECK |
| Proceedings of Science（SISSA） `pos_sissa` | 物 | Crossref 按前缀 + INSPIRE | 共享 OA | v2-P2 |
| SPIE Digital Library `spie_dl` | 物 | Crossref 按前缀 | 仅外链 | metadata-only |
| ASSA 年会（含 AFA 等分会场） `assa_meetings` | 经 金 | 程序页 → 会议事件与 JEL | 外链/用户侧私有 | v2-P1 |
| NBER Summer Institute 与各类会议 `nber_conferences` | 经 金 | 会议页 → 会议标签 | 同 NBER WP | v2-P1 |
| WFA 年会 `wfa_meeting` | 金 | 经 SSRN 版本关联 | 仅外链（经 SSRN） | metadata-only |
| SFS Cavalcade `sfs_cavalcade` | 金 | 人工维护会议标签 | 无（robots 禁止） | metadata-only |
| EFA 年会 `efa_meeting` | 金 | 待复勘 | 未核 | v2-P2 ⚑RECHECK |
| AOM Annual Meeting Proceedings `aom_proceedings` | 管 | Crossref 按前缀 | 仅外链 | v2-P2 |
| ICIS / AIS eLibrary `ais_icis` | 管 | Crossref（仅有 DOI 部分） | 仅外链 | v2-P2 |
| SED Meetings `sed_meetings` | 经 | 经 RePEc（待核） | 未核 | v2-P2 ⚑RECHECK |
| icml.cc / neurips.cc / iclr.cc（miniconf） `conf_virtual_sites` | CS | 不接（robots 禁区） | 无 | excluded |
| INFORMS Annual Meeting `informs_annual` | 管 | 不接（只有摘要级程序） | 无 | excluded |

### L2 聚合（44 行）

聚合 42 行，另含聚合兼仓储的 Europe PMC 与盗版源合并行各 1 行。

| 来源 | 学科 | 怎么接 | 全文 | 状态 |
|---|---|---|---|---|
| Crossref `crossref` | 全 | 官方 API + 年度数据文件 | 无 | v2-P0 |
| OpenAlex `openalex` | 全 | 季度快照 + 按量计费 API | 只做 OA 定位 | v2-P0 ⚑BUDGET |
| Semantic Scholar `s2` | 全 | 官方 API + 周更数据集 | OA 链接 | v2-P1 ⚑COMM |
| Unpaywall `unpaywall` | 全 | 按 DOI 查 OA 位置 | 只做 OA 定位 | v2-P1 |
| DOAJ `doaj` | 全 | API + OAI-PMH + 期刊 CSV | OA 链接 | v2-P1 |
| OpenAIRE Graph `openaire` | 全 | 全图快照 + API | 仅外链 | v2-P2 |
| Fatcat / IA Scholar `fatcat_ia_scholar` | 全 | 仅作链接来源 | IA 存档副本链接 | metadata-only |
| Lens.org `lens` | 全 | 用户自带 token，私有富化 | 无 | metadata-only |
| Dimensions `dimensions` | 全 | 不接（条款） | 无 | excluded |
| Scopus `scopus` | 全 | 平台不接；用户可自带 key | 无 | excluded |
| Web of Science `web_of_science` | 全 | 平台不接；用户可自带 key | 无 | excluded |
| BASE `base` | 全 | 不接（未获授权） | 无 | excluded |
| Microsoft Academic（MAG） `microsoft_academic` | 全 | 已关停；仅兼容 `mag` ID | 无 | excluded |
| Google Scholar `google_scholar` | 全 | 不接；只收用户手动导出 | 无 | excluded |
| SciRate `scirate` | 物 CS | 不接（挑战门） | 无 | excluded |
| Paper Copilot / paperlists `paper_copilot` | CS | 不接（数据无许可） | 无 | excluded |
| Hugging Face Papers `hf_papers` | CS | Hub API（每日精选与热度） | 无，只缓存信号 | v2-P0（信号层） ⚑RECHECK（仅商用与长期缓存条款） |
| Papers with Code 存档 `pwc_archive` | CS | HF 数据集一次性导入 | 无 | v2-P1 ⚑SA |
| alphaXiv `alphaxiv` | CS | MCP，用户自连 | 仅外链 | v2-P2 |
| Europe PMC（兼仓储） `europe_pmc` | 生 心 | 官方 REST API | 共享 OA | v2-P0 ⚑ROBOTS（仅 bulk） |
| PubMed / MEDLINE `pubmed` | 生 心 | 年度 baseline + 日更文件 | 无 | v2-P0 ⚑ROBOTS |
| NCBI PubTator3 `pubtator3` | 生 | 官方 REST（按 PMID） | 无 | v2-P1 ⚑RECHECK |
| NIH iCite `icite` | 生 | 官方 REST（按 PMID） | 无 | v2-P1 ⚑RECHECK |
| INSPIRE-HEP `inspire_hep` | 物 | 官方 REST API | 仅外链 | v2-P0 |
| NASA ADS / SciX `nasa_ads_scix` | 物 地材 | 官方 API（每用户 token） | 仅外链 | v2-P1 ⚑DRIFT |
| zbMATH Open `zbmath_open` | 数 | REST + OAI-PMH + 快照 | 仅外链 | v2-P0 ⚑SA ⚑COMM（MSC 码表） |
| PubChem `pubchem` | 化 生 | PUG-REST（化合物→文献） | 不适用 | v2-P2 ⚑ROBOTS |
| EuDML `eudml` | 数 | OAI-PMH | 仅外链 | v2-P2 ⚑RECHECK |
| RePEc（IDEAS/EconPapers） `repec` | 经 金 | ReDIF 批量同步 | 仅外链 | v2-P0 |
| EconBiz `econbiz` | 经 管 | 官方 API（beta） | 仅外链 | v2-P1 |
| dblp `dblp` | CS | DROPS 月度快照 + SPARQL | 仅外链 | v2-P0（快照形态） |
| MathSciNet `mathscinet` | 数 | 只生成外链 | 无 | link-only |
| CAS SciFinder `cas_scifinder` | 化 | 只生成外链 | 无 | link-only |
| EconLit `econlit` | 经 | 不接（无 API 与许可） | 无 | excluded |
| OpenCitations `opencitations` | 全 | REST/SPARQL + CC0 快照 | 无 | v2-P1 |
| Wikidata / WikiCite `wikidata` | 全 | SPARQL + dump | 无 | v2-P2 |
| Jisc Open policy finder `open_policy_finder` | 全 | 官方 API（2026 新版） | 无 | v2-P2 ⚑COMM |
| CiNii Research `cinii_research` | 全 区 | ResourceSync 批量同步 | 仅外链 | v2-P2 ⚑ROBOTS（仅 OpenSearch） |
| SciELO `scielo` | 全 区 | ArticleMeta API | 共享 OA | v2-P2 |
| Redalyc `redalyc` | 全 区 | 经 OpenAlex 等旁路 | OA，仅外链 | metadata-only |
| 中国知网（CNKI） `cnki` | 全 区 | 用户手动导入题录 | 无（订阅库） | user-import-only |
| 万方数据 `wanfang` | 全 区 | 用户手动导入题录 | 无（订阅库） | user-import-only |
| 维普（CQVIP） `cqvip` | 全 区 | 用户手动导入题录 | 无（订阅库） | user-import-only |
| 盗版源合并行（Sci-Hub、LibGen、Anna's Archive；无层级） `pirate_sources` | 全 | 永不接入 | 无 | excluded |

### L2 仓库（11 行）

| 来源 | 学科 | 怎么接 | 全文 | 状态 |
|---|---|---|---|---|
| CORE `core` | 全 | 官方 API v3 | 共享 OA（兜底） | v2-P1 ⚑LIC ⚑COMM |
| Zenodo `zenodo` | 全 | OAI-PMH | 按记录许可 | v2-P2 |
| HAL `hal` | 全 | 官方 API/OAI（确认前旁路） | 共享 OA | v2-P2 ⚑ROBOTS |
| PubMed Central `pmc` | 生 | S3 + OAI-PMH | 共享 OA | v2-P0 ⚑ROBOTS（仅 E-utilities） |
| PsychArchives `psycharchives` | 心 | OAI-PMH | OA，许可待核 | v2-P2 |
| SCOAP3 Repository `scoap3_repo` | 物 | 官方 API | 共享 OA | v2-P1 |
| OSTI.GOV `osti_gov` | 物 化 地材 | 官方 REST API | 链接或接受稿，许可待核 | v2-P2 ⚑RECHECK |
| EconStor `econstor` | 经 管 | OAI-PMH | 共享 OA | v2-P1 |
| FRASER `fraser` | 经 | 官方 API（待核） | 免费 | v2-P2 ⚑RECHECK |
| SSOAR `ssoar` | 管 | 经 CORE/OpenAlex 旁路 | OA，仅外链 | metadata-only ⚑RECHECK |
| 中国科技论文在线 `paper_edu_cn` | 全 区 | 暂不接（全站维护） | OA | v2-P2（暂缓） ⚑RECHECK |

### L2 注册表（3 行）

| 来源 | 学科 | 怎么接 | 全文 | 状态 |
|---|---|---|---|---|
| ORCID `orcid` | 全 | 用户 OAuth + 年度 CC0 文件 | 无 | v2-P1 ⚑ROBOTS ⚑COMM |
| ROR `ror` | 全 | Zenodo 快照（可本地自托管） | 无 | v2-P1 |
| DataCite `datacite` | 全 | 官方 REST + 年度文件 | 无 | v2-P1 |

## 排除清单

排除类 18 行，平台对它们零自动化。

**excluded（13）**

- `pirate_sources` Sci-Hub、LibGen、Anna's Archive 等盗版影子库：项目红线。
- `google_scholar` Google Scholar：无 API，robots 与 ToS 禁止自动查询；只接受用户手动导出后上传。
- `base` BASE：API 须 IP 白名单且主机 robots 全禁，网站声明禁止未授权自动获取，另有工作量证明挑战；未获授权前排除，其覆盖经 CORE、OpenAIRE、OpenAlex 间接获得。
- `dimensions` Dimensions：只对非商业科学计量研究免费，v2 的发现与推荐不属此类。
- `scopus` Scopus：按用例授权，"展示被引数"用例要求应用不能主要是搜索引擎或文摘索引；用户可自带 key 在本人私域富化。
- `web_of_science` Web of Science：订阅加使用政策，平台层不作数据源；用户可自带 key。
- `microsoft_academic` Microsoft Academic：2021 年底已关停，只兼容 `mag` 外部 ID，数据由 OpenAlex 承接。
- `scirate` SciRate：连 robots.txt 都在挑战门之后。
- `paper_copilot` Paper Copilot：GitHub 数据没有许可，只参考其字段设计。
- `conf_virtual_sites` 会议 miniconf 站：数据在 robots 禁区与未文档化接口里（违反 D-014），只作人工核对。
- `informs_annual` INFORMS 年会：只有摘要级程序，没有论文。
- `hbp_hbr` Harvard Business Review：Crossref 查无该刊，没有可枚举的 DOI；用户可手动导入。
- `econlit` EconLit：订阅书目，无公开 API，无数据许可；JEL 改经 RePEc、NBER、ASSA 获取。

**link-only（2）**

- `mathscinet` MathSciNet：robots 基本全禁，属订阅库；按 MR 号外链。
- `cas_scifinder` CAS SciFinder：学术版条款禁止脚本批量抽取、自动化与 AI 用途；由用户在订阅内手动打开。

**user-import-only（3）**：用户在机构授权下导出 RIS 或 EndNote 题录后导入本人文献库，平台不做代理、不绕 IP 授权。

- `cnki` 中国知网：`kns.cnki.net` 的 robots 全禁，无开放 API。
- `wanfang` 万方数据：检索子域有 WAF 拦截，无开放 API。
- `cqvip` 维普：robots 部分禁止，无开放 API。

另外两点：

- metadata-only 的 26 行只收元数据、全文零自动化，原因分五类：条款明文禁止自动化 4 行（如 SSRN，见 D-051）、robots 禁止或不可读 8 行、订阅墙且无开放全文通道 8 行、会议程序在登录墙后或 robots 禁论文路径 2 行、只作链接来源或旁路 4 行。
- 与具体来源无关的红线：盗版与影子库；求解或绕过 CAPTCHA 与挑战门；Google Scholar 自动化；用多 key、多账号、多 IP、住宅代理或伪装 UA 规避限额；平台出口代用户访问出版商或持有出版商会话；软门与未文档化接口；访问 robots 禁区路径；把 IEEE、Elsevier、SN Meta API 的内容放进共享索引、嵌入或共享 LLM。

## 已知缺口

- **地学与材料最薄**：地学专属来源只有 3 行且都是 P2，材料没有专属来源；AGU、EGU/Copernicus、GSA 与材料来源未调研，GeoScienceWorld 的 Crossref 未测。
- **中文与区域没有 P0/P1**：知网、万方、维普只能用户导入，ChinaXiv 与中国科技论文在线处于维护中；须补一轮中文生态调研，先量化 Crossref、OpenAlex 对中文刊的覆盖。
- **范围外与未勘察**：社会学、政治学、教育学不在 v2.0 范围；Project MUSE、SMF、UW Press 平台未勘察，本轮不增行，其上的 venue 暂时只能经 Crossref。心理学会议、ISMB/RECOMB、部分经管会议与 CS 长尾（MLSys、RSS、ECCC）也未核实，待补充调研或实现前勘察。
- **书面确认未到**：NCBI、EMBL-EBI（含 Europe PMC 用量）、OpenReview 服务账号为 P0，V0 即发函；ORCID、OSF、eLife、HAL、PubChem、CiNii、IACR 等为 P1。确认前：`pubmed` 首批降级，D-049 接受前 E-utilities 连按需调用也不做，生命科学主干由 Europe PMC、PMC 与 Crossref 承担；与 EBI 约定用量前，Europe PMC 只作后台收割；OpenReview 平台侧共享收割停用，ICLR、TMLR、COLM 等由 arXiv 版本、DROPS dblp 快照与 forum 外链兜底。
- **数据许可未取得**：CORE、NBER 周更元数据文件、APS Harvest 全量、S2 商用边界、SN 与 ADS 的平台级用途、HF Papers 与 alphaXiv、央行 WP、venue 名录体系、SSRN 的 CC 许可论文；取得前不启用或只外链。
- **配额与费用不明**：Crossref 分池容量、Metadata Plus 价格、OpenAlex 预算与 S2 key 待定，须按首个规模档 T1（≤1,000 活跃用户）的负载做配额仿真并正式询价。
- **许可元数据不全**：OpenAlex 许可常为空，Crossref 同一篇可有多条 license，部分来源没有 license 元数据。许可闸按多源投票、取最严、未知即拒，其精度列为 P0 验收项。
- **证据偏弱**：一批条款只有二手证据，须人工读原文或发函确认；出口 IP 会影响 WAF 与挑战结论，须在校园网和用户本地网络复测。

## 名录怎么维护

- **注册表是单一事实来源**：实现期每源一个 `registry/sources/<source_id>.yaml`，本表、统计与排除视图都由生成器产出，统计数字不许手改；首版以本表 187 行导入。运行时状态（健康度、配额余量）不写回名录。V0 验收注册表完整、枚举合法、生成一致、合规不变式与变更留痕（AC-V0.x）；V1 验收闸门执行、证据时效、漂移响应、venue 可路由、首批可用与学科覆盖（AC-V1.x）；季度复核为 AC-V3.26。
- **新增与退役**：新增来源先写调研短文，再提交注册表条目，初始状态为 `v2-P2` 或 `metadata-only`；生成器重建后由主 agent 复核证据再合并。退役改为 `excluded`，写明理由与替代来源，不删行。
- **状态与闸门变更附证据**：每次变更留证据链接与审批记录。`metadata-only` 升为 `v2-Px` 须有一手条款或书面确认；解除 ⚑ROBOTS 或 ⚑ACCT 须书面确认，⚑ROBOTS 另须按 D-049 登记；这些由主 agent 审批。改为 `excluded`、解除 ⚑LIC、⚑RECHECK、⚑DRIFT 由维护者审批；降级可由探针自动执行，维护者事后补证据确认。
- **证据时效**：每条通道带 `evidence{url, verified_at}`。超过 90 天未复核进入 `review_overdue`：探针持续为绿、证据其余字段完整时宽限 30 天，维持原模式；宽限结束或任一探针告警，即降为 `on_demand`（只做按需调用）并标 `needs_confirmation`（待确认）。快变事实（arXiv、bioRxiv、PMC、OpenAlex 计费、Crossref 分池、SSRN 平台等）按季度复核，venue 名录与出版商条款按年复读。
- **漂移处置**：漂移探针周期比对 robots 与 ToS 哈希、TDM 信号、挑战率、配额头、DOI 前缀与 member，并识别"200 空体"。告警后，robots 与 TDM 信号漂移立即把该通道降为仅元数据或暂停；ToS 哈希变化宽限 7 天，但依赖书面确认运行的通道 24 小时内失效，回退到确认前的模式；元数据通道自身受影响时暂停，并切换替补链。

---

完整草稿（含逐行证据、限速与条款、v1 状态、ConnectorFamily 与执行位置明细、代表性 venue 索引、统计明细、注册表示例与伪代码、全部验收条目、异议与评审记录）：`git show v2-drafts:docs/catalog/source-directory.md`
