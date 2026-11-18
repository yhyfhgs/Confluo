"""CVF Open Access (CVPR, ICCV, WACV) and the conference sites' accepted-paper lists.

Facts checked 2026-11-19: openaccess.thecvf.com has no robots.txt (404); `/{CONF}{year}?day=all`
lists a whole edition on one page (CVPR 2025: 2,871 papers, 8.4 MB); paper pages carry the
abstract in `<div id="abstract">`. `{cvpr,iccv}.thecvf.com/Conferences/{year}/AcceptedPapers` is
allowed by robots and marks highlights with `<img title="Highlight">` (CVPR 2025: 388); orals are
not marked there. CVPR 2026's page answers 404.
"""

from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import urljoin

from lxml import html as lxml_html

from confluo_scout.adapters.base import Batch, CrawlContext, chunks, ensure
from confluo_scout.records import (
    TIER_POSTER,
    TIER_SPOTLIGHT,
    PaperRecord,
    arxiv_from_url,
    clean_text,
    dehyphenate,
    norm_title,
)

BASE = "https://openaccess.thecvf.com"


def parse_list(page: str, base: str = BASE) -> list[dict]:
    doc = lxml_html.fromstring(page)
    out = []
    for dt in doc.xpath('//dt[contains(@class, "ptitle")]'):
        a = dt.xpath(".//a[@href]")
        if not a:
            continue
        href = a[0].get("href")
        title = clean_text(a[0].text_content())
        authors: list[str] = []
        links: list[tuple[str, str]] = []
        sib = dt.getnext()
        while sib is not None and sib.tag == "dd":
            authors += [clean_text(i.get("value")) for i in sib.xpath('.//input[@name="query_author"]') if i.get("value")]
            links += [(clean_text(x.text_content()).lower(), x.get("href")) for x in sib.xpath(".//a[@href]")]
            sib = sib.getnext()
        pdf = next((urljoin(base, h) for t, h in links if h.endswith(".pdf") and "supplemental" not in h and t == "pdf"),
                   None)
        arxiv = next((h for t, h in links if "arxiv" in t or "arxiv.org" in h), None)
        out.append({"title": title, "href": urljoin(base, href), "authors": authors, "pdf": pdf, "arxiv": arxiv})
    return out


def parse_paper_page(page: str) -> dict:
    doc = lxml_html.fromstring(page)
    ab = doc.xpath('//div[@id="abstract"]')
    abstract = dehyphenate(clean_text(ab[0].text_content())) if ab else ""
    pdf = doc.xpath('//meta[@name="citation_pdf_url"]/@content')
    return {"abstract": abstract, "pdf": pdf[0] if pdf else None}


def _key(href: str) -> str:
    return href.rsplit("/", 1)[-1].removesuffix(".html")


class CVFAdapter:
    name = "cvf"
    page_batch = 20

    def source_id(self, src: dict) -> str:
        return f"cvf:{src['conf']}{src['year']}"

    def crawl(self, src: dict, ctx: CrawlContext) -> Iterator[Batch]:
        conf, year = src["conf"], src["year"]
        state = dict(ctx.cursor or {})
        listed = state.get("listed", False)
        r = ctx.fetcher.get(f"{BASE}/{conf}{year}", params={"day": "all"}, max_age=3 * 86400 if listed else None,
                            accept=(200, 404))
        if r.status == 404:
            yield Batch([], {"listed": False}, note=f"{conf}{year}: not on CVF Open Access yet")
            return
        entries = parse_list(r.text)
        ensure(len(entries) >= int(src.get("min_entries", 50)), f"CVF {conf}{year}: only {len(entries)} entries on the list page")
        ensure(sum(1 for e in entries if e["authors"]) >= 0.9 * len(entries), "CVF list: authors missing")

        def record(e: dict, abstract: str | None = None, pdf: str | None = None) -> PaperRecord:
            return PaperRecord(source="cvf", source_key=_key(e["href"]), title=e["title"], authors=e["authors"],
                               abstract=abstract, proceedings_url=e["href"], pdf_url=pdf or e["pdf"],
                               arxiv_id=arxiv_from_url(e["arxiv"]), status="accepted")

        if not listed:
            for part in chunks(entries, 400):
                yield Batch([record(e) for e in part], {"listed": False}, phase="published",
                            note=f"{conf}{year}: listed {len(part)}")
            state = {"listed": True, "idx": 0}
            yield Batch([], dict(state), phase="published", note=f"{conf}{year}: {len(entries)} papers listed")
        idx = state.get("idx", 0)
        pending: list[PaperRecord] = []
        misses = 0
        next_idx = idx
        for i in range(idx, len(entries)):
            if ctx.stopped():
                break
            next_idx = i + 1
            e = entries[i]
            if ctx.has_abstract(norm_title(e["title"])):
                continue
            p = ctx.fetcher.get(e["href"], accept=(200, 404))
            if p.status == 404:
                continue
            info = parse_paper_page(p.text)
            if not info["abstract"]:
                misses += 1
                ensure(misses < 20, f"CVF {conf}{year}: abstracts missing on paper pages (structure drift?)")
            pending.append(record(e, info["abstract"] or None, info["pdf"]))
            if len(pending) >= self.page_batch:
                yield Batch(pending, {"listed": True, "idx": i + 1}, phase="published",
                            note=f"{conf}{year}: abstracts {i + 1}/{len(entries)}")
                pending = []
        if ctx.stopped():
            # Interrupted: keep the real position so the next run resumes instead of skipping the rest.
            yield Batch(pending, {"listed": True, "idx": max(0, next_idx - 1)}, phase="published", note="stopped")
            return
        yield Batch(pending, {"listed": True, "idx": len(entries)}, phase="published",
                    note=f"{conf}{year}: abstracts done")


class CVFAcceptedAdapter:
    """Decision labels (Highlight vs Poster) from the conference site's accepted-paper list."""

    name = "cvf_accepted"

    def source_id(self, src: dict) -> str:
        return f"cvf_accepted:{src['host']}:{src['year']}"

    def crawl(self, src: dict, ctx: CrawlContext) -> Iterator[Batch]:
        url = f"https://{src['host']}/Conferences/{src['year']}/AcceptedPapers"
        r = ctx.fetcher.get(url, max_age=86400, accept=(200, 404))
        if r.status == 404:
            yield Batch([], {}, note=f"{url}: 404")
            return
        rows = parse_accepted(r.text)
        ensure(len(rows) >= 50, f"{url}: only {len(rows)} rows")
        recs = [PaperRecord(source="cvf_accepted", source_key=norm_title(t), title=t, decision_label=lab, tier=tier,
                            label_only=True) for t, lab, tier in rows]
        for part in chunks(recs, 500):
            yield Batch(part, {}, note=f"{src['host']} {src['year']}: labels")


def parse_accepted(page: str) -> list[tuple[str, str, int]]:
    doc = lxml_html.fromstring(page)
    out = []
    for tr in doc.xpath("//tr"):
        strong = tr.xpath(".//strong")
        if not strong:
            continue
        title = clean_text(strong[0].text_content())
        if not title:
            continue
        marks = {m.lower() for m in tr.xpath(".//img/@title")}
        if "oral" in marks:
            out.append((title, "Oral", 4))
        elif "highlight" in marks:
            out.append((title, "Highlight", TIER_SPOTLIGHT))
        else:
            out.append((title, "Poster", TIER_POSTER))
    return out
