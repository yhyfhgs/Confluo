# `tests/fixtures/` —— Fixture 与 Golden 基建

对应 [test-plan §2](../../docs/testing/test-plan.md#2-fixture-体系t3-的核心机制)。
本目录承载两类离线制品：**golden 快照**（本任务 T6 起用，adapter 输出的确定性
基线）与 Phase 2+ 起的**真实站点 fixture 三件套**（页面快照 + 期望解析输出）。

## Golden 机制

`tests/helpers/golden.py` 提供 `assert_matches_golden(obj, golden_path)`：

1. 把 `obj`（dataclass 实例，或其 list/tuple）递归转换成 canonical 结构——
   dataclass → dict、`Enum` → `.value`、tuple → list；
2. 以 `json.dumps(..., indent=2, sort_keys=True, ensure_ascii=False)` 序列化；
3. 与 `golden_path` 文件内容逐字符比对；不一致时输出 unified diff 并 `fail`。

**重录纪律**（test-plan §2 "golden 变更必须人工过目"，防止解析器错改把错误固化
为预期）：

- golden 文件不存在，或环境变量 `UPDATE_GOLDEN=1`：写入当前实际输出后**仍然
  fail**（消息含 "golden (re)recorded, review diff"）——不会在同一次运行里
  静默转绿；
- 正确流程：`UPDATE_GOLDEN=1 uv run pytest <target> -q` 生成/更新文件 → 用
  `git diff` 人工检查改动是否符合预期（标题/字段是不是解析器改动导致的、而不是
  站点行为的巧合误判）→ 确认无误后正常提交；下一次不带 `UPDATE_GOLDEN` 重跑该
  测试应转绿。**任何人不得在未过目 diff 的情况下提交 `UPDATE_GOLDEN=1` 生成的
  文件**。

## 目录布局

```
tests/fixtures/
├── README.md                        # 本文件
└── mock_platform/
    └── golden/
        ├── timeline.json             # mock_journal 全量 timeline（6 IssueRef）
        └── issue-v1n1.json           # v1n1 期的 5 个 PaperStub
```

`mock_platform` 的 golden 由 `tests/unit/test_mock_platform.py` 生成/校验，
用的是 `helpers.make_mock_venue()` 构造的契约 venue（quirks: `volumes=3,
issues_per_volume=2, papers_per_issue=5, seed=42`——与 phase1-implementation-plan
Task 3 中 `venues/_mock/mock-journal.yaml` 的取值一致）。因为 mock 语料是
程序内确定性生成、零网络，这里不需要"页面快照"这一层，golden 就是唯一制品。

## Phase 2 起：真实站点 fixture 三件套

真实 adapter（openreview/crossref/elsevier_sd 等）的 fixture 落在
`tests/fixtures/<adapter_id>/` 下，每个 adapter **至少**准备三件套（test-plan
§2）：

```
tests/fixtures/<adapter_id>/
├── raw/
│   ├── listing_normal.html（或 .json）      # 正常 listing 页
│   ├── detail_normal.html（或 .json）        # 正常详情页
│   └── error_<case>.html（或 .json）         # 一种异常页：空结果 / 登录墙 / 404
└── golden/
    ├── listing_normal.json                   # 对应期望解析输出
    ├── detail_normal.json
    └── error_<case>.json
```

规则：

- **录制**：用 `crawler devtools record <adapter> <url>`（Phase 2 起提供）抓取
  原始响应，工具会自动脱敏（剥 cookie/token/个人数据）后落 `raw/`；重录暂存在
  `_staging/`（**不入 git**，确认无误后再手动挪进 `raw/`）；
- **认证站点**：fixture 一律来自登录态人工导出并脱敏，**绝不**包含存活的
  session/cookie/token 原文；`obslog.redact()` 覆盖的凭证形态字符串在入库前必须
  已被替换为占位符；
- **重录触发**：`crawler canary` 报漂移 → 人工确认站点真的变了（而不是网络抖动
  / 临时限流）→ 重录 `raw/` → 按需修解析器 → 用上面的 golden 流程更新
  `golden/` 并过目 diff；
- 站点响应快照本身不受 golden 重录纪律约束（它是"输入"不是"断言"），但增删
  `raw/` 文件同样应在 PR 描述里说明原因，方便审查。

## arXiv fixture 八件套（Phase 2 T5）

`tests/fixtures/arxiv/raw/`（无 `golden/` 层——这些是回放**输入**，断言写在
`tests/unit/test_arxiv_fixtures.py` / `tests/integration/test_arxiv_enumerate.py` 里）：

| 件 | 文件 | 覆盖（arxiv.md §5/§6） |
|---|---|---|
| ① | `01_query_atom_normal.xml` | Query API Atom 正常页（10 条，含 1 条老格式 id） |
| ② | `02_oai_listrecords_page1.xml` (+ `..._page2.xml`) | OAI ListRecords 正常页 + resumptionToken 翻页 |
| ③ | `03_query_atom_empty.xml` | 空结果 Atom（totalResults=0，边界正常态） |
| ④ | `04_query_atom_total_mismatch.xml` | totalResults>0 但 entry 空 → `parse` |
| ⑤ | `05_pdf_withdrawn.html` | 撤稿 HTML 页（pdf url 回 HTML）→ `gone` 嗅探 |
| ⑥ | `06_oai_503_retry_after.http` | HTTP 503 + Retry-After → `rate_limited`（响应头随 body 落盘） |
| ⑦ | `07_oai_bad_resumption_token.xml` | OAI badResumptionToken → `transient` |
| ⑧ | `08_query_400_offset.xml` | Query API 400 offset 超限 → `config` |
| 补 | `09_query_atom_healthcheck.xml` | 3 canary（healthcheck 双字段比对） |
| 补 | `10_oai_norecordsmatch.xml` | OAI noRecordsMatch → 合法空态（非错误，§5 勘误） |

**⚠ 全部为合成 fixture（SYNTHETIC）**：本批未做真实站点录制——结构依 OAI-PMH 2.0 /
Atom 1.0 / arXiv API 规范手写，内容为构造值，各文件头以注释标注。选择合成而非录制的
理由：(a) 确定性（真实 OAI 月页有上千条记录，需重裁且随时间漂移）；(b) 合规——真实
录制须先履行 arxiv.md §4 的在线 robots/ToU 复核义务。**T7 在线冒烟须用实测响应对照
保真度**（尤其 ⑨ 的 canary id/title 与 `adapter._CANARIES` 均为占位，须替换为经核验的
3 篇真实稳定论文）。重录工具：`scripts/record_arxiv_fixtures.py`（单次运行、D-014 UA、
≤10 请求 @1req/3s、落 `_staging/` 待人工过目脱敏）。

### `.http` 快照格式（⑥）

响应头需随 body 落盘时（Retry-After 等信号须 round-trip），用 `.http` 文本格式，
由 `tests/helpers/arxiv_fixtures.py::http_fixture()` 解析：以 `#` 开头的行是注释；
`HTTP-STATUS: <int>` 声明状态码；其余 `Key: Value` 为响应头；**首个空行**后是原始 body。

## OpenReview fixture 十一件套（Phase 2；AC-2.1/2.2）

`tests/fixtures/openreview/`（无 `golden/` 层——回放**输入**，断言在
`tests/unit/test_openreview_fixtures.py` / `tests/integration/test_openreview_pull.py`）：

| 件 | 文件 | 覆盖（openreview.md §6/§7） |
|---|---|---|
| ① | `01_v2_notes_normal.json` | v2 notes 正常页（接收+pdf / 接收无pdf / 被拒 Submission） |
| ② | `02_v2_notes_paged_page1.json` (+ `..._page2.json`) | count>limit 分页（offset 至 count） |
| ③ | `03_notes_empty.json` | 200 `{"notes":[],"count":0}` 合法空态 |
| ④ | `04_groups_venues.json` | groups venues 主表节选（届表交叉验证）；另 `04_group_2024_v2`/`04_group_2014_v1` 判版本 |
| ⑤ | `05_v1_notes_page.json` | v1 notes 直取形态（2014，arxiv 线索入 meta，无 pdf） |
| ⑥ | `06_challenge_403.http` | 403 ChallengeRequiredError → adapter 重分类 `auth_expired` |
| ⑦ | `07_notfound_404.http` | 404 NotFoundError → `gone` |
| ⑧ | `08_ratelimit_429.http` | 429 + ratelimit 头 → `rate_limited` |
| ⑨ | `09_malformed.json` | 畸形 JSON → `parse` |
| ⑩ | `10_server_error_500.http` | 5xx → `transient` |
| ⑪ | `11_bad_request_400.http` | 400 → `config` |

**⚠ 全部为合成 fixture（SYNTHETIC；Phase 2 无用户 token 故全部合成）**：结构依
docs.openreview.net v1/v2 note schema 与勘察 §1-§7 [DOC]/[LIVE] 手写，内容为构造值，
文件头（JSON `_synthetic` 键 / `.http` `#` 注释）标注"合成；待 token 后真实校验"。
④ 的 venues 主表 ICLR.cc/* 系勘察 §2 [LIVE] 转录（公开 CC0 元数据、匿名可读）。
**在线部分（带 token 冒烟 + anchor 正式 count 生成）BLOCKED 待用户 token**——离线全链
（enumerate→resolve→fetch MockTransport 回放、AC-2.1 anchor 结构比对、AC-2.2 pull 回放）
是本期 DoD。加载器 `tests/helpers/openreview_fixtures.py`（`fixture_bytes`/`http_fixture`）。

## Unpaywall fixture 十二件套（Phase 3 T5；design/adapters/aggregators.md §5.5/§8）

`tests/fixtures/unpaywall/`（无 `golden/` 层——回放**输入**，断言在
`tests/unit/test_unpaywall_parse.py` / `test_unpaywall_adapter.py` / `test_unpaywall_report.py`）：

| 件 | 文件 | 覆盖（aggregators.md §5.5/§8） |
|---|---|---|
| ① | `01_normal_gold_fallback.json` | 正常 OA（gold，`best_oa_location.url_for_pdf:null` 触发 `oa_locations[]` 回退链）；D-019 锚点，见下 |
| ② | `02_direct_pdf_hit_hybrid.json` | 直接命中 `url_for_pdf`（无需回退）；hybrid + 非正式版 `acceptedVersion` |
| ③ | `03_landing_only_no_pdf_anywhere.json` | `url_for_pdf` 全线为空，仅 landing 有值 → 0 AssetPlan（★裁决 J4） |
| ④ | `04_closed.json` | closed（`is_oa:false`，无 OA 副本，非错误） |
| ⑤ | `05_oa_status_green_submitted.json` | oa_status=green 代表值 + 非正式版 `submittedVersion` |
| ⑥ | `06_oa_status_bronze.json` | oa_status=bronze 代表值 + 正式版 `publishedVersion` |
| ⑦ | `07_not_found_404.http` | 404（DOI 未收录）→ `gone`（adapter 侧归一为 `None`，非错误） |
| ⑧ | `08_missing_email_422.http` | 422（缺 email）→ `config` |
| ⑨ | `09_ratelimit_429.http` | 429 + Retry-After → `rate_limited` |
| ⑩ | `10_server_error_500.http` | 5xx → `transient` |
| ⑪ | `11_malformed.json` | 畸形 JSON → `parse` |
| ⑫ | `12_missing_required_fields.json` | 语法合法但缺 `is_oa` → `parse`（防御性覆盖，非纯语法错误） |

①②③④⑤⑥ 合计覆盖 oa_status 五枚举值全量（gold/hybrid/green/bronze/closed）。
**⚠ 部分为 [LIVE] 核验值 + 合成外壳**：①的 `is_oa`/`oa_status`/`best_oa_location.
version`/`best_oa_location.url_for_pdf`/`oa_locations` 计数四项系 D-019 锚点
（`10.1371/journal.pmed.0020124`，[LIVE] 2026-07-22，aggregators.md §7）核验值，
其余字段与②-⑫全部内容均为按 Unpaywall v2 响应 schema 手写的构造值（文件头
`_grounded`/`_synthetic` 键标注）。①同时充当 `UnpaywallAdapter.healthcheck()` 的
mock 回放素材；真实在线核对留待 `tests/online/test_unpaywall_smoke.py`（已写、
按契约未执行，MAX_REAL_REQUESTS=1）。加载器 `tests/helpers/unpaywall_fixtures.py`
（`fixture_bytes`/`http_fixture`，与 openreview 同构）。

## OpenAlex fixture 八件套（Phase 3 T6；design/adapters/aggregators.md §5.3/§8）

`tests/fixtures/openalex/`（无 `golden/` 层——断言在
`tests/unit/test_openalex_parse.py` / `test_openalex_adapter.py`）：

| 件 | 文件 | 覆盖（aggregators.md §5.3/§8） |
|---|---|---|
| ① | `01_works_normal.json` | 正常批查（两条记录：一含 `abstract_inverted_index`/多作者/OA 全字段，一空倒排索引+空作者+closed），`meta.cost_usd` |
| ② | `02_works_empty.json` | 空结果（`count:0`），`meta.cost_usd` 仍读取 |
| ③ | `03_works_402_budget_exhausted.http` | 402 credit 耗尽 → `rate_limited` 特化（预算熔断同语义） |
| ④ | `04_works_malformed_inverted_index.json` | `abstract_inverted_index` 畸形（值非位置列表）→ `parse` |
| ⑤ | `05_works_429.http` | 429 + Retry-After → `rate_limited` |
| ⑥ | `06_works_400_bad_filter.http` | 400（filter 语法）→ `config` |
| ⑦ | `07_works_500.http` | 5xx → `transient` |
| ⑧ | `08_single_work_healthcheck.json` | 单条 `GET /works/W{id}`（healthcheck 用） |

**⚠ 部分为 [LIVE] 存在性核验 + 合成外壳**：①第一条记录/⑧的 DOI/OpenAlex id/title
取自真实存在的知名条目（Piwowar et al. 2018 "The state of OA"，`W2741809807`）——
仅借其真实存在性避免"合成假设"（Phase 2 教训），`abstract_inverted_index`/
`open_access` 等具体字段值仍为构造值，未经本次实现在线核验（[PENDING]，healthcheck
`_HEALTHCHECK_TITLE` 留待在线冒烟 UPDATE_GOLDEN 捕获）。加载器
`tests/helpers/openalex_fixtures.py`（`fixture_bytes`/`http_fixture`，与
crossref/unpaywall 同构）。真实在线核对留待 `tests/online/test_openalex_smoke.py`
（已写、按契约未执行，MAX_REAL_REQUESTS=1；用 D-019 **负锚点** DOI
`10.1257/aer.20221079` 而非本节的正锚点，避免依赖任何论文措辞随出版社修订漂移）。

## S2 (Semantic Scholar) fixture 七件套（Phase 3 T6；design/adapters/aggregators.md §5.4/§8）

`tests/fixtures/s2/`（无 `golden/` 层——断言在
`tests/unit/test_s2_parse.py` / `test_s2_adapter.py`）：

| 件 | 文件 | 覆盖（aggregators.md §5.4/§8） |
|---|---|---|
| ① | `01_batch_normal.json` | 正常 `POST /paper/batch` 响应（数组：一命中含 `citationCount`/`tldr`/`fieldsOfStudy`/`openAccessPdf`，一 `null` 未命中，一命中但缺 title→跳过） |
| ② | `02_single_not_found_404.http` | 404 not-found（单条端点；"有 key 真缺"场景，靠 key 存在性预判区分"无 key"同状态码症状） |
| ③ | `03_batch_429.http` | 429 + Retry-After（有 key 超速）→ `rate_limited` |
| ④ | `04_batch_400_bad_fields.http` | 400（`fields=` 语法）→ `config` |
| ⑤ | `05_batch_500.http` | 5xx → `transient` |
| ⑥ | `06_batch_malformed.json` | 顶层非数组（S2 batch 响应契约要求数组）→ `parse` |
| ⑦ | `07_single_paper_healthcheck.json` | 单条 `GET /paper/DOI:{doi}?fields=title`（healthcheck 用） |

"无 key"场景（§8 表第④项）**不落 fixture 文件**——`enrich_batch` 在函数入口直接
判定 key 是否配置，未配置立即 `CrawlerError(CONFIG)`、不发任何请求（不靠状态码
推断，D2），故没有可回放的响应体；`tests/unit/test_s2_adapter.py` 用
`_never`（一发请求即 `AssertionError`）handler 直接验证这条"零网络"路径，②号
fixture 的 404 body 在该测试的注释里作为"若发了请求会看到什么症状"的参照。
**⚠ 部分为 [LIVE] 存在性核验 + 合成外壳**：①/⑦的 `paperId`/DOI/title 取自真实存在
的知名论文（"Attention Is All You Need"，Vaswani et al. 2017）——S2 key 用户申请中
未经本次实现在线核验，`citationCount` 等具体数值为构造值（真实值会随时间增长，
不宜写死）。加载器 `tests/helpers/s2_fixtures.py`。真实在线核对留待
`tests/online/test_s2_smoke.py`（已写、按契约未执行且 `pytest.mark.skipif` 无 key
门控，MAX_REAL_REQUESTS=1）。
