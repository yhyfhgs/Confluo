"""Phase 6 T8：预置 topic 包 ×9 的参数化冒烟测试（design/09 §4）。

范围：`subscriptions/presets/` 下 9 件预置 topic 包，两层验收：

**结构合法性**（本文件第一批测试）：
- `load_subscription_file` 逐个解析零错（fail-loud 校验器本身已在 T1
  `tests/unit/test_subs_model.py` 覆盖，这里只验证 9 个真实文件都能过关）；
- 文件名 stem 与 `name` 一致（`load_subscription_file` 内建约束，此处对 9 件
  重申存在性，防未来加/改文件时漏了这条静默出错）；
- `guard` 在源 YAML 里显式写出两个字段（不依赖 `model.py` 的缺省补全——preset
  是给用户抄的模板，缺省值应该"看得见"，故本卡纪律比 T1 校验器本身更严格）；
- 每件至少声明一个源，且源集合是 `SOURCE_FIELDS` 六源子集；
- 每件都有非空 `filters`（体现"领域语义"要求——纯类目下推不足以证明取词有依据）。

**领域语义回归基准**（本文件第二批测试，T8 审查回合追加）：审查 agent 用各领域
真实经典论文标题实测，发现 P1 级缺陷（如 market-microstructure 6/6 经典标题被
本地过滤丢弃、causal-inference 6/6 丢弃或误杀——多为"query 有词、title_regex_any
无对应式"的死子句，或死板全词漏掉连字符/复数变体）。`CANONICAL_TITLES` 把审查
用过的实测标题资产化为回归门禁：每 preset ≥3 条正例（该领域公认经典/知名论文，
必须命中）+ ≥1 条负例（该领域知名"综述/survey"论文，必须被 `exclude_regex`
排除）。往后任何人再动 `title_regex_any`/`exclude_regex` 若重新引入同类缺陷，
这里立刻红。

**编译 smoke 未纳入**：T2（`subs/compile.py`）截至本卡（T8）尚未合并入 main
（`git show main:src/paper_crawler/subs/` 只见 `__init__.py`/`model.py`/
`types.py`，无 `compile.py`），故编译期 smoke 测试留待 T9（AC-6 端到端验收，
依赖 T2/T5/T6/T8 全部到位）补齐——不在本文件伪造一个提前失败或提前放水的断言。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from paper_crawler.subs.model import SOURCE_FIELDS, LocalFilter, load_subscription_file

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


# --- 领域语义回归基准（T8 审查回合：真实经典标题 → 回归门禁）----------------

# 每 preset：≥3 条该领域真实、可查证的经典/知名论文标题（正例，必须命中）+
# ≥1 条该领域知名"综述/survey"论文标题（负例，必须被 exclude_regex 排除）。
# 标题为真实论文标题（事实性引用，非受版权保护的创作内容），来源为公开可查证
# 的学术文献；choices 均经与 title_regex_any/exclude_regex 的逐条正则核对
# （见本文件测试断言本身即核对过程）。
CANONICAL_TITLES: dict[str, dict[str, list[str]]] = {
    "llm-agents": {
        "positive": [
            "Generative Agents: Interactive Simulacra of Human Behavior",
            "Toolformer: Language Models Can Teach Themselves to Use Tools",
            "Large Language Models are Zero-Shot Reasoners",
            "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena",
        ],
        "negative": ["The economy needs agent-based modelling"],
    },
    "rl-theory": {
        "positive": [
            "Near-optimal Regret Bounds for Reinforcement Learning in Factored"
            " Markov Decision Processes",
            "Policy Gradient Methods for Reinforcement Learning with Function Approximation",
            "On the Sample Complexity of Reinforcement Learning",
            "Finite-time Analysis of the Multiarmed Bandit Problem",
            "PAC Model-Free Reinforcement Learning",
        ],
        "negative": ["Reinforcement Learning: A Survey"],
    },
    "causal-inference": {
        "positive": [
            "Regression Discontinuity Designs: A Guide to Practice",
            "Synthetic Control Methods for Comparative Case Studies: Estimating"
            " the Effect of California's Tobacco Control Program",
            "Difference-in-Differences with Multiple Time Periods",
            "Double/Debiased Machine Learning for Treatment and Structural Parameters",
            "The Central Role of the Propensity Score in Observational Studies for Causal Effects",
        ],
        "negative": ["A Survey of Learning Causality with Data: Problems and Methods"],
    },
    "econometrics-methods": {
        "positive": [
            "Large Sample Properties of Generalized Method of Moments Estimators",
            "Instrumental Variables Regression with Weak Instruments",
            "Quantile Regression",
            "Co-integration and Error Correction: Representation, Estimation, and Testing",
            "Some Tests of Specification for Panel Data: Monte Carlo Evidence"
            " and an Application to Employment Equations",
        ],
        "negative": [
            "A Survey of Weak Instruments and Weak Identification in Generalized Method of Moments"
        ],
    },
    "asset-pricing": {
        "positive": [
            "The Equity Premium: A Puzzle",
            "The Cross-Section of Expected Stock Returns",
            "Dissecting Anomalies",
            "Bond Risk Premia",
            "Asset Pricing at the Millennium",
        ],
        "negative": ["A Survey of Behavioral Finance"],
    },
    "market-microstructure": {
        "positive": [
            "Commonality in Liquidity",
            "One Security, Many Markets: Determining the Contributions to Price Discovery",
            "The Components of the Bid-Ask Spread: A General Approach",
            "Dealership Market: Market-Making with Inventory",
            "The Flash Crash: High-Frequency Trading in an Electronic Market",
        ],
        "negative": ["Market Microstructure: A Survey"],
    },
    "corporate-finance": {
        "positive": [
            "The Determinants of Capital Structure Choice",
            "Do Managerial Objectives Drive Bad Acquisitions?",
            "Corporate Governance and Equity Prices",
            "A Review of IPO Activity, Pricing, and Allocations",
            "Managerial Power and Rent Extraction in the Design of Executive Compensation",
        ],
        "negative": ["A Survey of Corporate Governance"],
    },
    "mechanism-design": {
        "positive": [
            "Mechanism Design: How to Implement Social Goals",
            "School Choice: A Mechanism Design Approach",
            "Kidney Exchange",
            "Strategy-proofness and Arrow's Conditions: Existence and"
            " Correspondence Theorems for Voting Procedures and Social"
            " Welfare Functions",
            "Stable Matching: Theory, Evidence, and Practical Design",
        ],
        "negative": ["Combinatorial Auctions: A Survey"],
    },
    "optimization-ml": {
        "positive": [
            "Adam: A Method for Stochastic Optimization",
            "Large-Scale Machine Learning with Stochastic Gradient Descent",
            "On the Convergence of Adam and Beyond",
            "Mirror Descent and Nonlinear Projected Subgradient Methods for Convex Optimization",
            "Proximal Algorithms",
        ],
        "negative": ["A Survey of Optimization Methods from a Machine Learning Perspective"],
    },
}


def _would_ingest(filters: LocalFilter, title: str) -> bool:
    """模拟 T3（`subs/filter.py`，design/09 §3）的 title 过滤契约：大小写不敏感，
    `title_regex_any` 任一命中即通过、`exclude_regex` 任一命中即排除（排除优先）。

    T3 尚未合并（同上编译 smoke 说明），故此处用 `re` 直接模拟契约而非调用真实
    `filter_papers`——T5 集成 watch 管线后，可将本函数体替换为对真实实现的调用，
    本组测试数据（`CANONICAL_TITLES`）与断言形状不必变。
    """
    included = any(re.search(p, title, re.IGNORECASE) for p in filters.title_regex_any)
    excluded = any(re.search(p, title, re.IGNORECASE) for p in filters.exclude_regex)
    return included and not excluded


def test_canonical_titles_cover_every_preset() -> None:
    """基准数据自身完整性：9 件都要有 ≥3 正例 + ≥1 负例（防漏配/静默变空）。"""
    assert set(CANONICAL_TITLES) == set(_PRESET_NAMES)
    for name, cases in CANONICAL_TITLES.items():
        assert len(cases["positive"]) >= 3, f"{name}: 正例不足 3 条"
        assert len(cases["negative"]) >= 1, f"{name}: 负例不足 1 条"


@pytest.mark.parametrize("preset_name", _PRESET_NAMES)
def test_preset_domain_vocabulary_catches_canonical_titles(preset_name: str) -> None:
    """正例：该领域真实经典/知名论文标题必须被判定为命中（领域语义回归门禁）。"""
    sub = load_subscription_file(_PRESETS_DIR / f"{preset_name}.yaml")
    for title in CANONICAL_TITLES[preset_name]["positive"]:
        assert _would_ingest(sub.filters, title), f"{preset_name}: 经典标题未命中 —— {title!r}"


@pytest.mark.parametrize("preset_name", _PRESET_NAMES)
def test_preset_exclude_regex_catches_canonical_survey_titles(preset_name: str) -> None:
    """负例：该领域知名的"综述/survey"论文标题必须被 `exclude_regex` 挡下。"""
    sub = load_subscription_file(_PRESETS_DIR / f"{preset_name}.yaml")
    for title in CANONICAL_TITLES[preset_name]["negative"]:
        excluded = any(re.search(p, title, re.IGNORECASE) for p in sub.filters.exclude_regex)
        assert excluded, f"{preset_name}: 应排除的经典综述标题未被 exclude_regex 命中 —— {title!r}"
        assert not _would_ingest(sub.filters, title), (
            f"{preset_name}: 综述标题最终仍判定为收录 —— {title!r}"
        )
