"""`crawler auth login/status/logout` 子命令组（auth-framework §4；T1b）。

薄接线层：纯逻辑在 `auth/manager.py`/`auth/store.py`；本模块只做参数解析、
退出码映射与呈现。由 `cli.py` 挂载为 `auth` 子 app（§1 模块表）。

退出码契约（§4 / design/05 Task 8 口径）：

- `login`：0 成功；2 用法/配置错（provider 未知、key 缺失、未装 `[auth-browser]`——
  均属"配置后重来"类，`AuthRequired` 一律归此）；1 探测失败（探针不 OK / 网络失败 /
  `Challenged`——如实上报不重试）。
- `status`：恒 0（只读呈现非对账判据，同 `oa-report` 口径；不触发真实探测）。
- `logout`：0 成功（含"本就无残留"幂等）；2 provider 未知。

auth 命令不需要 DB/pipeline——不走 `_env` 全装配，只 `Config.load` + `setup_logging`
（轻装配；home/-v 语义同既有全局项）。
"""

from pathlib import Path
from typing import Annotated, NoReturn

import typer

from paper_crawler.auth.manager import AuthManager
from paper_crawler.config import Config
from paper_crawler.errors import AuthRequired, CrawlerError
from paper_crawler.obslog import setup_logging
from paper_crawler.types import HealthStatus

# 与 cli.py 的 HomeOpt/VerboseOpt 同语义（此处本地声明——auth.cli 在 cli.py 顶层被
# import，反向顶层 import cli 会撞上半初始化模块；文案保持一致）。
_HomeOpt = Annotated[
    Path | None,
    typer.Option("--home", help="运行时目录；等价 $PAPER_CRAWLER_HOME，且优先于它"),
]
_VerboseOpt = Annotated[
    bool, typer.Option("--verbose", help="控制台日志级别调到 DEBUG（文件日志恒全量）")
]
_ProfileOpt = Annotated[
    str | None,
    typer.Option(
        "--profile", help="临时覆盖 active_profile（后缀式 `campus` 或全键 `oup@campus`）"
    ),
]

auth_app = typer.Typer(
    no_args_is_help=True,
    help="认证 provider 管理：login（首登/校验）、status（只读呈现）、logout（取证式清理）。",
)


def _build_manager(home: Path | None, verbose: bool) -> AuthManager:
    """轻装配：Config.load + setup_logging + AuthManager（无 DB；测试注入缝）。"""
    config = Config.load(home)
    setup_logging(config.log_dir, console_level="DEBUG" if verbose else "INFO")
    return AuthManager(config)


def _fail(exc: CrawlerError, *, code: int) -> NoReturn:
    line = f"错误: {exc}"
    if exc.detail:
        line += f"（{exc.detail}）"
    typer.echo(line, err=True)
    raise typer.Exit(code=code)


@auth_app.command("login")
def auth_login(
    provider: Annotated[str, typer.Argument(help="profiles.toml 键（或 platform id）")],
    profile: _ProfileOpt = None,
    home: _HomeOpt = None,
    verbose: _VerboseOpt = False,
) -> None:
    """首登/凭证校验（§4.1；人在回路 D-006——绝不自动填密码、绝不自动过 MFA）。

    api_key：校验 key 已配置（config/env/keyring）；cookie_session/sso_flow/ezproxy：
    headed 浏览器首登 → storage_state 加密落盘 → 探针验证（有 probe_url 时）。
    """
    manager = _build_manager(home, verbose)
    try:
        target = manager.resolve(provider, profile=profile)
    except CrawlerError as exc:
        _fail(exc, code=2)  # provider 未知/歧义 → 用法错（§4.1）

    prof = manager.profiles()[target.provider_id]
    if prof.kind == "sso_flow" and prof.wayf_hint:
        typer.echo(f"WAYF 机构选择提示：{prof.wayf_hint}")

    try:
        handle = manager.ensure_session(target.provider_id, interactive=True)
        status = target.health_check(handle)
    except AuthRequired as exc:
        _fail(exc, code=2)  # key 缺失 / 未装 [auth-browser]（§4.1 退出码表）
    except CrawlerError as exc:
        _fail(exc, code=1)  # 探测失败/风控挑战（Challenged 如实上报，绝不重试）

    if status is not HealthStatus.OK:
        typer.echo(f"错误: {target.provider_id} 登录探针未通过（{status}）", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"{target.provider_id}: ready（kind={target.kind}）")
    raise typer.Exit(code=0)


@auth_app.command("status")
def auth_status(home: _HomeOpt = None, verbose: _VerboseOpt = False) -> None:
    """provider 状态表（§4.2）：只读——读 meta sidecar 与本地 key 存在性，
    **不触发真实探测**（不消耗配额/不触风控）。退出码恒 0。"""
    manager = _build_manager(home, verbose)
    rows = manager.status_rows()
    if not rows:
        typer.echo(f"（无 provider 配置：{manager.store.profiles_path}）")
        raise typer.Exit(code=0)
    from paper_crawler.cli import _render_table  # 迟到 import：cli.py 顶层挂载本子 app

    typer.echo(
        _render_table(
            ["provider", "kind", "backend", "session", "last_health", "est_expiry", "state"],
            [
                [
                    row.provider,
                    row.kind,
                    row.backend,
                    row.session,
                    row.last_health,
                    row.est_expiry,
                    row.state,
                ]
                for row in rows
            ],
        )
    )
    raise typer.Exit(code=0)


@auth_app.command("logout")
def auth_logout(
    provider: Annotated[str, typer.Argument(help="profiles.toml 键")],
    home: _HomeOpt = None,
) -> None:
    """取证式登出（§4.3 / AC-4.5，B-m6 按 kind 分列）：有状态类覆写删除
    `state/<ref>.enc`+meta+按需清主密钥；api_key 类清 keyring 副本——
    **不删**用户 config.toml 明文槽。"""
    manager = _build_manager(home, verbose=False)
    try:
        target = manager.logout(provider)
    except CrawlerError as exc:
        _fail(exc, code=2)  # provider 未知 → 2（§4.3）
    typer.echo(f"{target.provider_id}: 已登出（取证式清理，AC-4.5）")
    raise typer.Exit(code=0)


__all__ = ["auth_app"]
