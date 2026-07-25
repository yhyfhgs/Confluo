"""subs/report.py（Phase 6 T6）渲染器单测：golden 快照 + 边界场景。

风格对齐 `tests/unit/test_report.py`（`pipeline/report.py` 姊妹测试）：用小型
construct helper 装配 `RunSummary`/`ReportEntry`/`FailureEvent`，多数用例断言
渲染 markdown 的关键片段；三例 golden 快照（正常多订阅/含熔断+失败/空日，DoD
硬性要求）额外做字符级全文比对，fixture 存 `tests/fixtures/subs/golden/`。

Golden 记录纪律同 `tests/helpers/golden.py`（test-plan §2）：文件缺失或
`UPDATE_GOLDEN=1` 时先写入当前输出再 fail（强制人工过目 diff），非记录模式下
精确字符串比对。本文件未复用 `tests/helpers/golden.py`（其 `assert_matches_golden`
只认 dataclass→canonical JSON，本卡需要的是原始 markdown 文本的字符级比对），
自带一个纯文本版的等价小工具，不改动共享测试基建。
"""

from __future__ import annotations

import difflib
import os
from collections.abc import Sequence
from pathlib import Path

import pytest

from paper_crawler.subs.report import render_daily
from paper_crawler.subs.types import FailureEvent, ReportEntry, RunSummary, WatchOutcome

_GOLDEN_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "subs" / "golden"


def _assert_golden_md(text: str, name: str) -> None:
    path = _GOLDEN_DIR / name
    should_record = os.environ.get("UPDATE_GOLDEN") == "1" or not path.exists()

    if should_record:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        pytest.fail(
            f"golden (re)recorded, review diff: {path}\n"
            "重录后必须人工检查内容再提交（test-plan §2）；无误后去掉 "
            "UPDATE_GOLDEN=1 重跑本测试应转绿。"
        )

    expected = path.read_text(encoding="utf-8")
    if text != expected:
        diff = "\n".join(
            difflib.unified_diff(
                expected.splitlines(),
                text.splitlines(),
                fromfile=f"{path} (expected)",
                tofile="actual",
                lineterm="",
            )
        )
        pytest.fail(f"golden mismatch for {path}:\n{diff}")


# ---------------------------------------------------------------------------
# construct helpers
# ---------------------------------------------------------------------------


def _entry(**overrides: object) -> ReportEntry:
    defaults: dict[str, object] = {
        "title": "Agentic Tool Use",
        "authors": ("A. Author", "B. Author"),
        "url": "https://arxiv.org/abs/2401.00001",
        "matched_rules": ("title_regex_any[0]",),
        "source": "arxiv",
        "categories": ("cs.AI",),
    }
    defaults.update(overrides)
    return ReportEntry(**defaults)  # type: ignore[arg-type]


def _failure(**overrides: object) -> FailureEvent:
    defaults: dict[str, object] = {
        "source": "ssrn",
        "error_class": "transient",
        "message": "连接超时",
    }
    defaults.update(overrides)
    return FailureEvent(**defaults)  # type: ignore[arg-type]


def _summary(**overrides: object) -> RunSummary:
    defaults: dict[str, object] = {
        "subscription": "llm-agents",
        "started_at": "2026-07-26T00:00:00+00:00",
        "finished_at": "2026-07-26T00:05:00+00:00",
    }
    defaults.update(overrides)
    return RunSummary(**defaults)  # type: ignore[arg-type]


def _overload_entries(
    source_counts: Sequence[tuple[str, int]], categories: Sequence[str]
) -> tuple[ReportEntry, ...]:
    """构造 N 条熔断候选：`source_counts` 按 (source, count) 顺序铺开；`categories`
    按索引循环分配（长度须整除总数，测试内部保证），用于过载分布的确定性用例。
    """
    entries: list[ReportEntry] = []
    index = 0
    for source, count in source_counts:
        for _ in range(count):
            category = categories[index % len(categories)]
            entries.append(
                _entry(
                    title=f"Overload Candidate {index:03d}",
                    authors=("Author X",),
                    url=f"https://example.org/{index}",
                    matched_rules=("title_regex_any[0]",),
                    source=source,
                    categories=(category,),
                )
            )
            index += 1
    return tuple(entries)


# ---------------------------------------------------------------------------
# golden 快照三例（DoD 硬性要求：字符级稳定）
# ---------------------------------------------------------------------------


def test_golden_normal_multi_subscription() -> None:
    """正常多订阅：均 OK，无熔断无失败；含一个 dry-run 预览订阅。"""
    llm_agents = _summary(
        subscription="llm-agents",
        outcome=WatchOutcome.OK,
        new_count=2,
        ingested_count=2,
        library_total=42,
        guard_limit=200,
        entries=(
            _entry(
                title="Agentic Tool Use in LLMs",
                authors=("Alice Author", "Bob Author"),
                url="https://arxiv.org/abs/2401.00001",
                matched_rules=("title_regex_any[0]",),
                source="arxiv",
                categories=("cs.AI", "cs.LG"),
            ),
            _entry(
                title="Tool-Augmented Reasoning",
                authors=("Carol Cho",),
                url="https://arxiv.org/abs/2401.00002",
                matched_rules=("title_regex_any[1]", "exclude_regex[0]"),
                source="arxiv",
                categories=("cs.CL",),
            ),
        ),
    )
    asset_pricing = _summary(
        subscription="asset-pricing-wp",
        outcome=WatchOutcome.OK,
        dry_run=True,
        new_count=1,
        ingested_count=0,
        library_total=17,
        guard_limit=100,
        entries=(
            _entry(
                title="Cross-Section of Expected Returns Revisited",
                authors=(),
                url="https://papers.ssrn.com/sol3/papers.cfm?abstract_id=999999",
                matched_rules=("title_regex_any[0]",),
                source="ssrn",
                categories=(),
            ),
        ),
    )

    text = render_daily([llm_agents, asset_pricing], date="2026-07-26")
    _assert_golden_md(text, "daily-normal-multi.md")


def test_golden_truncated_and_failure() -> None:
    """一订阅熔断（250>阈值100，过载分布数据驱动源=distribution）+ 另一订阅含
    失败事件（含凭证脱敏）。T1b 接缝终裁后：熔断路径只带 `distribution`（T5 从
    `subs.guard.OverloadReport` 装配），不带全量 `entries`（真实场景：T5 不会为
    过载报告物化 250 条 `ReportEntry`）。
    """
    truncated = _summary(
        subscription="asset-pricing-wp",
        outcome=WatchOutcome.TRUNCATED,
        new_count=250,
        ingested_count=0,
        library_total=900,
        guard_limit=100,
        entries=(),
        distribution=(
            ("source", "arxiv", 150),
            ("source", "nber", 70),
            ("source", "ssrn", 30),
            ("category", "cs.LG", 130),
            ("category", "cs.AI", 120),
        ),
    )
    with_failure = _summary(
        subscription="llm-agents",
        outcome=WatchOutcome.OK,
        new_count=2,
        ingested_count=2,
        library_total=45,
        guard_limit=200,
        entries=(
            _entry(
                title="Emergent Tool Use",
                authors=("Dana Doe",),
                url="https://arxiv.org/abs/2402.00001",
                matched_rules=("title_regex_any[0]",),
                source="arxiv",
                categories=("cs.AI",),
            ),
            _entry(
                title="Planning with LLM Agents",
                authors=("Eve Smith", "Frank Lee"),
                url="https://arxiv.org/abs/2402.00002",
                matched_rules=("title_regex_any[0]", "min_year"),
                source="arxiv",
                categories=("cs.AI", "cs.MA"),
            ),
        ),
        failures=(
            _failure(
                source="openalex",
                error_class="rate_limited",
                message="HTTP 429 Authorization: Bearer sometoken123456",
            ),
        ),
    )

    text = render_daily([truncated, with_failure], date="2026-07-26")
    _assert_golden_md(text, "daily-truncated-failure.md")
    # 落盘前先在源头断言脱敏生效（golden 文件本身也不含明文 token，双重锁定）。
    assert "sometoken123456" not in text
    assert "Authorization: ***" in text


def test_golden_empty_day() -> None:
    """空日：零订阅——仍产合法文档 + 明确"无新增"语句。"""
    text = render_daily([], date="2026-07-27")
    _assert_golden_md(text, "daily-empty-day.md")


# ---------------------------------------------------------------------------
# 总览表
# ---------------------------------------------------------------------------


def test_overview_table_lists_every_subscription_with_five_columns() -> None:
    a = _summary(subscription="sub-a", new_count=3, ingested_count=3)
    b = _summary(
        subscription="sub-b", outcome=WatchOutcome.TRUNCATED, new_count=500, guard_limit=100
    )
    md = render_daily([a, b], date="2026-07-26")

    assert "| 订阅 | 状态 | 新增 | 入库 | 熔断 |" in md
    assert "| sub-a | ok | 3 | 3 | - |" in md
    assert "| sub-b | truncated | 500 | 0 | 熔断 |" in md


def test_overview_row_order_follows_input_order() -> None:
    first = _summary(subscription="zzz-last")
    second = _summary(subscription="aaa-first")
    md = render_daily([first, second], date="2026-07-26")

    assert md.index("| zzz-last |") < md.index("| aaa-first |")


# ---------------------------------------------------------------------------
# dry-run 标记
# ---------------------------------------------------------------------------


def test_dry_run_marker_appears_in_overview_and_section_status() -> None:
    summary = _summary(subscription="preview-sub", dry_run=True, new_count=5, ingested_count=0)
    md = render_daily([summary], date="2026-07-26")

    assert "| preview-sub | ok（预览，未入库） | 5 | 0 | - |" in md
    assert "- 状态: ok（预览，未入库）" in md


def test_no_dry_run_marker_when_dry_run_false() -> None:
    summary = _summary(dry_run=False)
    md = render_daily([summary], date="2026-07-26")

    assert "预览" not in md


def test_dry_run_orthogonal_to_truncated_outcome() -> None:
    """dry-run 也可能"本会熔断"：状态标记预览，但熔断提示/过载分布正常渲染。"""
    summary = _summary(
        outcome=WatchOutcome.TRUNCATED,
        dry_run=True,
        new_count=300,
        guard_limit=100,
        ingested_count=0,
        entries=(_entry(source="arxiv"),),
    )
    md = render_daily([summary], date="2026-07-26")

    assert "- 状态: truncated（预览，未入库）" in md
    assert "熔断：本次新增 300 篇超过阈值 100" in md
    assert "### 过载分布" in md


# ---------------------------------------------------------------------------
# 每订阅节：新增清单
# ---------------------------------------------------------------------------


def test_entries_section_renders_title_authors_url_matched_rules() -> None:
    summary = _summary(
        entries=(
            _entry(
                title="Some Title",
                authors=("X. Author", "Y. Author"),
                url="https://arxiv.org/abs/1",
                matched_rules=("title_regex_any[0]", "min_year"),
            ),
        )
    )
    md = render_daily([summary], date="2026-07-26")

    assert "### 新增清单" in md
    assert "| 标题 | 作者 | 链接 | 命中规则 |" in md
    row = "| Some Title | X. Author, Y. Author | https://arxiv.org/abs/1 | "
    assert row + "title_regex_any[0], min_year |" in md


def test_entries_section_uses_dash_for_empty_authors_and_matched_rules() -> None:
    summary = _summary(entries=(_entry(authors=(), matched_rules=()),))
    md = render_daily([summary], date="2026-07-26")

    assert "| Agentic Tool Use | - | https://arxiv.org/abs/2401.00001 | - |" in md


def test_zero_entries_non_truncated_shows_no_new_papers_sentence() -> None:
    summary = _summary(entries=())
    md = render_daily([summary], date="2026-07-26")

    assert "无新增论文。" in md
    assert "### 新增清单" not in md


def test_table_cell_pipe_character_is_escaped() -> None:
    summary = _summary(entries=(_entry(title="A | B: Title with Pipe"),))
    md = render_daily([summary], date="2026-07-26")

    assert "A \\| B: Title with Pipe" in md


# ---------------------------------------------------------------------------
# 熔断：显著提示 + 过载分布（新增清单被抑制）
# ---------------------------------------------------------------------------


def test_truncated_suppresses_entries_table_shows_overload_section() -> None:
    """`distribution` 留空（默认）——走 entries 兜底聚合路径。"""
    summary = _summary(
        outcome=WatchOutcome.TRUNCATED,
        new_count=250,
        guard_limit=100,
        ingested_count=0,
        entries=_overload_entries([("arxiv", 2), ("nber", 1)], ["cs.AI"]),
    )
    md = render_daily([summary], date="2026-07-26")

    assert "熔断：本次新增 250 篇超过阈值 100（guard.max_new_per_run）" in md
    assert "### 过载分布" in md
    assert "### 新增清单" not in md


def test_overload_distribution_sorted_by_count_desc_then_name_asc() -> None:
    """entries 兜底路径：`distribution` 留空。"""
    summary = _summary(
        outcome=WatchOutcome.TRUNCATED,
        new_count=6,
        guard_limit=1,
        entries=_overload_entries([("arxiv", 1), ("nber", 3), ("ssrn", 2)], ["cs.AI"]),
    )
    md = render_daily([summary], date="2026-07-26")

    # nber(3) > ssrn(2) > arxiv(1)
    assert md.index("| nber | 3 |") < md.index("| ssrn | 2 |") < md.index("| arxiv | 1 |")


def test_overload_category_distribution_tie_breaks_by_name() -> None:
    """entries 兜底路径：`distribution` 留空。"""
    summary = _summary(
        outcome=WatchOutcome.TRUNCATED,
        new_count=4,
        guard_limit=1,
        entries=_overload_entries([("arxiv", 4)], ["cs.LG", "cs.AI"]),  # 2 each, tie
    )
    md = render_daily([summary], date="2026-07-26")

    assert md.index("| cs.AI | 2 |") < md.index("| cs.LG | 2 |")


def test_narrowing_suggestion_names_top_source_and_category() -> None:
    """entries 兜底路径：`distribution` 留空。"""
    summary = _summary(
        outcome=WatchOutcome.TRUNCATED,
        new_count=10,
        guard_limit=1,
        entries=_overload_entries([("arxiv", 8), ("nber", 2)], ["cs.AI"] * 6 + ["cs.LG"] * 4),
    )
    md = render_daily([summary], date="2026-07-26")

    assert (
        "收窄建议：优先考虑收窄 来源 `arxiv`（8 篇，占 80.0%） 或 分类 `cs.AI`（6 篇，占 60.0%）。"
        in md
    )


def test_narrowing_suggestion_when_only_category_distribution_available() -> None:
    """entries 兜底路径：缺失 source（空字符串，`_count_sources` 跳过）——按分类分布仍可用。"""
    summary = _summary(
        outcome=WatchOutcome.TRUNCATED,
        new_count=3,
        guard_limit=1,
        entries=(
            _entry(source="", categories=("cs.AI",)),
            _entry(source="", categories=("cs.AI",)),
            _entry(source="", categories=("cs.LG",)),
        ),
    )
    md = render_daily([summary], date="2026-07-26")

    assert "| - | 0 |" in md  # 按来源分布：空，占位行
    assert "| cs.AI | 2 |" in md
    assert "收窄建议：优先考虑收窄 分类 `cs.AI`（2 篇，占 66.7%）。" in md


def test_narrowing_suggestion_when_only_source_distribution_available() -> None:
    """entries 兜底路径：无分类信息（如某些源天然无分类）——按来源分布仍可用。"""
    summary = _summary(
        outcome=WatchOutcome.TRUNCATED,
        new_count=2,
        guard_limit=1,
        entries=(
            _entry(source="ssrn", categories=()),
            _entry(source="ssrn", categories=()),
        ),
    )
    md = render_daily([summary], date="2026-07-26")

    assert "收窄建议：优先考虑收窄 来源 `ssrn`（2 篇，占 100.0%）。" in md


def test_overload_distribution_falls_back_to_placeholder_when_both_sources_empty() -> None:
    """防御性边界：`distribution` 与 `entries` 均为空——不崩溃，占位行。"""
    summary = _summary(
        outcome=WatchOutcome.TRUNCATED, new_count=500, guard_limit=100, entries=(), distribution=()
    )
    md = render_daily([summary], date="2026-07-26")

    assert "| 来源 | 数量 |" in md
    assert "| 分类 | 数量 |" in md
    assert "| - | 0 |" in md
    assert "暂无可用于建议收窄的来源/分类分布数据" in md


# ---------------------------------------------------------------------------
# distribution 优先路径（T1b 接缝终裁：RunSummary.distribution 三元组）
# ---------------------------------------------------------------------------


def test_distribution_field_takes_priority_over_entries_when_both_present() -> None:
    """`distribution` 非空时优先消费——即便 `entries` 同时给出不同的数据，也应
    被忽略（design 决策：T5 可能只带 distribution 不带全量 entries；两者都给出
    时 distribution 是权威——T3 `OverloadReport` 装配的量，entries 未必完整）。
    """
    summary = _summary(
        outcome=WatchOutcome.TRUNCATED,
        new_count=5,
        guard_limit=1,
        entries=_overload_entries([("nber", 5)], ["cs.GT"]),  # 若被消费会呈现 nber/cs.GT
        distribution=(("source", "arxiv", 5), ("category", "cs.AI", 5)),
    )
    md = render_daily([summary], date="2026-07-26")

    assert "| arxiv | 5 |" in md
    assert "| cs.AI | 5 |" in md
    assert "nber" not in md
    assert "cs.GT" not in md
    prefix = "收窄建议：优先考虑收窄 来源 `arxiv`（5 篇，占 100.0%） 或 "
    assert prefix + "分类 `cs.AI`（5 篇，占 100.0%）。" in md


def test_distribution_axis_filter_ignores_unknown_axis_values() -> None:
    """防御性：非文档取值域的 axis（如拼写错误）被静默忽略，不进两张表也不崩溃。"""
    summary = _summary(
        outcome=WatchOutcome.TRUNCATED,
        new_count=3,
        guard_limit=1,
        distribution=(("source", "arxiv", 3), ("venue", "ignored-axis", 99)),
    )
    md = render_daily([summary], date="2026-07-26")

    assert "| arxiv | 3 |" in md
    assert "ignored-axis" not in md
    assert "99" not in md


def test_distribution_empty_falls_back_to_entries_derivation() -> None:
    """`distribution` 显式留空元组（T5 默认值）——落回 entries 聚合，行为不变。"""
    summary = _summary(
        outcome=WatchOutcome.TRUNCATED,
        new_count=2,
        guard_limit=1,
        distribution=(),
        entries=_overload_entries([("arxiv", 2)], ["cs.AI"]),
    )
    md = render_daily([summary], date="2026-07-26")

    assert "| arxiv | 2 |" in md


# ---------------------------------------------------------------------------
# entries 兜底路径：条目内重复标签去重（审查 P2#4，同 subs.guard._counts_by 修法对齐）
# ---------------------------------------------------------------------------


def test_entries_fallback_dedupes_repeated_category_within_single_entry() -> None:
    """单条目内 `categories` 重复标签（如 arXiv 主分类与 cross-list 同值）只计一次，
    不应让该分类计数超过实际拥有该标签的条目数（P2#4，与 `subs.guard._counts_by`
    同款修法对齐）。3 个条目：条目 1 categories=("cs.AI","cs.AI")（条目内重复）、
    条目 2 categories=("cs.AI",)、条目 3 categories=("cs.LG",)——正确计数应是
    cs.AI=2（按条目数，不是标签出现次数 3）、cs.LG=1。
    """
    summary = _summary(
        outcome=WatchOutcome.TRUNCATED,
        new_count=3,
        guard_limit=1,
        distribution=(),  # 走 entries 兜底路径
        entries=(
            _entry(source="arxiv", categories=("cs.AI", "cs.AI")),
            _entry(source="arxiv", categories=("cs.AI",)),
            _entry(source="arxiv", categories=("cs.LG",)),
        ),
    )
    md = render_daily([summary], date="2026-07-26")

    assert "| cs.AI | 2 |" in md
    assert "| cs.AI | 3 |" not in md
    assert "| cs.LG | 1 |" in md


# ---------------------------------------------------------------------------
# 失败事件（与熔断/新增清单正交）
# ---------------------------------------------------------------------------


def test_failures_section_renders_source_error_class_message() -> None:
    summary = _summary(
        failures=(_failure(source="ssrn", error_class="transient", message="连接超时"),)
    )
    md = render_daily([summary], date="2026-07-26")

    assert "### 失败事件" in md
    assert "| 来源 | 错误类型 | 消息 |" in md
    assert "| ssrn | transient | 连接超时 |" in md


def test_failures_section_absent_when_no_failures() -> None:
    md = render_daily([_summary(failures=())], date="2026-07-26")
    assert "失败事件" not in md


def test_failures_section_redacts_credential_shaped_message() -> None:
    summary = _summary(failures=(_failure(message="Cookie: session=abc123456"),))
    md = render_daily([summary], date="2026-07-26")

    assert "abc123456" not in md
    assert "Cookie: ***" in md


def test_failures_coexist_with_entries_for_same_subscription() -> None:
    summary = _summary(
        entries=(_entry(),),
        failures=(_failure(),),
    )
    md = render_daily([summary], date="2026-07-26")

    assert "### 新增清单" in md
    assert "### 失败事件" in md


# ---------------------------------------------------------------------------
# WatchOutcome.FAILED（P2 补测：状态行 + 无新增 + 失败事件表，三者同现）
# ---------------------------------------------------------------------------


def test_failed_outcome_renders_status_line_no_new_papers_and_failures_table() -> None:
    """FAILED（本订阅整体失败，`subs/types.py` `WatchOutcome` docstring："全部源
    失败等"）的典型形态：总览/状态行标 `failed`；零新增走"无新增论文。"（与
    TRUNCATED 的"过载分布"分支互斥——FAILED 不熔断，`truncated` property 为
    False）；失败事件表照常列出每个失败源。"""
    summary = _summary(
        subscription="asset-pricing-wp",
        outcome=WatchOutcome.FAILED,
        new_count=0,
        ingested_count=0,
        library_total=900,
        guard_limit=100,
        entries=(),
        failures=(
            _failure(source="ssrn", error_class="transient", message="连接超时"),
            _failure(source="nber", error_class="transient", message="连接超时"),
        ),
    )
    md = render_daily([summary], date="2026-07-26")

    assert "| asset-pricing-wp | failed | 0 | 0 | - |" in md  # 总览行：非熔断，熔断列为 "-"
    assert "- 状态: failed" in md
    assert "无新增论文。" in md
    assert "### 过载分布" not in md  # FAILED ≠ TRUNCATED：不产过载分布
    assert "### 新增清单" not in md
    assert "### 失败事件" in md
    assert "| ssrn | transient | 连接超时 |" in md
    assert "| nber | transient | 连接超时 |" in md


def test_failed_outcome_with_dry_run_marker() -> None:
    """FAILED + dry_run=True（正交：预览运行也可能整体失败）——状态行两个标记并存。"""
    summary = _summary(
        outcome=WatchOutcome.FAILED,
        dry_run=True,
        new_count=0,
        ingested_count=0,
        entries=(),
        failures=(_failure(),),
    )
    md = render_daily([summary], date="2026-07-26")

    assert "- 状态: failed（预览，未入库）" in md


# ---------------------------------------------------------------------------
# 空日（零订阅 / 零新增）
# ---------------------------------------------------------------------------


def test_zero_subscriptions_yields_minimal_valid_document() -> None:
    md = render_daily([], date="2026-07-27")

    assert md.startswith("# 日报 — 2026-07-27")
    assert "无新增" in md


def test_all_subscriptions_zero_new_still_valid_per_section() -> None:
    a = _summary(subscription="sub-a", new_count=0, entries=())
    b = _summary(subscription="sub-b", new_count=0, entries=())
    md = render_daily([a, b], date="2026-07-26")

    assert md.count("无新增论文。") == 2


# ---------------------------------------------------------------------------
# 尾部：累计库存
# ---------------------------------------------------------------------------


def test_inventory_section_lists_all_subscriptions_library_total() -> None:
    a = _summary(subscription="sub-a", library_total=10)
    b = _summary(subscription="sub-b", library_total=20)
    md = render_daily([a, b], date="2026-07-26")

    assert "## 累计库存" in md
    assert "| 订阅 | 累计库存 |" in md
    assert "| sub-a | 10 |" in md
    assert "| sub-b | 20 |" in md


def test_inventory_section_is_last_top_level_section() -> None:
    md = render_daily([_summary()], date="2026-07-26")
    h2_headings = [line for line in md.splitlines() if line.startswith("## ")]
    assert h2_headings[-1] == "## 累计库存"


# ---------------------------------------------------------------------------
# 结构完整性：标题层级 / 收尾换行
# ---------------------------------------------------------------------------


def test_document_ends_with_single_trailing_newline() -> None:
    md = render_daily([_summary()], date="2026-07-26")
    assert md.endswith("\n")
    assert not md.endswith("\n\n")


def test_no_triple_blank_lines_anywhere() -> None:
    truncated = _summary(
        subscription="t",
        outcome=WatchOutcome.TRUNCATED,
        new_count=10,
        guard_limit=1,
        entries=(_entry(),),
        failures=(_failure(),),
    )
    quiet = _summary(subscription="q", entries=())
    md = render_daily([truncated, quiet], date="2026-07-26")

    assert "\n\n\n" not in md


def test_heading_hierarchy_is_h1_h2_h3_only() -> None:
    summary = _summary(
        outcome=WatchOutcome.TRUNCATED,
        new_count=10,
        guard_limit=1,
        entries=(_entry(),),
        failures=(_failure(),),
    )
    md = render_daily([summary], date="2026-07-26")

    headings = [line for line in md.splitlines() if line.startswith("#")]
    assert headings[0].startswith("# ") and not headings[0].startswith("## ")
    assert all(line.startswith(("# ", "## ", "### ")) for line in headings)
    assert "#### " not in md


# ---------------------------------------------------------------------------
# 风格：无 emoji / 加粗 / 引用块（对齐 pipeline/report.py 先例）
# ---------------------------------------------------------------------------


def test_no_bold_or_blockquote_markdown_constructs() -> None:
    summary = _summary(
        outcome=WatchOutcome.TRUNCATED,
        new_count=10,
        guard_limit=1,
        entries=(_entry(),),
        failures=(_failure(),),
    )
    md = render_daily([summary], date="2026-07-26")

    assert "**" not in md
    assert not any(line.startswith(">") for line in md.splitlines())
