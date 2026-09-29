---
title: 材料 venue 名录
status: draft
owner: opus5.5-primary
updated: 2026-09-29
---

# 材料 venue 名录

> 材料共 36 个 venue（期刊 36、会议 0），归并为 4 个子领域（原 8 个），另有中文刊 6 个。其中核心 12 个优先支持，其余 24 个登记在册、暂不专门支持，规则见[支持分级](README.md#支持分级)。主要学科库：OSTI、PubMed、CAS SciFinder、PubChem、CNKI、万方、维普（中文刊）；主要预印本与 WP 通道：arXiv cond-mat、ChemRxiv、bioRxiv、ChinaXiv（中文刊）。评级标签的体系、版本与许可见[评级体系](../venue-rankings.md)，七类分层见[来源分层](../source-taxonomy.md)。

## 关联图

```mermaid
flowchart LR
  D(("材料<br/>36"))
  D --> S0["综合与计算 · 核心 3 / 8"]
  S0 --- V0["Adv. Mater. · Nat. Mater. · Sci. China Mater."]
  D --> S1["纳米与功能材料 · 核心 3 / 7"]
  S1 --- V1["Nano Lett. · Nat. Nanotechnol. · Nano Res."]
  D --> S2["能源材料 · 核心 2 / 5"]
  S2 --- V2["Nat. Energy · ACS Energy Lett."]
  D --> S3["结构、高分子与生物材料 · 核心 3 / 10"]
  S3 --- V3["JMST · Int. J. Plast. · Acta Biomater."]
  D --> SCN["中文刊 · 核心 1 / 6"]
  SCN --- VCN["无机材料学报"]
  subgraph M1["M1 出版与托管"]
    P0{{"Elsevier · 12"}}
    P1{{"Nature Portfolio · 5"}}
    P2{{"ACS · 4"}}
    P3{{"Wiley · 3"}}
    P4{{"RSC · 2"}}
    P5{{"Springer Nature · 2"}}
  end
  M1 -. 出版/托管 .-> D
  subgraph L2A["L2a 文献库"]
    A0[("OSTI")]
    A1[("PubMed")]
    A2[("CAS SciFinder")]
    A3[("PubChem")]
    A4[("CNKI、万方、维普（中文刊）")]
  end
  D -. 被收录 .-> L2A
  subgraph L1B["L1b 预印本与 WP"]
    B0[["arXiv cond-mat"]]
    B1[["ChemRxiv"]]
    B2[["bioRxiv"]]
    B3[["ChinaXiv（中文刊）"]]
  end
  L1B -. 发表去向 .-> D
```

## 核心 venue（优先支持）

每个子领域内按评级强弱排序，评级相同按名称。`接入` 一列：`Crossref:ISSN` 指由 Crossref 委托按 ISSN 收元数据，`现有:`/`平台:` 指经名录里已有的来源行，`用户导入` 指只接受用户导出的题录。

本节只列核心 venue：逐刊核验标识与通道，进入首批验收与默认推荐池。其余 venue 见下文"登记 venue"。子领域由原来的细分方向归并而成：合并组先按原方向、再按评级排列，备注以"方向："开头标出原方向。

### 综合与计算（核心 3 · 登记 5）

含原方向：综合材料、计算材料。

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Advanced Materials（Adv. Mater.） | J | 0935-9648 / 1521-4095 | Wiley-VCH `wiley` | NI; T1(中国材料研究学会、中国硅酸盐学会) | OSTI | arXiv:cond-mat.mtrl-sci; ChemRxiv | Crossref:ISSN | 方向：综合材料 |
| Nature Materials（Nat. Mater.） | J | 1476-1122 / 1476-4660 | Springer Nature `nature_portfolio` | NI; T1(中国材料研究学会) | OSTI | arXiv:cond-mat.mtrl-sci; ChemRxiv | Crossref:ISSN | 方向：综合材料 |
| Science China Materials（Sci. China Mater.） | J | 2095-8226 / 2199-4501 | Springer / 中国科学杂志社 `springer_link` | T1(中国材料研究学会、中国金属学会); 卓越-梯队 | OSTI | arXiv:cond-mat.mtrl-sci; ChemRxiv | Crossref:ISSN | 方向：综合材料；中国(英文)；SciEngine 同刊 |

### 纳米与功能材料（核心 3 · 登记 4）

含原方向：纳米材料、功能与电子材料。

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Nano Letters（Nano Lett.） | J | 1530-6984 / 1530-6992 | ACS `acs` | NI; T1(中国材料研究学会) | OSTI; PubMed | arXiv:cond-mat.mtrl-sci; ChemRxiv | Crossref:ISSN | 方向：纳米材料；旧稿 2026-09-26 已核 |
| Nature Nanotechnology（Nat. Nanotechnol.） | J | 1748-3387 / 1748-3395 | Springer Nature `nature_portfolio` | NI; T1(中国材料研究学会) | OSTI | arXiv:cond-mat.mtrl-sci; ChemRxiv | Crossref:ISSN | 方向：纳米材料 |
| Nano Research（Nano Res.） | J | 1998-0124 / 1998-0000 | 清华大学出版社（SciOpen） | T1(中国材料研究学会); 卓越-领军 | OSTI | arXiv:cond-mat.mtrl-sci; ChemRxiv | Crossref:ISSN | 方向：纳米材料；中国(英文)；落地 SciOpen；e-ISSN 1998-0000 疑误 |

### 能源材料（核心 2 · 登记 3）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Nature Energy（Nat. Energy） | J | — / 2058-7546 | Springer Nature `nature_portfolio` | NI; T1(中国地理学会、中国材料研究学会) | OSTI | arXiv:cond-mat.mtrl-sci; ChemRxiv | Crossref:ISSN |  |
| ACS Energy Letters（ACS Energy Lett.） | J | 2380-8195 / 2380-8195 | ACS `acs` | T1(中国材料研究学会); T2(中国硅酸盐学会) | OSTI | arXiv:cond-mat.mtrl-sci; ChemRxiv | Crossref:ISSN |  |

### 结构、高分子与生物材料（核心 3 · 登记 7）

含原方向：结构与金属材料、高分子与软物质、生物材料。

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Journal of Materials Science & Technology（JMST） | J | 1005-0302 / — | Elsevier（中国金属学会等） `elsevier_sd` | T1(中国有色金属学会、中国材料研究学会、中国金属学会); T2(中国腐蚀与防护学会); 卓越-领军 | OSTI | arXiv:cond-mat.mtrl-sci; ChemRxiv | Crossref:ISSN | 方向：结构与金属材料；中国(英文) |
| International Journal of Plasticity（Int. J. Plast.） | J | 0749-6419 / — | Elsevier `elsevier_sd` | T1(中国岩石力学与工程学会); T2(中国材料研究学会) | OSTI | arXiv:cond-mat.mtrl-sci; ChemRxiv | Crossref:ISSN | 方向：结构与金属材料 |
| Acta Biomaterialia（Acta Biomater.） | J | 1742-7061 / — | Elsevier `elsevier_sd` | NI; T1(中国生物医学工程学会) | PubMed; OSTI | arXiv:cond-mat.mtrl-sci; ChemRxiv; bioRxiv | Crossref:ISSN | 方向：生物材料 |

### 中文刊（核心 1 · 登记 5）

子领域写在备注里。知网、万方、维普只接受用户导入题录；在 Crossref 注册了 DOI 的中文刊可经 Crossref 收元数据。只接受用户导入的中文刊不列为核心。

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| 无机材料学报（Journal of Inorganic Materials） | J | 1000-324X / — | 中国科学院上海硅酸盐研究所 | T1(中国硅酸盐学会); T2(中国材料研究学会); T3(中国腐蚀与防护学会); CSCD核心; 北大核心; 科技核心 | CNKI; 万方; CSCD | ChinaXiv | Crossref:ISSN | 无机非金属；Crossref前缀10.3724 |

## 登记 venue（长尾，暂不支持）

以下 venue 登记在册，保留标识、托管与评级，但暂不逐刊核验通道、不进首批验收。用户关注其中任意一个时，照常经 Crossref 或 OpenAlex 自动建 venue（`auto`）收元数据；问卷、调研与关注数达到[升级条件](README.md#支持分级)后升为核心。

### 综合与计算（登记 5）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Materials Today（Mater. Today） | J | 1369-7021 / — | Elsevier `elsevier_sd` | T1(中国材料研究学会) | OSTI | arXiv:cond-mat.mtrl-sci; ChemRxiv | Crossref:ISSN | 方向：综合材料 |
| Nature Reviews Materials（Nat. Rev. Mater.） | J | — / 2058-8437 | Springer Nature `nature_portfolio` | T1(中国材料研究学会) | OSTI | — | Crossref:ISSN | 方向：综合材料；综述刊 |
| Progress in Materials Science（Prog. Mater. Sci.） | J | 0079-6425 / 1873-2208 | Elsevier `elsevier_sd` | T1(中国材料研究学会) | OSTI | — | Crossref:ISSN | 方向：综合材料；综述刊 |
| Physical Review Materials（PRMaterials） | J | — / 2475-9953 | APS `aps` | T1(中国材料研究学会) | OSTI; INSPIRE ⚠ | arXiv:cond-mat.mtrl-sci | Crossref:ISSN | 方向：计算材料；兼物理 |
| npj Computational Materials（npj Comput. Mater.） | J | — / 2057-3960 | Springer Nature `nature_portfolio` | T1(中国材料研究学会、中国金属学会) | OSTI | arXiv:cond-mat.mtrl-sci | Crossref:ISSN | 方向：计算材料 |

### 纳米与功能材料（登记 4）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Nano-Micro Letters（Nano-Micro Lett.） | J | 2311-6706 / 2150-5551 | Springer（上海交大） `springer_link` | T1(中国材料研究学会); 卓越-梯队 | OSTI | arXiv:cond-mat.mtrl-sci; ChemRxiv | Crossref:ISSN | 方向：纳米材料；中国(英文) |
| Advanced Functional Materials（AFM） | J | 1616-301X / 1616-3028 | Wiley-VCH `wiley` | NI; T1(中国材料研究学会、中国硅酸盐学会) | OSTI | arXiv:cond-mat.mtrl-sci; ChemRxiv | Crossref:ISSN | 方向：功能与电子材料 |
| ACS Applied Materials & Interfaces（ACS AMI） | J | 1944-8244 / 1944-8252 | ACS `acs` | T1(中国材料研究学会、中国核学会、中国硅酸盐学会 等 4 家) | OSTI | arXiv:cond-mat.mtrl-sci; ChemRxiv | Crossref:ISSN | 方向：功能与电子材料 |
| Chemistry of Materials（Chem. Mater.） | J | 0897-4756 / 1520-5002 | ACS `acs` | T1(中国材料研究学会) | OSTI; CAS SciFinder（仅外链）; PubChem | arXiv:cond-mat.mtrl-sci; ChemRxiv | Crossref:ISSN | 方向：功能与电子材料 |

### 能源材料（登记 3）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Advanced Energy Materials（AEM） | J | 1614-6832 / 1614-6840 | Wiley-VCH `wiley` | T1(中国材料研究学会、中国硅酸盐学会) | OSTI | arXiv:cond-mat.mtrl-sci; ChemRxiv | Crossref:ISSN |  |
| Energy Storage Materials（EnSM） | J | 2405-8297 / — | Elsevier `elsevier_sd` | T1(中国材料研究学会、中国硅酸盐学会) | OSTI | arXiv:cond-mat.mtrl-sci; ChemRxiv | Crossref:ISSN |  |
| Journal of Materials Chemistry A（J. Mater. Chem. A） | J | 2050-7488 / 2050-7496 | RSC `rsc` | T1(中国材料研究学会、中国腐蚀与防护学会) | OSTI | arXiv:cond-mat.mtrl-sci; ChemRxiv | Crossref:ISSN | 旧稿 2026-09-26 已核 |

### 结构、高分子与生物材料（登记 7）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Acta Materialia（Acta Mater.） | J | 1359-6454 / — | Elsevier（Acta Materialia Inc.） `elsevier_sd` | T1(中国有色金属学会、中国材料研究学会、中国金属学会) | OSTI | arXiv:cond-mat.mtrl-sci; ChemRxiv | Crossref:ISSN | 方向：结构与金属材料 |
| Materials Science and Engineering: A（MSEA） | J | 0921-5093 / — | Elsevier `elsevier_sd` | T1(中国有色金属学会、中国金属学会); T2(中国材料研究学会) | OSTI | arXiv:cond-mat.mtrl-sci; ChemRxiv | Crossref:ISSN | 方向：结构与金属材料 |
| Scripta Materialia（Scripta Mater.） | J | 1359-6462 / — | Elsevier `elsevier_sd` | T1(中国材料研究学会、中国金属学会); T2(中国有色金属学会) | OSTI | arXiv:cond-mat.mtrl-sci; ChemRxiv | Crossref:ISSN | 方向：结构与金属材料 |
| Bioactive Materials（Bioact. Mater.） | J | 2097-1192 / 2452-199X | KeAi（Elsevier 托管） `elsevier_sd` | T1(中国材料研究学会); T2(中国生物医学工程学会) | PubMed; PMC | bioRxiv; ChemRxiv | Crossref:ISSN | 方向：生物材料；中国(英文)；Crossref 登记 print 2097-1192 |
| Biomaterials | J | 0142-9612 / — | Elsevier `elsevier_sd` | T1(中国生物医学工程学会); T3(中华医学会) | PubMed; OSTI | arXiv:cond-mat.mtrl-sci; ChemRxiv; bioRxiv | Crossref:ISSN | 方向：生物材料 |
| Soft Matter | J | 1744-683X / 1744-6848 | RSC `rsc` | T1(中国材料研究学会) | OSTI | arXiv:cond-mat.soft; ChemRxiv | Crossref:ISSN | 方向：高分子与软物质 |
| Progress in Polymer Science（Prog. Polym. Sci.） | J | 0079-6700 / — | Elsevier `elsevier_sd` | — | CAS SciFinder（仅外链）; PubChem | ChemRxiv | Crossref:ISSN | 方向：高分子与软物质；综述刊 |

### 中文刊（登记 5）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| 中国有色金属学报（The Chinese Journal of Nonferrous Metals） | J | 1004-0609 / — | 中国有色金属学会 | T1(中国有色金属学会、中国金属学会); T2(中国岩石力学与工程学会、中国材料研究学会); 卓越-领军; CSCD核心; 北大核心; 科技核心 | CNKI; 万方; CSCD | ChinaXiv | 用户导入 | 金属材料；一期梯队 |
| 硅酸盐学报（Journal of the Chinese Ceramic Society） | J | 0454-5648 / — | 中国硅酸盐学会 | T1(中国材料研究学会、中国硅酸盐学会); T3(中国腐蚀与防护学会); 卓越-领军; CSCD核心; 北大核心; 科技核心 | CNKI; 万方; CSCD | ChinaXiv | 用户导入 | 无机非金属；Crossref无该ISSN记录；一期梯队 |
| 金属学报（Acta Metallurgica Sinica） | J | 0412-1961 / — | 中国金属学会 | T1(中国有色金属学会、中国材料研究学会、中国金属学会); T3(中国腐蚀与防护学会); 卓越-领军; CSCD核心; 北大核心; 科技核心 | CNKI; 万方; CSCD | ChinaXiv | 用户导入 | 金属材料；Crossref仅至2013(10.3724)；一期梯队 |
| 复合材料学报（Acta Materiae Compositae Sinica） | J | 1000-3851 / — | 北京航空航天大学 | T2(中国材料研究学会); T3(中国腐蚀与防护学会); 卓越-领军; CSCD核心; 北大核心; 科技核心 | CNKI; 万方; CSCD | ChinaXiv | 用户导入 | 复合材料；Crossref无该ISSN记录；一期梯队 |
| 材料研究学报（Chinese Journal of Materials Research） | J | 1005-3093 / — | 中国材料研究学会 | T1(中国有色金属学会); T2(中国材料研究学会、中国金属学会); T3(中国腐蚀与防护学会); CSCD核心; 北大核心; 科技核心 | CNKI; 万方; CSCD | ChinaXiv | 用户导入 | 综合材料；Crossref无该ISSN记录 |

## 出处与说明

- **T 级**：材料-综合（中国材料研究学会，2025）、无机非金属（中国硅酸盐学会，2025）、冶金与金属材料（中国金属学会，2024）、有色金属（2024）、材料失效与保护（2021）。
- **平台**：Nano Research 在清华社 SciOpen（不在名录），Crossref 给它登记的 e-ISSN 1998-0000 疑似错误。
- **缺口**：没有开放的材料学科书目库；Materials Project、NOMAD 等是数据库，可作信号候选；TMS、ASM 等学会平台未列。
- **支持分级**：核心按[支持分级](README.md#支持分级)的规则初选，2026-09-29 定稿。本学科没有人工补选。
