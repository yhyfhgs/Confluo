# 日报 — 2026-07-26

## 总览

| 订阅 | 状态 | 新增 | 入库 | 熔断 |
| --- | --- | --- | --- | --- |
| asset-pricing-wp | truncated | 250 | 0 | 熔断 |
| llm-agents | ok | 2 | 2 | - |

## asset-pricing-wp

- 状态: truncated
- 新增: 250
- 入库: 0
- 累计库存: 900

熔断：本次新增 250 篇超过阈值 100（guard.max_new_per_run），已按护栏规则暂停入库；请收窄查询条件后重试。

### 过载分布

按来源分布：

| 来源 | 数量 |
| --- | --- |
| arxiv | 150 |
| nber | 70 |
| ssrn | 30 |

按分类分布：

| 分类 | 数量 |
| --- | --- |
| cs.LG | 130 |
| cs.AI | 120 |

收窄建议：优先考虑收窄 来源 `arxiv`（150 篇，占 60.0%） 或 分类 `cs.LG`（130 篇，占 52.0%）。

## llm-agents

- 状态: ok
- 新增: 2
- 入库: 2
- 累计库存: 45

### 新增清单

| 标题 | 作者 | 链接 | 命中规则 |
| --- | --- | --- | --- |
| Emergent Tool Use | Dana Doe | https://arxiv.org/abs/2402.00001 | title_regex_any[0] |
| Planning with LLM Agents | Eve Smith, Frank Lee | https://arxiv.org/abs/2402.00002 | title_regex_any[0], min_year |

### 失败事件

| 来源 | 错误类型 | 消息 |
| --- | --- | --- |
| openalex | rate_limited | HTTP 429 Authorization: *** |

## 累计库存

| 订阅 | 累计库存 |
| --- | --- |
| asset-pricing-wp | 900 |
| llm-agents | 45 |
