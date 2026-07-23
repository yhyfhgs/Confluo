"""AeaAdapter 主体单测（design/adapters/aea.md §3.3/§3.5/§4；phase5-plan T5 DoD）。

零真实网络（`resolve_assets`/`healthcheck` 本身即全离线，无需 mock transport）。
覆盖：① 订阅刊 resolve → `NO_ENTITLEMENT`（不计 failures 终态判据的载体；软门
text/html 挡板→no_entitlement 非 integrity 的离线等价断言，§6 失败模式表）；
② OA 刊（jel/jep）resolve → 空列表、不 raise；③ 两分支均先记 deferred 全文 URL 的
DEBUG 观测；④ 未知 DOI code → WARN 观测、不崩；⑤ P&P 形态不误触 WARN；⑥ 缺 DOI /
非 10.1257 DOI → CONFIG；⑦ healthcheck 恒 NotImplementedError（→ canary SKIP）；
⑧ 未声明能力（DISCOVER/ENUMERATE/FETCH）→ CapabilityNotSupported；⑨ adapter 元
数据完备性。
"""

from __future__ import annotations

import pytest

from paper_crawler.adapters.aea.adapter import AeaAdapter
from paper_crawler.errors import CapabilityNotSupported, CrawlerError, ErrorClass
from paper_crawler.types import (
    AuthLevel,
    IssueRef,
    PaperStub,
    VenueAuth,
    VenueNames,
    VenueSpec,
)

# --- 本地 venue 工厂（不依赖 tests/helpers 共享花名册，避免与并行任务的撞面）--------------


def _venue(
    venue_id: str,
    *,
    issn: str,
    auth_level: AuthLevel,
    full_name: str | None = None,
) -> VenueSpec:
    return VenueSpec(
        id=venue_id,
        kind="journal",
        names=VenueNames(full=full_name or venue_id.upper(), aliases=[]),
        field=["econ"],
        identifiers={"issn": [issn]},
        metadata_source="crossref",
        fulltext_source="aea",
        auth=VenueAuth(level=auth_level, provider_hint="aea"),
    )


def _subscription_venue(venue_id: str = "aer", issn: str = "0002-8282") -> VenueSpec:
    return _venue(venue_id, issn=issn, auth_level=AuthLevel.INSTITUTIONAL)


def _open_venue(venue_id: str = "jep", issn: str = "0895-3309") -> VenueSpec:
    return _venue(venue_id, issn=issn, auth_level=AuthLevel.NONE)


def _paper_with_doi(doi: str, title: str = "T") -> PaperStub:
    return PaperStub(title=title, identifiers=(("doi", doi),))


# --- 元数据/能力面 --------------------------------------------------------------------------


def test_adapter_attributes() -> None:
    adapter = AeaAdapter()
    assert adapter.adapter_id == "aea"
    assert adapter.family == "auth_gated"
    assert adapter.capabilities.name == "RESOLVE"
    assert adapter.auth_requirement is AuthLevel.NONE
    assert adapter.domains == ("www.aeaweb.org",)
    assert adapter.resolve_offline is True
    assert adapter.default_rate.requests_per_minute > 0
    assert adapter.default_rate.source_note != ""


def test_undeclared_capabilities_raise_capability_not_supported() -> None:
    adapter = AeaAdapter()
    venue = _open_venue()
    with pytest.raises(CapabilityNotSupported):
        list(adapter.discover_timeline(venue))
    with pytest.raises(CapabilityNotSupported):
        list(adapter.enumerate_issue(venue, IssueRef(venue_id=venue.id)))
    with pytest.raises(CapabilityNotSupported):
        adapter.fetch_asset(plan=None, io=None)  # type: ignore[arg-type]


# --- resolve_assets：订阅刊 → NO_ENTITLEMENT ------------------------------------------------


def test_resolve_assets_subscription_venue_raises_no_entitlement() -> None:
    adapter = AeaAdapter()
    venue = _subscription_venue("aer", "0002-8282")
    paper = _paper_with_doi("10.1257/aer.20230344")

    with pytest.raises(CrawlerError) as excinfo:
        adapter.resolve_assets(venue, paper)

    assert excinfo.value.error_class is ErrorClass.NO_ENTITLEMENT
    assert excinfo.value.detail == "no_entitlement"
    assert "10.1257/aer.20230344" in str(excinfo.value)


@pytest.mark.parametrize(
    ("venue_id", "issn"),
    [
        ("aer", "0002-8282"),
        ("aeri", "2640-205X"),
        ("aej_macro", "1945-7707"),
        ("aej_micro", "1945-7669"),
        ("aej_applied", "1945-7782"),
        ("aej_policy", "1945-7731"),
    ],
)
def test_resolve_assets_all_6_subscription_venues_raise_no_entitlement(
    venue_id: str, issn: str
) -> None:
    """6 订阅刊（aer/aeri/aej_×4）resolve 均 raise NO_ENTITLEMENT（aea.md §7 表）。"""
    adapter = AeaAdapter()
    venue = _subscription_venue(venue_id, issn)
    paper = _paper_with_doi("10.1257/aer.20230344")  # DOI 与 venue.id 是否一致不影响本断言

    with pytest.raises(CrawlerError) as excinfo:
        adapter.resolve_assets(venue, paper)
    assert excinfo.value.error_class is ErrorClass.NO_ENTITLEMENT


def test_resolve_assets_no_entitlement_does_not_produce_a_partial_asset_plan() -> None:
    """raise 前不应有任何"部分产出"副作用——resolve_assets 是纯函数式的
    raise-or-empty-list 契约（模块 docstring："结构性地从不返回非空 AssetPlan"）。
    """
    adapter = AeaAdapter()
    venue = _subscription_venue()
    paper = _paper_with_doi("10.1257/aer.20230344")
    try:
        adapter.resolve_assets(venue, paper)
    except CrawlerError:
        pass
    else:
        pytest.fail("expected CrawlerError(NO_ENTITLEMENT)")


# --- resolve_assets：OA 刊（jel/jep）→ 空列表，不 raise --------------------------------------


def test_resolve_assets_open_venue_returns_empty_list_not_an_error() -> None:
    adapter = AeaAdapter()
    venue = _open_venue("jep", "0895-3309")
    paper = _paper_with_doi("10.1257/jep.20251473")

    plans = adapter.resolve_assets(venue, paper)

    assert plans == []


@pytest.mark.parametrize(("venue_id", "issn"), [("jel", "0022-0515"), ("jep", "0895-3309")])
def test_resolve_assets_both_open_venues_return_empty_list(venue_id: str, issn: str) -> None:
    adapter = AeaAdapter()
    venue = _open_venue(venue_id, issn)
    paper = _paper_with_doi("10.1257/jep.20251473")

    assert adapter.resolve_assets(venue, paper) == []


def test_resolve_assets_open_venue_does_not_raise_no_entitlement() -> None:
    """OA 刊无认证问题（auth.level=none 本身属实）——不应误用 no_entitlement 语义
    （模块 docstring："raise 该错误类会误导为权限不足而非平台层技术阻断"）。
    """
    adapter = AeaAdapter()
    venue = _open_venue()
    paper = _paper_with_doi("10.1257/jep.20251473")
    adapter.resolve_assets(venue, paper)  # 不应抛出任何异常


# --- deferred 全文 URL 的 DEBUG 观测（两分支均记录，§3.3）-----------------------------------


def test_resolve_assets_subscription_logs_deferred_fulltext_url_before_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.aea.adapter.log_event",
        lambda level, msg, **kw: events.append({"level": level, "msg": msg, **kw}),
    )
    adapter = AeaAdapter()
    venue = _subscription_venue("aer", "0002-8282")
    paper = _paper_with_doi("10.1257/aer.20230344")

    with pytest.raises(CrawlerError):
        adapter.resolve_assets(venue, paper)

    deferred = [e for e in events if "deferred" in str(e["msg"])]
    assert len(deferred) == 1
    assert deferred[0]["deferred_url"] == "https://pubs.aeaweb.org/doi/pdfplus/10.1257/aer.20230344"
    assert deferred[0]["auth_needed"] == "institutional"
    assert deferred[0]["venue"] == "aer"
    assert deferred[0]["level"] == "DEBUG"


def test_resolve_assets_open_venue_logs_deferred_fulltext_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.aea.adapter.log_event",
        lambda level, msg, **kw: events.append({"level": level, "msg": msg, **kw}),
    )
    adapter = AeaAdapter()
    venue = _open_venue("jep", "0895-3309")
    paper = _paper_with_doi("10.1257/jep.20251473")

    adapter.resolve_assets(venue, paper)

    deferred = [e for e in events if "deferred" in str(e["msg"])]
    assert len(deferred) == 1
    assert deferred[0]["deferred_url"] == "https://pubs.aeaweb.org/doi/pdfplus/10.1257/jep.20251473"
    assert deferred[0]["auth_needed"] == "none"
    assert deferred[0]["venue"] == "jep"


# --- 未知 DOI code → WARN 观测，不崩（§3.2）--------------------------------------------------


def test_resolve_assets_unknown_code_logs_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.aea.adapter.log_event",
        lambda level, msg, **kw: events.append({"level": level, "msg": msg, **kw}),
    )
    adapter = AeaAdapter()
    venue = _open_venue()  # 用开放 venue 让 resolve 干净返回，便于断言事件列表
    paper = _paper_with_doi("10.1257/newjournal.20230344")

    plans = adapter.resolve_assets(venue, paper)

    assert plans == []
    warnings = [e for e in events if e["level"] == "WARNING"]
    assert len(warnings) == 1
    assert warnings[0]["code"] == "newjournal"
    assert warnings[0]["doi"] == "10.1257/newjournal.20230344"


def test_resolve_assets_known_code_does_not_log_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.aea.adapter.log_event",
        lambda level, msg, **kw: events.append({"level": level, "msg": msg, **kw}),
    )
    adapter = AeaAdapter()
    adapter.resolve_assets(_open_venue(), _paper_with_doi("10.1257/jep.20251473"))

    assert [e for e in events if e["level"] == "WARNING"] == []


def test_resolve_assets_pnp_form_does_not_log_warning_even_though_unrouted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P&P 形态（`aer.p*`）虽 `venue_id is None`，但这是已知的暂缓分类（A-3），不是
    "未知子刊"信号——不该触发 WARN（区别于真正未知 code 的 test_resolve_assets_
    unknown_code_logs_warning）。
    """
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.aea.adapter.log_event",
        lambda level, msg, **kw: events.append({"level": level, "msg": msg, **kw}),
    )
    adapter = AeaAdapter()
    adapter.resolve_assets(_open_venue(), _paper_with_doi("10.1257/aer.p20151048"))

    assert [e for e in events if e["level"] == "WARNING"] == []


# --- 缺 DOI / 非 10.1257 DOI → CONFIG --------------------------------------------------------


def test_resolve_assets_missing_doi_raises_config() -> None:
    adapter = AeaAdapter()
    venue = _open_venue()
    paper = PaperStub(title="No DOI", identifiers=(("arxiv", "2401.00001"),))

    with pytest.raises(CrawlerError) as excinfo:
        adapter.resolve_assets(venue, paper)
    assert excinfo.value.error_class is ErrorClass.CONFIG


def test_resolve_assets_non_aea_doi_raises_config() -> None:
    """路由错配防御：paper 携带的 DOI 前缀非 10.1257（如误路由到 aea 的 elsevier 论文）。"""
    adapter = AeaAdapter()
    venue = _open_venue()
    paper = _paper_with_doi("10.1016/j.jfineco.2011.03.021")

    with pytest.raises(CrawlerError) as excinfo:
        adapter.resolve_assets(venue, paper)
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert "10.1016" in str(excinfo.value)


# --- healthcheck：恒 NotImplementedError（→ canary SKIP，§3.5）------------------------------


def test_healthcheck_raises_not_implemented() -> None:
    adapter = AeaAdapter()
    with pytest.raises(NotImplementedError):
        adapter.healthcheck()


def test_healthcheck_not_implemented_message_mentions_browser_fetch() -> None:
    adapter = AeaAdapter()
    with pytest.raises(NotImplementedError, match="browser-fetch"):
        adapter.healthcheck()
