"""跨测试树共享的小工具：contract venue 工厂 + 假 `FetchIO`。

包名说明：`tests/` 目录本身没有 `__init__.py`（T1 起的既有布局——`tests/unit`、
`tests/contract`、`tests/integration` 各自独立成包，靠 pytest 的 rootdir 插入
机制把 `tests/` 加进 `sys.path`）。因此本包以顶层模块名导入：``from helpers import
...``，而不是 ``from tests.helpers import ...``（后者会因为 `tests` 不是包而
`ImportError`——已用探针测试验证）。
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from paper_crawler.types import VenueSpec

DEFAULT_MOCK_QUIRKS: dict[str, object] = {
    "volumes": 3,
    "issues_per_volume": 2,
    "papers_per_issue": 5,
    "seed": 42,
}

# arxiv 契约/集成测试用的 preprint_channel venue（不依赖 venues/ 目录——仓库不 ship
# arxiv YAML，test_venue_yaml_lint 钉死 shipped 集合为 {mock_journal, jfe, iclr, icml}）。
# inception 取近期月份保证 discover 非空；arxiv_category 决定 OAI set(=cs) 与子分类过滤。
DEFAULT_ARXIV_QUIRKS: dict[str, object] = {
    "inception": "2024-01",
    "arxiv_set": "cs",
    "arxiv_category": "cs.LG",
}

# openreview 契约/集成测试用的 conference venue（id 必须为 'iclr'——adapter 内置届表按
# venue.id 键取，见 adapters/openreview/venues._BUILTIN_TABLES）。auth free_account 匹配
# adapter auth_requirement（否则 lint 不过）。overrides 通道默认空。
DEFAULT_OPENREVIEW_QUIRKS: dict[str, object] = {"openreview_group_overrides": {}}
# pmlr 契约/集成测试用的 conference venue：quirks 自成一体、独立于 venues/cs_ai/icml.yaml
# 的真实内容（同 arxiv 先例的解耦考量——adapter 逻辑测试不应受真实 venue 数据编辑影响；
# 真实 shipped YAML 的自身正确性由 test_venue_yaml_lint.py 与 D-019 锚点一致性测试覆盖）。
# 只保留两个年份（一自托管旧卷 2023/v202、一 GitHub 托管新卷 2024/v235）即可覆盖双域路径。
DEFAULT_PMLR_QUIRKS: dict[str, object] = {
    "volume_map": {2023: 202, 2024: 235},
}
# aaai_ojs 契约/集成测试用的 conference venue：quirks 自成一体、独立于 venues/cs_ai/aaai.yaml
# 的真实内容（同 pmlr/arxiv 先例的解耦考量）。保留两个年份——一历史届（2019/v33，enumerate
# 全库回填无日期窗）、一当前届（2026/v40=volume_map 最大年，enumerate 触发固定回看窗增量），
# 覆盖 design §4 的双枚举路径。ojs_code=AAAI 显式给出（否则回退 venue.id.upper()='AAAI'，此处
# venue id 恰为 'aaai' 也能推出，但显式更贴近真实 YAML）。
DEFAULT_AAAI_QUIRKS: dict[str, object] = {
    "volume_map": {2019: 33, 2026: 40},
    "ojs_code": "AAAI",
}

# acl_anthology 契约/集成测试用的 conference venue（id='emnlp'，与 venues/cs_ai/emnlp.yaml
# 一致）。`anthology_legacy_prefix` 驱动旧式文件名构造（design/adapters/acl-anthology.md §4）。
DEFAULT_ACL_ANTHOLOGY_QUIRKS: dict[str, object] = {"anthology_legacy_prefix": "D"}

# cvf 契约/集成测试用venue 的展示名（id 必须是 cvpr/iccv/wacv 之一——adapter 内置 cadence
# 表按 venue.id 键取，见 adapters/cvf/cadence._CADENCE_TABLE）。无 quirks 默认（cadence 规则
# 生成届表零配置即可用；overrides/list_mode 按需经 quirks_overrides 注入）。
_CVF_NAMES: dict[str, dict[str, object]] = {
    "cvpr": {
        "full": "IEEE/CVF Conference on Computer Vision and Pattern Recognition",
        "aliases": ["CVPR"],
    },
    "iccv": {
        "full": "IEEE/CVF International Conference on Computer Vision",
        "aliases": ["ICCV"],
    },
    "wacv": {
        "full": "IEEE/CVF Winter Conference on Applications of Computer Vision",
        "aliases": ["WACV"],
    },
}

# neurips_proceedings 契约/集成测试用的 conference venue：quirks 自成一体、独立于
# venues/cs_ai/neurips.yaml 的真实内容（同 pmlr/arxiv 先例的解耦考量）。收窄到
# [2021, 2022]——单一后缀边界（legacy→modern）两侧各一年，恰好是 healthcheck 固定
# canary 覆盖的两届（design/adapters/neurips-proceedings.md §3.5），discover 默认零
# 网络产 2 个 IssueRef，测试确定性不随墙钟年份漂移。
DEFAULT_NEURIPS_QUIRKS: dict[str, object] = {
    "first_year": 2021,
    "known_through_year": 2022,
}


def make_mock_venue(**quirks_overrides: object) -> VenueSpec:
    """构造 mock_platform 契约测试用的 venue（不依赖 `venues/` 目录文件）。

    默认 quirks 与 phase1-implementation-plan Task 3 中 `venues/_mock/mock-journal.yaml`
    的取值一致（volumes=3, issues_per_volume=2, papers_per_issue=5, seed=42），
    保证本任务的 golden 快照与 T3 落地后的真实 venue YAML 语义一致。
    """
    quirks: dict[str, object] = dict(DEFAULT_MOCK_QUIRKS)
    quirks.update(quirks_overrides)
    return VenueSpec(
        id="mock_journal",
        kind="journal",
        names={"full": "Mock Journal", "aliases": ["MJ"]},
        field=["cs_ai"],
        identifiers={"issn": ["0000-0000"]},
        metadata_source="mock_platform",
        fulltext_source="mock_platform",
        quirks=quirks,
    )


def make_arxiv_venue(**quirks_overrides: object) -> VenueSpec:
    """构造 arxiv 契约/集成测试用的 `preprint_channel` venue（不依赖 `venues/` 目录文件）。

    默认 quirks：`inception='2024-01'`（近期，保证 discover 非空且窗口为过去完整月）、
    `arxiv_set='cs'`、`arxiv_category='cs.LG'`（决定 OAI set 与子分类客户端过滤）。
    """
    quirks: dict[str, object] = dict(DEFAULT_ARXIV_QUIRKS)
    quirks.update(quirks_overrides)
    return VenueSpec(
        id="arxiv_cs_lg",
        kind="preprint_channel",
        names={"full": "arXiv cs.LG (Machine Learning)", "aliases": ["arxiv-cs-lg"]},
        field=["cs_ai"],
        metadata_source="arxiv",
        fulltext_source="arxiv",
        quirks=quirks,
    )


def make_openreview_venue(**quirks_overrides: object) -> VenueSpec:
    """构造 openreview 契约/集成测试用的 `conference` venue（不依赖 `venues/` 目录文件）。

    id='iclr'（adapter 内置 ICLR 届表按 venue.id 键取）；auth=free_account+provider_hint
    （匹配 adapter auth_requirement）。`quirks_overrides` 可注入 `openreview_group_overrides`
    覆盖届表。
    """
    quirks: dict[str, object] = dict(DEFAULT_OPENREVIEW_QUIRKS)
    quirks.update(quirks_overrides)
    return VenueSpec(
        id="iclr",
        kind="conference",
        names={"full": "International Conference on Learning Representations", "aliases": ["ICLR"]},
        field=["cs_ai"],
        identifiers={"dblp_key": "conf/iclr"},
        metadata_source="openreview",
        fulltext_source="openreview",
        auth={"level": "free_account", "provider_hint": "openreview"},
        quirks=quirks,
    )


def make_pmlr_venue(**quirks_overrides: object) -> VenueSpec:
    """构造 pmlr 契约/集成测试用的 `conference` venue（不依赖 `venues/` 目录文件）。

    默认 quirks：`volume_map={2023: 202, 2024: 235}`（一自托管旧卷 + 一 GitHub
    托管新卷，覆盖 pmlr.md §3.3 的双域 resolve 路径）。
    """
    quirks: dict[str, object] = dict(DEFAULT_PMLR_QUIRKS)
    quirks.update(quirks_overrides)
    return VenueSpec(
        id="icml",
        kind="conference",
        names={"full": "International Conference on Machine Learning", "aliases": ["ICML"]},
        field=["cs_ai"],
        identifiers={"dblp_key": "conf/icml"},
        metadata_source="pmlr",
        fulltext_source="pmlr",
        quirks=quirks,
    )


def make_acl_anthology_venue(**quirks_overrides: object) -> VenueSpec:
    """构造 acl_anthology 契约/集成测试用的 `conference` venue（不依赖 `venues/` 目录文件）。

    id='emnlp'（与仓内 `venues/cs_ai/emnlp.yaml` 一致，虽测试默认不读该文件）；
    auth=none（family=open_access，勘察 §7 全程匿名）；quirks 默认含
    `anthology_legacy_prefix='D'` 驱动旧式文件名构造/候选年份提取。
    """
    quirks: dict[str, object] = dict(DEFAULT_ACL_ANTHOLOGY_QUIRKS)
    quirks.update(quirks_overrides)
    return VenueSpec(
        id="emnlp",
        kind="conference",
        names={
            "full": "Conference on Empirical Methods in Natural Language Processing",
            "aliases": ["EMNLP"],
        },
        field=["cs_ai"],
        identifiers={"dblp_key": "conf/emnlp"},
        metadata_source="acl_anthology",
        fulltext_source="acl_anthology",
        quirks=quirks,
    )


def make_cvf_venue(venue_id: str = "cvpr", **quirks_overrides: object) -> VenueSpec:
    """构造 cvf 契约/集成测试用的 `conference` venue（不依赖 `venues/` 目录文件）。

    默认 `id='cvpr'`（adapter 内置 cadence 表按 venue.id 键取：cvpr/iccv/wacv 三选一，
    调用方传 `venue_id='iccv'`/`'wacv'` 复用同一工厂）。`auth` 用默认值
    `AuthLevel.NONE`（CVF 匿名可读，无需声明——匹配 adapter `auth_requirement`）。
    `quirks_overrides` 可注入 `cvf_edition_overrides`/`list_mode` 等 quirks。
    """
    quirks: dict[str, object] = dict(quirks_overrides)
    return VenueSpec(
        id=venue_id,
        kind="conference",
        names=_CVF_NAMES.get(venue_id, {"full": venue_id.upper(), "aliases": [venue_id.upper()]}),
        field=["cs_ai"],
        metadata_source="cvf",
        fulltext_source="cvf",
        quirks=quirks,
    )


def make_aaai_venue(**quirks_overrides: object) -> VenueSpec:
    """构造 aaai_ojs 契约/集成测试用的 `conference` venue（不依赖 `venues/` 目录文件）。

    默认 quirks：`volume_map={2019: 33, 2026: 40}`（一历史届 + 一当前届，覆盖 aaai-ojs.md
    §4 的全库回填 / 固定回看窗双枚举路径）、`ojs_code='AAAI'`。
    """
    quirks: dict[str, object] = dict(DEFAULT_AAAI_QUIRKS)
    quirks.update(quirks_overrides)
    return VenueSpec(
        id="aaai",
        kind="conference",
        names={"full": "AAAI Conference on Artificial Intelligence", "aliases": ["AAAI"]},
        field=["cs_ai"],
        identifiers={"dblp_key": "conf/aaai"},
        metadata_source="aaai_ojs",
        fulltext_source="aaai_ojs",
        quirks=quirks,
    )


def make_crossref_venue(**quirks_overrides: object) -> VenueSpec:
    """构造 crossref 契约测试用的 `journal` venue（不依赖 `venues/` 目录文件）。

    id/names 借用真实 QJE 身份（与 crossref adapter 自身单测 `tests/unit/
    test_crossref_adapter.py` 的本地 `_venue()` 同一识别号，便于跨文件对照），
    `identifiers.issn` 是 `adapter._issn_of` 的唯一输入（D-015：期刊+crossref 必填，
    lint 已保证）——契约 handler 不校验请求里的实际 ISSN 值，故该值本身不需要与任何
    fixture 内容对应，只需形态合法。`quirks_overrides` 目前无消费方（crossref 不读
    quirks），保留形参只为与其余 `make_*_venue` 签名一致。
    """
    quirks: dict[str, object] = dict(quirks_overrides)
    return VenueSpec(
        id="qje",
        kind="journal",
        names={"full": "Quarterly Journal of Economics", "aliases": ["QJE"]},
        field=["econ"],
        identifiers={"issn": ["0033-5533"]},
        metadata_source="crossref",
        fulltext_source="mock_platform",
        quirks=quirks,
    )


def make_wiley_venue(**quirks_overrides: object) -> VenueSpec:
    """构造 wiley 契约/单测用的 `journal` venue（不依赖 `venues/` 目录文件）。

    id='jf'（Journal of Finance，Wiley 平台金融第一刊，wiley.md §1）；`metadata_source=
    'crossref'`（enumerate 走 crossref）、`fulltext_source='wiley'`；auth=institutional
    （TDM token + 订阅域，匹配 adapter `auth_requirement`）。wiley `resolve_assets` 不读
    `venue` 参数（TDM 按 DOI 取回，跨 venue——同 unpaywall 先例），故字段只需形态合法。
    `quirks_overrides` 目前无消费方，保留形参与其余 `make_*_venue` 签名一致。
    """
    quirks: dict[str, object] = dict(quirks_overrides)
    return VenueSpec(
        id="jf",
        kind="journal",
        names={"full": "The Journal of Finance", "aliases": ["JF"]},
        field=["finance"],
        identifiers={"issn": ["0022-1082"]},
        metadata_source="crossref",
        fulltext_source="wiley",
        auth={"level": "institutional", "provider_hint": "wiley"},
        quirks=quirks,
    )


def make_neurips_venue(**quirks_overrides: object) -> VenueSpec:
    """构造 neurips_proceedings 契约/集成测试用的 `conference` venue（不依赖 `venues/` 目录）。

    id='neurips'。默认 quirks 收窄届表到 `[2021, 2022]`（单一后缀边界两侧各一年）；
    `quirks_overrides` 可注入/覆盖 `first_year`/`known_through_year`。
    """
    quirks: dict[str, object] = dict(DEFAULT_NEURIPS_QUIRKS)
    quirks.update(quirks_overrides)
    return VenueSpec(
        id="neurips",
        kind="conference",
        names={
            "full": "Conference on Neural Information Processing Systems",
            "aliases": ["NeurIPS", "NIPS"],
        },
        field=["cs_ai"],
        identifiers={"dblp_key": "conf/nips"},
        metadata_source="neurips_proceedings",
        fulltext_source="neurips_proceedings",
        quirks=quirks,
    )


def make_elsevier_venue(**quirks_overrides: object) -> VenueSpec:
    """构造 elsevier_sd 契约/单测用的 `journal` venue（不依赖 `venues/` 目录文件）。

    借用真实 JFE 身份（Journal of Financial Economics，ISSN 0304-405X）；`metadata_source=
    crossref`（D-005：enumerate 走 crossref，elsevier 无 DISCOVER/ENUMERATE）、`fulltext_source=
    elsevier_sd`、`auth.level=institutional`（匹配 adapter `auth_requirement`）。elsevier resolve
    只读 `paper.identifiers` 的 doi（非 venue.issn），故 issn 值本身只需形态合法。`quirks_overrides`
    可注入 `elsevier_want_xml_source=True` 开启 XML SOURCE 备选（§3.1"可选同存"）。
    """
    quirks: dict[str, object] = dict(quirks_overrides)
    return VenueSpec(
        id="jfe",
        kind="journal",
        names={"full": "Journal of Financial Economics", "aliases": ["JFE"]},
        field=["finance"],
        identifiers={"issn": ["0304-405X"]},
        metadata_source="crossref",
        fulltext_source="elsevier_sd",
        auth={"level": "institutional", "provider_hint": "elsevier"},
        quirks=quirks,
    )


class FakeFetchIO:
    """`FetchIO` 协议的测试替身：把 chunks 缓冲进内存并计算 `(bytes_written, sha256)`。

    同时记录收到的 chunk 数，供测试断言 adapter 确实分块写入（而非一次性整块写）。
    """

    def __init__(self) -> None:
        self.data: bytes = b""
        self.chunk_count: int = 0

    def write_stream(self, chunks: Iterable[bytes]) -> tuple[int, str]:
        buf = bytearray()
        for chunk in chunks:
            buf.extend(chunk)
            self.chunk_count += 1
        self.data = bytes(buf)
        return len(self.data), hashlib.sha256(self.data).hexdigest()


__all__ = [
    "DEFAULT_AAAI_QUIRKS",
    "DEFAULT_ACL_ANTHOLOGY_QUIRKS",
    "DEFAULT_ARXIV_QUIRKS",
    "DEFAULT_MOCK_QUIRKS",
    "DEFAULT_OPENREVIEW_QUIRKS",
    "DEFAULT_PMLR_QUIRKS",
    "FakeFetchIO",
    "make_aaai_venue",
    "make_acl_anthology_venue",
    "make_arxiv_venue",
    "make_crossref_venue",
    "make_cvf_venue",
    "make_elsevier_venue",
    "make_mock_venue",
    "make_openreview_venue",
    "make_pmlr_venue",
    "make_wiley_venue",
    "DEFAULT_NEURIPS_QUIRKS",
    "make_neurips_venue",
]
