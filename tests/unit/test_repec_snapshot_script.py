"""`scripts/repec_snapshot.py` 单测：裁决三条件 (a)/(b)/(c) 的行为锁。

**为何本文件存在**：D-035 决策 3 如实记过"scripts/ 不占门禁覆盖 ⇒ 镜像回退与校验逻辑无
自动化测试，靠 T19 人工核验"。但**合规条件的判定逻辑**（robots 从其规则、拒绝信号即停手、
host 一致性、间隔/请求数下上限、记账行归属）是可纯离线测的——网络往返用假 transport 顶掉
即可。把"合规判定"与"真实取回"分开：前者机器锁死，后者留给 T19。

`scripts/` 非 Python 包，经 `importlib.util` 按路径动态加载（同 `test_budget_ledger.py`）。
全部用例走 `tmp_path` + `httpx.MockTransport`，零真实网络（`tests/conftest.py` 的 socket 护栏
另有兜底）。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import httpx
import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "repec_snapshot.py"
_REDIF = b"Template-Type: ReDIF-Paper 1.0\nTitle: Fixture\nHandle: RePEc:nbr:nberwo:5\n"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("repec_snapshot", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script() -> ModuleType:
    return _load_module()


@pytest.fixture
def stub_client(script: ModuleType, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """把脚本的 `_client` 换成挂 `MockTransport` 的 client；返回登记 handler 的函数。"""

    def _install(handler) -> list[httpx.Request]:  # noqa: ANN001
        seen: list[httpx.Request] = []

        def _recording(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return handler(request)

        monkeypatch.setattr(
            script,
            "_client",
            lambda ua: httpx.Client(
                transport=httpx.MockTransport(_recording),
                headers={"User-Agent": ua},
                follow_redirects=True,
            ),
        )
        return seen

    return _install


# --- 条件 (a)：robots 从其规则；探的是**实际使用的目标镜像** ----------------------------------


def test_robots_disallow_stops_the_run(script: ModuleType, stub_client) -> None:  # noqa: ANN001
    stub_client(lambda request: httpx.Response(200, text="User-agent: *\nDisallow: /RePEc/\n"))
    verdict = script.check_robots("www2.nber.org", "/RePEc/nbr/nberwo/nberwo.rdf", "UA")
    assert verdict.readable is True
    assert verdict.allowed is False


def test_robots_allow_lets_the_run_proceed(script: ModuleType, stub_client) -> None:  # noqa: ANN001
    stub_client(lambda request: httpx.Response(200, text="User-agent: *\nDisallow: /cgi-bin/\n"))
    verdict = script.check_robots("www2.nber.org", "/RePEc/nbr/nberwo/nberwo.rdf", "UA")
    assert verdict.readable is True
    assert verdict.allowed is True


def test_robots_403_is_unreadable_not_allowed(script: ModuleType, stub_client) -> None:  # noqa: ANN001
    """[LIVE 2026-07-27] 的实况：403 ⇒ 无可判读规则 ⇒ 走裁决条件 (b)，而非"判定为放行"。"""
    stub_client(lambda request: httpx.Response(403, text="Forbidden"))
    verdict = script.check_robots("www2.nber.org", "/RePEc/", "UA")
    assert verdict.readable is False
    assert "403" in verdict.detail


def test_robots_connection_failure_is_unreadable(script: ModuleType, stub_client) -> None:  # noqa: ANN001
    def _boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("TLS handshake aborted")

    stub_client(_boom)
    verdict = script.check_robots("repec.nber.org", "/RePEc/", "UA")
    assert verdict.readable is False
    assert "连接层失败" in verdict.detail


def test_robots_is_checked_against_the_mirror_actually_used(
    script: ModuleType, stub_client
) -> None:  # noqa: ANN001
    """条款修订后的核心：探的域＝取数的域（REP 按 origin 生效）。"""
    seen = stub_client(lambda request: httpx.Response(200, text="User-agent: *\n"))
    script.check_robots("repec.nber.org", "/RePEc/", "UA")
    assert seen[0].url.host == "repec.nber.org"


def test_url_host_must_match_mirror(script: ModuleType) -> None:
    """堵死"核了 A 域 robots、却从 B 域取数"——形式合规、实质无效。"""
    problem = script._validate_request_plan(
        10.0, ["https://repec.nber.org/RePEc/x.rdf"], "www2.nber.org"
    )
    assert problem is not None
    assert "robots 核验按 origin 生效" in problem


def test_matching_host_passes_validation(script: ModuleType) -> None:
    assert (
        script._validate_request_plan(10.0, ["https://www2.nber.org/x.rdf"], "www2.nber.org")
        is None
    )


# --- 条件 (b)：间隔下限 / 请求数上限，越界响亮拒绝而非静默钳值 --------------------------------


def test_delay_below_floor_is_refused_not_clamped(script: ModuleType) -> None:
    problem = script._validate_request_plan(2.0, ["https://www2.nber.org/x.rdf"], "www2.nber.org")
    assert problem is not None
    assert "不接受更激进的值" in problem


def test_more_urls_than_budget_is_refused(script: ModuleType) -> None:
    urls = [f"https://www2.nber.org/{i}.rdf" for i in range(5)]
    problem = script._validate_request_plan(10.0, urls, "www2.nber.org")
    assert problem is not None
    assert "T8-bulk" in problem


def test_request_budget_constant_matches_plan(script: ModuleType) -> None:
    assert script.MAX_REQUESTS == 4  # plan §3 T8-bulk ≤4
    assert script.MIN_DELAY_SECONDS >= 10.0


# --- 条件 (c)：拒绝信号与 5xx 均出列回报，绝不裸 traceback ------------------------------------


@pytest.mark.parametrize("status", [401, 403, 429, 451])
def test_explicit_refusal_retires_the_channel(
    script: ModuleType, stub_client, tmp_path: Path, status: int
) -> None:  # noqa: ANN001
    stub_client(lambda request: httpx.Response(status, text="no"))
    with pytest.raises(script.ChannelRetired) as excinfo:
        script.fetch_files(
            ["https://www2.nber.org/x.rdf"], user_agent="UA", delay=0.0, root=tmp_path
        )
    assert "明确拒绝" in str(excinfo.value)
    assert "出列回报" in str(excinfo.value)


@pytest.mark.parametrize("status", [500, 503])
def test_server_error_retires_instead_of_escaping_as_traceback(
    script: ModuleType, stub_client, tmp_path: Path, status: int
) -> None:  # noqa: ANN001
    """5xx 曾经从 `raise_for_status()` 逃逸成裸 traceback、绕开出列回报（docstring 是假陈述）。"""
    stub_client(lambda request: httpx.Response(status, text="oops"))
    with pytest.raises(script.ChannelRetired) as excinfo:
        script.fetch_files(
            ["https://www2.nber.org/x.rdf"], user_agent="UA", delay=0.0, root=tmp_path
        )
    assert "服务端错误" in str(excinfo.value)
    assert "不重试" in str(excinfo.value)


def test_other_4xx_also_retires(script: ModuleType, stub_client, tmp_path: Path) -> None:  # noqa: ANN001
    stub_client(lambda request: httpx.Response(404, text="gone"))
    with pytest.raises(script.ChannelRetired):
        script.fetch_files(
            ["https://www2.nber.org/x.rdf"], user_agent="UA", delay=0.0, root=tmp_path
        )


def test_connection_failure_retires(script: ModuleType, stub_client, tmp_path: Path) -> None:  # noqa: ANN001
    def _boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("reset")

    stub_client(_boom)
    with pytest.raises(script.ChannelRetired):
        script.fetch_files(
            ["https://www2.nber.org/x.rdf"], user_agent="UA", delay=0.0, root=tmp_path
        )


# --- 落盘与 manifest：原样字节 + sha256，与 adapter 的校验口径对得上 --------------------------


def test_fetch_writes_bytes_verbatim_and_manifest_matches_adapter_expectations(
    script: ModuleType, stub_client, tmp_path: Path
) -> None:  # noqa: ANN001
    stub_client(lambda request: httpx.Response(200, content=_REDIF))
    files = script.fetch_files(
        ["https://www2.nber.org/RePEc/nbr/nberwo/nberwo.rdf"],
        user_agent="UA",
        delay=0.0,
        root=tmp_path,
    )
    written = tmp_path / files[0].name
    assert written.read_bytes() == _REDIF  # 原样字节，不做任何规整
    assert files[0].sha256 == hashlib.sha256(_REDIF).hexdigest()

    script.write_manifest(
        tmp_path,
        mirror="www2.nber.org",
        urls=["https://www2.nber.org/RePEc/nbr/nberwo/nberwo.rdf"],
        files=files,
    )
    payload = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert payload["record_count"] == 1  # 由实际解析结果回填，非硬编码

    # 端到端契约：脚本产出的快照必须能被 adapter 的完整性校验接受
    from paper_crawler.adapters.repec.adapter import RepecAdapter

    assert RepecAdapter(tmp_path).healthcheck().healthy is True


# --- P2-⑥：记账提示按预算行分开（robots 记 T8-robots、数据记 T8-bulk）-------------------------


def test_ledger_reminder_splits_rows(script: ModuleType, capsys: pytest.CaptureFixture) -> None:
    """曾把 `len(urls)+1` 整个报给 T8-bulk：bulk 行虚高 + robots 行漏记，两行同时失真。"""
    script._print_ledger_reminder(2)
    out = capsys.readouterr().out
    assert "--row T8-robots" in out
    assert "--count 1" in out
    assert "--row T8-bulk" in out
    assert "--count 2" in out
    assert "两行分开记" in out
