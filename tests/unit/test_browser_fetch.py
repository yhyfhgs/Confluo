"""`browserfetch.py` 单测（design/11 §8 T-1/T-2/T-3/T-4/T-8/T-9 + §7 护栏）。

**零真实浏览器、零网络**：全部经假 `LaunchFetchFn` 注入 stub `BrowserFetchHandle`
（沿 `tests/unit/test_auth_browser.py` 的假 seam 先例）。覆盖：

- T-1 假 seam 全链：四态分支各一例 + OK 路径落盘字节数；
- T-2 挑战判定四态：复用 `ChallengeDetector` 既有特征（CF 头 / "Just a moment" body /
  hcaptcha / 正常全文页），判定器零改动即接线；
- T-3 **零对抗断言（红线专测）**：CHALLENGE 用例的 handle 调用序列 = `goto` 恰好 1 次、
  `download_via` 0 次、无二次 goto——"检测即停、零重试"可被机器判定（AC-0.2/AC-BF.1⑤）；
- T-4 同批约束：`resolve_in_context` 产出的 volatile 计划只活在栈上（返回的 outcome 携其
  URL），且非 `RENDER_PAGE` 计划响亮 CONFIG；
- T-8 一次性目录：`goto`/`download_via`/`launch` 任一抛异常，`pc-bfetch-` 目录亦被 rmtree；
- T-9 Playwright 缺失：默认 launcher → `AuthRequired` + 安装指引，且模块顶层零 playwright。
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import paper_crawler.browserfetch as bf
from paper_crawler.auth.challenge import ClassifyResult
from paper_crawler.browserfetch import (
    BrowserFetchHandle,
    BudgetGate,
    PageResponse,
    challenge_cooldown_active,
    fetch_one,
)
from paper_crawler.errors import AuthRequired, Challenged, CrawlerError, ErrorClass
from paper_crawler.types import AssetKind, AssetPlan, UrlStrategy

PDF_BYTES = b"%PDF-1.4\n" + b"0" * 512 + b"\n%%EOF\n"
LANDING = "https://papers.example.test/sol3/papers.cfm?abstract_id=1"
VOLATILE = "https://papers.example.test/Delivery.cfm/x.pdf?abstractid=1&mirid=1"


def render_plan(url: str = LANDING) -> AssetPlan:
    return AssetPlan(kind=AssetKind.PDF, url=url, url_strategy=UrlStrategy.RENDER_PAGE)


def ok_response(url: str = LANDING) -> PageResponse:
    return PageResponse(
        status=200,
        headers={"content-type": "text/html"},
        final_url=url,
        body=b"<html>Signed in as prof <a href='/article-pdf/1'>PDF</a></html>",
    )


class FakeHandle:
    """假 `BrowserFetchHandle`：记录调用序列（T-3 判据载体）+ 可注入异常。"""

    def __init__(
        self,
        response: PageResponse | None = None,
        *,
        goto_error: Exception | None = None,
        download_error: Exception | None = None,
        payload: bytes = PDF_BYTES,
    ) -> None:
        self.response = response if response is not None else ok_response()
        self.goto_error = goto_error
        self.download_error = download_error
        self.payload = payload
        self.calls: list[str] = []
        self.closed = False

    def goto(self, url: str) -> PageResponse:
        self.calls.append(f"goto:{url}")
        if self.goto_error is not None:
            raise self.goto_error
        return self.response

    def download_via(self, trigger, dest: Path) -> int:  # type: ignore[no-untyped-def]
        self.calls.append("download_via")
        trigger()  # 真实实现里在 expect_download 上下文内执行（点击/导航）
        if self.download_error is not None:
            raise self.download_error
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self.payload)
        return len(self.payload)

    def close(self) -> None:
        self.calls.append("close")
        self.closed = True

    @property
    def gotos(self) -> list[str]:
        return [c for c in self.calls if c.startswith("goto:")]


def launcher(handle: FakeHandle) -> tuple[list[tuple[str, bytes | None]], object]:
    """返回 (调用记录, launch fn)；记录 (user_data_dir, storage_state)。"""
    seen: list[tuple[str, bytes | None]] = []

    def _launch(user_data_dir: str, storage_state: bytes | None) -> BrowserFetchHandle:
        seen.append((user_data_dir, storage_state))
        assert Path(user_data_dir).is_dir()  # launch 时一次性目录已建
        return handle

    return seen, _launch


def gate(
    *,
    cap: int = 50,
    used: int = 0,
    cooling: bool = False,
    failures: int = 0,
    waits: list[str] | None = None,
) -> BudgetGate:
    sink = waits if waits is not None else []
    return BudgetGate(
        daily_cap=cap,
        count_today=lambda venue, domain: used,
        cooldown_active=lambda domain: cooling,
        consecutive_failures=lambda domain: failures,
        wait=lambda domain: (sink.append(domain), 0.0)[1],
    )


@pytest.fixture
def tracked_mkdtemp(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """截获 mkdtemp：记录真实创建的一次性 profile 目录（清理断言用，沿 auth 单测先例）。"""
    created: list[Path] = []
    import tempfile

    real = tempfile.mkdtemp

    def spy(prefix: str = "tmp") -> str:
        path = real(prefix=prefix)
        created.append(Path(path))
        return path

    monkeypatch.setattr(bf.tempfile, "mkdtemp", spy)
    return created


def run(
    handle: FakeHandle,
    dest: Path,
    *,
    budget: BudgetGate | None = None,
    plan: AssetPlan | None = None,
    storage_state: bytes | None = None,
    resolve_in_context: object = None,
) -> bf.BrowserFetchOutcome:
    _, launch = launcher(handle)
    return fetch_one(
        plan=plan if plan is not None else render_plan(),
        venue_id="mock_journal",
        dest=dest,
        storage_state=storage_state,
        budget=budget if budget is not None else gate(),
        resolve_in_context=resolve_in_context,  # type: ignore[arg-type]
        launch=launch,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# T-1 假 seam 全链（OK 路径）
# ---------------------------------------------------------------------------


def test_t1_ok_path_downloads_to_dest(tmp_path: Path, tracked_mkdtemp: list[Path]) -> None:
    handle = FakeHandle()
    dest = tmp_path / "tmp" / "asset.part"
    waits: list[str] = []
    outcome = run(handle, dest, budget=gate(waits=waits))

    assert outcome.ok is True
    assert outcome.no_entitlement is False
    assert outcome.verdict is ClassifyResult.OK
    assert outcome.bytes_written == len(PDF_BYTES)
    assert dest.read_bytes() == PDF_BYTES
    assert handle.closed is True
    # 限速闸：判定导航 + 下载触发各过一次域级闸（两次真实请求，绝不合并计一次）。
    assert waits == ["papers.example.test", "papers.example.test"]
    assert tracked_mkdtemp[0].name.startswith("pc-bfetch-")
    assert not tracked_mkdtemp[0].exists()  # 用完即毁（A-M7 一次性目录纪律）


def test_t1_storage_state_is_passed_through_to_launcher(tmp_path: Path) -> None:
    handle = FakeHandle()
    seen, launch = launcher(handle)
    fetch_one(
        plan=render_plan(),
        venue_id="v",
        dest=tmp_path / "a.part",
        storage_state=b'{"cookies": []}',
        budget=gate(),
        launch=launch,  # type: ignore[arg-type]
    )
    assert seen[0][1] == b'{"cookies": []}'


def test_t1_none_storage_state_is_a_legal_path(tmp_path: Path) -> None:
    """无凭证（gold OA / 未 opt-in 账号）以干净上下文启动，不是错误路径（§4.3）。"""
    handle = FakeHandle()
    seen, launch = launcher(handle)
    outcome = fetch_one(
        plan=render_plan(),
        venue_id="v",
        dest=tmp_path / "a.part",
        storage_state=None,
        budget=gate(),
        launch=launch,  # type: ignore[arg-type]
    )
    assert outcome.ok is True
    assert seen[0][1] is None


# ---------------------------------------------------------------------------
# T-2 四态判定（判定器零改动接线）+ T-3 零对抗断言
# ---------------------------------------------------------------------------


CHALLENGE_CASES: list[tuple[str, PageResponse]] = [
    (
        "cf_header",
        PageResponse(
            status=403,
            headers={"cf-mitigated": "challenge"},
            final_url=LANDING,
            body=b"<html>403</html>",
        ),
    ),
    (
        "just_a_moment",
        PageResponse(
            status=200, headers={}, final_url=LANDING, body=b"<html>Just a moment...</html>"
        ),
    ),
    (
        "captcha",
        PageResponse(
            status=200,
            headers={},
            final_url=LANDING,
            body=b"<html><div class='h-captcha'>hcaptcha</div></html>",
        ),
    ),
]


@pytest.mark.parametrize(("name", "response"), CHALLENGE_CASES, ids=[c[0] for c in CHALLENGE_CASES])
def test_t2_t3_challenge_stops_immediately(
    name: str, response: PageResponse, tmp_path: Path, tracked_mkdtemp: list[Path]
) -> None:
    """CHALLENGE → `Challenged`；**零后续动作**（T-3：goto 恰好 1 次、download_via 0 次）。"""
    handle = FakeHandle(response)
    dest = tmp_path / "a.part"
    with pytest.raises(Challenged):
        run(handle, dest)

    assert handle.gotos == [f"goto:{LANDING}"]  # 恰好一次导航，无二次尝试
    assert "download_via" not in handle.calls  # 绝不下载质询页
    assert handle.closed is True
    assert not dest.exists()
    assert not tracked_mkdtemp[0].exists()


def test_t2_login_redirect_raises_auth_required(tmp_path: Path) -> None:
    handle = FakeHandle(
        PageResponse(
            status=302,
            headers={},
            final_url="https://papers.example.test/signin",
            body=b"<html>please sign in</html>",
        )
    )
    with pytest.raises(AuthRequired) as excinfo:
        run(handle, tmp_path / "a.part")
    assert "crawler auth login" in excinfo.value.detail
    assert "download_via" not in handle.calls


def test_t2_no_entitlement_returns_outcome_without_raising(tmp_path: Path) -> None:
    handle = FakeHandle(
        PageResponse(
            status=200,
            headers={},
            final_url="https://papers.example.test/doi/article-abstract/1",
            body=b"<html>Get access</html>",
        )
    )
    outcome = run(handle, tmp_path / "a.part")
    assert outcome.no_entitlement is True
    assert outcome.ok is False
    assert outcome.verdict is ClassifyResult.NO_ENTITLEMENT
    assert "download_via" not in handle.calls  # 无权限不下载（交 OA-fallback 既有链）


# ---------------------------------------------------------------------------
# T-4 同批约束（volatile 计划只活在栈上）+ 计划形态护栏
# ---------------------------------------------------------------------------


def test_t4_non_render_page_plan_is_loudly_rejected(tmp_path: Path) -> None:
    handle = FakeHandle()
    with pytest.raises(CrawlerError) as excinfo:
        run(handle, tmp_path / "a.part", plan=AssetPlan(kind=AssetKind.PDF, url=LANDING))
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert handle.calls == []  # 拒绝发生在起浏览器之前


def test_t4_resolve_in_context_supplies_volatile_url_within_one_context(tmp_path: Path) -> None:
    """ssrn 同批约束：同一 handle 内先 resolve 出 volatile URL，立即用于本次下载。"""
    handle = FakeHandle()
    seen_handles: list[object] = []

    def resolve_in_context(h: BrowserFetchHandle) -> AssetPlan:
        seen_handles.append(h)
        return render_plan(VOLATILE)

    outcome = run(handle, tmp_path / "a.part", resolve_in_context=resolve_in_context)
    assert seen_handles == [handle]  # 同一上下文（非另起 context）
    assert handle.gotos[0] == f"goto:{VOLATILE}"  # 用的是 volatile URL
    assert outcome.url == VOLATILE  # 只在返回值（栈上）；落库归调用方（asset.url 存 landing）
    assert outcome.ok is True


def test_t4_resolve_in_context_result_must_stay_render_page(tmp_path: Path) -> None:
    handle = FakeHandle()
    with pytest.raises(CrawlerError) as excinfo:
        run(
            handle,
            tmp_path / "a.part",
            resolve_in_context=lambda h: AssetPlan(kind=AssetKind.PDF, url=VOLATILE),
        )
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert "download_via" not in handle.calls


# ---------------------------------------------------------------------------
# §7 预算护栏（三判定 + 优先级）
# ---------------------------------------------------------------------------


def test_budget_quota_boundary(tmp_path: Path) -> None:
    """边界：used=cap-1 放行；used=cap 熔断（沿护栏引擎同款边界纪律）。"""
    handle = FakeHandle()
    assert run(handle, tmp_path / "a.part", budget=gate(cap=3, used=2)).ok is True

    with pytest.raises(CrawlerError) as excinfo:
        run(FakeHandle(), tmp_path / "b.part", budget=gate(cap=3, used=3))
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert excinfo.value.detail == "browser_quota"


def test_budget_cooldown_precedes_quota(tmp_path: Path) -> None:
    """冷却优先于配额：两者同时命中时抛 CHALLENGE（不是 CONFIG）。"""
    handle = FakeHandle()
    with pytest.raises(Challenged) as excinfo:
        run(handle, tmp_path / "a.part", budget=gate(cap=3, used=99, cooling=True))
    assert excinfo.value.detail == "browser_cooldown"
    assert handle.calls == []  # 全离线判定：一个浏览器都没起


def test_budget_breaker_on_consecutive_failures(tmp_path: Path) -> None:
    handle = FakeHandle()
    assert run(handle, tmp_path / "a.part", budget=gate(failures=2)).ok is True

    with pytest.raises(CrawlerError) as excinfo:
        run(FakeHandle(), tmp_path / "b.part", budget=gate(failures=3))
    assert excinfo.value.detail == "browser_breaker"
    assert excinfo.value.error_class is ErrorClass.CONFIG


def test_budget_check_returns_quota_used(tmp_path: Path) -> None:
    assert gate(cap=50, used=7).check_or_raise(venue_id="v", domain="d") == 7


def test_challenge_cooldown_active_reads_runner_json(tmp_path: Path) -> None:
    """冷却读侧与 runner 写侧同源格式（`state/cooldown/<key>.json` + `{"until": iso}`）。"""
    path = tmp_path / "state" / "cooldown" / "papers.example.test.json"
    path.parent.mkdir(parents=True)
    until = datetime.now(UTC) + timedelta(hours=3)
    path.write_text(f'{{"until": "{until.isoformat()}"}}', encoding="utf-8")
    assert challenge_cooldown_active(tmp_path, "papers.example.test") is True
    assert challenge_cooldown_active(tmp_path, "other.example.test") is False

    stale = tmp_path / "state" / "cooldown" / "stale.json"
    stale.write_text('{"until": "2020-01-01T00:00:00+00:00"}', encoding="utf-8")
    assert challenge_cooldown_active(tmp_path, "stale") is False

    broken = tmp_path / "state" / "cooldown" / "broken.json"
    broken.write_text("not json", encoding="utf-8")
    assert challenge_cooldown_active(tmp_path, "broken") is False  # 畸形不致命（判定退回未冷却）


# ---------------------------------------------------------------------------
# T-8 一次性目录清理（异常路径亦清）
# ---------------------------------------------------------------------------


def test_t8_profile_dir_removed_when_goto_raises(
    tmp_path: Path, tracked_mkdtemp: list[Path]
) -> None:
    handle = FakeHandle(goto_error=RuntimeError("goto boom"))
    with pytest.raises(RuntimeError, match="goto boom"):
        run(handle, tmp_path / "a.part")
    assert handle.closed is True
    assert not tracked_mkdtemp[0].exists()


def test_t8_profile_dir_removed_when_download_raises(
    tmp_path: Path, tracked_mkdtemp: list[Path]
) -> None:
    handle = FakeHandle(download_error=RuntimeError("download boom"))
    with pytest.raises(RuntimeError, match="download boom"):
        run(handle, tmp_path / "a.part")
    assert handle.closed is True
    assert not tracked_mkdtemp[0].exists()


def test_t8_profile_dir_removed_when_launch_raises(
    tmp_path: Path, tracked_mkdtemp: list[Path]
) -> None:
    def launch(user_data_dir: str, storage_state: bytes | None) -> BrowserFetchHandle:
        raise RuntimeError("launch boom")

    with pytest.raises(RuntimeError, match="launch boom"):
        fetch_one(
            plan=render_plan(),
            venue_id="v",
            dest=tmp_path / "a.part",
            storage_state=None,
            budget=gate(),
            launch=launch,  # type: ignore[arg-type]
        )
    assert not tracked_mkdtemp[0].exists()


# ---------------------------------------------------------------------------
# T-9 Playwright 缺失 / 惰性 import
# ---------------------------------------------------------------------------


def test_t9_missing_playwright_raises_auth_required_with_install_hint(
    tmp_path: Path, tracked_mkdtemp: list[Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    with pytest.raises(AuthRequired) as excinfo:
        fetch_one(
            plan=render_plan(),
            venue_id="v",
            dest=tmp_path / "a.part",
            storage_state=None,
            budget=gate(),
        )
    assert "pip install paper-crawler[auth-browser]" in excinfo.value.detail
    assert "playwright install chromium" in excinfo.value.detail
    assert not tracked_mkdtemp[0].exists()  # 未装依赖同样零残留


def test_t9_module_import_does_not_load_playwright() -> None:
    assert "paper_crawler.browserfetch" in sys.modules
    assert "playwright" not in sys.modules


def test_default_launcher_wires_identity_header_and_storage_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """默认 launcher 装配面（真实 context 类本身归 runbook）：假 `playwright.sync_api` 模块
    让惰性 import 通过 → 断言**诚实身份串**以 `X-Paper-Crawler` 附加头下传、storage_state
    与一次性目录原样下传（红线 §2-3：绝不改写 UA 伪装成纯浏览器）。"""
    import types

    fake_module = types.ModuleType("playwright.sync_api")
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_module)
    seen: list[tuple[object, str, bytes | None, dict[str, str]]] = []

    class SpyContext:
        def __init__(
            self,
            sync_api: object,
            user_data_dir: str,
            storage_state: bytes | None,
            headers: dict[str, str],
        ) -> None:
            seen.append((sync_api, user_data_dir, storage_state, headers))

    monkeypatch.setattr(bf, "_PlaywrightFetchContext", SpyContext)
    launch = bf.playwright_launcher(identity_header="PaperCrawler/0.1.0 (personal research)")
    launch("/tmp/pc-bfetch-x", b'{"cookies": []}')

    sync_api, user_data_dir, storage_state, headers = seen[0]
    assert sync_api is fake_module
    assert user_data_dir == "/tmp/pc-bfetch-x"
    assert storage_state == b'{"cookies": []}'
    assert headers == {"X-Paper-Crawler": "PaperCrawler/0.1.0 (personal research)"}

    bf.playwright_launcher()("/tmp/pc-bfetch-y", None)  # 无身份串 → 不发该头
    assert seen[1][3] == {}


# ---------------------------------------------------------------------------
# AC-BF.2 静态红线（本模块无求解/绕过语义）
# ---------------------------------------------------------------------------


def _code_only(path: Path) -> str:
    """把源码投影为"**代码**文本"：剔除注释与字符串字面量（含文档字符串）。

    AC-BF.2 要判的是"代码里有没有求解/绕过语义"，而本模块的文档字符串**必须**能写出
    "不做 stealth/不调打码服务"这类否定式红线条款——按裸文本扫描会把红线声明本身
    误判为违规。故扫描对象取代码投影：真要引入这些能力，必然以 import/调用/标识符
    形态出现在代码里，投影后照样命中。
    """
    import tokenize

    kept: list[str] = []
    with path.open("rb") as handle:
        for token in tokenize.tokenize(handle.readline):
            if token.type not in (tokenize.COMMENT, tokenize.STRING):
                kept.append(token.string)
    return " ".join(kept).lower()


def test_ac_bf2_module_source_has_no_solver_or_evasion_semantics() -> None:
    """静态扫描：本通道**代码**零打码服务/UA 指纹轮换/stealth/质询脚本执行语义。"""
    source = _code_only(Path(bf.__file__))
    for forbidden in (
        "2captcha",
        "anticaptcha",
        "anti-captcha",
        "capsolver",
        "deathbycaptcha",
        "stealth",
        "undetected",
        "solve_captcha",
        "user_agent_rotation",
        "fake_useragent",
    ):
        assert forbidden not in source, f"browserfetch.py 出现禁用语义: {forbidden}"
    # 特征串单一权威源：判定全委 `ChallengeDetector`，本模块**整份文件**（含注释/文档）
    # 都不出现 CAPTCHA 特征串——不复制特征表，也就不可能在此处长出求解分支。
    raw = Path(bf.__file__).read_text(encoding="utf-8").lower()
    assert "hcaptcha" not in raw
    assert "recaptcha" not in raw
