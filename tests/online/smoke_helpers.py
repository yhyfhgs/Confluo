"""在线冒烟批（pmlr/cvf/acl_anthology/neurips/aaai）共享的两个小工具。

arxiv 冒烟（`test_arxiv_smoke.py`，本批样板）把限速 client 装配与 PDF 首 chunk
探测内联在文件里；本批 5 个 adapter 的装配模式 100% 同构（`register(domains[0])`
+ `alias(domains[1:])`，与 pipeline `route_for` 及 arxiv 会话 client 同机制），故
抽出共享，避免五份逐字重复漂移。arxiv 样板因其三域别名含站点特有主机名
（oaipmh/arxiv.org→export）而保留内联，不在此重构。
"""

from __future__ import annotations

from paper_crawler.http import HttpClient
from paper_crawler.ratelimit import RateLimiter
from paper_crawler.types import RatePolicy
from paper_crawler.useragent import build_user_agent


def make_rate_limited_client(
    *, domains: tuple[str, ...], default_rate: RatePolicy, contact_email: str
) -> HttpClient:
    """装配一个逐请求限速的 `HttpClient`：`domains[0]` 按 adapter `default_rate`
    注册、其余镜像域 alias 到 `domains[0]`（多域共用一份预算，与 pipeline
    `route_for` 的 register+alias 同机制，见 ratelimit.py `alias` docstring）。

    UA 携真实 `mailto:`（D-014）——`contact_email` 由调用方从 `PAPER_CRAWLER_
    CONTACT_EMAIL` env 取（缺失时整文件已在 import 期 skip）。
    """
    limiter = RateLimiter()
    limiter.register(domains[0], default_rate)
    for mirror in domains[1:]:
        limiter.alias(mirror, domains[0])
    return HttpClient(user_agent=build_user_agent(contact_email), rate_limiter=limiter)


def stream_first_chunk(client: HttpClient, url: str, *, min_bytes: int = 8) -> bytes:
    """流式 GET，累积到 `>= min_bytes`（或流自然结束）即关闭生成器中止其余下载，
    返回已读首段字节——`HttpClient` 无 HEAD，用「取首 chunk 断魔数后关流」达成
    HEAD 式的轻量探测（一次真实请求，不拉全 PDF）。

    `stream()` 是惰性生成器：首次迭代才发请求；`.close()` 向暂停在
    `yield from iter_bytes()` 处的生成器抛 `GeneratorExit`，触发底层
    `with client.stream(...)` 退出、释放连接（httpx 支持部分读后提前关流）。
    """
    stream = client.stream(url)
    head = bytearray()
    try:
        for chunk in stream:
            head.extend(chunk)
            if len(head) >= min_bytes:
                break
    finally:
        stream.close()
    return bytes(head)


__all__ = ["make_rate_limited_client", "stream_first_chunk"]
