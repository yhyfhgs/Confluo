"""Abstract shards: per-edition generations of zstd-compressed JSONL parts.

Layout: <root>/<edition>/g<gen>/part-<n>.jsonl.zst plus <root>/<edition>/manifest.json.
A crawl writes changed abstracts to `abstract_pending`; compaction rewrites the whole edition
into a new generation, the database switches its pointers in one transaction, the manifest is
replaced atomically and older generations are deleted. Readers use the (gen, part, line)
pointer stored with each paper, so a crash between steps never breaks reads.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
from collections import OrderedDict
from pathlib import Path

import zstandard

_GEN_RE = re.compile(r"^g(\d{4,})$")


class AbstractStore:
    def __init__(self, root: Path, part_size: int = 2000, cache_parts: int = 96, level: int = 12):
        self.root = root
        self.part_size = part_size
        self.level = level
        self._cache: OrderedDict[tuple[str, int, int], list[str]] = OrderedDict()
        self._cache_parts = cache_parts
        self._lock = threading.Lock()
        self.root.mkdir(parents=True, exist_ok=True)

    # ---- paths ----------------------------------------------------------------------------

    def _edition_dir(self, edition_id: str) -> Path:
        return self.root / edition_id

    def _part_path(self, edition_id: str, gen: int, part: int) -> Path:
        return self._edition_dir(edition_id) / f"g{gen:04d}" / f"part-{part:05d}.jsonl.zst"

    def generations(self, edition_id: str) -> list[int]:
        d = self._edition_dir(edition_id)
        if not d.is_dir():
            return []
        gens = []
        for child in d.iterdir():
            m = _GEN_RE.match(child.name)
            if m and child.is_dir():
                gens.append(int(m.group(1)))
        return sorted(gens)

    def manifest(self, edition_id: str) -> dict | None:
        p = self._edition_dir(edition_id) / "manifest.json"
        if not p.is_file():
            return None
        try:
            return json.loads(p.read_text())
        except (OSError, ValueError):
            return None

    # ---- read -----------------------------------------------------------------------------

    def _load_part(self, edition_id: str, gen: int, part: int) -> list[str]:
        key = (edition_id, gen, part)
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return hit
        path = self._part_path(edition_id, gen, part)
        raw = zstandard.ZstdDecompressor().decompress(path.read_bytes())
        texts = [json.loads(line)["abstract"] for line in raw.decode("utf-8").splitlines() if line]
        with self._lock:
            self._cache[key] = texts
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_parts:
                self._cache.popitem(last=False)
        return texts

    def read(self, edition_id: str, gen: int | None, part: int | None, line: int | None) -> str | None:
        if gen is None or part is None or line is None:
            return None
        try:
            texts = self._load_part(edition_id, gen, part)
        except (OSError, zstandard.ZstdError, ValueError, KeyError):
            return None
        return texts[line] if 0 <= line < len(texts) else None

    # ---- write ----------------------------------------------------------------------------

    def write_generation(self, edition_id: str, items: list[tuple[int, str, str]]) -> tuple[int, dict[int, tuple[int, int]]]:
        """Write a complete new generation. items: (paper_id, uid, abstract). Returns (gen, pointers)."""
        gens = self.generations(edition_id)
        gen = (gens[-1] + 1) if gens else 1
        gdir = self._edition_dir(edition_id) / f"g{gen:04d}"
        gdir.mkdir(parents=True, exist_ok=True)
        cctx = zstandard.ZstdCompressor(level=self.level)
        pointers: dict[int, tuple[int, int]] = {}
        parts_meta = []
        ordered = sorted(items, key=lambda it: it[1])
        for part_no, start in enumerate(range(0, len(ordered), self.part_size)):
            chunk = ordered[start:start + self.part_size]
            lines = []
            for line_no, (pid, uid, text) in enumerate(chunk):
                lines.append(json.dumps({"id": pid, "uid": uid, "abstract": text}, ensure_ascii=False))
                pointers[pid] = (part_no, line_no)
            payload = ("\n".join(lines) + "\n").encode("utf-8")
            blob = cctx.compress(payload)
            path = self._part_path(edition_id, gen, part_no)
            tmp = path.with_suffix(".tmp")
            with open(tmp, "wb") as fh:
                fh.write(blob)
                fh.flush()
                os.fsync(fh.fileno())
            tmp.replace(path)
            parts_meta.append({"name": path.name, "count": len(chunk), "bytes": len(blob),
                               "raw_bytes": len(payload), "sha256": hashlib.sha256(blob).hexdigest()})
        self._write_manifest(edition_id, {"edition": edition_id, "gen": gen, "parts": parts_meta,
                                          "count": len(ordered), "state": "written"})
        return gen, pointers

    def commit_generation(self, edition_id: str, gen: int) -> None:
        """Mark `gen` current and remove older generations (call after the DB switched pointers)."""
        man = self.manifest(edition_id) or {"edition": edition_id, "gen": gen, "parts": []}
        man["gen"], man["state"] = gen, "current"
        self._write_manifest(edition_id, man)
        for old in self.generations(edition_id):
            if old != gen:
                shutil.rmtree(self._edition_dir(edition_id) / f"g{old:04d}", ignore_errors=True)
        with self._lock:
            for key in [k for k in self._cache if k[0] == edition_id and k[1] != gen]:
                del self._cache[key]

    def _write_manifest(self, edition_id: str, data: dict) -> None:
        p = self._edition_dir(edition_id) / "manifest.json"
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
        tmp.replace(p)

    def verify(self, edition_id: str) -> tuple[bool, str]:
        """Check the current generation against its manifest checksums."""
        man = self.manifest(edition_id)
        if not man:
            return False, "no manifest"
        for part in man.get("parts", []):
            path = self._edition_dir(edition_id) / f"g{man['gen']:04d}" / part["name"]
            if not path.is_file():
                return False, f"missing {path.name}"
            if hashlib.sha256(path.read_bytes()).hexdigest() != part["sha256"]:
                return False, f"checksum mismatch {path.name}"
        return True, f"{man.get('count', 0)} abstracts in {len(man.get('parts', []))} parts"

    def disk_usage(self) -> int:
        total = 0
        for dirpath, _dirs, files in os.walk(self.root):
            for f in files:
                total += os.path.getsize(os.path.join(dirpath, f))
        return total
