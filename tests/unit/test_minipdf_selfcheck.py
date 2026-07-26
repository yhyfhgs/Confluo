"""L1/L2 生成器自校验（12-fulltext-extract §8.2 强制项；风险 R7）。

**为什么必须有这一组**：生成器换来参数化能力的代价是**它自己可能有 bug**——一个语法非法的
「合法 PDF」会让抽取器抽出空串，而测试把这解读成「抽取器正确地判了 image_only」，于是
**生成器缺陷伪装成被测行为**，整组负例测试全部变成假绿。故本文件的三层自校验：

1. **结构自检**（纯字节级，**完全不经被测的抽取代码路径**）：`%PDF-` 头 + `%%EOF` 尾 +
   xref 表偏移可解析 + 对象计数与 `/Count` 一致；
2. **SENTINEL 正例锚定**：`make_text_pdf("SENTINEL")` 经抽取器必须抽出 `SENTINEL`——
   这条断言若红，说明**生成器坏了**，不是抽取器坏了；
3. **负例区分度**：`make_image_only_pdf()` 与 `make_corrupt_pdf()` 必须产出**不同的**
   `note` token，否则说明生成器没造出预期形态。

断言消息一律显式指向「生成器坏了」——否则将来的人会去改抽取器。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from helpers.minipdf import (
    make_corrupt_pdf,
    make_encrypted_pdf,
    make_image_only_pdf,
    make_text_pdf,
)
from paper_crawler.pipeline.extract import (
    NOTE_CORRUPT,
    NOTE_EMPTY_TEXT,
    NOTE_ENCRYPTED,
    NOTE_IMAGE_ONLY,
    PypdfExtractor,
)

_GEN = "生成器（tests/helpers/minipdf.py）坏了——不要改抽取器"


def _write(tmp_path: Path, data: bytes, name: str = "sample.bin") -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


# -- 层 1：结构自检（零抽取器参与）--------------------------------------------------------


@pytest.mark.parametrize("pages", [1, 2, 5])
def test_structure_header_trailer_and_xref_offset(pages: int) -> None:
    data = make_text_pdf("structural self-check", pages=pages)
    assert data.startswith(b"%PDF-"), f"{_GEN}：缺 %PDF- 头"
    assert data.rstrip().endswith(b"%%EOF"), f"{_GEN}：缺 %%EOF 尾"

    match = re.search(rb"startxref\s+(\d+)\s*%%EOF", data)
    assert match is not None, f"{_GEN}：startxref 段不可解析"
    offset = int(match.group(1))
    assert data[offset : offset + 4] == b"xref", f"{_GEN}：startxref 偏移未指向 xref 表"


@pytest.mark.parametrize("pages", [1, 3])
def test_structure_object_count_matches_page_count(pages: int) -> None:
    """xref 表登记的对象数与实际 `N 0 obj` 数、`/Count` 与实际 page 对象数三者一致。"""
    data = make_text_pdf("counting", pages=pages)
    objects = re.findall(rb"^(\d+) 0 obj$", data, flags=re.MULTILINE)
    size = re.search(rb"/Size (\d+)", data)
    assert size is not None, f"{_GEN}：trailer 缺 /Size"
    assert int(size.group(1)) == len(objects) + 1, f"{_GEN}：/Size 与对象数不符（含 free 头项）"

    count = re.search(rb"/Count (\d+)", data)
    assert count is not None, f"{_GEN}：/Pages 缺 /Count"
    assert int(count.group(1)) == pages, f"{_GEN}：/Count 与请求页数不符"
    assert len(re.findall(rb"/Type /Page\b", data)) == pages, f"{_GEN}：page 对象数不符"


def test_structure_is_pure_ascii() -> None:
    """全 ASCII 源（§8.2）：可 diff、reviewer 可读，不是二进制黑箱。"""
    for data in (make_text_pdf("ascii"), make_image_only_pdf(), make_encrypted_pdf()):
        assert data.decode("ascii"), f"{_GEN}：产物含非 ASCII 字节"


# -- 层 2：SENTINEL 正例锚定 ---------------------------------------------------------------


def test_sentinel_round_trip(tmp_path: Path) -> None:
    produced = PypdfExtractor().extract(_write(tmp_path, make_text_pdf("SENTINEL")))
    assert "SENTINEL" in produced.text, f"{_GEN}：注入的 SENTINEL 没能被抽回来"
    assert produced.char_count > 0 and produced.note is None


def test_multi_page_concatenation_order(tmp_path: Path) -> None:
    """多页拼接序：第 1 页的标记必须先于第 2、3 页出现。"""
    produced = PypdfExtractor().extract(_write(tmp_path, make_text_pdf("body", pages=3)))
    positions = [produced.text.index(f"[page {n}/3]") for n in (1, 2, 3)]
    assert positions == sorted(positions), f"{_GEN}：多页文本拼接序错乱"


# -- 层 3：负例区分度 ----------------------------------------------------------------------


def test_negative_samples_yield_distinct_note_tokens(tmp_path: Path) -> None:
    """四个负例必须落**互不相同**的 note token；塌缩即说明生成器没造出预期形态。"""
    extractor = PypdfExtractor()
    cases = {
        NOTE_IMAGE_ONLY: make_image_only_pdf(),
        NOTE_CORRUPT: make_corrupt_pdf(),
        NOTE_ENCRYPTED: make_encrypted_pdf(),
        NOTE_EMPTY_TEXT: make_text_pdf(""),
    }
    observed: dict[str, str | None] = {}
    for expected, data in cases.items():
        produced = extractor.extract(_write(tmp_path, data, f"{expected}.bin"))
        assert produced.char_count == 0, f"{_GEN}：{expected} 负例竟抽出了文本"
        observed[expected] = produced.note
    assert observed == {token: token for token in cases}, (
        f"{_GEN}：负例 token 与预期形态不符 —— {observed}"
    )
    assert len(set(observed.values())) == len(cases), f"{_GEN}：负例 token 塌缩 —— {observed}"
