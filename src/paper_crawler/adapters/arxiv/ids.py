"""arXiv 论文 id 两代解析/归一（design/adapters/arxiv.md §3 identifier 归一裁决）。

两代形态：

- **新代**（2007-04 起）：``YYMM.NNNNN[vN]``——序号 2015-01 前 4 位，此后 5 位。
- **旧代**（更早）：``archive[.subject]/YYMMNNN[vN]``，如 ``hep-th/9901001``、
  ``math.GT/0309136``。

``normalize()`` 返回去版本号的规范 base id：新代原样返回（全数字，无大小写问
题）；旧代做小写归一但**保留斜杠分隔符**——这是跨版本/跨源强合并锚点的前提
（arxiv.md §3：``identifier(scheme='arxiv')`` 的 value 必须是该规范 base id）。
版本号只入 ``asset.version``，不进 identifier value，因此单独用
``split_version()`` 取出。

非法形态（空串、结构不匹配、月份越界、版本号非正整数等）一律抛
``CrawlerError(ErrorClass.PARSE)``——两代 id 均不做 archive/subject 白名单校验，
只校验形态；具体分类清单归 catalog 层管理。
"""

import re

from paper_crawler.errors import CrawlerError, ErrorClass

# 新代：(YY)(MM).(序号 4-5 位)，可选版本后缀。
_NEW_STYLE_RE = re.compile(r"^(?P<yy>\d{2})(?P<mm>\d{2})\.(?P<seq>\d{4,5})(?:v(?P<version>\d+))?$")

# 旧代：archive[.subject]/(YYMMNNN 7 位数字)，可选版本后缀。archive 部分只校验
# 形态（字母/点/连字符），不核对具体分类是否在 arXiv 官方归档表中。
_OLD_STYLE_RE = re.compile(
    r"^(?P<prefix>[a-zA-Z][a-zA-Z.\-]*)/(?P<num>\d{7})(?:v(?P<version>\d+))?$"
)


def split_version(id_str: str) -> tuple[str, int | None]:
    """把 arXiv id 拆成 ``(去版本号的规范 base id, 版本号|None)``。

    base id 已做归一（旧代小写、保留斜杠；新代原样）。非法形态抛
    ``CrawlerError(ErrorClass.PARSE)``。
    """
    if not id_str:
        raise CrawlerError(ErrorClass.PARSE, "arxiv id is empty")

    new_match = _NEW_STYLE_RE.match(id_str)
    if new_match is not None:
        month = int(new_match.group("mm"))
        if not 1 <= month <= 12:
            raise CrawlerError(ErrorClass.PARSE, f"arxiv id has out-of-range month: {id_str!r}")
        version = _parse_version(new_match.group("version"), id_str)
        base = f"{new_match.group('yy')}{new_match.group('mm')}.{new_match.group('seq')}"
        return base, version

    old_match = _OLD_STYLE_RE.match(id_str)
    if old_match is not None:
        version = _parse_version(old_match.group("version"), id_str)
        base = f"{old_match.group('prefix').lower()}/{old_match.group('num')}"
        return base, version

    raise CrawlerError(ErrorClass.PARSE, f"unrecognized arxiv id form: {id_str!r}")


def normalize(id_str: str) -> str:
    """返回去版本号的规范 base id（跨版本/跨源强合并锚点，arxiv.md §3）。"""
    base, _version = split_version(id_str)
    return base


def _parse_version(raw: str | None, id_str: str) -> int | None:
    """把捕获组文本转成正整数版本号；``v0``/负数（正则本就拒绝负号）一律非法。"""
    if raw is None:
        return None
    version = int(raw)
    if version < 1:
        raise CrawlerError(ErrorClass.PARSE, f"arxiv id has non-positive version: {id_str!r}")
    return version


__all__ = ["normalize", "split_version"]
