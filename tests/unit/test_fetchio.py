"""fetchio.py（T7a，接口冻结件§执行期重排记录）单测。

覆盖 `PartFileIO`（写 *.part → 校验前置 → 原子 commit → abort）、
`validate_pdf_magic`、`cleanup_tmp`。语义依据：design/05 §5.2
（"下载到 *.part 临时名 → 校验 → 原子 rename；崩溃残留启动清理"）。
"""

import hashlib
import os
from pathlib import Path

from paper_crawler.pipeline.fetchio import PartFileIO, cleanup_tmp, validate_pdf_magic
from paper_crawler.types import FetchIO

# ---------------------------------------------------------------------------
# part_path
# ---------------------------------------------------------------------------


def test_part_path_is_tmp_dir_slash_asset_id_dot_part(tmp_path: Path) -> None:
    io = PartFileIO(tmp_path, "asset42")
    assert io.part_path == tmp_path / "asset42.part"


# ---------------------------------------------------------------------------
# write_stream：流式写入、返回值、文件内容
# ---------------------------------------------------------------------------


def test_write_stream_writes_concatenated_chunks_to_part_file(tmp_path: Path) -> None:
    io = PartFileIO(tmp_path, "asset1")

    bytes_written, sha256_hex = io.write_stream([b"hello ", b"world"])

    assert io.part_path.read_bytes() == b"hello world"
    assert bytes_written == 11
    assert sha256_hex == hashlib.sha256(b"hello world").hexdigest()


def test_write_stream_creates_tmp_dir_if_missing(tmp_path: Path) -> None:
    tmp_dir = tmp_path / "nested" / "tmp"
    assert not tmp_dir.exists()

    io = PartFileIO(tmp_dir, "asset1")
    io.write_stream([b"x"])

    assert tmp_dir.is_dir()
    assert io.part_path.read_bytes() == b"x"


def test_write_stream_with_empty_iterable_produces_empty_file(tmp_path: Path) -> None:
    io = PartFileIO(tmp_path, "empty")

    bytes_written, sha256_hex = io.write_stream([])

    assert bytes_written == 0
    assert io.part_path.read_bytes() == b""
    assert sha256_hex == hashlib.sha256(b"").hexdigest()


def test_write_stream_with_empty_byte_chunks_interspersed(tmp_path: Path) -> None:
    io = PartFileIO(tmp_path, "empty-interspersed")

    bytes_written, sha256_hex = io.write_stream([b"", b"data", b""])

    assert bytes_written == 4
    assert io.part_path.read_bytes() == b"data"
    assert sha256_hex == hashlib.sha256(b"data").hexdigest()


def test_write_stream_large_payload_split_into_many_small_chunks_matches_whole_blob_hash(
    tmp_path: Path,
) -> None:
    # 随机负载：断言只跟 hashlib 直接对整块计算的结果比较，不依赖硬编码哈希值。
    payload = os.urandom(600_000)
    chunk_size = 777  # 刻意选非整除的尺寸，制造不对齐的分片边界
    chunks = [payload[i : i + chunk_size] for i in range(0, len(payload), chunk_size)]
    assert len(chunks) > 1  # 确保确实是"分片"而非一次性整块

    io = PartFileIO(tmp_path, "big")
    bytes_written, sha256_hex = io.write_stream(chunks)

    assert bytes_written == len(payload)
    assert sha256_hex == hashlib.sha256(payload).hexdigest()
    assert io.part_path.read_bytes() == payload


# ---------------------------------------------------------------------------
# write_stream：重复调用同一实例 = 覆盖重写（幂等重试语义）
# ---------------------------------------------------------------------------


def test_repeated_write_stream_on_same_instance_overwrites_not_appends(tmp_path: Path) -> None:
    io = PartFileIO(tmp_path, "retry")

    io.write_stream([b"first attempt payload"])
    bytes_written, sha256_hex = io.write_stream([b"second"])

    # 覆盖重写：文件内容是第二次调用的结果，而不是两次拼接。
    assert io.part_path.read_bytes() == b"second"
    assert bytes_written == 6
    assert sha256_hex == hashlib.sha256(b"second").hexdigest()


def test_repeated_write_stream_with_shorter_payload_truncates_old_tail(tmp_path: Path) -> None:
    # 关键回归点：若实现误用非截断的写模式（如先 seek(0) 再写不截断），
    # 第二次更短的负载会残留第一次的尾部字节。
    io = PartFileIO(tmp_path, "retry-shrink")

    io.write_stream([b"0123456789"])  # 10 字节
    io.write_stream([b"ab"])  # 2 字节，短于上一次

    assert io.part_path.read_bytes() == b"ab"


def test_repeated_write_stream_returns_fresh_hash_not_accumulated(tmp_path: Path) -> None:
    io = PartFileIO(tmp_path, "retry-hash")

    io.write_stream([b"aaaaaaaaaa"])
    _, second_hash = io.write_stream([b"bb"])

    assert second_hash == hashlib.sha256(b"bb").hexdigest()


# ---------------------------------------------------------------------------
# commit：原子落位、父目录创建、覆盖已存在目标、part 文件消失
# ---------------------------------------------------------------------------


def test_commit_moves_part_file_to_final_path(tmp_path: Path) -> None:
    io = PartFileIO(tmp_path / "tmp", "asset1")
    io.write_stream([b"%PDF-1.4\ncontent"])
    final_path = tmp_path / "pdf" / "venue" / "2024" / "paper.pdf"

    io.commit(final_path)

    assert final_path.read_bytes() == b"%PDF-1.4\ncontent"


def test_commit_creates_final_parent_directories(tmp_path: Path) -> None:
    io = PartFileIO(tmp_path / "tmp", "asset1")
    io.write_stream([b"data"])
    final_path = tmp_path / "a" / "b" / "c" / "paper.pdf"
    assert not final_path.parent.exists()

    io.commit(final_path)

    assert final_path.parent.is_dir()
    assert final_path.exists()


def test_commit_removes_part_file(tmp_path: Path) -> None:
    io = PartFileIO(tmp_path / "tmp", "asset1")
    io.write_stream([b"data"])
    final_path = tmp_path / "paper.pdf"

    io.commit(final_path)

    assert not io.part_path.exists()


def test_commit_overwrites_existing_final_path(tmp_path: Path) -> None:
    final_path = tmp_path / "pdf" / "paper.pdf"
    final_path.parent.mkdir(parents=True)
    final_path.write_bytes(b"OLD CONTENT FROM PRIOR RUN")

    io = PartFileIO(tmp_path / "tmp", "asset1")
    io.write_stream([b"NEW CONTENT"])
    io.commit(final_path)

    # os.replace 的覆盖语义：已存在的同名目标被直接替换，不报错。
    assert final_path.read_bytes() == b"NEW CONTENT"
    assert not io.part_path.exists()


# ---------------------------------------------------------------------------
# abort：删除 .part，幂等
# ---------------------------------------------------------------------------


def test_abort_removes_part_file(tmp_path: Path) -> None:
    io = PartFileIO(tmp_path, "asset1")
    io.write_stream([b"data"])
    assert io.part_path.exists()

    io.abort()

    assert not io.part_path.exists()


def test_abort_is_idempotent_when_part_file_never_existed(tmp_path: Path) -> None:
    io = PartFileIO(tmp_path, "never-written")

    io.abort()  # 不应抛异常
    io.abort()  # 再次调用同样不应抛异常


def test_abort_is_idempotent_after_already_aborted(tmp_path: Path) -> None:
    io = PartFileIO(tmp_path, "asset1")
    io.write_stream([b"data"])

    io.abort()
    io.abort()  # 第二次调用（文件已不存在）不应抛异常


# ---------------------------------------------------------------------------
# validate_pdf_magic
# ---------------------------------------------------------------------------


def test_validate_pdf_magic_true_for_pdf_header(tmp_path: Path) -> None:
    path = tmp_path / "x.pdf"
    path.write_bytes(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj")

    assert validate_pdf_magic(path) is True


def test_validate_pdf_magic_false_for_non_pdf_content(tmp_path: Path) -> None:
    path = tmp_path / "x.html"
    path.write_bytes(b"<html><body>not a pdf</body></html>")

    assert validate_pdf_magic(path) is False


def test_validate_pdf_magic_false_for_file_shorter_than_magic(tmp_path: Path) -> None:
    path = tmp_path / "short.bin"
    path.write_bytes(b"%PD")  # 仅 3 字节，不足 5 字节魔数长度

    assert validate_pdf_magic(path) is False


def test_validate_pdf_magic_false_for_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.bin"
    path.write_bytes(b"")

    assert validate_pdf_magic(path) is False


# ---------------------------------------------------------------------------
# cleanup_tmp
# ---------------------------------------------------------------------------


def test_cleanup_tmp_removes_all_part_files_and_returns_count(tmp_path: Path) -> None:
    (tmp_path / "a.part").write_bytes(b"x")
    (tmp_path / "b.part").write_bytes(b"y")
    (tmp_path / "keep.txt").write_bytes(b"z")  # 非 .part，不应被删

    removed = cleanup_tmp(tmp_path)

    assert removed == 2
    assert not (tmp_path / "a.part").exists()
    assert not (tmp_path / "b.part").exists()
    assert (tmp_path / "keep.txt").exists()


def test_cleanup_tmp_returns_zero_when_dir_missing(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"

    assert cleanup_tmp(missing) == 0


def test_cleanup_tmp_returns_zero_when_dir_empty(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    assert cleanup_tmp(empty_dir) == 0


# ---------------------------------------------------------------------------
# 崩溃模拟：write_stream 后不 commit/abort（视作进程被杀）→ 重启期 cleanup_tmp 清掉
# ---------------------------------------------------------------------------


def test_crash_simulation_uncommitted_part_file_is_cleaned_on_restart(tmp_path: Path) -> None:
    tmp_dir = tmp_path / "tmp"
    io = PartFileIO(tmp_dir, "asset-crashed")
    io.write_stream([b"%PDF-1.4\n" + b"0" * 2048])
    assert io.part_path.exists()  # 模拟的"崩溃点"：commit 从未被调用就中断

    # 模拟进程重启：新一轮启动清理扫描同一个 tmp_dir。
    removed = cleanup_tmp(tmp_dir)

    assert removed == 1
    assert not io.part_path.exists()


def test_crash_simulation_only_removes_part_files_not_other_assets_tmp(tmp_path: Path) -> None:
    tmp_dir = tmp_path / "tmp"
    crashed = PartFileIO(tmp_dir, "asset-crashed")
    crashed.write_stream([b"partial"])
    survivor = PartFileIO(tmp_dir, "asset-in-progress")
    survivor.write_stream([b"still writing"])

    removed = cleanup_tmp(tmp_dir)

    # 两个 .part 都会被清理——启动清理是无差别的（design/05 §5.2：不存在"部分清理"）；
    # 断言点在于返回计数与目录最终状态精确对应，而不是误删非 .part 邻居。
    assert removed == 2
    assert list(tmp_dir.glob("*.part")) == []


# ---------------------------------------------------------------------------
# 端到端：write → commit 全流程产出可被 validate_pdf_magic 识别的文件
# ---------------------------------------------------------------------------


def test_full_lifecycle_write_then_commit_yields_valid_pdf_file(tmp_path: Path) -> None:
    payload = b"%PDF-1.4\n% 10.9999/mock_journal.1.1.0\n" + b"0" * 2048 + b"\n%%EOF\n"
    chunks = [payload[i : i + 16] for i in range(0, len(payload), 16)]
    tmp_dir = tmp_path / "tmp"
    final_path = tmp_path / "pdf" / "mock_journal" / "2024" / "01ARZ3NDEKTSV4RRFFQ69G5FAV.pdf"

    io = PartFileIO(tmp_dir, "asset-xyz")
    bytes_written, sha256_hex = io.write_stream(chunks)
    assert bytes_written == len(payload)
    assert sha256_hex == hashlib.sha256(payload).hexdigest()

    io.commit(final_path)

    assert validate_pdf_magic(final_path) is True
    assert final_path.read_bytes() == payload
    assert not io.part_path.exists()


# ---------------------------------------------------------------------------
# FetchIO 协议：运行时形态检查
# （结构性满足性由 mypy 静态断言，见 fetchio.py 模块内 TYPE_CHECKING 块——
#  types.FetchIO 未标 @runtime_checkable，无法在运行时 isinstance 校验。）
# ---------------------------------------------------------------------------


def test_partfileio_write_stream_is_usable_through_fetchio_typed_reference(tmp_path: Path) -> None:
    io: FetchIO = PartFileIO(tmp_path, "shape-check")

    result = io.write_stream([b"ok"])

    assert result == (2, hashlib.sha256(b"ok").hexdigest())
