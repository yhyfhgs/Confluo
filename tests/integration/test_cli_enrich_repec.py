"""`crawler enrich --source repec` 端到端集成（走真 sqlite；D-035 决策 2/3/4 的 DoD 载体）。

与 `test_cli_enrich.py` 的分工：那边把 `enrich_batch` 猴补为受控假实现、只验 CLI 接线；
**本文件跑真实 `RepecAdapter`**（零网络，读 `tmp_path` 内的真快照文件），因为 repec 的
DoD 恰恰在"真实解析 + 真实优先级收敛"这条链上：

- **DoD①「JEL 落 meta 且对 crossref 既有字段零覆盖」**——须真的经 `SOURCE_PRIORITY`
  （`crossref 5` vs `repec 1`，D-035 决策 2 七位重编号）裁决，猴补假 stub 验不出这件事。
- **DoD②「快照缺失/过期响亮」**——须真的走 adapter 的失效分支到摘要行。
- `(repec, handle)` 的 *RePEc 内部* 幂等性——须真的经 `MergeEngine` 强合并。
"""

from __future__ import annotations

import hashlib
import json
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from paper_crawler.adapters.repec import parse
from paper_crawler.cli import app
from paper_crawler.merge import MergeEngine
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.types import PaperStub, VenueSpec

runner = CliRunner()

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "repec"
_REDIF_NAME = "nbr/nberwo/nberwo.rdf"
_W35506 = "10.3386/w35506"  # 快照内有 JEL 的记录
_W3210 = "10.3386/w3210"  # 快照内无 JEL 的历史记录
_VENUE = "mock_journal_a"


def _venue_spec() -> VenueSpec:
    return VenueSpec(
        id=_VENUE,
        kind="journal",
        names={"full": _VENUE, "aliases": []},
        field=["econ"],
        identifiers={"issn": ["0000-0000"]},
        metadata_source="mock_platform",
        fulltext_source="mock_platform",
    )


def _write_snapshot(home: Path, *, fetched_at: str | None = None) -> None:
    """在 `<home>/state/repec/` 写一份真快照（CLI 侧路径由 `_apply_enrich_key` 装配）。

    `sha256`/`bytes`/`record_count` 按实际内容算——加载器会校验（P2-⑦）。
    """
    root = home / "state" / "repec"
    payload = root / _REDIF_NAME
    payload.parent.mkdir(parents=True, exist_ok=True)
    data = (_FIXTURES / "01_nberwo_multi.rdf").read_bytes()
    payload.write_bytes(data)
    manifest = {
        "schema": 1,
        "archive": "nbr",
        "series": ["nberwo"],
        "mirror": "www2.nber.org",
        "source_urls": ["https://www2.nber.org/RePEc/nbr/nberwo/"],
        "fetched_at": fetched_at or datetime.now(UTC).isoformat(),
        "files": [
            {
                "name": _REDIF_NAME,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        ],
        "record_count": len(parse.parse_redif(data)),
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _seed_crossref_paper(home: Path, doi: str, *, title: str, abstract: str | None = None) -> None:
    """经 `MergeEngine.ingest(source="crossref")` 建行——**带 provenance**，故 repec 的低位
    优先级会被真正行使（对照 `upsert_paper` 的 pull 路径：无 provenance ⇒ 视为最高优先，
    那条路径验不出优先级表本身）。"""
    with closing(Database(home / "catalog.sqlite")) as db:
        db.migrate()
        repo = Repo(db)
        repo.upsert_venue(_venue_spec())
        MergeEngine(repo).ingest(
            PaperStub(title=title, identifiers=(("doi", doi),), abstract=abstract, year=2022),
            source="crossref",
        )


def _paper_row(home: Path, doi: str) -> dict[str, object]:
    with closing(Database(home / "catalog.sqlite")) as db:
        rows = db.query(
            "SELECT p.id, p.title, p.abstract, p.year, p.meta_json FROM paper p "
            "JOIN identifier i ON i.paper_id = p.id WHERE i.scheme = 'doi' AND i.value = ?",
            (doi,),
        )
    assert rows, f"no paper row for {doi}"
    return dict(rows[0])


def _identifiers(home: Path, paper_id: object) -> set[tuple[str, str]]:
    with closing(Database(home / "catalog.sqlite")) as db:
        rows = db.query("SELECT scheme, value FROM identifier WHERE paper_id = ?", (paper_id,))
    return {(str(r["scheme"]), str(r["value"])) for r in rows}


def _paper_count(home: Path) -> int:
    with closing(Database(home / "catalog.sqlite")) as db:
        rows = db.query("SELECT COUNT(*) AS n FROM paper", ())
    return int(rows[0]["n"])


def _candidate_count(home: Path) -> int:
    with closing(Database(home / "catalog.sqlite")) as db:
        rows = db.query(
            "SELECT COUNT(*) AS n FROM paper_relation WHERE kind = 'candidate_duplicate'", ()
        )
    return int(rows[0]["n"])


# --- DoD①：JEL 落 meta + 对 crossref 既有字段零覆盖 -------------------------------------------


def test_repec_enrich_lands_jel_in_meta_and_never_overwrites_crossref_fields(
    tmp_path: Path,
) -> None:
    """核心验收：JEL/published_in 补进 `meta`，**crossref 的 title 一字不改**。

    这是 D-035 决策 2「repec 取最低位 ⇒ 只补空即可全额兑现，**无须实现特殊'只补不覆盖'
    逻辑**」的端到端证据：adapter 侧照常产出 title/authors/year/abstract，由优先级表
    （`crossref 5` > `repec 1`）在收敛层挡住覆盖。
    """
    home = tmp_path / "home"
    home.mkdir()
    _write_snapshot(home)
    _seed_crossref_paper(home, _W35506, title="Crossref 权威标题", abstract=None)

    result = runner.invoke(app, ["enrich", "--source", "repec", "--home", str(home)])

    assert result.exit_code == 0, result.output
    row = _paper_row(home, _W35506)
    # ① crossref 既有 title 零覆盖（repec 的 stub 标题不同，若覆盖此处即打红）
    assert row["title"] == "Crossref 权威标题"
    # ② JEL 与版本关联落 meta（本通道的独家增值）
    meta = json.loads(str(row["meta_json"]))
    assert json.loads(meta["jel"]) == ["D1", "J13", "J15"]
    assert str(meta["published_in"]).startswith("published in Journal of Economic Perspectives")
    # ③ crossref 留空的 abstract 被补上（"只补空"的另一半）
    assert row["abstract"] is not None
    assert "US birth rates have fallen" in str(row["abstract"])


def test_repec_enrich_adds_repec_identifier_to_existing_paper(tmp_path: Path) -> None:
    """`(repec, handle)` 与入参 DOI 同挂一条 paper（不新建行）。"""
    home = tmp_path / "home"
    home.mkdir()
    _write_snapshot(home)
    _seed_crossref_paper(home, _W35506, title="Crossref 权威标题")

    result = runner.invoke(app, ["enrich", "--source", "repec", "--home", str(home)])

    assert result.exit_code == 0, result.output
    row = _paper_row(home, _W35506)
    assert ("repec", "RePEc:nbr:nberwo:35506") in _identifiers(home, row["id"])
    assert _paper_count(home) == 1


def test_repec_enrich_is_idempotent_across_runs(tmp_path: Path) -> None:
    """跑两遍不新建 paper、不重复 identifier——`(repec, handle)` 的 *RePEc 内部* 幂等锚点。

    注意这与 D-027「handle **非跨源合并锚点**」不冲突：那说的是"不拿 handle 去跟别的源对齐
    身份"，此处说的是"本源自身可重放"（见 `parse.stub_from_record` docstring）。
    """
    home = tmp_path / "home"
    home.mkdir()
    _write_snapshot(home)
    _seed_crossref_paper(home, _W35506, title="Crossref 权威标题")

    first = runner.invoke(app, ["enrich", "--source", "repec", "--home", str(home)])
    second = runner.invoke(app, ["enrich", "--source", "repec", "--home", str(home)])

    assert first.exit_code == 0 and second.exit_code == 0, second.output
    assert _paper_count(home) == 1
    row = _paper_row(home, _W35506)
    assert _identifiers(home, row["id"]) == {
        ("doi", _W35506),
        ("repec", "RePEc:nbr:nberwo:35506"),
    }


# --- P1-R2 对抗：w/t 混合快照——t 不污染 w、不落假 candidate、计不可寻址 ----------------------


def test_t_series_doi_does_not_pollute_w_or_flag_false_duplicate(tmp_path: Path) -> None:
    """P1-R2 端到端对抗：`w{n}` 与 `t{n}` 同号不再塌进同一 handle（假重复 + 静默污染根因）。

    修复前：`10.3386/t9001` 映射到 `RePEc:nbr:nberwo:9001`（= 快照内 w9001 记录的 handle）→
    enrich 给 t9001 的 paper 补上 w9001 的数据 + 同一 `(repec, handle)` 全局唯一锚点 → 两 paper
    共享一个锚点 → 落一条高置信 `candidate_duplicate`（假重复）、t9001 记录被 w9001 数据静默污染。
    修复后：t9001 → 不可寻址（不产 stub）→ 零污染、零假 candidate、计入"不可寻址"。
    快照复用 `01_nberwo_multi.rdf`（内含 `RePEc:nbr:nberwo:9001` 记录）。
    """
    home = tmp_path / "home"
    home.mkdir()
    _write_snapshot(home)
    _seed_crossref_paper(home, "10.3386/w9001", title="真 · 工作论文 9001", abstract=None)
    _seed_crossref_paper(home, "10.3386/t9001", title="另一篇 · 技术工作论文 9001", abstract=None)

    result = runner.invoke(app, ["enrich", "--source", "repec", "--home", str(home)])
    assert result.exit_code == 0, result.output

    # ① t9001 的 paper 绝不获得 w9001 的 repec handle，标题/摘要零污染
    t_row = _paper_row(home, "10.3386/t9001")
    assert ("repec", "RePEc:nbr:nberwo:9001") not in _identifiers(home, t_row["id"])
    assert t_row["title"] == "另一篇 · 技术工作论文 9001"
    assert t_row["abstract"] is None  # w9001 的 abstract 没漏进来
    # ② w9001 正常获得 handle（w 通道未被收窄误伤）
    w_row = _paper_row(home, "10.3386/w9001")
    assert ("repec", "RePEc:nbr:nberwo:9001") in _identifiers(home, w_row["id"])
    # ③ 零假 candidate_duplicate（修复前此处 ≥1）
    assert _candidate_count(home) == 0
    # ④ t9001 计入"不可寻址"（w9001 命中）
    assert "命中 1" in result.output
    assert "不可寻址 1" in result.output
    assert _paper_count(home) == 2  # 两篇独立论文，绝不被合并


# --- 摘要行：新鲜度 + 未命中三分（D-035 决策 4）-----------------------------------------------


def test_summary_line_reports_freshness_and_three_way_misses(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    _write_snapshot(home, fetched_at="2026-07-27T00:00:00+00:00")
    _seed_crossref_paper(home, _W35506, title="有 JEL")
    _seed_crossref_paper(home, _W3210, title="无 JEL 的历史条目")
    _seed_crossref_paper(home, "10.3386/w99999", title="快照未覆盖")
    _seed_crossref_paper(home, "10.2139/ssrn.42", title="SSRN——RePEc 结构性为 0")

    result = runner.invoke(app, ["enrich", "--source", "repec", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "[repec]" in result.output
    assert "fetched_at=2026-07-27T00:00:00+00:00" in result.output  # 新鲜度须可见
    assert "命中 2（无 JEL 1）" in result.output
    assert "不可寻址 1" in result.output
    assert "覆盖缺口 1" in result.output


def test_no_openalex_budget_note_leaks_into_repec_summary(tmp_path: Path) -> None:
    """附注按 adapter 实例分派——repec 不该出现 openalex 的预算行。"""
    home = tmp_path / "home"
    home.mkdir()
    _write_snapshot(home)
    _seed_crossref_paper(home, _W35506, title="t")

    result = runner.invoke(app, ["enrich", "--source", "repec", "--home", str(home)])

    assert "预算消耗" not in result.output


# --- DoD②：快照缺失（响亮 CONFIG，不改退出码）/ 过期（响亮警告 + 继续）-----------------------


def test_missing_snapshot_stops_this_source_loudly_without_failing_the_command(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    _seed_crossref_paper(home, _W35506, title="Crossref 权威标题")  # 不写快照

    result = runner.invoke(app, ["enrich", "--source", "repec", "--home", str(home)])

    assert result.exit_code == 0, result.output  # 与 s2 缺 key / openalex 熔断同构
    assert "提前终止: config" in result.output
    assert "快照缺失" in result.output
    assert "scripts/repec_snapshot.py" in result.output  # 指引可操作
    assert _paper_row(home, _W35506)["title"] == "Crossref 权威标题"  # 库未被动过


def test_stale_snapshot_warns_but_still_enriches(tmp_path: Path) -> None:
    """过期 → 警告 + **继续富化**（对 enrich-eval §2.7 DoD② 字面的有意收窄，D-035 已入档）。"""
    home = tmp_path / "home"
    home.mkdir()
    stale_at = (datetime.now(UTC) - timedelta(days=47)).isoformat()
    _write_snapshot(home, fetched_at=stale_at)
    _seed_crossref_paper(home, _W35506, title="Crossref 权威标题")

    result = runner.invoke(app, ["enrich", "--source", "repec", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "47 天未刷新" in result.output  # 天数
    assert "阈值 30 天" in result.output
    assert "scripts/repec_snapshot.py" in result.output  # 刷新命令
    assert "提前终止" not in result.output  # 关键：过期不阻断
    meta = json.loads(str(_paper_row(home, _W35506)["meta_json"]))
    assert json.loads(meta["jel"]) == ["D1", "J13", "J15"]


# --- --source 用法面 ---------------------------------------------------------------------------


def test_repec_is_an_accepted_source_value(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    _seed_crossref_paper(home, _W35506, title="t")

    result = runner.invoke(app, ["enrich", "--source", "repec", "--home", str(home)])

    assert result.exit_code == 0, result.output


def test_unknown_source_error_lists_repec_among_options(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    _seed_crossref_paper(home, _W35506, title="t")

    result = runner.invoke(app, ["enrich", "--source", "bogus", "--home", str(home)])

    assert result.exit_code == 2
    assert "repec" in result.output


def test_help_text_lists_repec(tmp_path: Path) -> None:
    result = runner.invoke(app, ["enrich", "--help"])
    assert result.exit_code == 0
    assert "repec" in result.output
