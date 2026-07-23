"""`tests/fixtures/aea/` 证据 fixture 有效性验证（design/adapters/aea.md §8）。

**目的**：`aea` adapter 本身零网络（`resolve_assets` 全离线），不解析 Crossref/
Unpaywall JSON 或落地页 HTML——本文件不是"adapter 消费 fixture"式的解析回归测试
（那类测试见 `test_aea_parse.py`/`test_aea_adapter.py`），而是给 §8 要求的
"crossref AER works 含 abstract / 单条 DOI / landing citation_* / pubs
cf-mitigated: challenge 403（BLOCKED 边界）/ unpaywall closed+gold 两样本" 五件
证据 fixture **上覆盖网**：证明每个 fixture 文件本身结构合法、且其中被标记
`[LIVE-DERIVED]` 的关键判定性字段（DOI/ISSN/volume/issue/is_oa/oa_status/
host_type/cf-mitigated 头）与 `docs/research/site-survey/aea.md` 的实测记录一致
——锁定设计文档援引的证据事实，供未来该证据漂移时的回归信号（沿 D-019 锚点先例）。

**Challenge-BLOCKED 边界断言**（aea.md §9 DoD 明确要求）：`01_challenge_cf_mitigated`
经共享 `ChallengeDetector`（auth-framework §11）判定为 `CHALLENGE`——即便本 adapter
自身从不发出这个请求，也证明"若该响应真实发生，系统判定链条正确"，供未来
browser-fetch 通道消费同一判定器时复用同一条边界证据。
"""

from __future__ import annotations

import json

from helpers.aea_fixtures import fixture_bytes, http_fixture
from paper_crawler.auth.challenge import ChallengeDetector, ClassifyResult

# 站点勘察 [LIVE] 2026-07-24 实测的全文交付 URL（docs/research/site-survey/aea.md §4
# 附录请求 #11）——CHALLENGE 判定不依赖 final_url（头命中即判），此处仅供断言语境。
_JEP_PUBS_URL = "https://pubs.aeaweb.org/doi/pdfplus/10.1257/jep.20251473"

_DETECTOR = ChallengeDetector()


# --- ① pubs.aeaweb.org CF 挑战边界 fixture -----------------------------------------------


def test_fixture_01_challenge_classifies_as_challenge() -> None:
    status, headers, body = http_fixture("01_challenge_cf_mitigated.http")
    assert status == 403
    assert headers["cf-mitigated"] == "challenge"
    result = _DETECTOR.classify(status=status, headers=headers, final_url=_JEP_PUBS_URL, body=body)
    assert result is ClassifyResult.CHALLENGE


def test_fixture_01_challenge_header_signature_exact_match() -> None:
    """`cf-mitigated: challenge` 是判定器精确相等比对的信号（非子串）——大小写不敏感
    但值须逐字符匹配（ChallengeDetector 特征库 `_CHALLENGE_HEADER_SIGNATURES`）。
    """
    _, headers, _ = http_fixture("01_challenge_cf_mitigated.http")
    assert headers["server"] == "cloudflare"


def test_fixture_01_challenge_body_carries_redundant_cloudflare_signatures() -> None:
    """body 亦含 "Just a moment"/"/cdn-cgi/challenge-platform/" 冗余特征（头命中已
    足够判 CHALLENGE，此断言额外锁定 body 侧信号不漂移）。
    """
    _, _, body = http_fixture("01_challenge_cf_mitigated.http")
    text = body.decode("utf-8").lower()
    assert "just a moment" in text
    assert "/cdn-cgi/challenge-platform/" in text


# --- ②③ crossref AER works/单条 DOI fixture ------------------------------------------------


def test_fixture_02_crossref_works_sample_matches_site_survey_counts() -> None:
    data = json.loads(fixture_bytes("02_crossref_aer_works_sample.json"))
    assert data["message"]["total-results"] == 5643  # site-survey §3：AER total-results
    item = data["message"]["items"][0]
    assert item["DOI"] == "10.1257/aer.20230344"
    assert item["ISSN"] == ["0002-8282"]
    assert item["volume"] == "116"
    assert item["issue"] == "7"
    assert item["published"]["date-parts"] == [[2026, 7]]
    # abstract 存交（has_abstract=True）——长度以 site-survey 记录的 724 为中心，容
    # SYNTHETIC 填充文本与真实文本用词密度差异的宽容差（本 fixture 非真实版权文字，
    # 见 _grounded 字段）。
    abstract_len = len(item["abstract"])
    assert abs(abstract_len - 724) <= 60, f"abstract len {abstract_len} 偏离锚点 724 过多"


def test_fixture_03_crossref_single_doi_matches_site_survey_fields() -> None:
    data = json.loads(fixture_bytes("03_crossref_single_doi_aer.json"))
    assert data["message-type"] == "work"  # 单条 work 封套，区别于 02 号的 work-list
    message = data["message"]
    assert message["DOI"] == "10.1257/aer.20230344"
    assert message["type"] == "journal-article"
    assert message["container-title"] == ["American Economic Review"]
    assert message["volume"] == "116"
    assert message["issue"] == "7"
    assert message["author"][0]["affiliation"][0]["name"]  # 机构字段存交（site-survey §3）


def test_fixture_02_and_03_describe_the_same_doi() -> None:
    """works-list 与单条 work 两种封套形态描述同一篇真实勘察过的文章（DOI 一致），
    互为交叉核对（沿 site-survey §3 两端点各自实测的记录）。
    """
    works = json.loads(fixture_bytes("02_crossref_aer_works_sample.json"))
    single = json.loads(fixture_bytes("03_crossref_single_doi_aer.json"))
    assert works["message"]["items"][0]["DOI"] == single["message"]["DOI"]


# --- ④ landing citation_* meta fixture --------------------------------------------------


def test_fixture_04_landing_meta_carries_expected_citation_keys() -> None:
    html = fixture_bytes("04_landing_citation_meta.html").decode("utf-8")
    # aea.md §3"landing 页另有全套 citation_* meta"列出的键集合（site-survey §3/§4）。
    for key in (
        "citation_title",
        "citation_journal_title",
        "citation_issn",
        "citation_volume",
        "citation_issue",
        "citation_firstpage",
        "citation_lastpage",
        "citation_doi",
        "citation_pdf_url",
        "citation_author",
        "citation_author_institution",
    ):
        assert f'name="{key}"' in html, f"缺失 citation_* meta 键: {key}"
    assert 'content="10.1257/aer.20230344"' in html


# --- ⑤⑥ unpaywall closed（AER）+ gold（JEP）两样本 -----------------------------------------


def test_fixture_05_unpaywall_closed_matches_site_survey() -> None:
    data = json.loads(fixture_bytes("05_unpaywall_closed_aer.json"))
    assert data["doi"] == "10.1257/aer.20230344"
    assert data["is_oa"] is False
    assert data["oa_status"] == "closed"
    assert data["best_oa_location"] is None
    assert data["oa_locations"] == []  # site-survey §5："closed，0 OA location"


def test_fixture_06_unpaywall_gold_matches_site_survey() -> None:
    data = json.loads(fixture_bytes("06_unpaywall_gold_jep.json"))
    assert data["doi"] == "10.1257/jep.20251473"
    assert data["is_oa"] is True
    assert data["oa_status"] == "gold"
    assert data["journal_is_oa"] is True
    assert data["best_oa_location"]["host_type"] == "publisher"


def test_fixture_06_gold_best_oa_host_is_the_cf_blocked_pubs_domain() -> None:
    """反直觉发现回归锁定（aea.md §3.4）：即便"gold OA"，best_oa 副本的宿主仍是
    pubs.aeaweb.org——与 fixture ① 判定为 CHALLENGE 的同一域，故 stateless OA-fallback
    对该"gold"记录实质仍不可取（aea.md §10 风险条："实现期不应把 unpaywall 当 AEA
    全文主路"）。
    """
    data = json.loads(fixture_bytes("06_unpaywall_gold_jep.json"))
    pdf_url = data["best_oa_location"]["url_for_pdf"]
    assert pdf_url is not None
    assert pdf_url.startswith("https://pubs.aeaweb.org/")


def test_fixture_05_and_06_together_show_aea_oa_fallback_is_structurally_low() -> None:
    """订阅刊 closed + OA 刊 gold-但-CF域——两样本合并即 §3.4"OA-fallback 对 AEA 实质
    产出 ≈ 0"论断的最小复现（订阅刊无 OA 副本；OA 刊有"OA"标记但副本不可 stateless
    取）。
    """
    closed = json.loads(fixture_bytes("05_unpaywall_closed_aer.json"))
    gold = json.loads(fixture_bytes("06_unpaywall_gold_jep.json"))
    assert closed["is_oa"] is False
    assert gold["is_oa"] is True
    assert gold["best_oa_location"]["url_for_pdf"].startswith("https://pubs.aeaweb.org/")
