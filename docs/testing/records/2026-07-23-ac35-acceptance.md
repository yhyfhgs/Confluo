---
title: 期刊聚合层验收执行记录（AC-3.5 · 五刊零爬取枚举全史）
status: draft
owner: fable5
updated: 2026-07-23
---

# 期刊聚合层验收执行记录（AC-3.5）

> 本记录由 T7 implementer 起草（授权真实网络实跑），**最终签署由 controller（主 agent）做**。
> 口径依 acceptance-criteria AC-3.5 + aggregators.md §5.1/§8 + D-018（时间维分层）/D-019（外源锚点）。

- 起草日期：2026-07-23 · 起草者：T7 implementer（opus 档）
- 分支：`feat/journal-venues`（起点 `8fc8036` = main，含 T1 合并引擎 / T3 crossref / T4 dblp / T5 unpaywall 全合并）
- 环境：macOS (Darwin 25.5.0) · Python 3.13.12（uv .venv）· uv
- 在线执行：**授权真实网络任务**——UA 携真实 `mailto:yhyfhgs@gmail.com`（D-014，Crossref polite pool 硬要求）、crossref 保守 5 req/s、dblp ≥4s/req（robots `Crawl-delay:4`）、unpaywall `?email=` 单 DOI
  - **email 注入方式**：经**隔离运行时 home**（scratchpad，仓库外）的 `config.toml [identity].email` 注入——用户真实 `~/.paper-crawler/config.toml` **无 `[identity].email`**（仅 `[auth.openreview]`），若用默认 home 直跑会掉出 polite pool（见 §Concerns C5）。email 不硬编码进任何提交文件（红线）。

## AC-3.5 判据与口径注记

**AC-3.5 原文**：含 QJE、JFE 在内 5 刊仅用 Crossref 即产出完整卷期+论文清单；篇数与 `paper_count_claimed` 差异有解释。

**口径注记（W0 裁决沿用）**：Crossref timeline 为**年粒度**（facet `published:*`，API 无 volume/issue 枚举维度）。"完整卷期"以**论文清单含 volume/issue 字段 + 按刊对账口径**判定，而非独立的卷/期时间轴维度。

**D-018 双层证据**：

| 层 | 内容 | 证据 | 结果 |
|---|---|---|---|
| ① 离线回放（机制正确性，CI 化） | crossref facet/cursor 解析、字段映射、cursor 断点续拉 fixture + 集成测试 | T3 `tests/unit/test_crossref_*` + `tests/integration`（`make check` 每次跑，socket 禁网） | 由 T3 门禁承载（本记录不重复） |
| ② 在线实跑（真实站点零爬取枚举） | 5 刊真实 `crawler timeline` + 抽年 `crawler list`；篇数对账；QJE 全史锚点 | 本记录 §在线实跑（授权真实网络） | **见下（PASS 建议）** |

## 交付物 A：5 刊 VenueSpec YAML（`crawler venues lint` 全过）

`kind: journal` + `metadata_source: crossref` + issn 必填（D-015）；`fulltext_source` 为 Phase 4 占位（见 C1）。

| id | 名称 | field | ISSN | DOI 前缀 | metadata | fulltext（占位） | 真实平台 | 选择理由 |
|---|---|---|---|---|---|---|---|---|
| qje | Quarterly Journal of Economics | econ | 0033-5533 | 10.1093 | crossref | `elsevier_sd`* | OUP（`oup_silverchair`，未注册） | **必含**；econ 旗舰；全史 6655 锚点载体 |
| jfe | Journal of Financial Economics | finance | 0304-405X | 10.1016 | crossref | `elsevier_sd` | Elsevier ✓ | **必含**（既存 YAML，保留） |
| jet | Journal of Economic Theory | econ | 0022-0531 | 10.1016 | crossref | `elsevier_sd` | Elsevier ✓ | ISSN 在册、Crossref 覆盖佳、经济学理论子域，长历史（1969–）验早期 DOI 化边界 |
| jpubeco | Journal of Public Economics | econ | 0047-2727 | 10.1016 | crossref | `elsevier_sd` | Elsevier ✓ | ISSN 在册、公共经济学 applied 子域，与 jet（理论）互补分散 |
| jbf | Journal of Banking & Finance | finance | 0378-4266 | 10.1016 | crossref | `elsevier_sd` | Elsevier ✓ | ISSN 在册、金融/银行子域、高发文量压测 cursor 深翻 |

`*` QJE 真实全文平台为 OUP（`oup_silverchair`，catalog 记载），该 adapter 属 Phase 4 尚未注册；`fulltext_source` 取已注册的机构认证占位 `elsevier_sd`（沿 `venues/finance/jfe.yaml` 与 `tests/online/test_crossref_smoke.py` 的 QJE 占位先例）。**其余 4 刊真实平台即 Elsevier，`elsevier_sd` 为真值。** 详见 C1。

- **lint 结果**：`crawler venues lint` → `OK：45 个 venue 全部通过 lint`（含 4 新增 + 既存 jfe + 全部既有 venue）。字段分散：econ 3（qje/jet/jpubeco）+ finance 2（jfe/jbf）。

## AC-3.5 在线实跑（层②证据）

每刊 `crawler timeline <id>`（1 请求：facet 逐年计数）+ `crawler list <id> --year 2024`（1 facet + cursor 枚举）。隔离 home 干净库，逐请求 obslog 记账。

| id | timeline 届数（年粒度） | 年跨度 | `total_all`（=Σ facet 年计数，=`paper_count_claimed` 全史） | 抽样年 | 该年 claimed | 枚举 parsed | **差异** |
|---|---|---|---|---|---|---|---|
| qje | 141 | 1886–2026 | **6655** | 2024 | 46 | 46 | **0** |
| jfe | 53 | 1974–2026 | 4513 | 2024 | 123 | 123 | **0** |
| jet | 58 | 1969–2026 | 6253 | 2024 | 122 | 122 | **0** |
| jpubeco | 55 | 1972–2026 | 5402 | 2024 | 165 | 165 | **0** |
| jbf | 50 | 1977–2026 | 7500 | 2024 | 178 | 178 | **0** |

- **QJE 全史 total 对照 D-019 锚点 6655**：实跑 `total_all=6655` **= 锚点下限 6655（≥ 成立）**；`total_2024=46` = 闭合年锚点。零爬取（纯 Crossref API）产出 141 个出版年（1886→2026）的完整年级时间轴。
- **抽样年枚举篇数 == `paper_count_claimed`（差异全 0）**：5 刊 2024 年枚举 parsed 数逐刊**精确等于** facet claimed 数——说明 2024 窗内全部 Crossref 记录均含 `title[0]` + DOI，`§5.1` 的「title/doi 空跳过」护栏一条未触发（无记录丢失）。

### "完整卷期" 对账（W0 口径：论文清单含 volume/issue + 按刊对账）

抽样年（2024）论文清单字段覆盖（DB 实测，零网络）：

| id | 2024 papers | 含 volume | 含 issue | 含 doi |
|---|---|---|---|---|
| qje | 46 | 46 (100%) | 46 (100%) | 46 (100%) |
| jfe | 123 | 123 (100%) | 0 (0%) | 123 (100%) |
| jet | 122 | 122 (100%) | 0 (0%) | 122 (100%) |
| jpubeco | 165 | 165 (100%) | 0 (0%) | 165 (100%) |
| jbf | 178 | 178 (100%) | 0 (0%) | 178 (100%) |

- **volume + DOI 全 5 刊 100% 覆盖** → 卷级归属 + 强合并锚点齐备。
- **issue 覆盖分化（真实出版实践差异，非数据丢失）**：QJE（OUP）100% 有 issue；4 刊 Elsevier（jfe/jet/jpubeco/jbf）**0% 有 issue**——Elsevier ScienceDirect 采**连续 article-number/卷**模型，向 Crossref 存缴 volume + article-number 而不含传统 issue 号。故"完整卷期"判定为：**年级时间轴完整 + 100% volume 归属 + issue 按出版社存缴实践呈现**，Elsevier 无 issue 属其元数据存缴口径，adapter 忠实透传、无解析缺陷。

### 篇数与 `paper_count_claimed` 差异逐刊解释

抽样年枚举层差异**全为 0**（见上表）。`paper_count_claimed`（=`total-results`）的**全史口径**说明（逐刊共性 + 个性）：

- **共性——`total_all` 是 Crossref 登记全集，非"研究论文纯数"**：facet `published:*` 计入该 ISSN 名下**全部** Crossref 登记条目——研究论文 + 书评/编辑札记 + 卷首/卷尾事务性条目 + 勘误/更正 + 早期回溯 DOI 化过刊。故 `total_all`（如 QJE 6655、JBF 7500）大于"仅研究论文"口径；我方枚举**忠实复现**该全集（抽样年 parsed==claimed 已证），差异解释=口径本身含非论文条目，非枚举遗漏。
- **qje 个性——online-first 印刷年错位**：2024 pub-date 窗内 46 篇中 **20 篇** `paper.year=2025`（非 2024）。缘由：QJE online-first 比例高，`from-pub-date:2024` 命中其**在线发表年（2024）**，而 `§5.1` 派生 `year` 优先取 published-print（online-first 篇的印刷卷期落 2025，vol 140）。**不影响 2024 窗计数（仍 46）**，仅影响单篇 `year` 字段归属——属 Crossref online-first 日期语义，adapter 按 `§5.1` 日期族优先级（print→online→issued）正确取值。其余 4 刊此错位为 0（Elsevier pub-date 与印刷年对齐更紧）。
- **早于 DOI 时代**：QJE 回溯至 1886（Crossref 已回溯 DOI 化部分）；更早/未 DOI 化过刊在 JSTOR（catalog tier T3），不在 Crossref 全集内——这是 `total_all` 与"该刊创刊至今物理论文总数"的口径差之一（本 AC 判据为 Crossref 零爬取产出的一致性，非物理全量）。

## 交付物 B：在线冒烟批量实跑

命令：`PAPER_CRAWLER_CONTACT_EMAIL=yhyfhgs@gmail.com uv run pytest tests/online/test_{crossref,dblp,unpaywall}_smoke.py -m online -v`（三个已合并 adapter；openalex/s2 属 T6 未合并不跑）。

| 冒烟文件 | 首跑结果 | 说明 |
|---|---|---|
| `test_crossref_smoke.py` | **2 passed / 1 failed** | healthcheck ✓（title[0]="Deep learning" 捕获）、discover QJE total≥6655 ✓；**enumerate FAILED**——非 adapter 缺陷，见 C2（`sample.year==2024` 断言对 online-first 脆弱；枚举数据正确：parsed 46 = 锚点） |
| `test_dblp_smoke.py` | **首跑 2 failed → 复跑 2 passed** | 首跑两测均 **HTTP 503**（dblp.org 瞬时不可用，adapter 正确映射 TRANSIENT）；控制复跑（服务恢复）**2/2 PASS**，icml2023=1828 独立确认（见 C4） |
| `test_unpaywall_smoke.py` | **1 passed** | 金锚点 `10.1371/journal.pmed.0020124` healthcheck `is_oa`/`oa_status` 比对 ✓ |

- **crossref healthcheck 真值捕获**：`_HEALTHCHECK_DOI=10.1038/nature14539` → 规整化 `title[0]="Deep learning"`（healthy=True，`[PENDING golden]` 结构态）。**UPDATE_GOLDEN 候选**（设 `_HEALTHCHECK_TITLE="Deep learning"`）——属 adapter 改动，留 owner/T8（本次不修 adapter，见 C3）。
- **dblp ≥4s 纪律**：复跑 2 请求耗时 32.61s（含 `Crawl-delay:4` 限速 + 索引页发现），间隔纪律达标。

## 交付物 C：D-019 锚点回填（aggregators.md §7，随实跑顺带、零额外请求）

| 源 | 回填内容 | 依据 |
|---|---|---|
| crossref | QJE `total_all=6655`(=下限)/`total_2024=46` 实跑确认；`sample_doi=10.1038/nature14539` → title 真值 **"Deep learning"** 捕获（UPDATE_GOLDEN 候选）；状态 → [LIVE] 2026-07-23 | 本记录在线实跑 + smoke healthcheck |
| dblp | `conf/icml/icml2023.record_count=1828`（`parse_volume_xml` 卷内 inproceedings 计数；首 key `conf/icml/AamandACINS23`）；状态 [PENDING]→[LIVE] 2026-07-23，与审查实测一致 | dblp 复跑直取卷 XML |
| unpaywall | 金锚点五字段复核一致（is_oa:true/oa_status:gold/oa_locations:4/version:publishedVersion/url_for_pdf:null）；[LIVE] 2026-07-22 →（2026-07-23 复核一致） | unpaywall lookup 实测 |

§9 修订记录补 #10；§10 [UNRESOLVED] 销 crossref healthcheck 真值 + dblp icml2023 两项（openalex 正锚点 / s2 需 key 仍 [PENDING]，属 T6 范围）。

## 在线请求台账（33 / 50 预算硬顶，全程限速合规、UA 携 mailto、零凭证）

| 批次 | 端点/命令 | 请求数 | 状态 |
|---|---|---|---|
| AC-3.5 CLI | 5 刊 × [`timeline`(facet 1) + `list --year 2024`(discover facet 1 + enumerate cursor 2)] | 20 | 全 200（obslog 记账） |
| 锚点捕获 | crossref `/works/10.1038/nature14539` ×1 + unpaywall `/v2/{gold}` ×2 + dblp `icml2023.xml` ×1 | 4 | 全 200（obslog 记账） |
| 冒烟首跑 | crossref(hc1+discover1+enum2=4) + dblp(hc1+discover1=2) + unpaywall(1) | 7 | crossref 200；dblp **2×503**（瞬时）；unpaywall 200 |
| dblp 冒烟复跑 | healthcheck 1 + discover 1 | 2 | 全 200 |
| **合计** | — | **33** | **≤ 50 硬顶，未逼近**（护栏未触发） |

- 逐请求 obslog（隔离 home `logs/crawler-*.jsonl`）记账 24 条 http exchange（crossref 21 / unpaywall 2 / dblp 1，全 200）；冒烟 9 条经各文件 `MAX_REAL_REQUESTS` 护栏（crossref≤5、dblp≤2、unpaywall≤1）记账。
- 合规声明：crossref 保守 5 req/s（polite pool，UA mailto）；dblp ≥4s/req（`Crawl-delay:4`）；unpaywall `?email=` 经日志脱敏（`obslog.redact` `email=***`，B-B4 已在位）；仅访问各源官方文档化 API；无认证、无凭证、无绕过。

## Concerns（供 controller 裁决，均已如实记录）

- **C1｜QJE `fulltext_source=elsevier_sd` 为注册占位（真实平台 `oup_silverchair` 未注册）**：`oup_silverchair` 尚无注册 adapter/stub（entry-point + stubs.py 均无），而 registry lint 要求 `fulltext_source` 已注册。本次沿在树先例（jfe.yaml/smoke test 均用 `elsevier_sd` 作 QJE 占位）取 `elsevier_sd`，YAML `notes` 显式披露真实平台 + Phase 4 改写计划。**未新增 adapter/stub**（AGENTS §7 架构/设计取舍归主 agent；红线倾向不改 adapter 层）。**建议 controller 决定 Phase 4 是否补 `oup_silverchair` stub 以对齐 catalog**（其余 4 刊 `elsevier_sd` 为真值，无此问题）。
- **C2｜crossref 冒烟 `test_enumerate_qje_2024_sample_field_mapping` 的 `sample.year==2024` 断言对 QJE online-first 脆弱**：`stubs[0]`（"Measuring and Mitigating Racial Disparities in Tax Audits", DOI 10.1093/qje/qjae027）为 online-first，pub_date 2025-01-11、印刷 year=2025，落在 2024 pub-date 窗内。**枚举数据正确**（parsed 46 = 锚点，DOI/title/volume 字段齐），仅该断言过严。**非 adapter 缺陷**。建议放宽（如 `year in {2024,2025}` 或改断言 issue/volume 而非 year）。**未擅改该在线测试**（归 T3 owner/controller）。
- **C3｜crossref healthcheck 真值 golden 化留 UPDATE_GOLDEN**：`_HEALTHCHECK_TITLE` 现为 `None`（结构态）；真值 "Deep learning" 已捕获。**未修 adapter**（红线 + owner 权责），建议 owner/T8 落 `_HEALTHCHECK_TITLE="Deep learning"` + 相应离线夹具。
- **C4｜dblp.org 瞬时 503**：冒烟首跑两测 503（服务瞬时不可用），复跑即 2/2 PASS——瞬时基础设施抖动，非代码缺陷；如实记录。可选加固：dblp 冒烟对 5xx 加一次退避重试（非本次范围）。
- **C5｜用户 `~/.paper-crawler/config.toml` 无 `[identity].email`**：默认 home 直跑真实 CLI 会掉出 Crossref polite pool（UA 无 mailto）。本次经隔离 scratchpad home 注入 email 规避。**建议用户在真实 config 补 `[identity].email`**。（附带观测：该 config 明文存 openreview password/token——属 config.py/AGENTS §6.4「home 内、仓库外」既定设计，本次未动、未外泄。）

## 判定建议（controller 终签）

- **5 刊（含 QJE/JFE）仅用 Crossref 零爬取产出完整年级时间轴 + 100% volume/DOI 论文清单**；抽样年枚举 parsed == `paper_count_claimed`（差异全 0）；QJE 全史 `total_all=6655 ≥` D-019 锚点；篇数/口径差异逐刊有据解释（online-first / 非论文条目 / Elsevier issue 存缴实践 / 早于 DOI 过刊）。
- **建议 AC-3.5 = PASS（Phase 3 口径，D-018 双层证据齐备：层① T3 离线门禁 + 层② 本记录在线实跑）**，待 controller：①采信独立复核台账合规；②裁决 C1（oup_silverchair）/C2（冒烟断言）/C3（UPDATE_GOLDEN）处置；③转正去 draft、并入 AC 汇总。

## 待 controller 终验补全

1. 独立复核（台账 33≤50 合规、限速 5req/s + ≥4s、端点官方文档化、UA mailto、零凭证）结论；
2. C1~C5 处置裁决；
3. 转正：去 draft、`aggregators.md → implemented`（T8）、INDEX/progress/decision-log 同步（T8）。
