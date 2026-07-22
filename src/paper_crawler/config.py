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
    # OpenReview 自有账号 access token（design/adapters/openreview.md §3 free_account
    # 通道）：CLI 装配期据此为 openreview adapter 构造携 `Cookie: openreview.accessToken=`
    # 附加头的**专属** client（绝不复用共享 client——cookie 外泄他站属凭证红线）。缺省
    # None → 匿名（groups/healthcheck 可用，notes/pdf 会 403→auth_expired→BLOCKED）。
    # 家目录 config（仓库外，不入 git）；空白串归一为 None。**不入日志/报告**（obslog redact
    # 覆盖 cookie/token 形态）——故本字段绝不经 log_event 落盘。
    openreview_token: str | None = None
    # T6（design/adapters/aggregators.md §5.3/§5.4）：openalex/s2 的可选 API key，沿
    # openreview_token 先例——家目录 config（仓库外）+ 环境变量覆盖，空白串归一为 None，
    # 不入日志/报告（obslog redact 覆盖 api_key/token 形态）。openalex key **可选**
    # （匿名请求现状 [LIVE] 200，有 key 只是提升每日 credit 额度）；s2 key **生产必需**
    # （无 key `enrich_batch` 直接 CONFIG，不发请求，D2）。
    openalex_api_key: str | None = None
    s2_api_key: str | None = None
    # OpenAlex 每日 credit 预算上限（美元；aggregators.md §4 伪代码）：保守默认 0.50
    # （≈ 无 key 5000 credits 的一半量级）。非凭证，可入日志/报告。
    openalex_daily_budget_usd: float = 0.50

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
        openreview_token: str | None = None
        openalex_api_key: str | None = None
        s2_api_key: str | None = None
        openalex_daily_budget_usd = 0.50
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
            # [auth.openreview].token：空白串归一为 None（openreview.md §3）。
            raw_token = doc.get("auth", {}).get("openreview", {}).get("token")
            if isinstance(raw_token, str) and raw_token.strip():
                openreview_token = raw_token.strip()
            # [auth.openalex].api_key / [auth.s2].api_key（T6，aggregators.md §5.3/§5.4）：
            # 空白串归一为 None，同 openreview token 口径。
            auth_doc = doc.get("auth", {})
            raw_openalex_key = auth_doc.get("openalex", {}).get("api_key")
            if isinstance(raw_openalex_key, str) and raw_openalex_key.strip():
                openalex_api_key = raw_openalex_key.strip()
            raw_s2_key = auth_doc.get("s2", {}).get("api_key")
            if isinstance(raw_s2_key, str) and raw_s2_key.strip():
                s2_api_key = raw_s2_key.strip()
            # [openalex].daily_budget_usd（T6，aggregators.md §4 伪代码）：非凭证数值。
            openalex_daily_budget_usd = float(
                doc.get("openalex", {}).get("daily_budget_usd", openalex_daily_budget_usd)
            )

        # 环境变量覆盖 config.toml（12-factor 惯例；CI/临时会话不落盘凭证的通道）。
        # 空白归一为 None——同 PAPER_CRAWLER_OPENREVIEW_TOKEN 既有先例。
        env_token = os.environ.get("PAPER_CRAWLER_OPENREVIEW_TOKEN", "").strip()
        if env_token:
            openreview_token = env_token
        env_openalex_key = os.environ.get("PAPER_CRAWLER_OPENALEX_API_KEY", "").strip()
        if env_openalex_key:
            openalex_api_key = env_openalex_key
        env_s2_key = os.environ.get("PAPER_CRAWLER_S2_API_KEY", "").strip()
        if env_s2_key:
            s2_api_key = env_s2_key

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
            openreview_token=openreview_token,
            openalex_api_key=openalex_api_key,
            s2_api_key=s2_api_key,
            openalex_daily_budget_usd=openalex_daily_budget_usd,
        )

    def ensure_dirs(self) -> None:
        """创建 data/{pdf,si,fulltext,export,tmp}、logs、reports（幂等）。"""
        for sub in ("pdf", "si", "fulltext", "export", "tmp"):
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
