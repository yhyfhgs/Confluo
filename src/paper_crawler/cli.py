"""`crawler` CLI —— 命令面接线（接口冻结件 §2.7/§2.8 的纯消费方，design/05 §6 命令面
的 Phase 1 子集）。

职责边界：本模块只做"接线"——把已冻结的 `PipelineRunner`/`VenueRegistry`/
`TaskQueue`/`verify_store`/`canary.run_canary` 等实物拼成命令行入口，不新增
业务语义。所有命令共用一个环境工厂 `_build_env`（`Config.load(home)` →
`setup_logging` → `Database`+`migrate` → `VenueRegistry.load_dirs` → 组装
`StageContext`），避免逐命令重复这套装配（任务书 Global Constraints 精神 +
phase1-implementation-plan Task 8 DoD）。`canary` 命令同样经 `_env` 走这套
装配以保持一致（复用其 Config/日志生命周期），但不消费 `StageContext` 里的
`registry`/`queue`/`limiter`——它只需要 `load_adapters()` 给出的原始 adapter
表，venue 层的路由与 canary 无关。

退出码契约（design/05 §6 + phase1-implementation-plan Task 8）：
- `0`：命令成功（含"报告 succeeded>0 或全 skipped"的正常结束）；
- `1`：产出一份 `RunReport` 且 `failed > 0`（pull/timeline/list）；
- `2`：用法/配置错误——未知 venue、`venues lint` 检出问题、Selector 冲突
  （如同时给 `--year` 与 `--volume`）、`resume` 缺参数、`retry --class` 给了
  未知 error_class、`canary --adapter` 给了未注册的 adapter id；
- `3`：产出一份 `RunReport` 且 `failed == 0` 但 `blocked > 0`。

`canary` 命令不产出 `RunReport`，退出码是独立的另一套契约（phase2-
implementation-plan §2.4，与上面的 0/1/3 判据无关，`2` 的用法错语义相同）：
- `0`：全部 adapter healthy（`NotImplementedError` 归的 SKIP 行不影响判定）；
- `1`：至少一个 adapter unhealthy（含 healthcheck 抛出非 `NotImplementedError`
  异常的情形）。

两个需要在此单独注记的实现选择（对应实物 API 不完全覆盖 CLI 语义的地方，
遵循"按 PipelineRunner 实物 API 选实现，选择写进 docstring"的指示）：

1. `timeline --refresh`：`PipelineRunner.run_single_stage` 是冻结签名
   （`(kind, venue_id, params) -> RunReport`，接口冻结件 §2.7），不接受
   `force`。而 `--refresh` 需要绕过入队新鲜度（24h fresh_skip）。解法：非
   `--refresh` 时走 `run_single_stage`（天然处理 fresh_skip 记账，与
   `crawler timeline` 反复调用的既有行为一致）；`--refresh` 时改为直接
   `TaskQueue.enqueue(..., force=True)` 再 `PipelineRunner.drain()`——
   `force=True` 保证 enqueue 永不落入 fresh_skip 分支，因此
   `run_single_stage` 相对"手工 enqueue+drain"多做的记账在这条路径下恰好是
   空操作，不丢语义，只是报告的 `command`/`venue_id` 标注从
   `"run discover"/venue` 变成 `"drain"/None`（纯展示层差异）。

2. `list`（清单预览，discover+enumerate 不下载）：`PipelineRunner` 没有"到
   enumerate 为止、覆盖多个 issue"的单一入口。经两次显式调用驱动：一次
   `run_single_stage("discover", ...)` 圈定 issue 范围，随后对该范围内每个
   issue 各调一次 `run_single_stage("enumerate", ...)`。副作用：每次
   `run_single_stage` 调用都会各自 `.save()` 一份 `reports_dir/last-run.md`
   （互相覆盖）——`crawler report --last-run` 在 `list` 之后看到的是"最后一个
   issue 的 enumerate 报告"而非合并结果；这是可接受的已知局限（`list` 本身的
   退出码与终端输出改为在 CLI 层对多份 `RunReport` 求和，不依赖某一份被保存的
   报告，见 `_fold_reports`）。

设计注记（T7c 审查产出，適用于 `pull`/`timeline`/`list` 三个驱动 `drain()` 循环
的命令）：`PipelineRunner.drain()`/内部 `_drain_loop` 领取的是**全局** PENDING
任务，不局限于本次命令新建的子任务——上次运行如果中途崩溃（kill -9 等）残留的
PENDING 任务，会在下一次任意 pipeline 命令运行时被顺带回收执行。这是断点续爬
机制的一部分，不是 bug；`status`/`resume`/`retry`/`verify`/`report` 是纯只读或
状态机操作命令，不构造 `PipelineRunner`，因此不触发其 `__init__` 的
`recover_running()`/`cleanup_tmp()` 副作用。
"""

from __future__ import annotations

import contextlib
import datetime as dt
import sqlite3
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from paper_crawler.adapter import (
    ApiKeyConsumer,
    CookieSupplier,
    EmailConsumer,
    EnrichmentSource,
    HttpClientConsumer,
    SourceAdapter,
    bind_cookie_supplier,
    bind_http_client,
    load_adapters,
)
from paper_crawler.adapters.crossref.adapter import CrossrefAdapter
from paper_crawler.adapters.nber import adapter as nber_adapter
from paper_crawler.adapters.nber.adapter import NberAdapter
from paper_crawler.adapters.openalex import budget as openalex_budget
from paper_crawler.adapters.openalex.adapter import OpenAlexAdapter
from paper_crawler.adapters.unpaywall import report as oa_report
from paper_crawler.adapters.unpaywall.adapter import UnpaywallAdapter
from paper_crawler.auth.cli import auth_app
from paper_crawler.auth.manager import AuthManager
from paper_crawler.canary import (
    canary_exit_code,
    canary_record_path,
    render_canary_markdown,
    render_canary_record,
    run_canary,
)
from paper_crawler.config import Config, ConfigLayer, describe_config
from paper_crawler.errors import CrawlerError, ErrorClass, IllegalTransition
from paper_crawler.http import HttpClient
from paper_crawler.ids import normalize_doi
from paper_crawler.merge import MergeEngine
from paper_crawler.obslog import log_event, redact, setup_logging
from paper_crawler.pipeline import PipelineRunner, RunReport, Selector, StageContext
from paper_crawler.pipeline.cooldown_cli import cooldown_app
from paper_crawler.ratelimit import RateLimiter
from paper_crawler.registry import VenueRegistry
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo, SubscriptionRepo
from paper_crawler.subs.report import render_daily
from paper_crawler.subs.types import RunSummary
from paper_crawler.subs.watch import (
    AdapterFetcher,
    NberRssFetcher,
    RoutingFetcher,
    SourceFetcher,
    WatchContext,
    exit_code_for,
    load_subscriptions,
    overload_brief,
    resolve_subscription,
    run_watch_all,
    write_daily_report,
)
from paper_crawler.tasks import TASK_STATES, TaskQueue
from paper_crawler.types import SessionHandle, VenueSpec
from paper_crawler.useragent import build_user_agent
from paper_crawler.verify import VerifyIssue, verify_store

# ---------------------------------------------------------------------------
# 全局选项（每条命令各自声明——Click 的解析模型不支持父组选项出现在子命令 token
# 之后，而 phase1-plan 的冒烟用例正是 `crawler pull ... --home <tmp>` 这种"选项
# 跟在子命令后面"的写法；共用同一对 Annotated 别名保持声明处的"全局"观感一致）。
# ---------------------------------------------------------------------------

HomeOpt = Annotated[
    Path | None,
    typer.Option("--home", help="运行时目录；等价 $PAPER_CRAWLER_HOME，且优先于它"),
]
VerboseOpt = Annotated[
    bool, typer.Option("--verbose", help="控制台日志级别调到 DEBUG（文件日志恒全量）")
]


# ---------------------------------------------------------------------------
# 环境工厂：全命令入口统一 Config.load(home) + setup_logging + Database/migrate
# + 组装 StageContext（本函数是唯一装配点，逐命令不得复制这套逻辑）。
# ---------------------------------------------------------------------------


@dataclass
class CliEnv:
    """一次命令调用的已装配环境。"""

    ctx: StageContext
    http: HttpClient
    # openreview 专属 token client（有 token 时构造，绝不复用共享 http——见
    # `_bind_openreview_token_client`）；无 token 时 None（openreview 沿用共享 http）。
    openreview_http: HttpClient | None = None
    # AuthManager（`auth=True` 装配，pull/grab 用）：auth_gated venue 的 provider/session
    # 解析入口（§8.2）；无 auth 装配的命令为 None。传入 `PipelineRunner(auth_manager=...)`。
    auth_manager: AuthManager | None = None


def _http_client_factory(config: Config, rate_limiter: RateLimiter | None = None) -> HttpClient:
    """从 config 组装 D-014 UA 的共享 `HttpClient`（真实 adapter 注入用）。

    UA `mailto:` 段取 `config.identity_email`（缺省 None → 省略 mailto，见
    `build_user_agent`）——优先级 **显式注入 > config > env**：本 client 经
    `bind_http_client` 注入 arxiv 等 adapter，覆盖其惰性 env 兜底（T5 过渡路径）。
    模块级函数是测试注入 `MockTransport` client 的 seam（零真实网络）。

    `rate_limiter`（C4 红线修复，plan §7-6）= pipeline `StageContext.limiter` 同一实例，
    使 adapter 内部翻页的逐请求限速与 pipeline 的 per-stage 限速落到同一预算（同桶共享）。
    """
    return HttpClient(user_agent=build_user_agent(config.identity_email), rate_limiter=rate_limiter)


def _openreview_client_factory(
    config: Config, rate_limiter: RateLimiter | None = None
) -> HttpClient:
    """构造 openreview 携 token cookie 的**专属** client（openreview.md §3）。

    client 级附加头 `Cookie: openreview.accessToken=<token>`（config.openreview_token，
    调用方须已确认非空）；共享 limiter 同桶计费。模块级函数是测试注入 `MockTransport`
    client 的 seam（零真实网络），与 `_http_client_factory` 对称。
    """
    return HttpClient(
        user_agent=build_user_agent(config.identity_email),
        rate_limiter=rate_limiter,
        extra_headers={"Cookie": f"openreview.accessToken={config.openreview_token}"},
    )


def _bind_openreview_token_client(
    adapters: dict[str, SourceAdapter], config: Config, rate_limiter: RateLimiter
) -> HttpClient | None:
    """有 token 时为 openreview adapter 注入携 cookie 的专属 client（openreview.md §3）。

    token 缺省 → 返回 None：openreview 沿用 `bind_http_client` 注入的共享匿名 client
    （groups/healthcheck 可用，notes/pdf 会 403→auth_expired→BLOCKED，status 给配置指引）。
    有 token → 经 `_openreview_client_factory` 构造独立 client 并注入，**绝不把 cookie
    挂到共享 http**（否则随 arxiv 等请求外泄他站，凭证红线）。返回专属 client（供 `_env`
    关闭）或 None。
    """
    if not config.openreview_token:
        return None
    adapter = adapters.get("openreview")
    if not isinstance(adapter, HttpClientConsumer):
        return None
    client = _openreview_client_factory(config, rate_limiter)
    adapter.set_http_client(client)
    return client


def _cookie_supplier_for(manager: AuthManager) -> CookieSupplier:
    """构造 OUP（及未来 cookie 档 adapter）的**懒解析** cookie 供给闭包（auth-framework §8.2）。

    闭包捕获 `manager`；仅当**真实 fetch** 触达 adapter 的 `_cookies_for(session)` 时才被调用
    ——据 `session.provider_id`（runner `ensure_session(provider.provider_id)` 建立该 session
    的 provider 键）经 `AuthManager.resolve` 拿到对应 provider → `load_cookies` 解密
    storage_state → httpx cookie jar → `dict`。故装配期不触发（无 session 即不调用）：离线
    pull（无 auth_gated venue 命中 fetch）与无凭证配置时装配期零解析、不抛 CONFIG。

    provider 无 `load_cookies`（cookie 档 venue 却映射到 api_key 等非 cookie provider）→ 响亮
    CONFIG（装配/路由缺陷）。cookie 隔离由 adapter 内部专属携密 client 承担，本闭包只返 cookie 表。
    """

    def _supply(session: SessionHandle) -> Mapping[str, str]:
        provider = manager.resolve(session.provider_id)
        load_cookies = getattr(provider, "load_cookies", None)
        if load_cookies is None:
            raise CrawlerError(
                ErrorClass.CONFIG,
                f"auth provider {session.provider_id!r} 无 load_cookies（cookie 档 venue 须映射 "
                "cookie_session/sso_flow profile）",
            )
        return dict(load_cookies(session))

    return _supply


def _assemble_auth_seam(
    config: Config,
    adapters: dict[str, SourceAdapter],
    ctx: StageContext,
    http: HttpClient,
    limiter: RateLimiter,
) -> AuthManager:
    """pull/grab 的 auth/OA-fallback 接缝装配（auth-framework §8；纯附加，默认关闭之外的启用点）。

    - OA-fallback（§8.1）：配置 unpaywall adapter（共享 `http` + `Config.identity_email` +
      主域限速登记）注入 `StageContext.unpaywall_adapter`/`http`，并置 `oa_fallback=True`
      （no_entitlement 兜底总开关）。
    - AuthManager（§8.2）：`[auth].active_profile` 从 config 接线（T1b 留的构造参数注入点；
      config 尚无该键时为 None → platform 单候选自动解析）。auth_gated venue 的健康门/日配额/
      工作时段窗/挑战冷却均由 runner 经该 manager 驱动。
    """
    ua = adapters.get("unpaywall")
    if isinstance(ua, UnpaywallAdapter):
        if isinstance(ua, HttpClientConsumer):
            ua.set_http_client(http)  # 共享 UA + limiter（同桶计费）
        if isinstance(ua, EmailConsumer):
            ua.set_email(config.identity_email)  # ?email= 查询参数（aggregators §3）
        limiter.register(ua.domains[0], ua.default_rate)  # api.unpaywall.org 独立桶
        ctx.unpaywall_adapter = ua
    ctx.http = http
    ctx.oa_fallback = True
    active_profiles = getattr(config, "auth_active_profile", None)
    manager = AuthManager(config, active_profiles=active_profiles)
    # OUP（oup_silverchair，已合入 main 且在此装配）及未来 cookie 档 adapter 的 cookie 供给：把
    # 懒解析闭包注入所有 duck-typed `CookieSupplierConsumer`（`set_cookie_supplier`）。闭包捕获
    # 上面的 `manager`，仅真实 fetch 时才按 session.provider_id 解析 provider→load_cookies（装配
    # 期不触发、无凭证配置不抛，见 `_cookie_supplier_for`）。限速不在此层：OUP fetch 由 pipeline
    # per-stage `acquire_and_wait` 依 default_rate 逐阶段兜住（stages.py `_stage_fetch`）；cookie
    # 只挂 adapter 内部专属携密 client（凭证隔离红线，绝不复用共享 http/limiter）。
    bind_cookie_supplier(adapters, _cookie_supplier_for(manager))
    return manager


def _build_env(
    home: Path | None, verbose: bool, *, dry_run: bool = False, auth: bool = False
) -> CliEnv:
    config = Config.load(home)
    config.ensure_dirs()
    setup_logging(config.log_dir, console_level="DEBUG" if verbose else "INFO")

    db = Database(config.db_path)
    db.migrate()
    repo = Repo(db)
    adapters = load_adapters()
    # C4 红线修复：limiter 先建，作为**同一实例**既进 StageContext（per-stage 限速）又进
    # HttpClient（逐请求限速，含 adapter 内部翻页），保证同桶共享、不放宽速率。
    limiter = RateLimiter(scale=config.rate_scale)
    http = _http_client_factory(config, limiter)
    bind_http_client(adapters, http)  # config UA + 共享 limiter 注入 http adapter（arxiv 等）
    # openreview token 通道：有 token 时覆盖为携 cookie 的专属 client（§3；绝不污染共享 http）。
    openreview_http = _bind_openreview_token_client(adapters, config, limiter)
    registry = VenueRegistry(adapters)
    registry.load_dirs(list(config.venues_dirs))
    queue = TaskQueue(db)

    stage_ctx = StageContext(
        config=config,
        db=db,
        repo=repo,
        registry=registry,
        queue=queue,
        limiter=limiter,
        dry_run=dry_run,
    )
    # pull/grab（auth=True）：装配 auth/OA-fallback 接缝（§8；其余命令 auth_manager=None）。
    auth_manager = _assemble_auth_seam(config, adapters, stage_ctx, http, limiter) if auth else None
    return CliEnv(
        ctx=stage_ctx, http=http, openreview_http=openreview_http, auth_manager=auth_manager
    )


@contextlib.contextmanager
def _env(
    home: Path | None, verbose: bool, *, dry_run: bool = False, auth: bool = False
) -> Iterator[CliEnv]:
    """`_build_env` 的上下文管理器包装：命令结束（正常或 `typer.Exit`）时关闭 DB + http。

    CLI 每次调用在真实使用中对应一个独立进程（连接随进程退出自然释放）；
    `typer.testing.CliRunner` 是进程内反复调用同一 Python 解释器，必须显式
    `close()` 避免一次测试函数内多次调用间的连接堆积。

    **分层加载护栏（D-025）**：`_build_env` 首行 `Config.load` 若命中项目级敏感键护栏
    （`./paper-crawler.toml` 含凭证形态键）→ `CrawlerError(CONFIG)`；在此统一转 `typer.Exit(2)`
    优雅拒启动（此前 Config.load 从不抛 CrawlerError，本 catch 纯附加，覆盖所有走 `_env`
    的命令）。同一 catch 亦覆盖 `Config.load` 的另一条 CrawlerError(CONFIG) 路径——家目录/
    项目级 config.toml 语法错误（`config.py::_load_toml`，2026-07-26 归类修正）。此时尚未开
    DB/日志，无资源需清理。
    """
    try:
        cli_env = _build_env(home, verbose, dry_run=dry_run, auth=auth)
    except CrawlerError as exc:
        _echo_error(exc)
        raise typer.Exit(code=2) from exc
    try:
        yield cli_env
    finally:
        cli_env.http.close()
        if cli_env.openreview_http is not None:
            cli_env.openreview_http.close()
        cli_env.ctx.db.close()


# ---------------------------------------------------------------------------
# 共用小件：错误呈现、退出码、表格渲染、Selector 范围参数
# ---------------------------------------------------------------------------


def _usage_error(message: str) -> NoReturn:
    """用法/配置错误的统一出口：打印到 stderr 并以退出码 2 终止（design/05 Task 8）。"""
    typer.echo(f"错误: {message}", err=True)
    raise typer.Exit(code=2)


def _echo_error(exc: Exception) -> None:
    typer.echo(f"错误: {exc}", err=True)


@dataclass(frozen=True)
class _Totals:
    succeeded: int
    failed: int
    blocked: int
    skipped: int


def _fold_reports(reports: list[RunReport]) -> _Totals:
    """把多份 `RunReport`（`list` 命令的 discover+多个 enumerate 调用）按计数求和。"""
    return _Totals(
        succeeded=sum(r.succeeded for r in reports),
        failed=sum(r.failed for r in reports),
        blocked=sum(r.blocked for r in reports),
        skipped=sum(r.skipped for r in reports),
    )


def _totals_exit_code(totals: _Totals) -> int:
    """退出码契约核心判据：1（有 failed）> 3（无 failed 有 blocked）> 0。"""
    if totals.failed > 0:
        return 1
    if totals.blocked > 0:
        return 3
    return 0


def _report_exit_code(report: RunReport) -> int:
    return _totals_exit_code(
        _Totals(report.succeeded, report.failed, report.blocked, report.skipped)
    )


def _render_table(headers: list[str], rows: list[list[str]]) -> str:
    """极简等宽表格渲染（不引入 rich——pyproject 计划外依赖，Global Constraints §4）。"""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt(cells: list[str]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    lines = [fmt(headers), fmt(["-" * w for w in widths])]
    lines.extend(fmt(row) for row in rows)
    return "\n".join(lines)


def _scope_params(volume: str | None, issue: str | None, year: int | None) -> dict[str, object]:
    """discover 子任务的范围参数：None 键省略（与 pull 级联对同一范围产生相同的
    discover 幂等键，`list`/`timeline --refresh` 前不重复真实工作）。"""
    scope: dict[str, object] = {}
    if volume is not None:
        scope["volume"] = volume
    if issue is not None:
        scope["issue"] = issue
    if year is not None:
        scope["year"] = year
    return scope


def _papers_in_scope(repo: Repo, venue_id: str, issues: list[sqlite3.Row]) -> list[sqlite3.Row]:
    """圈定 issues 内的 papers，跨 issue 去重、保持发现顺序（`list` 命令的预览负载）。"""
    seen: set[str] = set()
    out: list[sqlite3.Row] = []
    for issue_row in issues:
        for paper in repo.list_papers(venue_id, issue_id=str(issue_row["id"])):
            paper_id = str(paper["id"])
            if paper_id in seen:
                continue
            seen.add(paper_id)
            out.append(paper)
    return out


def _print_issue_table(issues: list[sqlite3.Row]) -> None:
    rows = [
        [
            str(r["volume"]) if r["volume"] is not None else "-",
            str(r["number"]) if r["number"] is not None else "-",
            str(r["year"]) if r["year"] is not None else "-",
            str(r["label"]) if r["label"] is not None else "-",
        ]
        for r in issues
    ]
    typer.echo(_render_table(["volume", "number", "year", "label"], rows))


def _print_paper_table(papers: list[sqlite3.Row]) -> None:
    rows = [[str(p["title"]), str(p["year"]) if p["year"] is not None else "-"] for p in papers]
    typer.echo(_render_table(["title", "year"], rows))


def _require_known_venue(env: CliEnv, venue_id: str) -> None:
    """`timeline`/`list` 的显式 fail-fast：二者经 `run_single_stage`/手工 enqueue
    驱动，未知 venue 不会像 `PipelineRunner.pull` 那样抛出——discover handler 内部
    的 `registry.route()` 失败会被 drain 循环捕获为 CONFIG → 任务 BLOCKED，而非
    异常，若不在此提前拦截，退出码会变成"3（blocked）"而非契约要求的"2（配置错）"。
    `pull` 不需要这一步：`PipelineRunner.pull` 已经在入队前 fail-fast 抛
    `CrawlerError(CONFIG)`（docstring 明示"不产生任何任务"），CLI 在调用处直接
    捕获该异常即可，无需重复查一次。
    """
    try:
        env.ctx.registry.get(venue_id)
    except CrawlerError as exc:
        _echo_error(exc)
        raise typer.Exit(code=2) from exc


# ---------------------------------------------------------------------------
# Typer app
# ---------------------------------------------------------------------------

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="可插拔式学术论文获取系统 —— crawler 命令行。",
)
venues_app = typer.Typer(no_args_is_help=True, help="venue 注册表浏览与校验。")
app.add_typer(venues_app, name="venues")
config_app = typer.Typer(no_args_is_help=True, help="生效配置自查（分层来源 + 脱敏）。")
app.add_typer(config_app, name="config")
# T1b（auth-framework §1/§4）：auth 子命令组（login/status/logout）——实现与纯逻辑
# 在 `auth/cli.py` + `auth/manager.py`，此处只挂载（既有分工：cli.py 仅接线）。
app.add_typer(auth_app, name="auth")
# E-2（检查单 #7 / D-030 裁决点④）：cooldown 子命令组（status/clear）——实现与纯逻辑
# 在 `pipeline/cooldown_cli.py` + `pipeline/cooldown.py`，此处只挂载（同 auth 分工）。
app.add_typer(cooldown_app, name="cooldown")


# -- venues -------------------------------------------------------------------


@venues_app.command("list")
def venues_list(
    field: Annotated[str | None, typer.Option("--field", help="按 field 过滤")] = None,
    tier: Annotated[str | None, typer.Option("--tier", help="按 tier 过滤")] = None,
    home: HomeOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """浏览已注册 venue（`VenueRegistry.all()`），可选按 field/tier 过滤。"""
    with _env(home, verbose) as env:
        venues = env.ctx.registry.all()
        if field is not None:
            venues = [v for v in venues if field in v.field]
        if tier is not None:
            venues = [v for v in venues if v.tier == tier]
        rows = [[v.id, v.kind, ",".join(v.field), v.tier or "-", v.status] for v in venues]
        typer.echo(_render_table(["id", "kind", "field", "tier", "status"], rows))
    raise typer.Exit(code=0)


@venues_app.command("lint")
def venues_lint(home: HomeOpt = None, verbose: VerboseOpt = False) -> None:
    """VenueSpec 结构性+语义校验（`VenueRegistry.lint()`）；有问题逐条打印并退出 2。"""
    with _env(home, verbose) as env:
        issues = env.ctx.registry.lint()
        for issue in issues:
            typer.echo(f"{issue.file}:{issue.venue_id or ''}:{issue.field}: {issue.message}")
        if issues:
            exit_code = 2
        else:
            typer.echo(f"OK：{len(env.ctx.registry.all())} 个 venue 全部通过 lint。")
            exit_code = 0
    raise typer.Exit(code=exit_code)


# -- timeline -------------------------------------------------------------------


@app.command()
def timeline(
    venue: Annotated[str, typer.Argument(help="venue id")],
    refresh: Annotated[
        bool, typer.Option("--refresh", help="忽略新鲜度窗口，强制重新 discover")
    ] = False,
    home: HomeOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """时间轴（discover 单阶段；`--refresh` 语义见模块 docstring 第 1 条）。"""
    with _env(home, verbose) as env:
        _require_known_venue(env, venue)
        runner = PipelineRunner(env.ctx)
        if refresh:
            env.ctx.queue.enqueue("discover", venue, {}, force=True)
            report = runner.drain()
        else:
            report = runner.run_single_stage("discover", venue, {})
        issues = env.ctx.repo.list_issues(venue)
        _print_issue_table(issues)
        typer.echo(report.render_markdown())
        exit_code = _report_exit_code(report)
    raise typer.Exit(code=exit_code)


# -- list -------------------------------------------------------------------


@app.command("list")
def list_cmd(
    venue: Annotated[str, typer.Argument(help="venue id")],
    volume: Annotated[str | None, typer.Option("--volume")] = None,
    issue: Annotated[str | None, typer.Option("--issue")] = None,
    year: Annotated[int | None, typer.Option("--year")] = None,
    home: HomeOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """清单预览：discover+enumerate 圈定范围内的 papers，不下载资产（design/05 §6）。

    实现选择见模块 docstring 第 2 条。
    """
    if volume is not None and year is not None:
        _usage_error("--volume 与 --year 不能同时指定")
    if issue is not None and volume is None:
        _usage_error("--issue 必须搭配 --volume 使用")
    if volume is None and year is None:
        _usage_error("必须指定 --volume 或 --year 之一")

    with _env(home, verbose) as env:
        _require_known_venue(env, venue)
        runner = PipelineRunner(env.ctx)

        reports = [runner.run_single_stage("discover", venue, _scope_params(volume, issue, year))]
        issues = env.ctx.repo.list_issues(venue, volume=volume, number=issue, year=year)
        for row in issues:
            reports.append(runner.run_single_stage("enumerate", venue, {"issue": str(row["id"])}))

        papers = _papers_in_scope(env.ctx.repo, venue, issues)
        _print_paper_table(papers)
        totals = _fold_reports(reports)
        typer.echo(
            f"成功 {totals.succeeded} 失败 {totals.failed} "
            f"阻塞 {totals.blocked} 跳过 {totals.skipped}"
        )
        exit_code = _totals_exit_code(totals)
    raise typer.Exit(code=exit_code)


# -- pull -------------------------------------------------------------------


@app.command()
def pull(
    venue: Annotated[str, typer.Argument(help="venue id")],
    volume: Annotated[str | None, typer.Option("--volume")] = None,
    issue: Annotated[str | None, typer.Option("--issue")] = None,
    year: Annotated[int | None, typer.Option("--year")] = None,
    doi: Annotated[list[str] | None, typer.Option("--doi", help="可重复给出")] = None,
    filter_expr: Annotated[
        str | None, typer.Option("--filter", help="标题大小写不敏感子串")
    ] = None,
    limit: Annotated[int | None, typer.Option("--limit", help="fetch 的 asset 数上限")] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="止于 resolve，不下载、不落盘")
    ] = False,
    extract: Annotated[bool, typer.Option("--extract", help="级联加跑阶段 5 extract")] = False,
    force: Annotated[bool, typer.Option("--force", help="绕过入队新鲜度，强制重跑")] = False,
    home: HomeOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """完整级联拉取（1→4，`--extract` 加 5，6 尾部必跑；`--dry-run` 止于 resolve）。"""
    if issue is not None and volume is None:
        _usage_error("--issue 必须搭配 --volume 使用")
    if volume is not None and year is not None:
        _usage_error("--volume 与 --year 不能同时指定")
    if volume is None and year is None and not doi:
        _usage_error("必须指定 --volume、--year 或 --doi 之一")

    selector = Selector(
        volume=volume,
        issue=issue,
        year=year,
        dois=tuple(doi) if doi else (),
        filter_expr=filter_expr,
        limit=limit,
    )
    with _env(home, verbose, dry_run=dry_run, auth=True) as env:
        runner = PipelineRunner(env.ctx, auth_manager=env.auth_manager)
        try:
            report = runner.pull(venue, selector, with_extract=extract, force=force)
        except CrawlerError as exc:
            _echo_error(exc)
            raise typer.Exit(code=2) from exc
        typer.echo(report.render_markdown())
        exit_code = _report_exit_code(report)
    raise typer.Exit(code=exit_code)


# -- grab -------------------------------------------------------------------


def _grab_resolve_venue(env: CliEnv, doi_norm: str, venue: str | None) -> str:
    """grab 的 venue 判定：显式 `--venue` 优先 > 库内该 DOI 的已绑定 paper 反查。

    二者皆无 → `CrawlerError(CONFIG)`（DOI 前缀→venue 的映射本框架无声明面——VenueSpec
    无 DOI 前缀字段，退化为要求显式 `--venue`；CLI 捕获转退出码 2）。
    """
    if venue is not None:
        return venue
    rows = env.ctx.db.query(
        "SELECT p.venue_id FROM paper p JOIN identifier i ON i.paper_id = p.id "
        "WHERE i.scheme = 'doi' AND i.value = ? AND p.venue_id IS NOT NULL "
        "ORDER BY p.venue_id LIMIT 1",
        (doi_norm,),
    )
    if rows:
        return str(rows[0]["venue_id"])
    raise CrawlerError(
        ErrorClass.CONFIG,
        f"无法从 DOI {doi_norm!r} 确定 venue（库内无该 DOI 的已绑定 paper）——请用 --venue 显式指定",
    )


def _grab_crossref_adapter(env: CliEnv) -> CrossrefAdapter:
    """带共享 http/限速登记的 crossref adapter（未入库 DOI 的单篇 lookup 用）。

    仿 `_prepare_unpaywall_adapter`：fresh `load_adapters()` + 注入 `env.http`（同 UA/同
    limiter）+ 主域登记。crossref 未注册 → 用法错退出 2。
    """
    adapter = load_adapters().get("crossref")
    if not isinstance(adapter, CrossrefAdapter):
        _usage_error("crossref adapter 未注册（无法 lookup 未入库 DOI）")
    if isinstance(adapter, HttpClientConsumer):
        adapter.set_http_client(env.http)
    env.ctx.limiter.register(adapter.domains[0], adapter.default_rate)
    return adapter


def _grab_ensure_paper(env: CliEnv, doi_norm: str, venue_id: str) -> str | None:
    """确定 grab 目标 paper_id：库内 DOI 反查命中即复用；否则 crossref 单篇 lookup →
    `MergeEngine.ingest(source='crossref')` 建最小 paper 行。均绑定到 `venue_id`（fetch
    路由读 paper.venue_id）。crossref 未收录该 DOI → None（业务失败，退出码 1）。"""
    rows = env.ctx.db.query(
        "SELECT paper_id FROM identifier WHERE scheme = 'doi' AND value = ? LIMIT 1",
        (doi_norm,),
    )
    if rows:
        paper_id = str(rows[0]["paper_id"])
        env.ctx.repo.bind_paper_venue(paper_id, venue_id)
        return paper_id
    stub = _grab_crossref_adapter(env).lookup(doi_norm)
    if stub is None:
        return None
    result = MergeEngine(env.ctx.repo).ingest(stub, source="crossref")
    env.ctx.repo.bind_paper_venue(result.paper_id, venue_id)
    return result.paper_id


def _grab_exit_code(report: RunReport) -> int:
    """grab 退出码（design/05 Task 口径）：至少一个资产落盘（含 OA 副本）→ 0；否则业务
    失败 → 1（no_entitlement 无 OA / blocked / gone / failed 皆归 1，grab 无 blocked=3 档）。"""
    return 0 if report.succeeded > 0 else 1


@app.command()
def grab(
    doi: Annotated[str | None, typer.Option("--doi", help="要抓取的论文 DOI")] = None,
    venue: Annotated[
        str | None, typer.Option("--venue", help="显式指定 venue（优先于库内 DOI 反查）")
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="绕过入队新鲜度，强制重跑")] = False,
    home: HomeOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """单篇 DOI 全链取回（resolve→fetch，含 no_entitlement→unpaywall OA 兜底）。

    venue 判定：显式 `--venue` 优先 > 库内该 DOI 已绑定 paper 反查。未入库 DOI 先经 crossref
    单篇 lookup → `MergeEngine.ingest(source='crossref')` 建最小 paper 行并绑定 venue，再走单篇
    resolve+fetch（复用 pull 全链：auth 健康门/日配额/工作时段窗/OA 兜底全生效）。退出码
    （design/05 Task 口径）：0=成功（资产落盘）/ 1=业务失败（无资产/blocked/未收录）/ 2=用法·
    配置错（缺 --doi / 未知 venue / 无法确定 venue）。
    """
    if not doi:
        _usage_error("必须指定 --doi")
    doi_norm = normalize_doi(doi)
    if not doi_norm:
        _usage_error(f"无效 DOI: {doi!r}")

    with _env(home, verbose, auth=True) as env:
        try:
            venue_id = _grab_resolve_venue(env, doi_norm, venue)
        except CrawlerError as exc:
            _echo_error(exc)
            raise typer.Exit(code=2) from exc
        _require_known_venue(env, venue_id)  # 未知 venue → 退出 2
        env.ctx.repo.upsert_venue(env.ctx.registry.get(venue_id))  # FK 前提：venue 行存在

        try:
            paper_id = _grab_ensure_paper(env, doi_norm, venue_id)
        except CrawlerError as exc:
            _echo_error(exc)
            raise typer.Exit(code=2) from exc
        if paper_id is None:
            typer.echo(f"DOI {doi_norm!r} 未在 crossref 找到元数据，无法建 paper——业务失败。")
            raise typer.Exit(code=1)

        runner = PipelineRunner(env.ctx, auth_manager=env.auth_manager)
        try:
            report = runner.grab(venue_id, paper_id, force=force)
        except CrawlerError as exc:
            _echo_error(exc)
            raise typer.Exit(code=2) from exc
        typer.echo(report.render_markdown())
        exit_code = _grab_exit_code(report)
    raise typer.Exit(code=exit_code)


# -- watch -------------------------------------------------------------------


def _emit_missing_email_warning(env: CliEnv) -> None:
    """config `[identity].email` 缺省时 obslog warn 一次（网络命令，UA 无 mailto）。"""
    if env.ctx.config.identity_email is None:
        log_event(
            "WARNING",
            "identity.email 未配置：真实抓取的 User-Agent 省略 mailto 段（D-014）；"
            "建议在 config.toml 设置 [identity].email 提供联系方式。",
        )


@app.command()
def watch(
    venue: Annotated[str | None, typer.Argument(help="preprint venue id（省略时需 --all）")] = None,
    all_: Annotated[
        bool, typer.Option("--all", help="对全部 preprint_channel venue 执行 watch")
    ] = False,
    home: HomeOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """preprint venue 的当月桶 METADATA 增量（arxiv.md §3 watch 裁决）。

    对 `kind=preprint_channel` 的 venue 执行 discover(强制刷新)→当月虚拟桶（跨月边界
    ——当日 ≤3 号时连上一月桶）enumerate(强制刷新)，**不 fetch**（watch 是元数据增量；
    `--fetch` 选项留 Phase 6）。去重由 `identifier(arxiv)` 主键天然保证（重叠窗口/同日
    二跑零重复入库）。运行报告复用 report 机制（新增/跳过计数）。

    非 preprint（`journal`/`conference`）venue 给用法错（退出 2）。`--all` 遍历全部
    preprint venue（非 preprint 自动跳过，不报错）。退出码同 pull/timeline/list：
    1（有 failed）> 3（无 failed 有 blocked）> 0；用法/配置错为 2。
    """
    if venue is None and not all_:
        _usage_error("必须指定 VENUE 或 --all")
    if venue is not None and all_:
        _usage_error("VENUE 与 --all 不能同时指定")

    with _env(home, verbose) as env:
        _emit_missing_email_warning(env)
        runner = PipelineRunner(env.ctx)
        if all_:
            specs = [s for s in env.ctx.registry.all() if s.kind == "preprint_channel"]
            if not specs:
                typer.echo("没有 preprint_channel 型 venue，watch 无目标。")
                raise typer.Exit(code=0)
            reports = [runner.watch(spec.id) for spec in specs]
            for spec, rep in zip(specs, reports, strict=True):
                typer.echo(_watch_summary_line(spec.id, rep))
            totals = _fold_reports(reports)
            typer.echo(
                f"合计 成功 {totals.succeeded} 失败 {totals.failed} "
                f"阻塞 {totals.blocked} 跳过 {totals.skipped}"
            )
            exit_code = _totals_exit_code(totals)
        else:
            assert venue is not None  # 上面两个用法错分支已排除 venue is None
            _require_known_venue(env, venue)
            spec = env.ctx.registry.get(venue)
            if spec.kind != "preprint_channel":
                _usage_error(
                    f"venue {venue!r} 的 kind={spec.kind!r} 非 preprint_channel；"
                    "watch 仅支持预印本 venue（journal/conference 用 pull/timeline）"
                )
            report = runner.watch(venue)
            typer.echo(report.render_markdown())
            exit_code = _report_exit_code(report)
    raise typer.Exit(code=exit_code)


def _watch_summary_line(venue_id: str, report: RunReport) -> str:
    """`watch --all` 的每 venue 单行摘要（含净新增 note）。"""
    note = next((n for n in report.notes if n.startswith("watch[")), "")
    detail = note.split(": ", 1)[1] if ": " in note else ""
    return (
        f"{venue_id}: 失败 {report.failed} 阻塞 {report.blocked} "
        f"跳过 {report.skipped}{f' | {detail}' if detail else ''}"
    )


# -- subs watch（订阅增量；Phase 6 T5）------------------------------------------
#
# 命名（**已裁决**，controller 2026-07-26，落档 design/05 §6 命令面表）：订阅增量是
# `crawler subs watch`，不是顶层 `crawler watch`——后者自 Phase 2 T6 起是 **preprint
# venue 的当月桶元数据增量**（上一节，带 AC-2.3/D-018 的 7 日 runbook 依赖），两者语义
# 不同、`--all` 的含义更是互斥（"全部 preprint venue" vs "全部订阅"）。子命令组形态沿
# `venues`/`config`/`auth` 的 house style；既有 `crawler watch <venue>` 逐字不变。

subs_app = typer.Typer(no_args_is_help=True, help="主题订阅（design/09）的增量运行。")
app.add_typer(subs_app, name="subs")


def _subscriptions_dir(env: CliEnv) -> Path:
    """订阅目录：`<home>/subscriptions` 优先，否则仓库根的 `subscriptions/`。

    订阅文件是**用户内容**，与 venue 注册表同属"声明面"，但 `Config` 尚无
    `subscriptions_dir` 键（design/10 未定义，本卡不擅自扩配置面）。故按两段查找：
    隔离 HOME 下有 `subscriptions/` 就用它（测试与多套配置并存的场景），否则退到相对
    当前工作目录的 `subscriptions/`（design/09 §2 字面路径，同 `canary_record_path`
    的"预期在仓库根调用"惯例）。
    """
    scoped = env.ctx.config.home / "subscriptions"
    return scoped if scoped.is_dir() else Path("subscriptions")


def _watch_source_venues(env: CliEnv) -> dict[str, VenueSpec]:
    """按**源 id** 索引的 `VenueSpec`：registry 内以该源为 `fulltext_source` 的 id 序首个。

    两个消费方：①T2 编译器读 ssrn 的 `quirks.topic_filter`（检查单 #10 的接线）；
    ②`AdapterFetcher` 拿它当 adapter 方法的 venue 入参。缺失的源由 `AdapterFetcher`
    合成最小 spec 兜底（其 `venue_for` docstring）。

    **arxiv 的收割面不再由本函数决定**（`fix/arxiv-category-fanout` 起）：订阅编译产物
    经请求参数覆盖 venue 的静态 quirks（`watch._compose_arxiv` 逐分类 fan-out，成对下推
    `arxiv_category`+`arxiv_set`），故"id 序首个 venue"对 arxiv 只剩 `quirks.inception`
    （其影响由 `SourceRequest.since` 收窄兜底）与日志身份两项影响。
    """
    venues: dict[str, VenueSpec] = {}
    for spec in env.ctx.registry.all():
        venues.setdefault(spec.fulltext_source, spec)
    return venues


def _watch_fetcher_factory(env: CliEnv) -> SourceFetcher:
    """订阅 watch 的源侧拉取件（模块级函数 = 测试注入 seam，同 `_http_client_factory`）。

    `load_adapters()` 取新鲜实例后注入 `_build_env` 已装配好的共享 `http`（同 UA、同
    限速器实例）——与 `_prepare_unpaywall_adapter`/`_prepare_enrich_source` 同款装配，
    使订阅拉取与 pipeline 走同一份限速预算，不另开一条绕过限速的通道。限速域登记复用
    `_register_rate_domains`（canary 侧同款需求：注入了带 limiter 的共享 client 后，
    未登记域会让逐请求 `acquire(host)` 撞 CONFIG fail-fast）——不在此另写一份同形循环。

    **nber 走专属 RSS 通道**（T7 `adapters/nber/rss.py`，nber.md §3.4）：`NberRssFetcher`
    用共享 `env.http` 打 `back.nber.org` 的 program feed。该域**刻意不在 nber adapter 的
    `domains` 里**（否则会被 `route_for` 别名到 `www.nber.org` 桶，错享宽松预算并违反
    robots `Crawl-delay:10`——nber/adapter.py §4 的 alias 陷阱注记），故 `_register_rate_domains`
    登记不到它；此处按"域出现即 register 保守桶"的既有惯例（`stages._fetch_oa_direct`
    的 OA-host 先例）显式登记 `NberAdapter.BACK_RATE_POLICY`（1 req/10s）。漏了这一步，
    RSS 的第一次请求就会撞 `RateLimiter` 的未注册域 CONFIG fail-fast。
    """
    adapters = load_adapters()
    bind_http_client(adapters, env.http)
    _register_rate_domains(env, adapters)
    env.ctx.limiter.register(nber_adapter.BACK_HOST, NberAdapter.BACK_RATE_POLICY)
    return RoutingFetcher(
        {"nber": NberRssFetcher(env.http)},
        AdapterFetcher(adapters, venues=_watch_source_venues(env)),
    )


def _subs_summary_line(summary: RunSummary) -> str:
    """每订阅单行摘要（`subs watch` 终端输出；日报是 markdown 的那份，此处是人读速览）。"""
    preview = "（预览，未入库）" if summary.dry_run else ""
    line = (
        f"{summary.subscription}: 状态 {summary.outcome.value}{preview} "
        f"候选 {summary.seen_count} 新增 {summary.new_count} 入库 {summary.ingested_count} "
        f"派生取回 {summary.fetched_count} 累计库存 {summary.library_total}"
    )
    if summary.failures:
        sources = ", ".join(sorted({failure.source for failure in summary.failures}))
        line += f" | 失败源: {sources}"
    return line


@subs_app.command("watch")
def subs_watch(
    name: Annotated[str | None, typer.Argument(help="订阅名（省略时需 --all）")] = None,
    all_: Annotated[bool, typer.Option("--all", help="跑 subscriptions/ 下全部订阅")] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="只报数：不入库、不派生任务、不推 watermark、不写记录"),
    ] = False,
    home: HomeOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """订阅增量运行（design/09；cron/launchd 触发的一次性运行，无常驻进程）。

    先把 `subscriptions/` 顶层的订阅文件加载并 upsert 入库（文件是权威，watermark
    等运行期状态不受影响），再按 `<NAME>`/`--all` 选目标逐个跑：编译→增量窗→per-source
    拉取→本地过滤→护栏→入库→推进 watermark→落运行记录，多订阅合并出一份
    `docs/reports/watch/daily-YYYY-MM-DD.md`。

    `--dry-run`（**新订阅上线前必跑**，design/09 §6.2）只报数：不入库、不派生取回任务、
    不推 watermark、不写运行记录，日报只回显到 stdout 不落盘——但拉取/过滤/护栏判定
    全程照跑，因此该跑出的报错一条都不会被跳过。

    退出码：0 正常（含零新增）/ 1 有源失败 / 2 用法·配置错（缺参数、未知订阅、订阅
    文件非法）/ 3 无失败但有护栏熔断。
    """
    if name is None and not all_:
        _usage_error("必须指定 NAME 或 --all")
    if name is not None and all_:
        _usage_error("NAME 与 --all 不能同时指定")

    with _env(home, verbose, dry_run=dry_run) as env:
        _emit_missing_email_warning(env)
        subs_repo = SubscriptionRepo(env.ctx.db)
        try:
            loaded = load_subscriptions(_subscriptions_dir(env), subs_repo)
            targets = loaded if all_ else [resolve_subscription(str(name), subs_repo)]
        except CrawlerError as exc:
            _echo_error(exc)
            raise typer.Exit(code=2) from exc

        if not targets:
            typer.echo("没有已登记的订阅，watch 无目标（把订阅 YAML 放进 subscriptions/）。")
            raise typer.Exit(code=0)

        context = WatchContext(
            db=env.ctx.db,
            repo=env.ctx.repo,
            subs_repo=subs_repo,
            fetcher=_watch_fetcher_factory(env),
            registry=env.ctx.registry,
            queue=env.ctx.queue,
            venues=_watch_source_venues(env),
        )
        # 时钟只取一次并贯穿全程（日报路径/渲染标题/增量窗同日，避免跨午夜时三者分裂）。
        today = dt.datetime.now(dt.UTC).date()
        summaries, report_path = run_watch_all(context, targets, dry_run=dry_run, now=today)

        for summary in summaries:
            typer.echo(_subs_summary_line(summary))
            brief = overload_brief(summary)
            if brief is not None:
                typer.echo(f"  熔断简报: {brief}")

        if dry_run:
            typer.echo(render_daily(summaries, date=today.isoformat()))
        else:
            write_daily_report(summaries, report_path, day=today)
            typer.echo(f"日报已落盘：{report_path}")
        exit_code = exit_code_for(summaries)
    raise typer.Exit(code=exit_code)


# -- status -------------------------------------------------------------------


@app.command()
def status(
    blocked: Annotated[bool, typer.Option("--blocked")] = False,
    failed: Annotated[bool, typer.Option("--failed")] = False,
    home: HomeOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """任务运维总览：默认打印各状态计数；`--blocked`/`--failed` 展开明细。

    只读查询，不构造 `PipelineRunner`（不触发其 recover_running/cleanup_tmp 副作用
    ——那些属于"即将执行任务"的命令，见模块 docstring）。
    """
    with _env(home, verbose) as env:
        if blocked:
            rows = env.ctx.queue.by_state("BLOCKED")
            for row in rows:
                typer.echo(
                    f"{row['id']} [{row['kind']}] venue={row['venue_id']}: {row['blocked_reason']}"
                )
            if rows:
                typer.echo(
                    "人工修复后运行 `crawler resume --all`"
                    "（或 `crawler resume <task_id>` 恢复单个任务）。"
                )
            else:
                typer.echo("无 BLOCKED 任务。")
        elif failed:
            rows = env.ctx.queue.by_state("FAILED")
            for row in rows:
                typer.echo(
                    f"{row['id']} [{row['kind']}] venue={row['venue_id']}: "
                    f"{row['error_class']} — {row['last_error']}"
                )
            if not rows:
                typer.echo("无 FAILED 任务。")
        else:
            for state in TASK_STATES:
                typer.echo(f"{state}: {len(env.ctx.queue.by_state(state))}")
    raise typer.Exit(code=0)


# -- resume -------------------------------------------------------------------


@app.command()
def resume(
    task_id: Annotated[str | None, typer.Argument(help="要恢复的任务 id")] = None,
    all_: Annotated[bool, typer.Option("--all", help="恢复全部 BLOCKED 任务")] = False,
    home: HomeOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """BLOCKED → PENDING；必须指定 TASK_ID 或 `--all` 之一。"""
    if task_id is None and not all_:
        _usage_error("必须指定 TASK_ID 或 --all")

    with _env(home, verbose) as env:
        if all_:
            n = env.ctx.queue.resume(all_blocked=True)
            typer.echo(f"已恢复 {n} 个任务")
            exit_code = 0
        else:
            assert task_id is not None  # 上面已保证：非 --all 时 task_id 必给
            try:
                n = env.ctx.queue.resume(task_id)
            except (KeyError, IllegalTransition) as exc:
                _echo_error(exc)
                exit_code = 2
            else:
                typer.echo(f"已恢复 {n} 个任务")
                exit_code = 0
    raise typer.Exit(code=exit_code)


# -- retry -------------------------------------------------------------------


@app.command()
def retry(
    error_class: Annotated[
        str | None, typer.Option("--class", help="限定重试的 error_class")
    ] = None,
    home: HomeOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """FAILED → PENDING 批量重试；`--class` 缺省时重试全部 FAILED 任务。"""
    ec: ErrorClass | None = None
    if error_class is not None:
        try:
            ec = ErrorClass(error_class)
        except ValueError:
            _usage_error(f"未知 error_class: {error_class}")

    with _env(home, verbose) as env:
        n = env.ctx.queue.retry_failed(ec)
        typer.echo(f"已重试 {n} 个任务")
    raise typer.Exit(code=0)


# -- verify -------------------------------------------------------------------
#
# AC-3.3（acceptance-criteria.md）判据："人为制造丢文件/孤儿文件/哈希不符三类 →
# `verify` 全部检出并给正确修复建议"。三类检出本身自 Phase 1 T8a 起已在
# `verify_store`（verify.py）完整实现（100% 覆盖，接口冻结，本次未改动）；本节
# 三个私有 helper 是 Phase 3 T2 补的差距——CLI 层把冻结的短关键词
# suggestion（re-fetch/adopt/quarantine）翻成人可读、且与现有 CLI 命令面真实
# 一致的修复建议文本（不发明不存在的命令）。


def _pdf_layout_scope(data_dir: Path, file_path: str) -> tuple[str | None, str | None]:
    """从 `data_dir/pdf/<venue_id>/<year>/...` 前缀推断 (venue_id, year)（design/06 §4
    文件存储布局）；仅用于把修复建议拼成可直接执行的 `crawler pull` 命令。

    解析不出时返回的对应位置为 None（调用方回退到占位提示），绝不臆造：
    - `file_path` 为空（`missing_file` 的"file_path 本身为空"异常路径，见
      `tests/unit/test_verify.py::test_verify_store_detects_missing_file_when_file_path_empty`）；
    - 路径不落在 `data_dir/pdf` 下；
    - year 段不是纯数字——`_asset_final_path`（pipeline/stages.py）对缺失 year 落
      目录名 "unknown"，不是合法的 `--year` 输入。

    只做纯路径字符串运算，不 stat 磁盘（missing_file 场景文件本就不存在）。
    """
    if not file_path:
        return None, None
    candidate = Path(file_path)
    if not candidate.is_absolute():
        candidate = data_dir / candidate
    try:
        parts = candidate.relative_to(data_dir / "pdf").parts
    except ValueError:
        return None, None
    venue_id = parts[0] if len(parts) >= 1 else None
    year = parts[1] if len(parts) >= 2 and parts[1].isdigit() else None
    return venue_id, year


def _pull_force_cmd(venue_id: str | None, year: str | None, asset_id: str | None) -> str:
    """拼一条真实可用的 `crawler pull ... --force` 提示（现状盘点结论见模块顶部）。

    `--force` 是唯一能让已 DONE 的 fetch 任务真正重新下载的现有 CLI 能力：
    `tasks.py` `FRESHNESS_TTL["fetch"] = None`——fetch 任务一旦 DONE 永久视为新鲜，
    普通重跑 `pull` 会 fresh_skip、不会真的重新调用 fetch handler；`crawler resume`
    只处理 BLOCKED 任务、`crawler retry` 只处理 FAILED 任务，均不覆盖"asset 记录
    fetched 但磁盘证据被破坏"这种场景（task 本身仍是 DONE）。`pull` 要求
    `--volume`/`--year`/`--doi` 三选一，故 venue_id 已知但 year 未知时仍需提示
    用户补一个 scope 参数。
    """
    if venue_id and year:
        return f"`crawler pull {venue_id} --year {year} --force`"
    if venue_id:
        return (
            f"`crawler pull {venue_id} --force`"
            "（须再加 `--volume <volume>`/`--year <year>`/`--doi <doi>` 之一定位该 asset）"
        )
    asset_part = f"；asset={asset_id}" if asset_id else ""
    return (
        "`crawler pull <venue_id> --force`"
        f"（须再加 `--volume <volume>`/`--year <year>`/`--doi <doi>` 定位该 asset{asset_part}）"
    )


def _verify_fix_hint(issue: VerifyIssue, data_dir: Path) -> str:
    """把一条 `VerifyIssue` 翻成人可读的修复建议（AC-3.3"正确修复建议"）。

    `verify_store` 本身只读、不自动修（design/05 §5.4）；本函数同样只读——只拼
    文本，不执行任何命令、不碰 DB/磁盘。三类分别对应 AC-3.3 判据原文：
    - missing_file →"re-fetch 提示"：见 `_pull_force_cmd`。
    - hash_mismatch →"标记 corrupt+re-fetch"：verify 只读，"标记 corrupt"是本行
      输出对该文件的判定说明（不是 DB 状态机新增一个 corrupt 值——`asset.state`
      的合法取值见 migrations/0001_init.sql，没有 corrupt），随后同样给 re-fetch。
    - orphan_file →"纳管或清理提示"：现有 CLI 命令面（`crawler --help`）核实结论
      是没有任何"把磁盘文件登记为 asset"的命令，如实告知而非编造一个
      `crawler adopt`。
    """
    if issue.kind == "missing_file":
        venue_id, year = _pdf_layout_scope(data_dir, issue.file_path)
        return (
            "    fix: DB 记录该 asset 已 fetched，但磁盘文件缺失；fetch 任务一旦 DONE "
            "永久视为新鲜（`resume`/`retry` 分别只对 BLOCKED/FAILED 任务生效，对本情形"
            f"无效），需强制重新拉取：{_pull_force_cmd(venue_id, year, issue.asset_id)}"
        )
    if issue.kind == "hash_mismatch":
        venue_id, year = _pdf_layout_scope(data_dir, issue.file_path)
        return (
            "    fix: 文件内容与记录的 sha256 不符，判定为 corrupt——不要信任现有文件，"
            f"先隔离/勿使用，再强制重新拉取覆盖：{_pull_force_cmd(venue_id, year, issue.asset_id)}"
        )
    return (
        "    fix: 磁盘有文件但 DB 无对应记录；当前 CLI 无自动纳管（adopt）命令——"
        "若确认是有效产物，需人工核实来源后手动登记；若为陈旧/无效文件，可直接删除该"
        "路径清理。"
    )


@app.command()
def verify(home: HomeOpt = None, verbose: VerboseOpt = False) -> None:
    """DB↔文件双向对账（design/05 §5.4）；只读、不自动修，发现不一致退出 1。"""
    with _env(home, verbose) as env:
        data_dir = env.ctx.config.data_dir
        issues = verify_store(env.ctx.repo, data_dir)
        for issue in issues:
            asset_part = f" asset={issue.asset_id}" if issue.asset_id else ""
            typer.echo(f"[{issue.kind}] {issue.file_path} -> {issue.suggestion}{asset_part}")
            typer.echo(_verify_fix_hint(issue, data_dir))
        if issues:
            typer.echo(f"发现 {len(issues)} 处不一致。")
            exit_code = 1
        else:
            typer.echo("verify: 一致，未发现问题。")
            exit_code = 0
    raise typer.Exit(code=exit_code)


# -- oa-report ------------------------------------------------------------------


def _doi_universe(db: Database, *, venue_id: str | None) -> list[str]:
    """库内 DOI 集合（`identifier.scheme='doi'`），可选按 venue 过滤；去重、按值排序。

    直查 `Database`（T5 共享文件纪律：`repo.py` 冻结不动，不为此新增仓储方法——
    与 `verify_store`/`run_canary` 复用既有 `Repo` 方法的既有分工不同，本查询是纯
    只读聚合、无跨表写语义，直接经 `Database.query` 这一冻结公共接口达成即可）。
    """
    if venue_id is not None:
        rows = db.query(
            "SELECT DISTINCT i.value FROM identifier i "
            "JOIN paper p ON p.id = i.paper_id "
            "WHERE i.scheme = 'doi' AND p.venue_id = ? ORDER BY i.value",
            (venue_id,),
        )
    else:
        rows = db.query("SELECT DISTINCT value FROM identifier WHERE scheme = 'doi' ORDER BY value")
    return [str(row["value"]) for row in rows]


def _prepare_unpaywall_adapter(env: CliEnv) -> UnpaywallAdapter:
    """取一个可正确限速/带凭证的 `unpaywall` adapter 实例（`oa-report` 命令专用装配）。

    unpaywall 不是任何 venue 的 `metadata_source`/`fulltext_source`，不经
    `registry.route()`/`pipeline.stages.route_for` 的既有限速登记路径（T5 范围内不
    接线 pipeline 兜底，见 `UnpaywallAdapter` 模块 docstring「触发条件语义」）——本
    命令独立补齐：注入 `_build_env` 已装配好的共享 `http`（同一 UA/同一限速器实例）+
    `Config.identity_email`，并把 `unpaywall.domains[0]` 登记进同一限速器（`route_for`
    对每源域的登记同款），使批量 DOI 循环切实遵守 5 req/s（不同于 `canary` 命令对
    `load_adapters()` 新鲜实例的"不额外装配、允许惰性自建"处理——那里只有一次探测
    请求，本命令可能循环上百次，必须走正确限速）。
    """
    adapters = load_adapters()
    adapter = adapters.get("unpaywall")
    if not isinstance(adapter, UnpaywallAdapter):
        _usage_error("unpaywall adapter 未注册（pyproject entry-point 缺失或被覆盖）")
    if isinstance(adapter, HttpClientConsumer):
        adapter.set_http_client(env.http)
    if isinstance(adapter, EmailConsumer):
        adapter.set_email(env.ctx.config.identity_email)
    env.ctx.limiter.register(adapter.domains[0], adapter.default_rate)
    return adapter


@app.command("oa-report")
def oa_report_cmd(
    venue: Annotated[str | None, typer.Option("--venue", help="仅统计该 venue 的 DOI")] = None,
    limit: Annotated[
        int | None, typer.Option("--limit", help="限制查询的 DOI 数量（默认不限）")
    ] = None,
    home: HomeOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Unpaywall OA 命中率报告：库内 DOI 集合逐个 `GET /v2/{doi}`（T5 DoD 第二项）。

    单 DOI GET 循环（无批量端点，design/adapters/aggregators.md §5.5）；5 req/s 限速下
    100 DOI ≈ 20s。只读，不写 DB、不下载资产；退出码恒为 0（报告本身不是"发现问题即
    失败"的对账判据，同 verify 不同——命中率高低是统计事实，非缺陷信号），`--venue`
    给未知 id 时按既有用法错口径退出 2。
    """
    with _env(home, verbose) as env:
        if venue is not None:
            _require_known_venue(env, venue)
        dois = _doi_universe(env.ctx.db, venue_id=venue)
        if limit is not None:
            dois = dois[:limit]

        if not dois:
            typer.echo("库内无 DOI（identifier.scheme='doi' 为空），无可查询目标。")
            raise typer.Exit(code=0)

        adapter = _prepare_unpaywall_adapter(env)
        rep = oa_report.build_oa_report(dois, adapter.lookup)
        typer.echo(oa_report.render_oa_report_markdown(rep))
    raise typer.Exit(code=0)


# -- enrich ---------------------------------------------------------------------
#
# T6（design/adapters/aggregators.md §5.3/§5.4；plan §2-5 冻结契约）：openalex/s2
# 补充层 enrich 通道的驱动命令。二者 capabilities 空集、不进 `SourceAdapter` 冻结
# 协议的枚举/取回语义，只经 duck-typed `EnrichmentSource.enrich_batch` 参与——**不进
# pull 六阶段、不产 RunReport、无任何 AC 依赖它**（同 `oa-report` 的定位/退出码
# 口径：薄包装接线，纯逻辑在各 adapter 自身，本节只做装配 + 循环编排 + 摘要渲染）。

_ENRICH_SOURCES = ("openalex", "s2")
# 每次 `enrich_batch` 调用处理的 DOI 数上限——CLI 层的"外层分页"，与各 adapter 内部
# 自己的批量机制（openalex URL 长度自算、s2 官方 ≤500/批）是两层独立的粒度：外层页
# 控制进度可见度/预算熔断响应粒度（一页可能触发数个真实请求），内层页是单次真实
# 请求的负载上限。200 是介于"太碎（调用开销）"与"太粗（一次性吞掉几千 DOI 才反馈
# 一次进度、一旦中途熔断损失的已完成工作也更多）"之间的折中值，非站点强制上限。
_ENRICH_PAGE_SIZE = 200


@dataclass(frozen=True)
class _EnrichmentSourceSummary:
    """单个 source 一次 `crawler enrich` 运行的摘要行数据。"""

    source: str
    processed: int
    created: int
    merged: int
    candidate: int
    stopped_reason: str | None


def _chunked(items: list[str], size: int) -> Iterator[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _apply_enrich_key(
    env: CliEnv, adapter: object, source_id: str, dedicated: list[HttpClient]
) -> None:
    """为 enrich source（openalex/s2）注入 key/client（抽自 `_prepare_enrich_source`，供
    `canary` 装配 `_bind_healthcheck_credentials` 复用——单一装配语义，不两处各写一份）。

    - s2 有 key → 构造携 `x-api-key` 头的**专属** `HttpClient`（append 到 `dedicated`，调用
      方负责 `close()`；绝不复用共享 `env.http`——头会随他域请求外泄，凭证红线）；无 key →
      注入共享 client（`enrich_batch` 入口会直接 CONFIG、不发请求，s2 adapter docstring）。
    - openalex 的 key 走每请求 URL 查询参数（非 client 级头），复用共享 client 即可。
    """
    if source_id == "s2":
        key = env.ctx.config.s2_api_key
        if key and isinstance(adapter, HttpClientConsumer):
            client = HttpClient(
                user_agent=build_user_agent(env.ctx.config.identity_email),
                rate_limiter=env.ctx.limiter,
                extra_headers={"x-api-key": key},
            )
            adapter.set_http_client(client)
            dedicated.append(client)
        elif isinstance(adapter, HttpClientConsumer):
            adapter.set_http_client(env.http)
        if isinstance(adapter, ApiKeyConsumer):
            adapter.set_api_key(key)
    elif source_id == "openalex":
        if isinstance(adapter, HttpClientConsumer):
            adapter.set_http_client(env.http)
        if isinstance(adapter, ApiKeyConsumer):
            adapter.set_api_key(env.ctx.config.openalex_api_key)
        if isinstance(adapter, OpenAlexAdapter):
            adapter.configure_budget(
                daily_budget_usd=env.ctx.config.openalex_daily_budget_usd,
                state_path=env.ctx.config.home / "state" / "openalex-budget.json",
            )


def _prepare_enrich_source(
    env: CliEnv, source_id: str
) -> tuple[EnrichmentSource, HttpClient | None]:
    """装配一个可用的 enrich source adapter（`enrich` 命令对单个 `--source` 取值的专用
    装配，接线风格仿 `_prepare_unpaywall_adapter`：fresh `load_adapters()` + 手工注入
    + 手工限速登记，不复用 `env.ctx.registry`——openalex/s2 不是任何 venue 的
    metadata_source/fulltext_source，不会天然出现在 registry 路由里）。

    返回 `(adapter, dedicated_client)`：`dedicated_client` 非 `None` 时调用方负责
    `close()`（s2 有 key 时的专属 client，见 `_apply_enrich_key`）。

    `source_id` 给出未注册、或已注册但未实现 duck-typed `enrich_batch` 的 id → 用法错
    退出 2（同 `oa-report`/`canary --adapter` 既有口径）。
    """
    adapters = load_adapters()
    candidate = adapters.get(source_id)
    if candidate is None or not isinstance(candidate, EnrichmentSource):
        _usage_error(
            f"{source_id!r} 不是已注册且支持 enrich 的 source"
            "（未注册，或未实现 duck-typed enrich_batch）"
        )

    dedicated: list[HttpClient] = []
    _apply_enrich_key(env, candidate, source_id, dedicated)
    env.ctx.limiter.register(candidate.domains[0], candidate.default_rate)
    return candidate, (dedicated[0] if dedicated else None)


def _run_enrich_source(
    adapter: EnrichmentSource, engine: MergeEngine, source_id: str, dois: list[str]
) -> _EnrichmentSourceSummary:
    """驱动一个 source 对整批 `dois` 的 enrich 循环：外层分页调 `enrich_batch` → 逐
    `PaperStub` 经 `MergeEngine.ingest(stub, source=source_id)` 回注（字段级来源优先级
    收敛天然补缺不覆盖，merge.py `SOURCE_PRIORITY`）。

    任一页触发的 `CrawlerError`（s2 缺 key/openalex 预算熔断/瞬时故障等）终止该
    source**剩余**页的处理、记入 `stopped_reason`——不重试、不向上抛出崩溃整个命令：
    `enrich` 不进 pull 六阶段，没有 pipeline 的重试/BLOCKED 语义（模块顶层注释）。
    已经处理完的页在终止前已正确回注入库，不回滚（"尽力而为，报告在哪停下"）。
    """
    processed = created = merged = candidate_flagged = 0
    stopped_reason: str | None = None
    for page in _chunked(dois, _ENRICH_PAGE_SIZE):
        try:
            stubs = adapter.enrich_batch(page)
        except CrawlerError as exc:
            stopped_reason = f"{exc.error_class.value}: {exc}"
            break
        for stub in stubs:
            result = engine.ingest(stub, source=source_id)
            processed += 1
            if result.action == "created":
                created += 1
            elif result.action == "merged":
                merged += 1
            else:
                candidate_flagged += 1
    return _EnrichmentSourceSummary(
        source=source_id,
        processed=processed,
        created=created,
        merged=merged,
        candidate=candidate_flagged,
        stopped_reason=stopped_reason,
    )


def _render_enrich_summary(
    summary: _EnrichmentSourceSummary, *, extra_note: str | None = None
) -> str:
    line = (
        f"[{summary.source}] 处理 {summary.processed} 篇"
        f"（created={summary.created} merged={summary.merged} candidate={summary.candidate}）"
    )
    if extra_note:
        line += f" | {extra_note}"
    if summary.stopped_reason:
        line += f" | 提前终止: {summary.stopped_reason}"
    return line


def _openalex_budget_note(env: CliEnv) -> str:
    """openalex 摘要行的预算消耗附注（读状态文件现值，不改动其内容）。"""
    state_path = env.ctx.config.home / "state" / "openalex-budget.json"
    state = openalex_budget.load_state(state_path)
    return (
        f"预算消耗 {state.spent_usd:.4f}/{env.ctx.config.openalex_daily_budget_usd:.2f} "
        "USD（今日 UTC）"
    )


@app.command()
def enrich(
    venue: Annotated[str | None, typer.Option("--venue", help="仅富化该 venue 的 paper")] = None,
    source: Annotated[
        str | None, typer.Option("--source", help="仅跑该 enrich source（openalex|s2）")
    ] = None,
    limit: Annotated[
        int | None, typer.Option("--limit", help="限制扫描的 DOI 数量（默认不限）")
    ] = None,
    home: HomeOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """补充层 enrich 通道：openalex/s2 duck-typed `enrich_batch`（plan §2-5/§4 T6）。

    扫库内带 `doi` identifier 的 paper（`--venue` 可选收窄，同 `oa-report` 的
    `_doi_universe` 复用）→ 按 `--source` 指定的（或省略时全部两个）source 分批调用
    `enrich_batch` → 每条 `PaperStub` 经 `MergeEngine.ingest(stub, source=…)` 回注。

    **不参与 pull 六阶段、不产 `RunReport`、无任何 AC 依赖它**（AC-3.5 五刊全史由
    crossref 独立完成，同模块顶层"-- enrich --"分节注释）——退出码恒为 0，除非早期
    用法/配置错误（未知 venue、未知 `--source` 取值 → 2，同既有 CLI 用法错口径）。
    单个 source 运行中途遇到的错误（s2 未配置 key、openalex 预算当日熔断、瞬时网络
    故障等）只记入该 source 摘要行的"提前终止"备注，不影响其它 source 继续跑、不
    改变命令整体退出码——这类情形是预期内的正常运维态（预算耗尽明日恢复、key 待
    申请），不是需要非零退出码提醒运维介入的错误。
    """
    if source is not None and source not in _ENRICH_SOURCES:
        _usage_error(f"未知 --source: {source!r}；可选 {', '.join(_ENRICH_SOURCES)}")

    with _env(home, verbose) as env:
        if venue is not None:
            _require_known_venue(env, venue)
        dois = _doi_universe(env.ctx.db, venue_id=venue)
        if limit is not None:
            dois = dois[:limit]

        if not dois:
            typer.echo("库内无 doi identifier（可选按 --venue 过滤后同样为空），无可富化目标。")
            raise typer.Exit(code=0)

        engine = MergeEngine(env.ctx.repo)
        sources = [source] if source is not None else list(_ENRICH_SOURCES)
        for source_id in sources:
            adapter, dedicated = _prepare_enrich_source(env, source_id)
            try:
                summary = _run_enrich_source(adapter, engine, source_id, dois)
            finally:
                if dedicated is not None:
                    dedicated.close()
            extra_note = _openalex_budget_note(env) if source_id == "openalex" else None
            typer.echo(_render_enrich_summary(summary, extra_note=extra_note))
    raise typer.Exit(code=0)


# -- report -------------------------------------------------------------------


@app.command()
def report(
    last_run: Annotated[bool, typer.Option("--last-run", help="打印最近一次运行报告")] = False,
    home: HomeOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """打印最近一次运行报告（`reports_dir/last-run.md`）。

    Phase 1 只有这一种报告视图：`--last-run` 是显式声明，省略时行为相同
    （design/05 §6 未定义其它 report 子视图；参数保留供未来扩展）。
    """
    del last_run
    with _env(home, verbose) as env:
        path = env.ctx.config.reports_dir / "last-run.md"
        if path.is_file():
            typer.echo(path.read_text(encoding="utf-8"))
        else:
            typer.echo("尚无历史运行报告（还没有执行过 pull/timeline/list 等命令）。")
    raise typer.Exit(code=0)


# -- canary -------------------------------------------------------------------


def _register_rate_domains(env: CliEnv, adapters: dict[str, SourceAdapter]) -> None:
    """canary 探测前登记每 adapter 的限速域（A-M1，仿 `_prepare_enrich_source` 的
    register+alias）。

    canary 逐 adapter 探测走**注入的共享 client**（携 `env.ctx.limiter`）逐请求 `acquire(host)`；
    host 未注册 → `RateLimiter` CONFIG fail-fast，会被 healthcheck 误当成"不健康"（伪不健康）。
    故先登记主域 `domains[0]`（`register` 幂等取最保守值）+ 副域别名到主域（arxiv 三域先例，
    `RateLimiter.alias`）——`register` 紧接 `alias` 保证 canonical 已注册。空 domains 跳过。
    """
    for adapter in adapters.values():
        domains: tuple[str, ...] = getattr(adapter, "domains", ())
        if not domains:
            continue
        env.ctx.limiter.register(domains[0], adapter.default_rate)
        for secondary in domains[1:]:
            env.ctx.limiter.alias(secondary, domains[0])


def _bind_healthcheck_credentials(
    env: CliEnv, adapters: dict[str, SourceAdapter]
) -> list[HttpClient]:
    """canary 探测前对每 adapter 施加与 pull/enrich 同款凭证注入（检查单 #3 闭合，
    auth-framework §7）——收敛"canary 另起 `load_adapters()` 新鲜实例却不注入凭证，即便用户
    已配置 token/key 仍体现为匿名"的缺陷。返回专属 client 列表供调用方 `close()`。

    装配步（与 `_build_env` 同语义）：
    - `bind_http_client`：共享 UA+limiter client 注入 http adapter（arxiv 等），同 `_build_env`。
    - `_register_rate_domains`（A-M1）：登记限速域——否则注入了带 limiter 的共享 client 后，
      逐请求 `acquire(host)` 撞未注册域 → CONFIG fail-fast（伪不健康）。
    - `_bind_openreview_token_client`：有 token → 携 `Cookie` 专属 client（复用既有，不污染共享）。
    - `_apply_enrich_key`（openalex/s2）：有 key → s2 专属 client / openalex 共享 client。

    **auth_gated 平台的 session 注入归 T5（AuthManager 装配），本函数不注入 session**——故
    auth_gated adapter 无 session 时 healthcheck 抛 `NotImplementedError` → canary SKIP（B-M4：
    与 pipeline fetch 路径的 `AuthRequired`→BLOCKED 二义分离，canary healthcheck 专用 SKIP）。
    """
    dedicated: list[HttpClient] = []
    bind_http_client(adapters, env.http)
    _register_rate_domains(env, adapters)
    openreview_client = _bind_openreview_token_client(adapters, env.ctx.config, env.ctx.limiter)
    if openreview_client is not None:
        dedicated.append(openreview_client)
    for source_id in _ENRICH_SOURCES:
        adapter = adapters.get(source_id)
        if isinstance(adapter, EnrichmentSource):
            _apply_enrich_key(env, adapter, source_id, dedicated)
    return dedicated


@app.command()
def canary(
    adapter: Annotated[str | None, typer.Option("--adapter", help="仅检查指定 adapter id")] = None,
    record: Annotated[
        bool,
        typer.Option(
            "--record",
            help="额外把健康矩阵落盘到 docs/testing/records/canary/<今日>-canary.md",
        ),
    ] = False,
    home: HomeOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """adapter 健康矩阵（test-plan §4/§9 canary 的 healthcheck 层，T3 落地）。

    遍历已注册 adapter（`load_adapters()`）逐个调用 `healthcheck()`，打印
    markdown 健康矩阵（`canary.render_canary_markdown`）。stub adapter 尚未实现
    健康检查而抛出的 `NotImplementedError` 归为 SKIP 行，不计入不健康
    （`canary.run_canary` 的分类规则，见该模块 docstring）。

    `--adapter ID` 限定只检查该 adapter；给了未注册的 id 视为用法错，退出 2。
    退出码契约见模块 docstring："canary 命令不产出 RunReport" 一段。

    `--record`：额外把同一份健康矩阵（与终端输出同源数据，`canary.render_canary_record`
    内部复用 `render_canary_markdown`）写入 `docs/testing/records/canary/<YYYY-MM-DD>
    -canary.md`（相对当前工作目录，预期仓库根目录下调用，见 `canary.canary_record_path`
    docstring）。省略 `--record` 时行为与此前完全一致，不建目录、不写文件。
    """
    with _env(home, verbose) as env:
        adapters = load_adapters()
        if adapter is not None:
            if adapter not in adapters:
                _usage_error(f"未注册的 adapter: {adapter!r}")
            adapters = {adapter: adapters[adapter]}

        # 检查单 #3：注入 token/key + 登记限速域，使已配置凭证的 adapter 不再体现为匿名态。
        dedicated = _bind_healthcheck_credentials(env, adapters)
        try:
            rows = run_canary(adapters)
        finally:
            for client in dedicated:
                client.close()

        typer.echo(render_canary_markdown(rows))
        if record:
            today = dt.date.today()
            path = canary_record_path(today)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render_canary_record(rows, today), encoding="utf-8")
            typer.echo(f"健康矩阵已落盘：{path}")
        exit_code = canary_exit_code(rows)
    raise typer.Exit(code=exit_code)


# -- config show --------------------------------------------------------------


def _mask_email(value: str) -> str:
    """email 部分脱敏（首字符 + `***` + 域）：`yhyfhgs@gmail.com` → `y***@gmail.com`。

    email 属半私 PII 但非硬凭证（config 护栏放行 `identity.email`）——config show 部分掩码
    以便确认"配的是哪个账号"，又不回显完整地址。无 `@`/空 local 段 → 整值 `***`。
    """
    local, sep, domain = value.partition("@")
    if not sep or not local:
        return "***"
    return f"{local[0]}***@{domain}"


def _format_config_value(layer: ConfigLayer) -> str:
    """`config show` 单元格：绝不回显凭证明文（10-config-layout §4）。

    未配置 → `(unset)`；硬凭证（api_key/token/insttoken/…）→ 整值 `***`；email → 部分脱敏；
    venues_dirs 空 → `(none)`、非空 → 逗号连接；余者过 `redact()`（纵深防御，路径/数值无影响）。
    """
    value = layer.value
    if value is None:
        return "(unset)"
    if layer.sensitive:
        return "***"
    if layer.is_email and isinstance(value, str):
        return _mask_email(value)
    if isinstance(value, tuple):  # paths.venues_dirs
        return ", ".join(str(entry) for entry in value) if value else "(none)"
    if isinstance(value, dict):  # auth.active_profile（platform→profile 映射，非敏感）
        return ", ".join(f"{k}={v}" for k, v in sorted(value.items())) if value else "(none)"
    return redact(str(value))


@config_app.command("show")
def config_show(home: HomeOpt = None) -> None:
    """打印全部生效配置项 + winning 来源层（env/project/home/default），敏感值脱敏。

    用于确认"配了没 / 来自哪层"，**绝不回显凭证明文**（10-config-layout §4）：敏感键整值
    `***`、email 部分脱敏、未配置 `(unset)`（来源列 `-`）。退出码恒 0（只读自查，非对账
    判据）；项目级 `./paper-crawler.toml` 含敏感键 → 分层加载护栏 `CrawlerError(CONFIG)`
    拒启动（退出 2，指引挪至家目录/env）。
    """
    try:
        layers = describe_config(home)
    except CrawlerError as exc:
        _echo_error(exc)
        raise typer.Exit(code=2) from exc
    rows = [
        [layer.key, _format_config_value(layer), layer.source if layer.value is not None else "-"]
        for layer in layers
    ]
    typer.echo(_render_table(["key", "value", "source"], rows))
    raise typer.Exit(code=0)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main() -> None:
    app()


if __name__ == "__main__":
    main()
