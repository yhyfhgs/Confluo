"""types.py（§2.2）单测：枚举值、frozen 值对象默认与 hashable、VenueSpec 校验、工具函数。"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from paper_crawler.errors import ErrorClass
from paper_crawler.types import (
    AssetKind,
    AssetPlan,
    AuthLevel,
    Capability,
    FetchResult,
    HealthReport,
    IssueRef,
    PaperStub,
    RatePolicy,
    UrlStrategy,
    VenueSpec,
    new_ulid,
    utcnow_iso,
)


def test_auth_level_ordering_values() -> None:
    assert [level.value for level in AuthLevel] == [
        "none",
        "free_account",
        "subscription",
        "institutional",
    ]


def test_asset_kind_and_url_strategy_values() -> None:
    assert {k.value for k in AssetKind} == {"pdf", "si", "html", "bibtex", "source"}
    assert {s.value for s in UrlStrategy} == {"direct", "render_page", "api_call"}


def test_capability_is_flag_and_composes() -> None:
    caps = Capability.DISCOVER | Capability.ENUMERATE
    assert Capability.DISCOVER in caps
    assert Capability.ENUMERATE in caps
    assert Capability.RESOLVE not in caps
    assert len(list(Capability)) == 5


def test_rate_policy_defaults() -> None:
    policy = RatePolicy(60)
    assert policy.requests_per_minute == 60
    assert policy.burst == 1
    assert policy.source_note == ""


def test_asset_plan_defaults() -> None:
    plan = AssetPlan(kind=AssetKind.PDF, url="https://mock.local/pdf/x")
    assert plan.expected_type == "application/pdf"
    assert plan.url_strategy is UrlStrategy.DIRECT
    assert plan.auth_needed is AuthLevel.NONE
    assert plan.version is None


def test_fetch_result_defaults_and_error_class_field() -> None:
    ok = FetchResult(ok=True, bytes_written=2048, sha256="deadbeef")
    assert ok.error_class is None
    bad = FetchResult(ok=False, error_class=ErrorClass.INTEGRITY, detail="bad magic")
    assert bad.error_class is ErrorClass.INTEGRITY


def test_health_report_defaults() -> None:
    assert HealthReport(healthy=True).detail == ""


def test_issue_ref_defaults() -> None:
    ref = IssueRef(venue_id="mock_journal")
    assert ref.volume is None
    assert ref.paper_count_claimed is None


def test_paper_stub_is_frozen_and_hashable() -> None:
    stub = PaperStub(title="T", identifiers=(("doi", "10.9999/x"),))
    # frozen dataclass 需 hashable —— 弹性字段用 tuple 保证可入 set。
    assert hash(stub) == hash(PaperStub(title="T", identifiers=(("doi", "10.9999/x"),)))
    assert {stub}  # 可放入 set
    with pytest.raises(AttributeError):
        stub.title = "other"  # type: ignore[misc]


def test_utcnow_iso_is_timezone_aware_iso8601() -> None:
    text = utcnow_iso()
    parsed = datetime.fromisoformat(text)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0  # type: ignore[union-attr]


def test_new_ulid_is_26_chars_and_unique() -> None:
    a = new_ulid()
    b = new_ulid()
    assert len(a) == 26
    assert a != b


# --- VenueSpec ---------------------------------------------------------------


def test_venue_spec_parses_valid_dict(venue_dict: dict[str, object]) -> None:
    spec = VenueSpec(**venue_dict)
    assert spec.id == "mock_journal"
    assert spec.kind == "journal"
    assert spec.names.full == "Mock Journal"
    assert spec.field == ["cs_ai"]


def test_venue_spec_applies_defaults(venue_dict: dict[str, object]) -> None:
    spec = VenueSpec(**venue_dict)
    assert spec.auth.level is AuthLevel.NONE
    assert spec.status == "active"
    assert spec.tier is None
    assert spec.rate_limit.requests_per_minute is None


def test_venue_spec_rejects_extra_field(venue_dict: dict[str, object]) -> None:
    venue_dict["bogus"] = 1
    with pytest.raises(ValidationError):
        VenueSpec(**venue_dict)


def test_venue_spec_rejects_unknown_field_enum(venue_dict: dict[str, object]) -> None:
    venue_dict["field"] = ["astrology"]
    with pytest.raises(ValidationError):
        VenueSpec(**venue_dict)


def test_venue_spec_rejects_bad_id_pattern(venue_dict: dict[str, object]) -> None:
    venue_dict["id"] = "Bad-ID"
    with pytest.raises(ValidationError):
        VenueSpec(**venue_dict)


def test_venue_spec_rejects_unknown_kind(venue_dict: dict[str, object]) -> None:
    venue_dict["kind"] = "magazine"
    with pytest.raises(ValidationError):
        VenueSpec(**venue_dict)


def test_venue_spec_parses_nested_auth_and_rate_limit(venue_dict: dict[str, object]) -> None:
    venue_dict["auth"] = {"level": "institutional", "provider_hint": "elsevier"}
    venue_dict["rate_limit"] = {"requests_per_minute": 10}
    spec = VenueSpec(**venue_dict)
    assert spec.auth.level is AuthLevel.INSTITUTIONAL
    assert spec.auth.provider_hint == "elsevier"
    assert spec.rate_limit.requests_per_minute == 10
