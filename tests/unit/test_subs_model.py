"""订阅 DSL 解析与校验（Phase 6 T1；design/09 §2）。

三块：
1. **双示例逐字段**——`tests/fixtures/subs/{llm-agents,asset-pricing-wp}.yaml` 是
   design/09 §2 两个示例的逐字转录，此处逐字段断言解析结果（含 guard 缺省补全）；
2. **非法输入矩阵**（≥12 例）——未知源/未知字段/坏正则/负数 guard/空 sources/坏 YAML…
   全部必须响亮报错为 `SubscriptionInvalid`，且消息带字段定位；
3. **目录加载语义**——只扫顶层（presets 是模板不是活订阅）、重名拒载、缺目录拒载。
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from paper_crawler.errors import CrawlerError, ErrorClass, SubscriptionInvalid
from paper_crawler.subs.model import (
    DEFAULT_DEDUPE_AGAINST_LIBRARY,
    DEFAULT_MAX_NEW_PER_RUN,
    SOURCE_FIELDS,
    Actions,
    Guard,
    LocalFilter,
    SourceSelector,
    Subscription,
    load_subscription_file,
    load_subscriptions_dir,
    parse_subscription,
)

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "subs"


def _write(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


# --- 1. design/09 §2 双示例逐字段 ------------------------------------------


def test_llm_agents_example_parses_field_by_field() -> None:
    sub = load_subscription_file(_FIXTURES / "llm-agents.yaml")

    assert sub.name == "llm-agents"
    assert sub.source_names() == ("arxiv", "openalex")  # 声明序

    arxiv = sub.selector_for("arxiv")
    assert arxiv is not None
    assert arxiv.categories == ("cs.AI", "cs.LG", "cs.CL", "cs.MA")
    # `query: >` 折叠标量：换行折成空格，尾随换行被 strip。
    assert arxiv.query == '(ti:"agent" OR abs:"agentic" OR abs:"tool use") AND NOT ti:"survey"'
    assert arxiv.concepts == ()  # 非本源字段保持空

    openalex = sub.selector_for("openalex")
    assert openalex is not None
    assert openalex.concepts == ("large language model",)
    assert openalex.from_source_types == ("preprint",)

    assert sub.filters == LocalFilter(
        title_regex_any=(r"\bagent(s|ic)?\b", "LLM"),
        exclude_regex=("quantum",),
        min_year=2024,
    )
    assert sub.actions == Actions(ingest="metadata", auto_fetch_limit=20)
    assert sub.guard == Guard(max_new_per_run=200, dedupe_against_library=True)
    assert sub.schedule_hint == "daily"  # 仅存不调度（已裁决歧义③）


def test_asset_pricing_example_parses_field_by_field_and_fills_guard_default() -> None:
    sub = load_subscription_file(_FIXTURES / "asset-pricing-wp.yaml")

    assert sub.name == "asset-pricing-wp"
    assert sub.source_names() == ("ssrn", "arxiv", "nber")

    ssrn = sub.selector_for("ssrn")
    assert ssrn is not None
    assert ssrn.networks == ("FEN",)
    assert ssrn.ejournals == ("Asset Pricing eJournal", "Capital Markets eJournal")

    arxiv = sub.selector_for("arxiv")
    assert arxiv is not None
    assert arxiv.categories == ("q-fin.PR", "q-fin.PM", "q-fin.ST")
    assert arxiv.query is None  # 本示例未声明

    nber = sub.selector_for("nber")
    assert nber is not None
    assert nber.programs == ("AP",)

    assert sub.filters == LocalFilter(
        title_regex_any=("asset pricing", "cross-section", "risk premi")
    )
    assert sub.actions == Actions(ingest="metadata", auto_fetch_limit=10)
    # 示例只写了 max_new_per_run → dedupe_against_library 按缺省补全（DoD 判据）。
    assert sub.guard == Guard(max_new_per_run=100, dedupe_against_library=True)
    assert sub.schedule_hint is None
    assert sub.selector_for("crossref") is None


@pytest.mark.parametrize("stem", ["llm-agents", "asset-pricing-wp"])
def test_examples_round_trip_through_query_dict(stem: str) -> None:
    """`to_query_dict()` + guard → `parse_subscription` 严格互逆（库内 JSON 的往返基础）。"""
    sub = load_subscription_file(_FIXTURES / f"{stem}.yaml")
    payload = json.loads(json.dumps(sub.to_query_dict()))
    payload["guard"] = json.loads(json.dumps(sub.guard.to_dict()))
    assert parse_subscription(payload) == sub


def test_minimal_document_takes_all_defaults() -> None:
    sub = parse_subscription({"name": "minimal", "sources": {"nber": {"programs": ["AP"]}}})
    assert sub.filters == LocalFilter() and sub.filters.is_empty()
    assert sub.actions == Actions(ingest="metadata", auto_fetch_limit=0)
    assert sub.guard.max_new_per_run == DEFAULT_MAX_NEW_PER_RUN
    assert sub.guard.dedupe_against_library is DEFAULT_DEDUPE_AGAINST_LIBRARY
    assert sub.schedule_hint is None


def test_all_six_sources_parse() -> None:
    """SOURCE_FIELDS 的每个源 × 每个字段都能被解析（能力面自断言，防清单漂移）。"""
    sources: dict[str, object] = {}
    for source, fields in SOURCE_FIELDS.items():
        sources[source] = {name: ("x" if name == "query" else ["x"]) for name in fields}
    sub = parse_subscription({"name": "everything", "sources": sources})
    assert sub.source_names() == tuple(SOURCE_FIELDS)
    for selector in sub.sources:
        for name in SOURCE_FIELDS[selector.source]:
            assert getattr(selector, name)  # 非空 = 该字段真的被落进了 dataclass


def test_source_fields_and_selector_dataclass_stay_in_sync() -> None:
    """`SOURCE_FIELDS` 的字段并集 == `SourceSelector` 的非 `source` 字段集合。

    集合等值自断言（沿审计 S4 的"注册了却没验证"根治手法）：任一侧新增字段而另一侧
    忘了跟进，这里立刻红——防止"DSL 里写了却永远读不到"的静默漏字段。
    """
    declared = {name for fields in SOURCE_FIELDS.values() for name in fields}
    on_class = {f.name for f in dataclasses.fields(SourceSelector)} - {"source"}
    assert declared == on_class


def test_selector_to_dict_only_emits_own_source_fields() -> None:
    selector = SourceSelector(source="nber", programs=("AP",), categories=("cs.AI",))
    assert selector.to_dict() == {"programs": ["AP"]}  # categories 不属于 nber，不外泄


def test_selector_to_dict_skips_unset_fields() -> None:
    """本源合法但未声明的字段（空列表 / query=None）不出现在回写里。"""
    selector = SourceSelector(source="s2", venues=("NeurIPS",))
    assert selector.to_dict() == {"venues": ["NeurIPS"]}  # fields_of_study / query 未声明


def test_ingest_metadata_pdf_with_default_fetch_limit() -> None:
    sub = parse_subscription(
        {
            "name": "pdf-mode",
            "sources": {"nber": {"programs": ["AP"]}},
            "actions": {"ingest": "metadata+pdf"},
        }
    )
    assert sub.actions == Actions(ingest="metadata+pdf", auto_fetch_limit=0)


# --- 2. 非法输入矩阵（DoD ≥12 例）------------------------------------------

_BASE_SOURCES: dict[str, object] = {"arxiv": {"categories": ["cs.AI"]}}


def _doc(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {"name": "probe", "sources": dict(_BASE_SOURCES)}
    document.update(overrides)
    return document


_INVALID: list[tuple[str, dict[str, object], str]] = [
    # (用例名, 文档, 报错消息里必须出现的定位/关键词)
    ("未知顶层字段", _doc(schedule="daily"), "schedule"),
    ("未知源", {"name": "probe", "sources": {"biorxiv": {"categories": ["x"]}}}, "未知源"),
    (
        "未知源内字段",
        {"name": "probe", "sources": {"arxiv": {"catgories": ["cs.AI"]}}},
        "sources.arxiv.catgories",
    ),
    (
        "字段串到别的源",
        {"name": "probe", "sources": {"nber": {"categories": ["cs.AI"]}}},
        "sources.nber.categories",
    ),
    ("空 sources", {"name": "probe", "sources": {}}, "至少声明一个源"),
    ("缺 sources", {"name": "probe"}, "sources"),
    ("缺 name", {"sources": dict(_BASE_SOURCES)}, "name"),
    ("name 形态非法", _doc(name="LLM Agents"), "kebab-case"),
    ("空选择器", {"name": "probe", "sources": {"arxiv": {}}}, "选择器为空"),
    ("None 选择器", {"name": "probe", "sources": {"arxiv": None}}, "必须是映射"),
    (
        "标量当列表",
        {"name": "probe", "sources": {"arxiv": {"categories": "cs.AI"}}},
        "实际是单个字符串",
    ),
    ("空列表", {"name": "probe", "sources": {"arxiv": {"categories": []}}}, "列表不得为空"),
    (
        "数值当列表",
        {"name": "probe", "sources": {"arxiv": {"categories": 5}}},
        "必须是列表，实际是 int",
    ),
    ("空 query", {"name": "probe", "sources": {"arxiv": {"query": "  "}}}, "不得为空字符串"),
    (
        "列表元素非串",
        {"name": "probe", "sources": {"arxiv": {"categories": [1]}}},
        "sources.arxiv.categories[0]",
    ),
    ("坏 title 正则", _doc(filters={"title_regex_any": ["["]}), "正则非法"),
    ("坏 exclude 正则", _doc(filters={"exclude_regex": ["(unclosed"]}), "正则非法"),
    ("未知 filters 字段", _doc(filters={"max_year": 2024}), "filters.max_year"),
    ("min_year 非整数", _doc(filters={"min_year": "2024"}), "必须是整数"),
    ("min_year 负数", _doc(filters={"min_year": -1}), "年份越界"),
    ("min_year 越界", _doc(filters={"min_year": 20240}), "年份越界"),
    ("filters 非映射", _doc(filters=["title_regex_any"]), "必须是映射"),
    ("未知 actions 字段", _doc(actions={"ingest": "metadata", "fetch": 3}), "actions.fetch"),
    ("ingest 取值非法", _doc(actions={"ingest": "metadata+html"}), "actions.ingest"),
    ("auto_fetch_limit 负数", _doc(actions={"auto_fetch_limit": -1}), "不得为负"),
    ("未知 guard 字段", _doc(guard={"max_total": 10}), "guard.max_total"),
    ("guard 负数", _doc(guard={"max_new_per_run": -5}), "须 ≥ 1"),
    ("guard 零", _doc(guard={"max_new_per_run": 0}), "须 ≥ 1"),
    ("guard bool 落数值位", _doc(guard={"max_new_per_run": True}), "必须是整数"),
    ("dedupe 非布尔", _doc(guard={"dedupe_against_library": 1}), "必须是布尔"),
    ("schedule_hint 非串", _doc(schedule_hint=3), "必须是字符串"),
]


@pytest.mark.parametrize(
    ("document", "needle"),
    [pytest.param(doc, needle, id=name) for name, doc, needle in _INVALID],
)
def test_invalid_documents_fail_loud(document: dict[str, object], needle: str) -> None:
    with pytest.raises(SubscriptionInvalid) as excinfo:
        parse_subscription(document, where="probe.yaml")
    message = str(excinfo.value)
    assert needle in message
    assert message.startswith("probe.yaml")  # 定位前缀恒在
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert isinstance(excinfo.value, CrawlerError)  # 归入既有 errors 层级


def test_invalid_matrix_covers_at_least_twelve_cases() -> None:
    """DoD 明文要求 ≥12 例；此断言防后人删测试时无声降标。"""
    assert len(_INVALID) >= 12


def test_sources_must_be_a_mapping() -> None:
    with pytest.raises(SubscriptionInvalid, match="必须是映射"):
        parse_subscription({"name": "probe", "sources": ["arxiv"]}, where="probe.yaml")


# --- 文件层：坏 YAML / 空文件 / 编码 / 文件名 --------------------------------


def test_broken_yaml_fails_loud(tmp_path: Path) -> None:
    path = _write(tmp_path / "broken.yaml", "name: broken\nsources: {arxiv: [\n")
    with pytest.raises(SubscriptionInvalid, match="YAML 解析失败"):
        load_subscription_file(path)


def test_empty_file_fails_loud(tmp_path: Path) -> None:
    path = _write(tmp_path / "empty.yaml", "# 只有注释\n")
    with pytest.raises(SubscriptionInvalid, match="文件为空"):
        load_subscription_file(path)


def test_yaml_top_level_list_fails_loud(tmp_path: Path) -> None:
    path = _write(tmp_path / "listy.yaml", "- name: listy\n")
    with pytest.raises(SubscriptionInvalid, match="必须是映射"):
        load_subscription_file(path)


def test_unreadable_file_fails_loud(tmp_path: Path) -> None:
    (tmp_path / "gone.yaml").write_bytes(b"\xff\xfe\x00name")  # 非 UTF-8
    with pytest.raises(SubscriptionInvalid, match="文件读取失败"):
        load_subscription_file(tmp_path / "gone.yaml")


def test_missing_file_fails_loud(tmp_path: Path) -> None:
    with pytest.raises(SubscriptionInvalid, match="文件读取失败"):
        load_subscription_file(tmp_path / "nope.yaml")


def test_filename_must_match_name(tmp_path: Path) -> None:
    path = _write(tmp_path / "other-name.yaml", "name: probe\nsources: {nber: {programs: [AP]}}\n")
    with pytest.raises(SubscriptionInvalid, match="与 name"):
        load_subscription_file(path)


# --- YAML 重复键（P1-2 热修：PyYAML 默认静默取后者覆盖前者）------------------


def test_duplicate_source_key_fails_loud(tmp_path: Path) -> None:
    """`sources:` 内重复声明同一源（两次 `arxiv:`）→ 拒载，而非静默取后者覆盖前者。"""
    path = _write(
        tmp_path / "dup-source.yaml",
        "name: dup-source\n"
        "sources:\n"
        "  arxiv:\n"
        "    categories: [cs.AI]\n"
        "  arxiv:\n"
        "    categories: [cs.LG]\n",
    )
    with pytest.raises(SubscriptionInvalid) as excinfo:
        load_subscription_file(path)
    message = str(excinfo.value)
    assert "重复键" in message and "arxiv" in message
    assert message.startswith(str(path))  # 文件定位恒在（_fail 的 where 前缀）


def test_duplicate_field_within_selector_fails_loud(tmp_path: Path) -> None:
    """选择器内重复字段（两次 `categories:`）→ 拒载，而非静默取后者覆盖前者。"""
    path = _write(
        tmp_path / "dup-field.yaml",
        "name: dup-field\nsources:\n  arxiv:\n    categories: [cs.AI]\n    categories: [cs.LG]\n",
    )
    with pytest.raises(SubscriptionInvalid) as excinfo:
        load_subscription_file(path)
    message = str(excinfo.value)
    assert "重复键" in message and "categories" in message
    assert message.startswith(str(path))


def test_duplicate_top_level_field_fails_loud(tmp_path: Path) -> None:
    """顶层字段重复（两次 `sources:`）同样拒载——检测不分层级。"""
    path = _write(
        tmp_path / "dup-top.yaml",
        "name: dup-top\n"
        "sources:\n"
        "  arxiv:\n"
        "    categories: [cs.AI]\n"
        "sources:\n"
        "  nber:\n"
        "    programs: [AP]\n",
    )
    with pytest.raises(SubscriptionInvalid) as excinfo:
        load_subscription_file(path)
    message = str(excinfo.value)
    assert "重复键" in message and "sources" in message
    assert message.startswith(str(path))


# --- 3. 目录加载语义 --------------------------------------------------------


def _valid_body(name: str) -> str:
    return f"name: {name}\nsources:\n  nber:\n    programs: [AP]\n"


def test_load_dir_reads_top_level_only_and_sorts(tmp_path: Path) -> None:
    _write(tmp_path / "zulu.yaml", _valid_body("zulu"))
    _write(tmp_path / "alpha.yaml", _valid_body("alpha"))
    (tmp_path / "presets").mkdir()
    _write(tmp_path / "presets" / "preset-one.yaml", _valid_body("preset-one"))
    _write(tmp_path / "notes.txt", "不是 YAML")

    loaded = load_subscriptions_dir(tmp_path)
    # presets/ 是模板不是活订阅 → 不递归；非 .yaml 忽略；按文件名排序。
    assert [s.name for s in loaded] == ["alpha", "zulu"]


def test_load_dir_empty_is_ok(tmp_path: Path) -> None:
    assert load_subscriptions_dir(tmp_path) == []


def test_load_dir_missing_fails_loud(tmp_path: Path) -> None:
    with pytest.raises(SubscriptionInvalid, match="订阅目录不存在"):
        load_subscriptions_dir(tmp_path / "absent")


def test_load_dir_name_uniqueness_comes_from_filename_rule(tmp_path: Path) -> None:
    """同目录内不可能出现重名：stem 必须等于 name，而同扩展名的 stem 天然唯一。

    "另一个文件想叫同一个 name" 的唯一形态就是 stem 不符 → 被文件名校验拦下。
    """
    _write(tmp_path / "dup.yaml", _valid_body("dup"))
    _write(tmp_path / "dup-copy.yaml", _valid_body("dup"))  # name=dup 但 stem=dup-copy
    with pytest.raises(SubscriptionInvalid, match="与 name"):
        load_subscriptions_dir(tmp_path)


def test_load_dir_propagates_file_error(tmp_path: Path) -> None:
    _write(tmp_path / "ok.yaml", _valid_body("ok"))
    _write(tmp_path / "bad.yaml", "name: bad\nsources: {biorxiv: {categories: [x]}}\n")
    with pytest.raises(SubscriptionInvalid, match="未知源"):
        load_subscriptions_dir(tmp_path)


# --- from_stored（库行还原；repo 的解析路径）-------------------------------


def test_from_stored_round_trip() -> None:
    original = load_subscription_file(_FIXTURES / "llm-agents.yaml")
    restored = Subscription.from_stored(
        "llm-agents",
        json.dumps(original.to_query_dict(), ensure_ascii=False),
        json.dumps(original.guard.to_dict()),
    )
    assert restored == original


def test_from_stored_without_guard_json_takes_defaults() -> None:
    restored = Subscription.from_stored(
        "probe", json.dumps({"name": "probe", "sources": {"nber": {"programs": ["AP"]}}})
    )
    assert restored.guard == Guard()


@pytest.mark.parametrize(
    ("name", "query_json", "guard_json", "needle"),
    [
        ("probe", "{not json", None, "JSON 解析失败"),
        ("probe", '["probe"]', None, "必须是映射"),
        ("probe", '{"name": "other", "sources": {"nber": {"programs": ["AP"]}}}', None, "不一致"),
        (
            "probe",
            '{"name": "probe", "sources": {"nber": {"programs": ["AP"]}}}',
            "{bad",
            "JSON 解析失败",
        ),
    ],
)
def test_from_stored_corrupt_row_fails_loud(
    name: str, query_json: str, guard_json: str | None, needle: str
) -> None:
    with pytest.raises(SubscriptionInvalid, match=needle):
        Subscription.from_stored(name, query_json, guard_json)
