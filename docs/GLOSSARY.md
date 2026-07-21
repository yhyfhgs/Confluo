---
title: 术语表（Glossary）
status: review
owner: fable5
updated: 2026-07-21
---

# 术语表

> 全库文档共用术语的单点定义。每条给出权威出处；本表只作速查，语义冲突时以出处文档为准。按主题分组，组内按逻辑序。

## 1. 领域对象（数据模型，详见 [design/06](design/06-data-model.md)）

| 术语 | 定义 |
|---|---|
| **Venue** | 一个文献来源单位：期刊 / 会议 / 预印本频道（`kind` 三值）。如 `jfe`、`iclr`、`arxiv-cs-lg` |
| **VenueSpec** | 描述一个 venue 的声明式 YAML 配置（`venues/**/*.yaml`），含标识符、平台绑定、认证需求、限速覆盖（[design/02 §2.2](design/02-plugin-framework.md)） |
| **VenueEra / era** | venue 的一个"年代段"：会议每届一条（官网年年漂移），期刊平台迁移时开新段；era 决定该年代用哪个 adapter（(venue, year) 二维路由，[design/08](design/08-venue-tracking.md)，D-012） |
| **Issue** | 期刊的卷/期、会议的届/track；预印本无期概念，用**虚拟月度桶**统一（如 `cs.LG/2024-07`） |
| **Paper** | 论文实体；主键为内部 ULID，**不用任何外部 id 做主键**（D-007） |
| **PaperStub** | enumerate 阶段产出的论文元数据载体（入库前形态，[design/02 §3](design/02-plugin-framework.md)） |
| **Identifier** | 论文的外部标识（doi/arxiv/ssrn/dblp/…），(scheme, value) 全局唯一——跨源**强合并的锚点** |
| **Asset** | 论文的一个可下载产物：pdf / si（补充材料）/ html / bibtex / source，含版本与校验信息 |
| **AssetPlan** | resolve 阶段产出的"获取计划"：URL + 认证需求 + `url_strategy`（见 §3） |
| **Fulltext** | extract 阶段产出的全文文本/结构化产物指针（1─1 于 paper） |
| **preprint_of** | 预印本→刊发版的关系边；两版**保留双条 paper 双份全文**，不合并（D-007） |
| **candidate_duplicate** | 弱信号（标题+作者模糊匹配）疑似同文关系，**只进人工候审队列，绝不自动合并** |
| **paper_count_claimed** | 源头宣称的每期篇数，用于枚举完整性对账（[design/08 §6](design/08-venue-tracking.md)） |

## 2. 插件与路由（详见 [design/02](design/02-plugin-framework.md)）

| 术语 | 定义 |
|---|---|
| **PlatformAdapter** | 按"出版平台"组织的代码插件（一个平台一包，~40 个覆盖数百 venue，D-002/D-015） |
| **SourceAdapter 协议** | 全部 adapter 实现的统一接口：discover_timeline / enumerate_issue / resolve_assets / fetch_asset / search / healthcheck |
| **Capability** | adapter 的能力声明位（DISCOVER/ENUMERATE/RESOLVE/FETCH/SEARCH）；**能力缺失即路由**——缺的阶段由 Registry 转交 metadata_source |
| **family** | adapter 三族：`open_access`（无认证）/ `auth_gated`（自有凭证）/ `aggregator`（元数据层）；同一协议，仅绑定不同（D-003） |
| **metadata_source / fulltext_source** | 同一 venue 的"元数据从哪来"与"全文从哪来"可以不同（D-005：期刊=Crossref、会议=DBLP 做元数据主干，出版社站点只做全文） |
| **VenueRegistry** | 启动时加载/校验全部 VenueSpec 并构建 (venue, year)→adapter 路由表的组件；`venues lint` 是其 CLI 形态 |
| **quirks** | VenueSpec 中平台 adapter 自定义的自由参数段（如 PMLR 的 volume_map、OpenReview 的 venue id 模板） |
| **entry points** | Python 包机制，第三方 pip 包声明 `paper_crawler.adapters` 组即被发现——"可插拔"的插口 |

## 3. 获取与认证（详见 [design/04](design/04-auth-gated-module.md)、[07](design/07-auth-session.md)）

| 术语 | 定义 |
|---|---|
| **HttpFetcher / BrowserFetcher** | L2 两种取回基建：httpx 直连 / Playwright 浏览器上下文（adapter 不自选，按 AssetPlan 路由） |
| **url_strategy** | AssetPlan 的取回方式声明：`direct`（直链）/ `render_page`（需渲染或一次性 token）/ `api_call`（官方 API） |
| **AuthProvider** | 认证服务四实现：CookieSession（首登人工→复用）/ EZProxy（URL 重写）/ SSOFlow（Shibboleth 等）/ APIKey |
| **AuthProfile** | 一套具体认证配置（如 `elsevier@campus` 与 `elsevier@ezproxy`）；运行时按 active_profile 选择 |
| **storage_state** | Playwright 序列化的登录态（cookie/localStorage）；加密落盘复用，**永不入 git** |
| **Shibboleth / OpenAthens / SeamlessAccess** | 学术界机构 SSO 三件套：SAML 联邦协议 / 托管联邦服务 / 出版社统一"机构登录"入口层 |
| **EZProxy** | 高校代理：URL 重写为 `www-xxx-com.proxy.univ.edu` 形态换取校外访问；对 adapter 透明（L2 统一重写） |
| **entitlement** | "当前凭证对该内容是否有权限"；能预检则预检（Elsevier 有 API），否则页面启发式判定 |
| **探针 URL** | 各平台声明的"已登录判定页"（不重定向到 login 且含账号标识）——health_check 的检测点 |
| **session 健康门** | 批量下载中每 20 篇/15 分钟强制 health_check——防止 session 失效后连续 401 轰炸（AC-4.2） |
| **TDM / TDMRep** | Text & Data Mining；TDMRep 是出版社机器可读的挖掘授权信号（HTTP 头 `tdm-reservation`），本系统尊重（D-014） |
| **polite pool** | Crossref 的礼貌通道：UA 带 mailto 换更高限速——"诚实身份换资源"的行业惯例 |

## 4. Pipeline 与任务（详见 [design/05](design/05-pipeline.md)）

| 术语 | 定义 |
|---|---|
| **六阶段** | discover → enumerate → resolve → fetch → extract → ingest；阶段间只经持久化实体通信，各阶段幂等（D-004） |
| **幂等键** | 每类任务的天然去重键（如 fetch=asset_id）；断点续爬=重跑时按键跳过已完成 |
| **新鲜度策略** | DONE 任务再次请求时的跳过/刷新规则：时间轴 24h、清单 7d、asset 永久（`--force` 覆盖） |
| **BLOCKED** | 任务状态：需人工介入（认证失效/风控/配置缺失），**不占重试、不自动恢复**；`resume` 转回 PENDING |
| **error_class** | 统一错误分类九类（transient/rate_limited/auth_expired/no_entitlement/challenge/gone/parse/integrity/config）——决定重试与升级路径 |
| **dry-run** | 只跑到 resolve 为止，报"将下载 N 篇"不落盘（FR-05）；新订阅上线前必跑 |
| **backfill** | 历史全量回填（低优先级队列）；**bulk 数据优先**，绝不在线翻爬全史 |
| **watch** | 订阅增量运行（cron 触发一次性进程）；游标见 watermark |
| **watermark** | 订阅的增量游标，亦称"水位线"（arXiv=submittedDate 上界+重叠 1 天窗；SSRN=近 N 页 id 差分）；Phase 2 arxiv 以"当月桶+整窗收割"隐式表达，显式游标随 Phase 6 |
| **收割 / harvest** | OAI-PMH 场景的批量元数据拉取（`ListRecords` + resumptionToken 翻页）；见 design/adapters/arxiv.md §3 |
| **guard / 熔断** | 订阅护栏：单次新增超 `max_new_per_run` → 零入库+过载报告（FR-16，AC-6.2） |
| **FetchLog** | 资产取回审计表（脱敏 URL/字节/耗时/限速等待）——限速合规的证据源（AC-4.4）；metadata 侧请求的审计证据为 obslog jsonl（Phase 2 勘误口径） |
| **日配额 / 工作时段窗** | auth_gated 纪律：单平台每日下载上限（默认 200；敏感站更低）+ 默认 8:00–23:00 运行窗 |

## 5. 测试与质量（详见 [testing/test-plan](testing/test-plan.md)）

| 术语 | 定义 |
|---|---|
| **T1–T6** | 六类测试：单元 / 契约 / fixture 回放 / 集成(mock) / 在线冒烟+canary / 手动 runbook |
| **fixture 三件套** | 每 adapter 最低快照配置：正常 listing 页 + 正常详情页 + 一种异常页（+auth 族四件套：登录/跳转/无权/风控页） |
| **golden** | fixture 的期望解析输出（JSON）；golden 变更必须人工过目（防错改固化） |
| **canary** | 已知答案的在线哨兵样本（如"ICLR 2024 应有 N 篇"）；周跑产出 adapter 健康矩阵，漂移早发现 |
| **runbook** | 需真实凭证的手动测试脚本清单（登录/下载/过期演练），结果留痕 testing/records/ |
| **DoD** | Definition of Done：各 Phase 的完成判据（development-plan 各节） |

## 6. 流程与治理

| 术语 | 定义 |
|---|---|
| **docs-as-code** | 全部非代码文本入 git 与代码同库演进（D-008）；INDEX.md 为唯一权威清单 |
| **front matter 状态机** | 文档五态 draft→review→approved→implemented→deprecated；**代码开工硬门禁=对应设计 approved**（D-010） |
| **ADR / D-xxx** | 架构决策记录（decision-log.md）；append-only，推翻旧决策用新条目 supersedes |
| **tier T1/T2/T3** | venue 范围分级：必做核心 / 平台已支持配置即得 / 登记暂缓——范围膨胀的闸门（R5） |
| **conventional commits** | 提交信息规范 `type(scope): subject`，body 关联 FR/AC/D 编号（git-workflow §2） |
| **[LIVE] / ⚠ 未核验** | 事实标注约定：当日实测验证 / 未经验证需实现期复核（doc-conventions §3） |
