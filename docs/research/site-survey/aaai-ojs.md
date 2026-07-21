---
title: 勘察：AAAI OJS（OAI-PMH 主路径/分页/覆盖边界）
status: approved
owner: fable5
updated: 2026-07-22
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
