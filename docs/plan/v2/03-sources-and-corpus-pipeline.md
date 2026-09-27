---
title: 来源接入与语料流水线（SourceSpec v2 / Connector / 策略引擎）
status: draft
owner: opus5.5-design
updated: 2026-09-27
---

# 03 · 来源接入与语料流水线（SourceSpec v2 / Connector / 策略引擎）

> **定位**：v2 设计阶段子文档 03。主承接用户需求 R1（自定义来源与支持名录），并为 R2（查询、最新、多来源）、R3（推荐所需的语料与表示）、R4（卡片内容）提供语料侧基础。上游约束是 [v2 设计决策简报][BRIEF]（下称"简报"），证据层是 [调研综合][SYN] 与 14 篇调研（代号见 [SYN] §1.1）。
>
> **本文定义**（简报 §9 接口归属）：SourceSpec v2 schema、SCD、ConnectorFamily 接口、策略引擎与漂移探针、语料流水线（harvest → normalize → identify → enrich → index → percolate）、enrich、摘要补齐链、身份模型语义、用户侧全文取回的候选生成与 FulltextRecipe、新增来源 SOP。
>
> **本文引用、不定义**：
> - [04][04]：Query AST、路由器、TSRG、WatchKey、`route_stat`、调度与稳定性算法；
> - [05][05]：物理 DDL、RLS、凭证库、存储分层；
> - [06][06]：事件契约、ValueModel、Percolator 的推荐侧匹配；
> - [07][07]：卡片字段、学科模板、AI 标识样式；
> - [08][08]：全库 HC 编号，展示级别 DL0–DL4（CP 的 V0–V4，简报 R2-03）、M1–M25 与 `display_scope` 的映射，许可矩阵落地；
> - [02][02]：组件边界与 API 面，含 Companion Extension（U2）与 pc-agent（U3）；09（路线图）：里程碑、AC 终编号、ADR 草案。
>
> 支持名录本体见 [catalog/source-directory][DIR]，本文不复制整表。
>
> **引用写法**：`[AG §2.2.1][AG]` 表示 aggregators-repositories 调研 §2.2.1；`HC-xx` 沿用合规调研（CP）的编号，[08][08] 统一登记时保留了 HC-01…HC-28 的原号，并从 HC-29 起新增；`SI-xx`、`T-xx`、`G-xx` 是 [SYN] 的局部编号。调研中标 ⚠ 的事实在此继续标 ⚠；除另注外，事实时点均为 2026-09-26（调研核验日）。
>
> **伪代码**：代码块注明"设计伪代码"的不可运行、不冻结接口；注明"设计伪代码 DDL"的只是语义契约，物理 DDL 以 [05][05] 为准。

**五要素索引**：功能说明 §1 · 实现方案 §2–§14 · 测试方法 §15 · 测试类型 §16 · 验收标准 §17（AC 草案）。另有术语 §18 · 异议与备选 §19 · 待决问题 §20 · 参考 §21 · 评审记录（文末）。配图：[v2-03-source-model.svg][DIAG]（Source / SourceChannel / Venue / Connector / Policy 的关系）。

---

## 0. 结论速览

1. **来源模型**：来源分两层——L1 为 `publisher`、`preprint`、`journal_platform`、`conference_platform`；L2 为 `repository`、`aggregator`、`registry`（注册表子类型：ORCID、ROR、DataCite 等，简报 R2-11）。Source 与 Venue 分离。
   - Venue 用多键归一：ISSN 集合、ISSN-L、OpenAlex source、DBLP key、OpenReview 前缀、Crossref member 与 owner prefix 的历史、container-title。
   - Venue 之间有演化边：`renamed_to`、`journalized_as`、`co_hosted_on`，另有托管平台随时间变化的 HostingPeriod。
   - 学科差异分别建模：理科用 `proceedings_series`；CS 用 `conference` 加 `VenueEdition`；经管用 `wp_series`，会议作为 `meeting`，论文以 `presented_at` 事件挂接（SI-01/03/20）。
2. **SourceSpec v2**：机读注册表 `registry/sources/*.yaml` 是单一事实来源。
   - 每个 Source 声明三条 SourceChannel（metadata、latest、fulltext）。
   - 每条通道带 method、endpoint、auth、exec_side、rate、逐主机 robots、ToS、tdmrep、Content-Signal、license_policy、`display_scope` 默认值、`evidence{url, verified_at}` 和运行状态。
   - 证据超过 90 天未复核的进入 `review_overdue`：仅当漂移探针持续为绿、证据其余字段完整时宽限 30 天并维持原模式，宽限结束或任一探针告警即降为 `on_demand` 并标 `needs_confirmation`（SI-11，[SYN §3.5][SYN]；简报 R2-16）。
   - v1 的 62 个 VenueSpec 经确定性转换器迁入（§3.7）。
3. **SCD 按端点声明**，内容包括：
   - 可下推谓词（native、emulated 或 none，并注明保真度）、排序键、增量游标、分页上限；
   - 成本模型，包括 Crossref 的请求类分池、OpenAlex 的美元单价；
   - 礼貌参数。

   静态部分由 SourceSpec 派生，动态部分来自运行统计。SCD 是 04 路由器与健全放宽的唯一输入（SI-22）。
4. **九个 ConnectorFamily**：`aggregator_api`、`oai_pmh`、`feed`、`crossref_delegated`、`bulk_snapshot`（快照与年度文件导入，简报 R2-11）、`platform_family`（带 Atypon、Silverchair、HighWire、OJS、DSpace、EPrints、InvenioRDM 的实例注册表）、`official_tdm_api`、`site_special`、`v1_bridge`。
   - 连接器只声明请求、解析响应。HTTP 一律经 02 P13 Egress Gateway（出站网关，平台侧唯一对外出口）执行；本文的 PoliteHttp 是网关内部使用的客户端库（简报 R2-08），负责 robots-first 闸、全局令牌桶和挑战检测；令牌桶的键为五元组 `(source, host, 上游请求类, 凭证, 出口 IP)`，出口 IP 维度只收紧、不叠加（§19 第 4 条）。
   - 调研期发生过 9 次"先请求后读 robots"（[AG §1.3.4][AG]），这类偏差由网关在结构上杜绝（SI-38）。
5. **策略引擎**（判定规则以 [08][08] §4.2 的 R1–R16 为准，本文是其实现，§6.2 在对应行标注 R 号）：
   - 五类信号各给出一个模式上限：文档化 API、bulk、逐主机 robots、ToS 自动化条款、TDMRep/Content-Signal/AI-UA。
   - 结构性上限另有七项：exec_side、商用门控、许可门控、证据时效、漂移状态、挑战冷却、红线。
   - 全部上限在全序 `background > on_demand > user_side > link_only > deny` 上取最小值。这五档是全库唯一的策略模式枚举，08 的判定名与 05 的策略快照都映射到它，不能一一对应时取更严者（简报 R2-09）。
   - 文档化 API 与 robots 冲突时，按简报 Q4 取 `on_demand` 并标 `needs_confirmation`（08 R5）；只有经书面确认的 PolicyOverride 才能放开后台收割。
   - PolicyOverride 只能放宽文档化 API、bulk、robots 三类冲突，不能放宽 ToS 禁令、TDM/AI 保留、挑战冷却与结构性上限（08 §4.4 纪律 2）；红线不可覆盖（P-05，SI-11/12）。
6. **漂移探针**周期比对以下内容：
   - robots 与 ToS 的哈希、tdmrep；
   - 挑战率、配额头；
   - DOI 前缀、member、publisher、落地域名；
   - "200 空体"与计数骤降、弃用公告。

   发现合规类漂移时按通道分档降级（简报 R2-15）：robots 与 TDM 信号漂移立即降级（全文降为 `link_only`）；ToS 哈希变化给 7 天宽限；元数据通道自身受影响时暂停并切换替补链。只降不升（SI-12）。
7. **接入计划**：
   - 多数期刊零代码，由 `crossref_delegated` 承接。
   - 新写代码只限有官方 API 或协议通道的来源（SI-09），例如 europe_pmc、pubmed（v2-P0，⚑ROBOTS，NCBI 书面确认后启用，简报 R2-13）、pmc、inspire_hep、zbmath_open、nasa_ads_scix（用户 token，R2-14）、aps_harvest、scoap3、plos、openreview（v2；平台侧共享收割待书面确认，R2-20）、dblp_drops（`bulk_snapshot`）、worldbank_dr、assa_program。
   - v1 的 20 个生产 adapter 按"包装 / 包装加修补 / 移植 / 仅用户侧 / 在线路径废止"五类去向处置（§7、§14）。
8. **摘要补齐链按出版方路由**：
   - 每条摘要记 `abstract_source` 与 `abstract_rights ∈ {open, publisher_copyright, personal_license, unknown}`，对应 CP 的 A/B/C 类与未知。
   - 卡片优先用 arXiv 等开放摘要。B 类最多展示到 DL3，且不得作为共享派生（TL;DR、翻译）的输入（P-02、LQ-05）；B 类默认纳入内部词法索引与嵌入（不展示），可经 `input_rights_max` 定点重建、可逆（简报 R2-21）；C 类永不进共享层。
   - Elsevier、APA、IEEE、AOM 等在 Crossref 中零摘要的出版方，各有替补链（[AG §2.6][AG]）。
9. **身份模型**分三层：Manifestation（源记录或载体）→ Version（按版本粒度的标识符做 union-find）→ Work（即 `cluster_id`，按多源投票通过的 `version_of` 边做 union-find）。
   - 标识符带粒度属性；第三方给出的 work 级 ID（OpenAlex W、S2 corpusId）只作为投票证据。
   - WP 与其发表版只建 `preprint_of` 边，不合并。
   - MinHash-LSH 加 Splink 只产生候审对，弱信号永不自动合并（D-007，SI-16/29）。
10. **语料流水线**为 harvest → normalize → identify → enrich → index → percolate，每段幂等，段间只经持久化实体通信。
    - 全文 fetch 移出后台，改为用户触发的按需服务；后台只把许可白名单内的 OA 全文取入共享层。
    - percolate 的输入不只是新 Work，也包括新增 Version 的已有 Work：预印本先入库、正式版后到时，关注该期刊的用户仍能收到（§10.7）。
    - "最新论文"以 Crossref `from-created-date` 加重叠窗口为主；`from-index-date` 只作周期补漏，因为它的结果约放大 100 倍。EPMC `FIRST_IDATE`、arXiv OAI 类目级 set（物理加 `physics:` 前缀）等按源定制。
    - 本地底座由 OpenAlex 季度快照、Crossref 年度文件、DROPS dblp 快照构成（`bulk_snapshot` 族），按"兴趣并集"导入子集。PubMed baseline 待 NCBI 书面确认后接入（简报 R2-13，§10）。
11. **enrich** 包括：
    - 主题：OpenAlex topic，约 12% 无 topic 的 work 由本地分类器补标；
    - 嵌入：按模型版本化，并记录输入基础；
    - 可共享 TL;DR 与翻译：只用 `public_shared` 输入，过三道闸；
    - 质量徽章与撤稿、OA 状态多源投票、许可多源取最严（§11）。
12. **用户侧全文**：平台只下发不含凭证的取回意图（RetrievalIntent，协议由 08 与 02 定义），本文为其候选方式提供声明式 FulltextRecipe。Companion Extension 或 pc-agent 在用户本人会话中单篇取回，私有存放：platform 部署默认只存设备本地，用户开启同步时服务端只存端到端密文（简报 R2-27）。
    - 平台出口不访问出版商的全文主机（P-03，CP HC-03/HC-04/HC-02）；任何部署都不批量取回；pc-agent 复用 v1 认证框架（§12）。
    - 用户侧的自动请求同样受 robots 与具名 AI-UA 规则约束（08 R2、R11、R16）。Atypon 族与 Springer 站点普遍对具名 AI UA 设有禁令，这些平台上的实际路径是"在出版社打开"加用户在场的一键保存，而不是后台 `user_fetch`（§12.3）。
13. **新增来源 SOP**：成本目标为已支持平台上的期刊或仓储实例 ≤30 分钟，新 connector ≤2 人日（§13）。
14. **跨文档对齐**：
    - 身份相关的表沿用 [05][05] 的物理表，本文只提语义增量（§9.7、§19 第 14 条）；
    - 策略规则沿用 [08][08] §4.2 的 R1–R16，覆盖记录沿用 08 §4.4 的确认登记（§6.2–§6.4）；本文的 PoliteHttp 是 [02][02] P13 Egress Gateway（出站网关）内部使用的客户端库（简报 R2-08，§5.1）；
    - 用户侧取回的协议沿用 [08][08] 与 [02][02]（§12.2、§19 第 15 条）；
    - SCD 的能力键沿用 [04][04] 的词表（§4.2、§19 第 16 条）；
    - 需求编号对应 [01][01] 已登记的 FR-17 至 FR-33、FR-85 与相关 NFR（§1.2）。

---

## 1. 功能说明

### 1.1 范围与边界

| 本文负责（定义） | 相邻文档负责（本文只引用或提供输入） |
|---|---|
| Source 与 Venue 的概念模型；注册表格式（SourceSpec v2、VenueSpec v2、实例注册表） | 物理表结构、分区、RLS（[05][05]） |
| SCD 的 schema 与静态取值；运行统计的产出口径 | 路由算法、TSRG、`route_stat` 计算、WatchKey 编译与调度（[04][04]） |
| ConnectorFamily 接口与各族职责；PoliteHttp 的两道合规闸（robots-first、挑战检测） | 令牌桶、AIMD、熔断、舱壁的算法与参数（[04][04]） |
| 策略引擎（取用决策）与漂移探针 | 权利引擎的展示与派生矩阵；DL0–DL4、M1–M25 与 `display_scope` 的映射（[08][08]） |
| 语料流水线六段的契约、幂等键、失败处理 | 任务队列实现与存储容量（[05][05]）；Percolator 的推荐侧匹配（[06][06]） |
| enrich 任务的定义；"共享派生"不变量的执行点 | 卡片字段取舍、学科模板、AI 标识样式（[07][07]）；LLM 路由合规（[08][08]） |
| 用户侧全文取回：候选方式的生成、FulltextRecipe、与 v1 认证框架的关系 | 扩展与 pc-agent 的形态与 API 面（02）；RetrievalIntent 与 PolicyBundle 的字段和签名（[08][08]）；凭证加密与同步（[05][05]、[08][08]） |
| 新增来源 SOP 与成本目标 | 支持名录文档本体（[DIR]）；里程碑与 AC 终编号（09） |

### 1.2 承接的需求与设计输入

| 用户需求 | 本文承接点 |
|---|---|
| R1 自定义来源与支持名录 | §2 来源模型、§3 SourceSpec、§5 连接器、§7 接入计划、§13 SOP；名录本体见 [DIR] |
| R2 查询、最新、筛选、多来源、组合 | §4 SCD（04 的唯一输入）、§10.4 最新论文增量、§10.5 本地底座 |
| R3 推荐与匹配 | §9 身份（去重与版本折叠）、§11 主题与嵌入 |
| R4 卡片 | §8 摘要补齐与权利、§11.4 共享 TL;DR 与翻译、§11.6 OA 状态 |
| 横切合规 | §6 策略引擎、§12 用户侧取回 |
| R5 开源与初创 | §5.6 可复用开源与排除清单（许可过 B-06）；各节引用的 OSS、PU、RT 结论 |

**R1 中"自定义论文来源"对用户的五种承接**（用户原话"自定义论文来源……都要写好或者准备写接口对接"）：
1. 关注或屏蔽任意 Source 与 Venue：由 [01][01] FR-28 定义，04、05、06 落实。本文保证每条 Manifestation 都带 `source_id`，屏蔽可以精确到来源，同一 Work 的其他来源不受影响。
2. 关注库中还没有的期刊：以自动 venue 即时满足元数据与最新论文（§2.5），同时生成策展工单。
3. 提交新来源登记请求：进入部署方审核队列；审核通过前，不向该来源的任何主机发请求（01 FR-29；§13.1）。
4. 用自己的凭证取全文：用户本人的 key 或机构会话，在用户侧执行（§12）。
5. 导入私有题录与名录：只进用户私域（§7.8；01 FR-30）。

**采纳的设计输入**（[SYN §6][SYN]）：
- SI-01 至 SI-20 全部采纳；
- 另采纳 SI-22（SCD）、SI-29（去重）、SI-37（限速账本的键）、SI-38（robots 先行闸）、SI-59 至 SI-61（与 07、08 共担）、SI-66（可导出、不锁定上游）、SI-67（依赖许可门禁）。

**采纳的合规硬约束**（CP 编号；[08][08] 保留原号统一登记）：HC-01 至 HC-11、HC-14（日志留存 ≥6 个月，§6.7）、HC-16、HC-20、HC-23 至 HC-28；另采纳 08 新增的 HC-29（robots 先行由出口层强制，含用户侧执行器）、HC-30（小样本门槛 `k_cf`/`k_reason`/`k_show`，简报 R2-04；本文用于标签纠正、配方健康统计与兴趣并集的细粒度键，取 `k_cf`，§10.5、§11.2、§12.4）、HC-31（needs_confirmation 通道）、HC-32（受限全文只单篇、显式取回）。HC-12（境内 LLM 路由）只引用，由 08 落实。

**需求候选**：本文先以 `FRc`/`NFRc` 占位；[01][01] 已按草案登记为正式编号，对应关系见右列，以 01 为准。另外，01 的 FR-26（分学科首批覆盖）由 §7 承接。

| 候选 | 内容 | 01 编号（草案） |
|---|---|---|
| FRc-03.1 | 支持名录与机读注册表：每个来源有状态、优先级、三通道声明与证据；文档名录由注册表生成 | FR-17、FR-18、FR-29 |
| FRc-03.2 | 零代码登记：已支持平台或族上的期刊、WP 系列、仓储实例，只需声明即可接入元数据与最新论文 | FR-19、FR-20、FR-29 |
| FRc-03.3 | 最新论文增量收割：按源定制游标，加重叠窗口与标识符去重，做到不漏不重 | FR-22 |
| FRc-03.4 | 本地底座：按全体用户兴趣并集导入快照子集；计量 API 只做增量与补查 | FR-22 |
| FRc-03.5 | 身份归并与版本关联：Work/Version/Manifestation 三层、多 ID 图、可回滚的合并、候审队列 | FR-23、FR-47（迁移） |
| FRc-03.6 | 摘要补齐与权利标注：按出版方路由的补齐链；每条摘要带来源与权利类别 | FR-24 |
| FRc-03.7 | enrich：主题、嵌入、可共享 TL;DR 与翻译、质量徽章与撤稿、OA 状态 | FR-25、FR-27 |
| FRc-03.8 | 用户侧全文取回：扩展或 pc-agent 单篇取回、私有存放、可选上传 | FR-31、FR-32、FR-33、FR-85 |
| FRc-03.9 | 策略引擎与漂移探针：五类信号取最严、`needs_confirmation` 流程、自动降级 | FR-21 |
| FRc-03.10 | 题录导入：RIS、BibTeX、EndNote、CSL-JSON（中文数据库导出的主通道），导入物归用户私域 | FR-30 |
| NFRc-03.1 | 礼貌：上游请求量不随用户数线性增长；每个上游只用一个平台身份（P-04，CP HC-10） | NFR-14 |
| NFRc-03.2 | 可审计：跨用户可见的字段 100% 可追溯到来源与许可证据（CP HC-28） | NFR-25 |
| NFRc-03.3 | 接入成本：期刊或仓储实例 ≤30 分钟；新 connector ≤2 人日 | NFR-22 |
| NFRc-03.4 | 可降级：每个 P0 能力至少 2 条同能力通道；任一上游失败都不致全局失败（P-09） | NFR-13 |
| NFRc-03.5 | 新鲜度：设计目标见 §10.9，待压测校准 | NFR-12 |

### 1.3 本文细化的设计规则（DR）

| # | 规则 | 来源 |
|---|---|---|
| DR-1 | **零接触优先**。元数据与最新论文通道的选择顺序：官方 bulk 或文档化 API（robots 允许）> `crossref_delegated` > 结构化官方页面（robots 允许）> feed（只作信号）> 无。有注册机构（Crossref、DataCite）可用时，不从出版商 HTML 取元数据 | D-005 延伸；[SS §3-1][SS] |
| DR-2 | **只为官方通道写代码**。WAF 或 robots 全禁的站点不写抓取型 connector | 简报 §6.1-4；SI-09 |
| DR-3 | **最严者为准，证据有时效**。每个合规字段有证据，超过 90 天未复核即进入降级流程（先经 `review_overdue` 宽限，简报 R2-16） | P-05；SI-11；[SYN §3.5][SYN]；R2-16 |
| DR-4 | **一个上游一个平台身份，全局礼貌**。令牌桶按上游计，不按用户计；禁止多 key、多 IP、UA 伪装 | P-04；CP HC-10；SI-37 |
| DR-5 | **robots-first 由网关强制**，不依赖调用方自觉 | SI-38 |
| DR-6 | **全文三档，受限全文在用户侧执行**：许可允许共享的 OA 全文进共享层；订阅全文由用户侧取回并私有存放；ToU 或 robots 禁止的只外链 | P-03；CP HC-03 |
| DR-7 | **派生继承最严，共享派生只用共享输入** | P-02；SI-60 |
| DR-8 | **可降级**：每个 P0 能力至少两级同能力替补 | P-09；[RT §3.5.5][RT] |
| DR-9 | **幂等且与顺序无关**：同一批输入以任意到达顺序处理，结果一致 | D-004、D-031 的纪律 |
| DR-10 | **可导出、可重建**：派生索引可从 corpus 重建；保留原始证据 | SI-66；[RT §10.7][RT] |

### 1.4 本文采用的默认假设

| # | 主题 | 默认假设 | 出处 | 若结论改变 |
|---|---|---|---|---|
| Q1 | 是否商业化 | `platform.commercial=false`；所有限非商业或需许可的来源已在注册表打上商用门控，切换即生效 | 简报 Q1；CP HC-23、DI-07 | 切为 true 后相关来源与共享自动停用（§6.2） |
| Q3 | 是否购买付费档 | 不购买 Crossref Metadata Plus 与 OpenAlex Member；用 polite 池加季度快照 | 简报 Q3 | 触发条件交 09（§20 第 5 条） |
| Q4 | robots 与文档化 API 冲突 | 冲突者取 `on_demand` 并标 `needs_confirmation`；取得书面确认前不做后台批量收割 | 简报 Q4 | PolicyOverride 放开（§6.4） |
| LQ-02 | B 类摘要能否用于内部索引与嵌入 | 默认允许进入内部 BM25 与嵌入输入（不展示，展示上限 DL3；简报 R2-21），但对有机器可读 TDM 保留的来源除外；设总开关，可经 `input_rights_max` 整体回退并重建 | CP §2.3.5、M5；[AG §3-9][AG]；R2-21 | 关闭开关后，嵌入按 `input_basis` 重建（§8.4、§11.3） |
| LQ-05 | B 类摘要能否作共享派生的输入 | 禁止 | 简报 P-02 | 由 08 放开 |
| LQ-07 | 受限全文在哪里执行 | 用户侧（扩展或 pc-agent）；平台出口不代取 | 简报 P-03 | — |
| — | robots 与具名 AI-UA 规则对用户侧操作的效力 | 平台侧与用户侧执行器的自动请求都受 robots 与具名 AI-UA 规则约束；只有用户在场的导航（在出版社打开）与用户在场的一键保存不受约束 | 08 的 HC-29、R2、R11、R16；另一种读法见 D-014 第 5 条与 [NS §4][NS] 第 1 条 | 由 robots ADR 裁定（§19 第 9 条、第 18 条；§20 第 1 条、第 18 条） |

---

## 2. 来源模型：Source 与 Venue 分离（①）

### 2.1 两层来源模型

| 层 | kind | 定义 | 例 |
|---|---|---|---|
| L1 | `publisher` | 出版商或学会平台，一般承载多刊 | `elsevier_sd`、`wiley`、`springer_link`、`aps`、`iop` |
| L1 | `preprint` | 预印本服务器，或工作论文（WP）系列的发行机构 | `arxiv`、`biorxiv`、`psyarxiv`、`ssrn`、`nber_wp`、`ecb_wp` |
| L1 | `journal_platform` | 学会自营期刊平台、单刊平台、overlay 平台 | `informs_pubsonline`、`aom_journals`、`scipost`、`elife`、`jmlr` |
| L1 | `conference_platform` | 会议论文集或评审平台 | `openreview`、`pmlr`、`cvf_open_access`、`acl_anthology`、`assa_meetings` |
| L2 | `repository` | 仓储（自存档、OA 全文） | `pmc`、`zenodo`、`hal`、`econstor`、`core` |
| L2 | `aggregator` | 聚合器、DOI 注册机构、学科库、信号层 | `crossref`、`openalex`、`europe_pmc`、`inspire_hep`、`dblp`、`hf_papers` |
| L2 | `registry` | 身份、机构与标识符注册表（简报 R2-11 新增的 L2 子类型） | `orcid`、`ror`、`datacite` |

L2 另按职能标注 `roles`（依据 [AG §2.1][AG]、[AG §3][AG] 第 1 条）：

| role | 含义 | 代表 |
|---|---|---|
| `authority` | DOI 注册机构，提供书目事实 | Crossref、DataCite |
| `breadth` | 覆盖面主干与主题图谱 | OpenAlex |
| `signal` | 嵌入、引文、社区热度 | S2、OpenCitations、HF Papers |
| `discipline` | 学科库 | Europe PMC、PubMed、INSPIRE、zbMATH、RePEc、dblp 快照、ADS、EconBiz |
| `fulltext` | OA 全文定位与仓储 | PMC、CORE、OpenAlex content、各仓储 |
| `registry` | 注册表（kind 为 `registry` 的来源恒带此 role；DOAJ、Open policy finder 这类目录型聚合器也可带） | ORCID、ROR、DataCite、DOAJ、Open policy finder |
| `regional` | 区域平台 | J-STAGE、SciELO、CiNii |

### 2.2 实体与关系

配图 [v2-03-source-model.svg][DIAG] 给出全貌，关系如下：

| 关系 | 基数 | 语义 |
|---|---|---|
| Source —has→ SourceChannel | 1:3 | 每源恰有 metadata、latest、fulltext 三条通道；某条缺失写 `method: none` |
| SourceChannel —implemented_by→ Connector | N:1 | 通道由某族的某个连接器实现，可带实例 |
| Connector —describes→ SCD | 1:N | 连接器为其每个端点给出静态 SCD |
| Source —hosts(period)→ Venue | N:M | HostingPeriod：托管平台、DOI owner prefix、Crossref member，随时间变化 |
| Venue —has→ VenueKey | 1:N | 多键归一（§2.3） |
| Venue —edge→ Venue | N:M | 演化边（§2.3） |
| Venue —has→ VenueEdition | 1:N | 期刊卷期、会议届与 track、论文集卷 |
| Version —published_in→ Venue / VenueEdition | N:1 | 发表关系 |
| Version —presented_at→ MeetingEvent | N:M | 经管会议的报告事件，不产生 Version（§2.4） |
| Policy Engine —decides→ (SourceChannel, Operation) | — | 输出 AccessMode 与 `needs_confirmation`（§6） |
| DriftProbe —observes→ Source 主机与 Venue 归属 | — | 更新策略输入，提出托管史变更提案（§6.5） |
| EvidenceRecord —backs→ 合规字段 | N:M | 每个合规字段至少一条证据（§3.3） |

### 2.3 Venue 多键归一与演化边

**VenueKey**：

| 键 | 例 | 取值来源 | 注意 |
|---|---|---|---|
| `issn`（印本、电子、历代，带 `type` 与 `since/until`） | PRB：0163-1829、1098-0121、2469-9950 等 | Crossref `/journals`、OpenAlex source | PRB 刊记录挂 7 个历代 ISSN，2016 年切换前后必须合并查询（[NS §0][NS] 第 1 条、[AG §2.6][AG]）；Nature Methods 的 ISSN 错挂在 Nature Chemical Biology 刊记录下，但按 ISSN 枚举出的作品正确（[AG §2.2.1][AG]）；Proc B 印本与电子各有一条刊记录（[LS §2.4.18][LS]）；Elsevier CS 刊在 Crossref 只认印本 ISSN（[CS §2.1.3][CS]） |
| `issn_l` | — | 与 ISSN 集合、OpenAlex source 一起做归一主键 | 不以单个 ISSN 作主键（[AG §2.6][AG]） |
| `openalex_source` | `S…` | OpenAlex | 其 host 字段**不能**用于路由：IHÉS 已迁 Centre Mersenne，OpenAlex 仍记为 Springer（[NS §3][NS] 第 9 条） |
| `dblp_key` | `conf/iclr`、`journals/jmlr` | DROPS 月度快照 | 在线主站全禁（[CS §0][CS] 第 1 条） |
| `openreview_prefix` | `ICLR.cc/{year}/Conference` | OpenReview | 大小写逐年不一，保留逐届覆盖表（v1 `iclr.yaml`） |
| `crossref_owner`（member、owner prefix，带时间段） | openRxiv：member 54368、owner prefix 10.64898 | Crossref | `prefix:` 过滤按记录的 owner prefix 匹配，**不按 DOI 字符串**；旧 `10.1101/…` 预印本已转入 openRxiv 名下（[LS §2.2.1][LS]） |
| `doi_string_prefix`（带时间段） | `10.1101` | DOI 本身 | 同一字符串前缀可能分属多方（CSHL 期刊与旧 bioRxiv），**永不单凭字符串前缀路由**（[LS §3][LS] 第 12 条） |
| `container_title`（按届/卷） | "Proceedings of the ACM Web Conference 2026" | Crossref | 标题含逗号时，精确过滤会报 `pair-list-form-invalid`，须退回 query 加本地核对（[CS §2.1.4][CS]） |
| `isbn`（按卷） | ICM 论文集卷 | Crossref | 用于 `proceedings_series` 与 book 结构（SODA） |
| `arxiv_category` | `cs.LG` | arXiv | 别名如 `math.MP ≡ math-ph`、`stat.TH ≡ math.ST`；去重键永远是 arXiv id（[NS §2.3.5][NS]） |
| `repec_series` | `RePEc:nbr:nberwo` | RePEc bulk | WP 系列与发表版的关联证据 |
| `ranking_labels` | CCF 等级、ICORE 等级、UTD24 成员 | 各名录 | 许可各异：CSRankings 为 CC BY-NC-ND，只记成员资格事实；ICORE 许可 ⚠（[CS §2.5][CS]） |

**归一流程**（normalize 段调用）：

```python
# 设计伪代码 —— venue 归一
def resolve_venue(rec: NormRecord) -> VenueMatch:
    cands: set[VenueId] = set()
    for issn in rec.issns:                               # 印本、电子、历代逐一尝试
        cands |= venue_by_key("issn", issn)
    cands |= venue_by_key("openalex_source", rec.openalex_source)
    cands |= venue_by_key("dblp_key", rec.dblp_venue_key)
    cands |= edition_lookup(rec.container_title, rec.isbn, rec.openreview_group)
    scored = [(v, match_score(v, rec)) for v in cands]   # 三方校验：member、container-title、owner prefix（SI-03）
    if not scored:
        return propose_auto_venue(rec)                   # §2.5：由 Crossref 或 OpenAlex 的 source 记录自动建 venue
    best, s = max(scored, key=lambda x: x[1])
    if s < TAU_VENUE or ambiguous(scored):
        return VenueMatch(best, confidence="low", review=True)   # 进 venue 候审，例如 ISSN 错挂
    return VenueMatch(best, confidence="high")
```

**演化边（VenueEdge）**：

| 边 | 语义 | 例 | 依据 |
|---|---|---|---|
| `renamed_to` | 更名或换 ISSN，内容连续 | TASLP：2329-9290 → 2998-4173；USENIX ATC → ACM SIGOPS ATC | [CS §2.1.3][CS]、[CS §2.5][CS] |
| `journalized_as` | 会议论文集期刊化 | SIGMOD → PACMMOD；FSE → PACMSE | [CS §3][CS] 第 14 条 |
| `co_hosted_on` | 同一届同时发布在多个平台 | CVPR：CVF 与 IEEE；ECCV：LNCS 与 ECVA | [CS §3][CS] 第 14 条 |
| HostingPeriod（托管或出版方迁移，venue 不变） | 平台、DOI 所有权随时间变化 | IHÉS → Centre Mersenne；Child Development → OUP；RSC → Silverchair；BMC 与 EMBO → Springer Link | [NS §0][NS] 第 4 条、[LS §2.4.2][LS]、[LS §2.4.10][LS] |
| `split_from` / `merged_into` | 分刊、合刊 | 调研中暂无实例，预留 | — |
| `status` | `active`、`ceased`、`transformed` | MIT SMR 停印，转为纯数字版 | [SS §0][SS] 第 11 条 |

### 2.4 学科差异建模（SI-20）

| 学科 | venue kind | 届与卷的建模 | 要点 | 依据 |
|---|---|---|---|---|
| 理科（物理、数学） | `journal`；`proceedings_series` | 论文集按"卷 = 会议"建 VenueEdition；ICM 为 edited-book 卷 | 用 Crossref 前缀加 `type:proceedings-article`，或 container-title 枚举（JPCS、AIP CP、Proc SPIE、PoS、EPJ WoC）；INSPIRE conferences 记录作 HEP 会议索引；BAPS 摘要只外链 ⚠ | [NS §2.7][NS]、[NS §3][NS] 第 1 条 |
| CS/AI | `conference`（多键）；`journal` | VenueEdition = 届（年）× track；每届的键包括 dblp 卷 key、OpenReview group、PMLR 卷号、CVF 年路径、Crossref container-title 或 ISBN | 有演化边；新鲜度阶梯 L0–L3 记在 edition 上；Curran 10.52202、IJCAI 10.24963 的前缀被多个会议共用，须按 container-title 拆分 | [CS §3][CS] 第 3/5/14 条 |
| 经济/金融 | `journal`；`wp_series`；`meeting` | WP 系列是一等 venue，带发行机构、编号规则、DOI 前缀与注册机构、原生通道；会议是 `meeting`，论文以 `presented_at` 事件挂接 | ASSA 程序提供 JEL 与 session；NBER SI 议程链到 w 号；WFA 与 SFS 只作会议标签 | [SS §2.9][SS]、[SS §3][SS] 第 11/15 条 |
| 商业/管理 | `journal`；`meeting`；`proceedings_series` | AOM Annual Meeting Proceedings 有 DOI（`10.5465/amproc`），建为 `proceedings_series`，默认只作作者兴趣信号 | UTD24 名录内置 | [SS §2.5][SS]、[SS §2.7][SS] |
| 生命科学、心理 | `journal`；`preprint_server` 与 `preprint_category`；`conference`（CogSci） | CogSci 届 = 卷，取 eScholarship OAI 的 `dc:source`；bioRxiv 与 medRxiv 的学科作 `preprint_category` | ISMB 并入 Bioinformatics，RECOMB 并入 LNCS ⚠ | [LS §2.5][LS] |
| 预印本（全学科） | `preprint_server`；`preprint_category` | arXiv 类目、OSF provider、bioRxiv subject | 类目是频道维度，不是身份维度 | [NS §2.3.5][NS]、[LS §2.2.3][LS] |

**`wp_series` 的专有字段**：
- `issuer`：发行机构；
- `numbering{pattern, id_scheme}`：编号规则，例如 NBER `w{n}`，标识符方案 `nber_w`；
- `doi{prefix, ra}`：`ra` 取值 `crossref`、`datacite`、`op`、`none`。ECB 的 DOI 由欧盟出版局 RA（OP）登记，不在 Crossref（[SS §2.4][SS]）；
- `open_after_months`：例如 NBER 的 18 个月规则。不利用软门（D-014）；
- `container_filter`：例如 IMF 在 Crossref 中混有大量 component 与 chapter，须过滤（[SS §2.4][SS]）。

新增的标识符方案有 `wb_repnb`、`iza_dp`、`cepr_dp`、`ecb_wp`、`bis_wp`、`imf_wp`（[SS §3][SS] 第 15 条）。

**`MeetingEvent`**：字段为 `(event_id, meeting_venue_id, year, session_id, title, jel_codes[], hosted_by, date, location, source_url)`。关系 `presented_at(version_id, event_id, evidence)` 为 N:M，一篇论文可以有多次报告。报告事件**不产生 Version**，只是论文的属性，并作为推荐信号，因为经管会议论文的公开全文几乎都以 SSRN 或作者主页版本存在（[SS §2.9][SS]）。

### 2.5 策展 venue 与自动 venue

| `curation` | 来源 | 内容 | 用途 |
|---|---|---|---|
| `curated` | `registry/venues/**/*.yaml`（人工 PR） | 键、演化边、届表、特殊路由、摘要链覆盖 | 需特殊处理的 venue：ISSN 冲突、非 DOI 会议、有 RSS 或 OAI 等原生通道、WP 系列 |
| `auto` | 由 Crossref `/journals/{issn}` 或 OpenAlex source 记录自动建立 | 只含键与默认路由（`crossref_delegated`） | 用户关注任意期刊时无需写 YAML；覆盖长尾 |
| `user_proposed` | 用户"关注此刊"时库中没有该刊 | 提案 → 自动核验（ISSN 在 Crossref 可枚举、member 可映射）→ 转为 `auto` | 冷启动与长尾 |

自动 venue 的出版方若尚未登记为 Source，归入占位 Source `unregistered_publisher`：元数据只经 Crossref，全文只给外链。出现以下任一情况时，自动 venue 升为策展 venue：键冲突、漂移告警、需要摘要链覆盖、有原生通道。

自动 venue 的三条约束：
- **名称与键以作品为准**：名称取按 ISSN 枚举出的作品 `container-title` 分面的众数，并与 OpenAlex source 交叉核对；不直接采用 Crossref 刊级记录的 title。反例：`/journals/1548-7091` 返回的刊名是 Nature Chemical Biology，而按该 ISSN 枚举出的作品几乎全是 Nature Methods（[AG §2.2.1][AG]）。众数与刊级记录不一致时，进 venue 候审。
- **只经已登记的来源发请求**：`user_proposed` 的自动核验只调用已登记且策略允许的 Source（Crossref 的 `/journals/{issn}`、OpenAlex source 单查），与一次联邦 LOOKUP 同级（on_demand）。它不向该期刊自己的站点或任何未登记主机发请求，因此不违反 v1 红线 4（"只处理注册表内 venue"），也符合 01 FR-29 对"新来源登记请求"的零请求要求：新**来源**（新主机）走 §13.1 的审核队列，审核通过前零请求。
- **限频**：每个用户每天的提案数设上限（初值 20，⚠ 设计值），防止把平台当作 Crossref 代理。

### 2.6 注册表与名录状态

- **单一事实来源**：`registry/` 下的 YAML（§3.1）经加载器校验后，写入 corpus 与 ops 的注册表快照（表结构由 [05][05] 定义）。文档名录 [catalog/source-directory][DIR] 由注册表生成（简报 §6.1-7；[SYN §3.5][SYN] 第 1 条）。
- **名录状态**按简报 R2-10 拆为两个字段：`directory.v2_status` 取简报 §6.1-7 枚举中除 `v1-implemented` 外的 7 个值：`v2-P0` / `v2-P1` / `v2-P2` / `metadata-only` / `link-only` / `user-import-only` / `excluded`，允许写作 `metadata-only（P1）`，括号内来自 `directory.priority`；`v1.status`（即名录与 05 `corpus.source` 的 `v1_status`）取 `v1-implemented` / `v1-partial` / `v1-designed-only` / `—`（[SYN §3.1][SYN]）。
- **两种状态分开**：`directory.v2_status` 是产品承诺，只能经 PR 变更，且必须写明依据（例如 `metadata-only → v2-P1` 需要一手条款或书面确认，[SYN §3.5][SYN] 第 4 条）；SourceChannel 的 `state` 是运行时合规状态，由策略引擎与探针改写（§6）。
- **规模参照**：[SYN §3.3][SYN] 的 187 行候选中，`v2-P0` 36、`v2-P1` 63、`v2-P2` 44、`metadata-only` 26、`link-only` 2、`user-import-only` 3、`excluded` 13。实现期以这 187 行作首版种子导入注册表。


---

## 3. SourceSpec v2（②）

### 3.1 注册表布局

```text
registry/                                  # 实现期落地；机读单一事实来源（简报 §6.1-7）
├── sources/<source_id>.yaml               # SourceSpec v2（本节）
├── venues/<discipline>/<venue_id>.yaml    # VenueSpec v2，只收策展 venue（§2.5）
├── instances/<family>/<instance_id>.yaml  # platform_family 实例（DSpace、OJS、Atypon 等）
├── evidence/<source_id>.yaml              # 证据记录，可从 SourceSpec 内联拆出
└── schema/                                # sourcespec / venuespec / instance / scd 的 JSON Schema
```

- 注册表变更一律走 git PR，沿用 v1 D-008 的 docs-as-code 模式。
- 紧急降级不改 YAML：由策略引擎或运维写入 `ops` 层的覆盖记录（§6.4），事后再回写 YAML 对账。
- v1 的 `venues/**`（62 个 VenueSpec）只供维护冻结中的 v1 CLI 使用；v2 的 venue 由转换器生成到 `registry/venues/`（§3.7）。

### 3.2 顶层字段

| 字段 | 类型 / 取值 | 必填 | 说明 | 依据 |
|---|---|---|---|---|
| `schema` | `sourcespec/v2` | ✓ | 版本标记；破坏性变更递增版本号 | v1 `spec_version` 惯例，[v1-02][v1-02] §4 |
| `source_id` | snake_case | ✓ | 全局唯一、永不复用，与文件名一致；沿用 [SYN §3.1][SYN] 统一后的 id | [SYN §3.1][SYN] |
| `aliases_of` | list[id] | — | 合并掉的旧 id，例如 `cell_press` → `elsevier_sd` | [SYN §3.1][SYN] |
| `names` | {full, short?, aliases[]} | ✓ | 展示名 | — |
| `layer` | `L1` / `L2` | ✓ | 两层来源模型 | 简报 §6.1-1 |
| `kind` | §2.1 七值（L2 含 `registry` 子类型） | ✓ | 必须与 layer 相容 | 简报 §6.1-1；R2-11 |
| `roles` | list（§2.1） | L2 必填 | L2 的职能 | [AG §2.1][AG] |
| `disciplines` | list：`math`、`physics_astro`、`chem_materials`、`earth`、`life_med`、`psych`、`econ_fin`、`business_mgmt`、`cs_ai`、`regional`、`general` | ✓ | 与 [SYN §3.1][SYN] 的学科代码一一对应 | [SYN §3.1][SYN] |
| `directory` | {v2_status, priority, since, rationale, survey_refs[]} | ✓ | 名录的 v2 状态与登记优先级（§2.6） | 简报 §6.1-7；R2-10 |
| `owner_org` | {name, crossref_members[], doi_prefixes[], ror?} | 建议 | DOI 字符串前缀与 Crossref owner 分开记 | [LS §3][LS] 第 12 条 |
| `hosting` | list[{platform_family, instance_id, since, until?}] | 建议 | 托管平台史 | [NS §0][NS] 第 4 条 |
| `hosts` | list[{host, role}]，role 取 `site`、`api`、`bulk`、`feed`、`oai`、`cdn` | ✓ | 本源会接触的**每个**主机都必须有 robots 结论，包括 bulk 主机 | [AG §1.3.4][AG] 核验补充 |
| `channels` | {metadata, latest, fulltext} | ✓ | 三条 SourceChannel（§3.3） | 简报 §5 |
| `defaults` | {display_scope: {metadata, abstract, fulltext}} | ✓ | 源级默认值，通道可覆盖 | 简报 P-02 |
| `commercial_gate` | {noncommercial_only, requires_license, license_on_file?} | ✓ | 商用开关的输入（§3.5） | CP HC-23、DI-07 |
| `attribution` | {text, required, render_on[]} | 条件 | 例：NLM、"Semantic Scholar"、CORE、CC 的 TASL | CP HC-24 |
| `storage_policy` | {raw_payload_retention, currency_rule, delete_on_upstream_delete, cache_mode} | ✓ | 原始载荷保留期；NLM 要求"保持最新，或声明非最新"；`cache_mode ∈ {store_shared, ttl_only, display_only}` 决定联邦结果与网关缓存的去向（如 S2 只许访问与展示，取 `ttl_only` 或 `display_only`；02 §2.3.3、§2.3.13；一致性审计 2026-09-27 按 02 的请求补入） | CP §2.1；LQ-18；OSS §3-7 |
| `identifiers_emitted` | list[{scheme, granularity}] | ✓ | 本源产出的标识符及其粒度（§9.1） | — |
| `review` | {verified_at, next_review_by, reviewer} | ✓ | `next_review_by` 不得晚于 `verified_at` 后 90 天 | [SYN §3.5][SYN] 第 2 条 |
| `v1` | {adapter, status, disposition} | ✓ | status 即 `v1_status`，取 `v1-implemented`、`v1-partial`、`v1-designed-only`、`—`（R2-10）；disposition 见 §14.1 | [SYN §3.1][SYN] |
| `notes` | text | — | — | — |

### 3.3 SourceChannel 字段

三条通道共用一套字段；`incremental` 只对 latest 必填。

| 字段 | 类型 / 取值 | 必填 | 说明 |
|---|---|---|---|
| `method` | `crossref_delegated`、`oai_pmh`、`rest_api`、`bulk_snapshot`、`feed`、`site_pages`、`tdm_api`、`user_session`、`openurl`、`link_out`、`none` | ✓ | 取得方式 |
| `connector` | {family, id, instance?} | method≠none 时 ✓ | 实现者（§5） |
| `endpoints` | list[{endpoint_id, base_url, path_templates, docs_url}] | 条件 | `endpoint_id` 即 SCD 的键（§4） |
| `auth` | {kind, secret_ref?} | ✓ | kind 取 `none`、`contact_email`、`platform_key`、`platform_account`、`user_key`、`user_oauth`、`user_session`、`institutional_ip`、`contract`。`secret_ref` 只能指向部署级密钥（简报 §6.3-3）；用户级凭证永不出现在注册表 |
| `exec_side` | `platform` / `user` | ✓ | `auth.kind` 为 `user_*` 时必须是 `user`（P-03） |
| `rate` | {ceiling, per_request_class, concurrency, quotas, budget, header_signals[], start_fraction} | 条件 | 书面上限是天花板，AIMD 只降不超（[RT §9.1][RT]）；算法与起步值由 [04][04] 定 |
| `robots` | list[{host, paths_used[], verdict, crawl_delay_s, ai_ua?, snapshot_sha256, fetched_at}] | ✓ | verdict 取 `allow`、`allow_with_delay`、`disallow`、`unreadable`、`absent`、`not_applicable`（§3.4）。`ai_ua` 记该主机对具名 AI UA 的规则：`{named_blocked[], scope: site | paths, paths[]}`。只有 `paths_used` 非空的主机参与本通道的裁决；站点主机若不在本通道访问范围内，记 `paths_used: []` |
| `robots_verdict` | 同上 | 派生 | 该通道所用各主机（`paths_used` 非空）中最严者 |
| `crawl_delay_s` | number | 派生 | 各主机的最大值 |
| `tos_automation` | `allowed`、`silent`、`api_only`、`user_initiated_only`、`forbidden`、`contract_required`、`unknown` | ✓ | 在 [SS §3][SS] 第 9 条四个取值的基础上，增加了 `silent`（已读条款、未见自动化条款）与 `unknown`（条款未读到），并单列 `contract_required` |
| `ai_bot_sensitivity` | `none`、`named_ai_ua_blocked_site`、`named_ai_ua_blocked_paths`、`unknown` | 派生 | 由所用主机的 `robots[].ai_ua` 派生，取最严值。例：ScienceDirect 点名禁止 claude-code（站点级）；INFORMS 对 AI UA 禁全文路径（路径级）。判定口径见 §6.2 的 S5 行（08 R11） |
| `api_quota` | 结构化文本 | 条件 | 例：`OA API 500/日/key、100/分` |
| `tdm_policy_url` | URL | 条件 | 出版方的 TDM 政策页 |
| `tdmrep` | {state, policy, fetched_at}，state 取 `absent`、`reservation_0`、`reservation_1`、`unreadable` | fulltext ✓ | 例：Springer Nature 为 `tdm-reservation: 1` |
| `content_signal` | {search, ai_input, ai_train}，各取 `yes`、`no`、`absent` | 条件 | Cloudflare Content Signals（CP C47） |
| `license_policy` | {record_license, abstract_rights_default, item_license_field, fulltext_policy, derivation, output_limits} | ✓ | 例：Elsevier 的 TDM 产出片段 ≤200 字符 |
| `display_scope_default` | `public_shared`、`per_user_only`、`link_only` | ✓ | 最终范围以权利门为准（[08][08]） |
| `incremental` | {cursor_kind, overlap, backfill, schedule_class, calendar?} | latest ✓ | 见 §10.4 |
| `fallbacks` | list[channel_ref] | P0 ✓ | 同能力替补链（P-09） |
| `evidence` | list[{id, claim, url, verified_at, grade, survey_ref, by}] | ✓ | grade 取 `LIVE`、`DOC`、`SNIPPET`、`3P`，沿用各调研的证据分级；落到 05 RightsTag 的 `evidence_grade` 时，`LIVE`、`DOC` 记为 A（一手），`SNIPPET`、`3P` 记为 B。`by` 取 `human` 或 `probe`：探针复测结果与原证据一致时自动续期（§6.5） |
| `state` | `planned`、`active`、`review_overdue`、`needs_confirmation`、`degraded`、`suspended` | ✓ | 运行态由策略引擎与探针改写（§6）；`review_overdue` 为证据复核逾期的宽限态（简报 R2-16，§6.2） |

### 3.4 合规字段的取值口径

| 字段 = 取值 | 含义 | 判定口径 | 例 |
|---|---|---|---|
| robots = `unreadable` | robots.txt 本身被挑战或拦截；或返回 5xx、超时 | 平台与用户侧的自动请求都视同 `disallow`（08 R3）；不重试、不绕过。5xx 与网络错误按 RFC 9309 §2.3.1.4 须"假定全禁"；该标准允许在持续约 30 天后改用缓存副本，本文不用这条放宽 | ACS、AMS、Cambridge、Preprints.org、SPIE（[NS §0][NS] 第 6 条） |
| robots = `absent` | robots.txt 返回 404 或 410 | 不构成限制；仍受 ToS 约束（08 R4；RFC 9309 §2.3.1.3 把 4xx 归为"unavailable"，爬虫可以访问） | api.crossref.org（[AG §2.5][AG]） |
| robots.txt 返回 401、403 | 4xx 中的鉴权与拒绝类 | RFC 9309 同样归为 unavailable，但无法区分源站应答与 WAF 拦截，按 08 R3 从严记为 `unreadable`。确属源站应答、且运营方另有机器分发意图的，可在 robots ADR 中逐站登记例外（先例：v1 对 `www2.nber.org` 的附条件放行，[v1-AGG][v1-AGG] §5.7） | www2.nber.org（v1 先例） |
| robots = `not_applicable` | 非网页主机，例如 S3 桶或数据集下载 | 以该数据集条款为准 | `s3://pmc-oa-opendata`、`s3://openalex` |
| robots = `allow_with_delay` | 允许，但有 Crawl-delay | 平台请求间隔 ≥ delay | www.ebi.ac.uk 对通用 UA 为 10 s（[AG §2.2.10][AG]） |
| tos = `silent` | 已读 ToS，其中没有自动化条款 | 不构成限制 | — |
| tos = `api_only` | 网站禁止系统化访问，但官方 API 或 bulk 是被许可的机器通道 | 只允许经 API 或 bulk | Elsevier：挖掘必须经 API（CP §2.3.1）；APS：网站 ToS 禁止系统化下载，Harvest API 是官方通道（[NS §2.3.1][NS]） |
| tos = `user_initiated_only` | 只允许用户交互、单篇 | 平台不自动化 | INFORMS（摘要级证据 ⚠，[SS §3][SS] 示例） |
| tos = `forbidden` | 禁止任何自动化查询 | `link_only` | SSRN ToU（[SS §0][SS] 第 1 条） |
| tos = `contract_required` | 机器访问须另签协议 | 取得合同前 `link_only` | IOP：2026-07 版起，API、机器可读 feed、MCP、自动化 agent 都须另签协议（[NS §2.3.1][NS]） |
| tos = `unknown` | 条款未读到或读不到 | 上限 `on_demand`，并标 `needs_confirmation` | AOM、Emerald 的 TDM 条款未取得（[SS §4][SS] 第 4 条） |
| tdmrep = `reservation_1` | 机器可读的 TDM 保留（DSM 第 4 条）；政策页中的自然语言明示保留同样按此处理（08 §4.1 第 5 项） | 全文自动化与派生按保留处理（§6.2 S5 行，08 R9） | link.springer.com、nature.com（[NS §2.3.4][NS]） |
| tdmrep = `unreadable` | `tdmrep.json` 被挑战或拦截 | 从严按 `reservation_1` 处理；用户本人许可的 `tdm_api` 不受影响（08 R9） | tandfonline、Wiley 的 `tdmrep.json` 为 403 挑战（[SS §1.3][SS] 过程记录） |

### 3.5 exec_side、display_scope 默认值与商用门控

- **exec_side**：
  - `platform` 表示由平台 worker 以平台身份执行，使用部署级凭证与单一 UA；
  - `user` 表示由用户的 Companion Extension 或 pc-agent（02 的 U2、U3）执行，使用用户本人的会话或 key。
  - `user` 通道的产物一律归用户私域（HC-01）。**即使许可是 CC BY 也不例外**：共享副本必须由平台经公开通道自行取得。数据域由来源决定，而不是只看许可。
- **display_scope**：
  - 通道给出默认值，最终范围取"通道默认、单篇许可、权利门结论"三者中最严的一个（派生继承最严，P-02）。
  - 权利门的矩阵，即展示级别 DL0–DL4（CP 的 V0–V4，简报 R2-03）、M1–M25 与 `display_scope` 的映射，由 [08][08] §3.3 定义：DL4、DL3、DL2 ↔ `public_shared`（按级别封顶）；DL1 ↔ `link_only`；DL0 ↔ `per_user_only` 或不入库。字段级权利标注（CP HC-07）用 08 §3.2 的 RightsTag，物理列组见 05 §2.3；本文的通道默认值、摘要变体与共享 OA 资产都按它落标签。
- **commercial_gate**：
  - `noncommercial_only=true` 的来源或内容，在 `platform.commercial=true` 时自动停用。这类包括 ORCID 公共 API、J-STAGE（商用须申请）、CC BY-NC 内容，以及出版商 TDM 流程（Elsevier、Wiley、SN、T&F 均限非商业）。MSC2020 标签空间（CC BY-NC-SA）属系统自身的数据依赖，按简报 R2-22 不作 TopicNode 默认叶子，作可选插件、任何部署都默认不加载；显式开启后仍受本开关强制关闭（08 §3.8）。
  - `requires_license=true` 的来源在 `license_on_file` 有证据之前不启用，例如 CORE：推荐与检索类产品须取得许可；Open policy finder：CC BY-NC-ND。
  - 依据：CP HC-23、DI-07；[AG §2.2.5][AG]；[NS §0][NS] 第 9 条。

### 3.6 示例

以下示例中的字段值均引自调研；标 ⚠ 的待实现前复核。

**示例 A：`crossref_delegated` 期刊平台**（元数据零代码，全文在用户侧）

```yaml
# 设计伪代码 —— registry/sources/informs_pubsonline.yaml
schema: sourcespec/v2
source_id: informs_pubsonline
names: {full: "INFORMS PubsOnline", aliases: [INFORMS]}
layer: L1
kind: journal_platform
disciplines: [business_mgmt, econ_fin]
directory: {status: v2-P0, priority: P0, rationale: "UTD24 中 7 刊", survey_refs: ["SS §2.3", "SS §3.1", "SYN §3.2.5"]}
owner_org: {name: INFORMS, doi_prefixes: ["10.1287"]}          # member id ⚠ 未在调研中登记
hosting: [{platform_family: atypon, instance_id: informs_pubsonline}]
hosts:
  - {host: api.crossref.org, role: api}
  - {host: pubsonline.informs.org, role: site}
channels:
  metadata:
    method: crossref_delegated
    connector: {family: crossref_delegated, id: crossref}
    endpoints: [{endpoint_id: crossref.journal_works}]
    auth: {kind: contact_email, secret_ref: deployment/crossref_mailto}   # polite 池
    exec_side: platform
    rate: {inherit_from: crossref}                  # 令牌桶属于 crossref 源，不按 venue 叠加
    robots: [{host: api.crossref.org, verdict: absent}]
    tos_automation: allowed
    ai_bot_sensitivity: none
    license_policy: {record_license: facts, abstract_rights_default: publisher_copyright}
    display_scope_default: public_shared
    fallbacks: [openalex.works_get]
    evidence:
      - {claim: "INFORMS 刊 Crossref 摘要覆盖 85–97%", url: "https://api.crossref.org/journals/{issn}",
         verified_at: 2026-09-26, grade: LIVE, survey_ref: "SYN §3.2.5"}
    state: active
  latest:
    method: crossref_delegated
    connector: {family: crossref_delegated, id: crossref}
    endpoints: [{endpoint_id: crossref.journal_works}]
    exec_side: platform
    incremental:
      cursor_kind: created_date
      overlap: P3D
      backfill: {kind: index_date, schedule: weekly}
      schedule_class: continuous
    fallbacks: [openalex.works_list]
    state: active
  fulltext:
    method: user_session
    connector: {family: platform_family, id: atypon, instance: informs_pubsonline}
    exec_side: user
    auth: {kind: user_session}                       # 机构 IP、SSO 或会员登录，均在用户侧
    robots:
      - {host: pubsonline.informs.org, paths_used: ["/doi/pdf/", "/doi/epdf/"],
         verdict: allow_with_delay, crawl_delay_s: 1,          # `*` 不禁 /doi/（SS §2.1 #16）
         ai_ua: {named_blocked: [GPTBot, ChatGPT-User, Google-Extended, PerplexityBot, anthropic-ai],
                 scope: paths, paths: ["/doi/full", "/doi/pdf", "/doi/epdf"]}}
    tos_automation: user_initiated_only              # T&C 摘要级证据：未经批准禁止系统性下载 ⚠
    ai_bot_sensitivity: named_ai_ua_blocked_paths    # 派生自上行 ai_ua
    tdmrep: {state: absent}                           # /.well-known/tdmrep.json 404
    license_policy: {fulltext_policy: per_item, item_license_field: "crossref.license[]"}
    display_scope_default: per_user_only
    rate: {ceiling: {min_interval_s: 6}, quotas: {daily_per_user: 200}}   # v1 04 §4 的纪律，按用户计
    state: active
    # 期望裁决（§15.3 黄金决策表）：LOCATE_FULLTEXT 的 user_fetch 为 link_only，只给 open_in_tab
    # 与用户在场的一键保存（08 §5.1.3）。依据 08 R11：具名 AI UA 被禁全文路径时，全文不自动取回，
    # 平台侧与用户侧相同。另一种读法见 §19 第 18 条。
defaults: {display_scope: {metadata: public_shared, abstract: by_rights, fulltext: per_user_only}}
commercial_gate: {noncommercial_only: false, requires_license: false}
storage_policy: {raw_payload_retention: P90D}
identifiers_emitted: [{scheme: doi, granularity: version}]
review: {verified_at: 2026-09-26, next_review_by: 2026-12-25, reviewer: "⚠ 待指派"}
v1: {adapter: null, status: design, disposition: none}   # v1 只有 adapters/informs.md 设计稿
```

**示例 B：`oai_pmh` 仓储实例**（DSpace 族；源文件与实例文件分离）

```yaml
# 设计伪代码 —— registry/instances/dspace/econstor.yaml（实例：平台知识 + 端点参数）
schema: instance/v2
instance_id: econstor
family: dspace                          # DSpace JSPUI（SS §2.2）
base_url: https://www.econstor.eu
oai:
  base_url: https://www.econstor.eu/oai/request      # SS [R55] Identify 实测
  metadata_prefixes: [oai_dc]
  granularity: seconds                               # SS 核验表 #47
  earliest_datestamp: 2009-01-28
  deleted_record: transient
  sets: {by: [subject, type]}
robots_snapshot: {host: www.econstor.eu, disallow: ["/discover", "/simple-search", "若干浏览路径"], fetched_at: 2026-09-26}
rate: {min_interval_s: 2}                            # 无书面值，取保守默认 ⚠
fingerprints: {robots_template: dspace_jspui}
verified_at: 2026-09-26
```

```yaml
# 设计伪代码 —— registry/sources/econstor.yaml
schema: sourcespec/v2
source_id: econstor
names: {full: "EconStor（ZBW）"}
layer: L2
kind: repository
roles: [fulltext, discipline]
disciplines: [econ_fin, business_mgmt]
directory: {status: v2-P1, priority: P1, survey_refs: ["SS §2.6", "SYN §3.4"]}
hosting: [{platform_family: dspace, instance_id: econstor}]
hosts: [{host: www.econstor.eu, role: oai}]
channels:
  metadata:
    method: oai_pmh
    connector: {family: oai_pmh, id: generic_oai, instance: econstor}
    endpoints: [{endpoint_id: econstor.oai}]
    auth: {kind: none}
    exec_side: platform
    robots: [{host: www.econstor.eu, paths_used: ["/oai/request"], verdict: allow}]
    tos_automation: unknown                   # ToS 未核验 ⚠ → on_demand 上限 + needs_confirmation，直到补读
    ai_bot_sensitivity: none
    license_policy: {record_license: unknown, abstract_rights_default: unknown}   # 元数据许可 ⚠
    display_scope_default: public_shared
    state: planned
  latest:
    method: oai_pmh
    connector: {family: oai_pmh, id: generic_oai, instance: econstor}
    exec_side: platform
    incremental: {cursor_kind: oai_datestamp, overlap: PT1H, schedule_class: continuous}
    state: planned
  fulltext:
    method: site_pages                        # OAI 记录中的 bitstream 链接，由实例规则解析
    connector: {family: platform_family, id: dspace, instance: econstor}
    exec_side: platform
    license_policy: {fulltext_policy: per_item, item_license_field: "oai_dc:rights"}   # 字段位置 ⚠
    display_scope_default: link_only          # 仅当单篇 license ∈ 白名单时升为 public_shared（CP HC-05）
    state: planned
commercial_gate: {noncommercial_only: false, requires_license: false}
identifiers_emitted: [{scheme: handle, granularity: version}, {scheme: doi, granularity: version}]
review: {verified_at: 2026-09-26, next_review_by: 2026-12-25}
v1: {adapter: null, status: none, disposition: none}
```

**示例 C：`official_tdm_api` 用户侧出版商**（元数据零代码，全文只在用户侧经官方 API 取回）

```yaml
# 设计伪代码 —— registry/sources/elsevier_sd.yaml
schema: sourcespec/v2
source_id: elsevier_sd
names: {full: "Elsevier ScienceDirect（含 Cell Press）", aliases: [ScienceDirect, "Cell Press"]}
aliases_of: [cell_press]
layer: L1
kind: publisher
disciplines: [math, physics_astro, chem_materials, life_med, psych, econ_fin, business_mgmt, cs_ai]
directory: {status: v2-P0, priority: P0, survey_refs: ["SYN §3.2.4", "SYN §3.4"]}
owner_org: {name: Elsevier, crossref_members: [78], doi_prefixes: ["10.1016"]}
hosts:
  - {host: api.crossref.org, role: api}
  - {host: api.elsevier.com, role: api}
  - {host: www.sciencedirect.com, role: site}
channels:
  metadata:
    method: crossref_delegated
    connector: {family: crossref_delegated, id: crossref}
    exec_side: platform
    license_policy: {record_license: facts, abstract_rights_default: unknown}
    # Crossref 摘要约为 0：2025 年 1,040,981 篇期刊文章中仅 424 篇带摘要（AG §2.2.1）→ 走 §8 补齐链
    fallbacks: [openalex.works_get, europe_pmc.search]
    state: active
  latest:
    method: crossref_delegated
    connector: {family: crossref_delegated, id: crossref}
    exec_side: platform
    incremental: {cursor_kind: created_date, overlap: P3D, backfill: {kind: index_date, schedule: weekly}}
    # published 日期常排到未来（在线先行加卷期日期，SS §2.8），新文判据用 created
    state: active
  fulltext:
    method: tdm_api
    connector: {family: official_tdm_api, id: elsevier_article_api}
    endpoints: [{endpoint_id: elsevier.article_retrieval, base_url: "https://api.elsevier.com/"}]   # 路径细节沿 v1 elsevier-sd.md
    auth: {kind: user_key}              # 每用户 API key（可加 insttoken）；平台不持有（CP HC-04）
    exec_side: user
    rate: {ceiling: {rps: 10}, quotas: {weekly_per_key: 50000}}   # TDM 专用 key 不限周配额（LS §0 第 7 条）
    robots:
      - {host: api.elsevier.com, paths_used: ["/content/article/"], verdict: absent}   # v1 勘察：API 主机无 robots
      - {host: www.sciencedirect.com, paths_used: [], verdict: disallow,               # `*` Disallow /；本通道不访问该主机，
         ai_ua: {named_blocked: [claude-code, ClaudeBot, "…"], scope: site}}          # 不参与本通道裁决（§3.3）
    tos_automation: api_only            # 挖掘必须经 API（CP §2.3.1）
    ai_bot_sensitivity: none            # 派生：只看 paths_used 非空的 api.elsevier.com
    tdm_policy_url: https://www.elsevier.com/about/policies-and-standards/text-and-data-mining
    tdmrep: {state: unreadable}         # v1 catalog 记有 TDMRep，具体取值 ⚠ 未核；按 §3.4 从严视同保留，
                                        # 只影响平台侧 TDM 与共享派生，用户本人 key 的 tdm_api 不受影响（08 R9）
    license_policy:
      fulltext_policy: per_item         # 订阅加混合 OA：Cell 2026 年 463 篇中 241 篇带即时 CC（LS §2.4.1）
      item_license_field: "crossref.license[content-version=vor]"
      derivation: {shared: forbidden, private_llm: needs_confirmation}   # CP HC-25、LQ-06
      output_limits: {snippet_max_chars: 200}                             # TDM 产出外发上限（CP §2.3.1）
    display_scope_default: per_user_only
    state: active
commercial_gate: {noncommercial_only: true, requires_license: false}   # Elsevier TDM 限非商业
identifiers_emitted: [{scheme: doi, granularity: version}, {scheme: pii, granularity: version}]
review: {verified_at: 2026-09-26, next_review_by: 2026-12-25}
v1: {adapter: elsevier_sd, status: implemented, disposition: user_side_only}
```

**示例 D：`oai_pmh` 预印本（arXiv，节选）**

```yaml
# 设计伪代码 —— registry/sources/arxiv.yaml（节选）
source_id: arxiv
layer: L1
kind: preprint
hosts:
  - {host: oaipmh.arxiv.org, role: oai}     # robots ⚠ 调研未核验，V0 注册前由 robots-first 闸实测
  - {host: export.arxiv.org, role: api}     # 全站 Disallow，只能经 API 访问（CS §2.1.1）→ Q4 冲突清单
  - {host: arxiv.org, role: site}           # Crawl-delay 15；允许 /abs /pdf /html；禁 /api /search /e-print /src
channels:
  metadata:
    method: oai_pmh
    connector: {family: oai_pmh, id: arxiv}  # 专用映射：metadataPrefix=arXiv（带逐篇 license）与 arXivRaw（版本史）
    rate: {ceiling: {min_interval_s: 3}, concurrency: 1, scope: all_machines}   # ToU：你控制的所有机器合计
    license_policy: {record_license: CC0, abstract_rights_default: open}        # 元数据含摘要为 CC0（CP HC-06）
  latest:
    method: oai_pmh
    incremental:
      cursor_kind: oai_datestamp            # 日粒度；datestamp 是最后修改时间
      overlap: P1D
      schedule_class: calendar
      calendar: {tz: America/New_York, announce: "Sun-Thu 20:00", oai_ready: "~22:30", holidays_ref: arxiv_2026}
  fulltext:
    method: site_pages
    exec_side: platform
    robots:
      - {host: arxiv.org, paths_used: ["/html/", "/pdf/"], verdict: allow_with_delay, crawl_delay_s: 15}
    license_policy: {fulltext_policy: per_item, item_license_field: "arXiv:license"}
    display_scope_default: link_only        # 只有单篇许可在 §11.9 白名单内的条目可升为 public_shared（CP HC-05、HC-06）
    # CP HC-06：非 CC 许可条目的 e-print（PDF、LaTeX 源、从中抽取的图与文本）平台不取、不存、不提供，
    # 只链接回 arXiv；`/e-print/`、`/src/` 永不出现在任何 RequestSpec 或配方中（§3.8 规则 12）
attribution: {text: "Thank you to arXiv for use of its open access interoperability.", required: true,
              no_endorsement: true}         # CS §3 第 6 条：致谢语，且不得暗示 arXiv 背书
v1: {adapter: arxiv, status: implemented, disposition: bridge_patch}
```

**VenueSpec v2 示例**：演化边、会议多键与 WP 系列。

```yaml
# 设计伪代码 —— registry/venues/cs_ai/ieee_taslp.yaml
schema: venuespec/v2
venue_id: ieee_taslp
kind: journal
curation: curated
names: {full: "IEEE Transactions on Audio, Speech and Language Processing", aliases: [TASLP]}
disciplines: [cs_ai]
keys:
  issn: [{value: "2998-4173", since: 2025}]
edges:
  - {type: renamed_to, from: ieee_acm_taslp, since: 2025,
     evidence: "CS §2.1.3：旧刊 2329-9290/2329-9304 最后一年为 2024；新刊 ISSN 2998-4173"}
hosting: [{source_id: ieee_xplore, since: 2025}]
routing: {metadata: crossref_delegated, latest: crossref_delegated, fulltext: link_only}   # CP HC-27
status: active
---
# 设计伪代码 —— registry/venues/cs_ai/neurips.yaml
schema: venuespec/v2
venue_id: neurips
kind: conference
curation: curated
keys:
  dblp_key: conf/nips
  openreview_prefix: "NeurIPS.cc/{year}/Conference"
  crossref: {prefix: "10.52202", split_by: container_title}   # Curran 前缀被多个会议共用（CS §3 第 3 条）
editions:
  derive_from: [dblp_drops, openreview_active_venues, neurips_proceedings]
  tracks: [conference, datasets_and_benchmarks, position_paper, creative_ai]   # 2025 新增两轨（CS §2.1.2）
edges:
  - {type: co_hosted_on, sources: [openreview, neurips_proceedings]}
freshness_ladder:                               # CS §2.6.5；Curran DOI 约晚 8 个月
  - {level: L0, channel: arxiv}
  - {level: L1, channel: openreview}
  - {level: L1, channel: neurips_proceedings}
  - {level: L2, channel: crossref_delegated}
  - {level: L3, channel: openalex}
routing: {fulltext: link_only}                  # 页面未声明开放许可 ⚠ → 不进共享缓存
---
# 设计伪代码 —— registry/venues/econ_fin/nber_wp.yaml
schema: venuespec/v2
venue_id: nber_wp
kind: wp_series
curation: curated
series:
  issuer: NBER
  numbering: {pattern: "w{n}", id_scheme: nber_w}
  doi: {prefix: "10.3386", ra: crossref}
  open_after_months: 18                         # 不利用软门（D-014；SS §0 第 2 条）
keys: {repec_series: "RePEc:nbr:nberwo"}
routing:
  metadata: [crossref_delegated, repec]         # Crossref 10.3386 摘要为 0 → 摘要走 RePEc 与 NBER RSS（SS §2.4）
  latest: [feed:nber_back_rss, crossref_delegated]   # back.nber.org Crawl-delay 10
  fulltext: link_only
```

### 3.7 从 v1 VenueSpec 迁移

v1 共有 62 个 VenueSpec（含 1 个 mock；D-037 全量核对）。迁移由确定性转换器完成，要求幂等，并做往返审计：每个 v1 字段要么映射到唯一的 v2 位置，要么以理由记为"已弃用"。

| v1 字段 | v2 去向 | 规则 |
|---|---|---|
| `id` | `venue_id` | 原样保留（v1 已是 snake_case）；文件从 `venues/<field>/` 移到 `registry/venues/<discipline>/` |
| `kind: journal` | `kind: journal` | — |
| `kind: conference` | `kind: conference` | `quirks.volume_map` → `editions.explicit`（aaai；econsoc 的 `te`、`qe` 期刊同样带 `volume_map`，一并转换） |
| `kind: preprint_channel` | arXiv 类目 → `preprint_category`（parent 为 `arxiv`）；`nber` → `wp_series`；`ssrn` → `preprint_server` | 按 `metadata_source` 判别 |
| `names` | `names` | 原样 |
| `field`（finance、econ、cs_ai、or_ms） | `disciplines` | finance、econ → `econ_fin`；or_ms → `business_mgmt`；cs_ai → `cs_ai` |
| `tier`（T1/T2/T3） | `labels.v1_tier` | 保留作参考；不再驱动优先级，优先级改由 Source 的 `directory.priority` 与用户兴趣决定 |
| `identifiers.issn` | `keys.issn[]` | 补 `type` 与 `since`，按 Crossref `/journals` 与 OpenAlex source 回填历代 ISSN；D-015 的"期刊必须有 ISSN"保留为策展期刊的 lint 规则 |
| `identifiers.dblp_key`、`openreview_id`、`openalex_source`、`crossref_prefix` | `keys.*` | 原样 |
| `metadata_source` | `routing.metadata` | `crossref` → `crossref_delegated`；平台 adapter → `v1_bridge:<adapter>` |
| `fulltext_source` | `routing.fulltext`，并落到对应 Source 的 fulltext 通道 | auth_gated adapter 对应的通道为 `exec_side: user`；平台部署默认 `link_only` 加用户侧配方 |
| `auth.level`、`provider_hint` | Source fulltext 通道的 `auth.kind` | `none` → `none`；`free_account` → `user_key` 或 `user_oauth`（依平台）；`subscription`、`institutional` → `user_session` 或 `user_key` |
| `rate_limit` | Source 通道的 `rate` | v2 取消 venue 级限速覆盖；令牌桶按 `(source, host, 请求类, 身份)` 计（P-04），出口 IP 维度见 §5.5 |
| `quirks` | 分拆：结构性参数 → `editions`、`keys`、`series`；合规事实 → Source 通道的合规字段与证据；增量参数 → `incremental`；adapter 私有参数 → `connector_params`（只对 v1_bridge 可见） | 逐键去向：`arxiv_set` 改为由类目自动推导（物理加 `physics:` 前缀），不再手写（[NS §2.3.5][NS]）；`ai_bot_sensitive`（AEA 系 9 刊）→ 对应主机的 `robots[].ai_ua` 加证据记录，**不得**落进 `connector_params`；`crossref_date_field: created`（ssrn）→ latest 通道的 `incremental.cursor_kind`；`topic_filter`（ssrn）→ 频道或 WatchKey 的过滤条件（04）；`fulltext_open_after_months`、`series_prefixes`（nber）→ `series.open_after_months`、`series.numbering`；`ojs_code`、`oai_base` → OAI 实例参数；`inception`（arXiv 类目）→ 回填起点；`cvf_edition_overrides`、`openreview_group_overrides`、`anthology_legacy_prefix` → `editions` 的逐届键；`doi_forms` → Mapper 参数；mock 专用键丢弃 |
| `status`（active、dormant、dead） | `status`（active、ceased、transformed）+ 演化边 | `dormant` → `active`（活跃度由探针判断）；`dead` → `ceased` |
| `notes` | `notes`；可核验的事实转为 `evidence` | 带日期的事实迁入证据记录 |

**迁移时须修补的已知漂移**（[CS §3][CS] 第 16 条、[NS §2.1][NS]）：
- arXiv 物理 set 前缀；
- NeurIPS 新增的两个 track；
- TASLP 换 ISSN；
- ECCV 全文源改为 ECVA；
- dblp 在线路径作废；
- OpenReview 限速改为按每次请求读响应头；
- PMLR 新卷发现改为"首页 diff 加卷号探测"。

### 3.8 注册表 lint 规则

1. 通过 JSON Schema 校验；拒绝未知字段（沿用 v1 `extra="forbid"`）。
2. `layer` 与 `kind` 相容；L2 源必须有 `roles`。
3. `hosts` 中每个主机都有 robots 条目，其 `fetched_at` 与 `review.verified_at` 相差不超过 90 天。注册表里的快照只是证据；运行时网关按 ≤24 小时刷新（§5.5）。
4. `exec_side=user` 当且仅当 `auth.kind` 是 `user_*`；`secret_ref` 只能引用 `deployment/*`。
5. `display_scope_default` 不得高于策略所允许的上限。例如订阅全文不得声明为 `public_shared`。
6. `directory.status` 为 P0 的源，其 metadata 与 latest 的 `fallbacks` 非空（NFRc-03.4）；且至少一条替补在当前策略下允许同一操作。latest 的替补须能跑 `INCREMENT`（background）；只允许 on_demand 的替补（如 `export.arxiv.org`）不计入。
7. 每个合规字段至少引用一条证据；`next_review_by` 与 `verified_at` 相差不超过 90 天。
8. 许可含 NC 时，`commercial_gate.noncommercial_only` 必须为 true。
9. 红线清单（盗版域名；Google Scholar 作为自动化来源）只能以 `excluded` 出现（CP HC-26）。
10. `directory.status` 与通道一致：
    - `metadata-only` 时，fulltext 的 method 只能是 `link_out` 或 `none`；
    - `link-only` 时，metadata 的 method 只能是 `link_out` 或 `none`；
    - `user-import-only` 时，三条通道均为 `none`，并声明导入映射器。
11. `v1.adapter` 非空时，必须是 v1 entry point 清单中的 id（20 个生产 adapter 加 mock）。
12. 专项红线（CP HC-06、HC-27）：
    - `ieee_xplore`、`acs`、`acm_dl` 的 fulltext 通道 method 只能是 `link_out` 或 `none`，且不得引用任何 FulltextRecipe；
    - 任何 RequestSpec 模板、`endpoints.path_templates` 与配方中，都不得出现 arxiv.org 的 `/e-print/`、`/src/` 路径。
13. 复核期错开：同一批导入的源，`next_review_by` 按 `source_id` 的哈希在 60–90 天内分散，避免上百个源在同一天集体超期、主干通道同时降级（§6.5）。

---

## 4. SCD：Source Capability Descriptor（③）

### 4.1 定义与边界

SourceChannel 回答"从哪里取、能不能取"，SCD 回答"这个端点能怎样查询、代价多少"。

- SCD 按**端点**声明。一个源可以有多个端点，例如 Crossref 有 `journal_works`、`works_query`、`works_doi`；OpenAlex 有 `works_list`、`works_search`、`works_semantic`、`works_get`、`group_by`。
  - Crossref 的 `works_query`（全局 `/works` 上的 filter 与 query，属 list 池）只服务交互道的 SEARCH，不用于后台收割与 venue 枚举（SI-02）。
- SCD 是 [04][04] 路由器与健全放宽的**唯一输入**（SI-22；[RT §12][RT] 第 2 条），同时供 harvest 规划器选择请求类与分页方式。
- 本文负责 SCD 的 schema 与静态取值，并产出动态统计；这些统计如何汇总成 `route_stat`、用于路由与调度，由 [04][04] 负责。

### 4.2 schema

```yaml
# 设计伪代码 —— SCD（每端点一份；静态部分由 SourceSpec 与 connector.describe() 生成）
scd_version: 1
endpoint_id: crossref.journal_works
source_id: crossref
serves: [ENUMERATE, INCREMENT]            # 可服务的操作（§5.2）；04 的意图映射到操作
id_lookup: []                              # 可解析的标识符方案，例如 [doi]；即能力 id.lookup.<scheme>
capabilities:                              # 能力键沿用 RT §3.5.1 与 04 §6、§7.7 的词表（完整清单见下方说明）
  filter.venue:          {support: native, fidelity: exact, bind: "path /journals/{issn}"}
  filter.date.created:   {support: native, fidelity: day, bind: "filter=from-created-date/until-created-date"}
  filter.date.published: {support: native, fidelity: day}
  filter.date.indexed:   {support: native, fidelity: day, note: "结果放大约 100 倍，只作补漏（AG §2.2.1）"}
  filter.type:           {support: native, fidelity: exact,
                          value_map: {journal-article: article, posted-content: preprint,
                                      proceedings-article: proceedings, report: wp}}   # 分面值对照（04 §7.7）
  filter.has_abstract:   {support: native}
  incr.since:            {support: native, via: filter.date.created}
  sort.recency:          {support: native, keys: [created, published, indexed, updated]}
  sort.cited_by:         {support: native, key: is-referenced-by-count}
  sort.relevance:        {support: none}   # 本端点不做相关性排序，放宽后结果有界（04 §7.2）
  kw.bool:               {support: none}
  kw.phrase:             {support: none}
  kw.field.*:            {support: none}
  filter.topic:          {support: none}   # 须由本地残差过滤
residual_trust: recheck                    # 残差信任策略，默认 recheck（04 §7.5、§7.7）
cursor: {kind: deep_cursor, ttl_s: 300, on_expire: restart_window}   # 5 分钟不用即过期（RT §3.4）；过期后从窗口起点重启（§5.4）
paging: {max_rows: 1000, max_offset: 10000}
cost:
  unit: request
  usd_per_call: 0
  request_class: single                    # 单条池（AG §0 第 1 条，LIVE 归类）
politeness:
  bucket_key: [source, host, request_class, identity, egress_ip]   # SI-37
  written_ceiling: {polite: {rps: 10, concurrency: 3}, public: {rps: 5, concurrency: 1}}
    # polite 数值来自 Crossref 公告与第三方观测，平台尚未用自己的联系邮箱实测 ⚠（AG §4 Q4）；限速器以响应头为准
  header_signals: [x-api-pool, x-rate-limit-limit, x-rate-limit-interval, x-concurrency-limit]
returns:
  fields: [doi, title, authors, container_title, issn, dates, type, license, reference, abstract?, relation, update_to]
  rights: {bibliographic: facts, abstract: publisher_copyright}
quirks: [issn_collision_possible, prefix_filter_matches_owner_prefix, comma_in_container_title_breaks_filter]
state: active                              # active / deprecated / suspended（探针可改写）
derived_from: {sourcespec_sha256: "…", connector_version: "…"}
verified_at: 2026-09-26
```

**能力支持等级**（04 的 `supports` 边沿用此口径）：
- `native`：语义与本地一致；
- `native_approx`：远端语义不同，例如词干化，须声明 `analyzer` 以对齐本地残差（[RT §3.5.3][RT]）；
- `emulated`：连接器通过多次请求实现，例如把超长 OR 拆成多个子请求再取并集；
- `none`：不支持。

**能力键词表**（本文定义，04 引用；按 04 §7.7 的要求细分了文本谓词）：
- 文本：`kw.bool`（`note` 写明否定的位置限制，例如"只支持 AND NOT"）、`kw.phrase`、`kw.near`、`kw.prefix`、`kw.wildcard`、`kw.field.{title, abstract, fulltext, all}`、`kw.field.section.*`（EPMC）；
- 语义与推荐：`sem.search`（如 OpenAlex 语义检索）、`rec.pos_neg`（如 S2 Recommendations 的正负例接口）；
- 过滤：`filter.date.{created, published, indexed, updated}`、`filter.venue`、`filter.topic[.<体系>]`、`filter.type`、`filter.oa`、`filter.license`、`filter.entity.*`、`filter.relation.*`；分面类能力可带 `value_map`；
- 其他：`id.lookup.<scheme>`、`incr.since`、`sort.{recency, relevance, cited_by}`、`rel.cites`（引文与被引）。

每个端点另声明 `residual_trust ∈ {recheck, trust_native}`，默认 `recheck`，即远端命中一律在本地做残差复核。

### 4.3 静态部分与动态部分

| 部分 | 内容 | 产生者 | 存放（表由 05 定义） |
|---|---|---|---|
| 静态 | 能力（可下推谓词）、排序、游标、分页、书面限额、单价、返回字段与权利 | SourceSpec 加 `connector.describe()` | 注册表快照 |
| 动态：健康 | 成功率 EWMA、p50/p95 延迟、429 与 5xx 计数、挑战计数、熔断状态 | PoliteHttp 网关 | `ops` 层健康表 |
| 动态：实测限额 | 响应头声明的限额与池名、实际页大小 | 网关 | 同上；与静态值不符时由漂移探针告警 |
| 动态：新鲜度 | 各源各 venue 与主题的滞后分布（发布日到首见日）、每个 WatchKey 的到达率样本 | harvest 与 identify 产出的 `first_seen_at` 等字段 | harvest 日志；由 04 汇总为 `route_stat` |

### 4.4 示例（节选）

```yaml
# 设计伪代码 —— openalex.works_list
endpoint_id: openalex.works_list
serves: [ENUMERATE, SEARCH, LOOKUP]
capabilities:
  filter.topic:            {support: native}          # domain / field / subfield / topic
  filter.venue:            {support: native, bind: "OpenAlex source id"}
  filter.date.published:   {support: native, note: "免费档只能按 publication_date 窗口；from_created/updated_date 需付费计划（AG §2.2.2）"}
  filter.oa:               {support: native}
  kw.field.title_abstract: {support: native_approx, bind: "search=", analyzer: stemmed, cost_override_usd: 0.001}
  filter.bool:             {and: native, or: {support: emulated, limit: "单个 filter 的 OR 值 ≤100，URL 约 4 KB"}, not: native}
paging: {max_per_page: 100, basic_paging_max: 10000, cursor: unlimited}   # RT §2.2
cost: {unit: usd, list: 0.0001, search: 0.001, group_by: 0.0001, singleton: 0}   # AG §2.2.2；RT §3.5.1
politeness: {hard_cap_rps: 100, budget: {free_key_usd_per_day: 1.0}, header_signals: [x-ratelimit-*, meta.cost_usd]}
---
# 设计伪代码 —— arxiv.oai_list_records
endpoint_id: arxiv.oai_list_records
serves: [INCREMENT, ENUMERATE]
capabilities:
  filter.topic.arxiv_category: {support: native, bind: "set=group:archive:category", note: "物理须加 physics: 前缀（NS §2.3.5）"}
  incr.since:                  {support: native, fidelity: day, bind: "from=", note: "datestamp 为最后修改时间"}
  kw.*:                        {support: none}
cursor: {kind: resumption_token}
politeness: {min_interval_s: 3, concurrency: 1, scope: all_machines,
             fake_success_patterns: ["Rate exceeded."]}   # CS §2.1.1
---
# 设计伪代码 —— europe_pmc.search
endpoint_id: europe_pmc.search
serves: [INCREMENT, ENUMERATE, SEARCH, LOOKUP]
capabilities:
  incr.since:                {support: native, bind: "FIRST_IDATE:[a TO b]"}
  kw.field.section.*:        {support: native}   # INTRO / METHODS / RESULTS / FIG / TABLE / DATA_AVAILABILITY…
  filter.entity.*:           {support: native}   # GENE_PROTEIN / DISEASE / CHEM / ORGANISM / GOTERM…
  filter.relation.*:         {support: native}   # HAS_PUBLISHED_VERSION / HAS_VERSION_EVALUATIONS…
  filter.license:            {support: native}
  kw.bool:                   {support: native}
cursor: {kind: cursor_mark}
paging: {max_page_size: 1000}
politeness: {min_interval_s: 10, note: "www.ebi.ac.uk 通用 UA Crawl-Delay 10；数值限额未公布 ⚠（AG §2.2.10）"}
cost: {usd_per_call: 0}
```

### 4.5 一致性保证

- **契约测试**（§15.2）：SCD 声明为 `native` 的能力，连接器生成的 RequestSpec 中必须出现对应参数；声明为 `none` 的能力永不下推。
- **放宽测试**：由 [04][04] 用属性测试保证"放宽后结果 ⊇ 原结果"（[RT §3.5.3][RT]）。本文提供每个端点的 SCD 与 fixture。
- **探针对账**（§6.5）：响应头与静态值不符时（例如 Crossref 池名或限额变化），SCD 的动态部分立即更新，并告警请人复核静态值。


---

## 5. Connector 与 ConnectorFamily（④）

### 5.1 分层与职责

| 层 | 形态 | 职责 |
|---|---|---|
| Connector | 代码，按族实现 | 声明请求（RequestSpec）、解析响应、规范化映射、给出 SCD、产出全文选项与探针 |
| ConnectorInstance | 数据（`registry/instances/**`） | 某平台族的具体实例：base URL、OAI 参数、robots 快照、速率、特例规则 |
| Mapper | 纯函数，按 `mapper_version` 版本化 | 把原始载荷映射为规范化记录（NormRecord，§10.6） |
| PoliteHttp | 共享网关，即 [02][02] 的 P13 Egress Gateway（独立服务、平台唯一公网出口，AD-01；中文名由 01 统一） | 执行 HTTP：robots-first 闸、令牌桶、重试预算、熔断、缓存与 singleflight、挑战检测、审计（§5.5） |

四条原则：
1. **连接器不直接发 HTTP**。它只产出 RequestSpec、接收 Response，由网关统一执行。这延续了 v1 "adapter 永不自己 sleep 或重试"的规定（[v1-02][v1-02] §3），并让 robots-first 成为结构性约束。
2. **平台侧连接器不持有任何用户凭证**。用户侧连接器只产出声明式配方（FulltextRecipe），由用户侧解释执行（§12）。
3. **解析与规范化是纯函数**，可用 fixture 回放测试（§15.1）。
4. **每个连接器都声明** `exec_side` 与 SCD。

### 5.2 通用协议

```python
# 设计伪代码 —— 连接器通用协议（非接口冻结；由首个里程碑的详设卡冻结）
class Operation(StrEnum):
    ENUMERATE = "enumerate"            # 回填：某 venue、前缀或集合在某窗口内的全部记录
    INCREMENT = "increment"            # 最新：按游标增量，由 WatchKey 驱动（04 编译）
    LOOKUP = "lookup"                  # 按标识符取记录（04 的联邦 LOOKUP）
    SEARCH = "search"                  # 远端检索，仅限 SCD 声明 native 或 emulated 的端点
    SNAPSHOT_IMPORT = "snapshot_import"
    LOCATE_FULLTEXT = "locate_fulltext"
    PROBE = "probe"

@dataclass(frozen=True)
class RequestSpec:                     # 连接器只"声明"请求，由 PoliteHttp 执行
    endpoint_id: str                   # 对应 SCD；决定令牌桶与请求类
    request_class: str                 # 例：Crossref 的 single / list
    method: Literal["GET", "HEAD", "POST"]
    url: str
    params: Mapping[str, str]
    headers: Mapping[str, str]         # 平台侧永不含用户凭证；部署级凭证由网关按 auth.kind 注入
    expect: Expectation                # content-type、最小字节数、空体判定、伪成功的正文特征
    idempotency_key: str

@dataclass(frozen=True)
class Page:
    records: list[RawRecord]           # (source_id, source_key, payload, fetched_at)
    next_cursor: Cursor | None
    signals: PageSignals               # 计数、空体、限流头、弃用头等，供漂移探针与 SCD 动态部分使用

class Connector(Protocol):
    connector_id: str
    family: ConnectorFamily
    exec_side: Literal["platform", "user"]
    def describe(self, spec: SourceSpec) -> list[SCD]: ...
    def plan(self, task: ConnectorTask) -> Generator[RequestSpec, Response, TaskOutcome]: ...
    def parse(self, endpoint_id: str, resp: Response) -> Page: ...        # 纯函数
    def normalize(self, raw: RawRecord) -> NormRecord: ...                  # 纯函数，带 mapper_version
    def locate_fulltext(self, v: VersionView, ctx: LocateCtx) -> list[FulltextOption]: ...
    def probes(self, spec: SourceSpec) -> list[ProbeSpec]: ...

def run(task: ConnectorTask, c: Connector, gw: PoliteHttp, policy: PolicyEngine,
        sink: HarvestSink) -> TaskOutcome:
    """平台侧执行器：由生成器驱动，HTTP 完全交给网关；每页数据与游标在同一事务落库。"""
    decision = policy.decide(task.source, task.channel, task.operation, task.ctx, now())
    if not decision.allowed:
        return TaskOutcome.denied(decision)              # 记审计，不发任何请求
    gen = c.plan(task)
    try:
        req = next(gen)
    except StopIteration as done:                        # 零网络任务（如 repec 的本地 join）
        return done.value
    while True:
        resp = gw.execute(req, decision)                 # robots-first → 令牌桶 → 请求 → 挑战、空体与伪成功检测；
                                                         # 网关每次执行前核对 decision.policy_version 仍是当前版本，否则拒绝
        if resp.terminal:                                # challenge / policy_denied / needs_confirmation / budget_exhausted
            gen.close()
            return TaskOutcome.stopped(resp.error_class, cursor=sink.last_committed(task))
        page = c.parse(req.endpoint_id, resp)            # 纯函数
        sink.commit_page(task, page)                     # 同一事务：source_record upsert + 游标推进（推进规则见 §10.3）
        try:
            req = gen.send(resp)
        except StopIteration as done:
            return done.value
```

### 5.3 九个族

| 族 | 适用 | 典型实例 | exec_side | 后台收割 | 需要写的代码 | 依据 |
|---|---|---|---|---|---|---|
| `aggregator_api` | 聚合器与学科库的文档化 API（快照与年度文件归 `bulk_snapshot`） | crossref（LOOKUP）、openalex、s2、europe_pmc、pubmed、inspire_hep、zbmath_open、nasa_ads_scix、opencitations、doaj、datacite、econbiz、pubtator3、icite | 多为 platform；ADS 为 user | 依策略 | 每源一个映射模块和预算模型 | SI-09；[AG §2.2][AG] |
| `oai_pmh` | 任何 OAI-PMH 2.0 端点 | arXiv、PMC、Numdam、zbMATH OAI、EconStor、Zenodo、DROPS/LIPIcs、AAAI OJS、TE/QE、CogSci（eScholarship）、PsychArchives、MDPI | platform | 是 | 族核心写一次（复用 v1 `adapters/_oai.py`）；实例零代码；arXiv、PMC 需少量专用映射 | [OSS §2.10.5][OSS] |
| `feed` | RSS、Atom、eTOC、CB-RSS | nature RSS、Science 与 PNAS 的 showFeed、APS feeds、Fed/ECB/BIS、JMLR、bioRxiv connect | platform | 是，但只用 robots 明确允许的 feed | 族核心写一次 | [NS §2.6][NS]、[LS §2.9][LS]、[SS §2.4][SS] |
| `crossref_delegated` | 在 Crossref（或 DataCite）登记 DOI 的期刊、WP、预印本前缀、论文集 | 绝大多数出版商期刊；SSRN、NBER、ChemRxiv、PsyArXiv、bioRxiv 的元数据 | platform | 是 | 引擎写一次（移植 v1 crossref）；venue 零代码 | SI-01/02/03 |
| `bulk_snapshot` | 官方快照、年度文件与批量 dump 的导入（简报 R2-11 新增） | OpenAlex 季度快照、Crossref 年度公共数据文件、PubMed baseline（NCBI 书面确认后，R2-13）、DROPS dblp 月度快照、RePEc ReDIF、ORCID/DataCite 年度文件、ROR dump、PwC 存档（一次性） | platform | 是（按快照发布周期；bulk 主机 robots 另判，08 R6） | 每源一个导入器（流式下载、断点续传、子集过滤）；族核心写一次 | SI-15；[AG §2.3][AG] |
| `platform_family` | 出版托管平台与仓储软件 | Atypon、Silverchair、HighWire、OJS、DSpace、EPrints、InvenioRDM | 托管族为 user；仓储族与 OJS 为 platform | 托管族：否；仓储族：是 | 每族一个模块；实例零代码 | SI-10；[SS §2.2][SS] |
| `official_tdm_api` | 按用户 key 的全文与 TDM API | Elsevier Article Retrieval、Wiley TDM、Springer Nature Full-text/TDM、APS Harvest 全量（用户授权） | user | 否 | 每源一份配方与限额声明 | CP §2.3.1 |
| `site_special` | 有官方 API 或官方结构化页面的专站；OA 论文集静态页（PMLR、CVF、NeurIPS、JMLR、IJCAI 等）须 robots 允许、结构稳定、无挑战门，受 P-05 与漂移探针约束，"免费阅读但未声明开放许可"的全文不进共享缓存（简报 R2-12） | OpenReview（平台侧共享收割待书面确认，R2-20）、PMLR、CVF、NeurIPS proceedings、ACL Anthology、JMLR、IJCAI、APS Harvest（OA 集）、SCOAP3、PLOS、eLife、World Bank D&R、ASSA 程序、HF Papers | platform | 依策略 | 每站一个模块 | SI-09；[CS §2.2][CS]；R2-12 |
| `v1_bridge` | v1 的 20 个生产 adapter | 见 §14.1 | platform，或用户侧的 pc_agent | 依策略 | 垫片写一次；逐个 adapter 的去向见 §14.1 | 简报 B-03 |

### 5.4 各族的专有接口

```python
# 设计伪代码 —— 各族在通用协议之上的专有部分

class AggregatorApi(Connector):
    def batch_lookup(self, ids: list[Identifier]) -> Iterator[RequestSpec]: ...
        # 按 SCD 的批量上限：S2 /paper/batch ≤500 个 id；OpenAlex 单个 filter 的 OR 值 ≤100
    def query(self, q: PushdownQuery) -> Iterator[RequestSpec]: ...
        # q 已由 04 按 SCD 做过健全放宽
    budget: BudgetModel      # 美元（OpenAlex）/ 每 key RPS（S2）/ 每 IP 配额（OpenCitations）

class BulkSnapshot(Connector):                         # 简报 R2-11 新增的族；快照导入不再挂在 AggregatorApi 下
    def snapshot(self) -> SnapshotSpec: ...
        # OpenAlex S3 季度快照、Crossref 年度文件、PubMed baseline（NCBI 确认后）、DROPS dblp、OpenCitations dump 等
    def subset_filter(self, union: InterestUnionView) -> SubsetFilter: ...
        # 按兴趣并集（§10.5）只导入子集；经 Egress 的流式模式下载，断点续传，不进 TTL 缓存（02 §2.3.7）
    host_robots_required: bool = True                  # bulk 主机自己的 robots 也要判定（08 R6）

@dataclass
class OaiInstance:
    base_url: str
    metadata_prefix: str                               # oai_dc / arXiv / arXivRaw / pmc / oai_agris
    sets: list[str]
    granularity: Literal["day", "seconds"]
    deleted_record: Literal["no", "transient", "persistent"]
    earliest_datestamp: date
    token_ttl_s: int | None                            # Zenodo 约 2 分钟，须即取即续（AG §2.2.16）

class OaiPmh(Connector):
    def list_records(self, inst: OaiInstance, set_: str | None,
                     frm: str, until: str | None) -> Generator[RequestSpec, Response, TaskOutcome]: ...
        # resumptionToken 立即续取。OAI-PMH 不保证按 datestamp 排序返回，因此 token 过期时以本次运行的
        # 起始 from 重启整段列表，重复由 (source_id, source_key) 去重吸收；只有实例声明
        # ordered_by_datestamp=true（经 fixture 验证）时，才可从最后落库的 datestamp 续起。
        # 本次运行的 until 在首个请求时固定（取 responseDate 或当前时间）；持久游标只在整段列表完成后推进到它（§10.3）

class Feed(Connector):
    formats = ("rss1.0_rdf", "rss2.0", "atom", "prism", "cb_rss")
    role: Literal["signal", "metadata"]
        # 多数 feed 只作 signal：触发补全，不展示 feed 内容（APS 的 RSS 声明"Personal use only"；08 R15）。
        # 例外：ECB（DOI 由欧盟出版局 RA 登记，不在 Crossref）、BIS（CB-RSS）、JMLR（无 DOI）的 feed 是元数据主通道，
        # NBER back RSS 补 Crossref 10.3386 缺失的摘要（SS §2.4、§3 第 1 条；CS §2.1.2）。Fed 以 Crossref 10.17016
        # 为主（摘要 99%），RSS 只作新鲜度信号。例外按源登记（简报 R2-17 已采纳，08 R15 随之增列例外）
    def diff(self, prev_guids: set[str], page: Page) -> list[RawRecord]: ...   # 沿用 v1 IdSetDiff 语义

class CrossrefDelegation(Connector):
    registry: Literal["crossref", "datacite"] = "crossref"
        # DataCite 变体用于 LIPIcs、arXiv DOI、dblp 快照 DOI（CS §2.4）
    def enumerate_venue(self, v: VenueView, window: DateWindow) -> Generator[...]: ...
        # 期刊：对 ISSN 集合逐个请求 /journals/{issn}/works（single 池），按 DOI 合并
        # 前缀型（WP、预印本）：/prefixes/{p}/works 加 type 过滤；或 /members/{m}/works
        # 论文集：/prefixes/{p}/works?filter=container-title:{精确标题}（single 池）；
        #   标题含逗号时 filter 报 pair-list-form-invalid（CS §2.1.4），改为在同一前缀或 member 端点上
        #   按时间窗枚举，再在本地按 container-title 拆分；不用全局 /works 的 filter 或 query（SI-02）
    def increment(self, key: WatchKeyView, cursor: Cursor) -> Generator[...]: ...
        # from-created-date = cursor − overlap，sort=created&order=asc（游标单调推进的前提，§10.3）
        # 每周补漏：from-index-date = 上周起点，并叠加 from-created-date ≥ now − L（L 为最大可见滞后，
        #   初值 30 天 ⚠ 待实测），只捞"创建较早、上周才可见"的记录，避免 index-date 约百倍的放大；
        #   L 之外的迟到记录由季度快照对账兜底。按标识符去重
        # deep cursor 5 分钟不用即过期（RT §3.4）：过期后从当前窗口起点重启，重复由去重吸收；
        #   窗口按月切分，使一个窗口能在令牌桶排队下连续取完
    post_filters = ("split_by_container_title",        # IJCAI 与 KR 共用前缀；Curran 前缀多会共用
                    "drop_components_and_chapters",    # IMF
                    "owner_vs_string_prefix_check")    # bioRxiv 10.1101 与 10.64898

class PlatformFamily(Protocol):
    family_id: Literal["atypon", "silverchair", "highwire", "ojs", "dspace", "eprints", "invenio_rdm"]
    background_allowed: bool
        # 出版托管族（atypon、silverchair、highwire）为 False；仓储族与 OJS 为 True，但仍逐实例过策略
    def fingerprint(self, obs: HostObservation) -> float: ...
        # 依据 robots 模板、响应头、路径特征识别平台；探针用它发现平台迁移（NS §2.5）
    def oai_defaults(self, inst: Instance) -> OaiInstance | None: ...
        # DSpace /server/oai/request；EPrints /cgi/oai2；InvenioRDM /oai2d；OJS /index.php/<journal>/oai（OSS §2.10.5）
    def fulltext_recipe(self, inst: Instance, v: VersionView) -> FulltextRecipe | None: ...
        # 用户侧：DOI → 落地页 → PDF 的规则
    def feed_rule(self, inst: Instance) -> FeedRule | None: ...
        # 例：Atypon 的 /action/showFeed 只在 robots 明确 Allow 的实例启用（SIAM、Science、PNAS）

class OfficialTdmApi(Connector):
    exec_side = "user"
    def recipe(self, v: VersionView) -> FulltextRecipe: ...
        # 端点模板加头部占位符，例如 {user_secret:elsevier.api_key}；占位符只在用户侧解析
    def entitlement_recipe(self, v: VersionView) -> FulltextRecipe | None: ...
    per_user_limits: RateSpec
        # 例：Wiley 每秒 3 篇且每 10 分钟 60 次；SN 直接下载 1/s、TDM API 150/分（CP §2.3.1）
    request_identity: IdentityRule | None
        # 例：SN 要求 TDM 请求的 UA 含 "TextDataMining"（NS §0 第 5 条），因此 SN 配方由 pc-agent 执行
        #（浏览器扩展不能改写 UA）；执行器只追加标记，不伪装其他客户端

class SiteSpecial(Connector):
    structure_contract: StructureContract
        # 所依赖的字段、选择器或 JSON 路径，加四类 fixture（§15.1）
        # 只为有官方 API 或官方结构化页面、且 robots 允许的站点实现（SI-09）

class V1Bridge(Connector):
    def __init__(self, adapter: SourceAdapter, v1_venues: list[VenueSpecV1],
                 mode: Literal["platform", "pc_agent"]): ...
    # discover_timeline + enumerate_issue → ENUMERATE / INCREMENT，产出 RawRecord(payload=PaperStub)
    # resolve_assets / fetch_asset → 只在 pc_agent 模式（用户侧、单篇、显式触发）运行。platform 模式一律
    #   不调用 fetch_asset，open_access 族（arxiv、cvf、pmlr、aaai_ojs、acl_anthology 等）也不例外：
    #   共享 OA 全文只经 §11.9 的许可白名单路径取得；v1 的 browser-fetch 横切件（aea、ssrn、wiley、
    #   oup_silverchair 使用）在 platform 模式下禁用（D-030 的浏览器取回只在用户侧）
    # v1 HttpClient 换成指向 Egress Gateway 的垫片（02 §6.2 的 EgressClient；PoliteHttp 是网关内部库）——v1 adapter 本来就经注入的 HttpClient 发请求
    # adapter.default_rate → 网关令牌桶声明；v1 capabilities → SCD 的 serves
```

### 5.5 PoliteHttp 的合规闸与审计

PoliteHttp 是 02 P13 Egress Gateway（出站网关）内部使用的客户端库（简报 R2-08）：连接器与探针只向网关提交请求，网关是平台侧唯一的对外出口，出口隔离由网络结构强制（02 AD-01、INV-03）。稳定性算法（令牌桶、AIMD、重试预算、熔断、舱壁）由 [04][04] 定义。本文只规定连接器侧契约和两道合规闸。

- **robots-first 闸**：
  - 每个 RequestSpec 执行前，先确认 `(host, path)` 的 robots 判定是新鲜的。缓存上限 24 小时：RFC 9309 §2.4 规定缓存副本不宜使用超过 24 小时（robots.txt 不可达时除外；一手来源，2026-09-27 读取）。v1 的"缓存 7 天"（[v1-03][v1-03] §3）不再沿用。缓存过期后先刷新 robots，再发业务请求；P0 主机另由探针每日刷新。
  - 解析采用 RFC 9309 语义与最长匹配（D-026），实现可用 protego（BSD-3，[OSS §2.10.5][OSS]）。状态码按 §3.4 映射。
  - 判定为 `disallow` 或 `unreadable` 的路径，平台侧请求一律拒绝，并记一条 `policy_denied` 审计。**唯一例外**：AccessDecision 带 `robots_basis`，且取值为 `api_conflict`（08 R5：运营方文档邀请程序化使用的专用 API 主机，模式 ≤ on_demand、按文档限速）或 `written_confirmation`（有效的 PolicyOverride 放宽了该主机该路径的 robots 冲突）。这类请求逐条记审计，带 `robots_exception_ref`，指向 §6.8 冲突清单或覆盖记录。`api_conflict` 类例外只放行按需请求，后台批量一律拒绝（08 HC-31、R6）；`written_confirmation` 类按确认登记的 `granted_mode` 与 `bulk_allowed` 放行，可以包含后台收割（§6.4；与 05 §3.4 ①② 的约束一致）。
  - 抓取 robots.txt 本身也受挑战检测约束：robots.txt 被挑战时记为 `unreadable`，不重试。
- **诚实身份**：
  - 平台侧统一 UA：`PaperCrawler/<ver> (+<部署方说明页>; mailto:<部署方联系邮箱>)`（D-014；CP HC-10）。
  - 联系邮箱由部署方配置，不硬编码（[NS §3][NS] 第 7 条）。
  - 上游拒绝时不更换 UA。
- **挑战检测**：
  - 复用 v1 ChallengeDetector 的特征库：`cf-mitigated: challenge`、Akamai 403、Imperva、Radware 302、ALTCHA、Anubis、reCAPTCHA（[v1-11][v1-11] §5；D-030）。
  - 命中即归为 `challenge` 错误类，主机冷却 24 小时（键为 URL host，D-030 E-1），不重试、不求解（CP HC-26）。
- **伪成功与空体检测**：按 `expect` 判定。
  - arXiv 返回"HTTP 200 + 正文 `Rate exceeded.`"时按 429 处理（[CS §2.1.1][CS]）；
  - bioRxiv `/details` 返回 200 空体时按端点故障处理（[LS §2.2.1][LS]）。
- **响应头上交**：限流头、池名、美元额度头交给限速器与 SCD 的动态部分。v1 的 `HttpClient.get_bytes` 不暴露响应头、只能静态限速，这是 v2 必须修复的缺口（[AG §3][AG] 第 5 条）。
- **令牌桶**：桶键为五元组 `(source, host, 上游请求类, 凭证, 出口 IP)`（简报 R2-08）；出口 IP 维度只收紧、不叠加：按 IP 计额的上游按 IP 设子桶，各子桶之和仍受全局桶约束（SI-37，见 §19 第 4 条）。其余机制由 [04][04] 定义（[RT §9][RT]）：
  - AIMD，以书面限额为上限；
  - 重试预算：每请求 ≤3 次，窗口内重试占比 ≤10%；
  - 按"源 × 端点"熔断；
  - 三道舱壁：交互、收割、enrich；
  - 同键在途请求合并（singleflight）与应用层缓存（04 §13.7–§13.8；CP §2.4 调度原则 2）；
  - 不对同一第三方主机发对冲请求。
- **审计**：每个请求都写入 `ops` 层的取回日志，带 `policy_decision_id`（CP HC-28）。元数据请求也记录，这扩大了 v1 FetchLog 只记资产取回的口径（[v1-05][v1-05] §7）。

### 5.6 可复用开源与排除清单（R5；许可过 B-06）

以 [SYN §4.4][SYN] 与 [OSS][OSS] 的 R/I/B/X 分级为底，只列与本文相关的项。第三方客户端一律锁版本，并配 §15.2 的契约测试。

| 分级 | 组件（许可） | 在本文的用途 | 依据 |
|---|---|---|---|
| 复用 | protego（BSD-3） | robots-first 闸的解析（§5.5） | [OSS §2.10.5][OSS] |
| 复用 | procrastinate（MIT） | 流水线各段的 PG 原生队列（简报 B-05） | [SYN §4.4][SYN] |
| 复用 | splink（MIT） | 弱信号候审的概率打分（§9.4） | [RT §7.1][RT] |
| 复用 | openreview-py（MIT） | `site_special/openreview` 的官方客户端 | [OSS][OSS] 客户端表 |
| 复用 | `acl-anthology` 包（构建代码 Apache-2.0；数据 2016 年起 CC BY 4.0，更早为 CC BY-NC-SA 3.0） | ACL Anthology 的元数据底座，免抓站 | [CS §2.1.2][CS]；[OSS][OSS] |
| 复用 | pubmed_parser（MIT）、metapub（Apache-2.0） | PMC OA XML 与 MEDLINE 解析；E-utilities 的按需补查（受 §6.8 门控） | [OSS][OSS] |
| 复用 | GROBID 与 grobid-client-python（均为 Apache-2.0）、pypdf（BSD-3，v1 依赖） | 共享 OA 全文与用户侧全文的抽取（§11.9、§12.7） | [SYN §4.4][SYN]；[v1-12][v1-12] |
| 复用 | MiniCheck-FT5（MIT）、HHEM-2.1-Open（Apache-2.0） | TL;DR 的 NLI 闸（§11.4） | [PU §2.7][PU] |
| 集成（默认关闭） | Zotero translation-server（AGPL-3.0） | 只作独立进程、改用诚实 UA、用户触发时调用；不进核心链路（B-06） | [OSS][OSS] §6.2 |
| 集成（待核） | biblio-glutton（README 声明 Apache-2.0，⚠ 未经 API 识别） | 参考串到 DOI 的匹配，可作 §9.4 的候选召回补充 | [OSS][OSS] |
| 借鉴 | sickle（BSD 风格，已停更） | OAI 客户端写法；v1 `adapters/_oai.py` 已覆盖，不引入依赖 | [OSS][OSS] |
| 借鉴 | arxiv-at-home（Apache-2.0） | 行锁保证索引恰好一次、标题模糊匹配加权（§9.3 并发、§9.4） | [SYN §4.4][SYN] |
| 借鉴 | paper-search-mcp（MIT，整体） | 多源能力矩阵的组织方式（对应 SCD，§4） | [OSS][OSS] |
| 排除 | PyPaperBot、SciDownl、Sci-Hub-MCP-Server 与各项目中的 Sci-Hub 组件 | 盗版源（CP HC-26 红线） | [SYN §4.4][SYN] |
| 排除 | scholarly 等 Google Scholar 自动化组件 | 红线（CP HC-26） | [SYN §4.4][SYN] |
| 排除 | paper-search-mcp 的"Mozilla UA 升级重试"、findpapers 的 `web_scraping`（curl_cffi 冒充 Chrome TLS 指纹） | UA 或指纹伪装（CP HC-10） | [SYN §4.4][SYN] |
| 排除 | science-parse、CERMINE（停更）；Nougat（停更，且权重非商用） | 抽取器选型 | [SYN §4.4][SYN] |

pyzotero（Blue Oak Model License 1.0.0）属于 06 的冷启动导入，不在本文范围；该许可不在 B-06 点名的 Apache/MIT/BSD/PostgreSQL 之内，引入前须经许可 ADR 裁定。

---

## 6. 策略引擎与漂移探针（⑤）

### 6.1 输入

| 类别 | 内容 | 取自 |
|---|---|---|
| S1 文档化 API | 通道是否由官方文档邀请程序化使用：`invites`、`allows_with_platform_key`、`requires_user_key`、`personal_use_only`、`no_api`、`deprecated`、`withdrawn` | 通道证据 |
| S2 bulk 通道 | `official_open`、`official_restricted`（申请制、付费、requester-pays、禁再分发）、`license_required`、`none` | 通道证据 |
| S3 robots | 逐主机、逐路径的判定（§3.4） | 通道 `robots[]` 与网关缓存 |
| S4 ToS 自动化条款 | `tos_automation`（§3.4） | 通道证据 |
| S5 TDM 与 AI 保留 | `tdmrep`、`content_signal`、逐主机的 `robots[].ai_ua`（派生出 `ai_bot_sensitivity`） | 通道证据与探针 |
| 结构性上限 | exec_side 与 auth.kind、商用门控、许可门控、证据时效、漂移状态、挑战冷却、红线 | SourceSpec、部署配置、`ops` 层状态 |

### 6.2 模式全序与上限表

模式全序为 `deny(0) < link_only(1) < user_side(2) < on_demand(3) < background(4)`：
- `background`：平台定时收割；
- `on_demand`：平台只在用户查询或补查时低频调用，受书面限额约束；
- `user_side`：平台不自动化，只由用户本人的客户端在显式操作时执行；
- `link_only`：只给出外链；
- `deny`：完全不接触。

每上升一级，平台参与程度就更深，所以取最小值等价于"最严者为准"（P-05）。

**与 08 的对应**：判定规则以 [08][08] §4.2 的 R1–R16 为准，下表在对应行标注 R 号。08 的 `Verdict` 与本文 AccessMode 的对应如下：
- `ALLOW`、`ALLOW_THROTTLED` ↔ background（后者带最小间隔）；
- `ON_DEMAND_ONLY` ↔ on_demand；
- 08 的 `USER_SIDE` 请求类 ↔ user_side；
- `METADATA_VIA_THIRD_PARTY` ↔ 该站各通道 link_only，元数据改经 `crossref_delegated` 等注册机构取得；
- `LINK_ONLY` ↔ link_only；`FORBIDDEN` ↔ deny。

08 HC-31（needs_confirmation 通道不跑后台批量）在本文表现为：凡带 needs_confirmation 的上限都 ≤ on_demand。

**五类信号给出的上限**（只对本通道实际访问的主机判定，即 `paths_used` 非空者，§3.3；平台侧请求与用户侧的自动请求 `user_fetch`、`tdm_api` 都按此表判定，08 R16、HC-29）：

| 信号 | 取值 | 上限 | 备注与例 |
|---|---|---|---|
| S1 | `invites`、`allows_with_platform_key` | background | Crossref、OpenAlex、INSPIRE |
| S1 | `requires_user_key`、`personal_use_only` | user_side | SN API 的摘要只许个人使用（CP §2.2.1）；ADS 每用户 token |
| S1 | `no_api`（通道是结构化页面或 feed） | background（中性） | 结合 S3、S4 判定 |
| S1 | `deprecated` | on_demand | OpenAlex `/text`（[RT §3.5.2][RT]） |
| S1 | `withdrawn` | deny | PMC OA Web Service，2026-08-25 退役（[LS §2.3.2][LS]） |
| S2 | `official_open` | background（优先选用） | OpenAlex S3、DROPS、PMC S3 |
| S2 | `official_restricted` | on_demand（首拉须人工启动） | bioRxiv S3 "不作为再分发来源"，只可做内部 TDM（[LS §2.2.1][LS]） |
| S2 | `license_required` 且无许可 | link_only，并标 needs_confirmation | CORE 新版 dump、NBER 周更元数据文件 |
| S3 | `allow`、`absent`、`not_applicable` | background | 08 R1、R4 |
| S3 | `allow_with_delay(N)` | background，请求间隔 ≥ max(N, 书面限额, 名录保守值) | EBI 10 s（08 R13） |
| S3 | `disallow`、`unreadable`（站点主机，或没有文档化 API 邀请的主机） | link_only | 08 R2、R3：平台与用户侧执行器的自动请求都禁止（HC-29、R16），只剩用户在场的导航（在出版社打开）。robots ADR 若采纳另一种读法，用户侧单篇可放宽为 user_side（§19 第 9 条） |
| S3 | `disallow`，且该主机是 S1 为 `invites` 或 `allows_with_platform_key` 的专用 API 主机 | on_demand，并标 needs_confirmation；决定带 `robots_basis=api_conflict` | 08 R5；简报 Q4 的默认（§6.8）。网关只放行这类按需请求（§5.5） |
| S3 | `disallow`，且该主机是 bulk 主机 | link_only，并标 needs_confirmation | 08 R6：bulk 没有"按需"形态，书面确认前不导入（ftp.ncbi、ftp.ebi） |
| S4 | `allowed`、`silent` | background | — |
| S4 | `api_only` | API 与 bulk 通道 background；站点通道 user_side | Elsevier、APS |
| S4 | `user_initiated_only` | user_side | INFORMS ⚠ |
| S4 | `forbidden` | link_only | 08 R8：不向该站发任何取数请求，元数据经第三方；SSRN |
| S4 | `contract_required` | link_only，并标 needs_confirmation | IOP |
| S4 | `unknown` | on_demand，并标 needs_confirmation | AOM、Emerald |
| S5 | 无保留 | 不设上限 | — |
| S5 | `tdmrep=reservation_1` 或 `unreadable`；政策页有明示的 TDM 保留 | 该站全文通道平台侧上限 user_side；用户本人 TDM 许可的 `tdm_api` 可行；该站内容的 TDM/AI 用途与共享派生 deny | 08 R9；Springer Nature |
| S5 | `content_signal.search=no` | 该站内容不进共享检索索引 | 08 R10 |
| S5 | `content_signal.ai_input=no` | 该站内容不作 LLM 输入，也不作共享嵌入的输入 | 08 R10；映射待 LQ-17 |
| S5 | 具名 AI-UA 封禁（`*` 组放行；站点级或覆盖全文路径的路径级） | 元数据按 `*` 组取；该主机全文的自动取回（平台侧，及用户侧 `user_fetch`）link_only，只留 `open_in_tab`；内容不作 LLM 输入 | 08 R11；INFORMS（全文路径）、nature.com、cell.com、CEPR。另一种读法见 §19 第 18 条 |

S5 各行只约束该站自身内容（全文、站点摘要），不约束经 Crossref 等注册机构取得的书目事实。运营方另有 robots 允许的机器通道时，只走该通道（08 R7，如 dblp → DROPS 快照，Zenodo → OAI），由 `fallbacks` 与路由表达。

**结构性上限**：

| 条件 | 上限 |
|---|---|
| `exec_side=user`，或 `auth.kind ∈ user_*` | user_side（P-03） |
| `platform.commercial=true` 且 `noncommercial_only` | 元数据 deny；全文只留外链（link_only）（CP HC-23） |
| `requires_license` 且无 `license_on_file` | link_only，并标 needs_confirmation |
| 当前时间晚于 `review.next_review_by`（证据复核逾期） | 漂移探针持续为绿、证据其余字段完整时记 `review_overdue`，宽限 30 天、维持原模式；宽限结束或任一探针告警，上限 on_demand 并标 needs_confirmation（简报 R2-16；08 §4.4；⚠ 设计判断，V0 复核） |
| 合规类漂移告警未关闭 | 按探针类型定（§6.5） |
| 该主机 24 小时内出现过挑战 | 该主机的平台操作 link_only（冷却期内；08 R12，不可覆盖） |
| 红线（盗版源、CAPTCHA 求解、Google Scholar 自动化） | deny，不可覆盖（CP HC-26） |

**各操作所需的最低模式**：

| 操作 | 最低模式 |
|---|---|
| `INCREMENT`、`ENUMERATE`、`SNAPSHOT_IMPORT` | background |
| `LOOKUP`、`SEARCH`（用户查询触发的联邦） | on_demand |
| `PROBE` | on_demand。robots.txt 本身总是可以抓取；ToS 页与 `tdmrep.json` 受 robots 约束。对 S4 为 `forbidden` 的主机（08 R8），探针只取 robots.txt，条款复核改由人工 |
| `LOCATE_FULLTEXT` 的平台侧共享 OA 取得（§11.9） | background；T2 按需取时为 on_demand |
| `LOCATE_FULLTEXT` 的用户侧配方 | user_side |
| 展示外链 | link_only |

### 6.3 判定函数

```python
# 设计伪代码 —— 策略引擎（逐通道、逐操作；规则口径以 08 §4.2 的 R1–R16 为准，本函数是其实现）
ORDER = {"deny": 0, "link_only": 1, "user_side": 2, "on_demand": 3, "background": 4}
RELAXABLE = {"S1", "S2", "S3"}        # 08 §4.4 纪律 2：书面确认只放宽文档化 API、bulk、robots 三类冲突

def decide(src: SourceSpec, ch: SourceChannel, op: Operation,
           ctx: DeployCtx, now: datetime) -> AccessDecision:
    if redline(src):                                                 # CP HC-26：不可覆盖
        return AccessDecision.deny("redline", policy_version=PV)
    used = [r for r in ch.robots if r.paths_used]                    # 只评估本通道实际访问的主机（§3.3）
    signal_caps: list[Cap] = [
        cap_api_doc(ch.api_doc),                                     # S1
        cap_bulk(ch),                                                # S2
        *[cap_robots(r, ch.api_doc, src.host_role(r.host)) for r in used],     # S3（08 R1–R7、R13、R14）
        cap_tos(ch.tos_automation, ch.method),                       # S4（08 R8）
        *[cap_tdm_ai(r.ai_ua, ch.tdmrep, ch.content_signal, ch.name) for r in used],  # S5（08 R9–R11）
    ]
    struct_caps: list[Cap] = [                                       # 结构性上限：任何覆盖记录都放宽不了
        cap_exec_side(ch.exec_side, ch.auth.kind),
        cap_commercial(src.commercial_gate, ctx.commercial),
        cap_license(src.commercial_gate),                            # requires_license 且无 license_on_file
        cap_evidence(src.review, ch.evidence, now),
        cap_drift(probe_state(src.source_id, ch.name)),
        cap_cooldown(cooldowns([r.host for r in used], now)),        # 挑战冷却（08 R12）
    ]
    ov = active_override(src.source_id, ch.name, now)                # 08 §4.4 的确认登记；过期或 robots/ToS 哈希漂移即失效
    if ov and ov.applies_to(op):
        if ov.kind == "relax":                                       # confirmed_scoped：只抬升它明确覆盖的 S1–S3 上限
            signal_caps = [c.raised_to(ov.mode, basis=ov.id) if c.signal in RELAXABLE and ov.covers(c) else c
                           for c in signal_caps]
        else:                                                        # denied / conditional：书面答复只收紧
            struct_caps.append(ov.as_cap())
    caps = signal_caps + struct_caps
    mode = min((c.mode for c in caps), key=ORDER.get)                # 覆盖后仍对全部上限取最小，所以越不过 S4、S5 与结构性上限
    binding = [c for c in caps if c.mode == mode]
    return AccessDecision(
        mode=mode,
        allowed=ORDER[mode] >= ORDER[required_mode(op)],
        min_interval_s=max_interval(ch, used),        # robots Crawl-delay、书面限额与名录保守值中最慢者（08 R13）
        display_scope=ch.display_scope_default,       # 通道级上限；单篇许可与权利门在展示闸再收紧（§3.5）
        robots_basis=robots_basis(binding, ov),       # none / api_conflict（08 R5）/ written_confirmation；网关据此放行（§5.5）
        needs_confirmation=any(c.needs_confirmation for c in caps),   # 被覆盖抬升的上限不再带此标记
        reasons=[c.reason for c in binding],
        inputs_sha256=digest(src, ch, ctx, ov),
        policy_version=PV)
```

判定函数须满足三条性质：
1. **单调**：任一信号变严，模式不会变松（取最小值的直接推论）。收紧型覆盖记录只会增加上限，同样单调。
2. **覆盖有界**：放宽型覆盖记录只能抬升它明确覆盖的 S1–S3 上限；抬升后仍对全部上限取最小值，所以永远越不过 S4（ToS 禁令）、S5（TDM/AI 保留）、挑战冷却、exec_side、商用与许可门控、证据时效和红线（08 §4.4 纪律 2）。
3. **可复现**：同样的输入哈希（含覆盖记录）与策略版本，必得同样的决定。

§15.3 用属性测试验证这三条。

### 6.4 needs_confirmation 流程与 PolicyOverride

流程与确认登记的逻辑字段以 [08][08] §4.4 为准，本文只规定它们怎样进入判定函数。状态机（与 08 §4.4 同构）：

```text
unassessed ──判定为 R5/R6 或条款不清──► needs_confirmation ──发函──► awaiting_reply
                                                                    │ 30、60 天两次提醒；90 天无回复记 no_reply
                                                                    │（仍按 on_demand；沉默不等于同意）
                    ┌───────────────────────────────────────────────┤
                    ▼                                               ▼
     confirmed_scoped → PolicyOverride(kind=relax)       denied → PolicyOverride(kind=restrict)
                    │
                    └─ 到期（≤12 个月），或该源 robots/ToS 哈希漂移 ─► 24 小时内回到 needs_confirmation（立即收紧）
```

- **PolicyOverride** 字段：`{override_id, source_id, channel, kind: relax | restrict, relaxes ⊆ {api_doc, bulk, robots}, ops_allowed, mode, scope{hosts, paths, rate_ceiling, concurrency, bulk_allowed}, evidence{type: written_reply | contract | adr_entry, ref, received_at}, decided_by, decided_at, expires_at（≤12 个月）, adr_ref}`。`kind=relax` 只能抬升 `relaxes` 列出的冲突（§6.3）；ToS 禁令、TDM/AI 保留与挑战停止永远不在可放宽之列（08 §4.4 纪律 2）。`rate_ceiling` 只是上限，仍受响应头驱动的 AIMD 约束（纪律 3）。
- `tos_automation=unknown` 与 `contract_required` 不靠覆盖记录解决：取得书面答复或合同后，更新 SourceSpec 的 `tos_automation` 与证据，走注册表 PR。
- 每条获批的覆盖记录，都在简报 §7-2 的 robots ADR 例外附表中逐站登记（ADR 由 09 起草），满足 v1 AC-0.5"记录例外需 ADR"。在覆盖生效之前，按 Q4 默认运行。
- 书面确认函的模板要点与待发函对象清单见 [08][08] §4.5、§4.6。§6.8 是其中与本文通道相关的子集。
- 运维界面有上游治理面板，显示配额、成本、429 与挑战计数、robots、Content-Signal、TDMRep 状态与条款哈希（CP DI-06）。面板的形态由 02、07 定义。

### 6.5 漂移探针（SI-12）

| 探针 | 对象 | 频率（默认） | 判定 | 自动动作 | 依据 |
|---|---|---|---|---|---|
| `robots_hash` | `hosts` 中的每个主机 | P0 主机每日；其余每周（网关的业务请求另按 ≤24 小时刷新，§5.5） | 哈希变化后，重新解析 `paths_used` 的判定 | 判定变严：该通道降级或暂停并告警；判定变松：只告警，不自动升级。该源的有效覆盖记录一律失效，24 小时内回到 needs_confirmation（08 §4.4 纪律 4） | [SYN §1.5][SYN]；dblp 在 2026-07 至 09 之间由 Crawl-delay 改为全禁（[RT §12][RT] 第 31 条） |
| `tos_hash` | `tos_url`、API 条款页 | 每周 | 哈希变化 | 开工单并标 needs_confirmation。通道有有效覆盖记录时，覆盖立即失效（同上）；没有覆盖记录时，给 7 天宽限期保持现模式，期满仍未复核则上限降为 on_demand（§19 第 5 条） | CP RK-02；[SS §3][SS] 第 14 条 |
| `tdm_signals` | `/.well-known/tdmrep.json`、robots 中的 Content-Signal、AI-UA 条目 | 每周 | 新出现保留或禁止 | 按 §6.2 的 S5 行收紧：TDM 保留 → 全文通道平台侧上限 user_side；`search=no`、`ai-input=no` → 退出共享索引或 LLM 输入；具名 AI-UA 封禁 → 全文自动取回 link_only；共享派生一律 deny | CP HC-11(b)；08 R9–R11 |
| `challenge_rate` | 网关遥测 | 持续 | 平台请求出现任何挑战 | 主机冷却 24 小时；7 天挑战率超过阈值时通道降级 | D-030 |
| `quota_headers` | 响应头与 SCD 对比 | 持续 | 声明的池名或限额变化 | 更新 SCD 动态部分；限额变低时告警 | [AG §0][AG] 第 1 条（Crossref 分池） |
| `ownership` | 每个策展 venue 在 Crossref 中最新 N 条 DOI | 每周 | member、owner prefix、publisher、`resource.primary.URL` 域名、平台指纹任一变化 | 生成 HostingPeriod 或演化边的变更提案，进 venue 候审；暂停该 venue 的全文配方 | [NS §3][NS] 第 9 条（IHÉS、ChemRxiv、RSC、APS DOI 形态）；[LS §3][LS] 第 11 条 |
| `empty_or_drop` | 各端点的 canary 查询 | 每日 | 200 空体；计数较基线骤降（例：prefix owner 变更导致 `prefix:10.1101` 查询归零） | 端点降级，切换替补链（bioRxiv 改用 Crossref `member:54368` 或 EPMC） | [LS §2.2.1][LS] |
| `deprecation` | 弃用公告页（OpenAlex deprecations、DataCite GraphQL 等） | 每周 | 哈希变化，或到了已知退役日期 | SCD 端点状态改为 deprecated 并告警 | [AG §4][AG] Q13 |
| `anon_access` | 已知的匿名可读端点，例如 OpenReview `active_venues` | 每周 | 变为 401 或 403 | 改写 SCD；告警 | [CS §4][CS] 第 12 条 |

探针本身也走 PoliteHttp，遵守 robots-first 与限速。对 robots.txt 就被挑战的主机（ACS、AMS、Cambridge 等），探针只记 `unreadable` 并停止，不重试。

**证据时效的自动续期**：187 行种子的证据几乎都核验于 2026-09-26。若只靠人工复核，它们会在同一天超过 90 天，主干通道（Crossref、arXiv、EPMC）的后台收割随之同时降为 on_demand（§6.2 结构性上限），违背 P-09。对策有三条：
1. 可由探针机器复测的证据（robots 快照、`tdmrep.json`、Content-Signal、ToS 与 API 条款页的哈希、配额响应头），复测结果与原证据一致时，自动把该证据的 `verified_at` 更新为复测时间，记 `grade=LIVE, by=probe`。
2. 只能由人判断的证据（条款语义、许可条款、书面确认），仍须人工复核；到期前 14 天在治理面板提醒（01 FR-82）。
3. 首次导入时，`next_review_by` 按 §3.8 规则 13 错开。

三条都不改变"证据超期即进入降级流程"这条规则本身（[SYN §3.5][SYN] 第 2 条）；简报 R2-16 在其上加了 `review_overdue` 的 30 天宽限（§6.2 结构性上限），宽限只在探针持续为绿、证据其余字段完整时成立。

### 6.6 自动降级语义

1. **按通道、按操作降级，只降不升**，分档按简报 R2-15：robots 与 TDM 信号漂移立即降级；ToS 哈希变化给 7 天宽限（有覆盖记录的通道覆盖立即失效，§6.5）；元数据通道自身受影响时暂停并切换替补链（下一条）。恢复须人工处理：关闭告警、重核证据、必要时发出 PolicyOverride。
2. **全文通道**降为 `link_only`。**元数据与最新论文通道**标为 `suspended`，路由器与调度器按 SCD 状态改走 `fallbacks`；没有替补时该能力降级，界面标注"该来源暂停更新"，文案由 07 定义（P-09）。
3. **venue 归属漂移**：暂停该 venue 的全文配方；元数据继续经 Crossref 取得；归属变更提案进入 venue 候审。
4. 降级事件写入 `ops` 层并推送告警，告警渠道由 02 定义；每周汇总进上游治理报告。

### 6.7 决策记录与审计

- **策略决定快照**：`(decision_id, source_id, channel, op, mode, robots_basis, override_id?, reasons, inputs_sha256, policy_version, decided_at)`。只在输入变化时生成新快照，不是每个请求一条。
- **取回日志**：记录请求级事实（时间、主机、路径、状态、字节数、耗时、限速等待），引用 `decision_id`。
- **留存期**：取回日志与决定快照至少保留 6 个月；影响评估类记录至少 3 年（CP HC-14）。具体矩阵由 [08][08] 定义。

### 6.8 冲突与待确认清单（初版）

本表是 [08][08] §4.6 待发函清单中与本文通道相关的子集，两处不一致时以 08 为准。标 on_demand 的行由网关按 `robots_basis=api_conflict` 放行（§5.5）；bulk 主机的行不做任何导入（08 R6）。

| 主机或通道 | 冲突 | 默认模式 | 替代通道 | 依据 |
|---|---|---|---|---|
| `eutils.ncbi.nlm.nih.gov`（PubMed E-utilities） | robots `Disallow: /`（注释为后端服务器）；NCBI 文档邀请程序化使用 | NCBI 书面确认（并在 robots ADR 附表登记）之前不调用；确认后 on_demand（单个 PMID 补查）。`pubmed` 在名录中保持 v2-P0 并标 ⚑ROBOTS（简报 R2-13；04 §20 第 3 项的从严读法） | EPMC REST `SRC:MED`；OpenAlex 按 PMID 单查（04 §8.4） | [LS §2.3.1][LS]、[AG §2.2.11][AG] |
| `ftp.ncbi.nlm.nih.gov`（PubMed baseline 与 updatefiles） | robots `Disallow: /`；NLM 文档邀请批量下载 | 暂不导入，needs_confirmation | EPMC REST；PMC S3 | [AG §2.2.11][AG] 核验补充 |
| `ftp.ebi.ac.uk`（EPMC bulk） | robots `Disallow: /` | 暂不导入 | EPMC REST（间隔 ≥10 s） | [AG §2.2.10][AG] |
| `pub.orcid.org`（ORCID Public API） | robots `Disallow: /` | on_demand（用户授权读取本人记录），needs_confirmation；商用时停用 | 年度 CC0 数据文件；用户手动导出 | [AG §2.2.13][AG] |
| `api.osf.io`（OSF API） | robots `Disallow: /` | 书面确认前不调用（08 §4.6 第 5 行，比 R5 允许的 on_demand 更严）；needs_confirmation | Crossref 前缀 10.31234 等（COS 名下 23 个前缀） | [AG §2.2.17][AG]、[LS §2.2.3][LS] |
| `api.elifesciences.org`（eLife API） | robots `Disallow: /` | on_demand，needs_confirmation | Crossref（摘要 99%）、RSS、GitHub `elife-article-xml` | [LS §2.4.5][LS] |
| `api.archives-ouvertes.fr`（HAL） | robots 禁 `/search/` 与 `/oai/`；`hal.science` 的 robots 注释鼓励使用 API | on_demand，needs_confirmation | OpenAlex | [AG §2.2.18][AG] |
| `zenodo.org` | robots 禁 `/api`（放行 `/api/records/*/files`），`/oai2d` 未禁 | OAI 取 background；REST 不用 | OAI-PMH | [AG §2.2.16][AG] |
| `export.arxiv.org`（arXiv Query API） | 全站 Disallow，只能经 API 访问 | on_demand（只作 OAI 的替补），needs_confirmation | OAI（`oaipmh.arxiv.org`，robots ⚠ 待实测） | [CS §2.1.1][CS]；简报 §7-2 |
| `pubchem.ncbi.nlm.nih.gov`（PUG-REST） | robots 禁 `/rest/pug/` | 暂不接入（P2） | — | [NS §2.3.2][NS] |
| `cir.nii.ac.jp`（CiNii OpenSearch） | robots 禁 `/opensearch`，放行 `/resourcesync/` | OpenSearch 不用 | ResourceSync | [AG §2.2.29][AG] |
| `eprint.iacr.org`（IACR ePrint） | `*` 为 `Disallow: /`，但 robots 注释声明 OAI、RSS、ATOM 为元数据通道 | on_demand，needs_confirmation | dblp 快照 | [CS §2.1.1][CS] |
| `data.nber.org`（NBER 周更元数据） | 非浏览器 UA 返回 403，页面说明有合理需要可联系 | 不访问；needs_confirmation（申请授权） | RePEc bulk | [SS §2.1][SS] |
| `api2.openreview.net`（OpenReview） | robots 宽松，但 API 需账号，ToS 规定一人一号 | 平台服务账号 needs_confirmation（简报 §7-12）；书面确认前平台侧共享收割停用，用户本人 token 只在用户侧供本人查询（HC-04）；V0 即发函（简报 R2-20）；`active_venues` 可匿名读 | ICLR、TMLR、COLM 等由 arXiv 版本 + DROPS dblp 快照 + 外链到 OpenReview forum 兜底；OpenAlex | [CS §2.1.2][CS] |


---

## 7. 各学科接入计划（⑥）

### 7.0 阅读说明

- **状态与优先级的权威**是 [catalog/source-directory][DIR]，底稿为 [SYN §3.2][SYN] 的合并名录（187 行）。本节只列计划层信息：主干通道、优先级、所属族、需新写的 connector、v1 adapter 去向、缺口。不复制整表。
- **族缩写**：
  - AGG = `aggregator_api`；OAI = `oai_pmh`；FEED = `feed`；XREF = `crossref_delegated`；
  - PF = `platform_family`；TDM = `official_tdm_api`；SITE = `site_special`；V1B = `v1_bridge`；BULK = `bulk_snapshot`（简报 R2-11）。
- **学科范围**（简报 R2-25）：社科按用户点名的经济、金融、商业、管理覆盖（§7.4、§7.5）；社会学、政治学、教育学不在 v2.0 范围，列入补充调研缺口，接入时走同一机制（多数经 XREF 零代码）。
- **"新写"的范围**：只列有官方 API 或协议通道、需要写代码的 connector（SI-09）。经 XREF 零代码接入的期刊不列。
- **全文的默认处理**：出版商的订阅全文一律在用户侧执行（TDM 或 PF 配方），或只给外链。下文不再逐条重复。

### 7.1 数理化（数学、物理/天文、化学/材料，附地学）

| 项 | 数学 | 物理/天文 | 化学/材料 |
|---|---|---|---|
| 主干通道 | Crossref（ISSN 集合；理科 115 刊全部可枚举）；arXiv OAI `math:math:*`（32 类）；zbMATH Open（REST 与 OAI，MSC 分类） | arXiv OAI `physics:*`（51 个叶子类，须带前缀）；Crossref；INSPIRE（HEP）；APS Harvest（OA 集） | Crossref（ACS、RSC、Wiley、Elsevier；化学/材料的摘要覆盖中位数 11%）；ChemRxiv（Crossref 前缀 10.26434，版本 DOI 形如 `/vN`，摘要约 98%）；arXiv `physics.chem-ph`、`cond-mat.mtrl-sci` |
| P0 | arxiv、zbmath_open、elsevier_sd、wiley、springer_link、oup_academic | arxiv、inspire_hep、aps、iop（metadata-only）、elsevier_sd、wiley、springer_link、nature_portfolio、oup_academic | chemrxiv、acs（metadata-only）、elsevier_sd、wiley、springer_link、nature_portfolio |
| P1 | ams、siam、ems_press、msp、project_euclid、centre_mersenne_numdam、cambridge_core、tandf_online、royal_society、mdpi；degruyter_brill（metadata-only） | nasa_ads_scix（用户 token）、scoap3_repo、aip、optica、edp_sciences、scipost、royal_society、cambridge_core | rsc（Silverchair 迁移完成后重勘）、mdpi |
| P2 及以下 | intl_press、episciences、eudml；annals_math（metadata-only）；mathscinet（link-only） | quantum_journal、pos_sissa、osti_gov、optica_open、wulixb；world_scientific、spie_dl（metadata-only） | ccs_chemistry、osti_gov、pubchem（只作关联，needs_confirmation）；cas_scifinder（link-only） |
| 族 | XREF（期刊）；OAI（arXiv、Numdam、zbMATH OAI）；AGG（zbMATH REST） | OAI（arXiv）；AGG（INSPIRE、ADS、OSTI）；SITE（APS Harvest、SCOAP3）；XREF（期刊、论文集系列）；FEED（APS feeds 与 nature RSS 只作信号） | XREF；OAI（arXiv；MDPI OAI 不稳定） |
| 新写 | zbmath_open；arXiv 数学类目 VenueSpec 生成器；numdam 只是 OAI 实例，零代码 | inspire_hep、aps_harvest、scoap3、nasa_ads_scix（exec_side=user）、osti_gov（P2） | 无（全部经 XREF）；pubchem 待 robots ADR（P2） |
| v1 去向 | arxiv：包装加修补（v1 只登记了 math.OC）；crossref：移植 | arxiv：修补物理 set 推导 | — |
| 缺口与注意 | MSP、IMS、Duke、Annals 的 Crossref 摘要约为 0，改用 arXiv → zbMATH 补齐；MSC2020 为 CC BY-NC-SA，不作 TopicNode 默认叶子，作可选插件、任何部署默认不加载，数学子树用 arXiv math 分类 + OpenAlex topics（简报 R2-22；zbMATH 记录上的 MSC 码只作记录标签保存，插件开启时才挂到 TSRG）；AMS 的"5 年墙"只有二手证据 ⚠，OpenAlex 也识别不出，不自动判为 OA（[NS §2.3.3][NS]） | IOP 的 robots 对 `*` 全禁，2026-07 起机器访问须签协议，因此只取元数据；PRL、PRB 摘要覆盖低，走 Harvest → arXiv → OpenAlex；SCOAP3 对 PRL、PRD 只资助 HEP 分类文章，须逐篇读许可；AIP 的 S2O 试点已于 2025 年底结束；PhySH 为 CC0；ADS 向 SciX 切换的日期 ⚠（[NS §0][NS]、[NS §2.3.1][NS]） | 化学缺少开放的细粒度分类，冷启动靠 OpenAlex subfield 加嵌入；**地学与材料**（Wiley/AGU、ESSOAr、EarthArXiv、GeoScienceWorld、OSTI、ADS）首批只经 Crossref 前缀与 ISSN 接入，待补充调研（G-05） |

### 7.2 生命科学/医学

| 项 | 内容 |
|---|---|
| 主干通道 | Europe PMC REST（`FIRST_IDATE`；覆盖 MED 与 PPR；请求间隔 ≥10 s）；Crossref；PMC（S3 加 OAI）。PubMed 的 E-utilities 与 baseline 待 NCBI 书面确认（并在 robots ADR 附表登记）后启用，此前由 EPMC 的 `SRC:MED`、PMC 允许的通道与 Crossref 承担（简报 R2-13；§6.8、§19 第 1 条）。bioRxiv、medRxiv 以 Crossref 为首选、原生 API 为补充 |
| P0 | europe_pmc、pubmed（v2-P0，⚑ROBOTS：NCBI 书面确认前不调用，确认后启用，R2-13）、pmc、biorxiv、medrxiv、arxiv（q-bio 10 类）、pnas（全文经 PMC，不接触出版商）、elsevier_sd（含 Cell Press）、wiley、springer_link、nature_portfolio、oup_academic |
| P1 | plos、elife、frontiers、mdpi、sfn_journals、research_square、preprints_org、royal_society、annual_reviews、aaas_science（Science Advances 全文经 PMC）、pubtator3、icite |
| P2 及以下 | cshl_press、peerj、authorea、f1000_platforms、psb_proceedings；ssrn 生医通道只取元数据（EPMC 对 SSRN 的收录停在 2023-10-28） |
| 族 | AGG（EPMC、PubMed、PubTator3、iCite）；OAI 加 bulk（PMC）；XREF（bioRxiv 与 medRxiv 经 `member:54368`；各刊）；SITE（PLOS API 与 allofplos、eLife XML；bioRxiv API 只作替补）；FEED（Cell `current.rss`、Nature RSS、eLife、PLOS、Frontiers，只作信号） |
| 新写 | europe_pmc；pubmed（含 bulk，受 ADR 门控）；pmc（OAI 映射 `pmc` 加 S3 每日 inventory 对账）；plos（API 限 10 次/分钟，另有 allofplos bulk）；elife（GitHub XML bulk；API 待确认）；pubtator3、icite（限速与许可 ⚠，核验后启用） |
| v1 去向 | v1 没有生命科学专用 adapter；elsevier_sd、wiley、oup_silverchair 转为只在用户侧运行 |
| 缺口与注意 | PMC 只允许 S3、OAI-PMH、E-utilities、BioC 四条自动化通道；按单篇 `license_code` 门控；删除不发通知，须用每日 inventory 对账（[LS §2.3.2][LS]）。bioRxiv 许可 6 选 1，约 19% 为 no-reuse；其 S3 桶不得作为再分发来源；`/details` 返回 200 空体（[LS §2.2.1][LS]）。MeSH 作主题叶子，须标明年度版本并致谢 NLM。质量信号：eLife Assessment、EPMC `HAS_VERSION_EVALUATIONS`、PMC `is_retracted`。NIH 2024 公共获取政策使作者手稿（`license_code=TDM`）比例上升，默认按私有 TDM 加跳转处理（[LS §4][LS] Q11） |

### 7.3 心理学

| 项 | 内容 |
|---|---|
| 主干通道 | Crossref（心理学 Crossref 摘要覆盖中位数 0%，21 刊中 13 刊低于 5%，[AG §2.6][AG]）；PsyArXiv（Crossref 前缀 10.31234）；EPMC 与 PubMed 只部分覆盖 |
| P0 | psyarxiv、medrxiv（心理、神经学科）、europe_pmc、pubmed、elsevier_sd、wiley、springer_link、nature_portfolio（Nature Human Behaviour）、oup_academic |
| P1 | sage_journals、cogsci_proceedings、osf_preprints、annual_reviews、frontiers、cambridge_core、tandf_online、royal_society |
| P2 及以下 | psycharchives、ucpress_online；hogrefe（metadata-only P2）；apa_psycnet（metadata-only P2）；PsycInfo 只接受用户导出后导入 |
| 族 | XREF；OAI（CogSci 经 eScholarship `set=cognitivesciencesociety`；PsychArchives）；AGG（EPMC） |
| 新写 | 无，只有 OAI 实例；PsyArXiv 以 Crossref 为首选（简报 R2-13），OSF API 只作补充且待书面确认 |
| v1 去向 | — |
| 缺口与注意 | APA 的摘要与参考文献覆盖都是 0。补齐顺序：PubMed → PsyArXiv 版本（约 30% 带 `is-preprint-of`）→ OpenAlex → 用户导入（私有）（[LS §3][LS] 第 15 条）。心理学期刊的共享 TL;DR 受 LQ-05 阻塞，卡片采用"元数据 + 受控标签 + 私有速读"模板（[PU §2.9][PU]；模板由 07 定义）。心理学会议（Psychonomics、SPSP、CCN）未核验（G-05）。分类用 MeSH F 分支与 Cognitive Atlas；后者为 CC BY-SA 3.0 US，映射表单独存放并标注 SA。APA Thesaurus 不嵌入 |

### 7.4 经济/金融

| 项 | 内容 |
|---|---|
| 主干通道 | Crossref（107 个 ISSN 中 106 个可枚举；经济摘要覆盖中位数 85%，金融 76%）；SSRN（Crossref 10.2139，按 created，91.2% 带摘要）；RePEc bulk（JEL，以及 WP 与发表版的关联）；WP 原生通道；arXiv econ 与 q-fin |
| P0 | crossref、ssrn（metadata-only P0）、nber_wp、repec、aea_journals、econsoc_journals、informs_pubsonline、elsevier_sd、wiley、oup_academic、springer_link、arxiv（econ 3 类、q-fin 9 类） |
| P1 | fed_board_wp、ecb_wp、bis_wp、imf_wp、worldbank_prwp、iza_dp、econstor、econbiz、assa_meetings、nber_conferences、socarxiv、cambridge_core、tandf_online、uchicago_journals、annual_reviews |
| P2 及以下 | cesifo_wp、other_cb_wp、fraser、pm_research、efa_meeting、sed_meetings；cepr_dp、mpra、hbs_wp、jstor、wfa_meeting（metadata-only）；sfs_cavalcade（只作会议标签）；econlit（excluded，只作 JEL 参考） |
| 族 | XREF（期刊、SSRN、NBER、Fed、IMF）；FEED（ECB、BIS CB-RSS、Fed、NBER back RSS）；AGG（RePEc bulk、EconBiz）；OAI（EconStor）；SITE（World Bank D&R API、ASSA 程序、NBER 会议议程） |
| 新写 | `cb_rss` 解析器（FEED 族内）、worldbank_dr、assa_program（产出 `presented_at` 事件与 JEL）、econbiz；econstor 只是 OAI 实例；repec 沿用 |
| v1 去向 | nber：包装；ssrn：包装，删除浏览器全文模式；aea：包装；econsoc：移植；repec：包装；arxiv 的 econ 与 q-fin：包装加修补；elsevier_sd、wiley、oup_silverchair：只在用户侧 |
| 名录 | UTD24、经济学 Top 5、金融 Top 3 内置；FT50、AJG、ABDC、VHB 只作用户私有导入（许可限制，[SS §2.7][SS]） |
| 缺口与注意 | NBER 的 18 个月规则不利用软门；NBER 周更元数据须申请授权。Econometrica 是混合 OA，按单篇 license 判定（[SS §0][SS] 第 3 条）。IMF 须过滤 component 与 chapter；ECB 只能走 RSS。WP 与发表版的证据优先级为 RePEc/NBER > Crossref relation > 模糊匹配（[SS §3][SS] 第 5 条） |

### 7.5 商业/管理

| 项 | 内容 |
|---|---|
| 主干通道 | Crossref；UTD24 的 24 刊中有 21 刊在 Atypon 或 Silverchair（[SS §0][SS] 第 5 条） |
| P0 | informs_pubsonline、aom_journals、elsevier_sd、wiley、springer_link、oup_academic |
| P1 | sage_journals、aaa_pubs、misq、cambridge_core、tandf_online、uchicago_journals、socarxiv、osf_preprints |
| P2 及以下 | aom_proceedings、ais_icis；emerald_insight、mit_smr（metadata-only P2）；hbp_hbr（excluded，ISSN 在 Crossref 不存在）；informs_annual（excluded） |
| 族 | XREF；PF（atypon、silverchair 实例，供用户侧全文使用；Atypon 实例多因具名 AI-UA 禁令只能"在出版社打开"，§12.3） |
| 新写 | 无，零代码；平台族 atypon、silverchair 的模块跨学科共用 |
| v1 去向 | v1 没有已实现的 adapter（informs、uchicago、sage 只有设计或登记） |
| 缺口与注意 | AOM、UChicago 的摘要为 0：先取 OpenAlex（有滞后），再取 SSRN 版本。INFORMS 与 AOM 几乎没有 hybrid OA，可读全文主要靠用户订阅或作者自存版（[SS §2.8][SS]）。Wiley 于 2026-06 收购 Emerald，平台去向待观察 ⚠。Project MUSE、SMF、UW Press 上有调研 venue 但未勘察，本轮不增名录行，列入补充调研缺口（简报 R2-26）。AIS eLibrary 的 bepress 默认 OAI 路径 `/do/oai/` 落在 robots 禁区 `Disallow: /do/`（端点本身 ⚠ 未实测，[SS §2.2][SS]） |

### 7.6 CS/AI

| 项 | 内容 |
|---|---|
| 主干通道 | arXiv OAI（40 个 cs 类目 set）；OpenReview（书面确认前平台侧共享收割停用，ICLR、TMLR、COLM 等由 arXiv 版本 + DROPS dblp 快照 + 外链兜底，简报 R2-20）；会议平台（PMLR、CVF、ACL Anthology、NeurIPS、AAAI OJS、IJCAI、JMLR）；Crossref（ACM、IEEE、Springer LNCS、AAAI、IJCAI、ACL、NDSS、PVLDB）；DataCite（LIPIcs、arXiv DOI）；DROPS dblp 快照；HF Papers（信号）。按新鲜度阶梯 L0–L3 路由（[CS §2.6.5][CS]） |
| P0 | arxiv、openreview、pmlr、cvf_open_access、neurips_proceedings、acl_anthology、aaai_ojs、ijcai_proceedings、jmlr、tmlr、dblp（快照形态）、hf_papers、crossref、openalex（受预算约束） |
| P1 | usenix、ndss、pvldb、isca_archive、lipics_drops、ecva、techrxiv、jair、iospress_faia、ieee_xplore（元数据加用户会话）、springer_link、elsevier_sd、s2、unpaywall、pwc_archive、datacite；iacr_eprint（metadata-only，needs_confirmation）；mit_press_direct、acm_dl（metadata-only） |
| P2 及以下 | rss_proceedings、mlsys_proceedings、ceur_ws、alphaxiv（只做用户自连）、eccc、siam_epubs、aamas_ifaamas、hal；now_publishers（metadata-only）；excluded：会议官网 miniconf 数据、scirate、paper_copilot、google_scholar |
| 族 | OAI（arXiv、AAAI OJS、LIPIcs/DROPS）；SITE（OpenReview、PMLR、CVF、NeurIPS、Anthology、JMLR、USENIX、ECVA、HF）；BULK（DROPS dblp、PwC 存档）；XREF（ACM、IEEE、LNCS、IJCAI、NDSS、PVLDB、ISCA、ECAI；LIPIcs 用 DataCite 变体） |
| 新写 | openreview（v2；平台服务账号待书面确认，V0 即发函）、dblp_drops（BULK 快照导入）、hf_papers（信号）、pwc_archive（BULK 一次性导入）、jmlr（RSS 加 citation meta）、usenix（P1）、ecva（P1；许可 ⚠，因此 link_only）；ijcai 走 XREF，站点 PDF 只外链 |
| v1 去向 | openreview：包装，personal 部署沿用用户 token；pmlr：包装加修补；cvf：包装；neurips_proceedings：包装加修补；acl_anthology：移植为包形态；aaai_ojs：移植为 OJS 实例并扩展；arxiv：包装加修补；dblp：在线路径废止；s2、openalex、unpaywall 见 §14.1 |
| 名录标签 | CCF 第七版（2026-03-31）；ICORE2026（许可 ⚠）；CSRankings（CC BY-NC-ND，只记成员资格事实）；ccfddl（MIT，提供会期与 DBLP key）（[CS §2.5][CS]） |
| 缺口与注意 | IEEE 在 Crossref 零摘要，DOI 滞后 2–6 个月，CV 与机器人会议的新鲜度改走 CVF 与 arXiv；NeurIPS 的 Curran DOI 约晚 8 个月；ACM 全库 OA 但禁止脚本下载，因此只取元数据并外链；平台层不接 IEEE API（CP HC-27）。ISCA 当年卷被 robots 禁止，调度器须支持"禁区到期后重新排队"（[CS §4][CS] 第 9 条）。会议全文中只有明确 CC 许可者进入共享层（Anthology 2016 年起的 CC BY、JMLR 的 CC BY、LIPIcs 的 CC BY、TechRxiv 逐篇判定），其余一律 link_only（[CS §2.7][CS]） |

### 7.7 二级聚合与仓储

| 职能 | 来源（优先级 / 族） | 要点 |
|---|---|---|
| 权威层 | crossref（P0；XREF，另有 LOOKUP；年度文件作回填）、datacite（P1；AGG 加年度 CC0 文件） | Crossref 按请求类分池；DataCite 覆盖 arXiv、LIPIcs、Zenodo 的 DOI |
| 广度层 | openalex（P0；季度快照加 API 补查；受预算约束） | host 字段不可用于路由；会议实体碎片化（NeurIPS 4,177 条、ICLR 757 条），会议仍靠 L1；OA 判定有偏差（JMLR 约 1%），OA 状态须多源投票（[AG §3][AG] 第 19 条） |
| 信号层 | s2（P1；Datasets 需 key，API 1 RPS；商用许可未明示，LQ-08）、opencitations（P1；CC0 dump 加 REST，180 次/分钟/IP）、hf_papers（P0，限 CS） | S2 的 key 只作批量与离线用途 |
| 学科层 | europe_pmc、pubmed、inspire_hep、zbmath_open、repec、dblp（快照）为 P0；nasa_ads_scix、econbiz 为 P1 | 见 §7.1–§7.6 |
| 全文与 OA | pmc（P0）；unpaywall（P1，兼容层）；core（P1，但 `requires_license`）；doaj（P1；API 2 req/s 加 CSV，CC0）；econstor、scoap3_repo（P1）；zenodo（P2，OAI 30 次/分钟）；hal（P2，needs_confirmation）；openaire（P2，dump 为 CC BY）；osti_gov（P2） | 共享全文只收许可白名单内的条目（CP HC-05） |
| 注册表（kind=`registry`，简报 R2-11） | orcid（P1；用户 OAuth；商用门控；robots 冲突，needs_confirmation；年度 CC0 文件经 BULK）、ror（P1；dump 为 CC0，BULK）、datacite（P1，与权威层同一行）、wikidata（P2；SPARQL）、open_policy_finder（P2；CC BY-NC-ND，`requires_license`） | ORCID 公共 API 限非商业，平台商业化时须成为会员（[AG §2.2.13][AG]） |
| 观察与仅元数据 | fatcat_ia_scholar、lens（用户 token）、ssoar | — |
| 平台层排除 | base、scopus、web_of_science（用户可自带 key 做私有富化）、dimensions、microsoft_academic（只兼容 `mag` ID）、google_scholar | CP HC-26 |
| 新写 | opencitations、doaj、datacite、ror（BULK）、openaire（BULK，P2）、wikidata（P2）、core（取得许可后）；仓储平台族 dspace、eprints、invenio_rdm、ojs 的模块（委托 OAI 族） | — |
| v1 去向 | crossref：移植；openalex：移植，并新写快照导入器；s2：包装；unpaywall：包装；repec：包装；dblp：在线路径废止，改为 dblp_drops | 见 §14.1 |

### 7.8 中文与区域

| 项 | 内容 |
|---|---|
| 主干通道 | 用户导入题录；OpenAlex 与 Crossref 中已收录的中文 DOI 刊；区域聚合（P2）。[SYN §3.3][SYN] 统计中文与区域来源没有 P0、P1 |
| P2 | jstage（WebAPI；商用须申请，受商用门控；不允许大批量下载）、scielo（ArticleMeta API）、cinii_research（ResourceSync；OpenSearch 不用）、chinaxiv（观察；robots.txt 返回 403 维护页）、paper_edu_cn（暂缓：停服维护）、wulixb（Crossref ⚠）、ccs_chemistry（Crossref）；sciengine（metadata-only，Crossref ⚠）；redalyc（metadata-only） |
| user-import-only | cnki、wanfang、cqvip |
| 族与新写 | 题录导入管线（新写，不是连接器）：解析 RIS、BibTeX、EndNote、CSL-JSON，结果进入用户私域；按 DOI 或标题匹配共享语料；匹配不上的条目留在私域（CP HC-01）。另有 jstage（SITE，P2）、scielo（AGG，P2）、cinii 的 ResourceSync（bulk，P2） |
| 缺口与注意 | 知网 robots 为 `Disallow: /`，万方检索子域有 WAF：不做代理，不绕开 IP 授权（[AG §2.2.28][AG]）。中文生态须补一轮调研（G-05）。面向境内用户的 LLM 路由由 08 定义（CP HC-12） |

### 7.9 新写 connector 汇总（SI-09）

| connector | 族 | 学科 | 优先级 | exec_side | 官方通道 | 依据 |
|---|---|---|---|---|---|---|
| europe_pmc | AGG | 生、心 | P0 | platform | REST v6.9（cursorMark、FIRST_IDATE） | [LS §2.3.3][LS] |
| pubmed | AGG + BULK | 生、心 | P0（⚑ROBOTS：NCBI 书面确认前不调用，R2-13） | platform | E-utilities；baseline 与 updatefiles | [LS §2.3.1][LS] |
| pmc | OAI + BULK | 生 | P0 | platform | PMC Cloud S3、OAI-PMH、BioC | [LS §2.3.2][LS] |
| inspire_hep | AGG | 物 | P0 | platform | REST（每 IP 每 5 秒 15 次） | [NS §2.3.1][NS] |
| zbmath_open | AGG + OAI 实例 | 数 | P0 | platform | REST 与 OAI-PMH | [NS §2.3.3][NS] |
| aps_harvest | SITE（OA 集）/ TDM（全量，用户授权） | 物 | P0 | platform / user | Harvest API | [NS §2.3.1][NS] |
| openreview（v2） | SITE | CS | P0 | platform（书面确认前停用平台侧共享收割，R2-20）/ user（本人 token 只供本人查询） | API v2 | [CS §2.1.2][CS] |
| dblp_drops | BULK | CS | P0 | platform | DROPS 月度 XML | [CS §2.1.4][CS] |
| hf_papers | SITE（信号） | CS | P0 | platform | Hub API | [CS §2.1.1][CS] |
| jmlr | SITE | CS | P0 | platform | RSS 加 citation meta | [CS §2.1.2][CS] |
| scoap3 | SITE | 物 | P1 | platform | `/api/records/` | [NS §2.3.1][NS] |
| nasa_ads_scix | AGG | 物、地 | P1 | user | ADS API（每用户 token；条款书面确认前按用户级凭证处理，R2-14） | [NS §2.3.1][NS] |
| plos | SITE | 生、心 | P1 | platform | Search API 与 allofplos | [LS §2.4.6][LS] |
| elife | SITE | 生 | P1 | platform | GitHub XML（API 待确认） | [LS §2.4.5][LS] |
| pubtator3、icite | AGG | 生 | P1 | platform | REST（限速与许可 ⚠） | [LS §2.3.4][LS] |
| worldbank_dr | SITE | 经 | P1 | platform | D&R API v3 | [SS §2.4][SS] |
| assa_program | SITE | 经 | P1 | platform | 程序 HTML（robots 只禁 GPTBot 与 Amazonbot） | [SS §2.5][SS] |
| cb_rss | FEED（解析器） | 经 | P1 | platform | BIS CB-RSS；ECB 与 Fed 的 RSS | [SS §2.4][SS] |
| econbiz | AGG | 经、管 | P1 | platform | API v1 beta（不得大规模复制） | [SS §2.6][SS] |
| opencitations、doaj、datacite、ror | AGG + BULK（datacite、ror 的 kind 为 `registry`，R2-11） | 全 | P1 | platform | REST 与 CC0 dump | [AG §2.2][AG] |
| usenix、ecva | SITE | CS | P1 | platform | 会议页；ECVA 目录页 | [CS §2.2][CS] |
| pwc_archive | BULK（一次性） | CS | P1 | platform | HF Datasets | [CS §2.2][CS] |
| springer_nature | TDM | 多学科 | P1 | user | Meta、OA、Full-text API（每用户 key；OA/Meta API 在条款书面确认前同样按用户级凭证处理，Meta API 摘要按 C 类不进共享层，简报 R2-14）；TDM 请求的 UA 须含 `TextDataMining`，因此由 pc-agent 执行；TDM 语料只在项目期间保存（[LS §0][LS] 第 7 条） | [NS §2.3.4][NS]、[NS §0][NS] 第 5 条；CP §2.2.1 |
| osti_gov | AGG | 物、化 | P2 | platform | REST | [NS §2.2.3][NS] |
| jstage、scielo、cinii | SITE / AGG / BULK | 区域 | P2 | platform | WebAPI / ArticleMeta / ResourceSync | [AG §2.2.28][AG]、[AG §2.2.29][AG] |
| 平台族模块 | PF：atypon、silverchair、highwire、ojs、dspace、eprints、invenio_rdm | — | P0–P1 | 见 §5.3 | — | SI-10 |
| 族引擎 | XREF（移植 v1 crossref）、OAI（移植 v1 `_oai.py`）、FEED | — | P0 | platform | — | — |

没有官方 API 或协议通道的出版商，如 IOP、ACS、AMS、Cambridge、APA、ACM，以及 IEEE 的站点，除 XREF 外不写任何取回代码。其中有用户侧取回需求的，由平台族配方承接（§12）。

---

## 8. 摘要补齐链（⑦）

### 8.1 权利类别

每条摘要都作为一个**摘要变体**（AbstractVariant）独立存放，字段为 `(version_id, source_id, lang, text, text_sha256, rights, license_code, reconstructed, version_match, display_level_max, fetched_at)`。其中 `abstract_source = source_id`，`abstract_rights = rights`（SI-04）。落表时整组带上 RightsTag（CP HC-07；05 `corpus.abstract` 的列组）：`open` 记 `rights_class=M4`、`publisher_copyright` 记 M5，另有 `commercial_ok`、`attribution_text`、`evidence_grade` 等；`personal_license`（M6）只存 `usr`。

| `abstract_rights` | CP 类别 | 典型来源 | 共享卡片展示上限 | 可作共享派生（TL;DR、翻译）输入 | 可作内部索引与嵌入输入（默认假设） | 存放域 |
|---|---|---|---|---|---|---|
| `open` | A 类（M4） | arXiv 元数据（CC0）；PMC 与 EPMC 的 OA 子集（按 LICENSE）；CC BY 期刊与预印本；APS Harvest OA；ACL Anthology（2016 年起为 CC BY）；DOAJ 文章（按文章许可）；zbMATH（CC BY-SA，部分评论因许可冲突不可得） | DL4（全文展示，按许可署名；SA 许可保持相同方式） | 允许（NC 视部署而定；ND 不得改写） | 允许 | corpus |
| `publisher_copyright` | B 类（M5） | Crossref 存缴的摘要；PubMed 与 EPMC 的非 OA 摘要；由 OpenAlex 倒排索引还原的摘要；S2 abstracts 数据集；经 Crossref 取得的 SSRN 摘要；RSS 中的摘要 | DL3：首句或 ≤N 字片段，加原文链接（N 由 08 依 LQ-01 定） | 禁止（P-02、LQ-05） | 默认允许；有机器可读 TDM 保留的来源除外；总开关可关闭（LQ-02） | corpus |
| `personal_license` | C 类（M6） | SN Meta API、Elsevier API（在用户侧取得）；IEEE API 平台层不接 | 不对他人展示（per_user_only） | 禁止 | 禁止 | usr |
| `unknown` | — | 新接入、尚未分类的来源 | 不展示，按 link_only 处理 | 禁止 | 禁止，直到完成分类 | 只留在源记录的载荷中；完成分类后才生成摘要变体（与 [05][05] 的 `corpus.abstract` 只收 A、B 类一致） |

还有两条规则：
- 单篇文章为 CC 许可时，它的摘要按 `open` 处理，无论这段摘要来自哪个渠道。
- 摘要的权利由**来源渠道与单篇许可**共同决定。例如同一段 Elsevier CC BY 文章的摘要，经 EPMC 取得时也是 `open`。依据：[LS §2.4.1][LS]、CP §2.2.1、HC-08。

### 8.2 通用补齐顺序

1. 同一版本的 `open` 摘要。
2. 同一 Work 其他版本的 `open` 摘要，例如 arXiv 预印本（CC0）、CC BY 的 bioRxiv 版本。卡片须注明"摘要来自预印本 vN"（`version_match=other`）。卡片优先使用 arXiv 版摘要（CP HC-08）。
3. 学科开放源：INSPIRE（以 CC0 为主）、zbMATH（CC BY-SA）。
4. `publisher_copyright` 类的注册机构摘要：Crossref；生医另有 EPMC 与 PubMed。
5. `publisher_copyright` 类的聚合还原：OpenAlex 倒排索引，优先用季度快照，否则用免费的单实体查询；S2 abstracts 数据集。
6. `personal_license` 类：用户侧取得，只对本人可见。
7. 降级：只显示标题 + venue + 作者 + 分类码。推荐冷启动不依赖摘要（SI-04）。

### 8.3 按出版方的路由表

下表的 Crossref 覆盖率是调研的样本实测值（`coverage.abstracts-current` 或年度计数），不是全量统计。

| 出版方（member / 前缀） | Crossref 摘要覆盖（样本） | 共享层补齐链 | 用户侧 C 类 | 依据 |
|---|---|---|---|---|
| Elsevier（78 / 10.1016） | 0%：理科 9 刊、经管 19 刊、Cell Press 系全部为 0；2025 年 1,040,981 篇期刊文章中仅 424 篇带摘要 | [生医] EPMC/PubMed（B；CC 单篇为 A）→ 同 Work 的 arXiv/bioRxiv 版本（A）→ OpenAlex（B）→ S2（B） | Elsevier API | [AG §2.2.1][AG]、[NS §2.4][NS]、[SS §2.8][SS]、[LS §2.4.1][LS] |
| APA（10.1037） | 0%（9 刊），参考文献覆盖也为 0 | PubMed（B，部分）→ PsyArXiv 版本（A，按许可）→ OpenAlex（B） | 用户导入 PsycInfo（私有） | [LS §2.4.13][LS] |
| IEEE（10.1109） | 2025 年 445,469 条全部无摘要 | arXiv 版本（A）→ OpenAlex（B）→ S2（B） | 不提供（CP HC-27） | [CS §2.4][CS] |
| ACS（10.1021） | 0.07–0.15 | ChemRxiv 版本（按许可）→ OpenAlex（B） | — | [NS §2.3.2][NS] |
| APS（10.1103） | PRL 0.29、PRB 0.11、RMP 0；OA 刊 ≥0.92 | APS Harvest OA（A）→ arXiv（A；arXiv 号来自 Harvest 或 INSPIRE）→ OpenAlex（B） | APS Harvest 全量（用户授权） | [NS §2.3.1][NS] |
| Springer Nature（10.1007 / 10.1038） | Nature 系 0.10–0.21（Nat Commun 0.47）；Springer 0.40–0.99；LNCS book-chapter 约 3% | [生医] EPMC → arXiv（A）→ Crossref（B）→ OpenAlex（B） | SN Meta API（C 类，只许个人使用） | [NS §2.4][NS]、[CS §2.4][CS]、CP §2.2.1 |
| AOM（10.5465） | 0%，含 Proceedings | OpenAlex（B，常有滞后；AMJ 2025 抽样 23/25 已补齐）→ SSRN 版本（B） | — | [SS §2.8][SS] |
| UChicago（10.1086） | 0%（5 刊） | OpenAlex（B）→ NBER、SSRN、RePEc 的 WP 版本（B） | — | [SS §2.8][SS] |
| Taylor & Francis（10.1080） | 多刊为 0% | OpenAlex（B）→ [生医] EPMC（B） | — | [NS §2.4][NS]、[LS §2.4.15][LS] |
| MSP（10.2140）、IMS、Duke、Intl Press、Annals | 0–0.14 | arXiv（A）→ zbMATH（A，SA）→ OpenAlex（B） | — | [NS §2.3.3][NS] |
| NBER（10.3386） | 0 | RePEc bulk（B）→ NBER RSS 中的摘要（B） | — | [SS §2.4][SS] |
| ACL（10.18653） | 0 | ACL Anthology XML（2016 年起 CC BY，为 A；更早为 CC BY-NC-SA，为 A 但受 NC 门控） | — | [CS §2.4][CS]、[CS §2.7][CS] |
| AAAI（10.1609） | 100%（© AAAI） | Crossref（B） | — | [CS §2.4][CS] |
| IOP、AIP、OUP、INFORMS、AEA、SAGE、SIAM、EMS、ACM 期刊 | 多数 ≥0.9 | Crossref（B；单篇 CC 许可时为 A） | — | [AG §2.6][AG]、[NS §2.4][NS] |
| OpenReview 上的 venue（ICLR、TMLR、COLM） | 不适用 | notes 元数据为 CC0（A）；服务账号确认前改经 arXiv | — | [CS §2.7][CS] |

**冲突裁决**：[NS §3][NS] 第 2 条建议把 SN Meta API 用作 Nature 与 Springer 的摘要源。本文按 CP §2.2.1 与 M6 把它归为 C 类，不进入共享链，详见 §19 第 7 条。

### 8.4 使用门（与 08 的接口）

| 用途 | 规则 | 裁定方 |
|---|---|---|
| 共享卡片展示 | 取可得的最高展示级别：`open`（DL4）优先于 `publisher_copyright`（DL3），否则不显示摘要 | 展示级别由 08 定 |
| 共享派生（TL;DR、翻译） | 只接受 `open`，且许可允许改编：非 ND；NC 只在非商业部署时可用 | 简报 P-02；LQ-05 |
| 内部索引与嵌入 | 总是可用 `open`；`publisher_copyright` 按简报 R2-21 默认可用（不展示，展示上限 DL3），但来源有 `tdmrep=reservation_1`（或 `unreadable`）、`content_signal.ai_input=no` 的除外；`content_signal.search=no` 的站点内容不进共享检索索引（08 R10）；`personal_license` 与 `unknown` 永不可用 | LQ-02、LQ-17（⚠ 嵌入对应 Content-Signal 的哪个用途尚未定） |
| 回退 | 关闭总开关 `policy.index_b_abstracts` 后，嵌入按 `input_basis`（及 05 由它推出的 `input_rights_max`）筛出受影响的行重建（§11.3），BM25 文档同步重建；LQ-02 结论为否时即执行（简报 R2-21） | 08 与本文 |

### 8.5 执行与预算

```python
# 设计伪代码 —— 摘要补齐（enrich 的子任务）
def abstract_fill(v: Version, chain: AbstractChain, budget: Budget) -> list[AbstractVariant]:
    have = existing_variants(v)
    if any(a.rights == "open" and a.version_match == "same" for a in have):
        return have                                          # 已有同版本 A 类，结束
    for step in chain.for_publisher(v.owner_member, v.discipline):   # 按出版方与学科路由（§8.3）
        d = policy.decide(step.source, step.channel, Operation.LOOKUP, ctx, now())
        if not d.allowed:
            continue                                         # 策略不允许，跳到下一环
        if not budget.try_spend(step.cost):                  # OpenAlex 美元额度、S2 RPS 等
            defer(v, step)
            continue
        a = step.fetch(v)                                    # 优先查本地快照，远端只做补查
        if a:
            a.rights = classify_rights(a, v.item_license)    # 单篇为 CC 许可时按 open
            have.append(a)
            if a.rights == "open":
                break                                        # 拿到 A 类即停；只有 B 类时继续找 A
    return have
```

- **成本**：OpenAlex 单实体查询免费，因此用快照未覆盖的新文按 DOI 单查补摘要，成本为零（[AG §2.2.2][AG]）；列表查询计费，只用于批量。S2 的 key 只有 1 RPS，只用数据集批量，不在补齐链中实时调用。
- **容量**：EPMC 受 `www.ebi.ac.uk` 的 Crawl-delay 10 约束，全平台单连接每日至多约 8,640 次请求（⚠ 估算）。生医摘要主要来自 `FIRST_IDATE` 收割流入库的记录，在本地 join；远端单条补查只补漏，并与收割共用同一个令牌桶。
- **可观测**：每周按学科与出版方报告摘要覆盖（A 类、B 类、无），作为 §17 的验收证据，也用来检验补齐链是否需要重排。


---

## 9. 身份模型：Work / Version / Manifestation（⑧）

### 9.1 三层定义与标识符粒度

| 层 | 定义 | 例 |
|---|---|---|
| Manifestation | 具体载体：一条源记录（每个 `(source_id, source_key)` 一行），或一个文件或页面（PDF、HTML、JATS、TEI） | Crossref 的一条 work 记录；EPMC 的一条记录；arXiv HTML 页；用户私有 PDF |
| Version | 可被独立引用的文本版本：预印本的每个修订（arXiv vN、OSF `_vN`、ChemRxiv `/vN`）、作者接受稿（AM）、正式版（VoR）、WP 的一个编号版本 | arXiv 2401.01234v2；某刊的 VoR；NBER w31234 |
| Work | 同一研究成果的全部 Version 的集合，其 id 即 `cluster_id` | "某论文"，包含其预印本 v1–v3 与期刊正式版 |

**标识符粒度**：每个方案必须声明粒度，union-find 只在对应粒度上合并。

| 方案 | 粒度 | 规范化 | 说明 |
|---|---|---|---|
| `doi` | version | 小写；去掉 `https://doi.org/` 与 `doi:` 前缀（沿用 v1 `ids.normalize_doi`） | 另记注册机构（crossref、datacite、op） |
| `doi_family` | version_family | 同 `doi` | 覆盖全部修订的 DOI：bioRxiv 与 medRxiv 的 DOI（owner prefix 10.64898，含旧 `10.1101/…` 字符串）、arXiv 的 DataCite DOI 10.48550。粒度随登记方而不同，方案级的 `granularity` 表达不了，所以 normalize 按注册表中的"DOI 前缀与 owner → 粒度"映射把它们改写为本方案；映射同样作用于关系声明里的 DOI，保证两边能对上。需要 05 在 `corpus.id_scheme` 增补此行（§19 第 14 条） |
| `arxiv_v`（如 2401.01234v2） | version | 保留版本号 | 取自 `arXivRaw` 的版本史 |
| `arxiv`（基础 id） | version_family | 去掉版本号；兼容旧式 `math.GT/0309136` | DataCite DOI 10.48550 也是 family 级 |
| `pmid` | version | 数字 | — |
| `pmcid` | version | `PMCxxxx.N` | 版本号不代表新旧，须读 JSON 判断 AM 还是 VoR（[LS §2.3.2][LS]） |
| `osf` | version（`_vN`）/ version_family（guid） | — | 每个 OSF 版本一个 DOI（[LS §2.2.3][LS]） |
| `ssrn`、`nber_w`、`repec`、`wb_repnb`、`iza_dp`、`ecb_wp`、`bis_wp`、`imf_wp`、`cepr_dp` | version | — | WP 系列的编号（[SS §3][SS] 第 15 条） |
| `dblp`、`acl`、`openreview_note`、`pii` | version | — | — |
| `openreview_forum` | version_family | — | — |
| `openalex`（W）、`s2`（corpusId）、`inspire`（recid ⚠）、`mag` | work_assertion | — | 第三方断言，**只作投票证据，不直接驱动合并**；OpenAlex 常把预印本与正式版并为同一个 W |
| `url`（v1 D-015） | manifestation | — | — |

### 9.2 Version 的形成：强标识符 union-find

1. **同一条源记录中出现的 version 粒度标识符**，归为同一个 Version；两条记录共享任一 version 粒度标识符，即为同一 Version（union-find，路径压缩加按秩合并，[RT §7.1][RT]）。
2. **只带版本系标识符的记录**（arXiv 基础 id、`doi_family`），挂到该版本系中、按记录自身时间戳（`oai_datestamp`、`posted` 或 `fetched_at`）当时的最新修订上；修订之间用 `revision_of` 边相连。
   - 修订史未知时，先挂到当前已知的最新修订；修订史补全（例如 `arXivRaw` 到达）后，按同一规则确定性地重挂，并写合并日志（`op=move_version`）。
   - 这样挂接结果只取决于最终的记录集合，与到达顺序无关。若简单地挂到"到达时的最新修订"，先到后到会得出不同的 Version 归属，违背 DR-9。
3. **指向其他著作的标识符是关系，不是身份**。这沿用 v1 的"同源著作判界"（[v1-AGG][v1-AGG] §6）：
   - arXiv 记录里的 `doi` 与 `journal_ref`、Crossref 的 `relation.is-preprint-of`、bioRxiv 的 `published`、OSF 的 `attributes.doi` 都指向另一版本，只产生关系声明（§9.3），不进入本 Version 的标识符集合。
4. **冲突**（例如一条记录声称两个不同的 VoR DOI）进入冲突队列，不猜测。

### 9.3 Work 的形成：多源投票的版本边

Work 的 union-find 只沿"已接受"的边合并：

| 边 | 证据 | 接受规则 | 依据 |
|---|---|---|---|
| `revision_of` | 同一版本系内的修订（arXiv vN、OSF `_vN`、ChemRxiv `/vN`） | 第一方强证据，自动接受 | [NS §3][NS] 第 14 条 |
| `version_of`（预印本、AM 与 VoR 之间，预印本服务器类） | **第一方**：arXiv `doi`/`journal_ref`、bioRxiv `/pubs`、EPMC `HAS_PUBLISHED_VERSION`、Crossref `is-preprint-of` 与 `has-version`、OSF `attributes.doi`、APS Harvest `identifiers.arxiv`、eLife RP 到 VoR、DataCite `IsVersionOf`；**第三方**：同一个 OpenAlex W、同一个 S2 corpusId、同一个 INSPIRE recid | 至少 1 条第一方证据且通过"同作品健全检查"（标题相似或作者重合达到阈值），或至少 2 条相互独立的第三方证据且通过检查。其余进入候审。"相互独立"按 `source_id` 计：同一来源经快照与 API 两条通道观察到的同一断言只算一票 | SI-16；[LS §3][LS] 第 7 条；[AG §3][AG] 第 7 条 |
| `preprint_of`（WP 系列与发表版） | RePEc "Published in"、NBER `published`、Crossref relation、标题与作者模糊匹配 | **只建关系边，不并入同一 Work**（D-007、SI-16）；证据优先级 RePEc/NBER > Crossref relation > 模糊匹配（模糊匹配只进候审） | [SS §3][SS] 第 5 条 |
| `same_as`（人工裁决） | 候审队列中人工判定为同一著作 | 人工决定后接受，可撤销 | D-007；v1 `dedupe decide` |

- **"预印本服务器类"**：arXiv、bioRxiv、medRxiv、PsyArXiv 与 OSF、ChemRxiv、Research Square、Preprints.org、TechRxiv 等，在 SourceSpec 中标记 `version_linking: union`。
- **"WP 系列类"**：NBER、SSRN、央行与国际组织 WP、RePEc WP，标记 `version_linking: relate_only`。
- 同一篇 SSRN 论文若同时有 arXiv 版本，其 arXiv 版与 VoR 之间仍按预印本服务器类处理。
- **与 D-007 的关系**：D-007 要求"预印本与正式版不合并为一条"。v2 中两者是同一 Work 下的不同 Version，各自保留元数据与全文，没有被合并成一条记录；WP 与发表版则连同一 Work 都不并入。这一细化需要以 ADR 记录，见 §14.3 与 §19 第 2 条。

**顺序无关**：
- 边是否被接受，只取决于证据的多重集合（投票可交换）和两端 Version 的收敛字段（健全检查用）。字段收敛本身按 D-031 的全序规则，与到达顺序无关；
- 证据或任一端的收敛字段变化时，重新评估这条边。由接受变为不接受时，按下文"回滚"撤销该边并重算分量；
- union-find 的结果只取决于被接受边的集合。

因此同一批输入以任意顺序到达，得到的簇相同（沿用 D-031 的纪律，§15.2 用属性测试验证）。如果只在边首次出现时评估一次，就会出现反例：一条第一方证据先于正式版的规范标题到达，健全检查因标题残缺而失败，之后不再重评；换一个到达顺序，同一条边就会被接受。

**并发**：identify 可以多 worker 并行。一次 union 先按 work_id 升序对涉及的 Work 行加锁（`SELECT … FOR UPDATE`），再改写，避免死锁与并发丢更新（与 02 §2.9.4"同一 cluster 的合并以行锁串行"一致；借鉴 arxiv-at-home 的行锁做法，§5.6）。

**`cluster_id` 物化与稳定性**：
- `cluster_id` 即连通分量的确定性代表元：最早创建的 work_id。"簇相同"指成员划分相同，与 work_id 的具体取值无关。
- 两个 Work 合并时，较早的 Work 为幸存者；被吸收的 Work 保留为墓碑，`merged_into` 指向幸存者。用户库、事件等引用方沿墓碑链解析，不需要跨用户改写 `usr` 数据（[05][05] 的做法）。
- 拆分时，包含原 Work 最早 Version（最小 version_id）的一侧保留原 work_id 与 `public_id`，另一侧分配新的 Work 与 `public_id`，使结果确定；受影响用户库条目的归属由 05、06 处理（RT §7.3）。

**回滚**：
- 所有 union 与 split 操作都追加写入合并日志（05 的 `corpus.cluster_log`）：操作、涉及的 work 与 version、原因（共享标识符、修订边、版本投票、人工）、证据、规则版本、操作者。
- union-find 本身不支持删除，所以拆分的做法是撤销某条边后，重算受影响的连通分量。分量一般很小。
- 沿用 v1 "物理不删行、可回滚"的语义（[v1-06][v1-06] §3）。

### 9.4 弱信号候审（L1 与 L2）

1. **候选召回**：
   - 标题 shingle 的 MinHash，经 LSH 分桶，Jaccard ≥0.8；
   - 分块条件：年份差在 [−1, +N] 内，且作者姓氏集合至少重合 1 个。N 按关系类别配置：预印本服务器类默认 3，WP 系列类默认 6（⚠ 设计值，用 §15.7 的金标集校准）。原方案"年份 ±1 且首作者姓氏一致"会漏掉大多数 WP 与发表版的配对（两者常隔数年，作者顺序也会变），也会漏掉拖了两三年才正式发表的预印本；
   - 姓氏先做 ASCII 折叠与常见音译归一，再比较；
   - 另加 v1 的观测级弱键 `(title_norm, 首作者姓)`（D-031，[RT §7.1][RT]）。
2. **概率打分**：用 Splink（Fellegi–Sunter 模型加 EM；MIT 许可；可用 DuckDB 或 PG 后端，[RT §7.1][RT]）。特征包括：
   - 标题相似度、作者姓氏集合的 Jaccard、年份差；
   - venue 相容性、DOI 前缀关系；
   - 摘要向量的余弦相似度。
3. **裁决**：高分对进入 `candidate_duplicate` 候审队列；**不论得分多高，一律不自动合并**（D-007）。同一 DOI 的大小写或前缀差异在 normalize 段已消除，不属于弱信号。
4. **队列负载控制**：
   - 只收阈值以上的对；
   - 按"是否进入任一用户的候选集"（06 发出的聚合信号，不带用户标识）排优先级，不按私有文献库成员资格排序（HC-01）；
   - 设每日上限。

   用户在界面上报告"这是同一篇"时，作为候审线索进入队列，入口由 07 与 06 定义。线索进入 corpus 时不带任何用户标识，按用户限频，人工裁决前不影响任何共享数据；`corpus.dedupe_candidate.method` 须由 05 增补 `user_report` 取值（§19 第 14 条）。
5. **审核人**：v2.0 由运维或策展人审核。界面承接 v1 的 `dedupe review/decide/revert` 语义（[v1-06][v1-06] §3）。

### 9.5 字段收敛与展示版本

- **字段级来源优先级**从 v1 的单一优先级表（D-021、D-035）扩展为"字段 × 学科 × 源"的可信度矩阵（[AG §3][AG] 第 19 条；T13）。例：
  - venue 与页码：出版方与 Crossref > dblp > OpenAlex；
  - 主题：OpenAlex 加本地分类器；
  - OA 状态：多源投票（§11.6）；
  - 引文计数：按来源分别保存，不合成一个数。

  同级 tie-break 采用 D-031 的全序规则。
- **展示版本**：Work 的卡片默认展示"最佳版本"，优先顺序为 VoR > AM > 最新修订的预印本。摘要按 §8 取权利最好的一个，并注明它来自哪个版本。
- **评审状态**，按新鲜度阶梯（SI-14）得出：
  - 预印本：只有预印本 Version；
  - 已接收：OpenReview 接收态，或会议官方 OA 平台已上线；
  - 已出版：有 VoR。

### 9.6 其他关系

| 边 | 来源 | 用途 |
|---|---|---|
| `erratum_of`、`retraction_of` | Crossref `update-to`（含 Retraction Watch，CC0）、OpenAlex `is_retracted`、PMC `is_retracted`、PubMed 出版类型 | 撤稿过滤与徽章（§11.5） |
| `supplement_of`、数据与软件关联 | DataCite `relatedIdentifiers`、Crossref 数据引用端点 | 详情页 |
| `cites` | OpenCitations（CC0）、OpenAlex `referenced_works`、Crossref 参考文献 | 引文图（04）；按来源分别记录（§11.7） |
| `presented_at` | ASSA 程序、NBER SI 议程 | 经管会议事件（§2.4） |

### 9.7 身份相关的表：与 05 的对应（设计伪代码 DDL）

物理表由 [05][05] 定义。下表是本文语义与 05 表的对应，以及本文对 05 表提出的语义要求。截至 2026-09-27，05 §3.1 已吸收 `id_scheme.granularity`、`version.family_key`、`identifier_assertion`、`version_edge` 的词表与 `source_record.provenance`；尚待 05 增补的只有 `id_scheme` 的 `doi_family` 行与 `dedupe_candidate.method` 的 `user_report` 取值（§19 第 14 条）。

| 本文语义 | 05 物理表 | 本文要求 |
|---|---|---|
| Work（簇） | `corpus.work` | 幸存者取最早创建的 work_id；被吸收者保留为墓碑（`status='merged'`、`merged_into`）；`canonical_version_id` 即 §9.5 的展示版本 |
| Version | `corpus.version` | `version_kind` 用 05 的枚举，其中 AM 记为 `accepted`；需要 `family_key` 表达版本系（arXiv 基础 id、bioRxiv DOI、OSF guid） |
| Manifestation：源记录 | `corpus.source_record`，`UNIQUE (source_id, source_key)` | 保存 mapper 的输入；harvest 段的幂等键（§10.2） |
| Manifestation：载体 | `corpus.manifestation` | 只记载体的公开事实，从不记录"谁有权限"（HC-02） |
| 标识符 | `corpus.identifier` 与 `corpus.id_scheme` | 粒度是方案的属性，记在 `id_scheme` 上。`work_assertion` 类方案**不进** `corpus.identifier`：该表的主键 `(scheme, value)` 是强合并锚点，放进去会让 OpenAlex W 之类的第三方断言直接驱动合并，违背 §9.1 与 D-007 |
| 版本边 | `corpus.version_edge` | `kind` 用 §9.3 的词表，另有 `link_class` 与 `state`（05 已采用） |
| 合并日志 | `corpus.cluster_log` | `reason` 覆盖共享标识符、修订边、版本投票、人工、回滚 |
| 候审 | `corpus.dedupe_candidate` | 方法取 `weak_key`、`minhash_lsh`、`splink`、`v1_import`，另请 05 增补 `user_report`（§9.4） |
| 摘要变体 | `corpus.abstract`（只收 A、B 类） | C 类存于 `usr`；`unknown` 不入表，完成分类前只留在源记录的载荷中（§8.1） |

```sql
-- 设计伪代码 DDL —— 本文对 05 物理表的语义增量；最终 DDL 以 05 为准（前三项 05 §3.1 已吸收，保留作语义说明）
ALTER TABLE corpus.id_scheme
  ADD COLUMN granularity text NOT NULL
    CHECK (granularity IN ('version', 'version_family', 'work_assertion', 'manifestation'));

ALTER TABLE corpus.version ADD COLUMN family_key text;      -- 版本系；只带版本系标识符的记录按 §9.2 规则 2 挂接

CREATE TABLE corpus.identifier_assertion (   -- 第三方 work 级断言：只作 version_of 的投票证据，不构成合并
  scheme      text NOT NULL,                  -- openalex_w | s2_corpus | inspire_recid | mag
  value       text NOT NULL,
  version_id  bigint NOT NULL REFERENCES corpus.version,
  source_id   text NOT NULL,
  observed_at timestamptz NOT NULL,
  PRIMARY KEY (scheme, value, version_id)     -- 同一断言可以挂在多个 version 上
);

-- corpus.version_edge 采用本文词表：
--   kind       ∈ revision_of | version_of | preprint_of | same_as | erratum_of | retraction_of | supplement_of | dataset_of
--   link_class ∈ preprint_server | wp_to_publication | registry_relation | manual
--   state      ∈ accepted | candidate | rejected | revoked
--   evidence   记录每一票：来源、第一方或第三方、健全检查的结果

-- 尚待 05 增补：
INSERT INTO corpus.id_scheme (scheme, normalizer, granularity)
  VALUES ('doi_family', 'doi', 'version_family');          -- §9.1：bioRxiv/medRxiv、arXiv DataCite DOI
-- corpus.dedupe_candidate.method 的取值增加 'user_report'（§9.4）
```

---

## 10. 语料流水线（⑨）

### 10.1 总览

```text
        ┌──────── 收割道（background） ────────┐   ┌──────── enrich 道 ────────┐
WatchKey/回填/快照 ─► harvest ─► normalize ─► identify ─► enrich ─► index ─► percolate ─► FeedInbox(usr)
        ▲              │            │            │          │          │
  PolicyEngine    source_record  norm_record  version/   card_field  outbox 事件（04 索引器、06 匹配）
  （§6）          + cursor                   work/relation oa_asset
联邦 LOOKUP/SEARCH（交互道，04）──► 结果以 provenance=federated 进入同一 normalize/identify 路径
用户侧全文（§12）── 不经本流水线；私有产物只进 usr
```

- **不变式**：各段只通过持久化实体通信，每段幂等，同一批输入以任意顺序到达，结果一致（沿用 D-004 与 D-031）。
- **全文 fetch 移出后台**（简报 §6.1-6）：后台只取许可白名单内的 OA 全文，作为 enrich 的一个子任务（§11.9）；订阅全文由用户侧按需取回（§12）。
- **三道舱壁**：收割、enrich、交互分开，各自有并发与预算（简报 §6.2-5，参数由 04 定）。任务队列用 PG 原生的 procrastinate（简报 B-05）。

### 10.2 六段契约

| 段 | 输入 | 输出（持久化） | 幂等键 | 失败处理 | 对应 v1 |
|---|---|---|---|---|---|
| harvest | HarvestTask（WatchKey 增量、venue 回填、快照导入）；联邦结果 | 源记录（05 的 `corpus.source_record`；原始载荷按 `storage_policy` 保留）；harvest 运行日志；推进后的游标 | `(source_id, source_key, payload_sha256)`；游标与本批数据在同一事务提交，推进规则见 §10.3；同一 WatchKey 同一时刻只有一个任务在跑 | `transient`、`rate_limited`：在网关重试预算内重试；`challenge`：BLOCKED、主机冷却、探针告警；`empty_body`：端点降级并切换替补链；`policy_denied`：不执行，只记审计；`parse`：隔离该页，canary 标红 | discover + enumerate |
| normalize | 源记录 | NormRecord：标识符与粒度、版本与关系声明、venue 解析、日期语义、摘要变体、许可声明、分类声明 | `(record_id, mapper_version)` | schema 不合：隔离并告警 mapper；venue 低置信：进 venue 候审，不阻塞 | enumerate 的字段映射（[v1-06][v1-06] §5） |
| identify | NormRecord | 标识符图、Version、Work（`cluster_id`）、关系边、合并日志、字段收敛结果；异步产生候审对 | 由标识符集合与已接受边集合决定，与到达顺序无关；合并日志的 `op_id` | 标识符冲突：进冲突队列；证据不足：进候审；拆分只能人工或按规则撤销，按合并日志回放 | ingest（强合并、候审、preprint_of） |
| enrich | 新建或有变更的 Version 与 Work | 摘要补齐、许可与 OA 裁决、主题、嵌入、引文、徽章、可共享的卡片字段、共享 OA 资产 | 内容寻址缓存键 = 字段 ∥ 语言 ∥ 源文本哈希 ∥ 源版本 ∥ 模型 ∥ prompt 版本 ∥ 策略版本（[PU §2.6.7][PU]）；OA 资产按 `(version_id, license_code, sha256)` | 各字段独立失败，不阻塞 index；预算耗尽则延后；过不了三道闸则降级为原文首句 | extract（只对可共享全文）+ v1 的 enrich 通道（openalex、s2、repec） |
| index | corpus 变更的出箱事件 | BM25 文档、向量、图边、facet 位图、`route_stat` 增量（结构由 04 定义） | `(work_id, index_version, doc_hash)` | 可从 corpus 全量重建；失败重试 | ingest 尾部的 FTS 更新（D-034） |
| percolate | index 提交后的本批新 Work，以及新增 Version 或关键字段变更的已有 Work（§10.7） | FeedInbox 条目（05 的 `usr.feed_inbox`；经 04 的 WatchKey 倒排与 06 的兴趣匹配） | 按 04 §12.5 的批次号；`usr.feed_inbox` 只追加，读取时按 `work_id` 去重并跟随 `merged_into`，所以用户视图中 `(user_id, work_id)` 唯一（05 §3.2.5） | 重放安全；按用户日预算截断（06） | 无；v1 `subs watch` 的日报是其雏形（[v1-09][v1-09] §5–§6） |

### 10.3 harvest

- **任务类型**：
  - `IncrementTask(watch_key_id, cursor)`：WatchKey 的编译与新鲜度调度算法由 04 定义，由 02 的 Harvest Scheduler（P6）执行，本文的 connector 消费（简报 R2-34）；引用计数去重；
  - `EnumerateTask(venue_id | prefix | set, window)`：回填；
  - `SnapshotTask(release, union_filter)`：快照导入（`bulk_snapshot` 族，R2-11）；
  - `ProbeTask`：漂移探针。
- **每个任务**先取策略决定（§6.3），再由连接器执行（§5.2）。
- **游标语义**：
  - 游标只在本批数据落库成功后，在同一事务中推进；
  - 逐页推进的前提是分页结果按游标字段升序（Crossref 用 `sort=created&order=asc`；EPMC 以日窗为单位）。不能保证顺序的通道，持久游标只在整个窗口或整段列表完成后推进。OAI-PMH 不保证按 datestamp 返回，属于后者（§5.4）。反例：分页无序时，第 1 页落库后游标就推到了该页的最大 `created`；若进程随后崩溃，而第 2 页中有记录的 `created` 比这个值早出重叠窗口以上（回填或大窗口时常见），这些记录会落在下次查询的 `cursor − overlap` 之前，从而被漏掉；
  - 每次从 `cursor − overlap` 开始，由 `(source_id, source_key)` 去重保证不重复；
  - 重叠窗口保证不漏（沿用 v1 `DateCursor` 与 `IdSetDiff`，[v1-09][v1-09] §5）。
- **并发**：`IncrementTask` 以 `watch_key_id` 为 procrastinate 的 lock 键（`EnumerateTask` 以 venue 或前缀为键），同一键同一时刻只有一个任务在跑，避免两个 worker 对同一上游重复请求；游标更新带版本号做比较交换，版本不符的提交整体回滚（⚠ procrastinate lock 的 API 须实现期核对，02 §2.3.4 有同样注记）。
- **与 04 的边界**：范围互相包含的 WatchKey（如某 venue 的 ISSN 流与其出版方的 member 流）是否合并，由 04 的 WatchKey 编译决定；本文只保证同键串行与结果去重。
- **联邦结果入库**：04 在交互道发起的 LOOKUP 与 SEARCH，其结果以 `provenance=federated` 写入源记录，走同一条 normalize 与 identify 路径。这样查询结果即成为语料，但仍受各源 `storage_policy` 约束，例如某些 API 条款禁止持久存储结果（[SS §0][SS] 第 8 条）。源记录与 harvest 日志不记录发起查询的用户与查询文本，只记 04 的 `plan_key`（其中不含用户信息，04 §8.1），以免私域信息经语料的来历流入共享层（HC-01、HC-02）。
- **向 04 提供的统计**：每批 harvest 为每个 WatchKey 记录新条目数、时间窗、请求数与成本；`EnumerateTask` 另按 venue、类目或前缀记录已完成的时间窗，供 04 判定范围完整性（04 §6.3 的 `scope_complete`、§20 第 30 项；落 05 的 `ops.harvest_run`）；identify 为每个 Version 记录 `first_seen_at` 与发布日。04 据此估计 λ 与滞后，写入 `route_stat`。

### 10.4 最新论文增量

| 源 | 增量方式 | 游标与重叠 | 日历型 / 连续型 | 要点 | 依据 |
|---|---|---|---|---|---|
| Crossref（期刊、带 DOI 的 WP 与预印本前缀、论文集） | `/journals/{issn}/works`、`/prefixes/{p}/works` 或 `/members/{m}/works`（均属 single 池），加 `filter=from-created-date` | 游标为已处理的最大 `created`；重叠 3 天；按标识符去重 | 连续 | 每周一次 `from-index-date` 补漏，其结果约放大 100 倍：Nature Methods 自 2026-09-01 起 index 3,223 条、update 63 条、created 32 条。因此补漏同时叠加 `from-created-date ≥ now − L`（L 初值 30 天 ⚠），只捞"创建较早、上周才可见"的记录，L 之外的迟到记录由季度快照对账兜底；放大系数只有这一个样本，V0 实测后再定补漏预算（§5.4）；更正与撤稿：在同一 venue、前缀或 member 端点上加 `update-type:retraction` 与 `from-update-date` 过滤（single 池），不打全局 `/works` 列表池（SI-02）；SSRN 必须用 created，用 posted 得到 0 条；兴趣集中的出版方可改用 member 流（由 04 按 SCD 成本选择） | [AG §2.2.1][AG]、[LS §2.2.5][LS]；SI-13 |
| arXiv | OAI-PMH `ListRecords`，`metadataPrefix=arXiv`（带逐篇 license）；需要区分新稿与更新时取 `arXivRaw` | `from` = 上次水位减 1 天（日粒度；datestamp 为最后修改时间）；按 arXiv id 去重 | 日历型：周日至周四 20:00 ET 公告，OAI 约 22:30 ET 可取，2026 年有 9 个节假日 | set 粒度由 WatchKey 编译决定，兴趣覆盖面大时退到 archive 级以节省请求；物理 set 须带 `physics:` 前缀；全平台 1 次/3 秒、单连接；识别 429 与伪 200 "Rate exceeded." | [NS §2.3.5][NS]、[CS §2.6.1][CS]、[CS §2.1.1][CS] |
| Europe PMC | `search?query=FIRST_IDATE:[d1 TO d2]`，可叠加 `SRC:PPR`、ISSN、MeSH；配 `cursorMark`，pageSize 1000 | 日窗加 1 天重叠；按 PMID、PMCID、DOI 去重 | 连续 | 请求间隔 ≥10 s；`FIRST_IDATE:[2026-09-24 TO 2026-09-25]` 全库共 3,295 条，其中 `SRC:PPR` 1,179 条 | [LS §2.3.3][LS]、[AG §2.2.10][AG] |
| PubMed | E-utilities `esearch` 按 `[edat]` 日窗；bulk 为 updatefiles（约每天 2 个文件） | 日窗加 1 天重叠 | 连续 | eutils 与 ftp.ncbi 主机的 robots 均为 `Disallow: /`：NCBI 书面确认（并在 robots ADR 附表登记）之前不调用，确认后只做低频 on_demand（补查单个 PMID）；后台增量由 EPMC `SRC:MED` 承担（简报 R2-13；§6.8） | [LS §2.3.1][LS]、[AG §2.2.11][AG] |
| bioRxiv、medRxiv | Crossref `member:54368` 或 owner prefix `10.64898`，`type:posted-content` | created 游标，重叠 3 天 | 连续 | 一次查询覆盖新旧两种 DOI 字符串（`prefix:10.1101` 已查不到预印本）；`/details` 返回 200 空体，不依赖；EPMC `SRC:PPR` 作替补；RSS（crawl-delay 10）只作信号 | [LS §2.2.1][LS] |
| PsyArXiv、OSF、SocArXiv | Crossref 前缀 `10.31234`、`10.31235` 等（COS 名下共 23 个前缀），posted-content | 同上 | 连续 | OSF API 主机的 robots 全禁，needs_confirmation；每个版本一个 DOI（`_vN`） | [LS §2.2.3][LS]、[AG §2.2.17][AG] |
| ChemRxiv 等预印本长尾 | Crossref 前缀：10.26434、10.21203、10.20944、10.22541、10.31223、10.36227 等 | 同上 | 连续 | 版本后缀形态不同（`/vN` 与 `.vN`），写成解析规则 | [NS §3][NS] 第 14 条、[CS §2.1.1][CS] |
| OpenReview | API v2 `notes?content.venueid=…&mintmdate=…`；新一届由 `groups?id=active_venues` 的差集发现 | `mintmdate` 水位 | 日历型（会期） | 需要账号；平台服务账号须书面确认（简报 §7-12），确认前平台侧共享收割停用，ICLR、TMLR、COLM 等由 arXiv 版本 + DROPS dblp 快照 + 外链到 OpenReview forum 兜底（简报 R2-20）；限流头按每次请求读取，已见 `20;w=60` 与 `180;w=60` 两档 | [CS §2.6.2][CS] |
| PMLR、CVF、NeurIPS、ACL Anthology、JMLR | 分别为：首页卷表 diff 加卷号探测；会议年目录页；年页（含新 track）；GitHub 数据仓库或 `acl-anthology` 包；RSS | 卷号、年份、仓库 commit | 日历型 | ICML 的最新一届在 PMLR 上线前走 OpenReview；NeurIPS 2025 新增 Position Paper 与 Creative AI 两个 track | [CS §2.1.2][CS] |
| dblp（快照，`bulk_snapshot`） | DROPS 月度 `dblp-YYYY-MM-01.xml.gz`，附 md5 | 快照版本（有 DOI） | 日历型（月） | 在线主站全禁；只作 venue 与届的目录、作者 PID 的底座 | [CS §2.1.4][CS] |
| INSPIRE、zbMATH、APS Harvest | 分别为 `sort=mostrecent`；OAI `from`（秒粒度）；`from/until/date=modified&set=openaccess` | 时间水位 | 连续 | INSPIRE 每 IP 每 5 秒 15 次；zbMATH 要求合理速率；APS Harvest 的 OA 集免认证 | [NS §2.3.1][NS]、[NS §2.3.3][NS] |
| 央行与国际组织 WP | Fed、ECB、BIS 的 RSS（guid 集合差分）；IMF 走 Crossref 10.5089，按 container 过滤掉 component 与 chapter；World Bank D&R API（`sort=docdt&order=desc`） | guid 集合或时间水位 | 连续 | ECB 的 DOI 由欧盟出版局 RA 登记，不在 Crossref，只能走 RSS；BIS 的 CB-RSS 可做成通用央行解析器 | [SS §2.4][SS] |
| NBER | back.nber.org RSS（Crawl-delay 10）加 Crossref 10.3386 | guid 集合（v1 `IdSetDiff`）加 created | 连续（周更） | Crossref 摘要为 0；周更元数据文件须授权，needs_confirmation | [SS §2.4][SS]、[v1-09][v1-09] §5 |
| OpenAlex | 免费档只能按 `publication_date` 窗口；`from_created_date` 与 `from_updated_date` 需付费计划 | 窗口，加季度快照对账 | 日历型（季度） | 不作最新论文的主通道，只作补查与快照底座 | [AG §2.2.2][AG] |
| S2 | Datasets diffs（需 key） | 版本对 | 日历型（周） | 嵌入与 TLDR 的批量来源 | [AG §2.2.3][AG] |
| 仓储（OAI） | `ListRecords` 加 `from` | 秒或日粒度，加重叠 | 连续 | Zenodo 的 resumptionToken 约 2 分钟过期，必须即取即续；CogSci（eScholarship）的 token 24 小时过期 | [AG §2.2.16][AG]、[LS §2.5][LS] |

### 10.5 本地底座：快照导入与兴趣并集

| 快照 | 规模与节奏 | 许可 | 导入方式 | 状态 | 依据 |
|---|---|---|---|---|---|
| OpenAlex 季度快照 | 2026-09 版约 6.26 亿条记录；JSONL 压缩约 745 GB（其中 works 约 615 GB），Parquet 约 770 GB；每年 1、4、7、10 月的第二个周三发布，下一次 2026-10-14；按 `updated_date` 分区；自 2026-09-23 版起公共桶包含 works 删除日志 | CC0 | S3 匿名下载 → 按兴趣并集过滤 → upsert；按删除日志清理 | 首个里程碑即可用 | [RT §2.2][RT]、[AG §2.2.2][AG] |
| Crossref 年度公共数据文件 | 2026-03-17 发布，约 1.8 亿条，压缩后 208 GB | 书目事实按 CC0 口径；摘要保留版权 | Academic Torrents 或 AWS requester-pays → 策展 venue 的全史回填 | 首个里程碑即可用 | [AG §2.2.1][AG] |
| DROPS dblp 月度快照 | `dblp-2026-09-01.xml.gz` 共 1,099,942,087 字节、12,928,181 条记录，附 md5 | CC0 | 每月 1 日后下载并校验 → venue、届目录与作者 PID | 首个里程碑即可用 | [CS §2.1.4][CS] |
| PubMed baseline 与 updatefiles | 2026 版为 pubmed26n0001–1334，每年 12 月发布；日更约每天 2 个文件 | NLM 条款：须致谢，须保持最新或声明非最新 | 所在主机 robots 全禁 → 等待 NCBI 书面确认与 robots ADR 登记（简报 R2-13；`bulk_snapshot` 族） | 延后（§19 第 1 条） | [LS §2.3.1][LS]、[AG §2.2.11][AG] |
| 其他 | OpenCitations dump（CC0）；ROR dump（CC0）；DOAJ 期刊 CSV（CC0）；S2 Datasets（需 key；ODC-BY；SPECTER2 嵌入为 Apache-2.0）；PwC 存档（CC BY-SA）；allofplos；eLife XML；ACL Anthology 数据仓库；PMC S3（逐篇文件，加每日 inventory） | 各异 | 按需 | 分批接入 | [AG §3][AG] 第 2 条 |

```python
# 设计伪代码 —— 兴趣并集（InterestUnion）与快照子集导入
@dataclass
class InterestUnion:
    venue_ids: set[VenueId]          # 全部策展 venue，加任一用户关注的 venue
    openalex_sources: set[str]       # 由 venue_ids 经 VenueKey 展开得到的 OpenAlex source id（快照行按它过滤）
    issns: set[str]                  # 同上，展开为全部历代 ISSN（Crossref 年度文件按它过滤）
    topic_ids: set[TopicId]          # 全体用户频道与画像涉及的 TSRG 节点（04），加兄弟节点作为探索缓冲
    arxiv_categories: set[str]
    prefixes_members: set[str]       # WP 与预印本的 DOI 前缀、Crossref member
    author_keys: set[AuthorKey]      # 关注的作者（ORCID、OpenAlex A、dblp PID）
    seed_neighborhood: set[WorkKey]  # 种子论文的 1 跳引文邻域；种子来源受下方约束
    floor: FloorRule                 # 例：P0 venue 近 N 年的全部 work（N 为配置项）
    version: str                     # 并集版本；corpus 中只记它，不记"哪个用户的哪项兴趣"导致了导入

def snapshot_filter(row: SnapshotWork, u: InterestUnion) -> bool:
    return (row.openalex_source in u.openalex_sources          # OpenAlex 行带 source id；Crossref 年度文件行改用 ISSN
            or overlaps(row.issns, u.issns)
            or overlaps(row.topic_ids, u.topic_ids)
            or overlaps(row.categories, u.arxiv_categories)
            or doi_prefix(row.doi) in u.prefixes_members       # 快照行不带 owner prefix：这里按 DOI 字符串前缀
            or row.crossref_member in u.prefixes_members       #   宽松包含（多导入无害），只决定导入范围，不用于路由与身份
            or overlaps(row.author_keys, u.author_keys)
            or row.key in u.seed_neighborhood
            or u.floor.matches(row))

def on_union_grow(delta: InterestUnion) -> None:
    # 新增兴趣：体量小时，用 OpenAlex API 按 topic 与 publication_date 列表补拉（每页 $0.0001）；
    #          体量大时，在最近一次快照上重扫。两者进入同一条 normalize → identify 流水线。
    # 兴趣收缩：不删除已入库的 work（回收策略由 05 定）。
    ...
```

**兴趣并集的隐私约束**（HC-01、HC-30）：兴趣并集由用户私域数据（频道、画像、文献库）汇总而来，但它只决定"导入哪些公开元数据"，不把任何私有内容写进共享层。为此：
- corpus 中的记录只记 `interest_union_version`，不记是哪位用户、哪项兴趣触发了导入；
- 粗粒度键（venue、主题、类目、前缀）直接并入；
- 细粒度键（具体论文的引文邻域、具体作者）只从公开或用户主动公开的种子派生，例如 ORCID 本人作品、公开的 DOI 列表；
- 由私有文献库或私有导入派生的细粒度键，须有至少 `k_cf` 个不同用户共有才并入平台收割，否则只做该用户的按需查询（简报 R2-19；08 HC-30；未达门槛的键以带密钥的哈希在本人 `usr` 行计数，04 §11.1）。未并入时，这位用户的私有条目照常只在私域中与已有语料匹配（§7.8）；
- 私有导入的题录本身（如 CNKI 导出）永不作为快照过滤键或 API 补拉的查询条件。

- **容量约束**：简报 B-04 给出起步语料约 100–300 万个 work、日新增收割 1–3 万。兴趣并集的规模须在这个目标之内；超出时先收紧 `floor`，例如缩短年份窗口。容量规划由 [05][05] 负责。
- **快照存放**：下载的原始快照放在冷存储，供季度内重扫。是否保留紧凑投影（例如只含 id、主题、source、年份、标题与倒排摘要的 Parquet）及其体积，由 05 结合容量决定，本文不给数字。

### 10.6 normalize 规则

1. **DOI**：小写；去掉 `https://doi.org/` 与 `doi:` 前缀；沿用 v1 `ids.normalize_doi` 作为唯一入口（[v1-AGG][v1-AGG] §6）。
2. **arXiv id**：拆出基础 id 与版本号；兼容旧式 id。
3. **ISSN**：规范连字符并校验校验位；映射到 VenueKey（§2.3）。
4. **日期分语义保存**，不合并成一个"日期"：
   - `created`、`indexed`、`published-online`、`published-print`、`posted`、`issued`；
   - `first_idate`（EPMC）、`edat`（PubMed）、`oai_datestamp`（最后修改）、`announced`（arXiv）；
   - 平台自己记录 `first_seen_at`。
5. **标题与摘要**：去掉 HTML 与 JATS 标签，**原样保留 LaTeX**（29% 的 arXiv 摘要含公式，[PU §2.3.1][PU]）。OpenAlex 倒排索引还原为文本，标记 `reconstructed=true`，权利为 B 类。
6. **许可**归一为 `license_code`：
   - 取值用 08 §3.4 与 05 `corpus.license` 的规范码：带版本的 SPDX 码（`CC0-1.0`、`CC-BY-4.0`、`CC-BY-SA-4.0`、`CC-BY-NC-4.0`、`CC-BY-NC-SA-4.0`、`CC-BY-ND-4.0`、`CC-BY-NC-ND-4.0` 等），加 `x-` 前缀的非 SPDX 码：`x-public-domain`、`x-arxiv-nonexclusive`、`x-publisher-tdm`（Crossref 中的 Elsevier、SAGE、T&F 等 TDM 许可）、`x-pmc-tdm`（PMC 作者手稿）、`x-no-reuse`（bioRxiv）、`x-free-to-read`、`x-subscription`、`x-other-oa`、`x-unknown`；
   - 上游原始写法（如 `arxiv-nonexclusive-1.0`、`publisher-tdm`、`unknown`）经 05 的 `corpus.license_alias` 归一，mapper 不自造新码；
   - 附带 `content_version`（vor、am、tdm）、`delay_in_days`、`start`，对应 Crossref 的 license 字段（[LS §3][LS] 第 3 条）。
7. **类型**：映射到规范类型，包括 journal-article、posted-content（预印本）、proceedings-article、book-chapter、report（WP）、dataset；IMF 的 component 与 chapter 丢弃。
8. **关系声明**，包括：
   - Crossref 的 `is-preprint-of`、`has-preprint`、`has-version`、`is-version-of`、`update-to`；
   - arXiv 的 `journal_ref` 与 `doi`；bioRxiv 的 `published`；EPMC 的 `HAS_PUBLISHED_VERSION`；OSF 的 `attributes.doi`；DataCite 的 `relatedIdentifiers`。

   这些只作关系，不作身份（§9.2）。
9. **分类声明**，每条都带 `label_source`：OpenAlex topics（含分数）、arXiv 类目、MeSH、JEL（RePEc、NBER）、MSC（zbMATH）、PhySH（APS Harvest）、ACM CCS、bioRxiv subject、OSF subjects。
10. **venue 解析**：见 §2.3。
11. **署名与时效**：按源的 `attribution` 与 `storage_policy` 给记录打标签，展示层据此渲染（CP HC-24）。

### 10.7 index 与 percolate 的交接

- **出箱事件**（主题名按简报 R2-07 统一为 `corpus.change`，由 identify 段在同一事务写出，05 §3.1.2）：`corpus.change {work_id, cluster_id, reason(new | update | merge | split | retraction), changed_fields[], version_ids[], topic_ids[], venue_ids[], first_seen_at}`。至少投递一次，消费方幂等。索引器（04）与 Percolator（04 与 06）订阅这些事件。
- **percolate 的触发**：index 提交后，把本批中以下两类 Work 交给 Percolator：
  1. 新 Work（`reason=new`）；
  2. 已有 Work 新增了 Version，或 venue、主题等参与匹配的字段发生变化（`reason ∈ {update, merge}`，且 `changed_fields` 含 `versions`、`venue_ids` 或 `topic_ids`）。Percolator 用新增 Version 的属性（venue、日期、类目）重新求值。

  第 2 类不可省。反例：一篇论文先以 arXiv 预印本入库，成为 Work W，但不匹配关注期刊 J 的频道；半年后 J 的正式版到达，经 `version_of` 并入 W。若只处理新 Work，W 不会再被求值，关注 J 的用户永远收不到这篇"J 的最新论文"。

  Percolator 按 04 §12 的三路匹配找出用户，写入 05 的 `usr.feed_inbox`（`user_id, offer_id, work_id, push_reason, channel_id, score, expires_at`）。该表只追加、不设唯一约束，读取时按 `work_id` 去重并跟随 `merged_into`（05 §3.2.5、04 §12.1），所以同一用户视图中每个 Work 只出现一次。已经收到过该 Work 的用户，由 04 生成"更新通知"（如"已出版"），不是新条目。每用户日预算与每篇曝光下限由 06 定义。
- **撤稿**：`reason=retraction` 的事件让 FeedInbox 中对应条目失效，并提醒已收藏的用户。提醒的形态由 06 与 07 定义。

### 10.8 错误分类学（沿用 v1 并扩展）

| error_class | 来历 | 含义 | 处理 |
|---|---|---|---|
| `transient` | 沿用 v1 | 超时、连接重置、5xx | 在重试预算内指数退避 |
| `rate_limited` | 沿用 v1 | 429、503 加 Retry-After，含伪 200 | 按响应头退避，不计为失败 |
| `challenge` | 沿用 v1（D-030） | 挑战页 | BLOCKED；主机冷却 24 小时；探针告警 |
| `gone` | 沿用 v1 | 404、410 | 标记 |
| `parse` | 沿用 v1 | 解析 0 命中、schema 校验失败 | 隔离该页；canary 标红 |
| `integrity` | 沿用 v1 | 非 `%PDF` 魔数、哈希不符 | 用户侧重下 1 次 |
| `auth_expired`、`no_entitlement` | 沿用 v1，只用于用户侧 | 会话失效、无权限 | 按 §12 处理 |
| `config` | 沿用 v1 | 注册表非法 | 启动期拦截 |
| `policy_denied` | 新增 | 策略引擎不允许 | 不执行，记审计 |
| `needs_confirmation` | 新增 | 需要书面确认 | 按 §6.4 处理，不重试 |
| `empty_body` | 新增 | 200 空体，或计数骤降 | 端点降级，切换替补链 |
| `budget_exhausted` | 新增 | 美元额度或配额用尽 | 延后到下一个预算窗口 |

### 10.9 新鲜度与吞吐（设计目标，待压测校准）

| 指标 | 目标 | 说明 |
|---|---|---|
| arXiv 公告到进入 FeedInbox | OAI 可取后 ≤2 小时 | 受全平台 1 次/3 秒约束；兴趣类目较多时以 archive 级 set 节省请求。OAI 约在公告后 2.5 小时可取（20:00 ET 公告，约 22:30 ET 可取），折合公告后约 4.5 小时，满足 01 的 NFR-12（公告后 ≤6 小时） |
| Crossref 委托期刊的新 DOI 入库 | DOI created 后 ≤24 小时 | 轮询频率由 04 按 λ 分配 |
| EPMC 新记录入库 | FIRST_IDATE 次日内 | 请求间隔 ≥10 s |
| 季度快照的子集导入 | 发布后 ≤7 天完成 | 冷存储加批处理 |
| 单批 harvest 到 percolate | p95 ≤30 分钟 | 不含等待上游公告的时间 |
| 日新增收割 | 1–3 万个 work | 简报 B-04 |

**估算依据**（⚠ 均为估算，待 AC-V2.41 实测校准）：
- **arXiv**：类目级 set 去重后共 174 个（[NS §0][NS] 第 3 条），WatchKey 编译出的 set 不会超过这个数；按每个 set 每日 1–3 页计，合计约 170–520 次请求，全平台每 3 秒 1 次，需 9–26 分钟，落在"OAI 可取后 ≤2 小时"之内。cs 大类 2026-09-21 至 25 的日记录数为 963–2,272 条（[CS §2.6.1][CS]），单类目的页数不高。关注类目增多到逼近上限时，按 §19 第 6 条退到 archive 级 set。
- **Crossref**：以数千个 venue 的起步量级（04 §5.1 的 Venue 行）估算，按 5,000 个 venue、平均 2 个 ISSN、每日轮询 1 次计，约 1 万次请求/日；polite single 池 10 次/秒时约 17 分钟。每周补漏按 §5.4 的叠加过滤执行，不会放大到约百倍。
- **EPMC**：`FIRST_IDATE` 日窗全库约 3,300 条（[LS §2.3.3][LS]），pageSize 1000 时约 4 次请求；Crawl-delay 10 秒不构成瓶颈。

---

## 11. enrich（⑩）

### 11.1 任务与触发

| 子任务 | 触发层（[PU §2.6.7][PU]） | 输入 | 输出 | 共享条件 |
|---|---|---|---|---|
| `license_resolve`、`oa_vote` | T0（入库时） | 多源许可与 OA 字段 | `item_license`、OA 四态中的公共部分 | — |
| `abstract_fill` | T0；T1 时补 | §8 补齐链 | 摘要变体 | 按 §8.4 |
| `topics` | T0 | OpenAlex topics、原生分类、嵌入 | 主题标签（带来源与置信度） | 是 |
| `embedding` | T0 或 T1 | 标题加可用摘要 | 向量（版本化） | 输入须满足 §8.4 |
| `citations` | T0 | OpenCitations、OpenAlex、Crossref | 引文边（按来源） | 是（CC0 或事实） |
| `badges` | T0 | 撤稿、评审评估、DOAJ、名录 | 徽章与评审状态 | 是 |
| `links` | T0 或 T1 | 摘要或 comments 中的正则、HF、PwC 存档 | 代码与数据链接 | 是 |
| `card_pack`（A 包） | T1：进入任一用户的候选集 | 只接受 `public_shared` 输入 | EN 与 ZH 的 TL;DR、中文标题、关键词 | 过三道闸后进共享缓存 |
| `translate`、`key_figure`、`highlights` | T2：打开详情时 | 只接受 `public_shared` 输入（CC 许可全文） | 中文摘要、关键图、结构化要点 | 同上 |
| `shareable_fulltext` | T2，或候选 Top-N | 许可白名单内的 OA 全文 | 共享 OA 资产加抽取文本 | CP HC-05 |
| 私有派生 | T3（用户侧） | 用户私有全文 | 私有 TL;DR、要点、嵌入 | 永不进共享层（P-02）。platform 部署的服务端 T3 默认关闭，由 pc-agent 或本地模型在用户侧生成（08 §5.4）；并按来源的 `license_policy.derivation.private_llm` 门控（§12.7） |

T1 的触发信号"进入候选集"由 [06][06] 发出。卡片字段怎样取舍、怎样展示，由 [07][07] 定义。

### 11.2 主题标注

1. **取源**：从快照或 API 记录中直接取 OpenAlex 的 `primary_topic` 与 `topics`（最多 3 个，带分数）（[RT §6.2][RT]）。
2. **补标**：约 12% 的 work 没有 topic（2026 年中为 3.22 亿中的 3,960 万）。
   - 主方案：用 OpenAlex 已标注 work 的嵌入，求出每个 topic 的质心；对无 topic 的 work 取最近的若干 topic，经 softmax 得到分布（[RT §3.5.2][RT]）。
   - 可选：自托管 OpenAlex 开源的标题加摘要分类器（Apache-2.0）。它的 4,516 类 top-1 训练准确率只有 0.4846，只能作召回特征，不作卡片标签（[PU §2.4.1][PU]）。
   - **不依赖 OpenAlex 的 `/text` 端点**：它已被标为 deprecated（简报 §6.6）。
3. **原生分类叶子**：arXiv 类目、MeSH、JEL、PhySH、ACM CCS 作为标签随记录保存，带 `label_source` 与置信度；MSC2020 码同样作为记录标签保存，但不作 TopicNode 默认叶子，只在可选插件开启时挂到 TSRG（简报 R2-22）。它们挂到 TSRG 节点的映射由 [04][04] 维护，可参照 Science Data Lake 的"嵌入加人工校验"对齐法（[RT §6.2][RT]）。
4. **许可**：MSC2020 为 CC BY-NC-SA，作可选插件、任何部署默认不加载，显式开启后仍受商用门控（R2-22；08 §10.6）；PhySH 为 CC0；Cognitive Atlas 为 CC BY-SA 3.0 US（[NS §0][NS] 第 9 条、[LS §2.6][LS]）；MeSH 须标明年度版本并致谢 NLM。ACM CCS 与 JEL 词表的许可调研未核验 ⚠（[PU §2.4.1][PU] 只写"各异"）：核验前只把分类码当作记录上的事实标签使用，不再分发词表文本，引入前按 B-06 复核。
5. **展示**：卡片最多显示 3 个标签，使用受控词表的中英文名（OpenAlex subfield 或 field 级，或学科体系），不显示 4,516 级 topic 的长名（[PU §2.4.4][PU]）。
6. **用户反馈**：对标签的纠正作为信号交给 06 与 04。只有聚合、去标识且满足 `k_cf` 个不同用户的反馈，才会改写共享标签（CP DI-03；08 HC-30；简报 R2-04）。

### 11.3 嵌入

- **模型**：按简报 Q7，在 V1 里程碑做分学科评测（每学科 ≥200 条金标）后定型。候选：
  - gte-large（MIT）；
  - Qwen3-Embedding-0.6B（Apache-2.0，多语）；
  - SPECTER2（`specter2_base` 为 Apache-2.0；adapter 许可 ⚠）。

  非商用许可的模型不进默认路径（简报 B-06）。
- **存储契约**：
  - 每行形如 `(work_id, model_id, model_rev, input_basis, dim, vector, created_at)`；
  - `input_basis` 记录输入构成，例如 `title`、`title+abstract:open`、`title+abstract:publisher_copyright`，用于 LQ-02 结论改变时的定点重建（§8.4）；
  - 向量以 `halfvec` 存放，索引结构由 [04][04] 定义。
- **版本化与双写**：换模型时新旧版本并存，双写到切换完成；检索与推荐须显式指定 `model_id`（[RT §12][RT] 第 10 条）。
- **零成本起步**：若选定 SPECTER2 族，可先导入 S2 数据集中已有的 SPECTER2 嵌入（1.2 亿条，Apache-2.0，需 key）（[AG §0][AG] 第 4 条）。这些向量由 S2 用它取得的摘要算出，本文无法区分输入是 A 类还是 B 类摘要，因此记 `input_basis=title+abstract:third_party_s2`，关闭 `policy.index_b_abstracts` 时与 B 类同批回退（§8.4）。
- **私有嵌入**：用户私有全文的嵌入只存在于 usr 域，永不进入共享索引（P-02）。

### 11.4 可共享的 TL;DR 与翻译

- **输入闸**：只接受 `public_shared` 输入，即 `open` 摘要或 CC 许可全文。ND 许可不做改写与翻译；NC 许可只在非商业部署时可用。B 类摘要在 LQ-05 有结论前不得作为输入（简报 P-02）。
- **机器可读保留**：输入前检查 Content-Signal `ai-input`、TDMRep、robots 中的 AI 规则，有保留的不输入（CP HC-11(b)）。
- **生成**：用一次调用产出 A 包（EN 与 ZH 的 TL;DR、中文标题、关键词、claim_type、hedged），批处理，放在谷时运行。选低幻觉的非推理小模型（[PU §3][PU] 第 4、6 条）。LLM 不进交互热路径（P-07）。
- **三道闸**：
  1. 规则闸：核对数字、实体、限定语、LaTeX；
  2. NLI 闸：MiniCheck-FT5（MIT）或 HHEM-2.1-Open（Apache-2.0）；
  3. 抽样 LLM 裁判加人工审计。

  不过闸即降级为原文首句（SI-61；[PU §2.7][PU]）。上线门槛用 600 篇双语黄金集。
- **输出约束**（CP HC-11(e)(f)，规则闸逐条检查）：
  - 长度不超过 07 为卡片字段定的上限：中文 ≤60 字、英文 ≤100 字符（07 §8.2、附录 B；07 §23 X-17）；规则闸按此校验，A 包提示词按此生成；
  - 不复述原句：与源文本的最长公共 n-gram 超过阈值即不过闸，阈值待 LQ-05 量化，⚠ 起步从严；
  - 永不替代作者摘要：卡片同时提供"展开原摘要"或原文链接，TL;DR 只作补充；
  - 不把生成的论断归到作者或期刊名下：不用"作者声称""本刊报道"一类句式，由规则闸检出。
- **模型与许可**：自托管的生成模型与 NLI 模型须过 B-06 的许可门禁（简报 R2-01 的四级分级，08 §10.6），社区许可或 NC 权重不进默认路径。这是只处理开放内容的论文侧预处理，按简报 R2-45 可用第三方 API：只送 `public_shared` 输入，须为零保留条款、非中国境内路由；T1 默认不配 GPU。数据出境与境内备案按 08 的路由规则（CP HC-12、HC-22）。
- **成本**：卡片基础包每千篇 $0.059（gpt-5-nano Batch）至 $3.44（Claude Sonnet 5 标准价）（[PU §2.6.3][PU]）；按日新增 3 万、候选比例 30% 的场景，月成本约 $26–806，随模型而定（[PU §2.6.4][PU] 的 S3 场景）。成本不是瓶颈，模型按忠实度、合规与延迟选型。
- **缓存键**：字段 ∥ 语言 ∥ 源文本哈希 ∥ 源版本 ∥ 模型 ∥ prompt 版本 ∥ 策略版本。以下情况触发重算：新版本（arXiv vN+1、勘误、撤稿）、许可变更、prompt 或模型升级（[PU §2.6.7][PU]）。预印本与正式版的摘要哈希相同时，共用 A 包。
- **S2 TLDR**：作为零成本的 T0 兜底与对照。它为 ODC-BY，须署名"Semantic Scholar"。覆盖按学科差异极大：cs.CL 与 cs.CV 为 92–98%，hep-th 为 0%（[PU §0][PU] 第 2 条）。
- **AI 标识与路由**：显式与隐式两种标识，样式由 07 与 08 定义；LLM 路由，包括境内用户的备案模型与私有全文不外发，由 08 定义（CP HC-11、HC-12）。

### 11.5 质量徽章、撤稿与评审状态

| 信号 | 来源 | 用法 |
|---|---|---|
| 撤稿、更正 | Crossref `update-to` 与 `update-type:retraction`（含 Retraction Watch，CC0；只在 venue、前缀、member 端点上查询）；OpenAlex `is_retracted`；PMC `is_retracted`；PubMed 出版类型 | 硬性可见性过滤（由 06 执行）加徽章；已收藏用户收到提醒（06、07） |
| 评审评估 | eLife Assessment（significance 5 级 × strength 6 级）；EPMC `HAS_VERSION_EVALUATIONS` | 作为有序特征与徽章（[LS §3][LS] 第 8 条） |
| 评审状态 | 新鲜度阶梯：预印本、已接收（OpenReview 接收态、会议 OA 平台已上线）、已出版（有 VoR） | 卡片 P0 字段"评审状态"（07） |
| 收录与名录 | DOAJ 收录；UTD24、CCF、ICORE 等名录的成员资格 | 标签（许可按 §7.4、§7.6） |

### 11.6 OA 状态与许可裁决

- **许可**：多源投票——arXiv OAI 的 license、Crossref 的 `license[vor]`、PMC 的 `license_code`、OpenAlex 的 `best_oa_location.license`、arXiv HTML 页上的许可行。**取最严的结论，未知即拒绝**（SI-60；[PU §3][PU] 第 9 条）。许可闸的精度是 P0 验收项（§17）。
- **OA 四态**（[UX §2.6][UX]）：
  - 可读（OA）；
  - OA 版本（仓储）；
  - 需订阅（用你的凭证）；
  - 不显示（未知）。

  前两态与"未知"由平台公共计算，依据 OpenAlex 与 Unpaywall 的 OA 位置、DOAJ、venue 白名单（纠正 OpenAlex 的误判，例如把 JMLR 判为约 1% OA）、单篇许可。"需订阅（用你的凭证）"一态**只在用户侧或用户私域计算**，不跨用户共享（CP HC-02）；数据来源只限用户自报的订阅配置与本人历史回执，**禁止为计算这一态而探测出版商站点**，那等同于系统性访问（08 §5.1.6）。配方中的 `entitlement_probe` 步骤只在用户显式触发的单篇取回中执行（§12.4）。
- 物理存储：05 `corpus.work.oa_state` 取 `oa_shared`（共享层已有白名单全文）、`oa_link`（OA 副本外链）、`closed`、`unknown`，与上面的公共三态对应；"用你的凭证"不落 corpus。

### 11.7 引文

引文边来自三个来源：OpenCitations（CC0）、OpenAlex 的 `referenced_works`、Crossref 中存缴的参考文献。按来源分别记录，不合成一个计数。

同一 DOI 的被引数在不同来源间并不一致，例如 OpenCitations 为 9,262，OpenAlex 为 10,801（[AG §2.2.9][AG]）。图上的算法由 [04][04] 负责。

### 11.8 代码、数据链接与社区信号

- **代码链接**：综合以下来源，经 GitHub API 校验后保存；非 CS 学科的卡片不预留代码位（[PU §3][PU] 第 14 条）。
  - 摘要与 comments 中的正则；
  - HF 的 `githubRepo`；
  - PwC 存档（CC BY-SA，已冻结）；
  - 全文中的 URL。
- **社区信号**：HF Papers 的 upvote 与评论数，作为 06 的开放热度信号。能否长期缓存、能否商用，受 HF ToS 约束 ⚠（[CS §4][CS] 第 6 条）。

### 11.9 共享 OA 全文的取得

- **准入**：取得通道须满足两个条件：
  - 策略允许平台执行（background，或 T2 时的 on_demand）；
  - 单篇许可在白名单内：CC BY、BY-SA、CC0 与公有领域（05 的 `x-public-domain`，如按单篇声明的美国联邦政府作品）；NC 只在非商业部署时允许；ND 只能原样分发，不做共享派生；NC、ND 在 05 `corpus.license` 中属可再分发，限制由 `nc` / `nd` 标志表达（简报 R2-24；08 §3.4）；"免费阅读但未声明开放许可"的全文不进共享缓存（R2-12）（CP HC-05）。判定用 05 的 `app.license_shareable(code, commercial)`，不按字符串猜测。
- **可用通道**：
  - PMC S3（按 `license_code`）、EPMC `fullTextXML`；
  - APS Harvest OA、SCOAP3、allofplos、eLife XML、ACL Anthology（2016 年起）、JMLR、LIPIcs；
  - arXiv 中 CC 许可的条目：优先 HTML，受 arxiv.org Crawl-delay 15 约束，只在 T2 按需取，不批量（CP HC-06；[PU §3][PU] 第 8 条）。按 15 秒间隔，全平台每日至多约 5,760 页（[PU §2.6.5][PU]）；T2 请求超出时排队，详情页先显示无图版本，关键图稍后补上。
  - arXiv 中非 CC 许可的条目：e-print（PDF、LaTeX 源、从中抽取的图与文本）平台不取、不存、不提供，只链接回 arXiv 摘要页（CP HC-06、M15）；这些条目的嵌入与索引只用 CC0 的元数据和摘要。
- **排除**：bioRxiv 的 S3 桶明文"不作为再分发来源"，所以 bioRxiv 的 CC BY 全文只经 EPMC 取得，否则只给外链（[LS §2.2.1][LS]）。
- **抽取**：沿用 v1 stage 5（[v1-12][v1-12]）：pypdf 为基线，GROBID 为可选增强，`consolidate*` 参数一律为 0。若评估 OCR 类抽取器（olmOCR、dots.ocr 等），须先在自有样本上用 olmOCR-Bench 复测，并逐项核对权重许可（[SYN §4.4][SYN] 的"集成"行；SI-68）。关键图须按简报 §7-13 增加 `teiCoordinates=figure`（[PU §1.3][PU]）。私有全文的抽取在用户侧进行（§12）。


---

## 12. 用户侧全文取回（⑪）

### 12.1 原则

1. **平台出口不访问出版商的受限全文主机**（简报 P-03；CP HC-03）。
   - 受限全文只在用户侧取回，执行者二选一：
     - 用户本人浏览器中的 Companion Extension（02 的 U2）；
     - 用户本机的 pc-agent（02 的 U3）。personal 部署只有在声明 `deployment.host_is_user_device=true` 时，才可以在本机执行 `exec_side=user` 通道（[08][08] §5.1.1）。
   - 取回使用用户自己的会话、key 与网络出口。
   - 理由：
     - SERU 把平台与平台员工排除在"授权用户"之外；
     - 服务端代理会造成"会话在数据中心 IP、用户却在别处""多个机构的会话从同一出口发出"等异常。EZproxy 默认规则会据此封禁：24 小时内超过 4 个国家、60 分钟内 IP 变化超过 20 次、每小时传输超过 2 GB（[CP §2.3.4][CP]）。
2. **单篇、显式触发，任何部署都不批量**。
   - 一次用户操作只对应一篇论文。
   - 平台不在后台为用户排队批量取回，也不做"猜你想读就先下载"的预取（08 的 HC-32）。
   - v1 冻结后仍可以作为独立工具在本机运行（简报 B-03），但其批量 `pull/grab` 属于 v1 工具本身，不是 v2 功能；v2 不调度、不编排它（§19 第 10 条）。
   - 唯一例外（简报 R2-48，Could）：personal 部署可提供"仅许可允许的 OA 全文，批量取回到本人私有空间"，以恢复 v1 对 OA 的批量能力。它只取逐篇许可白名单内的 OA 副本（HC-05），不涉及受限全文，沿用 v1 限速纪律；运行在云主机上的 personal 部署改由共享层 `corpus.oa_asset` 承接同一批全文（05 §15 第 11 项、`private_asset.origin = 'oa_batch'`）。
3. **平台不接触凭证与内容**（CP HC-04、HC-01）。
   - 平台下发的取回意图与配方只含公开信息与占位符，凭证只在用户侧解析。
   - 取回结果写入用户私域，平台只收到不含内容的状态码。
4. **不做跨用户复用**（CP HC-02）。
   - 私有文件不做跨用户的内容寻址去重；
   - 不暴露"他人已取回""他人有权限"一类信号；
   - "需订阅（用你的凭证）"一态只在用户侧或用户私域计算（§11.6）。
5. **自动请求遵守 robots，用户在场的导航除外**。
   - 用户侧执行器发出的自动请求（`user_fetch`、`tdm_api`），与平台侧一样要求目标路径的 robots 判定允许（08 的 HC-29 与 R16）。判定由平台的探针生成，随取回意图下发。
   - 目标主机对具名 AI UA 有禁令（站点级，或覆盖全文路径）时，`user_fetch` 同样不签发（08 R11）；`tdm_api` 走出版商的官方 API 主机，不受站点主机上这条规则影响。
   - 只有用户在场的导航（`open_in_tab`，即在出版社页面打开）不受此约束。用户在出版社页面上点扩展按钮"保存当前 PDF"（`activeTab`，只在用户点击时生效，08 §5.1.3）也属于用户在场的操作。简报 R2-18 据此裁定：具名 AI-UA 禁令站点不做扩展代发的 `user_fetch`，只提供"在出版社打开 + 打开后一键保存"（`tab_save`，08 §5.1.1），LQ-19 有结论后再议。
   - 这与 D-014 第 5 条（auth_gated 获取"不受本条限制"）的读法不同，见 §19 第 9 条、第 18 条。
6. **红线不变**（CP HC-26）。
   - 遇挑战页立即停止，并转为 `open_in_tab` 交给用户本人；不求解 CAPTCHA，不绕过付费墙。
   - 不做 UA 伪装的裸抓：要么用官方 API，要么在真实浏览器上下文中操作（[v1-04][v1-04] §5）。

### 12.2 与 02、08 的分工

| 内容 | 定义方 |
|---|---|
| 执行器形态（U2 扩展、U3 pc-agent）、API 面（`/retrieval-intents`、回执）、OAuth 作用域 | 02（§2.4、AD-09、AD-10） |
| 取回意图 RetrievalIntent 与策略包 PolicyBundle 的字段、签名、时效（≤5 分钟）、会话绑定；方式选择规则 R16；robots 判定下发（HC-29） | [08][08] §5.1 |
| **候选方式的生成**：由 SourceSpec 的 fulltext 通道、策略引擎的决定和单篇许可得出，并排序 | 本文 §12.3 |
| **FulltextRecipe**：每个候选方式的声明式取回配方（URL 模板、所需占位符、校验规则、主机白名单），随平台族实例与官方 TDM API 版本化 | 本文 §12.4 |
| 与 v1 认证框架的复用关系 | 本文 §12.6 |
| 私有存储、E2E 同步与私有派生的存放 | [05][05]、[08][08] §5.4；本文 §12.7 只给约束 |

### 12.3 候选方式的生成与排序

对每个 Version，平台计算候选项，映射到 08 的五种取回方式：

| 序 | 本文的选项（`FulltextOption.kind`） | 08 的方式 | 计算依据 | 产物归属 |
|---|---|---|---|---|
| 1 | `shared_oa_asset`：共享层已有的许可白名单 OA 全文（§11.9） | `oa_link`（由平台共享层提供） | 单篇许可在白名单内（CP HC-05） | 共享层 |
| 2 | `oa_location`：OA 位置外链，来自 OpenAlex 或 Unpaywall 的 `best_oa_location`、仓储、arXiv、PMC | `oa_link`（只外链） | OA 位置投票（§11.6） | 用户自己决定 |
| 3 | `user_tdm_api`：用户本人 key 的官方 TDM 或全文 API（Elsevier、Wiley、Springer Nature、APS Harvest 全量） | `tdm_api` | fulltext 通道 `method=tdm_api`；策略决定为 user_side | `per_user_only` |
| 4 | `user_session`：用户本人的机构会话（校园 IP、EZproxy、SSO）加平台族配方（Atypon、Silverchair、HighWire 等） | `user_fetch` | 平台族实例声明了 `fulltext_recipe`；R16 各项成立，且目标路径不命中 R11 的具名 AI-UA 禁令 | `per_user_only` |
| 5 | `link_resolver`：机构链接解析器（OpenURL、WAYFless） | `openurl` | 用户配置了本机构的解析器（⚠ LQ-07） | 用户自己决定 |
| 6 | `publisher_landing`：在出版社打开 | `open_in_tab` | 总是可用；platform 部署未装扩展时的默认动作 | — |
| — | `private_upload`：用户上传本人持有的 PDF | — | CP HC-16 | `per_user_only` |

- **产物归属**：选项 3、4 的产物一律 `per_user_only`，与单篇许可无关。即使是 CC BY，经用户凭证取得的副本也不进入共享层；共享副本须由平台经公开通道自行取得（§3.5）。
- **排序**：跨类按上表顺序，与 08 的 `oa_link > tdm_api > user_fetch > open_in_tab` 一致。同一类内，按 SourceSpec 的通道顺序与该用户最近的成功率排序。成功率只在该用户私域统计，不跨用户汇总（HC-02）。
- **可用面的现实预期**：Atypon 族的 robots 普遍具名封禁 GPTBot，Springer 站点具名封禁 20 多个 AI UA；Silverchair 模板只点名禁 `008`，未见 AI UA 条目（[SS §2.2][SS]）。按 08 R11，Atypon 与 Springer 主机上的选项 4 多半不签发，Silverchair 实例要逐个按 robots 与 ToS 判定。因此对订阅内容，实际可用的常常是选项 3（出版商官方 TDM API，用户本人 key）或选项 6 加用户在场的一键保存。选项 4 只在 robots 与 AI-UA 规则都允许的实例上启用，实例清单随探针结果维护（§19 第 18 条）。
- **候选项的内容**：每个候选项带上策略引擎在签发时对该通道的裁决：
  - `AccessDecision` 的 id；
  - robots 判定、`tos_automation`、`verified_at`；
  - 配方引用（§12.4）。

  签发与签名由 08 的 RetrievalIntent 承载。

### 12.4 FulltextRecipe（声明式配方）

配方是**数据，不是代码**：执行器只解释一套受限的步骤语言，不执行下发的任意脚本。这样一来，配方可以审计、签名、回放；平台即使被攻破，也无法借配方在用户浏览器中执行任意操作。

**建议的承载方式**（字段由 08 定稿）：
- 配方本体随 PolicyBundle 分发并签名；
- RetrievalIntent 的候选项只携带 `recipe: {id, version, params}`。

```yaml
# 设计伪代码 —— FulltextRecipe 示例 1：官方 TDM API（用户 key；默认由 pc-agent 执行）
recipe_id: elsevier.article_retrieval
version: 2
family: official_tdm_api
source_id: elsevier_sd
method: tdm_api
steps:
  - request:
      url: "https://api.elsevier.com/content/article/doi/{doi}"
      headers:
        X-ELS-APIKey: "{user_secret:elsevier.api_key}"           # 占位符，只在用户侧解析
        X-ELS-Insttoken: "{user_secret:elsevier.insttoken?}"     # 可选
        Accept: "application/pdf"
      allowed_host: api.elsevier.com                             # 携密头只发往此主机（沿用 v1 的凭证隔离规则）
  - expect: {magic: "%PDF", min_bytes: 10240}                    # 小于 10 KB 视为疑似拦截页（[v1-04] §4）
on_status:
  "401|403": auth_expired
  "429": {backoff: header, then: stop}
limits: {min_interval_s: 6, daily_cap: 200}                      # 另受每个 key 的书面配额约束
evidence: [ev_elsevier_api_2026-07-20]                           # v1 design/adapters/elsevier-sd.md 的 [LIVE] 勘察
```

```yaml
# 设计伪代码 —— FulltextRecipe 示例 2：平台族（Atypon），用户本人的浏览器会话（由扩展执行）
recipe_id: atypon.pdf_from_doi
version: 3
family: platform_family/atypon
method: user_fetch
applies_to: {instances: ["<robots 与 AI-UA 规则都允许 /doi/pdf/ 的 Atypon 实例>"]}   # 由探针结果维护的实例清单；
                                                                 # informs_pubsonline 因 08 R11 不在其中（§3.6 示例 A）
steps:
  - resolve: {url: "https://doi.org/{doi}", follow_redirects: true,
              allowed_hosts: ["{instance.site_host}"]}
  - entitlement_probe: {kind: link_contains_login, selector_ref: atypon.pdf_link}   # 只在本次显式取回中执行（§11.6）
  - download: {url: "https://{instance.site_host}/doi/pdf/{doi}",
               expect: {magic: "%PDF", min_bytes: 10240}}
requires: {robots_allowed: ["/doi/pdf/"], tos_automation_not: [forbidden],
           ai_ua_blocked_on_path: false}                         # R16 与 R11 的前提，签发时已判定
on_challenge: stop_then_open_in_tab                              # 主机冷却 24 小时
limits: {min_interval_s: 6, daily_cap: 200}
```

**配方语言只有以下步骤**：`request`、`resolve`、`entitlement_probe`、`download`、`expect`、`extract_link`（受限的选择器引用）。

**禁止的动作**：
- 执行下发的 JS；
- 填写表单或登录框；
- 点击验证码或同意按钮；
- 并发请求；
- 访问白名单之外的主机；
- 读取与本次取回无关的 cookie。

**登录**永远由用户本人在出版方页面上完成，执行器不代填（沿用 v1 D-006 的"人在回路首次登录"）。

**配方的维护**：
- 配方随 ConnectorInstance 版本化；
- 每个配方有四类 fixture：成功、无权限、会话过期、挑战，沿用 v1 auth-framework §11；
- 聚合失败率超过阈值时，自动停用该配方的 `user_fetch`，只保留 `open_in_tab`，并通知维护者。失败率只按配方与版本聚合，不按论文、机构或用户拆分；样本数不足 `k_cf` 个不同用户时不计算（HC-02、08 HC-30）。
- **本文建议**：08 的回执状态在 `error` 之下细分 `auth_expired`、`integrity`、`not_found`，以便统计配方健康。

### 12.5 流程中本文负责的步骤

完整流程见 [08][08] §5.1.2，即 fulltext-options → retrieval-intents → 扩展验签与选择 → 回执。其中由本文负责的步骤：

```text
① fulltext-options：平台按 §12.3 生成候选项
     → 对每个候选项调用 policy.decide(op=LOCATE_FULLTEXT)
     → 只读，不签发
② retrieval-intents：为需要用户侧执行的候选项（tdm_api、user_fetch）附上配方引用与签发时的裁决
     → 由 08 签发 RetrievalIntent
④ 执行器按配方执行
     → 占位符在用户侧由本机凭证库解析（§12.6）
⑥ 回执
     → 只进入 usr 域的"取回历史"
     → 配方的去标识失败率进入 ops（§12.4）
```

### 12.6 执行者、护栏与 v1 认证框架

**执行者与凭证所在**：

| 执行者 | 凭证所在 | 会话来源 | 默认承担的方式 |
|---|---|---|---|
| Companion Extension（U2） | 扩展本地的 E2E 凭证库 | 用户浏览器中已有的出版方或机构会话 | `oa_link`、`user_fetch`、`open_in_tab`、`openurl`；key 在扩展凭证库中时也执行 `tdm_api` |
| pc-agent（U3）；personal 部署且 `host_is_user_device=true` 时即部署本身 | 本机 CredentialStore（v1 D-023，AES-GCM）；`.paper-crawler/`（D-032） | 本机浏览器上下文（Playwright `storage_state` 复用，[v1-11][v1-11] §4.3） | `tdm_api`；机构 EZproxy 与 SSO 流程 |
| 无执行者（未安装扩展或 pc-agent） | — | — | 只提供选项 1、2、5、6 |

**护栏**：全部在用户侧执行，按"用户 × 出版平台"计。

| 护栏 | 规则 | 出处 |
|---|---|---|
| 串行与间隔 | 同一平台不并发、不并行多会话；每域最小间隔 6 秒，出版方书面限额更慢时取出版方的 | [v1-04][v1-04] §4–§5；08 的 HC-32 |
| 日上限 | 每个平台每天 ≤200 次尝试，成败都计入（v1 默认；08 §5.1.5），可以下调 | 同上 |
| 会话健康 | 每次执行前检查一次会话（v1 批量模式为每 20 篇或每 15 分钟一次，单篇模式收紧为每次） | auth-framework §8.2 |
| 挑战 | 立即停止，该平台冷却 24 小时，转为 `open_in_tab` | [v1-04][v1-04] §5；D-030；08 §5.1.2 |
| 文件校验 | 魔数须为 `%PDF`；小于 10 KB 视为疑似拦截页（`integrity`） | [v1-04][v1-04] §4 |
| 日志 | 请求级取回日志（时间、URL、字节数）只存于用户侧，作为"个人合理使用"的自证材料 | [v1-04][v1-04] §5 |

**与 v1 认证框架的关系**：

| v1 组件 | v2 用法 | 变化 |
|---|---|---|
| `AuthProvider` 协议，四种实现：`cookie_session`、`ezproxy`、`sso_flow`、`api_key`；五个方法（`ensure_session`、`health_check`、`refresh`、`invalidate`、`rewrite_url`）（auth-framework §2.2） | pc-agent 原样复用；扩展按同一语义实现，其中会话就是浏览器自己的会话，`rewrite_url` 用于 EZproxy 域名改写 | 执行位置从 CLI 进程扩展到扩展与 pc-agent；平台服务端不实现 AuthProvider |
| `CredentialStore`（AES-GCM，D-023；主密钥优先存 keyring） | pc-agent 原样复用；平台服务端**不可解密**（简报 §6.3-3） | 多设备同步只同步 E2E 密文，方案由 [05][05] 与 [08][08] 定义 |
| `profiles.toml`（只存 `key_ref`、EZproxy 改写规则、`active_profile`） | pc-agent 的配置；扩展有等价的本地设置 | — |
| 健康门、日配额、BLOCKED 映射（auth-framework §8.2–§8.4） | 用户侧护栏（见上表） | 单篇模式下健康门收紧为每次执行前检查；工作时段窗（auth-framework §8.6）只针对 v1 批量任务，v2 不用 |
| `ChallengeDetector` 及四类 fixture（auth-framework §11；D-030） | 扩展与 pc-agent 共用特征库；平台侧 PoliteHttp 也用它（§5.5） | 特征库版本随 PolicyBundle 下发 |
| browser-fetch 与 `storage_state` 复用链（[v1-11][v1-11] §4.3） | pc-agent 的浏览器路径 | 只在用户侧运行 |
| `no_entitlement → unpaywall` OA 回退（auth-framework §8.1） | 改为候选排序中的 `oa_location`，由平台预先计算 | — |
| FetchLog（资产取回日志） | 用户侧私有日志；平台侧另有元数据请求的取回日志（§5.5） | 两者分域，不合并 |
| v1 adapter 的 auth_gated 路径：`elsevier_sd`、`wiley`、`oup_silverchair`，以及 `ssrn` 的浏览器全文模式 | 前三者转为配方，由 pc-agent 或扩展执行；`ssrn` 的浏览器全文模式删除（简报 §7-4） | §14.1 |

### 12.7 私有存储、可选上传与私有派生

- **存放**：
  - 扩展：写入用户设备，例如浏览器的私有文件系统，或用户选择的下载目录；
  - pc-agent：写入本机的受忽略目录（`.paper-crawler/`，D-032）；
  - 可选同步（简报 R2-27，覆盖简报 §6.3-3 第三项）：platform 部署默认只存设备本地；用户开启 `features.private_pdf_sync` 后，服务端只存端到端密文、不可解密，服务端私有处理默认关闭（CP HC-16；01 的 FR-85）。`server_envelope`、`dek_ref` 与 `processor='api:<vendor>'` 只在 personal 部署且 `deployment.host_is_user_device=true` 时可用（R2-28）。存储分层、加密与配额由 [05][05] 与 [08][08] §5.4 定义。
- **私有空间的约束**：
  - 只有本人可见；
  - 不做跨用户去重（HC-02）；
  - 注销账号时删除私有全文及其派生物（CP HC-20）；
  - 不接受公共上传或转存（CP HC-16）。
- **私有派生（T3）**：私有 TL;DR、要点、私有嵌入与全文检索，只属于本人，永不进入共享索引、共享缓存或推荐的全局特征（HC-01；简报 P-02）。
  - **在哪里算**（08 §5.4）：platform 部署的私有全文默认只在用户设备上，或以 E2E 密文同步，服务端读不到明文，所以服务端 T3 默认关闭；T3 由 pc-agent 或本地模型在用户侧生成，结果存在用户设备，或以 E2E 密文同步。personal 部署且 `host_is_user_device=true` 时，服务端就是用户本人的环境，可以在服务端的 `usr` 域生成与存放。
  - **按来源门控**：T3 读取 SourceSpec 的 `license_policy.derivation.private_llm`。IEEE 内容为 `forbidden`：IEEE 禁止为 AI 使用创作演绎作品（CP §2.3.1、M10）。Elsevier 为 `needs_confirmation`（LQ-06）：Elsevier 把嵌入流水线与向量库也算作 AI System，只许在为本人服务的封闭环境中使用。未声明的来源默认 `needs_confirmation`。私有嵌入与私有 TL;DR 同样受此门控。
  - **路由**：私有全文送往哪个 LLM，须满足 [08][08] 的路由规则。例如 Elsevier 条款要求 closed hosted（enterprise-grade）端点（CP DI-05），境内用户须用备案模型（CP HC-12）。
  - **保存期**：Springer Nature 的 TDM 语料只在 TDM 项目期间保存（[LS §0][LS] 第 7 条）。执行器为 `official_tdm_api` 来源的私有副本提供到期提醒与一键清除，是否保留由用户决定。
- **题录导入**：用户导入的题录（RIS、BibTeX、EndNote、CSL-JSON）同样进入用户私域（§7.8）。按 DOI 或标题匹配到共享语料的，只在用户私域建立引用，不向共享层回写任何字段（HC-01）。

---

## 13. 新增来源 SOP 与成本目标（⑫）

### 13.1 四条路径

| 路径 | 适用 | 需要做的事 | 成本目标 |
|---|---|---|---|
| A. 零代码 venue | 已登记 Source（出版方或平台）下的新期刊、新 WP 系列、新预印本前缀；即 `crossref_delegated` 或已支持平台族上的 venue | 写一份 VenueSpec v2：`keys` 由工具从 Crossref `/journals/{issn}` 与 OpenAlex source 自动填充；合规字段继承自 Source；跑 lint、dry-run 与 canary | **≤30 分钟**（NFRc-03.3） |
| B. 零代码实例 | 已支持仓储软件或期刊系统上的新实例（DSpace、EPrints、InvenioRDM、OJS 的 OAI 端点） | 写一份实例 YAML：OAI `Identify` 自动取 granularity、earliest datestamp、deletedRecord；为 OAI 主机登记 robots；跑一次小窗口 `ListRecords` 回放 | **≤30 分钟** |
| C. 新 Source，已有族 | 新出版方或新平台，但使用已有族（`crossref_delegated`、`feed`、`platform_family`） | 在路径 A 或 B 的基础上，补 Source 级合规复核：每个主机的 robots；ToS 自动化条款；TDMRep、Content-Signal、AI-UA；许可与署名；商用门控；证据 | 设计目标 ≤0.5 人日（主要是合规阅读），待首批接入校准 |
| D. 新 connector | 有官方 API 或协议、但现有族无法承接的来源（SI-09；§7.9） | 见 §13.3 | **≤2 人日**（NFRc-03.3） |
| 拒绝 | 没有官方通道，且 robots 或 WAF 禁止 | 不写抓取型 connector（DR-2）；登记为 `link-only`、`metadata-only`（经 Crossref）或 `user-import-only` | — |

**用户提议**：用户关注一个尚未策展的 venue 时，系统先以自动 venue 满足元数据与最新论文需求（§2.5），同时生成 `user_proposed` 工单。策展人按路径 A–D 处理，处理结果回写支持名录（[DIR]）。用户提交的**新来源**登记请求（新出版方、新平台、新主机）进入部署方审核队列（01 FR-29）。部署方审核通过之前，平台不向新来源的任何主机产生上游请求，包括 robots.txt，由出口审计验证（简报 R2-23；已登记来源如 Crossref 上的自动 venue 不受此限）；通过后按路径 C 或 D 做合规复核，复核经 Egress Gateway 先取 robots.txt。

### 13.2 零代码路径（A 与 B）的步骤

```text
设计伪代码 —— 注册表工具命令（名称与参数由实现期冻结）
1. registry propose venue --issn 1234-5678        # 从 Crossref /journals 与 OpenAlex source 预填 keys、历代 ISSN、member、owner prefix
   registry propose instance --oai https://…/oai  # 用 Identify 预填实例参数；同时抓取并记录 OAI 主机的 robots
2. 人工核对：名称、学科、VenueEdge 或 HostingPeriod（若有迁移史）、curation 等级
3. registry lint                                   # §3.8 的 13 条规则
4. registry dry-run <id> --window 30d              # 经 PoliteHttp 真实请求，结果录为 fixture；核对记录数与抽样字段
5. registry canary <id>                            # 最新窗口内至少取到 1 条记录，且 venue 解析命中本条目
6. 提交评审（PR）：模板中记录起止时间，用于统计 NFRc-03.3
```

### 13.3 新 connector 路径（D）的两日拆分

| 时段 | 产出 |
|---|---|
| 第 1 天上午 | 证据：官方文档、限额、ToS、robots（每个主机）、TDMRep；写入 `registry/evidence/`。SourceSpec 与 SCD 草稿 |
| 第 1 天下午 | 录制四类 fixture：正常页、空页、限流或错误、边界（最后一页、删除记录、版本变化）；写 Mapper 纯函数与 `normalize` |
| 第 2 天上午 | `plan` 与 `parse`；契约测试（§15.2）、fixture 回放（§15.1）、策略引擎集成（被拒时不发请求） |
| 第 2 天下午 | 探针声明（§6.5）；canary 查询；在名录中登记；评审 |

**前提**：
- 族核心（PoliteHttp、OAI、XREF、FEED 引擎、注册表工具）已就绪；
- 该来源的端点语义不超出通用协议（§5.2）。

超出这些前提的来源，例如需要全新的认证形态，不适用 2 人日目标，须单独估算。

### 13.4 检查清单与评审门

| 门 | 检查项 | 通过标准 |
|---|---|---|
| G1 合规 | 每个主机有 robots 结论；有 `tos_automation`、`tdmrep`、`content_signal`、`ai_bot_sensitivity`；有许可与署名；有商用门控；每项都有证据与 `verified_at` | lint 规则 3、4、7、8、9、12 全部通过；合规字段须经第二人复核 |
| G2 技术 | Schema、SCD、`identifiers_emitted` 的粒度；fixture 回放；P0 来源有 `fallbacks` | lint 全部通过；回放测试通过；dry-run 的记录数与预期相符 |
| G3 上线 | 策略引擎对各通道与各操作给出的决定符合预期；探针完成第一个周期；canary 为绿色 | 状态由 `planned` 转为 `active` |

---

## 14. 与 v1 的关系与迁移

### 14.1 v1 adapter 的去向

五类去向：
- `bridge`（包装）：经 `v1_bridge` 原样运行；
- `bridge_patch`（包装加修补）：修补已知漂移后包装；
- `port`（移植）：把逻辑移植为 v2 族或连接器；
- `user_side_only`（仅用户侧）：转为用户侧配方；
- `retire_online`（在线路径废止）。

v1 维护冻结（简报 B-03），修补只在 v2 的包装层或移植后的代码中进行，不改 v1 仓库代码。

**过渡期**：除 `retire_online` 外，全部 adapter 先经 `v1_bridge` 通过 v2 连接器契约测试（对应 01 的 FR-20 验收）。`port` 类在对应的族引擎就绪后替换；`user_side_only` 类在过渡期以 `pc_agent` 模式运行，只在用户侧执行。

| v1 adapter | v1 角色 | 去向 | v2 承接 | 说明 |
|---|---|---|---|---|
| `arxiv` | 预印本（OAI、API） | bridge_patch | 先包装，后移植为 `oai_pmh` 的 arXiv 实例 | 修补物理 set 前缀、429 与伪 200、逐篇 license 字段；理科方向 v1 只登记了 math.OC，v2 升级为类目级 set 收割（[NS §2.2.2][NS]、[NS §2.3.5][NS]） |
| `crossref` | 元数据主干 | port | `crossref_delegated` 引擎 | 需要暴露响应头（分池与限额）、支持 owner prefix 过滤、处理 container-title 逗号问题（§5.4） |
| `openreview` | 会议评审平台 | bridge | `site_special/openreview`（v2） | 平台服务账号须书面确认（简报 §7-12）；personal 部署沿用用户 token；限流按每次请求读响应头 |
| `pmlr` | 会议论文集 | bridge_patch | `site_special/pmlr` | 新卷发现改为"首页 diff 加卷号探测"（[CS §2.1.2][CS]） |
| `acl_anthology` | 会议论文集 | port | `site_special/acl_anthology`（包形态） | 改用官方数据仓库或 `acl-anthology` 包（[CS §2.1.2][CS]） |
| `cvf` | 会议论文集 | bridge | `site_special/cvf` | ECCV 的全文源改为 ECVA（§3.7） |
| `aaai_ojs` | OJS 期刊式论文集 | port | `platform_family/ojs` 实例 | `quirks.volume_map` 转为 `editions.explicit` |
| `neurips_proceedings` | 会议论文集 | bridge_patch | `site_special/neurips` | 补 Position Paper 与 Creative AI 两个 track（[CS §0][CS] 第 9 条） |
| `unpaywall` | OA 位置 | bridge | `aggregator_api` 补查 | 主要依赖 OpenAlex 的 OA 字段，Unpaywall 只做补查（每天 100k 次，[CP §2.4][CP]；官方页为 JS 渲染，该数值未经一手复核 ⚠，[AG §4][AG] Q9） |
| `dblp` | 会议目录 | retire_online | `site_special/dblp_drops`（快照） | D-037 已将其出列生产链；在线主站 robots 已改为全禁（[RT §12][RT] 第 31 条） |
| `wiley` | 受限全文（TDM API） | user_side_only | `official_tdm_api` 配方 | `Wiley-TDM-Client-Token` 由用户本人持有（v1 `design/adapters/wiley.md`） |
| `elsevier_sd` | 受限全文（Article Retrieval API） | user_side_only | `official_tdm_api` 配方（§12.4 示例 1） | 用户 key；TDM 产出片段 ≤200 字符（CP HC-25） |
| `oup_silverchair` | 受限全文（会话） | user_side_only | `platform_family/silverchair` 配方 | 复用 v1 `CookieSession` 与 `SSOFlow` |
| `openalex` | enrich | port | `aggregator_api/openalex` 加快照导入器（§10.5） | 按美元计费的预算模型；`/text` 不作依赖 |
| `s2` | enrich | bridge | `aggregator_api/s2` | 以后改用 S2 Datasets（嵌入与 TLDR） |
| `aea` | 元数据 resolve | bridge | 元数据经 `crossref_delegated`；全文 link_only | 全文域名恒为 CF 挑战（v1 aea.md §4） |
| `econsoc` | TE/QE（OJS OAI）、ECMA | port | TE、QE 转为 `oai_pmh` 实例；ECMA 转为 HostingPeriod 路由（D-028） | ECMA 的受限全文走 Wiley 用户侧配方 |
| `ssrn` | 预印本元数据 | bridge | 元数据经 `crossref_delegated`（前缀 10.2139，按 created 游标） | 删除浏览器全文 opt-in 模式，全文 link_only（简报 §7-4；取代 D-029 的相关部分） |
| `nber` | WP | bridge | 元数据经 Crossref 10.3386 加 RSS | 全文：许可不在白名单内，平台 link_only；用户可自行打开 |
| `repec` | enrich（bulk 快照） | bridge | `aggregator_api/repec`（零网络的本地 join） | 沿用 D-035、D-036 |
| `mock_platform` | 测试 | 保留 | 契约测试夹具 | — |

### 14.2 模块复用

| v1 模块 | v2 去向 |
|---|---|
| `ids.py::normalize_doi` | normalize 的唯一 DOI 规范化入口（§10.6）。v1 中 `aaai_ojs/parse.py` 与 `acl_anthology/ids.py` 另有同名实现，v2 不沿用 |
| `adapters/_oai.py` | `oai_pmh` 族核心 |
| `http.py`（HttpClient） | 替换为 PoliteHttp；v1 adapter 经垫片接入（§5.4 V1Bridge）；补上响应头上交（§5.5） |
| `ratelimit.py`、`useragent.py` | 由 PoliteHttp 的令牌桶（04）与统一 UA 取代 |
| robots 处理 | v1 没有统一的 robots 闸：7 天缓存是设计约定（[v1-03][v1-03] §3），速率由各 adapter 按 Crawl-delay 自行声明，D-026 规定了 dblp 的最长匹配读法。v2 由 PoliteHttp 统一强制（DR-5），缓存上限改为 24 小时（RFC 9309 §2.4，§5.5） |
| `auth/challenge.py`（ChallengeDetector） | PoliteHttp 与用户侧共用（§5.5、§12.6） |
| `subs/watermark.py`（DateCursor、IdSetDiff） | latest 通道的游标语义（§10.3、§10.4） |
| `merge.py`（SOURCE_PRIORITY，D-021、D-035）、`dedupe_cli.py`、D-031 弱键 | identify 段（§9.4、§9.5）：优先级表扩展为"字段 × 学科 × 源"矩阵；候审语义沿用 |
| `pipeline/extract.py`（D-033） | 共享 OA 全文的抽取（§11.9）与用户侧抽取 |
| `auth/`（AuthProvider、CredentialStore） | 用户侧的 pc-agent（§12.6） |
| `browserfetch.py` | 只在用户侧运行 |
| `canary.py` | 扩展为按通道的 canary 与漂移探针（§6.5、§16） |
| `registry.py`（VenueSpec 加载、lint、路由） | 演进为 v2 注册表加载器与 §3.8 lint，沿用 `extra="forbid"` 与"同目录 id 重复即错"的纪律；v1 文件由 §3.7 转换器迁出 |
| `adapter.py`、`types.py`（SourceAdapter 协议、PaperStub、VenueSpec 类型） | 冻结为 `v1_bridge` 的包装对象；v2 连接器协议见 §5.2 |
| `errors.py`（ErrorClass 与 RETRY_TABLE） | §10.8 的错误分类学以其为底扩展；重试策略交网关的重试预算（04） |
| `pipeline/cooldown.py`、`cooldown_cli.py`（挑战冷却的落盘与查询，D-030 E-1） | 语义迁入网关的主机冷却状态（`ops` 域）与用户侧执行器的本地冷却；键仍按 URL host |
| `pipeline/runner.py`、`pipeline/stages.py`（v1 六阶段的串行编排） | 由 procrastinate 上的六段流水线取代，段的映射见 §10.2；v1 的 fetch 阶段不迁入后台 |
| `pipeline/fetchio.py`（`*.part` 暂存、魔数校验、原子 rename） | 用户侧执行器的落盘路径（§12.6 的文件校验） |
| `preprint_report.py`（preprint↔published 关联报告） | identify 段的关系报告与候审视图（§9.3、§9.4） |
| `obslog.py`、`sensitive.py`（结构化日志与敏感键单一权威源，D-025） | 平台侧与用户侧日志脱敏共用同一份敏感键表（§15.9） |
| `storage/`（SQLite、FTS5，D-034） | v1 冻结；v2 用 PG（B-01），数据迁移见 §14.4 |

### 14.3 对 v1 ADR 的影响（供 09 起草新 ADR）

| v1 ADR | 影响 | 建议 |
|---|---|---|
| D-002 Platform Adapter × Venue Spec 两层结构 | 被 Source、Venue、Connector、Policy 模型扩展 | **建议新增 ADR 候选**："SourceSpec v2 与 Source/Venue 分离"（§19 第 3 条） |
| D-003 open_access 与 auth_gated 双模块 | 由通道的 `exec_side` 取代模块二分 | 并入简报 §7-10（执行位置） |
| D-004 六阶段 pipeline | v2 六段改为 harvest → percolate；fetch 移出后台 | 并入简报 §7-10；同时在新 ADR 中记录段的映射（§10.2） |
| D-005 元数据主干走聚合 API | 延续并加强（DR-1） | 无需修订 |
| D-006 人在回路首次登录与 storage_state 复用 | 延续，执行位置改为用户侧 | 并入简报 §7-10 |
| D-007 Identifier 图加 preprint_of | 细化为 Work/Version/Manifestation；预印本服务器类的版本在同一 Work 内；WP 只建关系 | **建议新增 ADR 候选**："身份模型三层与版本边投票"（§19 第 2 条） |
| D-011、D-029 SSRN 定位 | 删除浏览器全文模式 | 简报 §7-4 |
| D-012 VenueEra 与 DBLP 历史主干，D-038 venue-tracking 整域 defer | 由 VenueEdition、HostingPeriod、演化边与 `ownership` 探针承接；DBLP 改用快照 | 建议在"SourceSpec v2"ADR 中一并取代 D-012，并关闭 D-038 在 v2 中的挂起 |
| D-013 ACM DL 归入 open_access 族；D-020、D-024 | v2 不自动化访问 ACM DL 网站（CP HC-27）；元数据经 Crossref；Wiley 转用户侧 | 由 08 的 HC-27 登记；ADR 中注明取代 D-013 的族归属 |
| D-014 AI-bot 指令与诚实 UA | 延续；补充"文档化 API 与 robots 冲突"和"用户侧单篇操作"的解释规则 | 简报 §7-2（robots ADR） |
| D-021 DBLP robots 修正与聚合优先级 | 优先级表扩展为矩阵；DBLP 部分被快照取代 | 简报 §7-3 |
| D-022 零网络 resolve 不受限速闸约束 | 与 PoliteHttp 一致：零网络步骤不计入令牌桶 | 无需修订 |
| D-023 AES-GCM 凭证库 | 用户侧沿用；服务端不可解密 | 由 05、08 的认证 ADR 引用 |
| D-026 dblp robots 最长匹配 | 推广为 PoliteHttp 的通用规则（RFC 9309） | 并入 robots ADR |
| D-028 ECMA 按年代分段路由 | 表达为 venue 的 HostingPeriod | 无需修订 |
| D-030 Browser-Fetch 与挑战判定 | 挑战判定推广到平台侧与用户侧；浏览器取回只在用户侧 | 并入简报 §7-10 |
| D-031 弱信号键与 tie-break | 沿用（§9.4、§9.5） | 无需修订 |
| D-032 `.paper-crawler/` | personal 部署与 pc-agent 沿用 | 无需修订 |
| D-033 全文抽取 | 沿用；增加 `teiCoordinates=figure` | 简报 §7-13 |
| D-034 FTS5 | 只用于 v1 | 由 04 与简报 §7-5 处理 |
| D-037 dblp 出列 | 由 DROPS 快照取代 | 简报 §7-3 |
| D-039 优先级队列与 backfill defer | v2 用三道舱壁加 EnumerateTask 回填（§10.3）；调度由 04 定义 | 由 04 与 09 处理 |

### 14.4 数据与文档迁移

- **注册表**：v1 的 62 个 VenueSpec（`venues/**`）由确定性转换器迁入 `registry/venues/**`（§3.7）。转换器幂等，可反复运行；转换报告列出每个字段的去向。在 v2 注册表成为唯一事实来源之前，v1 文件保持只读。
- **语料**：v1 本地库只有 179 篇（[SYN §6][SYN] SI-35；[RT §10.7][RT]），用一次性 ETL 导入 v2 corpus。迁移目标通常是 personal 部署（01 US-27）；若导入 platform 部署，论文元数据按联邦入库的口径进入 corpus，不记来历，而收藏状态、标签、笔记只进该用户的 `usr` 域（HC-01）。
  - v1 的 `paper`、`identifier`、`relation` 映射到 Version、identifier、relation；
  - 弱信号候审的状态原样带入；
  - 导入后按 §9 的规则重算簇，结果与 v1 的对比报告作为验收证据（§17）。
- **v1 已下载的 PDF**：一律视为该 v1 用户的**私有资产**，不进入共享层，许可为 CC 也不例外；共享副本由平台经公开通道重新取得（§3.5、§12.3）。迁往 `host_is_user_device=true` 的 personal 部署时，PDF 原地留在本机并登记到该用户私域；迁往 platform 部署时，PDF 留在用户设备上由 pc-agent 登记，是否上传受 01 FR-85 门控（LQ-15 有结论前默认关闭），上传时按 08 §5.4 做 E2E 加密。
- **凭证**：v1 `.paper-crawler/` 中的凭证不迁往服务端，由 pc-agent 原地使用（§12.6）。
- **文档**：
  - v1 设计文档保持现状态，不改动；
  - v2 文档用 `[v1-xx]` 链接引用；
  - 支持名录 [DIR] 今后由注册表生成；
  - 本文涉及的 v1 ADR 修订由 09 起草（§14.3），本文不改 decision-log。

---


## 15. 测试方法（⑬）

默认测试全部离线运行（AGENTS.md）。在线校验只在显式任务中运行，沿用 v1 `make smoke` 的门控方式（需要 `PAPER_CRAWLER_CONTACT_EMAIL`）；浏览器测试沿用 `PC_BROWSER_TESTS` 门控。

### 15.1 fixture 回放

- **录制**：每个 connector 与每个 ConnectorInstance 用 `registry dry-run`（§13.2）经 PoliteHttp 真实请求录制四类 fixture：
  - 正常页；
  - 空页或 200 空体；
  - 限流或错误，包括 arXiv 的"HTTP 200 + `Rate exceeded.`"和 bioRxiv `/details` 的 200 空体；
  - 边界：最后一页、resumptionToken 过期、删除记录、版本变化、DOI 前缀归属变化。
- **回放**：`parse` 与 `normalize` 是纯函数，在回放中与黄金 NormRecord 逐字段比对。`mapper_version` 递增时必须同时更新黄金文件，并在评审中给出差异说明。
- **v1 fixture 复用**：v1 各 adapter 的既有 fixture 经 `v1_bridge` 回放，结果须与 v1 产出的 PaperStub 语义等价（迁移回归）。

### 15.2 契约测试

| 契约 | 断言 |
|---|---|
| 连接器不发 HTTP | 以 mock 传输层替换网关后，连接器模块不产生任何网络调用；所有请求都以 RequestSpec 形式出现 |
| 平台侧无用户凭证 | 静态扫描加运行时断言：平台侧 RequestSpec 的 headers 与 params 中不出现 `user_*` 类密钥；注册表中 `secret_ref` 只指向 `deployment/*`（lint 规则 4） |
| 游标原子性 | 在"取到数据"与"提交"之间注入进程终止，重跑后没有漏数据，游标也没有越过未落库的数据。fixture 须含页内与页间乱序的 OAI 列表、中途过期的 resumptionToken 与 Crossref cursor |
| 同键串行 | 同一 WatchKey 并发提交两个任务，上游请求序列中只出现一个任务的请求；游标比较交换失败的一方整体回滚 |
| 幂等 | 同一批输入重放两次，第二次不产生任何新行或新事件 |
| 身份与顺序无关 | 属性测试：同一批 NormRecord 以随机顺序输入，得到的簇完全相同，且每条 Manifestation 挂接的 Version 也相同（D-031 的纪律；覆盖只带版本系标识符的记录、修订史晚到、健全检查所需字段晚到三种情形，§9.2、§9.3） |
| 合并可回滚 | 对任一合并操作执行撤销，按合并日志回放后，簇与 `public_id` 重定向都恢复为操作前的状态 |
| 弱信号不自动合并 | 合并日志中每个 union 都引用至少一条按 §9.3 规则被接受的边，或一条人工决定 |
| 注册表 | JSON Schema 与 13 条 lint 规则（§3.8）；v1 → v2 转换器幂等，往返审计没有未映射字段 |
| 专项红线 | 静态扫描加取回日志审计：arxiv.org 的 `/e-print/`、`/src/` 路径请求为 0，非 CC 许可 arXiv 条目的 PDF 在共享存储中为 0（CP HC-06）；`ieee_xplore`、`acs`、`acm_dl` 没有任何配方与平台侧全文请求（CP HC-27） |
| SCD 一致 | SCD 的静态部分与 `connector.describe()` 的输出一致；04 路由器只经 SCD 读取来源能力 |

### 15.3 策略引擎

- **属性测试**（Hypothesis 风格，随机生成信号组合与覆盖记录）：
  - 单调：任一信号变严，模式不会变松；收紧型覆盖记录只会让模式变严；
  - 覆盖有界：放宽型 PolicyOverride 只能抬升 S1–S3，越不过 S4、S5、挑战冷却、exec_side、商用与许可门控、证据时效与红线（08 §4.4 纪律 2）；
  - 可复现：同样的输入哈希与策略版本，得到同样的决定。
- **黄金决策表**：§6.8 冲突清单与 §3.6 示例中的每个"来源 × 通道 × 操作"，写成期望决定，由表驱动测试比对；另把 08 §4.2 的 R1–R16 每条至少写成一个用例（例如 INFORMS 全文的 `user_fetch` 为 link_only，对应 R11；ftp.ncbi 的快照导入为 link_only，对应 R6）。
- **时钟注入**：证据超期（`next_review_by` 已过）、覆盖记录到期、冷却期结束，都按预期改变决定。

### 15.4 PoliteHttp

- **robots-first**：对判定为 `disallow` 或 `unreadable` 的路径，mock 传输层收到的请求数为 0；唯一例外是带 `robots_basis=api_conflict` 或 `written_confirmation` 的按需请求，且每条都带 `robots_exception_ref`。robots 缓存超过 24 小时时，先刷新 robots 才发业务请求。robots.txt 返回 404、403、5xx、超时与挑战页时，分别映射为 `absent`、`unreadable`、`unreadable`、`unreadable`、`unreadable`（§3.4）。
- **挑战检测**：复用 v1 ChallengeDetector 的四类 fixture，外加 Anubis 与 ALTCHA 样本。命中后主机冷却 24 小时，冷却期内重试次数为 0。
- **伪成功与空体**：按 `expect` 判定，分别归入 `rate_limited` 或 `empty_body`。
- **响应头上交**：Crossref 的池名、OpenAlex 的美元额度头、OpenReview 的 `ratelimit-policy`，都能到达限速器与 SCD 的动态部分。
- **令牌桶键**：多出口 IP 时，全局桶的消耗等于各出口之和，不会因多出口而叠加额度（§19 第 4 条）。

### 15.5 漂移探针与自动降级

故障注入逐项验证 §6.5 的探针与 §6.6 的降级语义：

| 注入 | 期望 |
|---|---|
| robots 变严 | 下一个探针周期内，该通道降级或暂停，并发出告警 |
| robots 变松 | 只告警，不自动升级 |
| ToS 哈希变化 | 通道标 needs_confirmation；7 天内保持现模式；第 8 天仍未复核时，上限降为 on_demand |
| 新出现 `tdm-reservation: 1` | 全文通道上限降为 user_side；该站内容的共享派生为 deny |
| Crossref 最新 DOI 的 owner prefix 或 member 变化 | 生成 venue 变更提案；该 venue 的全文配方暂停 |
| canary 计数骤降为 0 | 端点降级，切换到替补链，例如 bioRxiv 改用 `member:54368` 或 EPMC |
| 有覆盖记录的通道出现 robots 或 ToS 哈希变化 | 覆盖记录在 24 小时内失效，通道回到 needs_confirmation（08 §4.4 纪律 4） |
| 探针复测证据与原证据一致 | 该证据的 `verified_at` 自动续期（`by=probe`）；条款语义类证据不续期 |
| 手动关闭告警之前 | 模式不会自动回升 |

### 15.6 流水线端到端回放

在 PG 测试实例上，把录制好的一天数据（arXiv OAI 一日、Crossref 若干 venue 一日、EPMC `FIRST_IDATE` 一日）走完六段，断言：
- manifestation 按 `(source_id, source_key)` 唯一；
- 与真值集合相比，召回率为 100%，重复为 0；
- 出箱事件数与变更数一致；
- 按用户读取 FeedInbox 视图（按 `work_id` 去重并跟随 `merged_into`）时，每个 Work 只出现一次；
- 回放数据中含"预印本先入库、期刊正式版后到"的样例：关注该期刊频道的用户收到这篇论文，已收到预印本的用户只收到更新通知（§10.7）；
- 再次回放没有任何变化。

### 15.7 身份质量评测

- **金标集**：按学科构建"预印本 ↔ 正式版""WP ↔ 发表版""同题不同文"三类标注对，规模由 09 定。
- **评测**：分别报告自动接受的边的精确率、候审队列的召回率、WP 对被错误合并的次数。
- **v1 对比**：179 篇 v1 语料按 §9 重算簇后，与 v1 的合并结果比对，差异逐条解释（§14.4）。

### 15.8 摘要、许可与共享派生

- **权利分类**：`classify_rights` 的黄金集覆盖 arXiv、PMC、Crossref 各种 license、OpenAlex 倒排还原、SN API 等。
- **许可闸**：
  - 共享 OA 资产每周抽样审计；
  - LLM 派生按 [PU §3][PU] 第 21 条的回归门槛：许可误放行为 0。
- **共享派生的输入谱系**：从缓存键追溯输入来源，断言全部为 `public_shared`。
- **总开关回退**：关闭 `policy.index_b_abstracts` 后跑重建，`input_basis` 含 B 类摘要或 `third_party_s2` 的向量行数归零。

### 15.9 用户侧

- **配方解释器沙箱**：对抗 fixture 覆盖以下情形，全部被拒绝：
  - 未列入白名单的步骤；
  - 越出白名单的主机；
  - 把携密头发往他域；
  - 执行下发的 JS；
  - 自动填写表单。
- **取回意图与回执**（协议测试由 08 定义，本文补充候选项与配方部分）：
  - 候选项中的配方引用在 PolicyBundle 中都能解析到已签名的配方；
  - 候选项、配方与回执中不存在凭证、内容、哈希字段；
  - 平台日志中扫描不到密钥（沿用 v1 obslog 的敏感键规则，auth-framework §5）。
- **robots 与 AI-UA**：候选项中 `user_fetch` 的签发前提是 robots 判定允许，且目标路径不在具名 AI-UA 禁令范围内；判定为 `disallow` 或 `unreadable`，或命中 08 R11 时，只给出 `open_in_tab`。
- **T3 门控**：来源的 `derivation.private_llm` 为 `forbidden`（IEEE）或 `needs_confirmation`（Elsevier）时，私有 TL;DR 与私有嵌入任务都不启动；platform 部署的服务端 T3 开关默认关闭。
- **护栏**：用 mock 时钟验证每域间隔 ≥6 秒、每平台每日 ≤200 次尝试（成败都计入）、挑战后冷却 24 小时并转为 `open_in_tab`。
- **v1 复用**：沿用 v1 mock IdP 的离线集成测试（auth-framework §9）。
- **浏览器路径**：真实浏览器测试在 `PC_BROWSER_TESTS` 门控下运行。

### 15.10 canary、新鲜度与负载

- **canary**：每个 P0 通道每日一条 canary 查询，断言三点：计数不低于基线、抽样字段完整、venue 解析命中。只在显式的在线任务中运行。
- **新鲜度**：在线观测 14 天，统计 §10.9 的各项指标，用于校准设计目标。
- **负载**：在同一组 WatchKey 下，把用户数放大 10 倍，上游请求数的增幅应接近 0（NFRc-03.1）。

### 15.11 接入成本

在 PR 模板中记录 SOP 的起止时间，统计首批 10 个零代码接入与首批 5 个新 connector 的中位耗时（NFRc-03.3）。

---

## 16. 测试类型

| 类型 | 覆盖 | 运行 | 门控 |
|---|---|---|---|
| 单元 | Mapper、normalize、权利分类、venue 解析、决定函数的各上限函数 | 默认离线 | `make check` |
| 契约 | 连接器协议、注册表 schema 与 lint、SCD 一致性、候选项与配方 schema | 默认离线 | `make check` |
| 属性 | 策略引擎三条性质；身份与顺序无关；合并可回滚 | 默认离线 | `make check` |
| fixture 回放 | 全部 connector 与实例（四类 fixture） | 默认离线 | `make check` |
| 集成 | 六段流水线在 PG 测试实例上的端到端回放；出箱事件；FeedInbox | 离线（本地 PG） | CI |
| 故障注入 | 漂移探针与降级；游标原子性；上游失败时走替补链 | 离线 | CI |
| 在线 canary 与探针 | P0 通道 canary；探针真实运行 | 显式在线任务 | 标记为 `online`，需要联系邮箱 |
| 浏览器 | 用户侧配方在真实浏览器中的执行 | 显式 | `PC_BROWSER_TESTS` |
| 合规审计 | 许可闸抽样；共享派生谱系；取回日志中"请求前 24 小时内有 robots 快照"的核对；robots 例外请求（`robots_exception_ref`）与联邦入库来历的审计 | 每周（人工加查询） | 运维 |
| 质量评测 | 身份金标集；摘要覆盖周报；TL;DR 黄金集（与 06、07 共用） | 里程碑前 | 09 |
| 负载与新鲜度 | 10 倍用户放大；§10.9 指标 | 里程碑前 | 04、09 |

---

## 17. 验收标准（AC 草案）

编号已由 [09](09-roadmap-and-milestones.md) 定稿为全库唯一的正式编号 `AC-V<m>.<n>`，编号中的 `V<m>` 即所属里程碑（新旧对照见 09 附录 A）；与 01 或其他文档同号的条目，表示已按 09 的合并规则合为同一验收项。"承接"列指向 §1.2 的需求候选（与 01 编号的对应见 §1.2）、§1.3 的设计规则或 HC。

| 编号 | 验收标准（可度量） | 承接 | 测试类型 |
|---|---|---|---|
| AC-V0.23 | `registry/` 下全部 SourceSpec、VenueSpec 与实例文件 100% 通过 JSON Schema 与 13 条 lint；CI 在失败时阻断合并 | FRc-03.1 | 契约 |
| AC-V1.8 | 每个 Source 的 `hosts` 中，每个主机都有 robots 判定与证据；证据超过 90 天未复核的：探针持续为绿且证据其余字段完整时进入 `review_overdue`，30 天内维持原模式；宽限结束或任一探针告警后，后台操作的决定 100% ≤ on_demand 且标 needs_confirmation（时钟注入测试；简报 R2-16） | DR-3；CP HC-28 | 契约、属性 |
| AC-V0.26 | v1 的 62 个 VenueSpec 全部由转换器迁入；往返审计中未映射字段为 0；第二次运行的差异为空 | FRc-03.1；§3.7 | 契约 |
| AC-V1.17 | 首批 10 个零代码接入（路径 A 或 B）的中位耗时 ≤30 分钟，且这些 PR 不改动 `src/` | FRc-03.2；NFRc-03.3 | 过程度量 |
| AC-V1.18 | 首批 5 个新 connector 的中位耗时 ≤2 人日；每个都带四类 fixture、SCD 与探针声明 | NFRc-03.3 | 过程度量 |
| AC-V1.5 | 平台侧与用户侧执行器对 robots 判定为 `disallow` 或 `unreadable` 的路径发出的自动请求数为 0；唯一例外是 §6.8 登记的 08 R5 冲突与有效书面确认下的按需请求，这类请求 100% 带 `robots_exception_ref`，其中后台批量请求为 0（契约测试）。在线取回日志中，每个请求的主机在请求前 24 小时内都有 robots 快照，违例为 0 | DR-5；SI-38；08 的 HC-29、HC-31 | 契约、合规审计 |
| AC-V1.4 | 平台侧请求 100% 带部署 UA 与联系邮箱；每个上游在同一时刻只使用一个平台身份；出现挑战后该主机 24 小时内的请求数为 0 | DR-4；CP HC-10、HC-26 | 契约、合规审计 |
| AC-V0.29 | 策略引擎的三条性质属性测试全部通过；§6.8 与 §3.6 的黄金决策表 100% 一致；红线在任何覆盖记录下都为 deny | FRc-03.9；P-05 | 属性、单元 |
| AC-V1.7 | 缺证据引用或有效期超过 12 个月的 PolicyOverride 被 lint 拒绝；放宽 S4、S5、挑战冷却或结构性上限的测试用例为 0（08 §4.4 纪律 2）；覆盖所在通道出现 robots 或 ToS 哈希变化后，覆盖在 24 小时内失效的比例为 100% | FRc-03.9 | 契约、故障注入 |
| AC-V1.10 | §15.5 的全部注入场景，在一个探针周期内达到期望状态并发出告警；没有任何场景出现模式自动回升 | FRc-03.9；SI-12 | 故障注入 |
| AC-V1.22 | 对录制的 7 日窗口（Crossref created 加重叠、arXiv OAI、EPMC `FIRST_IDATE`）回放：与真值相比，标识符召回为 100%，manifestation 重复为 0；重放后新增为 0 | FRc-03.3；DR-9 | 集成 |
| AC-V1.24 | 在"取到数据"与"提交"之间注入进程终止 100 次，全部满足：没有漏数据，游标没有越过未落库的数据 | FRc-03.3 | 故障注入 |
| AC-V2.41 | 在线观测 14 天：arXiv 从 OAI 可取到进入 FeedInbox 的 p95 ≤2 小时；P0 策展 venue 从 DOI created 到入库的 p95 ≤24 小时。未达标时，报告瓶颈并由 04、09 调整目标 | NFRc-03.5 | 在线、负载 |
| AC-V1.25 | OpenAlex 季度快照发布后 ≤7 天完成兴趣并集子集的导入并应用删除日志；导入报告给出子集规模，并与简报 B-04 的语料目标比对 | FRc-03.4 | 集成、在线 |
| AC-V1.26 | 身份属性测试：随机打乱输入顺序，簇 100% 相同；任一合并撤销后状态 100% 复原 | FRc-03.5；DR-9 | 属性 |
| AC-V1.28 | 合并日志审计：没有依据被接受的边或人工决定的 union 为 0；WP 系列 fixture 对的 `preprint_of` 关系 100% 建立，被并入同一 Work 的为 0 | FRc-03.5；D-007 | 契约、合规审计 |
| AC-V1.29 | 在身份金标集上，自动接受的 `version_of` 边精确率 ≥0.99（建议阈值，09 定稿）；另报告召回率与候审队列规模的基线 | FRc-03.5 | 质量评测 |
| AC-V1.30 | 摘要变体 100% 带 `abstract_source` 与 `abstract_rights`；B 类、C 类与未知摘要以 DL4 展示或作为共享派生输入的次数为 0 | FRc-03.6；CP HC-08 | 契约、合规审计 |
| AC-V1.31 | 每周按"学科 × 出版方"输出摘要覆盖报告（A 类、B 类、无），且包括 Elsevier、APA、IEEE、AOM 等 Crossref 零摘要出版方的替补链覆盖 | FRc-03.6 | 在线、报告 |
| AC-V2.20 | 关闭 `policy.index_b_abstracts` 后跑重建，`input_basis` 含 B 类摘要或 `third_party_s2` 的向量与 BM25 文档为 0 | LQ-02 回退 | 集成 |
| AC-V1.36 | 共享 OA 资产 100% 带白名单许可与证据；许可闸抽样审计的误放行为 0 | FRc-03.7；CP HC-05 | 合规审计 |
| AC-V1.34 | 共享 TL;DR 与翻译的输入谱系 100% 为 `public_shared`；不过三道闸的条目 100% 降级为原文首句 | FRc-03.7；CP HC-11；SI-60、SI-61 | 契约、质量评测 |
| AC-V1.32 | 嵌入行 100% 带 `model_id`、`model_rev` 与 `input_basis`；更换模型时新旧版本可以并存，检索调用未指定 `model_id` 的次数为 0 | FRc-03.7 | 契约 |
| AC-V1.38 | 平台出口访问 `exec_side=user` 通道所列全文主机的请求为 0（取回日志审计加出口白名单测试） | FRc-03.8；CP HC-03 | 合规审计、契约 |
| AC-V3.17 | 取回意图的候选项、FulltextRecipe 与回执的 schema 中没有凭证、内容、哈希字段；平台日志的密钥扫描命中为 0；候选项引用的配方 100% 可在已签名的 PolicyBundle 中解析 | FRc-03.8；CP HC-04、HC-02 | 契约 |
| AC-V3.18 | 配方解释器对全部对抗 fixture 的拒绝率为 100%；携密头发往白名单外主机的次数为 0 | FRc-03.8 | 契约 |
| AC-V3.19 | 用户侧护栏在 mock 时钟下全部成立：每域间隔 ≥6 秒、每平台每日 ≤200 次尝试（成败都计入）、挑战后冷却 24 小时并转为 `open_in_tab`、会话失效时停止；API 面不存在批量取回入口 | FRc-03.8；[v1-04][v1-04] §4–§5；08 的 HC-32 | 单元、浏览器 |
| AC-V3.7 | enrich、index 与共享缓存的作业读取 `per_user_only` 输入的次数为 0（契约测试，配合 05 的 RLS 测试） | CP HC-01；DR-7 | 契约 |
| AC-V1.40 | 抽样审计跨用户可见字段：100% 可追溯到来源、许可与证据记录 | NFRc-03.2；CP HC-28 | 合规审计 |
| AC-V1.21 | 每个 P0 能力声明 ≥2 条同能力通道（lint 规则 6）；主通道故障注入后经替补链提供服务，全局失败为 0 | NFRc-03.4；DR-8 | 故障注入 |
| AC-V2.38 | 在同一组 WatchKey 下，用户数放大 10 倍，上游请求数增幅 ≤10% | NFRc-03.1；P-04 | 负载 |
| AC-V3.10 | 题录导入：RIS、BibTeX、EndNote、CSL-JSON 的 fixture 全部解析成功；导入物 100% 落在 `usr` 域，向 corpus 回写的字段为 0 | FRc-03.10；CP HC-01 | 单元、契约 |
| AC-V2.44 | 端到端回放中，"预印本先入库、期刊正式版后到"的样例 100% 进入关注该期刊频道的用户的 FeedInbox 视图；已收到预印本的用户只收到更新通知，重复条目为 0 | FRc-03.3；§10.7 | 集成 |
| AC-V1.6 | 策略引擎对 08 §4.2 的 R1–R16 各至少一个黄金用例 100% 一致；其中命中 R11 的全文通道签发 `user_fetch` 的次数为 0 | FRc-03.9；08 §4.2 | 单元、契约 |
| AC-V1.23 | 游标故障注入覆盖乱序分页、resumptionToken 过期与 Crossref cursor 过期三类 fixture，全部满足"无遗漏、游标不越过未落库数据"；同一 WatchKey 并发任务的上游重复请求数为 0 | FRc-03.3；DR-9 | 故障注入 |
| AC-V1.27 | 身份属性测试同时比较 Manifestation → Version 的挂接：随机打乱输入顺序后 100% 相同（含修订史晚到、健全检查字段晚到的用例） | FRc-03.5；DR-9 | 属性 |
| AC-V1.39 | 共享存储与取回日志审计：非 CC 许可 arXiv 条目的 e-print 为 0，`/e-print/`、`/src/` 请求为 0（CP HC-06）；`ieee_xplore`、`acs`、`acm_dl` 的平台侧全文请求与配方为 0（CP HC-27） | CP HC-06、HC-27 | 契约、合规审计 |
| AC-V1.9 | 以 2026-09-26 批量导入的种子为输入跑时钟注入：探针复测一致的证据自动续期；任一自然日内同时超期的 P0 源不超过 P0 总数的 10%（⚠ 设计值），主干通道不会同日集体降级 | DR-3；P-09；§6.5 | 属性、故障注入 |
| AC-V3.11 | 兴趣并集与联邦入库审计：corpus 与 harvest 日志中可关联到具体用户或查询文本的字段为 0；由私有文献库派生、支持用户数不足 `k_cf` 的细粒度键没有触发导入（R2-19） | CP HC-01；08 HC-30 | 契约、合规审计 |

---

## 18. 术语（供 01 登记）

以下是本文新增、会被其他文档引用的术语。简报 §5 已有的术语（Source、SourceSpec v2、SCD、Connector/ConnectorFamily、Venue、Work/Version/Manifestation、Policy Engine、WatchKey、Percolator 等）不再重复；RetrievalIntent、PolicyBundle、Companion Extension（U2）、pc-agent（U3）由 02 与 [08][08] 定义，本文沿用。

| 术语 | 含义 | 定义处 |
|---|---|---|
| **SourceChannel（来源通道）** | SourceSpec 中的来源通道：`metadata`、`latest`、`fulltext` 三条之一。简报 R2-02 已统一：SourceSpec 内的通道称 SourceChannel，用户保存的查询称 Channel（频道） | §3.3 |
| **AccessMode** | 策略引擎输出的取用模式，全序为 `deny < link_only < user_side < on_demand < background`。它细化了简报 §5 Policy Engine 中的"后台 / 用户触发 / 仅外链"，是全库唯一的策略模式枚举（简报 R2-09） | §6.2 |
| **AccessDecision** | 策略决定快照：模式、是否允许、最小间隔、`display_scope`、`robots_basis`、是否 needs_confirmation、原因、输入哈希、策略版本 | §6.3、§6.7 |
| **robots_basis** | AccessDecision 上的 robots 放行依据：`none`、`api_conflict`（08 R5）、`written_confirmation`。网关只凭它放行 robots 禁止路径上的按需请求，并逐条审计 | §5.5、§6.3 |
| **needs_confirmation** | 合规状态：条款或 robots 与文档化 API 冲突、证据超期且宽限结束（`review_overdue` 之后，R2-16）、ToS 变化宽限期满等，须取得书面确认或复核后才能放开 | §6.4 |
| **PolicyOverride** | 经书面确认的有期限覆盖记录（≤12 个月），分放宽型与收紧型。放宽型只能抬升文档化 API、bulk、robots 三类冲突的上限，越不过 ToS 禁令、TDM/AI 保留、挑战冷却与结构性上限（08 §4.4）；robots 或 ToS 哈希漂移时 24 小时内失效 | §6.3、§6.4 |
| **DriftProbe** | 漂移探针：周期比对 robots、ToS、TDM 信号、挑战率、配额头、归属、空体与计数、弃用公告、匿名可访问性 | §6.5 |
| **EvidenceRecord** | 证据记录：`{id, claim, url, verified_at, grade, survey_ref}`，其中 grade 取 LIVE、DOC、SNIPPET、3P | §3.3 |
| **ConnectorInstance** | 平台族或协议族的具体实例（数据而非代码），例如某个 DSpace 或 OJS 的 OAI 端点 | §5.1 |
| **PoliteHttp** | 02 P13 Egress Gateway（出站网关，平台侧唯一对外出口）内部使用的 HTTP 客户端库，含 robots-first 闸、令牌桶、挑战检测、审计（简报 R2-08） | §5.1、§5.5 |
| **`bulk_snapshot`** | ConnectorFamily 之一：官方快照、年度文件与批量 dump 的导入（OpenAlex 快照、Crossref 年度文件、PubMed baseline、DROPS dblp 等；简报 R2-11） | §5.3、§5.4 |
| **`registry`（L2 子类型）** | 身份、机构与标识符注册表类来源（ORCID、ROR、DataCite 等；简报 R2-11） | §2.1 |
| **RequestSpec** | 连接器声明的请求，由 PoliteHttp 执行 | §5.2 |
| **RawRecord / NormRecord** | 源记录原文与规范化记录；NormRecord 带 `mapper_version` | §5.2、§10.6 |
| **VenueKey / VenueEdge / VenueEdition / HostingPeriod** | Venue 的多键归一键、演化边、届次（会议或卷）、托管期 | §2.3、§2.4 |
| **wp_series / MeetingEvent / presented_at** | 经管的 WP 系列、学术会议事件、论文在会议上报告的事件关系 | §2.4 |
| **curation 等级** | Venue 的策展等级：`curated`、`auto`、`user_proposed` | §2.5 |
| **标识符粒度** | `version`、`version_family`、`work_assertion`、`manifestation`；union-find 只在相应粒度上合并 | §9.1 |
| **version_linking** | Source 的版本归并方式：`union`（预印本服务器类）或 `relate_only`（WP 系列类） | §9.3 |
| **revision_of / version_of / preprint_of / link_class** | 版本关系边及其类别，例如 `wp_to_publication` | §9.3 |
| **AbstractVariant / abstract_rights** | 摘要变体，权利取 `open`、`publisher_copyright`、`personal_license`、`unknown` | §8.1、§9.7 |
| **license_code** | 规范化的单篇许可枚举 | §10.6 |
| **input_basis** | 派生物（嵌入、TL;DR）的输入构成标记，用于定点重建 | §11.3 |
| **InterestUnion** | 全体用户兴趣的并集，用于快照子集导入；只记并集版本，不记用户与兴趣的对应，私有来源的细粒度键受 `k_cf` 约束（R2-19） | §10.5 |
| **FulltextOption** | 某 Version 的全文候选项：`shared_oa_asset`、`oa_location`、`user_tdm_api`、`user_session`、`link_resolver`、`publisher_landing`、`private_upload`，映射到 08 的五种取回方式 | §12.3 |
| **FulltextRecipe** | 用户侧的声明式取回配方：受限步骤语言、占位符、主机白名单、校验规则；随平台族实例与官方 TDM API 版本化 | §12.4 |

---

## 19. 异议与备选

| # | 事项 | 本文做法 | 证据 | 备选 | 建议裁定方 |
|---|---|---|---|---|---|
| 1 | **PubMed 与 NCBI bulk 暂缓**。简报 §6.1-2 把"Europe PMC / PubMed"列为生命科学主干，把 PubMed baseline 列入本地底座 | 按简报 Q4 的默认与 §6.1-2 末句（bulk 主机的 robots 纳入 robots ADR），PubMed E-utilities 只做 on_demand 的单个 PMID 补查，baseline 与 updatefiles 暂不导入；后台主干由 EPMC REST 的 `SRC:MED` 承担（间隔 ≥10 s） | `eutils.ncbi.nlm.nih.gov` 与 `ftp.ncbi.nlm.nih.gov` 的 robots 均为 `Disallow: /`（[LS §2.3.1][LS]、[AG §2.2.11][AG] 核验补充）；EPMC `FIRST_IDATE:[2026-09-24 TO 2026-09-25]` 全库共 3,295 条（[LS §2.3.3][LS]），日增量级 REST 足以承载 | robots ADR 取得书面确认后，baseline 作为生命科学底座直接导入（体量与节奏见 §10.5）；EPMC 转为替补 | **已裁决**：简报 R2-13（NCBI 书面确认前由 EPMC + PMC 允许通道 + Crossref 承担，`pubmed` 保持 v2-P0 并标 ⚑ROBOTS）；本文按 04 §20 第 3 项的从严读法，确认前也不做 E-utilities 按需调用；robots ADR 由 09 起草 |
| 2 | **D-007 需要新 ADR 细化** | 预印本服务器类的预印本与正式版作为同一 Work 的不同 Version（各自保留元数据与全文）；WP 与发表版只建 `preprint_of`，不并入 | 简报 §5 对 Work/Version 的定义已包含"预印本 v1、v2、正式版"；SI-16。D-007 原文是"预印本与正式版默认不合并为一条，以 `preprint_of` 关系互联，两版全文都保留"，并要求查询层提供"按研究聚合"视图；v2 把该视图物化为 Work，同时保留两条 Version，WP 则按 D-007 的理由（标题都会改）只建关系 | 严格沿用 D-007，预印本与正式版为两个 Work。代价：推荐与检索中出现重复卡片，版本折叠只能在展示层临时做 | 09 起草；用户确认 |
| 3 | **简报 §7 未列出的 ADR 候选** | 建议新增两条：①"SourceSpec v2 与 Source/Venue 分离"，取代 D-002 的两层结构表述与 D-012，并在 v2 中关闭 D-038 的挂起；②"身份模型三层与版本边投票"（见第 2 条） | AGENTS.md："取代架构决策须有新 ADR 点名旧 ADR"；§14.3 | 并入简报 §7-5（单栈与冻结）一并记录。不建议：两者涉及的决策面不同 | 09 |
| 4 | **令牌桶键增加出口 IP** | 在简报 P-04 的键 `(source, host, 请求类, 身份)` 上，附加出口 IP 维度。它**只收紧、不叠加**：按 IP 计额的上游（Crossref 并发、OpenCitations、ROR、INSPIRE）按 IP 设子桶，所有子桶之和仍受全局桶约束；"所有机器合计"的上游（arXiv）只看全局桶 | SI-37；[AG §4][AG] Q11；CP HC-10（禁止多 IP 叠加额度） | 不加该维度，要求部署只有单一出口。代价：水平扩展时按 IP 计额的上游会被误判超限 | **已裁决**：简报 R2-08 定为五元组 `(source, host, 上游请求类, 凭证, 出口 IP)` |
| 5 | **ToS 哈希漂移设 7 天宽限期；降级目标按通道细化** | robots 与 TDM 信号漂移立即降级；只有 ToS 哈希变化给 7 天宽限期（保持现模式，同时标 needs_confirmation）。降级目标：全文通道降为 link_only（相当于"仅元数据"）；元数据通道本身受影响时暂停并切换替补链，而不是"仅元数据"。有有效覆盖记录的通道不享受宽限：robots 或 ToS 哈希一变，覆盖在 24 小时内失效（与 08 §4.4 纪律 4 一致） | 简报 §6.1-5 要求"发现漂移即告警，并自动降级到仅元数据"；[SS §3][SS] 第 14 条记录了 2 个月内的多起政策漂移，说明监测必要。但条款页的哈希也会因版式、cookie 横幅、日期等非实质改动而变化（推断，⚠ 误报率未实测），立即降级可能造成频繁停更 | 严格按简报：任何 ToS 哈希变化都立即降级。代价：误报导致频繁停更 | **已裁决**：简报 R2-15 采纳分档处置；"有覆盖记录的通道 24 小时失效"是与 08 §4.4 共同的从严细化，仍请主 agent 确认（08 §14 第 12 条） |
| 6 | **arXiv set 粒度** | 默认按类目级 set 收割（简报 §6.1-2）；兴趣覆盖某个 archive 的大部分类目时，退到 archive 级 set，以节省请求 | 全平台 1 次/3 秒、单连接（CP HC-06）；set 为 `group:archive:category` 三级，共 183 个（[NS §2.2.2][NS]） | 始终用类目级。代价：请求数随关注类目数线性增长 | 04（WatchKey 编译） |
| 7 | **Springer Nature Meta API 归为 C 类，只在用户侧使用** | SN API 的摘要不进入共享补齐链，只由用户本人的 key 在用户侧使用 | CP §2.2.1 与 M6：摘要只许个人使用；SN 条款禁止多账号或多 key 规避限额（CP §2.4 核验补充） | 按 [NS][NS] 的建议作为 P0 共享源。与 CP 冲突，不采纳 | **已裁决**：简报 R2-14（SN OA/Meta API 与 NASA ADS 在条款书面确认前按用户级凭证处理；SN Meta API 摘要按 C 类） |
| 8 | **B 类摘要可用于内部索引与嵌入（默认假设）** | 默认允许，有机器可读 TDM 保留的来源除外；设总开关 `policy.index_b_abstracts`，可整体回退并重建 | CP §2.3.5、M5；LQ-02 未决；[AG §3][AG] 第 9 条 | 默认禁止：内部索引只用 A 类摘要与标题。代价：Elsevier、APA 等出版方的论文检索召回明显下降 | **已裁决**：简报 R2-21（默认纳入、可逆重建、设开关）；本文对机器可读 TDM 保留的排除是从严细化，自然语言保留是否也排除见 04 §20 第 34 项 |
| 9 | **robots 对用户侧自动请求的效力** | 与 08 的 HC-29、R16 一致：用户侧执行器的自动请求（`user_fetch`、`tdm_api`）同样要求 robots 判定允许；只有用户在场的导航（`open_in_tab`）不受约束。因此 S3 为 `disallow` 或 `unreadable` 时，全文通道上限为 link_only（§6.2） | 08 的 HC-29、R16。另一种读法：D-014 第 5 条规定 auth_gated 获取"不受本条限制"；[NS §4][NS] 第 1 条建议"用户触发的单篇获取按 ToS 判断，并在 UI 中明示" | 按 D-014 第 5 条与 NS 的读法，用户侧单篇自动请求只受 ToS 与 TDM 条款约束，上限放宽为 user_side。策略引擎用配置即可切换（`cap_robots` 对 user_side 操作是否生效）。代价：与 HC-29 冲突，需要 08 修订。具名 AI-UA 规则（08 R11）有同样的两种读法，见第 18 条 | robots ADR（简报 §7-2）；08 |
| 10 | **v2 任何部署都不做批量取回** | 两种部署都只做单篇、显式触发（与 01 的 FR-32、08 的 HC-32 一致）。v1 冻结后仍可在本机独立运行，其批量 `pull/grab` 属于 v1 工具，不是 v2 功能 | 任务要求"单篇、显式触发"；SERU 把系统性下载列为可疑行为（[CP §2.3.4][CP]） | personal 部署（`host_is_user_device=true`）保留 v1 批量能力，照旧遵守 v1 纪律（串行、1 次/6 秒、每平台每天 200 篇、工作时段；CP §2.3.4 认为"v2 在用户侧执行时照旧适用"）。代价：与 HC-32 冲突 | **已裁决**：受限全文保持单篇、显式触发（HC-32）；简报 R2-48 另允许 personal 部署提供"仅许可允许的 OA 全文批量取回到本人私有空间"（Could，§12.1 第 2 条） |
| 11 | **术语 SourceChannel** | 简报 §5 中 SourceSpec 的"Channel"改称 SourceChannel | 简报 §5 同时定义了"Channel（用户频道）"，同名会造成歧义 | 保持 Channel，在上下文中区分 | **已裁决**：简报 R2-02 |
| 12 | **取用模式由三档细化为五档** | `background`、`on_demand`、`user_side`、`link_only`、`deny` | 简报 §5 的 Policy Engine 写作"后台 / 用户触发 / 仅外链"；"用户触发"须区分平台执行（on_demand，受 robots 约束）与用户侧执行（user_side，受凭证约束），否则无法表达简报 Q4 | 三档加一个 `executor` 字段。表达力相同，但判定函数不再是单一全序上的取最小，单调性更难证明 | **已裁决**：简报 R2-09（以本文五档全序为唯一枚举） |
| 13 | **新鲜度与吞吐目标未经实测** | §10.9 的数值是设计目标，由 AC-V2.41 在线观测后校准；arXiv 一项折合公告后约 4.5 小时，与 01 的 NFR-12（≤6 小时）相容 | 调研没有给出端到端时延的实测 | — | 04、09 |
| 14 | **与 05 物理表的对齐项** | ①版本边词表：`version_of`（投票通过，并入同一 Work）、`revision_of`（同一版本系的修订）、`preprint_of` 加 `link_class=wp_to_publication`（WP 与发表版，只建关系）。②`work_assertion` 类标识符（OpenAlex W、S2 corpusId、INSPIRE recid）不进 `corpus.identifier`，另立 `identifier_assertion`。③`id_scheme` 增加 `granularity`；`version` 增加 `family_key`。④`source_record` 区分 harvest、snapshot、federated 三种来历。**2026-09-27 核对：05 §3.1 已全部采纳①–④，并已增补 `id_scheme` 的 `doi_family` 行（§9.1）与 `dedupe_candidate.method` 的 `user_report` 取值（§9.4）（05 §14.4）** | ①v1 D-007 与 02 都把 `preprint_of` 用作"只建关系、不合并"的边，沿用可让 v1 `paper_relation` 的 `preprint_of` 行语义不变地迁移。②05 的 `corpus.identifier` 以 `(scheme, value)` 为主键，是强合并锚点；OpenAlex 常把预印本与发表版并成同一个 W（§9.1），放进去会让 WP 与发表版被强制合并，违背 D-007 与 SI-16。增补项：bioRxiv 与 arXiv DataCite 的 DOI 覆盖全部修订（[LS §2.2.1][LS]、[NS §2.3.5][NS]），方案级粒度表达不了 | — | 05 |
| 15 | **与 02、08 的对齐** | 用户侧取回的协议沿用 08 与 02 的定义（RetrievalIntent、PolicyBundle、U2、U3、R16）；本文只提供候选生成、FulltextRecipe 与 v1 认证复用。robots 对用户侧自动请求的效力与 08 的 HC-29 一致（第 9 条）；不批量与 08 的 HC-32 一致（第 10 条） | 08 §5.1 已定义取回协议与字段（"字段以 08 定稿为准"）；02 的 AD-10 | 本文另定一套票据（FetchTicket）。已放弃：会造成两套协议 | 08 |
| 16 | **与 04 的对齐** | SCD 的能力键沿用 [RT §3.5.1][RT] 与 [04][04] 的词表（`kw.*`、`sem.*`、`filter.*`、`id.lookup.*`、`incr.since`、`sort.*`）；`serves`、`id_lookup`、`analyzer` 等字段按 04 的引用保留，并按 04 §7.7 的请求增补了文本谓词细分（`kw.phrase`、`kw.near`、`kw.prefix`、`kw.wildcard`、`kw.field.*`）、分面 `value_map`、`sort.relevance` 与 `residual_trust`（§4.2）；令牌桶键中的出口 IP 与 04 的 Quota Ledger 一致 | 04 把 Capability 词表的定义方写为 03，并以 03 的 SCD 口径作为 `supports` 边的支持等级 | 另立一套谓词命名。已放弃：会让路由器多一层映射 | 04 与本文 |
| 17 | **官方 WP feed 作元数据主通道的例外** | ECB（DOI 由欧盟出版局 RA 登记，不在 Crossref）、BIS（CB-RSS）、JMLR（无 DOI）的 feed 作元数据主通道；NBER back RSS 补 Crossref 10.3386 缺失的摘要。展示时，书目事实按 DL2 展示；feed 中的摘要按 B 类（DL3），单篇许可为 CC 的按 A 类（如 JMLR 的 CC BY）。其余 feed 只作新鲜度信号 | [SS §3][SS] 第 1 条把 Fed RSS、ECB RSS、BIS CB-RSS、NBER back RSS 列为"合规的官方通道"例外清单；[SS §2.4][SS]：ECB 的"唯一合规增量是其 RSS"；[CS §2.1.2][CS]：JMLR RSS 含标题、作者、摘要，Crossref 查不到 | 严格按 SI-13 与 08 R15（"feed 内容只作新鲜度信号，不展示"）。代价：ECB 与 JMLR 的新论文没有可展示的元数据来源，这两个 P1/P0 来源实际不可用 | **已裁决**：简报 R2-17；08 R15 已增列例外 |
| 18 | **具名 AI-UA 禁令对用户侧 `user_fetch` 的效力** | 与 08 R11 一致：主机对具名 AI UA 有禁令（站点级，或覆盖全文路径）时，平台侧与用户侧都不自动取回全文，只给 `open_in_tab` 与用户在场的一键保存；`tdm_api` 走官方 API 主机，不受影响（§6.2、§12.1、§12.3） | 08 R11。另一种读法：D-014 第 5 条规定 auth_gated 获取"不受本条限制"（理由是那是用户在自有权限内经正规登录的访问，与无授权的 AI 爬取性质不同）；用户侧扩展以用户本人的浏览器 UA 发请求，并非被点名的 AI 爬虫 | 按 D-014 第 5 条：R11 只约束平台侧与 LLM 输入，用户侧单篇 `user_fetch` 仍可签发（仍受 robots 的 `*` 组、R16 与护栏约束）。**影响面**：Atypon 族 robots 普遍具名封禁 GPTBot（[SS §2.2][SS]），INFORMS 对 AI UA 禁 `/doi/pdf`（[SS §2.1][SS] 第 16 条），Springer 站点具名封禁 20 多个 AI UA（同上）。因此按现行 R11，Atypon 与 Springer 平台上的选项 4 多半不可用，订阅全文主要靠官方 TDM API 或"打开后一键保存" | **已裁决**：简报 R2-18（不做扩展代发的 `user_fetch`，只提供"在出版社打开 + 打开后一键保存"，LQ-19 有结论后再议） |

---

## 20. 待决问题

| # | 问题 | 影响 | 建议裁定方与时机 |
|---|---|---|---|
| 1 | robots ADR：NCBI（E-utilities、FTP）、EBI FTP、ORCID、OSF、eLife、HAL、arXiv export、IACR 各自是否取得书面确认；以及 robots 对用户侧单篇操作的效力（§19 第 9 条） | 生命科学底座；若干 P1 源的后台模式 | 09 起草，用户确认；首个里程碑前 |
| 2 | OpenReview 平台服务账号的使用边界（简报 §7-12） | CS 会议的最新论文与评审状态 | **已裁决**（简报 R2-20）：书面确认前平台侧共享收割停用，ICLR、TMLR、COLM 等由 arXiv + DROPS dblp + 外链兜底；用户本人 token 只在用户侧供本人查询；V0 即发函。ADR 由 09 起草 |
| 3 | LQ-02、LQ-17：B 类摘要能否用于内部索引与嵌入；嵌入对应 Content-Signal 的哪个用途 | 检索召回；§8.4 默认 | 08 |
| 4 | LQ-01、LQ-05：B 类摘要的摘录长度 N；B 类能否作为共享派生输入 | 卡片摘要展示级别 | 08 |
| 5 | 简报 Q3 的触发条件：何时购买 Crossref Metadata Plus 或 OpenAlex Member | WatchKey 规模扩大后 polite 池与每日 $1 免费额度是否够用 | 09 按运行统计设触发阈值 |
| 6 | 快照在冷存储中的保留期；是否保留紧凑投影 | 存储成本与重扫能力 | 05 |
| 7 | FulltextRecipe 在 PolicyBundle 与 RetrievalIntent 中的承载字段；回执状态是否细分（§12.4 的建议） | 配方的分发与健康统计 | 08 |
| 8 | 私有空间的 E2E 加密与多设备同步 | 可选上传 | 05、08 |
| 9 | 中文生态补充调研（G-05）：CNKI、万方、维普的题录导出格式与合规边界 | §7.8 | 09 排期 |
| 10 | 嵌入模型选型（简报 Q7） | §11.3 | 首个评测里程碑 |
| 11 | 多用户平台上，venue 候审与身份候审由谁审核；时限多长 | 候审队列积压 | 02、09 |
| 12 | `oaipmh.arxiv.org` 的 robots（⚠ 待实测）；INFORMS 的 ToS 自动化条款（⚠ 只有摘要级证据） | arXiv 主通道；INFORMS 配方能否启用 | 实现前核验 |
| 13 | 原生分类叶子（MeSH、JEL、MSC、PhySH、ACM CCS）与 TSRG 节点的映射及维护 | 主题标签与路由 | 04 |
| 14 | 机构链接解析器（OpenURL、WAYFless）的配置由谁提供，是否需要机构目录（LQ-07 ⚠） | 全文选项 5 | 07、08 |
| 15 | 书面确认函的定稿与发出排期（要点已在 08 §4.5、清单已在 08 §4.6） | needs_confirmation 流程 | 09 |
| 16 | Percolator 的输入须包含"新增 Version 或匹配字段变更的已有 Work"（§10.7） | 关注期刊的用户能否收到"预印本先到、正式版后到"的论文 | **已裁决**（简报 R2-35）；04 §12.1 已按此改写 |
| 17 | （已裁决）兴趣并集中由私有文献库派生的细粒度键的并入门槛 | 小众兴趣用户的语料覆盖与隐私 | 简报 R2-19：须 ≥`k_cf` 个不同用户，否则只做该用户的按需查询（§10.5） |
| 18 | 08 R11 的适用范围：具名 AI-UA 禁令是否也约束用户侧 `user_fetch`（§19 第 18 条） | 出版托管平台上的用户侧全文可用面 | **已裁决**（简报 R2-18）；LQ-19 有结论后再议 |
| 19 | 08 R15 是否为按源登记的官方 WP feed 开例外（§19 第 17 条） | ECB、BIS、JMLR 的新论文能否展示 | **已裁决**（简报 R2-17），08 R15 已增列 |
| 20 | 01 FR-29 的验收"审核通过前不产生任何上游请求"，其范围宜限定为"新来源的主机"；自动 venue 的核验只查已登记来源（§2.5） | FR-29 的验收口径与 §2.5 是否一致 | **已裁决**（简报 R2-23）；01 FR-29 已改写 |
| 21 | 证据集体超期：本文用探针续期与错开复核期缓解（§6.5、§3.8 规则 13）；是否再设"宽限"状态（01 §16-12 已提） | 主干通道的可用性 | **已裁决**（简报 R2-16）：`review_overdue` 宽限 30 天（§6.2），V0 复核 |
| 22 | 05 增补 `id_scheme` 的 `doi_family` 行与 `dedupe_candidate.method` 的 `user_report` 取值（§9.7） | 身份模型与用户线索落表 | **已关闭**：05 §3.1.1、§14.4 已增补 |

---

## 21. 参考

**上游与同级文档**：
- [v2 设计决策简报][BRIEF]
- [01 愿景与需求][01]
- [04 检索与路由][04]
- [05 数据平台][05]
- [06 推荐与匹配][06]
- [07 前端交互][07]
- [08 合规、安全与隐私][08]
- [02 架构][02]；09（路线图）：文件名待定
- 配图：[v2-03-source-model.svg][DIAG]

**调研**：
- [调研综合][SYN]
- 来源类：[自然科学][NS]、[生命科学与心理学][LS]、[社会科学（经济、金融、管理）][SS]、[CS/AI][CS]、[聚合器与仓储][AG]
- 开源项目：[论文获取与检索开源项目][OSS]、[推荐开源项目][RO]
- 市场：[初创与产品][MK]
- 算法：[社交媒体推荐][SM]、[学术推荐与匹配][SR]、[检索、路由与索引][RT]
- 交互：[卡片流交互][UX]
- 内容：[论文理解与卡片内容][PU]
- 合规：[多用户平台合规][CP]

**名录**：[支持名录（source-directory）][DIR]

**一手来源**（本文直接引用，读取日期 2026-09-27）：
- RFC 9309 *Robots Exclusion Protocol*：§2.3.1.3（4xx 为 unavailable，爬虫可以访问）、§2.3.1.4（5xx 与网络错误为 unreachable，须假定全禁）、§2.4（缓存副本不宜使用超过 24 小时）。https://www.rfc-editor.org/rfc/rfc9309.html

**v1 文档**：
- 设计：[插件框架][v1-02]、[Open Access 模块][v1-03]、[Auth-Gated 模块][v1-04]、[Pipeline][v1-05]、[数据模型][v1-06]、[检索与过滤][v1-09]、[Browser-Fetch][v1-11]、[全文抽取][v1-12]、[认证框架详设][v1-AUTH]
- adapter：[adapter 总览][v1-ADP]、[聚合器][v1-AGG]
- 名录：[catalog 总览][v1-CAT]、[出版商与平台][v1-PUB]
- ADR：[决策日志][D-LOG]（D-002 至 D-039）

---

## 评审记录

第 1 轮（2026-09-27，视角 FEAS + EVID）：对照简报、[SYN][SYN] §2.1/§3/§6、NS、LS、SS、CS、AG、OSS、PU、CP 的相关章节，02、04、05、08 的现行草稿，以及 v1 的设计文档与代码（`venues/`、`src/paper_crawler/`）逐项核对，并就地修订本文与配图。RFC 9309 是本轮新读的一手来源（2026-09-27）。"转主 agent"的条目同时登记在 §20。

| 轮次 | 视角 | 问题 | 严重度 | 处理 |
|---|---|---|---|---|
| 1 | FEAS | §5.5 网关"disallow/unreadable 一律拒绝"与 §6.2、§6.8 的 Q4 on_demand（08 R5）互相矛盾：PubMed E-utilities、ORCID、eLife、HAL、arXiv export 的按需调用永远发不出去；AC-V1.5 同样与之冲突 | 高 | 已修：AccessDecision 增加 `robots_basis`（`api_conflict`、`written_confirmation`），网关只放行这两类按需请求并逐条审计，后台批量一律拒绝（HC-31）；AC-V1.5 改写 |
| 1 | FEAS | percolate 只处理"本批新 Work"。反例：预印本先入库成为 W，期刊 J 的正式版后到并入 W，关注 J 的用户永远收不到这篇"J 的最新论文" | 高 | 已修 §10.2、§10.7，加 §15.6 用例与 AC-V2.44；转主 agent：04 §12.1 的输入须同步（§20 第 16 条） |
| 1 | FEAS | PolicyOverride 能放宽 S4（ToS 禁令）与 S5（TDM/AI 保留），与 08 §4.4 纪律 2 冲突；`max(mode, ov.mode)` 使 denied 类书面答复无效；判定函数漏了许可门控；robots 与 ToS 漂移后覆盖不失效 | 高 | 已修：重写 §6.3（只抬升 S1–S3，收紧型并入结构性上限，补 `cap_license`，只评估 `paths_used` 非空的主机）与 §6.4（对齐 08 §4.4 的状态机、字段与 24 小时失效）；§15.3 属性测试与 AC-V1.7 同步 |
| 1 | EVID | T3 私有派生没有按来源门控（IEEE 禁止为 AI 使用创作演绎作品；Elsevier 把嵌入流水线也算 AI System，CP M10、LQ-06），且与 08 §5.4"platform 部署服务端 T3 默认关闭、私有全文 E2E"不一致 | 高 | 已修 §11.1、§12.7（在哪里算、按 `derivation.private_llm` 门控、SN 保存期）与 §15.9 |
| 1 | FEAS | S5 行与 08 R9–R11 不一致：具名 AI-UA 封禁给出 user_side，而 R11 只许 `open_in_tab`；缺 `search=no`（R10）；示例 A 与配方示例 2 仍对 INFORMS 签发 `user_fetch` | 中 | 已修 §6.2（S5 拆为 R9、R10、R11 三行）、§3.6 示例 A 的期望裁决、配方 `applies_to`、§12.1、§12.3（用户侧可用面的现实预期）；另一种读法列 §19 第 18 条，转主 agent（§20 第 18 条） |
| 1 | FEAS | 游标推进缺单调前提：Crossref 未要求按 `created` 升序，OAI-PMH 不保证按 datestamp 排序，逐页推进在崩溃后会漏数；OAI token 过期后"从最后落库的 datestamp 重启"同样会漏；Crossref deep cursor 5 分钟过期未处理 | 中 | 已修 §4.2、§5.4、§10.3（给出反例与推进规则）；§15.2 fixture 与 AC-V1.23 |
| 1 | FEAS | 身份"顺序无关"的论证有缺口：只带版本系标识符的记录挂到"到达时的最新修订"依赖顺序；健全检查依赖会变的收敛字段却不重评；"相互独立的第三方证据"未定义；拆分后哪一侧保留 id 不确定；并发 union 无锁 | 中 | 已修 §9.2、§9.3（按记录自身时间戳确定性挂接、变化即重评、按 source 计票、拆分规则、按 work_id 升序加行锁）；AC-V1.27 |
| 1 | FEAS | bioRxiv/medRxiv 与 arXiv DataCite 的 DOI 覆盖全部修订，但 `doi` 方案声明为 version 粒度，按方案记粒度的 05 表表达不了，会把各修订并成一个 Version | 中 | 已修：新增 `doi_family` 方案，由"前缀 → 粒度"映射在 normalize 改写（§9.1、§9.7）；转 05 增补（§20 第 22 条） |
| 1 | FEAS | 弱信号分块"年份 ±1 且首作者姓氏一致"会漏掉多数 WP 与发表版的配对（常隔数年、作者顺序会变）和晚两三年发表的预印本 | 中 | 已修 §9.4：年份窗按关系类别配置，改用姓氏集合重合，并做音译归一；阈值用 §15.7 金标集校准 |
| 1 | FEAS | 每周 `from-index-date` 补漏约放大百倍，没有成本边界，而放大系数只有 Nature Methods 一个样本 | 中 | 已修 §5.4、§10.4：叠加 `from-created-date ≥ now − L`，L 之外由季度快照对账，系数标 ⚠ 待 V0 实测 |
| 1 | FEAS | 187 行种子的证据同日核验，90 天后会同日超期，Crossref、arXiv、EPMC 的后台收割随之集体降为 on_demand（违背 P-09） | 中 | 已修 §6.5（探针复测一致即自动续期，`by=probe`）、§3.8 规则 13（复核期错开）；AC-V1.9；是否另设宽限状态转主 agent（§20 第 21 条） |
| 1 | FEAS | FeedInbox 的幂等写作"`(user_id, cluster_id)` 唯一"，与 05 §3.2.5（只追加、读取去重、主键 `offer_id`）和 04 §12.1 冲突；字段名也不一致 | 中 | 已修 §10.2、§10.7、§15.6 |
| 1 | FEAS | 同一 WatchKey 的并发任务没有互斥，会重复请求上游并争抢游标 | 中 | 已修 §10.3：procrastinate lock 以 WatchKey 为键，游标做比较交换；§15.2 增加"同键串行"契约 |
| 1 | FEAS | SCD schema 没有覆盖 04 §7.7 请求的字段：文本谓词细分、分面 `value_map`、`sort.relevance`、`residual_trust` | 中 | 已修 §4.2（词表与示例）、§19 第 16 条 |
| 1 | FEAS | 示例 C 把本通道不访问的 www.sciencedirect.com（`disallow`）列入 fulltext 通道，按"取最严"会把用户本人 key 的 `tdm_api` 判成 link_only；`ai_bot_sensitivity` 是通道级而非主机级 | 中 | 已修 §3.3（`paths_used` 为空的主机不参与裁决，AI-UA 规则改为逐主机 `robots[].ai_ua`）与示例 A、C |
| 1 | FEAS | lint 规则 6 只要求替补非空；只能 on_demand 的替补（如 export.arxiv.org）接不住 latest 的后台收割 | 中 | 已修 §3.8 规则 6 |
| 1 | FEAS | 伪代码不可落地：`run()` 的首个 `next()` 没处理零网络任务，也没处理挑战、预算耗尽等终止错误，没有逐页落库；`snapshot_filter` 把 OpenAlex source id 与 venue_id 混比，并使用快照中不存在的 owner prefix | 中 | 已修 §5.2、§10.5 |
| 1 | EVID | robots 缓存 7 天，与本文宣称的 RFC 9309 语义不符（§2.4：缓存副本不宜超过 24 小时）；robots.txt 的 4xx、5xx 状态码映射未定义 | 中 | 已修 §5.5、§3.4（一手来源 RFC 9309，2026-09-27 读取，登记在 §21）；AC-V1.5 改为"24 小时内有快照" |
| 1 | EVID | CP HC-06 只隐含在示例里：没有明文规定非 CC 许可 arXiv 条目的 e-print（PDF、源文件、抽取的图）不取、不存、不提供，也没写"不暗示背书"；HC-27 没有 lint 保障 | 中 | 已修示例 D、§11.9、§3.8 规则 12、§15.2 与 AC-V1.39 |
| 1 | EVID | CP HC-11(e)(f) 的"不复述原句、不替代原摘要、附原文链接、不把论断归到作者名下"没有进三道闸；自托管 LLM 未过 B-06 | 中 | 已修 §11.4（输出约束、模型许可、按 PU §2.6.3–§2.6.4 给出成本依据） |
| 1 | EVID | CP HC-01：联邦入库与兴趣并集可能把私域信息（查询文本、私有文献库）带入共享层的来历；"同一篇"线索、标签纠正与配方健康统计缺去标识与 `k_min` | 中 | 已修 §9.4、§10.3、§10.5、§11.2、§12.4；AC-V3.11；私有来源细粒度键的 `k_min` 门槛转 08（§20 第 17 条） |
| 1 | EVID | 08 R15（feed 只作信号、不展示）与本文把 ECB、BIS、JMLR 的 feed 作元数据主通道冲突，原文没有列为异议；SS §3 第 1 条恰把这些官方 feed 列为例外 | 中 | 已加 §19 第 17 条（附证据与代价）；转主 agent 与 08（§20 第 19 条） |
| 1 | EVID | 用户侧日上限写作"200 篇"，08 §5.1.5 为"200 次尝试，成败都计入" | 中 | 已修 §12.6、§15.9、AC-V3.19 |
| 1 | FEAS | 自动 venue 若取 Crossref 刊级记录的名称会误名（`/journals/1548-7091` 返回 Nature Chemical Biology）；`user_proposed` 的自动核验与 01 FR-29"审核通过前不产生任何上游请求"表述冲突；用户提案无限频 | 低 | 已修 §2.5、§13.1（名称取作品 container-title 众数；只经已登记来源核验；新来源审核前零请求、连 robots.txt 也不取）；FR-29 的口径转 01（§20 第 20 条） |
| 1 | FEAS | v1 迁移表漏了 `registry.py`、`adapter.py`/`types.py`、`errors.py`、`pipeline/cooldown.py`、`runner.py`/`stages.py`、`fetchio.py`、`preprint_report.py`、`obslog.py`/`sensitive.py`；quirks 去向不具体（`ai_bot_sensitive` 是合规事实，不能落进 `connector_params`；`crossref_date_field` 属于 ssrn） | 低 | 已修 §3.7、§14.2（逐模块、逐键，依据仓库实际文件） |
| 1 | FEAS | V1Bridge 在 platform 模式下如何处理 open_access 族的 `fetch_asset` 与 browser-fetch 横切件，原文未写 | 低 | 已修 §5.4：platform 模式一律不调用；共享 OA 全文只走 §11.9 的白名单路径 |
| 1 | FEAS | 新鲜度目标、EPMC 补查、arXiv HTML 取图缺少量化依据 | 低 | 已补 §10.9、§8.5、§11.9 的估算（标 ⚠） |
| 1 | EVID | 若干断言的证据等级未照调研标注：Crossref polite 池数值（公告加第三方观测，AG §4 Q4）、Unpaywall 每日 10 万次（AG §4 Q9）、AIS bepress OAI 端点（SS §2.2） | 低 | 已补 ⚠ |
| 1 | EVID | §19 第 14 条仍称 05 用 `published_as`、`source_record` 只有 channel，与 05 现稿不符（05 §3.1 已采纳本文词表与 `provenance`） | 低 | 已更新 §9.7、§19 第 14 条，只保留两项待 05 增补 |
| 1 | EVID | `display_scope` 映射漏了 V2（08 §3.3）；许可码与 05、08 的规范码（SPDX 加 `x-` 前缀）不一致；许可白名单漏了"公有领域"（HC-05）；HC-07 未挂到 08 RightsTag 与 05 列组 | 低 | 已修 §3.5、§8.1、§10.6、§11.9 |
| 1 | EVID | 缺 R5（GitHub 开源）在本文的具体承接与 B-06 许可门禁；ACM CCS、JEL 词表许可未核；pyzotero 为 Blue Oak 许可 | 低 | 已加 §5.6 复用与排除清单、§11.2 ⚠；pyzotero 须经许可 ADR |
| 1 | EVID | 未写"禁止为计算'用你的凭证'态而探测出版商站点"（08 §5.1.6）；SN 的 TDM UA 要求与保存期（NS §0 第 5 条，LS §0 第 7 条）未落到连接器；Fed 在 Crossref 有 DOI 且摘要 99%（SS §2.4），不该列为 feed 主通道 | 低 | 已修 §11.6、§5.4、§7.9、§12.7 |
| 1 | EVID | v1 PDF 与语料迁移没有区分 personal、platform 部署与 FR-85 门控；S2 预计算嵌入的输入权利不可知，却不在 LQ-02 回退范围内 | 低 | 已修 §14.4、§11.3、§15.8、AC-V2.20 |
| 1 | FEAS | 配图：fulltext 通道的 method 写了不存在的取值 `oa`；lint 条数、覆盖边界、R11、PoliteHttp 与 Egress 同名、Fed feed 与正文不一致 | 低 | 已修 `v2-03-source-model.svg`，经 XML 校验与无头浏览器渲染核对 |
| 1 | FEAS | PoliteHttp 与 02 的 P13 Egress Gateway 是同一组件的两个名字 | 低 | 已在 §5.1、§18 注明同一组件；中文名转 01 统一（04 已提） |
| 审计 | 一致性（2026-09-27） | 与简报 §10 不一致：族数与 `bulk_snapshot`、L2 `registry`、名录两字段、V0–V4、`k_min`、PoliteHttp 定位与令牌桶键、`review_overdue`、漂移分档、PubMed/OpenReview/SN/ADS 过渡口径、MSC2020、OA 静态页、WP feed 例外、兴趣并集门槛、私有 PDF 存放、personal OA 批量；§5.5 与 §0/§6.4 对确认通道后台收割的表述自相矛盾；TL;DR 上限未落数字 | 中 | 已修：按 R2-01/02/03/04/07/08/09/10/11/12/13/14/15/16/17/18/19/20/21/22/23/24/25/26/27/28/34/35/45/48 改写 §0–§20；新增 `BulkSnapshot` 族与 `storage_policy.cache_mode`；§19、§20 标注裁决状态（清单见 01 §一致性审计记录） |

[BRIEF]: 00-design-brief.md
[SYN]: ../../survey/00-survey-synthesis.md
[NS]: ../../survey/sources/natural-sciences.md
[LS]: ../../survey/sources/life-sciences-psychology.md
[SS]: ../../survey/sources/social-sciences-econ-fin-mgmt.md
[CS]: ../../survey/sources/cs-ai.md
[AG]: ../../survey/sources/aggregators-repositories.md
[OSS]: ../../survey/oss/paper-acquisition-and-search-oss.md
[RO]: ../../survey/oss/recommendation-oss.md
[MK]: ../../survey/market/startups-and-products.md
[SM]: ../../survey/algorithms/social-media-recsys.md
[SR]: ../../survey/algorithms/scholarly-recommendation-and-matching.md
[RT]: ../../survey/algorithms/retrieval-routing-indexing.md
[UX]: ../../survey/ux/card-feed-interaction.md
[PU]: ../../survey/algorithms/paper-understanding-and-card-content.md
[CP]: ../../survey/compliance/multi-user-platform-compliance.md
[DIR]: ../../catalog/source-directory.md
[DIAG]: ../../diagrams/v2-03-source-model.svg
[01]: 01-vision-and-requirements.md
[02]: 02-architecture.md
[04]: 04-retrieval-and-routing.md
[05]: 05-data-platform.md
[06]: 06-recommendation-and-matching.md
[07]: 07-frontend-interaction.md
[08]: 08-compliance-security-privacy.md
[v1-02]: ../../archive-v1.md#docs-design-02-plugin-framework-md
[v1-03]: ../../archive-v1.md#docs-design-03-open-access-module-md
[v1-04]: ../../archive-v1.md#docs-design-04-auth-gated-module-md
[v1-05]: ../../archive-v1.md#docs-design-05-pipeline-md
[v1-06]: ../../archive-v1.md#docs-design-06-data-model-md
[v1-09]: ../../archive-v1.md#docs-design-09-search-filter-md
[v1-11]: ../../archive-v1.md#docs-design-11-browser-fetch-md
[v1-12]: ../../archive-v1.md#docs-design-12-fulltext-extract-md
[v1-AUTH]: ../../archive-v1.md#docs-design-auth-framework-md
[v1-ADP]: ../../archive-v1.md#docs-design-adapters-readme-md
[v1-AGG]: ../../archive-v1.md#docs-design-adapters-aggregators-md
[v1-CAT]: ../../archive-v1.md#docs-catalog-readme-md
[v1-PUB]: ../../archive-v1.md#docs-catalog-publishers-platforms-md
[D-LOG]: ../decision-log.md
