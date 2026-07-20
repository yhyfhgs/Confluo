"""``tests/helpers/dbdump.py`` 的单测（T8a；AC-1.3 canonical dump 口径的可执行验证）。

覆盖点：
- 剔除的列（id/created_at/updated_at/fetched_at/file_path）不参与比较——两个独立生成的库
  （不同 ULID、不同写入时间戳）只要业务数据相同即 ``canonical_dump`` 相等；
- 外键翻译为业务键（venue_id 原样保留、issue 翻译为 (venue_id,volume,number,label)、
  paper 翻译为 title、era_id 翻译为 (year,label)）；
- 行序按业务键排序，不受插入顺序影响；
- 少一行 / 字段不同 → 不相等（kill-9 幂等验收要能真的检出回归）。
"""

from __future__ import annotations

import time
from pathlib import Path

from helpers.dbdump import canonical_dump
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.types import (
    AssetKind,
    AssetPlan,
    AuthLevel,
    IssueRef,
    PaperStub,
    VenueSpec,
    new_ulid,
)

VENUE_ID = "mock_journal"


def _issue(*, volume: str, number: str, year: int = 2024, label: str | None = None) -> IssueRef:
    return IssueRef(venue_id=VENUE_ID, volume=volume, number=number, year=year, label=label)


def _stub(*, doi: str, title: str, extra_ids: tuple[tuple[str, str], ...] = ()) -> PaperStub:
    return PaperStub(title=title, identifiers=(("doi", doi), *extra_ids))


def _pdf_plan(*, version: str | None = None) -> AssetPlan:
    return AssetPlan(
        kind=AssetKind.PDF,
        url="https://mock.local/pdf/x",
        auth_needed=AuthLevel.NONE,
        version=version,
    )


def _populate(database: Database, venue: VenueSpec) -> None:
    """建一份小而全的语料：2 期、2 篇论文（其一跨两期）、2 个 fetched asset。"""
    repo = Repo(database)
    repo.upsert_venue(venue)
    i1 = repo.upsert_issue(_issue(volume="1", number="1"), source="mock")
    i2 = repo.upsert_issue(_issue(volume="1", number="2"), source="mock")
    p1 = repo.upsert_paper(VENUE_ID, i1, _stub(doi="10.9999/a", title="Paper A"))
    p2 = repo.upsert_paper(VENUE_ID, i2, _stub(doi="10.9999/b", title="Paper B"))
    repo.upsert_paper(VENUE_ID, i2, _stub(doi="10.9999/a", title="Paper A"))  # p1 也现身于 i2
    a1 = repo.plan_asset(p1, _pdf_plan(), "mock_platform")
    a2 = repo.plan_asset(p2, _pdf_plan(), "mock_platform")
    repo.mark_asset(
        a1,
        state="fetched",
        file_path=f"/data/pdf/{VENUE_ID}/2024/{p1}.pdf",
        bytes_=2048,
        sha256="hash-a",
    )
    repo.mark_asset(
        a2,
        state="fetched",
        file_path=f"/data/pdf/{VENUE_ID}/2024/{p2}.pdf",
        bytes_=4096,
        sha256="hash-b",
    )


def _build_db(path: Path, venue: VenueSpec) -> None:
    database = Database(path)
    database.migrate()
    _populate(database, venue)
    database.close()


# -- 空库 ----------------------------------------------------------------


def test_canonical_dump_empty_database_has_all_table_keys(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.sqlite"
    database = Database(db_path)
    database.migrate()
    database.close()

    dump = canonical_dump(db_path)
    assert set(dump) == {"venue", "issue", "paper", "identifier", "asset", "paper_issue_link"}
    assert all(rows == [] for rows in dump.values())


# -- 跨库相等（不同 ULID / 时间戳） ------------------------------------------


def test_canonical_dump_equal_despite_different_ulids_and_timestamps(
    tmp_path: Path, venue: VenueSpec
) -> None:
    db_a = tmp_path / "a.sqlite"
    db_b = tmp_path / "b.sqlite"
    _build_db(db_a, venue)
    time.sleep(0.01)  # 确保两库写入时间戳确实不同——避免巧合相等掩盖了"未剔除时间戳"的 bug
    _build_db(db_b, venue)

    dump_a = canonical_dump(db_a)
    dump_b = canonical_dump(db_b)
    assert dump_a == dump_b

    # 佐证两库的物理主键确实不同（否则上面的相等断言是平凡的、测不出剔除逻辑是否生效）
    raw_a, raw_b = Database(db_a), Database(db_b)
    ids_a = {row["id"] for row in raw_a.query("SELECT id FROM paper")}
    ids_b = {row["id"] for row in raw_b.query("SELECT id FROM paper")}
    raw_a.close()
    raw_b.close()
    assert ids_a.isdisjoint(ids_b)


# -- 少一行 / 字段不同 → 不相等 -----------------------------------------------


def test_canonical_dump_detects_missing_row(tmp_path: Path, venue: VenueSpec) -> None:
    db_a = tmp_path / "a.sqlite"
    db_b = tmp_path / "b.sqlite"
    _build_db(db_a, venue)

    database = Database(db_b)
    database.migrate()
    repo = Repo(database)
    repo.upsert_venue(venue)
    i1 = repo.upsert_issue(_issue(volume="1", number="1"), source="mock")
    repo.upsert_paper(VENUE_ID, i1, _stub(doi="10.9999/a", title="Paper A"))  # 缺 Paper B 整条
    database.close()

    assert canonical_dump(db_a) != canonical_dump(db_b)


def test_canonical_dump_detects_field_difference(tmp_path: Path, venue: VenueSpec) -> None:
    db_a = tmp_path / "a.sqlite"
    db_b = tmp_path / "b.sqlite"
    _build_db(db_a, venue)
    _build_db(db_b, venue)

    database = Database(db_b)
    database.execute("UPDATE asset SET bytes = 999999 WHERE bytes = 2048")
    database.close()

    assert canonical_dump(db_a) != canonical_dump(db_b)


# -- 外键翻译为业务键 ---------------------------------------------------------


def test_canonical_dump_translates_paper_id_to_title(tmp_path: Path, venue: VenueSpec) -> None:
    db_path = tmp_path / "fk.sqlite"
    _build_db(db_path, venue)
    dump = canonical_dump(db_path)

    identifier_titles = {row[0] for row in dump["identifier"]}
    asset_titles = {row[0] for row in dump["asset"]}
    assert identifier_titles == {"Paper A", "Paper B"}
    assert asset_titles == {"Paper A", "Paper B"}
    # 没有 26 字符裸 ULID 泄漏到首列（title 字符串长度恒不是 26，用作简单反证）
    assert all(len(str(title)) != 26 for title in identifier_titles | asset_titles)


def test_canonical_dump_paper_issue_link_uses_business_keys(
    tmp_path: Path, venue: VenueSpec
) -> None:
    db_path = tmp_path / "link.sqlite"
    _build_db(db_path, venue)
    dump = canonical_dump(db_path)

    links_for_a = [row for row in dump["paper_issue_link"] if row[0] == "Paper A"]
    assert len(links_for_a) == 2
    assert {row[1] for row in links_for_a} == {
        (VENUE_ID, "1", "1", None),
        (VENUE_ID, "1", "2", None),
    }


def test_canonical_dump_translates_era_id_when_present(tmp_path: Path, venue: VenueSpec) -> None:
    """venue_era 目前没有 Repo API（Phase 1 无写入路径），直接建行验证前向兼容的翻译规则。"""
    db_path = tmp_path / "era.sqlite"
    database = Database(db_path)
    database.migrate()
    repo = Repo(database)
    repo.upsert_venue(venue)
    era_id = new_ulid()
    database.execute(
        "INSERT INTO venue_era (id, venue_id, year, label, status) VALUES (?,?,?,?,?)",
        (era_id, VENUE_ID, 2024, "V1", "active"),
    )
    database.execute(
        "INSERT INTO issue "
        "(id, venue_id, era_id, volume, number, year, label, pub_date, source, "
        " paper_count_claimed) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (new_ulid(), VENUE_ID, era_id, "1", "1", 2024, None, None, "mock", None),
    )
    database.close()

    dump = canonical_dump(db_path)
    assert dump["issue"] == [(VENUE_ID, (2024, "V1"), "1", "1", 2024, None, None, "mock", None)]


def test_canonical_dump_issue_era_key_is_none_when_era_id_null(
    tmp_path: Path, venue: VenueSpec
) -> None:
    db_path = tmp_path / "noera.sqlite"
    database = Database(db_path)
    database.migrate()
    repo = Repo(database)
    repo.upsert_venue(venue)
    repo.upsert_issue(_issue(volume="1", number="1"), source="mock")
    database.close()

    dump = canonical_dump(db_path)
    assert dump["issue"][0][1] is None  # era_key 位（第 2 列）


# -- 行序 ---------------------------------------------------------------------


def test_canonical_dump_rows_are_sorted_by_business_key(tmp_path: Path, venue: VenueSpec) -> None:
    db_path = tmp_path / "order.sqlite"
    database = Database(db_path)
    database.migrate()
    repo = Repo(database)
    repo.upsert_venue(venue)
    # 故意乱序插入
    repo.upsert_issue(_issue(volume="2", number="1"), source="mock")
    repo.upsert_issue(_issue(volume="1", number="2"), source="mock")
    repo.upsert_issue(_issue(volume="1", number="1"), source="mock")
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/z", title="Zebra"))
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/a", title="Alpha"))
    database.close()

    dump = canonical_dump(db_path)
    issue_volume_number = [(row[2], row[3]) for row in dump["issue"]]
    assert issue_volume_number == [("1", "1"), ("1", "2"), ("2", "1")]
    paper_titles = [row[0] for row in dump["paper"]]
    assert paper_titles == ["Alpha", "Zebra"]
