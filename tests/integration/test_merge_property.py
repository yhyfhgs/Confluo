"""AC-3.4 顺序无关属性测试（Phase 3 T1；plan §2-1 / §6 / 06 §7）。

命题：同一批多源 `PaperStub` 以任意注入顺序经 `MergeEngine.ingest` 落库，最终 DB 的
canonical dump（paper/identifier/meta_json 含 `_field_src` provenance）+ paper_relation
dump 逐行一致——字段级来源优先级收敛 + 弱信号候审对到达顺序满足交换律。

## 策略的可靠性边界（重要，取舍入报告）

顺序无关性**并非对任意输入成立**——跨 paper identifier 冲突裁决本质顺序敏感（迟到的桥接
identifier 得 candidate 而非 merge，见 merge.py 裁决 3）。故本策略把输入限定在**无桥接冲突**
的输入类，此类上顺序无关性成立：

- 每个 work 有一个**唯一 anchor identifier**（doi），该 work 的全部多源观测都携带它 →
  任意顺序下都经 anchor 强合并进同一 paper，绝不触发跨 paper 冲突（identifier 交集）。
- 不同 work 的 anchor 与 per-source 附加 id 全局唯一 → 互不桥接（identifier 空集）。
- 一个 work 内的多源**来源各不相同**（distinct，故优先级级别互异）→ 任一字段的提供者集合有
  唯一最高优先者，终值/终 provenance 与顺序无关（跨级收敛）；同级仅以「同源同值幂等重复」
  形式出现（同级不覆盖分支，值相同故无顺序歧义）。
- 同 (title_norm, 首作者姓氏) 但 anchor 相异的 work → 弱信号候审；引擎对**每个**匹配建边，
  故终态 = 该簇全体两两 candidate，与创建顺序无关。

跨 paper 冲突裁决的**确定性**由 `test_merge.py` 的定向用例单独锁，不纳入随机顺序属性。

## 防 CI flaky

`derandomize=True` 固定种子（每次运行同一批用例，可复现）；`deadline=None` 免每例时限
（每例建两个 SQLite 库+多次 ingest+两次 dump，超默认 200ms 属正常）。≥200 examples。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from helpers.dbdump import canonical_dump, dump_paper_relations
from paper_crawler.merge import MergeEngine
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.types import PaperStub

_SOURCES = ["official", "crossref", "dblp", "openalex", "s2", "heuristic"]
_TITLES = ["Alpha Title", "Beta Title", "Gamma Title"]  # 少量 → 制造 title_norm 碰撞（弱信号）
_SURNAMES = ["smith", "jones"]

# 一次 ingest 观测 = (stub, source)。
_Observation = tuple[PaperStub, str]


@st.composite
def _work_observations(draw: st.DrawFn, work_index: int) -> list[_Observation]:
    """一个 work 的多源观测集：全部携同一 anchor doi、同标题、同首作者姓氏；来源互异。"""
    title = draw(st.sampled_from(_TITLES))
    surname = draw(st.sampled_from(_SURNAMES))
    anchor = ("doi", f"10.w/{work_index}")
    sources = draw(st.lists(st.sampled_from(_SOURCES), min_size=1, max_size=4, unique=True))

    observations: list[_Observation] = []
    for source in sources:
        identifiers: list[tuple[str, str]] = [anchor]
        if draw(st.booleans()):  # per-source 附加 id（全局唯一，测 identifier 并集）
            identifiers.append(("openalex", f"W-{work_index}-{source}"))
        stub = PaperStub(
            title=title,
            identifiers=tuple(identifiers),
            abstract=draw(st.none() | st.just(f"abs-{source}")),  # 字段缺失组合
            year=draw(st.none() | st.just(2000 + _SOURCES.index(source))),
            pub_date=draw(st.none() | st.just(f"pub-{source}")),
            authors=(f"X {surname}",),
            meta=draw(st.just(()) | st.just((("m", f"m-{source}"),))),  # 共享键→测 meta 优先
        )
        observations.append((stub, source))
        if draw(st.booleans()):  # 同源同值幂等重复（同级不覆盖分支）
            observations.append((stub, source))
    return observations


@st.composite
def _batches(draw: st.DrawFn) -> tuple[list[_Observation], list[_Observation]]:
    """一批观测 + 它的两个独立排列（两条注入顺序）。"""
    n_works = draw(st.integers(min_value=1, max_value=4))
    all_obs: list[_Observation] = []
    for work_index in range(n_works):
        all_obs.extend(draw(_work_observations(work_index)))
    order1 = draw(st.permutations(all_obs))
    order2 = draw(st.permutations(all_obs))
    return list(order1), list(order2)


def _content(dump: dict[str, list[tuple[object, ...]]]) -> dict[str, list[object]]:
    """把 canonical_dump 各表按整行 `repr` 排序，得到**行序无关**的内容视图。

    命题是「DB 行集合与注入顺序无关」——行在 dump 里的呈现次序无关。`canonical_dump` 的
    `paper` 表排序键 `(title, venue_id, year, pub_date)` 对弱信号候审生成的「同标题/同
    year/同 pub_date、异 identifier」两 paper **不唯一**（dbdump 模块 docstring 明示该排序
    键不要求全局唯一、只对 Phase 1 唯一标题语料稳定）——此时两行的 dump 次序随 ULID 抖动。
    故按 `repr`（含整行内容，两库同内容 → 同 repr 序）重排消除该抖动，比较的是行的多重集。
    """
    return {table: sorted(rows, key=repr) for table, rows in dump.items()}


def _run(order: list[_Observation]) -> tuple[dict[str, list[object]], list[object]]:
    """按给定顺序 ingest 到一个隔离库，返回 (行序无关的 canonical_dump, paper_relation dump)。"""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "prop.sqlite"
        database = Database(db_path)
        database.migrate()
        engine = MergeEngine(Repo(database))
        for stub, source in order:
            engine.ingest(stub, source=source)
        database.close()
        return _content(canonical_dump(db_path)), dump_paper_relations(db_path)


@settings(
    max_examples=250,
    deadline=None,
    derandomize=True,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(_batches())
def test_ingest_order_independent(batch: tuple[list[_Observation], list[_Observation]]) -> None:
    order1, order2 = batch
    dump1, rels1 = _run(order1)
    dump2, rels2 = _run(order2)
    assert dump1 == dump2
    assert rels1 == rels2


@settings(max_examples=50, deadline=None, derandomize=True)
@given(_batches())
def test_reingest_whole_batch_is_idempotent(
    batch: tuple[list[_Observation], list[_Observation]],
) -> None:
    """整批注入两遍（同库）与一遍等价——批级幂等（属性测试锁）。"""
    order1, _ = batch
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "idem.sqlite"
        database = Database(db_path)
        database.migrate()
        engine = MergeEngine(Repo(database))
        for stub, source in order1:
            engine.ingest(stub, source=source)
        database.close()
        once = _content(canonical_dump(db_path))
        once_rels = dump_paper_relations(db_path)

        database = Database(db_path)
        engine = MergeEngine(Repo(database))
        for stub, source in order1:  # 再来一遍
            engine.ingest(stub, source=source)
        database.close()
        assert _content(canonical_dump(db_path)) == once
        assert dump_paper_relations(db_path) == once_rels
