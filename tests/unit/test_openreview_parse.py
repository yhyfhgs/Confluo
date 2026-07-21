"""openreview/parse.py 单测（design/adapters/openreview.md §2/§4/§6；T1）。

v1/v2 双解析器（`.value` 嵌套 vs 直取）、版本判定（groups domain）、accepted 判定矩阵
（主会 id / Submission / Withdrawn / Desk_Rejected / venueid 缺失五态）、pdf 相对路径与
meta 线索（doi/arxiv）提取、空态、错配→PARSE。零网络（输入 bytes 字面量）。
"""

from __future__ import annotations

import json

import pytest

from paper_crawler.adapters.openreview import parse
from paper_crawler.adapters.openreview.parse import ApiVersion
from paper_crawler.errors import CrawlerError, ErrorClass


def _bytes(obj: object) -> bytes:
    return json.dumps(obj).encode("utf-8")


# --- 版本判定（groups 的 domain 字段）------------------------------------------------------


def test_api_version_v2_when_group_has_domain() -> None:
    vid = "ICLR.cc/2024/Conference"
    data = _bytes({"groups": [{"id": vid, "domain": vid}], "count": 1})
    assert parse.api_version_from_groups(data, vid) is ApiVersion.V2


def test_api_version_v1_when_group_lacks_domain() -> None:
    data = _bytes({"groups": [{"id": "ICLR.cc/2014/conference", "members": []}], "count": 1})
    assert parse.api_version_from_groups(data, "ICLR.cc/2014/conference") is ApiVersion.V1


def test_api_version_matches_group_by_id_among_many() -> None:
    data = _bytes(
        {
            "groups": [
                {"id": "other", "domain": "x"},
                {"id": "ICLR.cc/2014/conference"},  # 无 domain → v1
            ],
            "count": 2,
        }
    )
    assert parse.api_version_from_groups(data, "ICLR.cc/2014/conference") is ApiVersion.V1


def test_api_version_empty_groups_raises_gone() -> None:
    data = _bytes({"groups": [], "count": 0})
    with pytest.raises(CrawlerError) as exc:
        parse.api_version_from_groups(data, "ICLR.cc/1999/Conference")
    assert exc.value.error_class is ErrorClass.GONE


def test_api_base_url_mapping() -> None:
    assert parse.api_base_url(ApiVersion.V1) == "https://api.openreview.net"
    assert parse.api_base_url(ApiVersion.V2) == "https://api2.openreview.net"


def test_group_ids_extracts_all_ids() -> None:
    data = _bytes({"groups": [{"id": "a"}, {"id": "b"}, {"nope": 1}], "count": 3})
    assert parse.group_ids(data) == ["a", "b"]


# --- v2 解析（content.<f>.value 嵌套）------------------------------------------------------


def _v2_note(
    *,
    note_id: str = "paper1",
    venueid: str = "ICLR.cc/2024/Conference",
    title: str = "A V2 Paper",
    pdf: str | None = "/pdf/" + "a" * 40 + ".pdf",
) -> dict[str, object]:
    content: dict[str, object] = {
        "title": {"value": title},
        "abstract": {"value": "v2 abstract"},
        "venueid": {"value": venueid},
        "authors": {"value": ["Alice", "Bob"]},
    }
    if pdf is not None:
        content["pdf"] = {"value": pdf}
    return {"id": note_id, "forum": note_id, "content": content}


def test_parse_v2_note_unwraps_value_nesting() -> None:
    page = parse.parse_notes_page(_bytes({"notes": [_v2_note()], "count": 1}), ApiVersion.V2)
    (note,) = page.notes
    assert note.id == "paper1"
    assert note.forum == "paper1"
    assert note.venueid == "ICLR.cc/2024/Conference"
    assert note.title == "A V2 Paper"
    assert note.abstract == "v2 abstract"
    assert note.pdf == "/pdf/" + "a" * 40 + ".pdf"
    assert note.authors == ("Alice", "Bob")


def test_parse_v2_missing_value_wrapper_raises_parse() -> None:
    # v2 期望 {"value": ...}，拿到裸值 → 版本错配信号 PARSE（§6 canary 标红）。
    bad = {"id": "x", "forum": "x", "content": {"title": "bare string not wrapped"}}
    with pytest.raises(CrawlerError) as exc:
        parse.parse_notes_page(_bytes({"notes": [bad], "count": 1}), ApiVersion.V2)
    assert exc.value.error_class is ErrorClass.PARSE


# --- v1 解析（content.<f> 直取）-----------------------------------------------------------


def _v1_note(
    *,
    note_id: str = "old1",
    venueid: str = "ICLR.cc/2014/conference",
    pdf: str | None = "/pdf/" + "b" * 40 + ".pdf",
) -> dict[str, object]:
    content: dict[str, object] = {
        "title": "A V1 Paper",
        "abstract": "v1 abstract",
        "venueid": venueid,
        "authors": ["Carol"],
    }
    if pdf is not None:
        content["pdf"] = pdf
    return {"id": note_id, "forum": note_id, "content": content}


def test_parse_v1_note_reads_direct_values() -> None:
    page = parse.parse_notes_page(_bytes({"notes": [_v1_note()], "count": 1}), ApiVersion.V1)
    (note,) = page.notes
    assert note.title == "A V1 Paper"
    assert note.venueid == "ICLR.cc/2014/conference"
    assert note.pdf == "/pdf/" + "b" * 40 + ".pdf"
    assert note.authors == ("Carol",)


def test_parse_v1_unexpected_value_wrapper_raises_parse() -> None:
    # v1 直取，却拿到 {"value": ...} 包裹 → 版本错配（v2 note 误走 v1 解析器）。
    bad = {"id": "x", "forum": "x", "content": {"title": {"value": "wrapped"}}}
    with pytest.raises(CrawlerError) as exc:
        parse.parse_notes_page(_bytes({"notes": [bad], "count": 1}), ApiVersion.V1)
    assert exc.value.error_class is ErrorClass.PARSE


# --- accepted 判定矩阵（五态）--------------------------------------------------------------


@pytest.mark.parametrize(
    ("venueid", "expected"),
    [
        ("ICLR.cc/2024/Conference", True),  # 主会 id → 接收
        ("ICLR.cc/2024/Conference/Submission", False),  # 在投/被拒
        ("ICLR.cc/2024/Conference/Withdrawn_Submission", False),  # 撤稿
        ("ICLR.cc/2024/Conference/Desk_Rejected_Submission", False),  # desk-reject
        (None, False),  # venueid 缺失 → 非接收（保守）
    ],
)
def test_is_accepted_matrix(venueid: str | None, expected: bool) -> None:
    note = parse.Note(
        id="n",
        forum="n",
        venueid=venueid,
        title="t",
        abstract=None,
        pdf=None,
        supplementary_material=None,
        authors=(),
        doi=None,
        arxiv=None,
    )
    assert parse.is_accepted(note, "ICLR.cc/2024/Conference") is expected


# --- PaperStub 映射：identifier=forum、meta 线索、pdf/SI 定位符 ----------------------------


def test_to_paper_stub_identifier_is_forum_preserving_case() -> None:
    note = _note(forum="ryQu7f-RZ", venueid="ICLR.cc/2018/Conference")
    stub = parse.to_paper_stub(note, year=2018)
    assert stub.identifiers == (("openreview", "ryQu7f-RZ"),)  # 原样，无大小写归一


def test_to_paper_stub_doi_arxiv_go_to_meta_not_identifier() -> None:
    note = _note(doi="10.1000/x", arxiv="1312.6173")
    stub = parse.to_paper_stub(note, year=2014)
    meta = dict(stub.meta)
    assert meta["doi"] == "10.1000/x"
    assert meta["arxiv"] == "1312.6173"
    # 绝不产出为 identifier（防跨源早合并）。
    assert stub.identifiers == (("openreview", note.forum),)
    schemes = {s for s, _ in stub.identifiers}
    assert "doi" not in schemes and "arxiv" not in schemes


def test_to_paper_stub_pdf_path_carried_in_meta() -> None:
    note = _note(pdf="/pdf/" + "c" * 40 + ".pdf")
    stub = parse.to_paper_stub(note, year=2024)
    assert dict(stub.meta)[parse.META_PDF_PATH] == "/pdf/" + "c" * 40 + ".pdf"


def test_to_paper_stub_no_pdf_omits_pdf_meta_key() -> None:
    note = _note(pdf=None)
    stub = parse.to_paper_stub(note, year=2013)
    assert parse.META_PDF_PATH not in dict(stub.meta)


def test_to_paper_stub_si_carried_in_meta() -> None:
    note = _note(si="/attachment/" + "d" * 40 + ".zip")
    stub = parse.to_paper_stub(note, year=2024)
    assert dict(stub.meta)[parse.META_SI_PATH] == "/attachment/" + "d" * 40 + ".zip"


def test_to_paper_stub_missing_title_raises_parse() -> None:
    note = _note(title=None)
    with pytest.raises(CrawlerError) as exc:
        parse.to_paper_stub(note, year=2024)
    assert exc.value.error_class is ErrorClass.PARSE


# --- 空态与错误形态 -------------------------------------------------------------------------


def test_empty_notes_page_is_legal_empty() -> None:
    page = parse.parse_notes_page(_bytes({"notes": [], "count": 0}), ApiVersion.V2)
    assert page.notes == ()
    assert page.count == 0


def test_count_reflects_total_not_page_size() -> None:
    # 分页语义：count = 匹配总数（>本页条数）。
    page = parse.parse_notes_page(_bytes({"notes": [_v2_note()], "count": 1500}), ApiVersion.V2)
    assert len(page.notes) == 1
    assert page.count == 1500


def test_malformed_json_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_notes_page(b"{not json", ApiVersion.V2)
    assert exc.value.error_class is ErrorClass.PARSE


def test_notes_missing_array_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_notes_page(_bytes({"count": 0}), ApiVersion.V2)
    assert exc.value.error_class is ErrorClass.PARSE


def test_note_missing_id_raises_parse() -> None:
    bad = {"forum": "x", "content": {"title": {"value": "t"}}}
    with pytest.raises(CrawlerError) as exc:
        parse.parse_notes_page(_bytes({"notes": [bad], "count": 1}), ApiVersion.V2)
    assert exc.value.error_class is ErrorClass.PARSE


def test_note_entry_not_object_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_notes_page(_bytes({"notes": ["not-an-object"], "count": 1}), ApiVersion.V2)
    assert exc.value.error_class is ErrorClass.PARSE


def test_note_missing_content_raises_parse() -> None:
    bad = {"id": "x", "forum": "x"}  # 无 content
    with pytest.raises(CrawlerError) as exc:
        parse.parse_notes_page(_bytes({"notes": [bad], "count": 1}), ApiVersion.V2)
    assert exc.value.error_class is ErrorClass.PARSE


def test_notes_response_not_object_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_notes_page(_bytes(["a", "b"]), ApiVersion.V2)  # 顶层数组非对象
    assert exc.value.error_class is ErrorClass.PARSE


def test_note_forum_falls_back_to_id_when_absent() -> None:
    note = {"id": "solo", "content": {"title": {"value": "t"}, "venueid": {"value": "V"}}}
    page = parse.parse_notes_page(_bytes({"notes": [note], "count": 1}), ApiVersion.V2)
    assert page.notes[0].forum == "solo"  # forum 缺省回退 id


def test_non_string_content_scalar_becomes_none() -> None:
    # venueid 值意外为 int → 规整化为 None（非字符串标量不强转）。
    content = {"title": {"value": "t"}, "venueid": {"value": 2024}}
    note = {"id": "x", "forum": "x", "content": content}
    page = parse.parse_notes_page(_bytes({"notes": [note], "count": 1}), ApiVersion.V2)
    assert page.notes[0].venueid is None


def test_authors_non_list_becomes_empty_tuple() -> None:
    note = {
        "id": "x",
        "forum": "x",
        "content": {"title": {"value": "t"}, "authors": {"value": "not-a-list"}},
    }
    page = parse.parse_notes_page(_bytes({"notes": [note], "count": 1}), ApiVersion.V2)
    assert page.notes[0].authors == ()


# --- groups envelope 边界 -------------------------------------------------------------------


def test_api_version_falls_back_to_first_group_when_id_unmatched() -> None:
    # id 不匹配时退回首个 group（envelope 保证匹配；防御性兜底）。
    data = _bytes({"groups": [{"id": "whatever", "domain": "d"}], "count": 1})
    assert parse.api_version_from_groups(data, "ICLR.cc/2024/Conference") is ApiVersion.V2


def test_api_version_all_non_dict_entries_raises_parse() -> None:
    data = _bytes({"groups": [1, 2, 3], "count": 3})
    with pytest.raises(CrawlerError) as exc:
        parse.api_version_from_groups(data, "X")
    assert exc.value.error_class is ErrorClass.PARSE


def test_api_version_non_object_top_level_raises_gone() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.api_version_from_groups(_bytes(["a"]), "X")
    assert exc.value.error_class is ErrorClass.GONE


def test_group_ids_non_list_returns_empty() -> None:
    assert parse.group_ids(_bytes({"count": 0})) == []


# --- 辅助：构造 Note 中间记录 ---------------------------------------------------------------


def _note(
    *,
    forum: str = "forumX",
    venueid: str = "ICLR.cc/2024/Conference",
    title: str | None = "Title",
    pdf: str | None = None,
    si: str | None = None,
    doi: str | None = None,
    arxiv: str | None = None,
) -> parse.Note:
    return parse.Note(
        id=forum,
        forum=forum,
        venueid=venueid,
        title=title,
        abstract="abs",
        pdf=pdf,
        supplementary_material=si,
        authors=("A",),
        doi=doi,
        arxiv=arxiv,
    )
