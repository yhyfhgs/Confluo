"""数量护栏引擎（Phase 6 T3；design/09 §6 护栏与报告 + §5 末"全源统一…去重"）。

三件事，各自独立、供 T5（watch runner）编排调用：

1. `is_truncated`——`guard.max_new_per_run` 熔断判定（design/09 §6.1"超过即熔断：只出
   报告不入库"）：**净新增数严格大于阈值才熔断，等于阈值放行**（`max_new_per_run` 是
   "至多这么多"的上界声明——用户写 200 意味着"200 篇以内我能接受"，不是"少于 200"）。
2. `dedupe_against_library`——`guard.dedupe_against_library` 为真时，候选 `PaperStub`
   流按 identifier `(scheme,value)` 与既有库比对（design/09 §5 末"全源统一：入库前对
   (scheme,value) 去重 → 无重复由 identifier 主键保证"）。
3. `OverloadReport` + `build_overload_report`——熔断后的过载报告**数据**（计数/按源
   分布/按类目分布/收窄建议文本）；markdown 排版归 T6（plan §4 T3 接缝裁决③），本模块
   只产数据结构，不拼 markdown。

## 设计取舍

- `dedupe_against_library` 接收 `Database`（而非 `Repo`）：判重只需要对 `identifier`
  表的只读查询，`Repo` 是全领域读写仓储（`upsert_paper`/`merge_ingest` 等写路径）——
  引入它会让 guard.py 意外拿到不需要的写能力面。`Database.query` 已是既有代码复用的
  公开只读接口（`tests/integration/test_subscription_repo.py` 里 `repo.db.query(...)`
  的直接调用先例，`SubscriptionRepo` 同样只用它做只读校验）。
- identifier 归一复用 `ids.normalize_identifier`——与 `Repo.upsert_paper`/`MergeEngine`
  写入前的归一化是**同一个函数**，判重口径与入库口径不会漂移（如 DOI 大小写/前缀异形
  在两条路径下都会被折成同一 `(scheme,value)`）。
- 一个 stub 的**任一** identifier 命中库内既有记录即判定"库中已有"：`identifier` 是
  全局唯一强合并锚点（design/06 §3），单个命中已充分证明同一著作已入库。
- 零 identifier 的 stub（理论上不应出现——`PaperStub.identifiers` 契约"至少 1 个"，见
  `types.py` docstring）视为"库中没有"：无法证明已存在时保守判新，不臆造一个"存在"的
  结论。
- `OverloadReport.by_category` 按**多标签**计数：一条目多个 category（如 arXiv 论文
  同时属 `cs.AI`/`cs.LG`）在各自桶各计一次——"分布"回答"新增内容集中在哪些类目"，
  不是"论文数之和"，两桶合计因此可能大于 `new_count`（预期行为，非 bug）。
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from paper_crawler.ids import normalize_identifier
from paper_crawler.storage.db import Database
from paper_crawler.subs.types import ReportEntry
from paper_crawler.types import PaperStub

# --- 熔断判定 ----------------------------------------------------------------


def is_truncated(new_count: int, max_new_per_run: int) -> bool:
    """`guard.max_new_per_run` 熔断判定（design/09 §6.1）。

    **严格大于**阈值才熔断；等于阈值不熔断（"至多 N 篇"语义，非"少于 N 篇"）。
    """
    return new_count > max_new_per_run


# --- 去重对库 ------------------------------------------------------------------


@dataclass(frozen=True)
class DedupeResult:
    """`dedupe_against_library` 的返回：按"库中是否已有"切成两半，各自保持输入序。"""

    new: tuple[PaperStub, ...] = ()
    duplicates: tuple[PaperStub, ...] = ()


def _identifier_in_library(db: Database, scheme: str, value: str) -> bool:
    """单个 (scheme,value)（已归一）是否已存在于 `identifier` 表——存在性查询，不取值。"""
    norm_scheme, norm_value = normalize_identifier(scheme, value)
    rows = db.query(
        "SELECT 1 FROM identifier WHERE scheme = ? AND value = ? LIMIT 1",
        (norm_scheme, norm_value),
    )
    return bool(rows)


def dedupe_against_library(stubs: Iterable[PaperStub], db: Database) -> DedupeResult:
    """候选流按 identifier `(scheme,value)` 与既有库比对；任一 identifier 命中即"库中已有"。

    `db` 是既有 `storage.db.Database`（`Repo`/`SubscriptionRepo` 共用的同一连接封装）；
    本函数只读，不修改任何数据。返回的 `new`/`duplicates` 各自保持 `stubs` 的原始相对
    顺序（不重排、不去重同批内部的重复——同批内部重复由上游 `merge`/合并逻辑处理，不是
    "对库去重"的职责）。
    """
    new: list[PaperStub] = []
    duplicates: list[PaperStub] = []
    for stub in stubs:
        in_library = any(
            _identifier_in_library(db, scheme, value) for scheme, value in stub.identifiers
        )
        (duplicates if in_library else new).append(stub)
    return DedupeResult(new=tuple(new), duplicates=tuple(duplicates))


# --- 过载报告 ------------------------------------------------------------------


@dataclass(frozen=True)
class OverloadReport:
    """熔断后的过载报告数据（design/09 §6.1）。markdown 渲染归 T6，本类只产数据结构。"""

    subscription: str
    new_count: int
    guard_limit: int
    by_source: tuple[tuple[str, int], ...] = ()  # (source, count)；count 降序、source 升序
    by_category: tuple[tuple[str, int], ...] = ()  # (category, count)；同上排序，多标签各计一次
    suggestion: str = ""  # 收窄建议纯文本（T6 决定排版）


def _counts_by(
    entries: Sequence[ReportEntry], labels_of: Callable[[ReportEntry], Iterable[str]]
) -> tuple[tuple[str, int], ...]:
    """按 `labels_of` 抽取的标签计数，输出确定性排序（count 降序、label 升序打破平局）。

    **条目内去重、跨条目正常累计**：`labels_of(entry)` 在同一条目内重复的标签
    （`ReportEntry.categories` 是源侧原始元组，无去重契约——如 arXiv 主分类与
    cross-list 可能同值）只计一次（`dict.fromkeys` 保序去重）；不同条目共享同一
    标签则各自正常计数。否则单条目内的重复会让某个桶的计数超过实际拥有该标签的
    条目数，`_suggest_narrowing` 算出的份额可能溢出 100%（P2#4，审查发现）。
    """
    counts: dict[str, int] = {}
    for entry in entries:
        for label in dict.fromkeys(labels_of(entry)):
            counts[label] = counts.get(label, 0) + 1
    return tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _suggest_narrowing(
    *,
    new_count: int,
    guard_limit: int,
    by_source: tuple[tuple[str, int], ...],
    by_category: tuple[tuple[str, int], ...],
) -> str:
    """收窄建议：来源/类目两条候选取占比（占 `new_count` 比例）更高者，提示具体收窄动作。

    份额相同时优先"来源"（收紧源头选择器比事后补 exclude 更直接止损；来源候选先入列表，
    `max` 对相等的键稳定取首个，从而确定性地偏向来源）。
    """
    header = (
        f"新增 {new_count} 篇超过护栏阈值 {guard_limit}（max_new_per_run），本次已熔断、零入库。"
    )
    if new_count == 0:
        return header

    candidates: list[tuple[float, str, str, int, str]] = []
    if by_source:
        name, count = by_source[0]
        candidates.append(
            (
                count / new_count,
                "来源",
                name,
                count,
                f"收紧来源 {name!r} 的选择器（categories/query）或调低其 auto_fetch_limit",
            )
        )
    if by_category:
        name, count = by_category[0]
        candidates.append(
            (
                count / new_count,
                "类目",
                name,
                count,
                (
                    f"在 filters.exclude_regex 里补充排除 {name!r} 相关关键词，"
                    "或收窄 sources 的分类声明"
                ),
            )
        )
    if not candidates:
        return header + (
            "缺少来源/类目分布信息，建议直接调低 guard.max_new_per_run 或人工复核订阅范围。"
        )

    share, axis, name, count, advice = max(candidates, key=lambda c: c[0])
    return (
        f"{header}占比最高的{axis}是 {name!r}（{count}/{new_count} ≈ {share:.0%}）；建议{advice}。"
    )


def build_overload_report(
    subscription: str, entries: Sequence[ReportEntry], *, guard_limit: int
) -> OverloadReport:
    """从触发熔断的候选清单构建过载报告（计数 + 按源/类目分布 + 收窄建议）。

    `entries` 须是**本地过滤 + 去重之后**的净新增候选全集（触发 `is_truncated` 判定的
    同一批），而非截断后的展示样本——分布占比只有基于完整候选集才有意义。
    """
    by_source = _counts_by(entries, lambda e: (e.source,) if e.source else ())
    by_category = _counts_by(entries, lambda e: e.categories)
    suggestion = _suggest_narrowing(
        new_count=len(entries),
        guard_limit=guard_limit,
        by_source=by_source,
        by_category=by_category,
    )
    return OverloadReport(
        subscription=subscription,
        new_count=len(entries),
        guard_limit=guard_limit,
        by_source=by_source,
        by_category=by_category,
        suggestion=suggestion,
    )


__all__ = [
    "DedupeResult",
    "OverloadReport",
    "build_overload_report",
    "dedupe_against_library",
    "is_truncated",
]
