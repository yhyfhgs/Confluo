---
title: 候选来源
status: draft
owner: opus5.5-primary
updated: 2026-09-27
---

# 候选来源

> 本文列出 2026-09-27 这轮调研找到、但还没进入[支持名录](source-directory.md)的来源，按[七类分层](source-taxonomy.md)分节，共 156 个：M1 29（其中 24 个是国家与公共机构节点）、M2 21、L1b 1、L1c 48、L2a 28、L2b 29。它是名录维护流程里"调研短文"的索引。"建议"一列只是调研结论，不是承诺；进名录前须补齐证据、提交注册表条目并复核。

## 要点

- **最值得先补的**（有官方机读通道、补的是明显缺口）：Copernicus（EGU 全部 OA 刊，OAI-PMH 已核，建议 P1）、FEDS Notes（建议 P1）、NASA NTRS、NIST 与 USGS 报告、World Bank OKR、theses.fr、大学机构库 ETD（OAI 实例族，零代码）、IETF RFC、ccfddl。
- **L1c 从零起步**：企业技术报告多数已被 arXiv 覆盖，只在官网发布的 OpenAI、Anthropic system card 与百度 ERNIE 4.5 报告须单独作 L1c；大学技术报告系列（MIT、Berkeley、CMU、Cambridge）仍在更新；JMP 没有合规、可机读的聚合通道，默认用户导入。
- **M2 事实**：CNKI 是 DOI Foundation 正式列出的注册机构；中文 DOI 由 ISTIC 与万方合办；ISSN-L 对照表须先签许可；Crossref 自 2026-09-15 起把资助方名称匹配到 ROR；中国没有公开的全国性研究者标识。
- **国家机构只作关系图节点**，接入走它们运营的来源。
- **AI 检索与引文图谱工具全部"不接，仅作竞品参照"**：Elicit、Consensus、scite、Undermind 虽有 API，但绑定付费订阅或须另签商业许可。
- **已关停或下线**：CiteSeerX（根域跳到 Wayback 快照）、DART-Europe（2025-02-03 关停）、NDLTD Global ETD Search（下线重建）。OATD、CBO、RAND、IMF 站点遇挑战页或拒绝访问，只走 Crossref 或外链。

链接指向调研时读到的证据页；核验日 2026-09-27，取自旧稿的事实沿用其核验日 2026-09-26。标 ⚠ 的是未读到一手条款或文档的项。

## M1 出版与托管主体

### 国家与公共机构（24 个节点）

机构本身不单独接入，只在关系图里作 M1-nat 节点，下挂它运营的来源。带 `source_id` 的是名录已有行，其余是本文的新候选。

| 机构 | 运营的来源 | 主要学科 |
|---|---|---|
| NLM/NCBI（美国） | `pubmed`、`pmc`、`pubtator3`、`pubchem` | 生命科学与医学、心理 |
| NIH（美国） | `icite`；公共获取政策把成果送进 `pmc` | 生命科学与医学 |
| NSF（美国） | NSF-PAR 公共获取库（候选） | 跨学科 |
| DOE OSTI（美国） | `osti_gov`（兼 L1c 技术报告首发） | 物理、化学、材料 |
| NASA（美国） | `nasa_ads_scix`（SAO 运营）、NTRS（候选） | 物理与天文、地学 |
| EMBL-EBI（欧洲） | `europe_pmc` | 生命科学与医学 |
| CERN（欧洲） | `inspire_hep`（多机构合办）、`scoap3_repo`、`zenodo` | 物理与天文、跨学科 |
| CNRS/CCSD（法国） | `hal`、`episciences` | 数学、物理、CS |
| TIB（德国） | ConfIDent、ORKG（候选） | CS、跨学科 |
| ZBW（德国） | `econbiz`、`econstor` | 经济、金融、管理 |
| ZPID（德国） | `psycharchives`、PubPsych（候选） | 心理 |
| FIZ Karlsruhe（德国） | `zbmath_open` | 数学 |
| JST（日本） | `jstage`；J-GLOBAL、researchmap（候选）；与 NIMS、NII、NDL 共同运营 JaLC | 跨学科 |
| NII（日本） | `cinii_research`；IRDB、KAKEN（候选）；共同运营 JaLC | 跨学科 |
| KISTI（韩国） | ScienceON、KISTI DOI（候选） | 跨学科 |
| NRF（韩国） | KCI（候选） | 跨学科 |
| 中国科学院 | 文献情报中心：`chinaxiv`、CSCD（评级名录）、期刊分区表（订阅，已停更）；计算机网络信息中心：CSTR；中国科学杂志社：`sciengine`；上海有机所：期刊平台（候选） | 跨学科 |
| ISTIC（科技部） | 中文 DOI（与万方合办）、科技核心（评级名录）；合作企业 `wanfang` | 跨学科 |
| NSTL | 文献检索平台、学位论文（候选） | 跨学科 |
| 中国社会科学院 | NCPSSD（候选）；AMI 评价（中国社会科学评价研究院） | 经济、管理 |
| 中国科协 | 科协分级目录、卓越行动计划（评级名录） | 跨学科 |
| 教育部科技发展中心 | `paper_edu_cn` | 跨学科 |
| FAPESP（巴西） | `scielo` | 跨学科 |
| UAEM（墨西哥） | `redalyc` | 跨学科 |

同方知网是企业，不属 M1-nat：它运营 `cnki`、中国引文数据库与 CNKI DOI 注册机构。

### 托管平台（5）

| 候选 | 运营方 | 学科 | 通道与条款 | 建议 | 备注 |
|---|---|---|---|---|---|
| [African Journals Online（AJOL）](https://en.wikipedia.org/wiki/African_Journals_OnLine) `ajol` | AJOL（南非非营利组织 ⚠） | 跨学科综合、生命科学与医学 | Crossref（期刊自有 DOI ⚠）；OAI-PMH ⚠未核；混合 OA | 建议仅元数据 | 重判：托管平台，非 L2a；规模为二手 |
| [Copernicus Publications（EGU 期刊平台）](http://oai-pmh.copernicus.org/oai.php?verb=Identify) `copernicus` | Copernicus GmbH（EGU 合作） | 地学 | OAI-PMH http://oai-pmh.copernicus.org/oai.php（set: egu，dc:source 带 eI…；全 OA（CC BY）；robots 只禁 /js_for_profiles.js | 建议P1 | ACP、HESS、TC、GMD、BG、ESSD 等 |
| [美国气象学会 AMS 期刊平台](https://journals.ametsoc.org/) `ametsoc` | American Meteorological Soc… | 地学 | Crossref:ISSN（站点返回 403，不直连）；订阅为主 | 建议仅元数据 | J Climate、BAMS、JPO；与数学的 ams 同名，另起 id |
| [清华大学出版社 SciOpen](https://www.sciopen.com/) `sciopen` | 清华大学出版社 | 材料、跨学科综合 | Crossref:ISSN；站点待勘察；待核 | 待勘察 | Nano Research 等中国主办英文刊 |
| [上海有机化学研究所期刊平台](https://sioc-journal.cn/) `sioc_journals` | 中国科学院上海有机化学研究所 | 化学 | Crossref:ISSN（部分）；站点待勘察；待核 | 待勘察 | 化学学报、有机化学 |

## M2 标识与注册（21）

名录已有的 6 行 M2（`crossref`、`datacite`、`orcid`、`ror`、`wikidata`、`open_policy_finder`）本轮只复核角色，结论见文末。

| 候选 | 运营方 | 学科 | 通道与条款 | 建议 | 备注 |
|---|---|---|---|---|---|
| [DOI Foundation（DOI 注册机构体系）](https://www.doi.org/the-community/existing-registration-agencies/) `doi_foundation` | DOI Foundation | 跨学科综合 | doi.org 解析；Handle 协议；站点 CC BY 4.0 | 建议仅元数据（解析与 RA 判别） | 用 doi.org/ra/{prefix} 判 RA ⚠未测 |
| [mEDRA](https://www.doi.org/the-community/existing-registration-agencies/) `medra` | mEDRA（意大利 AIE 发起 ⚠） | 跨学科综合 | DOI 解析；mEDRA 元数据接口 ⚠未核；⚠ | 建议仅元数据（解析时识别 RA） |  |
| [Japan Link Center（JaLC）](https://japanlinkcenter.org/top/doc/REST_API_Functional_Description.pdf) `jalc` | JST、NIMS、NII、NDL 共运营 | 跨学科综合 | JaLC REST API（2021-12-22 发布：前缀、DOI 列表、元数据）与元数据批量下载 JSON；许可 ⚠ 未读到明确 CC0 | 建议P2（日本刊 DOI 元数据补充） | 补 Crossref 看不到的 JaLC DOI |
| [Korean DOI Center（KISTI）](https://www.doi.org/the-community/existing-registration-agencies/) `kisti_doi` | KISTI | 跨学科综合 | ⚠ 未核；⚠ | 待勘察 | URL 为公知 ⚠ |
| [中文 DOI（Chinese DOI）](https://www.doi.org/the-community/existing-registration-agencies/) `chinese_doi` | ISTIC 与万方数据合办 | 跨学科综合 | ⚠ 未核（无公开元数据 API 证据）；⚠ | 待勘察（中文刊 DOI 解析；元数据可能只能经万方） |  |
| [CNKI DOI 注册机构](https://www.doi.org/the-community/existing-registration-agencies/) `cnki_doi` | 中国知网 CNKI | 跨学科综合 | ⚠ 未核；⚠ | 待勘察（只作 DOI 解析与 RA 识别） | 已核：CNKI 是 RA |
| [Airiti DOI](https://www.doi.org/the-community/existing-registration-agencies/) `airiti_doi` | 华艺数位 Airiti（台湾） | 跨学科综合 | DOI Data Finder ⚠ 条款未核；⚠ | 待勘察 |  |
| [欧盟出版办公室 OP（DOI RA）](https://www.doi.org/the-community/existing-registration-agencies/) `eu_op_doi` | Publications Office of the … | 经济、跨学科综合 | ⚠ 未核；EU 再利用政策 ⚠ | 建议仅元数据 |  |
| [ISNI](https://isni.org/) `isni` | ISNI International Agency | 跨学科综合 | SRU/链接数据 ⚠ 未核；⚠ | 建议仅元数据（作者/机构交叉 ID） | 条款本次未读 ⚠；作为 Wikidata 交叉 ID 使用即可 |
| [ISSN 国际中心（ISSN Portal、ISSN-L 表）](https://www.issn.org/services/online-services/access-to-issn-l-table/) `issn_ic` | CIEPS / ISSN International … | 跨学科综合 | ISSN Portal 免费基础元数据与链接数据；ISSN-L 表按需申请；许可合同：未经授权不得再公开 ISSN 数据 | 建议仅元数据（ISSN-L 表须先签许可；Venue 主键靠 Crossref  | ROAD 为其 OA 子目录 |
| 国际 ISBN 中心 `isbn_ia` | International ISBN Agency | 跨学科综合 | 无开放书目数据 ⚠；⚠ | 不接（仅作书与论文集的属性字段） | 本次未访问 ⚠ |
| [ConfIDent（TIB 会议标识）](https://datacite.org/blog/confident-about-pids-using-datacite-dois-for-conferences/) `confident` | TIB 与 ZB MED ⚠ | 计算机与AI、跨学科综合 | Semantic MediaWiki；DataCite API；⚠ 未读到许可 | 待勘察（会议 Venue/Edition 的外部 ID 候选） |  |
| [RAiD 研究活动标识](https://ardc.edu.au/services/ardc-identifier-services/raid-research-activity-identifier-service/) `raid` | ARDC（全球注册管理机构）、SURF（欧洲 RA） | 跨学科综合 | RA 的 API（铸造/解析）；元数据方案开放 ⚠ | 不接（v2 暂无项目实体） |  |
| Handle System `handle_net` | CNRI / DONA Foundation | 跨学科综合 | hdl.handle.net 解析；— | 不接（仅作 URL 规范化规则） | 本次未访问 ⚠ |
| ARK 标识 `ark` | ARK Alliance；N2T 解析 | 跨学科综合 | n2t.net 解析；— | 不接（仅作 URL 规范化规则） | 本次未访问 ⚠ |
| [CSTR 科技资源标识](https://www.cstr.cn/phone/search/intro) `cstr` | 中科院计算机网络信息中心研发；标准 GB/T 3284… | 跨学科综合 | CSTR 服务平台解析；元数据接口 ⚠；⚠ | 待勘察（中文预印本/数据的次要 ID） |  |
| [researchmap 与 KAKEN 研究者号（日本）](https://support.nii.ac.jp/en/kaken/api/api_outline) `researchmap_kaken` | JST（researchmap）；NII（KAKEN） | 跨学科综合 | researchmap v2 API（需 JST 发放 client ID）；KAKEN OpenSearch（需 CiNii appid）；按各自 API 条款 | 不接（日本作者消歧时再评估） |  |
| [Lattes ID（巴西）](https://www.gov.br/pt-br/servicos/obter-acesso-ao-extrator-da-plataforma-lattes) `lattes` | CNPq（巴西） | 跨学科综合 | 定期公布全部 ID 列表；批量简历须机构经 Extrator Lattes 申请（需 CNPq VPN）；机构协议 | 不接 |  |
| 中国全国性公开研究者标识 | — | 跨学科综合 |  | 不接（缺口） | ⚠ 未专门检索；CSTR 不覆盖人 |
| OpenDOAR（OA 仓储名录） `opendoar` | Jisc | 跨学科综合 | ⚠ API 与许可未核（WAF 403）；⚠ | 待勘察（枚举机构仓储端点） |  |
| L2 内部标识汇总（PMID/PMCID、arXiv ID、RePEc handle、DBLP key、INSPIRE ID、MR/zbMATH 作者号、OpenAlex ID、Scopus Author ID、ResearcherID） | 各自归属 pubmed/pmc、arxiv、repec… | 跨学科综合 | 随对应来源获取；随对应来源 | 不单列来源（作 Work/作者的外部 ID 字段） | 映射优先经 Wikidata/OpenAlex |

## L1b 预印本与工作论文（1）

| 候选 | 运营方 | 学科 | 通道与条款 | 建议 | 备注 |
|---|---|---|---|---|---|
| [EGUsphere](https://egusphere.copernicus.org/) `egusphere` | Copernicus（EGU） | 地学 | 随 copernicus（OAI-PMH 待核是否含讨论稿）；CC BY | 建议P2 | EGU 期刊的公开讨论稿阶段 |

## L1c 长尾一级产出（48）

学位论文按"首发在哪"分两处：单篇论文首发在大学机构库，归本节；汇总各校论文的国家学位论文库归 L2a。

### 企业研究院技术报告（17）

| 候选 | 运营方 | 学科 | 通道与条款 | 建议 | 备注 |
|---|---|---|---|---|---|
| [Google Research Publications](https://research.google/robots.txt) `google_research_pubs` | Google | 计算机与AI | sitemap（/sitemap.xml）；博客 RSS /blog/rss/；robots 允许 /pubs/；条款未逐条核 ⚠ | 建议P2 | 论文按 arXiv/DOI 归并，仅存外链 |
| [Google DeepMind Research](https://deepmind.google/robots.txt) `deepmind_pubs` | Google DeepMind | 计算机与AI、生命科学与医学 | sitemap；博客 RSS /blog/rss.xml；robots 允许；条款 ⚠ | 建议P2 | Nature/Science 论文走 L1a |
| [Microsoft Research Publications](https://www.microsoft.com/en-us/research/feed/) `msr_pubs` | Microsoft | 计算机与AI | RSS /en-us/research/feed/；sitemap；robots 允许 /en-us/research/publication/；条款 ⚠ | 建议P2 | MSR-TR 编号系列需单独确认是否仍在发 ⚠ |
| [Meta AI (FAIR) Publications](https://ai.meta.com/robots.txt) `meta_fair_pubs` | Meta | 计算机与AI | sitemap（.xml.gz）；未见 RSS；robots 允许 /research/publications/；条款 ⚠ | 建议仅元数据 |  |
| [OpenAI Research 与 System Cards](https://openai.com/news/rss.xml) `openai_research` | OpenAI | 计算机与AI | RSS /news/rss.xml；sitemap；robots 允许 /research/；条款 ⚠ | 建议P2 | 需单独 L1c，arXiv 不覆盖 |
| [Anthropic Research 与 System Cards](https://www.anthropic.com/research) `anthropic_research` | Anthropic | 计算机与AI | sitemap（/sitemap.xml）；未见 RSS；robots 允许 /research；条款 ⚠ | 建议P2 | 需单独 L1c，arXiv 不覆盖 |
| [NVIDIA Research Publications](https://research.nvidia.com/robots.txt) `nvidia_research` | NVIDIA | 计算机与AI | sitemap + labs-sitemap；robots 允许；Content-Signal: ai-train=yes, search=ye… | 建议仅元数据 | 显式内容信号，可作 08 用例 |
| [IBM Research Publications](https://research.ibm.com/robots.txt) `ibm_research_pubs` | IBM | 计算机与AI、材料、化学 | sitemap；robots 允许；条款 ⚠ | 建议仅元数据 |  |
| [Apple Machine Learning Research](https://machinelearning.apple.com/rss.xml) `apple_mlr` | Apple | 计算机与AI | RSS /rss.xml；sitemap；robots 允许；条款 ⚠ | 建议P2 |  |
| [Amazon Science Publications](https://www.amazon.science/robots.txt) `amazon_science` | Amazon | 计算机与AI、经济、商业与管理 | RSS /index.rss；sitemap；robots Crawl-delay: 10；条款 ⚠ | 建议P2 |  |
| [DeepSeek 技术报告](https://arxiv.org/abs/2412.19437) `deepseek_reports` | DeepSeek（深度求索） | 计算机与AI | arXiv（主）；GitHub；GitHub 与 arXiv 各自条款 | 建议仅外链 | api-docs 站 robots 返回 HTML |
| [Qwen（阿里通义）技术报告](https://arxiv.org/abs/2505.09388) `qwen_reports` | 阿里巴巴 Qwen 团队 | 计算机与AI | arXiv（主）；博客 sitemap；robots 允许 | 建议仅外链 |  |
| [字节跳动 Seed 论文页](https://seed.bytedance.com/en/public_papers) `bytedance_seed` | 字节跳动 Seed | 计算机与AI | sitemap；arXiv；robots 允许；条款 ⚠ | 建议仅元数据 | 作机构归属信号 |
| [腾讯混元 / 腾讯 AI Lab](https://ai.tencent.com/robots.txt) `tencent_ai` | 腾讯 | 计算机与AI | ⚠ 待勘察（robots 的 sitemap 指向 yuanbao 域）；条款 ⚠ | 待勘察 | 发布渠道未核 |
| [百度文心（ERNIE）技术报告](https://yiyan.baidu.com/blog/publication/ERNIE_Technical_Report.pdf) `baidu_ernie` | 百度 | 计算机与AI | 人工；arXiv；条款 ⚠；research.baidu.com robots 返回 HTML | 建议仅外链 |  |
| [智谱 Z.ai（GLM）技术报告](https://arxiv.org/abs/2508.06471) `zhipu_glm` | 北京智谱华章 | 计算机与AI | arXiv（主）；sitemap；robots 允许 | 建议仅外链 |  |
| [月之暗面 Kimi 技术报告](https://arxiv.org/abs/2507.20534) `moonshot_kimi` | Moonshot AI | 计算机与AI | arXiv（主）；GitHub；moonshot.cn robots 404 | 建议仅外链 |  |

### 大学技术报告（5）

| 候选 | 运营方 | 学科 | 通道与条款 | 建议 | 备注 |
|---|---|---|---|---|---|
| [MIT CSAIL Technical Reports](https://dspace.mit.edu/handle/1721.1/29807) `mit_csail_tr` | MIT / DSpace@MIT | 计算机与AI | OAI-PMH（/server/oai/request，DSpace 7+）；sitemap；robots 允许；各条目许可不一 ⚠ | 建议P2 | OAI 按集合增量；DSpace 实例族 |
| [Stanford CS Technical Reports](https://exhibits.stanford.edu/cs/feature/technical-reports) `stanford_cs_tr` | Stanford CS | 计算机与AI | 人工（静态页）；⚠ | 建议仅外链 | 数量为二手（检索摘要） |
| [UC Berkeley EECS Technical Reports](https://www2.eecs.berkeley.edu/Pubs/TechRpts/) `berkeley_eecs_tr` | UC Berkeley EECS | 计算机与AI | 人工 HTML 列表；未见 OAI/RSS；robots 允许 /Pubs/TechRpts/ | 建议仅元数据 | 多数博士论文以 TR 形式发布 |
| [CMU SCS Technical Reports](http://reports-archive.adm.cs.cmu.edu/cs.html) `cmu_scs_tr` | Carnegie Mellon SCS | 计算机与AI | 人工（按年静态页）；⚠；仅 http | 建议仅元数据 |  |
| [Cambridge UCAM-CL-TR](https://www.cl.cam.ac.uk/techreports/) `cam_cl_tr` | University of Cambridge CST | 计算机与AI | 人工 HTML 列表；robots 允许 /techreports/；⚠ | 建议仅元数据 | 仍活跃 |

### 政府与国家实验室报告（8）

| 候选 | 运营方 | 学科 | 通道与条款 | 建议 | 备注 |
|---|---|---|---|---|---|
| [NASA NTRS](https://ntrs.nasa.gov/api/citations/search?q=turbulence&page.size=1) `nasa_ntrs` | NASA STI Program | 物理与天文、地学、材料 | JSON API /api/citations/search；sitemap；记录含 copyright.determinationType（样本为 PUBLIC_USE_PE… | 建议P2 | 按记录许可字段过滤 |
| [NIST Technical Series Publications](https://api.crossref.org/prefixes/10.6028/works?rows=0) `nist_pubs` | NIST | 物理与天文、化学、材料、计算机与AI | Crossref:prefix 10.6028；sitemap；robots 允许；联邦作品 ⚠ | 建议P2 | 含 NIST SP 800 等安全标准 |
| [USGS Publications Warehouse](https://api.crossref.org/prefixes/10.3133/works?rows=0) `usgs_pubs` | US Geological Survey | 地学 | Crossref:prefix 10.3133；⚠ 未核 robots/条款 | 建议P2 | 任务外补充 |
| [DTIC 公开技术报告](https://discover.dtic.mil/robots.txt) `dtic_public` | US DoD DTIC | 计算机与AI、物理与天文、材料 | sitemap；API ⚠；robots 允许；受限部分需账号，不接 | 待勘察 | 只取公开发布部分 |
| [US GAO Reports](https://www.gao.gov/rss/reports.xml) `gao_reports` | US GAO | 经济、商业与管理 | RSS /rss/reports.xml；robots Crawl-delay: 420（极保守）；联邦作品 ⚠ | 建议仅元数据 | 只用 RSS |
| [US CBO Reports](https://www.cbo.gov/robots.txt) `cbo_reports` | US Congressional Budget Off… | 经济 | —（robots.txt 返回 403 JS 挑战，已停用）；挑战页 | 建议仅外链 | 挑战页，停用 |
| [Fed FEDS Notes](https://www.federalreserve.gov/feeds/feds_notes.xml) `fed_feds_notes` | Federal Reserve Board | 经济、金融 | RSS /feeds/feds_notes.xml；Crossref:ISSN；公共领域 ⚠ | 建议P1（可与 fed_board_wp 共用连接器） | 并入 fed_board_wp 子系列 |
| [Liberty Street Economics](https://libertystreeteconomics.newyorkfed.org/feed/) `liberty_street` | Federal Reserve Bank of New… | 经济、金融 | RSS /feed/；sitemap；robots 允许；条款 ⚠ | 建议P2 | 区域联储博客代表 |

### 国际组织报告（4）

| 候选 | 运营方 | 学科 | 通道与条款 | 建议 | 备注 |
|---|---|---|---|---|---|
| [BIS 报告与 Bulletin（WP 系列外）](https://www.bis.org/doclist/bis_fsi_publs.rss) `bis_publ` | Bank for International Sett… | 经济、金融 | 官方 RSS（如 /doclist/bis_fsi_publs.rss）；robots 允许 /publ/；条款 ⚠ | 建议P2 | Quarterly Review 可判 L1a，待主 agent 裁 |
| [IMF 旗舰报告与 F&D](https://api.crossref.org/prefixes/10.5089/works?rows=0) `imf_publ` | IMF | 经济、金融 | Crossref:prefix 10.5089（站点 RSS 返回 Akamai 403）；站点拒绝，已停用；版权 IMF ⚠ | 建议P2 | 只走 Crossref |
| [OECD 出版物](https://api.crossref.org/prefixes/10.1787/works?rows=0) `oecd_publ` | OECD | 经济、商业与管理 | Crossref:prefix 10.1787；sitemap；robots 允许；许可 ⚠ | 建议P2 | OECD WP 已在 other_cb_wp |
| [World Bank Open Knowledge Repository](https://openknowledge.worldbank.org/server/oai/request?verb=Identify) `worldbank_okr` | World Bank | 经济、金融 | OAI-PMH（/server/oai/request，DSpace）；许可逐条 ⚠ | 建议P2 | PRWP 属 worldbank_prwp |

### 智库报告（6）

| 候选 | 运营方 | 学科 | 通道与条款 | 建议 | 备注 |
|---|---|---|---|---|---|
| [Brookings Research](https://www.brookings.edu/robots.txt) `brookings` | Brookings Institution | 经济 | sitemap_index；/feed/ 302 到首页（无 RSS）；robots 允许；条款 ⚠ | 建议仅元数据 |  |
| [PIIE Publications](https://www.piie.com/robots.txt) `piie` | Peterson Institute | 经济、金融 | ⚠（/rss.xml 404）；人工；robots 允许；条款 ⚠ | 待勘察 |  |
| [Bruegel Analysis](https://www.bruegel.org/rss.xml) `bruegel` | Bruegel | 经济、金融 | RSS /rss.xml；robots 允许；条款 ⚠ | 建议P2 |  |
| [RAND Reports](https://api.crossref.org/prefixes/10.7249/works?rows=0) `rand` | RAND Corporation | 经济、商业与管理、计算机与AI | Crossref:prefix 10.7249（站点 robots 返回 CloudFront 403，已停用）；站点拒绝 | 建议仅元数据 | 只走 Crossref |
| [VoxEU Columns（含 JMP Vox）](https://cepr.org/rss/vox-content) `voxeu` | CEPR | 经济、金融 | RSS /rss/vox-content；robots Crawl-delay: 3；条款 ⚠ | 建议P2 | 与 cepr_dp 同主体 |
| [McKinsey Global Institute](https://www.mckinsey.com/robots.txt) `mckinsey_mgi` | McKinsey & Company | 经济、商业与管理 | —（robots.txt 请求 15 秒超时）；⚠ 商业内容 | 建议仅外链 | 未取到 robots，不自动访问 |

### 学位论文首发（1）

| 候选 | 运营方 | 学科 | 通道与条款 | 建议 | 备注 |
|---|---|---|---|---|---|
| [大学机构库 ETD（DSpace/EPrints OAI 实例族）](https://dspace.mit.edu/robots.txt) `univ_ir_etd` | 各大学图书馆 | 跨学科综合 | OAI-PMH（按 set 选学位论文集合）；逐库、逐条许可 | 建议P2 | OATD/CORE 的上游，走 OAI 实例族 |

### JMP 与个人首发（4）

| 候选 | 运营方 | 学科 | 通道与条款 | 建议 | 备注 |
|---|---|---|---|---|---|
| [EconJobMarket.org](https://econjobmarket.org/) `econjobmarket` | Econ Job Market Inc. | 经济、金融 | —；robots 允许 /；材料非公开 | 不接（材料非公开） | 只作外链参考 |
| [AEA JOE](https://www.aeaweb.org/robots.txt) `aea_joe` | American Economic Associati… | 经济 | —；robots 禁 GPTBot | 不接（范围外） |  |
| [名校经济/金融/商学院 placement 与候选人页](https://econ.washington.edu/research/job-market-papers) `dept_placement` | 各院系 | 经济、金融、商业与管理 | 人工；无统一格式；逐站 | 建议仅用户导入 | 不做全站爬取 |
| 个人主页 JMP `personal_jmp` | 个人 | 经济、金融、商业与管理 | 用户导入或按需外链；逐站 | 建议仅用户导入 | 合规边界：零散，不爬 |

### 标准与技术规范（3）

| 候选 | 运营方 | 学科 | 通道与条款 | 建议 | 备注 |
|---|---|---|---|---|---|
| [IETF RFC](https://www.rfc-editor.org/rfcrss.xml) `ietf_rfc` | IETF / RFC Editor | 计算机与AI | RSS /rfcrss.xml；Crossref:prefix 10.17487；sitemap；robots 允许；IETF Trust 条款 ⚠ | 建议P2 | 建议纳入 CS L1c |
| [W3C Technical Reports](https://api.w3.org/specifications) `w3c_tr` | W3C | 计算机与AI | JSON API api.w3.org/specifications；robots 允许 /TR/；文档许可 ⚠ | 建议仅元数据 |  |
| ISO/IEC 等付费标准 `iso_iec` | ISO/IEC 等 | 计算机与AI | —；付费 | 不接（付费） | IEEE 标准已在 ieee_xplore |

## L2a 文献库与学科仓储（28）

### 区域与国家文献库（11）

| 候选 | 运营方 | 学科 | 通道与条款 | 建议 | 备注 |
|---|---|---|---|---|---|
| [KCI 韩国学术志引用索引](https://www.kci.go.kr/kciportal/po/openapi/openApiList.kci) `kci` | NRF（韩国） | 跨学科综合 | REST Open API（需 key）；OAI-PMH（免 key）；文件数据；⚠ 许可未读到 | 建议P2（区域扩展时，走 OAI-PMH） |  |
| [ScienceON（原 NDSL）](https://scienceon.kisti.re.kr/por/oapi/openApi.do) `scienceon` | KISTI | 跨学科综合、计算机与AI、材料 | API Gateway（注册会员后申请 key，XML）；按 API 条款 ⚠ | 待勘察（需会员，暂不接） |  |
| [J-GLOBAL](https://jglobal.jst.go.jp/help/webapi/home) `jglobal` | JST | 跨学科综合、化学、材料 | WebAPI 计划（页面证书链异常，条款未读到）；⚠ | 待勘察 | WebFetch 证书错误 |
| [Airiti Library 华艺线上图书馆](https://www.doi.org/the-community/existing-registration-agencies/) `airiti_library` | 华艺数位 | 跨学科综合 | 无开放 API ⚠；订阅 | 建议仅用户导入 | 订阅性质为公知 ⚠ |
| [eLIBRARY.ru（RSCI/РИНЦ）](https://sciguide.hse.ru/sources/elibrary/) `elibrary_ru` | НЭБ eLIBRARY（俄罗斯） | 跨学科综合 | 付费或申请的数据导出/API；条款禁止机器人与批量抓取 | 不接（条款禁止自动化） | 二手出处（HSE 指南） |
| [CyberLeninka](https://cyberleninka.org/about) `cyberleninka` | CyberLeninka（俄罗斯） | 跨学科综合 | OAI-PMH（cyberleninka.ru/oai，历史出处）；CC BY 为主 | 待勘察（OAI 现状未测） |  |
| 超星 / 读秀 `chaoxing_duxiu` | 超星集团 | 跨学科综合 | 无开放 API ⚠；订阅 | 建议仅用户导入 | 本次未访问 ⚠ |
| 中国引文数据库（CNKI） `cnki_citation` | 中国知网 | 跨学科综合 | 无开放 API ⚠；订阅；kns.cnki.net robots 全站禁止 | 不接（同 CNKI） | URL ⚠ |
| [国家哲学社会科学文献中心期刊库（NCPSSD）](https://www.ncpssd.cn/) `ncpssd` | 中国社会科学院 | 经济、商业与管理 | 网页；无开放 API ⚠；⚠ | 建议仅外链 | 规模为二手（高校图书馆页） |
| [NSTL 文献检索平台](https://www.nstl.gov.cn/) `nstl` | NSTL | 跨学科综合 | 网页；开放 API ⚠ 未找到；⚠ | 建议仅外链 |  |
| [中国科学引文数据库 CSCD](http://sciencechina.cn/select) `cscd` | 中国科学院文献情报中心 | 跨学科综合 | 订阅（Web of Science 平台上的区域库 ⚠）；订阅 | 不接（数据）；来源刊名单作评级标签 |  |

### 学科库（5）

| 候选 | 运营方 | 学科 | 通道与条款 | 建议 | 备注 |
|---|---|---|---|---|---|
| [GeoRef](https://information.americangeosciences.org/georef/) `georef` | 美国地球科学研究所 AGI | 地学 | 经 EBSCO/ProQuest 订阅；订阅 | 不接（订阅，仅外链） | 地学无免费等价库；经 OpenAlex 补 |
| APA PsycInfo / PsycArticles `apa_psycinfo` | APA | 心理与认知 | 订阅；订阅；APA 平台对自动化关闭 | 不接（订阅，仅外链） | 期刊层已由 apa_psycnet（M1）登记 |
| [PubPsych / PSYNDEX](https://pubpsych.zpid.de/pubpsych/about.jsp?lang=EN) `pubpsych` | ZPID | 心理与认知 | 网页检索；API ⚠ 未找到；⚠ | 待勘察 | pubpsych.de 根域返回 404 页 |
| ACM Guide to Computing Literature `acm_guide` | ACM | 计算机与AI | 随 acm_dl（站点不做自动化）；ACM 条款 | 建议仅外链（dblp 已覆盖书目） | 内容范围为公知 ⚠ |
| Reaxys（及同类化学订阅库） `reaxys` | Elsevier | 化学、材料 | 订阅；条款 ⚠ 未核（SciFinder 条款禁止批量与 AI 用途） | 不接（订阅，仅外链） |  |

### 仓储（3）

| 候选 | 运营方 | 学科 | 通道与条款 | 建议 | 备注 |
|---|---|---|---|---|---|
| [IRDB 学术机构仓储数据库](https://support.irdb.nii.ac.jp/ja/application/irdb) `irdb` | NII | 跨学科综合 | 对外 OAI-PMH/API ⚠ 未核；内容也经 CiNii Research 呈现；⚠ | 待勘察（优先经 CiNii ResourceSync） | 日本学位论文重要来源 |
| [NSF-PAR 公共获取库](https://catalog.data.gov/dataset/nsf-public-access-repository) `nsf_par` | NSF | 跨学科综合、计算机与AI | API/OAI ⚠ 未找到文档；data.gov 有目录条目；美国政府托管 ⚠ | 待勘察（优先经 OpenAlex/Crossref 旁路） |  |
| eScholarship（加州大学） `escholarship` | California Digital Library | 跨学科综合、心理与认知 | OAI-PMH；按单篇 | 建议P2（经 OAI；CogSci 用） | 兼 M1-open 角色 |

### 学位论文库（9）

| 候选 | 运营方 | 学科 | 通道与条款 | 建议 | 备注 |
|---|---|---|---|---|---|
| [ProQuest Dissertations & Theses Global](https://www.proquest.com/robots.txt) `proquest_pqdt` | Clarivate/ProQuest | 跨学科综合 | —（订阅）；订阅；robots 禁 GPTBot | 建议仅用户导入 |  |
| [ProQuest Open Access Dissertations（原 PQDT Open）](https://pqdtopen.proquest.com/about.html) `pqdt_open` | Clarivate/ProQuest | 跨学科综合 | —（旧站返回 521；二手称已迁入 ProQuest 平台）；免费阅读 ⚠ | 建议仅外链 | 迁移为二手信息 ⚠ |
| [EThOS（British Library）](https://ethos.bl.uk/) `ethos` | British Library | 跨学科综合 | ⚠（Hyku 新平台，API 未核）；条款 ⚠ | 待勘察 | 2023 网络攻击后 2026-07-08 恢复（二手） |
| [DART-Europe](https://www.ucl.ac.uk/library/dart-europe-e-theses-portal-has-closed-down) `dart_europe` | LIBER / UCL | 跨学科综合 | —（301 到 UCL 关停公告）；— | 不接（2025-02-03 关停） | 关停日期为二手 |
| [theses.fr](https://theses.fr/api/v1/theses/recherche/?q=economie&nombre=1) `theses_fr` | ABES（法国） | 跨学科综合 | JSON API /api/v1/theses/recherche/；sitemap；robots Crawl-delay: 5；元数据许可 ⚠ | 建议P2 | "economie" 命中 57,719 |
| [DNB 在线学位论文](https://www.dnb.de/DE/Professionell/Services/WissenschaftundForschung/DNBLab/DNBLabDatensets/freieDigitaleObjekte/freieDigitaleHochschulschriften.html) `dnb_diss` | Deutsche Nationalbibliothek | 跨学科综合 | OAI（XMetaDissPlus）；DNBLab 数据集；robots Crawl-delay: 10；许可 ⚠ | 待勘察 |  |
| [Shodhganga](https://shodhganga.inflibnet.ac.in/moredetails/about.html) `shodhganga` | INFLIBNET（印度） | 跨学科综合 | OAI-PMH（二手）；robots.txt 请求超时 ⚠ | 待勘察 |  |
| [国家图书馆博士论文库](https://lib.nankai.edu.cn/2019/0717/c15444a187830/pagem.htm) `nlc_thesis` | 中国国家图书馆 | 跨学科综合 | —（实名注册）；注册；robots 404 | 建议仅外链 |  |
| [NSTL 学位论文](https://www.nstl.gov.cn/) `nstl_thesis` | 国家科技图书文献中心 | 跨学科综合 | —（注册后请求全文）；注册；robots 返回 HTML ⚠ | 建议仅外链 |  |

## L2b 检索引擎与聚合项目（29）

### 检索引擎（6）

| 候选 | 运营方 | 学科 | 通道与条款 | 建议 | 备注 |
|---|---|---|---|---|---|
| [CiteSeerX](https://citeseerx.ist.psu.edu/) `citeseerx` | Penn State IST | 计算机与AI | 根域现重定向到 Wayback 快照（2025-12-30）；— | 不接（已停服） | 本次 curl 实测重定向 |
| 百度学术 `baidu_scholar` | 百度 | 跨学科综合 | 无公开 API；⚠ | 不接（无 API，仅竞品参照） |  |
| AMiner `aminer` | 智谱 Z.ai | 计算机与AI、跨学科综合 | 开放平台 API ⚠ 条款未核；⚠ | 待勘察（仅竞品参照为默认） |  |
| [Scilit](https://blog.mdpi.com/2017/11/24/scilit-scholarly-database/) `scilit` | MDPI | 跨学科综合 | API 按申请 ⚠；本次 UA 访问返回 403；⚠ | 不接（与 Crossref 重复，仅竞品参照） |  |
| [OATD](https://oatd.org/faq.html) `oatd` | Wake Forest Univ.（Thomas Do… | 跨学科综合 | —（robots.txt 返回 Cloudflare 挑战，已停用；FAQ 称无批量下载与 OAI 导出）；挑战页 | 建议仅外链 | 改从源机构库 OAI 收 |
| [NDLTD Global ETD Search](https://ndltd.org/thesis-resources/global-etd-search/) `ndltd_global` | NDLTD | 跨学科综合 | —（search.ndltd.org 503；官方称已下线重建，2025-05 更新）；— | 不接（下线） | 官方推荐 OATD |

### 评审与引用信号（4）

| 候选 | 运营方 | 学科 | 通道与条款 | 建议 | 备注 |
|---|---|---|---|---|---|
| Sciety `sciety` | eLife | 生命科学与医学 | ⚠ 数据接口未核（Europe PMC 已带评审信号）；⚠ | 待勘察（优先经 Europe PMC） |  |
| PubPeer `pubpeer` | PubPeer Foundation | 生命科学与医学、跨学科综合 | ⚠ API 未核；⚠ | 待勘察（撤稿/争议信号候选） |  |
| [scite](https://scite.ai/api) `scite` | Research Solutions | 跨学科综合 | API（控制台自助 key）；Search API 商用/研究须另签许可；商业许可 | 不接（商业许可，仅竞品参照） |  |
| Emergent Mind `emergent_mind` | Emergent Mind | 计算机与AI | ⚠ 无公开 API 证据；— | 不接（仅竞品参照） |  |

### 引文图谱工具（3）

| 候选 | 运营方 | 学科 | 通道与条款 | 建议 | 备注 |
|---|---|---|---|---|---|
| Connected Papers `connected_papers` | Connected Papers | 跨学科综合 | 无公开 API ⚠；— | 不接（仅竞品参照） |  |
| Litmaps / ResearchRabbit `litmaps` | Litmap Ltd（2025-05 收购 Resea… | 跨学科综合 | 无公开数据 API（二手）；— | 不接（仅竞品参照） |  |
| Inciteful `inciteful` | Inciteful | 跨学科综合 | —；— | 不接（已转向） |  |

### AI 检索与问答（10）

| 候选 | 运营方 | 学科 | 通道与条款 | 建议 | 备注 |
|---|---|---|---|---|---|
| [Elicit](https://elicit.com/blog/elicit-api) `elicit` | Elicit | 跨学科综合 | REST API 与 MCP，仅付费订阅用户；API Terms 约束 | 不接（仅竞品参照） |  |
| [Consensus](https://consensus.app/home/api/) `consensus` | Consensus | 跨学科综合 | API 与 MCP 含在付费计划（每次 $0.05 超额）；商业 | 不接（仅竞品参照） |  |
| [Undermind](https://www.undermind.ai/) `undermind` | Undermind | 跨学科综合 | Enterprise API 与 MCP；商业 | 不接（仅竞品参照） |  |
| SciSpace `scispace` | SciSpace（原 Typeset） | 跨学科综合 | ⚠；商业 | 不接（仅竞品参照） |  |
| Ai2 Asta（Paper Finder、ScholarQA） `asta` | Ai2 | 跨学科综合 | 经 S2 API 接入（s2 已为来源）；同 S2 条款 | 不接（经 s2 已覆盖，仅参照） |  |
| Scholar Inbox `scholar_inbox` | 图宾根大学 Geiger 组 | 计算机与AI、跨学科综合 | 无平台 API；数据集 avg-dev/scholar_inbox_datasets（许可 NOASSERTION）；⚠ | 不接（竞品参照；数据集许可待核后作离线评估） |  |
| Cool Papers（papers.cool） `papers_cool` | 苏剑林 | 计算机与AI | 无 API；仓库无 license；— | 不接（仅竞品参照） |  |
| Paper Digest `paper_digest` | Paper Digest | 跨学科综合 | ⚠ API 未找到；— | 不接（仅竞品参照） |  |
| R Discovery `r_discovery` | Cactus Communications | 跨学科综合 | 无公开 API ⚠；商业 | 不接（仅竞品参照） |  |
| 已关停或转向的发现产品（汇总） | — | 跨学科综合 | —；— | 不接（已关停，仅作风险参照） |  |

### 开源聚合项目（6）

| 候选 | 运营方 | 学科 | 通道与条款 | 建议 | 备注 |
|---|---|---|---|---|---|
| [arxiv-sanity-lite](https://github.com/karpathy/arxiv-sanity-lite) `arxiv_sanity_lite` | karpathy（开源） | 计算机与AI | 代码 MIT；最近 push 2023-06-19；MIT | 不接（仅借鉴算法） |  |
| [ccfddl / ccf-deadlines](https://github.com/ccfddl/ccf-deadlines) `ccfddl` | ccfddl 社区（开源） | 计算机与AI | GitHub 数据文件；MIT | 建议P2（会议名录与等级信号，快照导入） | core 字段版本须核 |
| [Conference-Acceptance-Rate](https://github.com/lixin4ever/Conference-Acceptance-Rate) `conf_accept_rate` | lixin4ever（开源） | 计算机与AI | GitHub Markdown；MIT | 建议仅元数据（录用率参考，最近 push 2025-09-23） |  |
| CSRankings `csrankings` | emeryberger（开源） | 计算机与AI | GitHub 数据文件；CC BY-NC-ND 4.0（COPYING） | 建议仅元数据（只存事实标签 CSR） |  |
| ORKG 开放研究知识图谱 `orkg` | TIB | 计算机与AI、跨学科综合 | REST API ⚠；代码 MIT；数据许可 ⚠ | 待勘察（观察） |  |
| Open Knowledge Maps / Scholia（开源发现前端汇总） | OKM（奥地利非营利）；Scholia（Wikidat… | 跨学科综合 | 代码 MIT / GPL-3.0；数据来自 BASE、PubMed、Wikidata；— | 不接（仅借鉴） |  |

## 对现有名录行的调研结论

这些结论不新增行，只在名录维护时补进对应行的证据：

- `osti_gov`：兼 L1c，是 DOE 技术报告的首发处；Crossref 前缀 10.2172 下有 327,969 条 Report；robots 对所有代理禁 `/search/`。
- `fed_board_wp`：FEDS Notes（ISSN 2380-7172，774 个 DOI，有 RSS）属 L1c，另列候选 `fed_feds_notes`，可与本行共用连接器。
- `cnki`、`wanfang`：它们的博硕论文库同样只接受用户导入。
- `repec`：JMP 系列停在 jm2020，2021–2025 年的页面返回 404。
- `crossref`、`datacite`、`orcid`、`ror`、`wikidata`、`open_policy_finder`：M2 角色不变。ROR 正在并入 Open Funder Registry；Open policy finder 的新 API 于 2026-02-11 发布，站点内容为 CC BY-NC-ND 4.0。
- `jstage`、`scielo`、`redalyc`、`sciengine`、`episciences`：维持 M1。
- Brookings 的 BPEA 已作为期刊列在[经济 venue 名录](venues/economics.md)；BIS Quarterly Review 并入上表"BIS 报告与 Bulletin"。

## 怎么用这份清单

- **升级路径**：候选 → 补齐证据（一手条款、robots、通道实测）→ 提交注册表条目（初始状态 `v2-P2` 或 `metadata-only`）→ 主 agent 复核 → 进名录。改为 `excluded` 同样留理由。
- **先读条款**：企业官网、智库与国际组织站点只核了 robots，批量取 PDF 前须按 [08 合规](../plan/v2/08-compliance-security-privacy.md)核读 ToS。
- **不做全站爬取**：个人主页、院系 placement 页零散，默认用户导入或按需外链。
- **本清单不是全集**：地学的 GSL Lyell Collection、SEG、PANGAEA，材料的 TMS、ASM，以及 Project MUSE、SMF 等平台还没调研。
