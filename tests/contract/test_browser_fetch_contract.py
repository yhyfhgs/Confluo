"""browser-fetch 冻结件契约（Phase 7 §2 冻结件表 `browserfetch.BrowserFetchHandle`；design/11 §9）。

三件事：

1. **Protocol/签名形态稳定性**：`BrowserFetchHandle` 三方法（goto/download_via/close）与
   `fetch_one` 的关键字形参集合——消费方（T11 三 adapter、T19 冒烟）按此接线，改动须仲裁；
2. **`RENDER_PAGE` 计划的 pipeline 识别契约**：派发**只看 `plan.url_strategy`**，与 adapter
   身份/family 无关；
3. **"注册了却没验证"反模式的结构性根治**：设计原文要求"声明 `RENDER_PAGE` 的 adapter 集合
   == 已接本通道的集合"的集合等值自断言。本实现里该集合**不存在**——没有 per-adapter 注册表
   可漂移（派发是策略驱动的单一分支），故等值断言的正确机械化形态是：① 断言不存在 adapter
   allowlist（两个不同 adapter_id 的 RENDER_PAGE 计划都命中同一分支）；② 断言凡在源码里声明
   `RENDER_PAGE` 的 adapter 都确实注册在 entry point 表内（否则"产了计划却进不了 pipeline"）。
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from pathlib import Path

import pytest

from paper_crawler.adapter import load_adapters
from paper_crawler.browserfetch import (
    BrowserFetchHandle,
    BrowserFetchOutcome,
    BudgetGate,
    PageResponse,
    fetch_one,
)
from paper_crawler.pipeline import StageContext
from paper_crawler.pipeline.stages import _fetch_via_browser  # 契约面：单一 browser 分支入口

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "paper_crawler"


# ---------------------------------------------------------------------------
# 1. 冻结件签名形态
# ---------------------------------------------------------------------------


def test_handle_protocol_methods_are_frozen() -> None:
    assert sorted(name for name in vars(BrowserFetchHandle) if not name.startswith("_")) == [
        "close",
        "download_via",
        "goto",
    ]

    goto = inspect.signature(BrowserFetchHandle.goto)
    assert list(goto.parameters) == ["self", "url"]
    assert goto.return_annotation in (PageResponse, "PageResponse")

    download = inspect.signature(BrowserFetchHandle.download_via)
    assert list(download.parameters) == ["self", "trigger", "dest"]

    assert list(inspect.signature(BrowserFetchHandle.close).parameters) == ["self"]


def test_page_response_is_exactly_the_classifier_quadruple() -> None:
    """四元组不多不少——`ChallengeDetector.classify` 的入参形态（§5.1）。"""
    assert list(PageResponse.__dataclass_fields__) == [
        "status",
        "headers",
        "final_url",
        "body",
    ]


def test_fetch_one_signature_is_keyword_only_and_stable() -> None:
    params = inspect.signature(fetch_one).parameters
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params.values())
    assert set(params) == {
        "plan",
        "venue_id",
        "dest",
        "storage_state",
        "budget",
        "detector",
        "resolve_in_context",
        "launch",
    }
    # 可选注入面（测试 seam / 同批约束 / 判定器）有默认值，消费方最小调用只需前五项。
    assert {name for name, p in params.items() if p.default is inspect.Parameter.empty} == {
        "plan",
        "venue_id",
        "dest",
        "storage_state",
        "budget",
    }
    assert inspect.signature(fetch_one).return_annotation in (
        BrowserFetchOutcome,
        "BrowserFetchOutcome",
    )


def test_budget_gate_surface_is_two_methods() -> None:
    assert list(inspect.signature(BudgetGate.check_or_raise).parameters) == [
        "self",
        "venue_id",
        "domain",
    ]
    assert list(inspect.signature(BudgetGate.wait_rate).parameters) == ["self", "domain"]


def test_stage_context_browser_slot_defaults_off() -> None:
    """新增槽是**纯附加、默认关**：既有直建 StageContext 的测试/命令行为逐字不变。"""
    field = StageContext.__dataclass_fields__["browser_fetch"]
    assert field.type in (bool, "bool")
    assert field.default is False


# ---------------------------------------------------------------------------
# 2/3. 派发契约 + 反模式结构性根治
# ---------------------------------------------------------------------------


def test_browser_branch_is_strategy_driven_not_adapter_allowlisted() -> None:
    """`_stage_fetch` 的分支条件只读 `plan.url_strategy`——源码里不得出现 adapter 名单。"""
    source = (SRC_ROOT / "pipeline" / "stages.py").read_text(encoding="utf-8")
    marker = "if plan.url_strategy is UrlStrategy.RENDER_PAGE:"
    assert source.count(marker) == 1  # 单一分支（案 A"一个分支 + 一个函数"量级纪律）
    branch_line = next(line for line in source.splitlines() if marker in line)
    assert "adapter" not in branch_line and "venue" not in branch_line
    # 通道入口恰好一个函数，且它不按 adapter_id 分流。
    body = inspect.getsource(_fetch_via_browser)
    assert "adapter_id" not in body


def test_adapters_declaring_render_page_are_registered() -> None:
    """凡源码里声明 `RENDER_PAGE` 的 adapter 包，都须在 entry point 表内可加载。

    这是"集合等值"在本实现下的可判形态：产 `RENDER_PAGE` 计划的 adapter 若未注册，
    计划根本进不了 pipeline——即"声明了却接不上"。T11 接入三消费方后本测自动覆盖它们。
    """
    registered = set(load_adapters())
    declaring: set[str] = set()
    for path in (SRC_ROOT / "adapters").rglob("*.py"):
        if "RENDER_PAGE" not in path.read_text(encoding="utf-8"):
            continue
        package = path.parent.name if path.name != path.parent.name else path.stem
        declaring.add(path.stem if package == "adapters" else package)
    assert declaring <= registered, f"声明 RENDER_PAGE 但未注册的 adapter: {declaring - registered}"


# ---------------------------------------------------------------------------
# 消费方最小接线样例（duck-type 可满足性——T11 照此实现即可）
# ---------------------------------------------------------------------------


class _MinimalHandle:
    def goto(self, url: str) -> PageResponse:
        return PageResponse(status=200, headers={}, final_url=url, body=b"")

    def download_via(self, trigger: Callable[[], None], dest: Path) -> int:
        trigger()
        return 0

    def close(self) -> None:
        return None


@pytest.mark.parametrize("method", ["goto", "download_via", "close"])
def test_minimal_duck_typed_handle_satisfies_protocol(method: str) -> None:
    handle: BrowserFetchHandle = _MinimalHandle()  # mypy 侧结构性校验 + 运行时存在性
    assert callable(getattr(handle, method))
