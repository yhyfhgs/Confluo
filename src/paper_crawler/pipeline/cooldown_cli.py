"""`crawler cooldown status|clear` 子命令组（E-2；检查单 #7 / D-030 裁决点④）。

薄接线层：纯逻辑在 `pipeline/cooldown.py`；本模块只做参数解析、退出码映射与
呈现（同 `auth/cli.py` 先例，见其模块 docstring"薄接线层"表述）。由 `cli.py`
挂载为 `cooldown` 子 app（§1 模块表）。

**CLI 进程无常驻 `PipelineRunner` 实例**（T3 卡已裁决）：两条命令都只
`Config.load(home)` 拿到 `config.home` 再直接消费 `pipeline/cooldown.py` 的
读写函数——不装配 DB/`VenueRegistry`/`StageContext`（同 `auth/cli.py::_build_manager`
"轻装配"先例）。

- `status`：扫 `state/cooldown/` 目录列出全部键——域级新键（asset URL host）与
  旧 `<adapter_id>` 平台级键**如实并列**（E-1/D-030 裁决③"保留不破坏"，本卡不做
  旧键迁移，见 `pipeline/cooldown.list_entries` 模块 docstring）+ 剩余冷却窗
  （已过期标注"已过期"，供人工判断是否需要 `crawler resume --all`）。损坏文件
  经 `cooldown.scan_problems` 另行侦测，逐个响亮 WARNING（文件名+原因）——不得
  静默归零成"看起来跟真空一样"（独立审查 P1 修复）。
- `clear`：按键删除单个冷却文件，或 `--all` 清空全部；均幂等（键不存在/目录
  为空不报错，返回 0 计数）。`KEY` 非法（路径穿越等，`cooldown.cooldown_path`
  P0 修复）→ 响亮报错退出 2，不静默吞、更不会真的删到 `state/cooldown/` 之外。

退出码：两命令正常路径恒 0（只读呈现/幂等清理，无"业务失败"语义，同
`auth status`/`resume`/`retry` 口径；`status` 遇损坏文件仍恒 0——WARNING 是
诊断信息非失败）；`clear` 未指定 KEY 也未给 `--all`，或两者同时指定，或 KEY
未通过白名单校验 → 2（用法/配置错，"必须指定/不可同给"二段校验同 `watch`/
`subs watch` 先例——`resume` 只查"两者都不给"，不查"两者都给"，并非本命令
的先例来源）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from paper_crawler.config import Config
from paper_crawler.errors import CrawlerError
from paper_crawler.obslog import log_event, setup_logging
from paper_crawler.pipeline import cooldown

# 与 cli.py 的 HomeOpt/VerboseOpt 同语义（本地声明——同 auth/cli.py 先例：
# cooldown_cli 在 cli.py 顶层被 import，反向顶层 import cli 会撞上半初始化模块）。
_HomeOpt = Annotated[
    Path | None,
    typer.Option("--home", help="运行时目录；等价 $PAPER_CRAWLER_HOME，且优先于它"),
]
_VerboseOpt = Annotated[
    bool, typer.Option("--verbose", help="控制台日志级别调到 DEBUG（文件日志恒全量）")
]

cooldown_app = typer.Typer(
    no_args_is_help=True,
    help="挑战冷却（§8.4）状态查看与清理：跨运行持久化于 state/cooldown/ 的域级/平台级键。",
)


def _load_config(home: Path | None, verbose: bool) -> Config:
    """轻装配：`Config.load` + `setup_logging`（无 DB/registry；测试注入缝）。"""
    config = Config.load(home)
    setup_logging(config.log_dir, console_level="DEBUG" if verbose else "INFO")
    return config


def _format_remaining(entry: cooldown.CooldownEntry, now: datetime) -> str:
    if not entry.active:
        return "已过期"
    remaining = entry.until - now
    total_seconds = int(remaining.total_seconds())
    hours, rem_seconds = divmod(total_seconds, 3600)
    minutes = rem_seconds // 60
    return f"{hours}h{minutes}m"


@cooldown_app.command("status")
def cooldown_status(home: _HomeOpt = None, verbose: _VerboseOpt = False) -> None:
    """列出 `state/cooldown/` 下全部冷却键：key / until / remaining（或"已过期"）。

    只读扫描，不构造 `PipelineRunner`（同 `crawler status` 先例：运维查询类命令
    不触发其 `recover_running`/`cleanup_tmp` 副作用）。损坏文件不静默跳过——先
    逐个 WARNING 列出文件名与原因（独立审查 P1 修复：目录只含损坏文件时若无此
    提示，会跟真空目录呈现得一模一样，误导用户"无冷却记录"）。
    """
    config = _load_config(home, verbose)
    now = datetime.now(UTC)

    for filename, reason in cooldown.scan_problems(config.home):
        message = f"冷却文件损坏已跳过: {filename}（{reason}）"
        typer.echo(f"警告: {message}", err=True)
        log_event("WARNING", message)

    entries = cooldown.list_entries(config.home, now=now)
    if not entries:
        typer.echo(f"（无冷却记录：{cooldown.cooldown_dir(config.home)}）")
        raise typer.Exit(code=0)
    from paper_crawler.cli import _render_table  # 迟到 import：cli.py 顶层挂载本子 app

    typer.echo(
        _render_table(
            ["key", "until", "remaining"],
            [
                [entry.key, entry.until.isoformat(), _format_remaining(entry, now)]
                for entry in entries
            ],
        )
    )
    raise typer.Exit(code=0)


@cooldown_app.command("clear")
def cooldown_clear(
    key: Annotated[str | None, typer.Argument(help="要清除的冷却键（域名或 adapter_id）")] = None,
    all_: Annotated[bool, typer.Option("--all", help="清空全部冷却记录")] = False,
    home: _HomeOpt = None,
    verbose: _VerboseOpt = False,
) -> None:
    """删除冷却文件；必须指定 KEY 或 `--all` 之一，二者不可同给（同 `watch`/
    `subs watch` 的"必须指定 NAME 或 --all"+"NAME 与 --all 不能同时指定"
    二段校验先例——`resume` 只查"两者都不给"一段，不是本命令的先例来源）。

    `KEY` 未通过白名单校验（路径穿越等，`cooldown.cooldown_path` P0 修复）→
    退出码 2，清楚报错，不裸抛 traceback。
    """
    if key is None and not all_:
        typer.echo("错误: 必须指定 KEY 或 --all", err=True)
        raise typer.Exit(code=2)
    if key is not None and all_:
        typer.echo("错误: KEY 与 --all 不可同时指定", err=True)
        raise typer.Exit(code=2)

    config = _load_config(home, verbose)
    try:
        removed = cooldown.clear(config.home, key)
    except CrawlerError as exc:
        typer.echo(f"错误: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"已清除 {removed} 条冷却记录")
    raise typer.Exit(code=0)


__all__ = ["cooldown_app"]
