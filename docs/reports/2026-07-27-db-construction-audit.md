# 全库 `Database` 构造审计报告（2026-07-27，Phase 7 T17）

> **卡片**：Phase 7 T17（[phase7-implementation-plan §4](../plan/phase7-implementation-plan.md#w3-波次) W3
> 波次）；**检查单出处**：[phase6-report §6 检查单 #10](2026-07-26-phase6-report.md)"全库 76 处/41 文件
> `Database` 构造审计（终审实测，归口审计域 S4，跨 Phase 遗留，本 Phase 未触及）"，溯源至
> [post-phase5-audit §3[S4]](2026-07-24-post-phase5-audit.md)"offline 全绿跑伴随 27 条 sqlite
> `ResourceWarning`（集中于 `tests/unit/test_migrations.py` 连接开闭不对等）"一项，Phase 6 F5 已修
> `test_migrations.py` 单文件（样板：`with contextlib.closing(Database(db_path)) as database:`），
> 终审时 opus 补做全库 grep 扫出 76/41 的更广缺口，列为 Phase 7 检查单 #10、本卡（T17）跨 Phase 收口。
> **性质**：本审计表是本卡**第一等交付物**（非附属品）——四分类甄别 + 处置 + B/C 类逐处修复，
> 修复只加资源纪律（`closing()`/`try…finally`/pytest fixture yield-teardown 三选一），**不改变任何
> 既有测试的断言与生产行为**。

## 1. 口径复现与 76/41 → 88/43 的差异说明

复现命令（与检查单 #10 出处同一 grep 口径）：

```
grep -rn "Database(" --include="*.py" src tests | grep -v __pycache__
```

| 时点 | 处数 | 文件数 | 备注 |
|---|---|---|---|
| Phase 6 终审实测（2026-07-26，opus） | 76 | 41 | [phase6-report 检查单 #10](2026-07-26-phase6-report.md) 原始口径 |
| 本卡侦察（派发时给出的参考数） | 82 | 41 | 需求文本内附注"main 演进后以实测为准" |
| 本卡实测（2026-07-27，分支切出点） | **87 行 / 88 处**（`test_dbdump.py:115` 一行两次构造
  `raw_a, raw_b = Database(db_a), Database(db_b)`） | **43** | 本报告口径 |

**差异原因**：三次测量之间 main 持续演进（Phase 7 W0/W1 卡陆续合并，例如 T7 抽取器落地新增
schema v4 相关测试断言、W0-W1 期间多张测试文件增补用例），76→82→88 的处数增长、41→43 的文件数
增长均是**新增测试文件/用例**带来的自然存量增长，不是同一批文件被重复计数或口径本身漂移——
逐次相差的具体 6 处/6 处/2 文件已不可逆向精确对账（各次测量均为一次性 grep 快照，未落盘中间结果），
本报告以 2026-07-27 分支切出点的 88 处/43 文件实测为准，不追溯復盘更早两次的逐处 diff。

## 2. 方法论：四分类判据

| 分类 | 判据 | 处置 |
|---|---|---|
| **A** 已有兜底 | `with contextlib.closing(Database(...))`；或 `try…finally: db.close()`（含嵌套）；
  或 pytest fixture 标准 `yield` 兜底范式（构造 → `yield` → `.close()`，含通过对象方法委托
  `env.close()` 后者内部再 `self.db.close()` 的形式；含"构造失败则自行 close 后重新抛出"的
  helper，如 `test_migrations.py::_seed_v1`） | 不动，登记 |
| **B** 无兜底 + 测试侧重复构造 | 测试函数体或测试 helper 内"构造 → 操作 → 函数尾部手写
  `.close()`"的线性写法（无 `try…finally`，中途任何 `assert`/`repo.*`/`db.migrate()` 调用抛出即
  泄漏）；或彻底无 `.close()`（更严重的裸泄漏） | 逐处改为 F5 样板 `closing()`，
  或提升为 `request.addfinalizer`/fixture |
| **C** 生产路径无兜底 | `src/` 内的构造点缺乏任何资源清理链路 | 本次审计**零命中**（见 §4） |
| **D** 非构造误匹配 | 类型注解（如 `db: Database`）、字符串/注释中的字面文本 | 本次审计**零命中**（见 §4） |

判据从严（"存疑归 B 改掉"）：凡不能在原地清楚看到 `closing()`/`try…finally`/fixture-yield 三者之一
的，一律计入 B 并修复，不因"实际上大概率不会中途抛异常"而放宽为 A。

## 3. 逐文件审计表（43 文件，88 处）

| 文件 | 处数 | 分类 | 处置 | 理由 |
|---|---|---|---|---|
| `src/paper_crawler/cli.py` | 1 | A | 不动 | `_build_env`（:291 `db = Database(config.db_path)`）唯一生产构造点，经 `_env()` contextmanager（:322-350）`try…finally` 兜底关闭（`cli_env.ctx.db.close()`），检查单 #10 原文举例即此处 |
| `tests/helpers/dbdump.py` | 3 | A | 不动 | `canonical_dump`/`dump_weak_keys`/`dump_paper_relations` 三函数均 `db = Database(...); try: …; finally: db.close()` |
| `tests/integration/test_aaai_enumerate.py` | 2 | A(1)+B(1) | B 处已修 | `repo` fixture（:52-58）yield-teardown 标准范式=A；`test_cold_backfill_whole_timeline_costs_one_full_pass`（原 :158）裸构造零 `.close()`=B，已改 `closing()` |
| `tests/integration/test_ac_blocked_resume.py` | 2 | A | 不动 | `_blocked_fetch_tasks`/`_assets_fetched` 均 `try…finally` |
| `tests/integration/test_ac_dryrun.py` | 1 | A | 不动 | `_asset_state_counts` `try…finally` |
| `tests/integration/test_ac_killresume.py` | 2 | A | 不动 | `_success_logs_per_asset`/`_assets_fetched` 均 `try…finally` |
| `tests/integration/test_ac_ratelimit.py` | 1 | A | 不动 | `_fetch_log_timestamps` `try…finally` |
| `tests/integration/test_acl_anthology_acceptance.py` | 2 | A | 不动 | `_papers_count`/`_pdf_asset_count` 均 `try…finally` |
| `tests/integration/test_arxiv_enumerate.py` | 1 | A | 不动 | `repo` fixture yield-teardown |
| `tests/integration/test_arxiv_watch.py` | 1 | A | 不动 | `make_watch_env` 工厂 fixture：内部 `envs: list[WatchEnv] = []` 累积每次 `factory()` 调用产物，teardown 逐个 `env.db.close()`——支持同测试多次调用的健壮范式 |
| `tests/integration/test_auth_pipeline.py` | 2 | B | 已修 | `_setup()`（:237，21 处调用方共用）与 `test_elsevier_resolve_entitlement_false_derives_oa_fallback`（原 :755）均裸构造/线性尾部 close，零 `try…finally`；`_setup` 尤其严重——21 个测试函数共用且此前**全程零关闭**。改用 `request.addfinalizer(db.close)`（pytest 标准清理钩子，测试 pass/fail 任一路径都会执行），22 处调用点（21 测试 + 1 独立测试）同步补 `request: pytest.FixtureRequest` 签名与 `request=request` 实参 |
| `tests/integration/test_browser_fetch_pipeline.py` | 1 | A | 不动 | `env` fixture yield-teardown，经 `Env.close()` 委托 `self.db.close()` |
| `tests/integration/test_cli.py` | 1 | A | 不动 | `test_papers_in_scope_dedupes_paper_shared_across_issues` 内 `try…finally` |
| `tests/integration/test_cli_enrich.py` | 2 | B | 已修 | `_seed_dois`/`_abstract_of` 线性尾部 close、无 `try…finally`；两处均改 `closing()` |
| `tests/integration/test_cli_enrich_repec.py` | 4 | B | 已修 | `_seed_crossref_paper`/`_paper_row`/`_identifiers`/`_paper_count` 四 helper 同构线性写法；四处均改 `closing()` |
| `tests/integration/test_cli_oa_report.py` | 1 | B | 已修 | `_seed_dois` 线性写法；改 `closing()` |
| `tests/integration/test_crossref_cursor_resume.py` | 3 | B | 已修 | 三个 `test_cursor_interrupt_*` 测试体直接构造且**全程零 `.close()`**（比线性写法更差的裸泄漏）；三处均改 `with closing(Database(...)) as database:` 包裹整个测试体 |
| `tests/integration/test_cvf_acceptance.py` | 1 | A | 不动 | `_issue_years` `try…finally` |
| `tests/integration/test_cvf_pull.py` | 3 | A | 不动 | `_papers`/`_fetched_titles`/`_cvf_identifiers` 均 `try…finally` |
| `tests/integration/test_econsoc_enumerate.py` | 1 | A | 不动 | `repo` fixture yield-teardown |
| `tests/integration/test_merge_acceptance.py` | 1 | A | 不动 | `env` fixture yield-teardown |
| `tests/integration/test_merge_property.py` | 3 | B | 已修 | `_run()` helper（hypothesis `@given` 驱动，每 example 调用一次）与 `test_reingest_whole_batch_is_idempotent` 内两处直接构造均线性写法，仅外层 `tempfile.TemporaryDirectory()` 管临时目录、未管连接；三处均改 `closing()` |
| `tests/integration/test_neurips_proceedings_enumerate.py` | 3 | A | 不动 | `repo` fixture yield-teardown + `_pull_papers`/`_pull_fetched_assets` 均 `try…finally` |
| `tests/integration/test_oa_report_ratelimit.py` | 1 | B | 已修 | `_seed_dois` 线性写法；改 `closing()` |
| `tests/integration/test_openreview_acceptance.py` | 1 | A | 不动 | `_issue_years` `try…finally` |
| `tests/integration/test_openreview_pull.py` | 3 | A | 不动 | `_papers`/`_fetched_assets`/`_openreview_identifiers` 均 `try…finally`（另两处对 `CliEnv` 的手工 `try…finally` 清理不计入本文件构造点——消费的是 `cli._build_env` 返回对象，构造点归 `cli.py`） |
| `tests/integration/test_oup_cookie_seam.py` | 1 | A | 不动 | `_assemble` 嵌套 `try…finally`（内层 `http.close()`、外层 `db.close()`） |
| `tests/integration/test_pipeline_e2e.py` | 1 | A | 不动 | `env` fixture yield-teardown，经 `PipelineEnv.close()` 委托 |
| `tests/integration/test_pmlr_enumerate.py` | 1 | A | 不动 | `repo` fixture yield-teardown |
| `tests/integration/test_subs_ac6_acceptance.py` | 1 | A | 不动 | `env` fixture yield-teardown |
| `tests/integration/test_subs_guard_db.py` | 1 | A | 不动 | `repo` fixture yield-teardown |
| `tests/integration/test_subs_watch_e2e.py` | 1 | A | 不动 | `env` fixture yield-teardown |
| `tests/integration/test_subscription_repo.py` | 1 | A | 不动 | `repo` fixture yield-teardown |
| `tests/online/test_openreview_smoke.py` | 1 | A | 不动 | `_issue_years` `try…finally`（同文件三个 session-scope `HttpClient` fixture 亦各自 `try…finally`，非 `Database` 构造不计入本表处数） |
| `tests/unit/test_cli_grab.py` | 2 | B | 已修 | `_seed_paper` helper 与 `test_not_in_db_creates_row_via_crossref` 内直接构造均线性写法；两处均改 `closing()` |
| `tests/unit/test_dbdump.py` | 16（17 处构造，`:115` 一行两次） | B | 已修 | 全文件统一"构造→操作→尾部 close"线性写法，零 `try…finally`——`_build_db` helper + 12 个测试函数体（含 1 处双构造）；17 处全部改 `closing()`（含 `with closing(...) as raw_a, closing(...) as raw_b:` 并列形式） |
| `tests/unit/test_merge.py` | 1 | A | 不动 | `env` fixture yield-teardown |
| `tests/unit/test_migrations.py` | 8 | A | 不动 | Phase 6 F5 已固化的参照样板本身：`db` fixture yield-teardown（1）+ 6 处 `with closing(Database(...)) as database:`（含 `closing(_seed_v1(...))` 复合形式）+ `_seed_v1` helper 自身 `try: …; except Exception: database.close(); raise`（构造失败即时清理后重新抛出，属"已有兜底"的第三种形态） |
| `tests/unit/test_repo.py` | 1 | A | 不动 | `repo` fixture yield-teardown |
| `tests/unit/test_subs_watermark.py` | 1 | A | 不动 | `repo` fixture yield-teardown |
| `tests/unit/test_task_queue.py` | 1 | A | 不动 | `database` fixture yield-teardown |
| `tests/unit/test_task_statemachine.py` | 1 | A | 不动 | `queue` fixture（内部 `database` 变量）yield-teardown |
| `tests/unit/test_verify.py` | 1 | A | 不动 | `repo` fixture yield-teardown |

## 4. 四分类计数与修复面

| 分类 | 处数 | 文件数（含该分类至少 1 处） |
|---|---|---|
| A（已有兜底，不动） | 52 | 33 |
| B（无兜底，已修） | 36 | 10 |
| C（生产路径无兜底） | 0 | 0 |
| D（非构造误匹配） | 0 | 0 |
| **合计** | **88** | **43** |

**C=0 说明**：`src/` 内唯一的 `Database(` 构造点（`cli.py:291`）经 `_env()` 的 `try…finally` 兜底，
不存在生产路径无兜底的实例——本次全库扫描没有发现新的生产侧缺口，检查单 #10 的风险面完全落在
测试侧（B 类）。

**D=0 说明**：逐处核对（含对 `#` 注释行与三引号字符串块的专项复检）未发现类型注解（如
`db: Database`，因缺少构造用括号不会被本 grep 模式命中）或字符串字面量误匹配；88 处全部是真实
`Database(...)` 构造调用。

**B 类 10 个文件、36 处修复清单**（均只加资源纪律，不改断言/不改生产行为）：

| 文件 | 处数 | 修复手法 |
|---|---|---|
| `tests/unit/test_dbdump.py` | 17 | `with closing(Database(...)) as database:` 包裹（含 1 处并列双构造） |
| `tests/integration/test_auth_pipeline.py` | 2 | `request.addfinalizer(db.close)`（`_setup()` 被 21 个测试函数共用，无法简单 `with` 包裹调用方函数体，改用 pytest 标准清理钩子；21 处调用点 + 1 处独立测试同步补 `request` 参数） |
| `tests/integration/test_cli_enrich_repec.py` | 4 | `closing()` |
| `tests/integration/test_merge_property.py` | 3 | `closing()`（`_run()` helper + `test_reingest_whole_batch_is_idempotent` 内两处） |
| `tests/integration/test_crossref_cursor_resume.py` | 3 | `closing()` 包裹整个测试体（原全程零 `.close()`） |
| `tests/unit/test_cli_grab.py` | 2 | `closing()` |
| `tests/integration/test_cli_enrich.py` | 2 | `closing()` |
| `tests/integration/test_aaai_enumerate.py` | 1 | `closing()` 包裹整个测试体（原全程零 `.close()`） |
| `tests/integration/test_cli_oa_report.py` | 1 | `closing()` |
| `tests/integration/test_oa_report_ratelimit.py` | 1 | `closing()` |

`test_auth_pipeline.py::_setup` 是本次审计发现的最严重个案：21 个测试函数共用同一 helper 构造
`Database`，此前**全程没有任何 `.close()` 调用**（比其余 B 类"线性写法但终会 close"更差一个层级
——纯裸连接泄漏），推断是 `post-phase5-audit §3[S4]` 记录的"27 条 sqlite ResourceWarning"跨文件
gc 效应的主要贡献源之一（该发现本身未被要求逐一溯源到具体来源文件，此处仅如实记录关联推断，
不作为断言）。

## 5. 验证

- 10 个受改文件全部 `python3 -m py_compile` 通过、`ruff check`/`ruff format --check` 全绿。
- 10 个受改文件单独 `pytest` 跑通：103 passed（含 `test_auth_pipeline.py` 31 项、`test_dbdump.py`
  等）。
- 全库 `make check` 结果见卡报告正文（分支/提交/门禁三行）。

## 6. 结论

Phase 6 检查单 #10 的"全库 Database 构造审计"缺口已收口：88 处（43 文件）逐处甄别完毕，52 处
（33 文件）确认已有兜底不动，36 处（10 文件）无兜底缺口已修复为 `closing()`/`request.addfinalizer`
两种资源纪律范式之一，生产路径（C 类）零命中，非构造误匹配（D 类）零命中。全部修复保持既有测试
断言与生产行为不变，仅补齐连接关闭的确定性（正常/异常路径均可靠 `.close()`）。
