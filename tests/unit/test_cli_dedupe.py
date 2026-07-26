"""`crawler dedupe review|decide|revert|groups` CLI 单测（T13；AC-7.3）。

薄接线层测试：语义已在 `tests/unit/test_dedupe.py` 覆盖，本文件只测参数解析/呈现/
退出码（同 `test_cli_cooldown.py` 的 CliRunner 进程内驱动手法，零网络/零 registry）。

**离线非交互**（本项目 CLI 文化，同 `auth`/`cooldown` 子命令组）：`review` 只列，
裁决走显式 `decide`——不做 TUI 交互提示，脚本化/可复现。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from paper_crawler.cli import app
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.types import AssetKind, AssetPlan, AuthLevel, PaperStub, VenueSpec

runner = CliRunner()

VENUE_ID = "mock_journal"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """cwd/env 绝缘（同 `test_cli_cooldown.py` 先例）——绝不触真实 config-home（D-032 红线）。"""
    monkeypatch.delenv("PAPER_CRAWLER_HOME", raising=False)
    workdir = tmp_path / "cwd"
    workdir.mkdir()
    monkeypatch.chdir(workdir)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


@pytest.fixture
def repo(home: Path, venue: VenueSpec) -> Iterator[Repo]:
    """在 CLI 将要打开的同一个库上预置数据（CLI 自身负责建库/迁移，此处先手一步）。"""
    database = Database(home / "catalog.sqlite")
    database.migrate()
    r = Repo(database)
    r.upsert_venue(venue)
    yield r
    database.close()


def all_output(result: object) -> str:
    output = str(getattr(result, "output", ""))
    try:
        stderr = str(getattr(result, "stderr", ""))
    except ValueError:
        stderr = ""
    return output + stderr


def _pair(repo: Repo, *, confidence: float = 0.5) -> tuple[str, str]:
    """建两篇疑似重复的 paper + 一条待审 candidate_duplicate。"""
    a = repo.upsert_paper(
        VENUE_ID,
        None,
        PaperStub(
            title="Deep Learning for Finance", identifiers=(("doi", "10.9999/a"),), year=2023
        ),
    )
    b = repo.upsert_paper(
        VENUE_ID,
        None,
        PaperStub(
            title="Deep learning for finance", identifiers=(("doi", "10.9999/b"),), year=2024
        ),
    )
    repo.plan_asset(a, AssetPlan(kind=AssetKind.PDF, url="u", auth_needed=AuthLevel.NONE), "mock")
    repo.db.execute(
        "INSERT INTO paper_relation "
        "(from_paper, to_paper, kind, confidence, evidence_json, decided) VALUES (?,?,?,?,?,?)",
        (
            a,
            b,
            "candidate_duplicate",
            confidence,
            json.dumps({"reason": "weak-signal-title-author", "keys": [["deep learning", "x"]]}),
            None,
        ),
    )
    return a, b


# -- review ------------------------------------------------------------------


def test_review_lists_pending_pair_with_evidence_and_actionable_hint(
    repo: Repo, home: Path
) -> None:
    a, b = _pair(repo)

    result = runner.invoke(app, ["dedupe", "review", "--home", str(home)])

    out = all_output(result)
    assert result.exit_code == 0, out
    assert "Deep Learning for Finance" in out and "Deep learning for finance" in out
    assert a in out and b in out
    assert "weak-signal-title-author" in out
    assert "doi:10.9999/a" in out
    assert "0.5" in out  # 证据强度（confidence）
    assert "crawler dedupe decide" in out  # 可直接复制的裁决命令


def test_review_empty_library_exits_0_with_notice(home: Path) -> None:
    result = runner.invoke(app, ["dedupe", "review", "--home", str(home)])

    assert result.exit_code == 0, all_output(result)
    assert "无匹配的去重候选" in all_output(result)


def test_review_state_filter_shows_history_after_reject(repo: Repo, home: Path) -> None:
    a, b = _pair(repo)
    repo.decide_candidate(a, b, "reject")

    pending = runner.invoke(app, ["dedupe", "review", "--home", str(home)])
    rejected = runner.invoke(app, ["dedupe", "review", "--state", "rejected", "--home", str(home)])

    assert "无匹配的去重候选" in all_output(pending)
    assert rejected.exit_code == 0, all_output(rejected)
    assert a in all_output(rejected)


def test_review_limit_truncates_and_says_so(repo: Repo, home: Path) -> None:
    _pair(repo)
    c = repo.upsert_paper(
        VENUE_ID, None, PaperStub(title="Third", identifiers=(("doi", "10.9999/c"),))
    )
    d = repo.upsert_paper(
        VENUE_ID, None, PaperStub(title="Fourth", identifiers=(("doi", "10.9999/d"),))
    )
    repo.db.execute(
        "INSERT INTO paper_relation "
        "(from_paper, to_paper, kind, confidence, evidence_json, decided) VALUES (?,?,?,?,?,?)",
        (c, d, "candidate_duplicate", 0.4, "{}", None),
    )

    result = runner.invoke(app, ["dedupe", "review", "--limit", "1", "--home", str(home)])

    out = all_output(result)
    assert result.exit_code == 0, out
    assert "--limit" in out  # 截断提示，避免误以为只剩 1 条待审


def test_review_unknown_state_exits_2(home: Path) -> None:
    result = runner.invoke(app, ["dedupe", "review", "--state", "bogus", "--home", str(home)])

    assert result.exit_code == 2
    assert "错误" in all_output(result)


# -- decide / revert ---------------------------------------------------------


def test_decide_merge_lands_same_as_and_exits_0(repo: Repo, home: Path) -> None:
    a, b = _pair(repo)

    result = runner.invoke(app, ["dedupe", "decide", a, b, "merge", "--home", str(home)])

    assert result.exit_code == 0, all_output(result)
    rows = repo.db.query("SELECT * FROM paper_relation WHERE kind = 'same_as'")
    assert len(rows) == 1 and rows[0]["decided"] == "merged"
    assert repo.db.query("SELECT COUNT(*) AS n FROM paper")[0]["n"] == 2  # 物理不删行


def test_decide_merge_twice_reports_no_change(repo: Repo, home: Path) -> None:
    """幂等重放：第二次同一裁决不改库，明说"无改动"（而不是假装又做了一次）。"""
    a, b = _pair(repo)
    runner.invoke(app, ["dedupe", "decide", a, b, "merge", "--home", str(home)])

    again = runner.invoke(app, ["dedupe", "decide", a, b, "merge", "--home", str(home)])

    assert again.exit_code == 0, all_output(again)
    assert "无改动" in all_output(again)
    assert len(repo.db.query("SELECT * FROM paper_relation WHERE kind = 'same_as'")) == 1


def test_decide_reject_exits_0_and_leaves_no_same_as(repo: Repo, home: Path) -> None:
    a, b = _pair(repo)

    result = runner.invoke(app, ["dedupe", "decide", a, b, "reject", "--home", str(home)])

    assert result.exit_code == 0, all_output(result)
    assert repo.db.query("SELECT * FROM paper_relation WHERE kind = 'same_as'") == []


def test_decide_unknown_decision_exits_2(repo: Repo, home: Path) -> None:
    a, b = _pair(repo)

    result = runner.invoke(app, ["dedupe", "decide", a, b, "drop", "--home", str(home)])

    assert result.exit_code == 2
    assert "merge" in all_output(result)  # 提示合法取值


def test_decide_pair_without_candidate_edge_exits_2(repo: Repo, home: Path) -> None:
    a, _b = _pair(repo)
    other = repo.upsert_paper(
        VENUE_ID, None, PaperStub(title="Unrelated", identifiers=(("doi", "10.9999/z"),))
    )

    result = runner.invoke(app, ["dedupe", "decide", a, other, "merge", "--home", str(home)])

    assert result.exit_code == 2
    assert "错误" in all_output(result)


def test_revert_restores_pending_and_exits_0(repo: Repo, home: Path) -> None:
    a, b = _pair(repo)
    runner.invoke(app, ["dedupe", "decide", a, b, "merge", "--home", str(home)])

    result = runner.invoke(app, ["dedupe", "revert", a, b, "--home", str(home)])

    assert result.exit_code == 0, all_output(result)
    review = runner.invoke(app, ["dedupe", "review", "--home", str(home)])
    assert a in all_output(review)  # 回到待审队列
    groups = runner.invoke(app, ["dedupe", "groups", "--home", str(home)])
    assert "无 same_as" in all_output(groups)  # 聚合视图随之还原


def test_revert_undecided_pair_is_a_noop_exit_0(repo: Repo, home: Path) -> None:
    """未裁决的对回滚 = 幂等空操作（同 `cooldown clear` 对不存在键的宽容口径），不报错。"""
    a, b = _pair(repo)

    result = runner.invoke(app, ["dedupe", "revert", a, b, "--home", str(home)])

    assert result.exit_code == 0, all_output(result)
    assert "无需回滚" in all_output(result)


def test_broken_config_toml_exits_2_without_traceback(home: Path) -> None:
    """分层加载护栏（D-025）：config.toml 语法错 → 优雅退出 2（同 `cli._env` 口径）。"""
    (home / "config.toml").write_text("[paths\nbroken", encoding="utf-8")

    result = runner.invoke(app, ["dedupe", "review", "--home", str(home)])

    assert result.exit_code == 2
    assert "错误" in all_output(result)


def test_review_warns_when_the_pair_also_has_a_preprint_of_edge(repo: Repo, home: Path) -> None:
    """独立审查 P1-1 呈现面：这类 pair 的 merge 会被拒，列表里就要说明白，且给出的
    下一步只剩 reject（不再打印 `merge|reject` 误导人去试）。"""
    a, b = _pair(repo)
    repo.db.execute(
        "INSERT INTO paper_relation "
        "(from_paper, to_paper, kind, confidence, evidence_json, decided) VALUES (?,?,?,?,?,?)",
        (a, b, "preprint_of", 1.0, '{"reason": "meta-clue:doi"}', None),
    )

    result = runner.invoke(app, ["dedupe", "review", "--home", str(home)])

    out = all_output(result)
    assert result.exit_code == 0, out
    assert "preprint_of" in out and "D-007" in out
    assert f"crawler dedupe decide {a} {b} reject" in out
    assert "merge|reject" not in out


def test_decide_merge_on_a_preprint_pair_exits_2_without_side_effects(
    repo: Repo, home: Path
) -> None:
    """D-007 红线：merge 被响亮拒绝（退出 2）、库内零副作用；**无 --force 旁路**。"""
    a, b = _pair(repo)
    repo.db.execute(
        "INSERT INTO paper_relation "
        "(from_paper, to_paper, kind, confidence, evidence_json, decided) VALUES (?,?,?,?,?,?)",
        (a, b, "preprint_of", 1.0, '{"reason": "meta-clue:doi"}', None),
    )

    result = runner.invoke(app, ["dedupe", "decide", a, b, "merge", "--home", str(home)])

    out = all_output(result)
    assert result.exit_code == 2
    assert "preprint_of" in out and "D-007" in out
    assert repo.db.query("SELECT * FROM paper_relation WHERE kind = 'same_as'") == []
    assert repo.merged_groups() == []
    # reject 仍可用（关掉误报候审是合法操作）。
    assert (
        runner.invoke(app, ["dedupe", "decide", a, b, "reject", "--home", str(home)]).exit_code == 0
    )


def test_revert_notes_that_the_pair_is_still_merged_via_another_edge(
    repo: Repo, home: Path
) -> None:
    """独立审查 P2-2：回滚只解除**这一条**边；两者若经 A~B、B~C 仍同类，出口须提示，
    否则人会以为"回滚了却没生效"。"""
    a, b = _pair(repo)
    c = repo.upsert_paper(
        VENUE_ID, None, PaperStub(title="Third", identifiers=(("doi", "10.9999/c3"),))
    )
    repo.db.execute(
        "INSERT INTO paper_relation "
        "(from_paper, to_paper, kind, confidence, evidence_json, decided) VALUES (?,?,?,?,?,?)",
        (b, c, "candidate_duplicate", 0.5, "{}", None),
    )
    repo.decide_candidate(a, b, "merge")
    repo.decide_candidate(b, c, "merge")
    # 再把 a~c 也裁决为 merge（冗余连通），使回滚 a~b 后两者仍同类。
    repo.db.execute(
        "INSERT INTO paper_relation "
        "(from_paper, to_paper, kind, confidence, evidence_json, decided) VALUES (?,?,?,?,?,?)",
        (a, c, "candidate_duplicate", 0.5, "{}", None),
    )
    repo.decide_candidate(a, c, "merge")

    result = runner.invoke(app, ["dedupe", "revert", a, b, "--home", str(home)])

    out = all_output(result)
    assert result.exit_code == 0, out
    assert "已回滚为待审" in out
    assert "折叠不解除" in out


def test_revert_unknown_pair_exits_2(repo: Repo, home: Path) -> None:
    a, _b = _pair(repo)
    other = repo.upsert_paper(
        VENUE_ID, None, PaperStub(title="Unrelated", identifiers=(("doi", "10.9999/zz"),))
    )

    result = runner.invoke(app, ["dedupe", "revert", a, other, "--home", str(home)])

    assert result.exit_code == 2


# -- groups ------------------------------------------------------------------


def test_groups_shows_canonical_and_folded_members(repo: Repo, home: Path) -> None:
    a, b = _pair(repo)
    repo.decide_candidate(a, b, "merge")

    result = runner.invoke(app, ["dedupe", "groups", "--home", str(home)])

    out = all_output(result)
    assert result.exit_code == 0, out
    assert min(a, b) in out and max(a, b) in out
    assert "doi:10.9999/a" in out and "doi:10.9999/b" in out  # identifier 并集视图
