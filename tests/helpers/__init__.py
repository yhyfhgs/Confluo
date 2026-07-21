"""跨测试树共享的小工具：contract venue 工厂 + 假 `FetchIO`。

包名说明：`tests/` 目录本身没有 `__init__.py`（T1 起的既有布局——`tests/unit`、
`tests/contract`、`tests/integration` 各自独立成包，靠 pytest 的 rootdir 插入
机制把 `tests/` 加进 `sys.path`）。因此本包以顶层模块名导入：``from helpers import
...``，而不是 ``from tests.helpers import ...``（后者会因为 `tests` 不是包而
`ImportError`——已用探针测试验证）。
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from paper_crawler.types import VenueSpec

DEFAULT_MOCK_QUIRKS: dict[str, object] = {
    "volumes": 3,
    "issues_per_volume": 2,
    "papers_per_issue": 5,
    "seed": 42,
}

# arxiv 契约/集成测试用的 preprint_channel venue（不依赖 venues/ 目录——仓库不 ship
# arxiv YAML，test_venue_yaml_lint 钉死 shipped 集合为 {mock_journal, jfe, iclr, icml}）。
# inception 取近期月份保证 discover 非空；arxiv_category 决定 OAI set(=cs) 与子分类过滤。
DEFAULT_ARXIV_QUIRKS: dict[str, object] = {
    "inception": "2024-01",
    "arxiv_set": "cs",
    "arxiv_category": "cs.LG",
}

# openreview 契约/集成测试用的 conference venue（id 必须为 'iclr'——adapter 内置届表按
# venue.id 键取，见 adapters/openreview/venues._BUILTIN_TABLES）。auth free_account 匹配
# adapter auth_requirement（否则 lint 不过）。overrides 通道默认空。
DEFAULT_OPENREVIEW_QUIRKS: dict[str, object] = {"openreview_group_overrides": {}}
# pmlr 契约/集成测试用的 conference venue：quirks 自成一体、独立于 venues/cs_ai/icml.yaml
# 的真实内容（同 arxiv 先例的解耦考量——adapter 逻辑测试不应受真实 venue 数据编辑影响；
# 真实 shipped YAML 的自身正确性由 test_venue_yaml_lint.py 与 D-019 锚点一致性测试覆盖）。
# 只保留两个年份（一自托管旧卷 2023/v202、一 GitHub 托管新卷 2024/v235）即可覆盖双域路径。
DEFAULT_PMLR_QUIRKS: dict[str, object] = {
    "volume_map": {2023: 202, 2024: 235},
}


def make_mock_venue(**quirks_overrides: object) -> VenueSpec:
    """构造 mock_platform 契约测试用的 venue（不依赖 `venues/` 目录文件）。

    默认 quirks 与 phase1-implementation-plan Task 3 中 `venues/_mock/mock-journal.yaml`
    的取值一致（volumes=3, issues_per_volume=2, papers_per_issue=5, seed=42），
    保证本任务的 golden 快照与 T3 落地后的真实 venue YAML 语义一致。
    """
    quirks: dict[str, object] = dict(DEFAULT_MOCK_QUIRKS)
    quirks.update(quirks_overrides)
    return VenueSpec(
        id="mock_journal",
        kind="journal",
        names={"full": "Mock Journal", "aliases": ["MJ"]},
        field=["cs_ai"],
        identifiers={"issn": ["0000-0000"]},
        metadata_source="mock_platform",
        fulltext_source="mock_platform",
        quirks=quirks,
    )


def make_arxiv_venue(**quirks_overrides: object) -> VenueSpec:
    """构造 arxiv 契约/集成测试用的 `preprint_channel` venue（不依赖 `venues/` 目录文件）。

    默认 quirks：`inception='2024-01'`（近期，保证 discover 非空且窗口为过去完整月）、
    `arxiv_set='cs'`、`arxiv_category='cs.LG'`（决定 OAI set 与子分类客户端过滤）。
    """
    quirks: dict[str, object] = dict(DEFAULT_ARXIV_QUIRKS)
    quirks.update(quirks_overrides)
    return VenueSpec(
        id="arxiv_cs_lg",
        kind="preprint_channel",
        names={"full": "arXiv cs.LG (Machine Learning)", "aliases": ["arxiv-cs-lg"]},
        field=["cs_ai"],
        metadata_source="arxiv",
        fulltext_source="arxiv",
        quirks=quirks,
    )


def make_openreview_venue(**quirks_overrides: object) -> VenueSpec:
    """构造 openreview 契约/集成测试用的 `conference` venue（不依赖 `venues/` 目录文件）。

    id='iclr'（adapter 内置 ICLR 届表按 venue.id 键取）；auth=free_account+provider_hint
    （匹配 adapter auth_requirement）。`quirks_overrides` 可注入 `openreview_group_overrides`
    覆盖届表。
    """
    quirks: dict[str, object] = dict(DEFAULT_OPENREVIEW_QUIRKS)
    quirks.update(quirks_overrides)
    return VenueSpec(
        id="iclr",
        kind="conference",
        names={"full": "International Conference on Learning Representations", "aliases": ["ICLR"]},
        field=["cs_ai"],
        identifiers={"dblp_key": "conf/iclr"},
        metadata_source="openreview",
        fulltext_source="openreview",
        auth={"level": "free_account", "provider_hint": "openreview"},
def make_pmlr_venue(**quirks_overrides: object) -> VenueSpec:
    """构造 pmlr 契约/集成测试用的 `conference` venue（不依赖 `venues/` 目录文件）。

    默认 quirks：`volume_map={2023: 202, 2024: 235}`（一自托管旧卷 + 一 GitHub
    托管新卷，覆盖 pmlr.md §3.3 的双域 resolve 路径）。
    """
    quirks: dict[str, object] = dict(DEFAULT_PMLR_QUIRKS)
    quirks.update(quirks_overrides)
    return VenueSpec(
        id="icml",
        kind="conference",
        names={"full": "International Conference on Machine Learning", "aliases": ["ICML"]},
        field=["cs_ai"],
        identifiers={"dblp_key": "conf/icml"},
        metadata_source="pmlr",
        fulltext_source="pmlr",
        quirks=quirks,
    )


class FakeFetchIO:
    """`FetchIO` 协议的测试替身：把 chunks 缓冲进内存并计算 `(bytes_written, sha256)`。

    同时记录收到的 chunk 数，供测试断言 adapter 确实分块写入（而非一次性整块写）。
    """

    def __init__(self) -> None:
        self.data: bytes = b""
        self.chunk_count: int = 0

    def write_stream(self, chunks: Iterable[bytes]) -> tuple[int, str]:
        buf = bytearray()
        for chunk in chunks:
            buf.extend(chunk)
            self.chunk_count += 1
        self.data = bytes(buf)
        return len(self.data), hashlib.sha256(self.data).hexdigest()


__all__ = [
    "DEFAULT_ARXIV_QUIRKS",
    "DEFAULT_MOCK_QUIRKS",
    "DEFAULT_OPENREVIEW_QUIRKS",
    "FakeFetchIO",
    "make_arxiv_venue",
    "make_mock_venue",
    "make_openreview_venue",
    "DEFAULT_PMLR_QUIRKS",
    "FakeFetchIO",
    "make_arxiv_venue",
    "make_mock_venue",
    "make_pmlr_venue",
]
