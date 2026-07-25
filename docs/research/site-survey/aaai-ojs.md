---
title: 勘察：AAAI OJS（OAI-PMH 主路径/分页/覆盖边界）
status: approved
owner: fable5
updated: 2026-07-26
---

# AAAI OJS（ojs.aaai.org）LIVE 勘察报告

- 勘察对象：`ojs.aaai.org`（对照旧稿 `docs/design/adapters/aaai-ojs.md`）
- 勘察时间：2026-07-21（服务器响应头 `date` 统一为 `Tue, 21 Jul 2026 17:4x:xx GMT`）
- UA：`PaperCrawler/0.1 (site survey; personal research)`
- 请求节奏：curl 逐条串行，间隔 ≥1.5s
- **实测请求总数：20**（预算 ≤25；明细见文末"请求清单"）
- 标签含义：`[LIVE]`=本次实测证实；`[DOC]`=旧稿断言未经本次验证；`[LIVE-推断]`=由实测数据推导但未直接抓取验证；`[UNRESOLVED]`=预算内未能查清

---

## 0. 结论速览（供重写者先读）

| 旧稿断言 | 本次结论 |
|---|---|
| archive 默认只显示最新一届⚠分页参数待核验 | **需改写**：不是"一页=一届"，是**每页固定 25 个 issue、纯"Next"链接翻页**（无页码/无跳末页）；最新一届（AAAI-26/Vol.40）自身就有 **48 个 issue**，跨 2 页才能看全，第 2 页中途才切到上一届。分页参数是路径序号 `/issue/archive/{n}`，非 query string。 |
| OAI-PMH 理论可用⚠未验证 | **证实可用**：`Identify`/`ListSets`/`ListRecords` 匿名 200，返回标准 oai_dc，含 DOI、摘要、直链 PDF relation。**强烈建议作为主抓取路径**（替代 HTML 翻页）。 |
| OJS REST API 未提及 | **新发现且是负面结果**：`/api/v1/issues` 匿名请求一律 **403** `api.403.unauthorized`，无论加不加参数。REST API 路径对本 adapter **不可用**，OAI-PMH 是唯一可行的机读批量路径。 |
| PDF URL `article/view/{id}/{galley}` → `article/download/{id}/{galley}` | **证实**：`view` 302 跳转到 `download`，`download` 才是 `application/pdf`。但更优路径是直接读文章详情页的 `citation_pdf_url` meta（值就是 download 终态 URL），可省一次跳转。 |
| DOI 形态 `10.1609/aaai.*` | **证实并精确化**：`10.1609/aaai.v{volume}i{issue}.{articleId}`，如 `10.1609/aaai.v40i1.36958`。 |
| 覆盖 1980、1982–2026 | **需澄清**：1980 是"AAAI proceedings 系列"官方历史起点（About 页原文），**不等于** ojs.aaai.org 这个 OJS 实例本身收录到 1980。实测只锚定到 2019（OAI 记录 `dc:date` 样本），更早年份是否在此 OJS 上 `[UNRESOLVED]`——**这正是旧稿 D-012 关注的"早年路径边界"问题的实测答案：早年大概率不在本 adapter 范围内**，需实现期专项核实。 |
| AAAI-38(2024) 锚点 | **命名体系澄清**：站点自己用 2 位年份品牌名 `AAAI-26`（=Vol.40=第 40 届，2026），旧稿的"AAAI-38"是**届序号**命名法，按本次实测的 Vol↔年 对应关系（Vol.40=2026, Vol.39=2025）**推算** Vol.38=站点自己会称为 "AAAI-24"（2024）。未直接抓取验证，`[UNRESOLVED，高置信推断]`。 |
| 免费全文、无防护 | **"无防护"证实；"免费"需精确措辞**：About 页原文承认 open access 阅读，但**版权顶头声明"Copyright to individual papers...is fully owned by AAAI. Permission is required for republication."**——是"免费可读"不是"可自由再分发"的开放许可（无 CC-BY）。爬虫合规定位应写成"免费只读镜像用途"而非"开放许可"。 |

**3 项最重要新发现**（对应最终回复要点）：
1. REST API 匿名 403（此前旧稿完全没提及这条路径，现已证伪其可用性）；OAI-PMH 才是真正可行的机读路径，且已证实含 DOI/摘要/PDF 直链。
2. 单届（AAAI-26/2026）proceedings 拆成 **48 个 OJS issue**，第 1 期（No.1，"Application Domains I" 子赛道）单期即 **94 篇 / 840 页**；track 拆分是真实存在的强特征，且不同 venue（AAAI vs ICWSM）拆分粒度不同，enumerate_issue 不能假设"一年一 issue"。
3. 版权是 all-rights-reserved 而非开放许可；早年覆盖边界（1980 vs 实测锚点 2019）未能在预算内查清，需实现期专项核实，不应想当然认为 ojs.aaai.org 收录全部历史。

---

## 1. OJS 结构确认 / family 划分

**[LIVE]** `GET https://ojs.aaai.org/index.php` → 200，`<meta name="generator" content="Open Journal Systems 3.3.0.22" />`

同一 OJS 实例（`ojs.aaai.org`）下托管的期刊代码（从首页链接提取，未逐一深入）：

```
/index.php/AAAI       ← 主会（本 adapter 核心）
/index.php/AAAI-SS    ← AAAI Spring Symposium Series（推测，未深入）
/index.php/AIES       ← AI, Ethics, and Society
/index.php/AIIDE      ← Artificial Intelligence and Interactive Digital Entertainment
/index.php/HCOMP      ← Human Computation
/index.php/IASEAI     ← 新增期刊代码，未深入（可能 2025/26 新设）
/index.php/ICAPS      ← Automated Planning and Scheduling
/index.php/ICWSM      ← International Conference on Web and Social Media
/index.php/SOCS       ← Symposium on Combinatorial Search
```

**[LIVE]** ICWSM 结构核验：`GET /index.php/ICWSM/issue/archive` → 200，同一套 `obj_issue_summary` HTML 结构，同一 generator 版本。**确认 ICWSM 就在本 OJS 实例上，不是外部站点**，回答了旧稿"AIES/ICWSM 等的 journal 划分"的疑问——它们是同一 OJS 实例下的独立期刊 context（`/index.php/{CODE}/...`），adapter 的 URL 构造逻辑可用同一套模板、仅替换 `{CODE}`。

**[LIVE] 重要跨 venue 差异**：ICWSM 的 issue/年 拆分粒度与 AAAI 不同——

```
Vol. 20 No. 1     ← 最新（无年份后缀，且已出现"No."子拆分，与今年新变化一致）
Vol. 19 (2025)    ← 单一 issue 涵盖全年，无 "No." 拆分
Vol. 18 (2024)    ← 同上
Vol. 17 (2023)    ← 同上
Vol. 16 (2022)    ← 同上
```

即 ICWSM 历史上"一年一个 OJS issue"，只有最新一届才开始像 AAAI 一样拆多个 "No."。**结论：track/issue 拆分粒度是逐年、逐 venue 可变的编辑决定，不是平台级固定规则**，enumerate_issue 必须按"实际抓到几个 issue 就是几个"的方式处理，不能硬编码"一年 N 个 issue"。

---

## 2. 卷/期页结构

### 2.1 archive 页 URL 与分页

**[LIVE]** `GET /index.php/AAAI/issue/archive` → 200；`GET /index.php/AAAI/issue/archive/2` → 200（页 2）。

分页机制：路径段 `/issue/archive/{pageNum}`（非 query string），每页固定 **25 个 issue**，倒序排列（最新在前）。翻页控件只有一个 `Next` 链接：

```html
<div class="cmp_pagination" aria-label="View additional pages">
  <a class="next" href="https://ojs.aaai.org/index.php/AAAI/issue/archive/2">Next</a>
</div>
```

**没有页码列表、没有"跳到最后一页"链接** —— 意味着要枚举全部历史 issue，必须**顺序翻页**直到 Next 消失，无法二分或直接跳页。这是 OAI-PMH 优先于 HTML 路径的关键理由之一。

### 2.2 单期页条目 HTML 形态（issue TOC）

**[LIVE]** `GET /index.php/AAAI/issue/view/683`（AAAI-26 Vol.40 No.1）→ 200，15805 bytes（gzip 前），**94 篇独立文章**。

选择器层级：

```html
<div class="obj_article_summary">
  <h3 class="title">
    <a id="article-36958" href="https://ojs.aaai.org/index.php/AAAI/article/view/36958">
      Resource Efficient Sleep Staging via Multi-Level Masking and Prompt Learning
    </a>
  </h3>
  <div class="meta">
    <div class="authors">
      Lejun Ai, Yulong Li, Haodong Yi, Jixuan Xie, Yue Wang, Jia Liu, Min Chen, Rui Wang
    </div>
    <div class="pages">3-11</div>
  </div>
  <ul class="galleys_links">
    <li>
      <a class="obj_galley_link pdf" href="https://ojs.aaai.org/index.php/AAAI/article/view/36958/40920"
         aria-labelledby=article-36958>PDF</a>
    </li>
    <!-- 部分文章还有第二个 galley： -->
    <li>
      <a class="obj_galley_link file" href=".../article/view/36959/49541"
         aria-labelledby=article-36959>Video/Poster/Slides</a>
    </li>
  </ul>
</div>
```

要点：
- 条目容器 `.obj_article_summary`；标题 `.title a`（`href` 含 articleId）；作者 `.authors`（纯文本逗号分隔，无结构化拆分，无机构信息）；页码 `.pages`。
- PDF 链接选择器：`a.obj_galley_link.pdf`（**必须按 class 过滤**，因为同一文章可能挂多个 galley，如 "Video/Poster/Slides"，class 是 `obj_galley_link file`）。
- galley 链接是 `/article/view/{articleId}/{galleyId}` 形态（两段 id，旧稿假设正确）。

### 2.3 AAAI-26(2026) 的 track 拆分方式（对应旧稿"AAAI-38(2024)"问题，用最新一届实测替代）

**[LIVE]** issue 描述原文（issue/view/683 的 description 字段，来自 archive 页摘要，节选）：

> "The proceedings have been published in **48 consecutive issues**. This issue (volume 40 no. 1) consists of **840 pages and 1 tracks**: AAAI Technical Track on Application Domains I"

**[LIVE]** page 1 的 25 个 issue 标题清单（全部同构，仅编号递增）：

```
Vol. 40 No. 1  :: AAAI-26 Technical Tracks 1
Vol. 40 No. 2  :: AAAI-26 Technical Tracks 2
...
Vol. 40 No. 25 :: AAAI-26 Technical Tracks 25
```

**[LIVE]** page 2 证实延续到 No.48 后切换到 Vol.39：

```
Vol. 40 No. 48 :: id=732   ← Vol.40 最后一个 issue
Vol. 39 No. 1  :: id=624   ← 上一届开始
Vol. 39 No. 2  :: id=625
```

**结论**：AAAI-26（2026）单届被拆成 **48 个 OJS issue**，每个 issue 对应技术赛道的一个切片（子 track，如"Application Domains I"），单 issue 规模约几百页、约 94 篇（以 No.1 为样本，其他期未逐一核验，**不应假设所有期都恰好 94 篇**）。issue 描述文本里同时提到 IAAI-26、EAAI-26 论文"included in this proceedings"，但未在预算内查清它们是否占用独立的 48+ 号 issue 还是穿插在 48 期之内——`[UNRESOLVED]`。

### 2.4 Vol ↔ 年份 ↔ 旧稿 "AAAI-NN" 命名对应关系

**[LIVE]** issue 683 描述原文：

> "**Fortieth** AAAI Conference on Artificial Intelligence" ... "**AAAI-26** ... January 20–27, 2026, Singapore"

即站点自己的品牌名 `AAAI-26`（2 位年份）= 第 **40 届** = OJS `Vol. 40`。

**[LIVE]** OAI-PMH 样本记录（见 §4）`dc:source` 字段：

> "Proceedings of the AAAI Conference on Artificial Intelligence; **Vol. 33 No. 01: AAAI-19, IAAI-19, EAAI-20**; 695-701"

即 `Vol.33` = 站点品牌名 `AAAI-19`（2019）。

**[LIVE-推断]** 由 Vol.40=2026、Vol.33=2019 两点可得近 7 年内 `Vol = 年份 - 1986` 线性关系；据此 **Vol.38 应对应 2024**，站点会称之为 `AAAI-24`（不是旧稿写的"AAAI-38"）。**旧稿的"AAAI-38"用的是届序号命名法**（AAAI 官方历史确实说"这是第 38 届"之类表述），**与站点 OJS 上实际使用的 2 位年份品牌名不是一回事**——重写时建议 adapter 内部一律用 `Vol.N` 或站点品牌名 `AAAI-YY`，避免和"第 N 届"序号混淆。此对应关系未直接抓取 Vol.38 issue 验证，标 `[UNRESOLVED，高置信]`。

**[LIVE] 关于"个别年份存疑"的成因**：About 页原文（见 §7）明确列出 1981/1985/1989/1995/2001/2003/2009 这些年份 AAAI 与 IJCAI 联合出版，proceedings "under the auspices of the international organization"——这很可能是导致"届序号"与"OJS Vol 号"不完全线性对应、以及旧稿标注"个别年份存疑"的**真实原因**：这些年份大概率没有独立的 AAAI-only Vol 号。

---

## 3. 详情页：citation_*/DC.* meta 与 DOI

**[LIVE]** `GET /index.php/AAAI/article/view/36958` → 200，4853 bytes。同时输出 **Dublin Core (`DC.*`) 与 Highwire/Google Scholar (`citation_*`) 两套标签**（旧稿猜测两者都可能存在，证实）：

```html
<meta name="DC.Creator.PersonalName" content="Lejun Ai"/>
<!-- ... 每作者一条 ... -->
<meta name="DC.Date.issued" scheme="ISO8601" content="2026-03-17"/>
<meta name="DC.Identifier" content="36958"/>
<meta name="DC.Identifier.DOI" content="10.1609/aaai.v40i1.36958"/>
<meta name="DC.Identifier.URI" content="https://ojs.aaai.org/index.php/AAAI/article/view/36958"/>
<meta name="DC.Rights" content="Copyright (c) 2026 Association for the Advancement of Artificial Intelligence"/>
<meta name="DC.Source.Issue" content="1"/>
<meta name="DC.Source.Volume" content="40"/>
<meta name="DC.Type.articleType" content="AAAI Technical Track on Application Domains I"/>

<meta name="citation_journal_title" content="Proceedings of the AAAI Conference on Artificial Intelligence"/>
<meta name="citation_author" content="Lejun Ai"/>
<meta name="citation_author_institution" content="South China University of Technology"/>
<!-- institution 只在部分作者后出现，不是每人必有 -->
<meta name="citation_title" content="Resource Efficient Sleep Staging via Multi-Level Masking and Prompt Learning"/>
<meta name="citation_date" content="2026/03/17"/>
<meta name="citation_volume" content="40"/>
<meta name="citation_issue" content="1"/>
<meta name="citation_firstpage" content="3"/>
<meta name="citation_lastpage" content="11"/>
<meta name="citation_doi" content="10.1609/aaai.v40i1.36958"/>
<meta name="citation_pdf_url" content="https://ojs.aaai.org/index.php/AAAI/article/download/36958/40920"/>
```

**要点**：
- `citation_pdf_url` 直接给出 **download 终态 URL**（即 `article/download/{id}/{galley}`），resolve_assets 阶段应优先读这个 meta 值，**可以省掉一次 302 跳转**（见 §4）。
- DOI 精确形态确认：`10.1609/aaai.v{volume}i{issue}.{articleId}`（`1609` 是 AAAI 在 CrossRef 注册的 DOI 前缀，About 页确认 AAAI 是 CrossRef 参与方）。
- 作者机构（`citation_author_institution`）覆盖不全，不能作为必有字段依赖。

---

## 4. PDF URL 形态与托管域

**[LIVE]** `curl -I -L` 追踪跳转链：

```
GET https://ojs.aaai.org/index.php/AAAI/article/view/36958/40920
→ HTTP/2 302, location: https://ojs.aaai.org/index.php/AAAI/article/download/36958/40920

GET https://ojs.aaai.org/index.php/AAAI/article/download/36958/40920
→ HTTP/2 200
  content-type: application/pdf
  content-disposition: attachment;filename=23369-AAAI26.AiL-AD.pdf
```

- **旧稿假设成立**：`article/view/{id}/{galley}` → `article/download/{id}/{galley}`。
- **托管域**：始终 `ojs.aaai.org` 本域，**无 CDN 卸载、无跨域跳转**（server 头全程 `nginx`）。
- `Content-Disposition` 文件名格式 `{内部编号}-{会议品牌}.{赛道缩写}.pdf`（如 `23369-AAAI26.AiL-AD.pdf`），可作为 fixture 命名参考，非 URL 结构必需项。
- **效率建议**：既然详情页 meta 已给出 `citation_pdf_url`（终态 download URL），resolve_assets 不必自己走 `view→download` 两跳，直接用 meta 值 + HEAD 校验 content-type 即可。

---

## 5. OJS API 探测（REST API 与 OAI-PMH）

### 5.1 REST API（`/api/v1/*`）—— 匿名不可用

**[LIVE]**
```
GET /index.php/AAAI/api/v1/issues?count=100 → HTTP 403
GET /index.php/AAAI/api/v1/issues            → HTTP 403
Body: {"error":"api.403.unauthorized","errorMessage":"You are not authorized to access the requested resource."}
```

两种参数形态均 403，**判定匿名 REST API 路径不可用**，需要 API token（本次勘察未申请/未测试认证路径，超出"匿名可读性"范围）。**这是旧稿完全没有讨论过的路径，现已证伪，写入正式设计文档可以直接排除该选项**，避免实现期浪费时间去试。

### 5.2 OAI-PMH（`/index.php/AAAI/oai`）—— 匿名可用，推荐作为主路径

**[LIVE] Identify**（200）：

```xml
<repositoryName>Proceedings of the AAAI Conference on Artificial Intelligence</repositoryName>
<baseURL>https://ojs.aaai.org/index.php/AAAI/oai</baseURL>
<protocolVersion>2.0</protocolVersion>
<earliestDatestamp>2020-06-02T17:44:16Z</earliestDatestamp>
<compression>gzip</compression>
<compression>deflate</compression>
```

⚠ **`earliestDatestamp` 不可信为"最早收录年份"**——见 §6 覆盖年限的实测矛盾证据。

**[LIVE] ListSets**（200，分页，`completeListSize="386"`，本次只取第 1 页 100 条）：set 命名形如 `AAAI:{year}-{trackId}`（如 `AAAI:2024-149` = "Intelligent Robots (ROB)"）或语义化 slug（如 `AAAI:IAAI-DEP` = "IAAI Deployed Papers"、`AAAI:EAAI-MAIA` = "EAAI Symposium: Model AI Assignment Abstracts"）。386 个 set 印证 track 切分粒度之细。

**[LIVE] ListRecords**（`metadataPrefix=oai_dc`，不加 set 过滤，200，`completeListSize="26185"`，单页 100 条 + resumptionToken）——样本记录：

```xml
<record>
  <header>
    <identifier>oai:ojs.aaai.org:article/3745</identifier>
    <datestamp>2021-09-12T12:50:00Z</datestamp>
    <setSpec>AAAI:AISI</setSpec>
  </header>
  <metadata><oai_dc:dc>
    <dc:title>Emergency Department Online Patient-Caregiver Scheduling</dc:title>
    <dc:creator>Rosemarin, Hanan</dc:creator>
    <dc:date>2019-07-21</dc:date>
    <dc:identifier>https://ojs.aaai.org/index.php/AAAI/article/view/3745</dc:identifier>
    <dc:identifier>10.1609/aaai.v33i01.3301695</dc:identifier>
    <dc:source>Proceedings of the AAAI Conference on Artificial Intelligence; Vol. 33 No. 01: AAAI-19, IAAI-19, EAAI-20; 695-701</dc:source>
    <dc:relation>https://ojs.aaai.org/index.php/AAAI/article/view/3745/3623</dc:relation>
    <dc:rights>Copyright (c) 2019 Proceedings of the AAAI Conference on Artificial Intelligence</dc:rights>
  </oai_dc:dc></metadata>
</record>
```

**OAI-PMH 单条记录即含**：标题、作者、摘要（`dc:description`，示例中省略）、发表日期、DOI、文章页 URL、galley/PDF 关系链接、期号引用串、版权声明——**足以覆盖 DISCOVER+ENUMERATE+RESOLVE 三阶段所需字段**，且是标准协议（分页 100 条/页 + resumptionToken，标准收割循环）。**强烈建议本 adapter 的 discover_timeline/enumerate_issue 首选 OAI-PMH ListRecords 全量收割，仅在字段缺失（如摘要为空）时才 fallback 到 HTML 详情页补抓。**

⚠ 注意：`set=AAAI:2023-11`（"Main Track"）单独过滤查询返回 `noRecordsMatch`（空），怀疑 ListSets 展示的 setSpec 与 ListRecords 实际可查询的 setSpec 存在层级/命名差异，**实现期需先用 ListIdentifiers 探测某个已知 setSpec 是否真的挂了记录，不能直接假设 ListSets 里列出的名字都能拿来单独过滤**，标 `[UNRESOLVED]`。

---

## 6. 覆盖年限（早年边界问题）

**矛盾证据**（均 LIVE 实测，非猜测）：

1. OAI `Identify.earliestDatestamp = 2020-06-02T17:44:16Z`
2. 但 §5.2 样本记录 `datestamp=2021-09-12`（导入/修改时间）对应的文章 `dc:date=2019-07-21`（真实发表日期），Vol.33=AAAI-19（2019）——**证明 `datestamp`/`earliestDatestamp` 反映的是 OAI 记录入库/修改时间，不是原始发表年份**，2019 年内容确定存在于本 OJS。
3. About 页官方原文（见 §7）："proceedings **was first published in 1980**"——但这是 AAAI proceedings **系列**的历史起点陈述，**不代表 ojs.aaai.org 这个 OJS 平台实例本身把 1980 年的内容也收录/迁移上来了**（很可能早年内容根本不在这个 OJS 部署里，而是别处的静态归档）。

**结论：`[UNRESOLVED]`**——本次预算内没有确认 ojs.aaai.org 实际可浏览的最早卷号/年份。已确认的下界是 **2019**（Vol.33/AAAI-19 有 live 记录），上界是当前 **2026**（Vol.40/AAAI-26）。1980–2018 年内容是否在本 OJS 实例、以何种 URL 形态存在，**未验证，需实现期专项核实**（建议方法：OAI-PMH 全量收割后按 `dc:date` 排序取最小值，比翻 HTML archive 页更省请求数——HTML 翻页没有跳页功能，若要翻到最早会消耗大量请求）。

**对 adapter 范围的影响**：如果早年（1980s–2018）确实不在本 OJS 实例，则这部分年份**不属于 `aaai_ojs` adapter 的覆盖范围**，需要另一个 adapter/数据源（旧稿提到的 `aaai.org/Library` 静态归档，本次未勘察，超出本次任务范围）。建议重写文档时明确写"本 adapter 覆盖范围下界为 2019 年附近（待精确核实），更早年份为界外，由其他 adapter 负责"，而不是笼统写"覆盖 1980、1982–2026"。

---

## 7. robots.txt 全文 + 版权声明

**[LIVE]** `GET /robots.txt` → 200：

```
User-agent: *
Disallow: /cache/
```

全文仅此两行。**无 `Crawl-delay`，无按 UA 区分的规则，无 sitemap 声明**。`/cache/` 路径与本 adapter 需要的 `/index.php/...` 路径无关，**对本 adapter 完全不构成限制**。

**[LIVE]** About 页版权与开放获取声明原文（`/index.php/AAAI/about`，节选，逐字引用 <15 词/条）：

> "provide them in open access to the entire worldwide scientific community"

> "Copyright to individual papers...is fully owned by...AAAI. Permission is required for republication."

**解读**：官方立场是"面向全球科研社区开放获取（可读）"，**但明确保留版权、转载/再出版需另行许可**——这不是 CC-BY 之类的开放许可，是"免费只读"。爬虫的合规定位应表述为"个人研究用途的只读镜像抓取"（与本次勘察自己使用的 UA 字符串"personal research"一致），**不应在设计文档里写成"开放许可可自由分发"**。

同页还确认：AAAI 是 **CrossRef** 参与方（DOI 由此分配，印证 §3 DOI 前缀 `10.1609`）；proceedings 系列 1980 年首次出版；1981/85/89/95/2001/03/09 与 IJCAI 联合出版（见 §2.4 关于"个别年份存疑"的解释）。

---

## 8. 反爬实测

**[LIVE]** 20 次实测请求（含 1 次 302→200 的跳转对）headers 逐一检查：

- **无 Cloudflare**：所有响应 `server: nginx`，无 `cf-ray`/`cf-mitigated` 等头。
- **无 CAPTCHA/挑战页**：全部请求要么按预期返回内容，要么返回语义明确的错误码（403/404/302），无"Checking your browser"之类拦截页面。
- **无限速信号**：全程无 429，无 `Retry-After` 头。
- **状态码分布**：200×14、302×2（1×PDF 跳转 + 1×未发布 issue 跳登录）、403×2（REST API 两次探测）、404×1（故意构造的不存在文章 ID）。
- Set-Cookie 每次请求都下发新的 `OJSSID`（session cookie），但**读取公开页面并不需要携带/维持该 cookie**（本次每条请求都是独立新连接、未做 cookie jar 复用，均正常 200），说明该站点不依赖 session 做匿名读取的准入控制。

**结论**：ojs.aaai.org 对匿名 HTTP 客户端**没有部署可观测的反爬机制**（无 CDN 挑战、无速率硬限制信号），旧稿"无防护"的表述成立。真正的访问限制是**应用层的 REST API 403**（见 §5.1），不是网络层的反爬产品。

---

## 9. 失败模式 / 空态

**[LIVE]** 两种"找不到"语义有明确区分：

| 场景 | 实测 URL | 结果 |
|---|---|---|
| 文章 ID 确定不存在 | `/article/view/999999999` | **HTTP 404**，body 仅 `<h1>404 Not Found</h1>` |
| Issue ID 存在但未发布/内部占位 | `/issue/view/1` | **HTTP 302 → `/login?source=...`**，非 404 |

**对 error_class 映射的建议**：404 → `gone`（明确不存在，符合旧稿设计）；302 跳登录 → 不应归为 `gone`，应视为"存在但不可匿名访问"（可能是未发布 issue、也可能是权限限制内容），旧稿 §5 失败模式表未覆盖这个分支，建议补充一行。

---

## 10. 锚点规模数据

**[LIVE]** 已直接实测的具体数字（AAAI-26/2026/Vol.40，因为这是勘察当下的"最新一届"；旧稿写的"AAAI-38/2024"按 §2.4 推算约等于 Vol.38，未直接抓取，作为对照仅供参考）：

- Vol.40 全届共 **48 个 issue**（"published in 48 consecutive issues"，issue 描述原文）。
- No.1 单期（子赛道 "Application Domains I"）：**94 篇文章、840 页**。
- OAI-PMH 全库（不分年份、不分 venue-within-AAAI-family）总记录数：**26,185 条**（`completeListSize`，含 AAAI 主会 + IAAI + EAAI + 各类 special track/symposium）。
- issue 描述原文还提到 AAAI-26 **投稿量**（非收录量，仅作规模背景）："Nearly 29,000 papers were submitted to the Main Technical Track, with roughly 23,000 remaining under review after policy compliance filtering."

**未直接测得**：Main Technical Track 单届**最终收录**总篇数精确值。若按 No.1 期 94 篇线性外推到全部 48 期会得出约 4500 篇的量级，但**issue 之间规模很可能不均匀**（No.1 恰好是最大的子 track 之一），**外推不可靠，不建议写入设计文档当作准确数字**；建议实现期用 OAI-PMH 全量收割后按 `dc:source`/`citation_volume=40` 精确统计，比人工外推靠谱。作为"量级"参考，千位数到接近五千的区间是合理预期（不精确）。

---

## 附：请求清单（共 20 次实际 HTTP 请求，预算 25）

| # | 方法 | URL | 结果 |
|---|---|---|---|
| 1 | GET | `/robots.txt` | 200 |
| 2 | GET | `/index.php` | 200 |
| 3 | GET | `/index.php/AAAI/issue/archive` | 200 |
| 4 | GET | `/index.php/AAAI/api/v1/issues?count=100` | 403 |
| 5 | GET | `/index.php/AAAI/oai?verb=Identify` | 200 |
| 6 | GET | `/index.php/AAAI/oai?verb=ListSets` | 200 |
| 7 | GET | `/index.php/AAAI/oai?verb=ListRecords&metadataPrefix=oai_dc&set=AAAI:2023-11` | 200（noRecordsMatch） |
| 8 | GET | `/index.php/AAAI/api/v1/issues`（无参数复核） | 403 |
| 9 | GET | `/index.php/AAAI/oai?verb=ListRecords&metadataPrefix=oai_dc` | 200 |
| 10 | GET | `/index.php/AAAI/issue/view/683` | 200 |
| 11 | GET | `/index.php/AAAI/article/view/36958` | 200 |
| 12 | HEAD(-L) | `/index.php/AAAI/article/view/36958/40920` | 302 |
| 13 | ↳ 跳转 | `/index.php/AAAI/article/download/36958/40920` | 200 |
| 14 | GET | `/index.php/AAAI/issue/archive/2` | 200 |
| 15 | GET | `/index.php/AAAI/issue/view/1` | 302→login |
| 16 | GET | `/index.php/AAAI/article/view/999999999` | 404 |
| 17 | GET | `/index.php/AAAI/about/submissions` | 200 |
| 18 | GET | `/index.php/AAAI/about` | 200 |
| 19 | GET | `/index.php/ICWSM/issue/archive` | 200 |

（表格 19 行对应 20 次 HTTP 请求，因 #12/#13 是一次 `curl -L` 内的两跳）

原始响应（headers + body）保存于 `/private/tmp/claude-501/-Users-fhgs-Projects-Paper-Crawler/9018ef45-ff1b-4ec2-bb34-b85c84a63542/scratchpad/aaai-raw/`，供重写时复核。

---

## 11. 全库收割统计 [LIVE 2026-07-23]

> 独立预算线任务（Phase 2 检查单 #3 → Phase 3 报告 §6 检查单 #8，跨 3 Phase 清账）。方法：
> 隔离脚本（不经 `paper_crawler` 的 DB/pipeline/config/`PAPER_CRAWLER_HOME`，只复用零网络的
> `_oai.py` 信封层 + `aaai_ojs/parse.py` `oai_dc` 体层解析）直连 `GET
> https://ojs.aaai.org/index.php/AAAI/oai?verb=ListRecords&metadataPrefix=oai_dc` +
> `resumptionToken` 翻页；UA `PaperCrawler/0.1.0 (personal research; mailto:yhyfhgs@gmail.com)`；
> 限速 2.1s/请求（≤30rpm，NFR-4 上限内留安全余量）；产出=统计，不落库、零 PDF 下载。逐请求
> 台账（页号/状态/耗时/记录数/累计数/`resumptionToken`）见 §11.6。

### 11.1 总记录数对账

| 指标 | 值 |
|---|---|
| OAI `completeListSize`（服务端声明，全程稳定复现） | **26185**（与 2026-07-21 勘察 §5.2/§10 完全一致，2 天内无漂移） |
| 成功翻页数 | 246 页（234 页主扫描 + 12 页补充窗口，均 100 条/页） |
| 已取回原始记录槽位 | 24600（246×100） |
| 其中墓碑（`<header status="deleted">`，OAI 合法删除标记） | **1048**（占已取回槽位 **4.26%**） |
| **活记录（非墓碑，DOI 去重后）** | **22352** |
| 解析失败（`PARSE`） | 0 |
| DOI-卷号 反解 失败（`volume=None`） | 0（22352 条全部命中 `aaai.v{V}i` 形态） |
| 覆盖进度 | 234/262 估算页 ≈ **89.3%**（原始槽位口径）；未覆盖尾部主要是 AAAI-26/Vol.40 尚未扫到的后段 issue（见 §11.5） |

**对账结论**：`completeListSize=26185` 是"含墓碑的全部历史记录数"，**不是活论文数**。按已取回样本的墓碑率（4.26%）外推，全库活论文数量级约 **25000 上下**（外推值，非精确值——外推假设墓碑率在未覆盖尾部同分布，未验证）。22352 是本次**实测下限**（已确认活记录，覆盖 17 个届、除 Vol.40 外其余 16 个届均呈完整结构）。

### 11.2 按年/卷分布表（DOI-卷号 partition）

`Vol = 年份 − 1986` 公式经本次实测**从 Vol.33=2019 一路验证到 Vol.24=2010，17 个届无一例外、无缺口**（此前设计文档仅锚定 2 点线性推断中间年，现为逐届实测）：

| Vol | 年 | 活记录数 | 覆盖状态 |
|---|---|---|---|
| 24 | 2010 | 333 | 完整（结构自洽：3 个 issue 全见，No.1 AAAI + No.2 IAAI + No.3 EAAI） |
| 25 | 2011 | 329 | 完整 |
| 26 | 2012 | 383 | 完整 |
| 27 | 2013 | 277 | 完整 |
| 28 | 2014 | 474 | 完整 |
| 29 | 2015 | 674 | 完整 |
| 30 | 2016 | 691 | 完整 |
| 31 | 2017 | 786 | 完整 |
| 32 | 2018 | 1102 | 完整 |
| 33 | 2019 | 1343 | 完整 |
| 34 | 2020 | 1865 | 完整 |
| 35 | 2021 | 1961 | 完整 |
| 36 | 2022 | 1624 | 完整 |
| 37 | 2023 | 2023 | 完整 |
| 38 | 2024 | 2865 | 完整 |
| 39 | 2025 | 3486 | 完整（issue 结构收尾完整，见 §11.4） |
| 40 | 2026 | 2136 | **部分**——只扫到 No.1–24（AAAI-26 已知共 48 个 issue，survey §2.3），Vol.40 真实活记录数应显著高于 2136 |

"完整"判据：该卷的 issue "No." 序列在实测数据中呈现自洽收尾结构（详见 §11.4 逐卷 issue 描述表），且卷内 `dc:date` 年份高度单一集中（无跳变），两者均与"仍在扫描中途"的 Vol.40（序列在 No.24 处硬性截断、无收尾 issue）形成对照。**唯一确认不完整的是 Vol.40（AAAI-26，当前届）**——其余 16 个届（2010–2025）均无此类截断信号。

**逐年 `dc:date` 直方图**（活记录，含跨卷少量"回填/勘误"晚期日期噪声——如 Vol.26 的 383 条里 362 条 `dc:date=2021` 而非 2012，疑似批量勘误/re-import 造成，属已知数据质量噪声，不影响卷号归属，DOI-卷号与 `dc:source` "Vol. N" 交叉核验 0 例不一致）：2010:333 / 2011:323 / 2012:21 / 2013:275 / 2014:474 / 2015:674 / 2016:691 / 2017:786 / 2018:1102 / 2019:1343 / 2020:1865 / 2021:2331 / 2022:1624 / 2023:1720 / 2024:3168 / 2025:3486 / 2026:2136。

### 11.3 UNRESOLVED① 结论：1980–2018 是否在本 OJS 实例——**推翻原判断，确认在库（至少到 2010/Vol.24）**

**原勘察（2026-07-21，§6）判断**："覆盖下界只锚定到 2019（Vol.33），更早届 `[UNRESOLVED]`"——该判断基于 20 请求的小样本，**未及扫到早期卷**。

**本次全库收割结论**：**推翻上述假设**。实测直接取回 **Vol.24–32（2010–2018，9 个届）活记录 5049 条**，最早 `dc:date=2010-07-03`（`10.1609/aaai.v24i1.7532`，"The Tree Representation of Feasible Solutions for the TSP with Pickup..."）。`Vol=年份−1986` 公式从 2019 一路验证到 2010 无缺口无异常，且这 9 个届的 issue 结构均完整自洽（§11.4），不是扫描中途的假象。

**残留不确定性（如实标注，非可回避的严谨性缺口）**：本次收割在到达 Vol.24 之前于 89.3% 处因站点侧连续 5xx 中止（§11.6），**理论上不能 100% 排除 Vol.24 更早（1980s–2009，About 页"1980 首次出版"提及的年代）也在本 OJS 实例**——但证据倾向于 Vol.24/2010 就是本实例真实下界：①已收割的 89.3% 已覆盖 datestamp 2021-09 到 2026-03 近乎全跨度（非仅早期一段，说明分页顺序不是"先老后新"的简单卷序，未见 Vol.24 以下卷号出现于任何已扫描页）；②`Vol=年份−1986` 线性关系连续 17 个届无一异常，与"某处存在断层/额外历史卷"的假设不吻合；③About 页"1980 年首次出版"极可能指 AAAI proceedings **系列**史（纸质/别处静态归档），而非这个 OJS 平台实例的收录史——与原勘察 §6 的推测方向一致，现由实测部分证实（**下界确认前移 9 年，从 2019→2010**，但未证明等于系列全史 1980）。**结论：`[UNRESOLVED]` 部分闭合**——"2019 是下界"已被推翻确认为假；"OJS 实例下界＝Vol.24/2010"是本次实测的最强证据支持结论，但非 100% 穷尽验证（差 10.7% 未扫，需要一次补完收割彻底排除 Vol.<24 存在的可能，预算 ≤30 请求可完成，见 §11.5）。

**对 adapter 范围的影响（留待主 agent 裁决，非本次擅自变更）**：`venues/cs_ai/aaai.yaml` 的 `quirks.volume_map` 目前只登记 2019→33…2026→40（8 个届），**本次实测证明至少还有 Vol.24→2010…Vol.32→2018 共 9 个届可用同一 adapter/同一 OAI 端点收割**——是否扩容 `volume_map`、`tests/fixtures/aaai/dblp-aaai-anchor.json` 是否新增对应行，属 adapter 覆盖范围的架构决策（AGENTS.md §7：架构决策须主 agent 裁决），本次只如实记录发现、不擅自扩容 `volume_map`（扩容会联动 `discover_timeline`/`enumerate_issue`/D-019 锚点表/AC 判据，超出本次"统计与文档"授权范围）。

### 11.4 UNRESOLVED③ 结论：IAAI/EAAI 是否独立 issue——**独立 issue，但编排方式随时代 4 次演变**

**方法**：逐记录抽取 `dc:source` 的"Vol. N No. M: `<issue 描述>`"片段，同 (volume, No.) 聚合出**逐 issue 的官方描述文本**（比 OAI `<header><setSpec>` 更可靠——setSpec 是主题/track 分类轴，例如 `AAAI:TP`/`AAAI:AISI`，与"是否 IAAI/EAAI 刊物"这条轴部分正交；已实测发现 576 条 issue 描述文本含"IAAI/EAAI...Special"但 setSpec 未打 IAAI/EAAI 标签的情形，故 issue 描述文本判据优先）。**结论：IAAI/EAAI 论文确实占用独立于主赛道的 issue 号**，但同一件事在 17 个届里经历了 4 种不同编排：

| 时期 | 届 | 结构 |
|---|---|---|
| **① 三分体制**（2010–2014） | Vol.24–28 | 每届固定 **3 个 issue**：No.1=AAAI 主会、No.2=IAAI（Innovative Applications）、No.3=EAAI（Symposium on Educational Advances） |
| **② 二分体制**（2015–2017） | Vol.29–31 | 每届 **2 个 issue**：No.1=AAAI、No.2=IAAI；EAAI 不再单独成 issue（个别 EAAI 论文改为并入 No.1，经 `setSpec` 抽样确认仍可辨识） |
| **③ 归并体制**（2018–2019） | Vol.32–33 | Vol.32 仅 **1 个 issue**（No.1，IAAI 描述文本消失）；Vol.33 仍 1 个 issue 但 `dc:source` 显式并列"AAAI-19, IAAI-19, EAAI-20"——三者挂同一 issue 号，个体层面不可由 issue 号区分 |
| **④ 多 Track + 尾部合并 issue 体制**（2020–2025，现行） | Vol.34–39 | 主赛道拆成 **10~25 个"Technical Tracks N"** 顺序 issue，**末尾追加 1 个（Vol.34 例外为 2 个）专属 issue** 把 IAAI + EAAI + Special Programs/Special Track + Student Papers/Undergraduate Consortium 打包：Vol.34→No.9（`EAAI-20 / AAAI Special Programs`，另 No.8 为 `AAAI-20/IAAI-20` 混合 Technical Track）、Vol.35→No.17、Vol.36→No.11、Vol.37→No.13、Vol.38→No.21、Vol.39→No.28（尾号随主赛道 track 数逐年增长同步后移） |

**AAAI-26/Vol.40 现状**：本次只扫到 No.1–24（全为纯 Technical Tracks，未见 IAAI/EAAI 标记），未及体制④预期的尾部合并 issue（按 Vol.39 的 No.28 类推，Vol.40 的尾部 issue 号大概率 > No.24，因主赛道 track 数逐年增长）——**该届 IAAI/EAAI 具体 issue 号本次未直接实测到，但按体制④连续 6 届（2020–2025）零例外的强规律，几乎确定同构存在，只是本次收割尾部未及**。

**结论**：`[UNRESOLVED]` **闭合**——IAAI/EAAI 在有独立标识的历史时段（2010–2017、2020–2025，共 14 个届）**确凿占用独立 issue 号**（体制①②各自专属 No.、体制④共享 1 个尾部合并 issue 号）；仅 2018–2019（体制③，2 个届）例外，与主赛道共享同一 issue 号、个体记录不可由 issue 号区分（需 `dc:source` 全文或作者列表等其它信号，超出 OAI 结构化字段能力）。此结论来自 `dc:source` 官方 issue 描述文本的**穷尽枚举**（17 个届 × 全部已扫 issue 号，非抽样），置信度高。

### 11.5 未覆盖部分与建议

- **AAAI-26/Vol.40 尾部**（No.25 起，含推定的 IAAI/EAAI/Special 合并 issue）：本次预算耗尽前未扫到，估计尚缺约 2000+ 条（按 No.1–24 均值外推，量级参考非精确值）。
- **Vol.24 以下**（是否存在 1980s–2009 内容）：§11.3 已给出高置信度间接证据支持"不存在"，但未做穷尽排除。
- **建议补跑**：一次 `from=<Vol.40 已知最新 datestamp 之后>` 窗口收割（预算 ≤30 请求）可大概率补完 Vol.40 尾部；穷尽排除 Vol.24 以下另需一次独立小预算收割（关注是否出现任何 `v2Ni`/`v1Ni` 等更小卷号的 DOI，或 `dc:date` < 2010-07-03 的记录）。

### 11.6 请求台账摘要

| 阶段 | 请求数 | 结果 |
|---|---|---|
| 站点连通性诊断（收割开工前，发现瞬时 HTTPS 中断并等到自愈；含收割脚本 1 请求冒烟验证） | ~12 | 9 失败（TLS/连接层，未达应用层）+ 3 成功 |
| 主扫描（全量 `ListRecords`，无 `from` 窗口，按 DOI 卷号 partition） | 237 | 234 页成功（100 条/页）+ **连续 3 次 HTTP 500**（同一 `resumptionToken` 复现，触发红线停手） |
| 停手后诊断（确认 500 是否瞬时：立即重试 1 次 + 冷却 70s 重试 1 次，均复现 500；判定为该 cursor 位置的服务端持续性故障，非瞬时抖动） | 3 | 3× 500（同一 URL 可复现，非概率性） |
| 补充窗口尝试 A（`from=2026-03-17` 绕开故障 cursor，预算硬顶 34） | 3 | 3× 连接层失败（二次瞬时中断，SSL EOF），预算顶戳未耗尽即中止 |
| 连通性恢复确认（间隔 20s 轮询，≤6 次） | 5 | 4 失败 + 1 恢复（200） |
| 补充窗口尝试 B（同窗口，预算硬顶 12，恢复后重试） | 12 | 12 页全成功，但与主扫描时间窗高度重叠——**去重后 0 条净新增**（DOI 主键去重验证有效） |
| **合计** | **~272 / 280 硬顶** | 246 页有效数据（23552 条，去重后 22352 条活记录）；红线触发 1 次（如约停手）；两段站点侧瞬时不稳定（非本方限速问题——全程未见 429/`Retry-After`，且 5xx 集中于单一 cursor 位置，非全站性） |

逐请求明细（页号/URL/状态码/耗时/记录数/`resumptionToken`/时间戳）落盘于隔离 scratchpad（`aaai-harvest/ledger.jsonl`，非 git 产物，本仓不留存原始台账文件，仅本节摘要入库）。

---

## 12. UNRESOLVED 专项在线核实尝试 [LIVE 2026-07-24] — 站点侧持续性故障，BLOCKED

> Phase 5 开工检查单 #5 分派本 agent 核实 aaai_ojs **2 项**（另 2 项 ①1980–2018 覆盖、③IAAI/EAAI 独立 issue 已由 2026-07-23 §11 全库收割闭合，不在本次范围）：
> - **项②**：「AAAI-38」式**届序号**命名 vs 站点 `Vol.N`/`AAAI-YY` 品牌名对应关系（§0/§2.4，`site-survey:29,166`）——原为 `[UNRESOLVED，高置信推断]`（Vol.38↔2024↔站点品牌 `AAAI-24`）。
> - **项④**：`ListSets` 展示的 setSpec 与 `ListIdentifiers`/`ListRecords` 实际可查询 setSpec 的层级/命名差异（§5.2，`site-survey:284`）——原 `set=AAAI:2023-11` 单独过滤返回 `noRecordsMatch`，疑 ListSets 名与可查询名不一致。

**结论（2026-07-24 判定）：两项均 `[UNRESOLVED 维持]`——2026-07-24 核实窗内 `ojs.aaai.org` 应用层持续性故障，判 BLOCKED，如约停手、未对抗。**

**[已闭合，LIVE 2026-07-26，Phase 6 M1-b 在线闭合批]**：`ojs.aaai.org` 已恢复（`GET /robots.txt`→200），按下方"移交 controller"段落方法以 5/6 请求闭合两项——

- **项②**：`OAI ListIdentifiers set=AAAI:2024-149` 取 Vol.38(2024) 记录 identifier，`GetRecord` 直取 `dc:source` = `"...Vol. 38 No. 9: AAAI-24 Technical Tracks 9; 10280-10287"`——**逐字串确认 Vol.38↔2024↔品牌名 `AAAI-24`**，`Vol=年份−1986` 公式（38=2024−1986）吻合，此前"低风险但未直接实测"的缺口已补齐。
- **项④**：重测 `set=AAAI:2023-11` 仍 `noRecordsMatch`（复现，非瞬时）；但 `set=AAAI:2024-149`（同为数字型 `AAAI:{year}-{trackId}`）**成功返回 16 条记录**。结论：`set=` 过滤机制本身正常工作，`ListSets`/`ListIdentifiers` 之间**不存在系统性命名或层级不一致**；`AAAI:2023-11` 的 `noRecordsMatch` 是该 setSpec 自身的数据问题（该 track 编号在 2023 年可能零挂载/已改号），非 API 缺陷。原"不假设 ListSets 名字均可查询、需逐个探测"的保守建议依然有效，予以保留。

详细请求台账与结论回填见 [design/adapters/aaai-ojs.md §11](../../design/adapters/aaai-ojs.md)（本文档按红线不重复记录同一台账，仅此处引用状态更新）。

**实测证据（隔离脚本，UA `PaperCrawler/0.1.0 (personal research; mailto:yhyfhgs@gmail.com)`，串行 ≥2s）**：

| 层 | 实测 | 判读 |
|---|---|---|
| DNS | `ojs.aaai.org` → 198.18.1.180（沙箱出站解析，与同批正常域 dblp/neurips 同一代理段） | 正常 |
| TCP :443 | connect OK（~5 ms） | 正常 |
| TLS | 握手 OK，`TLSv1.3` | 正常（nginx/TLS 终端在线） |
| **HTTP** | 发出 `GET /robots.txt` 后**服务器立即断开、返回 0 字节**（`RemoteProtocolError: Server disconnected without sending a response.` / curl `Empty reply from server` / HTTP2 `PROTOCOL_ERROR`），**裸 socket 手写 HTTP/1.1 复测 2 次仍 0 字节** | **应用层（OJS/PHP 后端或 nginx→后端）持续故障** |

- **尝试次数与时间跨度**：约 10 次跨 `httpx`/`curl(--http2/--http1.1)`/`openssl s_client`/裸 TLS socket 的独立探测（其中 **5 次经脚本 ledger 记录的失败连接**），覆盖 17:49→18:07（≈18 分钟），**无一次到达应用层**；期间 TCP/TLS 始终正常，排除本方网络/UA/限速问题（全程未触发 429/挑战页，纯服务端不吐 HTTP 响应）。
- **与既有勘察对照**：§11.6 已两度记录同站「站点侧瞬时不稳定（SSL EOF）」，2026-07-21/07-23 尚能自愈并完成 20 请求勘察 + 246 页收割；本次同一故障模式但在核实窗内**持续未自愈**。故属**已知的站点侧间歇性故障**，非端点消失、非反爬、非本方触发。
- **红线遵守**：连接层失败非 5xx/挑战页，但按「不重试轰炸、不对抗」精神，达成故障可复现判定后即停手，未换 UA、未绕行、未降级重试。**未产生任何成功的 aaai 请求**（4 次经脚本 ledger 记录的失败连接 + 若干裸 socket/curl 诊断，全 0 应用层响应）。

**为何无法以既有证据代替实测闭合（不编造）**：
- **项②**：`Vol=年份−1986` 映射本身已由 §11.2 全库收割**逐届实测**（Vol.24–40，17 届 DOI-卷号 partition 与 `dc:source` "Vol. N" 交叉核 0 例不一致），故「Vol.38=2024」在数据层是**硬事实**；**唯一未直接取到的是 Vol.38 issue 标题页/OAI 记录里那串品牌名 `AAAI-24` 逐字串**（本次拟以 1–3 请求直取 issue 标题或 `dc:source` "Vol. 38 … AAAI-24" 佐证，因 BLOCKED 未获）。风险评估：低——§2.4 已实测同型 `dc:source`（"Vol. 33 … AAAI-19"），品牌名=2 位年、届序号=第 N 届 的区分结论不依赖 Vol.38 单点；但严格意义上**「AAAI-24」逐字串未直接实测**，如实维持 `[UNRESOLVED 高置信]`。
- **项④**：完全依赖 live OAI 端点（`ListSets` 一次 + 带 `set` 的 `ListIdentifiers` 抽验），无任何离线替代证据可推断 setSpec 可查询性；`noRecordsMatch` 异常的成因（层级/命名/大小写/编码差异）**必须实测**。BLOCKED 下无法给出任何新结论，维持 `[UNRESOLVED]`。

**移交 controller（见终报）**：
1. **重跑窗口**：`ojs.aaai.org` 恢复后（可先裸 TLS + `GET /robots.txt` 探活确认应用层吐 200），以 ≤6 请求闭合两项：
   - 项②：取任一 Vol.38 文章详情页（`/article/view/{id}` breadcrumb 含「Vol. 38 … (2024): AAAI-24 …」）或 OAI 一条 Vol.38 记录的 `dc:source`，直取 `AAAI-24` 品牌串。获取 Vol.38 article id 的稳妥法：`ListSets`→挑 2024 相关 set→`ListIdentifiers&set=…`；若 set 过滤仍空（即项④现象），退化为 issue archive HTML 翻页至 Vol.38（约 4–5 页）。
   - 项④：`ListSets`（记 setSpec 原样）+ 对同一 setSpec 发 `ListIdentifiers&metadataPrefix=oai_dc&set={setSpec}`，比对返回 identifiers 数 vs `noRecordsMatch`；分别抽 `AAAI:{year}-{trackId}` 数字型 与 `AAAI:IAAI-DEP` 语义型 各一，定位「哪类 setSpec 可单独过滤」。
2. **`docs/design/adapters/aaai-ojs.md` 联动**（本 agent 严禁触碰该文件，由 controller 定向处理）：该设计文档若在 §2.4/§5.2 或失败模式表引用了这两项的 `[UNRESOLVED]`，重跑闭合后须同步；本次仅记录，不擅改。
