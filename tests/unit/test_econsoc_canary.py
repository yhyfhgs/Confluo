"""econsoc canary：3 个跨刊固定 GetRecord 样本，规整化 `dc:title` + DOI 刊别双字段比对
（design/adapters/econsoc.md §4/§7）。

**分层说明**（呼应 adapter.py 模块 docstring）：design §4 的 `healthcheck()` 是运行期 TE OAI
`Identify` ping（repositoryName 含 "Theoretical Economics"）；本文件的"3 样本已知答案比对"是
**测试层**的解析回归断言（沿 aaai §7 / pmlr §6.4——把已知答案比对独立放测试层，不给运行期
healthcheck 增网络面）。双字段（规整化 title + DOI 刊别）而非原串精确匹配，抗折行/微调 flake。

**数据来源诚实声明**：三样本的 DOI 后缀（`ecta`/`te`/`qe`）与前缀（10.3982）为实测形态
（survey §1 [LIVE] 2026-07-24：ecta23709/te6021/qe2297）；具体 title 为本次实现标注合成的占位
（未做真实网络录制，`PAPER_CRAWLER_CONTACT_EMAIL` 未设，按 D-014 全走合成路径）；design §7 注明
样本于 T5 在线冒烟以实测替换。
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from paper_crawler.adapters.econsoc import parse

_NS = (
    'xmlns="http://www.openarchives.org/OAI/2.0/" '
    'xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" '
    'xmlns:dc="http://purl.org/dc/elements/1.1/"'
)


@dataclass(frozen=True)
class _Canary:
    """一条跨刊 canary 锚点：DOI（含刊别后缀）+ 期望规整化 title + 期望刊别键。"""

    label: str
    doi: str
    title: str
    journal: str


_CANARIES: tuple[_Canary, ...] = (
    # ① Econometrica（当前段自营，survey §1 [LIVE] ecta23709/2026）——刊别 ecma。
    _Canary(
        label="ecma-current-synthetic",
        doi="10.3982/ecta23709",
        title="A Synthetic Cross-Journal Canary Paper for Econometrica",
        journal="ecma",
    ),
    # ② Theoretical Economics（survey §1 [LIVE] te6021）——刊别 te。
    _Canary(
        label="te-synthetic",
        doi="10.3982/te6021",
        title="A Synthetic Cross-Journal Canary Paper for Theoretical Economics",
        journal="te",
    ),
    # ③ Quantitative Economics（survey §1 [LIVE] qe2297/2026）——刊别 qe。
    _Canary(
        label="qe-synthetic",
        doi="10.3982/qe2297",
        title="A Synthetic Cross-Journal Canary Paper for Quantitative Economics",
        journal="qe",
    ),
)


def _get_record_bytes(canary: _Canary) -> bytes:
    landing = f"https://econtheory.org/ojs/index.php/{canary.journal}/article/view/1"
    return (
        f'<?xml version="1.0"?><OAI-PMH {_NS}><GetRecord><record>'
        f"<header><identifier>oai:econtheory.org:{canary.doi}</identifier></header>"
        f"<metadata><oai_dc:dc>"
        f"<dc:title>{canary.title}</dc:title>"
        f"<dc:creator>Canary, Author</dc:creator>"
        f"<dc:date>2026-01-01</dc:date>"
        f"<dc:identifier>{landing}</dc:identifier>"
        f"<dc:identifier>{canary.doi}</dc:identifier>"
        f"<dc:rights>Creative Commons Attribution 4.0</dc:rights>"
        f"</oai_dc:dc></metadata></record></GetRecord></OAI-PMH>"
    ).encode()


@pytest.mark.parametrize("canary", _CANARIES, ids=[c.label for c in _CANARIES])
def test_canary_get_record_matches_known_title_and_journal(canary: _Canary) -> None:
    """解析层双字段比对：`EconsocRecord.title`（已规整化）+ DOI 抽出的刊别。"""
    record = parse.parse_get_record(_get_record_bytes(canary))
    assert record.title == canary.title
    assert record.journal == canary.journal
    assert record.doi == canary.doi  # 已归一小写


@pytest.mark.parametrize("canary", _CANARIES, ids=[c.label for c in _CANARIES])
def test_canary_end_to_end_to_paper_stub_produces_doi_identifier(canary: _Canary) -> None:
    """端到端到 PaperStub：identifier 恒为本源 DOI（★B），刊别可由 DOI 反解一致。"""
    stub = parse.to_paper_stub(parse.parse_get_record(_get_record_bytes(canary)))
    assert stub.identifiers == (("doi", canary.doi),)
    assert parse.journal_of_doi(dict(stub.identifiers)["doi"]) == canary.journal


def test_canary_set_covers_three_distinct_journals() -> None:
    """canary 集合自证覆盖面：跨 3 刊（ecma/te/qe，抗单刊漂移的回归锚点）。"""
    assert {c.journal for c in _CANARIES} == {"ecma", "te", "qe"}
