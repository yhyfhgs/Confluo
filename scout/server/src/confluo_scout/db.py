"""SQLite storage: schema, migrations and per-thread connections.

One process owns the database (the scout service). Every thread gets its own connection;
WAL mode lets readers run while one writer commits. Abstract text is not stored here except
transiently in `abstract_pending`; the canonical copy lives in compressed shards.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = 2

_SCHEMA_V1 = """
create table if not exists series (
  id text primary key,
  short text not null,
  name text not null,
  kind text not null default 'conference',
  area text,
  ratings text not null default '[]',
  homepage text,
  meta text not null default '{}'
);

create table if not exists edition (
  id text primary key,
  series_id text not null references series(id),
  year integer not null,
  label text not null,
  phase text not null default 'unknown',
  enabled integer not null default 0,
  sources text not null default '[]',
  discovered integer not null default 0,
  last_crawl_at text,
  last_success_at text,
  next_due_at text,
  paper_count integer not null default 0,
  review_count integer not null default 0,
  abstract_count integer not null default 0,
  embedded_count integer not null default 0,
  status text not null default 'idle',
  fail_count integer not null default 0,
  last_error text,
  meta text not null default '{}'
);
create index if not exists edition_series on edition(series_id, year);

create table if not exists paper (
  id integer primary key,
  uid text not null unique,
  edition_id text not null references edition(id),
  title text not null,
  title_norm text not null,
  authors text not null default '[]',
  keywords text not null default '[]',
  area_native text,
  area_secondary text,
  area_unified text,
  tldr text,
  status text not null default 'accepted',
  decision_label text,
  tier integer,
  track text,
  forum_url text,
  pdf_url text,
  proceedings_url text,
  doi text,
  arxiv_id text,
  sources text not null default '{}',
  abstract_gen integer,
  abstract_part integer,
  abstract_line integer,
  abstract_hash text,
  abstract_len integer not null default 0,
  content_hash text not null,
  fts_hash text,
  embed_hash text,
  review_stats text,
  quality real,
  created_at text not null,
  updated_at text not null
);
create index if not exists paper_edition on paper(edition_id);
create index if not exists paper_title on paper(edition_id, title_norm);
create index if not exists paper_embed on paper(embed_hash);

create table if not exists paper_key (
  source text not null,
  key text not null,
  paper_id integer not null references paper(id) on delete cascade,
  primary key (source, key)
);
create index if not exists paper_key_paper on paper_key(paper_id);

create table if not exists review (
  paper_id integer not null references paper(id) on delete cascade,
  review_key text not null,
  rating real,
  rating_raw text,
  confidence real,
  subscores text not null default '{}',
  updated_at text,
  primary key (paper_id, review_key)
);

create virtual table if not exists paper_fts using fts5(
  title, keywords, authors, area, abstract,
  content='', contentless_delete=1,
  tokenize='porter unicode61 remove_diacritics 2'
);

create table if not exists abstract_pending (
  paper_id integer primary key references paper(id) on delete cascade,
  edition_id text not null,
  text text not null,
  hash text not null
);
create index if not exists abstract_pending_edition on abstract_pending(edition_id);

create table if not exists edition_stats (
  edition_id text primary key,
  rating_mean real,
  rating_std real,
  n_reviews integer not null default 0,
  updated_at text not null
);

create table if not exists crawl_cursor (
  edition_id text not null,
  source text not null,
  cursor text not null,
  updated_at text not null,
  primary key (edition_id, source)
);

create table if not exists crawl_job (
  id integer primary key,
  edition_id text not null,
  trigger text not null,
  started_at text not null,
  finished_at text,
  status text not null,
  stats text not null default '{}',
  error text
);
create index if not exists crawl_job_edition on crawl_job(edition_id, started_at);

create table if not exists concept (
  id integer primary key,
  term text not null unique,
  kind text not null,
  df integer not null default 0,
  aliases text not null default '[]',
  embedded integer not null default 0
);

create table if not exists decision_cache (
  key text primary key,
  value text not null,
  created_at text not null
);

create table if not exists setting (
  key text primary key,
  value text not null
);
"""


# v2: a vocabulary view over the FTS index (document frequency per stemmed term).
_SCHEMA_V2 = """
create virtual table if not exists paper_fts_v using fts5vocab(paper_fts, 'row');
"""

_MIGRATIONS = [(1, _SCHEMA_V1), (2, _SCHEMA_V2)]


def utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def dumps(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def loads(raw: str | None, default: object = None) -> object:
    if raw is None or raw == "":
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


class Database:
    """Per-thread SQLite connections to one database file."""

    def __init__(self, path: Path | str):
        self.path = Path(path) if str(path) != ":memory:" else path
        self._local = threading.local()
        self._write_lock = threading.RLock()
        if isinstance(self.path, Path):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def _new_connection(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.path), timeout=60, check_same_thread=False, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("pragma journal_mode=wal")
        con.execute("pragma synchronous=normal")
        con.execute("pragma foreign_keys=on")
        con.execute("pragma busy_timeout=60000")
        con.execute("pragma temp_store=memory")
        con.execute("pragma cache_size=-65536")
        return con

    @property
    def con(self) -> sqlite3.Connection:
        con = getattr(self._local, "con", None)
        if con is None:
            con = self._new_connection()
            self._local.con = con
        return con

    def close(self) -> None:
        con = getattr(self._local, "con", None)
        if con is not None:
            con.close()
            self._local.con = None

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """A write transaction. Writers are serialized in-process to avoid busy loops."""
        with self._write_lock:
            con = self.con
            for attempt in range(8):
                try:
                    con.execute("begin immediate")
                    break
                except sqlite3.OperationalError as exc:  # pragma: no cover - contention path
                    if "locked" not in str(exc) or attempt == 7:
                        raise
                    time.sleep(0.25 * (attempt + 1))
            try:
                yield con
            except BaseException:
                con.execute("rollback")
                raise
            else:
                con.execute("commit")

    def query(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        return self.con.execute(sql, params).fetchall()

    def one(self, sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
        return self.con.execute(sql, params).fetchone()

    def scalar(self, sql: str, params: tuple | dict = ()) -> object:
        row = self.con.execute(sql, params).fetchone()
        return None if row is None else row[0]

    def migrate(self) -> None:
        """Apply pending schema steps; each step runs as one transaction."""
        with self._write_lock:
            version = self.con.execute("pragma user_version").fetchone()[0]
            for target, ddl in _MIGRATIONS:
                if version < target:
                    self.con.executescript("begin;" + ddl + f"\npragma user_version={target};\ncommit;")
                    version = target

    # ---- settings -------------------------------------------------------------------------

    def get_setting(self, key: str, default: object = None) -> object:
        raw = self.scalar("select value from setting where key=?", (key,))
        return loads(raw, default) if raw is not None else default

    def set_setting(self, key: str, value: object) -> None:
        with self.tx() as con:
            con.execute(
                "insert into setting(key, value) values(?, ?) on conflict(key) do update set value=excluded.value",
                (key, dumps(value)),
            )

    # ---- maintenance ----------------------------------------------------------------------

    def backup_to(self, dest: Path) -> None:
        """Online backup (consistent copy while the service runs)."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        out = sqlite3.connect(str(tmp))
        try:
            self.con.backup(out)
        finally:
            out.close()
        tmp.replace(dest)
