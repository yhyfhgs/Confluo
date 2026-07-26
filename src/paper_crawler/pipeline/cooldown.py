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
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

CHALLENGE_COOLDOWN = timedelta(hours=24)  # §8.4 平台冷却窗口（原 `runner._CHALLENGE_COOLDOWN`）


def cooldown_dir(home: Path) -> Path:
    """`state/cooldown/` 目录（不保证存在——读侧按需判 `.is_dir()`，写侧按需 mkdir）。"""
    return home / "state" / "cooldown"


def cooldown_path(home: Path, key: str) -> Path:
    return cooldown_dir(home) / f"{key}.json"


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
    """
    path = cooldown_path(home, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"until": until.isoformat()}), encoding="utf-8")


def read_until(home: Path, key: str) -> datetime | None:
    """读单键的 `until`；文件不存在/损坏（非法 JSON、缺 `until`、非法时间戳）→ None（不抛）。"""
    path = cooldown_path(home, key)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return datetime.fromisoformat(str(data["until"]))
    except (OSError, ValueError, KeyError):
        return None


def drop(home: Path, key: str) -> None:
    """删单键落盘文件（幂等；失败静默——纯清理，不参与判定）。"""
    with contextlib.suppress(OSError):
        cooldown_path(home, key).unlink(missing_ok=True)


@dataclass(frozen=True)
class CooldownEntry:
    """`crawler cooldown status` 消费的一行：键 + 到期时刻 + 是否仍在冷却中。"""

    key: str
    until: datetime
    active: bool


def list_entries(home: Path, *, now: datetime) -> list[CooldownEntry]:
    """扫 `state/cooldown/` 列出全部键（`crawler cooldown status` 消费）。

    域级新键与旧 `adapter_id` 键如实并列（E-1 未做迁移，两形态键单从文件名无法
    区分——本函数不试图猜测键的"形态"，只如实读取文件名与内容）；损坏文件
    （非法 JSON/缺 `until`/非法时间戳）静默跳过、不抛，与 `read_until`/既有
    `_challenge_cooldown_active` 的容错姿态一致。按 key 排序，输出确定。
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


def clear(home: Path, key: str | None) -> int:
    """删除冷却文件；`key=None` 清空全部。返回实际删除的文件数（`crawler cooldown clear` 消费）。

    幂等：键不存在/目录为空/目录不存在 → 返回 0，不报错。
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
