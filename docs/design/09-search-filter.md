---
title: 主题订阅与精确搜索
status: approved
owner: fable5
updated: 2026-07-20
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
- SSRN：最近 N 页 `abstract_id` 集合差分（无可靠时间过滤时的通用法）；
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
