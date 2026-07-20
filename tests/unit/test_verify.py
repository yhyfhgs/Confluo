"""``verify_store`` 的单测（T8a；design/05 §5.4 基础版，AC-3.3 正式验收在 Phase 3）。

人为制造三类不一致（缺文件/孤儿文件/哈希不符），断言逐类检出且修复建议正确；
另断言只读语义（不改 DB、不改磁盘）与输出排序稳定性。
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest

from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.types import AssetKind, AssetPlan, AuthLevel, PaperStub, VenueSpec
from paper_crawler.verify import VerifyIssue, verify_store

VENUE_ID = "mock_journal"
_PDF_BYTES = b"%PDF-1.4\n%test\n"


def _stub(*, doi: str, title: str) -> PaperStub:
    return PaperStub(title=title, identifiers=(("doi", doi),))


def _pdf_plan(version: str | None = None) -> AssetPlan:
    return AssetPlan(
        kind=AssetKind.PDF,
        url="https://mock.local/pdf/x",
        auth_needed=AuthLevel.NONE,
        version=version,
    )


def _write_pdf(path: Path, content: bytes = _PDF_BYTES) -> str:
    """把 content 写到 path（自动建父目录），返回其 sha256 十六进制摘要。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


@pytest.fixture
def repo(tmp_path: Path, venue: VenueSpec) -> Iterator[Repo]:
    database = Database(tmp_path / "verify.sqlite")
    database.migrate()
    r = Repo(database)
    r.upsert_venue(venue)
    yield r
    database.close()


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    (d / "pdf").mkdir(parents=True)
    return d


# -- 全部一致 → 空列表 --------------------------------------------------------


def test_verify_store_no_issues_when_consistent(repo: Repo, data_dir: Path) -> None:
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/ok", title="Ok Paper"))
    asset_id = repo.plan_asset(paper_id, _pdf_plan(), "mock_platform")
    file_path = data_dir / "pdf" / VENUE_ID / "2024" / f"{paper_id}.pdf"
    sha = _write_pdf(file_path)
    repo.mark_asset(
        asset_id, state="fetched", file_path=str(file_path), bytes_=len(_PDF_BYTES), sha256=sha
    )

    assert verify_store(repo, data_dir) == []


def test_verify_store_ignores_planned_asset_without_file(repo: Repo, data_dir: Path) -> None:
    """未 fetch 的 asset（state=planned）没有文件是正常状态，不应报 missing_file。"""
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/pl", title="Planned Paper"))
    repo.plan_asset(paper_id, _pdf_plan(), "mock_platform")

    assert verify_store(repo, data_dir) == []


def test_verify_store_empty_store_no_issues(repo: Repo, data_dir: Path) -> None:
    assert verify_store(repo, data_dir) == []


# -- missing_file -------------------------------------------------------------


def test_verify_store_detects_missing_file_when_path_absent_on_disk(
    repo: Repo, data_dir: Path
) -> None:
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/miss", title="Missing Paper"))
    asset_id = repo.plan_asset(paper_id, _pdf_plan(), "mock_platform")
    file_path = data_dir / "pdf" / VENUE_ID / "2024" / f"{paper_id}.pdf"
    repo.mark_asset(
        asset_id, state="fetched", file_path=str(file_path), bytes_=100, sha256="deadbeef"
    )
    # 注意：从未真的写文件——磁盘上不存在

    issues = verify_store(repo, data_dir)
    assert issues == [
        VerifyIssue(
            kind="missing_file", asset_id=asset_id, file_path=str(file_path), suggestion="re-fetch"
        )
    ]


def test_verify_store_detects_missing_file_when_file_path_empty(repo: Repo, data_dir: Path) -> None:
    """asset.file_path 本身为空（NULL）但 state 已被标 fetched（异常路径）→ missing_file。"""
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/nopath", title="No Path Paper"))
    asset_id = repo.plan_asset(paper_id, _pdf_plan(), "mock_platform")
    repo.mark_asset(asset_id, state="fetched")  # 不传 file_path，保持 NULL

    issues = verify_store(repo, data_dir)
    assert issues == [
        VerifyIssue(kind="missing_file", asset_id=asset_id, file_path="", suggestion="re-fetch")
    ]


# -- orphan_file ----------------------------------------------------------------


def test_verify_store_detects_orphan_file(repo: Repo, data_dir: Path) -> None:
    orphan_path = data_dir / "pdf" / VENUE_ID / "2024" / "orphan.pdf"
    _write_pdf(orphan_path)

    issues = verify_store(repo, data_dir)
    assert issues == [
        VerifyIssue(
            kind="orphan_file", asset_id=None, file_path=str(orphan_path), suggestion="adopt"
        )
    ]


def test_verify_store_known_file_is_not_orphan(repo: Repo, data_dir: Path) -> None:
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/known", title="Known Paper"))
    asset_id = repo.plan_asset(paper_id, _pdf_plan(), "mock_platform")
    file_path = data_dir / "pdf" / VENUE_ID / "2024" / f"{paper_id}.pdf"
    sha = _write_pdf(file_path)
    repo.mark_asset(asset_id, state="fetched", file_path=str(file_path), bytes_=1, sha256=sha)

    assert verify_store(repo, data_dir) == []


def test_verify_store_ignores_files_outside_pdf_subtree(repo: Repo, data_dir: Path) -> None:
    """data_dir 下 pdf/ 以外的目录（如 si/）不在 orphan 扫描范围内（design/06 §4 范围声明）。"""
    (data_dir / "si").mkdir()
    _write_pdf(data_dir / "si" / "supplement.pdf")

    assert verify_store(repo, data_dir) == []


def test_verify_store_handles_missing_pdf_directory(repo: Repo, tmp_path: Path) -> None:
    """data_dir/pdf 尚不存在（如 `Config.ensure_dirs()` 还没跑过）时不应报错，等同于空目录。"""
    fresh_data_dir = tmp_path / "fresh_data"
    fresh_data_dir.mkdir()

    assert verify_store(repo, fresh_data_dir) == []


# -- hash_mismatch ----------------------------------------------------------------


def test_verify_store_detects_hash_mismatch(repo: Repo, data_dir: Path) -> None:
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/hash", title="Hash Paper"))
    asset_id = repo.plan_asset(paper_id, _pdf_plan(), "mock_platform")
    file_path = data_dir / "pdf" / VENUE_ID / "2024" / f"{paper_id}.pdf"
    _write_pdf(file_path)  # 实际内容
    repo.mark_asset(
        asset_id, state="fetched", file_path=str(file_path), bytes_=1, sha256="not-the-real-hash"
    )

    issues = verify_store(repo, data_dir)
    assert issues == [
        VerifyIssue(
            kind="hash_mismatch",
            asset_id=asset_id,
            file_path=str(file_path),
            suggestion="quarantine",
        )
    ]


def test_verify_store_hash_mismatch_does_not_require_fetched_state(
    repo: Repo, data_dir: Path
) -> None:
    """hash_mismatch 的检出条件只看"文件存在 + sha256 非空"，不像 missing_file 那样限定
    state='fetched'（口径原文对 hash_mismatch 未提 state 限定）。此用例锁定该行为，防止
    未来被误"简化"成只检查 fetched 资产。
    """
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/gone", title="Gone Paper"))
    asset_id = repo.plan_asset(paper_id, _pdf_plan(), "mock_platform")
    file_path = data_dir / "pdf" / VENUE_ID / "2024" / f"{paper_id}.pdf"
    _write_pdf(file_path)
    repo.mark_asset(asset_id, state="gone", file_path=str(file_path), bytes_=1, sha256="stale-hash")

    issues = verify_store(repo, data_dir)
    assert issues == [
        VerifyIssue(
            kind="hash_mismatch",
            asset_id=asset_id,
            file_path=str(file_path),
            suggestion="quarantine",
        )
    ]


def test_verify_store_no_hash_mismatch_when_sha256_not_recorded(repo: Repo, data_dir: Path) -> None:
    """asset.sha256 为空时不做哈希校验（没有基准可比）。"""
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/nohash", title="No Hash Paper"))
    asset_id = repo.plan_asset(paper_id, _pdf_plan(), "mock_platform")
    file_path = data_dir / "pdf" / VENUE_ID / "2024" / f"{paper_id}.pdf"
    _write_pdf(file_path)
    repo.mark_asset(asset_id, state="fetched", file_path=str(file_path), bytes_=1)  # sha256 缺省

    assert verify_store(repo, data_dir) == []


# -- 排序 ------------------------------------------------------------------------


def test_verify_store_results_sorted_by_kind_then_path(repo: Repo, data_dir: Path) -> None:
    _write_pdf(data_dir / "pdf" / "zz-orphan.pdf")  # orphan_file

    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/sort-miss", title="Sort Miss"))
    asset_id = repo.plan_asset(paper_id, _pdf_plan(), "mock_platform")
    missing_path = data_dir / "pdf" / "aa-missing.pdf"
    repo.mark_asset(asset_id, state="fetched", file_path=str(missing_path), bytes_=1, sha256="x")

    paper_id2 = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/sort-hash", title="Sort Hash"))
    asset_id2 = repo.plan_asset(paper_id2, _pdf_plan(), "mock_platform")
    hash_path = data_dir / "pdf" / "bb-hash.pdf"
    _write_pdf(hash_path)
    repo.mark_asset(asset_id2, state="fetched", file_path=str(hash_path), bytes_=1, sha256="wrong")

    issues = verify_store(repo, data_dir)
    kinds = [issue.kind for issue in issues]
    assert kinds == ["hash_mismatch", "missing_file", "orphan_file"]


def test_verify_store_orders_same_kind_issues_by_file_path(repo: Repo, data_dir: Path) -> None:
    _write_pdf(data_dir / "pdf" / "zzz-second.pdf")
    _write_pdf(data_dir / "pdf" / "aaa-first.pdf")

    issues = verify_store(repo, data_dir)
    assert [issue.kind for issue in issues] == ["orphan_file", "orphan_file"]
    paths = [issue.file_path for issue in issues]
    assert paths == sorted(paths)


# -- 只读 ------------------------------------------------------------------------


def test_verify_store_is_read_only(repo: Repo, data_dir: Path) -> None:
    """design/05 §5.4"输出修复建议"——只读，不自动修：不改 DB 行、不动磁盘文件。"""
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/ro", title="Read Only Paper"))
    asset_id = repo.plan_asset(paper_id, _pdf_plan(), "mock_platform")
    file_path = data_dir / "pdf" / VENUE_ID / "2024" / f"{paper_id}.pdf"
    repo.mark_asset(
        asset_id, state="fetched", file_path=str(file_path), bytes_=1, sha256="deadbeef"
    )
    orphan_path = data_dir / "pdf" / "keep-me.pdf"
    _write_pdf(orphan_path)

    before_row = repo.get_asset(asset_id)
    assert before_row is not None
    before = dict(before_row)

    verify_store(repo, data_dir)

    after_row = repo.get_asset(asset_id)
    assert after_row is not None
    assert dict(after_row) == before
    assert orphan_path.read_bytes() == _PDF_BYTES
