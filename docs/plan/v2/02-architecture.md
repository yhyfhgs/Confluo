---
title: v2 总体架构
status: draft
owner: opus5.5-design
updated: 2026-09-27
---

# 02 · v2 总体架构

> **定位**：v2 设计阶段文档 02。按[设计决策简报](00-design-brief.md) §9 的接口归属，本文定义**组件边界、服务拓扑、部署形态与 API 面**，03–07 引用。
> 本文只回答"某项能力在哪个组件里执行、与谁交互、失败时怎样退"。算法与参数的定义方如下：
> - 路由、调度与稳定性：[04](04-retrieval-and-routing.md)；
> - SourceSpec v2、Connector、Policy Engine 的实现、语料流水线：[03](03-sources-and-corpus-pipeline.md)；
> - DDL、RLS、凭证库：[05](05-data-platform.md)；
> - 事件契约与推荐：[06](06-recommendation-and-matching.md)；
> - 交互：[07](07-frontend-interaction.md)；
> - HC 登记、robots/ToS 判定规则（08 §4）、许可映射与安全细节：[08](08-compliance-security-privacy.md)；
> - 里程碑与 ADR：09（路线图）。
>
> **配图**：
> - [v2-01-architecture.svg](../../diagrams/v2-01-architecture.svg)：分层组件，标出平台侧/用户侧与四个数据域；
> - [v2-02-dataflow.svg](../../diagrams/v2-02-dataflow.svg)：收割 → 入库 → percolate → feed → 事件 → 学习的主数据流与合规边界。
>
> **证据口径**：事实断言引用 `docs/survey/` 下调研（2026-09-26 核验）。写法沿用[调研综合](../../survey/00-survey-synthesis.md)：`RT §10.6` 指检索路由调研 §10.6，链接只指向文件。
> - 调研已标 ⚠ 的，本文照样标 ⚠；
> - 调研未覆盖、由本文按常识补充的（主要是运维类组件的许可），一律标"⚠ 调研未覆盖"，实现期由许可扫描复核；
> - 本文自己的估算标"[估算]"，工程判断标"[判断]"。本文的 Python 代码块均为设计伪代码，`text` 代码块为时序与拓扑示意。
> - 对同批草案（01、05、06、07、08，2026-09-27）的引用写作"08 §4.3"等，指向该文档的章节。

---

## 0. 阅读指引

**编号约定（均为本文局部编号）**

| 前缀 | 含义 | 去向 |
|---|---|---|
| `AD-xx` | 本文的架构决策 | 需要 ADR 的见 §6.4，由 09 起草为 D-040 起的 proposed ADR |
| `INV-xx` | 数据流与执行位置的不变式 | 供 05、08 与验收引用 |
| `AC-V<m>.<n>` | 验收标准（正式编号） | 已由 09 统一改号（新旧对照见 [09](09-roadmap-and-milestones.md) 附录 A）；本文清单见附录 A |
| `FR/NFR` | 需求编号 | 本文不新编，由 01 登记 |
| `HC-xx` | 合规硬约束 | 沿用 CP §3.1 的编号，由 08 统一登记 |

**默认假设**（简报 §8）：

- Q1 非商业，`platform.commercial=false`；
- Q2 不面向中国大陆公众，`region=global`；
- Q3 不购买 OpenAlex、Crossref 付费档；
- Q4 robots 与文档化 API 冲突时从严。

凡依赖这些假设之处，正文标"默认假设"。

**术语**：严格使用简报 §5 的词表。

- 简报里有两种 Channel，按简报 R2-02 区分：
  - SourceSpec 的 `metadata` / `latest` / `fulltext` 写作 **SourceChannel（来源通道）**；
  - 用户保存的查询写作"**用户频道**（Channel）"。
- 本文新增的共享术语见 §7。

---

## 1. 功能说明

### 1.1 本文回答的问题

1. v2 由哪些组件构成？各自负责什么、不负责什么、在哪一侧执行（`exec_side`）、怎么扩缩？
2. 同一套代码怎样同时支撑 platform 与 personal 两种部署（B-02）？T1 怎样落在一台机器上（B-04）？何时、怎样演进到 T2？
3. 数据存放在哪里、怎样在组件之间流动？合规边界怎样**靠结构保证**，而不是靠调用方自觉？调研阶段多次"先请求、后读 robots"的偏差就是反例（综合 §1.5、SI-38）。
4. 前端与用户侧组件通过什么 API 与平台交互？包括资源、认证、限速、分页、版本与契约。
5. 任一依赖失败时系统怎样降级（P-09）？怎样观测、怎样验收？

### 1.2 需求到架构的映射

| 需求（简报 §1） | 架构承载 | 本文位置 |
|---|---|---|
| R1 自定义来源与支持名录 | Connector Workers（平台侧来源通道）；用户侧宿主（`fulltext` 通道）；Policy Engine；名录状态到运行时行为的映射；`/sources` 名录 API | §2.3.7、§2.3.14、§2.4、§2.8 |
| R2 查询（含最新、筛选、多来源、组合查询）与多用户库 | Router 与联邦执行器（LATEST 只读本地）；Index Maintainers；PG 四域；`/search`、`/channels`（频道间并交差）、`/me/search-history` | §2.3.3、§2.6、§2.7(d)、§2.8.2 |
| R3 推荐、反馈与双向匹配 | Rec Service；Feed Assembler；Percolator；事件接入；evt 域 | §2.3.4–2.3.6、§2.3.11、§2.7(a)–(c) |
| R4 卡片前端 | PWA；Feed API；SSE；性能预算 | §2.4、§2.8、§2.11 |
| R5 开源与初创 | 技术栈与许可表（综合 §4.4） | §2.10 |
| 横切：合规、隐私、安全 | Egress Gateway（四类出站路由）；`exec_side`；INV-01…11；架构参数；Notifier | §1.5、§2.3.13、§2.3.17、§2.14、§2.15 |

### 1.3 架构层面不做什么

- 不以平台出口代用户访问出版商（HC-03）。平台不持有可用的出版商会话，也不持有用户级凭证（HC-04）。
- 不做全文再分发，不提供公共全文上传（HC-16）。私有上传只进本人命名空间。
- 不引入独立图数据库。T1 不拆微服务，不建在线训练集群（简报 §6.2-4、§6.4-2）。
- LLM 不进交互热路径（P-07）。
- 不做 Google Scholar 自动化，不做任何挑战求解或规避（HC-26）。

### 1.4 关键架构决策

| 编号 | 决策 | 依据 | 主要备选 |
|---|---|---|---|
| AD-01 | **Egress Gateway（出站网关）是平台唯一的公网出口**，由网络隔离强制（简报 R2-08，另起草 ADR；例外只有 Edge 的入站与证书续期，见 INV-03）。03 的 PoliteHttp 是网关内部使用的客户端库，08 的"出站网关"即本组件。其余容器所在网络没有公网路由。Egress 是**应用层网关**：调用方经内网 RPC 提交结构化请求，由 Egress 自己向上游发起 TLS 连接，因此能按路径做 robots 与策略判定、读取限流头、缓存与逐请求审计；它不是 CONNECT 隧道代理（隧道代理看不到 HTTPS 路径与响应头）。出站分四类路由：学术上游、模型提供方、身份提供方、通知。Egress 同时是 04 稳定性算法与 Policy Engine（规则 08 §4，实现 03）的执行宿主 | P-04、HC-10、HC-29、SI-32/37/38；AG §3-5、§3-15 | 各进程内嵌限速库，令牌桶状态放在 PG 或 Valkey（§8-2） |
| AD-02 | **`exec_side` 双宿主**：`platform` 通道只在平台工作者执行；`user` 通道只在扩展或 pc-agent 中执行（personal 部署运行在用户本机时，由同机的 pc-agent 执行）。平台服务镜像（含 personal 部署的服务端容器）不打包用户级 AuthProvider | P-03、HC-03/04；CP §2.3.4 | 服务端代取（与 HC-03 冲突，排除） |
| AD-03 | **在线路径优先读预计算批块**：下一批块由近线预计算（当前批块消费约 70% 时触发，06 §7.7），请求期只做轻重排与 Hydrate。没有可用预计算时，在 API 进程内跑完整候选管线（06 §2.2 的热路径预算合计约 235 ms）；再失败依次降级为快路径（FeedInbox 加缓存候选池）与非个性化批块 | 简报 §3 性能预算；P-07、P-09；06 §2.2、§7.7 | 只允许读预构建结果（首个批块与会话态刚变化时拿不到新结果）；只在请求期跑完整管线（每次都要付全部召回成本，尾延迟无缓冲）[判断] |
| AD-04 | **下发记录由服务端生成 `impression_id`**，训练用反馈必须绑定它 | 简报 §5 Impression；SI-45；RO §3.1-9 | 只以客户端曝光事件为准（无法区分"没下发"和"没看见"） |
| AD-05 | **模块化单体加工作者池**：API 进程内含 Router 与 Feed 的在线路径，重计算下沉到推理服务与队列 | B-05；RT §11 | 按组件拆微服务（T1 运维成本过高） |
| AD-06 | **事务性 outbox + PG 原生队列**（procrastinate 首选，pgqueuer 备选）。worker 与 relay 直连 PG 使用 LISTEN；relay 以 `SKIP LOCKED` 领取，可多实例并行，不是单点；消费者必须幂等 | SI-34；RT §10.6 | Celery/Redis（多一个 broker）；arq（维护模式，排除） |
| AD-07 | **PG 四域，每个组件一个最小权限角色**。单向流靠授权结构保证：能读 `usr` 的角色都不能写 `corpus` | P-02、HC-01；RT §10.3 | 应用层自律（不可审计） |
| AD-08 | **对象存储分两类前缀**：`oa-shared/`（许可白名单，可内容寻址）；`private/{user_id}/`（随机键、不跨用户去重、注销即删） | HC-02、HC-05、HC-16、HC-20 | 私有资产也做内容寻址去重（违反 HC-02） |
| AD-09 | **API 形态**：REST + SSE，OpenAPI 3.1 为契约，URI 主版本 `/api/v2`，RFC 9457 错误体，游标分页；扩展与 pc-agent 走 OAuth 2.1 PKCE | B-05；简报 §6.5-6 | GraphQL（契约与缓存更复杂，收益不明） |
| AD-10 | **用户侧取回方式按 08 的规则选择**：`oa_link` > `tdm_api` > `user_fetch` > `open_in_tab`。`user_fetch` 须满足 08 的 R16（ToS 不禁止自动化、robots 允许、不在冷却期、用户已授权该域），否则退回可见标签页 `open_in_tab`，由用户本人阅读或保存（人在回路，沿用 D-006） | 08 §4 R16、§5.1；CP §2.3.4 推论、DI-02；LQ-07、LQ-19 | 一律后台直取（ToS 禁止自动化的站点会越界，机构风控风险高，见 RK-01） |
| AD-11 | **`platform.commercial` 与 `region` 是架构参数**，由策略引擎统一消费。`region` 按部署单元固定，不在运行期切换 | CP DI-07、DI-09；HC-21/22/23 | 按功能散落 if 判断（不可审计） |
| AD-12 | **联邦是稀缺资源**：设每用户日配额和全局美元预算，只在真正 fan-out 时扣减。联邦未命中的查询回灌为 WatchKey 候选，形成 P-01 的学习闭环；候选只存规范化下推查询与"不同用户数"，不存用户标识，达到 `k_cf` 个不同用户或经管理员复核后才纳入（§2.3.7；简报 R2-04、R2-19） | AG §3-16；RT §2.2；HC-01、HC-30 | 联邦不设限（OpenAlex 免费额度每日 $1，很快耗尽，§2.11） |
| AD-13 | **私有增益（T3）默认只在用户侧执行**。平台的私有增益道默认关闭，待 LQ-06 与出版商白名单明确后再议 | P-07、HC-11；PU §2.6.5、§3-1 | 平台代生成私有派生（受 Elsevier、IEEE 条款约束，⚠ LQ-06） |

### 1.5 数据流与执行位置不变式

| 编号 | 不变式 | 结构性保证 | 验收 |
|---|---|---|---|
| INV-01 | 从 `usr` 到 `corpus` 没有写路径，包括索引、嵌入、TL;DR、特征与日志样本（HC-01） | DB 授权矩阵：没有角色同时拥有"读 usr"与"写 corpus"；私有派生只写 `usr` | AC-V3.7 |
| INV-02 | `exec_side=user` 的来源通道不在平台出口执行（HC-03） | 平台镜像不含用户级 AuthProvider 与凭证库；Egress 按 registry 的 URL 模式自行推出来源通道，命中 `exec_side=user` 即拒绝，不采信调用方声明；分派器拒绝放置 | AC-V0.17；08 AC-0.13 |
| INV-03 | 平台所有公网出站都经 Egress（P-04、HC-10），包括 OIDC 令牌交换、ORCID/Zotero 导入、邮件与 Web Push、告警。只有两处例外：Edge 接收入站 443，并只可连 ACME 证书端点续期；异机备份采用拉取模式，由备份主机经 VPN 或 SSH 拉取，平台不主动外连（§2.6.5） | compose 的 `front` 与 `back` 网络都设为 `internal`，只有 Egress 与 Edge 挂非 `internal` 网络；Edge 的出站由宿主机防火墙（Docker 的 `DOCKER-USER` 链）限定到 ACME 端点 [判断]（§2.5.3） | AC-V0.15 |
| INV-04 | 私有数据不发往第三方 LLM 或嵌入 API（P-07）。查询文本、画像、笔记属个人数据（`data_class=personal`，08 §9.1），只能用自托管模型。唯一例外（简报 R2-27）：personal 部署且 `host_is_user_device=true` 时，用户可显式同意用第三方 API 处理本人私有全文（08 §9.5） | Egress 的 `model_provider` 路由按 `data_class` 拦截；调用方共享同一路由库（08 §9.4），自托管端点在 back 网络内直连推理服务 | AC-V1.14 |
| INV-05 | 训练用反馈必须绑定本人的下发记录（SI-45） | 事件接入时做绑定校验；训练视图只取已绑定事件 | AC-V3.9 |
| INV-06 | `open_fulltext` 与私有域信号不进入公共热度、社会证明和他人的解释（简报 §2、HC-02） | 聚合作业的输入白名单；k 匿名闸（k 值由 06 定） | AC-V4.25 |
| INV-07 | 用户级凭证不离开用户侧，服务端没有解密能力（HC-04） | 凭证库只打包在用户侧；多设备同步只传端到端密文（可选功能） | AC-V0.17、AC-V3.17 |
| INV-08 | 私有资产不跨用户去重（HC-02） | platform 部署中私有 PDF 默认只存用户设备；可选同步时只上传端到端密文。每个文件用随机密钥加密，服务端只存密文、大小与时间，不存明文哈希（08 §5.4），同一 PDF 在不同用户处的密文也不同 | AC-V3.7 |
| INV-09 | 协同类理由与社会证明满足"至少 k 个不同用户"（简报 §6.4-6；HC-30） | 由聚合作业（`pc_sys_aggregator`，只写 `evt.agg_*`）强制执行；参数按简报 R2-04 统一为 `k_cf`（协同信号入模）/ `k_reason`（协同类解释）/ `k_show`（公开计数与社会证明），初值见 06 §14.2：5 / 5（cohort ≥30）/ 10 ⚠，R0 下限 `k_show` ≥5 | 06 的 AC；08 AC-0.17 |
| INV-10 | 每一次出站尝试都在 FetchLog 中恰有一行，包括被策略或 robots 拒绝、重试、挑战、超时与预算耗尽；对任一主机的首个请求之前，必有有效的 robots 判定记录（HC-28、HC-29） | Egress 在请求入口开账、在 `finally` 中落账；robots 判定写入同一行的 `gate_decision` | AC-V0.18 |
| INV-11 | 卡片流、频道预览与 LATEST 查询不触发任何远端调用（P-01；01 FR-36） | Router 对这三类请求不进入联邦分支；Egress 审计按调用来源统计 | AC-V2.14 |

---

## 2. 实现方案

### 2.1 分层视图与原则落地

```text
L0 用户侧     PWA │ Companion Extension │ pc-agent（本机）   ← exec_side=user：用户会话·用户 key·用户网络出口
──────────────────────── HTTPS（意图 / 状态 / 事件；不含凭证与全文字节）────────────────────────
L1 接入层     Edge（TLS·静态资源·安全头）→ API（REST+SSE·会话/PKCE·限速·预算·RLS 上下文）│ Admin API（内网）
L2 在线服务   Router & 联邦执行器 │ Rec Service（Candidate Pipeline）│ Feed Assembler │ 推理服务
L3 近线/批处理 Harvest Scheduler │ Connector Workers │ Ingestor │ Enrich │ Index Maintainers │ Percolator │ Rec 近线与夜间 │ Notifier
L4 治理       Policy & Rights Engine │ Drift Probes │ Admin Console │ Observability
L5 出站       Egress Gateway（唯一公网出口；应用层网关）──► L1/L2 来源 · Bulk 快照 · LLM/嵌入 API · 身份提供方 · 通知
L6 数据       PostgreSQL 18 {corpus │ usr(RLS) │ evt(只追加) │ ops} · 对象存储 {oa-shared │ private/{uid} │ …} · Valkey(可选)
```

- **依赖方向**：依赖只向下。
- **出站**：L2、L3、L4 访问公网只能经 L5（INV-03）。
- **数据访问**：所有组件以最小权限角色访问 L6（AD-07）。
- **用户侧**：用户侧组件只与 L1 交互，另外直连出版商（用户本人的会话与网络出口）。

**简报原则在架构中的落点**

| 原则 | 架构机制 | 所在组件 | 验收 |
|---|---|---|---|
| P-01 先收割、后联邦 | 卡片流、用户频道与"最新"只读本地（INV-11）；Router 本地优先，覆盖不足才联邦；联邦未命中回灌 WatchKey 候选 | Router、Feed Assembler、Harvest Scheduler | AC-V2.46、AC-V2.32、AC-V2.36、AC-V2.14 |
| P-02 三域、`display_scope`、派生继承最严 | PG 四域加授权单向；Hydrate 按 `display_scope`；私有派生只写 `usr`；私有增益道默认关闭 | PG、Policy & Rights Engine、Enrich | AC-V3.7、AC-V3.5 |
| P-03 用户侧取回 | `exec_side` 双宿主；签名 RetrievalIntent；平台镜像剔除用户级凭证模块 | 扩展、pc-agent、Egress、策略引擎 | AC-V0.17、AC-V3.17 |
| P-04 全局礼貌 | 唯一出口；桶键五元组；响应头驱动的 AIMD（上限为书面限额）；不对同一主机对冲；挑战即停 | Egress Gateway | AC-V0.16、AC-V1.5、AC-V1.1、AC-V1.2、AC-V1.3、AC-V0.18 |
| P-05 最严者为准 | 五通道取最严（判定表 08 §4.2）；`needs_confirmation` 进复核队列 | 策略引擎、Admin Console | 03 的 AC；08 AC-V1.6、AC-0.14；本文 AC-V1.6 |
| P-06 可解释、可控、可导出 | 理由码贯穿召回到下发；非个性化模式；兴趣标签 API；导出与删除作业 | Rec、Feed、API | AC-V4.1、06/07 的 AC |
| P-07 LLM 不进热路径 | LLM 只出现在 `enrich_llm` 批处理（共享输入）、异步解析建议、懒生成解释与画像摘要中；后三者含个人数据，只用自托管模型；Egress 按数据类别与地区路由 | Enrich、Router、Rec、Egress | AC-V1.14 |
| P-08 评测先行 | 下发记录从第一天起记录位置、候选源、打分分量、实验桶与倾向分；Deck 与检索结果都铸造 `impression_id` | Feed Assembler、Router、evt | AC-V3.9 |
| P-09 可降级 | 降级矩阵（§2.12）；每项关键能力至少 2 级同能力替补链（01 NFR-13；RT §3.5.5）；兜底为"仅本地"或"非个性化" | 全部 | AC-V4.1、AC-V2.32 |

### 2.2 组件总表

| 编号 | 组件 | 层 | exec_side | 形态 | 扩缩方式 | 算法/契约定义方 |
|---|---|---|---|---|---|---|
| U1 | PWA 前端 | L0 | user | 浏览器应用 | 无状态静态资源 | 07 |
| U2 | Companion Extension | L0 | user | 浏览器扩展（MV3） | 每用户一份 | 08（安全）、07（交互） |
| U3 | pc-agent（本机代理） | L0 | user | 本机进程，独立安装包（复用 v1 代码，`[agent]`/`[auth]` extras）；personal 部署的用户侧能力也由它提供 | 每用户一份 | 03（Connector）、05（凭证库）、08（取回规则） |
| P1 | Edge 反向代理 | L1 | platform | 独立进程 | 单实例起步，可多实例 | 02 |
| P2 | API | L1 | platform | FastAPI 进程组 | 无状态水平扩展 | 02（API 面） |
| P3 | Router 与联邦执行器 | L2 | platform | API 进程内模块 | 随 API 扩展 | 04 |
| P4 | Rec Service | L2/L3 | platform | 库（在线管线与快路径，API 进程内）+ 工作者池（近线与夜间）。06 §2.1 的 rec-api 即 API 进程内的 Feed/Rec 模块，rec-worker 即 `worker-rec` | 按队列并发 | 06 |
| P5 | Feed Assembler | L2 | platform | API 进程内模块 + 近线作业 | 随 API 与队列扩展 | 06、07 |
| P6 | Harvest Scheduler | L3 | platform | 单例（PG advisory lock 选主） | 主备 | 04（WatchKey 编译与新鲜度调度算法）；本组件执行，03 的 connector 消费（简报 R2-34） |
| P7 | Connector Workers | L3 | platform | procrastinate 工作者 | 按队列并发；上游礼貌上限由 Egress 兜底 | 03 |
| P8 | Ingestor | L3 | platform | procrastinate 工作者 | 按队列并发；`corpus` 写入单一角色 | 03、05 |
| P9 | Enrich Workers | L3 | platform | procrastinate 工作者（分道） | 按道独立并发；可选 GPU | 03（PU 结论） |
| P10 | Index Maintainers | L3 | platform | 周期作业 | 夜间窗口 | 04、05 |
| P11 | Percolator | L3 | platform | procrastinate 工作者（批） | 批大小与并发 | 04（频道硬命中）；兴趣反向推送是 P4 的夜间作业（06 §11.3） |
| P12 | 推理服务 | L2 | platform | 模型服务进程 | CPU 副本（T1 默认不配 GPU，简报 R2-45）；GPU 可选 | 04、06（模型选型见 Q7） |
| P13 | Egress Gateway | L5 | platform | 单例服务（T1） | T2 按来源分片，保持单一出口身份 | 02（路由与接口）、04（稳定性）、08（判定规则） |
| P14 | Policy & Rights Engine，Drift Probes | L4 | platform（策略包下发到用户侧执行） | 库 + 快照表 + 周期作业 | 随调用方 | 08（判定规则与权利映射）、03（引擎实现与 SourceSpec 字段） |
| P15 | Admin Console | L4 | platform | 管理 SPA + `api-admin` 实例 | 单实例 | 02 |
| P16 | Observability | L4 | platform | OTel SDK + Collector + 存储 | 按量 | 02 |
| P17 | Notifier（通知出口） | L3 | platform | procrastinate 工作者（`notify` 队列） | 单实例起步 | 02（通道）、06（digest 内容）、08（隐私与留存） |
| D1–D3 | PostgreSQL 18、对象存储、Valkey（可选） | L6 | platform | 数据服务 | 纵向扩展为主，T2 加副本或外置 | 05 |

### 2.3 平台侧组件详述

各组件的 `exec_side` 与扩缩方式汇总在 §2.2。本节逐个说明职责与边界（不做什么），扩缩只在有额外约束时补充。用户侧组件见 §2.4。

#### 2.3.1 P1 Edge 反向代理

- **职责**：
  - TLS 终止，HTTP/2；
  - 托管 PWA 静态资源；
  - 安全响应头（CSP、HSTS、`frame-ancestors`）；
  - 匿名请求的粗粒度按 IP 限流；
  - 关闭 SSE 路径的响应缓冲。
- **不做**：鉴权决策、业务限速、任何上游访问。
- **扩缩**：T1 单实例；T2 可多实例，前置负载均衡。
- **选型**：Caddy（Apache-2.0，⚠ 调研未覆盖）或 nginx，二选一，实现期定。

#### 2.3.2 P2 API（FastAPI）

- **职责**：
  - REST 与 SSE 接入；
  - 会话认证与 OAuth PKCE 令牌校验；
  - 按用户限速与联邦预算记账；
  - 请求校验（Pydantic v2）；
  - 在事务内以 `SET LOCAL app.user_id` 建立 RLS 上下文；
  - 输出 OpenAPI 3.1；
  - 宿主 P3 Router 与 P5 Feed Assembler 的在线路径。
- **不做**：
  - 不直接访问公网（INV-03）：OIDC 授权码换令牌、JWKS 拉取、ORCID 与 Zotero 导入都经 Egress 的身份提供方路由；
  - 不在请求路径同步调用 LLM（P-07）；
  - 不执行重计算：嵌入与重排交给 P12，批量打分交给 P4 近线；
  - 不持有部署级上游密钥（由 P13 持有）。
- **扩缩**：
  - 无状态，水平扩展；
  - 数据库连接走 PgBouncer 事务池（可选）。RT §10.3 核验：事务池不支持会话级 SET 与 LISTEN；`SET LOCAL` 能否与事务池配合仍 ⚠ 待实测。
  - API 不 LISTEN；需要订阅的流式场景见 §2.9.3。
- **Admin API**：
  - 同一镜像以 `ROLE=admin` 启动 `api-admin` 实例；
  - 只绑定内网端口，经 VPN 或 SSH 隧道访问；
  - 强制 MFA，所有写操作记审计日志（§2.3.15）。

#### 2.3.3 P3 Router 与联邦执行器

- **职责**（算法由 04 定义，本文只定位置与边界）：
  1. 查询解析：规则快路径 → 实体链接 → 可编辑筛选条。LLM 受约束解析是**异步建议**，不阻塞首屏（P-07），见 §2.7(d)。查询文本属个人数据（08 §9.1），LLM 解析只路由到自托管模型；未部署自托管模型时不提供此建议（F16）。
  2. TSRG 选源：求主题后验，再做预算贪心（简报 §6.2-2；近似界以 04 §19-1 为准，R2-38）；路由不使用个人画像，只取共享层、个人谓词与个性化挂点之前的召回（R2-40；04 §6.2）。
  3. 本地混合检索：BM25 与 `halfvec` HNSW 并行召回，各列表先按 `cluster_id` 折叠，再做残差过滤、RRF 融合与 cross-encoder 重排（SI-26；顺序以 04 §8.1 为准）。重排 top-100 是上限：纯 CPU 的 T1 从小模型 int8、top-50 起步，超预算先发 RRF 结果，重排结果经流式 `upgrade` 补发（简报 R2-39）。
  4. 远端调用只在本地覆盖不足时发生：SEARCH、SIMILAR（及 04 提议、待裁定的 EXPAND）经 TSRG 选源做带截止时间的并行 fan-out；LOOKUP 本地未命中时按同能力替补链逐级补查，不做选源（04 §8.4）；LATEST、频道预览与卡片流不联邦（INV-11）。每个请求都经 P13 的**交互道**、以 `ON_DEMAND` 请求类发出；做健全放宽与本地残差过滤，按 `cluster_id` 折叠。
  5. 流式返回：本地结果先到，远端结果逐源补齐（传输见 §2.7(d)、§2.8.7）。结果条目与卡片一样铸造 `impression_id`（`surface=search`），检索页上的收藏等反馈因此可绑定（SI-45）。
  6. 规范化查询兼作缓存键与复现凭据（SI-24）。
- **不做**：
  - 不使用用户级凭证做远端检索。需要用户 key 的数据库（Scopus 等）只能作用户侧连接器，结果只进 `usr`（AG §3-13；v2.0 不做）；
  - 不对同一主机发对冲请求（SI-32）。
- **扩缩**：作为 API 进程内的 async 模块随 API 扩展。CPU 密集的查询嵌入与重排走 P12。
- **写回**：联邦得到的远端记录按来源的缓存策略（03 SourceSpec 的 `storage_policy.cache_mode ∈ {store_shared, ttl_only, display_only}`）决定去向：
  - 可入库的，经 P8 走正常入库路径（元数据）；
  - S2 这类只许"访问与展示"的来源（其 API 许可只授予 access and display，禁止再打包与分发，OSS §3-7），只做 TTL 缓存或只展示（RO §4-10；⚠ LQ-08）。

#### 2.3.4 P4 Rec Service（Candidate Pipeline）

- **职责**（算法与 ValueModel 由 06 定义）：
  - 按六类组件执行候选管线：Source、Hydrator、Filter、Scorer、Selector、SideEffect（SI-41）；
  - 多路召回，每条候选带来源归因；
  - R0 阶段在共享论文表示上训练每用户 LR（SI-39）；
  - ValueModel `Σ V_a·P̂(a)` 的版本化配置由 Admin Console 管理；
  - 做 DPP/MMR、作者衰减与探索槽；输出理由码与打分分量。
- **运行形态**（与 06 §2.2 的三条时间道一一对应）：
  1. **在线**（API 进程内的库，即 06 的 rec-api）：
     - 首选读预计算批块，只做轻重排；
     - 没有预计算时跑完整候选管线（Query Hydration → 并行召回 → Hydrator → Filter → Scorer → Selector，06 §2.2 预算合计约 235 ms）；
     - 在线管线超时或失败时走**快路径**（预算 150 ms [判断]）：只基于 FeedInbox 与缓存候选池（06 §7.7，TTL 30 分钟）打分，不做 ANN 召回。
  2. **近线**（`worker-rec`，即 06 的 rec-worker）：
     - `rec_update`（简报 R2-07 统一的近线队列名）：逐事件增量更新标签、画像与每用户 LR（按用户加锁、去抖约 1 秒，06 §8.2），目标"事件到达 → 生效"p95 ≤2 秒（01 NFR-9）；
     - `deck_build`：预计算下一批块。
  3. **夜间**：多质心重聚类、反向推送规划（层②的日预算与资格集合曝光下限分配，06 §11.3，§2.3.6）、R1 的 GBDT 与协同召回训练。
- **数据库角色**（以 05 §4.1 为准）：按用户执行的作业（`rec_update`、`deck_build`、画像更新）以 `pc_app` 在该用户的 RLS 上下文中运行，不跨用户读取；反向推送规划以 `pc_sys_percolator` 只读所需列、只写 FeedInbox；R1 起的全局模型只读 `pc_sys_aggregator` 产出的假名化训练抽取物（05 §3.3.5）。
- **不做**：
  - 滑动路径上不同步调用 LLM（P-07）；画像摘要、每日 top-K 重排与懒生成解释含个人数据（`data_class=personal`），只路由到自托管模型，未部署时关闭（08 §9.4）；
  - 不读取任何私有全文派生来构建共享特征（INV-01）；
  - 不把 `open_fulltext` 当公共信号（INV-06）。
- **扩缩**：
  - 近线按队列并发扩展；每用户以 procrastinate 的 lock 与 queueing lock 串行化、合并重复作业（⚠ 实现期核对 API）；
  - 夜间作业在 `worker-rec` 中按窗口运行，不与交互路径争用（§2.9.2 舱壁）。

#### 2.3.5 P5 Feed Assembler

- **职责**：
  - 把候选装配为**有限批次**（Deck/Batch）：默认 25 张，可选 15 / 25 / 35（简报 R2-42；⚠ 待 Demo 验证），按批块下发（06 §7.7：25 张分为 10/10/5）；禁止用净负分候选补满批次，候选不足时批次提前结束；"再来 10 篇"只由用户显式触发，每日总上限 60 ⚠；
  - 放置探索槽；
  - Hydrate 卡片字段：经展示闸（08 §3.9，API 出网的唯一序列化点）按 `display_scope` 与许可逐字段取值，按学科模板渲染（PU §3-23；映射由 08 定）；AI 生成字段附机器可读的 `ai_label`（08 §9.3，HC-11d）；
  - 生成 why-this 理由码的模板文本；
  - 写下发记录（SideEffect）：每卡一行写入 `evt.impression`，含 `impression_id`（服务端 UUIDv7）、位置、候选源、打分分量、实验桶、倾向分（AD-04；05 §3.3.2）；同一事务更新 `usr.seen_segment` 的 served 段与批次进度；
  - 在非个性化模式下，改用按时间或来源排序的装配器（HC-13）。
- **不做**：
  - 不计算"用你的权限"这一 OA 状态。该状态只按本人私有数据在用户侧计算：由扩展或 pc-agent 读取端到端加密凭证库中的订阅配置与本人回执后算出，PWA 经 `pc.entitlement.query` 取结果、只在内存中使用（08 §5.1.6、§5.3；07 §8.6、§15.7；CP DI-04、HC-02），平台只返回三种共享可判定的状态：
    - 开放可读（许可可共享）；
    - 开放外链；
    - 需订阅。
  - 分拣卡上不下发社交计数（SI-58）。
- **扩缩**：在线路径在 API 进程内；批块预计算在近线作业中。

#### 2.3.6 P11 Percolator

论文→读者的反向路由分两个时间尺度，与 06 §11.3 的分工一致：

- **近线：频道硬命中（本组件，算法由 04 定义）**：
  - 以批处理方式消费出箱主题 `corpus.change`（简报 R2-07；载荷见 03 §10.7），按 `work_search.index_seq` 水位只取 index 段已完成的作品（04 §12.1）；输入包括新 Work，以及新增 Version 或匹配字段发生变更的已有 Work（简报 R2-35）；
  - 用户频道匹配：对 Query AST 按主题、词项、venue、作者建倒排；
  - 命中即写 `usr.feed_inbox`（`origin=channel`），不占软推送预算，受频道护栏约束（沿用 v1 `max_new_per_run` 的熔断语义）；发出 `deck.stale`。
- **夜间：兴趣反向推送（Rec 的反向推送规划器，算法与参数由 06 §11.3 定义，在 `worker-rec` 中运行）**：
  - TSRG 节点倒排加用户质心批量点积，取候选读者；
  - 在"每用户日预算 + 资格集合的曝光下限"约束下对当日全部新论文一次性分配（贪心；硬配额用最小费用流，SI-48）。下限只对资格集合生效，并受全局预算约束（≤5% 期望曝光），其余新作品靠分级曝光的探索槽（简报 R2-41）。这一步需要看到当日全部边才能排序，放在逐批的近线里做会让先到的论文抢占预算，因此是夜间作业 [判断]。
- **读权限**：两者都以 `pc_sys_percolator` 运行：只读频道 AST、用户向量、兴趣节点权重、屏蔽规则中的所需列；夜间规划器另读边权所需的 `user_model.weights`、`action_stat`、`user_feature` 的所需列，并写自己的指派账本以免重复指派（06 §11.3 AL-17；05 §3.2.5、§4.1）；对 FeedInbox 只有 INSERT、没有 SELECT（05 §3.2.5、§4.4）。个性化关闭的用户不参与画像匹配（05 `uv_percolate` 策略）。不读私有资产，也不读凭证。
- **扩缩**：按批大小与并发扩展。
  - 规模估算：1 万用户 × 5 个质心 × 3 万篇 × 256 维，约 0.8 TFLOP [估算]，属夜间规划器。CPU BLAS 下为秒级，与 SR §3.1-14 的"秒到分钟"量级一致（06 §19.3 按 2.5 万篇估为 3.2×10¹¹ 次乘加）。
  - 订阅数达到 10⁵ 量级时，频道倒排的性能未知（RT §13-11）。T2 再评估外置 percolate。

#### 2.3.7 P6 Harvest Scheduler 与 P7 Connector Workers

- **P6 Harvest Scheduler（单例）**：
  - WatchKey 编译、对账与引用计数（SI-31；简报 R2-34：算法由 04 定义，本组件执行，03 的 connector 消费）：频道变更时，API 在本人事务内调用 04 的编译器把频道 AST 编译为下推查询，写入本人的 `usr.channel_watch`；调度器以 `pc_sys_scheduler` 按 `channel_watch` 重算 `ops.watch_key` 的引用计数。`ops` 侧只存下推查询与计数，不存用户标识（05 §3.4）。由私有文献库派生的细粒度键须 ≥`k_cf` 个不同用户才建平台键，未达门槛只做该用户的按需查询（简报 R2-19；04 §11.1）；
  - 日历型来源按发布窗口轮询，连续型来源按 Gamma-Poisson λ 做注水分配（04 定义）；
  - 按来源分配礼貌预算，调度 bulk 快照导入（`bulk_snapshot` 族：OpenAlex 季度快照、DROPS，SI-15）。PubMed baseline 所在的 ftp.ncbi 与 Europe PMC 的 ftp.ebi 的 robots 均为 `Disallow: /`（AG §0 第 7 条核验补充），属 `needs_confirmation`：书面确认之前不导入，Egress 对其后台批量请求一律拒绝（HC-31；08 §4.7；默认假设 Q4；简报 R2-13）。
  - 联邦未命中的查询以"候选 WatchKey"形式记入 `ops`：只存规范化下推查询与不同用户数，不存用户标识；达到 `k_cf` 个不同用户，或管理员在不见用户身份的前提下复核通过，才纳入收割（AD-12）。
  - 选主用 PG session 级 advisory lock，因此需要直连 PG：PgBouncer 事务池不支持会话级 advisory lock（RT §10.3）。
- **P7 Connector Workers**：
  - 执行 `exec_side=platform` 的来源通道，覆盖八个 Connector 家族：`aggregator_api`、`oai_pmh`、`feed`、`crossref_delegated`、`bulk_snapshot`（快照导入，简报 R2-11）、`platform_family`（仅元数据）、`site_special`、`v1_bridge`（`official_tdm_api` 只在用户侧执行）；
  - 产出 RawRecord 批次；
  - 增量语义复用 v1 watermark：先推进、后提交，重叠窗口加标识符去重（§6.2）。
  - 所有 HTTP 调用经 P13 的**收割道**、以 `BACKGROUND_BATCH` 请求类发出。连接器不管限速、重试与 sleep，这一点沿用 v1 D-002/design/02 §3 的"adapter 永不自己 sleep/重试"。
  - bulk 快照走 Egress 的流式模式：边下载边写入 `snapshots/`，支持断点续传，不进 TTL 缓存，同样经白名单、策略与 FetchLog（§2.3.13）。
  - `v1_bridge` 包装的 v1 adapter 是同步接口（v1 `HttpClient` 为同步客户端），在 procrastinate 同步任务的线程池中运行，出站经注入的 Egress 客户端（§6.2）。
- **不做**：不执行 `exec_side=user` 通道（INV-02）；不做全文后台预取（简报 §6.1-6）。

#### 2.3.8 P8 Ingestor（normalize + identify）

- **职责**：
  1. normalize：标识符规范化复用 v1 `ids.py`；
  2. 按字段标注权利：`abstract_source`、`abstract_rights`、`license_code`、`display_scope`，调用 P14 的权利引擎（HC-07）；
  3. identify：标识符图 union-find 物化 `cluster_id`，保留可回滚的合并日志；MinHash-LSH 加 Splink 产出候审对，进入 Admin Console 的去重复核队列（SI-29）。
  4. 以 `pc_ingest` 角色单写 `corpus`，并在同一事务写 outbox，主题为 `corpus.change`（简报 R2-07；载荷见 03 §10.7、05 §3.1.2）。
- **不做**：
  - 不接收任何来自 `usr` 的数据（INV-01）；
  - 弱信号不自动合并（D-007）；
  - WP 与其发表版只建 `preprint_of` 边。
- **扩缩**：按队列并发。同一 `cluster` 的合并以行锁串行。

#### 2.3.9 P9 Enrich Workers

enrich 分道运行，每道独立并发，互不饿死：

| 道（队列） | 内容 | 输入范围 | 输出 |
|---|---|---|---|
| `enrich_meta` | 按出版方路由的摘要补齐链；主题标注：本地分类器以 OpenAlex topic 质心为基，约 12% 无 topic 的 work 用嵌入补标，不依赖已 deprecated 的 `/text`（简报 §6.6）；引文边 | 共享元数据 | `corpus` 字段与引文 |
| `enrich_embed` | 向量化，版本化并支持双写（SR §3.1-5） | 标题与摘要：A 类照常；B 类按简报 R2-21 默认纳入（不展示），以 `input_rights_max` 记血缘、可逆重建，开关 `policy.index_b_abstracts`，LQ-02 结论为否时关闭并重建；C 类永不进入；来源带 Content-Signal `ai-input=no` 的不作共享嵌入（08 §4.2 R10，映射待 LQ-17） | `corpus` 向量表 |
| `enrich_llm` | T1 批量 A 包（TL;DR、中文标题、关键词）；T2 按需翻译与要点；三道闸（SI-59/61） | **只取可共享来源**（HC-11a）；在 LQ-05 有结论前不取 B 类摘要（简报 P-02）；输入前查 Policy Engine 的 AI 用途判定：Content-Signal `ai-input`、TDMRep、robots 中具名 AI 规则有保留的不输入，IEEE 与 Elsevier API 内容不输入（HC-11b/c；08 §9.1） | 共享 `card_field`，带 `ai_label`（HC-11d） |
| `enrich_fulltext` | 可共享 OA 全文解析（GROBID，consolidation 硬编码为 0，沿用 D-033）；选图须新增 `teiCoordinates=figure`（ADR 候选 13） | 仅许可闸放行的 OA 全文（HC-05/09）。arXiv 的 e-print（PDF、源文件、抽取的图）除 CC 许可者外不下载入库、不做共享派生（HC-06）。OA 仓储主机须先经 robots 与 SSRF 检查，自动登记为 `oa_host` 类来源并分配保守限速桶后才可访问（08 §10.3）；受 `features.oa_shared_cache` 门控 | `oa-shared/` 与 `corpus` |
| `enrich_private`（**默认关闭**） | 私有 T3 派生 | 本人私有资产 | 只写 `usr`（AD-13） |

- **LLM 调用**：经 P13 的 `model_provider` 路由，按地区与数据类别选提供方（§2.15）。`enrich_llm` 只处理开放内容，属简报 R2-45 允许使用第三方 API 的论文侧预处理（零保留条款、非中国境内路由）。按 PU §2.6.4，日增 3 万篇的最大场景月成本约 $26–806（Sonnet 5 计入新分词器后上限约 $1,050，⚠ 推断）；默认配置须落在 01 NFR-19 的成本目标内（§2.11）。
- **不做**：不对任何私有内容调用第三方 LLM（INV-04；唯一例外是简报 R2-27 的 personal 本机部署经用户同意处理本人私有全文）；不做全文后台预取。

#### 2.3.10 P10 Index Maintainers

- **职责**（索引设计由 04、05 定义）：
  - 维护 BM25（默认 pg_textsearch）与 `halfvec` HNSW；
  - 换模型时新旧并存双写，建好新索引后切换读别名；
  - 维护 facet 与主题数组；
  - 夜间把图导出为 CSR，用 rustworkx 做 PageRank、共被引等批算并回写（SI-28）；
  - 每周重算 `route_stat`，默认离线跑免费快照；用 OpenAlex group_by（每周约 9,000 次调用、约 $0.90，RT §3.5.1）时须先在美元账本中预留，否则会挤占当日联邦预算（免费额度每日 $1，AG §3-16）；
  - 维护 evt 月分区，并把冷数据归档为 Parquet；
  - 安排 VACUUM/ANALYZE。
- **扩缩**：夜间窗口运行，窗口不够即触发 T2 评估（RT §5.4）。

#### 2.3.11 事件接入（API 内模块）

`POST /events` 的接入逻辑放在 API 内，职责如下：

- 按 06 的事件契约与 `schema_version` 校验；
- 由 `event_id`（客户端生成的 UUIDv7，用于幂等去重）推出分区键 `event_ts`，超出分区安全窗口 [now−7 天, now+5 分钟] 的拒收（简报 R2-32；05 §3.3.4）；`impression_id` 由服务端 `uuidv7()` 生成（AD-04）；
- 做 `impression_id` 绑定校验（INV-05）：按 `(impression_id, user_id, work_id)` 在 `evt.impression` 中查找，UUIDv7 的时间戳用于定位分区；
- 以 `(event_id, event_ts)` 幂等写入 `evt.event`；
- `not_interested` 与 `block` 在同一事务中同步写入 `usr.mute_rule` / `usr.session_suppress`，保证"当次会话即生效"（简报 §6.4-3、R2-33）；撤销时按 `origin_event_id` 一并删除对应抑制；`block.target_type` 含 `source`；
- 写 outbox 并 `NOTIFY`，触发 `rec_update`。

不做：不在接入路径上训练或打分，这些由 `rec_update` 异步完成；不接受客户端自填的 `user_id`。扩缩随 API 水平扩展。传输细节见 §2.9.6。

#### 2.3.12 P12 推理服务

- **职责**：
  - 查询嵌入与批量文档嵌入；
  - cross-encoder 重排；
  - NLI 闸（MiniCheck-FT5 或 HHEM-2.1-Open）；
  - 主题分类器。
  - 模型取自带许可元数据的模型注册表（B-06）；表示模型的最终选型见 Q7。
  - 模型权重在构建或部署期由部署流水线下载，按注册表校验许可与哈希后放入镜像或只读卷；运行期推理服务不联网。
  - 可选的自托管 LLM 也放在此处（或独立的 `llm-local` 服务），承接含个人数据的 LLM 任务（08 §9.4）；调用方在 back 网络内直连，不经 Egress。
- **不做**：不访问公网；不处理私有全文（私有派生在用户侧完成，AD-13）。
- **扩缩**：CPU 副本起步；T1 默认不配 GPU（简报 R2-45），GPU 为可选加速。重排按 R2-39 从小模型 int8、top-50 起步（§8-4）。涉及用户画像的 LLM 任务（画像摘要、带画像的 listwise 重排）只允许自托管模型，T1 默认关闭并回退到非 LLM 路径。

#### 2.3.13 P13 Egress Gateway（出站网关）

**职责**：平台**唯一**的公网出口（AD-01、INV-03；简报 R2-08），也是 04 稳定性算法与 Policy Engine 裁决（判定规则 08 §4，实现 03）的执行宿主；03 的 PoliteHttp 是它内部使用的客户端库。它是应用层网关：调用方经内网 RPC 提交 `EgressRequest`，由 Egress 自己解析、校验并向上游发起 TLS 连接。四类路由：

1. `scholarly_upstream`（学术上游，含 bulk 快照、漂移探针与 `oa_host`），能力如下：
   - 主机白名单，取自 registry；SSRF 校验按 08 §10.3（规范化主机名、解析一次并固定地址、拒绝私网与云元数据地址）。**每一跳重定向都重做**白名单、SSRF 与策略判定，最多 5 跳；
   - 按 registry 的 URL 模式推出来源通道与上游请求类，不采信调用方声明（INV-02）；
   - robots 先行（HC-29、SI-38）：对任一主机，没有有效 robots 快照时，先以 `policy_probe` 取 robots.txt；取不到（WAF、5xx、超时）视同全禁（08 §4.2 R3）。robots 是 Policy Engine 五个通道之一，路径级读法沿用 D-026；
   - 策略裁决：五通道取最严，结论为 03 §6.3 的 AccessDecision，模式取 03 §6.2 的五档全序 `deny < link_only < user_side < on_demand < background`（简报 R2-09；08 §4.2 的判定名是它的规则层记法），含 `needs_confirmation`、商用与地区开关。模式低于请求类所需的最低模式（`BACKGROUND_BATCH` 需 background，`ON_DEMAND` 需 on_demand）一律不发请求；带 `needs_confirmation` 的通道拒绝 `BACKGROUND_BATCH`（HC-31）；
   - 挑战检测：v1 `ChallengeDetector` 的特征库单一来源（§6.2）；遇挑战按 D-030 E-1 的域级键冷却 24 小时；
   - 令牌桶按 **(source, host, upstream_class, credential_principal, egress_ip)** 五元组全局共享（P-04 的四元组加 SI-37 的出口 IP）。其中 `upstream_class` 是**上游定义的请求类**，例如 Crossref `x-api-pool` 的 single 与 array 两池（AG §2.2.1）、OpenAlex 的 list 与 search。本平台的 `BACKGROUND_BATCH`/`ON_DEMAND` 与三道舱壁只是同一个桶内的份额，不另开桶：否则同一上游的实际速率会随内部类别数翻倍，例如 arXiv 变成每 3 秒 2 次，违反 HC-06。每个来源在一个部署中至多登记一个部署级凭证主体，registry lint 拒绝多 key（HC-10；LQ-13）；
   - 最小请求间隔取 max(Crawl-delay, 书面限额, 名录保守值)（08 §4.2 R13）；
   - 解析 IETF RateLimit、`x-ratelimit-*`、`x-rate-limit-*`、`x-api-pool` 等响应头，在书面限额以下做 AIMD；
   - 重试预算：单请求 ≤3 次，每源 2 分钟窗口内重试占比 ≤10%（RT §9.1）；只重试幂等请求，退避用 full jitter，`Retry-After` 优先；
   - 按"源 × 端点"熔断；
   - 三道舱壁：交互、收割、enrich。交互道保底 ≥50%（RT §9.1 [判断]）。保底是下限而不是上限：交互道空闲时，其份额可借给收割道与 enrich 道；交互请求到来时，在下一个令牌上优先 [判断]；
   - 应用层 TTL 缓存与负缓存，TTL 取 `min(24h, 0.1/λ̂)`（SI-21），并服从来源的 `storage_policy.cache_mode`（03 §3.2）；singleflight 合并；
   - 流式模式：bulk 快照与大文件边下载边写入对象存储，不进 TTL 缓存，支持断点续传；
   - OpenAlex 美元预算桶；
   - FetchLog 逐请求审计（HC-28、INV-10）：每次尝试一行，含拒绝、重试、挑战与超时。v1 的 FetchLog 只记资产取回（design/05 §7），v2 扩到每个出站请求。
2. `model_provider`（LLM 与嵌入 API）：
   - `data_class` 闸：只放行 `shareable`（INV-04；08 §9.1）；
   - 地区路由：`region=cn` 时只允许已备案或自托管模型（HC-12）；
   - 零保留端点白名单；token 与美元记账；
   - 路由判定是调用方共享的库（08 §9.4），Egress 对外部端点再执行一次同样的闸（纵深防御）。自托管端点在 back 网络内，不经 Egress。
3. `identity_provider`（身份提供方与用户授权的导入）：
   - 范围：OIDC 授权码换令牌、JWKS 与 UserInfo；ORCID 作品导入；Zotero 导入；
   - 只接受用户触发的 `ON_DEMAND` 请求。用户登录用的 OAuth client secret（如 ORCID 登录）归认证服务持有，随令牌交换请求提交（简报 R2-30）；Egress 只转发，client secret 与用户的访问令牌都只随单次请求透传，不落盘、不进日志；
   - pub.orcid.org 的 robots 为全禁，按 08 §4.2 R5 只做按需低频调用（08 §4.6 第 4 项）。
4. `notification`（通知，§2.3.17）：
   - 范围：外发邮件（SMTP 中继或事务邮件 API）、Web Push 推送服务、告警 webhook；
   - 白名单只含部署配置的服务端点。请求体按模板生成，不含私有内容；日志只记收件方的假名化键、模板 id 与结果，不记正文。

**密钥**（简报 R2-30）：部署级上游 API key（NCBI、Crossref 联系邮箱、OpenAlex、S2、LLM、邮件服务凭证等）由 Egress 独占读取（docker secrets 或 0600 文件，外部 KMS 可选），在出站时注入。08 §5.5 列出的使用者（收割 worker、联邦查询 worker、LLM 网关）在本架构中都经 Egress 出站，API 与工作者本身不持有上游 key。用户登录用的 OAuth 客户端密钥（如 ORCID 登录、通用 OIDC）归认证服务的秘密存储（08 §5.5）。Springer Nature OA/Meta API 与 NASA ADS 在条款书面确认前按用户级凭证处理，不在 Egress 登记部署级 key（简报 R2-14）。用户提交的新来源登记请求在审核通过前不进 `scholarly_upstream` 的主机白名单，不产生任何上游请求（R2-23；01 FR-29）。

**不做**：

- 不感知用户身份。联邦配额在 API 侧按用户扣减；Egress 只看 lane 与预算主体。
- 不执行 `exec_side=user` 通道，也不接收任何用户级出版商凭证。
- 不对同一第三方主机发对冲请求；只在"同能力的不同来源"之间对冲，且额外负载 ≤5% 并计入预算（RT §9.1）。

**扩缩**：

- T1 单例。宕机时平台降级为"仅本地/仅元数据"（§2.12 F4）。
- T2 按来源分片：每个来源的桶只归一个实例所有，以租约切换；多实例共用同一出口 IP 与平台身份（HC-10）。

**请求接口与处理流程**（设计伪代码）：

```python
# 设计伪代码 —— Egress 请求接口与处理（判定规则以 08 §4 为准，Policy Engine 由 03 实现；稳定性参数以 04 为准）
@dataclass(frozen=True)
class EgressRequest:                      # 调用方经内网 RPC 提交；由 Egress 发起到上游的 TLS 连接
    route: Literal["scholarly_upstream", "model_provider", "identity_provider", "notification"]
    method: str
    url: URL
    headers: Mapping[str, str]
    body: bytes | None
    request_class: Literal["BACKGROUND_BATCH", "ON_DEMAND"]   # 08 §4.3；USER_SIDE 永不经过 Egress
    purpose: Literal["normal", "policy_probe"]                # policy_probe：robots.txt、ToS 页、tdmrep 等
    lane: Literal["interactive", "harvest", "enrich"]         # 三道舱壁（同一桶内的份额）
    deadline: datetime                                         # 逐层传递的截止时间
    source_hint: str | None                                    # 只作交叉校验；真值由 registry 按 (host, path) 推出
    data_class: str | None                                     # 仅 model_provider：08 §9.1 的四类
    idempotent: bool                                           # 非幂等请求不重试、不缓存
    stream_to: str | None                                      # bulk：流式写入 snapshots/ 下的对象键

async def handle(req: EgressRequest) -> EgressResponse:
    log = fetch_log.open(req)                                  # INV-10：每次尝试恰好一行，被拒也落账；URL 按 sensitive.py 脱敏
    try:
        return await _route(req, log, hop=0)
    except EgressError as e:                                   # 拒绝、挑战、熔断、超时、预算耗尽
        log.fail(e.code)
        raise
    finally:
        log.close()

async def _route(req: EgressRequest, log: FetchLogRow, hop: int) -> EgressResponse:
    target = ssrf.check_egress(req.url, route=req.route)       # 08 §10.3：规范化、固定解析结果、拒私网
    src = registry.source_for(req.route, target.host)          # 四类路由各自的主机白名单
    if src is None:
        raise Denied("host_not_registered")
    if req.source_hint not in (None, src.id):
        raise Denied("source_mismatch")
    chan, upstream_class = registry.classify(src, req.method, target.path)   # 按 URL 模式推出通道与上游请求类
    if req.route == "scholarly_upstream" and (chan is None or chan.exec_side == "user"):
        raise Denied("exec_side_user")                         # INV-02、HC-03
    if req.route == "model_provider" and not llm_routes.allows(REGION, req.data_class, src):
        raise Denied("model_route")                            # INV-04、HC-12
    snap = policy.snapshot()
    if not snap.trusted and req.purpose != "policy_probe":
        return cache.lookup_or_raise(req, code="policy_snapshot_untrusted")   # F15：失败即关闭，只回缓存命中
    if req.route in ("scholarly_upstream", "identity_provider") and not is_robots_txt(target):
        rb = await robots.ensure_fresh(target.host)            # HC-29：无有效快照时先取 robots.txt；不可读按 R3 视同全禁
        decision = (policy.decide(snap, src, chan, target.path, rb, req.request_class)   # 03 §6.3 的 AccessDecision（R2-09）
                    if snap.trusted else robots_only_decision(rb))   # 快照不可信时，只有探针可走到这里
        log.gate(rb, decision)                                 # 判定先于首个请求落账（08 AC-0.12）
        if not decision.allows(req.request_class):             # 模式低于该请求类的最低模式（03 §6.2）
            raise Denied(decision.reasons)                     # 含 needs_confirmation 通道上的后台批量（HC-31）
    if cooldown.active(src.id, target.host):
        raise Challenged(src.id)                               # 挑战冷却期内零请求（AC-V1.3）
    if breaker.is_open(src.id, chan):
        raise SourceUnavailable(src.id)
    if req.idempotent and req.stream_to is None and (hit := cache.lookup(req)) is not None:
        return hit
    return await singleflight.do(cache.key(req),               # 同键请求合并
                                 lambda: _send(req, src, chan, upstream_class, target, log, hop))

async def _send(req, src, chan, upstream_class, target, log, hop) -> EgressResponse:
    bucket = (src.id, target.host, upstream_class, src.credential_principal, EGRESS_IP)
    for attempt in (1, 2, 3):                                  # 单请求 ≤3 次
        await buckets.acquire(bucket, lane=req.lane, deadline=req.deadline,
                              min_interval=policy.min_interval(src, target.host))   # R13
        resp = await http.send(target, req, user_agent=IDENTITY_UA, inject=secrets.for_source(src),
                               follow_redirects=False, stream_to=req.stream_to, deadline=req.deadline)
        log.attempt(attempt, resp)                             # 重试也逐次落账
        buckets.observe(bucket, resp.status, resp.headers, resp.latency)   # 头驱动 + AIMD（上限为书面限额）
        breaker.record(src.id, chan, ok=resp.ok)
        if challenge.classify(resp) == "CHALLENGE":
            cooldown.open(src.id, target.host, hours=24)       # 域级冷却键（D-030 E-1）
            alert("challenge", src.id)
            raise Challenged(src.id)                           # 不重试、不求解（HC-26）
        if resp.is_redirect:
            if hop >= 5:
                raise Denied("too_many_redirects")
            return await _route(req.follow(resp.location), log, hop + 1)   # 每跳重做 SSRF、白名单与策略
        if resp.ok:
            return cache.store(req, resp, ttl=src.ttl_for(req), policy=src.storage_policy.cache_mode)
        if attempt == 3 or not (resp.retryable and req.idempotent and retry_budget.allow(src.id)):
            break                                              # 2 分钟窗口内重试占比 ≤10%
        await backoff_full_jitter(attempt, retry_after=resp.retry_after, deadline=req.deadline)
    raise UpstreamError(src.id, resp.status)
```

平台身份 UA 沿用 D-014 的"诚实可识别"原则，但用途字段要改。v1 的 `personal research` 不适用于多用户平台，建议改为部署身份加联系地址，例如 `PaperCrawler/<ver> (+https://<部署域名>/bot; mailto:<运维邮箱>)`，最终格式由 08 定。

#### 2.3.14 P14 Policy & Rights Engine 与 Drift Probes

- **Policy Engine**（判定规则由 08 §4 定义，引擎与 SourceSpec 字段由 03 实现）：
  - 纯函数库，输入为 `ops` 中的策略快照与请求类（`BACKGROUND_BATCH`、`ON_DEMAND`、`USER_SIDE`，08 §4.3）；
  - 对每个来源通道的五个判定通道（文档化 API、bulk、robots 路径、ToS 自动化条款、TDM 与 AI 信号，另加运行期挑战观测）取最严，输出 03 §6.2 五档全序上的模式 `deny < link_only < user_side < on_demand < background`（简报 R2-09：唯一的策略模式枚举；08 §4.2 的 `ALLOW`/`ON_DEMAND_ONLY`/`LINK_ONLY` 等判定名映射到它，不能一一对应时取更严者）；`needs_confirmation` 是通道状态，其放行面为 on_demand（08 §4.4）。05 `ops.policy_snapshot.mode` 用同一枚举；
  - 另给出 AI 用途判定（Content-Signal `ai-input`/`ai-train`、TDMRep、具名 AI UA 规则），供 `enrich_embed` 与 `enrich_llm` 使用（08 §4.2 R9–R11）；
  - 调用方有四处：Egress（每个请求）、Feed 的 Hydrate、全文选项 API、RetrievalIntent 签发（`USER_SIDE` 判定随意图下发，08 §5.1.2）；
  - 另编译**签名策略包**下发给用户侧组件（§2.4）。
- **Rights Engine**（CP DI-01）：
  - 输入为来源、多源许可字段与部署的商用属性；
  - 输出每个字段的 `rights_class`（M1–M25）、`display_level_max`（DL0–DL4，即 CP 的 V0–V4，简报 R2-03）与 `display_scope`；
  - 许可冲突取最严，未知即拒（SI-60）。映射由 08 定义。
- **Drift Probes**（周期作业，经 Egress 以 `policy_probe` 发出）：
  - 比对 robots 与 ToS 哈希、tdmrep、Content-Signal、挑战率、配额头、DOI 前缀与 member、"200 空体"、弃用公告页（RT §12-31）；
  - 发现漂移即告警，按简报 R2-15 分档处置（SI-12）：robots 与 TDM 信号漂移立即降级；ToS 哈希变化给 7 天宽限（依靠书面确认运行的通道，其确认在 24 小时内回退，08 §4.4）；元数据通道自身受影响时暂停，并切换到替补链。证据复核逾期按 R2-16 记 `review_overdue`，探针持续为绿、证据其余字段完整时宽限 30 天。
- **不做**：策略引擎不发网络请求（探针除外），也不在运行期修改名录（改动须经 Admin Console 复核）。唯一的自动登记是 `oa_host` 类来源（08 §10.3）：只用于许可闸放行的 OA 全文，分配保守限速桶，登记与撤销都写审计。
- **扩缩**：策略库随调用方扩展；快照按版本缓存在各进程。探针是周期作业，同样受 Egress 礼貌预算的约束。

**名录状态在运行时的效果**（回应需求 R1 的"支持名录"：名录状态不只是文档标签，而是由架构强制的运行时行为；状态按简报 R2-10 分为 `v1_status` 与 `v2_status`，只有 `v2_status` 影响运行时，登记流程见 03）：

| 名录状态 | 平台侧（Connector 与 Egress） | 用户侧 | 名录 API 与卡片 |
|---|---|---|---|
| `v2-P0…P2` | 按 SourceSpec 声明的来源通道运行；P1/P2 在接入完成前按 `metadata-only` 处理 | `fulltext` 通道按 `exec_side` 与 08 R16 执行 | `/sources` 显示状态、通道与 `verified_at` |
| `metadata-only` | 只运行 `metadata`、`latest` 通道（常经 `crossref_delegated`）；Egress 拒绝该来源的 `fulltext` 路径 | 按 08 R16 逐次判定：常见为 `open_in_tab` 或 `openurl`，用户有本人 TDM key 时可 `tdm_api` | 卡片给出外链 |
| `link-only` | 不向该主机发任何请求；元数据只经第三方获取 | `open_in_tab` 与 `openurl`（08 §4.2 R8） | 只给外链 |
| `user-import-only` | 不运行任何 Connector | 用户经 `POST /library/import` 导入题录（RIS、BibTeX） | 标注"仅导入" |
| `excluded` | 主机不进白名单，任何请求都被拒绝（例如 HC-26、HC-27 所列站点） | 不提供取回方式 | 可不列出，或列出并注明原因 |

名录状态只约束平台侧的收割与出站；用户侧能用哪种取回方式，始终由 Policy Engine 按 08 §4.2 逐次判定并随 RetrievalIntent 下发。

#### 2.3.15 P15 Admin Console

- **功能**：
  - 来源名录与状态管理，对应 registry 的状态枚举（简报 §6.1-7）；
  - `needs_confirmation` 复核队列与书面确认留档（Q4）；
  - 漂移告警处置；去重候审；
  - 用户、邀请码、删除请求；
  - 实验与 ValueModel 版本；特性开关；
  - 上游治理面板：配额、美元、429、挑战计数与条款哈希（CP DI-06）；
  - 推荐原理公示文本管理（HC-13）与算法备案材料导出（HC-14）；
  - 申诉与纠错队列（HC-13，v2.0 即启用，覆盖推荐、标签与内容纠错）；
  - 审核队列（V6，默认关闭）。
- **边界**：
  - 管理员常规界面只看到假名化与聚合后的数据，看不到用户私有内容（01 FR-82）；支持访问须经工单授权与限时的支持窗口（05 `ops.support_grant`），并写审计；
  - 管理 SPA 与 `api-admin` 只在内网暴露；强制 MFA；
  - 敏感开关（商用、地区、策略覆写）采用**四眼复核** [判断]；
  - 审计日志只追加，写入 `ops`：主体用 HMAC 假名 `subject_ref`，哈希链，单写者串行（简报 R2-36；05 §3.4 ⑤ 以暂存表加单例链接器实现）。留存期由 08 的留存矩阵确定，参考 HC-14：影响评估记录 ≥3 年，日志 ≥6 个月。

#### 2.3.16 P16 Observability

详见 §2.13。组件形态如下：

- 各进程内置 OpenTelemetry SDK；
- Collector 汇聚日志、指标与追踪；
- 指标存储（Prometheus 兼容），追踪存储（OTLP 后端）；
- 告警路由：外发告警经 P17 Notifier 与 Egress 的 `notification` 路由（INV-03）；
- 看板由 Admin Console 内嵌，是否另加外部看板见 §2.10.3。

#### 2.3.17 P17 Notifier（通知出口）

- **职责**：
  - 账号类邮件：注册验证、邀请码、口令重置、新设备登录通知（08 §10.2 第 1 项）；
  - 数据权利类通知：导出包就绪、注销宽限期提醒（08 §6.4）；
  - digest（邮件或站内），每日至多 1 封，内容与预算由 06 §7.9、§11.3 定义；Web Push 默认关闭；
  - 运维告警的外发（Alertmanager 的接收端）。
- **边界**：
  - 所有外发都经 Egress 的 `notification` 路由（INV-03）；
  - 作业参数只放 id，不放地址与正文（05 §3.4 的队列约定）。发送时在用户上下文中读取收件地址并渲染模板；
  - 正文不含私有全文、笔记或他人信息；digest 中的反馈链接须 POST 确认，防邮件网关预取（06 §5.8）；
  - 发送日志只记假名化收件方、模板 id、时间与结果，不记正文，留存按 08 的留存矩阵。
- **不做**：不做营销群发；不向用户未同意的渠道推送。
- **扩缩**：单实例起步；外部服务的速率上限由 Egress 桶约束。

### 2.4 执行位置（exec_side）与用户侧组件

**分派规则**：每个 SourceSpec 来源通道都声明 `exec_side`（简报 §5）。本文规定它的放置逻辑（设计伪代码）：

```python
# 设计伪代码 —— 按 exec_side 放置来源通道作业（Connector 接口由 03 定义）
def place(channel: SourceChannel, job: ChannelJob) -> Placement:
    if channel.exec_side == "platform":
        return Placement.PLATFORM_WORKER                     # P7，经 Egress 出站
    # exec_side == "user"：auth-gated 全文与用户级 TDM API（v2.0 范围）。
    # 用户自有 key 的检索型数据库（Scopus 等）不在 v2.0 范围（§2.3.3），接入时另定作业形态。
    if not (job.user_triggered and job.item_count == 1):
        raise Denied("user_side_requires_explicit_single_item")   # P-03、HC-32：显式触发、单篇、不预取
    if deployment.mode == "personal" and deployment.host_is_user_device:
        return Placement.LOCAL_AGENT                         # 签发意图后直接派给同机的 pc-agent（仍是单篇）
    return Placement.CLIENT                                   # 意图返回 PWA，由扩展或用户自己的 pc-agent 执行
```

两种用户侧放置都由 pc-agent 或扩展执行；平台服务镜像（含 personal 部署的服务端容器）本身从不执行 `exec_side=user` 通道（INV-02、AC-V0.17）。

**`host_is_user_device` 的含义**：P-03 允许"personal 部署或本地代理在用户本机取回"。personal 部署若运行在云主机上，出口是数据中心 IP，并不等于"用户本机"。这种情况容易触发 EZproxy 的"IP 与国家异常"风控，CP §2.3.4 列出的规则包括：24 小时内超过 4 个国家即封禁，60 分钟内 IP 变化超过 20 次即封禁。因此：

- personal 部署默认 `host_is_user_device=false`；
- 只有部署者声明运行在本人设备上时，才允许 `LOCAL_AGENT` 放置；
- 否则仍走扩展（见 §8-3）。

**用户侧组件**

| 组件 | 职责 | 边界（不做） | 与平台的交互 |
|---|---|---|---|
| U1 PWA | Deck 分拣、瀑布流、详情 Sheet；手势、按钮与键盘等价操作；IndexedDB 事件队列；缓存当前批次；OA 第四态（"用你的权限"）由扩展或 pc-agent 在用户侧计算（订阅配置在端到端加密凭证库中，PWA 不持有 Vault Key，08 §5.3），PWA 经 `pc.entitlement.query` 取结果、只在内存中使用；只用本人私有数据：用户自报的机构或出版商订阅配置（EZproxy 前缀、OpenURL 解析器等）与本人历史回执（08 §5.1.6；07 §8.6、§15.7），**不做探测请求**；用 pdf.js 阅读本机 PDF 副本（字节来源见下文） | 不持有出版商凭证；不跨用户共享任何状态 | 会话 Cookie；REST 与流式检索（§2.8.7） |
| U2 Companion Extension（MV3） | 验签 RetrievalIntent；执行用户本人会话内的单篇取回。按 08 的规则选择方式：`oa_link` > `tdm_api` > `user_fetch` > `open_in_tab`；`user_fetch` 须满足 R16，否则退回可见标签页，由用户本人阅读或保存（AD-10）；具名 AI-UA 禁令站点不代发 `user_fetch`，只提供"在出版社打开 + 打开后一键保存"（`tab_save`，经 `activeTab`；简报 R2-18、08 §5.1.1）。端侧纪律沿用 v1（08 §5.1.5）：同一出版商域串行，间隔 ≥6 s；单域单日尝试上限默认 200 次，成败都计；遇挑战即停，该域冷却 24 h，交给用户处理；校验 `%PDF` 魔数与 ≥10 KB | 不做后台批量；不解挑战；不暴露"抓取任意 URL"的接口；不向平台回传 Cookie、令牌或 PDF 字节（本机内把 PDF 交给 PWA 阅读不在此列） | OAuth 2.1 PKCE 令牌（作用域 `fulltext:intent`）；只回报回执：`ok`、`no_entitlement`、`challenge`、`handed_to_user`、`error`（08 §5.1.2） |
| U3 pc-agent（本机） | 用户级 TDM API（Elsevier、Wiley、SN 等，用本人 key）；机构 EZproxy/SSO 流程。复用 v1 的 AuthProvider、`CredentialStore`（AES-GCM，D-023）与 `browserfetch`；可选的 T3 本地模型派生，其产出遵守出版商 TDM 的输出规则，只留在本人私域（HC-25） | 只在用户本机运行；不接受来自平台的批量指令；localhost 接口必须带令牌鉴权，并限定来源（防 DNS 重绑定与跨站调用） | 拉取本人待执行的 RetrievalIntent（出站连接）；只回报回执 |
| personal 部署 | 平台服务按单租户运行（B-02），与 platform 使用同一服务镜像；用户侧能力由同机安装的 pc-agent 提供；部署级凭证属于用户本人，例如本人的 NCBI key、Crossref 联系邮箱 | 与 platform 同码，礼貌约束（P-04）照样生效；服务端容器不含用户级凭证模块 | 本机 API |

**两类签名对象**（设计伪代码）

```python
# 设计伪代码 —— 平台下发给用户侧的签名对象（字段以 08 定稿为准）
class RetrievalIntent:                # 单篇取回意图（与 08 §5.1.2 同名）；由用户点击生成
    intent_id: UUID
    work_id: int
    doi: str | None
    candidates: list[Candidate]       # 按序：oa_link / tdm_api / user_fetch / open_in_tab / openurl
                                      # 每项带签发时的策略裁决（robots 判定、tos_automation、verified_at），不含任何凭证
    provider: str                     # 出版商或平台 id，作端侧限速键
    session_binding: bytes            # 绑定签发时的用户会话（08 §5.1.2）
    expires_at: datetime              # ≤5 分钟（08 §5.1.2）
    signature: bytes                  # Ed25519；公钥随扩展发布，可轮换

class PolicyBundle:                   # 端侧策略包，周期拉取；只放端侧常量，逐次裁决在意图的候选项里
    version: str
    providers: dict[str, ProviderRule]    # 状态、端侧速率与日配额、挑战特征库版本、允许模式
    expires_at: datetime                  # 过期后扩展只允许 open_in_tab（08 §5.1.2）
    signature: bytes
```

**私有全文的存放与同步**（方案由 08 §5.3–§5.4 定义，本文只定组件与流向）：

- platform 部署中，用户取回的 PDF 默认只存在用户设备（扩展存储或下载目录）；personal 部署存在本机（pc-agent 的 config-home 或本机私有前缀）。
- PWA 内阅读：扩展经 `externally_connectable` 的长连接端口把 PDF 分块传给同一设备上的 PWA，PWA 存入本源的 OPFS 或 IndexedDB 后用 pdf.js 渲染；字节只在本机两个进程之间移动，不经平台服务器（⚠ 二进制分块的传输方式与大小上限实现期核验；Firefox 与 Safari 的对应机制见 §9 第 4 项）。不可用时退回扩展自带的阅读页或浏览器内置阅读器。
- 多设备同步是可选项（`features.private_pdf_sync`，默认关闭），上传的是**端到端密文**：
  - 由持有字节的一端（PWA 或扩展）用随机文件密钥加密，文件密钥由用户的 Vault Key 封装（08 §5.3–§5.4）；
  - 密文经限定前缀、大小与时效的预签名 URL 写入 `private/` 下该用户的命名空间（路径以 05 §6.1 为准）；
  - 服务端只存密文、大小与时间，不存明文哈希（INV-08）；如需本人范围内去重，用端侧以用户密钥计算的 `content_hmac`（08 §5.4）。
- `%PDF` 魔数与大小校验在端侧完成，复用 v1 `fetchio` 的校验逻辑。
- 简报 R2-27 已裁定（覆盖简报 §6.3-3 第三项）：platform 部署默认只存设备本地；用户开启同步时服务端只存端到端密文、不可解密；服务端私有处理默认关闭。`server_envelope`、`dek_ref`、`processor='api:<vendor>'` 只在 personal 部署且 `deployment.host_is_user_device=true` 时可用（R2-28）。会话 Cookie 与 `storage_state` 属设备绑定凭证，一律不同步，只有 API key 类凭证可做端到端密文同步（R2-29）。功能仍受 LQ-15 约束，`features.private_pdf_sync` 默认关闭。

### 2.5 部署拓扑

#### 2.5.1 两种部署：同一代码

| 维度 | platform（多用户） | personal（单租户） |
|---|---|---|
| 目标 | 自托管或邀请制（B-02、MK §2.9 阶段 1–2） | 承接 v1 的个人使用场景 |
| 编排 | docker compose，`--profile platform` | docker compose，`--profile personal`；用户侧能力由本机安装的 pc-agent 提供（独立安装包，不在服务镜像内） |
| 账号 | 邀请码注册；ORCID/OIDC 登录（§2.8.3） | 单一本地账户，admin 即 owner |
| 工作者 | 按队列分组的多个工作者 | 一个 `worker-all` 消费全部队列 |
| Egress | 单例；平台身份与部署级密钥 | 单例；用户本人的身份与 key |
| 用户侧通道 | 只在扩展或 pc-agent 执行 | 只在扩展或 pc-agent 执行；`host_is_user_device=true` 时，意图直接派给同机的 pc-agent |
| 对象存储 | 本地盘后端或 S3 兼容存储 | 本地盘后端 |
| Valkey、PgBouncer | 可选 | 不需要 |
| Admin | `api-admin`，只在内网暴露 | 绑定 localhost |
| 收割范围 | 全体用户兴趣并集（B-04） | 本人用户频道 |

#### 2.5.2 compose 服务（T1 platform）

| 服务 | 进程/镜像 | T1 副本 | 网络 | 持久卷 | profile |
|---|---|---|---|---|---|
| `edge` | Caddy 或 nginx | 1 | public（发布 443；出站经宿主机防火墙只放行 ACME）、front | 证书 | platform、personal |
| `api` | 应用镜像，`ROLE=api` | 2–4（personal 为 1） | front、back（两者都是 `internal`） | — | platform、personal |
| `api-admin` | 应用镜像，`ROLE=admin` | 1 | back；经 VPN 或 SSH 隧道访问（§2.3.2） | — | platform |
| `scheduler` | 应用镜像，`ROLE=scheduler`（Harvest Scheduler 与 WatchKey 对账、outbox relay、周期任务） | 1（主）+1（备，可选）；relay 两个实例都可运行（`SKIP LOCKED`），选主只约束调度与周期任务 | back | — | platform、personal |
| `worker-harvest` | 队列 `harvest`、`ingest`、`import`（bulk 快照） | 1–2 | back | — | platform |
| `worker-enrich` | 队列 `enrich_meta`、`enrich_embed`、`enrich_fulltext` | 1–2 | back | — | platform |
| `worker-llm` | 队列 `enrich_llm`（提交与轮询批处理） | 1 | back | — | platform |
| `worker-rec` | 队列 `rec_update`、`deck_build`、`percolate`、`rec_nightly` | 1–2 | back | — | platform |
| `worker-maint` | 队列 `index_maint`、`archive`、`drift_probe`、`maintenance`（商用切换清理、删除级联、保留作业）、`export`、`notify` | 1 | back | — | platform |
| `worker-all` | 全部队列 | 1 | back | — | personal |
| `egress` | 应用镜像，`ROLE=egress` | 1 | back、**egress（唯一公网）** | 缓存、robots 快照、流式下载暂存 | platform、personal |
| `inference` | 模型服务，T1 默认 CPU（GPU 可选，简报 R2-45） | 1–2 | back | 模型缓存 | platform、personal |
| `grobid` | GROBID（Apache-2.0） | 0–1 | back | — | 可选 |
| `postgres` | PG 18 + pgvector + pg_textsearch + pg_roaringbitmap | 1 | back | 数据、WAL | platform、personal |
| `pgbouncer` | 事务池，只供 API 使用 | 0–1 | back | — | 可选 |
| `valkey` | Valkey（BSD） | 0–1 | back | — | 可选 |
| `objectstore` | S3 兼容服务（可选；默认用本地盘后端，不起此服务） | 0–1 | back | 对象 | 可选 |
| `otel`、`prometheus`、`traces` | 观测栈 | 各 1 | back | 指标与追踪 | `observability` |
| （不在 compose 中）`pc-agent` | 独立安装包或独立镜像（`[agent]`、`[auth]`、`[auth-browser]` extras） | 每用户 1 | 用户本机网络；只经 Edge 访问 API，不挂 back | 本机 config-home（D-032）与凭证库（D-023） | 用户侧 |

各服务的队列归属与 05 §3.4 的五道舱壁对应如下（05 已定稿）：`interactive` ← `rec_update`、`deck_build`；`harvest` ← `harvest`、`ingest`、`import`、`drift_probe`；`enrich` ← `enrich_*`、`percolate`、`rec_nightly`、`index_maint`；`privacy` ← `export` 与删除级联；`maintenance` ← `maintenance`、`archive`、`notify`。这里的 `interactive` 指时延敏感的近线队列（01 NFR-9 的 2 秒生效目标），工作者进程仍与 API 进程隔离，与 06 §2.1"rec-worker 不在交互舱壁内"的说法不冲突。近线队列名按简报 R2-07 统一为 `rec_update`（06 §8.2、05 §3.3.4 同名）。

#### 2.5.3 网络拓扑

```text
Internet ──443──► [edge] ──(front，internal)──► [api ×N]
                                        │
      ┌──────────────── back 网络（internal: true，无公网路由）────────────────┐
      │ [api ×N] [api-admin] [scheduler] [worker-*] [inference] [grobid?]      │
      │     │            │            │           │                           │
      │     └────────────┴──► [pgbouncer?] ──► [postgres]   [objectstore?]    │
      │                                        [valkey?]    [otel/prom/traces] │
      │ [egress] ◄── 所有平台出站请求（EgressRequest RPC，内部）                  │
      └────┬───────────────────────────────────────────────────────────────────┘
           └──(egress 网络，唯一接公网)──► 学术上游 · Bulk 快照 · LLM/嵌入 API · 身份提供方 · 通知
Admin：VPN 或 SSH 隧道 ──► [api-admin]（内网端口）
备份：备份主机经 VPN 或 SSH 拉取 WAL 与基础备份（平台不主动外连）
```

- **Edge 的出站例外**：Edge 挂在可接收入站 443 的 `public` 网络上，Docker 默认也会给它出站能力。宿主机须以 `DOCKER-USER` 链限定 Edge 的出站只到 ACME 证书端点；或改用离线签发证书（DNS-01 在宿主机外完成），这时 Edge 零出站 [判断]。
- **只有 Edge 与 Egress 挂非 `internal` 网络**：一个容器只要挂上任一非 `internal` 网络就能出网，所以 `front` 也必须是 `internal`，API 不能直接挂 `public`。`api-admin` 的访问方式（宿主机 SSH 端口转发，或 Edge 上只绑定 VPN 接口的管理入口）与 Docker `internal` 网络上的端口发布行为，⚠ 实现期核验。
- **DNS**：back 网络只解析服务名；上游域名只由 Egress 解析，解析结果按 08 §10.3 固定后连接。

#### 2.5.4 T1 单机参考规格

以下均为设计值 [估算]。按 RT §12-24，须在目标硬件上用自有语料压测后校准。01 把 v1 NFR-7 中 personal 部署的资源目标交给本文，见表中 personal 两行。

| 档 | CPU | 内存 | 存储 | 适用 | 依据 |
|---|---|---|---|---|---|
| T1 起步 | 16 vCPU | 64 GB | 2 × 1.92 TB NVMe（RAID1） | ≤1,000 活跃用户，语料 100–300 万 | RT §11 T1（64–128 GB 加 NVMe）；§2.11 |
| T1 设计上限 | 32 vCPU | 128 GB | 2 × 3.84 TB NVMe（RAID1），另加异机备份 ≥2× 数据量 | 按 1 万用户、1,000 万 work 做容量设计（B-04） | RT §5.3：1,000 万 × 1024 维 `halfvec` 的 HNSW 约 23 GB ⚠ 粗估 |
| 可选加速（T1 默认不配，简报 R2-45） | 1 张 24 GB GPU | — | — | 回填嵌入、重排、自托管 LLM（`region=cn` 或隐私场景）；未配时含个人数据的 LLM 任务关闭 | RO §3.2：百万级回填单卡约数十分钟、纯 CPU 约数十小时 ⚠ |
| personal 最低 | 4 vCPU | 16 GB | 200 GB SSD | ≤50 万 work [估算] | RT §11 T0（≤100 万 work） |
| personal 推荐 | 8 vCPU | 32 GB | 1 TB SSD | ≤300 万 work [估算]；超出 RT T0 的 100 万部分须压测确认 | 同上 |

T1 设计上限档的内存预算 [估算]：

| 用途 | 预算 |
|---|---|
| PG `shared_buffers` | 约 32 GB |
| PG 有效缓存（含 `shared_buffers`） | 约 80 GB；工作集为 HNSW 约 23 GB + BM25 约 13 GB ⚠ + 热表，合计约 50–60 GB。换模型重建 HNSW 时，构建速度依赖 `maintenance_work_mem` 能否容纳图（⚠ 调研未覆盖，按 pgvector 文档实现期核对），应安排在夜间窗口并临时压低其他预算 |
| API 与工作者 | 约 16 GB |
| 推理服务（CPU 模型） | 8–16 GB |
| GROBID 与 Valkey | 约 6 GB |

#### 2.5.5 部署配置

01 把 v2 部署配置交给本文定义（v1 的 config-home 只作 ETL 的只读来源）。配置分四层，逐键覆盖，延续 design/10 的分层与敏感边界：

| 层（高 → 低） | platform | personal | 说明 |
|---|---|---|---|
| 1 环境变量 | `PC_*` | `PC_*` | 临时覆盖与 CI；密钥不经环境变量传递，改走第 2 层 |
| 2 秘密 | docker secrets（`/run/secrets/*`）或 0600 文件；外部 KMS 可选 | 同左 | 部署级密钥，只由 Egress 等持有方读取（§2.3.13） |
| 3 部署配置文件 | 挂载的 `config/*.toml`：架构参数（§2.15）、队列并发、限速初值、LLM 路由 | 同左 | 敏感键出现在此层即拒启动，沿用 D-025 的护栏 |
| 4 内置默认 | 代码中的默认值 | 同左 | 安全侧默认：开关默认关闭 |

pc-agent 是用户侧进程，沿用 v1 的 config-home（`PAPER_CRAWLER_HOME`，D-032）与凭证库（D-023），不读平台的部署配置。

#### 2.5.6 T2 演进路径

| 触发条件（可观测） | 动作 | 保持不变的契约 | 依据 |
|---|---|---|---|
| API 与工作者和 PG 争用 CPU 或 IO；在线 p95 持续超预算 | PG 独立主机；增加流复制只读副本，承接探索页、分析与近线读 | API 与事件契约；RLS | RT §11 T2 |
| HNSW 不能常驻内存；检索 p95 >300 ms；建索引超出夜间窗口 | 切换到 pgvectorscale（DiskANN + SBQ，按 subfield/topic 标签过滤） | 检索接口；向量版本表 | RT §5.4；SI-27 |
| 语料 >1,000 万–5,000 万，或检索 QPS 超出单机能力 | 外置检索引擎（Qdrant、Vespa、OpenSearch 择一），经 outbox/CDC 同步，PG 始终是真值源 | outbox 事件；规范化查询 | RT §5.4、§11 |
| evt >10⁹ 行/年 | 事件经 CDC 进入 ClickHouse；PG 只保留热数据 | 事件契约；下发记录语义 | RT §10.4；简报 §6.3-5 |
| Egress CPU 或可用性不足 | 按来源分片，保持单一出口身份与 IP | 桶键五元组；FetchLog | 本文 AD-01 |
| 长流程增多（深度检索、批量回填） | 评估 absurd、DBOS 或 Hatchet | 作业幂等键 | RT §10.6；SI-34 |
| 新鲜度 SLO 不达标，或联邦超出免费额度 80% | 按 Q3 的触发条件评估 OpenAlex Member、Crossref Metadata Plus | Egress 预算桶 | 综合 §7.1 Q3 |
| Q2 改为面向中国大陆 | 按法域拆分部署单元：共享底座各自构建，用户私域与个人信息不跨区 | 全部 API | CP DI-09；HC-22 |

### 2.6 数据存储概览

DDL、RLS 策略、分区与迁移细节归 [05](05-data-platform.md)。

#### 2.6.1 PostgreSQL 18 四域

| 域（schema） | 内容（概要） | 访问特征 | 关键约束 |
|---|---|---|---|
| `corpus` 共享层 | Source 与 Venue；TSRG（TopicNode、`route_stat`）；Work/Version/Manifestation 与 `cluster_id`；标识符；摘要（带 `abstract_source` 与 `abstract_rights`）；共享 `card_field`（带 `display_scope` 与 `license_code`）；版本化向量；引文邻接；`oa_asset` 元数据 | 应用角色只读，写入只经 `pc_ingest` 与 `pc_enrich` | 只放公开元数据，以及许可允许再分发的内容与派生物（P-02） |
| `usr` 私有层 | 账号与身份关联；同意记录；兴趣树权重（长期与短期）；用户频道 AST 与频道到 WatchKey 的映射（`channel_watch`）；文献库（状态、标签、笔记、集合）；评分与评论（`private`/`public`）；每用户模型；已见与已下发位图；FeedInbox；预计算批块与缓存候选池（05 `usr.deck_batch`）；屏蔽规则与会话抑制（`usr.mute_rule`、`usr.session_suppress`，由强负反馈与屏蔽在接入事务内同步写入，简报 R2-33）；取回意图与回执（只本人可见，08 §5.1.4）；私有资产元数据（密文引用、大小与时间）；私有 `card_field`；导出与删除请求；可选的端到端凭证密文与设备封装（08 §5.3） | **全表 RLS**；应用角色不是 owner，也没有 BYPASSRLS；事务内 `SET LOCAL` | 由 per_user 内容派生的一切都留在本域（派生继承最严） |
| `evt` 事件层 | 下发记录（`evt.impression`，服务端铸造 `impression_id`）；UI 事件（`evt.event`，06 的契约）；检索日志（规范化查询、所用来源、成本）；k 匿名聚合（`evt.agg_*`，只由 `pc_sys_aggregator` 写；平台指标 `agg_metric_daily` 由 `pc_sys_metrics` 写）。安全审计事件落 `ops.security_log`（05、08 §6.1） | 只追加，按月分区。分区键取自 UUIDv7 内嵌的时间戳，主键为 `(id, event_ts)`，同一事件重试必落同一分区，`ON CONFLICT` 去重才有效（05 §3.3.3） | 可识别形态在 PG 热存 6 个月，其后假名化归档为 Parquet 至第 13 个月（简报 R2-31；满足 HC-14 的 ≥6 个月留存，§2.11） |
| `ops` 运维域 | procrastinate 队列表；outbox；WatchKey（只含下推查询与引用计数，不含用户标识）与游标（watermark）；联邦未命中的候选 WatchKey；来源健康与熔断状态；配额与美元账本；策略快照（robots/ToS 哈希、tdmrep、Content-Signal）；确认登记（08 §4.4）；漂移告警；FetchLog；通知发送日志（不含正文）；去重复核队列；特性开关；ValueModel 与实验配置；管理审计 | 运维角色 | 不存个人内容；日志中的用户引用以假名化键表示 |

#### 2.6.2 数据库角色原则

- 每个组件一个角色，按"最小权限 + 单向流"授权。角色名与授权矩阵以 05 为准，例如 `pc_app`、`pc_auth`、`pc_ingest`、`pc_enrich`、`pc_sys_percolator`、`pc_sys_scheduler`、`pc_sys_aggregator`。
- 能 `SELECT usr.*` 的角色没有 `corpus` 写权限（INV-01）。
- 跨用户读取的后台组件只有 Percolator 与反向推送规划器，都以 `pc_sys_percolator` 运行：只能读频道 AST、用户向量、兴趣节点权重、屏蔽规则中的所需列，对 FeedInbox 只有 INSERT（05 §4.1、§4.4）。
- 按用户执行的近线作业（`rec_update`、`deck_build`、画像更新、导出打包）以 `pc_app` 在该用户的 RLS 上下文中运行，不跨用户读取（05 §4.1）。
- R1 起的全局模型训练只读 `pc_sys_aggregator` 产出的假名化训练抽取物，不读原始 `evt`（05 §3.3.5）。
- Egress 需要写 FetchLog、配额账本、来源健康与冷却状态，并读 registry 与策略快照。05 已为它设专用角色 `pc_sys_egress`：只读写 `ops` 的上述表、只读 `corpus` 的来源注册表，对 `usr`、`evt` 无权限（05 §4.1）。
- 应用角色都不是表 owner，也没有 `BYPASSRLS`；迁移由独立的 owner 角色执行，应用不使用它（RT §10.3）。
- 会话查找由认证模块以专用角色按 `session_id` 进行，查到后再 `SET LOCAL` 进入用户上下文。细节由 05、08 定义。

#### 2.6.3 对象存储

| 前缀 | 内容 | 键 | 访问 | 生命周期 |
|---|---|---|---|---|
| `oa-shared/` | 许可白名单内的 OA 全文与图（M11、M13），附许可旁注文件；arXiv 的非 CC e-print 与从中抽取的图不入（HC-06） | 可内容寻址 | 短时签名 URL，或回到原始 OA 链接 | 许可变更即撤下（§2.15） |
| `private/`（按用户命名空间，路径以 05 §6.1 为准） | 私有 PDF 的端到端密文（M16、M25），只在用户选择同步时才有 | 随机 id；服务端只存密文、大小与时间，不存明文哈希（INV-08） | 只对本人签发短时签名 URL，下载的是密文，在端侧解密；不经 CDN 缓存 | 注销即删密文与封装（加密粉碎）；备份残留随备份滚动淘汰（08 §5.4） |
| `snapshots/` | bulk 输入：OpenAlex 子集分区、DROPS dblp、RePEc；PubMed baseline 须待 NCBI 书面确认（§2.3.7） | 来源/版本 | 只供工作者使用 | 导入完成后保留最近 1–2 版 [判断] |
| `archive/` | evt 冷归档（Parquet）；来源原始载荷冷存 | 分区路径 | 运维与离线评测 | 按留存矩阵（08） |
| `exports/{user_id}/` | 用户数据导出包 | 随机 id | 本人签名 URL | 7 天 [判断] |

默认后端为本地盘（经存储抽象层）。S3 兼容后端可选：自托管 S3 的候选许可见 §2.10.3，MinIO 为 AGPL，⚠ 调研未覆盖。

#### 2.6.4 Valkey（可选）

用途有三：按用户的 API 限速计数、热批次缓存、会话缓存。约束如下：

- 永远不是真值源，缺失时回退到 PG；
- 不存私有全文、凭证与笔记；用户态缓存带 TTL，注销与删除请求执行时一并清除；
- 选 Valkey 而不用 Redis 8，因为后者为 RSALv2/SSPL/AGPL 三选一许可（RT §10.5）。

#### 2.6.5 留存分层与备份

- **PG 备份**：WAL 归档加基础备份，支持 PITR。platform 部署的恢复目标沿用 01 NFR-27（05 提议）：RPO ≤5 分钟、RTO ≤4 小时，由 AC-V3.27 演练验证。personal 部署提供一键备份与恢复。
- **异机备份的方向**：默认由备份主机经 VPN 或 SSH **拉取** WAL 与基础备份（平台容器不主动外连，保持 INV-03；简报 R2-37 已裁定拉取式为默认）；若改用推送到对象存储，须为备份进程单独设出口白名单并写入 INV-03 的例外清单。RPO ≤5 分钟要求拉取或推送的周期不长于 5 分钟。
- **删除与留存的冲突**：删除请求（HC-20）与日志留存（HC-14）冲突时，以 08 的留存矩阵为准。默认做法是：安全审计日志保留假名化记录，个人内容与画像立即删除。

### 2.7 关键时序

全局数据流见 [v2-02-dataflow.svg](../../diagrams/v2-02-dataflow.svg)。图中节点编号为 ①–㉑，本节时序里的组件名与图中节点一一对应。联邦检索（d）不在该图中。

#### (a) 取下一批块（`GET /api/v2/feed/deck/next`，即 `/feed/{surface}/next` 取 `surface=deck`）

```text
PWA              API · Feed Assembler(P5) · Rec 在线库(P4)                 PG                        队列
 │ 进入"今日"取首块；本地剩余未展示卡 ≤5 张时预取下一块（07 §15.4）
 │ GET deck/next ─►│ 会话校验 · SET LOCAL app.user_id
 │                 │ 个性化已关闭？→ 直接走非个性化装配器（HC-13）
 │                 │ ① 读预计算批块（ready 且会话态版本未变）───────────────►│
 │                 │    轻重排：mute_rule / session_suppress（强负反馈，R2-33）· 去已下发 · 探索槽位置
 │                 │ ② [无预计算] 在线候选管线（06 §2.2，热路径预算约 235 ms）──►│ 用户态 · 并行召回 · Hydrator
 │                 │ ③ [超时或失败] fast_assemble（预算 150 ms）：FeedInbox + 缓存候选池 → 每用户 LR
 │                 │ ④ [仍失败] 非个性化批块（频道/主题按时间），mode=non_personalized
 │                 │ Hydrate：经展示闸按 display_scope / 许可 / 学科模板取 card_field ─►│
 │                 │ SideEffect（同一事务）：evt.impression 每卡一行（impression_id=UUIDv7 · 位置 · 候选源 ·
 │                 │   分量 · 实验桶 · 倾向分）；usr.seen_segment(served)；usr.deck_batch 进度
 │                 │ defer(deck_build, lock=user)：预计算下一批块 ─────────────────────────────►│
 │◄────────────────│ 200 {batch_id, chunk_idx, final, mode, server_time, cards[批块]{impression_id, 字段, reason_codes,
 │                 │      suppress_keys}, progress{planned, served}, remaining_today, end_state{reason}, can_extend}
```

- **性能**：目标 p95 ≤300 ms（简报 §3），对全部请求成立，不以预计算命中为前提。常态走①（读 + 轻重排 + Hydrate）；②的预算由 06 §2.2 分解，合计约 235 ms；③④是降级路径（AD-03）。
- **批块**：默认每批 25 张（可选 15 / 25 / 35，简报 R2-42），分 10/10/5 三块下发；服务端在当前批块消费约 70% 时触发下一块的预计算（06 §7.7），客户端在剩余 ≤5 张时预取，两者互不依赖。禁止用净负分候选补满批次，候选不足时本批提前结束：最后一块标 `final=true`，`end_state.reason` 区分"候选不足"与"已到上限"，`can_extend` 表示可否"再来 10 篇"（每日总上限 60 ⚠）。每张卡附本地抑制所需的最小键 `suppress_keys`，并返回 `server_time` 供客户端校准事件时钟（06 §19.2、07 §16.3、§23 X-20）。`next` 以 `after` 游标幂等（06 §19.2）。
- **前端预算**：滑动提交到下一张卡可交互 ≤100 ms。这由前端本地完成，DOM 中常驻 3 张卡（UX §3-17），与本 API 解耦。

#### (b) 滑动事件上报（`POST /api/v2/events`）

```text
PWA（IndexedDB 发件箱）          API（事件接入）                              PG                    rec_update
 │ 滑动即入本地发件箱（event_id=UUIDv7, client_ts, impression_id）
 │ 满 20 条 / 5 s / 页面隐藏(sendBeacon) 发一批 ≤50 条
 │ POST /events ───────────────►│ 按 06 契约与 schema_version 校验
 │                              │ event_ts ← event_id 内嵌时间戳；超出 [now−7 d, now+5 min] 拒收 clock_out_of_window（R2-32；05 §3.3.4）
 │                              │ 绑定校验：(impression_id, user_id, work_id) ∈ evt.impression，按 UUIDv7 定位分区
 │                              │   → 不满足时库操作照常，但 train_eligible = agg_eligible = false（unbound，06 §5.8）
 │                              │ 同一事务：
 │                              │   INSERT evt.event … ON CONFLICT (event_id, event_ts) DO NOTHING
 │                              │   not_interested / block → 同步写 usr.mute_rule / usr.session_suppress（R2-33；undo 按 origin_event_id 删除）
 │                              │   INSERT ops.outbox(feedback.received, key=user_id) ; NOTIFY outbox_new
 │◄─────────────────────────────│ 202 {accepted[], duplicate[], rejected[{event_id, code}]}
 │ 429/5xx → 指数退避重发（同 event_id）；只有被明确拒收（如 clock_out_of_window）时才可按服务端时间校准后换 id 重发（07 §15.5）
 │                              │        relay（LISTEN 唤醒，1 s 轮询兜底）─► defer(rec_update, queueing_lock=user)
 │                              │                                                  │ 按 user 加锁，去抖约 1 s（06 §8.2）
 │                              │                                                  │ 标签 · 画像 · LR 热启动重训
 │                              │                                                  │ 使预计算批块失效
```

- **时延目标**：事件到达 → 每用户模型生效 p95 ≤2 秒（01 NFR-9；06 §8.1），见 AC-V4.34。强负反馈不等这条链路：接入事务内已写屏蔽规则，下一次批块请求即生效；客户端也会先从已下载未展示的卡中移除命中项（07）。
- **撤销**：撤销是追加一条撤回事件（简报 §6.4-6），接入层不删除原事件。
- **`open_fulltext`**：字段以 06 §5.3 为准（简报 R2-06）：`route ∈ {oa, user_side}`、可选 `via ∈ {oa_link, oa_version, publisher_link, companion_extension, local_proxy}`、`success`（仅用户侧有回执时填写）；只记路径类型，不记任何凭证信息，不进入任何跨用户聚合（INV-06）。

#### (c) 新论文入库 → percolate → FeedInbox

```text
Scheduler(P6)   Connector(P7)     Egress(P13)     Ingestor(P8)       Enrich/Index(P9/P10)   Percolator(P11)   usr
 │ WatchKey 到期（日历窗 / λ 注水）
 │─defer harvest(key)─►│
 │                     │─请求──────────►│ 白名单 · robots · 策略 · 桶 · 熔断
 │                     │◄──响应─────────│ FetchLog
 │                     │ watermark.advance（v1 语义：先推进、后提交）
 │                     │─RawRecord 批───────────────►│ normalize · 权利标注 · identify(cluster_id)
 │                     │                             │ 事务：corpus upsert + outbox(corpus.change)
 │                     │ watermark.commit（入库成功后）
 │                     │                             │──────────────►│ 摘要补齐 · 主题 · 嵌入(版本化)
 │                     │                             │               │ index 提交：work_search.index_seq
 │                     │                             │               │──────────────────►│ 按 index_seq 水位取批，频道 AST 倒排（硬命中）
 │                     │                             │               │                   │─写 feed_inbox(channel)─►│
 │                     │                             │               │                   │ outbox(deck.stale)
 │ 夜间：Rec 反向推送规划器（06 §11.3）读当日新论文 → 兴趣节点倒排 + 质心点积 → 日预算 · 资格集合曝光下限分配（R2-41）
 │       → 写 feed_inbox(profile_match | reverse_route | explore_pool)，次日 06:00 前完成 ⚠
```

- **时延目标**：频道硬命中从 identify 写出 `corpus.change` 到写入 FeedInbox，p95 ≤30 分钟 [判断]，见 AC-V4.14；兴趣反向推送按夜间批处理，次日可见（06 §8.1）。
- **A 包生成时机**：A 包在 work **首次进入任一用户候选集**时才进入 `enrich_llm` 批处理（PU §2.6.7 的 T1 层），不对全部新论文生成。

#### (d) 联邦检索（本地先返回，远端流式补齐）

执行器契约（合并顺序、事件语义、联邦意图集合）以 04 §8.1–§8.2 为准；本节只定传输。事件名按 04 统一（一致性审计 2026-09-27；07 已按此消费）。

```text
PWA                API · Router(P3)                     推理(P12)      PG（本地索引）      Egress(P13) → 远端
 │ POST /search {text | ast}（Accept: text/event-stream；以 fetch 流式读取响应体）
 │─────────────────►│ 规则快路径 → AST → 规范化查询（缓存键 query_hash）；在 PG 建结果快照 query_id
 │                  │ 投机执行：BM25 ∥ 查询嵌入 → ANN ────────────────►│
 │                  │────── 查询嵌入 ──────►│
 │                  │ 各列表内按 cluster_id 折叠 → 残差过滤 → RRF(k=60) → 每条结果铸造 impression_id（surface=search）
 │                  │── 重排（小模型 int8，top-50 起步，top-100 为上限；在预算内时）─►│（简报 R2-39）
 │◄─ event: snapshot{query_id, query_hash, canonical_query, 结果} ──│（首屏；端到端 p95 ≤800 ms，01 NFR-10）
 │◄─ event: upgrade ─│（仅当重排超预算：先发 RRF 结果，重排完成后替换尚未看到的部分）
 │                  │ 意图 ∈ {SEARCH, SIMILAR}（04 提议的 EXPAND 待裁定）且 覆盖估计 < 目标？
 │                  │   LOOKUP 本地未命中：按同能力替补链逐级补查，不选源（04 §8.4）；LATEST 不联邦（INV-11）
 │                  │   → 原子扣减本人联邦配额与全局美元预算；不足则 done 带 budget_exhausted
 │                  │   → TSRG 预算贪心选源
 │                  │── 并行 fan-out（交互道 · ON_DEMAND，总截止 3 s，同主机不对冲）─────────────────►│
 │◄─ event: source_status{source, status, counts} ─（逐源状态）
 │◄─ event: upgrade | append ─（逐源：健全放宽 → 本地残差 → 折叠 → RRF → 重排；用户空闲时 upgrade 替换未看到的部分，否则 append 追加；同步追加进结果快照）
 │◄─ event: done{completeness, missing_sources, budget} ─（≤3 s；超时源列入缺失）
 │                  │ SideEffect：按来源 storage_policy.cache_mode 入库或只缓存；未命中 → 候选 WatchKey（不带用户标识）
 │◄─ event: suggest（可选：自托管模型的受约束解析结果，以可编辑筛选条呈现，04 §4.2）
 │ 断线重连：GET /search/{query_id}/events + Last-Event-ID → 任一 API 副本从 PG 结果快照续传
```

- **为什么由 `POST` 直接返回事件流**：T1 的 API 有 2–4 个副本。若先 `POST` 拿 `query_id`、再另开 `EventSource` 的 `GET`，两次请求可能落到不同副本，而执行检索的是前一个副本的进程，后一个副本手里没有事件。改为同一个 `POST` 响应直接流式返回，执行与推送在同一进程；`EventSource` 只支持 `GET`，所以客户端用 `fetch` 读取流。每个事件同步追加进 PG 的结果快照，断线后任一副本都能按 `Last-Event-ID` 续传；查询尚未结束时，续传端轮询快照直到出现 `done` [判断]。
- **失败即降级**：Egress 或远端失败时，`done` 仍会发出，并在 `missing_sources` 中列出缺失的来源（P-09）。
- **重排**：01 NFR-10 把融合与重排都计入 800 ms。正常情况下 `snapshot` 携带重排后的结果；重排超出预算时先发 RRF 排序的 `snapshot`，再以 `upgrade` 事件替换尚未看到的部分（简报 R2-39）。这是降级路径，占比须 ≤5%（AC-V2.46），可行性见 §8-4。
- **配额只在真正 fan-out 时扣减**：纯本地命中、被 LATEST 规则挡下或远端全部命中缓存的查询不扣配额（AD-12）。

#### (e) 用户侧全文取回（扩展取回 → 可选以端到端密文同步）

```text
PWA                 API                     Extension（用户浏览器）              出版商          对象存储
 │ 点"全文"
 │ GET /works/{id}/fulltext-options ─►│ 只读：OA 可共享 / 仅外链 / 用户侧可行（不签发意图）
 │ [平台默认] "在出版社打开"（外链）
 │ [已装扩展] POST /retrieval-intents {work_id} ─►│ Policy Engine 以 USER_SIDE 判定候选方式 → 签发 RetrievalIntent（≤5 min）
 │◄── RetrievalIntent（签名，绑定会话，不含凭证；候选项携带 robots 与 ToS 判定）
 │ 经扩展消息通道转交 ─────────────────────────►│ 验签 · 来源白名单 · 策略包 · 端侧限速/日配额
 │                                            │ 按序选方式：oa_link > tdm_api > user_fetch(R16) > open_in_tab
 │                                            │ 本人会话、用户网络出口 ──────────────────►│
 │                                            │◄──────────── PDF ─────────────────────────│
 │                                            │ 挑战页 → 停手、转 open_in_tab 交给用户
 │                                            │ 校验 %PDF 与 ≥10 KB → 存本机
 │◄──── PDF 分块（externally_connectable 端口，本机内）─│ → PWA 存 OPFS/IndexedDB，pdf.js 阅读（§2.4）
 │                                            │─ POST …/receipt {ok|no_entitlement|challenge|handed_to_user|error} ─► API（只存本人 usr）
 │ （可选，features.private_pdf_sync）端侧用文件密钥加密 → POST …/private-assets:upload-url
 │ PUT 密文（预签名，限定本人私有前缀、大小、时效）─────────────────────────────────────────────►│
 │ 事件 open_fulltext{route=user_side, via=companion_extension, success}（06 §5.3；只计本人模型与北极星）
```

pc-agent 路径与此同构：用户在 PWA 选择"用本机代理取回"，pc-agent 拉取本人的 RetrievalIntent，用本人 key 调用 TDM API，同样只回报回执。

### 2.8 API 面

#### 2.8.1 原则

- 资源式 REST，路径前缀 `/api/v2`。流式场景用 SSE 的事件格式（`text/event-stream`）：检索由 `POST /search` 的响应直接流式返回，断线用 `GET` 续传（§2.7(d)）；不引入 WebSocket，因为双向实时需求不明 [判断]。
- **OpenAPI 3.1 是唯一契约**：由 FastAPI 与 Pydantic 模型生成，快照随代码提交；前端 TS 客户端从契约生成；CI 做破坏性变更检测（§3）。
- 错误体用 RFC 9457 `application/problem+json`，携带 `type`、`title`、`detail` 与 `trace_id`。
- 所有写接口都幂等：事件用 `event_id`，其余用 `Idempotency-Key` 请求头，服务端保留 24 小时 [判断]。
- 响应中的每张卡与每条结果都带 `display_scope` 与来源署名字段，署名按出处自动渲染（HC-24）。所有出网字段都经展示闸序列化（08 §3.9）。
- AI 生成字段（TL;DR、翻译、要点、LLM 解释）带机器可读的 `ai_label`（`generated`、`provider`、`content_id`、`model`、`created_at`，08 §9.3；HC-11d）。

#### 2.8.2 REST 资源清单

限速一列均为初值（⚠ 待压测，最终值写入配置）。

| 资源 | 方法与路径（前缀 `/api/v2`） | 语义 | 认证/作用域 | 分页 | 限速初值 ⚠ | 契约与算法归属 |
|---|---|---|---|---|---|---|
| 会话与身份 | `POST /auth/login`，`POST /auth/logout`，`GET /auth/session`，`POST /auth/register`（邀请码），`POST /auth/password/reset`，`GET /auth/oidc/{provider}/start`，`GET /auth/oidc/{provider}/callback`，`GET /oauth/authorize`，`POST /oauth/token`（PKCE），`POST /oauth/revoke` | 邮箱/密码；注册须完成中性年龄声明，不存出生日期（HC-19；01 FR-77）；ORCID OAuth；可选的通用 OIDC；扩展与 pc-agent 的令牌签发与撤销 | 公开或会话 | — | 登录每账号且每 IP 5 次/10 分钟 | 02、08 |
| 我 | `GET/PATCH /me`，`POST /me/export`，`DELETE /me`（带宽限期的删除请求），`GET /me/consents`，`PUT /me/consents/{kind}`，`GET/DELETE /me/search-history`，`GET/PUT /me/notifications`，`GET/DELETE /me/clients` | 账户、单独同意（如双向匹配 opt-in，HC-18）、导出与删除（P-06、HC-20）；本人检索历史的查看与删除；通知与 digest 的订阅（默认关闭）；已授权的扩展与 pc-agent 列表及撤销 | 会话 | — | 导出 2 次/日 | 05、08 |
| 卡片流 | `GET /feed/{surface}/next?after={batch_id}:{chunk_idx}`（`surface` 取 `deck` 或 `explore`；`explore` 即搜索层空查询态的"发现"，不再是独立一级入口，简报 R2-49），`POST /feed/deck/more`，`GET /feed/why/{impression_id}`，`GET/PUT /feed/settings` | 取下一批块（以 `after` 游标幂等）：卡片列表（含 `impression_id`、主次理由、`explore_tag`、`position`、`suppress_keys`）、批次进度（计划与已下发张数）、今日剩余数、`final`、结束原因与 `can_extend`（§2.7(a)）；"再来 10 篇"（只由用户显式触发，递增 05 `usr.daily_quota.extra_grants`，每日总上限 60 ⚠，简报 R2-42）；why-this 详情（模板立即返回；LLM 解释只在部署了自托管模型时懒生成、异步补齐，08 §9.4）；设置（批大小 15 / 25 / 35、免打扰） | `feed:read` | 批块 / 游标 | 30/分钟 | 06、07 |
| 卡片 | `GET /cards/{work_id}`，`GET /cards/{work_id}/related` | 详情（按 `display_scope` 与学科模板）；相关论文 | `feed:read` | 游标（related） | 120/分钟 | 06、07 |
| 事件 | `POST /events` | 批量 UI 事件，每批 ≤50 条，按 `event_id` 幂等；逐条返回接收或拒绝及原因码 | `events:write` | — | 120/分钟 | 06 定义事件；02 定义传输 |
| 作品 | `GET /works/{id}`，`GET /works:lookup?doi=&arxiv=&pmid=`，`GET /works/{id}/versions`，`GET /works/{id}/fulltext-options` | 三层身份；LOOKUP；全文选项（OA 共享 / 外链 / 可用的用户侧方式；只读，不签发意图） | 会话；元数据部分可公开 | — | 60/分钟 | 03、05 |
| 检索 | `POST /search`（响应即事件流），`GET /search/{query_id}/events`（断线续传），`GET /search/{query_id}/results`，`POST /search/parse` | 本地先返回、远端流式补齐；可编辑筛选条；结果快照；结果条目带 `impression_id` | `search` | 游标（基于快照） | 20/分钟；联邦远端每用户 ≤30 次/日 ⚠ | 04 |
| 用户频道 | `GET/POST /channels`，`GET/PATCH/DELETE /channels/{id}`，`POST /channels/{id}:preview` | 用户频道（Query AST 加推送偏好）；AST 可引用其他频道做并、交、差（组合查询），服务端校验无环；预览只查本地（INV-11），给出计数估计与样本；保存时编译 WatchKey 映射（§2.3.7） | `channels` | 游标 | 30/分钟 | 04、06 |
| 文献库 | `GET/POST /library/items`，`PATCH/DELETE /library/items/{work_id}`，`GET/POST /library/collections`，`POST /library/import`，`GET /library/export?format=bibtex\|ris\|json`，`POST /library/items/{work_id}/private-assets:upload-url`，`GET/DELETE /library/items/{work_id}/private-assets/{asset_id}` | 状态、标签、笔记；条目经 `usr.library_item.source_impression_id` 绑定来源曝光（R2-47）；导入（BibTeX/RIS、ORCID、Zotero；Zotero 令牌只在导入作业内存中使用、用后即删，06 AL-22）与导出（P-06；`export_citation` 事件可带 `impression_ids[]`）；私有 PDF 只收端到端密文（`features.private_pdf_sync`，默认关闭，R2-27） | `library` | 游标 | 60/分钟；上传 50 次/日，配额 1 GB ⚠ | 05、07 |
| 评价 | `GET/PUT /works/{id}/my-review`，`GET /me/reviews`，`GET /works/{id}/reviews`（V6，默认关闭） | 私有评分与笔记；公开评价要等 V6 开关与实名审核就绪（HC-15、Q6） | `reviews` | 游标 | 30/分钟 | 06、08 |
| 画像与推荐设置 | `GET/PATCH /me/interests`，`DELETE /me/interests/{node_id}`，`POST /me/interests/reset`，`PUT /me/personalization`，`PUT /me/exploration`，`PUT /me/learning` | 兴趣标签的查看、编辑、删除与重置，立即生效（HC-13）；个性化开关（Deck 顶栏直达，取值 `np_time` / `np_source`，简报 R2-05；响应直接返回新方式的首个批块，06 §19.2）；探索强度；暂停或恢复学习 | `profile` | — | 30/分钟 | 06 |
| 关注 | `GET /me/follows`，`PUT/DELETE /me/follows/{target_type}/{target_id}`（`target_type` ∈ author、venue、source） | 关注与取消关注作者、venue、来源（简报 R2-47）：同一事务内写 05 `usr.follow` 并追加 06 的 `follow` / `unfollow` 事件，事件 id 取请求的 `Idempotency-Key`；关注主题即添加兴趣标签（走 `/me/interests`） | `profile` | 游标 | 30/分钟 | 05、06 |
| 冷启动 | `POST /onboarding/seeds`，`GET /onboarding/calibration/next` | 提交种子（兴趣树勾选、DOI、BibTeX/RIS、ORCID 作品）；下一张校准卡 | `profile` | — | 30/分钟 | 06 |
| 推荐透明 | `GET /recommendation/explainer`，`GET /recommendation/why-not/{work_id}`（R1） | 推荐原理公示，由线上配置生成（HC-13）；为什么没看到 | explainer 公开；why-not 需会话 | — | 30/分钟 | 06、08 |
| 双向匹配（层③） | `PUT/DELETE /match/consent`，`GET/PUT /match/profile`，`GET /match/suggestions` | 单独同意的授予与撤回；公开研究画像；本周匹配建议。受 `features.r2r_matching` 门控（HC-18） | `match` | — | 10/分钟 | 06、08 |
| 来源名录 | `GET /sources`，`GET /sources/{id}`，`GET /venues`，`GET /venues/{id}`，`GET /topics/{node_id}/children` | 支持名录（R1，含状态、通道与 `verified_at`）；venue 目录；主题树 | 公开只读 | 游标 | 60/分钟（匿名 20） | 03 |
| 全文取回（用户侧） | `POST /retrieval-intents`，`GET /retrieval-intents?state=pending`（pc-agent 拉取），`POST /retrieval-intents/{id}/receipt`，`GET /ext/policy-bundle` | 签发单篇 RetrievalIntent（用户点击触发，候选方式由策略引擎给出，08 §5.1.2）；回执 `ok`、`no_entitlement`、`challenge`、`handed_to_user`、`error`（无内容，只存本人 `usr`；以 `intent_id` 幂等）；签名策略包。没有批量签发入口（HC-32）；personal 部署另有"许可允许的 OA 全文批量取回到本人私有空间"（Could，简报 R2-48），只取逐篇许可白名单内的 OA 副本 | `fulltext:intent` | — | 签发 60/分钟 | 08 |
| 申诉与举报 | `POST /reports`，`GET /me/reports` | 对推荐结果、标签、元数据或 AI 内容的申诉与纠错（HC-13 的申诉渠道，v2.0 即提供）；V6 起扩展为 UGC 的通知—处理（HC-15、HC-17） | 会话 | — | 10/日 | 08 |
| 管理（仅 `api-admin`） | `/admin/sources`，`/admin/policy/reviews`，`/admin/drift`，`/admin/dedupe`，`/admin/users`，`/admin/invites`，`/admin/deletions`，`/admin/experiments`，`/admin/value-models`，`/admin/flags`，`/admin/costs`，`/admin/appeals`，`/admin/moderation`（V6） | 见 §2.3.15 | `admin:*` 加 MFA | 游标 | — | 03、06、08 |
| 运维 | `GET /healthz`，`GET /readyz`，`GET /metrics` | 健康与指标，只在内网 | 内网 | — | — | 02 |

06 §19.2 列出的推荐相关 API 语义已在上表定稿路径，统一加 `/api/v2` 前缀；08 §5.1.2 的 `/retrieval-intents` 同理。对外只读 API 与 MCP（SI-70；01 FR-83，Could）列为后续可选项，默认关闭，不在 v2.0 范围。

#### 2.8.3 认证与会话

- **PWA**：
  - 服务端会话，Cookie 为 `HttpOnly; Secure; SameSite=Lax`；
  - 不安全方法要求 CSRF 令牌（双提交），并校验 `Origin`；`POST /events` 的令牌可放在请求体内，以兼容 `sendBeacon`（§2.9.6）；
  - 会话存放在 PG，可选 Valkey 缓存。
- **登录方式**：
  1. 邮箱加密码，argon2id 哈希；管理员强制 TOTP。
  2. ORCID OAuth，用于登录、作者认领与作品导入（简报 §6.3-2）。
     - ORCID 公共 API 限非商业（HC-23），受 `platform.commercial` 门控（LQ-09）；
     - `pub.orcid.org` 的 robots 为全禁，因此只走注册凭证的 OAuth 与 API，低频、由用户触发（SR §4-2、Q4；08 §4.2 R5、§4.6 第 4 项）；
     - 授权码换令牌、JWKS 与作品读取都经 Egress 的 `identity_provider` 路由（INV-03）。
  3. 通用 OIDC，部署可选。例如实验室或机构的 IdP 可以用于**平台登录**，但**绝不用于获取出版商会话**。
  4. OpenReview OIDC，可选，只用于身份关联与作者认领；文档没有说明该令牌能否调用数据 API，不作数据通道（CS §3-9）。
- **扩展与 pc-agent**：
  - OAuth 2.1 授权码 + PKCE，平台作为第一方公开客户端的授权服务器；扩展用浏览器提供的扩展重定向地址，pc-agent 用本机回环地址重定向（⚠ 调研未覆盖，实现期按各浏览器与 RFC 8252 核对）；
  - 访问令牌 15 分钟，刷新令牌轮换并做重用检测；用户可在 `/me/clients` 撤销；
  - 作用域：`feed:read`、`events:write`、`fulltext:intent`、`library:write`。PWA 走会话 Cookie，拥有本人的全部作用域；表中其余作用域名只在将来开放给第三方客户端时启用。
- **公开评论的实名锚定**（ORCID 或机构邮箱）属于 V6 前置条件（简报 §6.3-2），默认关闭。

#### 2.8.4 限速与预算

- **三层限速**：
  1. Edge 按 IP 粗限速；
  2. API 按用户、按端点的令牌桶，有 Valkey 时用 Valkey，没有时退回进程内近似值；
  3. 昂贵资源的**精确账本**：联邦远端调用、导出、私有上传。精确账本放在 `ops`，与 Egress 的全局美元预算联动。
- **超限响应**：429，附 `Retry-After`，以及 `RateLimit`/`RateLimit-Policy` 头（IETF 草案，⚠ 草案状态）。
- **上游是限速的单位，用户不是**（CP §2.4）：
  - 用户侧配额只用于保证公平；
  - 上游礼貌由 Egress 的全局桶保证，与用户数无关（P-04）。

#### 2.8.5 分页

- **列表**：游标分页。游标为不透明的 base64 串，内容是排序键加 id，再加 HMAC；`limit` 默认 20，最大 100。
- **检索**：检索结果以 `query_id` 快照保存 15 分钟 [判断]，远端流式补齐期间分页结果保持稳定。
- **Deck**：按批块下发，不分页。

#### 2.8.6 版本策略与 OpenAPI 契约

- **主版本**：URI 带主版本 `/api/v2`。v2 内只做增量变更：只加字段和端点，不改语义。
- **破坏性变更**：进入 `/api/v3`，与 v2 并行 ≥180 天 [判断]，期间返回 `Deprecation` 与 `Sunset` 头。
- **客户端兼容**：PWA 与 API 同源同发，兼容压力主要来自独立更新的扩展和 pc-agent。服务端对它们保持 N-1 个版本的兼容，客户端在 User-Agent 中声明所支持的 API 版本。
- **事件契约**：由 06 独立版本化（`schema_version`），与 API 版本解耦。

#### 2.8.7 流式与错误

- **事件名**（按 04 §8.2 统一）：`snapshot`、`upgrade`、`append`、`source_status`、`suggest`、`done`、`error`。每个事件带请求内单调递增的 `seq`，作为 SSE 事件 id，并在发出前追加进 PG 的结果快照；用户已看到的条目不移位（前端以 `cluster_id` 维持位置）。
- **保活与断线续传**：每 15 秒发一次心跳（经 Edge 时关闭响应缓冲）；断线后凭 `Last-Event-ID` 由任一 API 副本从结果快照续传，查询未结束时续传端轮询快照直到 `done`（§2.7(d)）。
- **部分成功是常态**：用 200 加 `missing_sources` 表达，不用 5xx（P-09）。

### 2.9 事件与异步

#### 2.9.1 事务性 outbox

- **写入**：领域写入与 outbox 行放在同一事务。outbox 的逻辑字段为 `id`、`topic`、`key`、`version`、`payload`、`created_at`、`published_at`；`payload` 只放 id，不放内容或 PII（05 §3.4 的 `ops.outbox` 已含 `key` 与 `version`）。写入事务同时 `NOTIFY outbox_new`，relay 被即时唤醒。
- **转发**：outbox relay 把 outbox 行转为队列作业。统一经 outbox，是为了 T2 的 CDC（ClickHouse、外置检索引擎）与多消费者扇出（RT §5.4、§10.4）。relay 用 `FOR UPDATE SKIP LOCKED` 领取，可在 `scheduler` 主备两个实例中同时运行，不构成单点。
- **语义**：至少一次投递，消费者按 `(topic, key, version)` 幂等。可合并的主题（`feedback.received`、`deck.stale`、`channel.changed`）按 `key` 合并：同键作业已在排队时，新行视为已合并。因此这些消费者不能依赖 `payload`，必须从库中读取该键的最新状态。

outbox 转发（设计伪代码）：

```python
# 设计伪代码 —— outbox 转发（procrastinate API 细节实现期核对 ⚠）
async def relay_once() -> int:
    async with db.tx(role="pc_sys_scheduler") as tx:          # 可多实例并行：SKIP LOCKED 保证不重复领取
        rows = await tx.fetch("""SELECT id, topic, key, version, payload FROM ops.outbox
                                 WHERE published_at IS NULL ORDER BY id LIMIT 500
                                 FOR UPDATE SKIP LOCKED""")
        for r in rows:
            try:
                await queue.defer(route(r.topic), args={**r.payload, "_key": r.key, "_v": r.version},
                                  queueing_lock=coalesce_key(r.topic, r.key),   # 只有可合并主题有值，其余为 None
                                  connection=tx)             # 优先与 outbox 同一事务入队（⚠ 核对 procrastinate 是否支持）
            except AlreadyEnqueued:                          # 同键作业已在排队：视为合并成功，不能让整批回滚
                pass
        await tx.execute("UPDATE ops.outbox SET published_at = now() WHERE id = ANY($1)",
                         [r.id for r in rows])
    return len(rows)

async def relay_loop() -> None:                              # 直连 PG：LISTEN 不能走 PgBouncer 事务池
    async for _ in notifications("outbox_new", fallback_poll_s=1.0):
        while await relay_once() == 500:                     # 积压时连续领取，直到清空
            pass
```

未捕获 `AlreadyEnqueued` 时，只要同键作业仍在排队，同一批 outbox 行会反复回滚、永远发不出去，所以上面的捕获是必需的。

#### 2.9.2 领域事件与队列

| 领域事件（outbox topic） | 生产者 | 队列 → 消费者 | 幂等/合并键 | 时延目标 [判断] |
|---|---|---|---|---|
| `watchkey.due`（调度器内部触发） | P6 | `harvest` → P7 | WatchKey 加窗口 | 按调度计划 |
| `raw.batch` | P7 | `ingest` → P8 | 来源 + 批次 id | 分钟级 |
| `corpus.change`（简报 R2-07；载荷见 03 §10.7） | P8（identify 段） | `enrich_meta`、`enrich_embed` → P9；index 段 → P10；`percolate` → P11（按 `index_seq` 水位取已完成 index 的作品，04 §12.1） | `work_id` 加 `version` | enrich p95 ≤10 分钟 |
| `work.candidate`（首次进入候选集） | P4 | `enrich_llm` → P9 | `work_id` 加 prompt 版本 | 批处理：Anthropic 多数 <1 小时，OpenAI ≤24 小时（PU §2.6.6） |
| （enrich 与 index 完成不另设出箱主题；Percolator 以 `work_search.index_seq` 水位为就绪条件） | P9、P10 | — | — | 频道硬命中端到端 p95 ≤30 分钟 |
| （夜间周期任务） | P6 | `rec_nightly` → P4（反向推送规划、多质心重聚类） | 日期 | 次日 06:00 前 ⚠（06 §8.1） |
| `deck.stale` | P11、事件接入 | `deck_build` → P4 | `user_id`（合并） | 下一批块请求之前 |
| `feedback.received` | 事件接入 | `rec_update` → P4 | `user_id`（去抖合并） | 事件到达 → 模型生效 p95 ≤2 秒（01 NFR-9） |
| `channel.changed` | API（同一事务已写 `usr.channel_watch`） | P6 的 WatchKey 对账（`pc_sys_scheduler`，relay 直接调用，不经队列）；`percolate`（按新频道回扫近期论文） | `channel_id`（合并） | 分钟级 |
| `source.drift_detected`、`source.status_changed` | P14 | `maintenance`（策略快照升版、暂停相关 WatchKey）；告警经 P17 | `source_id` | 即时告警；24 小时内完成降级（08 §4.4） |
| `user.export_requested` | API | `export` → 导出打包（`pc_app`，用户上下文） | `request_id` | ≤24 小时（08 AC-V3.12） |
| `user.deletion_requested` | API | `maintenance` → 删除级联（`pc_sys_privacy`，宽限期满后） | `user_id` | 宽限期满后 ≤30 天完成（08 AC-V3.13） |
| `policy.commercial_changed` | Admin | `maintenance`（停收割、清理 NC 派生） | 策略版本 | ≤1 小时 [判断] |
| `notify.requested` | API、各工作者 | `notify` → P17 | 模板 id + 对象 id | 分钟级 |

队列之间是舱壁关系：交互路径不走队列，在进程内执行；各队列有独立的工作者并发，`maintenance` 优先让位。队列到 05 五道舱壁的映射见 §2.5.2。

#### 2.9.3 连接、LISTEN 与流式

- **工作者**：procrastinate 默认用 LISTEN 唤醒工作者（`listen_notify=True`）。PgBouncer 事务池不支持 LISTEN，因此工作者、调度器与 relay **直连 PG** 或走会话池（RT §10.6 核验补充）。
- **API**：API 只做 NOTIFY 与普通事务，NOTIFY 是事务性的，可以走事务池（⚠ 实现期与 PgBouncer 的配置一并核验）。
- **流式**：检索事件由执行检索的 API 进程在同一个 `POST` 响应中推送，并同步追加进 PG 结果快照；续传由任一副本读快照完成，因此不需要跨进程推送（§2.7(d)）。若将来有长时间异步任务（例如深度检索），再评估每个 API 进程保留 1 条直连的 LISTEN 连接，或改用 Valkey pub/sub [判断]。

#### 2.9.4 幂等、顺序与重试

- **至少一次**：所有作业至少执行一次，处理函数必须幂等（沿用 v1 design/05 §1 的"每阶段幂等"纪律）。
- **顺序**：同一 `user_id` 的 `rec_update` 以 lock 串行；同一 `cluster` 的合并以行锁串行；其余作业不保证顺序。
- **作业重试**：作业自身失败按指数退避（full jitter）重试，最多 5 次 [判断]，之后进入死信状态，在 Admin 中可见。上游请求的重试预算由 Egress 单独控制，两者不叠加（RT §9.1）。
- **BLOCKED 语义**：沿用 v1 的 BLOCKED 语义（design/05 §2）。策略拒绝、挑战与 `needs_confirmation` 使作业进入"待人工"状态，不占重试次数、不自动恢复。

#### 2.9.5 周期任务

周期任务由 procrastinate 的周期任务功能调度（RT §10.6），全部经 `scheduler` 单例触发：

| 频率 | 任务 |
|---|---|
| 每日 | 漂移探针；evt 分区维护与冷归档；保留作业与到期的 DSR 执行（05 §5.4、§7） |
| 夜间 | 图 CSR 批算；`rec_nightly`（反向推送规划、多质心重聚类，06 §8.3）；k 匿名聚合与假名化训练抽取（`pc_sys_aggregator`） |
| 每周 | `route_stat` 重算（默认离线跑快照，§2.3.10） |
| 每季 | OpenAlex 快照导入，时间跟随快照发布日（RT §2.2） |
| 每月 | DROPS dblp 快照导入（⚠ DROPS 的下载路径与条款待来源调研确认，RT §2.2） |
| 不排期 | PubMed baseline：NCBI 书面确认之前不导入（HC-31；08 §4.7） |

#### 2.9.6 UI 事件的传输

事件名、字段与语义由 06 定义（简报 §6.5-6）。本文只规定传输：

- 批量 ≤50 条，单批体积 ≤64 KB [判断]；
- 客户端生成 `event_id`（UUIDv7，用于幂等去重），同时带 `client_ts`，服务端补 `server_ts`，时钟偏差由服务端记录；`impression_id` 只由服务端 `uuidv7()` 生成（简报 R2-32）；
- 客户端 IndexedDB 队列上限 5,000 条 [判断]，超过时丢最旧的"非训练类"事件；事件时间取按服务端时间校准的单调时钟；确实超过 7 天未发出的事件会被服务端按分区安全窗口 [now−7 天, now+5 分钟] 拒收（简报 R2-32；05 §3.3.4），客户端在发送前即丢弃；因设备时钟偏差被拒收（`clock_out_of_window`）的事件，按服务端时间校准后换新 id 重发（07 §15.5）；
- 页面隐藏时用 `sendBeacon` 发送，不可用时退化为 `fetch` 加 `keepalive: true`（07 §15.5）。`sendBeacon` 不能设置自定义请求头，所以 `/events` 的 CSRF 令牌放在请求体内，服务端同时校验 `Origin`，并接受以 `text/plain` 承载的 JSON（⚠ 各浏览器行为实现期核验）；
- 事件体中不放 PII：`user_id` 取自会话，不由客户端填写；也不放凭证信息（INV-07）；
- 训练只使用"已绑定本人下发记录"且"客户端报告可见"的事件（AD-04、INV-05）。

### 2.10 技术栈与许可（B-06 白名单与黑名单初稿）

#### 2.10.1 门禁机制

- **核心链路口径**（简报 R2-01，采纳 08 §10.6 的四级：放行 / 评审 / 可选 / 禁止）：放行级为宽松许可族 Apache-2.0、MIT、BSD-2/3、ISC、PostgreSQL、PSF、Blue Oak、Unlicense/CC0、zlib；弱 copyleft（LGPL、MPL-2.0）在"不修改、以库形式动态导入"时列评审级并放行（保留 psycopg 3）；字体 SIL OFL-1.1 作为未修改的静态资源放行（B-06、SI-67）。
- **可插拔项**：NC、AGPL、SSPL、BUSL 组件只能作可插拔项（可选级），默认关闭。
- **单独审查**：模型权重与数据集的许可单独审查。没有 LICENSE 的仓库只能借鉴思路。
- **CI 门禁**：
  - 对 Python 与 JS 依赖做许可扫描，与本节白名单和黑名单比对，黑名单命中即失败；
  - 维护模型与数据注册表（名称、版本、许可、`commercial_ok`、来源 URL、核验日期）。`platform.commercial=true` 时，`commercial_ok=false` 的条目不得加载（AC-V0.13）。
- **弱 copyleft 口径**：已由简报 R2-01 裁定（见上；§8-1 关闭）。

#### 2.10.2 白名单（核心链路默认依赖）

"证据"一列：写明调研章节的，是经调研核验的许可；标"⚠ 调研未覆盖"的，是本文按上游 LICENSE 常识记录，实现期由许可扫描复核。

| 领域 | 组件 | 许可 | 证据 |
|---|---|---|---|
| 运行时与 Web | Python 3.12+；FastAPI；Starlette/Uvicorn；Pydantic v2；httpx | PSF；MIT；BSD-3；MIT；BSD-3 | httpx：RT §9.2；其余 ⚠ 调研未覆盖 |
| 数据库 | PostgreSQL 18；pgvector；pg_textsearch（仅 PG 17/18）；pg_roaringbitmap；pgvectorscale（T1+）；psycopg 3 | PostgreSQL；PostgreSQL；PostgreSQL；Apache-2.0；PostgreSQL；LGPL-3.0-only（评审级放行，不修改、以库形式动态导入，简报 R2-01；08 §10.6） | 综合 §4.4；RT §5、§6.3；PyPI 元数据（08 §10.6） |
| 队列与缓存 | procrastinate（首选）；pgqueuer（备选）；Valkey | MIT；MIT；BSD-3 | RT §10.5–10.6 |
| 稳定性与采集 | tenacity；stamina；aiolimiter；PyrateLimiter；pybreaker；hishel | Apache-2.0；MIT；MIT；MIT；BSD-3；BSD-3 | RT §9.2 |
| robots 与 OAI | protego；sickle | ⚠ 许可待核 | 综合 §4.4 列为复用，未列许可 |
| 实体消解与图 | splink；rustworkx；networkx | MIT；Apache-2.0；BSD-3 | RT §6.1、§7.1 |
| 表示与重排 | sentence-transformers；text-embeddings-inference；gte-large；Qwen3-Embedding/Reranker；FlagEmbedding/BGE-M3；SPECTER2 base | ⚠；⚠；MIT；Apache-2.0；MIT；Apache-2.0（proximity adapter 许可 ⚠ 待核） | 综合 §4.4；SR §2.2.4；RT §4.5 |
| 推荐库 | scikit-learn；implicit；LensKit；River；Vowpal Wabbit（须 ≥9.11.6） | BSD-3；MIT；MIT；BSD-3；BSD-3 | RO §2.4、§3.2 |
| 文档与卡片 | pypdf；pypdfium2；Docling；GROBID（独立服务）；KeyBERT | BSD-3；Apache-2.0/BSD-3；MIT；Apache-2.0；MIT | v1 pyproject（pypdf）；综合 §4.4 |
| 质量闸 | MiniCheck-FT5；HHEM-2.1-Open；AlignScore；SummaC | MIT；Apache-2.0；MIT；Apache-2.0 | PU §2.7 |
| 前端 | React 19.3；Motion 13；Base UI；TanStack Virtual；masonic；KaTeX；pdf.js | pdf.js 为 Apache-2.0，其余 ⚠ | 综合 §4.4（未列许可）；OSS §2.10.5（pdf.js） |
| 密码学 | cryptography：平台用于 RetrievalIntent 与策略包的 Ed25519 签名；pc-agent 用于 AES-GCM 凭证库（D-023） | ⚠ 调研未覆盖（v1 D-023 在用）。平台镜像剔除的是凭证库**模块**（`auth/store.py` 等），不是这个库本身 | D-023 |
| 用户侧 | keyring；Playwright（只打包在 pc-agent 中，personal 部署的服务镜像同样不含） | ⚠；⚠ | ⚠ 调研未覆盖 |
| 认证与序列化 | argon2-cffi；Authlib；orjson | ⚠ 调研未覆盖 | — |
| 导入 | pyzotero（Zotero 导入） | Blue Oak 1.0.0（综合 §4.4）：宽松许可族，R2-01 放行级 | 综合 §4.4 |
| 观测与运维 | OpenTelemetry；Prometheus；Alertmanager；Jaeger；Caddy；PgBouncer；pg_partman；pgBackRest | ⚠ 调研未覆盖；RT 提及 pg_partman 与 PgBouncer，但未列许可。按上游 LICENSE 常识，PgBouncer 为 ISC 许可，属 R2-01 放行级 | — |
| 测试工具（非运行时） | pytest；hypothesis（MPL-2.0，仅开发期，R2-01 评审级）；Locust；schemathesis；oasdiff；import-linter；pgTAP；toxiproxy | ⚠ 调研未覆盖；开发与测试工具单独登记，不进入发行物（08 §10.6） | — |

#### 2.10.3 有条件（可插拔，默认关闭或只在特定档位启用）

| 组件 | 许可 | 条件 | 证据 |
|---|---|---|---|
| Zotero translation-server | AGPL | 独立进程，诚实 UA，只在用户触发时调用，并限速 | 综合 §4.4；OSS §3-17 |
| ParadeDB | AGPL | BM25 的可选替代，需法务评估 | 综合 §2.2；RT §5.2 |
| Qdrant、OpenSearch、Vespa；Apache AGE；ClickHouse | Apache-2.0（Vespa 为 ⚠） | T2 或特定需求；PG 始终是真值源 | RT §5.2、§6.1、§10.4 |
| Gorse | Apache-2.0 | R1 引擎候选；私有反馈隔离 ⚠ 待验证 | RO §2.4 |
| Hatchet、Temporal、absurd、DBOS | MIT；MIT；Apache-2.0；MIT | 长流程或 T2 | RT §10.6 |
| OCR/VLM：olmOCR、DeepSeek-OCR、dots.ocr；Marker/Surya/Chandra、MinerU | 各异，有营收门槛或署名义务 | 须在自有样本上用 olmOCR-Bench 复测；商用门槛逐项核对 | 综合 §4.4；OSS §3-19 |
| MinIO（自托管 S3） | AGPL-3.0（⚠ 调研未覆盖） | 可选对象存储后端；默认用本地盘，或 Apache 许可的替代（SeaweedFS 等，⚠） | — |
| Grafana、Loki、Tempo | AGPL-3.0（⚠ 调研未覆盖） | 只作运维侧外部进程，可选；默认用 Admin Console 内嵌看板 | — |
| ortools | Apache-2.0（⚠） | 06 的最小费用流（硬配额场景） | SR §3.1-14 |
| Expo SDK 57、Reanimated 4、RNGH 3 | — | v2.x 原生端，待留存验证后启动 | UX §2.10 |
| NC 许可的内容与来源：CORE、ORCID 公共 API、J-STAGE、CC BY-NC 内容 | 限非商业 | 受 `platform.commercial` 门控（HC-23） | 综合 §4.4；CP HC-23 |
| NC 许可的系统数据依赖：MSC2020（CC BY-NC-SA） | 可选级 | 不作 TopicNode 默认叶子，作可选插件，任何部署默认不加载；显式开启后仍受 `platform.commercial` 强制关闭（简报 R2-22；08 §3.8） | [NS] §3-11 |
| 第三方 LLM 与嵌入 API | 服务条款 | 只收可共享输入；零保留端点；按地区路由（§2.15） | PU §2.6、CP HC-11/12 |

#### 2.10.4 黑名单（禁止进入默认路径）

| 原因 | 组件 | 证据 |
|---|---|---|
| 许可与 B-06 冲突 | FalkorDB（SSPL）；Memgraph（BSL）；Elasticsearch 的 RRF（仅 Enterprise）；Citus（AGPL）；Redis 8（RSALv2/SSPL/AGPL）；Typesense（GPL）；Meilisearch EE（BUSL） | 综合 §4.4；RT §10.1、§10.5、§13-6 |
| 模型与数据限非商业或受限 | jina-embeddings v3/v5；NV-Embed-v2（CC-BY-NC）；SPLADE 官方权重（NC）；NLLB（CC-BY-NC）；CometKiwi/XCOMET（CC BY-NC-SA）；Dolphin（Qwen 研究许可）；MonkeyOCR v1 权重；Nougat 权重；snap-research/GRID；Hunyuan-MT（地区排除）；YAKE（AGPL）；CSRankings 数据（CC BY-NC-ND）；Scholar Inbox 数据集（CC BY-NC-ND，只可作非商业内部评测） | 综合 §4.4；SR §0-4；PU §2.3 |
| 淘汰或停更 | arq（维护模式）；Kùzu（已归档）；LightFM（不兼容 Py3.12）；use-gesture；vaul；react-tinder-card；paperswithcode-client；science-parse；CERMINE | 综合 §4.4；RT §10.6；UX §2.8 |
| 只借设计、不引入代码 | twitter/the-algorithm、zotero-arxiv-daily（AGPL）；openreview-matcher（没有 LICENSE，按论文自行实现） | 综合 §4.4；RO §3.1-19 |
| 合规红线（与许可无关） | 盗版源及其组件；Google Scholar 自动化与绕封锁组件；冒充 TLS 指纹或伪装 UA 的组件 | 综合 §4.4；CP HC-26 |

### 2.11 容量估算（T1）

**假设**

| 编号 | 假设 | 取值 | 依据 |
|---|---|---|---|
| A-1 | 活跃用户 | 目标 1,000 DAU；按 10,000 做容量设计 | B-04 |
| A-2 | 每 DAU 每日下发卡数 | 下界 25（06 §19.3 的口径）；典型 50（2 批 × 25）；上界 200（RT §10.4 的保守假设；06 §7.7、§7.9 的每日上限为 Deck 默认 25、"再来 10 篇"后总上限 60（简报 R2-42），加探索面 100 ⚠，上界只在放开上限时出现） | 06 §19.3；简报 §5 Deck；RT §10.4 |
| A-3 | 每张卡的 UI 事件数 | 约 3（曝光、决策、停留或展开） | RT §10.4 |
| A-4 | 语料 | 起步 300 万；按 1,000 万设计 | B-04 |
| A-5 | 日新增 | 1–3 万（OpenAlex 同期 article 与 preprint 约 2.3 万/日） | B-04；SR §2.6.6 |
| A-6 | 向量 | 检索用 1024 维 `halfvec`；推荐用 256 维（选型待 Q7） | RT §5.3；SR §3.1-3 |
| A-7 | 检索 | 每 DAU 每日 5 次，其中 15% 需要联邦 ⚠ 设计假设 | SR §2.6.6 用 5 次/日作估算 |

**派生估算** [估算]

| 量 | 1,000 DAU（典型） | 10,000 DAU（上界） | 说明 |
|---|---|---|---|
| UI 事件/日 | 15 万 | 600 万 | 与 RT §10.4 一致（每年约 22 亿） |
| 下发记录/日 | 5 万 | 200 万 | AD-04 |
| evt 年增量 | 约 0.73 亿行 | 约 29 亿行 | 超过 10⁹/年即触发 ClickHouse 评估（简报 §6.3-5）。按 06 §19.3 的默认有限批次口径（每人每日约 80 行），1 万 DAU 约 3×10⁸ 行/年，低于阈值 |
| evt 热数据（可识别形态在 PG 热存 6 个月，按 200 B/行，简报 R2-31） | 约 7.3 GB | 约 290 GB（按 06 §19.3 的有限批次口径约 30 GB） | 其后假名化归档为 Parquet 至第 13 个月；1,000 DAU 目标档不引入 ClickHouse（R2-31） |
| 已见位图 | 约 0.15 GB/年 | 约 1.5 GB/年 | RT §7.2 |
| FeedInbox（按 14 天 TTL） | 约 0.3 GB | 约 2.8 GB | 每用户每日 ≤200 条候选 |
| corpus 元数据 | 300 万 × 约 3 KB ≈ 9 GB | 1,000 万 × 约 3 KB ≈ 30 GB | 原始载荷冷存对象存储 |
| 检索向量与索引 | 300 万约 7 GB | 1,000 万约 23 GB | RT §5.3（⚠ 粗估） |
| 推荐向量（256 维） | 约 1.5 GB | 约 5.1 GB | 可只在时间窗候选池（约 60 天）建索引 |
| BM25 索引 | 约 4 GB | 约 13 GB | RT §5.3 按 FTS5 外推 ⚠ |
| 引文边 | 约 0.9 亿条 | 约 3 亿条，约 30 GB（含两个索引） | RT §6.1；每边约 100 B ⚠ |
| 共享 A 包 | 约 16 GB/年（上界） | 同左（与用户数无关） | 3 万/日 × 1.5 KB |
| PG 合计（热） | 约 45–65 GB | 上界约 420 GB（有限批次口径约 160 GB） | 上列各项相加；不含 WAL 与备份 [估算] |

**吞吐** [估算]

| 路径 | 负载 | 结论 |
|---|---|---|
| 期刊枚举 | 5,000 个 ISSN 各日轮询一次，经 Crossref `/journals/{issn}/works` 单条池；按 5 req/s 起步（RT §9.3），收割道独占时约 17 分钟；交互道占满保底份额时约 33 分钟 | 可行。禁止用列表池（1–3/s）做全局过滤（SI-02）。该端点归单条池是实测行为、官方未承诺（AG §0 第 1 条、§2.2.1），限速器必须按 `x-api-pool` 头动态分桶 ⚠ |
| arXiv | OAI 类目级 set，每日数十次请求，间隔 ≥3 秒 | 可行（HC-06） |
| 联邦 | 10,000 DAU × 5 × 15% ≈ 7,500 次/日。若都打到 OpenAlex search（$1/千次），约 $7.5/日；免费 key 每日 $1，Member 每日 $20（AG §3-16） | **联邦必须限额**，本地索引承担绝大多数检索（AD-12）。1,000 DAU 时约 $0.75/日，也已接近免费额度 |
| 频道硬命中（近线） | 每批新论文对全部频道 AST 倒排匹配 | 10⁵ 级订阅时性能未知（RT §13-11），T1 用 PG 倒排表 |
| 兴趣反向推送（夜间） | 3 万 × 5 万质心 × 256 维 ≈ 0.8 TFLOP | CPU 秒级（06 §19.3 按 2.5 万篇估为 3.2×10¹¹ 次乘加，秒到分钟） |
| 逐事件学习 | 每用户 LR 热启动重训约 10⁵ 次/日（06 §19.3） | 约 1–2 CPU 小时/日 |
| 嵌入 | 日增 3 万篇；回填 300 万篇 | 日增为 CPU 分钟级；回填 CPU 需数天，GPU 需数小时（RO §3.2 ⚠ 未实测） |
| 近线批块预计算 | 每批块 10 张：典型每人每日 5 次，上界 20 次；每次 0.1–0.3 秒 CPU（⚠） | 1 万 DAU 时典型约 4 CPU 小时/日，上界约 17 CPU 小时/日，占 32 vCPU 日算力的 2% 左右 |
| API | 10,000 DAU 上界口径的峰值（按平均的 10 倍）：事件批 35 req/s（600 万事件/日 ÷ 每批 20 条），feed 约 23 req/s（每人每日 20 个批块），检索 6 req/s | 单机充裕，瓶颈在 PG |
| LLM | A 包按 PU §2.6.4 的场景估算：每月 $26–806，与用户数基本无关 | 默认配置须落在 01 NFR-19 的成本目标内（LLM、嵌入与计量 API 合计 ≤US$300/月），即选 PU 场景中的低价模型档 |

结论：

- T1 设计上限档（§2.5.4）能容纳 1,000 万 work 与 1 万用户的数据量。
- 主要风险在三处：evt 行数、联邦预算、CPU 上的重排时延（§8-4）。
- 三者分别由以下手段对冲：热冷分层与 T2 的 ClickHouse、AD-12、重排事件异步化或加 GPU。

### 2.12 失败模式与降级矩阵（P-09）

| # | 失败 | 检测 | 影响 | 降级行为 | 恢复 |
|---|---|---|---|---|---|
| F1 | 某上游 5xx、超时或 429 风暴 | Egress 按"源 × 端点"统计错误率；熔断器 | 该源收割停滞；联邦缺一源 | 熔断打开：连续 5 次失败，或 60 秒内 ≥20 次请求错误率 >50%（RT §9.1 [判断]）；联邦在 `missing_sources` 中标出；走同能力替补链，例如 DOI 元数据按"本地 → Crossref → OpenAlex 单实体 → S2"（RT §3.5.5） | 半开探测间隔 30 秒，指数增至 30 分钟 |
| F2 | 挑战页或风控 | `ChallengeDetector` | 该源在该主机不可用 | 立即停止，冷却 24 小时；来源降级为仅元数据或仅外链；告警；**不重试、不求解**（HC-26） | 人工复核后解除 |
| F3 | robots、ToS 或 tdmrep 漂移 | Drift Probes 的哈希比对 | 继续访问可能违规 | 按简报 R2-15 分档：robots 与 TDM 信号漂移立即降级；ToS 哈希变化宽限 7 天后降为 on_demand 并标 `needs_confirmation`；元数据通道自身受影响时暂停并切换替补链（SI-12） | Admin 复核 |
| F4 | Egress 宕机 | 健康检查；调用超时 | 所有平台出站停止，含 OIDC 登录、ORCID/Zotero 导入与外发通知 | 检索只返回本地结果，`missing_sources` 为全部远端源；收割作业积压但不丢；Feed 不受影响；已登录会话照常，新的第三方登录与导入提示稍后重试；通知排队 | 重启后积压自动消化 |
| F5 | OpenAlex 美元预算耗尽 | 美元账本 | 计量调用不可用 | 路由剔除 OpenAlex，改用快照、本地与替补链 | 次日额度恢复；评估 Q3 |
| F6 | LLM 提供方故障或超预算 | `enrich_llm` 错误率；美元账本 | 新 A 包暂停 | 卡片只显示取源字段。TL;DR 按"S2 TLDR（CS/生医，署名）→ A 类摘要首句 → 隐藏"降级；why-this 本就以模板为默认 | 批次重提 |
| F7 | 嵌入积压或推理服务故障 | 队列龄；健康检查 | 新论文暂无向量；查询嵌入与重排不可用 | 推理服务故障：检索降为纯 BM25（没有查询嵌入就没有 ANN，也就没有 RRF），跳过重排；Deck 召回改用已存的用户质心、BM25、主题与频道匹配。嵌入积压：新论文暂时只经 BM25 召回，RRF 照常 | 积压消化后自动补齐 |
| F8 | Rec 近线故障或超时 | `deck_build` 与 `rec_update` 的队列龄 | 没有预计算批块；画像更新滞后 | 在线候选管线照常（用最近一次的用户态）；在线管线也失败时走快路径（150 ms），再失败才用非个性化批块，标 `mode=non_personalized`（与 HC-13 的非个性化模式同源） | 队列恢复后自动追平 |
| F9 | Percolator 滞后 | `corpus.change` 到 FeedInbox 的时延（按 `index_seq` 水位） | 新论文推送变慢 | Deck 仍可由时间窗候选池的 ANN 与频道本地查询召回 | 追平 |
| F10 | PG 主库宕机 | 连接失败 | T1 单机即全站写不可用（已接受的 SPOF，见 §9） | PWA 仍可阅读缓存的当前批次，事件留在 IndexedDB 待重放（幂等） | PITR 或重启；RTO ≤4 小时（01 NFR-27） |
| F11 | Valkey 缺失或宕机 | 连接失败 | 缓存未命中 | 回退到 PG；限速退回进程内近似值 | — |
| F12 | 对象存储不可用 | 健康检查 | 私有上传与共享 OA 资产不可用 | 私有 PDF 留在本机稍后重试；共享 OA 回到原始链接 | — |
| F13 | 队列积压 | 各队列的深度与最老作业龄 | 近线变慢 | `maintenance` 先让位；交互路径不经队列，不受影响 | 扩并发 |
| F14 | 用户未安装扩展或扩展失败 | 能力探测 | 无法在用户侧取回 | 平台默认"在出版社打开"外链（P-03） | — |
| F15 | 策略快照过期或损坏 | 快照版本与时效 | 裁决不可信 | Egress 按"失败即关闭"处理：快照不可信期间拒绝一切新的出站请求，只返回缓存命中；例外是 `policy_probe`（robots.txt、ToS 页、tdmrep），它们只按 robots 判定，经桶限速并记 FetchLog，否则快照无法重建 | 由 registry 与探针结果重建快照 |
| F16 | LLM 查询解析不可用，或未部署自托管模型 | 超时；配置 | 没有解析建议 | 只用规则快路径；首屏本来就不依赖它 | — |
| F17 | scheduler 主实例宕机 | 选主锁丢失；outbox 最老未发布行龄 | 调度与周期任务暂停 | 备实例经 advisory lock 接管；relay 两实例本就并行，outbox 不积压；Feed、检索与事件接入不受影响 | 接管后补跑错过的周期任务（幂等） |
| F18 | 通知服务（邮件、Web Push）不可用 | `notify` 队列错误率 | 验证邮件、口令重置、digest 延迟 | 作业按退避重试，账号类邮件优先；digest 过期即丢弃，不补发 | 服务恢复后自动发送 |

### 2.13 可观测性

**结构化日志**

- JSON 行，公共字段：`ts, level, service, trace_id, span_id, request_id, route, source, host, lane, status, error_class, latency_ms`。
- 用户以 `user_ref` 表示，即 HMAC(user_id, 轮换密钥) 的假名，不写原始 id。
- 查询文本只记规范化哈希，原文只保存在 `evt` 的检索日志中，归属用户、受留存矩阵约束。
- 脱敏规则沿用 v1 `sensitive.py` 的单一来源（D-025）；扩展与 PWA 用生成的同一份规则。
- 留存：应用日志热存 30 天；安全审计与 FetchLog ≥6 个月（HC-14），之后归档。

**指标**（前缀 `pc_`，OTel 与 Prometheus）

| 类别 | 指标 |
|---|---|
| API | 各路由的 RED（请求率、错误率、时延分布） |
| Feed | `deck_next` 延迟；预计算命中率；在线管线与快路径的占比；非个性化回退率 |
| 检索 | 首个 `local` 事件延迟；`done` 延迟；缺失来源率 |
| Egress | 每个桶键的令牌余量与等待；429 与挑战计数；熔断状态；重试预算占用；缓存命中；各源美元消耗；各路由的请求数与 FetchLog 行数对账（INV-10） |
| 队列 | 各队列的深度与最老作业龄 |
| 新鲜度 | 各 WatchKey 与各来源从发布到可见的滞后；percolate 时延 |
| enrich | 积压；LLM 的 token 与美元；三道闸的通过率 |
| 事件 | 接收率；`unbound` 率；重复率；时钟偏差拒收率；事件到达 → 模型生效延迟 |
| 通知 | 各模板的发送量、失败率与排队时长 |
| 合规 | 策略拒绝数（按原因）；漂移告警数 |

北极星与护栏指标属于**产品分析**，由 `pc_sys_metrics` 批处理从 `evt` 计算（含 VR-strict 诊断口径，并排除本人认领作品、单次批量导出 >5 篇与匿名会话，简报 R2-44；05 §3.3.5），输出切片 ≥`k_show` 的聚合结果，在 Admin 中展示，不混入运维指标。

**追踪**

- OTel 按 W3C `traceparent` 贯穿 API、推理服务、Egress 与 PG。
- 投递作业时把 trace 上下文写入作业参数，使工作者的 span 能接到原链路。
- 联邦 fan-out 每个来源一个子 span，只带 `source` 属性，不带用户信息。
- 采样：头部 10%；错误与慢请求 100% 保留（Collector 做尾部采样）[判断]。

**SLO（T1 设计目标）**

| SLI | 目标 | 窗口 | 依据 |
|---|---|---|---|
| 下一批卡片延迟 | p95 ≤300 ms | 滚动 28 天 | 简报 §3；01 NFR-9 |
| 本地检索端到端（含融合与重排） | p95 ≤800 ms；先发 RRF 的降级占比 ≤5% | 28 天 | 简报 §3；01 NFR-10 |
| 联邦完成 | ≥99% 的请求在 3.2 秒内收到 `done`（截止 3 秒加 0.2 秒余量） | 28 天 | 简报 §3；01 NFR-10 |
| 滑动到下一张可交互 | ≤100 ms；INP p75 ≤200 ms | RUM | 简报 §3；UX §3-17；01 NFR-9 |
| 事件接收成功率 | ≥99.9%（不计 4xx） | 28 天 | [判断] |
| API 可用性 | ≥99.5%/月（T1 单机） | 月 | [判断]，待确认（§9） |
| 事件生效 | 事件到达 → 每用户模型生效 p95 ≤2 秒 | 7 天 | 01 NFR-9；06 §8.1 |
| percolate 时延（频道硬命中） | p95 ≤30 分钟 | 7 天 | [判断] |
| 新鲜度 | arXiv 等日历型源：公告后 ≤6 小时完成收割并进入 FeedInbox；Crossref、Europe PMC 等增量源 ≤24 小时 | 7 天 | 01 NFR-12（草案口径），由 03 与 04 定稿 |
| 礼貌 | 违例 0 次：arXiv 间隔 <3 秒、robots 禁区请求、超过书面限额 | 持续 | HC-06、HC-10；AC-0.5；01 NFR-14 |
| 隐私 | RLS 越权 0 次；私有到共享的流 0 次 | CI 与月度审计 | HC-01；01 NFR-15 |

**错误预算与告警**

- 错误预算：7 天内烧掉超过 50%，就冻结高风险发布。
- 告警分级：
  - **最高级**：礼貌违例、挑战页与隐私违例。这三类是合规事件，不适用错误预算；
  - **警告级**：漂移告警、美元预算达到 80%、队列龄超阈值。

### 2.14 安全边界概要（细节见 08）

| 信任区 | 内容 | 主要控制 |
|---|---|---|
| Z0 用户设备 | PWA、扩展、pc-agent；用户级凭证；本机 PDF | 凭证库在端侧（AES-GCM，D-023）；扩展验签 RetrievalIntent 与策略包；来源白名单；端侧限速；pc-agent 的 localhost 接口要求令牌，并做 Host 与 Origin 校验 |
| Z1 边缘 | Edge | TLS；安全头与 CSP；按 IP 粗限速；出站只到 ACME 证书端点（宿主机防火墙） |
| Z2 应用 | API 与工作者 | 没有公网路由（INV-03）；会话与 CSRF；PKCE 作用域；输入校验；最小权限 DB 角色 |
| Z3 数据 | PG、对象存储、Valkey | 只在内网；RLS；私有前缀的签名 URL；静态加密（磁盘或对象存储层）[判断] |
| Z4 出站 | Egress | 四类路由各自的主机白名单；SSRF 校验每跳重做（08 §10.3）；部署级密钥只在这里注入，存于 docker secrets 或权限 0600 的文件，外部 KMS 可选；`data_class` 闸；FetchLog |
| Z5 管理面 | Admin Console、`api-admin` | 只在内网；MFA；四眼复核；只追加的审计日志 |

**主要威胁与对策**（线索，完整威胁模型由 08 给出）

| 威胁 | 对策 |
|---|---|
| 跨用户泄露 | RLS；受限视图；不跨用户去重；k 匿名 |
| 凭证外泄 | 平台不持有用户级凭证 |
| SSRF 与抓取范围蔓延 | Egress 主机白名单；逐跳重定向校验与固定 DNS 解析；`oa_host` 自动登记只限许可放行的 OA 全文，登记与撤销留审计 |
| 通知通道被滥用（发垃圾邮件、泄露内容） | 模板化正文、不含私有内容；按用户与全局限速；通知白名单只含部署配置的服务端点 |
| 扩展被滥用 | 签名意图；单篇；端侧配额 |
| 私有内容经 LLM 出境 | `data_class` 闸 |
| 管理面被攻破 | MFA；内网；四眼复核 |
| 供应链 | 许可扫描与漏洞扫描 |
| 机构级封禁（RK-01） | 用户侧执行；端侧限速 |

### 2.15 架构参数

| 参数 | 取值 | 默认 | 作用 | 生效机制 |
|---|---|---|---|---|
| `deployment.mode` | `platform` \| `personal` | —（安装时定） | 服务编排与账号模式（§2.5.1） | compose profile 与配置 |
| `deployment.host_is_user_device` | bool | false | 是否允许本机 pc-agent 执行 `exec_side=user` 通道（§2.4） | 放置器 |
| `platform.commercial` | bool | **false**（默认假设，Q1） | 为 true 时的动作： ① 停用 `commercial_ok=false` 的来源，如 CORE、ORCID 公共 API、J-STAGE（HC-23）；② 取消 NC 内容的共享，NC 派生的共享工件下架；③ 在用户侧策略包中关闭 Elsevier、Wiley、SN、T&F 的 TDM 流程，除非另签商业许可（CP DI-07）；④ 模型与数据注册表中 `commercial_ok=false` 的条目不得加载。注意：NC 许可的系统数据依赖（如 MSC2020）在任何部署都默认不加载（简报 R2-22、08 §10.6），④ 只是在曾被显式开启时强制关闭 | 策略引擎、权利引擎、注册表 |
| `region` | `global` \| `cn` | **global**（默认假设，Q2） | 为 `cn` 时：LLM 只路由到已备案或自托管模型，并公示模型名与备案号（HC-12）；个人信息境内存储（HC-22）；公开评论、个性化与 LLM 须等备案与登记完成才能开启（HC-21）；备案材料可导出（HC-14） | 部署单元级，**不在运行期切换** |
| `features.public_ugc` | bool | false | 公开评论与评分（V6，HC-15） | 特性开关 |
| `features.r2r_matching` | bool | false | 研究者↔研究者匹配。平台总开关，用户还须单独同意并声明年满 18 岁 ⚠；撤回后 ≤1 分钟停止展示、≤24 小时删除匹配资料（HC-18、Q5；简报 R2-46） | 特性开关加同意 |
| `features.public_lists` | bool | false | 公开收藏列表（U1 可选；08 §8.1、§6.5；07 S-12 只在开启时渲染） | 特性开关 |
| `features.private_enrich_platform` | bool | false | 平台的私有增益道（AD-13） | 特性开关，另受出版商白名单约束 |
| `features.oa_shared_cache` | bool | true [判断] | 许可白名单内 OA 全文与图的共享缓存；关闭时不自动登记 `oa_host`，`enrich_fulltext` 停用 | 特性开关 |
| `features.private_pdf_sync` | bool | false（简报 R2-27；LQ-15） | 私有 PDF 的端到端密文多设备同步（§2.4）；服务端只存密文、不可解密 | 特性开关 |
| `federation.user_daily_cap`、`federation.global_daily_usd` | int、float | 30、1.0 ⚠ | 联邦配额（AD-12） | API 账本与 Egress 美元桶 |
| `llm.providers` | 按 `region` 与 `data_class` 的列表 | 空，此时 LLM 功能关闭 | 模型路由（08 §9.4）；列表中没有自托管端点时，含个人数据的 LLM 功能（查询解析、画像摘要、懒生成解释、每日 top-K 重排）一律关闭 | 调用方共享的路由库与 Egress |
| `notify.channels` | `email`、`web_push` 的端点与凭证引用 | 只有 `email`；Web Push 关闭 | Notifier 可用的外发通道（§2.3.17） | Egress `notification` 路由 |

**`platform.commercial` 的切换流程**

1. Admin 生成预检报告，列出将停用的来源、将下架的共享工件与将关闭的用户侧流程。
2. 四眼复核。
3. 策略快照版本号递增；调度器停止相关 WatchKey。
4. 清理作业下架 NC 派生的共享工件：TL;DR、翻译、图、缓存的 NC OA 全文。
5. 生成校验报告，要求残留为 0。
6. 写审计日志。

反向切换（true → false）只需重新启用，派生物懒生成即可。

**`region` 的规则**

- `region` 在创建部署单元时确定。
- 改变 `region` 等于新建部署单元，并在用户同意后迁移用户数据（CP DI-09、HC-22）。

---

## 3. 测试方法

默认离线（AGENTS.md）：

- 单元、契约与集成测试都用 fixture 回放上游，沿用 v1 的 fixture 回放体系；
- 在线冒烟需显式运行，如 `make smoke`；
- 浏览器与扩展测试受 `PC_BROWSER_TESTS` 门控。

| # | 关注点 | 方法 |
|---|---|---|
| 1 | 分层与边界 | **架构适应度函数**：用 import-linter 类工具（⚠ 许可待核）断言依赖只向下，且平台包不得导入用户侧包（`auth.providers`、`auth.store`、`auth.browser`、`browserfetch`）；构建平台镜像后，断言打包清单中没有这些模块，并对每个经 `v1_bridge` 包装的 v1 adapter 在平台镜像中做导入冒烟（例如 v1 `ssrn/adapter.py` 顶层导入 `browserfetch`，不得被包装）（AC-V0.17） |
| 2 | 出站唯一性 | 在 compose 集成环境的 egress 网络上放一台 fake 外部服务。从每个非 egress 容器发起连接，期望全部失败；Edge 只能连到 fake ACME 端点；从 egress 发起，期望成功。另验证 OIDC 换令牌、导入与通知都只经 Egress 的对应路由（AC-V0.15、AC-V3.22） |
| 3 | 礼貌与合规 | 回放上游 fixture：robots（含 `Disallow: /` 的文档化 API 主机）、429、伪 200 "Rate exceeded."、挑战页四类、限流响应头、重定向到未登记主机或内网地址。对 FetchLog 断言以下各项：请求间隔、并发、先读 robots、同主机不对冲、重试预算、熔断状态机、R5 类主机的按需调用放行与后台批量拒绝、每次尝试恰有一行（AC-V0.16、AC-V1.5、AC-V1.1、AC-V1.2、AC-V1.3、AC-V0.18、AC-V1.6）。桶键的上游请求类用"同一上游的两类内部流量并发压测"验证不会拆桶翻倍 |
| 4 | 降级矩阵 | **故障注入**：用代理或 fake upstream 注入延迟尖峰、5xx 与 429；逐个停止 egress、推理服务、`worker-rec`、scheduler 主实例、Valkey、对象存储与通知端点；逐行验证 §2.12 的降级行为 F1–F18（AC-V4.1、AC-V2.32） |
| 5 | 契约 | OpenAPI 生成快照；破坏性变更检测（oasdiff 类工具）；基于契约的属性测试（schemathesis 类工具），要求没有 5xx；事件 JSON Schema（06）；RetrievalIntent 与策略包的验签测试，与 08 的意图签名 AC 同向（AC-V0.19） |
| 6 | 数据平面安全 | pgTAP 类工具覆盖越权的读、写与删；授权矩阵快照测试，要求没有"读 usr 且写 corpus"的角色；数据流测试：注入标记过的私有资产，确认其派生物不出现在 `corpus` 与共享缓存中（AC-V3.7、AC-V3.5） |
| 7 | 事件语义 | 重放同一批次（含跨月边界的重试），确认无重复；构造未绑定的事件，确认被标记且不进训练视图；注入 outbox 重复投递、同键作业已在排队（`AlreadyEnqueued`）、relay 双实例并发与工作者崩溃，确认结果集合与期望一致且 outbox 不卡死（AC-V3.9、AC-V4.4、AC-V2.45）；测量事件到达 → 模型生效的延迟分布（AC-V4.34） |
| 8 | 性能与容量 | 在 T1 参考机上用 Locust 类工具模拟 1,000 与 10,000 用户（feed、事件、检索）；数据集用自有 300 万语料快照与 04 的查询集；按 RT §12-24 报告 p50/p95/p99、建索引时间与常驻内存（AC-V4.33、AC-V2.46、AC-V4.14） |
| 9 | 端到端 | 用 Playwright 驱动 PWA 主流程：取批次 → 滑动 → 事件 → 下一批，以及切到非个性化模式；扩展流程受 `PC_BROWSER_TESTS` 门控 |
| 10 | 开关 | 在测试部署中切换 `platform.commercial` 与 `region`，比对预检报告与校验报告（AC-V1.13、AC-V1.14） |
| 11 | 迁移与灾备 | v1 fixture 库做 ETL 比对（AC-V3.29）；季度 PITR 恢复演练（AC-V3.27） |
| 12 | 许可与漏洞 | CI 对依赖做许可扫描与漏洞扫描；校验模型与数据注册表（AC-V0.13） |
| 13 | 多副本流式检索 | API 起 3 个副本，经 Edge 发起流式检索，随机切断连接并让续传落到其他副本；断言事件序列完整、无重复、`done` 必达（AC-V2.34） |
| 14 | 本地只读路径 | 回放卡片流、频道预览与 LATEST 查询的负载，Egress 审计中由这三类请求触发的远端调用为 0（AC-V2.14） |
| 15 | 通知路由 | fake SMTP 与 fake Web Push 端点：断言正文只来自模板、不含私有字段，日志不含正文（AC-V3.22） |

## 4. 测试类型

| 类型 | 范围 | 环境 | 门禁 | 频率 |
|---|---|---|---|---|
| 单元 | 纯函数：桶键构造、策略裁决、放置器、游标签名、降级选择、SSE 组装 | 本地 / CI | `make check` | 每次提交 |
| 契约 | OpenAPI、事件 schema、Connector 契约（沿用 v1 的参数化契约测试）、签名对象 | CI | `make check` | 每次提交 |
| 集成（compose） | 网络隔离、outbox → 队列、RLS 与授权、降级、Egress 行为 | CI（docker） | 合并前 | 每个 PR，重型项夜间跑 |
| 端到端 | PWA 主流程；扩展（门控） | CI 夜间 / 手动 | 发布前 | 夜间 |
| 性能与容量 | 1,000 / 10,000 用户模拟；索引构建 | T1 参考机 | 里程碑门禁 | 每个里程碑 |
| 故障注入与混沌 | 降级矩阵 F1–F18 | staging | 里程碑门禁 | 每个里程碑，另每季度一次 |
| 合规审计 | FetchLog 礼貌审计、数据流、许可扫描 | CI 加月度 | 相关 AC | 持续 |
| 安全 | 越权、SSRF、依赖漏洞、管理面 | CI 加季度 | 发布前 | 季度 |
| 迁移与灾备 | v1 ETL、PITR | staging | 对应里程碑 | 一次，另每季度演练 |

## 5. 验收标准（草案）

编号已由 [09](09-roadmap-and-milestones.md) 统一改为正式编号 `AC-V<m>.<n>`，编号中的 `V<m>` 即正式归属的里程碑（新旧对照见 09 附录 A）。"建议里程碑"列保留起草时供 09 参考的建议，与正式归属不同时以编号为准（09 §4.4）。

| 编号 | 验收标准（可度量） | 验证方法 | 建议里程碑 |
|---|---|---|---|
| AC-V0.14 | 同一镜像：在 T1 参考机上以 `--profile platform` 启动，在 4 vCPU/16 GB 机器上以 `--profile personal` 启动，全部核心服务的 `readyz` 都在 10 分钟内变绿；两种形态的平台服务镜像 digest 相同（pc-agent 是独立安装包，不计入） | 部署脚本 + 健康检查 | V0 |
| AC-V0.15 | 从 egress 与 edge 以外的每个容器连接公网测试端点，成功 0 次；edge 只能连到 ACME 测试端点，连其他地址成功 0 次；从 egress 连接可达。每次构建都执行 | compose 集成测试 | V0 |
| AC-V0.16 | Egress 拒绝所有发往未登记主机的请求（含重定向到未登记主机），拒绝率 100% | 集成测试 | V0 |
| AC-V1.5 | 回放 ≥50 个 fixture 主机：每个主机的首个请求之前都有 robots 快照读取；发往 Disallow 路径的请求为 0（与 AC-0.5 同向） | FetchLog 断言 | V0–V1 |
| AC-V1.1 | 20 个并发调用方（混合交互、收割与 enrich 三道）回放 24 小时：arXiv 相邻请求间隔 ≥3 秒且单连接，违例 0 次；其他来源每个桶键的实际速率 ≤配置值 +5%（沿用 AC-1.4 口径），且按 (source, host) 合计的速率不超过书面限额 | FetchLog 审计 | V1 |
| AC-V1.2 | 注入 429 风暴时：单请求尝试次数 ≤3；每源 2 分钟窗口内重试占比 ≤10%；同一逻辑请求对同一主机的并发副本为 0 | 故障注入 | V1 |
| AC-V1.3 | 满足"连续 5 次失败，或 60 秒内 ≥20 次请求错误率 >50%"时熔断打开。挑战 fixture（四类）命中后，该源在该主机冷却 24 小时，其后请求为 0，告警恰好 1 条 | 故障注入 | V1 |
| AC-V0.17 | 平台服务镜像（含 personal 部署的服务端容器）中不存在用户级 AuthProvider、凭证库与 `browserfetch` 模块，也不可导入；向 Egress 提交 `exec_side=user` 通道请求，拒绝率 100%；放置器对非"显式单篇"的用户侧作业拒绝率 100% | 打包清单 + 单元与集成测试 | V0 |
| AC-V3.7 | DB 授权快照中没有"可读 usr 且可写 corpus"的角色；数据流测试中，私有资产派生物出现在 `corpus` 或共享缓存中的次数为 0；服务端不存私有文件的明文哈希，私有对象只有密文 | 授权快照 + 数据流测试 | V0 |
| AC-V3.5 | pgTAP 类套件覆盖 `usr` 全部表的越权读、写与删，通过率 100%；应用角色都不是 owner，也没有 BYPASSRLS（系统目录断言） | pgTAP | V0 |
| AC-V4.33 | 10,000 模拟用户（T1 参考机）：`GET /feed/deck/next` 全部请求的 p95 ≤300 ms、p99 ≤600 ms，不以预计算命中为前提；另报告预计算命中率（目标 ≥90% [判断]）与在线管线路径单独的 p95 | 压测 | 卡片流 MVP 里程碑 |
| AC-V4.1 | ① 停止 `worker-rec`：feed 仍返回 200 且保持个性化（在线管线或快路径），p95 ≤300 ms；② 注入"全部个性化组件失败"：feed 返回 200，标 `mode=non_personalized`，p95 ≤300 ms；恢复后在 1 个 `deck_build` 周期内回到个性化；③ 用户关闭个性化后，下一次批块请求即生效 | 故障注入 + 端到端 | 卡片流 MVP 里程碑 |
| AC-V2.46 | 300 万 work 语料，用 04 的在线查询集：本地检索端到端（含 RRF 与重排）p95 ≤800 ms（01 NFR-10）；因重排超预算而先发 RRF 结果的请求占比 ≤5% | 压测 | V1 |
| AC-V2.32 | ≥99% 的联邦请求在 3.2 秒内收到 `done`，超时来源列入 `missing_sources`；停掉 Egress 时检索仍返回本地结果，`missing_sources` 为全部远端来源 | 压测 + 故障注入 | V1 |
| AC-V2.36 | 用户超出联邦日配额后远端调用为 0，响应带 `budget_exhausted`；全局美元账本不超过配置上限 | 集成测试 | V1 |
| AC-V3.9 | 同一批事件（相同 `event_id`）重复提交，新增 0 行；未绑定本人下发记录的事件 100% 标为 `unbound`，且不进入训练视图 | 集成测试 | 卡片流 MVP 里程碑 |
| AC-V4.4 | 提交"不感兴趣 + 原因"后，同一会话的下一批中，同一原因所指目标（主题、作者或 venue）的命中数为 0 | 端到端 | 卡片流 MVP 里程碑 |
| AC-V2.45 | 注入 outbox 重复投递、`AlreadyEnqueued`、relay 双实例并发与工作者崩溃：`corpus.change` 处理后 FeedInbox 与期望集合完全一致（按 `work_id` 去重后无重复、无丢失）；outbox 最老未发布行龄 ≤60 秒 | 故障注入 | V1 |
| AC-V4.14 | 在日新增 3 万、1 万用户的模拟下，频道硬命中从 `corpus.change` 写出到写入 FeedInbox 的 p95 ≤30 分钟；夜间反向推送在次日 06:00 前完成 ⚠ | 压测 | 卡片流 MVP 里程碑 |
| AC-V3.17 | 扩展与 pc-agent 的全部上报请求体都通过 schema 校验；模糊测试 1 万例中，出现 Cookie、令牌或 PDF 字节形态的次数为 0（沿用 AC-0.4 正则） | 契约测试 + 模糊测试 | 用户侧取回里程碑 |
| AC-V4.25 | 公共热度、社会证明与他人 why-this 的计算输入中，`open_fulltext` 事件数为 0 | 查询审计 | 卡片流 MVP 里程碑 |
| AC-V1.13 | 在测试部署中把 `platform.commercial` 切到 true 后，1 小时内 `commercial_ok=false` 来源的 WatchKey 全部停止；NC 派生共享工件的残留为 0（以校验报告为准）；全程有审计记录 | 开关演练 | V0–V1 |
| AC-V1.14 | `region=cn` 测试部署中，Egress 审计显示发往非白名单 LLM 端点的请求为 0；除简报 R2-27 的 personal 本机例外（`host_is_user_device=true`、用户同意、来源派生门允许，08 §9.5）外，任何部署中 `data_class≠shareable` 的请求发往第三方 LLM 的次数为 0 | 开关演练 + 审计 | V1 |
| AC-V0.19 | OpenAPI 3.1 文档随构建生成并提交；v2 内破坏性变更为 0（oasdiff 类工具）；基于契约的属性测试对全部端点无 5xx | CI | V0 起持续 |
| AC-V0.20 | 抽样 1,000 个请求，trace 从 API 经队列贯通到工作者的比例 ≥99%；日志脱敏扫描命中为 0（AC-0.4） | 观测测试 | V0 |
| AC-V3.27 | PITR 演练：RPO ≤5 分钟，RTO ≤4 小时（01 NFR-27；T1 参考机，每季度）；恢复后 RLS 套件与私有资产可用性检查全部通过 | 灾备演练 | V1 |
| AC-V3.29 | v1 fixture 库导入后：行数一致；标识符唯一性 100%；订阅转频道逐条比对无丢失 | ETL 测试 | V0–V1 |
| AC-V0.13 | CI 许可扫描的黑名单命中为 0；`platform.commercial=true` 时，注册表中 `commercial_ok=false` 的模型与数据不被加载 | CI | V0 起持续 |
| AC-V0.18 | 故障注入回放（策略拒绝、robots 拒绝、429 重试、挑战、超时、重定向）中，Egress 收到的每次出站尝试在 FetchLog 中恰有一行，行数与请求数对账差为 0；任一主机的首个请求之前都有 robots 判定记录（与 08 AC-0.12 同向） | FetchLog 审计 | V0–V1 |
| AC-V4.34 | 1 万模拟用户的事件负载下，事件到达 → 每用户模型生效的 p95 ≤2 秒（01 NFR-9）；强负反馈后的下一次批块请求中，被屏蔽目标的命中为 0 | 压测 + 端到端 | 卡片流 MVP 里程碑 |
| AC-V2.34 | API ≥2 个副本、流式检索中途断线并让续传随机落到其他副本：客户端收到的事件序列完整、无重复（按 `Last-Event-ID`），`done` 必达 | 集成测试 | V1 |
| AC-V2.14 | 卡片流、频道预览与 LATEST 查询触发的远端调用为 0（Egress 审计按调用来源统计；与 01 FR-36 同向） | 集成测试 + 审计 | V1 |
| AC-V1.6 | 08 §4.2 R5 类通道（如 E-utilities、pub.orcid.org）：`ON_DEMAND` 调用在书面限额内放行，`BACKGROUND_BATCH` 调用拒绝率 100%；R3 类主机（robots 不可读）除 robots.txt 探针外的请求为 0；挑战冷却期内对该主机的请求为 0 | 集成测试 | V1 |
| AC-V3.22 | OIDC 换令牌、ORCID/Zotero 导入、邮件与 Web Push 的出站 100% 经 Egress 对应路由；通知请求体只来自模板，私有字段（笔记、私有全文、他人信息）出现 0 次；通知日志不含正文 | 集成测试 + 审计 | V0–V1 |

---

## 6. 与 v1 的关系与迁移

### 6.1 定位

- **v1 冻结**：v1 CLI 与 SQLite 实现进入维护冻结，只修缺陷（B-03）。
- **v1 代码的新角色**：`src/paper_crawler` 的纯函数与协议件作为 v2 的共享库；v1 adapter 经 `v1_bridge` 包装复用，不重写；auth 框架只用在用户侧。
- **包布局**（设计建议，最终由 09 定）：
  - 沿用单一发行包 `paper-crawler`；
  - 新增子包：`paper_crawler.core`（共享件）、`paper_crawler.platform.*`（api、workers、egress、policy、rec、feed、router、notifier）、`paper_crawler.connectors.*`（家族与 `v1_bridge`）、`paper_crawler.agent`（用户侧）；
  - v1 模块保持原路径；
  - extras 分为 `[platform]`、`[agent]`、`[auth]`、`[auth-browser]`，**平台镜像不安装 `[agent]`、`[auth]`、`[auth-browser]`**（INV-02、INV-07）。这延续 AGENTS.md 中"核心依赖与可选认证/浏览器依赖分离、保持惰性导入"的约束。v1 的 `[auth]` 含 `cryptography` 与 `keyring`（pyproject）；平台签发 RetrievalIntent 与策略包要用 Ed25519，所以 `cryptography` 须同时列入 `[platform]`，`keyring` 不列入。
  - extras 只管依赖，不管源码文件。因此用户侧代码还要在打包时与平台分离，范围是 v1 `auth/` 中的 `store`、`manager`、`providers`、`browser`、`cli`，以及 `browserfetch.py` 与 `paper_crawler.agent`；`auth/challenge.py` 不在此列，Egress 要复用它。分离方式二选一：拆为独立发行包（如 `paper-crawler-agent`），或在平台镜像构建时剔除，由 09 选定。AC-V0.17 只验收结果：平台镜像中这些模块不可导入。

### 6.2 v1 模块复用映射表

去向四类：

- **复用**：原样作为共享库；
- **包装**：经 `v1_bridge` 或适配层接入 v2；
- **改造**：保留语义，重写或扩展；
- **冻结**：只供 v1 CLI 使用，v2 不调用。

| v1 模块 | 现状职责 | v2 去向 | 说明 |
|---|---|---|---|
| `ids.py` | DOI 与标题规范化（纯函数） | **复用** | Ingestor 的 normalize 直接调用 |
| `errors.py` | `ErrorClass` 分类学与重试表 | **复用 + 扩展** | 增加 `policy_denied`、`budget_exhausted`、`deadline_exceeded`；重试改由 Egress 的重试预算控制 |
| `sensitive.py` | 敏感键名的单一来源 | **复用** | 平台日志脱敏；生成给扩展与 PWA 用的同一份规则 |
| `useragent.py` | D-014 UA 组装 | **改造（小）** | 平台部署的用途字段改为部署身份（§2.3.13）；personal 部署保留个人口径 |
| `adapters/_oai.py` | OAI-PMH 信封层 | **复用** | 作为 `oai_pmh` 家族的基底 |
| `subs/watermark.py` | `DateUpperBound`、`DateCursor`、`IdSetDiff`，推进与提交分离 | **复用（核心语义）** | WatchKey 游标沿用"重叠窗口 + 标识符去重"。OSS §2.13-3 指出这一机制没有开源对标，是价值最高的复用件 |
| `pipeline/fetchio.py` | `.part` 暂存、魔数校验、原子落位 | **复用** | 私有上传校验、pc-agent 落盘、共享 OA 缓存写入 |
| `auth/challenge.py` | `ChallengeDetector` 特征库 | **复用** | Egress 与 pc-agent 直接使用；扩展由同一特征数据生成 |
| `adapter.py`、`types.py` | `SourceAdapter` 协议、`VenueSpec`、`PaperStub` 等冻结件 | **包装** | `v1_bridge` 把能力位映射为来源通道：DISCOVER/ENUMERATE → `metadata`/`latest`；RESOLVE/FETCH → `fulltext`（其 `exec_side` 与模式由策略引擎决定）；SEARCH → `metadata` 通道的查询能力，写入 SCD 供联邦使用。`PaperStub` 转为 RawRecord。v1 协议是同步接口，包装后的作业在 procrastinate 同步任务的线程池中运行。沿用 entry point 组 `paper_crawler.adapters`，v2 另设 `paper_crawler.connectors` |
| `http.py` | 共享的同步 httpx 客户端（`HttpClient`）与错误映射 | **改造** | 错误映射与 `Retry-After` 解析抽出复用；Egress 以异步 httpx 重写发送层，并暴露响应头（AG §3-5 指出 v1 `get_bytes` 不暴露响应头），加 robots、策略、缓存与 singleflight。v1 adapter 经 `bind_http_client` 注入 `EgressClient`：它实现 v1 `HttpClient` 的同名方法（`get_text`、`get_bytes`、`post_json`、`stream`），把每次调用转成一个 `EgressRequest`（§2.3.13），来源与通道由 `v1_bridge` 填入 `source_hint` |
| `ratelimit.py` | 按域令牌桶，"最保守值"单调合并 | **改造** | 在 Egress 内扩为五元组桶键，加响应头驱动与 AIMD；保留"只会更保守"的合并语义 |
| `pipeline/cooldown.py` | 挑战冷却（域级键） | **改造** | 并入 Egress 的熔断与冷却状态（存于 `ops`）；扩展的端侧冷却沿用同一键语义 |
| `merge.py` | MergeEngine：字段级来源优先级、弱信号候审 | **改造** | 成为 Ingestor 的 identify：union-find 物化 `cluster_id`，`SOURCE_PRIORITY` 演进为"字段 × 学科 × 源"可信度矩阵（T13） |
| `registry.py` | VenueSpec 加载、lint、路由 | **改造** | 演进为 SourceSpec v2 与 Venue 注册表加载器（`registry/sources/*.yaml`），lint 增加合规字段；62 个 v1 VenueSpec 一次性转换 |
| `config.py` | 分层配置与敏感键护栏 | **改造** | v2 配置层：env > 部署配置文件 > 默认；部署级密钥来自 secret 文件；保留敏感键护栏（D-025） |
| `obslog.py` | jsonl 结构化日志与脱敏 | **改造** | 并入 OTel 日志，带 `trace_id`，保留 `redact` |
| `subs/model.py`、`subs/compile.py`、`subs/filter.py` | 订阅 DSL；下推与本地补偿；本地残差过滤 | **改造** | DSL 演进为 Query AST（04），并提供 DSL → AST 转换器供 ETL；下推与补偿泛化为健全放宽（NNF 与极性，SI-25）；残差过滤并入 Router |
| `subs/guard.py` | 单次新增上限熔断 | **改造** | 演进为 WatchKey 的突增检测：超阈值暂缓入库并人工复核 |
| `pipeline/extract.py` | pypdf 基线加 GROBID 可选（consolidation 为 0） | **改造** | 供 `enrich_fulltext`（只处理可共享 OA）与 pc-agent（私有）使用；新增 `teiCoordinates=figure`（ADR 候选 13） |
| `auth/`（`protocol`、`store`、`manager`、`providers/*`、`browser`、`cli`） | AuthProvider 四实现、AES-GCM 凭证库、首登 | **复用，只用在用户侧** | 只在 pc-agent 中使用（personal 部署的用户侧能力同样由 pc-agent 提供）；平台服务镜像不含（INV-02、INV-07） |
| `browserfetch.py` | 浏览器上下文单篇取回（案 A） | **复用，只用在用户侧** | 仅限 pc-agent；SSRN 模式 B 按 ADR 候选 4 删除 |
| `adapters/crossref` | ISSN 枚举、前缀枚举 | **包装 → 改造** | 演进为 `crossref_delegated` 家族：按请求类型分池（SI-02），`from-created-date` 为主（SI-13） |
| `adapters/openalex`（含 `budget.py`） | enrich 通道；每日信用预算 | **改造** | 拆为快照导入器与计量 API 连接器；`budget.py` 并入 Egress 的美元桶 |
| `adapters/arxiv` | OAI、Query、分桶 | **改造** | 改为类目级 set（`group:archive:category`），修正物理 set，识别 429 与伪 200（SI-05） |
| `adapters/s2`、`adapters/unpaywall`、`adapters/repec` | enrich 与补查 | **包装** | S2 为"只展示或 TTL 缓存"（⚠ LQ-08）；Unpaywall 作 OA 补查；RePEc 作 bulk 快照 enrich |
| `adapters/openreview` | 会议元数据 | **包装** | 匿名访问 `/notes` 返回 403 `ChallengeRequiredError`（CS §2.1.2），平台层必须用服务账号，而服务账号的合规性待书面确认（CS §3-9；ADR 候选 12；08 §4.6 第 7 项）。确认前平台侧不调用 OpenReview API：匿名请求按挑战处理即停（HC-26），也不启用服务账号。过渡期由会议 OA 平台（如 PMLR、NeurIPS proceedings）、DOI、arXiv 与 DROPS 快照补位；ICLR、TMLR、COLM 这类只在 OpenReview 发布的 venue 在确认前覆盖与新鲜度下降，排期由 03、09 承接。用户可在 pc-agent 中用本人 token 读取，结果只进本人 `usr` |
| `adapters/pmlr`、`cvf`、`acl_anthology`、`neurips_proceedings`、`aaai_ojs`、`econsoc`、`nber`（含 `rss`）、`aea` | 元数据、最新与全文定位 | **包装** | `metadata` 与 `latest` 走平台侧；`fulltext` 按许可判定：CC 许可可进 `oa-shared`，否则只外链或在用户侧取回（CS §3-7） |
| `adapters/ssrn` | 元数据主路径加浏览器模式 B | **冻结（v2 不包装）** | v2 只取元数据加外链，删除浏览器模式（ADR 候选 4、SI-08）：元数据由 `crossref_delegated` 按前缀 10.2139 承接（D-029 模式 A），SSRN 站点零请求。v1 的 `ssrn/adapter.py` 在模块顶层导入 `browserfetch`，后者又导入 `auth.browser`；这两者从平台镜像剔除后该模块无法导入，所以不得经 `v1_bridge` 包装 |
| `adapters/dblp` | 已出列生产链（D-037） | **冻结** | 改用 DROPS 月度快照与 SPARQL（ADR 候选 3、SI-07） |
| `adapters/elsevier_sd`、`wiley`、`oup_silverchair` | auth_gated 全文 | **包装，只用在用户侧** | 作 `official_tdm_api` 或会话型用户侧连接器，只在 pc-agent 中运行 |
| `adapters/mock_platform` | 测试 adapter | **复用** | 契约测试夹具 |
| `storage/db.py`、`storage/repo.py`、`storage/migrations/0001–0007` | SQLite 仓储与迁移 | **冻结** | v2 用新的 PG schema（05）；ETL 以只读方式读取 |
| `tasks.py` | 任务队列与状态机 | **冻结** | 由 procrastinate 替代；BLOCKED 语义保留（§2.9.4） |
| `pipeline/runner.py`、`pipeline/stages.py` | 六阶段编排 | **冻结** | v2 语料流水线重新设计（03），全文 fetch 移出后台；幂等与错误路由的纪律保留 |
| `subs/watch.py`、`subs/report.py`、`subs/types.py` | watch 编排、日报、冻结件 | **冻结** | 编排职责由调度器与 Percolator 承担；日报以后可作 digest 另行设计 |
| `cli.py`、`dedupe_cli.py`、`verify.py`、`canary.py`、`preprint_report.py`、`pipeline/report.py`、`pipeline/cooldown_cli.py`、`adapters/unpaywall/report.py` | v1 CLI 与报告 | **冻结** | 不改为 v2 API 客户端（§6.5）。canary 的思路演进为 Drift Probes 与连接器契约测试；去重复核改到 Admin Console |

### 6.3 v1 文档去向

| v1 文档 | v2 去向 |
|---|---|
| [design/01-architecture.md](../../archive-v1.md#docs-design-01-architecture-md) | 继续作为 v1 的 `implemented` 文档。v2 架构以本文为准，六层视图演进为 §2.1 的七层（L0–L6） |
| [design/02-plugin-framework.md](../../archive-v1.md#docs-design-02-plugin-framework-md) | 两层结构（D-002）由 03 演进为 SourceSpec v2 × Connector 家族；本文只规定放置规则（§2.4） |
| [design/05-pipeline.md](../../archive-v1.md#docs-design-05-pipeline-md) | 六阶段由 03 演进为语料流水线；错误分类学与 BLOCKED 语义沿用（§2.9.4） |
| [design/10-config-layout.md](../../archive-v1.md#docs-design-10-config-layout-md) | §6 的敏感边界不变式对 v2 仍然有效；分层加载链在 v2 配置层中保留 |
| [design/11-browser-fetch.md](../../archive-v1.md#docs-design-11-browser-fetch-md) | 只在用户侧有效（pc-agent）；§2 的红线段原样适用于扩展 |
| [design/auth-framework.md](../../archive-v1.md#docs-design-auth-framework-md) | 只在用户侧有效；凭证库与 AuthProvider 不进入平台镜像 |
| [design/06-data-model.md](../../archive-v1.md#docs-design-06-data-model-md)、[design/09-search-filter.md](../../archive-v1.md#docs-design-09-search-filter-md)、[design/12-fulltext-extract.md](../../archive-v1.md#docs-design-12-fulltext-extract-md) | 分别由 05、04、03 演进 |

### 6.4 v1 ADR 的影响与 ADR 候选

**受影响的 v1 ADR**

| ADR | 影响 |
|---|---|
| D-001 | "SQLite → PG 预留路径"改为 v2 单栈 PG（简报 §7-5） |
| D-003 | open_access 与 auth_gated 的二分由 `exec_side` 加许可判定取代（简报 §7-10） |
| D-004 | 全文 fetch 移出后台流水线 |
| D-006 | 人在回路沿用到用户侧（AD-10） |
| D-014 | 平台 UA 口径与 robots ADR（简报 §7-2）；Content-Signal 的遵守延续到 Policy Engine 的 AI 用途判定 |
| D-026 | robots 路径级读法用于 Egress 与用户侧执行器的判定（HC-29） |
| D-023 | 凭证库只在用户侧 |
| D-025、D-032 | 配置分层与 config-home 用于 personal 部署与 pc-agent |
| D-029、D-030 | SSRN 与浏览器取回（简报 §7-4、§7-10）；D-030 的 CF-403 挑战判定契约（S-c）与域级冷却键（E-1）沿用到 Egress 与扩展 |
| D-037 | dblp（简报 §7-3） |
| D-039 | v2 以队列加舱壁取代"优先级队列 defer" |

**本文承接的简报 ADR 候选**：§7 的第 5、6、9、10、11 项，本文分别给出：

- 部署与单栈：§2.5、§2.6；
- 三域落地：INV-01、AD-07；
- 商用开关：§2.15；
- 执行位置：§2.4；
- LLM 路由：Egress 的 `model_provider`。

**本文建议 09 新增的 ADR 候选**（均为 proposed）：

1. Egress Gateway 作为唯一公网出口：应用层网关、四类路由、出口例外清单（Edge 的 ACME、拉取式备份）、桶键五元组中的"请求类"取上游定义的类别（AD-01、INV-03）；
2. API 契约：OpenAPI 3.1、URI 主版本与 SSE 的流式语义（AD-09）；
3. 事务性 outbox + procrastinate 队列与连接拓扑（AD-06）；
4. 下发记录与 `impression_id` 的生成方（AD-04，与 06 联签）；
5. 许可门禁四级分级（简报 R2-01 已裁定保留 psycopg 3；ADR 记录该裁定）；
6. personal 部署中 `host_is_user_device` 的判定（§8-3；简报 R2-28 已裁定默认 false、云主机不视为用户本机，并入执行位置 ADR）。

### 6.5 迁移路径（架构层面，细节见 05）

1. **v1 → v2 ETL**：只读打开 v1 SQLite（`.paper-crawler/catalog.sqlite`，D-032），转换后以 COPY 写入 v2 PG。RT §10.7 核验时 v1 库只有 179 篇、228 个标识符，迁移成本很低。
   - 订阅经 DSL → AST 转换器变为用户频道；
   - 文献库归入该用户的 `usr`；
   - v1 本地 PDF 视为私有资产：personal 部署导入本机私有前缀，platform 部署由用户自行上传（HC-16、LQ-15）。
2. **派生结构在 PG 侧重建，不搬运**：BM25、向量、`cluster_id`、`route_stat`（RT §10.7）。
3. **VenueSpec 转换**：62 个 VenueSpec 经转换脚本变为 SourceSpec v2 与 Venue 记录，由 03 的 lint 校验。
4. **v1 CLI 保留为冻结的离线版**：01 把"v1 CLI 是否改为 v2 API 客户端"交给本文决定。结论是**不改**：改造属于新增功能，与 B-03 的维护冻结（只修缺陷）冲突，而 PWA 与 API 已覆盖 v2 的全部交互。v2 需要的运维命令（ETL、迁移、备份恢复、开关演练、密钥轮换）由 v2 自带的管理 CLI 提供，它与 Admin API 走同一套权限与审计。

---

## 7. 术语（本文新增的共享术语，供 01 汇总）

| 术语 | 含义 |
|---|---|
| **Egress Gateway（出站网关）** | 平台唯一的公网出口组件（简报 R2-08），应用层网关（不是 CONNECT 代理）。执行主机白名单与逐跳 SSRF 校验、robots 先行、策略裁决、全局令牌桶（五元组键）、AIMD、重试预算、熔断、缓存、FetchLog，以及 LLM 的数据类别闸与地区路由；03 的 PoliteHttp 是其内部客户端库，08 的"出站网关"与"LLM 网关"指它的不同路由 |
| **Egress 路由（route）** | Egress 的四类出站：`scholarly_upstream`（学术上游）、`model_provider`（LLM 与嵌入 API）、`identity_provider`（OIDC 与用户授权的导入）、`notification`（邮件、Web Push、告警） |
| **上游请求类（upstream_class）** | 令牌桶键中的"请求类"：由上游定义的限速类别，例如 Crossref 的 single 与 array 两池。区别于 08 的策略请求类（`BACKGROUND_BATCH`/`ON_DEMAND`/`USER_SIDE`）与本文的舱壁道，后两者只是同一个桶内的份额 |
| **出口例外清单** | INV-03 允许的非 Egress 网络行为，只有两项：Edge 接收入站并续期 ACME 证书；备份主机拉取备份 |
| **Lane（舱壁道）** | Egress 与队列中按流量类型分隔的资源份额：交互、收割、enrich；交互道保底 |
| **RetrievalIntent（取回意图）** | 与 08 §15 为同一术语，以 08 为准：平台签发、短时有效、绑定会话、不含凭证的单篇取回意图，由用户点击生成，交给扩展或 pc-agent 在用户侧执行 |
| **Policy Bundle（策略包）** | 平台签名的端侧策略快照，含各出版商的状态、允许模式、端侧速率与日配额，以及挑战特征库版本 |
| **下发记录（Served Record）** | 服务端在下发卡片时写入 `evt` 的记录，生成 `impression_id`，含位置、候选源、打分分量、实验桶与倾向分；它是 Impression 的服务端载体 |
| **预计算批块（Deck Build）** | 近线为用户预先计算的下一批块（06 的"批块"）候选与打分；在线路径命中时只做轻重排与 Hydrate，未命中时跑在线管线（AD-03） |
| **非个性化批次（mode=non_personalized）** | 不使用画像的装配结果，按时间或来源排序。它既是 HC-13 的用户选项，也是降级兜底 |
| **pc-agent（本机代理）** | 运行在用户本机、复用 v1 认证框架的用户侧宿主，执行用户级 TDM API 与机构会话取回 |
| **`host_is_user_device`** | personal 部署的声明项：只有为 true 时，本机 pc-agent 才能执行 `exec_side=user` 通道 |
| **部署单元（Deployment Unit）** | 按 `region` 划分、不共享 `usr` 数据的一套独立部署 |
| **信任区（Trust Zone Z0–Z5）** | §2.14 的安全分区：用户设备、边缘、应用、数据、出站、管理面 |
| **outbox** | 与领域写入同事务的事件表（字段含 `topic`、`key`、`version`），由 relay 转为队列作业，是 T2 CDC 的接口 |
| **Notifier（通知出口）** | 平台侧的通知组件，负责账号邮件、数据权利通知、digest 与告警外发，全部经 Egress 的 `notification` 路由（§2.3.17） |
| **私有增益道（`enrich_private`）** | 平台上处理私有资产派生的 enrich 队列，默认关闭（AD-13） |

## 8. 异议与备选

1. **psycopg 3 的 LGPL 许可与 B-06 白名单冲突**。
   - **冲突**：
     - B-05 点名 psycopg 3，B-06 却规定核心链路只用 Apache、MIT、BSD、PostgreSQL 许可；
     - psycopg 3 为 LGPL-3.0（⚠ 调研未覆盖，按项目 LICENSE 记录）；
     - procrastinate 以 psycopg 3 为连接器（⚠ 实现期核对）。
   - **建议**：以 ADR 修订 B-06，把"未修改、以 Python 动态导入方式使用的 LGPL 库"列为白名单附条件项。一般理解是弱 copyleft 不传染调用方代码，最终以法务意见为准。
   - **备选**：核心改用 asyncpg（Apache-2.0，⚠ 调研未覆盖），队列改用 pgqueuer（RT §10.6 记为支持 PG 原生的 MIT 队列；其 asyncpg 驱动支持 ⚠ 待核）。代价是偏离 B-05 的首选，并失去 procrastinate 与 v1 单进程模型接近的优势。
   - MPL-2.0 等其他弱 copyleft 工具的口径应一并裁定，它们只出现在开发期或运维侧。
   - **字面白名单之外的宽松许可**也需一并裁定：PgBouncer（ISC，⚠ 调研未覆盖）、Python 运行时（PSF）、pyzotero（Blue Oak 1.0.0，综合 §4.4）。它们在义务上与 MIT/BSD 相当，但不在 B-06 的字面列表中。建议把白名单表述为"OSI 认可的宽松许可族（Apache-2.0、MIT、BSD、ISC、PostgreSQL、PSF、Blue Oak 等）"，由主 agent 以 ADR 定稿。
   - **状态**：已由简报 R2-01 裁定（采纳 08 §10.6 四级；宽松许可族放行；psycopg 3 评审级放行；未修改的 OFL 字体放行），§2.10 已改写。
2. **Egress Gateway 独立成服务，不作进程内库**（AD-01，属于细化而非偏离）。
   - **理由**：
     - 调研阶段多次发生"先请求、后读 robots"，说明纪律必须由框架强制（综合 §1.5、SI-38）；
     - 网络层隔离能把"平台只有一个出口身份"变成可测试的结构性质（AC-V0.15），也能让 arXiv"所有机器合计"的限速（HC-06）落到单点。
   - **代价**：多一跳网络，加上一个单点。单点故障时退化为"仅本地"（F4），T2 按来源分片。
   - **备选**：进程内库，令牌桶状态放在 PG 或 Valkey。无法防止某个组件绕过限速库直接出网，因此不取。
   - **两处必要的细化**（第 1 轮评审补入）：
     - 网关必须是应用层网关（调用方提交结构化请求，Egress 自己发起 TLS）。若做成 HTTP CONNECT 代理，HTTPS 流量对它不透明，按路径的 robots 判定、限流头解析、缓存与逐请求审计都无法实现。
     - "唯一出口"须覆盖身份提供方与通知这两类容易遗漏的出站，并列明例外（Edge 的 ACME 续期、拉取式备份）。否则 OIDC 登录、口令重置邮件与告警在 `internal` 网络下无法工作，或在实现中被悄悄开出后门。
3. **personal 部署运行在非本人设备时，不应视为"用户本机"**（对 P-03 的细化）。
   - **依据**：EZproxy 的默认规则会把数据中心出口与多国家、多 IP 的访问判为共享或盗号（CP §2.3.4）；SERU 下系统性下载可能导致整个机构被暂停（CP E7）。
   - **建议**：
     - 新增 `deployment.host_is_user_device`，默认 false；
     - 为 false 时，personal 部署同样只能经扩展在用户浏览器中取回；
     - 须由 09 与 08 确认后写入 ADR（执行位置 ADR，简报 §7-10）。
   - **状态**：已由简报 R2-28 采纳（`deployment.host_is_user_device` 默认 false）。
4. **本地检索 p95 ≤800 ms（01 NFR-10 的口径含融合与重排）与"cross-encoder 重排 top-100"在纯 CPU 的 T1 上可能冲突**（性能可行性保留意见）。
   - **依据**：调研没有给出 cross-encoder 在 CPU 上重排 100 对的延迟数据。按常识，大号重排器在 CPU 上可能需要秒级（⚠ 推断，未实测）。
   - **建议**：不改延迟目标，在 V1 压测中比较三种手段，由 04 定稿：给推理服务配 1 张 GPU；换小号重排器或只重排 top-30；重排超预算时先发 RRF 结果、再以 `upgrade` 事件替换（§2.7(d)）。第三种只作降级路径，AC-V2.46 要求其占比 ≤5%。
   - **状态**：已由简报 R2-39 裁定：800 ms 为端到端本地检索 p95，300 ms 为单路召回的升级触发；top-100 改为上限，纯 CPU 的 T1 从小模型 int8、top-50 起步，超预算先发 RRF、以流式 `upgrade` 补发。
5. **按 1 万 DAU 做容量设计时，evt 会超过简报 §6.3-5 的 ClickHouse 阈值**（澄清，不是异议）。
   - **数据**：上界口径下 UI 事件与下发记录合计约 29 亿行/年（§2.11），超过 10⁹/年。
   - **建议**（原稿）：T1 在 PG 中只保留约 90 天热数据，其余归档为 Parquet；超过阈值时再按 T2 引入 ClickHouse。按 1,000 DAU 的目标档（约 0.73 亿行/年），不需要 ClickHouse。
   - **状态**：简报 R2-31 裁定：可识别 6 个月、假名化 13 个月；PG 热存 6 个月，冷数据归档为 Parquet；1,000 DAU 目标档不引入 ClickHouse（§2.6.1、§2.11 已改）。
6. **部署级凭证的"服务端 KMS"**（简报 §6.3-3，细化）。
   - **现实**：自托管 T1 通常没有 KMS。
   - **建议**：抽象为 secret 提供者。默认用 docker secrets 或权限 0600 的文件，由 Egress 独占读取；云 KMS 作可选项。这不改变"平台身份与用户凭证两分"的裁决。
   - **状态**：已由简报 R2-30 采纳；用户登录用的 OAuth 客户端密钥归认证服务。
7. **限速键增加出口 IP**（P-04 的键为四元组，SI-37 建议加出口 IP）：本文采用五元组，与综合 §8 对 P-04 的核对结论一致。这属于细化，没有冲突。**状态**：已由简报 R2-08 采纳五元组 `(source, host, 上游请求类, 凭证, 出口 IP)`。

## 9. 待决问题

| # | 问题 | 影响 | 建议的决定方 |
|---|---|---|---|
| 1 | psycopg 许可例外，或改用 asyncpg（§8-1） | 依赖基线 | **已裁决**（简报 R2-01） |
| 2 | T1 单机的可用性目标（99.5%/月）与 PG 单点是否可以接受；要高可用须加第二台主机 | 部署成本 | 用户 |
| 3 | 管理面暴露方式：VPN、SSH 隧道或 IP 白名单 | 安全 | 08 |
| 4 | 扩展的覆盖范围与上架节奏：Chromium 优先，Firefox 与 Safari 的时间；商店对"下载内容"类扩展的审核风险（⚠ 未调研）；网页与扩展之间的消息通道（Chromium 的 `externally_connectable`）及本机 PDF 分块传给 PWA 的方式在各浏览器上的等价机制（08 §16 第 3 项） | 用户侧取回的可用性 | 07、08、09 |
| 5 | 哪些出版商可以放行"后台直取"模式（受 LQ-07 约束） | 用户侧体验 | 08 与法务 |
| 6 | `features.oa_shared_cache` 的默认值：共享缓存带来的收益，对比许可闸 100% 精度的要求与存储成本 | 合规与存储 | 03、08 |
| 7 | 联邦配额初值（每用户每日 30 次、全局每日 $1），以及何时触发 Q3 的付费档 | 检索体验与成本 | 04、09 |
| 8 | 各地区的 LLM 提供方、零保留条款；T1 是否配 GPU 自托管 | 成本与合规 | 部分裁决（简报 R2-45：T1 默认不配 GPU；含画像的 LLM 任务只用自托管模型、T1 默认关闭；开放内容预处理可用零保留、非中国境内路由的第三方 API）；各地区提供方待 03、08 |
| 9 | 运维看板是否满足于 Admin 内嵌，还是引入 AGPL 的 Grafana 作可选运维进程 | 许可口径 | 主 agent |
| 10 | 多设备凭证同步（只传端到端密文）是否进入 v2.0 | 范围 | 部分裁决（简报 R2-29：会话 Cookie 与 storage_state 不同步，只有 API key 类可做端到端密文同步）；是否进 v2.0 由 09 排期 |
| 11 | 术语统一：本文的 Egress Gateway 即 08 中的"出口网关"与"LLM 网关"；本文的"下发记录"即 06 的 `serve` 记录，落 05 的 `evt.impression` 表（06 已采用"serve 铸造 `impression_id`、客户端 impression 表示可见"的拆分）；本文的"预计算批块"即 06 的批块预计算 | 术语一致性 | **已裁决**（简报 R2-07、R2-08：Egress Gateway（出站网关）；`evt.impression`） |
| 12 | Zotero 导入的令牌处理：用后即删的 OAuth 一次性导入，或只支持文件导入 | 凭证边界 | **已答复**（06 AL-22：一次性导入，令牌只在导入作业内存中使用、用后即删，另支持文件导入） |
| 13 | 删除请求与日志留存冲突时的口径（HC-14 与 HC-20） | 数据治理 | 08 |
| 14 | personal 部署是否提供非 docker 的安装方式 | 易用性 | 09 |
| 15 | 简报 Q1、Q2、Q4 的默认假设一旦改变，§2.15 的开关与 AC-V1.13、AC-V1.14 的前提随之改变 | 全局 | 用户 |
| 16 | 私有文件的哈希与存储模式：08 §5.4 已写明"`content_hmac` 由端侧以用户密钥计算，服务端不存明文哈希"，本文按此写（INV-08、AC-V3.7）。05 §3.2.7 的 `usr.private_asset` 仍写 `content_hmac = HMAC(每用户盐, 字节)`（未说明由谁计算），并保留 `storage_mode='server_envelope'` 与 `dek_ref`；`usr.private_derivative.processor` 允许 `api:<vendor>`（凭同意调用第三方 API）。后两项在 platform 部署下与 INV-04、INV-08 及 08 §9.5 冲突，建议 05 限定为 personal 部署专用或删除 | 隐私与去重 | **已裁决**（简报 R2-27、R2-28：服务端托管模式只在 personal 且 `host_is_user_device=true` 时可用；05 已按此限定） |
| 17 | 跨文档命名与字段对齐：① 队列 `rec_events`（06 §8.2，本文采用）与 05 §3.3.4 的 `label_update`；② 下发记录表 `evt.impression`（05、06，本文已改用）；③ 05 `ops.outbox` 缺 `key`、`version` 列；④ 策略结论词表三处不一：08 §4.3 的 `Verdict`（本文采用）、05 `ops.policy_snapshot.verdict`、03 待定；⑤ 05 `ops.quota_ledger` 的 `request_class` 应为上游请求类（§2.3.13）；⑥ 预计算批块与缓存候选池（06 §7.7）在 05 尚无表；⑦ 建议 05 增设 `pc_sys_egress` 角色 | 契约一致性 | **已关闭**：①③⑦ 见 R2-07 与 05 §3.4（`rec_update`、outbox `key`/`version`、`pc_sys_egress`）；② `evt.impression`；④ 策略模式以 03 §6.2 五档全序为准（R2-09）；⑤ 配额键用上游请求类（05 已改）；⑥ 05 `usr.deck_batch` |
| 18 | ORCID 等 OAuth client secret 的存放：08 §5.5 放在认证服务的秘密存储；本文建议统一由 Egress 注入（身份提供方路由），使 API 不持有任何上游秘密 | 秘密管理 | **已裁决**（简报 R2-30：归认证服务；部署级上游 API key 由 Egress 独占） |
| 19 | 异机备份方向：拉取式（本文默认，保持 INV-03）还是推送到对象存储（须加出口例外）；以及 RPO ≤5 分钟对拉取周期的要求 | 灾备与出口边界 | **已裁决**（简报 R2-37：拉取式为默认；RPO/RTO 以 NFR-27 为准） |
| 20 | 强负反馈的写入时机：本文在事件接入事务内同步写 `usr.mute_rule`（保证 AC-V4.4 与 AC-V4.34）；05 §3.3.4 的写入路径把它放在异步 `label_update` 中 | 当次会话生效 | **已裁决**（简报 R2-33：接入事务内同步写 `usr.mute_rule` / `usr.session_suppress`，撤销按 `origin_event_id` 删除） |
| 21 | OpenReview 服务账号确认之前，ICLR、TMLR、COLM 等只在 OpenReview 发布的 venue 的覆盖与新鲜度如何补位 | 来源覆盖 | **已裁决**（简报 R2-20：arXiv 版本 + DROPS dblp 快照 + OpenReview forum 外链兜底；V0 即发函） |

## 10. 参考

**上游约束**

- [v2 设计决策简报](00-design-brief.md)：B-01…B-06、P-01…P-09、§5 术语、§6 子系统裁决、§7 ADR 候选、§8 待决问题、§9 接口归属
- [调研综合](../../survey/00-survey-synthesis.md)：§2.2（检索、路由与多用户数据库）、§4.4（可复用开源清单）、§5（张力 T1–T18）、§6（SI-01…SI-70、HC 摘要）、§7（风险与缺口）、§8（与简报的一致性核对）

**调研原文**（核验日期均为 2026-09-26）

| 代号 | 文档 | 本文主要引用 |
|---|---|---|
| RT | [algorithms/retrieval-routing-indexing.md](../../survey/algorithms/retrieval-routing-indexing.md) | §2.2 外部约束；§3.5 路由与替补链；§5.3–5.4 容量与分档；§6–7 图、树与去重；§8.3 调度；§9 稳定性；§10 多用户数据平台、队列与迁移；§11 参考架构与分档；§12 启示 |
| OSS | [oss/paper-acquisition-and-search-oss.md](../../survey/oss/paper-acquisition-and-search-oss.md) | §2.10.6 多用户隔离；§2.12–2.13 横向归纳与空白；§3 启示；§6 分级清单 |
| RO | [oss/recommendation-oss.md](../../survey/oss/recommendation-oss.md) | §2.2.2 x-algorithm 请求路径；§3.1 启示；§3.2 推荐栈 |
| SR | [algorithms/scholarly-recommendation-and-matching.md](../../survey/algorithms/scholarly-recommendation-and-matching.md) | §2.6.5–2.6.6 LLM 延迟与成本；§3.1–3.3 |
| SM | [algorithms/social-media-recsys.md](../../survey/algorithms/social-media-recsys.md) | §2.14 迁移清单；§3 启示 |
| UX | [ux/card-feed-interaction.md](../../survey/ux/card-feed-interaction.md) | §2.9.6 事件契约；§2.10 技术栈；§3 启示 |
| PU | [algorithms/paper-understanding-and-card-content.md](../../survey/algorithms/paper-understanding-and-card-content.md) | §2.6.4–2.6.7 成本、延迟与缓存；§2.8 流水线；§3 启示 |
| CP | [compliance/multi-user-platform-compliance.md](../../survey/compliance/multi-user-platform-compliance.md) | §2.3.3–2.3.5 每用户私有与共享边界；§2.4 礼貌；§2.7 合规矩阵；§3.1 HC；§3.2 DI；§4.1 LQ；§4.2 RK |
| AG | [sources/aggregators-repositories.md](../../survey/sources/aggregators-repositories.md) | §0 第 1 条与 §2.2.1 Crossref 分池（`/journals/{issn}/works` 归单条池为实测、官方未承诺）；§0 第 7 条 bulk 主机 robots；§3-5 响应头驱动限速；§3-13 用户自带凭证；§3-15 robots 先行闸；§3-16 成本边界 |
| CS | [sources/cs-ai.md](../../survey/sources/cs-ai.md) | §2.1.2 OpenReview 匿名访问 403；§3-7 全文逐篇许可；§3-9 OpenReview 两层接入；§3-12 限流头 |
| MK | [market/startups-and-products.md](../../survey/market/startups-and-products.md) | §2.9 形态演进 |

**v1 文档与决策**

- [design/01-architecture.md](../../archive-v1.md#docs-design-01-architecture-md)、[design/02-plugin-framework.md](../../archive-v1.md#docs-design-02-plugin-framework-md)、[design/05-pipeline.md](../../archive-v1.md#docs-design-05-pipeline-md)、[design/10-config-layout.md](../../archive-v1.md#docs-design-10-config-layout-md)、[design/11-browser-fetch.md](../../archive-v1.md#docs-design-11-browser-fetch-md)、[design/auth-framework.md](../../archive-v1.md#docs-design-auth-framework-md)
- [决策日志](../decision-log.md)：D-001、D-002、D-003、D-004、D-006、D-007、D-014、D-023、D-025、D-029、D-030、D-032、D-033、D-037、D-039
- [验收标准](../../archive-v1.md#docs-testing-acceptance-criteria-md)：AC-0.1…AC-0.5、AC-1.4
- 源码：`src/paper_crawler/`（2026-09-27 只读核对模块清单与 entry point 注册表：21 个 adapter entry point，含 `mock_platform`；62 个 VenueSpec）

**同级设计文档**：[01](01-vision-and-requirements.md)、[03](03-sources-and-corpus-pipeline.md)、[04](04-retrieval-and-routing.md)、[05](05-data-platform.md)、[06](06-recommendation-and-matching.md)、[07](07-frontend-interaction.md)、[08](08-compliance-security-privacy.md)、09（路线图）。本文对齐时主要引用（2026-09-27 草稿）：

- 01：NFR-9（事件生效 ≤2 秒）、NFR-10、NFR-13、NFR-19、NFR-27；FR-36、FR-77、FR-82、FR-83；
- 05：§3.2.4–§3.2.7（频道映射、收件箱、批次、私有资产）、§3.3（evt 分区与写入路径）、§3.4（ops）、§4.1–§4.4（角色与策略）；
- 06：§2.1–§2.2（进程与热路径预算）、§5.3、§5.8（事件契约）、§7.7（批块）、§8（学习闭环）、§11.3（反向推送）、§14.2（k 阈值）、§19（接口与容量）；
- 07：§15.4–§15.5（预取与发件箱）；
- 08：§4.2–§4.4（判定表、`Verdict`、确认流程）、§5.1–§5.5（用户侧取回、凭证、私有全文、部署级凭证）、§9.1–§9.5（LLM 数据类与路由）、§10.3（SSRF）、HC-29…HC-32。

---

## 附录 A：AC 清单（已由 09 统一改号）

| 编号 | 主题 | 关联 | 建议里程碑 |
|---|---|---|---|
| AC-V0.14 | 同一镜像双部署 | B-02 | V0 |
| AC-V0.15 | 出站唯一性 | INV-03、AD-01 | V0 |
| AC-V0.16 | 主机白名单 | AD-01 | V0 |
| AC-V1.5 | robots 先行 | SI-38、AC-0.5 | V0–V1 |
| AC-V1.1 | 全局礼貌 | P-04、HC-06/10 | V1 |
| AC-V1.2 | 重试预算与不对冲 | SI-32 | V1 |
| AC-V1.3 | 熔断与挑战即停 | HC-26 | V1 |
| AC-V0.17 | exec_side 强制 | INV-02、INV-07 | V0 |
| AC-V3.7 | 单向数据流 | INV-01、INV-08 | V0 |
| AC-V3.5 | RLS | P-02 | V0 |
| AC-V4.33 | 下一批卡片延迟 | 简报 §3 | 卡片流 MVP 里程碑 |
| AC-V4.1 | feed 降级与非个性化 | P-09、HC-13 | 卡片流 MVP 里程碑 |
| AC-V2.46 | 本地检索首屏 | 简报 §3 | V1 |
| AC-V2.32 | 联邦截止与降级 | P-09 | V1 |
| AC-V2.36 | 联邦预算 | AD-12 | V1 |
| AC-V3.9 | 事件幂等与绑定 | INV-05 | 卡片流 MVP 里程碑 |
| AC-V4.4 | 强负反馈当次会话生效 | 简报 §6.4-3 | 卡片流 MVP 里程碑 |
| AC-V2.45 | outbox 至少一次与幂等 | AD-06 | V1 |
| AC-V4.14 | percolate 时延（频道硬命中）与夜间反向推送完成时间 | §2.13 | 卡片流 MVP 里程碑 |
| AC-V3.17 | 用户侧回报无敏感内容 | INV-07、AC-0.4 | 用户侧取回里程碑 |
| AC-V4.25 | `open_fulltext` 隔离 | INV-06 | 卡片流 MVP 里程碑 |
| AC-V1.13 | 商用开关 | HC-23、DI-07 | V0–V1 |
| AC-V1.14 | 地区开关与 LLM 数据闸 | INV-04、HC-12 | V1 |
| AC-V0.19 | API 契约 | AD-09 | V0 起持续 |
| AC-V0.20 | 追踪贯通与日志脱敏 | §2.13、AC-0.4 | V0 |
| AC-V3.27 | 灾备 | §2.6.5 | V1 |
| AC-V3.29 | v1 ETL | B-03 | V0–V1 |
| AC-V0.13 | 许可门禁 | B-06 | V0 起持续 |
| AC-V0.18 | FetchLog 完整性与 robots 先行 | INV-10、HC-28、HC-29 | V0–V1 |
| AC-V4.34 | 事件生效时延与强负反馈 | 01 NFR-9、简报 §6.4-3 | 卡片流 MVP 里程碑 |
| AC-V2.34 | 多副本流式检索续传 | §2.7(d) | V1 |
| AC-V2.14 | 本地只读路径零远端调用 | INV-11、P-01、01 FR-36 | V1 |
| AC-V1.6 | 策略判定在 Egress 的落实（R5、R3、冷却） | HC-31、08 §4.2 | V1 |
| AC-V3.22 | 身份与通知出站经 Egress | INV-03、HC-01 | V0–V1 |

---

## 评审记录

| 轮次 | 视角 | 问题 | 严重度 | 处理 |
|---|---|---|---|---|
| 1 | FEAS | Egress 伪代码的 robots 闸位于策略裁决之后且直接拒绝，会把 08 §4.2 R5 允许按需调用的文档化 API（E-utilities、pub.orcid.org、export.arxiv.org）一并拒掉；robots 应作为 Policy Engine 的输入 | 高 | 已修：robots 快照作为五通道之一传入 `policy.decide`，按 08 `Verdict` 放行或拒绝（§2.3.13） |
| 1 | FEAS | 伪代码有挑战冷却却不检查冷却、熔断从不记录结果、没有重试循环、只在成功路径写 FetchLog；AC-V1.3 与 HC-28 无法满足 | 高 | 已修：加冷却检查、`breaker.record`、≤3 次重试与重试预算、`finally` 落账（INV-10、AC-V0.18） |
| 1 | FEAS | 重定向未逐跳校验，可绕过主机白名单与 SSRF 检查（AC-V0.16 的"重定向到未登记主机"无法验收） | 高 | 已修：`follow_redirects=False`，每跳重做 SSRF、白名单与策略，最多 5 跳（08 §10.3） |
| 1 | FEAS | 桶键里的"请求类"若按本平台的后台/按需类别拆桶，同一上游的速率会翻倍（arXiv 可达每 3 秒 2 次，违反 HC-06） | 高 | 已修：桶键用上游定义的请求类，内部类别与舱壁只是桶内份额；AC-V1.1 增加按 (source, host) 合计的约束 |
| 1 | FEAS | Egress 形态未说明；若按 HTTP 代理实现，HTTPS 路径与响应头不可见，robots、限流头、缓存与审计都做不到 | 中 | 已修：AD-01 与 §2.3.13 定为应用层网关，给出 `EgressRequest` 接口 |
| 1 | FEAS | "唯一出口"遗漏 OIDC 换令牌、ORCID/Zotero 导入、邮件、Web Push 与告警；Edge 的 ACME 出站与异机备份未定义，AC-V0.15 按原文无法通过 | 高 | 已修：新增 `identity_provider`、`notification` 路由与 P17 Notifier；INV-03 列出例外（Edge 的 ACME、拉取式备份）；AC-V0.15 修订，新增 AC-V3.22 |
| 1 | FEAS | 检索先 `POST` 再另开 `GET` 的 SSE，在 2–4 个 API 副本下两次请求可能落到不同进程，事件丢失 | 高 | 已修：`POST /search` 直接流式返回，事件同步写入 PG 快照，任一副本可续传（§2.7(d)、§2.8.7、AC-V2.34） |
| 1 | FEAS | 事件幂等写作 `ON CONFLICT (event_id)`，在按月分区表上不成立（唯一约束须含分区键） | 高 | 已修：按 05 §3.3.3 改为 UUIDv7 推出 `event_ts`，`ON CONFLICT (event_id, event_ts)`，并加时钟偏差窗口 |
| 1 | FEAS | outbox relay 未处理 `AlreadyEnqueued`，同键作业排队期间整批回滚、outbox 卡死；outbox 缺 `key`、`version`；relay 放在单例里成为单点 | 高 | 已修：捕获并视为合并、补逻辑字段、relay 可多实例（SKIP LOCKED）、NOTIFY 唤醒；新增 F17；05 表结构列入 §9 第 17 项 |
| 1 | FEAS | AD-03 与 06 §2.2 冲突：06 的热路径是请求期完整管线（约 235 ms），02 只允许读预构建；"p95 难以达标"无依据 | 中 | 已修：AD-03 改为"预计算优先、在线管线次之、快路径与非个性化兜底"，AC-V4.33、AC-V4.1 相应修订 |
| 1 | FEAS | 兴趣反向推送的日预算与曝光下限分配放在逐批近线里，先到的论文会抢占预算；06 §11.3 定为夜间规划 | 中 | 已修：Percolator 只做频道硬命中，兴趣反向推送为 Rec 的夜间作业（§2.3.6、§2.7(c)、AC-V4.14），两张图同步修改 |
| 1 | FEAS | `feedback.received` 的"排队 p95 ≤5 秒"与 01 NFR-9 的"事件到达 → 生效 ≤2 秒"冲突 | 中 | 已修：时延目标改为 ≤2 秒，relay 由 NOTIFY 唤醒；新增 SLO 与 AC-V4.34 |
| 1 | FEAS | `channel.changed` 被派给收割工作者；05 的角色设计是调度器按 `channel_watch` 对账；Rec 近线被写成跨用户受限视图读取，而 05 规定按用户作业以 `pc_app` 在 RLS 上下文运行；删除、漂移、导出的队列名与 compose 不一致 | 中 | 已修：§2.3.7、§2.6.2、§2.9.2、§2.5.2 按 05 对齐，补 `maintenance`、`notify`、`rec_nightly` 与五道舱壁映射；建议新增 `pc_sys_egress` |
| 1 | FEAS | personal 部署既要求与 platform 同一镜像（AC-V0.14），又在服务端执行用户侧通道并打包 AuthProvider/Playwright，自相矛盾；`cryptography` 被划为只在用户侧，但平台的 Ed25519 签名需要它 | 中 | 已修：用户侧能力统一由独立安装的 pc-agent 提供；`cryptography` 列入 `[platform]`，只剔除凭证库模块 |
| 1 | FEAS | PWA 无法直接读取扩展存储中的 PDF，(e) 的"PWA 内 pdf.js 阅读"缺传输路径 | 中 | 已修：扩展经 `externally_connectable` 端口在本机分块传给 PWA（⚠ 实现期核验），字节不经平台 |
| 1 | FEAS | v1 协议的 SEARCH 能力未映射；v1 `HttpClient` 为同步接口，桥接方式未说明；迁移路径写错为 `migrations/` | 低 | 已修：§6.2 补 SEARCH → SCD 查询能力、同步线程池与 `EgressClient` 适配、路径改为 `storage/migrations/` |
| 1 | FEAS | v1 `ssrn/adapter.py` 在模块顶层导入 `browserfetch`（它又导入 `auth.browser`），平台镜像剔除用户侧模块后，经 `v1_bridge` 包装会导入失败（源码核对） | 中 | 已修：SSRN 改由 `crossref_delegated` 按前缀 10.2139 承接（D-029），v1 模块不包装；测试方法第 1 项加 `v1_bridge` 导入冒烟 |
| 1 | FEAS | 容量估算口径不一：feed 峰值按典型值、事件峰值按上界；批块预计算次数与 06 批块不符；PG 内存两行可被误读为相加 | 低 | 已修：统一按上界口径（feed 约 23 req/s），批块次数按 06 §7.7 重算，注明 `shared_buffers` 含于有效缓存，补 HNSW 重建内存提示 |
| 1 | EVID/HC | OpenReview 映射写"确认前只做低频调用"，但匿名 `/notes` 返回 403 挑战（CS §2.1.2），08 §4.6 规定确认前不启用服务账号 | 高 | 已修：确认前平台侧不调用 OpenReview，列出补位通道与覆盖影响（§9 第 21 项） |
| 1 | EVID/HC | PubMed baseline 被列为后台 bulk 导入，但 ftp.ncbi 的 robots 为全禁（AG §0 第 7 条），属 `needs_confirmation`（HC-31、08 §4.7） | 高 | 已修：P6、`snapshots/`、周期任务均改为"确认前不导入" |
| 1 | HC | 联邦未命中查询作为 WatchKey 候选进入共享运维层与管理员复核，可能把个人查询带出私有域（HC-01） | 中 | 已修：候选只存规范化下推查询与不同用户数，达到 `k_feature` 或在不见身份的前提下复核才纳入（AD-12、§2.3.7） |
| 1 | HC | 查询文本、画像与懒生成解释属个人数据（08 §9.1），原文允许经 `model_provider` 发往第三方 LLM 做查询解析与解释 | 高 | 已修：INV-04、P3、P4、`llm.providers` 限定为自托管模型，未部署即关闭 |
| 1 | HC | HC-11(b)(d)、HC-06 在 enrich 与 API 中未落实；HC-13 申诉渠道、HC-19 年龄声明、HC-27 站点禁入未在 API 或架构中出现 | 中 | 已修：enrich 道加 AI 用途判定与 arXiv e-print 规则，API 加 `ai_label`、`POST /reports`、注册年龄声明；名录状态表写明 `excluded` 主机不进白名单 |
| 1 | HC | 数据流图 v2-02 中 ⑨"全局聚合信号"有箭头写入 ⑤ corpus，与 INV-01 及 05 的设计（聚合只写 `evt.agg_*`）矛盾；架构图 v2-01 的 Percolator、降级说明与规则归属同样过时 | 中 | 已修：⑨ 改为 `evt.agg_*`、箭头改指 ⑪ Rec 并注明不写 corpus；两图同步 Percolator/夜间反向推送、Notifier、四类出站路由与降级说明 |
| 1 | HC/B-06 | PgBouncer（ISC）、Python（PSF）、pyzotero（Blue Oak）不在 B-06 字面白名单 | 低 | 转主 agent：§8-1 建议把白名单表述为宽松许可族，以 ADR 定稿 |
| 1 | EVID | Crossref `/journals/{issn}/works` 归单条池是实测行为、官方未承诺；`route_stat` 周更用 group_by 会占用当日联邦预算；PU 成本上限未计新分词器；`open_fulltext` 字段沿用了已被 06 取代的 UX 草案 | 低 | 已修：补 ⚠ 与出处（AG §0 第 1 条、§2.2.1），route_stat 默认离线，成本上限补注，事件字段按 06 §5.3 |
| 1 | REQ | 需求① 的"支持名录"只有 API，缺名录状态到运行时行为的映射；需求② 的"最新论文"与"每个人的搜索信息"缺具体承接 | 中 | 已修：§2.3.14 新增名录状态效果表；LATEST 不联邦（INV-11、AC-V2.14）；新增 `/me/search-history` |
| 1 | FEAS | API 同时挂 `front` 与 `back`，而 `front` 未设 `internal`：Docker 中挂任一非 internal 网络即可出网，INV-03 与 AC-V0.15 会被 API 容器破坏 | 高 | 已修：`front`、`back` 都设 `internal`，只有 Edge（`public`）与 Egress 挂非 internal 网络（§2.5.2–§2.5.3、INV-03） |
| 1 | FEAS | 页面隐藏时用 `sendBeacon` 上报事件，但它不能带 CSRF 请求头，与"不安全方法要求 CSRF 双提交"冲突 | 低 | 已修：`/events` 的令牌可放在请求体内并校验 `Origin`，接受 `text/plain` 承载的 JSON（⚠ 实现期核验） |
| 1 | FEAS | 与 05、06、08 的命名与字段不一致（队列名、`evt.impression`、策略词表、outbox 列、配额账本的请求类、预计算批块无表、强负反馈同步与异步、私有资产的服务端加密模式） | 中 | 转主 agent：§9 第 16、17、20 项，需 05/06/08 对齐 |
| 审计 | 一致性（2026-09-27） | 与简报 §10 第 2 轮裁决及同批文档不一致：队列 `rec_events`、出箱 `work.ingested`/`work.enriched`、`k_feature`/`k_display`、Verdict 词表、"礼貌出口网关"、OAuth client secret 归属、evt 热存 90 天、批次 20–30、SSE 事件名与合并顺序、缺 `/me/follows` 与"再来 10 篇"接口、回执缺 `handed_to_user`、`open_fulltext` 字段、"用你的权限"计算位置、许可门禁口径、`cache_policy` 无 03 字段 | 中 | 已修：按 R2-01/02/03/04/05/06/07/08/09/10/11/13/14/15/16/18/19/20/21/22/23/27/28/29/30/31/32/33/34/35/36/37/38/39/40/41/42/44/45/46/47/48/49 改写；SSE 按 04 §8.2 统一；新增 `/me/follows`、`POST /feed/deck/more`、`features.public_lists`；`storage_policy.cache_mode` 对齐 03；§8、§9 标注裁决状态（清单见 01 §一致性审计记录） |
