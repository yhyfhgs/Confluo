---
title: 六阶段 Pipeline 与任务系统
status: implemented
owner: fable5
updated: 2026-07-21
---

# 05 · 六阶段 Pipeline 与任务系统

> 决策依据：D-004（六阶段）、D-005（元数据主干）。配图：[diagrams/03-pipeline.svg](../diagrams/03-pipeline.svg)。

## 1. 阶段定义

**不变式：阶段间只通过持久化实体通信；每阶段幂等（同输入重跑结果一致且无副作用叠加）。**

| 阶段 | 输入 | 输出（持久化） | 幂等键 | 典型 adapter 调用 |
|---|---|---|---|---|
| 1 discover | VenueSpec (+since) | `Issue` 行（含 VenueEra） | (venue, volume, issue) / (venue, year) | `discover_timeline` |
| 2 enumerate | Issue | `Paper` 行（metadata_only）+ `Identifier` | (source, source_key)，如 (crossref, doi) | `enumerate_issue` |
| 3 resolve | Paper | `Asset` 行（planned，含 URL/auth 需求/类型） | (paper, asset_kind) | `resolve_assets` |
| 4 fetch | Asset(planned) | 文件落盘 + Asset(fetched) + `FetchLog` | asset_id（文件存在且校验通过=完成） | `fetch_asset` |
| 5 extract | Asset(fetched, pdf) | `Fulltext` 行 / Paper 字段补全 | (asset, extractor_ver)（Phase 1 noop 抽取按 paper 粒度落 fulltext——其 PK=paper_id；asset 级键随 Phase 7 真实抽取启用） | —（本地） |
| 6 ingest | Paper/Identifier 增量 | 合并关系（same_as/preprint_of/candidate）+ 索引 | 确定性合并规则版本 | —（本地） |

阶段可单独执行（`crawler run enumerate --venue jfe --volume 160`），默认编排器按需级联（`pull` = 1→4，`--extract` 加 5，6 每次运行尾部自动跑）。

## 2. 任务模型与状态机

```
Task {
  id: ULID
  kind: discover | enumerate | resolve | fetch | extract | ingest
  venue_id, params_json          # 幂等键的来源
  state: PENDING → RUNNING → DONE
                 ↘ FAILED(error_class, attempts)
                 ↘ BLOCKED(reason)           # 需人工：认证失效/风控/需确认
  attempts, last_error, created_at, updated_at
  parent_id                      # 级联展开的溯源（pull 任务展开出的子任务）
}
```

- **入队去重**：同幂等键的 PENDING/RUNNING 任务不重复入队；DONE 任务重新请求时按"新鲜度策略"决定跳过或刷新（timeline 类 24h、清单类 7d、asset 永久，`--force` 覆盖）。
- **实现注记（Phase 1，勘误性补全）**：① `kind` 枚举含编排父任务 `pull`（本节 parent_id 一段所述"pull 任务"的机制化）；② 幂等唯一索引用 `COALESCE(venue_id,'')` 表达式（SQL NULL≠NULL，venue-less 任务需此保证去重）；③ 队列提供 `recover_running()`：进程启动时孤儿 RUNNING→PENDING（不占 attempts），是 §5 断点续爬的崩溃恢复入口；④ fetch 执行前**现场 re-resolve**（重新调 `resolve_assets` 刷新 asset 的 url/auth_needed 再下载）——资产幂等身份 (paper, kind) 不变，url 属易变执行细节（签名 URL/entitlement 时效的常态化处理），也是"认证修复后 resume 即可继续"语义的前提。
- **BLOCKED 语义**：不占重试次数、不自动恢复；`crawler status --blocked` 列出并给出人工动作提示（如 `auth login elsevier`）；人工处理后 `crawler resume <task|--all>` 转回 PENDING。
- **FAILED 语义**：按错误分类决定是否可重试（见 §4）；`crawler retry --class transient` 批量重试。

## 3. 调度与并发

- **单进程异步**（Phase1 起步可纯串行，接口不变）：全局并发闸（默认 4）+ per-domain 闸（默认 1）+ per-domain token bucket（速率来自 adapter 声明 → VenueSpec 覆盖 → CLI 临时覆盖，取**最保守值**）。
- **优先级**：交互式命令（pull/grab）> watch 增量 > backfill 回填；同优先级 FIFO。
- **auth_gated 附加约束**：同一 AuthProfile 全局串行（见 design/04 §5：不并行多 session）；工作时段窗口。
- **watch 模式**：`crawler watch` 由 cron/launchd 触发一次性运行（无常驻进程）；watermark 持久化在 `Subscription` 表（见 design/09）。

## 4. 错误分类学（贯穿全系统的统一枚举）

| error_class | 例 | 重试策略 | 升级路径 |
|---|---|---|---|
| `transient` | 超时、连接重置、5xx | 指数退避 3 次（2/8/30s） | 3 败转 FAILED，可批量 retry |
| `rate_limited` | 429、Retry-After | 按 Retry-After 或退避重试，不计失败 | 连续 3 次 → domain 冷却 1h（Phase 1 近似：连续 >3 次转按 `transient` 处置防串行 drain 挂死；domain 冷却机制随 Phase 2 真实站点落地） |
| `auth_expired` | 401/302→login、healthcheck 失败 | 不重试 | 整批 BLOCKED(auth) |
| `no_entitlement` | 403 且 session 健康、entitlement 预检否 | 不重试 | 标记 + OA fallback（Unpaywall） |
| `challenge` | CAPTCHA/Cloudflare 特征 | 不重试 | BLOCKED(challenge) + 平台冷却 24h |
| `gone` | 404/410 | 不重试 | Asset 标 gone；VenueEra 级链接走 Wayback 兜底 |
| `parse` | 解析 0 命中、schema 校验失败 | 不重试 | FAILED(parse) + canary 标红（adapter 腐化信号） |
| `integrity` | 非 %PDF 魔数、大小异常、哈希不符 | 重下 1 次 | auth_leak 疑似 → 触发 healthcheck |
| `config` | VenueSpec 非法、凭证缺失 | 不重试 | 启动期尽量拦截；运行期 BLOCKED(config) |

## 5. 断点续爬（FR-10 的实现语义）

1. 所有枚举结果先落库再继续（enumerate 批量 upsert，事务粒度=一期）；
2. fetch 以单 asset 为事务：下载到 `*.part` 临时名 → 校验 → 原子 rename → 更新 Asset 状态；崩溃残留 `*.part` 启动时清理；
3. 重跑任意命令：先查幂等键，DONE 且新鲜 → 跳过（日志记 skipped），实现"kill -9 后重跑零重复零遗漏"（AC-1.3 验收此不变式）；
4. `crawler verify`：DB↔文件双向对账（DB 有记录文件缺失 / 文件存在 DB 无记录），输出修复建议（re-fetch / adopt / quarantine）。

## 6. CLI 设计（用户接口层）

```
crawler venues list [--field finance] [--tier T1]     # 注册表浏览
crawler venues lint                                    # VenueSpec 校验
crawler timeline <venue> [--refresh]                   # 时间轴（discover）
crawler list <venue> --volume V [--issue I] | --year Y # 清单预览（enumerate，不下载）
crawler pull <venue> (--volume V [--issue I] | --year Y | --doi D...)
             [--filter EXPR] [--limit N] [--dry-run] [--extract]
crawler grab --doi D | --arxiv ID | --ssrn ID | --url U # 单篇跨 venue 精取（--url 供无标准 id 的 WP/ECCC 类，D-015）
crawler backfill <venue> --from YEAR [--to YEAR]       # 历史回填（低优先级队列）
crawler watch <subscription-name> | --all              # 订阅增量（cron 入口）
crawler auth login <provider> / status / logout        # 认证（design/07）
crawler status [--blocked] [--failed] / resume / retry # 任务运维
crawler verify / report [--last-run]                   # 对账与报告
```

`--dry-run` 贯穿：完成到 resolve 为止，输出"将下载 N 篇 / M MB（估）/ 命中过滤 K 篇"清单不落盘（FR-05）。

- **修订注记（2026-07-22，D-022 · C-C 修复）**：① **零网络 resolve 豁免限速闸**——adapter 经 `AdapterBase.resolve_offline = True` 声明其 `resolve_assets` 为纯本地构造（不发任何网络请求）时，resolve 阶段不取限速 token（未声明者默认 `False`，闸保留——安全侧）；该标记不属 `SourceAdapter` 冻结协议，pipeline 经 `getattr` 兜底读取。② **`--limit N` 前置到 resolve 圈选**——只对稳定序（`list_papers` 的 `ORDER BY (title, id)`，主键收尾保证并列标题确定性）前 N 篇建 resolve 任务；dry-run 计数与实跑一致、两次重跑圈选同一子集。语义边界：前 N 篇中存在零资产 paper 时落盘可 < N（不往后凑满——凑满需 resolve 更多 paper，与前置目标矛盾）；RunReport 如实呈现计划/实际计数。

## 7. 观测性（FR-14）

- **结构化日志**：jsonl，每行含 `ts, level, task_id, venue, stage, domain, url(脱敏), error_class, msg`；控制台人读摘要，文件机读全量。
- **FetchLog 表**：每次**资产**取回一行（含字节数、耗时、HTTP 状态、限速等待时长）——限速合规的审计证据（AC-4.4 数据源）。（勘误 2026-07-21：口径澄清为资产取回；metadata 侧请求（聚合 API/OAI 收割等）不入本表，其限速审计证据为 obslog jsonl 的逐请求事件——Phase 2 HttpClient 义务，见 phase2-implementation-plan §2.1。）
- **运行报告**：每次命令结束输出 markdown 摘要（成功/失败/阻塞/跳过计数、失败清单 top、下一步提示），`report` 子命令可重打印；watch 模式报告落 `docs/reports/watch/`（运行产物目录，不入 git 的 data 区）。
- **canary**：独立命令 `crawler canary`（testing/test-plan §canary 定义样本集），CI/cron 周跑，产出 adapter 健康矩阵。

## 8. 测试与验收

- **单元**：状态机转移全覆盖（含非法转移拒绝）；幂等键构造；错误分类映射表（HTTP 状态×上下文→class）。
- **集成（mock adapter）**：六阶段级联；kill-9 注入（随机点中断进程重跑）验证零重复零遗漏；BLOCKED→resume 流程。
- **验收**（AC-1.x 摘录）：
  - AC-1.1 mock venue 端到端 pull 产出文件+DB 一致；
  - AC-1.2 dry-run 与实跑清单一致且 dry-run 零网络下载副作用；
  - AC-1.3 任意阶段 kill 后重跑，最终结果与不中断一致（对比 DB dump）；
  - AC-1.4 限速器在压力测试下 per-domain 速率不超配置值 ±5%。
