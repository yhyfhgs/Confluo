"""`crawler oa-report` 循环端到端限速锁测试（phase3-report.md §6 检查单 #15b）。

补强动机（组合证明 -> 直接证明，如实标注该补强解决什么问题）：在本文件之前，
"oa-report 会被限速"这条性质只是**拼**出来的——`tests/unit/test_http.py` 用
`_SpyLimiter`（固定 wait 返回值的鸭子类型桩件，非真 `RateLimiter`）证明了
`HttpClient._throttle` 会调 `acquire`+按需 `sleep`；`tests/unit/test_ratelimit.py`
用假时钟单独证明了 `RateLimiter` 的 token bucket 算术本身正确；但 `cli.py::
_prepare_unpaywall_adapter` 把二者接线到 `oa-report` 命令这段**装配代码**，此前没有
任何测试真正执行到过——`tests/integration/test_cli_oa_report.py` 全部用例都
`monkeypatch.setattr(UnpaywallAdapter, "lookup", ...)` 直接短路掉 lookup，从未触发
真实的 `HttpClient.get_bytes`/`RateLimiter.acquire`。三份证据组合起来"看似"覆盖了
限速，但没有一份是"真的跑过 oa-report 的 DOI 循环、观察到限速器被消费"的直接证据。

本文件补上直接证据：不 mock `lookup`，让 `crawler oa-report` 走真实
`UnpaywallAdapter.lookup -> HttpClient.get_bytes -> RateLimiter.acquire` 全链路，只在
两处注入测试 seam：
①`cli._http_client_factory`——模块 docstring 自陈的既有测试 seam（"模块级函数是
  测试注入 MockTransport client 的 seam（零真实网络）"），注入 `httpx.MockTransport`；
②`cli.RateLimiter`——构造签名 seam（`RateLimiter(scale=...)` 关键字调用，可用同签名
  的假时钟工厂替换），使 token bucket 算术可预测断言、且不需真实等待。

断言直接证明的两件事：
1. 每个 DOI 恰触发 1 次 `RateLimiter.acquire("api.unpaywall.org")`——逐请求限速
   （§7-6 C4 红线）在 oa-report 命令上真实落地，不是"接线代码存在但从未执行"。
2. 时钟冻结（不推进）、burst=5 耗尽后，第 6/7/8 次请求算出的等待秒数被原样传给
   `time.sleep`（同 `test_http.py` 既有的 `paper_crawler.http.time.sleep` 猴补丁
   手法）——证明这个等待值真的会拖慢下一次请求，不是算出来又被丢弃的死数据。
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import closing
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

import paper_crawler.cli as cli_module
from paper_crawler.cli import app
from paper_crawler.config import Config
from paper_crawler.http import HttpClient
from paper_crawler.ratelimit import RateLimiter
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.types import PaperStub, VenueSpec
from paper_crawler.useragent import build_user_agent

runner = CliRunner()

_VENUE = "mock_journal"
_UNPAYWALL_DOMAIN = "api.unpaywall.org"
# unpaywall default_rate: requests_per_minute=300.0 (=5/s), burst=5（adapter.py）。
_BURST = 5


class _FakeClock:
    """手动前进的假时钟（同 tests/unit/test_ratelimit.py 的既有手法自持一份——本文件
    是 integration 测试，不跨 unit 边界 import 另一模块的测试私有类）。"""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now


def _venue_spec() -> VenueSpec:
    return VenueSpec(
        id=_VENUE,
        kind="journal",
        names={"full": "Mock Journal", "aliases": []},
        field=["cs_ai"],
        identifiers={"issn": ["0000-0000"]},
        metadata_source="mock_platform",
        fulltext_source="mock_platform",
    )


def _seed_dois(home: Path, dois: list[str]) -> None:
    """直接经 `Repo` 往 `home/catalog.sqlite` 插入 paper+doi identifier 行（同
    test_cli_oa_report.py 既有手法，绕过 pull 流水线）。"""
    with closing(Database(home / "catalog.sqlite")) as db:
        db.migrate()
        repo = Repo(db)
        repo.upsert_venue(_venue_spec())
        for index, doi in enumerate(dois):
            repo.upsert_paper(
                _VENUE, None, PaperStub(title=f"paper {index}", identifiers=(("doi", doi),))
            )


def _install_seams(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> tuple[list[str], list[float]]:
    """装配 ①MockTransport 注入的 `_http_client_factory` seam ②假时钟 `RateLimiter` seam。

    返回 `(acquire_calls, slept)`：前者记录每次 `RateLimiter.acquire` 的 domain 参数
    （按发生顺序），后者记录每次 `time.sleep` 收到的秒数（按发生顺序）——测试对这两个
    列表断言即是"直接证明"本身。
    """

    def _fake_http_client_factory(
        config: Config, rate_limiter: RateLimiter | None = None
    ) -> HttpClient:
        # 与真实 cli._http_client_factory 逐行同构，唯一差异是显式传 transport
        # （该模块级函数自身文档承诺的测试 seam）。
        return HttpClient(
            user_agent=build_user_agent(config.identity_email),
            rate_limiter=rate_limiter,
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr(cli_module, "_http_client_factory", _fake_http_client_factory)

    slept: list[float] = []
    monkeypatch.setattr("paper_crawler.http.time.sleep", lambda s: slept.append(s))

    acquire_calls: list[str] = []
    fake_clock = _FakeClock()

    def _fake_rate_limiter_factory(*, scale: float = 1.0) -> RateLimiter:
        limiter = RateLimiter(scale=scale, clock=fake_clock)
        real_acquire = limiter.acquire

        def _spy_acquire(domain: str) -> float:
            acquire_calls.append(domain)
            return real_acquire(domain)

        limiter.acquire = _spy_acquire  # type: ignore[method-assign]
        return limiter

    # `cli._build_env` 调用 `RateLimiter(scale=config.rate_scale)`（关键字调用，同签名）
    # ——替换 cli 模块命名空间里的绑定即可，函数体按名字在调用时从模块全局重新查找。
    monkeypatch.setattr(cli_module, "RateLimiter", _fake_rate_limiter_factory)

    return acquire_calls, slept


def _closed_record_handler(request: httpx.Request) -> httpx.Response:
    """最小合法 unpaywall 响应（closed 记录，`is_oa=false`）——本测试只关心限速链路，
    不关心 OA 命中内容。"""
    return httpx.Response(200, content=b'{"is_oa": false}')


# --- 直接证明 1+2：8 个 DOI（> burst=5）逐个 acquire，且耗尽后的等待值真实传给 sleep ----


def test_oa_report_loop_genuinely_acquires_rate_limiter_per_doi(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dois = [f"10.0/{i:03d}" for i in range(_BURST + 3)]  # 8 个：5 个立即可用 + 3 个需排队
    home = tmp_path / "home"
    _seed_dois(home, dois)

    acquire_calls, slept = _install_seams(monkeypatch, _closed_record_handler)

    result = runner.invoke(app, ["oa-report", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert f"总数: {len(dois)}" in result.output

    # 每个 DOI 恰 1 次 acquire，domain 恰为 unpaywall API 域——不是"注册了但从未消费"。
    assert acquire_calls == [_UNPAYWALL_DOMAIN] * len(dois)

    # 时钟冻结：前 5 次消耗 burst 立即可用（不 sleep）；第 6/7/8 次以 5 token/s 排队，
    # 应得等待 1/5、2/5、3/5 秒——且这三个值被原样传给 time.sleep（未被丢弃）。
    assert slept == [pytest.approx(0.2), pytest.approx(0.4), pytest.approx(0.6)]


# --- --limit 截断后，acquire 次数精确跟随（证明限速证据不是巧合于固定 8 次）--------------


def test_oa_report_limit_flag_reduces_acquire_call_count_accordingly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dois = [f"10.0/{i:03d}" for i in range(_BURST + 3)]
    home = tmp_path / "home"
    _seed_dois(home, dois)

    acquire_calls, slept = _install_seams(monkeypatch, _closed_record_handler)

    result = runner.invoke(app, ["oa-report", "--limit", "3", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "总数: 3" in result.output
    assert acquire_calls == [_UNPAYWALL_DOMAIN] * 3  # 3 <= burst=5：全部立即可用
    assert slept == []
