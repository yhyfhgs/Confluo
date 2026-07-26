"""AC-7.1 的标题匹配判据（12-fulltext-extract §12），**T7 与 T19 共用同一实现**。

两条路径判据分叉，均不弱于原文：

- **GROBID 路径**：TEI `titleStmt/title` 与 `paper.title` 的归一化编辑距离 / 标题长度 ≤ 0.15；
- **纯文本路径**（`ExtractedText.title` 为 None）：`paper.title` 的归一形出现在**正文前
  2000 字符**内，判据同为归一化编辑距离 ≤ 0.15 的**最优子串匹配**（学术 PDF 首页含标题，
  2000 字符窗足够且不虚高）。

编辑距离用本模块约 15 行 DP 实现（**零新依赖**）。

**阈值 0.15 与 2000 字符窗未经真实标定**（§12 / R8，如实声明）：二者是设计期的工程猜测，
不是实测结论——T7 的离线载体用生成式 PDF（标题是自己注进去的，必然 0 距离命中），**结构上
标定不了阈值**；第一次真实数据接触在 T19。处置口径已写死：T19 抽样若不达标，**先判「阈值
未标定」而非「抽取器不合格」**，逐篇人工过目失配样本区分三种成因（抽取器真抽错 → 修实现 /
标题归一化不足 → 修归一化 / 阈值定得太紧 → **允许一次**阈值修订），修订须把实测分布写进
验收记录并回填 §12 与 T18 的 AC 表述；**只允许这一次**，此后再改须走 ADR。
"""

from __future__ import annotations

import re

DEFAULT_MAX_RATIO = 0.15
DEFAULT_WINDOW = 2000

_NON_WORD_RE = re.compile(r"[^0-9a-z\s]+")


def normalize(text: str) -> str:
    """归一化：小写 + 去非字母数字 + 空白折叠（判据两侧同函数，防口径漂移）。"""
    return " ".join(_NON_WORD_RE.sub(" ", text.lower()).split())


def edit_distance(a: str, b: str) -> int:
    """Levenshtein 距离（滚动一维 DP）。"""
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def best_substring_distance(pattern: str, text: str) -> int:
    """`pattern` 与 `text` **任一子串**的最小编辑距离（首行全 0 = 起点自由，末行取 min）。"""
    if not pattern:
        return 0
    previous = [0] * (len(text) + 1)
    for i, cp in enumerate(pattern, start=1):
        current = [i]
        for j, ct in enumerate(text, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (cp != ct)))
        previous = current
    return min(previous)


def title_distance_ratio(title: str, extracted_title: str) -> float:
    """GROBID 路径判据：归一化编辑距离 / 归一化标题长度（标题为空 → 1.0，判不达标）。"""
    left, right = normalize(title), normalize(extracted_title)
    if not left:
        return 1.0
    return edit_distance(left, right) / len(left)


def title_in_body_ratio(title: str, body: str, *, window: int = DEFAULT_WINDOW) -> float:
    """纯文本路径判据：标题在**正文前 `window` 字符**内的最优子串匹配比。"""
    left = normalize(title)
    if not left:
        return 1.0
    return best_substring_distance(left, normalize(body[:window])) / len(left)


__all__ = [
    "DEFAULT_MAX_RATIO",
    "DEFAULT_WINDOW",
    "best_substring_distance",
    "edit_distance",
    "normalize",
    "title_distance_ratio",
    "title_in_body_ratio",
]
