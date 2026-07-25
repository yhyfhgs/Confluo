"""aaai_ojs fixture 加载器（`tests/fixtures/aaai/raw/`）。

十一件套均为**合成 fixture**（Phase 2，aaai_ojs adapter 实现）——结构依
docs/research/site-survey/aaai-ojs.md 的 [LIVE] 2026-07-21 勘察记录构造（原始响应
归档 `aaai-raw/`）；第一条真实条目（Vol.33/AAAI-19 的 `article/3745`，勘察 §5.2 逐字
样本）复用实测字段值，其余为标注合成的占位内容；各文件头以注释标注 "SYNTHETIC"。
本次实现未做真实网络录制（D-014 约定：录制脚本要求 `PAPER_CRAWLER_CONTACT_EMAIL`
环境变量存在，本会话未设，按约定全走合成路径）。
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

_RAW = Path(__file__).resolve().parents[1] / "fixtures" / "aaai" / "raw"


def fixture_bytes(name: str) -> bytes:
    """读取 `raw/<name>` 的原始字节。"""
    return (_RAW / name).read_bytes()


# --- 合成多卷 ListRecords 页（冷回填请求计数专测用）---------------------------------------------

_RECORD_TMPL = """<record>
<header>
<identifier>oai:ojs.aaai.org:article/{article_id}</identifier>
<datestamp>2026-03-17T09:00:00Z</datestamp>
</header>
<metadata>
<oai_dc:dc>
<dc:title>Synthetic AAAI paper v{volume} #{article_id}</dc:title>
<dc:creator>Synthetic, Author</dc:creator>
<dc:description>SYNTHETIC abstract for cold-backfill request accounting.</dc:description>
<dc:date>{year}-03-17</dc:date>
<dc:identifier>https://ojs.aaai.org/index.php/AAAI/article/view/{article_id}</dc:identifier>
<dc:identifier>10.1609/aaai.v{volume}i1.{article_id}</dc:identifier>
<dc:source>Proceedings of the AAAI Conference on Artificial Intelligence; \
Vol. {volume} No. 1</dc:source>
<dc:relation>https://ojs.aaai.org/index.php/AAAI/article/view/{article_id}/1</dc:relation>
</oai_dc:dc>
</metadata>
</record>"""

_PAGE_TMPL = """<?xml version="1.0" encoding="UTF-8"?>
<!-- SYNTHETIC (helpers.aaai_fixtures.build_oai_page): 多卷混合 ListRecords 页，供
     跨卷分区/冷回填请求计数专测按需生成。 -->
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"
         xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
<responseDate>2026-07-26T00:00:00Z</responseDate>
<request verb="ListRecords" metadataPrefix="oai_dc">https://ojs.aaai.org/index.php/AAAI/oai</request>
<ListRecords>
{records}
<resumptionToken>{token}</resumptionToken>
</ListRecords>
</OAI-PMH>
"""


def build_oai_page(
    records: Sequence[tuple[str, str]], *, resumption_token: str | None = None
) -> bytes:
    """合成一页 `ListRecords`：`records` 为 ``(volume, article_id)`` 序列。

    `resumption_token=None` → 空 `<resumptionToken>`（= 收割结束，与真实 fixture
    ``02_oai_listrecords_page2.xml`` 同形）。年份取 ``volume + 1986``（站点实测线性
    关系，site-survey §11.2），DOI 形如 ``10.1609/aaai.v{volume}i1.{article_id}``。
    """
    body = "\n".join(
        _RECORD_TMPL.format(volume=volume, article_id=article_id, year=int(volume) + 1986)
        for volume, article_id in records
    )
    return _PAGE_TMPL.format(records=body, token=resumption_token or "").encode("utf-8")


__all__ = ["build_oai_page", "fixture_bytes"]
