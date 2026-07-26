"""AC-3.4 顺序无关属性测试（Phase 3 T1；plan §2-1 / §6 / 06 §7。Phase 6 F1 补强）。

命题：同一批多源 `PaperStub` 以任意注入顺序经 `MergeEngine.ingest` 落库，最终 DB 的
canonical dump（paper/identifier/meta_json 含 `_field_src` provenance）+ paper_relation dump
+ paper_weak_key dump 逐行一致——字段级来源优先级收敛 + 弱信号候审对到达顺序满足交换律。

## Phase 6 F1 的两处补强（审计 P1/P3）

1. **生成器解除结构性遮蔽**：原生成器令同一 work 的各源共享 title/surname，于是"高优先源
   改写 title_norm 后不重跑弱信号"这条缝**测不出来**（审计原话：结构性遮蔽）。现每个观测
   独立抽 title/surname，同 anchor 各源可给出不同标题——正是缺陷的触发面。
2. **同源二次观测异值**：原生成器的重复观测同源**同值**（只走幂等分支）。现允许同源异值，
   逼出同级 tie-break 的确定性（审计 P3「先到胜」）。
弱信号匹配面（`paper_weak_key`）本身也纳入逐行比对——否则匹配面的漂移要等下一次 ingest
才显形，属性测试看不见。

## 策略的可靠性边界（重要，取舍入报告）

顺序无关性**并非对任意输入成立**——跨 paper identifier 冲突裁决本质顺序敏感（见 merge.py
裁决 3）：含"桥接 identifier"的输入类，不同注入序产生**真实数据差**（**非**等价数据态）——
桥接 stub 先到时静默建成单 paper、无候审痕迹（保守侧、非不变量），后到时裂成两 paper +
候审边；平局胜者随 ULID 摆动。差异体现在 paper 行数 / 桥字段落点 / 候审边有无，但**零丢失**
（identifier 值集不变、绝不删行）。这是既定语义的数学必然，其确定性由 `test_merge.py` 定向
用例单独锁。故本随机顺序属性测试把输入限定在**无桥接冲突**的输入类，此类上顺序无关成立：

- 每个 work 有一个**唯一 anchor identifier**（doi），该 work 的全部多源观测都携带它 →
  任意顺序下都经 anchor 强合并进同一 paper，绝不触发跨 paper 冲突（identifier 交集）。
- 不同 work 的 anchor 与 per-source 附加 id 全局唯一 → 互不桥接（identifier 空集）。附加 id
  的 scheme **不再限定**在 `openalex`（原限定使 anchor 恒为最小 identifier、候审边定向锚永不
  翻转——那是又一处结构性遮蔽）：现也抽 `arxiv`（< `doi` 字典序），故后补的 identifier 会改变
  最小锚、同一条边在不同注入序下可能方向相反。这是**既定语义**（定向是建边时刻快照、非不变量，
  merge.py 裁决 5），故 `dump_paper_relations` 按无序对归一后比较。
- 一个 work 内**跨源**冲突由优先级表定序（**七枚举**两两互异——D-035 扩位重编号后仍成立），
  **同源**二次观测异值由值序 tie-break 定序——两者都与到达顺序无关。
- 同 (title_norm, 首作者姓氏) 观测但 anchor 相异的 work → 弱信号候审；引擎按观测级键集合
  对**每个**曾持同键的 paper 建边，故终态 = 键集合有交者两两 candidate，与创建顺序无关。

跨 paper 冲突裁决的**确定性**由 `test_merge.py` 的定向用例单独锁，不纳入随机顺序属性。

## 防 CI flaky

`derandomize=True` 固定种子（每次运行同一批用例，可复现）；`deadline=None` 免每例时限
（每例建两个 SQLite 库+多次 ingest+两次 dump，超默认 200ms 属正常）。≥200 examples。
"""

from __future__ import annotations

import itertools
import tempfile
from contextlib import closing
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from helpers.dbdump import canonical_dump, dump_paper_relations, dump_weak_keys
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
    """一个 work 的多源观测集：全部携同一 anchor doi；**标题/姓氏逐观测独立抽取**。

    标题/姓氏不再按 work 固定（F1 解除结构性遮蔽）：同一 anchor 的各源可给出不同标题，
    使"高优先源改写 title_norm"与"低优先观测的键"同时存在于一个 paper 上——审计 P1 的
    触发面。同源重复观测既可同值（幂等分支）也可异值（同级 tie-break 分支）。
    """
    anchor = ("doi", f"10.w/{work_index}")
    sources = draw(st.lists(st.sampled_from(_SOURCES), min_size=1, max_size=4, unique=True))

    def _stub(source: str, variant: int) -> PaperStub:
        identifiers: list[tuple[str, str]] = [anchor]
        if draw(st.booleans()):  # per-source 附加 id（全局唯一，测 identifier 并集）
            # scheme 不限定：`arxiv` < `doi` < `openalex`，抽到 arxiv 时后补的 id 会改写该
            # paper 的最小 identifier（候审边定向锚），逼出"定向非不变量"的真实形态。
            scheme = draw(st.sampled_from(["arxiv", "openalex"]))
            identifiers.append((scheme, f"W-{work_index}-{source}-{scheme}"))
        return PaperStub(
            title=draw(st.sampled_from(_TITLES)),
            identifiers=tuple(identifiers),
            abstract=draw(st.none() | st.just(f"abs-{source}-{variant}")),  # 字段缺失组合
            year=draw(st.none() | st.just(2000 + _SOURCES.index(source) + variant)),
            pub_date=draw(st.none() | st.just(f"pub-{source}-{variant}")),
            authors=(f"X {draw(st.sampled_from(_SURNAMES))}",),
            meta=draw(st.just(()) | st.just((("m", f"m-{source}-{variant}"),))),  # 共享键
        )

    observations: list[_Observation] = []
    for source in sources:
        first = _stub(source, 0)
        observations.append((first, source))
        repeat = draw(st.sampled_from(["none", "same", "different"]))
        if repeat == "same":  # 同源同值幂等重复
            observations.append((first, source))
        elif repeat == "different":  # 同源异值 → 同级 tie-break 分支
            observations.append((_stub(source, 1), source))
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


def _run(order: list[_Observation]) -> tuple[dict[str, list[object]], list[object], list[object]]:
    """按给定顺序 ingest 到隔离库，返回 (行序无关 canonical_dump, relation dump, 弱信号键 dump)。"""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "prop.sqlite"
        with closing(Database(db_path)) as database:
            database.migrate()
            engine = MergeEngine(Repo(database))
            for stub, source in order:
                engine.ingest(stub, source=source)
        return (
            _content(canonical_dump(db_path)),
            dump_paper_relations(db_path),
            dump_weak_keys(db_path),
        )


@settings(
    max_examples=250,
    deadline=None,
    derandomize=True,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(_batches())
def test_ingest_order_independent(batch: tuple[list[_Observation], list[_Observation]]) -> None:
    order1, order2 = batch
    assert _run(order1) == _run(order2)


@settings(max_examples=50, deadline=None, derandomize=True)
@given(_batches())
def test_reingest_whole_batch_is_idempotent(
    batch: tuple[list[_Observation], list[_Observation]],
) -> None:
    """整批注入两遍（同库）与一遍等价——批级幂等（属性测试锁）。"""
    order1, _ = batch
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "idem.sqlite"
        with closing(Database(db_path)) as database:
            database.migrate()
            engine = MergeEngine(Repo(database))
            for stub, source in order1:
                engine.ingest(stub, source=source)
        once = (
            _content(canonical_dump(db_path)),
            dump_paper_relations(db_path),
            dump_weak_keys(db_path),
        )

        with closing(Database(db_path)) as database:
            engine = MergeEngine(Repo(database))
            for stub, source in order1:  # 再来一遍
                engine.ingest(stub, source=source)
        assert (
            _content(canonical_dump(db_path)),
            dump_paper_relations(db_path),
            dump_weak_keys(db_path),
        ) == once


# -- 审计 P1 复现用例 + 全排列属性（Phase 6 F1） ------------------------------

# 审计 P1（post-phase5-audit §3-1）隔离脚本复现用例的正式回归形态：
# A/B 同 DOI（强合并），B 是高优先源且标题不同 → 合并时改写 title_norm；C 是异 DOI、与 B
# 同标题同姓氏的独立 work（弱信号候审面）。修复前实测：序 A,B,C→1 条候审边，序 C,A,B→0 条
# （A,C,B 亦 0）；修复后六个排列恒 1 条，且三份 dump 逐字节一致。
_REPRO_A = (
    PaperStub(
        title="Alpha Study",
        identifiers=(("doi", "10.repro/a"),),
        authors=("Jane Smith",),
    ),
    "s2",
)
_REPRO_B = (
    PaperStub(
        title="Beta Study",
        identifiers=(("doi", "10.repro/a"),),
        authors=("Jane Smith",),
    ),
    "official",
)
_REPRO_C = (
    PaperStub(
        title="Beta Study",
        identifiers=(("doi", "10.repro/c"),),
        authors=("John Smith",),
    ),
    "crossref",
)


def test_ac_3_4_audit_repro_candidate_edge_in_every_injection_order() -> None:
    """审计 P1 复现用例：高优先源改写 title_norm 后候审边不得随注入序消失。

    修复前：`ABC`→1 边、`ACB`/`CAB`→0 边（三份 dump 因此不等）；修复后六个排列全一致、
    恒 1 条 candidate_duplicate，且两 paper 不合并（弱信号绝不自动合并，06 §3）。
    """
    baseline = None
    for order in itertools.permutations([_REPRO_A, _REPRO_B, _REPRO_C]):
        dumps = _run(list(order))
        assert len(dumps[1]) == 1, f"{order} 应恰有 1 条候审边"
        assert len(dumps[0]["paper"]) == 2, f"{order} 应有 2 个 paper（弱信号不自动合并）"
        if baseline is None:
            baseline = dumps
        assert dumps == baseline, "同一批观测的不同注入序落库结果必须逐行一致（AC-3.4）"


# 全排列属性的固定语料：3 个来源（s2/dblp/crossref，优先级两两互异）观测同一 work
# （anchor doi 相同 → 强合并），各自给出**不同**的 title/abstract/year/pub_date/meta 与姓氏；
# 外加一条异 anchor 的独立观测，其 (title, 姓氏) 与该 work 的**低优先**观测撞键（弱信号面）。
# 覆盖字段 ≥4：title / abstract / year / pub_date / meta:m / 首作者姓氏（共 6）。
_PERM_BATCH: list[_Observation] = [
    (
        PaperStub(
            title="Convergence of Estimators",
            identifiers=(("doi", "10.perm/w"),),
            abstract="s2 abstract",
            year=2019,
            pub_date="2019-03-01",
            authors=("Ann Smith",),
            meta=(("m", "s2"),),
        ),
        "s2",
    ),
    (
        PaperStub(
            title="Convergence of Estimators in Panels",
            identifiers=(("doi", "10.perm/w"), ("openalex", "W-perm-dblp")),
            abstract="dblp abstract",
            year=2020,
            pub_date="2020-05-01",
            authors=("Ann Smith",),
            meta=(("m", "dblp"),),
        ),
        "dblp",
    ),
    (
        PaperStub(
            title="Convergence of Estimators in Panel Data",
            identifiers=(("doi", "10.perm/w"),),
            abstract="crossref abstract",
            year=2021,
            pub_date="2021-07-01",
            authors=("Bob Jones",),
            meta=(("m", "crossref"),),
        ),
        "crossref",
    ),
    (
        PaperStub(  # 独立 work：与上面 s2 观测同 (title_norm, 姓氏) → 弱信号候审面
            title="Convergence of Estimators",
            identifiers=(("doi", "10.perm/other"),),
            abstract="other abstract",
            year=2018,
            pub_date="2018-01-01",
            authors=("Carl Smith",),
            meta=(("m", "other"),),
        ),
        "openalex",
    ),
]


def test_ac_3_4_all_permutations_of_multi_source_batch_agree() -> None:
    """4 条观测（3 源同 anchor + 1 条异 anchor）的**全部 24 个排列**落库结果逐行一致。

    手写全排列（非随机抽样）：源数 ≥3、异值字段 ≥4（title/abstract/year/pub_date/meta/姓氏），
    每个字段的胜者由优先级表唯一确定，候审边由观测级键集合唯一确定——任一环节残留顺序敏感
    都会让某个排列的 dump 偏离基准。
    """
    orders = list(itertools.permutations(_PERM_BATCH))
    assert len(orders) == 24
    baseline = _run(list(orders[0]))
    for order in orders[1:]:
        assert _run(list(order)) == baseline

    paper_dump, relations, weak_keys = baseline
    assert len(paper_dump["paper"]) == 2  # 强合并成 1 个 work + 1 个独立 work
    assert len(relations) == 1  # 弱信号候审边（与低优先观测的键撞上）
    assert len(weak_keys) == 4  # work 侧 3 个观测键（三标题/两姓氏）+ 独立 work 1 个
