"""stage 5 extract handler 的端到端契约（design/12 §5/§6/§7/§10；D-033）。

覆盖：落盘落库对账 · asset 级幂等跳过 · 支配预判与其护栏 · `--force` 绕过 · 全序取代与
顺序无关 · 失败三分 · GROBID 三态（AC-7.2）与空产物回归锁（§6.1 P0-2）· 崩溃窗 · 换后缀
旧产物清理。**全部离线**：GROBID 走 `httpx.MockTransport`，PDF 走程序化生成语料（零 `.pdf`
文件入库，AC-0.3）。

环境构建器复用 `test_pipeline_e2e.make_env`（tests/ 无顶层包，按 helpers 先例以
`integration.test_pipeline_e2e` 顶层包名导入）。
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from helpers.minipdf import make_image_only_pdf, make_text_pdf
from helpers.textmatch import DEFAULT_MAX_RATIO, title_distance_ratio, title_in_body_ratio
from integration.test_pipeline_e2e import VENUE, PipelineEnv, make_env
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.pipeline import Selector, stages
from paper_crawler.pipeline.extract import (
    STATE_EXTRACT_FAILED,
    STATE_EXTRACTED,
    STATE_NOOP,
    GrobidRuntime,
    PypdfExtractor,
    TextExtractor,
)
from paper_crawler.pipeline.report import RunReport
from paper_crawler.storage.repo import FetchLogRow
from paper_crawler.types import AssetKind, AssetPlan
from unit.test_extract_grobid import alive_handler, make_runtime, tei

TITLE = "Deterministic Extraction of Scholarly Full Text"
BODY = "\n".join([TITLE, "Ada Lovelace", *(f"section {i} paragraph text" for i in range(30))])


@pytest.fixture
def env(tmp_path: Path) -> Iterator[PipelineEnv]:
    e = make_env(tmp_path)
    yield e
    e.close()


# -- 夹具小件 ------------------------------------------------------------------------------


class CountingExtractor:
    """包一层计数的抽取器（断言「抽取器零调用」＝证明未打开源文件、未发 GROBID 请求）。"""

    def __init__(self, inner: TextExtractor) -> None:
        self._inner = inner
        self.name = inner.name
        self.version = inner.version
        self.calls = 0

    def extract(self, source: Path) -> object:
        self.calls += 1
        return self._inner.extract(source)


def seed_fetched_pdf(env: PipelineEnv, data: bytes = b"") -> tuple[str, str]:
    """跑一次 fetch-only pull，再把落盘的 pdf 换成真实生成语料并同步 asset 行的 sha/bytes。

    mock adapter 的载荷不是合法 PDF（`%PDF-1.4` 头 + 填充字节），真抽取下它是 `corrupt`；
    快乐路径的用例因此需要一份真实可抽的 PDF——替换文件 + 同步哈希即等价于「真取回了一份
    数字原生 PDF」，不必为此改动 mock adapter 的冻结载荷（会牵动大量既有字节级断言）。
    """
    env.make_runner().pull(VENUE, Selector(year=2024, limit=1))
    rows = env.db.query("SELECT * FROM asset WHERE state = 'fetched' AND kind = 'pdf'")
    assert len(rows) == 1
    asset = rows[0]
    asset_id, paper_id = str(asset["id"]), str(asset["paper_id"])
    if data:
        replace_source(env, asset_id, data)
    return asset_id, paper_id


def replace_source(env: PipelineEnv, asset_id: str, data: bytes) -> None:
    asset = env.repo.get_asset(asset_id)
    assert asset is not None
    path = Path(str(asset["file_path"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    env.repo.mark_asset(
        asset_id,
        state="fetched",
        file_path=str(path),
        bytes_=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


def run_extract(
    env: PipelineEnv,
    asset_id: str,
    *,
    grobid: GrobidRuntime | None = None,
) -> RunReport:
    """把一个 extract 任务塞进队列并 drain。

    队列级 `force=True` 只绕过入队新鲜度（否则重跑恒 fresh_skip、handler 根本不被调用）——
    它**不**是 `--force`：`_forced_run` 读的是父 `pull` 任务的参数，此处 `parent_id` 为
    None，故 handler 级的幂等跳过与支配预判照常求值，正是本文件要测的面。
    """
    runner = env.make_runner()
    if grobid is not None:
        runner.ctx.grobid = grobid
    env.queue.enqueue("extract", VENUE, {"asset": asset_id}, force=True)
    return runner.drain()


def fulltext(env: PipelineEnv, paper_id: str) -> sqlite3.Row:
    rows = env.db.query("SELECT * FROM fulltext WHERE paper_id = ?", (paper_id,))
    assert rows, "fulltext 行缺失"
    return rows[0]


def artifacts(env: PipelineEnv) -> list[Path]:
    root = env.config.data_dir / "fulltext"
    return sorted(p for p in root.rglob("*") if p.is_file()) if root.is_dir() else []


def log_text(env: PipelineEnv) -> str:
    return "".join(p.read_text(encoding="utf-8") for p in env.config.log_dir.glob("*.jsonl"))


def grobid_ok(text: str = "") -> GrobidRuntime:
    return make_runtime(alive_handler(lambda _r: httpx.Response(200, text=text or tei("full"))))


# -- 快乐路径：落盘 + 落库对账（AC-7.1 纯文本路径）----------------------------------------


def test_plain_text_landing_and_row(env: PipelineEnv) -> None:
    asset_id, paper_id = seed_fetched_pdf(env, make_text_pdf(BODY))
    report = run_extract(env, asset_id)
    assert report.failed == 0 and report.blocked == 0

    row = fulltext(env, paper_id)
    assert row["extractor"] == "pypdf" and row["state"] == STATE_EXTRACTED
    assert row["asset_id"] == asset_id and row["note"] is None
    assert row["char_count"] > 0 and row["lang"] is None

    # §5.4：text_path 是**相对 data_dir、不含 `data/` 前缀**的形态；带前缀会让 verify
    # 解析成 …/data/data/fulltext/… 使全库每一行都报 missing_file。
    text_path = str(row["text_path"])
    assert text_path.startswith("fulltext/") and not text_path.startswith("data/")
    assert text_path.endswith(f"/{paper_id}.txt")

    landed = env.config.data_dir / text_path
    assert landed.is_file()
    assert hashlib.sha256(landed.read_bytes()).hexdigest() == row["text_sha256"]
    assert row["source_sha256"] == env.repo.get_asset(asset_id)["sha256"]  # type: ignore[index]
    # pdf/{v}/{y}/{ulid}.pdf 与 fulltext/{v}/{y}/{ulid}.txt **同 v/y 对位**（verify 对账依赖）。
    pdf_path = Path(str(env.repo.get_asset(asset_id)["file_path"]))  # type: ignore[index]
    assert pdf_path.parent.name == landed.parent.name  # year 段
    assert pdf_path.parent.parent.name == landed.parent.parent.name  # venue 段

    # AC-7.1 判据（纯文本路径）：标题的归一形在正文前 2000 字符内。
    assert title_in_body_ratio(TITLE, landed.read_text(encoding="utf-8")) <= DEFAULT_MAX_RATIO
    # ingest_state 推进到 extracted（成功路径）。
    assert env.db.query("SELECT ingest_state FROM paper WHERE id = ?", (paper_id,))[0][0] == (
        "extracted"
    )


def test_rerun_hits_the_idempotent_skip(env: PipelineEnv, monkeypatch: pytest.MonkeyPatch) -> None:
    """§5.2 幂等跳过：四元组全等 + 产物校验通过 ⇒ `"skipped"`，**抽取器零调用**。"""
    asset_id, _ = seed_fetched_pdf(env, make_text_pdf(BODY))
    run_extract(env, asset_id)

    counter = CountingExtractor(PypdfExtractor())
    monkeypatch.setattr(stages, "_PYPDF", counter)
    report = run_extract(env, asset_id)
    assert report.skipped == 1 and counter.calls == 0


def test_rerun_after_source_change_reextracts(env: PipelineEnv) -> None:
    """asset 被 re-fetch（新内容、新 sha）⇒ 幂等键不命中且存量行陈旧 ⇒ 重抽取代。"""
    asset_id, paper_id = seed_fetched_pdf(env, make_text_pdf(BODY))
    run_extract(env, asset_id)
    first = fulltext(env, paper_id)["char_count"]

    replace_source(env, asset_id, make_text_pdf(BODY + "\nappended revision paragraph"))
    run_extract(env, asset_id)
    assert fulltext(env, paper_id)["char_count"] > first
    assert len(artifacts(env)) == 1  # 同后缀覆写，不留第二份


# -- 失败三分（§6.1）-----------------------------------------------------------------------


def test_class_2_failure_writes_extract_failed_row_without_failing_the_task(
    env: PipelineEnv,
) -> None:
    """第 2 类：源文件在、但抽不出 ⇒ 不抛、任务不 FAILED，落 `extract_failed` + note。"""
    asset_id, paper_id = seed_fetched_pdf(env, make_image_only_pdf())
    report = run_extract(env, asset_id)
    assert report.failed == 0 and report.blocked == 0

    row = fulltext(env, paper_id)
    assert row["state"] == STATE_EXTRACT_FAILED and row["note"] == "image_only"
    assert row["text_path"] is None and row["char_count"] == 0
    assert row["extractor"] == "pypdf" and row["asset_id"] == asset_id
    assert artifacts(env) == []
    # §6.2：失败**不进** ingest_state 阶梯——事实由 fulltext.state 承载，阶梯保持单调。
    assert env.db.query("SELECT ingest_state FROM paper WHERE id = ?", (paper_id,))[0][0] != (
        "extracted"
    )


def test_class_2_failure_is_idempotent(env: PipelineEnv, monkeypatch: pytest.MonkeyPatch) -> None:
    """失败行同受幂等键保护：不重复抽取一个已知抽不出的文件（长尾不被每轮重抽）。"""
    asset_id, _ = seed_fetched_pdf(env, make_image_only_pdf())
    run_extract(env, asset_id)
    counter = CountingExtractor(PypdfExtractor())
    monkeypatch.setattr(stages, "_PYPDF", counter)
    assert run_extract(env, asset_id).skipped == 1
    assert counter.calls == 0


def test_class_1_library_file_mismatch_raises_integrity(env: PipelineEnv) -> None:
    """第 1 类：asset 称 fetched 但文件被删 ⇒ 响亮 INTEGRITY（re-fetch/verify 的正管辖区）。

    静默记 `extract_failed` 会把一个**可修复的库缺陷**伪装成「这篇抽不出来」，永久掩盖。
    """
    asset_id, _ = seed_fetched_pdf(env, make_text_pdf(BODY))
    Path(str(env.repo.get_asset(asset_id)["file_path"])).unlink()  # type: ignore[index]
    report = run_extract(env, asset_id)
    assert report.failed == 1
    assert "INTEGRITY" in log_text(env) or "integrity" in log_text(env)


def test_class_3_missing_asset_raises_config(env: PipelineEnv) -> None:
    env.queue.enqueue("extract", VENUE, {"asset": "01NOPENOPENOPENOPENOPENOPE"}, force=True)
    assert env.make_runner().drain().blocked == 1  # CONFIG 经 pipeline 特判转 BLOCKED


def test_class_3_unfetched_asset_raises_config(env: PipelineEnv) -> None:
    asset_id, _ = seed_fetched_pdf(env, make_text_pdf(BODY))
    env.db.execute("UPDATE asset SET state = 'planned' WHERE id = ?", (asset_id,))
    assert run_extract(env, asset_id).blocked == 1


# -- 全序取代（§5.3）：三回归锁之二「rank 序 extract_failed > noop」-----------------------


def test_extract_failed_supersedes_legacy_noop_row(
    env: PipelineEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**回归锁**：存量 noop 行 + 一次抽取失败 ⇒ 终态是 `extract_failed`（**不是** noop），
    且再跑一轮命中幂等键 `"skipped"`、抽取器零调用（证明长尾不被反复重抽）。"""
    asset_id, paper_id = seed_fetched_pdf(env, make_image_only_pdf())
    env.db.execute(
        "INSERT INTO fulltext (paper_id, extractor, extractor_ver, text_path, char_count, "
        "lang, extracted_at, state) VALUES (?,?,?,?,?,?,?,?)",
        (paper_id, "noop", "1", None, 0, None, "2026-01-01T00:00:00Z", STATE_NOOP),
    )
    run_extract(env, asset_id)
    row = fulltext(env, paper_id)
    assert row["state"] == STATE_EXTRACT_FAILED and row["extractor"] == "pypdf"

    counter = CountingExtractor(PypdfExtractor())
    monkeypatch.setattr(stages, "_PYPDF", counter)
    assert run_extract(env, asset_id).skipped == 1
    assert counter.calls == 0


def test_real_extraction_supersedes_legacy_noop_row(env: PipelineEnv) -> None:
    asset_id, paper_id = seed_fetched_pdf(env, make_text_pdf(BODY))
    env.db.execute(
        "INSERT INTO fulltext (paper_id, extractor, extractor_ver, text_path, char_count, "
        "lang, extracted_at, state) VALUES (?,?,?,?,?,?,?,?)",
        (paper_id, "noop", "1", None, 0, None, "2026-01-01T00:00:00Z", STATE_NOOP),
    )
    run_extract(env, asset_id)
    row = fulltext(env, paper_id)
    assert row["state"] == STATE_EXTRACTED and row["char_count"] > 0


def test_loser_writes_nothing(env: PipelineEnv, monkeypatch: pytest.MonkeyPatch) -> None:
    """败者：不写文件、不改 DB，只落 obslog 说明被既有更优产物压制。

    场景取 §5.6「形态 A（同 rank 平局）」——同抽取器同版本、不同 asset（正刊版 vs OA 兜底版）：
    支配预判**挡不住**（`(rank, ver_key)` 相等，不是严格劣势），故必须实抽才能比 `char_count`，
    抽完再丢弃败者。这份重复算力如实入档、不优化（要根治须记 per-asset 产物矩阵＝1-N 升级）。
    """
    asset_id, paper_id = seed_fetched_pdf(env, make_text_pdf(BODY))
    run_extract(env, asset_id)
    before = dict(fulltext(env, paper_id))
    assert before["extractor"] == "pypdf"

    counter = CountingExtractor(PypdfExtractor())
    monkeypatch.setattr(stages, "_PYPDF", counter)
    second = plan_second_pdf(env, paper_id, make_text_pdf("truncated copy"))
    report = run_extract(env, second)
    assert report.failed == 0
    assert counter.calls == 1, "同 rank 平局：预判挡不住，必须实抽才能比 char_count"
    assert dict(fulltext(env, paper_id)) == before  # DB 逐列不变（败者零写入）
    assert '"reason": "suppressed"' in log_text(env)
    assert len(artifacts(env)) == 1  # 不落第二份文件


def test_dominated_second_asset_is_prejudged(
    env: PipelineEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """同 paper 第二个 pdf asset + 库里已有 grobid 行 ⇒ 支配预判命中，**零抽取**。"""
    asset_id, paper_id = seed_fetched_pdf(env, make_text_pdf(BODY))
    run_extract(env, asset_id, grobid=grobid_ok())
    counter = CountingExtractor(PypdfExtractor())
    monkeypatch.setattr(stages, "_PYPDF", counter)

    second = plan_second_pdf(env, paper_id, make_text_pdf(BODY + "\nmuch longer OA copy body"))
    assert run_extract(env, second).skipped == 1
    assert counter.calls == 0
    assert fulltext(env, paper_id)["extractor"] == "grobid"


def plan_second_pdf(env: PipelineEnv, paper_id: str, data: bytes) -> str:
    """给同一 paper 再建一个已 fetched 的 pdf asset（身份 `(paper, pdf, oa)`）。"""
    plan = AssetPlan(kind=AssetKind.PDF, url="https://oa.local/copy.pdf", version="oa")
    asset_id = env.repo.plan_asset(paper_id, plan, "unpaywall")
    path = env.config.data_dir / "pdf" / "oa" / f"{asset_id}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    env.repo.finalize_fetch(
        asset_id,
        file_path=str(path),
        bytes_=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        fetch_log_row=FetchLogRow(
            task_id=None,
            domain="oa.local",
            url=plan.url,
            http_status=200,
            bytes_=len(data),
            elapsed_ms=1,
            rate_wait_ms=0,
            error_class=None,
        ),
    )
    return asset_id


def test_order_independence_of_two_extractors(tmp_path: Path) -> None:
    """§5.3 顺序无关：GROBID→纯文本 与 纯文本→GROBID 两序的**终态逐列相同**。"""
    terminal: list[dict[str, object]] = []
    for grobid_first in (True, False):
        env = make_env(tmp_path / f"order-{grobid_first}")
        try:
            asset_id, paper_id = seed_fetched_pdf(env, make_text_pdf(BODY))
            order = [grobid_ok(), None] if grobid_first else [None, grobid_ok()]
            for runtime in order:
                run_extract(env, asset_id, grobid=runtime)
            row = dict(fulltext(env, paper_id))
            # 逐 env 变化的身份/时间列不是语义面：ULID 与时间戳每次都新；比较其余全部列 +
            # 落位后缀（同 paper 内 text_path 只由 venue/year/ulid/suffix 决定）。
            for identity in ("paper_id", "asset_id", "extracted_at"):
                row.pop(identity)
            row["text_path"] = str(row["text_path"]).rsplit("/", 1)[-1].split(".", 1)[-1]
            terminal.append(row)
        finally:
            env.close()
    assert terminal[0] == terminal[1]
    assert terminal[0]["extractor"] == "grobid"  # 全序胜者恒为 rank 更高者
    assert terminal[0]["text_path"] == "tei.xml"


def test_suffix_upgrade_prunes_the_old_artifact(env: PipelineEnv) -> None:
    """`.txt` → `.tei.xml` 升级时旧文件必须删（否则成 `orphan_file`）。"""
    asset_id, paper_id = seed_fetched_pdf(env, make_text_pdf(BODY))
    run_extract(env, asset_id)
    assert [p.name for p in artifacts(env)] == [f"{paper_id}.txt"]

    run_extract(env, asset_id, grobid=grobid_ok())
    assert [p.name for p in artifacts(env)] == [f"{paper_id}.tei.xml"]
    row = fulltext(env, paper_id)
    assert str(row["text_path"]).endswith(".tei.xml") and row["extractor"] == "grobid"
    # AC-7.1 判据（GROBID 路径）：TEI 标题与 paper.title 的归一化编辑距离比。
    assert title_distance_ratio(TITLE, "Deterministic Extraction of Scholarly Full Text") <= (
        DEFAULT_MAX_RATIO
    )


# -- 支配预判与护栏（§5.2）----------------------------------------------------------------


def test_dominance_prejudgement_skips_without_touching_the_source(
    env: PipelineEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§10-3c：库里已有 grobid 行、本轮 GROBID 关闭 ⇒ `"skipped"` 且**抽取器零调用**。

    若无此预判，每轮 pull 都会把全库 PDF 重抽一遍纯文本再全部丢弃。
    """
    asset_id, _ = seed_fetched_pdf(env, make_text_pdf(BODY))
    run_extract(env, asset_id, grobid=grobid_ok())

    counter = CountingExtractor(PypdfExtractor())
    monkeypatch.setattr(stages, "_PYPDF", counter)
    assert run_extract(env, asset_id).skipped == 1
    assert counter.calls == 0


@pytest.mark.parametrize("mode", ["deleted", "corrupted"])
def test_prejudgement_guard_reextracts_when_the_winner_artifact_is_gone(
    env: PipelineEnv, mode: str
) -> None:
    """§10-3d 护栏回归锁：胜者产物不在盘上/被改坏 ⇒ **不得**预判跳过，须实抽并重新落盘补齐。

    若无护栏：预判只看 `(rank, ver_key)` 判定 pypdf 必败 ⇒ `"skipped"` ⇒ verify 从此恒报
    `missing_file`（或 `hash_mismatch`）而**重跑 extract 永不自愈**——预判把一个本可自动修复
    的缺口变成永久缺口。
    """
    asset_id, paper_id = seed_fetched_pdf(env, make_text_pdf(BODY))
    run_extract(env, asset_id, grobid=grobid_ok())
    winner = env.config.data_dir / str(fulltext(env, paper_id)["text_path"])
    if mode == "deleted":
        winner.unlink()
    else:
        winner.write_text("tampered", encoding="utf-8")

    report = run_extract(env, asset_id)  # 本轮 GROBID 关闭
    assert report.skipped == 0

    row = fulltext(env, paper_id)
    assert row["extractor"] == "pypdf" and row["state"] == STATE_EXTRACTED
    landed = env.config.data_dir / str(row["text_path"])
    # 缺口自愈：产物重新落盘且哈希与库内记录相符（＝T14 verify 的 missing_file/hash_mismatch
    # 两类判据同时为绿）。
    assert landed.is_file()
    assert hashlib.sha256(landed.read_bytes()).hexdigest() == row["text_sha256"]
    assert artifacts(env) == [landed]  # 旧 .tei.xml 已被清理，无孤儿


# -- `--force` 绕过（§5.5 r3 ④a）----------------------------------------------------------


def test_force_bypasses_the_idempotent_skip(
    env: PipelineEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--force` 同时绕过任务级 fresh_skip、幂等跳过与支配预判 ⇒ 仍实抽（人工修复通道）。"""
    env.make_runner().pull(VENUE, Selector(year=2024, limit=1))
    asset_id = str(env.db.query("SELECT id FROM asset WHERE state = 'fetched'")[0]["id"])
    replace_source(env, asset_id, make_text_pdf(BODY))
    env.make_runner().pull(VENUE, Selector(year=2024, limit=1), with_extract=True)

    counter = CountingExtractor(PypdfExtractor())
    monkeypatch.setattr(stages, "_PYPDF", counter)
    env.make_runner().pull(VENUE, Selector(year=2024, limit=1), with_extract=True)
    assert counter.calls == 0, "无 --force 时必须命中幂等跳过"

    env.make_runner().pull(VENUE, Selector(year=2024, limit=1), with_extract=True, force=True)
    assert counter.calls == 1, "--force 必须绕过幂等跳过，真的重做这次运算"


def test_force_does_not_lower_the_partial_order(env: PipelineEnv) -> None:
    """force **不降偏序**：不可能用 pypdf 覆盖已有的 GROBID TEI（写入判据仍走全序）。"""
    env.make_runner().pull(VENUE, Selector(year=2024, limit=1))
    asset_id = str(env.db.query("SELECT id FROM asset WHERE state = 'fetched'")[0]["id"])
    paper_id = str(env.repo.get_asset(asset_id)["paper_id"])  # type: ignore[index]
    replace_source(env, asset_id, make_text_pdf(BODY))
    run_extract(env, asset_id, grobid=grobid_ok())
    assert fulltext(env, paper_id)["extractor"] == "grobid"

    env.make_runner().pull(VENUE, Selector(year=2024, limit=1), with_extract=True, force=True)
    assert fulltext(env, paper_id)["extractor"] == "grobid"


# -- GROBID 三态（AC-7.2）+ 空产物回归锁（§6.1 P0-2）--------------------------------------


def test_ac_7_2_state_1_unconfigured_is_plain_text(env: PipelineEnv) -> None:
    asset_id, paper_id = seed_fetched_pdf(env, make_text_pdf(BODY))
    run_extract(env, asset_id)
    row = fulltext(env, paper_id)
    assert row["extractor"] == "pypdf" and str(row["text_path"]).endswith(".txt")
    assert "grobid" not in log_text(env)  # 默认形态非降级：不刷 WARN


def test_ac_7_2_state_2_configured_and_online_is_tei(env: PipelineEnv) -> None:
    asset_id, paper_id = seed_fetched_pdf(env, make_text_pdf(BODY))
    run_extract(env, asset_id, grobid=grobid_ok())
    row = fulltext(env, paper_id)
    assert row["extractor"] == "grobid" and str(row["text_path"]).endswith(".tei.xml")
    assert row["lang"] == "en"
    landed = env.config.data_dir / str(row["text_path"])
    assert landed.read_text(encoding="utf-8") == tei("full")  # TEI 原样落盘


def test_ac_7_2_state_3_configured_but_down_degrades_without_failing(env: PipelineEnv) -> None:
    """③配置但服务不可用 ⇒ `.txt` + pypdf + **任务不 FAILED、无异常逃逸**。"""
    down = make_runtime(lambda _r: httpx.Response(500, text="down"))
    asset_id, paper_id = seed_fetched_pdf(env, make_text_pdf(BODY))
    report = run_extract(env, asset_id, grobid=down)
    assert report.failed == 0 and report.blocked == 0
    row = fulltext(env, paper_id)
    assert row["extractor"] == "pypdf" and str(row["text_path"]).endswith(".txt")
    assert '"reason": "grobid_unreachable"' in log_text(env)
    assert down.disabled is True  # 记忆本轮：此后不再调用 GROBID（含探活）


def test_grobid_empty_tei_must_not_suppress_existing_plain_text(env: PipelineEnv) -> None:
    """§10-3b **回归锁**：header-only 空 TEI（200 + 合法 XML）必须触发纯文本兜底，
    且 `fulltext` 行**仍是 pypdf 那条**——rank 2 的空 TEI 不得取胜。

    若按「200 且 XML 合法」判成功，这一次「增强」反而会抹掉已有的 pypdf 正文（审查实测反例）。
    """
    asset_id, paper_id = seed_fetched_pdf(env, make_text_pdf(BODY))
    run_extract(env, asset_id)
    baseline = dict(fulltext(env, paper_id))
    assert baseline["extractor"] == "pypdf" and int(str(baseline["char_count"])) > 0

    empty = make_runtime(alive_handler(lambda _r: httpx.Response(200, text=tei("header_only"))))
    report = run_extract(env, asset_id, grobid=empty)
    assert report.failed == 0

    row = fulltext(env, paper_id)
    assert row["extractor"] == "pypdf", "空 TEI 以 rank 2 压制了既有正文（P0-2 反例复现）"
    assert row["char_count"] == baseline["char_count"]
    assert str(row["text_path"]).endswith(".txt")
    assert '"reason": "grobid_empty_tei"' in log_text(env)
    assert (env.config.data_dir / str(row["text_path"])).is_file()


def test_grobid_timeout_is_not_remembered(env: PipelineEnv) -> None:
    """读超时是 per-文档 的（大 PDF 慢），不代表服务不可用 ⇒ 不记忆，下一篇仍调 GROBID。"""

    def process(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    runtime = make_runtime(alive_handler(process))
    asset_id, _ = seed_fetched_pdf(env, make_text_pdf(BODY))
    run_extract(env, asset_id, grobid=runtime)
    assert runtime.disabled is False
    assert '"reason": "grobid_timeout"' in log_text(env)


# -- 崩溃窗（§5.5）------------------------------------------------------------------------


def test_crash_between_rename_and_upsert_leaves_no_second_artifact(
    env: PipelineEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """窗 2：产物已就位、DB 未更新 ⇒ 重跑重抽，落位路径是**纯函数**，同内容覆写同一路径。"""
    asset_id, paper_id = seed_fetched_pdf(env, make_text_pdf(BODY))

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("kill -9 between rename and upsert")

    monkeypatch.setattr(stages, "_upsert_fulltext", boom)
    assert run_extract(env, asset_id).failed == 1
    assert len(artifacts(env)) == 1
    assert env.db.query("SELECT * FROM fulltext WHERE paper_id = ?", (paper_id,)) == []

    monkeypatch.undo()
    assert run_extract(env, asset_id).failed == 0
    assert len(artifacts(env)) == 1, "重跑不产生第二份垃圾"
    assert fulltext(env, paper_id)["state"] == STATE_EXTRACTED


def test_crash_before_commit_leaves_only_a_part_file(
    env: PipelineEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """窗 1：`.part` 残留 → 启动期既有清理机制处置；重跑重抽，无副作用叠加。"""
    asset_id, _ = seed_fetched_pdf(env, make_text_pdf(BODY))

    def boom(self: object, final_path: Path) -> None:
        raise RuntimeError("kill -9 before commit")

    monkeypatch.setattr(stages.PartFileIO, "commit", boom)
    assert run_extract(env, asset_id).failed == 1
    assert artifacts(env) == []
    assert list((env.config.data_dir / "tmp").glob("*.part"))

    monkeypatch.undo()
    assert run_extract(env, asset_id).failed == 0
    assert len(artifacts(env)) == 1


# -- 无 pypdf 参与的接线核对 ---------------------------------------------------------------


def test_extract_makes_no_network_call_when_grobid_is_off(env: PipelineEnv) -> None:
    """extract 是本地纯计算：GROBID 关闭时零请求（socket 猴补看守已在 conftest 生效）。"""
    asset_id, _ = seed_fetched_pdf(env, make_text_pdf(BODY))
    before = len(env.repo.fetch_logs())
    run_extract(env, asset_id)
    assert len(env.repo.fetch_logs()) == before  # 不写 FetchLog（在线预算唯一事实源）


def test_missing_source_raises_and_never_writes_a_row(env: PipelineEnv) -> None:
    with pytest.raises(CrawlerError) as excinfo:
        PypdfExtractor().extract(env.config.data_dir / "nope.pdf")
    assert excinfo.value.error_class is ErrorClass.INTEGRITY


# -- 接线细节：config 驱动装配 / 未登记抽取器 / 删除护栏 -----------------------------------


def test_grobid_runtime_is_built_lazily_from_config(env: PipelineEnv) -> None:
    """`[extract] grobid_url` 非空 ⇒ 惰性构造并缓存到 `ctx.grobid`（先例＝unpaywall_adapter）。

    构造本身不发请求；`rate_limiter=None`（本机服务不注册限速桶）。为空则恒 None——
    **默认形态，不是降级**。
    """
    ctx = env.make_runner().ctx
    assert stages._grobid_runtime(ctx) is None  # 未配置：默认关闭

    object.__setattr__(ctx.config, "grobid_url", "http://localhost:8070/")
    object.__setattr__(ctx.config, "grobid_timeout_s", 12)
    runtime = stages._grobid_runtime(ctx)
    assert runtime is not None and runtime.base_url == "http://localhost:8070/"
    assert ctx.grobid is runtime  # 缓存：整轮只构造一次
    assert stages._grobid_runtime(ctx) is runtime
    runtime.client.close()


def test_unregistered_extractor_row_is_ranked_as_noop_with_a_warning(env: PipelineEnv) -> None:
    """未登记的 extractor 名 → rank 与 noop 同档并 WARN：**不得压制已登记的真实抽取器**。"""
    asset_id, paper_id = seed_fetched_pdf(env, make_text_pdf(BODY))
    env.db.execute(
        "INSERT INTO fulltext (paper_id, extractor, extractor_ver, text_path, char_count, "
        "lang, extracted_at, state) VALUES (?,?,?,?,?,?,?,?)",
        (paper_id, "future_ocr", "9.9.9", None, 99_999, None, "2026-01-01T00:00:00Z", "extracted"),
    )
    run_extract(env, asset_id)
    row = fulltext(env, paper_id)
    assert row["extractor"] == "pypdf" and row["state"] == STATE_EXTRACTED
    assert '"reason": "unknown_extractor"' in log_text(env)


def test_prune_guard_never_deletes_outside_the_fulltext_root(env: PipelineEnv) -> None:
    """删旧产物带路径护栏：`text_path` 是库里的数据，绝不据其删 `data_dir/fulltext/` 之外。"""
    outsider = env.config.data_dir / "pdf" / "precious.pdf"
    outsider.parent.mkdir(parents=True, exist_ok=True)
    outsider.write_bytes(b"%PDF-keep-me")

    asset_id, paper_id = seed_fetched_pdf(env, make_text_pdf(BODY))
    env.db.execute(
        "INSERT INTO fulltext (paper_id, extractor, extractor_ver, text_path, char_count, "
        "lang, extracted_at, state, text_sha256) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            paper_id,
            "pypdf",
            "0.0.1",
            "pdf/precious.pdf",
            1,
            None,
            "2026-01-01T00:00:00Z",
            STATE_EXTRACTED,
            None,
        ),
    )
    run_extract(env, asset_id)
    assert outsider.is_file(), "护栏失效：删到了 fulltext/ 之外的文件"


def test_part_file_is_cleaned_up_when_the_write_fails(
    env: PipelineEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """写产物失败 ⇒ `.part` 被 abort 清理、不落位、无 fulltext 行（无副作用叠加）。"""
    asset_id, paper_id = seed_fetched_pdf(env, make_text_pdf(BODY))

    def boom(self: object, chunks: object) -> tuple[int, str]:
        raise OSError("disk full")

    monkeypatch.setattr(stages.PartFileIO, "write_stream", boom)
    assert run_extract(env, asset_id).failed == 1
    assert artifacts(env) == []
    assert list((env.config.data_dir / "tmp").glob("*.part")) == []
    assert env.db.query("SELECT * FROM fulltext WHERE paper_id = ?", (paper_id,)) == []


def test_per_document_connection_failure_is_remembered_for_the_run(env: PipelineEnv) -> None:
    """逐篇连接失败/重置 ⇒ 与「探活失败」同类：整轮降级并记忆（服务中途被 kill 的真实形态）。

    探活只证明**那一刻**在线——本机 GROBID 常跑在会被随手关掉的容器里。
    """

    def process(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("container stopped")

    runtime = make_runtime(alive_handler(process))
    asset_id, paper_id = seed_fetched_pdf(env, make_text_pdf(BODY))
    report = run_extract(env, asset_id, grobid=runtime)
    assert report.failed == 0
    assert runtime.disabled is True
    assert fulltext(env, paper_id)["extractor"] == "pypdf"
    assert '"reason": "grobid_unreachable"' in log_text(env)
