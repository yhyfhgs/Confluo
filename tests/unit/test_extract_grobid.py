"""GROBID 客户端 / TEI 消费口径 / §7.2 处置矩阵逐行（design/12 §7、§10-3）。

离线载体（§8.3）：`grobid_url` 指向一个**假 URL**，`HttpClient(transport=MockTransport(...))`
注入，handler 按路径分派 `isalive`/`version`/`processFulltextDocument`——矩阵逐行可测，
**零真实 GROBID、零网络**。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from helpers.minipdf import make_text_pdf
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.pipeline.extract import (
    REASON_BAD_TEI,
    REASON_EMPTY_TEI,
    REASON_TIMEOUT,
    REASON_UNREACHABLE,
    SUFFIX_TEI,
    GrobidRuntime,
    GrobidUnavailable,
    parse_tei,
)

BASE = "http://grobid.invalid:8070"
_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "grobid"


def tei(name: str) -> str:
    return (_FIXTURES / f"{name}.tei.xml").read_text(encoding="utf-8")


def make_runtime(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    sleeps: list[float] | None = None,
) -> GrobidRuntime:
    return GrobidRuntime(
        client=HttpClient(user_agent="test/1.0", transport=httpx.MockTransport(handler)),
        base_url=BASE,
        sleeper=(sleeps.append if sleeps is not None else (lambda _s: None)),
    )


def alive_handler(
    process: Callable[[httpx.Request], httpx.Response],
    *,
    version: str = "0.8.1",
) -> Callable[[httpx.Request], httpx.Response]:
    """探活/版本恒 200 的分派器；`processFulltextDocument` 由入参决定。"""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/api/isalive"):
            return httpx.Response(200, text="true")
        if path.endswith("/api/version"):
            return httpx.Response(200, text=version)
        if path.endswith("/api/processFulltextDocument"):
            return process(request)
        return httpx.Response(404, text="no route")

    return handler


def form_fields(request: httpx.Request) -> dict[str, str]:
    """从 multipart 请求体里取普通表单字段（供 consolidate 三参数断言）。"""
    body = request.content.decode("latin-1")
    pattern = r'name="([^"]+)"\r\n\r\n(.*?)\r\n--'
    return dict(re.findall(pattern, body, flags=re.S))


def source_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "paper.pdf"
    path.write_bytes(make_text_pdf("baseline body text that pypdf can read"))
    return path


# -- TEI 消费口径（§7.3）------------------------------------------------------------------


def test_parse_tei_takes_visible_text_not_xml_source() -> None:
    produced = parse_tei(tei("full"), version="0.8.1")
    assert produced.extractor == "grobid" and produced.suffix == SUFFIX_TEI
    assert produced.text == tei("full")  # TEI **原样**落盘（结构化产物即交付物）
    # char_count 取 <text> 可见文本，**不是** XML 源码长度——否则该维度跨 extractor
    # 失去可比性，全序会系统性偏袒 TEI。
    assert 0 < produced.char_count < len(produced.text)
    assert produced.lang == "en"
    assert produced.title == "Deterministic Extraction of Scholarly Full Text"


def test_parse_tei_rejects_malformed_xml() -> None:
    with pytest.raises(GrobidUnavailable) as excinfo:
        parse_tei("<TEI><unclosed>", version="0.8.1")
    assert excinfo.value.reason == REASON_BAD_TEI and excinfo.value.remember is False


def test_parse_tei_rejects_valid_xml_that_is_not_tei() -> None:
    with pytest.raises(GrobidUnavailable) as excinfo:
        parse_tei("<html><body>nope</body></html>", version="0.8.1")
    assert excinfo.value.reason == REASON_BAD_TEI


def test_parse_tei_header_only_is_empty_product_not_success() -> None:
    """§6.1 P0-2：合法 TEI 但可见文本为零 ⇒ **无有效产出**，绝不返回一个 rank 2 的空产物。"""
    with pytest.raises(GrobidUnavailable) as excinfo:
        parse_tei(tei("header_only"), version="0.8.1")
    assert excinfo.value.reason == REASON_EMPTY_TEI and excinfo.value.remember is False


# -- 请求形态（§2.1 机器判据）-------------------------------------------------------------


def test_consolidate_parameters_are_all_zero(tmp_path: Path) -> None:
    """三个 `consolidate*` 参数**均须显式为 0**——漏一个就漏一条外网通道（AC-0 邻域）。

    GROBID 的 consolidation 会代为访问 biblio-glutton/Crossref，开启即在用户不知情下从
    extract 阶段发出外网请求，越过本项目的限速/预算/FetchLog 全部记账面；且不得依赖
    GROBID 的默认值（其默认值随版本变动过）。
    """
    seen: dict[str, str] = {}

    def process(request: httpx.Request) -> httpx.Response:
        seen.update(form_fields(request))
        assert request.headers["accept"] == "application/xml"
        assert b'name="input"' in request.content  # multipart 字段名固定为 input
        return httpx.Response(200, text=tei("full"))

    runtime = make_runtime(alive_handler(process))
    runtime.extractor().extract(source_pdf(tmp_path))
    assert seen["consolidateHeader"] == "0"
    assert seen["consolidateCitations"] == "0"
    assert seen["consolidateFunders"] == "0"


def test_probe_version_feeds_extractor_version(tmp_path: Path) -> None:
    runtime = make_runtime(
        alive_handler(lambda _r: httpx.Response(200, text=tei("full")), version="0.8.1")
    )
    assert runtime.extractor().version == "0.8.1"
    assert runtime.extractor().extract(source_pdf(tmp_path)).extractor_ver == "0.8.1"


def test_probe_runs_once_per_run(tmp_path: Path) -> None:
    """**每轮一次**前置探活（不是每篇）：第二次取抽取器不再打 isalive/version。"""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return alive_handler(lambda _r: httpx.Response(200, text=tei("full")))(request)

    runtime = make_runtime(handler)
    runtime.extractor()
    runtime.extractor()
    assert [p for p in calls if "isalive" in p] == ["/api/isalive"]
    assert [p for p in calls if "version" in p] == ["/api/version"]


def test_version_endpoint_failure_degrades_to_unknown() -> None:
    """探活成功但版本端点失败 → `"unknown"`（§7.2 末段）；不阻塞 GROBID 路径。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/isalive"):
            return httpx.Response(200, text="true")
        return httpx.Response(500, text="boom")

    runtime = make_runtime(handler)
    assert runtime.extractor().version == "unknown"


def test_json_version_payload_is_parsed() -> None:
    runtime = make_runtime(
        alive_handler(lambda _r: httpx.Response(200), version='{"version": "0.8.2"}')
    )
    assert runtime.extractor().version == "0.8.2"


# -- §7.2 处置矩阵逐行 ---------------------------------------------------------------------


def test_probe_failure_remembers_for_the_whole_run() -> None:
    """探活失败（服务未起）→ 整轮降级并**记忆**：逐篇重试是纯空转。"""
    runtime = make_runtime(lambda _r: httpx.Response(503, text="down"))
    with pytest.raises(GrobidUnavailable) as excinfo:
        runtime.extractor()
    assert excinfo.value.reason == REASON_UNREACHABLE and excinfo.value.remember is True
    assert runtime.disabled is True


@pytest.mark.parametrize(
    ("exc", "reason", "remember"),
    [
        (httpx.ReadTimeout("slow"), REASON_TIMEOUT, False),
        (httpx.ConnectError("gone"), REASON_UNREACHABLE, True),
    ],
)
def test_transport_failures_are_split_by_detail(
    tmp_path: Path, exc: Exception, reason: str, remember: bool
) -> None:
    """判别键 = `CrawlerError.detail`：读超时 per-文档（不记忆）；连接失败＝服务不在了（记忆）。

    二者 `error_class` 同为 TRANSIENT 但**并非不可区分**——`http.py` 的两个 except 分支给了
    确定性判别位（`TimeoutException` → `detail="timeout"`；其余 `HTTPError` → 异常类名）。
    """

    def process(_request: httpx.Request) -> httpx.Response:
        raise exc

    runtime = make_runtime(alive_handler(process))
    extractor = runtime.extractor()
    with pytest.raises(GrobidUnavailable) as excinfo:
        extractor.extract(source_pdf(tmp_path))
    assert excinfo.value.reason == reason
    assert excinfo.value.remember is remember


def test_503_is_retried_once_then_degrades(tmp_path: Path) -> None:
    """503 = GROBID 的队列背压信号：退避重试一次（经注入 sleeper），再 503 则降级。"""
    sleeps: list[float] = []
    attempts: list[int] = []

    def process(_request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(503, text="queue full")

    runtime = make_runtime(alive_handler(process), sleeps=sleeps)
    extractor = runtime.extractor()
    with pytest.raises(GrobidUnavailable) as excinfo:
        extractor.extract(source_pdf(tmp_path))
    assert len(attempts) == 2, "503 只重试一次（不做指数三退：本地批量堆积无意义）"
    assert sleeps == [5.0]
    assert excinfo.value.reason == "grobid_http_503" and excinfo.value.remember is False


def test_503_retry_can_succeed(tmp_path: Path) -> None:
    responses = [httpx.Response(503, text="queue"), httpx.Response(200, text=tei("full"))]

    def process(_request: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    runtime = make_runtime(alive_handler(process), sleeps=[])
    assert runtime.extractor().extract(source_pdf(tmp_path)).char_count > 0


def test_404_remembers_and_hints_at_url(tmp_path: Path) -> None:
    runtime = make_runtime(alive_handler(lambda _r: httpx.Response(404, text="nope")))
    extractor = runtime.extractor()
    with pytest.raises(GrobidUnavailable) as excinfo:
        extractor.extract(source_pdf(tmp_path))
    assert excinfo.value.reason == "grobid_http_404" and excinfo.value.remember is True
    assert "grobid_url" in excinfo.value.hint


def test_other_non_200_degrades_without_memory(tmp_path: Path) -> None:
    runtime = make_runtime(alive_handler(lambda _r: httpx.Response(500, text="boom")))
    extractor = runtime.extractor()
    with pytest.raises(GrobidUnavailable) as excinfo:
        extractor.extract(source_pdf(tmp_path))
    assert excinfo.value.reason == "grobid_http_500" and excinfo.value.remember is False


def test_bad_tei_body_degrades_without_memory(tmp_path: Path) -> None:
    runtime = make_runtime(alive_handler(lambda _r: httpx.Response(200, text="<not-xml")))
    extractor = runtime.extractor()
    with pytest.raises(GrobidUnavailable) as excinfo:
        extractor.extract(source_pdf(tmp_path))
    assert excinfo.value.reason == REASON_BAD_TEI and excinfo.value.remember is False


def test_missing_source_file_still_raises_integrity(tmp_path: Path) -> None:
    """GROBID 路径同样遵守 §4.1：文件不存在 → `INTEGRITY`，不是降级。"""
    runtime = make_runtime(alive_handler(lambda _r: httpx.Response(200, text=tei("full"))))
    extractor = runtime.extractor()
    with pytest.raises(CrawlerError) as excinfo:
        extractor.extract(tmp_path / "missing.pdf")
    assert excinfo.value.error_class is ErrorClass.INTEGRITY


# -- `HttpClient.post_multipart` 纯附加扩展（§7.1）----------------------------------------


def test_post_multipart_goes_through_the_same_error_mapping() -> None:
    """与 `post_json` **同构地走 `_request`**：状态码→CrawlerError 映射逐字相同。"""
    client = HttpClient(
        user_agent="t/1", transport=httpx.MockTransport(lambda _r: httpx.Response(401, text="x"))
    )
    with pytest.raises(CrawlerError) as excinfo:
        client.post_multipart(f"{BASE}/x", files={"input": ("a.pdf", b"%PDF-", "application/pdf")})
    assert excinfo.value.error_class is ErrorClass.AUTH_EXPIRED
    assert excinfo.value.status_code == 401


def test_post_multipart_sends_files_and_form_data() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(form_fields(request))
        assert b"%PDF-" in request.content
        return httpx.Response(200, content=b"<ok/>")

    client = HttpClient(user_agent="t/1", transport=httpx.MockTransport(handler))
    body = client.post_multipart(
        f"{BASE}/x",
        files={"input": ("a.pdf", b"%PDF-1.4", "application/pdf")},
        data={"k": "v"},
        accept="application/xml",
    )
    assert body == b"<ok/>"
    assert seen["k"] == "v"


def test_get_paths_unchanged_by_the_extension() -> None:
    """回归：既有 GET 三方法签名/行为零改动（`files`/`form_data` 缺省即未提供）。"""
    client = HttpClient(
        user_agent="t/1", transport=httpx.MockTransport(lambda _r: httpx.Response(200, text="ok"))
    )
    assert client.get_text(f"{BASE}/x") == "ok"
    assert client.get_bytes(f"{BASE}/x") == b"ok"
