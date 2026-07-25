"""`dedupe_against_library` 去重对库（Phase 6 T3；design/09 §5 末"全源统一…去重"）——真 sqlite。

预置库中若干 identifier（经 `Repo.upsert_paper`——与生产写入路径共用同一
`ids.normalize_identifier` 归一入口），验证候选 `PaperStub` 流按 (scheme,value) 与既有库
比对的判重结果。`is_truncated`/`OverloadReport` 是纯函数，无需数据库，测试见
`tests/unit/test_subs_guard.py`。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.subs.guard import dedupe_against_library
from paper_crawler.types import PaperStub, VenueSpec

VENUE_ID = "mock_journal"


@pytest.fixture
def repo(tmp_path: Path, venue: VenueSpec) -> Iterator[Repo]:
    database = Database(tmp_path / "guard.sqlite")
    database.migrate()
    r = Repo(database)
    r.upsert_venue(venue)  # paper.venue_id 需要 venue 先存在（外键）
    yield r
    database.close()


def _stub(
    *, doi: str, title: str = "Paper", extra_ids: tuple[tuple[str, str], ...] = ()
) -> PaperStub:
    return PaperStub(title=title, identifiers=(("doi", doi), *extra_ids))


def test_dedupe_splits_new_and_duplicate_by_identifier(repo: Repo) -> None:
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.1/existing-a", title="Existing A"))
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.1/existing-b", title="Existing B"))

    candidates = [
        _stub(doi="10.1/existing-a", title="Existing A (seen again)"),
        _stub(doi="10.1/brand-new", title="Brand New"),
        _stub(doi="10.1/existing-b", title="Existing B (again)"),
    ]
    result = dedupe_against_library(candidates, repo.db)

    assert [s.title for s in result.new] == ["Brand New"]
    assert [s.title for s in result.duplicates] == [
        "Existing A (seen again)",
        "Existing B (again)",
    ]


def test_dedupe_normalizes_doi_case_and_prefix_before_comparing(repo: Repo) -> None:
    """判重口径须与 `Repo.upsert_paper` 写入口径一致（同一 `ids.normalize_identifier` 入口）。

    库内写入时 `10.1/MixedCase` 已被归一为小写 `10.1/mixedcase`；候选带
    `https://doi.org/` 前缀 + 大写形式，判重前须同样归一才能命中。
    """
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.1/MixedCase"))

    candidate = _stub(doi="https://doi.org/10.1/MIXEDCASE", title="Same Paper Different Form")
    result = dedupe_against_library([candidate], repo.db)

    assert result.new == ()
    assert [s.title for s in result.duplicates] == ["Same Paper Different Form"]


def test_dedupe_any_matching_identifier_marks_duplicate(repo: Repo) -> None:
    """多 identifier 的 stub：只要其一命中既有库，即整条判定为重复（不要求全部匹配）。"""
    repo.upsert_paper(
        VENUE_ID, None, _stub(doi="10.1/anchor", extra_ids=(("arxiv", "2401.00001"),))
    )

    candidate = _stub(doi="10.1/completely-different", extra_ids=(("arxiv", "2401.00001"),))
    result = dedupe_against_library([candidate], repo.db)

    assert result.duplicates and not result.new


def test_dedupe_no_hit_across_any_identifier_is_new(repo: Repo) -> None:
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.1/anchor"))

    candidate = _stub(doi="10.1/unrelated", extra_ids=(("arxiv", "2401.99999"),))
    result = dedupe_against_library([candidate], repo.db)

    assert result.new == (candidate,)
    assert result.duplicates == ()


def test_dedupe_empty_stream_returns_empty_result(repo: Repo) -> None:
    result = dedupe_against_library([], repo.db)
    assert result.new == ()
    assert result.duplicates == ()


def test_dedupe_stub_with_no_identifiers_is_treated_as_new(repo: Repo) -> None:
    """零 identifier（理论上不应出现——`PaperStub` 契约"至少 1 个"）：无法证明已存在，保守判新。"""
    orphan = PaperStub(title="No Identifiers At All", identifiers=())
    result = dedupe_against_library([orphan], repo.db)

    assert result.new == (orphan,)
    assert result.duplicates == ()


def test_dedupe_preserves_input_order_within_each_bucket(repo: Repo) -> None:
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.1/dup"))
    candidates = [
        _stub(doi="10.1/new-1", title="N1"),
        _stub(doi="10.1/dup", title="D1"),
        _stub(doi="10.1/new-2", title="N2"),
    ]
    result = dedupe_against_library(candidates, repo.db)

    assert [s.title for s in result.new] == ["N1", "N2"]
    assert [s.title for s in result.duplicates] == ["D1"]


def test_dedupe_empty_library_marks_everything_new(repo: Repo) -> None:
    candidates = [_stub(doi="10.1/a"), _stub(doi="10.1/b")]
    result = dedupe_against_library(candidates, repo.db)

    assert len(result.new) == 2
    assert result.duplicates == ()
