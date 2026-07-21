"""GitHub git-tree 清单解析与 (venue,year)→文件名 解析（design §4 discover/enumerate；§9-★4）。

**零网络纯逻辑**：本模块只消费已取回的 git-tree JSON 字节（`parse_tree_response`）与
已解析好的文件名集合，不发请求——网络编排（何时拉、24h 缓存、构造探测回退的实际
HTTP 调用）归 `adapter.py`（同 openreview `venues.py`/`parse.py` 的职责分层）。

- **端点选择（实现细节，design §4 未逐字冻结）**：`git/trees/master?recursive=1`
  ——GitHub Trees API 对分支名容忍度足够（不强制传真实 40 位 sha），`recursive=1`
  一次拿全整仓库全部 blob（含 `data/xml/*.xml`），比 design 描述的"先查
  `contents/data` 拿 `data/xml` 的 sha 再查该 sha 的 tree"两步更省一次请求、语义等价
  （"一次拿全清单"），故本实现取此路径。响应 `truncated=true`（GitHub 对超大仓库的
  截断信号）视为不完整清单，PARSE 失败而非静默按空处理——静默吞掉会让"有数据的年"
  被误判为 legal-empty。
- **两代文件名模式**：新式 `{year}.{venue_slug}.xml`；旧式 `{LETTER}{YY}.xml`
  （`LETTER` 取 venue YAML `quirks.anthology_legacy_prefix`）。`data/xml/` 前缀已在
  `parse_tree_response` 剥离，本模块内一律使用裸文件名（basename）。
"""

from __future__ import annotations

import json
import re

from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.types import VenueSpec

_DATA_XML_PREFIX = "data/xml/"
_XML_SUFFIX = ".xml"

# 新式文件名：{4位年}.{venue slug（小写字母数字，允许连字符如 "hep-th" 类 archive}}.xml。
_NEW_STYLE_FILE_RE = re.compile(r"^(?P<year>\d{4})\.(?P<venue>[a-z0-9]+(?:-[a-z0-9]+)*)\.xml$")
# 旧式文件名：{大写单字母}{两位年}.xml（勘察 §1/§2：D07~D19 等）。
_OLD_STYLE_FILE_RE = re.compile(r"^(?P<letter>[A-Z])(?P<yy>\d{2})\.xml$")

_LEGACY_PREFIX_QUIRK = "anthology_legacy_prefix"
# 两位年→四位年的世纪轴（标准 Y2K 轴点）：Anthology 摄入日期早于 2020 的老字母前缀
# 文件覆盖的历史区间落在两侧（如 EMNLP D07~D19 → 2007~2019；更早的 ACL 系可能落
# 199x），本轴点对本 adapter Phase 2 唯一登记的 EMNLP('D') 精确成立；其余字母前缀未
# 验证但作为通用兜底合理（模块 docstring 已声明"零网络纯逻辑"范围仅此）。
_CENTURY_PIVOT = 68


def parse_tree_response(data: bytes) -> frozenset[str]:
    """git-tree JSON 响应 → `data/xml/` 下的裸文件名集合（含 `schema.rnc` 自动被
    `.xml` 后缀过滤排除）。

    畸形 JSON / 缺 `tree` 数组 → `PARSE`；`truncated=true` → `PARSE`（模块 docstring
    "不完整清单不可静默吞掉"）。
    """
    try:
        doc = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CrawlerError(ErrorClass.PARSE, f"malformed github tree json: {exc}") from exc
    if not isinstance(doc, dict):
        raise CrawlerError(ErrorClass.PARSE, "github tree response is not a JSON object")
    if doc.get("truncated") is True:
        raise CrawlerError(
            ErrorClass.PARSE,
            "github tree response is truncated (incomplete data/xml listing) — "
            "refusing to treat missing entries as legal-empty",
        )
    raw_tree = doc.get("tree")
    if not isinstance(raw_tree, list):
        raise CrawlerError(ErrorClass.PARSE, "github tree response missing 'tree' array")

    names: set[str] = set()
    for entry in raw_tree:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if not isinstance(path, str):
            continue
        if entry.get("type") != "blob":
            continue
        if path.startswith(_DATA_XML_PREFIX) and path.endswith(_XML_SUFFIX):
            names.add(path[len(_DATA_XML_PREFIX) :])
    return frozenset(names)


def legacy_prefix(venue: VenueSpec) -> str | None:
    """venue YAML `quirks.anthology_legacy_prefix` → 单字母前缀；未声明/空白 → None。"""
    raw = venue.quirks.get(_LEGACY_PREFIX_QUIRK)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def new_style_filename(venue_id: str, year: int) -> str:
    """新式候选文件名：``{year}.{venue_id}.xml``。"""
    return f"{year}.{venue_id}{_XML_SUFFIX}"


def old_style_filename(prefix: str, year: int) -> str:
    """旧式候选文件名：``{prefix}{两位年}.xml``。"""
    return f"{prefix}{year % 100:02d}{_XML_SUFFIX}"


def findings_filename(year: int) -> str:
    """Findings 伴生文件名（按年合并、不按 venue 命名，§4 结构性核心）。"""
    return f"{year}.findings{_XML_SUFFIX}"


def resolve_primary_filename(venue: VenueSpec, year: int, filenames: frozenset[str]) -> str | None:
    """在已知清单 `filenames` 中解析 (venue,year) 的主文件名：新式优先，旧式兜底。

    两者均不在清单中 → None（该 venue-year 无 proceedings，§6 legal-empty 的
    警戒线索——调用方据此**零网络**短路，无需再发探测请求）。
    """
    new_name = new_style_filename(venue.id, year)
    if new_name in filenames:
        return new_name
    prefix = legacy_prefix(venue)
    if prefix is not None:
        old_name = old_style_filename(prefix, year)
        if old_name in filenames:
            return old_name
    return None


def _full_year(yy: int) -> int:
    return 2000 + yy if yy <= _CENTURY_PIVOT else 1900 + yy


def candidate_years(venue: VenueSpec, filenames: frozenset[str]) -> list[int]:
    """清单中该 venue 存在 proceedings 的年集合（新式∪旧式，升序）。discover_timeline 用。"""
    prefix = legacy_prefix(venue)
    years: set[int] = set()
    for name in filenames:
        new_match = _NEW_STYLE_FILE_RE.match(name)
        if new_match is not None and new_match.group("venue") == venue.id:
            years.add(int(new_match.group("year")))
            continue
        old_match = _OLD_STYLE_FILE_RE.match(name)
        if old_match is not None and prefix is not None and old_match.group("letter") == prefix:
            years.add(_full_year(int(old_match.group("yy"))))
    return sorted(years)


__all__ = [
    "candidate_years",
    "findings_filename",
    "legacy_prefix",
    "new_style_filename",
    "old_style_filename",
    "parse_tree_response",
    "resolve_primary_filename",
]
