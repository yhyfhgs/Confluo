# Phase 7 阶段报告 — 全文抽取与库增强（2026-07-27）

> 格式仿 [2026-07-26-phase6-report.md](2026-07-26-phase6-report.md)。**本稿由 T21 文档一致性收尾撰写**：
> **22** 张任务卡（W0 六卡 T1–T6 并行铺开 → W1 T7/T8/T9/T10 滚动补位 → W2 T11–T15 → W3 T16–T18 →
> W4 T19 在线验收批）+ **T20 终态独立审计批**（Opus 深审×2 + Sonnet 面审×1）+ **三条修复批**
> （P0 崩溃修复、R1 browser-fetch/ssrn 接缝修复、R2 repec/search 数据层修复，各经"执行→独立审查→
> 回修→复核→controller 合并+门禁"闭环）+ **在线重跑（卡 D）**，均已合入 `main`。本报告不重新独立
> 验证 AC-7.x（引用 [AC-7 验收记录](../testing/records/2026-07-27-ac7-acceptance.md) 已有结论），
> 只做交付盘点、检查单对账与 Phase 8 开工检查单产出（T21 职责边界，[phase7-implementation-plan.md
> §4 T21](../plan/phase7-implementation-plan.md)）。`tag phase-7` **未打**（T21 职责边界之外，
> controller 全分支终审 + 合并裁决后由 fable 另打，T22 卡）。
> 依据：[development-plan §Phase 7](../plan/development-plan.md)、
> [phase7-implementation-plan.md](../plan/phase7-implementation-plan.md)（22 卡切分+接口冻结件+
> 在线预算表）、[acceptance-criteria.md AC-7/AC-BF/AC-0](../testing/acceptance-criteria.md)、
> [AC-7 验收记录](../testing/records/2026-07-27-ac7-acceptance.md)、
> [decision-log D-033/D-034/D-035/D-036](../plan/decision-log.md)、
> [db-construction-audit（T17）](2026-07-27-db-construction-audit.md)、
> [phase6-report §6 开工检查单](2026-07-26-phase6-report.md)（本 Phase 处置的 16 项出处）。
> 代码版本：`main` @ `0a9ce11`（本报告写作时点；`tag phase-7` 待 controller 全分支终审、合并裁决后打）。
> `d56313f..0a9ce11` 共 **68 commits / 0 merges**（任务分支在隔离 worktree 内开发、由 controller
> 滚动合并进 main 的常规提交，非字面 `git merge`；**68/68** 提交带 `Co-Authored-By` 尾行——Fable 5/
> Opus 4.8/Opus/Opus 5/Sonnet 5 五档署名，git 纪律零缺）。`git diff --shortstat d56313f..0a9ce11` =
> **134 files changed, +24337 / -1263**（src+tests 105 文件 +21501/-1202；docs 22 文件 +2075/-59；
> subscriptions+venues 2 文件 +4/-2；scripts+顶层配置 3 文件 +725/-0；`config/config.example.toml`+
> `uv.lock` 2 文件为其余）。

## 1. 概览

Phase 7「全文抽取与库增强」**22 卡**5 波次（W0 六卡并行铺开 T1+T2+T3+T4+T5+T6 → W1 T7(←T1)+
T8(←T2)+T9+T10 滚动补位 → W2 T11(←T6)+T12(←T2)+T13+T14(←T1)+T15 → W3 T16(←T10)+T17+T18(←T6,T11) →
W4 T19→T20→T21→T22 串行收尾）**全交付**：T1–T19 主线于前一编排 session 完成合并；本 session 承接
**T20 终态独立审计**发现的 4 处跨卡缝缺陷 + T19 在线批自行发现的 P0 缺陷，完成全部三条修复批的
闭环与在线重跑，并交付本报告（T21）。

门禁全量测试从 Phase 7 开工基线（main @ `d56313f`，fan-out 修复卡已前置合并）的 **3832 passed /
28 skipped** 增至本报告写作时点（main @ `0a9ce11`，controller 亲跑）的 **4617 passed / 31 skipped /
覆盖 98.98% / EXIT=0**（+785 测试；`ruff check`/`ruff format --check`/`mypy src` 三项全绿）。
adapter 数 **20→21**（新增 `repec`，enrich-only、`domains=()`、零网络——`pyproject.toml`
entry-points 与 `crawler canary` 集合等值自断言同步 +1）；venue 数**不变**（仍 58，本 Phase 未新增
可路由 venue，repec 不进 registry 路由）。

新增一个包：`src/paper_crawler/adapters/repec/`（zero-network enrich adapter，D-035）；既有代码
新增/改造：`pipeline/extract.py`（stage 5 真实抽取，D-033）、`browserfetch.py`（横切件核心，design/11）、
`pipeline/cooldown.py`（冷却读写公用模块，E-2）、`storage/db.py` FTS5 迁移器扩展（`BEGIN…END` 复合语句
支持，D-034）、`merge.py` preprint_of 建边、`verify.py` 三段扩展（+si/+fulltext）。新增用户可见文件：
`scripts/budget_ledger.py`（机动预算运行时账本）、`scripts/repec_snapshot.py`（repec bulk 快照唯一
网络面）。schema **v3→v5**（`0004_fulltext_asset.sql` asset 级幂等键五列 + `0005_fts_paper.sql`
FTS5 虚表+触发器，两迁移零重叠、先合者取小号）。

AC-7 四条判据：[AC-7 验收记录](../testing/records/2026-07-27-ac7-acceptance.md)§1 逐条判定——
AC-7.1（全文抽取）与 AC-7.4（全库对账+关联报告）**PASS**（真实数据支撑：3 篇真实 PDF 标题比
0.0000、verify 注入缺陷复验 EXIT 0↔1↔0）；AC-7.3（去重审核）**条件 PASS**（离线三件套齐备，
在线因本库单源语料呈空态，如实标注不冒充通过）；AC-7.2（GROBID 可选）离线 **PASS**、在线为
**条件项**（本机无 GROBID 服务，环境未就绪，非缺陷）。`status: draft`——签署权限归 fable 终审
（AC-7 记录 §5 两处 NEEDS_DECISION 均已裁决落档，详见 §6 与该记录本身，转入待签署阶段，本报告
不代行签署）。

## 2. 关键决策

四条新 ADR 于 2026-07-27 定稿（[decision-log.md](../plan/decision-log.md) D-033/D-034/D-035/D-036，
均 `accepted`）：

- **D-033 · 全文抽取（stage 5 extract）语义定稿**：纯文本基线抽取器 = `pypdf`（入核心依赖，非
  extra；pdfminer.six 因"版面分析优势恰是 GROBID 覆盖的那一格、代价却踩 D-023 依赖分界线"被判
  支配劣势项出局，PyMuPDF 因 AGPL 许可冲突出局）；`TextExtractor` Protocol = 路径进、值对象出，
  `char_count==0` 为统一的"零输出"判据（而非 `text==""`，因 GROBID 的 TEI 源码非空但可见文本
  可能为零）；幂等键升级为 **asset 级** `(asset_id, source_sha256, extractor, extractor_ver)`，
  取代规则 = **全序取 max**（rank：grobid 2 > pypdf 1 > `extract_failed` 0 > `noop` −1 > 陈旧行
  −2，沿用 D-031 已付学费的"半格运算与注入顺序无关"纪律）；GROBID 为本地 REST 可选增强，
  `consolidateHeader/Citations/Funders` 三者硬编码 0（防越权外网请求）；降级链按"探活失败/
  逐篇连接失败→整轮降级并记忆，读超时→本篇降级不记忆"两类判别；fixture 策略 = 程序化生成
  （L1 手写最小合法 PDF/L2 生成式负例/L3 自造 TEI 语料），零 `.pdf` 文件入库（AC-0.3 明文
  PDF 不入 git 历史）。落款经"起草→独立审查 NEEDS_FIX（7 必修+7 P2）→r2 全吸收→re-review→
  r3 文档级补正→fable 终签"全链，落地 T7。
- **D-034 · FTS5 检索索引形态**：范围 = `paper.title`+`paper.abstract` 二字段（正文/向量索引
  defer，见 §8）；表形态 = **content-owning** 虚表（否决 external-content/contentless 两案，
  决定性理由 = `paper.id` 是 ULID 文本主键、隐式 rowid 在 `VACUUM` 后可重编号，content-owning
  把 `paper_id` 物化进索引行使"故障模式从静默错误降为响亮失败/可检出的不一致"）；同步策略 = SQL
  触发器（三条不变式：`paper_id` 必同写、UPDATE 取 DELETE+INSERT、DELETE 双条件防误删他行）；
  迁移 `0005_fts_paper.sql`（独立审查实测发现既有迁移器 `_iter_statements` 切不了触发器复合语句，
  T12 随卡扩展支持 `BEGIN…END`）；`crawler reindex [--check]` 三项校验（双向差集+行数配对+
  FTS5 自身 integrity-check）。**修订 D-017 决策 4**（兑现 Phase 由 Phase 6 改判 Phase 7 T12，
  Phase 6 未兑现属承诺落空、如实记债后再修订）。2026-07-27 追加修订：`search` 命令面被
  D-036 revise（见下）。
- **D-035 · repec 接入形态**：`_ENRICH_SOURCES` 元组扩位（最小改，registry role 声明式改造
  挂 P8）；`SOURCE_PRIORITY` 扩为七位重编号（repec 取最低非-heuristic 位，其独家增值 JEL/
  `Publication-Status` 只补空、无须"只补不覆盖"特殊逻辑）；`state/repec/` bulk 快照落盘契约
  （原样字节+sha256、失效语义"缺失→CrawlerError/过期→响亮 WARNING 继续运行"、刷新走
  `scripts/repec_snapshot.py` 唯一网络面使 `enrich_batch` 零网络成为可被 socket 猴补机械证明的
  结构事实）；`enrich_batch(dois)` 未命中三分观测（结构性不可寻址/覆盖缺口/增值为空）；DOI↔handle
  仅 NBER 语法映射（`w{n}`/`t{n}` 双映射，T8 期原案）。落款经独立审查 NEEDS_FIX（P1×2：`domains=()`
  会打红既有非空断言+过期 WARNING 缺可操作面）→ fable 落章两项 approved。
- **D-036 · repec DOI↔handle 映射收窄为 w-only + `search` 聚合展示与 `list` 统一**（T20 审计 R2
  修复批补账）：**supersedes D-035 决策 4** 两处——① `w{n}`/`t{n}` 双映射收窄为**只映射 `w`**
  （根因：`series_id[1:]` 去首字母令两篇不相交论文塌进同一 handle，静默污染+假
  `candidate_duplicate`；收窄走**正确性论证**而非"T19 实测证伪"路径，故须 supersede 而非援引
  D-035 原授权静默改）；② 未命中三分 (a) 定义扩为"非 NBER 工作论文 DOI"。**revises D-034 决策 5**
  的 `search` 命令面——增补 `--aggregate/--no-aggregate`（默认开，与 `list` 同名同义同默认），
  根治"同一个库、`list` 折叠而 `search` 恒不折叠"的自相矛盾（根因：`fold_merged` 内联写死
  `row["id"]` 只服务 `list_papers` 一种列形状，新增 `repo.display_row_paper_id` 唯一口径后
  两条展示路径共用同一份折叠实现）。落款经"代码先行落地（`243ef10`/`93ffedd`）→独立审查判代码面
  PASS、唯一阻断项=文档账缺失（推翻 approved 契约却零记录，违反 AGENTS §3/§5）→ 回派同卡补账"，
  本条即该补账（`82fbfa9`），代码与测试零改动。

## 3. 交付清单

### 3.1 主线（T1–T18，前一编排 session 完成合并）

| 卡 | 交付 | 关键 commit |
|---|---|---|
| T1 D-033 全文抽取详设 ADR | `docs/design/12-fulltext-extract.md`（新，approved）+ D-033 六项裁决（详见 §2） | `ff9a862`（起草）+ `d2d0832`（r2 吸收独立审查）+ `684880d`（r3 文档级补正）+ `3c96ce5`（fable 终签）+ `4982f66`（落款残句对齐） |
| T2 D-034 FTS5 + D-035 repec 双 ADR | decision-log D-034/D-035 两条 + design/06 索引节增补 + aggregators.md §5.7 契约级设计 | `e679155`（起草）+ `f398e1c`（NEEDS_FIX 修复：P0-1/P1×4/P2×4）+ `29ecc4a`（re-review 三处文本残留） |
| T3 E-2 冷却键统一 + `cooldown` CLI | 冷却读写逻辑抽为 `pipeline/cooldown.py` 公用模块（CLI 进程无常驻 runner）+ `crawler cooldown status\|clear` 子命令组 | `8871401`（feat）+ `a4bfe65`（NEEDS_FIX：路径穿越防护+status 损坏文件响亮化）+ `1e0eaf9`（browser-fetch 侧冷却读逻辑委派本模块，T6 rebase 联动） |
| T4 机动预算运行时账本（检查单 #16） | `scripts/budget_ledger.py` + `.paper-crawler/state/budget.json`（`fcntl.flock` 并发安全）+ `docs/process/online-budget.md`（三条纪律，闭合 phase6-report 事件⑤协调缺口） | `5efeb4f`（feat）+ `38b1186`（fail-loud 修复：畸形账本响亮拒绝+写入时计数护栏） |
| T5 文档微清账（检查单 #12+#15，纯文档卡） | `catalog/economics-journals.md` 四刊 `[LIVE]` 注记补齐 + ECMA 行 adapter 归属表述统一（`economics-journals.md`/`publishers-platforms.md` 两处统一为"econsoc(当前段自营 OA)/wiley(过刊段，D-028)"范式） | `9e846e3` |
| T6 browser-fetch 横切件核心（检查单 #1 前半） | `browserfetch.py`（新）：`fetch_one` 纯函数 + `BrowserFetchHandle` Protocol；`_stage_fetch` RENDER_PAGE 分支；`[browserfetch]` 四槽（`enabled/daily_cap/rate_rpm/jitter_s`）；`grab --browser` 三级门 | `2d1210e`+`a2d4527`+`cd5b9c1`+`fa836b4`+`fc5a776`+`4b9a4c9`（feat/test 六提交）+ `8407231`（NEEDS_FIX 三修+四项已知边界登记） |
| T7 extract 核心落地（依赖 T1） | schema v4（`0004_fulltext_asset.sql` 五列）+ 抽取器层（pypdf 基线+GROBID 客户端+全序取代）+ stage 5 noop→真实抽取（asset 级幂等+降级链） | `e8a872d`+`575a8ec`+`a9cfb29`+`775de9d`（feat/docs 四提交）+ `b3b8502`（审查 APPROVE 附条件三项收尾：列注释/迁移号注记/连接池释放） |
| T8 repec enrich 首批（依赖 T2，检查单 #2） | 两域 robots 附条件核验（fable 裁决"无从判读、附条件放行"）→ `adapters/repec/{__init__,adapter,parse}.py` + `scripts/repec_snapshot.py`（bulk ReDIF 零网络本地 join） | `73bf2f5`+`c31dd0a`（robots 核验落档）+ `c0642f3`（feat）+ `59f3cf8`（NEEDS_FIX：P1×3+P2×7）+ `652a5f7`（re-review：record_count 口径取齐） |
| T9 arxiv 参数化谓词机制（检查单 #4 谓词半边） | `PREDICATE_REGISTRY` 谓词签名改造（构造器形态）；`_compile_arxiv` 把 `query` 布尔式编译为参数化补偿谓词实例，替代 `title_regex_any` 手工镜像"约定"（9 preset 该谓词保留作防御纵深，非替换） | `d4409be`（feat）+ `1ac02ed`（接入 watch.py 运行时，controller 追加授权）+ `e6ffb27`（NEEDS_FIX：未闭合引号静默清零+真话/死码纠偏） |
| T10 preprint_of 建边引擎（检查单 #5） | `merge.py::MergeEngine.ingest()` 新增建边分支，消费 arxiv `journal_ref`/Crossref/OpenAlex preprint 字段等线索，方向固定 from(预印本)→to(发表版)（`paper_relation` 表已支持，零迁移） | `c1acdc6`（feat）+ `d367141`（NEEDS_FIX：双向矛盾环/证据溯源/arxiv 归一链三项 P1）+ `6299755`（re-review REOPEN #6：反向行守卫堵住跨观测双向矛盾环） |
| T11 browser-fetch 三消费方接入（依赖 T6，检查单 #1 后半） | ssrn 模式 B / aea pubs 全文 / wiley 页面兜底三处消费 `BrowserFetchHandle` 接缝 | `b3f4d6c`（feat）+ `43c227b`+`ad8bd67`（open_access 干净上下文裁决+二跳质询改判提案登记） |
| T12 FTS5 落地（依赖 T2） | `0005_fts_paper.sql`（迁移器扩展支持 `BEGIN…END` 复合语句）+ `repo.search_papers()` + `crawler search`/`reindex [--check]` | `2d63ab7`（计划号位裁决记录）+ `db1eade`（feat）+ `8c9a081`（NEEDS_FIX：rowid 对齐盲区+差集二次方+五项 P2）+ `3d6ee12`（rebase 后行长超限修正） |
| T13 dedupe review CLI（AC-7.3） | `repo.list_candidates`/`decide_candidate`；`same_as(decided=merged)` 查询层聚合语义；`crawler dedupe review\|groups` 子命令组 | `0e8cb75`（feat）+ `6f9adb0`（NEEDS_FIX：kind 隔离判到"对"，堵住 preprint 对被 merge 折叠） |
| T14 verify 全库扩展（AC-7.4 前半，依赖 T1） | `verify.py` 扫描范围 +si/+fulltext 两段，`missing_file`/`orphan_file`/`hash_mismatch` 同构扩展 + 新增 `stale_fulltext` 信息级 | `d9cd445`（feat）+ `ca53424`（`_optional_text` 列缺席分支直测补齐） |
| T15 econsoc 回看窗闭合（检查单 #6） | 移植 aaai_ojs F3 的跨卷分区缓存结构，修当前年首拉完整性（窗口外早发论文漏收缺口闭合）；ECMA `[UNRESOLVED①④]` 不在本卡范围（§8 出列） | `0b14661`（fix）+ `b12f135`（`_cached_partition` cache-hit 取舍裁决记录） |
| T16 preprint↔published 关联报告（AC-7.4 后半，依赖 T10） | 报告生成（markdown，沿 `report.py` 惯例），preprint_of 边聚合视图 | `056c71a`（feat）+ `abeacee`（去杜撰引注+排序测试补 tiebreak） |
| T17 Database 构造审计（检查单 #10） | 全库 `Database(` 构造点 88 处/43 文件四分类甄别，36 处补资源纪律；产出 [db-construction-audit](2026-07-27-db-construction-audit.md) | `3ed1d7a`（feat/test）+ `5824a71`（口径外盲区收口：7 处 `_seed_v1` 裸持连接改 `closing()`） |
| T18 AC-BF 转正 + AC-7 验收骨架（依赖 T6/T11） | `acceptance-criteria.md` 回填 AC-BF 正式编号 + AC-5.1b 承接指针；AC-7 验收记录模板骨架 | `3760dcc` |

### 3.2 W4：T19 在线验收批

`e77349c` 起草 [AC-7 验收记录](../testing/records/2026-07-27-ac7-acceptance.md)：AC-7.1 真实抽样
（`arxiv_econ_th` 3 篇，标题比 0.0000×3）、AC-7.2 环境探测（本机无 GROBID/playwright，条件项未执行）、
AC-7.3/7.4 真实库亲跑、检查单 #11（nber 隔离验证 PASS + `asset-pricing` 端到端**首跑崩溃**——即
下方 P0 缺陷的在线首次触发）、repec bulk 快照首拉（`nberwo.rdf` 404 探底 + `nberwo2026.rdf` 成功，
三项 [未实测] 收窄两项）。本卡在过程中发现的 P0 缺陷与遗留的两处 NEEDS_DECISION 移交本 session 处置。

### 3.3 T20 终态独立审计 + 三条修复批闭环（本 session 主体工作）

**T20**（[plan §4](../plan/phase7-implementation-plan.md)）＝ Opus 深审×2（①extract+
browserfetch+三消费方；②repec+merge 建边+dedupe 聚合）+ Sonnet 面审×1（其余：谓词/FTS/verify/
cooldown/回看窗/审计卡），审查规格＝亲自构造对抗输入+变异测试（P6 教训⑩先例）。抓出 **4 处
跨卡缝缺陷**（R1 域两处 F-1/F-2、R2 域两处 F-3/F-4），叠加 T19 在线批自行发现的 **P0**（不计入
T20 的"4 处"，因其发现渠道是真实在线执行而非静态/对抗审查）。三条修复批均经"执行→独立审查→
回修→复核→controller 合并+门禁"闭环：

**① P0（`crawler subs watch` 遇 crossref 偏日期即整轮崩溃，T19 在线发现，AC-7 记录 §4 缺口 3）**：
main 提交 `75b33f2`+`c04c8c4`。现象：`asset-pricing` 预设烧完 7 页 ssrn 游标后崩溃，arxiv/nber
两条腿一次没跑到，无 run 记录、无日报、裸 traceback。两个独立缺陷：**A（语义）**——crossref 的
`_format_date_parts` 故意产出 partial `'YYYY'`/`'YYYY-MM'`，而 `watermark._parse_date` 只认完整
ISO；修法拆双路径：宽松面 `_try_parse_date` 只用于本轮 `seen`（解析不了计数跳过，经
`advance_with_report`→WARNING），存储侧 `_parse_date` 保持 fail-loud。**B（结构）**——`advance()`
在 `run_watch` 的 per-step 循环里裸调用，一个源的水位故障不仅掀掉整轮、还饿死其后的源；修法新增
真隔离两层：**源级**在 `_advance_source`（记一条失败、其余源照跑），**订阅级**在 `run_watch_all`
（坏订阅记失败占位 `RunSummary`、其余订阅照跑、`exit_code_for` 返回 1，CLI 优雅面）。**首次
`75b33f2` 提交独立审查判 NEEDS_FIX**：其 `except WatermarkInvalid` 兜底在生产路径**结构性抛不出**
（审查实证：整个 revert 掉 `watch.py` 全树 4557 照绿，属死代码），真正需要兜住的故障点（订阅级
`--all` 下一句裸列表推导会被一个坏订阅整体掀翻）未被兜住；**`c04c8c4` 回修**删死兜底、把隔离
建在真故障层（`run_watch_all`）、订正冒名用例（其 docstring 曾自称覆盖"缺陷 B"、实际覆盖的是
缺陷 A 的多源场景）、CLI 优雅面、P2 五项——**复审 APPROVE**（变异体测试恰红、对抗输入全过）。

**② R1（T20 F-1/F-2，ssrn 模式 B 闭包生产端漏接线 + 签名 URL 未脱敏）**：main 提交
`46fade4`/`b060c5b`/`9f1d772`/`79450fb`/`d6079e7`。**F-1**——design/11 §4.4 的"同批约束"由一对
接缝构成，T6 只落了消费端（`fetch_one(resolve_in_context=…)`），T11 三消费方接入卡漏了生产端
（`grep -rn resolve_in_context src/` 修前仅 `browserfetch.py` 自命中）：ssrn 模式 B 的 volatile
`Delivery.cfm` URL 从未被解析，全文结构性取不到。修法＝**能力发现式接线**（`BrowserContextResolver`
鸭型协议，adapter 实现 `resolve_in_browser_context` 即声明同批约束，沿 `isinstance` 先例、无
adapter 名单）+ `classify_or_raise`（同批解析闭包与主路径共用同一份判定语义）。**F-2**——F-1 接线
后带签名 token 的 volatile URL 开始在真实链路流动，两层脱敏面均漏它：`sensitive.py` 单一权威源
补签名族关键词，`browserfetch.py` 在构造点脱敏（`BrowserFetchOutcome.url` 两条返回路径 + 导航
异常消息）。**独立审查判 NEEDS_FIX**（P1）：两跳之间（landing→volatile）限速间隔丢失，退化为
2 请求突发——修法把 `wait_rate` 下移至紧贴它保护的那一次导航之前（`resolve_in_context is None`
时闸位置逐字不变，aea/wiley 两消费方零影响）；另有 P2 六项（token 变体补全、第四 sink 脱敏面
补齐 tasks.fail/block、护栏名实相符收紧、href 左边界防诱饵属性、runbook 三处订正）。**复审
APPROVE**（时序锁死 `wait→goto(landing)→wait→goto(volatile)→wait→download`，单跳路径零影响）。

**③ R2（T20 F-3/F-4，repec w/t series 塌缝 + list/search 聚合语义矛盾）**：main 提交
`243ef10`/`93ffedd`/`82fbfa9`。**F-3**——`handle_from_doi` 原取 `series_id[1:]` 去首字母，令
`10.3386/w{n}` 与 `10.3386/t{n}` 塌进同一 handle：两篇不相交的论文共用一个 `(repec, handle)`
锚点，t 的元数据静默污染 w 记录 + 落一条高置信假 `candidate_duplicate`（实测：混合库跑一轮
enrich 即产 1 条假候选）。修法＝**w-only 收窄**（`t` 及其余非 `w` 前缀一律不映射，计"结构性
不可寻址"）。**F-4**——同一个库、同一批人工 merge 决策，`crawler list` 默认按 `same_as(merged)`
折叠只显示 1 行，`crawler search` 恒显示 2 行；根因＝`fold_merged` 内联写死 `row["id"]` 只服务
`list_papers` 一种列形状，`search_papers` 行列名是 `paper_id`（D-034 契约），一进折叠即
`IndexError`。修法＝`repo.display_row_paper_id` 唯一取 id 口径，两条展示路径共用同一份折叠实现；
`search` 新增 `--aggregate/--no-aggregate`（默认开，与 `list` 同名同义同默认）。**审查判代码面
PASS**（4/4 变异有效、对抗全过），**唯一阻断项＝文档账缺失**（两处修复均推翻 approved/implemented
状态的既有契约却零记录，违反 AGENTS §3/§5）——`82fbfa9` 补账：新增 **D-036** ADR（supersedes
D-035 决策 4 两处 + revises D-034 决策 5）+ `aggregators.md §5.7` 五处修订 + §9 变更表 #21，代码
与测试零改动。

### 3.4 在线重跑（卡 D）

main 提交 `0a9ce11`。P0 修复合入 main 后，在 `test/p7-ac7-rerun` 分支重跑 `asset-pricing` 预设
三源端到端——**12 请求（ssrn 7 + arxiv 4 + nber 1，全部 200）、EXIT=0**，三腿全跑、
`subscription_run` 行 + 当日日报 + 三源水位三件套俱全，入库 52 篇（paper 127→179）。**这是 P0
修复的首次真实数据验证**：窗内 5670/5696 条候选（99.5%）携 partial `'2026'` 日期，按修复语义
从 `watermark_seen` 剔除、不推进水位，经 WARNING 可观测（`stage=watch venue=ssrn`），整轮
**不受影响**——坐实"partial 是 SSRN 在 crossref 上的常态形态而非边角坏数据，修复前这条腿在任何
真实窗上都跑不完"的严重性判读。预算：`T19-rerun` 12 请求，额度全部来自 controller 裁决的三行
调剂（`T19-bf` 因 playwright 未装整行未动、全额调剂 10 + `T19-nber` 余 1 + `机动` 余 1），三行
调剂后恰好各自见底，无新增超线。详见 [AC-7 记录 §2.7(b)](../testing/records/2026-07-27-ac7-acceptance.md)。

## 4. 在线预算总账

汇总 [AC-7 记录 §3](../testing/records/2026-07-27-ac7-acceptance.md) T19 本卡账本 + §2.7(b)
T19-rerun 调剂批，两批合计在线请求 **33**（T19 本卡 21 + 重跑批 12），均在
[phase7-implementation-plan.md §3](../plan/phase7-implementation-plan.md) 全 Phase 专项 ≤40
请求预算内：

| 预算行 | 上限 | T19 本卡实耗 | 重跑批调剂 | 终态 | 状态 |
|---|---|---|---|---|---|
| `T8-robots` | ≤2 | **2** | 未动 | **5/2**（既有 3/2 + 本卡 2） | ⚠ 超线（已裁决，见下） |
| `T8-bulk` | ≤4 | 2 | 未动 | 2/4 | ✅ 未见底 |
| `T19-bf` | ≤10 | 0（playwright 未装，整行未执行） | +10（全额调剂） | 10/10 | ✅ 经调剂见底 |
| `T19-nber` | ≤9 | 8 | +1 | 9/9 | ✅ 经调剂见底 |
| 机动 | ≤10 | 9 | +1 | 10/10 | ✅ 经调剂见底 |
| `T19-rerun`（调剂批，无独立额度行） | 12（硬顶 13） | — | 12 | 12/12 | ✅ 与跑前定量精确吻合，未触硬顶 |

**`T8-robots` 超线裁决**（AC-7 记录 §4 缺口 2 追加注记，本报告同步说明）：`scripts/repec_snapshot.py`
把 fable 裁决的条件 (a)"真实拉取前对目标镜像重核 robots"实现为**每次调用无条件发 1 次请求、
不提供跳过开关**（有意的合规设计，非缺陷）——"跑一次真实快照拉取"与"不再消耗 `T8-robots`"在
当前实现下结构性互斥。**controller 裁定**：该行语义修正为**"随每次真实快照拉取联动 +1"**（采纳
AC-7 记录原 NEEDS_DECISION 选项①，弃选项②"允许缓存判定"——与条款 a"不缓存、不跨域外推"明文
冲突）。历史超线 5/2 如实留档不追溯改写，定性维持"协调可见性问题"而非"AC-0 红线触碰"（历次动作
本身都是"取数前先问许可"的合规动作）。`phase7-implementation-plan.md §3` 该行"≤2"字面不因本
注记改写（该文件 `status: approved`，改动须走仲裁）——语义更新由 AC-7 记录该条注记 + 本节承载，
供 Phase 8 预算表制定时参照。

## 5. AC-7 验收终态

| AC | 判据 | 终态 | 依据 |
|---|---|---|---|
| AC-7.1 全文抽取 | 抽样 PDF 经 extract 得非空文本，标题与 DB 记录匹配 | **PASS**——离线 2/2 + 在线真实 3/3（`arxiv_econ_th` 3 篇，标题比 0.0000/0.0000/0.0000，远低于 0.15 阈值，阈值一次修订额度本卡未动用） | AC-7 记录 §1/§2.1/§2.3 |
| AC-7.2 GROBID 可选 | 开/关两模式均产出，关闭时降级为纯文本不报错 | 离线 **PASS**（三态各一例）；在线**条件项未执行**（本机无 GROBID 服务，三端口探测全部连接失败；关模式的真实旁证已有——§2.3 三篇均在未配置 `grobid_url` 下走纯文本路径全部成功） | AC-7 记录 §1/§2.1/§2.2 |
| AC-7.3 去重审核工具 | `dedupe review` 逐条展示证据，merge/reject 后 same_as/rejected 正确落库且可回滚 | **条件 PASS**——离线三件套齐备且全绿（`test_cli_dedupe.py` 14 例+`test_dedupe.py` 31 例）；在线真实库 `dedupe review`/`groups` 均正常返回空态（本库为单源 arxiv 语料，零跨源重叠，`candidate_duplicate` 天然为空）；空态不冒充在线通过，如实标注 | AC-7 记录 §1/§2.4 |
| AC-7.4 全库对账 | 全库 `verify` 通过；preprint↔published 关联报告生成 | **PASS**——真实库 `crawler verify` 亲跑 EXIT=0；**主动注入缺陷复验**：`data/fulltext/` 植入孤儿文件→正确判 `[orphan_file]`+EXIT=1，移除后复跑回 EXIT=0，证明三段扫描面确含 fulltext/；`crawler preprint-report` 正常生成（本库 `preprint_of` total=0，单源语料下属预期） | AC-7 记录 §1/§2.5 |

`status: draft`——§4 两处 NEEDS_DECISION（`T8-robots` 额度/条款、P0 诊断表述订正）均已裁决落档
（本报告 §4 + AC-7 记录本身），转入待 fable 终审签署阶段，本报告不代行签署。

## 6. 检查单 16 项对账表

逐项引 [phase6-report §6](2026-07-26-phase6-report.md) 原文出处 + [phase7-implementation-plan.md
§4/§8](../plan/phase7-implementation-plan.md) 处置：

| # | phase6-report §6 原文摘要 | 本 Phase 处置 | 出处 |
|---|---|---|---|
| 1 | browser-fetch 横切件实现 + `AC-BF.x` 转正 | **已闭合**：T6（核心横切件）+ T11（三消费方接入）+ R1 修复批（F-1 生产端漏接线 + F-2 签名 URL 脱敏，独立审查 NEEDS_FIX 回修后 APPROVE）；T18 完成 AC-BF 编号转正 | plan §4 T6/T11/T18；§3.1/§3.3 本报告 |
| 2 | repec enrich 首批候选 | **已闭合**：T8 落地（bulk ReDIF 零网络 enrich）+ D-036 收窄（w-only 映射，R2 审查发现 w/t 塌缝后修正） | plan §4 T8；D-035/D-036 |
| 3 | OpenAlex 补枚举 ladder(a) | **未立卡**：plan §8 显式出列，defer P8 候选，条件原样沿账 | plan §8 |
| 4 | arxiv `search_query` 谓词/多分类 fan-out | **已闭合**：fan-out 半边已于 Phase 7 开工前经 `fix/arxiv-category-fanout` 合并（本 Phase 开工基线 main @ `d56313f` 即含此修复）；谓词半边由 T9（参数化谓词机制）本 Phase 落地 | plan 开工基线说明；plan §4 T9 |
| 5 | preprint_of 建边零实现 | **已闭合**：T10 落地（`merge.py` 新增建边分支，独立审查 NEEDS_FIX 回修双向矛盾环等三项 P1） | plan §4 T10 |
| 6 | aaai/econsoc 回看窗完整性闭合评估 | econsoc 半边**已闭合**（T15：跨年分区缓存+当前年首拉全量收割）；ECMA `[UNRESOLVED①④]` 仍属 **§8 出列**（Cloudflare 阻塞，待站点风险面稳定后专项批） | plan §4 T15；plan §8 |
| 7 | E-2 冷却键全量统一 + `cooldown` CLI | **已闭合**：T3 落地（`pipeline/cooldown.py` 公用模块 + `crawler cooldown status\|clear`，独立审查 NEEDS_FIX 回修路径穿越防护） | plan §4 T3 |
| 8 | http→auth import 分层 | **已评估登记**：T6 卡内评估"仅当横切件确需更细分层才动"，本 Phase 未触发该条件，维持登记状态（非阻断，未发现新缺陷） | plan §4 T6 已裁决歧义段 |
| 9 | 幻影字段文档清账 | **已在 Phase 6 T10 闭合**（phase6-report §6 #9 原文："此项已闭合，列入本检查单仅为完整性存档"）——Phase 7 无需处置 | phase6-report §6 #9 |
| 10 | 全库 76 处/41 文件 `Database` 构造审计 | **已闭合**：T17 实测 **88 处/43 文件**（存量演进所致口径增长，非漂移，见该报告 §1 差异说明）；A 类 52 处/33 文件确认已兜底不动，B 类 36 处/10 文件补资源纪律，C/D 类零命中；另于 T12/T17 rebase 后发现 7 处 `_seed_v1` 裸持连接口径外盲区，已收口 | [db-construction-audit](2026-07-27-db-construction-audit.md) |
| 11 | nber 隔离在线验证 + `asset-pricing` preset CLI 端到端补验 | **已闭合**：T19 §2.7(a) nber 隔离验证 **PASS**（1 请求）；§2.7(b) `asset-pricing` 首跑因 P0 崩溃未完成，P0 修复后**卡 D 重跑 PASS**（12 请求，三源三策略水位推进各验一次） | AC-7 记录 §2.7 |
| 12 | AEJ 四刊 catalog 行内注记与 notes 不一致清账 | **已闭合**：T5（检查单 #12+#15 合并处置） | plan §4 T5 |
| 13 | aaai 全文回填批 ~5049 篇 | **未动**：plan §8 显式出列，待用户令另行插单 | plan §8 |
| 14 | elsevier T7b / S2 key 等外部依赖沿账 | **未动**：plan §8 外部依赖沿账，key 到位即按既有 runbook 补验 | plan §8 |
| 15 | `economics-journals.md`/`publishers-platforms.md` ECMA 行 adapter 归属表述不一致清账 | **已闭合**：T5（与 #12 合卡处置） | plan §4 T5 |
| 16 | 机动预算运行时共享账本 | **已闭合**：T4 落地（`.paper-crawler/state/budget.json` + `scripts/budget_ledger.py` + `docs/process/online-budget.md` 三条纪律） | plan §4 T4 |

## 7. 事件与教训

- **① 跨卡缝缺陷的共同形态——"各卡局部正确、集成点无主"再度复现（P6 教训④的 Phase 7 变体）**：
  R1 域的 F-1（ssrn 模式 B 生产端漏接线）与 R2 域的 F-4（search/list 聚合矛盾），根因结构高度
  同构：**接口的两端分属两张不同任务卡**（T6 只落消费端、T11 才该落生产端；T13 定的聚合语义只
  服务了 `list_papers` 一种列形状、T12 新增的 `search_papers` 返回列契约与其不兼容），各卡在
  自己的验收范围内都测试通过、都不算"错"，但接缝本身没有默认属主。这与 Phase 6 报告记录的
  "批内去重三卡组合缺口"是同一类问题的再次发生——教训是这类"横切能力的生产端/消费端分属两卡"
  或"同一查询结果的两种展示命令分属两卡"的场景，若任务卡文本没有显式点名接缝归属，就只能靠
  **事后审查**（本次是 T20 终态独立审计，而非任何单卡自身的验收）兜底发现，检查单 #1/#4 已在
  卡文本尝试"依赖 T6/T11"这类声明，但仍需要审查层面的对抗构造才真正抓到漏接线；这提示"依赖
  声明"本身不足以保证接缝被完整覆盖，仍需审查阶段专门针对"两端分属两卡"的场景构造端到端验证。
- **② P0 缺陷的初次修复被独立审查判"死代码"——审查价值不止是"抓新缺陷"，也在于"验证修复本身
  命中了真故障点"**：P0 缺陷 A（partial 日期语义）与缺陷 B（`advance()` 未隔离）本是两个独立
  问题，`75b33f2` 对 A 的修复完全正确（9 个红用例锁死、审查"一行未动"），但对 B 的修复
  （`except WatermarkInvalid` 兜底）经审查亲自反证（revert 掉 `watch.py` 全树 4557 测试仍
  照绿）证实是**结构性抛不出的死代码**——真正的故障点（`run_watch_all` 的裸列表推导）根本没被
  触及。这是一个有价值的判例：**"修复后测试全绿"不足以证明修复命中了真实故障路径**，尤其当
  新增的 `except` 分支本身缺少"证明它确实会被触发"的反证测试时；`c04c8c4` 回修把隔离建在真正
  的故障层，并为"死兜底"补上"revert 后原树仍绿"这类结构性反证，是本次审查方法论上最值得记录
  的一点，也回应了 P6 检查单曾提到的"变异测试恰红"纪律——本次是其在诊断（而非仅在验证）阶段
  的应用。
- **③ D-036 补账事件——"代码先落地、文档账后补"在本项目纪律下不被接受，即便代码本身完全正确**：
  R2 修复批（`243ef10`/`93ffedd`）的独立审查结论是"代码面 PASS"（4/4 变异有效、对抗全过、
  commit message 事实断言全真）——即代码修复本身没有任何缺陷。但审查仍判定为**唯一阻断项**：
  两处修复都**推翻了 approved/implemented 状态的既有契约**（D-035 决策 4 的映射边界、D-034
  决策 5 的 `search` 命令面）却没有同批产出 ADR/文档记录，违反 AGENTS §3/§5"推翻既有决策须
  新增 ADR 标注 supersedes"的纪律。这与"代码对不对"是两个独立的判定轴——本项目把"决策留痕"
  本身当作与"实现正确性"同等级别的验收项，纯技术上完美的修复仍会因文档账缺失被判 NEEDS_FIX。
  这是本项目文档纪律（doc-conventions + AGENTS）在 Phase 7 的一次实证：**修复的正确性与修复的
  可追溯性是两件必须分别验收的事**，前者不能替代后者。

## 8. 已知限制（如实记录）

- **AC-7.3 在线验收止步于空态**：本库为单源 arxiv 语料（127 篇，零跨源重叠），`candidate_duplicate`
  天然为空，去重审核工具的在线证据由离线三件套载体承载。真实候选需再取一路跨源重叠语料（如
  nber crossref 前缀枚举），本 Phase 在线预算不足以覆盖（详见 §9 backlog ⑨）。
- **AC-7.2 在线为条件项**：本机无 GROBID 服务、亦无 playwright（`[auth-browser]` extra 未装），
  GROBID 真实开模式与 `AC-BF` 真实冒烟（`T19-bf` 预算行）均未执行；`T19-bf` 整行额度已在卡 D
  重跑批中全额调剂给 P0 修复的在线验证，转入 Phase 8 新批（§9 backlog ⑩）。
- **`t` 系列 series 段归属与 id 段前导零对称性仍 [未实测]**：D-036 已按正确性论证提前收窄 `t`
  为不映射（与是否实测无关），但 `t` 真实落在 RePEc 哪个 series 段、handle id 段前导零上游是否
  统一，均需再取一个 series 的快照才能核验；每次 `repec_snapshot.py` 调用强制再消耗一次
  `T8-robots`，本 Phase 未再触该行（AC-7 记录 §2.6 如实留缺口）。
- **日报落盘根 CWD 相对、与 config-home 相对的库/state 不同基准**：`subs/watch.py` 的
  `DEFAULT_REPORT_ROOT` 是仓库相对路径，从 worktree 调用时日报与真实库分家（卡 D 重跑批实测
  发现，AC-7 记录 §4 缺口 7），design 层面的根基准取向问题，本 Phase 未处理（§9 backlog ⑧）。
- **`T8-robots` 预算行超线 5/2**：已按 §4 裁决"随每次快照拉取联动 +1"处置，历史超线如实留档不
  追溯改写，非 AC-0 红线触碰。
- **CLI `--issue` 单用限制**：`--issue` 必须搭配 `--volume`，arxiv 月度虚拟桶 `IssueRef.volume`
  恒为 `None`，两条约束叠加后无法表达"只跑某一个月桶"，T19 改从 `PipelineRunner.pull()` 直调
  `Selector` 规避（同一条 pull 级联，仅选择器更窄），CLI 参数校验层本身未放宽（§9 backlog ⑪）。
- **search 折叠丢类内最佳 rank 未记 docstring**：D-036 落地的聚合展示未在 docstring 中说明折叠
  对排序/rank 选取的影响，R2 审查 P2 项登记（§9 backlog ⑦）。
- **S2 生产端接线无契约级锁**：R1 审查点名 S2 生产端接线只有 ssrn 集成用例在锁、无契约级锁，
  裁决不加锁（YAGNI），已知接受（§9 backlog ⑥）。

## 9. Phase 8 开工检查单

1. **RunSummary 跳过信号进日报 + 连续 N 轮零推进告警**（P0 独立审查 P2-5/P2-7，`c04c8c4` commit
   message"范围外"段登记，controller 已裁单开卡挂 backlog）。
2. **`SUBSCRIPTION_LEVEL_SOURCE` 值形态测试锁 + e2e 恒真断言修正**（P0 复审 P2-A）。
3. **占位 summary 与逐条事务 docstring 宽度措辞 + 单订阅文案**（P0 复审 P2-B/C）。
4. **`papers.ssrn.com` robots Disallow 面核验**（[design/11 §2](../design/11-browser-fetch.md)
   红线 4 前置门；首次真实演练前必核，`tests/manual/browser_fetch_runbook.md` §0 硬拦在）。
5. **F-2 脱敏对真实 ssrn Delivery 形态未核验**：token 可能在路径段/cookie 而非查询参数，当前
   按键名的脱敏对其可能零覆盖，`browser_fetch_runbook.md` 行 7 已登记，真实演练时先看形态再定
   是否扩展。
6. **S2 生产端接线无契约级锁**（已知接受，YAGNI，非阻断，登记供未来重估）。
7. **search 折叠丢类内最佳 rank 未记 docstring**（R2 审查 P2-2/3/4）：需补响亮校验数据条件式
   告诫 + `id`/`paper_id` 两列并存时的优先序说明。
8. **日报落盘根 CWD 相对 vs config-home 两套 `reports/` 并存**（卡 D 缺口 7，AC-7 记录 §4 已登记，
   需 P8 设计裁决该根的解析基准）。
9. **AC-7.3 在线真实候选**：需跨源重叠语料（如同一批论文经 ≥2 源入库）才能产生真实
   `candidate_duplicate`，本 Phase 在线预算不足，转 Phase 8 新批。
10. **AC-7.2 GROBID 真实开模式 + `AC-BF` 真实冒烟**（playwright）：`T19-bf` 预算行已在卡 D 调剂
    用尽，需 Phase 8 新批预算 + 本机装好 GROBID/playwright 环境。
11. **CLI `--issue` 单用限制**（T19 缺口 4）：`--issue` 校验层按 venue 形态放宽（preprint_channel
    月桶允许 `--issue` 单用）。
12. **OpenAlex 补枚举 ladder(a)**（§8 出列沿账）：P7 无余力承接，defer P8 候选，条件原样沿账。
13. **aaai 全文回填批** ~5049 篇：待用户令另行插单，本 Phase 不动。
14. **外部 key 四项沿账**：elsevier API key（**BLOCKER-1**，跨 Phase 3–7 五阶段未清）、S2 key、
    wiley TDM token、oup SSO 首登 runbook——均为计划内外部依赖，非阻断，待用户执行。

## 10. 门禁

`make check`（`sync-dev` + `ruff check` + `ruff format --check` + `mypy src` +
`pytest tests/unit tests/contract tests/integration --cov=paper_crawler --cov-fail-under=80`）
controller 亲跑（main @ `0a9ce11`）：

```
4617 passed, 31 skipped, ... warnings
Required test coverage of 80% reached. Total coverage: 98.98%
EXIT=0
```

ruff/mypy 均无输出（全绿）。中途各提交落款处亦各自记录过亲跑门禁数字（如 `c04c8c4`"4562 passed /
47 skipped / 6 deselected"、[db-construction-audit](2026-07-27-db-construction-audit.md) §7
"4550 passed / 31 skipped"）——这些是各自分支在合并进 main 前、于隔离 worktree 内亲跑的**中间
态**（测试子集/合并进度不同导致计数不同），**非门禁回退**；本报告引用的 **4617 passed / 31
skipped / 98.98%** 是 main @ `0a9ce11`（全部 68 commits 合并完毕后）的**最终态**，两者不冲突。
skip 构成本卡未逐条重新甄别（沿用既有 contract 能力缺口型分类，未展开逐例溯源）。

`crawler venues lint` 58 个 venue 全过；adapter 集合等值自断言（`test_cli_canary.py`）21/21
全过（20→21，新增 `repec`）。

## 11. 签署

- **T21 收尾（2026-07-27）**：22 卡全交付（主线 T1–T18 + T19 在线验收批 + T20 独立审计批 + P0/
  R1/R2 三条修复批闭环 + 在线重跑卡 D）；门禁 3832→4617（+785 测试，coverage 98.98%）；AC-7
  四条判据 AC-7.1/7.4 PASS、AC-7.3 条件 PASS、AC-7.2 离线 PASS/在线条件项；D-033/D-034/D-035/
  D-036 四条 ADR 均 accepted；在线预算 33（本 Phase 专项 ≤40 内）+ `T8-robots` 超线一处已裁决；
  检查单 16 项全数对账（§6）；Phase 8 开工检查单 14 项产出（§9）。判定列待 controller 终审裁决。
- **终审（待 controller）**：全分支终审、门禁亲跑复现、签署、打 `tag phase-7`（T22 卡，fable
  亲自执行，不在本报告职责范围）。
- **fable 终审判定（2026-07-27，T22）**：**达成，放行打 `tag phase-7`**。依据：①三条修复批审查链
  逐支复核——P0（初审 NEEDS_FIX 坐实死代码兜底→回修删死兜底+真隔离两层→复审 APPROVE，变异恰红
  不多不少）、R1（审查 NEEDS_FIX 坐实两跳限速突发→回修落位+P2 六项→复核 APPROVE，时序锁死、单跳
  零影响）、R2（审查判代码面 PASS、文档账缺失→D-036 补账，controller 合并前亲核四处修订）；
  ②在线重跑 §3.4 具备真实证据（12 请求精确吻合定量、三腿全跑、P0 修复 5670 条 partial 剔除实证）；
  ③终审门禁于终态树 main @ `a9d0d68` 亲跑复现 **4617 passed / 31 skipped / 98.98% / EXIT=0**、
  `venues lint` 58/58（签署提交 docs-only 不影响门禁面）；④AC-7 记录同批转 `approved`（该记录
  §5 签署行）；⑤残留分支于 tag 前清零（21 个已合并 worktree 分支 + 本 session 修复批分支）。
  条件项如实沿账不阻塞（GROBID/playwright 环境类 + key 类外部依赖，D-018 分层先例，Phase 8
  开工检查单 §9 承接）。
