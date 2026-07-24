# Phase 5 阶段报告 — SSRN 与特殊经济学源 adapters（2026-07-24）

> 格式仿 [2026-07-23-phase4-report.md](2026-07-23-phase4-report.md)。**本稿由 T8 收尾撰写**：
> 8 张任务卡（T1/T3/T4/T5/T6/T7/M1，T8 本身为第 8 张）已全部合并，[AC-5 离线端到端汇总验收记录](../testing/records/2026-07-24-ac5-acceptance.md)
> 已由 controller 终验签署（`status: approved`）——本报告引用其已签署结论，不重新独立验证 AC-5.x；
> `tag phase-5` **未打**（T8 职责边界之外，controller 在 opus 全分支终审 + 合并裁决后另打，见 phase5-implementation-plan.md §4 T8 卡定义）。
> 判定依据：[development-plan §Phase 5](../plan/development-plan.md)、
> [phase5-implementation-plan.md](../plan/phase5-implementation-plan.md)、
> [acceptance-criteria AC-5/AC-0](../testing/acceptance-criteria.md)、
> [AC-5 离线端到端汇总验收记录](../testing/records/2026-07-24-ac5-acceptance.md)、
> [decision-log D-027/D-028/D-029](../plan/decision-log.md)。
> 代码版本：`main` @ `a518111`（本报告写作时点；`tag phase-5` 待 T8 件④ 收尾 commit 落地 + 门禁复跑、opus 全分支终审后由 controller 打）。
> `phase-4..a518111` 共 **89 commits / 16 merges**（本报告自身 commit 前的计数，含 T8 件①②两个收尾 commit）；
> 其中 **3 次 merge 是 Phase 4 检查单遗留项**（[phase4-report §6](2026-07-23-phase4-report.md) 检查单 #4/#5/#9/#10，在 Phase 5
> R0 勘察启动前顺带清账：`7a1e571` aaai OAI 全库收割、`1d50790` UNRESOLVED 专项核实（neurips 5 项 + aaai 2 项）、
> `0c9fc2e` 收账四件[D-026 ADR + AC-3 验收记录 + 两项 backlog 登记]）；**其余 13 次 merge 为 Phase 5 8 卡本身**
> （R0 勘察 3 次 + W0 详设双评审 3 次 + 任务卡 7 次：T1/T5/T6/T4/T3/T7/M1，见 §3 逐条对应）。

## 1. 概览

Phase 5「SSRN 与特殊源」8 卡（T1/T3/T4/T5/T6/T7/T8/M1）4 波次（W1 三卡并行 T1+T5+T6 → W2 双发 T3+T4 → W3
T7 → W4 T8，M1 游离全程依 T4）**全交付**，波次并行图（phase5-implementation-plan.md §5）与实际合并顺序
（T1→T5→T6→T4→T3→T7→M1，见上方 blockquote）逐一吻合，零波次外插队。

门禁全量测试从 phase-4 tag 终态的 **2721 passed / 21 skipped** 增至本次 T8 亲跑复现的
**3056 passed / 28 skipped**（**+335 测试**，coverage **98.78%**，`ruff check`/`ruff format --check`/`mypy src`
三项全绿，**EXIT=0**，41.04s，详见 §7 门禁）；较 [AC-5 验收记录](../testing/records/2026-07-24-ac5-acceptance.md)
§3 台账的 `3056 passed, 28 skipped`（该记录在独立 worktree `chore/ac5-acceptance` @ `main` `5111fc0` 时点亲跑，coverage
98.80%）**数字一致、时点不同**——T8 本次是 main 分支合并全部 8 卡（含 T7/M1）后的终态复现，覆盖率 0.02pp
的浮动为正常机器/代码状态差异，非回归。

四个新 adapter 落地：`ssrn`（Crossref 前缀 10.2139 聚合元数据主路径，站点零接触，D-029）、`nber`（前缀 10.3386
枚举 + >18 月开放窗离线全文，D-014 软门不绕过）、`aea`（前缀 10.1257 含摘要 + DOI 双形态 8 刊路由，全文
deferred）、`econsoc`（TE/QE OJS-OAI 自枚举 + ECMA crossref 枚举 + 运行时域名分段路由，D-028）——已注册 adapter
由 **16 增至 20**（`uv run crawler venues lint` 亲跑确认 entry-points 20 个，含测试基建 `mock_platform`）。
`venues/econ/` 新增 13 个 venue YAML（`aer`/`aeri`/`aej_macro`/`aej_micro`/`aej_applied`/`aej_policy`/`jel`/`jep`
八刊·`aea` + `ecma`/`te`/`qe` 三刊·`econsoc` + `ssrn` + `nber`），`crawler venues lint` 本次亲跑
**58 个 venue 全部通过**（45→58，与 T1 §2 冻结件扩展的消费者零回归叠加验证：全部既有 by-ISSN venue，含 aea
8 刊自身与 econsoc ECMA，走原 issn+published 路径不受影响）。`CrossrefAdapter` 完成 T1 两轴参数化枚举扩展
（enum-key `issn` XOR `prefix` + date-field `published`|`created`，本 Phase**唯一动 implemented 冻结件**的改动，
`to_paper_stub`/cursor 契约/限速/UA 逐字复用零改）；wiley 侧同期移除 `10.3982` 前缀路由（D-028，`_WILEY_DOI_PREFIXES`
仅留 10.1111/10.1002）。

AC-5 四条 **PASS** + AC-5.1b **N/A（结构性 defer Phase 6）**：[AC-5 离线端到端汇总验收记录](../testing/records/2026-07-24-ac5-acceptance.md)
（`status: approved`）§1 逐条判定 AC-5.1a（ssrn 元数据三判据）/AC-5.2（nber >18 月）/AC-5.3（econsoc TE/QE）/
AC-5.4（平台归属正确性，含 Phase 5 新增的 aea 8 刊路由 + ECMA 三段路由 + wiley 10.3982 移除不误路由三维度）
均 **PASS（离线）**；AC-5.1b（ssrn 全文层模式 B）**结构性 defer**（D-029 案 B，Phase 5 未声明 `FETCH`，非"验证失败"
而是"本 Phase 结构性不存在该实现"）；该记录 §6 签署栏 controller 终验判定"**达成**"（2026-07-24，"AC-5.1a 三判据
于 main@5111fc0 亲跑 3 passed 复现；AC-5.2/5.3/5.4 判据载体与实跑台账逐条核对通过；AC-5.1b N/A defer Phase 6 与
POM/SODA 既有缺口标注处理均予确认"）。

## 2. 关键决策

三条新 ADR 于 2026-07-24 正式化（[decision-log.md](../plan/decision-log.md) D-027/D-028/D-029），均系 W0 双评审
（A/B 独立实例）通过后由 controller 落账：

- **D-027 · RePEc Phase 5 出列**：R0c 实测（[repec.md](../research/site-survey/repec.md) [LIVE] 2026-07-24，13
  请求）判定 RePEc 是分布式书目聚合器、非全文源，且其 DOI 化条目（NBER 前缀 10.3386 等）与 crossref/openalex
  既有主干重叠增量 ≈0；独家增值（JEL 分类、wp↔published 版本关联、非 DOI 长尾）属 `aggregator-enrich` 性质
  （对齐 aggregators.md 的 openalex/s2 一档），非 `ENUMERATE` 主干。**决策**：Phase 5 不建独立 `repec` pull
  adapter，降级为 enrich 通道候选，挂 **Phase 6 订阅 DSL 富化**评估（见 §6 检查单 #4）。附带事实：SSRN **不在**
  RePEc（Elsevier 商业源，442KB archives 全表无"ssrn"字样），进一步佐证 SSRN 需独立专源、RePEc 补不了这块缺口。
- **D-028 · ECMA 年代分段路由**：R0c 实测（[econometric-society.md](../research/site-survey/econometric-society.md)
  [LIVE] 2026-07-24，26 请求）证伪既有 `wiley/parse.py` 的裸前缀路由假设——`10.3982` 归 **Econometric Society**
  持有（crossref member 2359），ECMA/TE/QE 三刊共用该前缀、仅 DOI 后缀（ECTA/TE/QE）区分，且 ECMA 已**前向
  迁移**（2026 年新刊自营 `econometricsociety.org` 200 + CC BY 4.0；2015 年过刊仍在 `doi.wiley.com`；pre-DOI
  段在 JSTOR）。裸前缀 `10.3982→wiley` 会把 TE/QE（econsoc OA 刊）误路由到 wiley、把当前段自营 ECMA 漏取（大概率
  Wiley TDM no_entitlement）。**决策**：正确路由键＝venue(ISSN)+DOI 后缀+运行时域名（方向 a：resolve 时以
  `doi.org` HEAD 实际落地域名判归属，非硬编码切换年——自校正、不受学会未来继续前移边界影响）；wiley 侧移除
  `10.3982` 路由知识（`_WILEY_DOI_PREFIXES` 仅留 10.1111/10.1002，`test_wiley_parse.py:21,32` 断言同卡翻转）；
  econsoc 承担 ECMA 全部三段判定，过刊段/pre-DOI 段判 `no_entitlement`/skip（跨 adapter 交接给 wiley 显式
  defer，非本 Phase 范围）。
- **D-029 · SSRN 定位修订**（修订 D-011，不 supersede）：R0a 实测（[ssrn.md 站点勘察](../research/site-survey/ssrn.md)
  [LIVE] 2026-07-24）颠覆 D-011 原双模式设想——① SSRN 全库经 Crossref 前缀 10.2139（1.41M DOI）+ OpenAlex（1.63M）
  完整可读，元数据零 SSRN 站点接触即可闭环；② 匿名 HTTP 直连 SSRN 不可行（2026-07-20 Cloudflare 挑战 + 2026-07-24
  本机环境 TLS 阻断，双独立证据）；③ 全文无第三方旁路（unpaywall 对 SSRN 仅 landing）。**决策**：模式 A（聚合
  元数据）升**主路径**（`auth_level=none`）；模式 B（浏览器全文）降 **opt-in 低配额能力**、Phase 5 不点亮，
  与 aea pubs 全文 CF 门、wiley 页面兜底域一并 **defer Phase 6 横切件统一设计**（browser-fetch 通道两案评估，
  ssrn.md §11，controller 已终裁案 B——案 A 因本机环境对 CF 前置域 TLS 层阻断大概率在线验收不可行）。development-plan
  Phase 5 DoD 原文"按 FEN 子网…下载"相应**如实收窄**为"近 7 天新 WP 元数据 + econ/fin 近似过滤"（字面差异不
  静默弱化，AC-5 记录已载明）。

## 3. 交付清单

development-plan §Phase 5 范围逐项：

| 范围项 | 交付 |
|---|---|
| `CrossrefAdapter` 两轴参数化枚举扩展（T1，共享地基·**唯一动 implemented 冻结件**） | `enum-key`（issn XOR prefix）+ date-field（published\|created）两轴；`parse_facet_years` 泛化 `facets.{field}` 取键（原硬绑 `facets.published`）；`to_paper_stub`/cursor 契约/限速/UA/polite pool 零改；既有全部 by-ISSN 消费者（含 aea 8 刊、econsoc ECMA）零回归。合并时点零回归验证 **2740 passed / 21 skipped** |
| `ssrn` adapter（T4） | `adapters/ssrn/{adapter,parse}.py`：`DISCOVER` 纯生成年桶（zero-network，controller 发现①仲裁令：真实 Crossref `facet=created:*` 400 后改案）+ `ENUMERATE` 委 T1 扩展（prefix 10.2139+created）+ 后处理 DOI→abstract_id 正则增补 identifier + `RESOLVE` landing-only（零网络，恒空 asset plan，PDF 交 unpaywall OA-fallback）；无 `FETCH`；`venues/econ/ssrn.yaml` 单一 venue + `quirks.topic_filter` econ/fin 近似过滤 |
| `nber` adapter（T3） | `adapters/nber/{adapter,parse}.py`：`ENUMERATE` 委 T1 扩展（prefix 10.3386+published）；`RESOLVE|FETCH`——18 月窗谓词（假时钟跨边界断言）+ `%PDF` 魔数双守卫（软门非 PDF→`no_entitlement` 非 integrity，绝不重试/换 IP/走软门）；`www`/`back.nber.org` 独立限速桶（1req/5s、1req/10s，`back` 不进 domains alias 防错享宽松预算）；`venues/econ/nber.yaml` |
| `aea` adapter（T5） | `adapters/aea/{adapter,parse}.py`：`RESOLVE`（offline）——DOI 双形态容错解析（submission/vol_issue_page/pnp）+ code→venue 8 刊路由表；`ENUMERATE` 委 crossref 标准 ISSN 路径（不触 T1 prefix 扩展）；`FETCH` 本 Phase 不声明（全文域 `pubs.aeaweb.org` 全域 CF challenge，连 JEP OA 亦然）；`venues/econ/{aer,aeri,aej_macro,aej_micro,aej_applied,aej_policy,jel,jep}.yaml` 8 刊 |
| `econsoc` adapter（T6，含 wiley 联动） | `adapters/econsoc/{adapter,parse}.py`：`DISCOVER\|ENUMERATE\|RESOLVE\|FETCH` 四位，venue 非对称分工（TE/QE 全四位走自持 OJS OAI-PMH；ECMA 只行使 RESOLVE\|FETCH，enumerate 委 crossref）；`_oai.py` 第三消费者（零改 arxiv/aaai_ojs 共享信封）；ECMA 运行时域名三段路由（方向 a）；`venues/econ/{ecma,te,qe}.yaml`；**同卡联动**：`wiley/parse.py` 移除 `10.3982`（D-028） |
| AC-5 正式化 + 离线端到端验收（T7） | `acceptance-criteria.md` AC-5.x 转正（草案→正式，字面收窄如实公开）；[AC-5 离线端到端汇总验收记录](../testing/records/2026-07-24-ac5-acceptance.md)：四条 PASS + 5.1b N/A defer，具名判据 51 例 + 全套件补证 434 例、17 文件合并会话 434 passed/0 failed，`make check` 独立复现 3056 passed/28 skipped/EXIT=0 |
| SSRN 覆盖率量化 census（M1，游离在线） | OpenAlex source `S4210172589` 代理采样 N=1000（95%±3% CI）：DOI 非空率 **869/1000 = 86.9%**（[ssrn.md §9.1](../design/adapters/ssrn.md) [LIVE 2026-07-24]，独立脚本 httpx 非 CI）；<90% 阈值触发候补阶梯**记录**（不执行，见 §6 检查单 #1）；同批捎带 aea 4 刊 ISSN `[DOC]→[LIVE]` 转正 + ssrn healthcheck golden 转正 |
| 收尾（T8，本报告） | 四详设 `{ssrn,nber,aea,econsoc}.md` → `implemented`；catalog 13 venue `supported_since: phase-5` 标注；两处遗留清理（aea.md 孤立尾行、wiley_runbook ECMA 注记）；本报告；INDEX/progress 同步；`make check` 终态复现 |

**commit 统计**（详见 blockquote）：`phase-4..a518111` 共 89 commits / 16 merges，其中 Phase 5 8 卡本身对应
13 次 merge——R0 勘察 3 次（`74ef017` ssrn、`96ef374` nber+aea、`eb3ed9b` econsoc+repec，均 [LIVE 2026-07-24]）→
W0 详设双评审 3 次（`ed0a7f7` ssrn、`ce85420` nber+aea、`ad4c860` econsoc+wiley 联动，均 Approve-with-fixes→
修订闭合→approved）→ 任务卡 7 次（`03efc06` T1 / `23cb5ac` T5 / `7024a1f` T6 / `f914f18` T4 / `5111fc0` T3 /
`fa4b95f` T7 / `7520969` M1）；`git diff --shortstat phase-4..a518111` = **118 files changed, +10846 / -204**
（含 T8 本报告之前的两个收尾 commit，未含本报告自身与件④）。测试轨迹三点复核（合并时点亲跑数字，非事后推算）：
T1 合并 **2740/21** → T5 合并 **2810/25** → T6 合并 **2921/25** → T7/M1 全部合并后终态 **3056/28**。

## 4. 事件与教训

- **① T1 在线冒烟遇 spec-vs-reality 偏差，最早期拦截设计假设**：T1 committed 在线预算 ≤5 请求（`tests/online/test_crossref_prefix_smoke.py`），
  实耗 3 请求（works PASS / published-facet PASS / **created-facet 探测 HTTP 400**）。ssrn.md 原设计假设"1 请求
  `facet=created:*` 产年桶计数"，实测 Crossref **不支持** `created` facet（`CONFIG` 错误，非"暂时故障"）——该
  用例现以 `pytest.mark.xfail`（reason 内联注明，日后 Crossref 若新增该 facet 则 XPASS 提示复核）作**活体哨兵**
  存档，而非静默吞掉。controller 发现①仲裁：`discover_timeline` 改**纯本地生成**年桶（1990..今年，clock 注入
  上界，`paper_count_claimed=None`，规模锚移交 M1 census）。这是一次仅 3 个真实请求、发生在实现最早期（T1
  地基卡）就拦截"详设 §4.3 原方案不可实现"的实证案例——小预算在线冒烟的价值不在数据量，在**尽早**把文档假设
  摆到真实 API 面前验证。
- **② SSRN census 实测 86.9% 低于 90% 阈值，如实记录候补阶梯未执行**：M1 以 OpenAlex `S4210172589` 为代理
  采样 N=1000，DOI 非空率 **869/1000 = 86.9%**（首阶估计 1.41M/1.63M≈87% 与本次随机采样高度吻合，交叉验证
  合理）；`ssrn.md` §9.1 预定阈值 90%，86.9% **未达标**，触发候补阶梯——(a) OpenAlex 补枚举无-DOI works（该
  能力已收回 `ENUMERATE`+信用计费，需重评）、(b) RePEc/NBER 交叉核对、(c) 有限度 SSRN 浏览页 census（触
  Cloudflare，红线下降级/可选，默认不启用）。本次**仅完成"触发"侧的忠实记录**，三条候补路径均未执行/未评估
  优先级——如实量化边界而非粉饰达标，留给 Phase 6 定夺（见 §6 检查单 #1）。
- **③ 独立审查两次拦住真实缺口，一次确立可复用判例**：
  - **T6 F1（econsoc 审查 Approve-with-fixes）**：发现 ECMA 当前段落地页 404/410 原判 `GONE`（终态，代表
    "存在过又消失"），但生产 resolve 中 crossref 无落地域信号时乐观归当前段、实际由 Wiley 托管过刊——GONE
    会是误终态（污染合并引擎存在性判断）。修复：仅 ECMA 当前段分支的 404/410 改判 `no_entitlement`（触发
    OA-fallback，不误伤 TE/QE 自持记录的 GONE 权威性，`test_resolve_ecma_current_404_remapped_to_no_entitlement`
    对照 `test_resolve_te_landing_404_stays_gone`）。
  - **T5 MINOR①（aea 审查）**：发现 aea.md §3.2"OA 刊（jep/jel）全文…亦转 OA-fallback"的表述与本文档 §3.4
    已确立的结论（"OA-fallback 对 AEA 实质产出 ≈0"，gold 副本同样落在 CF 挡的 `pubs.aeaweb.org` 域）**内部
    不一致**——controller 裁定该分句"按现实校准废止"（`82d74a1`，保留原文 + 追加裁定注记，不删除，明示"此
    路径无实际损失"，如实存档而非静默改写）。
  - **T4（ssrn 审查）确立"landing-only vs 产 asset"两类 RESOLVE 契约判例**：共享契约测试
    `test_resolve_yields_nonempty_asset_plans` 原假设一切声明 `RESOLVE` 的 adapter 均产 ≥1 可下载
    asset plan；ssrn 的 landing-only 语义（PDF 交 OA-fallback、resolve 恒返回 `[]`）与此冲突。审查未选择
    "放宽契约"（会掩盖其余 adapter 的真实 bug），而是新增 `_LANDING_ONLY_RESOLVE` 白名单分层断言——白名单内
    走"恒空"分支、白名单外维持"≥1 plan"强断言，源码注释明示"此非放宽契约：是契约对两类 RESOLVE 的正确分层
    表述"。这是一个可复用的判例：共享契约测试遇到"合法但反直觉的空结果"新场景时，用**显式分层**而非**全局
    放宽**来吸收差异。
- **④ 连续网络故障波下的应对**（controller 直接记录，T8 未在 repo 内独立复核到痕迹）：本 Phase 执行期间
  controller 观察到连续多起 subagent 会话遭遇网络层连接重置（工具调用中断），应对策略是**缩小单次派发的
  任务粒度 + 更频繁的增量落盘**（每个子步骤独立 commit，而非攒大改动一次性提交）——这与本项目既有的"增量
  commit 纪律"（memory 条目「编排纪律：分支卫生」同源）在本 Phase 高故障率窗口下被进一步强化验证。此项
  依据 controller 亲历记录入档（如实标注证据来源，同 phase4-report §4"filter-branch 安全事件"处理口径：
  controller 一手记录、T8 转录存档、不代为独立复现取证）。
- **⑤ controller 路径派发误引未经核实的目录名，跨卡传染前发现**（controller 直接记录）：orchestrator 在向
  某任务卡下达文件路径指令时一度写成不存在的 `venues/econ_fin/` 目录（本仓库实际是 `venues/econ/` 与
  `venues/finance/` 两个并列目录，无合并目录），所幸在扩散到多张任务卡前被发现纠正——本仓库 git 历史内未
  留下该错误路径的提交痕迹（各任务卡实际写入的文件路径全部是 `venues/econ/*.yaml`，与 §3 交付清单一致）。
  教训：controller 向 subagent 下达路径类指令前，应先用只读命令核实仓库当前实际目录结构，而非凭记忆/推断
  拼装路径名——尤其在多卡并行派发场景下，一个错误路径若不早发现，可能被多个 subagent 各自"纠正性重新发明"
  出不一致的应对方式。此项同样是 controller 亲历记录，T8 未能从 repo 内证据独立复核（符合预期：路径指令
  的纠正发生在派发对话内，不必然留下 commit 级痕迹）。

## 5. 已知限制（如实记录）

- **ssrn 全文层（模式 B）defer**：D-029 案 B，Phase 5 `ssrn.capabilities()` 不含 `FETCH`；[AC-5 记录](../testing/records/2026-07-24-ac5-acceptance.md)
  §1 AC-5.1b 标注"结构性不存在该实现"，非"验证失败"。browser-fetch 横切件统一设计 defer Phase 6（见 §6 检查单 #2）。
- **aea 全文域 stateless 零产出**：`pubs.aeaweb.org` 全域 Cloudflare challenge（连 gold OA 的 JEP 亦不可达），
  `FETCH` 本 Phase 不声明；OA-fallback（unpaywall）对 aea 实质产出 ≈0（gold 副本同样落 CF 域，aea.md §3.4）——
  订阅版全文现实兜底是跨源 WP（NBER/SSRN，D-007 合并），非 unpaywall。
- **ECMA 过刊运行期终态待在线验证**（`econsoc.md` [UNRESOLVED④]，T6 审查 F1 移交，2026-07-24）：生产 resolve
  中 crossref 缺 `primary_url_domain` 信号时 ECMA 过刊 DOI 恒乐观归当前段、GET 自营域，当前段 404/410 已加固
  改判 `no_entitlement`（F1）；但 `econometricsociety.org` 对过刊 DOI 的真实响应（究竟 404 / 302→Wiley / 其它）
  与"是否将 `doi.org` HEAD 权威域名检查 wire 进生产 resolve"两项**仍待在线闭合**，登记为 ECMA 投产前收口项
  （不阻塞 TE/QE 主路径）。
- **POM/SODA 正向路由待 sage/siam 落地**（AC-5 记录 §1 AC-5.4 节核查中意外发现，早于 Phase 5 的既有缺口）：
  `sage`/`siam` adapter 在 `docs/design/adapters/README.md` 登记为 `planned`（待建），代码库无对应实现、无
  venue YAML 引用——"POM 走 SAGE / SODA 走 SIAM"判据当前结构性不可测（验证对象不存在，非"未变更"）。不影响
  本 Phase AC-5.4 PASS 判定（完全由 Phase 5 新增的 aea/ECMA/wiley 路由维度独立支撑），如实登记供后续处置
  （见 §6 检查单 #8）。
- **环境 Cloudflare 选择性阻断影响在线验收面**：ssrn 域＝本机 TLS 层阻断（元数据层零 SSRN 接触故不受影响）；
  econsoc 域＝实测可达；`pubs.aeaweb.org`＝**站点** CF 判罚 BLOCKED（区别于环境障碍，robots/TLS 本身 OK）。
  三者性质不同、已在各自设计文档内严格甄别（phase5-implementation-plan.md §3），不构成事实冲突，但共同
  限制了本 Phase 能达成的在线验收覆盖面。
- **`economics-journals.md` Top 5 表 ECMA 行 adapter 字段未随 D-028 同步更新**（T8 本次核查中发现，超出本次
  收尾任务窄范围、未修改，如实登记）：该表第 17 行仍写 `` `wiley` ``，但 D-028 已裁定 ECMA 现由 `econsoc`
  经运行时域名分段路由服务（wiley 仅覆盖过刊段、且 wiley 侧已不持有 `10.3982` 路由知识）；对照
  `publishers-platforms.md`（同一 catalog 目录下的平台映射总表）第 32/72 行**已经**正确反映"econsoc 服务
  ECMA(部分)"——即两处 catalog 文件对同一事实的描述现不一致。本次 T8 仅在该行补 `supported_since: phase-5`
  标注（事实上为真，与 adapter 字段是否准确正交），未一并改写 adapter 归属字段（改写涉及是否需要在同一行
  内同时体现"当前段 econsoc / 过刊段 wiley"的分段语义，判断空间较大，超出"标注惯例同步"这一窄任务的授权
  范围）——已用 `spawn_task` 登记为独立待办供后续处理。

## 6. Phase 6 开工检查单

1. **ssrn 覆盖候补阶梯评估**（M1 census 86.9% < 90% 阈值，§4 事件②）：candidate ladder 三条路径——(a)
   OpenAlex 补枚举无-DOI works（需重评该能力的 `ENUMERATE` 收回与信用计费约束）**优先评估**、(b) RePEc/NBER
   交叉核对（可与检查单 #4 repec enrich 评估合并考虑）、(c) 有限度 SSRN 浏览页 census（触 Cloudflare，红线
   下降级/可选，非默认路径）。ssrn.md §9.1 为完整依据出处。
2. **browser-fetch 横切件设计落地**（D-029 案 B defer；三个消费方 ssrn 模式 B / aea pubs CF 全文 / wiley
   deferred 页面兜底域共需，统一设计避免逐 adapter 重复）：[ssrn.md §11](../design/adapters/ssrn.md) 已留设计
   种子（案 A/B 两案评估 + 关键评估维度），Phase 6 需在此基础上出正式详设，含 `ChallengeDetector`/BLOCKED/
   预算护栏离线逻辑与实际浏览器上下文取回的接线。
3. **nber RSS watch 转主**（[nber.md §3.5](../design/adapters/nber.md)）：Phase 5 `DISCOVER` 经 program RSS
   `back.nber.org/rss/new{code}.xml`（19 feed）表达为可选增量通道；Phase 6 订阅/`crawler watch` 落地时转为
   主通道。
4. **repec enrich 通道评估**（D-027）：独家增值＝JEL 分类（crossref/openalex/nber.org 三路皆缺）+
   wp↔published 版本关联（服务 D-007，如 `nbr:nberwo:3210`→"Published in" Oxford Economic Papers 的 [LIVE]
   用例）；定位建议 `role: aggregator-enrich`，duck-typed `enrich_batch(dois)`，产 `(repec, handle)` 非跨源
   合并锚点、字段级只补不覆盖；收割走 bulk ReDIF/OAI、零 HTML。挂 Phase 6 订阅 DSL 富化评估。
5. **econsoc 在线闭合批**：[UNRESOLVED①]（当前 ECMA 是否全刊 OA，HEAD 一篇判定）、[UNRESOLVED②]（Wiley→自营
   切换日，仅方向 b pre-filter 需要，方向 a 主路径不依赖）、[UNRESOLVED④]（ECMA 过刊运行期终态在线验证，
   §5 已详述，**ECMA 投产前**收口）；顺带 TE/QE `volume_map` 锚定核实（TE completeListSize 656 vs crossref
   735 差额对账，[UNRESOLVED③]，DOI 后缀过滤 + `identifier('doi')` 去重已使两源自然收敛，非阻塞但值得
   查清成因）。
6. **aaai A⑥⑦ 重跑**（既有任务卡 #57，`ojs.aaai.org` 恢复后 ≤6 请求）：跨阶段遗留的独立小项，与 Phase 5
   四源无关联，随本检查单一并登记以防再次遗漏。
7. **P4-T7b elsevier key 冒烟**（跨 Phase 遗留，等用户；见 [phase4-report §6](2026-07-23-phase4-report.md) #1/#2）
   **+ wiley token 可选**：elsevier API key 为 BLOCKER-1（外部依赖，跨 Phase 3/4/5 三阶段仍未到位）；wiley
   TDM token 自助可得（click-through 无需审批），到位后可执行 [wiley_runbook.md](../../tests/manual/wiley_runbook.md)
   （本次 T8 已在该文档补 ECMA DOI 选取注记，见 §3 交付清单）。
8. **POM/SODA 正向路由随 sage/siam 落地验证**（§5 已知限制新发现的既有缺口）：`sage`/`siam` adapter 目前
   `planned` 未实现，AC-5.4"POM 走 SAGE / SODA 走 SIAM"正向路由判据待二者任一落地后补验；建议与两 adapter
   的实现任务卡合并考虑，而非单独起验收批次。
9. **aea 全文 / 机构认证 deferred 项**：全文域 pubs 全域 CF challenge、D-006 CookieSession 机构订阅认证
   留将来实现——待 browser-fetch 通道（检查单 #2）+ auth 落地时立专属 AC（类比 AC-4.1 单篇 / AC-4.3
   no_entitlement 降级的验收形态）。aea 剩余 2 刊（`aeri`/`jel`）ISSN 仍 `[DOC]`未升 `[LIVE]`（M1 本批仅转正
   4 刊，`aej_macro`/`aej_micro`/`aej_applied`/`aej_policy`），`test_aea_smoke.py` 对应断言已写未跑，可与
   本项同批核实。
10. **ssrn `topic_filter` 接线**（P6 Selector 下推）：`venues/econ/ssrn.yaml` 的 `quirks.topic_filter`
    econ/fin 近似过滤当前为静态声明，尚未接入订阅侧 `Selector.filter_expr` 下推逻辑（DSL 落地时一并设计，
    ssrn.md §1 已预留接缝）。

主体范围锚点：development-plan.md「Phase 6 — 订阅与搜索」（topic/tag 订阅 DSL、`crawler watch` 增量调度、
dry-run 计数预览、数量护栏、每日摘要报告）。

## 7. 门禁

`make check`（`sync-dev` + `ruff check` + `ruff format --check` + `mypy src` +
`pytest tests/unit tests/contract tests/integration --cov=paper_crawler --cov-fail-under=80`）T8 本次亲跑：

```
3056 passed, 28 skipped, 27 warnings in 41.04s
Required test coverage of 80% reached. Total coverage: 98.78%
EXIT=0
```

ruff/mypy 均无输出（全绿）；与 [AC-5 记录](../testing/records/2026-07-24-ac5-acceptance.md) §3 台账数字一致
（时点不同，见 §1 说明）。

## 8. 签署

- **T8 初判（2026-07-24）**：8 卡 4 波次全交付，实际合并顺序与波次并行图吻合；门禁 2721→3056（+335 测试，
  +7 skip，coverage 98.78%，EXIT=0）；adapter 16→20（+4）、venue 45→58（+13）；AC-5 四条 PASS + 5.1b N/A
  defer（controller 已终验签署"达成"，本报告引用而非重新判定）；D-027/D-028/D-029 三条新 ADR 已正式化；
  四详设本次转 `implemented`；两处遗留清理（aea.md 孤立尾行、wiley_runbook ECMA 注记）已闭合；一处新发现
  的既有 catalog 不一致（economics-journals.md ECMA 行 adapter 字段）已如实登记、未越权修改，已用 `spawn_task`
  移交独立待办。
- **最终判定**：Phase 5 判定：待终审。
