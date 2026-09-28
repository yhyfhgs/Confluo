---
title: 地学 venue 名录
status: draft
owner: opus5.5-primary
updated: 2026-09-27
---

# 地学 venue 名录

> 地学共 52 个 venue（期刊 52、会议 0），分 10 个子领域，另有中文刊 13 个。主要学科库：GeoRef、ADS、dblp、CNKI、万方、维普（中文刊）；主要预印本与 WP 通道：ESS Open Archive、EarthArXiv、arXiv physics、EGUsphere、ChinaXiv（中文刊）。评级标签的体系、版本与许可见[评级体系](../venue-rankings.md)，七类分层见[来源分层](../source-taxonomy.md)。

## 关联图

```mermaid
flowchart LR
  D(("地学<br/>52"))
  D --> S0["综合地球科学 · 9"]
  S0 --- V0["Geology · GRL · Nat. Geosci. · Science China Earth Sciences …"]
  D --> S1["地球化学 · 2"]
  S1 --- V1["EPSL · GCA"]
  D --> S2["地球物理与地震 · 3"]
  S2 --- V2["Journal of Geophysical Research:… · BSSA · GJI"]
  D --> S3["大气与气候 · 6"]
  S3 --- V3["JGR Atmos · Nature Climate Change · Advances in Atmospheric Sciences · ACP …"]
  D --> S4["海洋 · 2"]
  S4 --- V4["JGR Oceans · JPO"]
  D --> S5["水文 · 4"]
  S5 --- V5["HESS · J. Hydrol. · TC · WRR"]
  D --> S6["环境与地球系统 · 6"]
  S6 --- V6["BG · ESSD · Earths Future · GMD …"]
  D --> S7["遥感与地理信息 · 3"]
  S7 --- V7["TGRS · ISPRS J. · RSE"]
  D --> S8["行星科学 · 2"]
  S8 --- V8["JGR Planets · Icarus"]
  D --> S9["古生物与地层 · 2"]
  S9 --- V9["Palaeo3 · QSR"]
  D --> SCN["中文刊 · 13"]
  SCN --- VCN["地理学报 · 地质学报 · 岩石学报 · 测绘学报 …"]
  subgraph M1["M1 出版与托管"]
    P0{{"Wiley · 10"}}
    P1{{"Elsevier · 9"}}
    P2{{"Copernicus · 6"}}
    P3{{"Nature Portfolio · 3"}}
    P4{{"GeoScienceWorld · 3"}}
    P5{{"AMS 美国气象学会 · 3"}}
  end
  M1 -. 出版/托管 .-> D
  subgraph L2A["L2a 文献库"]
    A0[("GeoRef")]
    A1[("ADS")]
    A2[("dblp")]
    A3[("CNKI、万方、维普（中文刊）")]
  end
  D -. 被收录 .-> L2A
  subgraph L1B["L1b 预印本与 WP"]
    B0[["ESS Open Archive"]]
    B1[["EarthArXiv"]]
    B2[["arXiv physics"]]
    B3[["EGUsphere"]]
    B4[["ChinaXiv（中文刊）"]]
  end
  L1B -. 发表去向 .-> D
```

## 名录

每个子领域内按评级强弱排序，评级相同按名称。`接入` 一列：`Crossref:ISSN` 指由 Crossref 委托按 ISSN 收元数据，`现有:`/`平台:` 指经名录里已有的来源行，`用户导入` 指只接受用户导出的题录。

### 综合地球科学（9）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Geology | J | 0091-7613 / 0091-7613 | GSA（GeoScienceWorld 托管） `geoscienceworld` | NI; T1(中国地球物理学会、中国地质学会) | GeoRef（订阅） | ESS Open Archive; EarthArXiv | Crossref:ISSN | GSW 挑战页 |
| Geophysical Research Letters（GRL） | J | 0094-8276 / 1944-8007 | AGU（Wiley 托管） `wiley` | NI; T1(中国地球物理学会、中国地质学会) | GeoRef（订阅）; ADS | ESS Open Archive; EarthArXiv | Crossref:ISSN | p/e 颠倒；落地 agupubs(Wiley) |
| Nature Geoscience（Nat. Geosci.） | J | 1752-0894 / 1752-0908 | Springer Nature `nature_portfolio` | NI; T1(中国地球物理学会、中国地理学会、中国地质学会) | GeoRef（订阅）; ADS | ESS Open Archive; EarthArXiv | Crossref:ISSN |  |
| Science China Earth Sciences（Sci. China Earth Sci.） | J | 1674-7313 / 1869-1897 | Springer / 中国科学杂志社 `springer_link` | T1(中国地球物理学会、中国地理学会、中国地质学会); T2(中国岩石力学与工程学会); 卓越-领军 | GeoRef（订阅）; CNKI | ESS Open Archive; EarthArXiv | Crossref:ISSN | 中国(英文)；SciEngine 同刊 |
| AGU Advances（AGU Adv.） | J | 2576-604X / 2576-604X | AGU（Wiley 托管） `wiley` | T1(中国地质学会) | GeoRef（订阅）; ADS | ESS Open Archive; EarthArXiv | Crossref:ISSN | 全 OA 旗舰 |
| Annual Review of Earth and Planetary Sciences（AREPS） | J | 0084-6597 / 1545-4495 | Annual Reviews `annual_reviews` | T1(中国地球物理学会、中国地质学会) | GeoRef（订阅）; ADS | — | Crossref:ISSN | 综述刊；S2O 年度不同 |
| Earth-Science Reviews（ESR） | J | 0012-8252 / — | Elsevier `elsevier_sd` | T1(中国地球物理学会、中国地质学会) | GeoRef（订阅） | — | Crossref:ISSN | 综述刊 |
| Geological Society of America Bulletin（GSA Bull.） | J | 0016-7606 / 1943-2674 | GSA（GeoScienceWorld 托管） `geoscienceworld` | T1(中国地质学会) | GeoRef（订阅） | ESS Open Archive; EarthArXiv | Crossref:ISSN |  |
| Reviews of Geophysics（Rev. Geophys.） | J | 8755-1209 / 1944-9208 | AGU（Wiley 托管） `wiley` | T1(中国地球物理学会、中国地质学会) | GeoRef（订阅）; ADS | — | Crossref:ISSN | 综述刊 |

### 地球化学（2）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Earth and Planetary Science Letters（EPSL） | J | 0012-821X / 1385-013X | Elsevier `elsevier_sd` | NI; T1(中国地球物理学会、中国地理学会、中国地质学会) | GeoRef（订阅）; ADS | ESS Open Archive; EarthArXiv | Crossref:ISSN |  |
| Geochimica et Cosmochimica Acta（GCA） | J | 0016-7037 / 0016-7037 | Elsevier `elsevier_sd` | NI; T1(中国地质学会) | GeoRef（订阅）; ADS | ESS Open Archive; EarthArXiv | Crossref:ISSN | 地球化学会与陨石学会合办 |

### 地球物理与地震（3）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Journal of Geophysical Research: Solid Earth（JGR Solid Earth） | J | 2169-9313 / 2169-9356 | AGU（Wiley 托管） `wiley` | NI; T1(中国地球物理学会、中国地质学会、中国岩石力学与工程学会) | GeoRef（订阅）; ADS | ESS Open Archive; EarthArXiv; arXiv:physics.geo-ph | Crossref:ISSN |  |
| Bulletin of the Seismological Society of America（BSSA） | J | 0037-1106 / 1943-3573 | SSA（GeoScienceWorld 托管） `geoscienceworld` | T1(中国地质学会); T2(中国地球物理学会) | GeoRef（订阅）; ADS | ESS Open Archive; EarthArXiv; arXiv:physics.geo-ph | Crossref:ISSN | Crossref 落地 GSW；GSW 挑战页 |
| Geophysical Journal International（GJI） | J | 0956-540X / 1365-246X | OUP（RAS/DGG） `oup_academic` | T2(中国地球物理学会、中国地质学会、中国岩石力学与工程学会) | GeoRef（订阅）; ADS | ESS Open Archive; EarthArXiv; arXiv:physics.geo-ph | Crossref:ISSN | 2024 起转 OA ⚠ 未核 |

### 大气与气候（6）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Journal of Geophysical Research: Atmospheres（JGR Atmos） | J | 2169-897X / 2169-8996 | AGU（Wiley 托管） `wiley` | NI; T1(中国地质学会); T2(中国地理学会); T3(中国环境科学学会) | GeoRef（订阅）; ADS | ESS Open Archive; EarthArXiv; arXiv:physics.ao-ph | Crossref:ISSN |  |
| Nature Climate Change（Nat. Clim. Change） | J | 1758-678X / 1758-6798 | Springer Nature `nature_portfolio` | NI; T1(中国地理学会、中国地质学会、中国环境科学学会) | GeoRef（订阅） | ESS Open Archive; EarthArXiv | Crossref:ISSN |  |
| Advances in Atmospheric Sciences（Adv. Atmos. Sci.） | J | 0256-1530 / 1861-9533 | Springer / 中科院大气所 `springer_link` | T1(中国地质学会); T2(中国地球物理学会); 卓越-领军 | GeoRef（订阅）; ADS | ESS Open Archive; EarthArXiv | Crossref:ISSN | 中国(英文) |
| Atmospheric Chemistry and Physics（ACP） | J | — / 1680-7324 | Copernicus（EGU） | T1(中国地质学会); T2(中国地理学会); T3(中国环境科学学会) | GeoRef（订阅）; ADS | EGUsphere; ESS Open Archive | Crossref:ISSN; OAI-PMH 候选 | M1 候选：copernicus |
| Bulletin of the American Meteorological Society（BAMS） | J | 0003-0007 / 1520-0477 | AMS 美国气象学会 | T1(中国地质学会) | GeoRef（订阅） | ESS Open Archive; EarthArXiv | Crossref:ISSN | M1 候选：ametsoc |
| Journal of Climate（J. Climate） | J | 0894-8755 / 1520-0442 | AMS 美国气象学会 | T1(中国地理学会、中国地质学会) | GeoRef（订阅）; ADS | ESS Open Archive; EarthArXiv; arXiv:physics.ao-ph | Crossref:ISSN | 落地 journals.ametsoc.org；M1 候选 |

### 海洋（2）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Journal of Geophysical Research: Oceans（JGR Oceans） | J | 2169-9275 / 2169-9291 | AGU（Wiley 托管） `wiley` | T1(中国地质学会) | GeoRef（订阅）; ADS | ESS Open Archive; EarthArXiv; arXiv:physics.ao-ph | Crossref:ISSN |  |
| Journal of Physical Oceanography（JPO） | J | 0022-3670 / 1520-0485 | AMS 美国气象学会 | T1(中国地质学会) | GeoRef（订阅）; ADS | ESS Open Archive; EarthArXiv; arXiv:physics.ao-ph | Crossref:ISSN | M1 候选：ametsoc |

### 水文（4）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Hydrology and Earth System Sciences（HESS） | J | — / 1607-7938 | Copernicus（EGU） | T1(中国土壤学会、中国地球物理学会、中国地理学会 等 4 家) | GeoRef（订阅） | EGUsphere; ESS Open Archive | Crossref:ISSN; OAI-PMH 候选 | M1 候选：copernicus |
| Journal of Hydrology（J. Hydrol.） | J | 0022-1694 / — | Elsevier `elsevier_sd` | T1(中国土壤学会、中国地理学会、中国地质学会 等 4 家); T2(中国环境科学学会) | GeoRef（订阅） | ESS Open Archive; EarthArXiv | Crossref:ISSN |  |
| The Cryosphere（TC） | J | — / 1994-0424 | Copernicus（EGU） | T1(中国地理学会、中国地质学会) | GeoRef（订阅） | EGUsphere; ESS Open Archive | Crossref:ISSN; OAI-PMH 候选 | 冰冻圈；M1 候选 |
| Water Resources Research（WRR） | J | 0043-1397 / 1944-7973 | AGU（Wiley 托管） `wiley` | FMS-B; T1(中国岩石力学与工程学会); T2(中国地理学会、中国环境科学学会) | GeoRef（订阅） | ESS Open Archive; EarthArXiv | Crossref:ISSN |  |

### 环境与地球系统（6）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Biogeosciences（BG） | J | — / 1726-4189 | Copernicus（EGU） | T1(中国地质学会、中国生态学学会); T2(中国土壤学会、中国地理学会) | GeoRef（订阅） | EGUsphere; ESS Open Archive | Crossref:ISSN; OAI-PMH 候选 | M1 候选：copernicus |
| Earth System Science Data（ESSD） | J | — / 1866-3516 | Copernicus（EGU） | T1(中国地理学会、中国地质学会) | GeoRef（订阅） | EGUsphere; ESS Open Archive | Crossref:ISSN; OAI-PMH 候选 | 数据论文；M1 候选 |
| Earth's Future（Earths Future） | J | 2328-4277 / 2328-4277 | AGU（Wiley 托管） `wiley` | T1(中国地理学会、中国地质学会); T3(中国环境科学学会) | GeoRef（订阅） | ESS Open Archive; EarthArXiv | Crossref:ISSN | 全 OA |
| Geoscientific Model Development（GMD） | J | — / 1991-9603 | Copernicus（EGU） | T1(中国地质学会) | GeoRef（订阅） | EGUsphere; ESS Open Archive | Crossref:ISSN; OAI-PMH 候选 | 模式开发；M1 候选 |
| Global Biogeochemical Cycles（GBC） | J | 0886-6236 / 1944-9224 | AGU（Wiley 托管） `wiley` | T1(中国地质学会); T2(中国地理学会) | GeoRef（订阅） | ESS Open Archive; EarthArXiv | Crossref:ISSN |  |
| Nature Reviews Earth & Environment（Nat. Rev. Earth Environ.） | J | — / 2662-138X | Springer Nature `nature_portfolio` | T1(中国地理学会、中国地质学会); T2(中国环境科学学会) | GeoRef（订阅） | — | Crossref:ISSN | 综述刊 |

### 遥感与地理信息（3）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| IEEE Transactions on Geoscience and Remote Sensing（TGRS） | J | 0196-2892 / 1558-0644；dblp `journals/tgrs` | IEEE `ieee_xplore` | T1(中国地理学会、中国地质学会、中国遥感应用协会) | GeoRef（订阅）; dblp | arXiv:eess.IV; arXiv:cs.CV | Crossref:ISSN | dblp 收录 |
| ISPRS Journal of Photogrammetry and Remote Sensing（ISPRS J.） | J | 0924-2716 / — | Elsevier（ISPRS） `elsevier_sd` | T1(中国地球物理学会、中国地理学会、中国地质学会 等 4 家) | GeoRef（订阅） | arXiv:cs.CV; ESS Open Archive; EarthArXiv | Crossref:ISSN |  |
| Remote Sensing of Environment（RSE） | J | 0034-4257 / 1879-0704 | Elsevier `elsevier_sd` | T1(中国地理学会、中国遥感应用协会); T2(中国环境科学学会) | GeoRef（订阅） | ESS Open Archive; EarthArXiv | Crossref:ISSN |  |

### 行星科学（2）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Journal of Geophysical Research: Planets（JGR Planets） | J | 2169-9097 / 2169-9100 | AGU（Wiley 托管） `wiley` | T1(中国地球物理学会、中国地质学会) | ADS; GeoRef（订阅） | ESS Open Archive; EarthArXiv; arXiv:astro-ph.EP | Crossref:ISSN |  |
| Icarus | J | 0019-1035 / 1090-2643 | Elsevier `elsevier_sd` | — | ADS; GeoRef（订阅） | arXiv:astro-ph.EP | Crossref:ISSN | 兼物理与天文 |

### 古生物与地层（2）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Palaeogeography, Palaeoclimatology, Palaeoecology（Palaeo3） | J | 0031-0182 / — | Elsevier `elsevier_sd` | T1(中国地质学会); T2(中国地理学会) | GeoRef（订阅） | ESS Open Archive; EarthArXiv | Crossref:ISSN |  |
| Quaternary Science Reviews（QSR） | J | 0277-3791 / — | Elsevier `elsevier_sd` | T1(中国地理学会、中国地质学会) | GeoRef（订阅） | ESS Open Archive; EarthArXiv | Crossref:ISSN | 第四纪 |

### 中文刊（13）

子领域写在备注里。知网、万方、维普只接受用户导入题录；在 Crossref 注册了 DOI 的中文刊可经 Crossref 收元数据。

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| 地理学报（Acta Geogr. Sin.） | J | 0375-5444 / — | 中国地理学会 / 中科院地理所 | T1(中国地理学会、中国遥感应用协会); 卓越-领军; CSCD核心; 北大核心; 科技核心; AMI-顶级 | CNKI | ChinaXiv | 待勘察 | 遥感与地理信息；Crossref 404；Crossref 无记录 |
| 地质学报（Acta Geologica Sinica） | J | 0001-5717 / — | 中国地质学会 | T1(中国地质学会); 卓越-领军; CSCD核心; 北大核心; 科技核心 | CNKI; 万方; CSCD | ChinaXiv | 用户导入 | 地质学；Crossref该ISSN仅英文版旧记录；一期梯队 |
| 岩石学报（Acta Petrologica Sinica） | J | 1000-0569 / — | 中国矿物岩石地球化学学会 | T1(中国地球物理学会、中国地质学会); 卓越-领军; CSCD核心; 北大核心; 科技核心 | CNKI; 万方; CSCD | ChinaXiv | Crossref:ISSN | 地质学；Crossref前缀10.18654 |
| 测绘学报（Acta Geodaetica et Cartographica Sinica） | J | 1001-1595 / — | 中国测绘学会 | T1(中国地理学会、中国遥感应用协会); T2(中国地球物理学会); 卓越-领军; CSCD核心; 北大核心; 科技核心 | CNKI; 万方; CSCD | ChinaXiv | 用户导入 | 测绘遥感；Crossref无该ISSN记录；一期梯队 |
| 遥感学报（National Remote Sensing Bulletin） | J | 1007-4619 / — | 中国科学院空天信息创新研究院 | T1(中国地理学会、中国遥感应用协会); T2(中国地球物理学会); T3(中国环境科学学会); 卓越-领军; CSCD核心; 北大核心; 科技核心 | CNKI; 万方; CSCD | ChinaXiv | Crossref:ISSN | 测绘遥感；Crossref前缀10.11834 |
| 地理研究（Geographical Research） | J | 1000-0585 / — | 中国地理学会 | T1(中国地理学会、中国遥感应用协会); T2(中国地理学会); CSSCI; CSCD核心; 北大核心; 科技核心; AMI-核心 | CNKI; 万方; CSCD | ChinaXiv | 用户导入 | 地理学；Crossref无该ISSN记录 |
| 地理科学（Scientia Geographica Sinica） | J | 1000-0690 / — | 中国科学院东北地理与农业生态研究所 | T1(中国地理学会、中国遥感应用协会); T2(中国地理学会); CSSCI; CSCD核心; 北大核心; 科技核心; AMI-核心 | CNKI; 万方; CSCD | ChinaXiv | 用户导入 | 地理学；Crossref无该ISSN记录 |
| 中国科学:地球科学（Scientia Sinica Terrae） | J | 1674-7240 / — | 中国科学杂志社 `sciengine` | T1(中国地球物理学会、中国地理学会、中国地质学会 等 4 家); T2(中国环境科学学会); 卓越-梯队; CSCD核心; 北大核心; 科技核心 | CNKI; 万方; CSCD | ChinaXiv | Crossref:ISSN | 综合地学；Crossref前缀10.1360 |
| 地球化学（Geochimica） | J | 0379-1726 / — | 中国科学院广州地球化学研究所 | T1(中国地质学会); CSCD核心; 北大核心; 科技核心 | CNKI; 万方; CSCD | ChinaXiv | 用户导入 | 地球化学；Crossref无该ISSN记录 |
| 地球物理学报（Chin. J. Geophys.） | J | 0001-5733 / — | 中国科学出版传媒（中国地球物理学会） `sciengine` | T1(中国地球物理学会、中国地质学会、中国岩石力学与工程学会); 卓越-梯队; CSCD核心; 北大核心; 科技核心 | GeoRef（订阅）; CNKI | ChinaXiv | Crossref:ISSN | 地球物理与地震；落地 SciEngine；robots 禁 AI UA |
| 地质论评（Geological Review） | J | 0371-5736 / — | 中国地质学会 | T1(中国地质学会); T2(中国地球物理学会); CSCD核心; 北大核心; 科技核心 | CNKI; 万方; CSCD | ChinaXiv | 用户导入 | 地质学；Crossref无该ISSN记录 |
| 大气科学（Chinese Journal of Atmospheric Sciences） | J | 1006-9895 / — | 中国科学院大气物理研究所 | T1(中国地球物理学会、中国地质学会); T3(中国环境科学学会); CSCD核心; 北大核心; 科技核心 | CNKI; 万方; CSCD | ChinaXiv | 用户导入 | 大气科学；Crossref无该ISSN记录 |
| 海洋学报（Acta Oceanologica Sinica (Chinese)） | J | 0253-4193 / — | 中国海洋学会 | T1(中国地质学会、中国遥感应用协会); T2(中国地球物理学会); 卓越-梯队; CSCD核心; 北大核心; 科技核心 | CNKI; 万方; CSCD | ChinaXiv | 用户导入 | 海洋科学；Crossref无该ISSN记录；一期梯队 |

## 出处与说明

- **T 级**：取自科协总汇第五版的地球科学（中国地质学会，2023 修订）、地理资源（中国地理学会，2025）、地球物理（2025）、遥感（2024）、岩土（2022，原 CT/ET 分级折算为 T1–T3）、土壤（2024）、环境（2025）等目录。PDF 为中国地质大学（北京）的转载件，未与科协官方附件比对。
- **平台**：AGU 刊由 Wiley 托管，GSA 与 SSA 刊由 GeoScienceWorld 托管，都经 Crossref 落地 URL 核实。agupubs 与 GeoScienceWorld 站点有 Cloudflare 挑战，journals.ametsoc.org 返回 403，这三站只走 Crossref。Copernicus（EGU 全部 OA 刊）的 OAI-PMH 已证实可用（`egu` set，记录带 eISSN），列为 M1 候选，见[候选来源](../source-candidates.md)。
- **缺口**：GeoRef 是订阅库；GSL Lyell Collection、SEG、MSA、PANGAEA 等未调研。《地理学报》在 Crossref 返回 404。
