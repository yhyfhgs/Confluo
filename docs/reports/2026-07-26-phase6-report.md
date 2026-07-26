# Phase 6 阶段报告 — 订阅与搜索（2026-07-26）

> 格式仿 [2026-07-24-phase5-report.md](2026-07-24-phase5-report.md)。**本稿由 T10 收尾撰写**：**21** 张任务卡
> （主线 T1+T1b/T2–T10 共 11 卡、修复批 F1–F7 共 7 卡、设计批 R1/R2 共 2 卡、在线批 M1 共 1 卡；T1b/F7
> 系执行期间发现接缝/在线缺陷后增补，沿 F6"定稿增补卡"先例补入 [phase6-implementation-plan.md](../plan/phase6-implementation-plan.md) §4/§5）已全部合并；[AC-6 离线端到端验收 + 在线冒烟记录](../testing/records/2026-07-26-ac6-acceptance.md)
> 已由 controller（fable）亲验签署（`status: approved`，判定"达成"）——本报告引用其已签署结论，不重新独立验证 AC-6.x。
> `tag phase-6` **未打**（T10 职责边界之外，controller 在 opus 全分支终审 + 合并裁决后另打，见
> phase6-implementation-plan.md §4 T10 卡定义）。**opus 全分支终审已回"放行附条件"**（零 P0/代码
> 缺陷/红线，门禁逐位复现）——六项文档修正条件已随本次追加提交逐项闭合（详见 §8），`tag phase-6`
> 仍待 controller 执行。
> 依据：[development-plan §Phase 6](../plan/development-plan.md)、
> [phase6-implementation-plan.md](../plan/phase6-implementation-plan.md)、
> [acceptance-criteria.md AC-6/AC-0](../testing/acceptance-criteria.md)、
> [AC-6 离线端到端验收 + 在线冒烟记录](../testing/records/2026-07-26-ac6-acceptance.md)、
> [decision-log D-030/D-031](../plan/decision-log.md)、
> [post-phase5-audit](2026-07-24-post-phase5-audit.md)（本 Phase 全部修复批的处置依据）。
> 代码版本：`main` @ `e80f213`（本报告写作时点；`tag phase-6` 待 opus 全分支终审、合并裁决后由 controller 打）。
> `phase-5..e80f213` 共 **47 commits / 0 merges**（任务分支在隔离 worktree 内开发、由 controller 滚动
> squash 合并进 main 的常规提交，非字面 `git merge`）；`git diff --shortstat phase-5..e80f213` =
> **125 files changed, +18860 / -514**（src+tests 79 文件 +15822/-407；docs 30 文件 +2337/-95；
> venues+subscriptions 13 文件 +535/-12；其余为 scripts/ 与顶层配置文件）。全部 47 commit 均带
> `Co-Authored-By: Claude Fable 5` 尾行（47/47，git 纪律零缺）。

## 1. 概览

Phase 6「订阅与搜索」**21 卡**5 波次（较原计划新增 T1b/F7 两张执行期增补卡，详见
phase6-implementation-plan.md §4/§5）（W0 八卡并行铺开 T1+F1+F2+F3+F4+F5+R1+R2 → W1 滚动补位
T2+T3+T4+T8(部分)+M1 → W2 T5+T6+T7 → W3 T9 → W4 T10）**全交付**，实际合并顺序与波次并行图
（phase6-implementation-plan.md §5）吻合，零波次外插队；冲突面预算表所列的三处真正串行点
（repo.py 由 T1 独占先行、cli.py 由 T5 独占、`.gitignore` T5 一处）均按预期无冲突落地。

门禁全量测试从 tag `phase-5` 终态的 **3056 passed / 28 skipped** 增至本次 T10 亲跑复现的
**3820 passed / 28 skipped**（**+764 测试**，coverage **98.99%**，Phase 6 期间中途曾达峰值
**99.00%**——F7 卡新增测试相对新增语句行数的比例把末位小数小幅拉回；`ruff check`/`ruff format --check`/
`mypy src` 三项全绿，**EXIT=0**，46.85s，详见 §7 门禁）。28 个 skip 与 Phase 5 终态同构（全部
contract 能力缺口型，未新增）。adapter 数**不变**（仍 20——本 Phase 未新增平台 adapter，只扩展既有
`nber` 的 program RSS 增量通道）；venue 数**不变**（仍 58，仅 `aeri`/`jel`/`nber` 三个既有 YAML 的
ISSN/quirks 字段小改，M1/R2 供数），`crawler venues lint` 本次亲跑 58 个全过。

新增一个包：`src/paper_crawler/subs/`（8 模块：model/types/compile/filter/guard/watermark/watch/report，
共 4208 行），落地订阅 DSL 全链路——解析校验→查询编译→本地过滤+护栏→watermark 增量→watch 编排+CLI→
日报渲染；新增用户可见目录 `subscriptions/presets/`（9 个预置 topic 包）。既有代码侧新增一张表
`paper_weak_key`（schema v3，F1/D-031）。

AC-6 四条判据（AC-6.1 多 topic 7 天/AC-6.2 护栏熔断/AC-6.3 SSRN 无下推补偿/AC-6.4 下推-本地一致）
**全部 PASS**：[AC-6 记录](../testing/records/2026-07-26-ac6-acceptance.md)§1 逐条判定 + §8 fable 亲验
签署"**达成**"（2026-07-26）——离线 DoD 判据全部在隔离 worktree 内实测复现（`test_subs_ac6_acceptance.py`
6/6 + 既有回归 111 例零回归）；在线冒烟延伸经 F7 卡修复后可用（§3 在线预算台账）。

## 2. 关键决策

两条新 ADR 于 2026-07-26 正式化（[decision-log.md](../plan/decision-log.md) D-030/D-031）：

- **D-030 · Browser-Fetch 横切件形态定稿 + CF-403 挑战判定契约演进（S-c）+ 冷却键粒度修复（E-1）**：
  R1（opus 起草/fable 定稿）在 [ssrn.md §11](../design/adapters/ssrn.md) 设计种子基础上产出正式详设
  [design/11-browser-fetch.md](../design/11-browser-fetch.md)（approved），量化两案（薄接缝最小件 vs
  独立横切子系统）10 维取舍表后**采纳案 A**——决定性理由是"能力面恰好等于 AC-0 合规面"（D-029"非批量
  非默认"红线下，案 B 的核心增量恰是不允许行使的能力）。**本 Phase 交付详设，不交付实现**（落地 Phase
  由 controller 另裁，可能 Phase 6 末 stretch 或 Phase 7；草案验收标准 `AC-BF.1~6` 待转正）。同批裁决的
  两项**既有 httpx 路径**缺口（不依赖横切件实现，独立可修）随即立卡 **F6** 落地：① CF-403 头级判定采
  **S-c**——`http.py` 403 分支新增 `cf-mitigated: challenge` 头判别→CHALLENGE（此前统一映射
  NO_ENTITLEMENT），复用 `ChallengeDetector` 单一权威源、零特征串复制，全库 fixture 扫描零翻转；
  ② 冷却键粒度采 **E-1**——冷却判定上移至 family 判别之前（修复 `open_access` family 冷却"写而不读"），
  `RENDER_PAGE`/挑战场景冷却键改域级（向前兼容读旧 `<adapter_id>.json` 键）。
- **D-031 · 弱信号候审匹配键改为观测级键集合 + 同级 tie-break 复合序**：审计（post-phase5-audit P1，
  AC-3.4）实证注入顺序可静默改变弱信号候审边数（隔离脚本复现：序 A,B,C→1 边，序 C,A,B→0 边）——根因是
  匹配键取 paper 行**当前** `title_norm`/`_first_author`，会被高优先源字段收敛改写、抹掉匹配面。
  **决策**：匹配键改为**观测级键集合**（新表 `paper_weak_key`，schema v3，单调只增、不被收敛改写；
  新建/强合并/冲突并入三路径均记键并对新键重判候审），终态候审边＝键集合有交的输入对、与到达序无关；
  同级（同源二次观测）tie-break 由纯字典序改**复合序**（文本更长者胜/等长取字典序小者，修复前缀恒胜
  压制信息增补的系统性偏向；`year`/`pub_date` 纯 min）；新增取证抓手 `_field_tie` 供 Phase 7
  dedupe review。语义代价如实入档：跨观测拼接键（行态键）漏标不可序无关化，方向 fail-safe（宁可两条
  待审）。F1 opus 执行 + opus 审查（放行附条件全闭合，变异体 M3/M4/M8 补锁后 KILLED）+ fable 合并裁决。

## 3. 交付清单

development-plan §Phase 6 范围逐项：

### 3.1 主线（订阅域，新包 `src/paper_crawler/subs/`）

| 卡 | 交付 | 关键 commit |
|---|---|---|
| T1 订阅 DSL 地基（接口冻结件产出） | `subs/model.py`（`Subscription`/`SourceSelector`/`LocalFilter`/`Guard`/`Actions` dataclass + YAML 加载校验，未知字段/非法正则/负数 guard 一律 fail-loud，`_DuplicateKeySafeLoader` 拒绝重复键静默覆盖）；`subs/types.py`（`CompiledPlan`/`PlanStep`/`RunSummary`/`ReportEntry` 冻结件全集）；`storage/repo.py` 增 `SubscriptionRepo`（CRUD + watermark 读写）；`subscriptions/` 目录骨架 + README | `bdf0b14`（feat）+ `dd61a7d`（深审 3×P1 热修：声明序往返/重复键 fail-loud/`RunSummary` 承载 AC-6.2 字段）+ `cf4068f`（T1b 接缝终裁：过载分布三元组） |
| T2 六源查询编译器 | `subs/compile.py`——duck-typed per-source 编译器，`Subscription→CompiledPlan`；能力映射对齐 design/09 §3（arxiv 布尔式完整下推/crossref issn 重复键/openalex filter/s2 bulk/nber program/ssrn `topic_filter` 本地补偿接线，检查单 #10 闭合）；`DATE_WINDOW_PARAMS` 声明各源日期窗参数名 | `ca84df9`（feat，66 用例）+ `f3367e7`（审查七项：谓词只标有实现者、取值域把关，88 用例） |
| T3 本地过滤器 + 护栏引擎 | `subs/filter.py`（`title_regex_any`/`exclude_regex`/`min_year`，大小写不敏感，命中规则记 `matched_rules`；`PREDICATE_REGISTRY` 只登记有实现的补偿谓词）；`subs/guard.py`（`max_new_per_run` 熔断判定+`dedupe_against_library`+`OverloadReport` 数据结构） | `66617f8`（feat，50 例）+ `a3782df`（审查 P2#4：`_counts_by` 条目内标签去重） |
| T4 watermark 增量语义 | `subs/watermark.py`——三策略（日期上界+重叠窗/日期游标 `DateCursor`/id 集合差分 `IdSetDiff`），序列化 `subscription.watermark_json`（`schema_ver` 留演进缝），推进纪律=**run 成功才推进** | `dc85da4`（feat）+ `f23b475`（审查 P1×2：s2 年粒度→日粒度、ssrn `IdSetDiff`→`DateCursor`；P2 结构性根治：`DATE_WINDOW_PARAMS` 迁至叶子模块 `subs/types.py`） |
| T5 watch runner + CLI | `subs/watch.py` 编排（编译→per-source 增量拉取→批内去重→本地过滤→护栏判定→入库/派生取回任务→watermark 推进→`subscription_run` 落记录→`RunSummary`）；CLI `crawler subs watch <name>\|--all [--dry-run]`，与既有 `crawler watch <venue>` 语义分离共存（`4dd5ef9` 命名联动裁决） | `1b77d6b`（feat）+ `5729d50`（审查 P1×2+P2×5+P3：批内去重 `_dedupe_within_batch`、参数下达面修复、nber RSS 接线） |
| T6 日报渲染 | `subs/report.py`——纯函数 `render_daily`，多订阅合并一份 `daily-YYYY-MM-DD.md`；golden 快照三例字符级稳定 | `a6cc261`（feat）+ `31e7000`（审查后改造：过载分布切 distribution 优先路径） |
| T7 nber RSS watch 转主 | `adapters/nber/rss.py`——19 feed 中 5 个 `[LIVE]` 实证映射（AP/CF/EFG/IFM/ME）+ `discover_incremental` duck-typed watch 流 + id 集合差分桥接；proxy year 缓解 `min_year` 系统性排除（真实 RSS `<item>` 100% 无 `pubDate` 的在线实证发现） | `44ec3f3`（feat，43 例）+ `bf6e635`（审查 P1×2+在线坐实 5/5+P2 批）+ `63617c6`（proxy year 终笔） |
| T8 预置 topic 包 | `subscriptions/presets/` ×9（design/09 §4 清单）；每件头注 precision/recall 取向；经典论文标题回归实测发现并修复 P1×7（死子句/词族过窄） | `89e2f90`（feat）+ `c3f72bf`（审查修复：9 preset 领域词族 P1×7+P2 批+design/09 §2 反哺脚注） |
| T9 AC-6 验收 | 离线端到端 + 在线冒烟；[验收记录](../testing/records/2026-07-26-ac6-acceptance.md)（四条判据 PASS，fable 亲验签署"达成"） | `a226ef4`（T9 起草）+ `5a62004`/`4f7e0bd`/`e80f213`（F7 修复+复验+签署，见下） |

### 3.2 修复批（审计遗留，全部独立、与主线零文件交集）

| 卡 | 交付 | 关键 commit |
|---|---|---|
| F1 AC-3.4 合并顺序无关修复 | 弱信号候审匹配键改观测级键集合（新表 `paper_weak_key`）+ tie-break 复合序 + `_field_tie` 取证抓手（D-031，详见 §2） | `5dbc422`（fix）+ `5130c4a`（审查附条件十项全闭合）+ `591b8d0`（D-031 ADR 文档） |
| F2 config TOML 错误分类 + 文档滞后三项 | `config.py::_load_toml` 补 `TOMLDecodeError→CrawlerError(CONFIG)` 包裹；`unpaywall/adapter.py` docstring 精确化；`aggregators.md §5.2` 回填 dblp `<bht>` 真实 schema；`auth-framework.md §8.3` 日配额表述修正 | `6b3ab88`（fix）+ `de55f07`（unpaywall docstring 追加精确化） |
| F3 aaai_ojs 历史卷冷回填修复 | 跨卷分区缓存兑现"一趟"语义：首个历史届触发单趟全库收割、边流式产出边缓存其余历史卷；语义护栏四条（当前届永不读写缓存/仅收割跑完才发布/触顶 50k 响亮降级/未注册卷丢弃）。冷回填请求数 O(历史届数×全库页数)→O(全库页数)（4 请求 vs 修复前 10） | `fd956fd` |
| F4 静默降级六项清账 | `_oai.py` 响亮区分"合法空态"vs"真异常"；openreview 多页翻页专测补齐；pmlr 全卷零 `pdf_url` 新增 WARNING；econsoc 当前年 30 天回看窗完整性提示；acl_anthology bulk 对账新增独立交叉校验 | `d7541db`（fix）+ `e18c1a4`（审查追加：台账归属澄清+4 项修正） |
| F5 测试基建 | `test_cli_canary.py` 断言列表补 `aea` + **集合等值自断言**（根治"注册了却没验证"反模式第三次复现）；`test_migrations.py` 连接纪律（`contextlib.closing`）；`scripts/canary_weekly.sh` + launchd/cron plist 模板（不常驻、不改 CI） | `d536217` |
| F6 CF-403 判定演进 + 冷却键粒度修复 | `http.py` 403 分支 S-c 头级判别；`runner.py` 冷却判定上移至 family 判别前 + 冷却键改域级（D-030 裁决②③实现，详见 §2）；全库 fixture 双扫描零翻转 | `3b2977d`（fix）+ `38045c7`（审查五项闭合：OA 旁路前移冷却门/键退化如实/过期清理/文档同步）+ `9246102`（INDEX 联动补漏） |
| F7 watch 在线可用性两接缝修复 | `subs/watch.py::_lower_bound_of` 把窗值解回 ISO 下界喂 `since`（修复 arxiv 恒失败：`badArgument`"start date too early"）；`CrossrefAdapter` 新增日窗通道 `_window_bounds`（venue `quirks` 日期 filter 与桶年取交集，修复 ssrn 整年枚举风险：155,461→6,067 条，25.6× 收敛） | `5a62004`（fix）+ `4f7e0bd`（AC-6 记录更新+INDEX 同步）+ `e80f213`（fable 亲验签署） |

### 3.3 设计批

| 卡 | 交付 | 关键 commit |
|---|---|---|
| R1 browser-fetch 横切件详设 | `docs/design/11-browser-fetch.md`（draft→approved）：三消费方（ssrn 模式 B/aea pubs CF 全文/wiley 页面兜底）统一通道，`ChallengeDetector` 接线、BLOCKED 人工介入流、预算护栏离线逻辑、`AC-BF.1~6` 草案；D-030 定稿八项裁决全回填（详见 §2） | `02931c0`（draft）+ `dc83d64`（fable 定稿+D-030 ADR+F6 立卡） |
| R2 repec enrich + ssrn 覆盖候补合并评估 | `docs/research/enrich-eval-p6.md`（draft→approved）：① repec `aggregator-enrich` 判"再缓"，定档 Phase 7 首批候选（前置探针 P1–P3 三项全绿"GO"：JEL 在 bulk ReDIF 面确证、覆盖率 2010 起 100%；OAI `earliestDatestamp=2021-09` 增量面局限；主镜像单次连接失败样本不定性、备镜像 4/4 稳定）；② ssrn 覆盖候补 ladder 三路径终评——(b) RePEc 交叉核对**出列**（结构性无效，SSRN 不在 RePEc）、(c) 浏览页 census**永久否决**（触 Cloudflare 红线）、(a) OpenAlex 补枚举**条件立卡**（Phase 7 stretch，需 U2/U3 落 ≥90% 分支） | `4a78c01`（draft）+ `eddd83f`（fable 定稿 Q1-Q13 裁决签署+M1-d/探针回填+五处联动修正） |

### 3.4 在线批与在线预算台账

全部谨慎执行、逐请求入 obslog，结果无论成败如实回填文档：

| 批次 | 内容 | 预算/实耗 | 来源 |
|---|---|---|---|
| M1 在线闭合批 | econsoc `[UNRESOLVED①②③④]`（②已解决/③部分推进/①④遇 Cloudflare 交互质询维持未解决）+ aaai A⑥⑦复查（`ojs.aaai.org` 恢复，两项闭合）+ aea `aeri`/`jel` ISSN 转 `[LIVE]`（8 刊出处全清零）+ OpenAlex 无-DOI SSRN 抽样（供数 R2） | ≤35 / **15** | `d7793e5`（+`2d85e9d` 审查回执修正 7 项 P2+4 项 P3，不改结论） |
| repec 前置核实探针 | JEL bulk 面确证（P1）+ OAI 增量面局限确认（P2）+ 镜像稳定性抽样（P3），R2 供数 | 挂机动 / **6** | [enrich-eval-p6.md §6.2](../research/enrich-eval-p6.md) |
| acl_anthology SI 附件 URL 核实 | `D19-1001.Attachment.pdf` HEAD 核实 200 + 元数据吻合，闭合 `[UNRESOLVED]①`（独立小项，非本 Phase 主线，见 session-008） | 挂机动 / **1** | `6f6534c` |
| T7 nber RSS 坐实 | newap/newefg/newifm/newme 四个"命名模式外推"feed 实测 200+正确解析，证据分级"1 直证+4 外推"升级为"5/5 全 `[LIVE]`" | 挂机动 / **4** | `bf6e635` |
| T9 AC-6 冒烟延伸 | llm-agents/econometrics-methods 两 preset `--dry-run`（arxiv 恒失败实证，发现 §4 已知限制①②） | ≤15 / **3** | [AC-6 记录 §3](../testing/records/2026-07-26-ac6-acceptance.md) |
| F7 接缝复验 | F7 修复后在线复验（ssrn 日窗 count-only 探测 6,067 vs 整年 155,461；arxiv 收窄 venue dry-run 无 `badArgument`；cs archive 探测超时未重试） | controller 特批 ≤6 / **3** | [AC-6 记录 §4.1a](../testing/records/2026-07-26-ac6-acceptance.md) |
| T9 环境连通性探测（不占用任何预算行，为审计完整性一并如实记录） | 沙箱出网连通性确认：命中 `api.crossref.org`/`api.openalex.org` 200、`export.arxiv.org` 一次超时+一次 429，均在真正执行 `crawler` 命令前完成 | 不计入预算行 / **2** | [AC-6 记录 §3.4](../testing/records/2026-07-26-ac6-acceptance.md) |

**已知可核实的在线请求合计 34**（含上表最后一行 2 条环境连通性探测——该 2 条不占用任何预算行，
按 AC-6 记录 §3.4 原文"为审计完整性一并如实记录"的口径并入本报告 roll-up），远低于
phase6-implementation-plan.md §3 的 phase 级 ≤60 名义预算。
**一处台账缺口如实登记**（§4 事件⑤）：`repec 探针`(6) + `acl_anthology`(1) + `T7 坐实`(4) 三批均明确
标注"挂机动 ≤10 行"，合计 **11**，较该行名义上限**超出 1 请求**——三次独立会话各自依据静态余额推算
（"占机动预算 6/10"/"余 9"/未复核累计），无人核对过跨会话的累计消耗，暴露共享预算池缺一份运行时账本
的协调缺口（详见 §4 事件与教训）。

## 4. 事件与教训

- **① 并行接缝分歧的三层防线实证——s2/ssrn 日期窗案例**：Wave W1 中 T2（查询编译器）与 T4（watermark
  语义）并行开发（T4 依赖仅 T1，不依赖 T2），各自独立对同一对源（s2/ssrn）的"增量窗如何表达"做出了
  局部合理但互不一致的假设——T2 的 `DATE_WINDOW_PARAMS` 按早期设计假设声明 s2 为**年粒度**，ssrn 一度
  按"id 集合差分"（无日期窗）建模；T4 的 `subs/watermark.py` 独立构造三策略时，未与 T2 同一假设对齐。
  若不拦截，两处误配都会导致同一种失效模式：**窗被放大或塌陷 → 首跑撞护栏熔断 → 熔断不推进 watermark →
  下次仍是同样的窗 → 永久死循环**（且订阅级熔断连带冻结同订阅其他源）。拦截经过三层防线：**(1) 接口
  冻结件层**——T1 预先确立的类型契约给了"日期窗参数"一个可被检查的具体落点；**(2) 人工审查层**——T4
  自身的审查环节（非任何自动化）通过推演真实运行后果（"永久死循环"）人工发现两处误配（`f23b475`）；
  **(3) 结构性根治+自动化层**——修复不止改两个值，而是把 `DATE_WINDOW_PARAMS` 从 `compile.py` 迁至
  叶子模块 `subs/types.py`（T2/T4/T5 三方统一消费同一张表，谁存放都会让另两方反向依赖），并新增
  `⊆` 子集自断言（每源 `window_params()` 键集 ⊆ `DATE_WINDOW_PARAMS[source]`）防止未来静默再分歧。
  这是一个可复用的判例：**并行任务对同一接口的独立假设分歧，光靠"接口冻结"本身不够——真正兜底的是
  审查环节的人工失效推演，加上事后把"多头各自持有"结构性收敛为"单点权威+自动化校验"**。
- **② F5 集合等值自断言机制上线当日即逮住 `WatermarkInvalid` 的反模式治理闭环**：`03:32`，F5 卡
  （`d536217`）为根治 canary "注册了却没验证"反模式（审计 O4-P2，第三次复现）引入集合等值自断言技法
  （`assert set(listed) == set(registry.all())`）。**17 分钟后**（`03:49`），T1 深审（`dd61a7d`）独立
  借用同一技法（"同 F5 canary 手法"）修复 `errors.py` 的 `CrawlerError` 子类矩阵（此前也是"手工两条"
  清单，同源反模式）。而 T4 的 `subs/watermark.py`（`dc85da4`，`03:34`——恰好夹在两者之间）此时已在
  **独立开发的另一分支**里新增了 `WatermarkInvalid` 异常子类，对 T1 刚建立的矩阵一无所知。当 T4 的
  审查会话（`f23b475`，`04:09`）rebase 到已含 T1 新矩阵的 main 时，**新装的自断言机制当场把
  `WatermarkInvalid` 未登记的缺口揪了出来**（"main 期间新增的子类矩阵集合等值自断言正好逮住漏登记——
  机制按设计生效，非改测试迁就实现"）——一套**当天刚上线、专为治理"注册了却没验证"反模式而生的机制**，
  在自己诞生的**同一天**、面对一个完全独立分支产生的**真实新实例**，就以设计初衷的方式发挥了作用，
  而不是靠人工事后翻查发现。这是反模式治理从"事后台账登记"升级为"实时自动拦截"的一次完整闭环实证。
- **③ design/09 §5 过时文本致 T4 实现缺陷——"文档即缺陷源"的教训**：本项目纪律"实现只依据
  approved+ 文档"（phase6-implementation-plan.md §1 规则 7）本意是防止实现擅自偏离设计，但本次暴露
  其反面：`design/09-search-filter.md §5`（增量语义）在 Phase 5 的 D-029（SSRN 定位修订：元数据主路径
  改经 crossref prefix 枚举，时间过滤已可靠）之后**未同步更新**，仍留有"SSRN：最近 N 页 `abstract_id`
  集合差分"的旧文本。T4 早期按该文档字面实现 ssrn watermark 为 `IdSetDiff`，是**忠实执行了已过时的
  设计**，缺陷根源不在实现推理，而在文档滞后。T4 审查发现后一并修复了代码（改 `DateCursor`）与设计文档
  本身（`design/09 §5` 加删除线标注旧文本 + 补 D-029 联动修订说明，而非静默改写抹去痕迹）。教训：
  "实现只依据 approved 文档"这条纪律的前提是**文档本身必须随决策同步更新**——一旦决策（如 D-029）与
  其影响的下游设计段落（design/09 §5 引用 ssrn 的部分）之间出现更新时差，文档就从"防止偏离的锚点"
  反转为"缺陷的源头"。本次修复同时补上了这一具体时差，但机制层面（如何防止同类"决策已定、下游文档
  未同步"再发生）仍待后续过程改进，未在本 Phase 内解决。
- **④ 批内去重的三卡组合缺口——各卡局部正确但集成点无主**：T2（查询编译器）为多值 selector（如
  crossref 一个订阅声明 2 个 ISSN）正确地按设计生成**多条独立请求**（"重复键"模式，逐条下推，非
  `as_params()` 的 last-wins 合并）；T3（护栏引擎）的 `dedupe_against_library` 正确地对**已入库**的
  papers 做 identifier 去重；两者各自的设计范围内都是对的。但"**同一次 watch run 内**、来自多条并行
  请求的候选**在尚未入库前**是否可能重复"这一责任，既不在 T2 的范围内（T2 只管生成请求，不管请求结果
  如何合并），也不在 T3 原始设计内（`dedupe_against_library` 语义上限定为"对库"，非"批内"）——直到
  T5（编排层）把 T2 的多请求结果与 T3 的过滤/护栏串联执行时，`new_count` 虚高（同一 DOI 经两个 ISSN
  各来一次、被计为 2 条新增）才被**T5 自身的审查环节**以具体故障形式发现（凭空触发熔断、日报重复列
  条）。修复（`_dedupe_within_batch`，`5729d50`）在 T5 层新增了一段此前任何单卡设计都未显式声明过的
  逻辑。教训：**任务切分把"生成候选"（T2）与"判重入库"（T3）分给两张独立卡后，"批内多候选去重"这个
  处于两者之间的接缝天然没有默认属主**——除非任务卡显式点名"谁负责批内去重"，否则它只能依赖集成/编排
  层的事后审查兜底发现，而不是设计阶段被自然覆盖。
- **⑤（附加发现）共享"机动"在线预算行缺一份运行时账本**：`repec 探针`（6）、`acl_anthology`（1）、
  `T7 nber 坐实`（4）三次独立在线活动均明确引用同一条 phase6-implementation-plan.md §3"机动 ≤10"预算
  行，但各自的记录方式是"占用 6/10"（隐含起点为满额 10）与"余 9"（隐含起点为扣除自身前的 10）——没有
  一份文档在写下"余额"时核对过**另外两次**独立会话已经消耗的部分。三者合计 11，**较该行名义上限超出
  1 请求**。这不是红线违规（AC-0 五条与总预算 ≤60 均未触碰，三次动作本身也都符合"谨慎执行+超支即停"
  纪律），但暴露一个真实的协调缺口：**共享预算行在多会话并行消费时，若无一份中心化的运行时账本
  （而是各会话各自静态推算余额），累计值就可能悄悄超出声明上限而无人发现**——这是 T10 收尾盘点时通过
  比对三份独立记录的时间戳与自述余额才发现的，值得在 Phase 7 的预算记录规范中加一条"消费前先查其余
  会话是否已动用同一行"的纪律，或改用单一文件式运行时计数器。

## 5. 已知限制（如实记录）

- **browser-fetch 横切件本体未实现**：D-030 定稿采案 A，但**本 Phase 只交付详设**，实现权在 controller
  另裁（Phase 6 末 stretch 或 Phase 7）；ssrn 模式 B（全文层）/aea pubs 全文/wiley 页面兜底三处消费方
  仍全部 defer。`AC-BF.1~6` 为临时编号草案，落地 Phase 确定后转正回填 acceptance-criteria.md。
- **arxiv `search_query` 结构性缺口**（F7 期新发现，未修，转 Phase 7）：`_compile_arxiv` 把
  `categories`（`cat:` 组）与 `query`（`ti/abs` 字段级布尔式）合成单个 `search_query`，但 OAI-PMH 通道
  **无关键词查询能力**——`query` 分支完全不生效，9 个预置靠"`filters.title_regex_any` 手工镜像 query
  词族"这条**约定**兜底、非机制；且 `cli._watch_source_venues` 按 id 序取该源首个 venue，导致订阅声明的
  其余分类（如 llm-agents 的 `cs.LG`/`cs.CL`/`cs.MA`）实际收不到任何条目。F7 已做列账+响亮化
  WARNING+专测锁定措辞，修复方向已档（`arxiv_category` 走既有 `quirks` 通道 fan-out，adapter 零改动），
  但修复本身未落地。

  > **修复追记（2026-07-26，`fix/arxiv-category-fanout`）**：**fan-out 半边已闭合**——`categories` 编译成
  > 逐分类 `arxiv_category` 条目并由 `_compose_arxiv` 展开成独立请求，每条成对携带派生的 `arxiv_set`
  > （只推分类名会被注入 venue 的静态 set 压住，跨 archive 分类恒空），走既有 `venue_for` quirks 通道、
  > adapter 零改动；首 venue 路由对 arxiv 不再决定收割面。**谓词半边仍留**（`query` 布尔式无下推亦无
  > 补偿，靠 `title_regex_any` 镜像约定兜底），见 §6 检查单 #4。详见 AC-6 记录 §4 第 6 条的同名追记。
- **ssrn `FETCH` 仍未声明**：D-029 案 B + D-030 案 A 的组合结果——元数据层完整（`DISCOVER|ENUMERATE|
  RESOLVE`，站点零接触），全文层待 browser-fetch 横切件落地后才可能点亮，Phase 6 无变化。
- **nber 隔离在线验证 + `asset-pricing` preset CLI 端到端补验残留**：F7 §4.1a 因 ssrn count-only 探测
  实测 6,067 条 > 1000 门禁阈值，主动止损未实跑 `asset-pricing --dry-run`；nber 源本身在 `subs watch`
  编排下的真实网络验证本 Phase 未覆盖（T7 阶段已有 5/5 feed `[LIVE]` 证据，风险评估为低，controller
  亲验裁定转 Phase 7）。
- **econsoc `[UNRESOLVED①④]` 维持未解决**：ECMA 是否全刊 OA、过刊运行期终态两项因
  `econometricsociety.org` 本次遭遇 Cloudflare 交互质询（与 2026-07-24 勘察畅通结果不一致，成因未定性）
  未能闭合；建议提升该站 canary 优先级以持续观测风险面变化。
- **`economics-journals.md` ECMA 行 adapter 字段与 `publishers-platforms.md` 仍不一致**：Phase 5 T8 已
  发现并登记 `spawn_task`，本 Phase 未处理（不在 T10 窄范围内），跨 Phase 5–6 两阶段未清。
- **repec/ssrn 候补 ladder 均未落地实现**：R2 结论为"再缓/出列/否决/条件立卡"（§3.3），本 Phase 交付
  评估结论，不交付任何 enrich/枚举代码。
- **§4 事件⑤ 提及的机动预算台账缺口未做过程修复**：仅如实记录发现，未在本 Phase 内引入运行时账本机制，
  留待 Phase 7 或过程规范更新时处理。

## 6. Phase 7 开工检查单

1. **browser-fetch 横切件实现**（D-030 案 A 详设已 approved）+ `AC-BF.x` 转正：三消费方
   ssrn 模式 B/aea pubs 全文/wiley 页面兜底统一落地；落地后需回填 acceptance-criteria.md 的
   `AC-BF.x` 正式编号 + AC-5.1b 承接指针。
2. **repec enrich 首批候选**（探针 GO 入档，R2 §6.2）：`role: aggregator-enrich`、duck-typed
   `enrich_batch(dois)`，bulk ReDIF/OAI 零 HTML；立卡前先补两域（`www2.nber.org`/`repec.nber.org`）
   robots 核验（探针遗留项）。
3. **OpenAlex 补枚举 defer**（R2 ladder (a)，条件立卡）：W3 stretch 判定＝本 Phase 无余力，controller
   裁决是否与 repec enrich 合并评估或独立评估 U2/U3 落 ≥90% 分支的经济性。
4. **arxiv `search_query` 谓词/多分类 fan-out**（AC-6 记录 §4 第 6 条，F7 期发现未修）：`_compose_arxiv`
   按 `categories` fan-out（每条请求带一个 `arxiv_category`，走既有 `quirks` 通道，adapter 零改动）；
   关键词布尔式的本地补偿谓词需新的参数化谓词机制，改面更大。

   > **修复追记（2026-07-26，`fix/arxiv-category-fanout`）**：**fan-out 半边已闭合**（实现期新发现须
   > 成对下推 `arxiv_category`+派生 `arxiv_set`，否则注入 venue 的静态 set 存活、跨 archive 分类恒空）；
   > 本条**残留的是谓词半边**——`query` 关键词布尔式的参数化本地补偿谓词机制，Phase 7 照旧。


5. **`preprint_of` 建边零实现**（R2 Q6，enrich-eval-p6.md §附录）：repec 的 wp↔published 版本关联独家
   增值须先有此建边能力（merge/repo 侧新工作面），design/06 已有设计、无代码。
6. **aaai/econsoc 回看窗完整性闭合评估**：aaai_ojs 冷回填已修（F3），econsoc 当前年 30 天回看窗完整性
   缺口（与 aaai_ojs 同构）F4 审查后已将提示降级为 **INFO**（常态加窗路径每次触发，非异常条件，不占用
   WARNING 语义），但尚未做结构性修复（首拉当年仍可能漏收超 30 天论文）；econsoc ECMA `[UNRESOLVED①④]`
   亦待站点风险面稳定后重估。
7. **E-2 冷却键全量统一 + `cooldown` CLI**：D-030 §12 裁决点④"缓议"——`crawler cooldown status|clear`
   新 CLI 面登记为 Phase 7 检查单候选，横切件实现卡时一并重估；E-2（全量域键统一）列后续清账候选。
8. **http→auth import 分层**：本 Phase 未触及，若后续横切件实现需要更细的 provider/http 依赖分层，
   随该实现卡一并评估（未在本 Phase 发现具体缺陷，仅登记为需关注面）。**本条无既往台账出处，本报告
   首次登记**——底层事实：`http.py:52` 已 `import auth.challenge`（`ChallengeDetector`），即 http 层
   反向依赖 auth 包的具体点；F6 审查 P3 曾提及该依赖方向，但未单独立项，本条据此正式登记供 Phase 7
   评估是否需要分层解耦。
9. **幻影字段文档清账**：本卡（T10）已完成——`auth-framework.md §8.1`/`ssrn.md §4.4`/`aggregators.md
   §5.5` 三处"VenueSpec 声明 OA-fallback"幻影字段表述已订正为实况（`cli.py::_assemble_auth_seam`
   无条件置位）。此项**已闭合**，列入本检查单仅为完整性存档。
10. **全库 76 处/41 文件 `Database` 构造审计**（终审实测，归口审计域 S4，跨 Phase 遗留，本 Phase 未
    触及）：`test_migrations.py` 本 Phase 已加固连接纪律（F5），但更广泛的 `Database` 直接构造点是否
    全部遵循同等资源纪律未做全库扫描，建议 Phase 7 或下次全库审计时纳入。
11. **nber 隔离在线验证 + `asset-pricing` CLI 端到端补验**：F7 §4.1a 残留（§5 已详述），建议预算更宽
    的会话补一次（估 ~9 请求：ssrn 7 页 + arxiv 1 + nber RSS 1）。
12. **AEJ 四刊 catalog 行内注记与 notes 不一致清账**（口径订正——非 ISSN 未核验缺口）：
    `economics-journals.md` 表头"ISSN ⚠核验"的 `⚠` 是**列头标记**（提醒该列取值实现期以 Crossref 复核），
    非逐行未验证标记；`aej_macro`/`aej_micro`/`aej_applied`/`aej_policy` 四刊 ISSN 已随 Phase 5 M1 与
    `aeri`/`jel` 同批转 `[LIVE]`（8 刊出处全清零），并非未验证。残留的真实清账是：`aeri`/`jel` 两行
    备注列已补 `[LIVE 2026-07-26] crossref 核实` 注记，另外四行（`aej_*`）备注列仍为空、未同步补上
    对应注记——纯表格内部一致性清理，非阻断，随手可清但本 Phase 未纳入窄范围。
13. **aaai 全文回填批**（~5049 篇，≈2.8h@30rpm+5–15GB）：待用户令另行插单；enumerate 侧**首趟后边际
    历史届成本**已由 F3 降至 0 请求（首趟仍需一次全库扫描——F3 集成测试实测该场景 4 请求 vs 修复前
    10 请求，非"整体 0 请求"），仅剩 fetch 阶段待令。
14. **elsevier T7b / S2 key 等外部依赖沿账**：elsevier API key（BLOCKER-1，跨 Phase 3–6 四阶段未清）、
    S2 key、wiley TDM token、oup SSO 首登 runbook——均为计划内外部依赖，非阻断，待用户执行（见
    progress.md 快照"待用户执行"清单）。
15. **`economics-journals.md`/`publishers-platforms.md` ECMA 行 adapter 归属表述不一致清账**（§5 已知
    限制沿账，Phase 5 T8 `spawn_task` 移交、跨 Phase 5–6 两阶段未清）：今日实况——前者（`economics-
    journals.md` ecma 行）写"`econsoc`（当前段自营 OA）/`wiley`（过刊段，D-028）"；后者
    （`publishers-platforms.md` econsoc 行）写"TE、QE、ECMA(部分)"。两处对同一事实（econsoc 服务 ECMA
    当前段、wiley 服务 ECMA 过刊段）的表述结构不同，未经统一措辞规范核对，建议 Phase 7 择一表述范式
    统一改写。
16. **机动预算运行时共享账本**（§4 事件⑤ 载体行）：repec 探针/acl_anthology/T7 坐实三批共享同一条
    "机动 ≤10"预算行、累计 11、超线 1 请求（§4 详述），根因是缺一份跨会话运行时账本；建议 Phase 7
    预算记录规范新增"消费共享预算行前核对其余会话已用量"纪律，或改用单一文件式运行时计数器承载
    "机动"（及其他共享行）的累计消耗。

## 7. 门禁

`make check`（`sync-dev` + `ruff check` + `ruff format --check` + `mypy src` +
`pytest tests/unit tests/contract tests/integration --cov=paper_crawler --cov-fail-under=80`）T10 本次亲跑：

```
3820 passed, 28 skipped, 28 warnings in 46.85s
Required test coverage of 80% reached. Total coverage: 98.99%
EXIT=0
```

ruff/mypy 均无输出（全绿）；与 [AC-6 记录](../testing/records/2026-07-26-ac6-acceptance.md)§8 fable
亲验台账"3798→3820 passed / 28 skipped / 99.00%→98.99% / EXIT=0"逐位核对一致。

## 8. 签署

- **T10 初判（2026-07-26）**：21 卡全交付（主线 T1+T1b/T2–T10、修复 F1–F7、设计 R1/R2、在线 M1+探针）；门禁 3056→3820（+764 测试，coverage 98.99%）；AC-6 四条 PASS（fable 亲验签署）；D-030/D-031 两条 ADR；在线预算 ~34/60（机动行 11/10 记账缺口如实入档）；判定列待 controller 终审裁决。
- **终审（2026-07-26，opus 独立全分支）**：放行附条件——零 P0/零代码缺陷/零红线，门禁逐位复现（3820/28/98.99%/EXIT=0 + venues lint 58/58 + 尾行 48/48 + git 历史线性零 merge）；条件六项（检查单补载体 ×2、事实订正 ×4+出处 ×1、卡数统一 ×9 处+计划回填、INDEX 漂移 ×3、roll-up 口径、design/09 nber 条目）已全数闭合（`5c2c865`）。
- **最终判定（fable 合并裁决 2026-07-26）**：**Phase 6 判定：达成**。AC-6 四条 PASS（离线 DoD + F7 后在线通道实证可用）、AC-0 全程零触碰、终审七项清单全 PASS、放行条件全闭合。tag `phase-6` 随本裁决落地。
