"""PMLR volumes (ICML, CoRL, COLT, AISTATS, UAI).

Facts checked 2026-11-19: `proceedings.mlr.press/feed.xml` lists volumes with descriptions such as
"Proceedings of ICML 2026" (v306); each volume's `assets/bib/bibliography.bib` carries an
`abstract` field (v267: about 7 MB, slow to download); no robots.txt.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from confluo_scout.adapters.base import Batch, CrawlContext, chunks, ensure
from confluo_scout.adapters.bibtex import delatex, parse_bibtex
from confluo_scout.records import PaperRecord, split_authors_bibtex

BASE = "https://proceedings.mlr.press"


def feed_volumes(feed_xml: str) -> list[tuple[int, str]]:
    out = []
    for item in re.findall(r"<item>(.*?)</item>", feed_xml, re.S):
        link = re.search(r"<link>\s*([^<]+?)\s*</link>", item)
        desc = re.search(r"<description>(.*?)</description>", item, re.S)
        if not link:
            continue
        m = re.search(r"/v(\d+)/?$", link.group(1).strip())
        if m:
            out.append((int(m.group(1)), (desc.group(1).strip() if desc else "")))
    return out


def volume_for(feed: list[tuple[int, str]], label: str, year: int) -> int | None:
    pat = re.compile(rf"\b{re.escape(label)}\b\s*'?{year}\b", re.I)
    hits = [v for v, d in feed if pat.search(d)]
    return max(hits) if hits else None


def parse_volume_bib(text: str, volume: int) -> list[PaperRecord]:
    out = []
    for e in parse_bibtex(text):
        if e["type"] != "inproceedings":
            continue
        title = delatex(e.get("title", ""))
        if not title:
            continue
        key = e["key"]
        url = e.get("url") or f"{BASE}/v{volume}/{key.removeprefix(f'pmlr-v{volume}-')}.html"
        out.append(PaperRecord(
            source="pmlr", source_key=key, title=title, authors=split_authors_bibtex(delatex(e.get("author", ""))),
            abstract=delatex(e.get("abstract", "")) or None, proceedings_url=url, pdf_url=e.get("pdf"),
            status="accepted",
        ))
    return out


class PMLRAdapter:
    name = "pmlr"

    def source_id(self, src: dict) -> str:
        return f"pmlr:{src.get('feed_label', '')}:{src['year']}"

    def crawl(self, src: dict, ctx: CrawlContext) -> Iterator[Batch]:
        volume = src.get("volume")
        if not volume and src.get("feed_label"):
            feed = ctx.fetcher.get(f"{BASE}/feed.xml", max_age=86400)
            volume = volume_for(feed_volumes(feed.text), src["feed_label"], src["year"])
        if not volume:
            yield Batch([], {}, note=f"PMLR: no volume for {src.get('feed_label')} {src['year']} yet")
            return
        r = ctx.fetcher.get(f"{BASE}/v{volume}/assets/bib/bibliography.bib", accept=(200, 404), timeout=600)
        if r.status == 404:
            yield Batch([], {}, note=f"PMLR v{volume}: no bibliography yet")
            return
        records = parse_volume_bib(r.text, volume)
        ensure(len(records) >= 10, f"PMLR v{volume}: only {len(records)} entries")
        with_abs = sum(1 for x in records if x.abstract)
        ensure(with_abs >= 0.8 * len(records), f"PMLR v{volume}: abstracts missing ({with_abs}/{len(records)})")
        for part in chunks(records, 500):
            yield Batch(part, {}, phase="published", note=f"PMLR v{volume}: {len(part)} papers")
