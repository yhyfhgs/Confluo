"""per-source watermark 增量语义（Phase 6 T4；design/09 §5 + plan §4 T4）。

测试的重心是**增量正确性**而非实现细节，四条主线：

1. **三类策略的 fixture 时间线推演**（`DateUpperBound` / `DateCursor` / `IdSetDiff`
   各 ≥4 场景：空 watermark 首跑、正常推进、乱序到达、边界日，另加未来日期与零新增）；
2. **推进单调性 property**（hypothesis）：任意到达序下窗口下界**永不回退**——这是
   "宁可重看不可漏看"这条纪律的形式化表述；
3. **推进 ≠ 提交**：`advance()` 只产候选，run 不成功就不写库——走**真 sqlite**
   （`SubscriptionRepo`）验证"未提交则 read 回旧值"；
4. **序列化 fail-loud 矩阵**：坏格式/未知 `schema_ver`/kind 不符一律响亮拒载，
   绝不静默当成首跑（静默会导致全窗重刷，或更糟——被当成"已推进"而漏看）。

时钟一律经 `now=` 注入（`TODAY`），零 `datetime.now()` 依赖；仅一条测试验证缺省
时钟自洽。全程离线（sqlite + 纯函数）。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from paper_crawler.errors import CrawlerError, ErrorClass, WatermarkInvalid
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import SubscriptionRepo
from paper_crawler.subs.model import SOURCE_FIELDS, Subscription, parse_subscription
from paper_crawler.subs.types import DATE_WINDOW_PARAMS
from paper_crawler.subs.watermark import (
    DEFAULT_INITIAL_LOOKBACK_DAYS,
    DEFAULT_MAX_IDS,
    DEFAULT_OVERLAP_DAYS,
    SCHEMA_VERSION,
    STRATEGIES,
    DateCursor,
    DateState,
    DateUpperBound,
    IdSetDiff,
    IdSetState,
    Watermark,
    advance,
    strategy_for,
    window_params,
)

# 固定"今天"——全部时间线推演的锚（今天 − 7 = 2026-07-19 即首跑初窗下界）。
TODAY = date(2026, 7, 26)
FIRST_RUN_FLOOR = "2026-07-19"

# D-029 联动后（design/09 §5 修订 2026-07-26）：ssrn 归日期游标族，id 差分只剩 nber。
DATE_SOURCES = ("arxiv", "crossref", "openalex", "s2", "ssrn")
ID_SET_SOURCES = ("nber",)

# 各源窗口下界相对水位的回退天数（`overlap_days`；含端天然重扫之外的**额外**容忍）。
OVERLAP_DAYS = {"arxiv": 1, "crossref": 2, "ssrn": 1, "openalex": 0, "s2": 0}


def _date_state(source: str, day: str) -> Watermark:
    return Watermark().with_state(source, DateState(day))


# ---------------------------------------------------------------------------
# 注册表与窗口参数形态（design/09 §3 能力表 ↔ §5 增量语义）
# ---------------------------------------------------------------------------


def test_strategies_cover_exactly_the_dsl_source_set() -> None:
    """集合等值自断言：策略表与 DSL 源词表同集（防"加了源却没有增量语义"漂移）。"""
    assert set(STRATEGIES) == set(SOURCE_FIELDS)


def test_strategy_kinds_match_design_09_assignment() -> None:
    """design/09 §5 的源→策略分派（含 D-029 联动修订）：arxiv 上界窗、四源游标、nber id 差分。"""
    assert isinstance(STRATEGIES["arxiv"], DateUpperBound)
    assert all(
        isinstance(STRATEGIES[s], DateCursor) for s in ("crossref", "openalex", "s2", "ssrn")
    )
    assert all(isinstance(STRATEGIES[s], IdSetDiff) for s in ID_SET_SOURCES)
    assert set(DATE_SOURCES) | set(ID_SET_SOURCES) == set(SOURCE_FIELDS)  # 两族无缺无重


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # 日期类：首跑 = 今天 − 7 天保守初窗（模块 docstring "首跑"段的三条理由）
        ("arxiv", (("submittedDate", "[202607190000 TO 202607262359]"),)),
        ("crossref", (("from-pub-date", "2026-07-19"),)),
        ("openalex", (("from_publication_date", "2026-07-19"),)),
        # s2 日粒度（`year=` 的年粒度会把 7 天初窗放大成整年 → 首跑必熔断死循环）
        ("s2", (("publicationDateOrYear", "2026-07-19:"),)),
        # ssrn 成对产出：crossref `_works_url` 无条件拼 from/until 两端（D-029）
        ("ssrn", (("from-created-date", "2026-07-19"), ("until-created-date", "2026-07-26"))),
        # id 差分类：无日期轴，首跑 = 空 id 集（最近一轮 RSS 全算新增）
        ("nber", ()),
    ],
)
def test_first_run_window_params_per_source(source: str, expected: object) -> None:
    """每源的窗口参数名 + 首跑语义（T5 与 T2 静态参数合成的输入面）。"""
    assert window_params(Watermark(), source, now=TODAY) == expected


@pytest.mark.parametrize("source", sorted(SOURCE_FIELDS))
@pytest.mark.parametrize("first_run", [True, False], ids=["first-run", "with-watermark"])
def test_window_param_keys_are_subset_of_the_shared_slot_table(
    source: str, first_run: bool
) -> None:
    """⊆ 自断言：本层产出的键恒 ⊆ `types.DATE_WINDOW_PARAMS[source]`（单一同源不漂移）。

    T2 与 T4 各产一半窗口参数、T5 合成——槽位名表若与本层实际产出脱节，错就落在
    "参数拼进 URL 之后"，离线测不出来。首跑与已有水位两种状态都查。
    """
    strategy = STRATEGIES[source]
    state: DateState | IdSetState = (
        IdSetState(("w30000",)) if isinstance(strategy, IdSetDiff) else DateState("2026-07-22")
    )
    watermark = Watermark() if first_run else Watermark().with_state(source, state)
    produced = {key for key, _ in window_params(watermark, source, now=TODAY)}
    assert produced <= set(DATE_WINDOW_PARAMS[source])


def test_first_run_floor_tracks_the_declared_lookback() -> None:
    """初窗下界 = 今天 − `DEFAULT_INITIAL_LOOKBACK_DAYS`（常量与行为同源，非硬编码巧合）。"""
    assert (TODAY - timedelta(days=DEFAULT_INITIAL_LOOKBACK_DAYS)).isoformat() == FIRST_RUN_FLOOR


def test_strategy_for_unknown_source_is_fail_loud() -> None:
    with pytest.raises(WatermarkInvalid) as excinfo:
        strategy_for("scholar")
    assert "未知源" in str(excinfo.value)
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert isinstance(excinfo.value, CrawlerError)


def test_default_clock_is_today_utc() -> None:
    """不注入 `now` 时取当天 UTC（只断言与真实时钟自洽，不钉死具体日期）。"""
    floor = datetime.now(UTC).date() - timedelta(days=DEFAULT_INITIAL_LOOKBACK_DAYS)
    assert window_params(Watermark(), "crossref") == (("from-pub-date", floor.isoformat()),)


# ---------------------------------------------------------------------------
# 日期类策略：时间线推演（DoD ≥4 场景/策略）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("source", DATE_SOURCES)
@pytest.mark.parametrize(
    ("state", "seen", "expected", "scenario"),
    [
        (None, [], FIRST_RUN_FLOOR, "首跑零新增：锚在初窗下界，不留空档"),
        (None, ["2026-07-24"], "2026-07-24", "首跑正常推进"),
        ("2026-07-20", ["2026-07-21", "2026-07-22"], "2026-07-22", "正常推进：取已见最大"),
        ("2026-07-20", ["2026-07-22", "2026-07-21"], "2026-07-22", "乱序到达：取 max 非取末"),
        ("2026-07-22", ["2026-07-19", "2026-07-20"], "2026-07-22", "迟到旧条目：水位不回退"),
        ("2026-07-22", ["2026-07-22", "2026-07-22"], "2026-07-22", "边界日重复：原地不动"),
        ("2026-07-22", [], "2026-07-22", "零新增：不推进（下次窗更宽）"),
        ("2026-07-22", ["2026-07-26"], "2026-07-26", "边界日 = 今天：可推进到今天"),
        ("2026-07-22", ["2027-01-01"], "2026-07-22", "未来日期：不采信，水位不动"),
        ("2026-07-22", ["2026-12-01", "2026-07-24"], "2026-07-24", "未来+正常混排：只认非未来"),
    ],
)
def test_date_family_advance_timeline(
    source: str, state: str | None, seen: list[str], expected: str, scenario: str
) -> None:
    """日期类两策略共用的推进算法：`max(旧水位, max(已见 ∩ ≤今天))`。

    `scenario` 只为失败时可读（pytest 会把它打进用例 id）。
    """
    watermark = Watermark() if state is None else _date_state(source, state)
    assert advance(watermark, source, seen, now=TODAY).state_for(source) == DateState(expected)


@pytest.mark.parametrize("source", DATE_SOURCES)
def test_date_family_advance_accepts_timestamp_forms(source: str) -> None:
    """源侧日期形态不一（Atom 完整时间戳 / 空格分隔 / 紧凑）——统一取日期部分。"""
    seen = ["2026-07-21T09:30:00Z", "2026-07-22 18:00:00", "20260723"]
    assert advance(_date_state(source, "2026-07-20"), source, seen, now=TODAY).state_for(
        source
    ) == DateState("2026-07-23")


def test_arxiv_window_overlaps_exactly_one_day_below_the_watermark() -> None:
    """arxiv：下界 = 水位 − 1 天（design/09 §5 重叠窗，防 announce 延迟漏看）。"""
    watermark = _date_state("arxiv", "2026-07-22")
    assert window_params(watermark, "arxiv", now=TODAY) == (
        ("submittedDate", "[202607210000 TO 202607262359]"),
    )
    strategy = STRATEGIES["arxiv"]
    assert isinstance(strategy, DateUpperBound)
    assert strategy.lower_bound(DateState("2026-07-22"), now=TODAY) == date(2026, 7, 21)
    assert strategy.overlap_days == DEFAULT_OVERLAP_DAYS == 1


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # openalex：`overlap_days=0` → 下界 == 水位本身（含端天然重扫那一天即可）
        ("openalex", (("from_publication_date", "2026-07-22"),)),
        # crossref：`overlap_days=2` —— pub-date 是刊期非入库时刻，记录陆续沉积
        ("crossref", (("from-pub-date", "2026-07-20"),)),
        # ssrn：`overlap_days=1`（created ~1 日延迟）+ until 端成对到今天
        ("ssrn", (("from-created-date", "2026-07-21"), ("until-created-date", "2026-07-26"))),
        # s2：日粒度开区间，`<起>:` 单参数区间语法
        ("s2", (("publicationDateOrYear", "2026-07-22:"),)),
    ],
)
def test_date_cursor_window_shape_per_source(source: str, expected: object) -> None:
    """游标含端 → 下界 = 水位 − `overlap_days`；上界形态三选一（无 / 成对 / 区间后缀）。"""
    assert window_params(_date_state(source, "2026-07-22"), source, now=TODAY) == expected


@pytest.mark.parametrize("source", DATE_SOURCES)
def test_overlap_days_match_the_documented_per_source_table(source: str) -> None:
    """`overlap_days` 逐源取值 = 模块 docstring 的分工表（常量与行为同源）。"""
    strategy = STRATEGIES[source]
    assert isinstance(strategy, DateUpperBound | DateCursor)
    assert strategy.overlap_days == OVERLAP_DAYS[source]
    assert _lower_bound(source, DateState("2026-07-22")) == date(2026, 7, 22) - timedelta(
        days=OVERLAP_DAYS[source]
    )


def test_s2_uses_day_granularity_not_year() -> None:
    """s2 必须保住**日**粒度：年窗会把 7 天初窗放大成整年 → 首跑必超护栏 → 熔断死循环。

    审查裁定的 P1：`year=` 与 `publicationDateOrYear` 同轴（metadata-apis.md 同列），
    取后者。⚠ `<起>:` 开区间值语法待 T9 在线冒烟确认。
    """
    strategy = STRATEGIES["s2"]
    assert isinstance(strategy, DateCursor)
    assert strategy.param == "publicationDateOrYear" and strategy.range_suffix == ":"
    # 跨年也不塌成年份：值里保留完整日期
    assert window_params(_date_state("s2", "2025-12-31"), "s2", now=TODAY) == (
        ("publicationDateOrYear", "2025-12-31:"),
    )


def test_ssrn_uses_created_axis_cursor_with_paired_until() -> None:
    """ssrn D-029 联动：created 轴游标（非 id 差分），且 until 端必须成对。

    `CrossrefAdapter._works_url` 无条件拼 `from-…,until-…`——只给 from 就是半截 filter。
    """
    strategy = STRATEGIES["ssrn"]
    assert isinstance(strategy, DateCursor)
    assert (strategy.param, strategy.until_param) == ("from-created-date", "until-created-date")
    keys = [key for key, _ in window_params(Watermark(), "ssrn", now=TODAY)]
    assert keys == ["from-created-date", "until-created-date"]
    assert set(keys) == set(DATE_WINDOW_PARAMS["ssrn"])  # 成对 = 槽位名用满


def test_arxiv_advance_uses_max_seen_not_today() -> None:
    """上界取"已见最大"而非"今天"：靠近今天的提交尚未 announce，取今天会漏看。"""
    after = advance(_date_state("arxiv", "2026-07-20"), "arxiv", ["2026-07-21"], now=TODAY)
    assert after.state_for("arxiv") == DateState("2026-07-21")


def test_unparseable_seen_date_is_fail_loud() -> None:
    """已见日期解析不了 → 响亮报错（静默跳过会让"这批没推进水位"无从察觉）。"""
    with pytest.raises(WatermarkInvalid) as excinfo:
        advance(Watermark(), "arxiv", ["2026-07-21", "昨天"], now=TODAY)
    assert "无法解析为 ISO 日期" in str(excinfo.value)
    assert excinfo.value.detail == "sources.arxiv.seen[1]"


# ---------------------------------------------------------------------------
# id 集合差分策略：时间线推演（DoD ≥4 场景）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("source", ID_SET_SOURCES)
def test_id_set_first_run_treats_everything_as_new(source: str) -> None:
    """首跑：空 id 集 → 最近一轮 RSS 全是新增；窗口参数恒空（无日期轴）。"""
    strategy = STRATEGIES[source]
    assert isinstance(strategy, IdSetDiff)
    assert strategy.new_ids(None, ["a", "b"]) == ("a", "b")
    assert window_params(Watermark(), source, now=TODAY) == ()
    assert strategy.advance(None, ["a", "b"]) == IdSetState(("a", "b"))


def test_id_set_diff_reports_only_unseen_ids() -> None:
    """正常差分：与上次集合的交集不再算新增（保序，按候选到达序）。"""
    strategy = STRATEGIES["nber"]
    assert isinstance(strategy, IdSetDiff)
    assert strategy.new_ids(IdSetState(("b", "a")), ["b", "c", "a", "d"]) == ("c", "d")


def test_id_set_advance_puts_this_run_first_and_keeps_the_old_tail() -> None:
    """推进：本次置前（最新）+ 旧集合补后 —— 截断只砍最旧的那一段。"""
    after = advance(Watermark().with_state("nber", IdSetState(("b", "a"))), "nber", ["c", "b"])
    assert after.state_for("nber") == IdSetState(("c", "b", "a"))


def test_id_set_advance_dedupes_within_one_run() -> None:
    """乱序/重复到达：同一 id 在一次窗内出现多次只留一份（保序去重）。"""
    strategy = STRATEGIES["nber"]
    assert isinstance(strategy, IdSetDiff)
    assert strategy.advance(None, ["a", "b", "a", "c", "b"]) == IdSetState(("a", "b", "c"))


def test_id_set_advance_truncates_at_max_ids_dropping_the_oldest() -> None:
    """边界：N 上限生效时砍掉最旧的（掉出去的下次重报 → 去重兜底，不会漏看）。"""
    strategy = IdSetDiff(source="nber", max_ids=3)
    assert strategy.advance(IdSetState(("c", "b", "a")), ["e", "d"]) == IdSetState(("e", "d", "c"))


def test_default_max_ids_actually_bounds_the_document() -> None:
    """缺省上限真的咬得住（防 watermark_json 无限膨胀）。"""
    strategy = STRATEGIES["nber"]
    assert isinstance(strategy, IdSetDiff)
    after = strategy.advance(None, [f"w{n}" for n in range(DEFAULT_MAX_IDS + 25)])
    assert len(after.ids) == DEFAULT_MAX_IDS == strategy.max_ids


def test_id_set_zero_new_keeps_the_state() -> None:
    """零新增：集合原样保留（不清空——清空等于下次全量重报）。"""
    state = IdSetState(("b", "a"))
    assert advance(Watermark().with_state("nber", state), "nber", []).state_for("nber") == state


# ---------------------------------------------------------------------------
# 推进单调性 property（DoD：advance 结果的窗口下界不回退）
# ---------------------------------------------------------------------------


def _lower_bound(source: str, state: DateState) -> date:
    strategy = STRATEGIES[source]
    assert isinstance(strategy, DateUpperBound | DateCursor)
    return strategy.lower_bound(state, now=TODAY)


@settings(derandomize=True, deadline=None, max_examples=300)
@given(
    source=st.sampled_from(DATE_SOURCES),
    start_offset=st.integers(min_value=0, max_value=120),
    # 负 offset = 未来日期（坏数据/online-first），正 offset = 过去
    seen_offsets=st.lists(st.integers(min_value=-120, max_value=200), max_size=8),
)
def test_property_date_window_lower_bound_never_regresses(
    source: str, start_offset: int, seen_offsets: list[int]
) -> None:
    """任意已见日期集合（含乱序/未来/远古）下，推进后的窗口下界 ≥ 推进前。"""
    before_state = DateState((TODAY - timedelta(days=start_offset)).isoformat())
    seen = [(TODAY - timedelta(days=offset)).isoformat() for offset in seen_offsets]
    after_state = advance(
        Watermark().with_state(source, before_state), source, seen, now=TODAY
    ).state_for(source)
    assert isinstance(after_state, DateState)
    assert after_state.date >= before_state.date  # 水位单调
    assert _lower_bound(source, after_state) >= _lower_bound(source, before_state)  # 窗下界单调
    assert after_state.date <= TODAY.isoformat()  # 且永不越过今天


@settings(derandomize=True, deadline=None, max_examples=200)
@given(
    source=st.sampled_from(DATE_SOURCES),
    rounds=st.lists(st.lists(st.integers(min_value=-30, max_value=90), max_size=4), max_size=6),
)
def test_property_repeated_advance_is_monotone_across_rounds(
    source: str, rounds: list[list[int]]
) -> None:
    """多轮时间线推演：逐轮推进，窗口下界逐轮非递减（跨轮无回退）。"""
    watermark = Watermark()
    previous: date | None = None
    for offsets in rounds:
        seen = [(TODAY - timedelta(days=offset)).isoformat() for offset in offsets]
        watermark = advance(watermark, source, seen, now=TODAY)
        state = watermark.state_for(source)
        assert isinstance(state, DateState)
        current = _lower_bound(source, state)
        assert previous is None or current >= previous
        previous = current


@settings(derandomize=True, deadline=None, max_examples=200)
@given(
    old=st.lists(st.text(alphabet="abcdef", min_size=1, max_size=4), max_size=12),
    seen=st.lists(st.text(alphabet="abcdef", min_size=1, max_size=4), max_size=12),
)
def test_property_id_set_retains_this_run_and_stops_reporting_it(
    old: list[str], seen: list[str]
) -> None:
    """id 差分的对应单调性：本次见到的 id 推进后必在集合内，下一轮不再报为新增。"""
    strategy = IdSetDiff(source="nber", max_ids=64)  # 远大于样本量，避开截断路径
    after = strategy.advance(IdSetState(tuple(dict.fromkeys(old))), seen)
    assert set(seen) <= set(after.ids)
    assert strategy.new_ids(after, seen) == ()
    assert len(after.ids) == len(set(after.ids))  # 无重复


@settings(derandomize=True, deadline=None, max_examples=200)
@given(
    max_ids=st.integers(min_value=1, max_value=8),
    old=st.lists(st.text(alphabet="abcdefgh", min_size=1, max_size=3), max_size=14),
    seen=st.lists(st.text(alphabet="abcdefgh", min_size=1, max_size=3), max_size=14),
)
def test_property_id_set_truncation_keeps_a_bounded_ordered_prefix(
    max_ids: int, old: list[str], seen: list[str]
) -> None:
    """截断路径的不变量：长度恒 ≤ `max_ids`，且结果 == 「本次+旧集」保序去重的**前缀**。

    前缀语义 = 砍的永远是最旧的一段（`IdSetState` 的"新→旧"序约定），不会打乱顺序、
    也不会先砍新的——否则刚见过的 id 下轮又被报成新增，重叠窗就白开了。
    """
    strategy = IdSetDiff(source="nber", max_ids=max_ids)
    state = IdSetState(tuple(dict.fromkeys(old))[:max_ids])
    after = strategy.advance(state, seen)
    expected_full = list(dict.fromkeys([*seen, *state.ids]))
    assert len(after.ids) <= max_ids
    assert list(after.ids) == expected_full[:max_ids]  # 保序前缀，非任意子集


# ---------------------------------------------------------------------------
# 重叠窗的重复：策略层不去重、如实返回（接缝裁决③的说明性测试）
# ---------------------------------------------------------------------------


def test_overlap_window_repeats_are_returned_as_is_dedupe_belongs_downstream() -> None:
    """同一条目在相邻两窗重现——**watermark 层不去重**，如实让它再流一遍。

    watermark 只负责"不漏"；"不重"归下游三道网：T3 护栏 `dedupe_against_library`、
    入库层 identifier `(scheme, value)` 主键（design/09 §5 末），以及 id 差分类源自身的
    `new_ids()`。本测试是这条分工的可执行说明。
    """
    yesterday = date(2026, 7, 25)
    # run 1（昨天）：水位 07-23 → 窗下界 07-22；见到 07-24 的 P1，水位推到 07-24。
    run1 = advance(_date_state("arxiv", "2026-07-23"), "arxiv", ["2026-07-24"], now=yesterday)
    assert run1.state_for("arxiv") == DateState("2026-07-24")

    # run 2（今天）：重叠 1 天 → 下界回退到 07-23，P1（07-24）**必然**再次落在窗内。
    state = run1.state_for("arxiv")
    assert isinstance(state, DateState)
    assert _lower_bound("arxiv", state) == date(2026, 7, 23) < date(2026, 7, 24)

    # P1 二次出现：advance 幂等（水位不动），且策略层不给任何"这条见过"的信号——
    # 日期类策略连差分接口都没有，去重责任在别处，接缝上不留误会。
    run2 = advance(run1, "arxiv", ["2026-07-24"], now=TODAY)
    assert run2 == run1
    assert not hasattr(STRATEGIES["arxiv"], "new_ids")

    # 对照：id 差分类（nber）**才**在策略层去重——这是它的定义行为（无日期轴的替代品）。
    nber = STRATEGIES["nber"]
    assert isinstance(nber, IdSetDiff)
    seen_once = nber.advance(None, ["w30000"])
    assert nber.new_ids(seen_once, ["w30000", "w30001"]) == ("w30001",)


# ---------------------------------------------------------------------------
# 文档：序列化 / 多源 / 退订清理
# ---------------------------------------------------------------------------


def test_document_round_trip_through_dict() -> None:
    """`{schema_ver, sources: {源: {kind, ...}}}`（plan §4 T4 裁决格式）互逆且可 JSON。

    三类策略同时在场：`kind` 让人读 watermark_json 时一眼看出该源用的哪套语义。
    """
    watermark = (
        Watermark()
        .with_state("arxiv", DateState("2026-07-22"))
        .with_state("crossref", DateState("2026-07-21"))
        .with_state("nber", IdSetState(("w30000", "w30001")))
    )
    payload = watermark.to_dict()
    assert payload == {
        "schema_ver": SCHEMA_VERSION,
        "sources": {
            "arxiv": {"kind": "date_upper_bound", "date": "2026-07-22"},
            "crossref": {"kind": "date_cursor", "date": "2026-07-21"},
            "nber": {"kind": "id_set", "ids": ["w30000", "w30001"]},
        },
    }
    assert json.loads(json.dumps(payload, ensure_ascii=False)) == payload
    assert Watermark.parse(payload) == watermark


def test_empty_document_is_first_run() -> None:
    """`read_watermark` 对 NULL 返回 `{}` → 首跑（空文档是唯一合法的"缺省"）。"""
    assert Watermark.parse({}) == Watermark()
    assert Watermark().is_empty()
    assert Watermark().to_dict() == {"schema_ver": SCHEMA_VERSION, "sources": {}}


def test_with_state_replaces_in_place_and_keeps_order() -> None:
    watermark = _date_state("arxiv", "2026-07-20").with_state("nber", IdSetState(("w1",)))
    updated = watermark.with_state("arxiv", DateState("2026-07-24"))
    assert [name for name, _ in updated.states] == ["arxiv", "nber"]  # 原位替换，不挪到末尾
    assert updated.state_for("arxiv") == DateState("2026-07-24")
    assert watermark.state_for("arxiv") == DateState("2026-07-20")  # 原文档不被改


def test_with_state_rejects_unknown_source() -> None:
    with pytest.raises(WatermarkInvalid):
        Watermark().with_state("scholar", DateState("2026-07-20"))


def test_restrict_to_drops_ghost_cursors_of_unsubscribed_sources() -> None:
    """退订的源不留幽灵游标（`write_watermark` 整体覆盖，留谁删谁归本层裁决）。"""
    watermark = _date_state("arxiv", "2026-07-20").with_state("nber", IdSetState(("w1",)))
    kept = watermark.restrict_to(["arxiv"])
    assert [name for name, _ in kept.states] == ["arxiv"]
    assert kept.state_for("nber") is None  # 重新订阅 = 首跑（保守方向：重看不漏看）


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(
            lambda: DateUpperBound(source="x", param="p", overlap_days=-1), id="ub-overlap"
        ),
        pytest.param(
            lambda: DateUpperBound(source="x", param="p", initial_lookback_days=-1),
            id="ub-lookback",
        ),
        pytest.param(
            lambda: DateCursor(source="x", param="p", overlap_days=-3), id="cursor-overlap"
        ),
        pytest.param(
            lambda: DateCursor(source="x", param="p", initial_lookback_days=-7),
            id="cursor-lookback",
        ),
        pytest.param(lambda: IdSetDiff(source="x", max_ids=0), id="idset-zero"),
        pytest.param(lambda: IdSetDiff(source="x", max_ids=-5), id="idset-negative"),
    ],
)
def test_strategy_construction_rejects_out_of_domain_parameters(
    factory: Callable[[], object],
) -> None:
    """构造参数取值域：负天数/非正上限一律拒（负 overlap 会让水位往回走且静默生效）。"""
    with pytest.raises(WatermarkInvalid):
        factory()


def test_date_cursor_rejects_both_upper_bound_forms_at_once() -> None:
    """`until_param`（独立 until 参数）与 `range_suffix`（单参数区间）互斥。"""
    with pytest.raises(WatermarkInvalid) as excinfo:
        DateCursor(source="x", param="p", until_param="u", range_suffix=":")
    assert "互斥" in str(excinfo.value)


def test_state_type_mismatch_is_fail_loud_on_every_surface() -> None:
    """状态与策略不配对（编程错误）在三个面上都响亮拒绝，不静默当首跑。"""
    arxiv, nber = STRATEGIES["arxiv"], STRATEGIES["nber"]
    with pytest.raises(WatermarkInvalid):
        arxiv.advance(IdSetState(("a",)), [], now=TODAY)
    with pytest.raises(WatermarkInvalid):
        nber.advance(DateState("2026-07-20"), [])
    with pytest.raises(WatermarkInvalid):
        window_params(Watermark().with_state("nber", DateState("2026-07-20")), "nber", now=TODAY)
    with pytest.raises(WatermarkInvalid):
        Watermark().with_state("arxiv", IdSetState(("a",))).to_dict()
    with pytest.raises(WatermarkInvalid):
        Watermark().with_state("nber", DateState("2026-07-20")).to_dict()
    with pytest.raises(WatermarkInvalid):
        STRATEGIES["ssrn"].advance(IdSetState(("a",)), [], now=TODAY)


@pytest.mark.parametrize(
    ("raw", "needle"),
    [
        ({"sources": {}}, "schema_ver"),
        ({"schema_ver": 2, "sources": {}}, "未知 schema_ver"),
        ({"schema_ver": True, "sources": {}}, "必须是整数"),
        ({"schema_ver": "1", "sources": {}}, "必须是整数"),
        ({"schema_ver": 1}, "sources"),
        ({"schema_ver": 1, "sources": []}, "必须是映射"),
        ({"schema_ver": 1, "sources": None}, "实际是 空"),
        ({"schema_ver": 1, "sources": {}, "cursor": 1}, "未知字段"),
        ({"schema_ver": 1, "sources": {"scholar": {"kind": "date_cursor"}}}, "未知源"),
        ({"schema_ver": 1, "sources": {"arxiv": None}}, "必须是映射"),
        ({"schema_ver": 1, "sources": {"arxiv": {"date": "2026-07-22"}}}, "kind"),
        (
            {"schema_ver": 1, "sources": {"arxiv": {"kind": 7, "date": "2026-07-22"}}},
            "必须是字符串",
        ),
        ({"schema_ver": 1, "sources": {"arxiv": {"kind": "id_set", "ids": []}}}, "不符"),
        # D-029 前的旧格式（ssrn 曾是 id_set）现在必须响亮拒载，不能拿旧语义喂新策略
        ({"schema_ver": 1, "sources": {"ssrn": {"kind": "id_set", "ids": ["1"]}}}, "不符"),
        (
            {"schema_ver": 1, "sources": {"nber": {"kind": "date_cursor", "date": "2026-07-22"}}},
            "不符",
        ),
        ({"schema_ver": 1, "sources": {"arxiv": {"kind": "date_upper_bound"}}}, "date"),
        (
            {"schema_ver": 1, "sources": {"arxiv": {"kind": "date_upper_bound", "date": "昨天"}}},
            "ISO",
        ),
        (
            {
                "schema_ver": 1,
                "sources": {"arxiv": {"kind": "date_upper_bound", "date": "", "x": 1}},
            },
            "未知字段",
        ),
        ({"schema_ver": 1, "sources": {"nber": {"kind": "id_set"}}}, "ids"),
        ({"schema_ver": 1, "sources": {"nber": {"kind": "id_set", "ids": "a"}}}, "必须是列表"),
        ({"schema_ver": 1, "sources": {"nber": {"kind": "id_set", "ids": [1]}}}, "必须是字符串"),
        ({"schema_ver": 1, "sources": {"nber": {"kind": "id_set", "ids": ["  "]}}}, "空字符串"),
    ],
)
def test_parse_is_fail_loud(raw: dict[str, object], needle: str) -> None:
    """坏格式矩阵：一律 `WatermarkInvalid`(CONFIG)，绝不静默降级为"首跑"。"""
    with pytest.raises(WatermarkInvalid) as excinfo:
        Watermark.parse(raw)
    assert needle in str(excinfo.value)
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert excinfo.value.detail  # 定位串非空，CLI 可直指出错字段


def test_parse_rejects_id_set_beyond_the_cap() -> None:
    """外部改坏/旧版本写入的超长 id 集也拒载（上限是不变量，不是"尽力而为"）。"""
    ids = [f"w{n}" for n in range(DEFAULT_MAX_IDS + 1)]
    with pytest.raises(WatermarkInvalid) as excinfo:
        Watermark.parse({"schema_ver": 1, "sources": {"nber": {"kind": "id_set", "ids": ids}}})
    assert "超出上限" in str(excinfo.value)


def test_parse_normalises_timestamp_dates_to_iso_day() -> None:
    """文档里写完整时间戳也认，但归一存回日期（避免两种写法在库里并存）。"""
    parsed = Watermark.parse(
        {
            "schema_ver": 1,
            "sources": {"crossref": {"kind": "date_cursor", "date": "2026-07-22T10:00:00Z"}},
        }
    )
    assert parsed.state_for("crossref") == DateState("2026-07-22")


# ---------------------------------------------------------------------------
# 推进 ≠ 提交：run 成功才落库（走真 sqlite）
# ---------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[SubscriptionRepo]:
    database = Database(tmp_path / "subs.sqlite")
    database.migrate()
    yield SubscriptionRepo(database)
    database.close()


def _subscription() -> Subscription:
    return parse_subscription(
        {
            "name": "llm-agents",
            "sources": {"arxiv": {"categories": ["cs.LG"]}, "ssrn": {"networks": ["fen"]}},
        }
    )


def test_repo_round_trip_of_the_watermark_document(repo: SubscriptionRepo) -> None:
    """`read_watermark`/`write_watermark`（dict 进出）与本层对象形态严丝合缝。"""
    subscription = _subscription()
    repo.upsert(subscription)
    assert Watermark.parse(repo.read_watermark(subscription.name)) == Watermark()  # 首跑

    watermark = _date_state("arxiv", "2026-07-22").with_state("ssrn", DateState("2026-07-21"))
    repo.write_watermark(subscription.name, watermark.to_dict())
    assert Watermark.parse(repo.read_watermark(subscription.name)) == watermark


def test_candidate_is_not_committed_until_the_run_succeeds(repo: SubscriptionRepo) -> None:
    """**推进纪律核心**：熔断/失败路径不调 `write_watermark` → 库里仍是旧水位。

    候选与提交分离的好处正在这里：不需要回滚，也不可能"推进了一半"。
    """
    subscription = _subscription()
    repo.upsert(subscription)

    # run 1 成功：算候选 → 显式提交。
    committed = advance(
        Watermark.parse(repo.read_watermark(subscription.name)), "arxiv", ["2026-07-20"], now=TODAY
    )
    repo.write_watermark(subscription.name, committed.to_dict())
    assert Watermark.parse(repo.read_watermark(subscription.name)) == committed

    # run 2 熔断（或失败）：候选算出来了，但**不提交**。
    stored = Watermark.parse(repo.read_watermark(subscription.name))
    candidate = advance(stored, "arxiv", ["2026-07-24"], now=TODAY)
    assert candidate.state_for("arxiv") == DateState("2026-07-24")
    assert Watermark.parse(repo.read_watermark(subscription.name)) == committed  # 读回旧值

    # run 3：因为没推进，07-24 那条仍落在新窗内（宁可重看不可漏看）。
    reread = Watermark.parse(repo.read_watermark(subscription.name))
    assert window_params(reread, "arxiv", now=TODAY) == (
        ("submittedDate", "[202607190000 TO 202607262359]"),
    )
    repo.write_watermark(subscription.name, candidate.to_dict())
    assert Watermark.parse(repo.read_watermark(subscription.name)) == candidate


def test_stored_document_with_unknown_schema_is_not_silently_a_first_run(
    repo: SubscriptionRepo,
) -> None:
    """库里存着未来版本/损坏的文档 → 响亮拒载，不当成首跑把整窗重刷一遍。"""
    subscription = _subscription()
    repo.upsert(subscription)
    repo.write_watermark(subscription.name, {"schema_ver": 99, "sources": {}})
    with pytest.raises(WatermarkInvalid):
        Watermark.parse(repo.read_watermark(subscription.name))


def test_restrict_to_before_commit_clears_unsubscribed_sources(repo: SubscriptionRepo) -> None:
    """提交前按订阅当前 `sources` 过一道：退订的源不在库里留幽灵游标。"""
    subscription = _subscription()
    repo.upsert(subscription)
    stale = _date_state("arxiv", "2026-07-22").with_state("nber", IdSetState(("w30000",)))
    repo.write_watermark(
        subscription.name, stale.restrict_to(subscription.source_names()).to_dict()
    )

    reread = Watermark.parse(repo.read_watermark(subscription.name))
    assert reread.state_for("nber") is None
    assert reread.state_for("arxiv") == DateState("2026-07-22")
