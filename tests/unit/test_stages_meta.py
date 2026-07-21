"""`stages._meta_from_json` 单测（CS-1：meta round-trip 的容错降级分支）。

`_paper_stub` 从 `paper.meta_json` 还原 `PaperStub.meta`（resolve 依赖 enumerate 携带的
adapter 私有定位符，如 openreview pdf 相对路径）。本测试钉死其容错语义：NULL/畸形/非
dict 一律静默降级为空 meta（resolve 侧对缺失键已按「无该资产」处理，不需响亮停机），
合法 dict 按 sorted 键序还原为 tuple-of-tuples（与 `Repo._meta_to_json` 的 sort_keys 对齐）。
"""

from __future__ import annotations

from paper_crawler.pipeline.stages import _meta_from_json


def test_valid_json_object_restores_sorted_pairs() -> None:
    raw = '{"openreview_pdf": "/pdf/x.pdf", "doi": "10.1/y"}'
    # sorted 键序：doi < openreview_pdf。
    assert _meta_from_json(raw) == (("doi", "10.1/y"), ("openreview_pdf", "/pdf/x.pdf"))


def test_none_returns_empty() -> None:
    assert _meta_from_json(None) == ()


def test_empty_string_returns_empty() -> None:
    assert _meta_from_json("") == ()


def test_malformed_json_returns_empty() -> None:
    # 畸形/截断 JSON → 静默降级为空（非响亮停机）。
    assert _meta_from_json('{"openreview_pdf": ') == ()


def test_non_object_json_returns_empty() -> None:
    # 顶层非 object（数组 / 标量）→ 空。
    assert _meta_from_json("[1, 2, 3]") == ()
    assert _meta_from_json("42") == ()
    assert _meta_from_json('"a bare string"') == ()


def test_non_string_values_are_str_coerced() -> None:
    # 值经 str() 兜底（JSON number/bool → 文本），键序 sorted。
    result = _meta_from_json('{"n": 12, "flag": true}')
    assert result == (("flag", "True"), ("n", "12"))
