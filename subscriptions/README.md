# `subscriptions/` —— 主题订阅声明

用户的订阅文件放在**本目录顶层**，一个订阅一个 YAML：`subscriptions/<name>.yaml`
（文件名 stem 必须等于文件里的 `name`，如 `llm-agents.yaml` ↔ `name: llm-agents`）。

权威规格：[docs/design/09-search-filter.md §2](../docs/design/09-search-filter.md)。
解析与校验实现：`src/paper_crawler/subs/model.py`（DSL 变更以设计文档为准，不以本
README 为准——这里只是操作说明）。

## 最小示例

```yaml
name: llm-agents
sources:                       # 只列想要的源，各源有专属段
  arxiv:
    categories: [cs.AI, cs.LG, cs.CL, cs.MA]
    query: >
      (ti:"agent" OR abs:"agentic") AND NOT ti:"survey"
filters:                       # 本地二次过滤（对所有源结果统一执行）
  title_regex_any: ["\\bagent(s|ic)?\\b", "LLM"]
  exclude_regex: ["quantum"]
  min_year: 2024
actions:
  ingest: metadata             # metadata | metadata+pdf
  auto_fetch_limit: 20
guard:
  max_new_per_run: 200         # 缺省 200；超过即熔断（只出报告不入库）
  dedupe_against_library: true # 缺省 true
schedule_hint: daily           # 仅记录，不调度（定时交给 cron/launchd）
```

各源可用字段（design/09 §3 能力映射表）：

| 源 | 字段 |
|---|---|
| `arxiv` | `categories`、`query` |
| `ssrn` | `networks`、`ejournals` |
| `openalex` | `concepts`、`from_source_types` |
| `s2` | `venues`、`fields_of_study`、`query` |
| `nber` | `programs` |
| `crossref` | `issns` |

增量的时间窗**不写在 DSL 里**——由 watermark 自动推进（design/09 §5）。

## 校验是"响亮"的

未知的源、未知的字段、写不通的正则、`max_new_per_run: 0` 这类取值，一律**报错拒载**
而不是忽略：一个拼错的 `catgories:` 若被静默丢掉，你会收到一份看起来正常、实际少了
半个领域的日报。改完订阅先跑一次干跑确认：

```
crawler watch <name> --dry-run     # 只报数，不入库、不下载、不推进 watermark
```

（`crawler watch` 的订阅模式由 Phase 6 T5 交付；在此之前本目录只被 `subs` 模块读取。）

## `presets/`（后续到位）

`subscriptions/presets/` 将放 design/09 §4 的 9 个预置 topic 包（`llm-agents`、
`rl-theory`、`causal-inference`、`econometrics-methods`、`asset-pricing`、
`market-microstructure`、`corporate-finance`、`mechanism-design`、`optimization-ml`），
每件头部注明其 precision/recall 取向。

**preset 是模板，不是活订阅**：加载器只扫本目录**顶层**的 `*.yaml`，不递归进
`presets/`——想启用某个 preset，复制一份到顶层再按需改造，这样 `watch --all` 不会
把 9 个模板当成你的真实订阅跑掉。

## 不入 git 的东西

订阅文件本身可以入 git（不含凭证）。watch 的运行产物——日报、watermark、下载的
PDF——都不入 git（见仓库 `.gitignore` 与 AGENTS.md §6.4）。

## presets 索引（Phase 6 T8 交付）

`subscriptions/presets/` 9 件已到位（design/09 §4 清单）；每件头部注释 precision/
recall 取向与改造建议，逐字段解析校验见 `tests/unit/test_subs_presets.py`。

| 文件 | 领域 | 源组合 | 取向 |
|---|---|---|---|
| `llm-agents.yaml` | LLM 智能体（CS） | arxiv + openalex | 宽召回 |
| `rl-theory.yaml` | 强化学习理论（CS） | arxiv + openalex | 高精确 |
| `causal-inference.yaml` | 因果推断（计量方法） | arxiv + openalex + s2 | 宽召回 |
| `econometrics-methods.yaml` | 计量方法（计量方法） | arxiv + openalex + s2 | 高精确 |
| `asset-pricing.yaml` | 资产定价（econ/fin） | arxiv + ssrn + nber | 高精确 |
| `market-microstructure.yaml` | 市场微观结构（econ/fin） | arxiv + ssrn | 高精确 |
| `corporate-finance.yaml` | 公司金融（econ/fin） | arxiv + ssrn + nber | 宽召回 |
| `mechanism-design.yaml` | 机制设计（CS/理论经济学） | arxiv + openalex | 高精确 |
| `optimization-ml.yaml` | 机器学习优化（CS） | arxiv + openalex | 宽召回 |
