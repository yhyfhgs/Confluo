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
