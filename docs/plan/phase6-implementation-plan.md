---
title: Phase 6 实施计划（订阅与搜索：DSL + watch + 护栏 + 日报 任务切分）
status: approved
owner: fable5
updated: 2026-07-26
---

# Phase 6 实施计划 — 订阅与搜索

> 主体范围锚点：[development-plan §Phase 6](development-plan.md)（topic/tag 订阅 DSL、`crawler watch`
> 增量调度、dry-run 计数预览、数量护栏、每日摘要报告）。设计依据：[design/09](../design/09-search-filter.md)
> （approved）+ [design/06 §2 subscription 表](../design/06-data-model.md)（implemented，0001 已建表）+
> [design/05 §watch 模式](../design/05-pipeline.md)（implemented）。
> 并入执行：[phase5-report §6 检查单](../reports/2026-07-24-phase5-report.md)（10 项）与
> [post-phase5-audit §6 处置建议](../reports/2026-07-24-post-phase5-audit.md)（P1×3 + P2 批 + 测试基建）。
> 编排：fable planner/advisor/合并裁决；执行与审查档仅 opus/sonnet（见 §6）。

## §1 Global Constraints（每个任务隐含继承）

1. **AC-0 五条红线**（[acceptance-criteria](../testing/acceptance-criteria.md)）全程有效：无付费墙绕过/
   CAPTCHA 求解、无盗版源、robots+ToS 遵守、凭证不入 git、无再分发功能。
2. **门禁**：每卡合并前 `make check` 全绿（ruff + mypy + pytest cov≥80%）；基线 3056 passed / 28 skipped /
   98.78%（tag phase-5 时点，开工日亲跑复核）。
3. **离线优先**：单元/契约/集成测试零网络（`socket.connect` 猴补看守既有）；在线动作只在 M1/T9 专项批内，
   预算见 §3。
4. **分支纪律**（[git-workflow](../process/git-workflow.md)）：一卡一分支一 agent；执行 agent 在隔离
   worktree 内工作并提交到卡分支；合并由 controller（fable）在主仓库执行——core 冲突面先到先合，后者 rebase。
5. **提交规范**：conventional commits + Co-Authored-By 尾行；文档改动同步 INDEX/front matter `updated`。
6. **Subagent 输出纪律**：执行 agent 返回文本仅报告"分支名 + 提交 hash + 测试结果 + 偏离清单"；不粘贴
   大段代码。审查 agent 返回结构化发现（P0/P1/P2 分级 + 逐条文件:行号）。
7. **设计边界**：实现只依据 approved+ 文档。design/09 为主依据；执行中发现设计歧义 → 停手上报 fable
   仲裁，不擅自定夺（本计划 §4 各卡"已裁决歧义"段已预清一批）。

## §2 接口冻结件（Phase 6 增量；T1 落盘后冻结，改动须 fable 仲裁）

| 冻结件 | 内容 | 消费方 |
|---|---|---|
| `subs/model.py` | `Subscription`/`SourceSelector`/`LocalFilter`/`Guard`/`Actions` 类型 + YAML 加载校验入口 | T2/T3/T4/T5/T6/T8 |
| `subs/types.py` | `CompiledPlan`/`PlanStep`（下推参数+补偿谓词标记）、`RunSummary`/`ReportEntry`（日报数据结构）、`WatchOutcome` | T2/T3/T5/T6 |
| `storage/repo.py` 增量 | `SubscriptionRepo`：subscription/subscription_run CRUD + watermark 读写（表已在 0001 建好，字段核对 design/06 §2） | T4/T5 |
| 既有冻结件 | `types.PaperStub`/`adapter.AdapterBase`/`errors` 层级/退出码 0/1/2/3 契约——Phase 6 **不动**；如需动走仲裁 | 全部 |

## §3 在线预算分项表（全 Phase 专项行 ≤60 请求；超支入档）

| 批次 | 内容 | 预算 |
|---|---|---|
| M1-a | econsoc [UNRESOLVED①②④] 闭合（ECMA OA HEAD 判定/切换日/过刊终态）+ ③ TE 对账查因 | ≤15 |
| M1-b | aaai A⑥⑦ 重跑（前置确认 `ojs.aaai.org` 恢复） | ≤6 |
| M1-c | aea `aeri`/`jel` ISSN [LIVE] 核实（跑既有 smoke 断言） | ≤4 |
| M1-d | R2 供数：OpenAlex 无-DOI works 补枚举可行性抽样（ssrn 覆盖候补 ladder 路径 a） | ≤10 |
| T9-online | AC-6.1 在线冒烟延伸（3 preset 单轮真实 watch，arxiv/openalex/crossref 各一次增量窗） | ≤15 |
| 机动 | 突发复核 | ≤10 |

## §4 任务卡

> 每卡五要素：范围 / DoD / 测试 / 分支 / 模型（执行/审查）。依赖显式标注。
> "已裁决歧义"= fable 预仲裁结论，执行 agent 直接采用不再上报。

### 主线（订阅域，新包 `src/paper_crawler/subs/`）

#### T1 订阅 DSL 模型 + 解析校验 + SubscriptionRepo（`subs/dsl-core`，**opus/opus**，**共享地基·接口冻结件产出者**）

- **范围**：`subs/model.py`（design/09 §2 YAML 全字段 dataclass + 加载 `subscriptions/*.yaml` + 校验：
  未知源/非法正则/guard 缺省补全 `max_new_per_run=200`）；`subs/types.py`（§2 冻结件全集）；
  `storage/repo.py` 增 `SubscriptionRepo`（0001 已建表，先核对 DDL 与 design/06 §2 一致，不一致上报）；
  `subscriptions/` 目录骨架 + README 短说明。
- **已裁决歧义**：①订阅域立新包 `subs/`（类比 `auth/` 包先例）；②DSL 未知字段=报错拒载（fail-loud，
  呼应审计 S1 原则）；③`schedule_hint` 仅存不调度（cron 外置，design/05 已定）。
- **DoD**：DSL 双示例（design/09 §2 llm-agents/asset-pricing-wp）逐字段解析通过；非法输入 12 用例矩阵
  （未知源/坏正则/负数 guard/空 sources 等）全部响亮报错；repo CRUD + watermark 读写落 DB 可回读。
- **测试**：unit（解析/校验/缺省）+ integration（repo 走真 sqlite）；covering `subs/` ≥95%。

#### T2 查询编译器（`subs/compilers`，**opus/opus**，依 T1）

- **范围**：`subs/compile.py`——每源 Compiler 把 `Subscription` 编译为 `PlanStep`（下推参数 + 本地补偿
  谓词标记），能力映射按 design/09 §3 表：arxiv（ti/abs/cat 布尔式 + submittedDate 窗完整下推）、
  crossref（ISSN + from-pub-date，期刊 watch 通道，design/08 §5）、openalex（concepts/type/
  from_publication_date）、s2（bulk venue/year/fieldsOfStudy）、nber（program 下推）、ssrn（仅分类近似 +
  **`quirks.topic_filter` 接线**——检查单 #10，ssrn.md §1 预留接缝，关键词全量标记本地补偿）。
- **已裁决歧义**：①编译器注册表 duck-typed per-source（不进 AdapterBase 协议，避免动冻结件）；
  ②源不支持的谓词一律标记 `local_only`，正确性以本地过滤为准（design/09 §3 原则句）。
- **DoD**：DSL→URL 参数用例表每源 ≥6 例（含边界：空 query/多值/NOT）；ssrn topic_filter 从 venue YAML
  读入并进 `PlanStep.local_predicates`。
- **测试**：unit 用例表驱动；contract（PlanStep 结构稳定性）。

#### T3 本地过滤器 + 护栏引擎（`subs/filter-guard`，**sonnet/opus**，依 T1 仅类型）

- **范围**：`subs/filter.py`（title_regex_any/exclude_regex/min_year 对 `PaperStub` 流统一过滤，
  大小写不敏感，命中规则记录进 `ReportEntry.matched_rules`）；`subs/guard.py`（`max_new_per_run`
  熔断判定 + `dedupe_against_library` 复用 storage identifier (scheme,value) 去重 + 过载报告数据：
  计数/按源与分类分布/收窄建议生成）。
- **DoD**：正则命中矩阵 ≥10 用例；熔断边界（=阈值不熔断，>阈值熔断）；去重对库判定走真 sqlite。
- **测试**：unit + integration；AC-6.2 判据的离线载体在此卡先行成立。

#### T4 watermark 增量语义（`subs/watermark`，**opus/opus**，依 T1）

- **范围**：`subs/watermark.py`——per-source 策略（design/09 §5）：arxiv `submittedDate` 上界推进 +
  重叠 1 天窗防 announce 延迟；openalex/s2/crossref `from_*_date` 游标；ssrn/nber id 集合差分
  （最近 N 页 abstract_id/RSS id 集合）。序列化进 `subscription.watermark_json`；**推进纪律：run 成功才
  推进，熔断/失败不推进**（丢失容忍优于重复容忍的反向——宁可重看不可漏看，id 去重兜底重复）。
- **已裁决歧义**：watermark_json 格式 `{source: {cursor|ids|date}}` 带 `schema_ver` 字段留演进缝。
- **DoD**：三类策略（日期上界/游标/集合差分）各自 fixture 时间线推演正确；重叠窗重复由去重兜底验证；
  失败不推进有专测。
- **测试**：unit fixture 时间线；property（推进单调性）。

#### T5 watch runner + CLI（`subs/watch-cli`，**opus/opus**，依 T2+T3+T4）

- **范围**：`subs/watch.py` 编排：编译→per-source 增量拉取（复用各 adapter DISCOVER/ENUMERATE +
  http/ratelimit 既有设施）→本地过滤→guard 判定→入库（metadata；`ingest: metadata+pdf` 时按
  `auto_fetch_limit` 派生 fetch 任务进既有队列）→watermark 推进→`subscription_run` 落记录→
  `RunSummary` 交 T6 渲染。CLI：`crawler watch <name>|--all [--dry-run]`；**dry-run 只报数：不入库、
  不派生任务、不推 watermark、不写 run 记录**（AC-6.2 dry-run 语义）。退出码沿 0/1/2/3 契约。
- **已裁决歧义**：①watch 不引入常驻进程（design/05 已定 cron 单次）；②熔断时 run 记录仍落
  （truncated=1）但零入库；③日报文件落 `docs/reports/watch/`（design/05 字面）且该子目录进
  `.gitignore`（运行产物不入 git 语义，两处设计表述的合并裁决）。
- **DoD**：mock_platform 端到端四场景（正常增量/熔断/dry-run/零新增）全绿；`--all` 多订阅串行合并
  报告；CLI 集成测试走真实 argv。
- **测试**：integration 为主 + CLI 层；runner 分支覆盖 ≥95%。

#### T6 日报渲染（`subs/daily-report`，**sonnet/sonnet**，依 T1 类型，可与 T5 并行）

- **范围**：`subs/report.py`——纯函数 `render_daily(list[RunSummary]) -> str`：多订阅合并一份
  `daily-YYYY-MM-DD.md`（design/09 §6：每订阅新增清单（标题/作者/链接/命中规则）、累计库存、失败与
  熔断事件段）；过载报告渲染（分布 + 收窄建议）同文件实现。T5 只调用不实现渲染。
- **DoD**：golden markdown 三例（正常/含熔断/空日）字符级稳定；中文楷体表头与既有 report.py 风格一致。
- **测试**：golden 快照 + 空输入边界。

#### T7 nber RSS watch 通道转主（`subs/nber-rss`，**sonnet/opus**，依 T2 接缝）

- **范围**：检查单 #3（nber.md §3.5）：program RSS `back.nber.org/rss/new{code}.xml`（19 feed）作为
  watch 增量主通道——RSS 解析（fixture 快照）、`programs:` 选择器→feed 映射、id 集合差分 watermark
  接 T4 策略；`DISCOVER` 既有 crossref 通道保留为 backfill 主干（RSS 只服务增量）。nber.md §3.5 状态
  行同步改主（front matter updated + INDEX）。
- **DoD**：19 feed 映射表全量；RSS fixture 解析回归；watch 场景 nber 源走 RSS 不走 crossref 枚举的
  路由专测。
- **测试**：unit fixture + contract（feed 映射完整性自断言，防 canary 式清单漂移反模式）。

#### T8 预置 topic 包（`subs/presets`，**sonnet/opus**，依 T1 语法 + T2 语义）

- **范围**：`subscriptions/presets/` ×9（design/09 §4 清单：llm-agents、rl-theory、causal-inference、
  econometrics-methods、asset-pricing、market-microstructure、corporate-finance、mechanism-design、
  optimization-ml）；每件头注 precision/recall 取向注释；查询语法用 [research/site-survey/arxiv.md]
  分类全表 + design/09 §2 双示例为范式。
- **DoD**：9 preset 全部过 T1 校验器 + T2 编译 smoke（离线）；领域查询语义经审查 agent 学术常识复核
  （如 asset-pricing 含 q-fin.PR + FEN 网络）。
- **测试**：参数化 smoke（解析+编译零错）。

### 修复批（审计遗留，全部独立、可与主线并行）

#### F1 AC-3.4 merge 顺序无关修复（`fix/merge-order-invariance`，**opus/opus**，零依赖）

- **范围**：审计 P1（S 域）：注入顺序可静默破坏合并收敛（fail-safe 方向）——修 `merge.py` 使字段收敛
  与输入顺序无关；补属性生成器（hypothesis 或手写 permutation property）锁顺序无关性。
  权威台账：post-phase5-audit §3 对应条目。
- **DoD**：隔离脚本复现用例转为回归测试且修复后通过；全量 merge 既有测试零回归。

#### F2 config TOML 错误分类 + 文档滞后三项（`fix/config-toml-docs`，**sonnet/sonnet**，零依赖）

- **范围**：①审计 P1：畸形 TOML 逃逸 CONFIG 错误分类（小改，errors 分类修正）；②audit §5 文档滞后：
  `unpaywall/adapter.py` docstring 修正（OA-fallback 已实现）、`aggregators.md §5.2` 回填 dblp 真实
  `<bht>/<dblpcites>/<r>` 结构、`auth-framework.md §8.3/8.4` 日配额 cap 表述修正（删 VenueSpec.rate_limit
  日上限说法，对齐 `Config.auth_daily_cap` 实况）。文档改动随卡走 INDEX/updated 义务。
- **DoD**：畸形 TOML 用例归入 CONFIG 类退出码 2；三处文档与实现零漂移（审查 agent 对照源码复核）。

#### F3 aaai_ojs 历史卷冷回填修复（`fix/aaai-cold-backfill`，**opus/opus**，零依赖，volume_map 扩容前置）

- **范围**：审计 S1-P1：历史卷冷回填触发全库重扫——按窗口分区/跨卷缓存修复（audit §3 台账 + progress
  待补验 ★F 注记）；修复后 2010–2018 九届扩容裁决材料随卡产出（成本估算），扩容本身**不在本卡**（等
  fable 裁决另行插单）。
- **DoD**：冷回填场景请求数从全库重扫降为增量窗口（专测计数断言）；既有 aaai 测试零回归。

#### F4 静默降级清账（`fix/loud-failures`，**sonnet/opus**，零依赖；**排除** aaai 冷回填项——归 F3）

- **范围**：审计 S1 六项静默降级 + OAI 空信封——统一按「响亮失败优于静默空结果」改造（具体六项以
  post-phase5-audit §3 台账为权威，逐条列出文件:行号后动手）；econsoc 当前年 30 天回看窗完整性缺口
  （audit P2，与 aaai 同构）若属台账内一并修，不属则登记不扩scope。
- **DoD**：六项逐条有失败路径专测（异常/警告可断言）；全量零回归。

#### F6 CF-403 判定演进 + 冷却键粒度修复（`fix/cf403-cooldown`，**opus/opus**，零依赖；**R1 定稿增补卡**，D-030）

- **范围**：R1 详设定稿（[11-browser-fetch §5.4/§5.6](../design/11-browser-fetch.md)，D-030 裁决②③）的两项
  httpx 路径既有缺口修复（不依赖横切件实现，闭合审计处置 #2）：**S-c**——`http.py` 403 分支新增
  `cf-mitigated: challenge` 头判别 → CHALLENGE（特征判别复用 `ChallengeDetector` 单一权威源/只读常量，
  不复制特征串；403 无该头 → NO_ENTITLEMENT 逐字不变）；**E-1**——`runner.py` 冷却判定上移至 family
  判别之前（修复 open_access family 冷却"写而不读"）+ 挑战场景冷却键改域级（向前兼容读旧
  `<adapter_id>.json`）。
- **DoD**：11-browser-fetch §8 T-6（改判三形态 + **全库 fixture 扫描零翻转断言**）与 T-7（open_access
  冷却修复前必失败、修复后 BLOCKED）落地；wiley TDM 403/elsevier 封套行为回归锁定；全量零回归。
- **测试**：unit（http 映射）+ integration（runner 冷却链路走真 sqlite + 冷却 JSON）。

#### F5 测试基建（`fix/test-infra`，**sonnet/sonnet**，零依赖）

- **范围**：审计 S4 两项 + O4-P2：①`test_cli_canary.py` 断言列表补 `aea` + **集合等值自断言**
  （`assert set(listed) == set(registry.all())` 根治"注册了却没验证"三次复现反模式）；
  ②`test_migrations.py` 连接关闭纪律；③canary 周跑自动化载体评估——产出 launchd/cron 模板脚本 +
  文档段（不常驻、不改 CI，本地 cron 方案，写进 canary README 或 testing/）。
- **DoD**：canary 断言 20/20 等值自断言常绿；migrations 测试无 ResourceWarning；周跑模板可手动演练。

### 设计批（opus 起草 / fable 定稿——AGENTS §7 架构决策主 agent 保留）

#### R1 browser-fetch 横切件正式详设（`design/browser-fetch`，**opus 起草/fable 定稿**，零依赖）

- **范围**：检查单 #2 + 审计处置 #2 合批：在 [ssrn.md §11] 设计种子（案 A/B + 评估维度）基础上出
  `docs/design/11-browser-fetch.md` 正式详设——三消费方（ssrn 模式 B / aea pubs CF 全文 / wiley 页面
  兜底域）统一横切件：`ChallengeDetector` 接线、BLOCKED 人工介入流、预算护栏离线逻辑、浏览器上下文取回
  接缝（Playwright 复用 auth/browser.py 先例）；**CF-403 挑战冷却缺口系统性评估并入**（403+`cf-mitigated`
  形态判定属同一 ChallengeDetector/HttpClient 接缝，含 econsoc/wiley/oup 受限面分析）。
- **边界**：本 Phase 交付**详设文档 draft→fable 定稿 approved**；实现不在本 Phase 承诺（AC-5.1b 的
  实现落地随详设批准后另立卡，可能 Phase 6 末 stretch 或 Phase 7）。AC-0.2 红线段必须显式：仅检测
  分类，零求解/绕过。
- **DoD**：五要素齐全（功能/方案/测试/类型/AC 草案）；两案取舍有量化维度表；fable 定稿签署。

#### R2 repec enrich + ssrn 覆盖候补合并评估（`design/enrich-eval`，**opus 起草/fable 定稿**，M1-d 供数）

- **范围**：检查单 #4 + #1 合批评估文档（落 `docs/research/` 或 design 视结论定）：①repec
  `role: aggregator-enrich` 通道（D-027 定位：JEL 独家 + wp↔published 关联服务 D-007；duck-typed
  `enrich_batch`，bulk ReDIF/OAI 零 HTML）——产出"立卡实现 or 再缓"建议 + 若立卡的任务卡草稿；
  ②ssrn 覆盖候补 ladder（a) OpenAlex 补枚举（用 M1-d 抽样数据评估 ENUMERATE 收回与 credit 计费约束）
  (b) RePEc 交叉核对（与①合并考虑）(c) 浏览页 census 降级可选——三路径推荐序 + 量化依据。
- **DoD**：两份评估结论 + 明确 go/no-go 建议交 fable 裁决；引用数据全部 [LIVE]/[DOC] 标注。

### 在线与验收

#### M1 在线闭合批（`chore/p6-online-batch`，**sonnet/opus**，独立随时可插，预算 §3 M1-a~d ≤35）

- **范围**：econsoc [UNRESOLVED①②③④] 闭合回填 econsoc.md/site-survey；aaai A⑥⑦ 重跑（先 HEAD 确认
  `ojs.aaai.org` 恢复，未恢复则记录跳过）；aea `aeri`/`jel` ISSN 核实（跑 `test_aea_smoke.py` 既有断言，
  过则升 [LIVE] 并同步 catalog）；OpenAlex 无-DOI works 抽样（R2-d 供数，结果只入 R2 评估不动代码）。
  每请求记录进 obslog；结果无论成败如实回填文档。
- **DoD**：预算内完成 + 四子批结论落对应文档（[LIVE] 标注 + 核验日期）；超支中止上报。

#### T9 AC-6 离线端到端验收 + 在线冒烟（`feat/ac6-e2e`，**sonnet 执行/fable 亲验**，依 T5+T6+T8）

- **范围**：AC-6 判据正式执行：AC-6.2（熔断零入库+过载报告）/AC-6.4（全本地 vs 下推+补偿结果集相等）
  离线全验；AC-6.1 离线口径 = mock_platform 7 天时间线 fixture 推演（无重复无遗漏+日报生成），在线
  延伸 = 3 preset 单轮真实 watch（预算 §3 T9 行 ≤15）；AC-6.3 口径裁决 = SSRN 无关键词下推场景用
  crossref fixture 语料构造"人工浏览基准"代理集，一致率 ≥95% 离线判定（真人工基准 defer 运行期，
  如实标注）。验收记录落 `testing/records/2026-MM-DD-ac6-acceptance.md`。
- **DoD**：四条 AC 判据逐条 PASS/定口径留痕；fable 亲验签署。

#### T10 收尾（`docs/phase6-wrap`，**sonnet 执行 + opus 全分支终审 + fable 合并裁决**，依全部）

- **范围**：phase6-report（交付清单/事件教训/Phase 7 检查单）；progress/INDEX/模块状态表同步；
  design/09 转 implemented；GLOSSARY 增量（watch/watermark/preset 等）；tag `phase-6`。
- **DoD**：终审七项清单（门禁复现/AC-0 四项/接缝一致性/提交尾行/git 历史/backlog 载体/文档状态联动）
  全 PASS；fable 裁决签署。

## §5 波次并行图与冲突面预算

```
W0（8 卡并行铺开）: T1 ▎F1 F2 F3 F4 F5 ▎R1 R2
W1（T1 合并后滚动补位）: T2 T3 T4 ▎T8(依T1语法,T2语义部分后验) ▎M1(独立,窗口期插入)
W2（T2/T3/T4 合并后）: T5 ▎T6(依T1类型,与T5并行) ▎T7(依T2)
W3（T5+T6+T8 合并后）: T9(fable 亲验)
W4: T10(opus 终审 + fable 裁决 + tag)
```

冲突面预算：主线 T1–T8 全部落在新包 `subs/`、新目录 `subscriptions/` 与 repo.py 追加段——与修复批
F1（merge.py）/F2（config.py+docs）/F3（aaai_ojs/）/F4（分散 adapter 小改）/F5（tests 基建）零文件
交集；F4 与 F3 的 aaai 面已显式切割；R1/R2 纯文档。真正的串行点仅：①repo.py（T1 独占先行）；
②cli.py（T5 独占）；③`.gitignore`（T5 一处）。审查滚动跟进：每卡执行完成→同波审查 agent 复核→
fable 合并；合并顺序按完成序，core 文件后到者 rebase。

## §6 模型分配建议（执行/审查）

| 卡 | 执行 | 审查 | 难度依据 |
|---|---|---|---|
| T1 DSL 地基（冻结件产出） | **opus** | **opus** | 新接口冻结件，下游 6 卡消费 |
| T2 查询编译器 | **opus** | **opus** | 六源能力映射语义密度高 |
| T3 过滤+护栏 | sonnet | **opus** | 规格清晰，护栏语义须严审 |
| T4 watermark | **opus** | **opus** | 增量正确性微妙（重叠窗/不推进纪律） |
| T5 watch runner+CLI | **opus** | **opus** | 编排核心，动 cli.py |
| T6 日报渲染 | sonnet | sonnet | 纯渲染 golden |
| T7 nber RSS | sonnet | **opus** | 接线为主，路由专测须审 |
| T8 presets | sonnet | **opus** | 内容工作，领域语义复核 |
| F1 merge 顺序无关 | **opus** | **opus** | P1 微妙语义 + property 测试 |
| F2 config+docs | sonnet | sonnet | 小改+doc-only |
| F3 aaai 冷回填 | **opus** | **opus** | P1 性能语义 |
| F4 响亮失败清账 | sonnet | **opus** | 分散面广防漏 |
| F5 测试基建 | sonnet | sonnet | 机械加固 |
| R1 browser-fetch 详设 | **opus 起草** | **fable 定稿** | 架构文档（AGENTS §7 保留） |
| R2 enrich/候补评估 | **opus 起草** | **fable 定稿** | 决策建议（同上） |
| M1 在线批 | sonnet | **opus** | 预算纪律执行 |
| T9 AC-6 验收 | sonnet | **fable 亲验** | 验收签署保留 |
| T10 收尾 | sonnet | **opus 终审 + fable 裁决** | Phase 关闭 |

## §7 AC 映射与风险

| AC | 承载卡 | 口径 |
|---|---|---|
| AC-6.1 多 topic 7 天 | T5+T6+T8 → T9 | 离线 7 天 fixture 推演为 DoD 判据；在线单轮冒烟为延伸 |
| AC-6.2 护栏熔断 | T3+T5 → T9 | 全离线 |
| AC-6.3 SSRN 补偿一致率 | T2+T3 → T9 | fixture 代理基准 ≥95% 离线判定；真人工基准 defer 运行期 |
| AC-6.4 下推/本地一致 | T2+T3 → T9 | 全离线，fixture 双路径等集 |

风险：①arxiv 查询语法编译踩官方布尔式边界 → T2 用例表以 site-survey/arxiv.md 实测语法为准，不臆造；
②watch 与既有 pipeline 任务队列的接缝（auto_fetch 派生）耦合面 → T5 只派生任务不改 runner；
③8 卡并行的合并洪峰 → fable 按完成序滚动合并，不攒批；④M1 在线批 aaai 站点未恢复 → 记录跳过不阻塞。

## §8 不建卡项（显式出列，范围锁定 R5）

- 检查单 #7 elsevier key 冒烟（T7b）：外部依赖等用户 key，到位随时插单——**不占波次**。
- 检查单 #8 POM/SODA 正向路由：`sage`/`siam` adapter 未立项，Phase 6 范围外。
- 检查单 #9 aea 全文/机构认证实现：依赖 R1 详设批准后另立，本 Phase 仅设计。
- browser-fetch 横切件**实现**：同上，R1 详设先行。
- design/08 track 探测链（AC-8.x）与 Phase 7 内容（GROBID/向量索引/dedupe review）：范围外。
- aaai 2010–2018 volume_map 扩容执行：F3 修复后另行裁决插单（材料随 F3 产出）。
