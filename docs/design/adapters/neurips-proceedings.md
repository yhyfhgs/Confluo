---
title: Adapter 设计 · NeurIPS Proceedings
status: implemented
owner: fable5
updated: 2026-07-24
---

# Adapter · `neurips_proceedings`

> 2026-07-22 全文重写：旧稿（`updated: 2026-07-20`）多条关键断言经 [LIVE] 勘察证伪，
> 依 [research/site-survey](../../research/site-survey/) 归档的实测（26 请求，2026-07-21）逐项订正。
> **被证伪并弃用的旧稿断言**：①「早年后缀多档兼容（1987/2000/2019/2022 四档边界）」——实测**只有单一硬边界 2021→2022**（1987/1993/2019/2020/2021 五个跨度极大年份全部同属旧格式）；②「Supplemental 为 `-Supplemental-*.zip`」——实测 3 样本一律 `.pdf`，且**存在与否须从 Abstract 页判定**（1987 样本根本无 Supplemental）；③「robots ⚠ 实现期复核」——已解除，两域 `/robots.txt` 均 404（站点无 robots）；④「与 openreview 无共同强 id、只能弱匹配」——对 2022+ 成立，但 **2021 详情页内嵌 OpenReview forum 链接**（n=1，需扩样，见 §7）。
> ★ 各点已由主 agent 裁决落定——见 §8 裁决记录（2026-07-22）。

## 1. 定位

- **family**: `open_access`（全站静态、匿名可读、无认证、无防护——[LIVE] 26 请求 0 挑战门）。
- **服务 venue（Phase 2 范围：仅 `neurips`）**：NeurIPS 正式 proceedings，1987→当前全量（[LIVE] 首页 `ul.proceedings-list` 权威列出 39 届，逐年连续无缺口）。**与 OpenReview 评审版的分工**（[design/03](../../design/03-open-access-module.md) §4）：本 adapter 承担 proceedings 主源（design/03 命名 `neurips`(正式) channel）；其 OpenReview 评审数据源（design/03 命名 `neurips_openreview`）**本期推迟**，不在本文档范围（与 openreview.md §1 口径一致）。双 channel 的合并由 Phase 3 ingest 依 identifier 完成——proceedings 侧的 hash 与 OpenReview 侧的 forum id 无共同强 id（2022+），弱匹配走 candidate 队列（D-007）；**2021 例外**（详情页内嵌 forum 链接，可能提供强 id 捷径）见 §7。
- **capabilities**: `DISCOVER | ENUMERATE | RESOLVE | FETCH`（四位）。
  **无 SEARCH**：冻结 `SourceAdapter` 协议（接口冻结件 §2.3）无 `search()` 方法，Phase 2 亦无消费方；NeurIPS 无订阅增量语义（年度会议，追新经 `track` 子系统，见 §3）。SEARCH 位统一推迟（arxiv.md §1 / openreview.md §1 先例）。

## 2. 站点勘察摘要

来源：[research/site-survey](../../research/site-survey/)（[LIVE] 2026-07-21 实测，26 请求台账见勘察「合规审计」节）。要点：

| 事实 | 值 | 出处 |
|---|---|---|
| 域名 | 三镜像 `proceedings.neurips.cc` / `papers.neurips.cc` / `papers.nips.cc` 首页字节级相同（17032 B，同 `Apache/2.4.68`）、**互不重定向**（`num_redirects=0`）；`citation_pdf_url` 唯一自称 canonical＝`proceedings.neurips.cc` | [LIVE] §1 |
| 年份索引 | 首页 `ul.proceedings-list` 直出全部 **39 届（2025→1987 逆序、连续无缺）**；卷号＝`year−1987`（1987→vol 0 … 2025→vol 38），可作纯函数校验 | [LIVE] §2 |
| 年页 URL | `/paper_files/paper/{year}`（无查询参数）；`/paper_files/paper/1986`→404（下界）、`/2099`→404（未来年同一通用 404） | [LIVE] §2 |
| 单篇 hash | 32 位十六进制（形似 MD5）；路径 `/paper_files/paper/{year}/hash/{hash}-Abstract{SUFFIX}.html` | [LIVE] §3 |
| **单一后缀边界 2021→2022** | ≤2021 旧格式 `-Abstract.html`（`data-track="none"`、无 badge）；≥2022 新格式 `-Abstract-Conference.html` / `-Abstract-Datasets_and_Benchmarks.html`（`data-track` 出现、有 `span.paper-track-badge`） | [LIVE] §3/§5 |
| 列表选择器 | `ul.paper-list > li[data-track]` → `div.paper-content > a[title="paper title"][href]`（链接文字＝标题）＋`span.paper-authors`（逗号分隔作者全名）；2022+ 额外 `span.paper-track-badge` | [LIVE] §3 |
| PDF/Supplemental | ≤2021：`-Paper.pdf` / `-Supplemental.pdf`；≥2022：`-Paper-Conference.pdf`(或 `-Datasets_and_Benchmarks`) / `-Supplemental-Conference.pdf`(或 `-Datasets_and_Benchmarks`)。路径段 `/hash/`→`/file/`。**Supplemental 存在与否须从 Abstract 页判定**（1987 无 Supplemental 链接） | [LIVE] §5 |
| PDF 托管 | `proceedings.neurips.cc` 同源 Apache 直吐、`application/pdf`、`num_redirects=0`、无 CDN/WAF 头；`Content-Disposition` 给人类可读文件名（`NeurIPS-2023-…-Paper-Conference.pdf` / 早年 `NIPS-1987-…-Paper.pdf`） | [LIVE] §5 |
| robots | 两域 `/robots.txt` 均 **404**（站点无 robots.txt）；proceedings 子域无独立 ToS/版权页（footer 仅「Report an Issue」外链主会站 + 「Name Change Policy」弹窗） | [LIVE] §7 |
| 反爬 | 26 请求 **0 次** 429/403/CAPTCHA/JS challenge；无 `X-RateLimit-*`/`Retry-After`/CDN 特征头；后端 Django + Apache 静态直出 | [LIVE] §8 |
| 空态/404 | 「从未存在的年」与「未来未发布的年」**共用同一通用 404**（`<h1>Page Not Found</h1>`，23 B）；无「暂未发布」专属页 | [LIVE] §6 |
| citation_* meta | 详情页含 `citation_title/author/journal_title/volume/firstpage/lastpage/pdf_url/publication_date`；**年代差异**：1987 更稀疏（`journal_title` 无「Advances in」前缀、`volume="0"`、无 first/lastpage、`publication_date` 仅年份粒度） | [LIVE] §4 |
| Abstract 位置 | `<section class="paper-section"><h2>Abstract</h2><p class="paper-abstract"><p>…</p></p></section>`——**双层 `<p>` 包裹**（站点模板瑕疵，提取需处理） | [LIVE] §4 |

**[UNRESOLVED → 4/5 闭合 · LIVE 2026-07-24]**（Phase 5 检查单 #5 专项在线核实，证据见 site-survey §11；详情 §6/§7 各处就地闭合）：①2021 内嵌 OpenReview 链接**覆盖率**——~~n=1~~ **闭合**：8 篇跨表抽样 **8/8** 命中，普遍存在；②`Metadata.json` bulk 端点**可用年份窗**——~~边界未测~~ **闭合**：**1987–2019（含），2020 起 404**，边界 2019→2020；③详情页 Bibtex 按钮畸形 `…/{数字}-/bibtex`——~~未发请求~~ **闭合·可用**：302 短链重定向到规范 `{hash}-Bibtex.bib`（200）；④`sitemap.xml`——~~未探测~~ **闭合·不存在**：404；⑤`neurips.cc` 宣传站稳定性（**本次任务范围外，非"未解决"而是"未纳入范围"**，维持）。

## 3. 各阶段实现方案

### 3.0 数据流总览（避免「零网络」误述——前车之鉴 #5）

| 阶段 | 网络 | 说明 |
|---|---|---|
| `discover_timeline` | **零网络** | 程序生成 `[first_year .. known_through_year]` 逐年 Issue（年份连续、纯计算）；追新（新届）经 `track` 子系统，**不在本 adapter 的 discover 内**（design/08 §4；catalog「追新＝crawler track」） |
| `enumerate_issue` | **1 请求/届** | GET 年页列表，解析 `li[data-track]` |
| `resolve_assets` | **零网络** | 纯 URL 构造（hash＋year＋后缀规则）；仅产 PDF `AssetPlan` |
| `fetch_asset` | **1 请求/资产** | `HttpClient.stream` → `FetchIO.write_stream` |
| `healthcheck` | **2 请求** | GET 2021+2022 年页，跨边界 canary 双字段比对 |

### 3.1 discover_timeline（零网络）

- 逐年生成 `IssueRef`：`year ∈ [first_year .. known_through_year]`，**连续无缺**（[LIVE] §2 证实 1987→2025 逐年无缺口——与 openreview 的 2015/2016 缺届情况不同，**无需常量届表，程序生成即可**）。
  - `first_year`：`quirks.first_year`，默认 **1987**（[LIVE] §2：`/1987`→200（90 篇，现存最早）、`/1986`→404 为下界）。
  - `known_through_year`：`quirks.known_through_year`，缺省 **当前 UTC 年 − 1**（安全已发布界——NeurIPS 每年 12 月发布，故 `current−1` 恒已发布；[LIVE] 勘察于 2026-07 见首页最大届＝2025＝`current−1`，印证）。**当年届（12 月发布后）经 `track` 确认并 bump 该 quirk**（D-012 人工确认），避免把未发布当年误入 timeline（否则破坏 §6 锚点比对）。
  - `since`（可选下界，取年份）晚于 `first_year` 时收窄起点。
  - **为何程序生成而非解析首页列表**（[LIVE] §2 建议「优先解析首页 `ul.proceedings-list`」）：勘察已证实届表 **逐年连续、`vol=year−1987` 纯函数**——故程序生成与解析首页对**历史年**产出同一集合，且零网络更省（比首页解析的 1 请求还省，比旧稿逐年 200/404 探测更省）。首页列表的**独有价值**是探测「最新届何时出现」——该职责归 `track`（design/08 §4；catalog「追新＝crawler track」＋前车之鉴 #1「新届探测不塞进 discover」），`track` 正是以首页 `ul.proceedings-list` 为源。**裁决（§8-★2）**：零网络程序生成定稿（首页解析路径否决——discover 零网络先例优先）。
- **IssueRef 字段分解（幂等键定死；openreview 先例）**：
  - `volume` = `None`
  - `number` = `None`
  - `year` = `YYYY`（int——`--year` selector 的生效过滤列；Phase 1 `repo.list_issues(..., year=)` 已按此列圈定，[LIVE] 代码核实 `cli.py`/`repo`）
  - `label` = `'YYYY'`（极简，openreview 同款）
  - `pub_date` = `None`（discover 零网络不打详情页；真实出版日在 citation `publication_date`，属 enrichment）
  - `paper_count_claimed` = `None`（discover 阶段无权威篇数，交 enumerate 回填；arxiv/openreview 同款）
  - **不变式（校验用，不入字段）**：`vol == year − 1987`（[LIVE] §2）——可在解析/canary 层断言，不写进 `IssueRef.volume`。
  - > 备注（非阻塞）：NeurIPS 与 openreview 不同，**天然有确定卷号**（`year−1987`，且被 `citation_volume` meta 佐证：2023→`"36"`、1987→`"0"`）。本稿依任务口径取 `volume=None`（openreview 先例、`--year` 已足够圈定）；若主 agent 希望点亮 `crawler list neurips --volume 36`，可改 `volume=str(year−1987)`（零成本、可与 citation_volume 交叉核）。默认取 `None`。

### 3.2 enumerate_issue（1 请求/届）

- GET 年页 `{base}/paper_files/paper/{issue.year}`（`base` 见 §4 域选择）→ 解析 `ul.paper-list > li[data-track]`。每 `li`：
  - 标题 = `div.paper-content > a[title="paper title"]` 的**链接文字**（[LIVE] §3）；
  - 作者 = `span.paper-authors` 文本，逗号分隔全名 → `authors` tuple；
  - hash = `a[href]` 中 `/hash/{hash}-Abstract…` 段（32-hex）；
  - track = `li[data-track]` 值（`conference` / `datasets_and_benchmarks` / `none`）；
  - abstract 后缀 = href 中 `-Abstract` 与 `.html` 之间的**逐字子串**（`''` / `-Conference` / `-Datasets_and_Benchmarks`）。
- 产 `PaperStub`：
  - `title`、`authors`；`year = issue.year`；`abstract = None`（**年页无摘要**——摘要/citation meta 仅在逐篇 Abstract 页，本期不逐篇抓，见 §3.3「metadata 深度」）；
  - `identifiers = (('neurips', <hash>),)`（§8-★1 已定：裸小写 hash）；
  - `meta`：`(('track', <data-track 值>), ('asset_suffix', <逐字后缀>))`——resolve 的构造线索（`asset_suffix` 逐字保存以抗未来新 track 漂移，见 §3.3）。
- `paper_count_claimed`（本届回填）＝ `li[data-track]` 计数（[LIVE] §3：等价去重后 `Abstract*.html` href 计数；2023 校验 3218+322=3540 两法一致）。**D&B 与主会同页混排**（非独立页），靠 `data-track` 区分——**本届总篇数含两 track**（Phase 2 不按 track 拆 Issue；track 落 `meta`/`paper_count` 报告）。

**identifier scheme/value（§8-★1 已裁决：方案 A 裸小写 hash；以下为方案论证存档）**
scheme 固定 `'neurips'`（需在 design/06 `identifier.scheme` 清单预注册，与 `arxiv`/`openreview`/`pmlr` 并列）。value 三方案：
- **方案 A（建议）**：**裸 32-hex hash**（如 `0001ca33ba34ce0351e4612b744b3936`）。站点全小写十六进制、逐字原样保留（**不做 lower()/归一变换**，仅断言 `^[0-9a-f]{32}$`——形态校验，openreview「forum id 原样、无变换」先例）。理由：hash 是站点稳定 per-paper id、出现在该篇**全部**资产 URL（Abstract/Paper/Supplemental 同 hash，[LIVE] §5），跨年全局唯一（内容/分配型 hash，跨年撞车＝站点 bug，astronomically 罕见）；作强合并锚点最干净（design/06）；year/track 分居 `PaperStub.year`/`meta`，identifier 保持纯锚点。
- 方案 B：年份限定 `{year}/{hash}` 或 `neurips-{year}-{hash}`。自足（可从 identifier 单独重建 URL），但**把 year 耦进锚点**且冗余（hash 已唯一）——损合并纯度，不建议。
- 方案 C：站点内部数字 `sourceid`（仅 `Metadata.json` 暴露）。**否**——该端点可用窗窄（**实测 1987–2019 有、2020 起无**，[LIVE 2026-07-24] 闭合，见 §7），非全语料可得的稳定 id。（注：sourceid 另经 Bibtex 短链 `/{sourceid}-/bibtex` 暴露于全年份详情页，但仍是站点内部易变编号，不宜作合并锚点。）
- **建议：方案 A**（裸小写 32-hex hash，形态断言，无归一）。
- **空态**：年页 200 但解析 **0 条目** → **非合法空态，判 `parse`**（[LIVE]：已发布届恒 ≥1 篇，1987 都有 90 篇；0 条目＝选择器漂移信号，canary 标红）。合法「空」只出现在 discover 粒度（当年未发布→不在 timeline），见 §6。

### 3.3 resolve_assets（零网络，仅产 PDF）

- **纯 URL 构造**（arxiv 先例：resolve 零网络）。从 `PaperStub` 取 `hash`（identifier）、`year`、`meta.asset_suffix`（缺省时由 `meta.track`＋边界表回推，见下）：
  - **PDF 后缀改写规则（按 2021→2022 边界双形态）**：
    - `SUFFIX_BOUNDARY_YEAR = 2022`（首个新格式年）。`era = 'legacy' if year <= 2021 else 'modern'`。
    - `infix`：legacy → `''`；modern → 由 track 定：`conference`→`-Conference`、`datasets_and_benchmarks`→`-Datasets_and_Benchmarks`（(era,track)→infix 闭表，T1 矩阵）。
    - **运行时优先用 enumerate 逐字捕获的 `meta.asset_suffix`**（抗未来新 track：任何新后缀原样流过，无需改码）；`asset_suffix` 缺失时回退 (era,track) 闭表；modern 遇未知 track 且无捕获后缀 → `config`（响亮停机，绝不静默猜）。
    - Paper PDF URL＝`{base}/paper_files/paper/{year}/file/{hash}-Paper{infix}.pdf`（[LIVE] §5：`-Abstract`→`-Paper`、`/hash/`→`/file/`、`.html`→`.pdf` 三处替换，全样本一致）。
  - 产 **单个** `AssetPlan(kind=PDF, url=…, expected_type='application/pdf', url_strategy=DIRECT, auth_needed=NONE, version=None)`。
  - **仅产 PDF**（arxiv 先例：Phase 2 pipeline fetch 仅落 pdf，`_asset_final_path` 非 pdf 即 CONFIG）——landing HTML **不物化为可取回 asset**。
- **Supplemental：本期不产（deferred）**。[LIVE] §5 证实：存在与否**必须从 Abstract 页判定**（1987 无 Supplemental 链接），纯构造会误产不存在资产；且 Phase 2 pipeline 只落 PDF。构造规则**已知**（`{hash}-Supplemental{infix}.pdf`，**`.pdf` 非旧稿的 `.zip`**）但**存在性未知**——留待 enrichment（逐篇 Abstract 页解析）实现，本期以已知规则记档、不产 plan。
- **metadata 深度（本期口径，明确写出以免误解）**：Phase 2 enumerate **仅解析年页**（title/authors/hash/track），**不逐篇抓 Abstract 页**（一届 3540 篇＝3540 请求，无 AC 需求，代价过高；[LIVE] 无 API、无摘要 bulk）。故本期**不产出** abstract 正文、citation meta、Supplemental、2021 OpenReview/arXiv 线索——这些均需逐篇 Abstract 页，属 **Phase 3 enrichment**。
  - **meta 线索规约（现在定死，enrichment 落地时生效）**：逐篇 Abstract 页解析时，内嵌 **OpenReview forum id**（[LIVE] §9：2021 样本 `openreview.net/forum?id=CU8qQMhB3dh`）与 **arXiv id** 线索 → 存 `PaperStub.meta`（键 `'openreview'` / `'arxiv'`），**不产 identifier**（arxiv R3 裁决先例：防 Phase 2 意外触发跨源早合并；Phase 3 ingest 依 D-007 建 `preprint_of`/评审版边）。
  - **abstract 双 `<p>` 包裹**（[LIVE] §4）与 **1987 稀疏 citation**（无「Advances in」、`volume="0"`、无 first/lastpage、年份粒度日期）为 enrichment 期的解析注记，留 fixture golden（§6 ④）。

### 3.4 fetch_asset（流式）

- `HttpClient.stream(plan.url)` → `io.write_stream`。`%PDF` 权威校验归 pipeline（冻结分工）；adapter 职责：对「PDF url 却回 HTML 页」嗅探判 `gone`（arxiv `_gone_guarded_stream` 同款——避免 pipeline `%PDF` 校验误判 INTEGRITY 重试）。HTTP 404/410 由 `HttpClient` 直接映射 `gone`。

### 3.5 healthcheck（2 请求，跨边界 canary）

- GET **2021 年页（legacy 格式）＋2022 年页（modern 格式）**——一次覆盖后缀边界两态与 conference/D&B 两 track。解析后断言 **3 个固定 canary 论文**（1×2021 legacy、1×2022 conference、1×2022 D&B）各命中：**规整化 title ＋ track** 双字段（非原串精确——抗折行/无害微调误报，arxiv/openreview 先例）。任一 canary 缺失或双字段任一漂移、或任一页解析 < 篇数下限 → `unhealthy`。
- 校验的是 **enumerate 关键路径**（年页列表解析，最易漂移处）；后缀构造规则由 §6 T1 fixture 矩阵离线保障。

## 4. 限速与礼貌

| domain | 速率 | 依据 |
|---|---|---|
| proceedings.neurips.cc（[0] 主域＝限速账本键） | **30 rpm（1 req/2s），并发 1** | 站点无 robots、无 `X-RateLimit-*`/`Retry-After`、无 ToS 限速条款（[LIVE] §7/§8）；NFR-4「无声明站点 ≤1 req/2s/domain」默认；design/03 §3 同款 |
| papers.neurips.cc / papers.nips.cc（同源镜像） | 同上，**共享同一预算** | 三域同一 Apache 后端、字节级相同（[LIVE] §1）——一份 1req/2s 预算，不因换镜像翻倍 |

- **域选择**：三镜像内容等价、选谁纯团队偏好；**建议统一用 `proceedings.neurips.cc`** 与 `citation_pdf_url` 对齐（[LIVE] §1）。`domains = ("proceedings.neurips.cc", "papers.neurips.cc", "papers.nips.cc")`，`[0]` 为限速/日志账本键（同后端共享预算）。
- `default_rate.source_note` 引勘察 §7/§8＋NFR-4（`types.RatePolicy` 强制出处）。UA 按 D-014 `PaperCrawler/<ver> (personal research; mailto:<user>)`（由调用方注入，非 adapter 职责，http.py 不读 config）。实际限速由 pipeline `acquire_and_wait` 依 `default_rate` 强制，不在 adapter。
- **robots/合规表述（[LIVE] 已解除悬置）**：站点**无 robots.txt**（两域 404），无可 comply 的公约；proceedings 子域亦无抓取许可/版权声明——既未禁止亦未许可。按「公开学术索引、保守限速、不绕过任何门槛」默认姿态处理（AGENTS §6 保守义务仍适用，尽管无 robots 约束）。26 请求实测 0 挑战门，谈不上「绕过」。

### 网络层需求（复用 Phase 2 共享 `HttpClient`，见 http.py 冻结件）

**属 adapter 自身职责**：HTML 解析（首页届表 / 年页列表 / [详情页——deferred]）、后缀改写 URL 构造、PDF 流「回 HTML＝gone」嗅探。**不归 adapter**：限速（pipeline `acquire_and_wait`）、`%PDF` 校验（pipeline）、落盘（`FetchIO`）、重试调度（pipeline 按 `RETRY_TABLE`）。`transport` 注入 `httpx.MockTransport` 达成 T4 零真实网络。

## 5. 失败模式映射

| 站点现象 | error_class | 说明 |
|---|---|---|
| 年页 200 但解析 **0 条目** | `parse` | 已发布届恒 ≥1 篇（1987 都 90 篇），0 条目＝`ul.paper-list`/`li[data-track]` 选择器漂移；canary 标红。**非合法空态** |
| 首页 `ul.proceedings-list` 解析失败/0 届 | `parse` | discover 的权威源漂移；canary 标红 |
| 年页 404（[LIVE] 通用 404） | `gone` | HttpClient 404→GONE。discover 读程序生成的已发布界，正常不应命中——命中即 site drift 信号。**404 双语义**（「从未存在」vs「未来未发布」）站点**不可由 body 区分**（共用 23B 通用页，[LIVE] §6），故统一 `gone`（资源终态）；「未发布当年」由 discover 不生成该年前置规避（§3.1） |
| PDF/资产 404/410 | `gone` | 单篇资源消失/撤稿（HttpClient 映射） |
| PDF url 回 HTML 页（200 非 PDF） | `gone` | adapter `_gone_guarded_stream` 首字节嗅探（arxiv 先例） |
| modern 篇遇未知 track 且无捕获后缀 | `config` | resolve 构造缺陷/新 track 未适配，响亮停机（绝不静默猜后缀） |
| timeout / 连接错 | `transient` | HttpClient 统一映射 |
| 5xx（无 Retry-After） | `transient` | HttpClient；503 带 Retry-After → `rate_limited` |
| 429 / 503+Retry-After | `rate_limited` | HttpClient；30rpm 自限下罕见（[LIVE] 实测无限流） |
| 其余 4xx（400/405…） | `config` | HttpClient 兜底（请求构造缺陷，响亮停机转 BLOCKED） |
| **合法空态：当年未发布** | —（**非错误**） | discover **不生成**未发布当年（§3.1 `known_through_year`）→ timeline 合法少一届；与锚点表（§6）同口径呈现。**这是 NeurIPS 唯一的「合法空」**——不存在 openreview 式「200 空列表」（已发布届恒非空） |

**已知冻结限制（本期承认，收紧随 Phase 4 走接口仲裁；arxiv.md §5 / openreview.md §6 同批）**：①`FetchResult` 无 `http_status` 字段，`fetch_log.http_status` 本期恒 NULL；②metadata 阶段请求（首页届表、年页列表 GET）**不入 FetchLog**——其限速审计证据为 obslog jsonl（HttpClient 每请求 debug 事件：domain/脱敏 url/status/elapsed_ms）；③`Retry-After` 不驱动重试调度（仅解析入 detail 供观测）。这三点关涉 AC-4.4（日配额靠 FetchLog 对账）与 AC-0.5（限速审计）证据链，明确承认以免误以为 neurips 全部网络行为可在 FetchLog 查到。

## 6. Fixtures 与测试

**验收口径（无专属 AC——明确写出）**：`docs/testing/acceptance-criteria.md` 的 AC-2.1~2.6 无 neurips 条目（AC-2.1/2.2＝iclr、2.3＝arxiv、2.4＝cvpr、2.5＝ACL、2.6＝ACM OA），`phase2-implementation-plan` 排期表（§adapter 顺序）中 neurips_proceedings **未挂任何 AC 编号**。故 neurips **验收＝通用 DoD**：**① T3 离线 fixture 全解析回归（NFR-6 门禁，CI 强制）＋ ② 一次限量在线冒烟＋ ③ canary 注册**。D-019 锚点表虽无 AC 绑定，仍按 D-019 建表服务 timeline/篇数完整性核对。

- **T1 单元（与网络解耦）**：
  - 后缀改写矩阵：(era, track)→infix 闭表 × Paper/Supplemental × legacy/modern；`asset_suffix` 逐字优先 / 回退闭表 / 未知 track→config；`-Abstract→-Paper`、`/hash/→/file/`、`.html→.pdf` 三替换。
  - hash 形态校验（`^[0-9a-f]{32}$`，非法拒绝）。
  - discover 年份生成：`first_year`/`known_through_year`/`since` 边界；连续性与 `vol==year−1987` 不变式断言。
  - IssueRef 字段分解（volume/number=None、year=int、label='YYYY'）。
  - **discover 合法空态（纯逻辑，无需 fixture）**：`known_through_year < 当前年` 时 timeline 不含当年——断言不产该年 Issue、非错误。
- **T3 fixture 十一件套（§5 全部 error_class 各有落点，test-plan §6 强制；录制物为 CC0 公开元数据，难录形态合成并标注）**：
  1. **首页 `ul.proceedings-list`**（discover golden：39 届、连续、`vol=year−1987` 校验）
  2. **年页·legacy（2021 快照）**（`data-track="none"`、无 badge；enumerate golden，含 2021 canary）
  3. **年页·modern（2022 快照）**（conference＋datasets_and_benchmarks 混排＋badge；enumerate golden，含 2 个 2022 canary）
  4. **详情页 Abstract 快照**（modern conference：全 citation meta＋双 `<p>` abstract；另附 1987 legacy 稀疏 citation＋`Metadata.json` 线索记档）——**enrichment golden**（本期不解析，留 Phase 3；同时是后缀/era 的真实样本）
  5. **年页 404**（`<h1>Page Not Found</h1>` 23B）→ `gone`
  6. **年页结构漂移**（0 条目，**合成**，标注）→ `parse`
  7. **PDF 正常字节头**（`%PDF` 样本片段）→ fetch happy path
  8. **PDF 回 HTML 页**（撤稿/不存在，合成/真实）→ `gone`（`_gone_guarded_stream`）
  9. **503+Retry-After**（合成，**响应头随体落盘**）→ `rate_limited`
  10. **5xx 无 Retry-After**（合成）→ `transient`
  11. **400**（合成）→ `config`
- **T4 集成（MockTransport 全链）**：discover→enumerate→resolve 全链，legacy＋modern 双 era × conference/D&B 双 track 的后缀构造断言；`paper_count_claimed` 计数断言；`pull neurips --year 2023 --limit 10` 式 10 plan/魔数/DB↔文件对账（复用 AC-2.2 测试模式，虽无 AC 绑定）。
- **T5 在线冒烟（预算 `MAX_REAL_REQUESTS=6`）**：healthcheck 2（2021+2022 年页）＋ 单篇 legacy PDF fetch 1 ＋ 单篇 modern PDF fetch 1 ＋ 余量——一次覆盖两 era 的 enumerate 解析（在线）与 resolve+fetch（在线）。discover/resolve 零网络不计。
- **canary 样本（抗 flake，3 跨边界，2021/2022 各含——任务定死）**：`{2021 legacy, 2022 conference, 2022 datasets_and_benchmarks}`，**规整化 title ＋ track** 双字段。样本 hash/title 取自 fixture ②③（2021/2022 年页 golden），T5 在线冒烟再核验；**实现期用实测值替换任何占位**（arxiv canary「⚠ 合成占位需真实替换」同款纪律，见 arxiv adapter `_CANARIES`）。
- **D-019 锚点表** `tests/fixtures/neurips_proceedings/dblp-nips-anchor.json`（**路径更正**：文件实际落在 `neurips_proceedings/` 目录，非本段旧文所写的 `neurips/`——两者不同，2026-07-23 复核时如实标注）：逐年 `{year, paper_count_claimed, dblp_slug: "conf/nips", note}`。**生成程序（实现期）**：enumerate 取各届 `li` 计数 ＋ **人工对照 DBLP `conf/nips` TOC 页核准**（UPDATE_GOLDEN 纪律、records 留痕）。**勘察已捕获的种子值**（[LIVE]，供建表起点）：1987=90、1993=158、2019=1428、2020=1898、2021=2334、2022=2834（2671 conf＋163 D&B）、2023=3540（3218 conf＋322 D&B）。特例注记：1987/1988＝vol 0/1（DBLP 年份约定须核，[UNRESOLVED] 归入 note）。timeline 完整性判定＝`timeline neurips` 输出与锚点表全等——**测试须固定 `known_through_year`**（如锚点最大年 2025）使 `timeline` 确定性可复现（否则 `current−1` 默认随时钟漂移）。**D-019 人工 DBLP 核准部分闭合 [LIVE 2026-07-23]**：2023 行实测——`dblp_slug` 由本段假设的 `conf/nips/nips2023`（活测 **404**）纠正为 **`conf/nips/neurips2023`**（DBLP 于某未确认年份起把年度 TOC 文件名前缀从 `nips` 换成 `neurips`，目录本身仍是 `/db/conf/nips/`；经该站索引页发现）；`GET .../neurips2023.html` 实测 3540 条 `inproceedings`，与种子值**精确匹配**、无 Frontmatter 偏移。~~**其余年份（含 1987/1988 的 vol 0/1 约定）仍未验证，`conf/nips/nips{year}` slug 猜测对哪些年份成立仍是 [UNRESOLVED]**~~——核准出处见 fixture 该行 `note`/`dblp_toc_count`/`dblp_cross_check` 与顶层 `generated_note` 追记。**[UNRESOLVED 闭合 · LIVE 2026-07-24]**（Phase 5 检查单 #5 项⑤，证据见 site-survey §11）：dblp `conf/nips` 卷目录索引页（`/db/conf/nips/index.html`）一次请求列全 **39 个年 TOC 文件名**——**slug 命名规则实测锁定：`nips{year}` 用于 1987–2019（33 年），`neurips{year}` 用于 2020–2025（6 年），切换点精确在 2019→2020**（此前仅 2023 行经 M2a 核准；现全 39 年规则确定，逐年 slug 不再是猜测）。vol-0 年 `nips1987.html`=200、**90 篇 `inproceedings`** 与 proceedings 站 1987 篇数（种子值 90）**精确一致**；dblp 以**年份**（1987）而非**卷号**（vol 0）建 slug/键，故"1987/1988=vol 0/1"仅是 proceedings 站 `citation_volume=year−1987` 约定、**对 dblp slug 无影响**，锚点表 `dblp_slug: conf/nips` 正确，逐年 TOC 文件名按 `nips`(≤2019)/`neurips`(≥2020) 前缀规则生成即可。**巧合注记**：该 slug 切换年（2019→2020）与 §7 Metadata.json 消失边界（2019→2020）**同年**，均对应 NeurIPS 2020 proceedings 流水线换代。

## 7. 风险与维护

- **双域/镜像**：主用 `proceedings.neurips.cc`；`papers.neurips.cc`/`papers.nips.cc` 内容等价、不跳转，作兜底镜像写入 quirks（换镜像不翻倍限速预算——同后端）。
- **后缀边界维护**：`SUFFIX_BOUNDARY_YEAR=2022` 为单一硬边界（[LIVE] 五年验证）。运行时优先逐字捕获 `asset_suffix`（抗新 track）；**若 NeurIPS 增设新 track**（如 Position Papers），新 `data-track` 值与后缀自动流过；(era,track) 闭表遇未知 track→`config` 响亮暴露，canary 每届抽查。
- **★[UNRESOLVED → 闭合 · LIVE 2026-07-24] 2021 OpenReview 强 id 覆盖率**（[LIVE] §9→site-survey §11 项①）：2021 详情页内嵌 `openreview.net/forum?id=…`，2022/2023/1987 样本无。~~n=1 待扩样~~ **实测闭合**：2021 年页（2334 篇）跨全表均匀抽 8 篇 → **8/8 全部内嵌 forum 链接、8 id 互异 → 覆盖率 100%，2021 届普遍存在**。**裁决输入**：该链接确对 2021 全届普遍存在，Phase 3 ingest 处理 2021 时**应**优先抽 forum id 作强 id（而非一律弱匹配 candidate 队列），值得为 2021 单开强 id 合并分支（2022+ 无此链接、弱匹配不变）。本期仍仅在规约层预留 `meta['openreview']`（§3.3）；分支落地与否留 Phase 3 ingest 裁决，覆盖率前置条件已满足。
- **[UNRESOLVED → 闭合 · LIVE 2026-07-24] `Metadata.json` bulk 机会**（[LIVE] §10→site-survey §11 项②）：1987 详情页有 `…-Metadata.json`（含 `full_text` OCR 全文＋abstract＋authors[institution]），对老论文是比下载 PDF 自抽更省的全文源。~~可用年份窗未定（边界未测）~~ **二分实测闭合：可用窗 = 1987–2019（含），2020 起 404，边界精确在 2019→2020**（2004/2013/2017/2019=200；2020 双 hash 复测 404 且其 Abstract 页 200 佐证端点缺失而非坏 hash）。**注意此窗（≤2019）比后缀格式窗（≤2021）更窄**——两边界不同年，构造 Metadata.json URL 前须按 ≤2019 判定，不能复用 suffix_boundary。**本期不实现**；作为 ≤2019 老论文 enrichment/bulk 全文机会记档，年份窗已定，实现期可直接用。
- **[UNRESOLVED → 闭合 · LIVE 2026-07-24] 详情页 Bibtex 链接畸形**（[LIVE] §4→site-survey §11 项③）：2021/2022/2023 样本 Bibtex 按钮 href 为 `…/{数字}-/bibtex`（孤立连字符，疑模板 bug）。~~未实发请求验证~~ **实测闭合·可用**：`GET …/11624-/bibtex` → **302 → `…/{hash}-Bibtex.bib`** → 200 `application/x-bibtex`（合法体）。**`{数字}` 是站点内部 sourceid，短链服务端 302 到规范 `{hash}-Bibtex.bib`，非坏链**。若 enrichment 需站内 BibTeX：**推荐直接构造 `{hash}-Bibtex.bib`**（本次实测同样 200，绕过短链、形态与 1987 hash 前缀统一）；或用 citation_* meta 自拼。畸形短链亦可用（多一跳 302）。
- **[UNRESOLVED → 闭合 · LIVE 2026-07-24] `sitemap.xml`**（site-survey §11 项④）：~~未探测~~ **实测闭合·不存在**：`GET …/sitemap.xml` → 404（23 B 通用页）。站点无 sitemap（与"无 robots.txt"一致，Django 未启用 sitemap 框架）；discover 仍以首页 `ul.proceedings-list`（§2）为年份索引权威源，无机读全站清单可依。**[UNRESOLVED 维持] `neurips.cc` 宣传站稳定性未测**（勘察任务书明确排除，**非"未解决"而是"未纳入范围"**）——实现期若需要再补勘察。
- **站点技术背景**（非风险，参考）：Django＋Apache 静态直出，无 CDN/WAF；年页 `<title>Book</title>` 为 CMS 默认值，**对解析/校验无用，勿依赖**（[LIVE] §3）。
- **与 openreview 合并质量**：2022+ 无共同强 id，弱匹配依 ingest candidate 队列人工审核（D-007）；canary 抽查合并正确率（Phase 3）。

## 附录 · venue YAML 提案（`venues/cs_ai/neurips.yaml`）

```yaml
# venues/cs_ai/neurips.yaml —— NeurIPS 正式 proceedings（评审版 neurips_openreview 本期推迟）
id: neurips
kind: conference
names: {full: Conference on Neural Information Processing Systems, aliases: [NeurIPS, NIPS]}
field: [cs_ai]
tier: T1
identifiers:
  dblp_key: conf/nips          # 锚点表比对源（DBLP conf/nips TOC）
metadata_source: neurips_proceedings
fulltext_source: neurips_proceedings
auth: {level: none}            # [LIVE] 证实无认证（与 iclr.yaml 的 none-被证伪不同，此处 none 正确）
quirks:
  first_year: 1987             # [LIVE] /1986→404 下界
  # known_through_year: 2025   # 缺省＝当前年−1；track 确认新届后 bump（D-012）
  # suffix_boundary_year: 2022 # 单一后缀边界（默认常量，quirk 仅作显式覆盖通道）
status: active
```

> 注：design/03 §4「两条 channel」中 `neurips_openreview`（评审版）本期不注册——单 channel（proceedings）即本 adapter；冻结 `VenueSpec` 亦为单 `metadata_source/fulltext_source`，评审 channel 属未来独立 venue/adapter。

## 8. 主 agent 裁决记录（2026-07-22，正文 ★ 各点就此落定）

| ★ | 裁决 | 理由 |
|---|---|---|
| ★1 identifier value | **方案 A：裸小写 32-hex hash** | 站点保证全局唯一；年份经 issue 关联可得，identifier 无需冗余；形态断言（32hex）作 lint |
| ★2 discover | **零网络程序生成 [1987..known_through_year]**（默认 current−1；venue quirks 可覆盖上界），新届追加归 track（design/08） | 与 arxiv/openreview/cvf 零网络先例一致 |
| ★3 IssueRef.volume | **None**（不点亮 --volume） | openreview 先例；卷号=year−1987 恒等映射冗余，--year 已覆盖圈定需求 |
| ★4 metadata 深度 | **薄元数据 Phase 2 接受**（年页解析 title/authors/hash/track，无 abstract；逐篇详情页 enrichment 推迟 Phase 3） | 与 cvf list-only 同款裁决；abstract 缺失不阻塞 metadata_only（design/06 既定）；OpenReview/arXiv 线索随详情页 enrichment 一并推迟，本期 meta 仅承载年页可得信息 |
