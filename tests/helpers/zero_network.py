"""零网络 adapter 白名单——`domains == ()` 判定的**单一权威源**（D-035 决策 1）。

放在 `helpers/` 而非某个测试模块里，是因为该判定有**两个**消费方（`tests/unit/
test_adapter_loading.py` 与 `tests/contract/test_adapter_contract.py` 各有一条 domains
断言），两处各写一份集合就会漂移——正是本项目反复踩过的"注册了却没同步"反模式。

**语义是双向的，不是豁免**：`domains == ()` **当且仅当** adapter 属本集合。
- repec 日后若偷偷长出域名 → 打红（零网络性质被**正向锁定**）；
- 任何非本集合的 adapter 若 domains 变空（畸形）→ 照旧打红。

为何不给 repec 挂一个从不请求的占位域名以绕过原断言（D-035 明文否决）：那是为绕过一行
校验而写进代码的**假事实**。同理其 `default_rate.source_note` 如实注明"占位名义"。
"""

from __future__ import annotations

ZERO_NETWORK_ADAPTERS = frozenset({"repec"})


def assert_domains_match_network_face(adapter_id: str, domains: tuple[str, ...]) -> None:
    """按网络面双向断言 `domains`（两个消费方共用，口径不可能漂移）。"""
    assert isinstance(domains, tuple)
    if adapter_id in ZERO_NETWORK_ADAPTERS:
        assert domains == (), f"{adapter_id} 声明零网络（D-035），domains 必须为空元组"
    else:
        assert domains, f"{adapter_id} 非零网络源，domains 不得为空"
    assert all(isinstance(d, str) and d for d in domains)


__all__ = ["ZERO_NETWORK_ADAPTERS", "assert_domains_match_network_face"]
