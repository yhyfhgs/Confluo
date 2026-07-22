"""dblp fixture 加载器（`tests/fixtures/dblp/raw/`）+ 单测用 venue 工厂。

全部 fixture 均为 **合成 fixture**（Phase 3 T4，dblp adapter 实现）——结构依
docs/design/adapters/aggregators.md §5.2 与
docs/research/site-survey/aggregators-unpaywall-dblp-core.md 的 [LIVE]
2026-07-20/2026-07-22 勘察记录，以及公开的 dblp.xml schema（dblp.dtd）手写；
本次实现未做真实网络录制（AC-0.5/D-014 约定：录制需
`PAPER_CRAWLER_CONTACT_EMAIL` 且遵守 robots `Crawl-delay:4`，本会话未执行在线
抓取，全走合成路径）。唯一例外：`conf/icml/AamandACINS23` 键与其 PMLR `ee`
形态是 aggregators.md §5.2 字段映射表原文引用的具体真实示例，fixture 直接
复用该键名以贴合设计文档；周边标题/作者/页码等内容仍为标注合成的占位值，不是
该论文的真实转录（各 fixture 文件头以注释详述）。

放在 `tests/helpers/` 独立新文件（而非改共享 `tests/helpers/__init__.py`）：
本文件是本 adapter 专属新增，不与任何并行任务共享——phase3 W2 波次 T3
（crossref）等如需类似 loader 会各自新建同名模式的文件，不产生编辑同一文件的
合并冲突面（共享文件纪律，phase3-implementation-plan.md §5 波次并行图）；
`make_dblp_venue` 因此也放在这里而非该共享模块。
"""

from __future__ import annotations

from pathlib import Path

from paper_crawler.types import VenueSpec

_RAW = Path(__file__).resolve().parents[1] / "fixtures" / "dblp" / "raw"


def fixture_bytes(name: str) -> bytes:
    """读取 `raw/<name>` 的原始字节。"""
    return (_RAW / name).read_bytes()


def http_fixture(name: str) -> tuple[int, dict[str, str], bytes]:
    """解析 `.http` 快照 → `(status, headers, body)`（格式同 `arxiv_fixtures.http_fixture`：
    `#` 起始行是注释；`HTTP-STATUS: <int>` 声明状态码；其余 `Key: Value` 是响应头；
    首个空行后为原始 body）。
    """
    raw = (_RAW / name).read_bytes()
    head, sep, body = raw.partition(b"\n\n")
    if not sep:  # 无空行分隔——整体视为 body，200 无头
        return 200, {}, raw
    status = 200
    headers: dict[str, str] = {}
    for line in head.decode("utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, _, value = stripped.partition(":")
        key, value = key.strip(), value.strip()
        if key.upper() == "HTTP-STATUS":
            status = int(value)
        else:
            headers[key] = value
    return status, headers, body


def make_dblp_venue(**quirks_overrides: object) -> VenueSpec:
    """构造 dblp 单测用的 `conference` venue（不依赖 `venues/` 目录文件）。

    id='icml'（与真实 `venues/cs_ai/icml.yaml`、healthcheck 固定 canary
    `conf/icml/icml2023` 口径一致）；`identifiers.dblp_key='conf/icml'` 是
    adapter 派生 DBLP acr 的唯一输入（`adapter._acr_of`，先例见
    `make_pmlr_venue`/`make_openreview_venue` 已在用同一约定字段）。
    `metadata_source='dblp'`（本 adapter 自身）、`fulltext_source='pmlr'`
    （dblp 无 FETCH，一个合理的真实分工示例——PMLR 承担全文，dblp 只承担会议
    元数据主干，貼合 aggregators.md §1 "会议主干"定位）；两个字段值均只是
    本测试夹具的自洽占位，不代表真实 `venues/cs_ai/icml.yaml` 现行路由
    （该文件现仍是 `metadata_source: pmlr`，切换与否留待 T7 决定）。
    """
    quirks: dict[str, object] = dict(quirks_overrides)
    return VenueSpec(
        id="icml",
        kind="conference",
        names={"full": "International Conference on Machine Learning", "aliases": ["ICML"]},
        field=["cs_ai"],
        identifiers={"dblp_key": "conf/icml"},
        metadata_source="dblp",
        fulltext_source="pmlr",
        quirks=quirks,
    )


__all__ = ["fixture_bytes", "http_fixture", "make_dblp_venue"]
