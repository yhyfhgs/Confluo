"""ACL Anthology 两代 anthology_id 解析/构造/归一 + DOI 归一 + license 年份二分。

design/adapters/acl-anthology.md §4/§9-★3/★5 落地：

- **两代 id 形态**（勘察 §1/§2 [LIVE]）：新式 ``{collection_id}-{volume_id}.{paper_num}``
  （如 ``2023.emnlp-main.1``；``collection_id`` 自身含点，如 ``2023.emnlp``；paper 号不
  零填充）；旧式 ``{collection_id}-{volume_id}{paper_num:03d}``（如 ``D19-1001``；
  ``collection_id`` 为单字母+两位年，volume 号与 paper 号之间无分隔符，paper 号零填充
  3 位）。两套构造正则不共用（模块 docstring 强调）。
- **读取优先于构造**：解析时优先直接读 XML ``<url>`` 元素文本（`normalize_from_url_element`），
  构造函数只作校验/``<url>`` 缺失兜底（T1 覆盖，parse.py 消费）。
- **归一**：anthology_id 本身**不做大小写归一**——新式小写 venue slug、旧式大写字母前缀
  均原样保留（站点侧已是规范形式，§4 裁决）；DOI 剥 `https://doi.org/` 前缀但同样保留
  原始大小写。
- **license**：§3/§9-★5 裁决，论文年份 < 2016 → CC BY-NC-SA 3.0；>= 2016 → CC BY 4.0。
"""

from __future__ import annotations

import re

from paper_crawler.errors import CrawlerError, ErrorClass

# 新式：{collection_id}-{volume_id}.{paper_num}；collection_id 恒以 4 位年份开头
# （可能含点，如 "2023.emnlp"），volume_id 为小写字母数字（可含连字符，如 "findings-emnlp"
# 场景下 volume_id 本身不含连字符——连字符出现在整体 id 里是 collection/volume 分隔符）。
_NEW_STYLE_RE = re.compile(
    r"^(?P<collection>\d{4}(?:\.[a-z0-9]+)?)-(?P<volume>[a-z0-9]+)\.(?P<paper>\d+)$"
)
# 旧式：{单字母}{两位年}-{4位数字}（主刊 1+3 位切分 / workshop 2+2 位切分，校验只认
# 整体 4 位数字形态，不区分切法——构造只支持 1+3 切分，见 `construct_old`）。字母前缀
# 大写严格匹配（站点侧恒大写，勘察 §2）——不做大小写归一：形态本身即以"站点侧规范
# 形式"为唯一合法态，小写变体视为非法形态而非待归一的等价输入（§4 裁决措辞的引申）。
_OLD_STYLE_RE = re.compile(r"^(?P<collection>[A-Z]\d{2})-(?P<suffix>\d{4})$")

_URL_PREFIXES = (
    "https://aclanthology.org/",
    "http://aclanthology.org/",
    "https://www.aclanthology.org/",
    "http://www.aclanthology.org/",
)

_DOI_PREFIX_RE = re.compile(r"^https?://(dx\.)?doi\.org/", re.IGNORECASE)

# §3/§9-★5：论文内容许可证按摄入年份二分（<2016 NC-SA、>=2016 BY）。SPDX 风格短码。
_LICENSE_PRE_2016 = "CC-BY-NC-SA-3.0"
_LICENSE_2016_PLUS = "CC-BY-4.0"
_LICENSE_CUTOVER_YEAR = 2016


def is_legal_form(id_str: str) -> bool:
    """`id_str` 是否匹配两代任一合法形态（不含大小写/前缀归一，纯形态校验）。"""
    return bool(_NEW_STYLE_RE.match(id_str) or _OLD_STYLE_RE.match(id_str))


def validate(id_str: str) -> None:
    """`id_str` 非两代合法形态之一 → `CrawlerError(PARSE)`。"""
    if not is_legal_form(id_str):
        raise CrawlerError(ErrorClass.PARSE, f"illegal acl anthology id form: {id_str!r}")


def normalize_from_url_element(raw: str) -> str:
    """``<url>`` 元素文本 → 裸 anthology_id（剥可能的完整 URL 外壳，schema `url-with-checksum`
    的两种变体之一）；剥壳后校验合法形态，非法 → `CrawlerError(PARSE)`。

    裸 id 变体（多数条目，勘察 §1）无需处理；完整 URL 变体剥 `aclanthology.org` 域前缀
    （大小写域名/带 www 两种，§2 `faq/linking` 证实二者等价）与可能的 `.pdf`/尾部斜杠。
    大小写原样保留——不做 lower/upper 归一（§4 裁决）。
    """
    text = raw.strip()
    for prefix in _URL_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    text = text.strip("/")
    if text.endswith(".pdf"):
        text = text[: -len(".pdf")]
    validate(text)
    return text


def _positive_int(paper_num: str) -> int:
    try:
        value = int(paper_num)
    except ValueError:
        raise CrawlerError(ErrorClass.PARSE, f"paper id is not an integer: {paper_num!r}") from None
    if value <= 0:
        raise CrawlerError(ErrorClass.PARSE, f"paper id is not positive: {paper_num!r}")
    return value


def construct_new(collection_id: str, volume_id: str, paper_num: str) -> str:
    """新式构造：``{collection_id}-{volume_id}.{paper_num}``（不零填充）。

    仅作 T1 校验用途 / XML ``<url>`` 缺失兜底（§4）——正常路径优先读 `<url>` 元素。
    """
    pid = _positive_int(paper_num)
    return f"{collection_id}-{volume_id}.{pid}"


def construct_old(collection_id: str, volume_id: str, paper_num: str) -> str:
    """旧式构造：``{collection_id}-{volume_id}{paper_num:03d}``（零填充 3 位、无分隔符）。

    仅支持主刊 1 位 volume + 3 位 paper 的切分（本 adapter Phase 2 范围仅 EMNLP，
    legacy prefix 'D' 属此类；workshop 的 2+2 切分不在本期构造覆盖范围内，形态校验
    ``is_legal_form``/`validate` 对两种切法一视同仁，只有构造函数偏窄）。
    """
    pid = _positive_int(paper_num)
    return f"{collection_id}-{volume_id}{pid:03d}"


def normalize_doi(raw: str) -> str:
    """DOI 归一：剥 `https://doi.org/`（含 `dx.doi.org`、大小写协议）前缀，保留原始大小写。"""
    return _DOI_PREFIX_RE.sub("", raw.strip())


def license_for_year(year: int) -> str:
    """论文年份 → 许可证短码（§3/§9-★5：<2016 CC BY-NC-SA 3.0；>=2016 CC BY 4.0）。"""
    return _LICENSE_PRE_2016 if year < _LICENSE_CUTOVER_YEAR else _LICENSE_2016_PLUS


__all__ = [
    "construct_new",
    "construct_old",
    "is_legal_form",
    "license_for_year",
    "normalize_doi",
    "normalize_from_url_element",
    "validate",
]
