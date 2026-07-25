"""`helpers.acl_anthology_bulk` 分卷计数 ↔ anchor JSON 独立正确性专测（F4 清账）。

S1 审计发现："acl bulk 对账生成器分卷计数手抄自 anchor（实证算术自洽而非独立正确性）"：
`tests/helpers/acl_anthology_bulk.py` 的 `MAIN_VOLUME_COUNTS`/`FINDINGS_EMNLP_COUNT` 系
手抄自 `anchor-emnlp-2023.json`；该模块此前唯一的自检 `assert TOTAL_EMNLP_2023 == 2241`
只证明这些手抄数字彼此加总自洽——即便手抄错了、只要凑出同一个 2241 仍会通过，不证明
它们真的等于锚点文件里的权威值。真正的独立交叉校验此前只隐性存在于
`tests/integration/test_acl_anthology_acceptance.py` 的一条三方链式 assert 里。

本文件把 `assert_matches_anchor`（该模块新增的显式校验函数，模块导入期已自调用一次）
的**失败路径**钉死：任一卷手抄计数与 anchor 独立漂移时必须响亮 `AssertionError`，而不是
被算术自洽的假象掩盖；并额外确认真实模块常量当前确与真实 anchor 文件一致。

**F4 审查追加两项反向断言**（逐项相等只查"我方键→anchor 值"单向；`assert
TOTAL_EMNLP_2023==2241` 也只是手抄合计与手抄字面量自洽）：
①集合等值 ``set(main_counts)|{"findings"} == set(anchor_by_volume)``——防"anchor
多出一卷、我方从未覆盖"这一逐项断言查不出的反向漂移；②合计交叉核对——本模块算出
的合计须与 anchor 自己记录的 `total` 字段一致，而非只跟手抄字面量 2241 比。
"""

from __future__ import annotations

from typing import Any

import pytest

from helpers.acl_anthology_bulk import (
    FINDINGS_EMNLP_COUNT,
    MAIN_VOLUME_COUNTS,
    _load_anchor,
    assert_matches_anchor,
)


def _anchor(by_volume: dict[str, int], *, total: int | None = None) -> dict[str, Any]:
    """构造测试用 anchor JSON 形状 ``{"volumes": [...], "total": N}``。

    `total` 缺省时自动取 `by_volume` 求和（"合计与分项自洽"的默认基线）；显式传入
    `total` 用于构造"分项都对、唯独合计字段本身漂移"的反向断言测试场景。
    """
    return {
        "volumes": [
            {"anthology_volume_id": vid, "paper_count": count} for vid, count in by_volume.items()
        ],
        "total": total if total is not None else sum(by_volume.values()),
    }


def test_assert_matches_anchor_passes_when_counts_align() -> None:
    assert_matches_anchor({"main": 10}, 5, _anchor({"main": 10, "findings": 5}))  # 不抛


def test_assert_matches_anchor_raises_on_main_volume_count_drift() -> None:
    # 主 volume 手抄计数与 anchor 独立漂移——即便总和仍可能自洽，这里必须响亮报错。
    with pytest.raises(AssertionError, match="MAIN_VOLUME_COUNTS"):
        assert_matches_anchor({"main": 10}, 5, _anchor({"main": 11, "findings": 5}))


def test_assert_matches_anchor_raises_on_findings_count_drift() -> None:
    with pytest.raises(AssertionError, match="FINDINGS_EMNLP_COUNT"):
        assert_matches_anchor({"main": 10}, 5, _anchor({"main": 10, "findings": 6}))


def test_assert_matches_anchor_raises_when_anchor_missing_a_volume_entirely() -> None:
    # anchor 表若缺失某卷条目（如未来重构手误删行），也不能悄悄放行。
    with pytest.raises(AssertionError, match="MAIN_VOLUME_COUNTS"):
        assert_matches_anchor({"main": 10, "tutorial": 2}, 5, _anchor({"main": 10, "findings": 5}))


# --- F4 审查追加：反向断言①集合等值 -----------------------------------------------------------


def test_assert_matches_anchor_raises_when_anchor_has_extra_volume_we_never_cover() -> None:
    # anchor 独有一卷（如未来新增 "workshop" track 却忘了在 bulk.py 里补登记）——逐项
    # 断言（只查 main_counts 的键）查不出这个方向的漂移，必须靠集合等值断言兜住。
    with pytest.raises(AssertionError, match="卷集合不一致"):
        assert_matches_anchor(
            {"main": 10}, 5, _anchor({"main": 10, "findings": 5, "workshop": 3}, total=18)
        )


def test_assert_matches_anchor_set_equality_error_names_both_sides() -> None:
    with pytest.raises(AssertionError) as exc:
        assert_matches_anchor(
            {"main": 10}, 5, _anchor({"main": 10, "findings": 5, "workshop": 3}, total=18)
        )
    assert "workshop" in str(exc.value)  # anchor 独有项需在报错信息里点名


# --- F4 审查追加：反向断言②合计交叉核对 -------------------------------------------------------


def test_assert_matches_anchor_raises_when_anchor_total_disagrees_with_computed_sum() -> None:
    # 分项逐一核对全部通过，但 anchor 自己记录的 total 字段与"分项求和"不一致（如
    # anchor 文件被手误改动了 total 而忘了同步分项，或反之）——集合等值也过不了这个
    # 缝（卷集合本身是对的），必须靠独立的合计交叉核对兜住。
    with pytest.raises(AssertionError, match="不一致"):
        assert_matches_anchor({"main": 10}, 5, _anchor({"main": 10, "findings": 5}, total=999))


def test_real_bulk_constants_match_real_anchor_file_independently() -> None:
    # 冒烟：真实手抄常量与真实 anchor 文件目前确实逐卷、逐集合、逐合计一致（模块导入期
    # 已断言过一次；这里用独立重新加载的 anchor 文档再验一遍，形成可命名、可独立运行
    # 的显式回归）。
    assert_matches_anchor(MAIN_VOLUME_COUNTS, FINDINGS_EMNLP_COUNT, _load_anchor())
