"""Runtime configuration.

Scout reads its settings from environment variables and from the Confluo runtime config
(`$CONFLUO_HOME/config.toml`). Secrets are only kept in memory and never logged.

Paths (defaults):
- data dir: `$SCOUT_DATA`, else `$CONFLUO_HOME/scout`, else `<repo>/.confluo/scout`
- secrets:  `$SCOUT_SECRETS`, else `$CONFLUO_HOME/config.toml`, else `<repo>/.confluo/config.toml`
- registry: `$SCOUT_REGISTRY`, else `<repo>/scout/registry/venues.yaml`
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent


def _repo_root() -> Path | None:
    """The Confluo checkout that contains this package (None inside the container image)."""
    for parent in _PKG_DIR.parents:
        if (parent / "scout" / "registry").is_dir() and (parent / "AGENTS.md").is_file():
            return parent
    return None


def _confluo_home() -> Path | None:
    """`$CONFLUO_HOME` when it exists; otherwise the checkout's `.confluo/`.

    A stale variable (for example one left from a renamed folder) must not make Scout create a
    fresh, empty data tree somewhere else, so a missing directory falls back with a warning.
    """
    root = _repo_root()
    env = os.environ.get("CONFLUO_HOME")
    if env:
        path = Path(env).expanduser()
        if path.is_dir():
            return path
        if root is None:
            return path
        import logging

        logging.getLogger("scout.config").warning(
            "CONFLUO_HOME=%s does not exist; using %s instead", path, root / ".confluo")
    return root / ".confluo" if root else None


@dataclass(frozen=True)
class Secrets:
    openreview_username: str | None = field(default=None, repr=False)
    openreview_password: str | None = field(default=None, repr=False)
    gemini_api_key: str | None = field(default=None, repr=False)
    contact: str | None = None

    @property
    def has_openreview(self) -> bool:
        return bool(self.openreview_username and self.openreview_password)

    @property
    def has_gemini(self) -> bool:
        return bool(self.gemini_api_key)


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    secrets_path: Path | None
    registry_path: Path
    web_dist: Path | None
    qdrant_url: str
    model_dir: Path
    device: str
    torch_threads: int
    decision_model: str
    scheduler_enabled: bool
    embed_enabled: bool
    log_level: str
    db_override: Path | None = None
    embed_url: str | None = None

    @property
    def db_path(self) -> Path:
        """The live database. In the container it sits on a Docker volume (`SCOUT_DB_PATH`), because a
        host process that opens a WAL database through the virtiofs mount can corrupt it. A host run
        from the checkout gets its own copy (`scout-host.sqlite`, seeded from the newest backup)."""
        if self.db_override:
            return self.db_override
        name = "scout-host.sqlite" if _repo_root() is not None else "scout.sqlite"
        return self.data_dir / "db" / name

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "db" / "backups"

    @property
    def abstracts_dir(self) -> Path:
        return self.data_dir / "abstracts"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def state_dir(self) -> Path:
        return self.data_dir / "state"

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / "qdrant" / "snapshots"

    def ensure_dirs(self) -> None:
        for p in (self.db_path.parent, self.backups_dir, self.abstracts_dir, self.cache_dir, self.logs_dir,
                  self.state_dir, self.snapshots_dir):
            p.mkdir(parents=True, exist_ok=True)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    home = _confluo_home()
    root = _repo_root()
    data_env = os.environ.get("SCOUT_DATA")
    if data_env:
        data_dir = Path(data_env).expanduser()
    elif home:
        data_dir = home / "scout"
    else:
        data_dir = Path("/data")

    secrets_env = os.environ.get("SCOUT_SECRETS")
    secrets_path = Path(secrets_env).expanduser() if secrets_env else (home / "config.toml" if home else None)

    reg_env = os.environ.get("SCOUT_REGISTRY")
    if reg_env:
        registry_path = Path(reg_env).expanduser()
    elif root:
        registry_path = root / "scout" / "registry" / "venues.yaml"
    else:
        registry_path = Path("/app/registry/venues.yaml")

    web_env = os.environ.get("SCOUT_WEB_DIST")
    if web_env:
        web_dist: Path | None = Path(web_env)
    elif root and (root / "scout" / "web" / "dist").is_dir():
        web_dist = root / "scout" / "web" / "dist"
    else:
        web_dist = None

    model_env = os.environ.get("SCOUT_MODEL_DIR")
    model_dir = Path(model_env) if model_env else data_dir / "models" / "embeddinggemma-2"

    return Settings(
        data_dir=data_dir,
        secrets_path=secrets_path,
        registry_path=registry_path,
        web_dist=web_dist,
        qdrant_url=os.environ.get("QDRANT_URL", "http://127.0.0.1:6333"),
        model_dir=model_dir,
        device=os.environ.get("SCOUT_DEVICE", "auto"),
        torch_threads=int(os.environ.get("SCOUT_TORCH_THREADS", str(max(1, (os.cpu_count() or 4) - 1)))),
        decision_model=os.environ.get("SCOUT_DECISION_MODEL", "gemini-decision-1"),
        scheduler_enabled=_env_bool("SCOUT_SCHEDULER", True),
        embed_enabled=_env_bool("SCOUT_EMBED", True),
        log_level=os.environ.get("SCOUT_LOG_LEVEL", "INFO"),
        db_override=Path(os.environ["SCOUT_DB_PATH"]) if os.environ.get("SCOUT_DB_PATH") else None,
        embed_url=os.environ.get("SCOUT_EMBED_URL") or None,
    )


@lru_cache(maxsize=1)
def get_secrets() -> Secrets:
    """Secrets from the environment first, then from the Confluo runtime config file."""
    cfg: dict = {}
    path = get_settings().secrets_path
    if path and path.is_file():
        try:
            cfg = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            cfg = {}
    auth = cfg.get("auth", {}) if isinstance(cfg, dict) else {}
    orv = auth.get("openreview", {}) if isinstance(auth, dict) else {}
    gem = auth.get("gemini", {}) if isinstance(auth, dict) else {}
    scout = cfg.get("scout", {}) if isinstance(cfg, dict) else {}
    return Secrets(
        openreview_username=os.environ.get("OPENREVIEW_USERNAME") or orv.get("username") or None,
        openreview_password=os.environ.get("OPENREVIEW_PASSWORD") or orv.get("password") or None,
        gemini_api_key=os.environ.get("GEMINI_API_KEY") or gem.get("api_key") or None,
        contact=os.environ.get("SCOUT_CONTACT") or scout.get("contact") or None,
    )


def user_agent() -> str:
    from confluo_scout import __version__

    contact = get_secrets().contact
    suffix = f"; mailto:{contact}" if contact else ""
    return f"ConfluoScout/{__version__} (local personal research tool{suffix})"
