---
title: AC-6 离线端到端验收 + 在线冒烟记录 — 订阅与搜索（Phase 6 T9）
status: draft
owner: t9
updated: 2026-07-26
---

# AC-6 离线端到端验收 + 在线冒烟记录（订阅与搜索，Phase 6 T9）

> 判定依据：[acceptance-criteria.md AC-6.1~6.4](../acceptance-criteria.md)、[design/09-search-filter.md §8](../../design/09-search-filter.md)、[plan/phase6-implementation-plan.md T9 节 + §7](../../plan/phase6-implementation-plan.md)。
> 记录范式：沿 [AC-5 离线端到端汇总验收记录](2026-07-24-ac5-acceptance.md)（逐条判定表 / 证据链 / 亲跑台账 / 分层标注 / 签署）。
> **本记录由 T9 执行 agent（sonnet 档）起草，判定一律"建议 PASS"，不自置签署——最终签署由 controller（fable）亲验完成**（任务卡字面纪律）。
> 代码基线：`feat/ac6-e2e` 分支 @ `main` `5729d50`（Phase 6 T1–T8 主线全部已合并：DSL 地基/编译器/过滤+护栏/watermark/watch runner+CLI/日报渲染/nber RSS/9 preset）。本记录新增 `tests/integration/test_subs_ac6_acceptance.py`（6 例），零改动既有 `src/`。

## 0. 分层与范围

本记录判定分两层：

1. **离线判据**（AC-6.1~6.4 全部四条的 DoD 判据本体）：全部在隔离 worktree 内 `uv run pytest` 实测，零真实网络，可复现。
2. **在线冒烟延伸**（仅 AC-6.1 的附加验证，非 DoD 判据本身——design/09 §8/plan §7 明确 AC-6.1 的离线口径="7 天 fixture 推演"，在线单轮冒烟是**延伸**）：预算 ≤15 请求（plan §3 T9-online 行），谨慎执行，如实记录，**本次在线冒烟额外发现两项已知限制**（§4 详述），不影响离线 DoD 判定。

## 1. AC-6.1~6.4 逐条判定

| AC | 场景（acceptance-criteria.md 原文摘） | 判定 | 承载载体（离线） |
|---|---|---|---|
| AC-6.1 | 3 个预置 topic 连续 7 天：无重复、无遗漏（抽样对照）、日报生成 | **建议 PASS（离线）**；在线冒烟延伸如实记录（§3.5） | `test_subs_ac6_acceptance.py` 3 例（新增）+ `test_subs_watch_e2e.py` 既有回归（列账） |
| AC-6.2 | 构造超 `max_new_per_run` 场景 → 零入库、产出含分布与收窄建议的过载报告 | **建议 PASS（离线）** | `test_subs_ac6_acceptance.py` 1 例（新增，端到端补充）+ `test_subs_guard.py`/`test_subs_report.py`/`test_subs_watch_e2e.py` 既有回归（列账） |
| AC-6.3 | SSRN 订阅本地过滤后清单与人工浏览基准一致率 ≥95% | **建议 PASS（离线代理口径）**；真人工基准 defer 运行期 | `test_subs_ac6_acceptance.py` 1 例（新增） |
| AC-6.4 | 同一 DSL 的"全本地过滤"与"下推+补偿"结果一致 | **建议 PASS（离线）** | `test_subs_ac6_acceptance.py` 1 例（新增） |

---

### AC-6.1 · 多 topic 7 天 — **建议 PASS（离线）**

**场景原文**：3 个预置 topic 连续 7 天：无重复、无遗漏（抽样对照）、日报生成。

**口径裁决**（plan §7）：离线口径 = mock/fixture 7 天时间线 fixture 推演（无重复无遗漏 + 日报生成）为 DoD 判据；在线单轮冒烟为延伸，不改变离线 PASS 判定。

**判据载体（6 条判据最小充分集，T5 审查产出，本次 T9 逐条落地）**：

| 判据 | 载体（新增，`tests/integration/test_subs_ac6_acceptance.py`） | 判据要点 |
|---|---|---|
| 1 骨架 | `test_ac6_1_seven_day_timeline_no_omission_no_duplication_overlap_replay` | `run_watch(now=...)` 逐日注入 2026-07-20..07-26，`_TimelineFetcher` 按 `pub_date` 累积吐语料（crossref 每日 2 篇 + openalex 每日 1 篇，共 21 篇） |
| 2 无遗漏（含单源投毒） | 同上 | 7 日 entries 并集 DOI 集合 == 语料全集（21 篇）；crossref 于 2026-07-23 单源投毒（`CrawlerError` 注入）失败——断言当日水位停住（`watermark_dates[3]==watermark_dates[2]`）、次日（07-24）窗自然变宽把漏收的两篇追回、终态仍无遗漏 |
| 3 无重复 | 同上 | `env.papers()==21`（paper 行数==语料去重基数）；7 日全部 entries 的 `paper_id`/标题均互不重复 |
| 4 重叠窗回放 | 同上 | 常规日（07-22，非投毒相关）断言 crossref 请求 `since` 精确回退 `overlap_days(2)`（`= 前日水位 - 2 天`）；老语料（07-20/21）被二次拉回但对库去重挡住——当日新增清单只有 07-22 两篇，零重复 |
| 5 源组合三场景 | `test_ac6_1_scenario_arxiv_openalex_same_paper_dedup_via_real_llm_agents_preset`（arxiv+openalex 同篇）、`test_ac6_1_scenario_nber_rss_fixture_driven_via_real_corporate_finance_preset`（nber RSS fixture 驱动） | 两例均用**真实** `subscriptions/presets/{llm-agents,corporate-finance}.yaml`（`load_subscription_file` 直读，非改造副本），驱动语料标题均需独立满足该预置真实的 `title_regex_any`/`exclude_regex`/`min_year`（非绕过过滤的合成捷径）；nber 场景回放既有 `06_rss_program_cf_synth.xml` fixture 并验证 3 item 中 2 命中真实词族、1 如实被过滤 |
| 6 日报 | 同上（骨架用例内） | 7 份 `daily-2026-07-2{0..6}.md` 各自生成（文件名逐一断言）；对最后一天二次调用 `run_watch`+`write_daily_report`（水位已推进→零新增）断言**同日重跑覆盖**（`rerun_text != original_text` 且落盘内容 == 重跑渲染内容，非追加/残留） |

**判据 5 之三（crossref 多 issn fan-out）口径说明**：9 个预置文件中**无一声明 `crossref:` 源**（asset-pricing/corporate-finance 用 ssrn+arxiv+nber，其余 6 个用 arxiv/openalex/s2 组合），故该子场景沿用既有 `tests/integration/test_subs_watch_e2e.py::test_batch_dedupe_crossref_two_issns_hitting_the_same_doi`（已走真实 DSL 解析器 `load_subscriptions`/`parse_subscription`，非合成捷径）为载体，本记录不重复造轮子，如实标注该口径差异（不是缺口，是 9 preset 的真实源分布决定的）。

**AC-6.2 判据本身在 T3 卡先行成立的引用**：`test_subs_watch_e2e.py::test_truncation_blocks_ingest_but_still_records_the_run`、`test_truncation_at_exactly_the_limit_does_not_trigger`、`test_dry_run_still_runs_guard_and_reports_truncation`、`test_batch_dedupe_prevents_a_spurious_truncation`（熔断计数不被批内重复污染）——AC-6.2 独立小节详述，此处不重复列。

**亲跑（本记录，2026-07-26）**：
```
uv run pytest tests/integration/test_subs_ac6_acceptance.py::test_ac6_1_seven_day_timeline_no_omission_no_duplication_overlap_replay \
  tests/integration/test_subs_ac6_acceptance.py::test_ac6_1_scenario_arxiv_openalex_same_paper_dedup_via_real_llm_agents_preset \
  tests/integration/test_subs_ac6_acceptance.py::test_ac6_1_scenario_nber_rss_fixture_driven_via_real_corporate_finance_preset -v
=== 3 passed in 0.7s ===
```

---

### AC-6.2 · 护栏熔断 — **建议 PASS（离线）**

**场景原文**：构造超 `max_new_per_run` 场景 → 零入库、产出含分布与收窄建议的过载报告。

**既有承载（列账，T3/T5/T6 已穷尽单测，本记录不重复）**：
- 熔断判定边界：`test_subs_guard.py`（`is_truncated` 等于阈值不熔断/超过熔断）、`test_subs_watch_e2e.py::test_truncation_at_exactly_the_limit_does_not_trigger`。
- 零入库 + 过载报告结构：`test_subs_watch_e2e.py::test_truncation_blocks_ingest_but_still_records_the_run`（`ingested_count==0`/`fetched_count==0`/watermark 不推进）、`test_dry_run_still_runs_guard_and_reports_truncation`。
- 分布与收窄建议文本生成算法：`test_subs_guard.py::test_build_overload_report_counts_and_source_dominant_suggestion` 等 7 例（来源/类目主导、并列打破、零候选兜底）；`test_subs_report.py::test_narrowing_suggestion_names_top_source_and_category` 等 4 例（渲染字符串精确断言）。
- 熔断计数不被批内重复污染：`test_subs_watch_e2e.py::test_batch_dedupe_prevents_a_spurious_truncation`（同一 DOI 经两 ISSN 批内去重后 `new_count` 不再虚高触发熔断）。
- CLI 层：`test_cli_subs_watch.py::test_truncation_exits_3_and_prints_the_overload_brief`（退出码 3 + stdout 熔断简报 + 落盘过载分布段）。

**本记录补充证据（新增，端到端串联）**：`test_subs_ac6_acceptance.py::test_ac6_2_truncation_report_file_contains_actionable_narrowing_suggestion`——真实 `run_watch` 触发熔断（5 篇 > 阈值 3）→ `RunSummary.distribution` → `write_daily_report` 落盘，**断言落盘文件本身**含：
- `"请收窄查询条件后重试"`（熔断段本身的可操作提示）；
- `"收窄建议：优先考虑收窄"` + `"来源 \`crossref\`"` + `"分类 \`cs.AI\`"`（点名具体来源/分类，非空泛套话）；
- `"100.0%"`（具体占比数字，可操作性的量化依据）。

补的是"三段生成算法各自正确"之外的**端到端串联证据**——证明 T3（guard 判定）→T5（distribution 装配）→T6（渲染）→文件落盘四步确实被正确串起来，而非仅在各自孤立单测里成立。

**亲跑**：
```
uv run pytest tests/integration/test_subs_ac6_acceptance.py::test_ac6_2_truncation_report_file_contains_actionable_narrowing_suggestion \
  tests/unit/test_subs_guard.py tests/unit/test_subs_report.py \
  tests/integration/test_subs_watch_e2e.py::test_batch_dedupe_prevents_a_spurious_truncation \
  tests/integration/test_cli_subs_watch.py::test_truncation_exits_3_and_prints_the_overload_brief -v
=== 全部 PASS（详见 §5 台账合并计数）===
```

---

### AC-6.3 · SSRN 无下推补偿 — **建议 PASS（离线代理口径）**

**场景原文**：SSRN 订阅本地过滤后清单与人工浏览基准一致率 ≥95%。

**口径裁决**（任务卡字面 + plan §7）：用 crossref fixture 语料构造"人工浏览基准"**代理集**（非真人工标注）——语料含 econ/fin 与非 econ/fin 混合，本地过滤（`ssrn.topic_filter`）后清单与代理基准比对，一致率 ≥95% 判定；**真人工基准 defer 运行期**，如实标注（非本记录判定范围）。

**载体**：`test_subs_ac6_acceptance.py::test_ac6_3_ssrn_local_filter_matches_proxy_human_baseline_at_least_95_percent`。

**构造要点（避免"自比恒 100%"重言式——post-phase5-audit 对 AC-5.1a 原判据的废止理由）**：
- 30 条 crossref 形态语料：`proxy_human_econ_fin`（本测试独立赋予的代理标签，模拟"人工浏览会怎么判"）与驱动 `ssrn.topic_filter` 的 `stub.meta['openalex_field']` 信号是**两条独立赋值的数据列**——19 条二者天然一致（10 条 `Economics, Econometrics and Finance` + 9 条 `Business, Management and Accounting`，均判 econ/fin；10 条非 econ/fin 字段（Computer Science/Physics and Astronomy/Medicine），均判非 econ/fin）；**刻意构造 1 例分歧**（OpenAlex 粗粒度顶层分类把一篇人类会认作 econ/fin 的交叉学科论文归到 `Decision Sciences`，不在 `ECON_FIN_FIELDS` 内——自动化谓词判 False，代理人工基准判 True）。
- 全链路走真实 DSL→compile 接线：`parse_subscription`（订阅仅声明 `sources.ssrn.networks`，**不声明 `filters:`**——对应"无关键词下推场景"字面）→ `compile_subscription`（venue 携 `quirks.topic_filter=econ_fin`，逐字对齐 `venues/econ/ssrn.yaml`）→ 断言 `PlanStep.local_predicates` 确实携带 `ssrn.topic_filter`（DSL→编译接线证据，非绕过编译直调 `filter_papers`）→ `filter_papers(stubs, subscription.filters, extra_predicates=scoped)`。
- 一致率 = 29/30 ≈ **96.7%** ≥ 95%（`rate >= 0.95` 且 `rate < 1.0` 双断言——后者证明非重言式，确有分歧被如实计入分母）。

**亲跑**：
```
uv run pytest tests/integration/test_subs_ac6_acceptance.py::test_ac6_3_ssrn_local_filter_matches_proxy_human_baseline_at_least_95_percent -v
=== 1 passed in <0.1s ===
```

---

### AC-6.4 · 下推/本地一致 — **建议 PASS（离线）**

**场景原文**：同一 DSL 的"全本地过滤"与"下推+补偿"结果一致。

**载体**：`test_subs_ac6_acceptance.py::test_ac6_4_full_local_filter_equals_pushdown_plus_compensation_result_set`。

**构造要点（两条路径用不同输入语料子集构造，非对同一子集调用同一函数两遍的平凡重言）**：
- 6 条 crossref 形态语料，逐条覆盖一个应剔除的独立理由：①②目标刊+命中+年份达标（应收锚点）；③目标刊+标题不命中（`title_regex_any` 挡）；④目标刊+命中但年份不达标（`min_year` 挡）；⑤目标刊+命中 `exclude_regex`（"survey"挡）；⑥**非目标刊**+内容完美命中（issn 挡——两路径分岔的关键锚点）。
- **"下推+补偿"路径**：模拟源端已按 `issn` 完成下推（语料预先按 `declared_issns` 缩小，即"fetcher 只会吐目标刊语料"）→ 再跑 `filter_papers`（+ 该源 scoped 谓词，crossref 本场景为空）。
- **"全量本地过滤"路径**：假设该源无 issn 下推能力，全部 6 条语料原样喂给 `filter_papers` → 本地额外补一道"若只能本地判会怎么写"的 issn 成员检查。
- **按结果集（`stub.identifiers` 集合）判定，不比 `matched_rules` 标签集**（T3 审查 P2#6 提醒的判定口径——两路径下同一条幸存记录携带的命中规则标签可能因"issn 检查在哪一层完成"而不同，这只是标签命名空间的分岔，不代表结果不一致）。
- 两路径均收敛到 `{①,②}`（非空判据，防两边恒空的假阳性等集）。

**亲跑**：
```
uv run pytest tests/integration/test_subs_ac6_acceptance.py::test_ac6_4_full_local_filter_equals_pushdown_plus_compensation_result_set -v
=== 1 passed in <0.1s ===
```

## 2. 新增测试文件与既有回归的关系

`tests/integration/test_subs_ac6_acceptance.py`（本记录新增，6 例）**不重复**已有 T3/T5/T6 单测覆盖的算法正确性——只补 T9 任务卡明确要求、既有测试尚未覆盖的判据切面（7 天时间线骨架、真实 preset 驱动的组合场景、端到端熔断-建议串联、AC-6.3/6.4 两条一致性/代理口径的判据本体）。既有回归零改动、零回归（见 §5 台账）。

## 3. 在线冒烟延伸（AC-6.1，预算 ≤15 请求）

### 3.1 环境准备

隔离临时 `--home`（scratchpad，非仓库路径）：`config.toml` 仅声明 `[identity] email = "yhyfhgs@gmail.com"`（D-014 UA mailto 段，`paths.venues_dirs` 走缺省探测——从仓库根 CWD 运行时自动探测到真实 `venues/` 目录，与生产环境同路径）；`subscriptions/` 目录内放**真实**`subscriptions/presets/{llm-agents,asset-pricing,econometrics-methods}.yaml` 的原样拷贝（未改造）。

### 3.2 台账（逐请求记录）

| # | 动作 | 目标 | 结果 | 备注 |
|---|---|---|---|---|
| 1 | `crawler subs watch llm-agents --dry-run --verbose` | `oaipmh.arxiv.org`（DISCOVER，`from=1998-01-01&until=1998-01-31`） | HTTP 200，OAI-PMH 协议层 `badArgument`："start date too early" | arxiv 源失败；openalex 源同批失败但**零网络**（`capabilities=Capability(0)`，`AdapterBase` 默认能力检查在 Python 层直接拒绝，未发出请求——经 obslog 逐条核对，本次仅 1 条 `http exchange` 记录） |
| 2 | 单次 count-only 探测（`rows=0`，非 `crawler` CLI 发出，本记录执行者用同款 D-014 UA 手动核实规模） | `api.crossref.org/works?filter=prefix:10.2139,from-created-date:2026-01-01,until-created-date:2026-12-31&rows=0` | HTTP 200，`total-results: 155461` | 用于**在实跑 asset-pricing 之前**量化 ssrn 源的真实请求规模风险（§4.2），而非盲目实跑后才发现超支 |
| 3 | `crawler subs watch econometrics-methods --dry-run --verbose` | `oaipmh.arxiv.org`（同上，同一 `from=1998-01-01&until=1998-01-31` 请求） | HTTP 200，同 #1 的 `badArgument` | arxiv 源失败；openalex/s2 两源同批失败，均**零网络**（二者 `capabilities` 皆空集，同 #1 openalex 机理） |

**本次共发出 2 条 `crawler subs watch` 驱动的真实请求（obslog `logs/crawler-*.jsonl` 逐条核对，`msg: "http exchange"` 恰 2 条，均 host=`oaipmh.arxiv.org`）+ 1 条本记录执行者手动的规模核实探测 = 3 条计入预算的真实网络动作，远低于 ≤15 预算上限**。

**asset-pricing.yaml 未实跑 dry-run**（见 §4.2 说明；这是基于 #2 探测证据的主动止损决策，不是"忘记跑"或"网络不可用"）。

### 3.3 判定

llm-agents 与 econometrics-methods 两个已实跑的 preset，dry-run 净候选数均为 **0**（两者的 arxiv 源在真实网络下确定性失败——非偶发，`from=1998-01-01` 是硬编码起点、`badArgument` 是 arXiv 官方 OAI-PMH 服务端的确定性拒绝，见 §4.1）。"若 dry-run 计数合理（<200）再真跑其中 1 个最小者"这条件在数值上成立（0<200），但**语义上退化**——两个源结构性均产不出候选，"真跑"不会比 dry-run 多产出任何信息（无候选可入库，watermark 不会推进，见 watch.py 编排：仅 `succeeded_sources>0` 且非熔断才写入）。故本记录**未额外执行"真跑"**，如实记录该决策依据而非虚构一次形式上的"真跑"来凑数。

### 3.4 未消耗预算

3/15（另有 2 条本记录执行者用于确认沙箱出网连通性的探测性请求，命中 `api.crossref.org`/`api.openalex.org` 200、`export.arxiv.org` 一次超时+一次 429——均在真正执行 `crawler` 命令之前完成，用途是判断"网络是否可用"本身，不计入 AC-6.1 在线冒烟延伸的预算行，但为审计完整性一并如实记录于此）。

### 3.5 意外发现（如实上报，非本记录判定范围但影响生产可用性）

见 §4"已知限制"两项——均由本次在线冒烟**实证**（而非猜测）发现，已用 `spawn_task` 登记 arxiv 一项为独立后续任务（见 §6）。

## 4. 已知限制（如实列，不阻塞本记录 AC-6 离线 DoD 判定）

1. **`crawler subs watch` 的 arxiv 源在真实网络下当前不可用**（本次在线冒烟新证据）：`subs/watch.py::_lower_bound_of` 对 arxiv 恒返回 `None`（其窗口并入 `search_query` 字符串，非独立 `since` 参数——这是该模块 docstring"参数下达面"段已预先示警的已知设计现状），导致 `AdapterFetcher.fetch()` 调用 `arxiv 适配器.discover_timeline(venue, since=None)` 时，该适配器对 `since=None` 的默认行为是从硬编码起点 `1998-01-01` 按月桶枚举——本次实测该起点被 arXiv 官方 OAI-PMH 服务端以 `badArgument`/"start date too early" **确定性拒绝**（非限速、非偶发，两次独立调用逐字返回同一错误）。净效果：**任何声明了 `sources.arxiv` 的订阅，在真实网络下 `subs watch` 当前恒失败、零候选**——9 个预置里唯独 `market-microstructure`/`mechanism-design` 之外的绝大多数 preset 均含 arxiv 源，此为影响面较广的生产阻断项。**已通过 `spawn_task` 登记为独立后续任务**（见 §6），本记录不代为修复（超出 T9 验收范围）。
2. **asset-pricing.yaml 的 ssrn 源年粒度桶会触发对 crossref 前缀 10.2139 整年的枚举**（本次在线冒烟量化确认，非新发现——`subs/watch.py` 模块 docstring"参数下达面"段已预先示警"crossref 走 identifiers 下达、日期窗客户端收窄（请求量或超预期）"，本次冒烟**实测量化**了该风险的具体规模）：`SsrnAdapter.discover_timeline` 按**年**切桶（`_resolve_start_year` 只取 `since` 前 4 位），而非把 7 日 watch 增量窗传导到日粒度——本次单次 `rows=0` 探测实测 `prefix:10.2139` 在 `created` 轴 2026 全年已有 **155,461** 条 crossref 记录，意味着若真实执行 `crawler subs watch asset-pricing`，其 ssrn 源的 `enumerate_issue`（委托 `CrossrefAdapter` 分页枚举该整年）将产生远超预算的请求量（数十至数千页，视翻页大小而定）。**本记录出于预算纪律（≤15）主动放弃对 asset-pricing.yaml 的真实 dry-run 执行**，以 1 次安全的 count-only 探测量化风险后止损，而非盲目实跑到超支或网络挑战才停手——这正是任务卡"dry-run 先行/谨慎执行/超预算即停"纪律的字面落实。该发现与既有 `subs/watch.py` docstring 已记录的风险同源，本记录不重复登记独立后续任务，仅在此如实标注量化证据。
3. **NBER 源本次未做真实网络验证**（asset-pricing.yaml 唯一同时含 ssrn 风险的 preset，因 #2 原因整体未执行；其余两个已测 preset 不含 nber 源）——`NberRssFetcher` 走独立、有界的单次 RSS 请求路径（不经 `AdapterFetcher`/`DISCOVER`），T7 阶段已有 `newap.xml`/`newcf.xml` 等 [LIVE] 实测记录（`docs/catalog/preprint-platforms.md` §4、`adapters/nber/rss.py` 模块 docstring），本记录不重复验证，如实标注"本次会话未覆盖"而非默认其在 `subs watch` 编排下必然工作。
4. **AC-6.3 真人工基准 defer**：本记录判定使用的是独立赋值的代理标签（§AC-6.3 小节已述构造方法），非真实人工浏览标注；真人工基准验证 defer 至运行期实测，如实标注，不预支结论。
5. **crossref 多 issn fan-out 场景无真实 preset 承载**：9 个预置文件均未声明 `crossref:` 源（§AC-6.1 已述），该子场景沿用既有 e2e 回归而非本记录新造，是 9 preset 真实源分布决定的口径差异，不是覆盖缺口。

## 5. 亲跑台账（本 worktree `feat/ac6-e2e` @ `main` `5729d50`，`uv sync --extra auth` 后 `uv run pytest`，除 §3 明确列出的在线冒烟外零真实网络）

| 载体 | 计数 | 承载 AC |
|---|---|---|
| `test_subs_ac6_acceptance.py`（本记录新增，全部） | **6 passed** | AC-6.1（3 例）/ AC-6.2（1 例）/ AC-6.3（1 例）/ AC-6.4（1 例） |
| `test_subs_watch_e2e.py`（既有，全套件） | **42 passed**（四场景+批内去重+nber RSS+失败处置等，见 T5 DoD） | AC-6.1/6.2 通用 watch 编排 DoD 补证 |
| `test_subs_guard.py`（既有，全套件） | **16 passed** | AC-6.2 护栏判定+过载报告数据结构补证 |
| `test_subs_report.py`（既有，全套件） | **37 passed** | AC-6.2 收窄建议渲染字符串补证 |
| `test_cli_subs_watch.py`（既有，全套件） | **16 passed** | AC-6.2 CLI 层熔断简报补证 |
| **全量门禁 `make check`**（`sync-dev` + `ruff check` + `ruff format --check` + `mypy src` + `pytest tests/unit tests/contract tests/integration --cov=paper_crawler --cov-fail-under=80`） | **3804 passed, 28 skipped**（44.95s）；ruff `All checks passed!`；`ruff format` 322 files already formatted；mypy `Success: no issues found in 117 source files`；coverage **99.00%**（门槛 80%）；**EXIT=0** | 全局回归——较本记录执行前基线（**3798 passed / 28 skipped / 99.00%**，与主线 main 门禁记忆一致）**只增不减**：+6（本记录新增测试），skipped/coverage 均不变 |

## 6. 偏离与上报

- **偏离**：任务卡要求"3 个 preset（llm-agents/asset-pricing/econometrics-methods）各一轮真实 dry-run"，本记录只完整实跑了 2 个（llm-agents/econometrics-methods），**asset-pricing 基于量化风险证据（§4.2，155,461 条 crossref 记录）主动跳过实跑**，改以 1 次安全的 count-only 探测替代。此偏离是任务卡"谨慎执行/超预算即停"纪律的主动落实，不是遗漏——如实上报供 controller 复核是否需要另行安排（如临时提高 ssrn 场景的预算专项，或先修复 F 类问题①②后再补跑）。
- **上报**：已用 `spawn_task` 登记"`crawler subs watch` 的 arxiv 源在真实网络下恒失败"为独立后续任务（Fix ID 见任务面板；prompt 已附本记录 §4.1 的完整技术细节与复现步骤，供后续会话直接定位修复）。ssrn 年粒度枚举风险（§4.2）与既有 docstring 已记录风险同源，未另开新任务，仅在此登记量化证据供 controller 决定是否需要优先级提升。
- 其余：无。

## 7. 移交

- controller 亲验：复跑本记录 §5 亲跑台账（尤其 `test_subs_ac6_acceptance.py` 6 例 + `make check` 3804/28/99.00%/EXIT=0）核对吻合；复核 §3 在线台账（`logs/crawler-*.jsonl` 若需要可提供完整会话副本）与 §4 已知限制两项的技术判断（尤其 arxiv 发现是否需要提升为 Phase 6 范围内插单修复，而非仅 backlog 登记）。
- §4 已知限制清单转交后续处置：① arxiv watch 集成问题（已 spawn_task）；② ssrn 年粒度枚举风险（如实登记，未开新任务）；③ nber 本次未验（低风险，T7 已有 [LIVE] 证据，建议后续会话顺带补一次 asset-pricing 的 nber-only 隔离验证）。
- T10 收尾时按本记录 §1 四条"建议 PASS"逐条复核，phase6-report 汇总时一并登记本记录的两项在线发现。

## 8. 签署

- **T9 初判（2026-07-26）**：AC-6.1/6.2/6.3/6.4 离线判据本次在隔离 worktree 内实跑全部 PASS（§1 逐条 + §5 台账，6 新增 + 既有回归零回归）；在线冒烟延伸如实执行 2/3 preset + 1 次风险量化探测（§3），发现两项已知限制（§4）并已就其中较严重者（arxiv）登记独立后续任务。**判定：建议 PASS，待 controller（fable）亲验**（不自置 approved/签署）。
- **待办**：controller 亲验载体计数复现 + `docs/testing/acceptance-criteria.md` AC-6 节核对（本次未改动该文件，纯执行留痕）+ §4 已知限制两项的优先级裁决 + §6 偏离项确认后，方可转 `status: approved`。
