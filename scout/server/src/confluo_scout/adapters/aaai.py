"""AAAI proceedings via the OJS OAI-PMH endpoint.

Facts checked 2026-11-19: `ojs.aaai.org/index.php/AAAI/oai` answers ListRecords in pages of 100
oai_dc records; `dc:source` reads "Proceedings of the AAAI Conference on Artificial Intelligence;
Vol. 40 No. 1: AAAI-26 Technical Tracks 1; 3-11"; `dc:description` holds the abstract; sets are
technical-track sections. robots.txt only disallows /cache/. OAI `from` filters by last
modification, so a harvest from January of the edition year sees every paper of that edition
plus later-modified older ones, which are filtered out by volume.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import date, timedelta

from lxml import etree

from confluo_scout.adapters.base import Batch, CrawlContext, ensure
from confluo_scout.fetch import ChallengeError, CircuitOpen, FetchError, RobotsDenied
from confluo_scout.records import PaperRecord, clean_text

OAI = "https://ojs.aaai.org/index.php/AAAI/oai"
NS = {"oai": "http://www.openarchives.org/OAI/2.0/", "dc": "http://purl.org/dc/elements/1.1/",
      "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/"}
_NON_PAPER = re.compile(r"^(front matter|preface|table of contents|index|author index|organizing committee)",
                        re.I)


def section_area(set_name: str) -> str | None:
    name = clean_text(set_name)
    name = re.sub(r"^AAAI (Technical Track|Special Track)( on|:)?\s*", "", name, flags=re.I)
    name = re.sub(r"\s+(I|II|III|IV|V|VI|VII|VIII|IX|X)$", "", name)
    return name or None


def parse_sets(xml: bytes) -> dict[str, str]:
    root = etree.fromstring(xml)
    return {s.findtext("oai:setSpec", namespaces=NS): s.findtext("oai:setName", namespaces=NS) or ""
            for s in root.iterfind(".//oai:set", NS)}


def parse_records(xml: bytes, volume: int, sets: dict[str, str]) -> tuple[list[PaperRecord], str | None, str | None]:
    root = etree.fromstring(xml)
    err = root.find("oai:error", NS)
    if err is not None:
        return [], None, err.get("code")
    out = []
    for rec in root.iterfind(".//oai:record", NS):
        header = rec.find("oai:header", NS)
        if header is None or header.get("status") == "deleted":
            continue
        md = rec.find(".//oai_dc:dc", NS)
        if md is None:
            continue
        sources = [clean_text(x.text) for x in md.iterfind("dc:source", NS) if x.text]
        if not any(re.search(rf"\bVol\.\s*{volume}\b", s) for s in sources):
            continue
        title = clean_text(md.findtext("dc:title", namespaces=NS))
        if not title or _NON_PAPER.match(title):
            continue
        creators = []
        for c in md.iterfind("dc:creator", NS):
            name = clean_text(c.text)
            if "," in name:
                last, first = name.split(",", 1)
                name = f"{first.strip()} {last.strip()}".strip()
            if name:
                creators.append(name)
        idents = [clean_text(x.text) for x in md.iterfind("dc:identifier", NS) if x.text]
        url = next((i for i in idents if i.startswith("http")), None)
        doi = next((i for i in idents if i.startswith("10.")), None)
        rel = [clean_text(x.text) for x in md.iterfind("dc:relation", NS) if x.text]
        set_spec = header.findtext("oai:setSpec", namespaces=NS) or ""
        status = "withdrawn" if title.upper().startswith("RETRACTED") else "accepted"
        out.append(PaperRecord(
            source="aaai", source_key=(url or title).rsplit("/", 1)[-1], title=title, authors=creators,
            abstract=clean_text(md.findtext("dc:description", namespaces=NS)) or None,
            keywords=[clean_text(x.text) for x in md.iterfind("dc:subject", NS) if x.text],
            area=section_area(sets.get(set_spec, "")), status=status,
            proceedings_url=url, pdf_url=rel[0] if rel else None, doi=doi,
        ))
    token_el = root.find(".//oai:resumptionToken", NS)
    token = token_el.text.strip() if token_el is not None and token_el.text else None
    return out, token, None


def month_windows(year: int, today: date | None = None) -> list[list[str]]:
    """Monthly [from, until] windows from January of the edition year up to today."""
    today = today or date.today()
    out, cur = [], date(year, 1, 1)
    while cur <= today:
        nxt = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
        out.append([cur.isoformat(), (nxt - timedelta(days=1)).isoformat()])
        cur = nxt
    return out


def _split(window: list[str]) -> list[list[str]] | None:
    a, b = date.fromisoformat(window[0]), date.fromisoformat(window[1])
    if a >= b:
        return None
    mid = a + (b - a) // 2
    return [[a.isoformat(), mid.isoformat()], [(mid + timedelta(days=1)).isoformat(), b.isoformat()]]


class AAAIAdapter:
    name = "aaai"

    def source_id(self, src: dict) -> str:
        return f"aaai:{src['year']}"

    def crawl(self, src: dict, ctx: CrawlContext) -> Iterator[Batch]:
        year = src["year"]
        volume = year - int(src.get("volume_offset", 1986))
        sets_resp = ctx.fetcher.get(OAI, params={"verb": "ListSets"}, max_age=7 * 86400)
        sets = parse_sets(sets_resp.content)
        state = dict(ctx.cursor or {})
        windows = state.get("windows") or month_windows(year)
        token = state.get("token")
        seen = state.get("seen", 0)
        skipped = state.get("skipped", 0)
        pages = 0

        def snapshot() -> dict:
            return {"windows": windows, "token": token, "seen": seen, "skipped": skipped}

        while windows and not ctx.stopped():
            w = windows[0]
            if token:
                params = {"verb": "ListRecords", "resumptionToken": token}
            else:
                params = {"verb": "ListRecords", "metadataPrefix": "oai_dc", "set": "AAAI", "from": w[0], "until": w[1]}
            try:
                r = ctx.fetcher.get(OAI, params=params, use_cache=False)
            except (CircuitOpen, ChallengeError, RobotsDenied):
                raise  # stop this run; the saved cursor resumes it later
            except FetchError as exc:
                if exc.status is not None and exc.status < 500:
                    raise
                halves = _split(w)
                ctx.log.warning("AAAI %s: window %s..%s failed (%s); %s", year, w[0], w[1], exc,
                                "splitting" if halves else "falling back to single records")
                token = None
                if halves:
                    windows = halves + windows[1:]
                    yield Batch([], snapshot(), note=f"AAAI-{str(year)[2:]}: split {w[0]}..{w[1]}")
                    continue
                recs, lost = yield_from_identifiers(ctx, w[0], volume, sets)
                skipped += lost
                seen += len(recs)
                windows = windows[1:]
                yield Batch(recs, snapshot(), phase="published",
                            note=f"AAAI-{str(year)[2:]}: {w[0]} record by record ({lost} unreadable)")
                continue
            records, next_token, error = parse_records(r.content, volume, sets)
            if error == "badResumptionToken":
                ctx.log.warning("AAAI %s: resumption token expired; restarting window %s", year, w)
                token = None
                continue
            if error == "noRecordsMatch":
                windows, token = windows[1:], None
                yield Batch([], snapshot(), note=f"AAAI-{str(year)[2:]}: {w[0]} empty")
                continue
            ensure(error is None, f"AAAI OAI error {error}")
            pages += 1
            seen += len(records)
            if next_token:
                token = next_token
            else:
                windows, token = windows[1:], None
            yield Batch(records, snapshot(), phase="published", note=f"AAAI-{str(year)[2:]}: {w[0]} page {pages}")
        if not ctx.stopped():
            ensure(seen > 0 or year >= 2027, f"AAAI {year}: no papers of volume {volume} found")


def yield_from_identifiers(ctx: CrawlContext, day: str, volume: int, sets: dict[str, str]) -> tuple[list[PaperRecord], int]:
    """Last resort for a day whose ListRecords pages fail: list identifiers, then GetRecord one by one."""
    ids: list[str] = []
    token = None
    while True:
        params = ({"verb": "ListIdentifiers", "resumptionToken": token} if token else
                  {"verb": "ListIdentifiers", "metadataPrefix": "oai_dc", "set": "AAAI", "from": day, "until": day})
        try:
            r = ctx.fetcher.get(OAI, params=params, use_cache=False)
        except (CircuitOpen, ChallengeError, RobotsDenied):
            raise
        except FetchError:
            break
        root = etree.fromstring(r.content)
        ids += [h.findtext("oai:identifier", namespaces=NS) for h in root.iterfind(".//oai:header", NS)
                if h.get("status") != "deleted"]
        tok = root.find(".//oai:resumptionToken", NS)
        token = tok.text.strip() if tok is not None and tok.text else None
        if not token:
            break
    out, lost = [], 0
    for ident in ids:
        if ctx.stopped():
            break
        try:
            r = ctx.fetcher.get(OAI, params={"verb": "GetRecord", "identifier": ident, "metadataPrefix": "oai_dc"},
                                use_cache=False)
        except (CircuitOpen, ChallengeError, RobotsDenied):
            raise
        except FetchError:
            lost += 1
            continue
        recs, _tok, _err = parse_records(r.content, volume, sets)
        out += recs
    return out, lost
