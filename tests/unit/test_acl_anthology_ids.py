"""acl_anthology/ids.py 单测（design/adapters/acl-anthology.md §4/§9；T1 纯逻辑件）。

矩阵覆盖（design §7 T1 ①）：两代 id 解析（优先读 `<url>`）+ 构造 + 归一（新式不零填充
点分隔 × 旧式零填充 3 位无分隔 × 非法形态拒绝 × 大小写原样断言）；DOI 归一（剥前缀/
保大小写）；license 按年二分。零网络纯逻辑。
"""

from __future__ import annotations

import pytest

from paper_crawler.adapters.acl_anthology import ids
from paper_crawler.errors import CrawlerError, ErrorClass

# --- 合法矩阵：新式/旧式形态校验 ---------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "2023.emnlp-main.1",  # 新式，主会
        "2023.emnlp-tutorial.6",  # 新式，多位序号
        "2023.findings-emnlp.1059",  # 新式，findings 跨文件 join 后的构造形态
        "2020.acl-main.12",
        "D19-1001",  # 旧式，主刊 1+3 切分
        "P18-1024",  # 旧式，另一字母前缀
        "W19-5001",  # 旧式，workshop 2+2 切分（形态校验不区分切法）
    ],
)
def test_is_legal_form_accepts_both_generations(raw: str) -> None:
    assert ids.is_legal_form(raw) is True
    ids.validate(raw)  # 不抛


@pytest.mark.parametrize(
    "raw",
    [
        "",  # 空串
        "not-an-id",
        "2023.emnlp-main",  # 缺 paper 号
        "2023-emnlp-main.1",  # 分隔符错位（应为点分年.venue）
        "D19_1001",  # 旧式用了下划线而非连字符
        "D19-100",  # 旧式后缀不足 4 位
        "d19-1001",  # 旧式大写字母前缀被误传小写——形态即非法（不做大小写归一/放宽）
        "2023.emnlp-main.1.pdf",  # 误带扩展名后缀（未经过 normalize_from_url_element 剥离）
    ],
)
def test_is_legal_form_rejects_illegal_forms(raw: str) -> None:
    assert ids.is_legal_form(raw) is False
    with pytest.raises(CrawlerError) as exc:
        ids.validate(raw)
    assert exc.value.error_class is ErrorClass.PARSE


# --- 读取优先：normalize_from_url_element ------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2023.emnlp-main.1", "2023.emnlp-main.1"),  # 裸 id（多数条目形态，勘察 §1）
        ("D19-1001", "D19-1001"),  # 旧式裸 id，大写前缀原样保留
        (
            "https://aclanthology.org/2023.emnlp-main.1",
            "2023.emnlp-main.1",
        ),  # url-with-checksum 的完整 URL 变体
        ("https://aclanthology.org/2023.emnlp-main.1/", "2023.emnlp-main.1"),  # 尾部斜杠
        ("https://aclanthology.org/2023.emnlp-main.1.pdf", "2023.emnlp-main.1"),  # 误带 .pdf
        ("http://www.aclanthology.org/D19-1001", "D19-1001"),  # www + http 变体
        ("  2023.emnlp-main.1  ", "2023.emnlp-main.1"),  # 两侧空白
    ],
)
def test_normalize_from_url_element_strips_url_shell_and_keeps_case(
    raw: str, expected: str
) -> None:
    assert ids.normalize_from_url_element(raw) == expected


def test_normalize_from_url_element_rejects_illegal_bare_id() -> None:
    with pytest.raises(CrawlerError) as exc:
        ids.normalize_from_url_element("https://aclanthology.org/not-an-id")
    assert exc.value.error_class is ErrorClass.PARSE


# --- 构造：新式不零填充点分隔 / 旧式零填充 3 位无分隔 --------------------------------------------


def test_construct_new_does_not_zero_pad_and_uses_dot_separator() -> None:
    assert ids.construct_new("2023.emnlp", "main", "1") == "2023.emnlp-main.1"
    assert ids.construct_new("2023.emnlp", "main", "12") == "2023.emnlp-main.12"
    assert ids.construct_new("2023.findings", "emnlp", "1059") == "2023.findings-emnlp.1059"


def test_construct_old_zero_pads_three_digits_no_separator() -> None:
    assert ids.construct_old("D19", "1", "1") == "D19-1001"
    assert ids.construct_old("D19", "1", "12") == "D19-1012"
    assert ids.construct_old("D19", "1", "999") == "D19-1999"


@pytest.mark.parametrize("bad_paper_num", ["", "abc", "0", "-1", "1.5"])
def test_construct_rejects_non_positive_integer_paper_num(bad_paper_num: str) -> None:
    with pytest.raises(CrawlerError) as exc_new:
        ids.construct_new("2023.emnlp", "main", bad_paper_num)
    assert exc_new.value.error_class is ErrorClass.PARSE
    with pytest.raises(CrawlerError) as exc_old:
        ids.construct_old("D19", "1", bad_paper_num)
    assert exc_old.value.error_class is ErrorClass.PARSE


def test_constructed_ids_round_trip_through_is_legal_form() -> None:
    assert ids.is_legal_form(ids.construct_new("2023.emnlp", "main", "1")) is True
    assert ids.is_legal_form(ids.construct_old("D19", "1", "1")) is True


# --- DOI 归一：剥前缀保大小写 -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10.18653/v1/2023.emnlp-main.1", "10.18653/v1/2023.emnlp-main.1"),  # 已裸
        ("https://doi.org/10.18653/v1/2023.emnlp-main.1", "10.18653/v1/2023.emnlp-main.1"),
        ("http://doi.org/10.18653/v1/D19-1001", "10.18653/v1/D19-1001"),
        ("https://dx.doi.org/10.18653/v1/D19-1001", "10.18653/v1/D19-1001"),
        ("HTTPS://DOI.ORG/10.18653/v1/D19-1001", "10.18653/v1/D19-1001"),  # 协议大小写不敏感
        ("  10.18653/v1/2023.emnlp-main.1  ", "10.18653/v1/2023.emnlp-main.1"),  # 两侧空白
    ],
)
def test_normalize_doi_strips_prefix_and_keeps_case(raw: str, expected: str) -> None:
    assert ids.normalize_doi(raw) == expected


# --- license：按 2016 年二分 --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("year", "expected"),
    [
        (2015, "CC-BY-NC-SA-3.0"),
        (1999, "CC-BY-NC-SA-3.0"),
        (2016, "CC-BY-4.0"),  # 边界：2016 归入 BY 4.0（>=）
        (2023, "CC-BY-4.0"),
    ],
)
def test_license_for_year_splits_at_2016(year: int, expected: str) -> None:
    assert ids.license_for_year(year) == expected
