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


__all__ = ["DEFAULT_MOCK_QUIRKS", "FakeFetchIO", "make_mock_venue"]
