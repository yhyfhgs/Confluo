"""Elsevier ScienceDirect 在线冒烟（T3 committed 层；design/adapters/elsevier-sd.md §7）。

默认经 `addopts = -m 'not online'` 排除；显式 `uv run pytest tests/online -m online` 才跑。
硬预算 `MAX_REAL_REQUESTS = 5`（elsevier-sd.md §7：committed 在线冒烟 ≤5 req——**区别于**
T7b runbook 真实 key 窗 ≤40 req，两层预算独立，B-m9）。

**按 key 存在性 skip 门控（诚实 skip，不伪通过）**：Elsevier API key 缺失 = BLOCKER-1（机构
订阅关联、非商业；申请周期 1–2 周）——`pytest.mark.skipif` 而非无条件 skip：无 key 时**收集
但标记 skip**，供 CI/本地一眼看出"存在但未跑"（canary 层同步 NotImplementedError→SKIP）。

**本文件按任务契约"只写不跑"**：随 T3 一并落盘，未在本次实现里实际执行（Elsevier key 未到手，
且超出"零真实网络"实现门禁）。key 到手后的操作者检查单（→ 归 T7b runbook `tests/manual/
elsevier_runbook.md` 执行 + records 留痕）：

1. 设 `PAPER_CRAWLER_ELSEVIER_API_KEY`（+ 可选 `PAPER_CRAWLER_ELSEVIER_INSTTOKEN`）为真实值。
2. `uv run pytest tests/online/test_elsevier_smoke.py -m online -v`。
3. 核对 `HEALTHCHECK_CAPTURE` / `ENTITLEMENT_CAPTURE` 行：
   - entitlement 真实字段名/类型是否与 parse 假设（`entitled` bool）一致——若不符，按 elsevier-sd.md
     §2"⚠ 待核验"修正 `parse.py` 字段名 + fixtures 01/02，UPDATE_GOLDEN。
   - 若该 key 的机构订阅 JFE → entitled=true → fetch 得 `%PDF`；若未订阅 → NO_ENTITLEMENT（AC-4.3
     正常降级，非失败）。
4. **配额头审计**（AC-4.4）：`X-RateLimit-*`/`X-ELS-Status` 头在冻结 `HttpClient.get_bytes`
   （只回 body、不暴露 headers）下**本层不可达**——移交 T7b runbook 用原生 curl/httpx 审计。
5. 执行结果归档 `docs/testing/records/`（D-019 惯例）。

覆盖面（≤5 req）：healthcheck entitlement 探测（1）+ 单篇 JFE resolve(entitlement 1)+fetch(1)。
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from online.conftest import RealRequestBudget
from paper_crawler.adapters.elsevier_sd.adapter import (
    _HEALTHCHECK_DOI,
    ElsevierScienceDirectAdapter,
)
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.types import AssetPlan, PaperStub, VenueSpec
from paper_crawler.useragent import build_user_agent

MAX_REAL_REQUESTS = 5

_ELSEVIER_API_KEY = os.environ.get("PAPER_CRAWLER_ELSEVIER_API_KEY", "").strip()
_ELSEVIER_INSTTOKEN = os.environ.get("PAPER_CRAWLER_ELSEVIER_INSTTOKEN", "").strip()

_SKIP_REASON = "PAPER_CRAWLER_ELSEVIER_API_KEY 未设——BLOCKER-1（Elsevier key 申请中），诚实 skip"

# 单篇 JFE 取回锚点（AC-4.1 核心场景）：真实 Journal of Financial Economics DOI。
_JFE_DOI = _HEALTHCHECK_DOI


def _dedicated_headers() -> dict[str, str]:
    """凭证隔离：X-ELS-APIKey(+可选 X-ELS-Insttoken) 头（专属 client，不与他 adapter 共享）。"""
    headers = {"X-ELS-APIKey": _ELSEVIER_API_KEY}
    if _ELSEVIER_INSTTOKEN:
        headers["X-ELS-Insttoken"] = _ELSEVIER_INSTTOKEN
    return headers


@pytest.fixture
def elsevier_client() -> Iterator[HttpClient]:
    """真实 HttpClient：携 `X-ELS-APIKey` 头（凭证隔离——只在本文件独立测试进程内构造，
    不与其它 adapter 共享，同装配期专属 client 隔离原则，见 adapter `set_http_client` docstring）。
    """
    client = HttpClient(
        user_agent=build_user_agent(os.environ.get("PAPER_CRAWLER_CONTACT_EMAIL")),
        extra_headers=_dedicated_headers(),
    )
    try:
        yield client
    finally:
        client.close()


def _jfe_venue() -> VenueSpec:
    return VenueSpec(
        id="jfe",
        kind="journal",
        names={"full": "Journal of Financial Economics", "aliases": ["JFE"]},
        field=["finance"],
        identifiers={"issn": ["0304-405X"]},
        metadata_source="crossref",
        fulltext_source="elsevier_sd",
        auth={"level": "institutional", "provider_hint": "elsevier"},
    )


class _CaptureIO:
    """最小 `FetchIO`：缓冲字节供 `%PDF` 魔数断言（committed 层不落盘）。"""

    def __init__(self) -> None:
        self.data = b""

    def write_stream(self, chunks: object) -> tuple[int, str]:
        import hashlib

        buf = bytearray()
        for chunk in chunks:  # type: ignore[attr-defined]
            buf.extend(chunk)
        self.data = bytes(buf)
        return len(self.data), hashlib.sha256(self.data).hexdigest()


def _adapter(client: HttpClient) -> ElsevierScienceDirectAdapter:
    adapter = ElsevierScienceDirectAdapter(http=client)
    adapter.set_api_key(_ELSEVIER_API_KEY)
    return adapter


@pytest.mark.online
@pytest.mark.skipif(not _ELSEVIER_API_KEY, reason=_SKIP_REASON)
def test_healthcheck_entitlement_probe_when_key_configured(
    elsevier_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：有 key 时 JFE DOI 的 entitlement 探测 healthcheck（§3.3）。"""
    adapter = _adapter(elsevier_client)
    real_request_budget.spend(1)

    report = adapter.healthcheck()

    print(
        f"HEALTHCHECK_CAPTURE doi={_HEALTHCHECK_DOI!r} "
        f"healthy={report.healthy} detail={report.detail!r}"
    )
    assert "unreachable" not in report.detail, f"elsevier unreachable: {report.detail}"
    assert report.healthy, (
        f"healthcheck unhealthy against anchor DOI {_HEALTHCHECK_DOI!r} — see module docstring "
        f"UPDATE_GOLDEN steps before assuming a code bug: detail={report.detail!r}"
    )


@pytest.mark.online
@pytest.mark.skipif(not _ELSEVIER_API_KEY, reason=_SKIP_REASON)
def test_resolve_and_fetch_single_jfe(
    elsevier_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """≤2 请求：单篇 JFE resolve（entitlement 预检）→（有权则）fetch → `%PDF` 魔数（AC-4.1）。

    未订阅 JFE 的 key → resolve 抛 `NO_ENTITLEMENT`（AC-4.3 正常降级，非失败）：本用例据实
    记录并通过（entitlement 语义活验的一部分）。有权 → fetch 断言首字节 `%PDF`。
    """
    adapter = _adapter(elsevier_client)
    paper = PaperStub(title="A JFE paper", identifiers=(("doi", _JFE_DOI),))

    real_request_budget.spend(1)  # resolve 的 entitlement 预检
    try:
        plans = adapter.resolve_assets(_jfe_venue(), paper)
    except CrawlerError as exc:
        if exc.error_class is ErrorClass.NO_ENTITLEMENT:
            print(
                f"ENTITLEMENT_CAPTURE doi={_JFE_DOI!r} entitled=false (AC-4.3 降级，非失败): {exc}"
            )
            return
        raise

    print(
        f"ENTITLEMENT_CAPTURE doi={_JFE_DOI!r} entitled=true plans={[p.kind.value for p in plans]}"
    )
    assert plans, "entitled 但 resolve 未产 AssetPlan"
    pdf_plan: AssetPlan = plans[0]

    real_request_budget.spend(1)  # fetch
    io = _CaptureIO()
    result = adapter.fetch_asset(pdf_plan, io)
    print(f"FETCH_CAPTURE bytes={result.bytes_written} head={io.data[:8]!r}")
    assert result.ok
    assert io.data.startswith(b"%PDF"), f"JFE 取回非 PDF（首字节 {io.data[:8]!r}）"
