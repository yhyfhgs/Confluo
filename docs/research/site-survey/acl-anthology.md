---
title: 勘察：ACL Anthology（GitHub bulk/Findings 结构/许可二分）
status: approved
owner: fable5
updated: 2026-07-26
---

# ACL Anthology 站点勘察报告（LIVE）

- 勘察时间：2026-07-21T17:44–17:52 UTC
- UA：`PaperCrawler/0.1 (site survey; personal research)`
- 总请求数：**24 / 25**（GitHub API 4 + raw.githubusercontent.com 5 + aclanthology.org 15）
- 间隔：批内相邻请求均 `sleep 1` 显式控速（≥1s）；单批内请求有依赖时先解析上一响应再发下一请求
- HEAD 优先：PDF / 单篇 .bib / 全量 anthology.bib.gz 三处仅需存在性+元信息，均用 HEAD
- 挑战门：全程未遇到 CAPTCHA/Cloudflare 挑战页，无需记录绕过决策
- 旧稿：`docs/design/adapters/acl-anthology.md`（下称"旧稿"），逐条标注证实/证伪
- 完整请求日志见文末《请求日志》

---

## 1. GitHub Bulk 主路径（AC-2.5 核心）[LIVE]

**仓库元信息** — `GET https://api.github.com/repos/acl-org/acl-anthology` → 200
```
full_name: acl-org/acl-anthology
description: "Data and software for building the ACL Anthology."
size: 711976 KB (~695MB，git 压缩包含全history)
default_branch: master   ← 不是 main，旧稿未提及分支名，需在实现里写死 "master"
license: Apache-2.0（spdx_id）  ← 见第6节，纠正旧稿"MIT/CC"表述
pushed_at: 2026-07-21T17:18:35Z
created_at: 2014-05-23
stars: 762 / forks: 400 / open_issues: 367
homepage: https://aclanthology.org
```

**最近提交** — `GET .../commits?per_page=1&sha=master` → 200
```
sha: 18cb9a22f2
date: 2026-07-21T15:58:17Z   ← 距勘察发起仅 ~1.5 小时
message: "Checklist changes (#9253)"
```
**结论**：仓库更新频率为准实时/每日多次提交，非"定期批量更新"型仓库；`git pull` 拉取延迟可以做到很低。

**data/ 顶层结构** — `GET .../contents/data?ref=master` → 200
```
data/
├── xml/     ← 论文级元数据（本次核心）
└── yaml/    ← 人物/机构等辅助表（如 people.yaml，见 /faq/api/ 引用）
```
**关键**：data/ 下**没有** `pdf/` 或 `attachments/` 目录 —— PDF **不在此仓库中**，托管在 aclanthology.org 自己的服务器（README "Hosting a mirror" 章节明确："creating a mirror ... you have to download every single file of the Anthology from **the official webserver**"）。这与旧稿"仅 PDF 走在线"的设计吻合，且是仓库自证的强证据。

**data/xml/ 目录规模** — `GET .../git/trees/<sha data/xml>` (非递归) → 200，`truncated:false`
```
条目总数: 1661 (1660 个 *.xml 数据文件 + 1 个 schema.rnc)
xml 文件总字节数: 171,519,235 bytes (~171.5 MB)
平均单文件: ~103,325 bytes (~101 KB)
最大 5 个: 2025.findings.xml(7.79MB) > 2026.acl.xml(7.13MB) > 2026.findings.xml(6.64MB)
          > 2024.findings.xml(5.17MB) > 2025.emnlp.xml(4.89MB)
```

**命名规则实测确认**：
- 新式：`{year}.{venue}.xml`，如 `2023.emnlp.xml`（**存在**，2,266,697 bytes）
- 旧式：`{单字母}{YY}.xml`，如 `D19.xml`（**存在**，1,746,681 bytes；grep 全目录确认 D07~D19 均存在）
- 一个文件內含该 year+venue 下**多个 `<volume>`**（main/tutorial/demo/industry 等子track），**但 Findings 是例外**——见下方"结构性新发现"。

**XML Schema（RelaxNG Compact，官方权威定义）** — `GET .../data/xml/schema.rnc` → 200（4528 bytes，全文已抓取）：
```rnc
Paper = element paper {
  attribute id { xsd:positiveInteger },
  attribute ingest-date { xsd:date }?,
  attribute type { xsd:string }?,
  ( element abstract { MarkupText }?
  & attachment*
  & element bibkey { bibtex-key }
  & element author { Person }*
  & element doi { xsd:anyURI }?
  & element editor { Person }*
  & Revision*
  & element erratum {...}*
  & element retracted {...}?
  & element removed {...}?
  & element pages { text }?
  & element title { InlineMarkupText }
  & url-with-checksum?
  & element video {...}*
  & element language { xsd:language }?
  & element month { text }?
  & element year { xsd:gYear }?
  & element award { text }* )
}
Volume = element volume {
  attribute id { xsd:string }, attribute type { "journal" | "proceedings" },
  Meta, Frontmatter?, Paper*
}
Collection = element collection { attribute id { xsd:string }, Volume*, Event? }
start = Collection
```
`url-with-checksum` 允许两种形式：完整 https URL，**或**「本地文件名 + 8位hex checksum」——即多数条目里 `<url>` 内容只是不带扩展名的 anthology_id（如 `2023.emnlp-main.1`），PDF 真实 URL 需要 adapter 自行拼接 `https://aclanthology.org/{url}.pdf`。`attachment` 元素（type + checksum + local-filename）印证旧稿"attachment 按 XML 声明生成附属 AssetPlan"可行。

**新式论文实例**（`2023.emnlp.xml`，volume id="main"，paper id="1"，本地已下载全文分析）：
```xml
<paper id="1">
  <title><fixed-case>IAG</fixed-case>: Induction-Augmented Generation Framework ...</title>
  <author><first>Zhebin</first><last>Zhang</last></author>
  <!-- 共8位作者 -->
  <pages>1-14</pages>
  <abstract>Retrieval-Augmented Generation (RAG), ...</abstract>
  <url hash="0d73aa01">2023.emnlp-main.1</url>
  <bibkey>zhang-etal-2023-iag</bibkey>
  <doi>10.18653/v1/2023.emnlp-main.1</doi>
  <video href="2023.emnlp-main.1.mp4"/>
</paper>
```
`<meta><venue>emnlp</venue></meta>` 在 volume 外层的 `<meta>` 块。**abstract 字段在近年数据中完整存在**，enumerate_issue 阶段可直接拿到摘要，不必额外抓站。

**旧式论文实例**（`D19.xml`，Range 拉取前 6001 字节，collection id="D19"，volume id="1"，paper id="1"）：
```xml
<collection id="D19">
  <volume id="1" type="proceedings">
    <meta><venue>emnlp</venue><venue>ijcnlp</venue> ...</meta>
    <paper id="1">
      <title>Attending to Future Tokens for Bidirectional Sequence Generation</title>
      <author><first>Carolin</first><last>Lawrence</last></author>
      <pages>1–10</pages>
      <abstract>Neural sequence generation ...</abstract>
      <url hash="d4591cd4">D19-1001</url>
      <attachment hash="6477c456">D19-1001.Attachment.pdf</attachment>
      <doi>10.18653/v1/D19-1001</doi>
      <bibkey>lawrence-etal-2019-attending</bibkey>
    </paper>
```
ID 构造规则实测确认：`D19` (collection) + `-` + `1` (volume) + `001` (paper, 3位零填充) = `D19-1001`。**注意与新式的拼接差异**：新式用 `.` 分隔 paper 号且不零填充（`2023.emnlp-main.1`），旧式无分隔符且零填充到 3 位（`D19-1001`）——两套解析/构造正则不能共用。

### 结构性新发现（旧稿未覆盖，强烈建议写入新稿）

**EMNLP Findings 不在 `2023.emnlp.xml` 里**，而是与 ACL/EACL/IJCNLP 当年的 Findings 合并存放在同一个 **按年份不按 venue** 命名的文件 `data/xml/2023.findings.xml`（本次已全量下载验证，4,302,962 bytes）：
```
collection id="2023.findings"
  volume id="eacl"  <venue>findings</venue>  paper_count=197
  volume id="acl"   <venue>findings</venue>  paper_count=901
  volume id="emnlp" <venue>findings</venue>  paper_count=1059   ← EMNLP 2023 Findings
  volume id="ijcnlp"<venue>findings</venue>  paper_count=37
```
即 EMNLP Findings 论文的 anthology_id 形如 `2023.findings-emnlp.N`。**若 AC-2.5"回填某年 EMNLP 全量"的语义包含 Findings track，enumerate_issue 必须额外读取 `data/xml/{year}.findings.xml` 并按 volume id 过滤出该 venue 的子集**，这是一次跨文件 join，旧稿 §3 完全未提及，是本次勘察最重要的设计缺口。

### raw.githubusercontent.com 单文件拉取 vs git clone 取舍数据 [LIVE 实测 + 推算]

| 方案 | 实测/推算数据 |
|---|---|
| 单文件 raw 拉取（`2023.emnlp.xml`, 2.27MB） | 1 次 HTTP GET，实测 1.45s，Fastly/Varnish 边缘节点（`via: 1.1 varnish`），`x-cache: MISS`（首命中，未验证到缓存命中场景） |
| 单文件 raw 拉取（`D19.xml` 前6001字节 Range） | 1 次 HTTP GET + Range，实测 0.81s |
| 全量 `data/xml/` | 1660 文件 / 171.5MB，若逐文件拉取且遵守 1 req/s 礼貌间隔，仅传输时间下限 ≈ 28 分钟 + 每请求握手开销 |
| 完整仓库（含全历史） | 711,976 KB (~695MB) 压缩包大小（GitHub API `size` 字段） |

**结论**：AC-2.5 的字面场景"回填**某一年 EMNLP**"只需 1（或 2，若含 Findings）次 raw.githubusercontent.com GET，**完全不需要 clone**——单文件拉取在这个场景下比任何形式的 clone（含 `--depth 1`）都更轻量、更可审计（一条请求=一条日志证据，直接满足 AC-2.5"日志证据"要求）。`git clone --depth 1` + 定期 `pull` 更适合 discover_timeline 的**全量建目录**场景（一次性拿全 1660 个文件），旧稿 §7 的浅克隆建议应保留但明确限定其适用阶段为"全量目录"而非"单年回填"。

**GitHub API 限速实测**：`api.github.com` 未认证请求返回 `x-ratelimit-limit: 60`（/小时），本次勘察消耗 6 次后剩余 54。若 adapter 使用 `contents`/`git/trees`/`commits` 等 REST API（而非 raw.githubusercontent.com 直取文件或 `git clone`），60/hr 上限在生产中可能成为瓶颈，建议：目录发现类操作走 `git clone --depth 1` 或认证 token（5000/hr），避免依赖未认证 REST API。

---

## 2. Anthology ID 两代形态 [LIVE + 官方文档 `/info/ids/` `/faq/linking/`]

`GET https://aclanthology.org/info/ids/` → 200（更新日期 2022-02-12，权威说明）：

- **新式**（**2020年后被"摄入"的一切**，含补录的旧年份卷）：`YEAR.VENUE-VOLUME.NUMBER`
  例：`2020.acl-1.12`；卷号本身也可单独作为 ID：`2020.acl-main`
  **关键细节，旧稿未提**：新旧分界是"**摄入日期**"而非"论文实际发表年份"——2020年后新补录的历史卷仍会拿到新式 ID。
  前言（front matter）固定编号为 `0`（如 `2020.acl-srw.0`），后记（back matter）取该卷最后一个编号。
- **旧式**（2020年前摄入）：8字符 `{Letter}{YY}-{VPPP 或 VVPP}`
  例：`P18-1024`（P=ACL 专属前缀）。大型常设会议（ACL/EMNLP/NAACL 等）有专属单字母前缀，volume 1位+paper 3位（容量999）；其余用 `W` 前缀，volume 2位+paper 2位（容量99/卷，超量需拆多个 volume）。

`GET https://aclanthology.org/faq/linking/` → 200，补充：
- 官方示例用 `https://www.aclanthology.org/`（带 www），但本次对裸域 `aclanthology.org`（无 www）发出的所有请求均直接 200，两者等价可用；`<link rel=canonical>` 自身用**无 www** 形式。
- 直接后缀可取多种格式：`.pdf` / `.bib` / `.xml`（MODS）——对新旧两代 ID 均适用，旧稿只提到 `.pdf`，可补充 `.bib`/`.xml` 两个免费副产物端点。

---

## 3. 站点侧 URL 形态 [LIVE]

| 用途 | URL | 状态 | 备注 |
|---|---|---|---|
| venue 根页 | `GET /venues/emnlp/` | 200, 25832B | 列出该 venue 历年链接，每年指向 `/events/{venue}-{year}/`（1996…2026+全覆盖）|
| venue-year 事件页 | `GET /events/emnlp-2023/` | 200, **7,580,595B (7.6MB)** | 页面内联了该年所有 EMNLP 关联 volume 的题目+作者+摘要，**无** `citation_*` meta（仅列表，非详情）|
| 单篇 landing（新式）| `GET /2023.emnlp-main.1/` | 200, 44769B | 见第4节 citation_* meta |
| 单篇 landing（旧式）| `GET /D19-1001/` | 200, 40095B | 与新式 meta 结构完全一致 |

**旧稿的 `/venues/acl/`、`/events/acl-2024/` 形态实测证实**（本次用 emnlp 类比验证，模式通用）。

**新发现**：`/events/{venue}-{year}/` 页面体积可达 7MB+（内联全文摘要），比对应的 `data/xml/{year}.{venue}.xml`（2.27MB，结构化）**更大且更难解析**——这是支持"bulk 优先、网站仅兜底"设计判断的直接数据佐证，建议写入新稿"获取策略阶梯"章节作为量化理由。

### citation_* meta（landing 页，两代 ID 结构一致）
```html
<meta content="IAG: Induction-Augmented Generation Framework..." name=citation_title>
<meta content="Zhebin Zhang" name=citation_author>          <!-- 每作者一条 -->
<meta content="Proceedings of the 2023 Conference on Empirical Methods..." name=citation_conference_title>
<meta content="2023/12" name=citation_publication_date>
<meta content="https://aclanthology.org/2023.emnlp-main.1.pdf" name=citation_pdf_url>
<meta content="1" name=citation_firstpage>
<meta content="14" name=citation_lastpage>
<meta content="10.18653/v1/2023.emnlp-main.1" name=citation_doi>
<meta property="og:image" content="https://aclanthology.org/thumb/2023.emnlp-main.1.jpg">
<link rel=canonical href="https://aclanthology.org/2023.emnlp-main.1/">
```
**注意**：Hugo 渲染的属性顺序是 `content="..." name=citation_xxx`（content 在前），朴素的 `name="citation_xxx"[^>]*content="([^"]*)"` 正则会匹配失败，需要顺序无关的解析器/正则。

---

## 4. PDF URL 与托管域 [LIVE HEAD]

`HEAD -L https://aclanthology.org/2023.emnlp-main.1.pdf` → 200，0 次重定向
```
Server: Apache/2.4.41 (Ubuntu)
Content-Type: application/pdf
Content-Length: 791368  (773KB)
Last-Modified: Thu, 07 Dec 2023 15:02:37 GMT   ← 原始入库日期，非抓取当天
Accept-Ranges: bytes    ← 支持断点续传/Range
```
PDF **同域直挂**（aclanthology.org 自身 Apache，未转发到独立 CDN/S3 域名），证实旧稿 `https://aclanthology.org/{id}.pdf` 形态。

---

## 5. 空态 / 404 形态 [LIVE]

`GET https://aclanthology.org/2099.nonexistent-main.1/` → **404**, Content-Length 8019, `Content-Type: text/html; charset=utf-8`
可见文案：
> "404 The page you were looking for doesn't exist. Go back to the home page to browse the content of the Anthology, or try to use the search function (at the top) to find the content you were looking for. If you believe you're seeing this page in error, feel free to file an issue on our Github repository."

Hugo 静态站生成的统一 404 页（`meta name=generator content="Hugo 0.160.0"`），无 JSON 错误体，纯 HTML。error_class 映射可继续用旧稿的 `gone`（HTTP 404 精确匹配）。

---

## 6. robots.txt + 许可声明 [LIVE]

**robots.txt 不存在**：`GET https://aclanthology.org/robots.txt` → **404**（与上面空态 404 页字节数完全相同：8019B），即请求 robots.txt 命中的是站点通用 404 页，**不是一个"允许全部"的空 robots.txt，而是路径本身不存在**。站点没有任何机器可读的抓取策略声明，也没有 `Crawl-delay`。旧稿完全未提及 robots.txt，建议新稿明确写"经实测无 robots.txt，礼貌节流依赖项目自身 NFR-4 默认值，无站点侧机器可读依据可参照"。

**许可声明**（首页 footer + `GET /faq/copyright/` → 200，两处文案一致）：
> Materials **prior to 2016**: Creative Commons Attribution-NonCommercial-ShareAlike **3.0** (CC BY-NC-SA 3.0)
> Materials **2016 and later**: Creative Commons Attribution **4.0** (CC BY 4.0) — 允许商业与非商业使用
> "these policies only cover ACL materials"（协办的第三方素材不在此范围内）

**⚠️ 纠正旧稿**：旧稿写"XML/YAML，**MIT/CC 授权**"——实测**两处都不准确**：
1. 仓库代码许可证是 **Apache-2.0**（GitHub API `license.spdx_id`），不是 MIT；
2. 论文内容许可证**不是单一的"CC"**，而是按年份二分：2016前 CC BY-NC-SA 3.0，2016起 CC BY 4.0——非商业限制在旧内容上依然存在，crawler 若涉及再分发要按年份区分许可证元数据，不能笼统标"CC"。

---

## 7. 反爬实测 [LIVE]

- 全程 24 次请求（GitHub API 4 + raw.githubusercontent 5 + aclanthology.org 15）均**匿名**完成，无需登录/token；
- aclanthology.org 响应头仅 `Server: Apache/2.4.41 (Ubuntu)`，**无** Cloudflare/WAF 特征头（无 `cf-ray`、无 `x-sucuri`、无 `Retry-After`、无站点自定义 `X-RateLimit-*`）、无 `Set-Cookie`；
- raw.githubusercontent.com 经 Fastly（`via: 1.1 varnish`），本次样本全部 `x-cache: MISS`（未观测到缓存命中场景，样本量小不代表无缓存）；
- api.github.com 有标准 GitHub 未认证限速头（见第1节，60/hr），这是唯一观测到的"数字化"限速信号，且仅出现在 GitHub 侧而非 aclanthology.org 侧；
- 未遇到任何 CAPTCHA / JS 挑战 / 429，证实旧稿"无认证无防护"结论，但补充"GitHub REST API 60/hr 未认证上限"这个此前未记录的软约束。

---

## 8. AC-2.5 锚点：EMNLP 2023 论文计数 [LIVE，全量下载后本地精确计数]

来源：`data/xml/2023.emnlp.xml`（2,266,697 bytes，全量下载）+ `data/xml/2023.findings.xml`（4,302,962 bytes，全量下载，筛选 volume id="emnlp"）

| volume | 所在文件 | anthology_id 前缀 | 论文数 |
|---|---|---|---|
| main | 2023.emnlp.xml | `2023.emnlp-main.*` | **1047** |
| tutorial | 2023.emnlp.xml | `2023.emnlp-tutorial.*` | 6 |
| demo | 2023.emnlp.xml | `2023.emnlp-demo.*` | 52 |
| industry | 2023.emnlp.xml | `2023.emnlp-industry.*` | 77 |
| findings | 2023.findings.xml (volume=emnlp) | `2023.findings-emnlp.*` | 1059 |
| **合计** | | | **2241** |

若 T5 canary 只锚定"主会 long/short"，用 **1047**；若锚定"EMNLP 2023 全部 track"，用 **2241** 且必须双文件读取（见第1节"结构性新发现"）。旧稿 §6 提到"EMNLP 2023 主会 long 论文数已知答案"但未给出具体数字，也未区分是否含 short——本次数据里 "main" 卷已经是 long+short 合并存放（单一 `<paper>` 序列，未见卷内 type 属性区分 long/short 的样本，需要在 fixture 阶段单独核实是否有 `type` 属性区分）。

---

## 9. bib / API 替代 [LIVE + 官方文档，重大发现]

`GET https://aclanthology.org/faq/api/` → 200，官方原文：
> "The Anthology's data is hosted in our Github repo, which contains all the metadata for all its papers (under /data/xml) and their authors (data/yaml/people.yaml)... The PDFs are hosted on our servers. All of this data is accessible via **the ACL Anthology Python module on PyPI**, which you can install with pip: `pip install acl-anthology`"

**没有传统 REST/JSON API**——ACL 官方把 "GitHub 仓库 + 官方 Python 包" 本身定义为"API"。存在一个官方 PyPI 包 `acl-anthology`，封装了对 data/xml + data/yaml 的读取；如果 Paper Crawler 的实现语言是 Python，这个包可能是比"手写 XML 解析"更省心的 bulk 路径备选（需评估其数据模型是否贴合本项目 schema-v1，超出本次勘察范围，标记为后续可选调研项）。

`GET https://aclanthology.org/faq/bib/` → 200，官方原文确认存在**批量 BibTeX 导出**：
- `anthology+abstracts.bib.gz` —— 全量，含摘要
- `anthology.bib.gz` —— 全量，不含摘要（体积更小）
- `anthology.bib` —— 同上，未压缩
- `anthology-1.bib` / `anthology-2.bib` … —— 分片版，单片 <50MB，供 Overleaf 直接引用
- 单篇：BibTeX / MODS XML / EndNote / 纯文本引用串，页面按钮可下载或复制
- "we also offer an XML paper feed, which is useful in tools like Zotero and Mendeley" —— 疑似首页导航看到的 `/papers/index.xml`，本次**未验证**，标 `[UNRESOLVED]`

**LIVE HEAD 验证**：
```
HEAD https://aclanthology.org/anthology.bib.gz → 200
  Content-Length: 12,357,126 (~11.8MB)
  Content-Type: application/x-gzip
  Last-Modified: 2026-07-21T16:03:37Z   ← 与当天 GitHub 最新提交(15:58)几乎同步，说明 bib 导出随站点构建同步再生成

HEAD https://aclanthology.org/2023.emnlp-main.1.bib → 200
  Content-Type: text/plain; charset=utf-8
```

**评估**：bib 批量导出是真实存在的官方 bulk 端点，但**信息密度低于 XML**（无 abstract 分年份可选、无 attachment/video/checksum 等结构化字段），不适合作为 enumerate_issue 的主数据源；更适合作为 GitHub XML 路径的**独立交叉核对**（校验 paper_count / DOI 一致性）或未来"导出对账"类功能的数据源，不建议替代 data/xml 路径。

---

## 与旧稿的证实/证伪汇总

| 旧稿断言 | 判定 | 依据 |
|---|---|---|
| GitHub bulk 仓库含全量结构化元数据（XML/YAML） | ✅ 证实 | §1，data/{xml,yaml} 结构确认 |
| 仓库授权 "MIT/CC" | ❌ 证伪 | §6：代码 Apache-2.0；内容 CC BY-NC-SA 3.0(<2016)/CC BY 4.0(≥2016)，无 MIT |
| venue 页 `/venues/acl/`、事件页 `/events/acl-2024/` | ✅ 证实（emnlp 类比验证） | §3 |
| Anthology ID 两代（新式2020+ / 旧式前缀） | ✅ 证实，需补细节 | §2：分界是"摄入日期"非"发表年份"；P/W 前缀位宽不同 |
| PDF 直链 `https://aclanthology.org/{id}.pdf` | ✅ 证实 | §4：同域 Apache 直挂，无重定向 |
| 无认证无防护 | ✅ 证实，需补充 | §7：站点侧真无防护；GitHub REST API 侧有 60/hr 未认证限速 |
| enumerate_issue "全程无在线请求" | ⚠️ 需限定范围 | §1 结构性新发现：若含 Findings track 需读取额外的 `{year}.findings.xml`，但仍是 bulk 文件，不违反"无在线抓取"原则 |
| COLING/ICCL 非 ACL 学会但同库收录 | 未复核 | 本轮 9 项清单未覆盖，标 `[DOC]`（沿用旧稿，未重新验证）|
| NAACL/EACL 非每年举办 | 未复核 | 同上，`[DOC]`；间接观测到 2023.findings.xml 含 eacl volume，弱佐证 EACL 2023 确实举办，非直接证据 |

---

## 请求日志（24条，全部成功，无429/挑战页）

```
17:44:17Z GET api.github.com/repos/acl-org/acl-anthology                                    200
17:44:19Z GET raw.githubusercontent.com/.../master/README.md                                200
17:44:20Z GET api.github.com/.../contents/data?ref=master                                   200
17:44:22Z GET api.github.com/.../commits?per_page=1&sha=master                              200
17:45:29Z GET api.github.com/.../git/trees/<data/xml sha>                                   200
17:46:03Z GET raw.githubusercontent.com/.../data/xml/schema.rnc                             200
17:46:05Z GET raw.githubusercontent.com/.../data/xml/D19.xml (Range 0-6000)                 206
17:46:07Z GET raw.githubusercontent.com/.../data/xml/2023.emnlp.xml                         200
17:48:16Z GET raw.githubusercontent.com/.../data/xml/2023.findings.xml                      200
17:48:57Z GET aclanthology.org/robots.txt                                                   404
17:48:59Z GET aclanthology.org/                                                             200
17:49:01Z GET aclanthology.org/events/emnlp-2023/                                           200
17:49:10Z GET aclanthology.org/2023.emnlp-main.1/                                           200
17:49:12Z GET aclanthology.org/D19-1001/                                                    200
17:49:14Z GET aclanthology.org/2099.nonexistent-main.1/                                     404
17:50:37Z GET aclanthology.org/faq/api/                                                     200
17:50:38Z GET aclanthology.org/faq/bib/                                                     200
17:50:40Z GET aclanthology.org/faq/copyright/                                               200
17:50:42Z GET aclanthology.org/info/ids/                                                    200
17:50:44Z GET aclanthology.org/faq/linking/                                                 200
17:50:45Z HEAD(-L) aclanthology.org/2023.emnlp-main.1.pdf                                   200
17:50:47Z HEAD aclanthology.org/2023.emnlp-main.1.bib                                       200
17:52:22Z HEAD aclanthology.org/anthology.bib.gz                                            200
17:52:24Z GET aclanthology.org/venues/emnlp/                                                200
```

## 10. 补充勘察：attachment/SI URL 前缀 HEAD 核实 [LIVE 2026-07-26]

> 背景：§1 已实证 `<attachment>` 元素结构与「附件不在 GitHub 仓库、托管 aclanthology.org」，但原 24
> 请求预算内未 HEAD 确认路径前缀，design/adapters/acl-anthology.md §4/§8 因此标 ⚠ [UNRESOLVED]①
> （实现期首个 SI fetch 前须 HEAD 核实）；2026-07-24 审计（reports §3 S1 域）确认其零在线验证。本次
> 按该实现期义务补勘。预算：Phase 6 计划 §3「机动」批次（≤10）划支 **1** 请求（余 9）。
>
> 分工合规：架构裁决（预算划支 + AC-2.5 限定语撤除）与文档定稿由主 agent（fable）完成（AGENTS §7）。

- **样本**：`D19-1001.Attachment.pdf`——取自 §1 抓取的真实 `D19.xml` 数据（`<attachment
  hash="6477c456">` 样例见 §1；同值已 verbatim 入 fixture
  `tests/fixtures/acl_anthology/03_d19_legacy_excerpt.xml`，非合成值）。
- **方法**：单次 `curl -I`（HEAD、不跟随重定向），UA 按 D-014 `PaperCrawler/0.1.0 (personal
  research; mailto:<contact>)`。站外手工核实的理由：冻结 `HttpClient` 无 HEAD 方法（design §6 已知
  限制④），本核验本就是设计文档规定的实现期一次性人工义务；§6 实测本站无 robots.txt/无
  Crawl-delay，单请求远在 NFR-4 节流下界内。
- **结果：200，前缀证实**。完整响应头：

```
HTTP/1.1 200 OK
Date: Sat, 25 Jul 2026 20:22:27 GMT
Server: Apache/2.4.41 (Ubuntu)
Last-Modified: Sun, 03 Nov 2019 20:55:33 GMT
ETag: "e97c8-596776b97fc5a"
Accept-Ranges: bytes
Content-Length: 956360
Content-Type: application/pdf
```

- **证据链**：`Content-Type: application/pdf` + 956,360 字节实体 ⇒ 真文件非软 404/占位页；
  `Last-Modified: 2019-11-03` 与 D19 卷 `ingest-date="2019-11-03"`（§1）**精确吻合** ⇒ 该路径
  服务的正是当次数据摄入的附件本体；Apache/2.4.41 直挂、0 重定向、`Accept-Ranges: bytes` 与 §4
  PDF 直链观测同构 ⇒ attachments 与 PDF 同一托管形态。
- **结论**：`https://aclanthology.org/attachments/{local-filename}` 构造**正确**。`resolve_assets`
  现行实现与单测断言（`test_resolve_assets_produces_si_plan_per_attachment`）无需改动；design
  §4/§8 [UNRESOLVED]① 就此闭合。

### 请求日志（1 条，成功）

```
2026-07-25T20:22:27Z (UTC, 响应 Date 头)  HEAD aclanthology.org/attachments/D19-1001.Attachment.pdf  200
```
