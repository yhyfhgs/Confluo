---
title: 验收标准总表
status: approved
owner: fable5
updated: 2026-07-21
---

# 验收标准（Acceptance Criteria）

> 编号 `AC-<phase>.<n>`。每条含：前置、步骤、可观测的通过判据。判据必须客观可验（文件存在/计数相等/日志含特定记录），不用主观措辞。
> 与 FR/NFR 的映射见各设计文档 §测试与验收。执行留痕入 `docs/testing/records/`。

## AC-1 · 核心框架（Phase 1，mock adapter）

| ID | 场景 | 通过判据 |
|---|---|---|
| AC-1.1 | mock venue 端到端 `pull` | DB 中 Issue/Paper/Asset 计数符合 mock 数据；`data/` 下文件数=Asset(fetched) 数；报告"成功=N，失败=0" |
| AC-1.2 | dry-run 不落盘 | `pull --dry-run` 后 `data/` 无新增文件、DB 无 Asset(fetched)；输出的"将下载 N 篇"与随后实跑的实际下载数相等 |
| AC-1.3 | 断点续爬幂等 | 在 fetch 阶段随机 kill 进程后重跑 `pull`；最终 DB dump 与"不中断一次跑完"逐行一致；日志含 skipped 记录且无重复 FetchLog |
| AC-1.4 | 限速合规 | 压力场景下某 domain 的 FetchLog 时间戳间隔统计：实际速率 ≤ 配置值×1.05 |
| AC-1.5 | 状态机与 BLOCKED | 注入 auth_expired → 任务转 BLOCKED 不占重试；`resume` 后回 PENDING 并完成 |
| AC-1.6 | VenueSpec 校验 | 非法 spec（未知 adapter/auth 不兼容/id 冲突）被 `venues lint` 拒绝并给出定位信息 |

## AC-2 · Open-Access MVP（Phase 2）

| ID | 场景 | 通过判据 |
|---|---|---|
| AC-2.1 | `timeline iclr` | 列出 2013→当前年每一届；与 DBLP `conf/iclr` 卷数一致（±0） |
| AC-2.2 | `pull iclr --year 2024 --limit 10` | 落盘 10 个文件，每个魔数=`%PDF` 且 >10KB；DB↔文件对账一致 |
| AC-2.3 | arXiv 订阅 7 天增量 | 连续 7 日 watch：抽样 20 篇与 arXiv 官方 listing 比对，命中且无重复、无遗漏 |
| AC-2.4 | `pull cvpr --year 2023 --filter "diffusion"` | 过滤命中数=对 enumerate 全集本地过滤数；下载子集正确 |
| AC-2.5 | ACL Anthology bulk 优先 | 回填某年 EMNLP 全量走 github 数据仓库路径（日志证据），无逐页在线爬取 |
| AC-2.6 | ACM OA 会议（D-013）——**deferred(D-020)，Phase 4 重评** | 原判据：`pull kdd --year 2026` 无认证下载全文。修订 2026-07-22：LIVE 勘察证实 OA 后仍有 Cloudflare 挑战门 + ToS 禁自动下载条款（红线 AC-0.2/0.5 优先）→ 本条**不计入 Phase 2 判定**；Phase 4 依 D-020 重评（核 ToS 原文/官方通道，或降级为 Crossref 元数据+人工取回口径） |

## AC-3 · 数据模型与合并（Phase 3）

| ID | 场景 | 通过判据 |
|---|---|---|
| AC-3.1 | 强合并 | 同一 DOI 经 arXiv 与 Crossref 两路注入 → 1 条 paper、≥2 个 identifier |
| AC-3.2 | 弱信号不自动合并 | 标题改名的 WP↔刊发版注入 → 2 条 paper + 1 条 candidate_duplicate(decided=null) |
| AC-3.3 | verify 对账 | 人为制造丢文件/孤儿文件/哈希不符三类 → `verify` 全部检出并给正确修复建议 |
| AC-3.4 | 顺序无关 | 多源记录随机顺序注入，最终库状态逐行一致（属性测试通过） |
| AC-3.5 | 期刊 5 本零爬取枚举 | 含 QJE、JFE 在内 5 刊仅用 Crossref 即产出完整卷期+论文清单；篇数与 paper_count_claimed 差异有解释 |

## AC-4 · 认证与出版社（Phase 4，真实凭证 runbook）

| ID | 场景 | 通过判据 |
|---|---|---|
| AC-4.1 | 首登+取一篇 | `auth login <provider>` 人工登录后 `grab --doi <闭源DOI>` 得合法 PDF（魔数校验过） |
| AC-4.2 | 过期检测不轰炸 | 人为清 cookie 使 session 失效 → 批任务在 ≤20 篇内检出并 BLOCKED；日志无连续 401/403 轰炸（≤2 次即停） |
| AC-4.3 | 无权限降级 | 对无订阅 DOI → 标 no_entitlement、不重试、给出 Unpaywall 副本（若存在） |
| AC-4.4 | 日配额 | 单平台单日下载数 ≤ 配置上限（FetchLog 对账） |
| AC-4.5 | 登出无残留 | `auth logout <provider>` 后磁盘无可恢复 session（取证清单逐项过） |
| AC-4.6 | 风控即停 | 注入风控页特征 → BLOCKED(challenge) + 平台冷却生效 + 报告显著提示；无自动破解尝试 |

## AC-5 · SSRN 与特殊源（Phase 5）

| ID | 场景 | 通过判据 |
|---|---|---|
| AC-5.1 | SSRN 网络增量 | 按 FEN 子网枚举近 7 天清单成功率 ≥95%；全程限速 ≤1 req/5s（FetchLog 审计）；遇 Cloudflare 挑战正确 BLOCKED |
| AC-5.2 | NBER >18 月开放 | `pull nber --year <当前-2>` 无凭证成功；对 <18 月论文按策略提示配额/订阅（不利用软门绕过——见调研伦理批注） |
| AC-5.3 | TE/QE 开放刊 | Econometric Society 开放刊全文成功抓取，无需认证 |
| AC-5.4 | 平台归属正确性 | POM 走 SAGE adapter（非 Wiley/INFORMS）；SODA 走 SIAM（非 ACM）——路由解析正确 |

## AC-6 · 订阅与搜索（Phase 6）

| ID | 场景 | 通过判据 |
|---|---|---|
| AC-6.1 | 多 topic 7 天 | 3 个预置 topic 连续 7 天：无重复、无遗漏（抽样对照）、日报生成 |
| AC-6.2 | 护栏熔断 | 构造超 `max_new_per_run` 场景 → 零入库、产出含分布与收窄建议的过载报告 |
| AC-6.3 | SSRN 无下推补偿 | SSRN 订阅本地过滤后清单与人工浏览基准一致率 ≥95% |
| AC-6.4 | 下推/本地一致 | 同一 DSL 的"全本地过滤"与"下推+补偿"结果集相等 |

## AC-7 · 全文抽取与库增强（Phase 7）

| ID | 场景 | 通过判据 |
|---|---|---|
| AC-7.1 | 全文抽取 | 抽样 PDF 经 extract 得非空文本，标题与 DB 记录匹配（编辑距离阈值内） |
| AC-7.2 | GROBID 可选 | GROBID 开/关两模式均产出，关闭时降级为纯文本抽取不报错 |
| AC-7.3 | 去重审核工具 | `dedupe review` 逐条展示证据，merge/reject 后 same_as/rejected 正确落库且可回滚（物理不删行） |
| AC-7.4 | 全库对账 | 全库 `verify` 通过；preprint↔published 关联报告生成 |

## AC-8 · Venue 追踪（跨 Phase，随会议 adapter 验收）

| ID | 场景 | 通过判据 |
|---|---|---|
| AC-8.1 | 多段 era 路由 | `timeline colt` 显示 PMLR/Springer/ACM 三段 era，各段路由到对应 adapter |
| AC-8.2 | 追新→确认→落配置 | 模拟 DBLP 新卷 → `track` 出候选 → `track review` confirm → VenueSpec eras 段被正确更新 |
| AC-8.3 | 缺口区分 | `timeline naacl --audit` 区分"官方未举办年"与"数据缺失年" |

## AC-0 · 合规红线（贯穿所有 Phase，任何违反即整体不通过）

| ID | 判据 |
|---|---|
| AC-0.1 | 代码库与运行路径中不存在任何盗版源（Sci-Hub 等）集成点（静态扫描 + 人工核） |
| AC-0.2 | 无 CAPTCHA 自动求解/绕过代码；风控页一律走 BLOCKED |
| AC-0.3 | 凭证/session/PDF 不出现在 git 历史（`git log` 全历史扫描 + .gitignore 生效验证） |
| AC-0.4 | 日志与报告中无未脱敏的 cookie/token（正则扫描断言） |
| AC-0.5 | 各 adapter 默认限速 ≤ 其 research/site-survey 文档记载的站点要求；robots.txt 明确禁止的路径不访问（记录例外需 ADR） |

## 附：FR/NFR → AC 覆盖映射（可追溯性总表，D-016）

> 每条功能/非功能需求（[design/00-requirements.md](../design/00-requirements.md)）至少被一条 AC 覆盖。设计文档不逐条回引 FR 编号，追溯统一经本表。

| 需求 | 覆盖 AC | 备注 |
|---|---|---|
| FR-01 venue 注册表 | AC-1.6, AC-1.1 | lint 校验 + 端到端 |
| FR-02 时间轴发现 | AC-2.1, AC-8.1, AC-3.5 | 会议届数 / 多段 era / 期刊零爬取 |
| FR-03 年度追新 | AC-8.2 | track 候选→确认→落配置 |
| FR-04 期/届清单枚举 | AC-3.5, AC-2.1, AC-2.4 | 篇数对账（paper_count_claimed） |
| FR-05 精确选择 + dry-run | AC-1.2, AC-2.2, AC-2.4 | limit / filter / dry-run 零副作用 |
| FR-06 开放源下载 | AC-2.2, AC-2.5, AC-2.6, AC-5.2, AC-5.3 | 含 bulk 优先与 ACM OA 场景 |
| FR-07 认证源下载 | AC-4.1 | 全平台 runbook 逐个执行 |
| FR-08 会话管理 | AC-4.2, AC-4.5, AC-1.5 | 过期检测 / 登出无残留 / BLOCKED-resume |
| FR-09 礼貌爬取 | AC-1.4, AC-4.4, AC-5.1, AC-0.5 | 限速审计 / 日配额 / robots |
| FR-10 断点续爬 | AC-1.3, AC-3.3 | kill-9 幂等 / verify 对账 |
| FR-11 元数据入库与合并 | AC-3.1, AC-3.2, AC-3.4 | 强合并 / 弱信号候审 / 顺序无关 |
| FR-12 文件管理 | AC-1.1, AC-3.3 | DB↔文件双向对账 |
| FR-13 全文抽取 | AC-7.1, AC-7.2 | GROBID 可选降级 |
| FR-14 观测性 | AC-1.4, AC-4.2, AC-4.4 | FetchLog 为审计证据源；canary 见 test-plan §4 |
| FR-15 订阅 DSL | AC-6.1, AC-6.3, AC-6.4, AC-2.3 | 编译下推与本地一致性 |
| FR-16 增量与护栏 | AC-6.2, AC-2.3 | 熔断 / 无重复无遗漏 |
| NFR-3 断点续爬 | AC-1.3 | |
| NFR-4 限速默认值 | AC-1.4, AC-0.5 | |
| NFR-6 离线可测 | T3 fixture 门禁（test-plan §1） | 非 AC 形态，CI 强制 |
| NFR-8 凭证安全 | AC-0.3, AC-0.4, AC-4.5 | |

> NFR-1/2（新增成本）、NFR-5（可观测定位）、NFR-7（资源）为度量型指标，验收方式=Phase 报告中实测记录（非二值判据）。
