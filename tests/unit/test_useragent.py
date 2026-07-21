"""`paper_crawler.useragent` 单测（D-014 UA 组装；T6-C2 上移中性模块后）。

原挂在 arxiv adapter 下的 `build_user_agent`/`_package_version` 上移中性模块后，
其测试同步迁来（离线，纯字符串组装 + 版本回退）。
"""

from __future__ import annotations

import pytest

from paper_crawler import useragent
from paper_crawler.useragent import build_user_agent


def test_build_user_agent_is_d014_shaped() -> None:
    ua = build_user_agent("me@example.com", version="9.9.9")
    assert ua == "PaperCrawler/9.9.9 (personal research; mailto:me@example.com)"


def test_build_user_agent_omits_mailto_when_email_none() -> None:
    """config `[identity].email` 未配置（None）→ UA 省略 mailto 段（不硬编码占位地址）。"""
    ua = build_user_agent(None, version="9.9.9")
    assert ua == "PaperCrawler/9.9.9 (personal research)"


def test_build_user_agent_omits_mailto_when_email_empty() -> None:
    """空串等价未配置（防御性）——同样省略 mailto 段。"""
    assert build_user_agent("", version="9.9.9") == "PaperCrawler/9.9.9 (personal research)"


def test_build_user_agent_uses_package_version_when_version_omitted() -> None:
    """未显式给 version 时用已安装分发版本（形如 PaperCrawler/<ver> ...）。"""
    ua = build_user_agent("me@example.com")
    assert ua.startswith("PaperCrawler/")
    assert ua.endswith("(personal research; mailto:me@example.com)")


def test_package_version_falls_back_when_distribution_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from importlib import metadata as im

    from paper_crawler import __version__

    def _raise(_name: str) -> str:
        raise im.PackageNotFoundError(_name)

    monkeypatch.setattr(useragent.metadata, "version", _raise)
    assert useragent._package_version() == __version__
