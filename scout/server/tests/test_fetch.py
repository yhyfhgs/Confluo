import httpx
import pytest

from confluo_scout.fetch import ChallengeError, CircuitOpen, Fetcher, HostPolicy, RobotsDenied


class FakeTime:
    def __init__(self):
        self.t = 1000.0
        self.slept: list[float] = []

    def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.t += s

    def clock(self) -> float:
        return self.t


def make(tmp_path, handler, policies=None):
    ft = FakeTime()
    f = Fetcher(tmp_path, "ScoutTest/1.0", policies=policies, transport=httpx.MockTransport(handler),
                sleep=ft.sleep, clock=ft.clock)
    return f, ft


def test_retry_after_then_success(tmp_path):
    calls = {"n": 0}

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, headers={"retry-after": "7"})
        return httpx.Response(200, text="ok")

    f, ft = make(tmp_path, handler)
    r = f.get("https://example.org/page", use_cache=False)
    assert r.status == 200 and r.text == "ok"
    assert calls["n"] == 3 and f.stats["retries"] == 2
    assert any(s >= 7 for s in ft.slept)


def test_challenge_stops_host(tmp_path):
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(403, json={"name": "ChallengeRequiredError", "message": "Challenge verification required"})

    f, _ = make(tmp_path, handler)
    with pytest.raises(ChallengeError):
        f.get("https://api.example.org/notes", use_cache=False)
    with pytest.raises(CircuitOpen):
        f.get("https://api.example.org/notes", use_cache=False)


def test_robots_disallow(tmp_path):
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /static\n")
        return httpx.Response(200, text="ok")

    f, _ = make(tmp_path, handler)
    assert f.get("https://conf.example.org/virtual/2025/papers.html", use_cache=False).status == 200
    with pytest.raises(RobotsDenied):
        f.get("https://conf.example.org/static/virtual/data/x.json", use_cache=False)


def test_hourly_budget_waits(tmp_path):
    def handler(req):
        return httpx.Response(404) if req.url.path == "/robots.txt" else httpx.Response(200, text="ok")

    f, ft = make(tmp_path, handler, {"budget.example.org": HostPolicy(min_interval=0.0, budget=2, window=3600.0)})
    start = ft.t
    for _ in range(3):
        f.get("https://budget.example.org/x", use_cache=False)
    assert ft.t - start >= 3600


def test_cache_and_conditional_get(tmp_path):
    seen = []

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        seen.append(dict(req.headers))
        if req.headers.get("if-none-match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(200, text="body", headers={"etag": '"v1"'})

    f, _ = make(tmp_path, handler)
    assert f.get("https://cache.example.org/a").text == "body"
    r2 = f.get("https://cache.example.org/a")
    assert r2.text == "body" and r2.from_cache and f.stats["not_modified"] == 1
    r3 = f.get("https://cache.example.org/a", max_age=3600)
    assert r3.from_cache and len(seen) == 2  # served without a request


def test_breaker_after_failures(tmp_path):
    def handler(req):
        return httpx.Response(404) if req.url.path == "/robots.txt" else httpx.Response(500)

    f, _ = make(tmp_path, handler, {"down.example.org": HostPolicy(min_interval=0.0, retries=1, breaker_after=3)})
    from confluo_scout.fetch import FetchError

    with pytest.raises(FetchError):
        f.get("https://down.example.org/x", use_cache=False)
    with pytest.raises(FetchError):
        f.get("https://down.example.org/x", use_cache=False)
    with pytest.raises(CircuitOpen):
        f.get("https://down.example.org/x", use_cache=False)
