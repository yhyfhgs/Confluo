---
title: 站点勘察：CS/AI 顶会获取渠道（原始调研）
status: approved
owner: fable5
updated: 2026-07-20
---

# 站点勘察 · CS/AI 顶会

> 来源：subagent 实测（WebSearch/WebFetch 验证），2026-07-20。设计结论提炼至 [catalog/cs-ai-conferences.md](../../catalog/cs-ai-conferences.md) 与各 adapter 文档。

## ⚡ 两个重大政策事实（影响架构归类）

1. **ACM 自 2026-01-01 起全面开放获取**（官方公告 acm.org/articles/bulletins/2026/january/acm-open-access）：dl.acm.org 全部会议论文集（KDD、WWW、WSDM、CIKM、SIGIR、RecSys、STOC、SOSP、EC、SIGMOD/PACMMOD）免费全文。→ `acm_dl` adapter 归 open_access 族（保留 auth 能力做历史兜底）。已记 ADR D-013。
2. **Papers With Code 已于 2025-07 被 Meta 关闭**，域名重定向 Hugging Face Papers；历史数据存档于 github.com/paperswithcode/paperswithcode-data（不再更新）。→ 不作为索引源。

## 分渠道要点速记

### PMLR（proceedings.mlr.press）
- 卷号↔年份映射（实测）：ICML 2021→v139、2022→v162、2023→v202、2024→v235、2025→v267；AISTATS 2023→v206、2024→v238、2025→v258；COLT 2024→v247、2025→v291、2026→v336；UAI 2024→v244、2025→v286（2020 起才入 PMLR，此前 AUAI Press）；CoRL 2017→v78、2018→v87、2023→v229、2024→v270、2025→v305。
- 每卷 index 页含全部 BibTeX；无 API 但结构极规整。
- 历史边界：ICML 系统性收录约 2013(v28) 起，更早分散 Morgan Kaufmann/ACM；AISTATS 部分早年回溯补录，2007–2016 有些卷在旧域 jmlr.org/proceedings。

### OpenReview（ICLR 等）
- venue id `ICLR.cc/{year}/Conference`；API2 `api2.openreview.net`（2023+），更早届走 API1 `api.openreview.net`——需版本探测双端点路由。
- ICLR 2013 创立即用 OpenReview，历史连贯性最好；早期 venue id 格式有不一致，需兼容。
- `openreview-py` 官方客户端，`get_all_notes()` 按 Submission invitation 批量拉取再按 decision 过滤。

### NeurIPS proceedings
- `proceedings.neurips.cc/paper_files/paper/{year}`；单篇 `.../hash/{hash}-Abstract-Conference.html`、PDF `.../file/{hash}-Paper-Conference.pdf`；旧域 papers.nips.cc 并存内容一致；**1987 年起全量在线**。宣传站 nips.cc/neurips.cc 年年变，proceedings 域稳定。

### CVF Open Access（openaccess.thecvf.com）
- CVPR/ICCV/WACV：`/{CONF}{year}` 目录；单篇 `/content/CVPR{year}/html/{Author}_{Title}_CVPR_{year}_paper.html` + `/papers/` PDF。
- **收录起点：2013**（更早只在 IEEE Xplore 订阅）。WACV 系统收录约 2020 起。
- ECCV 特殊：正式版 Springer LNCS；CVF 镜像旧格式 `content_ECCV_{year}`，新格式未证实（实测 ECCV2024 路径 403）⚠ 待实现期核实。

### ACL Anthology（aclanthology.org）
- venue 页 `/venues/{acl,emnlp,naacl,coling,eacl}/`；ID 新式 `2023.acl-long.1`（2020+），旧式 `P19-1001`（P/N/D/E/C 前缀）；卷首=`.0`。
- **bulk：github.com/acl-org/acl-anthology 全量 XML/YAML 元数据可克隆**——首选通道。
- COLING 主办方是 ICCL（非 ACL 学会）但同样收录；NAACL/EACL 非每年举办。

### AAAI OJS（ojs.aaai.org）
- `/index.php/AAAI/issue/archive` **默认只显示最新一届**——历史届需翻页参数或按卷直达 ⚠。1980、1982–2026 覆盖（个别年份存疑）。OJS 平台理论上有标准 OAI-PMH（未逐一验证）。宣传站 aaai-{yy}.aaai.org 年年变。

### IJCAI（ijcai.org）
- `/proceedings/{year}/` + `/all_proceedings` 汇总页；**主域长期稳定**；2017 起自出版完全 OA，此前部分年份 AAAI Press/Morgan Kaufmann。1969 首届，1970s 起在线，更早 Internet Archive 补。

### ACM DL（dl.acm.org）——2026 起全面 OA
- 整卷 `doi/proceedings/10.1145/{id}`、单篇 `doi/10.1145/{a}.{b}`；聚合页 `/conference/{kdd,...}/proceedings`。
- KDD 2024 起一年两卷（V.1/V.2，双截止）；SIGMOD 2023 起转 **PACMMOD** 期刊滚动出版（`/journal/pacmmod/sigmod`）——新旧两套入口都要查。
- WWW/TheWebConf：域名年年变（www{year}.thewebconf.org）；**历届最稳定入口 archives.iw3c2.org**；2022 起完全归 ACM/SIGWEB。EC 2014 前名为 ACM Conference on Electronic Commerce——检索需双名。

### IEEE Xplore（订阅制，无 OA 新政）
- `ieeexplore.ieee.org/xpl/conhome/{conhomeID}/proceeding`；**conhome ID 逐年随机不可推导**（如 ICDM 2023=10415628），需经 `all-proceedings` 聚合页或搜索定位——定位成本最高的体系。
- 覆盖：ICDM、FOCS、ICASSP、ICRA、IROS（+CVPR/ICCV 的 IEEE 版）。ICRA/IROS 有 RA-L 双轨（期刊文另算）⚠ 检索时区分。有官方元数据 API（非全文）。

### SIAM（epubs.siam.org）—— SODA 在此，非 ACM DL！
- 整卷 `doi/book/10.1137/1.{isbn}`、单篇 `.../1.{isbn}.ch{N}`；**订阅制**，不受 ACM OA 新政覆盖。1990 创立，早年个别届曾在 ACM 体系。

### 其他独立体系
- **LIPIcs/Dagstuhl**（drops.dagstuhl.de）：ITCS 2017+ 完全 OA，DOI `10.4230/LIPIcs.ITCS.{year}.{n}`；ITCS 2012–2016 在 ACM DL、2010–2011 自建站——三段史。
- **Springer LNCS**：ECCV 正式版、WINE（2005+，订阅）；WINE 域名年年变（DBLP 定位）。
- **ISCA Archive**（isca-speech.org / isca-archive.org）：INTERSPEECH 及前身 EUROSPEECH/ICSLP 全量 OA；`/archive/interspeech_{year}/...`。
- **roboticsproceedings.org**：RSS 会议，`/rss{NN}/`（rss01–rss21 ↔ 2005–2025）完全 OA，极规整。
- **USENIX**（usenix.org）：OSDI `/conference/osdi{yy}/technical-sessions`，全量 OA（论文+slides+视频）；ACM DL 上的 10.5555 条目仅是索引非全文。
- **PVLDB**（vldb.org/pvldb/volumes/{vol}/）：2008 起期刊化完全 OA（CC BY-NC-ND）；此前老卷需 DBLP/馆藏。

### DBLP（导航层）
- `dblp.org/db/conf/{acronym}/`（nips/icml/iclr/acl/kdd/bmvc/corl/sosp/wine…）每届列表+官方渠道外链；搜索 API `dblp.org/search/publ/api?q=..&format=json`；作者 API `/pid/{pid}.{fmt}`；**全量 XML dump（CC0）**。只有元数据无摘要全文——作为 VenueEra 历史主干与"官网年年变"会议的定位层（D-012 的支撑证据）。

### Semantic Scholar
- 2 亿+ 论文；API `api.semanticscholar.org` 免 key 可用（~100 req/5min），key 提额；venue 字段规范化弱于 DBLP（NeurIPS 写法混用）→ 批量分析需归一化。Datasets API 月度快照含 S2ORC。

## 域名稳定性分级（供 VenueEra 策略参考）

- **稳定单域**：ijcai.org、vldb.org、usenix.org、roboticsproceedings.org、aclanthology.org、proceedings.neurips.cc、proceedings.mlr.press、openaccess.thecvf.com、drops.dagstuhl.de、isca-archive.org
- **宣传站年变但 proceedings 稳定**：NeurIPS、ICML、ICLR、CVPR/ICCV、AAAI、ACL 系
- **年年换域高危（必须 DBLP/归档站导航）**：WWW（archives.iw3c2.org）、BMVC（bmvc{year}.org→bmvc{year}.bmva.org→bmva-archive.org.uk 三段史）、WINE
