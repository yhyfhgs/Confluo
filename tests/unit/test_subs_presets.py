"""Phase 6 T8：预置 topic 包 ×9 的参数化冒烟测试（design/09 §4）。

范围：`subscriptions/presets/` 下 9 件预置 topic 包——只做"结构合法性"验收（领域
语义的真实性由审查 agent 做学术常识复核，见 T8 交付报告，不在本文件断言）：

- `load_subscription_file` 逐个解析零错（fail-loud 校验器本身已在 T1
  `tests/unit/test_subs_model.py` 覆盖，这里只验证 9 个真实文件都能过关）；
- 文件名 stem 与 `name` 一致（`load_subscription_file` 内建约束，此处对 9 件
  重申存在性，防未来加/改文件时漏了这条静默出错）；
- `guard` 在源 YAML 里显式写出两个字段（不依赖 `model.py` 的缺省补全——preset
  是给用户抄的模板，缺省值应该"看得见"，故本卡纪律比 T1 校验器本身更严格）；
- 每件至少声明一个源，且源集合是 `SOURCE_FIELDS` 六源子集；
- 每件都有非空 `filters`（体现"领域语义"要求——纯类目下推不足以证明取词有依据）。

**编译 smoke 未纳入**：T2（`subs/compile.py`）截至本卡（T8）尚未合并入 main
（`git show main:src/paper_crawler/subs/` 只见 `__init__.py`/`model.py`/
`types.py`，无 `compile.py`），故编译期 smoke 测试留待 T9（AC-6 端到端验收，
依赖 T2/T5/T6/T8 全部到位）补齐——不在本文件伪造一个提前失败或提前放水的断言。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from paper_crawler.subs.model import SOURCE_FIELDS, load_subscription_file

_PRESETS_DIR = Path(__file__).resolve().parents[2] / "subscriptions" / "presets"

# design/09 §4 清单（逐字，与任务卡 T8 范围一致）。
_PRESET_NAMES = (
    "llm-agents",
    "rl-theory",
    "causal-inference",
    "econometrics-methods",
    "asset-pricing",
    "market-microstructure",
    "corporate-finance",
    "mechanism-design",
    "optimization-ml",
)


def test_presets_dir_has_exactly_the_nine_design_doc_entries() -> None:
    """目录实际内容 == design/09 §4 清单（防漏件/多件/改名静默漂移）。"""
    on_disk = {path.stem for path in _PRESETS_DIR.glob("*.yaml")}
    assert on_disk == set(_PRESET_NAMES)


@pytest.mark.parametrize("preset_name", _PRESET_NAMES)
def test_preset_parses_without_error(preset_name: str) -> None:
    sub = load_subscription_file(_PRESETS_DIR / f"{preset_name}.yaml")
    assert sub.name == preset_name  # 隐含文件名 stem == name（否则解析期已拒载）


@pytest.mark.parametrize("preset_name", _PRESET_NAMES)
def test_preset_has_at_least_one_recognized_source(preset_name: str) -> None:
    sub = load_subscription_file(_PRESETS_DIR / f"{preset_name}.yaml")
    assert len(sub.sources) >= 1
    assert set(sub.source_names()).issubset(SOURCE_FIELDS)


@pytest.mark.parametrize("preset_name", _PRESET_NAMES)
def test_preset_guard_is_explicit_in_source_yaml(preset_name: str) -> None:
    """`guard` 两字段必须在 YAML 源文本里显式出现，不能靠 `model.py` 缺省补全。

    preset 是给用户抄的模板——若缺省值"看不见"，用户复制走后不会意识到有这道
    护栏（FR-16）。故本卡纪律比 T1 校验器本身更严格：不仅要解析通过，`guard`
    段本身要在文件里显式写出 `max_new_per_run` 与 `dedupe_against_library`。
    """
    path = _PRESETS_DIR / f"{preset_name}.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "guard" in raw, f"{preset_name}: guard 段缺失（不得依赖缺省补全）"
    guard = raw["guard"]
    assert "max_new_per_run" in guard, f"{preset_name}: guard.max_new_per_run 未显式声明"
    assert "dedupe_against_library" in guard, (
        f"{preset_name}: guard.dedupe_against_library 未显式声明"
    )


@pytest.mark.parametrize("preset_name", _PRESET_NAMES)
def test_preset_has_nonempty_local_filters(preset_name: str) -> None:
    """9 件都应有本地过滤——领域语义取词的落点（审查 agent 复核的对象）。"""
    sub = load_subscription_file(_PRESETS_DIR / f"{preset_name}.yaml")
    assert not sub.filters.is_empty()
    assert len(sub.filters.title_regex_any) >= 1


@pytest.mark.parametrize("preset_name", _PRESET_NAMES)
def test_preset_actions_and_guard_values_are_sane(preset_name: str) -> None:
    """数值域基本合理性（护栏不是摆设：> 0 且不至于大到形同虚设）。"""
    sub = load_subscription_file(_PRESETS_DIR / f"{preset_name}.yaml")
    assert 1 <= sub.guard.max_new_per_run <= 500
    assert sub.guard.dedupe_against_library is True
    assert sub.actions.auto_fetch_limit >= 0


def test_presets_directory_not_scanned_by_top_level_loader() -> None:
    """`load_subscriptions_dir` 只扫顶层——presets/ 是模板不是活订阅（model.py 目录语义）。

    用真实仓库路径断言：`subscriptions/` 顶层此刻不应有与 9 个 preset 同名的
    `*.yaml`（否则 `watch --all` 会把模板当成用户订阅跑掉）。存在即测试失败，
    提醒开发者这是用户复制模板后才会出现的产物，不该误提交到仓库顶层。
    """
    subscriptions_dir = _PRESETS_DIR.parent
    top_level_names = {path.stem for path in subscriptions_dir.glob("*.yaml")}
    assert top_level_names.isdisjoint(_PRESET_NAMES)
