---
title: 架构决策记录（ADR）
status: approved
owner: fable5
updated: 2026-07-23
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
- **附注（P0a 开放题②合并裁决）**：`types.SessionHandle = Any` → 具体 frozen dataclass 系 `types.py:128` 注释显式预留的**计划内受控具体化**（`Any\|None`→`SessionHandle\|None` 精化，既有 adapter 零改动），非协议漂移，无需独立 ADR，随本条记录。
- **影响**：pyproject 新增 `[project.optional-dependencies]`（auth / auth-browser）；`make check` 默认不 import 二进制依赖（惰性 + skip 门控）；CI 装 `[auth]`（轻）跑凭证库测试，`[auth-browser]`（重，Playwright）靠 `PC_BROWSER_TESTS` 手动门（auth-framework §10）——**cryptography/keyring/playwright 均不成核心路径硬依赖**。

## D-024 Phase 4 R0 平台勘察裁决：wiley 纳入（token 门控）+ acm_dl 维持出列（全文改道 unpaywall）

- 状态：accepted · 日期：2026-07-23 · 依据：[publisher-platforms-p4-recheck.md](../research/site-survey/publisher-platforms-p4-recheck.md) [LIVE 2026-07-23]
- **背景**：Phase 4 W0 R0 对四平台（Elsevier/OUP/Wiley/ACM）距 2026-07-20/07-22 原勘察做 3 天增量复核（实耗 5/25 在线预算，遇挑战/429 即停）。核心假设全部成立，无颠覆漂移；wiley/acm 两项需 controller 裁决。
- **决策**：
  1. **wiley 纳入本 Phase + token 门控**：TDM 端点 `api.wiley.com/onlinelibrary/tdm/v1/articles/{DOI}`、头 `Wiley-TDM-Client-Token`、速率 3 req/s + 60/10min **升级为活验**（GitHub `WileyLabs/tdm-client` v1.2.0 + 搜索索引二手确证）；token 可自助（WOL click-through TDM license，无邮件审批）但 entitlement 受订阅域约束。实现模式 = **完整 adapter + TDM 客户端 + token 存在性门控**（缺失→在线层 skip 不阻塞验收，s2 先例）；token 落 `[auth.wiley].token` Config-slot。**不整体顺延**（勘察稳定、实现风险低，顺延浪费已验证窗口）。双窗口限速经现有单 token bucket 表达（`RatePolicy(rpm=5-6, burst=3)`，[wiley.md §4](../design/adapters/wiley.md) 接缝结论：无需扩展 ratelimit.py 冻结件）。
  2. **acm_dl 维持 D-020 出列**（supersedes 无——延续 D-020 而非推翻）：出列两依据 R0 [LIVE] 复核**均未变**——(a) 全文挑战墙持续（OA 拆付费墙未拆机器人墙）；(b) ToS 明文禁 scripts/spiders 自动下载 + metadata harvest（[DOC] 原文未松）。**全文改道 unpaywall OA-fallback**（pipeline no_entitlement 兜底，auth-framework §8.1），**元数据维持 crossref+dblp**（畅通、不碰 dl.acm.org）；browser-fetcher 有限实现留待其落地后再评。
  3. **异常子类 + status_code 权威版归 T2**（P0a 开放题③）：`errors.py`/`http.py` 的 `AuthRequired`/`Challenged`/`status_code` 由 **T2 单一权威版**交付（T1/T2 同波，合并取 T2，沿 Phase 3 `ids.py` 约定）；健康门 N=20/15min、日配额 200、challenge 冷却 24h **确认沿 04 §4/§5 原文**（P0a 开放题）。
- **影响**：phase4-implementation-plan 新增 T-wiley 卡（W2 平台波第三件，opus/opus）+ 在线预算加 wiley 冒烟 ≤10（条件项）；elsevier-sd.md/oup-silverchair.md/wiley.md 扩写至实现级（status draft，待双评审）；acm-dl.md 维持出列口径不变；BLOCKER-1（elsevier key）/wiley token 缺失均计划内前置外部依赖，离线 DoD 不阻塞（D-018 分层）。
