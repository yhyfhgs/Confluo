"""An interrupted crawl must save its real position, not 'done'."""

import threading
from types import SimpleNamespace

from confluo_scout.adapters.base import CrawlContext
from confluo_scout.adapters.cvf import CVFAdapter


def test_cvf_stop_keeps_position(fixture_text):
    listing = fixture_text("cvf_list.html")
    paper = fixture_text("cvf_paper.html")
    stop = threading.Event()
    calls = {"pages": 0}

    class FakeFetcher:
        def get(self, url, **kw):
            if "day" in (kw.get("params") or {}):
                return SimpleNamespace(status=200, text=listing, content=listing.encode())
            calls["pages"] += 1
            stop.set()  # the service is asked to stop while the first paper page is processed
            return SimpleNamespace(status=200, text=paper, content=paper.encode())

    ctx = CrawlContext(fetcher=FakeFetcher(), edition_id="cvpr-2025", year=2025, label="CVPR 2025", stop=stop,
                       cursor={"listed": True, "idx": 0})
    batches = list(CVFAdapter().crawl({"conf": "CVPR", "year": 2025, "min_entries": 1}, ctx))
    assert calls["pages"] == 1
    last = batches[-1]
    assert last.note == "stopped"
    assert last.cursor["idx"] < 2  # two entries in the fixture; the second was never fetched
    assert any(r.abstract for r in last.records)  # the fetched abstract is still stored
