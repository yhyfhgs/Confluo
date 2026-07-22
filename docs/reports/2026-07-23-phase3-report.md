# Phase 3 阶段报告 — 聚合元数据层（2026-07-23）

> 格式仿 [2026-07-22-phase2-report.md](../reports/2026-07-22-phase2-report.md)。**本稿为收尾中草稿**：
> T8（AC-3.1~3.5 汇总验收记录、AC-0 系统性扫描、`tag phase-3`）尚未完成，controller 尚未终验签署——
> 文中判定性表格的"判定"列均留 `[待 controller 终验签署]` 占位，本稿只陈述证据、不代为下判定。
> 判定依据：[development-plan §Phase 3](../plan/development-plan.md)、
> [acceptance-criteria AC-3/AC-0](../testing/acceptance-criteria.md)、
> [phase3-implementation-plan](../plan/phase3-implementation-plan.md)、
> [AC-3.5 验收记录](../testing/records/2026-07-23-ac35-acceptance.md)、
> [decision-log D-021/D-022](../plan/decision-log.md)。
> 代码版本：main HEAD `47bb72a`（**未打 tag**）。`phase-2..HEAD` 共 62 commits / 12 merges；其中
> `775b29b..52861a8`（10 commits / 2 merges）为 Phase 2 收尾尾段（openreview AC-2.1/2.2 在线层终审
> + Phase 2 终签），`e8256bb`（"Phase 3 实施计划草案"提交）起 52 commits / 10 merges 为 Phase 3
> 本体——10 次 merge 精确对应 phase3-implementation-plan §4 的 10 张任务卡（F1/F2/M1 + T1~T7）；
> T8 尚未产生独立 merge。

## 1. DoD 判定

development-plan.md Phase 3 DoD 原文："任选 5 本期刊（含 QJE、JFE）不写任何出版社爬虫即可产出
完整期目与论文清单；OA 副本命中率报告生成。" phase3-implementation-plan §Goal 另加"AC-3.1~3.5
全过"为内部判据，一并列入本表。

| DoD 项 | 判定 | 证据 |
|---|---|---|
| 5 刊（含 QJE/JFE）零爬取产出完整期目+论文清单 | [待 controller 终验签署] | [AC-3.5 验收记录](../testing/records/2026-07-23-ac35-acceptance.md)：qje/jfe/jet/jpubeco/jbf 五刊 timeline 141/53/58/55/50 个出版年；抽样年（2024）枚举 parsed==`paper_count_claimed` 差异全 0；volume+DOI 全 5 刊 100% 覆盖；QJE 全史 `total_all=6655` ≥ D-019 锚点。记录自身给出"PASS（Phase 3 口径）"建议，并列 5 项待裁决 Concerns（C1~C5，见 §5/§6） |
| OA 副本命中率报告生成 | [待 controller 终验签署] | `src/paper_crawler/adapters/unpaywall/report.py`（T5 DoD 第二项）+ `oa-report` CLI；本次亲测覆盖率 100% |
| AC-3.1 强合并（同 DOI 混合双路→1 paper ≥2 identifier） | [待 controller 终验签署] | `tests/integration/test_merge_acceptance.py::test_ac_3_1_mixed_dual_path_one_paper_two_identifiers` + `::test_ac_3_1_mixed_dual_path_merges_across_doi_case_difference`，本次亲跑 2 用例通过。测试为**混合双路**（arxiv 经既有 `Repo.upsert_paper` pull 路径 + crossref 经 `MergeEngine.ingest` 路径），模块 docstring 注明"controller 2026-07-22 条件②的真实形态（不许两路都走 MergeEngine 自证）" |
| AC-3.2 弱信号候审（不自动合并） | [待 controller 终验签署] | 同文件 `::test_ac_3_2_wp_vs_published_two_papers_one_candidate` + `::test_ac_3_2_genuinely_renamed_title_no_candidate`，本次亲跑 2 用例通过（含"标题真改名不误判候选"反例） |
| AC-3.3 verify 三类检出+修复建议 | [待 controller 终验签署] | `tests/unit/test_verify.py`：缺文件/孤儿文件/哈希不符三类 + 排序/只读等辅助用例，共 14 用例，本次亲跑全通过 |
| AC-3.4 顺序无关（属性测试） | [待 controller 终验签署] | `tests/integration/test_merge_property.py::test_ingest_order_independent`（Hypothesis `max_examples=250`，满足 plan §4 T1"≥200 examples"判据，derandomize 固定种子防 flaky），本次亲跑通过。**适用边界**（模块 docstring 自述）：桥接 identifier（一个 stub 同时携带两个既有 paper 各自 identifier）场景顺序敏感，被显式排除在本属性测试范围外，由 `tests/unit/test_merge.py` 定向用例单独锁定确定性 |
| 五源 adapter 上线 + canary 注册 | [待 controller 终验签署] | crossref/dblp/unpaywall 三源 `healthcheck()` 已实现真实探测逻辑（非 `NotImplementedError`）；openalex/s2 的 `healthcheck()` 门控为"无 key→`NotImplementedError`→canary SKIP"（aggregators.md §5.3/§5.4，产品取舍非缺陷，本次随文档转正一并核实源码） |
| 每源在线冒烟（≤5 req/源；Phase 总预算 ≤100） | [待 controller 终验签署] | AC-3.5 记录请求台账：**实耗 33 请求**（局部 50 硬顶未近顶），含五刊 timeline/list + crossref/dblp/unpaywall 三源冒烟首跑与复跑 + D-019 锚点捕获，远低于 Phase 总预算 100；openalex/s2 无 key，未产生在线请求 |
| `make check` 全绿 / 核心覆盖率 ≥80% 不回退 | [待 controller 终验签署] | **本次复核（2026-07-23）亲跑发现不完全绿**：`ruff check`/`ruff format --check` PASS；`mypy src` PASS（73 源文件）；`pytest tests/unit tests/contract tests/integration` **2153 passed / 1 failed / 24 skipped**——`tests/unit/test_crossref_parse.py::test_parse_single_work_title` 失败（详见 §5）。覆盖率门禁本身达标：**99.18%**（≥80% 门槛，较 phase-2 tag 时 99.32% 微降 0.14pp） |
| 聚合源解析/映射模块覆盖 ≥90% | [待 controller 终验签署] | 本次亲测：crossref 98%、dblp 100%、openalex 99~100%（adapter/budget/parse 三文件）、s2 98~100%（adapter/parse）、unpaywall 100%（adapter/parse/report）；`merge.py`/`ids.py`/`verify.py` 均 100% |
| metadata_source/fulltext_source 分离语义落地（D-005） | [待 controller 终验签署] | `VenueSpec.metadata_source: str \| None`（纯附加）+ registry 校验落地；5 刊 YAML 均声明 `metadata_source: crossref`；本次亲跑 `crawler venues lint` → `OK：45 个 venue 全部通过 lint` |

## 2. 验收汇总

- **AC-3.5（五刊零爬取）**：独立验收记录已起草（[记录](../testing/records/2026-07-23-ac35-acceptance.md)，
  T7 implementer 撰，`status: draft`）。5 刊在线实跑：timeline 年级完整、抽样年枚举与
  `paper_count_claimed` 差异全 0、volume/DOI 100% 覆盖；QJE online-first 印刷年错位（2024 窗口
  46 篇中 20 篇 print year=2025）等口径差异均有解释。在线冒烟三件：crossref 首跑 2/3（1 处断言
  对 online-first 脆弱，非 adapter 缺陷，已随 `47bb72a` 放宽——但该次修复同时带出 §5 所述新回归）、
  dblp 首跑 2×503 复跑 2/2、unpaywall 1/1。**记录本身建议"PASS（Phase 3 口径）"**，并列 5 项
  Concerns（C1~C5）待 controller 裁决，本报告不代为签署。
- **AC-3.1/3.2（强合并/弱信号候审）**：由 `test_merge_acceptance.py` 4 个专属用例（`test_ac_3_1_*`
  ×2、`test_ac_3_2_*`×2）承载，本次亲跑全通过；**尚无独立汇总验收记录文档**（T8 待收口）。
- **AC-3.3（verify 对账）**：`test_verify.py` 14 用例覆盖缺文件/孤儿文件/哈希不符三类 + 排序/只读
  约束，本次亲跑全通过；`crawler verify` CLI 层输出含"正确修复建议"（缺文件→re-fetch 提示；
  孤儿→纳管/清理提示；哈希不符→corrupt 标记+re-fetch，plan T2 判据）。同样无独立汇总验收记录文档。
- **AC-3.4（顺序无关）**：`test_merge_property.py::test_ingest_order_independent`（Hypothesis 250
  examples）本次亲跑通过。**已知边界**（模块 docstring 自述，非本次新发现）：桥接 identifier
  场景的合并裁决本质顺序敏感（差异体现在 paper 行数/桥字段落点/候审边有无，但零丢失），此类
  输入被显式排除在随机属性测试范围外，由 `test_merge.py` 定向用例单独锁定——正式 AC-3.4 验收
  记录成文时应显式写出此适用边界，不宜无保留断言"顺序无关"。
- **AC-0 红线**：本次**未执行**系统性扫描（git 全历史+日志正则，Phase 1/2 先例）——
  phase3-implementation-plan T8 已列明此项，仍待执行，本报告不代为完成。本次文档复核范围内
  未见新增红线违反迹象（五源 adapter UA 均带 mailto；dblp `RatePolicy` 限速 ≥4s/req；无凭证
  硬编码；unpaywall email 经 obslog 脱敏，T5 先决条款已落地）——但这**不等于**系统性扫描已完成。

## 3. 交付清单

development-plan §Phase 3 范围逐项：

| 范围项 | 交付 |
|---|---|
| 合并引擎（T1，AC-3.1/3.2/3.4 载体） | `merge.py`（`MergeEngine.ingest`/`IngestResult`）+ `ids.py`（DOI/title_norm 归一）+ schema v2 迁移（`0002_title_norm.sql`：`title_norm` 列+索引，回填迁移器）；字段级来源优先级收敛表 `official>crossref>dblp>openalex>s2>heuristic`（D-021）落地 |
| verify 三类检出扩展（T2，AC-3.3 载体） | `verify.py` 扩展：缺文件/孤儿文件/哈希不符三类全检出 + 修复建议文案 |
| crossref adapter（T3，AC-3.5 载体） | `adapters/crossref/{adapter,parse}.py`：ISSN+日期枚举、cursor 深翻断点续拉、facet 逐年 timeline、静态 5 req/s 限速、healthcheck golden 转正（"Deep learning"） |
| dblp adapter（T4） | `adapters/dblp/{adapter,parse}.py`：卷索引发现+XML 解析、`ee→DOI` paper 级护栏、≥4s/req 限速；**审查期修复**真实线上 `<bht>` schema 与批量 dump `<dblp>` schema 不同构的 HIGH blocker（见 §4） |
| unpaywall adapter（T5） | `adapters/unpaywall/{adapter,parse,report}.py`：RESOLVE+回退链+OA 命中率报告；**先决**扩展 obslog email 脱敏正则（B-B4 条款）后再实现 adapter |
| openalex/s2 enrich 通道（T6） | `adapters/openalex/{adapter,budget,parse}.py`（duck-typed `enrich_batch` + 每日 credit 预算熔断）、`adapters/s2/{adapter,parse}.py`（key 门控批查）、`crawler enrich [--venue][--source]` CLI |
| 五刊 VenueSpec + AC-3.5 端到端（T7） | `venues/econ/{qje,jet,jpubeco}.yaml`、`venues/finance/jbf.yaml`（+ 既存 `jfe.yaml`）；[AC-3.5 验收记录](../testing/records/2026-07-23-ac35-acceptance.md) |
| Phase 2 移交修复（F1/F2/M1，本计划内先行派发） | F1：C-C 大 venue pull 可用性（`resolve_offline` 豁免限速闸 + `--limit` 前置圈选，D-022）；F2：C-D openreview venueid 异构缺陷（2018/2019 逐年 accepted 规则）；M1：`canary --record` 落盘、emnlp `supported_since` 补标、openreview meta 白名单 |
| 合规/文档 | D-021/D-022 两条新 ADR；`aggregators.md` 396→447 行（W0 扩写 + 双评审 19 条修订 + 本次转正对齐）；`metadata-apis.md` 增量复核归档 |

统计：**62 commits**（`775b29b..47bb72a`，含 12 次 merge）；其中 10 commits/2 merges 为 Phase 2
收尾尾段，`e8256bb` 起 52 commits/10 merges 为 Phase 3 本体——10 次 merge 精确对应
phase3-implementation-plan §4 的 10 张任务卡（F1/F2/M1 + T1~T7）。测试从 phase-2 tag 的 1629
passed / 8 skipped（99.32%）增至本次亲跑的 **2153 passed / 1 failed / 24 skipped**（99.18%）；
新增 21 个 `src/` 聚合层文件（5 源 adapter 包共 17 文件 + `merge.py`/`ids.py`/schema migration
+ openreview C-D 修复文件）、84 个 `tests/` 文件、6 个新 fixture 目录（crossref/dblp/openalex/
s2/unpaywall + openreview 补充）、4 个新 venue YAML；整体 **169 files changed / +42310 / -340**
（`git diff --shortstat phase-2..HEAD`）。已注册 adapter 由 8 个（Phase 2 末，含 mock）增至
**13 个**（新增 crossref/dblp/openalex/s2/unpaywall）；`crawler venues lint` 本次亲跑
`OK：45 个 venue 全部通过 lint`。

## 4. 过程与质量机制

- **详设硬门禁延续**：`aggregators.md` 双评审（W0）一轮即输出 19 条修订、**7 BLOCKER 闭合**
  （`998ac40`）——延续 Phase 2"评审优先于开工"纪律；修订涵盖优先级表假 `[UNRESOLVED]` 清除
  （改用 D-021 冻结表）、openalex/s2 收回 ENUMERATE 改 duck-typed `enrich_batch`、unpaywall 删除
  未经 [LIVE] 验证的批量端点、healthcheck `NotImplementedError`→SKIP 语义统一等，详见
  aggregators.md §9 修订记录 #9。
- **波次并行**（按 phase3-implementation-plan §5 设计）：`W0(勘察复核‖F1‖F2‖M1) → W1(T1‖T2) →
  W2(T3‖T4) → W3(T5‖T6) → W4(T7→T8)`。**实际合并序**（`git log --merges`，oldest→newest）：
  M1 → F2 → F1 → T2 → T3 → T5 → T4 → T1 → T7 → T6——与设计波次的依赖关系一致（T7 依赖
  T1+T3+T5，三者均先于 T7 合并；T6 无下游依赖，晚于 T7 落地不违反依赖顺序），但合并时间序不
  完全等于设计波次的严格分组。本报告不对"是否符合波次纪律"做定性判断，仅如实记录顺序。
- **评审拦截战果**（若无独立审查将带病进入生产的缺陷，本次可从 commit 记录复核的部分）：
  1. **dblp 真实 schema HIGH blocker**（`c144573`）：初版实现假定线上单届卷 XML 与
     `dblp.xml.gz` 批量 dump 同构（根元素 `<dblp>`，记录为直接子节点）；评审期真实交叉验证
     （`GET dblp.org/db/conf/icml/icml2023.xml`）发现线上真实根元素为 `<bht>`，记录嵌套在
     `<dblpcites><r>` 下两层——若未捕获，`enumerate_issue`/`healthcheck` 会在生产环境**零解析**
     任何真实线上卷，且 `ee→DOI` 护栏的 `container_dois` 收集会静默恒空（"看似通过、实则
     失效"的隐蔽失败模式）。修复改 `root.findall()` 为 `root.iter()`（递归任意深度）+ 补
     1828 条真实 ICML2023 全量记录端到端 fixture 锁定回归。
  2. **合并引擎 review follow-ups F1-F3**（`57d97b7`，Approved 附带 3 项轻量修复）：F1 纠正
     docstring 对桥接 identifier 顺序敏感性的"等价数据态"误导性措辞；F2 修复 schema v2 迁移
     "归一化删除异形行时可能连带删除该 paper 唯一 `is_primary` 行"的真实正确性 bug（新增
     `_restore_primary_if_needed`）；F3 碰撞标签中性化（`doi-case-collision`→
     `doi-normalization-collision`，涵盖前缀异形）。
  3. **T6 命名对齐 follow-up**（`b882648`）：`EnrichmentSource` 命名对齐 plan §2-5 冻结件表述
     + 清理死常量。
- **在线合规**：AC-3.5 在线实跑 33 请求全程 UA 携真实 `mailto:` 联系邮箱（经隔离 scratchpad
  home 注入，见 §5/§6）；crossref 保守 5 req/s、dblp ≥4s/req（`Crawl-delay:4`）、unpaywall
  `?email=` 经 obslog 脱敏；仅访问各源官方文档化 API，无认证绕过、无凭证入库/入日志明文。
- **fixture 纪律延续**：dblp `<bht>` 真实 schema 发现后，同步新增"schema-correct successor"
  fixture（真实 1828 条记录逐字节复制，DBLP 数据 CC0 公共领域）并保留 dump-schema 兼容
  fixture、显式改名去歧义（`04_volume_xml_normal.xml`→`04_volume_xml_dump_schema_normal.xml`）
  ——延续 Phase 2"合成假设是盲区源"教训的具体应用。

## 5. 已知限制（如实记录）

- **【新发现，本次文档复核，2026-07-23】main 存在 1 个失败单测**——
  `tests/unit/test_crossref_parse.py::test_parse_single_work_title`：断言
  `title == "Synthetic Canary Title for Works Healthcheck"`（旧合成占位串），但 `47bb72a`
  （T7 C2/C3 修复，healthcheck golden 转正）同步把共享 fixture
  `tests/fixtures/crossref/06_works_healthcheck.json` 的 `title` 字段改写为真实捕获值
  `"Deep learning"`——该 commit 正确同步更新了 `test_crossref_adapter.py` 中两个消费同一
  fixture 的 healthcheck 测试，但遗漏了 `test_crossref_parse.py` 中独立直接调用
  `parse.parse_single_work_title()` 的纯解析单测：**同一 fixture 被两个测试文件消费，只
  同步了其中一个**。`make check` 的 `test` 目标目前非全绿（lint/type 两项 PASS，仅此 1 测试
  FAIL，覆盖率门禁本身仍达标 99.18%）。**本次为纯文档任务，未修改测试/源代码**（任务边界），
  需 owner 在 `test_crossref_parse.py:226` 补一处断言更新。详见 §6 增补小节。
- **S2 API key 未到**：D-021 决策 2 记录"生产必须申请 key"；enrich（`crawler enrich --source
  s2`）与 canary 在线层均门控为 SKIP/CONFIG，不阻塞离线 DoD，但 D-019 s2 锚点、s2 在线冒烟均
  为 `[PENDING]`。
- **aaai_ojs 全库 OAI 补跑仍未做**：Phase 2 报告检查单 #3 残项（"aaai_ojs 需先补跑一次全库
  OAI 收割，当前全表计数为 null"），本 Phase 未排期，跨 2 个 Phase 未清零。
- **openalex 402 识别依赖文本嗅探，非稳定契约**：`HttpClient` 冻结错误映射未单列 402（归入
  "其余 4xx→CONFIG"），`openalex/adapter.py` 的 `_looks_like_status` 靠正则解析 `CrawlerError`
  消息里的 `"HTTP {status} for ..."` 固定前缀重分类为 `RATE_LIMITED`；模块 docstring 自陈
  "该嗅探依赖 `http.py` 当前的异常消息格式，非稳定契约（若该格式改变，本层退化为把 402
  误判成普通 CONFIG）"——已知取舍，非本次新发现。
- **OpenAlex 每日预算状态非跨进程原子**：`budget.py` 的 `add_spend`"读→加→写"三步不加跨进程
  锁；单次 `save_state` 用临时文件+`os.replace` 保证单次写入原子，但两个并发 `crawler enrich`
  进程各自读到同一旧值、后写者覆盖前写者增量（lost update）。模块 docstring 判定影响面
  "只是预算核销偏保守/偏宽松几美分，不影响正确性红线"；design 文档基线本就是"run-scoped
  累计"（aggregators.md §4 `[PENDING·T6 确认]` 已按此收口），跨进程强一致（如 `fcntl.flock`）
  留作后续加固项。
- **AC-3.1/3.2/3.3/3.4 尚无独立汇总验收记录文档**：现行判据分散在
  `test_merge_acceptance.py`/`test_merge_property.py`/`test_verify.py` 三个测试文件（均本次
  亲跑通过），未如 AC-3.5 那样收口成 `testing/records/` 下的 markdown 记录——T8 残项。
- **AC-3.4"顺序无关"结论有显式适用边界**：桥接 identifier 冲突输入类顺序敏感（模块 docstring
  自述），随机属性测试刻意排除该输入类，其确定性由 `test_merge.py` 定向用例单独锁定——正式
  AC-3.4 验收记录成文时应显式写出此边界。
- **AC-0 系统性扫描未执行**：phase3-implementation-plan T8 已列明，本次文档复核未代为执行，
  仍是 T8 待办。
- **`docs/plan/progress.md`"模块状态表"自 Phase 1 起未再更新**（本次复核发现，非本次任务
  范围）：现表仍停留在 Phase 1 的 T1-T9 命名，未含 Phase 2 的 7 个 adapter 模块、也未含本次
  Phase 3 新模块——如实标注供 controller 决定是否需专项补全；本次"进度刷新"任务范围限定在
  "当前快照"叙事段，未触碰该表。
- **`docs/plan/decision-log.md` 的 INDEX 摘要仍写"D-001…D-019"**（Phase 2 报告 §5 已首次
  记录此滞后，本次复核确认仍未更正，现应为 D-001…D-022）——跨 2 个 Phase 未清零的文档滞后，
  供 controller 决定是否一并处理。
- **本 Phase 无 `docs/logs/` session 日志**：AGENTS.md §4 义务"当日工作在
  `docs/logs/YYYY-MM-DD-session-NNN.md` 留痕"，现有日志止于 `2026-07-22-session-006.md`
  （Phase 2），Phase 3 全程（W0 至今）未见 `session-007` 或后续日志——本次任务范围为 4 份
  既定文档，未创建日志文件补记。

## 6. Phase 4 开工检查单（T8 收尾移交）

1. 【待用户】**S2 API key 申请到位后**：①`crawler enrich --source s2` 真实批查冒烟补跑；
   ②D-019 s2 锚点回填（aggregators.md §7）；③openalex 正锚点一并补齐（同批在线窗口，无需
   二次申请）。
2. **`oup_silverchair` adapter/stub 注册**——收敛 QJE `fulltext_source` 当前借用
   `elsevier_sd` 的占位状态（AC-3.5 记录 Concern C1；其余 4 刊 jfe/jet/jpubeco/jbf 的
   `elsevier_sd` 为真实平台，无此问题）。
3. **`crawler canary` 凭证注入架构缺口**（本次源码复核发现）：`cli.py::canary()` 直接
   `load_adapters()` 后即调用 `healthcheck()`，未像 `pull`/`enrich` 那样先经
   `_bind_openreview_token_client`/`_prepare_enrich_source` 注入 token/api_key——即便用户已
   在 config 配置 `openreview_token`/`s2_api_key`/`openalex_api_key`，`crawler canary` 仍会
   体现为匿名/未配置状态（含 **openreview_token 存量**：Phase 2 已配置生效于 `pull`，但
   canary 命令从未消费它）。需补一处装配步骤。
4. **`HttpClient` 结构化 status 暴露仲裁**（402 文本嗅探替代）：当前 openalex 的 402 识别
   （§5 已知限制）靠解析异常消息文本前缀，评估是否给 `CrawlerError`/`HttpClient` 补结构化
   `status_code` 字段作为更稳定的替代契约。
5. **`acm_dl` 依 D-020 到期重评**：Phase 2 报告已排期"Phase 4 重评"，本 Phase 未涉及，顺延。
6. 【待用户】**`config.toml [identity].email` 补配**：AC-3.5 记录 Concern C5 发现用户真实
   `~/.paper-crawler/config.toml` 无 `[identity].email`（仅 `[auth.openreview]`），默认 home
   直跑真实 CLI 会掉出 Crossref polite pool；本次经隔离 scratchpad home 规避，未触及用户
   真实 config。
7. AC-3.1~3.4 汇总验收记录成文（T8 残项，见 §5）；AC-0 红线系统性扫描执行（T8 残项，见
   §5）；`aggregators.md → implemented` 已于本次落地，`tag phase-3` 待前述项收口后打。
8. aaai_ojs 全库 OAI 补跑（Phase 2 检查单 #3 残项，跨 2 个 Phase 未清，见 §5）。
9. AC-3.5 记录 Concerns C1~C5 逐项裁决（C1 已并入本清单 #2；C2 冒烟断言脆弱性已随
   `47bb72a` 处理但见下方增补小节；C4 dblp 503 瞬时抖动，可选加固一次退避重试；C5 已并入
   本清单 #6）。
10. `budget.py` 跨进程原子性加固（`fcntl.flock` 或等价机制，§5 已知限制，非阻塞项）。
11. `docs/plan/progress.md`"模块状态表"与 `docs/plan/decision-log.md` INDEX 摘要
    （D-001…D-019→D-022）两处滞后（§5 已知限制新记录，跨 Phase 累计）——建议纳入下次全
    文档状态盘点一并处理。

### Phase 4 检查单增补（文档复核新发现，2026-07-23）

- **【置顶】main 单测回归**：`tests/unit/test_crossref_parse.py::test_parse_single_work_title`
  断言与 `47bb72a` 改写的共享 fixture 真值不同步（详见 §5 首条）——建议在打 `tag phase-3`
  前修复，否则 tag 对应的 commit 不是"全绿"状态。修复方式明确：把该测试第 226 行的期望字符串
  由 `"Synthetic Canary Title for Works Healthcheck"` 改为 `"Deep learning"`；是否需要为该
  fixture 拆出独立的合成版本、让 healthcheck 语义测试与纯解析测试解耦，留 owner 判断。
