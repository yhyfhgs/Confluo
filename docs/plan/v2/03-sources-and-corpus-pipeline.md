---
title: 来源接入与语料流水线
status: draft
owner: opus5.5-primary
updated: 2026-09-27
---

# 03 · 来源接入与语料流水线

> 本文回答：从哪些来源、在什么合规条件下收进论文，收进后怎样去重、补齐并推给用户。结论：来源用机读注册表声明，多数期刊经 Crossref 委托零代码接入；平台侧请求先经策略引擎取最严，再由出站网关发出；受限全文只在用户侧单篇取回，共享层只放公开元数据和许可允许再分发的内容。

## 要点

- **Source 与 Venue 分离**：多数期刊只需登记，由 Crossref 委托承接元数据与最新论文。
- **SourceSpec v2** 为每个来源声明 metadata、latest、fulltext 三条通道，各带合规结论与证据（90 天复核）。
- **只为有官方 API 或协议通道的来源写代码**：连接器分九族，只声明请求，由出站网关执行。
- **策略引擎**对各类合规信号取最严，得出五档模式；**漂移探针**发现变化即降级，只降不升。
- **身份三层** Work / Version / Manifestation：弱信号只进候审，工作论文（WP）与发表版只建关系。
- **流水线六段**各自幂等；全文取回移出后台，受限全文只在用户侧单篇、显式取回。
- **接入成本**：已支持平台上的期刊或仓储实例 ≤30 分钟，新 connector ≤2 人日。

## 来源模型：Source 与 Venue 分离

配图：[来源模型](../../diagrams/v2-03-source-model.svg)（Source、通道、Venue、连接器与策略引擎的关系）、[来源汇流](../../diagrams/v2-11-source-confluence.svg)（一级、二级来源经策略引擎汇入统一语料）。支持名录：[source-directory](../../catalog/source-directory.md)。

- **Source**：可对接的来源，按七类分层（定义、判定规则与现状见[来源分层](../../catalog/source-taxonomy.md)，D-072 草案）。每个来源一个主类，可带兼角色，如 Crossref 为 M2、兼 L2b 元数据 API。
  - 元层：M1 出版与托管主体（出版商、学会、公开托管平台、国家与公共机构），M2 标识与注册（DOI 注册机构、ORCID、ROR、ISSN 等）；
  - 一级：L1a 期刊与会议，L1b 预印本与工作论文，L1c 长尾一级产出（技术报告、学位论文、JMP）；
  - 二级：L2a 文献库与学科仓储，L2b 检索引擎与聚合项目。
- **Venue**：期刊、会议或 WP 系列，即 L1a 与 L1b 中的系列，仍独立于 Source 建模。理由：一个平台承载多刊，一本刊也会换平台；分开后多数期刊只需登记。只有自有站点与通道的 venue 才另写 SourceSpec，其余由所在 M1 平台或 Crossref 委托承接。按学科的 venue 详表与评级标签见 [venue 名录](../../catalog/venues/README.md)。
- **多键归一**：ISSN 集合（含历代）、ISSN-L、OpenAlex source、DBLP key、OpenReview 前缀、Crossref member 与 owner prefix（带时间段）、container-title。不以单个 ISSN 作主键，永不单凭 DOI 字符串前缀路由。
- **演化边**：`renamed_to`（更名或换 ISSN）、`journalized_as`（会议论文集期刊化）、`co_hosted_on`（同一届多平台发布）。
- **学科差异**：CS 会议按"届 × track"建届次；经管 WP 系列是一等 venue，会议报告以 `presented_at` 事件挂到论文上，不产生新版本。
- **策展等级**：`curated`（人工 YAML）；`auto`（由 Crossref 或 OpenAlex 记录自动建立，用户关注任意期刊都不必写 YAML）；`user_proposed`（经已登记来源核验后转为 `auto`）。

## SourceSpec v2：三条通道与合规证据

SourceSpec v2 是每个来源的机读声明（YAML），由 v1 VenueSpec 演进而来。注册表 `registry/`（实现期落地）是单一事实来源，名录由它生成，变更走 git PR。见 D-046。

- **三条来源通道**（SourceChannel）：`metadata`（元数据）、`latest`（最新论文增量）、`fulltext`（全文）；缺哪条就写 `method: none`。
- **每条通道声明**：取得方式与连接器、认证、执行位置 `exec_side`、限速、逐主机 robots 结论（含具名 AI 爬虫规则）、ToS 自动化条款、TDMRep 与 Content-Signal（站点对文本挖掘、AI 用途的机读保留声明）、许可策略、默认展示范围、替补链、运行状态。
- **合规证据**：每个合规字段至少一条 `evidence{url, verified_at}`；本源接触的每个主机（含 bulk 主机）都要有 robots 结论。
- **证据时效**：超过 90 天未复核进入 `review_overdue`，若探针持续为绿、证据其余字段完整，宽限 30 天、维持原模式（V0 复核）；宽限结束或任一探针告警，降为 `on_demand` 并标 `needs_confirmation`。可机器复测的证据复测一致即自动续期，首批复核期错开。
- **凭证**：注册表只引用部署级密钥，用户级凭证永不入表；用户级认证的通道必须 `exec_side: user`。
- **商用门控**：`platform.commercial=true` 时，限非商业的来源与内容（如 ORCID 公共 API、CC BY-NC 内容、出版商 TDM 流程）自动停用；需许可的来源（如 CORE）取得许可前不启用。见 D-045。
- **名录状态**分 `v1_status` 与 `v2_status`（`v2-P0`/`P1`/`P2`、`metadata-only`、`link-only`、`user-import-only`、`excluded`）。`v2_status` 是产品承诺，只能经 PR 写明依据来改；通道运行状态由策略引擎和探针改写。
- **把关**：13 条 lint 规则，例如 P0 来源的 metadata 与 latest 须有可用替补，盗版源与 Google Scholar 只能是 `excluded`。v1 的 62 个 VenueSpec 由确定性转换器迁入。

## SCD：来源能力描述

SCD（Source Capability Descriptor）按端点说明"能怎样查、代价多少"；来源通道则回答"从哪里取、能不能取"。

- **内容**：可下推的谓词及支持等级（原生、近似、连接器模拟、不支持）、排序键、增量游标、分页上限、成本模型（如 Crossref 按请求类分池、OpenAlex 按美元计价）、礼貌参数。
- **来源**：静态部分由 SourceSpec 与连接器生成，动态部分（成功率、延迟、实测限额、滞后）来自运行统计。
- **给谁用**：[04 检索与路由](04-retrieval-and-routing.md)的路由器选源、按来源能力放宽查询时，只经 SCD 读取能力；收割规划用它选请求类与分页。
- Crossref 在 SCD 中不声明关键词检索能力，`query.bibliographic` 只用于引文串匹配。

## 连接器九族与执行位置

- **连接器只声明请求、解析响应**，不自己发 HTTP。平台侧请求一律经出站网关（Egress Gateway，平台唯一对外出口）执行：robots 先行闸（缓存 ≤24 小时）、五元组令牌桶 `(source, host, 上游请求类, 凭证, 出口 IP)`、挑战检测（命中即该主机冷却 24 小时，不求解）、诚实 UA、逐请求审计。网关内部客户端库称 PoliteHttp。见 D-055。
- **执行位置 `exec_side`**：
  - `platform`：平台 worker 以部署身份执行；
  - `user`：用户的浏览器扩展或本机 pc-agent 用本人会话或 key 执行，产物一律归用户私域，许可是 CC BY 也不进共享层。
- **九族**：
  - `aggregator_api`：聚合器与学科库的文档化 API（OpenAlex、Europe PMC、INSPIRE 等）；多为 platform，NASA ADS 为 user。
  - `oai_pmh`：任何 OAI-PMH 端点（arXiv、PMC、EconStor 等）；platform；族核心写一次，实例零代码。
  - `feed`：RSS、Atom、eTOC；platform；多数只作新鲜度信号，按源登记的官方 feed（ECB、BIS、JMLR 等）可作元数据主通道。
  - `crossref_delegated`：在 Crossref（或 DataCite）登记 DOI 的期刊、WP、预印本前缀、论文集；platform；venue 零代码。
  - `bulk_snapshot`：官方快照与年度文件（OpenAlex 季度快照、Crossref 年度文件、DROPS dblp 快照等）；platform。
  - `platform_family`：托管平台（Atypon、Silverchair、HighWire）为 user；仓储软件（DSpace、EPrints、InvenioRDM）与 OJS 为 platform；实例零代码。
  - `official_tdm_api`：用户本人 key 的出版商全文或 TDM API（Elsevier、Wiley、Springer Nature 等）；user。
  - `site_special`：有官方 API 或结构化页面的专站，含 robots 允许、结构稳定、无挑战门的 OA 论文集静态页（PMLR、CVF 等）；platform。
  - `v1_bridge`：包装复用 v1 的 20 个生产 adapter（部分移植、转用户侧或废止在线路径）；platform 或用户侧 pc-agent。

## 策略引擎与漂移探针

- **五档模式**（策略引擎逐通道、逐操作判定；全库唯一枚举，从严到松）：`deny`（不接触）< `link_only`（只给外链）< `user_side`（只在用户本人客户端上、显式操作时执行）< `on_demand`（平台在用户查询或补查时低频调用）< `background`（平台定时收割）。
- **取最严**：五类信号各给一个上限——文档化 API、bulk 通道、逐主机 robots、ToS 自动化条款、TDM 与 AI 保留；另有结构性上限——执行位置、商用与许可门控、证据时效、漂移状态、挑战冷却、红线。结果取全部上限的最小值。
- **文档化 API 与 robots 冲突**：登记进 robots ADR（D-049）例外附表后，才允许低频、用户触发的按需单篇调用；后台批量须先取得书面确认。
- **书面确认**记为有期限（≤12 个月）的 PolicyOverride，只能放宽文档化 API、bulk、robots 三类冲突，越不过 ToS 禁令、TDM/AI 保留、挑战冷却与结构性上限。红线（盗版源、CAPTCHA 求解、Google Scholar 自动化）不可覆盖。
- **漂移探针**周期比对：robots 与 ToS 哈希、TDMRep、挑战率、配额头、DOI 前缀与 member 归属、"200 空体"与计数骤降、弃用公告。
- **分档处置**：
  - robots 与 TDM 信号漂移立即降级；
  - ToS 哈希变化给 7 天宽限，但依赖书面确认运行的通道 24 小时内失效，回到确认前的模式；
  - 元数据通道自身受影响时暂停并切换替补链；
  - 只降不升，恢复须人工。
- **替补**：关键能力（DOI 元数据查找、最新论文收割、OA 定位、标题精确匹配）至少两级同能力通道。

## 各学科接入计划

状态与优先级以[支持名录](../../catalog/source-directory.md)为准。187 行种子中 `v2-P0` 36 个，是 V1 首批接入范围；其余为 `v2-P1` 63、`v2-P2` 44、`metadata-only` 26、`link-only` 2、`user-import-only` 3、`excluded` 13。跨学科出版商 `elsevier_sd`、`wiley`、`springer_link`、`nature_portfolio`、`oup_academic` 均属 P0：元数据经 Crossref，订阅全文只在用户侧执行或外链。括号内为各学科其余 P0。

- **数学**（`arxiv`、`zbmath_open`）：Crossref、arXiv 数学类目、新写的 zbMATH Open。MSC2020 为 CC BY-NC-SA，只作默认不加载的插件。
- **物理/天文**（`arxiv`、`inspire_hep`、`aps`）：arXiv 物理类目（set 须带 `physics:` 前缀）、Crossref，新写 INSPIRE 与 APS Harvest（OA 集）。IOP 机器访问须另签协议，只取元数据。
- **化学/材料**（`chemrxiv`）：期刊与 ChemRxiv 都经 Crossref，不写新代码。地学与材料首批只经 Crossref，待补充调研。
- **生命科学/医学**（`europe_pmc`、`pmc`、`pubmed`、`biorxiv`、`medrxiv`、`pnas`、`arxiv`）：Europe PMC、PMC、Crossref 为主干；bioRxiv、medRxiv 以 Crossref 为首选。PubMed 在 D-049 接受前连按需调用也不做，接受后按附表允许单篇补查；后台收割与 baseline 导入待 NCBI 书面确认。与 EBI 约定用量前，Europe PMC 只作后台收割，交互联邦靠本地语料与 OpenAlex。
- **心理**（`psyarxiv`、`medrxiv`、`europe_pmc`、`pubmed`）：Crossref、PsyArXiv（经 Crossref）、Europe PMC；APA 摘要为 0，走补齐链；不写新代码。
- **经济/金融**（`nber_wp`、`repec`、`aea_journals`、`econsoc_journals`、`arxiv`）：Crossref、SSRN（只取元数据加外链，见 D-051）、NBER、RePEc bulk；央行与国际组织 WP 走官方 feed 或 API（新写央行 RSS 解析器等）。
- **商业/管理**（`informs_pubsonline`、`aom_journals`）：Crossref 零代码。UTD24 的 24 刊中 21 刊在 Atypon 或 Silverchair；Atypon 实例多有具名 AI 爬虫禁令，订阅全文只能"在出版社打开 + 一键保存"。
- **CS/AI**（`arxiv`、`openreview`、`tmlr`、`pmlr`、`cvf_open_access`、`neurips_proceedings`、`acl_anthology`、`aaai_ojs`、`ijcai_proceedings`、`jmlr`、`dblp`、`hf_papers`）：arXiv、会议平台、DROPS dblp 快照（在线 dblp 废止，见 D-050）、HF Papers 信号。OpenReview 平台侧共享收割在书面确认前停用，ICLR、TMLR、COLM 由 arXiv 版本、dblp 快照和 forum 外链兜底（见 D-052）。IEEE、ACM 只取元数据。
- **聚合与注册表**（`crossref`、`openalex`）：OpenAlex 受美元预算约束；Semantic Scholar（S2）、OpenCitations、DOAJ、DataCite、ROR、ORCID 为 P1；CORE 须先取得许可。
- **中文与区域**：没有 P0 或 P1；知网、万方、维普只接受用户导入题录，结果只进私域。
- **范围**：社科只覆盖经济、金融、商业、管理；社会学、政治学、教育学不在 v2.0。

## 摘要补齐链

每条摘要单独存为变体，记来源 `abstract_source` 与权利 `abstract_rights`；缺摘要时降级展示，推荐冷启动不依赖摘要。

- **四类权利**：
  - `open`（A 类：arXiv 元数据、CC 许可文章等）：卡片可完整展示，可作共享 TL;DR 与翻译的输入。
  - `publisher_copyright`（B 类：Crossref 存缴摘要、OpenAlex 倒排还原等）：卡片只展示片段加原文链接，不作共享派生输入。默认进入内部词法索引与嵌入（不展示），设总开关，关闭后按输入构成重建。来源登记了 TDM 保留（机器可读或条款中的自然语言保留）时，其摘要不进词法索引、嵌入、cross-encoder、TL;DR 等任何共享派生处理。
  - `personal_license`（C 类：用户侧经 Springer Nature、Elsevier API 取得）：只存本人私域。
  - `unknown`：完成分类前不展示、不使用。
- 单篇为 CC 许可时，摘要按 `open` 处理，不论经哪个渠道取得。
- **补齐顺序**：同版本 A 类 → 同 Work 其他版本的 A 类（如 arXiv 预印本，注明来自哪个版本）→ 学科开放源（INSPIRE、zbMATH）→ 注册机构的 B 类（Crossref、Europe PMC/PubMed）→ 聚合还原的 B 类（OpenAlex、S2）→ 用户侧 C 类 → 只显示标题、venue、作者与分类。
- **按出版方路由**：Elsevier、APA、IEEE、AOM 等在 Crossref 中零摘要，各有替补链；每周按"学科 × 出版方"报告覆盖。

## 身份模型：Work / Version / Manifestation

- **Manifestation**：具体载体，一条源记录或一个文件、页面。
- **Version**：可独立引用的文本版本，如 arXiv v2、作者接受稿、期刊正式版（VoR）、WP 的一个编号。
- **Work**：同一研究成果全部版本的集合，id 即 `cluster_id`。
- **合并规则**（见 D-048，修订 D-007 的表示）：
  - 标识符带粒度。两条记录共享任一版本级标识符（DOI、arXiv vN、PMID 等）即同一 Version。
  - Work 只沿被接受的版本边合并。同一版本系的修订自动接受；预印本与正式版之间须有 ≥1 条第一方证据（如 Crossref `is-preprint-of`、arXiv 记录中的 DOI）或 ≥2 条来自不同来源的第三方证据，且通过同作品健全检查。OpenAlex W、S2 corpusId 只作投票证据。
  - WP 与发表版只建 `preprint_of` 关系，不并入同一 Work。
  - 弱信号（标题 MinHash-LSH 近似、Splink 概率打分）只产生候审对，得分多高都不自动合并。
- 结果与到达顺序无关；合并与拆分都写日志，可撤销回滚。
- 卡片默认展示最佳版本：VoR > 作者接受稿 > 最新预印本。

## 语料流水线与 enrich

六段各自幂等，只经持久化实体通信，输入的到达顺序不影响结果。见 D-047。

- **harvest**：执行 WatchKey（由用户频道编译、多用户共享的收割键，算法见 04）增量、venue 回填与快照导入；游标与本批数据同一事务提交，每次重叠回取，再按 `(source_id, source_key)` 去重，不漏不重。
- **normalize**：规范标识符与许可码，日期按语义分开存，解析 venue 与版本关系声明。
- **identify**：按上节规则归并身份。
- **enrich**：补齐与标注，要点见下。
- **index**：BM25、向量与图（结构见 04），可从语料全量重建。
- **percolate**：把新 Work，以及新增 Version 或匹配字段变化的已有 Work，交给 Percolator 写入用户的新论文收件箱 FeedInbox，保证"预印本先到、正式版后到"时关注该期刊的用户仍能收到。

**最新论文增量**：Crossref 以 `from-created-date` 加 3 天重叠为主，`from-index-date`（结果约放大 100 倍）只作每周补漏；arXiv 走 OAI 类目级 set；Europe PMC 按 `FIRST_IDATE` 日窗。

**本地底座**：OpenAlex 季度快照、Crossref 年度文件、DROPS dblp 快照，按全体用户的"兴趣并集"只导入子集；计量 API 只做增量与补查。起步语料约 100–300 万 work，日新增 1–3 万。

- 语料只记并集版本，不记是谁的兴趣触发了导入；联邦查询结果入库时也不记用户与查询文本。
- 由私有文献库、频道或关注派生的细粒度键（作者、引文邻域），须 ≥`k_cf` 个不同用户共有才并入平台收割，否则只做该用户的按需查询。

**enrich 要点**：

- 主题：取 OpenAlex topic，约 12% 无 topic 的用 topic 质心补标。
- 嵌入：按模型版本化并记录输入构成，便于法务结论变化时定点重建；模型在 V1 分学科评测后定。
- 可共享 TL;DR 与翻译：只用可共享且无 TDM/AI 保留的输入；过规则、NLI、抽样裁判三道闸，不过闸降级为原文首句；永不替代作者摘要。
- OA 与许可：多源投票，取最严，未知即拒绝。"需订阅（用你的凭证）"只在用户侧计算。
- 共享 OA 全文：只收单篇许可在白名单内的（CC BY、BY-SA、CC0、公有领域；NC 只在非商业部署）；`features.oa_shared_cache` 默认关闭，直到许可闸精度验证通过。非 CC 许可的 arXiv 条目只外链。

**新鲜度设计目标**（按实测校准）：arXiv OAI 可取后 ≤2 小时进 FeedInbox；Crossref 委托期刊的新 DOI 创建后 ≤24 小时入库。需求上限是公告后 ≤6 小时（见 01），验收线在 09 中待定。

## 用户侧全文取回

- **执行位置**：平台出口不访问出版商的受限全文主机；受限全文只由用户浏览器的配套扩展（Companion Extension）或本机 pc-agent，用本人会话、key 与网络出口取回（见 D-053）。理由：机构订阅条款（如 SERU）不把平台算作授权用户。personal 部署须声明 `deployment.host_is_user_device=true` 才能在本机执行用户侧通道。
- **单篇、显式触发**：任何部署都不批量、不预取。唯一例外：本机 personal 部署可批量取回许可允许的 OA 全文到本人私有空间（云主机上改由共享层承接）。
- **平台只下发不含凭证的取回意图**（字段与签名见 [08 合规、安全与隐私](08-compliance-security-privacy.md)），附声明式配方 FulltextRecipe：配方是数据而非代码，执行器只解释受限步骤，不执行下发脚本、不代填登录、不点验证码，携密头只发往白名单主机。
- **候选排序**：共享 OA 全文 → OA 位置外链 → 用户本人 key 的官方 TDM API → 用户机构会话加平台族配方 → 机构链接解析器 → 在出版社打开。
- **robots 与 AI 爬虫禁令**：用户显式点击触发的单篇取回属于本人的浏览行为，不按爬虫处理。但具名 AI 爬虫禁令站点（Atypon 族与 Springer 站点多属此类）在法务结论出来前只提供"在出版社打开 + 一键保存"，不由扩展代发请求。
- **护栏**：同一平台不并发，每域间隔 ≥6 秒，每平台每日 ≤200 次尝试（成败都计），遇挑战立即停止并冷却 24 小时。
- **私有存放**：platform 部署默认只存设备本地；用户开启同步时，服务端只存端到端密文（见 D-054）。不做跨用户去重。私有派生（私有 TL;DR、嵌入）永不进共享层，并按来源门控，如 IEEE 禁止。

## 新增来源 SOP 与成本目标

- **A 零代码 venue**（已登记来源下的新期刊、WP 系列、预印本前缀）：工具预填键，人工核对后跑 lint、dry-run、canary，≤30 分钟。
- **B 零代码实例**（已支持仓储软件的新 OAI 端点）：≤30 分钟。
- **C 新来源、已有族**：另做来源级合规复核，设计目标 ≤0.5 人日。
- **D 新 connector**（有官方 API 或协议、现有族接不住）：≤2 人日，含证据、fixture、映射、契约测试、探针与 canary。
- 没有官方通道、又被 robots 或 WAF 禁止的站点不写抓取型连接器，登记为 `link-only`、`metadata-only` 或 `user-import-only`。
- 合规、技术、上线三道评审门，合规字段须第二人复核。
- 用户提交的新来源登记进部署方审核队列；通过前不向新来源的任何主机发请求，连 robots.txt 也不取。

## 怎么验收

- **V0**：注册表 schema 与 13 条 lint 阻断合并；62 个 VenueSpec 迁移零未映射字段；策略引擎单调、覆盖有界、可复现三条性质的属性测试与黄金决策表全过（AC-V0.x）。
- **V1**：robots 先行与全局礼貌零违例；漂移注入按期望降级、不自动回升；7 日增量回放零漏零重；身份与输入顺序无关、合并可撤销；许可闸误放行为 0；平台出口访问用户侧全文主机为 0（AC-V1.x）。
- **V2**：14 天在线观测新鲜度；用户数放大 10 倍时上游请求增幅 ≤10%；"预印本先到、正式版后到"正确推送（AC-V2.x）。
- **V3**：取回意图、配方与回执中没有凭证与内容；配方解释器对抗测试全拒；用户侧护栏成立；题录导入只进私域；兴趣并集遵守 `k_cf`（AC-V3.x）。

## 未决事项

- 默认假设：非商业部署；不购买 Crossref Metadata Plus 与 OpenAlex 付费档；robots 与文档化 API 冲突时从严，书面确认前不做后台批量。
- robots ADR（D-049）与逐站书面确认：NCBI、EBI（含 Europe PMC 用量）、OpenReview 服务账号 V0 即发函；ORCID、OSF、eLife、HAL、arXiv export、IACR 等随后。
- 法务待定：B 类摘要能否进内部索引、可展示的摘录长度、能否作共享派生输入；扩展代发的单篇请求算不算自动化访问。设计已按最严处理，可逆。
- 数据许可待取得：CORE、NBER 周更元数据、APS Harvest 全量、S2 商用边界等，取得前不启用或只外链。

---

完整草稿（含 YAML 与伪代码示例、逐源限额与证据、v1 迁移对照、测试方法与全部验收条目、异议与评审记录）：`git show v2-drafts:docs/plan/v2/03-sources-and-corpus-pipeline.md`
