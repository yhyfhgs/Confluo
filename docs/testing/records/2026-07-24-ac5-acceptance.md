---
title: AC-5 离线端到端汇总验收记录 — ssrn/nber/aea/econsoc 四 adapter（Phase 5 离线口径）
status: draft
owner: t7
updated: 2026-07-24
---

# AC-5 离线端到端汇总验收记录（ssrn/nber/aea/econsoc，Phase 5 离线口径收口）

> 判定依据：[acceptance-criteria.md AC-5.1a~5.4](../acceptance-criteria.md)（本次同批正式化，commit `847b90c`）、[design/adapters/ssrn.md §8](../../design/adapters/ssrn.md)、[nber.md §8](../../design/adapters/nber.md)、[aea.md §9](../../design/adapters/aea.md)、[econsoc.md §7](../../design/adapters/econsoc.md)、[plan/phase5-implementation-plan.md T7 节](../../plan/phase5-implementation-plan.md)。
> 记录范式：[AC-4 离线验收汇总记录](2026-07-23-ac4-acceptance.md) / [AC-3.1~3.4 独立汇总验收记录](2026-07-24-ac3-acceptance.md)（逐条判定表 / 证据链 / 亲跑台账 / 分层标注 / 签署）。
> 代码基线：`chore/ac5-acceptance` worktree @ `main` `5111fc0`（Phase 5 五张实现卡 T1 crossref 参数化扩展 + T3 nber + T4 ssrn + T5 aea + T6 econsoc+wiley 全部已合并）。**本记录零 `src/`/`tests/` 改动、零网络实跑**——全部计数为本 worktree 内 `uv run pytest` 实测（非转抄任何终报/设计文档草案数字）。
> **定位**：T7 任务三件之②③——逐条 AC-5.x 定位判据载体到"文件::用例名"颗粒度、实跑取证、成正式验收记录；①AC-5 正式化本身见同批 commit `847b90c`（`acceptance-criteria.md` diff）。

## 0. 分层与范围（D-018 先例，如实标注）

本记录判定**全部限于离线可判层**（mock/fixture/假时钟）。以下两类不在本记录判定范围内，如实分层标注、不静默纳入亦不阻塞离线 DoD：

1. **AC-5.1b（ssrn 全文层，模式 B）**：Phase 5 未声明 `FETCH` 能力（D-029 案 B，defer 至 Phase 6 横切件统一设计），ssrn 自身测试套件内无对应的挑战/取回判据可跑——非"离线失败"，而是"本 Phase 结构性不存在该实现"。§1 表内单独标注，不计入 PASS/FAIL 二值。
2. **在线依赖项**（M1 批 + 后续 UPDATE_GOLDEN 类，§2 详列）：SSRN OpenAlex 覆盖率 census（M1 游离任务）、aea 非 AER/JEP 6 刊 ISSN 在线核实、ssrn/nber healthcheck golden 值捕获（源码内均明确标注 `[PENDING golden]`/`[PENDING online-smoke UPDATE_GOLDEN]`）——均需真实网络，orchestrator 已另派在线批处理，不在本 T7 离线任务范围。**核实澄清**：econsoc healthcheck 为结构性 `repositoryName` 字符串匹配（无 pending golden，见源码 `test_healthcheck_ok_when_repository_name_matches`）、aea healthcheck 结构性 `NotImplementedError`（本 Phase 无 FETCH，canary SKIP，沿 auth_gated 先例）——二者均非"待在线捕获"性质，不属本类。

## 1. AC-5.x 逐条判定

| AC | 场景（acceptance-criteria.md 原文摘） | 判定 | 承载载体（离线） |
|---|---|---|---|
| AC-5.1a | ssrn 元数据层三判据：①7 收割日回放无重复无遗漏 ②econ/fin 确定性过滤单测 ③obslog 证零 SSRN 站点接触 | **PASS（离线）** | `test_ssrn_adapter.py` + `test_ssrn_parse.py` 具名判据 3 例 + 全套件 47 例 |
| AC-5.1b | ssrn 全文层（模式 B，opt-in） | **N/A — defer Phase 6**（D-029 案 B；本 Phase 未声明 `FETCH`，非离线 DoD 阻塞项） | — |
| AC-5.2 | nber >18 月开放：`pull nber --year <当前-2>` 无凭证成功 + <18 月软门零网络诚实 + 双域限速 | **PASS（离线）** | `test_nber_adapter.py` 具名判据 11 例 + 全套件（含 parse/fixtures）71 例 |
| AC-5.3 | econsoc TE/QE 开放刊：OJS-OAI 枚举 + galley 全文抓取无需认证 + D-019 锚点 | **PASS（离线）** | `test_econsoc_*.py` 具名判据 11 例 + 全套件（adapter/parse/canary/integration）79 例 |
| AC-5.4 | 平台归属正确性：POM/SODA（原判据）+ aea 8 刊路由 + ECMA 三段路由 + wiley 10.3982 移除不误路由（Phase 5 新增） | **PASS（离线，凭 Phase 5 新增维度独立支撑）**；POM/SODA 正向路由部分核实后发现**目标 adapter（sage/siam）status: planned、未实现**，非"Phase 4 已验证"，如实标注为既有缺口、不计入本条 PASS 依据 | `test_aea_parse.py` + `test_econsoc_*.py` + `test_wiley_parse.py` 具名判据 26 例（+ aea/wiley 全套件 84 例） |

---

### AC-5.1a · ssrn 元数据层三判据 — **PASS（离线）**

**场景原文**（acceptance-criteria.md）：①7 收割日回放（含重叠 created 窗 + ~1 日延迟注入）→ abstract_id 清单无重复无遗漏；②econ/fin 主题过滤＝确定性过滤逻辑单测；③全程零 SSRN 站点接触。

**具名判据载体**（源码内以 `AC-5.1a①/②/③` 注释直接标定，非本记录事后归因）：
- ① `tests/unit/test_ssrn_adapter.py::test_seven_harvest_day_replay_dedup_no_dup_no_omission`：7 日 created 窗序列（含相邻日重叠窗 + 延迟注入 id `1004`）→ 跨日累计去重集合 `==` 期望完整集合；`len(all_ids) > len(deduped)` 证重叠窗确有重复被折叠（非"从未重复过"的空判）；延迟注入 id 断言在集合内（无遗漏）。
- ② `tests/unit/test_ssrn_parse.py::test_filter_stubs_by_topic_deterministic`：固定输入集（econ/biz/med 三 stub）→ 期望过滤输出精确断言，保序。支持簇：`test_topic_field_matches_{in_allowed,not_in_allowed,none_excluded,custom_allowed_set}`、`test_stub_topic_field_present_and_absent`（`topic_field_matches(None)==False`——诚实排除未 enrich 者，opt-in 收窄语义）。
- ③ `tests/unit/test_ssrn_adapter.py::test_zero_ssrn_contact_across_full_lifecycle`：discover+enumerate+resolve 全生命周期 MockTransport 记录请求域，`handler` 内联断言 `not host.endswith("ssrn.com")`（红线级——命中即测试失败，非事后过滤）；断言唯一接触域 `==api.crossref.org`。

**亲跑（本记录，2026-07-24，`uv run pytest`，零真实网络）**：
```
tests/unit/test_ssrn_adapter.py::test_seven_harvest_day_replay_dedup_no_dup_no_omission PASSED
tests/unit/test_ssrn_parse.py::test_filter_stubs_by_topic_deterministic PASSED
tests/unit/test_ssrn_adapter.py::test_zero_ssrn_contact_across_full_lifecycle PASSED
=== 3 passed in 0.66s ===
```
全套件补证：`test_ssrn_adapter.py`(25) + `test_ssrn_parse.py`(17) + `test_ssrn_buckets.py`(5) = **47 passed**（discover 纯生成年桶边界、DOI→abstract_id 正则矩阵、`skipped_non_ssrn` 护栏、cursor 续拉、resolve landing-only 零网络、healthcheck golden/drift、unpaywall SSRN landing-only 净效果等，构成 ssrn adapter 通用 DoD）。

**口径注记**：限速审计条款（"经 obslog jsonl，聚合 API 请求不入 FetchLog"）为架构性事实（元数据层无 fetch 阶段，design/05 §7 口径），非独立可失败判据，本记录不单列亲跑；`healthcheck` 的 golden 真值仍 `[PENDING]`（真实 crossref title 捕获），列入 §2 在线批。

---

### AC-5.1b · ssrn 全文层（模式 B） — **N/A，defer Phase 6**

**场景原文**：遇 Cloudflare 挑战正确 BLOCKED(challenge)+冷却 24h；真实取回=用户参与 runbook；限速 ≤1 req/5s。

Phase 5 `ssrn.capabilities()` 未含 `FETCH`（controller 采纳 D-029 案 B，ssrn.md §11.4）；ssrn 自身测试套件中无 Cloudflare 挑战 fixture / `Delivery.cfm` 取回判据（已核实：`test_ssrn_adapter.py`/`test_ssrn_parse.py`/`test_ssrn_buckets.py` 全 47 例内无一涉及 challenge/浏览器 seam）。Cloudflare 挑战判定的**通用机制**（`ChallengeDetector` 四态分类）已由 Phase 4 `test_auth_challenge.py`（23 passed，见 [2026-07-23-ac4-acceptance.md](2026-07-23-ac4-acceptance.md) §1 AC-4.6 节）离线验证，ssrn 侧复用该机制的具体接线待 Phase 6 横切件落地时才产生可判对象。**本条不计入本记录 PASS/FAIL 二值统计**，如实标注为"defer"而非"FAIL"或静默略过。

---

### AC-5.2 · NBER >18 月开放 — **PASS（离线）**

**场景原文**：`pull nber --year <当前-2>` 无凭证成功；<18 月按策略提示配额/订阅（不利用软门绕过）。

**具名判据载体**：
- `>18 月成功路径`：`test_resolve_open_yields_direct_pdf_plan`（>18 月 DOI → 产 `AssetPlan(kind=PDF, auth_needed=NONE)`，URL 确定性构造）、`test_resolve_boundary_exactly_open`（恰满 18 月边界→开放，非 gated——精确边界断言，非"大约"）、`test_fetch_streams_pdf`（流式 PDF 落盘）、`test_fetch_pdf_head_fixture_replays`（`[LIVE-shape]` w30000 PDF head fixture 回放，`%PDF-` 魔数）。
- `<18 月软门零网络诚实`：`test_resolve_recent_raises_no_entitlement`——**关键结构性证据**：该用例使用 `_adapter(_never)`，其中 `_never` handler 定义为「一旦被调用即 `raise AssertionError("no network expected for this path")`」。即"<18 月无软门请求发出"不是靠事后审计一条日志实现，而是**resolve 路径本身对 <18 月论文零网络**（`resolve_offline` 语义），handler 断言是该零网络契约的直接证明，比"审计请求日志"更强。`error_class is NO_ENTITLEMENT`（非 integrity）、`detail=="recent_gated"`。`test_fetch_soft_gate_html_maps_no_entitlement_not_integrity` + `test_fetch_soft_gate_synth_fixture_maps_no_entitlement`：fetch 阶段软门 HTML 挡板同样映射 no_entitlement（非 integrity），双守卫覆盖两阶段。
- `双域限速假时钟`：`test_www_bucket_is_1_req_per_5s`、`test_www2_aliases_share_www_bucket`（低号别名共享 www 桶）、`test_back_host_not_auto_registered_by_route_for`（`route_for` 陷阱规避——back 域不被自动别名进宽松 www 桶）、`test_back_bucket_independent_1_req_per_10s`（back 独立 1req/10s，不受 www 欠账影响）。

**亲跑（本记录，2026-07-24）**：具名判据 11 例：
```
uv run pytest tests/unit/test_nber_adapter.py::test_resolve_open_yields_direct_pdf_plan \
  tests/unit/test_nber_adapter.py::test_resolve_boundary_exactly_open \
  tests/unit/test_nber_adapter.py::test_fetch_streams_pdf \
  tests/unit/test_nber_adapter.py::test_fetch_pdf_head_fixture_replays \
  tests/unit/test_nber_adapter.py::test_resolve_recent_raises_no_entitlement \
  tests/unit/test_nber_adapter.py::test_fetch_soft_gate_html_maps_no_entitlement_not_integrity \
  tests/unit/test_nber_adapter.py::test_fetch_soft_gate_synth_fixture_maps_no_entitlement \
  tests/unit/test_nber_adapter.py::test_www_bucket_is_1_req_per_5s \
  tests/unit/test_nber_adapter.py::test_www2_aliases_share_www_bucket \
  tests/unit/test_nber_adapter.py::test_back_host_not_auto_registered_by_route_for \
  tests/unit/test_nber_adapter.py::test_back_bucket_independent_1_req_per_10s -v
=== 11 passed in 0.08s ===
```
全套件补证：`test_nber_adapter.py`(33) + `test_nber_parse.py`(36) + `test_nber_fixtures.py`(2) = **71 passed**（series-id 正则矩阵、pub_date 解析边界、RSS item 解析、venue-YAML 驱动的 discover/enumerate 契约测试等，构成 nber adapter 通用 DoD）。

**口径注记**：`pull nber --year <当前-2>` 的在线冒烟 1 篇实证（`tests/online/test_nber_smoke.py`，`-m online`）不在本次离线任务范围，按 D-018 归 M1/后续在线批（§2）；本记录只判离线机制正确性，离线回放已 PASS。

---

### AC-5.3 · TE/QE 开放刊 — **PASS（离线）**

**场景原文**：OJS-OAI 枚举 + galley 全文成功抓取，无需认证；①`timeline {te,qe}` 覆盖 volume_map 全区间；②`pull {te,qe} --year <Y> --limit N` 落盘 N 个 `%PDF` 文件 >10KB、DB↔文件对账；D-019 锚点。

**具名判据载体**：
- ①`timeline` 覆盖：`test_discover_te_yields_per_year_issues`、`test_discover_since_narrows_start`（`since` 收窄下界 + 界外年拒绝）。
- ②`pull` 全链路：`tests/integration/test_econsoc_enumerate.py::test_full_chain_te_discover_enumerate_resolve_fetch`（discover→enumerate(OAI)→resolve(landing→galley)→fetch 全链，DOI 后缀过滤计数断言）；`test_overlapping_reharvest_does_not_duplicate`（重叠窗口重复收割无重复无遗漏，`identifier('doi')` 主键去重天然保证）。
- D-019 锚点：`test_econsoc_canary.py` 7 例——`test_canary_get_record_matches_known_title_and_journal`（TE/QE/ECMA 当前段三样本，规整化 `dc:title` + journal 比对，参数化 `[ecma-current-synthetic, te-synthetic, qe-synthetic]`）、`test_canary_end_to_end_to_paper_stub_produces_doi_identifier`（同三样本端到端至 PaperStub）、`test_canary_set_covers_three_distinct_journals`（防跨刊漏覆盖）。**数据来源诚实声明**（源码内注记）：三样本 DOI 后缀/前缀为实测形态、非完全捏造。

**亲跑（本记录，2026-07-24）**：具名判据 11 例：
```
uv run pytest tests/unit/test_econsoc_adapter.py::test_discover_te_yields_per_year_issues \
  tests/unit/test_econsoc_adapter.py::test_discover_since_narrows_start \
  tests/integration/test_econsoc_enumerate.py::test_full_chain_te_discover_enumerate_resolve_fetch \
  tests/integration/test_econsoc_enumerate.py::test_overlapping_reharvest_does_not_duplicate \
  tests/unit/test_econsoc_canary.py -v
=== 11 passed in 0.09s ===
```
全套件补证：`test_econsoc_adapter.py`(26) + `test_econsoc_parse.py`(36) + `test_econsoc_canary.py`(7) + `test_econsoc_enumerate.py`(integration, 10) = **79 passed**（oai_dc 薄解析器字段抽取、`noRecordsMatch`/`badResumptionToken`/`idDoesNotExist` 等 OAI 错误码路由、tombstone 跳过计数经 obslog 暴露、QE endpoint membership 过滤等，构成 econsoc adapter 通用 DoD；本套件同时承载 AC-5.4 的 ECMA 路由维度，详见下条，不重复计数）。

**口径注记**：D-019 锚点表 TE completeListSize 656 vs crossref 735 的差额（`[UNRESOLVED③]`，econsoc.md §8）为已知开放问题，DOI 后缀过滤 + `identifier('doi')` 去重使两源差额自然收敛，不阻塞本条离线判定；在线冒烟（TE `Identify`/OAI 首页/galley fetch 等）归 M1/后续在线批。

---

### AC-5.4 · 平台归属正确性 — **PASS（离线，凭 Phase 5 新增维度独立支撑）**

**场景原文**：POM 走 SAGE adapter（非 Wiley/INFORMS）；SODA 走 SIAM（非 ACM）——路由解析正确（Phase 4 既有）。Phase 5 新增：aea 8 刊路由 + ECMA 三段路由 + wiley 10.3982 移除不误路由。

**Phase 4 既有部分（POM/SODA）——核实后发现需更正的偏差**：`docs/design/adapters/acm-dl.md:56`（"AC-5.4（SODA 不在本 adapter）"）、`docs/design/adapters/informs.md:52`（"AC-5.4（POM 不路由到本 adapter）"）交叉引用了该判据，但**核实后确认二者只断言"负向排除"**（SODA/POM 不误落入 acm_dl/informs 自身范围），**均未断言"正向路由到正确 adapter"**。实地核查 `src/paper_crawler/adapters/` 目录与全仓 `venues/**.yaml`：**不存在 `sage`/`siam` 实现**（无对应源码目录、无任何 venue YAML 引用 `sage`/`siam`）；`docs/design/adapters/README.md:91,95` 明确登记两者状态为 `planned`（"待建"），非 implemented。**故 AC-5.4 原判据（POM 走 SAGE / SODA 走 SIAM）的正向路由部分当前在代码库中结构性不可测——无路由目标可验，非"Phase 4 已验证、未变更"，而是"目标 adapter 尚未实现，验证对象本身不存在"**。此为既有已知缺口（早于 Phase 5、非 Phase 5 五张实现卡范围），本记录如实标注、不代为下判定，亦不计入本条 PASS 依据（本条 PASS 完全由下述 Phase 5 新增维度独立支撑）。`test_venue_yaml_lint.py`（66 passed）未见回归，但该套件校验的是**现存** venue YAML 的结构合法性，不能证明 sage/siam 缺失本身是否符合预期——仅确认本次未引入新的 lint 失败。

**Phase 5 新增部分具名判据载体**：
- **aea 8 刊路由**：`test_all_8_venues_route_correctly_from_submission_form_doi`（参数化 8 例：aer/aeri/aej_macro/aej_micro/aej_applied/aej_policy/jel/jep，均正确路由）、`test_code_to_venue_table_has_exactly_8_entries`（路由表恰 8 条，`"pandp" not in CODE_TO_VENUE`——P&P 归位暂缓不入 8 刊清单，防静默漏收/多收）。
- **ECMA 域名三段路由**（parse 纯函数层）：`test_ecma_segment_current_on_self_hosted_domain`（econometricsociety.org→CURRENT）、`test_ecma_segment_backfile_on_wiley_domain`（doi.wiley.com→BACKFILE）、`test_ecma_segment_pre_doi_on_jstor_domain`（jstor.org→PRE_DOI）、`test_ecma_segment_optimistic_current_when_domain_unknown`（无域名信号→乐观归 CURRENT，主路径容错）。
- **ECMA 三段路由**（adapter/resolve 层，含零网络断言）：`test_resolve_ecma_current_domain_fetches_galley`、`test_resolve_ecma_backfile_wiley_domain_is_no_entitlement`（`calls==[]`——分段前置判定未触网）、`test_resolve_ecma_pre_doi_jstor_is_zero_assets`（同样零网络）。
- **F1 终态诚实化**（审查修复闭合，routing 的关键正确性延伸）：`test_resolve_ecma_current_404_remapped_to_no_entitlement`（crossref 无落地域信号→乐观归 CURRENT→自营域 404→**改判** no_entitlement 而非 GONE，因过刊实际由 Wiley 托管、econsoc 不托管，GONE 会是误终态；obslog 计数 `ecma_current_404_as_ne` 可观测）对照 `test_resolve_te_landing_404_stays_gone`（TE/QE 的 404 仍判 GONE——F1 修复**仅**作用于 ECMA，不误伤 TE/QE 自持记录的权威性）。
- **integration 三分流**：`tests/integration/test_econsoc_enumerate.py::test_ecma_segment_three_way_split`。
- **wiley 10.3982 移除不误路由**：`test_wiley_parse.py::test_is_wiley_doi_false_for_non_wiley`（参数化含 `10.3982/ECTA12345`、`10.3982/TE6021` 两例，均正确判 `False`——即 wiley adapter 不再认领该前缀，D-028）。

**亲跑（本记录，2026-07-24）**：具名判据 26 例：
```
uv run pytest tests/unit/test_aea_parse.py::test_all_8_venues_route_correctly_from_submission_form_doi \
  tests/unit/test_aea_parse.py::test_code_to_venue_table_has_exactly_8_entries \
  tests/unit/test_econsoc_parse.py::test_ecma_segment_current_on_self_hosted_domain \
  tests/unit/test_econsoc_parse.py::test_ecma_segment_backfile_on_wiley_domain \
  tests/unit/test_econsoc_parse.py::test_ecma_segment_pre_doi_on_jstor_domain \
  tests/unit/test_econsoc_parse.py::test_ecma_segment_optimistic_current_when_domain_unknown \
  tests/unit/test_econsoc_adapter.py::test_resolve_ecma_current_domain_fetches_galley \
  tests/unit/test_econsoc_adapter.py::test_resolve_ecma_backfile_wiley_domain_is_no_entitlement \
  tests/unit/test_econsoc_adapter.py::test_resolve_ecma_pre_doi_jstor_is_zero_assets \
  tests/unit/test_econsoc_adapter.py::test_resolve_ecma_current_404_remapped_to_no_entitlement \
  tests/unit/test_econsoc_adapter.py::test_resolve_te_landing_404_stays_gone \
  tests/integration/test_econsoc_enumerate.py::test_ecma_segment_three_way_split \
  tests/unit/test_wiley_parse.py::test_is_wiley_doi_false_for_non_wiley -v
=== 26 passed in 0.08s ===
```
全套件补证：`test_aea_adapter.py`(24) + `test_aea_parse.py`(30) + `test_aea_fixtures.py`(11) = aea **65 passed**；`test_wiley_parse.py` **19 passed**（econsoc 全套件 79 passed 已计入 AC-5.3，不重复计数）。

**口径注记**：aea 8 刊中仅 AER/JEP 的 ISSN 经 [LIVE 2026-07-24] 实证，余 6 刊（aeri/aej_macro/aej_micro/aej_applied/aej_policy/jel）ISSN 取自 catalog `[DOC]` 标注、待在线核实（UPDATE_GOLDEN，D-019）——**不影响本条路由正确性判据**（路由逻辑测的是 code→venue_id 映射本身，与 ISSN 真实性正交，ISSN 核实见 §2）。

## 2. [在线批 M1/后续] 分层清单（不在本记录判定范围，如实标注、不阻塞离线 DoD）

沿 D-018 分层先例（AC-4.1 真实凭证归 T7b 之例），以下项均需真实网络，orchestrator 已另派在线批处理（M1 及后续），本记录不判、不预支结论：

| 项 | 归属 | 说明 |
|---|---|---|
| SSRN OpenAlex 覆盖率 census | M1（游离任务，依 T4） | ssrn.md §9.1：openalex `source.id:S4210172589` 分页随机偏移 N≈1000 采样，判"crossref 相对 openalex"覆盖率（≥90% 阈值判定，credit 预算内） |
| aea 非 AER/JEP 6 刊 ISSN 在线核实 | 后续（T5 冒烟延伸） | aeri/aej_macro/aej_micro/aej_applied/aej_policy/jel 六刊 ISSN 现仅 catalog `[DOC]` 标注，需 crossref 在线核对 + UPDATE_GOLDEN（D-019） |
| ssrn healthcheck golden 转正 | 后续 | `api.crossref.org/works/10.2139/ssrn.4056799` 规整化 `title[0]` 真值现 `[PENDING]`，需一次在线捕获后 `UPDATE_GOLDEN=1` 固化 |
| nber healthcheck golden 转正 + 在线冒烟 1 篇实证 | 后续（T7b 类比） | 源码 `[PENDING online-smoke UPDATE_GOLDEN]`（`src/paper_crawler/adapters/nber/adapter.py:23,230`）；`pull nber --year <当前-2>` 的真实 PDF HEAD 200 + w30000 title 核对（`tests/online/test_nber_smoke.py`） |
| econsoc 在线冒烟 | 后续 | TE `Identify` + OAI 首页/续页 + galley fetch + ECMA 当前段 OA HEAD 判定（`[UNRESOLVED①]` 闭合）+ 过刊段 doi.org HEAD 域名核对（`[UNRESOLVED②]`） |
| AC-5.1b ssrn 全文层真实取回 | Phase 6（非 M1，架构性 defer） | 见 §1 AC-5.1b 节；D-029 案 B，本 Phase 结构性不存在，非"待核实"而是"待实现" |

## 3. 亲跑台账（本 worktree `chore/ac5-acceptance` @ `main` `5111fc0`，`uv sync --extra auth` 后 `uv run pytest`，零真实网络）

| 载体 | 计数 | 承载 AC | 角色 |
|---|---|---|---|
| AC-5.1a 具名判据（3 例） | **3 passed** | AC-5.1a | 正式判据（源码内 `AC-5.1a①②③` 注释直接标定） |
| `test_ssrn_adapter.py` + `test_ssrn_parse.py` + `test_ssrn_buckets.py`（全套件） | **47 passed** | AC-5.1a | 通用 adapter DoD 补证 |
| AC-5.2 具名判据（11 例） | **11 passed** | AC-5.2 | 正式判据 |
| `test_nber_adapter.py` + `test_nber_parse.py` + `test_nber_fixtures.py`（全套件） | **71 passed** | AC-5.2 | 通用 adapter DoD 补证 |
| AC-5.3 具名判据（11 例） | **11 passed** | AC-5.3 | 正式判据 |
| `test_econsoc_adapter.py` + `test_econsoc_parse.py` + `test_econsoc_canary.py` + `test_econsoc_enumerate.py`（全套件） | **79 passed** | AC-5.3 + AC-5.4（ECMA 路由子集） | 通用 adapter DoD 补证（含 AC-5.4 ECMA 路由用例，§1 已注明不重复计数） |
| AC-5.4 具名判据（26 例，跨 aea/econsoc/wiley 三文件） | **26 passed** | AC-5.4 | 正式判据 |
| `test_aea_adapter.py` + `test_aea_parse.py` + `test_aea_fixtures.py`（全套件） | **65 passed** | AC-5.4（+ 通用 DoD，aea 无专属 AC-5.x） | 通用 adapter DoD 补证 |
| `test_wiley_parse.py`（全套件） | **19 passed** | AC-5.4 | 补证（10.3982 移除回归防护） |
| `test_crossref_adapter.py` + `test_crossref_parse.py`（T1 共用枚举源，nber/ssrn/aea/econsoc 均消费） | **87 passed** | 跨 AC-5.1a/5.2/5.3/5.4 基础层 | 上游共用契约补证（enum-key/date-field 两轴参数化扩展） |
| `test_venue_yaml_lint.py`（全部 venue YAML，含新增 8+3+1+1=13 个 Phase 5 venue） | **66 passed** | 跨 AC-5.x（lint 维度） | venue 声明结构校验 |
| **17 文件单次会话合并跑**（显式列出全部文件路径为 pytest 参数，验证互不干扰） | **434 passed / 0 failed**（2.37s） | AC-5.1a/5.2/5.3/5.4 全条 | — |
| **全量门禁 `make check`**（`sync-dev` + `ruff check` + `ruff format --check` + `mypy src` + `pytest tests/unit tests/contract tests/integration --cov=paper_crawler --cov-fail-under=80`） | **3056 passed, 28 skipped**（44.07s）；ruff 全绿；mypy "no issues found in 107 source files"；coverage **98.80%**（门槛 80%）；**EXIT=0** | 全局回归 | 与 Phase 5 五卡合并后基线（parent 报告数字）一致，本次为独立实跑复现，非转抄 |

## 4. 结论

AC-5.1a（ssrn 元数据层三判据）、AC-5.2（nber >18 月）、AC-5.3（econsoc TE/QE）、AC-5.4（平台归属正确性，含 Phase 5 新增的 aea/ECMA/wiley 路由维度）**离线判据本次在隔离 worktree 内实跑全部 PASS**（具名判据 51 例 + 全套件补证 434 例，零 failed、零 skipped、零真实网络）；AC-5.1b（ssrn 全文层）**结构性 defer 至 Phase 6**（D-029 案 B，非本 Phase DoD 范围，不计入 PASS/FAIL）；全量门禁 `make check` 独立复现 **3056 passed / 28 skipped / EXIT=0**，lint/type/coverage 三项均绿。§2 所列在线依赖项（M1 census、aea 6 刊 ISSN、healthcheck golden 等）均未预支结论，如实分层留待在线批处理。**核查中意外发现并如实上报**：AC-5.4 原判据的 POM/SODA 正向路由半部（走 SAGE/SIAM）目标 adapter 尚未实现（`sage`/`siam` status: planned，§1 AC-5.4 节详述）——早于 Phase 5 的既有缺口，不影响本记录 AC-5.4 PASS 判定（完全由 Phase 5 新增维度支撑），但如实登记供 controller 决定后续处置。

**判定：待 controller 终验。**

## 5. 移交

- controller 亲验：复跑本记录 §3 亲跑台账（尤其 17 文件合并会话 434 passed + `make check` 3056/28/EXIT=0）核对吻合；确认 AC-5 正式化 commit（`847b90c`）与本记录 commit 均未触碰 `src/**`/`tests/**`（`git diff --stat` 核对）。
- §2 在线批清单转交 M1（已游离派发）及后续 T7b 类比在线批次，本记录不预判其结论；T8 收尾时按"阈值达→无候补 / 不达→候补改期"口径（phase5-implementation-plan.md）如实登记，不阻塞 tag。
- **发现（非 Phase 5 范围，如实上报）**：AC-5.4 原判据"POM 走 SAGE / SODA 走 SIAM"的正向路由部分，核实后确认 `sage`/`siam` adapter 均为 `docs/design/adapters/README.md` 登记的 `planned`（待建）状态，代码库中无对应实现、无 venue YAML 引用——该判据当前结构性不可测（并非"验证通过后未变更"，而是"验证对象不存在"）。此缺口早于 Phase 5、非本次五张实现卡范围，本记录不代为下判定；建议 controller 登记为独立 backlog（sage/siam adapter 实现，Phase 4 遗留范围）或在下次涉及 POM/SODA 的验收批次中一并核实，非本记录 AC-5.4 PASS 判定的阻塞项（该判定完全由 Phase 5 新增的 aea/ECMA/wiley 路由维度独立支撑，§1 已注明）。

## 6. 签署

- **T7 初判（2026-07-24）**：AC-5.1a/5.2/5.3/5.4 离线判据在 `chore/ac5-acceptance` 隔离 worktree 内实跑全部 PASS（§1 逐条 + §3 台账）；AC-5.1b 如实标注 defer Phase 6、不计入 PASS/FAIL；全量门禁独立复现 3056 passed/28 skipped/EXIT=0；§2 在线依赖项分层不预支结论。**判定：待 controller 终验**（不自置 approved）。
- **待办**：controller 亲验载体计数复现 + `acceptance-criteria.md` AC-5 节 diff 复核 + §2 清单确认无遗漏后，方可转 `status: approved`。
