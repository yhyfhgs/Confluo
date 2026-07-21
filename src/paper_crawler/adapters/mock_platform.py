"""mock_platform —— Phase 1 的假 adapter（T1 落骨架，T6 实现方法体）。

确定性、程序内生成语料，零网络。所有"随机"成分（标题里的形容词/名词）由
`quirks.seed` 派生的 `random.Random` 采样，保证同 seed 同输出——且与调用顺序无关：
每一期（issue）用 `_issue_seed()` 独立派生自己的种子，不共享一个跨期递进的
生成器状态，所以无论先枚举哪一期，各期的输出都固定不变。

`fetch_asset` 的签名冻结于接口冻结件 §2.3，**不含 venue 参数**——但两个故障注入
quirk（`fail_fetch`、`fetch_delay_ms`）定义在 `VenueSpec.quirks` 上，只有
`resolve_assets`（有 venue 参数）能读到。解法：`resolve_assets` 把这两个 quirk
的效应"编译"进它产出的 `AssetPlan.url` 查询串（`?fail=<ErrorClass>`、
`&delay_ms=<int>`），`fetch_asset` 只需解析自己收到的 URL 就能复现故障注入，不
依赖 adapter 实例的内存状态。这不只是绕过签名限制的权宜之计，也是正确性要求：
resolve 与 fetch 是两个流水线阶段，AssetPlan 中间会持久化到 DB（真实 pipeline
里如此），可能跨进程重启后才执行 fetch（kill-9 续爬场景，AC-1.3/AC-1.5）——如果
故障注入的判定依赖 adapter 对象的内存缓存，重启后新建的 adapter 实例会丢失这份
缓存，注入语义就会跑偏。"quirks 恒定无状态"这条规格用 URL 编码的方式天然满足。

默认（未触发任何故障 quirk）路径下，产出的 URL 严格等于规格文本
`f"https://mock.local/pdf/{doi}"`，不带任何 query string。
"""

import hashlib
import random
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.types import (
    AssetKind,
    AssetPlan,
    AuthLevel,
    Capability,
    FetchIO,
    FetchResult,
    IssueRef,
    PaperStub,
    RatePolicy,
    SessionHandle,
    VenueSpec,
)

_DOI_PREFIX = "10.9999"

# 词表纯粹为了让 mock 标题看起来像论文标题；内容无实际含义，只需在给定 seed 下稳定。
_ADJECTIVES: tuple[str, ...] = (
    "Robust",
    "Scalable",
    "Adaptive",
    "Efficient",
    "Novel",
    "Resilient",
    "Sparse",
    "Bayesian",
    "Distributed",
    "Latent",
)
_NOUNS: tuple[str, ...] = (
    "Networks",
    "Estimators",
    "Equilibria",
    "Embeddings",
    "Frontiers",
    "Heuristics",
    "Manifolds",
    "Signals",
    "Pipelines",
    "Ensembles",
)
_AUTHORS: tuple[str, ...] = (
    "Ada Lovelace",
    "Alan Turing",
    "Grace Hopper",
    "Claude Shannon",
    "Barbara Liskov",
    "Donald Knuth",
)


@dataclass(frozen=True)
class _Quirks:
    """`VenueSpec.quirks` 的已解析视图；全部字段有默认值（规格要求"全部有默认值"）。"""

    volumes: int = 3
    issues_per_volume: int = 2
    papers_per_issue: int = 5
    seed: int = 42
    fail_fetch: Mapping[str, object] | None = None
    fail_enumerate: Mapping[str, object] | None = None
    fetch_delay_ms: int = 0


def _quirk_int(raw: Mapping[str, object], key: str, default: int) -> int:
    value = raw.get(key, default)
    if isinstance(value, bool):
        return default  # bool 是 int 子类；quirk 误写成 true/false 时退回默认值。
    if isinstance(value, int | float | str):
        return int(value)
    return default


def _quirk_mapping(raw: Mapping[str, object], key: str) -> Mapping[str, object] | None:
    value = raw.get(key)
    return value if isinstance(value, Mapping) else None


def _read_quirks(venue: VenueSpec) -> _Quirks:
    raw = venue.quirks
    return _Quirks(
        volumes=_quirk_int(raw, "volumes", 3),
        issues_per_volume=_quirk_int(raw, "issues_per_volume", 2),
        papers_per_issue=_quirk_int(raw, "papers_per_issue", 5),
        seed=_quirk_int(raw, "seed", 42),
        fail_fetch=_quirk_mapping(raw, "fail_fetch"),
        fail_enumerate=_quirk_mapping(raw, "fail_enumerate"),
        fetch_delay_ms=_quirk_int(raw, "fetch_delay_ms", 0),
    )


def _issue_seed(seed: int, venue_id: str, volume: str | None, number: str | None) -> int:
    """把 (seed, venue_id, volume, number) 派生成一个稳定的 per-issue 种子。

    用 `hashlib.sha256` 而非内置 `hash()`：内置 `hash()` 受 `PYTHONHASHSEED`
    影响、跨进程不稳定，会破坏"同 seed 同输出"的确定性契约。
    """
    digest = hashlib.sha256(f"{seed}:{venue_id}:{volume}:{number}".encode()).hexdigest()
    return int(digest[:16], 16)


def _authors_for_index(index: int) -> tuple[str, str]:
    """固定作者表按 index 轮转取 2 人（非随机——与 adj/noun 的抽样来源分开）。"""
    first = _AUTHORS[index % len(_AUTHORS)]
    second = _AUTHORS[(index + 1) % len(_AUTHORS)]
    return (first, second)


def _paper_doi(paper: PaperStub) -> str:
    for scheme, value in paper.identifiers:
        if scheme == "doi":
            return value
    raise CrawlerError(ErrorClass.CONFIG, "mock paper is missing a doi identifier")


def _doi_paper_index(doi: str, venue_id: str) -> int:
    """从 `10.9999/{venue_id}.{v}.{n}.{i}` 形式的 doi 中取回 `i`（期内 0-based 序号）。"""
    prefix = f"{_DOI_PREFIX}/{venue_id}."
    if not doi.startswith(prefix):
        raise CrawlerError(ErrorClass.PARSE, f"unrecognized mock doi: {doi}")
    _, _, index_part = doi.removeprefix(prefix).rpartition(".")
    try:
        return int(index_part)
    except ValueError as exc:
        # 畸形尾段（非数字）是解析失败，不能让裸 ValueError 穿透 pipeline 的
        # CrawlerError 错误路由（design/05 §4：任何异常路径都须映射到 ErrorClass）。
        raise CrawlerError(
            ErrorClass.PARSE, f"malformed mock doi index segment {index_part!r} in {doi}"
        ) from exc


def _as_index_set(value: object) -> set[int]:
    if not isinstance(value, list | tuple):
        return set()
    return {item for item in value if isinstance(item, int) and not isinstance(item, bool)}


def _chunked(data: bytes, parts: int = 3) -> list[bytes]:
    """把 payload 切成恰好 `parts` 块（用于练习 fetch 的流式写入路径）。"""
    size = len(data)
    step = max(1, size // parts)
    boundaries = [step * i for i in range(parts)] + [size]
    return [data[boundaries[i] : boundaries[i + 1]] for i in range(parts)]


class MockPlatformAdapter(AdapterBase):
    """本地确定性 mock；驱动 Phase 1 全 pipeline（AC-1.x）。"""

    adapter_id = "mock_platform"
    family: AdapterFamily = "open_access"
    capabilities = (
        Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    default_rate = RatePolicy(600, burst=10, source_note="本地 mock，无真实站点约束")
    auth_requirement = AuthLevel.NONE
    domains: tuple[str, ...] = ("mock.local",)

    def discover_timeline(self, venue: VenueSpec, since: str | None = None) -> Iterable[IssueRef]:
        """生成 venue 的全量 timeline（`volumes` x `issues_per_volume` 期，确定性）。

        `since` 增量发现参数 Phase 1 版本忽略：mock 语料没有"新增期"的概念，无论
        `since` 取何值都返回完整 timeline；真实增量发现语义留给 Phase 2+ 的真实
        adapter 实现。
        """
        quirks = _read_quirks(venue)
        for v in range(1, quirks.volumes + 1):
            year = 2023 + v  # 卷 "1"/"2"/"3" → year 2024/2025/2026
            for n in range(1, quirks.issues_per_volume + 1):
                yield IssueRef(
                    venue_id=venue.id,
                    volume=str(v),
                    number=str(n),
                    year=year,
                    label=None,
                    paper_count_claimed=quirks.papers_per_issue,
                )

    def enumerate_issue(self, venue: VenueSpec, issue: IssueRef) -> Iterable[PaperStub]:
        """生成一期内的 `papers_per_issue` 篇论文（标题/DOI/作者均确定性派生）。

        `fail_enumerate` quirk 命中时抛 `CrawlerError(PARSE)`，只对配置的
        `(volume, number)` 生效——其余期不受影响。
        """
        quirks = _read_quirks(venue)
        fail = quirks.fail_enumerate
        if fail is not None:
            target_volume = str(fail.get("volume"))
            target_number = str(fail.get("number"))
            if issue.volume == target_volume and issue.number == target_number:
                raise CrawlerError(
                    ErrorClass.PARSE,
                    f"mock enumerate fault injection for {venue.id} v{issue.volume}n{issue.number}",
                )

        rng = random.Random(_issue_seed(quirks.seed, venue.id, issue.volume, issue.number))
        for i in range(quirks.papers_per_issue):
            adjective = rng.choice(_ADJECTIVES)
            noun = rng.choice(_NOUNS)
            doi = f"{_DOI_PREFIX}/{venue.id}.{issue.volume}.{issue.number}.{i}"
            yield PaperStub(
                title=f"Mock Paper {issue.volume}.{issue.number}.{i}: {adjective} {noun}",
                identifiers=(("doi", doi),),
                year=issue.year,
                authors=_authors_for_index(i),
            )

    def resolve_assets(
        self, venue: VenueSpec, paper: PaperStub, session: SessionHandle | None = None
    ) -> list[AssetPlan]:
        """产出单个 PDF `AssetPlan`。

        `fail_fetch`/`fetch_delay_ms` 的效应编码进 URL 查询串（见模块 docstring：
        `fetch_asset` 无 venue 参数，必须只凭 URL 就能复现故障注入）。未触发任何
        quirk 时 URL 严格等于规格文本 `https://mock.local/pdf/{doi}`。
        """
        quirks = _read_quirks(venue)
        doi = _paper_doi(paper)
        index = _doi_paper_index(doi, venue.id)

        query_parts: list[str] = []
        if quirks.fail_fetch is not None:
            failing_indexes = _as_index_set(quirks.fail_fetch.get("paper_indexes"))
            if index in failing_indexes:
                error_class = str(quirks.fail_fetch.get("error_class", "transient"))
                query_parts.append(f"fail={error_class}")
        if quirks.fetch_delay_ms > 0:
            query_parts.append(f"delay_ms={quirks.fetch_delay_ms}")

        url = f"https://mock.local/pdf/{doi}"
        if query_parts:
            url = f"{url}?{'&'.join(query_parts)}"

        return [
            AssetPlan(
                kind=AssetKind.PDF,
                url=url,
                expected_type="application/pdf",
                auth_needed=AuthLevel.NONE,
            )
        ]

    def fetch_asset(
        self, plan: AssetPlan, io: FetchIO, session: SessionHandle | None = None
    ) -> FetchResult:
        """把确定性字节流经 `io.write_stream` 写出；fail/delay 效应从 URL query 解析。

        故障：`CrawlerError(ErrorClass(...))`（不返回 `FetchResult(ok=False)`——
        由 pipeline 统一捕获分类，design/05 §4 的错误路由模型）。
        """
        parsed = urlsplit(plan.url)
        params = parse_qs(parsed.query)

        delay_ms = int(params.get("delay_ms", ["0"])[0])
        if delay_ms > 0:
            time.sleep(delay_ms / 1000)

        fail_values = params.get("fail")
        if fail_values:
            error_class = fail_values[0]
            try:
                resolved_class = ErrorClass(error_class)
            except ValueError as exc:
                # 非法 error_class 编码进 url 是配置层问题（畸形 quirk），转 CONFIG；
                # 裸 ValueError 不属 ErrorClass 语义、会绕过 pipeline 的错误路由。
                raise CrawlerError(
                    ErrorClass.CONFIG, f"unknown fail error_class in mock url: {error_class!r}"
                ) from exc
            raise CrawlerError(resolved_class, f"mock fetch fault injection: {error_class}")

        doi = parsed.path.removeprefix("/pdf/")
        payload = b"%PDF-1.4\n% " + doi.encode() + b"\n" + b"0" * 2048 + b"\n%%EOF\n"
        bytes_written, sha256_hex = io.write_stream(_chunked(payload))
        return FetchResult(ok=True, bytes_written=bytes_written, sha256=sha256_hex)
