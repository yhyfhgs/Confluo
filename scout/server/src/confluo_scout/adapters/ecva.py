"""ECVA (ECCV papers).

Facts checked 2026-11-19: `www.ecva.net/papers.php` is one page (3.6 MB) with ECCV 2018-2024
sections; ECCV 2026 is not on it yet. robots.txt only addresses Googlebot. Paper pages carry
the abstract in `<div id="abstract">` (wrapped in quotes).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from urllib.parse import urljoin

from lxml import html as lxml_html

from confluo_scout.adapters.base import Batch, CrawlContext, chunks, ensure
from confluo_scout.records import PaperRecord, clean_text, norm_title

BASE = "https://www.ecva.net/"


def parse_index(page: str, year: int) -> list[dict]:
    doc = lxml_html.fromstring(page)
    out = []
    marker = f"eccv_{year}"
    for dt in doc.xpath('//dt[contains(@class, "ptitle")]'):
        a = dt.xpath(".//a[@href]")
        if not a or marker not in a[0].get("href", ""):
            continue
        href = urljoin(BASE, a[0].get("href").strip())
        title = clean_text(a[0].text_content())
        authors: list[str] = []
        pdf = doi = None
        sib = dt.getnext()
        first = True
        while sib is not None and sib.tag == "dd":
            if first:
                authors = [clean_text(x).strip("* ") for x in sib.text_content().split(",") if clean_text(x).strip("* ")]
                first = False
            for x in sib.xpath(".//a[@href]"):
                label = clean_text(x.text_content()).lower()
                if label == "pdf":
                    pdf = urljoin(BASE, x.get("href"))
                elif label == "doi":
                    doi = x.get("href")
            sib = sib.getnext()
        if doi:
            m = re.search(r"(10\.\d{4,9}/\S+)", doi)
            doi = m.group(1) if m else None
        out.append({"title": title, "href": href, "authors": authors, "pdf": pdf, "doi": doi})
    return out


def parse_paper(page: str) -> str:
    doc = lxml_html.fromstring(page)
    ab = doc.xpath('//div[@id="abstract"]')
    return clean_text(ab[0].text_content()).strip('"').strip() if ab else ""


class ECVAAdapter:
    name = "ecva"
    page_batch = 20

    def source_id(self, src: dict) -> str:
        return f"ecva:{src['year']}"

    def crawl(self, src: dict, ctx: CrawlContext) -> Iterator[Batch]:
        year = src["year"]
        state = dict(ctx.cursor or {})
        r = ctx.fetcher.get(f"{BASE}papers.php", max_age=3 * 86400 if state.get("listed") else None)
        entries = parse_index(r.text, year)
        if not entries:
            ensure("ECCV" in r.text, "ECVA papers.php changed (no ECCV sections)")
            yield Batch([], {}, note=f"ECCV {year}: not on ECVA yet")
            return
        ensure(len(entries) >= 100, f"ECCV {year}: only {len(entries)} entries")

        def record(e: dict, abstract: str | None = None) -> PaperRecord:
            key = e["href"].rsplit("/", 1)[-1].removesuffix(".php")
            return PaperRecord(source="ecva", source_key=key, title=e["title"], authors=e["authors"], abstract=abstract,
                               proceedings_url=e["href"], pdf_url=e["pdf"], doi=e["doi"], status="accepted")

        if not state.get("listed"):
            for part in chunks(entries, 400):
                yield Batch([record(e) for e in part], {"listed": False}, phase="published")
            state = {"listed": True, "idx": 0}
            yield Batch([], dict(state), phase="published", note=f"ECCV {year}: {len(entries)} papers listed")
        pending: list[PaperRecord] = []
        misses = 0
        next_idx = state.get("idx", 0)
        for i in range(state.get("idx", 0), len(entries)):
            if ctx.stopped():
                break
            next_idx = i + 1
            e = entries[i]
            if ctx.has_abstract(norm_title(e["title"])):
                continue
            p = ctx.fetcher.get(e["href"], accept=(200, 404))
            if p.status == 404:
                continue
            abstract = parse_paper(p.text)
            if not abstract:
                misses += 1
                ensure(misses < 20, f"ECCV {year}: abstracts missing on paper pages")
            pending.append(record(e, abstract or None))
            if len(pending) >= self.page_batch:
                yield Batch(pending, {"listed": True, "idx": i + 1}, phase="published",
                            note=f"ECCV {year}: abstracts {i + 1}/{len(entries)}")
                pending = []
        if ctx.stopped():
            # Interrupted: keep the real position so the next run resumes instead of skipping the rest.
            yield Batch(pending, {"listed": True, "idx": max(0, next_idx - 1)}, phase="published", note="stopped")
            return
        yield Batch(pending, {"listed": True, "idx": len(entries)}, phase="published", note=f"ECCV {year}: done")
