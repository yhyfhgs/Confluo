---
title: CS/AI 顶会清单
status: approved
owner: fable5
updated: 2026-07-23
---

# CS/AI 顶会

> 勘察依据 [research/site-survey/cs-ai-conferences.md](../research/site-survey/cs-ai-conferences.md)（2026-07-20 [LIVE]）。
> **DBLP `conf/{key}` 是所有会议的 VenueEra 历史主干与枚举备源**（D-012）。多数会议 auth=none。

## 机器学习

| id | 名称 | tier | 平台/adapter | DBLP key | metadata/fulltext | 历史起点 | 备注 |
|---|---|---|---|---|---|---|---|
| neurips | NeurIPS | T1 | neurips_proceedings（supported_since: phase-2） | conf/nips | proceedings.neurips.cc | 1987 | 评审版另在 openreview(2022+) |
| icml | ICML | T1 | pmlr（supported_since: phase-2） | conf/icml | PMLR | 2013(v28)系统收录 | 卷号映射见 quirks |
| iclr | ICLR | T1 | openreview（supported_since: phase-2，在线验收待 token） | conf/iclr | OpenReview | 2013 | venue `ICLR.cc/{y}/Conference`；v1/v2 双端点 |
| aistats | AISTATS | T1 | pmlr | conf/aistats | PMLR | 全程 | 勘误 2026-07-22：2007–2016 卷实测存活于 PMLR（v9/v15 HEAD 200，[LIVE] site-survey/pmlr）——"或在旧域"传闻证伪 |
| uai | UAI | T2 | pmlr(2020+)/auai | conf/uai | PMLR/AUAI | 2020 起 PMLR | 平台迁移 |
| colt | COLT | T1 | pmlr(2011+/v19 起，勘误 2026-07-22) | conf/colt | 多段 era | 1988 | ACM→Springer→PMLR 三段(D-012)；PMLR 段起点实测 v19/2011 |
| corl | CoRL | T2 | pmlr | conf/corl | PMLR | 2017 | 最干净单一体系 |

## NLP（全在 ACL Anthology，`acl_anthology` adapter，GitHub bulk 优先）

| id | 名称 | tier | Anthology venue | DBLP key | 备注 |
|---|---|---|---|---|---|
| acl | ACL | T1 | acl | conf/acl | ID `2023.acl-long.1` |
| emnlp | EMNLP | T1 | emnlp | conf/emnlp | SIGDAT（supported_since: phase-2） |
| naacl | NAACL | T1 | naacl | conf/naacl | 非每年 |
| coling | COLING | T2 | coling | conf/coling | ICCL 主办 |
| eacl | EACL | T2 | eacl | conf/eacl | 非每年 |

## 计算机视觉

| id | 名称 | tier | 平台/adapter | DBLP key | 历史起点 | 备注 |
|---|---|---|---|---|---|---|
| cvpr | CVPR | T1 | cvf（supported_since: phase-2） | conf/cvpr | CVF 2013+ | 早期仅 IEEE |
| iccv | ICCV | T1 | cvf（supported_since: phase-2） | conf/iccv | CVF 2013+ | 双年(奇数) |
| wacv | WACV | T2 | cvf（supported_since: phase-2） | conf/wacv | CVF ~2020+ | |
| eccv | ECCV | T1 | springer(正式)/cvf(镜像) | conf/eccv | Springer LNCS | CVF 新格式 ⚠核；双年(偶数) |
| bmvc | BMVC | T3 | bmvc(专用) | conf/bmvc | 域名年年变 | 三段史，DBLP 导航 |

## 综合 AI

| id | 名称 | tier | 平台/adapter | DBLP key | 备注 |
|---|---|---|---|---|---|
| aaai | AAAI | T1 | aaai_ojs（supported_since: phase-2）（volume_map **已注册** 2019+，更早届经 D-012 走 DBLP+era） | conf/aaai | 全库收割 [LIVE 2026-07-23]：实测确认 OJS 实例上 2010–2018（Vol.24–32）同构可收割，**是否扩容 volume_map 待裁决**（design/adapters/aaai-ojs.md §10 ★F）；IAAI/EAAI 独立 issue 归属已闭合（同 §4） |
| ijcai | IJCAI | T1 | ijcai(专用) | conf/ijcai | 主域稳定；2017+ 自出版 |

## 数据挖掘 / IR / Web（ACM 系，`acm_dl`，**2026 起全 OA** D-013）

| id | 名称 | tier | 平台 | DBLP key | 备注 |
|---|---|---|---|---|---|
| kdd | KDD | T1 | acm_dl | conf/kdd | 2024 起一年两卷(V.1/V.2) |
| www | WWW/TheWebConf | T1 | acm_dl | conf/www | 域名年年变；archives.iw3c2.org 导航 |
| wsdm | WSDM | T2 | acm_dl | conf/wsdm | |
| sigir | SIGIR | T1 | acm_dl | conf/sigir | 1978 起 |
| cikm | CIKM | T2 | acm_dl | conf/cikm | |
| recsys | RecSys | T2 | acm_dl | conf/recsys | |
| icdm | ICDM | T2 | **ieee_xplore** | conf/icdm | **IEEE 非 ACM**；conhome 逐年随机 |

## 理论（TCS）

| id | 名称 | tier | 平台/adapter | DBLP key | 备注 |
|---|---|---|---|---|---|
| stoc | STOC | T1 | acm_dl | conf/stoc | 2026 OA；作者常挂 ECCC/arXiv |
| focs | FOCS | T1 | **ieee_xplore** | conf/focs | IEEE 订阅；ECCC/arXiv 替代 |
| soda | SODA | T1 | **siam** | conf/soda | **SIAM 非 ACM**；epubs.siam.org |
| itcs | ITCS | T2 | lipics(2017+) | conf/innovations | 三段 era(自建→ACM→LIPIcs) |
| ec | EC (Economics and Computation) | T1 | acm_dl | conf/sigecom | 2014 前名 Electronic Commerce（双名检索） |
| wine | WINE | T2 | springer | conf/wine | 域名年年变，DBLP 导航 |

## 语音 / 机器人 / 系统（选列）

| id | 名称 | tier | 平台/adapter | DBLP key | 备注 |
|---|---|---|---|---|---|
| icassp | ICASSP | T2 | ieee_xplore | conf/icassp | conhome 逐年随机 |
| interspeech | INTERSPEECH | T2 | isca | conf/interspeech | ISCA Archive OA |
| icra | ICRA | T2 | ieee_xplore | conf/icra | RA-L 双轨 |
| iros | IROS | T2 | ieee_xplore | conf/iros | RA-L 双轨 |
| rss | RSS | T2 | rss_proceedings | conf/rss | roboticsproceedings.org OA |
| osdi | OSDI | T3 | usenix | conf/osdi | 全 OA |
| sosp | SOSP | T3 | acm_dl | conf/sosp | 2026 OA |
| sigmod | SIGMOD | T3 | acm_dl | conf/sigmod | 2023 起 PACMMOD 期刊化 |
| vldb | VLDB | T3 | pvldb | conf/vldb | PVLDB 2008+ OA |

## PMLR 卷号↔年份映射（`pmlr` quirks 初始表，[LIVE]）

| 会议 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|
| ICML | v139 | v162 | v202 | v235 | v267 | — |
| AISTATS | — | — | v206 | v238 | v258 | — |
| COLT | — | — | — | v247 | v291 | v336 |
| CoRL | — | — | v229 | v270 | v305 | — |
| UAI | — | — | — | v244 | v286 | — |

> 实现期每年新增一行；映射写入各会议 VenueSpec 的 `quirks.volume_map`。

## 枚举策略统一口径

- 历史回填：**DBLP `conf/{key}/{key}{year}.xml`**（结构化，一次拿全）→ 平台官方结构交叉对账（paper_count_claimed）；
- 追新：`crawler track`（DBLP 新卷 / OpenReview 新 venue / PMLR 新卷）→ 人工确认（D-012）；
- IEEE 系（ICDM/FOCS/ICASSP/ICRA/IROS）conhome ID 逐年随机 → 经 DBLP 的 `ee` 外链或 IEEE 元数据 API 定位，不猜测。
