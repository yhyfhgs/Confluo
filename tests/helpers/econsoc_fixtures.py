"""econsoc fixture 加载器（`tests/fixtures/econsoc/raw/`）+ 合成多年 ListRecords 页构造器。

五件套均为**合成 fixture**（Phase 5 T6，econsoc adapter 实现）——结构依
docs/research/site-survey/econometric-society.md 的 [LIVE] 2026-07-24 R0c 勘察记录构造
（TE OAI ListRecords oai_dc completeListSize 656；DOI 后缀 `te{n}` 为实测形态；
econometricsociety.org 当前段落地页含 galley 链 `/publications/.../file/{file}.PDF`）；
各文件头以注释标注 "SYNTHETIC"。本次实现未做真实网络录制（D-014 约定：录制脚本要求
`PAPER_CRAWLER_CONTACT_EMAIL` 环境变量，本会话未设，按约定全走合成路径）。

`build_oai_page`（T15/检查单#6 追加，结构移植自 `helpers.aaai_fixtures.build_oai_page`）：
供跨年分区缓存/冷回填请求计数专测按需生成合成多年混合页——econsoc 的 partition 维度是
`dc:date` 年（非 aaai 的 DOI 卷号），故记录以 ``(year, article_id)`` 而非
``(volume, article_id)`` 定型，DOI 形如 `10.3982/{journal}{article_id}`。
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

_RAW = Path(__file__).resolve().parents[1] / "fixtures" / "econsoc" / "raw"


def fixture_bytes(name: str) -> bytes:
    """读取 `raw/<name>` 的原始字节。"""
    return (_RAW / name).read_bytes()


# --- 合成多年 ListRecords 页（冷回填请求计数专测用）----------------------------------------------

_RECORD_TMPL = """<record>
<header>
<identifier>oai:econtheory.org:article/{article_id}</identifier>
<datestamp>{year}-03-17T09:00:00Z</datestamp>
</header>
<metadata>
<oai_dc:dc>
<dc:title>Synthetic econsoc paper {journal}{article_id}</dc:title>
<dc:creator>Synthetic, Author</dc:creator>
<dc:description>SYNTHETIC abstract for cold-backfill request accounting.</dc:description>
<dc:date>{year}-03-17</dc:date>
<dc:identifier>https://econtheory.org/ojs/index.php/{journal}/article/view/{article_id}</dc:identifier>
<dc:identifier>10.3982/{journal}{article_id}</dc:identifier>
<dc:source>Vol X, No 1 ({year}); 1-10</dc:source>
<dc:relation>https://www.econometricsociety.org/publications/x/{year}/01/01/x/file/\
{article_id}.PDF</dc:relation>
</oai_dc:dc>
</metadata>
</record>"""

_PAGE_TMPL = """<?xml version="1.0" encoding="UTF-8"?>
<!-- SYNTHETIC (helpers.econsoc_fixtures.build_oai_page): 多年混合 ListRecords 页，供
     跨年分区/冷回填请求计数专测按需生成。 -->
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"
         xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
<responseDate>2026-07-27T00:00:00Z</responseDate>
<request verb="ListRecords" metadataPrefix="oai_dc">https://econtheory.org/ojs/index.php/\
{journal}/oai</request>
<ListRecords>
{records}
<resumptionToken>{token}</resumptionToken>
</ListRecords>
</OAI-PMH>
"""


def build_oai_page(
    records: Sequence[tuple[int, str]],
    *,
    journal: str = "te",
    resumption_token: str | None = None,
) -> bytes:
    """合成一页 `ListRecords`：`records` 为 ``(year, article_id)`` 序列。

    `resumption_token=None` → 空 `<resumptionToken>`（= 收割结束，与真实 fixture
    ``02_oai_listrecords_page2.xml`` 同形）。DOI 形如 ``10.3982/{journal}{article_id}``
    （`journal` 默认 ``te``，可传 ``qe`` 构造 QE 记录/混刊页）。
    """
    body = "\n".join(
        _RECORD_TMPL.format(year=year, article_id=article_id, journal=journal)
        for year, article_id in records
    )
    return _PAGE_TMPL.format(records=body, token=resumption_token or "", journal=journal).encode(
        "utf-8"
    )


__all__ = ["build_oai_page", "fixture_bytes"]
