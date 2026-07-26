"""``verify_store`` 的单测（T8a；design/05 §5.4 基础版，AC-3.3 正式验收在 Phase 3）。

人为制造三类不一致（缺文件/孤儿文件/哈希不符），断言逐类检出且修复建议正确；
另断言只读语义（不改 DB、不改磁盘）与输出排序稳定性。
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest

from helpers.fulltext_schema import write_fulltext_row, write_legacy_fulltext_row
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.types import AssetKind, AssetPlan, AuthLevel, PaperStub, VenueSpec
from paper_crawler.verify import VerifyIssue, count_pending_extraction, verify_store

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


def _si_plan(version: str | None = None) -> AssetPlan:
    return AssetPlan(
        kind=AssetKind.SI,
        url="https://mock.local/si/x/supplement.zip",
        expected_type="application/zip",
        auth_needed=AuthLevel.NONE,
        version=version,
    )


def _write_pdf(path: Path, content: bytes = _PDF_BYTES) -> str:
    """把 content 写到 path（自动建父目录），返回其 sha256 十六进制摘要。

    名字沿用 T8a 先例，但内容不限于 PDF——si/fulltext 测试同样复用本 helper 写
    zip/txt 等任意字节内容（`verify_store` 本就只做字节级 sha256 比对，不关心
    文件语义类型）。
    """
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


def test_verify_store_ignores_files_outside_known_subtrees(repo: Repo, data_dir: Path) -> None:
    """data_dir 下 pdf/si/fulltext 以外的目录（如 export/、tmp/）不在孤儿扫描范围内
    （design/12 §9.2：T14 把扫描范围显式扩到 pdf/si/fulltext 三棵子树，export/tmp
    仍不产出对账产物）。si/ 自 T14 起已纳入扫描范围——本用例原以 si/ 作越界例证，
    现已不成立，改测真正越界的 export/tmp（见下方 si 专属测试组的孤儿检出用例）。
    """
    (data_dir / "export").mkdir()
    _write_pdf(data_dir / "export" / "report.pdf")
    (data_dir / "tmp").mkdir()
    _write_pdf(data_dir / "tmp" / "some.part")

    assert verify_store(repo, data_dir) == []


def test_verify_store_handles_missing_si_and_fulltext_directories(
    repo: Repo, data_dir: Path
) -> None:
    """`data_dir/si`、`data_dir/fulltext` 尚不存在时不应报错（同 `pdf/` 既有先例，见
    `test_verify_store_handles_missing_pdf_directory`）。"""
    assert not (data_dir / "si").exists()
    assert not (data_dir / "fulltext").exists()

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


# -- si（asset 表面；孤儿判定=文件级，design/12 §9.2 裁决）-----------------------------
#
# si asset 与 pdf 同构（同一 `asset` 表、同一 `repo.list_assets()`，kind 无关）——
# missing_file/hash_mismatch 的判据与 pdf 完全一致，故不逐类重复整套用例，只各补一例
# 锁定"si 确实被扫描到"；孤儿判定单独用一例证明是**文件级**而非目录级。


def test_verify_store_detects_si_missing_file(repo: Repo, data_dir: Path) -> None:
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/si-miss", title="SI Missing"))
    asset_id = repo.plan_asset(paper_id, _si_plan(), "mock_platform")
    file_path = data_dir / "si" / VENUE_ID / "2024" / paper_id / "supplement.zip"
    repo.mark_asset(
        asset_id, state="fetched", file_path=str(file_path), bytes_=10, sha256="deadbeef"
    )
    # 注意：从未真的写文件——磁盘上不存在

    issues = verify_store(repo, data_dir)
    assert issues == [
        VerifyIssue(
            kind="missing_file", asset_id=asset_id, file_path=str(file_path), suggestion="re-fetch"
        )
    ]


def test_verify_store_detects_si_hash_mismatch(repo: Repo, data_dir: Path) -> None:
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/si-hash", title="SI Hash"))
    asset_id = repo.plan_asset(paper_id, _si_plan(), "mock_platform")
    file_path = data_dir / "si" / VENUE_ID / "2024" / paper_id / "supplement.zip"
    _write_pdf(file_path, b"PK\x03\x04actual-zip-bytes")
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


def test_verify_store_detects_si_orphan_file_at_file_level_not_directory_level(
    repo: Repo, data_dir: Path
) -> None:
    """si"每 paper 一目录多文件"结构按**文件级**孤儿判定（design/12 §9.2 裁决，T14 卡
    指名由 design/12 裁决）：同一 paper 的 si 目录下，一个文件被正确记录、另一个未
    记录，后者仍须单独检出——若误做目录级判定（"该目录下已有被记录的文件，判定该
    paper 的 si 已对齐"），这条用例会被错误地判成一致，正好掩盖它要检出的缺口。
    """
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/si-file", title="SI File"))
    asset_id = repo.plan_asset(paper_id, _si_plan(), "mock_platform")
    tracked_path = data_dir / "si" / VENUE_ID / "2024" / paper_id / "keep.zip"
    sha = _write_pdf(tracked_path, b"tracked-si-bytes")
    repo.mark_asset(asset_id, state="fetched", file_path=str(tracked_path), bytes_=1, sha256=sha)

    stray_path = data_dir / "si" / VENUE_ID / "2024" / paper_id / "stray.pdf"
    _write_pdf(stray_path, b"untracked-extra-file-in-same-paper-directory")

    issues = verify_store(repo, data_dir)
    assert issues == [
        VerifyIssue(
            kind="orphan_file", asset_id=None, file_path=str(stray_path), suggestion="adopt"
        )
    ]


# -- _optional_text（T7/T14 合并顺序兼容的读列 helper）---------------------------
#
# T7（真实 extract 落地，含 0004 迁移）已合并 main——`Database.migrate()` 产出的库
# 现在恒含五列，`tests/helpers/fulltext_schema.py::ensure_fulltext_asset_columns`
# 对这些库退化为空操作（列已存在，PRAGMA 探测后跳过）。但 `_optional_text` 的"列
# 缺席"分支仍是有意义的防御性代码——`verify.py` 模块 docstring 承诺的"T7/T14 任一
# 合并顺序均可正确运行"不应随 T7 已落地而失去验证，故直接构造一张真不含该列的表
# 单测这一分支（同 `cli_module._pdf_layout_scope` 直调私有函数的既有先例）。


def test_optional_text_returns_none_when_column_truly_absent() -> None:
    """列在表结构中确实不存在（而非存在但为 NULL）时返回 None（不抛 KeyError）。"""
    import sqlite3

    from paper_crawler import verify as verify_module

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE t (paper_id TEXT)")
    conn.execute("INSERT INTO t (paper_id) VALUES ('p1')")
    row = conn.execute("SELECT * FROM t").fetchone()
    conn.close()

    assert verify_module._optional_text(row, "asset_id") is None


# -- fulltext（design/12 §9.2 T14 扩展）-------------------------------------------


def test_verify_store_fulltext_no_issues_when_consistent(repo: Repo, data_dir: Path) -> None:
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/ft-ok", title="FT Ok"))
    asset_id = repo.plan_asset(paper_id, _pdf_plan(), "mock_platform")
    pdf_path = data_dir / "pdf" / VENUE_ID / "2024" / f"{paper_id}.pdf"
    pdf_sha = _write_pdf(pdf_path)
    repo.mark_asset(asset_id, state="fetched", file_path=str(pdf_path), bytes_=1, sha256=pdf_sha)

    text_path = data_dir / "fulltext" / VENUE_ID / "2024" / f"{paper_id}.txt"
    text_sha = _write_pdf(text_path, b"extracted plain text")
    write_fulltext_row(
        repo,
        paper_id,
        text_path=str(text_path),
        text_sha256=text_sha,
        asset_id=asset_id,
        source_sha256=pdf_sha,
        state="extracted",
    )

    assert verify_store(repo, data_dir) == []


def test_verify_store_fulltext_text_path_relative_form_resolves_correctly(
    repo: Repo, data_dir: Path
) -> None:
    """`fulltext.text_path` 落盘为相对 `data_dir`、**不含** `data/` 前缀的形态
    （design/12 §5.4 正误对照块）——`verify.py::_resolve` 的既有相对路径展开逻辑对
    fulltext 域同样适用（与 asset 域共用同一 `_resolve`，零改造）。本用例显式锁定
    这一契约点：误加 `data/` 前缀会使全库每一行都假性报 `missing_file`（design/12
    §5.4 明文警示），本用例证明正确形态下不会。
    """
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/relpath", title="Rel Path"))
    relative_text_path = f"fulltext/{VENUE_ID}/2024/{paper_id}.txt"
    absolute_text_path = data_dir / "fulltext" / VENUE_ID / "2024" / f"{paper_id}.txt"
    text_sha = _write_pdf(absolute_text_path, b"relative-path-contract text")
    write_fulltext_row(
        repo, paper_id, text_path=relative_text_path, text_sha256=text_sha, state="extracted"
    )

    assert verify_store(repo, data_dir) == []


def test_verify_store_detects_fulltext_missing_file(repo: Repo, data_dir: Path) -> None:
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/ft-miss", title="FT Missing"))
    text_path = data_dir / "fulltext" / VENUE_ID / "2024" / f"{paper_id}.txt"
    write_fulltext_row(repo, paper_id, text_path=str(text_path), text_sha256="deadbeef")
    # 注意：从未真的写文件——磁盘上不存在

    issues = verify_store(repo, data_dir)
    assert issues == [
        VerifyIssue(
            kind="missing_file", asset_id=None, file_path=str(text_path), suggestion="re-extract"
        )
    ]


def test_verify_store_detects_fulltext_hash_mismatch(repo: Repo, data_dir: Path) -> None:
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/ft-hash", title="FT Hash"))
    text_path = data_dir / "fulltext" / VENUE_ID / "2024" / f"{paper_id}.txt"
    _write_pdf(text_path, b"actual on-disk text")
    write_fulltext_row(repo, paper_id, text_path=str(text_path), text_sha256="not-the-real-hash")

    issues = verify_store(repo, data_dir)
    assert issues == [
        VerifyIssue(
            kind="hash_mismatch", asset_id=None, file_path=str(text_path), suggestion="re-extract"
        )
    ]


def test_verify_store_detects_fulltext_orphan_file(repo: Repo, data_dir: Path) -> None:
    orphan_path = data_dir / "fulltext" / VENUE_ID / "2024" / "orphan.txt"
    _write_pdf(orphan_path, b"nobody points at me")

    issues = verify_store(repo, data_dir)
    assert issues == [
        VerifyIssue(
            kind="orphan_file", asset_id=None, file_path=str(orphan_path), suggestion="prune"
        )
    ]


def test_verify_store_ignores_legacy_fulltext_rows_without_text_path(
    repo: Repo, data_dir: Path
) -> None:
    """`state='noop'`/`'extract_failed'`（两者 `text_path IS NULL`）不参与文件对账
    （design/12 §9.2「legacy 行不参与文件对账」裁决）——两态各造一行，断言零 issue。
    """
    noop_paper = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/ft-noop", title="FT Noop"))
    write_fulltext_row(repo, noop_paper, text_path=None, state="noop")

    failed_paper = repo.upsert_paper(
        VENUE_ID, None, _stub(doi="10.9999/ft-failed", title="FT Failed")
    )
    write_fulltext_row(repo, failed_paper, text_path=None, state="extract_failed")

    assert verify_store(repo, data_dir) == []


def test_verify_store_ignores_legacy_pre_t7_schema_noop_row(repo: Repo, data_dir: Path) -> None:
    """main 存量 schema（T7 未合并，无 state/asset_id 等列）下的 noop 行同样不误报——
    `text_path IS NULL` 是唯一需要的判据，T7 增量列缺席不影响这一条。
    """
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/ft-legacy", title="FT Legacy"))
    write_legacy_fulltext_row(repo, paper_id)

    assert verify_store(repo, data_dir) == []


# -- stale_fulltext（信息级；design/12 §9.2 新增第四类）---------------------------


def test_verify_store_detects_stale_fulltext_as_info_severity(repo: Repo, data_dir: Path) -> None:
    """asset 被 re-fetch（sha256 变化）后，fulltext 行仍指向旧版 PDF 抽出的文本——
    前三类判据全绿（文件在、哈希对、路径对），只有 stale_fulltext 能检出这类静默
    错配。`severity='info'`：不是缺陷，cli.py 消费面须与前三类分开呈现、不计入退出码。
    """
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/stale", title="Stale Paper"))
    asset_id = repo.plan_asset(paper_id, _pdf_plan(), "mock_platform")
    pdf_path = data_dir / "pdf" / VENUE_ID / "2024" / f"{paper_id}.pdf"
    new_sha = _write_pdf(pdf_path, b"brand-new-re-fetched-content")
    repo.mark_asset(asset_id, state="fetched", file_path=str(pdf_path), bytes_=1, sha256=new_sha)

    text_path = data_dir / "fulltext" / VENUE_ID / "2024" / f"{paper_id}.txt"
    text_sha = _write_pdf(text_path, b"text extracted from the OLD pdf content")
    write_fulltext_row(
        repo,
        paper_id,
        text_path=str(text_path),
        text_sha256=text_sha,
        asset_id=asset_id,
        source_sha256="old-pdf-sha-before-refetch",  # != new_sha：陈旧
        state="extracted",
    )

    issues = verify_store(repo, data_dir)
    assert issues == [
        VerifyIssue(
            kind="stale_fulltext",
            asset_id=asset_id,
            file_path=str(text_path),
            suggestion="re-extract",
            severity="info",
        )
    ]
    assert [issue for issue in issues if issue.severity == "defect"] == []


def test_verify_store_no_stale_fulltext_when_source_sha256_matches_current_asset(
    repo: Repo, data_dir: Path
) -> None:
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/fresh", title="Fresh Paper"))
    asset_id = repo.plan_asset(paper_id, _pdf_plan(), "mock_platform")
    pdf_path = data_dir / "pdf" / VENUE_ID / "2024" / f"{paper_id}.pdf"
    sha = _write_pdf(pdf_path)
    repo.mark_asset(asset_id, state="fetched", file_path=str(pdf_path), bytes_=1, sha256=sha)

    text_path = data_dir / "fulltext" / VENUE_ID / "2024" / f"{paper_id}.txt"
    text_sha = _write_pdf(text_path, b"matching extraction")
    write_fulltext_row(
        repo,
        paper_id,
        text_path=str(text_path),
        text_sha256=text_sha,
        asset_id=asset_id,
        source_sha256=sha,  # 与当前 asset.sha256 一致——不陈旧
        state="extracted",
    )

    assert verify_store(repo, data_dir) == []


def test_verify_store_stale_fulltext_excludes_legacy_asset_id_null_row(
    repo: Repo, data_dir: Path
) -> None:
    """`asset_id IS NULL` 的 legacy 行不参与 stale_fulltext 判定（design/12 §9.2：
    「asset_id IS NULL 的 legacy 行不参与本类判定」）——即便凑巧填了 source_sha256。
    """
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/nullasset", title="Null Asset"))
    text_path = data_dir / "fulltext" / VENUE_ID / "2024" / f"{paper_id}.txt"
    text_sha = _write_pdf(text_path, b"orphaned-from-asset-identity text")
    write_fulltext_row(
        repo,
        paper_id,
        text_path=str(text_path),
        text_sha256=text_sha,
        asset_id=None,
        source_sha256="some-sha-that-would-otherwise-look-stale",
        state="extracted",
    )

    assert verify_store(repo, data_dir) == []


# -- T7 崩溃窗 2/3 残留回归锁（design/12 §5.5；T14 合并后一次全库 verify 收口承诺）-----


def test_verify_store_fulltext_same_suffix_overwrite_crash_window_reports_hash_mismatch(
    repo: Repo, data_dir: Path
) -> None:
    """崩溃窗 2（design/12 §5.5）同后缀覆写场景：重跑 extract 已把新内容原子 rename
    到与旧产物相同的路径/后缀，但进程在"DB upsert"之前崩溃——DB 仍是旧行（旧
    `text_sha256`），磁盘已是新内容。design 明文裁决：此形态须报 `hash_mismatch`
    （旧行仍引用该路径、盘上已是新内容），**不是** `orphan_file`。
    """
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/crash-w2a", title="Crash W2a"))
    text_path = data_dir / "fulltext" / VENUE_ID / "2024" / f"{paper_id}.txt"
    old_sha = _write_pdf(text_path, b"pre-crash extracted text (stale)")
    # DB 行记录的是崩溃前的产物哈希——模拟"DB upsert 尚未发生"。
    write_fulltext_row(
        repo, paper_id, text_path=str(text_path), text_sha256=old_sha, state="extracted"
    )
    # 崩溃后重跑的原子 rename 已完成（同路径覆写），DB 却还没来得及更新到新哈希。
    _write_pdf(text_path, b"post-crash re-extracted text (new content, same path)")

    issues = verify_store(repo, data_dir)
    assert issues == [
        VerifyIssue(
            kind="hash_mismatch", asset_id=None, file_path=str(text_path), suggestion="re-extract"
        )
    ]


def test_verify_store_fulltext_suffix_change_crash_window_reports_orphan_file(
    repo: Repo, data_dir: Path
) -> None:
    """崩溃窗 3（design/12 §5.5）换后缀场景：DB 已 upsert 到新路径（如 GROBID 升级
    产出 `.tei.xml` 取代旧 `.txt`），但进程在"删旧产物文件"之前崩溃——旧后缀文件在
    磁盘上孤存，DB 不再引用它。design 明文裁决：报 `orphan_file` + suggestion
    `prune`；重跑 extract 命中幂等键跳过、不会自愈，须由 verify 检出（不自愈本身
    如实入档，是 R5 风险的验收载体）。
    """
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/crash-w3", title="Crash W3"))
    old_path = data_dir / "fulltext" / VENUE_ID / "2024" / f"{paper_id}.txt"
    _write_pdf(old_path, b"superseded pypdf extraction")  # 旧后缀产物，DB 已不再引用

    new_path = data_dir / "fulltext" / VENUE_ID / "2024" / f"{paper_id}.tei.xml"
    new_sha = _write_pdf(new_path, b"<TEI>grobid winner</TEI>")
    write_fulltext_row(
        repo, paper_id, text_path=str(new_path), text_sha256=new_sha, state="extracted"
    )

    issues = verify_store(repo, data_dir)
    assert issues == [
        VerifyIssue(kind="orphan_file", asset_id=None, file_path=str(old_path), suggestion="prune")
    ]


# -- count_pending_extraction（design/12 §9.2 附注："未真实抽取"信息计数，非缺陷）-----


def test_count_pending_extraction_counts_noop_rows_without_text_path(repo: Repo) -> None:
    p1 = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/cpe1", title="CPE1"))
    p2 = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/cpe2", title="CPE2"))
    write_fulltext_row(repo, p1, text_path=None, state="noop")
    write_fulltext_row(repo, p2, text_path=None, state="noop")

    assert count_pending_extraction(repo) == 2


def test_count_pending_extraction_excludes_extract_failed_and_extracted_rows(
    repo: Repo, data_dir: Path
) -> None:
    noop_paper = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/cpe-noop", title="Noop"))
    write_fulltext_row(repo, noop_paper, text_path=None, state="noop")

    failed_paper = repo.upsert_paper(
        VENUE_ID, None, _stub(doi="10.9999/cpe-failed", title="Failed")
    )
    write_fulltext_row(repo, failed_paper, text_path=None, state="extract_failed")

    ok_paper = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/cpe-ok", title="Ok"))
    text_path = data_dir / "fulltext" / VENUE_ID / "2024" / f"{ok_paper}.txt"
    text_sha = _write_pdf(text_path, b"real text")
    write_fulltext_row(
        repo, ok_paper, text_path=str(text_path), text_sha256=text_sha, state="extracted"
    )

    assert count_pending_extraction(repo) == 1  # 只有 noop 那一行


def test_count_pending_extraction_treats_pre_t7_schema_rows_as_noop(repo: Repo) -> None:
    """main 存量 schema（无 `state` 列）下，`_stage_extract` 唯一产出形态就是 noop——
    列缺省时按 `"noop"` 处理（verify.py 模块 docstring「T7/T14 合并顺序兼容」一节）。
    """
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/cpe-legacy", title="Legacy"))
    write_legacy_fulltext_row(repo, paper_id)

    assert count_pending_extraction(repo) == 1


def test_count_pending_extraction_zero_when_no_fulltext_rows(repo: Repo) -> None:
    assert count_pending_extraction(repo) == 0
