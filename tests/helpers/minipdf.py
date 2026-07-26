"""程序化生成的最小合法 PDF 语料（12-fulltext-extract §8 裁决⑥；**零 `.pdf` 文件入库**）。

「仓库内小样本 PDF」被**否决**，两条证据：AC-0.3 明文「凭证/session/**PDF** 不出现在 git
历史」；仓库 `.gitignore` 现有 `*.pdf` 全局条目（提交 fixture PDF 需 `git add -f` 强推——
形式与实质都违规，且会让 AC-0.3 的守卫面出现「合法的例外」，侵蚀该红线此后一切执行力）。
附带理由：真实站点 PDF 还带版权面，即使红线不禁也不该入库。

生成器优于「入库一个真 PDF」的实质点不只是合规让步：它是**参数化**的——同一函数可造多页/
空页/超长文本/指定标题的任意组合，测试可直接断言「注入的标题被抽了出来」；而一份静态 PDF
只能测一个形态，且其内容对 reviewer 是不可 diff 的二进制黑箱。

三层（§8.2）：

- **L1 快乐路径**：`make_text_pdf`——base-14 Helvetica + `Tj` 文本算子，全 ASCII 源，约 1 KB。
- **L2 生成式负例**：`make_image_only_pdf` / `make_corrupt_pdf` / `make_encrypted_pdf`，
  覆盖 §6.1 第 2 类的四个 `note` token。
- L3（TEI 语料）见 `tests/fixtures/grobid/`。

**代价与对策（R7，§8.2 强制项）**：生成器**自己可能有 bug**——一个语法非法的「合法 PDF」
会让抽取器抽出空串，而测试把这解读成「抽取器正确地判了 image_only」，于是**生成器缺陷伪装
成被测行为**，整组负例测试全部变成假绿。故 `tests/unit/test_minipdf_selfcheck.py` 落独立自
校验（结构自检不经被测抽取路径 + SENTINEL 正例锚定 + 负例 token 区分度），其断言消息显式
指向「生成器坏了」而非抽取器。

**不实现任何加密算法**（§2.3）：`make_encrypted_pdf` 只在 trailer 挂一个 `/Encrypt` 字典触发
阅读器的加密判定，字典里的 `/O`/`/U` 是常量填充字节，既不是从口令派生的、也解不开。
"""

from __future__ import annotations

from collections.abc import Sequence

_HEADER = b"%PDF-1.4\n"
_MEDIABOX = b"/MediaBox [0 0 612 792]"


def _escape(text: str) -> bytes:
    """PDF 字面串转义（`\\`、`(`、`)`）；非 ASCII 字符落为 `?`（全 ASCII 源要求）。"""
    out = []
    for ch in text:
        if ch in "\\()":
            out.append("\\" + ch)
        elif ch.isascii() and (ch.isprintable() or ch == " "):
            out.append(ch)
        else:
            out.append("?")
    return "".join(out).encode("ascii")


def _content_stream(lines: Sequence[str]) -> bytes:
    """把若干行文本编译成一个 `BT … Tj … ET` 内容流（`TL` 行距 + `T*` 换行）。"""
    if not lines:
        return b""
    body = bytearray(b"BT\n/F1 12 Tf\n14 TL\n72 720 Td\n")
    for index, line in enumerate(lines):
        if index:
            body += b"T*\n"
        body += b"(" + _escape(line) + b") Tj\n"
    body += b"ET\n"
    return bytes(body)


def _stream_object(stream: bytes, extra: bytes = b"") -> bytes:
    return (
        b"<< /Length "
        + str(len(stream)).encode("ascii")
        + b" "
        + extra
        + b">>\nstream\n"
        + (stream)
        + b"\nendstream"
    )


def _assemble(objects: Sequence[bytes], *, trailer_extra: bytes = b"") -> bytes:
    """把 1-based 编号的对象列表组装成带 xref 表的完整 PDF（对象 1 恒为 `/Catalog`）。

    xref 偏移量按实际字节位置计算——这是自校验测试「xref 表偏移可解析」那条断言的被测面。
    """
    body = bytearray(_HEADER)
    offsets: list[int] = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body += str(number).encode("ascii") + b" 0 obj\n" + obj + b"\nendobj\n"
    xref_offset = len(body)
    size = len(objects) + 1
    body += b"xref\n0 " + str(size).encode("ascii") + b"\n"
    body += b"0000000000 65535 f \n"
    for offset in offsets:
        body += f"{offset:010d} 00000 n \n".encode("ascii")
    body += b"trailer\n<< /Size " + str(size).encode("ascii") + b" /Root 1 0 R " + trailer_extra
    body += b">>\nstartxref\n" + str(xref_offset).encode("ascii") + b"\n%%EOF\n"
    return bytes(body)


def _page_object(parent: int, resources: bytes, contents: int) -> bytes:
    return (
        b"<< /Type /Page /Parent "
        + str(parent).encode("ascii")
        + b" 0 R "
        + _MEDIABOX
        + b" /Resources "
        + resources
        + b" /Contents "
        + str(contents).encode("ascii")
        + b" 0 R >>"
    )


def make_text_pdf(text: str, *, pages: int = 1) -> bytes:
    """L1：含真实文本层的最小合法 PDF（base-14 Helvetica，全 ASCII 源）。

    - `pages == 1`：唯一一页的可见文本**恰为** `text`（传空串即造「空页」——无任何可见
      文本、但结构完全合法，用于把 `empty_text` 与 `corrupt`/`image_only` 区分开）。
    - `pages > 1`：每页内容 = `text` + 一行页码标记 `[page n/N]`，供「多页拼接序」断言
      （抽出的正文里 `[page 1/N]` 必须先于 `[page 2/N]` 出现）。

    标题可控注入：把标题作为 `text` 的首行传入，AC-7.1 的「标题出现在正文前 2000 字符内」
    判据即可精确断言（对比静态 PDF 只能测一个形态）。
    """
    if pages < 1:
        raise ValueError("pages must be >= 1")
    page_count = pages
    kids: list[str] = []
    objects: list[bytes] = [b"", b""]  # 1=Catalog, 2=Pages（先占位，末尾回填）
    font_number = 3
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    resources = b"<< /Font << /F1 " + str(font_number).encode("ascii") + b" 0 R >> >>"
    for index in range(1, page_count + 1):
        lines = [line for line in text.split("\n") if line != ""] if text else []
        if page_count > 1:
            lines = [*lines, f"[page {index}/{page_count}]"]
        objects.append(b"")  # page 对象占位（编号 = len(objects)）
        page_number = len(objects)
        objects.append(_stream_object(_content_stream(lines)))
        contents_number = len(objects)
        objects[page_number - 1] = _page_object(2, resources, contents_number)
        kids.append(f"{page_number} 0 R")
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = (
        b"<< /Type /Pages /Kids ["
        + " ".join(kids).encode("ascii")
        + b"] /Count "
        + str(page_count).encode("ascii")
        + b" >>"
    )
    return _assemble(objects)


def make_image_only_pdf() -> bytes:
    """L2：**无文本层**、仅内嵌一个 1×1 ASCIIHex 图像 XObject 的一页 PDF（`image_only`）。

    模拟纯图像扫描件：结构完全合法、有可渲染内容，但抽不出任何字符。与 `make_text_pdf("")`
    的差别正是「页面资源里有 `/Subtype /Image`」——`note` 由此分化为 `image_only` 而非
    `empty_text`，两者的 token 区分度是自校验测试的一条断言。
    """
    image = _stream_object(
        b"FF>",
        b"/Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceGray "
        b"/BitsPerComponent 8 /Filter /ASCIIHexDecode ",
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        _page_object(2, b"<< /XObject << /Im1 5 0 R >> >>", 4),
        _stream_object(b"q 100 0 0 100 72 700 cm /Im1 Do Q"),
        image,
    ]
    return _assemble(objects)


def make_corrupt_pdf() -> bytes:
    """L2：结构损坏的 PDF（`corrupt`）——截断 L1 字节并抹掉 xref/trailer/`%%EOF`。

    截断点取「首个 `endobj` 之后」：`%PDF-` 头仍在（故它不是「根本不是 PDF」那类），但对象
    表不完整、无 xref、无 trailer、无 `%%EOF`，解析器无从重建文档结构。
    """
    intact = make_text_pdf("corrupt sample body text")
    cut = intact.find(b"endobj") + len(b"endobj\n")
    return intact[:cut]


def make_encrypted_pdf() -> bytes:
    """L2：trailer 挂 `/Encrypt` 的 PDF（`encrypted`）——**不实现任何加密算法**。

    `/O`/`/U` 是常量填充字节（既非口令派生、也解不开），`/Filter /Standard /V 1 /R 2`
    让阅读器进入标准安全处理器：`decrypt("")` 的空口令校验必然失败 → 抽取器落
    `note='encrypted'` 这**一个** token（§2.3 第五条：绝不分化出携带破解线索的取值）。
    """
    filler = b"<" + b"41" * 32 + b">"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        _page_object(2, b"<< /Font << /F1 5 0 R >> >>", 4),
        _stream_object(_content_stream(["locked away"])),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Filter /Standard /V 1 /R 2 /O " + filler + b" /U " + filler + b" /P -1 >>",
    ]
    doc_id = b"<" + b"30" * 16 + b">"
    return _assemble(
        objects, trailer_extra=b"/Encrypt 6 0 R /ID [" + doc_id + b" " + doc_id + b"] "
    )


__all__ = [
    "make_corrupt_pdf",
    "make_encrypted_pdf",
    "make_image_only_pdf",
    "make_text_pdf",
]
