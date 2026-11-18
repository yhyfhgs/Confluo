"""ACL Anthology (ACL, EMNLP, NAACL, EACL and their Findings volumes).

Facts checked 2026-11-19: the official data lives in GitHub `acl-org/acl-anthology` under
`data/xml/{year}.{event}.xml` (2025.acl.xml: 1,966 papers, each with an abstract) and
`{year}.findings.xml` (one volume per event). aclanthology.org has no robots.txt; content since
2016 is CC BY 4.0. 2026.acl, 2026.emnlp, 2026.eacl and 2026.findings exist; 2026.naacl does not.
"""

from __future__ import annotations

from collections.abc import Iterator

from lxml import etree

from confluo_scout.adapters.base import Batch, CrawlContext, chunks, ensure
from confluo_scout.records import TIER_FINDINGS, TIER_POSTER, PaperRecord, clean_text

RAW = "https://raw.githubusercontent.com/acl-org/acl-anthology/master/data/xml/"
SITE = "https://aclanthology.org/"

# volume id -> (label, tier, track)
VOLUMES = {
    "long": ("Main", TIER_POSTER, "Long papers"),
    "short": ("Main", TIER_POSTER, "Short papers"),
    "main": ("Main", TIER_POSTER, None),
    "papers": ("Main", TIER_POSTER, None),
    "industry": ("Industry", TIER_FINDINGS, "Industry"),
    "demo": ("Demo", TIER_FINDINGS, "System demonstrations"),
    "demos": ("Demo", TIER_FINDINGS, "System demonstrations"),
    "srw": ("SRW", TIER_FINDINGS, "Student research workshop"),
}
SKIP_VOLUMES = {"tutorials", "tutorial-abstracts", "tutorial"}


def _text(el) -> str:
    # Inline markup such as <fixed-case>E</fixed-case>com must be joined without separators.
    return clean_text("".join(el.itertext())) if el is not None else ""


def parse_collection(xml: bytes, volumes: set[str] | None, findings: bool = False) -> list[PaperRecord]:
    root = etree.fromstring(xml)
    coll = root.get("id")
    out = []
    for vol in root.findall("volume"):
        vid = vol.get("id")
        if vid in SKIP_VOLUMES or (volumes is not None and vid not in volumes):
            continue
        label, tier, track = ("Findings", TIER_FINDINGS, "Findings") if findings else VOLUMES.get(
            vid, ("Main", TIER_POSTER, vid))
        for paper in vol.findall("paper"):
            if paper.find("removed") is not None:
                continue
            url = (paper.findtext("url") or "").strip()
            if not url:
                url = f"{coll}-{vid}.{paper.get('id')}"
            authors = []
            for a in paper.findall("author"):
                name = " ".join(x for x in (_text(a.find("first")), _text(a.find("last"))) if x)
                if name:
                    authors.append(name)
            status = "withdrawn" if paper.find("retracted") is not None else "accepted"
            out.append(PaperRecord(
                source="acl", source_key=url, title=_text(paper.find("title")), authors=authors,
                abstract=_text(paper.find("abstract")) or None, status=status, decision_label=label, tier=tier,
                track=track, proceedings_url=f"{SITE}{url}/", pdf_url=f"{SITE}{url}.pdf",
                doi=(paper.findtext("doi") or "").strip() or None,
            ))
    return out


class ACLAdapter:
    name = "acl"

    def source_id(self, src: dict) -> str:
        return f"acl:{src['year']}.{src['event']}"

    def crawl(self, src: dict, ctx: CrawlContext) -> Iterator[Batch]:
        year, event = src["year"], src["event"]
        main = ctx.fetcher.get(f"{RAW}{year}.{event}.xml", accept=(200, 404), timeout=300)
        if main.status == 404:
            yield Batch([], {}, note=f"{year}.{event}.xml not in the Anthology yet")
            return
        records = parse_collection(main.content, None)
        ensure(len(records) >= 20, f"ACL {year}.{event}: only {len(records)} papers")
        with_abs = sum(1 for r in records if r.abstract)
        ensure(with_abs >= 0.6 * len(records), f"ACL {year}.{event}: abstracts missing ({with_abs}/{len(records)})")
        for part in chunks(records, 500):
            yield Batch(part, {}, phase="published", note=f"{year}.{event}: {len(part)} papers")
        fnd = ctx.fetcher.get(f"{RAW}{year}.findings.xml", accept=(200, 404), timeout=300)
        if fnd.status == 200:
            frecs = parse_collection(fnd.content, {event}, findings=True)
            for part in chunks(frecs, 500):
                yield Batch(part, {}, phase="published", note=f"{year}.findings/{event}: {len(part)} papers")
