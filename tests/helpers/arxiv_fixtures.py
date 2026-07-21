"""arxiv fixture 加载器（`tests/fixtures/arxiv/raw/`）。

八件套（+ 补充件）均为 **合成 fixture**（Phase 2 T5）——结构依 OAI-PMH 2.0 / Atom 1.0 /
arXiv API 规范，内容为构造值，各文件头以注释标注 "SYNTHETIC"。T7 在线冒烟负责用实测
响应对照保真度（并可经 `scripts/record_arxiv_fixtures.py` 重录）。

``.http`` 格式（⑥ 503 快照，响应头随 body 落盘——fixtures README 扩展）：
以 ``#`` 开头的行为注释；``HTTP-STATUS: <int>`` 声明状态码；其余 ``Key: Value`` 为
响应头；**首个空行**后为原始 body。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

_RAW = Path(__file__).resolve().parents[1] / "fixtures" / "arxiv" / "raw"


def fixture_bytes(name: str) -> bytes:
    """读取 `raw/<name>` 的原始字节。"""
    return (_RAW / name).read_bytes()


def http_fixture(name: str) -> tuple[int, dict[str, str], bytes]:
    """解析 ``.http`` 快照 → ``(status, headers, body)``（见模块 docstring 的格式说明）。"""
    raw = (_RAW / name).read_bytes()
    head, sep, body = raw.partition(b"\n\n")
    if not sep:  # 无空行分隔——整体视为 body，200 无头
        return 200, {}, raw
    status = 200
    headers: dict[str, str] = {}
    for line in head.decode("utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, _, value = stripped.partition(":")
        key, value = key.strip(), value.strip()
        if key.upper() == "HTTP-STATUS":
            status = int(value)
        else:
            headers[key] = value
    return status, headers, body


# ---------------------------------------------------------------------------
# 合成 OAI-PMH ListRecords 生成器（T6 watch 七收割日回放）
#
# 八件套静态 fixture（fixtures/arxiv/raw/）覆盖固定的解析/错误路由场景；watch 的
# 七收割日回放需要**按日序动态生成**逐日递增、重叠、announce-延迟的记录集，静态
# fixture 无法表达。本生成器产出结构等价于 fixture ②（02_oai_listrecords_page1.xml）
# 的合成 OAI-PMH 2.0 + arXiv `arXiv` 元数据 XML，文本值经 XML 转义。
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OaiRecord:
    """一条合成 OAI 记录的最小规格（供 `build_oai_listrecords` 渲染为 `<record>`）。

    `categories` 空格分隔，首个为 primary_category（adapter 子分类客户端过滤依据）。
    `deleted=True` 渲染为墓碑 header（`status="deleted"`、无 `<metadata>`）。
    """

    arxiv_id: str
    title: str
    categories: str = "cs.LG"
    created: str = "2024-06-01"
    abstract: str | None = None
    journal_ref: str | None = None
    doi: str | None = None
    deleted: bool = False


@dataclass
class OaiDay:
    """回放中某一收割日 OAI 窗口应返回的记录集（`build_oai_listrecords` 的输入）。"""

    records: list[OaiRecord] = field(default_factory=list)


def _render_record(rec: OaiRecord) -> str:
    if rec.deleted:
        return (
            '<record><header status="deleted">'
            f"<identifier>oai:arXiv.org:{escape(rec.arxiv_id)}</identifier>"
            f"<datestamp>{escape(rec.created)}</datestamp></header></record>"
        )
    lines = [
        "<record><header>",
        f"<identifier>oai:arXiv.org:{escape(rec.arxiv_id)}</identifier>",
        f"<datestamp>{escape(rec.created)}</datestamp><setSpec>cs</setSpec></header>",
        '<metadata><arXiv xmlns="http://arxiv.org/OAI/arXiv/">',
        f"<id>{escape(rec.arxiv_id)}</id>",
        f"<created>{escape(rec.created)}</created>",
        f"<title>{escape(rec.title)}</title>",
        f"<categories>{escape(rec.categories)}</categories>",
    ]
    if rec.journal_ref is not None:
        lines.append(f"<journal-ref>{escape(rec.journal_ref)}</journal-ref>")
    if rec.doi is not None:
        lines.append(f"<doi>{escape(rec.doi)}</doi>")
    if rec.abstract is not None:
        lines.append(f"<abstract>{escape(rec.abstract)}</abstract>")
    lines.append("</arXiv></metadata></record>")
    return "".join(lines)


def build_oai_listrecords(
    records: list[OaiRecord], *, resumption_token: str | None = None
) -> bytes:
    """把记录集渲染为一页合成 OAI-PMH `ListRecords` XML 字节（结构同 fixture ②）。

    `resumption_token` 非 None 时附 `<resumptionToken>`（触发 adapter 续页）；None（缺省）
    即单页收割结束。空 `records` 渲染为合法的空 `<ListRecords>`（非 `noRecordsMatch`——
    后者是独立错误页形态，见 fixture ⑩）。
    """
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<!-- SYNTHETIC (T6 watch replay generator). Structure per OAI-PMH 2.0 + arXiv"
        " `arXiv` metadata format; fabricated content. -->",
        '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">',
        "<responseDate>2024-06-30T08:00:00Z</responseDate>",
        '<request verb="ListRecords" metadataPrefix="arXiv" set="cs">'
        "https://oaipmh.arxiv.org/oai</request>",
        "<ListRecords>",
    ]
    parts.extend(_render_record(rec) for rec in records)
    if resumption_token is not None:
        parts.append(f"<resumptionToken>{escape(resumption_token)}</resumptionToken>")
    parts.append("</ListRecords></OAI-PMH>")
    return "\n".join(parts).encode("utf-8")


__all__ = [
    "OaiDay",
    "OaiRecord",
    "build_oai_listrecords",
    "fixture_bytes",
    "http_fixture",
]
