"""`crawler` CLI —— 命令面接线（接口冻结件 §2.7/§2.8 的纯消费方，design/05 §6 命令面
的 Phase 1 子集）。

职责边界：本模块只做"接线"——把已冻结的 `PipelineRunner`/`VenueRegistry`/
`TaskQueue`/`verify_store` 等实物拼成命令行入口，不新增业务语义。所有命令共用
一个环境工厂 `_build_env`（`Config.load(home)` → `setup_logging` →
`Database`+`migrate` → `VenueRegistry.load_dirs` → 组装 `StageContext`），避免
逐命令重复这套装配（任务书 Global Constraints 精神 + phase1-implementation-plan
Task 8 DoD）。

退出码契约（design/05 §6 + phase1-implementation-plan Task 8）：
- `0`：命令成功（含"报告 succeeded>0 或全 skipped"的正常结束）；
- `1`：产出一份 `RunReport` 且 `failed > 0`（pull/timeline/list）；
- `2`：用法/配置错误——未知 venue、`venues lint` 检出问题、Selector 冲突
  （如同时给 `--year` 与 `--volume`）、`resume` 缺参数、`retry --class` 给了
  未知 error_class；
- `3`：产出一份 `RunReport` 且 `failed == 0` 但 `blocked > 0`。

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
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from paper_crawler.adapter import load_adapters
from paper_crawler.config import Config
from paper_crawler.errors import CrawlerError, ErrorClass, IllegalTransition
from paper_crawler.obslog import setup_logging
from paper_crawler.pipeline import PipelineRunner, RunReport, Selector, StageContext
from paper_crawler.ratelimit import RateLimiter
from paper_crawler.registry import VenueRegistry
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.tasks import TASK_STATES, TaskQueue
from paper_crawler.verify import verify_store

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


def _build_env(home: Path | None, verbose: bool, *, dry_run: bool = False) -> CliEnv:
    config = Config.load(home)
    config.ensure_dirs()
    setup_logging(config.log_dir, console_level="DEBUG" if verbose else "INFO")

    db = Database(config.db_path)
    db.migrate()
    repo = Repo(db)
    registry = VenueRegistry(load_adapters())
    registry.load_dirs(list(config.venues_dirs))
    queue = TaskQueue(db)
    limiter = RateLimiter(scale=config.rate_scale)

    stage_ctx = StageContext(
        config=config,
        db=db,
        repo=repo,
        registry=registry,
        queue=queue,
        limiter=limiter,
        dry_run=dry_run,
    )
    return CliEnv(ctx=stage_ctx)


@contextlib.contextmanager
def _env(home: Path | None, verbose: bool, *, dry_run: bool = False) -> Iterator[CliEnv]:
    """`_build_env` 的上下文管理器包装：命令结束（正常或 `typer.Exit`）时关闭 DB 连接。

    CLI 每次调用在真实使用中对应一个独立进程（连接随进程退出自然释放）；
    `typer.testing.CliRunner` 是进程内反复调用同一 Python 解释器，必须显式
    `close()` 避免一次测试函数内多次调用间的连接堆积。
    """
    cli_env = _build_env(home, verbose, dry_run=dry_run)
    try:
        yield cli_env
    finally:
        cli_env.ctx.db.close()


# ---------------------------------------------------------------------------
# 共用小件：错误呈现、退出码、表格渲染、Selector 范围参数
# ---------------------------------------------------------------------------


def _usage_error(message: str) -> None:
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
    with _env(home, verbose, dry_run=dry_run) as env:
        runner = PipelineRunner(env.ctx)
        try:
            report = runner.pull(venue, selector, with_extract=extract, force=force)
        except CrawlerError as exc:
            _echo_error(exc)
            raise typer.Exit(code=2) from exc
        typer.echo(report.render_markdown())
        exit_code = _report_exit_code(report)
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


@app.command()
def verify(home: HomeOpt = None, verbose: VerboseOpt = False) -> None:
    """DB↔文件双向对账（design/05 §5.4）；只读、不自动修，发现不一致退出 1。"""
    with _env(home, verbose) as env:
        issues = verify_store(env.ctx.repo, env.ctx.config.data_dir)
        for issue in issues:
            asset_part = f" asset={issue.asset_id}" if issue.asset_id else ""
            typer.echo(f"[{issue.kind}] {issue.file_path} -> {issue.suggestion}{asset_part}")
        if issues:
            typer.echo(f"发现 {len(issues)} 处不一致。")
            exit_code = 1
        else:
            typer.echo("verify: 一致，未发现问题。")
            exit_code = 0
    raise typer.Exit(code=exit_code)


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


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main() -> None:
    app()


if __name__ == "__main__":
    main()
