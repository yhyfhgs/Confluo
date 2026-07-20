# Phase-0 收官一致性审查报告（开发前第一次修订）

> 日期：2026-07-20 · 执行：fable5 · 触发：用户指令（开发前全面复查方案与需求一致性）
> 方法：①用户原始需求逐条覆盖核查 ②机器交叉检查（链接 / front matter / INDEX 对账 / catalog-adapter 注册对账 / 占位符）③全库人工通读 ④修复并提交（D-015）

## 1. 需求符合性矩阵（用户原始 7 点要求 → 系统落点）

| # | 用户要求 | 落点 | 判定 |
|---|---|---|---|
| 1a | 可插拔双模块（开源预印本/会议 + 认证闭源出版社） | D-002/D-003；design/02（Adapter×VenueSpec）、03（open_access）、04（auth_gated） | ✅ |
| 1b | 出版时间轴、期数历史、每期论文清单 | FR-02/03/04；design/05 discover/enumerate、design/08 VenueEra；`timeline`/`list` CLI | ✅ |
| 1c | 自定义特定期数/文章下载 + 文章所有内容获取 | FR-05；`pull --volume/--issue/--doi/--filter`、`grab`；Asset 五类（pdf/si/html/bibtex/source）+ extract 全文 | ✅ |
| 1d | 登录、下载、入库整体 pipeline | D-004 六阶段 + D-006 认证（design/05/07，SVG-03/04） | ✅ |
| 2a | CS/AI 顶会清单（用户点名 11 个全覆盖） | catalog/cs-ai-conferences（ICML/NeurIPS/ICLR/AAAI/KDD/CVPR/STOC/FOCS/SODA/WWW/EC ✓ + 21 个扩展） | ✅ |
| 2b | AI 期刊（IEEE 系）+ CS 出版社/协会 | catalog/ai-ml-journals（IEEE 6 刊 + OA 独立刊 + ACM/Springer/Elsevier）；publishers-platforms（IEEE/ACM/SIAM/USENIX/Springer…） | ✅ |
| 2c | 金融期刊（Top3/量化/Field Top/次级） | catalog/finance-journals（JF/JFE/RFS + MathFin/FinStoch/QuantFin/SIFIN/JFEc + JFQA/RoF/JFI/JBF/JFM/JCF + RAPS/RCFS + JPM 系） | ✅ |
| 2d | OR 期刊（MS 等） | catalog/or-ms-journals（MS/OR/MSOM/MOOR/IJOC + EJOR/POM/MP/AOR） | ✅ |
| 2e | 经济学顶刊（Top5/Field Top/TE/ET） | catalog/economics-journals（AER/ECMA/JPE/QJE/REStud + AEJ 系 + 13 个 Field + TE/QE 开放 + ET） | ✅ |
| 2f | 预印本平台（arXiv/SSRN；自定义 Topic/Tag 防过载） | catalog/preprint-platforms（arXiv 白名单 40+9+3+6 类核验、SSRN FEN/ERN、RePEc/NBER/CEPR）；design/09 订阅 DSL + guard 熔断 | ✅ |
| 2g | 逐站爬虫流程 + 浏览器登录 + 分类入库 + 会议年度网址漂移 | 16 篇 adapter 详设 + design/07 登录 + design/06 分域落盘 + D-012 VenueEra/track | ✅ |
| 3 | GitHub 同类项目架构参考 | research/github-similar-projects（20 项 + 四维横向总结 + 设计对照表） | ✅ |
| 4 | 文本系统（计划/进度/测试/logs/reports） | docs 九目录树 + INDEX + front matter 状态机（D-008） | ✅ |
| 5 | SVG 图 + 多篇详设 md（功能/方案/测试/验收五要素） | 6 SVG + 45 篇 md；五要素为 doc-conventions §3 硬规范 | ✅ |
| 6 | git 流程 + 文档/代码状态流程 + AGENTS.md | process 三篇（D-009/D-010）+ AGENTS.md | ✅ |
| 7 | Sonnet 做搜索、Fable 做设计 | AGENTS.md §7 制度化；实际执行 7 个 Sonnet 调研任务、全部设计由 Fable 定稿 | ✅ |

## 2. 发现与修复清单（本次共 13 项，全部已修）

**实质性设计修正（3 项，记 [D-015](../plan/decision-log.md)）**
1. VenueSpec 校验：期刊 issn 必填（openalex_source 降为可选）——与 D-005 修订传导一致；
2. CLI `grab --url` 增补 + identifier 开放 scheme `url`——覆盖无标准 id 的 WP/ECCC 场景（此前 catalog 已引用该用法但 CLI 未定义）；
3. adapter 总量口径统一 ~40（D-002 原估 15~25 过时；publishers-platforms 顶注与 SVG-02 数字同步）。

**勘误修复（8 项）**
4. economics-journals：Econometric Theory（cambridge、订阅）误列于"开放获取/学会刊（econsoc，无需认证）"表 → 移出独立成节；
5. finance-journals：删除幽灵行 `jffr`（内容为"见 jfqa"的无效条目）；
6. or-ms-journals："ijaa/orsc…" 混合 id 行 → 拆为 orsc/isre 两条规范条目；
7. adapters/README 索引：5 行"⚠ 勘察待并入/平台栈待辨"标注已过时（勘察当日已并入）→ 更新为已并入状态；
8. arxiv adapter §1 服务范围列举缺 math.OC（catalog 白名单含）→ 补齐并声明以 catalog 为准；
9. ssrn adapter §4 限速表述自相矛盾（"两倍保守"vs"即下限"）→ 改为"5s 底线 + 2–5s 抖动 = 有效 5–10s"；
10. design/06 identifier scheme 注释缺 openreview/cvf/neurips/repec（各 adapter 已使用）→ 补全并标注开放枚举；
11. design/07 配图相对路径风格不一致（`../../docs/diagrams/` vs 全库 `../diagrams/`）→ 统一。

**注册补全（2 项）**
12. catalog 引用但未登记的 8 个 planned adapter → 补入 adapters/README：ijcai、jmlr、jair、bmvc（OA）+ tandf、annual_reviews、now_publishers、uwpress（auth，T2/T3 暂缓）；
13. design/02 §2.1 清单表同步补 ijcai 与 jmlr/jair 行（含 TMLR→openreview、TACL→acl_anthology 的复用注记）。

## 3. 审查中确认无误的关键一致性（抽查留痕）

- 编号引用：45 篇文档中出现的全部 FR-xx/AC-x.x/D-xxx/NFR-x/R 引用在源头文档存在；
- 双状态机口径：16 篇 adapter front matter=review 与 INDEX、README 索引三方一致；
- 限速值链条：各 adapter 声明值 ≥ 其 research 勘察记载的站点要求（AC-0.5 口径），无一例外；SSRN 1/5s、闭源 1/6s、arXiv 1/3s、Crossref 动态头；
- 合规红线传导：D-014 的"点名禁止站"处理在 CEPR（仅 RePEc 元数据）、JSTOR（认证态低量兜底）、MIT Press（按需单篇）三处 catalog/adapter 落地一致；
- SVG↔文档：六图的阶段名/状态名/族划分/决策编号与对应文档逐项一致（02 号图数字已随本次修正更新）。

## 4. 遗留（不阻塞 Phase 1，均已在对应文档标注）

- 实现期核验清单：AAAI OJS 的 OAI-PMH 与 archive 分页、ECCV 的 CVF 新格式路径、jair print ISSN、INFORMS/Springer 登录态 robots 补勘察、IJOC/mksc ISSN 复核；
- adapter 详设 16 篇 review→approved 按平台开工节奏逐篇评审（status-workflow 门禁不变）；
- 外部申请项（R6）：Elsevier dev key、Wiley TDM token、IEEE 元数据 API、S2 key。

## 5. 结论

需求覆盖 17/17 项符合；发现的 13 项不一致全部修复并提交。**判定：设计基线一致性通过，可进入 Phase 1。**
