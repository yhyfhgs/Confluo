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
"""

from __future__ import annotations

# 与 anchor-emnlp-2023.json 逐字段对齐——改动任一处务必同步更新该锚点文件。
MAIN_VOLUME_COUNTS: dict[str, int] = {"main": 1047, "tutorial": 6, "demo": 52, "industry": 77}
FINDINGS_EMNLP_COUNT = 1059
# 该年 Findings 文件内混入另一 venue 的极小配额——全量规模下依然要证明 join 过滤
# 生效（非 emnlp 的 volume 绝不能混入 enumerate 产出）；不计入 anchor total。
FINDINGS_OTHER_VENUE_COUNT = 3

TOTAL_EMNLP_2023 = sum(MAIN_VOLUME_COUNTS.values()) + FINDINGS_EMNLP_COUNT
assert TOTAL_EMNLP_2023 == 2241  # 锚点表 §2/§7 合计校验（防未来改动悄悄漂移不被发现）


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
    "synthetic_emnlp_main_2023_xml",
    "synthetic_findings_2023_xml",
]
