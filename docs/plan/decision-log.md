---
title: 架构决策记录（ADR）
status: approved
owner: fable5
updated: 2026-07-27
---

# 架构决策记录（Decision Log / ADR）

> 格式：每条决策一节，编号 D-NNN 单调递增，永不复用。推翻旧决策时新增一条并注明 `supersedes: D-XXX`，旧条目标注 `superseded-by`。
> 状态：`accepted`（生效）/ `proposed`（待定）/ `superseded`（被取代）。

---

## D-001 目标技术栈假设：Python 3.12+ / httpx / Playwright / SQLite→PostgreSQL

- 状态：accepted · 日期：2026-07-20
- **背景**：设计文档需要一个具体技术底座假设，否则接口与伪代码无从谈起。
- **决策**：实现语言 Python 3.12+；HTTP 层 `httpx`（异步）；浏览器自动化 `Playwright`；存储初期 `SQLite`（WAL 模式），预留升级 `PostgreSQL` 的迁移路径；数据模型用 `Pydantic v2`；CLI 用 `typer`。
- **理由**：学术数据生态（arxiv.py、pyalex、openreview-py、habanero、semanticscholar）几乎全部是 Python；Playwright 的 `storage_state` 与 persistent context 是维持登录会话最成熟的方案；单机个人工具 SQLite 足够且零运维。
- **影响**：所有设计伪代码按 Python 风格书写；但 adapter 协议、pipeline 语义与语言无关，若未来换栈设计仍成立。

## D-002 可插拔核心：Platform Adapter × Venue Spec 两层结构

- 状态：accepted · 日期：2026-07-20
- **背景**：目标 venue 数量为几百（期刊+会议），逐站写爬虫不可维护。观察到学术出版高度平台化：JF/ECMA→Wiley，QJE/RFS/REStud/RF→OUP(Silverchair)，JFE/JME/JET→Elsevier ScienceDirect，MS/OR/MSOM→INFORMS PubsOnline，ICML/AISTATS/COLT→PMLR，CVPR/ICCV→CVF，ACL 系→ACL Anthology，KDD/WWW/STOC/EC→ACM DL，ICASSP/ICRA→IEEE Xplore。
- **决策**：代码级插件按**平台**组织（PlatformAdapter，预计 15~25 个）；每个期刊/会议是平台上的一条**声明式配置**（VenueSpec，YAML），声明其平台、标识符（ISSN/DBLP key/OpenReview id）、URL 参数、认证需求、限速覆盖。特殊站点（arXiv、SSRN、NBER、AEA、Econometric Society）各自独占一个 adapter。
- **理由**：新增期刊的边际成本从"写一个爬虫"降为"写 30 行 YAML"；平台改版只修一个 adapter；与 Zotero translators 的实践一致（per-site 逻辑 + 通用框架）。
- **影响**：注册表、能力声明、测试组织都按两层设计（见 design/02）。

## D-003 双模块划分：open_access 与 auth_gated 共享同一 Adapter 协议

- 状态：accepted · 日期：2026-07-20
- **背景**：需求要求区分"开源直接可下载"与"需登录/SSO"两类站点。
- **决策**：两个获取模块不是两套接口，而是同一 `SourceAdapter` 协议的两种 **fetcher backend 绑定**：`open_access` 绑定 httpx 直连（无认证），`auth_gated` 绑定 `AuthProvider` + （必要时）Playwright 浏览器上下文。Adapter 通过 `capabilities()` 声明自己需要哪种 backend 与认证等级（`none / free_account / subscription / institutional`）。
- **理由**：pipeline、数据模型、任务调度对两类源完全同构，仅"怎么发请求"不同；单一协议避免上层出现 if/else 分叉。
- **影响**：SSRN 这类"匿名可下载但受限、登录后更稳"的站点可声明双等级，运行时按可用凭证降级/升级。

## D-004 六阶段 Pipeline：discover → enumerate → resolve → fetch → extract → ingest

- 状态：accepted · 日期：2026-07-20
- **决策**：pipeline 固定六阶段，每阶段幂等、以持久化任务为边界、可独立重跑：
  1. `discover`：获取 venue 的出版时间轴（卷/期/届清单，VenueEra）；
  2. `enumerate`：展开某期/届的论文清单（元数据级）；
  3. `resolve`：把每篇论文解析为可下载资产列表（PDF/SI/HTML 的最终 URL + 所需认证）；
  4. `fetch`：按资产下载落盘（限速、断点、校验）；
  5. `extract`：本地解析（PDF 元数据核对、全文文本抽取，GROBID 为可选后端）；
  6. `ingest`：入库（去重合并、identifier 关联、索引更新）。
- **理由**：阶段边界即断点续爬边界；"清单先行、下载置后"支持 dry-run 计数与选择性下载（需求 FR 明确要求指定期数/文章）。
- **影响**：任务表按 (stage, venue, params) 建幂等键；CLI 动词与阶段对应。

## D-005 元数据主干走聚合 API，官网站点只做全文与补充

- 状态：accepted · 日期：2026-07-20
- **背景**：出版社 HTML 页面反爬强、易改版；而 Crossref/OpenAlex/DBLP/Semantic Scholar/OpenReview 提供稳定结构化元数据。
- **决策**：`discover/enumerate` 阶段**优先**走聚合 API（期刊：Crossref 按 ISSN 枚举 DOI + OpenAlex 补充；会议：DBLP 卷目录 + OpenReview/PMLR/CVF 官方结构）；出版社站点 adapter 主要承担 `resolve/fetch`（拿全文）与少数聚合源缺失的字段。每个 VenueSpec 声明其 `metadata_source` 与 `fulltext_source` 可以不同。
- **理由**：把"脆弱的爬取面"压缩到最小；历史期数枚举在 Crossref/DBLP 一次 API 调用可完成，无需翻页爬 archive。
- **影响**：数据模型必须支持同一 venue 的元数据与全文来自不同 source（见 D-007 去重）。
- **2026-07-20 修订（依据 research/site-survey/metadata-apis.md 实测）**：原设想以 OpenAlex 为免费主干，但 OpenAlex 已于 2026-02-13 取消免费 polite pool 改为信用计费制。故主干调整为：**期刊 = Crossref（ISSN+日期，仍免费 polite pool 10 req/s）**；**会议 = DBLP（conf XML 卷目录，CC0）**；OpenAlex 降为补充层（摘要倒排重建、OA 链接发现、topics），按信用预算受控调用；Semantic Scholar 作次级补充（需申请 key，1 req/s）。三源分工表见 metadata-apis.md。

## D-006 认证设计：人在回路首次登录 + storage_state 复用 + 绝不对抗风控

- 状态：accepted · 日期：2026-07-20
- **决策**：`AuthProvider` 抽象四种实现：`CookieSession`（Playwright 有头首登→加密保存 storage_state→headless 复用）、`EZProxy`（URL 重写 + 一次登录）、`SSOFlow`（Shibboleth/OpenAthens，首登人工完成含 MFA）、`APIKey`（Elsevier/Wiley TDM 官方 API）。凭证存 OS keyring 或加密文件，永不入 git。检测到 CAPTCHA/风控页一律转 `BLOCKED` 状态待人工，不做自动破解。官方 API 存在时优先于页面爬取。
- **理由**：合法、稳定、可维护；学术出版社对机构订阅的自动化下载有明确 ToS 约束，保守策略是长期可用的前提。
- **影响**：pipeline 必须有 `BLOCKED` 任务状态与人工介入 CLI；测试计划包含"session 过期→重登"场景。

## D-007 跨源同文合并：Identifier 图 + preprint_of 关系

- 状态：accepted · 日期：2026-07-20
- **背景**：同一研究常同时存在 arXiv 预印本、SSRN 工作论文、期刊正式版。
- **决策**：`Paper` 不以单一外部 ID 为主键，内部 ULID 主键 + `Identifier` 多值表（doi/arxiv_id/ssrn_id/openalex_id/s2_id/dblp_key…）。合并策略：强标识符（DOI 精确匹配、arXiv id）自动合并；弱信号（标题+作者模糊匹配）只建 `candidate_duplicate` 边待确认。预印本与正式版默认**不合并为一条**，以 `preprint_of` 关系互联，两版全文都保留。
- **理由**：金融/经济领域 working paper 与刊发版差异巨大（标题都会改），激进合并会丢信息。
- **影响**：查询层需提供"按研究聚合"视图；ingest 阶段含 candidate 审核队列。

## D-008 文本系统：docs-as-code + front matter 状态机 + INDEX 单一索引

- 状态：accepted · 日期：2026-07-20
- **决策**：所有非代码文本（计划/进度/设计/测试记录/日志/报告）以 markdown 存于 `docs/` 树，随 git 版本化；每篇文档带 YAML front matter（title/status/owner/updated）；`docs/INDEX.md` 是唯一权威索引；日志按 session 追加于 `docs/logs/`，阶段报告于 `docs/reports/`。
- **理由**：与代码同库同 PR 演进，LLM/人类都可全文检索；状态机让"哪些设计已定稿可开工"机器可判。
- **影响**：AGENTS.md 把 INDEX 同步、日志留痕定为硬义务。

## D-009 Git 流程：trunk-based 轻量变体，设计阶段直提 main，实现阶段强制分支

- 状态：accepted · 日期：2026-07-20
- **决策**：单人+AI 协作项目采用 trunk-based：`main` 始终可用；实现阶段一律 `feat/*`、`fix/*`、`docs/*`、`adapter/*` 短分支 + PR 自查清单合入；conventional commits；阶段完成打 tag `phase-N`。设计阶段（无代码）允许直接提交 main。敏感产物由 .gitignore 硬隔离。
- **理由**：流程成本与项目规模匹配；分支语义为未来多 agent 并行（每 adapter 一分支）预留。

## D-010 双状态机：文档 status 与模块 dev-status 联动

- 状态：accepted · 日期：2026-07-20
- **决策**：文档状态机 `draft→review→approved→implemented→deprecated`；代码模块状态机 `planned→spec_approved→in_dev→testing→stable→deprecated`。联动规则：模块进入 `in_dev` 的前置条件是对应设计文档 `approved`；模块 `stable` 后设计文档转 `implemented`；文档实质变更需评估是否把关联模块打回 `testing`。
- **理由**：把"文档先行"从口号变成可检查的门禁（未来可做 CI 校验脚本）。

## D-011 SSRN 定位：预印本主源之一，匿名+免费账号双模式，严格限速

- 状态：accepted · 日期：2026-07-20
- **背景**：Econ/Fin 领域 SSRN 地位等同 arXiv 之于 CS，但 SSRN 无官方 API、有 Cloudflare 防护、下载路径含一次性 token。
- **决策**：SSRN 独立 adapter，归 open_access 模块但声明 `auth_level: free_account_preferred`；枚举走其 eLibrary 浏览页与 RSS；下载用 Playwright 上下文（复用匿名或免费账号 session）；限速默认 1 req/5s，日配额上限可配；被 Cloudflare 挑战即 BLOCKED 转人工。
- **理由**：SSRN 是 Fin/Econ working paper 不可替代的源，值得为其承担浏览器自动化成本；保守限速换长期可用。
- **2026-07-24 修订（依据 D-029）**：双模式重定——模式 A 聚合元数据升主路径、模式 B 浏览器全文降 opt-in 并 defer Phase 6（依据 R0a 勘察 [LIVE 2026-07-24]：SSRN 站点 CF 门双向证据 + crossref 10.2139=1.41M DOI 聚合侧完整可读；W0 双评审通过）。

## D-012 会议历年网址漂移：VenueEra 表 + DBLP 为历史主干 + 年度探测任务

- 状态：accepted · 日期：2026-07-20
- **决策**：每个会议每届一条 `VenueEra` 记录（year、official_site、proceedings_url、metadata_source、状态）。历史届用 DBLP conf 目录一次性回填；新一届靠年度定时探测任务（官网、DBLP 新卷、OpenReview 新 venue id、CFP 站点）生成候选，人工确认后入 registry。Wayback Machine 作为死链兜底。
- **理由**：会议官网域名年年变（thewebconf、各届 aaai.org/Conferences 子页），但 DBLP key（`conf/nips/2024`）与 proceedings 平台稳定——以稳定锚点组织历史，以探测任务追新。

## D-013 ACM DL 按 2026 全面 OA 新政归入 open_access 族

- 状态：accepted · 日期：2026-07-20
- **背景**：调研证实 ACM 自 2026-01-01 起全面开放获取（官方公告 acm.org/articles/bulletins/2026/january/acm-open-access），dl.acm.org 全部会议论文集免费全文；同时证实 SODA 出版方为 SIAM（epubs.siam.org，订阅制），不在 ACM DL。
- **决策**：`acm_dl` adapter 归 open_access 族（auth 能力保留为兜底开关）；新增 `siam` adapter（auth_gated）承接 SODA；受影响 venue（KDD、WWW、WSDM、CIKM、SIGIR、RecSys、STOC、SOSP、EC、SIGMOD/PACMMOD）auth.level 一律 `none`。
- **影响**：Phase 2 的 open_access MVP 范围可纳入 ACM 系会议；Phase 4 出版社清单相应缩减；catalog 与 adapter 文档按此口径撰写。同批调研亦确认 Papers With Code 已于 2025-07 关闭——从候选索引源中移除。

## D-014 尊重站点 AI-bot 指令：诚实 UA + robots/Content-Signal 遵守 + 敏感站白名单式抓取

- 状态：accepted · 日期：2026-07-20
- **背景**：调研[LIVE]发现多站在 robots.txt 用具名方式封禁 AI 爬虫——ScienceDirect 禁 20+ 个（含 `claude-code`、ClaudeBot、GPTBot…）、**CEPR 明确点名 ClaudeBot 且设 `ai-train=no`**、SSRN 禁 GPTBot/ChatGPT-User/Google-Extended。同时出现两个"可绕过软门"的经验发现（SSRN 内部 API、NBER 静态 PDF 路径）。
- **决策**：
  1. UA **诚实标明身份与用途**（`PaperCrawler/<ver> (personal research; mailto:<user>)`），不伪装成通用浏览器或搜索引擎 bot；
  2. **遵守 robots.txt 与 Content-Signal**：明确 `Disallow` 的路径不访问；`ai-train=no` 站点不做任何训练性用途（本系统本就只做个人检索下载，无训练用途）；
  3. **敏感站（CEPR 等点名禁止者）默认只取合法开放的元数据（经 RePEc 等第三方 bulk），不自动抓其全文**；需要全文时引导用户在其订阅内手动获取；
  4. **禁止依赖未文档化/软门绕过通道**（SSRN 内部 API、NBER 软门），写入 AC-0 与相关 adapter 文档 quirks 禁区；
  5. 合法机构订阅内容的获取（auth_gated 模块）不受本条限制——那是用户在自有权限内经正规登录的访问，与"无授权 AI 爬取"性质不同；但同样遵守各站 TDM/速率政策。
- **理由**：合规与长期可用性优先于覆盖率最大化；诚实身份+尊重站点声明是个人科研工具可持续的前提，也符合 AGENTS.md §6 红线。
- **影响**：各 adapter 文档必须记录目标站 robots/AI-bot/TDM 现状与本 adapter 的合规姿态；catalog 对敏感站标注获取边界。

## D-015 Phase-0 收官一致性审查的三项设计修正

- 状态：accepted · 日期：2026-07-20
- **背景**：Phase 0 完成后、Phase 1 开工前的全库一致性审查（用户指令触发；全过程见 [reports/2026-07-20-consistency-review.md](../reports/2026-07-20-consistency-review.md)）。对 `approved` 文档的实质修改按 status-workflow §1 规则以本条 ADR 记录理由，不降级文档状态。
- **决策**：
  1. **VenueSpec 校验收紧**（design/02 §2.2）：期刊 **issn 必填**；`openalex_source` 降为可选补充字段，不再可替代 issn。理由：D-005 修订后 Crossref（按 ISSN）是期刊元数据主干，OpenAlex 信用计费制下不能作为枚举依赖。
  2. **CLI 增补 `grab --url`**（design/05 §6）：单篇精取支持无标准标识符的来源（ECCC、个人主页 WP 等）；identifier 相应增加开放 scheme `url`（design/06 注释同步）。理由：Econ/Fin WP 场景常见无 DOI 无平台 id 的合法直链。
  3. **adapter 总量预估修正**：D-002 原估"15~25 个"，经四域 catalog 全量盘点为 **~40 个**（首批详设 16 + planned ~24，其中 8 个为审查中补登记：ijcai/jmlr/jair/bmvc/tandf/annual_reviews/now_publishers/uwpress）。D-002 原文不改（ADR append-only），活文档（publishers-platforms、SVG-02）已按新口径更新。
- **影响**：Phase 1 的 `venues lint` 按新校验规则实现；勘误类修复（8 项，不构成决策）清单见审查报告。

## D-016 第二轮深度审计：可追溯性与可读性增强批次

- 状态：accepted · 日期：2026-07-21
- **背景**：Phase 1 开工前第二轮审计（用户指令；第一轮为结构级 D-015，本轮下沉到语义级——数值口径、术语、需求↔验收双向映射、CLI 一致性；全过程见 [reports/2026-07-21-audit-round2.md](../reports/2026-07-21-audit-round2.md)）。
- **决策**（对 approved 文档的增补按 status-workflow §1 以本条记录，不降级）：
  1. **FR/NFR→AC 覆盖映射总表**（acceptance-criteria.md 附表）：审计发现 7 条 FR 在需求文档之外无显式编号回引——设计文档不逐条回引 FR，可追溯性统一经该表闭环；度量型 NFR（1/2/5/7）明确为"Phase 报告实测记录"验收形态。
  2. **术语表 GLOSSARY.md 新增**（docs/ 根，与 INDEX 平级）：50+ 全库共用术语单点定义+出处链接；解决 45 篇文档专有名词无处速查的可读性缺口。
  3. **INDEX 增加"按意图导航"层**：七条任务式阅读路径（理解系统/加 venue/写 adapter/合规/开发/查决策/查勘察）前置于逐目录清单。
- **影响**：新文档/新 FR/AC 的登记义务扩展——同步维护映射表与（若引入新术语）GLOSSARY；AGENTS.md §4 checklist 随本条更新。

## D-017 Phase 1 工具链与包布局

- 状态：accepted · 日期：2026-07-21
- **背景**：D-001 确定语言与核心库（Python 3.12+ / httpx / Playwright / SQLite / Pydantic v2 / typer），但未定构建工具、测试与质量工具链、包布局。Phase 1 开工（[phase1-implementation-plan](phase1-implementation-plan.md)）需要冻结这些实现载体决策。
- **决策**：
  1. **包管理与构建**：`uv`（uv.lock 入库）+ hatchling 后端；dist 名 `paper-crawler`、包名 `paper_crawler`、src 布局（`src/paper_crawler/`）、CLI 入口 `crawler`。
  2. **质量工具**：pytest + pytest-cov（core 覆盖率门禁 ≥80%，test-plan §6）、ruff（lint+format）、mypy（对 src 全量检查）。本地门禁 `make check`＝lint+type+test（test-plan §8 的 `make test` 细化）。
  3. **依赖最小化**：Phase 1 运行时仅 `typer`、`pydantic>=2`、`pyyaml`、`python-ulid`；**httpx 推迟到 Phase 2、Playwright 推迟到 Phase 4** 首个真实需求出现时引入（Phase 1 零网络，mock adapter 本地生成语料）。SQLite 经标准库 `sqlite3` 直接执行 DDL/DML，不引入 ORM——保持 SQL 方言中性（D-001 的 PG 迁移路径）。
  4. **FTS5 推迟**：design/06 §2 的 paper FTS5 虚表**不进 schema v1**，推迟到 Phase 6（搜索需求）以独立 migration 追加。理由：FTS5 是 SQLite 专有特性，与 06 文档"避免 SQLite 专有特性"的迁移原则冲突；推迟到需要时以附加虚表实现（可在 PG 侧以 tsvector 等价替换），主 schema 保持中性。
- **影响**：phase1-implementation-plan §Global Constraints 与各任务以本条为准；Phase 2/4 引入 httpx/Playwright 时无需新 ADR（本条已预留），版本约束届时在 pyproject 记录。

## D-018 AC-2.3（arXiv 订阅 7 日增量）验收证据分层

- 状态：accepted · 日期：2026-07-21
- **背景**：AC-2.3 字面要求"连续 7 日 watch，抽样 20 篇与官方 listing 比对无重复无遗漏"。CI 无法等待 7 个自然日；arxiv 详设评审（Phase 2 W0 双评审）指出若仅以离线回放+单次冒烟判定，与 AC 字面存在真实差距，不应静默弱化。
- **决策**：AC-2.3 证据分三层——①T4 fixture 回放模拟 7 个收割日（含重叠窗口与 announce 延迟注入，CI 化，证机制正确）；②T5 限量在线冒烟单日 1 次（证真实响应可解析入库）。**①+② 为 Phase 2 的 AC-2.3 判定依据**（验收记录标注"PASS（Phase 2 口径，D-018）"）。③真实连续 7 自然日 watch + 第 7 天抽样 20 篇人工比对官方 listing = T6 runbook，**随 Phase 6 AC-6.1 联合执行**，届时 AC-2.3 完成字面口径复验。
- **影响**：arxiv.md §6、phase2-implementation-plan T6/T7 按此口径；Phase 6 验收清单须包含 T6 runbook 执行；后续 7 日类验收（如 SSRN watch）沿用同分层模式。

## D-019 外源比对类验收的锚点快照模式（AC-2.1 首例）

- 状态：accepted · 日期：2026-07-22
- **背景**：AC-2.1 要求 timeline 与 DBLP 卷数"一致 ±0"，但 DBLP adapter 属 Phase 3、验收不能依赖在线拉取外源；openreview 勘察亦证实 2015/2016 届在两侧俱缺等特例需固化口径。后续 Stage B adapter（pmlr/cvf/acl 等）的完整性验收均将面对同构问题。
- **决策**：外源比对类 AC 以**人工核准的锚点快照（anchor golden 表）**为可执行判定：①快照由实现期程序生成（本例：带 token 按 venueid 过滤取 count）；②**人工对照外源页面核准**后入库（UPDATE_GOLDEN 纪律+records 留痕）；③特例（缺届/跨源）在表内显式标注；④验收判定=系统输出与快照全等。快照生成与核准过程记入验收记录。
- **影响**：openreview.md §7（AC-2.1 anchor 表）为首例；Stage B 各 adapter 的"与外源一致"类验收沿用本模式；与 D-018（时间维分层）互补——D-018 解"等不了的时间"，本条解"依赖不了的外源"。

## D-020 acm_dl 自动全文抓取 Phase 2 出列（红线优先），Phase 4 重评

- 状态：accepted · 日期：2026-07-22
- **背景**：D-013（2026-07-20 调研）确认 ACM 2026 全面 OA 并将 acm_dl 纳入 Phase 2、设 AC-2.6（pull kdd 无认证下载全文）。2026-07-22 LIVE 勘察（research 归档于 scratchpad/acm-survey，3 请求即按纪律停站）实测：①OA 拆付费墙未拆机器人墙——匿名非浏览器请求对 landing/PDF 一律 Cloudflare 挑战（`cf-mitigated: challenge`，403 拦截页）；②ToS 明文禁"scripts/spiders 自动下载/harvest metadata"（搜索摘录证据——政策页本身对脚本 403，原文未直接取得）；③无官方 API/OAI-PMH；④robots 放行 /doi/ 与 WAF 拦截矛盾——以更严者为准。
- **决策**：AC-0.2（不对抗挑战门）与 AC-0.5/AGENTS §6.3（ToS 合规）优先于 AC-2.6——**Phase 2 不实现 acm_dl 自动全文抓取**（无合规路径：httpx 必被拦；浏览器自动化仍属 ToS 禁止的 automated download 风险面）。AC-2.6 标注 deferred(D-020)，**Phase 4 重评**：届时人工核验 ToS 原文、官方 API/TDM 通道态势、挑战门策略；若仍无合规通道，acm 系会议降级为"元数据经 Crossref/DBLP（Phase 3 聚合层，member 320 实测畅通）+ landing 链接呈现 + 人工取回"。
- **附带事实**：KDD 2026 尚未出版（8 月会议，proceedings 仅 3 篇预注册）——AC-2.6 字面场景本期亦无内容；WWW 2026（10.1145/3774904，719+222 篇）为已出版代理候选，重评时可换载体。
- **影响**：Phase 2 范围 8→7 adapter（development-plan 注记）；acceptance-criteria AC-2.6 修订；acm-dl.md 维持 review 不重写（Phase 4 按届时事实重写）；Phase 2 收尾验收以 AC-2.1~2.5 + 各 adapter DoD 为准。

## D-021 Phase 3 开工勘察增量复核：DBLP robots 合规修正与聚合层口径定稿

- 状态：accepted · 日期：2026-07-22
- **背景**：Phase 3 详设扩写前对五源（crossref/dblp/openalex/s2/unpaywall）做 LIVE 增量复核（19 请求合规，报告归档 [metadata-apis.md §增量复核](../research/site-survey/metadata-apis.md)）。主勘察（2026-07-20）5 项断言漂移。
- **决策**：
  1. **DBLP 限速与能力面修正（合规级）**：robots.txt 实测 `Crawl-delay: 4` 且 `/search`、`/rec/xml` 等 Disallow → dblp adapter 限速 **≥4s/req**（原设计 1 req/2s 作废）；**capabilities 不含 SEARCH**，枚举只走 robots 允许区 `/db/**` 结构化 XML 与官方 dump。AC-0.5 从"FAQ 建议"升级为"robots 强约束"依据。
  2. **S2 无 key 检测口径**：症状已从 429 变为 404 not-found（被受理非限流）→ 错误检测与 healthcheck 不得依赖 429 判 key 缺失；"生产必须申请 key"结论不变。
  3. **合并优先级表补 dblp 位次**（phase3-implementation-plan §2-1 冻结件扩展）：`official > crossref > dblp > openalex > s2 > heuristic`。理由：Crossref 为 DOI 注册源头（出版社存缴）元数据居先；DBLP 人工策展（CC0）质量高于 OpenAlex/S2 机器聚合。
  4. **OpenAlex 预算核销精确化**：响应 `meta.cost_usd` 字段（[LIVE] 新发现）作为 credit 熔断的实时核销信号，取代估算制。
- **影响**：aggregators.md 扩写版（396 行）承载全部修正；勘察复核前置（Phase 2 REJECT 教训的制度化延续）再次在写代码前拦下合规缺陷。

## D-022 零网络 resolve 豁免限速闸 + --limit 前置圈选（C-C 修复语义定案）

- 状态：accepted · 日期：2026-07-22
- **背景**：Phase 2 终检置顶缺陷 C-C——`url_strategy=direct` 的 resolve 是零网络纯 URL 构造却逐篇过 per-domain 限速闸，且 `--limit` 在全量 resolve 后才截断：ICLR 2024（2260 篇）量级 pull 的 resolve 阶段数十分钟纯空转。
- **决策**：① adapter 以 `AdapterBase.resolve_offline = True`（类属性，非冻结协议成员，pipeline `getattr` 兜底，默认 `False` 安全侧）声明零网络 resolve，声明者 resolve 阶段免限速 token；本仓 8 个 adapter 逐个核实零网络后显式置 `True`（独立审查复核无错标）。② `--limit N` 前置：按 `list_papers` 稳定序（`ORDER BY (title, id)`，审查发现并修复并列标题 tiebreaker 缺口）圈选前 N 篇建 resolve 任务。③ 语义边界显式化：前 N 篇含零资产 paper 时落盘可 < N，不往后凑满（凑满与前置目标根本矛盾）；AC-2.2 类场景（camera-ready 恒有 PDF）不受影响。④ AC-1.4 限速压力测试测量窗收窄至稳态尾段（resolve 免闸后 burst 移至 fetch 起点），判据 ≤ 配置×1.05 不变。
- **影响**：design/05 §6 修订注记；2260 篇量级 resolve 壁钟从数十分钟降至秒级（回归测试锁定 <5s）；真实网络 resolve 策略的限速闸保留（反向 guard 测试锁定）。

## D-023 认证凭证库加密方案：cryptography>=42 AES-GCM 作 [auth] optional extra

- 状态：accepted · 日期：2026-07-23
- **背景**：Phase 4 认证框架（[design/07 §4](../design/07-auth-session.md) approved）要求 storage_state/cookie jar **AES-GCM 加密落盘**。评估（[auth-framework.md §3.2](../design/auth-framework.md)）：Python 标准库**无任何对称分组密码**（`hashlib`/`hmac` 仅摘要+MAC）→ AES-GCM 纯标准库不可行；`pynacl`（XSalsa20-Poly1305）与 07 §4"AES-GCM"字面不符。项目 D-017 依赖最小化姿态与"需加密但无 stdlib 原语"客观事实冲突。
- **决策**：取 **`cryptography>=42`，用 `AESGCM`**（AES-256-GCM，每文件随机 12B nonce，AAD 绑定条目名），**作为可选依赖** `[project.optional-dependencies].auth`（+ `keyring>=24` 主密钥存储）——**不进核心 `dependencies`**（Phase 1-3 聚合层零加密需求）。`auth/store.py` **惰性 import**：未装 `[auth]` 时需加密路径响亮 `CrawlerError(CONFIG, "pip install paper-crawler[auth]")`；**纯 APIKey 路径（elsevier AC-4.1 / wiley TDM）不触该依赖**（简单字符串密钥走 `[auth.<platform>]` Config-slot，两级凭证模型①，auth-framework §3.4）。主密钥 keyring 首选 → 无后端降级文件密钥（`state/.filekey` 0600）+ 显式一次性警告。
- **附注 1（P0a 开放题②合并裁决）**：`types.SessionHandle = Any` → 具体 frozen dataclass 系 `types.py:128` 注释显式预留的**计划内受控具体化**（`Any\|None`→`SessionHandle\|None` 精化，既有 adapter 零改动），非协议漂移，无需独立 ADR，随本条记录。
- **附注 2（A-M3 显式裁决转正：明文 Config-slot 与 07"加密配置"张力）**：①类**简单字符串密钥**（elsevier `api_key`/`insttoken`、wiley TDM `token`）走 `[auth.<platform>]` 明文 Config-slot（家目录 config、仓库外、0600、obslog 脱敏、env 覆盖）与 07 §4"加密配置"措辞的张力，**裁决为对既有惯例的诚实收敛**——沿 Phase 2/3 `[auth.s2].api_key`/`[auth.openreview].token` 已生效先例，**keyring 为可选加固层**（配置了即 `read_key` 优先取 keyring）；②类**有状态凭证**（storage_state/cookie jar）方走 AES-GCM `CredentialStore`。07 §4 文末加**修订注记指向本条**（不改 07 正文语义段）。完整 config 分层/敏感边界规范见 D-025 / [design/10-config-layout.md](../design/10-config-layout.md)。
- **影响**：pyproject 新增 `[project.optional-dependencies]`（auth / auth-browser）；`make check` 默认不 import 二进制依赖（惰性 + skip 门控）；**CI 标准环境统一装 `[auth]`**（`uv sync --extra auth`，凭证库测试进 CI，B-m7），`[auth-browser]`（重，Playwright）靠 `PC_BROWSER_TESTS` 手动门（auth-framework §10）——**cryptography/keyring/playwright 均不成核心路径硬依赖**。

## D-024 Phase 4 R0 平台勘察裁决：wiley 纳入（token 门控）+ acm_dl 维持出列（全文改道 unpaywall）

- 状态：accepted · 日期：2026-07-23 · 依据：[publisher-platforms-p4-recheck.md](../research/site-survey/publisher-platforms-p4-recheck.md) [LIVE 2026-07-23]
- **背景**：Phase 4 W0 R0 对四平台（Elsevier/OUP/Wiley/ACM）距 2026-07-20/07-22 原勘察做 3 天增量复核（实耗 5/25 在线预算，遇挑战/429 即停）。核心假设全部成立，无颠覆漂移；wiley/acm 两项需 controller 裁决。
- **决策**：
  1. **wiley 纳入本 Phase + token 门控**：TDM 端点 `api.wiley.com/onlinelibrary/tdm/v1/articles/{DOI}`、头 `Wiley-TDM-Client-Token`、速率 3 req/s + 60/10min **升级为活验**（GitHub `WileyLabs/tdm-client` v1.2.0 + 搜索索引二手确证）；token 可自助（WOL click-through TDM license，无邮件审批）但 entitlement 受订阅域约束。实现模式 = **完整 adapter + TDM 客户端 + token 存在性门控**（缺失→在线层 skip 不阻塞验收，s2 先例）；token 落 `[auth.wiley].token` Config-slot。**不整体顺延**（勘察稳定、实现风险低，顺延浪费已验证窗口）。双窗口限速经现有单 token bucket 表达（`RatePolicy(rpm=5-6, burst=3)`，[wiley.md §4](../design/adapters/wiley.md) 接缝结论：无需扩展 ratelimit.py 冻结件）。
  2. **acm_dl 维持 D-020 出列**（supersedes 无——延续 D-020 而非推翻）：出列两依据 R0 [LIVE] 复核**均未变**——(a) 全文挑战墙持续（OA 拆付费墙未拆机器人墙）；(b) ToS 明文禁 scripts/spiders 自动下载 + metadata harvest（[DOC] 原文未松）。**全文改道 unpaywall OA-fallback**（pipeline no_entitlement 兜底，auth-framework §8.1），**元数据维持 crossref+dblp**（畅通、不碰 dl.acm.org）；browser-fetcher 有限实现留待其落地后再评。
  3. **异常子类 + status_code 权威版归 T2**（P0a 开放题③）：`errors.py`/`http.py` 的 `AuthRequired`/`Challenged`/`status_code` 由 **T2 单一权威版**交付（T1/T2 同波，合并取 T2，沿 Phase 3 `ids.py` 约定）；健康门 N=20/15min、日配额 200、challenge 冷却 24h **确认沿 04 §4/§5 原文**（P0a 开放题）。
- **影响**：phase4-implementation-plan 新增 T-wiley 卡（W2 平台波第三件，opus/opus）+ 在线预算加 wiley 冒烟 ≤10（条件项）；elsevier-sd.md/oup-silverchair.md/wiley.md 扩写至实现级（status draft，待双评审）；acm-dl.md 维持出列口径不变；BLOCKER-1（elsevier key）/wiley token 缺失均计划内前置外部依赖，离线 DoD 不阻塞（D-018 分层）。

## D-025 config 归集：仓库内 config/ 规范文件夹 + 分层加载链 + 敏感边界护栏

- 状态：accepted · 日期：2026-07-23 · 依据：用户架构令（2026-07-23）
- **背景**：Phase 4 引入 elsevier/wiley 等多个 `[auth.*]` 凭证槽后，配置项分散、优先级隐晦、敏感边界无护栏（易误把 api_key 提交进仓库）。用户令：把配置规范归集、加显式分层与防误提交护栏，并为未来第三方凭证槽（Kaggle 等）立统一规范。
- **决策**（详设 [design/10-config-layout.md](../design/10-config-layout.md)）：
  1. **仓库内 `config/` 规范文件夹**：`README.md`（配置规范总纲：全部配置项分层/优先级/敏感边界）+ `config.example.toml`（全键注释样例，含 `[auth.*]` 全部槽）+ `profiles.example.toml`——**真实值绝不入**（仅样例/占位）。
  2. **加载链改造**：`env > 项目级 ./paper-crawler.toml（仅非敏感键）> config-home config.toml > 内置默认`；**项目级文件出现敏感键形态**（`api_key`/`token`/`insttoken`/`password`/`secret`/`credential`/`cookie` 等——正则匹配集与 obslog 脱敏键单一同源，详见 10-config-layout §3.1）→ `CrawlerError(CONFIG)` **拒启动**并指引挪至家目录/env（**防误提交护栏**）。
  3. **`crawler config show` 命令**：打印全部生效配置 + 来源层，**敏感值脱敏显示**（obslog redact 口径）。
  4. **第三方凭证槽归集规范**：未来 Kaggle 等一律 `[auth.<name>]` 槽、单一 config-home，不依赖各工具家目录约定（如 `~/.kaggle/kaggle.json`）。
  5. **敏感凭证物理隔离于仓库（AC-0.3）为不变式**，写入规范总纲。
- **归属**：**T2 扩容**——T2 更名"平台地基件：config 分层加载 + HttpClient status_code + canary 凭证注入"，实现档 **sonnet→opus**；`config/` 三文件 + `config.py` 加载链改造 + `crawler config show` 归 T2 Files。config.py 全部改动 T2 独占（T1a/T1b 零触）。
- **影响**：新建 `docs/design/10-config-layout.md`（status draft，纳入 W0 复审范围）；plan §4 T2 卡扩容、§6 模型表 T2 sonnet→opus；INDEX 登记新文档（合并时 controller）。既有 config.py 加载优先级（显式 home > `$PAPER_CRAWLER_HOME` > `~/.paper-crawler`）保持，项目级 `./paper-crawler.toml` 为**新增非敏感层**，纯附加不破坏既有家目录 config。

## D-026 dblp robots 路径级读法：同后缀通配词按最长匹配前缀判定（ADR 化）

- 状态：accepted · 日期：2026-07-24
- **背景**：dblp.org `/robots.txt`（[LIVE] 2026-07-22，D-021 增量复核首次实测）对同一 `xml` 后缀词在不同路径前缀下给出相反判定——顶层 `Allow: /xml`（`/xml/dblp.xml.gz` 全量 dump 所在前缀）、`Allow: /db`（含 `/db/conf/**/*.xml` per-conference 卷目录，dblp adapter 主枚举路径）与更深的 `Disallow: /rec/{xml,bib,ris,nt,rdf}`（per-record 导出路径；`/rec` 本身落在粗粒度 `Allow` 清单内，但 `/rec/xml` 被更深规则单独禁掉）并存。三类路径的区分此前散落三处独立论证——[aggregators.md §3「DBLP robots 红线」](../design/adapters/aggregators.md)、[dblp/adapter.py 模块顶部合规红线注释](../../src/paper_crawler/adapters/dblp/adapter.py)、D-021 决策 1——但均未提炼出一条可复用的一般性判读原则；[2026-07-23-phase4-report.md §6 开工检查单 #6](../reports/2026-07-23-phase4-report.md) 登记此项待办（"建议后续新源遇到类似 robots 通配歧义时，本条可作为该类判断的可援引先例，登记为独立小节或新 ADR"）。
- **决策**：同一文件后缀通配词（如 `*.xml`）在不同路径前缀下的 robots 读法不同——判读以最长匹配路径前缀的 Allow/Disallow 为准；官方文档明示的 API/dump 通道（如 dblp XML API、`dblp.xml.gz`）不因后缀通配歧义而误伤；per-record 导出路径 `/rec/xml` 属 Disallow 禁区维持零请求。本原则为后续新源遇到 robots 通配歧义时的可援引先例（AC-0.5"例外需 ADR"精神的延伸）。
- **依据**：标准 robots.txt 语义为「最长匹配路径前缀优先」（更具体的规则覆盖更泛的规则）；dblp 站点实测正是该语义的一个实例——`Allow: /db、/pid、/pers、/rec、/xml` 是前缀级粗粒度许可，`Disallow: /search、/search/publ、/rec/{xml,bib,ris,nt,rdf}、/db/indices、/cgi-bin、//` 是更深前缀的具体禁区：`/rec` 前缀本身 `Allow`，但 `/rec/xml`（及同级 `/rec/{bib,ris,nt,rdf}`）落在更深的 `Disallow` 规则之下故禁止访问；`/xml`（dump 前缀）与 `/db/**/*.xml`（卷目录前缀）均不落在 `/rec/` 之下，不受该 `Disallow` 影响，维持 `Allow`。三处既有论证按此原则交叉引用（不搬移原文）：①[aggregators.md §3「DBLP robots 红线（D1，高优先）」](../design/adapters/aggregators.md)——站点级 Allow/Disallow 清单原文与"能力面结论"（capabilities 不含 SEARCH）；②[dblp/adapter.py 模块 docstring「合规红线（AC-0.5…）」](../../src/paper_crawler/adapters/dblp/adapter.py)——代码侧承诺"全部请求构造只落在两类允许区路径"（`/db/conf/{acr}/` 索引页与 `/db/conf/{acr}/{slug}.xml` 卷 XML），不出现 `/rec`、`/search` 路径构造；③D-021 决策 1——首次把该 robots 实测从"FAQ 建议"升级为"robots 强约束"、定限速 `≥4s/req`。
- **影响**：后续新源 adapter 遇到"同一后缀词在不同路径前缀下给出相反 robots 判定"的同类歧义时，可直接援引本条「最长匹配路径前缀优先」原则判读，无需每次重新论证是否构成 AC-0.5 例外；不改变 dblp adapter 现有实现（`/rec/xml`/`/search` 本就从未被访问构造，本条是把既有正确行为背后的判读依据显式化，非行为变更）。

## D-027 RePEc Phase 5 出列：降级为 enrich 通道候选（挂 Phase 6 DSL 富化评估）

- 状态：accepted · 日期：2026-07-24 · 依据：[research/site-survey/repec.md](../research/site-survey/repec.md)（[LIVE] 2026-07-24 R0c，13 请求）
- **背景**：Phase 5 兄弟源勘察含 RePEc 生态（ideas/econpapers.repec.org）。R0c 实测判定 RePEc = **分布式书目元数据聚合器、非全文源**（条目=元数据+摘要+链出到源；NBER 条目 [LIVE] 全文链回 nber.org、RePEc 不自托管）。定位落 [aggregators.md](../design/adapters/aggregators.md) 谱系里 **openalex/s2 那一档（enrich/补充），非 crossref/dblp（ENUMERATE 主干）**。
- **决策**：**Phase 5 不建独立 `repec` pull adapter**；降级为**可选 enrich 通道候选**，独家增值项挂 **Phase 6 订阅 DSL 富化**评估。
- **理由**（三点）：
  1. **DOI 化系列与 crossref/openalex 重叠增量≈0**（repec.md §5 [LIVE]）：NBER 前缀 10.3386 归 NBER、在 crossref；同 WP 在 openalex（`W4323309095`，`ids={openalex,doi}`，无 repec 键、按 DOI 去重）。凡 DOI 化内容经既有主干即全覆盖。本项目 Phase 5 目标（SSRN/NBER/AEA/Econometric Society）多为 DOI 化或有专源。
  2. **门控与维护成本**（repec.md §3 [LIVE]）：RePEc API **email 门控**（致信取 access code、无搜索、非批量、保留限流权）；OAI-PMH 官方**自注"sometimes flaky"**；官方强烈不建议爬 HTML（隐私红线"Email addresses are released under no circumstances"）。取用须走 bulk（FTP/Rsync/OAI ReDIF）、零 HTML 爬——建设/维护成本高而主干价值冗余。
  3. **独家增值属 enrich 性质**（repec.md §5④⑤ [LIVE]）：① **JEL 分类**（`nbr:nberwo:35506`→D1/J13/J15，crossref/openalex/nber.org **三路皆缺**，经济学检索核心维度，Phase 6 DSL 高价值过滤键）；② **wp↔published 版本关联**（`nbr:nberwo:3210`→"Published in" Oxford Economic Papers，服务 D-007，crossref/openalex 无此策展）；③ 非 DOI 的 WP 长尾（2250+ 机构 archive）。三者均 **enrich 性质、非全文/非目标刊 ENUMERATE 主干** → 挂 **Phase 6** 评估。
- **定位建议（若未来纳入）**：`role: aggregator-enrich`（沿 aggregators.md openalex/s2 机制）——**capabilities 不声明 ENUMERATE/SEARCH/FETCH**；duck-typed `enrich_batch(dois)->list[PaperStub]` + `crawler enrich --source repec` 驱动；产 `(repec, handle)` identifier（`RePEc:{archive}:{series}:{id}`，仅 RePEc 内唯一、**非跨源合并锚点**——跨源仍靠 DOI）+ JEL/versions/citec 入 `meta`；**字段级优先级低位、只补不覆盖**（补 crossref/openalex 空缺）；收割走 bulk ReDIF/OAI，零 HTML。
- **附带事实**（repec.md §6 [LIVE]）：兄弟源 **NBER/CEPR 在 RePEc**（经 RePEc 取其书目与直建 nber adapter / CEPR 元数据面**重复建设**）；**SSRN 不在 RePEc**（Elsevier 商业源，442KB archives 全表无"ssrn"——SSRN 覆盖只能靠 `ssrn` 专源，RePEc 补不了）→ 进一步削弱独立 adapter 必要性。handle↔DOI **无内建映射**（NBER 条目页不显 DOI，须外部 crossref join）。
- **影响**：development-plan Phase 5 `repec` 由"adapter"注记为**"enrich 通道候选（R0c：主枚举/全文与 crossref/openalex 高度重叠→降级；独家增值＝JEL + wp↔published 版本关联，挂 Phase 6 DSL）"**；catalog 若有 repec 行→`role: aggregator-enrich`/`fulltext: none(links out)`/`enrich_fields: [jel, versions, citec]`。**建议排序：SSRN/NBER 专源优先落地 > RePEc enrich（挂 Phase 6）**。**触发条件（未来纳入）**：项目 venue 清单扩张到"非 DOI 经济学 WP series 长尾"时，以 bulk ReDIF/OAI enrich 通道实现（实现前 live 复核 OAI endpoint 活性与 FTP 结构）。
- **落款**：W0 双评审（A/B 独立实例）2026-07-24 通过，详见 [econsoc.md §9](../design/adapters/econsoc.md)。

## D-028 ECMA（Econometrica）年代分段路由：10.3982 归 Econometric Society，裸前缀路由 wiley 作废

- 状态：accepted · 日期：2026-07-24 · 依据：[research/site-survey/econometric-society.md](../research/site-survey/econometric-society.md)（[LIVE] 2026-07-24 R0c，26 请求）
- **背景**：既有 wiley.md §1/§2 与 `wiley/parse.py` 把 `10.3982` 列为 wiley 的 enumerate/resolve 路由前缀（`_WILEY_DOI_PREFIXES` 含 `10.3982/`、`is_wiley_doi` 裸前缀甄别）。R0c 实测证伪：`prefixes/10.3982` → owner=**The Econometric Society**（crossref member 2359），**ECMA/TE/QE 三刊共用此前缀、仅 DOI 后缀（ECTA/TE/QE）区分**——裸前缀 `10.3982→wiley` 会把 TE/QE（econsoc OA）**误路由到 wiley**。且 ECMA 已**前向迁移**：新刊自营 econometricsociety.org（2026 DOI 实测 200 + CC BY 4.0）、过刊留 Wiley（2015 DOI→doi.wiley.com 403 CF）、pre-DOI 留 JSTOR。
- **决策**：
  1. **`10.3982` 前缀归 Econometric Society，非 Wiley；裸前缀路由作废**。正确路由键 = **venue(ISSN) + DOI 后缀（`ECTA` vs `TE`/`QE`）+ 年代/域名**，绝非裸前缀。
  2. **ECMA fulltext 段路由**（`fulltext_source: econsoc` 单值）：当前段→`econsoc`（OA，econometricsociety.org 自营）；过刊段（doi.wiley.com，~2010–切换点）与 pre-DOI 段（10.2307/JSTOR，<2010）经域名路由判定后**非本 adapter 覆盖 → `no_entitlement`/skip**（Phase 5；跨 adapter 交 wiley 的 handoff 显式 defer）。**TE/QE 全程 econsoc（OA）不分段**。
  3. **分段判定法取方向 a（运行时 per-DOI 域名判归属）**：resolve 时以 DOI 实际落地域名（`doi.org` HEAD `-L` 实时终点，权威）判归属——`econometricsociety.org`=econsoc、`doi.wiley.com`=过刊段（`no_entitlement`/skip，wiley handoff defer）、`jstor`=界外；crossref `resource.primary.URL` 域名作 pre-filter 提示（**但有陈旧风险**：QE crossref link 仍留遗留 Wiley link——权威信号取实时落地非 crossref 登记）。方向 b（年份粗分）作快速 pre-filter、边界年实现期二分核实。
- **wiley 侧联动修正范围**：
  - **文档**：wiley.md §1/§2 **移除** `10.3982` 路由键（wiley 侧不持该前缀知识，ECMA 过刊归属改由 econsoc 域名路由）+ ECMA 前向迁移注记（2026-07-24，依据 R0c）；frontmatter `updated` → 2026-07-24（随本次三合并生效）。
  - **代码（实现期卡，本次只报告不改）**：`src/paper_crawler/adapters/wiley/parse.py` **`_WILEY_DOI_PREFIXES` 移除 `10.3982/`**（仅留 10.1111/10.1002）——W0 评审 B 实证 `is_wiley_doi(doi:str)` 单入参无域名/年代信息、无法判过刊段，**取移除非收窄**；ECMA 过刊→wiley 归属由 econsoc 域名路由（方向 a）承担、wiley 侧不持 10.3982。`wiley/adapter.py`+`wiley/__init__.py` docstring 同步。**联动 test**：`tests/unit/test_wiley_parse.py:21,32` 断言 `is_wiley_doi("10.3982/…") is True` 随移除**同卡翻转**（移入非 Wiley 组）。**实现顺序**：`parse.py` 移除 + `ecma/te/qe` venue YAML 落地**同一实现卡**（`is_wiley_doi` 现**零 runtime 调用=休眠**，落地前无活风险）。**venues/ 无 10.3982 硬编码**（grep 空、无 ecma/te/qe YAML）。
- **理由**：R0c [LIVE] 实测 = 前缀所有权（Econometric Society）+ 三刊共用 + ECMA 前向迁移三事实叠加，裸前缀路由在 TE/QE 上系统性误路由、在当前 ECMA 上系统性漏取（Wiley TDM 对自营新 DOI 大概率 no_entitlement）。
- **影响**：catalog `ecma` 行 `fulltext_source: econsoc`（单值）+ 域名路由分段（当前 OA / 过刊·pre-DOI 段 no_entitlement/skip），`enumerate` 仍 crossref；wiley.md 修正（随本次三合并生效）；wiley `parse.py` 移除 10.3982 + `test_wiley_parse.py` 断言翻转（实现期同卡）；econsoc.md §3.3 承载 ECMA 分段主设计。`economics-journals.md` catalog TE/QE 平台注记更新为"econsoc（OJS@econtheory.org/ojs + 合并前端 econometricsociety.org；qeconomics.org 证书过期停用）"。**[UNRESOLVED]（不阻塞）**：① 当前 ECMA 是否全刊 OA（实现期 HEAD 判）；② Wiley→自营切换日（方向 a 不依赖）。
- **落款**：W0 双评审（A/B 独立实例）2026-07-24 通过，详见 [econsoc.md §9](../design/adapters/econsoc.md)。

## D-029 SSRN 定位修订：聚合元数据主路径确立 + 浏览器全文降 opt-in（修订 D-011 定位）

- 状态：accepted · 日期：2026-07-24 · 依据：[research/site-survey/ssrn.md](../research/site-survey/ssrn.md)（[LIVE 2026-07-24] R0a）+ [design/adapters/ssrn.md](../design/adapters/ssrn.md)
- **背景**：D-011（2026-07-20）设想「eLibrary 浏览页 + RSS 枚举 + 浏览器下载」双模式、`auth_level: free_account_preferred`。R0a 勘察（2026-07-24）实测颠覆三点：① SSRN 全库经 Crossref 前缀 10.2139（1.41M DOI）+ OpenAlex（1.63M）完整可读，枚举/元数据/增量 watch 聚合 API 即可闭环、零 SSRN 接触；② 匿名 HTTP 直连 SSRN 不可行（2026-07-20 Cloudflare 挑战 + 2026-07-24 环境 TLS 阻断，双独立证据）；③ 全文无第三方旁路（unpaywall 对 SSRN 仅 landing）。
- **决策**（修订 D-011，收窄双模式定位，不 supersede）：
  1. **模式 A（聚合元数据）升主路径**：Crossref 前缀 10.2139 枚举主干 + OpenAlex 交叉核对/补摘要；`auth_level=none`；SSRN 站点本体零请求。
  2. **模式 B（浏览器全文）降 opt-in 低配额**：唯一全文路径但穿 Cloudflare 门，按最严红线 opt-in/用户发起单篇、非批量非默认；实现 defer 评估（ssrn.md §11 案 B，controller 已终裁）。
  3. **元数据与全文能力解耦**（D-005 同款）：元数据能力不依赖 SSRN 站点连通性。
  4. **venue 建模**：单一 `ssrn` venue（前缀全库）+ econ/fin 主题近似过滤，非 per-FEN 独立 venue（聚合源无子网过滤维度，对照 arxiv 差异，ssrn.md §3）。
- **理由**：browser fetch 通道（ssrn 模式 B / aea 全文域 pubs Cloudflare / wiley deferred 页面兜底三处共需）评估两案：案 A（Phase 5 落地最小件）在线验收因**本机环境对 CF 前置域 TLS 层阻断**而大概率不可行（curl/httpx [LIVE] 实测，浏览器上下文 [推断] 同源本机代理同样受阻）；案 B（defer 至 Phase 6 横切件）离线逻辑（challenge 判定/BLOCKED/预算护栏）可全覆盖、defer 全文不丢元数据价值、与 aea/wiley 两消费方一并做横切件设计避免逐 adapter 重复。**controller 已正式采纳案 B**。
- **影响**：ssrn.md 实现级详设据此；AC-5.1 分层改写（元数据 CI 可判 / 全文 opt-in，ssrn.md §8）；development-plan Phase 5 DoD「按 FEN 子网…下载」相应收窄为「近 7 天新 WP 元数据 + econ/fin 近似过滤」；browser fetch 横切件（案 B）Phase 6 与 aea pubs CF / wiley deferred 页面兜底一并设计。
- **落款**：W0 双评审（A/B 独立实例）2026-07-24 通过，详见 [ssrn.md §10.1](../design/adapters/ssrn.md)。

## D-030 Browser-Fetch 横切件形态定稿（案 A）+ CF-403 挑战判定契约演进（S-c）+ 冷却键粒度修复（E-1）

- 状态：accepted · 日期：2026-07-26 · 依据：[design/11-browser-fetch.md](../design/11-browser-fetch.md)（R1 详设，fable 定稿）+ [post-phase5-audit §3 S3-P2/§6 #2](../reports/2026-07-24-post-phase5-audit.md)
- **背景**：D-029 把 browser-fetch 横切件统一设计 defer 至 Phase 6；R1 详设起草完成，量化评估形态两案并新发现冷却键粒度缺口（open_access family 冷却"写而不读"——`runner.py` family 早返回先于冷却判定，实证）。
- **决策**（三项，对应 11-browser-fetch §12 裁决点①②③）：
  1. **横切件形态采案 A（薄接缝最小件）**：单模块 `fetch_one` + 一 fetch 分支 + 一 CLI flag，一次性上下文用完即毁；不建上下文池/批量入口/独立账本。决定性理由＝**能力面恰好等于 AC-0 合规面**（D-029"非批量非默认"红线下，案 B 的核心增量恰是不允许行使的能力）；预算唯一事实源＝FetchLog（per-venue 维度 join 派生，零新表）。演进缝（调用方作用域 context 复用）已预留，`fetch_one` 签名零破坏。
  2. **CF-403 挑战判定契约演进采 S-c**：`http.py` 403 分支新增 `cf-mitigated: challenge` 头判别 → CHALLENGE（此前统一映射 NO_ENTITLEMENT）。这是对 Phase 2 T2 冻结映射表的**受控演进**：改判面经论证恰好＝wiley.md §5/aea.md §6/auth-framework §11 三处文档**已声明应改**的场景（wiley TDM 403 无 CF 头、elsevier JSON 封套均不受影响）——让实现追上文档，非语义变更。特征判别复用 `ChallengeDetector` 单一权威源，不复制特征串。实现卡必须附全库 fixture 扫描断言（零既有用例翻转）。
  3. **冷却键粒度采 E-1（最小修复）**：冷却判定上移至 family 判别之前（修复 open_access family"写而不读"）；`RENDER_PAGE`/挑战场景冷却键改**域级**（修复 aea 双域异质连坐），向前兼容读旧 `<adapter_id>.json` 键。E-2（全量域键统一）列后续清账候选。
- **同批定稿确认**（§12 裁决点④–⑧）：④ `crawler cooldown` CLI 缓议（登记 Phase 7 检查单候选）；⑤ ★接缝 A-1＝`RENDER_PAGE` 复用既有枚举、不新增 asset state（门控表达 deferred 语义）、aea 产计划改动归实现卡；⑥ 配额口径＝`browser_daily_cap=50` 默认与 VenueSpec 声明取 min；⑦ AC 编号＝临时 AC-BF.x，落地 Phase 转正并回填 FR→AC 映射 + AC-5.1b 承接指针；⑧ S-a（`get_with_meta`）不落。
- **影响**：11-browser-fetch.md 转 `approved`（实现仍未承诺——落地卡权在 controller，Phase 6 末 stretch 或 Phase 7）；**S-c + E-1 属既有 httpx 路径缺口修复、不依赖横切件实现，立即立卡 F6**（Phase 6 修复批增补，闭合审计处置 #2 CF-403 缺口）；wiley.md §5 与 http.py 的文档/实现漂移随 S-c 自动收口。
- **落款**：fable 定稿裁决 2026-07-26（R1 opus 起草 + fable 通读全文签署）。

## D-031 弱信号候审匹配键改为观测级键集合（新表 paper_weak_key）+ 同级 tie-break 复合序

- 状态：accepted · 日期：2026-07-26 · 依据：[post-phase5-audit §3](../reports/2026-07-24-post-phase5-audit.md) AC-3.4 P1 + P6-F1 卡（`5130c4a`）+ F1 独立审查（双候选修法反例实测/12 变异体）
- **背景**：审计实证注入顺序可改变弱信号候审边（ABC→1 边、ACB/CAB→0 边）——根因是匹配键取 paper 行**当前** `title_norm`/`_first_author`，会被高优先源字段收敛改写，抹掉匹配面。
- **决策**：
  1. **匹配键 = 观测级键集合**：新表 `paper_weak_key(paper_id, title_norm, first_author)`（schema v3，`0003` 迁移 + 存量回填零倒退零扩张），单调只增、不被收敛改写；新建/强合并/冲突并入三路径均记键并对新键重判候审。终态候审边＝键集合有交的 paper 对（输入集合的函数，与到达序无关）。审计所列两个候选修法（收敛改键后重判/冻结 title_norm）均经审查反例实测证伪。语义代价如实入档：跨观测拼接键（行态键）漏标——该匹配面被证明不可序无关化，漏标方向 fail-safe（D-007「宁可两条待审」不破坏）。
  2. **同一来源二次观测的 tie-break＝复合全序取 min**：文本字段「更长者胜、等长取字典序小者」（修复纯字典序对信息增补的系统性压制——前缀恒胜会静默丢弃 "(Retracted)" 标记与完整摘要）；`year`/`pub_date` 纯 min（取更早观测，保守）。min 为幂等+交换+结合的半格运算 ⇒ 顺序无关成立。「取新值」方案明确排除（"新"＝到达序，违反 AC-3.4）。
  3. **取证抓手 `_field_tie`**：tie-break 实际压制不同同源值时在 `meta_json` 记字段键集合（集合并、被更高优先源改写即清——记号本身亦序无关），供 Phase 7 `dedupe review` 审计。
  4. **候审边 from/to 定向如实化**：定向是建边时刻快照、非不变量（identifier 增长不重定向）；`candidate_duplicate` 语义上是**无序对**，消费方不得依赖 from/to 字面序。
- **影响**：schema v2→v3（备份链/幂等/失败回滚经审查亲测）；design/06 §2/§3 已随卡更新；`IngestResult` 三枚举与退出码契约不变；行为面为旧候审的向下收敛+同级收敛的确定化，绝不自动合并/不删行语义不变；性能 +0.023ms/ingest 常数开销（审查实测）。
- **落款**：F1 opus 执行 + opus 审查（放行附条件全闭合，变异体 M3/M4/M8 补锁后 KILLED）+ fable 合并裁决 2026-07-26。

## D-032 config-home 迁入仓库根 `.paper-crawler/`（env 主指向；凭证红线表述收窄）

- 状态：accepted · 日期：2026-07-26 · 依据：用户架构令 2026-07-26（config 归集进项目文件夹）+ 迁移实录（[session-010](../logs/2026-07-26-session-010.md)）
- **背景**：用户令「散落 `~/.xxx` 的论文平台 config 归集到项目文件夹统一管理」。D-025 已归集**规范与样例**（仓库内 `config/`），但真实值仍在家目录。实际散点盘点：`~/.paper-crawler`（唯一需人编辑的 config 是 1KB `config.toml`，其余为 DB/数据/日志）、`~/.kaggle/access_token`（外部 kaggle CLI 自有产物）、`~/Library/LaunchAgents/com.papercrawler.openreview-token.plist`（launchd 硬约束位置）。
- **决策**：
  1. **config-home 物理迁入仓库根 `.paper-crawler/`**（config.toml/catalog.sqlite/data/logs/reports 整体原样迁移），指向机制 = `PAPER_CRAWLER_HOME` env（`~/.zshenv` 全局 export，覆盖交互/非交互 zsh）。**加载链与优先级零变更**（D-025 四层原样）。symlink 过渡方案经评估被用户否决——家目录彻底干净。
  2. **launchd 硬化**：plist 模板 `ProgramArguments` 显式携 `--home`（launchd 不读 shell env，防静默回落）；日志路径随 home 派生。已重装生效（顺带修复 07-24 起停摆的 token 刷新）。
  3. **兜底路径纪律**：绕过 env 的 `Path.home()/".paper-crawler"` 硬编码兜底会静默重建空家目录——一律改经新公共 `config.resolve_home()`（与 `Config.load` home 链单一同源；首例修正 openalex 预算 state 兜底）。
  4. **红线表述收窄**：AC-0.3 本体（凭证不入 **git 历史**）不变；D-025 §6「凭证只存仓库外」收窄为「凭证只存 config-home（git 追踪范围外，`.gitignore` 锚定 `/.paper-crawler/` 整目录强制忽略）或 env」。AC-0.3 守卫测试（check-ignore 参数化）扩 3 条覆盖该目录。
  5. **周边散点处置**：`~/.kaggle/access_token` **登记不搬**（外部 CLI 自有文件，物理搬动会破坏该 CLI；Kaggle 回填特性排期时按 D-025 §5 收值入 `[auth.kaggle]` 槽）；plist 位置属 launchd 硬约束，登记为「安装产物，源=scripts/refresh_openreview_token.py」。canary-weekly 模板文档同步改用 `$PAPER_CRAWLER_HOME`。
  6. **新增操作红线（入 AGENTS §6）**：本仓库禁止裸 `git clean -fdx`——必须带 `-e .paper-crawler`（`clean -x` 无视 ignore 规则，一条命令可抹掉凭证+数据库）。
- **影响**：`config/README.md` 升级为全配置地图；`10-config-layout.md` §3/§6 随修。**存量文档读法**：既有文档中 `~/.paper-crawler` 字样此后读作「config-home 默认值」——本机经 env 指向仓库内，无 env 的环境仍回落家目录，语义不破（01/02/07/auth-framework 等不逐一改写）。迁移验收：`crawler config show` 与迁移前逐键一致（仅 home 行 default→env）；全量门禁 3824 passed / 覆盖率 98.99% 全绿。
- **落款**：fable 设计+执行 2026-07-26（用户两轮批准：迁入方向 + env 机制）。

## D-033 全文抽取（stage 5 extract）语义定稿：pypdf 基线 + GROBID 可选增强 + asset 级幂等键全序取 max

- 状态：proposed（待 fable 终签转 accepted；**其中两项子裁决已由 fable 单独 approve，见下方「已裁决子项」**）· 日期：2026-07-27（r2 审查修订同日）· 依据：[design/12-fulltext-extract.md](../design/12-fulltext-extract.md)（P7-T1 详设，r2）+ [phase7-implementation-plan §2/§4 T1](phase7-implementation-plan.md) + [AC-7.1/7.2](../testing/acceptance-criteria.md)
- **已裁决子项（fable，2026-07-27，原 proposed → approved）**：① **`HttpClient.post_multipart` 纯附加扩展**——纯附加且有两处成文先例（`extra_headers`、`CrawlerError.status_code`），退路（自建 `httpx.Client`）的双份维护代价更大；落地须与 `post_json` 同构走 `_request`，不得另起绕过既有限速/obslog/错误映射的请求通路。② **空口令加密 PDF 姿态**——approve，并按审查建议把实现约束加严至五条（见下方「附带裁决」）。
- **背景**：stage 5 自 Phase 1 起为 noop（`stages.py::_stage_extract` 写 `extractor="noop"/text_path=NULL/char_count=0`），幂等键实际是 paper 级（`fulltext` 表 PK=`paper_id`），与 design/05 §1 阶段表登记的「(asset, extractor_ver)」不符——该表已自注「asset 级键随 Phase 7 真实抽取启用」。Phase 7 兑现该注记，需一次性把抽取器选型、幂等语义、失败态、降级链、测试载体五面同时定死，否则 T7/T14/T19 三卡各自推断必然漂移。
- **决策**（六项，对应 12-fulltext-extract §3–§8）：
  1. **纯文本基线抽取器 = `pypdf`，进核心 `dependencies`**（非 extra）。三轴（依赖纯度/维护活跃度/抽取质量）比较见详设 §3.1。决定性理由不是质量更高，而是 **pdfminer.six 在本架构里是被两侧夹住的支配劣势项**：它相对 pypdf 的唯一实质优势（版面分析）恰是 GROBID 覆盖的那一格，而代价（把 `cryptography` 从 `[auth]` opt-in 提升为核心必装）正踩 D-023 已划的依赖分界线；PyMuPDF 因 AGPL-3.0 与本仓 Proprietary 许可冲突直接出局。入核心而非 extra，是因为 extra 会凭空造出「stage 5 不可用」这一**无验收载体**的降级态。**回滚触发条件写死**：T7 实测若证伪「零传递依赖」或安装体积 >5 MB，降为 `[extract]` extra。依赖事实标 ⚠ 未核验（离线设计卡），T7 装依赖时实测复核回填。
  2. **`TextExtractor` Protocol = 路径进、值对象出**：`extract(source: Path) -> ExtractedText`，抽取器不知 DB/Config/网络。`ExtractedText` 携 `text/extractor/extractor_ver/suffix/char_count/lang/title` + **`note`**。三处强约束：**`version` 必须构造期可知**（幂等键前置可判的硬前提，否则「幂等跳过」退化成「抽完再比」）；**`suffix` 由抽取器给**（落位后缀属产物形态）；**`note` 是判别信息不是判决**（r2 审查 P0-1）——只有抽取器分得清「加密/无文本层/结构损坏/有文本层但抽空」，handler 拿到零输出无从复原是哪一种，§6.1 的四元 `note` 闭集就不可生产；分工线精确化为「抽取器报看到的是什么、handler 决算不算失败」，抽取器**不得**据此自行落库/抛异常/降级（`char_count>0` ⇒ `note` 恒 None，`char_count==0` ⇒ `note` 必非空，T7 断言锁定）。「文件在但抽不出」返回 `char_count==0` 不抛异常——错误分类学决策归 handler，抽取器不做。**零输出判据统一取 `char_count==0` 而非 `text==""`**：纯文本路径二者等价，但 GROBID 路径的 `text` 是 TEI XML 源码（header-only 空产物时 XML 非空、可见文本为零），用 `text==""` 会漏判该反例；`char_count` 是两路径唯一同口径的量。`lang` 在纯文本路径恒 `None`（不引入语言识别依赖；错值比 NULL 更坏，且当前零消费方）。
  3. **幂等键 asset 级 = `(asset_id, source_sha256, extractor, extractor_ver)`**，`fulltext` 表**保持 1-1（PK 仍 paper_id）**——asset 级的是键不是表的基数，改 1-N 才叫改 ER 模型，本 Phase 不做（升级触发条件：出现 per-asset 产物矩阵的真实消费方 → P8）。schema 走**纯附加 5 列**（`asset_id`/`source_sha256`/`text_sha256`/`state`/`note`）+ 存量 noop 行回填 `state='noop'`，方言中性、无破坏性变更；迁移编号 `000N` 占位（T2 的 FTS 迁移并行争号，T7 按目录当时最大号 +1 取）。**取代规则 = 全序取 max** `(rank, ver_key, char_count, asset_id)`，rank：grobid 2 > pypdf 1 > **`extract_failed` 0 > `noop` −1** > **陈旧行 −2**（`source_sha256` ≠ 该 asset 当前 `sha256`）——max 是幂等+交换+结合的半格运算 ⇒ 终态是输入集合的函数、与注入顺序无关（**直接沿用 D-031 已付过学费的纪律**，不在 extract 面重犯）。**`extract_failed` 必须高于 `noop`**（r2 审查 P1-1，初稿写反）：noop 是 P1 占位空行（无抽取事实），`extract_failed` 是已判定的抽取结论；反序会让存量 noop 永久压制失败行 ⇒ 失败结论写不进库 ⇒ 幂等键永不命中 ⇒ **每轮 pull 对同一批长尾扫描件重抽**（审查实测）。**支配预判**（r2 审查 P1-2）：四元组不全等但存量 `(rank, ver_key)` 严格更优 ⇒ 本次注定败 ⇒ 直接 `"skipped"`，**不开源文件、不发 GROBID 请求**（典型：库里已有 TEI 而本轮 GROBID 关闭，否则每轮全库重抽纯文本再全丢）；预判只用抽取前可知的两维、与取 max 同向，不改终态。残余成本如实入档：`(rank, ver_key)` 平局（同抽取器同版本、不同 asset）仍须实抽才能比 `char_count`。legacy `asset_id IS NULL` 行归一：tie-break 取 `""`、**一律不判陈旧**（避免 NULL 三值逻辑把「未知」误判成「陈旧」）。`--force` 绕过任务级 fresh_skip 但**仍走全序**，故**不降偏序**（措辞如实化：不等于「只会变好」——同 rank 下版本升级即使 `char_count` 腰斩仍胜，因 `ver_key` 位序更高；取证面只有 obslog 前后两行的 char_count）。断点语义沿 fetch 先例：`.part` → 原子 rename → DB upsert → 删旧后缀产物；三个崩溃窗逐一入档（窗 2 换后缀＝`orphan_file`、**同后缀覆写＝`hash_mismatch`**；窗 3 旧产物孤儿**不自愈**由 verify 处置；**且 T7(W1)→T14(W2) 之间窗 2/3 无检出工具**——缺口由 T7 报告登记、T14 合并后一次全库 verify 收口）。
  4. **失败态三分**：①库↔文件不一致（asset 称 fetched 但文件缺失/哈希不符）→ **抛 `INTEGRITY`**（这是可修复的库缺陷，静默记 extract_failed 会把它伪装成「这篇抽不出来」）；②源文件在但抽不出——**判据统一为抽取器返回 `char_count == 0`**（加密/纯图像/损坏/空白；**严格等于 0，不设经验阈值**，以免把一页勘误这类真实短文误判）→ **不抛、任务不 FAILED**，落 `fulltext(state='extract_failed', note=<token>)` + WARN（该类失败既非瞬态也非 adapter 腐化，判 `FAILED(parse)` 会让长尾数据批量飘红并永久占据 retry 队列）；③asset 缺失/状态非法 → 抛 `CONFIG`（现状保留）。**`extract_failed` 不进 `paper.ingest_state` 阶梯**（四值不变）——该阶梯是单调前进的进度轴，塞入失败态会引入回边并污染一切按 `ingest_state IN (...)` 取范围的既有查询；失败时 `ingest_state` 停在 `fetched`，事实由 `fulltext.state` 列承载。**GROBID 零输出走同一判据并触发纯文本兜底**（r2 审查 P0-2，本卡最关键的相容性修正）：GROBID 对 image-only PDF 会返回**语法合法但只有 header 的 TEI**（200 + 合法 XML + 可见文本近乎为零），若按「200 且 XML 合法」判成功，它会以 rank 2 **压制同 paper 已有的 pypdf 五万字正文**（审查实测反例）——一次「增强」反而抹掉基线成果。故 `char_count == 0` 的 GROBID 产物一律判第 2 类无效，并**立即以纯文本抽取器兜底重抽同一 PDF**（复用既有降级路径，非新路径），语义收敛为一句话：**「GROBID 无有效产出 → 纯文本」**（不区分成因是服务不可用/超时/非法 TEI/header-only 空产物）；兜底后纯文本仍为 0 才落 `extract_failed`；obslog 记 `grobid_empty_tei`。
  5. **GROBID = 本地 REST 可选增强，零新 SDK**：config 两槽 `[extract] grobid_url`（空=关，默认形态）/`grobid_timeout_s`（60）；`consolidateHeader` / `consolidateCitations` / **`consolidateFunders`** **三者硬编码 0 不设槽、逐一显式**（r2 P2-⑥：漏写一个即漏一条外网通道，且不得依赖 GROBID 默认值——其默认值随版本变动过）——GROBID 的 consolidation 会代为访问 Crossref/biblio-glutton，开启即在 extract 阶段发出用户不知情的外网请求，越过本项目全部限速/预算/FetchLog 记账面（AC-0 邻域）；T7 须落「三参数均为 0」的机器断言。客户端**复用 `http.HttpClient`**（`rate_limiter=None`、诚实 UA）：**不注册限速桶、不写 FetchLog**（FetchLog 是在线预算唯一事实源，D-030 §7.2，本地调用记入即污染派生口径），复用既有 `transport=` 缝使 mock 两模式测试零新基建。**对冻结件 `HttpClient` 做一处纯附加扩展 `post_multipart`**（先例＝`extra_headers`、`CrawlerError.status_code`）——**fable 已 approve**（见上方「已裁决子项」①）。**降级链 = 每轮一次前置探活（`/api/isalive`+`/api/version`，结果缓存在 `StageContext` 新增可选字段，先例＝`unpaywall_adapter`）+ 逐篇处置矩阵**：url 空→纯文本（非降级，不刷 WARN）；探活失败→整轮降级并**记忆**（服务未起是持久态，逐篇重试纯空转）；**逐篇连接失败/重置→与探活失败同类，整轮降级并记忆**（r2 审查 P1-3 补行：探活只证明那一刻在线，本机 GROBID 常跑在会被随手关掉的容器里，中途挂掉是真实常见形态）；读超时→本篇降级**不记忆**（超时是 per-文档的）；503→退避重试一次（GROBID 的队列背压信号）再降级；404→降级并**记忆**+明示检查 url；其它非 200 / 200 但非法 TEI / **200 且合法 TEI 但 `char_count==0`**→本篇降级。「记忆本轮」＝本次运行内此后不再调 GROBID（含探活），**只活在进程内、不落库不跨运行**（用户起好服务后无需清任何状态）。**不变式（AC-7.2 形式化）：GROBID 相关异常一律不得逃逸 extract handler、不得使任务 FAILED**；降级只留 obslog reason token，DB 无痕。TEI 原样落 `.tei.xml`，**`char_count` 取 `<text>` 可见文本字符数（stdlib ElementTree itertext，零新依赖）而非 XML 源码长度**——该值参与全序比较，混入标签会使维度跨 extractor 失去可比性并系统性偏袒 TEI。
  6. **fixture 策略 = 程序化生成，零 `.pdf` 文件入库**——**「仓库内小样本 PDF」被否决**，两条证据：AC-0.3 明文「PDF 不出现在 git 历史」；`.gitignore` 现有全局 `*.pdf` 条目（提交需 `git add -f` 强推，且会在红线守卫面开出「合法例外」侵蚀其此后执行力）。替代三层：L1 手写最小合法 PDF 生成器（base-14 字体 + `Tj` 算子，全 ASCII，`tests/helpers/minipdf.py`）；L2 生成式负例（纯图像/截断/挂 `/Encrypt` 触发加密判定，**不实现任何加密算法**）；L3 自造 TEI 语料 + `httpx.MockTransport`。L1 的实质优势不只是合规让步：生成器**参数化**（标题可控注入 ⇒ AC-7.1 判据可精确断言、多页/空页任配），而静态 PDF 只测一个形态且对 reviewer 是不可 diff 的二进制黑箱。真实 PDF 只出现在 T19 在线批（开放许可样本落 config-home，不入仓库）。
- **附带裁决**（同批定稿，避免下游各自推断）：
  - **落盘路径**：`fulltext.text_path` 存**相对 `data_dir` 的相对路径**，**写死为不含 `data/` 前缀**的 `fulltext/{venue}/{year}/{ulid}{suffix}`（r2 审查 P1-4）——`verify._resolve` 把相对路径挂在 `Config.data_dir` 下、而 `data_dir` 本身即指向 `…/data`，带前缀会解析成 `…/data/data/fulltext/…` 使**全库每一行都报 `missing_file`**。**T7 须同步改两处列注释**（审查实地核证，现均含 `data/` 前缀，照抄即踩坑）：`docs/design/06-data-model.md:136` 与 `storage/migrations/0001_init.sql:113`。选择相对形态的理由：**config-home 可整体迁移**（D-032 刚发生过一次，绝对路径迁移后全库失效）+ `verify._resolve` 已支持（T14 零改造）。如实入档债务：`asset.file_path` 现存绝对形态，两列不一致，本卡**不改** asset 侧（改动使存量库路径全失效需数据迁移），登记 P8 清账候选。
  - **不扩 `AssetKind`**：新增 `_fulltext_final_path()` 与 `_asset_final_path()` 并列（T1 卡文本「`_asset_final_path` 扩 fulltext kind」按此读法执行）。`AssetKind` 是 resolve 契约的**上游资产类型**，fulltext 是本地派生产物；混入会污染 `asset` 表 `UNIQUE(paper,kind,version)`、adapter 能力声明面与 fetch 落位分支，换来的只是一个函数的复用。
  - **T14 消费面**（T14 卡指名由本卡裁决）：`missing_file`/`orphan_file`/`hash_mismatch` 三类在 fulltext 面同构成立（`text_sha256` 列即为第三类而设）；**新增第四类 `stale_fulltext`（信息级，r2 审查 P1-5）**——asset 被 re-fetch 后 `fulltext.source_sha256 ≠ asset.sha256`，此时文件在、哈希对、路径对，**前三类判据全绿**，但全文与当前 PDF 已**静默错配**，无此类则该错配可永久隐身；判据与 §5.3 陈旧判据共用同一谓词，suggestion `re-extract`，归信息级因它可自愈（下次 extract 必然取代）。`state='noop' AND text_path IS NULL` 报「未真实抽取」信息级、不计入三类；**si 孤儿判定粒度 = 文件级**（`asset.file_path` 对 si 存具体文件路径，asset 行 ⇄ 文件 1-1，与 pdf 完全同构；目录级判定会把「同 paper 多 si 文件里少一个」整体判成存在，正好掩盖它要检出的缺口）。
  - **T12 零消费**（r2 P2-⑦，闭合 phase7 计划 §2 消费方表）：D-034 的 FTS5 范围＝title+abstract，二字段都在 `paper` 表，与 `fulltext` 行/落盘产物**零交集**（正文索引已 defer）。故 D-033 与 D-034 实现面**无接缝**，T7/T12 可完全并行，两卡迁移只在**编号**上竞争、schema 内容不重叠。
  - **加密 PDF 姿态**（**fable 已 approve**，见上方「已裁决子项」②；实现约束按审查建议加严至五条）：①允许空口令打开（等价于任何阅读器的常规行为，不涉猜测）；②**只试一次空串**（`decrypt("")` 至多一次，不重试、不变形——不试 `" "`/`None`/doi/标题等文档相关串）；③**禁止任何回退口令列表**（代码中不得出现候选口令常量/口令文件读取/「常见 owner password」集合——**存在这样的数据结构本身即违规**，与是否执行无关）；④不实现权限位改写/绕过代码；⑤**`note` 不泄露口令强度信息**（非空口令一律记 `encrypted` 单一 token，不得分化出 `weak_password`/`password_length_n`/`rc4_vs_aes` 等携破解线索的取值，obslog 同口径——「哪些文件口令更好猜」的清单本身即破解辅助面）。边界在「绕过保护措施获取本无权访问的内容」，不在「对已授权持有的文件做本地处理」。
  - **AC-7.1 判据两路径分叉**（不弱于原文，正式编号与验收记录模板归 T18，本卡不改 `acceptance-criteria.md`）：GROBID 路径比 TEI `titleStmt/title`；纯文本路径比正文前 2000 字符内的最优子串；两者同用归一化 Levenshtein ≤ 0.15，DP 实现约 15 行落 `tests/helpers/`，**零新依赖**、T7 与 T19 共用同一判据。**阈值 0.15 与 2000 字符窗未经真实标定**（r2 P2-⑤，如实声明）：离线载体的标题是自己注进去的、结构上标定不了阈值，第一次真实接触在 T19；处置口径写死＝T19 不达标**先判「阈值未标定」而非「抽取器不合格」**，人工过目失配样本区分三成因（抽取器真错 / 标题归一化不足 / 阈值过紧），**允许一次**基于实测分布的阈值修订并入 T19 验收记录 + 回填详设与 T18 的 AC 表述，此后再改须走 ADR（防「调阈值直到通过」的验收自证）。**AC-7.2 覆盖三态**（url 未配 / mock 在线 / 服务不可用逐行），第三态即「关闭时降级不报错」的严格形式。
- **影响**：`design/12-fulltext-extract.md` 新建（`review` → fable 签署后 `approved`）；**design/05 §1 stage 5 行的幂等键注记与 design/06 §2 `fulltext` 表 DDL / §4 布局，由 T7 实现卡随迁移回填**（沿 D-031/F1 的「设计文档随实现卡更新」先例，避免与 T2 在 design/06 上撞面）；T7 施工面＝`pipeline/extract.py`（新）+ `_stage_extract` 改写 + `_fulltext_final_path` + config 两槽 + `HttpClient.post_multipart` + `StageContext` 一可选字段 + `000N` 迁移 + `pyproject` 加 pypdf；**T7 不碰 `cli.py`/`repo.py`/`types.py`**（主动退出 phase7 §5 已列的 cli.py 四卡冲突面）；T14 按上方**四类**口径扩 `verify`（三类缺陷 + `stale_fulltext` 信息级）；T19 按 §12 判据做真实批（GROBID 真实冒烟为条件项，本地服务零在线预算）；**T12 与本条零接缝**（见附带裁决）。T7 另须落三项回归锁：GROBID 空产物不压制既有正文、rank 序 `extract_failed > noop`、L1 生成器自校验（防生成器 bug 伪装成抽取失败）。
- **落款**：P7-T1（opus）起草 2026-07-27 → 独立审查（opus）NEEDS_FIX（7 必修 + 7 P2，六项主裁决方向全部认同）→ **r2 修订同日全部吸收**（逐条落点见 [12-fulltext-extract §14 修订记录第 2 行](../design/12-fulltext-extract.md)）；两项子裁决 **fable 已 approve（2026-07-27）**；**ADR 本体待 fable 终签转 accepted**。
