"""OpenReview T4 集成 + AC-2.2 离线层（design/adapters/openreview.md §7）。

零真实网络：CLI `pull` 全链路经 `cli._http_client_factory` / `cli._openreview_client_factory`
两个 seam 注入 `httpx.MockTransport` client。覆盖：

- AC-2.2 离线：`pull iclr --year 2024 --limit 10` 全链回放——accepted 过滤对账（15 note →
  12 接收）、resolve pdf plan、fetch 10 个 %PDF、limit 截断、退出码。
- v1/v2 双路：2024（v2，api2 端点 + .value 嵌套）与 2014（v1，api 端点 + 直取）各一次
  enumerate 全链，断言走对端点、解析对形态。
- T4 token/BLOCKED/resume（复用 AC-1.5 模式）：无 token→notes 403→enumerate 整批
  BLOCKED(auth)→配置 token（env）+ resume --all→重跑完成；token 值经 redact 不入日志。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
import yaml
from typer.testing import CliRunner

from helpers.openreview_fixtures import fixture_bytes
from paper_crawler import cli as cli_module
from paper_crawler.cli import app
from paper_crawler.config import Config
from paper_crawler.http import HttpClient
from paper_crawler.ratelimit import RateLimiter
from paper_crawler.storage.db import Database

runner = CliRunner()

_MOCK_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"
_TOKEN = "sekret-openreview-token-value"
_PDF = b"%PDF-1.7\n" + b"openreview-synthetic-pdf\n" + b"0" * 400 + b"\n%%EOF\n"


# --- home 装配（iclr venue + rate scale 快进）------------------------------------------------


def _write_iclr_home(base: Path, *, with_token_config: bool = False) -> Path:
    home = base / "home"
    venues_dir = home / "venues"
    venues_dir.mkdir(parents=True)
    config_lines = ["[paths]", 'venues_dirs = ["venues"]', "", "[rate]", "scale = 1000.0"]
    if with_token_config:
        config_lines += ["", "[auth.openreview]", f'token = "{_TOKEN}"']
    (home / "config.toml").write_text("\n".join(config_lines) + "\n", encoding="utf-8")
    doc = {
        "id": "iclr",
        "kind": "conference",
        "names": {
            "full": "International Conference on Learning Representations",
            "aliases": ["ICLR"],
        },
        "field": ["cs_ai"],
        "tier": "T1",
        "identifiers": {"dblp_key": "conf/iclr"},
        "metadata_source": "openreview",
        "fulltext_source": "openreview",
        "auth": {"level": "free_account", "provider_hint": "openreview"},
        "quirks": {"openreview_group_overrides": {}},
        "status": "active",
    }
    (venues_dir / "iclr.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return home


# --- 合成响应构造 ----------------------------------------------------------------------------


def _v2_group(vid: str) -> bytes:
    return json.dumps({"groups": [{"id": vid, "domain": vid}], "count": 1}).encode()


def _v1_group(vid: str) -> bytes:
    return json.dumps({"groups": [{"id": vid, "members": []}], "count": 1}).encode()


def _v2_notes_page(vid: str, *, accepted: int) -> bytes:
    """v2 notes 页：`accepted` 条接收（含 pdf）+ 3 条未接收（Submission/Withdrawn/Desk_Reject）。"""
    notes: list[dict[str, object]] = []
    for i in range(accepted):
        fid = f"acc{i:04d}"
        notes.append(
            {
                "id": fid,
                "forum": fid,
                "content": {
                    "title": {"value": f"Accepted Paper {i}"},
                    "venueid": {"value": vid},
                    "pdf": {"value": f"/pdf/{fid}{'0' * 34}.pdf"},
                },
            }
        )
    for suffix in ("Submission", "Withdrawn_Submission", "Desk_Rejected_Submission"):
        notes.append(
            {
                "id": f"rej{suffix}",
                "forum": f"rej{suffix}",
                "content": {
                    "title": {"value": f"Rejected {suffix}"},
                    "venueid": {"value": f"{vid}/{suffix}"},
                },
            }
        )
    return json.dumps({"notes": notes, "count": len(notes)}).encode()


def _v1_notes_page(vid: str) -> bytes:
    note = {
        "id": "v1acc",
        "forum": "v1acc",
        "content": {"title": "Old V1 Paper", "venueid": vid, "arxiv": "1312.6173"},
    }
    return json.dumps({"notes": [note], "count": 1}).encode()


# --- MockTransport handler + seam patch ------------------------------------------------------


def _make_handler(
    *, accepted: int, require_cookie: bool
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/pdf" in path:
            return httpx.Response(200, content=_PDF)
        if "/groups" in path:
            vid = request.url.params.get("id", "ICLR.cc/2024/Conference")
            body = _v1_group(vid) if "/2014/" in vid else _v2_group(vid)
            return httpx.Response(200, content=body)
        # /notes：token 门——require_cookie 且无 cookie → 403 ChallengeRequiredError。
        if require_cookie and not request.headers.get("cookie"):
            return httpx.Response(
                403, content=json.dumps({"name": "ChallengeRequiredError", "status": 403}).encode()
            )
        vid = request.url.params.get("content.venueid", "ICLR.cc/2024/Conference")
        body = _v1_notes_page(vid) if "/2014/" in vid else _v2_notes_page(vid, accepted=accepted)
        return httpx.Response(200, content=body)

    return handler


def _patch_clients(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    """两 seam 都注入 MockTransport：共享 client 无 cookie；token client 携 config token cookie。"""

    def shared_factory(_config: Config, _rate_limiter: RateLimiter | None = None) -> HttpClient:
        return HttpClient(user_agent=_MOCK_UA, transport=httpx.MockTransport(handler))

    def token_factory(config: Config, _rate_limiter: RateLimiter | None = None) -> HttpClient:
        return HttpClient(
            user_agent=_MOCK_UA,
            transport=httpx.MockTransport(handler),
            extra_headers={"Cookie": f"openreview.accessToken={config.openreview_token}"},
        )

    monkeypatch.setattr(cli_module, "_http_client_factory", shared_factory)
    monkeypatch.setattr(cli_module, "_openreview_client_factory", token_factory)


# --- DB 探针 ---------------------------------------------------------------------------------


def _papers(home: Path) -> int:
    db = Database(home / "catalog.sqlite")
    try:
        return int(db.query("SELECT COUNT(*) AS n FROM paper")[0]["n"])
    finally:
        db.close()


def _fetched_assets(home: Path) -> int:
    db = Database(home / "catalog.sqlite")
    try:
        return int(db.query("SELECT COUNT(*) AS n FROM asset WHERE state='fetched'")[0]["n"])
    finally:
        db.close()


def _openreview_identifiers(home: Path) -> set[str]:
    db = Database(home / "catalog.sqlite")
    try:
        rows = db.query("SELECT value FROM identifier WHERE scheme='openreview'")
        return {str(r["value"]) for r in rows}
    finally:
        db.close()


def _pdf_files(home: Path) -> list[Path]:
    root = home / "data" / "pdf"
    return sorted(root.rglob("*.pdf")) if root.is_dir() else []


# --- AC-2.2 离线：pull iclr --year 2024 --limit 10 全链 --------------------------------------


def test_ac_2_2_pull_2024_limit_10_full_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Closes: AC-2.2 (offline layer). 全链回放 + accepted 对账 + limit + 10 %PDF。"""
    monkeypatch.delenv("PAPER_CRAWLER_OPENREVIEW_TOKEN", raising=False)
    home = _write_iclr_home(tmp_path)
    _patch_clients(monkeypatch, _make_handler(accepted=12, require_cookie=False))

    result = runner.invoke(
        app, ["pull", "iclr", "--year", "2024", "--limit", "10", "--home", str(home)]
    )
    assert result.exit_code == 0, result.output

    # accepted 对账：15 note（12 接收 + 3 未接收）→ enumerate 只落 12 篇 accepted。
    assert _papers(home) == 12
    ids = _openreview_identifiers(home)
    assert len(ids) == 12
    assert all(i.startswith("acc") for i in ids)  # 3 条 rej* 被 venueid 过滤排除

    # limit=10：12 个 pdf plan 截断到 10 个 fetch → 10 个 %PDF 落盘（魔数校验过 pipeline）。
    pdfs = _pdf_files(home)
    assert len(pdfs) == 10
    assert all(f.read_bytes().startswith(b"%PDF-") for f in pdfs)
    assert _fetched_assets(home) == 10


def test_pull_2024_dry_run_stops_at_resolve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--dry-run 止于 resolve：12 篇 accepted、pdf plan 产出，但 0 落盘。"""
    monkeypatch.delenv("PAPER_CRAWLER_OPENREVIEW_TOKEN", raising=False)
    home = _write_iclr_home(tmp_path)
    _patch_clients(monkeypatch, _make_handler(accepted=12, require_cookie=False))

    result = runner.invoke(
        app, ["pull", "iclr", "--year", "2024", "--dry-run", "--home", str(home)]
    )
    assert result.exit_code == 0, result.output
    assert _papers(home) == 12
    assert _pdf_files(home) == []  # 止于 resolve，无下载


# --- 缺陷 C-D：2018 决定帖 join 全链（venueid 惯例外的早届）------------------------------------


def test_pull_2018_decision_join_full_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """缺陷 C-D 回归：ICLR 2018（blind submission 无 venueid）经 venue 级 Acceptance_Decision
    join 枚举出 accepted——由修复前的 0 篇修为 2 篇（sub_oral/sub_poster），全链落盘 2 个 %PDF。

    fixtures 12（决定帖：Accept Oral/Poster + Reject + Invite to Workshop Track）+ 13（提交帖，
    无 venueid，带 pdf）——形态 [LIVE] 2026-07-22 实证（research/site-survey/openreview.md §11）。
    """
    monkeypatch.delenv("PAPER_CRAWLER_OPENREVIEW_TOKEN", raising=False)
    home = _write_iclr_home(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        if "/pdf" in request.url.path:
            return httpx.Response(200, content=_PDF)
        if "/groups" in request.url.path:
            return httpx.Response(
                200, content=_v1_group("ICLR.cc/2018/Conference")
            )  # 无 domain → v1
        inv = request.url.params.get("invitation", "")
        name = (
            "12_v1_2018_decisions.json"
            if "Acceptance_Decision" in inv
            else "13_v1_2018_submissions.json"
        )
        return httpx.Response(200, content=fixture_bytes(name))

    _patch_clients(monkeypatch, handler)
    result = runner.invoke(app, ["pull", "iclr", "--year", "2018", "--home", str(home)])
    assert result.exit_code == 0, result.output

    # 决定帖 join：Reject + Invite to Workshop Track 排除 → 只 2 篇 accepted 落库。
    assert _papers(home) == 2
    assert _openreview_identifiers(home) == {"sub_oral", "sub_poster"}
    # 提交帖带 pdf → resolve 纯构造 URL → 2 个 %PDF 落盘。
    pdfs = _pdf_files(home)
    assert len(pdfs) == 2
    assert all(f.read_bytes().startswith(b"%PDF-") for f in pdfs)


# --- v1/v2 双路 -----------------------------------------------------------------------------


def test_v1_path_2014_uses_v1_endpoint_and_direct_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2014（v1）：groups 无 domain → api.openreview.net notes → 直取 content。"""
    monkeypatch.delenv("PAPER_CRAWLER_OPENREVIEW_TOKEN", raising=False)
    home = _write_iclr_home(tmp_path)
    hosts: list[str] = []

    base_handler = _make_handler(accepted=1, require_cookie=False)

    def tracking_handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return base_handler(request)

    _patch_clients(monkeypatch, tracking_handler)
    # --dry-run 免下载（2014 v1 note 无 pdf 字段 → 0 plan，本就无 fetch）。
    result = runner.invoke(
        app, ["pull", "iclr", "--year", "2014", "--dry-run", "--home", str(home)]
    )
    assert result.exit_code == 0, result.output
    assert _openreview_identifiers(home) == {"v1acc"}  # v1 直取解析成功
    # notes 走 v1 端点 api.openreview.net（非 api2）。
    assert any(h == "api.openreview.net" for h in hosts)


# --- T4 token/BLOCKED/resume（复用 AC-1.5 模式）---------------------------------------------


def _blocked_count(output: str) -> bool:
    return "| 阻塞 |" in output and "resume --all" in output


def test_no_token_403_blocks_then_token_resume_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Closes: AC-2.2 T4. 无 token→notes 403→BLOCKED(auth)→配置 token+resume→重跑完成。"""
    monkeypatch.delenv("PAPER_CRAWLER_OPENREVIEW_TOKEN", raising=False)
    home = _write_iclr_home(tmp_path)
    # require_cookie=True：notes 需 cookie，否则 403 ChallengeRequiredError。
    _patch_clients(monkeypatch, _make_handler(accepted=5, require_cookie=True))

    # -- 1. 无 token → enumerate 收 403 → 整批 BLOCKED(auth)，退出 3 --------------------
    r1 = runner.invoke(app, ["pull", "iclr", "--year", "2024", "--home", str(home)])
    assert r1.exit_code == 3, r1.output
    assert _blocked_count(r1.output)  # 阻塞态 + resume 指引
    assert _papers(home) == 0  # enumerate 未产出
    assert _pdf_files(home) == []

    status = runner.invoke(app, ["status", "--blocked", "--home", str(home)])
    assert status.exit_code == 0
    assert "auth" in status.output and "crawler resume --all" in status.output

    # -- 2. 配置 token（env）+ resume --all → BLOCKED 回 PENDING ------------------------
    monkeypatch.setenv("PAPER_CRAWLER_OPENREVIEW_TOKEN", _TOKEN)
    resume = runner.invoke(app, ["resume", "--all", "--home", str(home)])
    assert resume.exit_code == 0, resume.output

    # -- 3. 重跑 pull（token 经 cookie 注入）→ notes 200 → 完成 -------------------------
    r2 = runner.invoke(app, ["pull", "iclr", "--year", "2024", "--home", str(home)])
    assert r2.exit_code == 0, r2.output
    assert _papers(home) == 5  # 5 篇 accepted
    assert len(_pdf_files(home)) == 5
    assert all(f.read_bytes().startswith(b"%PDF-") for f in _pdf_files(home))


def test_token_value_not_leaked_to_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """token 值经 obslog redact 不入日志（§3 红线；测试断言）。"""
    monkeypatch.setenv("PAPER_CRAWLER_OPENREVIEW_TOKEN", _TOKEN)
    home = _write_iclr_home(tmp_path)
    _patch_clients(monkeypatch, _make_handler(accepted=3, require_cookie=True))

    captured: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            payload = getattr(record, "_event", None)
            if isinstance(payload, dict):
                captured.append(json.dumps(payload, ensure_ascii=False))

    logger = logging.getLogger("paper_crawler")
    handler = _Capture()
    logger.addHandler(handler)
    try:
        result = runner.invoke(app, ["pull", "iclr", "--year", "2024", "--home", str(home)])
        assert result.exit_code == 0, result.output
    finally:
        logger.removeHandler(handler)

    blob = "\n".join(captured)
    assert _TOKEN not in blob  # token 明文绝不出现在任何 obslog 事件
    assert _TOKEN not in result.output  # 也不在 CLI 输出


# --- CS-2 凭证红线：跨 adapter cookie 隔离回归 ----------------------------------------------


def test_arxiv_client_never_carries_openreview_cookie(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """红线守护：配置 token 后，arxiv adapter 的 client 请求**不携** openreview cookie。

    双 client 装配的隔离性——`bind_http_client` 把共享（无 cookie）client 注入所有
    HttpClientConsumer（含 arxiv/openreview）；`_bind_openreview_token_client` **仅**为
    openreview 覆盖为携 cookie 的专属 client。若未来重构把 token 挂到共享 client，arxiv
    等他站请求就会外泄用户凭证（§3 红线）——本测试用 MockTransport 捕获请求头钉死隔离。
    """
    monkeypatch.setenv("PAPER_CRAWLER_OPENREVIEW_TOKEN", _TOKEN)
    home = _write_iclr_home(tmp_path)
    captured: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append((request.url.host, request.headers.get("cookie")))
        return httpx.Response(200, content=b"ok")

    # 两个 seam 都注入 MockTransport（**不接 limiter**——离线无逐请求限速闸，避免未注册
    # host 的 acquire fail-fast）；共享无 cookie，token client 携 config token cookie。
    def shared_factory(_config: Config, _rate_limiter: RateLimiter | None = None) -> HttpClient:
        return HttpClient(user_agent=_MOCK_UA, transport=httpx.MockTransport(handler))

    def token_factory(config: Config, _rate_limiter: RateLimiter | None = None) -> HttpClient:
        return HttpClient(
            user_agent=_MOCK_UA,
            transport=httpx.MockTransport(handler),
            extra_headers={"Cookie": f"openreview.accessToken={config.openreview_token}"},
        )

    monkeypatch.setattr(cli_module, "_http_client_factory", shared_factory)
    monkeypatch.setattr(cli_module, "_openreview_client_factory", token_factory)

    env = cli_module._build_env(home, verbose=False)
    try:
        adapters = env.ctx.registry._adapters  # noqa: SLF001 (测试内省装配结果)
        arxiv = adapters["arxiv"]
        openreview = adapters["openreview"]

        # 装配隔离：arxiv 用共享（无 cookie）client；openreview 用专属 token client；两者不同实例。
        assert arxiv._client() is env.http  # type: ignore[attr-defined]
        assert openreview._client() is env.openreview_http  # type: ignore[attr-defined]
        assert env.http is not env.openreview_http

        # 实证：arxiv 请求无 cookie；openreview 请求携 token cookie。
        arxiv._client().get_bytes("https://export.arxiv.org/api/query")  # type: ignore[attr-defined]
        openreview._client().get_bytes("https://api2.openreview.net/notes")  # type: ignore[attr-defined]
    finally:
        env.http.close()
        if env.openreview_http is not None:
            env.openreview_http.close()
        env.ctx.db.close()

    by_host = dict(captured)
    assert by_host["export.arxiv.org"] is None  # 红线：arxiv 绝不携 openreview cookie
    assert by_host["api2.openreview.net"] == f"openreview.accessToken={_TOKEN}"


@pytest.fixture(autouse=True)
def _reset_logger() -> Iterator[None]:
    """每个测试后清空 paper_crawler logger handler（避免跨测试文件句柄泄漏）。"""
    yield
    logger = logging.getLogger("paper_crawler")
    for h in list(logger.handlers):
        h.close()
        logger.removeHandler(h)
