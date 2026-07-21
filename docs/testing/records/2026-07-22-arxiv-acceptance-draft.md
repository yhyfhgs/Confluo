---
title: arXiv 验收执行记录（AC-2.3）· DRAFT
status: draft
owner: fable5
updated: 2026-07-22
---

# arXiv 验收执行记录（AC-2.3）— **DRAFT**

> **draft 状态**：本记录由 Phase 2 T7 implementer 起草并附实测证据；**主 agent 终验后转正**
> （去掉 draft 标记、补独立复核结论）。口径依 arxiv.md §6 的 AC-2.3 证据分层（D-018）。

- 起草日期：2026-07-22 · 起草者：T7 implementer（fable5 档）
- 代码版本：`worktree-agent-a00d496f50d3bb46e` @ `d933472`（起点 982c2ad = main，含 T5/T6 全合并）
- 环境：macOS (Darwin 25.5.0) · Python 3.13.12 · uv
- 在线执行：**授权真实网络任务**（本项目首个）——UA 携真实 mailto（`yhyfhgs@gmail.com`，D-014）、
  单连接 1 req/3s（ToU），限速器三域共享一桶（C4 逐请求限速闸）

## AC-2.3 判据与双层证据（D-018）

AC-2.3 口径：预印本渠道（arXiv）增量 watch 无重复无遗漏、真实解析入库。证据分两层——

| 层 | 内容 | 证据 | 结果 |
|---|---|---|---|
| ① 离线七日回放（机制正确性，CI 化） | 连续 7 收割日 watch，注入逐日递增 + 重叠窗口 + announce 延迟，断言 7 日累计无重复无遗漏 | `tests/integration/test_arxiv_watch.py::test_seven_harvest_day_replay_dedups_and_handles_announce_delay`（T4 设计 / T6 合并，MockTransport 零网络） | **PASS**（随离线门禁每次跑） |
| ② 在线冒烟（真实解析入库） | 真实站点 healthcheck + 单桶 enumerate 首页解析 + 单篇 PDF 魔数 + robots/ToU 复核 | `tests/online/test_arxiv_smoke.py`（`@online`，实跑见下） | **PASS**（2026-07-21T19:19Z 实跑 6 passed） |

> 第三层（真实连续 7 自然日 watch + 第 7 日抽样 20 篇人工比对官方 listing）属 **T6 runbook**，
> 随 Phase 6 AC-6.1 联合执行——不在本期判定（D-018 明示，不静默弱化 AC 字面）。

## 在线冒烟实跑（层②证据）

- 命令：`uv run pytest tests/online -m online -v`（全文归档 `scratchpad/p2-t7-online-run.txt`）
- 窗口：2026-07-21T19:19:39Z → 19:20:01Z（22.09s，含 1req/3s 限速 sleep）
- 结果：**6 passed**（5 arxiv 冒烟 + 1 基建占位）
- 预算：`MAX_REAL_REQUESTS = 10`，实际 **7 真实请求**（见台账），护栏未触发

### 在线请求台账（7 请求 ≤ 10，全程 1req/3s 单连接、UA 含 mailto）

| # | 阶段 | 方法/端点 | 说明 |
|---|---|---|---|
| 1 | canary 选样 cs.LG | GET export.arxiv.org/api/query `search_query=cat:cs.LG`（1999 窗，升序） | 取主分类原生最早篇 |
| 2 | canary 选样 econ.EM | GET export.arxiv.org/api/query `cat:econ.EM`（2018 窗） | 同上 |
| 3 | canary 选样 q-fin.PR | GET export.arxiv.org/api/query `cat:q-fin.PR`（2010 窗） | 同上 |
| 4 | healthcheck | GET export.arxiv.org/api/query `id_list=cs/9901001v1,1801.00973v1,1001.0615v1` | 双字段比对 → healthy |
| 5 | enumerate 首页 | GET oaipmh.arxiv.org/oai `ListRecords set=cs from=2026-07-01 until=2026-07-22` | 解析出首个真实 stub（不翻页） |
| 6 | 单篇 PDF fetch | GET arxiv.org/pdf/cs/9901001 | 102401 bytes，`%PDF` 魔数 ✓ |
| 7 | robots/ToU 复核 | GET export.arxiv.org/robots.txt | 见下节 |

合规声明：7 请求全部经共享 `RateLimiter`（1req/3s、三域别名同桶）逐请求 `acquire` 限速；
UA = `PaperCrawler/<ver> (personal research; mailto:yhyfhgs@gmail.com)`（D-014）；无认证、无凭证；
仅访问官方文档化端点（Query API / OAI-PMH / abs-pdf / robots.txt）。

## canary 样本记录（arxiv.md §6，3 跨域主分类原生论文）

选样策略：每域在"该 archive 上线后若干年"的日期窗内升序取**主分类即目标 category** 的最早原生
论文（年代久远 → 最稳定，主分类正确 → 贴合跨域语义）。规整化 title + primary_category 为 Query API
实测捕获，已落 `adapter._CANARIES` 及 offline 夹具（`09_query_atom_healthcheck.xml`）。

| 域 | base_id | query_id | primary_category | 规整化 title |
|---|---|---|---|---|
| cs.LG | `cs/9901001`（老式 slash id） | `cs/9901001v1` | cs.LG | TDLeaf(lambda): Combining Temporal Difference Learning with Game-Tree Search |
| econ.EM | `1801.00973` | `1801.00973v1` | econ.EM | A New Wald Test for Hypothesis Testing Based on MCMC outputs |
| q-fin.PR | `1001.0615` | `1001.0615v1` | q-fin.PR | Adaptive Wave Models for Option Pricing Evolution: Nonlinear and Quantum Schrödinger Approaches |

在线 healthcheck 实测：`healthy=True — 3 canaries matched (title + primary_category)`。
cs.LG canary 用老式 slash id，顺带验证 Query API `id_list` 接受老式 id + 版本号并正确回样。

## robots / ToU 复核（arxiv.md §4 ⚠ 实现期义务）

- 实测 `export.arxiv.org/robots.txt` 全文（2026-07-21T19:20Z）：

  ```
  User-agent: *
  Disallow: /
  ```

- 判定：与 arxiv.md §4 推理**一致，无相悖条款**。§4 早已预判 export.arxiv.org 对通用爬虫全禁
  （`Disallow: /`）；该 blanket disallow 是**网页爬虫公约**，不针对、也未点名禁止 ToU 授权的
  API 消费。本 adapter 对该域仅走官方文档化 Query API（export.arxiv.org/api/query）与 OAI-PMH
  （oaipmh.arxiv.org/oai），其程序化访问依据是 arXiv **API Terms of Use 的明确邀请**（限速 1req/3s、
  单连接——本实现严格遵守）。robots.txt 未含任何"禁止 API/程序化消费""禁止 ToU 授权访问"之类
  **直接否定 API ToU 邀请**的条款，故 §4 的"robots 公约不适用于 ToU 授权 API 消费"推理成立，
  通道保持授权。**未触发** decision-log 升级（AC-0.5 红线未命中）。
- ⚠ 诚实标注（供主 agent 终验注意）：`Disallow: /` 对 `User-agent: *` 字面上覆盖全路径含 `/api`。
  本判定依赖"API ToU 为独立且更具体的明确授权，优先于泛化 robots 网页公约"这一 §4 [LIVE 2026-07-20]
  既立推理——**非本期新证伪**。若主 agent/合规复核认为该张力需更强的书面 ToU 引用佐证，建议作为
  Phase 2 收尾的 AC-0.5 复核项留痕（当前证据：robots 实测形态符合预判、访问严守 ToU 限速与端点边界）。

## M3 顺手项（503/错误响应形态校正 fixture08）

- **未执行（标注跳过）**：真实触发 400（offset>30000）/503 需额外请求且形态易变（arxiv.md §6 承认
  错误态难可靠录制）；本期为守请求预算未做实测校正。fixture08（400 offset 超限）保持合成，已与
  HttpClient「其余 4xx→CONFIG」冻结契约离线对齐（`test_arxiv_fixtures` / `test_arxiv_adapter`）。
  排期真实校正时走 `scripts/record_arxiv_fixtures.py`。

## 待主 agent 终验补全

1. 独立复核（另一 agent 亲跑门禁 + 抽验在线台账合规）结论；
2. robots/ToU 张力是否需追加书面 ToU 引用（见上节 ⚠）；
3. 转正：去 draft 标记、并入 AC 汇总。
