---
title: AI/ML/CS 期刊清单
status: review
owner: fable5
updated: 2026-07-20
---

# AI/ML/CS 期刊

> 平台映射见 [publishers-platforms.md](publishers-platforms.md)。标 [VERIFIED] 的 ISSN/平台/访问模式经 subagent 于 2026-07-20 逐一核验（原始报告：[research/site-survey/ai-journals-preprints-verification.md](../research/site-survey/ai-journals-preprints-verification.md)）。
> 会议为主的 CS/AI 领域，期刊层重点收 IEEE 系 + 完全 OA 独立刊 + 少量 Elsevier/Springer 刊。

## IEEE 系（`ieee_xplore` adapter，订阅制混合刊，DOI 10.1109）[VERIFIED]

| id | 名称 | tier | Print/E-ISSN | 访问 | 备注 |
|---|---|---|---|---|---|
| tpami | IEEE Trans. Pattern Analysis and Machine Intelligence | T1 | 0162-8828 / 1939-3539 | 混合 | IEEE CS；CSDL 双托管 |
| tnnls | IEEE Trans. Neural Networks and Learning Systems | T1 | 2162-237X / 2162-2388 | 混合 | CIS |
| tkde | IEEE Trans. Knowledge and Data Engineering | T1 | 1041-4347 / 1558-2191 | 混合 | IEEE CS |
| tip | IEEE Trans. Image Processing | T2 | 1057-7149 / 1941-0042 | 混合 | SPS |
| taffc | IEEE Trans. Affective Computing | T2 | 1949-3045（电子） | 混合 | 纯电子刊（未见独立纸质 ISSN） |
| taslp | **IEEE/ACM** Trans. Audio, Speech, and Language Processing | T2 | 2329-9290 / 2329-9304 | 混合 | 官名含 "/ACM"；**未并入 OJSP、未改名**（勘误：与 OJSP 是并存两刊）|

> metadata_source 一律 `crossref`（ISSN 枚举）；fulltext_source=`ieee_xplore`；auth=institutional。

## 完全 OA 独立刊（无需认证，各自专属通道）[VERIFIED]

| id | 名称 | tier | 平台/adapter | ISSN | 备注 |
|---|---|---|---|---|---|
| jmlr | Journal of Machine Learning Research | T1 | `jmlr`（专用，静态站极规整） | 1532-4435 / 1533-7928 | 完全 OA；2004 后连续发表按年归卷；jmlr.org/papers/v{N}/ |
| tmlr | Transactions on Machine Learning Research | T1 | `openreview`（依托其平台运行） | 2835-8856 | 完全 OA；2022-06 创刊；滚动接收 |
| jair | Journal of Artificial Intelligence Research | T2 | `jair`（OJS 类，jair.org 自营） | 1076-9757 ⚠电子/纸质未分列 | 钻石 OA；出版方 AI Access Foundation（非 AAAI） |
| tacl | Transactions of the ACL | T1 | `acl_anthology`（镜像全文）/ mit_press（正式版） | 2307-387X | 钻石 OA CC-BY；**fulltext 走 Anthology 免登录** |

## ACM 刊（`acm_dl` adapter，D-013 OA 口径）[VERIFIED]

| id | 名称 | tier | ISSN | 访问 | 备注 |
|---|---|---|---|---|---|
| cacm | Communications of the ACM | T2 | 0001-0782 / 1557-7317 | **OA（2024-02 起，先于全站）** | Web-first |
| jacm | Journal of the ACM | T2 | 0004-5411 / 1557-735X | **OA（2026-01 起随 ACM 全站）** | 此前混合/订阅 |

## Elsevier 系（`elsevier_sd`，混合刊，DOI 10.1016）[VERIFIED]

| id | 名称 | tier | ISSN | 备注 |
|---|---|---|---|---|
| aij | Artificial Intelligence | T2 | 0004-3702 / 1872-7921 | |
| pattern_recognition | Pattern Recognition | T2 | 0031-3203 / 1873-5142 | |
| neural_networks | Neural Networks | T3 | 0893-6080 / 1879-2782 | INNS 等三学会官方刊 |
| neurocomputing | Neurocomputing | T3 | 0925-2312 / 1872-8286 | |

## Springer 系（`springer`，混合刊，DOI 10.1007）[VERIFIED]

| id | 名称 | tier | ISSN | 备注 |
|---|---|---|---|---|
| mlj | Machine Learning | T2 | 0885-6125 / 1573-0565 | 原 Kluwer，2004 并入 |
| ijcv | International Journal of Computer Vision | T2 | 0920-5691 / 1573-1405 | |
| nmi | Nature Machine Intelligence | T3 | 2522-5839（电子） | Nature Portfolio；订阅+高 APC 混合 |

## 其他

| id | 名称 | tier | 平台 | ISSN | 备注 |
|---|---|---|---|---|---|
| fnt_ml | Foundations and Trends in Machine Learning | T3 | `now_publishers`（⚠ 需新 adapter，暂缓） | 1935-8237 / 1935-8245 | **订阅制**（[VERIFIED] 非 OA） |

## 枚举与获取策略

- 全部期刊 metadata 走 `crossref`（ISSN+日期，AC-3.5 同款零爬取路径）；
- **OA 独立刊优先做**（jmlr/tmlr/tacl 无认证成本，Phase 2 可顺带）：jmlr 需一个轻量专用 adapter（静态 `papers/v{N}/` 卷页，结构与 pmlr 同族可复用解析基建）；tmlr 复用 `openreview`；tacl 复用 `acl_anthology`；
- IEEE 系全文成本最高（browser + conhome 定位），tier 内按需拉取而非全量回填；
- CS/AI 期刊相对会议是次要文献源——tier 整体低于同域会议（范围控制 R5）。

## 待核验

- jair 的 print ISSN 分列；jmlr 专用 adapter 的卷页解析细节（实现期勘察）；
- IEEE OJ 系开放刊（OJSP 等）是否纳入清单（待用户需求确认，暂不登记）。
