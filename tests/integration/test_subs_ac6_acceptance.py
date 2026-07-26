"""AC-6 离线端到端验收（Phase 6 T9；`docs/testing/acceptance-criteria.md` AC-6.1~6.4）。

本文件是四条 AC-6 判据里**既有 e2e/unit 覆盖之外**的补充载体——`test_subs_watch_e2e.py`
（T5 DoD）与 `test_subs_guard.py`/`test_subs_report.py`（T3/T6 DoD）已经承载了大量回归，
本文件不重复它们，只补齐 T9 任务卡明确要求、既有测试尚未覆盖的判据切面：

- AC-6.1：7 天时间线推演骨架（`run_watch(now=...)` 逐日注入 + 单源投毒恢复 + 无遗漏/
  无重复 + 重叠窗回放 + 7 份日报/同日重跑覆盖）；以及三个源组合场景里"用真实 preset
  DSL 文件驱动"的两个（arxiv+openalex 同篇、nber RSS）——crossref 多 issn fan-out 场景
  没有任何一个 9 preset 声明 crossref，故沿用既有 `test_subs_watch_e2e.py::
  test_batch_dedupe_crossref_two_issns_hitting_the_same_doi`（已走真实 DSL 解析器）
  为载体，本文件不重复。
- AC-6.2：端到端补充——真实 `run_watch` 熔断 → `RunSummary.distribution` →
  `write_daily_report` 落盘，确认**落盘文件本身**含可操作（点名具体来源/分类）的收窄
  建议文本；护栏/收窄建议句的生成正确性本身已由 `test_subs_guard.py`/
  `test_subs_report.py` 单测穷尽，本文件不重复，只补"三段真的被串起来了"这一环。
- AC-6.3：SSRN 无关键词下推场景——用独立赋值的"代理人工浏览基准"标签（非从驱动过滤器
  的同一信号反推，避免 post-phase5-audit 曾指出的"自比恒 100%"重言式）与本地过滤
  （`ssrn.topic_filter`）实际产出的清单比对，一致率 ≥95%。
- AC-6.4：同一 DSL 对"下推+本地补偿"与"全量本地过滤"两条独立构造的语料路径断言
  结果集相等（按 identifier 集合判定，不比 `matched_rules` 标签集——T3 审查 P2#6）。

零网络：`_TimelineFetcher`/`_StubFetcher` 程序内生成语料；nber 场景经
`httpx.MockTransport` 回放既有 fixture（同 `test_subs_watch_e2e.py` 先例）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
import yaml

from helpers.nber_fixtures import fixture_bytes
from paper_crawler.adapters.ssrn.parse import TOPIC_FIELD_META_KEY
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo, SubscriptionRepo
from paper_crawler.subs.compile import compile_subscription
from paper_crawler.subs.filter import filter_papers
from paper_crawler.subs.model import Subscription, load_subscription_file, parse_subscription
from paper_crawler.subs.types import RunSummary, WatchOutcome, is_source_scoped_predicate
from paper_crawler.subs.watch import (
    RoutingFetcher,
    SourceRequest,
    WatchContext,
    daily_report_path,
    load_subscriptions,
    run_watch,
    write_daily_report,
)
from paper_crawler.types import PaperStub, VenueNames, VenueSpec

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PRESETS_DIR = _REPO_ROOT / "subscriptions" / "presets"

DAY = date(2026, 7, 26)


# ---------------------------------------------------------------------------
# 共享装配（同 `test_subs_watch_e2e.py::_Env`/`_StubFetcher` 先例，独立复制不跨文件导入
# ——本仓库既有惯例：每个测试文件的 helper 自成一体，见 test_cli_subs_watch.py 同类重复）
# ---------------------------------------------------------------------------


@dataclass
class _Env:
    db: Database
    repo: Repo
    subs_repo: SubscriptionRepo
    subs_dir: Path
    report_root: Path

    def papers(self) -> int:
        return int(self.db.query("SELECT COUNT(*) AS n FROM paper")[0]["n"])

    def context(self, *, fetcher: object) -> WatchContext:
        return WatchContext(
            db=self.db,
            repo=self.repo,
            subs_repo=self.subs_repo,
            fetcher=fetcher,  # type: ignore[arg-type]
            report_root=self.report_root,
        )


@pytest.fixture
def env(tmp_path: Path) -> _Env:
    database = Database(tmp_path / "ac6.sqlite")
    database.migrate()
    subs_dir = tmp_path / "subscriptions"
    subs_dir.mkdir()
    result = _Env(
        db=database,
        repo=Repo(database),
        subs_repo=SubscriptionRepo(database),
        subs_dir=subs_dir,
        report_root=tmp_path / "reports",
    )
    yield result
    database.close()


def _write_subscription(
    directory: Path,
    name: str,
    *,
    sources: dict[str, object],
    filters: dict[str, object] | None = None,
    actions: dict[str, object] | None = None,
    guard: dict[str, object] | None = None,
) -> Path:
    doc: dict[str, object] = {
        "name": name,
        "sources": sources,
        "actions": actions if actions is not None else {"ingest": "metadata"},
        "guard": guard if guard is not None else {"max_new_per_run": 200},
    }
    if filters is not None:
        doc["filters"] = filters
    path = directory / f"{name}.yaml"
    path.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return path


def _load(env: _Env, name: str, **kwargs: object) -> Subscription:
    """写盘 + 走真实 `load_subscriptions`（同时 upsert 入库，满足 FK 前提）。"""
    _write_subscription(env.subs_dir, name, **kwargs)  # type: ignore[arg-type]
    return load_subscriptions(env.subs_dir, env.subs_repo)[0]


def _stub(
    title: str, doi: str, *, year: int | None = 2025, meta: tuple[tuple[str, str], ...] = ()
) -> PaperStub:
    return PaperStub(title=title, identifiers=(("doi", doi),), year=year, meta=meta)


class _StubFetcher:
    """可控语料的 `SourceFetcher`：按**源**给定固定 stub 列表，并记录收到的请求。

    "按源"而非"按请求"：fan-out 的源（arxiv 多分类 / crossref 多 issn / nber 多 program）
    会拿到同一份语料若干遍——那正是批内去重要挡住的形状，故此处不按请求裁语料。
    `requests` 供请求面断言（同 `test_subs_watch_e2e._StubFetcher` 先例）。
    """

    def __init__(self, corpus: dict[str, list[PaperStub]]) -> None:
        self.corpus = corpus
        self.requests: list[SourceRequest] = []

    def fetch(self, request: SourceRequest) -> list[PaperStub]:
        self.requests.append(request)
        return list(self.corpus.get(request.source, []))


def _wm_date(env: _Env, name: str, source: str) -> str | None:
    """读某源 watermark 的日期水位（date_cursor 策略专属字段）；未推进过 → None。"""
    sources = env.subs_repo.read_watermark(name).get("sources", {})
    entry = sources.get(source)  # type: ignore[union-attr]
    return None if entry is None else str(entry["date"])  # type: ignore[index]


# ===========================================================================
# AC-6.1 判据 1-4 + 6：7 天时间线骨架 + 单源投毒恢复 + 无遗漏/无重复 + 重叠窗回放
#                       + 每日日报生成/同日重跑覆盖
# ===========================================================================

TIMELINE_DAYS: tuple[date, ...] = tuple(date(2026, 7, 20) + timedelta(days=i) for i in range(7))
POISON_DAY = TIMELINE_DAYS[3]  # 2026-07-23：crossref 当日投毒失败


def _cf_stub(day: date, slot: str) -> PaperStub:
    iso = day.isoformat()
    return PaperStub(
        title=f"Crossref Timeline Paper {iso}-{slot}",
        identifiers=(("doi", f"10.1/ac6-timeline-cf-{iso}-{slot}"),),
        year=day.year,
        pub_date=iso,
    )


def _oa_stub(day: date) -> PaperStub:
    iso = day.isoformat()
    return PaperStub(
        title=f"OpenAlex Timeline Paper {iso}",
        identifiers=(("doi", f"10.1/ac6-timeline-oa-{iso}"),),
        year=day.year,
        pub_date=iso,
    )


def _build_timeline_corpus() -> dict[str, list[PaperStub]]:
    """crossref 每日 2 篇（overlap_days=2）+ openalex 每日 1 篇（overlap_days=0）。

    两源均为 `DateCursor` 策略、`SourceRequest.since` 干净可读（区别于 arxiv——其窗口
    并入 `search_query` 字符串，`since` 恒 None，不适合本测试直接断言窗口下界）。
    """
    return {
        "crossref": [_cf_stub(day, slot) for day in TIMELINE_DAYS for slot in ("a", "b")],
        "openalex": [_oa_stub(day) for day in TIMELINE_DAYS],
    }


class _TimelineFetcher:
    """驱动七日推演的语料源：按 `pub_date` 累积可见（"今天"之前尚未发生的不吐出）+
    可对 `(source, day)` 精确投毒（模拟单源当日故障）。

    `since` 为空视为无下界；`pub_date` 缺失的条目本类不产出（语料全部显式带
    `pub_date`，故不涉及 watch.py "缺日期保留"分支，那条分支另有 e2e 覆盖）。
    """

    def __init__(
        self, corpus: dict[str, list[PaperStub]], *, poison: dict[str, date], today: date
    ) -> None:
        self.corpus = corpus
        self.poison = poison
        self.today = today
        self.requests: list[SourceRequest] = []

    def fetch(self, request: SourceRequest) -> list[PaperStub]:
        self.requests.append(request)
        if self.poison.get(request.source) == self.today:
            raise CrawlerError(
                ErrorClass.TRANSIENT, f"{request.source} 当日投毒失败（模拟单源故障注入）"
            )
        since = request.since
        today_iso = self.today.isoformat()
        return [
            stub
            for stub in self.corpus.get(request.source, [])
            if stub.pub_date is not None
            and stub.pub_date <= today_iso
            and (since is None or stub.pub_date >= since)
        ]


def test_ac6_1_seven_day_timeline_no_omission_no_duplication_overlap_replay(env: _Env) -> None:
    """AC-6.1 判据 1/2/3/4（T5 审查产出的 6 条判据最小充分集之核心四条）+ 判据 6 部分。

    骨架（判据 1）：`run_watch(now=...)` 逐日注入 2026-07-20..07-26，`_TimelineFetcher`
    按 pub_date 累积吐语料。crossref 在 2026-07-23 单源投毒失败（判据 2 的"必须含一日
    单源投毒失败"）：断言该源水位当日停住、次日窗自然变宽把漏收的那天追回、7 日终态
    entries 并集仍等于语料全集（无遗漏）。判据 3：paper 行数==语料去重基数，且全部
    entries 的 paper_id/标题互不重复。判据 4：crossref 的 overlap_days=2 在一个**非投毒**
    的常规日（07-22）同样把窗下界回退 2 天、老语料被二次拉回，但对库去重挡住——当日
    新增清单里零重复。判据 6：7 份 daily-*.md 各自生成 + 对最后一天重跑验证同日覆盖。
    """
    corpus = _build_timeline_corpus()
    expected_dois = {stub.identifiers[0][1] for stubs in corpus.values() for stub in stubs}
    assert len(expected_dois) == 21  # 14 crossref + 7 openalex，语料去重基数

    fetcher = _TimelineFetcher(corpus, poison={"crossref": POISON_DAY}, today=TIMELINE_DAYS[0])
    subscription = _load(
        env,
        "ac6-timeline",
        sources={
            "crossref": {"issns": ["0304-405X"]},
            "openalex": {"concepts": ["C41008148"], "from_source_types": ["preprint"]},
        },
    )
    context = env.context(fetcher=fetcher)

    summaries: list[RunSummary] = []
    watermark_dates: list[str | None] = []
    for day in TIMELINE_DAYS:
        fetcher.today = day
        path = daily_report_path(day, root=env.report_root)
        summary = run_watch(context, subscription, now=day, report_path=str(path))
        write_daily_report([summary], path, day=day)
        summaries.append(summary)
        watermark_dates.append(_wm_date(env, subscription.name, "crossref"))

    # --- 判据 1：骨架 -------------------------------------------------------
    assert len(summaries) == 7
    assert {entry.source for s in summaries for entry in s.entries} <= {"crossref", "openalex"}

    # --- 判据 2：无遗漏（含单源投毒恢复）------------------------------------
    all_entries = [entry for s in summaries for entry in s.entries]
    seen_dois = {entry.url.removeprefix("https://doi.org/") for entry in all_entries}
    assert seen_dois == expected_dois  # 7 日 entries 并集 == 语料全集，无遗漏

    poison_index = TIMELINE_DAYS.index(POISON_DAY)
    poison_summary = summaries[poison_index]
    assert poison_summary.outcome is WatchOutcome.OK  # openalex 成功 → 不整体判 FAILED
    assert [failure.source for failure in poison_summary.failures] == ["crossref"]
    poison_day_titles = {entry.title for entry in poison_summary.entries}
    assert f"Crossref Timeline Paper {POISON_DAY.isoformat()}-a" not in poison_day_titles
    assert f"Crossref Timeline Paper {POISON_DAY.isoformat()}-b" not in poison_day_titles
    assert f"OpenAlex Timeline Paper {POISON_DAY.isoformat()}" in poison_day_titles  # 未受牵连

    # 分源提交语义：投毒当日 crossref 水位与前一日一致（未推进，未被"部分成功"污染）。
    assert watermark_dates[poison_index] == watermark_dates[poison_index - 1]

    # 次日窗变宽补回：投毒日的两篇被追回，当日新语料同样正常收到，水位恢复推进。
    recovery_index = poison_index + 1
    recovery_day = TIMELINE_DAYS[recovery_index]
    recovery_titles = {entry.title for entry in summaries[recovery_index].entries}
    assert f"Crossref Timeline Paper {POISON_DAY.isoformat()}-a" in recovery_titles
    assert f"Crossref Timeline Paper {POISON_DAY.isoformat()}-b" in recovery_titles
    assert f"Crossref Timeline Paper {recovery_day.isoformat()}-a" in recovery_titles
    assert f"Crossref Timeline Paper {recovery_day.isoformat()}-b" in recovery_titles
    assert watermark_dates[recovery_index] == recovery_day.isoformat()

    # --- 判据 3：无重复 ------------------------------------------------------
    assert env.papers() == len(expected_dois)  # paper 行数 == 语料去重基数
    all_paper_ids = [entry.paper_id for entry in all_entries]
    assert len(all_paper_ids) == len(set(all_paper_ids))  # 全部 entries 的 paper_id 互不重复
    assert all(all_paper_ids)  # 均非空（均已入库，P2#3 的 dry-run/熔断恒零场景不适用本测试）
    all_titles = [entry.title for entry in all_entries]
    assert len(all_titles) == len(set(all_titles))  # 标题也互不重复（双重锁，P1-A 回归）

    # --- 判据 4：重叠窗回放（常规日 2026-07-22，与投毒恢复机制无关）--------
    regular_index = 2
    regular_day = TIMELINE_DAYS[regular_index]
    crossref_requests = [r for r in fetcher.requests if r.source == "crossref"]
    assert len(crossref_requests) == 7  # 每日恰 1 条 crossref 请求（单 issn，无 fan-out）
    prior_watermark = watermark_dates[regular_index - 1]
    assert prior_watermark is not None
    expected_since = (date.fromisoformat(prior_watermark) - timedelta(days=2)).isoformat()
    assert crossref_requests[regular_index].since == expected_since  # 窗下界回退 overlap_days(2)
    # 老语料（07-20/07-21）确实被重叠窗二次拉回，但当日"新增清单"只有 07-22 两篇——
    # 对库去重挡住重复，同篇二拉零重复入库、日报零重复。
    regular_titles = {
        entry.title for entry in summaries[regular_index].entries if entry.source == "crossref"
    }
    assert regular_titles == {
        f"Crossref Timeline Paper {regular_day.isoformat()}-a",
        f"Crossref Timeline Paper {regular_day.isoformat()}-b",
    }

    # --- 判据 6（部分）：7 份 daily-*.md 各自生成 ---------------------------
    report_files = sorted(env.report_root.glob("daily-*.md"))
    expected_names = [f"daily-{day.isoformat()}.md" for day in TIMELINE_DAYS]
    assert [f.name for f in report_files] == expected_names

    # 同日重跑覆盖：对最后一天再跑一次——水位已推进到当天，本轮零新增，落盘内容随之
    # 更新（而非维持首次的非零新增内容，也非追加）。
    last_day = TIMELINE_DAYS[-1]
    last_path = daily_report_path(last_day, root=env.report_root)
    original_text = last_path.read_text(encoding="utf-8")
    fetcher.today = last_day
    rerun_summary = run_watch(context, subscription, now=last_day, report_path=str(last_path))
    assert rerun_summary.new_count == 0
    rerun_text = write_daily_report([rerun_summary], last_path, day=last_day)
    assert last_path.read_text(encoding="utf-8") == rerun_text
    assert rerun_text != original_text  # 内容确实随重跑更新（覆盖生效，非残留/追加）


# ===========================================================================
# AC-6.1 判据 5：源组合三场景——真实 preset DSL 文件驱动（两个；第三个见文件头注）
# ===========================================================================


def test_ac6_1_scenario_arxiv_openalex_same_paper_dedup_via_real_llm_agents_preset(
    env: _Env,
) -> None:
    """判据 5 之一：真实 `subscriptions/presets/llm-agents.yaml`（design/09 §4）驱动
    arxiv + openalex 同篇（同 DOI）批内去重，两侧标题各自独立满足该预置真实的
    `title_regex_any`/`exclude_regex`/`min_year` 过滤（非绕过过滤的合成捷径）。
    """
    subscription = load_subscription_file(_PRESETS_DIR / "llm-agents.yaml")
    assert subscription.name == "llm-agents"  # 确认加载的正是真实预置文件
    env.subs_repo.upsert(subscription)  # 满足 subscription_run 的 FK 前提

    shared_doi = "10.48550/arxiv.2601.99999"
    arxiv_view = PaperStub(
        title="Large Language Model Agents Learn Tool Use",
        identifiers=(("doi", shared_doi),),
        year=2025,
    )
    openalex_view = PaperStub(
        title="Studying Large Language Model Agents That Use External Tools",
        identifiers=(("doi", shared_doi),),
        year=2025,
    )
    fetcher = _StubFetcher({"arxiv": [arxiv_view], "openalex": [openalex_view]})

    summary = run_watch(env.context(fetcher=fetcher), subscription, now=DAY)

    # arxiv 自 `fix/arxiv-category-fanout` 起按分类逐条 fan-out：该预置声明 4 个分类 →
    # 4 条独立请求，`_StubFetcher` 按**源**给语料（不按请求）故同一份 stub 被吐 4 遍。
    # 判定强度不变、只是如实反映新的请求面——净新增/去重/入库三项断言逐字保留。
    arxiv_selector = subscription.selector_for("arxiv")
    assert arxiv_selector is not None
    assert arxiv_selector.categories == ("cs.AI", "cs.LG", "cs.CL", "cs.MA")  # 真实预置
    arxiv_requests = [r for r in fetcher.requests if r.source == "arxiv"]
    assert len(arxiv_requests) == len(arxiv_selector.categories)  # 一分类一请求
    assert [r.params[0] for r in arxiv_requests] == [
        ("arxiv_category", category) for category in arxiv_selector.categories
    ]
    assert summary.seen_count == len(arxiv_selector.categories) + 1  # 4 份 arxiv + 1 份 openalex
    assert summary.new_count == 1  # 同 DOI 批内去重折叠为 1 篇（含 fan-out 的同源重复）
    assert summary.ingested_count == 1
    (survivor,) = summary.entries
    assert survivor.source == "arxiv"  # 声明序（arxiv 先于 openalex）在前者胜
    assert "merged_from:openalex" in survivor.matched_rules
    assert env.papers() == 1


def test_ac6_1_scenario_nber_rss_fixture_driven_via_real_corporate_finance_preset(
    env: _Env,
) -> None:
    """判据 5 之二：真实 `subscriptions/presets/corporate-finance.yaml`（nber
    `programs: [CF]`）驱动 program RSS 增量通道，回放既有 `06_rss_program_cf_synth.xml`
    fixture（同 `test_subs_watch_e2e.py` 先例）——同时验证该预置真实的
    `title_regex_any` 词族确实对 fixture 的合成标题生效（含一条如实被过滤掉）。
    """
    subscription = load_subscription_file(_PRESETS_DIR / "corporate-finance.yaml")
    assert subscription.name == "corporate-finance"
    assert subscription.selector_for("nber") is not None
    assert subscription.selector_for("nber").programs == ("CF",)  # 与 fixture 的 newcf.xml 对应
    env.subs_repo.upsert(subscription)

    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, content=fixture_bytes("06_rss_program_cf_synth.xml"))

    client = HttpClient(user_agent="PaperCrawler/test", transport=httpx.MockTransport(handler))
    from paper_crawler.subs.watch import NberRssFetcher

    nber_fetcher = NberRssFetcher(client, now=DAY)
    # corporate-finance.yaml 同时声明 arxiv/ssrn/nber 三源；只喂 nber 走真实 RSS 通道，
    # 另两源用空语料 stub——arxiv/ssrn 各自的组合场景已有他处覆盖，本用例聚焦 nber。
    combined = RoutingFetcher({"nber": nber_fetcher}, _StubFetcher({}))

    summary = run_watch(env.context(fetcher=combined), subscription, now=DAY)

    assert urls == ["https://back.nber.org/rss/newcf.xml"]  # 真实 preset 的 program=CF 正确路由
    # fixture 3 item：①②命中 corporate-finance.yaml 的真实词族（"capital structure"/
    # "leverage"），③无任何词族命中——如实被过滤，证明关键词族对真实 fixture 内容生效
    # （非空判：若过滤器失灵放行一切，也会得到"3 条全收"这种表面正常但错误的结果）。
    titles = {entry.title for entry in summary.entries}
    assert titles == {
        "Synthetic Capital Structure Adjustment Speeds",
        "Synthetic Study of Board Composition and Leverage",
    }
    assert summary.new_count == 2
    assert summary.ingested_count == 2


# ===========================================================================
# AC-6.2 补充：端到端熔断 → 落盘日报文件含可操作收窄建议字面文本
# ===========================================================================


def test_ac6_2_truncation_report_file_contains_actionable_narrowing_suggestion(
    env: _Env,
) -> None:
    """AC-6.2 补充证据：真实 `run_watch` 熔断 → `RunSummary.distribution` →
    `write_daily_report` 落盘，**落盘文件本身**含可操作（点名具体来源/分类 + 百分比）
    的收窄建议文本，而非仅在孤立单测里验证 `guard.py`/`report.py` 各自的字符串生成。

    护栏计数判定与收窄建议生成算法本身已由 `test_subs_guard.py`（`OverloadReport.
    suggestion`）与 `test_subs_report.py`（`_narrowing_suggestion` 渲染字符串）分别
    穷尽单测；"熔断计数不被批内重复污染"已有 `test_subs_watch_e2e.py::
    test_batch_dedupe_prevents_a_spurious_truncation` 回归——三者列账，本用例不重复，
    只补三段被真实串联后的端到端证据。
    """
    corpus = {
        "crossref": [
            _stub(f"Overloaded Paper {i}", f"10.1/of-{i}", meta=(("categories", "cs.AI"),))
            for i in range(5)
        ]
    }
    fetcher = _StubFetcher(corpus)
    subscription = _load(
        env,
        "ac6-2-truncation",
        sources={"crossref": {"issns": ["0000-0000"]}},
        guard={"max_new_per_run": 3},
    )
    path = daily_report_path(DAY, root=env.report_root)

    summary = run_watch(env.context(fetcher=fetcher), subscription, now=DAY, report_path=str(path))
    text = write_daily_report([summary], path, day=DAY)

    assert summary.outcome is WatchOutcome.TRUNCATED
    assert path.read_text(encoding="utf-8") == text
    assert "请收窄查询条件后重试" in text  # 熔断段本身的可操作提示
    assert "收窄建议：优先考虑收窄" in text
    assert "来源 `crossref`" in text  # 点名具体来源，非空泛"请收窄"
    assert "分类 `cs.AI`" in text  # 点名具体分类
    assert "100.0%" in text  # 带具体占比数字（可操作性的量化依据）


# ===========================================================================
# AC-6.3：SSRN 无关键词下推场景——本地过滤清单 vs 代理人工浏览基准，一致率 ≥95%
# ===========================================================================

_ECON_FIN_A = "Economics, Econometrics and Finance"
_ECON_FIN_B = "Business, Management and Accounting"


@dataclass(frozen=True)
class _LabeledStub:
    """一条语料 + 独立赋予的"代理人工浏览基准"标签（与驱动过滤器的信号分离赋值）。"""

    stub: PaperStub
    proxy_human_econ_fin: bool


def _labeled(doi: str, title: str, field: str, *, proxy: bool) -> _LabeledStub:
    return _LabeledStub(
        stub=PaperStub(
            title=title,
            identifiers=(("doi", doi),),
            year=2025,
            meta=((TOPIC_FIELD_META_KEY, field),),
        ),
        proxy_human_econ_fin=proxy,
    )


def _build_ac63_corpus() -> list[_LabeledStub]:
    """30 条 crossref 形态语料：econ/fin 与非 econ/fin 混合 + 1 例刻意分歧的"难例"。

    `proxy_human_econ_fin` 是本测试**独立**赋予的代理标签（模拟"人工浏览会怎么判"），
    与驱动 `ssrn.topic_filter` 的 `openalex_field` 信号是两条独立赋值的数据列——刻意
    构造 1 例二者不一致（OpenAlex 粗粒度顶层分类把一篇人类会认作 econ/fin 的交叉学科
    论文归到 "Decision Sciences"，不在 `ECON_FIN_FIELDS` 内），证明该指标不是"同一
    信号 vs 自身"的重言式（呼应 post-phase5-audit 对 AC-5.1a 原判据"自比恒 100%"的
    废止理由）。真人工基准（而非本测试构造的代理）defer 运行期实测，如实标注。
    """
    items: list[_LabeledStub] = []
    for i in range(10):
        items.append(
            _labeled(f"10.2139/ssrn.{1000 + i}", f"Econ Fin Paper {i}", _ECON_FIN_A, proxy=True)
        )
    for i in range(9):
        items.append(
            _labeled(f"10.2139/ssrn.{2000 + i}", f"Business Paper {i}", _ECON_FIN_B, proxy=True)
        )
    non_econ_fields = ("Computer Science", "Physics and Astronomy", "Medicine")
    for i in range(10):
        field = non_econ_fields[i % len(non_econ_fields)]
        doi = f"10.2139/ssrn.{3000 + i}"
        items.append(_labeled(doi, f"Unrelated Paper {i}", field, proxy=False))
    items.append(
        _labeled(
            "10.2139/ssrn.9001",
            "Behavioral Decision Making in Financial Markets",
            "Decision Sciences",
            proxy=True,
        )
    )
    return items


def test_ac6_3_ssrn_local_filter_matches_proxy_human_baseline_at_least_95_percent() -> None:
    """AC-6.3 离线代理口径：无关键词下推场景（订阅不声明 `filters:`，唯一收窄手段是
    `ssrn.topic_filter` 近似过滤）——本地过滤后清单与代理人工浏览基准一致率 ≥95%。
    """
    labeled = _build_ac63_corpus()
    ssrn_venue = VenueSpec(
        id="ssrn",
        kind="preprint_channel",
        names=VenueNames(full="SSRN"),
        field=["econ"],
        fulltext_source="ssrn",
        quirks={"topic_filter": "econ_fin"},  # 逐字对齐 venues/econ/ssrn.yaml 的声明
    )
    subscription = parse_subscription(
        {"name": "ac6-3-ssrn-proxy", "sources": {"ssrn": {"networks": ["FEN"]}}}
    )
    plan = compile_subscription(subscription, venues={"ssrn": ssrn_venue})
    step = plan.step_for("ssrn")
    assert step is not None
    scoped = tuple(name for name in step.local_predicates if is_source_scoped_predicate(name))
    assert scoped == ("ssrn.topic_filter",)  # 确认谓词确实被编译标记（DSL→compile 接线证据）

    stubs = [item.stub for item in labeled]
    kept = filter_papers(stubs, subscription.filters, extra_predicates=scoped)
    kept_dois = {item.stub.identifiers[0][1] for item in kept}

    agreements = sum(
        1
        for item in labeled
        if (item.stub.identifiers[0][1] in kept_dois) == item.proxy_human_econ_fin
    )
    rate = agreements / len(labeled)

    assert rate >= 0.95
    assert rate < 1.0  # 非重言式：确有刻意构造的分歧被如实计入分母（见语料构造注释）


# ===========================================================================
# AC-6.4：同一 DSL 的"全量本地过滤"与"下推+补偿过滤"结果集相等
# ===========================================================================

_AC64_TARGET_ISSN = "0304-405X"
_AC64_OTHER_ISSN = "0022-1082"


def _ac64_pair(idx: int, *, issn: str, title: str, year: int) -> PaperStub:
    return PaperStub(
        title=title, identifiers=(("doi", f"10.1/ac6-4-{idx}"),), year=year, meta=(("issn", issn),)
    )


def _build_ac64_corpus() -> list[PaperStub]:
    return [
        # ① 目标刊 + 标题命中 + 年份达标 → 两条路径都应保留（判据的"应收"锚点）。
        _ac64_pair(1, issn=_AC64_TARGET_ISSN, title="Asset Pricing Anomalies Revisited", year=2023),
        _ac64_pair(2, issn=_AC64_TARGET_ISSN, title="Risk Premia in Emerging Markets", year=2024),
        # ② 目标刊 + 标题不命中 → 两条路径都应剔除（title_regex_any 挡住）。
        _ac64_pair(3, issn=_AC64_TARGET_ISSN, title="Unrelated Topic in Finance", year=2023),
        # ③ 目标刊 + 命中 + 年份不达标 → 两条路径都应剔除（min_year 挡住）。
        _ac64_pair(4, issn=_AC64_TARGET_ISSN, title="Asset Pricing Before The Cutoff", year=2020),
        # ④ 目标刊 + 命中 exclude_regex（survey）→ 两条路径都应剔除。
        _ac64_pair(5, issn=_AC64_TARGET_ISSN, title="A Survey of Asset Pricing Models", year=2023),
        # ⑤ 非目标刊 + 内容完美命中——"下推"路径本就不会拉到它（源端已按 issn 过滤）；
        #   "全量本地"路径若不补一道 issn 成员检查会误收——两路径分岔的关键锚点。
        _ac64_pair(
            6, issn=_AC64_OTHER_ISSN, title="Asset Pricing Anomalies In Another Journal", year=2023
        ),
    ]


def test_ac6_4_full_local_filter_equals_pushdown_plus_compensation_result_set() -> None:
    """AC-6.4：同一 DSL 对 fixture 数据集"全量本地过滤"与"下推+补偿过滤"结果集相等。

    两条路径用**不同**的输入语料子集构造（而非对同一子集调用同一函数两遍这种平凡
    重言）：
    - "下推+补偿"：模拟源端已按 `issn` 完成下推（fetcher 只会吐目标刊语料）——语料
      预先按 issn 缩小，之后只需再跑 `filter_papers`；
    - "全量本地过滤"：假设该源无 issn 下推能力，全部语料原样喂给本地过滤，本地额外
      补一道"若只能本地判会怎么写"的 issn 成员检查。

    按**结果集**（identifier 集合）判定，不比 `matched_rules` 标签集——两路径下同一条
    幸存记录携带的命中规则标签可能因"issn 检查在哪一层完成"而不同，但这只是标签
    命名空间的分岔，不影响最终结果集是否一致（T3 审查 P2#6 提醒的判定口径）。
    """
    subscription = parse_subscription(
        {
            "name": "ac6-4-consistency",
            "sources": {"crossref": {"issns": [_AC64_TARGET_ISSN]}},
            "filters": {
                "title_regex_any": ["asset pricing", "risk premi"],
                "exclude_regex": ["survey"],
                "min_year": 2022,
            },
        }
    )
    plan = compile_subscription(subscription)
    step = plan.step_for("crossref")
    assert step is not None
    declared_issns = {value for name, value in step.pushdown if name == "issn"}
    assert declared_issns == {_AC64_TARGET_ISSN}
    scoped = tuple(name for name in step.local_predicates if is_source_scoped_predicate(name))
    assert scoped == ()  # crossref 无源专属补偿谓词——本场景分岔纯粹来自 issn 检查的层位

    corpus = _build_ac64_corpus()

    pushdown_corpus = [s for s in corpus if dict(s.meta)["issn"] in declared_issns]
    pushdown_kept = filter_papers(pushdown_corpus, subscription.filters, extra_predicates=scoped)

    full_local_kept = [
        item
        for item in filter_papers(corpus, subscription.filters, extra_predicates=scoped)
        if dict(item.stub.meta)["issn"] in declared_issns
    ]

    def identity_set(items: list) -> set:  # type: ignore[type-arg]
        return {item.stub.identifiers for item in items}

    pushdown_ids = identity_set(pushdown_kept)
    full_local_ids = identity_set(full_local_kept)
    assert pushdown_ids == full_local_ids
    # 非空判据：防止两边恒空的假阳性等集；同时锚定预期的"应收"集合（见语料构造注释①）。
    assert pushdown_ids == {(("doi", "10.1/ac6-4-1"),), (("doi", "10.1/ac6-4-2"),)}
