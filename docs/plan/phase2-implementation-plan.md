---
title: Phase 2 实施计划 — Open-Access MVP
status: approved
owner: fable5
updated: 2026-07-21
---

# Phase 2 实施计划 — Open-Access MVP

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development 逐任务派发执行。
> 判定依据：[development-plan §Phase 2](development-plan.md)、[acceptance-criteria AC-2/AC-0](../testing/acceptance-criteria.md)、[Phase 1 报告 §6 开工检查单](../reports/2026-07-21-phase1-report.md)、D-013/D-014/D-017。
> 实施模式沿用 [phase1-implementation-plan.md](phase1-implementation-plan.md) 验证过的全部纪律（接口冻结先行 / worktree 波次并行 / 每任务独立审查+fix 循环 / 主 agent 合并亲跑门禁 / 全分支终审 / SDD ledger）。

**Goal**：8 个 open_access adapter 上线（arxiv 先行），AC-2.1~2.6 全过；首次引入真实网络流量，红线与限速纪律全程在线。

**Architecture**：Phase 1 冻结接口不变（SourceAdapter 协议 / types / errors / pipeline 六阶段）。Phase 2 新增三块地基后逐 adapter 滚动：①核心硬化包（审计脱敏+事务化）；②共享 HTTP 客户端 `http.py`（httpx 落地，D-017）；③在线测试基建（T5 marker/护栏/canary）。每个 adapter = 独立分支、独立详设门禁、独立验收合并。

**Tech Stack**：Python 3.12+ / httpx（本 Phase 引入，D-017 既定）/ 其余不变（sqlite3 标准库、pydantic v2、typer、pytest+coverage、ruff、mypy strict）。**不引入**：Playwright（Phase 4）、feedparser 等 XML 便利库（用标准库 `xml.etree`——arxiv Atom/OAI 结构简单，依赖最小化原则 D-017）。

## Global Constraints（每个任务隐含继承）

- **AC-0 红线五条**（acceptance-criteria）：无盗版源集成点；无 CAPTCHA 求解；凭证/session/PDF 不入 git；日志与报告无未脱敏敏感值（本 Phase 起含 `fetch_log.url`）；限速 ≤ 站点声明、robots 禁区不访问。
- **真实网络纪律**（AGENTS §6，本 Phase 首次生效）：默认测试**零真实网络**（T1-T4 全离线）；T5 在线冒烟显式 `-m online` 才跑、单次运行真实请求数有硬护栏；UA 一律 `PaperCrawler/<ver> (personal research; mailto:<user_email>)`（D-014，email 来自 config，不硬编码）。
- **限速出处**：每个 adapter 的 `default_rate` 必须带 `source_note` 注明出处（types.RatePolicy 已强制字段）。
- **门禁**：`make check` 全绿（ruff + format + mypy strict + pytest + 覆盖率 ≥80%）方可合并；adapter 解析器模块覆盖 ≥90%（test-plan §6）。
- **详设硬门禁**：每个 adapter 开工前对应 `docs/design/adapters/<id>.md` 必须 `approved`（status-workflow）。
- **提交规范**：Conventional Commits，scope 用 `adapter:<id>` / `core` / `testing`；尾行 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`；任何 git 写操作前 `git branch --show-current` 确认（分支卫生教训）。
- **repo 事务约束**（Phase 1 移交）：repo 方法自带事务不可嵌套；T1 新增的组合事务 API 是唯一例外入口。
- **fixture 纪律**：真实站点录制的 fixture 一律脱敏（无 cookie/token/个人信息）后入库；golden 重录走 `UPDATE_GOLDEN=1` + 人工过目（tests/fixtures/README）。

## §2 接口冻结件（Phase 2 增量；T1-T3 落盘后冻结，改动须仲裁）

1. **`http.py` · HttpClient**（T2 产出）：
   ```python
   class HttpClient:
       def __init__(self, *, user_agent: str, timeout_s: float = 30.0,
                    transport: httpx.BaseTransport | None = None) -> None: ...
       def get_text(self, url: str, *, accept: str | None = None) -> str: ...
       def get_bytes(self, url: str, *, accept: str | None = None) -> bytes: ...
       def stream(self, url: str) -> Iterator[bytes]:  # 供 fetch_asset 交给 io.write_stream
       # 全部方法：HTTP 异常/状态 → raise CrawlerError(ErrorClass, detail)
       # 429/503+Retry-After → CrawlerError(RATE_LIMITED, detail 含 retry_after_s=<n>)
       # transport 注入口 = T4 测试用 httpx.MockTransport 的唯一通道
   ```
   映射表（冻结，T2 执行期补全）：timeout/连接错及其余 httpx 传输异常（TooManyRedirects/DecodingError 等）→TRANSIENT；429→RATE_LIMITED；5xx→TRANSIENT（503+Retry-After→RATE_LIMITED）；401→AUTH_EXPIRED；403→NO_ENTITLEMENT；404/410→GONE；451→GONE（法律不可用=资源终态）；**其余 4xx（400/405/…）→CONFIG**（请求构造缺陷信号，响亮停机——arxiv offset>30000→400 即此类；adapter 可按上下文捕获重分类）。附加资源管理面：close()/上下文管理器（纯附加不破坏冻结签名）。重定向跳的 obslog 事件不含 elapsed_ms（httpx history 限制），终响应事件含。
   **Retry-After 裁决（W0 定）**：HttpClient **不做内部重试/等待**（单一职责，且限速器已把速率压到站点声明以下，Retry-After 实际罕见）；仅解析头值（秒数与 HTTP-date 两形态）写入 CrawlerError detail（`retry_after_s=<n>`）供日志观测；pipeline 维持冻结固定退避 2/8/30s（通常 ≥ 站点 Retry-After，保守合规）；domain 冷却维持 Phase 1 近似，真实冷却机制随 Phase 4 认证站点（修订记录 §7-1）。
   **obslog 义务**：HttpClient 每次请求记 debug 事件（domain / url 经 redact / status / elapsed_ms）——metadata 侧流量不入 FetchLog（冻结限制），jsonl 即其限速审计证据。
2. **repo 组合事务 API**（T1 产出）：`repo.finalize_fetch(asset_id, *, file_path, bytes_, sha256, fetch_log_row) -> None` —— commit 文件收尾三步单事务。
3. **在线测试契约**（T3 产出）：pytest marker `online`（pyproject 注册，默认 `-m "not online"`）；`tests/online/` 目录；每测试文件头部声明预算 `MAX_REAL_REQUESTS`，会话级 fixture 计数超限即 fail。
4. **canary 契约**（T3 产出）：`crawler canary [--adapter ID]` 遍历已注册 adapter 的 `healthcheck()`，输出健康矩阵（markdown），退出码 0=全健康/1=有不健康。
5. **arxiv 冻结细节**：已随 [design/adapters/arxiv.md](../design/adapters/arxiv.md)（approved 2026-07-21）定死——月度桶字段分解（volume=NULL / number='MM' / year=YYYY / label='YYYY-MM'）、identifier(arxiv) 去版本归一、asset.version=None（最新版语义）、journal_ref/doi 入 PaperStub.meta 不产 identifier、watch=当月桶重复 enumerate（零接口变更）、fixture 八件套、canary 三样本双字段比对。T4-T6 的 brief 以 arxiv.md 为需求源。

## §3 Stage A 任务卡

> 任务卡 = implementer brief 的源文本（scripts/task-brief 提取）。每任务：TDD、自审、独立 reviewer 双裁决（Spec+质量）、Critical/Important 回派修复、复审通过才合并。BASE 在派发前记录。

### T1 核心硬化包（opus · 分支 `fix/core-hardening` · worktree）
**Files**：storage/repo.py、pipeline/stages.py、obslog.py（如需）、adapters/mock_platform.py、tests/unit+integration 对应件
**要求**：
1. `fetch_log.url` 落库前经 redact（复用 obslog 现有 redact 形态规则）；扩展红线扫描断言覆盖 fetch_log 表内容（AC-0.4）。
2. `repo.finalize_fetch(...)` 组合事务（§2.2 签名）：mark_asset(fetched) + add_fetch_log 同事务；stages.py fetch 收尾改用之；旧的两步调用路径删除。AC-1.3 验收记录里的"已知窗口"附注在本任务后更新为已消除（勘误性修改验收记录 + design/05 若有涉及）。
3. mock 两处裸 ValueError → CrawlerError（非法 error_class→CONFIG、畸形 doi 尾段→PARSE），补对应单测。
4. backlog 小项：repo 双 is_primary 修复；registry `domains[0]` 空元组防御。
**测试**：现有 519 全绿不回退；新增：fetch_log 脱敏单测（含引号/嵌套形态）、finalize_fetch 事务原子性测试（注入中途异常回滚）、mock 错误类单测。
**DoD**：make check 绿；AC-1.3 kill 测试仍过且"每 asset 成功 fetch_log ≤1"断言可收紧为 ==1（消除缝隙后）。

### T2 共享 HTTP 客户端（opus · 分支 `feat/core-http` · worktree）
**Files**：新建 src/paper_crawler/http.py、pyproject.toml（httpx 依赖 + uv.lock）、tests/unit/test_http.py
**要求**：§2.1 冻结签名逐条实现。UA 从构造参数注入（调用方从 config 组装 D-014 格式，本模块不读 config）。httpx.MockTransport 全覆盖测试：每个 ErrorClass 映射分支、Retry-After 解析（秒数与 HTTP-date 两形态）、重定向跟随+obslog 事件、流式分块、超时。禁真实网络（单测全走 MockTransport）。
**DoD**：http.py 覆盖 ≥95%；make check 绿；映射表与 §2.1 冻结文本逐行一致。

### T3 在线测试基建（sonnet · 分支 `test/online-infra` · worktree）
**Files**：pyproject.toml（marker 注册 + addopts 默认排除）、tests/online/__init__.py + conftest.py（预算 fixture）、src/paper_crawler/cli.py（canary 命令）、src/paper_crawler/verify.py 或新模块（健康矩阵组装）、docs/testing/test-plan.md（T5 执行细则勘误补充）
**要求**：§2.3/§2.4 契约逐条实现。canary 对 stub adapter 输出 SKIP（NotImplementedError 捕获为"未实现"行，不算不健康）。预算 fixture：`real_request_budget(n)`，超限立即 fail 并提示。
**测试**：marker 默认排除的元测试（`pytest --collect-only` 断言 online 用例不在默认集）；canary 对 mock 的健康/不健康两态；预算超限 fail 路径。
**DoD**：make check 绿（全程零真实网络）；`crawler canary` 对 mock 出健康矩阵。

### T4 arxiv 纯逻辑件（sonnet · 分支 `adapter/arxiv` 第 1 段）
**Files**：新建 src/paper_crawler/adapters/arxiv/（__init__.py、ids.py、buckets.py、atom.py 骨架）、tests/unit/test_arxiv_ids.py 等
**要求**：①ID 两代解析/构造/规范化矩阵（`YYMM.NNNNN[vN]` 与 `archive.subject/YYMMNNN[vN]`，含非法形态拒绝）；②月度桶生成（1991-08 起点、当月未满、category→venue_id 映射）；③Atom/OAI XML 解析器（xml.etree，输入 bytes 输出中间记录 dataclass）——解析器与网络完全解耦（T3 fixture 直接喂）。字段映射按 design/06 §5 与 arxiv.md §3。
**DoD**：解析器覆盖 ≥90%；全离线。幂等键字段与 meta 清单按 arxiv.md §3（approved）逐字执行。

### T5 arxiv adapter 主体（opus · 分支 `adapter/arxiv` 第 2 段，串行接 T4）
**Files**：adapters/arxiv/adapter.py（ArxivAdapter(AdapterBase)）、entry point 注册、tests/contract/（arxiv 契约用例激活）、tests/fixtures/arxiv/ 三件套+补充
**要求**：discover_timeline（月度桶，无网络）/ enumerate_issue（OAI-PMH ListRecords + resumptionToken 翻页）/ resolve_assets（URL 构造，无网络）/ fetch_asset（HttpClient.stream→io.write_stream）/ healthcheck（Query API 固定 id 比对 title）。错误映射按 arxiv.md §5。default_rate=1 req/3s 带 ToU 出处。**contract 测试 12 skip 中 arxiv 相关 4 条转 pass。**
**DoD**：T3 fixture 回放全绿；adapter 模块覆盖 ≥90%；make check 绿。

### T6 arxiv watch 最小实现（opus · 分支 `adapter/arxiv` 第 3 段）
**要求**（按 arxiv.md §3 watch 裁决，**subscription 表不启用**——推迟 Phase 6）：`crawler watch <venue>|--all` 命令 + watch 编排＝对 preprint venue 的当月桶（跨月边界含上一月桶）执行 enumerate 级联（复用新鲜度 TTL；watch 强制 refresh 当月桶）；去重靠 identifier(arxiv) 主键天然保证。T4 集成测试：重叠窗口注入无重复入库、**七收割日回放模拟**（含 announce 延迟注入某日数据延至次日，AC-2.3 离线证据层，D-018）。

### T7 arxiv 收束（sonnet 实现 + 主 agent 验收）
5 个代表性 venue YAML（`arxiv-cs-lg`【AC-2.3 主承载】/`arxiv-stat-ml`/`arxiv-econ-gn`/`arxiv-q-fin-pr`/`arxiv-math-oc`，lint 全过；design/02 §2.2 顺带勘误补 preprint_channel identifiers 示例——现无模板）；其余 ~25 个白名单 YAML 留 Phase 2 收尾批量生成。tests/online/test_arxiv_smoke.py（预算 ≤10 请求：healthcheck 1 + 单桶 enumerate 首页 + 单篇 PDF fetch + **robots/ToU 实测复核**【arxiv.md §4 ⚠ 义务】）；canary 三样本注册（带版本号、规整化 title+primary_category 双字段）；AC-2.3 验收执行与记录（D-018 分层：T4 回放 + T5 冒烟 = Phase 2 判定）。

### 阶段中检（主 agent）：T1-T7 全并后亲跑 make check + CLI 真实旅程（arxiv dry-run→限量 pull→verify），SDD ledger 更新，Stage B 放行。

## §4 Stage B 滚动模板（每 adapter 一个标准工作包）

顺序（development-plan §Phase 2；acm_dl 已依 **D-020** 出列——红线优先，Phase 4 重评）：**openreview（AC-2.1/2.2）→ pmlr → cvf（AC-2.4）→ acl_anthology（AC-2.5）→ neurips_proceedings → aaai_ojs**。相邻无共享文件的 adapter 允许 2-3 线 worktree 并行；openreview 先行单独走（AC 载体，重件）。

每包固定流程（= arxiv 模式复制）：
1. **详设门禁**：`docs/design/adapters/<id>.md` 双评审（技术一致性+测试红线，档位按文档复杂度）→ 主 agent 裁决修订 → approved 提交。
2. **实现**：分支 `adapter/<id>`；纯逻辑/解析器先行（sonnet）→ adapter 主体（档位见 §6）→ fixture 三件套；契约测试对应 skip 转 pass。
3. **审查**：独立 reviewer 双裁决 + fix 循环 + 复审。
4. **验收合并**：fixture 回放全绿 + 在线冒烟（预算内）+ 对应 AC-2.x 判定 + canary 注册 → 主 agent 合并亲跑门禁 → ledger 记账 → 详设转 implemented。

## §5 W0 评审裁决记录（2026-07-21 已全部闭合；评审报告归档 session 日志）

双独立评审（A=技术一致性 opus / B=测试+红线 sonnet）各出 1 BLOCKER：A-F2 watch 增量在冻结 enumerate 签名上无法表达；B-G1 fixture 三件套仅覆盖 5 个 error_class 之 1（违反 test-plan §6 强制条款）。主 agent 裁决：

| # | 裁决结果 | 落点 |
|---|---|---|
| R1 | SEARCH 位本期**不声明**（capabilities 四位），Phase 6 加 search() 后点亮 | arxiv.md §1 |
| R2 | watch=当月桶重复 enumerate + identifier 主键去重（零接口变更）；subscription 表推迟 Phase 6；AC-2.3 证据三层分层 → **D-018** | arxiv.md §3/§6、decision-log |
| R3 | 月度桶 volume=NULL/number='MM'/year/label='YYYY-MM'；identifier 去版本归一；version=None=最新版，--all-versions deferred；journal_ref/doi 入 meta 不产 identifier | arxiv.md §3 |
| R4 | §2.1 清单与评审 A F5 核对全齐；三处冻结限制承认（http_status/metadata 不入 FetchLog/Retry-After 仅观测），metadata 审计走 obslog（design/05 §7 + GLOSSARY 勘误） | arxiv.md §5 |
| R5 | fixture 扩**八件套**（§5 全部 error_class 各有落点；503 快照含响应头；parse 态可合成标注） | arxiv.md §6 |
| R6 | 5 个代表性 venue YAML 起步，~25 个收尾批量；design/02 补 preprint_channel 示例 | 本计划 T7 |
| R7 | Kaggle bulk backfill **本期 deferred** 并在设计中显式声明（凭证走 ~/.kaggle 仓库外惯例，禁项目内存放） | arxiv.md §3 |
| R8 | development-plan Phase 2 范围勘误补第 8 项 acm_dl | development-plan |
| 附 | robots 两域名张力明文回应 + T5 实测复核义务；canary 三样本带版本号+双字段规整化比对；GLOSSARY 补 watermark 别名与"收割"条目 | arxiv.md §4/§6、GLOSSARY |

## §6 模型分档

| 角色 | 档位 |
|---|---|
| Advisor/编排/评审定稿/仲裁/全分支终审/AC 验收 | fable（主 agent） |
| T1 硬化、T2 http、T5 arxiv 主体、T6 watch、openreview、acm_dl、关键 reviewer | opus |
| T3 在线基建、T4 纯逻辑、T7 收束、pmlr/cvf/acl/neurips/aaai、轻 reviewer | sonnet |
| 卡壳升档 | opus→fable（SendMessage 续上下文优先于重派） |

## §7 执行期修订记录

| # | 日期 | 修订 | 依据 |
|---|---|---|---|
| 1 | 2026-07-21 | Phase 1 报告 §5"真实 domain 冷却随 Phase 2"降级为随 Phase 4：arxiv 场景限速器前置（1req/3s 保守值）使冷却机制冗余，Retry-After 仅观测不驱动调度 | 评审 A F4/F5 + 主 agent 裁决 |
| 2 | 2026-07-21 | T1/T2 先于计划整体 approved 派发（其任务卡与 arxiv 评审零耦合，依据为 Phase 1 报告 §6 移交项）；计划于 W0 收束时整体定稿 | 用户并行度指令 + 主 agent 裁决 |
| 3 | 2026-07-21 | §2.1 映射表补全：其余 4xx→CONFIG（否决 implementer 的 GONE 兜底——400 是请求缺陷非资源终态）、451→GONE、传输异常超集→TRANSIENT、close()/上下文管理器附加 | T2 DONE_WITH_CONCERNS 仲裁 |
| 4 | 2026-07-22 | HttpClient 冻结件扩展立项：构造参数 `extra_headers: dict[str,str] \| None = None`（client 级附加头，纯附加带默认值）——openreview token 通道（cookie 注入）依赖；随 openreview 实现任务落地 | openreview.md §3（LIVE 勘察证实鉴权必需） |
| 5 | 2026-07-22 | openreview.md 双评审 REJECT 后回炉：LIVE 勘察（25 请求）→ 主 agent 全文重写 → 复审；openreview 定位修正为 free_account 级（勘察证伪匿名可读），Phase 2 范围仅注册 iclr | 评审报告 + survey 归档 |
