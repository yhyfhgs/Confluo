"""运行时配置（接口冻结件 §2.7 的 `Config` 部分；Selector/RunReport/Pipeline 属 T7）。

所有路径经 `Config` 注入，禁止硬编码 `~/.paper-crawler`（Global Constraints §8）——
kill-9 子进程测试依赖 `PAPER_CRAWLER_HOME` 隔离。

**分层加载链（D-025 / [design/10-config-layout.md](../../docs/design/10-config-layout.md)）**——
优先级（高→低，逐键覆盖）：

1. `env`（`PAPER_CRAWLER_*` / 各 `[auth.*]` env 覆盖）      ← 最高（CI/临时会话不落盘凭证）
2. 项目级 `./paper-crawler.toml`（**仅非敏感键**）           ← 本机工作区层（路径/限速/venue 目录）
3. config-home `config.toml`（`$PAPER_CRAWLER_HOME` 或 `~/.paper-crawler`）  ← git 外，可含敏感槽
4. 内置默认（`Config` dataclass 字段默认值）                ← 兜底

- **既有优先级保持**：home 解析（显式 home > `$PAPER_CRAWLER_HOME` > `~/.paper-crawler`）与
  既有 config-home `config.toml` 读取语义**逐字段不变**；项目级 `./paper-crawler.toml` 为**新增
  非敏感层**，插在 env 与 home 之间，纯附加——无项目级文件 + 无新 env 时结果与旧版逐字段一致。
- **项目级定位**：自 `cwd` 起向上查 `paper-crawler.toml`（仓库根惯例），首个命中即读；缺失静默跳过。
- **敏感键防误提交护栏**（§3.1）：项目级文件（易随 `git add .` 误提交）出现敏感键形态 →
  `CrawlerError(CONFIG)` **拒启动**，指引挪至 config-home。敏感键正则与 obslog 脱敏键**单一同源**
  （`sensitive.CONFIG_GUARD_KEY_PATTERN`，防两套清单漂移）。

`describe_config()` 暴露分层解析中间态（每键生效值 + winning 来源层 + 敏感标记）供
`crawler config show` 渲染（脱敏在 CLI presentation 层，config.py 不依赖 obslog）。
"""

import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.sensitive import CONFIG_GUARD_KEY_PATTERN

_PROJECT_CONFIG_NAME = "paper-crawler.toml"
_HOME_CONFIG_NAME = "config.toml"

# 项目级 `./paper-crawler.toml` 敏感键护栏（§3.1）。子串 `re.search`（大小写不敏感）——
# 与 obslog 脱敏键单一同源（`sensitive.py`），不含裸 `key`（误伤 `key_ref`）与 `email`
# （`identity.email` 属合法非凭证键）。
_SENSITIVE_CONFIG_KEY_RE = re.compile(CONFIG_GUARD_KEY_PATTERN, re.IGNORECASE)


def _resolve_under(home: Path, raw: object) -> Path:
    """把 config.toml 里的路径解析为绝对路径：绝对则原样，相对则挂在 home 下。"""
    path = Path(str(raw)).expanduser()
    return path if path.is_absolute() else home / path


def _to_float(raw: object) -> float:
    """toml 数值（int/float/str）→ float。`bool` 显式拒绝（避免 True→1.0 意外）。"""
    if isinstance(raw, bool):
        raise TypeError("expected a number for a scale/budget field, got bool")
    if isinstance(raw, int | float | str):
        return float(raw)
    raise TypeError(f"expected a number, got {type(raw).__name__}")


def _to_int(raw: object) -> int:
    """toml 数值（int/float/str）→ int（auth-framework §8 整数 knob）。`bool` 显式拒绝。"""
    if isinstance(raw, bool):
        raise TypeError("expected an integer for a knob field, got bool")
    if isinstance(raw, int | float | str):
        return int(float(raw))  # "900"/"900.0"/900.0 → 900（whole-second/count 语义）
    raise TypeError(f"expected an integer, got {type(raw).__name__}")


# --- 分层解析核心（Config.load 与 describe_config 共享，防两条路径漂移）------------------------


def _resolve_home(home: Path | None) -> tuple[Path, str]:
    """解析 config-home 及其来源：显式 home > `$PAPER_CRAWLER_HOME` > `~/.paper-crawler`。"""
    if home is not None:
        return home.expanduser(), "explicit"
    if env_home := os.environ.get("PAPER_CRAWLER_HOME"):
        return Path(env_home).expanduser(), "env"
    return (Path.home() / ".paper-crawler").expanduser(), "default"


def resolve_home(home: Path | None = None) -> Path:
    """解析 config-home（显式 home > `$PAPER_CRAWLER_HOME` > `~/.paper-crawler`）。

    供 CLI 装配之外的兜底路径复用（如 openalex 预算 state 的惰性默认），与
    `Config.load` 的 home 解析**单一同源**。D-032（config-home 迁入仓库、env 为主
    指向机制）后，任何绕过 env 的 `Path.home()` 硬编码兜底都会静默回落到空的
    `~/.paper-crawler`——新兜底路径一律经本函数解析。
    """
    return _resolve_home(home)[0]


def _find_project_config(start: Path) -> Path | None:
    """自 `start` 起向上查 `paper-crawler.toml`；首个命中即返回，无则 None（可选层）。

    **上界（NIT-1）**：查到含 `.git`（目录**或**文件——兼容 git worktree 的 `.git` 指针文件）
    的目录（= 仓库根）后即停止本轮向上——不越过仓库根去命中家目录等高层的 stray 同名文件；
    到文件系统根同样停止（`current.parents` 天然终止于根）。本层先查配置文件再判仓库根，故
    仓库根目录**自身**的 `paper-crawler.toml` 仍会被命中。
    """
    current = start.resolve()
    for directory in (current, *current.parents):
        candidate = directory / _PROJECT_CONFIG_NAME
        if candidate.is_file():
            return candidate
        if (directory / ".git").exists():
            break  # 仓库根：本层已查毕，不再向上（防越界命中祖先 stray 文件）
    return None


def _load_toml(path: Path) -> dict[str, object]:
    """读取并解析一个 TOML 文件（家目录 `config.toml` 或项目级 `paper-crawler.toml` 共用）。

    语法错误归一为 `CrawlerError(CONFIG)`——不放行裸 `tomllib.TOMLDecodeError` 逃逸。
    本函数同一层级的敏感键护栏（`_guard_project_config`）早已规范包 CONFIG，语法错误路径
    此前不一致（2026-07-24 审计 P1 [O1]：`config.py:98` 畸形 TOML 逃逸出 errors.py「配置
    错误归 CONFIG 类」契约，CLI 侧因此收到裸异常而非退出码 2）；风格对齐
    `auth/store.py::load_profiles` 对 `profiles.toml` 的同款包裹先例。
    """
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise CrawlerError(
            ErrorClass.CONFIG, f"配置文件解析失败（{path}）：{exc}", detail=str(path)
        ) from exc


def _scan_sensitive_keys(node: object, path: tuple[str, ...] = ()) -> str | None:
    """递归 dict/list，返回首个键名命中敏感模式的**点号路径**；无命中 → None。

    检查每一层的键名（不止叶子——`[credentials]` 这类敏感表名也拦），子串匹配（§3.1）。
    合法结构键（`auth`/`paths`/`rate`/`identity`/`email`/…）均不命中，无误伤。
    """
    if isinstance(node, dict):
        for key, value in node.items():
            key_str = str(key)
            if _SENSITIVE_CONFIG_KEY_RE.search(key_str):
                return ".".join((*path, key_str))
            hit = _scan_sensitive_keys(value, (*path, key_str))
            if hit is not None:
                return hit
    elif isinstance(node, list):
        for index, item in enumerate(node):
            hit = _scan_sensitive_keys(item, (*path, f"[{index}]"))
            if hit is not None:
                return hit
    return None


def _guard_project_config(project_doc: dict[str, object]) -> None:
    """项目级敏感键护栏：命中即 `CrawlerError(CONFIG)` 拒启动（§3.1 指引文案逐字）。"""
    hit = _scan_sensitive_keys(project_doc)
    if hit is not None:
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"项目级 ./paper-crawler.toml 含敏感键 {hit}；凭证禁入项目文件（易误提交）——"
            "挪至 config-home config.toml（$PAPER_CRAWLER_HOME）或环境变量 PAPER_CRAWLER_*",
            detail=hit,
        )


def _lookup_toml(doc: dict[str, object], table: tuple[str, ...], leaf: str) -> object | None:
    """取 `doc[table[0]][table[1]]…[leaf]`；任一层缺失/非表 → None。"""
    node: object = doc
    for part in table:
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    if not isinstance(node, dict):
        return None
    return node.get(leaf)


@dataclass(frozen=True)
class _Resolved:
    """一个配置键的生效值 + winning 来源层。"""

    value: object | None
    source: str  # "env" | "project" | "home" | "default"


@dataclass(frozen=True)
class _FieldSpec:
    """一个配置键的分层解析规格。"""

    key: str  # 点号显示路径，如 "auth.elsevier.api_key"
    table: tuple[str, ...]  # toml 表路径
    leaf: str  # 叶键名
    kind: str  # "str" | "float" | "path" | "paths"
    env: str | None = None  # 环境变量名（仅 str 类有）
    default: object = None  # str→None；float→数值；path/paths 特殊（见 _resolve_field）
    sensitive: bool = False  # 硬凭证（config show 整值脱敏）
    is_email: bool = False  # email（config show 部分脱敏；护栏放行）


# 全部配置键的分层解析规格（顺序即 config show 呈现顺序）。
_FIELD_SPECS: tuple[_FieldSpec, ...] = (
    _FieldSpec("identity.email", ("identity",), "email", "str", is_email=True),
    _FieldSpec(
        "auth.elsevier.api_key",
        ("auth", "elsevier"),
        "api_key",
        "str",
        env="PAPER_CRAWLER_ELSEVIER_API_KEY",
        sensitive=True,
    ),
    _FieldSpec(
        "auth.elsevier.insttoken",
        ("auth", "elsevier"),
        "insttoken",
        "str",
        env="PAPER_CRAWLER_ELSEVIER_INSTTOKEN",
        sensitive=True,
    ),
    _FieldSpec(
        "auth.wiley.token",
        ("auth", "wiley"),
        "token",
        "str",
        env="PAPER_CRAWLER_WILEY_TDM_TOKEN",
        sensitive=True,
    ),
    _FieldSpec(
        "auth.openreview.token",
        ("auth", "openreview"),
        "token",
        "str",
        env="PAPER_CRAWLER_OPENREVIEW_TOKEN",
        sensitive=True,
    ),
    _FieldSpec(
        "auth.openalex.api_key",
        ("auth", "openalex"),
        "api_key",
        "str",
        env="PAPER_CRAWLER_OPENALEX_API_KEY",
        sensitive=True,
    ),
    _FieldSpec(
        "auth.s2.api_key",
        ("auth", "s2"),
        "api_key",
        "str",
        env="PAPER_CRAWLER_S2_API_KEY",
        sensitive=True,
    ),
    _FieldSpec("paths.data_dir", ("paths",), "data_dir", "path"),
    _FieldSpec("paths.venues_dirs", ("paths",), "venues_dirs", "paths"),
    _FieldSpec("rate.scale", ("rate",), "scale", "float", default=1.0),
    _FieldSpec("retry.scale", ("retry",), "scale", "float", default=1.0),
    _FieldSpec(
        "openalex.daily_budget_usd", ("openalex",), "daily_budget_usd", "float", default=0.50
    ),
    # auth-framework §8 pipeline knobs（非敏感数值/字符串；default 与 runner/stages getattr
    # 兜底逐一相同，补字段后行为零变化——runner 消费侧不改）。
    _FieldSpec(
        "auth.daily_cap",
        ("auth",),
        "daily_cap",
        "int",
        env="PAPER_CRAWLER_AUTH_DAILY_CAP",
        default=200,
    ),
    _FieldSpec(
        "auth.health_interval",
        ("auth",),
        "health_interval",
        "int",
        env="PAPER_CRAWLER_AUTH_HEALTH_INTERVAL",
        default=20,
    ),
    _FieldSpec(
        "auth.health_max_age_s",
        ("auth",),
        "health_max_age_s",
        "int",
        env="PAPER_CRAWLER_AUTH_HEALTH_MAX_AGE_S",
        default=900,
    ),
    _FieldSpec(
        "auth.work_hours",
        ("auth",),
        "work_hours",
        "str",
        env="PAPER_CRAWLER_AUTH_WORK_HOURS",
        default="8-23",
    ),
    _FieldSpec(
        "oa_fallback.rate_rpm",
        ("oa_fallback",),
        "rate_rpm",
        "int",
        env="PAPER_CRAWLER_OA_FALLBACK_RATE_RPM",
        default=30,
    ),
    # active_profile：platform→profile 映射（§3.4；无 env，config-home/项目级 TOML 表）。
    _FieldSpec("auth.active_profile", ("auth",), "active_profile", "mapping", default=None),
)


def _default_venues_dirs(home: Path) -> tuple[Path, ...]:
    """venues_dirs 无任何层配置时的默认检测（cwd/venues 在前，home/venues 在后）。"""
    candidates: list[Path] = []
    cwd_venues = Path.cwd() / "venues"
    if cwd_venues.is_dir():
        candidates.append(cwd_venues)
    home_venues = home / "venues"
    if home_venues.is_dir():
        candidates.append(home_venues)
    return tuple(candidates)


def _resolve_field(
    spec: _FieldSpec,
    *,
    home: Path,
    project_doc: dict[str, object],
    home_doc: dict[str, object],
) -> _Resolved:
    """按 env > project > home > default 逐键解析一个字段（各 kind 的规范化见内联）。"""
    if spec.kind == "str":
        # 空白串归一为"未提供"（等价未配置——同既有 token/email 口径）。
        if spec.env:
            env_value = os.environ.get(spec.env, "").strip()
            if env_value:
                return _Resolved(env_value, "env")
        for doc, source in ((project_doc, "project"), (home_doc, "home")):
            raw = _lookup_toml(doc, spec.table, spec.leaf)
            if isinstance(raw, str) and raw.strip():
                return _Resolved(raw.strip(), source)
        # spec.default（既有凭证/email 类恒 None，逐字不变；work_hours 类有非 None 默认）。
        return _Resolved(spec.default, "default")

    if spec.kind == "int":
        if spec.env:
            env_value = os.environ.get(spec.env, "").strip()
            if env_value:
                return _Resolved(_to_int(env_value), "env")
        for doc, source in ((project_doc, "project"), (home_doc, "home")):
            raw = _lookup_toml(doc, spec.table, spec.leaf)
            if raw is not None:
                return _Resolved(_to_int(raw), source)
        return _Resolved(spec.default, "default")

    if spec.kind == "mapping":
        # active_profile 类 TOML 表 → dict[str,str]（无 env——映射不走环境变量，§8）。
        for doc, source in ((project_doc, "project"), (home_doc, "home")):
            raw = _lookup_toml(doc, spec.table, spec.leaf)
            if isinstance(raw, dict):
                return _Resolved({str(k): str(v) for k, v in raw.items()}, source)
        return _Resolved(spec.default, "default")

    if spec.kind == "float":
        for doc, source in ((project_doc, "project"), (home_doc, "home")):
            raw = _lookup_toml(doc, spec.table, spec.leaf)
            if raw is not None:
                return _Resolved(_to_float(raw), source)
        return _Resolved(spec.default, "default")

    if spec.kind == "path":
        for doc, source in ((project_doc, "project"), (home_doc, "home")):
            raw = _lookup_toml(doc, spec.table, spec.leaf)
            if raw is not None:
                return _Resolved(_resolve_under(home, raw), source)
        return _Resolved(home / "data", "default")

    # kind == "paths"
    for doc, source in ((project_doc, "project"), (home_doc, "home")):
        raw = _lookup_toml(doc, spec.table, spec.leaf)
        if isinstance(raw, list):
            return _Resolved(tuple(_resolve_under(home, entry) for entry in raw), source)
    return _Resolved(_default_venues_dirs(home), "default")


def _resolve_all(home: Path | None) -> tuple[Path, str, dict[str, _Resolved]]:
    """分层解析全部字段（Config.load 与 describe_config 共享核心）。

    返回 `(resolved_home, home_source, {key: _Resolved})`。项目级敏感键护栏在此触发
    （命中 → `CrawlerError(CONFIG)` 拒启动，波及所有走 `_resolve_all` 的入口）。
    """
    resolved_home, home_source = _resolve_home(home)

    home_config = resolved_home / _HOME_CONFIG_NAME
    home_doc: dict[str, object] = _load_toml(home_config) if home_config.is_file() else {}

    project_path = _find_project_config(Path.cwd())
    project_doc: dict[str, object] = {}
    if project_path is not None:
        project_doc = _load_toml(project_path)
        _guard_project_config(project_doc)  # 敏感键 → 拒启动（家目录层不受此约束）

    resolved = {
        spec.key: _resolve_field(
            spec, home=resolved_home, project_doc=project_doc, home_doc=home_doc
        )
        for spec in _FIELD_SPECS
    }
    return resolved_home, home_source, resolved


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
    # config-home（不入 git，D-032）；空白串归一为 None。**不入日志/报告**（obslog redact
    # 覆盖 cookie/token 形态）——故本字段绝不经 log_event 落盘。
    openreview_token: str | None = None
    # T6（design/adapters/aggregators.md §5.3/§5.4）：openalex/s2 的可选 API key，沿
    # openreview_token 先例——config-home config.toml + 环境变量覆盖，空白串归一为 None，
    # 不入日志/报告（obslog redact 覆盖 api_key/token 形态）。openalex key **可选**
    # （匿名请求现状 [LIVE] 200，有 key 只是提升每日 credit 额度）；s2 key **生产必需**
    # （无 key `enrich_batch` 直接 CONFIG，不发请求，D2）。
    openalex_api_key: str | None = None
    s2_api_key: str | None = None
    # Phase 4（auth-framework §3.4 / D-023 两级凭证模型①类简单串；D-025 config 归集）：
    # elsevier `X-ELS-APIKey`(+`X-ELS-Insttoken`) 与 wiley TDM `Wiley-TDM-Client-Token`
    # 走 `[auth.elsevier]`/`[auth.wiley]` Config-slot（config-home config.toml + env 覆盖，空白
    # 归一 None，obslog redact 覆盖）——**不触 AES-GCM/keyring**（纯 API 路径无 storage_state）。
    # 不入日志/报告。env：PAPER_CRAWLER_ELSEVIER_API_KEY / _ELSEVIER_INSTTOKEN / _WILEY_TDM_TOKEN。
    elsevier_api_key: str | None = None
    elsevier_insttoken: str | None = None
    wiley_tdm_token: str | None = None
    # OpenAlex 每日 credit 预算上限（美元；aggregators.md §4 伪代码）：保守默认 0.50
    # （≈ 无 key 5000 credits 的一半量级）。非凭证，可入日志/报告。
    openalex_daily_budget_usd: float = 0.50
    # Phase 4 auth-framework §8 pipeline 运行时 knobs（非敏感，可入日志/报告 + 项目级 config）。
    # 默认值与 pipeline/{runner,stages}.py 的 getattr 兜底逐一相同——补真实字段后 runner 直接
    # 读到本值（getattr 兜底降级为防御纵深，仅 Config 缺字段时触发）。
    auth_daily_cap: int = 200  # §8.3 日配额（fetch 尝试篇次）
    auth_health_interval: int = 20  # §8.2 每 N 篇强制 healthcheck
    auth_health_max_age_s: int = 900  # §8.2 健康门老化（15 min）
    auth_work_hours: str = "8-23"  # §8.6 本地工作时段窗（""/"0-24" 关闭）
    oa_fallback_rate_rpm: int = 30  # §8.1 OA 第三方 host 保守限速
    # §3.4 AuthProvider 运行时选择：platform id → profiles.toml 键（`--profile` 可临时覆盖）。
    auth_active_profile: dict[str, str] | None = None

    @classmethod
    def load(cls, home: Path | None = None) -> "Config":
        """按分层加载链（env > 项目级 > home > 默认，模块 docstring）解析出一份 `Config`。

        无项目级 `./paper-crawler.toml` + 无新 env 时结果与旧版**逐字段一致**（纯附加）。
        项目级文件含敏感键 → `CrawlerError(CONFIG)` 拒启动（`_guard_project_config`）。
        """
        resolved_home, _home_source, resolved = _resolve_all(home)

        def _str(key: str) -> str | None:
            value = resolved[key].value
            return value if isinstance(value, str) else None

        def _float(key: str) -> float:
            value = resolved[key].value
            assert isinstance(value, int | float)  # 解析器保证 float 类字段恒有值
            return float(value)

        def _int(key: str) -> int:
            value = resolved[key].value
            assert isinstance(value, int) and not isinstance(value, bool)  # int 类恒有值
            return value

        def _mapping(key: str) -> dict[str, str] | None:
            value = resolved[key].value
            return dict(value) if isinstance(value, dict) else None

        data_dir = resolved["paths.data_dir"].value
        assert isinstance(data_dir, Path)
        venues_dirs = resolved["paths.venues_dirs"].value
        assert isinstance(venues_dirs, tuple)

        return cls(
            home=resolved_home,
            data_dir=data_dir,
            db_path=resolved_home / "catalog.sqlite",
            log_dir=resolved_home / "logs",
            reports_dir=resolved_home / "reports",
            venues_dirs=venues_dirs,
            rate_scale=_float("rate.scale"),
            retry_scale=_float("retry.scale"),
            identity_email=_str("identity.email"),
            openreview_token=_str("auth.openreview.token"),
            openalex_api_key=_str("auth.openalex.api_key"),
            s2_api_key=_str("auth.s2.api_key"),
            elsevier_api_key=_str("auth.elsevier.api_key"),
            elsevier_insttoken=_str("auth.elsevier.insttoken"),
            wiley_tdm_token=_str("auth.wiley.token"),
            openalex_daily_budget_usd=_float("openalex.daily_budget_usd"),
            auth_daily_cap=_int("auth.daily_cap"),
            auth_health_interval=_int("auth.health_interval"),
            auth_health_max_age_s=_int("auth.health_max_age_s"),
            auth_work_hours=_str("auth.work_hours") or "8-23",
            oa_fallback_rate_rpm=_int("oa_fallback.rate_rpm"),
            auth_active_profile=_mapping("auth.active_profile"),
        )

    def ensure_dirs(self) -> None:
        """创建 data/{pdf,si,fulltext,export,tmp}、logs、reports（幂等）。"""
        for sub in ("pdf", "si", "fulltext", "export", "tmp"):
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class ConfigLayer:
    """`describe_config` 产出的一行：一个配置键的生效值 + winning 来源层 + 脱敏标记。

    `value` 是**已类型化的原始值**（Path/tuple/float/str）或 None（未配置）——脱敏/渲染由
    CLI presentation 层（`crawler config show`）据 `sensitive`/`is_email` 施加，config.py
    不回显凭证也不依赖 obslog（关注点分离）。
    """

    key: str
    value: object | None
    source: str  # "env" | "project" | "home" | "default"
    sensitive: bool
    is_email: bool


def describe_config(home: Path | None = None) -> list[ConfigLayer]:
    """分层解析全部配置键 → 每键 (值, winning 来源层, 敏感标记)（`crawler config show` 用）。

    与 `Config.load` 共享 `_resolve_all` 核心（含项目级敏感键护栏——含敏感键则同样拒启动）。
    首行是 `home` 及其来源（explicit/env/default），随后按 `_FIELD_SPECS` 顺序。
    """
    resolved_home, home_source, resolved = _resolve_all(home)
    rows = [
        ConfigLayer(
            key="home", value=resolved_home, source=home_source, sensitive=False, is_email=False
        )
    ]
    for spec in _FIELD_SPECS:
        entry = resolved[spec.key]
        rows.append(
            ConfigLayer(
                key=spec.key,
                value=entry.value,
                source=entry.source,
                sensitive=spec.sensitive,
                is_email=spec.is_email,
            )
        )
    return rows
