"""共享 HTTP 客户端（Phase 2 T2 冻结件 §2.1）。

全部真实 adapter 共用的薄 httpx 包装。**只管**：发请求、注入 UA/超时、流式取字节、
把 HTTP 状态/异常映射为 `CrawlerError(ErrorClass)`、解析 `Retry-After` 写入 detail
供观测、每次请求落一条 obslog debug 事件。

**不管**（分层职责，见 T2 brief）：限速（`ratelimit.acquire_and_wait` 在 adapter
调用前由 pipeline 执行）、落盘（`FetchIO.write_stream` 原子写 / 魔数校验归 pipeline）、
重试调度（pipeline 按 `RETRY_TABLE` 固定退避 2/8/30s）。因此本客户端 **不做内部
重试/等待**：`Retry-After` 仅被解析成秒数写进 `CrawlerError.detail`（`retry_after_s=<n>`）
供日志观测，不据此 sleep（单一职责；限速器已把速率压到站点声明以下，实际罕见）。

错误映射表（§2.1 冻结，逐行）：
- timeout / 连接错 → TRANSIENT
- 429 → RATE_LIMITED（detail 含 `retry_after_s=<n>`，无头时省略该段）
- 5xx → TRANSIENT（503 且带 Retry-After → RATE_LIMITED）
- 401 → AUTH_EXPIRED
- 403 → NO_ENTITLEMENT
- 404 / 410 → GONE
- 其余 4xx → GONE（终态、不重试，遵 design/03 §重试 "4xx 不重试(429 除外)"）
- 重定向默认跟随（每一跳与终响应各记一条 obslog debug 事件）

`transport` 构造参数是 T4 单测注入 `httpx.MockTransport` 的唯一通道——生产传 None
即用 httpx 默认传输，测试传 MockTransport 即零真实网络。UA 由调用方（从 config 组装
D-014 格式 `PaperCrawler/<ver> (personal research; mailto:<email>)`）注入，本模块不读
config。
"""

import time
from collections.abc import Iterator
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from types import TracebackType

import httpx

from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.obslog import log_event, redact


def _parse_retry_after(response: httpx.Response) -> int | None:
    """解析 `Retry-After` 头为非负整数秒；无头或无法解析返回 None。

    两形态（RFC 9110 §10.2.3）：整数秒（`Retry-After: 120`）与 HTTP-date
    （`Retry-After: Wed, 21 Oct 2026 07:28:00 GMT`）。HTTP-date 换算为"距当前
    时刻的秒数"，过去时刻钳到 0。
    """
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    raw = raw.strip()
    if raw.isdigit():  # 纯非负整数秒
        return int(raw)
    try:
        target = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if target.tzinfo is None:  # HTTP-date 理论恒带 GMT，防御性兜底
        target = target.replace(tzinfo=UTC)
    delta = (target - datetime.now(UTC)).total_seconds()
    return max(0, int(delta))


def _error_for_status(response: httpx.Response) -> CrawlerError:
    """把 >=400 的响应状态映射为 `CrawlerError`（§2.1 冻结映射表）。"""
    status = response.status_code
    msg = f"HTTP {status} for {redact(str(response.url))}"

    if status == 429:
        return _rate_limited(response, msg)
    if status == 401:
        return CrawlerError(ErrorClass.AUTH_EXPIRED, msg)
    if status == 403:
        return CrawlerError(ErrorClass.NO_ENTITLEMENT, msg)
    if status in (404, 410):
        return CrawlerError(ErrorClass.GONE, msg)
    if status == 503:
        # 5xx→TRANSIENT，但 503 带 Retry-After 视为限流信号 → RATE_LIMITED。
        retry_after = _parse_retry_after(response)
        if retry_after is not None:
            return CrawlerError(ErrorClass.RATE_LIMITED, msg, detail=f"retry_after_s={retry_after}")
        return CrawlerError(ErrorClass.TRANSIENT, msg)
    if 500 <= status < 600:
        return CrawlerError(ErrorClass.TRANSIENT, msg)
    # 其余 4xx（400/405/406/451…）：客户端错误终态，不重试（design/03 "4xx 不重试"）。
    return CrawlerError(ErrorClass.GONE, msg)


def _rate_limited(response: httpx.Response, msg: str) -> CrawlerError:
    """429 → RATE_LIMITED；有 Retry-After 则 detail 含 `retry_after_s=<n>`，无则省略。"""
    retry_after = _parse_retry_after(response)
    detail = f"retry_after_s={retry_after}" if retry_after is not None else ""
    return CrawlerError(ErrorClass.RATE_LIMITED, msg, detail=detail)


def _log_exchange(response: httpx.Response, *, elapsed_ms: float) -> None:
    """每次请求落 obslog debug 事件：每个重定向跳 + 终响应各一条。

    重定向跳的 `elapsed` 在 httpx 中不可靠取用（未读/已释放会抛 RuntimeError），
    故跳的事件省略 elapsed_ms；终响应用调用方实测的 elapsed_ms。
    """
    for hop in response.history:
        _emit_event(hop.url, hop.status_code, None)
    _emit_event(response.url, response.status_code, elapsed_ms)


def _emit_event(url: httpx.URL, status: int, elapsed_ms: float | None) -> None:
    """写一条 http 层 debug 事件（url 由 obslog 侧 redact；domain 取 host）。"""
    log_event(
        "DEBUG",  # obslog 内部会 .upper()；与既有 call-site 统一传大写
        "http exchange",
        domain=url.host or None,
        url=str(url),
        status=status,
        elapsed_ms=elapsed_ms,
    )


def _accept_headers(accept: str | None) -> dict[str, str] | None:
    """把可选的 `accept` 组装成单请求头覆盖（None 则不覆盖，用客户端默认）。"""
    return {"Accept": accept} if accept else None


class HttpClient:
    """真实 adapter 共享的薄 HTTP 客户端（§2.1 冻结签名）。"""

    def __init__(
        self,
        *,
        user_agent: str,
        timeout_s: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=timeout_s,
            transport=transport,
            follow_redirects=True,
        )

    def get_text(self, url: str, *, accept: str | None = None) -> str:
        """GET 并返回解码后的文本正文；错误状态/异常 → `CrawlerError`。"""
        return self._request(url, accept=accept).text

    def get_bytes(self, url: str, *, accept: str | None = None) -> bytes:
        """GET 并返回原始字节正文；错误状态/异常 → `CrawlerError`。"""
        return self._request(url, accept=accept).content

    def stream(self, url: str) -> Iterator[bytes]:
        """GET 流式取字节（供 `fetch_asset` 交给 `io.write_stream`）。

        惰性生成器：网络请求、obslog 事件与错误状态判定在首次迭代时执行；
        分块由 httpx `iter_bytes()` 产出（已做 content-decoding）。
        """
        return self._stream(url)

    def close(self) -> None:
        """释放底层连接池（幂等）。"""
        self._client.close()

    @property
    def is_closed(self) -> bool:
        """底层 httpx.Client 是否已关闭。"""
        return self._client.is_closed

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _request(self, url: str, *, accept: str | None) -> httpx.Response:
        """非流式 GET：发请求、记 obslog、按状态映射错误，返回已读响应。"""
        start = time.monotonic()
        try:
            response = self._client.get(url, headers=_accept_headers(accept))
        except httpx.TimeoutException as exc:
            raise CrawlerError(
                ErrorClass.TRANSIENT, f"timeout for {redact(url)}", detail="timeout"
            ) from exc
        except httpx.HTTPError as exc:
            raise CrawlerError(
                ErrorClass.TRANSIENT,
                f"connection error for {redact(url)}",
                detail=type(exc).__name__,
            ) from exc
        elapsed_ms = (time.monotonic() - start) * 1000
        _log_exchange(response, elapsed_ms=elapsed_ms)
        if response.status_code >= 400:
            raise _error_for_status(response)
        return response

    def _stream(self, url: str) -> Iterator[bytes]:
        """`stream()` 的生成器实现：见其 docstring 的惰性语义。"""
        start = time.monotonic()
        try:
            with self._client.stream("GET", url) as response:
                elapsed_ms = (time.monotonic() - start) * 1000
                _log_exchange(response, elapsed_ms=elapsed_ms)
                if response.status_code >= 400:
                    raise _error_for_status(response)
                yield from response.iter_bytes()
        except httpx.TimeoutException as exc:
            raise CrawlerError(
                ErrorClass.TRANSIENT, f"timeout for {redact(url)}", detail="timeout"
            ) from exc
        except httpx.HTTPError as exc:
            raise CrawlerError(
                ErrorClass.TRANSIENT,
                f"connection error for {redact(url)}",
                detail=type(exc).__name__,
            ) from exc


__all__ = ["HttpClient"]
