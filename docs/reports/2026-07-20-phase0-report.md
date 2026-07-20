# Phase 0 阶段报告 — 设计与文本系统

> 日期：2026-07-20 · 责任：fable5（主设计）+ Sonnet subagent（调研）
> 对应计划：[development-plan.md](../plan/development-plan.md) Phase 0 · 执行留痕：[logs/session-001](../logs/2026-07-20-session-001.md)、[logs/session-002](../logs/2026-07-20-session-002.md)

## 1. 目标回顾

建立完整的文本系统（docs-as-code）并完成全部设计文档，达到"任何一个模块可以按文档独立开工"的程度；同时完成四域 venue 清单、站点勘察、同类项目调研、流程规范与 AI 协作规范。

## 2. 交付清单与状态（对照 Phase 0 DoD）

| 交付项 | 计划 | 实际 | 状态 |
|---|---|---|---|
| 文本系统目录 + git 仓库 | ✓ | docs/{plan,design,catalog,testing,process,research,diagrams,logs,reports} | **完成** |
| plan/ 三篇 | ✓ | development-plan、progress、decision-log（D-001…D-014） | **完成（approved）** |
| design/ 00–09 十篇 | ✓ | 全部 | **完成（approved）** |
| adapters/ 模板 + ≥12 篇详设 | ≥12 | 模板 + **16 篇**（OA 9 + aggregator 合册 + auth 6） | **完成（review）** |
| catalog/ 7 篇 | 7 | **8 篇**（含 README；四域+平台+预印本全覆盖） | **完成** |
| testing/ 两篇 | ✓ | test-plan（T1–T6）、acceptance-criteria（AC-0…AC-8） | **完成（approved）** |
| process/ 三篇 | ✓ | git-workflow、status-workflow、doc-conventions | **完成（approved）** |
| diagrams/ 6 张 SVG | 6 | 6 张（xmllint 全过；01 号经浏览器渲染验证） | **完成** |
| research/ 调研归档 | ✓ | **9 篇**（站点勘察 8 + GitHub 同类项目 1） | **完成** |
| AGENTS.md / README / INDEX | ✓ | 全部；INDEX 与文件树对账一致 | **完成** |
| git 初始提交 | ✓ | session-002 末执行（见 §5） | **完成** |

**DoD 判定：达成**——INDEX 内所有文档 ≥ review；核心十篇+流程三篇 approved；SVG 与文档交叉引用一致；初始提交完成。

## 3. 关键设计结论（一页速览）

- **双模块**：open_access 与 auth_gated 共享同一 `SourceAdapter` 协议（D-003），差异只在能力声明与 fetcher/auth 绑定；
- **可插拔**：PlatformAdapter（代码，~37 个）× VenueSpec（YAML，数百条）两层（D-002）——新增同平台期刊 ≤30 分钟；
- **Pipeline**：discover→enumerate→resolve→fetch→extract→ingest 六阶段幂等（D-004），清单先行下载置后（支持 dry-run 与精确选择）；
- **元数据主干走聚合 API**（D-005 修订）：期刊=Crossref、会议=DBLP；出版社站点只承担全文（勘察证实其反爬现实使此为唯一可行架构）；
- **认证**：人在回路首登 + storage_state 复用 + 绝不对抗风控（D-006）；四种 AuthProvider；
- **合规**（D-014 + AC-0）：诚实 UA、遵守 robots/TDM 信号、不碰盗版源与 CAPTCHA、凭证不入库、下载仅个人科研。

## 4. 调研亮点与勘误（影响设计的事实）

1. **出版社平台格局实测**（9 平台）：Elsevier API 配额官方数字齐备（Article API 50k/周、TDM key 不限量）→ API 路线可行性确认；UChicago=Atypon 确认（epdf 无静态直链→browser 出口）；SIAM=Atypon、SODA=book 结构；REStat=MIT Press 确认且其 TDM **明文禁脚本抓取**（获取边界=按需单篇）；JSTOR=PerimeterX+点名禁 ClaudeBot+Constellate 已停运；Cambridge issue ID 不透明；JEP 全刊免费。
2. **AI 期刊/预印本核验勘误**：arXiv q-fin 实为 9 子类（补 q-fin.EC）；NEP 的 nep-fin 已停更（活跃代码以 nep-fmk 等替代）；TASLP 未并入 OJSP；CACM 2024-02 先于全站 OA；TACL=MIT Press 出版+Anthology 免费镜像；JAIR 属 AI Access Foundation。
3. **GitHub 20 项目横向**：能力 mixin/manifest 注册/生产级重试（openreview-py、findpapers 可直接参照）/缓存与多 key 配额池（pybliometrics）——均印证既有设计；**增量订阅无教科书级开源实现**→ design/09 自研路线确认为差异化价值点。

## 5. 偏差与原因

- session-001 结束时未写日志、progress 中"git 初始提交"记录先于事实——已在 session-002 补记并修正（流程教训：AGENTS.md §4 义务应在 session 内闭环）；
- 两个调研 subagent 因 API 连接中断失败，重试+缩小范围后完成——教训：**大范围调研任务应从一开始切小、限制输出体量**（已写入日志）；
- INFORMS/Springer 的 robots/TDM 明文条目因云 IP 拒连未能直接抓取（网络层现实本身已是设计输入）——列入实现期首次登录态勘察补项。

## 6. 风险更新（对照 development-plan §风险登记）

- R1（反爬升级）：**证据增强**——Elsevier 深集成 CF、JSTOR PerimeterX；缓解不变（API 优先+保守限速+BLOCKED）；
- R2（SSO/MFA）：不变；
- R3（站点漂移）：新增证据（ACM 双卷/PACMMOD 等结构性改版频发）——fixture+canary 体系按计划；
- **新增 R6：外部依赖申请周期**——Elsevier API key、Wiley TDM token、IEEE API（人工审批）、S2 key 均需申请，Phase 3/4 开工前 1–2 周提交（已写入相应 adapter 文档 §7）；
- **新增 R7：条款敏感平台**——MIT Press（禁脚本）、CEPR/JSTOR（点名禁 AI bot）按 D-014 白名单式最小获取执行，catalog 已标注获取边界。

## 7. 下阶段建议（Phase 1 开工清单）

1. 按 [development-plan §Phase 1](../plan/development-plan.md) 搭核心框架（mock adapter 驱动，无真实站点）；
2. 先行外部申请（并行无阻塞）：Elsevier dev key、S2 key、Kaggle 账号；
3. adapter 详设 16 篇的 review→approved 评审批次化处理（每平台开工前完成该篇评审即可，不必一次全过）；
4. 实现期首批核验清单（各 adapter §7 已标注）：AAAI OJS 的 OAI-PMH 与 archive 分页、ECCV 的 CVF 新格式路径、jair print ISSN、INFORMS/Springer 登录态 robots 补勘察。
