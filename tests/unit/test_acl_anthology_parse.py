"""acl_anthology/parse.py 单测（design/adapters/acl-anthology.md §4/§6/§7; T1/T3 纯逻辑件）。

覆盖 design §7 T1 ③④ + fixture①②③ 的"golden 解析输出"（本仓沿用 arxiv/openreview
先例——golden 断言直接写在测试代码里，不另立 `golden/*.json` 层，见
`tests/fixtures/README.md` 对二者的既有分工）与 ⑨ canary 3 样本
（新式=main/paper[1]、旧式=D19-1001、findings=findings-emnlp.1，均取真实公开
标题/DOI，见 fixture 文件头注记）：①解析 `2023.emnlp.xml` 节选（新式、含
volume→track、doi 可选、attachment、`<url>` 缺失构造兜底）；②解析
`2023.findings.xml` 节选（Findings 跨文件 join：按 volume id 过滤 + track 固定为
"findings"）；③解析 `D19.xml` 节选（旧式 id、大写前缀原样、attachment、license
年份二分实际生效）；⑤畸形 XML → `parse`。零网络。
"""

from __future__ import annotations

import pytest

from helpers.acl_anthology_fixtures import fixture_bytes
from paper_crawler.adapters.acl_anthology import parse
from paper_crawler.errors import CrawlerError, ErrorClass

# --- ① 新式：2023.emnlp.xml 节选 -----------------------------------------------------------------


def _load_main_2023() -> parse.RawCollection:
    return parse.parse_collection_xml(fixture_bytes("01_emnlp_main_2023_excerpt.xml"))


def test_parse_main_2023_collection_and_volume_shape() -> None:
    collection = _load_main_2023()
    assert collection.id == "2023.emnlp"
    by_id = {v.id: v for v in collection.volumes}
    assert set(by_id) == {"main", "tutorial", "demo", "industry"}
    assert len(by_id["main"].papers) == 2
    assert len(by_id["tutorial"].papers) == 1
    assert len(by_id["demo"].papers) == 1
    assert len(by_id["industry"].papers) == 1
    # volume 级 meta 的 year/month 兜底字段被解析（真实数据 year 恒 volume 级，勘察 §1）。
    assert by_id["main"].year == 2023
    assert by_id["main"].month == "December"


def test_canary_new_style_main_paper_known_answer_title_and_track() -> None:
    """canary（新式，design §7⑨(a)）：main/paper[1] 的真实公开标题+track+双 identifier。"""
    collection = _load_main_2023()
    main = next(v for v in collection.volumes if v.id == "main")
    stub = parse.to_paper_stub(
        collection.id,
        main.id,
        main.papers[0],
        track=main.id,
        volume_year=main.year,
        volume_month=main.month,
    )
    assert stub.title == (
        "IAG: Induction-Augmented Generation Framework for Answering Reasoning Questions"
    )
    assert stub.identifiers == (
        ("anthology", "2023.emnlp-main.1"),
        ("doi", "10.18653/v1/2023.emnlp-main.1"),
    )
    assert stub.year == 2023
    assert stub.pub_date == "2023-12"
    assert dict(stub.meta)["track"] == "main"
    assert dict(stub.meta)["license"] == "CC-BY-4.0"
    assert dict(stub.meta)["anthology_collection"] == "2023.emnlp"
    assert len(stub.authors) == 4
    assert stub.authors[0] == "Zhebin Zhang"
    assert stub.abstract is not None and stub.abstract.startswith("Retrieval-Augmented")


def test_main_paper_without_doi_produces_single_identifier() -> None:
    collection = _load_main_2023()
    main = next(v for v in collection.volumes if v.id == "main")
    stub = parse.to_paper_stub(
        collection.id,
        main.id,
        main.papers[1],
        track=main.id,
        volume_year=main.year,
        volume_month=main.month,
    )
    assert stub.identifiers == (("anthology", "2023.emnlp-main.2"),)  # 无 doi → 单 identifier


def test_demo_paper_attachment_carried_into_meta() -> None:
    collection = _load_main_2023()
    demo = next(v for v in collection.volumes if v.id == "demo")
    stub = parse.to_paper_stub(
        collection.id,
        demo.id,
        demo.papers[0],
        track=demo.id,
        volume_year=demo.year,
        volume_month=demo.month,
    )
    attachments = [v for k, v in stub.meta if k == "acl_anthology_attachment"]
    assert attachments == ["2023.emnlp-demo.1.Software.zip"]
    assert dict(stub.meta)["track"] == "demo"


def test_industry_paper_missing_url_uses_construct_fallback() -> None:
    collection = _load_main_2023()
    industry = next(v for v in collection.volumes if v.id == "industry")
    paper = industry.papers[0]
    assert paper.url_text is None  # fixture 故意省略 <url>
    stub = parse.to_paper_stub(
        collection.id,
        industry.id,
        paper,
        track=industry.id,
        volume_year=industry.year,
        volume_month=industry.month,
    )
    # 新式构造兜底：collection_id 以 4 位年份开头 → construct_new，不零填充。
    assert stub.identifiers[0] == ("anthology", "2023.emnlp-industry.1")


# --- ② Findings 跨文件 join：2023.findings.xml 节选 -----------------------------------------------


def _load_findings_2023() -> parse.RawCollection:
    return parse.parse_collection_xml(fixture_bytes("02_findings_2023_excerpt.xml"))


def test_findings_collection_has_four_venue_volumes() -> None:
    collection = _load_findings_2023()
    assert collection.id == "2023.findings"
    assert {v.id for v in collection.volumes} == {"eacl", "acl", "emnlp", "ijcnlp"}
    # meta/venue 恒为字面 "findings"（非目标 venue 名）——join 键必须是 volume id。
    emnlp_volume = next(v for v in collection.volumes if v.id == "emnlp")
    assert len(emnlp_volume.papers) == 2


def test_canary_findings_join_filters_by_volume_id_and_track_fixed_to_findings() -> None:
    """canary（findings，design §7⑨(c)）：join 后 track 固定 "findings"（非原始 volume id）。"""
    collection = _load_findings_2023()
    emnlp_volume = next(v for v in collection.volumes if v.id == "emnlp")
    stubs = [
        parse.to_paper_stub(
            collection.id,
            emnlp_volume.id,
            paper,
            track="findings",
            volume_year=emnlp_volume.year,
            volume_month=emnlp_volume.month,
        )
        for paper in emnlp_volume.papers
    ]
    assert [s.identifiers[0][1] for s in stubs] == [
        "2023.findings-emnlp.1",
        "2023.findings-emnlp.2",
    ]
    assert all(dict(s.meta)["track"] == "findings" for s in stubs)
    assert all(dict(s.meta)["anthology_collection"] == "2023.findings" for s in stubs)
    lead = stubs[0]
    assert lead.title == (
        "Multi Document Summarization Evaluation in the Presence of Damaging Content"
    )
    assert lead.identifiers == (
        ("anthology", "2023.findings-emnlp.1"),
        ("doi", "10.18653/v1/2023.findings-emnlp.1"),
    )


def test_findings_acl_volume_would_be_excluded_by_an_emnlp_join() -> None:
    """acl volume 存在于同一文件，但 emnlp venue 的 enumerate 绝不应产出它（adapter 层过滤）。"""
    collection = _load_findings_2023()
    ids_by_volume = {
        v.id: [
            parse.to_paper_stub(
                collection.id, v.id, p, track="findings", volume_year=v.year, volume_month=v.month
            ).identifiers[0][1]
            for p in v.papers
        ]
        for v in collection.volumes
    }
    assert ids_by_volume["acl"] == ["2023.findings-acl.1"]
    assert "2023.findings-acl.1" not in ids_by_volume["emnlp"]


# --- ③ 旧式：D19.xml 节选 -------------------------------------------------------------------------


def _load_d19() -> parse.RawCollection:
    return parse.parse_collection_xml(fixture_bytes("03_d19_legacy_excerpt.xml"))


def test_parse_d19_collection_and_volume_shape() -> None:
    collection = _load_d19()
    assert collection.id == "D19"
    assert len(collection.volumes) == 1
    volume = collection.volumes[0]
    assert volume.id == "1"
    assert len(volume.papers) == 4
    assert volume.year == 2019
    assert volume.month == "November"


def test_canary_old_style_d19_1001_known_answer_title_and_case_preserved() -> None:
    """canary（旧式，design §7⑨(b)）：D19-1001 真实公开标题，大写前缀原样、license 按年生效。"""
    collection = _load_d19()
    volume = collection.volumes[0]
    stub = parse.to_paper_stub(
        collection.id,
        volume.id,
        volume.papers[0],
        track=volume.id,
        volume_year=volume.year,
        volume_month=volume.month,
    )
    assert stub.title == "Attending to Future Tokens for Bidirectional Sequence Generation"
    assert stub.identifiers == (
        ("anthology", "D19-1001"),  # 大写前缀原样保留，不做大小写归一
        ("doi", "10.18653/v1/D19-1001"),
    )
    assert stub.year == 2019
    # 2019 >= 2016 → CC BY 4.0（新旧式 id 分界=摄入日期，与许可证的发表年份二分无关）。
    assert dict(stub.meta)["license"] == "CC-BY-4.0"
    attachments = [v for k, v in stub.meta if k == "acl_anthology_attachment"]
    assert attachments == ["D19-1001.Attachment.pdf"]
    assert stub.authors[:2] == ("Carolin Lawrence", "Bhushan Kotnis")


def test_d19_synthetic_paper_missing_url_uses_old_style_construct_fallback() -> None:
    collection = _load_d19()
    volume = collection.volumes[0]
    paper = volume.papers[3]
    assert paper.url_text is None
    stub = parse.to_paper_stub(
        collection.id,
        volume.id,
        paper,
        track=volume.id,
        volume_year=volume.year,
        volume_month=volume.month,
    )
    # 旧式构造兜底：collection_id "D19" 非 4 位数字开头 → construct_old，零填充 3 位。
    assert stub.identifiers == (("anthology", "D19-1004"),)  # 无 doi → 单 identifier
    assert stub.abstract is None


# --- ⑤ 畸形 XML → parse -----------------------------------------------------------------------


def test_malformed_xml_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_collection_xml(fixture_bytes("04_malformed.xml"))
    assert exc.value.error_class is ErrorClass.PARSE


# --- 结构性异常（非 fixture，直接构造） -----------------------------------------------------------


def test_non_collection_root_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_collection_xml(b"<not-a-collection/>")
    assert exc.value.error_class is ErrorClass.PARSE


def test_collection_missing_id_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_collection_xml(b"<collection><volume id='1' type='proceedings'/></collection>")
    assert exc.value.error_class is ErrorClass.PARSE


def test_volume_missing_id_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_collection_xml(b"<collection id='X'><volume type='proceedings'/></collection>")
    assert exc.value.error_class is ErrorClass.PARSE


def test_paper_missing_title_raises_parse() -> None:
    xml = (
        b"<collection id='2023.emnlp'><volume id='main' type='proceedings'>"
        b"<meta><year>2023</year></meta><paper id='1'><bibkey>x-2023</bibkey></paper>"
        b"</volume></collection>"
    )
    with pytest.raises(CrawlerError) as exc:
        parse.parse_collection_xml(xml)
    assert exc.value.error_class is ErrorClass.PARSE


def test_paper_missing_id_attribute_raises_parse() -> None:
    xml = (
        b"<collection id='2023.emnlp'><volume id='main' type='proceedings'>"
        b"<meta><year>2023</year></meta><paper><title>T</title></paper>"
        b"</volume></collection>"
    )
    with pytest.raises(CrawlerError) as exc:
        parse.parse_collection_xml(xml)
    assert exc.value.error_class is ErrorClass.PARSE


def test_title_with_fixed_case_markup_is_flattened_to_text() -> None:
    xml = (
        b"<collection id='2023.emnlp'><volume id='main' type='proceedings'>"
        b"<meta><year>2023</year></meta>"
        b"<paper id='1'><title><fixed-case>IAG</fixed-case>: a test</title>"
        b"<bibkey>x-2023</bibkey><url hash='aaaaaaaa'>2023.emnlp-main.1</url></paper>"
        b"</volume></collection>"
    )
    collection = parse.parse_collection_xml(xml)
    stub = parse.to_paper_stub(
        collection.id,
        "main",
        collection.volumes[0].papers[0],
        track="main",
        volume_year=2023,
        volume_month=None,
    )
    assert stub.title == "IAG: a test"
    assert stub.pub_date is None  # 无 month 时不产 pub_date


def test_unrecognized_month_name_yields_no_pub_date() -> None:
    xml = (
        b"<collection id='2023.emnlp'><volume id='main' type='proceedings'>"
        b"<meta><year>2023</year><month>Q4</month></meta>"
        b"<paper id='1'><title>T</title><bibkey>x-2023</bibkey></paper>"
        b"</volume></collection>"
    )
    collection = parse.parse_collection_xml(xml)
    volume = collection.volumes[0]
    stub = parse.to_paper_stub(
        collection.id,
        volume.id,
        volume.papers[0],
        track=volume.id,
        volume_year=volume.year,
        volume_month=volume.month,
    )
    assert stub.pub_date is None


def test_paper_level_year_overrides_volume_level() -> None:
    xml = (
        b"<collection id='2023.emnlp'><volume id='main' type='proceedings'>"
        b"<meta><year>2023</year><month>December</month></meta>"
        b"<paper id='1'><title>T</title><bibkey>x-2020</bibkey>"
        b"<year>2020</year><month>June</month></paper>"
        b"</volume></collection>"
    )
    collection = parse.parse_collection_xml(xml)
    volume = collection.volumes[0]
    stub = parse.to_paper_stub(
        collection.id,
        volume.id,
        volume.papers[0],
        track=volume.id,
        volume_year=volume.year,
        volume_month=volume.month,
    )
    assert stub.year == 2020
    assert stub.pub_date == "2020-06"
