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

import paper_crawler.auth.store as store_mod
from paper_crawler.adapters.mock_platform import MockPlatformAdapter
from paper_crawler.cli import app
from paper_crawler.types import HealthReport

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolated_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    """keyring 绝缘（R2c 独立审查 Minor #3；同 `test_auth_key_seam.py` 的 autouse `_isolated`
    口径统一）：R2c 起 `_bind_healthcheck_credentials` 经 `_bind_auth_key_clients` →
    `CredentialStore.read_key` 会先探真实 keyring（本仓 `.venv` 确有装 `keyring` 包，macOS
    上会真的弹 Keychain）——凡调用该函数的用例（含本文件修复前就有的两条：
    `test_bind_healthcheck_credentials_returns_dedicated_clients`/
    `test_register_rate_domains_prevents_config_failfast`，以及新增的两条 elsevier/wiley
    用例）都会触达这条路径，不止"新增"的两条。绝不触宿主 OS Keychain（`tests/helpers/
    auth.py:3` 红线）——本 autouse fixture 把 `_import_keyring` 替换为返回 `None`，令
    `read_key` 走 `_CONFIG_KEY_SLOTS` 委派 config 槽这一分支（keyring 优先级本身已由
    `test_auth_key_seam.py` 覆盖，不在本文件重复）。对不触及该路径的其余 canary 用例
    （如 openreview token 那组）无影响——它们从不调用 `_import_keyring`。
    """
    monkeypatch.setattr(store_mod, "_import_keyring", lambda: None)


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

    历史注：Phase 3 前部分 adapter healthcheck 曾未覆写、继承默认恒 healthy；现全部真实
    实现（无凭证平台抛 NotImplementedError→SKIP）。本测试不依赖该现状（改动
    相关注释随 P4-T3 stub 退役同步）。用 mock_platform 注入等价场景验证
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


# 断言列表须与 `load_adapters()` 实际注册表全集保持同步——Phase 4 M2b 检查单 #15d 发现
# 本列表此前遗漏了 aaai_ojs/dblp；Phase 4 T8 controller 收尾又补上 oup_silverchair/wiley
# （同模式第二次）；post-phase5-audit §3[O4] 发现 Phase 5 新增的 aea 又漏——"注册了却没
# 验证"反模式第三次复现（aea healthcheck 天然 SKIP，逐条 `in result.output` 断言本身仍能
# 通过，只是从未真正要求 aea 出现，漏了也不会报错，故测试仍绿）。为根治该反模式，本模块
# 级列表改配一条**集合等值自断言**（见下方测试函数体）：与 `load_adapters()` 的实际返回
# 集合动态比对，而非仅逐个 `in` 检查——未来任何新 adapter 注册后忘记同步本列表，多了/
# 少了任何一个都会响亮失败，不再依赖人工发现第四次。
_EXPECTED_CANARY_ADAPTER_IDS = (
    "mock_platform",
    "arxiv",
    "pmlr",
    "crossref",
    "openreview",
    "elsevier_sd",  # T3 auth_gated 无 key → SKIP 行
    "acl_anthology",
    "cvf",
    "aaai_ojs",
    "neurips_proceedings",
    "dblp",
    "unpaywall",
    "oup_silverchair",  # T4 auth_gated 无 session → SKIP 行
    "wiley",  # T-wiley auth_gated 无 token → SKIP 行
    "openalex",  # T6（SKIP 行——无 key）
    "s2",  # T6（SKIP 行——无 key）
    "econsoc",  # Phase 5 T6（open_access；healthcheck 猴补丁为 healthy，同 aaai_ojs）
    "ssrn",  # Phase 5 T4（healthcheck 猴补丁为 healthy——经内部 crossref lookup 发真实请求）
    "nber",  # Phase 5 T3（open_access，healthcheck 猴补丁为 healthy）
    "aea",  # Phase 5 T5（auth_gated 无网络探针 → 恒 SKIP，同 elsevier_sd；此前漏列本次补齐）
    "repec",  # Phase 7 T8（零网络 enrich；无快照 → NotImplementedError → SKIP 行）
)


def test_canary_without_filter_checks_all_registered_adapters(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """无 --adapter 时遍历全部注册 adapter（全部真实 adapter + mock；stubs 已于 P4 清零）。

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
    from paper_crawler.adapters.econsoc.adapter import EconsocAdapter
    from paper_crawler.adapters.nber.adapter import NberAdapter
    from paper_crawler.adapters.neurips_proceedings.adapter import NeuripsProceedingsAdapter
    from paper_crawler.adapters.openreview.adapter import OpenReviewAdapter
    from paper_crawler.adapters.pmlr.adapter import PmlrAdapter
    from paper_crawler.adapters.ssrn.adapter import SsrnAdapter
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
    # econsoc（Phase 5 T6）healthcheck 发真实 TE OAI Identify 请求（同 aaai_ojs OAI 探针）→
    # 离线须猴补丁，否则 socket 护栏拦截 → unhealthy → 退出码 1。
    monkeypatch.setattr(EconsocAdapter, "healthcheck", _fake_healthy)
    monkeypatch.setattr(DblpAdapter, "healthcheck", _fake_healthy)
    monkeypatch.setattr(MockPlatformAdapter, "healthcheck", _fake_healthy)
    monkeypatch.setattr(UnpaywallAdapter, "healthcheck", _fake_healthy)
    # ssrn（Phase 5 T4）healthcheck 经内部 crossref lookup **无条件**发真实请求（同 crossref/
    # arxiv 等）——离线须猴补丁，否则 socket 护栏拦截 → unhealthy → 退出码 1。
    monkeypatch.setattr(SsrnAdapter, "healthcheck", _fake_healthy)
    # Phase 5 T3 nber：healthcheck 发真实请求（w30000 首 chunk %PDF 探测），离线须猴补丁。
    monkeypatch.setattr(NberAdapter, "healthcheck", _fake_healthy)

    result = runner.invoke(app, ["canary", "--home", str(_home(tmp_path))])

    assert result.exit_code == 0, result.output

    # 集合等值自断言（post-phase5-audit §3[O4]/§6 处置 4：根治"注册了却没验证"反模式，
    # 已第三次复现——aaai_ojs/dblp → oup_silverchair/wiley → aea）：与 `load_adapters()`
    # 的实际注册表全集动态比对，而非仅逐个 `in` 检查。任何一侧多了/少了任何一个 adapter_id
    # 都会在这里响亮失败——不再需要靠人工记得同步 `_EXPECTED_CANARY_ADAPTER_IDS`。
    from paper_crawler.adapter import load_adapters

    assert set(_EXPECTED_CANARY_ADAPTER_IDS) == set(load_adapters())

    # 逐个校验每个 adapter_id 确实出现在 canary 的终端输出里（集合等值只保证"清单本身
    # 与注册表一致"，不保证 CLI 真的把每一行都渲染出来——两条断言互补，缺一不可）。
    for adapter_id in _EXPECTED_CANARY_ADAPTER_IDS:
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


def test_bind_healthcheck_credentials_injects_elsevier_and_wiley(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """R2c（R2a 顾虑①闭合）：配了 elsevier api_key / wiley token → canary 的
    `_bind_healthcheck_credentials` 也要把它们注入到（canary 自己那份独立 `load_adapters()`
    新鲜实例的）adapter 上——离线断言注入本身，不发真实网络。

    修复前：`_bind_healthcheck_credentials` 只装配 openreview/enrich 三源，完全没有 elsevier/
    wiley 分支——即便 `pull`/`grab` 侧（R2a 的 `_bind_auth_key_clients`）已能正确鉴权，canary
    这份独立实例的 `_api_key`/`_token` 仍恒 None，`healthcheck` 恒 `NotImplementedError`→SKIP，
    体现为"配了 key 也 SKIP"（本用例在修复前会因 `els._api_key is None` 失败）。

    读取方式与 `pull`/`grab` 侧完全一致（同一 `_bind_auth_key_clients`，keyring 优先于
    config 槽——本用例只需证明"注入发生"，keyring 优先级已由 `test_auth_key_seam.py` 覆盖，
    不在此重复）。
    """
    from paper_crawler.adapter import load_adapters
    from paper_crawler.adapters.elsevier_sd.adapter import ElsevierScienceDirectAdapter
    from paper_crawler.adapters.wiley.adapter import TDM_TOKEN_HEADER, WileyAdapter
    from paper_crawler.cli import _bind_healthcheck_credentials, _env

    monkeypatch.delenv("PAPER_CRAWLER_ELSEVIER_API_KEY", raising=False)
    monkeypatch.delenv("PAPER_CRAWLER_ELSEVIER_INSTTOKEN", raising=False)
    monkeypatch.delenv("PAPER_CRAWLER_WILEY_TDM_TOKEN", raising=False)

    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text(
        '[auth.elsevier]\napi_key = "els-key-abc"\n[auth.wiley]\ntoken = "wiley-tok-xyz"\n',
        encoding="utf-8",
    )
    with _env(home, False) as env:
        adapters = load_adapters()
        dedicated = _bind_healthcheck_credentials(env, adapters)
        try:
            els = adapters["elsevier_sd"]
            wiley = adapters["wiley"]
            assert isinstance(els, ElsevierScienceDirectAdapter)
            assert isinstance(wiley, WileyAdapter)

            assert els._api_key == "els-key-abc"  # 此前恒 None
            assert wiley._token == "wiley-tok-xyz"  # 此前恒 None

            els_headers = dict(els._client()._client.headers)  # noqa: SLF001
            assert els_headers.get("x-els-apikey") == "els-key-abc"
            wiley_headers = dict(wiley._client()._client.headers)  # noqa: SLF001
            assert wiley_headers.get(TDM_TOKEN_HEADER.lower()) == "wiley-tok-xyz"

            # 携密专属 client，绝不是共享 env.http（凭证隔离红线，同 R2a）。
            assert els._client() is not env.http
            assert wiley._client() is not env.http
        finally:
            for client in dedicated:
                client.close()


def test_bind_healthcheck_credentials_no_elsevier_wiley_keys_stays_unchanged(
    tmp_path: Path,
) -> None:
    """对照组：无 elsevier/wiley 凭证配置 → 不注入、不报错，两 adapter 仍沿用共享
    client（`_bind_auth_key_clients` 既有的"无凭证=行为不变"契约，canary 侧同样成立）。"""
    from paper_crawler.adapter import load_adapters
    from paper_crawler.adapters.elsevier_sd.adapter import ElsevierScienceDirectAdapter
    from paper_crawler.adapters.wiley.adapter import WileyAdapter
    from paper_crawler.cli import _bind_healthcheck_credentials, _env

    with _env(_home(tmp_path), False) as env:
        adapters = load_adapters()
        dedicated = _bind_healthcheck_credentials(env, adapters)
        try:
            els = adapters["elsevier_sd"]
            wiley = adapters["wiley"]
            assert isinstance(els, ElsevierScienceDirectAdapter)
            assert isinstance(wiley, WileyAdapter)
            assert els._api_key is None
            assert wiley._token is None
            assert els._client() is env.http
            assert wiley._client() is env.http
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
