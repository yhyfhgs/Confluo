"""oup_silverchair adapter 单测（design/adapters/oup-silverchair.md §3/§5/§7）。

覆盖：四件套 `ChallengeDetector` 判定回放（§7）；resolve/fetch 四态错误映射（§5）；
无 session→AuthRequired / 无 DOI→CONFIG / seam 未装配→CONFIG；healthcheck SKIP 语义；
cookie 域限定的凭证防泄漏（doi.org 首跳不带 cookie）。全程 httpx.MockTransport 零真实网络。
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from helpers import FakeFetchIO, make_oup_venue
from helpers.oup_silverchair_fixtures import (
    MINIMAL_PDF,
    direct_transport,
    landing_transport,
    oup_fixture,
    static_cookie_supplier,
)
from paper_crawler.adapters.oup_silverchair.adapter import OupSilverchairAdapter
from paper_crawler.auth.challenge import ChallengeDetector, ClassifyResult
from paper_crawler.errors import AuthRequired, Challenged, CrawlerError, ErrorClass
from paper_crawler.types import (
    AssetKind,
    AssetPlan,
    AuthLevel,
    Capability,
    PaperStub,
    SessionBackend,
    SessionHandle,
    UrlStrategy,
)

_DOI = "10.1093/qje/qjae044"
_VENUE = make_oup_venue()


def _paper(doi: str = _DOI) -> PaperStub:
    return PaperStub(title="A Synthetic Placeholder Article", identifiers=(("doi", doi),))


def _session() -> SessionHandle:
    return SessionHandle(
        provider_id="oup@campus",
        backend=SessionBackend.HTTPX_COOKIES,
        payload_ref="oup-campus-state",
        established_at=datetime(2026, 7, 23, tzinfo=UTC),
    )


def _adapter(final_or_transport, *, cookies=None) -> OupSilverchairAdapter:
    return OupSilverchairAdapter(
        cookie_supplier=static_cookie_supplier(cookies), transport=final_or_transport
    )


def _fixture_transport(name: str) -> httpx.MockTransport:
    status, headers, final_url, body = oup_fixture(name)
    return landing_transport(final_url, status, headers, body)


# ---------------------------------------------------------------------------
# 四件套 ChallengeDetector 判定回放（§7 离线判定器基石）
# ---------------------------------------------------------------------------

_DETECTOR = ChallengeDetector()


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("01_challenge_cf_mitigated", ClassifyResult.CHALLENGE),
        ("02_login_redirect_signin", ClassifyResult.LOGIN_REDIRECT),
        ("03_no_entitlement_abstract", ClassifyResult.NO_ENTITLEMENT),
        ("04_fulltext_logged_in", ClassifyResult.OK),
    ],
)
def test_four_fixture_detector_replay(fixture: str, expected: ClassifyResult) -> None:
    status, headers, final_url, body = oup_fixture(fixture)
    result = _DETECTOR.classify(status=status, headers=headers, final_url=final_url, body=body)
    assert result is expected, f"{fixture}: expected {expected}, got {result}"


# ---------------------------------------------------------------------------
# resolve_assets 四态 + 边界（§3.1/§5）
# ---------------------------------------------------------------------------


def test_resolve_ok_yields_pdf_and_si_plans() -> None:
    adapter = _adapter(_fixture_transport("04_fulltext_logged_in"))
    plans = adapter.resolve_assets(_VENUE, _paper(), session=_session())

    assert len(plans) == 2
    pdf = plans[0]
    assert pdf.kind is AssetKind.PDF
    assert pdf.url == "https://academic.oup.com/qje/article-pdf/141/3/2205/61701561/qjae044.pdf"
    assert pdf.url_strategy is UrlStrategy.DIRECT
    assert pdf.auth_needed is AuthLevel.INSTITUTIONAL
    assert pdf.expected_type == "application/pdf"
    si = plans[1]
    assert si.kind is AssetKind.SI
    assert "supplementary" in si.url.lower()


def test_resolve_challenge_raises_challenged() -> None:
    adapter = _adapter(_fixture_transport("01_challenge_cf_mitigated"))
    with pytest.raises(Challenged) as exc:
        adapter.resolve_assets(_VENUE, _paper(), session=_session())
    assert exc.value.error_class is ErrorClass.CHALLENGE


def test_resolve_login_redirect_raises_auth_required() -> None:
    adapter = _adapter(_fixture_transport("02_login_redirect_signin"))
    with pytest.raises(AuthRequired) as exc:
        adapter.resolve_assets(_VENUE, _paper(), session=_session())
    assert exc.value.error_class is ErrorClass.AUTH_EXPIRED


def test_resolve_no_entitlement_raises_no_entitlement() -> None:
    adapter = _adapter(_fixture_transport("03_no_entitlement_abstract"))
    with pytest.raises(CrawlerError) as exc:
        adapter.resolve_assets(_VENUE, _paper(), session=_session())
    assert exc.value.error_class is ErrorClass.NO_ENTITLEMENT


def test_resolve_ok_page_with_zero_pdf_links_is_parse_error() -> None:
    # design §5：OK 全文页却 0 PDF 链接 = 改版腐化信号 → PARSE（由 classify=OK 区分于
    # NO_ENTITLEMENT，非文本二次嗅探）。
    body = (
        b"<html><body><a href='/user/logout'>Sign out</a><p>Full text, no link.</p></body></html>"
    )
    transport = landing_transport(
        "https://academic.oup.com/qje/article/141/3/2205/8662148", 200, {}, body
    )
    adapter = _adapter(transport)
    with pytest.raises(CrawlerError) as exc:
        adapter.resolve_assets(_VENUE, _paper(), session=_session())
    assert exc.value.error_class is ErrorClass.PARSE


def test_resolve_without_session_raises_auth_required() -> None:
    adapter = _adapter(_fixture_transport("04_fulltext_logged_in"))
    with pytest.raises(AuthRequired) as exc:
        adapter.resolve_assets(_VENUE, _paper(), session=None)
    assert exc.value.error_class is ErrorClass.AUTH_EXPIRED


def test_resolve_missing_doi_is_config_error() -> None:
    adapter = _adapter(_fixture_transport("04_fulltext_logged_in"))
    paper = PaperStub(title="No DOI", identifiers=(("arxiv", "2401.00001"),))
    with pytest.raises(CrawlerError) as exc:
        adapter.resolve_assets(_VENUE, paper, session=_session())
    assert exc.value.error_class is ErrorClass.CONFIG


def test_resolve_without_cookie_supplier_is_config_error() -> None:
    # session 在但 seam 未装配（pre-T1b 装配缺陷）→ 响亮 CONFIG。
    adapter = OupSilverchairAdapter(
        cookie_supplier=None, transport=_fixture_transport("04_fulltext_logged_in")
    )
    with pytest.raises(CrawlerError) as exc:
        adapter.resolve_assets(_VENUE, _paper(), session=_session())
    assert exc.value.error_class is ErrorClass.CONFIG


# ---------------------------------------------------------------------------
# fetch_asset（§3.2/§5）
# ---------------------------------------------------------------------------


def _pdf_plan(
    url: str = "https://academic.oup.com/qje/article-pdf/141/3/2205/61701561/qjae044.pdf",
) -> AssetPlan:
    return AssetPlan(kind=AssetKind.PDF, url=url)


def test_fetch_ok_writes_pdf_magic() -> None:
    adapter = _adapter(direct_transport(200, {"content-type": "application/pdf"}, MINIMAL_PDF))
    io = FakeFetchIO()
    result = adapter.fetch_asset(_pdf_plan(), io, session=_session())
    assert result.ok is True
    assert io.data.startswith(b"%PDF")
    assert result.bytes_written == len(MINIMAL_PDF)


def test_fetch_challenge_raises_challenged() -> None:
    _, headers, _, body = oup_fixture("01_challenge_cf_mitigated")
    adapter = _adapter(direct_transport(403, headers, body))
    with pytest.raises(Challenged) as exc:
        adapter.fetch_asset(_pdf_plan(), FakeFetchIO(), session=_session())
    assert exc.value.error_class is ErrorClass.CHALLENGE


def test_fetch_login_redirect_raises_auth_required() -> None:
    _, _, final_url, body = oup_fixture("02_login_redirect_signin")
    adapter = _adapter(direct_transport(200, {}, body, redirect_to=final_url))
    with pytest.raises(AuthRequired) as exc:
        adapter.fetch_asset(_pdf_plan(), FakeFetchIO(), session=_session())
    assert exc.value.error_class is ErrorClass.AUTH_EXPIRED


def test_fetch_html_disguised_as_pdf_is_integrity_auth_leak() -> None:
    # 200 但非 %PDF、分类 OK（登录态泄漏/拦截页伪装）→ integrity(auth_leak)。
    body = b"<html><body><a href='/user/logout'>Sign out</a>Not a pdf.</body></html>"
    adapter = _adapter(direct_transport(200, {"content-type": "text/html"}, body))
    with pytest.raises(CrawlerError) as exc:
        adapter.fetch_asset(_pdf_plan(), FakeFetchIO(), session=_session())
    assert exc.value.error_class is ErrorClass.INTEGRITY
    assert exc.value.detail == "auth_leak"


def test_fetch_no_entitlement_raises_no_entitlement() -> None:
    _, _, final_url, body = oup_fixture("03_no_entitlement_abstract")
    # fetch 落点为 article-abstract → classify NO_ENTITLEMENT。
    adapter = _adapter(direct_transport(200, {}, body, redirect_to=final_url))
    with pytest.raises(CrawlerError) as exc:
        adapter.fetch_asset(_pdf_plan(), FakeFetchIO(), session=_session())
    assert exc.value.error_class is ErrorClass.NO_ENTITLEMENT


def test_fetch_without_session_raises_auth_required() -> None:
    adapter = _adapter(direct_transport(200, {}, MINIMAL_PDF))
    with pytest.raises(AuthRequired):
        adapter.fetch_asset(_pdf_plan(), FakeFetchIO(), session=None)


# ---------------------------------------------------------------------------
# healthcheck（§3.3；SKIP 语义）
# ---------------------------------------------------------------------------


def test_healthcheck_without_session_raises_not_implemented() -> None:
    # canary SKIP 语义（无 session 的 healthcheck = NotImplementedError，auth-framework §7）。
    adapter = _adapter(direct_transport(200, {}, b""))
    with pytest.raises(NotImplementedError):
        adapter.healthcheck(session=None)


def test_healthcheck_ok_probe_is_healthy() -> None:
    body = (
        b"<html><body><a href='/my-account'>My Account</a>"
        b"<a href='/user/logout'>Sign out</a></body></html>"
    )
    adapter = _adapter(direct_transport(200, {}, body))
    report = adapter.healthcheck(session=_session())
    assert report.healthy is True


def test_healthcheck_expired_session_is_unhealthy() -> None:
    _, _, final_url, body = oup_fixture("02_login_redirect_signin")
    adapter = _adapter(direct_transport(200, {}, body, redirect_to=final_url))
    report = adapter.healthcheck(session=_session())
    assert report.healthy is False
    assert "过期" in report.detail


def test_healthcheck_challenge_is_unhealthy() -> None:
    _, headers, _, body = oup_fixture("01_challenge_cf_mitigated")
    adapter = _adapter(direct_transport(403, headers, body))
    report = adapter.healthcheck(session=_session())
    assert report.healthy is False


def test_healthcheck_no_entitlement_probe_is_unhealthy() -> None:
    # 账号探针页落 NO_ENTITLEMENT（非 OK/EXPIRED/CHALLENGED）→ 非预期分类 → unhealthy。
    _, _, _, body = oup_fixture("03_no_entitlement_abstract")
    adapter = _adapter(direct_transport(200, {}, body))
    report = adapter.healthcheck(session=_session())
    assert report.healthy is False
    assert "非预期" in report.detail


# ---------------------------------------------------------------------------
# seam 注入 + 网络层异常映射（§3.2 seam / design §6 冻结错误映射对齐）
# ---------------------------------------------------------------------------


def test_set_cookie_supplier_injects_seam_post_construction() -> None:
    # 生产路径：load_adapters() 无参构造 → pipeline set_cookie_supplier 注入（duck-typed）。
    adapter = OupSilverchairAdapter(transport=_fixture_transport("04_fulltext_logged_in"))
    adapter.set_cookie_supplier(static_cookie_supplier())
    plans = adapter.resolve_assets(_VENUE, _paper(), session=_session())
    assert plans and plans[0].kind is AssetKind.PDF


@pytest.mark.parametrize(
    "exc",
    [httpx.ConnectTimeout("synthetic timeout"), httpx.ConnectError("synthetic conn error")],
    ids=["timeout", "connect-error"],
)
def test_network_error_maps_to_transient(exc: httpx.HTTPError) -> None:
    def _boom(_request: httpx.Request) -> httpx.Response:
        raise exc

    adapter = _adapter(httpx.MockTransport(_boom))
    with pytest.raises(CrawlerError) as raised:
        adapter.fetch_asset(_pdf_plan(), FakeFetchIO(), session=_session())
    assert raised.value.error_class is ErrorClass.TRANSIENT


# ---------------------------------------------------------------------------
# 凭证红线：cookie 域限定（doi.org 首跳不带 cookie；academic.oup.com 才带）
# ---------------------------------------------------------------------------


def test_cookies_scoped_to_oup_domain_not_leaked_to_doi_org() -> None:
    seen: dict[str, str | None] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        seen[request.url.host] = request.headers.get("cookie")
        if request.url.host == "doi.org":
            return httpx.Response(
                302, headers={"Location": "https://academic.oup.com/qje/article/1/1/1/1"}
            )
        body = (
            b'<html><head><meta name="citation_pdf_url" '
            b'content="https://academic.oup.com/qje/article-pdf/1/1/1/F9/x.pdf"/></head>'
            b"<body><a href='/user/logout'>Sign out</a></body></html>"
        )
        return httpx.Response(200, content=body)

    adapter = _adapter(httpx.MockTransport(_handler), cookies={"SILVERCHAIR_SESSION": "secret"})
    adapter.resolve_assets(_VENUE, _paper(), session=_session())

    assert seen["doi.org"] is None, "cookie 泄漏给了 doi.org（凭证红线违规）"
    assert seen["academic.oup.com"] is not None
    assert "SILVERCHAIR_SESSION" in seen["academic.oup.com"]


# ---------------------------------------------------------------------------
# 类属性（family/caps/auth/domain/rate 出处）
# ---------------------------------------------------------------------------


def test_adapter_class_attributes() -> None:
    adapter = OupSilverchairAdapter()
    assert adapter.adapter_id == "oup_silverchair"
    assert adapter.family == "auth_gated"
    assert adapter.capabilities == (Capability.RESOLVE | Capability.FETCH)
    assert adapter.auth_requirement is AuthLevel.INSTITUTIONAL
    assert adapter.domains == ("academic.oup.com",)
    assert adapter.default_rate.requests_per_minute == 10.0
    assert adapter.default_rate.source_note
