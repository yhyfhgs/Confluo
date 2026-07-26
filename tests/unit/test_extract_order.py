"""§5.3 全序取 max 的纯函数级契约 + 顺序无关性的机器证明（design/12 §10-2/§10-8）。

`max` 是幂等 + 交换 + 结合的半格运算 ⇒ 终态是**输入集合**的函数、与注入顺序无关。这是
D-031（AC-3.4）已经付过一次学费的纪律，extract 面不重犯——否则「先跑 GROBID 后跑纯文本」
与反序会得到不同的库状态。本文件用 hypothesis 对随机排列做机器证明（复刻 D-031 的做法），
handler 级的同款回归锁见 `tests/integration/test_extract_stage.py`。
"""

from __future__ import annotations

import random

from hypothesis import given
from hypothesis import strategies as st

from paper_crawler.pipeline.extract import (
    RANK_EXTRACT_FAILED,
    RANK_INVALID,
    RANK_NOOP,
    extractor_rank,
    order_key,
    version_key,
)

_ULID_A = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
_ULID_B = "01BX5ZZKBKACTAV9WEVGEMMVRZ"


# -- version_key --------------------------------------------------------------------------


def test_version_key_takes_first_three_numeric_segments() -> None:
    assert version_key("5.1.0") == (5, 1, 0)
    assert version_key("0.8.2-SNAPSHOT") == (0, 8, 2)
    assert version_key("6.14") == (6, 14, 0)
    assert version_key("7") == (7, 0, 0)


def test_version_key_without_digits_is_zero() -> None:
    """[UNRESOLVED]：GROBID 版本端点格式未实测——无数字串归零，语义安全（不凭空压制）。"""
    assert version_key("unknown") == (0, 0, 0)
    assert version_key(None) == (0, 0, 0)
    assert version_key("") == (0, 0, 0)


# -- rank 序（§5.3；三回归锁之一）---------------------------------------------------------


def test_registered_extractor_ranks() -> None:
    assert extractor_rank("grobid") == 2
    assert extractor_rank("pypdf") == 1
    assert extractor_rank("noop") is None  # 未登记 → 调用方落 RANK_NOOP
    assert extractor_rank("future_ocr") is None


def test_rank_order_extract_failed_beats_noop() -> None:
    """**回归锁**：`extract_failed(0)` 必须高于 `noop(-1)`（初稿写反过，代价见下）。

    若反序，存量 noop 行会永久压制真实失败行 ⇒ 失败结论写不进库 ⇒ §5.2 的幂等键永远命不中
    ⇒ **每轮 pull 对同一批长尾扫描件重抽一次**（审查实测反例）。
    """
    assert RANK_EXTRACT_FAILED > RANK_NOOP > RANK_INVALID
    failed = order_key(rank=RANK_EXTRACT_FAILED, extractor_ver="1", char_count=0, asset_id=_ULID_A)
    noop = order_key(rank=RANK_NOOP, extractor_ver="1", char_count=0, asset_id=_ULID_A)
    assert failed > noop
    # 而任何真实抽取器又都高于 extract_failed（更强抽取器能自动取代失败结论）。
    real = order_key(rank=1, extractor_ver="6.0.0", char_count=1, asset_id=_ULID_A)
    assert real > failed


def test_grobid_outranks_pypdf_regardless_of_char_count() -> None:
    grobid = order_key(rank=2, extractor_ver="0.8.0", char_count=10, asset_id=_ULID_A)
    pypdf_key = order_key(rank=1, extractor_ver="9.9.9", char_count=999_999, asset_id=_ULID_B)
    assert grobid > pypdf_key


def test_version_outranks_char_count_within_same_extractor() -> None:
    """`ver_key` 位序**高于** `char_count`：版本是能力的显式声明，字数只是启发式。"""
    newer = order_key(rank=1, extractor_ver="7.0.0", char_count=10, asset_id=_ULID_A)
    older = order_key(rank=1, extractor_ver="6.0.0", char_count=50_000, asset_id=_ULID_A)
    assert newer > older


def test_char_count_breaks_ties_within_same_version() -> None:
    """同抽取器同版本、不同 asset（正刊版 vs OA 兜底版）：文本更长者胜（＝完整版）。"""
    longer = order_key(rank=1, extractor_ver="6.0.0", char_count=50_000, asset_id=_ULID_A)
    shorter = order_key(rank=1, extractor_ver="6.0.0", char_count=1_200, asset_id=_ULID_B)
    assert longer > shorter


def test_legacy_null_asset_id_sorts_first_and_loses() -> None:
    """legacy 归一：`asset_id IS NULL` → `""`，排在一切 ULID 之前 ⇒ 同键时 legacy 必败。"""
    legacy = order_key(rank=1, extractor_ver="6.0.0", char_count=10, asset_id=None)
    fresh = order_key(rank=1, extractor_ver="6.0.0", char_count=10, asset_id=_ULID_A)
    assert fresh > legacy


# -- 顺序无关性（hypothesis 属性测试）------------------------------------------------------

_records = st.lists(
    st.tuples(
        st.sampled_from([RANK_INVALID, RANK_NOOP, RANK_EXTRACT_FAILED, 1, 2]),
        st.sampled_from(["unknown", "0.8.0", "5.1.0", "6.14.2", "7.0.0"]),
        st.integers(min_value=0, max_value=200_000),
        st.sampled_from([None, "", _ULID_A, _ULID_B, "01CZZZZZZZZZZZZZZZZZZZZZZZ"]),
    ),
    min_size=1,
    max_size=8,
)


@given(records=_records, seed=st.integers(min_value=0, max_value=2**32 - 1))
def test_terminal_state_is_order_independent(
    records: list[tuple[int, str, int, str | None]], seed: int
) -> None:
    """任意注入顺序下，逐次「取 max」的终态恒等于集合的 max —— §5.3 顺序无关性的机器证明。"""
    keys = [order_key(rank=r, extractor_ver=v, char_count=c, asset_id=a) for r, v, c, a in records]
    shuffled = list(keys)
    random.Random(seed).shuffle(shuffled)

    terminal = shuffled[0]
    for key in shuffled[1:]:
        terminal = max(terminal, key)  # 逐条注入：胜者留库、败者零写入
    assert terminal == max(keys)


@given(records=_records)
def test_max_is_idempotent_and_commutative(
    records: list[tuple[int, str, int, str | None]],
) -> None:
    keys = [order_key(rank=r, extractor_ver=v, char_count=c, asset_id=a) for r, v, c, a in records]
    assert max([*keys, *keys]) == max(keys)  # 幂等（重跑不改终态）
    assert max(reversed(keys)) == max(keys)  # 交换
