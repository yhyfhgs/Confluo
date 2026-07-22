"""OpenReview 在线冒烟（Phase 2 AC-2.1 / AC-2.2 在线层；design/adapters/openreview.md §7）。

默认经 `addopts = -m 'not online'` 排除，显式 `-m online` 才跑。硬预算
`MAX_REAL_REQUESTS = 10`。UA 携真实 mailto（D-014，`PAPER_CRAWLER_CONTACT_EMAIL`）。

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

- **AC-2.2 在线层（token-gated，Closes: AC-2.2 (online layer)）**：真实 enumerate ICLR
  2024 主会 → **accepted stub 数 == DBLP 锚点 2260**（api2 v2；`content.venueid=
  ICLR.cc/2024/Conference`，[LIVE] 2026-07-22 交叉核验：OpenReview accepted 2260 == DBLP
  iclr2024 toc 2260），再对首篇 accepted 的真实 PDF 流式取首 chunk 断 **`%PDF` 魔数 +
  ≥10KB**。**需有效 OpenReview token**（env `PAPER_CRAWLER_OPENREVIEW_TOKEN`）；未设则 skip。
  > 契约（AC-2.2 final，2026-07-22）：本层与 5 个兄弟 adapter 在线冒烟同构——**enumerate
  > 计数对锚点 + 单篇 PDF %PDF 探测**（pmlr/cvf/neurips/acl/aaai 同款），验证「真实站点
  > 应答 + accepted 集合 + 真 PDF 下载」。**不**走 `pull --limit 10` 全级联：pipeline 的
  > resolve 阶段对**每篇** enumerate 出的 paper 逐个 `acquire_and_wait`（30rpm 闸），而
  > openreview 的 `resolve_assets` 是零网络纯构造——2024 的 2260 篇会被逐个限速空转（≈数十
  > 分钟墙钟，见 pipeline/stages.py:371 与 runner.py:465-473「resolve 全量后按 limit 截断」），
  > 对 10 篇的在线冒烟不切实际。`pull --year 2024 --limit 10` 的「10 落盘 + DB↔文件对账」
  > 全链仍由离线 tests/integration/test_openreview_pull.py（mock HTTP，确定性）全绿覆盖。

MAX_REAL_REQUESTS=10 = AC-2.1(venues 1 + dblp index 1) + healthcheck(2) + AC-2.2(groups 1
+ notes 3〔2260 accepted @1000/页〕+ pdf 首 chunk 1 = 5)。真实执行结果归档
scratchpad/ac22-final-run.txt。
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
from online.smoke_helpers import make_rate_limited_client, stream_first_chunk
from paper_crawler.adapters.openreview import parse, venues
from paper_crawler.adapters.openreview.adapter import OpenReviewAdapter
from paper_crawler.cli import app
from paper_crawler.http import HttpClient
from paper_crawler.ratelimit import RateLimiter
from paper_crawler.storage.db import Database
from paper_crawler.types import AssetKind, RatePolicy
from paper_crawler.useragent import build_user_agent

MAX_REAL_REQUESTS = 10

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

# AC-2.2 accepted 锚点：ICLR 2024 主会 accepted = 2260（[LIVE] 2026-07-22 api2 v2
# content.venueid=ICLR.cc/2024/Conference count；== DBLP iclr2024 toc 2260，两源互证）。
_ICLR_2024_ACCEPTED = 2260


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


@pytest.fixture(scope="session")
def openreview_token_client() -> Iterator[HttpClient]:
    """携 token 的 openreview 专属限速 client（AC-2.2）。

    client 级附加头 `Cookie: openreview.accessToken=<token>`（与 CLI 装配期同机制，
    adapter.py §3）——**专属** client，绝不复用匿名 client（cookie 外泄他站属凭证红线）。
    token 仅在进程内经 env `_TOKEN` 注入到该 client，绝不落盘/入日志。三域共享一份 30rpm。
    """
    limiter = RateLimiter()
    limiter.register(OpenReviewAdapter.domains[0], OpenReviewAdapter.default_rate)
    for mirror in OpenReviewAdapter.domains[1:]:
        limiter.alias(mirror, OpenReviewAdapter.domains[0])
    client = HttpClient(
        user_agent=build_user_agent(_CONTACT_EMAIL),
        rate_limiter=limiter,
        extra_headers={"Cookie": f"openreview.accessToken={_TOKEN}"},
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
def test_ac_2_2_enumerate_2024_accepted_matches_anchor_and_fetches_real_pdf(
    openreview_token_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """Closes: AC-2.2 (online layer).

    真实 enumerate ICLR 2024 主会 accepted → 数 == DBLP 锚点 2260（两源互证），再对
    首篇 accepted 的真实 PDF 流式取首 chunk 断 `%PDF` 魔数 + ≥10KB。契约（不走 pull
    全级联的理由 + 离线全链覆盖）见模块 docstring。token 经 client cookie（不落盘）。
    """
    adapter = OpenReviewAdapter(http=openreview_token_client)
    venue = make_openreview_venue()
    # discover 零网络（内置届表）取 2024 IssueRef，不手搓字段。
    issue = next(i for i in adapter.discover_timeline(venue) if i.year == 2024)

    # enumerate = groups(判版本 1) + notes 翻页（2260 accepted @1000/页 = 3）。CLI 外直调
    # adapter、逐请求无 spend 钩子，按设计一次性记账（2260 钉死→翻页数随之钉死）。
    real_request_budget.spend(4)
    stubs = list(adapter.enumerate_issue(venue, issue))
    print(f"AC2.2 enumerate 2024 accepted={len(stubs)} anchor={_ICLR_2024_ACCEPTED}")
    assert len(stubs) == _ICLR_2024_ACCEPTED, (
        f"2024 accepted enumerate {len(stubs)} != DBLP 锚点 {_ICLR_2024_ACCEPTED}"
        "（OpenReview accepted 集合漂移或 DBLP 卷更新——需重新核销 anchor，design §7）"
    )
    # accepted 判定生效：每篇 stub 的单一 identifier 为 ('openreview', forum)。
    assert all(s.identifiers and s.identifiers[0][0] == "openreview" for s in stubs)

    # 首篇携 openreview_pdf 相对路径的 accepted stub → resolve 纯构造绝对 URL → 流式探测。
    first_pdf = next((s for s in stubs if dict(s.meta).get(parse.META_PDF_PATH)), None)
    assert first_pdf is not None, "2024 无任何 accepted stub 携带 openreview_pdf 路径"
    plan = next(p for p in adapter.resolve_assets(venue, first_pdf) if p.kind is AssetKind.PDF)

    real_request_budget.spend(1)
    head = stream_first_chunk(openreview_token_client, plan.url, min_bytes=11_000)
    print(f"AC2.2 pdf url={plan.url} head={head[:8]!r} first_chunk_bytes={len(head)}")
    assert head.startswith(b"%PDF"), f"下载体前 8 字节非 %PDF: {head[:8]!r}（token 失效/删除页？）"
    assert len(head) >= 10_240, f"PDF 首 chunk 仅 {len(head)}B（<10KB，疑非真 PDF）"
