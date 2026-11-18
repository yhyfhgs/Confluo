"""Adapter protocol shared by all platform adapters."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Protocol

from confluo_scout.fetch import Fetcher
from confluo_scout.records import PaperRecord


class StructureDrift(Exception):
    """A page no longer looks like what the parser expects. The batch is not stored."""


class AuthError(Exception):
    """Credentials are missing or rejected."""


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise StructureDrift(message)


@dataclass
class Batch:
    records: list[PaperRecord]
    cursor: dict
    phase: str | None = None
    note: str | None = None


@dataclass
class CrawlContext:
    fetcher: Fetcher
    edition_id: str
    year: int
    label: str
    cursor: dict = field(default_factory=dict)
    has_abstract: Callable[[str], bool] = lambda _title_norm: False
    known_titles: Callable[[], set[str]] = lambda: set()
    stop: threading.Event = field(default_factory=threading.Event)
    log: logging.Logger = field(default_factory=lambda: logging.getLogger("scout.adapter"))
    include_rejected: bool = False

    def stopped(self) -> bool:
        return self.stop.is_set()


class Adapter(Protocol):
    name: str

    def source_id(self, src: dict) -> str:
        """Stable id of one configured source within an edition (cursor key)."""
        ...

    def crawl(self, src: dict, ctx: CrawlContext) -> Iterator[Batch]:
        ...


def chunks(items: list, size: int) -> Iterator[list]:
    for i in range(0, len(items), size):
        yield items[i:i + size]
