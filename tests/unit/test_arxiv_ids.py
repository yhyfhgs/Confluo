"""arXiv id 两代解析/归一单测（design/adapters/arxiv.md §3；T4 纯逻辑件）。

矩阵覆盖：新代 4/5 位序号 × 带/不带 vN；旧代 archive[.subject] 形态 × 带/不带
vN；非法形态（空串/乱串/月份越界/版本非正整数/宽度错误/外部前缀污染）一律
`CrawlerError(ErrorClass.PARSE)`。
"""

import pytest

from paper_crawler.adapters.arxiv import ids
from paper_crawler.errors import CrawlerError, ErrorClass

# --- 合法矩阵：split_version ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected_base", "expected_version"),
    [
        # 新代：5 位序号（2015-01 起宽度），带/不带版本。
        ("2401.12345", "2401.12345", None),
        ("2401.12345v1", "2401.12345", 1),
        ("2401.12345v12", "2401.12345", 12),
        # 新代：4 位序号（2015-01 前宽度），带/不带版本。
        ("0704.0001", "0704.0001", None),
        ("0704.0001v2", "0704.0001", 2),
        # 月份边界：01 与 12 均合法。
        ("2401.00001", "2401.00001", None),
        ("2412.00001", "2412.00001", None),
        # 旧代：无 subject class，带/不带版本。
        ("hep-th/9901001", "hep-th/9901001", None),
        ("hep-th/9901001v3", "hep-th/9901001", 3),
        # 旧代：带 subject class（点分隔），带/不带版本。
        ("math.GT/0309136", "math.gt/0309136", None),
        ("cs.CG/9901001v1", "cs.cg/9901001", 1),
        # 旧代：archive 混合大小写 → 小写归一，斜杠保留。
        ("HEP-TH/9901001", "hep-th/9901001", None),
    ],
)
def test_split_version_accepts_legal_forms(
    raw: str, expected_base: str, expected_version: int | None
) -> None:
    base, version = ids.split_version(raw)
    assert base == expected_base
    assert version == expected_version


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2401.12345v7", "2401.12345"),
        ("hep-th/9901001v2", "hep-th/9901001"),
        ("HEP-TH/9901001v1", "hep-th/9901001"),  # 混合大小写 + 版本号同时命中两条归一规则
    ],
)
def test_normalize_strips_version(raw: str, expected: str) -> None:
    assert ids.normalize(raw) == expected


def test_normalize_is_idempotent_on_already_normalized_id() -> None:
    assert ids.normalize("2401.12345") == "2401.12345"
    assert ids.normalize("hep-th/9901001") == "hep-th/9901001"


# --- 非法矩阵 --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "",  # 空串
        "not-an-id",  # 乱串，两代都不匹配
        "12345",  # 纯数字，无点无斜杠
        "arXiv:2401.12345",  # 外部前缀污染——ids.py 只认裸 id，不认 "arXiv:" 前缀
        " 2401.12345",  # 前导空白
        "2401.12345 ",  # 尾随空白
        "2401.123",  # 新代序号宽度错误（3 位，非 4/5）
        "2401.123456",  # 新代序号宽度错误（6 位）
        "2413.12345",  # 新代月份越界（13）
        "2400.12345",  # 新代月份越界（00）
        "2401.12345v-1",  # 负版本号（正则拒绝负号，视为乱串）
        "2401.12345v0",  # 版本号非正整数（v0 不存在）
        "hep-th/990100",  # 旧代数字段宽度错误（6 位，非 7）
        "hep-th/99010001",  # 旧代数字段宽度错误（8 位）
        "hep-th/9901001v0",  # 旧代版本号非正整数
        "/9901001",  # 旧代缺 archive 前缀
        "hep-th/",  # 旧代缺数字段
    ],
)
def test_split_version_rejects_illegal_forms(raw: str) -> None:
    with pytest.raises(CrawlerError) as exc_info:
        ids.split_version(raw)
    assert exc_info.value.error_class is ErrorClass.PARSE


def test_normalize_rejects_illegal_form_too() -> None:
    with pytest.raises(CrawlerError) as exc_info:
        ids.normalize("bogus")
    assert exc_info.value.error_class is ErrorClass.PARSE
