"""Discover editions announced by the platforms (the "dynamic" part of the venue list)."""

from __future__ import annotations

import logging
import re
from datetime import date

from confluo_scout.adapters.pmlr import BASE as PMLR
from confluo_scout.adapters.pmlr import feed_volumes, volume_for
from confluo_scout.fetch import FetchError
from confluo_scout.registry import add_discovered_edition

log = logging.getLogger("scout.discovery")


def discover_all(svc) -> dict:
    out: dict = {"added": [], "errors": []}
    this_year = date.today().year
    for step in (_openreview, _pmlr, _cvf, _acl):
        try:
            out["added"] += step(svc, this_year)
        except (FetchError, Exception) as exc:
            out["errors"].append(f"{step.__name__}: {exc}")
            log.warning("discovery %s failed: %s", step.__name__, exc)
    return out


def _openreview(svc, this_year: int) -> list[str]:
    adapter = svc.adapters["openreview"]
    if not svc.secrets.has_openreview:
        return []
    token = adapter._login(svc.fetcher)
    r = svc.fetcher.get("https://api2.openreview.net/groups", params={"id": "venues"},
                        headers={"Authorization": f"Bearer {token}"}, use_cache=False)
    members = set(((r.json() or {}).get("groups") or [{}])[0].get("members", []))
    added = []
    for spec in svc.specs:
        for src in spec.sources:
            if src.get("adapter") != "openreview" or src.get("years"):
                continue
            tmpl = src["group"]
            for year in range(this_year - 1, this_year + 2):
                if tmpl.format(year=year) in members and add_discovered_edition(svc.db, spec, year, []):
                    added.append(f"{spec.id}-{year}")
    return added


def _pmlr(svc, this_year: int) -> list[str]:
    feed = feed_volumes(svc.fetcher.get(f"{PMLR}/feed.xml", max_age=86400).text)
    added = []
    for spec in svc.specs:
        for src in spec.sources:
            if src.get("adapter") != "pmlr" or not src.get("feed_label"):
                continue
            for year in range(this_year - 1, this_year + 1):
                vol = volume_for(feed, src["feed_label"], year)
                if vol and add_discovered_edition(svc.db, spec, year, [{"adapter": "pmlr", "feed_label": src["feed_label"],
                                                                         "volume": vol, "year": year}]):
                    added.append(f"{spec.id}-{year}")
    return added


def _cvf(svc, this_year: int) -> list[str]:
    menu = svc.fetcher.get("https://openaccess.thecvf.com/menu", max_age=86400).text
    found = {(m.group(1), int(m.group(2))) for m in re.finditer(r'href="/?(CVPR|ICCV|WACV)(\d{4})"', menu)}
    added = []
    for spec in svc.specs:
        for src in spec.sources:
            if src.get("adapter") != "cvf":
                continue
            for conf, year in found:
                if conf == src["conf"] and year >= this_year - 1 and add_discovered_edition(svc.db, spec, year, []):
                    added.append(f"{spec.id}-{year}")
    return added


def _acl(svc, this_year: int) -> list[str]:
    added = []
    for spec in svc.specs:
        for src in spec.sources:
            if src.get("adapter") != "acl":
                continue
            year = this_year + 1
            r = svc.fetcher.get(f"https://raw.githubusercontent.com/acl-org/acl-anthology/master/data/xml/"
                                f"{year}.{src['event']}.xml", accept=(200, 404), max_age=86400)
            if r.status == 200 and add_discovered_edition(svc.db, spec, year, []):
                added.append(f"{spec.id}-{year}")
    return added
