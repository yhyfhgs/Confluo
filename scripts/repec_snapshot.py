#!/usr/bin/env python3
"""RePEc bulk ReDIF 快照取回（Phase 7 T8；[D-035](../docs/plan/decision-log.md) 决策 3）。

**本脚本是 repec 通道唯一的网络面**——这是 D-035 的结构性要点，不是组织偏好：把取快照的
HTTP 动作放在 `src/paper_crawler` **之外**，`src` 侧 `RepecAdapter.enrich_batch` 的"零网络"
就成了**可被 socket 猴补机械证明的结构事实**（`tests/unit/test_repec_adapter.py`），而非靠
自律。同时取快照本就是低频运维动作，不属爬虫功能面。

**定位（同 `scripts/budget_ledger.py` 先例）**：不入 `paper_crawler` 包 ⇒ 不占门禁覆盖率
（`[tool.coverage.run] source = ["paper_crawler"]`）、不入 mypy 扫描面（`files = ["src"]`）；
仍须过 `ruff check .` / `ruff format --check .`（两者扫全仓库）。
**代价如实记（D-035 决策 3 原文）**：本脚本的镜像回退与校验逻辑**无自动化测试**，靠 T19
在线批人工核验。

## 合规：fable 2026-07-27 裁决的三项附加条件（T19 执行时为硬约束）

T8 首步两域 robots 核验 [LIVE 2026-07-27] 结果为"无从判读"——`www2.nber.org/robots.txt`
返回 **403**（源站 Apache 亲答；403 系 `/robots.txt` 路径特异，同域数据路径探针 4/4 成功），
`repec.nber.org/robots.txt` **TLS 握手中断**。裁决：**附条件放行**（RFC 9309 §2.3.1.3 把 4xx
归 "Unavailable"、明文 crawler MAY access；ReDIF/RePEc 是为机器批量交换设计的公开分发网络，
NBER 主动发布 bulk 文件＝分发意图明示）。三项条件由本脚本承载：

- **(a) 先重试 robots 一次**：真实拉取前对目标镜像 `GET /robots.txt`（TLS 中断可能瞬时）。
  **可判读则以其为准**——目标路径被 `Disallow` 即**停手退出**，绝不"因为上次读不到所以永远
  当作放行"。
- **(b) 仍不可判读则按裁决执行，但限最小面**：`--max-requests` 默认 4（plan §3 `T8-bulk` 行
  上限）、逐请求间隔 `--delay` 默认 **≥10s**（不接受更小值）、诚实 UA（`build_user_agent`，
  D-014 格式，不伪装浏览器）。
- **(c) 数据路径遇任何拒绝信号（403/429/401/5xx）→ 立即停止并把 repec 通道"出列"回报**。
  本裁决只覆盖"robots 不可判读"，**不覆盖"数据端点明确拒绝"**——后者是站点在数据面明确
  说不，与 robots 取不到是两回事。

## 零 HTML 硬红线

只取 ReDIF bulk 文件；**绝不请求或解析** `ideas.repec.org` / `econpapers.repec.org` 的 HTML
条目页（哪怕其 robots 允许）——RePEc 官方明文强烈不建议爬 HTML 并设隐私红线（"Email
addresses are released under no circumstances"）。本脚本也**不抓目录索引页**：ReDIF 文件的
实际命名 **[未实测]**，须由执行者从 NBER 的 archive 模板读出后经 `--url` 显式给出，
默认值只是按 RePEc 惯例的候选、**不是实测事实**。

## `--dry-run` 的边界（**"零数据请求"≠"零请求"**，务必先读）

`--dry-run` 跳过的是**数据**取回；条件 (a) 的 robots 核验**照常发出 1 次真实请求**——那正是
干跑要给出的信息（"现在的 robots 判定是什么"）。故**干跑仍消耗 1 次在线预算**，须按
[online-budget.md](../docs/process/online-budget.md) 记账。T8 实现期即因误以为"干跑＝零请求"
而使 `T8-robots` 行超线 1（3/2，已入档 aggregators.md §9 修订 #20）。

用法::

    # 干跑：robots 核验（**发 1 次真实请求**）+ 计划打印；零数据请求
    uv run python scripts/repec_snapshot.py --dry-run

    # 真实取快照（T19 在线批；完成后须记 T8-bulk 账本行）
    uv run python scripts/repec_snapshot.py --home <config-home> \\
        --url https://www2.nber.org/RePEc/nbr/nberwo/nberwo.rdf

    uv run python scripts/budget_ledger.py record --row T8-bulk --session t19 \\
        --batch "repec 快照首拉" --count <实际数>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.robotparser
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from paper_crawler.adapters.repec import parse as repec_parse
from paper_crawler.config import resolve_home
from paper_crawler.useragent import build_user_agent

# 镜像：默认 `www2.nber.org`（探针 [LIVE 2026-07-26] 4/4 稳），`repec.nber.org` 为备
# （探针 1 次连接层失败 + T8 robots 核验 1 次 TLS 中断，样本小、不构成判罚）。
DEFAULT_MIRROR = "www2.nber.org"
BACKUP_MIRROR = "repec.nber.org"

# **[未实测]** ReDIF 文件的真实命名与切分（单大文件 vs 逐条文件）——RePEc 惯例候选，
# T19 执行者须从 NBER archive 模板读出实际地址后经 `--url` 覆盖（见模块 docstring）。
DEFAULT_PATH = "/RePEc/nbr/nberwo/nberwo.rdf"

# 条件 (b)：间隔下限 10s、请求数上限 4（plan §3 `T8-bulk` ≤4）。二者是**下/上限而非默认建议**
# ——命令行给出更激进的值会被拒绝（下方 `_validate_politeness`）。
MIN_DELAY_SECONDS = 10.0
MAX_REQUESTS = 4

# 条件 (c)：数据面的拒绝信号 ⇒ 立即停手并出列回报（非重试、非退避）。
REFUSAL_STATUSES = frozenset({401, 402, 403, 405, 406, 410, 429, 451})

_ARCHIVE = "nbr"
_SERIES = "nberwo"
_MANIFEST_SCHEMA = 1


class ChannelRetired(RuntimeError):
    """数据端点明确拒绝 ⇒ repec 通道出列（条件 c）。裁决不覆盖此情形，须人工复裁。"""


@dataclass(frozen=True)
class RobotsVerdict:
    """一次 robots 核验的判定。`readable=False` ⇒ 走裁决的"不可判读"分支（条件 b）。"""

    readable: bool
    allowed: bool
    detail: str


def _client(user_agent: str) -> httpx.Client:
    return httpx.Client(headers={"User-Agent": user_agent}, timeout=60.0, follow_redirects=True)


def check_robots(mirror: str, target_path: str, user_agent: str) -> RobotsVerdict:
    """条件 (a)：取 `https://<mirror>/robots.txt` 并判 `target_path` 是否被 Disallow。

    三种结局：**可判读且放行** → `(True, True)`；**可判读且禁止** → `(True, False)`（调用方
    停手）；**不可判读**（4xx/连接层失败）→ `(False, False)` 交调用方按裁决的条件 (b) 处置。
    """
    url = f"https://{mirror}/robots.txt"
    try:
        with _client(user_agent) as client:
            response = client.get(url)
    except httpx.HTTPError as exc:
        return RobotsVerdict(False, False, f"{url} 连接层失败：{type(exc).__name__}: {exc}")

    if response.status_code != 200:
        # RFC 9309 §2.3.1.3：4xx = "Unavailable" ⇒ 无可违反的规则（本项目仍按裁决走条件 b）。
        return RobotsVerdict(False, False, f"{url} → HTTP {response.status_code}（无可判读规则）")

    parser = urllib.robotparser.RobotFileParser()
    parser.parse(response.text.splitlines())
    allowed = parser.can_fetch(user_agent, f"https://{mirror}{target_path}")
    return RobotsVerdict(
        True, allowed, f"{url} → 200，{'放行' if allowed else 'Disallow'} {target_path}"
    )


def fetch_files(
    urls: list[str], *, user_agent: str, delay: float, root: Path
) -> list[repec_parse.SnapshotFile]:
    """逐 URL 取回并**原样落盘**（条件 b/c）。返回 manifest 的 `files[]` 项。

    **原样字节 + sha256**（D-035 决策 3）：ReDIF 是上游权威格式，本地解析口径可能随实现修正，
    保留原文才能不重新联网即可重解析。落盘路径 = `<root>/nbr/nberwo/<URL 末段>`——`files[].name`
    记实际名，加载器按 manifest 遍历，故**不预设文件名**。
    """
    written: list[repec_parse.SnapshotFile] = []
    with _client(user_agent) as client:
        for index, url in enumerate(urls):
            if index:
                time.sleep(delay)  # 条件 b：逐请求间隔 ≥10s
            print(f"GET {url}")
            try:
                response = client.get(url)
            except httpx.HTTPError as exc:
                raise ChannelRetired(f"{url} 连接层失败：{type(exc).__name__}: {exc}") from exc
            if response.status_code in REFUSAL_STATUSES:
                raise ChannelRetired(
                    f"{url} → HTTP {response.status_code}：数据端点明确拒绝。"
                    "fable 2026-07-27 裁决只覆盖「robots 不可判读」，**不覆盖本情形** ⇒ "
                    "立即停止取回，repec 通道出列回报，待人工复裁。"
                )
            response.raise_for_status()

            name = f"{_ARCHIVE}/{_SERIES}/{Path(urlparse(url).path).name or 'nberwo.rdf'}"
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(response.content)
            written.append(
                repec_parse.SnapshotFile(
                    name=name,
                    bytes=len(response.content),
                    sha256=hashlib.sha256(response.content).hexdigest(),
                )
            )
            print(f"  → {path} ({len(response.content)} bytes)")
    return written


def write_manifest(
    root: Path, *, mirror: str, urls: list[str], files: list[repec_parse.SnapshotFile]
) -> Path:
    """写 `manifest.json`（D-035 决策 3 冻结的字段集）；`record_count` 由实际解析结果回填。"""
    record_count = 0
    for entry in files:
        record_count += len(repec_parse.parse_redif((root / entry.name).read_bytes()))
    payload = {
        "schema": _MANIFEST_SCHEMA,
        "archive": _ARCHIVE,
        "series": [_SERIES],
        "mirror": mirror,
        "source_urls": urls,
        "fetched_at": datetime.now(UTC).isoformat(),
        "files": [{"name": f.name, "bytes": f.bytes, "sha256": f.sha256} for f in files],
        "record_count": record_count,
    }
    path = root / "manifest.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _validate_politeness(delay: float, urls: list[str]) -> str | None:
    """条件 (b) 的硬下/上限校验；越界返回错误文案（调用方拒绝执行，不静默钳值）。

    刻意**不**把过小的 delay 悄悄提到 10s：那会让调用者以为自己的参数生效了。合规约束被
    违反时应当响亮拒绝，而不是替对方改主意。
    """
    if delay < MIN_DELAY_SECONDS:
        return (
            f"--delay {delay}s 低于裁决条件 (b) 的下限 {MIN_DELAY_SECONDS}s；"
            "该间隔是合规约束，不接受更激进的值"
        )
    if len(urls) > MAX_REQUESTS:
        return f"{len(urls)} 个 --url 超过裁决条件 (b) 的上限 {MAX_REQUESTS} （plan §3 T8-bulk ≤4）"
    return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--home", type=Path, default=None, help="显式 config-home（默认走解析链）")
    parser.add_argument(
        "--mirror",
        default=DEFAULT_MIRROR,
        help=f"镜像主机（默认 {DEFAULT_MIRROR}，备 {BACKUP_MIRROR}）",
    )
    parser.add_argument(
        "--url",
        action="append",
        default=None,
        help=f"ReDIF 文件地址（可重复，≤{MAX_REQUESTS}）；默认 https://<mirror>{DEFAULT_PATH}【未实测】",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=MIN_DELAY_SECONDS,
        help=f"逐请求间隔秒（下限 {MIN_DELAY_SECONDS}，裁决条件 b）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只做 robots 核验与计划打印，零**数据**请求（robots 仍发 1 次真实请求，须记账）",
    )
    return parser


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv[1:])
    user_agent = build_user_agent(None)
    urls = args.url or [f"https://{args.mirror}{DEFAULT_PATH}"]

    problem = _validate_politeness(args.delay, urls)
    if problem is not None:
        print(f"error: {problem}", file=sys.stderr)
        return 2

    # 条件 (a)：真实拉取前重试 robots 一次；可判读则以其为准。
    verdict = check_robots(args.mirror, urlparse(urls[0]).path or DEFAULT_PATH, user_agent)
    print(f"robots: {verdict.detail}")
    if verdict.readable and not verdict.allowed:
        print(
            "error: 目标路径被 robots Disallow —— 停手（裁决条件 a：可判读则以 robots 为准）",
            file=sys.stderr,
        )
        return 3
    if not verdict.readable:
        print(
            "robots 不可判读 → 按 fable 2026-07-27 裁决执行，"
            f"限 ≤{MAX_REQUESTS} 请求 / 间隔 ≥{args.delay}s / 诚实 UA（条件 b）"
        )

    root = resolve_home(args.home) / "state" / "repec"
    print(f"snapshot root: {root}")
    print(f"plan: {len(urls)} 请求，间隔 {args.delay}s，UA={user_agent}")
    for url in urls:
        print(f"  - {url}")
    if args.dry_run:
        print("dry-run：未发出任何**数据**请求（上方 robots 核验已消耗 1 次，记得记账）。")
        return 0

    root.mkdir(parents=True, exist_ok=True)
    try:
        files = fetch_files(urls, user_agent=user_agent, delay=args.delay, root=root)
    except ChannelRetired as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 4

    manifest_path = write_manifest(root, mirror=args.mirror, urls=urls, files=files)
    print(f"manifest: {manifest_path}")
    print(
        "记账提醒：本次实际请求数 = "
        f"{len(urls) + 1}（含 1 次 robots）；请跑 "
        "`uv run python scripts/budget_ledger.py record --row T8-bulk ...` 入账。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
