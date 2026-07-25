---
title: 主题订阅与精确搜索
status: approved
owner: fable5
updated: 2026-07-26
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
    query: >                   # 编译为 arXiv API search_query 的字段级布尔式
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
| arXiv | 字段前缀 ti/abs/cat/au + 布尔 + submittedDate 窗口（research/site-survey/arxiv.md） | 完整下推 | 少 |
| SSRN | 仅分类浏览（network/eJournal）+ 站内搜索（无稳定 API） | 只下推分类，按日期倒序取增量窗口 | **关键词全在本地过滤** |
| OpenAlex | filter=concepts/ids/type/from_publication_date | 概念+类型+日期下推 | 正则本地 |
| Semantic Scholar | bulk search venue/year/fieldsOfStudy | 同上 | 正则本地 |
| NBER | program 分类 + RSS | 分类下推 | 正则本地 |
| Crossref（期刊 watch） | ISSN + from-pub-date | 完整下推（无关键词场景） | — |

原则：**下推尽可能多以省流量，但正确性以本地过滤为准**（两层过滤结果一致性可测）。

## 4. 预置 Topic 包（catalog 提供、用户可改）

`subscriptions/presets/`：`llm-agents`、`rl-theory`、`causal-inference`、`econometrics-methods`、`asset-pricing`、`market-microstructure`、`corporate-finance`、`mechanism-design`、`optimization-ml`。每个 preset 文件头注释其 precision/recall 取向（宽召回 vs 高精确），供用户改造。

## 5. 增量语义（watermark）

- arXiv：`submittedDate` 上界推进，重叠 1 天窗口防边界丢失（announce 延迟）+ id 去重；
- SSRN：~~最近 N 页 `abstract_id` 集合差分（无可靠时间过滤时的通用法）~~ **D-029 联动修订（2026-07-26）**：ssrn 元数据主路径改经 crossref prefix 枚举后，时间过滤已可靠——增量语义改用 `from-created-date` 游标（[ssrn.md §4.2](adapters/ssrn.md) 权威，P6-T4 审查裁定）；
- OpenAlex/S2/Crossref：`from_*_date` 游标；
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
| 1 | 2026-07-26 | 滞后修正（status 不降，仍 approved）：§2 示例一（llm-agents）补脚注——`title_regex_any` 需含 `sources.*.concepts`/`query` 声明词的全称对应式，防止照抄该示例时复现"query/concept 有词、title 本地过滤无对应式"的死子句缺陷 | T8（`subs/presets`）审查：用真实经典论文标题实测 9 件预置 topic 包，发现同类 P1 级缺陷 7 处并修复；本条为反哺设计文档源头示例 |
