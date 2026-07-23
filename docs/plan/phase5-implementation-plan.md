---
title: Phase 5 实施计划 — SSRN 与特殊经济学源 adapters
status: approved
owner: controller
updated: 2026-07-24
---

# Phase 5 实施计划 — SSRN 与特殊经济学源 adapters

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development 逐任务派发执行。
> 判定依据：[development-plan §Phase 5](development-plan.md)、[acceptance-criteria AC-5/AC-0](../testing/acceptance-criteria.md)、
> [decision-log D-027/D-028/D-029](decision-log.md)（RePEc 出列 / ECMA 分段路由 / SSRN 定位修订，均 2026-07-24 正式化）。
> 实施模式沿用 phase1–4 验证过的全部纪律（详设 approved 硬门禁 / worktree 波次并行 / 每任务独立审查 +
> 限量真实交叉验证 / fix 循环 / 主 agent 合并亲跑门禁 / 全分支终审 / SDD ledger）。
> **详设载体（四份全 approved，W0 已闭合，本计划引用节号不复制设计内容）**：
> [ssrn.md](../design/adapters/ssrn.md) / [nber.md](../design/adapters/nber.md) /
> [aea.md](../design/adapters/aea.md) / [econsoc.md](../design/adapters/econsoc.md)；
> 结构模板 [elsevier-sd.md](../design/adapters/elsevier-sd.md)、OAI 复用面 [aaai-ojs.md](../design/adapters/aaai-ojs.md)、
> 聚合接缝 [aggregators.md](../design/adapters/aggregators.md)、OA-fallback 接缝 [auth-framework.md §8](../design/auth-framework.md)。

**Goal**：交付四个经济学/金融特殊源 adapter——`ssrn`（Crossref 前缀 10.2139 聚合元数据主路径，站点零接触，D-029）、
`nber`（前缀 10.3386 枚举 + >18 月开放窗离线全文，D-014 软门不绕过）、`aea`（前缀 10.1257 含摘要 + DOI 双形态 8 刊路由，
全文 deferred）、`econsoc`（TE/QE OJS-OAI 自枚举 + ECMA crossref + 运行时域名分段路由，D-028）；为此**先扩展 `CrossrefAdapter`
为通用参数化枚举源**（enum-key issn XOR prefix + date-field published|created，nber/ssrn 共用）；量化 SSRN 覆盖率、正式化 AC-5.x、
落地 13 个 venue YAML。全 Phase 元数据主干走聚合 API（D-005），全文按各源合规姿态分层（OA 直取 / OA-fallback / deferred）。
AC-5.1a/5.2/5.3/5.4 离线 CI 可判 + 限量在线冒烟（D-018 分层）。**repec 出列**（D-027，enrich 通道候选挂 Phase 6）。

**Architecture**：Phase 1–4 冻结接口不变（SourceAdapter 五方法协议 / HttpClient 签名 + `status_code` / pipeline 六阶段 +
OA-fallback 第七 handler / MergeEngine / AuthProvider）。Phase 5 增量**两类**：①**唯一动 implemented 冻结件**＝
`CrossrefAdapter` 参数化枚举扩展（T1，两轴 enum-key/date-field，`to_paper_stub` 不动，既有 by-ISSN 消费者零回归）；
②四个**纯附加** adapter 包 + 各自 venue YAML（`adapters/{ssrn,nber,aea,econsoc}/`，disjoint 包目录 + entry-point union）。
`_oai.py` 信封（`parse_oai_page(data, *, record_parser)` 已 arxiv+aaai 双消费）由 econsoc 作**第三消费者**注入 `record_parser`
回调，**零改 implemented aaai_ojs**（econsoc.md §4 ★C）。全文获取全部复用既有 pipeline direct-fetch / OA-fallback（auth-framework §8），
**不新增 pipeline/auth/config 面**（四源 auth 均 `none`，不触 cryptography/keyring/Config-slot）。

**Tech Stack**：不变（Python 3.12+ / httpx / sqlite3 / pydantic v2 / typer / pytest+coverage / ruff / mypy strict）。
**零新增依赖**——四源均 open_access、无浏览器/加密/凭证需求；SSRN 模式 B（浏览器全文）与 browser-fetch 横切件 **defer Phase 6**（D-029 案 B）。

## Global Constraints（每个任务隐含继承）

- **AC-0 红线五条**（[acceptance-criteria AC-0](../testing/acceptance-criteria.md)）：无盗版/未文档化软门绕过集成点（**SSRN 内部 `api.ssrn.com` 禁用、
  NBER <18 月软门永不绕过**，D-014）；无 CAPTCHA 求解/风控对抗（Cloudflare 挑战一律 BLOCKED——ssrn/aea pubs/econsoc 域）；
  凭证/PDF 不入 git；日志报告脱敏；限速 ≤ 站点声明、robots 禁区不访问（NBER `/search/` 禁、DBLP 先例 D-026）。
- **爬虫域硬红线（[AGENTS §6](../../AGENTS.md) 逐条约束，不复述）**：诚实 UA `PaperCrawler/<ver> (personal research; mailto:<user>)`
  （D-014，绝不伪装浏览器）；robots/AI-bot 指令遵守（aea/econsoc 具名封 GPTBot/ClaudeBot → 落 `*` 组、诚实非训练用途、全文从严）；
  敏感站只取合法开放元数据；**遇挑战即停手不对抗**（AC-0.2）；开放许可（CC BY/BY-NC）个人科研只读、不再分发（AGENTS §6.5）。
- **真实网络纪律**：默认测试零真实网络（socket 禁网护栏在位）；`tests/online/` 显式 `-m online` + committed `MAX_REAL_REQUESTS` 预算头；
  聚合层请求证据 = obslog jsonl 逐请求事件（metadata 侧不入 FetchLog，design/05 §7）；`UPDATE_GOLDEN=1` 重录 golden/canary。
- **门禁**：`make check`（sync-dev+lint+type+test）全绿方可合并（覆盖率 ≥80% 不回退）；**各 adapter 解析/判定模块 ≥90%**（DOI 抽取/
  路由/18 月窗谓词/oai_dc 体层/过滤谓词）。
- **详设硬门禁**：四详设 W0 双评审 approved（2026-07-24，D-027/D-028/D-029 落 decision-log）——**门禁已闭合，全卡可直接开工**；
  故本计划 `status: approved`（W0 无未决项）。
- **范围只减不增**（development-plan R5）：本 Phase = ssrn + nber + aea + econsoc（四源）；**repec 出列**（D-027，降级 enrich 候选挂 Phase 6）；
  aea 全文/认证 deferred（browser-fetch 通道待 Phase 6 横切件裁决）；ssrn 模式 B defer Phase 6。
- **提交规范**：Conventional Commits，scope `adapter:<id>` / `core`（crossref 扩展）/ `testing` / `docs`；
  尾行 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`；任何 git 写操作前确认分支（worktree 纪律，实现/审查独立实例）。
- **fixture 纪律**：录制物一律脱敏（无 cookie/token/个人信息/邮箱）；出处分级 [LIVE]/[DOCS]/[SYNTH] 标注（NBER <18 月软门无真实抓取→
  合成 `[SYNTH]`，红线未探）；人工过目后入库；golden/canary 重录走 `UPDATE_GOLDEN=1` + records 留痕（D-019 锚点纪律）。

## §2 接口冻结件（Phase 5 增量；T1 落盘后冻结，改动须仲裁）

> 逐字规范见 [nber.md §3.1](../design/adapters/nber.md)（CrossrefAdapter 扩展全谱规范出处）+ [ssrn.md §4.2](../design/adapters/ssrn.md)（消费侧契约）。本节列冻结锚点。

1. **`CrossrefAdapter` 两轴参数化枚举扩展**（T1；nber.md §3.1，★N-1 裁决=YES）：**唯一动 implemented 冻结件的改动**。
   - **轴① enum-key（issn XOR prefix）**：`_issn_of`→`_enum_key_of(venue)->(mode,key)`（互斥校验）；URL 基址 `/journals/{issn}/works`
     **XOR** `/prefixes/{prefix}/works`（venue `identifiers.crossref_prefix`）。
   - **轴② date-field（published | created）**：三处联动（facet `{field}:*` / filter `from/until-{field}-date` / `parse.parse_facet_years`
     解析 `facets.{field}`）——**评审实证 `parse.py:114` 硬绑 `facets.published` 须泛化**，否则 ssrn 的 `created` facet 恒空。
   - **零改面**：`to_paper_stub`（仍产 `(doi,)`）、cursor 契约、`parse_works_page` 首页空判、限速、UA、polite pool 逐字复用。
   - 消费方：**nber（prefix+published）** 与 **ssrn（prefix+created）**；既有全部 by-ISSN venue（含 aea 8 刊、econsoc ECMA）走 issn+published 原路径**零回归**。
2. **`_oai.py` 第三消费者接缝**（T6；econsoc.md §4，**零改共享件**）：`parse_oai_page(data, *, record_parser)` 已存在
   （arxiv/aaai 双消费 + `test_oai_envelope.py` 守门）；econsoc 仅注入自己的 `record_parser` 回调（找 `<oai_dc:dc>` 体元素），
   **不触碰 implemented aaai_ojs**（体层各写 ~50 行，★C 边界＝信封共享/体层各写）。
3. **无其他冻结件改动**：pipeline / runner / auth / config / errors / http / ratelimit 冻结面**零改**（四源 auth=none、
   全文复用既有 direct-fetch/OA-fallback、`back.nber.org` 独立桶经"域出现即 register 保守桶"OA-host 先例落地——不扩展 ratelimit.py，nber.md §4/wiley §4 同口径）。

## §3 在线预算分项表（全 Phase 专项行 ≤60；超支须如 Phase 2 C-A 入档）

| 分项 | 估算 | 依据 / 环境可行性 |
|---|---|---|
| nber 在线冒烟（T3） | ≤5 | nber.md §7：crossref prefix facet 1 + 已知 >18 月 `w{n}` PDF **HEAD** 1（不下正文）+ landing 1；`www.nber.org` nginx 无挑战 **可行** |
| ssrn 在线冒烟（T4，**零 SSRN 域**） | ≤5 | ssrn.md §7 T5：crossref prefix 1 + openalex source S4210172589 计数 1 + unpaywall SSRN DOI 1（证 landing-only）——**均非 SSRN 域**；SSRN 站点 TLS 阻断，元数据层永不接触 **可行** |
| aea 在线冒烟（T5） | ≤10 | aea.md §8：crossref AER ISSN facet 1 + 单条 DOI 1 + landing 1；**+ 6 刊 ISSN [DOC] 逐一核实**（aeri/aej_×4/jel，UPDATE_GOLDEN，D-019）；**不触 `pubs.aeaweb.org`**（CF 判罚 BLOCKED，全文冒烟标 [环境受限，延后]） |
| econsoc 在线冒烟（T6） | ≤10 | econsoc.md §7 T5：TE `Identify` 1 + OAI 首页 1 + resumptionToken 续页 1 + TE landing→galley→PDF 1 + 当前 ECMA galley HEAD 1（闭 [UNRESOLVED①]）+ ECMA 过刊 doi.org HEAD 1（闭 [UNRESOLVED②] 抽样）+ robots 1；`econtheory/econometricsociety.org` 实测**可达** |
| SSRN 覆盖率 census（M1，走 openalex） | ≤10 | ssrn.md §9.1：openalex `source.id:S4210172589` 分页随机偏移 N≈1000（95%±3% CI），**credit 预算内**（`meta.cost_usd` 实时核销熔断）；独立在线执行段 |
| 缓冲（重试 / 重录 / canary 验证 / robots 复核） | ≤15 | — |
| **合计** | **≤55（上限 60）** | — |

- **环境注记（CF 阻断选择性）**：ssrn 域 = 本机 TLS 层阻断（元数据层零 SSRN 故不受影响）；econsoc 域 = 实测可达；`pubs.aeaweb.org` = 站点 CF 判罚 BLOCKED
  （区别于环境障碍，robots/TLS OK）。**受阻项标 `[环境受限，延后]` 不阻塞离线 DoD**（沿 D-018 分层验收先例）——四源离线 DoD（fixture 回放 + 单测）不消耗在线预算，全 CI 可判。
- **限速审计证据**：元数据聚合 API 请求不入 FetchLog（obslog jsonl 逐请求）；FetchLog 仅在 nber/econsoc 全文 fetch 或 OA-fallback direct 取回落行。

## §4 任务卡

> **卡集：8 卡（7 波次卡 + 1 游离卡），4 波次。** 编号沿 Phase 4 语义（T1 共享地基 / T3–T6 adapter / T7 验收 / T8 收尾）——
> **T2 位（Phase 4 的 config 分层地基件）本 Phase 无对应工作、空缺**；游离卡 **M1**（SSRN 覆盖率 census，沿 Phase 4 M2a/M2b 游离卡先例）
> 承接 ssrn.md §9.1「独立在线执行段」。依赖：**T1、T5、T6 无卡间依赖（W1 同波开工）→ T1 解锁 T3/T4（W2 双发）；T5/T6 全程可与 T1 并行 →
> T7 依 T3+T4+T5+T6 全合并 → T8 依 T7（M1 可后补）；M1 依 T4·游离在线**。每任务 = implementer(worktree) → 双裁决审查（Spec+质量，
> 限量真实交叉验证 ≤5 req 授权）→ fix 回派 → controller 合并亲跑 `make check`。

### T1 CrossrefAdapter 参数化枚举扩展（`core/crossref-prefix`，**opus**/**opus**，**共享地基·触 implemented 冻结件最高关注**）
**Files**：`src/paper_crawler/adapters/crossref/adapter.py`（`_issn_of`→`_enum_key_of(venue)->(mode,key)` issn|prefix 互斥 +
新 `_date_field_of(venue)` 默认 published；`discover_timeline`/`enumerate_issue` 的 URL builder 与 facet 分派按两轴、cursor 循环零改）、
`src/paper_crawler/adapters/crossref/parse.py`（`parse_facet_years` 泛化 `facets.{field}` 按 date-field 取键；**`to_paper_stub` 不动**）、
`tests/unit/test_crossref_{adapter,parse}.py`（扩展）。
**Interfaces**：冻结 §2-1（两轴参数化，规范出处 nber.md §3.1）；enum-key `issn` XOR `prefix`、date-field `published`|`created`；
既有 by-ISSN + published 消费者契约逐字不变。
**DoD**：`make check` 绿；**既有 by-ISSN 全测试零回归**（安全网 = 现有 crossref 消费者全部测试，含 aea 8 刊 / econsoc ECMA 走原路径）；
prefix 新模式测试（`/prefixes/10.3386/works` + `/prefixes/10.2139/works`）+ created facet 泛化测试（断言 `facets.created` 解析非空——评审 MAJOR 联动点）；
enum-key 互斥校验单测（issn+prefix 同现→CONFIG 响亮）。
**测试要点**：`parse.py:114` 硬绑 published 的泛化正确性；URL 基址两轴分派；cursor 契约/首页空判 parse 沿用零改。
**审查关注面**：**动 implemented `CrossrefAdapter` 冻结面——全 crossref 消费者受影响，回归锁定为第一关注**；扩展面窄（URL 基址 +
filter 前缀 + facet 键 + 键/字段取值，独立审查易验），风险低但影响广（opus 实现 + opus 独立实例审查）。**依赖**：无（W0 已闭合）；是 T3/T4 上游。

### T5 aea adapter（`adapter/aea`，crossref 标准 ISSN + DOI 双形态 8 刊路由，全文 deferred）——**sonnet**/**opus**·**零 T1 依赖**
**Files**：新建 `src/paper_crawler/adapters/aea/`（`adapter.py`/`parse.py`（DOI 双形态容错解析器 + code→venue 路由表）+ entry point）、
`venues/econ/{aer,aeri,aej_macro,aej_micro,aej_applied,aej_policy,jel,jep}.yaml`（**8 刊·catalog 蛇形命名**，A-2 裁决）、
`tests/fixtures/aea/`（crossref AER works 含 abstract / 单条 DOI / landing citation_* / **pubs `cf-mitigated: challenge` 403 头 5672B 截断**（BLOCKED 边界）/ unpaywall closed+gold 两样本，脱敏 [LIVE]）、
`tests/{unit,contract}/test_aea_*.py`、`tests/online/test_aea_smoke.py`（`-m online`，`MAX_REAL_REQUESTS≤5`，不触 pubs）。
**Interfaces**（aea.md §3/§4）：`capabilities = RESOLVE`(offline)；元数据 enumerate **委 crossref 标准 ISSN 路径**（不触 T1 prefix 扩展，无摘要缺口）；
**FETCH 本 Phase 不声明**（全文域 pubs CF challenge，D-006 禁对抗 → 声明恒 BLOCKED 不诚实，§4 论证）；`resolve_assets` = DOI 形态解析 +
venue OA-class 静态分类（订阅刊→`no_entitlement`、OA 刊 jep/jel→`deferred(browser-fetch)` 占位）；DOI 双形态（`aer.20230344` submission / `aer.106.6.i` vol_issue_page / `p{n}` pnp）+ code→venue 8 刊路由（未知 code→WARN 不崩）。
**DoD**：`make check` 绿；解析器 ≥90%；DOI 双形态 + 8 刊路由 + OA-class 分类 + challenge-BLOCKED 边界断言全绿；`crawler venues lint` 绿
（8 刊 `kind: journal` ISSN 齐全 + auth.level 前瞻声明不触 registry.py:234）；committed 在线冒烟 ≤5（+ 6 刊 [DOC] ISSN 核实，UPDATE_GOLDEN）。
**测试要点**：`aer.p*`/`pandp.*` **pnp 形态识别但 venue 暂缓**（A-3，不入 8 刊）；订阅刊 text/html 挡板→`no_entitlement`（非 integrity）；反直觉——JEP gold 副本落 CF 域（OA-fallback 对 aea 实质产出≈0）。
**审查关注面**：DOI 双形态容错（任一形态不抛错）；venue 命名蛇形与 catalog 一致；auth 层次澄清（venue `auth.level: institutional` 前瞻声明 vs adapter `auth_requirement=none`，§1）。**依赖**：无（crossref 标准路径，与 T1 解耦）。

### T6 econsoc adapter（`adapter/econsoc`，TE/QE OJS-OAI 自枚举 + ECMA 域名分段路由 + wiley 联动）——**opus**/**opus**·**零 T1 依赖**
**Files**：新建 `src/paper_crawler/adapters/econsoc/`（`adapter.py`/`parse.py`（**自写 oai_dc 体层薄解析器 ~50 行** + galley 链抽取 + ECMA 域名分段判定）+ entry point）、
`venues/econ/{ecma,te,qe}.yaml`（3 刊）、`tests/fixtures/econsoc/`（TE OAI ListRecords + 续页 + noRecordsMatch/badResumptionToken/badArgument/idDoesNotExist + 落地页含 galley 链 + CF 挑战页 + galley→HTML + ECMA crossref works 三域名样本 + 畸形 XML，脱敏 §7）、
`tests/{unit,contract,integration}/test_econsoc_*.py`、`tests/online/test_econsoc_smoke.py`（`-m online`，`MAX_REAL_REQUESTS≤10`）；
**同卡联动（D-028）**：`src/paper_crawler/adapters/wiley/parse.py`（`_WILEY_DOI_PREFIXES` **移除 `10.3982/`**，仅留 10.1111/10.1002）+
`wiley/adapter.py`+`wiley/__init__.py` docstring 同步 + `tests/unit/test_wiley_parse.py:21,32` 断言翻转（`is_wiley_doi("10.3982/…")` True→False，移入非 Wiley 组）。
**Interfaces**（econsoc.md §3/§4）：`capabilities = DISCOVER|ENUMERATE|RESOLVE|FETCH`（venue 非对称：TE/QE 全四位走 OJS OAI；**ECMA 只行使 RESOLVE|FETCH，enumerate 委 crossref-by-ISSN**——ECMA 无 OAI 端点）；
`_oai.py` 第三消费者注入 `record_parser`（§2-2，零改共享件）；**ECMA 运行时域名分段路由（方向 a）**：resolve 以 DOI 落地域名判归属——`econometricsociety.org`→econsoc OA 取；`doi.wiley.com`→过刊段 `no_entitlement`/skip（跨 adapter handoff **显式 defer**）；`jstor`→界外零资产；`resolve_offline=False`（galley 不可构造须 GET 落地页抽链，经限速闸）。
**DoD**：`make check` 绿；oai_dc 体层 + DOI 后缀过滤谓词（te|qe）+ ECMA 三域名分段判定 ≥90%；OAI 信封复用 `_oai.py`（econsoc 仅测 record_parser 回调接线）；**wiley 联动**：`test_wiley_parse.py` 断言翻转后全绿（`is_wiley_doi` 现零 runtime 调用=休眠，无活风险）；`crawler venues lint` 绿（3 刊 journal+ISSN 齐全）；在线冒烟 ≤10（闭 [UNRESOLVED①②] 抽样）。
**测试要点**：`noRecordsMatch`=非错误空序列；墓碑 `status="deleted"` 跳过计数；crossref link 陈旧 caveat（权威取实时落地域名非登记）；galley url 回 HTML→`gone`（arxiv `_gone_guarded_stream` 首字节嗅探复用）；`qeconomics.org` TLS 过期**绝不直连**（QE 全经 econtheory OAI + econometricsociety 落地）。
**审查关注面**：`_oai.py` 零改验证（不动 aaai_ojs）；ECMA 分段路由三态计数正确；**wiley 联动同卡不遗漏**（D-028 移除+翻转必须同卡合并，`parse.py` 与 `test` 一致）；反 AI 保守限速 + canary 监挑战。**依赖**：无（OAI 自枚举 + crossref 标准 ISSN，与 T1 解耦）。

### T3 nber adapter（`adapter/nber`，prefix 10.3386 消费 + >18 月离线全文窗 + 双域分桶）——**opus**/**opus**·**依 T1**
**Files**：新建 `src/paper_crawler/adapters/nber/`（`adapter.py`/`parse.py`（DOI→series 号 + 18 月窗谓词 + RSS `<item>` 解析）+ entry point）、
`venues/econ/nber.yaml`（`kind: preprint_channel` + `identifiers.crossref_prefix: "10.3386"` + `quirks.fulltext_open_after_months: 18`/`series_prefixes: [w, t]`）、
`tests/fixtures/nber/`（crossref prefix facet+cursor 页 / landing citation_* / RSS new.xml 截断 / openalex inverted_index / **PDF HEAD 200 头**（w30000，[LIVE]）/ **<18 月软门合成非 PDF `[SYNTH]`**，脱敏）、
`tests/{unit,contract}/test_nber_*.py`、`tests/online/test_nber_smoke.py`（`-m online`，`MAX_REAL_REQUESTS≤5`，全程不触 <18 月）。
**Interfaces**（nber.md §3/§4）：`capabilities = RESOLVE|FETCH`（enumerate 委 T1 扩展的 CrossrefAdapter，**prefix+published**）；DISCOVER 经 RSS 增量 watch 通道（可选，Phase 6 转主）；
`resolve_offline=True`——resolve 纯离线（DOI 后缀取 `w{n}`/`t{n}` + `open := (today−pub_date)≥18 月`：开放→确定性构造 `www.nber.org/system/files/working_papers/{sid}/{sid}.pdf` DIRECT 计划；<18 月→`no_entitlement(recent_gated)` 不产计划→OA-fallback 天然兜底）；
`fetch_asset` = 共享 HttpClient direct + **`%PDF` 魔数双守卫**（软门返非 PDF→改判 `no_entitlement` 非 integrity，**绝不重试凑配额/不换 IP/不走软门**）；**`back.nber.org` 独立限速桶**（`rpm=6`=1 req/10s 遵 Crawl-delay:10，**不进 domains alias**——否则被 alias 到 www 桶错享宽松预算）。
**DoD**：`make check` 绿；解析器 ≥90%；**18 月窗谓词假时钟跨边界 open/gated 断言**（红线核心）+ 软门非 PDF→no_entitlement 映射 + 双域分桶假时钟（www 1 req/5s、back 1 req/10s 独立）全绿；`t{n}` 全文路径未证实→Phase 5 全文先限 `w`（`t` 元数据照收，N-2）；在线冒烟 ≤5（PDF 仅 HEAD）。
**测试要点**：`pub_date` 缺失→保守尝试开放路径交 fetch 魔数兜底；`www2.nber.org` 别名共享 www 桶（低号 301）；JEL 缺口如实标注 notes（N-5，RePEc 挂 Phase 6）。
**审查关注面**：**<18 月软门永不绕过**（AC-5.2 调研伦理批注，obslog 审计无 <18 月 PDF host 命中）；`back.nber.org` 独立桶不被 alias（route_for alias 陷阱）；消费 T1 prefix+published 扩展契约。**依赖**：T1（prefix 枚举）。

### T4 ssrn adapter（`adapter/ssrn`，prefix 10.2139 消费 + landing-only + 站点零接触）——**opus**/**opus**·**依 T1**
**Files**：新建 `src/paper_crawler/adapters/ssrn/`（`adapter.py`/`parse.py`（DOI→abstract_id 抽取 + 主题过滤谓词）+ entry point）、
`venues/econ/ssrn.yaml`（**单一 ssrn venue**·前缀 10.2139 全库 + `quirks.topic_filter` econ/fin 近似过滤，非 per-FEN venue）、
`tests/fixtures/ssrn/`（crossref 前缀 works **混 journal-article+posted-content** / 空 created 窗 / cursor 两页 / **非-ssrn 中缀 10.2139 DOI**（护栏）/ **unpaywall SSRN landing-only** / **7 收割日回放序列**（重叠窗+created 延迟注入）/ **主题过滤输入集**，脱敏 §7）、
`tests/{unit,contract}/test_ssrn_*.py`、`tests/online/test_ssrn_smoke.py`（`-m online`，`MAX_REAL_REQUESTS≤5`，**零 SSRN 域**）。
**Interfaces**（ssrn.md §4）：`capabilities = {DISCOVER, ENUMERATE, RESOLVE(landing-only)}`（**FETCH 不点亮**——模式 B 浏览器全文 defer Phase 6，D-029 案 B）；
enumerate 委 T1 扩展的 CrossrefAdapter（**prefix 10.2139 + created**，两类型全收）；**后处理层**：DOI 正则 `^10\.2139/ssrn\.(\d+)$` 取 abstract_id → **增补 `(ssrn, abstract_id)` identifier**（DOI 锚点保留）；**护栏**：非 `ssrn.` 中缀→不增补 + 计 `skipped_non_ssrn` 观测；
`resolve_offline=True`——landing-only 零网络 URL 构造（`papers.ssrn.com/sol3/papers.cfm?abstract_id={id}`，不产 PDF asset）；PDF 交 unpaywall OA-fallback（landing-only 净效果 PDF 命中≈0，如实标注）；DISCOVER=created 年虚拟时间桶（脏未来年 2077/2103/2104 不产桶）。
**DoD**：`make check` 绿；解析器 ≥90%；abstract_id 正则矩阵 + 护栏 `skipped_non_ssrn` + 虚拟桶边界 + **7 收割日回放去重无重复无遗漏** + **确定性主题过滤单测**（固定 fixture 输入→期望输出，AC-5.1a②）全绿；**obslog 断言零 `*.ssrn.com` 请求**（AC-5.1a③）；在线冒烟 ≤5（crossref/openalex/unpaywall，均非 SSRN 域）。
**测试要点**：混 journal-article+posted-content 两类全收（不加 type 过滤）；unpaywall SSRN 响应→`_stage_oa_fallback` 不产 asset；主题过滤如实标注「近似」（非精确 FEN 子网枚举）。
**审查关注面**：**元数据主路径零 SSRN 接触**（红线核心，站点 TLS+CF 双阻断天然免疫）；消费 T1 prefix+created 契约（created facet 泛化依赖 T1 DoD）；单 venue + 主题近似过滤不冒充精确子网。**依赖**：T1（prefix 枚举）。

### M1 SSRN 覆盖率量化 census（`chore/ssrn-coverage-census`，**sonnet**/**opus 审查**，**游离·在线·依 T4**）
**Files**：`scripts/ssrn_coverage_census.py`（或 `tests/online/test_ssrn_coverage.py`，OpenAlex census 采样脚本）、`docs/testing/records/2026-MM-DD-ssrn-coverage.md`（量化结论 + 采样过程留痕）。
**Interfaces**（ssrn.md §9.1，零-SSRN-接触量化法）：以 OpenAlex source `S4210172589`（1.63M works）作 census 代理——`filter=primary_location.source.id:S4210172589` + 分页随机偏移随机采样 N≈1000 → 测「带 DOI 且 crossref 可解析」比率（openalex-相对覆盖）；**首阶估计 ≈ 1.41M/1.63M ≈ 87%**。
**DoD**：census 采样执行（N≈1000，95%±3% CI，credit 预算内熔断）→ openalex-相对 DOI 覆盖率入 records；**阈值判定**：≥90%→crossref 前缀枚举判「覆盖充分·无候补」；<90%→评估候补阶梯（(a) openalex 补枚举无-DOI works / (b) RePEc/NBER 交叉 Phase 5 同批 / (c) 有限 SSRN 浏览页 census——触 CF 须专门 BLOCKED 处置，默认不启用）。
**测试要点**：**固有天花板如实标注**——测「crossref 相对 openalex」非「相对 SSRN 真实全库」（后者需 SSRN census 无合规路径，openalex 自身覆盖上界未知）。
**审查关注面**：不采样整数 abstract_id（多数非存在投稿，混淆两成因）；不采样 SSRN 本体 census（CF 门）；credit 预算护栏。**依赖**：T4（ssrn adapter 落地后）；**游离全程·不阻塞 T7/T8**（覆盖率结论入报告，阈值不达则候补另行评估）。

### T7 AC-5 正式化 + 离线端到端验收（`feat/ac5-e2e-offline`，**sonnet 执行**/**controller 亲验**）·**依 T3+T4+T5+T6**
**Files**：`docs/testing/acceptance-criteria.md`（AC-5.x 正式化：从 ssrn.md §8 草案转录 AC-5.1a/5.1b 分层 + AC-5.2/5.3/5.4 收敛 + 全 adapter DoD 关联）、
`docs/testing/records/2026-MM-DD-ac5-acceptance.md`（离线汇总验收记录）、`tests/integration/`（端到端场景）。
**Interfaces**（分层验收 D-018 离线层）：**AC-5.1a**（ssrn 元数据 CI：7 收割日回放无重复无遗漏 + 确定性主题过滤 + 零 SSRN 接触）；**AC-5.1b**（ssrn 全文 opt-in，defer Phase 6，离线 challenge 判定可判）；
**AC-5.2**（nber >18 月：`pull nber --year <当前−2>` 离线回放 + <18 月抽样判 no_entitlement + 断言无软门请求）；**AC-5.3**（TE/QE OA 全文成功抓取，无认证）；**AC-5.4**（平台归属正确性：aea code→venue 8 刊路由 + ECMA 域名分段三分流 + wiley 10.3982 移除后不误路由）。
**DoD**：AC-5.1a/5.2/5.3/5.4 离线 PASS（mock/fixture 层）；acceptance-criteria.md AC-5.x 由草案转正（字面收窄如实公开——「FEN 子网」→「econ/fin 近似过滤」，D-029/ssrn.md §8）；验收记录成文（含适用边界 + D-018 分层标注）。**controller 亲验**。
**测试要点**：AC-5.1 原「≥95% vs OpenAlex field」废止（自比恒 100% 空判，ssrn.md §8）→ 改确定性过滤单测；AC-5.1b/全文真实取回 defer（环境+红线，用户参与 runbook）。
**审查关注面**：AC 字面差异不静默弱化（development-plan 原 DoD vs 分层新现实，如实注记）；四源 DoD 关联无遗漏。**依赖**：T3+T4+T5+T6 全合并（M1 census 结论可后补入记录）。

### T8 收尾（`docs/phase5-wrap`，**sonnet 执行 + opus 全分支终审 + controller 合并裁决**）·**依 T7（M1 可后补）**
**Files**：四详设 `{ssrn,nber,aea,econsoc}.md` → **implemented**；`docs/INDEX.md`（登记 phase5-plan + 四 adapter 状态 + AC 更新）；`progress.md`（模块状态表刷新）；
`catalog/economics-journals.md`（13 venue `supported_since: phase-5` + econsoc/ECMA 平台注记 D-028）；`docs/reports/2026-MM-DD-phase5-report.md`；tag `phase-5`。
**DoD**：AC-5.1a/5.2/5.3/5.4 离线全过；M1 census 结论入报告（阈值达→无候补 / 不达→候补改期如实记录，不阻塞 tag）；四详设转 implemented；INDEX/progress/catalog 同步（D-027/D-028/D-029 已于 2026-07-24 落 decision-log，此处只需 INDEX 摘要与状态同步）；AC-0 系统性扫描（git 全历史无凭证/cookie 形态 AC-0.3、日志脱敏 AC-0.4、限速/robots AC-0.5）全过；阶段报告成稿；`make check` 全绿状态打 tag。**opus 全分支终审 + controller 合并裁决放行**。**依赖**：T7（T7b/M1 可后补，沿 Phase 4 T8 口径）。

## §5 波次并行图与冲突面预算

```
W0(已闭合): 四详设(ssrn/nber/aea/econsoc)双评审 approved + D-027/D-028/D-029 正式化 → 硬门禁开，全卡可开工
W1(三卡并行): T1 crossref prefix 扩展(opus) ‖ T5 aea(sonnet) ‖ T6 econsoc+wiley(opus)   [T5/T6 无卡间依赖；T1 是 T3/T4 上游]
W2(T1 合并后双发): T3 nber(opus) ‖ T4 ssrn(opus)                                          [均依 T1 的 prefix+date-field 扩展]
W3: T7 AC-5 正式化+离线端到端(sonnet→controller 亲验)                                     [依 T3+T4+T5+T6 全合并]
W4: T8 收尾(sonnet+opus 全分支终审→controller 裁决)                                       [依 T7；M1 可后补]
游离全程: M1 SSRN 覆盖率 census(sonnet/opus 审查，依 T4·在线，openalex credit 预算内)
峰值并行 3 线(W1): T1 + T5 + T6
每任务: implementer(worktree) → 双裁决审查(Spec+质量, 限量真实交叉验证 ≤5 req) → fix 回派 → controller 合并亲跑 make check
```

**冲突面预算（worktree 波次并行的写文件重叠分析）**：
| 文件 | 写方任务 | 冲突管理 |
|---|---|---|
| `crossref/adapter.py` + `crossref/parse.py` | **T1 独占** | 唯一动 implemented 冻结件；T3/T4 只读消费其 prefix 模式（波次序化：T1 先合、T3/T4 rebase 后消费） |
| `wiley/parse.py` + `test_wiley_parse.py` + wiley docstring | **T6 独占**（D-028 联动） | 单卡，`_WILEY_DOI_PREFIXES` 移除 + 断言翻转同卡；`is_wiley_doi` 零 runtime 调用=休眠，无活风险 |
| `_oai.py` | **只读**（T6 注入 record_parser 回调） | econsoc 第三消费者，零改共享件（不动 implemented aaai_ojs，test_oai_envelope 守门充分） |
| `pyproject.toml` `[project.entry-points]` | **T3+T4+T5+T6 四方写** | **已知 union 点**——controller 合并统一 union（Phase 3/4 五源/三平台先例），各卡只加自己一行、不动他行 |
| `venues/econ/*.yaml` | T3(`nber`) / T4(`ssrn`) / T5(`aer,aeri,aej_×4,jel,jep` 8 刊) / T6(`ecma,te,qe`) | 各卡独占各自 YAML 文件名，disjoint 无重叠 |
| `adapters/{ssrn,nber,aea,econsoc}/` | T3/T4/T5/T6 各独占包目录 | disjoint，四 adapter 波真并行安全（沿 Phase 2/3 逐 adapter 独立分支先例） |
| `acceptance-criteria.md` | **T7 独占**（AC-5.x 正式化） | 单卡 |
| `INDEX/progress/catalog/decision-log` | **T8 独占**（收尾同步） | 单卡（D-027/28/29 已落，仅状态同步） |

- **关键序化**：`crossref/*`（T1）→ nber/ssrn（T3/T4 消费 prefix+date-field 扩展）跨波依赖——**T1 先合、T3/T4 rebase 后消费扩展契约**；
  T5/T6 与 T1 全程解耦（各走 crossref 标准 ISSN / OJS OAI 自枚举），W1 三卡真并行安全。**四 adapter 各独占包目录 + fixture 目录（disjoint），仅共享只读 T1 扩展 + entry-points union 点**。

## §6 模型分配建议

**分配原则**：opus = 判断力密集处（T1 冻结件扩展、nber 软门红线、ssrn 站点零接触红线、econsoc 分段路由+wiley 联动、全分支终审）；
sonnet = 规格已写死到字段级的执行件（aea DOI 解析/路由已详设列表化、census 脚本、AC-5 转录、收尾）。**实现/审查独立实例**（实现审查分离）。

| 件 | 实现档 | 审查档 |
|---|---|---|
| T1 CrossrefAdapter 参数化扩展（触 implemented 冻结件） | **opus** | **opus**（全 crossref 消费者回归锁定） |
| T5 aea adapter（DOI 双形态 + 8 刊路由，全文 deferred） | **sonnet** | **opus** |
| T6 econsoc adapter（OJS-OAI + ECMA 分段 + wiley 联动 D-028） | **opus** | **opus** |
| T3 nber adapter（18 月软门红线 + 双域分桶） | **opus** | **opus** |
| T4 ssrn adapter（站点零接触红线 + landing-only） | **opus** | **opus** |
| M1 SSRN 覆盖率 census（游离在线） | sonnet | opus（阈值 + 候补阶梯判定） |
| T7 AC-5 正式化 + 离线端到端 | sonnet | controller 亲验 |
| T8 收尾 | sonnet + controller | opus 全分支终审 |

## §7 AC 映射与风险

| AC | 载体任务 | 验收形态 |
|---|---|---|
| AC-5.1a SSRN 元数据（CI 可判） | T4（+T1）+T7 | 7 收割日回放无重复无遗漏 + 确定性主题过滤单测 + obslog 零 SSRN 接触 |
| AC-5.1b SSRN 全文（opt-in） | — | **defer Phase 6**（D-029 案 B；离线 challenge 判定可判，真实取回用户 runbook） |
| AC-5.2 NBER >18 月开放 | T3+T7 | prefix enumerate + 离线 18 月窗 resolve + fetch 魔数（离线回放 + 冒烟 1 篇）；<18 月判 no_entitlement 断言无软门请求 |
| AC-5.3 TE/QE 开放刊 | T6+T7 | OJS-OAI 枚举 + galley OA 全文抓取（无认证；离线 fixture + 冒烟） |
| AC-5.4 平台归属正确性 | T5+T6+T7 | aea code→venue 8 刊路由 + ECMA 域名分段三分流 + wiley 10.3982 移除后不误路由（TE/QE 不误归 wiley） |
| （aea 元数据/DOI 路由，无专属 AC-5.x） | T5 | 通用 adapter DoD + AC-5.4 类比（aea.md §9） |

风险：①**AC-5.1 字面收窄**（「FEN 子网」→「econ/fin 近似过滤」，D-029）——如实公开非静默弱化，精确子网枚举无合规路径（ssrn.md §3）；
②**SSRN 站点 CF/TLS 双阻断**——元数据层零 SSRN 接触故天然免疫（模式 B 全文 defer Phase 6）；③**NBER 18 月边界模糊**（分批开放）——
离线日期预判 + fetch 魔数 no_entitlement 双守卫诚实处置，不猜配额；④**aea 全文域 pubs CF 判罚**——FETCH 不声明、全文 deferred（browser-fetch 通道 Phase 6 横切件）；
⑤**econsoc 反 AI 收紧**（具名封 ClaudeBot，当前对 PaperCrawler UA 无挑战）——保守限速 + canary 监挑战、连续 challenge→catalog 降级仅元数据（不硬对抗，AC-0.2）；
⑥**T1 触 implemented 冻结件**——既有 by-ISSN 全测试为安全网，opus 实现 + opus 独立审查、prefix/created 新模式与既有路径回归双锁定；
⑦**[UNRESOLVED] 实现期闭合**（不阻塞离线 DoD）：ECMA 全刊 OA（econsoc.md §8①，冒烟 HEAD 判）、Wiley→自营切换日（②，方向 a 不依赖）、TE 656 vs crossref 735 差额（③，DOI 后缀过滤自收敛）、SSRN DOI 覆盖率（M1 census）、`t{n}` 全文路径（nber N-2，先限 `w`）、JEL 缺口（nber N-5，RePEc 挂 Phase 6）。

## §8 不建卡项（显式出列，范围锁定 R5）

- **repec**（D-027 出列）：R0c 实测=分布式书目聚合器、非全文源；主枚举/全文与 crossref/openalex 高度重叠（增量≈0）→ **Phase 5 不建独立 pull adapter**，
  降级为可选 enrich 通道候选（独家增值 = JEL + wp↔published 版本关联），**挂 Phase 6 订阅 DSL 富化评估**。
- **browser-fetch 通道**（D-029 案 B defer Phase 6）：ssrn 模式 B 全文 / aea pubs CF 全文 / wiley deferred 页面兜底**三处共需**——
  本机 CF 前置域 TLS 阻断致在线验收不可行 + 横切件宜统一设计 → **defer Phase 6**（[ssrn.md §11](../design/adapters/ssrn.md) 保留为设计种子）。
- **aea 全文 / 机构认证**（deferred）：全文域 pubs CF challenge，D-006 CookieSession 机构订阅**留将来**（browser-fetch 通道 + auth 落地时立 AC，类比 AC-4.1/4.3）。
- **P4-T7b elsevier 真实 key 冒烟**（等外部 key，与本 Phase 无耦合）：Phase 4 游离项，key 到位后补录，不入本 Phase。
