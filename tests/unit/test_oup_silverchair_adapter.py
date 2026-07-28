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
    host_scoped_cookie_supplier,
    landing_transport,
    oup_fixture,
    static_cookie_supplier,
)
from paper_crawler.adapters.oup_silverchair import adapter as adapter_module
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
# MINOR-1：非 PDF SI 附录不做 %PDF 魔数断言 / 不误报 auth_leak（expected_type 门控）
# ---------------------------------------------------------------------------

_SI_ZIP_URL = (
    "https://academic.oup.com/qje/article-pdf/141/3/2205/61701561/appendix_supplementary.zip"
)


def _si_plan(url: str = _SI_ZIP_URL, *, expected_type: str = "application/zip") -> AssetPlan:
    return AssetPlan(kind=AssetKind.SI, url=url, expected_type=expected_type)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://x/a_supplementary.pdf", "application/pdf"),
        ("https://x/a_supplementary.zip", "application/zip"),
        (
            "https://x/a_supplementary.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        ("https://x/a_supplementary.bin", "application/octet-stream"),  # 未知扩展名回落
    ],
)
def test_expected_type_inferred_by_extension(url: str, expected: str) -> None:
    from paper_crawler.adapters.oup_silverchair.adapter import _expected_type_for

    assert _expected_type_for(url) == expected


def test_resolve_infers_si_zip_expected_type() -> None:
    # 落地页含 .zip SI 附录 → SI plan.expected_type 按扩展名推断为 application/zip（非硬编）。
    body = (
        b'<head><meta name="citation_pdf_url" '
        b'content="https://academic.oup.com/qje/article-pdf/1/1/1/F/main.pdf"/></head>'
        b"<body><a href='/user/logout'>Sign out</a>"
        b'<a href="/qje/article-pdf/1/1/1/F/appendix_supplementary.zip">'
        b"Supplementary Data</a></body>"
    )
    transport = landing_transport("https://academic.oup.com/qje/article/1/1/1/1", 200, {}, body)
    plans = _adapter(transport).resolve_assets(_VENUE, _paper(), session=_session())
    si = next(p for p in plans if p.kind is AssetKind.SI)
    assert si.expected_type == "application/zip"


def test_fetch_non_pdf_si_writes_without_magic_and_no_auth_leak() -> None:
    # 关键 MINOR-1 断言：zip 形态 SI（首字节 PK，非 %PDF）200 → 正常写，**不误报** auth_leak。
    zip_body = b"PK\x03\x04" + b"\x00" * 64
    adapter = _adapter(direct_transport(200, {"content-type": "application/zip"}, zip_body))
    io = FakeFetchIO()
    result = adapter.fetch_asset(_si_plan(), io, session=_session())
    assert result.ok is True
    assert io.data == zip_body


def test_fetch_non_pdf_si_challenge_still_detected() -> None:
    # 魔数门控不削弱挑战判读：SI 请求被 challenge 拦截仍如实上报（红线不变）。
    _, headers, _, body = oup_fixture("01_challenge_cf_mitigated")
    adapter = _adapter(direct_transport(403, headers, body))
    with pytest.raises(Challenged):
        adapter.fetch_asset(_si_plan(), FakeFetchIO(), session=_session())


def test_fetch_non_pdf_si_non_200_is_integrity_not_auth_leak() -> None:
    # 非 PDF 资产非 200 且分类 OK（罕见，如 5xx 良性体）→ 泛 integrity（**非** auth_leak，
    # auth_leak 仅属 PDF 主路的魔数失败——门控生效的负向证据）。
    adapter = _adapter(direct_transport(500, {}, b"upstream hiccup, not a challenge"))
    with pytest.raises(CrawlerError) as exc:
        adapter.fetch_asset(_si_plan(), FakeFetchIO(), session=_session())
    assert exc.value.error_class is ErrorClass.INTEGRITY
    assert exc.value.detail != "auth_leak"


def test_fetch_pdf_main_path_magic_protection_unchanged() -> None:
    # 正例：真 PDF（%PDF）写入成功；反例：HTML 伪装 → auth_leak——PDF 主路防护逐字不变。
    ok = _adapter(direct_transport(200, {"content-type": "application/pdf"}, MINIMAL_PDF))
    assert ok.fetch_asset(_pdf_plan(), FakeFetchIO(), session=_session()).ok is True

    fake = b"<html><body><a href='/user/logout'>Sign out</a>not pdf</body></html>"
    bad = _adapter(direct_transport(200, {"content-type": "text/html"}, fake))
    with pytest.raises(CrawlerError) as exc:
        bad.fetch_asset(_pdf_plan(), FakeFetchIO(), session=_session())
    assert exc.value.error_class is ErrorClass.INTEGRITY and exc.value.detail == "auth_leak"


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
# R3e：cookie 域感知（ezproxy 改写后的 host 拿 proxy cookie；平台 cookie 不外发代理域）
# ---------------------------------------------------------------------------

# pipeline `_proxy_rewritten` 在 fetch 前把 plan.url 换成的代理形态（EZProxyProvider
# `rewrite_url` 规则：host 的 `.`→`-` + rewrite_suffix，见 tests/unit/test_auth_providers.py）。
_PROXY_HOST = "academic-oup-com.login-myuniv-edu.ezproxy"
_PROXY_PDF_URL = f"https://{_PROXY_HOST}/qje/article-pdf/141/3/2205/61701561/qjae044.pdf"
_PLATFORM_COOKIES = {"SILVERCHAIR_SESSION": "platform-secret"}
_PROXY_COOKIES = {"ezproxy": "proxy-secret"}


def _cookie_capturing_transport(seen: dict[str, str | None]) -> httpx.MockTransport:
    """记录每次请求 host → `Cookie` 头，回 200 PDF（fetch 主路快路直接成功）。"""

    def _handler(request: httpx.Request) -> httpx.Response:
        seen[request.url.host] = request.headers.get("cookie")
        return httpx.Response(200, content=MINIMAL_PDF, headers={"content-type": "application/pdf"})

    return httpx.MockTransport(_handler)


def _host_aware_adapter(transport: httpx.MockTransport) -> OupSilverchairAdapter:
    """域感知 supplier（平台主域 → 平台 cookie；代理域 → proxy cookie）+ 给定 transport。"""
    return OupSilverchairAdapter(
        cookie_supplier=host_scoped_cookie_supplier(
            {"academic.oup.com": _PLATFORM_COOKIES, _PROXY_HOST: _PROXY_COOKIES}
        ),
        transport=transport,
    )


def test_fetch_on_ezproxy_rewritten_host_carries_proxy_cookie() -> None:
    """ezproxy 形态：pipeline 已把 plan.url 改写到代理域 → 请求须带 **proxy cookie**。

    修复前 `_cookies_for` 把 supplier 交出的 cookie 硬钉平台主域（`domain=_PRIMARY_DOMAIN`）
    且 seam 的类型面丢掉域信息，代理域请求域匹配失败 → cookie 全被丢、请求裸发（R2d 顾虑①）。
    """
    seen: dict[str, str | None] = {}
    adapter = _host_aware_adapter(_cookie_capturing_transport(seen))

    result = adapter.fetch_asset(_pdf_plan(_PROXY_PDF_URL), FakeFetchIO(), session=_session())

    assert result.ok is True
    assert "ezproxy=proxy-secret" in (seen[_PROXY_HOST] or ""), "proxy cookie 未随代理请求发出"


def test_platform_cookie_not_sent_to_ezproxy_host() -> None:
    """凭证隔离：平台主域 cookie 绝不外发到代理域（供给方按 host 交付，消费方按 host 钉域）。"""
    seen: dict[str, str | None] = {}
    adapter = _host_aware_adapter(_cookie_capturing_transport(seen))

    adapter.fetch_asset(_pdf_plan(_PROXY_PDF_URL), FakeFetchIO(), session=_session())

    assert "platform-secret" not in (seen[_PROXY_HOST] or "")
    assert "SILVERCHAIR_SESSION" not in (seen[_PROXY_HOST] or "")


def test_fetch_on_platform_host_still_carries_platform_cookie() -> None:
    """直连不回归：未经代理改写的平台域请求仍带平台 cookie（同一域感知路径的另一支）。"""
    seen: dict[str, str | None] = {}
    adapter = _host_aware_adapter(_cookie_capturing_transport(seen))

    adapter.fetch_asset(_pdf_plan(), FakeFetchIO(), session=_session())

    assert "SILVERCHAIR_SESSION=platform-secret" in (seen["academic.oup.com"] or "")
    assert "proxy-secret" not in (seen["academic.oup.com"] or "")


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://doi.org/10.1093/qje/qjae044", "academic.oup.com"),  # 首跳归重定向落点
        ("https://academic.oup.com/qje/article-pdf/x.pdf", "academic.oup.com"),  # 直连
        (f"https://{_PROXY_HOST}/qje/article-pdf/x.pdf", _PROXY_HOST),  # ezproxy 改写后
        ("https://ACADEMIC.OUP.COM/qje/x.pdf", "academic.oup.com"),  # host 归一小写
        ("/relative/path.pdf", "academic.oup.com"),  # 无 host → 保守回落主域
    ],
)
def test_cookie_host_for_maps_request_url_to_owning_domain(url: str, expected: str) -> None:
    """cookie 归属域的逐条判据（`_cookies_for` 的过滤键 + 钉域键，两处共用同一函数）。"""
    assert adapter_module._cookie_host_for(url) == expected


def test_resolve_first_hop_asks_supplier_for_platform_host_not_doi_org() -> None:
    """resolve 首跳是 `doi.org`，但 cookie 归属是**重定向落点**（平台主域）——供给方被问的
    host 是 `academic.oup.com`，doi.org 依旧零 cookie（防泄漏红线在域感知后仍成立）。"""
    asked: list[str] = []
    seen: dict[str, str | None] = {}

    def _supplier(_session_handle: SessionHandle, host: str) -> dict[str, str]:
        asked.append(host)
        return dict(_PLATFORM_COOKIES) if host == "academic.oup.com" else {}

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

    adapter = OupSilverchairAdapter(
        cookie_supplier=_supplier, transport=httpx.MockTransport(_handler)
    )
    adapter.resolve_assets(_VENUE, _paper(), session=_session())

    assert asked == ["academic.oup.com"], "首跳 doi.org 不该被当成 cookie 归属域"
    assert seen["doi.org"] is None
    assert "platform-secret" in (seen["academic.oup.com"] or "")


# ---------------------------------------------------------------------------
# 联系邮箱注入 + per-request obslog（R2c：P1-17/18 修复）
# ---------------------------------------------------------------------------


def _ua_capturing_transport(sink: list[str], *, body: bytes = MINIMAL_PDF) -> httpx.MockTransport:
    """记录每次请求的 `User-Agent` 头，回一个 200 PDF 响应（供 fetch 主路快路直接成功）。"""

    def _handler(request: httpx.Request) -> httpx.Response:
        sink.append(request.headers.get("user-agent", ""))
        return httpx.Response(200, content=body, headers={"content-type": "application/pdf"})

    return httpx.MockTransport(_handler)


def test_set_email_reaches_user_agent_mailto(monkeypatch: pytest.MonkeyPatch) -> None:
    """`set_email` 注入后，UA 含 `mailto:<email>`（`build_user_agent` 统一组装，D-014 格式）。

    修复前：oup 恒读 env、无 seam 可挂，`set_email` 尚不存在——本用例在修复前会因
    `AttributeError: 'OupSilverchairAdapter' object has no attribute 'set_email'` 失败。
    """
    monkeypatch.delenv("PAPER_CRAWLER_CONTACT_EMAIL", raising=False)
    seen: list[str] = []
    adapter = _adapter(_ua_capturing_transport(seen))
    adapter.set_email("researcher@example.edu")

    adapter.fetch_asset(_pdf_plan(), FakeFetchIO(), session=_session())

    assert seen and "mailto:researcher@example.edu" in seen[0]


def test_unset_email_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """未注入 email 时回退环境变量 `PAPER_CRAWLER_CONTACT_EMAIL`（修复前恒读的同一条兜底链
    保持不变——`set_email` 是新增的更高优先级，不破坏既有 env 兜底）。"""
    monkeypatch.setenv("PAPER_CRAWLER_CONTACT_EMAIL", "env-fallback@example.edu")
    seen: list[str] = []
    adapter = _adapter(_ua_capturing_transport(seen))

    adapter.fetch_asset(_pdf_plan(), FakeFetchIO(), session=_session())

    assert seen and "mailto:env-fallback@example.edu" in seen[0]


def test_unset_email_and_env_falls_back_to_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    """既无显式注入也无 env → 回退 `.invalid` 占位（回退链末端逐字不变，先例 cvf/arxiv）。"""
    monkeypatch.delenv("PAPER_CRAWLER_CONTACT_EMAIL", raising=False)
    seen: list[str] = []
    adapter = _adapter(_ua_capturing_transport(seen))

    adapter.fetch_asset(_pdf_plan(), FakeFetchIO(), session=_session())

    assert seen and "mailto:anonymous@paper-crawler.invalid" in seen[0]


def test_explicit_email_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """显式注入优先于 env（同 unpaywall `_resolve_email` 优先级先例）。"""
    monkeypatch.setenv("PAPER_CRAWLER_CONTACT_EMAIL", "env-loses@example.edu")
    seen: list[str] = []
    adapter = _adapter(_ua_capturing_transport(seen))
    adapter.set_email("explicit-wins@example.edu")

    adapter.fetch_asset(_pdf_plan(), FakeFetchIO(), session=_session())

    assert seen and "mailto:explicit-wins@example.edu" in seen[0]
    assert "env-loses" not in seen[0]


def test_authed_get_emits_obslog_event_for_resolve_fetch_and_healthcheck(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """resolve/fetch/healthcheck 三调用点经 `_authed_get` 唯一收口，各产恰 1 条 DEBUG 事件
    （`url`/`status`/`stage` 齐全）——V2 订正口径：本卡只补这条 per-request 事件，FetchLog
    落库口径不动。修复前 `_authed_get` 零 obslog 调用，本用例在修复前会因 `events == []` 失败。
    """
    events: list[dict[str, object]] = []

    def _fake_log_event(level: str, msg: str, **fields: object) -> None:
        events.append({"level": level, "msg": msg, **fields})

    monkeypatch.setattr(adapter_module, "log_event", _fake_log_event)

    resolve_adapter = _adapter(_fixture_transport("04_fulltext_logged_in"))
    resolve_adapter.resolve_assets(_VENUE, _paper(), session=_session())

    fetch_adapter = _adapter(
        direct_transport(200, {"content-type": "application/pdf"}, MINIMAL_PDF)
    )
    fetch_adapter.fetch_asset(_pdf_plan(), FakeFetchIO(), session=_session())

    healthcheck_body = (
        b"<html><body><a href='/my-account'>My Account</a>"
        b"<a href='/user/logout'>Sign out</a></body></html>"
    )
    health_adapter = _adapter(direct_transport(200, {}, healthcheck_body))
    health_adapter.healthcheck(session=_session())

    assert [event["stage"] for event in events] == ["resolve", "fetch", "healthcheck"]
    for event in events:
        assert event["level"] == "DEBUG"
        assert isinstance(event["url"], str) and event["url"]
        assert event["status"] == 200
        assert event["domain"] == "academic.oup.com"


# ---------------------------------------------------------------------------
# R3f：URL 改写 seam（oup resolve 侧接入 ezproxy 改写，完成端到端闭环）
# ---------------------------------------------------------------------------


def _proxying_rewriter(_session: SessionHandle, url: str) -> str:
    """离线替身：模拟 `EZProxyProvider.rewrite_url` 对平台主域的改写（不需要自证不碰
    doi.org——调用方 `_rewritten_target` 本就不会把 doi.org 传给它，见其 docstring）。"""
    return url.replace("academic.oup.com", _PROXY_HOST)


def test_set_url_rewriter_injects_seam_post_construction() -> None:
    """生产路径：`load_adapters()` 无参构造 → CLI 装配期经 `set_url_rewriter` 注入
    （duck-typed，同 `set_cookie_supplier` 先例）。"""
    adapter = OupSilverchairAdapter(cookie_supplier=static_cookie_supplier())
    assert adapter._url_rewriter is None

    adapter.set_url_rewriter(_proxying_rewriter)

    assert adapter._url_rewriter is _proxying_rewriter


def test_resolve_platform_landing_is_rewritten_to_proxy_host_when_rewriter_set() -> None:
    """核心断言（R3f AC）：ezproxy 场景下 resolve 的落地请求 host 须为 proxy 域——修复前
    doi.org 302 后 httpx 径直跟到 `academic.oup.com`（裸发），本用例在修复前构造期就会因
    `OupSilverchairAdapter` 不认识 `url_rewriter` 形参而 `TypeError` 失败；假设签名已加但
    改写未接线，则会因 `seen_hosts` 里出现 "academic.oup.com" 而非代理域失败（mock 对
    未预期 host 返 404，解析随之失败）。"""
    seen_hosts: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen_hosts.append(request.url.host)
        if request.url.host == "doi.org":
            return httpx.Response(
                302, headers={"Location": "https://academic.oup.com/qje/article/1/1/1/1"}
            )
        if request.url.host == _PROXY_HOST:
            body = (
                b'<html><head><meta name="citation_pdf_url" '
                b'content="https://academic.oup.com/qje/article-pdf/1/1/1/F9/x.pdf"/></head>'
                b"<body><a href='/user/logout'>Sign out</a></body></html>"
            )
            return httpx.Response(200, content=body)
        return httpx.Response(404, content=b"unexpected host: rewriter did not fire")

    adapter = OupSilverchairAdapter(
        cookie_supplier=static_cookie_supplier(),
        transport=httpx.MockTransport(_handler),
        url_rewriter=_proxying_rewriter,
    )

    plans = adapter.resolve_assets(_VENUE, _paper(), session=_session())

    assert plans and plans[0].kind is AssetKind.PDF
    assert seen_hosts[0] == "doi.org", "doi.org 首跳须仍是第一个物理请求"
    assert _PROXY_HOST in seen_hosts, "落地请求未走代理域——rewriter 未生效"
    assert "academic.oup.com" not in seen_hosts, "落地请求裸打了真实平台域（rewriter 被跳过）"


def test_resolve_doi_org_probe_carries_no_cookie_when_rewriter_set() -> None:
    """doi.org 首跳零 cookie 的红线在 rewriter 在场（手工两段式探路）时依然成立：探路请求
    走的是 `_send`，其 cookie 计算沿用既有 `_cookies_for` 口径（doi.org host 域不匹配、
    恒不随请求发出），不因新增探路分支而破例。"""
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

    adapter = OupSilverchairAdapter(
        cookie_supplier=static_cookie_supplier({"SILVERCHAIR_SESSION": "secret"}),
        transport=httpx.MockTransport(_handler),
        url_rewriter=_proxying_rewriter,
    )

    adapter.resolve_assets(_VENUE, _paper(), session=_session())

    assert seen["doi.org"] is None, "rewriter 在场时 doi.org 探路请求仍不该带 cookie"


def test_resolve_ezproxy_cookie_supplier_hits_proxy_cookie_on_rewritten_host() -> None:
    """端到端（离线，adapter 内）：resolve 落地请求改写到代理域后，域感知 cookie supplier
    （R3e）在该改写后的 host 上命中 **proxy cookie**（不是平台 cookie）——rewriter 与
    cookie 域感知在同一个 host 上闭合，doi.org 依旧零 cookie（brief 要求的"端到端断言"）。
    """
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

    adapter = OupSilverchairAdapter(
        cookie_supplier=host_scoped_cookie_supplier(
            {"academic.oup.com": _PLATFORM_COOKIES, _PROXY_HOST: _PROXY_COOKIES}
        ),
        transport=httpx.MockTransport(_handler),
        url_rewriter=_proxying_rewriter,
    )

    plans = adapter.resolve_assets(_VENUE, _paper(), session=_session())

    assert plans and plans[0].kind is AssetKind.PDF
    assert seen["doi.org"] is None
    assert "ezproxy=proxy-secret" in (seen[_PROXY_HOST] or "")
    assert "platform-secret" not in (seen[_PROXY_HOST] or "")


def test_fetch_applies_rewriter_to_plan_url_directly() -> None:
    """fetch 侧同一 seam 生效（`_authed_get` 唯一收口的必然结果）：即便这次 `plan.url` 未经
    pipeline `stages._proxy_rewritten` 预先改写（adapter 单测天然不过 pipeline），adapter
    自己的 rewriter 仍把它改到代理域——两处施加各自独立，谁先谁后都不改变最终落点
    （`EZProxyProvider.rewrite_url` 对已改写 host 幂等，adapter 不需要判断"谁先改过"）。"""
    seen: dict[str, str | None] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        seen[request.url.host] = request.headers.get("cookie")
        return httpx.Response(200, content=MINIMAL_PDF, headers={"content-type": "application/pdf"})

    adapter = OupSilverchairAdapter(
        cookie_supplier=host_scoped_cookie_supplier({_PROXY_HOST: _PROXY_COOKIES}),
        transport=httpx.MockTransport(_handler),
        url_rewriter=_proxying_rewriter,
    )

    result = adapter.fetch_asset(_pdf_plan(), FakeFetchIO(), session=_session())  # 平台域 URL

    assert result.ok is True
    assert _PROXY_HOST in seen
    assert "academic.oup.com" not in seen
    assert "ezproxy=proxy-secret" in (seen[_PROXY_HOST] or "")


def test_rewritten_target_falls_back_when_doi_org_gives_no_redirect() -> None:
    """探路响应不是"合式的 3xx+Location"（如 doi.org 直接 200，异常形态）→ `_rewritten_target`
    退回原 URL，不强行拼一个不存在的改写目标；`_authed_get` 的终请求自然复现该异常状态
    （此处退化为该 200 页面本身被拿去 classify/解析，0 个 PDF 链接 → PARSE）。"""

    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "doi.org"
        return httpx.Response(200, content=b"<html><body>doi.org itself, no redirect</body></html>")

    adapter = OupSilverchairAdapter(
        cookie_supplier=static_cookie_supplier(),
        transport=httpx.MockTransport(_handler),
        url_rewriter=_proxying_rewriter,
    )

    with pytest.raises(CrawlerError) as exc:
        adapter.resolve_assets(_VENUE, _paper(), session=_session())
    assert exc.value.error_class is ErrorClass.PARSE


def test_resolve_with_rewriter_still_emits_exactly_one_obslog_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R3f 的手工两段式探路不打破"只记终点这一条"的既有口径（同
    `test_authed_get_emits_obslog_event_for_resolve_fetch_and_healthcheck` 的断言粒度）——
    doi.org 探路请求物理发生但不产生 obslog 事件，resolve 仍恰产 1 条，且其 `domain` 字段
    是改写后的代理域（真正记账的终请求落点）。"""
    events: list[dict[str, object]] = []

    def _fake_log_event(level: str, msg: str, **fields: object) -> None:
        events.append({"level": level, "msg": msg, **fields})

    monkeypatch.setattr(adapter_module, "log_event", _fake_log_event)

    def _handler(request: httpx.Request) -> httpx.Response:
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

    adapter = OupSilverchairAdapter(
        cookie_supplier=static_cookie_supplier(),
        transport=httpx.MockTransport(_handler),
        url_rewriter=_proxying_rewriter,
    )

    adapter.resolve_assets(_VENUE, _paper(), session=_session())

    assert [event["stage"] for event in events] == ["resolve"]
    assert events[0]["domain"] == _PROXY_HOST


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
