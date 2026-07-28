"""oup_silverchair 四件套 fixture 加载器（`tests/fixtures/oup_silverchair/`）。

四件套（design/adapters/oup-silverchair.md §7）出处分级（每文件头注明）：
① `01_challenge_cf_mitigated`   [LIVE-DERIVED] 依 R0 [LIVE 2026-07-23] O2 记录构造
② `02_login_redirect_signin`    ⚠[DOCS]        合成，依详设 URL 模式
③ `03_no_entitlement_abstract`  ⚠[SYNTHETIC]   合成占位（runbook 采真实脱敏样本替换）
④ `04_fulltext_logged_in`       ⚠[SYNTHETIC]   合成占位（runbook 采真实脱敏样本替换）

``.http`` 格式（沿 neurips/arxiv fixtures 约定，扩展一个 `X-FINAL-URL` 头承载
跟随重定向后的落点 URL——`ChallengeDetector.classify` 的 `final_url` 入参）：以 ``#``
开头为注释；``HTTP-STATUS: <int>`` 声明状态码；``X-FINAL-URL: <url>`` 声明落点；其余
``Key: Value`` 为响应头；**首个空行**后为原始 body。
"""

from __future__ import annotations

from pathlib import Path

import httpx

from paper_crawler.types import SessionHandle

_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "oup_silverchair"

_FINAL_URL_KEY = "x-final-url"

# 最小合成 PDF（首字节 %PDF- 魔数，供 fetch 成功路径的魔数断言）。
MINIMAL_PDF = b"%PDF-1.7\n% oup contract\n" + b"0" * 256 + b"\n%%EOF\n"

_DOI_RESOLVER_HOST = "doi.org"
_ARTICLE_PDF_MARKER = "article-pdf"


def static_cookie_supplier(cookies: dict[str, str] | None = None):
    """构造一个固定 `CookieSupplier`（离线 seam 注入）：无视 session/host、恒返回同一 cookie 表。

    默认返回一个占位 session cookie（脱敏合成值）。真实供给（读 CredentialStore 解密
    storage_state）由 T1b 落地——本替身只验 adapter 的 cookie 装配 + 域限定路径。
    host 形参（R3e 域感知）在此**刻意忽略**：本替身模拟"单域凭证"形态，域过滤的真替身
    见 `host_scoped_cookie_supplier`。
    """
    jar = dict(cookies) if cookies is not None else {"SILVERCHAIR_SESSION": "synthetic-offline"}

    def _supplier(_session: SessionHandle, _host: str) -> dict[str, str]:
        return jar

    return _supplier


def host_scoped_cookie_supplier(by_host: dict[str, dict[str, str]]):
    """构造一个**域感知** `CookieSupplier` 替身：按消费方传入的 host 返回该 host 适用的 cookie。

    模拟 `cli._cookie_supplier_for` 的真实形态——供给方持有带域信息的 jar，按请求 host
    过滤后才交出 name→value（域信息不再在 seam 上被丢弃，R3e）。`by_host` 未列的 host
    返回空表（= 该 host 无凭证，请求裸发）。
    """

    def _supplier(_session: SessionHandle, host: str) -> dict[str, str]:
        return dict(by_host.get(host, {}))

    return _supplier


def landing_transport(
    final_url: str,
    status: int,
    headers: dict[str, str],
    body: bytes,
    *,
    pdf_bytes: bytes = MINIMAL_PDF,
) -> httpx.MockTransport:
    """resolve 流的 MockTransport：`doi.org/{doi}` 302→`final_url`；落点服务四件套 fixture；
    任意 `article-pdf` 路径 → 200 `%PDF`（供 resolve→fetch 全链契约）。

    模型化 design §3.1 的 `doi.org` 首跳 + 跟随重定向落到 OUP 落地页；`final_url` 决定
    `ChallengeDetector` 的落点判定（article-abstract / signin / article）。
    """
    final = httpx.URL(final_url)

    def _handler(request: httpx.Request) -> httpx.Response:
        url = request.url
        if url.host == _DOI_RESOLVER_HOST:
            return httpx.Response(302, headers={"Location": final_url})
        if _ARTICLE_PDF_MARKER in url.path and url.path != final.path:
            return httpx.Response(
                200, content=pdf_bytes, headers={"content-type": "application/pdf"}
            )
        if url.path == final.path:
            return httpx.Response(status, headers=headers, content=body)
        return httpx.Response(404, content=b"unexpected url in oup landing mock")

    return httpx.MockTransport(_handler)


def direct_transport(
    status: int, headers: dict[str, str], body: bytes, *, redirect_to: str | None = None
) -> httpx.MockTransport:
    """fetch 流的 MockTransport：对任意（首个）请求返回 `(status, headers, body)`。

    `redirect_to` 非空时首个请求先 302→该 URL，落点再返回 `(status, headers, body)`
    （模型化 fetch 时 PDF URL 302→signin 的过期场景，落点 `final_url` 即 `redirect_to`）。
    """
    target = httpx.URL(redirect_to) if redirect_to else None

    def _handler(request: httpx.Request) -> httpx.Response:
        if target is not None and request.url.path != target.path:
            return httpx.Response(302, headers={"Location": redirect_to or ""})
        return httpx.Response(status, headers=headers, content=body)

    return httpx.MockTransport(_handler)


def oup_fixture(name: str) -> tuple[int, dict[str, str], str, bytes]:
    """解析四件套 ``.http`` → ``(status, headers, final_url, body)``。

    `name` 可省略 ``.http`` 后缀。`headers` 不含 `X-FINAL-URL`（已单列为 `final_url`）；
    `final_url` 缺省空串。见模块 docstring 的格式说明。
    """
    filename = name if name.endswith(".http") else f"{name}.http"
    raw = (_DIR / filename).read_bytes()
    head, sep, body = raw.partition(b"\n\n")
    if not sep:  # 无空行分隔——整体视为 body，200 无头无落点
        return 200, {}, "", raw

    status = 200
    final_url = ""
    headers: dict[str, str] = {}
    for line in head.decode("utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, _, value = stripped.partition(":")
        key, value = key.strip(), value.strip()
        lowered = key.lower()
        if lowered == "http-status":
            status = int(value)
        elif lowered == _FINAL_URL_KEY:
            final_url = value
        else:
            headers[key] = value
    return status, headers, final_url, body


__all__ = [
    "MINIMAL_PDF",
    "direct_transport",
    "host_scoped_cookie_supplier",
    "landing_transport",
    "oup_fixture",
    "static_cookie_supplier",
]
