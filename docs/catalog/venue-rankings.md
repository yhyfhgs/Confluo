---
title: 期刊会议评级体系
status: draft
owner: opus5.5-primary
updated: 2026-09-27
---

# 期刊会议评级体系

> 本文回答：有哪些期刊会议评级体系，各覆盖哪些学科、最新是哪一版、能不能在平台里用，[venue 名录](venues/README.md)里的评级标签各指什么。共收 45 个体系，核验日 2026-09-27。结论：CS 有 CCF 这样的完整名录，经管有 UTD24、FT50、ABDC、VHB、FMS，理工医靠中国科协分级目录与 Nature Index 拼合，中文刊用 CSSCI、CSCD、北大核心等；能不能内置由许可决定，订阅数据一律不做逐刊标注。

## 要点

- **计算机与 AI**：以 CCF 第七版（2026-03-31）为主，并列 ICORE2026、清华 THCPL、CAAI 2024 与 CSRankings 成员资格。
- **经管**：UTD24、FT50（2026-04-29 修订，2016 年后首次）、ABDC 2025、VHB-Rating 2024、FMS 2025，加上 Top5/Top3 两个约定名单。AJG 2024 须登录查看，不标；Tinbergen 已取消 AA/A/B 分级，不标。
- **理工医**：没有覆盖全学科的中文名录。中国科协分级目录（总汇第五版，2025-12，59 个领域）覆盖数学、地学、材料、医学、计算、管理等，但**没有物理、化学、心理、经济、金融、统计**的领域目录；Nature Index（当前 178 个刊会）是跨学科的开放参照。
- **中文刊**：CSSCI 2025–2026、CSCD 2025–2026、北大核心 2023、科技核心 2025、AMI 2022、卓越行动计划二期（2024）。
- **中科院分区表 2025 年版是最终版**：文献情报中心 2026-03-27 宣布停更。它和 JCR 都是订阅数据，不做逐刊标注。
- **许可决定用法**：公开的名单型、等级型数据内置为标签；ABDC、FT50、VHB 在许可确认前只接受用户导入；AJG、JCR、分区表只接受用户自带。本仓库里的逐刊标注只作内部设计参考。

## 标签词表

venue 名录的"评级"一列只用下表的标签，每个都在名录原文中核过。标签不带版本号，版本以本表为准。

| 标签 | 体系与版本 | 适用学科 | 平台用法 |
|---|---|---|---|
| `CCF-A`/`B`/`C` | CCF 推荐国际学术会议和期刊目录，第七版（2026） | CS | 内置 |
| `ICORE-A*`/`A`/`B`/`C` | ICORE2026 会议评级 | CS 会议 | 内置（只存等级事实，注明来源） |
| `THCPL-A`/`B` | 清华大学计算机学科推荐学术会议和期刊列表（2019） | CS | 内置 |
| `CAAI-A`/`B`/`C` | 中国人工智能学会推荐目录（2024） | AI | 内置 |
| `CSR` | CSRankings 会议集合成员 | CS 会议 | 内置（只标成员事实） |
| `CCF中文-A`/`B`/`C` | CCF 推荐中文科技期刊目录（2019） | 中文 CS 刊 | 内置 |
| `Top5`、`Top3` | 经济学五大刊、金融三大刊（学界约定） | 经济、金融 | 内置 |
| `UTD24` | UT Dallas 24 刊 | 商管、金融、会计 | 内置 |
| `FT50` | FT Research Rank 50 刊（2026 修订） | 商管、经济、金融、心理 | 许可确认前用户导入 |
| `ABDC-A*`/`A`/`B`/`C` | ABDC Journal Quality List 2025 | 商管、经济、金融、统计、心理 | 许可确认前用户导入 |
| `VHB-A+`/`A`/`B`/`C`/`D` | VHB-Rating 2024（分领域） | 商管 | 许可确认前用户导入 |
| `FMS-A`/`B`、`FMS-T1`/`T2` | FMS 管理科学高质量期刊推荐列表 2025（国际刊 A–D，中文刊 T1/T2；名录只显示 A、B、T1、T2） | 商管、经济、金融、心理 | 内置 |
| `NI` | Nature Index 当前名单 | 理科、健康、部分社科与 CS | 内置 |
| `T1`/`T2`/`T3`(学会) | 中国科协高质量科技期刊分级目录，按编制学会与年份 | 见下文科协表 | 内置 |
| `卓越-领军`/`梯队`/`新刊` | 中国科技期刊卓越行动计划二期（2024）；只在一期入选的写 `卓越-梯队(一期)` | 中国主办科技刊 | 内置 |
| `CSSCI`、`CSSCI扩展` | CSSCI 来源期刊 2025–2026（二手全表） | 中文社科 | 内置（注明二手） |
| `CSCD核心`、`CSCD扩展` | 中国科学引文数据库来源期刊 2025–2026 | 中国科技刊 | 内置 |
| `北大核心` | 中文核心期刊要目总览 2023 年版 | 中文刊 | 内置（只标事实） |
| `科技核心` | 中国科技核心期刊 2025 年版 | 中文科技刊 | 内置 |
| `AMI-顶级`/`权威`/`核心` | 中国人文社会科学期刊 AMI 综合评价 2022 | 中文社科 | 内置 |
| `NSFC管理-A`/`B` | 国家自然科学基金委管理科学部认定重要期刊（二手） | 中文管理与经济刊 | 内置（注明二手） |
| `惯例-顶级`/`惯例-一流` | 无正式名录的学界惯例，逐条附出处 | 数学、统计、金融会议等 | 内置 |

## 体系目录

### 计算机与 AI

| 体系 | 发布方 | 最新版本 | 分级与规模 | 获取与许可 |
|---|---|---|---|---|
| [CCF 推荐目录](https://www.ccf.org.cn/Academic_Evaluation/By_category/) | 中国计算机学会 | 第七版，2026-03-31（04-09 勘误） | 10 个领域 A/B/C，约 670 条，每条附 dblp 链接 | 公开 PDF，未声明许可；ccfddl 仓库转载（MIT） |
| [ICORE](https://www.core.edu.au/icore-portal) | CORE、GII、GRIN、SCIE | ICORE2026（具体日期 ⚠） | A*/A/B/C，825 个评级会议 | 门户与 CSV 导出，未见许可条款；门户 robots 对 Claude 类代理全站禁止，数据取自 ccfddl 与旧稿 |
| [THCPL](https://numbda.cs.tsinghua.edu.cn/~yuwj/TH-CPL.pdf) | 清华大学计算机学位评定分委员会 | 2019-08-13（未见更新版 ⚠） | A/B | 公开 PDF（二手托管） |
| [CAAI 推荐目录](https://www.caai.cn/site/content/4024.html) | 中国人工智能学会 | 2024-08-24 正式版 | 11 个领域 A/B/C，418 种（会议 158、国际刊 239、国内刊 21） | 公开 PDF |
| [CSRankings](https://github.com/emeryberger/CSrankings) | Emery Berger 等 | 滚动更新 | 27 个父领域、77 个会议键 | CC BY-NC-ND 4.0，只记成员事实，不导入数据文件 |
| [CCF 中文期刊目录](https://www.ccf.org.cn/c/2019-07-31/667609.shtml) | 中国计算机学会 | 2019-07-31 | A 7、B 11、C 19 | 公开 PDF；实际已由 2025 年的计算领域分级目录（T1 19、T2 22、T3 27）接替，两套都标 |

CCF 第七版相对 2022 年版的主要变化：ICLR 新入 A；IJCAI 由 A 降 B；HPDC 由 B 升 A；WINE 由 A 降 B；Interspeech、FMCAD、ISCAS 由 C 升 B；USENIX ATC 改名 ACM SIGOPS ATC，WWW 会议改名 The Web Conference。

### 经管（国际）

| 体系 | 发布方 | 最新版本 | 分级与规模 | 获取与许可 |
|---|---|---|---|---|
| Top5 / Top3 | 学界约定 | — | AER、ECMA、JPE、QJE、REStud；JF、JFE、RFS | 约定名单 |
| [UTD24](https://jsom.utdallas.edu/the-utd-top-100-business-school-research-rankings/list-of-journals) | UT Dallas Jindal School | 在线列表 | 24 刊：会计 3、金融 3、IS 3、营销 4、运营与管理科学 5、管理 6 | 公开网页，事实性名单 |
| [FT50](https://libguides.mcmaster.ca/ft-top50) | Financial Times | 2026-04-29 修订 | 50 刊；移出 Human Relations、JBE、Organization Studies，加入 AMAnn、ASR、Psychological Science | FT 原页不可达，经 McMaster 图书馆转载核对；FT 条款未取得 |
| [AJG](https://charteredabs.org/academic-journal-guide/) | Chartered ABS | AJG 2024；2027 版在编 | 4*/4/3/2/1 | 须登录查看，版权保留；未找到可访问的全表 |
| [ABDC JQL](https://abdc.edu.au/abdc-journal-quality-list/) | 澳大利亚商学院院长委员会 | 2025 复审（文件标 "Current to September 2026"） | A* 219、A 630、B 859、C 940，共 2,648 种 | 公开下载 xlsx，All Rights Reserved，再分发须许可 |
| [VHB-Rating](https://www.vhbonline.org/en/services/vhb-rating-2024) | 德国商业研究学会 | 2024-04-18 | 18 个领域各自 A+/A/B/C/D，不编总排名 | 公开 PDF，许可未核 |
| [FMS 列表](http://www.fms-journal.net/) | 中国优选法统筹法与经济数学研究会、管理科学与工程学会、中国系统工程学会 | 2025 版（两处出处分别记 2025-07-07 与 2025-10-29 发布 ⚠） | 国际刊 1,183 种（A 102、B 374、C 494、D 213）；中文刊 94 种（T1 28、T2 66） | 公开下载；它同时是科协总汇的管理科学领域目录 |
| [Tinbergen](https://tinbergen.nl/media/research/ti_fellowship_charter_feb2026_ti.pdf) | Tinbergen Institute | Fellowship Charter 2025–2028（2026-02） | 不再分级：按 JCR 五个类目中有 AIS 的全部期刊计分 | 依赖 Clarivate 订阅数据，不用 |
| [RePEc 排名](https://ideas.repec.org/top/) | RePEc | 月度滚动 | 期刊与 WP 系列的影响因子、排名 | 公开；只作可选质量信号，不作标签 |
| CNRS / HCERES | CNRS 第 37 节、HCERES | HCERES 2021-07-09（已停更） | 1*/1/2/3/4；A/B/C，937 种 | 不用 |

### 中文体系

| 体系 | 发布方 | 最新版本 | 规模 | 获取与许可 |
|---|---|---|---|---|
| [CSSCI](https://cssrac.nju.edu.cn/) | 南京大学中国社会科学研究评价中心 | 2025–2026（2025-10 发证书） | 来源 660、扩展 249（二手全表） | 官方不公开全表；逐刊依据图书馆转载，须标"二手" |
| [CSCD](http://sciencechina.cn/select) | 中国科学院文献情报中心 | 2025–2026 | 1,504 种：核心 1,120、扩展 384（网传 1,464 与转载 PDF 不一致，以 PDF 为准） | 图书馆转载 PDF |
| [北大核心](http://hxqk.lib.pku.edu.cn/) | 北京大学图书馆 | 2023 年版（第 10 版，2024-03 出版） | 1,987 种 | 纸本书，转载标"切勿商用"；只标事实 |
| [科技核心](https://www.istic.ac.cn/ueditor/jsp/upload/file/20251029/1761720843494043699.pdf) | 中国科学技术信息研究所 | 2025 年版（2025-10-30） | 2,745 种（学术卷 2,693、科普卷 52） | 官方 PDF |
| [卓越行动计划](https://www.cast.org.cn/xw/tzgg/KJCX/art/2024/art_81a8a2cc3e7846c98a3b668721f68082.html) | 中国科协等七部委 | 二期 2024-11-28；一期 2019 | 二期：英文领军 50、英文梯队 150、中文领军 100、中文梯队 100、高起点新刊 50、集群 13 | 官方文件 |
| [AMI](https://journals.xmu.edu.cn/2022nianzhongguorenwenshehuikexueqikanpingjiajieguogongshiban-20230112.pdf) | 中国社会科学评价研究院 | 2022 年版（2023-03-17） | 老牌刊 1,924 种：顶级 22、权威 55、核心 605 | 公开报告 |
| NSFC 管理科学部重要期刊 | 国家自然科学基金委管理科学部 | 年份不详，官方原件未找到 | 30 种：A 22、B 8 | 只有高校转载，须标"二手" |

### 中国科协分级目录（按学科）

总汇第五版于 2025-12-12 发布，收 59 个领域目录，由各全国学会编制（[公告](https://www.cast.org.cn/xw/gzdt/KJCX/art/2025/art_7affb3ed494c436b9a69aedb8604e400.html)）。与我们学科组对应的目录：

| 学科组 | 科协领域（种数） | 编制学会 | 版本 |
|---|---|---|---|
| 数学 | 数学（449） | 中国数学会 | 2024 |
| 物理与天文 | 光学工程和光学（88）、声学（201）、核（112） | 中国光学工程学会、中国声学学会、中国核学会 | 2022、2024、2024 |
| 化学 | 化工（93） | 中国化工学会 | 2024 |
| 地学 | 地球科学（642）、地理资源（368）、地球物理（175）、遥感（140）、岩土（129）、土壤（175） | 中国地质学会、中国地理学会、中国地球物理学会等 | 2022–2025 |
| 材料 | 材料-综合（410）、无机非金属（97）、冶金与金属材料（158）、有色金属（232）、材料失效与保护（102） | 中国材料研究学会、中国硅酸盐学会、中国金属学会等 | 2021–2025 |
| 生命科学与医学 | 临床医学（1,160）、预防医学（172）、药学（225）、细胞生物学（45）、植物科学（142）、生态学（187）、生物医学工程（72） | 中华医学会等 | 2023–2025 |
| 计算机与 AI | 计算（68）、自动化（321，分 A+/A/B）、图像图形（195）、电子（418）、通信（93）、仿真（96） | 中国计算机学会等 | 2023–2025 |
| 商业与管理、经济 | 管理科学（1,277，即 FMS）、技术经济（174） | FMS 三学会、中国技术经济学会 | 2025、2023 |

**缺口**：没有物理学（综合）、化学（综合）、心理学、经济学（综合）、金融、统计的领域目录，中国物理学会、化学会、心理学会也没有公开单独名单（⚠ 只据第五版目录页判断）。所以物理刊的 T 标签只来自核与光学目录，化学刊的 T 标签来自材料、环境、化工等相邻目录，心理刊的 T 标签来自中华医学会"精神病学"子目录——标签括号里的学会名说明它出自哪份目录。

### 通用指标与国家名录

| 体系 | 发布方 | 最新版本 | 用法 |
|---|---|---|---|
| [Nature Index](https://www.nature.com/nature-index/faq) | Springer Nature | 当前 12 个月窗口，178 个刊会（含部分社科刊与 IROS） | 内置 `NI`；名单每年调整，按年复读 |
| [JCR](https://clarivate.com/news/clarivate-releases-journal-citation-reports-2026/) | Clarivate | JCR 2026（2026-06-17），22,643 刊、254 类 | 订阅，不用；用户可自带 |
| [中科院分区表](https://las.cas.cn/news/tzgg/202603/t20260327_8178738.html) | 中国科学院文献情报中心 | 2025 年版（2025-03-20）为最终版，2026-03-27 宣布停更 | 订阅，不用；用户可自带 |
| SCImago SJR | SCImago Lab | 未核（站点有 Cloudflare 挑战，未访问） | 不用 |
| [CiteScore](https://www.elsevier.com/products/scopus/metrics/citescore) | Elsevier | CiteScore 2025（2026-06-03，二手） | 不用 |
| [Google Scholar Metrics](https://scholar.googleblog.com/2025/07/2025-scholar-metrics-released.html) | Google | 2025 版（2025-07）；截至 2026-09-27 未见 2026 版 ⚠ | 条款禁止抓取，只作外链 |
| 挪威 Kanalregisteret、芬兰 JUFO | HK-dir、Federation of Finnish Learned Societies | 2026 级别；JUFO 自 2027 年起取消 3 级 | 许可未核，暂作参考 |
| 巴西 Qualis、澳大利亚 ERA 2010 | CAPES、ARC | Qualis 2021–2024 为最后一版刊级分级；ERA 2010 已停 | 不用 |

### 风险名单

| 名单 | 现状 | 用法 |
|---|---|---|
| 中科院国际期刊预警名单 | 2025 版（二手）；2026 版未见 ⚠ | 只作风险提示，不作评级 |
| Cabell's Predatory Reports | 订阅 | 不用 |
| Beall's List | 2017 年冻结 | 不用 |

## 近似对照

**近似，仅供参考，不能换算或合并打分**：各体系的依据与覆盖面不同，例如 ABDC A* 有 219 种，AJG 4* 通常只有几十种；北大核心、科技核心是"入选即核心"的宽口径名单。

| 大致层次 | CS 国际 | CS 中文 | 经管国际 | 经管中文 | 理工中文与中国主办刊 |
|---|---|---|---|---|---|
| 顶级 | CCF-A ≈ ICORE-A* ≈ THCPL-A ≈ CAAI-A | CCF中文-A ≈ T1(中国计算机学会) | Top5/Top3 ⊂ UTD24 ⊂ FT50；≈ AJG-4* ≈ ABDC-A* ≈ VHB-A+ ≈ FMS-A | NSFC管理-A ≈ FMS-T1 ≈ AMI-顶级/权威 | 卓越-领军 ≈ T1 |
| 较高 | CCF-B ≈ ICORE-A ≈ THCPL-B ≈ CAAI-B | CCF中文-B ≈ T2 | AJG-4/3 ≈ ABDC-A ≈ VHB-A/B ≈ FMS-B | NSFC管理-B ≈ FMS-T2 ≈ AMI-核心 ≈ CSSCI | 卓越-梯队 ≈ T2 ≈ CSCD核心 |
| 一般 | CCF-C ≈ ICORE-B ≈ CAAI-C | CCF中文-C ≈ T3 | AJG-2 ≈ ABDC-B ≈ VHB-C | CSSCI扩展 ≈ 北大核心 | T3 ≈ CSCD扩展 ≈ 北大核心 ≈ 科技核心 |

## 平台怎么用

- **数据模型**：评级是 venue 的属性，按旧稿（03、05）设计落为 `venue_list(list_id, version, venue_id, rating, field_code, source_url, license_scope)`，`license_scope` 取 `public_builtin` 或 `user_private`；用户自带的名单进 `usr.private_venue_list`，只在本人私域使用。
- **内置**（公共 venue 库可显示，只存"等级事实 + 出处 + 版本"）：CCF、CCF中文、ICORE、THCPL、CAAI、CSR、Top5、Top3、UTD24、NI、科协 T 级、卓越、FMS、CSSCI、CSCD、北大核心、科技核心、AMI、NSFC 管理、惯例。
- **许可确认前只作用户导入**：FT50、ABDC、VHB。前端可以显示用户自己导入的等级，但平台不提供整表导出。
- **只接受用户自带**：AJG、JCR、中科院分区表、CiteScore、SJR。
- **不用**：Tinbergen 分级（已取消）、ERA 2010、CNRS/HCERES、Qualis、Beall、Google Scholar Metrics（只外链）；挪威与芬兰名录暂作参考。
- **风险提示**：预警名单只作风险标记。
- **在推荐里的角色**（待你确认）：建议评级只用于展示、过滤与频道条件，不进默认排序，避免把名录偏好放大成推荐偏见。
- **本仓库的逐刊标注**只作内部设计参考；产品内置按上面的许可结论执行。

## 怎么维护

- **复读节奏**：CCF 约 3–4 年一版；ABDC 三年复审；AJG 2027 版在编；FMS 约三年一版；CSSCI、CSCD 两年一版；北大核心三年一版；科技核心与科协总汇每年；Nature Index 滚动，按年复读。
- **版本**：数据里每个标签带版本（如 CCF 第七版），名录展示时不带；换版时整表替换，保留旧版以便追溯。
- **单一事实来源**：实现期落为 `registry/venue_lists/<list_id>.yaml`，venue 名录的评级列由生成器产出。
- **新增体系**：先在本文登记发布方、版本、许可与用法，再加标签。

## 未决与缺口

- **许可**：ICORE、FT50、ABDC、VHB 的再分发许可，CSRankings 的 NC-ND 边界，均待书面确认。
- **版本未核**：ICORE2026 的发布日期；THCPL 有无 2019 年后的版本；AJG 2024 各级数量；FMS 2025 的发布日期；SJR 与 GS Metrics 2026 的状态；2026 版预警名单。
- **二手依据**：CSSCI 全表、NSFC 管理 30 刊、FT50 名单都来自转载；科协总汇 PDF 部分取自高校转载件，未与官方附件逐字比对。
- **学科空白**：物理、化学、心理、经济、金融、统计没有科协领域目录；经济学会议与心理学会议没有可引用的分档出处。

---

逐刊标注见 [venue 名录](venues/README.md)，来源七类分层见[来源分层](source-taxonomy.md)。
