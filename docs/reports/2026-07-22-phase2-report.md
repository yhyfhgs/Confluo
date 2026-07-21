# Phase 2 阶段报告 — Open-Access MVP（2026-07-22）

> **草稿**，格式仿 [2026-07-21-phase1-report.md](../reports/2026-07-21-phase1-report.md)，待主
> agent 终验后落盘 `docs/reports/`。
> 判定依据：[development-plan §Phase 2](../plan/development-plan.md)、
> [acceptance-criteria AC-2/AC-0](../testing/acceptance-criteria.md)、
> [验收汇总记录（草稿）](phase2-acceptance-draft.md)。
> 代码版本：main `c157123`（Stage B 6/6 全部合并）；tag `phase-2` 待终验后打。

## 1. DoD 判定

development-plan.md Phase 2 DoD 原文："验收场景 AC-2.x 全过……；每个 adapter 有离线 fixture
测试 + 1 个限量在线冒烟；canary 监控注册。"

| DoD 项 | 判定 | 证据 |
|---|---|---|
| open_access adapter 上线 | **PASS**（7/7，8→7 因 D-020 acm_dl 出列） | `pyproject.toml` entry-points 7 条；main 1629 passed |
| AC-2.x 全过 | **PARTIAL** | AC-2.3 PASS（转正）；AC-2.1/2.2 离线 PASS+在线待 token；AC-2.4/2.5 离线 PASS+在线留待；AC-2.6 deferred（D-020，明确不计入判定）——详见验收汇总 |
| 每 adapter 离线 fixture 测试 | **PASS**（7/7） | 各 adapter fixture 回放全绿，覆盖率 96~100%（本次亲跑复核） |
| 每 adapter 1 个限量在线冒烟 | **PARTIAL**（1/7 committed） | 仅 arxiv 有 `tests/online/test_arxiv_smoke.py`；openreview BLOCKED（token）；pmlr/cvf/acl_anthology/neurips_proceedings 以审查期限量真实交叉验证替代（未 committed）；aaai_ojs 情况 ledger 未逐条明记——**口径待终验裁决**（见 §6） |
| canary 监控注册 | **PASS**（7/7） | 7 个 adapter healthcheck 均已实现（非 `NotImplementedError` 占位），可经 `crawler canary` 探活 |
| 核心覆盖率 ≥80% 不回退 | **PASS** | 99.32%（门禁 80%），`make check` 本次终验前亲跑复核全绿 |
| adapter 解析器覆盖 ≥90% | **PASS** | 7 个 adapter 包实测 96~100%（openreview 96%，未覆盖行为惰性 client 构造等防御性分支，非在线路径缺口；其余均 ≥99%） |

## 2. 验收汇总

详见 [phase2-acceptance-draft.md](phase2-acceptance-draft.md)（草稿，待转正）。摘要：

- **AC-2.3（arxiv）：PASS，已转正**——D-018 双层证据齐备，首次真实网络任务（7 请求，全程合规）。
- **AC-2.1/2.2（openreview）：离线层 PASS，在线层 BLOCKED 待用户 OpenReview 免费账号 token。**
- **AC-2.4（cvf）/AC-2.5（acl_anthology）：离线层 PASS（AC-2.5 含日志判据），在线层留待**（非
  blocked，Phase 2 范围内未排入 committed 在线冒烟）。
- **AC-2.6（acm_dl）：deferred（D-020），Phase 4 重评**，不计入 Phase 2 判定；范围 8→7。
- **pmlr/neurips_proceedings/aaai_ojs（无专属 AC-2.x）**：走通用 DoD——fixture 回放全绿 + canary
  注册 + D-019 锚点结构就位（**正式 count 核准 pending**）。
- **AC-0 红线**：本报告起草期未发现违反证据（限速三域共享 1req/3s 桶、UA 全程携真实 mailto、
  D-020 已因红线优先主动收窄范围而非违反后补救）——**逐条系统性复核仍需终验 agent 按
  phase1-report 先例对 git 全历史+日志做正则扫描**，本报告不代为该项终验。

## 3. 交付清单

development-plan §Phase 2 范围逐项：

| 范围项 | 交付 |
|---|---|
| Stage A · 核心硬化（T1） | `fetch_log.url` 落库前 redact；`repo.finalize_fetch()` 组合事务（mark_asset+add_fetch_log 同事务，消除 Phase 1 report §5 移交的"已知窗口"）；mock 两处裸 `ValueError`→`CrawlerError` |
| Stage A · 共享 HTTP 客户端（T2） | `src/paper_crawler/http.py`（httpx 落地，D-017）——统一错误分类映射、Retry-After 解析、流式下载、`extra_headers`/`rate_limiter` 纯附加扩展点（后随 openreview/C4 落地） |
| Stage A · 在线测试基建（T3） | `online` pytest marker（默认排除）、`tests/online/` + 预算护栏 fixture、`crawler canary` 健康矩阵命令 |
| arxiv 全链（T4-T7） | `adapters/arxiv/`（ids/buckets/parse/adapter）、`crawler watch`、31 个 preprint venue YAML（5 代表性+26 批量）、AC-2.3 双层证据、canary 3 样本、首次真实网络冒烟 |
| Stage B · 6 adapter | `adapters/{openreview,pmlr,cvf,acl_anthology,neurips_proceedings,aaai_ojs}/`；共享 OAI-PMH 信封核 `_oai.py`（aaai_ojs 落地时抽取，arxiv 验证零回归）；D-019 锚点快照 6 份 |
| 硬化修复 | Phase 1 遗留 pipeline 缺陷修复：`stages._asset_final_path` 补齐 si 资产落地路径（cvf 实现暴露，独立任务修复） |
| 合规/文档 | D-018/D-019/D-020 三条新 ADR；7 篇 `research/site-survey/`（含 acm_dl 勘察）；6 篇 adapter 详设 approved（arxiv.md 已转 implemented） |

统计：**104 commits**（`0e0e92f..c157123`，含 14 次 merge）；测试从 Phase 1 收尾的 519 passed
增至 **1629 passed / 8 skipped**（覆盖率 99.13%→99.32%）；零真实网络流量的默认门禁下，仅
`tests/online/` 1 个用例文件需显式 `-m online` 才触发真实请求。

## 4. 过程与质量机制

- **分档并行**：fable（编排/裁决/全分支终审/AC 验收）；opus（T1/T2/T5/T6 重件、openreview、
  关键 reviewer）；sonnet（T3/T4/T7、pmlr/cvf/acl_anthology/neurips_proceedings/aaai_ojs、轻
  reviewer）；峰值 **6 线 worktree 并行**（neurips_proceedings/aaai_ojs 实现 + acl_anthology/cvf
  审查 + si 资产修复同时在跑）。
- **详设硬门禁**：每 adapter 开工前对应设计文档须双评审（技术一致性+测试红线）通过。openreview
  两轮 REJECT 后 LIVE 勘察回炉重写；pmlr 详设 REJECT 触发 6 站（pmlr/cvf/acl_anthology/
  neurips_proceedings/aaai_ojs/acm_dl）LIVE 勘察批量前置，一次性压缩 Stage B 关键路径；
  6 篇详设最终经批量复审全部 approved。
- **LIVE 站点勘察合规**：7 站累计 **160 次只读请求**，全程诚实 UA（`PaperCrawler/0.1 (site
  survey; personal research)`）、限速≥1-2s/请求、遇挑战门即停不对抗：

  | 站点 | 请求数 | 关键发现 |
  |---|---|---|
  | openreview | 25 | 匿名读取 403 挑战门（须 free_account token）；60 请求/60s 限流 |
  | pmlr | 21 | PDF 双域按上传时间切分，带内 `citation_pdf_url` 自描述解法；AISTATS 缺口证伪 |
  | cvf | 22 | 三法交叉验证 CVPR2023=2353；ECCV 断言证伪；`day=all` 语义 |
  | acl_anthology | 24 | GitHub raw 单文件拉取优于 clone；robots.txt 实为 404（非空允许） |
  | neurips_proceedings | 26 | 首页年份列表本身即权威索引；2021→2022 单一格式硬边界 |
  | aaai_ojs | 20 | REST API 全线 403，OAI-PMH 为唯一可行机读路径 |
  | acm_dl | 3（另 19 次旁路取证不计入站点预算） | OA 拆付费墙未拆机器人墙，Cloudflare 挑战 + ToS 禁自动下载 |

- **评审拦截战果**（若无独立审查将带病进入生产的缺陷）：
  1. openreview 双评审两轮 REJECT（A 5 BLOCKER + B 3 BLOCKER，含 arxiv 缺陷复发 3 处）→ LIVE
     勘察回炉重写 → approved。
  2. pmlr 详设评审 REJECT（8 BLOCKER，含 PDF 双域迁移实锤、AC 编号查无、D-019 未落）。
  3. pmlr 实现审查 **HIGH**：`healthcheck` 正则对 `<b>` 标签切分的真实 DOM 结构失配，生产环境
     canary 会恒定误报 unhealthy——已修复（`adapter.py` docstring 自述"独立审查 2026-07-22
     发现并修复"）。
  4. cvf 实现审查 **HIGH**：flat-era 作者属性字段名误写（`query` vs `query_author`）全线 29
     处——commit `dfa2d2a` 修复。
  5. aaai_ojs 详设批量复审 5 项修订之一：回撤 watermark/subscription 表依赖倾向，改回与
     arxiv/openreview 同构的"零接口变更、固定回看窗"方案（`aaai-ojs.md` 现文显式标注"非持久化
     watermark"）。
  6. cvf 实现暴露 **Phase 1 遗留** pipeline 缺陷：`stages._asset_final_path` 只支持 pdf→si
     资产 pull 永久 `BLOCKED`（mock/arxiv 无 si 资产未曾暴露）——独立核心任务修复
     （`7a78856`）。
- **流程创新**：审查期"限量只读真实交叉验证"（pmlr ≤5 请求级）被证明是发现合成 fixture
  失真的有效手段（发现#3），在 pmlr/acl_anthology/cvf/neurips_proceedings 的 reviewer 派发中
  被制度化授权；**该实践未回写 `docs/testing/test-plan.md` 文档本身**（见 §6）。
- **多轮 union 合并教训**：6 个 Stage B adapter 陆续汇入 main 时，花名册断言/`parametrize`
  夹具/函数体截断三类高频冲突模式——已改为 controller 手工+AST 校验流程，避免正则联合解冲突
  的静默截断风险（`b92c70c` 前一次即遭遇并修复）。

## 5. 已知限制（如实记录）

- **openreview 在线三项 BLOCKED**：anchor 正式化（AC-2.1）、`pull` 在线冒烟（AC-2.2）、
  healthcheck 在线路径，均待用户在 `PAPER_CRAWLER_HOME/config.toml` `[auth.openreview]` 或
  环境变量 `PAPER_CRAWLER_OPENREVIEW_TOKEN` 配置免费账号 token。
- **在线冒烟 DoD 字面缺口**：development-plan.md 要求每 adapter 1 个限量在线冒烟，实际仅
  arxiv 达成 committed 可重跑测试；5 个 adapter（pmlr/cvf/acl_anthology/neurips_proceedings 明确、
  aaai_ojs 未逐条明记）以审查期非 committed 真实交叉验证替代——精神满足但字面未满足，口径未
  裁决（验收汇总附注 3）。
- **D-019 锚点均未达人工核准终态**：6/7 adapter（除 arxiv）锚点表结构就位，但 openreview 全表
  待 token、pmlr/neurips_proceedings 各仅 1 行 LIVE 种子、cvf 仅 1/28 行、aaai_ojs 全表
  `null`、acl_anthology 计数真实但外源核对未做——无一 adapter 完成"人工核准终态"。
- **三处 `[UNRESOLVED]`（各 adapter 详设/勘察已显式标注，非本报告新发现）**：aaai_ojs
  2019 年前届（1980-2018）覆盖范围未验证；aaai_ojs IAAI/EAAI 记录归属拆分未验证；
  neurips_proceedings 详情页 BibTeX 按钮 URL 疑似模板拼接 bug，未实测校正（预算内耗尽）。
- **运维收尾项未落地**：`make smoke` 目标未添加（T3 审查 concern 遗留至今）；canary 输出落盘
  `docs/testing/records/canary/` 未建立（T3 concern，"运维化随收尾"，尚未收尾）；
  development-plan.md"里程碑与节奏"约定的 catalog `supported_since: phase-N` 标注，全库
  **0 处**落地——含 Phase 1 mock 与本 Phase 全部 7 个 adapter，是自 Phase 1 起就存在的缺口，
  非本 Phase 新增。
- **文档状态滞后**（D-010/status-workflow"模块 stable 后文档转 implemented"应属收尾动作）：
  6 个 Stage B adapter 设计文档（openreview/pmlr/cvf/acl-anthology/neurips-proceedings/
  aaai-ojs）均已合并且 DoD 达成，但 front matter 仍为 `approved`，未转 `implemented`（仅
  arxiv.md 已转正）；`docs/plan/progress.md` 快照仍停留在"W0 完成/T1-T2 开发中"叙事，未反映
  Stage B 6/6 合并现状；`docs/INDEX.md` 摘要仍写"decision-log D-001…D-019"未含 D-020——以上
  均为本报告草稿阶段的已知状态，非本报告职责范围内的落盘对象（本报告与验收记录不写
  `docs/`，由主 agent 终验时一并处理）。
- **Phase 1 report §5 移交项已消除**：fetch 收尾三步同事务化（T1 `finalize_fetch`）、mock 裸
  `ValueError` 转 `CrawlerError`——均已完成，不再是限制。

## 6. Phase 3 开工检查单（终审 triage 移交）

1. **【待用户】** OpenReview 免费账号 token 配置——解除 AC-2.1/2.2 在线层与 anchor 正式化
   BLOCKED（config 路径见 §5）。
2. **【待用户】** 外部 API 申请提醒（Elsevier / Semantic Scholar / Kaggle）——Phase 3 聚合层
   与 Phase 4 认证框架前置；Kaggle bulk backfill 已在 arxiv 范围内 deferred（W0 R7），Phase 3
   视聚合层需要重议。
3. D-019 六份锚点表（除 arxiv）人工 DBLP/官方页核准 → 转各自 `count_status`/
   `dblp_cross_check` 终态（UPDATE_GOLDEN 纪律，records 留痕）；aaai_ojs 需先补跑一次全库 OAI
   收割（当前全表计数为 `null`，非仅核对未做）。
4. 6 篇 Stage B adapter 详设 `approved`→`implemented` 转正；`progress.md`/`INDEX.md`/
   decision-log 摘要同步 D-020；tag `phase-2`。
5. **在线冒烟 DoD 口径裁决**（§5）：建议二选一——①比照 pmlr/cvf/acl_anthology/
   neurips_proceedings 各补 1 个最小 `tests/online/` 用例（1-3 请求量级，仿 arxiv 模式）后再
   关闭 Phase 2；②明确记入 decision-log，接受"审查期限量真实交叉验证"等价满足 DoD 精神，
   并回写 `docs/testing/test-plan.md` 使该实践从"操作层默契"变为文档化政策。
6. openreview `meta` 私有键白名单方案（实现期审查 concern，移交 Phase 3 落地）。
7. aaai_ojs 三项 `[UNRESOLVED]`（2019 年前覆盖范围 / BibTeX 按钮 URL bug 校验 / IAAI-EAAI
   拆分）与 neurips_proceedings 的同类项，实现期或独立任务专项核实。
8. 运维收尾三项（§5）：`make smoke` 目标、canary 落盘目录、catalog `supported_since` 全量
   补标（Phase 0-2 累计缺口，建议一次性批处理而非逐 Phase 补）。
9. AC-0 红线的系统性终验扫描（git 全历史+日志正则）——本报告 §2 已标注为待终验 agent 执行项，
   不可省略（Phase 1 report 先例）。
