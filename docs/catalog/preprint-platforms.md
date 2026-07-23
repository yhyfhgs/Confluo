---
title: 预印本/工作论文平台清单与订阅范围
status: review
owner: fable5
updated: 2026-07-24
---

# 预印本 / 工作论文平台

> 需求边界（FR-15/需求§5）：**只覆盖 CS/AI、Econ、Fin（含 OR 交叉）**，不扩展其他领域；靠 category/network 白名单防过载。
> 分类体系经 subagent 2026-07-20 [VERIFIED]（原始报告：[research/site-survey/ai-journals-preprints-verification.md](../research/site-survey/ai-journals-preprints-verification.md)）；平台机制勘察见 [research/site-survey/arxiv.md](../research/site-survey/arxiv.md)、[econ-fin-preprints.md](../research/site-survey/econ-fin-preprints.md)。

## 1. arXiv（`arxiv` adapter，T1 主源；supported_since: phase-2，AC-2.3 已验收）

**venue 切分**：每个订阅相关 category 一条 `preprint_channel` VenueSpec（`arxiv-cs-lg.yaml` 等），月度虚拟桶（design/08 §1）。

**本项目默认白名单**（[VERIFIED] 对照官方 taxonomy）：

| 域 | categories |
|---|---|
| CS/AI 核心 | cs.AI · cs.LG · cs.CL · cs.CV · cs.IR · cs.MA · cs.NE · cs.RO · cs.SD |
| CS 理论/交叉（按需启用） | cs.GT · cs.DS · cs.CC · cs.CR · cs.DB · cs.SI · cs.HC · cs.IT |
| 统计 | stat.ML（+按需 stat.ME/stat.TH） |
| 经济（全部 3 个） | econ.EM · econ.GN · econ.TH |
| 量化金融（**全部 9 个**，勘误：q-fin.EC 曾被遗漏） | q-fin.CP · **q-fin.EC** · q-fin.GN · q-fin.MF · q-fin.PM · q-fin.PR · q-fin.RM · q-fin.ST · q-fin.TR |
| OR 交叉 | math.OC（运筹优化主阵地，OR 域订阅默认含） |

> cs.* 全集 40 个子分类清单在核验报告中留档；白名单外分类不建 VenueSpec（防过载），用户可随时按 FR-01 增补。

## 2. SSRN（`ssrn` adapter，T1，Econ/Fin 主源，D-011；supported_since: phase-5）

- 组织：Network → 主题 eJournal（**非嵌套子网**）[VERIFIED]；
- 本项目默认范围：**FEN**（Financial Economics Network，~30 eJournals：Asset Pricing、Corporate Finance、Market Microstructure、Derivatives、Behavioral Finance、Cryptocurrency…）、**ERN**（Economics Research Network：Econometrics、Development、Behavioral…）；
- URL 形态 [VERIFIED]：network 页 `ssrn.com/index.cfm/en/{fen|ern}/`；eJournal 清单 `.../fen-ejournals/`；JEL 浏览 `papers.ssrn.com/sol3/displayjel.cfm`；单篇 `papers.ssrn.com/sol3/papers.cfm?abstract_id={id}`；
- auth：`free_account_preferred`；Cloudflare [LIVE-TESTED] → 浏览器上下文 + 1 req/5s + 日配额（详见 [adapter](../design/adapters/ssrn.md)）；
- 订阅：eJournal 白名单 + 本地关键词过滤（无查询 API，design/09）。

## 3. RePEc / IDEAS / EconPapers（`repec` adapter，T1 元数据主干）

- 定位：Econ WP **书目主干**（5.4M+ 条，覆盖 NBER/CEPR 等 2000+ archive）；不自托管全文（~89% 链出）；
- 通道：**FTP bulk（首选）** `ftp.repec.org/opt/ReDIF/RePEc/` · OAI-PMH `oai.repec.org`（官方称偶尔不稳）· 官方不建议爬网页；
- handle：`RePEc:nbr:nberwo:{n}`（NBER）、`RePEc:cpr:ceprdp:{n}`（CEPR）→ identifier scheme `repec`；
- **NEP 邮件列表分类**（订阅 DSL 的 program 维度参照，[VERIFIED] 活跃代码）：nep-fmk（金融市场）· nep-ban（银行）· nep-cba（央行）· nep-cfn（公司金融）· nep-ifn（国际金融）· nep-mst（微观结构）· nep-ecm（计量）· nep-cmp（计算经济）· nep-ain（AI）· nep-isf；
  ⚠ 勘误：`nep-fin` **2006-10 已停更**，勿作为活跃源引用（由 nep-fmk 等接续）。

## 4. NBER（`nber` adapter，T1；supported_since: phase-5）

- 编号：`w{n}`（历史 h/t 前缀已停用）[VERIFIED]；landing `nber.org/papers/w{n}`；
- **19 个官方 Program**；本项目相关 program 代码 [VERIFIED]：`AP`（Asset Pricing）· `CF`（Corporate Finance）· `EFG`（Fluctuations & Growth）· `IFM`（Intl Finance & Macro）· `ME`（Monetary）；⚠ PE 缩写存两义（Public/Political Economy）未核验，实现期以官网筛选器确认；
- **无官方 "AI" program**（Economics of AI 是 project/会议，非 program）[VERIFIED]；
- 增量：program RSS `back.nber.org/rss/new{code}.xml`（19 feed，[LIVE]）；
- 访问：>18 月完全开放；<18 月按策略配额——**不利用软门绕过**（D-014，AC-5.2）。

## 5. CEPR Discussion Papers（**仅元数据**，T2）

- [VERIFIED] 订阅/会员制：摘要页公开（`cepr.org/publications/dp{n}`），全文需机构 Site Authorisation / 个人订阅 / 单篇购买；
- **合规限制（D-014）**：robots 点名禁 ClaudeBot + `ai-train=no` → 本系统只经 RePEc 收书目，**不自动抓全文**；catalog 标 `fulltext: subscription_manual`（用户在自己订阅内手动获取）。

## 6. 其他平台（登记不排期，T3）

| 平台 | 定位 | 处理 |
|---|---|---|
| EconStor（ZBW） | 欧洲经济学 OA 知识库，30 万+ 全文免费 | Unpaywall/CORE 命中时自然利用；不单独 adapter |
| OSF Preprints | Center for Open Science 预印本聚合 | 暂缓 |
| Research Square | Springer Nature "In Review" 通道 | 暂缓 |
| ECCC | 理论计算机 WP（FOCS/STOC 作者常挂） | 暂缓；`grab --url` 人工单篇 |

## 7. 订阅预设与护栏（对齐 design/09）

- 预设包：`llm-agents`（arXiv cs.AI/LG/CL/MA）· `asset-pricing-wp`（SSRN FEN + q-fin.PR/PM/ST + NBER AP）· `econometrics-methods`（econ.EM + nep-ecm + stat.ME）· `market-microstructure`（q-fin.TR + FEN 微观结构 eJournal + nep-mst）· `mechanism-design`（cs.GT + econ.TH）· `optimization-ml`（math.OC + cs.LG）；
- 每订阅 `max_new_per_run` 熔断 + dry-run 预览是上线前规定动作（FR-16）；
- Google Scholar 不做自动化源（需求§5；用户自行配 Scholar Alerts 邮件互补）。
