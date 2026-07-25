"""AC-2.5 离线层用的全量规模合成生成器（design/adapters/acl-anthology.md §2/§7；D-019）。

**与 `tests/fixtures/acl_anthology/` 的 T3 十一件套小样本是两回事**：T3 样本按比例
缩样（几篇/volume），服务解析器正确性单测；本模块反其道而行——追求"篇数精确匹配
`anchor-emnlp-2023.json` 锚点表"（main=1047 / tutorial=6 / demo=52 / industry=77 /
findings-emnlp=1059，合计 2241），供 AC-2.5"EMNLP 全量"离线验收使用。

程序化生成而非提交一份 4-5MB 手写 XML fixture 入 git：内容为构造占位文本，但结构
严格遵循 `schema.rnc`（Collection→Volume→Paper，含 `<url>`/`<doi>`/`<bibkey>`/
`<pages>`/`<abstract>` 等常见字段），足以让 `parse.py` 按真实解析路径逐篇产出
`PaperStub`——不是一份"假装数量对的空壳"，而是 2241 篇结构合法、内容可解析的
合成论文。

**F4 清账（S1 审计"acl bulk 对账生成器分卷计数手抄自 anchor"）**：下方
`MAIN_VOLUME_COUNTS`/`FINDINGS_EMNLP_COUNT` 系手抄自 `anchor-emnlp-2023.json`；
`assert TOTAL_EMNLP_2023 == 2241` 只证明这些手抄数字**自身算术自洽**（即便手抄
错了，只要几个数字凑出同一个 2241 仍会通过）——不证明它们真的等于锚点文件里的
权威值。`assert_matches_anchor` 在模块导入期即独立重新加载 anchor JSON 并逐卷
断言一致，把此前仅靠某个下游测试文件"恰好"做了这项 cross-check 的隐性依赖，
变成本模块自身在导入时就响亮校验的显式契约。
"""

from __future__ import annotations

import json
from pathlib import Path

_ANCHOR_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "acl_anthology" / "anchor-emnlp-2023.json"
)


def _load_anchor_by_volume(path: Path = _ANCHOR_PATH) -> dict[str, int]:
    """`anchor-emnlp-2023.json` → ``{anthology_volume_id: paper_count}``（独立加载，
    不经 `MAIN_VOLUME_COUNTS`/`FINDINGS_EMNLP_COUNT`，供交叉校验用）。
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    return {v["anthology_volume_id"]: v["paper_count"] for v in data["volumes"]}


def assert_matches_anchor(
    main_counts: dict[str, int], findings_count: int, anchor_by_volume: dict[str, int]
) -> None:
    """独立正确性校验（非仅算术自洽，F4/S1 审计）：手抄分卷计数须与 anchor 逐项相等。

    `TOTAL_EMNLP_2023 == 2241` 式的内部求和自检只证明"手抄数字彼此自洽"——即便
    `main_counts`/`findings_count` 手抄错误，只要凑出同一个合计仍能通过。这里逐项
    对照**独立加载**的 anchor 表，任一卷漂移立即响亮 `AssertionError`。
    """
    for volume_id, count in main_counts.items():
        anchor_count = anchor_by_volume.get(volume_id)
        assert count == anchor_count, (
            f"MAIN_VOLUME_COUNTS[{volume_id!r}]={count} 与 anchor paper_count="
            f"{anchor_count!r} 不一致（anchor-emnlp-2023.json）——两处已漂移，"
            "须先核对哪个是权威值再同步"
        )
    findings_anchor_count = anchor_by_volume.get("findings")
    assert findings_count == findings_anchor_count, (
        f"FINDINGS_EMNLP_COUNT={findings_count} 与 anchor findings paper_count="
        f"{findings_anchor_count!r} 不一致（anchor-emnlp-2023.json）"
    )


# 与 anchor-emnlp-2023.json 逐字段对齐——改动任一处务必同步更新该锚点文件（下方
# assert_matches_anchor 调用会在两处漂移时立即响亮报错，不必只靠人工纪律记住）。
MAIN_VOLUME_COUNTS: dict[str, int] = {"main": 1047, "tutorial": 6, "demo": 52, "industry": 77}
FINDINGS_EMNLP_COUNT = 1059
# 该年 Findings 文件内混入另一 venue 的极小配额——全量规模下依然要证明 join 过滤
# 生效（非 emnlp 的 volume 绝不能混入 enumerate 产出）；不计入 anchor total。
FINDINGS_OTHER_VENUE_COUNT = 3

TOTAL_EMNLP_2023 = sum(MAIN_VOLUME_COUNTS.values()) + FINDINGS_EMNLP_COUNT
assert TOTAL_EMNLP_2023 == 2241  # 锚点表 §2/§7 合计校验（防未来改动悄悄漂移不被发现）
assert_matches_anchor(MAIN_VOLUME_COUNTS, FINDINGS_EMNLP_COUNT, _load_anchor_by_volume())


def _paper_xml(collection_id: str, volume_id: str, n: int) -> str:
    anthology_id = f"{collection_id}-{volume_id}.{n}"
    return (
        f'<paper id="{n}">'
        f"<title>Synthetic {volume_id} Paper {n}</title>"
        f"<author><first>Auto</first><last>Author{n}</last></author>"
        f"<pages>{n}-{n}</pages>"
        f"<abstract>Synthetic abstract for paper {n} of volume {volume_id}.</abstract>"
        f'<url hash="{n:08x}">{anthology_id}</url>'
        f"<bibkey>synthetic-{volume_id}-{n}</bibkey>"
        f"<doi>10.18653/v1/{anthology_id}</doi>"
        "</paper>"
    )


def _volume_xml(collection_id: str, volume_id: str, count: int, *, venue_text: str) -> str:
    papers = "".join(_paper_xml(collection_id, volume_id, n) for n in range(1, count + 1))
    return (
        f'<volume id="{volume_id}" type="proceedings">'
        "<meta>"
        f"<booktitle>Synthetic {volume_id} Proceedings</booktitle>"
        "<publisher>Association for Computational Linguistics</publisher>"
        "<address>Singapore</address><month>December</month><year>2023</year>"
        f"<venue>{venue_text}</venue>"
        "</meta>"
        f"{papers}"
        "</volume>"
    )


def _collection_xml(collection_id: str, body: str) -> bytes:
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        f'<collection id="{collection_id}">{body}</collection>'
    ).encode()


def synthetic_emnlp_main_2023_xml() -> bytes:
    """`2023.emnlp.xml` 的全量规模合成体：main/tutorial/demo/industry 四 volume（1182 篇）。"""
    collection_id = "2023.emnlp"
    body = "".join(
        _volume_xml(collection_id, volume_id, count, venue_text="emnlp")
        for volume_id, count in MAIN_VOLUME_COUNTS.items()
    )
    return _collection_xml(collection_id, body)


def synthetic_findings_2023_xml() -> bytes:
    """`2023.findings.xml` 全量规模合成体：emnlp volume（1059）+ 另一 venue（3，join 过滤靶子）。"""
    collection_id = "2023.findings"
    body = _volume_xml(collection_id, "emnlp", FINDINGS_EMNLP_COUNT, venue_text="findings")
    body += _volume_xml(collection_id, "acl", FINDINGS_OTHER_VENUE_COUNT, venue_text="findings")
    return _collection_xml(collection_id, body)


__all__ = [
    "FINDINGS_EMNLP_COUNT",
    "FINDINGS_OTHER_VENUE_COUNT",
    "MAIN_VOLUME_COUNTS",
    "TOTAL_EMNLP_2023",
    "assert_matches_anchor",
    "synthetic_emnlp_main_2023_xml",
    "synthetic_findings_2023_xml",
]
