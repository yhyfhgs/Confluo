---
title: Adapter 设计 · OpenReview
status: implemented
owner: fable5
updated: 2026-07-22
---

# Adapter · `openreview`

> 2026-07-22 全文重写：原稿被双评审退回（8 BLOCKER + 14 CONCERN，含 arxiv 缺陷复发 3 项），且 [LIVE] 勘察证伪原稿三处关键假设（匿名可读 notes、v1/v2 按年切分、venue id 模板拼接）。本稿依据勘察实测（25 请求，归档 [research/site-survey/openreview.md](../../research/site-survey/openreview.md)）逐项闭合。**AC-2.1 / AC-2.2 的验收载体。**

## 1. 定位

- **family**: `open_access`（内容开放获取；访问需免费账号 token，见 §3——与 SSRN（D-011）同属 free_account 级）
- **服务 venue（Phase 2 范围：仅 `iclr`）**：ICLR 2013→当前（主会 Conference 卷；Workshop/TinyPapers/BlogPosts 为独立 venue 本期不注册）。NeurIPS 分工按 [design/03](../../design/03-open-access-module.md)：proceedings 主源走 `neurips_proceedings` adapter；其 OpenReview 评审数据源（design/03 命名 `neurips_openreview`）推迟，不在本文档范围。
- **capabilities**: `DISCOVER | ENUMERATE | RESOLVE | FETCH`（四位；无 SEARCH——冻结协议无 search()，先例 arxiv.md §1）。

## 2. 站点勘察摘要

来源：[research/site-survey/openreview.md](../../research/site-survey/openreview.md)（[LIVE] 2026-07-22 实测）。要点：

| 事实 | 值 | 出处 |
|---|---|---|
| API 双版本 | v2 `api2.openreview.net` / v1 `api.openreview.net`；**判定靠 group 的 `domain` 字段**（有→v2，无→v1）；官方明言不能按年份切（"API 1 may be used by some venues through 2024"） | [DOC]+[LIVE] |
| 鉴权 | `/notes` 与 PDF **匿名 403 `ChallengeRequiredError`**；OpenAPI 定义 cookie `openreview.accessToken` Required；仅 `/groups` 匿名开放（readers:everyone） | [LIVE] |
| 限流 | 60 请求 / 60s 滑动窗（`x-ratelimit-*` 头实测）；挑战门与限流相互独立 | [LIVE] |
| 分页 | limit≤1000，offset 翻页至 `count`（count=匹配总数非页内数） | [DOC] |
| 空态两形态 | 按 id 查未命中=**404 `NotFoundError` JSON**；按过滤器查零匹配=**200 `{"notes":[],"count":0}`** | [LIVE]/[DOC] |
| v2 note 结构 | `content.<field>.value` 嵌套（v1 为 `content.<field>` 直取）；顶层论文帖 `id == forum`；`content.pdf.value` 为相对路径 `/pdf/<40hex>.pdf` | [DOC] |
| accepted 判定 | `content.venueid.value == 主会 venue id` 即接收；被拒/撤稿/desk-reject 落 `submission_venue_id`/`withdrawn_venue_id`/`desk_rejected_venue_id` 类字段值 | [DOC] |
| ICLR 届表 | 2013/2014/2017 **小写** `conference`、2018+ **大写** `Conference`；**2015 主会缺失、2016 仅 workshop 无 conference 卷**（两届均无主会数据）；2013→2027 权威逐年表见勘察 §2——**不能硬编码模板拼接** | [LIVE] |
| robots | 两站相同、仅 `Disallow: /*?*email=` | [LIVE] |
| ToS | API 为官方定义的程序化接口（data upload/search/download）；禁止绕过 readers/writers 访问控制；平台有权设传输速率上限；元数据 CC0、评论 CC-BY-4.0；账号须真实身份、单账号 | [LIVE] 2026-07-22 |

## 3. 认证边界（本 adapter 的运行前提）

- **等级**：`auth.level = free_account`（AuthLevel 既有枚举），`provider_hint = openreview`。venues/cs_ai/iclr.yaml 随实现任务同步修改（现为 none——勘察证伪，属 venue YAML 勘误）。
- **Phase 2 最小 token 通道（不建 AuthProvider 框架——Phase 4 范围）**：用户以**自有** OpenReview 免费账号获取 access token，配置于 `PAPER_CRAWLER_HOME/config.toml`（`[auth.openreview] token = "..."`；家目录、仓库外）或环境变量 `PAPER_CRAWLER_OPENREVIEW_TOKEN`；adapter 构造时读取，经 HttpClient **client 级附加头**注入 `Cookie: openreview.accessToken=<token>`。依赖冻结件扩展：HttpClient 构造参数 `extra_headers: dict[str,str] | None = None`（带默认值的纯附加参数——phase2-implementation-plan §7 修订记录立项，随本 adapter 实现落地）。
- **无 token 行为**：enumerate/fetch 收到 403 ChallengeRequiredError → `auth_expired` → 整批 BLOCKED(auth)，`crawler status --blocked` 提示"在 config.toml [auth.openreview] 配置 token 后 `crawler resume --all`"；**discover 与 healthcheck 不受影响**（走匿名 `/groups`）。
- **红线（AGENTS §6 对照）**：token 为用户自有合法凭证（§6.1）；**不代注册账号**（ToS 单账号/真实身份条款）；token 不入 git（家目录 config，§6.4）、不入日志/报告（obslog redact 既有 token/cookie 形态规则覆盖）；不破解/绕过挑战门——token 是 OpenAPI 定义的官方鉴权路径，非绕过（§6.1/6.3）。
- ⚠ **实现期复核义务（首次带 token 冒烟）**：确认带 token 后 `/notes` 返回 200（勘察备注：挑战门存在被自定义 UA 触发的可能）；若 token 后仍被挑战，立即停用该通道并升级 decision-log 仲裁。

## 4. 各阶段实现方案

- **discover_timeline**：零网络。届表来自 **adapter 内置常量表**（勘察 §2 权威表编码：年 → 主会 venue id / None）+ venue YAML `quirks.openreview_group_overrides`（dict[year→id]，新届/修正覆盖通道）。产出 IssueRef **字段分解（定死）**：`volume=None`、`number=None`、`year=YYYY`（int——`--year` selector 过滤的生效字段，stages 靠它圈定）、`label='YYYY'`、`pub_date=None`、`paper_count_claimed=None`（discover 阶段不打 notes 端点）。**2015/2016 不产出 Issue**（内置表为 None——主会不在 OpenReview，平台事实；timeline 呈现"缺届"与 AC-2.1 anchor 表同口径）。
- **enumerate_issue**：①由 `issue.year` 查届表得 venue id（精确大小写）；②`GET api2/groups?id=<venueid>` 依 `domain` 字段有无定 v2/v1 base URL（每届一次、进程内缓存）；③`GET <base>/notes?content.venueid=<venueid>&limit=1000&offset=…` 循环翻页至累计 `count`；④**accepted 过滤**：`venueid == 主会 id` 即接收，`*Submission/Withdrawn/Desk_Rejected` 类值排除——AC-2.1"全部接收论文"的判定源；解析器按版本双套（v2 `content.<f>.value` / v1 直取）；⑤空态：200 `{"notes":[],"count":0}` 为**合法空结果正常完成**（非错误——arxiv noRecordsMatch 先例）；⑥字段映射：`identifier(scheme='openreview').value = forum id`（顶层帖 `id==forum`，原样保留大小写，无归一变换）；content 内 doi/arxiv 线索（2013/2014 常见）**入 `PaperStub.meta`（键 'doi'/'arxiv'），不产 identifier**（arxiv R3 裁决先例，防跨源早合并——Phase 3 ingest 建边）；`paper_count_claimed` 以 accepted 过滤后实数回填。
- **resolve_assets**：纯构造零网络：`content.pdf.value`（相对路径）→ `https://openreview.net<path>`，kind=pdf、version=None、`auth_needed=free_account`、`url_strategy=direct`；landing=`https://openreview.net/forum?id=<forum>`。SI（`content.supplementary_material` 存在时）→ kind=si 同域构造。**note 无 pdf 字段 → 产 0 个 pdf plan（正常非错误）**——2013/2014 届正文多在 arXiv（DBLP 电子版指向 arxiv，勘察 §9），跨源 arXiv 副本的发现与 preprint_of 关联归 Phase 3。
- **fetch_asset**：HttpClient.stream（携 token 头）下载；响应 `Content-Type: text/html`（删除页等）→ `gone`（token 失效的批量 HTML 由 403→auth_expired 路径先行拦截，此处兜底个别页）。`%PDF` 权威校验在 pipeline（冻结分工）。
- **healthcheck**：**匿名可用（不依赖 token）**，v1/v2 双端各一查合成单报告：`GET api2.openreview.net/groups?id=ICLR.cc/2024/Conference`（断言 200 且含 `domain`）+ `GET api.openreview.net/groups?id=ICLR.cc/2014/conference`（断言 200，v1 端点存活基线——2013-2017 届数据路径依赖它）。token 有效性不属 healthcheck（平台健康与用户凭证状态分离；token 问题由 BLOCKED 机制反馈）。

## 5. 限速与礼貌

| domain | 速率 | 依据 |
|---|---|---|
| api.openreview.net / api2.openreview.net | **30 rpm，并发 1**（实测 60/60s 窗取半保守） | [LIVE] 勘察 §6 `x-ratelimit-*` 头；ToS 限速权条款 |
| openreview.net（PDF/forum 页） | 30 rpm，并发 1 | 同一基础设施（GCP 前置），口径统一 |

- `default_rate.source_note` 引勘察 §6；UA 按 D-014；批量取数走 limit=1000 分页而非高频小请求。
- robots 合规：唯一禁则 `/*?*email=` → 本 adapter **禁止任何携带 email 查询参数的请求**（兼隐私红线）；程序化访问的 ToS 依据见 §2 表。

## 6. 失败模式映射

| 站点现象 | error_class | 说明 |
|---|---|---|
| 403 `ChallengeRequiredError`（无/失效 token） | `auth_expired` | **实现注记（复审修订 2026-07-22）**：冻结 HttpClient 默认 403→`no_entitlement`；本 adapter 对 api/pdf 端点的 403 **上下文重分类**为 `auth_expired`（走计划 §2.1 预留的"adapter 捕获重分类"通道，无需读响应体——该平台对公开 venue 的 403 语义唯一＝挑战门/token 缺失，不存在"有 token 仍无权"场景）。重分类后走 Phase 1 既有 auth_expired→整批 BLOCKED(auth) 路由（AC-1.5 同款），status 给 token 配置指引（§3） |
| 404 `NotFoundError`（按 id 精确查未命中） | `gone` | groups/单 note 场景；2015/2016 由届表 None 前置拦截不发查询 |
| 200 `{"notes":[],"count":0}` | —（**非错误**） | 过滤器零匹配的合法空态，正常完成 |
| 429 | `rate_limited` | HttpClient 统一处理；30rpm 自限下罕见 |
| 5xx | `transient` | HttpClient 统一映射 |
| 畸形 JSON / content 嵌套与版本预期不符 | `parse` | canary 标红（v1/v2 解析器错配信号） |
| 其余 4xx | `config` | HttpClient 兜底（请求构造缺陷，响亮停机） |

**已知冻结限制**（arxiv.md §5 先例同批承认）：`FetchResult` 无 http_status（fetch_log.http_status 本期 NULL）；metadata 请求不入 FetchLog（obslog jsonl 为限速审计证据）；Retry-After 仅观测不驱动调度。

## 7. Fixtures 与测试

- **T1 单元**：届表查询矩阵（大小写形态 ×2015/2016 None× overrides 合并优先级）；v1/v2 双解析器（`.value` 嵌套 vs 直取）；accepted 判定矩阵（主会 id / Submission / Withdrawn / Desk_Rejected / venueid 缺失五态）；pdf 相对路径拼接；meta 线索（doi/arxiv）提取。
- **T3 fixture 十一件套**（§6 全部 error_class **含 transient/config** 各有落点——test-plan §6 强制；**带 token 录制**，录制物为 CC0/CC-BY 公开元数据、录制前剔除请求头/cookie 残留；难录形态合成并标注）：①v2 notes 正常页（含接收 venueid、pdf 字段、≥1 条无 pdf note）②分页页（count>limit）③空结果 `{"notes":[],"count":0}` ④groups venues 主表节选（届表交叉验证）⑤v1 notes 页（2014 形态直取）⑥403 ChallengeRequiredError JSON→auth_expired（经 adapter 重分类）⑦404 NotFoundError JSON→gone ⑧429 含 ratelimit 头（合成）→rate_limited ⑨畸形 JSON（合成）→parse ⑩5xx 响应（合成）→transient ⑪400 响应（合成）→config。
- **T4 集成**：MockTransport 全链路 discover→enumerate→resolve，accepted 过滤计数断言；v1/v2 双路；**无 token→403→BLOCKED(auth)→配置 token→resume 恢复链路**（复用 AC-1.5 测试模式）。
- **AC-2.1 验收机制（anchor golden 表）**：`tests/fixtures/openreview/dblp-iclr-anchor.json`——逐年 `{year, openreview_venueid|null, accepted_count, dblp_slug, note}`。**生成程序（实现期）**：带 token 按 venueid 过滤取 `count` + **人工对照 DBLP TOC 页（`dblp.org/db/conf/iclr/iclr<year>.html`）核准**，双源核对、UPDATE_GOLDEN 纪律、人工过目留痕 records；2015/2016 标 null（缺届）、2013/2014 note"正文在 arXiv"。**验收判定 = `timeline iclr` 输出与 anchor 表全等**（届列表+计数；"与 DBLP ±0"经人工核准的 anchor 表传递，勘察 §9 约值仅供量级参考不作判定）。
- **AC-2.2 证据分层（D-018 模式）**：T4 离线（fixture 走 `pull iclr --year 2024 --limit 10` 全链，10 个 plan/魔数/对账断言）＋ T5 在线冒烟（预算 ≤12：groups 1 + notes 首页 1 + PDF fetch 2 + healthcheck 1，`MAX_REAL_REQUESTS=12`）＝ Phase 2 判定。**在线部分需用户 token——未配置时该项记 BLOCKED 待用户，验收记录如实标注**。
- **canary 样本（抗 flake，arxiv 先例）**：3 个跨届 forum id（2018/2021/2024 各 1；2018 可用勘察实例 `ryQu7f-RZ`）比对**规整化 title + venueid** 双字段；另 1 条匿名断言：venues 主表含 `ICLR.cc/2024/Conference`（无 token 也可跑的基线 canary）。
- **T6 runbook**：无（AC-2.1/2.2 为一次性验收，无 7 日类场景）。
- **验收关联**：AC-2.1、AC-2.2；测试类型定义见 [testing/test-plan.md](../../testing/test-plan.md)。

## 8. 风险与维护

- **挑战门语义变化**：若平台收紧（token 后仍挑战 / UA 白名单），停用并升 decision-log 仲裁（§3 ⚠ 复核义务）；
- **届表维护**：新届（2027+）随年度 canary 追加内置表；命名规约再变由 overrides 兜底；
- **v1 退役**：官方措辞暗示 v1 长尾存续——若下线，2013-2017 数据路径失效，届时评估 v2 镜像或标注届不可用（老届一次性回填入库后运行依赖趋零）；
- **decision 模板历届漂移**：accepted 判定依赖 venueid 语义（v2 统一），早届（v1）若有出入按届入 quirks 覆盖，canary 每届抽查；
- **2015/2016 缺届**：平台事实非本系统缺陷，anchor 表与 timeline 同口径呈现。
