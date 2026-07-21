"""运行时配置（接口冻结件 §2.7 的 `Config` 部分；Selector/RunReport/Pipeline 属 T7）。

所有路径经 `Config` 注入，禁止硬编码 `~/.paper-crawler`（Global Constraints §8）——
kill-9 子进程测试依赖 `PAPER_CRAWLER_HOME` 隔离。
"""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


def _resolve_under(home: Path, raw: object) -> Path:
    """把 config.toml 里的路径解析为绝对路径：绝对则原样，相对则挂在 home 下。"""
    path = Path(str(raw)).expanduser()
    return path if path.is_absolute() else home / path


@dataclass(frozen=True)
class Config:
    """一次运行的全部路径与缩放因子。"""

    home: Path
    data_dir: Path
    db_path: Path
    log_dir: Path
    reports_dir: Path
    venues_dirs: tuple[Path, ...]
    rate_scale: float = 1.0
    retry_scale: float = 1.0
    # D-014 联系人 email：真实 adapter 的 UA `mailto:` 段来源（不硬编码）。缺省
    # None → UA 省略 mailto 段（CLI 网络命令 obslog warn 一次）。空白串归一为 None。
    identity_email: str | None = None

    @classmethod
    def load(cls, home: Path | None = None) -> "Config":
        """按优先级解析 home 并加载可选的 config.toml。

        优先级：显式 home 参数 > $PAPER_CRAWLER_HOME > ~/.paper-crawler。
        若 home/config.toml 存在，读取 [paths].data_dir、[paths].venues_dirs、
        [rate].scale、[retry].scale。venues_dirs 缺省 = (cwd/"venues" 若存在,
        home/"venues" 若存在)；后目录同 id 覆盖前目录（design/02 §4）。
        """
        if home is not None:
            resolved_home = home
        elif env_home := os.environ.get("PAPER_CRAWLER_HOME"):
            resolved_home = Path(env_home)
        else:
            resolved_home = Path.home() / ".paper-crawler"
        resolved_home = resolved_home.expanduser()

        data_dir = resolved_home / "data"
        rate_scale = 1.0
        retry_scale = 1.0
        identity_email: str | None = None
        venues_dirs_override: tuple[Path, ...] | None = None

        config_file = resolved_home / "config.toml"
        if config_file.is_file():
            with config_file.open("rb") as handle:
                doc = tomllib.load(handle)
            paths = doc.get("paths", {})
            if "data_dir" in paths:
                data_dir = _resolve_under(resolved_home, paths["data_dir"])
            if "venues_dirs" in paths:
                venues_dirs_override = tuple(
                    _resolve_under(resolved_home, entry) for entry in paths["venues_dirs"]
                )
            rate_scale = float(doc.get("rate", {}).get("scale", rate_scale))
            retry_scale = float(doc.get("retry", {}).get("scale", retry_scale))
            # [identity].email：空白串归一为 None（等价未配置——UA 不带 mailto）。
            raw_email = doc.get("identity", {}).get("email")
            if isinstance(raw_email, str) and raw_email.strip():
                identity_email = raw_email.strip()

        if venues_dirs_override is not None:
            venues_dirs = venues_dirs_override
        else:
            candidates: list[Path] = []
            cwd_venues = Path.cwd() / "venues"
            if cwd_venues.is_dir():
                candidates.append(cwd_venues)
            home_venues = resolved_home / "venues"
            if home_venues.is_dir():
                candidates.append(home_venues)
            venues_dirs = tuple(candidates)

        return cls(
            home=resolved_home,
            data_dir=data_dir,
            db_path=resolved_home / "catalog.sqlite",
            log_dir=resolved_home / "logs",
            reports_dir=resolved_home / "reports",
            venues_dirs=venues_dirs,
            rate_scale=rate_scale,
            retry_scale=retry_scale,
            identity_email=identity_email,
        )

    def ensure_dirs(self) -> None:
        """创建 data/{pdf,si,fulltext,export,tmp}、logs、reports（幂等）。"""
        for sub in ("pdf", "si", "fulltext", "export", "tmp"):
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
