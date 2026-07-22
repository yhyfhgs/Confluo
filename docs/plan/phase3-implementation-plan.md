---
title: Phase 3 实施计划 — 聚合元数据层
status: draft
owner: fable5
updated: 2026-07-22
---

# Phase 3 实施计划 — 聚合元数据层

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development 逐任务派发执行。
> 判定依据：[development-plan §Phase 3](development-plan.md)、[acceptance-criteria AC-3/AC-0](../testing/acceptance-criteria.md)、[Phase 2 报告 §6 开工检查单](../reports/2026-07-22-phase2-report.md)、D-005（修订）/D-007/D-019。
> 实施模式沿用 phase1/phase2 验证过的全部纪律（详设 approved 硬门禁 / worktree 波次并行 / 每任务独立审查+限量真实交叉验证 / fix 循环 / 主 agent 合并亲跑门禁 / 全分支终审 / SDD ledger）。
> 详设载体：[design/adapters/aggregators.md](../design/adapters/aggregators.md)（W0 扩写至实现级后 approved）+ [design/06-data-model.md §3](../design/06-data-model.md)（合并语义，已 implemented）。

**Goal**：五源聚合客户端（crossref/dblp/openalex/s2/unpaywall）+ 合并引擎上线；AC-3.1~3.5 全过；QJE/JFE 等 5 刊零爬取产出完整期目与论文清单；OA 副本命中率报告生成。

**Architecture**：Phase 1/2 冻结接口不变（SourceAdapter 协议 / HttpClient 签名 / pipeline 六阶段）。Phase 3 两条主线：①**合并引擎**（ingest 路径升级：identifier 强合并 + 弱信号候审 + 字段级来源优先级收敛——AC-3.4 顺序无关的实现基石）；②**aggregator 家族 adapter**（capabilities 无 FETCH，产出 PaperStub 流与 OA-fallback AssetPlan；metadata_source/fulltext_source 分离语义按 D-005 以纯附加方式落进 VenueSpec）。两线接口解耦（adapter 产 stub、引擎管收敛），开发可并行，AC-3.1 验收在两线合流处。

**Tech Stack**：不变（Python 3.12+ / httpx / sqlite3 / pydantic v2 / typer / pytest+coverage / ruff / mypy strict）。**新增 dev 依赖**：`hypothesis`（AC-3.4 属性测试判据明文要求，仅 dev-dependencies）。**不引入**：其他运行时依赖（XML 走标准库 `xml.etree`，沿 arxiv/_oai 先例）。

## Global Constraints（每个任务隐含继承）

- **AC-0 红线五条**（acceptance-criteria §AC-0）：无盗版源集成点；无 CAPTCHA 求解；凭证/session/PDF 不入 git；日志报告无未脱敏敏感值；限速 ≤ 站点声明、robots 禁区不访问。
- **真实网络纪律**：默认测试零真实网络（socket 禁网护栏在位）；`tests/online/` 显式 `-m online` + `MAX_REAL_REQUESTS` 预算头；UA `PaperCrawler/<ver> (personal research; mailto:<email>)` 经 config 注入（D-014）。**Crossref polite pool 硬要求 mailto**——五源客户端一律带。
- **限速出处**：每源 `default_rate` 带 `source_note`（勘察复核 [LIVE] 值为准，见 §2 限速表）。
- **门禁**：`make check` 全绿方可合并（覆盖率 ≥80% 门禁不回退，现 99.32%）；聚合源解析/映射模块覆盖 ≥90%（对齐 adapter 解析器纪律）。
- **详设硬门禁**：aggregators.md `approved` 前 T3~T6 不开工；合并引擎语义依 06 §3（已 approved/implemented），实现级接口冻结见本计划 §2（评审随本计划 approved 一并生效）。
- **提交规范**：Conventional Commits，scope `merge` / `adapter:<id>` / `core` / `testing`；尾行 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`；任何 git 写操作前确认分支（worktree 纪律）。
- **fixture 纪律**：真实响应录制一律脱敏；golden 重录 `UPDATE_GOLDEN=1` + 人工过目；合成 fixture 的关键数值优先取自勘察 [LIVE] 实测（Phase 2 教训：合成假设是盲区源）。
- **范围只减不增**：五源为 committed 范围；`core`（CORE API）在设计文档合册内但**不在本 Phase 交付范围**（development-plan 五源字面），不主动实现。

## §2 接口冻结件（Phase 3 增量；T1 落盘后冻结，改动须仲裁）

1. **合并引擎 `merge.py` · MergeEngine**（T1 产出）：
   ```python
   class MergeEngine:
       def __init__(self, repo: Repo) -> None: ...
       def ingest(self, stub: PaperStub, *, source: str) -> IngestResult: ...

   @dataclass(frozen=True)
   class IngestResult:
       paper_id: str
       action: Literal["created", "merged", "candidate_flagged"]
       matched_identifiers: tuple[str, ...]   # 命中的 (scheme:value) 列表
   ```
   - **强合并**：stub 携带的任一 identifier `(scheme,value)` 已存在 → 并入既有 paper；事务内完成（查→并→补 identifier 单事务，防并发裂脑）。
   - **字段级来源优先级收敛（AC-3.4 基石）**：字段写入记录来源级别（`paper.meta_json` 内 `_field_src` 映射）；新值仅当 ①现值为空 或 ②新来源优先级严格高于现值来源 时写入；同级不覆盖（先到先得仅在同级内，跨级由优先级决定终态→任意到达顺序收敛到同一终态）。优先级表冻结：`official`（官方 proceedings/出版社）> `crossref` > `dblp` > `openalex` > `s2` > `heuristic`（★W0 仲裁 2026-07-22：dblp 位次新增——Crossref 系 DOI 注册源头存缴元数据居先；DBLP 人工策展质量高于机器聚合层；详见 D-021）。
   - **弱信号候审**：无共同 identifier 时，`title_norm`（去标点/大小写/LaTeX 宏/空白折叠）精确匹配 + 首作者姓氏一致 → 建 `paper_relation(kind=candidate_duplicate, decided=NULL, confidence, evidence_json)`，**绝不自动合并**；无匹配 → 新建 paper。
   - **schema v2 迁移**（0002）：`paper` 增列 `title_norm TEXT` + 索引 `idx_paper_title_norm`；迁移器回填存量行。纯附加，v1 库自动升级。
   - **DOI 规范化**：`ids.normalize_doi()`（小写化/剥 `https://doi.org/`、`doi:` 前缀）——identifier 写入的唯一入口经过它（crossref/unpaywall/dblp ee 回填共用）。
2. **VenueSpec 分离语义**（D-005，T3 第一消费者落地，纯附加）：`metadata_source: str | None`（默认 None=沿用 adapter 自身）；registry 校验：声明了 metadata_source 的 venue，其值必须是已注册 aggregator adapter id；期刊 kind 且 metadata_source=crossref 时 issn 必填（D-015 既有规则保持）。
3. **aggregator 无 FETCH 契约**：家族 capabilities 不含 FETCH；unpaywall RESOLVE 产 `AssetPlan(url_strategy="direct", auth="none")` 交通用 fetcher；pipeline 对 metadata-only venue 的 fetch 阶段行为=空集跳过（现有语义已支持，回归测试锁定）。
4. **在线预算**（T5 契约沿用）：每源在线冒烟 `MAX_REAL_REQUESTS ≤ 5`；本 Phase 在线总预算 ≤60 请求（冒烟批量+AC-3.5 实跑+锚点核准），超支须如 Phase 2 C-A 入档。

## §3 限速与预算表（2026-07-22 勘察复核定稿，[LIVE]）

| 源 | 默认策略 | 出处 |
|---|---|---|
| crossref | 动态读 X-Rate-Limit 头（实测 10/1s），上限 5 req/s 起步 | polite pool 官方 [LIVE] |
| dblp | **≥4s/req**（robots `Crawl-delay: 4`）；`/search`、`/rec/xml` robots 禁区→capabilities 无 SEARCH，只走 `/db/**` 卷目录与 dump | robots.txt [LIVE]（D-021） |
| openalex | 每日 credit 预算 + 响应 `meta.cost_usd` **实时精确核销**熔断 | 计费制官方 + [LIVE] 复核 |
| s2 | 1 req/s（有 key）；无 key 症状=**404 not-found**（非 429）→ `config` 不重试、healthcheck 检测口径按此设计 | 官方 + [LIVE] 复核 |
| unpaywall | 5 req/s 且日总量 <100k | 官方 |

## §4 任务卡

### F1/F2/M1（Phase 2 移交，已先行派发——不依赖本计划门禁）
- **F1** `fix/core-pull-usability`（opus）：C-C 零网络 resolve 跳限速 + `--limit` 前置确定性圈选；AC-1.2/1.3 回归锁定。
- **F2** `fix/openreview-venueid-quirks`（opus，在线 ≤15）：逐届 venueid 实测 → quirks 按届规则 + anchor 0 值届修正。
- **M1** `chore/phase2-handover`（sonnet）：make smoke / canary 落盘 / supported_since 补标 / meta 白名单。

### T1 合并引擎核心（opus/fable 档，`feat/merge-engine`）——AC-3.1/3.2/3.4 载体
- 交付：§2-1 全部 + Hypothesis 属性测试（多源记录集随机顺序注入 → 最终 DB canonical dump 逐行一致；策略生成器覆盖：identifier 交集/空集、字段缺失组合、同级/跨级来源）。
- 判据：AC-3.1（同 DOI 两路注入→1 paper ≥2 identifier）、AC-3.2（改名 WP↔刊发版→2 paper + 1 candidate_duplicate(decided=NULL)）用例直接落 `tests/integration/`；属性测试 ≥200 examples 稳定通过。
- 现状盘点义务：先读现有 ingest 路径（pipeline stages 的 ingest 段与 repo.upsert 行为），diff 出改造面清单入报告。

### T2 verify 三类检出扩展（sonnet，`feat/verify-recon`）——AC-3.3 载体
- 人为制造 ①DB 有 Asset(fetched) 但文件缺失 ②data/ 有文件但 DB 无行（孤儿） ③文件在但 sha256 不符 → `crawler verify` 三类全检出，输出含**正确修复建议**（缺文件→re-fetch 提示；孤儿→纳管或清理提示；哈希不符→标记 corrupt+re-fetch）。先盘点 Phase 1 T8a verify 现状，差距驱动。

### T3 crossref adapter（opus，`adapter/crossref`）——AC-3.5 载体
- `/journals/{issn}/works` 枚举（rows/cursor 深翻断点续拉）、日期过滤、字段映射（title[0]/日期族选择/author 结构）、volume/issue → Issue 行聚合、`paper_count_claimed` 记录、X-Rate-Limit 动态限速（rate_limiter 扩展点）、429/5xx 映射、healthcheck 固定 DOI 比对。含 §2-2 VenueSpec 分离语义落地。fixture：正常页/空结果/429/cursor 中断续拉。

### T4 dblp adapter（sonnet，`adapter/dblp`）
- conf 索引页卷 key 发现 → 卷 XML 解析（inproceedings/ee/author-pid）→ `ee` DOI 经 `normalize_doi` 回填 identifier；404→gone 回索引重发现一次再 parse；1 req/2s；healthcheck icml 已知卷。

### T5 unpaywall adapter（sonnet，`adapter/unpaywall`）
- 按 DOI RESOLVE：`best_oa_location.url_for_pdf` → AssetPlan(direct)；version 映射（[LIVE] 全拼串 `submittedVersion`/`acceptedVersion`/`publishedVersion`）→ Asset.version 并标注非正式版；`url_for_pdf` 为 null 时不产 AssetPlan（landing 仅记 meta）；触发条件（no_entitlement 兜底 / VenueSpec OA-fallback 声明）；**OA 命中率报告**：批量 DOI 输入 → 命中率统计 markdown（DoD 第二项）。

### T6 openalex + s2 补充层（sonnet，`adapter/openalex-s2`）
- openalex：DOI 批查摘要倒排重建；每日 credit 预算熔断（402→rate_limited 特化+报告提示）；s2：`/paper/batch`（≤500）引用计数/TLDR；无 key→`config` 不重试。在线冒烟按 key 存在性 skip（S2 key 用户申请中，诚实标注）。

### T7 期刊 5 刊 YAML + AC-3.5 端到端（sonnet，`feat/journal-venues`）
- QJE(0033-5533)/JFE(0304-405X) + 3 刊（catalog economics/finance 表内选，凑齐 5）；`metadata_source: crossref` + fulltext_source 留 Phase 4；`timeline`/`enumerate` 零爬取全史；篇数与 `paper_count_claimed` 差异逐刊解释入验收记录；五源在线冒烟批量 committed（`tests/online/test_<src>_smoke.py` ×5）。

### T8 收尾（fable 编排）
- AC-3.1~3.5 汇总验收记录 + AC-0 系统性扫描（git 全历史+日志正则，Phase 1/2 先例）；D-019 五站锚点人工核准清账（检查单 #3，aaai 需先全库 OAI 补跑）；aggregators.md → implemented；INDEX/progress/decision-log 同步；`docs/reports/` 阶段报告；tag `phase-3`。

## §5 波次并行图

```
W0(现在):  勘察复核 ‖ F1 ‖ F2 ‖ M1          → aggregators.md 扩写→双评审 approved + 本计划定稿
W1:        T1 合并引擎(opus) ‖ T2 verify(sonnet)      [计划 approved 即开；T1 是接口冻结锚]
W2:        T3 crossref(opus) ‖ T4 dblp(sonnet)        [详设 approved 后；与 T1 接口解耦可并行]
W3:        T5 unpaywall ‖ T6 openalex+s2 (sonnet×2)
W4:        T7 端到端(依 T1+T3+T5) → T8 收尾(依全线)
每任务: implementer(worktree) → 双裁决审查(Spec+质量, 限量真实交叉验证 ≤5 req 授权) → fix 回派 → controller 合并亲跑 make check
```

## §6 AC 映射与风险

| AC | 载体任务 | 验收形态 |
|---|---|---|
| AC-3.1 强合并 | T1（+T3 双路实数据） | 集成测试 + 端到端复核 |
| AC-3.2 弱信号候审 | T1 | 集成测试 |
| AC-3.3 verify 三类 | T2 | 集成测试（三类人为制造） |
| AC-3.4 顺序无关 | T1 | Hypothesis 属性测试 |
| AC-3.5 五刊零爬取 | T3+T7 | 在线实跑 + 离线回放双层（D-018 分层先例） |

风险：①OpenAlex 计费政策继续演化（预算护栏+降级路径=Crossref+S2 补摘要，设计已备）；②S2 key 未到（在线层 skip 门控，不阻塞离线 DoD）；③合并引擎触 ingest 热路径（Phase 2 全部 adapter 回归锁定——1629 测试是安全网）；④字段级 provenance 增加 meta_json 体积（仅记录来源级别短枚举，可控）。
