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
    """
    from paper_crawler.adapters.aaai_ojs.adapter import AaaiOjsAdapter
    from paper_crawler.adapters.acl_anthology.adapter import AclAnthologyAdapter
    from paper_crawler.adapters.arxiv.adapter import ArxivAdapter
    from paper_crawler.adapters.crossref.adapter import CrossrefAdapter
    from paper_crawler.adapters.cvf.adapter import CVFAdapter
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
