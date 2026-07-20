"""Golden 文件比对（test-plan §2 fixture 纪律的实现）。

`assert_matches_golden(obj, golden_path)`：把 `obj`（dataclass 实例、或其
list/tuple）递归转换成 canonical 结构（dataclass→dict、`Enum`→`.value`、
tuple→list），再以 `sort_keys=True, indent=2` 序列化成 JSON 文本。

重录纪律（test-plan §2 "golden 变更必须人工过目"）：golden 文件不存在，或环境变量
`UPDATE_GOLDEN=1`，都会先把当前实际输出写入文件，然后**仍然 fail**（消息提示
"golden (re)recorded, review diff"）——这样重录永远不会在同一次运行里被静默
放行，必须人工看一眼 diff/新内容、确认无误后再提交，下一次不带 `UPDATE_GOLDEN`
重跑才会转绿。
"""

from __future__ import annotations

import dataclasses
import difflib
import json
import os
from enum import Enum
from pathlib import Path
from typing import Any

import pytest


def _canonicalize(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _canonicalize(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {str(k): _canonicalize(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_canonicalize(v) for v in obj]
    return obj


def canonical_json(obj: Any) -> str:
    """`obj` 的 canonical JSON 文本（键排序、缩进 2、UTF-8 不转义、末尾换行）。"""
    return json.dumps(_canonicalize(obj), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def assert_matches_golden(obj: Any, golden_path: Path) -> None:
    """断言 `obj` 的 canonical 序列化与 `golden_path` 文件内容一致。

    文件缺失或 `UPDATE_GOLDEN=1`：写入当前输出后 `pytest.fail`（强制人工过目，
    见模块 docstring）。否则按字符串精确比对，不一致时输出统一 diff 后 fail。
    """
    actual = canonical_json(obj)
    should_record = os.environ.get("UPDATE_GOLDEN") == "1" or not golden_path.exists()

    if should_record:
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(actual, encoding="utf-8")
        pytest.fail(
            f"golden (re)recorded, review diff: {golden_path}\n"
            "重录后必须人工检查内容再提交（test-plan §2）；无误后去掉 "
            "UPDATE_GOLDEN=1 重跑本测试应转绿。"
        )

    expected = golden_path.read_text(encoding="utf-8")
    if actual != expected:
        diff = "\n".join(
            difflib.unified_diff(
                expected.splitlines(),
                actual.splitlines(),
                fromfile=f"{golden_path} (expected)",
                tofile="actual",
                lineterm="",
            )
        )
        pytest.fail(f"golden mismatch for {golden_path}:\n{diff}")


__all__ = ["assert_matches_golden", "canonical_json"]
