"""核心数据类型、`VenueSpec` 与工具函数（接口冻结件 §2.2）。

约定（Global Constraints §7）：时间戳一律 UTC ISO8601 字符串（`utcnow_iso`）；
主键一律 ULID 文本（`new_ulid`）。所有 dataclass 均 `frozen`——需 hashable，
故弹性字段用 tuple-of-tuples 而非 dict。
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Flag, StrEnum, auto
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field
from ulid import ULID

from paper_crawler.errors import ErrorClass

# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------


class AuthLevel(StrEnum):
    """平台/venue 的最低认证等级（升序：none < free_account < subscription < institutional）。"""

    NONE = "none"
    FREE_ACCOUNT = "free_account"
    SUBSCRIPTION = "subscription"
    INSTITUTIONAL = "institutional"


class Capability(Flag):
    """adapter 声明的能力位（design/02 §3）。"""

    DISCOVER = auto()
    ENUMERATE = auto()
    RESOLVE = auto()
    FETCH = auto()
    SEARCH = auto()


class AssetKind(StrEnum):
    PDF = "pdf"
    SI = "si"
    HTML = "html"
    BIBTEX = "bibtex"
    SOURCE = "source"


class UrlStrategy(StrEnum):
    DIRECT = "direct"
    RENDER_PAGE = "render_page"
    API_CALL = "api_call"


# ---------------------------------------------------------------------------
# 值对象（frozen dataclass）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RatePolicy:
    """adapter 的默认限速；`source_note` 必须注明出处（design/02）。"""

    requests_per_minute: float
    burst: int = 1
    source_note: str = ""  # design/02：默认值必须注明出处


@dataclass(frozen=True)
class IssueRef:
    """一期/一届的引用（时间轴条目）。"""

    venue_id: str
    volume: str | None = None
    number: str | None = None
    year: int | None = None
    label: str | None = None
    pub_date: str | None = None
    paper_count_claimed: int | None = None


@dataclass(frozen=True)
class PaperStub:
    """论文的最小元数据锚点；`identifiers` 至少 1 个 (scheme, value)。"""

    title: str
    identifiers: tuple[tuple[str, str], ...]  # ((scheme, value), ...) 至少 1 个
    year: int | None = None
    pub_date: str | None = None
    abstract: str | None = None
    authors: tuple[str, ...] = ()
    meta: tuple[tuple[str, str], ...] = ()  # 弹性字段（frozen 需 hashable）


@dataclass(frozen=True)
class AssetPlan:
    """一个可下载资产的定位与获取策略。"""

    kind: AssetKind
    url: str
    expected_type: str = "application/pdf"
    url_strategy: UrlStrategy = UrlStrategy.DIRECT
    auth_needed: AuthLevel = AuthLevel.NONE
    version: str | None = None


@dataclass(frozen=True)
class FetchResult:
    """adapter 下载单个资产的结果。"""

    ok: bool
    bytes_written: int = 0
    sha256: str | None = None
    error_class: ErrorClass | None = None
    detail: str = ""


@dataclass(frozen=True)
class HealthReport:
    """healthcheck 的结果。"""

    healthy: bool
    detail: str = ""


# Phase 4 具体化（design/07）；Phase 1 恒 None。
SessionHandle = Any


class FetchIO(Protocol):
    """pipeline 提供实现；adapter 只写流（校验/rename 归 pipeline）。"""

    def write_stream(self, chunks: Iterable[bytes]) -> tuple[int, str]:
        """写入 *.part 临时文件，返回 (bytes_written, sha256_hex)。"""
        ...


# ---------------------------------------------------------------------------
# VenueSpec（Pydantic v2；字段与 design/02 §2.2 YAML schema v1 一一对应）
# ---------------------------------------------------------------------------


class VenueNames(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full: str
    aliases: list[str] = []


class VenueAuth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: AuthLevel = AuthLevel.NONE
    provider_hint: str | None = None


class VenueRateLimit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requests_per_minute: float | None = None


class VenueSpec(BaseModel):
    """venue 声明（YAML schema v1）。未知字段拒绝（extra="forbid"）。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    kind: Literal["journal", "conference", "preprint_channel"]
    names: VenueNames
    field: list[Literal["finance", "econ", "cs_ai", "or_ms"]]
    tier: Literal["T1", "T2", "T3"] | None = None
    # issn: list[str] / dblp_key / openreview_id / openalex_source
    identifiers: dict[str, object] = {}
    # D-005 分离语义（plan §2-2，crossref 是第一消费者，纯附加变更）：现放宽为可选。
    # None（默认）= 沿用 adapter 自身——即元数据由 fulltext_source 的平台 adapter 兼任
    # （既有全部 venue 显式声明 metadata_source==fulltext_source 的旧式同源写法不受影响，
    # 零改动零回归）。声明为聚合源 id（crossref/dblp）即"元数据主干"分离到该 aggregator。
    # registry 校验：声明值须已注册；且当 metadata_source != fulltext_source（真分离）时其
    # family 须为 aggregator（见 registry._lint_adapter_refs）。
    metadata_source: str | None = None
    fulltext_source: str
    auth: VenueAuth = VenueAuth()
    rate_limit: VenueRateLimit = VenueRateLimit()
    quirks: dict[str, object] = {}
    status: Literal["active", "dormant", "dead"] = "active"
    notes: str = ""


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def utcnow_iso() -> str:
    """当前 UTC 时间的 ISO8601 字符串（带 +00:00 偏移）。"""
    return datetime.now(UTC).isoformat()


def new_ulid() -> str:
    """生成一个新的 ULID 文本（26 字符，Crockford base32；主键用）。"""
    return str(ULID())


__all__ = [
    "AssetKind",
    "AssetPlan",
    "AuthLevel",
    "Capability",
    "FetchIO",
    "FetchResult",
    "HealthReport",
    "IssueRef",
    "PaperStub",
    "RatePolicy",
    "SessionHandle",
    "UrlStrategy",
    "VenueAuth",
    "VenueNames",
    "VenueRateLimit",
    "VenueSpec",
    "new_ulid",
    "utcnow_iso",
]
