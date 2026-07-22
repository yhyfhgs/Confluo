"""VenueSpec 加载、校验（lint）与路由（接口冻结件 §2.8）。

职责边界（design/02 §2.2/§4）：
- `load_dirs` 递归扫描给定目录序列下的 `*.yaml`，解析为 `VenueSpec` 并登记。
  `dirs` 的每个元素视为"一个目录"：同一元素内（递归子目录也算）id 重复=错误
  （排序后先出现的文件保留，其余被忽略并记一条 LintIssue）；不同元素之间同 id
  = 覆盖合法，后一个元素覆盖前一个元素（用户目录覆盖项目目录的语义）。单个文件的
  读取失败（非 UTF-8 编码、权限拒绝、悬空符号链接等 OSError/UnicodeDecodeError）、
  YAML 解析失败或 VenueSpec 结构校验失败都只影响该文件，不影响其余文件；本方法
  只返回问题列表，从不 raise。每次调用都会重置之前 load_dirs 积累的状态。
- `lint` 在已加载的 venue 上补充语义校验（引用的 adapter 是否已注册、auth 等级
  是否兼容、journal 的 issn 是否必填且格式合法），并叠加 `load_dirs` 期间发现的
  结构性问题——空列表即代表全部通过（`crawler venues lint` 的判据）。
- `get`/`route`/`all` 是运行期查询面：`get` 对未知 id 抛 `CrawlerError(CONFIG)`；
  `route` 把 venue 解析为 metadata/fulltext adapter 绑定 + 限速覆盖（design/02 §4）。
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from paper_crawler.adapter import SourceAdapter
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.types import AuthLevel, VenueSpec

# 认证等级序（design/02 §2.2）：none < free_account < subscription < institutional。
# 不可用 StrEnum 的天然字符串比较（"free_account" < "none" 字典序会得出错误结论），
# 必须显式给出语义顺序。
_AUTH_LEVEL_ORDER: dict[AuthLevel, int] = {
    AuthLevel.NONE: 0,
    AuthLevel.FREE_ACCOUNT: 1,
    AuthLevel.SUBSCRIPTION: 2,
    AuthLevel.INSTITUTIONAL: 3,
}

# D-015：期刊 ISSN 格式 NNNN-NNN[N|X]。
_ISSN_PATTERN = re.compile(r"^\d{4}-\d{3}[\dX]$")


@dataclass(frozen=True)
class Route:
    """venue_id 的绑定解析结果（design/02 §4）。"""

    venue: VenueSpec
    metadata_adapter: SourceAdapter
    fulltext_adapter: SourceAdapter
    auth_profile: str | None  # = venue.auth.provider_hint
    rate_overrides: dict[str, float]  # domain -> rpm


@dataclass(frozen=True)
class LintIssue:
    """一条校验问题；file/field 定位供 `crawler venues lint` 输出（AC-1.6）。"""

    file: str
    venue_id: str | None
    field: str
    message: str


class VenueRegistry:
    """VenueSpec 的加载、校验与路由。"""

    def __init__(self, adapters: dict[str, SourceAdapter]) -> None:
        self._adapters = adapters
        self._venues: dict[str, VenueSpec] = {}
        self._file_of: dict[str, str] = {}
        self._load_issues: list[LintIssue] = []

    # -- 加载 ------------------------------------------------------------

    def load_dirs(self, dirs: Sequence[Path]) -> list[LintIssue]:
        """递归加载 `dirs` 下的所有 `*.yaml`；返回加载期发现的问题（不 raise）。"""
        self._venues = {}
        self._file_of = {}
        self._load_issues = []

        for raw_dir in dirs:
            base_dir = Path(raw_dir)
            if not base_dir.is_dir():
                continue

            ids_in_this_dir: dict[str, Path] = {}
            for yaml_path in sorted(base_dir.rglob("*.yaml")):
                spec, issues = self._load_one_file(yaml_path)
                self._load_issues.extend(issues)
                if spec is None:
                    continue

                existing = ids_in_this_dir.get(spec.id)
                if existing is not None:
                    self._load_issues.append(
                        LintIssue(
                            file=str(yaml_path),
                            venue_id=spec.id,
                            field="id",
                            message=(
                                f"id '{spec.id}' 在同一目录内重复定义"
                                f"（已在 '{existing}' 定义，此文件被忽略）"
                            ),
                        )
                    )
                    continue
                ids_in_this_dir[spec.id] = yaml_path

                stem_normalized = yaml_path.stem.replace("-", "_")
                if stem_normalized != spec.id:
                    self._load_issues.append(
                        LintIssue(
                            file=str(yaml_path),
                            venue_id=spec.id,
                            field="id",
                            message=(
                                f"文件名 '{yaml_path.stem}' 归一（kebab→snake）后为 "
                                f"'{stem_normalized}'，与 id '{spec.id}' 不一致"
                            ),
                        )
                    )

                self._venues[spec.id] = spec
                self._file_of[spec.id] = str(yaml_path)

        return list(self._load_issues)

    def _load_one_file(self, path: Path) -> tuple[VenueSpec | None, list[LintIssue]]:
        """解析单个 YAML 文件为 `VenueSpec`；失败时返回 `(None, issues)`。"""
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return None, [
                LintIssue(
                    file=str(path),
                    venue_id=None,
                    field="<yaml>",
                    message=f"文件读取失败（{type(exc).__name__}）: {exc}",
                )
            ]

        try:
            raw = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            return None, [
                LintIssue(
                    file=str(path), venue_id=None, field="<yaml>", message=f"YAML 解析失败: {exc}"
                )
            ]

        if not isinstance(raw, dict):
            return None, [
                LintIssue(
                    file=str(path),
                    venue_id=None,
                    field="<yaml>",
                    message=f"YAML 顶层必须是映射（object），实际是 {type(raw).__name__}",
                )
            ]

        try:
            spec = VenueSpec(**raw)
        except ValidationError as exc:
            raw_id = raw.get("id")
            venue_id = raw_id if isinstance(raw_id, str) else None
            issues = [
                LintIssue(
                    file=str(path),
                    venue_id=venue_id,
                    field=".".join(str(part) for part in err["loc"]) or "<root>",
                    message=err["msg"],
                )
                for err in exc.errors()
            ]
            return None, issues

        return spec, []

    # -- 校验 ------------------------------------------------------------

    def lint(self) -> list[LintIssue]:
        """语义校验（adapter 注册/auth 兼容/issn）叠加加载期的结构性问题。"""
        issues = list(self._load_issues)
        for venue_id, spec in self._venues.items():
            file = self._file_of.get(venue_id, "")
            issues.extend(self._lint_adapter_refs(file, venue_id, spec))
            issues.extend(self._lint_issn(file, venue_id, spec))
        return issues

    def _lint_adapter_refs(self, file: str, venue_id: str, spec: VenueSpec) -> list[LintIssue]:
        issues: list[LintIssue] = []

        # metadata_source 分离语义（D-005，plan §2-2）：None = 沿用 adapter 自身（不校验）。
        # 声明了值时须已注册；且当它与 fulltext_source 不同（真"元数据主干"分离，如
        # jfe: crossref≠elsevier_sd）时，其 family 须为 aggregator——旧式同源写法
        # （metadata_source==fulltext_source，既有全部 venue 皆此形态）不触发 aggregator 约束。
        meta_src = spec.metadata_source
        if meta_src is not None:
            meta_adapter = self._adapters.get(meta_src)
            if meta_adapter is None:
                issues.append(
                    LintIssue(
                        file=file,
                        venue_id=venue_id,
                        field="metadata_source",
                        message=f"未注册的 adapter: {meta_src!r}",
                    )
                )
            elif meta_src != spec.fulltext_source and meta_adapter.family != "aggregator":
                issues.append(
                    LintIssue(
                        file=file,
                        venue_id=venue_id,
                        field="metadata_source",
                        message=(
                            f"metadata_source '{meta_src}'（family={meta_adapter.family!r}）"
                            f"与 fulltext_source '{spec.fulltext_source}' 分离时须为 aggregator"
                            "（D-005 元数据主干分离语义）"
                        ),
                    )
                )

        fulltext_adapter = self._adapters.get(spec.fulltext_source)
        if fulltext_adapter is None:
            issues.append(
                LintIssue(
                    file=file,
                    venue_id=venue_id,
                    field="fulltext_source",
                    message=f"未注册的 adapter: {spec.fulltext_source!r}",
                )
            )
        elif (
            _AUTH_LEVEL_ORDER[spec.auth.level]
            < _AUTH_LEVEL_ORDER[fulltext_adapter.auth_requirement]
        ):
            issues.append(
                LintIssue(
                    file=file,
                    venue_id=venue_id,
                    field="auth.level",
                    message=(
                        f"auth.level={spec.auth.level.value!r} 低于 fulltext_source "
                        f"'{spec.fulltext_source}' 要求的 "
                        f"{fulltext_adapter.auth_requirement.value!r}"
                    ),
                )
            )

        return issues

    def _lint_issn(self, file: str, venue_id: str, spec: VenueSpec) -> list[LintIssue]:
        if spec.kind != "journal":
            return []

        issn_value = spec.identifiers.get("issn")
        if not issn_value:
            return [
                LintIssue(
                    file=file,
                    venue_id=venue_id,
                    field="identifiers.issn",
                    message="kind=journal 必须提供非空的 identifiers.issn（D-015）",
                )
            ]

        if not isinstance(issn_value, list):
            return [
                LintIssue(
                    file=file,
                    venue_id=venue_id,
                    field="identifiers.issn",
                    message=f"identifiers.issn 必须是列表，实际是 {type(issn_value).__name__}",
                )
            ]

        issues = []
        for index, item in enumerate(issn_value):
            if not isinstance(item, str) or not _ISSN_PATTERN.match(item):
                issues.append(
                    LintIssue(
                        file=file,
                        venue_id=venue_id,
                        field=f"identifiers.issn[{index}]",
                        message=f"issn 格式不合法: {item!r}（应匹配 ^\\d{{4}}-\\d{{3}}[\\dX]$）",
                    )
                )
        return issues

    # -- 查询 ------------------------------------------------------------

    def get(self, venue_id: str) -> VenueSpec:
        """按 id 取 venue；未知 id 抛 `CrawlerError(CONFIG)`。"""
        try:
            return self._venues[venue_id]
        except KeyError:
            raise CrawlerError(ErrorClass.CONFIG, f"unknown venue_id: {venue_id!r}") from None

    def route(self, venue_id: str) -> Route:
        """把 venue_id 解析为绑定结果（design/02 §4）；未知引用抛 `CrawlerError(CONFIG)`。"""
        spec = self.get(venue_id)

        # metadata_source=None（D-005 默认）→ 沿用 adapter 自身：元数据由 fulltext_source 的
        # 平台 adapter 兼任（既有同源写法与此等价）。声明了值时按声明解析。
        metadata_source = (
            spec.metadata_source if spec.metadata_source is not None else spec.fulltext_source
        )
        try:
            metadata_adapter = self._adapters[metadata_source]
        except KeyError:
            raise CrawlerError(
                ErrorClass.CONFIG,
                f"venue {venue_id!r} 的 metadata_source 未注册: {metadata_source!r}",
            ) from None

        try:
            fulltext_adapter = self._adapters[spec.fulltext_source]
        except KeyError:
            raise CrawlerError(
                ErrorClass.CONFIG,
                f"venue {venue_id!r} 的 fulltext_source 未注册: {spec.fulltext_source!r}",
            ) from None

        rate_overrides: dict[str, float] = {}
        rpm = spec.rate_limit.requests_per_minute
        if rpm is not None:
            # 每域限速覆盖以 fulltext_adapter 主域为键；domains 为空元组（畸形 adapter）
            # 时无键可用，早失败为 CONFIG（同上文两处未注册引用的处置），避免裸 IndexError。
            if not fulltext_adapter.domains:
                raise CrawlerError(
                    ErrorClass.CONFIG,
                    f"venue {venue_id!r} 声明了 rate_limit，但 fulltext_source "
                    f"{spec.fulltext_source!r} 的 domains 为空，无主域可登记限速",
                )
            rate_overrides[fulltext_adapter.domains[0]] = rpm

        return Route(
            venue=spec,
            metadata_adapter=metadata_adapter,
            fulltext_adapter=fulltext_adapter,
            auth_profile=spec.auth.provider_hint,
            rate_overrides=rate_overrides,
        )

    def all(self) -> list[VenueSpec]:
        """全部已加载 venue，按 id 排序（确定性输出）。"""
        return [self._venues[venue_id] for venue_id in sorted(self._venues)]


__all__ = ["LintIssue", "Route", "VenueRegistry"]
