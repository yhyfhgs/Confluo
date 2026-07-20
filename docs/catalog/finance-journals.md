---
title: 金融学期刊清单
status: approved
owner: fable5
updated: 2026-07-20
---

# 金融学期刊

> 平台映射见 [publishers-platforms.md](publishers-platforms.md)。ISSN 标 `⚠` 实现期以 Crossref 复核。

## Top 3（tier T1）

| id | 名称 | 平台/fulltext | ISSN ⚠核验 | DOI 前缀 | auth | 备注 |
|---|---|---|---|---|---|---|
| jf | Journal of Finance | `wiley` | 0022-1082 | 10.1111 | institutional | AFA；Wiley；SSRN 常有先行版 |
| jfe | Journal of Financial Economics | `elsevier_sd` | 0304-405X | 10.1016 | institutional | [LIVE]Elsevier；SSRN First Look 关系未证实 |
| rfs | Review of Financial Studies | `oup_silverchair` | 0893-9454 | 10.1093 | institutional | SFS；OUP |

## Field Top（tier T1/T2）

| id | 名称 | 平台/fulltext | ISSN ⚠ | DOI 前缀 | auth |
|---|---|---|---|---|---|
| jfqa | Journal of Financial and Quantitative Analysis | `cambridge` | 0022-1090 | 10.1017 | institutional |
| rof | Review of Finance | `oup_silverchair` | 1572-3097 | 10.1093 | institutional |
| jfi | Journal of Financial Intermediation | `elsevier_sd` | 1042-9573 | 10.1016 | institutional |
| jbf | Journal of Banking & Finance | `elsevier_sd` | 0378-4266 | 10.1016 | institutional |
| jfmarkets | Journal of Financial Markets | `elsevier_sd` | 1386-4181 | 10.1016 | institutional |
| jcorpfin | Journal of Corporate Finance | `elsevier_sd` | 0929-1199 | 10.1016 | institutional |
| jfineco_acct | Journal of Accounting and Economics | `elsevier_sd` | 0165-4101 | 10.1016 | institutional |
| raps | Review of Asset Pricing Studies | `oup_silverchair` | 2045-9920 | 10.1093 | institutional |
| rcfs | Review of Corporate Finance Studies | `oup_silverchair` | 2046-9128 | 10.1093 | institutional |
| jffr | J. Financial and Quantitative（见 jfqa） | — | — | — | — |

## 量化 / 数理金融（tier T1/T2）

| id | 名称 | 平台/fulltext | ISSN ⚠ | DOI 前缀 | auth | 备注 |
|---|---|---|---|---|---|---|
| mathfin | Mathematical Finance | `wiley` | 0960-1627 | 10.1111 | institutional | |
| finstoch | Finance and Stochastics | `springer` | 0949-2984 | 10.1007 | institutional | journal-id 780 ⚠ |
| quantfin | Quantitative Finance | `tandf`(⚠平台核) | 1469-7688 | 10.1080 | institutional | Taylor & Francis |
| sifin | SIAM J. on Financial Mathematics | `siam` | 1945-497X | 10.1137 | institutional | epubs.siam.org |
| jfec | Journal of Financial Econometrics | `oup_silverchair` | 1479-8409 | 10.1093 | institutional | |
| jempfin | Journal of Empirical Finance | `elsevier_sd` | 0927-5398 | 10.1016 | institutional | |

## 实务 / PM Research 系（`pm_research` adapter，DOI 10.3905）

| id | 名称 | tier | ISSN ⚠ | 备注 |
|---|---|---|---|---|
| jpm | Journal of Portfolio Management | T2 | 0095-4918 | 小平台谨慎限速 |
| jod | Journal of Derivatives | T2 | 1074-1240 | |
| jfds | Journal of Financial Data Science | T3 | 2640-3943 | 量化/ML |
| arfe | Annual Review of Financial Economics | T3 | `annual_reviews`(⚠) 1941-1367 | Annual Reviews 平台 |

## 枚举与获取策略

- 时间轴与清单：`crossref` 按 ISSN（JF 可回溯至 1946）；
- **SSRN 是金融 working paper 的关键先行源**（D-011）：JF/JFE/RFS 论文常先在 SSRN；订阅缺失时 SSRN 公开版 + Unpaywall 兜底；
- JFE 走 Elsevier（[LIVE] Cloudflare + TDM opt-out，走 API 优先）；JF/ECMA/MathFin 走 Wiley（TDM API 优先）；RFS/RoF/RAPS/RCFS 走 OUP 一个 adapter 全包。

## 待核验

- Quantitative Finance 平台（Taylor & Francis, tandfonline.com）、Annual Review of Financial Economics（Annual Reviews）、JHR 类小平台是否新建 adapter（tier 决定）；
- 各刊电子 ISSN 与 Finance and Stochastics 的 Springer journal-id。
