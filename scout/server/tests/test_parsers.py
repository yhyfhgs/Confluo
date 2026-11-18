import json

from confluo_scout.adapters.aaai import parse_records, parse_sets, section_area
from confluo_scout.adapters.acl import parse_collection
from confluo_scout.adapters.bibtex import delatex, parse_bibtex
from confluo_scout.adapters.cvf import parse_accepted, parse_list, parse_paper_page
from confluo_scout.adapters.ecva import parse_index, parse_paper
from confluo_scout.adapters.ijcai import parse_detail, parse_detail_json, parse_year
from confluo_scout.adapters.openreview import parse_note, status_from_venueid
from confluo_scout.adapters.pmlr import feed_volumes, parse_volume_bib, volume_for


def test_openreview_note_with_reviews(fixture_text):
    notes = json.loads(fixture_text("openreview_notes.json"))["notes"]
    rec = parse_note(notes[0], groups={"ICLR.cc/2026/Conference"}, track=None)
    assert rec.status == "accepted" and rec.decision_label == "Oral" and rec.tier == 4
    assert rec.forum_url.endswith("id=AbC123") and rec.pdf_url
    assert rec.keywords == ["calibration", "large language models"]
    assert len(rec.reviews) == 2
    r1 = next(r for r in rec.reviews if r.key == "R1")
    assert (r1.rating, r1.confidence) == (8.0, 4.0)
    assert set(r1.subscores) == {"soundness", "presentation", "contribution"}  # no flags, no free text
    r2 = next(r for r in rec.reviews if r.key == "R2")
    assert (r2.rating, r2.confidence) == (6.0, 3.0)
    rej = parse_note(notes[1], groups={"ICLR.cc/2026/Conference"}, track=None)
    assert rej.status == "rejected" and rej.decision_label is None and rej.reviews == []


def test_openreview_status_suffixes():
    g = {"ICLR.cc/2027/Conference"}
    assert status_from_venueid("ICLR.cc/2027/Conference/Submission", g) == "under_review"
    assert status_from_venueid("ICLR.cc/2027/Conference/Withdrawn_Submission", g) == "withdrawn"
    assert status_from_venueid("ICLR.cc/2027/Conference/Desk_Rejected_Submission", g) == "desk_rejected"
    assert status_from_venueid("ICLR.cc/2027/Conference", g) == "accepted"


def test_cvf_pages(fixture_text):
    entries = parse_list(fixture_text("cvf_list.html"))
    assert len(entries) == 2
    assert entries[0]["title"].startswith("Deterministic Image-to-Image Translation")
    assert entries[0]["authors"][0] == "Bohan Xiao"
    assert entries[0]["href"].startswith("https://openaccess.thecvf.com/content/CVPR2025/html/")
    info = parse_paper_page(fixture_text("cvf_paper.html"))
    assert len(info["abstract"]) > 200 and "- " not in info["abstract"][:80]
    rows = parse_accepted(fixture_text("cvf_accepted.html"))
    assert len(rows) == 3
    assert [r[1] for r in rows].count("Highlight") == 1 and [r[1] for r in rows].count("Poster") == 2


def test_acl_collection(fixture_bytes):
    recs = parse_collection(fixture_bytes("acl_collection.xml"), None)
    assert len(recs) == 2
    assert recs[0].title.startswith("EcomScriptBench")  # <fixed-case> joined without spaces
    assert recs[0].source_key == "2025.acl-long.1"
    assert recs[0].decision_label == "Main" and recs[0].track == "Long papers"
    assert recs[0].abstract and recs[0].pdf_url.endswith(".pdf")
    findings = parse_collection(fixture_bytes("acl_collection.xml"), {"long"}, findings=True)
    assert findings[0].decision_label == "Findings"


def test_aaai_oai(fixture_bytes):
    sets = parse_sets(b'<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><ListSets><set><setSpec>AAAI:NLP-III</setSpec>'
                      b"<setName>AAAI Technical Track on Natural Language Processing III</setName></set></ListSets></OAI-PMH>")
    assert section_area(sets["AAAI:NLP-III"]) == "Natural Language Processing"
    recs, token, error = parse_records(fixture_bytes("aaai_listrecords.xml"), 40, sets)
    assert error is None and token
    assert len(recs) == 2  # the record from another volume is filtered out
    assert all(r.abstract and r.doi.startswith("10.1609/") for r in recs)
    assert all(" " in a for r in recs for a in r.authors)  # "Last, First" -> "First Last"


def test_ijcai_pages(fixture_text):
    papers = parse_year(fixture_text("ijcai_year.html"), 2025)
    assert len(papers) == 2
    assert papers[0]["track"] == "Main Track"
    assert papers[0]["area"] == "Agent-based and Multi-agent Systems"
    assert papers[0]["doi"] == "10.24963/ijcai.2025/1"
    j = parse_detail_json(b'{"abstract": "A key problem.", "section": "Agent-based and Multi-agent Systems", '
                          b'"track": "Main Track", "keywords": ["MAS: Normative systems"]}')
    assert j == {"abstract": "A key problem.", "keywords": ["MAS: Normative systems"],
                 "area": "Agent-based and Multi-agent Systems", "track": "Main Track"}
    d = parse_detail(fixture_text("ijcai_detail.html"))
    assert d["abstract"].startswith("A key problem in the design of normative multi-agent systems")
    assert d["keywords"] and d["keywords"][0].startswith("Agent-based and Multi-agent Systems")


def test_ecva_pages(fixture_text):
    entries = parse_index(fixture_text("ecva_index.html"), 2024)
    assert len(entries) == 2
    assert entries[0]["authors"][0] == "Jacopo Bonato"
    assert entries[0]["doi"].startswith("10.1007/")
    assert parse_paper(fixture_text("ecva_paper.html")).startswith("In this paper, we introduce")


def test_pmlr_bib(fixture_text):
    entries = parse_bibtex(fixture_text("pmlr_bibliography.bib"))
    assert [e["type"] for e in entries] == ["proceedings", "inproceedings", "inproceedings"]
    recs = parse_volume_bib(fixture_text("pmlr_bibliography.bib"), 267)
    assert len(recs) == 2
    assert recs[0].title == "Aggregation of Dependent Expert Distributions in Multimodal Variational Autoencoders"
    assert recs[0].authors[0] == "Rogelio A. Mancisidor"
    assert "consistent" in recs[0].abstract and "{" not in recs[0].abstract
    assert recs[1].title == "Learning with Gödel Machines"
    assert delatex(r"G{\"o}del") == "Gödel"


def test_pmlr_feed():
    feed = ("<rss><channel><item><title>v306</title><description>Proceedings of ICML 2026</description>"
            "<link>https://proceedings.mlr.press/v306</link></item><item><title>v305</title>"
            "<description>Proceedings of CoRL 2025</description><link>https://proceedings.mlr.press/v305</link></item>"
            "</channel></rss>")
    vols = feed_volumes(feed)
    assert volume_for(vols, "ICML", 2026) == 306
    assert volume_for(vols, "CoRL", 2025) == 305
    assert volume_for(vols, "ICML", 2027) is None
