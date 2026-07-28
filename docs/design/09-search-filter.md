---
title: 主题订阅与精确搜索
status: implemented
owner: fable5
updated: 2026-07-29
---

# 09 · 主题订阅与精确搜索（Topic/Tag DSL）

> 需求：FR-15/16——预印本平台自定义 Topic/Tag 精确订阅，覆盖 CS/AI、Econ、Fin 不遗漏，同时防止内容过载。

## 1. 功能说明

- 用户以声明式 `Subscription` 定义"我关心什么"；
- 系统把它编译到各源的原生查询能力（arXiv 查询语法、SSRN 分类浏览、OpenAlex/S2 过滤器），源不支持的条件在本地二次过滤；
- watch 运行产出：新论文入库（metadata 级）+ 可选自动下载 + 日报。

## 2. Subscription 定义（YAML，存 `subscriptions/`）

```yaml
# subscriptions/llm-agents.yaml —— 示例
name: llm-agents
sources:                       # 只列想要的源，各源有专属段
  arxiv:
    categories: [cs.AI, cs.LG, cs.CL, cs.MA]     # 官方分类（见 research/site-survey/arxiv.md 全表）
    query: >                   # 编译为本地补偿谓词 arxiv.query_bool 的字段级布尔式（Phase 7 T9）
      (ti:"agent" OR abs:"agentic" OR abs:"tool use")
      AND NOT ti:"survey"
  openalex:                    # 聚合源兜底（收 arXiv 外的 OA 预印本）
    concepts: ["large language model"]
    from_source_types: [preprint]
filters:                       # 本地二次过滤（对所有源结果统一执行）
  title_regex_any: ["\\bagent(s|ic)?\\b", "LLM"]
  exclude_regex: ["quantum"]
  min_year: 2024
actions:
  ingest: metadata             # metadata | metadata+pdf
  auto_fetch_limit: 20         # 每次运行最多自动下载篇数
guard:                         # 护栏（FR-16）
  max_new_per_run: 200         # 超过即熔断：只出报告不入库，提示收窄查询
  dedupe_against_library: true
schedule_hint: daily
```

> **脚注（2026-07-26 补，见修订记录 #1）**：`title_regex_any` 应至少有一条能
> 匹配 `sources.*.concepts`/`query` 里声明的概念**全称**——本例
> `openalex.concepts: ["large language model"]` 与 `query` 的 `tool use`
> 分支，若 `title_regex_any` 只有 `\bagent(s|ic)?\b`/`LLM` 两条缩写式，会把
> 标题直接写全称"Large Language Model"（不含"agent"或"LLM"缩写）或只提
> "tool"不提"agent"的论文漏判为不命中。照抄本示例产出订阅/preset 时请一并
> 检查这条对应关系；`subscriptions/presets/llm-agents.yaml`（T8）已按此修复，
> 并以真实论文标题（如 *Large Language Models are Zero-Shot Reasoners*）
> 建了回归测试（`tests/unit/test_subs_presets.py`）。

```yaml
# subscriptions/asset-pricing-wp.yaml —— 金融示例
name: asset-pricing-wp
sources:
  ssrn:
    networks: [FEN]                    # SSRN 子网（FEN=Financial Economics Network）
    ejournals: ["Asset Pricing eJournal", "Capital Markets eJournal"]  # ⚠ 名称实现期核验
  arxiv:
    categories: [q-fin.PR, q-fin.PM, q-fin.ST]
  nber: {programs: [AP]}               # NBER Asset Pricing program
filters:
  title_regex_any: ["asset pricing", "cross-section", "risk premi"]
actions: {ingest: metadata, auto_fetch_limit: 10}
guard: {max_new_per_run: 100}
```

## 3. 查询编译（每源的能力映射）

| 源 | 原生能力（勘察依据） | 编译策略 | 本地补偿 |
|---|---|---|---|
| arXiv | 字段前缀 ti/abs/cat/au + 布尔 + submittedDate 窗口（research/site-survey/arxiv.md）；但 watch 通道是 OAI-PMH，**无关键词查询能力** | `categories` → `arxiv_category` **逐分类 fan-out**（每条请求成对带派生的 `arxiv_set`，经 venue quirks 进 OAI `set=` + 客户端 primary_category 过滤）；`query` **无下推通道** | `filters` 三谓词 + **`arxiv.query_bool`**（Phase 7 T9 落地的参数化本地补偿谓词，见修订记录 #4）：`query` 字段级布尔式（ti/abs 前缀 + AND/OR/ANDNOT + 引号短语）经 `subs/compile.py::_compile_arxiv` 归一、`subs/types.py::parse_arxiv_query` 解析出语法树、`subs/filter.py::PREDICATE_REGISTRY` 的构造器产生求值闭包，挂 `PlanStep.predicate_params`（非免参谓词通道），在真实 `subs watch` 运行中对标题/摘要实际求值——**不再是**"手工镜像约定"（本行原表述），是机制 |
| SSRN | 仅分类浏览（network/eJournal）+ 站内搜索（无稳定 API） | 只下推分类，按日期倒序取增量窗口 | **关键词全在本地过滤** |
| OpenAlex / Semantic Scholar | **不可作 watch 源**——`capabilities` 恒为空集，无 `DISCOVER`/`ENUMERATE`（二者是 enrich-only 补充源，design/adapters/aggregators.md §1）。**如实订正（2026-07-29）**：本行原写"filter=concepts/ids/type/from_publication_date"/"bulk search venue/year/fieldsOfStudy"式下推，那是设计期的愿望；2026-07-28 审计修复批 R2b 核实后收窄为实况——watch 通道从未能真正驱动这两源 | 不适用——`subs/model.py::SOURCE_FIELDS`（"watch 真的跑得动的源"白名单）不含 openalex/s2；订阅文件 `sources:` 段声明 `openalex:`/`s2:` 会触发 `ENRICH_ONLY_SOURCES` 专属校验消息（"这个源不支持 watch，请改用 enrich"，区别于泛化的"未知源"报错，R2b/P0-4）；`crawler venues lint` 新增 `registry.py::_lint_capabilities` 同批校验 58 个 venue（R2b 当时；现 62 个）的 `metadata_source`/`fulltext_source` 能力位（须含 `DISCOVER\|ENUMERATE`/`RESOLVE`），零错配 | 不适用——元数据/摘要补充改走 `crawler enrich --source openalex\|s2`（批量补充，非订阅增量 watch），见 design/adapters/aggregators.md |
| NBER | program 分类 + RSS | 分类下推 | 正则本地 |
| Crossref（期刊 watch） | ISSN + from-pub-date | 完整下推（无关键词场景） | — |

原则：**下推尽可能多以省流量，但正确性以本地过滤为准**（两层过滤结果一致性可测）。

## 4. 预置 Topic 包（catalog 提供、用户可改）

`subscriptions/presets/`：`llm-agents`、`rl-theory`、`causal-inference`、`econometrics-methods`、`asset-pricing`、`market-microstructure`、`corporate-finance`、`mechanism-design`、`optimization-ml`。每个 preset 文件头注释其 precision/recall 取向（宽召回 vs 高精确），供用户改造。

## 5. 增量语义（watermark）

- arXiv：`submittedDate` 上界推进，重叠 1 天窗口防边界丢失（announce 延迟）+ id 去重；
- SSRN：~~最近 N 页 `abstract_id` 集合差分（无可靠时间过滤时的通用法）~~ **D-029 联动修订（2026-07-26）**：ssrn 元数据主路径改经 crossref prefix 枚举后，时间过滤已可靠——增量语义改用 `from-created-date` 游标（[ssrn.md §4.2](adapters/ssrn.md) 权威，P6-T4 审查裁定）；
- OpenAlex/S2/Crossref：`from_*_date` 游标；
- **NBER（P6-T10 补记，2026-07-26）**：program RSS（`back.nber.org/rss/new{code}.xml`）无日期轴可下推，SSRN 让出的"最近 N 个 id 集合差分"通用法改由 NBER 承接——`IdSetDiff`（[nber.md §3.4](adapters/nber.md) 权威规格，`subs/watermark.py` 实现），截断只砍最旧、保留上限防 `watermark_json` 无限膨胀。**口径收窄**：本项目当前只映射 19 个官方 program 中的 5 个（`AP`/`CF`/`EFG`/`IFM`/`ME`，逐条 `[LIVE]` 实证）；`PE` 因 Public/Political Economy 两义未核验被明确排除，其余 14 个官方 program 无码不猜——**扩展前须先补勘察证据（含 PE 语义核验）**，不得凭猜测扩表；
- 全源统一：入库前对 (scheme,value) 去重 → "无重复"由 identifier 主键保证（design/06）。

## 6. 护栏与报告（防过载）

1. `max_new_per_run` 熔断：超限 → 本次不入库，产出"过载报告"（计数、按分类分布、建议收窄的维度）；
2. `crawler watch --dry-run <name>`：只报数不动库——**新订阅上线前必跑**（文档规定的操作规范）；
3. 日报（markdown）：每订阅新增清单（标题/作者/链接/命中的过滤规则）、累计库存、失败与熔断事件；多订阅合并一份 `daily-YYYY-MM-DD.md`；
4. 噪声反馈回路（Phase 7 可选）：报告中的条目可标 `irrelevant`，累计生成 exclude 建议。

## 7. 与 Google Scholar 的边界

不自动化（调研确认：无 API、ToS 禁止、封锁激进+法律风险——research/site-survey/aggregators-unpaywall-dblp-core.md）。文档建议用户：Scholar Alerts 邮件自行订阅，与本系统的 `grab --doi` 单篇精取配合使用。

## 8. 测试与验收

- **单元**：DSL 解析与校验（非法 YAML、未知源、guard 缺省）；各源查询编译器（DSL→URL 参数的用例表）；本地过滤器（正则命中矩阵）。
- **一致性测试**：同一 DSL 对 fixture 数据集"全量本地过滤"与"下推+补偿过滤"结果一致。
- **验收**（AC-6.x 摘录）：
  - AC-6.1 3 个预置 topic 连续 7 天 watch：无重复、无遗漏（与源头 listing 抽样对照）、日报生成；
  - AC-6.2 人为构造超限场景：正确熔断、零入库、过载报告含分布与建议；
  - AC-6.3 SSRN 订阅在无关键词下推能力下，本地过滤后的清单与人工浏览基准一致率 ≥95%。

## 修订记录

| # | 日期 | 修订 | 依据 |
|---|---|---|---|
| 5 | 2026-07-29 | **纯记账（非设计变更），消除文档漂移**：①§3 arXiv 行"本地补偿"栏回填 Phase 7 T9 已落地的 `arxiv.query_bool` 参数化谓词机制（此前本栏仍写"手工镜像约定，不是机制"，T9 早已使其成为机制，文档未同步）；②§3 OpenAlex/Semantic Scholar 两行订正为"不可作 watch 源"（`capabilities` 空集、无 DISCOVER/ENUMERATE），原"filter=... 下推"式描述从未在 watch 通道可达，2026-07-28 审计修复批 R2b 已把 `subs/model.py::SOURCE_FIELDS` 收窄至可达四源并加 `ENRICH_ONLY_SOURCES` 专属校验 + `registry.py::_lint_capabilities` 能力位 lint | 源码核实（`subs/filter.py`/`subs/compile.py`/`subs/model.py`/`registry.py`）+ 2026-07-28 审计修复批 R2（`fix(cli,subs,pipeline,auth)` 提交，P0-4/P1-12） |
| 1 | 2026-07-26 | 滞后修正（status 不降，仍 approved）：§2 示例一（llm-agents）补脚注——`title_regex_any` 需含 `sources.*.concepts`/`query` 声明词的全称对应式，防止照抄该示例时复现"query/concept 有词、title 本地过滤无对应式"的死子句缺陷 | T8（`subs/presets`）审查：用真实经典论文标题实测 9 件预置 topic 包，发现同类 P1 级缺陷 7 处并修复；本条为反哺设计文档源头示例 |
| 2 | 2026-07-26 | **文档转正**：front matter `status: approved`→`implemented`——T1–T8 主线全部合并（DSL 地基/查询编译器/本地过滤+护栏/watermark 三策略/watch runner+CLI/日报渲染/nber RSS watch 转主/9 preset）；AC-6.1~6.4 离线 DoD 判据 T9 全部建议 PASS、fable 亲验签署"达成"（[2026-07-26-ac6-acceptance.md](../testing/records/2026-07-26-ac6-acceptance.md)） | Phase 6 T10 收尾（[phase6-report](../reports/2026-07-26-phase6-report.md)） |
| 3 | 2026-07-26 | **§5 补 NBER 增量语义条目**（此前只有 arXiv/SSRN/OpenAlex-S2-Crossref 三条，NBER 缺席）：`IdSetDiff`（id 集合差分）权威归属由 SSRN（D-029 后已改 `DateCursor`）移交 NBER；一并登记口径收窄——19 官方 program 仅 5 个 `[LIVE]` 映射、`PE` 两义未核验排除、扩展前须先补勘察证据 | Phase 6 终审附条件：`subs/watermark.py:425` docstring 引用的"design/09 §5 第二条"实指已删除线的 SSRN 旧文，本条补齐 NBER 权威归属并订正该 docstring 引用 |
| 4 | 2026-07-26 | **§3 能力映射表 arXiv 行改判如实两栏**：编译策略由"完整下推"改为"`categories` → `arxiv_category` 逐分类 fan-out（每条请求成对带派生的 `arxiv_set`，经 venue quirks 进 OAI `set=`）＋ `query` 无下推通道"；本地补偿由"少"改为"仅 `filters` 三谓词——`query` 词族靠 `title_regex_any` 手工镜像这条**约定**兜底、非机制" | 改动原因见 [AC-6 验收记录](../testing/records/2026-07-26-ac6-acceptance.md) §4 第 6 条及其修复追记：watch 通道是 OAI-PMH（无关键词查询能力），原表"完整下推"对 arXiv 不成立；fan-out 半边已由 `fix/arxiv-category-fanout` 闭合，谓词半边仍留（[phase6-report](../reports/2026-07-26-phase6-report.md) §6 检查单 #4） |
