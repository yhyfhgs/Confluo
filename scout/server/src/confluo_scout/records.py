"""Records exchanged between adapters and the store, plus small text helpers."""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from dataclasses import dataclass, field

# Decision tiers used for ranking: higher is a stronger presentation slot.
TIER_ORAL = 4
TIER_SPOTLIGHT = 3   # spotlight, highlight
TIER_POSTER = 2      # poster, regular, accepted without a slot
TIER_FINDINGS = 1    # findings, workshop-like tracks

STATUS_ACCEPTED = "accepted"
STATUS_UNDER_REVIEW = "under_review"
STATUS_REJECTED = "rejected"
STATUS_WITHDRAWN = "withdrawn"
STATUS_DESK_REJECTED = "desk_rejected"
VISIBLE_STATUSES = (STATUS_ACCEPTED, STATUS_UNDER_REVIEW)


@dataclass
class ReviewRecord:
    key: str
    rating: float | None
    rating_raw: str | None
    confidence: float | None
    subscores: dict[str, float] = field(default_factory=dict)
    updated_at: str | None = None


@dataclass
class PaperRecord:
    """One paper as one source sees it. `None` means "this source does not say"."""

    source: str
    source_key: str
    title: str
    authors: list[str] = field(default_factory=list)
    abstract: str | None = None
    keywords: list[str] = field(default_factory=list)
    area: str | None = None
    area_secondary: str | None = None
    tldr: str | None = None
    status: str | None = None
    decision_label: str | None = None
    tier: int | None = None
    track: str | None = None
    forum_url: str | None = None
    pdf_url: str | None = None
    proceedings_url: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    reviews: list[ReviewRecord] | None = None
    label_only: bool = False  # only carries a decision label for an existing paper (matched by title)


_WS = re.compile(r"\s+")
_TAGS = re.compile(r"<[^>]+>")


def clean_text(raw: str | None) -> str:
    if not raw:
        return ""
    text = html.unescape(_TAGS.sub(" ", raw))
    text = unicodedata.normalize("NFC", text)
    return _WS.sub(" ", text).strip()


_HYPHEN_BREAK = re.compile(r"(?<=[a-z])- (?=[a-z])")


def dehyphenate(text: str) -> str:
    """Join words split by PDF line breaks ('im- age' -> 'image')."""
    return _HYPHEN_BREAK.sub("", text)


def norm_title(title: str) -> str:
    """Lowercase ASCII-folded letters and digits only: the cross-source matching key."""
    t = unicodedata.normalize("NFKD", clean_text(title)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", t.lower())


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


_NUM = re.compile(r"^\s*(-?\d+(?:\.\d+)?)")


def parse_score(value: object) -> tuple[float | None, str | None]:
    """Review scores arrive as numbers or as strings like '6: marginally above the threshold'."""
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, str(value)
    if isinstance(value, (int, float)):
        return float(value), str(value)
    if isinstance(value, dict) and "value" in value:
        return parse_score(value["value"])
    text = str(value).strip()
    m = _NUM.match(text)
    return (float(m.group(1)) if m else None), text[:200]


_LABEL_RULES: list[tuple[re.Pattern, str, int]] = [
    (re.compile(r"\boral\b", re.I), "Oral", TIER_ORAL),
    (re.compile(r"\bspotlight", re.I), "Spotlight", TIER_SPOTLIGHT),
    (re.compile(r"\bhighlight", re.I), "Highlight", TIER_SPOTLIGHT),
    (re.compile(r"\bposter\b", re.I), "Poster", TIER_POSTER),
    (re.compile(r"\bregular\b", re.I), "Poster", TIER_POSTER),
    (re.compile(r"\bfindings\b", re.I), "Findings", TIER_FINDINGS),
]


def label_from_text(text: str | None) -> tuple[str | None, int | None]:
    """Map a venue string or decision ('ICLR 2026 Oral', 'Accept (spotlight)') to (label, tier)."""
    if not text:
        return None, None
    for pat, label, tier in _LABEL_RULES:
        if pat.search(text):
            return label, tier
    if re.search(r"\baccept", text, re.I):
        return "Accepted", TIER_POSTER
    return None, None


def split_authors_bibtex(raw: str) -> list[str]:
    """'Last, First and Other, Name' -> ['First Last', 'Name Other']."""
    out = []
    for part in re.split(r"\s+and\s+", clean_text(raw)):
        part = part.strip()
        if not part:
            continue
        if "," in part:
            last, first = part.split(",", 1)
            out.append(f"{first.strip()} {last.strip()}".strip())
        else:
            out.append(part)
    return out


_ARXIV = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", re.I)


def arxiv_from_url(url: str | None) -> str | None:
    if not url:
        return None
    m = _ARXIV.search(url)
    return m.group(1) if m else None
