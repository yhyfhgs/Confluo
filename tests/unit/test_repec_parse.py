"""`adapters/repec/parse.py` 单测：ReDIF 切分/字段抽取、DOI↔handle 映射矩阵、manifest 与新鲜度。

fixture 出处如实标注：`tests/fixtures/repec/*.rdf` 是**自造合成样本**（真实快照拉取归
T19，见该目录 README.md）；唯一有 [LIVE 2026-07-26 探针] 依据的是字段名
`Classification-JEL`/`Publication-Status` 与 `nbr:nberwo:35506` 的 JEL 值 `D1; J13; J15`。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from paper_crawler.adapters.repec import parse
from paper_crawler.errors import CrawlerError, ErrorClass

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "repec"


@pytest.fixture
def multi_records() -> tuple[parse.RedifRecord, ...]:
    return parse.parse_redif((_FIXTURES / "01_nberwo_multi.rdf").read_bytes())


# --- 记录切分与字段抽取 -----------------------------------------------------------------------


def test_parse_redif_splits_on_template_type_and_skips_non_paper_blocks(
    multi_records: tuple[parse.RedifRecord, ...],
) -> None:
    """3 条 Paper 记录；`ReDIF-Series` 块（有 handle 无 title）与前言均被跳过。"""
    assert [r.handle for r in multi_records] == [
        "RePEc:nbr:nberwo:35506",
        "RePEc:nbr:nberwo:3210",
        "RePEc:nbr:nberwo:9001",
    ]


def test_parse_redif_extracts_live_jel_verbatim(
    multi_records: tuple[parse.RedifRecord, ...],
) -> None:
    """[LIVE 2026-07-26] `nbr:nberwo:35506` = `D1; J13; J15`——探针实测串逐字节还原。"""
    assert multi_records[0].jel == ("D1", "J13", "J15")


def test_parse_redif_extracts_publication_status_verbatim(
    multi_records: tuple[parse.RedifRecord, ...],
) -> None:
    """`Publication-Status` 原串直落（供 T10 preprint_of 建边消费，本层不解析其语义）。"""
    assert multi_records[0].publication_status == (
        "published in Journal of Economic Perspectives, 2022, vol 36 no 1"
    )


def test_parse_redif_collects_repeated_author_name_in_order(
    multi_records: tuple[parse.RedifRecord, ...],
) -> None:
    assert multi_records[0].authors == (
        "Melissa Schettini Kearney",
        "Phillip B. Levine",
        "Luke Pardue",
    )


def test_parse_redif_folds_continuation_lines_and_survives_blank_line_in_abstract(
    multi_records: tuple[parse.RedifRecord, ...],
) -> None:
    """摘要内的空行**不切记录、也不终止续行**（否则记录被腰斩、段落被丢）；续行空格折叠。"""
    abstract = multi_records[0].abstract or ""
    assert abstract.startswith("US birth rates have fallen substantially")
    # 空行后的段落必须仍属于同一 abstract 字段——这正是"空行不是字段终止符"的判据
    assert "We consider a wide range of potential explanations" in abstract
    assert "policy environments." in abstract
    # 记录未被腰斩：空行之后声明的字段仍归本条记录
    assert multi_records[0].year == 2022
    assert multi_records[0].jel == ("D1", "J13", "J15")


def test_parse_redif_year_from_creation_date(
    multi_records: tuple[parse.RedifRecord, ...],
) -> None:
    assert [r.year for r in multi_records] == [2022, 1989, 2015]


def test_parse_redif_historical_record_without_jel_is_kept(
    multi_records: tuple[parse.RedifRecord, ...],
) -> None:
    """缺 JEL 的历史记录（探针实测 1989 年代即此类）**照常产出**，只是增值为空。"""
    historical = multi_records[1]
    assert historical.jel == ()
    assert historical.publication_status == "Published in Oxford Economic Papers"
    assert historical.title == "Endogenous Technological Change"


def test_parse_redif_field_names_are_case_insensitive(
    multi_records: tuple[parse.RedifRecord, ...],
) -> None:
    lowercase_record = multi_records[2]
    assert lowercase_record.jel == ("C13", "C33")
    assert lowercase_record.year == 2015


def test_parse_redif_skips_records_missing_handle_or_title() -> None:
    """无 handle（无稳定身份）或无 title（`PaperStub.title` 必填）→ 跳过，**非异常**。"""
    records = parse.parse_redif((_FIXTURES / "02_malformed.rdf").read_bytes())
    assert [r.handle for r in records] == ["RePEc:nbr:nberwo:8888"]


def test_parse_redif_drops_non_jel_fragments() -> None:
    """JEL 是受控词表：不合形态的碎片丢弃而非入库（宁缺毋滥）。"""
    records = parse.parse_redif((_FIXTURES / "02_malformed.rdf").read_bytes())
    assert records[0].jel == ("G12", "G2")


def test_parse_redif_accepts_str_and_bytes_alike() -> None:
    text = (_FIXTURES / "01_nberwo_multi.rdf").read_text(encoding="utf-8")
    assert parse.parse_redif(text) == parse.parse_redif(text.encode("utf-8"))


def test_parse_redif_survives_undecodable_bytes() -> None:
    """非法字节 `replace` 而非炸整份快照（上游历史条目编码不齐）。"""
    raw = b"Template-Type: ReDIF-Paper 1.0\nTitle: Caf\xe9 Economics\nHandle: RePEc:nbr:nberwo:1\n"
    records = parse.parse_redif(raw)
    assert len(records) == 1
    assert records[0].handle == "RePEc:nbr:nberwo:1"


def test_parse_redif_empty_input_is_empty_tuple() -> None:
    assert parse.parse_redif(b"") == ()


def test_parse_redif_discards_field_shaped_preamble_before_first_record() -> None:
    """首个 `Template-Type:` 之前的**字段形态**行整体丢弃，不得渗进第一条记录。

    上游 archive 文件常以 `Provider-Name:` 之类的字段行开头；若不丢弃，这些值会被误挂到
    第一条论文记录上（如把 archive 的 `Handle:` 当成论文 handle），产出一条假论文。
    """
    raw = (
        "Provider-Name: National Bureau of Economic Research\n"
        "Handle: RePEc:nbr:nberwo\n"
        "Template-Type: ReDIF-Paper 1.0\n"
        "Title: Real Paper\n"
        "Handle: RePEc:nbr:nberwo:5\n"
    )
    records = parse.parse_redif(raw)
    assert [r.handle for r in records] == ["RePEc:nbr:nberwo:5"]


def test_parse_redif_first_occurrence_wins_for_duplicate_fields() -> None:
    raw = (
        "Template-Type: ReDIF-Paper 1.0\n"
        "Title: First Title\n"
        "Title: Second Title\n"
        "Handle: RePEc:nbr:nberwo:2\n"
    )
    assert parse.parse_redif(raw)[0].title == "First Title"


# --- JEL / 年份归一 ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("D1; J13; J15", ("D1", "J13", "J15")),  # [LIVE] 探针实测形态
        ("C13, C33", ("C13", "C33")),  # 逗号变体
        ("  g12 ;  g2  ", ("G12", "G2")),  # 大小写与空白归一
        ("E31; E31; E32", ("E31", "E32")),  # 保序去重
        ("", ()),
        ("see also the appendix", ()),  # 自由文本整体丢弃
        ("A", ("A",)),  # 单字母顶级码
    ],
)
def test_parse_jel_matrix(raw: str, expected: tuple[str, ...]) -> None:
    assert parse.parse_jel(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("2022-05", 2022), ("1989-12-01", 1989), ("2015", 2015), ("n.d.", None), ("", None)],
)
def test_parse_year_matrix(raw: str, expected: int | None) -> None:
    assert parse.parse_year(raw) == expected


# --- DOI↔handle 映射矩阵（≥8 例，§5.7 fixture 清单）------------------------------------------


@pytest.mark.parametrize(
    ("doi", "expected"),
    [
        ("10.3386/w35506", "RePEc:nbr:nberwo:35506"),  # w 系列主形态
        ("10.3386/w1", "RePEc:nbr:nberwo:1"),  # 下界低号
        ("10.3386/W3210", "RePEc:nbr:nberwo:3210"),  # 大小写不敏感
        ("  10.3386/w3210  ", "RePEc:nbr:nberwo:3210"),  # 首尾空白
        ("10.3386/t0042", "RePEc:nbr:nberwo:0042"),  # t 系列（[未实测] 推断，见 parse docstring）
        ("10.3386/c12345", None),  # 非 w/t 后缀（book chapter）
        ("10.3386/w35506v2", None),  # 尾部杂串 → 不模糊匹配
        ("10.1257/aer.20210001", None),  # 非 NBER 前缀（AEA）
        ("10.2139/ssrn.1234567", None),  # SSRN——RePEc 结构性为 0
        ("", None),
        ("not-a-doi", None),
    ],
)
def test_handle_from_doi_matrix(doi: str, expected: str | None) -> None:
    assert parse.handle_from_doi(doi) == expected


def test_handle_from_doi_reuses_nber_series_normalization() -> None:
    """series 号归一**复用** `nber.parse.series_id_from_doi`（单一权威源，不复制正则）。"""
    from paper_crawler.adapters.nber import parse as nber_parse

    assert nber_parse.series_id_from_doi("10.3386/W3210") == "w3210"
    assert parse.handle_from_doi("10.3386/W3210") == "RePEc:nbr:nberwo:3210"


# --- stub 映射 --------------------------------------------------------------------------------


def test_stub_from_record_carries_both_identifiers_and_meta(
    multi_records: tuple[parse.RedifRecord, ...],
) -> None:
    stub = parse.stub_from_record(multi_records[0], "10.3386/w35506")
    assert stub.identifiers == (("doi", "10.3386/w35506"), ("repec", "RePEc:nbr:nberwo:35506"))
    meta = dict(stub.meta)
    # `meta` 值类型冻结为 str：非标量结构一律 json.dumps（aggregators §6 A-C1）。
    assert json.loads(meta["jel"]) == ["D1", "J13", "J15"]
    assert meta["published_in"].startswith("published in Journal of Economic Perspectives")
    assert stub.year == 2022
    assert stub.authors[0] == "Melissa Schettini Kearney"


def test_stub_from_record_omits_empty_meta_keys(
    multi_records: tuple[parse.RedifRecord, ...],
) -> None:
    """无 JEL 的历史记录不产空 `jel` 键（空值不入 meta，避免把"没有"写成"空字符串"）。"""
    stub = parse.stub_from_record(multi_records[1], "10.3386/w3210")
    assert dict(stub.meta).keys() == {"published_in"}


# --- manifest 与新鲜度 ------------------------------------------------------------------------


def _manifest_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": 1,
        "archive": "nbr",
        "series": ["nberwo"],
        "mirror": "www2.nber.org",
        "source_urls": ["https://www2.nber.org/RePEc/nbr/nberwo/"],
        "fetched_at": "2026-07-27T00:00:00+00:00",
        "files": [{"name": "nbr/nberwo/nberwo.rdf", "bytes": 123, "sha256": "ab" * 32}],
        "record_count": 3,
    }
    payload.update(overrides)
    return payload


def test_parse_manifest_roundtrip() -> None:
    manifest = parse.parse_manifest(json.dumps(_manifest_payload()))
    assert manifest.schema == 1
    assert manifest.series == ("nberwo",)
    assert manifest.files[0].name == "nbr/nberwo/nberwo.rdf"
    assert manifest.record_count == 3


@pytest.mark.parametrize(
    "raw",
    [
        b"{not json",  # 非法 JSON
        b"[]",  # 顶层不是对象
        b'{"archive": "nbr"}',  # 缺 schema/fetched_at
        json.dumps(_manifest_payload(files=[{"name": "x"}])).encode(),  # files 项缺字段
    ],
)
def test_parse_manifest_malformed_raises_parse(raw: bytes) -> None:
    """快照是本通道唯一数据来源，manifest 畸形静默降级＝无法解释的空结果（审计 S1）→ 响亮。"""
    with pytest.raises(CrawlerError) as excinfo:
        parse.parse_manifest(raw)
    assert excinfo.value.error_class is ErrorClass.PARSE


@pytest.mark.parametrize(
    ("fetched_at", "expected"),
    [
        ("2026-07-27T00:00:00+00:00", 0),
        ("2026-06-27T00:00:00+00:00", 30),
        ("2026-06-10T00:00:00+00:00", 47),
        ("2026-07-27T00:00:00", 0),  # 无偏移串按 UTC 补齐（宽容旧写法）
        ("2026-08-01T00:00:00+00:00", 0),  # 未来时间（时钟偏斜）钳到 0
        ("not-a-timestamp", None),
    ],
)
def test_staleness_days_matrix(fetched_at: str, expected: int | None) -> None:
    now = datetime(2026, 7, 27, tzinfo=UTC)
    assert parse.staleness_days(fetched_at, now=now) == expected


def test_parse_fetched_at_returns_aware_datetime() -> None:
    parsed = parse.parse_fetched_at("2026-07-27T00:00:00")
    assert parsed is not None
    assert parsed.tzinfo is UTC
