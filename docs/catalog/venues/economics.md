---
title: 经济 venue 名录
status: draft
owner: opus5.5-primary
updated: 2026-09-27
---

# 经济 venue 名录

> 经济共 98 个 venue（期刊 89、会议 9），分 16 个子领域，另有中文刊 15 个。主要学科库：RePEc、EconBiz、zbMATH、CNKI、万方、维普（中文刊）；主要预印本与 WP 通道：NBER、SSRN、CEPR、arXiv econ。评级标签的体系、版本与许可见[评级体系](../venue-rankings.md)，七类分层见[来源分层](../source-taxonomy.md)。

## 关联图

```mermaid
flowchart LR
  D(("经济<br/>98"))
  D --> S0["综合 · 17"]
  S0 --- V0["AER · ECMA · JPE · QJE …"]
  D --> S1["理论与博弈 · 7"]
  S1 --- V1["AEJ:Micro · GEB · JET · TE …"]
  D --> S2["计量 · 6"]
  S2 --- V2["ETheory · JBES · JoE · JAE …"]
  D --> S3["宏观与货币 · 7"]
  S3 --- V3["AEJ:Macro · JME · JEDC · JEG …"]
  D --> S4["国际 · 2"]
  S4 --- V4["JIE · IMFER"]
  D --> S5["公共 · 4"]
  S5 --- V5["JPubE · AEJ:Policy · ITAX · NTJ"]
  D --> S6["劳动 · 4"]
  S6 --- V6["JOLE · ILRR · JHR · LabEc"]
  D --> S7["发展 · 4"]
  S7 --- V7["WD · JDE · EDCC · WBER"]
  D --> S8["产业组织 · 4"]
  S8 --- V8["RAND · IJIO · JIndE · JEMS"]
  D --> S9["城市与区域 · 3"]
  S9 --- V9["JUE · JEcGeo · RSUE"]
  D --> S10["健康 · 3"]
  S10 --- V10["HEcon · JHE · AJHE"]
  D --> S11["环境与资源 · 4"]
  S11 --- V11["AJAE · JEEM · EnEco · JAERE"]
  D --> S12["实验与行为 · 3"]
  S12 --- V12["ExpEc · JEBO · JRU"]
  D --> S13["经济史 · 3"]
  S13 --- V13["JEH · EHR · EEH"]
  D --> S14["政治经济与法经济 · 3"]
  S14 --- V14["JLE · JLEO · PubCh"]
  D --> S15["会议 · 9"]
  S15 --- V15["ASSA · AMES · EEA · ESWC …"]
  D --> SCN["中文刊 · 15"]
  SCN --- VCN["中国人口·资源与环境 · 数量经济技术经济研究 · 世界经济 · 中国农村经济 …"]
  subgraph M1["M1 出版与托管"]
    P0{{"Elsevier · 21"}}
    P1{{"AEA · 10"}}
    P2{{"UChicago Press · 9"}}
    P3{{"Wiley · 9"}}
    P4{{"OUP · 8"}}
    P5{{"Econometric Society · 7"}}
  end
  M1 -. 出版/托管 .-> D
  subgraph L2A["L2a 文献库"]
    A0[("RePEc")]
    A1[("EconBiz")]
    A2[("zbMATH")]
    A3[("CNKI、万方、维普（中文刊）")]
  end
  D -. 被收录 .-> L2A
  subgraph L1B["L1b 预印本与 WP"]
    B0[["NBER"]]
    B1[["SSRN"]]
    B2[["CEPR"]]
    B3[["arXiv econ"]]
  end
  L1B -. 发表去向 .-> D
```

## 名录

每个子领域内按评级强弱排序，评级相同按名称。`接入` 一列：`Crossref:ISSN` 指由 Crossref 委托按 ISSN 收元数据，`现有:`/`平台:` 指经名录里已有的来源行，`用户导入` 指只接受用户导出的题录。

### 综合（17）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| American Economic Review（AER） | J | 0002-8282 / 1944-7981 | AEA（Atypon） `aea_journals` | Top5; FT50; NI; ABDC-A*; VHB-A+; FMS-A | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| Econometrica（ECMA） | J | 0012-9682 / 1468-0262 | Econometric Society（自营） `econsoc_journals` | Top5; FT50; NI; ABDC-A*; VHB-A+; FMS-A | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| Journal of Political Economy（JPE） | J | 0022-3808 / 1537-534X | UChicago Press（Atypon） `uchicago_journals` | Top5; FT50; NI; ABDC-A*; VHB-A+; FMS-A | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| Quarterly Journal of Economics（QJE） | J | 0033-5533 / 1531-4650 | Oxford Academic `oup_academic` | Top5; FT50; NI; ABDC-A*; FMS-A | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| Review of Economic Studies（REStud） | J | 0034-6527 / 1467-937X | Oxford Academic `oup_academic` | Top5; FT50; NI; ABDC-A*; FMS-A | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| American Economic Journal: Applied Economics（AEJ:Applied） | J | 1945-7782 / 1945-7790 | AEA `aea_journals` | ABDC-A*; FMS-A | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| International Economic Review（IER） | J | 0020-6598 / 1468-2354 | Wiley `wiley` | ABDC-A*; FMS-A | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| Journal of Economic Literature（JEL） | J | 0022-0515 / 2328-8175 | AEA `aea_journals` | ABDC-A*; FMS-A | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| Journal of Economic Perspectives（JEP） | J | 0895-3309 / — | AEA `aea_journals` | ABDC-A*; FMS-A | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| Journal of the European Economic Association（JEEA） | J | 1542-4766 / 1542-4774 | Oxford Academic `oup_academic` | ABDC-A*; FMS-A | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| Review of Economics and Statistics（REStat） | J | 0034-6535 / 1530-9142 | MIT Press Direct `mit_press_direct` | ABDC-A*; FMS-A | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| The Economic Journal（EJ） | J | 0013-0133 / 1468-0297 | Oxford Academic `oup_academic` | ABDC-A*; FMS-A | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| American Economic Review: Insights（AERI） | J | 2640-205X / — | AEA `aea_journals` | ABDC-A*; FMS-B | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| European Economic Review（EER） | J | 0014-2921 / — | Elsevier `elsevier_sd` | ABDC-A*; FMS-B | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| AEA Papers and Proceedings（AEA P&P） | J | 2574-0768 / 2574-0776 | American Economic Association `aea_journals` | — | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN | 会议论文集性质(ASSA 选文) |
| Journal of Political Economy Macroeconomics（JPE Macro） | J | 2832-9341 / 2832-935X | The University of Chicago Press `uchicago_journals` | ABDC-A | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| Journal of Political Economy Microeconomics（JPE Micro） | J | 2832-9368 / 2832-9376 | The University of Chicago Press `uchicago_journals` | ABDC-A | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |

### 理论与博弈（7）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| American Economic Journal: Microeconomics（AEJ:Micro） | J | 1945-7669 / 1945-7685 | American Economic Association `aea_journals` | ABDC-A*; FMS-A | RePEc; EconBiz | SSRN; arXiv:econ.TH | Crossref:ISSN |  |
| Games and Economic Behavior（GEB） | J | 0899-8256 / 1090-2473 | Elsevier `elsevier_sd` | ABDC-A*; FMS-A | RePEc; EconBiz; zbMATH | SSRN; arXiv:econ.TH | Crossref:ISSN |  |
| Journal of Economic Theory（JET） | J | 0022-0531 / 1095-7235 | ScienceDirect `elsevier_sd` | ABDC-A*; FMS-A | RePEc; EconBiz; zbMATH | SSRN; arXiv:econ.TH | Crossref:ISSN |  |
| Theoretical Economics（TE） | J | 1933-6837 / 1555-7561 | Econometric Society（OJS） `econsoc_journals` | ABDC-A*; FMS-A | RePEc; EconBiz; zbMATH | SSRN; arXiv:econ.TH | Crossref:ISSN |  |
| Economic Theory（ET） | J | 0938-2259 / 1432-0479 | Springer-Verlag `springer_link` | ABDC-A*; FMS-B | RePEc; EconBiz; zbMATH | SSRN; arXiv:econ.TH | Crossref:ISSN |  |
| International Journal of Game Theory（IJGT） | J | 0020-7276 / 1432-1270 | Springer-Verlag `springer_link` | ABDC-A | RePEc; EconBiz; zbMATH | SSRN; arXiv:econ.TH | Crossref:ISSN |  |
| Journal of Mathematical Economics（JMathE） | J | 0304-4068 / — | Elsevier `elsevier_sd` | ABDC-A; FMS-B; T3(中国数学会) | RePEc; EconBiz; zbMATH | SSRN; arXiv:econ.TH | Crossref:ISSN |  |

### 计量（6）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Econometric Theory（ETheory） | J | 0266-4666 / 1469-4360 | Cambridge University Press `cambridge_core` | ABDC-A*; FMS-A | RePEc; EconBiz | arXiv:econ.EM; SSRN | Crossref:ISSN |  |
| Journal of Business & Economic Statistics（JBES） | J | 0735-0015 / 1537-2707 | Informa UK (American Statistical Association) `tandf_online` | ABDC-A*; FMS-A | RePEc; EconBiz | arXiv:econ.EM; SSRN | Crossref:ISSN |  |
| Journal of Econometrics（JoE） | J | 0304-4076 / 1872-6895 | ScienceDirect `elsevier_sd` | ABDC-A*; FMS-A | RePEc; EconBiz | arXiv:econ.EM; SSRN | Crossref:ISSN |  |
| Journal of Applied Econometrics（JAE） | J | 0883-7252 / 1099-1255 | Wiley (John Wiley & Sons) `wiley` | ABDC-A*; FMS-B | RePEc; EconBiz | arXiv:econ.EM; SSRN | Crossref:ISSN |  |
| Quantitative Economics（QE） | J | 1759-7323 / 1759-7331 | Econometric Society（OJS） `econsoc_journals` | ABDC-A*; FMS-B | RePEc; EconBiz | arXiv:econ.EM; SSRN | Crossref:ISSN |  |
| The Econometrics Journal（EctJ） | J | 1368-4221 / 1368-423X | Oxford University Press `oup_academic` | ABDC-A*; FMS-B | RePEc; EconBiz | arXiv:econ.EM; SSRN | Crossref:ISSN |  |

### 宏观与货币（7）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| American Economic Journal: Macroeconomics（AEJ:Macro） | J | 1945-7707 / 1945-7715 | AEA `aea_journals` | ABDC-A*; FMS-A | RePEc; EconBiz | NBER; CEPR; 央行WP | Crossref:ISSN |  |
| Journal of Monetary Economics（JME） | J | 0304-3932 / — | ScienceDirect `elsevier_sd` | ABDC-A*; FMS-A | RePEc; EconBiz | NBER; CEPR; 央行WP | Crossref:ISSN |  |
| Journal of Economic Dynamics and Control（JEDC） | J | 0165-1889 / — | Elsevier `elsevier_sd` | ABDC-A*; FMS-B | RePEc; EconBiz | NBER; CEPR; 央行WP | Crossref:ISSN |  |
| Journal of Economic Growth（JEG） | J | 1381-4338 / 1573-7020 | Springer-Verlag `springer_link` | ABDC-A*; FMS-B | RePEc; EconBiz | NBER; CEPR; 央行WP | Crossref:ISSN |  |
| Journal of Money, Credit and Banking（JMCB） | J | 0022-2879 / 1538-4616 | Wiley (Blackwell Publishing) `wiley` | ABDC-A*; FMS-B | RePEc; EconBiz | NBER; CEPR; 央行WP | Crossref:ISSN |  |
| Review of Economic Dynamics（RED） | J | 1094-2025 / — | Elsevier `elsevier_sd` | ABDC-A*; FMS-B | RePEc; EconBiz | NBER; CEPR; 央行WP | Crossref:ISSN |  |
| Brookings Papers on Economic Activity（BPEA） | J | 0007-2303 / 1533-4465 | Brookings Institution（Crossref 登记为 Project MUSE） | ABDC-A; FMS-B | RePEc; EconBiz | NBER; CEPR; 央行WP | Crossref:ISSN | Crossref 仅至1999，新刊待勘察 |

### 国际（2）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Journal of International Economics（JIE） | J | 0022-1996 / — | Elsevier `elsevier_sd` | ABDC-A*; FMS-A | RePEc; EconBiz | NBER; CEPR; IMF WP | Crossref:ISSN |  |
| IMF Economic Review（IMFER） | J | 2041-4161 / 2041-417X | Springer Science and Business Media LLC `springer_link` | ABDC-A; FMS-B | RePEc; EconBiz | NBER; CEPR; IMF WP | Crossref:ISSN |  |

### 公共（4）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Journal of Public Economics（JPubE） | J | 0047-2727 / — | Elsevier `elsevier_sd` | ABDC-A*; FMS-A | RePEc; EconBiz | NBER; CEPR | Crossref:ISSN |  |
| American Economic Journal: Economic Policy（AEJ:Policy） | J | 1945-774X / 1945-7731 | American Economic Association `aea_journals` | ABDC-A*; FMS-B | RePEc; EconBiz | NBER; CEPR | Crossref:ISSN | 种子外；Crossref 印刷/电子 ISSN 与常用号互换 |
| International Tax and Public Finance（ITAX） | J | 0927-5940 / 1573-6970 | Springer-Verlag `springer_link` | ABDC-A | RePEc; EconBiz | NBER; CEPR | Crossref:ISSN |  |
| National Tax Journal（NTJ） | J | 0028-0283 / 1944-7477 | The University of Chicago Press `uchicago_journals` | ABDC-A | RePEc; EconBiz | NBER; CEPR | Crossref:ISSN |  |

### 劳动（4）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Journal of Labor Economics（JOLE） | J | 0734-306X / 1537-5307 | The University of Chicago Press `uchicago_journals` | ABDC-A*; FMS-A | RePEc; EconBiz | NBER; IZA DP | Crossref:ISSN |  |
| ILR Review（ILRR） | J | 0019-7939 / 2162-271X | SAGE Publications `sage_journals` | ABDC-A*; FMS-B | RePEc; EconBiz | NBER; IZA DP | Crossref:ISSN |  |
| Journal of Human Resources（JHR） | J | 0022-166X / 1548-8004 | University of Wisconsin Press | ABDC-A*; FMS-B | RePEc; EconBiz | NBER; IZA DP | Crossref:ISSN | UW Press 自营，无 source_id |
| Labour Economics（LabEc） | J | 0927-5371 / — | Elsevier `elsevier_sd` | ABDC-A*; FMS-B | RePEc; EconBiz | NBER; IZA DP | Crossref:ISSN |  |

### 发展（4）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| World Development（WD） | J | 0305-750X / — | Elsevier `elsevier_sd` | ABDC-A*; FMS-B; T1(中国地理学会) | RePEc; EconBiz | NBER; World Bank PRWP | Crossref:ISSN |  |
| Journal of Development Economics（JDE） | J | 0304-3878 / — | Elsevier `elsevier_sd` | ABDC-A*; FMS-A | RePEc; EconBiz | NBER; World Bank PRWP | Crossref:ISSN |  |
| Economic Development and Cultural Change（EDCC） | J | 0013-0079 / 1539-2988 | The University of Chicago Press `uchicago_journals` | ABDC-A; FMS-B | RePEc; EconBiz | NBER; World Bank PRWP | Crossref:ISSN |  |
| World Bank Economic Review（WBER） | J | 0258-6770 / 1564-698X | Oxford University Press `oup_academic` | ABDC-A; FMS-B | RePEc; EconBiz | NBER; World Bank PRWP | Crossref:ISSN |  |

### 产业组织（4）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| RAND Journal of Economics | J | 0741-6261 / 1756-2171 | Wiley `wiley` | ABDC-A*; FMS-A | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| International Journal of Industrial Organization（IJIO） | J | 0167-7187 / — | Elsevier `elsevier_sd` | ABDC-A*; FMS-B | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| Journal of Industrial Economics（JIndE） | J | 0022-1821 / 1467-6451 | Wiley (Blackwell Publishing) `wiley` | ABDC-A*; FMS-B | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| Journal of Economics & Management Strategy（JEMS） | J | 1058-6407 / 1530-9134 | Wiley (Blackwell Publishing) `wiley` | ABDC-A; FMS-B | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |

### 城市与区域（3）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Journal of Urban Economics（JUE） | J | 0094-1190 / 1095-9068 | Elsevier `elsevier_sd` | ABDC-A*; FMS-A; T1(中国地理学会) | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| Journal of Economic Geography（JEcGeo） | J | 1468-2702 / 1468-2710 | Oxford University Press `oup_academic` | ABDC-A; FMS-B; T1(中国地理学会) | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| Regional Science and Urban Economics（RSUE） | J | 0166-0462 / — | Elsevier `elsevier_sd` | ABDC-A; FMS-B | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |

### 健康（3）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Health Economics（HEcon） | J | 1057-9230 / 1099-1050 | Wiley (John Wiley & Sons) `wiley` | ABDC-A*; FMS-A | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| Journal of Health Economics（JHE） | J | 0167-6296 / — | Elsevier `elsevier_sd` | ABDC-A*; FMS-A | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| American Journal of Health Economics（AJHE） | J | 2332-3493 / 2332-3507 | The University of Chicago Press `uchicago_journals` | ABDC-A*; FMS-B | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |

### 环境与资源（4）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| American Journal of Agricultural Economics（AJAE） | J | 0002-9092 / 1467-8276 | Wiley (Blackwell Publishing) `wiley` | ABDC-A*; FMS-A | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| Journal of Environmental Economics and Management（JEEM） | J | 0095-0696 / 1096-0449 | Elsevier `elsevier_sd` | ABDC-A*; FMS-A; T3(中国环境科学学会) | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| Energy Economics（EnEco） | J | 0140-9883 / — | Elsevier `elsevier_sd` | ABDC-A*; FMS-B | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| Journal of the Association of Environmental and Resource Economists（JAERE） | J | 2333-5955 / 2333-5963 | The University of Chicago Press `uchicago_journals` | ABDC-A*; FMS-B | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |

### 实验与行为（3）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Experimental Economics（ExpEc） | J | 1386-4157 / 1573-6938 | Cambridge University Press `cambridge_core` | ABDC-A*; FMS-B | RePEc; EconBiz | SSRN; OSF Preprints | Crossref:ISSN | 2024年起迁 CUP |
| Journal of Economic Behavior & Organization（JEBO） | J | 0167-2681 / — | Elsevier `elsevier_sd` | ABDC-A*; FMS-B | RePEc; EconBiz | SSRN; OSF Preprints | Crossref:ISSN |  |
| Journal of Risk and Uncertainty（JRU） | J | 0895-5646 / 1573-0476 | Springer-Verlag `springer_link` | ABDC-A*; FMS-B | RePEc; EconBiz | SSRN; OSF Preprints | Crossref:ISSN |  |

### 经济史（3）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Journal of Economic History（JEH） | J | 0022-0507 / 1471-6372 | Cambridge University Press `cambridge_core` | ABDC-A*; FMS-A | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| Economic History Review（EHR） | J | 0013-0117 / 1468-0289 | Wiley (Blackwell Publishing) `wiley` | ABDC-A*; FMS-B | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |
| Explorations in Economic History（EEH） | J | 0014-4983 / 1090-2457 | Elsevier `elsevier_sd` | ABDC-A; FMS-B | RePEc; EconBiz | NBER; CEPR; SSRN | Crossref:ISSN |  |

### 政治经济与法经济（3）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| Journal of Law and Economics（JLE） | J | 0022-2186 / 1537-5285 | The University of Chicago Press `uchicago_journals` | ABDC-A*; FMS-B | RePEc; EconBiz | SSRN; NBER | Crossref:ISSN |  |
| Journal of Law, Economics, and Organization（JLEO） | J | 8756-6222 / 1465-7341 | Oxford University Press `oup_academic` | ABDC-A; FMS-B | RePEc; EconBiz | SSRN; NBER | Crossref:ISSN |  |
| Public Choice（PubCh） | J | 0048-5829 / 1573-7101 | Springer-Verlag `springer_link` | ABDC-A | RePEc; EconBiz | SSRN; NBER | Crossref:ISSN |  |

### 会议（9）

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| ASSA Annual Meeting (AEA 等联合年会) | C | — | AEA/ASSA `assa_meetings` | — | RePEc | NBER; CEPR; SSRN | 现有:assa_meetings | 程序含JEL与摘要，部分PDF |
| Asian Meetings of the Econometric Society（AMES） | C | — | Econometric Society | — | RePEc | NBER; CEPR; SSRN | 待勘察 | 东亚/南亚/中国等分会 |
| EEA Annual Congress | C | — | European Economic Association | — | RePEc | NBER; CEPR; SSRN | 待勘察 | 与ESEM联合举办 |
| Econometric Society World Congress（ESWC） | C | — | Econometric Society | — | RePEc | NBER; CEPR; SSRN | 待勘察 | 每5年一届 |
| European Meeting of the Econometric Society（ESEM） | C | — | Econometric Society | — | RePEc | NBER; CEPR; SSRN | 待勘察 | 与EEA年会联合举办 |
| NBER Summer Institute（NBER SI） | C | — | NBER `nber_conferences` | — | RePEc | NBER; CEPR; SSRN | 现有:nber_conferences | 论文多链NBER WP |
| North American Summer Meeting of the Econometric Society（NASM） | C | — | Econometric Society | — | RePEc | NBER; CEPR; SSRN | 待勘察 |  |
| Royal Economic Society Annual Conference（RES） | C | — | Royal Economic Society | — | RePEc | NBER; CEPR; SSRN | 待勘察 |  |
| SED Annual Meeting | C | — | Society for Economic Dynamics `sed_meetings` | — | RePEc | NBER; CEPR; SSRN | 现有:sed_meetings | 论文在RePEc sed系列(待核) |

### 中文刊（15）

子领域写在备注里。知网、万方、维普只接受用户导入题录；在 Crossref 注册了 DOI 的中文刊可经 Crossref 收元数据。

| venue | 类型 | ISSN（印/电）或 dblp | 出版托管（M1） | 评级 | 学科库（L2a） | 预印本（L1b） | 接入 | 备注 |
|---|---|---|---|---|---|---|---|---|
| 中国人口·资源与环境（China Population, Resources and Environment） | J | 1002-2104 / — | 中国可持续发展研究会 | T1(中国地理学会); T2(中国环境科学学会); CSSCI; CSCD核心; 科技核心; AMI-权威; NSFC管理-B; FMS-T2 | CNKI; 万方; CSCD | — | 用户导入 | 资源环境经济；Crossref无该ISSN记录 |
| 数量经济技术经济研究（Journal of Quantitative & Technological Economics） | J | 1000-3894 / — | 中国社会科学院数量经济与技术经济研究所 | CSSCI; CSCD核心; 北大核心; 科技核心; AMI-权威; NSFC管理-A; FMS-T1 | CNKI; 万方; CSCD | — | 用户导入 | 数量经济与计量；Crossref无该ISSN记录 |
| 世界经济（The Journal of World Economy） | J | 1002-9621 / — | 中国世界经济学会 | CSSCI; 北大核心; 科技核心; AMI-顶级; FMS-T1 | CNKI; 万方; 维普 | — | 用户导入 | 国际经济；Crossref无该ISSN记录 |
| 中国农村经济（Chinese Rural Economy） | J | 1002-8870 / — | 中国社会科学院农村发展研究所 | CSSCI; 北大核心; 科技核心; AMI-权威; NSFC管理-B; FMS-T1 | CNKI; 万方; 维普 | — | 用户导入 | 农业经济；Crossref无该ISSN记录 |
| 中国工业经济（China Industrial Economics） | J | 1006-480X / — | 中国社会科学院工业经济研究所 | CSSCI; 北大核心; 科技核心; AMI-顶级; NSFC管理-A; FMS-T1 | CNKI; 万方; 维普 | — | 用户导入 | 产业经济；Crossref无该ISSN记录 |
| 经济研究（Economic Research Journal） | J | 0577-9154 / — | 中国社会科学院经济研究所 | CSSCI; 北大核心; 科技核心; AMI-顶级; FMS-T1 | CNKI; 万方; 维普 | — | 用户导入 | 综合经济；Crossref无该ISSN记录 |
| 统计研究（Statistical Research） | J | 1002-4565 / — | 中国统计学会; 国家统计局统计科学研究所 | CSSCI; 北大核心; 科技核心; AMI-权威; FMS-T1 | CNKI; 万方; 维普 | — | 用户导入 | 数量经济与计量；Crossref无该ISSN记录 |
| 经济学(季刊)（China Economic Quarterly） | J | 2095-1086 / — | 北京大学 | CSSCI; AMI-权威; FMS-T1 | CNKI; 万方; 维普 | — | 用户导入 | 综合经济；Crossref无该ISSN记录 |
| 计量经济学报（China Journal of Econometrics） | J | 2096-9732 / — | 中国科学院数学与系统科学研究院 | CSSCI扩展; CSCD核心; 科技核心; FMS-T1 | CNKI; 万方; CSCD | — | 用户导入 | 数量经济与计量；Crossref无该ISSN记录 |
| 农业经济问题（Issues in Agricultural Economy） | J | 1000-6389 / — | 中国农业经济学会 | CSSCI; 北大核心; 科技核心; AMI-核心; NSFC管理-A; FMS-T2 | CNKI; 万方; 维普 | — | 用户导入 | 农业经济；Crossref无该ISSN记录 |
| 南开经济研究（Nankai Economic Studies） | J | 1001-4691 / — | 南开大学经济学院 | CSSCI; 北大核心; 科技核心; AMI-核心; FMS-T2 | CNKI; 万方; 维普 | — | 用户导入 | 综合经济；Crossref无该ISSN记录 |
| 经济学动态（Economic Perspectives） | J | 1002-8390 / — | 中国社会科学院经济研究所 | CSSCI; 北大核心; 科技核心; AMI-权威; FMS-T2 | CNKI; 万方; 维普 | — | 用户导入 | 综合经济；Crossref无该ISSN记录 |
| 经济科学（Economic Science） | J | 1002-5839 / — | 北京大学 | CSSCI; 北大核心; 科技核心; AMI-核心; FMS-T2 | CNKI; 万方; 维普 | — | 用户导入 | 综合经济；Crossref无该ISSN记录 |
| 财经研究（Journal of Finance and Economics） | J | 1001-9952 / — | 上海财经大学 | CSSCI; 北大核心; 科技核心; AMI-核心; FMS-T2 | CNKI; 万方; 维普 | — | 用户导入 | 综合经济；Crossref无该ISSN记录 |
| 财贸经济（Finance & Trade Economics） | J | 1002-8102 / — | 中国社会科学院财经战略研究院 | CSSCI; 北大核心; 科技核心; AMI-权威; FMS-T2 | CNKI; 万方; 维普 | — | 用户导入 | 贸易与财政；Crossref无该ISSN记录 |

## 出处与说明

- **名录**：`Top5`（学界约定）；`FT50`（2026-04-29 修订版，经 McMaster 图书馆转载核对，FT 原页不可达）；`ABDC-*`（ABDC JQL 2025 本地文件按 ISSN 匹配，108 刊命中 107）；`NI`（AER、Econometrica、JPE、QJE、REStud）；`FMS-A/B`（FMS 2025）。
- **不标**：`TI-*`——Tinbergen 现行章程（2025–2028）改为按 JCR AIS 收刊，没有 AA/A/B 分级；`AJG-*`——AJG 2024 需要登录，没找到可访问的全表转载。
- **会议**：经济学会议没有正式或研究型的分档出处，不标评级。
- **其他**：BPEA（Brookings）在 Crossref 只到 1999 年；JHR（UW Press）没有对应的 source_id。
