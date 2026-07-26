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

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, replace
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


def _verify_integrity(entry: parse.SnapshotFile, raw: bytes, root: Path) -> None:
    """校验单个快照文件的 `bytes`/`sha256` 与 manifest 记账一致；不符 → `INTEGRITY`（响亮）。

    **只写不校等于没校**：manifest 落 sha256 的全部意义就是"这份字节还是取回时那份"。截断、
    半程写入、事后手改都只在此处能被发现——而本通道的产出会直接进主库，一份坏快照静默通过
    就是把损坏数据写进 paper 行。故此处是**响亮失败**（区别于解析伪影的"观测+继续"：那是
    上游数据本身的瑕疵，这是本地文件与自己的记账对不上）。
    """
    if len(raw) != entry.bytes:
        raise CrawlerError(
            ErrorClass.INTEGRITY,
            f"repec 快照完整性校验失败：{entry.name!r} 实际 {len(raw)} 字节、manifest 记 "
            f"{entry.bytes} 字节（截断或被改动）；重跑 `{_REFRESH_HINT}` 重取快照",
            detail=f"root={root}",
        )
    digest = hashlib.sha256(raw).hexdigest()
    if digest != entry.sha256:
        raise CrawlerError(
            ErrorClass.INTEGRITY,
            f"repec 快照完整性校验失败：{entry.name!r} sha256 不符"
            f"（实际 {digest[:16]}…、manifest 记 {entry.sha256[:16]}…）；"
            f"重跑 `{_REFRESH_HINT}` 重取快照",
            detail=f"root={root}",
        )


def _verify_record_count(manifest: parse.SnapshotManifest, loaded: int) -> None:
    """校验**唯一 handle 数**与 manifest `record_count` 一致；不符 → `INTEGRITY`（响亮）。

    与 sha256 校验互补、不冗余：sha256 保证**字节**没变，本校验保证**本地解析口径**仍与取
    快照时一致。二者会在不同场景分别报警——解析器改口径后字节不变而记录数变，正是这一条能
    抓到的（且那正是"快照该重取/解析器该复核"的信号，静默通过会让 join 覆盖率悄悄塌掉）。

    **口径＝去重后的可用记录数**，与 `scripts/repec_snapshot.py::write_manifest` 逐字对齐
    （该处按唯一 handle 计数）。两侧口径必须同源：若 manifest 记未去重条数、此处比去重后的
    dict 大小，一份**含重复 handle 的合法快照**会硬失败，且**重取永远修不好**（重取写回同一
    未去重计数）。重复 handle 是预期内现象——`_load_snapshot` 明确按"同 handle 取首条"处置。
    """
    if manifest.record_count and loaded != manifest.record_count:
        raise CrawlerError(
            ErrorClass.INTEGRITY,
            f"repec 快照完整性校验失败：解析出 {loaded} 条记录、manifest 记 "
            f"{manifest.record_count} 条（快照损坏，或本地解析口径已与取快照时不一致）；"
            f"重跑 `{_REFRESH_HINT}` 重取快照",
        )


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
    # **解析伪影，与上面三分严格分离**（P1-1）：handle 语法不合的记录数 + 悬空续行数。
    # 前三者说的是"快照与查询的关系"，这两者说的是"快照文件本身没读懂"——混作一谈会让一段
    # archive 页脚散文伪装成"该刷快照了"，把运维引向错误的动作。
    malformed_records: int = 0
    stray_lines: int = 0


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
        malformed = stray = 0
        for entry in manifest.files:
            path = root / entry.name
            if not path.is_file():
                raise CrawlerError(
                    ErrorClass.CONFIG,
                    f"repec 快照损坏：manifest 记载的 {entry.name!r} 不存在于 {root}；"
                    f"重跑 `{_REFRESH_HINT}` 重建",
                )
            raw = path.read_bytes()
            _verify_integrity(entry, raw, root)
            result = parse.parse_redif_result(raw)
            malformed += len(result.malformed)
            stray += result.stray_lines
            for record in result.records:
                # handle 已经 `canonical_handle` 归一（大小写惯例）⇒ 键与 `handle_from_doi`
                # 的产出同源；`setdefault` 使同 handle 重复块取首条（保守，不让后块挤掉）。
                records.setdefault(record.handle, record)

        _verify_record_count(manifest, len(records))
        self._manifest = manifest
        self._records = records
        self._stats = replace(
            self._stats,
            malformed_records=self._stats.malformed_records + malformed,
            stray_lines=self._stats.stray_lines + stray,
        )
        self._warn_if_parse_artifacts(malformed, stray)
        self._warn_if_stale(manifest)
        return records

    def _warn_if_parse_artifacts(self, malformed: int, stray: int) -> None:
        """解析伪影 → **PARSE 类响亮观测**（P1-1）；与三分计数分离，不静默。

        不抛异常：一份 3.6 万条的快照里几条畸形记录不该让整条通道停摆（同"非法字节 replace"
        的既有取舍）。但**必须响亮**——静默吞掉会让解析伪影伪装成"覆盖缺口"，把运维引向
        "去刷快照"这个治不了本的动作。
        """
        if not (malformed or stray):
            return
        log_event(
            "WARNING",
            f"repec 快照解析伪影：handle 语法不合 {malformed} 条、悬空续行 {stray} 行"
            "（**不计入未命中三分**；典型成因＝记录间散文/archive 页脚）",
            stage="enrich",
            error_class=ErrorClass.PARSE.value,
            malformed_records=malformed,
            stray_lines=stray,
        )

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

        self._stats = replace(
            self._stats,
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
        # 解析伪影**单列**，不混进三分（P1-1）：它指向的动作是"复核快照/解析器"，
        # 而非三分里"覆盖缺口"暗示的"去刷快照"。
        if stats.malformed_records or stats.stray_lines:
            parts.append(
                f"⚠ 解析伪影 handle 不合 {stats.malformed_records} / "
                f"悬空续行 {stats.stray_lines}（不计入上列三分）"
            )
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
