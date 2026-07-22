"""OpenReview 在线冒烟（Phase 2 AC-2.1 / AC-2.2 在线层；design/adapters/openreview.md §7）。

默认经 `addopts = -m 'not online'` 排除，显式 `-m online` 才跑。硬预算
`MAX_REAL_REQUESTS = 18`。UA 携真实 mailto（D-014，`PAPER_CRAWLER_CONTACT_EMAIL`）。

三层，按 token 依赖分级：

- **AC-2.1 在线层（token-free，Closes: AC-2.1 (online layer)）**：`timeline iclr` 实跑
  （零网络 discover，内置届表驱动）落库的年列表，与两个活体源对照——
    (a) **活体 OpenReview `venues` 主表**（`groups?id=venues` 匿名 1 请求）里 ICLR 主会
        群（`ICLR.cc/<yr>/[Cc]onference`）的年集合：**±0 全等**（adapter 的真实数据源，
        大小写规约随之验证）。这是 AC-2.1 最强、最直接的在线判定。
    (b) **DBLP `conf/iclr` index**（1 请求）卷年集合：**非 ±0**，差集为已核销的口径差
        `{2015, 2016}`（DBLP-only：主会确在但电子版托管 @ iclr.cc、不在 OpenReview）
        与 `{2026, 2027}`（OpenReview-only：未来/新近届，DBLP 卷尚未发布）。测试把这两个
        差集**钉死**——DBLP/OpenReview 推进（如 DBLP 发布 2026 卷、OpenReview 建 2028 群）
        会令其失败，正确触发重新核销（anchor UPDATE_GOLDEN 纪律，design §7）。
  > ⚠ 勘误：site-survey 原称"两侧 2015/2016 同缺"被本层 [LIVE] 证伪——DBLP **有**
  > iclr2015/iclr2016（电子版 @ iclr.cc）。见 tests/fixtures/openreview/dblp-iclr-anchor.json。

- **匿名 healthcheck 基线（token-free）**：`adapter.healthcheck()`（v2 2024 + v1 2014 群，
  匿名 2 请求）判 healthy——平台健康与用户凭证分离（§4），无 token 也须绿。

- **AC-2.2 在线层（token-gated，Closes: AC-2.2 (online layer)）**：`pull iclr --year 2024
  --limit 10` 真实执行——10 个 %PDF 落盘（魔数 + >10KB）+ DB↔文件对账。**需有效
  OpenReview token**（env `PAPER_CRAWLER_OPENREVIEW_TOKEN`）；未设则 skip。
  > ⚠ 2026-07-22 本会话用户 token 已过期（401 TokenExpiredError，非 UA 挑战、非机制缺陷
  > ——cookie 机制经服务器验证正确）。故 AC-2.2 在线层**本会话未执行、待用户 token 刷新**；
  > 该项验收在线判定 = BLOCKED(pending valid token)。离线层（tests/integration/
  > test_openreview_pull.py）已全绿覆盖同一 --year 2024 --limit 10 全链。

MAX_REAL_REQUESTS=18 = AC-2.1(venues 1 + dblp index 1) + healthcheck(2) + AC-2.2(groups 1
+ notes ~3 + pdf 10 = 14)。真实执行结果归档 scratchpad/openreview-online-run.txt。
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from helpers import make_openreview_venue
from online.conftest import RealRequestBudget
from online.smoke_helpers import make_rate_limited_client
from paper_crawler.adapters.openreview import venues
from paper_crawler.adapters.openreview.adapter import OpenReviewAdapter
from paper_crawler.cli import app
from paper_crawler.http import HttpClient
from paper_crawler.storage.db import Database
from paper_crawler.types import RatePolicy

MAX_REAL_REQUESTS = 18

runner = CliRunner()

_CONTACT_EMAIL = os.environ.get("PAPER_CRAWLER_CONTACT_EMAIL", "")
if not _CONTACT_EMAIL:
    pytest.skip(
        "PAPER_CRAWLER_CONTACT_EMAIL not set (required for D-014 UA identity)",
        allow_module_level=True,
    )

_TOKEN = os.environ.get("PAPER_CRAWLER_OPENREVIEW_TOKEN", "").strip()

# 内置届表（venues._ICLR_TABLE）非空年 = timeline 应产出的年集合 = AC-2.1 的 OpenReview 侧真值。
_TIMELINE_YEARS: set[int] = {
    y for y, vid in venues.resolve_venue_table(make_openreview_venue()).items() if vid
}

_VENUES_URL = "https://api2.openreview.net/groups?id=venues"
_DBLP_INDEX_URL = "https://dblp.org/db/conf/iclr/index.html"

# 已核销的 timeline↔DBLP 口径差（design §7 anchor；[LIVE] 2026-07-22）——见模块 docstring。
_DBLP_ONLY_YEARS = {2015, 2016}  # 主会 @ iclr.cc、不在 OpenReview
_OPENREVIEW_ONLY_YEARS = {2026, 2027}  # 未来/新近届，DBLP 卷未发布


# --- 活体源解析（零依赖，与勘察脚本同逻辑）--------------------------------------------------


def _iclr_conference_years_from_venues(data: bytes) -> set[int]:
    """`groups?id=venues` 响应 → ICLR 主会群（`ICLR.cc/<yr>/[Cc]onference`）的年集合。"""
    doc = json.loads(data)
    groups = doc.get("groups", []) if isinstance(doc, dict) else []
    members = groups[0].get("members", []) if groups else []
    years: set[int] = set()
    for m in members:
        mm = re.match(r"^ICLR\.cc/(\d{4})/[Cc]onference$", m) if isinstance(m, str) else None
        if mm:
            years.add(int(mm.group(1)))
    return years


def _iclr_years_from_dblp_index(data: bytes) -> set[int]:
    """DBLP `conf/iclr` index → 卷年集合（`db/conf/iclr/iclr<yr>.html` 引用）。"""
    text = data.decode("utf-8", errors="replace")
    return {int(m) for m in re.findall(r"db/conf/iclr/iclr(\d{4})\.html", text)}


# --- fixtures ---------------------------------------------------------------------------------


@pytest.fixture(scope="session")
def openreview_client() -> Iterator[HttpClient]:
    """匿名（token-free）限速 client（OpenReview 三域共享一桶 30rpm，UA 携真实 mailto）。"""
    client = make_rate_limited_client(
        domains=OpenReviewAdapter.domains,
        default_rate=OpenReviewAdapter.default_rate,
        contact_email=_CONTACT_EMAIL,
    )
    try:
        yield client
    finally:
        client.close()


@pytest.fixture(scope="session")
def dblp_client() -> Iterator[HttpClient]:
    """DBLP 限速 client（≥3s 间隔的 20rpm 保守值——DBLP 对高频敏感；UA 携真实 mailto）。"""
    client = make_rate_limited_client(
        domains=("dblp.org",),
        default_rate=RatePolicy(
            requests_per_minute=20.0, burst=1, source_note="DBLP conservative smoke rate"
        ),
        contact_email=_CONTACT_EMAIL,
    )
    try:
        yield client
    finally:
        client.close()


# --- home 装配（iclr venue；identity email 令 UA 携 mailto）-----------------------------------


def _write_iclr_home(base: Path, *, identity_email: str) -> Path:
    home = base / "home"
    venues_dir = home / "venues"
    venues_dir.mkdir(parents=True)
    # 真实在线：**不**快进限速（无 rate.scale），UA 携真实 mailto。token 经 env 注入（不落盘）。
    (home / "config.toml").write_text(
        f'[paths]\nvenues_dirs = ["venues"]\n\n[identity]\nemail = "{identity_email}"\n',
        encoding="utf-8",
    )
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


def _issue_years(home: Path) -> set[int]:
    db = Database(home / "catalog.sqlite")
    try:
        rows = db.query(
            "SELECT DISTINCT year FROM issue WHERE venue_id='iclr' AND year IS NOT NULL"
        )
        return {int(r["year"]) for r in rows}
    finally:
        db.close()


def _pdf_files(home: Path) -> list[Path]:
    root = home / "data" / "pdf"
    return sorted(root.rglob("*.pdf")) if root.is_dir() else []


def _fetched_assets(home: Path) -> int:
    db = Database(home / "catalog.sqlite")
    try:
        return int(db.query("SELECT COUNT(*) AS n FROM asset WHERE state='fetched'")[0]["n"])
    finally:
        db.close()


def _paper_count(home: Path) -> int:
    db = Database(home / "catalog.sqlite")
    try:
        return int(db.query("SELECT COUNT(*) AS n FROM paper")[0]["n"])
    finally:
        db.close()


# --- AC-2.1 在线层（token-free）--------------------------------------------------------------


@pytest.mark.online
def test_ac_2_1_timeline_matches_live_venues_and_reconciles_with_dblp(
    tmp_path: Path,
    openreview_client: HttpClient,
    dblp_client: HttpClient,
    real_request_budget: RealRequestBudget,
) -> None:
    """Closes: AC-2.1 (online layer).

    `timeline iclr`（零网络 discover）年列表 == 活体 OpenReview venues ICLR 主会年（±0），
    且与 DBLP conf/iclr index 卷年的差集恰为已核销口径差 {2015,2016}/{2026,2027}。
    """
    # 1) timeline iclr 实跑（零网络 discover），落库年集合。
    home = _write_iclr_home(tmp_path, identity_email=_CONTACT_EMAIL)
    result = runner.invoke(app, ["timeline", "iclr", "--home", str(home)])
    assert result.exit_code == 0, result.output
    timeline_years = _issue_years(home)
    # discover 与内置届表一致（缺届 2015/2016 不产 Issue）。
    assert timeline_years == _TIMELINE_YEARS, (
        f"timeline 年集合 {sorted(timeline_years)} != 内置届表非空年 {sorted(_TIMELINE_YEARS)}"
    )
    assert 2015 not in timeline_years and 2016 not in timeline_years

    # 2) 活体 OpenReview venues 主表 → ICLR 主会年集合（±0 全等，adapter 真实源）。
    real_request_budget.spend(1)
    venues_years = _iclr_conference_years_from_venues(openreview_client.get_bytes(_VENUES_URL))
    print(f"AC2.1 timeline={sorted(timeline_years)}")
    print(f"AC2.1 live_venues={sorted(venues_years)}")
    assert timeline_years == venues_years, (
        f"timeline {sorted(timeline_years)} != 活体 venues {sorted(venues_years)}（±0 应成立）"
    )
    # 基线 canary：venues 主表含 2024 主会（design §7 无 token 也可跑的 canary）。
    assert 2024 in venues_years

    # 3) DBLP conf/iclr index → 卷年集合；差集恰为已核销口径差（非 ±0，钉死）。
    real_request_budget.spend(1)
    dblp_years = _iclr_years_from_dblp_index(dblp_client.get_bytes(_DBLP_INDEX_URL))
    print(f"AC2.1 dblp_index={sorted(dblp_years)}")
    assert dblp_years, "DBLP index 解析出 0 个 iclr 卷（选择器漂移？）"
    assert dblp_years - timeline_years == _DBLP_ONLY_YEARS, (
        f"DBLP-only 年 {sorted(dblp_years - timeline_years)} != 已核销 {sorted(_DBLP_ONLY_YEARS)}"
        "（DBLP/OpenReview 推进需重新核销 anchor，design §7）"
    )
    assert timeline_years - dblp_years == _OPENREVIEW_ONLY_YEARS, (
        f"OpenReview-only 年 {sorted(timeline_years - dblp_years)} != 已核销 "
        f"{sorted(_OPENREVIEW_ONLY_YEARS)}（需重新核销 anchor）"
    )


@pytest.mark.online
def test_healthcheck_anonymous_baseline_is_healthy(
    openreview_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """匿名 healthcheck（token-free，§4）：v2 2024 + v1 2014 群双端可达 → healthy。"""
    adapter = OpenReviewAdapter(http=openreview_client)
    real_request_budget.spend(2)  # healthcheck 内部固定查 2 个 group（v2 2024 + v1 2014）
    report = adapter.healthcheck()
    print(f"HEALTHCHECK healthy={report.healthy} detail={report.detail!r}")
    assert report.healthy, f"匿名 healthcheck 应 healthy: {report.detail!r}"


# --- AC-2.2 在线层（token-gated；需有效 token，否则 skip）-------------------------------------


@pytest.mark.online
@pytest.mark.skipif(not _TOKEN, reason="PAPER_CRAWLER_OPENREVIEW_TOKEN 未设——AC-2.2 需有效 token")
def test_ac_2_2_pull_2024_limit_10_real(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_request_budget: RealRequestBudget
) -> None:
    """Closes: AC-2.2 (online layer). `pull iclr --year 2024 --limit 10` 真实执行。

    10 个 %PDF 落盘（魔数 + >10KB）+ DB↔文件对账。token 经 env 注入（config 不落盘）。
    ⚠ 需**有效** token；过期 token 会走 auth_expired→BLOCKED(退出 3)，本测试断言完成态
    （退出 0）——过期时应 skip 本测试（勿以过期 token 跑）。
    """
    # groups 1 + notes 分页（2024 ~2260 @1000/页 ≈ 3）+ pdf 10 ≈ 14；上限声明（CLI 内部翻页
    # 无逐请求 spend 钩子，此处按设计上限一次性记账）。
    real_request_budget.spend(14)
    home = _write_iclr_home(tmp_path, identity_email=_CONTACT_EMAIL)
    # token 仅经 env（Config.load 读 PAPER_CRAWLER_OPENREVIEW_TOKEN 覆盖 config；不落盘）。
    monkeypatch.setenv("PAPER_CRAWLER_OPENREVIEW_TOKEN", _TOKEN)

    result = runner.invoke(
        app, ["pull", "iclr", "--year", "2024", "--limit", "10", "--home", str(home)]
    )
    assert result.exit_code == 0, result.output

    pdfs = _pdf_files(home)
    assert len(pdfs) == 10, f"期望 10 个 PDF 落盘，实得 {len(pdfs)}"
    for f in pdfs:
        head = f.read_bytes()[:8]
        assert head.startswith(b"%PDF"), f"{f.name} 前 8 字节非 %PDF: {head!r}"
        assert f.stat().st_size > 10_240, f"{f.name} 仅 {f.stat().st_size}B（<10KB，疑非真 PDF）"
    assert _fetched_assets(home) == 10  # DB↔文件对账：10 个 asset state=fetched
    # limit 只截断 fetch 不截断 enumerate：2024 accepted 远超 10。
    assert _paper_count(home) >= 10
    print(f"AC2.2 pulled pdfs={len(pdfs)} fetched_assets=10 papers>={_paper_count(home)}")
