---
title: 经济学期刊清单
status: approved
owner: fable5
updated: 2026-07-27
---

# 经济学期刊

> 平台映射见 [publishers-platforms.md](publishers-platforms.md)。ISSN 标 `⚠` 者实现期以 Crossref 复核。metadata_source 一律 `crossref`（按 ISSN 枚举全史卷期）；fulltext_source 见各行。

## Top 5（tier T1）

| id | 名称 | 平台/fulltext | ISSN ⚠核验 | DOI 前缀 | auth | 备注 |
|---|---|---|---|---|---|---|
| aer | American Economic Review | `aea`（supported_since: phase-5） | 0002-8282 | 10.1257 | institutional | AEA 自营；AER: Insights 另刊 |
| ecma | Econometrica | `econsoc`（当前段自营 OA）/`wiley`（过刊段，D-028） | 0012-9682 | 10.3982 | institutional | Econometric Society，Wiley 出版 |
| jpe | Journal of Political Economy | `uchicago` | 0022-3808 | 10.1086 | institutional | UChicago Press |
| qje | Quarterly Journal of Economics | `oup_silverchair` | 0033-5533 | 10.1093 | institutional | OUP |
| restud | Review of Economic Studies | `oup_silverchair` | 0034-6527 | 10.1093 | institutional | OUP（RES 学会） |

## AEA 系列（`aea` adapter，DOI 10.1257，supported_since: phase-5）

| id | 名称 | tier | ISSN ⚠ | 备注 |
|---|---|---|---|---|
| aeri | AER: Insights | T2 | 2640-205X | ISSN [LIVE 2026-07-26] crossref 核实 |
| aej_macro | AEJ: Macroeconomics | T1 | 1945-7707 | ISSN [LIVE 2026-07-26] crossref 核实 |
| aej_micro | AEJ: Microeconomics | T1 | 1945-7669 | ISSN [LIVE 2026-07-26] crossref 核实 |
| aej_applied | AEJ: Applied Economics | T1 | 1945-7782 | ISSN [LIVE 2026-07-26] crossref 核实 |
| aej_policy | AEJ: Economic Policy | T1 | 1945-7731 | ISSN [LIVE 2026-07-26] crossref 核实 |
| jel | Journal of Economic Literature | T2 | 0022-0515 | 综述；ISSN [LIVE 2026-07-26] crossref 核实 |
| jep | Journal of Economic Perspectives | T2 | 0895-3309 | **全刊免费**（[LIVE] 2026-07-20 官方口径），auth=none |

## Field Top 与次级（tier T1/T2）

| id | 名称 | 平台/fulltext | ISSN ⚠ | DOI 前缀 | auth |
|---|---|---|---|---|---|
| restat | Review of Economics and Statistics | `mit_press`（[LIVE]确认 direct.mit.edu/rest；TDM 禁脚本→仅按需单篇） | 0034-6535 | 10.1162 | institutional |
| jeea | J. of the European Economic Association | `oup_silverchair` | 1542-4766 | 10.1093 | institutional |
| ej | The Economic Journal | `oup_silverchair` | 0013-0133 | 10.1093 | institutional |
| ier | International Economic Review | `wiley` | 0020-6598 | 10.1111 | institutional |
| jinteco | Journal of International Economics | `elsevier_sd` | 0022-1996 | 10.1016 | institutional |
| jdeveco | Journal of Development Economics | `elsevier_sd` | 0304-3878 | 10.1016 | institutional |
| jpubeco | Journal of Public Economics | `elsevier_sd` | 0047-2727 | 10.1016 | institutional |
| jmoneco | Journal of Monetary Economics | `elsevier_sd` | 0304-3932 | 10.1016 | institutional |
| jet | Journal of Economic Theory | `elsevier_sd` | 0022-0531 | 10.1016 | institutional |
| jeconometrics | Journal of Econometrics | `elsevier_sd` | 0304-4076 | 10.1016 | institutional |
| jole | Journal of Labor Economics | `uchicago` | 0734-306X | 10.1086 | institutional |
| jhr | Journal of Human Resources | `uwpress`(⚠平台核) | 0022-166X | 10.3368 | institutional |
| rand | RAND Journal of Economics | `wiley` | 0741-6261 | 10.1111 | institutional |

## 开放获取 / 学会刊（`econsoc` adapter，无需认证，supported_since: phase-5）

| id | 名称 | tier | 平台 | ISSN ⚠ | 备注 |
|---|---|---|---|---|---|
| te | Theoretical Economics | T1 | econsoc | 1933-6837 | **完全 OA** |
| qe | Quantitative Economics | T1 | econsoc | 1759-7323 | **完全 OA** |

## 计量理论刊（订阅制）

| id | 名称 | tier | 平台/fulltext | ISSN ⚠ | DOI 前缀 | auth |
|---|---|---|---|---|---|---|
| et | Econometric Theory | T2 | `cambridge` | 0266-4666 | 10.1017 | institutional |

## 枚举与获取策略

- 全史时间轴与每期清单：`crossref` 按 ISSN 枚举（QJE 可回溯至 1886 的 DOI 化部分；早于 DOI 时代过刊在 JSTOR，tier T3）；
- 全文：AEA/AEJ 常有 working paper 先行版（作者页/NBER/SSRN），无订阅时经 Unpaywall/RePEc 找 OA 副本；
- TE/QE 完全开放——优先级最高、最省心，Phase 5 早做。

## 待核验

- 各刊当前 ISSN（尤其电子 ISSN）以 Crossref `/journals/{issn}` 复核；
- REStat 的 MIT Press 平台细节（direct.mit.edu，Silverchair 系）；JHR 的 UW Press 平台；
- AEA 会员登录与哪些内容对会员免费的边界。
