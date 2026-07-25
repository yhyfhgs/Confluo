# Phase 5 终审后独立代码审计报告（2026-07-24）

> **性质**：`tag phase-5` 落地后、Phase 6 开工前的一次**全库存量代码独立复审**（用户指令触发），
> 与各 Phase 内的任务卡审查/opus 终审相互独立。8 个审计 subagent 并行执行：
> **4 × Opus 4.8 深审档**（核心框架 / 数据与合并引擎 / 认证安全与 AC-0 红线 / pipeline+CLI）+
> **4 × Sonnet 5 面审档**（Phase 2 OA adapters / Phase 3 聚合 adapters / Phase 5 新 adapters+venues / 测试体系）。
> 纪律：全程只读（零 `src/`/`tests/` 改动、零 git 写操作、零真实网络请求）；发现只登记不修复。
> 基线：审计前主线亲跑 `make check` **3056 passed / 28 skipped / 覆盖率 98.78% / EXIT=0**（37.97s），
> 与 [phase5-report §7](2026-07-24-phase5-report.md) 门禁数字一致；各审计员在此绿基线上另行亲跑
> 分域测试子集（372/398/539/292/1039/437/377 等，全部通过）与隔离复现脚本（scratchpad，不落仓库）。

## 1. 总判定

**八个审计域全部「附条件达标」，零 P0（阻断性功能错误）。** Phase 1–5 已交付代码的核心语义
（接口冻结件、任务状态机、限速数学、AES-GCM 凭证库、合并引擎保守性、OA-fallback 链、20 adapter 能力
契约）实现正确且测试基本充分；AC-0 五条红线经逐行复核**全部 PASS**。发现集中在三类：
①少数真实但 fail-safe 方向的语义缺陷（P1×3）；②"边界/漂移场景静默降级"模式类缺陷（P2 主体）；
③文档与实现的滞后漂移（本报告 §5 处置）。

## 2. 分域结论

| # | 审计域 | 模型档 | 判定 | 发现概况 |
|---|---|---|---|---|
| O1 | 核心框架（types/errors/adapter/registry/config/http/ratelimit/useragent/obslog/sensitive/tasks） | Opus 4.8 | 附条件达标 | P1×1 + P2×3 + P3×3；盲区 5 |
| O2 | 数据与合并引擎（storage/ids/merge/verify） | Opus 4.8 | 附条件达标 | P1×1 + P2×1 + P3×4；盲区 5 |
| O3 | 认证与安全（auth 包 + 三 auth_gated adapter + sensitive） | Opus 4.8 | 附条件达标 | P2×1 + P3×3；**AC-0 五条全 PASS** |
| O4 | pipeline+CLI+canary | Opus 4.8 | 附条件达标 | P2×1 + P3×4；正向确认状态机/退出码契约完整 |
| S1 | Phase 2 OA adapters（arxiv/openreview/pmlr/acl/cvf/aaai_ojs/neurips/_oai） | Sonnet 5 | 附条件达标 | P1×1 + P2×6；C-D 修复与两历史 HIGH 修复确认真修 |
| S2 | Phase 3 聚合 adapters（crossref/dblp/unpaywall/openalex/s2） | Sonnet 5 | 附条件达标 | P2×1 + P3×4；crossref `lookup()` 已有直测（P4 遗留清账确认） |
| S3 | Phase 5 新 adapters（ssrn/nber/aea/econsoc）+ venues 58 YAML | Sonnet 5 | 附条件达标 | P2×2 + P3×1；D-028/D-029 三方一致，ssrn 零接触代码层成立 |
| S4 | 测试体系（3056 测试/28 skip/覆盖率配置/隔离性） | Sonnet 5 | 附条件达标 | P2×2 + P3×3；28-skip 台账逐行核对干净 |

## 3. 发现台账

### P1（应修缺陷，均非阻断、fail-safe 方向）

1. **[O2] AC-3.4「注入顺序无关」静默破坏** — `storage/repo.py:536-539`（`_converge_fields` 收敛
   title/title_norm）+ `merge.py`（弱信号仅在 `_merge_ingest_no_hit` 建行时判定）：强合并时高优先源
   改写 `title_norm` 后**不重跑弱信号候审匹配**，同一观测批不同注入序产生不同候审边数（审计员隔离
   脚本实测：序 A,B,C→1 条候审边；序 C,A,B→0 条）。`_first_author` 收敛（repo.py:549-553）同理。
   方向 fail-safe（漏标候审、不误并），但违反 AC-3.4 判据字面语义。现有属性测试因生成器令同 work
   各源共享 title/surname 而**结构性遮蔽**该缝隙。建议：收敛改键后重判候审，或冻结 title_norm/
   `_first_author` 不参与收敛；并令属性生成器对同 anchor 各源变动标题。
2. **[O1] 畸形 TOML 逃逸错误分类契约** — `config.py:98`（`_load_toml`）：家目录/项目级 `config.toml`
   语法错误时抛裸 `tomllib.TOMLDecodeError`，未包成 `CrawlerError(CONFIG)`（实测复现）；同函数的
   敏感键护栏却规范包 CONFIG，处理不一致，违反 errors.py「配置错误归 CONFIG 类」契约。
3. **[S1] aaai_ojs 历史卷冷回填全库重扫** — `adapters/aaai_ojs/adapter.py:174-178`：`enumerate_issue`
   仅对当前卷加回看窗，其余 16 个历史卷各自触发全库无窗口重扫（按设计文档单趟 262 页推算冷回填
   ≈4200 请求/~140 分钟），与详设承诺的单趟性能相悖。效率/对站礼貌风险，非正确性错误；与
   progress.md 既有待裁决项「volume_map 扩容 2010–2018」直接相关——**扩容前必须先修此项**。

### P2（应跟踪修复；按域归组）

- **[O3] oup_silverchair 429 缺专属处置**（`adapters/oup_silverchair/adapter.py:356-385,256-291`）：
  429 被 `ChallengeDetector` 判为 OK 后落 `PARSE`/`INTEGRITY(auth_leak)` 而非 `RATE_LIMITED`，与
  elsevier（当日熔断）/wiley（HttpClient 映射）不一致；失败安全但限速信号丢失、可能误导 canary。
- **[O1] `load_adapters` entry point 同名静默覆盖 + 第三方加载异常无兜底**（`adapter.py:241`）。
- **[O1] `RateLimiter.alias()` 可放宽已注册域速率**（`ratelimit.py:79`）：别名覆盖已有独立桶时无
  「有效 rpm 单调不增」守卫。
- **[O1] `auth_work_hours=""` 关闭路径不可达**（`config.py:479`）：空串被归一为未配置回落默认
  `"8-23"`，文档与行为不符（仅 `"0-24"` 有效）。
- **[O2] verify 孤儿扫描仅覆盖 `data_dir/pdf/`**（`verify.py:98-109`）：si/fulltext/export 下孤儿
  不检出（有测试锁定此边界=有意，但 AC-3.3「孤儿文件」语义下是真实漏报面）。
- **[S2] openalex 日预算跨进程 check-then-act 竞态**（`adapters/openalex/budget.py:20-28` +
  `adapter.py:198-210`）：flock 仅加固 `add_spend` 自身，「查预算→发请求→记账」窗口未闭合（代码
  已自陈），并发 `crawler enrich` 可共同突破日预算。
- **[O4] `test_cli_canary.py` 断言列表第三次滞后**（`tests/integration/test_cli_canary.py:159-179`）：
  oup_silverchair/wiley 已补齐（Phase 4 遗留清账确认），但 Phase 5 新增 `aea` 又漏（列 19 个 vs
  同函数注释自称「现 20 个」，自相矛盾）；同一「注册了却没验证」反模式第三次复现
  （aaai_ojs/dblp→oup_silverchair/wiley→aea），测试因 aea SKIP 语义仍绿。
- **[S4] canary/golden 漂移检测零自动化**：test-plan §4 承诺的周跑在库内无任何自动化载体
  （无 CI/cron），`records/canary/` 仅 1 份手跑记录；golden 无时效告警字段，漂移全靠人工纪律。
- **[S4] offline 全绿跑伴随 27 条 sqlite `ResourceWarning`**（集中于 `tests/unit/test_migrations.py`
  连接开闭不对等）：不影响断言正确性，属资源纪律缺口。
- **[S1] Phase 2 adapters「静默降级」模式类 ×6**：`_oai.py:133-135` 缺 ListRecords 且无 error 时
  静默空页；openreview 2018/2019 规则（C-D）多页翻页无专属测试（fixture 均单页）；
  `aaai_ojs/adapter.py:199` 卷号不匹配静默丢弃无日志；`pmlr/parse.py:90,163-168` 链接正则对标记
  漂移静默退化为 0 资产（cvf 同场景是硬失败）；acl_anthology SI 路径 `[UNRESOLVED]` 零在线验证；
  acl bulk 对账生成器分卷计数手抄自 anchor（实证算术自洽而非独立正确性）。
- **[S3] econsoc CF-403 挑战冷却缺口**（`adapters/econsoc/adapter.py:307,506` + `http.py:89` +
  `pipeline/runner.py:665`）：冻结 `HttpClient` 把 403 统一映射 `NO_ENTITLEMENT`，仅 `CHALLENGE`
  触发 24h 冷却；econsoc 的 `ChallengeDetector` 嗅探只对 200 状态挑战页生效，对 403+`cf-mitigated`
  （aea 勘察实测到的 CF 真实形态）不生效。**Phase 2/4 冻结架构的系统性边界**（wiley/oup 同受限），
  econsoc 是首个实际会触网遇到它的 adapter；CF 测试均只 mock 200，403 场景零覆盖。
- **[S3] 当前年 30 天回看窗完整性缺口**（`adapters/econsoc/adapter.py:199`，与 `aaai_ojs:176` 同构）：
  首拉当年数据时漏收入库已超 30 天的论文，须待年份滚出后由历史收割补回；测试只断言 URL 含
  `from=`，未测语义完整性。

### P3（备忘/低风险，摘要）

时区与归一边界：nber `_today` 用本地时区（项目内唯一未 UTC 化的时间敏感 adapter，软门兜底不可利用）；
`ids.normalize_doi` 不识别无 scheme 裸 host（`doi.org/10.x` 原样返回）；LaTeX 宏 vs Unicode 字母
归一不对称（`\o`→"ko" 但 ø 保留）。健壮性：挑战冷却落盘非原子且损坏时 fail-open
（`runner.py:594,608`）；`pull --limit 0`/负值无下界校验（`cli.py:595`）；elsevier 熔断进程内易失
（已文档化扩展点）；crossref cursor 无「不推进」哨兵；同源二次观测异值「先到胜」顺序敏感
（`repo.py:527-534`）；`db.py:160` 迁移切分不识别块注释（当前迁移不含）；obslog 跨 UTC 午夜不切
新文件；OA 副本与平台 pdf 同路径覆盖（代码内已记 MINOR-2 已知债）。测试基建：contract 28-skip
计数无自断言防腐（由 `EXPECTED_ADAPTER_IDS` 硬编码 20 项间接兜住）；无 `test_sensitive.py` 直测；
`http.post_json` 无直测。

## 4. 正面确认（审计证实无问题的高风险面）

1. **AC-0 五条红线全 PASS**（O3 逐行复核）：无盗版源集成点；`ChallengeDetector` 纯防御分类零求解/
   绕过逻辑（hcaptcha/recaptcha 仅作检测子串）；`git log --all --diff-filter=A` 全历史零凭证文件；
   obslog 经 `sensitive.py` 单一权威源脱敏含 insttoken/x-els-apikey/tdm-token；三平台限速保守且
   `source_note` [LIVE] 溯源。
2. **AES-GCM 凭证库实现正确**：每次新 nonce、AAD=ref 防跨条目重放、32B 主密钥、keyring→filekey
   降级链、0600/0700 原子创建、取证式覆写删除、ref 路径穿越防御，全部测试锁定；交付面内 `read_key`
   明文零泄漏（仅 `has_key` 布尔消费）。
3. **任务状态机与退出码契约完整**：7 合法转移 25 格矩阵全覆盖测试；退出码 0/1/2/3 九命令一致。
4. **28-skip 台账干净**：逐行均为 contract 能力缺口型，精确加总=28 与 phase5-report 口径逐字一致；
   凭证门控 skip 全隔离 `tests/online/`，三层防护（Makefile 物理排除 + `-m 'not online'` +
   `socket.connect` autouse 猴补，后者系此前真实网络泄漏事件后的加固）。
5. **ssrn「站点零接触」代码层成立**（D-029 红线）：`domains=("api.crossref.org",)`，无任何请求路径
   触达 `*.ssrn.com`（`landing_url` 纯字符串构造）。
6. **D-028 三方一致**：`wiley/parse.py`（10.3982 已移除）↔ econsoc.md §3.3 ↔ catalog 两清单
   （`ffb2028` 修正）逐一吻合；nber 双域、aea 8 刊 ISSN 路由三方核对一致。
7. **历史修复真修确认**：openreview C-D（2018/2019 规则）四层测试锁定；pmlr healthcheck DOM 失配、
   cvf `query_author`/`query` 两历史 HIGH 均有专属回归+在线冒烟看守；crossref `lookup()` 已补直测；
   canary 断言列表 oup_silverchair/wiley 已补（但见 P2 aea 新漏）。
8. **覆盖率无系统性盲区**：`pragma: no cover` 全仓仅 8 处/5 文件，逐一核查均为合理防御/平台分支/
   手动门控；integration 层非空心 mock（mock IdP 为完整状态机，sqlite/队列/runner/CLI 全真实）。

## 5. 文档滞后处置（本次审计发现的实现↔文档漂移）

| 漂移 | 处置 |
|---|---|
| progress.md 快照/进度板/模块状态表停留 Phase 4 收尾时点 | **本收尾链已修**（快照重写至 2026-07-24、Phase 5 行转 done、模块表 +4 adapter 行） |
| INDEX.md phase5-report 行仍写「判定：待终审」 | **本收尾链已修** |
| `unpaywall/adapter.py` docstring 称 OA-fallback 接线「留待评估」（实际 Phase 4 已实现并被测试覆盖） | 登记 Phase 6 检查单（src 注释改动不入本 docs 收尾链） |
| `aggregators.md §5.2` 未回填 dblp 真实 `<bht>/<dblpcites>/<r>` 结构（修复仅见 parse.py docstring 与测试） | 登记 Phase 6 检查单 |
| auth-framework §8.3/8.4 称日配额 cap 可由 `VenueSpec.rate_limit` 日上限覆盖——schema 无此字段、runner 只读 `Config.auth_daily_cap`，文档高估能力 | 登记 Phase 6 检查单 |

## 6. 处置建议（并入 Phase 6 开工检查单）

1. **P1×3 立项**：AC-3.4 顺序无关修复（含属性生成器补强）→ 建议 Phase 6 首批；config TOML 包裹
   CONFIG（小改）；aaai_ojs 历史卷窗口分区/跨卷缓存（与 volume_map 扩容裁决合并考虑，扩容前置）。
2. **CF-403 挑战冷却缺口**（S3-P2）系统性评估：与 Phase 6 browser-fetch 横切件设计（phase5-report
   检查单 #2）同批处理——403+`cf-mitigated` 形态判定属同一 `ChallengeDetector`/HttpClient 接缝。
3. **静默降级模式类**（S1 六项 + OAI 空信封）：统一按「响亮失败优于静默空结果」原则排一次小批
   清账卡。
4. **测试基建两项**（S4）：canary 周跑自动化载体（cron/CI 任选）+ `test_migrations.py` 连接关闭
   纪律；顺带 canary 断言列表补 `aea` 并加集合等值自断言（根治第三次复现的反模式）。
5. 其余 P3 逐条已录本报告 §3，随相关模块的下次触碰顺带处理，不单独立卡。

## 7. 签署

- **审计执行**（2026-07-24）：8 subagent 并行（4 Opus 4.8 + 4 Sonnet 5），只读纪律零违例
  （审计后 `git status` 复核 clean）；分域测试亲跑全绿；两处 P1 级发现附隔离脚本实测复现证据。
- **合并判定**：**全库附条件达标** —— Phase 1–5 存量代码功能正确性与测试充分性经独立复审成立，
  `tag phase-5` 判定不受影响；附条件（P1×3 + P2×12）已全数登记本报告 §3/§6，纳入 Phase 6 开工
  检查单执行，无需回滚或紧急修复。
