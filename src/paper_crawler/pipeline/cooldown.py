"""Cooldown 状态读写公用模块（E-2；检查单 #7 / D-030 裁决点④）。

挑战冷却（§8.4）的落盘布局与判定逻辑集中于此，供 `PipelineRunner`（写入侧，
`pipeline/runner.py` 委托本模块）与 `crawler cooldown` CLI（只读/清理侧，
`pipeline/cooldown_cli.py`；CLI 进程无常驻 `PipelineRunner` 实例，直接消费
本模块）共用——避免两处各自实现一份读写逻辑漂移。

键设计（E-1/D-030 裁决③，本模块**原样保留、不重新设计**——T3 卡已裁决歧义：
"E-1 的域级新键/adapter_id 旧键兼容读是有意设计，保留不破坏"）：域级新键
（asset URL host）优先、旧 `<adapter_id>` 平台级键向前兼容，两者均只读不迁移。
本模块只管"键→文件"的读写判定，**不知道"域怎么来的"**——venue/asset 路由到
host/adapter_id 是调用方（`runner.py`）职责，本模块零 `VenueRegistry` 依赖，
CLI 侧因此可以只经 `Config.load(home)` 直接消费，无需装配 DB/registry。

落盘布局：`<home>/state/cooldown/<key>.json`，形如 `{"until": "<ISO8601>"}`；
单键单文件，无索引文件（E-2"全量统一"到此程度即闭合，索引文件属更深重构，
T3 卡已裁决 YAGNI，不做）。

**路径穿越防护（独立审查 P0 修复）**：写侧键来自 `host_of()`（urlsplit 解析的
URL hostname，语法上不含 `/`）与 adapter_id（内部受控标识符）——恒安全；但
CLI 侧 `clear <KEY>` 的键来自**用户输入**，未经校验时 `key="../../../victim/x"`
可令 `cooldown_path` 拼出的路径逃出 `state/cooldown/`，被 `clear`/`write`/
`read_until`/`drop` 真实读写到 home 之外（曾实测 `crawler cooldown clear
"../../../victim/important"` 删除 home 外文件）。`cooldown_path` 是全部读写
函数唯一的路径构造入口（write/read_until/drop/clear 均经它），故校验只需
在此**一处**生效：①白名单校验 `key`（`_validate_key`，合法键=域名/adapter_id
形态：字母数字开头结尾，中间允许 `.`/`-`/`_`，拒绝 `/`、`\\`、纯 `.`/`..`）；
②防御纵深——校验通过后仍对拼出的路径做 `is_relative_to(cooldown_dir)` 二次
确认（正常情况下①已保证不可能触发，此层只防①未来被削弱/绕过）。两层任一
不过 → 响亮 `CrawlerError(CONFIG)`，不静默拒绝、不静默截断、不静默改写。
"""

from __future__ import annotations

import contextlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from paper_crawler.errors import CrawlerError, ErrorClass

CHALLENGE_COOLDOWN = timedelta(hours=24)  # §8.4 平台冷却窗口（原 `runner._CHALLENGE_COOLDOWN`）

# 合法冷却键：字母/数字开头与结尾，中间允许字母/数字/`.`/`-`/`_`（域名/adapter_id
# 形态的公共超集）。天然拒绝：空串、含 `/`、含 `\`、字面 `.`/`..`（首尾必须是
# 字母数字，`.`/`..` 首字符即不匹配）——见模块 docstring"路径穿越防护"段。
_KEY_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?")


def _validate_key(key: str) -> None:
    """白名单校验冷却键；非法 → 响亮 `CrawlerError(CONFIG)`（P0 修复，见模块 docstring）。"""
    if not _KEY_RE.fullmatch(key):
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"非法冷却键: {key!r}",
            detail="合法键形如域名（pubs.example.org）或 adapter_id（mock_platform）："
            "仅字母/数字/`.`/`-`/`_`，首尾须为字母或数字，不得含路径分隔符或为 `.`/`..`",
        )


def cooldown_dir(home: Path) -> Path:
    """`state/cooldown/` 目录（不保证存在——读侧按需判 `.is_dir()`，写侧按需 mkdir）。"""
    return home / "state" / "cooldown"


def cooldown_path(home: Path, key: str) -> Path:
    """`state/cooldown/<key>.json` 的路径——全部读写函数（write/read_until/drop/clear）
    唯一的路径构造入口，两层路径穿越防护均在此生效（P0 修复，见模块 docstring）。
    """
    _validate_key(key)  # 层①：白名单
    directory = cooldown_dir(home)
    path = directory / f"{key}.json"
    if not path.resolve().is_relative_to(directory.resolve()):  # 层②：防御纵深
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"非法冷却键: {key!r}",
            detail=f"解析后路径逃出 {directory} 范围",
        )
    return path


def host_of(raw_url: str | None) -> str | None:
    """asset URL → host（域级键来源）；无 URL/解析不出 host 时 None。

    原 `runner._cooldown_keys` 内联逻辑的纯函数化：`raw_url` 为空/None → None；
    相对路径（无 host，schema 允许）解析不出 hostname → 同样 None。
    """
    return urlsplit(str(raw_url)).hostname if raw_url else None


def resolve_keys(host: str | None, adapter_id: str | None) -> tuple[str, ...]:
    """候选键集合：域级新键在前、`adapter_id` 旧键在后（去重）——E-1/D-030 裁决③的落地形态。

    调用方（`runner.py`）职责：`host` 取自本任务实际请求的 asset URL；`adapter_id`
    取自 venue 路由（未知/畸形 venue 或路由失败时传 None）。两者皆空 → 空元组
    （无键可写/可查，如实反映"手上没有证据"，不猜 `domains[0]`）。

    本函数只做字符串组合，不触碰文件系统——白名单校验统一在 `cooldown_path`
    生效（写侧的 host/adapter_id 语法上恒合法，见模块 docstring），这里不重复
    校验以免制造第二套可能漂移的规则；任何非法候选键在实际读写时（`write`/
    `read_until`）经 `cooldown_path` 响亮报错，不会被静默使用。
    """
    keys: list[str] = []
    if host:
        keys.append(host)
    if adapter_id and adapter_id not in keys:
        keys.append(adapter_id)
    return tuple(keys)


def write(home: Path, key: str, until: datetime) -> None:
    """落盘冷却状态（跨运行持久化，§8.4）。

    调用方负责捕获 `OSError`（落盘失败不阻断运行态生效——见 runner 的
    `_enter_challenge_cooldown`：写失败只 WARNING 日志，运行态字典仍生效）。
    `key` 非法时 `cooldown_path` 抛 `CrawlerError`（不属 `OSError`，不会被
    调用方的 `except OSError` 吞掉——响亮传播）。
    """
    path = cooldown_path(home, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"until": until.isoformat()}), encoding="utf-8")


def read_until(home: Path, key: str) -> datetime | None:
    """读单键的 `until`；文件不存在/损坏（非法 JSON、缺 `until`、非法时间戳）→ None（不抛）。

    `key` 本身非法（路径穿越等）→ `cooldown_path` 响亮抛 `CrawlerError`（与"文件
    内容损坏"是两类不同问题：前者是调用方给错键，后者是磁盘上的数据坏了）。
    """
    path = cooldown_path(home, key)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return datetime.fromisoformat(str(data["until"]))
    except (OSError, ValueError, KeyError):
        return None


def drop(home: Path, key: str) -> None:
    """删单键落盘文件（幂等；文件系统失败静默——纯清理，不参与判定）。

    `key` 本身非法 → `cooldown_path` 响亮抛 `CrawlerError`（不在本函数的
    `except OSError` 吞掉范围内——非法键是调用方错误，不是"删不掉"的
    正常清理失败）。
    """
    path = cooldown_path(home, key)
    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)


@dataclass(frozen=True)
class CooldownEntry:
    """`crawler cooldown status` 消费的一行：键 + 到期时刻 + 是否仍在冷却中。"""

    key: str
    until: datetime
    active: bool


def list_entries(home: Path, *, now: datetime) -> list[CooldownEntry]:
    """扫 `state/cooldown/` 列出全部**可解析**的键（`crawler cooldown status` 消费）。

    域级新键与旧 `adapter_id` 键如实并列（E-1 未做迁移，两形态键单从文件名无法
    区分——本函数不试图猜测键的"形态"，只如实读取文件名与内容）；损坏文件
    （非法 JSON/缺 `until`/非法时间戳）静默跳过、不抛，与 `read_until` 的容错
    姿态一致——**但"跳过"不等于"隐瞒"**：损坏文件的诊断由姊妹函数
    `scan_problems` 单独提供，`status` 命令两者都调用（独立审查 P1 修复：目录
    只含损坏文件时不得呈现得跟真空一样）。本函数按 key 排序，输出确定；键直接
    取自已存在的文件名（`path.stem`），不经 `cooldown_path`/白名单校验——
    磁盘上已有的文件名不受"新写入路径穿越"风险约束。
    """
    directory = cooldown_dir(home)
    if not directory.is_dir():
        return []
    entries: list[CooldownEntry] = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            until = datetime.fromisoformat(str(data["until"]))
        except (OSError, ValueError, KeyError):
            continue
        entries.append(CooldownEntry(key=path.stem, until=until, active=now < until))
    return entries


def scan_problems(home: Path) -> list[tuple[str, str]]:
    """扫 `state/cooldown/` 找出**无法解析**的文件（`crawler cooldown status` 消费，
    供其呈现响亮 WARNING——独立审查 P1 修复：`list_entries` 对损坏文件的静默跳过
    在"只列有效键"这个用途上是对的，但会让 `status` 在目录只含损坏文件时显得跟
    真空一样，误导用户"无冷却记录"）。

    返回 `(文件名, 原因)` 列表；目录不存在/全部文件可解析 → 空列表。与
    `list_entries` 各自独立扫描目录（两者关注点不同——一个只要有效键、一个只要
    "坏在哪"，刻意不合并成一次扫描双返回，保持职责单一、互不牵连既有调用方）。
    """
    directory = cooldown_dir(home)
    if not directory.is_dir():
        return []
    problems: list[tuple[str, str]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            datetime.fromisoformat(str(data["until"]))
        except (OSError, ValueError, KeyError) as exc:
            problems.append((path.name, f"{type(exc).__name__}: {exc}"))
    return problems


def clear(home: Path, key: str | None) -> int:
    """删除冷却文件；`key=None` 清空全部。返回实际删除的文件数（`crawler cooldown clear` 消费）。

    幂等：键不存在/目录为空/目录不存在 → 返回 0，不报错。`key` 非法（路径穿越等，
    P0 修复）→ `cooldown_path` 响亮抛 `CrawlerError`，调用方（CLI 层）负责转
    退出码 2；`--all`（`key=None`）分支只枚举目录内**已存在**的 `*.json`
    文件名再逐个 `unlink`，不经 `cooldown_path` 重新拼路径，不受此风险面影响。
    """
    if key is not None:
        path = cooldown_path(home, key)
        if path.is_file():
            path.unlink()
            return 1
        return 0
    directory = cooldown_dir(home)
    if not directory.is_dir():
        return 0
    removed = 0
    for path in sorted(directory.glob("*.json")):
        path.unlink()
        removed += 1
    return removed
