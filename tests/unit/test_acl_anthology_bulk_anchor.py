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
"""

from __future__ import annotations

import pytest

from helpers.acl_anthology_bulk import (
    FINDINGS_EMNLP_COUNT,
    MAIN_VOLUME_COUNTS,
    _load_anchor_by_volume,
    assert_matches_anchor,
)


def test_assert_matches_anchor_passes_when_counts_align() -> None:
    assert_matches_anchor({"main": 10}, 5, {"main": 10, "findings": 5})  # 不抛


def test_assert_matches_anchor_raises_on_main_volume_count_drift() -> None:
    # 主 volume 手抄计数与 anchor 独立漂移——即便总和仍可能自洽，这里必须响亮报错。
    with pytest.raises(AssertionError, match="MAIN_VOLUME_COUNTS"):
        assert_matches_anchor({"main": 10}, 5, {"main": 11, "findings": 5})


def test_assert_matches_anchor_raises_on_findings_count_drift() -> None:
    with pytest.raises(AssertionError, match="FINDINGS_EMNLP_COUNT"):
        assert_matches_anchor({"main": 10}, 5, {"main": 10, "findings": 6})


def test_assert_matches_anchor_raises_when_anchor_missing_a_volume_entirely() -> None:
    # anchor 表若缺失某卷条目（如未来重构手误删行），也不能悄悄放行。
    with pytest.raises(AssertionError, match="MAIN_VOLUME_COUNTS"):
        assert_matches_anchor({"main": 10, "tutorial": 2}, 5, {"main": 10, "findings": 5})


def test_real_bulk_constants_match_real_anchor_file_independently() -> None:
    # 冒烟：真实手抄常量与真实 anchor 文件目前确实逐卷一致（模块导入期已断言过一次；
    # 这里用独立重新加载的 anchor 表再验一遍，形成可命名、可独立运行的显式回归）。
    assert_matches_anchor(MAIN_VOLUME_COUNTS, FINDINGS_EMNLP_COUNT, _load_anchor_by_volume())
