"""`crawler dedupe review|decide|revert|groups` 子命令组（T13；AC-7.3）。

薄接线层：语义与事务全在 `storage/repo.py`（`list_candidates`/`decide_candidate`/
`revert_candidate`/`merged_*`，权威说明见该模块「dedupe review 与 same_as 聚合语义」
注释块）；本模块只做参数解析、呈现与退出码映射（同 `auth/cli.py`、
`pipeline/cooldown_cli.py` 的"薄接线层"先例）。由 `cli.py` 挂载为 `dedupe` 子 app。

**离线非交互**（controller 已裁，与本项目 CLI 文化一致）：`review` 只**列**证据、不做
TUI 问答；裁决走显式的 `decide <PAPER_A> <PAPER_B> merge|reject`，回滚走
`revert <PAPER_A> <PAPER_B>`。理由：①与 `auth`/`cooldown`/`status` 等既有命令同构
（全部一次性、可脚本化、无常驻状态）；②去重裁决是**有副作用且需留痕**的判断，显式
命令行天然可复制进工作日志、可在 shell history 里复盘，交互式选择做不到；③`review`
的每条输出直接附上可复制的 `decide` 命令行（同 `verify` 打印真实可执行修复命令的先例），
交互的便利性用"可复制的下一步"补齐，不必引入 TUI 依赖。

**轻装配**（同 `auth/cli.py::_build_manager`、`cooldown_cli._load_config` 先例）：只
`Config.load(home)` + `Database`+`migrate` + `Repo`——不构造 `PipelineRunner`/
`VenueRegistry`/adapters/HTTP 客户端。dedupe 是纯库内操作，零网络。

退出码：
- `review`/`groups`：只读呈现，恒 `0`（空结果打印提示行，不是失败）；`--state` 取值
  非法 → `2`；
- `decide`/`revert`：成功（含"幂等无改动"）→ `0`；未知 paper id、两 paper 之间没有
  `candidate_duplicate` 边（含只有 `preprint_of` 的情形——kind 隔离）、裁决词非法 → `2`。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

import typer

from paper_crawler.config import Config
from paper_crawler.errors import CrawlerError
from paper_crawler.obslog import setup_logging
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import (
    CANDIDATE_STATES,
    DEDUPE_DECISIONS,
    DedupeCandidate,
    MergedView,
    PaperBrief,
    Repo,
)

# 与 cli.py 的 HomeOpt/VerboseOpt 同语义（本地声明——同 `auth/cli.py`/`cooldown_cli.py`
# 先例：本模块在 cli.py 顶层被 import，反向顶层 import cli 会撞上半初始化模块）。
_HomeOpt = Annotated[
    Path | None,
    typer.Option("--home", help="运行时目录；等价 $PAPER_CRAWLER_HOME，且优先于它"),
]
_VerboseOpt = Annotated[
    bool, typer.Option("--verbose", help="控制台日志级别调到 DEBUG（文件日志恒全量）")
]
_DEFAULT_REVIEW_LIMIT = 20

dedupe_app = typer.Typer(
    no_args_is_help=True,
    help="去重审核（design/06 §3）：列候选证据、人工 merge/reject、可回滚；物理不删行。",
)


@contextmanager
def _repo(home: Path | None, verbose: bool) -> Iterator[Repo]:
    """轻装配：Config + 日志 + DB(migrate) + Repo；退出时关连接（同 `cli._env` 的清理纪律）。"""
    try:
        config = Config.load(home)
    except CrawlerError as exc:  # 分层加载护栏/配置语法错（同 `cli._env`）
        typer.echo(f"错误: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    setup_logging(config.log_dir, console_level="DEBUG" if verbose else "INFO")
    db = Database(config.db_path)
    db.migrate()
    try:
        yield Repo(db)
    finally:
        db.close()


def _indent(text: str, prefix: str = "  ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def _brief_row(label: str, brief: PaperBrief) -> list[str]:
    return [
        label,
        brief.paper_id,
        brief.title,
        brief.venue_id or "-",
        str(brief.year) if brief.year is not None else "-",
        ", ".join(brief.identifiers) or "-",
        str(brief.asset_count),
    ]


def _brief_table(label_header: str, rows: list[list[str]]) -> str:
    """两/多行 paper 并排表（`_render_table` 按 `len()` 定宽，故标签列一律 ASCII 免错位）。"""
    from paper_crawler.cli import _render_table  # 迟到 import：cli.py 顶层挂载本子 app

    return _render_table(
        [label_header, "paper_id", "title", "venue", "year", "identifiers", "assets"], rows
    )


def _render_candidate(index: int, candidate: DedupeCandidate) -> str:
    """一条候选的人读展示：表头行（强度/reason/裁决态）+ 两 paper 并排 + 证据 + 下一步命令。"""
    strength = "-" if candidate.confidence is None else f"{candidate.confidence:g}"
    head = (
        f"[{index}] 强度 {strength}  reason {candidate.reason or '-'}  "
        f"裁决 {candidate.decided or '待审'}"
    )
    table = _brief_table(
        "side", [_brief_row("A", candidate.paper_a), _brief_row("B", candidate.paper_b)]
    )
    evidence = json.dumps(dict(candidate.evidence), ensure_ascii=False, sort_keys=True)
    action = (
        f"crawler dedupe decide {candidate.paper_a.paper_id} "
        f"{candidate.paper_b.paper_id} merge|reject"
    )
    return "\n".join(
        [head, _indent(table), _indent(f"证据  {evidence}"), _indent(f"裁决  {action}")]
    )


def _render_group(index: int, view: MergedView) -> str:
    """一个合并类的展示：主行 + 被折叠成员并排 + identifier 并集（归并视图，聚合语义 5）。"""
    head = (
        f"[{index}] 主行 {view.canonical.paper_id}  成员 {len(view.members)}  "
        f"identifier {len(view.identifiers)}  asset {view.asset_count}"
    )
    rows = [
        _brief_row("canon" if member.paper_id == view.canonical.paper_id else "folded", member)
        for member in view.members
    ]
    table = _brief_table("role", rows)
    union = ", ".join(view.identifiers) or "-"
    return "\n".join([head, _indent(table), _indent(f"合并 identifier  {union}")])


@dedupe_app.command("review")
def dedupe_review(
    state: Annotated[
        str,
        typer.Option("--state", help=f"候选状态：{'/'.join(CANDIDATE_STATES)}"),
    ] = "pending",
    limit: Annotated[
        int, typer.Option("--limit", help="最多显示多少条（按证据强度降序取前 N；0 = 不限）")
    ] = _DEFAULT_REVIEW_LIMIT,
    home: _HomeOpt = None,
    verbose: _VerboseOpt = False,
) -> None:
    """逐条展示待审去重候选的证据（AC-7.3 前半）：两 paper 并排 + 原始 evidence + 裁决命令。

    只读；`--state merged|rejected|all` 查历史裁决（reject 过的对不再出现在默认列表里，
    但永远可查——关系行绝不物理删除）。`preprint_of` 边不在此列（kind 隔离）。
    """
    with _repo(home, verbose) as repo:
        try:
            total = repo.count_candidates(state=state)
            candidates = repo.list_candidates(state=state, limit=max(limit, 0) or None)
        except CrawlerError as exc:
            typer.echo(f"错误: {exc}", err=True)
            raise typer.Exit(code=2) from exc
        if not candidates:
            typer.echo(f"（无匹配的去重候选：state={state}）")
            raise typer.Exit(code=0)
        typer.echo(f"去重候选 {total} 条（state={state}，显示 {len(candidates)} 条）\n")
        for index, candidate in enumerate(candidates, start=1):
            typer.echo(_render_candidate(index, candidate))
            typer.echo("")
        if len(candidates) < total:
            typer.echo(f"（另有 {total - len(candidates)} 条未显示，用 --limit 调整）")
    raise typer.Exit(code=0)


@dedupe_app.command("decide")
def dedupe_decide(
    paper_a: Annotated[str, typer.Argument(help="一侧 paper id（顺序无关）")],
    paper_b: Annotated[str, typer.Argument(help="另一侧 paper id")],
    decision: Annotated[str, typer.Argument(help="merge 或 reject")],
    home: _HomeOpt = None,
    verbose: _VerboseOpt = False,
) -> None:
    """人工裁决一对候选（AC-7.3 后半）：`merge` 落 same_as(decided=merged)，`reject` 置拒。

    两 paper 行、identifier、asset、磁盘文件全程零改动——`merge` 只是让查询层把两行按
    一篇著作显示（`crawler dedupe groups` 可查），随时可 `crawler dedupe revert` 回滚。
    """
    if decision not in DEDUPE_DECISIONS:
        typer.echo(f"错误: 未知裁决 {decision!r}；可选：{', '.join(DEDUPE_DECISIONS)}", err=True)
        raise typer.Exit(code=2)
    with _repo(home, verbose) as repo:
        try:
            outcome = repo.decide_candidate(paper_a, paper_b, decision)
        except CrawlerError as exc:
            typer.echo(f"错误: {exc}", err=True)
            raise typer.Exit(code=2) from exc
        pair = f"{outcome.paper_a} ~ {outcome.paper_b}"
        if not outcome.changed:
            typer.echo(f"已是 {outcome.decided}，无改动：{pair}")
        elif decision == "merge":
            typer.echo(
                f"已合并（查询层聚合）：{pair}\n"
                "两 paper 行原样保留，未删除任何数据；回滚："
                f"crawler dedupe revert {outcome.paper_a} {outcome.paper_b}"
            )
        else:
            typer.echo(f"已拒绝合并：{pair}（不再出现在待审列表，可用 --state rejected 查历史）")
    raise typer.Exit(code=0)


@dedupe_app.command("revert")
def dedupe_revert(
    paper_a: Annotated[str, typer.Argument(help="一侧 paper id（顺序无关）")],
    paper_b: Annotated[str, typer.Argument(help="另一侧 paper id")],
    home: _HomeOpt = None,
    verbose: _VerboseOpt = False,
) -> None:
    """回滚一对已裁决的候选：`decided` 置回 NULL，聚合视图随之还原，候选回到待审列表。"""
    with _repo(home, verbose) as repo:
        try:
            outcome = repo.revert_candidate(paper_a, paper_b)
        except CrawlerError as exc:
            typer.echo(f"错误: {exc}", err=True)
            raise typer.Exit(code=2) from exc
        pair = f"{outcome.paper_a} ~ {outcome.paper_b}"
        if outcome.changed:
            typer.echo(f"已回滚为待审：{pair}")
        else:
            typer.echo(f"已是待审状态，无需回滚：{pair}")
    raise typer.Exit(code=0)


@dedupe_app.command("groups")
def dedupe_groups(home: _HomeOpt = None, verbose: _VerboseOpt = False) -> None:
    """列出全部 `same_as(decided='merged')` 合并类：主行、被折叠成员与归并后的 identifier。

    这是"查询层聚合"的直观自查面：`crawler list` 折叠掉的那些行在此逐类可见
    （聚合从不删数据，只是换一种显示）。
    """
    with _repo(home, verbose) as repo:
        views = repo.merged_views()
        if not views:
            typer.echo("（无 same_as(merged) 合并组）")
            raise typer.Exit(code=0)
        typer.echo(f"合并组 {len(views)} 个\n")
        for index, view in enumerate(views, start=1):
            typer.echo(_render_group(index, view))
            typer.echo("")
    raise typer.Exit(code=0)


__all__ = ["dedupe_app"]
