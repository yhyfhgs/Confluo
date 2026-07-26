---
title: Phase 7 实施计划 — 全文抽取与库增强
status: approved
updated: 2026-07-27
owner: fable (advisor/controller)
---

# Phase 7 实施计划 — 全文抽取与库增强

**依据**:[development-plan](development-plan.md) Phase 7 定义(GROBID 可选集成、全文倒排/向量索引(可选)、
candidate_duplicate 审核 CLI、preprint↔published 关联报告;DoD=AC-7.x+全库一致性校验工具)+
[phase6-report §6](../reports/2026-07-26-phase6-report.md) 开工检查单 16 项处置(逐项裁决见 §4/§8)+
[acceptance-criteria AC-7](../testing/acceptance-criteria.md) 四条。

**开工基线**:main @ d56313f(fan-out 修复卡已合并),门禁 3832 passed / 28 skipped / 98.99% / EXIT=0
(2026-07-27 controller 亲跑)。

## §1 Global Constraints(每个任务隐含继承)

1. **AC-0 五条红线**([acceptance-criteria](../testing/acceptance-criteria.md))全程有效:无付费墙绕过/
   CAPTCHA 求解、无盗版源、robots+ToS 遵守、凭证不入 git、无再分发功能。
2. **门禁**:每卡合并前 `make check` 全绿(ruff + mypy + pytest cov≥80%);基线 3832/28/98.99%(见上)。
3. **离线优先**:单元/契约/集成测试零网络(socket 猴补看守既有);在线动作只在 §3 专项批内。
4. **分支纪律**([git-workflow](../process/git-workflow.md)):一卡一分支一 agent;执行 agent 在隔离
   worktree 内工作并提交到卡分支;合并由 controller(fable)在主仓库执行——冲突面先到先合,后者 rebase。
   **subagent 禁一切破坏性 git(filter-branch/reset 他人提交/clean);禁 push;禁动主仓库工作树。**
5. **提交规范**:conventional commits + Co-Authored-By 尾行;文档改动同步 INDEX/front matter `updated`。
6. **Subagent 输出纪律**:执行 agent 返回文本仅报告"分支名 + 提交 hash + 测试结果 + 偏离清单 + 接缝表";
   不粘贴大段代码。审查 agent 返回结构化发现(P0/P1/P2 分级 + 逐条文件:行号)。
7. **设计边界**:实现只依据 approved+ 文档(design/11 已 approved;D-033/034/035 由 W0 产出并经 fable
   签署后生效)。执行中发现设计歧义→停手上报 fable 仲裁;各卡"已裁决歧义"段已预清一批。
8. **config-home 红线**(D-032):config-home 在仓库根 `.paper-crawler/`(gitignored,含凭证与 DB)——
   **禁裸 `git clean -fdx`**;任何涉及 state/ 的新文件走 `config.resolve_home()`,禁 `Path.home()` 硬编码。

## §2 接口冻结件(Phase 7 增量;落盘即冻结,改动须 fable 仲裁)

| 冻结件 | 内容 | 产出卡 | 消费方 |
|---|---|---|---|
| D-033 extract 语义 | `TextExtractor` Protocol、stage 5 幂等键 paper 级→asset 级、`fulltext.text_path` 落盘契约、GROBID 开/关降级链 | T1 | T7/T12/T14/T19 |
| D-034 FTS5 决策 | title+abstract 索引范围、`0004_*.sql` 迁移形态、rebuild 策略、D-017 修订(PG 路径关系) | T2 | T12 |
| D-035 repec 接入 | `SOURCE_PRIORITY` 扩位(D-021 修订)、`_ENRICH_SOURCES` 接入形态、`state/repec/` bulk 快照契约、DOI↔handle 映射边界(仅 NBER) | T2 | T8 |
| `browserfetch.BrowserFetchHandle` | Protocol(goto/download_via/close)+`fetch_one` 纯函数签名+config 4 槽 | T6 | T11/T19 |
| 参数化谓词签名 | `PREDICATE_REGISTRY` 构造器形态 + `PlanStep` 参数承载 | T9 | (subs 链全体后续) |
| dedupe 聚合语义 | `same_as(decided=merged)` 在 `list_papers` 等查询层的合并显示规则 | T13 | T14/T16 |
| 既有冻结件 | `types.PaperStub`/`AdapterBase`/`errors` 层级/退出码契约/subs 包 Phase 6 冻结件——**不动**;动走仲裁 | — | 全部 |

## §3 在线预算分项表(全 Phase 专项行 ≤40 请求;超支入档;消费前核对 T4 账本)

| 批次 | 内容 | 预算 |
|---|---|---|
| T8-robots | repec 两域(`www2.nber.org`/`repec.nber.org`)robots 核验(探针遗留) | ≤2 |
| T8-bulk | repec bulk ReDIF 快照首拉(NBER 面) | ≤4 |
| T19-bf | browser-fetch 真实冒烟(三消费方各至多 3) | ≤10 |
| T19-nber | 检查单 #11:nber 隔离在线验证 + `asset-pricing` preset CLI 端到端(ssrn 7 页+arxiv 1+nber RSS 1) | ≤9 |
| 机动 | 突发复核(消费前查 `state/budget.json` 账本,T4 起) | ≤10 |

GROBID 为本地服务,零外网请求;真实 GROBID 冒烟列为 T19 条件项(本机可用才跑,不占在线预算)。

## §4 任务卡

### W0 波次(无相互依赖,即刻并行)

**T1【Opus/Opus 审】D-033 全文抽取详设 + ADR**(纯设计卡,不写实现)
- 产出:`docs/design/12-fulltext-extract.md`(新)+ decision-log **D-033** + 接口冻结件清单落 §2。
- 必须裁决:①`TextExtractor` Protocol(输入 asset 路径/输出文本+元信息);②纯文本基线抽取器选型
  (候选 pypdf/pdfminer.six,给依赖体积与纯度论证);③GROBID 可选接线=对本地 REST 服务的 httpx 调用
  (零新 SDK),`[extract] grobid_url` config 槽,down→纯文本降级不报错(AC-7.2);④stage 5 幂等键
  paper 级→asset 级语义迁移(现状 stages.py:715-746 noop、PK=paper_id;设计注记"asset 级键随 Phase 7
  启用"),含重跑/断点语义与 `_asset_final_path` 扩 fulltext kind;⑤失败态(`extract_failed`)与
  ingest_state 机;⑥落盘布局沿 design/06:167-172(`data/fulltext/{venue}/{year}/{ulid}.txt|.tei.xml`)。
- 已裁决歧义:纯文本是基线路径、GROBID 是可选增强(AC-7.2 语义,controller 定);正文入 DB **否决**
  (只落文件+`text_path`,FTS 见 D-034)。

**T2【Opus/Opus 审】D-034 FTS5 + D-035 repec 接入双 ADR**(纯设计卡)
- 产出:decision-log **D-034**、**D-035** 两条 + `docs/design/06-data-model.md` 索引节增补 +
  enrich 设计增补(落 `docs/research/enrich-eval-p6.md` 附录或 design 侧,agent 依 doc-conventions 定)。
- D-034 必须裁决:FTS5 范围=**title+abstract 二字段**(controller 已裁,正文索引 defer 见 §8);
  external-content vs contentless 形态;`0004_fts_title.sql` 迁移+rebuild 命令形态;D-017"不用 FTS5"
  原则修订(债务承认+PG 迁移路径替代论证)。
- D-035 必须裁决:`SOURCE_PRIORITY` 6 源闭表(D-021)扩位 repec 的位次;接入形态=`_ENRICH_SOURCES`
  元组扩位(最小改)vs registry role 声明式(controller 预裁:**P7 走元组扩位**,role 声明式挂 P8 评估);
  `state/repec/` bulk 快照落盘契约(零网络 enrich:快照→本地 join);`enrich_batch(dois)` duck-type
  与在线源语义差异的契约表述。
- 已裁决歧义:两 ADR 同卡防 decision-log 并发冲突;repec 可寻址集合仅 NBER ~3.6 万 WP(SSRN 结构性
  为 0)如实入档。

**T3【Sonnet/Sonnet 审】E-2 冷却键统一 + `cooldown` CLI**(检查单 #7)
- 冷却读写逻辑自 `pipeline/runner.py:576-697` 抽为 `pipeline/cooldown.py` 公用模块(CLI 进程无常驻
  runner);新 `crawler cooldown status|clear` 子命令组(仿 `auth/cli.py` 的 add_typer 模式);
  `status` 扫 `state/cooldown/` 目录列全部键+剩余窗;`clear` 支持按键/全量。
- 已裁决歧义:E-1 的"新键=域名/旧键=adapter_id 兼容读"设计**保留不破坏**(是有意设计非 bug);
  旧键存量文件不做迁移,`status` 如实列出两形态;E-2"全量统一"到此程度即闭合,更深重构不做(YAGNI)。

**T4【Sonnet/Sonnet 审】机动预算运行时账本**(检查单 #16)
- `.paper-crawler/state/budget.json` 单文件计数器(共享预算行→累计消耗+会话戳数组);读写小工具
  `scripts/budget_ledger.py`(不入 src 包/不占门禁覆盖,先例=scripts/ 既有);新
  `docs/process/online-budget.md` 规范条款:消费共享行前必读账本、消费后必记、超线入档。
- 已裁决歧义:不进 src/paper_crawler(编排流程工具非爬虫功能);本 Phase §3 预算行自此账本起记。

**T5【Sonnet/Sonnet 审】文档微清账**(检查单 #12+#15,纯文档卡)
- #12:`docs/catalog/economics-journals.md` `aej_macro`/`aej_micro`/`aej_applied`/`aej_policy` 四行
  备注列补 `[LIVE 2026-07-26] crossref 核实` 注记(与 `aeri`/`jel` 两行同批同格式)。
- #15:ECMA 行 adapter 归属表述统一——`economics-journals.md` ecma 行与 `publishers-platforms.md`
  econsoc 行,统一为分段列举范式"econsoc(当前段自营 OA)/wiley(过刊段,D-028)"(controller 已裁)。
- INDEX front matter `updated` 同步。

**T6【Opus/Opus 审】browser-fetch 横切件核心**(检查单 #1 前半;design/11 approved 直接施工)
- `src/paper_crawler/browserfetch.py`(新):`fetch_one` 纯函数 + `BrowserFetchHandle` Protocol
  (goto/download_via/close),一次性 context 用完即毁,不建池/账本(design/11 §3.2 案 A/§4.6 接缝
  A-1);预算唯一事实源=FetchLog 派生(零新表)。
- `pipeline/stages.py` `_stage_fetch` 加分支 + `_fetch_via_browser`;`config.py` 4 槽
  (`[browserfetch] enabled/daily_cap/rate_rpm/jitter_s`,design/11 §7.5);`cli.py` `--browser` flag。
- 已裁决歧义:S-c/E-1 前置**已落地**(P6 F6,勿重做);`types.py` 零改(`RENDER_PAGE` 已在枚举);
  真实浏览器实现(playwright)按 design/11 的依赖裁决执行——若 design 定为可选 extra,则 Protocol
  注入 + 可选依赖两层,测试全走 fake handle 零浏览器;AC-BF 编号转正归 T18,本卡按 design/11 §10
  草案落测试;检查单 #8(http→auth 分层)随本卡评估,仅当横切件确需更细分层才动,否则报告里登记。

### W1 波次(T1/T2 签署后滚动开;T9/T10 无依赖可提前)

**T7【Opus/Opus 审】extract 核心落地**(依赖 T1/D-033)
- stage 5 noop→真实:纯文本抽取器(D-033 选型)+ GROBID 可选客户端 + 降级链 + asset 级幂等 +
  `_asset_final_path` 扩 fulltext + `fulltext` 行真实字段(extractor/extractor_ver/text_path/
  char_count/lang)。离线测试:fixture PDF(仓库内小样本)+ mock GROBID 两模式(AC-7.1/7.2 离线载体)。

**T8【Opus/Opus 审】repec enrich 首批**(依赖 T2/D-035;检查单 #2)
- 首步:两域 robots 核验(≤2 请求,§3 T8-robots 行;不通过则停手上报)。
- `adapters/repec/{__init__,adapter,parse}.py`(参照 enrich-eval-p6.md §2.7 任务卡草稿):bulk ReDIF
  快照(`state/repec/`)→本地 join,`enrich_batch(dois)` duck-type,`Classification-JEL` 字段消费,
  DOI↔handle 仅 NBER 语法映射(复用 `adapters/nber/parse.py` series 归一);`_ENRICH_SOURCES` 扩位。
- 快照首拉(≤4 请求)可与 T19 合批,离线测试用 fixture 快照。

**T9【Sonnet/Opus 审】arxiv 参数化谓词机制**(检查单 #4 谓词半边)
- `subs/filter.py` `PREDICATE_REGISTRY` 谓词签名改造(构造器形态,承载订阅级参数);
  `subs/compile.py::_compile_arxiv` 把 `query` 布尔式编译为参数化补偿谓词实例(替代
  `title_regex_any` 手工镜像"约定");`subs/types.py` `PlanStep` 参数承载;`subs/model.py` 校验。
- 已裁决歧义:既有 `ssrn.topic_filter` 谓词迁移到新签名(唯一存量,兼容层不做);9 preset 的
  `title_regex_any` 镜像**保留**(防御纵深),新机制叠加非替换;审查档 Opus(接缝=subs 链冻结件)。

**T10【Sonnet/Opus 审】preprint_of 建边引擎**(检查单 #5)
- `merge.py::MergeEngine.ingest()` 新增 preprint_of 判定分支:消费各 adapter 已存入 `PaperStub.meta`
  的线索(arxiv `journal_ref/doi` 回填、Crossref/OpenAlex preprint 字段、SSRN→DOI 提示),跨 paper
  查找,建 `paper_relation(kind="preprint_of")` 边(仿 `repo.py:766-818 _upsert_candidate` 模式,
  证据/置信度落 evidence_json);**双条 paper 双份全文、不合并**(design/06 §3)。
- 已裁决歧义:`paper_relation` 表已支持(kind 枚举含 preprint_of),**零迁移**;方向约定=
  from(preprint)→to(published),写死并测试锁定;审查档 Opus(合并算法正确性)。

### W2 波次(依赖各自上游卡合并后滚动开)

**T11【Sonnet/Sonnet 审】browser-fetch 三消费方接入**(依赖 T6;检查单 #1 后半)
- ssrn 模式 B(`adapters/ssrn/adapter.py`,D-029 案 B 接线)/aea pubs 全文(`_deferred_fulltext_url`
  转真实 AssetPlan)/wiley 页面兜底(TDM 失败路径),三处消费 `BrowserFetchHandle` 接缝;逐处极薄,
  合规注记(AC-0)每处复述。
**T12【Sonnet/Sonnet 审】FTS5 落地**(依赖 T2/D-034):`0004_*.sql` 迁移 + rebuild + `crawler search`
  最小命令(title+abstract)。
**T13【Opus/Opus 审】dedupe review CLI + 聚合语义**(AC-7.3;依赖无,W2 起防 repo.py 冲突面)
- `repo.py` 新增 `list_candidates`/`decide_candidate`;`same_as(decided=merged)` 的查询层聚合语义
  (design/06 §3:merge 保留两行+置边,物理不删,查询层合并显示,**可回滚**);`crawler dedupe review`
  子命令组(逐条展示 evidence_json,merge/reject 落 decided)。
**T14【Sonnet/Sonnet 审】verify 全库扩展**(AC-7.4 前半;依赖 T1 冻结件,可与 T7 并行)
- `verify.py` 扫描范围 pdf/ → +si/ +fulltext/(`fulltext.text_path` 对账);si"每 paper 一目录多文件"
  孤儿判定粒度按 T1 冻结件裁决执行;`missing_file`/`orphan_file`/`hash_mismatch` 三类同构扩展。
**T15【Sonnet/Sonnet 审】econsoc 回看窗闭合**(检查单 #6)
- 移植 aaai_ojs F3 的 `_cached_partition`/`_backfill_pages` 结构(`aaai_ojs/adapter.py:179-304`
  同构参照);**并修当前年首拉完整性**:首拉当年走无窗全量、此后窗口增量(controller 裁决:两 adapter
  同构缺口本卡先修 econsoc,aaai_ojs 同缺口若属实由审查确认后同卡顺修或立 P2 记录)。
- ECMA `[UNRESOLVED①④]` **不在本卡**(Cloudflare 阻,站点风险面稳定后另批,§8)。

### W3 波次

**T16【Sonnet/Sonnet 审】preprint↔published 关联报告**(AC-7.4 后半;依赖 T10):报告生成
  (markdown,沿 subs/report.py 或 report.py 惯例),preprint_of 边聚合视图。
**T17【Sonnet/Sonnet 审】Database 构造审计**(检查单 #10):grep 口径 82 处/41 文件逐处甄别
  (F5 `with closing()` 样板;已有 fixture/try-finally 兜底的如实记录不改),修复无兜底处;
  产出审计表落 `docs/reports/` 附录或卡报告。
**T18【Sonnet/Sonnet 审】AC-BF 转正 + AC-7 验收载体**(依赖 T6/T11):acceptance-criteria.md 回填
  AC-BF 正式编号+AC-5.1b 承接指针(检查单 #1 尾项);AC-7 四条验收记录模板(testing/records/)。

### W4 波次(收尾)

**T19【Opus 执行】在线验收批**(§3 预算;依赖全部实现卡):AC-7.1/7.2 真实抽样、browser-fetch 冒烟、
  repec bulk 快照、检查单 #11(nber 隔离+asset-pricing 端到端);逐请求记账入 T4 账本。
**T20【独立审计批】**:Opus 深审×2(①extract+browserfetch+三消费方;②repec+merge 建边+dedupe 聚合)
  + Sonnet 面审×1(其余:谓词/FTS/verify/cooldown/回看窗/审计卡);审查规格=亲自构造对抗输入+
  变异测试(P6 教训⑩)。
**T21【Sonnet】文档一致性收尾**:INDEX/progress/development-plan 状态行、phase7-report 骨架、
  检查单 16 项逐项处置对账表。
**T22【fable 亲自】终审 + tag phase-7**:全分支终审、门禁亲跑、签署、打 tag。

## §5 波次并行图与冲突面预算

```
W0: T1 T2 T3 T4 T5 T6          (6 并行;T3/T6 共 cli.py——T3 先合,T6 rebase)
W1: T7(←T1) T8(←T2) T9 T10     (T9/T10 可与 W0 尾部重叠滚动)
W2: T11(←T6) T12(←T2) T13 T14(←T1 冻结件) T15
W3: T16(←T10) T17 T18(←T6,T11)
W4: T19 → T20 → T21 → T22      (串行收尾)
```

已知 union 冲突点(合并顺序=先到先合,后者 rebase;INDEX.md/decision-log.md 冲突由 controller 亲解,
防"选边丢行"——P6 教训⑭):
- `cli.py`:T3(cooldown 组)/T6(--browser)/T12(search)/T13(dedupe 组)——跨波次天然错峰。
- `config.py`:T6(browserfetch 槽)/T7(extract 槽)。
- `pipeline/stages.py`:T6(fetch 分支)/T7(extract 阶段)——不同函数区域。
- `storage/repo.py`:T10(建边)/T13(list/decide)/T14(verify 消费)——T10 先,T13/T14 依次 rebase。
- `decision-log.md`:T1(D-033)/T2(D-034/035)——同波次,先到先合,追加区冲突 controller 亲解。

## §6 模型分配(执行/审查;fable 纯 advisor 零执行)

| 档 | 卡 |
|---|---|
| Opus 执行 | T1 T2 T6 T7 T8 T13 T19 T20-深审×2 |
| Sonnet 执行 | T3 T4 T5 T9 T10 T11 T12 T14 T15 T16 T17 T18 T21 T20-面审×1 |
| Opus 审查 | T1 T2 T6 T7 T8 T9 T10 T13 |
| Sonnet 审查 | T3 T4 T5 T11 T12 T14 T15 T16 T17 T18 |
| fable | 切卡/派发/仲裁/合并+门禁亲跑/终审 T22 |

## §7 AC 映射与风险

| AC | 载体卡 |
|---|---|
| AC-7.1 全文抽取 | T7(离线 fixture)+T19(真实抽样) |
| AC-7.2 GROBID 可选 | T7(mock 开+关降级)+T19(条件:本机 GROBID 可用) |
| AC-7.3 去重审核 | T13 |
| AC-7.4 全库对账+关联报告 | T14+T16(+T19 全库 verify 亲跑) |
| AC-BF.x(转正) | T6/T11 实现,T18 转正,T19 冒烟 |

风险:①extract 幂等键改版触碰 pipeline 核心——T1 设计先行+T7 独立审查+T20 深审三重门;②repec bulk
快照体积未知——T8 首拉限 NBER 面并记账;③browser-fetch 合规敏感——AC-0 每卡复述+T20 深审专项;
④GROBID 本机不可用→AC-7.2 真实开模式转条件项,离线 mock 载体保底(D-018 分层先例)。

## §8 不建卡项(显式出列,范围锁定 R5)

- **OpenAlex 补枚举 ladder(a)**(检查单 #3):P7 无余力承接(本计划 22 卡已满),且与 repec enrich
  目标不重叠(ssrn 元数据覆盖 vs NBER JEL 增值)——**defer P8 候选**,条件原样沿账。
- **全文正文 FTS 索引与向量索引**:defer——正文索引等抽取产物规模实测(P8 评估经济性),向量索引
  无消费场景+引重依赖(YAGNI)。D-034 内如实记录。
- **registry role 声明式改造**(D-035 相关):P7 走 `_ENRICH_SOURCES` 元组扩位最小改,role 字段挂 P8。
- **aaai 全文回填批 ~5049 篇**(检查单 #13):待用户令另行插单,本 Phase 不动。
- **elsevier T7b/S2 key/wiley token/oup 首登**(检查单 #14):外部依赖沿账,key 到位即按既有 runbook
  补验,非本 Phase 卡。
- **econsoc ECMA [UNRESOLVED①④]**(检查单 #6 尾):Cloudflare 交互质询阻塞在线核实,待站点风险面
  稳定后专项批,不占本 Phase 在线预算。
- **`~/.kaggle` 等 config 外围**:D-032 已裁不搬,不动。
