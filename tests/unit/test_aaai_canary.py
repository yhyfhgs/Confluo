"""aaai_ojs canary：3 个跨届固定 GetRecord 样本，规整化 `dc:title` + DOI-卷号双字段
比对（design/adapters/aaai-ojs.md §7）。

**分层说明**（呼应 adapter.py 模块 docstring）：design §4 的 `healthcheck()` 是运行期
OAI `Identify` ping（repositoryName 含 "AAAI"）；本文件的"3 样本已知答案比对"是**测试
层**的解析回归断言（先例 pmlr §6.4——把已知答案比对独立放测试层，不给运行期
healthcheck 增网络面）。双字段（规整化 title + DOI 卷号）而非原串精确匹配，抗折行/微调
flake。

**数据来源诚实声明**：样本①为真实数据（[LIVE] 2026-07-21 survey §5.2：
oai:ojs.aaai.org:article/3745，Vol.33/AAAI-19，title/DOI 实测）。样本②③的**卷号与届**
取自实测的 Vol↔年线性关系（Vol.37=2023、Vol.40=2026），但**具体 article id/title 是
本次实现标注合成**的占位（未做真实网络录制，`PAPER_CRAWLER_CONTACT_EMAIL` 未设，按
D-014 全走合成路径）；design §7 注明样本②③"于 T5 在线冒烟以实测替换"。
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from paper_crawler.adapters.aaai_ojs import parse

_NS = (
    'xmlns="http://www.openarchives.org/OAI/2.0/" '
    'xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" '
    'xmlns:dc="http://purl.org/dc/elements/1.1/"'
)


@dataclass(frozen=True)
class _Canary:
    """一条 canary 锚点：article id 定位 + 期望规整化 title + 期望 DOI 卷号。"""

    label: str
    article_id: str
    doi: str
    title: str
    volume: str


_CANARIES: tuple[_Canary, ...] = (
    # ① Vol.33/AAAI-19（2019）——真实数据（survey §5.2 [LIVE] article/3745）。
    _Canary(
        label="vol33-2019-real",
        article_id="3745",
        doi="10.1609/aaai.v33i01.3301695",
        title="Emergency Department Online Patient-Caregiver Scheduling",
        volume="33",
    ),
    # ② Vol.37/AAAI-23（2023）——卷号/届真实，article/title 合成占位（T5 冒烟以实测替换）。
    _Canary(
        label="vol37-2023-synthetic",
        article_id="25001",
        doi="10.1609/aaai.v37i1.25001",
        title="A Synthetic Cross-Edition Canary Paper for AAAI-23",
        volume="37",
    ),
    # ③ Vol.40/AAAI-26（2026）——当前届，卷号真实，article/title 合成占位。
    _Canary(
        label="vol40-2026-synthetic",
        article_id="36958",
        doi="10.1609/aaai.v40i1.36958",
        title="A Synthetic Current-Edition Canary Paper for AAAI-26",
        volume="40",
    ),
)


def _get_record_bytes(canary: _Canary) -> bytes:
    return (
        f'<?xml version="1.0"?><OAI-PMH {_NS}><GetRecord><record>'
        f"<header><identifier>oai:ojs.aaai.org:article/{canary.article_id}</identifier></header>"
        f"<metadata><oai_dc:dc>"
        f"<dc:title>{canary.title}</dc:title>"
        f"<dc:creator>Canary Author</dc:creator>"
        f"<dc:date>20{canary.volume[-2:]}-01-01</dc:date>"
        f"<dc:identifier>https://ojs.aaai.org/index.php/AAAI/article/view/{canary.article_id}</dc:identifier>"
        f"<dc:identifier>{canary.doi}</dc:identifier>"
        f"<dc:relation>https://ojs.aaai.org/index.php/AAAI/article/view/{canary.article_id}/9{canary.article_id}</dc:relation>"
        f"</oai_dc:dc></metadata></record></GetRecord></OAI-PMH>"
    ).encode()


@pytest.mark.parametrize("canary", _CANARIES, ids=[c.label for c in _CANARIES])
def test_canary_get_record_matches_known_title_and_volume(canary: _Canary) -> None:
    """解析层双字段比对：`AaaiRecord.title`（已规整化）+ DOI 抽出的卷号。"""
    record = parse.parse_get_record(_get_record_bytes(canary))
    assert record.title == canary.title  # 空白已规整化，直接等值
    assert record.volume == canary.volume
    assert record.doi == canary.doi


@pytest.mark.parametrize("canary", _CANARIES, ids=[c.label for c in _CANARIES])
def test_canary_end_to_end_to_paper_stub_produces_doi_identifier(canary: _Canary) -> None:
    """端到端到 PaperStub：identifier 恒为本源 DOI（★B），卷号可由 DOI 反解一致。"""
    stub = parse.to_paper_stub(parse.parse_get_record(_get_record_bytes(canary)))
    assert stub.identifiers == (("doi", canary.doi),)
    assert parse.volume_from_doi(dict(stub.identifiers)["doi"]) == canary.volume


def test_canary_set_covers_three_distinct_editions() -> None:
    """canary 集合自证覆盖面：跨 3 个不同卷号/届（抗单届漂移的回归锚点）。"""
    assert len({c.volume for c in _CANARIES}) == 3
    assert {c.volume for c in _CANARIES} == {"33", "37", "40"}
