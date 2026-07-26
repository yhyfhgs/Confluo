"""OpenAlex `enrich_batch` 主体（design/adapters/aggregators.md §5.3；plan §2-5 T6）。

**能力面**：`capabilities = Capability(0)`（空集——无 DISCOVER/ENUMERATE/RESOLVE/FETCH/
SEARCH）。本 adapter **不进** `SourceAdapter` 五方法冻结协议的取回语义，不参与
`crawler pull` 六阶段主流程、无任何 AC 依赖它（AC-3.5 五刊全史由 crossref 独立完成，
plan §2-5）。改经冻结协议之外的 duck-typed `enrich_batch`（`adapter.EnrichmentSource`
协议）——由 `crawler enrich` CLI 驱动，扫库内带 `doi` identifier 的 paper、分批查询、
经 `MergeEngine.ingest` 回注（字段级来源优先级收敛天然补缺不覆盖，`SOURCE_PRIORITY`
表 openalex 位阶低于 crossref/dblp，merge.py）。

**批大小 = URL 长度安全上限自定**（`_batch_dois`，§4/§5.3"filter=doi: OR 拼批查"）：
OpenAlex 官方未文档化 OR 项数上限，真实约束是**整条请求 URL 的长度**——`filter` 参数
值需 `urlencode()`（DOI 内的 `/`、`:` 等字符会被编码膨胀，如 `/`→`%2F` 由 1 字符变
3 字符）。`_MAX_URL_CHARS=2000` 是常见的跨浏览器/反向代理/CDN"安全线下限"经验值
（历史上 IE 曾硬顶 2083；现代服务器/CDN 普遍支持 4–8KB+ 但并非处处保证，2000 是较
保守、被广泛引用的下限，本身非站点事实、不带 [LIVE]/[DOCS] 标注，是工程保守惯例）。
`_batch_dois` 按**精确编码后长度**（`quote_plus`，与 `urlencode()` 默认编码函数一致）
逐条累加装箱，任一批超过该上限前收口——保证生成的每条请求 URL 严格不超限，不是"估个
平均值乘批大小"的近似值。另加 `_MAX_BATCH_ITEMS=100` 作次要保守上限（防御 DOI 普遍
极短的退化场景——避免单批 OR 项数远超"典型批查"直觉、撞上未文档化的服务端解析上限）。

**预算护栏**（§4 伪代码，`budget.py` 落地）：`enrich_batch` 内部循环，每次真实请求前
检查 `state.spent_usd >= daily_budget_usd`——命中即熔断 `raise CrawlerError
(RATE_LIMITED, ...)`，不发这次请求（未消费的批次直接放弃，不做部分退化）；请求成功后
按响应 `meta.cost_usd` 累计持久化。服务端 402（credit 耗尽）在 `HttpClient` 冻结映射
下落入"其余 4xx→CONFIG"分支（§2.1 表未单列 402，不可改动冻结映射）——本层捕获后按
`exc.status_code == 402` 精确重分类为 `RATE_LIMITED`，与预算熔断同语义（"明日恢复"）。
`CrawlerError.status_code` 是 `http.py` 状态映射携带的**结构化状态码**（auth-framework §6，
检查单 #4 闭合，T2 落地），非异常消息文本——契约稳定，不随消息措辞变动漂移。

**healthcheck 的 key 门控**（不同于 `enrich_batch` 可匿名运行）：未配置 key → `raise
NotImplementedError("openalex key 未配置")` → `crawler canary` 现有语义显示 SKIP；
有 key → 固定 `GET /works/W{id}` 结构性/精确比对。这一门控收紧于设计稿 §5.3"匿名即可
探测"的原始表述——统一 openalex/s2 两者"canary 默认不因未配置而消耗真实请求/预算"
的产品取舍（任务书 T6 卡片口径），使 `crawler canary`（可能被 cron/CI 高频调用）默认
不因"用户根本没打算用这个可选补充源"而悄悄计入 openalex 每日 credit 消耗。
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import quote_plus, urlencode

from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.adapters.openalex import budget, parse
from paper_crawler.config import resolve_home
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.obslog import log_event
from paper_crawler.types import AuthLevel, Capability, HealthReport, PaperStub, RatePolicy
from paper_crawler.useragent import build_user_agent

# --- 端点与常量（§5.3 表）---------------------------------------------------------------------

_API_ROOT = "https://api.openalex.org"

# 批大小的 URL 长度安全上限（模块 docstring 已详论证）。
_MAX_URL_CHARS = 2000
_MAX_BATCH_ITEMS = 100
# `"https://api.openalex.org/works?filter=" + quote_plus("doi:")`：批内首个 DOI 前的
# 固定前缀长度（`api_key` 若注入会追加，但 `_batch_dois` 只需一个**下限安全**的固定
# 前缀估计——不含 api_key 时的前缀更短，故按不含 api_key 计算，比含 api_key 的真实
# 情形更保守，仍在安全线内；也避免让"是否注入了 key"影响批大小这一测试无关变量）。
_FILTER_PREFIX = f"{_API_ROOT}/works?" + urlencode({"filter": "doi:"})
_OR_SEP_ENCODED_LEN = len(quote_plus("|"))  # OR 分隔符编码后长度（用于批内追加项估计）

_CONTACT_EMAIL_ENV = "PAPER_CRAWLER_CONTACT_EMAIL"
_PLACEHOLDER_EMAIL = "anonymous@paper-crawler.invalid"

_DEFAULT_DAILY_BUDGET_USD = 0.50  # §4：保守默认（≈ 无 key 5000 credits 的一半量级）
_STATE_SUBPATH = ("state", "openalex-budget.json")  # <config-home>/state/openalex-budget.json

# healthcheck 固定 W-id（design §5.3/§7；真值 [PENDING]，留待在线冒烟 UPDATE_GOLDEN 捕获）。
# W2741809807 ="The state of OA"（Piwowar et al. 2018）——常被引用作 OpenAlex/OA 相关
# 文档示例的知名条目，选作结构性探测锚点；title 精确串未经本次实现的在线核验。
_HEALTHCHECK_ID = "W2741809807"
_HEALTHCHECK_TITLE: str | None = None


def _default_user_agent() -> str:
    email = os.environ.get(_CONTACT_EMAIL_ENV, "").strip() or _PLACEHOLDER_EMAIL
    return build_user_agent(email)


def _batch_dois(dois: Sequence[str]) -> list[list[str]]:
    """按 URL 长度安全上限（+ 次要项数上限）把 `dois` 切分为多个批次（模块 docstring 论证）。

    逐条精确计算 `quote_plus` 编码后长度（与 `urlencode()` 默认编码函数一致，非估算），
    连同 OR 分隔符编码长度一起累加；任一批的下一项会使累计长度超过 `_MAX_URL_CHARS`
    （且当前批非空）即收口开新批。单个 DOI 自身编码后就超限（理论上不会发生——真实
    DOI 远短于 2000 字符——但防止死循环）时该 DOI 独占一批，不无限阻塞其余项。
    """
    batches: list[list[str]] = []
    current: list[str] = []
    current_len = len(_FILTER_PREFIX)
    for doi in dois:
        encoded_len = len(quote_plus(doi))
        added_len = encoded_len + (_OR_SEP_ENCODED_LEN if current else 0)
        would_exceed = current_len + added_len > _MAX_URL_CHARS
        at_item_cap = len(current) >= _MAX_BATCH_ITEMS
        if current and (would_exceed or at_item_cap):
            batches.append(current)
            current = []
            current_len = len(_FILTER_PREFIX)
            added_len = encoded_len  # 新批首项前无 OR 分隔符
        current.append(doi)
        current_len += added_len
    if current:
        batches.append(current)
    return batches


def _works_url(dois: Sequence[str], *, api_key: str | None) -> str:
    params: dict[str, str] = {"filter": "doi:" + "|".join(dois)}
    if api_key:
        params["api_key"] = api_key
    return f"{_API_ROOT}/works?{urlencode(params)}"


def _work_by_id_url(work_id: str, *, api_key: str | None) -> str:
    # §5.3："单条 | GET /works/W{id} | 避免 URL-in-path（代理归一风险）"——用裸 id 路径
    # 段而非把完整 DOI/URL 塞进 path。
    params: dict[str, str] = {}
    if api_key:
        params["api_key"] = api_key
    suffix = f"?{urlencode(params)}" if params else ""
    return f"{_API_ROOT}/works/{work_id}{suffix}"


class OpenAlexAdapter(AdapterBase):
    """OpenAlex 补充层 adapter（`aggregator` family；capabilities 空集，enrich-only）。"""

    adapter_id = "openalex"
    family: AdapterFamily = "aggregator"
    capabilities = Capability(0)
    # 真实护栏是 credit 预算熔断（§4）；此处 req/s 只防意外突发撞上官方 100 req/s 硬顶，
    # 保守取远低于硬顶的 5 req/s（同 crossref"保守取上限"的取值精神）。
    default_rate = RatePolicy(
        requests_per_minute=300.0,
        burst=2,
        source_note=(
            "OpenAlex: 100 req/s 官方硬顶下保守取 5 req/s（真实护栏是每日 credit 预算"
            "熔断，见 budget.py + §4 daily_budget_usd）；"
            "docs/design/adapters/aggregators.md §4/§5.3 [DOCS] 2026-02 计费制官方文档"
        ),
    )
    auth_requirement = AuthLevel.NONE  # key 可选（匿名请求现状 [LIVE] 200）
    domains: tuple[str, ...] = ("api.openalex.org",)

    def __init__(self, http: HttpClient | None = None) -> None:
        # http=None：首次网络调用时惰性自建（同 crossref/dblp 先例）。
        self._http = http
        self._api_key: str | None = None
        self._daily_budget_usd = _DEFAULT_DAILY_BUDGET_USD
        self._state_path: Path | None = None  # None → `_resolve_state_path` 惰性默认

    def set_http_client(self, client: HttpClient) -> None:
        """注入组装好的 `HttpClient`（`adapter.HttpClientConsumer` 协议）。"""
        self._http = client

    def set_api_key(self, key: str | None) -> None:
        """注入可选 API key（`adapter.ApiKeyConsumer` 协议；CLI 装配期传入 config 值）。"""
        self._api_key = key

    def configure_budget(self, *, daily_budget_usd: float, state_path: Path) -> None:
        """注入每日预算上限与状态文件路径（CLI 装配期传入 `Config` 值）。

        未调用本方法时使用保守默认（`_DEFAULT_DAILY_BUDGET_USD` + 惰性默认状态路径
        `<config-home>/state/openalex-budget.json`，经 `config.resolve_home()` 解析——
        与 `Config.load` 的 home 链单一同源、尊重 `$PAPER_CRAWLER_HOME`，D-032），使本
        adapter 脱离 CLI 装配也可独立构造使用（单测/未来其它调用方）。
        """
        self._daily_budget_usd = daily_budget_usd
        self._state_path = state_path

    def _client(self) -> HttpClient:
        if self._http is None:
            self._http = HttpClient(user_agent=_default_user_agent())
        return self._http

    def _resolve_state_path(self) -> Path:
        if self._state_path is not None:
            return self._state_path
        return resolve_home().joinpath(*_STATE_SUBPATH)

    # -- enrich_batch（duck-typed EnrichmentSource；真实网络）------------------------------------

    def enrich_batch(self, dois: Sequence[str]) -> list[PaperStub]:
        """按 DOI 批查 works（`filter=doi:` OR 拼）→ `PaperStub` 列表（§5.3 enrich 通道）。

        去重保序、跳过空串后按 `_batch_dois` 切分；每个内部批次请求前做预算熔断检查
        （命中即 `raise`，放弃本次调用剩余未处理的批次——不做部分让步，模块 docstring
        "预算护栏"段）、请求后把该批次 `meta.cost_usd` 累计入状态文件。
        """
        unique = [doi for doi in dict.fromkeys(dois) if doi]
        if not unique:
            return []
        state_path = self._resolve_state_path()
        stubs: list[PaperStub] = []
        for batch in _batch_dois(unique):
            state = budget.load_state(state_path)
            if state.spent_usd >= self._daily_budget_usd:
                raise CrawlerError(
                    ErrorClass.RATE_LIMITED,
                    "openalex daily budget exhausted; resets next UTC day",
                    detail=f"spent_usd={state.spent_usd} daily_budget_usd={self._daily_budget_usd}",
                )
            data = self._request_works(batch)
            page = parse.parse_works_batch(data)
            budget.add_spend(state_path, page.cost_usd)
            if page.skipped_untitled or page.skipped_no_identifier:
                log_event(
                    "DEBUG",
                    "openalex enrich_batch records skipped",
                    stage="enrich",
                    domain=self.domains[0],
                    skipped_untitled=page.skipped_untitled,
                    skipped_no_identifier=page.skipped_no_identifier,
                )
            stubs.extend(page.stubs)
        return stubs

    def _request_works(self, batch: list[str]) -> bytes:
        url = _works_url(batch, api_key=self._api_key)
        try:
            return self._client().get_bytes(url)
        except CrawlerError as exc:
            # 402 credit 耗尽 → 与本地预算熔断同语义的 RATE_LIMITED（"明日恢复"）。判据是
            # `http.py` 携带的结构化 `status_code`（auth-framework §6），非异常消息文本嗅探
            # ——契约稳定。402 在冻结映射下 error_class=CONFIG，但此处只认 status_code。
            if exc.status_code == 402:
                raise CrawlerError(
                    ErrorClass.RATE_LIMITED,
                    "openalex daily budget exhausted (server 402 credit exhausted)",
                    detail=str(exc),
                ) from exc
            raise

    # `discover_timeline`/`enumerate_issue`/`resolve_assets`/`fetch_asset` 未声明能力
    # （capabilities 空集）——不覆写，沿用 `AdapterBase` 默认 `CapabilityNotSupported`。

    # -- healthcheck（key 门控，模块 docstring）------------------------------------------------

    def healthcheck(self, session: object = None) -> HealthReport:
        """未配置 key → `NotImplementedError`（→canary SKIP）；有 key → 固定查询比对。"""
        if not self._api_key:
            raise NotImplementedError("openalex key 未配置")
        try:
            data = self._client().get_bytes(_work_by_id_url(_HEALTHCHECK_ID, api_key=self._api_key))
        except CrawlerError as exc:
            return HealthReport(
                healthy=False, detail=f"openalex unreachable ({exc.error_class.value}): {exc}"
            )
        try:
            title = parse.parse_single_work_title(data)
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


__all__ = ["OpenAlexAdapter"]
