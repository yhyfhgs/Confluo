"""Venue registry: series from venues.yaml, editions in SQLite.

The YAML file is the static knowledge; the `edition` table is the runtime state. A sync never
overrides what the user switched on or off. Discovery adds editions that platforms announce
(a new OpenReview group, a new PMLR volume, a new CVF year); a discovered edition starts enabled
when its series is in use and the year is not older than the newest enabled one.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

from confluo_scout.db import Database, dumps, loads, utcnow

log = logging.getLogger("scout.registry")


@dataclass
class SeriesSpec:
    id: str
    short: str
    name: str
    kind: str
    area: str | None
    ratings: list[str]
    homepage: str | None
    years: list[int]
    enabled_years: list[int]
    sources: list[dict]


def load_registry(path: Path) -> list[SeriesSpec]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = []
    for s in data.get("series", []):
        out.append(SeriesSpec(
            id=s["id"], short=s["short"], name=s["name"], kind=s.get("kind", "conference"),
            area=s.get("area"), ratings=list(s.get("ratings") or []), homepage=s.get("homepage"),
            years=sorted(int(y) for y in s.get("years", [])),
            enabled_years=sorted(int(y) for y in s.get("enabled_years", [])),
            sources=list(s.get("sources") or []),
        ))
    return out


def edition_id(series_id: str, year: int) -> str:
    return f"{series_id}-{year}"


def resolve_sources(spec: SeriesSpec, year: int) -> list[dict]:
    """Expand the series' source templates for one year."""
    out = []
    for src in spec.sources:
        years = src.get("years")
        if years and year not in years:
            continue
        cfg = copy.deepcopy({k: v for k, v in src.items() if k != "years"})
        if cfg["adapter"] == "openreview":
            cfg["group"] = cfg["group"].format(year=year)
            extras = []
            for ex in cfg.get("extra_groups", []) or []:
                if ex.get("years") and year not in ex["years"]:
                    continue
                extras.append({"group": ex["group"].format(year=year), "track": ex.get("track")})
            cfg["extra_groups"] = extras
            if year in (cfg.pop("api_v1_years", None) or []):
                cfg["api"] = "v1"
        elif cfg["adapter"] == "pmlr":
            vols = cfg.pop("volumes", {}) or {}
            vol = vols.get(year) or vols.get(str(year))
            if vol:
                cfg["volume"] = int(vol)
        cfg["year"] = year
        out.append(cfg)
    return out


def sync_registry(db: Database, specs: list[SeriesSpec]) -> dict:
    """Upsert series and the editions the YAML lists. User toggles survive."""
    added = 0
    with db.tx() as con:
        for s in specs:
            con.execute(
                "insert into series(id, short, name, kind, area, ratings, homepage) values(?,?,?,?,?,?,?) "
                "on conflict(id) do update set short=excluded.short, name=excluded.name, kind=excluded.kind, "
                "area=excluded.area, ratings=excluded.ratings, homepage=excluded.homepage",
                (s.id, s.short, s.name, s.kind, s.area, dumps(s.ratings), s.homepage),
            )
            for year in s.years:
                eid = edition_id(s.id, year)
                sources = resolve_sources(s, year)
                row = con.execute("select id, meta from edition where id=?", (eid,)).fetchone()
                if row is None:
                    con.execute(
                        "insert into edition(id, series_id, year, label, enabled, sources, meta) values(?,?,?,?,?,?,?)",
                        (eid, s.id, year, f"{s.short} {year}", int(year in s.enabled_years), dumps(sources),
                         dumps({"registry_enabled": year in s.enabled_years})),
                    )
                    added += 1
                else:
                    meta = loads(row["meta"], {}) or {}
                    discovered_sources = meta.get("discovered_sources") or []
                    con.execute("update edition set sources=?, label=? where id=?",
                                (dumps(sources + discovered_sources), f"{s.short} {year}", eid))
    return {"series": len(specs), "editions_added": added}


def add_discovered_edition(db: Database, spec: SeriesSpec, year: int, extra_sources: list[dict]) -> bool:
    """Add an edition found on a platform but not listed in the YAML. Returns True when new."""
    eid = edition_id(spec.id, year)
    with db.tx() as con:
        row = con.execute("select id, sources, meta from edition where id=?", (eid,)).fetchone()
        if row is not None:
            # Known edition: merge newly found sources (e.g. a PMLR volume that appeared later).
            sources = loads(row["sources"], []) or []
            meta = loads(row["meta"], {}) or {}
            known = {dumps(x) for x in sources}
            changed = False
            for src in extra_sources:
                if dumps(src) not in known:
                    sources.append(src)
                    meta.setdefault("discovered_sources", []).append(src)
                    changed = True
            if changed:
                con.execute("update edition set sources=?, meta=? where id=?", (dumps(sources), dumps(meta), eid))
            return False
        enabled_years = [r[0] for r in con.execute(
            "select year from edition where series_id=? and enabled=1", (spec.id,))]
        enable = bool(enabled_years) and year >= max(enabled_years)
        sources = resolve_sources(spec, year)
        known = {dumps(x) for x in sources}
        sources += [x for x in extra_sources if dumps(x) not in known]
        con.execute(
            "insert into edition(id, series_id, year, label, enabled, sources, discovered, meta) "
            "values(?,?,?,?,?,?,1,?)",
            (eid, spec.id, year, f"{spec.short} {year}", int(enable), dumps(sources),
             dumps({"discovered_at": utcnow(), "discovered_sources": extra_sources})),
        )
    log.info("discovered edition %s (enabled=%s)", eid, enable)
    return True
