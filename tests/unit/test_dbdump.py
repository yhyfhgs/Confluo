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
from contextlib import closing
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
    with closing(Database(path)) as database:
        database.migrate()
        _populate(database, venue)


# -- 空库 ----------------------------------------------------------------


def test_canonical_dump_empty_database_has_all_table_keys(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.sqlite"
    with closing(Database(db_path)) as database:
        database.migrate()

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
    with closing(Database(db_a)) as raw_a, closing(Database(db_b)) as raw_b:
        ids_a = {row["id"] for row in raw_a.query("SELECT id FROM paper")}
        ids_b = {row["id"] for row in raw_b.query("SELECT id FROM paper")}
    assert ids_a.isdisjoint(ids_b)


# -- 少一行 / 字段不同 → 不相等 -----------------------------------------------


def test_canonical_dump_detects_missing_row(tmp_path: Path, venue: VenueSpec) -> None:
    db_a = tmp_path / "a.sqlite"
    db_b = tmp_path / "b.sqlite"
    _build_db(db_a, venue)

    with closing(Database(db_b)) as database:
        database.migrate()
        repo = Repo(database)
        repo.upsert_venue(venue)
        i1 = repo.upsert_issue(_issue(volume="1", number="1"), source="mock")
        repo.upsert_paper(VENUE_ID, i1, _stub(doi="10.9999/a", title="Paper A"))  # 缺 Paper B 整条

    assert canonical_dump(db_a) != canonical_dump(db_b)


def test_canonical_dump_detects_field_difference(tmp_path: Path, venue: VenueSpec) -> None:
    db_a = tmp_path / "a.sqlite"
    db_b = tmp_path / "b.sqlite"
    _build_db(db_a, venue)
    _build_db(db_b, venue)

    with closing(Database(db_b)) as database:
        database.execute("UPDATE asset SET bytes = 999999 WHERE bytes = 2048")

    assert canonical_dump(db_a) != canonical_dump(db_b)


# -- 外键翻译为业务键 ---------------------------------------------------------


def test_canonical_dump_translates_paper_id_to_title(tmp_path: Path, venue: VenueSpec) -> None:
    db_path = tmp_path / "fk.sqlite"
    _build_db(db_path, venue)
    dump = canonical_dump(db_path)

    identifier_titles = {row[0] for row in dump["identifier"]}
    assert identifier_titles == {"Paper A", "Paper B"}
    # 没有 26 字符裸 ULID 泄漏到 identifier 首列（title 字符串长度恒不是 26，用作简单反证）
    assert all(len(str(title)) != 26 for title in identifier_titles)

    # asset 的 paper 外键翻译为复合业务键 (title, primary_identifier)，而不是裸 ULID
    asset_paper_keys = {row[0] for row in dump["asset"]}
    assert asset_paper_keys == {
        ("Paper A", ("doi", "10.9999/a")),
        ("Paper B", ("doi", "10.9999/b")),
    }


def test_canonical_dump_paper_issue_link_uses_business_keys(
    tmp_path: Path, venue: VenueSpec
) -> None:
    db_path = tmp_path / "link.sqlite"
    _build_db(db_path, venue)
    dump = canonical_dump(db_path)

    paper_a_key = ("Paper A", ("doi", "10.9999/a"))
    links_for_a = [row for row in dump["paper_issue_link"] if row[0] == paper_a_key]
    assert len(links_for_a) == 2
    assert {row[1] for row in links_for_a} == {
        (VENUE_ID, "1", "1", None),
        (VENUE_ID, "1", "2", None),
    }


# -- 标题碰撞：翻译/排序键消歧（reviewer 对抗构造，回归防护） -----------------------


def test_canonical_dump_disambiguates_asset_ownership_on_title_collision(
    tmp_path: Path, venue: VenueSpec
) -> None:
    """两 paper 同标题时，若两库里"谁拥有哪个 asset"这一真实业务事实不同（此处用
    sha256 互换构造），canonical_dump 必须能分辨——不能因为都叫同一个标题就被
    误判为相等。这是验证 primary_identifier 消歧确实生效的正向用例。
    """
    db_a = tmp_path / "swap_a.sqlite"
    db_b = tmp_path / "swap_b.sqlite"

    with closing(Database(db_a)) as database_a:
        database_a.migrate()
        repo_a = Repo(database_a)
        repo_a.upsert_venue(venue)
        p1a = repo_a.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/d1", title="Same Title"))
        p2a = repo_a.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/d2", title="Same Title"))
        a1a = repo_a.plan_asset(p1a, _pdf_plan(), "mock_platform")
        a2a = repo_a.plan_asset(p2a, _pdf_plan(), "mock_platform")
        repo_a.mark_asset(a1a, state="fetched", file_path="/x", bytes_=1, sha256="hash-1")
        repo_a.mark_asset(a2a, state="fetched", file_path="/y", bytes_=1, sha256="hash-2")

    with closing(Database(db_b)) as database_b:
        database_b.migrate()
        repo_b = Repo(database_b)
        repo_b.upsert_venue(venue)
        p1b = repo_b.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/d1", title="Same Title"))
        p2b = repo_b.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/d2", title="Same Title"))
        a1b = repo_b.plan_asset(p1b, _pdf_plan(), "mock_platform")
        a2b = repo_b.plan_asset(p2b, _pdf_plan(), "mock_platform")
        # 互换：doi=d1 的论文这次拿到 hash-2，doi=d2 的论文拿到 hash-1（真实业务差异）
        repo_b.mark_asset(a1b, state="fetched", file_path="/x", bytes_=1, sha256="hash-2")
        repo_b.mark_asset(a2b, state="fetched", file_path="/y", bytes_=1, sha256="hash-1")

    dump_a, dump_b = canonical_dump(db_a), canonical_dump(db_b)
    assert dump_a != dump_b
    # 定位到具体差异：doi=d1 的论文在两库分别持有不同的 sha256
    key_d1 = ("Same Title", ("doi", "10.9999/d1"))
    sha_a = next(row[7] for row in dump_a["asset"] if row[0] == key_d1)
    sha_b = next(row[7] for row in dump_b["asset"] if row[0] == key_d1)
    assert sha_a == "hash-1"
    assert sha_b == "hash-2"


def test_canonical_dump_equal_when_title_collision_only_insertion_order_differs(
    tmp_path: Path, venue: VenueSpec
) -> None:
    """两 paper 同标题、asset 的 kind/version 也相同（仅靠 title/kind/version 排不出
    确定顺序）时，若两库的业务赋值（谁拥有哪个 sha256）完全相同、只是两库的插入顺序
    相反，canonical_dump 必须相等——kill-9 中断重跑正是典型的"插入顺序不同、业务数据
    相同"场景（AC-1.3），这是本次修复要堵住的回归点。
    """
    db_a = tmp_path / "order_a.sqlite"
    db_b = tmp_path / "order_b.sqlite"

    with closing(Database(db_a)) as database_a:
        database_a.migrate()
        repo_a = Repo(database_a)
        repo_a.upsert_venue(venue)
        p1a = repo_a.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/d1", title="Same Title"))
        p2a = repo_a.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/d2", title="Same Title"))
        a1a = repo_a.plan_asset(p1a, _pdf_plan(), "mock_platform")
        a2a = repo_a.plan_asset(p2a, _pdf_plan(), "mock_platform")
        repo_a.mark_asset(a1a, state="fetched", file_path="/x", bytes_=1, sha256="hash-1")
        repo_a.mark_asset(a2a, state="fetched", file_path="/y", bytes_=1, sha256="hash-2")

    with closing(Database(db_b)) as database_b:
        database_b.migrate()
        repo_b = Repo(database_b)
        repo_b.upsert_venue(venue)
        # 插入顺序相反：先建 doi=d2 的论文，再建 doi=d1 的
        p2b = repo_b.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/d2", title="Same Title"))
        p1b = repo_b.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/d1", title="Same Title"))
        a2b = repo_b.plan_asset(p2b, _pdf_plan(), "mock_platform")
        a1b = repo_b.plan_asset(p1b, _pdf_plan(), "mock_platform")
        # 业务赋值与 DB A 完全相同：doi=d1 → hash-1，doi=d2 → hash-2（只是插入顺序反了）
        repo_b.mark_asset(a1b, state="fetched", file_path="/x", bytes_=1, sha256="hash-1")
        repo_b.mark_asset(a2b, state="fetched", file_path="/y", bytes_=1, sha256="hash-2")

    assert canonical_dump(db_a) == canonical_dump(db_b)


def test_canonical_dump_disambiguates_paper_issue_link_on_title_collision(
    tmp_path: Path, venue: VenueSpec
) -> None:
    """paper_issue_link 版的对抗用例（a）：同标题两 paper 分别链接到不同 issue，两库
    间"谁链接到哪个 issue"互换 → 属于真实业务差异，dump 必不等。"""
    db_a = tmp_path / "link_swap_a.sqlite"
    db_b = tmp_path / "link_swap_b.sqlite"

    with closing(Database(db_a)) as database_a:
        database_a.migrate()
        repo_a = Repo(database_a)
        repo_a.upsert_venue(venue)
        i1a = repo_a.upsert_issue(_issue(volume="1", number="1"), source="mock")
        i2a = repo_a.upsert_issue(_issue(volume="1", number="2"), source="mock")
        repo_a.upsert_paper(VENUE_ID, i1a, _stub(doi="10.9999/d1", title="Same Title"))
        repo_a.upsert_paper(VENUE_ID, i2a, _stub(doi="10.9999/d2", title="Same Title"))

    with closing(Database(db_b)) as database_b:
        database_b.migrate()
        repo_b = Repo(database_b)
        repo_b.upsert_venue(venue)
        i1b = repo_b.upsert_issue(_issue(volume="1", number="1"), source="mock")
        i2b = repo_b.upsert_issue(_issue(volume="1", number="2"), source="mock")
        # 互换：doi=d1 这次链到 (1,2)，doi=d2 链到 (1,1)
        repo_b.upsert_paper(VENUE_ID, i2b, _stub(doi="10.9999/d1", title="Same Title"))
        repo_b.upsert_paper(VENUE_ID, i1b, _stub(doi="10.9999/d2", title="Same Title"))

    assert canonical_dump(db_a) != canonical_dump(db_b)


def test_canonical_dump_paper_issue_link_equal_when_only_insertion_order_differs(
    tmp_path: Path, venue: VenueSpec
) -> None:
    """paper_issue_link 版的对抗用例（b）：同标题两 paper 分别链接到不同 issue，两库
    间的"谁链接到哪个 issue"业务赋值完全相同、只是两库的建papper/issue 顺序相反 →
    dump 必相等。"""
    db_a = tmp_path / "link_order_a.sqlite"
    db_b = tmp_path / "link_order_b.sqlite"

    with closing(Database(db_a)) as database_a:
        database_a.migrate()
        repo_a = Repo(database_a)
        repo_a.upsert_venue(venue)
        i1a = repo_a.upsert_issue(_issue(volume="1", number="1"), source="mock")
        i2a = repo_a.upsert_issue(_issue(volume="1", number="2"), source="mock")
        repo_a.upsert_paper(VENUE_ID, i1a, _stub(doi="10.9999/d1", title="Same Title"))
        repo_a.upsert_paper(VENUE_ID, i2a, _stub(doi="10.9999/d2", title="Same Title"))

    with closing(Database(db_b)) as database_b:
        database_b.migrate()
        repo_b = Repo(database_b)
        repo_b.upsert_venue(venue)
        # 顺序相反：先建第二期与 d2 的链接，再建第一期与 d1 的链接；业务赋值不变
        i2b = repo_b.upsert_issue(_issue(volume="1", number="2"), source="mock")
        i1b = repo_b.upsert_issue(_issue(volume="1", number="1"), source="mock")
        repo_b.upsert_paper(VENUE_ID, i2b, _stub(doi="10.9999/d2", title="Same Title"))
        repo_b.upsert_paper(VENUE_ID, i1b, _stub(doi="10.9999/d1", title="Same Title"))

    assert canonical_dump(db_a) == canonical_dump(db_b)


def test_canonical_dump_translates_era_id_when_present(tmp_path: Path, venue: VenueSpec) -> None:
    """venue_era 目前没有 Repo API（Phase 1 无写入路径），直接建行验证前向兼容的翻译规则。"""
    db_path = tmp_path / "era.sqlite"
    with closing(Database(db_path)) as database:
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

    dump = canonical_dump(db_path)
    assert dump["issue"] == [(VENUE_ID, (2024, "V1"), "1", "1", 2024, None, None, "mock", None)]


def test_canonical_dump_issue_era_key_is_none_when_era_id_null(
    tmp_path: Path, venue: VenueSpec
) -> None:
    db_path = tmp_path / "noera.sqlite"
    with closing(Database(db_path)) as database:
        database.migrate()
        repo = Repo(database)
        repo.upsert_venue(venue)
        repo.upsert_issue(_issue(volume="1", number="1"), source="mock")

    dump = canonical_dump(db_path)
    assert dump["issue"][0][1] is None  # era_key 位（第 2 列）


# -- 行序 ---------------------------------------------------------------------


def test_canonical_dump_rows_are_sorted_by_business_key(tmp_path: Path, venue: VenueSpec) -> None:
    db_path = tmp_path / "order.sqlite"
    with closing(Database(db_path)) as database:
        database.migrate()
        repo = Repo(database)
        repo.upsert_venue(venue)
        # 故意乱序插入
        repo.upsert_issue(_issue(volume="2", number="1"), source="mock")
        repo.upsert_issue(_issue(volume="1", number="2"), source="mock")
        repo.upsert_issue(_issue(volume="1", number="1"), source="mock")
        repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/z", title="Zebra"))
        repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/a", title="Alpha"))

    dump = canonical_dump(db_path)
    issue_volume_number = [(row[2], row[3]) for row in dump["issue"]]
    assert issue_volume_number == [("1", "1"), ("1", "2"), ("2", "1")]
    paper_titles = [row[0] for row in dump["paper"]]
    assert paper_titles == ["Alpha", "Zebra"]
