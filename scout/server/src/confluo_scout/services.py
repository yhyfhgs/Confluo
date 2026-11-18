"""Wiring: one place that builds the long-lived components of the service."""

from __future__ import annotations

import logging
import logging.handlers
import sys
import threading

from confluo_scout.abstracts import AbstractStore
from confluo_scout.adapters import build_adapters
from confluo_scout.config import Settings, get_secrets, get_settings, user_agent
from confluo_scout.crawler import Crawler
from confluo_scout.db import Database
from confluo_scout.fetch import Fetcher
from confluo_scout.registry import load_registry, sync_registry
from confluo_scout.store import Store

log = logging.getLogger("scout")


def setup_logging(settings: Settings) -> None:
    root = logging.getLogger()
    if getattr(root, "_scout_configured", False):
        return
    root.setLevel(settings.log_level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    root.addHandler(sh)
    try:
        settings.logs_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.TimedRotatingFileHandler(settings.logs_dir / "scout.log", when="midnight",
                                                       backupCount=14, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        pass
    for noisy in ("httpx", "httpcore", "urllib3", "sentence_transformers", "transformers", "filelock"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    root._scout_configured = True  # type: ignore[attr-defined]


class Busy:
    """Counts running interactive searches; background embedding yields while any is active."""

    def __init__(self):
        self._n = 0
        self._lock = threading.Lock()
        self._event = threading.Event()

    def __enter__(self):
        with self._lock:
            self._n += 1
            self._event.set()
        return self

    def __exit__(self, *exc):
        with self._lock:
            self._n -= 1
            if self._n <= 0:
                self._n = 0
                self._event.clear()

    def is_set(self) -> bool:
        return self._event.is_set()


class Services:
    """Long-lived components. Heavy ones (model, vector store, search) load lazily."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.settings.ensure_dirs()
        setup_logging(self.settings)
        self.secrets = get_secrets()
        self.db = Database(self.settings.db_path)
        self.abstracts = AbstractStore(self.settings.abstracts_dir)
        self.store = Store(self.db, self.abstracts)
        self.fetcher = Fetcher(self.settings.cache_dir, user_agent())
        self.specs = load_registry(self.settings.registry_path)
        sync_registry(self.db, self.specs)
        self.adapters = build_adapters(self.secrets)
        self.crawler = Crawler(self.db, self.store, self.fetcher, self.adapters)
        self._lock = threading.Lock()
        self.interactive = Busy()
        self.scheduler = None
        self._embedder = None
        self._bg_embedder = None
        self._vectors = None
        self._engine = None
        self._decider = None

    @property
    def spec_by_id(self) -> dict:
        return {s.id: s for s in self.specs}

    @property
    def embedder(self):
        with self._lock:
            if self._embedder is None:
                from confluo_scout.embed import Embedder

                self._embedder = Embedder(self.settings)
            return self._embedder

    @property
    def bg_embedder(self):
        """A second model instance for background indexing, so searches never wait for a batch."""
        with self._lock:
            if self._bg_embedder is None:
                from confluo_scout.embed import Embedder

                self._bg_embedder = Embedder(self.settings)
            return self._bg_embedder

    @property
    def vectors(self):
        with self._lock:
            if self._vectors is None:
                from confluo_scout.vectors import VectorStore

                self._vectors = VectorStore(self.settings)
            return self._vectors

    @property
    def decider(self):
        with self._lock:
            if self._decider is None:
                from confluo_scout.search.decision import build_decider

                self._decider = build_decider(self.db, self.secrets, self.settings.decision_model)
            return self._decider

    @property
    def engine(self):
        if self._engine is None:
            from confluo_scout.search.engine import SearchEngine

            engine = SearchEngine(self)
            with self._lock:
                if self._engine is None:
                    self._engine = engine
        return self._engine
