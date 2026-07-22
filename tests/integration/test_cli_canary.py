"""`crawler canary` CLI 集成测试（T3：test-plan §4/§9 canary healthcheck 层）。

不依赖任何 venue（canary 只探测已注册 adapter 的 `healthcheck()`，与 venue 路由
无关）——每个用例用一个全新的空 `tmp_path/home`，`_env` 内的 `Config.load` +
`ensure_dirs` 按需建目录，不需要预先写 `venues/` 目录或 `config.toml`（同
`test_cli.py` 的 `_make_home` 相比，canary 用例明显更轻量）。

健康/不健康两态与 SKIP 态都借 `MockPlatformAdapter.healthcheck` 猴补丁注入
（`--adapter mock_platform` 收窄检查范围，不依赖 crossref/openreview/elsevier_sd
当前"未覆写 healthcheck 故默认 healthy"这一容易随后续 Phase 变化的现状）。
纯函数层（三态分类/排序/redact/markdown 渲染细节、`--record` 落盘内容/路径纯函数）
见 `tests/unit/test_canary.py`；这里只测 CLI 接线（`--adapter` 过滤、退出码、
未知 id 用法错、`--record` 实际落盘/默认不落盘）。

`--record` 用例用 `monkeypatch.chdir(tmp_path)` 隔离出一个临时"仓库根"——
`canary_record_path` 相对当前工作目录解析（不做仓库根探测，见 canary.py
docstring），借此避免测试真的写进本仓库的 `docs/` 树。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from paper_crawler.adapters.mock_platform import MockPlatformAdapter
from paper_crawler.cli import app
from paper_crawler.types import HealthReport

runner = CliRunner()


def _home(tmp_path: Path) -> Path:
    """canary 不读 venues/config.toml，一个全新的空目录即可（`_env` 按需建子目录）。"""
    return tmp_path / "home"


def test_canary_mock_healthy_exits_0(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["canary", "--adapter", "mock_platform", "--home", str(_home(tmp_path))]
    )

    assert result.exit_code == 0, result.output
    assert "| adapter | healthy | detail |" in result.output
    assert "| mock_platform | healthy |" in result.output


def test_canary_mock_unhealthy_exits_1(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def _fake_healthcheck(self: MockPlatformAdapter, session: object = None) -> HealthReport:
        return HealthReport(healthy=False, detail="mock injected failure")

    monkeypatch.setattr(MockPlatformAdapter, "healthcheck", _fake_healthcheck)

    result = runner.invoke(
        app, ["canary", "--adapter", "mock_platform", "--home", str(_home(tmp_path))]
    )

    assert result.exit_code == 1, result.output
    assert "| mock_platform | unhealthy | mock injected failure |" in result.output


def test_canary_not_implemented_renders_skip_and_exits_0(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """SKIP 行不影响退出码（DoD："NotImplementedError 捕获为未实现行，不算不健康"）。

    真实 stub adapter（crossref/openreview/elsevier_sd）现状是 healthcheck 尚未
    覆写、继承 AdapterBase 默认恒 healthy——不天然抛 NotImplementedError（改动
    stubs.py 不在本任务文件范围内）。用 mock_platform 注入等价场景验证
    canary.run_canary 的分类规则对任何 adapter 一视同仁。
    """

    def _fake_healthcheck(self: MockPlatformAdapter, session: object = None) -> HealthReport:
        raise NotImplementedError("stub until later")

    monkeypatch.setattr(MockPlatformAdapter, "healthcheck", _fake_healthcheck)

    result = runner.invoke(
        app, ["canary", "--adapter", "mock_platform", "--home", str(_home(tmp_path))]
    )

    assert result.exit_code == 0, result.output
    assert "| mock_platform | SKIP | stub until later |" in result.output


def test_canary_unknown_adapter_exits_2(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["canary", "--adapter", "not_a_real_adapter", "--home", str(_home(tmp_path))]
    )

    assert result.exit_code == 2
    assert "not_a_real_adapter" in result.output


def test_canary_without_filter_checks_all_registered_adapters(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """无 --adapter 时遍历全部注册 adapter（全部真实 adapter + mock + stubs）。

    本测试只验证遍历编排；真 healthcheck 属在线域（真实 adapter 的实现会发真实
    请求——合并期修复 2026-07-22：此前直调导致离线门禁打真网），故一律
    猴补丁为恒 healthy。真实健康探测由 `crawler canary` 在在线冒烟/运维场景执行。

    openalex/s2（T6）**不需要猴补丁**：本用例的 `_home(tmp_path)` 是全新空目录，
    无 `config.toml`，故二者 `healthcheck()` 在 key 未配置分支天然 `raise
    NotImplementedError` → SKIP（不发任何真实请求，不受本测试的"合并期修复"约束——
    该修复只针对**无条件**发真实请求的 healthcheck 实现）。
    """
    from paper_crawler.adapters.aaai_ojs.adapter import AaaiOjsAdapter
    from paper_crawler.adapters.acl_anthology.adapter import AclAnthologyAdapter
    from paper_crawler.adapters.arxiv.adapter import ArxivAdapter
    from paper_crawler.adapters.crossref.adapter import CrossrefAdapter
    from paper_crawler.adapters.cvf.adapter import CVFAdapter
    from paper_crawler.adapters.dblp.adapter import DblpAdapter
    from paper_crawler.adapters.neurips_proceedings.adapter import NeuripsProceedingsAdapter
    from paper_crawler.adapters.openreview.adapter import OpenReviewAdapter
    from paper_crawler.adapters.pmlr.adapter import PmlrAdapter
    from paper_crawler.adapters.unpaywall.adapter import UnpaywallAdapter

    def _fake_healthy(self: object, session: object = None) -> HealthReport:
        return HealthReport(healthy=True, detail="patched offline")

    monkeypatch.setattr(ArxivAdapter, "healthcheck", _fake_healthy)
    # crossref 已 Phase 3 T3 落地为真实 adapter：healthcheck 发真实请求，离线须猴补丁
    # （同其余真实 adapter；否则 socket 护栏拦截 → unhealthy → 退出码 1）。
    monkeypatch.setattr(CrossrefAdapter, "healthcheck", _fake_healthy)
    monkeypatch.setattr(OpenReviewAdapter, "healthcheck", _fake_healthy)
    monkeypatch.setattr(PmlrAdapter, "healthcheck", _fake_healthy)
    monkeypatch.setattr(AclAnthologyAdapter, "healthcheck", _fake_healthy)
    monkeypatch.setattr(CVFAdapter, "healthcheck", _fake_healthy)
    monkeypatch.setattr(AaaiOjsAdapter, "healthcheck", _fake_healthy)
    monkeypatch.setattr(NeuripsProceedingsAdapter, "healthcheck", _fake_healthy)
    monkeypatch.setattr(DblpAdapter, "healthcheck", _fake_healthy)
    monkeypatch.setattr(MockPlatformAdapter, "healthcheck", _fake_healthy)
    monkeypatch.setattr(UnpaywallAdapter, "healthcheck", _fake_healthy)

    result = runner.invoke(app, ["canary", "--home", str(_home(tmp_path))])

    assert result.exit_code == 0, result.output
    for adapter_id in (
        "mock_platform",
        "arxiv",
        "pmlr",
        "crossref",
        "openreview",
        "elsevier_sd",
        "acl_anthology",
        "cvf",
        "neurips_proceedings",
        "unpaywall",
        "openalex",  # T6（SKIP 行——无 key）
        "s2",  # T6（SKIP 行——无 key）
    ):
        assert adapter_id in result.output


# --- --record ------------------------------------------------------------------


def test_canary_record_writes_file_matching_terminal_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _fake_healthcheck(self: MockPlatformAdapter, session: object = None) -> HealthReport:
        return HealthReport(healthy=True, detail="ok")

    monkeypatch.setattr(MockPlatformAdapter, "healthcheck", _fake_healthcheck)
    monkeypatch.chdir(tmp_path)  # canary_record_path 相对 CWD 解析，隔离出临时"仓库根"

    result = runner.invoke(
        app,
        ["canary", "--adapter", "mock_platform", "--record", "--home", str(_home(tmp_path))],
    )

    assert result.exit_code == 0, result.output
    record_path = (
        tmp_path
        / "docs"
        / "testing"
        / "records"
        / "canary"
        / f"{date.today().isoformat()}-canary.md"
    )
    assert record_path.is_file()
    recorded = record_path.read_text(encoding="utf-8")
    assert "| mock_platform | healthy | ok |" in recorded
    # 同源数据：落盘内容与终端回显里的表格行一致。
    assert "| mock_platform | healthy | ok |" in result.output
    # 落盘提示打印相对路径（canary_record_path 本就相对 CWD 解析，不额外绝对化）。
    assert "docs/testing/records/canary/" in result.output
    assert f"{date.today().isoformat()}-canary.md" in result.output


def test_canary_without_record_flag_writes_no_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """默认行为不变：省略 `--record` 时不建目录、不落盘，只终端输出。"""

    def _fake_healthcheck(self: MockPlatformAdapter, session: object = None) -> HealthReport:
        return HealthReport(healthy=True, detail="ok")

    monkeypatch.setattr(MockPlatformAdapter, "healthcheck", _fake_healthcheck)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app, ["canary", "--adapter", "mock_platform", "--home", str(_home(tmp_path))]
    )

    assert result.exit_code == 0, result.output
    assert "| mock_platform | healthy | ok |" in result.output
    assert not (tmp_path / "docs").exists()


def test_canary_record_persists_even_when_unhealthy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """健康快照要如实留痕不健康态——不能因为 unhealthy 就跳过落盘。"""

    def _fake_healthcheck(self: MockPlatformAdapter, session: object = None) -> HealthReport:
        return HealthReport(healthy=False, detail="site down")

    monkeypatch.setattr(MockPlatformAdapter, "healthcheck", _fake_healthcheck)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["canary", "--adapter", "mock_platform", "--record", "--home", str(_home(tmp_path))],
    )

    assert result.exit_code == 1, result.output
    record_path = (
        tmp_path
        / "docs"
        / "testing"
        / "records"
        / "canary"
        / f"{date.today().isoformat()}-canary.md"
    )
    assert record_path.is_file()
    assert "| mock_platform | unhealthy | site down |" in record_path.read_text(encoding="utf-8")


# --- 凭证注入（检查单 #3：canary 装配 token/key + 限速域，不再体现匿名/未配置态）----------


def _cookie_header(adapter: object) -> str:
    """取 adapter 注入的 client 的 Cookie 头（无 client → 空串）。"""
    client = getattr(adapter, "_http", None)
    if client is None:
        return ""
    return client._client.headers.get("cookie", "")


def test_canary_binds_openreview_token_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """配置了 openreview_token → canary 为 openreview 注入携 `Cookie` 的专属 client（非匿名态）。

    openreview healthcheck 本身匿名可跑，故用 patched healthcheck 检视注入的 client 是否携
    token cookie——直证 canary 现在会装配凭证（此前用未绑定的新鲜实例，恒匿名）。
    """
    from paper_crawler.adapters.openreview.adapter import OpenReviewAdapter

    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text("[auth.openreview]\ntoken = 'tok-abc'\n", encoding="utf-8")

    def _probe(self: OpenReviewAdapter, session: object = None) -> HealthReport:
        bound = "accessToken" in _cookie_header(self)
        return HealthReport(healthy=bound, detail="token-bound" if bound else "anonymous")

    monkeypatch.setattr(OpenReviewAdapter, "healthcheck", _probe)
    result = runner.invoke(app, ["canary", "--adapter", "openreview", "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert "token-bound" in result.output
    assert "anonymous" not in result.output


def test_canary_openreview_anonymous_without_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """无 token → openreview 沿用共享匿名 client（对照组：确认上例的差异来自 token 注入）。"""
    from paper_crawler.adapters.openreview.adapter import OpenReviewAdapter

    monkeypatch.delenv("PAPER_CRAWLER_OPENREVIEW_TOKEN", raising=False)

    def _probe(self: OpenReviewAdapter, session: object = None) -> HealthReport:
        bound = "accessToken" in _cookie_header(self)
        return HealthReport(healthy=True, detail="token-bound" if bound else "anonymous")

    monkeypatch.setattr(OpenReviewAdapter, "healthcheck", _probe)
    result = runner.invoke(
        app, ["canary", "--adapter", "openreview", "--home", str(_home(tmp_path))]
    )
    assert result.exit_code == 0, result.output
    assert "anonymous" in result.output
    assert "token-bound" not in result.output


def test_canary_auth_gated_stub_skips(tmp_path: Path) -> None:
    """auth_gated 平台（elsevier_sd stub）无 session → healthcheck NotImplementedError → SKIP
    （B-M4：canary 不注入 session，二义分离于 pipeline 的 AuthRequired→BLOCKED）。"""
    result = runner.invoke(
        app, ["canary", "--adapter", "elsevier_sd", "--home", str(_home(tmp_path))]
    )
    assert result.exit_code == 0, result.output
    assert "| elsevier_sd | SKIP |" in result.output


def test_bind_healthcheck_credentials_returns_dedicated_clients(tmp_path: Path) -> None:
    """`_bind_healthcheck_credentials`：有 token/key → openreview + s2 各得专属携密 client。"""
    from paper_crawler.adapter import load_adapters
    from paper_crawler.cli import _bind_healthcheck_credentials, _env

    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text(
        "[auth.openreview]\ntoken = 't'\n[auth.s2]\napi_key = 'k'\n", encoding="utf-8"
    )
    with _env(home, False) as env:
        adapters = load_adapters()
        dedicated = _bind_healthcheck_credentials(env, adapters)
        try:
            assert len(dedicated) == 2  # openreview token client + s2 key client
            assert "accessToken" in _cookie_header(adapters["openreview"])
            s2_client = adapters["s2"]._http  # type: ignore[attr-defined]
            assert s2_client._client.headers.get("x-api-key") == "k"
        finally:
            for client in dedicated:
                client.close()


def test_register_rate_domains_prevents_config_failfast(tmp_path: Path) -> None:
    """A-M1：登记后每 adapter 的域可 `acquire` 不抛 CONFIG（否则注入带 limiter 的共享 client
    后 canary 逐请求探测撞未注册域 → 伪不健康）。"""
    from paper_crawler.adapter import load_adapters
    from paper_crawler.cli import _bind_healthcheck_credentials, _env

    with _env(_home(tmp_path), False) as env:
        adapters = load_adapters()
        dedicated = _bind_healthcheck_credentials(env, adapters)
        try:
            for adapter in adapters.values():
                for domain in adapter.domains:
                    env.ctx.limiter.acquire(domain)  # 已注册（含 alias）→ 不抛 CONFIG
        finally:
            for client in dedicated:
                client.close()
