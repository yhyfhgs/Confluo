"""`ChallengeDetector` 四态判定单测（auth-framework §11；T1a）。

每态 ≥2 用例 + 边界（正常页不误判 / 特征命中即 CHALLENGE / 守卫条件）。
fixture 为模块内最小 HTML 片段常量（任务卡口径）；OUP 真实脱敏样本归 T4
（oup-silverchair.md §8 四类 fixture）。判定器为纯防御分类——用例中不存在
任何"绕过后重试成功"形态（AC-0.2/AC-4.6）。
"""

import pytest

from paper_crawler.auth.challenge import ChallengeDetector, ClassifyResult

DETECTOR = ChallengeDetector()

ARTICLE_URL = "https://academic.oup.com/qje/article/141/3/2205/8662148"

# ---- 最小 HTML 片段常量（合成；结构对齐 R0 勘察记录的特征，无真实凭证/个人信息）----

# 风控页（R0 [LIVE 2026-07-23] O2：403 + cf-mitigated: challenge + "Just a moment…"）
CLOUDFLARE_INTERSTITIAL = (
    b"<html><head><title>Just a moment...</title></head>"
    b'<body><script src="/cdn-cgi/challenge-platform/h/b/orchestrate/jsch/v1"></script>'
    b"Enable JavaScript and cookies to continue</body></html>"
)
CAPTCHA_PAGE = (
    b'<html><body><div class="g-recaptcha" data-sitekey="synthetic"></div>'
    b"Please complete the security check to access this page.</body></html>"
)
HCAPTCHA_PAGE = b'<html><body><div class="h-captcha"></div>hCaptcha verification</body></html>'
UNUSUAL_ACTIVITY_PAGE = (
    b"<html><body>We have detected unusual activity from your network.</body></html>"
)
VERIFY_HUMAN_PAGE = b"<html><body>Please verify you are human to continue.</body></html>"

# 未登录跳转落点（signin 表单页，无账号标识）
SIGNIN_PAGE = (
    b"<html><body><h1>Sign in</h1>"
    b'<form action="/signin?returnUrl=%2Fqje"><input name="username"/></form></body></html>'
)

# 无权限页（article-abstract 路由 / Get access 面板，无 PDF 链接）
ABSTRACT_ONLY_PAGE = (
    b"<html><body><section>Abstract text.</section>"
    b'<div class="access-panel">Get access</div><a href="/store">Purchase</a></body></html>'
)
PURCHASE_ONLY_PAGE = (
    b"<html><body><div>Purchase this article for institutional use.</div></body></html>"
)

# 已登录全文页（账号标识 + citation_pdf_url meta + article-pdf 链接）
FULLTEXT_PAGE = (
    b'<html><head><meta name="citation_pdf_url" '
    b'content="https://academic.oup.com/qje/article-pdf/140/2/889/61701561/qjae044.pdf"/></head>'
    b'<body><a href="/account">My Account</a><a href="/signout">Sign out</a>'
    b'<a href="/qje/article-pdf/140/2/889/61701561/qjae044.pdf">PDF</a></body></html>'
)
PLAIN_PAGE = b"<html><body><p>Journal of Things, volume 12. Editorial board.</p></body></html>"


def classify(
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
    final_url: str = ARTICLE_URL,
    body: bytes = b"",
) -> ClassifyResult:
    return DETECTOR.classify(status=status, headers=headers or {}, final_url=final_url, body=body)


# ---------------------------------------------------------------------------
# CHALLENGE（特征命中即判，绝不求解）
# ---------------------------------------------------------------------------


def test_cf_mitigated_header_alone_is_challenge() -> None:
    # R0 O2 形态：403 + 头即足够（body 无关）。
    result = classify(status=403, headers={"cf-mitigated": "challenge"}, body=PLAIN_PAGE)
    assert result is ClassifyResult.CHALLENGE


def test_cf_mitigated_header_name_case_insensitive() -> None:
    assert (
        classify(status=403, headers={"CF-Mitigated": "Challenge"}, body=b"")
        is ClassifyResult.CHALLENGE
    )


def test_cloudflare_interstitial_body_is_challenge() -> None:
    # 无质询头时 body 特征（"Just a moment"/challenge-platform）仍命中。
    assert classify(status=403, body=CLOUDFLARE_INTERSTITIAL) is ClassifyResult.CHALLENGE


@pytest.mark.parametrize(
    "body",
    [CAPTCHA_PAGE, HCAPTCHA_PAGE, UNUSUAL_ACTIVITY_PAGE, VERIFY_HUMAN_PAGE],
    ids=["recaptcha", "hcaptcha", "unusual-activity", "verify-human"],
)
def test_captcha_and_activity_signatures_are_challenge(body: bytes) -> None:
    assert classify(status=200, body=body) is ClassifyResult.CHALLENGE


def test_challenge_takes_precedence_over_login_and_entitlement_signals() -> None:
    # §11 表行序：质询特征优先于登录/权限判定。
    result = classify(
        status=302,
        headers={"cf-mitigated": "challenge"},
        final_url="https://academic.oup.com/signin",
        body=ABSTRACT_ONLY_PAGE,
    )
    assert result is ClassifyResult.CHALLENGE


def test_cf_mitigated_header_with_other_value_is_not_challenge() -> None:
    # 值精确匹配：非 "challenge" 值不触发（避免把非质询缓解动作误判为风控）。
    assert classify(status=200, headers={"cf-mitigated": "logged"}, body=PLAIN_PAGE) is (
        ClassifyResult.OK
    )


# ---------------------------------------------------------------------------
# LOGIN_REDIRECT（302 / 登录落点，且无账号标识）
# ---------------------------------------------------------------------------


def test_302_without_account_identity_is_login_redirect() -> None:
    assert classify(status=302, body=b"") is ClassifyResult.LOGIN_REDIRECT


def test_signin_final_url_is_login_redirect() -> None:
    result = classify(
        status=200,
        final_url="https://academic.oup.com/signin?returnUrl=%2Fqje%2Farticle%2F141",
        body=SIGNIN_PAGE,
    )
    assert result is ClassifyResult.LOGIN_REDIRECT


def test_shibboleth_sso_final_url_is_login_redirect() -> None:
    result = classify(
        status=200,
        final_url="https://academic.oup.com/Shibboleth.sso/Login?entityID=idp",
        body=b"",
    )
    assert result is ClassifyResult.LOGIN_REDIRECT


def test_login_url_with_account_identity_is_not_login_redirect() -> None:
    # §11 守卫："且无账号标识"——已带登录态的账号页 URL 含 /login 不误判。
    result = classify(
        status=200,
        final_url="https://academic.oup.com/my-account/login-history",
        body=FULLTEXT_PAGE,
    )
    assert result is ClassifyResult.OK


# ---------------------------------------------------------------------------
# NO_ENTITLEMENT（article-abstract 路由 / access 面板且无 PDF 链接）
# ---------------------------------------------------------------------------


def test_article_abstract_route_is_no_entitlement() -> None:
    # oup-silverchair.md §2：无权 302→/article-abstract/ 落点。
    result = classify(
        status=200,
        final_url="https://academic.oup.com/qje/article-abstract/141/3/2205/8662148",
        body=ABSTRACT_ONLY_PAGE,
    )
    assert result is ClassifyResult.NO_ENTITLEMENT


def test_get_access_panel_without_pdf_link_is_no_entitlement() -> None:
    assert classify(status=200, body=ABSTRACT_ONLY_PAGE) is ClassifyResult.NO_ENTITLEMENT


def test_purchase_panel_without_pdf_link_is_no_entitlement() -> None:
    assert classify(status=200, body=PURCHASE_ONLY_PAGE) is ClassifyResult.NO_ENTITLEMENT


def test_access_wording_with_fulltext_node_is_not_no_entitlement() -> None:
    # §11 守卫："且无 PDF 链接"——全文页顺带出现 "Purchase reprints" 类文案不误判。
    body = FULLTEXT_PAGE + b"<footer>Purchase reprints</footer>"
    assert classify(status=200, body=body) is ClassifyResult.OK


# ---------------------------------------------------------------------------
# OK（正常页不误判——零特征命中兜底 + 正例行）
# ---------------------------------------------------------------------------


def test_logged_in_fulltext_page_is_ok() -> None:
    # §11 正例行：status 200 + 账号标识 + 全文/PDF 节点。
    assert classify(status=200, body=FULLTEXT_PAGE) is ClassifyResult.OK


def test_plain_page_without_signals_is_ok() -> None:
    assert classify(status=200, body=PLAIN_PAGE) is ClassifyResult.OK


def test_empty_response_is_ok() -> None:
    assert classify(status=200, final_url="", body=b"") is ClassifyResult.OK


def test_non_utf8_body_does_not_crash_detector() -> None:
    assert classify(status=200, body=b"\xff\xfe\x00 binary junk") is ClassifyResult.OK


# ---------------------------------------------------------------------------
# 枚举面（§11 逐字四值）
# ---------------------------------------------------------------------------


def test_classify_result_members_exact() -> None:
    assert {member.value for member in ClassifyResult} == {
        "ok",
        "login_redirect",
        "no_entitlement",
        "challenge",
    }
    assert len(list(ClassifyResult)) == 4
