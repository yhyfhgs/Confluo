"""S2 `enrich_batch` 主体（design/adapters/aggregators.md §5.4；plan §2-5 T6）。

**能力面**：`capabilities = Capability(0)`（空集）。不进 `SourceAdapter` 五方法冻结
协议，不参与 `crawler pull` 六阶段主流程、无任何 AC 依赖它（同 openalex，plan §2-5）。
经 duck-typed `enrich_batch`（`adapter.EnrichmentSource` 协议）由 `crawler enrich` CLI 驱动。

**无 key → 不发任何请求**（D2 [LIVE] 修订：无 key 现症状是单请求被受理但返回 404
"not found"——连已收录 DOI 亦然，非 429；生产必须申请 key 才可用）：`enrich_batch`
在函数入口**直接判定** key 是否配置，未配置立即 `raise CrawlerError(CONFIG, ...)`，
不靠状态码推断、不发出这次注定无意义的请求。

**批查通道**：`POST /graph/v1/paper/batch`（body `{"ids": ["DOI:<doi>", ...]}`，
`fields=` query 显式声明 `title,externalIds,citationCount,tldr,fieldsOfStudy,
openAccessPdf`——S2 稀疏返回，不显式声明的字段不回传，§5.4）。**≤500 id/批**是
官方文档明示的硬性上限（非本层自定的安全边际，区别于 openalex 的 URL 长度自算批量）
——`_chunk` 按固定数量切分，不做动态估算。

**限速**：有 key 统一 1 req/s（官方文档）；`x-api-key` 头经**专属** `HttpClient`
注入（CLI 装配期构造，绝不复用共享 client——见包 `__init__.py` docstring 的凭证
隔离说明）。

**healthcheck 的 key 门控**：无 key → `raise NotImplementedError("s2 key 未配置")`
→ `crawler canary` 现有语义显示 SKIP（精确复用 `canary.py` 的 `NotImplementedError`
→skip 分支，零 canary 改动，§5.4）；有 key → `GET /paper/DOI:{固定DOI}?fields=title`
比对规整化 title，不靠 429/404 判活。
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from urllib.parse import quote, urlencode

from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.adapters.s2 import parse
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.obslog import log_event
from paper_crawler.types import AuthLevel, Capability, HealthReport, PaperStub, RatePolicy
from paper_crawler.useragent import build_user_agent

# --- 端点与常量（§5.4 表）---------------------------------------------------------------------

_API_ROOT = "https://api.semanticscholar.org/graph/v1"
# 官方文档硬性上限（非本层安全边际自算——对照 openalex 的 URL 长度自算批量，见该包
# adapter.py 模块 docstring 的批大小论证段落）。
_MAX_BATCH_SIZE = 500
# 显式声明需要的字段（S2 稀疏返回；title 虽未列入 §5.4 映射表但 PaperStub 必需，见
# parse.py 模块 docstring）。
_FIELDS = "title,externalIds,citationCount,tldr,fieldsOfStudy,openAccessPdf"

_CONTACT_EMAIL_ENV = "PAPER_CRAWLER_CONTACT_EMAIL"
_PLACEHOLDER_EMAIL = "anonymous@paper-crawler.invalid"

# healthcheck 固定 DOI（design §5.4/§7；真值与"有 key 命中"均 [PENDING]，需 key 在线
# 验证——"Attention Is All You Need" transformer 论文，收录状态几无争议，选作探测锚点）。
_HEALTHCHECK_DOI = "10.48550/arXiv.1706.03762"
_HEALTHCHECK_TITLE: str | None = None


def _default_user_agent() -> str:
    email = os.environ.get(_CONTACT_EMAIL_ENV, "").strip() or _PLACEHOLDER_EMAIL
    return build_user_agent(email)


def _batch_url() -> str:
    return f"{_API_ROOT}/paper/batch?{urlencode({'fields': _FIELDS})}"


def _single_paper_url(doi: str) -> str:
    encoded = quote(doi, safe="")
    return f"{_API_ROOT}/paper/DOI:{encoded}?{urlencode({'fields': 'title'})}"


def _chunk(items: Sequence[str], size: int) -> list[list[str]]:
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


class S2Adapter(AdapterBase):
    """Semantic Scholar 补充层 adapter（`aggregator` family；capabilities 空集，enrich-only）。"""

    adapter_id = "s2"
    family: AdapterFamily = "aggregator"
    capabilities = Capability(0)
    default_rate = RatePolicy(
        requests_per_minute=60.0,
        burst=1,
        source_note=(
            "Semantic Scholar Graph API: 有 key 统一 1 req/s（官方文档）；无 key 时 "
            "enrich_batch 直接 CONFIG、不发请求（不消耗本限速预算）；"
            "docs/design/adapters/aggregators.md §4/§5.4 [DOCS]"
        ),
    )
    # 系统层面不强制——由 enrich_batch/healthcheck 各自按 key 存在性判定。
    auth_requirement = AuthLevel.NONE
    domains: tuple[str, ...] = ("api.semanticscholar.org",)

    def __init__(self, http: HttpClient | None = None) -> None:
        # http=None：首次网络调用时惰性自建（无 key 时 enrich_batch 早退，不会走到这里；
        # healthcheck 同样先判 key 才可能触网）。
        self._http = http
        self._api_key: str | None = None

    def set_http_client(self, client: HttpClient) -> None:
        """注入组装好的 `HttpClient`（`adapter.HttpClientConsumer` 协议）。

        **凭证隔离义务在调用方**（CLI 装配期）：有 key 时必须注入携 `x-api-key` 头的
        **专属** client，不得把跨 adapter 共享的匿名 client 传入——本方法自身不校验
        传入 client 是否携带正确的头（无法从 `HttpClient` 反读其内部头，同
        unpaywall email 场景的既有限制），信任调用方遵守包 docstring 的隔离约定。
        """
        self._http = client

    def set_api_key(self, key: str | None) -> None:
        """注入可选 API key（`adapter.ApiKeyConsumer` 协议）。

        本方法只记录 key 值本身（供 `enrich_batch`/`healthcheck` 判定"是否已配置"），
        **不**据此改动 `self._http` 的请求头——`x-api-key` 头必须随专属 client 的构造
        一次性注入（见 `set_http_client` docstring），本方法与 `set_http_client` 的
        调用顺序在 CLI 侧由调用方保证一致（先构造好携正确头的专属 client 再注入）。
        """
        self._api_key = key

    def _client(self) -> HttpClient:
        if self._http is None:
            self._http = HttpClient(user_agent=_default_user_agent())
        return self._http

    # -- enrich_batch（duck-typed EnrichmentSource；真实网络，1 req/s）-----------------------------

    def enrich_batch(self, dois: Sequence[str]) -> list[PaperStub]:
        """无 key → 直接 `CrawlerError(CONFIG)`（不发请求）；有 key → 分批 `POST /paper/batch`。

        `_MAX_BATCH_SIZE=500` 官方硬上限切分；去重保序、跳过空串。单条未命中（数组
        对应位为 `null`）与命中但缺标题的记录经 `parse.BatchResult` 计数、不中断整批
        （非错误，正常结果）。
        """
        if not self._api_key:
            raise CrawlerError(
                ErrorClass.CONFIG,
                "s2 api key 未配置；请在 config.toml [auth.s2] api_key 注入后重试"
                "（生产必须 key，无 key 现症状是 404 not-found，D2）",
            )
        unique = [doi for doi in dict.fromkeys(dois) if doi]
        if not unique:
            return []
        stubs: list[PaperStub] = []
        for batch in _chunk(unique, _MAX_BATCH_SIZE):
            data = self._client().post_json(
                _batch_url(), json_body={"ids": [f"DOI:{doi}" for doi in batch]}
            )
            result = parse.parse_batch_response(data)
            if result.skipped_untitled or result.not_found:
                log_event(
                    "DEBUG",
                    "s2 enrich_batch records skipped/not-found",
                    stage="enrich",
                    domain=self.domains[0],
                    skipped_untitled=result.skipped_untitled,
                    not_found=result.not_found,
                )
            stubs.extend(result.stubs)
        return stubs

    # `discover_timeline`/`enumerate_issue`/`resolve_assets`/`fetch_asset` 未声明能力
    # （capabilities 空集）——不覆写，沿用 `AdapterBase` 默认 `CapabilityNotSupported`。

    # -- healthcheck（key 门控，模块 docstring）------------------------------------------------

    def healthcheck(self, session: object = None) -> HealthReport:
        """未配置 key → `NotImplementedError`（→canary SKIP）；有 key → 固定 DOI 查询比对。"""
        if not self._api_key:
            raise NotImplementedError("s2 key 未配置")
        try:
            data = self._client().get_bytes(_single_paper_url(_HEALTHCHECK_DOI))
        except CrawlerError as exc:
            return HealthReport(
                healthy=False, detail=f"s2 unreachable ({exc.error_class.value}): {exc}"
            )
        try:
            title = parse.parse_single_paper_title(data)
        except CrawlerError as exc:
            return HealthReport(healthy=False, detail=f"canary parse failed: {exc}")

        if _HEALTHCHECK_TITLE is None:
            return HealthReport(healthy=True, detail=f"[PENDING golden] observed title={title!r}")
        if title != _HEALTHCHECK_TITLE:
            return HealthReport(
                healthy=False,
                detail=f"canary drift — title {title!r} != expected {_HEALTHCHECK_TITLE!r}",
            )
        return HealthReport(healthy=True, detail="canary matched (title)")


__all__ = ["S2Adapter"]
