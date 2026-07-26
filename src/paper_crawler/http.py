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
- 403 + `cf-mitigated: challenge` 响应头 → CHALLENGE（`Challenged`）；403 无该头 →
  NO_ENTITLEMENT（**受控演进 S-c**，D-030 裁决②；见 `_error_for_status` 403 分支注释）
- 404 / 410 / 451 → GONE（资源终态；451 法律不可用亦属资源终态）
- 其余 4xx（400 / 405 / …）→ CONFIG（请求构造有缺陷，如 arxiv offset>30000→400，
  应响亮停机而非标资源终态；CONFIG 经 pipeline 特判转 BLOCKED）
- 重定向默认跟随（每一跳与终响应各记一条 obslog debug 事件）

`transport` 构造参数是 T4 单测注入 `httpx.MockTransport` 的唯一通道——生产传 None
即用 httpx 默认传输，测试传 MockTransport 即零真实网络。UA 由调用方（从 config 组装
D-014 格式 `PaperCrawler/<ver> (personal research; mailto:<email>)`）注入，本模块不读
config。

**S-c 受控演进**（D-030 裁决②，11-browser-fetch §5.4/§5.5）：403 分支新增头级判别
——真实 Cloudflare 判罚形态是 `403 + cf-mitigated: challenge`，此前被统一映射
NO_ENTITLEMENT，导致「不冷却、不 BLOCKED、还派生 OA-fallback 继续对判罚中的平台
发请求」，与 04 §5/AC-4.6"检测到风控页立即 BLOCKED + 冷却 24h"语义相反。改判面经
论证恰好 = wiley.md §5 / aea.md §6 / auth-framework §11 三处文档**已声明应改**的场景
（wiley TDM 403 走无 CF 前置的 `api.wiley.com`、elsevier 走 JSON 封套，均不携该头
⇒ 行为不变），故属"让实现追上文档"而非语义变更；全库 fixture 零翻转由 T-6 机器化复核。

**T6 纯附加扩展**：新增 `post_json`（S2 `POST /paper/batch` 批查通道所需——冻结的
GET-only 三方法 `get_text`/`get_bytes`/`stream` 签名与行为完全未改动，仅在 `_request`
内部新增可选 `method`/`json_body` 参数，缺省值保证既有调用点零回归）。错误映射表/
限速闸/obslog 记录机制对 POST 路径同样适用（同一套 `_request`）。

**T7 纯附加扩展**（D-033 已裁决子项①，12-fulltext-extract §7.1）：新增 `post_multipart`
（GROBID `POST /api/processFulltextDocument` 走 `multipart/form-data`，`post_json` 不覆盖）。
同样只在 `_request` 内部新增可选 `files`/`form_data` 参数——既有方法签名/行为逐字不变，
且新方法**与 `post_json` 同构地走 `_request`**，不另起绕过限速/obslog/错误映射的通路。
GROBID 客户端构造时 `rate_limiter=None`（本机服务不是站点）且**不写 FetchLog**——FetchLog
是在线预算的唯一事实源（D-030 §7.2），把本地调用记进去会污染预算派生口径。
"""

import time
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from types import TracebackType

import httpx

from paper_crawler.auth.challenge import ChallengeDetector
from paper_crawler.errors import Challenged, CrawlerError, ErrorClass
from paper_crawler.obslog import log_event, redact
from paper_crawler.ratelimit import RateLimiter


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
    # 必须 isascii()：str.isdigit() 对非 ASCII 数字字符（如 latin-1 的 "²"，畸形
    # 头字节可解出）返回 True，但 int() 只接受十进制字符会抛 ValueError——而本段
    # 不在 try 兜底内，裸异常会破坏"状态→CrawlerError"契约。isascii()+isdigit()
    # 保证只剩 '0'-'9'，int() 必成功；非 ASCII 落到下方 HTTP-date 兜底（在 try 内）。
    if raw.isascii() and raw.isdigit():  # 纯 ASCII 非负整数秒
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
    """把 >=400 的响应状态映射为 `CrawlerError`（§2.1 冻结映射表）。

    **纯附加**（auth-framework §6，检查单 #4）：各分支额外携带 `status_code=status`
    （此处 `response.status_code` 已在手）——**映射表本身不变**，消息格式逐字不变，只是
    异常多带原始 status，供上层精确重分类（如 openalex 402→`exc.status_code == 402`）。
    """
    status = response.status_code
    msg = f"HTTP {status} for {redact(str(response.url))}"

    if status == 429:
        return _rate_limited(response, msg)
    if status == 401:
        return CrawlerError(ErrorClass.AUTH_EXPIRED, msg, status_code=status)
    if status == 403:
        # S-c（D-030 裁决②）：头级质询判别复用 `ChallengeDetector` 的**唯一权威特征源**
        # （不在本模块复制 `cf-mitigated` 特征串，11-browser-fetch §5.5-1）。命中 →
        # `Challenged`（error_class 恒 CHALLENGE）→ pipeline 既有 `_BLOCK_CLASSES` 路径
        # → BLOCKED + 域冷却 24h，**零新增处置逻辑**（§5.5-2）。未命中 → NO_ENTITLEMENT
        # 逐字不变（wiley TDM 403 / 机构无订阅等真实场景，§5.5-3）。
        # `Challenged` 的冻结签名不带 `status_code`（沿 auth-framework §2.4 固定
        # error_class 先例），故本分支不携原始 status——这也让 elsevier 的
        # `exc.status_code == 403 → AUTH_EXPIRED` 重分类不会把挑战悄悄降级（fail-safe）。
        if ChallengeDetector.has_challenge_headers(response.headers):
            return Challenged(msg, detail="cf_challenge")
        return CrawlerError(ErrorClass.NO_ENTITLEMENT, msg, status_code=status)
    if status in (404, 410, 451):
        # 404/410 资源消失；451 法律不可用——同属"资源终态、不重试"。
        return CrawlerError(ErrorClass.GONE, msg, status_code=status)
    if status == 503:
        # 5xx→TRANSIENT，但 503 带 Retry-After 视为限流信号 → RATE_LIMITED。
        retry_after = _parse_retry_after(response)
        if retry_after is not None:
            return CrawlerError(
                ErrorClass.RATE_LIMITED,
                msg,
                detail=f"retry_after_s={retry_after}",
                status_code=status,
            )
        return CrawlerError(ErrorClass.TRANSIENT, msg, status_code=status)
    if 500 <= status < 600:
        return CrawlerError(ErrorClass.TRANSIENT, msg, status_code=status)
    # 其余 4xx（400/405/406…）：请求构造有缺陷（如 arxiv offset>30000→400 属 config
    # 类设计案例）——响亮停机而非标资源终态；CONFIG 经 pipeline 特判转 BLOCKED。
    # 402（credit 耗尽）亦落此分支——status_code 供上层（openalex）精确重分类为限流。
    return CrawlerError(ErrorClass.CONFIG, msg, status_code=status)


def _rate_limited(response: httpx.Response, msg: str) -> CrawlerError:
    """429 → RATE_LIMITED；有 Retry-After 则 detail 含 `retry_after_s=<n>`，无则省略。"""
    retry_after = _parse_retry_after(response)
    detail = f"retry_after_s={retry_after}" if retry_after is not None else ""
    return CrawlerError(
        ErrorClass.RATE_LIMITED, msg, detail=detail, status_code=response.status_code
    )


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
        rate_limiter: RateLimiter | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        # `extra_headers`（plan §7-4 冻结扩展）：client 级附加头，**纯附加**——与 UA 并列
        # 挂在底层 httpx.Client 上，随每个请求自动发出。用途：free_account 级 adapter
        # （openreview）注入 `Cookie: openreview.accessToken=<token>`；缺省 None 时行为与
        # 扩展前完全一致（只带 UA）。附加头是**该 client 实例私有**的——token 通道须为
        # 携密 adapter 单独构造 client，绝不复用共享 client（否则 cookie 会外泄到他站，
        # 违反凭证红线）。同名键（如显式传 User-Agent）由附加头覆盖，调用方自负。
        self._client = httpx.Client(
            headers={"User-Agent": user_agent, **(extra_headers or {})},
            timeout=timeout_s,
            transport=transport,
            follow_redirects=True,
        )
        # 逐请求限速（C4 红线修复，plan §7-6）：非 None 时每次请求发出前对**请求 host**
        # `acquire`+按需 sleep，使 adapter 内部翻页（每页一请求）不绕过限速。与 pipeline
        # 的 per-stage `acquire_and_wait` 共享同一 `RateLimiter` 实例（同桶——arxiv 三域经
        # `RateLimiter.alias` 归并到主域），故两处计费落到同一预算，不放宽速率。None 时
        # （单测/离线 MockTransport 路径、canary 惰性自建 client）行为与限速前完全一致。
        self._rate_limiter = rate_limiter

    def get_text(self, url: str, *, accept: str | None = None) -> str:
        """GET 并返回解码后的文本正文；错误状态/异常 → `CrawlerError`。"""
        return self._request(url, accept=accept).text

    def get_bytes(self, url: str, *, accept: str | None = None) -> bytes:
        """GET 并返回原始字节正文；错误状态/异常 → `CrawlerError`。"""
        return self._request(url, accept=accept).content

    def post_json(
        self, url: str, *, json_body: object, accept: str | None = "application/json"
    ) -> bytes:
        """POST 一个 JSON 请求体，返回原始字节正文；错误映射同 GET 路径（§2.1 冻结表）。

        **纯附加扩展**（T6，S2 `POST /paper/batch` 批查通道所需——冻结接口原仅有
        GET-only 的 `get_text`/`get_bytes`/`stream` 三方法，均未改动签名/行为；本方法
        复用同一套 `_request` 机制：限速闸/超时映射/状态码→CrawlerError 映射/obslog
        记录与 GET 路径完全一致，只是 HTTP method 与请求体不同）。`json_body` 交给
        httpx 的 `json=` 参数序列化（自动置 `Content-Type: application/json`）。
        """
        return self._request(url, accept=accept, method="POST", json_body=json_body).content

    def post_multipart(
        self,
        url: str,
        *,
        files: Mapping[str, tuple[str, bytes, str]],
        data: Mapping[str, str] | None = None,
        accept: str | None = None,
    ) -> bytes:
        """POST 一个 `multipart/form-data` 请求体，返回原始字节正文；错误映射同 GET 路径。

        **纯附加扩展**（T7 / D-033 已裁决子项①，12-fulltext-extract §7.1；先例＝
        `extra_headers` 与 `CrawlerError.status_code`）——冻结的既有方法签名/行为**零改动**。
        用途：GROBID 的 `POST /api/processFulltextDocument` 走 multipart（现有 `post_json`
        不覆盖）。与 `post_json` **同构地走 `_request`**（同一限速闸 / obslog 记录 /
        状态码→`CrawlerError` 映射路径），不另起一条绕过既有记账的请求通路。

        `files` 的值形如 `(filename, content, content_type)`，`data` 是并列的普通表单字段
        （httpx 负责 boundary 组装与 `Content-Type` 头）。
        """
        return self._request(url, accept=accept, method="POST", files=files, form_data=data).content

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

    def _throttle(self, url: str) -> None:
        """逐请求限速闸：对请求 host `acquire` 一个 token，需等待则真实 `time.sleep`。

        无 `rate_limiter` 或 host 不可解析时为无操作。host 必须已在限速器注册
        （arxiv 三域经 `route_for` 的 register+alias 落到同一主域桶）；未注册即
        限速策略缺失，`acquire` fail-fast 为 `CrawlerError(CONFIG)`——响亮暴露
        「有网络请求却无限速声明」的装配缺陷，而非静默放行绕过限速。
        """
        if self._rate_limiter is None:
            return
        host = httpx.URL(url).host
        if not host:
            return
        wait = self._rate_limiter.acquire(host)
        if wait > 0:
            time.sleep(wait)

    def _request(
        self,
        url: str,
        *,
        accept: str | None,
        method: str = "GET",
        json_body: object = None,
        files: Mapping[str, tuple[str, bytes, str]] | None = None,
        form_data: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        """限速闸 → 发请求、记 obslog、按状态映射错误，返回已读响应。

        `method`/`json_body` 缺省值（`"GET"`/`None`）保证既有 `get_text`/`get_bytes`
        调用点行为逐字不变；`post_json`（T6）与 `post_multipart`（T7）是仅有的两个传非默认
        值的调用方——二者共用本方法的限速闸/错误映射/obslog，不存在旁路请求通路。
        `files`/`form_data` 恒为 None 时 httpx 视作未提供，POST JSON 路径行为亦逐字不变。
        """
        self._throttle(url)
        start = time.monotonic()
        try:
            if method == "GET":
                response = self._client.get(url, headers=_accept_headers(accept))
            else:
                response = self._client.request(
                    method,
                    url,
                    headers=_accept_headers(accept),
                    json=json_body,
                    files=files,
                    data=form_data,
                )
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
        """`stream()` 的生成器实现：见其 docstring 的惰性语义。

        限速闸在首次迭代（真正发请求前）触发，与非流式路径同粒度：一次逻辑请求
        一次 `acquire`（内部重定向跳由 httpx 在同一 `.stream()` 内跟随，不重复计费）。
        """
        self._throttle(url)
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
