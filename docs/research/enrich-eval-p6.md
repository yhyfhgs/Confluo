---
title: R2 合并评估：repec aggregator-enrich 通道 + ssrn 覆盖候补 ladder
status: draft
owner: fable5
updated: 2026-07-26
---

# R2 · repec enrich 通道 + ssrn 覆盖候补 ladder 合并评估（draft，待 fable 裁决）

> **任务卡**：[phase6-implementation-plan §4 R2](../plan/phase6-implementation-plan.md)（opus 起草 / fable 定稿）。
> 合并对象 = [phase5-report §6 检查单 #4](../reports/2026-07-24-phase5-report.md)（repec enrich）+ **#1**（ssrn 覆盖候补阶梯）。
> **本稿零网络请求**：全部结论建立在既有 [LIVE] 勘察与本仓库源码事实上；需在线数据处标 `[PENDING M1-d]`
> （由并行 M1-d 批供数，预算 §3 M1-d 行 ≤10 请求），并对每个待填格给出**先行判定规则**——数据到位即可机械读出结论，
> 不需要重跑评估。
>
> **出处标注约定**（AGENTS §5）：
> - `[LIVE 日期]`＝本项目实测（勘察台账可回溯）；`[DOC]`＝官方文档或既有勘察转述；
> - `[CODE]`＝本仓库源码/DDL 事实（给 `文件:行` 或符号名，可 grep 复核）；
> - `[推断]`＝未经核实的推理，**不得**当事实用；`[PENDING M1-d]`＝待 M1-d 供数。

## 0. 摘要

- **① repec `aggregator-enrich`：建议「再缓」**——Phase 6 **不立实现卡**，改立一张 **≤6 请求的前置核实探针**
  （挂 §3 预算表「机动」行）把三项 `[UNRESOLVED]` 转成事实；实现卡草稿见 §2.7，探针全绿后由 fable 决定插单
  时点（首选 Phase 7 首批，次选 P6 末 stretch）。决定性理由不是「价值不够」而是**消费端缺位 + 前置事实未核实**
  （§2.6 五条）。
- **② ssrn 候补 ladder 推荐序：(a) OpenAlex 无-DOI 补枚举 ≫ (b) RePEc 交叉核对【出列】≫ (c) SSRN 浏览页 census【否决】。**
  (b) 不是「优先级低」而是**结构性无效**——SSRN 根本不在 RePEc（[LIVE] 442KB archives 全表无 "ssrn" 串），
  可闭合缺口 = **0**；(c) 触 AC-0 红线且本机环境不可执行，双重出局。(a) 一次性历史 backfill 量化成本
  ≈ **1,070 页 / 1,070 credits / $0.107**，日增量 ≈ **1 页 / $0.0001**，合规与环境风险均为零。
- **交裁决问题清单**：§4，共 **13 项**（主裁决 Q1/Q7/Q8/Q9），每项一行 + 起草人倾向。

---

## 1. 共用事实底账

### 1.1 站点侧（两部分共享）

| # | 事实 | 出处 |
|---|---|---|
| F1 | RePEc = 分布式书目元数据聚合器，**非全文源**；IDEAS/EconPapers 是同一数据的只读前端 | [LIVE 2026-07-24] [repec.md §2](site-survey/repec.md) |
| F2 | **JEL 分类**：`nbr:nberwo:35506` → D1/J13/J15；crossref / openalex / nber.org **三路皆缺** | [LIVE 2026-07-24] [repec.md §5④](site-survey/repec.md)；[nber.md §6](site-survey/nber.md)「缺摘要缺 JEL」 |
| F3 | JEL **覆盖偏近年**：`nbr:nberwo:3210`（1989）无 JEL、仅 NBER 程序码；历史覆盖率＝`[UNRESOLVED④]` | [LIVE 2026-07-24] [repec.md §5④/§附](site-survey/repec.md) |
| F4 | **wp↔published 版本关联**：`nbr:nberwo:3210` → "Published in" Oxford Economic Papers（服务 D-007） | [LIVE 2026-07-24] [repec.md §4](site-survey/repec.md) |
| F5 | handle↔DOI **无内建映射**；NBER 条目页不显 DOI，须外部经 crossref join | [LIVE 2026-07-24] [repec.md §4](site-survey/repec.md) |
| F6 | **SSRN 不在 RePEc**（Elsevier 商业源，442KB archives 全表无 "ssrn"） | [LIVE 2026-07-24] [repec.md §6](site-survey/repec.md) |
| F7 | RePEc 取用面：ReDIF / AMF / OAI-PMH（官方自注 "sometimes flaky"）/ Rsync（需联系）/ anonymous FTP；**API email 门控、无搜索、非批量**；官方**强烈不建议爬 HTML** | [LIVE 2026-07-24] [repec.md §3](site-survey/repec.md) |
| F8 | NBER 全库规模：crossref 前缀 `10.3386` **total-results = 35,976**；w 系列上界 ≈ w35506（2026-07）；年增 1200–1500 | [LIVE 2026-07-20] [nber.md §6](site-survey/nber.md) |
| F9 | SSRN 规模：crossref DOI'd **1,414,774**；OpenAlex source `S4210172589` works **1,632,966** | [LIVE 2026-07-24] [ssrn.md §7](site-survey/ssrn.md) |
| F10 | SSRN census：OpenAlex 代理随机采样 N=1000（`sample=1000&seed=42`），**DOI 非空率 869/1000 = 86.9%**（严格 `10.2139` 前缀 86.4%）；阈值 90% **未达标** | [LIVE 2026-07-24] [design/adapters/ssrn.md §9.1](../design/adapters/ssrn.md) |
| F11 | SSRN 领域分布：Economics·Econometrics·Finance 285,640 + Business·Management·Accounting 198,928 = **484,568 / 1,632,966 ≈ 29.7%** | [LIVE 2026-07-24] [ssrn.md §7](site-survey/ssrn.md) |
| F12 | SSRN 年产出：2025 ≈ 243K–262K works；crossref 新 DOI 延迟 ≈ 1 日 | [LIVE 2026-07-24] [ssrn.md §7](site-survey/ssrn.md) |
| F13 | **`*.ssrn.com` = BLOCKED 硬边界**（双独立证据：2026-07-20 站点 Cloudflare 挑战 403 "verify you are human" + 2026-07-24 本机环境 CF 前置域 TLS reset）；SSRN `robots.txt` 的 Disallow 面**至今未取得** | [LIVE/PRIOR-LIVE] [ssrn.md §1/§4/§8](site-survey/ssrn.md)；[D-029](../plan/decision-log.md) |
| F14 | OpenAlex 计费（2026-02-13 起）：**无 key 1000 credits/天、free key 10000/天**；filter 查询 **1 credit**、`search=` 10 credits；匿名 `works?filter=` 仍 200 且 `meta.cost_usd:0.0001`；**`from_created_date`/`from_updated_date` 属 Premium 门控** | [LIVE 2026-07-22] [aggregators.md §2](../design/adapters/aggregators.md) |
| F15 | `api.openalex.org` `/robots.txt` = 404，无 crawl 限制；护栏＝credit 预算 | [LIVE 2026-07-22] [aggregators.md §3](../design/adapters/aggregators.md) |
| F16 | `ideas.repec.org` / `econpapers.repec.org` robots 极宽松、本机可达 200；`repec.org` apex 为环境 TLS 障碍（非站点判罚，且非数据面） | [LIVE 2026-07-24] [repec.md §1](site-survey/repec.md) |

### 1.2 本仓库代码与契约（接入成本的硬约束）

| # | 事实 | 出处 |
|---|---|---|
| C1 | `EnrichmentSource` 是**冻结协议之外**的 duck-typed 可选接口：`enrich_batch(self, dois: Sequence[str]) -> list[PaperStub]`；不实现者静默不参与 | [CODE] `src/paper_crawler/adapter.py:176-190` |
| C2 | `crawler enrich --source <id>` 装配是**通用**的（`load_adapters()` + `isinstance(EnrichmentSource)` + `limiter.register(domains[0], default_rate)`），新 enrich 源**无需改 CLI 主干**；`--source` 是自由 `str`（非枚举），仅 help 文案写着 `openalex\|s2` | [CODE] `cli.py::_prepare_enrich_source`、`cli.py::enrich` 签名 |
| C3 | `_apply_enrich_key` 是 `if source_id == "s2" / elif "openalex"` 的分支链、**无 else 抛错** → 无 key 的新源天然落空跑通 | [CODE] `cli.py:1159-1193` |
| C4 | **`SOURCE_PRIORITY` 是六枚举闭表**（`official 5 / crossref 4 / dblp 3 / openalex 2 / s2 1 / heuristic 0`），`MergeEngine.ingest` 对表外 source **`raise ValueError`**；该表由 **D-021 冻结** | [CODE] `merge.py:58-65,111-112`；[D-021 §3](../plan/decision-log.md) |
| C5 | `identifier.scheme` 是**无 CHECK 约束的 TEXT**（注释举例 `doi\|arxiv\|ssrn\|openalex\|s2\|dblp\|anthology\|...`）→ 新增 `(repec, handle)` scheme **零 migration** | [CODE] `storage/migrations/0001_init.sql:62-65` |
| C6 | **`preprint_of` 建边在 src/ 内零实现**：`preprint_of` 串在 src/ 下仅出现于 `0001_init.sql:102` 的 `kind` 注释；两处 `paper_relation` 插入点（`storage/repo.py:612`、`storage/db.py:67`）**均硬编码 `kind="candidate_duplicate"`** → F4 的版本关联**目前没有消费者**（design/06 §…有设计、代码无路径） | [CODE] `grep -rn "preprint_of\|paper_relation" src/` |
| C7 | openalex `parse_works_batch` 已能把 works 页转 `PaperStub` 流并回报 `cost_usd`/跳过计数；`identifier(openalex)=W…` **恒有** → **无 DOI 的 works 也能构造合法 stub** | [CODE] `adapters/openalex/parse.py::parse_works_batch`/`_stub_of` |
| C8 | openalex `_meta_of` 当前**只取** `open_access.*` 与 `best_oa_location.pdf_url`——**不取** `primary_location.landing_page_url` → 路径 (a) 要拿 abstract_id 须扩这一处解析 | [CODE] `adapters/openalex/parse.py::_meta_of` |
| C9 | openalex 本地预算：默认 `_DEFAULT_DAILY_BUDGET_USD = 0.50`，熔断在**每个内部批次请求前**判 `spent_usd >= budget`；服务端 402 由 `status_code` 精确重分类为 `RATE_LIMITED` | [CODE] `adapters/openalex/adapter.py:71,200-237` |
| C10 | openalex/s2 **capabilities 恒为空集**（`Capability(0)`），ENUMERATE 已收回、不进 pull 六阶段 | [CODE] `adapters/openalex/adapter.py:136`；[aggregators.md §1/§5.3](../design/adapters/aggregators.md) |
| C11 | `ssrn` adapter 已确立「**自己持 ENUMERATE、内部委托另一个 aggregator adapter**」的先例（内部 `CrossrefAdapter` + 后处理增补 `(ssrn, abstract_id)`），且 `domains` 只登记 `api.crossref.org` | [CODE] `adapters/ssrn/adapter.py:104,133-159` |
| C12 | adapter 注册表现 **20 项** entry-points；F5 卡将把 `test_cli_canary.py` 改为**集合等值自断言** → 本 Phase 内任何 adapter 增删都与 F5 有冲突面 | [CODE] `pyproject.toml:31-63`；[plan §4 F5](../plan/phase6-implementation-plan.md) |
| C13 | design/09（**approved**）§2 的 `filters:` 只有 `title_regex_any` / `exclude_regex` / `min_year`——**没有 JEL 过滤键**；T1 的 DSL 模型是 Phase 6 **接口冻结件** | [CODE] [design/09 §2](../design/09-search-filter.md)；[plan §2](../plan/phase6-implementation-plan.md) |

---

## 2. ① repec `aggregator-enrich` 通道评估（检查单 #4 / D-027）

### 2.1 独家增值三项 —— 逐项做「可消费性」核验

D-027 列了三项独家增值。评估的关键不是「RePEc 有没有」（F2/F4 已 [LIVE] 证实有），而是
**「到了我们库里有没有人用得上」**：

| 增值项 | 独家性 | 本项目当前的**消费端** | 判定 |
|---|---|---|---|
| **JEL 分类** | 强（F2：三路皆缺，[LIVE]） | design/09 DSL **无 JEL 过滤键**（C13）；storage 侧可入 `meta`（`PaperStub.meta` 弹性字段）但**无查询/过滤面** | **有货无口**——须先在 design/09（approved）开 `filters.jel_any` 并进 T1 冻结件，才谈得上「Phase 6 DSL 富化」 |
| **wp↔published 版本关联** | 强（F4，[LIVE]） | **`preprint_of` 建边零实现**（C6） | **有货无口**——须先补 merge/repo 侧建边能力（新工作面，design/06 §…有设计、无代码） |
| **CitEc 引文图** | 中（与 s2 `citationCount` 部分重叠） | `meta` 可落；无消费面 | 边际 |
| （非 DOI WP 长尾） | 强 | **不在当前 venue 清单**（D-027 明文） | 出列 |

> **本节结论**：D-027 写的「挂 Phase 6 订阅 DSL 富化」这一去处，在 Phase 6 的**实际接口现实**下并不成立——
> 两项主增值都**缺消费端**，各自要先开一条新的下游通道（DSL 过滤键 / `preprint_of` 建边）。这是本次评估
> 相对 D-027 起草时点的**新事实**（D-027 时 Phase 6 冻结件尚未定形），须原样上报，不粉饰。

### 2.2 接入形态（按 D-027 定位展开）

D-027「定位建议」四要素逐条落到本仓库的具体接缝：

1. **duck-typed `enrich_batch(dois)`（C1）**——形式上完全可复用，`crawler enrich --source repec` **零 CLI 改动**
   即可驱动（C2/C3）。但**语义上与 openalex/s2 不同构**：openalex/s2 是「按 DOI 在线批查」，RePEc 的合规取用面
   （F7）是 **bulk（ReDIF/OAI/Rsync/FTP）**，**没有**「按 DOI 批查」的在线端点（API 是 handle 键、email 门控、
   无搜索、非批量）。⇒ repec 的 `enrich_batch(dois)` 只能实现为
   **「一次性 bulk 快照落盘 → 每次调用做本地 join」**：
   - 新增落盘状态载体：`<config-home>/state/repec/` 下的 ReDIF 快照 + 刷新策略（类比 `openalex-budget.json`
     的家目录状态先例，[CODE] `budget.py` 模块 docstring）；
   - `enrich_batch` 本身**零网络**（快照命中）——这是与既有两源的**本质差异**，属新契约，须裁决（§4 Q4）。
2. **DOI→handle 的 join 键**——F5 说 handle↔DOI 无内建映射，但存在一个**确定性特例**：
   NBER 的 `RePEc:nbr:nberwo:{n}` 与 crossref DOI `10.3386/w{n}` **共用同一个 WP 序号**
   （[LIVE] repec.md §4 同时给出 `RePEc:nbr:nberwo:3210` 与 `10.3386/w3210`），且本仓库已有
   `10.3386/w{n}|t{n}` → series 号的归一解析（[CODE] `adapters/nber/parse.py:29-50`）。
   ⇒ **nber 域内 DOI↔handle 是纯语法映射、零模糊匹配**，这是 MVP 唯一可靠的落点。
   （`t` 系列映射到哪个 series 段、期刊条目怎么 join——**均未核实**，[推断] 不作依据。）
3. **`(repec, handle)` identifier**——`scheme` 无约束（C5），**零 migration**；按 D-027 明文
   **非跨源合并锚点**（handle 仅 RePEc 内唯一，跨源仍靠 DOI），实现上就是「随 stub 携带、不参与强合并判定」
   ——注意 `MergeEngine` 的强合并是**按 (scheme,value) 命中**的，`(repec,…)` 一旦入库就天然成为
   *RePEc 内部*的幂等锚点，这与「非跨源锚点」不冲突（跨源锚仍是 DOI），实现时须在注释里写清，防误读。
4. **字段级只补不覆盖**——由 `SOURCE_PRIORITY` 天然实现，但 **repec 不在六枚举闭表内 → `ingest` 直接
   `ValueError`**（C4）。⇒ **必须扩位，且该表由 D-021 冻结 → 须新 ADR**。扩位方案见 §4 Q3。
5. **bulk / 零 HTML**——F7 的官方要求与 AC-0.3（robots+ToS）方向一致，实现上以 ReDIF/OAI 为准、
   **绝不解析 ideas/econpapers 的 HTML 条目页**（哪怕 robots 允许）。这条要写进卡的 DoD。

### 2.3 可寻址集合：谁真正拿得到增值

| 语料 | 规模 | 在 RePEc？ | DOI→handle join | 结论 |
|---|---|---|---|---|
| **NBER WP** | **35,976** DOI（F8） | 是（`nbr:nberwo`，F1/§6） | **确定性语法映射**（§2.2-2） | **MVP 唯一落点** |
| **SSRN** | 1,414,774 DOI（F9） | **否**（F6，[LIVE]） | — | **结构性 0** |
| AEA / Econometric Society 等已刊期刊 | 58 venue 中的 econ 刊 | 未核实 | 未核实（无语法映射线索） | 出列 MVP，待核实 |
| 非 DOI WP 长尾 | `[UNRESOLVED②]`（规模未知） | 是 | 无 DOI 可 join（须反向枚举） | D-027 明文出列 |

⇒ **可寻址集合 ≈ 3.6 万篇 NBER WP**（且 JEL 只在其中偏近年的一段有值，F3）。作为对照：同一 Phase 的
ssrn 语料是 141 万篇——**repec enrich 的覆盖面比 ssrn 小两个数量级**。

### 2.4 实现成本估算

| 面 | 内容 | 量级 |
|---|---|---|
| 新模块 | `adapters/repec/{__init__,adapter,parse}.py` + ReDIF 文本格式解析层（**不能复用 `_oai.py`**——ReDIF 不是 OAI 信封；除非走 OAI-PMH 通道，但其活性 `[UNRESOLVED①]`） | ≈ 400–550 行 src |
| 新落盘契约 | `<config-home>/state/repec/` 快照 + 刷新/失效策略 + 大小护栏（nbr 单 series ≈ 3.6 万条记录，字节量级**未核实**） | 新子系统（**非**「一个 enrich 分支」） |
| 冻结件改动 | `merge.py::SOURCE_PRIORITY` 扩位（D-021 冻结 → **新 ADR**）；`pyproject.toml` entry-points +1（**与 F5 的 canary 集合等值断言撞车**，C12） | 2 处，均需协调 |
| CLI | **零改动**（C2/C3 已验证通用装配路径） | 0 |
| venue 触点 | **零**——repec 不是任何 venue 的 `metadata_source`/`fulltext_source`（同 openalex/s2 不进 registry 路由，[CODE] `cli.py::_prepare_enrich_source` docstring）；`venues/econ/nber.yaml` 的 N-5 注记（「唯一已知源 RePEc nbr:nberwo ReDIF」）落地后可回改，属文档面 | 0 代码 / 1 文档 |
| 测试 | ReDIF 解析 fixture（正常/缺 JEL/畸形/多记录）、DOI→handle 映射矩阵、快照命中与失效、`enrich_batch` 零网络断言、merge 只补不覆盖的集成 | ≈ 25–35 例，覆盖 ≥95% |
| 在线 | bulk 取回 1–3 请求（快照）；**实现前**须先做 §2.5 探针 | ≤6（探针）+ ≤3（实现期） |

**工时量级**：一张 **opus 档卡**，与 Phase 5 的 T4（ssrn）同量级或略大（多出「落盘快照契约」一项）。

### 2.5 前置未核实事实 —— go/no-go 的真正闸门

| # | 未核实项 | 为什么是闸门 | 探针动作（≤6 请求） |
|---|---|---|---|
| **P1** | **JEL 是否出现在 bulk（ReDIF）面** | repec.md 的 JEL 证据（F2）**全部来自 IDEAS 的 HTML 条目页**；而取用红线是「零 HTML、只走 bulk」（F7）。若 JEL 只在前端渲染而不在 ReDIF 记录里，**整个 JEL 用例在合规路径上不成立** | 取 `nbr` archive 模板 → 取其 ReDIF series 文件 → 检 1 条近年记录是否含 JEL 分类字段（字段名以实际记录为准，**不要凭 [推断] 的字段名写代码**） |
| **P2** | OAI-PMH endpoint 活性与 flaky 程度（`[UNRESOLVED①]`） | 决定增量刷新走 OAI 还是「定期重取 bulk」 | 1 次 `Identify`（若 P1 已能确定 bulk 面可用，本项可降级为实现期项） |
| **P3** | **JEL 历史覆盖率**（`[UNRESOLVED④]`，F3 已知 1989 无、2026 有） | 决定增值的**实际篇数**：若只覆盖近 10 年 ≈ 1.2–1.5 万篇而非 3.6 万 | 抽 3 个年代样本（如 w10000/w20000/w30000）看 JEL 有无 |

> 三项都在 `ideas.repec.org` / archive ReDIF 面上，**本机可达**（F16），不触任何 CF 域。

### 2.6 建议：**再缓**（Phase 6 不立实现卡）+ 立探针

**建议：再缓。** 五条理由，按权重：

1. **消费端缺位**（§2.1）：两项主增值在本项目里**都还没有出口**——JEL 要先改 design/09（**approved**）新增过滤键
   并进 T1 冻结件（T1 是 W0 关键路径、下游 6 卡消费），`preprint_of` 要先补建边代码（C6）。在 Phase 6 主线
   正铺开时往冻结件塞增量，是本计划 §5 明确要避的合并洪峰风险。
2. **前置事实未核实**（§2.5 P1 尤其致命）：JEL 的全部实证来自 HTML 前端，而合规路径只允许 bulk。
   在这一点澄清前立实现卡，等于把「Phase 2 REJECT / T1 `facet=created:*` 400」两次教训再犯一遍
   （[phase5-report §4 事件①](../reports/2026-07-24-phase5-report.md)）。
3. **可寻址集合窄**（§2.3）：≈3.6 万篇 NBER（其中 JEL 覆盖偏近年），且**最大宗的 SSRN 结构性拿不到**（F6）。
4. **冻结件与并行冲突成本**（§2.4）：`SOURCE_PRIORITY` 扩位须新 ADR（D-021 冻结）；entry-points +1 与
   F5 的 canary 集合等值断言在**同一 Phase 内**撞车。
5. **形态不同构**（§2.2-1）：它不是「再加一个 openalex/s2 式 enrich 分支」，而是「bulk 快照 + 本地 join」
   的新子系统 + 新落盘契约——按 opus 档预算，它与主线争资源而不服务任何 AC-6.x。

**公平呈现反方**（不藏）：
- `venues/econ/nber.yaml` 的 N-5 注记已由 controller 令把该缺口指向 Phase 6，「再缓」是对该注记的**推迟**，
  须在裁决里显式承认并回改注记指向（§4 Q1 附带动作）。
- 技术上 MVP 并不难：DOI↔handle 是纯语法映射，无模糊匹配风险；若 §2.5 三项全绿，一张 opus 卡即可闭合。
- JEL 对经济学检索确是**核心维度**，长期价值不因本次推迟而减损。

**因此建议的完整形态**：
> **再缓实现卡 + 立即立「≤6 请求前置核实探针」**（挂 §3 预算表「机动 ≤10」行，不占 M1-a~d）。
> 探针结论回填 repec.md `[UNRESOLVED①④]` 与本文档 §2.5；**三项全绿** → §2.7 任务卡草稿可直接并入
> **Phase 7 首批**（或 P6 末 stretch，由 fable 按波次余量裁）；**P1 红**（JEL 不在 bulk 面）→
> **JEL 用例在合规路径上不成立，repec 通道整体永久出列**，回改 D-027 影响段与 nber.yaml N-5。

### 2.7 若立卡：任务卡草稿（格式对齐 plan §4）

> 编号留空待 fable 指派（建议 `P7-T1` 或 `P6-R2a`）。**前置条件：§2.5 探针三项全绿。**

#### Rx repec aggregator-enrich 通道（`enrich/repec-jel`，**opus/opus**，依「探针全绿」+ 新 ADR）

- **范围**：新增 `src/paper_crawler/adapters/repec/{__init__,adapter,parse}.py`——
  ①**bulk 快照**：按 `nbr` archive 模板给出的 ReDIF 地址取回 `nberwo` series 记录，落
  `<config-home>/state/repec/`（含取回日期 + 记录数 + 校验；**零 HTML 解析**，仅 ReDIF/OAI 面）；
  ②**ReDIF 解析层**：`Template-Type` 记录切分 + 字段抽取（handle / title / authors / year / **JEL 分类** /
  "Published in" 版本关联串），字段名以探针实测为准；
  ③**duck-typed `enrich_batch(dois)`**：`10.3386/w{n}|t{n}` → `RePEc:nbr:nberwo:{n}` 语法映射
  （复用 `adapters/nber/parse.py` 的 series 号归一）→ 快照本地 join → 产 `PaperStub`
  （`identifiers=((doi,…),(repec,handle))`，`meta` 携 `jel`/`published_in`）；**本方法零网络**；
  ④`pyproject.toml` entry-points 注册 `repec`；⑤`merge.py::SOURCE_PRIORITY` 扩位（依 ADR 裁决值）。
- **已裁决歧义**（待 fable 在 §4 拍板后填）：① `SOURCE_PRIORITY` 位次（Q3）；②快照刷新策略与失效语义（Q4）；
  ③`(repec,handle)` 明确**非跨源合并锚点**、跨源锚仍为 DOI（D-027 原文）；④非 DOI WP 长尾**不在本卡**；
  ⑤JEL **不进** DSL 过滤键（Q5 若裁「defer」则本卡只入 `meta`，检索面另卡）。
- **DoD**：①`crawler enrich --source repec` 对含 `10.3386` DOI 的库跑通，JEL 落 `meta` 且
  **对 crossref 既有字段零覆盖**（集成断言）；②快照缺失/过期时**响亮失败**（不静默空结果——审计 S1 原则）；
  ③`enrich_batch` 全程零网络有专测（socket 猴补看守）；④HTML 面零请求有专测（domains 白名单断言）；
  ⑤覆盖 ≥95%。
- **测试**：unit（ReDIF 解析 4 fixture + DOI↔handle 映射矩阵 ≥8 例 + 快照失效）；
  integration（走真 sqlite 验只补不覆盖 + `(repec,handle)` 幂等）；contract（`EnrichmentSource` 协议一致性）。
- **分支**：`enrich/repec-jel`。**模型**：执行 **opus**（新落盘契约 + 冻结表改动）/ 审查 **opus**。
- **不在本卡**：JEL 检索面（DSL 过滤键）、`preprint_of` 建边、非 DOI 长尾枚举、期刊条目 join。

---

## 3. ② ssrn 覆盖候补 ladder 评估（检查单 #1 / [ssrn.md §9.1](../design/adapters/ssrn.md)）

### 3.1 口径澄清：86.9% 是什么、不是什么

- **是**：OpenAlex source `S4210172589` 收录的 works 中「带 DOI」的比率（F10），即
  **crossref 前缀枚举相对 OpenAlex 宇宙的覆盖率**。
- **不是**：crossref 相对「SSRN 真实全库」的覆盖率——后者需要 SSRN census，**无合规路径**
  （F13）。ssrn.md §9.1 已把这条写成「固有天花板」，本评估**沿用不放宽**。
- **因此**：ladder 的三条路径里，只有 (a) 是在**同一把尺子**（OpenAlex 宇宙）上把 86.9% 往 100% 推；
  (c) 才是试图换一把尺子（绝对覆盖），而那把尺子被红线锁死。这决定了整个推荐序。

**缺口的量化体量**（点估计 + 95%±3% CI 传播）：

| 量 | 点估计 | CI 区间 | 推导 |
|---|---|---|---|
| 无-DOI 切片占比 | **13.1%** | 10.1%–16.1% | 1 − 86.9%（F10） |
| 无-DOI works 绝对量 | **≈ 21.4 万** | 16.5 万–26.3 万 | 13.1% × 1,632,966（F9） |
| 其中 econ/fin 相关 | **≈ 6.4 万** | — | × 29.7%（F11）；**假设无-DOI 切片与全库同领域分布** → [推断]，M1-d 顺带可验 |
| 日新增无-DOI works | **≈ 90 篇/日** | — | 250K/年（F12）÷365 × 13.1% |
| 其中 econ/fin（订阅实际可见增量） | **≈ 27 篇/日** | — | × 29.7%（F11） |

### 3.2 路径 (a)：OpenAlex 补枚举无-DOI works

**能力面的关键澄清（本次评估的主要发现之一）**：检查单 #1 与 ssrn.md §9.1 都写「该能力已收回
`ENUMERATE`（aggregators §1）+ 信用计费，需重评能力面」——**这个顾虑可以整体绕开**：

- ENUMERATE 能力**不需要还给 openalex**。`ssrn` adapter **自己持有 ENUMERATE**，并且**已经**在内部
  委托另一个 aggregator adapter（`CrossrefAdapter`）完成实际取数（C11）。
  ⇒ 路径 (a) 的正确形态是**在 `ssrn` adapter 内新增第二条内部通道（openalex 切片）**，
  与既有 crossref 通道**结构对称**；`openalex` 的 `capabilities = Capability(0)` **一字不改**（C10），
  aggregators.md §1 的分工表**零改动**，D-005/D-021 均不受影响。
- 换言之：「收回 ENUMERATE」这一顾虑**在本形态下不成立**，不构成 (a) 的阻碍。

**信用计费约束（逐项量化，F14 + C9）**：

| 项 | 数值 | 推导 |
|---|---|---|
| 单页成本 | 1 credit = **$0.0001** | F14（filter 查询 1 credit；`meta.cost_usd:0.0001` [LIVE]） |
| 页大小 | ≤200 works/页 | [DOC] aggregators §5.3 |
| **历史 backfill 总量** | **≈ 1,070 页 = 1,070 credits ≈ $0.107** | 21.4 万 ÷ 200 |
| 匿名日配额下的耗时 | **2 天**（1000 credits/天） | F14 |
| free key 下的耗时 | **单日**（10000 credits/天） | F14 |
| **日增量成本** | **≈ 1 页/日 ≈ $0.0001/日** | 90 篇/日 ÷ 200 |
| 与本地预算护栏的关系 | 默认 `$0.50/日`（C9）＝ **5000 credits 等价**，但**匿名硬配额只有 1000 credits（$0.10 等价）** ⇒ **backfill 会先撞服务端 402、而非本地预算熔断** | C9 + F14 |

> **护栏错配 finding**：匿名场景下服务端 402 会**先于**本地 `daily_budget_usd` 触发。行为本身正确
> （`adapter.py:231` 已把 402 精确重分类为 `RATE_LIMITED`＝「明日恢复」同语义），但**报告语义不同**
> （用户看到的是服务端拒绝而非「预算用尽」）。⇒ backfill 卡应**要求配置 free key**，或显式把该场景写进
> 卡的预期行为，不要让它以「看起来像故障」的形式出现（§4 Q12）。

**未知项（决定 (a) 的入库形态，必须 M1-d 供数）**：

| # | 未知项 | 为什么决定成败 | 状态 |
|---|---|---|---|
| **U1** | `filter=…,has_doi:false` 是否被 OpenAlex 接受（不接受则只能全量枚举后本地筛：1,632,966÷200 = **8,165 页 ≈ $0.82**，成本涨 **7.6 倍**且超默认日预算） | 决定 (a) 是否经济 | `[PENDING M1-d]` |
| **U2** | 无-DOI works 的 `primary_location.landing_page_url` 能否正则出 `abstract_id`（`papers.ssrn.com/…abstract_id={id}`） | **决定 identifier 强度**：能 → 产 `(ssrn, abstract_id)` 强锚点、与 DOI 侧记录天然强合并；不能 → 只有 `(openalex, W…)` 孤儿锚点，日后 DOI 补登记时**只能靠弱信号 title 匹配** → 制造 `candidate_duplicate` 噪声 | `[PENDING M1-d]` |
| **U3** | 该切片的 `title`/`authors`/`publication_date` 非空率 | 决定 stub 可构造率与增量窗可用性（`from_created_date` 是 Premium 门控 F14 ⇒ 增量只能用 `from_publication_date`） | `[PENDING M1-d]` |
| **U4** | 切片内的**非-SSRN 杂质率**（DOI 侧已见 5/869=0.58% 前缀非 10.2139，F10 细分） | 决定是否需要与 `skipped_non_ssrn` 同款护栏 | `[PENDING M1-d]` |
| **U5** | 切片的领域分布是否与全库同分布（§3.1 表的 [推断] 假设） | 只影响体量估计精度，不影响 go/no-go | `[PENDING M1-d]`（顺带） |

**先行判定规则**（M1-d 数据到位后**机械读出**，不需重评）：

| U2 实测（abstract_id 可提取率） | 判定 |
|---|---|
| **≥ 90%** | (a) **推荐立卡**：产 `(ssrn, abstract_id)` 强锚点入库；不可提取的少数按 `skipped_*` 观测计数、不入库 |
| **50%–90%** | (a) **分层立卡**：可提取者入库、不可提取者**只计数不入库**（避免孤儿 `(openalex,W…)` 制造 candidate 噪声）；覆盖率提升按可提取比例如实标注 |
| **< 50%** | (a) **降级为 census/计数用途**，不作入库通道；SSRN 覆盖缺口如实标注为**当前不可闭合**（三路径全灭），写进 Phase 6 已知限制 |
| U1 为「不接受」（400） | 无论 U2 如何，(a) 判**不经济**（$0.82/次 + 8,165 页），按 <50% 分支处理；同时把该 400 作**活体哨兵 XFAIL** 存档（沿 T1 `facet=created:*` 判例） |

**实现面（若立卡）**：

| 面 | 内容 | 量级 |
|---|---|---|
| 新代码 | `adapters/ssrn/openalex_channel.py`（内部 openalex 切片通道：分页 + budget 记账 + 停止条件）+ `adapters/openalex/parse.py::_meta_of` 扩取 `primary_location.landing_page_url`（C8）+ ssrn 侧 landing→abstract_id 正则（复用 `parse.augment_with_ssrn_id`，C11） | ≈ 150–220 行 |
| 冻结件 | **零**（openalex capabilities 不动、SOURCE_PRIORITY 不动、CLI 不动） | 0 |
| 红线 | 仍**零 `*.ssrn.com` 接触**（AC-5.1a③ 不破）；新增 domain 仅 `api.openalex.org`（robots 404 无限制，F15） | 合规无新增风险 |
| 与 Phase 6 主线的接缝 | 动 `ssrn` 的 ENUMERATE 结果集 ⇒ **影响 AC-6.3/AC-6.4 的基准集**（T2/T3/T9）；须排在 T5 合并之后 | 波次约束 |
| 测试 | 切片分页 fixture、budget 熔断、landing→abstract_id 矩阵、杂质护栏、与 crossref 通道的**去重等价性**（同一 work 两通道各来一次 → 单 paper） | ≈ 15–20 例 |

### 3.3 路径 (b)：RePEc 交叉核对 —— **出列（结构性无效）**

- **[LIVE 2026-07-24]**：`ideas.repec.org/archives.html` 442KB 主表**全表无 "ssrn" 串**；SSRN 属 Elsevier
  商业源、非 RePEc 志愿网络成员（F6）。repec.md §6 与 D-027「附带事实」段均已明写
  「**SSRN 覆盖只能靠 `ssrn` 专源，RePEc 补不了**」。
- ⇒ 用 RePEc 交叉核对 SSRN 覆盖，**可闭合缺口恒等于 0**。它既不能发现 SSRN 漏收的 work，
  也不能判断某个 SSRN abstract_id 是否存在。
- **它能做的另一件事**（不要混淆）：RePEc/NBER 提供的是**另一个语料**（econ WP 长尾）的覆盖，
  即「用别的源补经济学 WP 的整体视野」，而**不是**「补 SSRN 这一个源的覆盖缺口」。前者的价值评估
  属 §2（enrich）与未来 venue 清单扩张议题，**不属本 ladder**。
- **建议**：把检查单 #1 的 (b) 项正式**改判为「结构性无效、出列」**，并回填
  [ssrn.md §9.1](../design/adapters/ssrn.md) 的候补阶梯记录与 phase5-report §6 检查单 #1 注记
  （§4 Q7）。这是一次**如实纠正**：检查单起草时把「RePEc/NBER 交叉核对」与 (a)(c) 并列，
  与同一批 [LIVE] 勘察的 F6 事实相互矛盾。

### 3.4 路径 (c)：有限度 SSRN 浏览页 census —— **否决**

三重出局，任一条即足够：

1. **红线**（AC-0.1/0.3 + D-029 §BLOCKED 硬边界，F13）：`*.ssrn.com` 已判 BLOCKED
   （2026-07-20 站点 CF 挑战 403「verify you are human」）；红线要求**遇挑战即停、不对抗**。
   任何「有限度浏览页 census」都是对已判 BLOCKED 域的重新发起。
2. **合规基础缺失**：SSRN `robots.txt` 的 **Disallow 路径面至今未取得**（F13，两次尝试均 TLS 层失败）
   ⇒ 连「哪些路径可爬」都无法确立，**无法构造合规的 census 方案**。
3. **环境结构性不可执行**：本机对 CF 前置域在 TLS 握手层 reset（[LIVE] curl/httpx 双实测；
   浏览器上下文同走本机代理 → [推断] 同样受阻，ssrn.md §11.3）⇒ 即便红线放行也**跑不通一次**。
   这与 D-029 采纳案 B 的决定性理由同源（「shipping 无法验一次的代码」违项目纪律）。

- **建议**：**永久出列**，措辞写死为「除非①站点侧挑战门形态改变 ②本机网络环境改变 ③重新取得
  robots Disallow 面并确认允许——三者同时成立，且即便如此也仅限**用户发起的人工**核验、非自动化
  census」。ssrn.md §9.1 候补阶梯记录同步改写（§4 Q8）。

### 3.5 量化依据表与推荐序

| 维度 | **(a) OpenAlex 无-DOI 补枚举** | (b) RePEc 交叉核对 | (c) SSRN 浏览页 census |
|---|---|---|---|
| **可闭合的缺口** | 13.1% 切片 ≈ **21.4 万 works**（OpenAlex 宇宙内 86.9% → ~100%） | **0**（F6，结构性） | 理论上是唯一能测**绝对**覆盖的路径 |
| 订阅可见的日增量 | ≈ **27 篇/日**（econ/fin 过滤后） | 0 | — |
| 一次性成本 | **1,070 页 / 1,070 credits / $0.107**（匿名 2 天，free key 单日） | — | 不可执行 |
| 增量成本 | ≈ 1 页/日 ≈ **$0.0001/日** | — | — |
| 合规风险 | **零**（`api.openalex.org` robots 404 无限制，F15；零 `*.ssrn.com` 接触不破 AC-5.1a③） | 零（bulk 面） | **红线**（AC-0 + D-029 BLOCKED，F13） |
| 环境可行性 | **可**（非 CF 域，历次 [LIVE] 全程可达） | 可（F16） | **不可**（CF 域 TLS 阻断 ×2 [LIVE]） |
| 冻结件影响 | **零**（openalex capabilities 不动，ENUMERATE 留在 ssrn，§3.2） | `SOURCE_PRIORITY` 扩位 + 新 ADR | — |
| 实现量级 | ≈ 150–220 行 + 15–20 测试例 | 见 §2.4（一张 opus 卡） | — |
| 前置未知 | U1–U5 `[PENDING M1-d]`（≤5 请求可全清） | P1–P3（≤6 请求） | robots Disallow 面**取不到** |
| 阻塞的 AC | 无（AC-6.x 不依赖）；但会**改变** AC-6.3/6.4 的基准集 | 无 | 无 |
| **推荐** | **① 推荐（条件立卡）** | **② 出列（结构性无效）** | **③ 否决（永久）** |

**推荐序一句话**：**(a) 条件立卡 ≫ (b) 出列 ≫ (c) 否决**——(a) 的成本（$0.107 一次性 / $0.0001 日）
与合规风险（零）都低到可忽略，唯一的真问题是 identifier 强度（U2）；(b) 与 (c) 不是「排在后面」，
而是**分别因结构性无效与红线+环境双重出局而离开阶梯**。

### 3.6 M1-d 供数需求（≤5 请求，落在 §3 预算表 M1-d ≤10 行内）

> 建议 M1-d 执行者按此清单取数并回填本节表格；**全部落在 `api.openalex.org` 单域**，串行 ≥1.2s，带 `mailto`。

| 步 | 请求 | 取什么 | 回填 |
|---|---|---|---|
| 1 | `GET /works?filter=primary_location.source.id:S4210172589,has_doi:false&per-page=1` | ①该 filter 是否 200（U1）②`meta.count`＝无-DOI 切片**真实绝对量**（替换 §3.1 的推算值） | U1 / §3.1 表 |
| 2 | 同上 + `&sample=200&seed=42&per-page=200&select=id,doi,title,publication_date,authorships,primary_location` | 200 条样本 | U2–U5 |
| 3 | （本地统计，零请求） | `primary_location.landing_page_url` 命中 `abstract_id=(\d+)` 的比率（U2）；title/authors/publication_date 非空率（U3）；landing 域非 `*.ssrn.com` 的比率（U4 杂质）；`primary_topic.field` 分布（U5） | 判定规则表 |
| 备 | 若步 1 返 400（`has_doi` 非法） | 记为 U1=否 → 直接走「<50% 分支」；**该 400 存档为 XFAIL 活体哨兵** | §3.2 判定规则 |

**填表位**（M1-d 到位后直接改这三格）：

| 指标 | 实测 | 判定 |
|---|---|---|
| U1 `has_doi:false` 合法性 | `[PENDING M1-d]` | — |
| 无-DOI 切片 `meta.count` | `[PENDING M1-d]`（推算 ≈21.4 万，CI 16.5–26.3 万） | — |
| **U2 abstract_id 可提取率** | `[PENDING M1-d]` | **→ §3.2 三分支判定** |
| U3 title/authors/pub_date 非空率 | `[PENDING M1-d]` | — |
| U4 非-SSRN 杂质率 | `[PENDING M1-d]`（DOI 侧对照 0.58%） | — |

### 3.7 若立卡：任务卡草稿（格式对齐 plan §4）

> **前置条件**：M1-d 判定落 §3.2 的「≥90%」或「50–90%」分支。**波次约束**：须排在 **T5 合并之后**
> （动 ssrn ENUMERATE 结果集，与 T2/T3/T9 的 AC-6.3/6.4 基准集有语义耦合）。

#### Ry ssrn 无-DOI 切片补枚举通道（`feat/ssrn-openalex-slice`，**opus/opus**，依 T5 合并 + M1-d 达标）

- **范围**：`adapters/ssrn/openalex_channel.py`——`ssrn` adapter 的**第二条内部通道**
  （结构对称于既有内部 `CrossrefAdapter`，C11）：`filter=primary_location.source.id:S4210172589,has_doi:false`
  + `from_publication_date` 增量窗（**不可用 `from_created_date`**——Premium 门控 F14）+ `per-page=200` cursor 深翻；
  逐页复用 `openalex/parse.py::parse_works_batch`（C7）产 stub、`openalex/budget.py` 记账熔断（C9）；
  `openalex/parse.py::_meta_of` 扩取 `primary_location.landing_page_url`（C8）；ssrn 侧
  landing→abstract_id 正则 + `augment_with_ssrn_id` 增补强锚点；杂质护栏同款 `skipped_non_ssrn` 观测。
- **已裁决歧义**（待 fable 拍板后填）：①入库分层阈值取 §3.2 三分支（Q10）；②openalex `capabilities`
  **保持空集不动**，ENUMERATE 留在 ssrn（§3.2）；③历史 backfill **不在本卡**（本卡只做增量窗；
  backfill 作一次性运维动作单独裁，Q9）；④backfill/大窗场景要求配置 free key（Q12）。
- **DoD**：①同一 work 分别经 crossref 通道与 openalex 通道到达 → **单 paper**（identifier 去重专测）；
  ②不可提取 abstract_id 的记录按裁定分支处理且**有观测计数**（不静默丢弃——审计 S1 原则）；
  ③预算熔断（本地 + 402）各有专测；④仍**零 `*.ssrn.com` 请求**（domains 白名单断言，AC-5.1a③ 回归）；
  ⑤`ssrn` 覆盖率提升按实测比例如实回填 ssrn.md §9.1，**不宣称绝对覆盖**（固有天花板不消解）。
- **测试**：unit（切片分页 fixture / landing→abstract_id 矩阵 ≥8 例 / 杂质护栏）；
  integration（双通道去重等价、budget 熔断）；contract（ENUMERATE 结果集形状稳定）。
- **分支**：`feat/ssrn-openalex-slice`。**模型**：执行 **opus** / 审查 **opus**（动 ENUMERATE 结果集 + 预算面）。
- **不在本卡**：历史 21 万条 backfill 的实际执行、SSRN 绝对覆盖率的重新量化、模式 B 全文。

---

## 4. 交裁决问题清单（fable 拍板）

> 一行一个决策点，附起草人倾向。**Q1/Q7/Q8/Q9 是主裁决，其余为其从属细则。**

| # | 决策点 | 起草人倾向 |
|---|---|---|
| **Q1** | ① repec 通道：Phase 6 **立实现卡** vs **再缓** | **再缓**（§2.6 五条）；附带动作＝回改 `venues/econ/nber.yaml` N-5 注记的指向 Phase，不留悬空承诺 |
| **Q2** | 是否批准 §2.5「≤6 请求前置核实探针」占用 §3 预算表**机动 ≤10** 行 | **批准**——P1（JEL 是否在 bulk 面）是 go/no-go 真闸门，一次问清比再评估一轮便宜 |
| **Q3** | 若日后立卡：`SOURCE_PRIORITY`（D-021 冻结）扩位方案 | **重编号**为 `official 6 / crossref 5 / dblp 4 / openalex 3 / s2 2 / repec 1 / heuristic 0`（repec 取最低非-heuristic 位，保严格全序）；**须新 ADR** 记 supersedes D-021 §3 位次表 |
| **Q4** | 是否接受 repec 的「bulk 快照 + 本地 join」**新落盘契约**（`<config-home>/state/repec/`），及其刷新策略进 ADR | **接受但入 ADR**——它与 openalex/s2 的「在线批查」不同构（§2.2-1），不写进决策记录会成为隐性架构债 |
| **Q5** | JEL 是否进 design/09（**approved**）的 DSL 过滤键（新增 `filters.jel_any`） | **本 Phase 不动**——T1 冻结件在 W0 关键路径上；JEL 先只入 `meta`，检索面随 repec 卡之后另立 |
| **Q6** | `preprint_of` 建边（C6，代码零实现）是否本 Phase 补 | **否**——与 repec 一同 defer；但建议把「设计有、代码无」这一缺口正式登记进 Phase 7 检查单（现仅隐含在 D-007/design/06） |
| **Q7** | ② 路径 **(b) RePEc 交叉核对**正式改判「结构性无效·出列」，并回填 ssrn.md §9.1 + phase5-report §6 #1 注记 | **同意**——F6 [LIVE] 与检查单原表述直接冲突，属如实纠正 |
| **Q8** | ② 路径 **(c) 浏览页 census** 正式**永久否决**（措辞按 §3.4 三条件写死） | **同意**——红线 + 合规基础缺失 + 环境不可执行，三重出局 |
| **Q9** | ② 路径 **(a)** 是否立卡；若立，排 **W3（T5 合并后）stretch** 还是 **defer Phase 7 首批** | **条件立卡**：M1-d 落「≥90%」→ 排 W3 stretch（波次有余量才插）；落「50–90%」→ defer P7；落「<50%/U1 否」→ 不立卡，写进已知限制 |
| **Q10** | (a) 的入库分层阈值（§3.2 三分支 90%/50%）是否采纳为正式判据 | **采纳**——把「孤儿 `(openalex,W…)` 锚点会制造 candidate_duplicate 噪声」这一代价显式定价，而非事后发现 |
| **Q11** | 历史 backfill（1,070 页 / $0.107）作**卡内动作**还是**一次性运维动作** | **一次性运维动作**（卡只做增量窗）——它是数据补齐而非代码能力，不该占卡的 DoD |
| **Q12** | 匿名 1000 credits/日（≈$0.10）先于本地 `$0.50` 预算触顶（§3.2 护栏错配）：调低默认值 vs backfill 场景要求 free key | **要求 free key，不动默认值**——默认值服务的是日常 enrich 小批量，为一次性 backfill 改全局默认是错配 |
| **Q13** | 本文档定稿去向：`draft → approved` 后是否①回填 ssrn.md §9.1 / repec.md §7 ②新增一条 ADR 记录「(b)(c) 出列 + (a) 排序」 | **两项都做**——ladder 的三路径判定是**跨文档的方向性结论**，只留在 research/ 会在 Phase 7 被重新讨论一遍 |

---

## 5. 修订记录

| # | 日期 | 修订 | 依据 |
|---|---|---|---|
| 1 | 2026-07-26 | 初稿（R2 起草，opus）：① repec enrich 评估（建议再缓 + 探针 + 任务卡草稿）；② ssrn ladder 三路径评估（推荐序 a≫b 出列≫c 否决 + 量化表 + M1-d 供数清单 + 任务卡草稿）；§4 交裁决 13 项 | 既有 [LIVE] 勘察（repec.md / ssrn.md / nber.md / aggregators.md）+ 本仓库源码事实（C1–C13）；**零网络** |
