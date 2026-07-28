"""watch 端到端（Phase 6 T5 DoD）：mock_platform 载体 + 真 sqlite，四场景 + `--all`。

四场景 = plan §4 T5 DoD 字面：**正常增量 / 熔断 / dry-run / 零新增**。载体是
`mock_platform`（确定性语料、零网络），经 `AdapterFetcher` 的 DISCOVER→ENUMERATE 默认
路径驱动——即"复用各 adapter DISCOVER/ENUMERATE"这条接缝本身也在被测。订阅源用
`crossref`（DSL 四源之一）而 adapter 实物是 mock_platform：`AdapterFetcher` 按**源 id**
索引 adapter，把哪个实物挂在这个 id 上是装配期的事，正是这个接缝让离线端到端成立。

零网络：mock_platform 程序内生成语料，不触 socket（全局护栏 `tests/conftest.py` 兜底）。
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx
import pytest
import yaml

from helpers.nber_fixtures import fixture_bytes
from paper_crawler.adapters.mock_platform import MockPlatformAdapter
from paper_crawler.errors import CrawlerError, ErrorClass, SubscriptionInvalid
from paper_crawler.http import HttpClient
from paper_crawler.registry import VenueRegistry
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo, SubscriptionRepo
from paper_crawler.subs.model import Subscription
from paper_crawler.subs.types import RunSummary, WatchOutcome
from paper_crawler.subs.watch import (
    MERGED_SOURCE_RULE_PREFIX,
    SUBSCRIPTION_LEVEL_SOURCE,
    AdapterFetcher,
    NberRssFetcher,
    SourceRequest,
    WatchContext,
    daily_report_path,
    exit_code_for,
    load_subscriptions,
    resolve_subscription,
    run_watch,
    run_watch_all,
    write_daily_report,
)
from paper_crawler.tasks import TaskQueue
from paper_crawler.types import PaperStub, VenueNames, VenueSpec

DAY = date(2026, 7, 26)
CORPUS_SIZE = 6  # volumes 1 × issues 1 × papers 6（mock quirks，见 `_mock_venue`）

# mock_platform 的语料配置：一卷一期六篇，seed 固定 → 同输入同输出（其模块 docstring）。
_MOCK_QUIRKS: dict[str, object] = {
    "volumes": 1,
    "issues_per_volume": 1,
    "papers_per_issue": CORPUS_SIZE,
    "seed": 42,
}


def _mock_venue(
    venue_id: str = "mock_journal", *, fulltext_source: str = "mock_platform"
) -> VenueSpec:
    return VenueSpec(
        id=venue_id,
        kind="journal",
        names=VenueNames(full="Mock Journal"),
        field=["cs_ai"],
        identifiers={"issn": ["0000-0000"]},
        metadata_source=fulltext_source,
        fulltext_source=fulltext_source,
        quirks=dict(_MOCK_QUIRKS),
    )


@dataclass
class _Env:
    """一次测试的隔离装配（真 sqlite + 临时订阅目录）。"""

    db: Database
    repo: Repo
    subs_repo: SubscriptionRepo
    queue: TaskQueue
    subs_dir: Path
    report_root: Path

    def context(
        self,
        *,
        registry: VenueRegistry | None = None,
        fetcher: object | None = None,
        venues: dict[str, VenueSpec] | None = None,
    ) -> WatchContext:
        source_venues = venues if venues is not None else {"crossref": _mock_venue()}
        return WatchContext(
            db=self.db,
            repo=self.repo,
            subs_repo=self.subs_repo,
            fetcher=fetcher  # type: ignore[arg-type]
            or AdapterFetcher({"crossref": MockPlatformAdapter()}, venues=source_venues),
            registry=registry,
            queue=self.queue,
            venues=source_venues,
            report_root=self.report_root,
        )

    def papers(self) -> int:
        return int(self.db.query("SELECT COUNT(*) AS n FROM paper")[0]["n"])

    def runs(self, name: str) -> list[dict[str, object]]:
        return [dict(row) for row in self.subs_repo.runs(name)]


@pytest.fixture
def env(tmp_path: Path) -> Iterator[_Env]:
    database = Database(tmp_path / "watch.sqlite")
    database.migrate()
    subs_dir = tmp_path / "subscriptions"
    subs_dir.mkdir()
    yield _Env(
        db=database,
        repo=Repo(database),
        subs_repo=SubscriptionRepo(database),
        queue=TaskQueue(database),
        subs_dir=subs_dir,
        report_root=tmp_path / "reports",
    )
    database.close()


def _write_subscription(
    directory: Path,
    name: str = "mock-watch",
    *,
    sources: dict[str, object] | None = None,
    filters: dict[str, object] | None = None,
    actions: dict[str, object] | None = None,
    guard: dict[str, object] | None = None,
) -> Path:
    doc: dict[str, object] = {
        "name": name,
        "sources": sources if sources is not None else {"crossref": {"issns": ["0000-0000"]}},
        "actions": actions if actions is not None else {"ingest": "metadata"},
        "guard": guard if guard is not None else {"max_new_per_run": 200},
    }
    if filters is not None:
        doc["filters"] = filters
    path = directory / f"{name}.yaml"
    path.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return path


def _load_one(env: _Env, **kwargs: object) -> Subscription:
    _write_subscription(env.subs_dir, **kwargs)  # type: ignore[arg-type]
    return load_subscriptions(env.subs_dir, env.subs_repo)[0]


# ---------------------------------------------------------------------------
# 场景一：正常增量
# ---------------------------------------------------------------------------


def test_normal_increment_ingests_advances_watermark_and_records_run(env: _Env) -> None:
    subscription = _load_one(env)
    path = daily_report_path(DAY, root=env.report_root)

    summary = run_watch(env.context(), subscription, now=DAY, report_path=str(path))

    assert summary.outcome is WatchOutcome.OK
    assert summary.seen_count == CORPUS_SIZE
    assert summary.new_count == CORPUS_SIZE
    assert summary.ingested_count == CORPUS_SIZE
    assert summary.library_total == CORPUS_SIZE
    assert env.papers() == CORPUS_SIZE
    # 每条 entry 拿到入库后的内部 id（`ReportEntry.paper_id` 契约）。
    assert all(entry.paper_id for entry in summary.entries)
    assert {entry.source for entry in summary.entries} == {"crossref"}
    # watermark 已提交且带 schema_ver（T4 序列化契约）。
    stored = env.subs_repo.read_watermark(subscription.name)
    assert stored["schema_ver"] == 1
    assert "crossref" in stored["sources"]  # type: ignore[operator]
    # run 记录落库且 report_path 已填（record_run 是 INSERT-only，路径须先于它算好）。
    (run_row,) = env.runs(subscription.name)
    assert run_row["new_count"] == CORPUS_SIZE
    assert run_row["truncated"] == 0
    assert run_row["report_path"] == str(path)
    assert exit_code_for([summary]) == 0


def test_normal_increment_writes_the_daily_report_file(env: _Env) -> None:
    subscription = _load_one(env)
    path = daily_report_path(DAY, root=env.report_root)
    summary = run_watch(env.context(), subscription, now=DAY, report_path=str(path))

    text = write_daily_report([summary], path, day=DAY)

    assert path.is_file()
    assert path.read_text(encoding="utf-8") == text
    assert "# 日报 — 2026-07-26" in text
    assert subscription.name in text


# ---------------------------------------------------------------------------
# 场景二：熔断（AC-6.2：正确熔断、零入库、过载报告含分布与建议）
# ---------------------------------------------------------------------------


def test_truncation_blocks_ingest_but_still_records_the_run(env: _Env) -> None:
    subscription = _load_one(env, guard={"max_new_per_run": 2})
    path = daily_report_path(DAY, root=env.report_root)

    summary = run_watch(env.context(), subscription, now=DAY, report_path=str(path))

    assert summary.outcome is WatchOutcome.TRUNCATED
    assert summary.truncated is True
    assert summary.new_count == CORPUS_SIZE
    assert summary.ingested_count == 0
    assert summary.fetched_count == 0
    assert env.papers() == 0
    # 分布三元组带 axis 标记（plan §4 T5 裁决⑥）；来源轴必有，分类轴视源侧信号而定。
    assert ("source", "crossref", CORPUS_SIZE) in summary.distribution
    assert {axis for axis, _, _ in summary.distribution} <= {"source", "category"}
    assert summary.narrowing_hints == ()  # 收窄句归 T6 现算，T5 恒留空
    # 熔断仍落 run 记录（truncated=1）且计数如实（P3：不是空壳行），但 watermark 不推进。
    (run_row,) = env.runs(subscription.name)
    assert run_row["truncated"] == 1
    assert run_row["new_count"] == CORPUS_SIZE  # 记的是"本会新增多少"，不是 0
    assert run_row["fetched_count"] == 0  # 零入库 → 零派生
    assert run_row["report_path"] == str(path)
    assert env.subs_repo.read_watermark(subscription.name) == {}
    # `last_run_at` 与 run 记录同口径："跑过就算跑过"（熔断也 touch，审查 P2③）。
    assert (
        env.db.query("SELECT last_run_at FROM subscription WHERE name = ?", (subscription.name,))[
            0
        ]["last_run_at"]
        == summary.started_at
    )
    assert exit_code_for([summary]) == 3


def test_truncation_at_exactly_the_limit_does_not_trigger(env: _Env) -> None:
    """ "至多 N 篇"语义：等于阈值不熔断（T3 `is_truncated` 的边界，端到端复验）。"""
    subscription = _load_one(env, guard={"max_new_per_run": CORPUS_SIZE})
    summary = run_watch(env.context(), subscription, now=DAY)
    assert summary.outcome is WatchOutcome.OK
    assert summary.ingested_count == CORPUS_SIZE


# ---------------------------------------------------------------------------
# 场景三：dry-run（只报数，但完整消费各源流）
# ---------------------------------------------------------------------------


def test_dry_run_reports_counts_without_touching_anything(env: _Env) -> None:
    subscription = _load_one(env)
    path = daily_report_path(DAY, root=env.report_root)

    summary = run_watch(env.context(), subscription, dry_run=True, now=DAY, report_path=str(path))

    assert summary.dry_run is True
    assert summary.outcome is WatchOutcome.OK
    # 完整消费的证据：候选/新增计数照常算出来（惰性生成器若被早退跳过，这里会是 0）。
    assert summary.seen_count == CORPUS_SIZE
    assert summary.new_count == CORPUS_SIZE
    # 四不做：不入库、不派生、不推 watermark、不写 run 记录。
    assert summary.ingested_count == 0
    assert summary.fetched_count == 0
    assert env.papers() == 0
    assert env.subs_repo.read_watermark(subscription.name) == {}
    assert env.runs(subscription.name) == []
    assert not path.exists()  # 日报只回显不落盘（落盘由调用方决定，dry-run 不调）


def test_dry_run_still_runs_guard_and_reports_truncation(env: _Env) -> None:
    """dry-run 与熔断正交：预览也要能提前告诉用户"这次会被拦下"（AC-6.2 的用法）。"""
    subscription = _load_one(env, guard={"max_new_per_run": 1})

    summary = run_watch(env.context(), subscription, dry_run=True, now=DAY)

    assert summary.outcome is WatchOutcome.TRUNCATED
    assert summary.dry_run is True
    assert summary.ingested_count == 0
    assert env.runs(subscription.name) == []  # dry-run 优先于"熔断也落记录"


def test_dry_run_surfaces_predicate_wiring_errors_instead_of_skipping_them(env: _Env) -> None:
    """未登记谓词在 dry-run 下同样炸——"上线前必跑 dry-run"才有意义（T7 教训）。"""

    class _BadFetcher:
        def fetch(self, request: SourceRequest) -> list[PaperStub]:
            del request
            return [PaperStub(title="x", identifiers=(("doi", "10.1/x"),))]

    subscription = _load_one(env)
    context = env.context(fetcher=_BadFetcher())
    # 直接构造一个带未登记源专属谓词的计划：经 filter_papers 的前置校验响亮报错。
    from dataclasses import replace as dataclass_replace

    from paper_crawler.subs import compile as compile_module

    original = compile_module.compile_subscription

    def _poisoned(sub: Subscription, **kwargs: object) -> object:
        plan = original(sub, **kwargs)  # type: ignore[arg-type]
        step = dataclass_replace(plan.steps[0], local_predicates=("crossref.nope",))
        return dataclass_replace(plan, steps=(step,))

    from paper_crawler.subs import watch as watch_module

    watch_module.compile_subscription = _poisoned  # type: ignore[assignment]
    try:
        with pytest.raises(ValueError, match="未登记的本地补偿谓词"):
            run_watch(context, subscription, dry_run=True, now=DAY)
    finally:
        watch_module.compile_subscription = original  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# 场景四：零新增（第二次运行全是库内已有）
# ---------------------------------------------------------------------------


def test_second_run_finds_nothing_new_and_still_records_the_run(env: _Env) -> None:
    subscription = _load_one(env)
    context = env.context()

    first = run_watch(context, subscription, now=DAY)
    second = run_watch(context, subscription, now=DAY)

    assert first.ingested_count == CORPUS_SIZE
    assert second.seen_count == CORPUS_SIZE  # 窗照拉（重叠窗必然重复，T4 纪律）
    assert second.new_count == 0  # 对库去重把它们全滤掉
    assert second.ingested_count == 0
    assert second.outcome is WatchOutcome.OK
    assert env.papers() == CORPUS_SIZE  # 零重复入库
    assert len(env.runs(subscription.name)) == 2
    assert exit_code_for([second]) == 0


def test_dedupe_can_be_switched_off(env: _Env) -> None:
    """`dedupe_against_library: false` = 用户显式要重复看——不去重，入库靠主键幂等兜底。"""
    subscription = _load_one(env, guard={"max_new_per_run": 200, "dedupe_against_library": False})
    context = env.context()

    run_watch(context, subscription, now=DAY)
    second = run_watch(context, subscription, now=DAY)

    assert second.new_count == CORPUS_SIZE
    assert env.papers() == CORPUS_SIZE  # identifier 主键保证零重复行


# ---------------------------------------------------------------------------
# `--all`：多订阅串行 + 合并一份日报
# ---------------------------------------------------------------------------


def test_watch_all_runs_serially_and_merges_one_daily_report(env: _Env) -> None:
    _write_subscription(env.subs_dir, "alpha")
    # beta 关掉对库去重：alpha 先跑并把整批语料入了库，否则 beta 会看到零新增而非熔断
    # ——串行语义本身的体现（后跑的订阅看到的是前一个已经改过的库）。
    _write_subscription(
        env.subs_dir, "beta", guard={"max_new_per_run": 1, "dedupe_against_library": False}
    )
    subscriptions = load_subscriptions(env.subs_dir, env.subs_repo)

    summaries, path = run_watch_all(env.context(), subscriptions, now=DAY)

    assert [summary.subscription for summary in summaries] == ["alpha", "beta"]
    assert [summary.outcome for summary in summaries] == [
        WatchOutcome.OK,
        WatchOutcome.TRUNCATED,
    ]
    # 一份合并日报，路径先算好、两条 run 记录都填了同一个值。
    assert path == daily_report_path(DAY, root=env.report_root)
    assert env.runs("alpha")[0]["report_path"] == str(path)
    assert env.runs("beta")[0]["report_path"] == str(path)
    text = write_daily_report(summaries, path, day=DAY)
    assert "## alpha" in text and "## beta" in text
    assert exit_code_for(summaries) == 3  # 无失败但有熔断


def test_watch_all_rejects_the_whole_batch_when_any_file_is_invalid(env: _Env) -> None:
    """plan §4 T5 裁决④：`--all` 遇任一坏订阅整体响亮拒载，报错带出错文件路径。"""
    _write_subscription(env.subs_dir, "good")
    bad = env.subs_dir / "bad.yaml"
    bad.write_text("name: bad\nsources: {arxiv: {catgories: [cs.AI]}}\n", encoding="utf-8")

    with pytest.raises(SubscriptionInvalid) as excinfo:
        load_subscriptions(env.subs_dir, env.subs_repo)

    assert str(bad) in str(excinfo.value)
    assert env.subs_repo.list_names() == []  # 坏文件排在 good 之前，整批未生效


def test_resolve_subscription_rejects_unknown_name(env: _Env) -> None:
    _load_one(env)
    with pytest.raises(CrawlerError) as excinfo:
        resolve_subscription("nope", env.subs_repo)
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert "mock-watch" in str(excinfo.value)  # 报错列出已登记的名字


def test_resolve_subscription_message_when_registry_is_empty(env: _Env) -> None:
    with pytest.raises(CrawlerError, match="一个订阅都没有登记"):
        resolve_subscription("nope", env.subs_repo)


# ---------------------------------------------------------------------------
# id 集合差分源（nber）：窗内先差分，再走后续链路
# ---------------------------------------------------------------------------


def test_id_set_diff_source_reports_nothing_new_on_the_second_run(env: _Env) -> None:
    venues = {"nber": _mock_venue()}
    context = env.context(
        fetcher=AdapterFetcher({"nber": MockPlatformAdapter()}, venues=venues), venues=venues
    )
    subscription = _load_one(env, sources={"nber": {"programs": ["AP"]}})

    first = run_watch(context, subscription, now=DAY)
    stored = env.subs_repo.read_watermark(subscription.name)
    second = run_watch(context, subscription, now=DAY)

    assert first.new_count == CORPUS_SIZE
    assert stored["sources"]["nber"]["kind"] == "id_set"  # type: ignore[index]
    assert len(stored["sources"]["nber"]["ids"]) == CORPUS_SIZE  # type: ignore[index]
    # 第二次：id 差分在**本地过滤之前**就把重叠部分摘掉了（seen 仍是整窗）。
    assert second.seen_count == CORPUS_SIZE
    assert second.new_count == 0


# ---------------------------------------------------------------------------
# 本地过滤 / 谓词分流 / 条目字段（用可控语料的 stub fetcher）
# ---------------------------------------------------------------------------


class _StubFetcher:
    """可控语料的 `SourceFetcher`：按源给定 stub，并记录收到的请求。"""

    def __init__(self, corpus: dict[str, list[PaperStub]]) -> None:
        self.corpus = corpus
        self.requests: list[SourceRequest] = []

    def fetch(self, request: SourceRequest) -> list[PaperStub]:
        self.requests.append(request)
        return list(self.corpus.get(request.source, []))


def _stub(
    title: str,
    doi: str,
    *,
    year: int | None = 2026,
    pub_date: str | None = None,
    meta: tuple[tuple[str, str], ...] = (),
) -> PaperStub:
    return PaperStub(
        title=title,
        identifiers=(("doi", doi),),
        year=year,
        pub_date=pub_date,
        authors=("Ada Lovelace",),
        meta=meta,
    )


def test_local_filters_apply_and_matched_rules_reach_the_report(env: _Env) -> None:
    corpus = {
        "crossref": [
            _stub("Agentic tool use in LLMs", "10.1/a", meta=(("categories", "cs.AI, cs.LG"),)),
            _stub("Quantum agents", "10.1/b"),  # exclude_regex 命中 → 剔除
            _stub("Unrelated topology", "10.1/c"),  # title_regex_any 未命中 → 剔除
            _stub("Agent memory", "10.1/d", year=None),  # min_year 声明下 year 缺失 → 剔除
        ]
    }
    fetcher = _StubFetcher(corpus)
    subscription = _load_one(
        env,
        filters={
            "title_regex_any": ["agent"],
            "exclude_regex": ["quantum"],
            "min_year": 2024,
        },
    )

    summary = run_watch(env.context(fetcher=fetcher), subscription, now=DAY)

    assert summary.seen_count == 4
    assert [entry.title for entry in summary.entries] == ["Agentic tool use in LLMs"]
    entry = summary.entries[0]
    assert entry.matched_rules == ("title_regex_any[0]", "min_year")
    assert entry.categories == ("cs.AI", "cs.LG")
    assert entry.url == "https://doi.org/10.1/a"  # 无 meta['url'] → DOI resolver 兜底
    assert entry.authors == ("Ada Lovelace",)


def test_meta_url_wins_over_the_doi_resolver(env: _Env) -> None:
    fetcher = _StubFetcher(
        {"crossref": [_stub("T", "10.1/x", meta=(("url", "https://example.test/x"),))]}
    )
    subscription = _load_one(env)
    summary = run_watch(env.context(fetcher=fetcher), subscription, now=DAY)
    assert summary.entries[0].url == "https://example.test/x"


def test_entry_url_is_empty_without_doi_or_meta(env: _Env) -> None:
    fetcher = _StubFetcher({"crossref": [PaperStub(title="T", identifiers=(("arxiv", "2601.1"),))]})
    subscription = _load_one(env)
    summary = run_watch(env.context(fetcher=fetcher), subscription, now=DAY)
    assert summary.entries[0].url == ""
    assert summary.entries[0].categories == ()


def test_source_scoped_predicate_only_reaches_its_own_source(env: _Env) -> None:
    """ssrn 的主题谓词不得误伤 crossref 的结果（`is_source_scoped_predicate` 分流）。

    信号未接线时 `ssrn.topic_filter` 是 pass-through 放行（T3 兜底，随本卡修）——两源
    因此都应完整通过，且 ssrn 一侧的命中记录里带上该谓词名。
    """
    ssrn_venue = VenueSpec(
        id="ssrn",
        kind="preprint_channel",
        names=VenueNames(full="SSRN"),
        field=["econ"],
        fulltext_source="ssrn",
        quirks={"topic_filter": "econ_fin"},
    )
    fetcher = _StubFetcher(
        {
            "ssrn": [_stub("Asset pricing puzzle", "10.2139/ssrn.1")],
            "crossref": [_stub("Asset pricing anomalies", "10.1/j")],
        }
    )
    subscription = _load_one(
        env,
        sources={"ssrn": {"networks": ["FEN"]}, "crossref": {"issns": ["0000-0000"]}},
    )
    context = env.context(fetcher=fetcher, venues={"ssrn": ssrn_venue, "crossref": _mock_venue()})

    summary = run_watch(context, subscription, now=DAY)

    by_source = {entry.source: entry for entry in summary.entries}
    assert set(by_source) == {"ssrn", "crossref"}
    assert "ssrn.topic_filter" in by_source["ssrn"].matched_rules
    assert by_source["crossref"].matched_rules == ()


def test_arxiv_query_bool_narrows_beyond_the_title_regex_mirror(env: _Env) -> None:
    """Phase 7 T9 追加改动：`arxiv.query_bool` 经 `watch._scoped_predicates` +
    `filter_papers(..., predicate_params=...)` 真实接入运行时——与
    `filters.title_regex_any` 镜像**叠加**执行（决策④，防御纵深，非替换），且有
    **独立贡献**：镜像放过、但精确布尔式拦下的条目必须被剔除，证明新机制不是
    "反正镜像已经挡住了"的重复劳动。

    镜像 `title_regex_any=["agent"]` 是宽松子串匹配；查询式
    `ti:"agentic" AND NOT ti:"survey"` 精确得多——两条区分用例：
    - "A Survey of Agentic Systems"：镜像命中（含"agent"），但 `ANDNOT ti:"survey"`
      拦下（题目含"survey"）。
    - "Multi-Agent Coordination Survey"：镜像命中（"Multi-Agent"含"agent"），但
      `ti:"agentic"` 原子本身不命中（题目只有"Agent"无"agentic"精确短语）——不同的
      拦截路径，同样证明谓词在独立生效。
    """
    corpus = {
        "arxiv": [
            _stub("Agentic Tool Use in LLMs", "10.48550/arxiv.2601.1"),  # 两道都过 → 收
            _stub("A Survey of Agentic Systems", "10.48550/arxiv.2601.2"),  # 镜像放过/谓词拦
            _stub("Multi-Agent Coordination Survey", "10.48550/arxiv.2601.3"),  # 同上，另一路径
            _stub("Unrelated Topology Results", "10.48550/arxiv.2601.4"),  # 两道都拦，基线
        ]
    }
    fetcher = _StubFetcher(corpus)
    subscription = _load_one(
        env,
        sources={"arxiv": {"categories": ["cs.AI"], "query": 'ti:"agentic" AND NOT ti:"survey"'}},
        filters={"title_regex_any": ["agent"]},
    )

    summary = run_watch(env.context(fetcher=fetcher, venues={}), subscription, now=DAY)

    assert summary.seen_count == 4
    assert [entry.title for entry in summary.entries] == ["Agentic Tool Use in LLMs"]
    assert summary.entries[0].matched_rules == ("title_regex_any[0]", "arxiv.query_bool")


# ---------------------------------------------------------------------------
# 失败处置
# ---------------------------------------------------------------------------


class _FailingFetcher:
    def __init__(self, failing: set[str], corpus: dict[str, list[PaperStub]]) -> None:
        self.failing = failing
        self.corpus = corpus

    def fetch(self, request: SourceRequest) -> list[PaperStub]:
        if request.source in self.failing:
            raise CrawlerError(ErrorClass.TRANSIENT, f"{request.source} exploded")
        return list(self.corpus.get(request.source, []))


def test_partial_source_failure_keeps_the_other_source_and_exits_one(env: _Env) -> None:
    fetcher = _FailingFetcher({"ssrn"}, {"crossref": [_stub("Kept", "10.1/k")]})
    subscription = _load_one(
        env, sources={"ssrn": {"networks": ["FEN"]}, "crossref": {"issns": ["0000-0000"]}}
    )

    summary = run_watch(env.context(fetcher=fetcher), subscription, now=DAY)

    assert summary.outcome is WatchOutcome.OK  # 成功源照常入库
    assert summary.ingested_count == 1
    assert [failure.source for failure in summary.failures] == ["ssrn"]
    assert summary.failures[0].error_class == "transient"
    assert exit_code_for([summary]) == 1  # 但退出码非零：挂掉的源必须可见
    # 失败源不进 watermark（成功源才推进）。
    assert set(env.subs_repo.read_watermark(subscription.name)["sources"]) == {  # type: ignore[arg-type]
        "crossref"
    }


def test_partial_pub_dates_do_not_kill_the_run(env: _Env) -> None:
    """P0 回归（2026-07-27 线上）：crossref 系源的 partial `pub_date` 不得炸掉整轮。

    `crossref/parse.py::_format_date_parts` **故意**产出 `'YYYY'`/`'YYYY-MM'`（其
    docstring 明文"partial 容 'YYYY'/'YYYY-MM'"），而 `watermark._parse_date` 曾只认
    完整 ISO —— ssrn 的**首个真实 run** 即触发 `WatermarkInvalid`，整轮在网络请求已经
    花掉之后崩掉：不推水位、不落 run 记录、无日报、非优雅 traceback。

    断言面 = 报告要求的三条：run 跑完、写 run 记录、水位按"跳过"语义推进。
    """
    fetcher = _StubFetcher(
        {
            "crossref": [
                _stub("Year only", "10.1/p1", pub_date="2026"),
                _stub("Year and month", "10.1/p2", pub_date="2026-07"),
                _stub("Full date", "10.1/p3", pub_date="2026-07-24"),
            ]
        }
    )
    subscription = _load_one(env)
    path = daily_report_path(DAY, root=env.report_root)

    summary = run_watch(env.context(fetcher=fetcher), subscription, now=DAY, report_path=str(path))

    # ① 整轮跑完，三条都正常入库（partial 只影响水位，不影响收录）。
    assert summary.outcome is WatchOutcome.OK
    assert summary.ingested_count == 3
    assert env.papers() == 3
    assert summary.failures == ()
    # ② run 记录落库（旧行为下这行根本不会执行到）。
    (run_row,) = env.runs(subscription.name)
    assert run_row["new_count"] == 3
    # ③ 水位只被**完整**日期推进；两条 partial 跳过（保守侧：下轮窗更宽）。
    stored = env.subs_repo.read_watermark(subscription.name)
    assert stored["sources"]["crossref"]["date"] == "2026-07-24"  # type: ignore[index]


def test_all_partial_dates_leave_the_watermark_unadvanced(env: _Env) -> None:
    """整窗全是 partial → 水位不推进（停在首跑初窗），但 run 照样成功落地。

    "不推进"在本模块是**保守侧**（下次窗更宽、重扫），不是失败——故 outcome 仍是 OK。
    """
    fetcher = _StubFetcher({"crossref": [_stub("Only year", "10.1/q1", pub_date="2026")]})
    subscription = _load_one(env)

    summary = run_watch(env.context(fetcher=fetcher), subscription, now=DAY)

    assert summary.outcome is WatchOutcome.OK
    assert summary.ingested_count == 1
    stored = env.subs_repo.read_watermark(subscription.name)
    # 首跑初窗下界 = DAY − 7；没有任何可解析日期能把它推起来。
    assert stored["sources"]["crossref"]["date"] == "2026-07-19"  # type: ignore[index]


def test_unparseable_date_in_one_source_does_not_starve_the_later_sources(env: _Env) -> None:
    """缺陷 A 的**多源**场景：一条解析不了的源侧日期不得让排在其后的源收不到东西。

    单源场景（`test_partial_pub_dates_do_not_kill_the_run`）只证明"这一个源没崩"；本
    用例证明的是**跨源**的那一半——`advance` 在 `run_watch` 的 per-step 循环里，旧
    实现下它一抛就把循环整个掀掉，后面的源一次都跑不到。修法在
    `watermark._advance_date`：解析不了的日期跳过并计数，压根不抛（见
    `_try_parse_date` 的宽松面）。

    这里用"真垃圾"（`'昨天'`，非合法 partial）而非 `'YYYY'`，是要覆盖到宽松面的另一
    半：不只 crossref 那种**预期内**的 partial 走跳过，任意源侧脏数据同样走跳过。

    **注**：本用例不覆盖存储侧水位损坏那条路径（那条仍 fail-loud，隔离粒度是订阅级，
    回归见 `test_a_broken_stored_watermark_fails_only_its_own_subscription`）。
    """
    ssrn_venue = VenueSpec(
        id="ssrn",
        kind="preprint_channel",
        names=VenueNames(full="SSRN"),
        field=["econ"],
        fulltext_source="ssrn",
    )
    fetcher = _StubFetcher(
        {
            # 真垃圾（非合法 partial）也必须只降级本源。
            "ssrn": [_stub("Broken date", "10.2139/ssrn.9", pub_date="昨天")],
            "crossref": [_stub("Later source survives", "10.1/z", pub_date="2026-07-24")],
        }
    )
    subscription = _load_one(
        env, sources={"ssrn": {"networks": ["FEN"]}, "crossref": {"issns": ["0000-0000"]}}
    )
    context = env.context(fetcher=fetcher, venues={"ssrn": ssrn_venue, "crossref": _mock_venue()})

    summary = run_watch(context, subscription, now=DAY)

    assert summary.outcome is WatchOutcome.OK
    # 排在坏源之后的源照跑照入库——这正是旧代码做不到的。
    assert {entry.source for entry in summary.entries} == {"ssrn", "crossref"}
    assert summary.ingested_count == 2
    stored = env.subs_repo.read_watermark(subscription.name)
    assert stored["sources"]["crossref"]["date"] == "2026-07-24"  # type: ignore[index]


def test_a_broken_stored_watermark_fails_only_its_own_subscription(env: _Env) -> None:
    """真·缺陷 B 回归（P0 独立审查回修 2026-07-27）：坏订阅不得掀翻 `--all` 的其余订阅。

    **存储侧**水位文档损坏（这里直写一份 `date: '2026'` 的 partial 游标）在
    `run_watch` **开头**那句 `Watermark.parse` 就抛 `WatermarkInvalid`——per-step 循环
    之外，源级隔离（`_run_source` / `_advance_source`）一个都够不着。那条 fail-loud
    是刻意的（损坏游标当成首跑 = 静默重刷全窗），**不降级**；真正该做的隔离在
    `run_watch_all`：本订阅记为失败，其余订阅照跑。

    此前 `run_watch_all` 是一句裸列表推导，于是排在坏订阅后面的全部订阅一次都跑不到
    ——线上 `asset-pricing` 崩掉后 arxiv/nber 两条腿没跑到，正是这个形态的源级同构。
    """
    _write_subscription(env.subs_dir, "alpha")
    _write_subscription(env.subs_dir, "beta")
    subscriptions = load_subscriptions(env.subs_dir, env.subs_repo)
    # 预置损坏水位：`date` 是 partial `'2026'`，存储侧 `_parse_date` 必须拒载（fail-loud）。
    env.subs_repo.write_watermark(
        "alpha",
        {"schema_ver": 1, "sources": {"crossref": {"kind": "date_cursor", "date": "2026"}}},
    )

    summaries, path = run_watch_all(env.context(), subscriptions, now=DAY)

    # ① 坏订阅**可见地**失败：占位 summary 带订阅级失败事件；没跑到 record_run 故无 run 行。
    assert [summary.subscription for summary in summaries] == ["alpha", "beta"]
    assert summaries[0].outcome is WatchOutcome.FAILED
    (failure,) = summaries[0].failures
    assert failure.source == SUBSCRIPTION_LEVEL_SOURCE
    assert failure.error_class == "config"
    assert "无法解析为 ISO 日期" in failure.message
    assert env.runs("alpha") == []
    assert env.subs_repo.read_watermark("alpha")["sources"] == {  # type: ignore[index]
        "crossref": {"kind": "date_cursor", "date": "2026"}
    }  # 坏水位原样留着等人工处置，绝不被"修好"或清空
    # ② 次订阅**照跑**：入库、推水位、并落 `subscription_run` 行（旧实现下一次都跑不到）。
    assert summaries[1].outcome is WatchOutcome.OK
    assert summaries[1].ingested_count == CORPUS_SIZE
    assert env.papers() == CORPUS_SIZE
    (beta_run,) = env.runs("beta")
    assert beta_run["new_count"] == CORPUS_SIZE
    assert beta_run["report_path"] == str(path)
    # ③ 整体结果携带失败信息 → 退出码非零；日报两条订阅都在，失败事件段点名坏订阅。
    assert exit_code_for(summaries) == 1
    text = write_daily_report(summaries, path, day=DAY)
    assert "## alpha" in text and "## beta" in text
    assert SUBSCRIPTION_LEVEL_SOURCE in text


def test_a_broken_watermark_does_not_swallow_programming_errors(env: _Env) -> None:
    """订阅级隔离**只兜 `CrawlerError`**：编程错误照旧冒泡，不许变成一行日报表格。"""

    class _BoomFetcher:
        def fetch(self, request: SourceRequest) -> list[PaperStub]:
            del request
            raise KeyError("programming error")

    _write_subscription(env.subs_dir, "alpha")
    subscriptions = load_subscriptions(env.subs_dir, env.subs_repo)

    with pytest.raises(KeyError):
        run_watch_all(env.context(fetcher=_BoomFetcher()), subscriptions, now=DAY)


def test_all_sources_failing_marks_the_run_failed_and_ingests_nothing(env: _Env) -> None:
    fetcher = _FailingFetcher({"crossref"}, {})
    subscription = _load_one(env)

    summary = run_watch(env.context(fetcher=fetcher), subscription, now=DAY)

    assert summary.outcome is WatchOutcome.FAILED
    assert summary.ingested_count == 0
    assert env.papers() == 0
    assert env.subs_repo.read_watermark(subscription.name) == {}
    assert len(env.runs(subscription.name)) == 1  # 失败也留痕
    assert exit_code_for([summary]) == 1


# ---------------------------------------------------------------------------
# `ingest: metadata+pdf` → 派生取回链任务（不 drain，不改 runner）
# ---------------------------------------------------------------------------


def _registry_with(tmp_path: Path, spec: VenueSpec) -> VenueRegistry:
    venues_dir = tmp_path / "venues"
    venues_dir.mkdir(exist_ok=True)
    (venues_dir / f"{spec.id}.yaml").write_text(
        yaml.safe_dump(spec.model_dump(mode="json"), allow_unicode=True), encoding="utf-8"
    )
    registry = VenueRegistry(
        {"crossref": MockPlatformAdapter(), "mock_platform": MockPlatformAdapter()}
    )
    registry.load_dirs([venues_dir])
    return registry


def test_metadata_plus_pdf_derives_resolve_tasks_within_the_limit(
    env: _Env, tmp_path: Path
) -> None:
    spec = _mock_venue("crossref_backed", fulltext_source="crossref")
    registry = _registry_with(tmp_path, spec)
    subscription = _load_one(env, actions={"ingest": "metadata+pdf", "auto_fetch_limit": 2})

    summary = run_watch(env.context(registry=registry), subscription, now=DAY)

    assert summary.ingested_count == CORPUS_SIZE
    assert summary.fetched_count == 2  # auto_fetch_limit 上限内
    pending = env.queue.by_state("PENDING")
    assert [row["kind"] for row in pending] == ["resolve", "resolve"]
    assert {row["venue_id"] for row in pending} == {"crossref_backed"}
    # 派生的 paper 已绑定 venue（`_stage_resolve` 靠 paper.venue_id 路由）。
    bound = env.db.query("SELECT COUNT(*) AS n FROM paper WHERE venue_id IS NOT NULL")
    assert int(bound[0]["n"]) == 2


def test_dry_run_derives_no_tasks_even_with_a_live_queue(env: _Env, tmp_path: Path) -> None:
    """判别力用例（审查 P2①）：真 registry + 真 queue + metadata+pdf，dry-run 下队列仍为空。

    此前的"dry-run 不派生"断言在 `queue=None` 的上下文里跑，即便实现漏判 dry-run 也照样
    绿——那不是在测 dry-run，是在测"没有队列就派不出任务"。
    """
    registry = _registry_with(tmp_path, _mock_venue("crossref_backed", fulltext_source="crossref"))
    subscription = _load_one(env, actions={"ingest": "metadata+pdf", "auto_fetch_limit": 5})

    summary = run_watch(env.context(registry=registry), subscription, dry_run=True, now=DAY)

    assert summary.fetched_count == 0
    assert env.queue.by_state("PENDING") == []  # 真队列在场，仍然一条都没派
    assert env.papers() == 0


def test_metadata_only_derives_nothing(env: _Env, tmp_path: Path) -> None:
    registry = _registry_with(tmp_path, _mock_venue("crossref_backed", fulltext_source="crossref"))
    subscription = _load_one(env, actions={"ingest": "metadata", "auto_fetch_limit": 5})

    summary = run_watch(env.context(registry=registry), subscription, now=DAY)

    assert summary.fetched_count == 0
    assert env.queue.by_state("PENDING") == []


def test_quota_is_not_eaten_by_unroutable_sources(env: _Env, tmp_path: Path) -> None:
    """审查 P2④：配额在"能路由的条目"上切——排在前面的无 venue 源不吃名额。

    ssrn 声明在前但 registry 里没有以它为 `fulltext_source` 的 venue；crossref 有。
    `auto_fetch_limit=2` 应当派出 2 个 crossref 任务，而不是被前两条 ssrn 条目吃掉。
    """
    registry = _registry_with(tmp_path, _mock_venue("crossref_backed", fulltext_source="crossref"))
    fetcher = _StubFetcher(
        {
            "ssrn": [_stub(f"S{i}", f"10.2139/ssrn.{i}") for i in range(3)],
            "crossref": [_stub(f"C{i}", f"10.1/c{i}") for i in range(3)],
        }
    )
    # 声明序 crossref→ssrn 由 YAML 键序决定；这里要 ssrn 在前，故直接构造 DSL 文本。
    (env.subs_dir / "mixed.yaml").write_text(
        "name: mixed\n"
        "sources:\n"
        "  ssrn: {networks: [FEN]}\n"
        "  crossref: {issns: ['0000-0000']}\n"
        "actions: {ingest: metadata+pdf, auto_fetch_limit: 2}\n",
        encoding="utf-8",
    )
    subscription = load_subscriptions(env.subs_dir, env.subs_repo)[0]
    assert subscription.source_names() == ("ssrn", "crossref")

    summary = run_watch(env.context(registry=registry, fetcher=fetcher), subscription, now=DAY)

    assert summary.ingested_count == 6
    assert summary.fetched_count == 2  # 名额全给了能路由的 crossref
    assert {row["venue_id"] for row in env.queue.by_state("PENDING")} == {"crossref_backed"}


# ---------------------------------------------------------------------------
# 批内重复计数（审查 P1-A#1）：同一 run 内多源/多请求撞同一 identifier
# ---------------------------------------------------------------------------


class _PerRequestFetcher:
    """按 `(源, 首个参数值)` 给语料——覆盖同源多请求（多 issn / 多 program）的场景。"""

    def __init__(self, corpus: dict[tuple[str, str | None], list[PaperStub]]) -> None:
        self.corpus = corpus
        self.requests: list[SourceRequest] = []

    def fetch(self, request: SourceRequest) -> list[PaperStub]:
        self.requests.append(request)
        key = (request.source, request.params[0][1] if request.params else None)
        return list(self.corpus.get(key, []))


def _assert_deduped(summary: RunSummary, expected: int) -> None:
    """去重基数一致性：new_count / entries / ingested 三者同数，且 paper_id 互不重复。"""
    assert summary.new_count == expected
    assert len(summary.entries) == expected
    assert summary.ingested_count == expected
    paper_ids = [entry.paper_id for entry in summary.entries]
    assert len(set(paper_ids)) == expected
    assert all(paper_ids)


def test_arxiv_query_bool_applies_uniformly_across_fan_out_categories(env: _Env) -> None:
    """Phase 7 T9 追加改动④：fan-out 交互说明——`arxiv.query_bool` 是**订阅级**
    （非分类级）参数，`_compile_arxiv` 只产一份 `predicate_params`，跟分类无关；
    `_run_source` 对多个 fan-out 请求的结果先聚合（`stubs.extend` 循环，未改动），
    `filter_papers` 再逐条目求值（per-stub 循环，未改动）——语义上就是"fan-out
    展开后逐条目独立过滤"，不存在"汇总后过滤"与"逐条目过滤"的二选一，因为过滤
    从来就是逐条目的，只是"条目"来自哪个 fan-out 分类对它不可见也不重要。

    本测试**不改**、也不依赖 `_compose_arxiv`/`_DELIVERABLE_PARAMS`/`_FANOUT_KEY`
    的任何行为——只验证既有 fan-out 展开出的多条请求，其聚合结果被同一个查询
    谓词正确、统一地过滤。
    """
    fetcher = _PerRequestFetcher(
        {
            ("arxiv", "cs.AI"): [_stub("Agentic Planning", "10.48550/arxiv.2601.10")],
            ("arxiv", "cs.LG"): [
                _stub("Agentic Optimization", "10.48550/arxiv.2601.11"),
                _stub("A Survey of Agentic Learning", "10.48550/arxiv.2601.12"),  # 谓词应拦
            ],
        }
    )
    subscription = _load_one(
        env,
        sources={
            "arxiv": {
                "categories": ["cs.AI", "cs.LG"],
                "query": 'ti:"agentic" AND NOT ti:"survey"',
            }
        },
        filters={"title_regex_any": ["agent"]},
    )

    summary = run_watch(env.context(fetcher=fetcher, venues={}), subscription, now=DAY)

    assert len(fetcher.requests) == 2  # 两分类各自 fan-out 一条请求——本卡未改这条语义
    assert summary.seen_count == 3
    assert {entry.title for entry in summary.entries} == {
        "Agentic Planning",
        "Agentic Optimization",
    }
    expected_rules = ("title_regex_any[0]", "arxiv.query_bool")
    assert all(entry.matched_rules == expected_rules for entry in summary.entries)


def test_batch_dedupe_crossref_two_issns_hitting_the_same_doi(env: _Env) -> None:
    """场景一：两个 ISSN 各拉回同一篇（合刊/转载）——一篇就是一篇。"""
    shared = _stub("Shared across journals", "10.1/shared")
    fetcher = _PerRequestFetcher(
        {
            ("crossref", "0304-405X"): [shared, _stub("Only in A", "10.1/a")],
            ("crossref", "0022-1082"): [shared, _stub("Only in B", "10.1/b")],
        }
    )
    subscription = _load_one(env, sources={"crossref": {"issns": ["0304-405X", "0022-1082"]}})

    summary = run_watch(env.context(fetcher=fetcher), subscription, now=DAY)

    assert len(fetcher.requests) == 2  # 重复键确实逐条展开了
    assert summary.seen_count == 4  # 拉回 4 条
    _assert_deduped(summary, 3)  # 去重后 3 篇
    assert env.papers() == 3
    # 同源合并不记 merged_from（那是给"另一个源也看到了"用的）。
    assert all(
        not any(rule.startswith(MERGED_SOURCE_RULE_PREFIX) for rule in entry.matched_rules)
        for entry in summary.entries
    )


def test_batch_dedupe_within_a_single_request(env: _Env) -> None:
    """场景二：同一个请求内部就出现重复（源侧翻页重叠等）。"""
    dup = _stub("Twice in one page", "10.1/dup")
    fetcher = _PerRequestFetcher({("crossref", "0000-0000"): [dup, dup, _stub("X", "10.1/x")]})
    subscription = _load_one(env)

    summary = run_watch(env.context(fetcher=fetcher), subscription, now=DAY)

    assert summary.seen_count == 3
    _assert_deduped(summary, 2)


def test_batch_dedupe_nber_two_programs_sharing_a_working_paper(env: _Env) -> None:
    """场景三：一篇 WP 同时挂在两个 program 的 feed 下。"""
    shared = _stub("Cross-listed WP", "10.3386/w40001")
    fetcher = _PerRequestFetcher(
        {
            ("nber", "AP"): [shared],
            ("nber", "CF"): [shared, _stub("CF only", "10.3386/w40002")],
        }
    )
    subscription = _load_one(env, sources={"nber": {"programs": ["AP", "CF"]}})

    summary = run_watch(
        env.context(fetcher=fetcher, venues={"nber": _mock_venue()}), subscription, now=DAY
    )

    assert summary.seen_count == 3
    _assert_deduped(summary, 2)


def test_batch_dedupe_across_sources_records_the_merged_origin(env: _Env) -> None:
    """场景四：arxiv 与 ssrn 给出同一个 DOI——保留声明序首个源，另一个记进命中规则。

    R2b/P0-4：原用 arxiv + openalex 这一对，openalex 已退出 DSL 源白名单（enrich-only，
    watch 侧不可达）。换成 arxiv + ssrn——同为两个真实可跑的源，跨源去重的被测语义
    （声明序首个胜 + `merged_from:` 记账）逐字不变。
    """
    shared_arxiv = _stub("Same paper, arxiv view", "10.48550/arxiv.2601.1")
    shared_ssrn = _stub("Same paper, ssrn view", "10.48550/arxiv.2601.1")
    fetcher = _StubFetcher(
        {
            "arxiv": [shared_arxiv, _stub("arxiv only", "10.48550/arxiv.2601.2")],
            "ssrn": [shared_ssrn],
        }
    )
    subscription = _load_one(
        env,
        sources={"arxiv": {"categories": ["cs.AI"]}, "ssrn": {"networks": ["FEN"]}},
    )

    summary = run_watch(env.context(fetcher=fetcher), subscription, now=DAY)

    assert summary.seen_count == 3
    _assert_deduped(summary, 2)
    survivor = next(e for e in summary.entries if e.title == "Same paper, arxiv view")
    assert survivor.source == "arxiv"  # 声明序在前者胜
    assert f"{MERGED_SOURCE_RULE_PREFIX}ssrn" in survivor.matched_rules
    assert "Same paper, ssrn view" not in [entry.title for entry in summary.entries]


def test_batch_dedupe_does_not_merge_identifier_less_stubs(env: _Env) -> None:
    """零 identifier 的条目无从证明重复 → 一律保留（同 guard 的保守判新口径）。"""
    fetcher = _StubFetcher(
        {
            "crossref": [
                PaperStub(title="anon A", identifiers=()),
                PaperStub(title="anon B", identifiers=()),
            ]
        }
    )
    subscription = _load_one(env)
    summary = run_watch(env.context(fetcher=fetcher), subscription, now=DAY)
    assert summary.new_count == 2


def test_batch_dedupe_prevents_a_spurious_truncation(env: _Env) -> None:
    """批内重复曾把 `new_count` 顶过阈值——去重后不该再熔断（虚高计数的真实后果）。"""
    dup = _stub("Repeated", "10.1/rep")
    fetcher = _PerRequestFetcher(
        {("crossref", "0304-405X"): [dup], ("crossref", "0022-1082"): [dup]}
    )
    subscription = _load_one(
        env,
        sources={"crossref": {"issns": ["0304-405X", "0022-1082"]}},
        guard={"max_new_per_run": 1},
    )

    summary = run_watch(env.context(fetcher=fetcher), subscription, now=DAY)

    assert summary.outcome is WatchOutcome.OK
    assert summary.new_count == 1


# ---------------------------------------------------------------------------
# nber RSS 通道端到端（P1-B；T7 `adapters/nber/rss.py` fixture 驱动）
# ---------------------------------------------------------------------------


def _nber_rss_fetcher(urls: list[str]) -> NberRssFetcher:
    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, content=fixture_bytes("06_rss_program_cf_synth.xml"))

    client = HttpClient(user_agent="PaperCrawler/test", transport=httpx.MockTransport(handler))
    return NberRssFetcher(client, now=DAY)


def test_nber_subscription_runs_through_the_rss_channel(env: _Env) -> None:
    urls: list[str] = []
    fetcher = _nber_rss_fetcher(urls)
    subscription = _load_one(
        env, sources={"nber": {"programs": ["CF"]}}, filters={"min_year": 2026}
    )

    summary = run_watch(env.context(fetcher=fetcher), subscription, now=DAY)

    assert urls == ["https://back.nber.org/rss/newcf.xml"]  # 走 RSS，绝不触 crossref
    # proxy year 生效：3 条里 2 条没有可用 pubDate，若不传 default_year 会被 min_year 全灭。
    assert summary.new_count == 3
    assert summary.ingested_count == 3
    assert {entry.categories for entry in summary.entries} == {("CF",)}  # program → 分类轴
    assert all(entry.url.startswith("https://www.nber.org/papers/") for entry in summary.entries)
    # watermark 走 id 集合差分（T4 `IdSetDiff`），而非日期游标。
    stored = env.subs_repo.read_watermark(subscription.name)
    assert stored["sources"]["nber"]["kind"] == "id_set"  # type: ignore[index]


def test_nber_second_run_is_all_diffed_away(env: _Env) -> None:
    urls: list[str] = []
    fetcher = _nber_rss_fetcher(urls)
    subscription = _load_one(env, sources={"nber": {"programs": ["CF"]}})
    context = env.context(fetcher=fetcher)

    run_watch(context, subscription, now=DAY)
    second = run_watch(context, subscription, now=DAY)

    assert second.seen_count == 3  # feed 照拉整份快照
    assert second.new_count == 0  # id 差分把重叠部分全摘掉
    assert env.papers() == 3


def test_zero_auto_fetch_limit_derives_nothing(env: _Env, tmp_path: Path) -> None:
    registry = _registry_with(tmp_path, _mock_venue("crossref_backed", fulltext_source="crossref"))
    subscription = _load_one(env, actions={"ingest": "metadata+pdf", "auto_fetch_limit": 0})
    summary = run_watch(env.context(registry=registry), subscription, now=DAY)
    assert summary.fetched_count == 0


def test_derivation_is_skipped_loudly_when_no_venue_serves_the_source(
    env: _Env, tmp_path: Path
) -> None:
    """没有以该源为 fulltext_source 的 venue → 跳过派生，不产出永远 BLOCKED 的任务。"""
    registry = _registry_with(
        tmp_path, _mock_venue("mock_journal")
    )  # fulltext_source=mock_platform
    subscription = _load_one(env, actions={"ingest": "metadata+pdf", "auto_fetch_limit": 3})

    summary = run_watch(env.context(registry=registry), subscription, now=DAY)

    assert summary.ingested_count == CORPUS_SIZE
    assert summary.fetched_count == 0
    assert env.queue.by_state("PENDING") == []


def test_derivation_is_skipped_when_registry_or_queue_is_absent(env: _Env) -> None:
    subscription = _load_one(env, actions={"ingest": "metadata+pdf", "auto_fetch_limit": 3})
    context = env.context()
    context.queue = None

    summary = run_watch(context, subscription, now=DAY)

    assert summary.fetched_count == 0


# ---------------------------------------------------------------------------
# 空目录 / 空计划
# ---------------------------------------------------------------------------


def test_empty_subscription_dir_loads_nothing(env: _Env) -> None:
    assert load_subscriptions(env.subs_dir, env.subs_repo) == []


def test_run_watch_all_with_no_subscriptions_returns_the_path_only(env: _Env) -> None:
    summaries, path = run_watch_all(env.context(), [], now=DAY)
    assert summaries == []
    assert path.name == "daily-2026-07-26.md"
    assert isinstance(write_daily_report(summaries, path, day=DAY), str)


def test_run_summary_default_clock_is_used_when_now_is_omitted(env: _Env) -> None:
    """`now=None` 走真实 UTC 今日（唯一时钟入口的另一分支）。"""
    subscription = _load_one(env)
    summary: RunSummary = run_watch(env.context(), subscription)
    assert summary.outcome is WatchOutcome.OK
    assert summary.finished_at >= summary.started_at


def test_resolve_subscription_returns_the_stored_subscription(env: _Env) -> None:
    """库内取回走 `Subscription.from_stored`（与文件加载同一校验器）——声明序须保住。"""
    loaded = _load_one(env)
    resolved = resolve_subscription(loaded.name, env.subs_repo)
    assert resolved == loaded


def test_repeat_derivation_does_not_recount_already_queued_tasks(env: _Env, tmp_path: Path) -> None:
    """派生计数只算 `enqueued`：同一 paper 的 PENDING resolve 已在队列里就不是新工作。"""
    registry = _registry_with(tmp_path, _mock_venue("crossref_backed", fulltext_source="crossref"))
    subscription = _load_one(
        env,
        actions={"ingest": "metadata+pdf", "auto_fetch_limit": 2},
        guard={"max_new_per_run": 200, "dedupe_against_library": False},
    )
    context = env.context(registry=registry)

    first = run_watch(context, subscription, now=DAY)
    second = run_watch(context, subscription, now=DAY)

    assert first.fetched_count == 2
    assert second.fetched_count == 0  # 同键 PENDING 已存在 → duplicate，不重复计数
    assert len(env.queue.by_state("PENDING")) == 2


def test_min_year_with_all_years_present_drops_nothing(env: _Env) -> None:
    """声明 min_year 但语料年份齐全 → 无"因 year 缺失被排除"计数（该分支的另一侧）。"""
    fetcher = _StubFetcher({"crossref": [_stub("Agent A", "10.1/a"), _stub("Agent B", "10.1/b")]})
    subscription = _load_one(env, filters={"min_year": 2024})

    summary = run_watch(env.context(fetcher=fetcher), subscription, now=DAY)

    assert summary.new_count == 2
    assert all("min_year" in entry.matched_rules for entry in summary.entries)


def test_id_set_diff_falls_back_to_title_for_identifier_less_stubs(env: _Env) -> None:
    """`PaperStub.identifiers` 契约是"至少 1 个"，真空了也不该炸掉整轮——退回标题差分。"""
    fetcher = _StubFetcher({"nber": [PaperStub(title="Untitled anchor", identifiers=())]})
    subscription = _load_one(env, sources={"nber": {"programs": ["AP"]}})
    context = env.context(fetcher=fetcher, venues={"nber": _mock_venue()})

    first = run_watch(context, subscription, now=DAY)
    stored = env.subs_repo.read_watermark(subscription.name)

    assert first.new_count == 1
    assert stored["sources"]["nber"]["ids"] == ["title:Untitled anchor"]  # type: ignore[index]
