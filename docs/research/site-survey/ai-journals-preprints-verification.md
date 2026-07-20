---
title: 事实核验：AI/ML 期刊与预印本平台分类体系（subagent 原始报告归档）
status: approved
owner: fable5
updated: 2026-07-20
---

# 事实核验 · AI/ML 期刊 + 预印本分类体系

> 来源：Sonnet subagent 于 2026-07-20 逐项 Web 核验（78 次工具调用）。本文为原始返回的归档（格式微调）；提炼结论已写入 [catalog/ai-ml-journals.md](../../catalog/ai-ml-journals.md) 与 [catalog/preprint-platforms.md](../../catalog/preprint-platforms.md)。
> 置信度：标"[核验]"者有来源 URL 且当日访问成功；标 ⚠ 者未核验或存疑。

## 第一组：AI/ML/CS 期刊（全部 [核验]，来源见各行）

| 期刊 | 全名 | 出版方/平台 | ISSN (P/E) | 访问模式 | 关键来源 |
|---|---|---|---|---|---|
| TPAMI | IEEE Trans. Pattern Analysis and Machine Intelligence | IEEE CS（Xplore+CSDL） | 0162-8828 / 1939-3539 | 混合 | portal.issn.org；computer.org/csdl/journal/tp |
| TNNLS | IEEE Trans. Neural Networks and Learning Systems | IEEE CIS | 2162-237X / 2162-2388 | 混合 | portal.issn.org；cis.ieee.org |
| TKDE | IEEE Trans. Knowledge and Data Engineering | IEEE CS | 1041-4347 / 1558-2191 | 混合 | portal.issn.org |
| TIP | IEEE Trans. Image Processing | IEEE SPS | 1057-7149 / 1941-0042 | 混合（官方自述 hybrid） | signalprocessingsociety.org |
| TAFFC | IEEE Trans. Affective Computing | IEEE CS 等联办 | 1949-3045（电子；未见纸质） | 混合 | portal.issn.org |
| TASLP | **IEEE/ACM** Trans. Audio, Speech, and Language Processing | IEEE SPS + ACM 联办 | 2329-9290 / 2329-9304 | 混合 | portal.issn.org；dl.acm.org/journal/taslp |
| JMLR | Journal of Machine Learning Research | 自营非营利（jmlr.org） | 1532-4435（停印）/ 1533-7928 | **完全 OA** | jmlr.org |
| TMLR | Transactions on Machine Learning Research | **OpenReview 平台运行**，jmlr.org/tmlr 展示 | 2835-8856 | **完全 OA**（2022-06 创刊，无 APC） | jmlr.org/tmlr |
| MLJ | Machine Learning | Springer（原 Kluwer，2004 并入） | 0885-6125 / 1573-0565 | 混合 | link.springer.com/journal/10994 |
| AIJ | Artificial Intelligence | Elsevier | 0004-3702 / 1872-7921 | 混合 | sciencedirect.com |
| JAIR | Journal of AI Research | **AI Access Foundation**（jair.org 自营，非 AAAI） | 1076-9757 ⚠未分列 | **钻石 OA**（1993 起） | jair.org/about |
| TACL | Transactions of the ACL | **MIT Press 正式出版** + ACL Anthology 免费镜像 | 2307-387X | **钻石 OA** CC-BY 4.0 | direct.mit.edu/tacl；aclanthology.org/venues/tacl |
| IJCV | International Journal of Computer Vision | Springer | 0920-5691 / 1573-1405 | 混合（APC ~$4290） | link.springer.com/journal/11263 |
| Pattern Recognition | — | Elsevier | 0031-3203 / 1873-5142 | 混合（APC ~$2800） | sciencedirect.com |
| Neural Networks | — | Elsevier（INNS/APNNS/JNNS 官方刊） | 0893-6080 / 1879-2782 | 混合 | sciencedirect.com |
| Neurocomputing | — | Elsevier | 0925-2312 / 1872-8286 | 混合 | sciencedirect.com |
| Nature MI | Nature Machine Intelligence | Springer Nature | 2522-5839（电子） | 混合（APC €9500） | nature.com/natmachintell |
| CACM | Communications of the ACM | ACM | 0001-0782 / 1557-7317 | **OA（2024-02 起，先于全站）** | cacm.acm.org OA 公告 |
| JACM | Journal of the ACM | ACM | 0004-5411 / 1557-735X | **OA（2026-01 起随全站）** | dl.acm.org/journal/jacm/open-access |
| FnT ML | Foundations and Trends in Machine Learning | now publishers | 1935-8237 / 1935-8245 | **订阅制** | nowpublishers.com/MAL |

**关键勘误（对训练知识/初稿的更正）**：
1. **TASLP 未并入 OJSP、未改名**——2026-07 仍独立活跃出版（Vol. 33, 2025 在刊）；与完全 OA 的 IEEE OJSP 是并存两刊。
2. **ACM OA 两个时间层**：CACM 2024-02 单独转 OA（Web-first）；JACM 等随 2026-01 全站转型——不可混淆。
3. JMLR 卷结构：2000–2004 纸质 8 期/年；之后连续发表按年归卷；Vol.20（2019）后纯电子。

## 第二组：预印本平台分类体系

### arXiv（来源 arxiv.org/category_taxonomy，[核验]）

- **cs.\* 全 40 个**：cs.AI, cs.AR, cs.CC, cs.CE, cs.CG, cs.CL, cs.CR, cs.CV, cs.CY, cs.DB, cs.DC, cs.DL, cs.DM, cs.DS, cs.ET, cs.FL, cs.GL, cs.GR, cs.GT, cs.HC, cs.IR, cs.IT, cs.LG, cs.LO, cs.MA, cs.MM, cs.MS, cs.NA, cs.NE, cs.NI, cs.OH, cs.OS, cs.PF, cs.PL, cs.RO, cs.SC, cs.SD, cs.SE, cs.SI, cs.SY
- **stat.\* 6 个**：stat.AP, stat.CO, stat.ME, **stat.ML**, stat.OT, stat.TH
- **econ.\* 3 个**：econ.EM, econ.GN, econ.TH
- **q-fin.\* 实为 9 个**（⚡ 初稿清单少了 q-fin.EC）：q-fin.CP, **q-fin.EC**, q-fin.GN, q-fin.MF, q-fin.PM, q-fin.PR, q-fin.RM, q-fin.ST, q-fin.TR

### SSRN（[核验]）

- 组织逻辑：Network（FEN/ERN/ARN/…）→ 主题 eJournal（数十/网络），**非嵌套子网**；
- FEN eJournal 例：Banking & Insurance、Capital Markets: Asset Pricing & Valuation、Corporate Finance 系、Derivatives、Behavioral & Experimental Finance、Cryptocurrency Research（全清单 ssrn.com/index.cfm/en/fen/fen-ejournals/）；
- URL：JEL 浏览 `papers.ssrn.com/sol3/displayjel.cfm`；eLibrary 浏览 `sol3/DisplayJournalBrowse.cfm`；单篇 `sol3/papers.cfm?abstract_id=`；network 页 `ssrn.com/index.cfm/en/{code}/`。

### RePEc / NEP（[核验]）

- IDEAS（Christian Zimmermann 维护）与 EconPapers（Sune Karlsson，Örebro University 托管）为同一 RePEc 数据的两个独立前端；全文不驻站；
- **NEP 共 111 个分类报告**；金融/计量/AI 相关活跃 10 个：nep-ban, nep-cba, nep-cfn, nep-fmk, nep-ifn, nep-isf, nep-mst, nep-ecm, nep-cmp, nep-ain；
- ⚡ **nep-fin 已于 2006-10-28 关闭停更**（"This report is closed"）——活跃清单勿引用。

### NBER（[核验]）

- 编号 `w{n}`（h/t 前缀历史遗留已停用）；
- 19 个正式 Program；相关代码：AP（Asset Pricing）、CF（Corporate Finance）、EFG、IFM、ME；⚠ "PE" 存 Public/Political Economy 两义未辨；
- **无官方 AI program**——Economics of AI 是 project/center（8230）与常设会议；
- Household Finance / Behavioral Finance 属 Working Groups（编制更松散，非 Program）。

### CEPR（[核验]）

- 订阅/会员制：摘要页公开；全文需 Site Authorisation / 个人订阅 / 单篇购买；CEPR 研究员与部分记者免费；
- RePEc 上 CEPR 条目常仅摘要（与 NBER 开放策略对比）。

### 其他（一句话定位，[核验]）

- **Research Square**：跨学科预印本+作者服务；Springer Nature "In Review" 通道；有 DOI、被 Scholar/Crossref 索引。
- **OSF Preprints**：Center for Open Science 的预印本发布与聚合入口（可跨库检索）。
- **EconStor**：ZBW（Leibniz）运营的经济/工商 OA 知识库，30 万+ 全文免费——欧洲经济学 WP 重要免费源。
