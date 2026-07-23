"""nber/parse.py 单测（零网络纯逻辑；nber.md §3.2/§3.4/§7）。

覆盖：① DOI→series 号正则（w/t/大写/chapter/非 nber/畸形）；② **18 月窗谓词假时钟跨边界
open/gated**（红线核心，nber.md §7①②）；③ pub_date 解析（full/partial/畸形/越界）+ 加月钳日；
④ 全文 PDF URL 构造；⑤ 软门 HTML 嗅探；⑥ RSS `<item>` 反解（2 有效 + 1 畸形跳过 + guid 反解 +
畸形 XML→PARSE）。解析层 ≥90% 覆盖目标（DoD）。
"""

from __future__ import annotations

from datetime import date

import pytest

from helpers.nber_fixtures import fixture_bytes
from paper_crawler.adapters.nber import parse
from paper_crawler.errors import CrawlerError, ErrorClass

# 假时钟基准（nber.md [LIVE] 2026-07-24）：18 月窗谓词跨边界断言的固定 today。
_TODAY = date(2026, 7, 24)


# --- ① DOI→series 号正则 ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("doi", "expected"),
    [
        ("10.3386/w30000", "w30000"),  # 工作论文
        ("10.3386/t0042", "t0042"),  # 技术工作论文
        ("10.3386/w1", "w1"),  # 低号老论文
        ("10.3386/W30000", "w30000"),  # 大写归一小写（防御 normalize 前）
        ("  10.3386/w30000  ", "w30000"),  # 前后空白容错
        ("10.3386/c14009", None),  # book chapter（非 w/t series）→ None
        ("10.3386/w", None),  # 无数字号 → None
        ("10.3386/30000", None),  # 无 series 字母 → None
        ("10.1257/aer.20230001", None),  # 非 nber 前缀 → None
        ("10.3386/w30000/extra", None),  # 尾巴多余 → None
        ("", None),  # 空串 → None
    ],
)
def test_series_id_from_doi(doi: str, expected: str | None) -> None:
    assert parse.series_id_from_doi(doi) == expected


def test_series_letter() -> None:
    assert parse.series_letter("w30000") == "w"
    assert parse.series_letter("t0042") == "t"


def test_pdf_url_deterministic() -> None:
    assert (
        parse.pdf_url("w30000")
        == "https://www.nber.org/system/files/working_papers/w30000/w30000.pdf"
    )
    assert parse.pdf_url("t0042").endswith("/working_papers/t0042/t0042.pdf")


# --- ② 18 月窗谓词假时钟跨边界（红线核心）---------------------------------------------------


def _open(pub_date: str | None, months: int = 18) -> bool:
    return parse.is_open_after_window(pub_date, window_months=months, today=_TODAY)


def test_window_exact_boundary_is_open() -> None:
    """恰满 18 月（pub_date + 18mo == today）→ 开放（>= 边界含当日）。"""
    # 2025-01-24 + 18 月 = 2026-07-24 == today → open。
    assert _open("2025-01-24") is True


def test_window_one_day_short_is_gated() -> None:
    """差 1 天不足 18 月（pub_date + 18mo > today）→ 软门（gated）。"""
    # 2025-01-25 + 18 月 = 2026-07-25 > today → gated。
    assert _open("2025-01-25") is False


def test_window_clearly_old_is_open() -> None:
    assert _open("2015-06") is True
    assert _open("2010-01-01") is True


def test_window_clearly_recent_is_gated() -> None:
    assert _open("2026-06") is False
    assert _open("2026-07-01") is False


def test_window_missing_pub_date_conservatively_open() -> None:
    """pub_date 缺失 → 保守判开放（§3.2 步 2，交 fetch %PDF 守卫兜底）。"""
    assert _open(None) is True


def test_window_malformed_pub_date_conservatively_open() -> None:
    """畸形/不可解析 pub_date → 按缺失保守判开放（同 None 分支）。"""
    assert _open("not-a-date") is True
    assert _open("") is True


def test_window_partial_year_uses_first_of_precision() -> None:
    """'YYYY' 取该年 1 月 1 日（首日口径，已过月数取上界，偏向判开放）。"""
    # 2024-01-01 + 18 月 = 2025-07-01 <= today → open。
    assert _open("2024") is True
    # 2025-01-01 + 18 月 = 2026-07-01 <= today → open（恰过边界）。
    assert _open("2025") is True


def test_window_custom_window_months() -> None:
    """venue quirks 可自定义窗口（如 24 月）：2025-01 在 24 月窗内 → gated。"""
    assert parse.is_open_after_window("2025-01", window_months=24, today=_TODAY) is False
    assert parse.is_open_after_window("2024-07-01", window_months=24, today=_TODAY) is True


# --- ③ pub_date 解析 + 加月钳日 --------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2024-03-15", date(2024, 3, 15)),
        ("2024-03", date(2024, 3, 1)),  # YYYY-MM → 当月 1 日
        ("2024", date(2024, 1, 1)),  # YYYY → 1 月 1 日
        ("2024-03-15T00:00:00", date(2024, 3, 15)),  # 尾巴容错（^ 锚定前缀）
        ("2024-13", None),  # 月越界 → None
        ("2024-02-30", None),  # 日越界 → None
        ("garbage", None),
        ("", None),
    ],
)
def test_parse_pub_date(raw: str, expected: date | None) -> None:
    assert parse.parse_pub_date(raw) == expected


def test_add_months_clamps_day_to_month_end() -> None:
    assert parse._add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)  # 闰年 2 月
    assert parse._add_months(date(2023, 1, 31), 1) == date(2023, 2, 28)  # 平年 2 月
    assert parse._add_months(date(2024, 1, 15), 18) == date(2025, 7, 15)
    assert parse._add_months(date(2024, 12, 1), 1) == date(2025, 1, 1)  # 跨年进位


# --- ⑤ 软门 HTML 嗅探 ------------------------------------------------------------------------


def test_looks_like_html() -> None:
    assert parse.looks_like_html(b"<!DOCTYPE html><html>") is True
    assert parse.looks_like_html(b"  \n<html lang='en'>") is True  # 前导空白容错
    assert parse.looks_like_html(b"<head><html>") is True  # <html 内嵌
    assert parse.looks_like_html(b"%PDF-1.7\n") is False
    assert parse.looks_like_html(b"") is False


# --- ⑥ RSS <item> 反解 ------------------------------------------------------------------------


def test_doi_from_guid() -> None:
    assert parse.doi_from_guid("https://www.nber.org/papers/w33333") == "10.3386/w33333"
    assert parse.doi_from_guid("/papers/t0099") == "10.3386/t0099"
    assert parse.doi_from_guid("https://www.nber.org/papers/W12") == "10.3386/w12"  # 归一小写
    assert parse.doi_from_guid("https://www.nber.org/feed/entry/12345") is None  # 无 series 段


def test_parse_rss_items_fixture() -> None:
    """[LIVE 结构] new.xml 截断：2 有效 item + 1 畸形（缺 guid series 段）→ 跳过畸形。"""
    items = parse.parse_rss_items(fixture_bytes("01_rss_new_truncated.xml"))
    assert len(items) == 2  # 第 3 item 无 /papers/w{n} guid → 跳过
    first = items[0]
    assert first.doi == "10.3386/w33333"
    assert first.series_id == "w33333"
    assert "-- by" in first.title  # 标题含作者尾巴（原样保留）
    assert first.abstract is not None and "synthetic abstract" in first.abstract
    # 第 2 item 是 t-series（覆盖两 series prefix）。
    assert items[1].doi == "10.3386/t0099"
    assert items[1].series_id == "t0099"


def test_parse_rss_items_skips_item_without_guid() -> None:
    rss = b"<rss><channel><item><title>No guid</title></item></channel></rss>"
    assert parse.parse_rss_items(rss) == ()


def test_parse_rss_items_missing_description_is_none() -> None:
    rss = (
        b"<rss><channel><item><title>T</title>"
        b"<guid>https://www.nber.org/papers/w5</guid></item></channel></rss>"
    )
    items = parse.parse_rss_items(rss)
    assert len(items) == 1
    assert items[0].abstract is None


def test_parse_rss_items_malformed_xml_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_rss_items(b"<rss><channel><item> not closed")
    assert exc.value.error_class is ErrorClass.PARSE
