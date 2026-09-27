---
title: v2 总体架构
status: draft
owner: opus5.5-primary
updated: 2026-09-27
---

# 02 · 总体架构

> 本文回答 v2 的组件、部署形态、数据流、出站方式与 API 面怎样设计。结论：模块化单体加工作者池，一套代码支撑平台与个人两种部署；PostgreSQL 四个数据域靠授权结构保证单向流；平台只经出站网关访问公网；受限全文只在用户侧取回。算法与表结构见 03–08，本文只定"在哪执行、与谁交互、失败时怎样退"。

## 要点

- **一套镜像，两种部署**：platform（多用户，自托管或邀请制）与 personal（单租户，承接 v1 个人场景），按 compose profile 切换。首个规模档 T1：≤1,000 活跃用户，按 1 万设计容量。
- **模块化单体加工作者池**：在线路径在 API 进程内，重计算交给推理服务与队列工作者；T1 不拆微服务，因为运维成本过高。
- **四个数据域，单向流**：`corpus`、`usr`、`evt`、`ops`；没有角色能同时读 `usr`、写 `corpus`，私有派生只进 `usr`（见 D-043）。
- **出站网关是唯一公网出口**：robots、策略、全局限速、配额与逐请求审计都在这里执行，由网络隔离强制（见 D-055）。
- **受限全文在用户侧取回**：由浏览器扩展或本机代理 pc-agent 执行，用户显式触发、单篇（见 D-053）。
- **API 契约先行**：REST + SSE，OpenAPI 3.1 是唯一契约；检索本地先返回、远端流式补齐（见 D-068）。
- **本地优先、处处可降级**：卡片流、频道预览与"最新"只读本地；依赖失败时退到仅本地、仅元数据或非个性化。
- **v1 代码复用**：共享件直接用，adapter 经 `v1_bridge` 包装，认证代码只进 pc-agent；v1 CLI 冻结。

## 不做什么

- 不以平台出口代取全文，不持有出版商会话与用户级凭证。
- 不做全文再分发与公共全文上传。
- 不引入独立图数据库，不建在线训练集群；LLM 不进交互热路径。

## 分层与组件

分层见 [v2-01-architecture.svg](../../diagrams/v2-01-architecture.svg)。依赖只向下；平台组件只经网关出网；用户侧只与接入层交互，另用本人会话直连出版商。

- **用户侧**：PWA；Companion Extension（浏览器配套扩展）；pc-agent（本机进程，独立安装包）。
- **接入层**：Edge 负责 TLS、静态资源、安全头与按 IP 粗限流；API（FastAPI）负责会话与令牌、按用户限速、联邦配额记账，并在事务内设置 RLS 用户上下文。
- **在线服务**（API 进程内）：
  - Router 与联邦执行器：规则快路径解析（LLM 只给异步建议）→ 本地 BM25 与向量并行召回、RRF 融合、cross-encoder 重排。本地覆盖不足时，SEARCH、SIMILAR、EXPAND（引文扩展）经 TSRG（主题-来源路由图）选源并行联邦，LOOKUP 按替补链补查。路由不用个人画像（见 [04](04-retrieval-and-routing.md)）。
  - Rec Service 与 Feed Assembler：优先读近线预计算的批块，只做轻重排；装配有限批次（默认 25 张，可选 15/25/35），不用净负分候选补满；每张卡写下发记录并由服务端生成 `impression_id`；非个性化时按 `first_public` 时间或来源排序（见 [06](06-recommendation-and-matching.md)）。
- **近线与批处理**：
  - Harvest Scheduler（单例）：WatchKey（多用户共享、带引用计数的收割键）对账与新鲜度调度、bulk 快照导入。由文献库、频道或关注派生的作者键与引文邻域键，须至少 `k_cf` 个不同用户共有才并入平台收割。
  - Connector Workers 执行平台侧来源通道，不自管限速与重试；Ingestor 规范化、标注权利、去重聚类，以单一角色写 `corpus`，同事务写出箱事件。
  - Enrich 分道处理元数据、嵌入、LLM 生成与 OA 全文；LLM 只取可共享输入；平台私有增益道默认关闭。
  - Percolator 分两档：近线档做频道硬命中，写入用户的 FeedInbox（候选收件箱）；日批档在夜间做兴趣反向推送（论文→读者），受每用户日预算与新论文曝光下限约束（见 D-063）。
  - Rec 近线逐事件更新画像与每用户模型，并预计算下一批块；按用户作业只在该用户的 RLS 上下文中运行。
  - 推理服务做嵌入、重排与分类，运行期不联网，T1 默认只用 CPU；Notifier 发账号邮件、digest（每日至多 1 封）与告警，全部经网关。
- **治理**：
  - Policy & Rights Engine：对文档化 API、bulk、robots、ToS、TDM 信号五个通道取最严，输出五档模式 `deny < link_only < user_side < on_demand < background`，给字段定 `display_scope`，并编译签名策略包下发用户侧（实现见 [03](03-sources-and-corpus-pipeline.md)）。
  - [支持名录](../../catalog/source-directory.md)的状态在运行时强制生效：`metadata-only` 只跑元数据与最新通道，`link-only` 主机零请求，`excluded` 主机不进白名单。
  - 漂移探针周期比对 robots、ToS 等，发现漂移即告警并分档降级。
  - Admin Console 强制 MFA，管理员只看假名化聚合数据；审计日志用 HMAC 假名与哈希链（见 D-066）。
- **数据**：PostgreSQL 18、对象存储、Valkey（可选）。

## 部署形态与规模档位

- **platform**：邀请码注册，ORCID/OIDC 登录；工作者按队列分组；网关用平台身份与部署级密钥；收割全体用户兴趣的并集。
- **personal**：单一本地账户；一个工作者消费全部队列；网关用用户本人的身份与 key；收割本人频道。礼貌约束照样生效。
- **T1 档**：≤1,000 活跃用户，按 1 万做容量设计；语料起步 100–300 万、按 1,000 万 work 设计；日新增 1–3 万。
- **T1 单机参考规格**（估算，须压测校准）：起步 16 vCPU / 64 GB / 2×1.92 TB NVMe；设计上限 32 vCPU / 128 GB / 2×3.84 TB NVMe；默认不配 GPU。personal 最低 4 vCPU / 16 GB / 200 GB SSD。
- **网络**：内部网络都设为 `internal`，只有 Edge 与网关可出网；管理面只经 VPN 或 SSH 隧道访问。
- **T2 档按可观测信号触发**：PG 独立主机加只读副本；HNSW 放不下内存时换 pgvectorscale；语料超过 1,000 万–5,000 万时外置检索引擎，PG 仍是真值源；事件超过 10⁹ 行/年引入 ClickHouse；网关按来源分片，仍保持单一出口身份。

## 数据域与单向流

主数据流为收割 → 入库 → enrich 与索引 → percolate → FeedInbox → 下发 → 事件 → 学习，见 [v2-02-dataflow.svg](../../diagrams/v2-02-dataflow.svg)。表结构归 [05](05-data-platform.md)。

- **`corpus` 共享层**：公开元数据，以及许可允许再分发的内容与派生物。应用只读，只经入库与 enrich 角色写入。
- **`usr` 私有层**：账号、兴趣、频道、文献库、每用户模型、FeedInbox、取回回执等。全表 RLS；应用角色不是 owner，也没有 BYPASSRLS。
- **`evt` 事件层**：下发记录、UI 事件、检索日志、k 匿名聚合。只追加，按月分区；可识别形态热存 6 个月，其后假名化归档为 Parquet，保留至第 13 个月。
- **`ops` 运维域**：队列与出箱、WatchKey（不存用户标识）、配额与美元账本、策略快照、FetchLog、审计。
- **单向流**：每个组件一个最小权限角色；跨用户读取的只有 Percolator 与反向推送规划器，只读所需列，对 FeedInbox 只能插入。
- **派生继承最严**：个人内容的一切派生（嵌入、摘要、特征、解释）留在 `usr`；打开全文等私有信号不进公共热度、社会证明与他人的解释；协同信号须满足 k 匿名门槛。
- **对象存储**：`oa-shared/` 只放许可白名单内的 OA 全文与图；`private/` 按用户命名空间只存端到端密文，不跨用户去重，注销即删。默认本地盘，经存储抽象层（见 D-070）。Valkey 只作缓存，不是真值源。

## 出站网关（Egress Gateway）

- **为什么独立成服务**：调研时多次出现"先请求、后读 robots"，纪律须由结构强制；单一出口也让 arXiv 这类全平台合计的限速可落地。代价是多一跳与一个单点，宕机时退到仅本地。
- **应用层网关**：调用方经内网 RPC 提交结构化请求，由网关自己发起 TLS；CONNECT 隧道看不到路径与响应头，做不了按路径判 robots 与逐请求审计。
- **四类路由**：学术上游（含 bulk 快照与探针）、模型提供方、身份提供方（OIDC、ORCID 与 Zotero 导入）、通知。出口例外只有两处：Edge 续 ACME 证书，备份主机拉取备份。
- **判定顺序**：主机白名单与 SSRF 校验（每跳重定向重做，最多 5 跳）→ 由注册表推出来源通道，`exec_side=user` 一律拒绝 → robots 先行，取不到视同全禁 → 策略裁决 → 冷却与熔断 → 缓存 → 令牌桶 → 发送。
- **全局限速**：令牌桶键为 `(source, host, 上游请求类, 凭证, 出口 IP)`，全平台共享；"上游请求类"是上游自定义的限速类别，如 Crossref 的 single 与 array 两池。后台/按需类别与交互、收割、enrich 三道舱壁只是桶内份额，不另开桶，否则速率翻倍；交互道有保底。
- **礼貌**：响应头驱动、以书面限额为上限的 AIMD；单请求至多 3 次尝试，每源 2 分钟内重试占比 ≤10%；按"源 × 端点"熔断；遇挑战冷却 24 小时、不求解；不对同一主机发对冲请求。
- **待确认通道**：`needs_confirmation` 通道拒绝后台批量。robots 全禁的文档化 API，后台收割须先有书面确认，按需单篇调用须先登记在 D-049 例外附表。
- **配额**：每用户日联邦配额初值 30 次，全局美元预算初值每日 1 美元，只在真正远端并行查询时扣减；按每人每日 5 次检索、15% 需要联邦估算，1 万日活的联邦请求若全走 OpenAlex，约每日 7.5 美元，而免费额度每日 1 美元。联邦未命中的查询回灌为候选收割键，只存规范化查询与用户计数，达到 `k_cf` 或经匿名复核才纳入。
- **审计与密钥**：每次出站尝试在 FetchLog 恰有一行，含被拒、重试、挑战与超时。部署级上游 key 只由网关读取（docker secrets 或 0600 文件）；登录用 OAuth 客户端密钥归认证服务。
- **模型路由**：只放行可共享数据；查询文本、画像、笔记属个人数据，只能用自托管模型。

## 受限全文在用户侧取回

- **放置**：每个来源通道声明 `exec_side`。`platform` 通道只在平台工作者执行；`user` 通道（受限全文、用户本人 key 的 TDM API）只在扩展或 pc-agent 执行，须用户显式触发、单篇、不预取。理由：SERU、EZproxy 等订阅条款约束代取，数据中心出口易被判为账号共享，系统性下载可能导致整个机构被暂停。
- **流程**：用户点"全文" → API 按策略签发 RetrievalIntent（签名、绑定会话、≤5 分钟有效、不含凭证）→ 扩展验签，按 `oa_link` > `tdm_api` > `user_fetch` > `open_in_tab` 选方式，用本人会话与网络取回 → 只回报不含内容的回执。
- **`user_fetch` 条件**：用户显式点击的单篇取回属于本人浏览，不按爬虫处理；另须 ToS 不禁自动化、不在冷却期、用户已授权该域，否则开可见标签页交给用户（规则见 [08](08-compliance-security-privacy.md)）。具名禁止 AI 爬虫的站点只提供"在出版社打开 + 一键保存"。
- **端侧纪律**：同一出版商域串行、间隔 ≥6 秒；单域每日至多 200 次尝试；遇挑战即停，冷却 24 小时。
- **pc-agent**：复用 v1 认证框架与 AES-GCM 凭证库，执行用户级 TDM API 与机构 EZproxy/SSO，只回报回执。
- **默认**：platform 默认"在出版社打开"，未装扩展只给外链；扩展先做 Chromium 系。
- **`deployment.host_is_user_device`**（默认 false）：云主机上的 personal 部署出口是数据中心 IP，仍只能走扩展；声明运行在本人设备上，意图才派给同机 pc-agent。
- **私有 PDF**：platform 默认只存用户设备，PWA 经扩展在本机取字节、用 pdf.js 阅读，不经平台。多设备同步默认关闭，只传端到端密文，服务端不可解密；会话 Cookie 不同步（见 D-054）。"用你的权限"状态只在用户侧计算。
- **personal 的 OA 批量取回**（Could）：只在 `host_is_user_device=true` 时进入本人私有空间；云主机上的 personal 改由共享层承接，只收许可允许再分发的 OA 全文。
- **私有全文不发第三方 LLM**；唯一例外是 personal 本机部署，须同时满足用户单独同意、来源许可允许、零保留条款三道闸。

## API 面

- **契约**：资源式 REST，前缀 `/api/v2`；OpenAPI 3.1 由代码生成并随代码提交，前端客户端从契约生成，CI 检测破坏性变更。错误体用 RFC 9457，列表用游标分页，写接口幂等（`event_id` 或 `Idempotency-Key`）。
- **出网字段**：一律经展示闸序列化，带 `display_scope` 与来源署名；AI 生成字段带机器可读的 `ai_label`。
- **认证**：PWA 用服务端会话 Cookie 加 CSRF 校验；登录用邮箱密码、ORCID OAuth 或可选通用 OIDC（只用于平台登录，绝不用于取出版商会话）。扩展与 pc-agent 用 OAuth 2.1 授权码 + PKCE，访问令牌 15 分钟。
- **主要资源**：`/me`（导出、删除、同意、检索历史）；`/feed/{surface}/next` 与"再来 10 篇"（每日总上限 60）；`/events`（每批 ≤50 条）；作品与 LOOKUP；`/search`；用户频道（可并、交、差组合，预览只查本地）；文献库；兴趣、个性化开关与关注；冷启动；原理公示；研究者匹配（默认关闭）；`/sources` 名录；`/retrieval-intents`（无批量签发入口）；申诉。管理接口只在 `api-admin`。
- **流式检索**：`POST /search` 的响应直接以 SSE 事件格式流式返回，事件为 `snapshot`、`upgrade`、`append`、`source_status`、`suggest`、`done`、`error`：先发本地结果，远端逐源补齐，`done` 必达并列出缺失来源。事件同步写入 PG 结果快照，断线凭 `Last-Event-ID` 从任一副本续传。不拆成"先 POST、再 GET"，因为多副本下两次请求可能落到不同进程。
- **版本**：v2 内只加不改；破坏性变更进 `/api/v3`，与 v2 并行 ≥180 天；对扩展与 pc-agent 保持 N-1 兼容；事件契约由 06 独立版本化。

## 关键非功能设计

- **性能预算**（T1 设计目标）：取下一批 p95 ≤300 ms；本地检索端到端 p95 ≤800 ms；联邦总截止 3 秒；滑动到下一张可交互 ≤100 ms；事件到达后模型生效 p95 ≤2 秒；频道硬命中进 FeedInbox p95 ≤30 分钟。
- **取批降级链**：预计算批块 → 在线候选管线（约 235 ms）→ 快路径（150 ms，只用 FeedInbox 与缓存候选池）→ 非个性化批块。
- **重排**：纯 CPU 的 T1 从小模型 int8、top-50 起步，top-100 为上限；超预算先发 RRF 结果、再以 `upgrade` 补发，占比 ≤5%。
- **降级**：关键能力（DOI 元数据 LOOKUP、最新论文收割、OA 定位、标题精确匹配）至少两级同能力替补。网关宕机时检索只回本地、收割积压不丢；推理服务故障时检索降为纯 BM25。
- **异步**：领域写入与出箱事件同事务，relay 转入 PG 原生队列 procrastinate（pgqueuer 备选）；至少一次投递，消费者幂等（见 D-069）。
- **事件**：训练用反馈必须绑定服务端生成的 `impression_id`，否则分不清"没下发"和"没看见"（见 D-062）；"不感兴趣"与屏蔽这类强负反馈在接入事务内同步生效。
- **可观测**：OpenTelemetry 日志、指标与追踪；日志里用户只用 HMAC 假名。可用性 ≥99.5%/月、新鲜度（日历型源 ≤6 小时、增量源 ≤24 小时）为设计目标，V0 实测后固化。
- **成本**：LLM、嵌入与计量 API 合计 ≤300 美元/月。
- **备份与删除**：pgBackRest 做 WAL 与基础备份，由备份主机拉取；RPO ≤5 分钟，RTO ≤4 小时。删除请求与法定日志留存冲突时留存优先，但收到请求即假名化，期满即删（见 D-067）。
- **架构参数**：
  - `platform.commercial`（默认 false）：切到 true 时停用限非商业的来源、模型与数据，下架 NC 派生的共享工件；须预检与四眼复核（见 D-045）。
  - `region`（默认 global）：按部署单元固定，不在运行期切换（见 D-057）；为 cn 时 LLM 只用已备案模型并完成属地登记与公示，自托管不等于备案，个人信息境内存储。
  - 特性开关默认关闭：公开评论、研究者匹配、公开收藏列表、平台私有增益、私有 PDF 同步，以及 OA 共享缓存（许可闸精度验证通过前）。

## 技术栈与许可

- **后端**：Python 3.12+、FastAPI、Pydantic v2、psycopg 3、httpx；PostgreSQL 18 + pgvector + pg_textsearch + pg_roaringbitmap；队列 procrastinate；缓存 Valkey（Redis 8 许可不合）；图批算 rustworkx。
- **前端**：React 19 PWA（Vite、Motion、Base UI），pdf.js 阅读；原生端延后到 v2.x。
- **许可门禁四级**（见 D-044）：
  - 放行：Apache-2.0、MIT、BSD-2/3、ISC、PostgreSQL、PSF、Blue Oak、Unlicense/CC0、zlib，以及未修改的 OFL 字体；
  - 评审：LGPL、MPL-2.0 在不修改、以库形式动态导入时放行，因此保留 psycopg 3；
  - 可选：AGPL、SSPL、BUSL 与限非商业组件，默认关闭，如 ParadeDB、Zotero translation-server、Grafana（只作独立运维进程）；
  - 禁止：没有 LICENSE 的仓库只借思路，不引入代码。
- **不进默认路径**：FalkorDB、Memgraph、Redis 8、Citus 等许可冲突组件，限非商业的模型与数据，已停更组件，盗版源、Google Scholar 自动化与绕封锁组件。
- **CI 门禁**：依赖许可与漏洞扫描；模型与数据注册表记录许可与 `commercial_ok`。

## v1 模块复用

- **v1 冻结**：v1 CLI 与 SQLite 只修缺陷，也不改成 v2 API 客户端；v2 运维命令由自带的管理 CLI 提供（见 D-042）。
- **直接复用**：`ids.py`（标识符规范化）、`errors.py`、`sensitive.py`（脱敏规则）、`adapters/_oai.py`、`subs/watermark.py`（重叠窗口加标识符去重，复用价值最高）、`pipeline/fetchio.py`（暂存与魔数校验）、`auth/challenge.py`（挑战特征库）。
- **包装**：v1 adapter 经 `v1_bridge` 映射为来源通道，出站改经网关。
- **改造**：`http.py`、`ratelimit.py`、`pipeline/cooldown.py` 并入网关；`merge.py` 演进为去重聚类；`registry.py` 演进为 SourceSpec v2 加载器，62 个 VenueSpec 一次性转换；订阅 DSL 演进为 Query AST。
- **只用在用户侧**：`auth/`、`browserfetch.py` 以及 Elsevier、Wiley、OUP 全文 adapter，只在 pc-agent 中运行；打包时与平台分离，平台镜像中不可导入。
- **冻结不用**：SQLite 仓储、`tasks.py`、六阶段编排、v1 CLI 与报告；SSRN 改由 Crossref 按 DOI 前缀承接（见 D-051），dblp 改用 DROPS 快照（见 D-050）。
- **迁移**：只读 v1 库，经 COPY 写入 PG；订阅转为用户频道；索引、向量与聚类在 PG 侧重建，不搬运。

## 怎么验收

- **V0**：同一镜像双部署；除网关与 Edge 外任何容器连公网全部失败；未登记主机与 `exec_side=user` 请求 100% 拒绝；FetchLog 每次尝试恰有一行；OpenAPI 无破坏性变更；许可扫描零命中（AC-V0.13–V0.20）。
- **V1**：24 小时并发回放中 arXiv 间隔 ≥3 秒零违例；重试、熔断、挑战冷却与 robots 先行按规则生效；商用与地区开关演练通过（AC-V1.x）。
- **V2**：300 万语料上本地检索 p95 ≤800 ms；≥99% 联邦请求 3.2 秒内收到 `done`；多副本断线续传完整；卡片流、频道预览与"最新"零远端调用（AC-V2.x）。
- **V3**：没有"读 `usr` 又写 `corpus`"的角色；RLS 越权测试全过；用户侧回报中零凭证、零 PDF 字节；PITR 演练与 v1 ETL 通过（AC-V3.x）。
- **V4**：1 万模拟用户下取批 p95 ≤300 ms；个性化组件全挂时仍返回非个性化批次；强负反馈当次生效；`open_fulltext` 不进公共信号（AC-V4.x）。

## 未决事项

- **默认假设**：非商业、不面向中国大陆公众、不买 OpenAlex 与 Crossref 付费档、robots 与文档化 API 冲突时从严；假设一变，架构参数与验收随之变。
- T1 单机的 PG 单点是否可接受；要高可用须加第二台主机（待用户定）。
- 联邦配额初值与何时启用付费数据档；各地区的 LLM 提供方。
- 哪些出版商可放行扩展的 `user_fetch`（待法务意见）；扩展在 Firefox、Safari 上的时间表与商店审核风险。
- 多设备凭证同步是否进入 v2.0；personal 是否提供非 docker 安装。
- 待实测：PgBouncer 事务池与 `SET LOCAL` 的配合；扩展向 PWA 分块传 PDF 的方式；T1 规格与延迟预算。

---

完整草稿（含组件逐项详述、网关与放置器伪代码、compose 服务表、关键时序、REST 资源全表、容量估算、降级矩阵、测试方法与全部验收条目、v1 模块逐项映射、异议与评审记录）：`git show v2-drafts:docs/plan/v2/02-architecture.md`
