---
title: 六阶段 Pipeline 与任务系统
status: implemented
owner: fable5
updated: 2026-07-29
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
| 5 extract | Asset(fetched, pdf) | `Fulltext` 行 / Paper 字段补全 | **(asset_id, source_sha256, extractor, extractor_ver)**（Phase 7 T7 兑现「asset 级键」注记；表 PK 仍 paper_id——asset 级的是**键**不是基数。取代规则＝全序取 max `(rank, ver_key, char_count, asset_id)`，故终态与注入顺序无关。[D-033](../plan/decision-log.md) / [design/12](12-fulltext-extract.md) §5） | —（本地；GROBID 为可选本机服务） |
| 6 ingest | Paper/Identifier 增量 | 合并关系（same_as/preprint_of/candidate）+ 索引 | 确定性合并规则版本 | —（本地） |

各阶段在实现里彼此独立、可分别重跑（断点续爬的基础，见 §5），但**没有通用的逐阶段 CLI 动词**（如实订正，2026-07-29：本行原写 `crawler run enumerate --venue jfe --volume 160`，该命令不存在，`cli.py` 命令表里没有 `run` 子命令）。用户可见的组合入口是 `crawler list <venue> --volume V [--issue I]`（内部经 `PipelineRunner.run_single_stage` 驱动 discover→enumerate，只产清单不下载资产，§6）与 `crawler pull ...`（默认编排器按需级联：1→4，`--extract` 加 5，6 每次运行尾部自动跑；`pull --extract` 是 stage 5 extract 的**唯一**入口，没有独立的 `run extract`/`crawler extract` 命令）。

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

### 任务 GC（保留窗清理，审计修复批 R3c 新增，2026-07-29 补文档）

- **目的**：`task` 表全库零 `DELETE` 语句，DONE 行随运行单调累积，拖慢 `_fresh_skip`/`claim_next` 等高频查询（审计 C2 合成库定量实测；索引侧的第一道防线见 [design/06 §2](06-data-model.md) 的 `0006_perf_indexes.sql` 说明）。`TaskQueue.gc_done(retention_days=30, limit=1000)`（`tasks.py`）是第二道防线：只删 `state='DONE'` 且 `updated_at` 早于 `now - retention_days` 的行；非 DONE 任何龄一律不动；受 `task.parent_id` 自引用外键保护（每轮只挑当下真无人引用的候选，循环到不动点或耗尽 `limit` 预算才停）；单批以"先 `SELECT id` 定批、再按 id 列表 `DELETE`"两步写法执行（不依赖 SQLite 的 `DELETE...LIMIT` 扩展语法）；幂等，重复调用安全收敛。
- **接线点**：`PipelineRunner._finalize`（`pipeline/runner.py`）在报告落盘（`report.save()`）之后调用 `_gc_done_tasks()`，是 `TaskQueue.gc_done` 的**唯一**调用点。三条理由缺一不可：①`_finalize` 是五个公开入口（pull/run_single_stage/drain/watch/grab）一律在 `finally` 中调用的单点，覆盖全部路径含异常路径；②`_finalize` 整段落在各入口的进程级排他锁内（见下"进程级互斥"），故 GC 与另一进程的任何 pipeline 会话互斥，避免"先 SELECT 定批、再 DELETE"两步之间被并发插入的删除/新建打乱；③GC 失败被吞成 WARNING 日志、不改变本轮任何语义、不覆盖正在传播的原异常——GC 是"跑完一轮之后顺手做的家务"，不放进 `__init__`（只读命令如 `crawler list`/`timeline` 构造 runner 时不该顺手删别人的历史行）。
- **`fetch_log.task_id` 悬空口径**：`fetch_log` 表的 `task_id` 列（`0001_init.sql`）是纯 `TEXT`，**没有**外键约束（不像 `asset_id`/`parent_id` 那样声明 `REFERENCES`）——GC 删除超窗 DONE 任务行后，`fetch_log.task_id` 可能指向一个已不存在的任务 id。这是**刻意留白**而非疏漏：`fetch_log` 是限速合规的审计留痕（§7），价值在于"何时对哪个域发了什么请求"，与任务本身是否还存活无关；给它加外键会让 GC 删任务时被迫级联删审计日志（或改 `ON DELETE SET NULL`），徒增复杂度换不到实际收益。消费方若需按 `task_id` 反查任务，须自行容忍该字段可能悬空。

## 3. 调度与并发

- **单进程异步**（Phase1 起步可纯串行，接口不变）：全局并发闸（默认 4）+ per-domain 闸（默认 1）+ per-domain token bucket（速率来自 adapter 声明 → VenueSpec 覆盖 → CLI 临时覆盖，取**最保守值**）。
- **优先级**：交互式命令（pull/grab）> watch 增量 > backfill 回填；同优先级 FIFO。**实况订正（2026-07-29，D-039 defer）**：本条分层从未实现——`TaskQueue.claim_next`（`tasks.py`）是单一 `SELECT ... ORDER BY created_at, id LIMIT 1`，任务表无优先级字段，pull/grab/watch 之间不存在调度层面的优先关系，只有提交顺序的 FIFO。`crawler backfill` 命令本身也未实现（§6 该行为设计声明）。单用户场景下纯 FIFO 实测已足够；再评估条件（回填与在线交互任务互相饥饿的实证场景）见 [D-039](../plan/decision-log.md)。
- **auth_gated 附加约束**：同一 AuthProfile 全局串行（见 design/04 §5：不并行多 session）；工作时段窗口。
- **watch 模式**：`crawler watch` 由 cron/launchd 触发一次性运行（无常驻进程）；watermark 持久化在 `Subscription` 表（见 design/09）。

### 进程级互斥（`flock`，审计修复批 R3d 新增，2026-07-29 补文档）

- **问题**：`PipelineRunner.__init__` 的两个启动动作——`cleanup_tmp(data/tmp)`（清理 `*.part` 崩溃残留，§5.2）与 `queue.recover_running()`（孤儿 RUNNING 归还 PENDING）——都是**无进程范围**的破坏性操作。`.part` 文件名恒为 `{asset_id}.part`，若 cron `watch` 与交互式 `pull` 重叠运行，后启动者的这两个动作会删掉前者正在写的 part、抢走前者已 claim 的 RUNNING 任务——落盘字节与 DB `sha256` 可以不符，且只有事后 `crawler verify` 才看得见。
- **修复**：`fcntl.flock` 排他锁，路径 `<config-home>/state/.pipeline.lock`（`pipeline_lock_path`，`pipeline/runner.py`），覆盖启动动作与**五个公开入口**（pull/run_single_stage/drain/watch/grab）各自的整个会话——从入队到 drain 结束再到 `_finalize` 报告落盘（含上一小节的任务 GC）。锁范围是**会话粒度**（`_exclusive()` 上下文管理器），不是从 `__init__` 一直持到对象析构——持到析构等于把释放时机交给"该对象何时被丢弃"，一次异常回溯就可能把它拖到调用方丢弃 `__traceback__` 为止，届时"同一进程里的下一条命令"会被自己上一条挡住。
- **语义**：`LOCK_EX | LOCK_NB`（非阻塞）——抢不到锁即**响亮失败**（`CrawlerError(CONFIG)`），不等待、不静默（cron 撞上手动运行时，本轮跳过、下一轮 cron 自然恢复，语义上比互相等待更合适）。崩溃自动释放：`flock` 绑在打开的文件描述符上，进程无论正常退出还是被 SIGKILL/断电，内核回收 fd 时都会释放锁——没有陈旧锁文件问题，不需要 PID 探活/TTL，也不该在启动时删锁文件。互斥域是 **config-home**（一个 `--home` = 一套 DB + 一份 `data/`），正是 cron `watch` 与手动 `pull` 争抢的那一套东西。Windows（无 `fcntl`）降级为无锁，如实标注非跨平台承诺（本仓库 CI/开发/部署目标均为 macOS/Linux）。
- **`cleanup_tmp`/`recover_running` 的作用范围不变**：二者仍是**无进程范围**的全局清理（分别清 `data/tmp/` 下全部 `*.part`、把全库孤儿 RUNNING 行归还 PENDING）——锁修复的是"两个进程的这类清理与对方的 drain 互相踩踏"，不是把清理范围收窄到"只清本进程自己产生的"。会话之间的空档不构成缺陷窗口：下一个会话开始时若另一进程仍在跑，一样在取锁处响亮失败，不会出现两边同时清理的交错。

## 4. 错误分类学（贯穿全系统的统一枚举）

| error_class | 例 | 重试策略 | 升级路径 |
|---|---|---|---|
| `transient` | 超时、连接重置、5xx | 指数退避 3 次（2/8/30s） | 3 败转 FAILED，可批量 retry |
| `rate_limited` | 429、Retry-After | 按 Retry-After 或退避重试，不计失败 | 连续 3 次 → domain 冷却 1h（Phase 1 近似：连续 >3 次转按 `transient` 处置防串行 drain 挂死；domain 冷却机制随 Phase 2 真实站点落地） |
| `auth_expired` | 401/302→login、healthcheck 失败 | 不重试 | 整批 BLOCKED(auth) |
| `no_entitlement` | 403 且 session 健康、entitlement 预检否 | 不重试 | 标记 + OA fallback（Unpaywall） |
| `challenge` | CAPTCHA/Cloudflare 特征（含 403 + `cf-mitigated: challenge` 头） | 不重试 | BLOCKED(challenge) + **域冷却 24h**（D-030 E-1：键 = 该任务 asset URL host，无 asset 时退回 `<adapter_id>` 平台级键；冷却门先于 OA-fallback 旁路，对全部 fetch 生效。详见 [auth-framework.md](auth-framework.md) §8.4） |
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
             [--filter EXPR] [--limit N] [--dry-run] [--extract]  # --extract = stage 5 的唯一入口，无独立 run/extract 命令
crawler grab --doi D | --arxiv ID | --ssrn ID | --url U # 单篇跨 venue 精取（--url 供无标准 id 的 WP/ECCC 类，D-015）
crawler backfill <venue> --from YEAR [--to YEAR]       # 设计声明，命令未实现（低优先级队列同未实现，D-039 defer）；现状用 pull --year/--volume 逐期手工回填
crawler subs watch <subscription-name> | --all         # 订阅增量（cron 入口；P6-T5 落地时因 crawler watch 已被 preprint venue 增量占用而落子命令组，controller 裁决 2026-07-26）
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

## 9. 修订记录

| # | 日期 | 修订 | 依据 |
|---|---|---|---|
| 1 | 2026-07-26 | §4 `challenge` 行"平台冷却 24h"→"**域冷却 24h**"（键 = asset URL host，无 asset 退回 `<adapter_id>`；冷却门先于 OA-fallback 旁路），并补 403+`cf-mitigated` 亦属该类的判据来源 | [D-030](../plan/decision-log.md) 裁决②③ + F6 实现卡（`fix/cf403-cooldown`）+ F6 审查裁决 F6-1 |
| 2 | 2026-07-29 | 文档订正批（纯记账，代码此前已交付）：①§1 删除虚构的 `crawler run enumerate --venue jfe --volume 160` 叙述，改为如实描述 `crawler list`/`crawler pull --extract` 两条真实入口；②§2 新增"任务 GC"小节（`gc_done` 保留窗、`_finalize` 内锁内执行、`fetch_log.task_id` 悬空口径）；③§3 新增"进程级互斥"小节（五入口 `flock`、`cleanup_tmp`/`recover_running` 作用范围）；④§3 优先级分层行补 defer 标注；⑤§6 CLI 列表 `backfill` 行标注未实现 | 2026-07-28/29 审计修复批 R3c/R3d（`fix(pipeline)` 提交）+ [D-039](../plan/decision-log.md) |
