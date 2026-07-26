"""RePEc `enrich_batch` 主体（design/adapters/aggregators.md §5.7；D-035 决策 3/4）。

**能力面**：`capabilities = Capability(0)`（空集）——不进 `SourceAdapter` 五方法冻结协议、
不参与 `crawler pull` 六阶段（同 openalex/s2）。经 duck-typed `enrich_batch`
（`adapter.EnrichmentSource` 协议）由 `crawler enrich --source repec` 驱动。

**零网络（结构事实，非自律）**：本模块**不导入 `HttpClient`、不实现 `HttpClientConsumer`**，
`domains = ()`（结构性宣告无网络面）。数据来自 `<config-home>/state/repec/` 的 bulk ReDIF
快照——取快照的网络面在 `scripts/repec_snapshot.py`（`src/` 之外，不占门禁覆盖）。该性质由
socket 猴补专测**正向锁定**（`tests/unit/test_repec_adapter.py`），而 `domains == ()` 由
`test_adapter_loading.py::_ZERO_NETWORK_ADAPTERS` 双向断言锁定——repec 日后若偷偷长出域名
同样打红。

**名义 `RatePolicy`**（`default_rate`）：`test_adapter_loading.py` 要求全体 adapter 的
`source_note` 非空且 `requests_per_minute > 0`，而本源没有任何限速语义可言。故 `source_note`
**如实注明"零网络源、限速闸不生效、本值为占位名义"**——`source_note` 的既有契约是"默认值
必须注明出处"，给一个零网络源伪造站点限速文档等于往出处字段里写假事实（D-035 明文否决，
同否决"给 repec 挂一个从不请求的域名"）。

## 失效语义（D-035 决策 3；对 enrich-eval §2.7 DoD② 字面的有意收窄，已入档）

- **快照缺失** → `CrawlerError(CONFIG, …)` → 经 `cli._run_enrich_source` 既有 per-source
  捕获记"提前终止"，**不崩其它 source、不改整体退出码**（与 s2 缺 key / openalex 预算熔断
  完全同构）。
- **快照过期**（`fetched_at` 早于 `_STALE_AFTER_DAYS=30` 天）→ **响亮 WARNING + 摘要行注记，
  继续运行**。理由：`Classification-JEL`/`Publication-Status` 是准静态字段，让一个 31 天未
  刷新的快照使整条通道不可用，代价与收益不匹配；"响亮、不静默"的实质要求全额保留。
  **警告必须可操作**（与缺失分支指引对称）：文案同时携 ①`fetched_at` 与**实际过期天数**、
  ②**刷新命令一行提示**——只喊"过期了"而不给天数与修法，等同于把响亮做成噪声。
- 阈值取**模块常量、不开 config 槽**：过期只影响一条警告文案、非行为开关（YAGNI）。

## healthcheck（与 openalex/s2 相反的性质）

快照缺失 → `NotImplementedError` → `crawler canary` 既有 SKIP 分支（**零 canary 改动**，
复用 openalex/s2 未配置 key 的先例）；快照在 → 健康并带 `record_count` + `fetched_at`。
openalex 当初收紧 healthcheck 是**怕 canary 高频调用悄悄消耗 credit**；本源零网络零预算，
高频探测无成本，故不设额外门控。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.adapters.repec import parse
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.obslog import log_event
from paper_crawler.types import AuthLevel, Capability, HealthReport, PaperStub, RatePolicy

# 快照过期阈值（模块常量，不开 config 槽——见模块 docstring）。
_STALE_AFTER_DAYS = 30
# 刷新命令一行提示（缺失分支与过期分支**同源同格式**，D-035 决策 3 的对称性要求）。
_REFRESH_HINT = "uv run python scripts/repec_snapshot.py --home <config-home>"
_MANIFEST_NAME = "manifest.json"


@dataclass(frozen=True)
class SnapshotStats:
    """一次 `crawler enrich --source repec` 运行的未命中三分计数（D-035 决策 4）。

    三类各自计数、**不合并为一个"没查到"**：`unaddressable` 是结构性事实（该 DOI 本就不在
    RePEc 可寻址集合内，非缺陷）、`missing_handle` 指示快照陈旧或 series 未覆盖（**可行动**：
    刷新快照）、`no_jel` 指示该条目本身无增值（探针实测 1989 年代条目即此类，**不可行动**）。
    把三者混作一个数字会让"该刷快照了"与"这批论文本来就没 JEL"无法区分（审计 S1 原则）。
    """

    matched: int = 0
    unaddressable: int = 0
    missing_handle: int = 0
    no_jel: int = 0


class RepecAdapter(AdapterBase):
    """RePEc bulk 快照本地 join adapter（`aggregator` family；capabilities 空集，enrich-only）。"""

    adapter_id = "repec"
    family: AdapterFamily = "aggregator"
    capabilities = Capability(0)
    default_rate = RatePolicy(
        requests_per_minute=60.0,
        burst=1,
        source_note=(
            "零网络源（bulk ReDIF 快照本地 join，enrich_batch 不发任何请求）——限速闸对本源"
            "不生效，本值为**占位名义**，非任何站点限速文档的转录；唯一网络面在 "
            "scripts/repec_snapshot.py（src 之外）。D-035 决策 1 / "
            "docs/design/adapters/aggregators.md §5.7"
        ),
    )
    auth_requirement = AuthLevel.NONE
    # 空元组＝结构性宣告"本源无网络面"（D-035 决策 1 否决"挂一个从不请求的域名"）。
    # 装配侧 `cli._prepare_enrich_source` 对空 domains 跳过限速登记，与
    # `cli._register_rate_domains` 的既有"空 domains 跳过"语义同构。
    domains: tuple[str, ...] = ()

    def __init__(self, snapshot_root: Path | None = None) -> None:
        self._snapshot_root = snapshot_root
        self._records: dict[str, parse.RedifRecord] | None = None
        self._manifest: parse.SnapshotManifest | None = None
        self._stale_note: str | None = None
        self._stats = SnapshotStats()

    def configure_snapshot(self, root: Path) -> None:
        """注入快照根目录（CLI 装配期传 `<config-home>/state/repec`，经 `config.resolve_home()`
        ——**D-032 红线**：禁 `Path.home()` 硬编码兜底，本模块自身不认识 "config-home" 概念，
        只接受调用方传入的 `Path`，同 `openalex.budget` 的既有口径）。

        改根即弃缓存——测试与运维可在同进程内切换快照，不会读到上一份的残留。
        """
        self._snapshot_root = root
        self._records = None
        self._manifest = None
        self._stale_note = None

    # -- 快照加载（惰性、进程内缓存；不建派生索引，D-035 决策 3）----------------------------

    def _load_snapshot(self) -> dict[str, parse.RedifRecord]:
        """惰性全量解析快照入进程内 dict（handle → 记录）；缺失/损坏 → `CrawlerError(CONFIG)`。

        3.6 万条量级，一次全量解析后逐页 join 的开销可忽略 ⇒ **不建 `index.sqlite`、不入主库表**
        （YAGNI，且避免与 schema 迁移链纠缠）。文件名不预设：按 `manifest.files[].name` 遍历。
        """
        if self._records is not None:
            return self._records

        root = self._snapshot_root
        if root is None or not (root / _MANIFEST_NAME).is_file():
            where = str(root) if root is not None else "<未配置>"
            raise CrawlerError(
                ErrorClass.CONFIG,
                f"repec 快照缺失（{where}/{_MANIFEST_NAME} 不存在）；"
                f"先跑 `{_REFRESH_HINT}` 取快照后重试",
            )
        manifest = parse.parse_manifest((root / _MANIFEST_NAME).read_bytes())

        records: dict[str, parse.RedifRecord] = {}
        for entry in manifest.files:
            path = root / entry.name
            if not path.is_file():
                raise CrawlerError(
                    ErrorClass.CONFIG,
                    f"repec 快照损坏：manifest 记载的 {entry.name!r} 不存在于 {root}；"
                    f"重跑 `{_REFRESH_HINT}` 重建",
                )
            for record in parse.parse_redif(path.read_bytes()):
                records.setdefault(record.handle, record)

        self._manifest = manifest
        self._records = records
        self._warn_if_stale(manifest)
        return records

    def _warn_if_stale(self, manifest: parse.SnapshotManifest) -> None:
        """过期 → 响亮 WARNING（带天数 + 刷新命令）并记 `_stale_note` 供摘要行注记；否则清空。

        只在**加载时**判一次（而非每页），避免把一条运维提示刷成噪声。
        """
        days = parse.staleness_days(manifest.fetched_at, now=datetime.now(UTC))
        if days is None or days <= _STALE_AFTER_DAYS:
            self._stale_note = None
            return
        note = (
            f"快照已 {days} 天未刷新（fetched_at={manifest.fetched_at}，"
            f"阈值 {_STALE_AFTER_DAYS} 天）；刷新：`{_REFRESH_HINT}`"
        )
        self._stale_note = note
        log_event("WARNING", f"repec {note}", stage="enrich", stale_days=days)

    # -- enrich_batch（duck-typed EnrichmentSource；**零网络**）-------------------------------

    def enrich_batch(self, dois: Sequence[str]) -> list[PaperStub]:
        """快照本地 join：`10.3386/w|t{n}` → handle → 记录 → `PaperStub`。**全程零网络**。

        对固定快照是 `(dois, snapshot)` 的**纯函数**（可重放、可用于回归锁定）——与在线源
        "受上游变动影响"的幂等性相反。去重保序、跳过空串（同 s2/openalex 既有口径）。

        未命中不静默丢弃，按 `parse.MissKind` 三分累加到 `stats`（摘要行可见）：
        (a) 非 `10.3386` 前缀 → `unaddressable`；(b) 前缀符但快照无该 handle →
        `missing_handle`；(c) 命中但无 JEL → `no_jel`（**仍产 stub**——title/authors/year/
        abstract 照常回注，靠 `SOURCE_PRIORITY` 最低位天然只补空）。
        """
        records = self._load_snapshot()
        unique = [doi for doi in dict.fromkeys(dois) if doi]
        stubs: list[PaperStub] = []
        matched = unaddressable = missing_handle = no_jel = 0

        for doi in unique:
            handle = parse.handle_from_doi(doi)
            if handle is None:
                unaddressable += 1
                continue
            record = records.get(handle)
            if record is None:
                missing_handle += 1
                continue
            matched += 1
            if not record.jel:
                no_jel += 1
            stubs.append(parse.stub_from_record(record, doi))

        self._stats = SnapshotStats(
            matched=self._stats.matched + matched,
            unaddressable=self._stats.unaddressable + unaddressable,
            missing_handle=self._stats.missing_handle + missing_handle,
            no_jel=self._stats.no_jel + no_jel,
        )
        if unaddressable or missing_handle:
            log_event(
                "DEBUG",
                "repec enrich_batch misses",
                stage="enrich",
                unaddressable=unaddressable,
                missing_handle=missing_handle,
                no_jel=no_jel,
            )
        return stubs

    # `discover_timeline`/`enumerate_issue`/`resolve_assets`/`fetch_asset` 未声明能力
    # （capabilities 空集）——不覆写，沿用 `AdapterBase` 默认 `CapabilityNotSupported`。

    # -- 观测面（摘要行消费）-------------------------------------------------------------------

    @property
    def stats(self) -> SnapshotStats:
        """本进程迄今累计的未命中三分计数（`crawler enrich` 摘要行读它渲染注记）。"""
        return self._stats

    def summary_note(self) -> str:
        """摘要行注记：新鲜度（`fetched_at`）+ 三分计数 + 过期警告（若过期）。

        `fetched_at` **须在摘要行可见**（D-035 决策 4 的"新鲜度"面契约）——在线源的新鲜度是
        "实时"无须说明，本源的数据有多新完全取决于上次取快照的时间，不说等于让用户对着
        一份可能半年前的数据做判断。
        """
        stats = self._stats
        parts = [
            f"快照 fetched_at={self._manifest.fetched_at if self._manifest else '<未加载>'}",
            (
                f"命中 {stats.matched}"
                f"（无 JEL {stats.no_jel}）"
                f" | 不可寻址 {stats.unaddressable} | 覆盖缺口 {stats.missing_handle}"
            ),
        ]
        if self._stale_note:
            parts.append(f"⚠ {self._stale_note}")
        return " | ".join(parts)

    # -- healthcheck（模块 docstring）-----------------------------------------------------------

    def healthcheck(self, session: object = None) -> HealthReport:
        """快照缺失 → `NotImplementedError`（→canary SKIP）；快照在 → 健康并带记录数/新鲜度。

        零网络零预算 ⇒ canary 高频调用无成本（与 openalex/s2 的 key 门控性质相反，见模块
        docstring）。快照**损坏**（manifest 畸形/文件缺失）不走 SKIP 而是如实报不健康——那是
        真实故障，不是"未配置"。
        """
        del session
        root = self._snapshot_root
        if root is None or not (root / _MANIFEST_NAME).is_file():
            raise NotImplementedError("repec 快照未落盘")
        try:
            records = self._load_snapshot()
        except CrawlerError as exc:
            return HealthReport(healthy=False, detail=f"repec 快照损坏: {exc}")
        manifest = self._manifest
        if manifest is None:  # pragma: no cover - _load_snapshot 成功即已置位，防御性分支
            return HealthReport(healthy=False, detail="repec 快照 manifest 未加载")
        detail = (
            f"snapshot ok — record_count={len(records)}"
            f"（manifest 记 {manifest.record_count}）, fetched_at={manifest.fetched_at}"
        )
        if self._stale_note:
            detail += f"; ⚠ {self._stale_note}"
        return HealthReport(healthy=True, detail=detail)


__all__ = ["RepecAdapter", "SnapshotStats"]
