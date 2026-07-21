"""D-014 User-Agent 组装（中性模块）。

`build_user_agent` 原在 `adapters/arxiv/adapter.py`，但 UA 组装不是 arxiv 专属——
CLI `_http_client_factory` 及后续任何真实 adapter 都要用。上移到中性模块（T6-C2
backlog），arxiv/CLI 改从此处引用，消除"通用件挂在具体 adapter 下"的耦合。

D-014 格式：``PaperCrawler/<ver> (personal research; mailto:<email>)``。email 缺省
（config `[identity].email` 未配置）时省略 ``mailto:`` 段——不硬编码占位地址（隐私
安全），诚实反映"未提供联系方式"。
"""

from __future__ import annotations

from importlib import metadata

from paper_crawler import __version__


def _package_version() -> str:
    """已安装分发版本；源码树/未安装场景回退到包内 `__version__`。"""
    try:
        return metadata.version("paper-crawler")
    except metadata.PackageNotFoundError:  # 源码树/未安装场景
        return __version__


def build_user_agent(email: str | None, *, version: str | None = None) -> str:
    """D-014 UA：``PaperCrawler/<ver> (personal research; mailto:<email>)``。

    `email=None`（或空白串）时省略 `mailto:` 段，产出
    ``PaperCrawler/<ver> (personal research)``——不硬编码占位地址（隐私安全）。
    """
    ver = version or _package_version()
    if email:
        return f"PaperCrawler/{ver} (personal research; mailto:{email})"
    return f"PaperCrawler/{ver} (personal research)"


__all__ = ["build_user_agent"]
