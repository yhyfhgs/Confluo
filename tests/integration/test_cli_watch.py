"""`crawler watch` CLI 集成测试（Phase 2 T6）。

覆盖：用法校验（缺 venue/--all、二者同给、未知 venue、非 preprint venue → 退出 2）、
happy-path（preprint venue 经 `_http_client_factory` seam 注入 MockTransport 零真实网络
→ 退出 0 + 报告）、`--all` 过滤 preprint venue、config `[identity].email` 缺省 warn +
UA 接线。

网络零真实：CLI 的 `_build_env` 默认建真实 HttpClient，本测试 monkeypatch 模块级
`cli._http_client_factory` seam 注入 `httpx.MockTransport` client（offline 门禁 socket
护栏亦会拦真实连接）。
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import yaml
from typer.testing import CliRunner

from helpers.arxiv_fixtures import OaiRecord, build_oai_listrecords
from paper_crawler import cli as cli_module
from paper_crawler.cli import app
from paper_crawler.config import Config
from paper_crawler.http import HttpClient

runner = CliRunner()

_ARXIV_VENUE = "arxiv_cs_lg"
_MOCK_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"


def _write_config(home: Path, *, email: str | None) -> None:
    # rate.scale 高值：CLI 走真实 time.sleep 限速；arxiv 1req/3s 会真睡 ~3s/桶。
    # 放大 refill 速率把限速 wait 压到亚毫秒（同 make_env 的 retry_scale 加速手法），
    # 不改语义只提速测试。
    lines = ["[paths]", 'venues_dirs = ["venues"]', "[rate]", "scale = 1000"]
    if email is not None:
        lines += ["[identity]", f'email = "{email}"']
    (home / "config.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_arxiv_venue(venues_dir: Path) -> None:
    doc: dict[str, object] = {
        "id": _ARXIV_VENUE,
        "kind": "preprint_channel",
        "names": {"full": "arXiv cs.LG", "aliases": ["arxiv-cs-lg"]},
        "field": ["cs_ai"],
        "metadata_source": "arxiv",
        "fulltext_source": "arxiv",
        "quirks": {"inception": "2024-01", "arxiv_set": "cs", "arxiv_category": "cs.LG"},
        "status": "active",
    }
    (venues_dir / "arxiv-cs-lg.yaml").write_text(
        yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8"
    )


def _write_journal_venue(venues_dir: Path) -> None:
    """非 preprint（kind=journal）venue——watch 应拒绝（用法错）。"""
    doc: dict[str, object] = {
        "id": "mock_journal",
        "kind": "journal",
        "names": {"full": "Mock Journal", "aliases": ["MJ"]},
        "field": ["cs_ai"],
        "identifiers": {"issn": ["0000-0000"]},
        "metadata_source": "mock_platform",
        "fulltext_source": "mock_platform",
        "status": "active",
    }
    (venues_dir / "mock-journal.yaml").write_text(
        yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8"
    )


def _make_home(
    tmp_path: Path, *, arxiv: bool = True, journal: bool = False, email: str | None = None
) -> Path:
    home = tmp_path / "home"
    venues_dir = home / "venues"
    venues_dir.mkdir(parents=True)
    _write_config(home, email=email)
    if arxiv:
        _write_arxiv_venue(venues_dir)
    if journal:
        _write_journal_venue(venues_dir)
    return home


def _patch_mock_client(
    monkeypatch: pytest.MonkeyPatch, records: list[OaiRecord] | None = None
) -> None:
    """把 `cli._http_client_factory` 换成 MockTransport client（零真实网络）。"""
    recs = records if records is not None else [OaiRecord("2406.00001", "One")]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=build_oai_listrecords(recs))

    def factory(_config: Config) -> HttpClient:
        return HttpClient(user_agent=_MOCK_UA, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(cli_module, "_http_client_factory", factory)


# --- 用法校验（退出 2）----------------------------------------------------------------------


def test_watch_no_venue_no_all_exits_2(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["watch", "--home", str(home)])
    assert result.exit_code == 2
    assert "VENUE" in result.output or "--all" in result.output


def test_watch_venue_and_all_together_exits_2(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["watch", _ARXIV_VENUE, "--all", "--home", str(home)])
    assert result.exit_code == 2


def test_watch_unknown_venue_exits_2(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["watch", "no_such_venue", "--home", str(home)])
    assert result.exit_code == 2
    assert "no_such_venue" in result.output


def test_watch_non_preprint_venue_exits_2(tmp_path: Path) -> None:
    """journal venue → watch 用法错（退出 2）——watch 仅支持 preprint_channel。"""
    home = _make_home(tmp_path, arxiv=False, journal=True)
    result = runner.invoke(app, ["watch", "mock_journal", "--home", str(home)])
    assert result.exit_code == 2
    assert "preprint_channel" in result.output


# --- happy-path（seam 注入 MockTransport）---------------------------------------------------


def test_watch_preprint_venue_happy_path_exits_0(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = _make_home(tmp_path, email="me@lab.edu")
    _patch_mock_client(
        monkeypatch, [OaiRecord("2406.00001", "One"), OaiRecord("2406.00002", "Two")]
    )
    result = runner.invoke(app, ["watch", _ARXIV_VENUE, "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert "Pipeline Report" in result.output
    assert "watch[arxiv_cs_lg]: +2 new paper(s)" in result.output


def test_watch_all_filters_preprint_venues(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`--all` 只对 preprint venue 执行——同目录的 journal venue 被跳过。"""
    home = _make_home(tmp_path, arxiv=True, journal=True, email="me@lab.edu")
    _patch_mock_client(monkeypatch, [OaiRecord("2406.00001", "One")])
    result = runner.invoke(app, ["watch", "--all", "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert _ARXIV_VENUE in result.output
    assert "mock_journal" not in result.output  # 非 preprint 不在 watch 目标
    assert "合计" in result.output


def test_watch_all_no_preprint_venue_exits_0_with_message(tmp_path: Path) -> None:
    """无 preprint venue（只有 journal）→ `--all` 退出 0 并提示无目标。"""
    home = _make_home(tmp_path, arxiv=False, journal=True)
    result = runner.invoke(app, ["watch", "--all", "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert "无目标" in result.output


# --- config [identity].email 缺省 warn + UA 接线 -------------------------------------------


def test_watch_warns_when_identity_email_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = _make_home(tmp_path, email=None)  # 无 [identity].email
    _patch_mock_client(monkeypatch)
    result = runner.invoke(app, ["watch", _ARXIV_VENUE, "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert "identity.email" in result.output  # obslog WARNING 经控制台 handler 可见


def test_watch_no_warning_when_identity_email_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = _make_home(tmp_path, email="me@lab.edu")
    _patch_mock_client(monkeypatch)
    result = runner.invoke(app, ["watch", _ARXIV_VENUE, "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert "identity.email 未配置" not in result.output


# --- _http_client_factory：config email → UA mailto 接线 ------------------------------------


def test_http_client_factory_uses_config_email(tmp_path: Path) -> None:
    """config `[identity].email` → 组装的 client UA 携 `mailto:`（显式注入通道）。"""
    home = tmp_path / "home"
    home.mkdir()
    _write_config(home, email="wired@lab.edu")
    config = Config.load(home=home)
    client = cli_module._http_client_factory(config)
    try:
        ua = client._client.headers["user-agent"]
    finally:
        client.close()
    assert "mailto:wired@lab.edu" in ua


def test_http_client_factory_omits_mailto_without_config_email(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    _write_config(home, email=None)
    config = Config.load(home=home)
    client = cli_module._http_client_factory(config)
    try:
        ua = client._client.headers["user-agent"]
    finally:
        client.close()
    assert "mailto:" not in ua
    assert ua == "PaperCrawler/0.1.0 (personal research)"
