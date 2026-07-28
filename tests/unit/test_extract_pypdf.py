"""纯文本基线抽取器单测 + 加密 PDF 五条实现约束 + AC-7.1 判据小件（design/12 §3/§4/§12）。

`PypdfExtractor` 的契约面：路径进、值对象出；「文件在但抽不出」**不抛异常**（返回
`char_count == 0` + note），「文件不存在/不可读」抛 `CrawlerError(INTEGRITY)`。
"""

from __future__ import annotations

import re
from pathlib import Path

import pypdf
import pytest

from helpers.minipdf import (
    make_corrupt_pdf,
    make_encrypted_pdf,
    make_image_only_pdf,
    make_text_pdf,
)
from helpers.textmatch import (
    DEFAULT_MAX_RATIO,
    best_substring_distance,
    edit_distance,
    title_distance_ratio,
    title_in_body_ratio,
)
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.pipeline import extract as extract_mod
from paper_crawler.pipeline.extract import (
    NOTE_ENCRYPTED,
    NOTE_TOKENS,
    SUFFIX_TXT,
    ExtractedText,
    PypdfExtractor,
    visible_char_count,
)

_EXTRACT_SRC = Path(extract_mod.__file__).read_text(encoding="utf-8")


def _pdf(tmp_path: Path, data: bytes, name: str = "s.bin") -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


# -- 快乐路径 -----------------------------------------------------------------------------


def test_extract_returns_value_object_with_txt_suffix(tmp_path: Path) -> None:
    produced = PypdfExtractor().extract(_pdf(tmp_path, make_text_pdf("hello world")))
    assert produced.extractor == "pypdf"
    assert produced.extractor_ver == pypdf.__version__
    assert produced.suffix == SUFFIX_TXT
    assert produced.char_count == visible_char_count(produced.text) > 0
    assert produced.note is None
    # §4.2：不引入语言识别依赖——错误的 lang 比 NULL 更坏（NULL 的语义是「未知」）。
    assert produced.lang is None
    # 纯文本路径无结构化标题（AC-7.1 走正文前 2000 字符窗判据）。
    assert produced.title is None


def test_version_is_known_at_construction_time() -> None:
    """§5.2 硬前提：版本**构造期即可知**，否则「幂等跳过」退化成「抽完再比」。"""
    extractor = PypdfExtractor()
    assert extractor.version and extractor.name == "pypdf"


def test_missing_source_raises_integrity(tmp_path: Path) -> None:
    with pytest.raises(CrawlerError) as excinfo:
        PypdfExtractor().extract(tmp_path / "nope.pdf")
    assert excinfo.value.error_class is ErrorClass.INTEGRITY


# -- 零输出四态（§6.1 第 2 类）------------------------------------------------------------


@pytest.mark.parametrize(
    ("factory", "token"),
    [
        (make_image_only_pdf, "image_only"),
        (make_corrupt_pdf, "corrupt"),
        (make_encrypted_pdf, "encrypted"),
        (lambda: make_text_pdf(""), "empty_text"),
    ],
)
def test_zero_output_notes(tmp_path: Path, factory: object, token: str) -> None:
    produced = PypdfExtractor().extract(_pdf(tmp_path, factory()))  # type: ignore[operator]
    assert produced.char_count == 0
    assert produced.note == token
    assert produced.note in NOTE_TOKENS


def test_zero_output_does_not_raise(tmp_path: Path) -> None:
    """抽取器不做错误分类学决策——「抽不出」是观测，不是判决（§4.1 分工线）。"""
    assert PypdfExtractor().extract(_pdf(tmp_path, make_corrupt_pdf())).char_count == 0


# -- §4.1 断言锁定：char_count ⇄ note 的不变式 --------------------------------------------


def test_zero_output_without_note_is_rejected() -> None:
    with pytest.raises(ValueError, match="note token"):
        ExtractedText(text="", extractor="x", extractor_ver="1", suffix=".txt", char_count=0)


def test_successful_output_with_note_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not carry"):
        ExtractedText(
            text="t", extractor="x", extractor_ver="1", suffix=".txt", char_count=1, note="corrupt"
        )


def test_note_outside_the_closed_set_is_rejected() -> None:
    with pytest.raises(ValueError, match="note must be one of"):
        ExtractedText(
            text="", extractor="x", extractor_ver="1", suffix=".txt", char_count=0, note="weird"
        )


# -- §2.3 加密 PDF 五条实现约束（逐条各有测试）--------------------------------------------


def test_encrypted_constraint_1_empty_password_is_attempted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """①允许空口令打开：`decrypt("")` **确实被调用**（等价于阅读器打开该文件的常规行为）。"""
    seen: list[object] = []
    original = pypdf.PdfReader.decrypt

    def spy(self: pypdf.PdfReader, password: str) -> object:
        seen.append(password)
        return original(self, password)

    monkeypatch.setattr(pypdf.PdfReader, "decrypt", spy)
    PypdfExtractor().extract(_pdf(tmp_path, make_encrypted_pdf()))
    assert seen == [""]


def test_encrypted_constraint_2_exactly_one_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """②**只试一次空串**：失败即止——不重试、不变形（不试 `" "`/`None`/doi/标题等）。"""
    attempts: list[object] = []

    def spy(self: pypdf.PdfReader, password: str) -> object:
        attempts.append(password)
        raise RuntimeError("decryption unsupported")  # 最坏情形：解密直接炸

    monkeypatch.setattr(pypdf.PdfReader, "decrypt", spy)
    produced = PypdfExtractor().extract(_pdf(tmp_path, make_encrypted_pdf()))
    assert attempts == [""], "空口令必须**恰好**试一次，且只试空串"
    assert produced.note == NOTE_ENCRYPTED


def test_encrypted_constraint_3_no_fallback_password_list() -> None:
    """③**禁止任何回退口令列表**——存在这样的数据结构本身即违规，与是否被执行无关。

    机器判据：抽取模块内 `decrypt(` 恰好出现一次且实参恒为空串；且源码不出现候选口令/
    口令文件/常见 owner password 之类的标识符。
    """
    assert len(re.findall(r"\.decrypt\(", _EXTRACT_SRC)) == 1
    assert re.findall(r"\.decrypt\((.*?)\)", _EXTRACT_SRC) == ['""']
    forbidden = (
        "PASSWORDS",
        "PASSWORD_LIST",
        "candidate_password",
        "owner_password",
        "user_password",
        "password_file",
        "common_passwords",
        "try_passwords",
    )
    hits = [name for name in forbidden if name.lower() in _EXTRACT_SRC.lower()]
    assert hits == [], f"抽取模块出现口令回退面：{hits}"


def test_encrypted_constraint_4_no_permission_bypass() -> None:
    """④**不实现权限位改写/绕过**：抽取器默认行为如何即如何。"""
    forbidden = ("_override_encryption", "decrypt_permissions", "/P ", "permissions =")
    hits = [name for name in forbidden if name in _EXTRACT_SRC]
    assert hits == [], f"抽取模块出现权限位旁路面：{hits}"


def test_encrypted_constraint_5_note_leaks_no_password_strength(tmp_path: Path) -> None:
    """⑤`note` **不泄露口令强度信息**：非空口令一律记 `encrypted` 这**一个** token。

    「哪些文件的口令更好猜」的清单本身就是破解辅助面——故闭集里不得出现分化取值。
    """
    produced = PypdfExtractor().extract(_pdf(tmp_path, make_encrypted_pdf()))
    assert produced.note == NOTE_ENCRYPTED
    leaky = ("weak_password", "password_length", "rc4", "aes_256", "cipher")
    hits = [name for name in leaky if name in "|".join(sorted(NOTE_TOKENS)).lower()]
    assert hits == []
    assert [t for t in NOTE_TOKENS if "password" in t or "pwd" in t] == []


# -- §7.3 char_count 同口径 ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [("", 0), ("   \n\t ", 0), ("abc", 3), ("a  b\n c", 5), ("  padded  ", 6)],
)
def test_visible_char_count_collapses_whitespace(text: str, expected: int) -> None:
    assert visible_char_count(text) == expected


# -- §12 AC-7.1 判据小件（T7 与 T19 共用同一实现）-----------------------------------------


def test_edit_distance_basics() -> None:
    assert edit_distance("kitten", "sitting") == 3
    assert edit_distance("", "abc") == 3
    assert edit_distance("same", "same") == 0


def test_best_substring_distance_finds_embedded_pattern() -> None:
    assert best_substring_distance("needle", "a big needle in hay") == 0
    assert best_substring_distance("needle", "a big neadle in hay") == 1


def test_ac_7_1_plain_text_path_title_within_first_window(tmp_path: Path) -> None:
    """纯文本路径判据：标题的归一形出现在正文前 2000 字符内（≤ 0.15）。"""
    title = "Deterministic Extraction of Scholarly Full Text"
    body = "\n".join([title, "Ada Lovelace", *(f"paragraph {i}" for i in range(40))])
    produced = PypdfExtractor().extract(_pdf(tmp_path, make_text_pdf(body)))
    assert title_in_body_ratio(title, produced.text) <= DEFAULT_MAX_RATIO


def test_ac_7_1_grobid_path_title_ratio() -> None:
    """GROBID 路径判据：TEI 标题与 paper.title 的归一化编辑距离比 ≤ 0.15。"""
    assert title_distance_ratio("A Study of Things", "A Study of Things") == 0.0
    assert title_distance_ratio("A Study of Things", "A Study of Thing") <= DEFAULT_MAX_RATIO
    assert title_distance_ratio("A Study of Things", "Totally Different") > DEFAULT_MAX_RATIO


# -- 防御性分支（判别精度不得反过来影响成败判决）------------------------------------------


def test_extractor_rank_of_unknown_or_empty_name() -> None:
    from paper_crawler.pipeline.extract import extractor_rank

    assert extractor_rank(None) is None and extractor_rank("") is None


def test_negative_char_count_is_rejected() -> None:
    with pytest.raises(ValueError, match="char_count"):
        ExtractedText(text="x", extractor="a", extractor_ver="1", suffix=".txt", char_count=-1)


def test_page_iteration_failure_is_corrupt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """页面遍历/解码期抛异常 ⇒ 归 `corrupt`（不逃逸，不误判成 image_only/empty_text）。"""

    def boom(self: pypdf.PdfReader) -> list[object]:
        raise RuntimeError("page tree exploded")

    monkeypatch.setattr(pypdf.PdfReader, "pages", property(boom))
    produced = PypdfExtractor().extract(_pdf(tmp_path, make_text_pdf("body")))
    assert produced.char_count == 0 and produced.note == "corrupt"


def test_image_probe_never_changes_the_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_has_image_xobject` 出错时保守判「无图像」——它只服务 note 精度，不参与成败判决。"""
    from paper_crawler.pipeline.extract import _has_image_xobject

    class Boom:
        @property
        def pages(self) -> list[object]:
            raise RuntimeError("resources unreadable")

    assert _has_image_xobject(Boom()) is False  # type: ignore[arg-type]
    produced = PypdfExtractor().extract(_pdf(tmp_path, make_text_pdf("")))
    assert produced.note == "empty_text"  # 无图像证据 → empty_text，不冒充 image_only


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0.8.1\n", "0.8.1"),
        ('{"version": "0.8.2"}', "0.8.2"),
        ('{"build": "x"}', "unknown"),
        ("{not json", "unknown"),
        ("   ", "unknown"),
    ],
)
def test_grobid_version_payload_parsing(raw: str, expected: str) -> None:
    """[UNRESOLVED]：版本端点格式未实测——纯文本与 JSON 两形态都兜住，取不到即 `unknown`。"""
    from paper_crawler.pipeline.extract import _parse_version_text

    assert _parse_version_text(raw) == expected


# -- P1-7：pypdf 孤立代理字符清洗（畸形 CMap → `\ud800` 等）--------------------------------
#
# 根因：pypdf `_cmap.py` 解析内嵌字体 CMap 时用 `decode("utf-16-be", "surrogatepass")`，
# 畸形/截断的 CMap 数据可让 `page.extract_text()` 产出**孤立代理字符**——它是合法的 Python
# str 元素，却不是合法的 Unicode 标量值，下游 `str.encode("utf-8")`（stages.py 落盘前必经）
# 会对其抛 `UnicodeEncodeError`（非 `CrawlerError`）。修复：抽取器出口统一清洗为 U+FFFD。


def test_sanitize_lone_surrogates_replaces_with_u_fffd() -> None:
    """孤立代理码点 → U+FFFD；其余字符（含普通 Unicode）原样保留。"""
    from paper_crawler.pipeline.extract import _sanitize_lone_surrogates

    dirty = "clean \ud800 text \udfff end"
    clean = _sanitize_lone_surrogates(dirty)
    assert "\ud800" not in clean and "\udfff" not in clean
    assert clean.count("�") == 2
    assert clean == "clean � text � end"
    assert clean.encode("utf-8") == "clean � text � end".encode()  # 必须不抛


def test_sanitize_lone_surrogates_is_a_noop_without_surrogates() -> None:
    from paper_crawler.pipeline.extract import _sanitize_lone_surrogates

    text = "plain ascii + 你好 unicode, no surrogates here"
    assert _sanitize_lone_surrogates(text) == text


def test_extract_sanitizes_lone_surrogates_from_malformed_cmap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """回归锁：`page.extract_text()` 产出孤立代理字符时，`PypdfExtractor` 出口必须已净化——
    否则下游 `.encode("utf-8")` 会抛 `UnicodeEncodeError`，被 runner 误判 TRANSIENT，
    RETRY_TABLE 4 次重试每次 100% 复现后判 FAILED（P1-7 审查实测；design/12 §6.1「畸形
    PDF 属第 2 类不失败任务」）。

    用 monkeypatch 模拟 pypdf 内部对畸形 CMap 的产出——无法用 `helpers.minipdf` 构造真实
    的畸形 CMap 字节流（生成器契约是全 ASCII 源，见 minipdf 模块 docstring），且该缺陷是
    pypdf 库内部实现细节，与既有 `test_page_iteration_failure_is_corrupt` 同一手法。
    """

    class _SurrogatePage:
        def extract_text(self) -> str:
            return "hello \ud800 world"

    monkeypatch.setattr(pypdf.PdfReader, "pages", property(lambda self: [_SurrogatePage()]))
    produced = PypdfExtractor().extract(_pdf(tmp_path, make_text_pdf("placeholder")))

    assert "\ud800" not in produced.text and "\udfff" not in produced.text
    assert produced.text.encode("utf-8") is not None  # 必须不抛
    assert "�" in produced.text
    assert "hello" in produced.text and "world" in produced.text
    assert produced.note is None  # 成功产物：§4.1 不变式要求零 note
    assert produced.char_count == visible_char_count(produced.text) > 0
