---
title: Adapter 设计 · AEA（AER + AEJ 四系 + AER:Insights + JEL/JEP，实现级）
status: approved
owner: D2
updated: 2026-07-24
---

# Adapter · `aea`(实现级详设)

> **controller 预裁决**（Phase 5 W0）：元数据 **100% Crossref**（前缀 `10.1257`，**含摘要**，站点零元数据爬取——elsevier_sd 先例）；
> DOI 双形态容错解析；**全文能力本 Phase 不落地**——全文域 `pubs.aeaweb.org` 整体 Cloudflare challenge（连 gold OA 的 JEP 亦
> stateless 不可达），fetch 走 OA-fallback（unpaywall 对 `10.1257` 覆盖低、如实标注）+ **全文域直连标 BLOCKED/deferred，待
> browser-fetch 通道裁决**（D1 并行评估 + controller 终裁，本文只交叉引用、不重复评估）；auth 预判 D-006 CookieSession 机构订阅
> **留将来**（本 Phase 不实现 aea 认证）。
> 勘察：[research/site-survey/aea.md](../../research/site-survey/aea.md)（[LIVE] 2026-07-24，approved，18 请求预算内）。
> 复用面：[crossref/adapter.py](../../../src/paper_crawler/adapters/crossref/adapter.py)（enumerate 主干，**标准 ISSN 路径**）、
> [unpaywall/adapter.py](../../../src/paper_crawler/adapters/unpaywall/adapter.py)（OA-fallback）、[elsevier-sd.md](elsevier-sd.md)/[wiley.md](wiley.md)（模板 + challenge/BLOCKED 边界写法）。
> 接缝：[auth-framework.md §8.1/§8.4/§8.5](../auth-framework.md)（no_entitlement→OA-fallback、BLOCKED(challenge)+冷却、不计 failures）、
> [design/05 §4](../05-pipeline.md)（错误分类学）、[decision-log D-006/D-007](../../plan/decision-log.md)（CookieSession/跨源合并）。
> 红线（AGENTS §6.3 / AC-0.2）：`pubs.aeaweb.org` 遇 `cf-mitigated: challenge` **即停手、不对抗、不重试**（D-006）；
> AEA robots 点名封 GPTBot/Amazonbot → 本系统诚实 UA、非训练用途、全文从严（quirks 记 AI-bot 敏感）。

## 1. 定位

- **family**：`open_access`（元数据面）+ `auth_gated`（全文面，**本 Phase 不落地**）——混合定位，本 Phase 仅交付元数据/resolve 面。
- **capabilities**：`RESOLVE`（零网络，offline）——**FETCH 本 Phase 不声明**（论证见 §4）；**enumerate 走 crossref**（D-005，标准 ISSN 路径）。
- **domains**：`("www.aeaweb.org",)`——发现/landing host（Apache，开放）。全文 host `pubs.aeaweb.org`（Cloudflare）**不进 domains**
  （本 Phase 无 stateless 全文请求；browser-fetch 通道落地时另议其桶/域声明）。
- **AuthProvider**：**无**（本 Phase）。订阅刊 auth 预判 = D-006 `CookieSession`（Playwright 机构首登→storage_state 复用）**留将来**，
  venue YAML 先声明 `auth.level` 备用，不接 AuthProvider。
  **⚠ 层次澄清（venue 前瞻声明 vs adapter 本期实态）**：订阅刊 venue YAML 的 `auth.level: institutional` 是**刊物真实访问级的前瞻声明**
  （备 D-006 落地）；本期 **adapter `auth_requirement = none`**（RESOLVE-only、无认证 FETCH）。二者不矛盾、**不触 lint**——`registry.py:234`
  仅当 venue `auth.level` **低于** fulltext adapter 要求时报错（`none` adapter 零门槛、`institutional` venue 高于零门槛天然通过）；
  D-006 落地时把 adapter `auth_requirement` 升 institutional 与 venue 对齐。
- **服务 venue**：**8 刊**（§7 命名清单）——`aer`/`aeri`/`aej_macro`/`aej_micro`/`aej_applied`/`aej_policy`/`jel`/`jep`；P&P 见 §7 注。
- **`resolve_offline = True`**：resolve = DOI 形态解析 + venue OA-class 静态分类（零网络，D-022 免限速闸）。

## 2. 站点勘察摘要（全 [LIVE] 2026-07-24）

- **元数据主干 = Crossref `10.1257`，含摘要（优于 NBER）**：前缀总 **50,692** DOI；按刊 ISSN 枚举——AER(`0002-8282`)=5,643、
  JEP(`0895-3309`)=2,330，抽查近文 `has_abstract=True`（len ~700–850）。单条含 `title/abstract/author(given/family+affiliation)/
  volume/issue/page/published/container`。landing 另有全套 `citation_*` meta。→ **元数据 100% Crossref，站点零爬取**（D-005 标准态）。
- **DOI 双形态**：近年 `aer.{8 位投稿号}`（`aer.20230344`）；早年 `aer.{卷}.{期}.{页}`（`aer.106.6.i`）；P&P `aer.p20151048`/`pandp.116.742`；
  子刊前缀 `aeri.`/`mac.`/`app.`/`mic.`/`pol.`/`jel.`/`jep.`。→ **解析器须容两种 aer 形态 + 子刊 code→venue 路由**（§3.2）。
- **全文两层双主机**：`www.aeaweb.org`（Apache，发现层，开放）；`pubs.aeaweb.org`（Atypon/Literatum + **Cloudflare**，全文层）。
  - AER 近文（订阅）：`HEAD www.aeaweb.org/articles/pdf/doi/{DOI}` → `200` 但 `Content-Type: text/html`（订阅挡板，非 PDF）+ 下发 cookie。
  - JEP（免费）：同 URL → `302` → `pubs.aeaweb.org/doi/pdfplus/{DOI}`。
  - **`pubs.aeaweb.org` = CF BLOCKED 边界**：`HEAD /doi/pdfplus/{JEP DOI}` → `HTTP/2 403 + cf-mitigated: challenge + 5672B 挑战体`
    （**站点级判罚**，非环境障碍——同域 robots 先前 200/TLS OK）。**连 OA 的 JEP 全文也住此 CF 域** → stateless httpx 拿不到任何 AEA 全文。
- **Unpaywall 对 `10.1257` green 覆盖低**：AER 抽查 3/3 `closed`（0 OA location）；JEP=`gold`（但 `best_oa host_type=publisher`
  = pubs.aeaweb.org，**仍落 CF 域**，见 §3.4 反直觉发现）。结构因：NBER/SSRN 先行版持**独立 DOI**，未登记为 `10.1257` 的 OA 副本。
- **反爬**：www=Apache 无挑战（≥2s）；pubs=Cloudflare（robots `Crawl-delay:1`，但 bot 管理判罚，非 robots）。robots 仅点名封 GPTBot/Amazonbot。

## 3. 各阶段实现方案（字段级）

### 3.1 enumerate = Crossref **标准 ISSN 路径**（无需 NBER 式 prefix 扩展）

- 8 刊各持 ISSN（§7），走现 `CrossrefAdapter` 未改动路径：`discover_timeline`=`/journals/{issn}/works?facet=published:*`；
  `enumerate_issue`=日期窗 + cursor 深翻（crossref adapter.py 逐字复用）。**与 NBER 关键差异**：AEA 是标准期刊（有 ISSN），
  **不触** NBER 的 prefix 模式扩展（nber.md §3.1）；亦**不缺摘要**（Crossref 存交），故 OpenAlex 仅作 topics/引用**可选**补充、非必需。
- 全库交叉核对可选用前缀 `/prefixes/10.1257/works`（total=50,692）对账 8 刊 ISSN 计数之和（观测用，非枚举主路径）。

### 3.2 DOI 双形态容错解析器 + code→venue 路由（**controller 预裁决 #5 核心**）

`10.1257/{code}.{suffix}`，**容错解析**（两种 aer 形态 + P&P，任一形态不得抛错）：

- **code→venue 路由表**（DOI 子前缀 code ≠ venue id）：

  | DOI code | venue id | 刊 |
  |---|---|---|
  | `aer` | `aer` | American Economic Review |
  | `aer.p*` / `pandp.*` | （暂缓，§7 A-3） | AEA Papers & Proceedings — pnp 形态识别、venue 本 Phase 不落 |
  | `aeri` | `aeri` | AER: Insights |
  | `mac` | `aej_macro` | AEJ: Macroeconomics |
  | `app` | `aej_applied` | AEJ: Applied Economics |
  | `mic` | `aej_micro` | AEJ: Microeconomics |
  | `pol` | `aej_policy` | AEJ: Economic Policy |
  | `jel` | `jel` | JEL |
  | `jep` | `jep` | JEP |

- **suffix 形态**（仅供展示/元数据，**不作路由键**）：① 8 位投稿号 `20230344`（含隐式年）；② `卷.期.页` `106.6.i`（页可为罗马数字/front matter）；
  ③ P&P `p{8 位}`。解析器产 `(venue_id, doi_form∈{submission|vol_issue_page|pnp}, raw)`；**未知 code → 不路由 + WARN 观测**（非崩溃，防新子刊上线）。
- 复用/落点：置 `adapters/aea/parse.py` 纯函数（零网络，单测密集）；routing 供 registry 把 8 venue 的 `10.1257` 各刊 DOI 归位。

### 3.3 resolve_assets(venue, paper, session)（RESOLVE，零网络）

输入 paper 的 `doi`。**纯离线**（DOI 形态解析 + venue OA-class 静态分类，无网络）：

- **订阅刊**（`aer`/`aeri`/`aej_*`）→ **不产平台 AssetPlan、标 `no_entitlement`**（无机构订阅 + 全文域 CF 挡）→ pipeline 转 OA-fallback
  （unpaywall；覆盖低，多数无 OA → 跨源 WP 兜底，见 §3.4）。auth 预判 D-006 CookieSession **留将来**，本 Phase resolve 不产订阅计划。
- **OA 刊**（`jep`/`jel`）→ 全文经 `pubs.aeaweb.org/doi/pdfplus/{DOI}`，但该域 CF challenge（§3.4）→ **同样不产可 stateless-fetch 的计划**，
  标 **deferred(browser-fetch)**（记规范全文 URL 作 BLOCKED 观测，供 browser 通道落地时消费）。→ 亦转 OA-fallback（unpaywall gold，但见 §3.4 反直觉）。（2026-07-24 审查 MINOR① controller 裁定：jep/jel 返回空计划不派生 OA-fallback——§3.4 已证 OA-fallback 对 10.1257 产出≈0，此路径无实际损失，本句按现实校准废止。）
- **deferred 全文 URL 记录**：resolve 可产一条 `AssetPlan(kind=PDF, url=pubs.../doi/pdfplus/{DOI}, url_strategy=BROWSER,
  auth_needed=INSTITUTIONAL|NONE, state=deferred)` 作**文档化占位**（本 Phase 不 fetch）——★接缝 A-1：`url_strategy=BROWSER`/`state=deferred`
  是否入冻结件由 browser-fetch 通道详设（D1）统一定，本文只交叉引用、**不新增冻结件**。

### 3.4 全文能力矩阵 + FETCH deferred/BLOCKED（含反直觉发现）

| venue 类 | stateless 路径实测 | 本 Phase 结论 |
|---|---|---|
| AER/AEJ/AER:Insights（订阅） | www→挡板 HTML；pubs→CF challenge；unpaywall 3/3 closed | `no_entitlement`→OA-fallback（低命中）→**跨源 WP**（NBER `10.3386`/SSRN，D-007 关系互联，**非 unpaywall**）；平台 fetch **deferred(browser + D-006 CookieSession)** |
| JEP/JEL（gold/免费） | pubs `/doi/pdfplus/` → CF challenge（**即便 OA**） | 全文 **deferred(browser)**；unpaywall 报 gold 但 `best_oa=publisher`=pubs（CF 域）→ **OA-fallback 亦不可 stateless 取**（反直觉，下） |

- **反直觉发现（强化"全文 deferred"）**：JEP 虽 `oa_status=gold`，unpaywall `best_oa host_type=publisher` 指回 **pubs.aeaweb.org**
  （CF-blocked）→ 即"gold OA"的副本也在 CF 域后 → **stateless OA-fallback 对 AEA 实质产出 ≈ 0**（订阅刊 closed + OA 刊落 CF 域）。
  真正可取的全文路径仅二：① browser-fetch 通道（Playwright context 破 CF challenge + 携机构 cookie，D-006/wiley 先例）；② 跨源 WP 版（另 DOI/venue）。
- **FETCH 本 Phase 不声明**（§4 论证）：一切 stateless 全文路径均 challenge/挡板 阻断，D-006 禁对抗 challenge——声明恒 BLOCKED 的 FETCH 不诚实。
  平台 FETCH 待 **browser-fetch 通道 D1 详设 + controller 终裁**（本文交叉引用，不重复评估）。
- **BLOCKED 边界写法**（沿 wiley §5）：pubs `cf-mitigated: challenge` → `Challenged` → **BLOCKED(challenge) + 冷却 24h**（auth-framework §8.4）。

### 3.5 healthcheck(session)

- 元数据面健康由 crossref adapter 自有 canary 覆盖（不重复）。AEA adapter 本 Phase 无网络 FETCH → healthcheck 结构性：
  `raise NotImplementedError("aea 全文能力本 Phase 未落地（browser-fetch 通道待裁）")` → canary **SKIP**（复用 elsevier/wiley
  NotImplementedError→SKIP 先例，auth-framework §7）。browser-fetch 通道落地后补全文健康探针。

## 4. capabilities 集合论证（controller 预裁决 #6：RESOLVE 有 / FETCH 无 的完整论据）

- **ENUMERATE：不声明**——D-005 元数据主干走 crossref（标准 ISSN），与 elsevier_sd/wiley 同口径；AEA adapter 不承担枚举。
- **RESOLVE：声明（offline）**——理由：① 承载 DOI 双形态解析 + 8-venue 路由（§3.2，本 Phase 可测硬交付）；② 是接入 OA-fallback 的
  接缝（订阅刊 emit `no_entitlement`→§8.1）；③ 记录 deferred 全文 URL 供 browser 通道消费；④ 零网络（resolve_offline=True），无限速/凭证风险。
  **RESOLVE-only（无 FETCH）有先例**：unpaywall adapter 即 RESOLVE-only（"只定位不下载"）。
- **FETCH：不声明（deferred）**——理由：① 订阅刊无机构认证（本 Phase 不实现 aea auth，controller #7）；② 全文域 `pubs.aeaweb.org`
  对 stateless 客户端一律 `cf-mitigated: challenge`（**连 gold OA JEP 亦然**，§3.4），D-006 禁对抗；③ 唯一可行平台 fetch = browser-fetch
  通道（Playwright storage_state），**其纳入与否 = D1 详设 + controller 终裁**，本文交叉引用不重复评估。→ 声明恒 BLOCKED 的 FETCH 属不诚实
  能力，故本 Phase **不声明**，全文经 pipeline OA-fallback（通用机制，非 AEA 能力）尝试 + deferred 占位。
- **一句话结论**：`capabilities = RESOLVE`（offline）；enumerate=crossref；FETCH deferred 至 browser-fetch 通道裁决。

## 5. 限速与预算表（本 Phase 仅发现层）

| 域 | 默认策略 | 说明 | 出处 |
|---|---|---|---|
| `www.aeaweb.org`（`domains[0]`，发现/landing） | `RatePolicy(rpm=30, burst=1)`（=1 req/2s） | Apache 无挑战；本 Phase resolve 零网络，此桶仅备 landing 补字段（如需） | robots 无 `*` 限速 [LIVE 07-24] |
| `api.crossref.org`（enumerate） | crossref adapter 自有（rpm=300, burst=1） | 8 刊 ISSN 枚举 | crossref adapter.py |
| `pubs.aeaweb.org`（全文 CF 域） | **本 Phase 不注册**（无 stateless 请求） | browser-fetch 通道落地时定桶（robots `Crawl-delay:1`，但 CF 判罚，须保守 + challenge 即停） | [LIVE 07-24] |

- `default_rate = RatePolicy(requests_per_minute=30, burst=1, source_note="www.aeaweb.org 发现层 Apache 无挑战，保守 1 req/2s；
  全文域 pubs.aeaweb.org(Cloudflare) 本 Phase 不 stateless 触达 [LIVE 2026-07-24]")`。
- 日配额：本 Phase 无 FETCH → 不占 `auth_daily_cap`；browser-fetch 落地后按 "fetch 尝试篇次" 纳入（auth-framework §8.3）。

## 6. 失败模式映射（对齐 HttpClient 冻结错误类 + `status_code`，design/05 §4）

| 现象 | status_code | error_class | 说明 |
|---|---|---|---|
| 订阅刊无认证 | — | `no_entitlement` | resolve 离线判定；**不计 failures**（§8.5）→ OA-fallback（§8.1）；auth D-006 留将来 |
| `pubs.aeaweb.org` CF 挑战（browser 通道落地后才会遇） | 403 | `challenge` | `cf-mitigated: challenge` → `Challenged` → BLOCKED(challenge)+冷却 24h（§8.4，沿 wiley） |
| www 全文 URL 返 text/html 挡板 | 200 | `no_entitlement` | 订阅挡板（非 PDF）；归门控（非 integrity）→ OA-fallback |
| DOI 未知 code（新子刊） | — | （不路由 + WARN） | 解析器容错，不崩溃（§3.2） |
| OA-fallback（unpaywall）低命中 | — | — | 归 unpaywall 既有映射；AEA 结构性低覆盖如实呈现，不误判失败 |

## 7. venue 建模 — **8 venue 命名清单**（⚠ 与 controller 简报有命名冲突，已按 catalog 裁决）

**命名冲突裁决**：controller 简报列 `aejapp/aejmac/aejmic/aejpol`（紧凑）；但**权威源 [catalog/economics-journals.md](../../catalog/economics-journals.md)
§AEA 系列**用 `aej_macro/aej_micro/aej_applied/aej_policy`（蛇形）。controller 令"venue id 命名**沿 catalog 与既有 YAML 惯例核实后定**"
→ **采 catalog 蛇形**（既有 YAML `id` 规则=小写蛇形，蛇形合规）。**开放题 A-2：请 controller 确认此裁决**（若坚持紧凑写法需同步改 catalog）。

| venue id | 刊 | ISSN（catalog） | tier | auth.level（YAML 备用） | metadata | fulltext |
|---|---|---|---|---|---|---|
| `aer` | American Economic Review | 0002-8282 | T1 | institutional | crossref | aea（deferred） |
| `aeri` | AER: Insights | 2640-205X | T2 | institutional | crossref | aea（deferred） |
| `aej_macro` | AEJ: Macroeconomics | 1945-7707 | T1 | institutional | crossref | aea（deferred） |
| `aej_micro` | AEJ: Microeconomics | 1945-7669 | T1 | institutional | crossref | aea（deferred） |
| `aej_applied` | AEJ: Applied Economics | 1945-7782 | T1 | institutional | crossref | aea（deferred） |
| `aej_policy` | AEJ: Economic Policy | 1945-7731 | T1 | institutional | crossref | aea（deferred） |
| `jel` | Journal of Economic Literature | 0022-0515 | T2 | none（免费） | crossref | aea（deferred/OA） |
| `jep` | Journal of Economic Perspectives | 0895-3309 | T2 | none（gold OA） | crossref | aea（deferred/OA） |

- **⚠ ISSN 出处分级**：上表 8 ISSN 中唯 **AER(`0002-8282`)/JEP(`0895-3309`) 经勘察 [LIVE 2026-07-24] 实证**（crossref 枚举实跑）；
  其余 6（aeri/aej_macro/aej_micro/aej_applied/aej_policy/jel）**仅 catalog [DOC] 来源**——**实现期在线冒烟负逐一核实义务**（UPDATE_GOLDEN 纪律，沿 D-019 锚点先例）。
- 字段设计（YAML 属实现期交付，本文只给字段）：`kind: journal`；`field: [econ]`；`identifiers.issn: [<上表>]`；`metadata_source: crossref`；
  `fulltext_source: aea`；`auth.level`（上表，`provider_hint: aea` 备用）；`quirks: {ai_bot_sensitive: true, doi_forms: [submission, vol_issue_page, pnp]}`；`status: active`。
- **P&P 注（A-3 裁决）**：AEA Papers & Proceedings（`aer.p*`/`pandp.*` 形态）**独立 venue 暂缓**——不入本 Phase 8 刊清单（年刊特刊、
  勘察未覆盖、非主线）；DOI 解析器仍容 pnp 形态（不崩），其 venue 归属留将来。

## 8. Fixtures 与测试（出处分级）

- **T-aea 单元**（零网络，DOI 解析为重点）：① **DOI 双形态解析**（`aer.20230344`=submission / `aer.106.6.i`=vol_issue_page /
  `aer.p20151048`=pnp / `mac.20180329`=子刊；未知 code→WARN 不崩）；② code→venue 路由全 8 刊断言；③ resolve OA-class 分类
  （订阅→no_entitlement 不产计划 / OA→deferred 占位）；④ 软门 text/html 挡板→no_entitlement（非 integrity）。
- **T-aea fixture**（脱敏，出处标级）：① Crossref `/journals/{issn}/works` 页（AER，[LIVE] 含 abstract，脱敏截断）；② 单条
  `10.1257/aer.20230344`（[LIVE] 含 abstract 724 字）；③ landing `citation_*` meta（[LIVE]）；④ **pubs `cf-mitigated: challenge`
  403 挑战响应头**（[LIVE]，5672B 体截断——BLOCKED 边界 fixture，沿 wiley 挑战 fixture 先例）；⑤ unpaywall closed（AER）+ gold（JEP）两样本（[LIVE]）。
- **T-aea 在线冒烟**（`tests/online/test_aea_smoke.py`，`-m online`，`MAX_REAL_REQUESTS≤5`）：crossref AER ISSN facet 1 + 单条 DOI 1 +
  landing 1 ≤3；**不触 pubs.aeaweb.org**（CF challenge，红线不对抗）。全文冒烟随 browser-fetch 通道落地补。
- **预算层次**：committed 冒烟 ≤5（本行）≠ browser-fetch 全文 runbook（未来，通道裁决后）。

## 9. 验收关联（无专属 AC-5.x，按 acceptance-criteria 先例给建议）

- AC-5.x 无 AEA 专条（AC-5.2=NBER、5.3=TE/QE、5.1=SSRN、5.4=路由）。建议关联：
  - **元数据/enumerate → 通用 adapter DoD + AC-3.5 类比**（crossref 零爬取枚举，含摘要）：离线 fixture 回放 + 单测 PASS。
  - **DOI 双形态 + 8-venue 路由正确性 → AC-5.4 类比**（"平台归属正确性"——AEA 的 code→venue 路由 + P&P 归位是同构的路由正确性判据）。
  - **全文 → 本 Phase 无 AC**（deferred）：未来 browser-fetch 通道 + D-006 机构认证落地时立 AC（类比 AC-4.1 单篇 / AC-4.3 no_entitlement 降级）。
- **离线 DoD**：resolve/DOI 解析/路由/OA-class 分类逻辑单测 + fixture 回放 + challenge-BLOCKED 边界断言全 PASS 即本 Phase DoD PASS
  （沿 elsevier/wiley "离线层先行，在线/runbook 分层" 口径，D-018）。

## 10. 风险与开放问题

- **A-2 venue 命名冲突（controller 简报 vs catalog）**：已按 catalog 蛇形裁决（§7），**待 controller 确认**。
- **全文 deferred 是本 adapter 最大不确定面**：browser-fetch 通道能否破 pubs CF challenge = D1 详设 + controller 终裁（本文不评估）。
  勘察 §7 另注：本机对部分 CF 域有 **TLS-reset 环境障碍**（R0a/SSRN 实测），但本次 AEA pubs 的 403 系**站点 CF 判罚**（robots 200/TLS OK 已区分）；
  **开放题 A-4**：实现期须在干净网络 + 浏览器上下文复测 pubs 真实可达性（区分"站点 CF 判罚"与"环境 TLS 障碍"）。
- **OA-fallback 对 AEA 实质产出 ≈ 0**（§3.4 反直觉）：订阅刊 unpaywall closed + OA 刊 gold 副本落 CF 域——实现期**不应把 unpaywall 当 AEA 全文主路**；
  订阅版全文的现实兜底是跨源 WP（NBER/SSRN，另 DOI，D-007 合并），非 unpaywall。
- **A-3 pandp venue 归属**：**裁决=独立 venue 暂缓**（不入本 Phase 8 刊清单；年刊特刊、勘察未覆盖、非主线）——解析器容 pnp 形态、venue 留将来（§7）。
- **勘察事实无内部冲突**：aea.md [LIVE 2026-07-24] 与 catalog 一致（除命名写法 A-2）；env-TLS-障碍 vs 站点-CF-判罚 勘察已严格甄别、不构成事实冲突。

## 11. 修订记录

| # | 日期 | 修订 | 依据 |
|---|---|---|---|
| 1 | 2026-07-24 | 初稿（实现级，status draft）：crossref 标准 ISSN 枚举（含摘要，无需 prefix 扩展）+ DOI 双形态容错解析器 + code→venue 8 刊路由 + capabilities 论证（RESOLVE offline 有 / FETCH deferred 无）+ 全文 deferred/BLOCKED（pubs CF challenge，连 JEP OA 亦然的反直觉发现）+ 跨源 WP 兜底（D-007，非 unpaywall）+ browser-fetch 通道交叉引用（不重评）+ 8 venue 命名冲突按 catalog 裁决 + challenge-BLOCKED 边界（沿 wiley）+ 测试/fixture + 验收关联建议 | [research/site-survey/aea.md](../../research/site-survey/aea.md) [LIVE 2026-07-24] + catalog/economics-journals.md + crossref/unpaywall adapter + wiley.md/elsevier-sd.md 模板 + D-006/D-007 |
| 2 | 2026-07-24 | **W0 双评审修订轮**（Approve-with-fixes）：③ §7 补注 **ISSN 出处分级**（唯 AER/JEP [LIVE] 实证、余 6 仅 catalog [DOC]，实现期在线冒烟负核实）+ **A-3 裁决** pandp 独立 venue 暂缓（不入 8 刊清单，同步 §3.2 路由表/§10 风险条）；④ §1 **auth 层次澄清**（venue `auth.level: institutional` 前瞻声明 vs adapter 本期 `auth_requirement=none`；不触 registry.py:234 lint——仅 venue 低于 adapter 要求时报错） | controller W0 回派 + registry.py:234 实证 |
| 3 | 2026-07-24 | W0 双评审（A/B 独立实例，2026-07-24）Approve-with-fixes → 修订轮闭合 → controller approved | controller W0 收口 |

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
