---
title: 化学 venue 名录
status: draft
owner: opus5.5-primary
updated: 2026-09-27
---

# 化学 venue 名录

> 化学共 47 个 venue（期刊 47、会议 0），分 14 个子领域，另有中文刊 8 个。主要学科库：CAS SciFinder、PubChem、PubMed、ADS、CNKI、万方、维普（中文刊）；主要预印本与 WP 通道：ChemRxiv、arXiv physics、arXiv cond-mat、bioRxiv、ChinaXiv（中文刊）。评级标签的体系、版本与许可见[评级体系](../venue-rankings.md)，七类分层见[来源分层](../source-taxonomy.md)。

## 关联图

```mermaid
flowchart LR
  D(("化学<br/>47"))
  D --> S0["综合顶刊 · 5"]
  S0 --- V0["Angewandte Chemie International … · JACS · Chem. Sci. · Nat. Chem. …"]
  D --> S1["综合 · 9"]
  S1 --- V1["Chem. Commun. · Chinese Chemical Letters · ACS Cent. Sci. · CCS Chem. …"]
  D --> S2["综述刊 · 4"]
  S2 --- V2["Accounts of Chemical Research · Chem. Rev. · Chemical Society Reviews · Nature Reviews Chemistry"]
  D --> S3["有机 · 2"]
  S3 --- V3["Org. Lett. · J. Org. Chem."]
  D --> S4["无机与配位 · 3"]
  S4 --- V4["Inorg. Chem. · Coordination Chemistry Reviews · Dalton Trans."]
  D --> S5["物理化学 · 3"]
  S5 --- V5["The Journal of Physical Chemistr… · PCCP · J. Chem. Phys."]
  D --> S6["分析 · 1"]
  S6 --- V6["Anal. Chem."]
  D --> S7["催化 · 4"]
  S7 --- V7["Chinese Journal of Catalysis · ACS Catal. · J. Catal. · Nat. Catal."]
  D --> S8["高分子 · 1"]
  S8 --- V8["Macromolecules"]
  D --> S9["电化学与能源化学 · 2"]
  S9 --- V9["EES · Journal of The Electrochemical S…"]
  D --> S10["化学生物学 · 1"]
  S10 --- V10["ACS Chemical Biology"]
  D --> S11["理论与计算化学 · 1"]
  S11 --- V11["JCTC"]
  D --> S12["绿色与环境化学 · 2"]
  S12 --- V12["ES&T · Green Chem."]
  D --> S13["纳米化学 · 1"]
  S13 --- V13["ACS Nano"]
  D --> SCN["中文刊 · 8"]
  SCN --- VCN["CIESC Journal · 物理化学学报 · 高分子学报 · 中国科学:化学 …"]
  subgraph M1["M1 出版与托管"]
    P0{{"ACS · 16"}}
    P1{{"RSC · 7"}}
    P2{{"Elsevier · 5"}}
    P3{{"Wiley · 3"}}
    P4{{"Nature Portfolio · 3"}}
    P5{{"AIP · 1"}}
  end
  M1 -. 出版/托管 .-> D
  subgraph L2A["L2a 文献库"]
    A0[("CAS SciFinder")]
    A1[("PubChem")]
    A2[("PubMed")]
    A3[("ADS")]
    A4[("CNKI、万方、维普（中文刊）")]
  end
  D -. 被收录 .-> L2A
  subgraph L1B["L1b 预印本与 WP"]
    B0[["ChemRxiv"]]
    B1[["arXiv physics"]]
    B2[["arXiv cond-mat"]]
    B3[["bioRxiv"]]
    B4[["ChinaXiv（中文刊）"]]
  end
  L1B -. 发表去向 .-> D
```

## 名录

每个子领域内按评级强弱排序，评级相同按名称。`接入` 一列：`Crossref:ISSN` 指由 Crossref 委托按 ISSN 收元数据，`现有:`/`平台:` 指经名录里已有的来源行，`用户导入` 指只接受用户导出的题录。

### 综合顶刊（5）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Angewandte Chemie International Edition（Angew. Chem. Int. Ed.） | J | 1433-7851 / 1521-3773 | Wiley-VCH（GDCh） `wiley` | NI; T1(中国材料研究学会) | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN |  |
| Journal of the American Chemical Society（JACS） | J | 0002-7863 / 1520-5126 | ACS `acs` | NI; T1(中国材料研究学会) | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN |  |
| Chemical Science（Chem. Sci.） | J | 2041-6520 / 2041-6539 | RSC `rsc` | NI | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN | RSC 旗舰，DOAJ |
| Nature Chemistry（Nat. Chem.） | J | 1755-4330 / 1755-4349 | Springer Nature `nature_portfolio` | NI | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN |  |
| Chem | J | 2451-9294 / — | Cell Press（Elsevier） `elsevier_sd` | — | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN | Crossref 摘要 0.00 |

### 综合（9）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Chemical Communications（Chem. Commun.） | J | 1359-7345 / 1364-548X | RSC `rsc` | NI | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN |  |
| Chinese Chemical Letters（Chin. Chem. Lett.） | J | 1001-8417 / — | Elsevier（中国化学会） `elsevier_sd` | T3(中国环境科学学会); 卓越-领军 | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN | 中国(英文) |
| ACS Central Science（ACS Cent. Sci.） | J | 2374-7943 / 2374-7951 | ACS `acs` | — | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN | DOAJ，APC 0 |
| CCS Chemistry（CCS Chem.） | J | 2096-5745 / 2096-5745 | 中国化学会 `ccs_chemistry` | 卓越-梯队 | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN | 中国(英文)；自有平台 Atypon 模板 |
| Chemistry – A European Journal（Chem. Eur. J.） | J | 0947-6539 / 1521-3765 | Wiley-VCH（ChemPubSoc Europe） `wiley` | — | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN |  |
| Chinese Journal of Chemistry（Chin. J. Chem.） | J | 1001-604X / 1614-7065 | Wiley（中国化学会/上海有机所） `wiley` | — | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN | 中国(英文) |
| JACS Au | J | 2691-3704 / 2691-3704 | ACS `acs` | — | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN | 旧稿 2026-09-26 已核 |
| Pure and Applied Chemistry（Pure Appl. Chem.） | J | 0033-4545 / 1365-3075 | De Gruyter Brill（IUPAC） `degruyter_brill` | — | CAS SciFinder（仅外链）; PubChem | — | Crossref:ISSN |  |
| Science China Chemistry（Sci. China Chem.） | J | 1674-7291 / 1869-1870 | Springer / 中国科学杂志社 `springer_link` | 卓越-梯队 | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN | 中国(英文)；SciEngine 同刊，robots 禁 AI UA |

### 综述刊（4）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Accounts of Chemical Research（Acc. Chem. Res.） | J | 0001-4842 / 1520-4898 | ACS `acs` | — | CAS SciFinder（仅外链）; PubChem | — | Crossref:ISSN |  |
| Chemical Reviews（Chem. Rev.） | J | 0009-2665 / 1520-6890 | ACS `acs` | — | CAS SciFinder（仅外链）; PubChem | — | Crossref:ISSN |  |
| Chemical Society Reviews（Chem. Soc. Rev.） | J | 0306-0012 / 1460-4744 | RSC `rsc` | — | CAS SciFinder（仅外链）; PubChem | — | Crossref:ISSN |  |
| Nature Reviews Chemistry（Nat. Rev. Chem.） | J | — / 2397-3358 | Springer Nature `nature_portfolio` | — | CAS SciFinder（仅外链）; PubChem | — | Crossref:ISSN |  |

### 有机（2）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Organic Letters（Org. Lett.） | J | 1523-7060 / 1523-7052 | ACS `acs` | NI | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN | 旧稿 2026-09-26 已核 |
| The Journal of Organic Chemistry（J. Org. Chem.） | J | 0022-3263 / 1520-6904 | ACS `acs` | — | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN |  |

### 无机与配位（3）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Inorganic Chemistry（Inorg. Chem.） | J | 0020-1669 / 1520-510X | ACS `acs` | NI | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN | 旧稿 2026-09-26 已核 |
| Coordination Chemistry Reviews（Coord. Chem. Rev.） | J | 0010-8545 / 0010-8545 | Elsevier `elsevier_sd` | — | CAS SciFinder（仅外链）; PubChem | — | Crossref:ISSN | 综述刊；摘要 0.00 |
| Dalton Transactions（Dalton Trans.） | J | 1477-9226 / 1477-9234 | RSC `rsc` | — | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN |  |

### 物理化学（3）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| The Journal of Physical Chemistry Letters（J. Phys. Chem. Lett.） | J | 1948-7185 / 1948-7185 | ACS `acs` | NI; T2(中国材料研究学会) | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN |  |
| Physical Chemistry Chemical Physics（PCCP） | J | 1463-9076 / 1463-9084 | RSC `rsc` | — | CAS SciFinder（仅外链）; PubChem | ChemRxiv; arXiv:physics.chem-ph | Crossref:ISSN | 旧稿 2026-09-26 已核 |
| The Journal of Chemical Physics（J. Chem. Phys.） | J | 0021-9606 / 1089-7690 | AIP Publishing `aip` | — | CAS SciFinder（仅外链）; PubChem; ADS | ChemRxiv; arXiv:physics.chem-ph | Crossref:ISSN |  |

### 分析（1）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Analytical Chemistry（Anal. Chem.） | J | 0003-2700 / 1520-6882 | ACS `acs` | NI; T2(中国环境科学学会) | CAS SciFinder（仅外链）; PubChem; PubMed | ChemRxiv | Crossref:ISSN | 旧稿 2026-09-26 已核 |

### 催化（4）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Chinese Journal of Catalysis（Chin. J. Catal.） | J | 0253-9837 / 1872-2067 | Elsevier（中科院大连化物所/中国化学会） `elsevier_sd` | 卓越-领军 | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN | 中国(英文)；英文版用 1872-2067；0253-9837 为旧中文版 |
| ACS Catalysis（ACS Catal.） | J | 2155-5435 / 2155-5435 | ACS `acs` | — | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN |  |
| Journal of Catalysis（J. Catal.） | J | 0021-9517 / 1090-2694 | Elsevier `elsevier_sd` | — | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN | 旧稿 2026-09-26 已核 |
| Nature Catalysis（Nat. Catal.） | J | — / 2520-1158 | Springer Nature `nature_portfolio` | — | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN |  |

### 高分子（1）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Macromolecules | J | 0024-9297 / 1520-5835 | ACS `acs` | NI | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN | 兼材料-高分子 |

### 电化学与能源化学（2）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Energy & Environmental Science（EES） | J | 1754-5692 / 1754-5706 | RSC `rsc` | NI; T1(中国核学会、中国环境科学学会、中国硅酸盐学会) | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN | 兼材料-能源 |
| Journal of The Electrochemical Society（J. Electrochem. Soc.） | J | 0013-4651 / 1945-7111 | The Electrochemical Society（IOP 托管） `iop` | T1(中国腐蚀与防护学会) | CAS SciFinder（仅外链）; PubChem; OSTI | ChemRxiv | Crossref:ISSN | Crossref 落地 iopscience |

### 化学生物学（1）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| ACS Chemical Biology（ACS Chem. Biol.） | J | 1554-8929 / 1554-8937 | ACS `acs` | — | PubMed; CAS SciFinder（仅外链）; PubChem | ChemRxiv; bioRxiv | Crossref:ISSN |  |

### 理论与计算化学（1）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Journal of Chemical Theory and Computation（JCTC） | J | 1549-9618 / 1549-9626 | ACS `acs` | — | CAS SciFinder（仅外链）; PubChem | ChemRxiv; arXiv:physics.chem-ph | Crossref:ISSN | 旧稿 2026-09-26 已核 |

### 绿色与环境化学（2）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Environmental Science & Technology（ES&T） | J | 0013-936X / 1520-5851 | ACS `acs` | NI; T1(中国地理学会、中国环境科学学会) | CAS SciFinder（仅外链）; PubChem; PubMed | ChemRxiv | Crossref:ISSN | 兼地学-环境 |
| Green Chemistry（Green Chem.） | J | 1463-9262 / 1463-9270 | RSC `rsc` | T3(中国环境科学学会) | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN | 旧稿 2026-09-26 已核 |

### 纳米化学（1）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| ACS Nano | J | 1936-0851 / 1936-086X | ACS `acs` | NI; T1(中国材料研究学会) | CAS SciFinder（仅外链）; PubChem; PubMed | arXiv:cond-mat.mtrl-sci; ChemRxiv | Crossref:ISSN | 兼材料-纳米 |

### 中文刊（8）

子领域写在备注里。知网、万方、维普只接受用户导入题录；在 Crossref 注册了 DOI 的中文刊可经 Crossref 收元数据。

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| 化工学报（CIESC Journal） | J | 0438-1157 / — | 中国化工学会 | T1(中国化工学会); 卓越-领军; CSCD核心; 北大核心; 科技核心 | CNKI; 万方; CSCD | ChinaXiv | 用户导入 | 化工；Crossref无该ISSN记录；一期梯队 |
| 物理化学学报（Acta Physico-Chimica Sinica） | J | 1000-6818 / — | 中国化学会 | 卓越-领军; CSCD核心; 北大核心; 科技核心 | CNKI; 万方; CSCD | ChinaXiv | Crossref:ISSN | 物理化学；Crossref前缀10.1016；现由Elsevier出版 |
| 高分子学报（Acta Polymerica Sinica） | J | 1000-3304 / — | 中国化学会 | T1(中国化工学会); T2(中国材料研究学会); T3(中国腐蚀与防护学会); CSCD核心; 北大核心; 科技核心 | CNKI; 万方; CSCD | ChinaXiv | 用户导入 | 高分子；Crossref仅至2014(10.3724) |
| 中国科学:化学（Scientia Sinica Chimica） | J | 1674-7224 / — | 中国科学杂志社 `sciengine` | 卓越-梯队; CSCD核心; 北大核心; 科技核心 | CNKI; 万方; CSCD | ChinaXiv | Crossref:ISSN | 综合化学；Crossref前缀10.1360 |
| 分析化学（Chinese Journal of Analytical Chemistry） | J | 0253-3820 / — | 中国科学院长春应用化学研究所 | 卓越-梯队; CSCD核心; 北大核心; 科技核心 | CNKI; 万方; CSCD | ChinaXiv | 用户导入 | 分析化学；Crossref仅至2014(10.3724) |
| 化学学报（Acta Chim. Sinica） | J | 0567-7351 / — | 上海有机化学研究所（中国化学会） | T3(中国腐蚀与防护学会); 卓越-梯队(一期); CSCD核心; 北大核心; 科技核心 | CAS SciFinder（仅外链）; PubChem; CNKI | ChemRxiv | Crossref:ISSN | 综合；落地 sioc-journal.cn；M1 不在 187 |
| 高等学校化学学报（Chemical Journal of Chinese Universities） | J | 0251-0790 / — | 吉林大学 | 卓越-梯队(一期); CSCD核心; 北大核心; 科技核心 | CNKI; 万方; CSCD | ChinaXiv | 用户导入 | 综合化学；Crossref无该ISSN记录 |
| 有机化学（Chinese Journal of Organic Chemistry） | J | 0253-2786 / — | 中国化学会 | T3(中国腐蚀与防护学会); CSCD扩展; 北大核心; 科技核心 | CNKI; 万方; CSCD | ChinaXiv | Crossref:ISSN | 有机化学；Crossref前缀10.6023 |

## 出处与说明

- **T 级**：科协总汇第五版没有中国化学会编制的化学领域目录。化学刊的 T 标签来自材料、环境、硅酸盐、腐蚀、化工等相邻学会的目录（括号里写学会），只说明入选该学会目录，不代表化学学科内的分级。
- **NI**：14 刊。
- **平台**：化学学报在上海有机所自有站，不在名录；化学生物学刊另挂 PubMed。
- **待核**：新增传统出版商刊的 OA 列按出版模式写"混合"，未逐刊核 DOAJ。
