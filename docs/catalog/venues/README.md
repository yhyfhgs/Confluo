---
title: venue 名录（按学科）
status: draft
owner: opus5.5-primary
updated: 2026-09-28
---

# venue 名录（按学科）

> 本目录按 12 个学科组列出 L1a 期刊与会议，共 866 个：期刊 719、会议 135、期刊化会议论文集 12，其中中国主办英文刊 44 个、中文刊 121 个，746 个带评级标签。每个 venue 标出出版托管主体（M1）、评级、收录它的学科库（L2a）、对应的预印本或 WP 通道（L1b），以及 Confluo 的接入方式。评级体系见[评级体系](../venue-rankings.md)，七类分层见[来源分层](../source-taxonomy.md)。

## 要点

- **学科**：覆盖数学、物理与天文、化学、地学、材料、生命科学与医学、心理与认知、经济、金融、商业与管理、计算机与 AI，外加跨学科综合；中文刊按主属学科分进各文件末尾的"中文刊"一节。
- **接入**：600 个经 Crossref 按 ISSN 委托收元数据；139 个经名录里已有的来源行（`现有:`、`平台:`）；95 个中文刊只接受用户导入；28 个待勘察，主要是经管会议；4 个经 dblp 快照。
- **评级覆盖**：CS 最完整（CCF 128、ICORE 83、THCPL 79、CAAI 70）；经管有 FMS、ABDC、VHB、FT50、UTD24；理科主要靠科协 T 级与 Nature Index。物理、化学、心理没有本学科的科协目录，T 标签来自相邻学会，括号里写明学会。
- **规模**：名录是"核心 + 名录覆盖"，不是全集。CCF-B/C、ABDC-A 以下与各学科长尾刊没有收；用户关注任意期刊时，由 Crossref 或 OpenAlex 自动建 venue（策展等级 `auto`，见 03）。
- **许可**：ABDC、FT50、VHB 的标注只作内部设计参考，产品里在许可确认前只接受用户导入；中科院分区与 JCR 不标。

## 数字概览

| 学科组 | venue | 期刊 | 会议 | 中国主办英文刊 | 中文刊 | 带评级 | 主要评级（venue 数） |
|---|---:|---:|---:|---:|---:|---:|---|
| [数学](math.md) | 63 | 61 | 2 | 3 | 10 | 61 | 科协 T 60、ABDC 11、北大核心 10、FMS 10、科技核心 9 |
| [物理与天文](physics-astronomy.md) | 61 | 55 | 6 | 9 | 7 | 39 | 科协 T 29、NI 13、卓越 11、北大核心 7、科技核心 6 |
| [化学](chemistry.md) | 47 | 47 | 0 | 5 | 8 | 27 | 科协 T 14、NI 13、卓越 10、科技核心 8、CSCD 8 |
| [地学](earth-sciences.md) | 52 | 52 | 0 | 2 | 13 | 51 | 科协 T 51、科技核心 13、CSCD 13、北大核心 13、卓越 10 |
| [材料](materials.md) | 36 | 36 | 0 | 5 | 6 | 35 | 科协 T 35、卓越 8、NI 7、科技核心 6、CSCD 6 |
| [生命科学与医学](life-sciences-medicine.md) | 104 | 98 | 6 | 8 | 12 | 92 | 科协 T 63、NI 50、卓越 14、科技核心 12、CSCD 12 |
| [心理与认知](psychology-cognition.md) | 57 | 52 | 5 | 1 | 6 | 35 | 科协 T 16、ABDC 14、FMS 9、CSSCI 6、北大核心 6 |
| [经济](economics.md) | 98 | 89 | 9 | 0 | 15 | 88 | FMS 82、ABDC 73、CSSCI 15、科技核心 14、AMI 14 |
| [金融](finance.md) | 45 | 37 | 8 | 1 | 4 | 42 | ABDC 33、FMS 28、FT50 5、科协 T 5、惯例 5 |
| [商业与管理](business-management.md) | 124 | 106 | 18 | 0 | 18 | 111 | FMS 104、ABDC 89、VHB 87、FT50 39、UTD24 21 |
| [计算机与 AI](computer-science-ai.md) | 154 | 61 | 93 | 5 | 16 | 150 | CCF 128、ICORE 83、THCPL 79、CAAI 70、CSR 62 |
| [跨学科综合](multidisciplinary.md) | 25 | 25 | 0 | 5 | 6 | 15 | 科协 T 9、卓越 8、科技核心 6、北大核心 6、CSCD 5 |
| **合计** | **866** | **719** | **147** | **44** | **121** | **746** | |

"会议"一列含期刊化会议论文集（PVLDB、PACM 系列等）。一刊有多个同类标签时只计一次。

## 关联总图

学科之间怎样经由预印本、学科库与跨学科层串起来。实线箭头读作"流向"：预印本发表到期刊（L1b → L1a），期刊被学科库收录（L1a → L2a），学科库汇入跨学科引擎（L2a → L2b）；M2 给所有 L1 分配 DOI 与 ISSN。每个学科文件开头另有一张"学科 → 子领域 → 代表 venue"的局部图。

```mermaid
flowchart LR
  subgraph L1B["L1b 预印本与工作论文"]
    arx[["arXiv"]]
    chemrx[["ChemRxiv"]]
    ess[["ESS Open Archive · EarthArXiv · EGUsphere"]]
    bio[["bioRxiv · medRxiv"]]
    psy[["PsyArXiv"]]
    ssrn[["SSRN"]]
    wp[["NBER · CEPR · 央行与国际组织 WP"]]
    cx[["ChinaXiv · 中国科技论文在线"]]
  end
  subgraph L1A["L1a 期刊与会议 · 866"]
    math["数学 · 63"]
    phys["物理与天文 · 61"]
    chem["化学 · 47"]
    geo["地学 · 52"]
    mat["材料 · 36"]
    life["生命科学与医学 · 104"]
    psyc["心理与认知 · 57"]
    econ["经济 · 98"]
    fin["金融 · 45"]
    mgmt["商业与管理 · 124"]
    cs["计算机与 AI · 154"]
    multi["跨学科综合 · 25"]
  end
  subgraph L2A["L2a 学科库"]
    zb[("zbMATH · MathSciNet")]
    ins[("INSPIRE · ADS")]
    cas[("CAS SciFinder · PubChem")]
    geor[("GeoRef（订阅） · ADS")]
    pm[("PubMed · Europe PMC · PMC")]
    psyi[("PsycInfo（订阅） · PubPsych")]
    rep[("RePEc · EconBiz")]
    dblp[("dblp")]
    cnki[("CNKI · 万方 · 维普")]
  end
  M2{{"M2 Crossref · DataCite · ORCID · ROR · ISSN"}}
  L2B[["L2b OpenAlex · Semantic Scholar · OpenCitations · Unpaywall"]]
  arx --> math & phys & mat & cs & econ & fin
  chemrx --> chem & mat
  ess --> geo
  bio --> life & multi
  psy --> psyc
  ssrn --> econ & fin & mgmt
  wp --> econ & fin
  math --> zb
  phys --> ins
  chem --> cas
  geo --> geor
  life --> pm
  psyc --> psyi & pm
  econ & fin --> rep
  cs --> dblp
  multi --> pm
  cx -. 中文刊 .-> L1A
  L1A -. 中文刊 .-> cnki
  M2 -. DOI · ISSN .-> L1A
  L2A --> L2B
  M2 --> L2B
```

## 表格怎么读

每个学科文件按子领域分表，子领域内按评级强弱排序：

- **标识**：期刊写印刷版 / 电子版 ISSN，会议写 dblp key；ISSN 经旧稿、Crossref、ABDC 或 CSCD 名单核过，未核的在备注里写明。
- **出版托管（M1）**：出版或托管主体，后附它在[支持名录](../source-directory.md)里的 `source_id`；没有 `source_id` 的平台尚未勘察。
- **评级**：[评级体系](../venue-rankings.md)词表里的标签。科协 T 级按等级合并学会，如 `T1(中国地质学会、中国地理学会)`。
- **学科库（L2a）、预印本（L1b）**：收录它的主要学科库与对应的首发通道，多数按子领域惯例填写，没有逐刊核验。
- **接入**：`Crossref:ISSN` 指由 Crossref 委托按 ISSN 收元数据；`现有:`、`平台:` 指经名录里已有的来源行；`用户导入` 指只接受用户导出的题录；`待勘察` 指通道未核。
- **备注**：主办方、更名、Crossref 登记异常与区域（中国主办英文刊写"中国(英文)"）。

## 怎么维护

- **单一事实来源**：现阶段以这些表为准；V0 建注册表后，venue 落为 `registry/venues/<学科>/*.yaml`，表格改由生成器产出，本目录的数字与表格不再手改。
- **新增 venue**：用户关注的任意期刊先由 Crossref 或 OpenAlex 自动建为 `auto`；要进本名录的 venue 须核实 ISSN（或 dblp key）、M1 平台与评级出处。
- **评级更新**：随[评级体系](../venue-rankings.md)的复读节奏整表替换，替换后重新生成各学科文件。
- **跨学科 venue 只挂一个主属学科**，其他学科在备注里提及。

## 已知缺口

- **评级**：AJG 未标（须登录）；ICORE 有 38 个标签取自 ccfddl，版本可能混有 CORE2023；物理、化学、心理、经济没有本学科的科协目录；非 CS 会议多数没有可引用的分档出处。
- **接入**：121 个中文刊里 95 个只能用户导入，经 ISTIC 中文 DOI 收元数据的通道待勘察；28 个 venue（主要是经管会议）的通道待勘察。
- **平台**：Copernicus（EGU）、美国气象学会、清华社 SciOpen、Project MUSE、SMF、上海有机所期刊站等托管平台不在名录，候选见[候选来源](../source-candidates.md)。
- **数据异常**：各学科文件的"出处与说明"列出 Crossref 登记异常（错误 ISSN、新旧 ISSN 未合并等），接入前须处理。
