"""HTTP API and static web UI."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from confluo_scout import __version__
from confluo_scout.db import loads
from confluo_scout.services import Services

log = logging.getLogger("scout.api")

SEARCH_KEYS = ("q", "mode", "sort", "venues", "year_from", "year_to", "statuses", "topn", "seeds", "new_keywords",
               "judge_top", "max_rounds", "time_budget_s", "beta", "gamma", "hop_decay", "limit")
NUMERIC_DEFAULT_KEYS = ("topn", "seeds", "new_keywords", "judge_top", "max_rounds", "time_budget_s", "beta", "gamma",
                        "hop_decay", "limit")


def _search_params(svc: Services, request: Request) -> dict:
    qp = request.query_params
    params: dict = {k: qp.get(k) for k in SEARCH_KEYS if qp.get(k) not in (None, "")}
    for key in ("venues", "statuses"):
        if key in params:
            params[key] = [x.strip() for x in str(params[key]).split(",") if x.strip()]
    defaults = svc.db.get_setting("search_defaults", {}) or {}
    for k, v in defaults.items():
        params.setdefault(k, v)
    return params


def _sse(events: Iterator[dict], svc: Services) -> Iterator[bytes]:
    with svc.interactive:
        try:
            for ev in events:
                yield f"event: {ev['event']}\ndata: {json.dumps(ev['data'], ensure_ascii=False, default=str)}\n\n".encode()
        except Exception as exc:
            log.exception("search failed: %s", exc)
            yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n".encode()


def _bibtex(p: dict, venue: str, year: int | None) -> str:
    first = (p["authors"][0].split()[-1] if p["authors"] else "anon").lower()
    word = next((w for w in p["title"].lower().split() if len(w) > 3), "paper")
    key = "".join(ch for ch in f"{first}{year or ''}{word}" if ch.isalnum())
    fields = [f"  title = {{{p['title']}}}", f"  author = {{{' and '.join(p['authors'])}}}",
              f"  booktitle = {{{venue}}}", f"  year = {{{year or ''}}}"]
    url = p.get("proceedings_url") or p.get("forum_url")
    if url:
        fields.append(f"  url = {{{url}}}")
    if p.get("doi"):
        fields.append(f"  doi = {{{p['doi']}}}")
    return "@inproceedings{" + key + ",\n" + ",\n".join(fields) + "\n}"


def create_app() -> FastAPI:
    svc = Services()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        def warm() -> None:
            try:
                _ = svc.vectors
                _ = svc.embedder
                _ = svc.decider
            except Exception as exc:
                log.warning("warm-up incomplete: %s", exc)
            if svc.settings.scheduler_enabled:
                from confluo_scout.scheduler import Scheduler

                svc.scheduler = Scheduler(svc)
                svc.scheduler.start()

        threading.Thread(target=warm, name="warm-up", daemon=True).start()
        yield
        if svc.scheduler:
            svc.scheduler.shutdown()

    app = FastAPI(title="Confluo Scout", version=__version__, lifespan=lifespan)
    app.state.svc = svc

    @app.get("/api/health")
    def health() -> dict:
        out: dict = {"version": __version__, "db": "ok"}
        try:
            out["papers"] = svc.db.scalar("select count(*) from paper")
        except Exception as exc:
            out["db"] = f"error: {exc}"
        try:
            out["vectors"] = svc.vectors.count() if svc._vectors is not None else "starting"
        except Exception as exc:
            out["vectors"] = f"error: {exc}"
        out["model"] = ({"device": svc._embedder.device, "params_m": svc._embedder.params_m}
                        if svc._embedder is not None else "loading")
        out["decision"] = svc._decider.status() if svc._decider is not None else "loading"
        out["scheduler"] = "on" if svc.scheduler else ("off" if not svc.settings.scheduler_enabled else "starting")
        out["status"] = "ok" if out["db"] == "ok" else "degraded"
        return out

    @app.get("/api/stats")
    def stats() -> dict:
        db = svc.db
        row = db.one("select count(*) n, sum(abstract_len>0) a, sum(embed_hash is not null and embed_hash=content_hash) e, "
                     "sum(review_stats is not null) r from paper p join edition ed on ed.id=p.edition_id "
                     "where ed.enabled=1")
        return {
            "papers": row["n"] or 0, "abstracts": row["a"] or 0, "embedded": row["e"] or 0, "with_reviews": row["r"] or 0,
            "reviews": db.scalar("select count(*) from review"),
            "editions_enabled": db.scalar("select count(*) from edition where enabled=1"),
            "concepts": db.scalar("select count(*) from concept where df>0"),
            "abstract_store_bytes": svc.abstracts.disk_usage(),
            "db_bytes": svc.settings.db_path.stat().st_size if svc.settings.db_path.exists() else 0,
        }

    @app.get("/api/venues")
    def venues() -> dict:
        series = {r["id"]: dict(r) | {"ratings": loads(r["ratings"], []), "editions": []}
                  for r in svc.db.query("select id, short, name, kind, area, ratings, homepage from series order by id")}
        for e in svc.db.query("select * from edition order by year desc"):
            d = {k: e[k] for k in ("id", "year", "label", "phase", "enabled", "status", "paper_count", "abstract_count",
                                   "review_count", "embedded_count", "last_success_at", "last_crawl_at", "next_due_at",
                                   "last_error", "discovered")}
            d["enabled"] = bool(d["enabled"])
            d["sources"] = [s.get("adapter") for s in loads(e["sources"], [])]
            if e["series_id"] in series:
                series[e["series_id"]]["editions"].append(d)
        order = [s.id for s in svc.specs]
        return {"series": sorted(series.values(), key=lambda s: order.index(s["id"]) if s["id"] in order else 999)}

    @app.patch("/api/venues/{edition_id}")
    def toggle(edition_id: str, payload: dict = Body(...)) -> dict:
        row = svc.db.one("select id, last_success_at from edition where id=?", (edition_id,))
        if row is None:
            raise HTTPException(404, "unknown edition")
        if "enabled" in payload:
            with svc.db.tx() as con:
                con.execute("update edition set enabled=? where id=?", (int(bool(payload["enabled"])), edition_id))
            if payload["enabled"] and not row["last_success_at"] and svc.scheduler:
                svc.scheduler.enqueue(edition_id, front=True)
        return {"id": edition_id, "enabled": bool(payload.get("enabled"))}

    @app.post("/api/venues/{edition_id}/crawl")
    def crawl_now(edition_id: str) -> dict:
        if svc.db.one("select id from edition where id=?", (edition_id,)) is None:
            raise HTTPException(404, "unknown edition")
        if not svc.scheduler:
            raise HTTPException(503, "scheduler not running")
        svc.scheduler.enqueue(edition_id, front=True)
        return {"queued": edition_id}

    @app.post("/api/discover")
    def discover() -> dict:
        from confluo_scout.discovery import discover_all

        return discover_all(svc)

    @app.get("/api/jobs")
    def jobs(limit: int = Query(30, le=200)) -> dict:
        rows = svc.db.query("select * from crawl_job order by id desc limit ?", (limit,))
        return {"scheduler": svc.scheduler.status() if svc.scheduler else None,
                "jobs": [dict(r) | {"stats": loads(r["stats"], {})} for r in rows]}

    @app.get("/api/search")
    def search(request: Request) -> JSONResponse:
        params = _search_params(svc, request)
        with svc.interactive:
            res = svc.engine.search(params)
        return JSONResponse(res)

    @app.get("/api/search/stream")
    def search_stream(request: Request) -> StreamingResponse:
        params = _search_params(svc, request)
        return StreamingResponse(_sse(svc.engine.stream(params), svc), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/papers/{pid}")
    def paper(pid: str) -> dict:
        row = svc.db.one("select * from paper where id=?", (int(pid),)) if pid.isdigit() else \
            svc.db.one("select * from paper where uid=?", (pid,))
        if row is None:
            raise HTTPException(404, "unknown paper")
        ed = svc.db.one("select e.label, e.year, e.phase, s.short, s.name, s.ratings from edition e "
                        "join series s on s.id=e.series_id where e.id=?", (row["edition_id"],))
        est = svc.db.one("select rating_mean, rating_std, n_reviews from edition_stats where edition_id=?",
                         (row["edition_id"],))
        p = {k: v for k, v in dict(row).items() if k not in ("abstract_gen", "abstract_part", "abstract_line",
                                                              "fts_hash", "embed_hash", "sources")}
        p["authors"] = loads(row["authors"], [])
        p["keywords"] = loads(row["keywords"], [])
        p["review_stats"] = loads(row["review_stats"], None)
        p["abstract"] = svc.store.abstract_of(row) or ""
        p["venue"] = ed["label"] if ed else row["edition_id"]
        p["year"] = ed["year"] if ed else None
        p["series"] = {"short": ed["short"], "name": ed["name"], "ratings": loads(ed["ratings"], [])} if ed else None
        p["edition_stats"] = dict(est) if est else None
        p["sources"] = sorted(k for k in (loads(row["sources"], {}) or {}) if not k.startswith("_"))
        p["reviews"] = [dict(r) | {"subscores": loads(r["subscores"], {})} for r in
                        svc.db.query("select review_key, rating, rating_raw, confidence, subscores, updated_at "
                                     "from review where paper_id=? order by rating desc", (row["id"],))]
        p["bibtex"] = _bibtex(p, ed["name"] if ed else p["venue"], p["year"])
        return p

    @app.get("/api/settings")
    def get_settings() -> dict:
        from confluo_scout.search.engine import DEFAULTS

        return {"defaults": DEFAULTS, "saved": svc.db.get_setting("search_defaults", {})}

    @app.put("/api/settings")
    def put_settings(payload: dict = Body(...)) -> dict:
        clean = {k: payload[k] for k in NUMERIC_DEFAULT_KEYS if k in payload}
        svc.db.set_setting("search_defaults", clean)
        return {"saved": clean}

    @app.get("/api/suggest")
    def suggest(q: str = Query("", max_length=80)) -> dict:
        from confluo_scout.concepts import get_vocab, norm_concept

        prefix = norm_concept(q)
        if len(prefix) < 2:
            return {"items": []}
        vocab = get_vocab(svc)
        hits = [e for t, e in vocab.by_term.items() if t.startswith(prefix) and e["kind"] != "word"]
        hits.sort(key=lambda e: -e["df"])
        return {"items": [{"term": e["term"], "df": e["df"], "kind": e["kind"]} for e in hits[:8]]}

    web = svc.settings.web_dist
    if web and Path(web).is_dir():
        assets = Path(web) / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            target = Path(web) / path
            if path and target.is_file() and Path(web) in target.resolve().parents:
                return FileResponse(target)
            return FileResponse(Path(web) / "index.html")

    return app
