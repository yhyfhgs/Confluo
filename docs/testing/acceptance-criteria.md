---
title: 验收标准总表
status: approved
owner: fable5
updated: 2026-07-27
---

# 验收标准（Acceptance Criteria）

> 编号 `AC-<phase>.<n>`。每条含：前置、步骤、可观测的通过判据。判据必须客观可验（文件存在/计数相等/日志含特定记录），不用主观措辞。
> 与 FR/NFR 的映射见各设计文档 §测试与验收。执行留痕入 `docs/testing/records/`。

## AC-1 · 核心框架（Phase 1，mock adapter）

| ID | 场景 | 通过判据 |
|---|---|---|
| AC-1.1 | mock venue 端到端 `pull` | DB 中 Issue/Paper/Asset 计数符合 mock 数据；`data/` 下文件数=Asset(fetched) 数；报告"成功=N，失败=0" |
| AC-1.2 | dry-run 不落盘 | `pull --dry-run` 后 `data/` 无新增文件、DB 无 Asset(fetched)；输出的"将下载 N 篇"与随后实跑的实际下载数相等 |
| AC-1.3 | 断点续爬幂等 | 在 fetch 阶段随机 kill 进程后重跑 `pull`；最终 DB dump 与"不中断一次跑完"逐行一致；日志含 skipped 记录且无重复 FetchLog |
| AC-1.4 | 限速合规 | 压力场景下某 domain 的 FetchLog 时间戳间隔统计：实际速率 ≤ 配置值×1.05 |
| AC-1.5 | 状态机与 BLOCKED | 注入 auth_expired → 任务转 BLOCKED 不占重试；`resume` 后回 PENDING 并完成 |
| AC-1.6 | VenueSpec 校验 | 非法 spec（未知 adapter/auth 不兼容/id 冲突）被 `venues lint` 拒绝并给出定位信息 |

## AC-2 · Open-Access MVP（Phase 2）

| ID | 场景 | 通过判据 |
|---|---|---|
| AC-2.1 | `timeline iclr` | 列出 2013→当前年每一届；与 DBLP `conf/iclr` 卷数一致（±0） |
| AC-2.2 | `pull iclr --year 2024 --limit 10` | 落盘 10 个文件，每个魔数=`%PDF` 且 >10KB；DB↔文件对账一致 |
| AC-2.3 | arXiv 订阅 7 天增量 | 连续 7 日 watch：抽样 20 篇与 arXiv 官方 listing 比对，命中且无重复、无遗漏 |
| AC-2.4 | `pull cvpr --year 2023 --filter "diffusion"` | 过滤命中数=对 enumerate 全集本地过滤数；下载子集正确 |
| AC-2.5 | ACL Anthology bulk 优先 | 回填某年 EMNLP 全量走 github 数据仓库路径（日志证据），无逐页在线爬取 |
| AC-2.6 | ACM OA 会议（D-013）——**deferred(D-020)，Phase 4 重评** | 原判据：`pull kdd --year 2026` 无认证下载全文。修订 2026-07-22：LIVE 勘察证实 OA 后仍有 Cloudflare 挑战门 + ToS 禁自动下载条款（红线 AC-0.2/0.5 优先）→ 本条**不计入 Phase 2 判定**；Phase 4 依 D-020 重评（核 ToS 原文/官方通道，或降级为 Crossref 元数据+人工取回口径） |

## AC-3 · 数据模型与合并（Phase 3）

| ID | 场景 | 通过判据 |
|---|---|---|
| AC-3.1 | 强合并 | 同一 DOI 经 arXiv 与 Crossref 两路注入 → 1 条 paper、≥2 个 identifier |
| AC-3.2 | 弱信号不自动合并 | 标题改名的 WP↔刊发版注入 → 2 条 paper + 1 条 candidate_duplicate(decided=null) |
| AC-3.3 | verify 对账 | 人为制造丢文件/孤儿文件/哈希不符三类 → `verify` 全部检出并给正确修复建议 |
| AC-3.4 | 顺序无关 | 多源记录随机顺序注入，最终库状态逐行一致（属性测试通过） |
| AC-3.5 | 期刊 5 本零爬取枚举 | 含 QJE、JFE 在内 5 刊仅用 Crossref 即产出完整卷期+论文清单；篇数与 paper_count_claimed 差异有解释 |

## AC-4 · 认证与出版社（Phase 4，真实凭证 runbook）

| ID | 场景 | 通过判据 |
|---|---|---|
| AC-4.1 | 首登+取一篇 | `auth login <provider>` 人工登录后 `grab --doi <闭源DOI>` 得合法 PDF（魔数校验过） |
| AC-4.2 | 过期检测不轰炸 | 人为清 cookie 使 session 失效 → 批任务在 ≤20 篇内检出并 BLOCKED；日志无连续 401/403 轰炸（≤2 次即停） |
| AC-4.3 | 无权限降级 | 对无订阅 DOI → 标 no_entitlement、不重试、给出 Unpaywall 副本（若存在） |
| AC-4.4 | 日配额 | 单平台单日下载数 ≤ 配置上限（FetchLog 对账） |
| AC-4.5 | 登出无残留 | `auth logout <provider>` 后磁盘无可恢复 session（取证清单逐项过） |
| AC-4.6 | 风控即停 | 注入风控页特征 → BLOCKED(challenge) + 平台冷却生效 + 报告显著提示；无自动破解尝试 |

## AC-5 · SSRN 与特殊源（Phase 5）

| ID | 场景 | 通过判据 |
|---|---|---|
| AC-5.1a | SSRN 元数据层增量（聚合 API 主路径，CI 可判） | ①7 收割日回放（含重叠 created 窗 + ~1 日延迟注入）→ abstract_id 清单无重复无遗漏；②econ/fin 主题过滤＝确定性过滤逻辑单测（固定 fixture 输入→期望输出精确断言；原「一致率≥95% vs OpenAlex field 基准」废止——过滤信号本取自 OpenAlex field，自比恒 100% 为空判）；③全程零 SSRN 站点接触（obslog 断言无 `*.ssrn.com` 请求）；限速审计经 obslog jsonl（聚合 API 请求不入 FetchLog） |
| AC-5.1b | SSRN 全文层（模式 B 浏览器取回，opt-in，非 CI） | 遇 Cloudflare 挑战正确 BLOCKED(challenge)+平台冷却 24h（离线 challenge fixture 可判）；真实取回落盘＝用户参与 runbook（须换非阻断网络）；限速 ≤1 req/5s（仅模式 B 触 `*.ssrn.com` 时，FetchLog 审计）。**Phase 5 defer 至 Phase 6 横切件统一设计**（D-029 案 B；本 Phase 不声明 FETCH 能力，不阻塞离线 DoD）。**承接指针（Phase 7 T18，2026-07-27）**：三判据现分别由 AC-BF.1（挑战 BLOCKED+冷却）／AC-BF.3（真实取回 runbook）／AC-BF.4（限速 FetchLog 审计）承接兑现（见下方 AC-BF 区；design/11 §10）——T11 已将 ssrn 模式 B 接入 browser-fetch 通道并产 `RENDER_PAGE` 计划，本行判据语义不变、不重复立条 |
| AC-5.2 | NBER >18 月开放 | `pull nber --year <当前-2>`（>18 月区）无凭证成功：prefix enumerate 该年 + resolve 直链 + fetch PDF 魔数合格（离线 fixture 回放 PASS + 在线冒烟 1 篇实证，D-018 分层）；<18 月抽样 → resolve 判 no_entitlement（非 integrity）、报告提示订阅、且 resolve 本身零网络（无软门请求发出，不利用软门绕过——见调研伦理批注）；通用 adapter DoD：resolve/fetch/enumerate 逻辑单测 + fixture 回放 + www/back 双域限速假时钟断言全 PASS |
| AC-5.3 | TE/QE 开放刊 | OJS-OAI 枚举 + galley 全文成功抓取，无需认证：①`timeline {te,qe}` 覆盖 volume_map 全区间；②`pull {te,qe} --year <Y> --limit N` 落盘 N 个 `%PDF` 文件 >10KB、DB↔文件对账一致；D-019 锚点：TE/QE crossref-by-ISSN 计数各 ≥1 行（对账编辑部记录差额，如实注明差额成因，不阻塞） |
| AC-5.4 | 平台归属正确性 | POM 走 SAGE adapter（非 Wiley/INFORMS）；SODA 走 SIAM（非 ACM）——路由解析正确（Phase 4 既有判据，未变更）。**Phase 5 新增**：aea 8 刊 DOI code→venue 路由正确（P&P 归位暂缓、不入 8 刊清单）；ECMA 域名三段路由正确（当前段自营域→galley 取回 / 过刊段 Wiley 域→no_entitlement 零网络 / pre-DOI 段 JSTOR 域→零 asset 零网络，且当前段 404 终态诚实改判 no_entitlement 而非 GONE、TE/QE 404 仍判 GONE 不误判）；wiley 10.3982 前缀移除后不再误路由 ECMA/TE/QE 至 wiley（D-028）。aea 元数据/enumerate/DOI 解析无专属 AC-5.x，按通用 adapter DoD（fixture 回放 + 单测全 PASS）+ 本条路由类比收口 |

## AC-6 · 订阅与搜索（Phase 6）

| ID | 场景 | 通过判据 |
|---|---|---|
| AC-6.1 | 多 topic 7 天 | 3 个预置 topic 连续 7 天：无重复、无遗漏（抽样对照）、日报生成 |
| AC-6.2 | 护栏熔断 | 构造超 `max_new_per_run` 场景 → 零入库、产出含分布与收窄建议的过载报告 |
| AC-6.3 | SSRN 无下推补偿 | SSRN 订阅本地过滤后清单与人工浏览基准一致率 ≥95% |
| AC-6.4 | 下推/本地一致 | 同一 DSL 的"全本地过滤"与"下推+补偿"结果集相等 |

## AC-7 · 全文抽取与库增强（Phase 7）

| ID | 场景 | 通过判据 |
|---|---|---|
| AC-7.1 | 全文抽取 | 抽样 PDF 经 extract 得非空文本，标题与 DB 记录匹配（编辑距离阈值内） |
| AC-7.2 | GROBID 可选 | GROBID 开/关两模式均产出，关闭时降级为纯文本抽取不报错 |
| AC-7.3 | 去重审核工具 | `dedupe review` 逐条展示证据，merge/reject 后 same_as/rejected 正确落库且可回滚（物理不删行） |
| AC-7.4 | 全库对账 | 全库 `verify` 通过；preprint↔published 关联报告生成 |

## AC-BF · Browser-Fetch 横切件（design/11 转正，Phase 7 T6/T11 落地）

> **转正说明**（Phase 7 T18，2026-07-27）：编号继承 [design/11 §10](../design/11-browser-fetch.md) 草案原文（`AC-BF.1`~`AC-BF.6`），**判据语义不变**——转正只做两件事：①编号由"临时"转"正式"（本区即正式落点，design/11 §10 转为草案溯源）；②逐条补测试载体出处（grep 实况，2026-07-27，代码基线 `b3b8502`）。**未按 D-030 §12 裁决点⑦原议"转正为 `AC-<phase>.x`"重编号**——`AC-7.x` 已被本 Phase 自身的全文抽取/去重/对账四条占用（见上 AC-7），沿用 `AC-BF` 前缀可避免编号碰撞，且与本文件 `AC-0`/`AC-8` 两个既有"主题式而非阶段式"编号先例同构。
>
> **与既有 AC 的关系**：**AC-5.1b**（SSRN 全文层，见上 AC-5 区）由 AC-BF.1+AC-BF.3+AC-BF.4 承接兑现，AC-5.1b 行已加承接指针（不重复立条）；**aea 全文 AC**（[phase5-report 检查单 #9](../reports/2026-07-24-phase5-report.md)"待 browser-fetch 通道+auth 落地时立专属 AC"）同样由本区承接，aea 机构认证面另属 auth 域不在此列；**AC-4.6**（风控即停）是 AC-BF.1 的父条——AC-BF.1 是其在浏览器传输层的具化，不替代原条（原条覆盖 httpx 路径）。

| ID | 场景 | 通过判据 | 已落测试载体（grep 实况，2026-07-27） |
|---|---|---|---|
| AC-BF.1 | 风控即停（红线核心） | 注入 CF 挑战响应（403+`cf-mitigated` / 200+"Just a moment" / CAPTCHA 三形态各一）→ ① 判 CHALLENGE ② 抛 `Challenged`→BLOCKED ③ 域冷却 24h 写入且**下次 drain 读得到** ④ 报告显著提示 ⑤ **零重试零绕过**（调用序列断言：`goto`=1、`download_via`=0） | 判据①⑤：`tests/unit/test_browser_fetch.py::test_t2_t3_challenge_stops_immediately`；判据②：`tests/integration/test_browser_fetch_pipeline.py::test_challenge_raises_and_logs_failure_row`；判据③（E-1 修复判据载体）：`tests/integration/test_cf403_cooldown.py::test_t7_open_access_challenge_cooldown_blocks_second_drain` + `test_challenge_writes_domain_key_not_adapter_key`；判据④沿用 AC-4.6 既有报告机制（`pipeline/report.py` blocked 计数+提示文案），design/11 §6.2 明文"不新增报告结构"，非缺口。**载体缺口**：`download_via` 内部第二跳导航不重新过判定器（若该处才发质询→归 `TRANSIENT` 进重试表，非 `Challenged`）——上述调用序列断言仅覆盖 `goto` 层判据⑤，不覆盖此二跳场景；已登记 `browserfetch.py` 模块 docstring"已知边界 #2"+`tests/manual/browser_fetch_runbook.md` §5 第 2 行，fable 已裁"本 Phase 维持现状"（过度重试方向安全），转正不因此改判据文字 |
| AC-BF.2 | AC-0.2 静态红线 | 全仓静态扫描：本通道代码无求解/绕过语义（无打码服务调用、无 UA/指纹轮换、无 stealth 插件、无质询脚本执行）；`hcaptcha`/`recaptcha` 串仅出现在检测上下文 | `tests/unit/test_browser_fetch.py::test_ac_bf2_module_source_has_no_solver_or_evasion_semantics`（同名直接载体）；UA 恒定诚实旁证：`test_default_launcher_wires_identity_header_and_storage_state` + `tests/integration/test_browser_fetch_pipeline.py::test_identity_header_is_honest_ua_string` |
| AC-BF.3 | 单篇取回（对标 AC-4.1） | 用户已 CF-cleared session + 非阻断网络下，`crawler grab --doi <X> --browser` 取回 1 篇，`%PDF` 魔数校验过、>10KB、DB↔文件对账一致 | `tests/manual/browser_fetch_runbook.md` §3（T-11，**非 CI**，用户参与，结果留痕 `testing/records/`）；离线对应物：`tests/unit/test_browser_fetch.py::test_t1_ok_path_downloads_to_dest` |
| AC-BF.4 | 预算与限速审计（对标 AC-4.4/AC-0.5） | ① 单 venue×域单日 browser-fetch 尝试 ≤ `browser_daily_cap`（FetchLog 对账，成败均计）；② 相邻两次请求间隔 ≥ 域声明下限（ssrn ≥5s；obslog `channel="browser"` 事件时序审计）；③ 达 cap → BLOCKED 非 FAILED | 判据①③：`tests/integration/test_browser_fetch_pipeline.py::test_t5_quota_boundary_allows_cap_minus_one` + `test_t5_quota_blocks_at_cap_without_extra_fetch_log`（拒绝不落尝试行，非 failed）+ `test_t5_quota_is_scoped_to_venue_and_domain`；熔断三判定：`test_t5_cooldown_precedes_quota` + `test_t5_breaker_after_three_consecutive_failures`；L2 限速机制：`test_rate_gate_charges_每次导航`（`RateLimiter` 假时钟断言）。**载体缺口**：判据②字面"obslog 时序审计"无直接载体——`browserfetch.py` 已知边界 #3（T6 审查登记，本卡转正评估结论：维持现状）如实：obslog 每次调用只记 `rate_wait_ms` 汇总，无请求发起时刻序列，真实约束在 `RateLimiter` 桶配置（已测）而非日志；时序审计留 T19 在线批人工计时佐证 |
| AC-BF.5 | 无权限降级（对标 AC-4.3） | 判 NO_ENTITLEMENT → asset 标 `no_entitlement`、**不计 failures**、不重试；有 DOI 时派生 OA-fallback（既有链）；无 OA 副本时如实无副本 | `tests/unit/test_browser_fetch.py::test_t2_no_entitlement_returns_outcome_without_raising`（`fetch_one` 层，不抛异常）；`tests/integration/test_browser_fetch_pipeline.py::test_no_entitlement_raises_for_existing_oa_chain`（stage 层转译接入既有 OA-fallback 链）；不计 failures 回归：`test_t5_no_entitlement_rows_do_not_trip_the_breaker` + `test_t5_no_entitlement_rows_are_transparent_to_the_streak` |
| AC-BF.6 | CF-403 缺口闭合（S-c 已采纳，D-030） | 403+`cf-mitigated: challenge` → `challenge`（非 `no_entitlement`）+ 冷却；403 无该头 / wiley TDM 403 → `no_entitlement` **行为逐字不变**（回归锁定）；全库 fixture 零翻转 | `tests/unit/test_http.py::test_t6_form1_cf_403_maps_challenge` + `test_t6_form2_plain_403_stays_no_entitlement` + `test_t6_form2_cf_mitigated_other_value_stays_no_entitlement` + `test_t6_form3_wiley_tdm_403_stays_no_entitlement`（三形态+回归锁定）；`test_t6_full_repo_403_fixture_scan_zero_flip` + `test_t6_scan_finds_the_expected_403_fixture_corpus`（全库零翻转+扫描器自证不空跑）；端到端：`tests/integration/test_cf403_cooldown.py::test_t6_cf403_through_http_client_reaches_cooldown` + `test_plain_403_still_no_entitlement_end_to_end` |

**载体缺口小计**：2 处（AC-BF.1 判据⑤的 `download_via` 二跳导航细分场景；AC-BF.4 判据②的时序审计字面形态），均为 T6/T11 审查已登记的已知边界（非本卡新发现），本卡按"如实标注不改判据"原则转正，不因转正而扩大或缩小判据范围。

## AC-8 · Venue 追踪（跨 Phase，随会议 adapter 验收）

| ID | 场景 | 通过判据 |
|---|---|---|
| AC-8.1 | 多段 era 路由 | `timeline colt` 显示 PMLR/Springer/ACM 三段 era，各段路由到对应 adapter |
| AC-8.2 | 追新→确认→落配置 | 模拟 DBLP 新卷 → `track` 出候选 → `track review` confirm → VenueSpec eras 段被正确更新 |
| AC-8.3 | 缺口区分 | `timeline naacl --audit` 区分"官方未举办年"与"数据缺失年" |

## AC-0 · 合规红线（贯穿所有 Phase，任何违反即整体不通过）

| ID | 判据 |
|---|---|
| AC-0.1 | 代码库与运行路径中不存在任何盗版源（Sci-Hub 等）集成点（静态扫描 + 人工核） |
| AC-0.2 | 无 CAPTCHA 自动求解/绕过代码；风控页一律走 BLOCKED |
| AC-0.3 | 凭证/session/PDF 不出现在 git 历史（`git log` 全历史扫描 + .gitignore 生效验证） |
| AC-0.4 | 日志与报告中无未脱敏的 cookie/token（正则扫描断言） |
| AC-0.5 | 各 adapter 默认限速 ≤ 其 research/site-survey 文档记载的站点要求；robots.txt 明确禁止的路径不访问（记录例外需 ADR） |

## 附：FR/NFR → AC 覆盖映射（可追溯性总表，D-016）

> 每条功能/非功能需求（[design/00-requirements.md](../design/00-requirements.md)）至少被一条 AC 覆盖。设计文档不逐条回引 FR 编号，追溯统一经本表。

| 需求 | 覆盖 AC | 备注 |
|---|---|---|
| FR-01 venue 注册表 | AC-1.6, AC-1.1 | lint 校验 + 端到端 |
| FR-02 时间轴发现 | AC-2.1, AC-8.1, AC-3.5 | 会议届数 / 多段 era / 期刊零爬取 |
| FR-03 年度追新 | AC-8.2 | track 候选→确认→落配置 |
| FR-04 期/届清单枚举 | AC-3.5, AC-2.1, AC-2.4 | 篇数对账（paper_count_claimed） |
| FR-05 精确选择 + dry-run | AC-1.2, AC-2.2, AC-2.4 | limit / filter / dry-run 零副作用 |
| FR-06 开放源下载 | AC-2.2, AC-2.5, AC-2.6, AC-5.2, AC-5.3 | 含 bulk 优先与 ACM OA 场景 |
| FR-07 认证源下载 | AC-4.1 | 全平台 runbook 逐个执行 |
| FR-08 会话管理 | AC-4.2, AC-4.5, AC-1.5 | 过期检测 / 登出无残留 / BLOCKED-resume |
| FR-09 礼貌爬取 | AC-1.4, AC-4.4, AC-5.1a, AC-5.1b, AC-0.5 | 限速审计 / 日配额 / robots |
| FR-10 断点续爬 | AC-1.3, AC-3.3 | kill-9 幂等 / verify 对账 |
| FR-11 元数据入库与合并 | AC-3.1, AC-3.2, AC-3.4 | 强合并 / 弱信号候审 / 顺序无关 |
| FR-12 文件管理 | AC-1.1, AC-3.3 | DB↔文件双向对账 |
| FR-13 全文抽取 | AC-7.1, AC-7.2 | GROBID 可选降级 |
| FR-14 观测性 | AC-1.4, AC-4.2, AC-4.4 | FetchLog 为审计证据源；canary 见 test-plan §4 |
| FR-15 订阅 DSL | AC-6.1, AC-6.3, AC-6.4, AC-2.3 | 编译下推与本地一致性 |
| FR-16 增量与护栏 | AC-6.2, AC-2.3 | 熔断 / 无重复无遗漏 |
| NFR-3 断点续爬 | AC-1.3 | |
| NFR-4 限速默认值 | AC-1.4, AC-0.5 | |
| NFR-6 离线可测 | T3 fixture 门禁（test-plan §1） | 非 AC 形态，CI 强制 |
| NFR-8 凭证安全 | AC-0.3, AC-0.4, AC-4.5 | |

> NFR-1/2（新增成本）、NFR-5（可观测定位）、NFR-7（资源）为度量型指标，验收方式=Phase 报告中实测记录（非二值判据）。
