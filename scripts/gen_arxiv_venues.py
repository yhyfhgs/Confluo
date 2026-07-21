#!/usr/bin/env python3
"""生成 arXiv `preprint_channel` venue YAML（catalog/preprint-platforms.md §1 白名单）。

**单一真相源**：本脚本内联白名单表（category → 全名/领域/inception），确定性生成
`venues/preprint/arxiv-<archive>-<subject>.yaml` 全集。5 个代表 venue（arxiv-cs-lg
【AC-2.3 主承载】/arxiv-stat-ml/arxiv-econ-gn/arxiv-q-fin-pr/arxiv-math-oc）与其余
白名单条目同源生成，保证结构一致、全部过 `crawler venues lint`。

命名/派生（venue lint 强制"文件名 kebab→snake == id"）：
- id：category 小写、`.`/`-`→`_`、前缀 `arxiv_`（`q-fin.PR`→`arxiv_q_fin_pr`）。
- 文件名：category 小写、`.`→`-`、前缀 `arxiv-`（`q-fin.PR`→`arxiv-q-fin-pr.yaml`）。
- OAI set：archive 段 `category.split('.')[0]`（`q-fin.PR`→`q-fin`；带连字符 archive
  须显式落 quirks.arxiv_set，adapter 无法从 snake_case id 复原）。

inception（quirks）：该 category 所属 archive 的上线月**近似**——arXiv 分类史常识
（catalog 未给逐 category 起始月）。仅用于月度虚拟桶起点（discover）；backfill
（deferred）排期实现前应逐 category 核准。近似偏早无害（多出的空窗口 OAI 返回
noRecordsMatch 正常完成），偏晚才会漏早期论文，故取各 archive 保守下界。

用法：
    uv run python scripts/gen_arxiv_venues.py          # 生成到 venues/preprint/
    uv run python scripts/gen_arxiv_venues.py --check   # 只校验现有文件与生成物一致
"""

from __future__ import annotations

import sys
from pathlib import Path

_VENUES_DIR = Path(__file__).resolve().parents[1] / "venues" / "preprint"

# archive → (inception 'YYYY-MM', 近似依据注记)。arXiv 各 archive 上线月：
# - cs（CoRR）1998 上线；stat 2007 上线；q-fin 2008-12 上线；econ 2017 上线；
#   math 现代 subject 分类 1998 重整（archive 本体更早，取 1998 保守）。
_ARCHIVE_INCEPTION: dict[str, str] = {
    "cs": "1998-01",
    "stat": "2007-04",
    "econ": "2017-09",
    "q-fin": "2008-12",
    "math": "1998-01",
}

# 白名单表（catalog/preprint-platforms.md §1）：(category, 官方全名, field)。
# field ∈ {cs_ai, econ, finance, or_ms}（VenueSpec.field 枚举）。
_WHITELIST: tuple[tuple[str, str, str], ...] = (
    # CS/AI 核心
    ("cs.AI", "Artificial Intelligence", "cs_ai"),
    ("cs.LG", "Machine Learning", "cs_ai"),
    ("cs.CL", "Computation and Language", "cs_ai"),
    ("cs.CV", "Computer Vision and Pattern Recognition", "cs_ai"),
    ("cs.IR", "Information Retrieval", "cs_ai"),
    ("cs.MA", "Multiagent Systems", "cs_ai"),
    ("cs.NE", "Neural and Evolutionary Computing", "cs_ai"),
    ("cs.RO", "Robotics", "cs_ai"),
    ("cs.SD", "Sound", "cs_ai"),
    # CS 理论/交叉
    ("cs.GT", "Computer Science and Game Theory", "cs_ai"),
    ("cs.DS", "Data Structures and Algorithms", "cs_ai"),
    ("cs.CC", "Computational Complexity", "cs_ai"),
    ("cs.CR", "Cryptography and Security", "cs_ai"),
    ("cs.DB", "Databases", "cs_ai"),
    ("cs.SI", "Social and Information Networks", "cs_ai"),
    ("cs.HC", "Human-Computer Interaction", "cs_ai"),
    ("cs.IT", "Information Theory", "cs_ai"),
    # 统计
    ("stat.ML", "Machine Learning (Statistics)", "cs_ai"),
    # 经济
    ("econ.EM", "Econometrics", "econ"),
    ("econ.GN", "General Economics", "econ"),
    ("econ.TH", "Theoretical Economics", "econ"),
    # 量化金融（全部 9 个）
    ("q-fin.CP", "Computational Finance", "finance"),
    ("q-fin.EC", "Economics (Quantitative Finance)", "finance"),
    ("q-fin.GN", "General Finance", "finance"),
    ("q-fin.MF", "Mathematical Finance", "finance"),
    ("q-fin.PM", "Portfolio Management", "finance"),
    ("q-fin.PR", "Pricing of Securities", "finance"),
    ("q-fin.RM", "Risk Management", "finance"),
    ("q-fin.ST", "Statistical Finance", "finance"),
    ("q-fin.TR", "Trading and Market Microstructure", "finance"),
    # OR 交叉
    ("math.OC", "Optimization and Control", "or_ms"),
)


def _venue_id(category: str) -> str:
    return "arxiv_" + category.lower().replace(".", "_").replace("-", "_")


def _file_stem(category: str) -> str:
    return "arxiv-" + category.lower().replace(".", "-")


def _archive(category: str) -> str:
    return category.split(".", 1)[0]


def render_venue(category: str, full_name: str, field: str) -> str:
    """一个 category 的 VenueSpec YAML 文本（幂等；lint 可过）。"""
    archive = _archive(category)
    inception = _ARCHIVE_INCEPTION[archive]
    return f"""\
# {_file_stem(category)}.yaml —— arXiv {category}（自动生成 by scripts/gen_arxiv_venues.py）
id: {_venue_id(category)}
kind: preprint_channel
names:
  full: "arXiv {category} · {full_name}"
  aliases: ["{category}"]
field: [{field}]
tier: T1
metadata_source: arxiv
fulltext_source: arxiv
auth:
  level: none
quirks:
  inception: "{inception}"       # {archive} archive 上线月近似（arXiv 分类史）；月度桶起点
  arxiv_set: "{archive}"          # OAI-PMH archive 级 set
  arxiv_category: "{category}"    # 子分类客户端过滤 + set 派生（大小写敏感权威源）
status: active
notes: >
  自动生成（scripts/gen_arxiv_venues.py，catalog/preprint-platforms.md §1 白名单）。
  inception 为 archive 上线月近似，仅作月度虚拟桶起点；backfill 排期实现前逐 category 核准。
"""


def _targets() -> list[tuple[Path, str]]:
    out: list[tuple[Path, str]] = []
    for category, full_name, field in _WHITELIST:
        path = _VENUES_DIR / f"{_file_stem(category)}.yaml"
        out.append((path, render_venue(category, full_name, field)))
    return out


def main(argv: list[str]) -> int:
    check_only = "--check" in argv[1:]
    _VENUES_DIR.mkdir(parents=True, exist_ok=True)
    targets = _targets()

    if check_only:
        drift = [
            str(path)
            for path, text in targets
            if not path.is_file() or path.read_text(encoding="utf-8") != text
        ]
        if drift:
            print(f"drift: {len(drift)} venue file(s) differ from generator output:")
            for path in drift:
                print(f"  {path}")
            return 1
        print(f"ok: {len(targets)} venue file(s) match generator output")
        return 0

    for path, text in targets:
        path.write_text(text, encoding="utf-8")
    print(f"wrote {len(targets)} venue file(s) to {_VENUES_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
