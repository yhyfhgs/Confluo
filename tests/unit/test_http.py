"""http.py（Phase 2 T2 冻结件 §2.1）单测：共享 HttpClient。

全部走 `httpx.MockTransport` 注入（构造参数 transport），零真实网络。覆盖：
每个 ErrorClass 映射分支、Retry-After 两形态（整数秒 / HTTP-date）、重定向跟随 +
obslog debug 事件、流式多分块、超时与连接错误、UA/Accept 头、url 脱敏、资源清理。
"""

import json
import logging
import re
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

import httpx
import pytest

from paper_crawler.errors import Challenged, CrawlerError, ErrorClass
from paper_crawler.http import HttpClient, _error_for_status
from paper_crawler.obslog import setup_logging

UA = "PaperCrawler/0.1.0 (personal research; mailto:test@example.com)"

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(autouse=True)
def _reset_paper_crawler_logger() -> Iterator[None]:
    """每个测试后关闭并清空全局 logger 的 handler，避免跨测试文件句柄泄漏。"""
    yield
    logger = logging.getLogger("paper_crawler")
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)


def make_client(handler: Handler, *, timeout_s: float = 30.0) -> HttpClient:
    """用 MockTransport 注入 handler 构造一个被测 HttpClient。"""
    return HttpClient(user_agent=UA, timeout_s=timeout_s, transport=httpx.MockTransport(handler))


def ok_text(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text="hello world")


def _read_events(log_dir: Path) -> list[dict[str, object]]:
    files = list(log_dir.glob("crawler-*.jsonl"))
    assert len(files) == 1, f"expected exactly one jsonl file, found {files}"
    lines = [ln for ln in files[0].read_text(encoding="utf-8").splitlines() if ln]
    return [json.loads(ln) for ln in lines]


# ---------------------------------------------------------------------------
# 基本 GET：文本 / 字节 / 头部
# ---------------------------------------------------------------------------


def test_get_text_returns_body() -> None:
    client = make_client(ok_text)
    assert client.get_text("https://x.local/p") == "hello world"


def test_get_bytes_returns_raw_body() -> None:
    payload = b"%PDF-1.4\nbytes"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload)

    client = make_client(handler)
    assert client.get_bytes("https://x.local/f.pdf") == payload


def test_user_agent_and_accept_headers_are_sent() -> None:
    captured: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["ua"] = request.headers.get("user-agent")
        captured["accept"] = request.headers.get("accept")
        return httpx.Response(200, text="ok")

    client = make_client(handler)
    client.get_text("https://x.local/p", accept="application/pdf")
    assert captured["ua"] == UA
    assert captured["accept"] == "application/pdf"


def test_user_agent_sent_on_stream_requests() -> None:
    captured: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["ua"] = request.headers.get("user-agent")
        return httpx.Response(200, content=b"data")

    client = make_client(handler)
    list(client.stream("https://x.local/f"))
    assert captured["ua"] == UA


# ---------------------------------------------------------------------------
# extra_headers（plan §7-4 冻结扩展）：client 级附加头，纯附加带默认值
# ---------------------------------------------------------------------------


def test_extra_headers_are_sent_on_every_request() -> None:
    """`extra_headers` 注入的 client 级头随每次请求发出（openreview token cookie 通道）。"""
    captured: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.headers.get("cookie"))
        return httpx.Response(200, text="ok")

    client = HttpClient(
        user_agent=UA,
        transport=httpx.MockTransport(handler),
        extra_headers={"Cookie": "openreview.accessToken=SEKRET_TOKEN"},
    )
    client.get_text("https://api2.openreview.net/notes?content.venueid=X")
    client.get_bytes("https://api2.openreview.net/groups?id=Y")
    assert captured == [
        "openreview.accessToken=SEKRET_TOKEN",
        "openreview.accessToken=SEKRET_TOKEN",
    ]


def test_extra_headers_are_sent_on_stream_requests() -> None:
    """流式取回（PDF 下载）同样携带 client 级附加头。"""
    captured: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.headers.get("cookie"))
        return httpx.Response(200, content=b"%PDF-1.7\nx")

    client = HttpClient(
        user_agent=UA,
        transport=httpx.MockTransport(handler),
        extra_headers={"Cookie": "openreview.accessToken=T"},
    )
    list(client.stream("https://openreview.net/pdf?id=abc"))
    assert captured == ["openreview.accessToken=T"]


def test_extra_headers_default_none_keeps_user_agent_only() -> None:
    """缺省 `extra_headers=None`：只发 UA，无附加头（扩展前行为不变）。"""
    captured: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["ua"] = request.headers.get("user-agent")
        captured["cookie"] = request.headers.get("cookie")
        return httpx.Response(200, text="ok")

    client = make_client(handler)
    client.get_text("https://x.local/p")
    assert captured["ua"] == UA
    assert captured["cookie"] is None


def test_extra_headers_coexist_with_user_agent() -> None:
    """附加头与 UA 并存：既发 UA 也发附加头（纯附加，互不覆盖）。"""
    captured: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["ua"] = request.headers.get("user-agent")
        captured["cookie"] = request.headers.get("cookie")
        return httpx.Response(200, text="ok")

    client = HttpClient(
        user_agent=UA,
        transport=httpx.MockTransport(handler),
        extra_headers={"Cookie": "openreview.accessToken=T"},
    )
    client.get_text("https://api2.openreview.net/notes")
    assert captured["ua"] == UA
    assert captured["cookie"] == "openreview.accessToken=T"


# ---------------------------------------------------------------------------
# 流式分块（多 chunk）
# ---------------------------------------------------------------------------


def test_stream_yields_multiple_chunks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        def gen() -> Iterator[bytes]:
            yield b"AAAA"
            yield b"BBBB"
            yield b"CCCC"

        return httpx.Response(200, content=gen())

    client = make_client(handler)
    chunks = list(client.stream("https://x.local/f"))
    assert len(chunks) >= 2
    assert b"".join(chunks) == b"AAAABBBBCCCC"


def test_stream_result_is_iterator() -> None:
    client = make_client(lambda request: httpx.Response(200, content=b"xy"))
    stream = client.stream("https://x.local/f")
    assert iter(stream) is not None
    assert b"".join(stream) == b"xy"


# ---------------------------------------------------------------------------
# 错误映射表（§2.1 冻结）
# ---------------------------------------------------------------------------


def _status_handler(status: int, *, headers: dict[str, str] | None = None) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers or {}, text="err")

    return handler


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, ErrorClass.AUTH_EXPIRED),
        (403, ErrorClass.NO_ENTITLEMENT),
        (404, ErrorClass.GONE),
        (410, ErrorClass.GONE),
        (451, ErrorClass.GONE),  # 法律不可用（Unavailable For Legal Reasons）= 资源终态
        (500, ErrorClass.TRANSIENT),
        (502, ErrorClass.TRANSIENT),
        (504, ErrorClass.TRANSIENT),
    ],
)
def test_status_maps_to_error_class(status: int, expected: ErrorClass) -> None:
    client = make_client(_status_handler(status))
    with pytest.raises(CrawlerError) as exc_info:
        client.get_text("https://x.local/p")
    assert exc_info.value.error_class is expected


@pytest.mark.parametrize("status", [400, 405, 406])
def test_other_4xx_maps_to_config(status: int) -> None:
    """未列入冻结表的其余 4xx → CONFIG：请求构造缺陷（如 arxiv offset>30000→400）应
    响亮停机（CONFIG 经 pipeline 特判转 BLOCKED），而非误标资源终态。"""
    client = make_client(_status_handler(status))
    with pytest.raises(CrawlerError) as exc_info:
        client.get_text("https://x.local/p")
    assert exc_info.value.error_class is ErrorClass.CONFIG


# ---------------------------------------------------------------------------
# status_code 携带（纯附加，auth-framework §6 / 检查单 #4）：映射不变，额外带原始 status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, ErrorClass.AUTH_EXPIRED),
        (403, ErrorClass.NO_ENTITLEMENT),
        (404, ErrorClass.GONE),
        (410, ErrorClass.GONE),
        (451, ErrorClass.GONE),
        (500, ErrorClass.TRANSIENT),
        (502, ErrorClass.TRANSIENT),
        (429, ErrorClass.RATE_LIMITED),
        (400, ErrorClass.CONFIG),
        (405, ErrorClass.CONFIG),
        (402, ErrorClass.CONFIG),  # 402 落"其余 4xx→CONFIG"，但携 status_code 供上层重分类
    ],
)
def test_mapped_error_carries_status_code(status: int, expected: ErrorClass) -> None:
    """各状态码映射为对应 ErrorClass **且** `status_code` 携带原始 status（映射表本身不变）。"""
    client = make_client(_status_handler(status))
    with pytest.raises(CrawlerError) as exc_info:
        client.get_text("https://x.local/p")
    assert exc_info.value.error_class is expected
    assert exc_info.value.status_code == status


def test_402_maps_config_but_carries_status_code_402() -> None:
    """检查单 #4 闭合：402 credit 耗尽仍映射 CONFIG（冻结表不改），但 status_code=402 供
    openalex 等上层经 `exc.status_code == 402` 精确重分类（不再靠异常消息文本嗅探）。"""
    client = make_client(_status_handler(402))
    with pytest.raises(CrawlerError) as exc_info:
        client.get_text("https://api.openalex.org/works")
    assert exc_info.value.error_class is ErrorClass.CONFIG
    assert exc_info.value.status_code == 402


def test_503_with_retry_after_carries_status_code() -> None:
    client = make_client(_status_handler(503, headers={"Retry-After": "30"}))
    with pytest.raises(CrawlerError) as exc_info:
        client.get_text("https://x.local/p")
    assert exc_info.value.error_class is ErrorClass.RATE_LIMITED
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "retry_after_s=30"


def test_transport_errors_have_no_status_code() -> None:
    """超时/连接错是非 HTTP 来源 → status_code 恒 None（`== <int>` 判据天然不误命中）。"""

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    with pytest.raises(CrawlerError) as exc_info:
        make_client(timeout_handler).get_text("https://x.local/p")
    assert exc_info.value.status_code is None

    def conn_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(CrawlerError) as exc_info:
        make_client(conn_handler).get_text("https://x.local/p")
    assert exc_info.value.status_code is None


def test_429_maps_to_rate_limited() -> None:
    client = make_client(_status_handler(429))
    with pytest.raises(CrawlerError) as exc_info:
        client.get_text("https://x.local/p")
    assert exc_info.value.error_class is ErrorClass.RATE_LIMITED


def test_get_bytes_maps_error_status() -> None:
    client = make_client(_status_handler(500))
    with pytest.raises(CrawlerError) as exc_info:
        client.get_bytes("https://x.local/p")
    assert exc_info.value.error_class is ErrorClass.TRANSIENT


def test_stream_maps_error_status_on_iteration() -> None:
    client = make_client(_status_handler(404))
    with pytest.raises(CrawlerError) as exc_info:
        list(client.stream("https://x.local/p"))
    assert exc_info.value.error_class is ErrorClass.GONE


# ---------------------------------------------------------------------------
# Retry-After 解析（整数秒 / HTTP-date），仅写入 detail，不做内部等待
# ---------------------------------------------------------------------------


def test_429_retry_after_integer_seconds_in_detail() -> None:
    client = make_client(_status_handler(429, headers={"Retry-After": "120"}))
    with pytest.raises(CrawlerError) as exc_info:
        client.get_text("https://x.local/p")
    assert exc_info.value.error_class is ErrorClass.RATE_LIMITED
    assert exc_info.value.detail == "retry_after_s=120"


def test_429_without_retry_after_omits_detail_segment() -> None:
    client = make_client(_status_handler(429))
    with pytest.raises(CrawlerError) as exc_info:
        client.get_text("https://x.local/p")
    assert exc_info.value.error_class is ErrorClass.RATE_LIMITED
    assert exc_info.value.detail == ""


def test_429_retry_after_http_date_in_detail() -> None:
    future = datetime.now(UTC) + timedelta(seconds=3600)
    header = format_datetime(future, usegmt=True)
    client = make_client(_status_handler(429, headers={"Retry-After": header}))
    with pytest.raises(CrawlerError) as exc_info:
        client.get_text("https://x.local/p")
    assert exc_info.value.error_class is ErrorClass.RATE_LIMITED
    assert exc_info.value.detail.startswith("retry_after_s=")
    seconds = int(exc_info.value.detail.removeprefix("retry_after_s="))
    assert 3590 <= seconds <= 3600


def test_retry_after_http_date_in_past_clamps_to_zero() -> None:
    past = datetime.now(UTC) - timedelta(seconds=500)
    header = format_datetime(past, usegmt=True)
    client = make_client(_status_handler(429, headers={"Retry-After": header}))
    with pytest.raises(CrawlerError) as exc_info:
        client.get_text("https://x.local/p")
    assert exc_info.value.detail == "retry_after_s=0"


def test_retry_after_http_date_without_zone_treated_as_utc() -> None:
    """无时区的 HTTP-date（`-0000` 形态解析为 naive）按 UTC 兜底换算。"""
    future = datetime.now(UTC) + timedelta(seconds=1800)
    header = future.strftime("%a, %d %b %Y %H:%M:%S -0000")
    client = make_client(_status_handler(429, headers={"Retry-After": header}))
    with pytest.raises(CrawlerError) as exc_info:
        client.get_text("https://x.local/p")
    seconds = int(exc_info.value.detail.removeprefix("retry_after_s="))
    assert 1790 <= seconds <= 1800


def test_retry_after_garbage_value_is_ignored() -> None:
    client = make_client(_status_handler(429, headers={"Retry-After": "not-a-date"}))
    with pytest.raises(CrawlerError) as exc_info:
        client.get_text("https://x.local/p")
    assert exc_info.value.error_class is ErrorClass.RATE_LIMITED
    assert exc_info.value.detail == ""


def test_retry_after_non_ascii_digit_header_does_not_raise_bare_exception() -> None:
    """畸形 Retry-After：非 ASCII 数字字符（latin-1 `²`，`str.isdigit()` 为 True 但
    `int()` 抛 ValueError）不得逃逸为裸异常——仍须产出 RATE_LIMITED 且省略 detail 段。"""

    def handler(request: httpx.Request) -> httpx.Response:
        # 以原始 latin-1 字节注入（服务端在线上即这样发 header 字节，httpx 按 latin-1
        # 解回字符串 "²"）；用 str 传会被 httpx ascii 编码拒绝，无法复现该畸形。
        return httpx.Response(429, headers=[(b"Retry-After", b"\xb2")], text="err")

    client = make_client(handler)
    with pytest.raises(CrawlerError) as exc_info:
        client.get_text("https://x.local/p")
    assert exc_info.value.error_class is ErrorClass.RATE_LIMITED
    assert exc_info.value.detail == ""


def test_503_with_retry_after_maps_to_rate_limited() -> None:
    client = make_client(_status_handler(503, headers={"Retry-After": "30"}))
    with pytest.raises(CrawlerError) as exc_info:
        client.get_text("https://x.local/p")
    assert exc_info.value.error_class is ErrorClass.RATE_LIMITED
    assert exc_info.value.detail == "retry_after_s=30"


def test_503_without_retry_after_maps_to_transient() -> None:
    client = make_client(_status_handler(503))
    with pytest.raises(CrawlerError) as exc_info:
        client.get_text("https://x.local/p")
    assert exc_info.value.error_class is ErrorClass.TRANSIENT
    assert exc_info.value.detail == ""


# ---------------------------------------------------------------------------
# 传输层异常：超时 / 连接错 → TRANSIENT
# ---------------------------------------------------------------------------


def test_timeout_maps_to_transient() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    client = make_client(handler)
    with pytest.raises(CrawlerError) as exc_info:
        client.get_text("https://x.local/p")
    assert exc_info.value.error_class is ErrorClass.TRANSIENT
    assert exc_info.value.detail == "timeout"


def test_read_timeout_maps_to_transient() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = make_client(handler)
    with pytest.raises(CrawlerError) as exc_info:
        client.get_bytes("https://x.local/p")
    assert exc_info.value.error_class is ErrorClass.TRANSIENT
    assert exc_info.value.detail == "timeout"


def test_connection_error_maps_to_transient() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = make_client(handler)
    with pytest.raises(CrawlerError) as exc_info:
        client.get_text("https://x.local/p")
    assert exc_info.value.error_class is ErrorClass.TRANSIENT
    assert exc_info.value.detail == "ConnectError"


def test_stream_connection_error_maps_to_transient() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = make_client(handler)
    with pytest.raises(CrawlerError) as exc_info:
        list(client.stream("https://x.local/p"))
    assert exc_info.value.error_class is ErrorClass.TRANSIENT


def test_stream_timeout_maps_to_transient() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = make_client(handler)
    with pytest.raises(CrawlerError) as exc_info:
        list(client.stream("https://x.local/p"))
    assert exc_info.value.error_class is ErrorClass.TRANSIENT
    assert exc_info.value.detail == "timeout"


# ---------------------------------------------------------------------------
# 重定向默认跟随 + obslog debug 事件
# ---------------------------------------------------------------------------


def _redirect_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/start":
        return httpx.Response(302, headers={"Location": "https://x.local/final"})
    return httpx.Response(200, text="arrived")


def test_redirect_is_followed_by_default() -> None:
    client = make_client(_redirect_handler)
    assert client.get_text("https://x.local/start") == "arrived"


def test_redirect_emits_debug_events_for_hop_and_final(tmp_path: Path) -> None:
    setup_logging(tmp_path)
    client = make_client(_redirect_handler)
    client.get_text("https://x.local/start")

    events = _read_events(tmp_path)
    statuses = [(ev.get("status"), ev.get("url")) for ev in events]
    assert (302, "https://x.local/start") in statuses
    assert (200, "https://x.local/final") in statuses
    # 全部 obslog 事件都是 debug 级
    assert all(ev.get("level") == "DEBUG" for ev in events)


def test_redirect_hop_event_omits_elapsed_ms_final_event_includes_it(tmp_path: Path) -> None:
    """重定向跳事件不含 elapsed_ms（httpx history 响应 .elapsed 不可靠取用），
    终响应事件含实测 elapsed_ms——钉死 concern #4 的实现契约。"""
    setup_logging(tmp_path)
    client = make_client(_redirect_handler)
    client.get_text("https://x.local/start")

    events = _read_events(tmp_path)
    hop_event = next(ev for ev in events if ev.get("status") == 302)
    final_event = next(ev for ev in events if ev.get("status") == 200)
    # obslog 省略 None 值键：跳事件 elapsed_ms=None → 键缺席；终事件带实测值 → 键在场。
    assert "elapsed_ms" not in hop_event
    assert "elapsed_ms" in final_event
    assert isinstance(final_event["elapsed_ms"], int | float)


# ---------------------------------------------------------------------------
# obslog：每次请求一条 debug 事件（domain / url 脱敏 / status / elapsed_ms）
# ---------------------------------------------------------------------------


def test_request_emits_debug_event_with_required_fields(tmp_path: Path) -> None:
    setup_logging(tmp_path)
    client = make_client(ok_text)
    client.get_text("https://api.local/paper/42")

    events = _read_events(tmp_path)
    assert len(events) == 1
    event = events[0]
    assert event["level"] == "DEBUG"
    assert event["domain"] == "api.local"
    assert event["url"] == "https://api.local/paper/42"
    assert event["status"] == 200
    assert isinstance(event["elapsed_ms"], int | float)
    assert event["elapsed_ms"] >= 0


def test_error_response_still_emits_debug_event(tmp_path: Path) -> None:
    setup_logging(tmp_path)
    client = make_client(_status_handler(404))
    with pytest.raises(CrawlerError):
        client.get_text("https://api.local/missing")

    events = _read_events(tmp_path)
    assert len(events) == 1
    assert events[0]["status"] == 404


def test_stream_emits_debug_event(tmp_path: Path) -> None:
    setup_logging(tmp_path)
    client = make_client(lambda request: httpx.Response(200, content=b"data"))
    list(client.stream("https://api.local/f"))

    events = _read_events(tmp_path)
    assert len(events) == 1
    assert events[0]["status"] == 200
    assert events[0]["domain"] == "api.local"


def test_debug_event_url_is_redacted(tmp_path: Path) -> None:
    setup_logging(tmp_path)
    client = make_client(ok_text)
    client.get_text("https://api.local/x?token=SEKRET&q=1")

    events = _read_events(tmp_path)
    url = str(events[0]["url"])
    assert "SEKRET" not in url
    assert "token=***" in url


# ---------------------------------------------------------------------------
# 资源清理：close / context manager
# ---------------------------------------------------------------------------


def test_close_is_idempotent() -> None:
    client = make_client(ok_text)
    client.close()
    client.close()


def test_context_manager_closes_client() -> None:
    with make_client(ok_text) as client:
        assert client.get_text("https://x.local/p") == "hello world"
    assert client.is_closed


def test_custom_timeout_still_serves_requests() -> None:
    client = make_client(ok_text, timeout_s=5.0)
    assert client.get_text("https://x.local/p") == "hello world"


# ---------------------------------------------------------------------------
# 逐请求限速闸（C4 红线修复，plan §7-6）：每请求发出前 acquire(host)+按需 sleep
# ---------------------------------------------------------------------------


class _SpyLimiter:
    """记账每次 `acquire` 的 domain（并可返回预设 wait），用于断言逐请求限速。

    只需 `acquire(domain)->float`——`HttpClient._throttle` 只调这一个方法（鸭子类型；
    tests 不受 `mypy src` 约束，无需是真正的 `RateLimiter`）。
    """

    def __init__(self, wait: float = 0.0) -> None:
        self.calls: list[str] = []
        self._wait = wait

    def acquire(self, domain: str) -> float:
        self.calls.append(domain)
        return self._wait


def test_no_rate_limiter_means_no_throttle() -> None:
    """未注入 limiter（默认 None）：行为与限速前完全一致，不触任何 acquire。"""
    client = HttpClient(user_agent=UA, transport=httpx.MockTransport(ok_text))
    assert client.get_text("https://x.local/p") == "hello world"


def test_rate_limiter_acquires_once_per_request_on_request_host() -> None:
    """逐请求限速：每次 GET 发出前对**请求 host** acquire 一次（多请求逐一记账）。"""
    spy = _SpyLimiter()
    client = HttpClient(user_agent=UA, transport=httpx.MockTransport(ok_text), rate_limiter=spy)

    client.get_text("https://export.arxiv.org/api/query?a=1")
    client.get_bytes("https://oaipmh.arxiv.org/oai?verb=ListRecords")
    client.get_text("https://export.arxiv.org/api/query?a=2")

    assert spy.calls == ["export.arxiv.org", "oaipmh.arxiv.org", "export.arxiv.org"]


def test_rate_limiter_sleeps_when_acquire_returns_positive_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """acquire 返回正 wait 时真实 sleep 该秒数（限速在 HttpClient 层生效，非仅计数）。"""
    slept: list[float] = []
    monkeypatch.setattr("paper_crawler.http.time.sleep", lambda s: slept.append(s))
    spy = _SpyLimiter(wait=3.0)
    client = HttpClient(user_agent=UA, transport=httpx.MockTransport(ok_text), rate_limiter=spy)

    client.get_text("https://export.arxiv.org/api/query")

    assert slept == [3.0]


def test_rate_limiter_does_not_sleep_when_wait_is_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """wait=0（token 立即可用）时不 sleep——避免无谓的 sleep(0) 调度开销。"""
    slept: list[float] = []
    monkeypatch.setattr("paper_crawler.http.time.sleep", lambda s: slept.append(s))
    spy = _SpyLimiter(wait=0.0)
    client = HttpClient(user_agent=UA, transport=httpx.MockTransport(ok_text), rate_limiter=spy)

    client.get_text("https://export.arxiv.org/api/query")

    assert slept == []


def test_stream_throttles_once_per_logical_request() -> None:
    """流式取回同样过限速闸：一次 `stream()` = 一次 acquire（首次迭代前触发）。"""
    spy = _SpyLimiter()

    def pdf_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"%PDF-1.5\nx")

    client = HttpClient(user_agent=UA, transport=httpx.MockTransport(pdf_handler), rate_limiter=spy)
    chunks = list(client.stream("https://arxiv.org/pdf/2401.00001"))

    assert b"".join(chunks) == b"%PDF-1.5\nx"
    assert spy.calls == ["arxiv.org"]


# ---------------------------------------------------------------------------
# T-6：CF-403 判定演进 S-c（D-030 裁决②；11-browser-fetch §5.4/§8 T-6）
#
# 改判面严格限于「403 **且** 响应头 `cf-mitigated: challenge`」——真实 Cloudflare
# 判罚形态（[LIVE 2026-07-24] aea pubs / [LIVE 2026-07-23] OUP QJE）。其余一切 403
# 维持 NO_ENTITLEMENT **逐字不变**（wiley TDM 无权 / 机构无订阅 / github 配额 403…），
# 由下方三形态用例 + 全库 fixture 等值扫描（权威）+ 内联 mock 启发式扫描（辅助）
# 共同回归锁定。
# ---------------------------------------------------------------------------

_CF_HEADERS = {"cf-mitigated": "challenge"}
_FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures"
_TESTS_ROOT = Path(__file__).resolve().parents[1]


def _parse_http_fixture(path: Path) -> tuple[int, dict[str, str], bytes]:
    """解析 `.http` 快照 → `(status, headers, body)`（全库 fixture 通用约定：`#` 注释行、
    `HTTP-STATUS: <int>` 声明状态码、其余 `Key: Value` 为响应头、首个空行后为 body）。"""
    raw = path.read_bytes()
    head, sep, body = raw.partition(b"\n\n")
    if not sep:
        return 200, {}, raw
    status = 200
    headers: dict[str, str] = {}
    for line in head.decode("utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, _, value = stripped.partition(":")
        key, value = key.strip(), value.strip()
        if key.upper() == "HTTP-STATUS":
            status = int(value)
        else:
            headers[key] = value
    return status, headers, body


# --- 三形态（§8 T-6 主表）------------------------------------------------------


def test_t6_form1_cf_403_maps_challenge() -> None:
    """形态①：403 + `cf-mitigated: challenge` → `Challenged`（error_class=CHALLENGE）。"""
    client = make_client(_status_handler(403, headers=_CF_HEADERS))
    with pytest.raises(Challenged) as exc_info:
        client.get_text("https://pubs.aeaweb.org/doi/pdfplus/10.1257/jep.20251473")
    assert exc_info.value.error_class is ErrorClass.CHALLENGE
    assert exc_info.value.detail == "cf_challenge"


def test_t6_form1_cf_403_on_stream_path_too() -> None:
    """流式取回路径共用同一 `_error_for_status`——改判在 fetch(stream) 上同样生效。"""
    client = make_client(_status_handler(403, headers=_CF_HEADERS))
    with pytest.raises(Challenged):
        list(client.stream("https://pubs.aeaweb.org/doi/pdfplus/10.1257/jep.20251473"))


def test_t6_form1_cf_403_header_match_is_case_insensitive() -> None:
    """头名/值大小写不敏感（判定复用 `ChallengeDetector` 的小写化精确比对）。"""
    client = make_client(_status_handler(403, headers={"CF-Mitigated": "Challenge"}))
    with pytest.raises(Challenged):
        client.get_text("https://academic.oup.com/qje/article/1/1/1/1")


def test_t6_form2_plain_403_stays_no_entitlement() -> None:
    """形态②：403 **无** CF 头 → NO_ENTITLEMENT 逐字不变（类型/消息/status_code 均不变）。"""
    client = make_client(_status_handler(403))
    with pytest.raises(CrawlerError) as exc_info:
        client.get_text("https://x.local/p")
    assert type(exc_info.value) is CrawlerError  # 非 Challenged 子类
    assert exc_info.value.error_class is ErrorClass.NO_ENTITLEMENT
    assert exc_info.value.status_code == 403
    assert str(exc_info.value) == "HTTP 403 for https://x.local/p"


def test_t6_form2_cf_mitigated_other_value_stays_no_entitlement() -> None:
    """`cf-mitigated` 值非 `challenge`（如 `logged`）→ 不改判——精确相等而非子串。"""
    client = make_client(_status_handler(403, headers={"cf-mitigated": "logged"}))
    with pytest.raises(CrawlerError) as exc_info:
        client.get_text("https://x.local/p")
    assert exc_info.value.error_class is ErrorClass.NO_ENTITLEMENT


def test_t6_form3_wiley_tdm_403_stays_no_entitlement() -> None:
    """形态③（回归锁定）：wiley TDM 403 真实形态（`api.wiley.com` 无 CF 前置，不携该头）
    → NO_ENTITLEMENT 不变；wiley.md §5 第 2 行与 adapter 的 OA 兜底链均依赖此语义。"""
    status, headers, body = _parse_http_fixture(
        _FIXTURE_ROOT / "wiley" / "03_tdm_403_no_entitlement.http"
    )
    assert status == 403 and "cf-mitigated" not in {k.lower() for k in headers}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers, content=body)

    client = make_client(handler)
    with pytest.raises(CrawlerError) as exc_info:
        client.get_bytes("https://api.wiley.com/onlinelibrary/tdm/v1/articles/10.1111%2Fecta.12058")
    assert exc_info.value.error_class is ErrorClass.NO_ENTITLEMENT
    assert exc_info.value.status_code == 403


# --- 全库零翻转扫描：§5.4 兼容性论证的机器化复核 ---------------------------------

# 全库**唯一**两个携 `cf-mitigated: challenge` 的 403 fixture。二者**都不经共享
# HttpClient 消费**，故 S-c 对既有行为零影响：
#   - oup_silverchair/01：oup adapter 用**专属 httpx.Client**（凭证隔离 + 需读挑战页
#     body，见其模块 docstring"为何不复用共享 HttpClient"），直喂 `ChallengeDetector`；
#   - aea/01：`test_aea_fixtures.py` 直喂 `ChallengeDetector`（aea adapter 零网络）。
# 两者本就判 CHALLENGE，S-c 只是让**共享 HttpClient 路径**也得到同一结论。
_CF_403_FIXTURES = frozenset(
    {
        "aea/01_challenge_cf_mitigated.http",
        "oup_silverchair/01_challenge_cf_mitigated.http",
    }
)

# 构造内联 `httpx.Response(403, …cf-mitigated…)` 的测试文件白名单：
#   - `integration/conftest.py` / `unit/test_auth_providers.py`：auth provider 的探针路径
#     （`CookieSessionProvider`/`SSOFlowProvider` 自持 httpx.Client + `ChallengeDetector`），
#     **不经** `HttpClient` 错误映射 ⇒ 零翻转（本就判 CHALLENGE）；
#   - `integration/test_cf403_cooldown.py`：S-c 改判**本身**的端到端用例（期望 CHALLENGE）。
# 新增条目须先论证它不落在期望 NO_ENTITLEMENT 的面上。
_INLINE_CF_403_ALLOWLIST = frozenset(
    {
        "integration/conftest.py",
        "integration/test_cf403_cooldown.py",
        "unit/test_auth_providers.py",
    }
)


def _all_403_fixtures() -> list[tuple[str, dict[str, str], bytes]]:
    """全库 `.http` fixture 中**全部** 403 用例（相对路径, headers, body）。"""
    found: list[tuple[str, dict[str, str], bytes]] = []
    for path in sorted(_FIXTURE_ROOT.rglob("*.http")):
        status, headers, body = _parse_http_fixture(path)
        if status == 403:
            found.append((path.relative_to(_FIXTURE_ROOT).as_posix(), headers, body))
    return found


def test_t6_scan_finds_the_expected_403_fixture_corpus() -> None:
    """扫描器自证不空跑（防"扫了 0 条也绿"的假通过）：全库 403 fixture 恰这 5 条。"""
    names = {name for name, _, _ in _all_403_fixtures()}
    assert names == {
        "acl_anthology/08_github_403.http",
        "aea/01_challenge_cf_mitigated.http",
        "openreview/06_challenge_403.http",
        "oup_silverchair/01_challenge_cf_mitigated.http",
        "wiley/03_tdm_403_no_entitlement.http",
    }


def test_t6_full_repo_403_fixture_scan_zero_flip() -> None:
    """全库 403 fixture 逐条过新映射：改判集合**恰好**等于两个 CF 挑战 fixture，
    其余全部维持 NO_ENTITLEMENT（且仍携 status_code=403）。

    ⚠ 本断言若失败即意味着"某个期望 NO_ENTITLEMENT 的既有用例被 S-c 翻转"——
    D-030 兼容性论证的前提被破坏，必须停手复核而非放宽断言。
    """
    flipped: set[str] = set()
    for name, headers, body in _all_403_fixtures():
        response = httpx.Response(
            403,
            headers=headers,
            content=body,
            request=httpx.Request("GET", "https://fixture.local/probe"),
        )
        error = _error_for_status(response)
        if error.error_class is ErrorClass.CHALLENGE:
            flipped.add(name)
            continue
        assert error.error_class is ErrorClass.NO_ENTITLEMENT, name
        assert error.status_code == 403, name
    assert flipped == set(_CF_403_FIXTURES)


def test_t6_inline_403_challenge_mocks_are_allowlisted() -> None:
    """测试源码里内联构造的 `httpx.Response(403, …cf-mitigated…)` 集合冻结在白名单内。

    **定位：辅助护栏，非权威判据。** 零翻转的权威复核是上一测（`_all_403_fixtures`
    等值扫描——解析真实响应、跑真实映射）。本测只是正则 + 300 字符窗的**启发式**
    tripwire：它按文本近似判断"这个 403 mock 带不带 CF 头"，既会被跨窗写法漏掉
    （头声明离构造点太远、头存于变量、经 `MockTransport` 间接构造），也会被散文
    注释误命中。它的价值只在于：**新增一处内联 403+CF mock 时集合变化 → 失败 →
    强制作者论证它不落在期望 NO_ENTITLEMENT 的面上**，不能据此宣称"全库无遗漏"。
    """
    pattern = re.compile(r"httpx\.Response\(\s*403\b")
    self_path = Path(__file__).resolve()
    found: set[str] = set()
    for path in sorted(_TESTS_ROOT.rglob("*.py")):
        if path == self_path:
            # 自排除：本文件既有**真实** 403 构造（`_all_403_fixtures` 扫描用，窗内无 CF 头），
            # 也在散文注释里字面写出 `httpx.Response(403, …cf-mitigated…)` 形态——后者会被
            # 正则+窗口误命中（扫描器自指）。本文件自身的 403 语义由同段其余用例直接断言。
            continue
        text = path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            if "cf-mitigated" in text[match.start() : match.start() + 300].lower():
                found.add(path.relative_to(_TESTS_ROOT).as_posix())
    assert found == set(_INLINE_CF_403_ALLOWLIST)
