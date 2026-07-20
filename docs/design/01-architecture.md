---
title: 总体架构
status: approved
owner: fable5
updated: 2026-07-20
---

# 01 · 总体架构

> 配图：[diagrams/01-architecture.svg](../diagrams/01-architecture.svg)（分层）与 [diagrams/02-plugin-modules.svg](../diagrams/02-plugin-modules.svg)（插件视图）。

## 1. 分层视图

自上而下六层，依赖只允许向下：

```
┌─────────────────────────────────────────────────────────┐
│ L6 接口层        CLI (typer) · 未来: TUI/daemon 定时器     │
├─────────────────────────────────────────────────────────┤
│ L5 编排层        Orchestrator · Task 队列/状态机 · 调度与   │
│                  限速协调 · 断点恢复 · watch 增量           │
├─────────────────────────────────────────────────────────┤
│ L4 领域层        六阶段 Pipeline (discover/enumerate/       │
│                  resolve/fetch/extract/ingest) · 去重合并   │
│                  · 订阅过滤 DSL                            │
├─────────────────────────────────────────────────────────┤
│ L3 插件层        VenueRegistry · PlatformAdapter ×N        │
│                  (open_access / auth_gated 两族) ·          │
│                  聚合源客户端 (Crossref/OpenAlex/DBLP/S2)   │
├─────────────────────────────────────────────────────────┤
│ L2 获取基建层    HttpFetcher (httpx) · BrowserFetcher      │
│                  (Playwright) · RateLimiter · RetryPolicy  │
│                  · AuthProvider 族 · robots 缓存           │
├─────────────────────────────────────────────────────────┤
│ L1 存储与观测层  SQLite(→PG) · 文件库 data/ · 结构化日志    │
│                  · FetchLog · 报告生成                     │
└─────────────────────────────────────────────────────────┘
```

## 2. 组件职责与边界

| 组件 | 职责 | 关键边界（不做什么） |
|---|---|---|
| **CLI** | 参数解析、人机交互（确认/进度/BLOCKED 提示） | 不含业务逻辑；一切经 Orchestrator |
| **Orchestrator** | 把用户意图展开为 Task DAG；调度执行；并发与全局限速协调 | 不理解站点细节 |
| **Task 队列** | 持久化任务与状态机（PENDING/RUNNING/DONE/FAILED/BLOCKED）；幂等键去重 | 不含重试策略（属 RetryPolicy） |
| **Pipeline 阶段** | 每阶段一个纯函数式核心：输入实体 → 调 adapter → 输出实体+副作用（DB/文件） | 阶段间只通过持久化实体通信 |
| **VenueRegistry** | 加载/校验 VenueSpec YAML；venue→adapter 绑定解析 | 不发网络请求 |
| **PlatformAdapter** | 站点专有逻辑：URL 构造、页面/API 解析、资产定位 | 不管限速/重试/session 生命周期（声明需求，基建执行） |
| **聚合源客户端** | Crossref/OpenAlex/DBLP/S2/Unpaywall 的类型化客户端 | 是特殊的 adapter，同受限速管理 |
| **HttpFetcher** | 异步 HTTP、条件请求缓存（ETag）、代理（EZProxy 重写点） | — |
| **BrowserFetcher** | Playwright 上下文池、页面渲染、上下文内下载 | 不做指纹对抗 |
| **AuthProvider** | session 获取/校验/续期/失效上报（见 design/07） | 不存明文密码 |
| **RateLimiter** | per-domain token bucket + 全局并发闸 | 策略值来自 adapter 声明与 VenueSpec 覆盖 |
| **Storage** | SQLite 事务、迁移、文件落盘与对账 | — |
| **Observability** | 结构化日志（jsonl）、FetchLog 表、运行报告、canary 结果 | — |

## 3. 一次典型运行的数据流

以 `crawler pull jfe --volume 160` 为例（JFE = Journal of Financial Economics，Elsevier 平台）：

1. **CLI→Orchestrator**：解析出意图 `(venue=jfe, selector={volume:160}, stages=auto)`。
2. **Registry**：`jfe.yaml` → metadata_source=`crossref`(ISSN 0304-405X)，fulltext_source=`elsevier_sd`，auth=`institutional`。
3. **discover**（若时间轴未缓存）：Crossref 客户端按 ISSN 拉卷期结构 → 写 `Issue` 表。
4. **enumerate**：Crossref 按 volume 过滤列出该卷全部 DOI + 元数据 → 写 `Paper`（状态 metadata_only）。
5. **resolve**：`elsevier_sd` adapter 把每个 DOI 映射为 PDF 资产 URL（优先官方 API 的 entitlement 检查，fallback 页面解析）→ 写 `Asset`（状态 resolved）。
6. **fetch**：AuthProvider 确认 Elsevier session 健康 → BrowserFetcher/HttpFetcher 按限速下载 → 文件校验 → `Asset` 状态 fetched，写 FetchLog。
7. **extract**：PDF 元数据核对（页数、标题比对），可选全文抽取 → `Paper` 补全。
8. **ingest**：identifier 合并（该文若有 SSRN 前身则建 `preprint_of` 候选）→ 索引更新 → 运行报告输出。

失败路径：resolve 或 fetch 遇 403/登录页 → AuthProvider.health_check → 失败则 Task 转 BLOCKED，CLI 提示 `crawler auth login elsevier`；其余错误按分类重试或标记 FAILED（见 design/05 §错误分类）。

## 4. 双模块在架构中的位置

`open_access` 与 `auth_gated` 不是两条竖井，而是 L3 adapter 的**能力声明**差异 + L2 绑定差异（D-003）：

| | open_access 族 | auth_gated 族 |
|---|---|---|
| 典型源 | arXiv、OpenReview、PMLR、CVF、ACL Anthology、NeurIPS、AAAI OJS、NBER、TE/QE | Elsevier、Wiley、OUP、UChicago、INFORMS、IEEE、ACM、Cambridge、Springer、JSTOR |
| fetcher | HttpFetcher 为主 | HttpFetcher(带 session/API key) 或 BrowserFetcher |
| auth | none（SSRN: free_account 可选） | institutional / subscription / api_key |
| 失败特型 | 404/结构变化 | 401/403/登录跳转/entitlement 不足 |
| 附加状态 | — | session 生命周期、BLOCKED 人工介入 |

## 5. 部署形态

- **Phase ≤6**：单机 CLI 按需运行 + `cron`/`launchd` 定时 `crawler watch`。
- **可选演进**：常驻 daemon（同一代码库，Orchestrator 加事件循环）；SQLite→PostgreSQL 仅当出现并发写瓶颈。
- 所有路径可配置：`~/.paper-crawler/config.toml`（数据目录、凭证库位置、全局限速系数）。

## 6. 技术选型理由摘要

见 D-001。补充两点：
- **httpx 而非 requests**：原生 async + HTTP/2，与 per-domain 并发闸配合自然。
- **Playwright 而非 Selenium**：`storage_state` 序列化、context 隔离、自动等待语义，且 auth_gated 模块的核心诉求（session 复用）是其一等公民能力。

## 7. 本文档的验收关联

架构层面的可测性设计：L3 adapter 全部面向接口（可 mock）、L2 fetcher 可注入 fixture 回放实现（NFR-6）。测试类型与门禁见 [testing/test-plan.md](../testing/test-plan.md)。
