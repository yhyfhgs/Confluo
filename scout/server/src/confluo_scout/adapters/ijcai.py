"""IJCAI proceedings.

Facts checked 2026-11-19: `/proceedings/{year}/` lists a whole edition (2025: 1,280 papers) as
`div.section` (track, e.g. "Main Track") > `div.subsection` (area) > `div.paper_wrapper`. Every paper
URL also answers with `.json` (title, authors, abstract, DOI, section, track, keywords), as
`/llms.txt` announces; the HTML detail page is the fallback. robots.txt now only disallows
/wp-admin/ ("AI agents and crawlers are welcome"); the Crawl-delay of 10 recorded on 2026-09-30 is
gone. Scout keeps a 2 s interval.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from urllib.parse import urljoin

from lxml import html as lxml_html

from confluo_scout.adapters.base import Batch, CrawlContext, chunks, ensure
from confluo_scout.records import PaperRecord, clean_text, norm_title

BASE = "https://www.ijcai.org"


def parse_year(page: str, year: int) -> list[dict]:
    doc = lxml_html.fromstring(page)
    out = []
    for wrap in doc.xpath('//div[contains(@class, "paper_wrapper")]'):
        a = wrap.xpath('.//a[contains(@class, "title")]')
        if not a:
            continue
        href = urljoin(BASE, a[0].get("href"))
        title = clean_text(a[0].text_content())
        authors = [clean_text(x.text_content()) for x in wrap.xpath('.//div[contains(@class, "authors")]//a')]
        if not authors:
            raw = wrap.xpath('.//div[contains(@class, "authors")]')
            authors = [clean_text(x) for x in raw[0].text_content().split(",")] if raw else []
        doi = None
        for link in wrap.xpath(".//a[@href]"):
            m = re.search(r"(10\.24963/\S+)", link.get("href"))
            if m:
                doi = m.group(1)
        pdf = next((urljoin(BASE, h) for h in wrap.xpath(".//a/@href") if h.endswith(".pdf")), None)
        sec = wrap.xpath('./ancestor::div[contains(concat(" ", normalize-space(@class), " "), " section ")][1]'
                         '/div[contains(concat(" ", normalize-space(@class), " "), " section_title ")]')
        sub = wrap.xpath('./ancestor::div[contains(concat(" ", normalize-space(@class), " "), " subsection ")][1]'
                         '/div[contains(concat(" ", normalize-space(@class), " "), " subsection_title ")]')
        out.append({"title": title, "href": href, "authors": [x for x in authors if x], "doi": doi, "pdf": pdf,
                    "track": clean_text(sec[0].text_content()) if sec else None,
                    "area": clean_text(sub[0].text_content()) if sub else None})
    return out


def parse_detail_json(raw: bytes) -> dict:
    d = json.loads(raw)
    kws = [clean_text(k) for k in d.get("keywords") or [] if isinstance(k, str)]
    return {"abstract": clean_text(d.get("abstract") or ""), "keywords": [k for k in kws if k],
            "area": clean_text(d.get("section") or "") or None, "track": clean_text(d.get("track") or "") or None}


def parse_detail(page: str) -> dict:
    doc = lxml_html.fromstring(page)
    ab = doc.xpath('//div[contains(@class, "article__abstract")]//p[not(contains(@class, "eyebrow"))]')
    abstract = clean_text(" ".join(p.text_content() for p in ab))
    kws = [clean_text(li.text_content()) for li in doc.xpath('//div[contains(@class, "article__keywords")]//li')]
    return {"abstract": abstract, "keywords": [k for k in kws if k]}


class IJCAIAdapter:
    name = "ijcai"
    page_batch = 10

    def source_id(self, src: dict) -> str:
        return f"ijcai:{src['year']}"

    def crawl(self, src: dict, ctx: CrawlContext) -> Iterator[Batch]:
        year = src["year"]
        state = dict(ctx.cursor or {})
        r = ctx.fetcher.get(f"{BASE}/proceedings/{year}/", accept=(200, 404),
                            max_age=7 * 86400 if state.get("listed") else None)
        if r.status == 404:
            yield Batch([], {}, note=f"IJCAI {year}: proceedings not online yet")
            return
        entries = [e for e in parse_year(r.text, year) if e["track"] not in ("Doctoral Consortium",)]
        ensure(len(entries) >= 100, f"IJCAI {year}: only {len(entries)} papers on the year page")

        def record(e: dict, abstract: str | None = None, keywords: list[str] | None = None) -> PaperRecord:
            key = e["href"].rstrip("/").rsplit("/", 1)[-1]
            return PaperRecord(source="ijcai", source_key=key, title=e["title"], authors=e["authors"],
                               abstract=abstract, keywords=keywords or [], area=e["area"], track=e["track"],
                               proceedings_url=e["href"], pdf_url=e["pdf"], doi=e["doi"], status="accepted",
                               decision_label="Main" if e["track"] == "Main Track" else None,
                               tier=2 if e["track"] == "Main Track" else (1 if e["track"] else None))

        if not state.get("listed"):
            for part in chunks(entries, 400):
                yield Batch([record(e) for e in part], {"listed": False}, phase="published")
            state = {"listed": True, "idx": 0}
            yield Batch([], dict(state), phase="published", note=f"IJCAI {year}: {len(entries)} papers listed")
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
            p = ctx.fetcher.get(e["href"].rstrip("/") + ".json", accept=(200, 404))
            try:
                info = parse_detail_json(p.content) if p.status == 200 else None
            except ValueError:
                info = None
            if info is None:
                p = ctx.fetcher.get(e["href"], accept=(200, 404))
                if p.status == 404:
                    continue
                info = parse_detail(p.text)
            if info.get("area") and not e["area"]:
                e = dict(e, area=info["area"])
            if not info["abstract"]:
                misses += 1
                ensure(misses < 15, f"IJCAI {year}: abstracts missing on detail pages")
            area = e["area"]
            if not area and info["keywords"]:
                area = info["keywords"][0].split(":")[0].strip() or None
            pending.append(record(dict(e, area=area), info["abstract"] or None, info["keywords"]))
            if len(pending) >= self.page_batch:
                yield Batch(pending, {"listed": True, "idx": i + 1}, phase="published",
                            note=f"IJCAI {year}: abstracts {i + 1}/{len(entries)}")
                pending = []
        if ctx.stopped():
            # Interrupted: keep the real position so the next run resumes instead of skipping the rest.
            yield Batch(pending, {"listed": True, "idx": max(0, next_idx - 1)}, phase="published", note="stopped")
            return
        yield Batch(pending, {"listed": True, "idx": len(entries)}, phase="published", note=f"IJCAI {year}: done")
