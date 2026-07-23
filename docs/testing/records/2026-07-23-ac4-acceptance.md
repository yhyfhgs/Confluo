---
title: AC-4 离线端到端验收汇总记录 — 认证与出版社（离线载体收口）
status: draft
owner: t7a
updated: 2026-07-23
---

# AC-4 离线验收汇总记录（AC-4.2~4.6 离线载体 + DoD + 移交）

> 判定依据：[acceptance-criteria.md](../acceptance-criteria.md) AC-4.2~4.6 原文、[auth-framework.md §8/§11/§12](../../design/auth-framework.md)、[phase4-implementation-plan.md §7](../../plan/phase4-implementation-plan.md)。
> 记录范式：[Phase 3 验收汇总记录](2026-07-23-phase3-acceptance.md)（逐条判定表 / 证据链 / DoD / 纪律事项 / 签署）。
> 证据链：T5 pipeline 集成载体 `tests/integration/test_auth_pipeline.py`、T6 mock IdP 生命周期载体 `tests/integration/test_auth_lifecycle.py`、T1a/T1b 单元层 `tests/unit/test_auth_{store,manager,challenge}.py`、T5 grab `tests/unit/test_cli_grab.py`。
> 代码基线：`test/ac4-e2e` @ `f22407f`（Phase 4 全实现件 + T5 pipeline 集成合并态；base = T5 merge，含 fable 审查 2 MAJOR 闭合）。**本记录零在线请求**——AC-4.2~4.6 全离线判定（分层验收 D-018；AC-4.1 真实凭证归 T7b）。
> **定位**：本记录是 T7a 汇总验收——不新写实现，而是亲跑 T5+T6 已落地的离线载体、逐条 AC 判定、成正式记录。

## 0. T7a 汇总的关键收口（两层证据合流）

T6 载体 `test_auth_lifecycle.py` 的 docstring 在其独立开发期（T5 尚未合并）注记："批级 `_auth_batch`/`_auth_blocked_venues` wiring 归 T7a 收口"、"本 worktree 未合并 pipeline/runner.py"。**在本 T7a worktree（base = f22407f = T5 merge）中，T5 的真实 `PipelineRunner` 批级健康门与 T6 的 provider 层证据首次共存**——T6 当时悬置给 T7a 的"批级 BLOCKED wiring"由共存的 T5 载体 `test_auth_pipeline.py`（真实 runner + `_BatchGate`）闭环证明。这正是 AC-4.2 的**两层证据**（批级门 + provider 层双源）合流点，也是本汇总记录的核心增量。

## 1. AC-4.2~4.6 逐条判定

| AC | 场景（原文摘） | 判定 | 承载载体 |
|---|---|---|---|
| AC-4.2 | 过期检测不轰炸：session 失效 → ≤20 篇内 BLOCKED，日志无连续 401（≤2 即停） | **PASS（离线）** | T5 批级门 5 用例 + T6 provider 层双源 4 用例 |
| AC-4.3 | 无权限降级：no_entitlement 标记 + 不重试 + 给出 Unpaywall 副本 | **PASS（离线）** | T5：真实 elsevier resolve NE→OA 全链（MAJOR-1）+ 泛 mock 全链 + 7 边界 |
| AC-4.4 | 日配额：单平台单日 ≤ 上限（FetchLog 对账） | **PASS（离线）** | T5：`count_fetch_today` `DATE(ts)` 对账 3 用例 |
| AC-4.5 | 登出无残留：logout 后磁盘无可恢复 session（取证清单逐项） | **PASS（离线）** | T6 全 home 树字节扫描 + T1b store 4 + manager 6 |
| AC-4.6 | 风控即停：注入风控页 → BLOCKED(challenge) + 冷却 + 无自动破解 | **PASS（离线）** | T5 冷却持久 3 + T6 双路径一致 2 + ChallengeDetector 23 |

---

### AC-4.2 · 过期检测不轰炸 — **PASS（离线）**

**场景原文**：人为清 cookie 使 session 失效 → 批任务在 ≤20 篇内检出并 BLOCKED；日志无连续 401/403 轰炸（≤2 次即停）。

**两层证据（B-m8 双源 + 批级门）**：

*批级门（T5，真实 `PipelineRunner` + `_BatchGate`，`test_auth_pipeline.py`）*：
- `test_first_fetch_auth_expired_blocks_batch_no_bombardment`：n=8 批，首 fetch 撞 401 → `blocked==8`（1 触发 + 7 连带 `_auth_blocked_venues`）、`fetch_calls==1`、`auth_fail_calls==1`（≤1，无轰炸）。
- `test_health_gate_detects_expired_within_interval`：n=10、`auth_health_interval=2` → 前 2 篇成功、第 3 篇门触发 `health_check==EXPIRED`（refresh→None）→ `succeeded==2`/`blocked==8`、`health_calls==1`、`fetch_calls==2`（门前置拦截，EXPIRED 后 0 次 fetch）、`auth_fail_calls==0`。
- `test_health_gate_aging_triggers_check_and_refresh_continues`：老化门 EXPIRED→refresh 成功续期 → `succeeded==2`/`blocked==0`、`refresh_calls==1`、session 换新（`payload_ref=="refreshed"`）。
- `test_ensure_session_unavailable_blocks_batch`：批入口 `ensure_session` 抛 AuthRequired → `blocked==3`、`fetch_calls==0`（未发起取回）。
- `test_integrity_forces_health_check_on_next_fetch`（MAJOR-2）：伪装 PDF→INTEGRITY→门龄归零→下个 fetch 强制 `health_check`（`health_calls==1`），防伪装页连环命中。

*provider 层双源（T6，`test_auth_lifecycle.py`）*：
- `test_ac42_batch_fetch_stops_after_first_401_dual_source`：≤20 篇批，第 8 篇 session 失效 → `blocked_at==8`（<20，"≤20 篇内检出"）、`route_hits("/article-pdf/")==8`（7 成功 + 1 次 401，之后零请求）。**主证** `mock_idp.status_count(401)==1`（≤2）；**辅证** obslog jsonl 独立扫描 `status==401` 事件 `==1`（≤2）——两条独立代码路径（MockTransport handler vs `HttpClient._log_exchange`），非同一计数复读。
- `test_ac42_health_check_expired_and_unrefreshable_is_the_block_signal`：EXPIRED+refresh None 幂等复检（探测不"治愈"、不放大），`route_hits` 精确 =2/2（无隐藏重试）。
- 生命周期链 `test_lifecycle_03_expiry_detected_via_probe_redirect` / `_04a_refresh_succeeds_while_idp_session_alive` / `_04b_refresh_none_when_idp_session_also_gone` 证 provider 探测/续期契约稳定。

**亲跑**：`test_auth_pipeline.py` 31 passed、`test_auth_lifecycle.py` 10 passed（`pytest -p no:randomly`，1.7s，零真实网络）。

**口径注记**：真实 401 轰炸的**线上**演练（真实平台清 cookie → 观察实际 401 计数）归 T7b runbook；离线层以 MockTransport handler 401 计数（主证）+ obslog 事件扫描（辅证）双源精确断言"≤2 即停"，为 AC-4.2 的**可 CI 判定**载体。

---

### AC-4.3 · 无权限降级 — **PASS（离线）**

**场景原文**：对无订阅 DOI → 标 no_entitlement、不重试、给出 Unpaywall 副本（若存在）。

**首证（核心载体，MAJOR-1 修复的真实端到端）**：
- `test_elsevier_resolve_entitlement_false_derives_oa_fallback`（`test_auth_pipeline.py`）：**真实 `ElsevierScienceDirectAdapter`** 在 **resolve** 阶段 entitlement 预检 `entitled:false`（MockTransport 回真实封套结构）→ 抛 NO_ENTITLEMENT（非 fetch 阶段）→ runner 从 `params["paper"]` 派生 `oa_fallback` → unpaywall 规格化 OA pdf plan → `_fetch_oa_direct` 无凭证 direct 取回落盘。断言：`no_entitlement==1`/`failed==0`（不计失败率，§8.5）、`ua.calls==1`、`fetched[0].source_adapter=="unpaywall"` 且 `file_path` 为 %PDF 实文件。此前 NE 派生仅限 `kind=="fetch"`（asset_id 门控），resolve NE 不派生 → elsevier 无权 DOI 得不到 OA 兜底，AC-4.3 破；本用例是该修复的端到端断言（真实 elsevier 场景，非泛 mock）。

**辅证（泛 mock 全链 + 边界）**：
- `test_no_entitlement_triggers_oa_fallback_direct_fetch`：no_entitlement→OA-fallback 落盘 OA asset（`publishedVersion`），原平台 asset 停 no_entitlement 与 OA 副本身份并存不覆盖。
- `test_no_entitlement_no_oa_link_no_download`：unpaywall 无 PDF 直链 → done、无副本落盘（landing-only 不下载，"若存在"口径）。
- 边界 5 条：`test_no_entitlement_paper_without_doi_no_oa_fallback`（无 DOI 不兜底）、`test_oa_fallback_disabled_no_derivation`（默认关不派生）、`test_oa_fallback_no_unpaywall_adapter_skips`、`test_oa_direct_fetch_no_http_client_skips`（asset 停 planned）、`test_oa_direct_fetch_non_pdf_fails_integrity`（OA host 非 %PDF→INTEGRITY+`.part` 清理）；幂等 `test_oa_direct_fetch_idempotent_skip_when_already_fetched`（MINOR-1）。

**亲跑**：随 `test_auth_pipeline.py` 31 passed 全绿。

**口径注记**："不重试"由 no_entitlement 独立终态（不进 RetrySpec、不计 failures）保证；真实无订阅 DOI 的**线上** Unpaywall 命中率归 T3/T-wiley 真实 no_entitlement + T7b。离线以真实 elsevier resolve 封套 + MockTransport OA host 完成 NE→OA 全链落盘的可 CI 判定。

---

### AC-4.4 · 日配额 — **PASS（离线）**

**场景原文**：单平台单日下载数 ≤ 配置上限（FetchLog 对账）。

**承载载体（`test_auth_pipeline.py`）**：
- `test_daily_quota_reached_blocks`：预置 3 行 fetch_log 占满当日配额、`auth_daily_cap=3` → 后续两篇 `blocked==2`、`succeeded==0`、`fetch_calls==0`（门前置拦截，未发起取回）、`blocked_reason` 含"日配额"。对账口径 = `count_fetch_today(domain)` 走 `SELECT COUNT(*) FROM fetch_log WHERE domain=? AND DATE(ts)=DATE('now')`（"fetch 尝试篇次"，成败均计，resolve 不计）。
- `test_default_daily_cap_is_200`：默认 `_DEFAULT_AUTH_DAILY_CAP==200`（§8.3 / 04 §4）。
- `test_runner_reads_real_config_field_not_getattr_default`（controller 令对照）：`config.toml [auth].daily_cap=3` 经 `Config.load` 落**真实字段**（非 `object.__setattr__` 注入）→ runner 读到真实 3 而非 getattr 兜底 200 → 达 3 即 `blocked==1`。

**亲跑**：随 `test_auth_pipeline.py` 31 passed 全绿。

**口径注记**：FetchLog 为对账唯一证据源（design/05 §7"AC-4.4 数据源"）；OA-fallback direct fetch 走第三方 OA host 桶，天然不占 auth 平台域配额（§8.1/§8.3 限速隔离对账侧印证）。真实平台日配额的**线上**长跑对账归 T7b。

---

### AC-4.5 · 登出无残留 — **PASS（离线）**

**场景原文**：`auth logout <provider>` 后磁盘无可恢复 session（取证清单逐项过）。

**集成层全 home 树取证（T6，`test_auth_lifecycle.py`）**：
- `test_lifecycle_05_logout_forensic_wipe_full_home_tree`：经 `AuthManager.logout("oup@shib")`（非手搓 provider.invalidate）→ 取证清单（B-m6 有状态类）：`state/*.enc`、`*.meta.json`、keyring 主密钥条目全清。**超出已知路径逐一核对的范围**——对**全 home 目录树** `rglob("*")` 逐文件读字节，断言 cookie 明文不藏任何角落（`scanned_files>0` 反空扫误判绿）；再次 logout 幂等静默成功（non-fatal no-op）。

**store 层取证式删除（T1b，`test_auth_store.py`）**：
- `test_delete_state_overwrites_content_before_unlink`：spy `Path.unlink` 捕获——unlink 时内容已被随机覆写（`!=original`）且**等长覆写**（无截断残留窗），防删除后磁盘可恢复。
- `test_delete_state_missing_is_silent_noop`、`test_delete_state_removes_meta_sidecar_too`、`test_forensic_unlink_zero_size_file`（零字节文件覆写不崩）。

**manager 层按 kind 分列（T1b，`test_auth_manager.py`）**：
- `test_logout_stateful_forensic_chain`（有状态类 .enc+meta+keyring 链）、`test_logout_stateful_keeps_master_key_while_others_remain`（多 provider 时主密钥保留）、`test_logout_clears_session_cache`（进程内缓存清）、`test_logout_api_key_keyring_copy_only`（api_key 类只清 keyring 副本、不删用户 config.toml 明文槽）、`test_logout_unknown_provider_raises`（未知 provider→退出 2）、`test_logout_idempotent_when_nothing_stored`。

**亲跑**：`test_auth_lifecycle.py` 10 passed；`test_auth_store.py` delete_state/forensic 子集 4 passed；`test_auth_manager.py` logout 子集 6 passed。

**口径注记**：取证清单第⑥项"无残留一次性 user-data-dir"（浏览器 profile）由 `test_auth_browser.py` 的 mkdtemp/rmtree 机制覆盖（本 Phase 首登假 seam 不触真实浏览器）；api_key 类⑥/①不适用（无 storage_state / user-data-dir）。真实浏览器上下文的登出残留**线上**核验归 `PC_BROWSER_TESTS` 手动门 / T7b。

---

### AC-4.6 · 风控即停 — **PASS（离线）**

**场景原文**：注入风控页特征 → BLOCKED(challenge) + 平台冷却生效 + 报告显著提示；无自动破解尝试。

**冷却持久化（T5，`test_auth_pipeline.py`）**：
- `test_challenge_blocks_and_writes_cooldown`：fetch 命中挑战 → `blocked==3`、`fetch_calls==1`（首篇命中；其余经冷却门连带 BLOCKED 未 fetch）、冷却状态落盘 `<home>/state/cooldown/<platform>.json`、`blocked_reason` 含 challenge。
- `test_challenge_cooldown_persists_across_runs`：预置 12h 冷却文件（模拟前次运行）→ 新 runner `blocked==1`、`fetch_calls==0`（跨运行从 JSON 加载冷却拦截）。
- `test_health_check_challenged_blocks_and_cooldown`：健康门 `health_check→CHALLENGED`（非 fetch 抛）→ `blocked==3`、冷却落盘。

**双路径一致 + 不重试（T6，`test_auth_lifecycle.py`）**：
- `test_ac46_challenge_cross_validated_and_platform_resolvable`：mock 返 `cf-mitigated: challenge` 头 + "Just a moment..." body → 两条独立探测路径 `health_check`（如实上报 CHALLENGED，不抛）与 `refresh`（命中风控显式抛 `Challenged`，`error_class==CHALLENGE`）对**同一**挑战态一致判定，`route_hits("/my-account")==1`、`route_hits("/InstitutionalLogin")==1`（各只探一次，不对抗不重试，AC-0.2）；`platform=="oup_silverchair"` 零网络解析（冷却落盘键）。
- `test_lifecycle_04c_refresh_raises_challenged_on_challenge_page`：refresh 命中挑战→`Challenged`，`route_hits==1`（命中即报，绝不重试）。

**判定器特征库（T1a，`test_auth_challenge.py`，23 passed）**：`ChallengeDetector` 四态（OK / LOGIN_REDIRECT / NO_ENTITLEMENT / CHALLENGE）判定；`test_challenge_takes_precedence_over_login_and_entitlement_signals`（挑战信号优先级最高）；`cf-mitigated` 头大小写不敏感 / Cloudflare 拦截页 body / hCaptcha·reCAPTCHA·"unusual activity" 签名 → CHALLENGE；结构化 `status`（非文本嗅探）；非 utf-8 body 不崩。**全程无任何破解/绕过/CAPTCHA 求解代码**（AC-0.2/AC-4.6 红线）。

**亲跑**：随 `test_auth_pipeline.py`（3 冷却用例）+ `test_auth_lifecycle.py`（2 挑战用例）+ `test_auth_challenge.py` 23 passed 全绿。

**口径注记**："报告显著提示"由 RunReport 的 BLOCKED(challenge) 计数 + `blocked_reason` 承载；真实平台 Cloudflare 挑战墙的**线上**撞墙 → BLOCKED 演练归 T7b + canary 周检。

## 2. AC-4 DoD 小结（离线载体全绿 = AC-4.2~4.6 达成）

| DoD 项 | 判定 | 依据 |
|---|---|---|
| AC-4.2~4.6 离线载体全绿 | **达成** | 本记录 §1 逐条 PASS（离线口径）；T5+T6 载体 41 passed，单元层 33 passed（store/manager/challenge 子集）+ grab 6 passed |
| 分层验收边界如实（D-018） | **达成** | AC-4.2~4.6 = 离线 mock 层判定 PASS（可 CI）；AC-4.1（elsevier API 真实取回）+ oup SSO runbook = 真实凭证"用户参与层"，**归 T7b，不阻塞离线 DoD** |
| 零在线请求（本任务） | **达成** | 全程 MockTransport / 假时钟 / 假 browser seam / conftest socket 护栏；本记录零在线预算消耗 |

**结论**：AC-4.2/4.3/4.4/4.5/4.6 离线载体全部亲跑通过 → **AC-4.2~4.6 达成（离线口径）**。AC-4.1 真实 API 取回按 D-018 分层归 T7b，**不阻塞** T8 离线收尾与 tag。

## 3. 亲跑台账（本 worktree `f22407f`，`uv run pytest -p no:randomly`，零真实网络）

| 载体 | 计数 | 承载 AC |
|---|---|---|
| `tests/integration/test_auth_pipeline.py`（T5） | **31 passed** | AC-4.2 批级门 / AC-4.3 全链+边界 / AC-4.4 配额 / AC-4.6 冷却 |
| `tests/integration/test_auth_lifecycle.py`（T6） | **10 passed** | AC-4.2 双源 / AC-4.5 全 home 树 / AC-4.6 双路径 |
| `tests/unit/test_auth_store.py`（delete_state/forensic 子集） | **4 passed** | AC-4.5 取证式删除 |
| `tests/unit/test_auth_manager.py`（logout 子集） | **6 passed** | AC-4.5 按 kind 分列 |
| `tests/unit/test_auth_challenge.py`（T1a） | **23 passed** | AC-4.6 判定器特征库 + AC-0.2 |
| `tests/unit/test_cli_grab.py`（T5） | **6 passed** | AC-4.1 全链骨架（grab 三退出码，真实取回归 T7b） |
| **auth 全离线套件**（上述 + providers/cli/browser/protocol/types 11 文件合跑） | **275 passed** | — |

## 4. 口径与适用边界（离线 vs 线上分层）

- **离线 PASS 的证明力**：AC-4.2~4.6 的**逻辑正确性**（NE→OA 派生、批级门 ≤20 篇检出、日配额对账、取证式删除、挑战→冷却）由 mock IdP / MockTransport / 假时钟精确断言，**可 CI 复现、零真实网络**。
- **归 T7b 的线上口径**（本任务不含，如实标注，不阻塞离线 DoD）：AC-4.2 真实 401 轰炸计数、AC-4.3 真实无订阅 DOI 的 Unpaywall 命中、AC-4.4 真实平台长跑配额对账、AC-4.5 真实浏览器 profile 残留、AC-4.6 真实 Cloudflare 挑战墙撞墙——均为"必须真实网络"项，随 AC-4.1 真实 key/token 一并入 T7b runbook。

## 5. 移交 T7b / T8

- **AC-4.1 真实 key/token 冒烟（→ T7b）**：`auth login elsevier`（APIKey）→ JFE DOI 经 Article Retrieval API 得魔数校验合格 PDF；wiley token→JF/ECMA；oup SSO→QJE。R0 [LIVE 2026-07-23] 确认 config/env **无 elsevier key**（BLOCKER-1，外部依赖申请 1–2 周）→ 未到位则 AC-4.1 降级 runbook-only 分层（D-018）。grab 全链骨架已由 `test_cli_grab.py` 离线覆盖（含"未入库→crossref lookup→建行→resolve+fetch"路径，即 AC-4.1 runbook 的 JFE DOI 场景）。
- **asset 路径 version 债务（→ T8 / design 修订）**：OA-fallback 产的 OA 副本 asset 唯一键含 `version`（design/06 §2，如 `publishedVersion`），但落盘路径布局 `data/pdf/<venue>/<year>/<ulid>.pdf` **不含 version 判别位**，原平台 asset（version=None）与 OA 副本仅靠 ULID 区分——审查转 design/06 缺口，建议 T8 登记入债务表 / design 修订议题（非离线 DoD 阻塞项，身份并存语义在 `test_no_entitlement_triggers_oa_fallback_direct_fetch` 已验不覆盖）。
- **AuthManager DI 缺口（T6 发现 → T8 登记）**：`AuthManager.resolve/get` 走 provider 默认构造，**不支持注入 `http_factory`/`login_flow` 测试 seam**——故 T6 全生命周期集成须直接 `SSOFlowProvider(...)` 构造（`_make_sso_provider`），仅 `logout`（网络无关）经 `AuthManager` 驱动。生产无影响（默认构造即真实路径），但集成测试无法端到端经 manager 装配 mock 平台；建议 T8 登记为可测性改进 backlog（非阻塞项）。

## 6. 签署

- **初判（2026-07-23，t7a）**：AC-4.2/4.3/4.4/4.5/4.6 **离线载体全部亲跑 PASS**（口径逐条注明）；AC-4 离线 DoD **达成**；AC-4.1 + 线上口径按 D-018 分层归 T7b，不阻塞离线收尾。本记录 status=draft，待 controller 亲验 + T8 统一登记（INDEX/progress 不在本任务改动范围）。
- **待办**：controller 亲验（`make check` 复跑吻合 + 载体计数复现）；§5 移交三项入 T7b/T8 检查单。
