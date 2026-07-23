---
title: Adapter 设计 · Econometric Society（econsoc，实现级）
status: draft
owner: D3
updated: 2026-07-24
---

# Adapter · `econsoc`（Econometric Society 三刊 · 实现级详设）

> 全称 **The Econometric Society**（自营平台 `econometricsociety.org`，Cloudflare 前置，CC BY 4.0 / CC BY-NC 4.0）。
> 服务 Econometrica(ECMA) / Theoretical Economics(TE) / Quantitative Economics(QE) 三刊当前面。
> **事实基座**：[research/site-survey/econometric-society.md](../../research/site-survey/econometric-society.md)（[LIVE] 2026-07-24 R0c，26 请求实测，零全文下载、零凭证）。
> **技术形态复用**：[aaai-ojs.md](aaai-ojs.md)——OJS+OAI-PMH 收割的既有完整设计；TE/QE 与 AAAI-OJS **同款技术形态**（OAI `ListRecords`/`resumptionToken` 翻页、DOI 后缀过滤、墓碑处理、oai_dc 体层解析、canary 结构均最大化复用，见 §4/§10）。
> **联动件**：[wiley.md](wiley.md)（ECMA 过刊段 token 档，§9 D-028 草案定分段修正范围）；D-005（元数据主干 crossref）/D-007（preprint_of，服务 JF↔ECMA）/D-011（ssrn 限速纪律参照系）。
> **红线**：三刊为开放许可（CC BY/BY-NC）个人科研只读；诚实 UA；不设计再分发（AGENTS §6.5）。Wiley 域 stateless 403 CF 即 BLOCKED、停手（红线，§5）。

## 1. 定位

- **family**：`open_access`（匿名 OA 全文、无认证、无 token——survey §4 [LIVE] 匿名 galley PDF `HTTP/2 200 application/pdf accept-ranges`）。**auth 档 = `none`**。
- **capabilities**：`DISCOVER | ENUMERATE | RESOLVE | FETCH`（四位）。**无 SEARCH**——冻结 `SourceAdapter` 协议无 `search()`（先例 arxiv.md §1 / aaai-ojs.md §1）；订阅命中经 enumerate 增量 + 本地过滤，SEARCH 统一推迟 Phase 6。
- **能力按 venue 非对称分工（★ 见 §3.1）**：**TE/QE** 走全四位（econsoc 自持 OJS OAI-PMH 枚举）；**ECMA** 只实际行使 `RESOLVE | FETCH`（枚举走 crossref——**ECMA 不在 econtheory OJS 实例上**，OAI 无 ECMA 端点）。capabilities 是 adapter 上界，venue 的 `metadata_source`/`fulltext_source` 决定每刊实际行使哪几位（先例 wiley：capabilities 只 RESOLVE|FETCH、enumerate 委 crossref）。
- **服务 venue（3 个 venue YAML：`ecma` / `te` / `qe`）**：
  - **TE / QE**：`metadata_source: econsoc`（OJS OAI-PMH），`fulltext_source: econsoc`，`auth.level: none`。
  - **ECMA**：`metadata_source: crossref`（按 ISSN，D-005），`fulltext_source: 年代分段`（当前→econsoc / 过刊→wiley(token) / pre-DOI→界外，§3.3 + §9 D-028）；`auth.level: none`（当前段主路径；过刊段路由到 wiley adapter 时由 wiley 自持 institutional 认证）。
- **元数据/全文本域分工**：TE/QE 元数据在 `econtheory.org/ojs`（OAI），全文 galley 在 `econometricsociety.org`（合并前端）；ECMA 元数据在 crossref、全文 galley 在 `econometricsociety.org`。**resolve/fetch 对三刊当前段统一落 `econometricsociety.org`**（§4）。
- **版权红线（AGENTS §6.5）**：三刊最新样本 CC BY 4.0(ECMA) / CC BY-NC 4.0(TE/QE)（survey §1 [LIVE]，逐字引用 <15 词）——**是开放许可**（区别于 aaai_ojs 的"免费只读非 CC"）；仍按个人科研只读、诚实 UA、不再分发姿态实现。

## 2. 站点勘察摘要

来源：[econometric-society.md](../../research/site-survey/econometric-society.md)（[LIVE] 2026-07-24，26 请求）。

| 事实 | 值 | 出处 |
|---|---|---|
| 平台迁移形态 | **前向切换**：三刊新刊迁自营 `econometricsociety.org`（CF 前置）；过刊不迁——ECMA 过刊留 Wiley（2015 DOI→`doi.wiley.com` 403 CF）、pre-DOI 留 JSTOR（10.2307） | §0/§2 |
| OAI-PMH（TE/QE） | `econtheory.org/ojs/index.php/{te,qe}/oai` 匿名 200；**单一多刊 OJS 实例**；TE `Identify` earliestDatestamp=2006-03-02、`deletedRecord=no`、granularity 秒级、gzip；TE `ListRecords` **completeListSize=656** | §4 |
| **ECMA 不在 OJS** | econtheory OJS 实例仅 `te`/`qe` 两刊端点；ECMA(ECTA) 无 OAI 端点 → 枚举只能 crossref-by-ISSN | §4/§1 |
| crossref 覆盖 | prefix `10.3982` → owner=**The Econometric Society**（member 2359，**三刊共用前缀**）；ECMA ISSN 0012-9682 total **7307**（含 pre-DOI/JSTOR 时代）、TE 1933-6837 total **735**、QE 1759-7323 total **617** | §1 |
| DOI 形态 | `10.3982/{ECTA\|TE\|QE}{n}`（如 `ecta23709`/`te6021`/`qe2297`）；**前缀学会自持、三刊共用，仅 DOI 后缀区分刊** | §1 |
| 全文 galley | 当前落地 `econometricsociety.org/doi/{DOI}` →302→ `/publications/{journal-slug}/{yyyy}/{mm}/{dd}/{title-slug}`，页标 "Open Access"，含 galley 链 `/publications/.../file/{file}.PDF`；**TE galley HEAD [LIVE] 200 application/pdf accept-ranges**（匿名 OA 确认，Range 支持） | §4 |
| galley 不可构造 | `{file}`/`{slug}` 非 DOI 可推导 → **resolve 须 GET 落地页抽 galley 链**（§4，`resolve_offline=False`，异于 aaai_ojs 零网络 resolve） | §4 |
| robots | `econometricsociety.org`：`*` 仅禁 `/admin//ckeditor//temp/`、**具名封 `ClaudeBot`/GPTBot/… `Disallow: /`**（反 AI）；`econtheory.org` 极宽松（仅禁 dotbot、无 AI 封禁）；`qeconomics.org` **TLS 证书过期**（curl 60，停用不直连） | §5 |
| license | TE/QE CC BY-NC 4.0；**ECMA CC BY 4.0**（OA 强信号，[UNRESOLVED① 全刊 OA 未终证]，§8） | §1/§3 |

## 3. 覆盖边界与 venue 分段建模（★核心裁决）

### 3.1 三刊标识与枚举通道：非对称（TE/QE OAI-枚举 vs ECMA crossref-枚举）

三刊各有独立 ISSN、共用 `10.3982` 前缀（仅后缀 `ECTA`/`TE`/`QE` 区分刊）。**枚举通道非对称，因 ECMA 不在 econtheory OJS 实例**：

| 刊 | venue id | 枚举通道 | metadata_source | fulltext_source |
|---|---|---|---|---|
| Theoretical Economics | `te` | OJS OAI-PMH（econsoc 自持）＋ crossref-by-ISSN 交叉核对 | `econsoc` | `econsoc`（OA） |
| Quantitative Economics | `qe` | 同 TE（同一 OJS 实例第二刊） | `econsoc` | `econsoc`（OA） |
| Econometrica | `ecma` | **crossref-by-ISSN（唯一）**——ECMA 无 OAI 端点 | `crossref` | 年代分段（§3.3） |

> **⚠ 勘察/预置口径澄清**：controller 预置提及 "OAI DOI 后缀过滤 **ECTA**/TE/QE"——但 survey §4 [LIVE] 实测 OJS 实例仅 `te`/`qe` 两端点，**ECTA(ECMA) 不在其上**。故 OAI 后缀过滤实际只作用于 **TE/QE**；ECMA 枚举归 crossref-by-ISSN。此非对称是本设计的既定事实，非可选。

### 3.2 ENUMERATE 通道选型（方案对比 + 建议）

TE/QE 有两条独立可用枚举通道，需定主/辅：

| | **方案 α（建议）：TE/QE econsoc 自持 OAI 枚举** | 方案 β：三刊全 crossref-by-ISSN |
|---|---|---|
| te/qe `metadata_source` | `econsoc`（OAI-PMH，复用 aaai_ojs 收割机） | `crossref`（系统同构，D-005 期刊主干） |
| 一趟收获 | DOI + 摘要(`dc:description`) + rights + 期号，**单次收割齐全** | DOI + 有限元数据（crossref 摘要稀疏） |
| OAI 角色 | 主枚举 | 降为二级核对 / D-019 锚点校验 |
| crossref 角色 | 交叉核对（656 vs 735 对账 [UNRESOLVED③]） | 主枚举 |
| `_oai.py` 信封复用面 | **信封层全复用**（`_oai.py`，arxiv/aaai 第 3 消费者）+ 体层薄解析器自写（★C：体层各写，~50 行） | 仅 crossref（不用 OJS 收割机） |
| 系统一致性 | 期刊枚举双机制（OAI for TE/QE、crossref for ECMA+他刊）——轻微 D-005 张力 | 全期刊单机制（crossref） |

**建议方案 α**，理由：①controller 预置定"主路径=OJS OAI-PMH ... aaai_ojs 同构复用"，且必读输入令"最大化复用 aaai_ojs 收割机"；②OAI 一趟收 DOI+摘要+rights（crossref 摘要覆盖稀疏，OA 刊摘要在 OJS 最全）；③crossref-by-ISSN 保留为对账通道（TE completeListSize 656 vs crossref 735 差额，实现期对账 [UNRESOLVED③]，survey §4）；④**D-005 张力可解**：D-005 措辞是"discover/enumerate **优先**走聚合 API"（偏好非绝对），aaai_ojs 先例已确立"OJS adapter 自持 OAI 枚举为 metadata_source"；TE/QE 是 OA 刊 + 活 OAI + 原生摘要，自枚举正当。**代价**（承认）：系统内期刊枚举出现双机制，ECMA 与他刊仍走 crossref。若主 agent 更重系统单机制一致性，翻方案 β（自洽但放弃 OJS 收割机复用）。

> **⚠ 选型透明化（本 α 反转勘察推荐）**：survey §4/§6.1 [LIVE] 定 **crossref-by-ISSN 为主干/推荐、OJS OAI-PMH 为二级校验/补摘要**；本 α **反转此推荐**（OAI 主枚举、crossref 降为交叉核对）。反转理由：①OJS 原生端点携摘要（`dc:description`）+ rights，OA 刊元数据在 OAI 最全（crossref 摘要覆盖稀疏）；②复用 `_oai.py` 信封核（arxiv/aaai 先例、零新信封代码）；③**controller 已批定枚举四范式全谱——OAI 原生端点自持属合法第③范式**（原生 API 端点自枚举，与 aaai_ojs 同类，非越界）。crossref-by-ISSN 保留为交叉核对（656 vs 735 对账 [UNRESOLVED③]）。翻 β 即回落 survey 原推荐。

### 3.3 ECMA 年代分段路由（★ 方向 a/b 论证；D-028 草案主设计）

ECMA(ECTA) 的 `10.3982` DOI 跨三个托管年代，**fulltext 分三段**：

| 段 | 年代 | 托管 | 归属 adapter | 全文获取 |
|---|---|---|---|---|
| 当前段 | ~切换点起（2026 实测自营） | `econometricsociety.org` 自营（CF） | **econsoc**（本 adapter） | 匿名 OA galley 200 |
| 过刊段 | ~2010–切换点 | `doi.wiley.com`（Wiley TDM 域） | **wiley**（token 档） | TDM API by DOI，无 token→skip |
| pre-DOI 段 | <2010（10.2307 旧前缀） | JSTOR | 界外（tier T3 暂缓） | 不获取 |

**切换点日历日 [UNRESOLVED②]**（survey §2：R0c 未能定；实现期二分确定 DOI 区间分界）。分段判定法两案：

- **方向 a（建议）：运行时 per-DOI 域名判归属**。判据 = DOI 实际落地域名：resolve 阶段对每个 ECMA DOI 走 `doi.org` HEAD `-L`（或读 crossref works 的 `resource.primary.URL` 域名，枚举 payload 已带、边际零请求）→ `econometricsociety.org`＝econsoc 取；`doi.wiley.com`＝路由 wiley adapter（token 档）；`jstor.org`＝界外跳过。
- **方向 b：年份粗分 + 实现期在线核实**。在 `ecma.yaml` quirks 硬编码切换边界年：year≥boundary→econsoc、[wiley起,boundary)→wiley、pre-DOI→界外；边界年实现期以 `doi.org` HEAD 二分核实修正。

**论证（取方向 a）**：①econsoc 的 resolve **本就网络绑定**（须 GET 落地页抽 galley，§4）——域名判归属的边际成本近零（crossref `resource.primary.URL` 域名在枚举 payload 已在手，doi.org 落地在 resolve 本会发生）；②**自校正**：学会未来若继续前向迁移过刊、或切换边界模糊，域名路由自动跟随现实，无需改 config/文档；硬编码边界年一旦学会移动边界即静默误路由；③**避开未定切换日**（[UNRESOLVED②] R0c 未能 pin down，方向 a 不依赖它）。**caveat**：crossref 登记 link 有陈旧风险（survey §2：QE 的 crossref link 仍留 `onlinelibrary.wiley.com` 遗留 Wiley link，即使已自营）→ **权威信号取 resolve 时的实际落地域名（doi.org HEAD -L 实时重定向终点），crossref link 仅作 pre-filter 提示**。方向 b 保留为 pre-filter（快速排除 10.2307/JSTOR 明显界外记录、在 crossref 域名可信为 econsoc/wiley 时免逐 DOI HEAD）。**TE/QE 不分段**（全程 econsoc OA），ECMA 才分段。

### 3.4 identifier：产本源规范 DOI

- **`identifiers = (('doi', <DOI 小写规范串>),)`**——三刊 DOI 均为 Econometric Society 为本篇本版注册的**本源官方 id**（前缀 `10.3982` 学会自持），是强合并锚点。归一：小写化、`10.3982/{ecta|te|qe}{n}` 精确形态、不剥前缀（沿 aaai-ojs.md §3.3 ★B「本源官方 DOI 产 identifier」原则，`ids.normalize_doi()` 统一入口）。
- **与 R3/D-007 关系**：本源 DOI 产 identifier 不违反 R3（R3 针对指向他源版本的跨源线索）；ECMA 过刊 Wiley 版与当前自营版**同一 DOI**（前向迁移不改 DOI）→ 天然同一性（非 preprint_of）。JF/SSRN 先行版（不同 DOI/id）经 D-007 `preprint_of` 关联，不自动合并。
- **meta**（`str→str`）：`('pdf_url', <galley 落地 URL 或 OJS article/view URL>)`（resolve 输入）、`('landing_url', econometricsociety.org/doi/{DOI})`、可选 `('ojs_article_id', …)`（TE/QE）、`('primary_url_domain', …)`（ECMA 分段路由信号，§3.3）。摘要/作者走 PaperStub 一级字段。

## 4. 各阶段实现方案

- **discover_timeline**：
  - **TE/QE（econsoc-owned）**：零网络，读 `quirks.volume_map`（year→volume；TE/QE 自 2006 连续卷）逐年产 IssueRef，幂等键 `(venue, year)`（沿 aaai-ojs.md §3.2 方案 B 届/年聚合）。`since` 收窄起点。**⚠ 卷↔年映射实现期由 OAI 全量收割 `dc:date` 最小值锚定**（earliestDatestamp 2006 不可信为发表下界——datestamp=入库时间，aaai §3.1 同类教训）。
  - **ECMA**：委 crossref（`metadata_source: crossref`）——econsoc 不参与 ECMA discover。
- **enumerate_issue**：
  - **TE/QE（OAI-PMH 收割，复用 `_oai.py` 信封核）**：`GET {oai_base}?verb=ListRecords&metadataPrefix=oai_dc`（+`resumptionToken`），`oai_base = econtheory.org/ojs/index.php/{ojs_code}/oai`（`ojs_code`∈{te,qe}，来自 `quirks.ojs_code`）。**客户端过滤 = DOI 后缀**（保留 `dc:identifier` 中 DOI 后缀匹配 `{TE|QE}` 且属该刊的记录）。`noRecordsMatch`＝非错误（空序列正常完成）；`<header status="deleted">` 墓碑跳过计数（`deletedRecord=no` 实测，墓碑罕见但仍守）。字段映射：`title=dc:title`、`abstract=dc:description`、`authors=(dc:creator,…)`、`year=int(dc:date[:4])`、`identifiers=(('doi',doi_lower),)`、`meta` 见 §3.4。**枚举策略同 aaai §4**：历史回填=一次全库收割按刊 partition；当前增量=固定回看窗 datestamp（datestamp≠发表日，故 membership 判据是 DOI 后缀非日期窗）；去重由 `identifier('doi')` 主键天然保证。
  - **ECMA**：委 crossref-by-ISSN（不经 econsoc）。
- **resolve_assets（★ 网络绑定，`resolve_offline = False`）**：输入 paper DOI。**统一路径**（三刊当前段）：`GET econometricsociety.org/doi/{DOI}` →302→ 落地页 → 解析 galley 链 `/publications/.../file/{file}.PDF` → `AssetPlan(kind=PDF, url=<galley 绝对 URL>, url_strategy=DIRECT, auth_needed=none, expected_type="application/pdf")`。**ECMA 分段前置**（§3.3 方向 a）：先判 DOI 落地域名——`doi.wiley.com`→改产 wiley 档 AssetPlan（或交 wiley adapter，token 门控）、`jstor`→零资产（界外）、`econometricsociety.org`→上述 econsoc 路径。**⚠ 异于 aaai_ojs 零网络 resolve**：galley `{file}`/`{slug}` 不可由 DOI 构造 → 必 GET 落地页；故 econsoc **不置 `resolve_offline=True`**，resolve 经限速闸（D-022，正确——econometricsociety.org CF 前置需限速）。**实现期核实**（⚠）：econtheory oai_dc `dc:relation` 是否直给 galley 链——若给且指向 econometricsociety.org galley，则 TE/QE resolve 可退化零网络优化；保守设计取网络绑定路径。
- **fetch_asset（流式）**：`HttpClient.stream`→`io.write_stream`；`%PDF` 魔数校验归 pipeline（冻结分工）。**adapter 职责**：把"PDF url 却回 HTML"嗅探为 `GONE`（撤稿）或 challenge（CF 挑战页，§5/§6）；复用 arxiv `_gone_guarded_stream` HTML 首字节嗅探。
- **healthcheck**：TE OAI `Identify` 200（存活基线，`repositoryName` 含 "Theoretical Economics"）+ **跨刊 GetRecord/落地 canary**（TE/QE/当前 ECMA 各 1，比对规整化 `dc:title` + DOI 后缀双字段，抗 flake）+ econometricsociety.org galley HEAD 200 探针（监 CF 挑战，§5）。crossref canary 归 aggregators。
- **OAI 复用边界（★ 承 aaai-ojs.md §9 ★C 裁决）**：共享核实体 = **`src/paper_crawler/adapters/_oai.py`**（**信封层**：错误码表/`noRecordsMatch` 空态/墓碑遍历+计数/`resumptionToken`/`OaiListPage` 页形状——公有 `parse_oai_page(data, *, record_parser)` + `raise_if_oai_error`/`resumption_token_from`/`normalize_ws`/`required_text` 等 helper），已 **arxiv + aaai_ojs 双消费**、`tests/unit/test_oai_envelope.py` 专测守门。**econsoc = 第三个信封消费者**：注入自己的 `record_parser` 回调（在 `<metadata>` 内找 `<oai_dc:dc>` 体元素），**零触碰 implemented aaai_ojs**（其 T4 + 专测守门充分，无回归面）。**oai_dc 体层自写薄解析器**（`dc:title`/`creator*`/`description`/`date`/`identifier→DOI`/`rights`，~50 行）——★C 裁决边界＝**信封共享、体层各写**：econsoc 虽与 aaai 同用 `oai_dc`，**刻意不复用 aaai 的体层解析器**（跨 adapter import 会引入耦合，`_oai.py` 分层边界注释明示"体层由调用方 `record_parser` 注入"），**接受 ~50 行重复**（★C 退路）。省力面 = **信封层零新代码**（复用 `_oai.py`）+ 体层薄解析器 + DOI 后缀过滤谓词（`{te|qe}`）+ `ojs_code`/`oai_base` 参数。

## 5. 限速与礼貌

| domain | 速率 | 依据 |
|---|---|---|
| `econtheory.org`（OAI 收割） | **1 req/2s（30 rpm），并发 1** | robots 极宽松（仅禁 dotbot，无 AI 封禁、无 Crawl-delay，survey §5 [LIVE]）；OJS 单实例承载有限，沿 aaai_ojs OJS 保守默认 |
| `econometricsociety.org`（landing + galley fetch） | **≥3s/req 下限（controller 预置）；起步建议 5s + 抖动、并发 1、日配额**；连续 CF 挑战即 **BLOCKED** | CF 前置 + **具名封 ClaudeBot 反 AI**（survey §5，CEPR 先例同构）→ 宁慢勿封；survey §6.1 建议 5s 起步对齐 ssrn(D-011) 纪律 |
| `crossref`（ECMA 枚举） | 系统默认（aggregators polite pool ≥1s） | 委 crossref adapter，非 econsoc 自持桶 |

- **robots 合规**：econometricsociety.org 具名封 ClaudeBot 等（`Disallow: /`），**PaperCrawler UA 不含 ClaudeBot token → 落 `*` 组**，`/doi/`+`/publications/`（OA 全文路径）字面允许、`*` 仅禁 `/admin//ckeditor//temp/`（与本 adapter 路径无交集）。**但学会明确反 AI 爬** → 保守限速 + 诚实 UA + canary 监挑战，**降级信号交 controller 裁决**（连续 challenge → catalog 降级为仅元数据 via crossref，不硬对抗，AC-0.2）。
- **速率口径冲突记录**：controller 预置 ≥3s vs survey §6.1 ≥5s 起步——取 **≥3s 为硬下限、5s+抖动为起步建议值**（CF+反 AI 姿态偏保守），实测 429/challenge 后按纪律调。
- **绝不依赖的域**：`qeconomics.org`（TLS 证书过期，survey §5，`-k` 仅勘察诊断、adapter 不关校验绕过）；`doi.wiley.com` stateless（403 CF → BLOCKED 停手，过刊段合规正道是 wiley TDM token）。
- **版权/ToS 姿态**：开放许可（CC BY/BY-NC）个人科研只读、不再分发；不申请任何 token（当前段匿名 OA 足够；过刊段 token 归 wiley adapter）。

## 6. 失败模式映射

| 站点现象 | error_class | 说明 |
|---|---|---|
| OAI `noRecordsMatch`（TE/QE） | —（**非错误**） | 空刊/空窗合法响应，解析空序列正常完成（arxiv/aaai 先例） |
| OAI `badResumptionToken` | `transient` | token 过期，任务级重跑重建收割窗 |
| OAI `badArgument`/`badVerb`/`cannotDisseminateFormat` | `config` | 我方请求构造缺陷，响亮停机 |
| OAI `idDoesNotExist`（GetRecord canary） | `gone` | 单 id 未命中 |
| **econometricsociety.org CF 挑战**（galley/landing） | `challenge` | `cf-mitigated: challenge`/挑战页 HTML → **BLOCKED + 冷却**；canary 监（§5）；**不对抗**（AC-0.2） |
| galley PDF url 回 HTML（撤稿/登录/合并） | `gone` | adapter 首字节嗅探（复用 arxiv `_gone_guarded_stream`）；`%PDF` 权威校验归 pipeline |
| ECMA DOI 落 `doi.wiley.com`（过刊段） | `no_entitlement`（路由信号） | §3.3：非 econsoc 覆盖面 → 路由 wiley adapter（token 档）或标 skip；无 token→该篇 skip 不阻塞 |
| ECMA DOI 落 JSTOR（10.2307，pre-DOI） | —（界外零资产） | resolve 产零资产（tier T3 暂缓），非错误 |
| **当前 ECMA galley 非匿名可下**（若非全刊 OA，[UNRESOLVED①]） | `no_entitlement` | 保留 OA fallback 升级路径（unpaywall / 过刊 wiley token）；实现期 HEAD 一篇当前 ECMA galley 判定 |
| oai_dc XML 语法错 / 缺 `dc:title` / 无 DOI | `parse` | canary 标红（arxiv `_fromstring`→PARSE 先例） |
| 连接超时 / 5xx | `transient` | HttpClient 统一映射 |

**已知冻结限制（沿 aaai-ojs.md §6 同批先例）**：`FetchResult` 无 `http_status`（本期 NULL）；metadata 阶段请求（OAI 收割/落地页 GET）不入 `FetchLog`，限速审计经 obslog jsonl；`Retry-After` 仅观测不驱动调度。

## 7. Fixtures 与测试

- **T1 单元**（网络解耦）：DOI 后缀解析/归一矩阵（`{ecta|te|qe}{n}` 抽刊别+小写化+非法拒绝）；oai_dc 体层解析器（若复用 aaai 共享核则测过滤谓词差异）；OAI 信封层（复用 aaai 共享核测例）；ECMA 分段路由判定（域名→adapter，方向 a：econometricsociety.org/doi.wiley.com/jstor 三态 + crossref link 陈旧 caveat）；volume_map→IssueRef（TE/QE，含 `since` 收窄、界外年拒绝）；galley 链抽取（落地 HTML→`/publications/.../file/{file}.PDF`）。
- **T3 fixture（覆盖 §6 error_class）**：①TE OAI `ListRecords` oai_dc 正常页（`resumptionToken`、多 `dc:creator`、CC BY-NC `dc:rights`）②续页（token 消费到无）③`noRecordsMatch`→非错误 ④`badResumptionToken`→transient ⑤`badArgument`→config ⑥`idDoesNotExist`→gone ⑦econometricsociety.org 落地页正常（含 galley 链）⑧CF 挑战页 HTML→challenge/BLOCKED ⑨galley url 回 HTML→gone ⑩ECMA crossref works 记录（`resource.primary.URL` 三域名样本，分段路由）⑪畸形 XML→parse。**录制物为公开元数据，剔请求头/cookie**。
- **T4 集成（MockTransport 全链路）**：TE/QE discover→enumerate(OAI)→resolve(landing→galley)→fetch，DOI 后缀过滤计数断言；ECMA enumerate(crossref)→分段路由(域名)→resolve 断言（econsoc/wiley/界外三分流计数）；当前段重复 enumerate 无重复无遗漏（`identifier('doi')` 去重）。
- **T5 在线冒烟（≤10 请求）**：TE `Identify` 1 + TE OAI 首页 1 + resumptionToken 续页 1 + TE 单篇 landing→galley→PDF fetch 1 + 当前 ECMA galley HEAD OA 判定 1（闭 [UNRESOLVED①]）+ ECMA 过刊 DOI doi.org HEAD 域名核对 1（闭 [UNRESOLVED②] 抽样）+ robots 复核 1；`MAX_REAL_REQUESTS` 设限。
- **canary 样本**：TE/QE/当前 ECMA 各 1 跨刊固定记录，比对规整化 `dc:title` + DOI 后缀（抗折行）；基线 TE `Identify.repositoryName` 含 "Theoretical Economics"。**实测锚**：TE completeListSize 656（量级参考非精确判据，对账 [UNRESOLVED③]）。
- **验收口径（★ 沿 aaai-ojs.md §7 ★E）**：**通用 DoD**（无专属 AC-2.x；econsoc 属 Phase 5，AC 待 Phase 5 验收表登记）——①`timeline {te,qe}` 覆盖 volume_map 全区间；②`pull {te,qe} --year <Y> --limit N` 落盘 N 个 `%PDF` 文件 >10KB、DB↔文件对账；③ECMA 分段：`pull ecma --year <当前>` 当前段 OA 取回、过刊段无 token 时 skip 不阻塞。**D-019 锚点**：三刊 crossref-by-ISSN 计数各 ≥1 行（对账 656/735 等差额）。

## 8. 风险与维护

- **[UNRESOLVED① 当前 ECMA 是否全刊 OA]**（survey §3）：最新样本 CC BY 4.0 + 匿名 200 是强信号，但 Econometrica 历史订阅制、学会自营后可能 diamond/subscribe-to-open，单篇 license 不足断全刊。**实现期 HEAD 一篇当前 ECMA galley 判匿名可下否**（T5 冒烟闭合）；若非全刊 OA→当前 ECMA 走 no_entitlement + OA fallback（§6）。**不阻塞 TE/QE 主路径**（TE/QE OA 已 [LIVE] 确认）。
- **[UNRESOLVED② Wiley→自营切换日]**（survey §2）：方向 a（域名判归属）**不依赖切换日**故此项不阻塞路由；仅方向 b pre-filter 需边界年，实现期 doi.org HEAD 二分核实。
- **[UNRESOLVED③ TE 656 vs crossref 735 差额]**（survey §4）：编辑部记录/DOI 粒度差，实现期对账；不阻塞——DOI 后缀过滤 + `identifier('doi')` 去重使两源差额自然收敛。
- **qeconomics.org TLS 证书过期**（survey §5 [LIVE]）：**adapter 绝不直连该域、绝不关校验绕过**；QE 一切经 OAI（econtheory.org/ojs/index.php/qe）+ crossref + econometricsociety.org 落地。风险节明记：若 QE 独立域证书长期不修，QE 路径完全不受影响（不依赖该域）。
- **CF 策略/反 AI 收紧**：econometricsociety.org 具名封 ClaudeBot、当前对 stateless PaperCrawler UA 无挑战——若未来对 `*` 组加挑战，canary 首触即 BLOCKED + catalog 降级为仅元数据（crossref）。canary 周检。
- **前向迁移持续**（学会可能继续把 Wiley 过刊迁自营）：方向 a 域名路由自动跟随，无需改 config；方向 b 会静默误路由——**再证方向 a 优越**。
- **OJS/前端平台升级改 URL/schema**：fixture+canary 覆盖；oai_dc 标准协议较 HTML 稳；galley 链抽取选择器（`/publications/.../file/*.PDF`）是 HTML 依赖面、canary 监。

## 9. 裁决记录（决策草案 · 待 controller 并入 decision-log）

> 本节两条为**草案成型文本**（格式仿 [decision-log.md](../../plan/decision-log.md) D-020/D-024），**不改 decision-log.md 本身**——待主 agent/controller 采纳后由其分配正式 D-NNN 号并录入。编号 D-027/D-028 为**建议占位**（decision-log 当前最新为 D-026，单调递增）。

### D-027 草案 · repec Phase 5 出列（降级为 enrich 通道候选，挂 Phase 6 DSL）

- 状态：**proposed（草案）** · 日期：2026-07-24 · 依据：[research/site-survey/repec.md](../../research/site-survey/repec.md)（[LIVE] 2026-07-24 R0c，13 请求）
- **背景**：Phase 5 兄弟源勘察含 RePEc 生态（ideas/econpapers.repec.org）。R0c 实测判定 RePEc = **分布式书目元数据聚合器、非全文源**（条目=元数据+摘要+链出到源；NBER 条目 [LIVE] 全文链回 nber.org、RePEc 不自托管）。定位落 [aggregators.md](aggregators.md) 谱系里 **openalex/s2 那一档（enrich/补充），非 crossref/dblp（ENUMERATE 主干）**。
- **决策**：**Phase 5 不建独立 `repec` pull adapter**；降级为**可选 enrich 通道候选**，独家增值项挂 **Phase 6 订阅 DSL 富化**评估。
- **理由（三点）**：
  1. **DOI 化系列与 crossref/openalex 重叠增量≈0**（repec.md §5 [LIVE]）：NBER 前缀 10.3386 归 NBER、在 crossref；同 WP 在 openalex（`W4323309095`，`ids={openalex,doi}`，无 repec 键、按 DOI 去重）。凡 DOI 化内容经既有主干即全覆盖。本项目 Phase 5 目标（SSRN/NBER/AEA/Econometric Society）多为 DOI 化或有专源。
  2. **门控与维护成本**（repec.md §3 [LIVE]）：RePEc API **email 门控**（致信取 access code、无搜索、非批量、保留限流权）；OAI-PMH 官方**自注 "sometimes flaky"**；官方强烈不建议爬 HTML（隐私红线"Email addresses are released under no circumstances"）。取用须走 bulk（FTP/Rsync/OAI ReDIF）、零 HTML 爬——建设/维护成本高而主干价值冗余。
  3. **独家增值属 enrich 性质**（repec.md §5④⑤ [LIVE]）：① **JEL 分类**（`nbr:nberwo:35506`→D1/J13/J15，crossref/openalex/nber.org **三路皆缺**，经济学检索核心维度、Phase 6 DSL 高价值过滤键）；② **wp↔published 版本关联**（`nbr:nberwo:3210`→"Published in" Oxford Economic Papers，服务 D-007，crossref/openalex 无此策展）；③ 非 DOI 的 WP 长尾（2250+ 机构 archive）。三者均 **enrich 性质、非全文/非目标刊 ENUMERATE 主干** → 挂 **Phase 6** 评估。
- **定位建议（若未来纳入）**：`role: aggregator-enrich`（沿 aggregators.md openalex/s2 机制，§5.3）——**capabilities 不声明 ENUMERATE/SEARCH/FETCH**；duck-typed `enrich_batch(dois)->list[PaperStub]` + `crawler enrich --source repec` 驱动；产 `(repec, handle)` identifier（`RePEc:{archive}:{series}:{id}`，仅 RePEc 内唯一、**非跨源合并锚点**——跨源仍靠 DOI）+ JEL/versions/citec 入 `meta`；**字段级优先级低位、只补不覆盖**（补 crossref/openalex 空缺）；收割走 bulk ReDIF/OAI，零 HTML。
- **附带事实**（repec.md §6 [LIVE]）：兄弟源 **NBER/CEPR 在 RePEc**（经 RePEc 取其书目与直建 nber adapter / CEPR 元数据面**重复建设**）；**SSRN 不在 RePEc**（Elsevier 商业源、442KB archives 全表无 "ssrn"——SSRN 覆盖只能靠 `ssrn` 专源，RePEc 补不了）→ 进一步削弱独立 adapter 必要性。handle↔DOI **无内建映射**（NBER 条目页不显 DOI，须外部 crossref join）。
- **影响**：development-plan Phase 5 `repec` 由"adapter"注记为 **"enrich 通道候选（R0c：主枚举/全文与 crossref/openalex 高度重叠→降级；独家增值＝JEL + wp↔published 版本关联，挂 Phase 6 DSL）"**；catalog 若有 repec 行→`role: aggregator-enrich`/`fulltext: none(links out)`/`enrich_fields: [jel, versions, citec]`。**建议排序：SSRN/NBER 专源优先落地 > RePEc enrich（挂 Phase 6）**。
- **触发条件（未来纳入）**：项目 venue 清单扩张到"非 DOI 经济学 WP series 长尾"时，以 bulk ReDIF/OAI enrich 通道实现（实现前 live 复核 OAI endpoint 活性与 FTP 结构）。
- **[PENDING·实现期]**（不阻塞本裁决）：OAI-PMH endpoint live 活性与 flaky 程度；非 DOI WP 长尾规模量级；CitEc API live 形态/配额；JEL 历史覆盖率（近年 WP 有、1989 无，enrich 价值随年代衰减）。

### D-028 草案 · ECMA 年代分段路由原则（10.3982 非全前缀路由 → wiley 侧联动修正）

- 状态：**proposed（草案）** · 日期：2026-07-24 · 依据：[research/site-survey/econometric-society.md](../../research/site-survey/econometric-society.md)（[LIVE] 2026-07-24 R0c，26 请求）
- **背景**：既有 wiley.md §1/§2 与 `wiley/parse.py` 把 `10.3982` 列为 wiley 的 enumerate/resolve 路由前缀（`_WILEY_DOI_PREFIXES` 含 `10.3982/`、`is_wiley_doi` 裸前缀甄别）。R0c 实测证伪：`prefixes/10.3982` → owner=**The Econometric Society**（crossref member 2359），**ECMA/TE/QE 三刊共用此前缀、仅 DOI 后缀（ECTA/TE/QE）区分**——裸前缀 `10.3982→wiley` 会把 TE/QE（econsoc OA）**误路由到 wiley**。且 ECMA 已**前向迁移**：新刊自营 econometricsociety.org（2026 DOI 实测 200 + CC BY 4.0）、过刊留 Wiley（2015 DOI→doi.wiley.com 403 CF）、pre-DOI 留 JSTOR。
- **决策**：
  1. **`10.3982` 前缀归 Econometric Society，非 Wiley；裸前缀路由作废**。正确路由键 = **venue(ISSN) + DOI 后缀（`ECTA` vs `TE`/`QE`）+ 年代/域名**，绝非裸前缀。
  2. **ECMA fulltext 三段路由**：当前段→`econsoc`（OA，econometricsociety.org 自营）；过刊段→`wiley`（token 档，doi.wiley.com，~2010–切换点）；pre-DOI 段（10.2307/JSTOR，<2010）→**界外**（tier T3 暂缓）。**TE/QE 全程 econsoc（OA）不分段**。
  3. **分段判定法取方向 a（运行时 per-DOI 域名判归属）**：resolve 时以 DOI 实际落地域名（`doi.org` HEAD `-L` 实时终点，权威）判归属——`econometricsociety.org`=econsoc、`doi.wiley.com`=wiley、`jstor`=界外；crossref `resource.primary.URL` 域名作 pre-filter 提示（**但有陈旧风险**：QE crossref link 仍留遗留 Wiley link——权威信号取实时落地非 crossref 登记）。方向 b（年份粗分）作快速 pre-filter、边界年 [UNRESOLVED] 实现期二分核实。论证详见 §3.3（resolve 本网络绑定→域名判归属边际零成本；自校正随前向迁移；避开未定切换日）。
- **wiley 侧联动修正范围**（本次 D3b 段③已改文档层，src 层留实现期）：
  - **文档**：wiley.md §1/§2 去除裸 `10.3982` 路由键、改注"仅 ECMA 过刊段 DOI 区间（分段见 econsoc.md §3.3/本草案），非全前缀路由"+ 迁移注记（2026-07-24，依据 R0c）；frontmatter `updated` → 2026-07-24（**本次段③已落**）。
  - **代码（实现期卡，本次只报告不改）**：`src/paper_crawler/adapters/wiley/parse.py` `_WILEY_DOI_PREFIXES` 收窄——`10.3982/` **不能裸前缀命中**；`is_wiley_doi` 需加"DOI 后缀=ECTA + 域名/年代=过刊段"复合判别（避免吞掉 TE/QE 与当前 ECMA）。`wiley/adapter.py`+`wiley/__init__.py` docstring 同步。**venues/ 无 10.3982 硬编码**（grep 空、无 ecma/te/qe YAML）。
- **理由**：R0c [LIVE] 实测 = 前缀所有权（Econometric Society）+ 三刊共用 + ECMA 前向迁移三事实叠加，裸前缀路由在 TE/QE 上系统性误路由、在当前 ECMA 上系统性漏取（Wiley TDM 对自营新 DOI 大概率 no_entitlement）。
- **影响**：catalog `ecma` 行 `fulltext_source` 年代分段（econsoc 当前/wiley 过刊/jstor pre-DOI），`enumerate` 仍 crossref；wiley.md 修正（段③已落）；wiley `parse.py` 收窄（实现期）；econsoc.md §3.3 承载 ECMA 分段主设计。`economics-journals.md` catalog TE/QE 平台注记更新为"econsoc（OJS@econtheory.org/ojs + 合并前端 econometricsociety.org；qeconomics.org 证书过期停用）"。
- **[UNRESOLVED]**（不阻塞）：① 当前 ECMA 是否全刊 OA（§8 [UNRESOLVED①]，实现期 HEAD 判）；② Wiley→自营切换日（§8 [UNRESOLVED②]，方向 a 不依赖）。
