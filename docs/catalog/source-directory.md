---
title: v2 来源支持名录（Source Directory）
status: draft
owner: opus5.5-design
updated: 2026-09-27
---

# v2 来源支持名录（Source Directory）

> **定位**：用户需求 R1"维护一张支持的名录"的正式载体（[简报][BRIEF] §1、§6.1-7）。本文是名录的**文档形态**：设计期手工维护；实现期由机读注册表 `registry/sources/*.yaml` 生成，注册表是单一事实来源（§8）。
> **上游约束**：[v2 设计决策简报][BRIEF]（B-01…B-06、P-01…P-09、§5 术语、§6.1、§8 Q1–Q7）。
> **证据层**：[调研综合][SYN] §3（187 行候选总表、合并口径、优先级裁决、学科统计、维护建议），以及五篇来源调研 [NS]、[LS]、[SS]、[CS]、[AG]；合规口径取 [CP]。本文**没有发出任何新的外部请求**，事实全部转引自上述调研，核验日期统一为 2026-09-26（UTC）。调研中标 ⚠ 的事实在此继续标 ⚠；◐ 表示二手或摘要级证据。
> **分工**：SourceSpec v2 schema、SCD、ConnectorFamily 接口与策略引擎由 [03] 定义；合规硬约束的全库编号由 [08] 统一登记（本文沿用 CP 的 HC-01…HC-28）；Query AST、TSRG 与路由由 [04] 定义。本文只回答"有哪些来源、各以什么方式接、到什么程度、受什么约束"，并规定名录的维护流程。

---

## 0. 结论速览

1. **规模**：名录共 **187 行**，行集合与综合 §3.2 一一对应。其中 L1 129 行（出版商与学会平台 44、预印本与工作论文 30、期刊平台 24、会议平台 31），L2 57 行，另有盗版源合并行 1 行。按简报 §6.1-7 与本任务要求分为 8 节；区域性 L1 来源（5 行）归入"中文与区域"一节。
2. **v2 状态**：`v2-P0` 36、`v2-P1` 63、`v2-P2` 44、`metadata-only` 26、`link-only` 2、`user-import-only` 3、`excluded` 13。逐行对照五篇来源调研后，**v2 状态与综合 §3.2 完全一致，本轮未改动任何一行**。
3. **v1 状态修正 17 行**：现为 `v1-implemented` 16、`v1-partial` 5、`v1-designed-only` 29、无 137（综合为 16/15/21/135）。
   - 9 行由"部分"改为无：NS 的"部分"只表示 v1 通用 `crossref` adapter 理论上可按 ISSN 枚举，这对所有 `crossref_delegated` 来源都成立；v1 并没有这些来源的 VenueSpec 或专用代码。
   - 7 行由"否"改为 `v1-designed-only`：它们已在 v1 catalog 登记。
   - `cepr_dp` 由"部分"改为 `v1-designed-only`：v1 `repec` 只映射 NBER `w` 系列（[DL] D-036）。
   - 明细见附录 A。
4. **接入工作量**：169 个非排除来源中：
   - 92 行的元数据/最新论文通道用到 `crossref_delegated`；出版商与期刊平台（§3.1、§3.3）的 63 个非排除行中，53 行的平台侧元数据通道只有 Crossref 委托（口径见 §4.1）。
   - 66 行只需登记 SourceSpec，不必为其单写 connector。
   - 93 行至少需要一个源专用或按源配置的 connector，其中 21 行经 `v1_bridge` 复用 v1 全部 20 个 adapter。
   - 10 行暂无 connector（待复勘或经他源旁路）。

   这与简报 §6.1-1"多数出版商期刊不需要写代码"一致。
5. **用户侧执行**：27 个非排除来源至少有一条通道在用户侧执行（`exec_side=U`）。它们全部是订阅全文、按用户 key 的 TDM/API，或用户自有 token（ADS、Lens、alphaXiv，以及服务账号确认前的 OpenReview）。平台出口从不代用户访问出版商（P-03、HC-03）。
6. **闸门**：66 行带至少一个闸门标记（§2.2）。影响首批落地的有四处：
   - `pubmed`（v2-P0）的 E-utilities 主机与 bulk 主机 robots 都是 `Disallow: /`（`pmc` 的 E-utilities 通道同受此限）。按简报 Q4 默认，书面确认前不能做后台批量，所以首批生命科学主干实际由 `europe_pmc`（REST 路径未被 robots 禁止，Crawl-Delay 10）、`pmc`（S3/OAI）与 Crossref 承担；`pubmed` 保持 v2-P0 并标 ⚑ROBOTS，NCBI 确认后启用（简报 R2-13）。
   - `openreview`、`tmlr`（v2-P0）的平台服务账号须书面确认（⚑ACCT）；确认前平台侧共享收割停用，由 arXiv 版本 + DROPS dblp 快照 + forum 外链兜底，用户自己的 token 只供本人查询（简报 R2-20）。
   - `chemrxiv`、`biorxiv`、`medrxiv`（v2-P0）处于平台迁移或端点异常（⚑DRIFT），以 Crossref 为主通道、原生 API 为补充（简报 R2-13 已采纳，§11 异议 8）。
   - 17 行受商用开关门控（⚑COMM），`platform.commercial=true` 时自动停用相应通道。
7. **学科覆盖**（§4.3）：
   - CS-AI 40 行（P0 14）、经济 34 行（P0 9）最强；金融 25 行（P0 7）。
   - 生物的 L2 骨干最完整。
   - 心理依赖 Crossref，而 APA 期刊在 Crossref 的摘要与参考文献覆盖都是 0%。
   - 地学材料只有 12 行（P0 5 行，全是跨学科出版商与预印本），中文/区域没有 P0/P1。这两组是主要缺口（§7）。
   - "管"组中的社会学、政治学只做了简述，按简报 R2-25 不在 v2.0 范围（教育学同）；Project MUSE、SMF、UW Press 三个平台上有调研 venue 但未勘察，按 R2-26 本轮不增行（§7 K-14、K-15）。
8. **代表性 venue 索引**（§5）：11 个学科组共 195 个 venue，每组不超过 20 个。数据全部取自调研映射表与附件；316 个 ISSN 已用脚本逐一在调研原文中比对，全部命中。
9. **维护**（§8）：注册表是单一事实来源；每条通道带 `evidence{url, verified_at}`，超过 90 天未复核进入 `review_overdue`，宽限 30 天后降为 on_demand 并标 `needs_confirmation`（简报 R2-16）；快变事实按季度复核；漂移探针告警按简报 R2-15 分档处置：robots 与 TDM 信号漂移立即降级，ToS 哈希变化宽限 7 天，元数据通道自身受影响时暂停并切换替补链。

---

## 1. 功能说明

### 1.1 用途与读者

本名录回答四个问题：

1. v2 支持（或计划支持）哪些来源；
2. 每个来源的元数据、最新论文、全文三条通道各怎么接，由谁执行；
3. 接到什么程度（v1 状态、v2 状态）；
4. 受哪些条款、限速与合规闸门约束。

| 读者 | 用途 |
|---|---|
| 产品与最终用户 | 对外"支持的来源"页面的内容来源；按学科查看覆盖与缺口 |
| [03] 来源与语料流水线 | connector 排期；SourceSpec v2 首版种子；策略引擎的闸门初值 |
| [04] 检索与路由 | SCD 与 `route_stat` 的初值：可下推谓词、限速、新鲜度阶梯、替补链 |
| [05] 数据平台 | 许可字段、`abstract_rights`、署名义务、凭证类型的来源 |
| [08] 合规 | HC 的逐源落点：商用开关、robots 冲突、用户侧执行、署名 |
| 09 路线图 | 按 v2 状态划定里程碑范围；验收标准草案（附录 B） |

### 1.2 范围与非目标

- **范围**：五篇来源调研登记、经综合 §3.1 合并去重后的 187 行候选来源。学科覆盖简报 R1 的全部范围（数学、物理、化学、生物、心理；经济、金融、商业管理；计算机与 AI），并补充地学材料与中文/区域两个横向组。
- **非目标**：
  - 不定义 SourceSpec v2 schema 与 ConnectorFamily 接口（[03]）；
  - 不登记全库 HC 编号（[08]）；
  - 不是 venue 全量名录：venue 是独立于 Source 的实体（简报 §5），§5 只给代表性索引；
  - 不含实现代码；不对法律问题（CP 的 LQ-xx）下结论。

### 1.3 名录层落实的简报原则

| 原则 | 名录中的体现 |
|---|---|
| Source 与 Venue 分离（简报 §6.1-1） | 本表按来源登记；venue 只出现在 §5 索引，并指回 `source_id` |
| 只为有官方 API 或协议通道的站点写代码（§6.1-4） | WAF 或 robots 全禁的站点，ConnectorFamily 只有 `crossref_delegated` 或"外链"；全文最多"用户侧单篇"。对"无 API 的 OA 论文集静态页"的解释见 §11 异议 3 |
| 先收割、后联邦（P-01） | "最新通道"列只描述收割与增量通道；联邦检索能力由 SCD 描述（[04]） |
| 用户自有凭证、取回在用户侧（P-03） | exec_side 列；订阅全文与按用户 key 的 API 一律 `U` |
| 全局礼貌（P-04） | 限速列只记书面或实测限额；运行时一律由响应头驱动 |
| 最严者为准（P-05） | 闸门标记；robots 不可读按禁止处理 |
| 可降级（P-09） | 元数据通道列尽量给出替补（Crossref → EPMC → OpenAlex 等） |

---

## 2. 名录约定

### 2.1 状态：两个正交字段

**`v2_status`（v2 目标状态）**

| 值 | 含义 | 最低证据要求 | 对调度与展示的效果 |
|---|---|---|---|
| `v2-P0` | v2 首批必须接入 | 至少 1 条合规元数据通道有一手证据；闸门要么不阻断，要么有降级路径 | 进入首批里程碑与验收 |
| `v2-P1` | 首批之后的第一批 | 同上 | 第二批 |
| `v2-P2` | 按需接入 | 有候选通道，证据可以不全（常带 ⚑RECHECK） | 由用户需求触发 |
| `metadata-only（Px）` | 只收元数据；全文零自动化（外链、OA 链或用户侧单篇） | 元数据通道合规；全文条款禁止或无合规通道 | 括号内为登记优先级（简报 §6.1-7 允许的写法）；全文按钮只外链 |
| `link-only` | 不收录元数据，只按标识符生成外链 | — | 详情页"在 X 中打开" |
| `user-import-only` | 平台零自动化，只接受用户手动导出的题录 | — | 导入向导 |
| `excluded` | 因红线、条款、授权或无通道而排除；可带限定语，如"用户自带 key 私用可选" | — | 调度器与路由器不可选 |

**`v1_status`（v1 实现状况）**

| 值 | 含义 | 与综合 §3.2"v1"列的对应 |
|---|---|---|
| `v1-implemented` | v1 有生产 adapter（entry point 已注册），并已注册 VenueSpec 或作为 enrich/resolve 通道运行 | 是 |
| `v1-partial` | v1 有 adapter 代码，但覆盖面窄、已出列，或只覆盖该来源的一部分 | 部分（本文口径收窄，见附录 A） |
| `v1-designed-only` | v1 只有设计文档或 catalog 登记，没有实现 | 设计 |
| `—` | v1 无任何对应物 | 否 |

**与简报 §6.1-7 的关系**：简报 R2-10 已采纳两字段方案：`v1_status` 取 `v1-implemented` / `v1-partial` / `v1-designed-only` / `—`，`v2_status` 取简报 §6.1-7 枚举中其余 7 个值（与 [03] §2.6、§3.2 及 05 `corpus.source` 一致）。注册表中若须输出单值，按"`v2_status` + v1 徽标"渲染。

### 2.2 闸门（Gate）标记

闸门写在"v2 状态"列的第二行；只影响某条通道时，在括号里注明范围。

| 标记 | 含义 | 策略引擎的默认处置 | 依据 |
|---|---|---|---|
| ⚑ROBOTS | 文档化 API 或 bulk 主机与 robots 冲突（robots 全禁或禁关键路径，而官方文档邀请程序化访问）；或声明的协议通道与 robots 冲突 | 标 `needs_confirmation`。书面确认与 robots 统一 ADR 落定前，只按文档限速做低频或用户触发调用，不做后台批量 | 简报 §7-2、Q4；[SYN] T8、G-03 |
| ⚑ACCT | 需要平台服务账号，而 ToS 要求一人一号 | 书面确认前只用用户自有 token | [CS] §3-9、§4-3；简报 §7-12 |
| ⚑COMM | 数据、API 或 TDM 条款限非商业，或商用须另获许可或书面确认 | `platform.commercial=true` 时自动停用对应通道 | [CP] HC-23；简报 §7-9 |
| ⚑LIC | 某通道须先取得数据许可或授权 | 取得前该通道不可用，其余通道不受影响 | CORE 许可、NBER 批量文件、APS Harvest 全量 |
| ⚑BUDGET | 按量计费 | 进入美元预算桶；超额时降级为快照或本地数据 | [AG] §2.2.2 |
| ⚑DRIFT | 平台迁移、端点异常或产品停办进行中 | 以替代通道为主；漂移探针高频监测；恢复后重勘 | [NS] §3-9；[LS] §3-11；[SS] §3-14 |
| ⚑RECHECK | 通道未核（⚠）、站点当前不可达或维护中，或 robots 不可读 | 启用前复勘并补证据；robots 不可读时按最严处理（零自动化） | P-05；[SYN] G-05、G-11 |
| ⚑SA | 数据为相同方式共享（ShareAlike）许可 | 派生数据集若对外发布须沿用同一许可，须法务评估 | [NS] §4-10；[CS] §2.7 |

### 2.3 列定义

| 列 | 内容 | 取值或记法 |
|---|---|---|
| source_id | 全库唯一的 snake_case 标识；沿用 v1 id 与综合 §3.1 别名表 | 例：`wiley` 合并了 `wiley_vch`、`wiley_online`、`wiley_wol` |
| 名称 | 常用名，括号内为承载的品牌或子站 | — |
| 层级类型 | 简报 §6.1-1 的两层来源模型，另加简报 R2-11 的 L2 子类型 `registry` | `L1-publisher`、`L1-preprint`、`L1-journal_platform`、`L1-conference_platform`、`L2-aggregator`、`L2-repository`、`L2-registry`；括号内为补充说明，如"DOI 注册""引文" |
| 学科 | 该源在调研中实际覆盖的学科组 | §2.4 代码 |
| ConnectorFamily | 按通道列出所需 connector 族 | §2.5 |
| exec_side | 各通道的执行位置 | `P`、`U` |
| 元数据通道 | 首选通道、关键端点、Crossref 摘要覆盖（current） | — |
| 最新通道 | 增量或新鲜度通道；feed 只作信号 | — |
| 全文通道与门控 | OA 或订阅、许可门控、共享边界 | 共享层 / 私有 / 外链 |
| 认证 | 凭证类型 | 无 / 部署级 / 用户级 / 机构会话（用户侧） |
| 限速/ToS 要点 | 书面或实测限额、robots、条款要点 | 各行只写本源特有部分，共同规则见 §2.7 |
| v1_status | §2.1（简报 R2-10） | — |
| v2_status | §2.1 状态，第二行为闸门（简报 R2-10） | — |
| 证据 | 调研文档与章节 | §2.6 |

### 2.4 学科代码

| 代码 | 学科组 | 说明 |
|---|---|---|
| 数 | 数学（含统计、概率） | — |
| 物 | 物理与天文 | — |
| 化 | 化学 | 综合的"化"包含材料；本文把材料移入"地材" |
| 地材 | 地学与材料 | 本文新设；材料标注依据 [NS] §2.3.6、§2.8.4 |
| 生 | 生物、生命科学与医学 | — |
| 心 | 心理（含认知科学） | — |
| 经 | 经济（含计量、发展、公共与政策） | 综合的"经"是经济与金融合并，本文拆开 |
| 金 | 金融（含量化金融） | 会计归"管"，与 UTD24 的分组一致 |
| 管 | 商业与管理（含会计、营销、信息系统、运营与 OR，以及社会学、政治学） | — |
| CS | 计算机与 AI | — |
| 全 | 跨学科、通用 | 统计时只计入"跨学科"一行（§4.3） |
| 区 | 中文/区域 | 横切标记，不算学科 |

每行的学科标注取自来源调研名录表的"学科"列，综合 §3.2 的合并结果作底；本文另作的 8 处修正见附录 A。

### 2.5 通道与执行记法

- **通道前缀**：`M` 元数据、`L` 最新论文、`F` 全文；`ML` 表示同一通道兼任元数据与最新论文。
- **ConnectorFamily 族名**取简报 §5 与 R2-11：`aggregator_api`、`oai_pmh`、`feed`、`crossref_delegated`、`bulk_snapshot`、`platform_family:<族>`、`official_tdm_api`、`site_special`；v1 adapter 经 `v1_bridge(<目标形态>)` 复用。此外补充四种记法：
  - `bulk_snapshot`：官方快照、年度文件与批量 dump 的导入族（简报 R2-11 新增，接口见 [03] §5.3–§5.4）。
  - "经 `x`"：由另一行来源的 connector 承担，本行只登记。例：`cepr_dp` 经 `repec`。
  - "OA 链"：经 OA 定位链在平台侧取回，链上的来源包括 `openalex` 的 `best_oa_location`、`unpaywall`、`pmc`、`europe_pmc`、`scoap3_repo` 等。只对逐篇许可白名单内的作品执行（HC-05），其余降为外链。
  - "外链"：只生成"在出版社打开"的链接（简报 P-03 的平台默认动作）。
  - "用户侧单篇"：由浏览器配套扩展或本地代理在用户本人会话中单篇取回（P-03、HC-03）。对 robots 具名禁止 AI UA 的站点，只提供"在出版社打开 + 打开后一键保存"，不做扩展代发的 `user_fetch`（简报 R2-18）。
- **exec_side**：`P` = platform，`U` = user；"P/U"表示同一通道按内容分流，例如 OA 内容在平台侧、订阅内容在用户侧。
- **feed 标"信号"**时只用来触发 Crossref/API 补全，不展示 feed 内容（[NS] §3-6、[LS] §3-6）。例外（简报 R2-17）：在 SourceSpec 中按源登记、robots 允许、ToS 无禁止的官方 WP feed（ECB、BIS、JMLR 等）可作元数据主通道。
- ConnectorFamily 是**初始归类**，接口与粒度以 [03] 为准。

### 2.6 证据写法

- `[NS] §2.2.1` 指 natural-sciences 调研第 2.2.1 节；"核验 X"指该调研"核验记录"节中的条目；`[SYN]` 为调研综合；`[CP]` 为合规调研；`[DL]` 为决策日志；`[v1-*]` 为 v1 catalog 文档。
- 链接只指向文件，章节号写在文字里，与综合采用同一约定，以免锚点随标题改动失效。
- 核验日期均为 2026-09-26（UTC）。⚠ 表示未核验；◐ 表示二手或摘要级证据。

### 2.7 共同规则（对所有行默认适用，各行不再重复）

1. **一个上游一个平台身份**：诚实 UA 并附联系邮箱。限速由响应头驱动，以书面限额为上限，按五元组 `(source, host, 上游请求类, 凭证, 出口 IP)` 设全局令牌桶，平台侧只经 Egress Gateway（出站网关）出站（P-04、HC-10、SI-37；简报 R2-08）。禁止多 key、多 IP 规避限额，禁止对同一第三方主机发对冲请求。
2. **robots 先行**：HTTP 层在请求前检查 robots 快照并检测挑战页，由框架强制执行（SI-38）；遇挑战即停，转 BLOCKED（HC-26）。
3. **最严者为准**：文档化 API、bulk、robots、ToS、tdmrep 五类信号冲突时取最严（P-05）。
4. **全文**：
   - 逐篇许可白名单：CC BY、BY-SA、CC0、公有领域可进共享层；NC 视商用开关；ND 只能原样分发；许可未知一律不可共享（HC-05）。
   - auth-gated 全文只在用户侧、由用户显式触发、单篇取回，不预取、不共享、不跨用户去重（P-03、HC-02/03/04）。
5. **摘要按权利分级**（HC-08）：
   - A 类（CC0 或开放许可）可全文展示；
   - B 类（有版权但公开分发，如 Crossref、PubMed 摘要）最高展示到 DL3（CP 的 V3，简报 R2-03）；默认纳入内部词法索引与嵌入（不展示），可逆重建（简报 R2-21）；
   - C 类（出版商 API 的个人许可摘要）不进共享层；
   - 卡片优先使用 arXiv 版摘要。
6. **署名**：来源声明与署名由 provenance 字段自动渲染（HC-24）。
7. **证据时效**：每条通道带 `evidence{url, verified_at}`，超过 90 天未复核的进入 `review_overdue`：漂移探针持续为绿、证据其余字段完整时宽限 30 天并维持原模式，宽限结束或任一探针告警即降为 on_demand 并标 `needs_confirmation`（简报 R2-16；§8.5）。

---

## 3. 总表（187 行）

分节说明：
- 按本任务规定分为 8 节。每行只出现一次；排除类来源放在其自然所属的节，§6 另给排除视图。
- 区域性 L1 来源（`chinaxiv`、`ccs_chemistry`、`sciengine`、`wulixb`、`jstage`）统一归入 §3.8。
- 节内顺序大体沿用综合 §3.2：先高优先级、后长尾。

> 实现任何 connector 之前，必须回到"证据"列所指的调研原文，复核端点、限速与条款（综合 §1.6、§3 引言）。表中通道描述为控制列宽做了压缩。

### 3.1 L1 出版商与学会平台（43 行）

出版商与学会自营平台。多数行的元数据只靠 `crossref_delegated`；全文按许可分为 OA 链、用户侧单篇或外链。

| source_id | 名称 | 层级类型 | 学科 | ConnectorFamily | exec_side | 元数据通道 | 最新通道 | 全文通道与门控 | 认证 | 限速/ToS 要点 | v1_status | v2_status | 证据 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `elsevier_sd` | Elsevier ScienceDirect（含 Cell Press） | L1-publisher | 数 物 化 地材 生 心 经 金 管 CS | ML: crossref_delegated<br>F: v1_bridge(official_tdm_api) | ML: P<br>F: U | Crossref 按 ISSN（10.1016；摘要约 0%；CS 刊只认 print ISSN）+ PubMed（生医）；摘要经 OpenAlex/PubMed 补齐 | Crossref `from-created-date`；`rss.sciencedirect.com` robots 全禁，不轮询；Cell Press `current.rss` robots 允许（仅新鲜度信号） | 订阅/混合 OA（Cell 系 2026 年即时 CC 约 36–53%，按条许可门控）；订阅全文只经 Article Retrieval API（用户 key），私有、不共享；TDM 外发片段 ≤200 字符（HC-25） | 用户 API key（+insttoken）；机构 IP | SD robots `*` Disallow /，具名禁 ClaudeBot/claude-code；API 50k/周·10 rps（TDM key 不限周配额）；key 不得转让披露；API 内容不进共享 LLM（HC-11c）；TDM 限非商业 | v1-implemented（`elsevier_sd`） | v2-P0<br>⚑COMM | [NS] §2.2.1、§2.8；[LS] §2.4.1、§2.8；[SS] §2.1、§2.3；[CS] §2.2-D；[CP] §2.3.1 |
| `wiley` | Wiley Online Library（含 Wiley-VCH、学会子域 sms./myscp.） | L1-publisher | 数 物 化 地材 生 心 经 金 管 | ML: crossref_delegated<br>F: v1_bridge(official_tdm_api)；页面兜底 platform_family:atypon | ML: P<br>F: U | Crossref（10.1002/10.1111；理科样本摘要 61–93%，经管 64–90%） | Crossref 增量；`/feed/{eissn}/most-recent` robots 允许（信号）；Atypon `/action`、`/rss` 禁 | 订阅/混合；TDM API（用户 token，受订阅 entitlement 约束）；私有 | 用户 TDM token；机构 SSO | TDM 3 篇/s 且 60 次/10 min；robots Crawl-delay 1，禁 GPTBot/Google-Extended；tdmrep.json 被 CF 挑战；TDM 限非商业 | v1-implemented（`wiley`） | v2-P0<br>⚑COMM | [NS] §2.2.1；[LS] §2.4.16；[SS] §2.3；[CP] §2.3.1 |
| `springer_link` | Springer Nature Link（Springer、BMC、EMBO Press、Palgrave、Birkhäuser） | L1-publisher | 数 物 化 生 心 经 金 管 CS | ML: crossref_delegated<br>M+F: official_tdm_api（SN Meta/OA/TDM API） | ML: P<br>API: U | Crossref（10.1007/10.1057 等；摘要差异大：LNCS 约 3%，期刊样本 22–99%；EMBO J、BRM 须 eISSN）；SN Meta API 摘要限个人使用（C 类，只进本人私域） | Crossref 增量；`search.rss` 不在 robots 白名单，不用 | OA API（CC BY）；订阅：直接下载 ≤1 req/s 不另收 TDM 费，TDM API 另收费（150/min）；只存机构内部、不得第三方访问、存到项目结束；私有 | 用户 api_key；机构 IP/SSO | OA/Meta 免费档 100/分·500/日；禁多账号多 key 规避限额；TDM UA 须含 `TextDataMining`；TDMRep `tdm-reservation: 1`；robots 白名单外全禁、具名禁 AI UA；TDM 限非商业 | v1-designed-only（catalog `springer`） | v2-P0<br>⚑COMM | [NS] §2.2.1、§2.3.4；[LS] §2.4.2；[SS] §2.3；[CS] §2.1.3；[CP] §2.2.1、§2.3.1 |
| `nature_portfolio` | Nature Portfolio（nature.com） | L1-publisher | 物 化 地材 生 心 | ML: crossref_delegated；L 另用 feed<br>F: official_tdm_api（同 SN） | ML: P<br>F: U | Crossref（摘要 10–47%；Nature Methods 刊记录错挂，按 works 校验）+ PubMed；SN Meta API（C 类） | `nature.com/{code}.rss`（RSS 1.0，robots 允许，仅信号）+ Crossref 增量 | 订阅 + 部分 OA（Nat Commun 全 OA；Nature 2026 年 656/3,312 为 CC）；TDM 同 SN 条款；私有 | 机构；用户 api_key | robots 具名禁 anthropic-ai/ClaudeBot 等；TDMRep 同 SN；文章页 cookie 跳转 idp | — | v2-P0<br>⚑COMM | [NS] §2.2.1、§2.3.4、§2.8.4；[LS] §2.4.2、§2.8.1 |
| `oup_academic` | Oxford Academic（OUP） | L1-publisher | 数 物 生 心 经 金 管 | ML: crossref_delegated<br>F: v1_bridge(platform_family:silverchair) | ML: P<br>F: U | Crossref（10.1093；摘要 78–99%；Child Development 已转入 OUP，须 eISSN） | Crossref 增量；`/rss/site_*` robots 允许（信号） | 订阅/混合（NAR、Bioinformatics、MNRAS 等全 OA，逐篇许可）；无公开 TDM API；订阅全文用户侧单篇 | 机构 SSO（用户侧） | robots 无 AI 条目（仅 UA 008 全禁）；页面 CF 质询 | v1-implemented（`oup_silverchair`） | v2-P0 | [NS] §2.2.1；[LS] §2.4.10；[SS] §2.3 |
| `cambridge_core` | Cambridge Core（CUP） | L1-publisher | 数 物 心 经 金 管 | ML: crossref_delegated<br>F: site_special（用户侧单篇） | ML: P<br>F: U | Crossref（10.1017；摘要 76–99%） | Crossref 增量（robots.txt 被 CF 挑战，不读站点 feed） | 订阅/混合（Forum Pi/Sigma 全 OA）；非商业 TDM；个人或集体每小时 >500 PDF 可撤销访问；私有 | 机构 | robots.txt 本身 403 CF 挑战（v1 2026-07-20 为 200，已漂移）→ 站点零自动化；用户侧设远低于 500 PDF/时的硬顶 | v1-designed-only（catalog `cambridge`） | v2-P1<br>⚑COMM | [NS] §2.2.1、§2.3.4；[LS] §2.4.11；[SS] §2.1、§2.3；[CP] §2.3.1 |
| `tandf_online` | Taylor & Francis Online | L1-publisher | 数 物 化 心 经 金 管 | ML: crossref_delegated<br>F: platform_family:atypon（用户侧单篇） | ML: P<br>F: U | Crossref（10.1080；Mol. Phys.、QF、JMIS、C&E 等摘要 0%） | Crossref 增量；`/feed/rss/{code}` robots 允许（信号）；`/action/showFeed` 禁 | 订阅/混合（C&E 2026 年 44% CC）；订阅者非商业 TDM（STM 模型许可，邮件报备）；私有 | 机构 | robots Crawl-delay 1，禁 `/action`、`/rss`、`/doi/epdf/`；只具名 GPTBot；tdmrep.json 被 CF 挑战 | v1-designed-only（catalog `tandf` ⚠） | v2-P1<br>⚑COMM | [NS] §2.2.1；[LS] §2.4.15；[SS] §2.3；[CP] §2.3.1 |
| `sage_journals` | SAGE Journals（含 APS 心理刊、AMA 营销刊） | L1-publisher | 心 管 | ML: crossref_delegated<br>F: platform_family:atypon（用户侧单篇） | ML: P<br>F: U | Crossref（10.1177；摘要 39–99%，ASQ 39%；带 TDM link） | Crossref 增量 | 混合（Psych Sci 2026 年 61% CC；AMPPS 全 OA）；合法可访问内容的非商业 TDM 无需另签，AI 用途须另获许可；私有 | 机构 | TDM 许可页限速：PT 工作日 0–12 时 1 次/6 s、其余 1 次/2 s（◐）；`journals.sagepub.com` robots 未核（本机 TLS 中断） | v1-designed-only（catalog `sage`，仅 POM） | v2-P1<br>⚑COMM ⚑RECHECK | [LS] §2.4.14；[SS] §2.3、核验 S5 |
| `aaas_science` | Science / AAAS（Science、Science Advances） | L1-publisher | 全 | ML: crossref_delegated；L 另用 feed<br>F: OA 链（Sci Adv 经 PMC）；Science 主刊用户侧 | ML: P<br>F: P/U | Crossref（10.1126；摘要 85–98%）+ PubMed | `/action/showFeed`（robots 明确 Allow，信号）+ Crossref | Science 订阅（2026 年 101/1,563 带复用许可，部分延迟 365 天）；Science Advances 全 OA（经 PMC） | 机构 | robots 具名禁 anthropic-ai、GPTBot 等；政策页 403 ⚠；TDM 限非商业、合理速率（二手 ◐） | — | v2-P1 | [NS] §2.2.1、§2.3.4；[LS] §2.4.3 |
| `pnas` | PNAS | L1-publisher | 全 | ML: crossref_delegated；L 另用 feed<br>F: OA 链（PMC） | P | Crossref（10.1073；摘要 85%）+ PubMed | `/action/showFeed`（robots Allow，信号）+ Crossref | 2026 年 3,649/3,688 带 CC（多为 BY-NC-ND）；PMC 覆盖 98%（Release Delay 6 个月）→ 全文走 PMC，零出版商接触 | 无（经 PMC） | robots 只具名 GPTBot，禁 `/doi/epdf/` 等 | — | v2-P0 | [NS] §2.2.1、核验 B；[LS] §2.4.4；[SYN] §3.4 |
| `royal_society` | Royal Society Publishing（Proc A/B、Phil Trans、RSOS） | L1-publisher | 数 物 生 | ML: crossref_delegated<br>F: OA 链（PMC）；订阅部分用户侧 | ML: P<br>F: P/U | Crossref（10.1098；摘要 89–99%；Proc B 有 p/e 两条刊记录，须双查） | Crossref 增量（站点 RSS 未测 ⚠） | 8 种订阅刊 2026 年 S2O 转 OA（门槛已达成）；Proc B、RSOS 2026 年事实上全 OA（CC BY）；PMC 覆盖高 | 无/机构 | Silverchair（2025-12 上线）模板 robots，无 AI 专条、无 Crawl-delay | — | v2-P1 | [NS] §2.2.1、核验 C；[LS] §2.4.18；[SYN] §3.4 |
| `annual_reviews` | Annual Reviews | L1-publisher | 生 心 经 金 管 | ML: crossref_delegated<br>F: OA 链 | P | Crossref（10.1146；摘要 93–96%） | Crossref 增量（RSS 被 CF 挑战） | S2O：当年卷多为 CC（Annu Rev Psychol 2026 年 25/34 CC BY），逐篇许可 | 机构 | robots Crawl-delay 2，禁 `/deliver/`；平台为 Ingenta Edify（◐） | v1-designed-only（catalog `annual_reviews` ⚠，T3） | v2-P1 | [LS] §2.4.12；[SS] §2.3、核验 #37 |
| `mdpi` | MDPI | L1-publisher | 数 物 化 地材 生 心 | M: crossref_delegated + oai_pmh（`oai.mdpi.com`）<br>L: crossref_delegated<br>F: OA 链 | P | Crossref（摘要与 license 均 100%）；OAI-PMH 只按文章类型分 set，无按刊 set | Crossref 增量；OAI `from` | 全 OA（CC BY）→ 逐篇许可白名单后可进共享层；PMC 覆盖约 100% | 无 | www 与 robots.txt 均 Akamai 403 → 站点零自动化；OAI 间歇 504（须长超时退避）；体量大，须过载护栏 | — | v2-P1 | [NS] §2.2.1、核验 D；[LS] §2.4.8 |
| `frontiers` | Frontiers | L1-publisher | 生 心 | ML: crossref_delegated；L 另用 feed<br>F: OA 链（PMC） | P | Crossref（摘要 90–92%，全为 CC BY） | `/journals/{slug}/rss`（robots 允许，信号）+ Crossref | 全 OA（CC BY）；PMC 覆盖高 | 无 | robots `*` Allow /；条款页未读到 ⚠ | — | v2-P1 | [LS] §2.4.7 |
| `plos` | PLOS | L1-publisher | 生 心 | M: site_special（PLOS Search API）+ crossref_delegated<br>L: site_special<br>F: OA（allofplos/PMC，平台侧） | P | 官方 Search API（Solr，无 key）+ Crossref（须 eISSN）；allofplos 全量 XML | API `publication_date` 日窗；`/{journal}/feed/atom`（robots 允许） | 全 OA（CC BY，个别 CC0）→ 可进共享层；JATS | 无 | API 10 次/分、300/时、7,200/日、≤5 并发、≤100 行/请求，超限封 IP；站点 Crawl-delay 30 | — | v2-P1 | [LS] §2.4.6 |
| `apa_psycnet` | APA PsycNet（APA 期刊） | L1-publisher | 心 管 | ML: crossref_delegated<br>F: —（外链） | ML: P | Crossref（10.1037；摘要与参考文献均 0%）+ PubMed（部分）；另开放用户导入 RIS/PsycInfo 导出 | Crossref 增量（无合规 feed） | 订阅（少量 CC；AM 许可延迟 365 天）；PsycInfo 为订阅库，不做任何自动化；全文只外链/用户自取 | 机构/个人订阅 | psycnet robots `*` Disallow /；apa.org 为 Imperva；APA Thesaurus 与分类码专有，不嵌入 | — | metadata-only（P2） | [LS] §2.4.13；[SS] §2.3；[AG] §2.6 |
| `cshl_press` | CSHL Press（Genome Research、Genes & Dev） | L1-publisher | 生 | ML: crossref_delegated<br>F: OA 链（PMC） | P | Crossref（摘要 98%，无 license 元数据；DOI 字符串 10.1101 与旧 bioRxiv 相同，须按 member/type 路由） | Crossref 增量（RSS 302 到登录） | 订阅/延迟开放 ⚠；PMC 覆盖 100% → 全文走 PMC | 机构 | HighWire（Drupal + SAMS Sigma）+ CF | — | v2-P2 | [LS] §2.2.1、§2.4.17 |
| `hogrefe` | Hogrefe | L1-publisher | 心 | ML: crossref_delegated<br>F: —（外链） | ML: P | Crossref（10.1027；摘要 71–81%） | Crossref 增量（robots 禁 `/rss`） | 混合（2026 年全社 CC 119/357，逐篇许可）；订阅内容用户自取 | 机构 | Atypon 模板 robots，Crawl-delay 1，GPTBot 全禁；European Psychologist 的 PubMed 覆盖为 0 | — | metadata-only（P2） | [LS] §2.4.18、§2.7 |
| `ucpress_online` | UC Press 期刊（Collabra: Psychology） | L1-publisher | 心 | ML: crossref_delegated<br>F: OA 链 | P | Crossref（摘要 99%） | Crossref 增量 | 全 OA（CC BY） | 无 | robots 未取 ⚠ | — | v2-P2<br>⚑RECHECK | [LS] §2.7、§2.8.2 |
| `aps` | American Physical Society（Physical Review 系列） | L1-publisher | 物 | M: site_special（APS Harvest）+ crossref_delegated<br>L: crossref_delegated；RSS 仅信号<br>F: site_special（Harvest OA 集） | M/L/F(OA): P<br>F(订阅): U | Harvest API（OA 集免认证：摘要、PhySH、arXiv 号、许可）+ Crossref（10.1103；PRL 摘要 0.29、PRB 0.11；历史 ISSN 须合并；新 DOI 为不透明后缀） | Harvest `from/until` + Crossref；RSS 小时级但"Personal use only"，只作信号 | PRX 系全 OA、SCOAP3/CC BY 单篇 → 共享层；其余订阅走用户侧；ToS 禁系统化下载 | OA 集无；全量需 JWT/IP/CHORUS | robots（2026-09-23）`*` 只禁 /search 等；ToS 禁 robots 与网络加速器；APS Data Sets 仅限申请人 | — | v2-P0<br>⚑LIC（仅全量 Harvest） | [NS] §2.2.1、§2.3.1、核验 A/B |
| `iop` | IOP Publishing（含 AAS 天文刊、JPCS） | L1-publisher | 物 | ML: crossref_delegated<br>F: OA 链（SCOAP3/arXiv/OpenAlex）/外链 | ML: P | Crossref（10.1088、AAS 10.3847；摘要 0.98–1.00，TDM link 1.00，理科最完备） | Crossref 增量（站点 RSS 在 robots 全禁范围，不用） | OA（NJP、JPCS、AAS 刊）或订阅；批量 TDM 须邮件申请、SFTP 交付；2026-07 起 API/feed/agent 等一切机器访问须另签协议 | 机构 | robots `*` Disallow /；Radware 挑战；政策写明屏蔽系统化下载 → 站点零自动化 | — | metadata-only（P0） | [NS] §2.2.1、§2.3.1、核验 B |
| `aip` | AIP Publishing（含 AIP Conf. Proc.） | L1-publisher | 物 | ML: crossref_delegated<br>F: platform_family:silverchair（用户侧） | ML: P<br>F: U | Crossref（10.1063；摘要 0.98–0.99，licenses 0.07–0.19） | Crossref 增量（站点 RSS ⚠） | 订阅为主；JAP/PoP 仅 2024–2025 卷为 S2O 整刊 OA，2026 起逐篇判定 | 机构 | TDM 个案授权，未经授权禁系统下载（二手 ◐） | — | v2-P1 | [NS] §2.2.1、§2.2.4、§2.3.1、核验 C |
| `optica` | Optica Publishing Group | L1-publisher | 物 | ML: crossref_delegated<br>F: OA 链（旗舰 OA 刊）/外链 | ML: P<br>F: P | Crossref（10.1364；摘要 0.98） | Crossref 增量 | Optica、Optics Express 全 OA（DOAJ）；其余订阅 | 机构（OpenAthens） | robots 具名禁 ClaudeBot 等 30+ AI UA；数据条款保留 TDM 与 AI 训练权（◐，条款页 Radware 挑战） | — | v2-P1 | [NS] §2.2.1、§2.3.1 |
| `edp_sciences` | EDP Sciences（A&A、EPJ Web of Conferences） | L1-publisher | 物 | ML: crossref_delegated<br>F: OA 链 | P | Crossref（A&A、EPJ WoC 摘要 0.99） | Crossref 增量 | A&A 全 OA（DOAJ）；EPJ WoC 为 OA 论文集（许可逐卷 ⚠） | 无 | robots 只禁 CMS 目录 | — | v2-P1 | [NS] §2.2.1、§2.2.4 |
| `world_scientific` | World Scientific | L1-publisher | 物 数 | ML: crossref_delegated<br>F: —（外链） | ML: P | Crossref（10.1142；摘要 0.96–0.99） | Crossref 增量（robots 禁 `/rss`） | 订阅；短时 200 次下载即切断（二手 ◐） | 机构 | Atypon robots Crawl-delay 1 | — | metadata-only（P2） | [NS] §2.2.1 |
| `degruyter_brill` | De Gruyter Brill | L1-publisher | 数 物 化 经 | ML: crossref_delegated<br>F: —（外链） | ML: P | Crossref（10.1515；摘要 0.87–1.00） | Crossref 增量 | 订阅/OA 刊；robots 依德国著作权法 §44b 保留商业 TDM | 机构 | robots 具名禁 GPTBot/CCBot/Google-Extended 等；TDM 口径二手来源互相矛盾（◐） | — | metadata-only（P1） | [NS] §2.2.1；[SS] §2.3 |
| `acs` | ACS Publications | L1-publisher | 化 地材 | ML: crossref_delegated<br>F: —（外链；HC-27） | ML: P | Crossref（10.1021；摘要 0.07–0.15）；摘要经 ChemRxiv 版本 → OpenAlex 补齐 | Crossref 增量 | 订阅；TDM 为付费方案；平台不做任何 ACS 自动化，全文只外链/用户人工阅读 | 机构 | robots.txt 本身 CF 403 → 站点零自动化 | — | metadata-only（P0） | [NS] §2.2.1、§2.3.2；[CP] §2.3.1、HC-27 |
| `rsc` | Royal Society of Chemistry | L1-publisher | 化 | ML: crossref_delegated<br>F: OA 链（Chem Sci 等）；订阅部分待迁移完成后重勘 | ML: P<br>F: P | Crossref（10.1039；摘要 0.77–0.93） | Crossref 增量 | Chemical Science 等全 OA；其余订阅；TDM 须提前申请（◐） | 机构 | 2026-02 公告迁 Silverchair，robots 已换模板、首页 CF 挑战；OA 路线改为区域化（◐） | — | v2-P1<br>⚑DRIFT | [NS] §2.2.1、§2.3.2 |
| `ams` | American Mathematical Society | L1-publisher | 数 | ML: crossref_delegated<br>F: —（外链；用户单篇） | ML: P | Crossref（10.1090；摘要 0.70–0.87） | Crossref 增量 | 订阅；5 年滑动墙后免费（二手 ⚠），OpenAlex 不能识别此墙，须按"出版年 + 5"自行判定 | 机构 | www 与 pubs 的 robots.txt 均被 CF 挑战 → 站点零自动化 | — | v2-P1 | [NS] §2.2.1、§2.3.3、核验 B |
| `siam` | SIAM Publications Library | L1-publisher | 数 CS | ML: crossref_delegated；L 另用 feed<br>F: platform_family:atypon（用户侧） | ML: P<br>F: U | Crossref（10.1137；摘要 0.76–1.00）；SODA 为 book 结构 | `/action/showFeed`（robots Allow，信号）+ Crossref | 订阅；TDM 不被许可（二手 ◐） | 机构/Shibboleth | Atypon robots Crawl-delay 1，只具名 GPTBot | v1-designed-only（catalog `siam`） | v2-P1 | [NS] §2.2.1、§2.3.3；[CS] §2.2-D |
| `ems_press` | EMS Press | L1-publisher | 数 | ML: crossref_delegated<br>F: OA 链（S2O 年卷） | P | Crossref（10.4171；摘要 1.00，许可元数据 0） | Crossref 增量 | 22 种 S2O 刊 2024–2026 年卷 CC BY 4.0，往期订阅 → 按"年份 + 单篇许可"判定；FoCM、Archiv der Math. 2027 起 L2O | 无 | robots `Allow: /` | — | v2-P1 | [NS] §2.2.1、§2.3.3 |
| `msp` | Mathematical Sciences Publishers | L1-publisher | 数 | ML: crossref_delegated<br>F: —（外链） | ML: P | Crossref（10.2140；摘要 0）→ 摘要经 arXiv/zbMATH 补 | Crossref 增量；每刊 sitemap（robots 无禁令，只作低频新刊探测候选） | 订阅；S2O 状态 ⚠ | 机构 | robots 只列 sitemap | — | v2-P1 | [NS] §2.2.1、§2.3.3 |
| `intl_press` | International Press | L1-publisher | 数 | ML: crossref_delegated<br>F: —（外链） | ML: P | Crossref（摘要 0–0.03） | Crossref 增量 | Acta Math. 期刊级 OA（不在 DOAJ）；其余订阅 | 机构 | robots 未取到（301）⚠ | — | v2-P2<br>⚑RECHECK | [NS] §2.2.1 |
| `uchicago_journals` | UChicago Press Journals | L1-publisher | 经 管 | ML: crossref_delegated<br>F: platform_family:atypon（用户侧，epdf） | ML: P<br>F: U | Crossref（10.1086；JPE/JOLE/JLE/AJS/JOP 摘要 0%） | Crossref 增量 | 订阅；epdf 阅读器；批量下载需事先许可 | 机构 SSO | Atypon robots Crawl-delay 1，含 GPTBot 条目 | v1-designed-only（catalog `uchicago`） | v2-P1 | [SS] §2.3、§2.8 |
| `mit_press_direct` | MIT Press Direct（REStat、TACL、CL） | L1-publisher | 经 CS | ML: crossref_delegated<br>F: —（TACL/CL 经 `acl_anthology`） | ML: P | Crossref（10.1162；REStat 摘要 99%，TACL 2026 年 110 条中 109 条有摘要） | Crossref 增量 | 订阅；TDM 须书面特批、明文禁脚本抓取；TACL/CL 钻石 OA，全文走 ACL Anthology | 机构 | Silverchair（UA 008 全禁）；transacl.org Crawl-delay 60 | v1-designed-only（catalog `mit_press`） | metadata-only（P1） | [CS] §2.2-C；[SS] §2.3 |
| `emerald_insight` | Emerald Insight | L1-publisher | 金 管 | ML: crossref_delegated<br>F: —（外链） | ML: P | Crossref（10.1108；Critical Finance Review 已归 Emerald，摘要 28%） | Crossref 增量 | 订阅/混合；TDM ⚠ 未核 | 机构 | Silverchair（2025-07 新版）；首页 CF managed challenge；robots 显式 Allow 检索型 AI UA；2025-05 收购 now publishers，2026-06 被 Wiley 收购，平台去向待观察 | — | metadata-only（P2）<br>⚑DRIFT | [SS] §2.3、核验 #36、S4 |
| `pm_research` | PM Research（JPM 等） | L1-publisher | 金 | ML: crossref_delegated<br>F: —（外链） | ML: P | Crossref（10.3905；出版者现为 With Intelligence LLC；摘要 0） | Crossref 增量 | 订阅 | 机构/个人 | ⚠ 未核 | v1-designed-only（catalog `pm_research`） | v2-P2<br>⚑RECHECK | [SS] §2.3、§2.8 |
| `hbp_hbr` | Harvard Business Review | L1-publisher（实务刊） | 管 | — | — | ISSN 0017-8012 在 Crossref 返回 404，无 DOI 枚举通道 | — | 订阅（HBP） | — | ⚠ 未核 | — | excluded（无开放元数据通道） | [SS] §2.3、§2.8 |
| `mit_smr` | MIT Sloan Management Review | L1-publisher（实务刊） | 管 | ML: crossref_delegated | ML: P | Crossref 新前缀 10.63383（仅 135 个 DOI，摘要 100%） | Crossref 增量 | 订阅 | 个人 | 2026-05 宣布停办，秋季刊后停印、冬季转纯数字版，新前缀后续登记不确定 | — | metadata-only（P2）<br>⚑DRIFT | [SS] §2.3、核验 S3 |
| `acm_dl` | ACM Digital Library | L1-publisher | CS | ML: crossref_delegated<br>F: —（外链；HC-27） | ML: P | Crossref（10.1145；2025 年摘要 15.5%、license 27.5%，期刊类约 100%）；会议摘要经 OpenAlex/S2 补 | Crossref（ACM 系 DOI 常在会前注册，如 KDD 2026） | 2026-01 起全库 OA（新文 CC BY 或 BY-NC-ND）；匿名遇 CF 质询，ToS 禁脚本下载与元数据收割 → 只外链；机构 ACM Open 协议的 TDM 须经 ACM 提供的 API（未公开） | 无 | robots Crawl-delay 1，具名禁 GPTBot 等；bulk 下载属付费 DL Premium | v1-designed-only（D-020/D-024 出列） | metadata-only（P1） | [CS] §2.1.3、§2.2-D；[CP] §2.3.1、HC-27 |
| `ieee_xplore` | IEEE Xplore（含 CSDL） | L1-publisher | CS | ML: crossref_delegated<br>F: site_special（用户本人机构会话） | ML: P<br>F: U | Crossref（10.1109；2025 年 445,469 条零摘要）；摘要经 OpenAlex 补；平台层不接 IEEE API（HC-27） | Crossref DOI 滞后 2–6 个月（CVPR 约 2、ICRA 约 3.5、ICCV 约 6）→ CV/机器人会议最新走 CVF/arXiv | 订阅（IEEE Access、OJ 系为金色 OA）；全文只在用户本人机构会话中 | 机构 Shibboleth/OpenAthens（用户侧） | API ToU：限机构内非商业、单次查询展示、禁再分发、禁 AI/ML 训练与索引（用户自带 key 所得亦不得入索引/嵌入）；robots 禁 `/rest`、`/ielx*` 与 25 个 AI UA | v1-designed-only（catalog `ieee_xplore`） | v2-P1<br>⚑COMM | [CS] §2.1.3、§2.2-D、§3-8；[CP] §2.3.1、HC-27 |
| `iospress_faia` | IOS Press FAIA（ECAI 等） | L1-publisher | CS | ML: crossref_delegated<br>F: OA 链（NC） | P | Crossref（10.3233，带摘要） | Crossref 增量 | OA（样本 CC BY-NC 4.0）→ 非商业部署才可共享 | 无 | robots 只禁后台路径 | — | v2-P1<br>⚑COMM | [CS] §2.1.3、§2.2-D、§2.7 |
| `now_publishers` | now publishers（Foundations and Trends） | L1-publisher | CS | ML: crossref_delegated | ML: P | Crossref（10.1561；FnT ML 2026 年 2 条） | Crossref 增量 | 订阅 | 机构 | ⚠ 未核；2025-05 被 Emerald 收购（Emerald 2026-06 被 Wiley 收购） | v1-designed-only（catalog `now_publishers`，暂缓） | metadata-only（P2）<br>⚑DRIFT ⚑RECHECK | [CS] §2.2-D；[SS] 核验 S4 |

### 3.2 L1 预印本与工作论文（29 行）

预印本服务器与工作论文系列（含央行与国际组织）。长尾预印本走 Crossref 前缀，不碰站点。

| source_id | 名称 | 层级类型 | 学科 | ConnectorFamily | exec_side | 元数据通道 | 最新通道 | 全文通道与门控 | 认证 | 限速/ToS 要点 | v1_status | v2_status | 证据 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `arxiv` | arXiv | L1-preprint | 数 物 地材 生 经 金 CS | ML: v1_bridge(oai_pmh)（升级为类目级 set）<br>F: OA 链（仅 CC 许可 e-print）/外链 | P | OAI-PMH `oaipmh.arxiv.org`（`group:archive:category` 类目级 set，物理须 `physics:` 前缀；arXivRaw 区分新稿与更新；逐篇 `<license>`）；元数据含摘要 CC0；DOI 在 DataCite（10.48550） | 公告日 ET 22:30 后 OAI `from` 增量（周五周六无公告，内置节假日）；RSS 只作速览 | e-print 多为非独占许可 → 外链或用户私有取回；CC BY/BY-SA/CC0 者可进共享层（逐篇）；S3 requester-pays bulk 只作内部用途 | 无 | 全平台所有机器合计 ≤1 req/3 s、单连接（HC-06）；2026-02 起 429 频发，另有伪 200"Rate exceeded."；robots Crawl-delay 15；须致谢语、不得暗示背书 | v1-implemented（`arxiv`，31 个类目 VenueSpec，archive 级 set） | v2-P0 | [NS] §2.2.2、§2.3.5；[CS] §2.1.1、§2.6.1、§2.7；[LS] §2.2.6；[SS] §2.4；[CP] HC-06 |
| `chemrxiv` | ChemRxiv | L1-preprint | 化 地材 | ML: crossref_delegated（10.26434 + posted-content） | P | Crossref（10.26434；`/v{n}` 版本 DOI；摘要约 98%） | Crossref `from-posted-date`/`from-created-date`（站点 `/rss` robots 禁） | 预印本公开；许可逐篇 ⚠ → 按 license 门控 | 无 | 2026-01-21 迁 Wiley Research Exchange；旧 Open Engage API 返回 CF 挑战，新平台 API 未公布；robots Crawl-delay 1 | — | v2-P0<br>⚑DRIFT | [NS] §2.2.2、§2.3.2、核验 C |
| `biorxiv` | bioRxiv（openRxiv） | L1-preprint | 生 | M: crossref_delegated（`member:54368`）+ site_special（bioRxiv API `/pubs` 等）<br>L: crossref_delegated + feed | P | Crossref `member:54368` 或 `prefix:10.64898` 一次覆盖新旧两种 DOI 字符串（摘要 100%）+ EPMC；官方 API `/details`、`/funder` 于 2026-09-26 返回 200 空体 | Crossref `from-posted-date`；学科 RSS（RSS 1.0，最近 30 篇，crawl-delay 10） | OA，许可 6 选 1（约 19% no-reuse）→ 逐篇门控；S3 MECA 月包为 requester-pays，不得作再分发源；单篇网页 PDF 仅用户触发 | 无（S3 需 AWS） | www robots Crawl-delay 7，禁 curl/wget/python-requests 与 AI UA；API 主机无 robots；勿只按 10.1101 字符串路由 | — | v2-P0<br>⚑DRIFT | [LS] §2.2.1、§2.7、核验 #5–#15；[CP] §2.1 |
| `medrxiv` | medRxiv（openRxiv） | L1-preprint | 生 心 | 同 `biorxiv`（server=medrxiv） | P | 同 `biorxiv` | 同 `biorxiv`；默认只订精神病学/临床心理与神经相关学科，其余学科按 P2 | 同 `biorxiv`（S3 `medrxiv-src-monthly`） | 无 | robots `*` Crawl-delay 7，无 AI 专条 | — | v2-P0<br>⚑DRIFT | [LS] §2.2.1、§2.7 |
| `psyarxiv` | PsyArXiv（OSF） | L1-preprint | 心 | ML: crossref_delegated（10.31234）+ 经 `europe_pmc`<br>（OSF API：site_special，⚑ROBOTS） | P | Crossref（10.31234，每版本一个 DOI `_vN`）+ EPMC（65,080 条）；OSF API v2 字段更全（`attributes.doi` 为正式版 DOI），但 api.osf.io robots `Disallow: /` | Crossref 前缀 + posted-content 增量；OSF `filter[date_created]` 待书面确认后启用 | OA，按条许可（CC BY/CC0 为主） | 无；OSF PAT（部署级，确认后） | OSF 源码默认匿名 100/时、登录 10,000/日（生产值 ⚠）；osf.io crawl-delay 10 | — | v2-P0<br>⚑ROBOTS（仅 OSF API） | [LS] §2.2.3、§2.7；[AG] §2.2.17 |
| `osf_preprints` | OSF Preprints（其余社区） | L1-preprint | 心 管 | ML: crossref_delegated（COS 名下 23 个前缀） | P | Crossref（COS member 15934，23 个前缀，230,767 个 DOI）；OSF API 同 `psyarxiv`，受 robots 约束 | Crossref 前缀增量 | OA，按条许可；部分 provider 已停收（`allow_submissions=false`），状态须周期刷新 | 无 | 同 `psyarxiv` | v1-designed-only（catalog T3 暂缓） | v2-P1 | [LS] §2.2.3；[AG] §2.2.17；[v1-pre] §6 |
| `socarxiv` | SocArXiv（OSF） | L1-preprint | 经 管 | ML: crossref_delegated（10.31235） | P | Crossref（10.31235；25,786 个 DOI，摘要 99%）；OSF API 不用（robots 全禁） | Crossref 增量 | OA（osf.io 下载，Crawl-delay 10）；2026-03 起 AI 政策收紧审核 | 无 | osf.io 具名禁 GPTBot 等；api.osf.io 全禁 | — | v2-P1 | [SS] §2.4、核验 #49 |
| `research_square` | Research Square（Springer Nature） | L1-preprint | 全 生 | ML: crossref_delegated（10.21203）+ 经 `europe_pmc` | P | Crossref（10.21203；2026-08 共 8,995 条，样本摘要 100%）+ EPMC；官方 API 申请制 ⚠ | Crossref、EPMC 增量 | CC BY 4.0（Crossref 登记 100%）→ 可进共享层（全文优先取 EPMC）；网站 PDF 仅用户触发 | 无 | robots `*` 禁 `/api/`，具名禁 ClaudeBot 等 AI UA | v1-designed-only（catalog T3 暂缓） | v2-P1 | [NS] §2.2.2；[LS] §2.2.2；[SYN] §3.4；[v1-pre] §6 |
| `preprints_org` | Preprints.org（MDPI） | L1-preprint | 全 | ML: crossref_delegated（10.20944）+ 经 `europe_pmc` | P | Crossref（10.20944；`group-title` 即学科大类；33% 带 relation）+ EPMC | Crossref 增量 | CC BY 4.0（100%）→ 可进共享层（取 EPMC 已有全文） | 无 | robots.txt 即返回 Akamai 403 → 站点零自动化 | — | v2-P1 | [NS] §2.2.2；[LS] §2.2.4；[SYN] §3.4 |
| `authorea` | Authorea Preprints（Wiley） | L1-preprint | 全 | ML: crossref_delegated（10.22541）+ 经 `europe_pmc` | P | Crossref（10.22541；摘要 93%，无 license 元数据） | Crossref 增量 | 许可 ⚠ → 许可未知按不可共享处理 | 无 | ⚠ 未核 | — | v2-P2 | [LS] §2.2.6、§2.7 |
| `ess_open_archive` | ESS Open Archive（AGU/Wiley） | L1-preprint | 地材 | ML: crossref_delegated（10.22541） | P | Crossref（10.22541，落地域以 essopenarchive.org 为主） | Crossref 增量（robots 禁 `/rss`） | 预印本公开（许可 ⚠） | 无 | Wiley REX（Atypon 模板）robots Crawl-delay 1；迁移月份 ⚠ | — | v2-P2 | [NS] §2.2.2、核验 C |
| `eartharxiv` | EarthArXiv | L1-preprint | 地材 | M: crossref_delegated（10.31223）+ site_special（Janeway REST）<br>L: crossref_delegated | P | Crossref（10.31223）+ Janeway REST `/api/preprints/` | Crossref 增量 | 预印本公开（许可 ⚠） | 无 | robots 无禁令 | — | v2-P2 | [NS] §2.2.2 |
| `optica_open` | Optica Open | L1-preprint | 物 | ML: crossref_delegated（10.1364/opticaopen） | P | Crossref（含版本 DOI） | Crossref 增量 | 预印本公开（许可 ⚠） | 无 | robots 返回 202 空响应（疑似 WAF ⚠） | — | v2-P2 | [NS] §2.2.2、§2.3.1 |
| `techrxiv` | TechRxiv（IEEE） | L1-preprint | CS | ML: crossref_delegated（10.36227） | P | Crossref（10.36227，posted-content，带摘要） | Crossref `from-posted-date`（2025 年 6,329 条） | OA，逐篇 license（样本 CC BY 4.0） | 无 | Atypon 形态 robots，禁 `/rss`、`/action` 等，Crawl-delay 1 | — | v2-P1 | [CS] §2.1.1、§2.2-A |
| `iacr_eprint` | IACR Cryptology ePrint Archive | L1-preprint | CS | M: oai_pmh<br>L: feed（RSS/Atom） | P | OAI-PMH `eprint.iacr.org/oai`（earliest 1996；robots 注释声明的元数据通道） | RSS 最新 100 条 | 各篇 license（多为 CC BY）；全文只外链 | 无 | robots 对 `*` 为 `Disallow: /`（爬虫须白名单），AI bot 不得取 PDF → 声明的协议通道与 robots 冲突 | — | metadata-only（P1）<br>⚑ROBOTS | [CS] §2.1.1、§2.2-A、§3-2 |
| `eccc` | ECCC | L1-preprint | CS | — | — | ⚠ 未核 | ⚠ | OA ⚠ | 无 | ⚠ | v1-designed-only（catalog T3 暂缓） | v2-P2<br>⚑RECHECK | [CS] §2.2-A；[v1-pre] §6 |
| `ssrn` | SSRN | L1-preprint | 生 经 金 管 | ML: v1_bridge(crossref_delegated)（10.2139）<br>F: —（外链） | ML: P | Crossref（10.2139；148.7 万个 DOI，2026 年新建 91.2% 带摘要；2026-07 起登记 license）；`group-title` 恒为 SSRN | Crossref `from-created-date`（新 DOI 当日可见；`from-posted-date` 为 0） | ToU 禁止任何自动化查询 → 全文只外链；删除 v1 浏览器 opt-in 模式 B（新 ADR 取代 D-029/D-030 相关部分）；CC 许可不解除 ToU 禁令 | 无 | 商业线 2026-12-31 前关停、平台改造中；ToU 与 robots 只有 SNIPPET 级证据（v1 记禁 GPTBot 等、crawl-delay 5）◐ | v1-implemented（`ssrn`，元数据；模式 B 默认关） | metadata-only（P0）<br>⚑DRIFT | [SS] §2.1、§2.4、§3-4、核验 S1；[LS] §2.2.5；[BRIEF] §7-4 |
| `nber_wp` | NBER Working Papers | L1-preprint | 经 金 | M: crossref_delegated（10.3386）+ 经 `repec`<br>L: feed（back.nber.org RSS）<br>F: v1_bridge(nber)（用户侧） | ML: P<br>F: U | Crossref（10.3386；36,256 个 DOI，摘要 0）；JEL 与已发表映射经 RePEc；周更元数据文件（abs/jel/prog/published）须授权 | `back.nber.org/rss/new.xml` 与 program feed（Crawl-delay 10） | 18 个月后开放、近期须订阅（匿名每年 3 篇）；机构 IP 识别；不利用软门（D-014）；可读但无再分发许可 → 外链/用户私有 | 机构 IP | `data.nber.org` 对 bot 返回 403，批量文件须向 NBER 申请 | v1-implemented（`nber`） | v2-P0<br>⚑LIC（仅周更元数据文件） | [SS] §2.1、§2.4、核验 #9–#14 |
| `cepr_dp` | CEPR Discussion Papers | L1-preprint | 经 金 | ML: 经 `repec`（ReDIF bulk） | P | RePEc（`cpr:ceprdp`）；Crossref 无该系列记录 | RePEc 增量；CEPR 站每周新闻页不做 connector | 订阅/单篇购买 → 全文由用户在订阅内自取 | 无 | robots（2026-09-24）已无 AI 具名条目与 Content-Signal | v1-designed-only（catalog"仅元数据"；v1 `repec` 只映射 NBER w 系列，D-036） | metadata-only | [SS] §2.1、§2.4；[DL] D-036 |
| `iza_dp` | IZA Discussion Papers | L1-preprint | 经 | ML: 经 `repec`（`iza:izadps` ⚠）<br>F: —（外链） | P | RePEc 优先；站点列表页（robots 全允许）不写 connector（简报 §6.1-4）；Crossref 无该系列记录 | RePEc 增量 | 免费 PDF（`docs.iza.org/dp{n}.pdf`；再分发许可 ⚠）→ 外链/用户按需 | 无 | robots `Disallow:` 为空（全允许） | — | v2-P1 | [SS] §2.4、核验 #46 |
| `fed_board_wp` | Fed Board FEDS / IFDP / FEDS Notes | L1-preprint | 经 金 | M: crossref_delegated（10.17016）<br>L: feed（`feeds/feds.xml` 等） | P | Crossref（10.17016；4,991 个 DOI，摘要 99%） | RSS（各 15 条，含作者与摘要）+ Crossref | 免费（联邦政府作品原则上无版权，站点声明未核 ⚠） | 无 | robots.txt 404（无限制） | — | v2-P1 | [SS] §2.4、§4-15、核验 #41 |
| `ecb_wp` | ECB Working Paper Series | L1-preprint | 经 金 | ML: feed（`rss/wppub.html`） | P | RSS（RSS 2.0，含摘要）；DOI 10.2866 由欧盟出版局（OP）登记，不在 Crossref | RSS 轮询（Crawl-delay 5） | 免费 PDF（平台缓存前须确认许可 ⚠） | 无 | robots Crawl-delay 5 | — | v2-P1 | [SS] §2.4、§3-12、§4-15 |
| `bis_wp` | BIS Working Papers | L1-preprint | 经 金 | ML: feed（RSS 1.0 + CB-RSS，可做通用央行解析器） | P | RSS 1.0 + Dublin Core + CB-RSS（`cb:keyword`、`cb:person`、PDF 链接） | `doclist/wppubls.rss`（25 条） | 免费 PDF（许可 ⚠） | 无 | robots 为 Drupal 默认 + 禁 `/p/`、`/sites/default/files/` | — | v2-P1 | [SS] §2.4、核验 #43 |
| `imf_wp` | IMF Working Papers | L1-preprint | 经 金 | ML: crossref_delegated（10.5089，按 container 过滤）+ 经 `repec` | P | Crossref（10.5089；2026 年新建 76,378 条中 component 65,142、chapter 10,372，须过滤）/RePEc | Crossref 增量（官方 RSS 对本 UA 403，已停手） | 免费（许可 ⚠） | 无 | robots 宽松 | — | v2-P1 | [SS] §2.4、§4-12、核验 #44 |
| `worldbank_prwp` | World Bank Policy Research WP（含 OKR） | L1-preprint | 经 金 | ML: site_special（D&R API v3） | P | 官方 D&R API v3（PRWP 11,380 条，含摘要、pdfurl、WPS 号）；Crossref（10.1596）只覆盖约 2.2k | API `sort=docdt&order=desc` | 免费（许可逐篇字段 ⚠） | 无 | API 主机无 robots；OKR robots 禁 `/server/oai/`、`/server/api/`、Crawl-delay 10 → 不用 OKR | — | v2-P1 | [SS] §2.4、§2.6、核验 #45 |
| `hbs_wp` | HBS Working Papers | L1-preprint | 管 | ML: 经 `ssrn`/`repec`（⚠） | P | 经 SSRN（Crossref 10.2139）/RePEc ⚠ | Crossref（SSRN） | 免费 PDF ⚠ → 外链 | 无 | 研究页对本 UA 403；robots Crawl-delay 2；SSRN RPS 关停可能影响其系列页 | — | metadata-only（P2） | [SS] §2.4 |
| `mpra` | MPRA | L1-preprint（仓储型） | 经 | ML: 经 `repec`（`pra:mprapa` ⚠） | P | RePEc；EPrints OAI（`/cgi/oai2`）在 robots 禁区，不收割 | RePEc | 免费 PDF → 外链 | 无 | robots 禁 `/cgi/`，具名禁 ClaudeBot/Claude-User/Claude-SearchBot | — | metadata-only（P2） | [SS] §2.4、核验 #50 |
| `cesifo_wp` | CESifo Working Papers | L1-preprint | 经 | ML: 经 `repec`（`ces:ceswps` ⚠） | P | RePEc ⚠ | RePEc | 免费 ⚠ | 无 | 站点 301（未深探） | — | v2-P2<br>⚑RECHECK | [SS] §2.4 |
| `other_cb_wp` | 其他央行/国际组织 WP（NY Fed、BoE、OECD、Brookings 等，组） | L1-preprint | 经 金 | ML: 经 `repec`/crossref_delegated；各自 feed ⚠ | P | 优先 RePEc/Crossref（有 DOI 者） | 各自 RSS ⚠ | 多为免费（逐源许可 ⚠） | 无 | robots 均只有常规 `*` 条目 | — | v2-P2<br>⚑RECHECK | [SS] §2.4 |

### 3.3 L1 期刊平台（21 行）

学会或专业期刊平台与过刊档案。

| source_id | 名称 | 层级类型 | 学科 | ConnectorFamily | exec_side | 元数据通道 | 最新通道 | 全文通道与门控 | 认证 | 限速/ToS 要点 | v1_status | v2_status | 证据 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `informs_pubsonline` | INFORMS PubsOnline | L1-journal_platform | 管 | ML: crossref_delegated<br>F: platform_family:atypon（用户侧） | ML: P<br>F: U | Crossref（10.1287；摘要 85–97%，license 0%） | Crossref 增量（eTOC 在 `/action/showFeed`，robots 禁） | 订阅；PubsOnLine T&C（摘要级 ◐）禁止未经批准以机器人系统下载、离线浏览 ≤20 页/分 | 机构 SSO/会员 | robots `*` 不禁 `/doi/`、Crawl-delay 1；对 GPTBot/anthropic-ai 等禁全文路径；其余页面 CF 挑战；无 tdmrep.json | v1-designed-only（catalog `informs`） | v2-P0 | [SS] §2.1、§2.3、核验 S6；[v1-or] |
| `aom_journals` | AOM Journals（AMJ、AMR 等） | L1-journal_platform | 管 | ML: crossref_delegated<br>F: platform_family:atypon（用户侧） | ML: P<br>F: U | Crossref（10.5465；7 刊摘要 0%，OpenAlex 摘要滞后） | Crossref 增量 | 订阅/会员；新 OA 刊 AMIO/AMOE 在 ScienceDirect（Crossref 尚无刊记录） | 会员/机构 | robots Crawl-delay 1、GPTBot 全禁；www 主机首行孤立 Crawl-delay 10（按保守解释遵守）；TDM 条款未核 ⚠ | — | v2-P0 | [SS] §2.3、§4-9、核验 #32–#34 |
| `aea_journals` | AEA Journals（AER、AEJ 系、JEL、JEP） | L1-journal_platform | 经 | ML: crossref_delegated（v1 VenueSpec）<br>F: v1_bridge(aea)（用户侧） | ML: P<br>F: U | Crossref（10.1257；摘要 80–94%） | Crossref 增量 | AER/AEJ/P&P 订阅；JEP 钻石 OA；JEL 只有 green 副本 | 机构 IP/会员 | www 只禁 GPTBot/Amazonbot；pubs 为 Atypon + CF、Crawl-delay 1 | v1-implemented（`aea`，8 刊） | v2-P0 | [SS] §2.1、§2.3、核验 #56–#57 |
| `econsoc_journals` | Econometric Society（ECMA、TE、QE） | L1-journal_platform | 经 | M: crossref_delegated（10.3982）+ oai_pmh（TE/QE OJS）<br>L: crossref_delegated<br>F: v1_bridge(econsoc) | ML: P<br>F: P/U | Crossref（10.3982；publisher 为 The Econometric Society）+ TE/QE OJS OAI | Crossref 增量 | TE/QE 全 OA（钻石）；ECMA 为混合 gold OA（2025–26 年 79/170 带 CC：BY 53、BY-NC 10、BY-NC-ND 16）→ 按单篇 license；非会员经 Wiley（1999–）/JSTOR | 会员/机构（Wiley） | 自营站 robots 具名禁 ClaudeBot 等、曾现 CF 质询；ECMA 按年代分段路由（D-028） | v1-implemented（`econsoc`） | v2-P0 | [SS] §2.1、§2.3、核验 #15–#17；[DL] D-028 |
| `aaa_pubs` | AAA Publications（TAR 等） | L1-journal_platform | 管 | ML: crossref_delegated<br>F: platform_family:silverchair（用户侧） | ML: P<br>F: U | Crossref（10.2308；TAR 摘要 91%） | Crossref 增量 | 订阅 | 会员/机构 | Silverchair（2022-12 上线）；ToS 与 TDM 条款未核 ⚠ | — | v2-P1 | [SS] §2.3、核验 #36 |
| `misq` | MIS Quarterly | L1-journal_platform | 管 | ML: crossref_delegated<br>F: platform_family:silverchair（用户侧） | ML: P<br>F: U | Crossref（10.25300；摘要 90%） | Crossref 增量 | 订阅 | 机构 | Silverchair（2025-08 上线）；ToS 未核 ⚠ | — | v2-P1 | [SS] §2.3、核验 #36 |
| `jstor` | JSTOR | L1-journal_platform（过刊档案） | 全 | ML: crossref_delegated（10.2307）<br>F: —（外链） | ML: P | Crossref（10.2307）；数据集须人工申请 | —（过刊） | 订阅；Constellate 已于 2025-07 停运 | 机构/JPASS | Fastly + PerimeterX；robots 具名禁 ClaudeBot/CCBot/GPTBot | v1-designed-only（catalog `jstor`） | metadata-only（P2） | [SS] §2.3、核验 #60；[v1-pub] |
| `scipost` | SciPost | L1-journal_platform | 物 | ML: crossref_delegated（10.21468）；L 另用 feed<br>F: OA 链 | P | Crossref（摘要与 TDM link 0.96）；站点 `/api/` 细节未核 ⚠ | Crossref 增量；`/feeds`（robots 允许） | 全 OA → 逐篇许可后可进共享层 | 无 | robots 只禁 /search 与少数 AI UA | — | v2-P1 | [NS] §2.2.1 |
| `quantum_journal` | Quantum | L1-journal_platform | 物 | ML: crossref_delegated；L 另用 feed<br>F: OA 链（即 arXiv 版本） | P | Crossref（摘要与 TDM link 均 1.00） | RSS `/feed/`（robots 允许）+ Crossref | 全 OA（arXiv overlay） | 无 | robots 只禁 wp-admin | — | v2-P2 | [NS] §2.2.1 |
| `project_euclid` | Project Euclid（Duke UP 托管；IMS、Duke Math. J. 等） | L1-journal_platform | 数 | ML: crossref_delegated<br>F: OA 链/外链 | P | Crossref（各出版者前缀；Duke/IMS 摘要 0.09–0.14）→ 摘要经 arXiv/zbMATH 补；现行 OAI 端点 ⚠ | Crossref 增量 | 80% 以上文章开放（许可逐篇 ⚠）；其余订阅 | IP/Shibboleth | robots Crawl-delay 10 | — | v2-P1 | [NS] §2.2.1、§2.3.3 |
| `centre_mersenne_numdam` | Centre Mersenne / Numdam | L1-journal_platform（兼仓储） | 数 | M: crossref_delegated（10.5802）+ oai_pmh（Numdam）<br>L: crossref_delegated/oai_pmh<br>F: OA 链 | P | Crossref（10.5802）+ Numdam OAI-PMH（earliestDatestamp 2018-10-09）；Publ. Math. IHÉS 已迁入（OpenAlex 仍挂 Springer，host 不可用于路由） | Crossref/OAI 增量 | 多为钻石 OA ⚠（逐篇许可） | 无 | Numdam robots Crawl-delay 2 | — | v2-P1 | [NS] §2.2.1、§2.3.3 |
| `episciences` | Episciences（overlay 期刊平台） | L1-journal_platform | 数 CS | ML: crossref_delegated/DataCite ⚠；oai_pmh ⚠ | P | Crossref/DataCite ⚠；OAI ⚠ | ⚠ | 钻石 OA ⚠ | 无 | robots 禁元数据导出格式路径（/json、/crossref 等）→ 只走 Crossref 或 OAI | — | v2-P2<br>⚑RECHECK | [NS] §2.2.1、§2.3.3 |
| `annals_math` | Annals of Mathematics | L1-journal_platform | 数 | ML: crossref_delegated<br>F: —（外链） | ML: P | Crossref（10.4007；摘要 0.11） | Crossref 增量 | 订阅（往期经 JSTOR ⚠） | 机构 | robots `Disallow: /annals`（内容路径被禁） | — | metadata-only | [NS] §2.2.1、§2.3.3 |
| `geoscienceworld` | GeoScienceWorld（GSA、SEG 等地学刊） | L1-journal_platform | 地材 | ML: crossref_delegated（⚠ 未测）<br>F: platform_family:silverchair（用户侧） | ML: P<br>F: U | Crossref ⚠ 未测 | Crossref | 订阅 | 机构 | Silverchair 模板 robots + CF | — | v2-P2<br>⚑RECHECK | [NS] §2.2.1、§2.3.6 |
| `elife` | eLife | L1-journal_platform | 生 | M: crossref_delegated + site_special（eLife API，⚑ROBOTS）<br>L: feed + crossref_delegated<br>F: OA（CC BY/CC0，GitHub JATS 语料） | P | Crossref（摘要 99%）+ 官方 API（`/articles` 19,543、`/reviewed-preprints` 4,806；API 主机 robots `Disallow: /`）+ GitHub `elife-article-xml` | `/rss/recent.xml`（robots 允许）+ Crossref | 全 OA（CC BY/CC0）→ 可进共享层；eLife Assessment 词表（significance 5 级 × strength 6 级）作质量信号 | 无 | 网站 Crawl-delay 10；API 限速 ⚠ | — | v2-P1<br>⚑ROBOTS（仅官方 API） | [LS] §2.4.5、§2.7 |
| `peerj` | PeerJ | L1-journal_platform | 生 | ML: crossref_delegated<br>F: OA 链（PMC） | P | Crossref（摘要 100%，CC BY/BY-NC） | Crossref 增量（RSS 被 CF 挑战） | 全 OA；PMC 100% | 无 | robots Crawl-delay 2；所有权变更 ⚠ | — | v2-P2 | [LS] §2.4.9 |
| `sfn_journals` | SfN（J Neurosci、eNeuro） | L1-journal_platform | 生 | ML: crossref_delegated<br>F: OA 链（PMC） | P | Crossref（摘要 84%） | Crossref 增量（robots.txt 被 CF 挑战） | 约 6 个月后以 CC BY-NC-SA 开放（2026 年 439/523）；PMC 覆盖高 → 全文走 PMC | 机构 | robots.txt 即被 CF 挑战 → 站点零自动化 | — | v2-P1<br>⚑COMM | [LS] §2.4.17、§2.7 |
| `f1000_platforms` | F1000Research、Wellcome Open Research、Open Research Europe 等 | L1-journal_platform（发表后评审） | 生 全 | ML: 经 `europe_pmc` + crossref_delegated | P | EPMC + Crossref | EPMC 增量 | OA ⚠（逐篇许可） | 无 | ⚠ 未核 | — | v2-P2 | [LS] §2.2.6、§2.7 |
| `jmlr` | JMLR（含 MLOSS） | L1-journal_platform | CS | ML: feed（`jmlr.xml`）+ site_special（卷页 `citation_*`）<br>F: OA（平台侧） | P | RSS（205 条，含摘要）+ 论文页 `citation_*` meta；无 DOI（Crossref 为 0） | RSS；卷页 v27（2026） | OA，CC BY 4.0 → 可进共享层（须署名） | 无 | 无 robots.txt（S3 NoSuchKey）→ 自行保守限速 | v1-designed-only（catalog `jmlr` 专用） | v2-P0 | [CS] §2.1.2、§2.2-C、§2.7 |
| `tmlr` | TMLR | L1-journal_platform | CS | ML: 经 `openreview`（venue TMLR）+ site_special（jmlr.org/tmlr 列表）<br>F: —（外链） | P | OpenReview API + `jmlr.org/tmlr/papers/`（4,767 个 forum id）；无 DOI | 滚动接收；OpenReview `mintmdate` | 免费阅读（逐篇许可 ⚠）→ 外链 | OpenReview 账号（确认前平台侧不收割，经 arXiv + DROPS dblp + forum 外链兜底，简报 R2-20） | 同 `openreview` | v1-designed-only（catalog 经 `openreview`） | v2-P0<br>⚑ACCT | [CS] §2.1.2、§2.2-C |
| `jair` | JAIR | L1-journal_platform | CS | ML: crossref_delegated（10.1613）<br>F: OA 链 | P | Crossref（2026 年 109 条，摘要 100%） | Crossref 增量 | 钻石 OA（许可逐篇确认后共享） | 无 | robots 只禁 `/cache/` | v1-designed-only（catalog `jair`） | v2-P1 | [CS] §2.2-C；[v1-ai] |

### 3.4 L1 会议平台（31 行）

会议论文集平台；经管会议按 `presented_at` 事件建模（SI-20）。含 2 个排除行。

| source_id | 名称 | 层级类型 | 学科 | ConnectorFamily | exec_side | 元数据通道 | 最新通道 | 全文通道与门控 | 认证 | 限速/ToS 要点 | v1_status | v2_status | 证据 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `openreview` | OpenReview | L1-conference_platform | CS | ML: v1_bridge(site_special：API v2)<br>F: —（外链） | P（服务账号，⚑ACCT）/U（用户 token） | REST API v2（`api2.openreview.net`；`mintcdate/mintmdate`、`sort`、`after`、`select`）；元数据 CC0 | `active_venues`（匿名，约 1,090 个）差集发现新届；notes 以 `mintmdate` 为水位 | PDF 作者保留版权，不缓存 → 外链 | 免费账号（一人一号；平台服务账号须书面确认，V0 即发函）；书面确认前平台侧共享收割停用，ICLR、TMLR、COLM 等由 arXiv 版本 + DROPS dblp 快照 + 外链到 OpenReview forum 兜底；用户本人 token 只在用户侧供本人查询，不用于共享收割（简报 R2-20；HC-04）；OIDC 只用于作者身份绑定 | 限流按请求而异（实测 `20;w=60` 与 `180;w=60`），须读响应头；匿名 `/notes` 403；robots 只禁 `?email=`；不访问 profiles 等身份端点（2025-11 身份泄露事件） | v1-partial（`openreview`，仅 ICLR，token 用户自备） | v2-P0<br>⚑ACCT | [CS] §2.1.2、§2.2-B、§2.6.2、§3-9 |
| `pmlr` | PMLR | L1-conference_platform | CS | ML: v1_bridge(site_special：卷页 + BibTeX)<br>F: —（外链） | P | 卷页 + BibTeX；无 DOI | 首页卷表 diff + 卷号探测（ICML 2026 截至 09-26 未上线，先走 OpenReview） | OA PDF（许可未声明 ⚠）→ 外链 | 无 | robots.txt 404；沿用 v1 保守限速 | v1-partial（`pmlr`，仅 ICML 已注册） | v2-P0 | [CS] §2.1.2、§2.2-B |
| `neurips_proceedings` | NeurIPS Proceedings | L1-conference_platform | CS | M: v1_bridge(site_special：年/卷页) + crossref_delegated（10.52202）<br>L: v1_bridge<br>F: —（外链） | P | 年页/卷页 + `citation_*` meta；Crossref（Curran 10.52202，vol 35–38 共 16,691 条，无摘要；前缀与 Curran 其他会议共用，须按 container-title 过滤） | 会后上线；DOI 约晚 8 个月；最新接收先走 OpenReview | OA PDF（未声明开放许可 ⚠）→ 外链 | 无 | robots.txt 404；2025 新增 Position Paper 与 Creative AI 分轨（v1 闭表须补） | v1-implemented（`neurips_proceedings`） | v2-P0 | [CS] §2.1.2、§2.2-B、§2.4、核验 #25–#26 |
| `cvf_open_access` | CVF Open Access（CVPR、ICCV、WACV） | L1-conference_platform | CS | ML: v1_bridge(site_special：目录页 + 论文页)<br>F: —（外链） | P | 目录页 `/{CONF}{year}?day=all` + 论文 html（含摘要）；正式版 DOI 在 IEEE | CVPR 2026 共 4,042 篇已上线，早于 IEEE DOI | 录用版免费阅读，页面声明版权归作者 → 外链 | 无 | robots.txt 404 | v1-implemented（`cvf`） | v2-P0 | [CS] §2.1.2、§2.2-B、§2.7 |
| `ecva` | ECVA（ECCV 开放版） | L1-conference_platform | CS | M: site_special（`papers.php`）+ 经 `springer_link`（Crossref）<br>F: —（外链） | P | `papers.php` 单页（ECCV 2018–2024 共 6,166 篇）+ Springer DOI 外链 | 滞后于 LNCS（ECCV 2026 截至 09-26 未上 ECVA，Crossref 已有 2,251 条） | OA PDF + supp（许可未声明 ⚠）→ 外链 | 无 | robots 只含 Googlebot Allow、无 Disallow | — | v2-P1 | [CS] §2.1.2、§2.2-B |
| `acl_anthology` | ACL Anthology | L1-conference_platform | CS | ML: v1_bridge(site_special：GitHub XML/`acl-anthology` 包)<br>F: OA（平台侧） | P | GitHub `/data/xml` + 官方 Python 包；Crossref 10.18653（2025 年 11,121 条，全部无摘要）；"Verified authors"关联 ORCID | 会期前后上线（ACL 2026 long 2,222 篇、Findings 2,163 篇） | 2016 年起 CC BY 4.0 → 可进共享层（署名）；2016 年前 CC BY-NC-SA 3.0（受商用开关） | 无 | robots.txt 404 | v1-partial（`acl_anthology`，仅 EMNLP 已注册） | v2-P0 | [CS] §2.1.2、§2.2-B、§2.7、核验 #39 |
| `aaai_ojs` | AAAI OJS（AAAI、AIES、ICWSM、ICAPS、HCOMP、AIIDE、SoCS、AAAI-SS、IASEAI） | L1-conference_platform | CS | M: v1_bridge(oai_pmh) + crossref_delegated（10.1609）<br>L: v1_bridge(oai_pmh)<br>F: —（外链） | P | OAI-PMH（每页 100 条 + resumptionToken，earliest 2020-06-02）；Crossref 10.1609 摘要 100% | 期号页（AAAI-26 已上线）；AAAI-27 起在 OpenReview 评审 | 免费阅读（© AAAI，非 CC）→ 外链 | 无 | robots 只禁 `/cache/` | v1-implemented（`aaai_ojs`，仅 AAAI） | v2-P0 | [CS] §2.1.2、§2.2-B |
| `ijcai_proceedings` | IJCAI Proceedings（兼 KR） | L1-conference_platform | CS | M: crossref_delegated（10.24963，按 container-title 分流）+ site_special（年页）<br>L: crossref_delegated<br>F: —（外链） | P | 年页 `/proceedings/{y}/`；Crossref 10.24963 只覆盖 2017 年起（前缀与 KR 共用：2026 年 1,085 = IJCAI-35 972 + KR 111 + 2） | 会前上线（2026 年 972 条） | 免费阅读（© IJCAI）→ 外链 | 无 | robots Crawl-delay 10，禁 `/search` | v1-designed-only（catalog `ijcai` 专用） | v2-P0 | [CS] §2.1.2、§2.2-B、核验 #23 |
| `usenix` | USENIX（Security、OSDI、NSDI、FAST） | L1-conference_platform | CS | ML: site_special（technical-sessions 页 + `citation_*`）<br>F: —（外链） | P | 会话页 + `citation_*` meta（含 `citation_pdf_url`）；无 DOI → 以 dblp key 为 ID 锚 | 录用后即挂 prepub PDF | "freely available once the event begins"（许可未声明）→ 外链 | 无 | robots Crawl-delay 10，禁 `/publications/proceedings`、`/search` | v1-designed-only（catalog `usenix`） | v2-P1 | [CS] §2.1.2、§2.2-B |
| `ndss` | NDSS Symposium | L1-conference_platform | CS | ML: crossref_delegated（10.14722）<br>F: —（外链） | P | Crossref（2026 年 390 条，无摘要，resource 直链 PDF） | Crossref 增量（会期 2 月） | OA PDF（许可未声明）→ 外链 | 无 | robots 只禁 `/wp-admin/` | — | v2-P1 | [CS] §2.1.3、§2.2-B |
| `pvldb` | PVLDB（VLDB） | L1-conference_platform（期刊化） | CS | M: crossref_delegated（10.14778）+ site_special（卷页）<br>L: crossref_delegated<br>F: OA（平台侧，NC-ND） | P | Crossref（2025 年 446 条，摘要 100%；link 指向有 CF 的 ACM 镜像）；卷页内嵌 PDF 链接 | 每月一期（vol 19 No.1–12） | OA，CC BY-NC-ND 4.0 → 仅非商业部署且原样再分发时可共享；全文取 vldb.org | 无 | vldb.org robots 404 | v1-designed-only（catalog `pvldb`） | v2-P1<br>⚑COMM | [CS] §2.1.2、§2.2-B、§2.7 |
| `isca_archive` | ISCA Archive（Interspeech 等） | L1-conference_platform | CS | ML: crossref_delegated（10.21437）+ site_special（年页）<br>F: —（外链） | P | 年页 + Crossref 10.21437（2025 年 1,388 条，无摘要） | 当年卷被 robots 禁 → 当年只收元数据，禁区到期后重排队 | 免费阅读 → 外链 | 无 | robots `Disallow: /interspeech_2026/`、`/tmp/`（按年份变化的禁区） | v1-designed-only（catalog `isca`） | v2-P1 | [CS] §2.1.2、§2.2-B、§4-9 |
| `lipics_drops` | Dagstuhl LIPIcs（DROPS） | L1-conference_platform | CS 数 | ML: aggregator_api（DataCite 10.4230）+ oai_pmh（DROPS）<br>F: OA（平台侧） | P | DataCite（10.4230；2025 年 2,336 条，带 descriptions 与 rights）+ OAI-PMH（earliest 1991）；Crossref 查为 0 | OAI 增量 | OA，CC BY 4.0 → 可进共享层 | 无 | robots 禁 `/api/*`、`/metadata/*/*` | v1-designed-only（catalog `lipics`） | v2-P1 | [CS] §2.1.2、§2.2-B、核验 #11 |
| `rss_proceedings` | Robotics: Science and Systems | L1-conference_platform | CS | ML: site_special（卷页 `/rss{NN}/`）<br>F: —（外链） | P | 卷页（v1 勘察） | 2026 卷未核 ⚠ | OA（许可未声明）→ 外链 | 无 | robots `*` Allow / | v1-designed-only（catalog `rss_proceedings`） | v2-P2<br>⚑RECHECK | [CS] §2.2-B |
| `mlsys_proceedings` | MLSys Proceedings | L1-conference_platform | CS | —（⚠ 未核；评审在 OpenReview） | — | ⚠ 未核 | ⚠（`MLSys.org/2027/Conference` 在 OpenReview 活跃） | OA ⚠ | 无 | robots.txt 404 | — | v2-P2<br>⚑RECHECK | [CS] §2.2-B、§4-11 |
| `ceur_ws` | CEUR Workshop Proceedings | L1-conference_platform（workshop） | CS | ML: site_special（卷页 `Vol-{n}/`）<br>F: —（外链；license.xml 未读） | P | 卷页（robots 头部声明 License URL） | 卷号递增 | OA（许可 ⚠） | 无 | robots 只禁 `/temp/`、`/ftp/` 等 | — | v2-P2<br>⚑RECHECK | [CS] §2.2-B |
| `aamas_ifaamas` | IFAAMAS AAMAS Proceedings | L1-conference_platform | CS | ML: crossref_delegated（10.65109，按 container-title + created）<br>F: —（外链） | P | Crossref（member 54598，共 7,301 条，回溯卷约 2026-01 集中注册；AAMAS 2026 的 656 条无摘要、无 published 日期；container-title/publisher 字段混乱） | 年度论文集页（AAMAS 2026 已上线）；按 pub-date 过滤会整届漏掉，须用 created | 免费阅读（© IFAAMAS）；Crossref resource 指向 ACM DL（CF 质询与 ToS 约束）→ 外链 | 无 | ifaamas.org 无 robots.txt | — | v2-P2 | [CS] §2.2-B、§2.4、核验补充 2 |
| `cogsci_proceedings` | CogSci Proceedings | L1-conference_platform | 心 | ML: oai_pmh（eScholarship `set=cognitivesciencesociety`）<br>F: OA（平台侧） | P | OAI-PMH（completeListSize 21,720，每页 500，resumptionToken 24 h；`dc:source` 卷号 = 届）；Crossref（ISSN 1069-7977）404、PubMed 0 | OAI datestamp 增量 | OA（样本 CC BY）→ 逐篇许可后可进共享层 | 无 | 网页与 robots.txt 为 CloudFront 403，OAI 返回 200 | — | v2-P1 | [LS] §2.5、§2.7、核验 #49 |
| `psb_proceedings` | Pacific Symposium on Biocomputing | L1-conference_platform | 生 | ML: 经 `pubmed` | P | PubMed（2025 年 57 条，ISSN 2335-6936）；Crossref 两个 ISSN 均无记录 | ⚠ | ⚠ | 无 | ⚠ | — | v2-P2<br>⚑RECHECK | [LS] §2.5、§2.8.1 |
| `pos_sissa` | Proceedings of Science（SISSA） | L1-conference_platform | 物 | ML: crossref_delegated（10.22323）+ 经 `inspire_hep`<br>F: OA 链（逐卷许可） | P | Crossref（2025 年 2,852 条）+ INSPIRE | Crossref/INSPIRE | OA（许可逐卷 ⚠） | 无 | robots Crawl-delay 5 | — | v2-P2 | [NS] §2.2.4、§2.7 |
| `spie_dl` | SPIE Digital Library（Proc. SPIE 等） | L1-conference_platform | 物 | ML: crossref_delegated（10.1117） | ML: P | Crossref（2025 年 proceedings-article 27,794 条） | Crossref 增量 | 订阅/单篇购买 ⚠ → 外链 | 机构 | Imperva Incapsula，连 robots.txt 都是挑战页 → 视为禁止自动化 | — | metadata-only | [NS] §2.2.4、§2.7 |
| `assa_meetings` | ASSA 年会（AEA 主办，含 AFA 等分会场） | L1-conference_platform | 经 金 | ML: site_special（程序 HTML）→ `presented_at` 事件与 JEL | P | 程序 HTML：session 带 JEL 码与主办学会，论文页含作者、机构与摘要 | 年度（1 月会期） | 部分作者上传"Download Preview (PDF)"（再分发授权 ⚠）→ 外链/按需 | 无 | robots 只禁 GPTBot/Amazonbot | — | v2-P1 | [SS] §2.5、§2.9、核验 #53 |
| `nber_conferences` | NBER Summer Institute 与各类会议 | L1-conference_platform | 经 金 | ML: v1_bridge(nber) + site_special（会议页与议程）→ 会议标签 | P | SI 页面（2026 年 50 个 `si-2026-*` 分会）+ `conference.nber.org` 议程 | 年度（SI 7 月） | 论文多链至 NBER WP → 按 `nber_wp` 处理 | 无 | 同 `nber_wp` | v1-partial（`nber` 仅 WP） | v2-P1 | [SS] §2.5、§2.9、核验 #54 |
| `wfa_meeting` | WFA 年会 | L1-conference_platform | 金 | —（经 `ssrn` 版本关联） | — | 程序在会员登录门户，不自动化 | — | 作者自存（多在 SSRN） | 会员 | 主站 robots 宽松，程序须登录 | — | metadata-only（经 SSRN） | [SS] §2.5、§2.9 |
| `sfs_cavalcade` | SFS Cavalcade | L1-conference_platform | 金 | —（会议标签人工维护/经 SSRN） | — | 程序页 HTML ⚠ | — | `/acceptedpaper` 被 robots 禁 → 全文排除 | — | robots 禁 `/acceptedpaper`、`/portal`、`/wp-content` | — | metadata-only（仅会议标签） | [SS] §2.5、§2.9、核验 #55 |
| `efa_meeting` | EFA 年会 | L1-conference_platform | 金 | —（⚠ 未核） | — | ⚠ | ⚠ | ⚠ | — | ⚠ | — | v2-P2<br>⚑RECHECK | [SS] §2.5 |
| `aom_proceedings` | AOM Annual Meeting Proceedings | L1-conference_platform | 管 | ML: crossref_delegated（10.5465/amproc） | ML: P | Crossref（ISSN 0065-0668；69,864 个 DOI，摘要 0%） | Crossref 增量 | 摘要/简版论文，会员 → 外链 | 会员 | 同 `aom_journals` | — | v2-P2 | [SS] §2.5、§2.8 |
| `ais_icis` | ICIS / AIS eLibrary | L1-conference_platform | 管 | ML: crossref_delegated（仅有 DOI 部分） | ML: P | bepress 默认 OAI 路径 `/do/oai/` 在 robots 禁区 → 不收割；有 DOI 部分经 Crossref | — | 多为 OA → 外链 | 无 | robots `Disallow: /do/`；CF | — | v2-P2 | [SS] §2.5、§2.9、核验 #64 |
| `sed_meetings` | SED Meetings | L1-conference_platform | 经 | ML: 经 `repec` ⚠ | P | RePEc ⚠ | — | ⚠ | — | ⚠ | — | v2-P2<br>⚑RECHECK | [SS] §2.5 |
| `conf_virtual_sites` | icml.cc / neurips.cc / iclr.cc（miniconf） | L1-conference_platform | CS | — | — | 数据在未文档化的 `/static` JSON 与 `/api/miniconf/` | — | 链到 OpenReview/proceedings | — | robots 禁 `/static`、`/virtual/*/search`、`/search`（违反 D-014） | — | excluded（仅人工核对） | [CS] §1.3、§2.2-B |
| `informs_annual` | INFORMS Annual Meeting | L1-conference_platform | 管 | — | — | 只有摘要级程序 ⚠ | — | 无论文 | — | ⚠ | — | excluded | [SS] §2.5 |

### 3.5 L2 聚合器（20 行）

跨学科聚合器、OA 叠加层、社区信号层与商业索引。含商业 A&I、历史平台与盗版源等排除行。

| source_id | 名称 | 层级类型 | 学科 | ConnectorFamily | exec_side | 元数据通道 | 最新通道 | 全文通道与门控 | 认证 | 限速/ToS 要点 | v1_status | v2_status | 证据 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `crossref` | Crossref | L2-aggregator（DOI 注册） | 全 | ML: v1_bridge(aggregator_api)；bulk_snapshot（年度公共数据文件） | P | `/journals/{issn}/works`、`/works/{doi}`、`/prefixes/{p}/works`（均归 single 池）；年度公共数据文件（2026 版约 1.8 亿条、208 GB，2026-03-17 发布） | 期刊：`from-created-date` + 重叠窗口 + 标识符去重为主；`from-index-date` 只补漏（重建索引会把结果放大约百倍） | 无全文（`link` 为 TDM/相似度检测用途）；摘要版权归出版方（B 类，最高 DL3）；撤稿/更正经 `update-to` | 部署级 mailto（polite 池）；Plus token（付费杠杆） | 公共池单条 5/s、列表 1/s、并发 1；polite 10/3/s、并发 3；按 `x-api-pool`/`x-rate-limit-*` 分桶；关键词检索不打 Crossref | v1-implemented（`crossref`） | v2-P0 | [AG] §0、§2.2.1、核验 C1–C12；[NS] §3-8；[SS] §2.1；[CS] §2.1.4；[CP] §2.1 |
| `openalex` | OpenAlex | L2-aggregator | 全 | ML: v1_bridge(aggregator_api)；bulk_snapshot（季度快照） | P | 季度 CC0 快照（JSONL 约 745 GB）+ 计量 API；Topics 4/26/252/4,516；摘要只给倒排索引 | `from_publication_date`（免费）；`from_created/updated_date` 需付费计划 | OA 定位（`best_oa_location`，与 Unpaywall 同源）；content PDF/TEI 保留原版权（$0.01/次） | 部署级 API key（免费 $1/日） | 列表 $0.0001、搜索 $0.001；100 req/s 硬顶；不得多 key 叠加（LQ-13）；会议实体碎片化，OA 判定有误（JMLR 约 1%），host 字段不可用于路由 | v1-implemented（`openalex`，enrich） | v2-P0<br>⚑BUDGET | [AG] §2.2.2、§2.4、核验 C14–C22；[CS] §2.1.4；[CP] §2.4 |
| `s2` | Semantic Scholar | L2-aggregator | 全 | ML: v1_bridge(aggregator_api)；bulk_snapshot（Datasets 周更） | P | Graph/Recommendations API + Datasets（papers/abstracts/tldrs 为 ODC-BY；SPECTER2 嵌入为 Apache-2.0） | bulk search 按 publicationDate；Datasets diffs | `openAccessPdf` 链接；s2orc_v2 全文数据集（ODC-BY，只含 OA） | 部署级 key（申请制，不下发给用户） | key 1 RPS；匿名 404/429；须署名"Semantic Scholar"；不得再分发或出售 API；商用未明示，须书面确认 | v1-implemented（`s2`，key 待申请） | v2-P1<br>⚑COMM | [AG] §2.2.3、§2.3.4、核验 C24–C27；[CS] §2.2-E；[CP] §2.1 |
| `unpaywall` | Unpaywall | L2-aggregator（OA 叠加层） | 全 | F: v1_bridge(aggregator_api)（DOI→OA 位置） | P | DOI 单查 API（email 参数）；2025 年末已并入 OpenAlex 数据库；只覆盖 Crossref DOI | —（不是发现源） | OA 位置定位（许可另判） | 部署级 email | 10 万次/日（第三方资料一致，官方页未读 ◐） | v1-implemented（`unpaywall`） | v2-P1 | [AG] §2.2.4、核验 C28–C29；[CP] §2.1 |
| `doaj` | DOAJ | L2-aggregator（OA 期刊目录） | 全 | M: aggregator_api（API v4）+ oai_pmh + bulk_snapshot（期刊 CSV） | P | API v4 + OAI-PMH + 期刊 CSV；全量 dump 须邮件申请；期刊级与文章级元数据 CC0 | OAI-PMH/按年份检索 | 全部 OA（按文章许可；CC0 弃权不覆盖作品本身） | 无 | 全部路由 2 req/s（突发排队 5）；robots 只禁 `/search` 等 | — | v2-P1 | [AG] §2.2.7、核验 C47；[CP] §2.1 |
| `openaire` | OpenAIRE Graph | L2-aggregator | 全 | M: bulk_snapshot（Zenodo 全图 dump）+ aggregator_api | P | Graph API v1 + Zenodo dump（CC BY，按实体分文件） | ⚠ | 链接 | token（可选） | 文档：匿名 60/时、认证 7,200/时（实测匿名头 7199，以文档为准保守执行）；须署名 OpenAIRE | — | v2-P2 | [AG] §2.2.8、核验 C45 |
| `fatcat_ia_scholar` | Fatcat / IA Scholar | L2-aggregator（保存副本） | 全 | —（仅作链接来源） | — | fatcat 三个主机连接超时（GitHub 最近推送 2024-07-31，已停更）；Scholar 检索有 ALTCHA 挑战 | — | IA 保存副本链接 | — | robots 禁 `/search`、`/verify`；遇挑战即停 | — | metadata-only | [AG] §2.2.20、核验 C54 |
| `lens` | Lens.org | L2-aggregator（机构订阅） | 全 | M: aggregator_api（用户侧私有富化） | U | token API（机构订阅；须展示 Lens logo；条款 v2026.06.01） | ⚠ | 无 | 用户自带机构 token | 试用限非商业，正式只经机构订阅，商用须定制合同；平台层不作数据源 | — | metadata-only（用户自带 token） | [AG] §2.2.21、核验 C48 |
| `dimensions` | Dimensions | L2-aggregator（商业） | 全 | — | — | API/BigQuery（合同） | — | 无 | — | 只对非商业科学计量研究项目免费；v2 的发现与推荐不属此类 | — | excluded | [AG] §2.2.22、核验 C48 |
| `scopus` | Scopus | L2-aggregator（商业 A&I） | 全 | —（可选：aggregator_api，用户侧） | U（可选） | API key + 机构订阅，按用例授权 | — | 无 | 用户自带 key（可选） | 按周配额；"展示被引数"用例要求应用不能主要是搜索引擎或 A&I；IR/CRIS 用例不得公开展示摘要 | — | excluded（平台层；用户自带 key 私用可选） | [AG] §2.2.23、核验 C49 |
| `web_of_science` | Web of Science | L2-aggregator（商业 A&I） | 全 | —（可选：aggregator_api，用户侧） | U（可选） | Starter/Expanded API | — | 无 | 用户自带 key（可选） | 免费档 1/s、50/日、无被引数；机构档 5,000–20,000/日 | — | excluded（平台层；用户自带 key 私用可选） | [AG] §2.2.24、核验 C49 |
| `base` | BASE | L2-aggregator | 全 | — | — | API 须 IP 白名单；API 主机 robots `Disallow: /` | — | 链接 | — | 网站 robots 附法律声明、禁止未授权自动获取，具名禁 ClaudeBot 等；Anubis 工作量证明 → 不求解 | — | excluded（未获授权前） | [AG] §2.2.6、核验 C55 |
| `microsoft_academic` | Microsoft Academic（MAG） | L2-aggregator（历史） | 全 | — | — | 2021-12-31 关停 | — | — | — | 只兼容 `mag` 外部 ID（OpenAlex 已承接） | — | excluded（仅兼容 `mag` ID） | [AG] §2.2.26、核验 C53 |
| `google_scholar` | Google Scholar | L2-aggregator | 全 | — | — | 无 API | — | — | — | robots 禁 `/scholar`、`/search`；ToS 禁自动查询（HC-26） | —（v1 明确排除） | excluded（红线；只接受用户手动导出后上传） | [AG] §2.2.25；[NS] §2.2.5；[CS] §2.2-E；[CP] HC-26 |
| `scirate` | SciRate | L2-aggregator | 物 CS | — | — | — | — | — | — | 连 robots.txt 都被 CF 托管质询 | — | excluded | [CS] §2.1.1、§2.2-E |
| `paper_copilot` | Paper Copilot / paperlists | L2-aggregator（第三方整理） | CS | — | — | GitHub 数据无 license | — | — | — | 无许可，不能复用数据 | — | excluded（仅参考字段设计） | [CS] §2.2-E |
| `hf_papers` | Hugging Face Papers | L2-aggregator（社区信号） | CS | ML: aggregator_api（Hub API：`daily_papers`、`papers/{id}`、`papers/search`） | P | 每日精选与 trending（upvotes、评论数、组织、GitHub stars）；ID 统一为 arXiv id | 每日精选 + trending | 无（链 arXiv）；只缓存信号 | 无/部署级 token（提额） | 匿名 API 500 次/5 min、search 50 次/5 min；robots Allow all；推荐商用与长期缓存条款未核 ⚠ | — | v2-P0（信号层）<br>⚑RECHECK（仅商用与长期缓存条款） | [CS] §2.1.1、§2.2-E、§2.7、§4-6 |
| `pwc_archive` | Papers with Code 存档 | L2-aggregator（静态） | CS | M: bulk_snapshot（HF Datasets 一次性导入） | P | HF `pwc-archive/*`（CC BY-SA 4.0；2025-07 关停后冻结） | 无（站点已关） | 无 | 无 | 遵循 HF 规则；ShareAlike：派生数据集须同许可 | — | v2-P1<br>⚑SA | [CS] §2.1.1、§2.2-E |
| `alphaxiv` | alphaXiv | L2-aggregator（讨论与热度） | CS | M: aggregator_api（MCP，用户自连） | U | 只有 MCP（19 个工具；OAuth 2.1 或个人 API key） | 站内 trending（只在页面） | 链 arXiv | 用户 OAuth/个人 key | 配额未公开；ToS ⚠；CORS 只放行第一方来源 | — | v2-P2 | [CS] §2.1.1、§2.2-E |
| `pirate_sources` | Sci-Hub / LibGen / Anna's Archive（盗版源，合为一行） | —（盗版影子库） | 全 | — | — | — | — | — | — | 项目红线（AC-0.1；HC-26） | — | excluded（项目红线） | [NS] §2.2.5；[LS] §2.7；[CP] HC-26 |

### 3.6 L2 仓储与学科库（25 行）

仓储、仓储聚合与学科库（生医、物理、数学、经济、CS）。含订阅 A&I 的外链与排除行。

| source_id | 名称 | 层级类型 | 学科 | ConnectorFamily | exec_side | 元数据通道 | 最新通道 | 全文通道与门控 | 认证 | 限速/ToS 要点 | v1_status | v2_status | 证据 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `core` | CORE | L2-repository（仓储聚合） | 全 | M+F: aggregator_api（API v3） | P | API v3（`/search/works`、`/works/{id}`、`/download`）；旧 dump 为 ODC-By，新 dump 需许可 | 按日期增量能力未核 ⚠ | OA 全文（未认证不给全文）→ 排在 OpenAlex/Unpaywall 之后的兜底 | 部署级 key（个人 1,000/日、学术 5,000/日） | v2 属推荐/检索类产品，须先取得 CORE 许可；受商用开关门控（HC-23）；须注明使用 CORE（HC-24） | v1-designed-only（v1 聚合层设计存档） | v2-P1<br>⚑LIC ⚑COMM | [AG] §2.2.5、核验 C30；[CP] §2.1、HC-23 |
| `zenodo` | Zenodo | L2-repository | 全 | ML: oai_pmh（`/oai2d`） | P | OAI-PMH（按 community/set；每页 50 条，resumptionToken 2 分钟内须续拉）；robots 禁 `/api` 检索 | OAI 增量 | 按记录许可（元数据 CC0） | 无 | 访客 60/分、OAI 30/分；robots Crawl-delay 10 | — | v2-P2 | [AG] §2.2.16、核验 C43 |
| `hal` | HAL | L2-repository | 全 | ML: aggregator_api（API v3）/oai_pmh | P | API v3（search/OAI）；元数据 CC0；API 主机 robots 禁 `/search/`、`/oai/`，而 `hal.science` 注释鼓励用 API → 冲突 | OAI/API 日期过滤 ⚠（确认前经 CORE/OpenAlex 旁路） | OA 全文按存缴许可（2026-02 起上传须标许可） | 无 | 见元数据通道列 | — | v2-P2<br>⚑ROBOTS | [AG] §2.2.18、核验 C34/C52；[CS] §2.2-E |
| `europe_pmc` | Europe PMC | L2-aggregator + repository | 生 心 | M: aggregator_api（REST）+ bulk_snapshot（ftp.ebi，⚑ROBOTS）<br>L: aggregator_api | P | REST（143 个字段、`cursorMark`、pageSize ≤1,000；章节/实体/关系字段可下推）；预印本 1,247,001 条 | `FIRST_IDATE`/`INDEX_DATE` 增量 | OA 子集 JATS（按 LICENSE）；新鲜预印本多无全文 | 无 | 数值限速未公布 ⚠（仅称按 IP 计，过量即封）；`www.ebi.ac.uk` robots 对通用 UA `Crawl-Delay: 10`（REST 路径未禁）；bulk 主机 `ftp.ebi.ac.uk` `Disallow: /`；只用 ebi.ac.uk 上的 API，不碰 europepmc.org 网站（CF） | — | v2-P0<br>⚑ROBOTS（仅 bulk） | [LS] §2.3.3、§2.7；[AG] §2.2.10、核验 C38–C40/C61 |
| `pubmed` | PubMed / MEDLINE | L2-aggregator | 生 心 | ML: bulk_snapshot（baseline + updatefiles）+ aggregator_api（E-utilities） | P | 年度 baseline（`pubmed26n0001–1334`）+ 日更 updatefiles（每日约 2 个文件，含删除）；E-utilities 补查；MeSH 主干 | EDAT/`[crdt]` 日窗；updatefiles | 无全文；部分摘要受版权保护（B 类） | 部署级 NCBI key（可选） | 无 key 3 rps、有 key 10 rps（跨 IP 合并）；超 100 次的批量放美东非高峰；须带 tool/email；`eutils` 与 `ftp.ncbi` 两个主机 robots 均 `Disallow: /`；须注明"Courtesy of NLM"并保持最新（HC-24） | — | v2-P0<br>⚑ROBOTS | [LS] §2.3.1、§2.7；[AG] §2.2.11、核验 C35–C36；[CP] §2.1、§2.4 |
| `pmc` | PubMed Central | L2-repository | 生 | M+F: bulk_snapshot（S3 Cloud）+ oai_pmh + aggregator_api（BioC/E-utilities） | P | 只允许 4 条自动化通道：S3（逐篇 JSON 带 `license_code`、`is_retracted`，每日 inventory）、OAI-PMH、E-utilities、BioC；OA Web Service 2026-08 下线 | `[pmcrdat]` 日窗 + S3 inventory；OAI `from` | OA 子集与作者手稿按 `license_code` 门控（只再分发许可允许者）；删除无通知，靠 inventory 对账 | 无 | OAI 3 rps、禁并发、超 100 次须美东非高峰；主站网页禁系统性获取；pmc 主机 robots 允许 `/api/`；E-utilities 通道同 `pubmed` 受 robots 约束 | — | v2-P0<br>⚑ROBOTS（仅 E-utilities） | [LS] §2.3.2、§2.7、核验 #21–#24；[AG] §2.2.11；[CP] §2.1 |
| `pubtator3` | NCBI PubTator3 | L2-aggregator（实体标注层） | 生 | M: aggregator_api（BioC JSON） | P | REST `publications/export/biocjson?pmids=`（化学物、疾病、物种、细胞系及关系） | 随 PubMed 更新 | 只有标注 | 无 | 限速（第三方称 ≤3 rps）与数据许可 ⚠ | — | v2-P1<br>⚑RECHECK | [LS] §2.3.4、§2.7 |
| `icite` | NIH iCite / Open Citation Collection | L2-aggregator（引文指标层） | 生 | M: aggregator_api | P | REST `api/pubs?pmids=`（RCR、citation_count、cited_by、references 等 27 个字段） | — | 只有指标与引文链接 | 无 | 文档页 401；限速、许可与批量快照 ⚠ | — | v2-P1<br>⚑RECHECK | [LS] §2.3.4、§2.7 |
| `psycharchives` | PsychArchives（ZPID） | L2-repository | 心 | ML: oai_pmh | P | OAI-PMH `…/oai/request` | OAI `from` | OA，按条许可 ⚠ | 无 | robots Crawl-delay 2 | — | v2-P2 | [LS] §2.2.6、§2.7 |
| `inspire_hep` | INSPIRE-HEP | L2-aggregator（学科） | 物 | ML: aggregator_api（REST） | P | REST（literature/authors/conferences 等 9 类记录；`size` ≤1000，单查询 ≤10,000）；arXiv↔DOI↔会议映射 | `sort=mostrecent` + 查询 | 无全文（链 arXiv/DOI） | 无 | 每 IP 每 5 秒 15 次（被拒也计额），用全局共享限速器；元数据多为 CC0；robots 只禁账户/提交路径 | — | v2-P0 | [NS] §2.2.3、§2.3.1；[AG] §2.2.27；[SYN] §3.4 |
| `nasa_ads_scix` | NASA ADS / SciX | L2-aggregator（学科） | 物 地材 | ML: aggregator_api（用户侧） | U | 官方 API（search/export/metrics/libraries）；bibcode↔arXiv↔DOI | 查询 API | 链接 | 每用户 token（Bearer） | 每端点单独限速（search 示例 5,000/日，UTC 午夜重置）；2026 年 ADS→SciX 过渡（官方只说"今年秋季"），切换后须重测端点 | — | v2-P1<br>⚑DRIFT | [NS] §2.2.3、§2.3.1、核验 C；[AG] §2.2.27；[SYN] §3.4 |
| `zbmath_open` | zbMATH Open | L2-aggregator（学科） | 数 | ML: aggregator_api（REST）+ oai_pmh + bulk_snapshot（KG dump） | P | REST `api.zbmath.org/v1`（MSC、DOI、评论、作者消歧）+ OAI-PMH（earliestDatestamp 1755，秒级）+ Zenodo KG dump | OAI `from` | 无全文（链接）；部分评论因许可冲突不返回 | 无 | 数据 CC BY-SA 4.0（须署名、评估 ShareAlike）；MSC2020 码表为 CC BY-NC-SA：不作 TopicNode 默认叶子，作可选插件、任何部署默认不加载（简报 R2-22），开启后仍受商用开关约束；要求"reasonable rate"；zbmath.org 网页 CF 挑战 | — | v2-P0<br>⚑SA ⚑COMM（MSC 码表） | [NS] §2.2.3、§2.3.3、核验 B；[AG] §2.2.27、核验 C51 |
| `scoap3_repo` | SCOAP3 Repository | L2-repository | 物 | M+F: aggregator_api（`/api/records/`） | P | 官方 API（87,667 条，含摘要与 PDF/XML 链接） | API 分页（增量参数 ⚠） | OA 全文 CC BY、元数据 CC0 → 可进共享层；PRL/PRD/PRC 只覆盖 HEP 分类文章，须逐篇读许可 | 无 | robots.txt 404 | — | v2-P1 | [NS] §2.2.3、§2.3.1、核验 A/C |
| `osti_gov` | OSTI.GOV | L2-repository | 物 化 地材 | ML: aggregator_api（REST） | P | REST `api/v1/records`（`entry_date_start/end`、`has_fulltext`；`Link` 头分页） | `entry_date_start` 增量（语义 ⚠） | 链接/接受稿（许可 ⚠） | 无 | 文档未写数值限额；robots 未禁 `/api/` | — | v2-P2<br>⚑RECHECK | [NS] §2.2.3、核验 D |
| `pubchem` | PubChem | L2-aggregator（化合物） | 化 生 | M: aggregator_api（PUG-REST，化合物→文献关联） | P | PUG-REST（化合物 → PubMed/专利 xref） | 不适用 | 不适用（非论文源，仅关联） | 无 | robots `*` 禁 `/rest/pug/`，与文档化 API 冲突；2019 口径 ≤5/s、≤400/分（现值 ⚠）；响应头 `X-Throttling-Control` | — | v2-P2<br>⚑ROBOTS | [NS] §2.2.3、§2.3.2、核验 A |
| `eudml` | EuDML | L2-aggregator（数学回溯） | 数 | ML: oai_pmh | P | OAI-PMH `eudml.org/oai/OAIHandler` | — | 链接到各成员库 | 无 | robots.txt 与 Identify 均 nginx 403；集合陈旧（二手 ◐）；回溯内容已由 Numdam、zbMATH 覆盖 | — | v2-P2<br>⚑RECHECK | [NS] §2.2.3、核验 D |
| `repec` | RePEc（IDEAS/EconPapers） | L2-aggregator（学科，分布式） | 经 金 | ML: v1_bridge(bulk_snapshot)（ReDIF FTP/rsync） | P | FTP/rsync ReDIF bulk（官方推荐，勿抓网页）；OAI（2021-09 起，"sometimes flaky"）；2,400+ archive、550 万+ 条目 | rsync/FTP 增量；NEP 主题报告 | 链出（不自托管） | 无 | getdata 页强烈不建议抓网站；IDEAS robots 只禁 `/cgi-bin/`；v1 只映射 NBER w 系列（D-036） | v1-implemented（`repec`，enrich，D-035） | v2-P0 | [SS] §2.1、§2.6、核验 #51–#52；[AG] §2.2.27；[DL] D-035、D-036 |
| `econstor` | EconStor（ZBW） | L2-repository | 经 管 | ML: oai_pmh | P | OAI-PMH（earliestDatestamp 2009-01-28，秒级，`deletedRecord: transient`，按学科/类型分 set） | OAI `from` 增量 | OA 全文（机构 WP 为主，逐篇许可） | 无 | robots 只禁检索与浏览页 | v1-designed-only（catalog T3 登记） | v2-P1 | [SS] §2.6、核验 #47；[AG] §2.2.27；[SYN] §3.4；[v1-pre] §6 |
| `econbiz` | EconBiz（ZBW） | L2-aggregator（学科） | 经 管 | ML: aggregator_api（API v1 beta） | P | API v1（JSON；STW 标准词表主题标引；`econbiz_created` 时间戳） | `econbiz_created` | 链出 | 无（建议申请应用名） | beta、当前无配额；不得用于大规模复制索引；数据许可未检出 ⚠ | — | v2-P1 | [SS] §2.6、核验 #48；[AG] §2.2.27 |
| `fraser` | FRASER（St. Louis Fed） | L2-repository | 经 | ML: aggregator_api ⚠ | P | API ⚠ 未核 | — | 免费 | 无 | robots Crawl-delay 10 | — | v2-P2<br>⚑RECHECK | [SS] §2.6 |
| `ssoar` | SSOAR | L2-repository | 管 | —（经 CORE/OpenAlex 旁路） | — | ⚠（本轮连接失败） | — | OA 全文 | — | ⚠ | — | metadata-only<br>⚑RECHECK | [AG] §2.2.27 |
| `dblp` | dblp | L2-aggregator（人工策展） | CS | ML: v1_bridge→bulk_snapshot（DROPS 月度 XML）+ aggregator_api（SPARQL） | P | 只剩 DROPS 月度 XML 快照（2026-09-01 版 1,099,942,087 字节、12,928,181 条、CC0，附 md5）+ `sparql.dblp.org`；VenueEra、会议卷目录、作者 PID 的主干 | 月度快照 | 无（`ee` 外链） | 无 | 三个主站 robots `*` 全禁（v1 在线 `/db/**` 路径已不合规）；SPARQL 只放行 `/sparql`、`/download`，Crawl-delay 10 | v1-partial（代码保留，D-037 出列） | v2-P0（快照形态） | [CS] §0、§2.1.4、§2.2-E、核验 #1–#2；[AG] §2.2.12；[CP] §2.1；[DL] D-037 |
| `mathscinet` | MathSciNet（AMS） | L2-aggregator（订阅 A&I） | 数 | —（外链模板） | — | 无开放 API（订阅数据库） | — | — | 机构订阅（用户人工） | robots `*` Disallow /（只放行 MRAuthorID 与 publications-search），Crawl-delay 10 | — | link-only | [NS] §2.2.3、§2.2.5；[AG] §2.2.27 |
| `cas_scifinder` | CAS SciFinder | L2-aggregator（订阅库） | 化 | —（外链模板） | — | 无（订阅库） | — | — | Named User 订阅 | 学术版条款禁脚本批量抽取、自动化登录与 AI 用途，每人至多存 5,000 条 | — | link-only | [NS] §2.2.5、核验 D |
| `econlit` | EconLit（AEA） | L2-aggregator（订阅书目） | 经 | — | — | 200 万+ 条记录、JEL 标引；无公开 API 或批量下载 | — | 订阅 | 机构订阅 | 只有"All rights reserved"，无公开数据许可；JEL 路由以 RePEc/NBER/ASSA 为主 | — | excluded（仅作 JEL 参考） | [SS] §2.6、核验 S9 |

### 3.7 L2 身份与引文注册表（6 行）

作者、机构、DOI、引文与政策注册表：身份图与去重的底座。

| source_id | 名称 | 层级类型 | 学科 | ConnectorFamily | exec_side | 元数据通道 | 最新通道 | 全文通道与门控 | 认证 | 限速/ToS 要点 | v1_status | v2_status | 证据 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `orcid` | ORCID | L2-registry | 全 | M: aggregator_api（用户 OAuth 读本人记录）+ bulk_snapshot（年度 CC0 文件） | P（用户授权） | Public API（用户 OAuth，读本人作品与任职）+ 年度公共数据文件（CC0，figshare） | — | 无 | 用户 OAuth；部署级 client | 匿名 12 req/s、每 IP 2.5 万读/日；注册 client 10 万读/日；公共 API 限非商业，凭证归个人、禁持续轮询；`pub.orcid.org` robots `Disallow: /`；商业化须成为 Member | — | v2-P1<br>⚑ROBOTS ⚑COMM | [AG] §2.2.13、核验 C33；[CP] §2.1、HC-23 |
| `ror` | ROR | L2-registry | 全 | ML: bulk_snapshot（Zenodo dump，可本地 Docker 自托管 API） | P | REST v2 + Zenodo dump（CC0） | dump 发布 | — | 无（client ID 方案暂停） | 每 IP 2,000 次/5 min | — | v2-P1 | [AG] §2.2.15、核验 C42 |
| `datacite` | DataCite | L2-registry（DOI 注册） | 全 | ML: aggregator_api（REST）+ bulk_snapshot（年度 CC0 文件） | P | REST（arXiv 10.48550、LIPIcs 10.4230、Zenodo、dblp 快照的 DOI 均在此）；GraphQL 将于 2027-07 弃用 | created/updated 日期（参数 ⚠） | 无 | 无/mailto/认证 | 匿名 500 次/5 min、带标识 1,000、认证 3,000；Event Data 2026 年收缩；Unpaywall 不覆盖 DataCite DOI | — | v2-P1 | [AG] §2.2.14、核验 C41；[CS] §2.2-E；[SYN] §3.4 |
| `opencitations` | OpenCitations | L2-aggregator（引文） | 全 | ML: aggregator_api（REST v2/SPARQL）+ bulk_snapshot（CC0 dump） | P | Index（25 亿+ 条引用）+ Meta（1.47 亿实体，已对齐 OpenAlex ID）；REST v2、SPARQL、dump | dump 版本 | 无 | token（建议） | 每 IP 180 次/分；数据 CC0；与 OpenAlex 被引数不一致（9,262 对 10,801），须交叉校验 | — | v2-P1 | [AG] §2.2.9、核验 C46；[CP] §2.1 |
| `wikidata` | Wikidata / WikiCite | L2-aggregator（知识图谱） | 全 | ML: aggregator_api（SPARQL）+ bulk_snapshot（dump） | P | SPARQL（学术文章已拆到 `query-scholarly.wikidata.org`，跨图须联邦）+ CC0 dump | — | 无 | 无 | 单查询 60 s；每客户端每 60 s 最多 60 s 处理时间；每 IP 5 并发；UA 不合规可能被封 | — | v2-P2 | [AG] §2.2.19、核验 C44 |
| `open_policy_finder` | Jisc Open policy finder（原 Sherpa） | L2-aggregator（政策注册表） | 全 | M: aggregator_api（新 API，2026-02） | P | 新 API（旧 Sherpa API 迁移期延至 2026-07；注册方式 ⚠） | — | 无（只提供自存档/禁运政策，辅助全文共享判定） | ⚠ | 站点内容 CC BY-NC-ND 4.0 → 不得加工后对外展示，商用须另谈；`v2.sherpa.ac.uk` WAF 403 | — | v2-P2<br>⚑COMM | [AG] §2.2.29、核验 C60 |

### 3.8 中文与区域（12 行）

中文与区域来源（含 5 个区域性 L1）。

| source_id | 名称 | 层级类型 | 学科 | ConnectorFamily | exec_side | 元数据通道 | 最新通道 | 全文通道与门控 | 认证 | 限速/ToS 要点 | v1_status | v2_status | 证据 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `chinaxiv` | ChinaXiv（中科院科技论文预发布平台） | L1-preprint | 全 区 | —（robots 恢复可读前不接） | — | 首页可访问（ChinaXiv 论文 47,810 篇）；`robots.txt` 返回 403 维护页；OAI 等机器接口 ⚠；DOI 注册情况 ⚠ | ⚠ | OA 预印本 | — | robots 不可读 → 零自动化 | — | v2-P2（观察）<br>⚑RECHECK | [NS] §2.2.2；[AG] §2.2.28；[SYN] §3.4 |
| `ccs_chemistry` | CCS Chemistry（中国化学会） | L1-publisher | 化 区 | ML: crossref_delegated<br>F: OA 链 | P | Crossref（摘要 0） | Crossref 增量 | 全 OA（DOAJ；逐篇许可） | 无 | Atypon 模板 robots，Crawl-delay 1 | — | v2-P2 | [NS] §2.2.1、§2.3.6 |
| `sciengine` | SciEngine（中国科学、科学通报等） | L1-journal_platform | 全 区 | ML: crossref_delegated（⚠ 未测） | P | Crossref ⚠ 未测 | Crossref | 订阅/OA 混合 ⚠ | ⚠ | robots 具名禁 ClaudeBot、anthropic-ai、GPTBot 等 | — | metadata-only（P2）<br>⚑RECHECK | [NS] §2.2.1、§2.3.6 |
| `wulixb` | 物理学报（中国物理学会） | L1-journal_platform | 物 区 | ML: crossref_delegated（⚠ 未测） | P | Crossref ⚠ 未测 | ⚠ | ⚠ | ⚠ | robots `Allow: /` | — | v2-P2<br>⚑RECHECK | [NS] §2.2.1、§2.3.6 |
| `jstage` | J-STAGE（日本 JST） | L1-journal_platform（兼聚合） | 全 区 | ML: aggregator_api（WebAPI，Atom） | P | WebAPI（`service=3` 文章检索，须带 issn/cdjournal 等参数之一；2026-03 新增期刊检索） | 按 issn/年份检索 | OA 为主，各刊不同 ⚠ | 无（商业用途须事先申请） | 条款仅有日文版；浏览政策禁大批量下载；须注明出处；robots 禁 `/*_pdf` | — | v2-P2<br>⚑COMM | [AG] §2.2.28、核验 C57；[CP] HC-23 |
| `cinii_research` | CiNii Research（NII） | L2-aggregator（区域） | 全 区 | M: bulk_snapshot（ResourceSync，robots 放行）；OpenSearch（⚑ROBOTS） | P | OpenSearch API（须 `appid`，每页 1–200、start ≤10,000）；ResourceSync 为 robots 放行的批量同步通道 | ⚠ | 链接 | `appid` | robots 只放行 `/`、`/crid/`、`/sitemaps/`、`/resourcesync/`（Crawl-Delay 1），`/opensearch` 被禁，与 API 文档冲突 | — | v2-P2<br>⚑ROBOTS（仅 OpenSearch） | [AG] §2.2.29、核验 C60 |
| `scielo` | SciELO | L2-aggregator（拉美/伊比利亚 OA 期刊网络） | 全 区 | ML: aggregator_api（ArticleMeta API） | P | ArticleMeta API（巴西合集 564,934 篇）；OAI ⚠；多数期刊有 Crossref DOI | 按合集/处理日期 | OA（逐篇许可） | 无 | `www` robots Crawl-delay 10；检索站在 Bunny Shield 挑战之后（不碰） | — | v2-P2 | [AG] §2.2.28、核验 C57 |
| `redalyc` | Redalyc | L2-aggregator（拉美 OA） | 全 区 | —（经 OpenAlex/Crossref/DOAJ 旁路） | — | OAI-PMH ⚠ | — | OA | — | robots.txt 返回 403 | — | metadata-only | [AG] §2.2.28 |
| `paper_edu_cn` | 中国科技论文在线 | L2-repository | 全 区 | — | — | 全站维护、暂停所有线上服务 | — | OA | — | robots.txt 302 到挑战页（未求解） | — | v2-P2（暂缓）<br>⚑RECHECK | [AG] §2.2.28、核验 C56 |
| `cnki` | 中国知网（CNKI） | L2-aggregator（商业全文库） | 全 区 | —（用户手动导入 RIS/EndNote） | — | 无公开元数据 API（未发现官方开放接口 ⚠） | — | 订阅 | 机构 IP/账号（用户本人） | `kns.cnki.net` robots `Disallow: /`；不做代理、不绕 IP 授权 | — | user-import-only | [AG] §2.2.28、核验 C56 |
| `wanfang` | 万方数据 | L2-aggregator（商业） | 全 区 | —（用户手动导入） | — | 无公开 API ⚠ | — | 订阅 | 机构 | 检索子域 WAF 拦截 | — | user-import-only | [AG] §2.2.28 |
| `cqvip` | 维普（CQVIP） | L2-aggregator（商业） | 全 区 | —（用户手动导入） | — | 无公开 API ⚠ | — | 订阅 | 机构 | robots 只封部分百度子爬虫；`qikan.cqvip.com` 禁 `/Read/Read.aspx` | — | user-import-only | [AG] §2.2.28 |

---

## 4. 覆盖统计

> 本节全部数字由脚本从 §3 的行数据重算得到，与表格一致。实现期由注册表生成器产出（§8.3），不允许手工改数。

### 4.1 总体分布

| 维度 | 分布 |
|---|---|
| 分节 | L1 出版商与学会平台 43；L1 预印本与工作论文 29；L1 期刊平台 21；L1 会议平台 31；L2 聚合器 20；L2 仓储与学科库 25；L2 身份与引文注册表 6；中文与区域 12 |
| 层级类型 | L1 129（publisher 44、preprint 30、journal_platform 24、conference_platform 31）；L2 57（aggregator 42、registry 3、repository 11、aggregator + repository 1）；盗版源合并行 1 |
| v2_status | v2-P0 36；v2-P1 63；v2-P2 44；metadata-only 26（登记优先级 P0 3、P1 4、P2 10，未标 9）；link-only 2；user-import-only 3；excluded 13 |
| v1_status | v1-implemented 16；v1-partial 5；v1-designed-only 29；无（`—`）137 |
| v1 × v2 | v1-implemented 16 → v2-P0 13、v2-P1 2、metadata-only 1；v1-partial 5 → v2-P0 4、v2-P1 1；v1-designed-only 29 → v2-P0 5、v2-P1 16、v2-P2 3、metadata-only 5；无 137 → v2-P0 14、v2-P1 44、v2-P2 41、metadata-only 20、link-only 2、user-import-only 3、excluded 13 |
| 闸门（行数，可重复） | 66 行至少带一个闸门：⚑RECHECK 27、⚑COMM 17、⚑ROBOTS 10、⚑DRIFT 9、⚑LIC 3、⚑ACCT 2、⚑SA 2、⚑BUDGET 1 |
| ConnectorFamily 使用（行数，可重复） | crossref_delegated 92；aggregator_api 35；site_special 25；v1_bridge 21；bulk_snapshot 18；oai_pmh 17；feed 16；platform_family:atypon 7；platform_family:silverchair 5；official_tdm_api 4 |
| 接入工作量 | 169 个非排除来源中：只需登记 66；需要源专用或按源配置的 connector 93（其中经 `v1_bridge` 复用 v1 代码的 21 行）；暂无 connector 10（待复勘或经他源旁路）。另有排除类 18 行。口径："需要"指至少一条通道用到 `site_special`、`oai_pmh`、`feed`、`aggregator_api`、`bulk_snapshot`、`official_tdm_api` 或 `v1_bridge`，或写作"同 `x`"、须按源配置 `x` 的 connector（如 `medrxiv`）；只用 `crossref_delegated`、族级共享的 `platform_family`（用户侧）、"经 `x`"、OA 链或外链的，计为"只需登记"；ConnectorFamily 为"—"的计为"暂无" |
| `crossref_delegated` 覆盖 | 92 个非排除来源的元数据/最新通道用到 Crossref 委托；出版商与期刊平台（§3.1、§3.3）的 63 个非排除行中，53 行的平台侧元数据通道只有 Crossref 委托（用户侧 API 不计，如 `springer_link` 的 SN API）。其余 10 行另有 OAI、官方 API、feed 或他源通道：`mdpi`、`plos`、`aps`、`econsoc_journals`、`centre_mersenne_numdam`、`episciences`、`elife`、`f1000_platforms`、`jmlr`、`tmlr` |
| 执行位置 | 27 个非排除来源至少一条通道为 `U`；另有 2 个排除来源（`scopus`、`web_of_science`）只允许用户自带 key 私用 |

**闸门明细**

| 闸门 | 行数 | 行（括号为只影响的通道） |
|---|---:|---|
| ⚑ROBOTS | 10 | `psyarxiv`（仅 OSF API）、`iacr_eprint`、`elife`（仅官方 API）、`hal`、`europe_pmc`（仅 bulk）、`pubmed`、`pmc`（仅 E-utilities）、`pubchem`、`orcid`、`cinii_research`（仅 OpenSearch） |
| ⚑ACCT | 2 | `tmlr`、`openreview` |
| ⚑COMM | 17 | `elsevier_sd`、`wiley`、`springer_link`、`nature_portfolio`、`cambridge_core`、`tandf_online`、`sage_journals`、`ieee_xplore`、`iospress_faia`、`sfn_journals`、`pvldb`、`s2`、`core`、`zbmath_open`（MSC 码表）、`orcid`、`open_policy_finder`、`jstage` |
| ⚑LIC | 3 | `aps`（仅全量 Harvest）、`nber_wp`（仅周更元数据文件）、`core` |
| ⚑BUDGET | 1 | `openalex` |
| ⚑DRIFT | 9 | `rsc`、`emerald_insight`、`mit_smr`、`now_publishers`、`chemrxiv`、`biorxiv`、`medrxiv`、`ssrn`、`nasa_ads_scix` |
| ⚑RECHECK | 27 | `sage_journals`、`ucpress_online`、`intl_press`、`pm_research`、`now_publishers`、`eccc`、`cesifo_wp`、`other_cb_wp`、`episciences`、`geoscienceworld`、`rss_proceedings`、`mlsys_proceedings`、`ceur_ws`、`psb_proceedings`、`efa_meeting`、`sed_meetings`、`hf_papers`（仅商用与长期缓存条款）、`pubtator3`、`icite`、`osti_gov`、`eudml`、`fraser`、`ssoar`、`chinaxiv`、`sciengine`、`wulixb`、`paper_edu_cn` |
| ⚑SA | 2 | `pwc_archive`、`zbmath_open` |

### 4.2 分节 × v2 状态

| 节 | 行数 | v2-P0 | v2-P1 | v2-P2 | metadata-only | link-only | user-import-only | excluded |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| §3.1 L1 出版商与学会平台 | 43 | 7 | 20 | 4 | 11 | 0 | 0 | 1 |
| §3.2 L1 预印本与工作论文 | 29 | 6 | 11 | 7 | 5 | 0 | 0 | 0 |
| §3.3 L1 期刊平台 | 21 | 6 | 8 | 5 | 2 | 0 | 0 | 0 |
| §3.4 L1 会议平台 | 31 | 7 | 9 | 10 | 3 | 0 | 0 | 2 |
| §3.5 L2 聚合器 | 20 | 3 | 4 | 2 | 2 | 0 | 0 | 9 |
| §3.6 L2 仓储与学科库 | 25 | 7 | 7 | 7 | 1 | 2 | 0 | 1 |
| §3.7 L2 身份与引文注册表 | 6 | 0 | 4 | 2 | 0 | 0 | 0 | 0 |
| §3.8 中文与区域 | 12 | 0 | 0 | 7 | 2 | 0 | 3 | 0 |
| **合计** | **187** | **36** | **63** | **44** | **26** | **2** | **3** | **13** |

### 4.3 分学科 × 状态

计数口径：
- 一个来源可以标注多个学科，所以各行之和大于 187。
- 标"全"的来源同时服务所有学科，只计入"跨学科（通用）"一行；同时标"全"与具体学科的来源（如 `research_square` 标"全 生"），两行都计。
- "中文/区域"是横切标记，单列一行供参考；这些来源同时计入各自所标的学科行。
- "v1-implemented"列为该学科行中 v1 已实现的来源数。

| 学科组 | 标注该学科的来源 | L1 | L2 | v2-P0 | v2-P1 | v2-P2 | metadata-only | link-only | user-import-only | excluded | v1-implemented | v2-P0 来源 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 数学 | 24 | 21 | 3 | 6 | 11 | 3 | 3 | 1 | 0 | 0 | 4 | `elsevier_sd`、`wiley`、`springer_link`、`oup_academic`、`arxiv`、`zbmath_open` |
| 物理 | 28 | 23 | 5 | 8 | 10 | 5 | 4 | 0 | 0 | 1 | 4 | `elsevier_sd`、`wiley`、`springer_link`、`nature_portfolio`、`oup_academic`、`aps`、`arxiv`、`inspire_hep` |
| 化学 | 14 | 11 | 3 | 5 | 3 | 3 | 2 | 1 | 0 | 0 | 2 | `elsevier_sd`、`wiley`、`springer_link`、`nature_portfolio`、`chemrxiv` |
| 生物 | 27 | 21 | 6 | 11 | 10 | 5 | 1 | 0 | 0 | 0 | 5 | `elsevier_sd`、`wiley`、`springer_link`、`nature_portfolio`、`oup_academic`、`arxiv`、`biorxiv`、`medrxiv`、`europe_pmc`、`pubmed`、`pmc` |
| 心理 | 22 | 19 | 3 | 9 | 9 | 2 | 2 | 0 | 0 | 0 | 3 | `elsevier_sd`、`wiley`、`springer_link`、`nature_portfolio`、`oup_academic`、`medrxiv`、`psyarxiv`、`europe_pmc`、`pubmed` |
| 经济 | 34 | 29 | 5 | 9 | 15 | 4 | 5 | 0 | 0 | 1 | 9 | `elsevier_sd`、`wiley`、`springer_link`、`oup_academic`、`arxiv`、`nber_wp`、`aea_journals`、`econsoc_journals`、`repec` |
| 金融 | 25 | 24 | 1 | 7 | 10 | 3 | 5 | 0 | 0 | 0 | 7 | `elsevier_sd`、`wiley`、`springer_link`、`oup_academic`、`arxiv`、`nber_wp`、`repec` |
| 商业管理 | 27 | 24 | 3 | 6 | 11 | 2 | 6 | 0 | 0 | 2 | 4 | `elsevier_sd`、`wiley`、`springer_link`、`oup_academic`、`informs_pubsonline`、`aom_journals` |
| CS-AI | 40 | 34 | 6 | 14 | 12 | 7 | 4 | 0 | 0 | 3 | 5 | `elsevier_sd`、`springer_link`、`arxiv`、`jmlr`、`tmlr`、`openreview`、`pmlr`、`neurips_proceedings`、`cvf_open_access`、`acl_anthology`、`aaai_ojs`、`ijcai_proceedings`、`hf_papers`、`dblp` |
| 地学材料 | 12 | 10 | 2 | 5 | 2 | 4 | 1 | 0 | 0 | 0 | 3 | `elsevier_sd`、`wiley`、`nature_portfolio`、`arxiv`、`chemrxiv` |
| 跨学科（通用） | 41 | 10 | 30 | 3 | 11 | 12 | 5 | 0 | 3 | 7 | 4 | `pnas`、`crossref`、`openalex` |
| 中文/区域（横切） | 12 | 5 | 7 | 0 | 0 | 7 | 2 | 0 | 3 | 0 | 0 | — |

### 4.4 覆盖评估与对策

| 学科组 | 评估 | 主要缺口与对策 | 依据 |
|---|---|---|---|
| 数学 | 结构化主干较好：zbMATH Open（P0）、arXiv 类目、EMS S2O、Numdam；MathSciNet 只外链 | MSP、IMS、Duke、Annals、International Press 的 Crossref 摘要接近 0，走 arXiv → zbMATH 补齐链。MSC2020 为 CC BY-NC-SA、zbMATH 数据为 CC BY-SA，用作标签或对外发布派生数据时受商用开关与 SA 约束。Am. J. Math.（Project MUSE）、Ann. Sci. ENS（SMF）的平台未勘察，名录无对应行（K-15） | [NS] §2.4、§2.8.1、§3-2、§3-11 |
| 物理 | 通道最丰富：arXiv、APS Harvest（OA 集）、INSPIRE、SCOAP3、ADS；IOP 元数据质量最好，但站点零自动化 | PRL、PRB、RMP 摘要覆盖低，走 Harvest → arXiv → OpenAlex；ADS token 每用户自持，且正向 SciX 迁移 | [NS] §2.3.1、§2.4 |
| 化学 | 最弱的理科：Crossref 摘要中位数 11%（AG 样本，化学/材料合计）；ACS 只取元数据，CAS SciFinder 只外链；缺开放的细粒度分类法 | 摘要走 ChemRxiv 版本 → OpenAlex；冷启动靠 OpenAlex subfield 与嵌入；RSC 迁移完成后重勘 | [NS] §2.3.2、§3-11；[AG] §2.6 |
| 生物 | L2 骨干最强：Europe PMC、PubMed、PMC 的许可字段完善；预印本量大 | `pubmed` 两条通道均为 ⚑ROBOTS，首批以 EPMC + PMC + Crossref 为主干；bioRxiv `/details` 返回空体，走 Crossref `member:54368`；ISMB/RECOMB 的枚举方式未核 | [LS] §2.3、§4；[AG] §2.2.10–§2.2.11 |
| 心理 | 依赖 Crossref，但 APA 期刊的摘要与参考文献覆盖都是 0%；PubMed 覆盖残缺；PsyArXiv（经 Crossref）与 CogSci OAI 可用 | APA 只取元数据。补齐手段：关联 PsyArXiv 预印本、OpenAlex 摘要（计费）、用户导入 PsycInfo/RIS、OpenURL。心理学会议（Psychonomics、SPSP、CCN）未调研 | [LS] §2.4.13、§3-15；[AG] §2.6 |
| 经济 | 34 行、P0 9 行：AEA、ECMA、NBER、RePEc bulk、arXiv econ；央行与国际组织 WP 多有合规 RSS 或 API | SSRN 只取元数据加外链；NBER 周更元数据文件须授权；ECB 只能走 RSS；IMF 须过滤 component；v1 的 RePEc 实现只覆盖 NBER `w` 系列；JHR（UW Press）、BPEA（Crossref 只到 1999 年）的平台未勘察，名录无对应行（K-15） | [SS] §2.4、§2.8、§3-12；[DL] D-036 |
| 金融 | 25 行、P0 7 行：Top3（JF、JFE、RFS）分别在 Wiley、Elsevier、OUP；WP 主要经 SSRN 与 NBER | 金融会议（WFA、SFS、EFA）的论文大多只在 SSRN，只能作 `presented_at` 标签；Elsevier 金融刊摘要 0% | [SS] §2.5、§2.8、§2.9 |
| 商业管理 | UTD24 中 21/24 刊在 Atypon 或 Silverchair；INFORMS、AOM 为 P0。"管"所含的社会学、政治学只做了简述（SS 映射表 5 个 venue），除 SocArXiv、SSOAR 外没有学科专属来源 | AOM、UChicago 摘要为 0；FT50、AJG、ABDC 名录的许可只允许用户私有导入；MIT SMR 停印；社会学、政治学覆盖见 K-14 | [SS] §1.1、§2.2、§2.7、§2.8、§3-10 |
| CS-AI | P0 最多（14 行）：OpenReview、ACL Anthology、PMLR、CVF、AAAI、IJCAI、JMLR/TMLR、dblp 快照、HF 信号 | IEEE 与 ACM 只取元数据；无 DOI 的 venue 靠原生通道；IEEE DOI 滞后 2–6 个月；MLSys、RSS、ECCC 未核；OpenReview 服务账号待确认 | [CS] §2.4、§2.6.5、§4 |
| 地学材料 | 最薄：12 行中地学专属来源只有 3 行，且全为 P2（GeoScienceWorld，Crossref 未测；ESS Open Archive、EarthArXiv 两个预印本）；材料没有专属来源。其余 9 行是跨学科出版商（Elsevier、Wiley、Nature、MDPI）、化学来源（ACS、ChemRxiv）、arXiv 与 ADS/OSTI；P0 的 5 行全是跨学科出版商与预印本 | AGU、EGU/Copernicus、GSA 与材料专门来源未调研（K-01、K-02）；GeoScienceWorld 的 Crossref 未测 | [NS] §2.2.1、§2.2.2、§2.3.6、§4-15 |
| 跨学科（通用） | Crossref、OpenAlex 为主干（P0）；S2、DOAJ、OpenCitations、ROR、DataCite、ORCID 为 P1；商业 A&I 平台层排除 | OpenAlex 按量计费，增量过滤需付费计划；S2 key 只有 1 RPS，商用未明示 | [AG] §2.2、§4 |
| 中文/区域 | 没有 P0/P1：知网、万方、维普只能用户导入；ChinaXiv、中国科技论文在线维护中；J-STAGE、SciELO、CiNii 为 P2 | 中文覆盖靠用户导入题录，加上 OpenAlex/Crossref 中已有的中文 DOI 刊（覆盖未实测）；须补一轮中文生态调研（K-06） | [AG] §2.2.28、§3-17、§4 Q14 |

### 4.5 与综合 §3.3 的差异

- 数学、物理、化学、生物、心理、商业管理、CS-AI、跨学科、中文/区域 9 组的计数与综合 §3.3 完全相同。本轮的学科修正（加"地材"，从 `informs_pubsonline` 与 `now_publishers` 去掉"经"）不改变这 9 组的数字。
- 综合的"经济/金融"41 行在本文拆为经济 34 行、金融 25 行（并集 39、交集 20）。并集比 41 少 2，是因为 `informs_pubsonline` 与 `now_publishers` 去掉了"经"（附录 A.2）。
- 综合的"地学"6 行扩为"地学材料"12 行，新增 6 行材料标注：`arxiv`、`chemrxiv`、`acs`、`mdpi`、`elsevier_sd`、`nature_portfolio`。
- v1 现状由"是 16、部分 15、设计 21、否 135"变为"v1-implemented 16、v1-partial 5、v1-designed-only 29、无 137"（附录 A.1）。

---

## 5. 代表性 venue 名录索引

选取规则：
- 每个学科组列不超过 20 个核心 venue，共 195 个。
- 数据只取自调研映射表与附件：[NS] §2.8（115 个刊与论文集，附件 [NS-CSV]）、[LS] §2.8（58 个）、[SS] §2.8（107 个 ISSN）、[CS] §2.3（30 条，另有补充映射）、[AG] §2.6（204 刊，附件 [AG-JSONL]；会议另见 [AG-CONF]）。
- 选取口径：优先学科公认名录中的刊会（经济 Top5、金融 Top3、UTD24、CCF-A/ICORE-A*），其余按调研映射表的代表性选取。同一 venue 在多篇调研中出现时，数值取学科调研，交叉引用 AG。
- "ISSN"照录调研中的 print / electronic；Crossref 登记异常照注，如 PRB、MNRAS、GRL、Nature Methods、Genome Biology。
- "元数据通道"括号内为 Crossref `abstracts-current` 覆盖：NS 用 0–1 的小数，其余各篇用百分比，均照录。"OA 情况"照录调研口径。
- 316 个 ISSN 已用脚本逐一在调研原文与附件中比对，全部命中；140 组 p/e 配对都能在调研的同一行中找到。
- 跨学科综合刊（Nature、Science、PNAS 等）只列在 §5.11，生物组不重复列出。

### 5.1 数学（20）

| # | venue | ISSN（p / e） | 出版平台 | 元数据通道（Crossref 摘要覆盖） | OA 情况 | source_id | 出处 |
|---|---|---|---|---|---|---|---|
| 1 | Annals of Mathematics | 0003-486X / 1939-8980 | Princeton（自营站） | Crossref（0.11） | 订阅 | `annals_math` | [NS] §2.8.1 |
| 2 | Acta Mathematica | 0001-5962 / 1871-2509 | International Press | Crossref（0.00） | 期刊级 OA（不在 DOAJ） | `intl_press` | [NS] §2.8.1 |
| 3 | Inventiones Mathematicae | 0020-9910 / 1432-1297 | Springer Nature Link | Crossref（0.50） | 订阅 | `springer_link` | [NS] §2.8.1 |
| 4 | Journal of the AMS | 0894-0347 / 1088-6834 | AMS | Crossref（0.70） | 订阅；5 年后免费（二手 ⚠） | `ams` | [NS] §2.8.1 |
| 5 | Publ. Math. IHÉS | 0073-8301 / 1618-1913 | Centre Mersenne（已迁出 Springer，10.5802） | Crossref（0.96） | ⚠（OpenAlex 仍标 Springer，不可信） | `centre_mersenne_numdam` | [NS] §2.8.1 |
| 6 | Duke Mathematical Journal | 0012-7094 / 1547-7398 | Project Euclid | Crossref（0.09）→ arXiv/zbMATH 补 | 订阅 | `project_euclid` | [NS] §2.8.1 |
| 7 | Journal of the EMS | 1435-9855 / 1435-9863 | EMS Press | Crossref（1.00） | OA（DOAJ；S2O 2024–26） | `ems_press` | [NS] §2.8.1 |
| 8 | Forum of Mathematics, Pi | — / 2050-5086 | Cambridge Core | Crossref（0.99） | OA（DOAJ） | `cambridge_core` | [NS] §2.8.1 |
| 9 | Geometric and Functional Analysis | 1016-443X / 1420-8970 | Springer Nature Link（Birkhäuser） | Crossref（0.51） | 订阅 | `springer_link` | [NS] §2.8.1 |
| 10 | Comm. Pure Appl. Math. | 0010-3640 / 1097-0312 | Wiley | Crossref（0.61） | 订阅 | `wiley` | [NS] §2.8.1 |
| 11 | Advances in Mathematics | 0001-8708 / 1090-2082 | ScienceDirect | Crossref（0.00） | 订阅 | `elsevier_sd` | [NS] §2.8.1 |
| 12 | Mathematische Annalen | 0025-5831 / 1432-1807 | Springer Nature Link | Crossref（0.40） | 订阅 | `springer_link` | [NS] §2.8.1 |
| 13 | J. reine angew. Math.（Crelle） | 0075-4102 / 1435-5345 | De Gruyter Brill | Crossref（1.00） | 订阅 | `degruyter_brill` | [NS] §2.8.1 |
| 14 | Compositio Mathematica | 0010-437X / 1570-5846 | Cambridge Core | Crossref（0.76） | 订阅 | `cambridge_core` | [NS] §2.8.1 |
| 15 | Geometry & Topology | 1465-3060 / 1364-0380 | MSP | Crossref（0.00）→ arXiv/zbMATH 补 | 订阅（S2O ⚠） | `msp` | [NS] §2.8.1 |
| 16 | Annals of Probability | 0091-1798 / 2168-894X | Project Euclid（IMS；托管关系 ⚠） | Crossref（0.13） | 订阅 | `project_euclid` | [NS] §2.8.1 |
| 17 | Annals of Statistics | 0090-5364 / 2168-8966 | IMS（Crossref 出版方；托管平台 ⚠） | Crossref（14%） | 订阅/混合 | `project_euclid`（⚠ 按 IMS 托管推断） | [AG] §2.6.1 |
| 18 | Journal of the American Statistical Association | 0162-1459 / 1537-274X | Taylor & Francis（ASA） | Crossref（0%） | 订阅/混合 | `tandf_online` | [AG] §2.6.1 |
| 19 | Journal of the Royal Statistical Society Series B | 1369-7412 / 1467-9868 | Oxford Academic | Crossref（60%） | 订阅/混合 | `oup_academic` | [AG] §2.6.1 |
| 20 | SIAM J. Numer. Anal. | 0036-1429 / 1095-7170 | SIAM | Crossref（1.00） | 订阅 | `siam` | [NS] §2.8.1 |

### 5.2 物理与天文（20）

| # | venue | ISSN（p / e） | 出版平台 | 元数据通道（Crossref 摘要覆盖） | OA 情况 | source_id | 出处 |
|---|---|---|---|---|---|---|---|
| 1 | Physical Review Letters | 0031-9007 / 1079-7114 | APS | Crossref（0.29）+ Harvest（OA 集）→ arXiv 补摘要 | 订阅（单篇 CC BY） | `aps` | [NS] §2.8.2 |
| 2 | Physical Review X | — / 2160-3308 | APS | Crossref（0.92）+ Harvest OA 集 | OA（DOAJ） | `aps` | [NS] §2.8.2 |
| 3 | Reviews of Modern Physics | 0034-6861 / 1539-0756 | APS | Crossref（0.00） | 订阅 | `aps` | [NS] §2.8.2 |
| 4 | Physical Review B | 查询用 2469-9950；刊记录挂旧 1098-0121 / 1550-235X | APS | Crossref（0.11）；须合并新旧 ISSN | 订阅 | `aps` | [NS] §2.8.2 |
| 5 | Physical Review D | 查询用 2470-0010；刊记录挂 1550-7998 / 1089-4918 | APS | Crossref（0.57） | 订阅（SCOAP3 单篇 CC BY） | `aps` | [NS] §2.8.2 |
| 6 | Physical Review Research | — / 2643-1564 | APS | Crossref（0.95） | OA（DOAJ） | `aps` | [NS] §2.8.2 |
| 7 | Nature Physics | 1745-2473 / 1745-2481 | Nature Portfolio | Crossref（0.16） | 订阅 | `nature_portfolio` | [NS] §2.8.2 |
| 8 | New Journal of Physics | — / 1367-2630 | IOP | Crossref（0.99） | OA（DOAJ） | `iop` | [NS] §2.8.2 |
| 9 | Classical and Quantum Gravity | 0264-9381 / 1361-6382 | IOP | Crossref（0.99） | 订阅 | `iop` | [NS] §2.8.2 |
| 10 | JCAP | 1475-7508 / 1475-7516 | IOP | Crossref（0.99） | 订阅 | `iop` | [NS] §2.8.2 |
| 11 | JHEP | 1126-6708 / 1029-8479 | Springer Nature Link | Crossref（0.99） | OA（DOAJ，APC 0，SCOAP3） | `springer_link` | [NS] §2.8.2 |
| 12 | Physics Letters B | 0370-2693 / — | ScienceDirect | Crossref（0.00） | OA（DOAJ，APC 0） | `elsevier_sd` | [NS] §2.8.2 |
| 13 | Eur. Phys. J. C | 1434-6044 / 1434-6052 | Springer Nature Link | Crossref（0.98） | OA（DOAJ，APC 0） | `springer_link` | [NS] §2.8.2 |
| 14 | Astrophysical Journal | 0004-637X / 1538-4357 | IOP（AAS，10.3847） | Crossref（0.99） | OA（DOAJ） | `iop` | [NS] §2.8.2 |
| 15 | MNRAS | 0035-8711 / 1365-2966（论文级；刊级记录误登 1365-8711） | Oxford Academic | Crossref（0.97） | OA（DOAJ） | `oup_academic` | [NS] §2.8.2 |
| 16 | Astronomy & Astrophysics | 0004-6361 / 1432-0746 | EDP Sciences | Crossref（0.99） | OA（DOAJ） | `edp_sciences` | [NS] §2.8.2 |
| 17 | Applied Physics Letters | 0003-6951 / 1077-3118 | AIP | Crossref（0.99） | 订阅 | `aip` | [NS] §2.8.2 |
| 18 | Optica | — / 2334-2536 | Optica | Crossref（0.98） | OA（DOAJ） | `optica` | [NS] §2.8.2 |
| 19 | Quantum | — / 2521-327X | Quantum | Crossref（1.00） | OA（DOAJ） | `quantum_journal` | [NS] §2.8.2 |
| 20 | SciPost Physics | 2542-4653 / 2542-4653 | SciPost | Crossref（0.96） | OA（DOAJ） | `scipost` | [NS] §2.8.2 |

### 5.3 化学（20）

| # | venue | ISSN（p / e） | 出版平台 | 元数据通道（Crossref 摘要覆盖） | OA 情况 | source_id | 出处 |
|---|---|---|---|---|---|---|---|
| 1 | JACS | 0002-7863 / 1520-5126 | ACS | Crossref（0.10）→ ChemRxiv/OpenAlex 补 | 订阅 | `acs` | [NS] §2.8.3 |
| 2 | Chemical Reviews | 0009-2665 / 1520-6890 | ACS | Crossref（0.07） | 订阅 | `acs` | [NS] §2.8.3 |
| 3 | Angew. Chem. Int. Ed. | 1433-7851 / 1521-3773 | Wiley（VCH） | Crossref（0.92） | 订阅 | `wiley` | [NS] §2.8.3 |
| 4 | Nature Chemistry | 1755-4330 / 1755-4349 | Nature Portfolio | Crossref（0.20） | 订阅 | `nature_portfolio` | [NS] §2.8.3 |
| 5 | Chemical Society Reviews | 0306-0012 / 1460-4744 | RSC | Crossref（0.77） | 订阅 | `rsc` | [NS] §2.8.3 |
| 6 | Chemical Science | 2041-6520 / 2041-6539 | RSC | Crossref（0.91） | OA（DOAJ） | `rsc` | [NS] §2.8.3 |
| 7 | Accounts of Chemical Research | 0001-4842 / 1520-4898 | ACS | Crossref（0.09） | 订阅 | `acs` | [NS] §2.8.3 |
| 8 | ACS Catalysis | 2155-5435 / 2155-5435 | ACS | Crossref（0.15） | 订阅 | `acs` | [NS] §2.8.3 |
| 9 | ACS Nano | 1936-0851 / 1936-086X | ACS | Crossref（0.07） | 订阅 | `acs` | [NS] §2.8.3 |
| 10 | J. Chem. Phys. | 0021-9606 / 1089-7690 | AIP | Crossref（0.98） | 订阅 | `aip` | [NS] §2.8.3 |
| 11 | Chem（Cell Press） | 2451-9294 / — | ScienceDirect（Cell Press） | Crossref（0.00） | 订阅 | `elsevier_sd` | [NS] §2.8.3 |
| 12 | Nature Catalysis | — / 2520-1158 | Nature Portfolio | Crossref（0.11） | 订阅 | `nature_portfolio` | [NS] §2.8.3 |
| 13 | Energy & Environ. Sci. | 1754-5692 / 1754-5706 | RSC | Crossref（0.86） | 订阅 | `rsc` | [NS] §2.8.3 |
| 14 | Chemical Communications | 1359-7345 / 1364-548X | RSC | Crossref（0.89） | 订阅 | `rsc` | [NS] §2.8.3 |
| 15 | J. Org. Chem. | 0022-3263 / 1520-6904 | ACS | Crossref（0.07） | 订阅 | `acs` | [NS] §2.8.3 |
| 16 | J. Phys. Chem. Lett. | 1948-7185 / 1948-7185 | ACS | Crossref（0.08） | 订阅 | `acs` | [NS] §2.8.3 |
| 17 | Chem. Eur. J. | 0947-6539 / 1521-3765 | Wiley（VCH） | Crossref（0.88） | 订阅 | `wiley` | [NS] §2.8.3 |
| 18 | CCS Chemistry | 2096-5745 / 2096-5745 | 中国化学会（Atypon 模板） | Crossref（0.00） | OA（DOAJ） | `ccs_chemistry` | [NS] §2.8.3 |
| 19 | ACS Central Science | 2374-7943 / 2374-7951 | ACS | Crossref（0.09） | OA（DOAJ，APC 0） | `acs` | [NS] §2.8.3 |
| 20 | Pure Appl. Chem.（IUPAC） | 0033-4545 / 1365-3075 | De Gruyter Brill | Crossref（0.87） | 订阅 | `degruyter_brill` | [NS] §2.8.3 |

### 5.4 生物与生命科学（20）

| # | venue | ISSN（p / e） | 出版平台 | 元数据通道（Crossref 摘要覆盖） | OA 情况 | source_id | 出处 |
|---|---|---|---|---|---|---|---|
| 1 | Cell | 0092-8674 | Cell Press（ScienceDirect） | Crossref（0%）+ PubMed/EPMC 补摘要 | 混合（2026 年即时 CC 241/463） | `elsevier_sd` | [LS] §2.8.1 |
| 2 | eLife | 2050-084X | eLife | Crossref（99%）+ eLife API | 全 OA（CC BY/CC0） | `elife` | [LS] §2.8.1 |
| 3 | Nature Genetics | 1061-4036 / 1546-1718 | Nature Portfolio | Crossref（23%） | 混合 | `nature_portfolio` | [LS] §2.8.1 |
| 4 | Nature Neuroscience | 1097-6256 / 1546-1726 | Nature Portfolio | Crossref（25%） | 混合 | `nature_portfolio` | [LS] §2.8.1 |
| 5 | Nature Methods | 1548-7091 / 1548-7105 | Nature Portfolio | Crossref（刊记录错挂为 Nature Chemical Biology，按 works 路由） | 混合 | `nature_portfolio` | [LS] §2.8.1；[AG] §2.6.4 |
| 6 | Neuron | 0896-6273 | Cell Press | Crossref（0%） | 混合（2026 年 CC 130/366） | `elsevier_sd` | [LS] §2.8.1 |
| 7 | Molecular Cell | 1097-2765 | Cell Press | Crossref（0%） | 混合（2026 年 CC 123/300） | `elsevier_sd` | [LS] §2.8.1 |
| 8 | Current Biology | 0960-9822 | Cell Press | Crossref（0%） | 混合（2026 年 CC 266/722） | `elsevier_sd` | [LS] §2.8.1 |
| 9 | Cell Reports | 2211-1247 | Cell Press | Crossref（0%） | 全 OA（DOAJ） | `elsevier_sd` | [LS] §2.8.1 |
| 10 | PLOS Biology | 1544-9173 / 1545-7885 | PLOS | Crossref（82%；印本号查 2026 年为 0，须 eISSN）+ PLOS API | 全 OA（CC BY） | `plos` | [LS] §2.8.1 |
| 11 | PLOS Computational Biology | 1553-734X / 1553-7358 | PLOS | Crossref（95%；须 eISSN） | 全 OA | `plos` | [LS] §2.8.1 |
| 12 | Nucleic Acids Research | 0305-1048 / 1362-4962 | Oxford Academic | Crossref（94%） | 全 OA（DOAJ） | `oup_academic` | [LS] §2.8.1 |
| 13 | Bioinformatics（含 ISMB 论文集） | 1367-4803 / 1367-4811 | Oxford Academic | Crossref（98%；eISSN 更全） | 全 OA（DOAJ 按 eISSN，2023 起） | `oup_academic` | [LS] §2.8.1 |
| 14 | Genome Research | 1088-9051 / 1549-5469 | CSHL Press | Crossref（98%；无 license 元数据） | 订阅/延迟开放 ⚠（PMC 100%） | `cshl_press` | [LS] §2.8.1 |
| 15 | The EMBO Journal | 0261-4189 / 1460-2075 | Springer Nature Link（EMBO Press 迁入） | Crossref（89%；印本号查 2026 年为 0） | 2026 年 244/247 为 CC BY | `springer_link` | [LS] §2.8.1 |
| 16 | Molecular Systems Biology | 1744-4292 | Springer Nature Link | Crossref（88%） | 全 OA（DOAJ） | `springer_link` | [LS] §2.8.1 |
| 17 | Genome Biology | 1474-760X（Crossref 另记 1465-6906） | Springer Nature Link（BMC 迁入） | Crossref（56%） | 全 OA（DOAJ） | `springer_link` | [LS] §2.8.1 |
| 18 | Journal of Neuroscience | 0270-6474 / 1529-2401 | SfN | Crossref（84%） | 约 6 个月后 CC BY-NC-SA | `sfn_journals` | [LS] §2.8.1 |
| 19 | Annual Review of Biochemistry | 0066-4154 / 1545-4509 | Annual Reviews | Crossref（96%） | S2O（样本 23/24 为 CC） | `annual_reviews` | [LS] §2.8.1 |
| 20 | PeerJ | 2167-8359 | PeerJ | Crossref（100%） | 全 OA（DOAJ） | `peerj` | [LS] §2.8.1 |

### 5.5 心理（20）

| # | venue | ISSN（p / e） | 出版平台 | 元数据通道（Crossref 摘要覆盖） | OA 情况 | source_id | 出处 |
|---|---|---|---|---|---|---|---|
| 1 | Psychological Bulletin | 0033-2909 / 1939-1455 | APA PsycNet | Crossref（0%）+ PubMed（部分） | 订阅 | `apa_psycnet` | [LS] §2.8.2 |
| 2 | Psychological Review | 0033-295X / 1939-1471 | APA PsycNet | Crossref（0%） | 订阅 | `apa_psycnet` | [LS] §2.8.2 |
| 3 | J Personality & Social Psychology | 0022-3514 / 1939-1315 | APA PsycNet | Crossref（0%） | 订阅（2026 年 CC 22/184） | `apa_psycnet` | [LS] §2.8.2 |
| 4 | J Exp Psych: General | 0096-3445 / 1939-2222 | APA PsycNet | Crossref（0%） | 订阅 | `apa_psycnet` | [LS] §2.8.2 |
| 5 | American Psychologist | 0003-066X / 1935-990X | APA PsycNet | Crossref（0%） | 订阅（部分 CC） | `apa_psycnet` | [LS] §2.8.2 |
| 6 | Developmental Psychology | 0012-1649 / 1939-0599 | APA PsycNet | Crossref（0%） | 订阅 | `apa_psycnet` | [LS] §2.8.2 |
| 7 | Psychological Science | 0956-7976 / 1467-9280 | SAGE（APS） | Crossref（98%） | 混合（2026 年 CC 28/46） | `sage_journals` | [LS] §2.8.2 |
| 8 | Perspectives on Psych Science | 1745-6916 / 1745-6924 | SAGE（APS） | Crossref（91%） | 混合 | `sage_journals` | [LS] §2.8.2 |
| 9 | Clinical Psychological Science | 2167-7026 / 2167-7034 | SAGE（APS） | Crossref（97%） | 混合 | `sage_journals` | [LS] §2.8.2 |
| 10 | AMPPS | 2515-2459 / 2515-2467 | SAGE（APS） | Crossref（92%）；PubMed/PMC 为 0 | 全 OA（DOAJ） | `sage_journals` | [LS] §2.8.2 |
| 11 | Annual Review of Psychology | 0066-4308 / 1545-2085 | Annual Reviews | Crossref（93%） | S2O（2026 年 CC BY 25/34） | `annual_reviews` | [LS] §2.8.2 |
| 12 | Behavioral and Brain Sciences | 0140-525X / 1469-1825 | Cambridge Core | Crossref（99%）；PMC 为 0 | 订阅 | `cambridge_core` | [LS] §2.8.2 |
| 13 | Psychological Medicine | 0033-2917 / 1469-8978 | Cambridge Core | Crossref（91%） | 混合 | `cambridge_core` | [LS] §2.8.2 |
| 14 | Nature Human Behaviour | 2397-3374 | Nature Portfolio | Crossref（19%） | 混合 | `nature_portfolio` | [LS] §2.8.2 |
| 15 | Trends in Cognitive Sciences | 1364-6613 | Cell Press | Crossref（0%） | 混合（2026 年 CC 62/174） | `elsevier_sd` | [LS] §2.8.2 |
| 16 | Cognition | 0010-0277 | ScienceDirect | Crossref（0%） | 混合（2026 年 CC 135/254） | `elsevier_sd` | [LS] §2.8.2 |
| 17 | Psychonomic Bulletin & Review | 1069-9384 / 1531-5320 | Springer Nature Link | Crossref（57%） | 混合（2026 年 CC BY 139/221） | `springer_link` | [LS] §2.8.2 |
| 18 | Cognitive Science | 0364-0213 / 1551-6709 | Wiley | Crossref（82%） | 混合（2026 年 CC 54/115） | `wiley` | [LS] §2.8.2 |
| 19 | Child Development | 0009-3920 / 1467-8624 | Oxford Academic（由 Wiley 转入） | Crossref（94%；印本号查 2026 年为 0，须 eISSN） | 混合 | `oup_academic` | [LS] §2.8.2 |
| 20 | CogSci Proceedings（会议） | ISSN 1069-7977 | eScholarship | OAI-PMH（21,720 条；Crossref 查该 ISSN 为 404） | OA（CC BY） | `cogsci_proceedings` | [LS] §2.8.2 |

### 5.6 经济（20）

| # | venue | ISSN（p / e） | 出版平台 | 元数据通道（Crossref 摘要覆盖） | OA 情况 | source_id | 出处 |
|---|---|---|---|---|---|---|---|
| 1 | American Economic Review | 0002-8282 / 1944-7981 | AEA（Atypon） | Crossref（89%） | 订阅（Econ Top5） | `aea_journals` | [SS] §2.8；[AG] §2.6.6 |
| 2 | Econometrica | 0012-9682 / 1468-0262 | Econometric Society（自营） | Crossref（69%） | 混合 gold OA，按单篇 license（Econ Top5） | `econsoc_journals` | [SS] §2.8；[AG] §2.6.6 |
| 3 | Journal of Political Economy | 0022-3808 / 1537-534X | UChicago Press（Atypon） | Crossref（0%） | 订阅（Econ Top5） | `uchicago_journals` | [SS] §2.8；[AG] §2.6.6 |
| 4 | Quarterly Journal of Economics | 0033-5533 / 1531-4650 | Oxford Academic | Crossref（97%） | 订阅/混合（Econ Top5） | `oup_academic` | [SS] §2.8；[AG] §2.6.6 |
| 5 | Review of Economic Studies | 0034-6527 / 1467-937X | Oxford Academic | Crossref（98%） | 订阅/混合（Econ Top5） | `oup_academic` | [SS] §2.8；[AG] §2.6.6 |
| 6 | AER: Insights | 2640-205X | AEA | Crossref（89%） | 订阅 | `aea_journals` | [SS] §2.8 |
| 7 | Journal of Economic Literature | 0022-0515 / 2328-8175 | AEA | Crossref（90%） | 订阅（只有 green 副本） | `aea_journals` | [SS] §2.8；[AG] §2.6.6 |
| 8 | Journal of Economic Perspectives | 0895-3309 | AEA | Crossref（84%） | 钻石 OA | `aea_journals` | [SS] §2.8 |
| 9 | Journal of the European Economic Association | 1542-4766 / 1542-4774 | Oxford Academic | Crossref（97%） | 订阅/混合 | `oup_academic` | [SS] §2.8；[AG] §2.6.6 |
| 10 | The Economic Journal | 0013-0133 / 1468-0297 | Oxford Academic | Crossref（97%） | 订阅/混合 | `oup_academic` | [SS] §2.8；[AG] §2.6.6 |
| 11 | Theoretical Economics | 1933-6837 / 1555-7561 | Econometric Society（OJS） | Crossref（85%）+ OJS OAI | 钻石 OA | `econsoc_journals` | [SS] §2.8；[AG] §2.6.6 |
| 12 | Quantitative Economics | 1759-7323 / 1759-7331 | Econometric Society（OJS） | Crossref（81%）+ OJS OAI | 钻石 OA | `econsoc_journals` | [SS] §2.8；[AG] §2.6.6 |
| 13 | Review of Economics and Statistics | 0034-6535 / 1530-9142 | MIT Press Direct | Crossref（99%） | 订阅 | `mit_press_direct` | [SS] §2.8；[AG] §2.6.6 |
| 14 | Journal of Economic Theory | 0022-0531 / 1095-7235 | ScienceDirect | Crossref（0%） | 订阅/混合 | `elsevier_sd` | [SS] §2.8；[AG] §2.6.6 |
| 15 | Journal of Econometrics | 0304-4076 / 1872-6895 | ScienceDirect | Crossref（0%） | 订阅/混合 | `elsevier_sd` | [SS] §2.8；[AG] §2.6.6 |
| 16 | Journal of Monetary Economics | 0304-3932 | ScienceDirect | Crossref（0%） | 订阅/混合 | `elsevier_sd` | [SS] §2.8 |
| 17 | AEJ: Macroeconomics | 1945-7707 / 1945-7715 | AEA | Crossref（92%） | 订阅 | `aea_journals` | [SS] §2.8；[AG] §2.6.6 |
| 18 | AEJ: Applied Economics | 1945-7782 / 1945-7790 | AEA | Crossref（93%） | 订阅 | `aea_journals` | [SS] §2.8；[AG] §2.6.6 |
| 19 | International Economic Review | 0020-6598 / 1468-2354 | Wiley | Crossref（85%） | 订阅/混合 | `wiley` | [SS] §2.8；[AG] §2.6.6 |
| 20 | RAND Journal of Economics | 0741-6261 / 1756-2171 | Wiley | Crossref（83%） | 订阅/混合 | `wiley` | [SS] §2.8；[AG] §2.6.6 |

### 5.7 金融（20）

| # | venue | ISSN（p / e） | 出版平台 | 元数据通道（Crossref 摘要覆盖） | OA 情况 | source_id | 出处 |
|---|---|---|---|---|---|---|---|
| 1 | Journal of Finance | 0022-1082 / 1540-6261 | Wiley | Crossref（73%） | 订阅/混合（UTD24、Fin Top3） | `wiley` | [SS] §2.8；[AG] §2.6.7 |
| 2 | Journal of Financial Economics | 0304-405X | ScienceDirect | Crossref（0%） | 订阅/混合（UTD24、Fin Top3） | `elsevier_sd` | [SS] §2.8；[AG] §2.6.7 |
| 3 | Review of Financial Studies | 0893-9454 / 1465-7368 | Oxford Academic | Crossref（98%） | 订阅/混合（UTD24、Fin Top3） | `oup_academic` | [SS] §2.8；[AG] §2.6.7 |
| 4 | Journal of Financial and Quantitative Analysis | 0022-1090 / 1756-6916 | Cambridge Core | Crossref（84%） | 订阅/混合 | `cambridge_core` | [SS] §2.8；[AG] §2.6.7 |
| 5 | Review of Finance | 1572-3097 / 1573-692X | Oxford Academic | Crossref（99%） | 订阅/混合 | `oup_academic` | [SS] §2.8；[AG] §2.6.7 |
| 6 | Review of Asset Pricing Studies | 2045-9920 / 2045-9939 | Oxford Academic | Crossref（98%） | 订阅/混合 | `oup_academic` | [SS] §2.8；[AG] §2.6.7 |
| 7 | Review of Corporate Finance Studies | 2046-9128 / 2046-9136 | Oxford Academic | Crossref（99%） | 订阅/混合 | `oup_academic` | [SS] §2.8；[AG] §2.6.7 |
| 8 | Journal of Financial Intermediation | 1042-9573 / 1096-0473 | ScienceDirect | Crossref（0%） | 订阅/混合 | `elsevier_sd` | [SS] §2.8；[AG] §2.6.7 |
| 9 | Journal of Banking & Finance | 0378-4266 | ScienceDirect | Crossref（0%） | 订阅/混合 | `elsevier_sd` | [SS] §2.8；[AG] §2.6.7 |
| 10 | Journal of Corporate Finance | 0929-1199 | ScienceDirect | Crossref（0%） | 订阅/混合 | `elsevier_sd` | [SS] §2.8；[AG] §2.6.7 |
| 11 | Journal of Financial Markets | 1386-4181 | ScienceDirect | Crossref（0%） | 订阅/混合 | `elsevier_sd` | [SS] §2.8；[AG] §2.6.7 |
| 12 | Journal of Empirical Finance | 0927-5398 | ScienceDirect | Crossref（0%） | 订阅/混合 | `elsevier_sd` | [SS] §2.8；[AG] §2.6.7 |
| 13 | Journal of Financial Econometrics | 1479-8409 / 1479-8417 | Oxford Academic | Crossref（97%） | 订阅/混合 | `oup_academic` | [SS] §2.8；[AG] §2.6.7 |
| 14 | Mathematical Finance | 0960-1627 / 1467-9965 | Wiley | Crossref（78%） | 订阅/混合 | `wiley` | [SS] §2.8；[AG] §2.6.7 |
| 15 | Finance and Stochastics | 0949-2984 / 1432-1122 | Springer Nature Link | Crossref（54%） | 订阅/混合 | `springer_link` | [SS] §2.8；[AG] §2.6.7 |
| 16 | Quantitative Finance | 1469-7688 / 1469-7696 | Taylor & Francis | Crossref（0%） | 订阅/混合 | `tandf_online` | [SS] §2.8；[AG] §2.6.7 |
| 17 | SIAM Journal on Financial Mathematics | 1945-497X / 1945-497X | SIAM | Crossref（100%） | 订阅/混合 | `siam` | [AG] §2.6.7 |
| 18 | Annual Review of Financial Economics | 1941-1367 / 1941-1375 | Annual Reviews | Crossref（95%） | 部分 OA ⚠ | `annual_reviews` | [SS] §2.8；[AG] §2.6.7 |
| 19 | Critical Finance Review | 2164-5744 | Emerald（原 now publishers） | Crossref（28%） | 订阅/混合 | `emerald_insight` | [SS] §2.8 |
| 20 | Journal of Portfolio Management | 0095-4918 | PM Research（With Intelligence） | Crossref（0%） | 订阅 | `pm_research` | [SS] §2.8 |

### 5.8 商业与管理（20）

| # | venue | ISSN（p / e） | 出版平台 | 元数据通道（Crossref 摘要覆盖） | OA 情况 | source_id | 出处 |
|---|---|---|---|---|---|---|---|
| 1 | Academy of Management Journal | 0001-4273 / 1948-0989 | AOM（Atypon） | Crossref（0%） | 订阅/会员（UTD24） | `aom_journals` | [SS] §2.8；[AG] §2.6.9 |
| 2 | Academy of Management Review | 0363-7425 / 1930-3807 | AOM（Atypon） | Crossref（0%） | 订阅/会员（UTD24） | `aom_journals` | [SS] §2.8；[AG] §2.6.9 |
| 3 | Administrative Science Quarterly | 0001-8392 / 1930-3815 | SAGE | Crossref（39%） | 订阅/混合（UTD24） | `sage_journals` | [SS] §2.8；[AG] §2.6.9 |
| 4 | Organization Science | 1047-7039 / 1526-5455 | INFORMS | Crossref（95%） | 订阅（UTD24） | `informs_pubsonline` | [SS] §2.8；[AG] §2.6.9 |
| 5 | Strategic Management Journal | 0143-2095 / 1097-0266 | Wiley（SMS 子域） | Crossref（78%） | 订阅/混合（UTD24） | `wiley` | [SS] §2.8；[AG] §2.6.9 |
| 6 | Journal of International Business Studies | 0047-2506 / 1478-6990 | Springer Nature Link（Palgrave） | Crossref（36%） | 订阅/混合（UTD24） | `springer_link` | [SS] §2.8；[AG] §2.6.8 |
| 7 | Management Science | 0025-1909 / 1526-5501 | INFORMS | Crossref（97%） | 订阅（UTD24） | `informs_pubsonline` | [SS] §2.8；[AG] §2.6.9 |
| 8 | Marketing Science | 0732-2399 / 1526-548X | INFORMS | Crossref（85%） | 订阅（UTD24） | `informs_pubsonline` | [SS] §2.8；[AG] §2.6.8 |
| 9 | Journal of Marketing | 0022-2429 | SAGE（AMA） | Crossref（95%） | 订阅/混合（UTD24） | `sage_journals` | [SS] §2.8；[AG] §2.6.8 |
| 10 | Journal of Marketing Research | 0022-2437 / 1547-7193 | SAGE（AMA） | Crossref（98%） | 订阅/混合（UTD24） | `sage_journals` | [SS] §2.8；[AG] §2.6.8 |
| 11 | Journal of Consumer Research | 0093-5301 / 1537-5277 | Oxford Academic | Crossref（90%） | 订阅/混合（UTD24） | `oup_academic` | [SS] §2.8；[AG] §2.6.8 |
| 12 | Information Systems Research | 1047-7047 / 1526-5536 | INFORMS | Crossref（93%） | 订阅（UTD24） | `informs_pubsonline` | [SS] §2.8；[AG] §2.6.8 |
| 13 | MIS Quarterly | 0276-7783 / 2162-9730 | MISQ（Silverchair） | Crossref（90%） | 订阅（UTD24） | `misq` | [SS] §2.8；[AG] §2.6.8 |
| 14 | Journal of Operations Management | 0272-6963 / 1873-1317 | Wiley | Crossref（64%） | 订阅/混合（UTD24） | `wiley` | [SS] §2.8；[AG] §2.6.9 |
| 15 | Manufacturing & Service Operations Management | 1523-4614 / 1526-5498 | INFORMS | Crossref（95%） | 订阅（UTD24） | `informs_pubsonline` | [SS] §2.8；[AG] §2.6.9 |
| 16 | Production and Operations Management | 1059-1478 / 1937-5956 | SAGE（POMS） | Crossref（99%） | 订阅/混合（UTD24） | `sage_journals` | [SS] §2.8；[AG] §2.6.9 |
| 17 | Operations Research | 0030-364X / 1526-5463 | INFORMS | Crossref（93%） | 订阅（UTD24） | `informs_pubsonline` | [SS] §2.8；[AG] §2.6.9 |
| 18 | The Accounting Review | 0001-4826 / 1558-7967 | AAA（Silverchair） | Crossref（91%） | 订阅（UTD24） | `aaa_pubs` | [SS] §2.8；[AG] §2.6.8 |
| 19 | Journal of Accounting Research | 0021-8456 / 1475-679X | Wiley | Crossref（70%） | 订阅/混合（UTD24） | `wiley` | [SS] §2.8；[AG] §2.6.8 |
| 20 | Journal of Accounting and Economics | 0165-4101 | ScienceDirect | Crossref（0%） | 订阅/混合（UTD24） | `elsevier_sd` | [SS] §2.8；[AG] §2.6.8 |

### 5.9 计算机与 AI（20）

| # | venue | 类型 | 标识（DBLP key / ISSN / DOI 前缀） | 出版平台（全文主源） | 元数据通道 | OA 情况 | source_id | 出处 |
|---|---|---|---|---|---|---|---|---|
| 1 | NeurIPS | 会议 | `nips` | proceedings.neurips.cc（评审在 OpenReview） | 年/卷页；Crossref 10.52202（Curran，无摘要，约晚 8 个月） | 免费阅读 | `neurips_proceedings` | [CS] §2.3 |
| 2 | ICML | 会议 | `icml` | PMLR（接收列表在 OpenReview） | 卷页 + BibTeX；无 DOI | 免费阅读 | `pmlr` | [CS] §2.3 |
| 3 | ICLR | 会议 | `iclr` | OpenReview | OpenReview API；无 DOI | 免费阅读；元数据 CC0 | `openreview` | [CS] §2.3 |
| 4 | AAAI | 会议 | `aaai` | AAAI OJS | OAI-PMH + Crossref 10.1609（摘要 100%） | 免费阅读（© AAAI） | `aaai_ojs` | [CS] §2.3 |
| 5 | IJCAI | 会议 | `ijcai` | ijcai.org | Crossref 10.24963（2017 年起；与 KR 共用前缀） | 免费阅读（© IJCAI） | `ijcai_proceedings` | [CS] §2.3 |
| 6 | CVPR | 会议 | `cvpr` | CVF Open Access（正式版在 IEEE） | CVF 页（含摘要）；IEEE DOI 约晚 2 个月、无摘要 | CVF 免费阅读 | `cvf_open_access` | [CS] §2.3 |
| 7 | ICCV | 会议 | `iccv` | CVF Open Access（正式版在 IEEE） | CVF 页；ICCV 2025 的 DOI 约晚 6 个月 | CVF 免费阅读 | `cvf_open_access` | [CS] §2.3 |
| 8 | ECCV | 会议 | `eccv` | Springer LNCS（OA 版在 ECVA） | Crossref 10.1007（book-chapter，会期前后注册） | ECVA 免费阅读 | `springer_link`/`ecva` | [CS] §2.3 |
| 9 | ACL | 会议 | `acl` | ACL Anthology | GitHub XML；Crossref 10.18653（无摘要） | CC BY 4.0 | `acl_anthology` | [CS] §2.3 |
| 10 | EMNLP | 会议 | `emnlp` | ACL Anthology | 同 ACL | CC BY 4.0 | `acl_anthology` | [CS] §2.3 |
| 11 | KDD | 会议 | `kdd` | ACM DL | Crossref 10.1145（会前注册） | ACM OA（2026-01 起） | `acm_dl` | [CS] §2.3 |
| 12 | SIGIR | 会议 | `sigir` | ACM DL | Crossref 10.1145 | ACM OA | `acm_dl` | [CS] §2.3 |
| 13 | WWW | 会议 | `www` | ACM DL | Crossref 10.1145 | ACM OA | `acm_dl` | [CS] §2.3 |
| 14 | CHI | 会议 | `chi` | ACM DL | Crossref 10.1145 | ACM OA | `acm_dl` | [CS] §2.3 |
| 15 | SIGMOD（PACMMOD） | 会议→期刊 | `sigmod`；PACMMOD 2836-6573 | ACM DL | Crossref（PACMMOD 摘要 100%） | ACM OA | `acm_dl` | [CS] §2.3 |
| 16 | VLDB（PVLDB） | 期刊式会议 | `vldb`；前缀 10.14778 | vldb.org | Crossref（摘要 100%） | CC BY-NC-ND 4.0 | `pvldb` | [CS] §2.3 |
| 17 | USENIX Security | 会议 | `uss` | USENIX | 会话页 + `citation_*`；无 DOI | OA（录用后即有 prepub） | `usenix` | [CS] §2.3 |
| 18 | NDSS | 会议 | `ndss` | ndss-symposium.org | Crossref 10.14722（无摘要） | 免费阅读 | `ndss` | [CS] §2.3 |
| 19 | JMLR | 期刊 | 1533-7928（`journals/jmlr`） | jmlr.org | RSS + `citation_*`；无 DOI | CC BY 4.0 | `jmlr` | [CS] §2.3 |
| 20 | IEEE TPAMI | 期刊 | 0162-8828 / 1939-3539 | IEEE Xplore | Crossref（两种 ISSN 都能查，无摘要） | 混合 | `ieee_xplore` | [CS] §2.3 |

### 5.10 地学与材料（7）

| # | venue | ISSN（p / e） | 出版平台 | 元数据通道（Crossref 摘要覆盖） | OA 情况 | source_id | 出处 |
|---|---|---|---|---|---|---|---|
| 1 | Nature Materials | 1476-1122 / 1476-4660 | Nature Portfolio | Crossref（0.10） | 订阅 | `nature_portfolio` | [NS] §2.8.4 |
| 2 | Advanced Materials | 0935-9648 / 1521-4095 | Wiley（VCH） | Crossref（0.88） | 订阅 | `wiley` | [NS] §2.8.4 |
| 3 | Advanced Functional Materials | 1616-301X / 1616-3028 | Wiley（VCH） | Crossref（0.93） | 订阅 | `wiley` | [NS] §2.8.4 |
| 4 | Acta Materialia | 1359-6454 / — | ScienceDirect | Crossref（0.00） | 订阅 | `elsevier_sd` | [NS] §2.8.4 |
| 5 | Geophysical Research Letters | Crossref 登记 1944-8007 / 0094-8276（p/e 颠倒） | Wiley（AGU；托管关系 ⚠） | Crossref（0.99） | OA（DOAJ） | `wiley` | [NS] §2.8.4 |
| 6 | Earth Planet. Sci. Lett. | 0012-821X / 1385-013X | ScienceDirect | Crossref（0.00） | 订阅 | `elsevier_sd` | [NS] §2.8.4 |
| 7 | Nature Geoscience | 1752-0894 / 1752-0908 | Nature Portfolio | Crossref（0.21） | 订阅 | `nature_portfolio` | [NS] §2.8.4 |

地学与材料的预印本来源（不是 venue）：`chemrxiv`、`ess_open_archive`、`eartharxiv`、`arxiv`（`cond-mat.mtrl-sci`）。本组 venue 只有 7 个，原因是调研只做了简述（NS §2.3.6），见 §7 缺口 K-01。

### 5.11 跨学科综合刊（8）

| # | venue | ISSN（p / e） | 出版平台 | 元数据通道（Crossref 摘要覆盖） | OA 情况 | source_id | 出处 |
|---|---|---|---|---|---|---|---|
| 1 | Nature | 0028-0836 / 1476-4687 | Nature Portfolio | Crossref（0.12）+ PubMed | 混合（2026 年 CC 656/3,312） | `nature_portfolio` | [NS] §2.8.4；[LS] §2.8.1 |
| 2 | Science | 0036-8075 / 1095-9203 | AAAS | Crossref（0.85） | 订阅（2026 年 101/1,563 带复用许可） | `aaas_science` | [NS] §2.8.4；[LS] §2.8.1 |
| 3 | PNAS | 0027-8424 / 1091-6490 | PNAS | Crossref（0.85）+ PubMed | 2026 年 99% 带 CC；6 个月后经 PMC | `pnas` | [NS] §2.8.4；[LS] §2.8.1 |
| 4 | Science Advances | 2375-2548 / 2375-2548 | AAAS | Crossref（0.98） | 全 OA（DOAJ） | `aaas_science` | [NS] §2.8.4；[LS] §2.8.1 |
| 5 | Nature Communications | — / 2041-1723 | Nature Portfolio | Crossref（0.47） | 全 OA（DOAJ） | `nature_portfolio` | [NS] §2.8.4；[LS] §2.8.1 |
| 6 | National Science Review | 2095-5138 / 2053-714X | Oxford Academic | Crossref（0.78） | OA（DOAJ） | `oup_academic` | [NS] §2.8.4 |
| 7 | Proc. R. Soc. A | 1364-5021 / 1471-2946 | Royal Society | Crossref（0.98） | 2026 年 S2O 转 OA | `royal_society` | [NS] §2.8.4 |
| 8 | Phil. Trans. R. Soc. A | 1364-503X / 1471-2962 | Royal Society | Crossref（0.89） | 2026 年 S2O 转 OA | `royal_society` | [NS] §2.8.4 |

### 5.12 其余 venue 的位置

- **理科**：[NS] §2.8 与附件 [NS-CSV]（115 个刊与论文集的 Crossref + OpenAlex 核验原始数据）。§2.8.5 另列论文集系列：JPCS、AIP Conf. Proc.、Proc. SPIE、PoS、EPJ WoC、Oberwolfach Reports、ICM 2022、BAPS。
- **生命科学与心理**：[LS] §2.8（58 个 venue，含 PSB 会议）。
- **经管**：[SS] §2.8（107 个 ISSN，含社会学与政治学简表；未入索引的 UTD24 刊 INFORMS Journal on Computing 见此）；§2.7 期刊名录体系（UTD24、FT50、AJG、ABDC、VHB）。
- **CS/AI**：[CS] §2.3 的"补充映射"（UAI、AISTATS、ALT、ECAI、ICAPS、ICWSM、AIES、AIJ、JAIR、TMLR、KR、AAMAS、WACV、NAACL、EACL、TASLP、ACM MM、IROS、RSS、S&P、CCS、NSDI、SOSP、MLSys、STOC、SODA、FOCS）；§2.5 会议名录体系（CCF 第七版、ICORE2026、CSRankings、ccfddl）。
- **聚合视角**：[AG] §2.6，附件 [AG-JSONL]（204 刊）与 [AG-CONF]（会议 Crossref 分面核验）。

---

## 6. 排除清单与理由

本节是 §3 的派生视图，每行在 §3 中都有完整记录。

### 6.1 excluded（13）

| source_id | 类别 | 理由 | 替代或兜底 | 证据 |
|---|---|---|---|---|
| `pirate_sources` | 红线 | Sci-Hub、LibGen、Anna's Archive 等盗版影子库（AC-0.1、HC-26） | 合法 OA 链 + 用户侧单篇 | [NS] §2.2.5；[LS] §2.7 |
| `google_scholar` | 红线/ToS | 无 API；robots 禁 `/scholar`、`/search`；ToS 禁自动查询 | 用户手动导出后上传；用户自行配置 Scholar Alerts 邮件 | [AG] §2.2.25；[CP] HC-26 |
| `base` | 授权 | API 须 IP 白名单；API 主机 robots 全禁；网站附法律声明，并有 Anubis 挑战 | 其覆盖经 CORE、OpenAIRE、OpenAlex 间接获得 | [AG] §2.2.6 |
| `dimensions` | 条款 | 只对非商业科学计量研究项目免费；v2 的发现与推荐不属此类 | OpenAlex、OpenCitations | [AG] §2.2.22 |
| `scopus` | 条款 | 按用例授权；"展示被引数"用例要求应用不能主要是搜索引擎或 A&I；IR/CRIS 用例不得公开展示摘要 | 用户自带 key 在本人私域富化（可选） | [AG] §2.2.23 |
| `web_of_science` | 条款 | 订阅 + 使用政策，平台层不作数据源 | 同上 | [AG] §2.2.24 |
| `microsoft_academic` | 已关停 | 2021-12-31 关停 | 只兼容 `mag` 外部 ID（OpenAlex 已承接） | [AG] §2.2.26 |
| `scirate` | 挑战门 | robots.txt 本身被 CF 托管质询 | arXiv + HF Papers 信号 | [CS] §2.1.1 |
| `paper_copilot` | 无许可 | GitHub 数据没有 license | 只参考其字段设计 | [CS] §2.2-E |
| `conf_virtual_sites` | robots/未文档化接口 | 数据在 robots 禁区 `/static` 与未文档化的 `/api/miniconf/`（违反 D-014） | OpenReview 与官方论文集；人工核对 | [CS] §1.3、§2.2-B |
| `informs_annual` | 无论文 | 只有摘要级程序 | — | [SS] §2.5 |
| `hbp_hbr` | 无通道 | ISSN 在 Crossref 为 404，无 DOI 可枚举 | 用户手动导入 | [SS] §2.3、§2.8 |
| `econlit` | 订阅书目 | 无公开 API，无数据许可 | JEL 经 RePEc、NBER、ASSA 获取 | [SS] §2.6 |

### 6.2 link-only（2）

| source_id | 理由 | 外链方式 | 证据 |
|---|---|---|---|
| `mathscinet` | robots 基本全禁（Crawl-delay 10）；订阅数据库 | 按 MR 号外链；MR 号可由用户手动补录 | [NS] §2.2.5、§2.3.3 |
| `cas_scifinder` | 学术版条款禁脚本批量抽取、自动化与 AI 用途；每人至多存 5,000 条 | 由用户在其订阅内手动打开 | [NS] §2.2.5、核验 D |

### 6.3 user-import-only（3）

| source_id | 理由 | 导入方式 | 证据 |
|---|---|---|---|
| `cnki` | `kns.cnki.net` robots `Disallow: /`；无开放 API | 用户在机构授权下手动导出 RIS/EndNote 后导入个人库；平台不做代理、不绕 IP 授权 | [AG] §2.2.28 |
| `wanfang` | 检索子域有 WAF；无开放 API | 同上 | [AG] §2.2.28 |
| `cqvip` | robots 部分禁止；无开放 API | 同上 | [AG] §2.2.28 |

### 6.4 metadata-only 中全文零自动化的原因（26 行）

| 原因 | 行 |
|---|---|
| ToU 或政策明文禁止自动化（4） | `ssrn`（ToU 禁任何自动化查询）、`iop`（2026-07 起一切机器访问须另签协议）、`acm_dl`（ToS 禁脚本下载与元数据收割）、`mit_press_direct`（TDM 须书面特批，明文禁脚本抓取） |
| robots 全禁、禁内容路径或 robots 不可读（8） | `apa_psycnet`、`spie_dl`、`acs`、`annals_math`（`Disallow: /annals`）、`mpra`（OAI 在禁区）、`iacr_eprint`（`*` 全禁）、`sciengine`（具名禁 AI UA）、`redalyc`（robots.txt 403） |
| 订阅墙，无开放全文通道（8） | `cepr_dp`、`jstor`、`world_scientific`、`degruyter_brill`、`hogrefe`、`emerald_insight`、`mit_smr`、`now_publishers` |
| 会议程序在登录墙后，或 robots 禁论文路径（2） | `wfa_meeting`、`sfs_cavalcade` |
| 只作链接来源或旁路（4） | `fatcat_ia_scholar`、`ssoar`、`lens`（用户自带 token）、`hbs_wp`（PDF 免费但研究页对本 UA 403，元数据经 SSRN/RePEc） |

### 6.5 不采用的获取方式（与具体来源无关的红线）

- 盗版源与影子库（AC-0.1）；
- 求解或绕过 CAPTCHA 与挑战门（AC-0.2、HC-26）；
- Google Scholar 自动化；
- 用多 key、多账号、多 IP、住宅代理或伪装 UA 规避限额（HC-10；SN API 条款明文禁止）；
- 平台服务器以平台出口代用户访问出版商，或持有可用的出版商会话（P-03、HC-03）；
- 软门与未文档化接口：SSRN 内部 API、NBER 软门、会议 miniconf `/static`（D-014）；
- 访问 robots 禁区路径，包括按年份变化的禁区（如 ISCA 当年卷）；
- 把 IEEE API、Elsevier API、SN Meta API 的内容放进共享索引、嵌入或共享 LLM（HC-11c、HC-27）。

---

## 7. 已知缺口

| # | 缺口 | 影响 | 对策 | 来源 |
|---|---|---|---|---|
| K-01 | 地学：AGU（经 Wiley）、EGU/Copernicus、GSA 等未调研；GeoScienceWorld 的 Crossref 未测 | 地学材料只有 12 行，venue 索引只有 7 个 | 按 §3 的列做补充调研，每个缺口一篇短文 | [SYN] G-05；[NS] §2.3.6、§4-15 |
| K-02 | 材料未单独调研；化学缺开放的细粒度分类法 | 化学与材料的冷启动与路由偏弱 | 补充调研；冷启动先用 OpenAlex subfield 与嵌入 | [SYN] G-05；[NS] §3-11 |
| K-03 | 心理学会议（Psychonomics、SPSP、CCN）与 ISMB/RECOMB 的枚举方式未核 | 心理与计算生物会议覆盖空白 | 补充调研 | [LS] §2.5、§4 Q15 |
| K-04 | CS 长尾：MLSys、RSS 2026 卷、ECCC、now publishers、SIAM 未复测；IEEE API 配额、Kaggle arXiv 版本、HAL OAI、DataCite 增量参数 ⚠ | 对应行为 P2 并带 ⚑RECHECK | 实现前定向勘察 | [CS] §4-11 |
| K-05 | 经管会议：EFA、SED、Econometric Society 区域会议、SMS、Marketing Science Conference 未勘察；ASSA PDF 的再分发授权未核 | 会议事件标签覆盖不全 | 补充调研 | [SS] §2.9、§4-13 |
| K-06 | 中文生态（含 Gitee 开源）未调研；中文 DOI 期刊在 Crossref/OpenAlex 的实际覆盖未测 | 中文/区域没有 P0/P1 | 补一轮中文生态调研；先量化 Crossref/OpenAlex 对中文刊的覆盖 | [SYN] G-05；[AG] §4 Q14 |
| K-07 | OpenDOAR 现状与 API ⚠；Jisc Open policy finder 新 API 的注册方式 ⚠ | 仓储 OAI 端点无法系统枚举；全文共享判定缺辅助信号 | 启用前重新核验 | [AG] §2.2.29 |
| K-08 | robots 与文档化 API 的冲突未获书面确认：NCBI（eutils、ftp）、EBI ftp、ORCID、OSF、eLife、HAL、PubChem、CiNii、IACR；另有 OpenReview 服务账号、dblp 快照使用意图 | 10 行 ⚑ROBOTS、2 行 ⚑ACCT；`pubmed` 首批降级，`pmc` 的 E-utilities 通道暂停 | robots 统一 ADR（简报 §7-2）+ 逐站发函（附邮件模板） | [SYN] G-03；[AG] §4 Q1；[CS] §4-1、§4-3 |
| K-09 | 一批条款只有二手证据：ACS、SIAM、De Gruyter 的 TDM；AMS 的 5 年墙；WSP 的下载阈值；APA、SAGE、PNAS、AAAS 政策页；Research Square API；PubTator3/iCite 限速；Europe PMC 数值限速；SSRN ToU 原文；INFORMS T&C 原文 | 对应行的限速/条款列带 ◐ 或 ⚠ | 人工阅读原文或发函确认，再录入证据字段 | [SYN] G-11；[SS] §4-1、§4-4 |
| K-10 | 出口 IP 影响 WAF 与挑战结论（SAGE、SSRN 的 TLS 中断，Cambridge 的 CF 挑战） | 可达性判断可能偏保守 | 在校园网与用户本地网络复测；平台侧与用户侧分别建可达性画像 | [SYN] G-10；[SS] §4-11 |
| K-11 | 规模化配额与费用不明：Crossref polite 列表池名称与容量、Metadata Plus 价格、OpenAlex 预算、S2 key 与商用书面许可 | 首批新鲜度与联邦检索预算 | 在 T1 负载模型下做配额仿真，并正式询价 | [SYN] G-04；[AG] §4 Q4–Q6 |
| K-12 | 时点事实会过期：arXiv、bioRxiv、PMC、OpenAlex 计费、Crossref 分池、SSRN 平台等 | 名录内容随时间失真 | 季度复核（§8.5）+ 90 天证据时效 | [SYN] G-16、§3.5-3 |
| K-13 | 许可元数据缺口：OpenAlex 许可为空的占比高；Crossref 同一篇有多条 license；Authorea 等没有 license 元数据 | 许可闸误放行或误拒 | 多源投票、取最严、未知即拒；把许可闸精度列为 P0 验收项 | [SYN] R-03；[CP] RK-04 |
| K-14 | 社会学、政治学只做了简述（简报 R2-25：v2.0 覆盖用户点名的经济、金融、商业、管理；社会学、政治学、教育学不在 v2.0 范围，列入补充调研缺口，接入时走同一机制）：SS 的范围写明"社会学、政治学简述"，映射表只有 5 个 venue（ASR、AJS、APSR、AJPS、JOP），除 SocArXiv、SSOAR 外没有学科专属的预印本、仓储或聚合源；§5 venue 索引未收录 | "管"组中的社会学、政治学覆盖只靠跨学科出版商与 Crossref，venue 路由缺种子 | 若产品面向广义社科，补一轮社会学、政治学来源调研；在此之前按 Crossref 委托登记 venue | [SS] §1.1、§2.8 |
| K-15 | 调研映射表中有 venue 的平台未勘察、名录无对应行（简报 R2-26：本轮不增行，列入补充调研缺口）：Project MUSE（JHU Press：Am. J. Math.；BPEA 新刊，Crossref 只到 1999 年 JSTOR 段）、SMF（Ann. Sci. ENS）、UW Press（JHR，Crossref 前缀 10.3368；[v1-econ] 已以 `uwpress`(⚠平台核) 登记） | 这些 venue 无法解析到 `source_id`；元数据暂时只能经 Crossref（Am. J. Math. 摘要 0.98，Ann. Sci. ENS、JHR 为 0） | 按 §3 的列补勘三个平台后增行（初始状态按 §8.4 为 `v2-P2` 或 `metadata-only`）；BPEA 新刊通道须单独确认 | [NS] §2.4、§2.8.1；[SS] §2.8；[v1-econ] |

---

## 8. 实现方案

### 8.1 形态与单一事实来源

- **实现期**：`registry/sources/<source_id>.yaml`，每源一个文件。本文由生成器从注册表渲染：§3 表格、§4 统计、§5 索引、§6 视图。
- **设计期**：本文是手工维护的种子。注册表首次落地时，以本文 187 行与调研原文导入，每条带原调研章节号（综合 §3.5-1）。
- **边界**：运行时状态（健康度、`route_stat`、配额余量）不写回名录；名录只记录"声明与证据"。
- **schema**：字段以 [03] 的 SourceSpec v2 为准；本文 14 列是 SourceSpec 的一个投影。

### 8.2 注册表条目示例

以 `pubmed` 为例，演示闸门、按通道的执行位置与证据字段。

```yaml
# 设计伪代码 —— registry/sources/pubmed.yaml（字段名为示意，schema 以 03 的 SourceSpec v2 为准）
source_id: pubmed
name: "PubMed / MEDLINE"
layer: L2                                 # 03 §3.2 的 layer / kind
kind: aggregator
disciplines: [life_med, psych]            # 生 心（03 §3.2 的学科代码）
directory: {v2_status: v2-P0}             # 简报 R2-10：v2_status 与 v1_status 两个字段
v1: {status: "—"}
gates:
  - {code: ROBOTS, scope: [metadata, latest], adr: pending, confirmation: pending}
channels:
  metadata:
    - family: bulk_snapshot               # 简报 R2-11；年度 baseline + 日更 updatefiles
      host: ftp.ncbi.nlm.nih.gov
      exec_side: platform
      auth: none
      robots: {verdict: disallow_all, checked_at: 2026-09-26}
      tos: {automation: needs_confirmation, attribution: "Courtesy of the U.S. National Library of Medicine"}
      rate_limit: {policy: header_driven}
      evidence:
        - {url: "https://ftp.ncbi.nlm.nih.gov/robots.txt", verified_at: 2026-09-26, ref: "AG 核验 C35"}
    - family: aggregator_api
      mode: api                           # E-utilities 补查
      host: eutils.ncbi.nlm.nih.gov
      exec_side: platform
      auth: deployment_key_optional
      rate_limit: {policy: header_driven, written_cap: "无 key 3 rps；有 key 10 rps，跨 IP 合并"}
      robots: {verdict: disallow_all, checked_at: 2026-09-26}   # NCBI 书面确认前不调用（简报 R2-13）
      evidence:
        - {url: "https://eutils.ncbi.nlm.nih.gov/robots.txt", verified_at: 2026-09-26, ref: "LS §2.3.1"}
  latest: {same_as: metadata, cursor: "EDAT 日窗 / updatefiles"}
  fulltext: {family: none, note: "无全文；链接到 PMC 或出版商"}
abstract_rights: B                        # HC-08：最高展示到 DL3（R2-03）
directory: {section: "L2 仓储与学科库", evidence_refs: ["LS §2.3.1", "AG §2.2.11", "CP §2.1"]}
```

### 8.3 生成与一致性校验

```python
# 设计伪代码 —— 由注册表生成名录并做一致性校验
V2 = {"v2-P0", "v2-P1", "v2-P2", "metadata-only", "link-only", "user-import-only", "excluded"}   # v2_status（R2-10）
V1 = {"v1-implemented", "v1-partial", "v1-designed-only", "—"}                                   # v1_status（R2-10）
NO_AUTOMATION = {"link-only", "user-import-only", "excluded"}

def build_directory(registry_dir, venues_file, today):
    specs = [load_spec(p) for p in sorted(registry_dir.glob("*.yaml"))]
    for s in specs:
        validate(s, today)
    tables = {sec: [render_row(s) for s in specs if s.directory.section == sec] for sec in SECTIONS}
    stats = compute_stats(specs)            # §4 的数字只能出自这里
    venues = render_venue_index(load_venues(venues_file), specs)   # venue 的 source_id 必须存在
    return render(TEMPLATE, tables=tables, stats=stats, venues=venues)

def validate(s, today):
    assert strip_priority(s.directory.v2_status) in V2      # 允许 "metadata-only（P1）"
    assert s.v1.status in V1
    for ch in s.all_channels():
        if ch.family == "official_tdm_api" or ch.gated_fulltext:
            assert ch.exec_side == "user"                     # P-03 / HC-03
        if s.directory.v2_status in NO_AUTOMATION:
            assert ch.family in (None, "link_template")       # 排除类零自动化
        for ev in ch.evidence:
            if (today - ev.verified_at).days > 90:           # 综合 §3.5-2；简报 R2-16
                ch.policy_state = ("review_overdue"           # 探针持续为绿且证据其余字段完整：宽限 30 天、维持原模式
                                   if probes_green(ch) and evidence_complete(ch)
                                   and (today - ev.verified_at).days <= 120
                                   else "needs_confirmation")  # 宽限结束或任一探针告警：上限 on_demand
    for g in s.gates:
        if g.code == "ROBOTS" and g.confirmation != "written":
            for ch in s.channels_in(g.scope):
                ch.background_harvest = False                 # 简报 Q4 默认
        if g.code == "COMM":
            for ch in s.channels_in(g.scope):
                ch.enabled_when = "platform.commercial == false"   # HC-23
```

### 8.4 维护流程

1. **新增来源**：先写调研短文（沿用 §3 的 14 列与证据写法）→ 提交注册表条目，初始状态为 `v2-P2` 或 `metadata-only` → 生成器重建名录与统计 → 主 agent 复核证据 → 合并。
2. **状态变更**：按 §8.6 附证据，由主 agent 或维护者审批。
3. **漂移处置**：漂移探针告警 → 策略引擎自动把该通道降为"仅元数据"或暂停 → 维护者复勘 → 恢复原状态或更新状态。复勘时限由 09 定。
4. **退役**：改为 `excluded` 并写明理由与替代来源；不删除行，以保留可追溯性。
5. **留痕**：注册表 changelog 记录每次变更的证据链接与审批人；提交遵循 `docs/process/git-workflow.md` 的 Conventional Commits。

### 8.5 核验节奏

| 节奏 | 内容 | 涉及的行 |
|---|---|---|
| 持续（事件驱动） | 漂移探针周期比对 robots/ToS 哈希、tdmrep、挑战率、配额头、DOI 前缀/member/publisher，以及"200 空体"；发现漂移即告警并按简报 R2-15 分档降级：robots 与 TDM 信号漂移立即降级，ToS 哈希变化宽限 7 天，元数据通道自身受影响时暂停并切换替补链（探针由 [03] 定义，SI-12） | 全部 P0/P1 |
| 90 天 | 每条通道 `verified_at` 超过 90 天未复核的进入 `review_overdue`（探针持续为绿、证据其余字段完整时宽限 30 天），宽限结束或任一探针告警即降为 on_demand 并标 `needs_confirmation`（简报 R2-16） | 全部 |
| 季度（快变事实清单） | arXiv 独立后的 ToU 与 bulk 渠道；ADS→SciX 切换；bioRxiv API（`/details`、`/funder`）；PMC 自动化通道；OpenAlex 计费与快照节奏；Crossref 分池与池名；SSRN 商业线关停后的平台；dblp robots 与 DROPS 快照；ChemRxiv 在 Wiley REX 上的 API；RSC 迁移进度；OpenReview 匿名接口与限流；HF Hub 限额；S2 key 政策；DataCite GraphQL 弃用（2027-07）；Open policy finder 新 API；Emerald 并入 Wiley 后的平台；AIP、EMS、Royal Society、Annual Reviews 的 S2O 年度状态 | `arxiv`、`nasa_ads_scix`、`biorxiv`、`medrxiv`、`pmc`、`openalex`、`crossref`、`ssrn`、`dblp`、`chemrxiv`、`rsc`、`openreview`、`hf_papers`、`s2`、`datacite`、`open_policy_finder`、`emerald_insight`、`aip`、`ems_press`、`royal_society`、`annual_reviews` |
| 年度 | venue 名录版本（UTD24、FT50、ABDC、AJG、VHB、CCF、ICORE）；各出版商 TDM 与 AI 条款全文复读 | §5 与 L1 出版商各行 |

### 8.6 状态变更规则

| 变更 | 必要证据 | 审批 |
|---|---|---|
| 任意状态 → `excluded` | 条款、红线或授权证据；写明替代来源 | 维护者 |
| `metadata-only` → `v2-Px` | 一手条款原文或书面确认（综合 §3.5-4） | 主 agent |
| 涉及 robots 与文档化 API 冲突的任何变更 | 引用 robots 统一 ADR（简报 §7-2），并附书面确认 | 主 agent |
| `v2-Px` → `metadata-only`（降级） | 漂移探针告警或条款变化即可自动执行，按简报 R2-15 分档（ToS 哈希变化先宽限 7 天），事后补证据 | 自动，维护者事后确认 |
| 解除 ⚑ROBOTS、⚑ACCT | 书面确认；⚑ROBOTS 另须 ADR 登记 | 主 agent |
| 解除 ⚑LIC | 许可或授权文件 | 维护者 |
| 解除 ⚑RECHECK | 补齐所有 ⚠ 项的一手证据 | 维护者 |
| 解除 ⚑DRIFT | 迁移或异常结束后重勘 | 维护者 |
| `v1_status` 变化 | 只随代码事实变化（entry point、VenueSpec），由生成器对照代码仓库核对 | 自动 |

---

## 9. 测试方法、测试类型与验收标准

### 9.1 测试方法

1. **注册表 schema 校验**：必填字段、枚举（层级、学科、状态、闸门、族、执行位置）与证据格式。
2. **生成一致性**：注册表 → 名录的 golden 测试，渲染结果须与仓库内文档逐字节一致。
3. **统计一致性**：§4 的每个数由行数据重算，与渲染结果比对；本稿已用脚本完成首次比对，见附录 A.6。
4. **合规不变式**：用契约测试断言排除类零自动化、用户侧执行、商用开关、robots 闸门等（AC-V0.27、AC-V1.11）。
5. **证据时效**：定时任务扫描 `verified_at`；季度复核清单逐项打勾。
6. **通道契约测试**：每个 P0/P1 通道至少四类离线 fixture：正常、空态（如"200 空体"）、限流（含伪 200 "Rate exceeded."）、robots 禁止或挑战页（[CS] §3-17）。
7. **在线冒烟**：只在显式门控下运行，默认测试保持离线（AGENTS.md）；逐源限量、带预算护栏。
8. **venue 可路由性**：§5 的 venue 按 ISSN 集合（p/e 双查）或 DBLP key 解析到 `source_id`；ISSN 与调研附件逐一比对。
9. **人工评审**：主 agent 季度复核；闸门解除与状态升级的审批。

### 9.2 测试类型

| 类型 | 覆盖对象 | 运行方式 | 门禁 |
|---|---|---|---|
| 单元 | schema、枚举、统计函数、证据时效判定 | CI，离线 | `make check` |
| 契约 | 合规不变式；各 connector 的 fixture 四类 | CI，离线 | `make check` |
| 集成 | 注册表 → 策略引擎 → 调度器：闸门与商用开关是否生效 | CI，离线（模拟上游） | `make check` |
| golden | 注册表 → 名录文档渲染 | CI，离线 | `make check` |
| 在线冒烟 | P0/P1 通道可达性与字段完整性 | 显式门控（参照 `make smoke`） | 发布前 |
| 回放 | 漂移探针对历史漂移样本的检出 | CI，离线 | `make check` |
| 人工评审 | 季度复核、闸门解除、状态升级 | 流程 | 季度与每次变更 |

### 9.3 验收标准（草案）

编号已由 [09 路线图](../plan/v2/09-roadmap-and-milestones.md) 统一定稿为正式编号 `AC-V<m>.<n>`（汇总见附录 B；新旧对照见 09 附录 A）。

- **AC-V0.24 注册表完整性**：`registry/sources/` 的条目数等于名录行数（首版 187）；每条都有 `v1_status`、`v2_status`，以及至少 1 条带 `evidence{url, verified_at}` 的元数据通道。缺任一项，CI 失败。
- **AC-V0.25 生成一致**：由注册表生成的名录（§3 表、§4 统计、§5 索引、§6 视图）与仓库内文档逐字节一致；统计数字 100% 由生成器产出，人工改动 0 处。
- **AC-V0.23 枚举合法**：层级类型、学科代码、状态、闸门、ConnectorFamily、exec_side 的取值 100% 属于 §2 定义的枚举。
- **AC-V0.27 合规不变式**：
  - (a) `link-only`、`user-import-only`、`excluded` 行的自动化 connector 数为 0；
  - (b) `official_tdm_api` 通道与订阅全文通道的 exec_side 100% 为 `U`；
  - (c) `pirate_sources`、`google_scholar` 在调度器与路由器的可选源集合中出现 0 次。
- **AC-V1.11 闸门执行**：
  - (a) 带 ⚑ROBOTS 的通道在取得书面确认前，后台批量调度次数为 0（审计日志可证）；
  - (b) `platform.commercial=true` 时，⚑COMM 通道 100% 停用；
  - (c) 带 ⚑ACCT 的通道在确认前只接受用户 token。
- **AC-V1.8 证据时效**：v2-P0 来源的通道证据 100% 在 90 天以内；超期通道在 24 小时内被策略引擎置为 `needs_confirmation`。
- **AC-V1.19 首批可用**：36 个 v2-P0 来源中，除闸门阻断的通道外（首版为 `pubmed` 两条通道、`pmc` 的 E-utilities、`europe_pmc` 的 bulk、`psyarxiv` 的 OSF API，以及 `openreview`、`tmlr` 的平台账号通道），每个来源至少 1 条元数据通道通过四类离线 fixture 契约测试；在线冒烟在显式门控下通过率 ≥95%。
- **AC-V1.10 漂移响应**：漂移探针检出 robots/ToS 哈希变化、"200 空体"、DOI 前缀/member/publisher 变化后，在 24 小时内告警，并把该通道降为"仅元数据"或暂停。用历史样本回放（bioRxiv `/details` 空体、IHÉS 迁至 Centre Mersenne、dblp robots 改为全禁），检出率 100%。
- **AC-V1.16 venue 可路由**：§5 的 195 个 venue 100% 能按 ISSN 集合（p/e 双查）或 DBLP key 解析到对应 `source_id`；ISSN 与调研附件逐一比对，不符 0 处。
- **AC-V1.20 学科覆盖**：11 个学科组中每组至少 3 个 v2-P0 来源通过 AC-V1.19（按 §4.3，当前最少的组为"跨学科"，共 3 个）。
- **AC-V3.26 季度复核**：§8.5 快变事实清单每季度复核完成率 100%，结论写入注册表 changelog；未完成项自动加 ⚑RECHECK。
- **AC-V0.28 变更留痕**：每次 `v2_status` 或闸门变更 100% 附证据链接与审批记录；涉及 robots 冲突的变更 100% 引用 robots 统一 ADR。

---

## 10. 与 v1 的关系与迁移

### 10.1 v1 文档的去向

| v1 文档 | 在 v2 中的去向 |
|---|---|
| [v1-pub] `publishers-platforms.md`（平台 → adapter 映射总表，D-002 骨架） | 职能由本名录承接：平台映射扩为"来源 × 三通道 × 执行位置 × 闸门"。本名录进入 `approved` 后，建议把它标为 `deprecated` 并链接本文（由维护者执行，本卡不改） |
| [v1-cs]、[v1-ai]、[v1-econ]、[v1-fin]、[v1-or]、[v1-pre]（v1 venue 清单） | 继续作为 v1 VenueSpec 的依据（v1 维护冻结，B-03）；在 v2 中经 ETL 作为 Venue 实体的种子；平台归属以本名录为准 |
| [v1-readme] `catalog/README.md`（venue 登记流程） | v1 流程保留；v2 的来源登记流程见 §8.4，venue 登记流程由 [03] 与 [05] 定义 |

### 10.2 v1 adapter 与名录行的映射

v1 共 20 个生产 adapter（另有测试用 `mock_platform`），全部经 `v1_bridge` 复用（简报 B-03），共对应 21 行。

| v1 adapter | 名录行 | 迁移动作 | 依据 |
|---|---|---|---|
| `arxiv` | `arxiv` | 改用类目级 OAI set，修正物理 set 的 `physics:` 前缀；逐篇 license 入库；全平台单连接；识别伪 200 | [NS] §2.3.5；[CS] §3-6、§3-16 |
| `crossref` | `crossref`（同时承接 92 行 `crossref_delegated`） | 限速改为响应头驱动、按 single/array 池分桶；增量以 `from-created-date` 为主 | [AG] §0、§2.2.1 |
| `openreview` | `openreview`、`tmlr` | 按每次响应头配置限流；`mintmdate` 增量；覆盖扩至 `active_venues`；服务账号待书面确认 | [CS] §2.1.2、§3-9 |
| `pmlr` | `pmlr` | 新卷发现改为"首页 diff + 卷号探测" | [CS] §3-16 |
| `acl_anthology` | `acl_anthology`（兼 `mit_press_direct` 的 TACL/CL 全文） | 扩到全部 Anthology venue；许可按年代区分 | [CS] §2.1.2 |
| `cvf` | `cvf_open_access` | 保持；ECCV 的开放全文改走 `ecva` | [CS] §3-16 |
| `aaai_ojs` | `aaai_ojs` | 扩到同一 OJS 实例的其余 8 个会议或刊 | [CS] §2.1.2 |
| `neurips_proceedings` | `neurips_proceedings` | 补 Position Paper、Creative AI 分轨；接 Curran DOI 做对齐 | [CS] §3-16 |
| `unpaywall` | `unpaywall` | 降为兼容层，新能力改用 OpenAlex | [AG] §2.2.4 |
| `dblp` | `dblp` | 在线 `/db/**` 路径作废（robots 全禁）；改为 DROPS 月度快照 + SPARQL；解除 D-037 的出列状态须新 ADR（简报 §7-3） | [CS] §0；[AG] §2.2.12 |
| `wiley` | `wiley` | 执行位置改到用户侧（扩展或本地代理）；token 端侧加密 | 简报 P-03、§6.3-3；[CP] HC-03、HC-04 |
| `elsevier_sd` | `elsevier_sd`（含 Cell Press） | 同上；API 所得内容不进共享层 | [CP] §2.3.1 |
| `oup_silverchair` | `oup_academic` | 同上 | 简报 P-03 |
| `openalex` | `openalex` | 增加季度快照导入；设美元预算桶 | [AG] §2.2.2 |
| `s2` | `s2` | 申请 key；嵌入走 Datasets；商用须书面确认 | [AG] §2.2.3 |
| `aea` | `aea_journals` | 全文 resolve 改到用户侧 | 简报 P-03 |
| `econsoc` | `econsoc_journals` | 保持 D-028 的分段路由；TE/QE 经 OJS OAI | [SS] §2.3；[DL] D-028 |
| `ssrn` | `ssrn` | 删除浏览器 opt-in 模式 B（新 ADR 取代 D-029/D-030 的相关部分）；只保留 Crossref 元数据 + 外链 | 简报 §7-4；[SS] §3-4 |
| `nber` | `nber_wp`、`nber_conferences` | 全文改到用户侧；新增会议标签；周更元数据文件待授权 | [SS] §2.4、§2.5 |
| `repec` | `repec`（并承接 `cepr_dp`、`iza_dp`、`mpra`、`cesifo_wp`、`sed_meetings` 等） | v1 只映射 NBER `w` 系列（D-036）；要承接非 DOI 的 WP 系列，须扩展 handle 映射（§12 Q-SD-8） | [DL] D-035、D-036 |

### 10.3 受影响的 ADR

| ADR | 影响 | 处理 |
|---|---|---|
| D-002 Adapter × VenueSpec | 演进为 Source/SourceSpec v2 × Venue | 由 [03] 定义；09 起草新 ADR |
| D-005 元数据主干走聚合 API | 延续并扩展：Crossref 主干 + EPMC/PubMed（生命科学）+ OpenAlex 快照底座 | 本名录的通道列即其落实 |
| D-011、D-029、D-030 SSRN | 浏览器 opt-in 模式 B 须被取代 | 简报 §7-4 |
| D-012、D-021、D-026、D-037 dblp | dblp 主站 robots 已全禁，在线路径与路径级读法失效；v2 以快照形态重新入列 | 简报 §7-3（补充 D-037） |
| D-013、D-020、D-024 ACM | 延续：只取元数据 + 外链 | HC-27 |
| D-014 robots/AI-bot 指令 | 须补充"文档化 API 或 bulk 主机与 robots 冲突"的统一规则 | 简报 §7-2 |
| D-023 凭证库 | 扩为按用户、端到端加密；影响全部 `exec_side=U` 的行 | 简报 §6.3-3；[05]、[08] |
| D-027、D-035、D-036 RePEc | 延续 enrich 形态；v2 可能须扩展到非 NBER 系列 | §12 Q-SD-8 |
| D-028 ECMA 分段路由 | 延续 | — |
| D-038 venue-tracking 整域 defer | v2 以 OpenReview `active_venues` 差集 + ccfddl 会期发现新届（[CS] §3-4） | 由 [03]、[04] 裁定 |

### 10.4 v1 名录中已过时的事实（只登记，不在本卡修改）

v1 已维护冻结（B-03），以下条目留待维护者按需勘误：

- **[v1-pub]**：
  - `dblp` 行"~1-2s；429 退避""会议枚举主干"：dblp 主站 robots 已全禁（[CS] §0）。
  - Springer 的检索 RSS `search.rss`：不在 robots 白名单内（[NS] §2.3.4、[LS] §2.4.2）。
  - "link.springer.com 云 IP TLS 拒连"：本轮调研环境可达，可达性与出口 IP 有关（[SS] §2.1 #15）。
  - Cambridge"直连未触发质询"：robots.txt 本身已被 CF 挑战（[SS] §2.1 #14）。
  - INFORMS"云 IP 拒连"：robots 已可读（[SS] §2.1 #16）。
  - OpenAlex"10k credits/天"：已改为每日 $1 额度（[AG] §2.2.2）。
  - "ECMA 由 Wiley 出版"：Crossref publisher 为 The Econometric Society（[SS] 核验 #15）。
  - 行中"JEP(免费)"与 JEL 并列：JEL 只有 green 副本（[SS] §2.1 #7）。
- **[v1-or]**：EJOR 的 `rss.sciencedirect.com` feed 所在主机 robots 为 `Disallow: /`（[SS] §2.1 #12）。
- **[v1-ai]**：
  - TASLP"未改名"：已改名并启用新 ISSN 2998-4173（[CS] §2.1.3）。
  - Elsevier CS 刊在 Crossref 只能用 print ISSN 查询（[CS] §0-9）。
- **[v1-cs]**：
  - ECCV"cvf(镜像)"：开放全文在 ECVA（[CS] §2.1.2）。
  - NeurIPS 自 vol 35 起有 Curran DOI（[CS] §2.1.2）。
  - DBLP 作为枚举主干：只能用快照（[CS] §3-4）。
- **[v1-pre]**：
  - CEPR"robots 点名禁 ClaudeBot + ai-train=no"：2026-09-24 版已无此条目（[SS] §2.1 #9）。
  - arXiv"set 只到 archive 级"：已支持类目级 set（[CS] §2.1.1）。
  - SSRN 模式 B：见 §10.3。

---

## 11. 异议与备选

1. **状态字段：单值枚举与两个正交字段**
   - **简报**（§6.1-7）："每条记录的状态取以下之一：`v1-implemented` / `v2-P0` / …"。
   - **问题**：16 个 v1 已实现来源的 v2 目标各不相同，单值会丢失信息。例如 `ssrn` 是 v1-implemented、v2 为 `metadata-only（P0）`；`dblp` 是 v1-partial、v2 为 `v2-P0`（快照形态）；`arxiv` 是 v1-implemented、v2 为 `v2-P0`。若单值取 `v1-implemented`，路线图就看不到 SSRN 已降级、dblp 须改造。
   - **证据**：综合 §3.1 已采用"v1 列 + 建议状态"的做法；本任务也要求表中分设"v1 状态"与"v2 状态"两列。
   - **本文做法**：`v1_status` 与 `v2_status` 两个字段；简报枚举全部保留，其中 `v1-implemented` 作为 `v1_status` 的取值。
   - **备选**：保留单值，另加 `v2_target` 字段。语义相同，但字段名不直观。
   - **状态**：已由简报 R2-10 采纳；`v1_status` 取值为 `v1-implemented` / `v1-partial` / `v1-designed-only` / `—`，本表 43 处原记法 `v1-design` 已改为 `v1-designed-only`。[03] §2.6、§3.2 与 05 `corpus.source` 已对齐。
2. **ConnectorFamily 族表没有 bulk 快照族**
   - **现状**：简报 §6.1-2 把 OpenAlex 季度快照、PubMed baseline、Crossref 年度文件、DROPS dblp 定为本地底座，但 §5 的族表没有对应的族。
   - **本文做法**：记为 `bulk_snapshot`，共 18 行。
   - **备选**：新增 `bulk_snapshot` 族。好处是 bulk 主机的 robots 登记（简报 §7-2）与存储预算可以按族管理；代价是多一个族。
   - **状态**：已由简报 R2-11 采纳新增 `bulk_snapshot` 族；本表 18 行改用该族名（[03] §5.3）。
3. **简报 §6.1-4 第一句的字面解读**
   - **问题**：简报写"只为有官方 API/协议通道的站点写代码"。按字面，PMLR、CVF、NeurIPS、USENIX、IJCAI 年页、ISCA、PVLDB 卷页、ECVA、ASSA 程序页这类没有 API 的 OA 论文集静态页都不能写 connector。
   - **后果**：其中 PMLR、CVF、NeurIPS 在 v1 已实现或部分实现，CS 调研还把它们列为 P0 的"平台原生接口"（[CS] §3-3）。字面执行会让 ICML、CVPR、NeurIPS 的开放版失去首发通道。
   - **本文解读**：结合该条第二句"WAF 或 robots 全禁的出版商站点不写抓取型 connector"，只允许为同时满足三条的 OA 论文集静态页写 `site_special`：robots 允许；结构稳定；无挑战门。并以 P-05 最严判定与漂移探针兜底。
   - **涉及范围**：本名录共 25 行用到 `site_special`。其中 8 行是官方 API（PLOS、APS Harvest、bioRxiv、OSF、Janeway、World Bank D&R、eLife、OpenReview），1 行是官方数据包（ACL Anthology 的 GitHub XML），2 行是用户侧单篇（Cambridge、IEEE），这 11 行不受本异议影响。受影响的是 14 行无 API 的静态页：JMLR 卷页、TMLR 列表、PMLR、NeurIPS、CVF、ECVA、IJCAI 年页、USENIX、PVLDB 卷页、ISCA、RSS、CEUR、ASSA 程序页、NBER 会议页；其中 PMLR、NeurIPS、CVF 在 v1 已实现。
   - **状态**：已由简报 R2-12 采纳这一解读：robots 允许、结构稳定、无挑战门的 OA 论文集静态页允许 `site_special`，受 P-05 与漂移探针约束；"免费阅读但未声明开放许可"的全文不进共享缓存，默认外链或用户侧取回。
4. **PubMed 在 Q4 默认下能否作为首批主干**
   - **简报**（§6.1-2）：生命科学以 Europe PMC / PubMed 为主干。
   - **问题**：按 Q4 默认，PubMed 的 E-utilities 主机与 bulk 主机都在 robots 全禁范围内，书面确认前不能做后台批量。
   - **证据**：[AG] 核验 C35；[LS] §2.3.1。
   - **本文做法**：`pubmed` 保持 `v2-P0`、带 ⚑ROBOTS；首批生命科学主干由 `europe_pmc`（REST 路径未被禁止，按 `Crawl-Delay: 10` 执行）+ `pmc`（S3、OAI）+ Crossref 承担。这是对简报的细化，不改变方向。
   - **建议**：09 把"向 NCBI 书面确认"列为生命科学里程碑的前置任务。
   - **状态**：已由简报 R2-13 按本文做法裁定；确认前 E-utilities 的按需调用也不做（[03] §6.8 与 04 §20 第 3 项的从严读法）。
5. **Springer Nature OA API 的凭证模型**
   - **现状**：[NS] §2.2.1（认证列）、§3-7 与综合 §3.2 都写"每用户 api_key"，所以本文把 SN API 通道记为 `U`。
   - **问题**：OA API 返回的是 CC BY 全文，本可进共享层。但若经用户 key 取回，按 P-02"派生继承最严"只能留在该用户私域，平台共享层就拿不到 SN 的 CC BY 全文。
   - **备选**：平台用一个部署级 key 调 OA API。这符合 HC-10"一个上游一个平台身份"，但须确认 SN API 条款是否允许平台级用途；已知条款禁止多 key 规避限额，SN API 摘要只许个人使用（[NS] 核验 B；[CP] §2.2.1）。
   - **本文暂按调研口径记为 `U`**，共享层的 SN OA 全文先经 PMC、OpenAlex 等 OA 链获取。列入 §12 Q-SD-3。
   - **状态**：简报 R2-14 裁定：条款书面确认前按用户级凭证（更严）处理，SN Meta API 摘要按 C 类、不进共享层。
6. **NASA ADS token 的归属**
   - **分歧**：[NS] §2.2.3 写"token 必须由每个用户自己持有"；[AG] §2.2.27 写"用户或平台自带 token 时启用"。
   - **本文做法**：取更严的 NS 口径，记为 `U`。
   - **备选**：部署级 token（须先核 ADS 条款）。列入 Q-SD-4。
   - **状态**：简报 R2-14 裁定按用户级凭证处理，直至条款书面确认。
7. **L2 层级缺少"注册表"类型**
   - **现状**：简报 §6.1-1 的 L2 只有 repository、aggregator 两类。ORCID、ROR、DataCite、OpenCitations、Wikidata、Open policy finder 实为身份、引文或政策注册表；本任务也单设"身份与引文注册表"一节。
   - **本文做法**：沿用综合的写法"L2-aggregator（注册表）"。
   - **备选**：在 SourceSpec 中增加 `registry` 子类型，便于 [04] 的路由与 [05] 的身份图区分"论文源"与"标识源"。影响小，留给 [03] 裁定。
   - **状态**：已由简报 R2-11 采纳 L2 子类型 `registry`（ORCID、ROR、DataCite 等）；本表 `orcid`、`ror`、`datacite` 三行改记 `L2-registry`，OpenCitations、Wikidata、Open policy finder 仍为 `L2-aggregator`（与 [03] §2.1 一致）。
8. **预印本"走原生通道"在首批的落地**
   - **简报**（§6.1-2）："预印本走各平台原生通道（arXiv OAI 类目级 set、bioRxiv API、OSF 等）"；综合 §2.1 推荐方案 2 写作"openRxiv 经 Crossref 兜底"。
   - **问题**：bioRxiv 官方 API 的 `/details`、`/funder` 于 2026-09-26 返回 200 空体（[LS] §2.2.1、§4 Q1）；OSF API 主机 `api.osf.io` 的 robots 为 `Disallow: /`（[LS] §2.2.3；[AG] §2.2.17）。按 P-05 与简报 Q4 默认，这两条原生通道在首批都不能作后台主通道。
   - **本文做法**：`biorxiv`、`medrxiv` 以 Crossref `member:54368`（或 `prefix:10.64898`）为元数据与最新论文的首选通道，官方 API 保留为补充（⚑DRIFT）；`psyarxiv` 以 Crossref 10.31234 + EPMC 为首选，OSF API 待书面确认（⚑ROBOTS，仅 OSF API）。arXiv 仍走原生 OAI。这是对简报的细化，方向不变；漂移恢复或取得书面确认后，原生 API 可升为首选（§8.6）。
   - **状态**：已由简报 R2-13 裁定：bioRxiv、medRxiv、PsyArXiv 以 Crossref 为首选、原生 API 为补充；[03] §7.2、§7.3 已沿用。

---

## 12. 待决问题

| # | 问题 | 影响的行 | 建议的下一步 | 归属 |
|---|---|---|---|---|
| Q-SD-1 | robots 统一 ADR 与逐站书面确认：NCBI（eutils、ftp）、EBI ftp、ORCID、OSF、eLife、HAL、PubChem、CiNii、IACR | 10 行 ⚑ROBOTS；`pubmed` 首批降级，`pmc` 的 E-utilities 通道暂停 | 09 起草 ADR（简报 §7-2），附邮件模板；先办 NCBI 与 OSF | 09、08 |
| Q-SD-2 | OpenReview 平台服务账号的合规性 | `openreview`、`tmlr`（v2-P0） | **已裁决**（简报 R2-20）：书面确认前平台侧共享收割停用，ICLR、TMLR、COLM 等由 arXiv 版本 + DROPS dblp 快照 + 外链兜底；用户本人 token 只在用户侧供本人查询，不用于共享收割；V0 即发函 | 09（简报 §7-12） |
| Q-SD-3 | SN OA API 用部署级 key 还是用户 key（§11 异议 5） | `springer_link`、`nature_portfolio` | 简报 R2-14：书面确认前按用户级凭证；仍须核读 SN API 条款中平台级用途的规定 | 03、08 |
| Q-SD-4 | ADS token 能否部署级持有（§11 异议 6） | `nasa_ads_scix` | 简报 R2-14：书面确认前按用户级凭证；核读 ADS 条款，SciX 切换后重测 | 03 |
| Q-SD-5 | 数据许可：CORE（推荐与检索类产品须先获许可）、NBER 周更元数据文件、APS Harvest 全量 | `core`、`nber_wp`、`aps` | 分别发函申请 | 08 |
| Q-SD-6 | 状态字段形态（§11 异议 1）与 bulk 族（§11 异议 2） | 全部 | **已裁决**（简报 R2-10、R2-11） | 03 |
| Q-SD-7 | 对简报 §6.1-4 的解读（§11 异议 3） | 14 行静态页 `site_special`（含 v2-P0 的 `jmlr`、`tmlr`、`pmlr`、`neurips_proceedings`、`cvf_open_access`、`ijcai_proceedings`） | **已裁决**（简报 R2-12） | 主 agent |
| Q-SD-8 | RePEc 是否扩展到非 NBER 系列（v1 只映射 `w`，D-036） | `cepr_dp`、`iza_dp`、`mpra`、`cesifo_wp`、`sed_meetings`、`other_cb_wp` | 评估 ReDIF handle 映射的扩展成本；须新 ADR 修订 D-036 | 03、09 |
| Q-SD-9 | "免费阅读但未声明开放许可"的会议全文能否进共享层 | `cvf_open_access`、`neurips_proceedings`、`pmlr`、`aaai_ojs`、`ijcai_proceedings`、`usenix`、`isca_archive`、`ecva`、`ndss` | **已裁决**（简报 R2-12）：不进共享缓存，默认外链或用户侧取回；可向主办方确认许可后按单篇许可重判 | 08 |
| Q-SD-10 | venue 名录体系的许可（FT50、AJG、ABDC、ICORE、CSRankings）：内置还是只供用户私有导入 | §5 的名录标签 | 按 [SS] §3-10、[CS] §4-7 的建议，首版只内置 UTD24 与学界约定名单 | 08、04 |
| Q-SD-11 | 补充调研（K-01…K-07、K-14、K-15）的排期，以及新增行的准入门槛 | 地学材料、中文/区域、心理学会议、社会学与政治学（简报 R2-25：不在 v2.0 范围）、Project MUSE / SMF / UW Press（R2-26：本轮不增行） | 09 排入 V? 调研任务；新增行沿用 §3 的列 | 09 |
| Q-SD-12 | 社区信号源（HF Papers、alphaXiv）用于推荐与商用、长期缓存的条款 | `hf_papers`、`alphaxiv` | 核读 HF ToS | 06、08 |
| Q-SD-13 | 用户手动下载的 SSRN CC 许可论文能否进平台缓存 | `ssrn` | 按 [SS] §4-16，裁定前只外链 | 08 |
| Q-SD-14 | 央行与国际组织 WP 的再分发许可（Fed、ECB、BIS、IMF、World Bank） | `fed_board_wp`、`ecb_wp`、`bis_wp`、`imf_wp`、`worldbank_prwp` | 逐源核读条款（[SS] §4-15） | 08 |
| Q-SD-15 | 预印本首批以 Crossref 为首选、原生 API 为补充（§11 异议 8） | `biorxiv`、`medrxiv`、`psyarxiv` | **已裁决**（简报 R2-13）；[03] 已落实 | 主 agent、03 |

---

## 13. 术语

本文新增或细化的共享术语，供 [01] 汇总到术语节：

| 术语 | 含义 | 出处 |
|---|---|---|
| 支持名录（Source Directory） | 本文；来源注册表的文档投影 | §0 |
| 来源注册表（Source Registry） | `registry/sources/*.yaml`，名录的单一事实来源；条目即 SourceSpec v2 | §8.1 |
| `v1_status` / `v2_status` | 名录状态的两个正交字段（简报 R2-10 已采纳） | §2.1 |
| 登记优先级 | `metadata-only（Px）` 中的 Px（简报 §6.1-7） | §2.1 |
| 闸门（Gate） | 名录层的合规与运营约束标记，共 8 种：ROBOTS、ACCT、COMM、LIC、BUDGET、DRIFT、RECHECK、SA | §2.2 |
| `needs_confirmation` | 策略引擎对冲突证据或过期证据的处置状态（简报 P-05） | §2.2 |
| 通道记法 M/L/F | 元数据 / 最新论文 / 全文通道 | §2.5 |
| OA 链 | 经 OA 定位链在平台侧取回逐篇许可白名单内的全文 | §2.5 |
| 用户侧单篇 | 由配套扩展或本地代理在用户本人会话中单篇取回 | §2.5 |
| `bulk_snapshot` | 快照与年度文件导入的 ConnectorFamily（简报 R2-11；原记法 `aggregator_api[bulk]` 废止） | §2.5 |
| 学科组代码 | 数、物、化、地材、生、心、经、金、管、CS、全、区 | §2.4 |
| 代表性 venue 索引 | 按学科组列出的核心 venue 与其 `source_id` | §5 |
| 快变事实清单 | 按季度复核的易变事实 | §8.5 |
| 证据时效 | `verified_at` 超过 90 天进入 `review_overdue`，宽限 30 天后降级并标 `needs_confirmation`（简报 R2-16） | §8.5 |

---

## 14. 参考

**上游约束与证据层**
- [v2 设计决策简报][BRIEF]：§1（R1）、§3（B-03、B-06）、§4（P-01…P-09）、§5（术语）、§6.1、§7（ADR 候选 2、3、4、9、10、12）、§8（Q1、Q2、Q3、Q4）。
- [调研综合][SYN]：§1.6（局限）、§2.1、§3（全节）、§5（T4、T8、T11、T18）、§6（SI-01…SI-20、SI-37、SI-38、HC 摘要）、§7（R-03、G-03…G-05、G-10、G-11、G-16）。

**来源调研**（核验日期 2026-09-26）
- [NS] 理科：§2.2 名录总表、§2.3 分源详述、§2.4 Crossref 质量、§2.5 防护矩阵、§2.6 最新通道、§2.8 venue 映射、§3、§4、核验记录；附件 [NS-CSV]。
- [LS] 生命科学与心理学：§2.2–§2.6、§2.7 名录表、§2.8 venue 映射、§2.9 robots 矩阵、§3、§4、核验记录。
- [SS] 经济、金融、商业、管理：§2.1 v1 复核、§2.2 平台族、§2.3–§2.6 名录 A–D、§2.7 名录体系、§2.8 venue 映射、§2.9 会议形态、§3、§4、核验记录。
- [CS] 计算机与 AI：§0、§2.1 变化核验、§2.2 名录表、§2.3 venue 映射、§2.4 元数据可得性、§2.6 最新通道、§2.7 许可矩阵、§3、§4、核验记录。
- [AG] 聚合与仓储：§0、§2.2 逐源档案、§2.3 跨源对比、§2.4 路由矩阵、§2.5 名录表、§2.6 venue 映射、§3、§4、核验记录；附件 [AG-JSONL]、[AG-CONF]。

**合规**
- [CP]：§2.1（元数据许可逐源）、§2.2（摘要与图）、§2.3（TDM 与每用户私有）、§2.4（礼貌性）、§2.7（合规矩阵 M1–M25）、§3.1（HC-01…HC-28）。

**v1 文档**
- [v1-readme]、[v1-pub]、[v1-cs]、[v1-ai]、[v1-econ]、[v1-fin]、[v1-or]、[v1-pre]；[决策日志][DL]（D-002、D-005、D-011…D-014、D-020、D-021、D-023、D-024、D-026…D-030、D-035…D-038）；[v1 adapter 设计目录][v1-adapters]。

**v2 兄弟文档**（设计阶段并行起草）
- [01] 愿景与需求、[03] 来源与语料流水线、[04] 检索与路由、[05] 数据平台、[08] 合规安全隐私；02（架构）与 09（路线图）见 `docs/plan/v2/`。

[BRIEF]: ../plan/v2/00-design-brief.md
[SYN]: ../survey/00-survey-synthesis.md
[NS]: ../survey/sources/natural-sciences.md
[LS]: ../survey/sources/life-sciences-psychology.md
[SS]: ../survey/sources/social-sciences-econ-fin-mgmt.md
[CS]: ../survey/sources/cs-ai.md
[AG]: ../survey/sources/aggregators-repositories.md
[CP]: ../survey/compliance/multi-user-platform-compliance.md
[NS-CSV]: ../survey/sources/natural-sciences/venue-verification-2026-09-26.csv
[AG-JSONL]: ../survey/sources/aggregators-repositories/venue-verification-2026-09-26.jsonl
[AG-CONF]: ../survey/sources/aggregators-repositories/conference-crossref-check-2026-09-26.json
[DL]: ../plan/decision-log.md
[v1-readme]: ../archive-v1.md#docs-catalog-readme-md
[v1-pub]: ../archive-v1.md#docs-catalog-publishers-platforms-md
[v1-cs]: ../archive-v1.md#docs-catalog-cs-ai-conferences-md
[v1-ai]: ../archive-v1.md#docs-catalog-ai-ml-journals-md
[v1-econ]: ../archive-v1.md#docs-catalog-economics-journals-md
[v1-fin]: ../archive-v1.md#docs-catalog-finance-journals-md
[v1-or]: ../archive-v1.md#docs-catalog-or-ms-journals-md
[v1-pre]: ../archive-v1.md#docs-catalog-preprint-platforms-md
[v1-adapters]: ../archive-v1.md#docs-design-adapters-readme-md
[01]: ../plan/v2/01-vision-and-requirements.md
[03]: ../plan/v2/03-sources-and-corpus-pipeline.md
[04]: ../plan/v2/04-retrieval-and-routing.md
[05]: ../plan/v2/05-data-platform.md
[08]: ../plan/v2/08-compliance-security-privacy.md

---

## 附录 A：与综合 §3.2 的差异清单

本附录由脚本逐行比对 §3 与综合 §3.2 生成，再逐条补写依据。

### A.1 v1 状态修正（17 行）

| source_id | 综合 §3.2 | 本文 | 依据 |
|---|---|---|---|
| `aps`、`iop`、`aip`、`optica`、`edp_sciences`、`acs`、`rsc`、`ams`、`royal_society`（9 行） | 部分 | — | NS 对"部分"的定义是"v1 的 crossref 通用 adapter 可按 ISSN 枚举元数据，但没有 VenueSpec，也没有全文 adapter"（[NS] §2.2）。这一能力对所有 `crossref_delegated` 来源普遍成立（同为 Crossref 可枚举的 `tandf_online`、`nature_portfolio` 等在综合中记为"否"），不能区分来源。全量核对 `venues/` 的 62 个 VenueSpec，没有这 9 个来源的任何条目 |
| `osf_preprints`、`research_square` | 否 | `v1-designed-only` | 在 [v1-pre] §6 以"暂缓"登记（与已记为"设计"的 `eccc` 同表） |
| `econstor` | 否 | `v1-designed-only` | 在 [v1-pre] §6 登记为"不单独 adapter" |
| `annual_reviews` | 否 | `v1-designed-only` | 在 [v1-fin] 以 `annual_reviews`(⚠) 平台登记 ARFE（T3） |
| `tandf_online` | 否 | `v1-designed-only` | 在 [v1-fin] 以 `tandf`(⚠平台核) 登记 Quantitative Finance |
| `jair` | 否 | `v1-designed-only` | 在 [v1-ai] 以 `jair`（OJS 类）登记（T2） |
| `tmlr` | 否 | `v1-designed-only` | 在 [v1-ai] 登记为经 `openreview` 运行（T1），未注册 VenueSpec |
| `cepr_dp` | 部分（经 RePEc 元数据） | `v1-designed-only` | v1 `repec` 是零网络 enrich，只按 DOI 回填，且映射已收窄为 NBER `w` 系列（[DL] D-035、D-036）；CEPR DP 在 Crossref 没有记录，v1 实际不产出 CEPR 条目。v1 只有 catalog 登记（[v1-pre] §5） |

### A.2 学科标注修正（8 行，不含按学科组的机械拆分）

| source_id | 综合 §3.2 | 本文 | 依据 |
|---|---|---|---|
| `arxiv` | 数 物 CS 生 经 | 数 物 地材 生 经 金 CS | `cond-mat.mtrl-sci` 覆盖材料预印本（[NS] §2.3.6）；`econ.*`/`q-fin.*` 分拆为经、金 |
| `chemrxiv` | 化 | 化 地材 | NS 名录学科列为"化学/材料"（[NS] §2.2.2） |
| `acs` | 化 | 化 地材 | NS 名录学科列为"化学/材料"（[NS] §2.2.1） |
| `mdpi` | 数 物 化 生 心 | 数 物 化 地材 生 心 | NS 名录学科列为"化学/材料/数学/物理"（[NS] §2.2.1，核验补充） |
| `elsevier_sd` | 数 物 化 生 心 经 管 CS | 数 物 化 地材 生 心 经 金 管 CS | Acta Materialia、EPSL 在 NS 映射中归 `elsevier_sd`（[NS] §2.8.4）；经管侧学科列为"经济/金融/会计/管理/OR"（[SS] §2.3） |
| `nature_portfolio` | 物 化 生 心 | 物 化 地材 生 心 | Nature Materials、Nature Geoscience 归 `nature_portfolio`（[NS] §2.8.4） |
| `informs_pubsonline` | 管 经 | 管 | SS 名录学科列为"管理科学/营销/IS/OR/组织"（[SS] §2.3），映射表也把 MS 等归入"商业" |
| `now_publishers` | CS 经 | CS | CS 名录学科列为"ML 综述"（[CS] §2.2-D）；经管侧原 now publishers 刊物（CFR）已随 2025-05 收购归入 Emerald，计入 `emerald_insight`（[SS] §2.3、核验 S4） |

### A.3 按本任务学科组所做的机械重编码

- 综合的"经"（经济/金融）按各来源调研名录表的"学科"列拆为"经""金"：例如 `nber_wp` 为"经济/金融"→ 经 金；`pm_research` 为"实务金融/量化"→ 金；`emerald_insight` 为"管理/营销/运营/金融"→ 金 管；`wfa_meeting`、`sfs_cavalcade`、`efa_meeting` 为金融会议 → 金。
- 综合的"地"并入"地材"；`osti_gov` 的"物理/化学/材料/能源"记为 物 化 地材。
- 这些重编码在换回综合的代码后与综合一致，脚本比对无差异。

### A.4 分节调整

- **区域 L1 移入 §3.8**：`chinaxiv`（原 §3.2.3）、`ccs_chemistry`（原 §3.2.4）、`sciengine`、`wulixb`、`jstage`（原 §3.2.5）。
- **排除类按自然所属分节**：综合 §3.2.7 的排除行放回自然所属的节。`conf_virtual_sites`、`informs_annual` → §3.4；`mathscinet`、`cas_scifinder`、`econlit` → §3.6；`scopus`、`web_of_science`、`dimensions`、`base`、`microsoft_academic`、`google_scholar`、`scirate`、`paper_copilot`、`pirate_sources` → §3.5。§6 另给排除视图。
- **L2 重分三节**：综合 §3.2.1 与 §3.2.2 的 L2 行重分为：
  - §3.5 聚合器；
  - §3.6 仓储与学科库：`core`、`zenodo`、`hal` 与全部学科库；
  - §3.7 身份与引文注册表：`orcid`、`ror`、`datacite`、`opencitations`、`wikidata`、`open_policy_finder`。
  - 社区信号层（`hf_papers`、`pwc_archive`、`alphaxiv`）归入聚合器。

### A.5 新增与拆分的列

- **新增三列**：
  - ConnectorFamily、exec_side：按简报 §5 与 P-03，由各调研的通道事实推导，属初始归类。
  - 认证：取自来源调研名录表的"认证方式"列。
- **拆分两列**：综合的"接入通道（元数据/最新）"与"全文门控"两列，拆回来源调研的"元数据通道 / 最新论文通道 / 全文通道与门控 / 限速与 ToS"四列。
- **新增闸门标记**（§2.2），写在"v2 状态"列的第二行。

### A.6 未改动项与一致性自检

- 187 个 `source_id` 与综合 §3.2 一一对应，无增删；层级类型 187/187 一致；v2 状态（含 `metadata-only` 的登记优先级）187/187 一致。
- 在综合原有的 11 个学科代码下，本文的行数据重算得到的统计与综合 §3.3 逐格相同（数、物、化、生、心、管、CS、全、区；经与地因重编码另计，见 §4.5）。
- §5 的 316 个 ISSN、140 组 p/e 配对全部可在调研原文或附件中找到。

---

## 附录 B：验收标准编号

| 编号 | 标题 | 测试类型 |
|---|---|---|
| AC-V0.24 | 注册表完整性 | 单元 |
| AC-V0.25 | 生成一致 | golden |
| AC-V0.23 | 枚举合法 | 单元 |
| AC-V0.27 | 合规不变式 | 契约 |
| AC-V1.11 | 闸门执行 | 契约 + 集成 |
| AC-V1.8 | 证据时效 | 单元 + 定时任务 |
| AC-V1.19 | 首批可用 | 契约 + 在线冒烟（门控） |
| AC-V1.10 | 漂移响应 | 回放 + 集成 |
| AC-V1.16 | venue 可路由 | 单元 |
| AC-V1.20 | 学科覆盖 | 集成 + 人工评审 |
| AC-V3.26 | 季度复核 | 流程（人工评审） |
| AC-V0.28 | 变更留痕 | 契约 + 流程 |

---

## 评审记录

第 1 轮（COVER）核对范围：§3 的 187 行逐行对照综合 §3.2 与五篇来源调研的名录表（`source_id` 一一对应，v2 状态与综合 §3.4 裁决 187/187 一致）；§3 各行的数字、端点与路径逐个在所引调研的该源上下文中检索命中；证据列所引章节与"核验"编号全部可解析且提及该源；§5 的 195 个 venue、316 个 ISSN、140 组 p/e 配对、摘要覆盖值与 `source_id` 均对得上调研映射表；§4 的统计由脚本从 §3 重算。以下为发现的问题。

| 轮次 | 视角 | 问题 | 严重度 | 处理 |
|---|---|---|---|---|
| 1 | COVER | `pmc` 把 E-utilities 列为通道、限速列也写明其受 robots 约束（eutils 主机 `Disallow: /`，[AG] §2.2.11），但 v2 状态没有 ⚑ROBOTS，后台调度会误放行 | 中 | 已修：加 `⚑ROBOTS（仅 E-utilities）`；同步 §0-6（66 行）、§4.1 闸门统计与明细、K-08、Q-SD-1、AC-V1.19 |
| 1 | COVER | §4.4 称地学材料"没有学科专属来源"，与表不符：GeoScienceWorld、ESS Open Archive、EarthArXiv 均为地学专属（全为 P2） | 中 | 已修：改写该行评估，并补 [NS] §2.2.1、§2.2.2 |
| 1 | COVER | 已知缺口漏列社会学、政治学：SS 范围写明只作简述（映射表 5 个 venue），而本文"管"组声称包含二者 | 中 | 已修：新增 K-14；同步 §0-7、§4.4 商业管理、Q-SD-11 |
| 1 | COVER | 已知缺口漏列调研映射表中"平台未勘察"的 venue：Project MUSE（Am. J. Math.、BPEA）、SMF（Ann. Sci. ENS）、UW Press（JHR，v1 catalog 已登记 `uwpress`），名录无对应行，venue 无法路由 | 中 | 已修：新增 K-15；同步 §0-7、§4.4 数学与经济、Q-SD-11。是否增行转主 agent |
| 1 | COVER | 简报 §6.1-2"预印本走原生通道（bioRxiv API、OSF）"、综合 §2.1"openRxiv 经 Crossref 兜底"，本文实际把 `biorxiv`、`medrxiv`、`psyarxiv` 的首选通道定为 Crossref，未记入异议（静默细化） | 中 | 已修：新增 §11 异议 8 与 Q-SD-15；转主 agent 确认 |
| 1 | COVER | "出版商与期刊平台 63 个非排除行中 55 行元数据只靠 Crossref"无法由表重算，按任何一致口径均为 53 行 | 低 | 已修：§0-4、§4.1 改为 53，写明口径（平台侧，用户侧 API 不计）并列出其余 10 行 |
| 1 | COVER | 接入工作量 66/93/10 未写分类规则；只有把族级 `platform_family` 计为共享、把"同 `x`"的 `medrxiv` 计为需配置时才能复现 | 低 | 已修：§4.1 写明规则（数字不变，脚本复核一致） |
| 1 | COVER | `hf_papers` 是唯一带 ⚑RECHECK 的 v2-P0 行；按 §2.2 未注明范围即"启用前复勘"全部通道，与 P0 及 AC-V1.19 冲突，而 ⚠ 只涉及商用与长期缓存条款（[CS] §4-6） | 低 | 已修：限定为"仅商用与长期缓存条款"，闸门明细同步 |
| 1 | COVER | AC-V1.19 列举的闸门阻断通道不全，漏 `europe_pmc` 的 bulk 与 `psyarxiv` 的 OSF API | 低 | 已修：补全（含 `pmc` 的 E-utilities） |
| 1 | COVER | §6.4 把 `hbs_wp` 归入"订阅墙"；调研记为免费 PDF，受阻于研究页 403，元数据经 SSRN/RePEc | 低 | 已修：移入"只作链接来源或旁路"（8/4，合计仍 26） |
| 1 | COVER | §11 异议 5 称 [NS] §3-4 写"每用户 api_key"；该条未写，出处应为 [NS] §2.2.1 认证列与 §3-7 | 低 | 已修 |
| 1 | COVER | `datacite` 的优先级在 CS 内部不一致（§2.2-E 为 P1、§3-15 为 P0）；本文随综合 §3.4 记 v2-P1 | 低 | 保留：综合 §3.4 已裁决；转主 agent 知悉 |
| 1 | COVER | [03]、[04] 链接目标尚未落盘 | 低 | 保留：兄弟文档并行起草中，简报采用同一链接 |
| 1 | COVER | v1 状态口径有残留不一：`aaai_ojs`（仅注册 AAAI）记 v1-implemented，而同为单 venue 注册的 `pmlr`、`acl_anthology`、`openreview` 记 v1-partial；v1 catalog 以 `springer` 登记了 Nature Machine Intelligence，`nature_portfolio` 仍记"—" | 低 | 保留：沿用 CS 与综合的判定，不影响 v2 范围；由 §8.6 的生成器按代码核对时统一 |
| 1 | COVER | `pnas` 全文多为 CC BY-NC-ND（2026 年 2,841/3,649）却无 ⚑COMM，而 `sfn_journals` 有 | 低 | 保留：`pnas` 许可混合，逐篇 NC 由 §2.7-4 的许可白名单处理；⚑COMM 只用于整源限非商业（`sfn_journals` 2026 年 439/523 为 BY-NC-SA） |
| 审计 | 一致性（2026-09-27） | 与简报 §10 不一致：`v1-design` 取值、`aggregator_api[bulk]` 记法、L2 注册表类型、V3 展示级、证据逾期与漂移处置口径、OpenReview/PubMed/SN/ADS 过渡、MSC2020、社科范围与 MUSE/SMF/UW Press | 中 | 已修：按 R2-03/08/10/11/12/13/14/15/16/17/18/20/21/22/25/26 改写（43 处 `v1-designed-only`、22 处 `bulk_snapshot`、3 行 `L2-registry`、表头 `v1_status`/`v2_status`、§4.1 统计重算、§8.2–§8.3 示例对齐 03 schema）；§11、§12 标注裁决状态 |
