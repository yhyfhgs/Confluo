---
title: Adapter 设计 · AAAI OJS
status: implemented
owner: fable5
updated: 2026-07-26
---

# Adapter · `aaai_ojs`

> 2026-07-22 全文重写：原稿（`updated: 2026-07-20`）多处关键路径停留在"⚠ 实现期核验"（OAI 可用性、archive 分页参数、覆盖年限），且未对齐 D-018/D-019/前车之鉴清单。本稿依 [research/site-survey/aaai-ojs.md](../../research/site-survey/aaai-ojs.md)（[LIVE] 2026-07-21，20 请求实测；原始响应归档 `aaai-raw/`）逐项落地。勘察证伪/澄清原稿四处：①REST API 匿名 403 不可用（原稿未提及此路径）；②OAI-PMH 匿名可用且含 DOI/摘要/PDF 直链，应为主抓取路径；③"archive 默认只显最新届"不准确——是每页固定 25 issue、纯 Next 顺序翻页，且单届自身拆 48 个 OJS issue；④覆盖下界实测只锚定到 2019，"1980+"是 proceedings 系列史非本 OJS 实例收录史。★ 各点已由主 agent 裁决落定——见 §9 裁决记录（2026-07-22）。

## 1. 定位

- **family**: `open_access`（免费只读；无认证、无反爬——survey §7/§8 [LIVE]）
- **服务 venue（Phase 范围建议：先 `aaai` 主会）**：AAAI 学会 OJS 实例 `ojs.aaai.org` 上的出版物。同实例托管多刊（`/index.php/{CODE}/…`：AAAI / AIES / AIIDE / HCOMP / ICAPS / ICWSM / SOCS / AAAI-SS / IASEAI），**同一套 URL 模板仅替换 `{CODE}`**（survey §1 [LIVE] 已就 ICWSM 核验为同实例、同 generator）。姊妹 venue 作为复用本 adapter 的独立 venue 后续注册（先例：arxiv 按 category 切多 venue、openreview 本期仅 iclr）。
- **capabilities**: `DISCOVER | ENUMERATE | RESOLVE | FETCH`（四位）。**无 SEARCH**——冻结 `SourceAdapter` 协议无 `search()` 方法（adapter.py §2.3），先例 arxiv.md §1 / openreview.md §1；订阅命中经 enumerate 增量 + 本地过滤达成，SEARCH 位统一推迟 Phase 6。
- **元数据/全文分工**：本 adapter 同时承担元数据（OAI-PMH oai_dc）与全文 PDF（OJS galley 直链），均在 `ojs.aaai.org` 本域。
- **版权红线（AGENTS §6.5 对齐）**：AAAI About 页承认"面向全球科研社区开放获取（可读）"，但顶头声明**版权归 AAAI 全持、转载/再出版需另行许可**（survey §7 [LIVE]，逐字引用 <15 词/条）——**非 CC-BY 类开放许可，是"免费只读"**。故本 adapter 合规定位＝**个人科研用途的只读镜像抓取，不设计任何再分发功能**（与勘察自用 UA `personal research` 一致）。

## 2. 站点勘察摘要

来源：[research/site-survey/aaai-ojs.md](../../research/site-survey/aaai-ojs.md)（[LIVE] 2026-07-21 实测，20 请求）。要点：

| 事实 | 值 | 出处 |
|---|---|---|
| 平台 | OJS 3.3.0.22（`<meta generator>`）；单 nginx 本域，无 CDN 卸载 | [LIVE] §1/§4 |
| **OAI-PMH** | `https://ojs.aaai.org/index.php/{CODE}/oai` 匿名 200；`Identify`/`ListSets`/`ListRecords` 均可用；`granularity=YYYY-MM-DDThh:mm:ssZ`、`deletedRecord=persistent`、`compression=gzip/deflate` | [LIVE] §5.2 |
| oai_dc 记录 | 单条即含 `dc:title/creator*/description(摘要)/date/identifier(URL+DOI)/relation(galley)/source(期号串)/rights`；`ListRecords` 100/页 + `resumptionToken`；全库 `completeListSize=26185`（AAAI+IAAI+EAAI+各 symposium 合计） | [LIVE] §5.2/§10 |
| **REST API** | `/api/v1/issues`（带/不带参数）**一律 403** `api.403.unauthorized`——匿名不可用，需 token；本 adapter **排除该路径** | [LIVE] §5.1 |
| DOI 形态 | `10.1609/aaai.v{volume}i{issue}.{articleId}`，如 `10.1609/aaai.v40i1.36958`；AAAI 为 CrossRef 参与方，前缀 `10.1609` | [LIVE] §3 |
| PDF 路由 | `article/view/{id}/{galley}` →302→ `article/download/{id}/{galley}`（`application/pdf`）；详情页 `citation_pdf_url` 直给 download 终态 URL（可省一跳） | [LIVE] §3/§4 |
| archive 分页 | 路径段 `/index.php/{CODE}/issue/archive/{n}`（非 query string），每页固定 **25 个 issue** 倒序，翻页仅 `Next`（无页码、无跳末页）——**仅作对账辅助**，主路径不依赖 | [LIVE] §2.1 |
| 单届拆分 | AAAI-26/Vol.40 拆 **48 个 OJS issue**（Vol.40 No.1..48）；单 issue（No.1 = 子 track "Application Domains I"）94 篇/840 页；**拆分粒度逐年逐 venue 可变**（ICWSM 历史 1 issue/年，仅最新届才拆 "No."）——enumerate 不得硬编码"一年 N issue" | [LIVE] §2.3/§1 |
| Vol↔年 | Vol.40=2026（"Fortieth"，站点品牌 `AAAI-26`）、Vol.33=2019（`AAAI-19`）、**Vol.38=2024（`AAAI-24`，[LIVE] 2026-07-26 直取 `dc:source` 逐字串确认，§12 项②闭合）**；近 7 年 `Vol = 年份 − 1986`；站点用 2 位年份品牌名 `AAAI-YY`，≠ 旧稿"AAAI-38"届序号命名 | [LIVE] §2.4/§12 |
| robots | `User-agent: * / Disallow: /cache/`（全文两行）；无 `Crawl-delay`、无 sitemap；`/cache/` 与本 adapter 路径无关 | [LIVE] §7 |
| 反爬 | 无 Cloudflare、无 CAPTCHA、无 429/`Retry-After`；`OJSSID` cookie 下发但匿名读取无需携带 | [LIVE] §8 |
| 版权 | open access to read + 版权 AAAI 全持、转载需许可（非 CC-BY） | [LIVE] §7 |

## 3. 覆盖边界与"届↔OJS issue"建模（★ 核心裁决）

### 3.1 覆盖边界：`volume_map` 注册 2010+（扩容已裁决落地，2026-07-24，见 §10 ★F）

- OAI `Identify.earliestDatestamp = 2020-06-02`（[LIVE]）**不可信为"最早收录年份"**：`datestamp` 是记录入库/修改时间（样本 2021-09-12），非发表日期（同记录 `dc:date=2019-07-21`，Vol.33/AAAI-19）——曾据此确认下界 = 2019（Vol.33）（后经 2026-07-23 全库收割证伪，实际下界 2010，见下条与 §10 ★F），上界 = 当前 2026（Vol.40）。
- About 页"first published in 1980"是 AAAI proceedings **系列**史，**不等于** `ojs.aaai.org` 这个 OJS 实例把 1980–2018 也迁上来了。**[UNRESOLVED 部分闭合，LIVE 2026-07-23]**：全库 OAI 收割（research/site-survey/aaai-ojs.md §11.3）实测直接取回 **Vol.24–32（2010–2018，9 个届，5049 条活记录）**，`Vol=年份−1986` 公式验证到 Vol.24=2010 无缺口——**"2019 是下界"已被证伪**；已确认下界前移至 **2010（Vol.24）**，`Vol.24` 以下（1980s–2009）未被 100% 穷尽排除（收割止于 89.3%，未及验证是否存在更小卷号），但间接证据（跨度近全量的已扫窗口内无 Vol.24 以下出现、线性关系连续 17 届无异常）倾向支持 Vol.24/2010 即本 OJS 实例真实下界。volume_map 已扩容登记 2010–2026（17 个届，2026-07-24 裁决落地，见 §10 ★F）；D-012（DBLP `conf/aaai` 为历史主干 + VenueEra + Wayback 死链兜底）覆盖范围相应收窄至 <2010。
- **实现期精确核实法（省请求）**：OAI 全量收割后按 `dc:date` 取最小值 —— 比翻 HTML archive（Next-only 无跳页、翻到最早耗大量请求）省得多（survey §6）。

### 3.2 Issue 建模：★A 届/年聚合 vs OJS issue（方案对比 + 建议）

冻结 `IssueRef`（types.py）= `(venue_id, volume, number, year, label, pub_date, paper_count_claimed)`；design/05 §1 幂等键**两种合法形态**：`(venue, volume, issue)` 或 `(venue, year)`。两方案：

| | **方案 B（建议）：Issue = 届/年聚合** | 方案 A：Issue = OJS issue |
|---|---|---|
| 一届产出 | 1 条 IssueRef（Vol.40=2026） | 48 条 IssueRef（Vol.40 No.1..48） |
| 幂等键 | `(venue, year)` | `(venue, volume, issue)` |
| discover | **零网络**（volume_map: year→volume） | **需网络**（walk archive 才知有几个 issue、拿 issue-view-id；届内 issue 数不可预知） |
| enumerate 天然路径 | **OAI 收割**（届内不再细分，与 arxiv 月度桶同为"收割型"） | **HTML issue TOC**（`issue/view/{id}` 逐 issue） |
| timeline 显示 | 紧凑（1 行/届） | 冗长（48 行/届） |
| `pull --year 2026` | year 列直命中 | year 列命中 48 个 issue，扇出 |
| `paper_count_claimed` | 全届口径 | 单 issue 口径 |

**建议方案 B（Issue = 届/年聚合）**，理由：①与勘察确立的"OAI 主路径、HTML 仅对账辅助"核心裁决自洽——OAI 收割本就是届/库级、不按 OJS issue 细分（见 §3.3 datestamp 关键点）；②discover 零网络（arxiv/openreview/pmlr 一致的形态偏好）；③`(venue, year)` 是 design/05 §1 明列的合法幂等键；④timeline 紧凑、`--year` 语义直白。**代价**：单届 48 个 OJS issue 的"No.M"降为 per-paper 内部信息（存 `meta`），非 IssueRef 维度。
若主 agent 反而优先"按 OJS issue 精细枚举/断点/篇数对账"，则翻到方案 A——enumerate 路径随之翻转为 HTML issue TOC、discover 变为网络操作、OAI 降为 bulk 预取，是自洽但相反的设计。

**IssueRef 字段分解（定死，方案 B）**：
- `volume`：裸数字串 `'40'`（一届＝一卷；也可由 DOI `v40i1` 反解，与 volume_map 冗余校验）；
- `number`：恒 `None`（OJS "No.M" 子 issue 不建模为 IssueRef 维度）；
- `year`：`int`（2026），来自 `quirks.volume_map` 的 key ——`--year`/`--volume` selector 的生效字段；
- `label`：`f'AAAI-{year%100:02d}'`（站点品牌名如 `'AAAI-26'`，人读友好；**与"第 N 届"序号刻意区分**，survey §2.4）；
- `pub_date`：`None`（discover 零网络，volume_map 无日期）；
- `paper_count_claimed`：`None`（volume_map 无篇数权威口径——先例 arxiv"留空"；enumerate 以实收数回填）。

### 3.3 identifier：★B 产 `scheme='doi'`（与 R3 先例的关系）

**建议 `identifiers = (('doi', <DOI 小写规范串>),)`**，即以 AAAI DOI 为唯一强合并锚点。

- **归一规则（定死）**：value = `10.1609/aaai.v{V}i{I}.{articleId}` 精确形态，**统一小写**（DOI 大小写不敏感，小写化保证 `PRIMARY KEY(scheme,value)` 稳定），**不剥前缀、不改分隔符**。从 oai_dc 的两个 `dc:identifier` 中按 `10.1609/` 前缀（或 DOI 正则）择出 DOI，另一个 `https://…/article/view/{id}` 为 landing URL。
- **与 R3 先例的关系（关键说理）**：arxiv/openreview 的 R3 裁决（doi/arxiv 线索入 `meta` 不产 identifier）针对的是**指向"另一版本/另一来源"的跨源线索**（arxiv 记录里的期刊 DOI 指向别处刊发版、openreview content 里的 arxiv id 指向 arXiv 副本）——产 identifier 会在 Phase 2 就误触发跨版本强合并（D-007 规定预印本↔刊发版不自动合并，走 `preprint_of`）。**AAAI DOI 性质不同：它是本源（AAAI proceedings）为本篇本版分配的官方规范 id**，等价于 arxiv 产 `('arxiv', base_id)` 的本源 identifier，**不是跨源指针**。故产 identifier 不违反 R3、正是 R3 底层原则（产本源 id、推迟跨版本连边）的正确应用；由此形成的强合并（本篇 ↔ 另一源引用同一 `10.1609` DOI）是**正确的同一性解析**，D-007 明列"DOI 精确匹配自动合并"。且它**不会**与 arXiv 预印本误合并——预印本侧刻意把 DOI 留在 `meta`（不入 identifier 图），Phase 2 不生成 identifier 边，Phase 3 ingest 依 meta 线索建 `preprint_of`。
- **不另产 OJS 本地 id**：article id（`36958`）已内嵌于 DOI 末段，无需再产 `scheme='aaai_ojs'` identifier（单一强锚点更清晰）；article id 与 galley/PDF URL 入 `meta` 供 URL 构造。
- `meta`（键名定死，`PaperStub.meta` tuple-of-tuples）：`('pdf_url', <galley view URL，取自 dc:relation>)`（供 resolve 零网络构造）、`('ojs_article_id', '36958')`；可选 `('ojs_source', <dc:source 期号串>)` 供对账。**摘要/作者不入 meta**（走 PaperStub 一级字段 `abstract`/`authors`）。

## 4. 各阶段实现方案

- **discover_timeline**（零网络）：读 `quirks.volume_map`（`dict[year→volume]`，覆盖已确认的 2010→24 … 2026→40，[LIVE] 2 点 + [LIVE-推断] 中间年 `Vol=年−1986`；早于 2010 不登记＝界外），逐条产出 §3.2 定死字段的 IssueRef。`since`（可选下界，'YYYY' 前缀）晚于 volume_map 最小年时收窄起点（增量发现）。**volume_map 是 D-019 锚点表的同源数据**（§7），新届/联合出版异常年（1981/85/89/95/2001/03/09 与 IJCAI 联合，Vol 号非线性——survey §2.4）由显式表项兜底，不靠公式。
- **enumerate_issue**（OAI-PMH 收割）：
  - **协议**：`GET {oai_base}?verb=ListRecords&metadataPrefix=oai_dc`（+ `resumptionToken` 翻页 100/页），`oai_base = https://ojs.aaai.org/index.php/{ojs_code}/oai`（`ojs_code` 来自 `quirks.ojs_code`，默认 `venue.id.upper()`）。
  - **客户端过滤 = DOI 卷号**：保留 DOI 解析出 `v{V}` == `issue.volume` 的记录（`dc:source` "Vol. N No. M" 作二次校验）。这是 arxiv"按 primary_category 客户端过滤"的同构落点——**过滤维度是 DOI-卷号，不是 OAI set**（set 过滤 ⚠ 不可靠，见下）。
  - **⚠ 关键点：`from/until` 按 datestamp（入库时间）过滤，非发表日期**（survey §6：2019 论文 datestamp=2021）——故**无法用"发表年窗口"选出一届**，membership 判据是 DOI-卷号过滤而非日期窗。**枚举策略（★A 附属已裁决，2026-07-22 复审后正文同步）——零接口变更，先例 arxiv 方案 A**：①**历史回填 = 一次全库收割**（一趟 262 页级收割按 DOI 卷号 partition 落盘所有届，pipeline upsert 去重；~262 请求 @30rpm ≈9 分钟可接受）；②**当前届增量 = 对当前届 IssueRef 的重复 `enumerate_issue`**——adapter 内部以**固定回看窗**（`from=<今日−回看天数>`，adapter 常量、非持久化 watermark）做全库 datestamp 窗收割 + DOI 卷号过滤出属于该届的新增记录；去重由 `identifier('doi')` 主键天然保证。**enumerate_issue 不新增形参、不依赖 subscription 表**（与 arxiv"当月桶+整窗+回看"完全同构）。③历史旧届按需 `pull` = 命中已入库 DB（design/05 新鲜度跳过）；**HTML issue-TOC 兜底路径已否决**（单路径原则，见文末裁决记录 ★A 附属）。
  - **"一次全库收割"的落地机制：跨卷分区缓存（2026-07-26 补齐，审计 S1-P1）**。上条①说的"一趟"是**跨所有历史届共享的一趟**，但冻结的 `enumerate_issue(venue, issue)` 一次只被问一个届——首版实现照字面逐届各发一趟全库收割，于是 16 个历史届 = 16 × 262 页 ≈ 4200 请求/~140 分钟，与本条承诺相悖（[post-phase5-audit §3 S1-P1](../../reports/2026-07-24-post-phase5-audit.md)）。修复：**首个历史届触发单趟全库收割，边流式产出目标卷、边把其余已注册历史卷就地 partition 进实例内存缓存；其余历史届零请求命中缓存**（key=`(venue_id, oai_base)`，姊妹刊互不串味）。语义护栏四条：①**当前届永不读写缓存**（恒走回看窗，新鲜度优先）；②缓存只在收割**自然跑完**时发布（调用方提前 break 不留残缺分区）；③收割后才登记的新卷查无此键 → 退回真收割，不静默产空序列；④记录数触顶 `_BACKFILL_CACHE_MAX_RECORDS`（50k，≈全库活记录 22.4k 的 2×）→ WARN 事件 + 关缓存回退逐卷收割（响亮降级；缓存是纯性能设施，关掉只慢不错）。缓存**实例内存态、不落盘、不跨进程**——一次 CLI 进程内有效。
  - **⚠ 为何不用"按卷切日期窗"分区（已否决，理由入档以免重蹈）**：`from/until` 过滤 `datestamp` 而非发表日（本节 ⚠ 关键点），survey §11.2 实测 Vol.26 的 383 条里 362 条 `dc:date` 因批量勘误落在 2021；且 `datestamp` 会被站点侧再编辑改写——"今天正确的窗"明天就**静默少收**。故历史届不存在安全的日期窗，单趟全库 + 跨卷 partition 是唯一既省请求又不漏收的路径。
  - **字段映射（每记录→PaperStub）**：`title=dc:title`、`abstract=dc:description`、`authors=(dc:creator, …)`、`year=int(dc:date[:4])`、`pub_date=dc:date`、`identifiers=(('doi', doi_lower),)`、`meta` 见 §3.3。
  - **空态**：OAI `noRecordsMatch` = **非错误**（空记录序列正常完成——arxiv 先例，parse.py 已落地）；空届/空卷同理。
  - **墓碑**：`deletedRecord=persistent`（[LIVE]），`<header status="deleted">` 记录跳过并计数 → obslog debug（arxiv `OaiListPage.skipped_tombstones` 先例，复用）。
  - **set 过滤：非全局不可靠，须逐 setSpec 探测（[LIVE] 2026-07-26 §12 项④闭合，细化原判断）**：`ListSets` 列出的 setSpec **并非全部不可查询**——`set=AAAI:2023-11` 单独查仍复现 `noRecordsMatch`（2026-07-26 重测，与 survey §5.2 原发现一致、非瞬时），但 `set=AAAI:2024-149`（同为 `AAAI:{year}-{trackId}` 数字型）**单独查返回 16 条正确记录**（`ListIdentifiers` 全部标 `setSpec=AAAI:2024-149`）。**结论**：`set=` 过滤机制本身工作正常，`AAAI:2023-11` 的 `noRecordsMatch` 是该 setSpec 特定的（该 track 在 2023 年可能确实零挂载记录/已改名改号，非 API 层级/命名规范性的系统性故障）——**原"不假设 ListSets 里的名字都能拿来单独过滤"的保守结论依然成立且是唯一稳妥做法**：实现期若要用 set，仍须先 `ListIdentifiers` 逐个探测目标 setSpec 是否真的挂记录，不能仅凭 `ListSets` 出现过而假设可查询。
  - **IAAI/EAAI 归属**：全库 26185 条含 AAAI 主会 + IAAI + EAAI + symposium；`dc:source` 形如 "…AAAI-19, IAAI-19, EAAI-20…"。**`[UNRESOLVED] 已闭合，LIVE 2026-07-23`**（research/site-survey/aaai-ojs.md §11.4，17 个届 `dc:source` issue 描述穷尽枚举）：IAAI/EAAI **确实占用独立于主赛道的 issue 号**，但编排方式随时代 4 次演变——①2010–2014（Vol.24–28）三分体制：No.1=AAAI/No.2=IAAI/No.3=EAAI 各自独立；②2015–2017（Vol.29–31）二分体制：仅 No.2=IAAI 独立，EAAI 并入 No.1；③2018–2019（Vol.32–33）归并体制：全部并入同一 issue 号，个体记录不可由 issue 号区分；④2020–2025（Vol.34–39，现行）多 Track + 尾部合并 issue：主赛道拆 10–25 个"Technical Tracks N"，末尾追加 1 个专属 issue 打包 IAAI+EAAI+Special+Student（尾号逐年后移，Vol.39→No.28）。**主会 venue 当前不排除 IAAI/EAAI**（enumerate_issue 的 DOI-卷号过滤本就不区分 track，两者天然随卷号一并收割入库）——若未来要单独排除/标注，需在 §3.3 `meta` 新增 track 归属字段（识别信号：`dc:source` issue 描述文本含 "IAAI"/"EAAI"子串，比 OAI `<header><setSpec>` 更可靠——已实测 576 条 issue 描述含 IAAI/EAAI 但 setSpec 未打标签的反例）。
- **resolve_assets**（零网络）：读 `paper.meta['pdf_url']`（enumerate 从 `dc:relation` 捕获的 galley view URL）→ 路径 `/view/`→`/download/` 直接构造 download 终态 URL（survey §4：view 302→download，预换可省一跳）→ 单个 `AssetPlan(kind=pdf, url_strategy=direct, auth_needed=none, version=None)`。landing = `article/view/{articleId}`（不物化为 asset，与 arxiv 一致）。**⚠ 多 galley 消歧（复审后修订——resolve 保持真零网络）**：个别文章挂第二 galley（Video/Poster/Slides），oai_dc `dc:relation` 无类型标注——取首个 relation（通常为 PDF）+ 记录级 `dc:format=application/pdf` 佐证；**消歧失败的偶发非 PDF 由 pipeline `%PDF` 魔数校验拦截 → `integrity` 路由（fails-safe，不牵连批次）**。详情页 `citation_pdf_url` 仅作 fixture 对账参考，**不作运行时兜底**（否则违反 resolve 零网络断言——pmlr-B3 同款教训）。实现期核验 relation 顺序（⚠）。
- **fetch_asset**（流式）：`HttpClient.stream` → `io.write_stream`；`%PDF` 权威校验归 pipeline（冻结分工）。**adapter 职责**：把"PDF url 却回了 HTML 页"嗅探为 `GONE`——覆盖两态：撤稿/不存在，以及**未发布 issue/galley 的 302→`/login` 落地页**（survey §9，见 §6）。复用 arxiv `_gone_guarded_stream` 的 HTML 首字节嗅探模式。
- **healthcheck**：OAI `Identify` 200（存活基线，匿名、零 token）+ **3 条 GetRecord canary**（§7）比对规整化 `dc:title` + DOI-卷号双字段。REST API 不参与（匿名 403 非健康信号）。

**OAI 解析器复用评估（★C，涉及已实现 arxiv 代码，需主 agent 定夺）**：`src/paper_crawler/adapters/arxiv/parse.py` 的 OAI 解析分两层——**信封层**（`_raise_if_oai_error` + `_OAI_ERROR_CLASS` 错误码表、`_iter_oai_records` 的 record/墓碑遍历、`_resumption_token_from`、`noRecordsMatch=非错误`、`OaiListPage` 形状）与**元数据体层**（`_parse_oai_arxiv_element`，绑定 arXiv 私有 schema `http://arxiv.org/OAI/arXiv/`）。AAAI 用 `oai_dc`（`http://www.openarchives.org/OAI/2.0/oai_dc/` + `http://purl.org/dc/elements/1.1/`），**信封层 100% 同构可复用**（错误码表逐条相同：`badResumptionToken→TRANSIENT`、`badArgument/badVerb/cannotDisseminateFormat→CONFIG`、`idDoesNotExist→GONE`、`noRecordsMatch=非错误`），**仅体层需新写 oai_dc 解析器**。**建议：把信封层泛化为共享 OAI-PMH 核**（如 `adapters/_oai/envelope.py`，参数化"元素→中间记录"回调），arxiv 与 aaai 各自提供体层解析器——避免错误码表/墓碑逻辑重复漂移。**约束**：arxiv 已 implemented，此泛化须为**无回归重构**（arxiv 现有 T4 测试为守门）；若主 agent 不愿动已实现代码，退路是 aaai 独立复制信封逻辑（~50 行）并在文档标注"待日后合并"的重复。

## 5. 限速与礼貌

| domain | 速率 | 依据 |
|---|---|---|
| ojs.aaai.org | **1 req/2s（30 rpm），并发 1** | NFR-4 无站点声明保守默认；survey §7 robots 无 `Crawl-delay`、§8 无 `Retry-After`/无反爬 [LIVE] 2026-07-21；OJS 单 nginx 本域承载力有限，克制并发 |

- `default_rate.source_note` 引 survey §7/§8 + NFR-4；UA 按 D-014（`PaperCrawler/<ver> (personal research; mailto:<email>)`，由 HttpClient 调用方注入，本 adapter 不读 config）。
- **robots 合规（实测结论，非"待复核"）**：`/robots.txt` = `User-agent: * / Disallow: /cache/`（仅两行，[LIVE] §7）——`/cache/` 与本 adapter 的 `/index.php/…/oai`、`/issue/…`、`/article/…` 路径无交集，**无 Disallow 命中**；无 `Crawl-delay` 可循，故取上表保守默认。
- **批量走 OAI 收割**（100/页 + resumptionToken）而非逐 issue/逐篇 HTML 高频小请求；archive HTML 翻页仅在对账/兜底时用。
- **版权/ToS 姿态**：只读镜像、个人科研用途、**不再分发**（§1 红线，AGENTS §6.5）；诚实 UA；不申请/不使用 REST API token（超出匿名可读范围，且本 adapter 无此需求）。

## 6. 失败模式映射

| 站点现象 | error_class | 说明 |
|---|---|---|
| OAI `noRecordsMatch` | —（**非错误**） | 空窗口/空届/空卷的合法响应，解析为空序列正常完成（arxiv 先例；误归 parse 会使空届假故障） |
| OAI `badResumptionToken` | `transient` | token 过期，任务级重跑天然重建收割窗口（arxiv 先例） |
| OAI `badArgument`/`badVerb`/`cannotDisseminateFormat` | `config` | 我方请求构造缺陷，响亮停机（与 http.py 4xx→CONFIG 平行，arxiv 先例） |
| OAI `idDoesNotExist` | `gone` | 单 id（GetRecord canary）未命中场景 |
| article id 确定不存在（`/article/view/999999999`） | `gone` | HTTP 404，body `404 Not Found`（survey §9 [LIVE]） |
| **issue/article/galley 302→`/login`（未发布/占位 issue）** | `no_entitlement`（detail 注 `login-gated`；**★D 裁决定稿，2026-07-22 复审后正文同步**） | survey §9 [LIVE]：非 404 而是跳登录页——"存在但不可匿名取"语义上是权限门非消失（保留 design/05 no_entitlement 的 OA fallback 升级路径）。**主路径 OAI 只列已发布记录，天然不遇此态**；仅陈旧 galley id 等罕见路径触发，由 adapter 嗅探重定向落点/登录页 HTML 判定，不重试 |
| PDF url 回 HTML（撤稿/合并/登录页） | `gone` | adapter 首字节嗅探（复用 arxiv `_gone_guarded_stream`）；`%PDF` 权威校验归 pipeline |
| oai_dc XML 语法错/记录缺 `dc:title`/`dc:identifier` 无 DOI | `parse` | canary 标红；截断响应等（arxiv `_fromstring`→PARSE 先例） |
| 连接超时/5xx | `transient` | HttpClient 统一映射 |
| REST API 403 | （不触达） | 本 adapter 不请求 REST API（§2/§4），无此路径 |

**已知冻结限制（本期承认，收紧随 Phase 4 走接口仲裁；arxiv.md §5 / openreview.md §6 同批先例）**：①`FetchResult` 无 `http_status` 字段，`fetch_log.http_status` 本期恒 NULL；②metadata 阶段请求（OAI 收割/HTML 对账页）不入 `FetchLog`——其限速审计证据为 obslog jsonl（HttpClient 每请求 debug 事件：domain/脱敏 url/status/elapsed_ms）；③`Retry-After` 不驱动重试调度（仅观测；本站实测无此头）。

## 7. Fixtures 与测试

- **T1 单元**（与网络解耦，bytes 进 / 中间记录出）：DOI 解析/归一矩阵（`v{V}i{I}.{id}` 抽卷号、小写化、非法形态拒绝）；oai_dc 体层解析器（title/creator*/description/date/identifier 双值择 DOI/relation→pdf_url）；OAI 信封层（resumptionToken 翻页、`noRecordsMatch`、墓碑跳过计数、错误码表——若 ★C 泛化则测共享核）；volume_map→IssueRef 字段分解（含 `since` 收窄、界外年拒绝）；view→download URL 构造。
- **T3 fixture（覆盖 §6 全部 error_class，test-plan §6 强制；录制物为公开元数据，录制前剔请求头/cookie；难录形态合成并标注）**：①OAI `ListRecords` oai_dc 正常页（含 `resumptionToken`、≥1 条多 `dc:creator`、≥1 条带次 galley relation）②分页续页（`resumptionToken` 消费到无）③`noRecordsMatch` 空页 → 非错误 ④`badResumptionToken` → `transient` ⑤`badArgument` → `config` ⑥`idDoesNotExist`（GetRecord）→ `gone` ⑦article 404 页 → `gone` ⑧issue 302→`/login` 落地 HTML → `no_entitlement`（login-gated，★D 定稿口径）⑨截断/畸形 XML → `parse` ⑩HTML issue TOC 正常页（对账/兜底路径：`.obj_article_summary`/`.title a`[含 articleId]/`.authors`/`.pages`/`a.obj_galley_link.pdf` **按 class 过滤**）⑪article 详情页（`DC.*` + `citation_*` 双套 meta，`citation_pdf_url` 为 resolve 兜底源）。
- **T4 集成（MockTransport 全链路）**：discover→enumerate→resolve，DOI-卷号过滤计数断言；全库收割按卷 partition 落盘正确；当前届重复 enumerate（固定回看窗 + 卷号过滤）无重复无遗漏（去重由 `identifier('doi')` 主键天然保证——重叠窗口不产重复行）；墓碑跳过计数经 obslog 暴露。
- **T5 在线冒烟（预算 ≤10 请求）**：`Identify` 1 + 单届 OAI 首页 1 + resumptionToken 续页 1 + 单篇 PDF fetch 1 + article 404/issue-login 各 1 语义核对 + robots 复核 1；`MAX_REAL_REQUESTS` 设限。
- **canary 样本（抗 flake，arxiv/openreview 先例）**：3 条跨届固定 GetRecord（如 Vol.33/2019 实测 `oai:ojs.aaai.org:article/3745`、Vol.37/2023、Vol.40/2026 各 1；后两为合成占位，⚠ T5 在线冒烟以实测替换）比对**规整化 `dc:title` + DOI-卷号双字段**（非原串精确匹配——抗折行/微调）；另 1 条基线：`Identify.repositoryName` 含 "AAAI"（无 token 也可跑）。
- **验收（DoD + D-019 锚点，★E）**：**AAAI 无专属 AC-2.x 条目**（AC-2.1/2.2=iclr、2.3=arxiv、2.4=cvpr、2.5=ACL、2.6=ACM deferred——AAAI 不在其中，[核对 acceptance-criteria.md]）。故本 adapter 验收走**通用 DoD 口径**（D-020 收尾原则"AC-2.1~2.5 + 各 adapter DoD"）：①`timeline aaai` 覆盖 volume_map 全区间且与锚点表全等；②`pull aaai --year <Y> --limit N` 落盘 N 个文件、每个魔数=`%PDF` 且 >10KB、DB↔文件对账一致。**D-019 锚点快照表** `tests/fixtures/aaai/dblp-aaai-anchor.json`——逐年 `{year, volume, oai_count|null, dblp_slug:'conf/aaai', note}`；生成程序（实现期）＝OAI 全库收割按卷计数 + **人工对照 DBLP `conf/aaai` TOC 核准**（UPDATE_GOLDEN 纪律、records 留痕）；特例（<2010 界外标 null、IAAI/EAAI 归属口径、联合出版异常年）表内显式标注；验收判定＝系统输出与锚点表全等。**规模锚（survey §10）**：Vol.40=48 issue、No.1=94 篇/840 页、全库 completeListSize=26185（仅量级参考，不作精确判据）。★E 若主 agent 要为 AAAI 设专属 AC-2.x，属 acceptance-criteria.md 联动变更（非本文单文件可闭合，先例 pmlr 评审）。
- **验收关联**：FR-02（时间轴发现）/FR-04（清单枚举·篇数对账）/FR-06（开放源下载）经 acceptance-criteria.md 末尾 FR→AC 覆盖表闭环；测试类型定义见 [testing/test-plan.md](../../testing/test-plan.md)。

## 8. 风险与维护

- **OAI datestamp≠发表日期**（§4 ⚠ 关键点）：是"届不可日期窗化"的根因——枚举窗口/路由策略随 ★A 一并定；canary 监控 `Identify` 存活与 oai_dc 结构。
- **跨卷分区缓存的内存占用**（§4 修复项）：单趟全库回填期间，除当前届外的全部已注册历史卷 `PaperStub` 常驻内存直到进程结束——按实测 22.4k 活记录、平均含摘要 ~2KB/条估，量级 ~50MB。硬顶 `_BACKFILL_CACHE_MAX_RECORDS=50000` 是站点规模异常增长时的响亮泄压阀（超顶 → WARN + 关缓存回退逐卷收割），不是常态路径；若日后全库规模逼近该值，应重评"分区落磁盘/直接改用一次多届 upsert"而非简单抬高常量。
- **单届拆分粒度逐年逐 venue 可变**（AAAI 48 issue vs ICWSM 1 issue/年，最新届才拆）：方案 B 把"No.M"降为 per-paper meta 已规避硬编码风险；姊妹 venue 复用本 adapter 时各自 volume_map。
- **OJS 平台升级改 URL/schema**：fixture + canary 覆盖；oai_dc 是标准协议，较 HTML 选择器稳。
- **覆盖下界与早年归属**（§3.1，`[LIVE 2026-07-23]` 已核实下界＝2010/Vol.24，非 2019）：全库收割已取代"取最小值精确核实"的原计划——直接实测 `dc:date` 最小值为 2010-07-03（Vol.24）。`volume_map` 已扩容纳入 2010–2018（2026-07-24 裁决落地，见 §10 ★F），这些届现纳入本 adapter 运行时覆盖；D-012（DBLP/Wayback）覆盖范围相应收窄至 <2010。
- **REST API 若未来开放**：本期排除（匿名 403）；如 AAAI 放开匿名 REST，重评是否作为 OAI 的补充清单源（届时走接口仲裁）。
- **★C OAI 信封泛化的回归风险**：若采纳共享核，arxiv 现有 T4 为守门；未采纳则承认 ~50 行重复，标注待合并。

## 9. 主 agent 裁决记录（2026-07-22，正文 ★ 各点就此落定）

| ★ | 裁决 | 理由 |
|---|---|---|
| ★A Issue 建模 | **方案 B：届/年聚合**（幂等键 (venue,year)，一届一 IssueRef） | discover 零网络、OAI 收割型与 arxiv 月度桶同构、timeline 紧凑；48 个 OJS issue 是站点实现细节非领域概念 |
| ★A 附属（枚举窗口/路由） | **先全库回填、后按需命中 DB**：历史回填=一次全库收割（~262 页 @30rpm ≈9 分钟，可接受）按卷号 partition 落库；当前届增量=datestamp 水位增量；旧届 pull 命中已入库数据（新鲜度跳过）。**不做 HTML issue-TOC 兜底**（保持单路径） | datestamp≠发表日使日期窗不可用；全库量级实测可控；双路径维护成本不值 |
| ★B identifier | **产 `identifier('doi', 小写规范串)`**。同批沉淀通用原则：**本源官方 DOI（站点为该论文注册的 DOI）产 identifier；指向他源版本的 DOI/id 线索入 meta**——R3 先例的正确边界（arxiv 的 journal_ref/doi 属后者故入 meta） | AAAI DOI 是这篇论文自身的官方 id，Phase 3 Crossref 同 DOI 合并是强合并锚点的正用非误合并 |
| ★C OAI 信封层 | **泛化为共享核**（如 adapters/_oai.py：错误码表/墓碑/resumptionToken/信封遍历参数化；arxiv parse.py 改薄封装）。约束：独立重构 commit 先行、arxiv 全量测试守门零回归 | 信封层 100% 同构勘察证实；复制 50 行的漂移风险大于受控重构 |
| ★D 登录跳转 | **`no_entitlement`**（否决 gone） | "存在但不可匿名取"语义上是权限门非消失；保留 design/05 的 OA fallback 升级路径；主路径 OAI 不遇此态，兜底行罕见 |
| ★E 验收口径 | **通用 DoD + D-019 锚点表**，不设专属 AC-2.x | 与 neurips/pmlr 同类；acceptance-criteria 不因单 adapter 扩条目 |

## 10. 全库收割实测发现与裁决记录（2026-07-23，独立预算线任务）

> Phase 2 检查单 #3 → Phase 3 报告 §6 检查单 #8（跨 3 Phase 清账）。234/262 页（89.3%，
> 22352 条活记录）全库 OAI 收割，方法与完整台账见
> [research/site-survey/aaai-ojs.md §11](../../research/site-survey/aaai-ojs.md#11-全库收割统计-live-2026-07-23)。
> §3.1/§4 的 `[UNRESOLVED]` 标注已按下表结论就地更新；本节汇总**需要主 agent 裁决的架构性
> 后续事项**（本次任务授权范围＝统计与文档，不含裁决本身，AGENTS.md §7）。

**★F 覆盖下界扩容 —— 已裁决（2026-07-24，controller）：扩容纳入 2010-2018，依据 §11 收割实测**：
实测确认 `ojs.aaai.org` 本 OJS 实例上 **Vol.24–32（2010–2018，9 个届，5049 条活记录）与
Vol.33–40 同构可收割**（同一 OAI 端点、同一 DOI 形态 `10.1609/aaai.v{V}i{I}.{id}`、同一
`Vol=年份−1986` 线性关系）。裁决落地内容：
- `venues/cs_ai/aaai.yaml` 的 `quirks.volume_map` 已从 8 项扩至 17 项（新增
  `2010: 24 … 2018: 32`，与本节实测值逐条一致）；头部注释同步改述覆盖下界＝2010；
- `tests/fixtures/aaai/dblp-aaai-anchor.json` 已新增对应 9 行（`dblp_slug` 形如
  `conf/aaai/aaai2010`，`oai_count` 取自本节 §11.2 实测活记录数），D-019 锚点表与
  venue yaml 的 volume_map 逐条一致性由 `test_dblp_aaai_anchor_years_match_venue_yaml_volume_map`
  继续守门；
- D-012（DBLP 历史主干 + Wayback 死链兜底）覆盖范围相应收窄至 <2010（1980s–2009，
  §3.1 未 100% 穷尽排除但证据倾向不在本实例）；
- 早期 5 个届（Vol.24–28）的 issue 结构（§4 体制①，固定 3-issue：AAAI/IAAI/EAAI 各一）比
  近年更简单规整，`resolve_assets`/`enumerate_issue` 现有实现**无需改动**即兼容（DOI-卷号
  过滤与 pdf_url 构造逻辑与年代无关）——本次扩容为纯 config/fixture 变更，零 adapter 代码改动。

**★G IAAI/EAAI track 标注（待裁决，优先级较低）**：§4 结论已确认 IAAI/EAAI 在 14/17 个届
占独立 issue 号，可靠识别信号是 `dc:source` issue 描述文本（非 `setSpec`）。若未来产品需求
要求区分/过滤/单独标注 track 归属（现状：不区分，全部随卷号收割），需在 §3.3 `meta` 新增字段
（如 `('track', 'iaai'|'eaai'|'main')`，从 `dc:source` 正则抽取）并补测试；本次不产生此实现，
仅记录信号来源供未来实现参考。

**规模注记**：AAAI-26/Vol.40 本身仍在扫描中途（No.1–24/预期 48+），其活记录数 2136 是**下限
非终值**；补完预算 ≤30 请求（见 [research/site-survey/aaai-ojs.md](../../research/site-survey/aaai-ojs.md) §11.5，非本文档章节）。

## 11. A⑥⑦ 重跑闭合（2026-07-26，Phase 6 M1-b 在线闭合批，预算 5/6 请求）

> 承接 [research/site-survey/aaai-ojs.md §12](../../research/site-survey/aaai-ojs.md#12-unresolved-专项在线核实尝试-live-2026-07-24--站点侧持续性故障blocked) 2026-07-24 的 BLOCKED 移交（`ojs.aaai.org` 应用层持续性故障，未获结论）。本次前置 1 次 `GET /robots.txt` 确认站点已恢复（200），随后按该节"移交 controller"段落的既定方法执行，5 请求内两项全部闭合。

- **项②（"AAAI-38"届序号 vs 站点 `Vol.N`/`AAAI-YY` 品牌名对应关系）——[已闭合，LIVE 2026-07-26]**：`OAI ListIdentifiers set=AAAI:2024-149` 取得 Vol.38(2024) 记录 identifier `oai:ojs.aaai.org:article/28894`，`GetRecord` 直取其 `dc:source` = `"Proceedings of the AAAI Conference on Artificial Intelligence; Vol. 38 No. 9: AAAI-24 Technical Tracks 9; 10280-10287"`——**逐字串直接确认 Vol.38↔2024↔站点品牌 `AAAI-24`**，与 `Vol=年份−1986` 公式（38=2024−1986）完全吻合。本表§2.4 已同步更新为 [LIVE]（原 `[LIVE-推断]` 转正）。
- **项④（`ListSets` setSpec vs 实际可查询 setSpec 的命名/层级差异）——[已闭合，LIVE 2026-07-26]**：`ListSets` 返回的 setSpec 既有数字型（`AAAI:{year}-{trackId}`，如 `AAAI:2023-11`/`AAAI:2024-149`）也有语义型（如 `AAAI:IAAI-DEP`）。重测 `set=AAAI:2023-11` 仍 `noRecordsMatch`（与 2026-07-24 原发现一致、可复现非瞬时故障）；但 `set=AAAI:2024-149` 单独查询**成功返回 16 条记录**（`ListIdentifiers` 响应逐条 `<setSpec>AAAI:2024-149</setSpec>` 与请求一致）。**结论**：`set=` 过滤功能本身工作正常，不存在 `ListSets`/`ListIdentifiers` 之间系统性的命名或层级不一致问题；`AAAI:2023-11` 的 `noRecordsMatch` 是该特定 setSpec 的数据/生命周期问题（该 track 编号在 2023 年可能未挂载任何记录，或已改名/改号），而非 API 设计缺陷。§3.2 现有"不假设 ListSets 名字都可单独过滤、实现期先探测"的保守建议依然是唯一稳妥做法，本次予以保留并强化措辞（见 §3.2 本次同步修正）。

**请求台账**（5/6，UA 恒 `PaperCrawler/0.1.0 (personal research; mailto:yhyfhgs@gmail.com)`，间隔 ≥2s，站点声明限速 30rpm）：

| # | 方法 | 目标 | 结果 |
|---|---|---|---|
| 1 | GET | `ojs.aaai.org/robots.txt` | 200（应用层恢复确认） |
| 2 | GET | `oai?verb=ListSets` | 200（386+ setSpec 全量，含数字型与语义型） |
| 3 | GET | `oai?verb=ListIdentifiers&set=AAAI:2024-149` | 200，16 条记录（项④正例） |
| 4 | GET | `oai?verb=GetRecord&identifier=oai:ojs.aaai.org:article/28894` | 200，`dc:source` 含 "AAAI-24"（项②闭合） |
| 5 | GET | `oai?verb=ListIdentifiers&set=AAAI:2023-11` | `noRecordsMatch`（复现，项④反例，确认非瞬时） |

第 6 请求预算未使用（两项已用 5 请求充分闭合，经济收尾）。零 PDF 下载、零登录、零表单；[research/site-survey/aaai-ojs.md](../../research/site-survey/aaai-ojs.md) §12 同步更新结论状态。
