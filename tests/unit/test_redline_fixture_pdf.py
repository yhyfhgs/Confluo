"""AC-0.3 红线守卫（本卡侧）：**`tests/` 树下 `.pdf` 文件数恒为 0**（design/12 §8/§10-6）。

AC-0.3 明文「凭证/session/**PDF** 不出现在 git 历史（`git log` 全历史扫描 + .gitignore 生效
验证）」，且仓库 `.gitignore` 有 `*.pdf` 全局条目（任意层级）——提交一份 fixture PDF 必须
`git add -f` 强推，形式与实质都违规，且会让该红线的守卫面出现「合法的例外」，侵蚀它此后
一切执行力。抽取测试的 PDF 语料一律**程序化生成**（`tests/helpers/minipdf.py`），运行期落
`tmp_path`、随测试结束即弃。

本文件是那条纪律的机器判据：任何人未来「就放一个小样本吧」都会在这里红。
"""

from __future__ import annotations

from pathlib import Path

_TESTS_ROOT = Path(__file__).resolve().parents[1]


def test_no_pdf_files_under_tests_tree() -> None:
    found = [p for p in _TESTS_ROOT.rglob("*.pdf") if p.is_file()]
    assert found == [], (
        "AC-0.3：tests/ 树下不得出现 .pdf 文件（PDF 不入 git 历史）——"
        f"改用 tests/helpers/minipdf.py 的程序化生成器。命中：{[str(p) for p in found]}"
    )


def test_generated_pdf_corpus_is_not_written_into_the_repo() -> None:
    """生成器只产字节（不写文件）——落盘位置由调用方给，测试一律给 `tmp_path`。"""
    from helpers import minipdf

    source = Path(minipdf.__file__).read_text(encoding="utf-8")
    for forbidden in ("write_bytes(", "open(", ".pdf'", '.pdf"'):
        assert forbidden not in source, f"生成器不得自行落盘/引用 .pdf 路径：{forbidden}"
