"""Command line: `scout <command>`."""

from __future__ import annotations

import argparse
import json
import sys


def _services():
    from confluo_scout.services import Services

    return Services()


def cmd_editions(args) -> int:
    svc = _services()
    rows = svc.db.query(
        "select id, enabled, phase, status, paper_count, abstract_count, review_count, embedded_count, last_success_at, "
        "last_error from edition order by series_id, year")
    for r in rows:
        if args.enabled and not r["enabled"]:
            continue
        print(f"{r['id']:<14} {'on ' if r['enabled'] else 'off'} {r['phase']:<10} {r['status']:<9} "
              f"papers={r['paper_count']:<6} abstracts={r['abstract_count']:<6} reviews={r['review_count']:<6} "
              f"embedded={r['embedded_count']:<6} {r['last_error'] or ''}")
    return 0


def cmd_crawl(args) -> int:
    svc = _services()
    if args.reset:
        with svc.db.tx() as con:
            con.execute("delete from crawl_cursor where edition_id=?", (args.edition,))
    if args.max_batches:
        count = {"n": 0}

        def progress(_eid, note):
            count["n"] += 1
            print(f"  batch {count['n']}: {note}", file=sys.stderr)
            if count["n"] >= args.max_batches:
                svc.crawler.stop.set()

        svc.crawler.on_progress = progress
    else:
        svc.crawler.on_progress = lambda _e, note: print(f"  {note}", file=sys.stderr)
    result = svc.crawler.crawl_edition(args.edition, trigger="cli")
    print(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    return 0 if result["status"] in ("ok", "stopped") else 1


def cmd_embed(args) -> int:
    from confluo_scout.indexer import Indexer

    svc = _services()
    idx = Indexer(svc)
    n = idx.embed_pending(limit=args.limit)
    print(json.dumps({"embedded": n}))
    return 0


def cmd_concepts(args) -> int:
    from confluo_scout.concepts import ConceptBuilder

    svc = _services()
    print(json.dumps(ConceptBuilder(svc).rebuild(embed=not args.no_embed), ensure_ascii=False))
    return 0


def cmd_search(args) -> int:
    svc = _services()
    params = {"q": args.query, "mode": args.mode, "topn": args.topn}
    res = svc.engine.search(params)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
        return 0
    print(f"rounds={len(res['trace'])} reason={res['converged']['reason']} keywords={res['keywords']}")
    for i, r in enumerate(res["results"][: args.show], 1):
        print(f"{i:>2}. [{r['score']:.3f}] {r['venue']} {r.get('decision_label') or ''} | {r['title_plain']}")
    return 0


def cmd_discover(args) -> int:
    from confluo_scout.discovery import discover_all

    svc = _services()
    print(json.dumps(discover_all(svc), ensure_ascii=False, indent=1))
    return 0


def cmd_eval(args) -> int:
    from confluo_scout.evaluate import run

    svc = _services()
    print(json.dumps(run(svc, n=args.n), ensure_ascii=False, indent=1))
    return 0


def cmd_embed_serve(args) -> int:
    import uvicorn

    uvicorn.run("confluo_scout.embed_server:create_app", factory=True, host=args.host, port=args.port,
                log_level="warning")
    return 0


def cmd_backup(args) -> int:
    from confluo_scout.scheduler import write_backup

    svc = _services()
    print(write_backup(svc))
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    uvicorn.run("confluo_scout.api:create_app", factory=True, host=args.host, port=args.port, log_level="info")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="scout", description="Confluo Scout")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("editions", help="list editions")
    s.add_argument("--enabled", action="store_true")
    s.set_defaults(func=cmd_editions)
    s = sub.add_parser("crawl", help="crawl one edition")
    s.add_argument("edition")
    s.add_argument("--reset", action="store_true", help="drop saved cursors first")
    s.add_argument("--max-batches", type=int, default=0)
    s.set_defaults(func=cmd_crawl)
    s = sub.add_parser("embed", help="embed papers whose vectors are stale")
    s.add_argument("--limit", type=int, default=0)
    s.set_defaults(func=cmd_embed)
    s = sub.add_parser("concepts", help="rebuild the concept vocabulary")
    s.add_argument("--no-embed", action="store_true")
    s.set_defaults(func=cmd_concepts)
    s = sub.add_parser("search", help="run a search")
    s.add_argument("query")
    s.add_argument("--mode", default="smart", choices=["smart", "exact"])
    s.add_argument("--topn", type=int, default=10)
    s.add_argument("--show", type=int, default=15)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_search)
    s = sub.add_parser("discover", help="discover new editions on the platforms")
    s.set_defaults(func=cmd_discover)
    s = sub.add_parser("eval", help="known-item evaluation (TL;DR as query)")
    s.add_argument("--n", type=int, default=40)
    s.set_defaults(func=cmd_eval)
    s = sub.add_parser("embed-serve", help="host-side embedding accelerator (GPU)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8790)
    s.set_defaults(func=cmd_embed_serve)
    s = sub.add_parser("backup", help="write a consistent database backup to the data directory")
    s.set_defaults(func=cmd_backup)
    s = sub.add_parser("serve", help="run the HTTP service")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8770)
    s.set_defaults(func=cmd_serve)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
