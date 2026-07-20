"""仓储层语义测试（phase1-plan Task 2；Refs: D-007, D-017, AC-1.1）。

重点：upsert_paper 强合并（补缺不覆盖）、upsert_issue/plan_asset 的 NULL-安全幂等键、
paper_issue_link 幂等建链、外键约束、counts 对账口径。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.types import AssetKind, AssetPlan, AuthLevel, IssueRef, PaperStub, VenueSpec

VENUE_ID = "mock_journal"


@pytest.fixture
def repo(tmp_path: Path, venue: VenueSpec) -> Iterator[Repo]:
    database = Database(tmp_path / "repo.sqlite")
    database.migrate()
    r = Repo(database)
    r.upsert_venue(venue)  # paper/issue.venue_id 需要 venue 先存在（外键）
    yield r
    database.close()


def _issue(
    *,
    volume: str | None = None,
    number: str | None = None,
    year: int | None = 2024,
    label: str | None = None,
) -> IssueRef:
    return IssueRef(venue_id=VENUE_ID, volume=volume, number=number, year=year, label=label)


def _stub(
    *,
    doi: str = "10.9999/mj.1",
    title: str = "Paper A",
    year: int | None = None,
    abstract: str | None = None,
    pub_date: str | None = None,
    meta: tuple[tuple[str, str], ...] = (),
    extra_ids: tuple[tuple[str, str], ...] = (),
) -> PaperStub:
    return PaperStub(
        title=title,
        identifiers=(("doi", doi), *extra_ids),
        year=year,
        abstract=abstract,
        pub_date=pub_date,
        meta=meta,
    )


def _pdf_plan(*, version: str | None = None, url: str = "https://mock.local/pdf/1") -> AssetPlan:
    return AssetPlan(kind=AssetKind.PDF, url=url, auth_needed=AuthLevel.NONE, version=version)


# -- venue -------------------------------------------------------------------


def test_upsert_venue_creates_row_with_snapshot(repo: Repo, venue: VenueSpec) -> None:
    rows = repo.db.query("SELECT * FROM venue WHERE id = ?", (VENUE_ID,))
    assert len(rows) == 1
    assert rows[0]["name"] == venue.names.full
    assert json.loads(rows[0]["field_json"]) == venue.field
    snapshot = json.loads(rows[0]["spec_snapshot_json"])
    assert snapshot["id"] == VENUE_ID  # 审计快照可解析且含 id


def test_upsert_venue_idempotent(repo: Repo, venue: VenueSpec) -> None:
    repo.upsert_venue(venue)
    repo.upsert_venue(venue)
    assert len(repo.db.query("SELECT id FROM venue")) == 1


def test_upsert_venue_update_preserves_children(repo: Repo, venue: VenueSpec) -> None:
    """就地 UPDATE：venue 有子 issue 时再次 upsert 不违反外键、状态被更新。"""
    repo.upsert_issue(_issue(volume="1", number="1"), source="mock")
    updated = venue.model_copy(update={"status": "dormant"})
    repo.upsert_venue(updated)
    row = repo.db.query("SELECT status FROM venue WHERE id = ?", (VENUE_ID,))[0]
    assert row["status"] == "dormant"
    assert len(repo.db.query("SELECT id FROM issue")) == 1


# -- issue -------------------------------------------------------------------


def test_upsert_issue_returns_ulid(repo: Repo) -> None:
    issue_id = repo.upsert_issue(_issue(volume="1", number="1"), source="mock")
    assert isinstance(issue_id, str) and len(issue_id) == 26


def test_upsert_issue_idempotent_same_ref(repo: Repo) -> None:
    first = repo.upsert_issue(_issue(volume="160", number="2"), source="mock")
    second = repo.upsert_issue(_issue(volume="160", number="2"), source="mock")
    assert first == second
    assert len(repo.db.query("SELECT id FROM issue")) == 1


def test_upsert_issue_conference_null_volume_dedupes(repo: Repo) -> None:
    """会议 issue（volume/number 均 NULL）两次 upsert → 1 行（查后插绕过 UNIQUE 的 NULL 语义）。"""
    ref = _issue(volume=None, number=None, label="2024")
    first = repo.upsert_issue(ref, source="mock")
    second = repo.upsert_issue(ref, source="mock")
    assert first == second
    assert len(repo.db.query("SELECT id FROM issue")) == 1


def test_upsert_issue_distinct_keys_create_rows(repo: Repo) -> None:
    repo.upsert_issue(_issue(volume="1", number="1"), source="mock")
    repo.upsert_issue(_issue(volume="1", number="2"), source="mock")
    assert len(repo.db.query("SELECT id FROM issue")) == 2


def test_list_issues_filters(repo: Repo) -> None:
    repo.upsert_issue(_issue(volume="1", number="1", year=2024), source="mock")
    repo.upsert_issue(_issue(volume="1", number="2", year=2024), source="mock")
    repo.upsert_issue(_issue(volume="2", number="1", year=2025), source="mock")
    assert len(repo.list_issues(VENUE_ID)) == 3
    assert len(repo.list_issues(VENUE_ID, volume="1")) == 2
    assert len(repo.list_issues(VENUE_ID, volume="1", number="2")) == 1
    assert len(repo.list_issues(VENUE_ID, year=2025)) == 1


# -- paper 强合并 ------------------------------------------------------------


def test_upsert_paper_creates_paper_and_identifier(repo: Repo) -> None:
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/mj.a"))
    assert len(paper_id) == 26
    paper = repo.db.query("SELECT * FROM paper WHERE id = ?", (paper_id,))[0]
    assert paper["ingest_state"] == "metadata_only"
    ident = repo.db.query("SELECT * FROM identifier WHERE paper_id = ?", (paper_id,))[0]
    assert ident["scheme"] == "doi" and ident["is_primary"] == 1


def test_upsert_paper_strong_merge_same_identifier(repo: Repo) -> None:
    """两个 stub 共享同一 (doi) → 返回同一 paper_id，identifier 不重复。"""
    p1 = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/shared", title="First"))
    p2 = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/shared", title="Second"))
    assert p1 == p2
    assert len(repo.db.query("SELECT id FROM paper")) == 1
    assert len(repo.db.query("SELECT scheme FROM identifier")) == 1


def test_upsert_paper_fills_missing_fields(repo: Repo) -> None:
    """第二次调用补第一次的空缺字段。"""
    doi = "10.9999/fill"
    repo.upsert_paper(VENUE_ID, None, _stub(doi=doi, abstract=None, year=None))
    repo.upsert_paper(VENUE_ID, None, _stub(doi=doi, abstract="Now present", year=2030))
    paper = repo.db.query("SELECT * FROM paper WHERE year = 2030")[0]
    assert paper["abstract"] == "Now present"
    assert paper["year"] == 2030


def test_upsert_paper_does_not_overwrite_non_empty(repo: Repo) -> None:
    """第二次的非空字段不覆盖第一次的非空值。"""
    doi = "10.9999/keep"
    repo.upsert_paper(VENUE_ID, None, _stub(doi=doi, abstract="Original", year=2024))
    repo.upsert_paper(VENUE_ID, None, _stub(doi=doi, abstract="Changed", year=2025))
    paper = repo.db.query("SELECT * FROM paper")[0]
    assert paper["abstract"] == "Original"
    assert paper["year"] == 2024


def test_upsert_paper_merge_across_identifier_overlap(repo: Repo) -> None:
    """第二个 stub 带新 identifier 且与既有 doi 重叠 → 并入同一 paper，新增 identifier。"""
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/x"))
    p2 = repo.upsert_paper(
        VENUE_ID, None, _stub(doi="10.9999/x", extra_ids=(("arxiv", "2401.00001"),))
    )
    idents = repo.db.query(
        "SELECT scheme FROM identifier WHERE paper_id = ? ORDER BY scheme", (p2,)
    )
    assert [r["scheme"] for r in idents] == ["arxiv", "doi"]
    assert len(repo.db.query("SELECT id FROM paper")) == 1


def test_upsert_paper_meta_serialized(repo: Repo) -> None:
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/meta", meta=(("jel", "G12"),)))
    paper = repo.db.query("SELECT meta_json FROM paper")[0]
    assert json.loads(paper["meta_json"]) == {"jel": "G12"}


def test_upsert_paper_fills_pub_date_and_meta(repo: Repo) -> None:
    """补缺覆盖 pub_date 与 meta 两条合并分支。"""
    doi = "10.9999/pdmeta"
    repo.upsert_paper(VENUE_ID, None, _stub(doi=doi))  # pub_date/meta 皆空
    repo.upsert_paper(
        VENUE_ID,
        None,
        _stub(doi=doi, pub_date="2024-03-01", meta=(("track", "main"),)),
    )
    paper = repo.db.query("SELECT * FROM paper")[0]
    assert paper["pub_date"] == "2024-03-01"
    assert json.loads(paper["meta_json"]) == {"track": "main"}


def test_upsert_paper_second_call_no_new_fields_is_noop_merge(repo: Repo) -> None:
    """第二次调用无可补字段 → 合并早退（updates 为空），paper 不变、仍单行。"""
    doi = "10.9999/noop"
    repo.upsert_paper(VENUE_ID, None, _stub(doi=doi, abstract="A", year=2024))
    repo.upsert_paper(VENUE_ID, None, _stub(doi=doi))  # 全空，无可补
    rows = repo.db.query("SELECT abstract, year FROM paper")
    assert len(rows) == 1
    assert rows[0]["abstract"] == "A" and rows[0]["year"] == 2024


# -- paper_issue_link 幂等 ---------------------------------------------------


def test_paper_issue_link_idempotent(repo: Repo) -> None:
    """同一 (paper, issue) 建链两次 → 1 条 link。"""
    issue_id = repo.upsert_issue(_issue(volume="1", number="1"), source="mock")
    doi = "10.9999/link"
    p1 = repo.upsert_paper(VENUE_ID, issue_id, _stub(doi=doi))
    p2 = repo.upsert_paper(VENUE_ID, issue_id, _stub(doi=doi))
    assert p1 == p2
    links = repo.db.query("SELECT * FROM paper_issue_link WHERE paper_id = ?", (p1,))
    assert len(links) == 1


def test_same_paper_in_two_issues_two_links(repo: Repo) -> None:
    """同一 paper 出现于不同 issue → 多条 link。"""
    i1 = repo.upsert_issue(_issue(volume="1", number="1"), source="mock")
    i2 = repo.upsert_issue(_issue(volume="1", number="2"), source="mock")
    doi = "10.9999/multi"
    p1 = repo.upsert_paper(VENUE_ID, i1, _stub(doi=doi))
    p2 = repo.upsert_paper(VENUE_ID, i2, _stub(doi=doi))
    assert p1 == p2
    links = repo.db.query("SELECT issue_id FROM paper_issue_link WHERE paper_id = ?", (p1,))
    assert {r["issue_id"] for r in links} == {i1, i2}


# -- list_papers / state -----------------------------------------------------


def test_list_papers_all_and_by_issue(repo: Repo) -> None:
    i1 = repo.upsert_issue(_issue(volume="1", number="1"), source="mock")
    repo.upsert_paper(VENUE_ID, i1, _stub(doi="10.9999/a", title="Alpha"))
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/b", title="Beta"))
    assert len(repo.list_papers(VENUE_ID)) == 2
    in_issue = repo.list_papers(VENUE_ID, issue_id=i1)
    assert len(in_issue) == 1 and in_issue[0]["title"] == "Alpha"


def test_set_paper_state(repo: Repo) -> None:
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/s"))
    repo.set_paper_state(paper_id, "resolved")
    row = repo.db.query("SELECT ingest_state FROM paper WHERE id = ?", (paper_id,))[0]
    assert row["ingest_state"] == "resolved"


# -- asset -------------------------------------------------------------------


def test_plan_asset_creates_planned(repo: Repo) -> None:
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/asset"))
    asset_id = repo.plan_asset(paper_id, _pdf_plan(), "mock_platform")
    asset = repo.get_asset(asset_id)
    assert asset is not None
    assert asset["state"] == "planned"
    assert asset["kind"] == "pdf"
    assert asset["auth_needed"] == "none"
    assert asset["source_adapter"] == "mock_platform"


def test_plan_asset_idempotent(repo: Repo) -> None:
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/idem"))
    a1 = repo.plan_asset(paper_id, _pdf_plan(), "mock_platform")
    a2 = repo.plan_asset(paper_id, _pdf_plan(), "mock_platform")
    assert a1 == a2
    assert len(repo.db.query("SELECT id FROM asset")) == 1


def test_plan_asset_null_version_dedupes(repo: Repo) -> None:
    """version=None 的两次 plan → 1 行（NULL-安全查后插）。"""
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/nv"))
    a1 = repo.plan_asset(paper_id, _pdf_plan(version=None), "mock_platform")
    a2 = repo.plan_asset(paper_id, _pdf_plan(version=None), "mock_platform")
    assert a1 == a2
    assert len(repo.db.query("SELECT id FROM asset")) == 1


def test_plan_asset_distinct_version_creates_rows(repo: Repo) -> None:
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/ver"))
    repo.plan_asset(paper_id, _pdf_plan(version="v1"), "mock_platform")
    repo.plan_asset(paper_id, _pdf_plan(version="v2"), "mock_platform")
    assert len(repo.db.query("SELECT id FROM asset")) == 2


def test_plan_asset_does_not_revert_fetched(repo: Repo) -> None:
    """已 fetched 的资产再 plan → 状态不回退、id 不变。"""
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/fetched"))
    asset_id = repo.plan_asset(paper_id, _pdf_plan(), "mock_platform")
    repo.mark_asset(asset_id, state="fetched", file_path="/x.pdf", bytes_=2048, sha256="abc")
    again = repo.plan_asset(paper_id, _pdf_plan(), "mock_platform")
    assert again == asset_id
    asset = repo.get_asset(asset_id)
    assert asset is not None and asset["state"] == "fetched"


def test_plan_asset_orphan_paper_rejected(repo: Repo) -> None:
    """asset.paper_id 外键：不存在的 paper → IntegrityError（事务回滚）。"""
    with pytest.raises(sqlite3.IntegrityError):
        repo.plan_asset("ghost_paper", _pdf_plan(), "mock_platform")


def test_get_asset_absent_returns_none(repo: Repo) -> None:
    assert repo.get_asset("nope") is None


# -- refresh_asset_plan（T7c 追加设计裁决：fetch 前 re-resolve 同步）----------


def test_refresh_asset_plan_updates_planned(repo: Repo) -> None:
    """planned 资产：url 与 auth_needed 被新 resolve 结果覆盖（其余字段不动）。"""
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/refresh"))
    asset_id = repo.plan_asset(
        paper_id, _pdf_plan(url="https://mock.local/pdf/old?fail=auth_expired"), "mock_platform"
    )
    repo.refresh_asset_plan(asset_id, url="https://mock.local/pdf/new", auth_needed="subscription")
    asset = repo.get_asset(asset_id)
    assert asset is not None
    assert asset["url"] == "https://mock.local/pdf/new"
    assert asset["auth_needed"] == "subscription"
    assert asset["state"] == "planned"  # 状态不被 refresh 触碰


def test_refresh_asset_plan_does_not_touch_fetched(repo: Repo) -> None:
    """已 fetched 的资产不回退不改（授权语义）：url/auth_needed/state 全保持。"""
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/refreshed"))
    asset_id = repo.plan_asset(paper_id, _pdf_plan(url="https://mock.local/pdf/a"), "mock_platform")
    repo.mark_asset(asset_id, state="fetched", file_path="/x.pdf", bytes_=1, sha256="h")
    repo.refresh_asset_plan(asset_id, url="https://mock.local/pdf/CHANGED", auth_needed="none")
    asset = repo.get_asset(asset_id)
    assert asset is not None
    assert asset["url"] == "https://mock.local/pdf/a"
    assert asset["auth_needed"] == "none"
    assert asset["state"] == "fetched"


def test_refresh_asset_plan_missing_asset_is_noop(repo: Repo) -> None:
    """不存在的 asset id：静默零行更新，不报错（fetch 手边路由自会处理缺行）。"""
    repo.refresh_asset_plan("no_such_asset", url="https://x", auth_needed="none")
    assert repo.get_asset("no_such_asset") is None


def test_refresh_asset_plan_refreshes_failed_state(repo: Repo) -> None:
    """非 fetched 的其余状态（如 failed）同样可刷新——重试路径需要新 url。"""
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/refail"))
    asset_id = repo.plan_asset(paper_id, _pdf_plan(url="https://mock.local/pdf/f"), "mock_platform")
    repo.mark_asset(asset_id, state="failed")
    repo.refresh_asset_plan(asset_id, url="https://mock.local/pdf/f2", auth_needed="none")
    asset = repo.get_asset(asset_id)
    assert asset is not None
    assert asset["url"] == "https://mock.local/pdf/f2"
    assert asset["state"] == "failed"  # refresh 只动执行细节，不动状态机


def test_mark_asset_fetched_sets_fields(repo: Repo) -> None:
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/mark"))
    asset_id = repo.plan_asset(paper_id, _pdf_plan(), "mock_platform")
    repo.mark_asset(
        asset_id, state="fetched", file_path="/data/x.pdf", bytes_=4096, sha256="deadbeef"
    )
    asset = repo.get_asset(asset_id)
    assert asset is not None
    assert asset["state"] == "fetched"
    assert asset["file_path"] == "/data/x.pdf"
    assert asset["bytes"] == 4096
    assert asset["sha256"] == "deadbeef"
    assert asset["fetched_at"] is not None


def test_mark_asset_gone_without_file(repo: Repo) -> None:
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/gone"))
    asset_id = repo.plan_asset(paper_id, _pdf_plan(), "mock_platform")
    repo.mark_asset(asset_id, state="gone")
    asset = repo.get_asset(asset_id)
    assert asset is not None
    assert asset["state"] == "gone"
    assert asset["fetched_at"] is None


def test_list_assets_filters(repo: Repo) -> None:
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/la"))
    a1 = repo.plan_asset(paper_id, _pdf_plan(version="v1"), "mock_platform")
    repo.plan_asset(paper_id, _pdf_plan(version="v2"), "mock_platform")
    repo.mark_asset(a1, state="fetched", file_path="/x.pdf", bytes_=1, sha256="h")
    assert len(repo.list_assets()) == 2
    assert len(repo.list_assets(venue_id=VENUE_ID)) == 2
    assert len(repo.list_assets(state="fetched")) == 1
    assert len(repo.list_assets(venue_id=VENUE_ID, state="planned")) == 1


# -- fetch_log ---------------------------------------------------------------


def test_add_and_query_fetch_logs(repo: Repo) -> None:
    repo.add_fetch_log(
        asset_id=None,
        task_id="t1",
        domain="mock.local",
        url="https://mock.local/pdf/1",
        http_status=200,
        bytes_=2048,
        elapsed_ms=12,
        rate_wait_ms=5,
    )
    repo.add_fetch_log(
        asset_id=None,
        task_id="t2",
        domain="other.local",
        url="https://other.local/x",
        http_status=404,
        bytes_=0,
        elapsed_ms=3,
        rate_wait_ms=0,
        error_class="gone",
    )
    assert len(repo.fetch_logs()) == 2
    mock_logs = repo.fetch_logs(domain="mock.local")
    assert len(mock_logs) == 1
    assert mock_logs[0]["rate_wait_ms"] == 5
    assert repo.fetch_logs(domain="other.local")[0]["error_class"] == "gone"


# -- counts 对账 -------------------------------------------------------------


def test_counts_reconciliation(repo: Repo) -> None:
    """assets_planned=全部 asset 行；assets_fetched=state='fetched' 行数。"""
    i1 = repo.upsert_issue(_issue(volume="1", number="1"), source="mock")
    i2 = repo.upsert_issue(_issue(volume="1", number="2"), source="mock")
    p1 = repo.upsert_paper(VENUE_ID, i1, _stub(doi="10.9999/c1", title="C1"))
    p2 = repo.upsert_paper(VENUE_ID, i2, _stub(doi="10.9999/c2", title="C2"))
    a1 = repo.plan_asset(p1, _pdf_plan(url="u1"), "mock_platform")
    repo.plan_asset(p2, _pdf_plan(url="u2"), "mock_platform")
    repo.mark_asset(a1, state="fetched", file_path="/1.pdf", bytes_=1, sha256="h1")

    counts = repo.counts(VENUE_ID)
    assert counts == {
        "issues": 2,
        "papers": 2,
        "assets_planned": 2,
        "assets_fetched": 1,
    }


def test_counts_empty_venue(repo: Repo) -> None:
    assert repo.counts(VENUE_ID) == {
        "issues": 0,
        "papers": 0,
        "assets_planned": 0,
        "assets_fetched": 0,
    }
