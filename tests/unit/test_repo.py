"""仓储层语义测试（phase1-plan Task 2；Refs: D-007, D-017, AC-1.1）。

重点：upsert_paper 强合并（补缺不覆盖）、upsert_issue/plan_asset 的 NULL-安全幂等键、
paper_issue_link 幂等建链、外键约束、counts 对账口径、preprint_of 建边（T10；pull 路径
`upsert_paper` 消费 meta 线索——见"-- preprint_of 建边"节；MergeEngine.ingest() 路径的对应
用例在 test_merge.py）。
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import FetchLogRow, MergeInput, Repo
from paper_crawler.types import AssetKind, AssetPlan, AuthLevel, IssueRef, PaperStub, VenueSpec

# AC-0.4 红线扫描：库内不得残留 (session|token|key) 的 key=value / 引号变体形态。
_CREDENTIAL_LEAK = re.compile(
    r"(session|token|key)['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9]{6,}", re.IGNORECASE
)

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


def test_upsert_paper_merge_keeps_single_primary_identifier(repo: Repo) -> None:
    """合并路径不得产生双 is_primary：既有 paper 已有 primary，新来 stub 的首个
    （index==0）identifier 是新增的，应降为非 primary（既有 primary 保留）。"""
    # 首建：doi X 成为 primary。
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/dp", title="First"))
    # 二次：新 identifier 排在首位（index 0）、与既有 doi 重叠 → 并入同一 paper。
    p2 = repo.upsert_paper(
        VENUE_ID,
        None,
        PaperStub(
            title="Second",
            identifiers=(("arxiv", "2401.09999"), ("doi", "10.9999/dp")),
        ),
    )
    primaries = repo.db.query(
        "SELECT scheme, value FROM identifier WHERE paper_id = ? AND is_primary = 1", (p2,)
    )
    assert len(primaries) == 1  # 恰一个 primary（修复前 arxiv 会被误标 primary → 2 个）
    assert primaries[0]["scheme"] == "doi"  # 既有 primary 不被新来者篡夺
    assert len(repo.db.query("SELECT scheme FROM identifier WHERE paper_id = ?", (p2,))) == 2


def test_upsert_paper_new_paper_first_identifier_is_primary(repo: Repo) -> None:
    """回归护栏：全新 paper 的首个 identifier 仍标 primary（修复不误伤新建路径）。"""
    paper_id = repo.upsert_paper(
        VENUE_ID,
        None,
        PaperStub(title="New", identifiers=(("doi", "10.9999/np"), ("arxiv", "2402.00001"))),
    )
    primaries = repo.db.query(
        "SELECT scheme FROM identifier WHERE paper_id = ? AND is_primary = 1", (paper_id,)
    )
    assert len(primaries) == 1
    assert primaries[0]["scheme"] == "doi"


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


# -- preprint_of 建边（T10；design/06 §3 单一事实源，检查单 #5）-------------
#
# `upsert_paper`（pull 路径）是 arxiv/cvf/openreview 等真实 adapter 线索的实际必经之路
# （T10 grep 实况核实：这些 adapter 的 PaperStub 经 `_stage_enumerate` 走本方法，不走
# `MergeEngine.ingest`）——故本节直接用 `upsert_paper` 验证建边机制；`MergeEngine.ingest()`
# 路径共享同一 `Repo._apply_preprint_clues` 机制，对应用例见 test_merge.py。


def _preprint_edges(repo: Repo) -> list[sqlite3.Row]:
    return repo.db.query(
        "SELECT pf.title AS from_title, pt.title AS to_title, r.confidence, "
        "       r.evidence_json, r.decided "
        "FROM paper_relation r "
        "JOIN paper pf ON pf.id = r.from_paper "
        "JOIN paper pt ON pt.id = r.to_paper "
        "WHERE r.kind = 'preprint_of' "
        "ORDER BY pf.title, pt.title"
    )


def test_upsert_paper_doi_clue_builds_preprint_of_edge_when_target_exists(repo: Repo) -> None:
    """arxiv 先例：meta['doi'] 回填线索命中既有 identifier → 建边，自身=from（预印本）。"""
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/published", title="Published Version"))
    repo.upsert_paper(
        VENUE_ID,
        None,
        PaperStub(
            title="Preprint Version",
            identifiers=(("arxiv", "2401.00100"),),
            meta=(("doi", "10.9999/published"),),
        ),
    )
    edges = _preprint_edges(repo)
    assert len(edges) == 1
    assert edges[0]["from_title"] == "Preprint Version"
    assert edges[0]["to_title"] == "Published Version"
    assert edges[0]["confidence"] == 1.0
    assert edges[0]["decided"] is None


def test_upsert_paper_arxiv_clue_builds_reverse_direction_edge(repo: Repo) -> None:
    """cvf/openreview 先例：meta['arxiv'] 线索命中 → 自身=to（发表版），目标=from（预印本）。"""
    repo.upsert_paper(
        VENUE_ID,
        None,
        PaperStub(title="Preprint Version", identifiers=(("arxiv", "2401.00200"),)),
    )
    repo.upsert_paper(
        VENUE_ID,
        None,
        PaperStub(
            title="Conference Version",
            identifiers=(("cvf", "cvpr2024/foo"),),
            meta=(("arxiv", "2401.00200"),),
        ),
    )
    edges = _preprint_edges(repo)
    assert len(edges) == 1
    assert edges[0]["from_title"] == "Preprint Version"
    assert edges[0]["to_title"] == "Conference Version"


def test_upsert_paper_dangling_preprint_clue_skips_edge_and_logs_debug(
    repo: Repo, caplog: pytest.LogCaptureFixture
) -> None:
    """查不到目标端＝线索悬空：as-is 跳过 + DEBUG 记录，不建悬空边（controller 裁决③）。"""
    with caplog.at_level(logging.DEBUG, logger="paper_crawler"):
        repo.upsert_paper(
            VENUE_ID,
            None,
            PaperStub(
                title="Preprint Version",
                identifiers=(("arxiv", "2401.00300"),),
                meta=(("doi", "10.9999/never-lands"),),
            ),
        )
    assert _preprint_edges(repo) == []
    assert any("dangling" in r.getMessage() for r in caplog.records)


def test_upsert_paper_preprint_clue_evidence_includes_journal_ref(repo: Repo) -> None:
    """同 stub 携带 journal_ref 时作为补充证据搭车进 evidence_json（不单独驱动查找）。"""
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/withref", title="Published"))
    repo.upsert_paper(
        VENUE_ID,
        None,
        PaperStub(
            title="Preprint",
            identifiers=(("arxiv", "2401.00400"),),
            meta=(("doi", "10.9999/withref"), ("journal_ref", "Journal of Testing, 2026")),
        ),
    )
    edges = _preprint_edges(repo)
    assert len(edges) == 1
    assert "Journal of Testing, 2026" in edges[0]["evidence_json"]


def test_upsert_paper_preprint_clue_no_self_referencing_edge(repo: Repo) -> None:
    """同一 paper 已持有 doi+arxiv 两 scheme（先例：既存强合并）、meta 线索指回自身 → 自指
    防御，不建边（正常数据不会出现，保守跳过）。"""
    repo.upsert_paper(
        VENUE_ID,
        None,
        PaperStub(
            title="Merged", identifiers=(("doi", "10.9999/selfref"), ("arxiv", "2401.00500"))
        ),
    )
    repo.upsert_paper(
        VENUE_ID,
        None,
        PaperStub(
            title="Merged",
            identifiers=(("doi", "10.9999/selfref"),),
            meta=(("arxiv", "2401.00500"),),
        ),
    )
    assert _preprint_edges(repo) == []


def test_upsert_paper_without_preprint_clue_keys_is_noop(repo: Repo) -> None:
    """meta 不含 'doi'/'arxiv' 键 → 不建任何 preprint_of 边（纯烟雾测试）。"""
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/plain", meta=(("pages", "1-10"),)))
    assert _preprint_edges(repo) == []


def test_upsert_paper_preprint_clue_idempotent_reingest(repo: Repo) -> None:
    """同一线索重复观测 → 边只一行（幂等，同构于 candidate_duplicate）。"""
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/idem-pub", title="Published"))
    stub = PaperStub(
        title="Preprint",
        identifiers=(("arxiv", "2401.00600"),),
        meta=(("doi", "10.9999/idem-pub"),),
    )
    repo.upsert_paper(VENUE_ID, None, stub)
    repo.upsert_paper(VENUE_ID, None, stub)
    assert len(_preprint_edges(repo)) == 1


def test_upsert_paper_conflicting_doi_and_arxiv_clues_same_target_keeps_doi_direction(
    repo: Repo,
) -> None:
    """独立审查（原 P1-1，现由 `_upsert_preprint_relation` 的反向行守卫统一兜底）：
    同一调用内 doi(role=from) 与 arxiv(role=to) 解析到**同一** target（目标 paper 已
    聚合 doi+arxiv 两 identifier——openreview 双键场景可达）→ 双向矛盾环风险（A→B 与
    B→A 并存）。doi 线索按 `_PREPRINT_CLUE_ROLES` 声明序先处理、先落地；arxiv 线索
    随后撞见反向行、被守卫挡下——只留 doi 方向一条，不建反向边。"""
    repo.upsert_paper(
        VENUE_ID,
        None,
        PaperStub(
            title="Aggregated Target",
            identifiers=(("doi", "10.9999/conflict"), ("arxiv", "2401.00700")),
        ),
    )
    repo.upsert_paper(
        VENUE_ID,
        None,
        PaperStub(
            title="Self",
            identifiers=(("cvf", "cvpr2024/conflict"),),
            meta=(("doi", "10.9999/conflict"), ("arxiv", "2401.00700")),
        ),
    )
    edges = _preprint_edges(repo)
    assert len(edges) == 1  # 不是两条（无反向环）
    assert edges[0]["from_title"] == "Self"
    assert edges[0]["to_title"] == "Aggregated Target"
    assert json.loads(edges[0]["evidence_json"])["clue_key"] == "doi"


def test_upsert_paper_cross_observation_reverse_edge_guard_prevents_bidirectional_loop(
    repo: Repo, caplog: pytest.LogCaptureFixture
) -> None:
    """独立审查 re-review REOPEN #6（P1）：跨观测四步时序仍会成环，同调用内预判堵不住。

    ①target 最初只有 arxiv identifier；②self 首次观测（仅 arxiv 线索）建
    `target→self`；③target 经普通强合并（与 preprint_of 无关）聚合进 doi；④self 再次
    观测、这次 doi/arxiv 两条线索都能解析到同一 target——若无反向行守卫会再建
    `self→target`，与步骤②遗留的旧边 `target→self`（"绝不删行"）构成矛盾对并存。
    断言：全程只有步骤②那一条边，方向不变，第④步的写入尝试被 DEBUG 记录后跳过。
    """
    # ① target 最初只有 arxiv。
    repo.upsert_paper(
        VENUE_ID, None, PaperStub(title="Target", identifiers=(("arxiv", "2401.07000"),))
    )
    # ② self 首次观测：仅 arxiv 线索 → 建 target→self。
    repo.upsert_paper(
        VENUE_ID,
        None,
        PaperStub(
            title="Self",
            identifiers=(("cvf", "cvpr2024/xobs"),),
            meta=(("arxiv", "2401.07000"),),
        ),
    )
    edges_after_step2 = _preprint_edges(repo)
    assert len(edges_after_step2) == 1
    assert edges_after_step2[0]["from_title"] == "Target"
    assert edges_after_step2[0]["to_title"] == "Self"

    # ③ target 经普通强合并聚合进 doi（与 preprint_of 无关，纯 identifier 补全）。
    repo.upsert_paper(
        VENUE_ID,
        None,
        PaperStub(
            title="Target",
            identifiers=(("arxiv", "2401.07000"), ("doi", "10.9999/target-doi")),
        ),
    )

    # ④ self 再次观测：doi + arxiv 双线索都解析到同一 target。
    with caplog.at_level(logging.DEBUG, logger="paper_crawler"):
        repo.upsert_paper(
            VENUE_ID,
            None,
            PaperStub(
                title="Self",
                identifiers=(("cvf", "cvpr2024/xobs"),),
                meta=(("doi", "10.9999/target-doi"), ("arxiv", "2401.07000")),
            ),
        )

    edges_final = _preprint_edges(repo)
    assert len(edges_final) == 1  # 仍只一条，不是两条方向相反的边
    assert edges_final[0]["from_title"] == "Target"
    assert edges_final[0]["to_title"] == "Self"  # 方向未被第④步的 doi 线索翻转
    assert any("reverse edge already exists" in r.getMessage() for r in caplog.records)


def test_upsert_paper_preprint_clue_evidence_includes_venue_id(repo: Repo) -> None:
    """独立审查 P1-2：evidence_json 记 venue_id（`upsert_paper` pull 路径持有）——
    controller 裁决③（openreview doi 语义存疑靠 evidence 溯源核实）的前提。"""
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/withvenue", title="Published"))
    repo.upsert_paper(
        VENUE_ID,
        None,
        PaperStub(
            title="Preprint",
            identifiers=(("arxiv", "2401.00800"),),
            meta=(("doi", "10.9999/withvenue"),),
        ),
    )
    evidence = json.loads(_preprint_edges(repo)[0]["evidence_json"])
    assert evidence["venue_id"] == VENUE_ID
    assert "source" not in evidence  # pull 路径无 source 概念（upsert_paper 签名无此参数）


@pytest.mark.parametrize(
    "raw_arxiv_value",
    [
        "2401.00900v2",  # 新代带版本
        "https://arxiv.org/abs/2401.00900",  # URL 形（新代无版本）
        "http://www.arxiv.org/abs/2401.00900v3",  # URL 形 + 版本 + www
    ],
)
def test_upsert_paper_arxiv_clue_normalizes_versioned_and_url_forms(
    repo: Repo, raw_arxiv_value: str
) -> None:
    """独立审查 P1-3：'arxiv' 线索值须与 identifier(scheme='arxiv') 同一归一链（去版本号
    +去 URL 前缀），否则带版本/URL 形线索静默悬空（实测 #8/#9）。"""
    repo.upsert_paper(
        VENUE_ID, None, PaperStub(title="Preprint", identifiers=(("arxiv", "2401.00900"),))
    )
    repo.upsert_paper(
        VENUE_ID,
        None,
        PaperStub(
            title="Conference Version",
            identifiers=(("cvf", "cvpr2024/normalize"),),
            meta=(("arxiv", raw_arxiv_value),),
        ),
    )
    edges = _preprint_edges(repo)
    assert len(edges) == 1
    assert edges[0]["from_title"] == "Preprint"
    assert edges[0]["to_title"] == "Conference Version"


def test_upsert_paper_arxiv_clue_old_style_with_version_normalizes(repo: Repo) -> None:
    """旧代 id 带版本号+大小写异形（`HEP-TH/9901001v1`）→ 去版本号+小写归一后与库内裸旧代
    id（`hep-th/9901001`）匹配（design/adapters/arxiv.md §3：旧代小写归一、保留斜杠）。"""
    repo.upsert_paper(
        VENUE_ID, None, PaperStub(title="Preprint", identifiers=(("arxiv", "hep-th/9901001"),))
    )
    repo.upsert_paper(
        VENUE_ID,
        None,
        PaperStub(
            title="Conference Version",
            identifiers=(("cvf", "cvpr2024/oldstyle"),),
            meta=(("arxiv", "HEP-TH/9901001v1"),),
        ),
    )
    assert len(_preprint_edges(repo)) == 1


def test_upsert_paper_arxiv_clue_unparseable_value_skipped_no_edge(
    repo: Repo, caplog: pytest.LogCaptureFixture
) -> None:
    """既非新代也非旧代形态（非 URL、非法结构）→ 视为无法解析，DEBUG 记录后跳过，不建边、
    不抛异常炸 ingest 事务（线索值是自由文本，非 adapter 内部受控解析——`arxiv.ids.normalize`
    对非法输入本会 raise，消费侧须降级捕获，不能让单条脏线索拖垮整批 ingest）。"""
    with caplog.at_level(logging.DEBUG, logger="paper_crawler"):
        repo.upsert_paper(
            VENUE_ID,
            None,
            PaperStub(
                title="Conference Version",
                identifiers=(("cvf", "cvpr2024/garbage"),),
                meta=(("arxiv", "not-an-arxiv-id-at-all"),),
            ),
        )
    assert _preprint_edges(repo) == []
    assert any("unparseable" in r.getMessage() for r in caplog.records)


def test_upsert_paper_decided_preprint_edge_not_rewritten_via_pull_path(repo: Repo) -> None:
    """独立审查 P2-3：`decided` 保护规则须在 `upsert_paper` pull 路径也覆盖到（此前只在
    test_merge.py 经 `MergeEngine.ingest` 验证过，两条写路径共享同一 `_upsert_preprint_relation`
    机制，但缺 pull 路径直测）。"""
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/decided-pub", title="Published"))
    repo.upsert_paper(
        VENUE_ID,
        None,
        PaperStub(
            title="Preprint",
            identifiers=(("arxiv", "2401.01000"),),
            meta=(("doi", "10.9999/decided-pub"), ("journal_ref", "v1")),
        ),
    )
    repo.db.execute("UPDATE paper_relation SET decided = 'rejected' WHERE kind = 'preprint_of'")
    before = _preprint_edges(repo)[0]["evidence_json"]

    repo.upsert_paper(
        VENUE_ID,
        None,
        PaperStub(
            title="Preprint",
            identifiers=(("arxiv", "2401.01000"),),
            meta=(("doi", "10.9999/decided-pub"), ("journal_ref", "v2")),
        ),
    )
    edges = _preprint_edges(repo)
    assert len(edges) == 1
    assert edges[0]["decided"] == "rejected"
    assert edges[0]["evidence_json"] == before


# -- preprint_of 关联报告查询（T16；AC-7.4 后半，design/06 §3）--------------
#
# `list_preprint_relations` 是只读 join 视图，供 `preprint_report.build_preprint_report`
# 消费；本节只验证查询本身（双端 title/year/venue join、venue 可空、排序、decided 原样
# 透出）——边的建立逻辑已由上一节（T10）与 test_merge.py 覆盖，不重复造边场景。


def _second_venue(venue_id: str = "arxiv_mock", full_name: str = "ArXiv Mock") -> VenueSpec:
    """第二个最小合法 venue（不同于 fixture 自带的 `VENUE_ID`），供跨 venue join 断言。"""
    return VenueSpec(
        id=venue_id,
        kind="preprint_channel",
        names={"full": full_name, "aliases": []},
        field=["cs_ai"],
        identifiers={},
        metadata_source="mock_platform",
        fulltext_source="mock_platform",
    )


def _merge_input(
    *,
    title: str,
    year: int | None = None,
    meta: tuple[tuple[str, str], ...] = (),
    source: str = "crossref",
) -> MergeInput:
    """`Repo.merge_ingest` 直调入参（绕开 `MergeEngine`——本文件只测 `Repo` 层）。

    `priority` 是调用方自定义的最小映射，不借用生产 `SOURCE_PRIORITY`（`merge_ingest`
    对 `source`/`priority` 无枚举校验，那是 `MergeEngine.ingest` 的职责，见 merge.py）。
    仅用于构造 venue_id=NULL 的 aggregator 路径 paper（`_create_paper` "venue-agnostic"
    先例），验证 `list_preprint_relations` 的 LEFT JOIN venue 在两端皆缺 venue 时不报错。
    """
    return MergeInput(
        title=title,
        title_norm=title.lower(),
        first_author=None,
        abstract=None,
        year=year,
        pub_date=None,
        meta=meta,
        source=source,
        priority={"crossref": 1, "official": 2},
    )


def test_list_preprint_relations_empty_is_empty_list(repo: Repo) -> None:
    assert repo.list_preprint_relations() == []


def test_list_preprint_relations_joins_titles_years_and_venue_names(repo: Repo) -> None:
    """两端均经 pull 路径（各自绑定 venue）→ join 出双端 title/year/venue 名。"""
    repo.upsert_venue(_second_venue())
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/pub-a", title="Published A", year=2025))
    repo.upsert_paper(
        "arxiv_mock",
        None,
        PaperStub(
            title="Preprint A",
            identifiers=(("arxiv", "2401.01111"),),
            year=2024,
            meta=(("doi", "10.9999/pub-a"),),
        ),
    )
    rows = repo.list_preprint_relations()
    assert len(rows) == 1
    row = rows[0]
    assert row["preprint_title"] == "Preprint A"
    assert row["preprint_venue"] == "ArXiv Mock"
    assert row["preprint_year"] == 2024
    assert row["published_title"] == "Published A"
    assert row["published_venue"] == "Mock Journal"
    assert row["published_year"] == 2025
    assert row["confidence"] == 1.0
    assert row["decided"] is None
    assert "doi" in row["evidence_json"]


def test_list_preprint_relations_null_venue_for_aggregator_created_papers(repo: Repo) -> None:
    """两端均经 aggregator 路径（`merge_ingest`，venue_id=NULL）→ 两侧 venue 名均为 None。"""
    repo.merge_ingest(
        _merge_input(title="Published Agg", year=2025, source="crossref"),
        identifiers=(("doi", "10.5/agg"),),
    )
    repo.merge_ingest(
        _merge_input(title="Preprint Agg", meta=(("doi", "10.5/agg"),), source="official"),
        identifiers=(("arxiv", "2401.09999"),),
    )
    rows = repo.list_preprint_relations()
    assert len(rows) == 1
    assert rows[0]["preprint_venue"] is None
    assert rows[0]["published_venue"] is None
    assert rows[0]["preprint_title"] == "Preprint Agg"
    assert rows[0]["published_title"] == "Published Agg"


def test_list_preprint_relations_orders_named_venues_before_null_then_by_year_and_title(
    repo: Repo,
) -> None:
    """排序：published venue 非空者优先（NULL venue 分组殿后）；同组内按 year 升序，
    同 year 再按 published 标题排序（逐一实测三条同组边的相对顺序，而非仅两组之间）。
    """
    repo.upsert_venue(_second_venue())

    def _named_edge(*, doi: str, title: str, year: int, arxiv_id: str) -> None:
        repo.upsert_paper(VENUE_ID, None, _stub(doi=doi, title=title, year=year))
        repo.upsert_paper(
            "arxiv_mock",
            None,
            PaperStub(
                title=f"Preprint of {title}",
                identifiers=(("arxiv", arxiv_id),),
                meta=(("doi", doi),),
            ),
        )

    # 同组（published venue = Mock Journal）三条边：故意乱序建边，验证输出顺序与建边
    # 顺序无关，只由 (year, published 标题) 决定——2019 排最前；2020 的两条按标题排序。
    _named_edge(doi="10.9999/z-2020", title="Z Named Pub", year=2020, arxiv_id="2401.02222")
    _named_edge(doi="10.9999/early-2019", title="B Earlier Pub", year=2019, arxiv_id="2401.02223")
    _named_edge(doi="10.9999/a-2020", title="A Same Year Pub", year=2020, arxiv_id="2401.02224")

    repo.merge_ingest(
        _merge_input(title="Agg Published", source="crossref"),
        identifiers=(("doi", "10.5/agg2"),),
    )
    repo.merge_ingest(
        _merge_input(title="Agg Preprint", meta=(("doi", "10.5/agg2"),), source="official"),
        identifiers=(("arxiv", "2401.03333"),),
    )

    rows = repo.list_preprint_relations()
    assert len(rows) == 4
    assert [r["published_title"] for r in rows[:3]] == [
        "B Earlier Pub",  # year 2019：全组最早
        "A Same Year Pub",  # year 2020，标题字典序早于下一条
        "Z Named Pub",  # year 2020，标题字典序较晚
    ]
    assert rows[3]["published_venue"] is None  # NULL venue 分组殿后


def test_list_preprint_relations_includes_non_pending_decided_state(repo: Repo) -> None:
    """`decided` 非空（已人工裁决，如 rejected）的边仍原样返回——报告不静默隐藏（响亮呈现）。"""
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/rej-pub", title="Rejected Pub"))
    repo.upsert_paper(
        VENUE_ID,
        None,
        PaperStub(
            title="Rejected Preprint",
            identifiers=(("arxiv", "2401.04444"),),
            meta=(("doi", "10.9999/rej-pub"),),
        ),
    )
    repo.db.execute("UPDATE paper_relation SET decided = 'rejected' WHERE kind = 'preprint_of'")
    rows = repo.list_preprint_relations()
    assert len(rows) == 1
    assert rows[0]["decided"] == "rejected"


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


def test_list_papers_duplicate_titles_id_tiebreaker(repo: Repo) -> None:
    """并列标题的序由唯一 id 收尾（F1 审查 MEDIUM）。

    --limit 前置圈选把 list_papers 的序抬成 load-bearing 确定性保证——标题
    并列时不可依赖 SQLite 实现定义序，ORDER BY (title, id) 由主键背书。
    """
    ids = [
        repo.upsert_paper(VENUE_ID, None, _stub(doi=f"10.9999/dup{i}", title="Same Title"))
        for i in range(3)
    ]
    listed = [r["id"] for r in repo.list_papers(VENUE_ID) if r["title"] == "Same Title"]
    assert listed == sorted(ids), "并列标题必须按 id 升序稳定"


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


def test_add_fetch_log_redacts_token_style_url(repo: Repo) -> None:
    """AC-0.4 扩展到 fetch_log 表：含 token 样式的 URL 落库前必须经 redact。"""
    repo.add_fetch_log(
        asset_id=None,
        task_id="t1",
        domain="mock.local",
        url="https://mock.local/pdf/x?api_key=deadbeef123456&session_id=abcdef987654",
        http_status=200,
        bytes_=2048,
        elapsed_ms=12,
        rate_wait_ms=5,
    )
    stored = str(repo.fetch_logs()[0]["url"])
    assert stored == "https://mock.local/pdf/x?api_key=***&session_id=***"
    assert "deadbeef123456" not in stored and "abcdef987654" not in stored
    assert _CREDENTIAL_LEAK.search(stored) is None


@pytest.mark.parametrize(
    ("raw_url", "expected"),
    [
        # query-style（URL 最常见形态）。
        ("https://mock.local/x?token=abc123456", "https://mock.local/x?token=***"),
        # 引号变体（签名 URL 把凭证塞进 JSON 参数：`"token": "..."`）。
        (
            'https://mock.local/x?meta={"token": "abc123456"}',
            'https://mock.local/x?meta={"token": "***"}',
        ),
        # header/冒号 + 单引号变体（`\'Authorization\': \'Bearer ...\'`）。
        (
            "https://mock.local/x#{'Authorization': 'Bearer abc123456'}",
            "https://mock.local/x#{'Authorization': '***'}",
        ),
    ],
)
def test_add_fetch_log_redacts_quoted_url_forms(repo: Repo, raw_url: str, expected: str) -> None:
    """fetch_log.url 走的是与 obslog 同一套 redact，引号/嵌套形态一并覆盖（AC-0.4）。"""
    repo.add_fetch_log(
        asset_id=None,
        task_id="t",
        domain="mock.local",
        url=raw_url,
        http_status=None,
        bytes_=0,
        elapsed_ms=0,
        rate_wait_ms=0,
    )
    stored = str(repo.fetch_logs()[0]["url"])
    assert stored == expected
    assert _CREDENTIAL_LEAK.search(stored) is None


# -- finalize_fetch（Phase 2 T1 组合事务：mark fetched + fetch_log 单事务）-----


def _success_log_row(*, url: str = "https://mock.local/pdf/x", bytes_: int = 2048) -> FetchLogRow:
    return FetchLogRow(
        task_id="t1",
        domain="mock.local",
        url=url,
        http_status=None,
        bytes_=bytes_,
        elapsed_ms=7,
        rate_wait_ms=0,
        error_class=None,
    )


def test_finalize_fetch_marks_asset_and_writes_single_log(repo: Repo) -> None:
    """成功路径：单事务内 asset→fetched（补 file/bytes/sha/fetched_at）+ 恰一条成功 fetch_log。"""
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/fin"))
    asset_id = repo.plan_asset(paper_id, _pdf_plan(), "mock_platform")

    repo.finalize_fetch(
        asset_id,
        file_path="/data/x.pdf",
        bytes_=2048,
        sha256="deadbeef",
        fetch_log_row=_success_log_row(),
    )

    asset = repo.get_asset(asset_id)
    assert asset is not None
    assert asset["state"] == "fetched"
    assert asset["file_path"] == "/data/x.pdf"
    assert asset["bytes"] == 2048
    assert asset["sha256"] == "deadbeef"
    assert asset["fetched_at"] is not None
    logs = repo.fetch_logs()
    assert len(logs) == 1
    assert logs[0]["asset_id"] == asset_id
    assert logs[0]["error_class"] is None
    assert logs[0]["bytes"] == 2048


def test_finalize_fetch_redacts_fetch_log_url(repo: Repo) -> None:
    """finalize_fetch 的 url 参数与 add_fetch_log 同源脱敏（AC-0.4 fetch_log 红线）。"""
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/finr"))
    asset_id = repo.plan_asset(paper_id, _pdf_plan(), "mock_platform")

    repo.finalize_fetch(
        asset_id,
        file_path="/data/x.pdf",
        bytes_=1,
        sha256="h",
        fetch_log_row=_success_log_row(url="https://mock.local/pdf/x?token=qwerty123456", bytes_=1),
    )

    stored = str(repo.fetch_logs()[0]["url"])
    assert stored == "https://mock.local/pdf/x?token=***"
    assert "qwerty123456" not in stored
    assert _CREDENTIAL_LEAK.search(stored) is None


def test_finalize_fetch_rolls_back_on_midtransaction_failure(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    """注入中途异常（UPDATE 已执行、INSERT 生成 id 时抛错）→ 整事务回滚：
    asset 停在 planned、无 fetch_log 行。这正是消除三步缝隙后 finalize 的原子性保证。"""
    paper_id = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/atom"))
    asset_id = repo.plan_asset(paper_id, _pdf_plan(), "mock_platform")

    def _boom() -> str:
        raise RuntimeError("injected mid-transaction failure")

    monkeypatch.setattr("paper_crawler.storage.repo.new_ulid", _boom)
    with pytest.raises(RuntimeError):
        repo.finalize_fetch(
            asset_id,
            file_path="/data/x.pdf",
            bytes_=2048,
            sha256="deadbeef",
            fetch_log_row=_success_log_row(),
        )

    asset = repo.get_asset(asset_id)
    assert asset is not None
    assert asset["state"] == "planned"  # UPDATE 与 INSERT 同回滚
    assert asset["file_path"] is None
    assert asset["sha256"] is None
    assert asset["fetched_at"] is None
    assert repo.fetch_logs() == []


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


# -- search_papers（FTS5，Phase 7 T12，D-034 决策 6）--------------------------


def test_search_papers_matches_title(repo: Repo) -> None:
    repo.upsert_paper(
        VENUE_ID, None, _stub(doi="10.9999/s1", title="Deep Learning for Asset Pricing")
    )
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/s2", title="Unrelated Topic"))

    rows = repo.search_papers("pricing")

    assert [r["title"] for r in rows] == ["Deep Learning for Asset Pricing"]


def test_search_papers_matches_abstract(repo: Repo) -> None:
    repo.upsert_paper(
        VENUE_ID,
        None,
        _stub(doi="10.9999/s1", title="Paper One", abstract="We study neural networks."),
    )
    repo.upsert_paper(
        VENUE_ID, None, _stub(doi="10.9999/s2", title="Paper Two", abstract="Unrelated content.")
    )

    rows = repo.search_papers("neural")

    assert [r["title"] for r in rows] == ["Paper One"]


def test_search_papers_no_match_returns_empty(repo: Repo) -> None:
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/s1", title="Some Paper"))

    assert repo.search_papers("nonexistentterm") == []


def test_search_papers_returns_paper_id_and_fields(repo: Repo) -> None:
    pid = repo.upsert_paper(
        VENUE_ID,
        None,
        _stub(doi="10.9999/s1", title="Asset Pricing Survey", year=2021, abstract="survey text"),
    )

    rows = repo.search_papers("survey")

    assert len(rows) == 1
    assert rows[0]["paper_id"] == pid
    assert rows[0]["title"] == "Asset Pricing Survey"
    assert rows[0]["abstract"] == "survey text"
    assert rows[0]["year"] == 2021
    assert rows[0]["venue_id"] == VENUE_ID


def test_search_papers_respects_limit(repo: Repo) -> None:
    for i in range(5):
        repo.upsert_paper(VENUE_ID, None, _stub(doi=f"10.9999/s{i}", title=f"Pricing Paper {i}"))

    rows = repo.search_papers("pricing", limit=2)

    assert len(rows) == 2


def test_search_papers_filters_by_venue_id(repo: Repo, venue_dict: dict[str, object]) -> None:
    other_id = "mock_journal_b"
    other = VenueSpec(**{**venue_dict, "id": other_id})
    repo.upsert_venue(other)
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/a1", title="Pricing in Venue A"))
    repo.upsert_paper(other_id, None, _stub(doi="10.9999/b1", title="Pricing in Venue B"))

    rows = repo.search_papers("pricing", venue_id=VENUE_ID)

    assert [r["title"] for r in rows] == ["Pricing in Venue A"]


def test_search_papers_reflects_title_update_via_trigger(repo: Repo) -> None:
    """检索经触发器同步的索引读，非静态回填快照——改标题后立刻能用新词查到。"""
    pid = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/s1", title="Original Title"))
    repo.db.execute("UPDATE paper SET title = ? WHERE id = ?", ("Renamed Title", pid))

    assert [r["paper_id"] for r in repo.search_papers("renamed")] == [pid]
    assert repo.search_papers("original") == []


# -- check_fts_consistency / reindex_fts（`crawler reindex [--check]`，D-034 决策 5）--


def test_check_fts_consistency_ok_when_in_sync(repo: Repo) -> None:
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/s1", title="Paper One"))
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/s2", title="Paper Two"))

    report = repo.check_fts_consistency()

    assert report.ok is True
    assert report.paper_count == 2
    assert report.fts_count == 2
    assert report.missing_ids == ()
    assert report.orphan_ids == ()
    assert report.duplicate_ids == ()
    assert report.integrity_check_ok is True


def test_check_fts_consistency_empty_library_is_ok(repo: Repo) -> None:
    report = repo.check_fts_consistency()
    assert report.ok is True
    assert report.paper_count == 0
    assert report.fts_count == 0


def test_check_fts_consistency_detects_missing_index(repo: Repo) -> None:
    """`paper` 有行、`paper_fts` 无对应行（漏索引）——直接删 paper_fts 侧模拟漂移。"""
    pid = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/s1", title="Paper One"))
    repo.db.execute("DELETE FROM paper_fts WHERE paper_id = ?", (pid,))

    report = repo.check_fts_consistency()

    assert report.ok is False
    assert report.missing_ids == (pid,)
    assert report.orphan_ids == ()


def test_check_fts_consistency_detects_orphan_row(repo: Repo) -> None:
    """`paper_fts` 有行、`paper` 无对应行（孤儿行）——直接插入不对应真实 paper 的行。"""
    repo.db.execute(
        "INSERT INTO paper_fts(rowid, paper_id, title, abstract) VALUES (999, 'ghost', 'x', '')"
    )

    report = repo.check_fts_consistency()

    assert report.ok is False
    assert report.orphan_ids == ("ghost",)
    assert report.missing_ids == ()


def test_check_fts_consistency_detects_duplicate_paper_id(repo: Repo) -> None:
    """同一 `paper_id` 在 `paper_fts` 内出现两行——正常写路径不产生，人工制造以验证检出。"""
    pid = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/s1", title="Paper One"))
    repo.db.execute(
        "INSERT INTO paper_fts(rowid, paper_id, title, abstract) VALUES (12345, ?, 'dup', '')",
        (pid,),
    )

    report = repo.check_fts_consistency()

    assert report.ok is False
    assert report.duplicate_ids == (pid,)


def test_check_fts_consistency_sample_limit_truncates(repo: Repo) -> None:
    for i in range(3):
        pid = repo.upsert_paper(VENUE_ID, None, _stub(doi=f"10.9999/s{i}", title=f"Paper {i}"))
        repo.db.execute("DELETE FROM paper_fts WHERE paper_id = ?", (pid,))

    report = repo.check_fts_consistency(sample_limit=2)

    assert len(report.missing_ids) == 2  # 样本截断，非全量


def test_check_fts_consistency_detects_failed_integrity_check(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FTS5 `integrity-check` 本身失败（倒排索引与其自持 content 不自洽，如磁盘级
    损坏）——真实损坏难以在测试环境人为构造，经 monkeypatch 拦截该特定命令模拟失败，
    验证 `check_fts_consistency` 正确捕获并回报 `integrity_check_ok=False`（同
    D-034 决策 4 对"FTS5 缺失模块"的验证手法：目标环境无法直接复现，改为定点模拟）。
    """
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/s1", title="Paper One"))

    real_execute = Database.execute

    def _fake_execute(self: Database, sql: str, params: tuple[object, ...] = ()) -> None:
        if "integrity-check" in sql:
            raise sqlite3.DatabaseError("database disk image is malformed")
        real_execute(self, sql, params)

    monkeypatch.setattr(Database, "execute", _fake_execute)

    report = repo.check_fts_consistency()

    assert report.integrity_check_ok is False
    assert "malformed" in (report.integrity_check_error or "")
    assert report.ok is False


def test_reindex_fts_rebuilds_from_paper_table(repo: Repo) -> None:
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/s1", title="Paper One"))
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/s2", title="Paper Two"))
    # 人为破坏索引（孤儿行 + 漏索引），验证 reindex 能从 paper 表如实重建。
    repo.db.execute(
        "INSERT INTO paper_fts(rowid, paper_id, title, abstract) VALUES (999, 'ghost', 'x', '')"
    )

    count = repo.reindex_fts()

    assert count == 2
    assert repo.check_fts_consistency().ok is True


def test_reindex_fts_is_idempotent(repo: Repo) -> None:
    repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/s1", title="Paper One"))

    assert repo.reindex_fts() == 1
    assert repo.reindex_fts() == 1  # 二次调用同样结果，无报错


def test_reindex_fts_recovers_after_rowid_collision(repo: Repo) -> None:
    """完整叙事：模拟 rowid 漂移（ghost 行占位）→ 正常写路径撞车、响亮失败（须先跑
    `reindex`）→ `reindex_fts()` 清空重建 → 原先失败的写路径重试后成功。
    """
    # paper 表当前为空，故新 paper 的首行会被 SQLite 自动分配 rowid=1——预先在
    # paper_fts 里放一个占用 rowid=1 的 ghost 行，模拟"VACUUM 重编号后遗留漂移"。
    repo.db.execute(
        "INSERT INTO paper_fts(rowid, paper_id, title, abstract) VALUES (1, 'ghost', 'x', '')"
    )

    with pytest.raises(CrawlerError) as exc_info:
        repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/s1", title="Real Paper"))
    assert exc_info.value.error_class == ErrorClass.CONFIG
    assert "reindex" in str(exc_info.value)
    # 写入连同触发器整体回滚——paper 侧也没有半成品行。
    assert repo.db.query("SELECT 1 AS x FROM paper") == []

    count = repo.reindex_fts()
    assert count == 0  # paper 为空，重建后 paper_fts 也应清空（ghost 行被清除）

    # 恢复后，原先失败的写路径重试即成功。
    pid = repo.upsert_paper(VENUE_ID, None, _stub(doi="10.9999/s1", title="Real Paper"))
    assert repo.check_fts_consistency().ok is True
    assert [r["paper_id"] for r in repo.search_papers("real")] == [pid]
