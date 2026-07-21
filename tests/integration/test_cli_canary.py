"""`crawler canary` CLI 集成测试（T3：test-plan §4/§9 canary healthcheck 层）。

不依赖任何 venue（canary 只探测已注册 adapter 的 `healthcheck()`，与 venue 路由
无关）——每个用例用一个全新的空 `tmp_path/home`，`_env` 内的 `Config.load` +
`ensure_dirs` 按需建目录，不需要预先写 `venues/` 目录或 `config.toml`（同
`test_cli.py` 的 `_make_home` 相比，canary 用例明显更轻量）。

健康/不健康两态与 SKIP 态都借 `MockPlatformAdapter.healthcheck` 猴补丁注入
（`--adapter mock_platform` 收窄检查范围，不依赖 crossref/openreview/elsevier_sd
当前"未覆写 healthcheck 故默认 healthy"这一容易随后续 Phase 变化的现状）。
纯函数层（三态分类/排序/redact/markdown 渲染细节）见
`tests/unit/test_canary.py`；这里只测 CLI 接线（`--adapter` 过滤、退出码、
未知 id 用法错）。
"""

from __future__ import annotations

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


def test_canary_without_filter_checks_all_registered_adapters(tmp_path: Path) -> None:
    result = runner.invoke(app, ["canary", "--home", str(_home(tmp_path))])

    # 当前四个内置 adapter 均未覆写 healthcheck（继承 AdapterBase 默认恒 healthy），
    # 全部 healthy → 退出 0；即便未来某个 stub 改为抛 NotImplementedError，SKIP
    # 依旧不影响退出码，这条断言对该预期中的后续变化保持稳健。
    assert result.exit_code == 0, result.output
    for adapter_id in ("mock_platform", "crossref", "openreview", "elsevier_sd"):
        assert adapter_id in result.output
