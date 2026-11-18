"""Polite, robust HTTP fetching shared by all adapters.

Per host: robots.txt (RFC 9309 semantics), a minimum interval between requests, an optional
sliding-window budget (OpenReview: requests per hour), retries with exponential backoff and
jitter, a circuit breaker, challenge-page detection and a raw-response cache with conditional
requests. Adapters only decide what to request and how to parse it.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import random
import threading
import time
import urllib.robotparser
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import httpx

log = logging.getLogger("scout.fetch")


class FetchError(Exception):
    """A request failed after retries (network error, 4xx/5xx outside the accepted set)."""

    def __init__(self, message: str, status: int | None = None, url: str | None = None):
        super().__init__(message)
        self.status = status
        self.url = url


class ChallengeError(FetchError):
    """The host answered with a bot challenge. Never retried; the host cools down."""


class RobotsDenied(FetchError):
    """robots.txt disallows the URL for our user agent."""


class CircuitOpen(FetchError):
    """The host had too many consecutive failures; requests are paused."""


@dataclass
class HostPolicy:
    min_interval: float = 1.5
    budget: int | None = None          # max requests per window
    window: float = 3600.0
    timeout: float = 120.0
    retries: int = 4
    respect_robots: bool = True
    breaker_after: int = 5            # consecutive failures before the host pauses 15 minutes


@dataclass
class Response:
    url: str
    status: int
    headers: dict[str, str]
    content: bytes
    from_cache: bool = False

    @property
    def text(self) -> str:
        enc = "utf-8"
        ctype = self.headers.get("content-type", "")
        if "charset=" in ctype:
            enc = ctype.split("charset=")[-1].split(";")[0].strip() or "utf-8"
        try:
            return self.content.decode(enc, errors="replace")
        except LookupError:
            return self.content.decode("utf-8", errors="replace")

    def json(self) -> object:
        return json.loads(self.content)


@dataclass
class _HostState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    last: float = 0.0
    stamps: deque = field(default_factory=deque)
    fails: int = 0
    open_until: float = 0.0   # circuit breaker / challenge: requests raise until then
    hold_until: float = 0.0   # upstream quota nearly used: requests wait until then
    robots: urllib.robotparser.RobotFileParser | None = None
    robots_at: float = 0.0
    robots_delay: float | None = None
    robots_mode: str = "unknown"  # parsed | allow_all | deny_all


_CHALLENGE_MARKERS = (b"cf-chl", b"Just a moment...", b"challenge-platform", b"Attention Required! | Cloudflare")

DEFAULT_POLICIES: dict[str, HostPolicy] = {
    # OpenReview: logged-in budget is 500 requests/hour (header `ratelimit-policy: 500;w=3600`,
    # checked 2026-11-19); Scout uses 80% of it and never sends the email parameter.
    "api2.openreview.net": HostPolicy(min_interval=2.0, budget=400, window=3600.0, timeout=180.0),
    "api.openreview.net": HostPolicy(min_interval=2.0, budget=400, window=3600.0, timeout=180.0),
    "openaccess.thecvf.com": HostPolicy(min_interval=1.5),
    "cvpr.thecvf.com": HostPolicy(min_interval=3.0),
    "iccv.thecvf.com": HostPolicy(min_interval=3.0),
    "www.ecva.net": HostPolicy(min_interval=2.0),
    "raw.githubusercontent.com": HostPolicy(min_interval=1.0),
    "proceedings.mlr.press": HostPolicy(min_interval=2.0, timeout=300.0),
    # The AAAI OAI endpoint fails on some pages; the adapter narrows date windows on purpose.
    "ojs.aaai.org": HostPolicy(min_interval=2.0, retries=1, breaker_after=30),
    # robots.txt (2026-11-19) welcomes crawlers and sets no Crawl-delay; 2 s stays polite.
    "www.ijcai.org": HostPolicy(min_interval=2.0),
    "ijcai.org": HostPolicy(min_interval=2.0),
}
# Hosts that share one budget (same upstream service).
_BUDGET_GROUP = {"api.openreview.net": "api2.openreview.net"}


class Fetcher:
    def __init__(self, cache_dir: Path, user_agent: str, policies: dict[str, HostPolicy] | None = None,
                 transport: httpx.BaseTransport | None = None, sleep=time.sleep, clock=time.monotonic):
        self.cache_dir = cache_dir
        self.user_agent = user_agent
        self.policies = dict(DEFAULT_POLICIES)
        if policies:
            self.policies.update(policies)
        self._states: dict[str, _HostState] = {}
        self._states_lock = threading.Lock()
        self._sleep = sleep
        self._clock = clock
        self._client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            follow_redirects=True,
            timeout=httpx.Timeout(60.0, connect=20.0),
            transport=transport,
        )
        self.stats = {"requests": 0, "cache_hits": 0, "not_modified": 0, "retries": 0, "errors": 0}

    def close(self) -> None:
        self._client.close()

    # ---- host bookkeeping -----------------------------------------------------------------

    def _state(self, host: str) -> _HostState:
        key = _BUDGET_GROUP.get(host, host)
        with self._states_lock:
            st = self._states.get(key)
            if st is None:
                st = _HostState()
                self._states[key] = st
            return st

    def policy(self, host: str) -> HostPolicy:
        return self.policies.get(host, HostPolicy())

    def cool_down(self, host: str, seconds: float) -> None:
        st = self._state(host)
        st.open_until = max(st.open_until, self._clock() + seconds)

    def host_status(self) -> dict[str, dict]:
        now = self._clock()
        out = {}
        with self._states_lock:
            for host, st in self._states.items():
                out[host] = {
                    "paused_s": max(0, round(st.open_until - now)),
                    "waiting_s": max(0, round(st.hold_until - now)),
                    "window_used": len(st.stamps),
                    "consecutive_failures": st.fails,
                    "robots": st.robots_mode,
                }
        return out

    # ---- robots ---------------------------------------------------------------------------

    def _robots_allows(self, url: str) -> bool:
        parts = urlsplit(url)
        host = parts.hostname or ""
        pol = self.policy(host)
        if not pol.respect_robots:
            return True
        st = self._state(host)
        now = self._clock()
        if st.robots_mode == "unknown" or now - st.robots_at > 24 * 3600:
            robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
            mode, parser, delay = "allow_all", None, None
            try:
                r = self._client.get(robots_url, timeout=30.0)
                if r.status_code >= 500:
                    mode = "deny_all"
                elif r.status_code >= 400:
                    mode = "allow_all"
                else:
                    parser = urllib.robotparser.RobotFileParser()
                    parser.parse(r.text.splitlines())
                    mode = "parsed"
                    d = parser.crawl_delay(self._ua_token())
                    delay = float(d) if d else None
            except httpx.HTTPError:
                mode = "deny_all"
            st.robots, st.robots_mode, st.robots_at, st.robots_delay = parser, mode, now, delay
            log.info("robots %s -> %s (crawl-delay=%s)", host, mode, delay)
        if st.robots_mode == "allow_all":
            return True
        if st.robots_mode == "deny_all":
            return False
        assert st.robots is not None
        return st.robots.can_fetch(self._ua_token(), url)

    def _ua_token(self) -> str:
        return self.user_agent.split("/")[0]

    # ---- pacing ---------------------------------------------------------------------------

    def _pace(self, host: str) -> None:
        pol = self.policy(host)
        st = self._state(host)
        interval = max(pol.min_interval, st.robots_delay or 0.0)
        while True:
            now = self._clock()
            if st.open_until > now:
                raise CircuitOpen(f"{host} paused for {round(st.open_until - now)}s", url=host)
            wait = max(st.last + interval - now, st.hold_until - now)
            if pol.budget:
                while st.stamps and now - st.stamps[0] > pol.window:
                    st.stamps.popleft()
                if len(st.stamps) >= pol.budget:
                    wait = max(wait, st.stamps[0] + pol.window - now + 0.5)
            if wait <= 0:
                st.last = now
                if pol.budget:
                    st.stamps.append(now)
                return
            self._sleep(min(wait, 60.0))

    def _observe_rate_headers(self, host: str, headers: httpx.Headers) -> None:
        """Wait for the window to reset when the upstream says its quota is used up."""
        remaining = headers.get("ratelimit-remaining") or headers.get("x-ratelimit-remaining")
        reset = headers.get("ratelimit-reset")
        if remaining is None or not reset:
            return
        try:
            rem, secs = int(remaining), float(reset)
        except ValueError:
            return
        if rem <= 1 and 0 < secs <= 3600:
            st = self._state(host)
            st.hold_until = max(st.hold_until, self._clock() + secs + 1.0)
            log.warning("%s quota nearly used (remaining=%s); waiting %.0fs", host, rem, secs)

    # ---- cache ----------------------------------------------------------------------------

    def _cache_paths(self, url: str) -> tuple[Path, Path]:
        host = urlsplit(url).hostname or "unknown"
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
        base = self.cache_dir / "http" / host / digest[:2]
        return base / f"{digest}.gz", base / f"{digest}.json"

    def _cache_read(self, url: str) -> tuple[dict, bytes] | None:
        body_p, meta_p = self._cache_paths(url)
        if not (body_p.is_file() and meta_p.is_file()):
            return None
        try:
            meta = json.loads(meta_p.read_text())
            return meta, gzip.decompress(body_p.read_bytes())
        except (OSError, ValueError, EOFError):
            return None

    def _cache_write(self, url: str, status: int, headers: httpx.Headers, content: bytes) -> None:
        body_p, meta_p = self._cache_paths(url)
        body_p.parent.mkdir(parents=True, exist_ok=True)
        meta = {
            "url": url,
            "status": status,
            "fetched_at": time.time(),
            "etag": headers.get("etag"),
            "last_modified": headers.get("last-modified"),
            "content_type": headers.get("content-type", ""),
        }
        tmp = body_p.with_suffix(".tmp")
        tmp.write_bytes(gzip.compress(content, compresslevel=6))
        tmp.replace(body_p)
        meta_p.write_text(json.dumps(meta))

    # ---- main entry -----------------------------------------------------------------------

    def get(self, url: str, *, params: dict | None = None, headers: dict | None = None,
            max_age: float | None = None, use_cache: bool = True, accept: tuple[int, ...] = (200,),
            timeout: float | None = None) -> Response:
        """GET with politeness and retries.

        max_age: serve from the local cache without any request when the cached copy is younger.
        use_cache: store the body and send conditional headers (ETag / Last-Modified).
        accept: status codes returned to the caller instead of raising.
        """
        if params:
            url = f"{url}{'&' if '?' in url else '?'}{urlencode(params, doseq=True)}"
        cached = self._cache_read(url) if use_cache else None
        if cached and max_age is not None and time.time() - cached[0].get("fetched_at", 0) < max_age:
            self.stats["cache_hits"] += 1
            meta, body = cached
            return Response(url, meta.get("status", 200), {"content-type": meta.get("content_type", "")}, body, True)
        hdrs = dict(headers or {})
        if cached:
            if cached[0].get("etag"):
                hdrs["If-None-Match"] = cached[0]["etag"]
            if cached[0].get("last_modified"):
                hdrs["If-Modified-Since"] = cached[0]["last_modified"]
        r = self._request("GET", url, headers=hdrs, accept=accept + ((304,) if cached else ()), timeout=timeout)
        if r.status == 304 and cached:
            self.stats["not_modified"] += 1
            meta, body = cached
            return Response(url, meta.get("status", 200), {"content-type": meta.get("content_type", "")}, body, True)
        if use_cache and r.status == 200:
            self._cache_write(url, r.status, httpx.Headers(r.headers), r.content)
        return r

    def post_json(self, url: str, payload: dict, *, headers: dict | None = None,
                  accept: tuple[int, ...] = (200,), timeout: float | None = None) -> Response:
        # Login-style endpoints have their own small quota; their headers must not pace the host.
        return self._request("POST", url, headers=headers or {}, json_body=payload, accept=accept,
                             timeout=timeout, check_robots=False, observe_quota=False)

    def _request(self, method: str, url: str, *, headers: dict, accept: tuple[int, ...],
                 json_body: dict | None = None, timeout: float | None = None,
                 check_robots: bool = True, observe_quota: bool = True) -> Response:
        host = urlsplit(url).hostname or ""
        pol = self.policy(host)
        st = self._state(host)
        if check_robots and not self._robots_allows(url):
            raise RobotsDenied(f"robots.txt disallows {url}", url=url)
        attempt = 0
        while True:
            with st.lock:
                self._pace(host)
                self.stats["requests"] += 1
                try:
                    resp = self._client.request(method, url, headers=headers, json=json_body,
                                                timeout=timeout or pol.timeout)
                    err: Exception | None = None
                except httpx.HTTPError as exc:  # network errors and timeouts
                    resp, err = None, exc
            if resp is not None:
                if observe_quota:
                    self._observe_rate_headers(host, resp.headers)
                content = resp.content
                if self._is_challenge(resp.status_code, content):
                    st.fails += 1
                    self.cool_down(host, 24 * 3600)
                    self.stats["errors"] += 1
                    raise ChallengeError(f"bot challenge from {host} (HTTP {resp.status_code})",
                                         status=resp.status_code, url=url)
                if resp.status_code in accept:
                    st.fails = 0
                    return Response(str(resp.url), resp.status_code,
                                    {k.lower(): v for k, v in resp.headers.items()}, content)
                retryable = resp.status_code == 429 or resp.status_code >= 500
                retry_after = self._retry_after(resp.headers)
                if not retryable:
                    st.fails += 1
                    self.stats["errors"] += 1
                    raise FetchError(f"HTTP {resp.status_code} for {url}", status=resp.status_code, url=url)
                reason = f"HTTP {resp.status_code}"
            else:
                retry_after = None
                reason = f"{type(err).__name__}: {err}"
            attempt += 1
            st.fails += 1
            if st.fails >= pol.breaker_after:
                self.cool_down(host, 15 * 60)
            if attempt > pol.retries:
                self.stats["errors"] += 1
                raise FetchError(f"giving up on {url} after {attempt} attempts ({reason})",
                                 status=getattr(resp, "status_code", None), url=url)
            delay = retry_after if retry_after is not None else min(300.0, (2 ** attempt) * 2.0)
            delay += random.uniform(0, delay * 0.25)
            self.stats["retries"] += 1
            log.warning("retry %s in %.1fs (%s, attempt %d)", url, delay, reason, attempt)
            self._sleep(delay)

    @staticmethod
    def _retry_after(headers: httpx.Headers) -> float | None:
        raw = headers.get("retry-after")
        if not raw:
            return None
        try:
            return min(3600.0, float(raw))
        except ValueError:
            return None

    @staticmethod
    def _is_challenge(status: int, content: bytes) -> bool:
        head = content[:4096]
        if status == 403 and b"ChallengeRequiredError" in head:
            return True
        return status in (200, 403, 503) and any(m in head for m in _CHALLENGE_MARKERS)
