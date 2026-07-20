---
title: Phase 1 实施计划（核心框架）
status: approved
owner: fable5
updated: 2026-07-21
---

# Phase 1 实施计划 — 核心框架

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development。任务步骤用 checkbox 跟踪。
> 需求依据（均 `approved`）：[development-plan §Phase 1](development-plan.md)、[design/01](../design/01-architecture.md)、[design/02](../design/02-plugin-framework.md)、[design/05](../design/05-pipeline.md)、[design/06](../design/06-data-model.md)、[testing/test-plan](../testing/test-plan.md)、[testing/acceptance-criteria AC-1](../testing/acceptance-criteria.md)。
> 工具链决策：[decision-log D-017](decision-log.md)。

**Goal**：交付 `src/paper_crawler` 核心框架——registry、SQLite schema v1、task 队列、六阶段串行 pipeline、限速器、结构化日志、`crawler` CLI——全部由 `mock_platform` 假 adapter 驱动，AC-1.1~1.6 全过，core 覆盖率 ≥80%。

**Architecture**：分层依赖只向下（design/01 §1）。本 Phase 实现 L1(存储/日志)、L2(限速)、L3(registry+mock adapter)、L4(六阶段)、L5(task 队列+串行编排)、L6(CLI)。零网络：mock adapter 程序内确定性生成语料。

**Tech Stack**（D-001 + D-017）：Python ≥3.12、uv、typer、Pydantic v2、PyYAML、python-ulid、sqlite3(标准库, WAL)、pytest+pytest-cov、ruff、mypy。**Phase 1 不引入 httpx/Playwright**（无网络需求，Phase 2/4 再进）。

## Global Constraints（每个任务隐含遵守）

1. 提交遵循 [git-workflow](../process/git-workflow.md)：Conventional Commits；scope 表；代码与测试同提交；body 写 `Refs: FR-xx, D-xxx` / `Closes: AC-x.x`。每条提交信息尾行 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`。
2. 一个任务一个分支（分支名在任务标题）；实现者不合并——合并由主 agent 串行执行。
3. TDD：先写失败测试再实现；任务完成时 `make check`（lint+type+test）必须全绿。
4. 禁止越界：不写其他任务的文件；不实现真实站点 adapter；不引入计划外依赖。
5. 错误分类学（design/05 §4）是全系统唯一错误语义，任何异常路径必须映射到 `ErrorClass`。
6. 日志/异常文本不得含凭证形态内容；`redact()` 覆盖 cookie/token/authorization/api_key/password（NFR-8、AC-0.4）。
7. 时间戳一律 UTC ISO8601 字符串；主键一律 ULID 文本（design/06 §2）。
8. 所有路径经 `Config` 注入，禁止硬编码 `~/.paper-crawler`（kill-9 子进程测试依赖 `PAPER_CRAWLER_HOME` 隔离）。
9. SQL 保持方言中性（PG 迁移路径，design/06 §6）；不使用 FTS5/专有特性（D-017：FTS5 推迟 Phase 6）。
10. 覆盖率门禁：`--cov=paper_crawler --cov-fail-under=80`（test-plan §6）。

## §2 接口冻结件（Interface Freeze — 唯一权威，实现禁止偏离签名）

> 以下签名由 T1 落盘。T2+ 只消费；发现缺陷须报告主 agent 仲裁，不得自行改签名。

### 2.1 `errors.py`

```python
from enum import StrEnum

class ErrorClass(StrEnum):
    TRANSIENT = "transient"; RATE_LIMITED = "rate_limited"
    AUTH_EXPIRED = "auth_expired"; NO_ENTITLEMENT = "no_entitlement"
    CHALLENGE = "challenge"; GONE = "gone"; PARSE = "parse"
    INTEGRITY = "integrity"; CONFIG = "config"

class CrawlerError(Exception):
    def __init__(self, error_class: ErrorClass, msg: str, *, detail: str = ""): ...
    error_class: ErrorClass; detail: str

class IllegalTransition(Exception): ...          # task 状态机非法转移
class CapabilityNotSupported(CrawlerError): ...  # error_class=CONFIG

# 重试表（design/05 §4）；backoff 秒可被 Config.retry_scale 缩放
from dataclasses import dataclass
@dataclass(frozen=True)
class RetrySpec:
    max_attempts: int          # 含首次；1 = 不重试
    backoff_seconds: tuple[float, ...] = ()

RETRY_TABLE: dict[ErrorClass, RetrySpec] = {
    ErrorClass.TRANSIENT:      RetrySpec(4, (2.0, 8.0, 30.0)),  # 3 次重试
    ErrorClass.RATE_LIMITED:   RetrySpec(4, (2.0, 8.0, 30.0)),  # 不计 attempts（队列层特判）
    ErrorClass.INTEGRITY:      RetrySpec(2, (0.0,)),            # 重下 1 次
    # 其余 → RetrySpec(1)；AUTH_EXPIRED/CHALLENGE/CONFIG → BLOCKED（pipeline 特判）
}
```

### 2.2 `types.py`（核心数据类型 + VenueSpec）

```python
class AuthLevel(StrEnum):
    NONE="none"; FREE_ACCOUNT="free_account"; SUBSCRIPTION="subscription"; INSTITUTIONAL="institutional"

class Capability(Flag):
    DISCOVER=auto(); ENUMERATE=auto(); RESOLVE=auto(); FETCH=auto(); SEARCH=auto()

@dataclass(frozen=True)
class RatePolicy:
    requests_per_minute: float
    burst: int = 1
    source_note: str = ""      # design/02：默认值必须注明出处

@dataclass(frozen=True)
class IssueRef:
    venue_id: str
    volume: str | None = None; number: str | None = None
    year: int | None = None; label: str | None = None
    pub_date: str | None = None; paper_count_claimed: int | None = None

@dataclass(frozen=True)
class PaperStub:
    title: str
    identifiers: tuple[tuple[str, str], ...]     # ((scheme, value), ...) 至少 1 个
    year: int | None = None; pub_date: str | None = None
    abstract: str | None = None
    authors: tuple[str, ...] = ()
    meta: tuple[tuple[str, str], ...] = ()       # 弹性字段（frozen 需 hashable）

class AssetKind(StrEnum): PDF="pdf"; SI="si"; HTML="html"; BIBTEX="bibtex"; SOURCE="source"
class UrlStrategy(StrEnum): DIRECT="direct"; RENDER_PAGE="render_page"; API_CALL="api_call"

@dataclass(frozen=True)
class AssetPlan:
    kind: AssetKind; url: str
    expected_type: str = "application/pdf"
    url_strategy: UrlStrategy = UrlStrategy.DIRECT
    auth_needed: AuthLevel = AuthLevel.NONE
    version: str | None = None

@dataclass(frozen=True)
class FetchResult:
    ok: bool; bytes_written: int = 0; sha256: str | None = None
    error_class: ErrorClass | None = None; detail: str = ""

@dataclass(frozen=True)
class HealthReport:
    healthy: bool; detail: str = ""

SessionHandle = Any        # Phase 4 具体化（design/07）；Phase 1 恒 None

class FetchIO(Protocol):   # pipeline 提供实现；adapter 只写流
    def write_stream(self, chunks: Iterable[bytes]) -> tuple[int, str]:
        """写入 *.part 临时文件，返回 (bytes_written, sha256_hex)。校验/rename 由 pipeline 负责。"""
```

`VenueSpec`（Pydantic v2，`extra="forbid"`，字段与 design/02 §2.2 YAML schema v1 一一对应）：

```python
// 修订 2026-07-21（T1 实施仲裁）：三个嵌套模型同样 extra="forbid"——嵌套键拼写错静默落默认值
// 会使 auth 兼容校验假阴性（AC-1.6 缺陷路径），故全树拒绝未知键。
class VenueNames(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full: str; aliases: list[str] = []
class VenueAuth(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: AuthLevel = AuthLevel.NONE; provider_hint: str | None = None
class VenueRateLimit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requests_per_minute: float | None = None

class VenueSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str                                    # ^[a-z][a-z0-9_]*$
    kind: Literal["journal", "conference", "preprint_channel"]
    names: VenueNames
    field: list[Literal["finance", "econ", "cs_ai", "or_ms"]]
    tier: Literal["T1", "T2", "T3"] | None = None
    identifiers: dict[str, object] = {}        # issn: list[str] / dblp_key / openreview_id / openalex_source
    metadata_source: str
    fulltext_source: str
    auth: VenueAuth = VenueAuth()
    rate_limit: VenueRateLimit = VenueRateLimit()
    quirks: dict[str, object] = {}
    status: Literal["active", "dormant", "dead"] = "active"
    notes: str = ""
```

### 2.3 `adapter.py`（SourceAdapter 协议 + 注册）

```python
@runtime_checkable
class SourceAdapter(Protocol):
    adapter_id: str
    family: Literal["open_access", "auth_gated", "aggregator"]
    capabilities: Capability
    default_rate: RatePolicy
    auth_requirement: AuthLevel
    domains: tuple[str, ...]     # 限速/日志归属域；[0] 为主域。实现期对 design/02 §3 的补充（per-domain 限速语义需要）

    def discover_timeline(self, venue: VenueSpec, since: str | None = None) -> Iterable[IssueRef]: ...
    def enumerate_issue(self, venue: VenueSpec, issue: IssueRef) -> Iterable[PaperStub]: ...
    def resolve_assets(self, venue: VenueSpec, paper: PaperStub,
                       session: SessionHandle | None = None) -> list[AssetPlan]: ...
    def fetch_asset(self, plan: AssetPlan, io: FetchIO,
                    session: SessionHandle | None = None) -> FetchResult: ...
    def healthcheck(self, session: SessionHandle | None = None) -> HealthReport: ...

class AdapterBase:
    """便利基类：未声明能力的方法默认 raise CapabilityNotSupported；healthcheck 默认 healthy。"""

def load_adapters() -> dict[str, SourceAdapter]:
    """扫描 entry point 组 'paper_crawler.adapters'（design/02 §4）＋内置注册。key=adapter_id。"""
```

### 2.4 `storage/`（T2 交付；签名供 T5/T7 消费）

```python
class Database:
    def __init__(self, db_path: Path): ...     # PRAGMA journal_mode=WAL, foreign_keys=ON
    def migrate(self) -> int                   # 顺序执行 storage/migrations/000N_*.sql；返回 schema_version
    def tx(self) -> ContextManager[sqlite3.Connection]
    def query(self, sql: str, params: Sequence = ()) -> list[sqlite3.Row]
    def execute(self, sql: str, params: Sequence = ()) -> None
    def close(self) -> None

class Repo:
    def __init__(self, db: Database): ...
    def upsert_venue(self, spec: VenueSpec) -> None                      # spec_snapshot_json 审计
    def upsert_issue(self, ref: IssueRef, source: str) -> str            # 幂等键 UNIQUE(venue,volume,number,label)
    def list_issues(self, venue_id: str, *, volume: str | None = None,
                    number: str | None = None, year: int | None = None) -> list[sqlite3.Row]
    def upsert_paper(self, venue_id: str, issue_id: str | None, stub: PaperStub) -> str
        # identifier (scheme,value) 命中 → 返回既有 paper_id，字段补缺不覆盖（design/06 §3 强合并锚点）
    def list_papers(self, venue_id: str, issue_id: str | None = None) -> list[sqlite3.Row]
    def set_paper_state(self, paper_id: str, ingest_state: str) -> None  # metadata_only|resolved|fetched|extracted
    def plan_asset(self, paper_id: str, plan: AssetPlan, source_adapter: str) -> str
        # UNIQUE(paper,kind,version) 幂等；state=planned；已 fetched 的不回退
    def list_assets(self, *, venue_id: str | None = None, state: str | None = None) -> list[sqlite3.Row]
    def get_asset(self, asset_id: str) -> sqlite3.Row | None
    def mark_asset(self, asset_id: str, *, state: str, file_path: str | None = None,
                   bytes_: int | None = None, sha256: str | None = None) -> None
    def add_fetch_log(self, *, asset_id: str | None, task_id: str | None, domain: str, url: str,
                      http_status: int | None, bytes_: int, elapsed_ms: int,
                      rate_wait_ms: int, error_class: str | None = None) -> None
    def fetch_logs(self, *, domain: str | None = None) -> list[sqlite3.Row]
    def counts(self, venue_id: str) -> dict[str, int]
        # {"issues": n, "papers": n, "assets_planned": n, "assets_fetched": n}  （AC-1.1 对账）
```

Schema v1 注记（对 design/06 §2 草案的两处实现期补全，T10 收尾时回填设计文档）：
- **补 `paper_issue_link` 表 DDL**（ER 总览已声明该表，§2 草案漏列）：`CREATE TABLE paper_issue_link (paper_id TEXT REFERENCES paper, issue_id TEXT REFERENCES issue, PRIMARY KEY (paper_id, issue_id));`
- **`task` / `fetch_log` DDL** 按 design/05 §2/§7 字段清单落定（见 T2）；`task.kind` 增列 `pull`（05 §2 文字已有"pull 任务展开子任务"语义）。

### 2.5 `tasks.py`（T5 交付）

```python
TaskKind = Literal["pull", "discover", "enumerate", "resolve", "fetch", "extract", "ingest"]
TaskState = Literal["PENDING", "RUNNING", "DONE", "FAILED", "BLOCKED"]

# 合法转移（全集，其余 raise IllegalTransition）：
#   PENDING→RUNNING; RUNNING→DONE|FAILED|BLOCKED|PENDING(退避重试);
#   FAILED→PENDING(retry); BLOCKED→PENDING(resume)

FRESHNESS_TTL: dict[str, timedelta | None] = {   # design/05 §2；None=永久新鲜
    "discover": timedelta(hours=24), "enumerate": timedelta(days=7),
    "resolve": None, "fetch": None, "extract": None, "ingest": timedelta(0), "pull": timedelta(0),
}  # timedelta(0)=永不视为新鲜（每次重跑）

@dataclass(frozen=True)
class EnqueueResult:
    task_id: str | None
    status: Literal["enqueued", "duplicate", "fresh_skip"]

class TaskQueue:
    def __init__(self, db: Database, clock: Callable[[], datetime] | None = None): ...
    def canonical_params(self, params: Mapping[str, object]) -> str      # sorted-keys JSON（幂等键成分）
    def enqueue(self, kind: TaskKind, venue_id: str | None, params: Mapping[str, object],
                *, parent_id: str | None = None, force: bool = False) -> EnqueueResult
    def claim_next(self) -> sqlite3.Row | None          # 最老 PENDING → RUNNING（事务内）
    def complete(self, task_id: str) -> None
    def fail(self, task_id: str, error_class: ErrorClass, msg: str) -> TaskState
        # 按 RETRY_TABLE：attempts<max → 回 PENDING（返回 "PENDING"）；否则 FAILED。RATE_LIMITED 不增 attempts。
    def block(self, task_id: str, reason: str) -> None  # 不动 attempts（design/05 §2）
    def resume(self, task_id: str | None = None, *, all_blocked: bool = False) -> int
    def retry_failed(self, error_class: ErrorClass | None = None) -> int
    def get(self, task_id: str) -> sqlite3.Row | None
    def by_state(self, state: TaskState) -> list[sqlite3.Row]
```

### 2.6 `ratelimit.py` / `obslog.py`（T4 交付）

```python
class RateLimiter:
    def __init__(self, *, scale: float = 1.0, clock: Callable[[], float] = time.monotonic): ...
    def register(self, domain: str, policy: RatePolicy) -> None   # 重复注册取更保守（更小 rpm）
    def override(self, domain: str, requests_per_minute: float) -> None  # VenueSpec/CLI 覆盖，取 min
    def acquire(self, domain: str) -> float
        # token bucket 消费；返回调用方应 sleep 的秒数（0=立即）。本方法不 sleep（可测性）。
    def effective_rpm(self, domain: str) -> float

# obslog.py —— 命名避开标准库 logging
def setup_logging(log_dir: Path, *, console_level: str = "INFO") -> None   # jsonl 文件 + 人读控制台
def log_event(level: str, msg: str, *, task_id: str | None = None, venue: str | None = None,
              stage: str | None = None, domain: str | None = None, url: str | None = None,
              error_class: str | None = None, **extra: object) -> None
    # jsonl 行：{ts, level, msg, task_id, venue, stage, domain, url(先 redact), error_class, ...}；None 键省略
def redact(text: str) -> str
    # 规则：(?i)(cookie|set-cookie|authorization|token|api[_-]?key|password|secret|session[_-]?id)
    #       键值对与 URL query 同名参数值 → "***"
```

### 2.7 `pipeline/`（T7 交付）与 `config.py`（T1 交付）

```python
@dataclass(frozen=True)
class Config:
    home: Path; data_dir: Path; db_path: Path; log_dir: Path; reports_dir: Path
    venues_dirs: tuple[Path, ...]
    rate_scale: float = 1.0; retry_scale: float = 1.0
    @classmethod
    def load(cls, home: Path | None = None) -> "Config"
        # 优先级：显式 home 参数 > $PAPER_CRAWLER_HOME > ~/.paper-crawler
        # 若 home/config.toml 存在：tomllib 读 [paths].data_dir、[paths].venues_dirs、[rate].scale、[retry].scale
        # venues_dirs 默认 = (cwd/"venues" 若存在, home/"venues" 若存在)；后者同 id 覆盖前者（design/02 §4）
    def ensure_dirs(self) -> None    # data/{pdf,si,fulltext,export,tmp}、logs、reports

@dataclass(frozen=True)
class Selector:
    volume: str | None = None; issue: str | None = None; year: int | None = None
    dois: tuple[str, ...] = (); filter_expr: str | None = None; limit: int | None = None
    # filter_expr Phase 1 语义 = 标题大小写不敏感子串（FR-05 关键词过滤；DSL 属 Phase 6）

@dataclass
class RunReport:
    command: str; venue_id: str | None; started_at: str; finished_at: str = ""
    succeeded: int = 0; failed: int = 0; blocked: int = 0; skipped: int = 0
    planned_downloads: int = 0; planned_bytes: int = 0
    failures: list[dict] = field(default_factory=list)   # {task_id, stage, error_class, msg}
    notes: list[str] = field(default_factory=list)
    def render_markdown(self) -> str
    def save(self, reports_dir: Path) -> Path            # 写 last-run.md + 追加 history.jsonl

@dataclass
class StageContext:
    config: Config; db: Database; repo: Repo; registry: VenueRegistry
    queue: TaskQueue; limiter: RateLimiter
    sleeper: Callable[[float], None] = time.sleep
    dry_run: bool = False

class PipelineRunner:
    def __init__(self, ctx: StageContext): ...
    def pull(self, venue_id: str, sel: Selector, *, with_extract: bool = False,
             force: bool = False) -> RunReport
    def run_single_stage(self, kind: TaskKind, venue_id: str, params: dict) -> RunReport
    def drain(self) -> RunReport      # claim_next 循环直到队列无 PENDING
```

### 2.8 `registry.py`（T3 交付）

```python
@dataclass(frozen=True)
class Route:
    venue: VenueSpec
    metadata_adapter: SourceAdapter
    fulltext_adapter: SourceAdapter
    auth_profile: str | None            # auth.provider_hint
    rate_overrides: dict[str, float]    # domain -> rpm（VenueSpec.rate_limit 展开到 fulltext 主域）

@dataclass(frozen=True)
class LintIssue:
    file: str; venue_id: str | None; field: str; message: str

class VenueRegistry:
    def __init__(self, adapters: dict[str, SourceAdapter]): ...
    def load_dirs(self, dirs: Sequence[Path]) -> list[LintIssue]   # 递归 *.yaml；后目录同 id 覆盖前目录；返回错误（不 raise）
    def lint(self) -> list[LintIssue]     # 校验规则见 T3；空列表=通过
    def get(self, venue_id: str) -> VenueSpec          # 未知 id → CrawlerError(CONFIG)
    def route(self, venue_id: str) -> Route            # 绑定解析（design/02 §4）
    def all(self) -> list[VenueSpec]
```

---

## 任务分解

**波次与并行**（git-workflow §1：无共享文件可并行；core 合并串行，由主 agent 执行）：

```
Wave A: T1(bootstrap, opus)                                  ← 串行独占
Wave B: T2(storage, opus) ‖ T3(registry, sonnet) ‖ T4(infra, sonnet)   ← worktree 并行
Wave C: T5(tasks, opus) ‖ T6(mock+contract, sonnet)          ← worktree 并行
Wave D: T7(pipeline, opus)                                   ← 串行
Wave E: T8(CLI, opus) → T9(acceptance, opus)                 ← 串行
Wave F: T10(closeout, fable5 主 agent)
```

每任务完成 → 独立 reviewer subagent 审查（spec 合规 + 质量双裁决）→ 修复循环 → 主 agent 合并 main 并跑全量测试。

---

### Task 1: Bootstrap — 项目骨架与接口冻结件落盘

**分支** `feat/core-bootstrap` · **模型** opus · **Reviewer** opus

**Files:**
- Create: `pyproject.toml`、`Makefile`、`.gitignore`(增补)、`src/paper_crawler/__init__.py`、`src/paper_crawler/errors.py`、`src/paper_crawler/types.py`、`src/paper_crawler/adapter.py`、`src/paper_crawler/config.py`、`src/paper_crawler/adapters/__init__.py`、`src/paper_crawler/adapters/mock_platform.py`（骨架）、`src/paper_crawler/adapters/stubs.py`、`tests/conftest.py`、`tests/unit/test_errors.py`、`tests/unit/test_types.py`、`tests/unit/test_adapter_loading.py`、`tests/unit/test_config.py`
- Modify: `AGENTS.md`（§0 与 §2 目录表：设计阶段→实现阶段措辞）、`README.md`（同步措辞）、`docs/INDEX.md`（AGENTS/README updated 日期）

**Interfaces:** Produces = §2.1/2.2/2.3/2.7-Config 全部签名（逐字落盘）。

要点与步骤：
- [ ] `uv init` 风格 pyproject：`name="paper-crawler"`、`requires-python=">=3.12"`、deps `typer`,`pydantic>=2`,`pyyaml`,`python-ulid`；dev-group `pytest`,`pytest-cov`,`ruff`,`mypy`,`types-PyYAML`；`[project.scripts]` **T1 不声明**（cli 模块 T8 才有，避免 broken entry point；T8 增补 `crawler = "paper_crawler.cli:main"`——2026-07-21 派发修正，与实现一致）；entry point 组 `[project.entry-points."paper_crawler.adapters"]` 注册 `mock_platform`。`uv.lock` 入库。
- [ ] `Makefile`：`make test`(pytest T1–T4 目录 + 覆盖率门禁 80)、`make lint`(ruff check + ruff format --check)、`make type`(mypy src)、`make check`(三者)。
- [ ] `.gitignore` 增补：`.venv/`、`__pycache__/`、`.coverage`、`*.sqlite*`、`data/`、`.superpowers/`。
- [ ] errors/types/adapter/config 按 §2 逐字实现；`utcnow_iso()`、`new_ulid()` 工具函数进 `types.py`。
- [ ] `adapters/mock_platform.py` 骨架：类属性齐全（`adapter_id="mock_platform"`, family="open_access", capabilities=DISCOVER|ENUMERATE|RESOLVE|FETCH, default_rate=RatePolicy(600, burst=10, source_note="本地 mock，无真实站点约束"), auth_requirement=NONE, domains=("mock.local",)），方法体 `raise NotImplementedError("T6")`。
- [ ] `adapters/stubs.py`：`crossref`(aggregator, DISCOVER|ENUMERATE, none, RatePolicy(50, source_note="⚠ 占位；Phase 3 按 research/site-survey/metadata-apis.md 定值"), domains=("api.crossref.org",))、`openreview`(open_access, DISCOVER|ENUMERATE|RESOLVE|FETCH, none, RatePolicy(30, source_note="⚠ 占位；Phase 2 定值"), domains=("api2.openreview.net",))、`elsevier_sd`(auth_gated, RESOLVE|FETCH, institutional, RatePolicy(10, source_note="⚠ 占位；Phase 4 定值"), domains=("www.sciencedirect.com",))。全部方法 `raise CapabilityNotSupported`/`NotImplementedError("stub until Phase 2/3/4")`。用途：jfe/iclr VenueSpec 可通过 lint（design/02 §6 验收前提）。`load_adapters()` 内置注册 stubs + entry point 扫描。
- [ ] AGENTS.md：§0 改为"当前处于实现阶段（Phase 1 起）：代码与文档同库演进，设计仍先行"；§2 表 `src/`、`tests/`、`venues/` 行去掉"（未来）/现阶段不建"，补职责（`src/` 实现代码——对应 approved 设计；`tests/` T1–T6 测试树——见 test-plan；`venues/` VenueSpec YAML）。README 同步一句定位。
- [ ] 测试：ErrorClass 枚举值=文档九类；RETRY_TABLE 语义；VenueSpec 解析合法/非法 YAML dict（extra 字段拒绝、field 枚举校验）；`load_adapters()` 能发现 4 个注册者且属性完整；Config.load 的 home 优先级与 toml 读取（tmp_path 下造 config.toml）。
- [ ] `make check` 全绿后提交（可多个逻辑提交：chore(core) 骨架 / feat(core) types+errors / docs 措辞）。

**DoD**：`uv run make check` 绿；`uv run python -c "from paper_crawler.adapter import load_adapters; print(sorted(load_adapters()))"` 输出 4 个 adapter id。

---

### Task 2: Storage — schema v1 迁移器与 repo 层

**分支** `feat/core-storage` · **模型** opus · **Reviewer** opus · **并行组** Wave B（worktree）

**Files:**
- Create: `src/paper_crawler/storage/__init__.py`、`storage/db.py`、`storage/repo.py`、`storage/migrations/0001_init.sql`、`tests/unit/test_migrations.py`、`tests/unit/test_repo.py`

**Interfaces:** Consumes §2.1/2.2；Produces §2.4 全部签名。

要点与步骤：
- [ ] `0001_init.sql`：design/06 §2 全表 DDL 逐表落定（venue、venue_era、issue、paper、identifier、asset、author、authorship、paper_relation、fulltext、subscription、subscription_run）+ 本计划 §2.4 注记的 `paper_issue_link`、`task`、`fetch_log`：

```sql
CREATE TABLE task (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, venue_id TEXT,
  params_json TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'PENDING',
  error_class TEXT, blocked_reason TEXT,
  attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT,
  parent_id TEXT REFERENCES task(id),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX idx_task_active_idem ON task(kind, venue_id, params_json)
  WHERE state IN ('PENDING','RUNNING');
CREATE INDEX idx_task_state_kind ON task(state, kind);
CREATE TABLE fetch_log (
  id TEXT PRIMARY KEY, asset_id TEXT REFERENCES asset(id), task_id TEXT,
  domain TEXT NOT NULL, url TEXT NOT NULL,
  http_status INTEGER, bytes INTEGER NOT NULL DEFAULT 0,
  elapsed_ms INTEGER NOT NULL DEFAULT 0, rate_wait_ms INTEGER NOT NULL DEFAULT 0,
  error_class TEXT, ts TEXT NOT NULL
);
CREATE INDEX idx_fetch_log_domain_ts ON fetch_log(domain, ts);
CREATE INDEX idx_asset_state ON asset(state);
CREATE TABLE schema_version (version INTEGER NOT NULL);
```

  （其余表 DDL 以 design/06 §2 原文为准逐列转写；**不建 FTS5**，D-017。）
- [ ] `db.py`：连接工厂（`sqlite3.connect(db_path, isolation_level=None)` + `row_factory=sqlite3.Row` + PRAGMA WAL/foreign_keys）；`migrate()` 读包内 migrations 目录按序执行未应用脚本，每步事务 + 执行前 `db_path` 文件 copy 备份（design/06 §6）；`tx()` 上下文管理器（BEGIN IMMEDIATE / COMMIT / ROLLBACK）。
- [ ] `repo.py` 按 §2.4 签名实现。`upsert_paper` 合并语义单测重点：两个 stub 共享 (doi,x) → 同一 paper_id；第二次的非空字段仅填补第一次的空缺（不覆盖非空）；`paper_issue_link` 建链幂等。
- [ ] 测试：migrate 幂等（连跑 2 次版本不变、无异常）；全表存在性对 DDL 清单断言；外键约束生效（插孤儿行报错）；upsert 族幂等；counts 口径。

**DoD**：`uv run pytest tests/unit/test_migrations.py tests/unit/test_repo.py -q` 绿；`make check` 绿。

---

### Task 3: Registry — VenueSpec 加载/校验/路由 + venues YAML 三份

**分支** `feat/core-registry` · **模型** sonnet · **Reviewer** sonnet · **并行组** Wave B（worktree）

**Files:**
- Create: `src/paper_crawler/registry.py`、`venues/_mock/mock-journal.yaml`、`venues/finance/jfe.yaml`、`venues/cs_ai/iclr.yaml`、`tests/unit/test_registry.py`、`tests/unit/test_venue_yaml_lint.py`

**Interfaces:** Consumes §2.2 VenueSpec、§2.3 load_adapters；Produces §2.8。

要点与步骤：
- [ ] 校验规则（design/02 §2.2 校验段，全部产出 `LintIssue` 带 file/field 定位——AC-1.6 要求定位信息）：
  1. id 唯一（跨目录重复=覆盖合法【用户目录覆盖语义】，同目录内重复=错误）；id 与文件名 stem 一致（kebab→snake 归一后比对，如 `mock-journal.yaml` ↔ `id: mock_journal`）；
  2. metadata_source / fulltext_source ∈ 已注册 adapter；
  3. auth.level ≥ fulltext_adapter.auth_requirement（等级序 none<free_account<subscription<institutional；不足=不兼容。例：elsevier_sd(institutional) 的 venue 声明 none → 报错）；
  4. kind=journal ⇒ identifiers.issn 必填且每项匹配 `^\d{4}-\d{3}[\dX]$`（D-015）；
  5. YAML 解析失败 / VenueSpec 结构校验失败 → LintIssue（file+pydantic loc 路径）。
- [ ] `route()`：capability 路由（design/02 §3"能力缺失即路由"）——discover/enumerate 缺失时由 metadata_adapter 承担已是绑定语义，Phase 1 直接按 metadata/fulltext 两列绑定；rate_overrides 从 `rate_limit.requests_per_minute` 映射到 fulltext_adapter.domains[0]。
- [ ] 三份 YAML：`mock-journal.yaml`（id=mock_journal, kind=journal, field=[cs_ai], issn=["0000-0000"], metadata_source=fulltext_source=mock_platform, auth none, quirks: {volumes: 3, issues_per_volume: 2, papers_per_issue: 5, seed: 42}）；`jfe.yaml`/`iclr.yaml` 按 design/02 §2.2 两个示例逐字（jfe 的 openalex_source 保留 `⚠ 示例值` 注释）。
- [ ] 测试：AC-1.6 非法族逐类（未知 adapter / auth 不兼容 / id 冲突 / journal 缺 issn / issn 格式错 / extra 字段 / 文件名-id 不一致）各断言 LintIssue.field 与 message；合法三份全过；覆盖目录优先级（同 id 后目录覆盖）。

**DoD**：`uv run pytest tests/unit/test_registry.py tests/unit/test_venue_yaml_lint.py -q` 绿；`make check` 绿。

---

### Task 4: Infra — RateLimiter 与结构化日志

**分支** `feat/core-infra` · **模型** sonnet · **Reviewer** sonnet · **并行组** Wave B（worktree）

**Files:**
- Create: `src/paper_crawler/ratelimit.py`、`src/paper_crawler/obslog.py`、`tests/unit/test_ratelimit.py`、`tests/unit/test_obslog.py`

**Interfaces:** Consumes §2.2 RatePolicy；Produces §2.6。

要点与步骤：
- [ ] Token bucket：容量=burst，速率=rpm/60 token/s（乘 `scale`）；`acquire` 无 token 时返回到下个 token 的等待秒并预登记消费（连续 acquire 排队累加）；注入 `clock`（monotonic float）。数学单测：rpm=60/burst=1 时连续 3 次 acquire 返回 ≈(0, 1.0, 2.0)（fake clock 不推进）；fake clock 推进 1.5s 后 acquire → 0。
- [ ] `register` 重复注册与 `override` 均取更小 rpm（design/05 §3"最保守值"）。
- [ ] obslog：jsonl 文件 `log_dir/crawler-YYYYMMDD.jsonl`（追加）；控制台 INFO+ 人读单行（`[level] venue/stage msg`）；`redact` 单测用例族：`Cookie: session=abc123` → `Cookie: ***`；URL `?api_key=xyz&x=1` → `?api_key=***&x=1`；`Authorization: Bearer tok` → `***`；正常文本不变。log_event 写入的 url 字段强制过 redact。
- [ ] 测试含"jsonl 行可被 json.loads 且键集合正确、None 键省略"。

**DoD**：对应单测绿；`make check` 绿。

---

### Task 5: Tasks — 队列与状态机

**分支** `feat/core-tasks` · **模型** opus · **Reviewer** opus · **并行组** Wave C（worktree）

**Files:**
- Create: `src/paper_crawler/tasks.py`、`tests/unit/test_task_queue.py`、`tests/unit/test_task_statemachine.py`

**Interfaces:** Consumes §2.4 Database、§2.1 RETRY_TABLE；Produces §2.5。

要点与步骤：
- [ ] 状态机转移矩阵**全覆盖测试**：5 状态×5 目标全枚举，合法 4+2 条通过、其余 IllegalTransition（design/05 §8"含非法转移拒绝"）。
- [ ] 入队去重：同 canonical_params 的 PENDING/RUNNING 存在 → `duplicate`（利用 T2 的 partial unique index，捕获 IntegrityError 转 duplicate——竞态安全）；DONE 存在且未过 FRESHNESS_TTL → `fresh_skip`（`force=True` 绕过）。
- [ ] `fail()`：查 RETRY_TABLE；RATE_LIMITED 不增 attempts（05 §4"不计失败"）；attempts 达上限 → FAILED 落 error_class/last_error。
- [ ] `block()` 不动 attempts；`resume` 支持单个与 `--all`；`retry_failed` 按 error_class 过滤（05 §2 `retry --class transient`）。
- [ ] 时钟注入测新鲜度：DONE 后 23h（clock 前拨）→ fresh_skip；25h → enqueued。

**DoD**：对应单测绿；`make check` 绿。

---

### Task 6: Mock adapter 实现 + 契约测试 + golden 基建

**分支** `feat/core-mock-adapter` · **模型** sonnet · **Reviewer** sonnet · **并行组** Wave C（worktree）

**Files:**
- Modify: `src/paper_crawler/adapters/mock_platform.py`（骨架→实现）
- Create: `tests/contract/__init__.py`、`tests/contract/test_adapter_contract.py`、`tests/fixtures/README.md`、`tests/fixtures/mock_platform/golden/timeline.json`、`tests/fixtures/mock_platform/golden/issue-v1n1.json`、`tests/helpers/golden.py`、`tests/unit/test_mock_platform.py`

**Interfaces:** Consumes §2.2/2.3；Produces mock 语料规格（下）与 golden helper `assert_matches_golden(obj, path)`（env `UPDATE_GOLDEN=1` 重录，重录必须人工 diff——test-plan §2）。

Mock 语料规格（**确定性，全部派生自 quirks**）：
- quirks: `volumes`(默认 3→year 2024+i)、`issues_per_volume`(2)、`papers_per_issue`(5)、`seed`(42)；
- IssueRef: volume=`"1".."3"`、number=`"1"/"2"`、year、label=None、paper_count_claimed=papers_per_issue；
- PaperStub: title=`"Mock Paper {v}.{n}.{i}: {adj} {noun}"`（词表 seed 取样）、identifiers=(("doi", `"10.9999/{venue_id}.{v}.{n}.{i}"`),)、authors 固定表轮转 2 人、year 随卷；
- resolve → 1 个 AssetPlan(kind=PDF, url=`"https://mock.local/pdf/{doi}"`, auth_needed=NONE)；
- fetch → 经 `io.write_stream` 写确定性字节：`b"%PDF-1.4\n% " + doi + b"\n" + b"0"*2048 + b"\n%%EOF\n"`；
- 故障注入 quirks（恒定、无状态——测试通过改 YAML 解除，模拟"人工修复"）：
  - `fail_fetch: {"error_class": "auth_expired", "paper_indexes": [0,1]}` → 对期内第 0/1 篇 fetch 抛 `CrawlerError(AUTH_EXPIRED)`；error_class 可为九类任意值；
  - `fail_enumerate: {"volume": "2", "number": "1"}` → 该期 enumerate 抛 PARSE；
  - `fetch_delay_ms: 200` → fetch 前 sleep（kill-9 测试窗口）。

契约测试（test-plan T2 类）：参数化遍历 `load_adapters()`：
- 元数据完备：adapter_id 非空、default_rate.source_note 非空、domains 非空；
- 声明 DISCOVER/ENUMERATE/RESOLVE/FETCH 者对 **contract venue**（mock: 测试内构造 VenueSpec；stubs: `pytest.skip(reason="stub until Phase 2/3/4")`）产出合法非空结果、PaperStub 至少 1 identifier；
- 未声明能力的方法调用 → `CapabilityNotSupported`。

**DoD**：契约+mock 单测+golden 用例绿；`make check` 绿。

---

### Task 7: Pipeline — 六阶段执行器与断点续爬

**分支** `feat/core-pipeline` · **模型** opus · **Reviewer** opus · **串行**（Wave D）

**Files:**
- Create: `src/paper_crawler/pipeline/__init__.py`、`pipeline/report.py`、`pipeline/stages.py`、`pipeline/runner.py`、`pipeline/fetchio.py`、`tests/integration/__init__.py`、`tests/integration/test_pipeline_e2e.py`、`tests/integration/test_pipeline_errors.py`、`tests/unit/test_report.py`、`tests/unit/test_fetchio.py`

**Interfaces:** Consumes §2.4/2.5/2.6/2.8 全部；Produces §2.7 PipelineRunner/RunReport/StageContext。

语义要点（全部出自 design/05，段落号已注）：
- [ ] `pull` 级联（§1）：pull 父任务 → discover（新鲜度内跳过）→ 按 Selector 圈定 issues → enumerate（事务粒度=一期，§5.1）→ resolve（每 paper）→ fetch（每 planned asset）→ [--extract] → ingest 尾部自动跑。子任务 parent_id 溯源。
- [ ] dry-run（§6）：完成到 resolve 为止；报告 planned_downloads/planned_bytes（mock: 每 asset 估 2KB 级真实字节数——取 resolve 后已知长度或估值）；**不执行 fetch、data/ 零写入**（AC-1.2）。
- [ ] fetch 原子性（§5.2）：`fetchio.py` 的 `PartFileIO` 写 `data/tmp/{asset_id}.part` → 校验（expected_type=pdf 时魔数 `%PDF` + bytes>0；sha256 计算）→ 原子 `os.replace` 到 `data/pdf/{venue_id}/{year}/{paper_ulid}.pdf`（布局 design/06 §4）→ `mark_asset(fetched)` → `add_fetch_log`（含 rate_wait_ms）。runner 启动时清理 `data/tmp/*.part`（§5.2）。
- [ ] 幂等跳过（§5.3）：asset 已 fetched 且文件存在＆sha256 合 → 计 skipped 并 `log_event(..., msg="skipped")`；enumerate/discover 依赖 upsert 幂等 + 任务新鲜度。
- [ ] 错误分类路由（§4）：CrawlerError.error_class → AUTH_EXPIRED/CHALLENGE/CONFIG → `queue.block()`（AUTH_EXPIRED 整批：同 venue 后续 fetch 子任务连带 BLOCKED，§4"整批 BLOCKED(auth)"）；TRANSIENT/RATE_LIMITED/INTEGRITY 按 RETRY_TABLE 经 `queue.fail()` 回 PENDING（退避 sleep×retry_scale）；GONE → asset state=gone、任务 DONE（预期内跳过）；PARSE/NO_ENTITLEMENT → FAILED/标记。非 CrawlerError 异常 → TRANSIENT 处置并记日志。
- [ ] 限速接入：每次 adapter 网络型调用（discover/enumerate/resolve/fetch——mock 虽本地仍走全流程）前 `limiter.acquire(domain)` → `sleeper(wait)`；wait 记入 FetchLog.rate_wait_ms（fetch 阶段）。
- [ ] 集成测试（进程内）：端到端 pull mock_journal --year 2024 → counts 断言（2 期/10 papers/10 assets fetched/文件数=10）；dry-run 零副作用；fail_fetch 注入 → BLOCKED 与连带；fail_enumerate → FAILED(parse)；GONE 注入 → gone 不重试。

**DoD**：集成+单测绿；`make check` 绿（覆盖率此时可能仍 <80% 整体——T9 补齐，本任务不降门禁：Makefile 门禁自 T1 起生效，故本任务需保住 ≥80%，缺口补对应单测）。

---

### Task 8: CLI — crawler 子命令全套

**分支** `feat/core-cli` · **模型** opus · **Reviewer** opus · **串行**（Wave E）

**Files:**
- Create: `src/paper_crawler/cli.py`、`src/paper_crawler/verify.py`、`tests/integration/test_cli.py`、`tests/unit/test_verify.py`
- Modify: `pyproject.toml`（scripts 入口指向 `paper_crawler.cli:main`）

**Interfaces:** Consumes §2.7/2.8；Produces CLI 命令面（design/05 §6 Phase 1 子集）：

```
crawler venues list [--field F] [--tier T]
crawler venues lint
crawler timeline VENUE [--refresh]
crawler list VENUE (--volume V [--issue I] | --year Y)
crawler pull VENUE (--volume V [--issue I] | --year Y | --doi D ...)
             [--filter EXPR] [--limit N] [--dry-run] [--extract] [--force]
crawler status [--blocked] [--failed]
crawler resume [TASK_ID | --all]
crawler retry [--class ERROR_CLASS]
crawler verify
crawler report [--last-run]
全局: --home PATH（等价 $PAPER_CRAWLER_HOME）、--verbose
```

- [ ] 退出码契约（测试断言）：`0` 成功；`1` 有 failed；`2` 用法/配置错（lint 有错、未知 venue）；`3` 无 failed 但有 blocked。
- [ ] `status --blocked` 输出含人工动作提示（design/05 §2：如 `resume` 指引；auth 提示 Phase 4 落地，Phase 1 打印 blocked_reason）。
- [ ] `verify.py`（design/05 §5.4 基础版，AC-3.3 正式验收在 Phase 3）：DB↔文件双向对账，检出 缺文件/孤儿文件/哈希不符，输出修复建议（re-fetch / adopt / quarantine），不自动修。
- [ ] `report`：打印最近 RunReport（reports_dir/last-run.md）。
- [ ] CLI 集成测试用 `subprocess.run([...,"--home",tmp])` + `typer.testing.CliRunner` 双层：冒烟 venues lint(合法 0/非法 2)、timeline、list、pull mock（成功 0）、status、report。

**DoD**：CLI 测试绿；`uv run crawler venues lint` 对仓库 venues/ 通过；`make check` 绿。

---

### Task 9: 验收加固 — AC-1 自动化与覆盖率

**分支** `test/core-acceptance` · **模型** opus · **Reviewer** opus · **串行**（Wave E 尾）

**Files:**
- Create: `tests/integration/test_ac_killresume.py`、`tests/integration/test_ac_dryrun.py`、`tests/integration/test_ac_ratelimit.py`、`tests/integration/test_ac_blocked_resume.py`、`tests/helpers/dbdump.py`、（按需补单测提覆盖率）

要点：
- [ ] **AC-1.3 kill-9**：`subprocess.Popen(crawler pull ... env={PAPER_CRAWLER_HOME: home_a})`，`fetch_delay_ms=150` + rpm 放开；随机 0.3–1.2s 后 `SIGKILL`；循环 ≥3 次后完整跑至退出 0；对照 home_b 一次跑完。断言：**canonical dump 一致**（口径见下）＋ 每 asset 成功 fetch_log ≤1 ＋ 重跑日志含 skipped。
- [ ] **canonical dump 口径**（写入 `tests/helpers/dbdump.py` docstring，验收记录引用）：比较表=venue/issue/paper/identifier/asset(+paper_issue_link)；剔除 volatile 列 id/created_at/updated_at/fetched_at/file_path（ULID 与时钟不可复现）；行序按业务键（issue: venue,volume,number；paper: title；identifier: scheme,value；asset: (paper.title,kind,version)+bytes+sha256+state）；task/fetch_log 不参与逐行对比（历史轨迹合法地不同），单独断言上一条。
- [ ] **AC-1.2 dry-run**：dry-run 后 `data/` 目录树快照无新增、DB 无 state=fetched、report.planned_downloads==随后实跑 succeeded。
- [ ] **AC-1.4 限速**：venue rate_limit rpm=600、30 fetch 真实时钟；fetch_log 按 domain 取 ts 序列，滑动窗口速率 ≤600×1.05。另单元级 fake-clock 精确曲线已在 T4。
- [ ] **AC-1.5**：fail_fetch auth_expired → 2 task BLOCKED（attempts==0）→ 改临时 venues YAML 移除注入 → `crawler resume --all` → 重跑 pull 退出 0、counts 齐。
- [ ] **AC-1.1/1.6** 已由 T7/T3 测试覆盖——此处补 CLI 层端到端断言（报告"成功=N 失败=0"字样）。
- [ ] 覆盖率补齐至 ≥80%（`make test` 门禁）；缺口优先补 stages/runner/cli 分支路径。

**DoD**：`make check` 绿（含 80% 门禁）；AC-1.1~1.6 每条至少一个自动化测试映射（测试 docstring 标 `Closes: AC-1.x`）。

---

### Task 10: 收尾 — 验收留痕、文档状态流转、tag（主 agent 亲自）

**分支** `docs/phase1-closeout` · **执行** fable5 主 agent

- [ ] 全量跑 T1–T4 测试 + AC 套件，采集输出与 commit hash，写 `docs/testing/records/2026-07-XX-phase1-acceptance.md`（模板：代码 commit、每条 AC、命令、判据、结果、日志片段路径——test-plan §7）。
- [ ] design/01/02/05/06 front matter `status: implemented` + `updated`；正文如有实现期勘误（§2.4 注记的 paper_issue_link DDL 补全、task.kind 含 pull 的说明）以勘误性修改并入，提交信息注明。
- [ ] INDEX.md：四篇状态列、计划文档行（→approved 已在计划定稿时登记，收尾核对）、testing/records 新行。
- [ ] progress.md：Phase 1 → done、快照更新、新增**模块状态表**（status-workflow §4：registry/storage/tasks/ratelimit/obslog/pipeline/cli/mock_platform 各行 state=stable）。
- [ ] `docs/logs/2026-07-XX-session-005.md` session 日志；`docs/reports/2026-07-XX-phase1-report.md` 阶段报告（DoD 逐项判定）。
- [ ] 合 main 后：`git tag -a phase-1 -m ...`（指向报告提交）、`git tag -a schema-v1`（git-workflow §5）。

---

## 执行期重排记录（2026-07-21，用户指令：提高并行度）

交付物与 DoD 不变，任务边界重切：**T7 拆为 T7a(fetchio)/T7b(report)/T7c(stages+runner)**，**T8 拆出 T8a(verify+dbdump 前置)**，T8b(CLI 主体) 变薄改派 sonnet（审查仍 opus）。模型按难度分层（2026-07-21 用户指令）：T7c 为 Phase 1 最复杂集成件，implementer 升配 **fable 档**；最终全分支审查亦用 fable 档。T7a/T7b/T8a 与 T5/T6 五线并行（文件零交集）；关键路径缩为 T7c→T8b→T9。补充冻结签名：

```python
# pipeline/fetchio.py（T7a）
class PartFileIO:                      # FetchIO 实现
    def __init__(self, tmp_dir: Path, asset_id: str): ...
    def write_stream(self, chunks: Iterable[bytes]) -> tuple[int, str]   # 写 {asset_id}.part，返回 (bytes, sha256)
    @property
    def part_path(self) -> Path
    def commit(self, final_path: Path) -> None    # 父目录 mkdir -p + os.replace 原子落位
    def abort(self) -> None                       # 删 .part（幂等）
def validate_pdf_magic(path: Path) -> bool        # 头部 %PDF-
def cleanup_tmp(tmp_dir: Path) -> int             # 启动清理 *.part（design/05 §5.2），返回清理数

# verify.py（T8a；design/05 §5.4 基础版，AC-3.3 正式验收 Phase 3）
@dataclass(frozen=True)
class VerifyIssue:
    kind: Literal["missing_file", "orphan_file", "hash_mismatch"]
    asset_id: str | None
    file_path: str
    suggestion: Literal["re-fetch", "adopt", "quarantine"]
def verify_store(repo: Repo, data_dir: Path) -> list[VerifyIssue]
# missing_file→re-fetch；orphan_file→adopt；hash_mismatch→quarantine

# tests/helpers/dbdump.py（T8a；AC-1.3 canonical dump 口径的可执行定义）
def canonical_dump(db_path: Path) -> dict[str, list[tuple[object, ...]]]
# 表集=venue/issue/paper/identifier/asset/paper_issue_link；剔除 id/created_at/updated_at/fetched_at/file_path；
# 行序按业务键（Task 9 节口径）；task/fetch_log 不参与
```

## 审查协议（每任务）

1. Implementer 完成 → 报告（状态/提交列表/测试命令与结果/自审发现/concerns）落盘 scratchpad 报告文件。
2. 主 agent 生成 review package（`git diff BASE..HEAD` 全量 + stat + log）→ 独立 reviewer subagent。
3. Reviewer 双裁决：**Spec 合规**（对照任务节+引用设计文档：无缺失、无越界）+ **代码质量**（正确性/测试真实断言/日志脱敏/幂等）→ Critical/Important 必修，修复后重审；Minor 记入 ledger 由 T9/T10 统一处理。
4. 主 agent 合并 main（squash 不用，保留任务内提交）后跑 `make check` 方可开下一波。

## 风险与回退

| 风险 | 缓解 |
|---|---|
| 并行分支接口漂移 | §2 冻结件先行落盘（T1）；变更须主 agent 仲裁并同步计划 |
| kill-9 测试平台差异（macOS 信号语义） | 测试标记 `@pytest.mark.slow`；CI 门禁包含；不稳定时重试上限 3 次并记录 |
| 覆盖率门禁与任务推进冲突 | 门禁自 T1 起常绿；每任务对自己模块负责 ≥80% |
| SQLite 并发写（WAL 单写者） | Phase 1 串行 runner 天然规避；tx 用 BEGIN IMMEDIATE 早失败 |
