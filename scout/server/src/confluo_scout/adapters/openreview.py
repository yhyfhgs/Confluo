"""OpenReview adapter (API v2, with API v1 for editions up to 2023).

Facts checked 2026-11-19: anonymous `/notes` answers 403 ChallengeRequiredError; a logged-in
account gets `ratelimit-policy: 500;w=3600`; `details=replies` pages of 100 notes weigh about
7 MB; responses carry no `count`, so paging stops at a short page. Scout logs in with the
user's own account (token sent as `Authorization: Bearer`), never touches `/profiles*`,
`challengeUrl` or the `email` parameter, and keeps the token in memory only.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Iterator
from datetime import UTC, datetime

from confluo_scout.adapters.base import AuthError, Batch, CrawlContext, ensure
from confluo_scout.config import Secrets
from confluo_scout.fetch import Fetcher, FetchError
from confluo_scout.records import (
    STATUS_ACCEPTED,
    STATUS_DESK_REJECTED,
    STATUS_REJECTED,
    STATUS_UNDER_REVIEW,
    STATUS_WITHDRAWN,
    PaperRecord,
    ReviewRecord,
    clean_text,
    label_from_text,
    parse_score,
)

API2 = "https://api2.openreview.net"
API1 = "https://api.openreview.net"
SITE = "https://openreview.net"

RATING_KEYS = ("rating", "overall_recommendation", "recommendation", "overall_assessment", "overall_score",
               "final_rating", "score", "preliminary_rating")
SUBSCORE_KEYS = {"soundness", "presentation", "contribution", "quality", "clarity", "significance", "originality",
                 "informativeness", "novelty", "technical_quality", "impact", "reproducibility", "correctness",
                 "technical_novelty_and_significance", "empirical_novelty_and_significance", "excitement",
                 "reproducibility_score", "relevance"}
_SCORE_TEXT = re.compile(r"^\s*-?\d+(?:\.\d+)?\s*(?::|$)")
_NOT_A_SCORE = re.compile(r"flag|ethic|conduct|acknowledg|compliance|policy|limitations|checklist", re.I)


def _ms_to_iso(ms: object) -> str | None:
    if not isinstance(ms, (int, float)):
        return None
    return datetime.fromtimestamp(ms / 1000, tz=UTC).replace(microsecond=0).isoformat()


def _val(content: dict, key: str):
    v = content.get(key)
    if isinstance(v, dict) and "value" in v:
        return v["value"]
    return v


def _invitations(note: dict) -> list[str]:
    invs = note.get("invitations")
    if invs:
        return list(invs)
    inv = note.get("invitation")
    return [inv] if inv else []


def status_from_venueid(venueid: str, groups: set[str]) -> str:
    if venueid in groups:
        return STATUS_ACCEPTED
    tail = venueid.rsplit("/", 1)[-1]
    if tail == "Withdrawn_Submission":
        return STATUS_WITHDRAWN
    if tail == "Desk_Rejected_Submission":
        return STATUS_DESK_REJECTED
    if tail == "Rejected_Submission":
        return STATUS_REJECTED
    if tail in ("Submission", "Blind_Submission"):
        return STATUS_UNDER_REVIEW
    return STATUS_UNDER_REVIEW


def parse_review(reply: dict) -> ReviewRecord | None:
    content = reply.get("content") or {}
    rating, rating_raw = None, None
    for key in RATING_KEYS:
        if key in content:
            rating, rating_raw = parse_score(_val(content, key))
            if rating is not None:
                break
    confidence, _ = parse_score(_val(content, "confidence")) if "confidence" in content else (None, None)
    subs: dict[str, float] = {}
    for key in content:
        if key in RATING_KEYS or key == "confidence" or _NOT_A_SCORE.search(key):
            continue
        raw = _val(content, key)
        if key in SUBSCORE_KEYS or isinstance(raw, (int, float)) or (isinstance(raw, str) and len(raw) < 120
                                                                    and _SCORE_TEXT.match(raw)):
            num, _ = parse_score(raw)
            if num is not None and not isinstance(raw, bool):
                subs[key] = num
    if rating is None and confidence is None and not subs:
        return None
    return ReviewRecord(key=reply.get("id", ""), rating=rating, rating_raw=rating_raw, confidence=confidence,
                        subscores=subs, updated_at=_ms_to_iso(reply.get("tmdate") or reply.get("mdate")))


def parse_note(note: dict, *, groups: set[str], track: str | None, api: str = "v2") -> PaperRecord:
    c = note.get("content") or {}
    forum = note.get("forum") or note.get("id")
    venue = clean_text(str(_val(c, "venue") or ""))
    venueid = str(_val(c, "venueid") or "")
    if api == "v1" and not venueid:
        status = STATUS_UNDER_REVIEW if venue.lower().startswith("submitted to") or not venue else STATUS_ACCEPTED
    else:
        status = status_from_venueid(venueid, groups)
    label, tier = label_from_text(venue) if status == STATUS_ACCEPTED else (None, None)
    details = note.get("details") or {}
    # An empty list means "asked for replies, none are public" and must clear stale reviews.
    replies = details["replies"] if "replies" in details else details.get("directReplies")
    reviews = None
    decision_text = None
    if replies is not None:
        reviews = []
        for r in replies:
            invs = _invitations(r)
            if any(i.endswith("/-/Official_Review") or i.endswith("/Official_Review") for i in invs):
                rv = parse_review(r)
                if rv:
                    reviews.append(rv)
            elif any(i.endswith("/-/Decision") or i.endswith("/Decision") for i in invs):
                decision_text = str(_val(r.get("content") or {}, "decision") or "")
    if status == STATUS_ACCEPTED and label is None:
        label, tier = label_from_text(decision_text)
        if label is None:
            label, tier = "Accepted", 2
    pdf = _val(c, "pdf")
    keywords = _val(c, "keywords") or []
    if isinstance(keywords, str):
        keywords = [k.strip() for k in re.split(r"[;,]", keywords) if k.strip()]
    authors = _val(c, "authors") or []
    if isinstance(authors, str):
        authors = [a.strip() for a in authors.split(",") if a.strip()]
    return PaperRecord(
        source="openreview",
        source_key=str(forum),
        title=clean_text(str(_val(c, "title") or "")),
        authors=[clean_text(str(a)) for a in authors],
        abstract=clean_text(str(_val(c, "abstract") or "")) or None,
        keywords=[clean_text(str(k)) for k in keywords if str(k).strip()],
        area=clean_text(str(_val(c, "primary_area") or "")) or None,
        area_secondary=clean_text(str(_val(c, "secondary_area") or "")) or None,
        tldr=clean_text(str(_val(c, "TLDR") or _val(c, "TL;DR") or "")) or None,
        status=status,
        decision_label=label,
        tier=tier,
        track=track,
        forum_url=f"{SITE}/forum?id={forum}",
        pdf_url=f"{SITE}/pdf?id={forum}" if pdf else None,
        reviews=reviews,
    )


class OpenReviewAdapter:
    name = "openreview"

    def __init__(self, secrets: Secrets):
        self._secrets = secrets
        self._token: str | None = None
        self._lock = threading.Lock()

    def source_id(self, src: dict) -> str:
        return f"openreview:{src['group']}"

    # ---- auth -------------------------------------------------------------------------------

    def _login(self, fetcher: Fetcher, force: bool = False) -> str:
        with self._lock:
            if self._token and not force:
                return self._token
            if not self._secrets.has_openreview:
                raise AuthError("OpenReview credentials missing ([auth.openreview] in .confluo/config.toml)")
            r = fetcher.post_json(f"{API2}/login", {"id": self._secrets.openreview_username,
                                                     "password": self._secrets.openreview_password},
                                  accept=(200, 400, 401, 403))
            if r.status != 200:
                raise AuthError(f"OpenReview login rejected (HTTP {r.status})")
            token = (r.json() or {}).get("token")
            if not token:
                raise AuthError("OpenReview login returned no token")
            self._token = token
            return token

    def _notes(self, fetcher: Fetcher, base: str, params: dict) -> list[dict]:
        for attempt in range(2):
            token = self._login(fetcher, force=attempt > 0)
            r = fetcher.get(f"{base}/notes", params=params, headers={"Authorization": f"Bearer {token}"},
                            use_cache=False, accept=(200, 401))
            if r.status == 401:
                continue
            data = r.json()
            ensure(isinstance(data, dict) and isinstance(data.get("notes"), list), "OpenReview /notes without notes")
            return data["notes"]
        raise AuthError("OpenReview token rejected twice")

    # ---- crawl ------------------------------------------------------------------------------

    def crawl(self, src: dict, ctx: CrawlContext) -> Iterator[Batch]:
        api = src.get("api", "v2")
        base = API1 if api == "v1" else API2
        groups = [{"group": src["group"], "track": None}, *(src.get("extra_groups") or [])]
        group_ids = {g["group"] for g in groups}
        state = dict(ctx.cursor or {})
        start_idx = state.get("group_idx", 0)
        for gi in range(start_idx, len(groups)):
            g = groups[gi]
            if state.get("group_idx") != gi:
                state = {"group_idx": gi}
            mode = state.get("mode")
            if mode is None:
                mode = self._choose_mode(ctx.fetcher, base, g["group"], api, src.get("scope"))
                state.update({"mode": mode, "offset": 0, "replies": True})
                if mode == "none":
                    ctx.log.info("%s: nothing public yet in %s", ctx.edition_id, g["group"])
                    yield Batch([], dict(state, group_idx=gi + 1, mode=None), note=f"{g['group']}: empty")
                    continue
            phase = "in_review" if mode == "submissions" else "decided"
            while not ctx.stopped():
                with_replies = state.get("replies", True)
                limit = 100 if with_replies else 1000
                params = self._params(api, g["group"], mode, limit, state["offset"], with_replies)
                try:
                    notes = self._notes(ctx.fetcher, base, params)
                except FetchError as exc:
                    if exc.status == 400 and "sort" in params:
                        state["nosort"] = True
                        params.pop("sort", None)
                        notes = self._notes(ctx.fetcher, base, params)
                    else:
                        raise
                records = []
                saw_review = False
                for n in notes:
                    rec = parse_note(n, groups=group_ids, track=g.get("track"), api=api)
                    if rec.reviews:
                        saw_review = True
                    if rec.status in ("withdrawn", "desk_rejected") and mode != "submissions":
                        continue
                    if rec.status == "rejected" and not ctx.include_rejected:
                        continue
                    if not rec.title:
                        continue
                    records.append(rec)
                if notes:
                    titled = sum(1 for n in notes if _val(n.get("content") or {}, "title"))
                    ensure(titled >= 0.9 * len(notes), f"OpenReview: only {titled}/{len(notes)} notes have titles")
                state["offset"] += len(notes)
                done = len(notes) < limit
                # A first page with no public reviews: switch to light pages of 1000 notes.
                if with_replies and state["offset"] == len(notes) and notes and not saw_review and not done:
                    state["replies"] = False
                    state["offset"] = 0
                    yield Batch(records, dict(state), phase=phase, note=f"{g['group']}: reviews not public")
                    continue
                yield Batch(records, dict(state, group_idx=gi + 1, mode=None) if done else dict(state),
                            phase=phase, note=f"{g['group']} offset {state['offset']}")
                if done:
                    break
            if ctx.stopped():
                return
            state = {"group_idx": gi + 1}

    def _params(self, api: str, group: str, mode: str, limit: int, offset: int, replies: bool) -> dict:
        if api == "v1":
            params = {"invitation": f"{group}/-/Blind_Submission", "limit": limit, "offset": offset}
            if replies:
                params["details"] = "directReplies"
            return params
        params = {"limit": limit, "offset": offset, "sort": "number:asc"}
        if mode == "accepted":
            params["content.venueid"] = group
        else:
            params["invitation"] = f"{group}/-/Submission"
        if replies:
            params["details"] = "replies"
        return params

    def _choose_mode(self, fetcher: Fetcher, base: str, group: str, api: str, scope: str | None) -> str:
        if api == "v1":
            return "submissions"
        accepted = self._notes(fetcher, base, {"content.venueid": group, "limit": 1})
        if accepted:
            return "accepted"
        if scope == "accepted":
            return "none"
        subs = self._notes(fetcher, base, {"invitation": f"{group}/-/Submission", "limit": 1})
        return "submissions" if subs else "none"
