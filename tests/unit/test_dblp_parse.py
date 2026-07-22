"""`adapters.dblp.parse` 单测（design/adapters/aggregators.md §5.2 字段映射 +
"ee→DOI 同源护栏"，A-C3 评审必落项的专项覆盖）。

覆盖三块：①conf 索引页 HTML 解析（含"nips2023 404"命名不规则教训的专项证明）；
②卷 XML 解析（`DblpVolume`：记录 + 容器 DOI 集合，含各类容错/失败分支）；
③`to_paper_stub` 的护栏落地（paper 级 ee 正确产出 identifier / 容器 DOI 绝不
产出 identifier / 非 DOI ee 入 meta）。
"""

from __future__ import annotations

import json

import pytest

from helpers.dblp_fixtures import fixture_bytes
from paper_crawler.adapters.dblp import parse
from paper_crawler.errors import CrawlerError, ErrorClass

# --- ①conf 索引页 HTML ---------------------------------------------------------------------


def test_normal_index_discovers_real_slugs_in_document_order() -> None:
    links = parse.parse_conf_index(fixture_bytes("01_conf_index_normal.html"))
    assert links == (
        parse.DblpVolumeLink(slug="icml2024", year=2024),
        parse.DblpVolumeLink(slug="icml2023", year=2023),
        parse.DblpVolumeLink(slug="icml2022", year=2022),
        parse.DblpVolumeLink(slug="icml2022w", year=2022),
    )


def test_normal_index_excludes_decoy_nav_links() -> None:
    links = parse.parse_conf_index(fixture_bytes("01_conf_index_normal.html"))
    slugs = {link.slug for link in links}
    assert "index" not in slugs
    assert not any("search" in slug for slug in slugs)
    assert not any("faq" in slug for slug in slugs)


def test_absolute_url_href_resolves_to_basename_slug() -> None:
    # icml2022w 的 fixture 条目故意用绝对 URL（https://dblp.org/db/conf/icml/icml2022w.html）。
    links = parse.parse_conf_index(fixture_bytes("01_conf_index_normal.html"))
    absolute_entry = next(link for link in links if link.slug == "icml2022w")
    assert absolute_entry.year == 2022


def test_key_naming_irregular_index_discovers_renamed_slug_not_guessed_one() -> None:
    """ "nips2023 404" 教训的专项证明：naive acr+year 拼接（'nips2023'）绝不出现在
    发现结果中；真实（改名后的）slug 'neurips2023' 才是应被发现的对象。
    """
    links = parse.parse_conf_index(fixture_bytes("02_conf_index_key_naming_irregular.html"))
    slugs = {link.slug: link.year for link in links}
    assert "nips2023" not in slugs  # 从未拼接猜测——猜测值根本不该出现
    assert slugs == {"neurips2023": 2023, "neurips2022": 2022, "nips1988": 1988}


def test_empty_index_returns_empty_tuple() -> None:
    assert parse.parse_conf_index(fixture_bytes("03_conf_index_empty.html")) == ()


def test_duplicate_href_appears_once() -> None:
    html = (
        b'<html><body><a href="icml2023.html">ICML 2023</a>'
        b'<a href="icml2023.html">ICML 2023 (mirror link)</a></body></html>'
    )
    links = parse.parse_conf_index(html)
    assert links == (parse.DblpVolumeLink(slug="icml2023", year=2023),)


@pytest.mark.parametrize("slug", ["foo0001", "bar9999"])
def test_year_out_of_bounds_is_excluded(slug: str) -> None:
    html = f'<html><body><a href="{slug}.html">out of range</a></body></html>'.encode()
    assert parse.parse_conf_index(html) == ()


def test_href_without_trailing_year_is_excluded() -> None:
    html = b'<html><body><a href="about.html">About this venue</a></body></html>'
    assert parse.parse_conf_index(html) == ()


# --- ②卷 XML：正常态 + 容器 DOI 集合 ----------------------------------------------------------


def test_normal_volume_parses_expected_record_count_and_skips_container_entries() -> None:
    volume = parse.parse_volume_xml(fixture_bytes("04_volume_xml_dump_schema_normal.xml"))
    keys = [record.key for record in volume.records]
    assert keys == [
        "conf/icml/AamandACINS23",
        "conf/icml/NoLinkExample23",
        "conf/xyz/Smith23",
        "conf/xyz/Jones23",
        "conf/xyz/Adversary23",
    ]
    assert volume.skipped_missing_title == 0


def test_normal_volume_collects_only_doi_form_container_ees() -> None:
    volume = parse.parse_volume_xml(fixture_bytes("04_volume_xml_dump_schema_normal.xml"))
    # ICML 容器的 ee 是 PMLR 站点链接（非 DOI）——不进 container_dois；
    # XYZ 容器的 ee 是 doi.org 全卷 DOI——归一后进 container_dois。唯二容器仅此一条。
    assert volume.container_dois == frozenset({"10.1007/978-3-030-99999-9"})


def test_no_proceedings_container_is_ever_converted_to_a_record() -> None:
    volume = parse.parse_volume_xml(fixture_bytes("04_volume_xml_dump_schema_normal.xml"))
    keys = {record.key for record in volume.records}
    assert "conf/icml/2023" not in keys
    assert "conf/xyz/2023" not in keys


def test_empty_volume_xml_is_legal_and_yields_zero_records() -> None:
    volume = parse.parse_volume_xml(fixture_bytes("05_volume_xml_empty.xml"))
    assert volume == parse.DblpVolume(
        records=(), container_dois=frozenset(), skipped_missing_title=0
    )


def test_malformed_xml_raises_parse_error() -> None:
    with pytest.raises(CrawlerError) as exc_info:
        parse.parse_volume_xml(fixture_bytes("06_volume_xml_malformed.xml"))
    assert exc_info.value.error_class is ErrorClass.PARSE


def test_wrong_root_element_raises_parse_error_as_structural_drift() -> None:
    with pytest.raises(CrawlerError) as exc_info:
        parse.parse_volume_xml(b"<notdblp></notdblp>")
    assert exc_info.value.error_class is ErrorClass.PARSE


def test_bht_root_is_accepted_as_valid_schema() -> None:
    """`<bht>` 是 `/db/conf/{acr}/{slug}.xml` 在线卷页的真实根元素（2026-07-23
    审查真实交叉验证核实，见 parse.py 模块 docstring"双 schema"专节）——本测试
    锁定"未来若误改回单一 `dblp` 根校验"这一回归。"""
    xml = (
        b'<bht><dblpcites><r style="ee"><inproceedings key="conf/x/Bht23">'
        b"<title>Bht Root Smoke Test.</title>"
        b"</inproceedings></r></dblpcites></bht>"
    )
    volume = parse.parse_volume_xml(xml)
    assert [record.key for record in volume.records] == ["conf/x/Bht23"]


def test_dump_dblp_root_is_still_accepted_as_valid_schema() -> None:
    """`<dblp>` 平铺根（批量导出 `dblp.xml.gz` schema）继续被接受——双 schema
    兼容而非"改真实 schema 就丢弃 dump 兼容"的替换式修复。"""
    xml = (
        b'<dblp><inproceedings key="conf/x/Dump23"><title>Dump Root Smoke Test.</title>'
        b"</inproceedings></dblp>"
    )
    volume = parse.parse_volume_xml(xml)
    assert [record.key for record in volume.records] == ["conf/x/Dump23"]


def test_bht_root_with_zero_records_is_legal_empty() -> None:
    xml = b"<bht><dblpcites></dblpcites></bht>"
    volume = parse.parse_volume_xml(xml)
    assert volume == parse.DblpVolume(
        records=(), container_dois=frozenset(), skipped_missing_title=0
    )


def test_inproceedings_missing_key_attribute_raises_parse_error() -> None:
    xml = b"<dblp><inproceedings><title>No Key</title></inproceedings></dblp>"
    with pytest.raises(CrawlerError) as exc_info:
        parse.parse_volume_xml(xml)
    assert exc_info.value.error_class is ErrorClass.PARSE


def test_inproceedings_missing_title_is_skipped_not_raised() -> None:
    xml = (
        b"<dblp>"
        b'<inproceedings key="conf/x/NoTitle23"></inproceedings>'
        b'<inproceedings key="conf/x/HasTitle23"><title>Has A Title.</title></inproceedings>'
        b"</dblp>"
    )
    volume = parse.parse_volume_xml(xml)
    assert [record.key for record in volume.records] == ["conf/x/HasTitle23"]
    assert volume.skipped_missing_title == 1


def test_inproceedings_with_blank_title_text_is_also_skipped() -> None:
    xml = b'<dblp><inproceedings key="conf/x/Blank23"><title>   </title></inproceedings></dblp>'
    volume = parse.parse_volume_xml(xml)
    assert volume.records == ()
    assert volume.skipped_missing_title == 1


def test_minimal_record_defaults_missing_optional_fields_to_none_or_empty() -> None:
    xml = (
        b'<dblp><inproceedings key="conf/x/Minimal23"><title>Minimal.</title>'
        b"</inproceedings></dblp>"
    )
    volume = parse.parse_volume_xml(xml)
    (record,) = volume.records
    assert record.authors == ()
    assert record.year is None
    assert record.pages is None
    assert record.ees == ()
    assert record.crossref is None


def test_year_element_present_but_non_numeric_is_none() -> None:
    xml = (
        b'<dblp><inproceedings key="conf/x/BadYear23">'
        b"<title>Bad Year.</title><year>unknown</year>"
        b"</inproceedings></dblp>"
    )
    (record,) = parse.parse_volume_xml(xml).records
    assert record.year is None


def test_author_without_pid_has_none_pid() -> None:
    xml = (
        b'<dblp><inproceedings key="conf/x/NoPid23"><title>No Pid.</title>'
        b"<author>Anonymous Author</author>"
        b"</inproceedings></dblp>"
    )
    (record,) = parse.parse_volume_xml(xml).records
    assert record.authors == (parse.DblpAuthor(name="Anonymous Author", pid=None),)


def test_author_with_blank_text_is_dropped() -> None:
    xml = (
        b'<dblp><inproceedings key="conf/x/BlankAuthor23"><title>T.</title>'
        b'<author pid="1/1">Real Author</author>'
        b"<author>   </author>"
        b"</inproceedings></dblp>"
    )
    (record,) = parse.parse_volume_xml(xml).records
    assert record.authors == (parse.DblpAuthor(name="Real Author", pid="1/1"),)


def test_proceedings_container_with_no_ee_contributes_nothing() -> None:
    xml = (
        b'<dblp><proceedings key="conf/x/2023"><title>No EE Proceedings</title></proceedings>'
        b'<inproceedings key="conf/x/Paper23"><title>T.</title>'
        b"<ee>https://doi.org/10.1/only-paper-doi</ee>"
        b"</inproceedings></dblp>"
    )
    volume = parse.parse_volume_xml(xml)
    assert volume.container_dois == frozenset()
    stub = parse.to_paper_stub(volume.records[0], volume.container_dois)
    assert ("doi", "10.1/only-paper-doi") in stub.identifiers


# --- ③ to_paper_stub：ee→DOI 同源护栏 ---------------------------------------------------------


def _record_for(volume: parse.DblpVolume, key: str) -> parse.DblpRecord:
    return next(record for record in volume.records if record.key == key)


def test_paper_level_doi_ee_produces_doi_identifier() -> None:
    volume = parse.parse_volume_xml(fixture_bytes("04_volume_xml_dump_schema_normal.xml"))
    smith = _record_for(volume, "conf/xyz/Smith23")
    stub = parse.to_paper_stub(smith, volume.container_dois)
    assert stub.identifiers == (
        ("dblp", "conf/xyz/Smith23"),
        ("doi", "10.1007/978-3-030-99999-9_1"),
    )


def test_distinct_paper_dois_in_the_same_volume_do_not_collide() -> None:
    volume = parse.parse_volume_xml(fixture_bytes("04_volume_xml_dump_schema_normal.xml"))
    jones = _record_for(volume, "conf/xyz/Jones23")
    stub = parse.to_paper_stub(jones, volume.container_dois)
    assert ("doi", "10.1007/978-3-030-99999-9_2") in stub.identifiers
    assert stub.authors == ("Robert Jones", "Amara Okafor")


def test_adversarial_ee_matching_container_doi_produces_no_doi_identifier() -> None:
    """毒性缺陷防御：即使某条 inproceedings 自身的 ee 恰好等于容器 DOI（如误配的
    全卷式 DOI 缺 `_N` 后缀），也绝不能产出 identifier——否则会把整卷论文经这个
    共享 DOI 强合并成一条 paper。"""
    volume = parse.parse_volume_xml(fixture_bytes("04_volume_xml_dump_schema_normal.xml"))
    adversary = _record_for(volume, "conf/xyz/Adversary23")
    stub = parse.to_paper_stub(adversary, volume.container_dois)
    assert stub.identifiers == (("dblp", "conf/xyz/Adversary23"),)
    assert ("ee", "https://doi.org/10.1007/978-3-030-99999-9") in stub.meta


def test_non_doi_ee_goes_to_meta_not_identifier() -> None:
    volume = parse.parse_volume_xml(fixture_bytes("04_volume_xml_dump_schema_normal.xml"))
    aamand = _record_for(volume, "conf/icml/AamandACINS23")
    stub = parse.to_paper_stub(aamand, volume.container_dois)
    assert stub.identifiers == (("dblp", "conf/icml/AamandACINS23"),)
    assert ("ee", "https://proceedings.mlr.press/v202/aamand23a.html") in stub.meta


def test_record_with_no_ee_has_only_dblp_identifier_and_no_ee_meta() -> None:
    volume = parse.parse_volume_xml(fixture_bytes("04_volume_xml_dump_schema_normal.xml"))
    no_link = _record_for(volume, "conf/icml/NoLinkExample23")
    stub = parse.to_paper_stub(no_link, volume.container_dois)
    assert stub.identifiers == (("dblp", "conf/icml/NoLinkExample23"),)
    assert all(key != "ee" for key, _ in stub.meta)


def test_author_pids_captured_in_meta_as_json_pairs() -> None:
    volume = parse.parse_volume_xml(fixture_bytes("04_volume_xml_dump_schema_normal.xml"))
    aamand = _record_for(volume, "conf/icml/AamandACINS23")
    stub = parse.to_paper_stub(aamand, volume.container_dois)
    meta = dict(stub.meta)
    assert json.loads(meta["author_pids"]) == [
        ["Anders Aamand", "111/1111"],
        ["Fabrizio Boninsegna", "222/2222"],
    ]


def test_author_without_pid_is_excluded_from_author_pids_meta() -> None:
    xml = (
        b'<dblp><inproceedings key="conf/x/NoPidMeta23"><title>T.</title>'
        b"<author>Anonymous Author</author>"
        b"</inproceedings></dblp>"
    )
    (record,) = parse.parse_volume_xml(xml).records
    stub = parse.to_paper_stub(record, frozenset())
    assert all(key != "author_pids" for key, _ in stub.meta)


def test_pages_and_crossref_captured_in_meta() -> None:
    volume = parse.parse_volume_xml(fixture_bytes("04_volume_xml_dump_schema_normal.xml"))
    smith = _record_for(volume, "conf/xyz/Smith23")
    stub = parse.to_paper_stub(smith, volume.container_dois)
    meta = dict(stub.meta)
    assert meta["pages"] == "1-15"
    assert meta["crossref"] == "conf/xyz/2023"


def test_year_and_pub_date_populated_from_year_element() -> None:
    volume = parse.parse_volume_xml(fixture_bytes("04_volume_xml_dump_schema_normal.xml"))
    smith = _record_for(volume, "conf/xyz/Smith23")
    stub = parse.to_paper_stub(smith, volume.container_dois)
    assert stub.year == 2023
    assert stub.pub_date == "2023"


def test_missing_year_leaves_year_and_pub_date_none() -> None:
    xml = b'<dblp><inproceedings key="conf/x/NoYear23"><title>T.</title></inproceedings></dblp>'
    (record,) = parse.parse_volume_xml(xml).records
    stub = parse.to_paper_stub(record, frozenset())
    assert stub.year is None
    assert stub.pub_date is None


def test_abstract_is_always_none() -> None:
    volume = parse.parse_volume_xml(fixture_bytes("04_volume_xml_dump_schema_normal.xml"))
    stub = parse.to_paper_stub(volume.records[0], volume.container_dois)
    assert stub.abstract is None


def test_multiple_non_doi_ees_are_all_captured_as_separate_meta_entries() -> None:
    xml = (
        b'<dblp><inproceedings key="conf/x/TwoLinks23"><title>T.</title>'
        b"<ee>https://official.example/paper</ee>"
        b"<ee>https://mirror.example/paper</ee>"
        b"</inproceedings></dblp>"
    )
    (record,) = parse.parse_volume_xml(xml).records
    stub = parse.to_paper_stub(record, frozenset())
    ee_values = [value for key, value in stub.meta if key == "ee"]
    assert ee_values == ["https://official.example/paper", "https://mirror.example/paper"]


def test_ee_dx_doi_org_mixed_case_is_detected_as_doi() -> None:
    xml = (
        b'<dblp><inproceedings key="conf/x/MixedCase23"><title>T.</title>'
        b"<ee>HTTPS://DX.DOI.ORG/10.1145/Foo</ee>"
        b"</inproceedings></dblp>"
    )
    (record,) = parse.parse_volume_xml(xml).records
    stub = parse.to_paper_stub(record, frozenset())
    assert ("doi", "10.1145/foo") in stub.identifiers


# --- ④双 schema：bht 在线卷页 schema（2026-07-23 审查真实交叉验证修复）--------------------------
#
# 上面①-③全部用 dump（`<dblp>`）schema fixture 覆盖了字段映射与护栏三层；本节
# 用真实交叉验证核实的在线卷页 schema（`<bht><dblpcites><r>…</r></dblpcites>
# </bht>`）把同样的护栏三层**重新锁定一遍**——防止"只在 dump schema 下测过护栏，
# bht schema 下 container_dois 其实是恒空集、测试却因为从未断言非空而从未发现"
# 这一具体复发模式（审查阻断项原话）。10_volume_xml_bht_schema_normal.xml 是
# 真实抓取（2 条 ICML 记录逐字节未改动）+ 拼接合成护栏记录（3 条，因为真实
# ICML/PMLR 数据不含任何 DOI 形式 ee，护栏三层无法只用真实数据练到）的混合体，
# 记录集与 04_volume_xml_dump_schema_normal.xml 同构（同一批 conf/xyz/* 合成
# 角色），故断言基本平行，只是包装换成生产真实形态。


def test_bht_schema_normal_volume_parses_expected_record_count() -> None:
    volume = parse.parse_volume_xml(fixture_bytes("10_volume_xml_bht_schema_normal.xml"))
    keys = [record.key for record in volume.records]
    assert keys == [
        "conf/icml/AamandACINS23",
        "conf/icml/AbbasS23",
        "conf/xyz/Smith23",
        "conf/xyz/Jones23",
        "conf/xyz/Adversary23",
    ]
    assert volume.skipped_missing_title == 0


def test_bht_schema_container_dois_is_non_empty() -> None:
    """审查阻断项点名要求的断言：`container_dois` 必须**非空**——这正是修复前
    "生产恒空集"这一失效模式的直接反证。空集合会让下面的
    `test_bht_schema_adversarial_ee_produces_no_doi_identifier` 断言即使护栏
    逻辑完全失效也照样通过（"恒空集自证通过"），故本测试必须独立存在、不能被
    其他断言隐式替代。
    """
    volume = parse.parse_volume_xml(fixture_bytes("10_volume_xml_bht_schema_normal.xml"))
    assert volume.container_dois == frozenset({"10.1007/978-3-030-99999-9"})
    assert volume.container_dois != frozenset()  # 冗余但故意直白的"非空"断言


def test_bht_schema_real_record_has_real_title_and_author_pids() -> None:
    """真实内容保真度：真实抓取记录的标题/作者/pid 逐字段核对（不是占位符）。"""
    volume = parse.parse_volume_xml(fixture_bytes("10_volume_xml_bht_schema_normal.xml"))
    aamand = _record_for(volume, "conf/icml/AamandACINS23")
    assert aamand.title == "Data Structures for Density Estimation."
    assert aamand.pages == "1-18"
    assert aamand.crossref == "conf/icml/2023"
    assert [a.name for a in aamand.authors] == [
        "Anders Aamand",
        "Alexandr Andoni",
        "Justin Y. Chen",
        "Piotr Indyk",
        "Shyam Narayanan",
        "Sandeep Silwal",
    ]
    assert aamand.authors[0].pid == "205/2416"


def test_bht_schema_no_proceedings_container_is_ever_converted_to_a_record() -> None:
    volume = parse.parse_volume_xml(fixture_bytes("10_volume_xml_bht_schema_normal.xml"))
    keys = {record.key for record in volume.records}
    assert "conf/icml/2023" not in keys
    assert "conf/xyz/2023" not in keys


def test_bht_schema_paper_level_doi_ee_produces_doi_identifier() -> None:
    volume = parse.parse_volume_xml(fixture_bytes("10_volume_xml_bht_schema_normal.xml"))
    smith = _record_for(volume, "conf/xyz/Smith23")
    stub = parse.to_paper_stub(smith, volume.container_dois)
    assert stub.identifiers == (
        ("dblp", "conf/xyz/Smith23"),
        ("doi", "10.1007/978-3-030-99999-9_1"),
    )


def test_bht_schema_distinct_paper_dois_do_not_collide() -> None:
    volume = parse.parse_volume_xml(fixture_bytes("10_volume_xml_bht_schema_normal.xml"))
    jones = _record_for(volume, "conf/xyz/Jones23")
    stub = parse.to_paper_stub(jones, volume.container_dois)
    assert ("doi", "10.1007/978-3-030-99999-9_2") in stub.identifiers


def test_bht_schema_adversarial_ee_produces_no_doi_identifier() -> None:
    """毒性缺陷防御，bht schema 下重锁定（dump schema 侧见
    `test_adversarial_ee_matching_container_doi_produces_no_doi_identifier`）。"""
    volume = parse.parse_volume_xml(fixture_bytes("10_volume_xml_bht_schema_normal.xml"))
    adversary = _record_for(volume, "conf/xyz/Adversary23")
    stub = parse.to_paper_stub(adversary, volume.container_dois)
    assert stub.identifiers == (("dblp", "conf/xyz/Adversary23"),)
    assert ("ee", "https://doi.org/10.1007/978-3-030-99999-9") in stub.meta


def test_bht_schema_non_doi_ee_goes_to_meta_not_identifier() -> None:
    volume = parse.parse_volume_xml(fixture_bytes("10_volume_xml_bht_schema_normal.xml"))
    abbas = _record_for(volume, "conf/icml/AbbasS23")
    stub = parse.to_paper_stub(abbas, volume.container_dois)
    assert stub.identifiers == (("dblp", "conf/icml/AbbasS23"),)
    assert ("ee", "https://proceedings.mlr.press/v202/abbas23a.html") in stub.meta


# --- ⑤未裁剪真实响应：1828 条端到端（审查阻断项的规模级证据）------------------------------------


def test_full_real_capture_parses_all_1828_records_with_zero_skips() -> None:
    volume = parse.parse_volume_xml(
        fixture_bytes("11_volume_xml_bht_schema_full_real_icml2023.xml")
    )
    assert len(volume.records) == 1828
    assert volume.skipped_missing_title == 0


def test_full_real_capture_first_and_last_keys_match_document_order() -> None:
    volume = parse.parse_volume_xml(
        fixture_bytes("11_volume_xml_bht_schema_full_real_icml2023.xml")
    )
    assert volume.records[0].key == "conf/icml/AamandACINS23"
    assert volume.records[-1].key == "conf/icml/ZouCLG23"


def test_full_real_capture_container_dois_is_empty_because_pmlr_has_no_dois() -> None:
    """与 `test_bht_schema_container_dois_is_non_empty` 互补：真实 ICML 容器确实
    没有 DOI（PMLR 不注册 DOI），此处的空集是**真实数据的诚实反映**，不是
    "查找逻辑失效"（那种失效由上面那条非空断言把关）——两条测试合起来才完整
    覆盖"该非空时非空、该空时空"两面。
    """
    volume = parse.parse_volume_xml(
        fixture_bytes("11_volume_xml_bht_schema_full_real_icml2023.xml")
    )
    assert volume.container_dois == frozenset()


def test_full_real_capture_no_paper_gets_a_spurious_doi_identifier() -> None:
    volume = parse.parse_volume_xml(
        fixture_bytes("11_volume_xml_bht_schema_full_real_icml2023.xml")
    )
    stubs = [parse.to_paper_stub(r, volume.container_dois) for r in volume.records]
    doi_ids = [i for stub in stubs for i in stub.identifiers if i[0] == "doi"]
    assert doi_ids == []
