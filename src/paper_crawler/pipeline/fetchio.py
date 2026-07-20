"""下载原子性支持：`*.part` 暂存 → 校验前置 → 原子 rename（design/05 §5.2）。

接口冻结件（`docs/plan/phase1-implementation-plan.md` §执行期重排记录，T7a
补充签名）。`FetchIO` 协议（`types.py` §2.2）由 pipeline 提供实现，adapter 只管
把字节流交给 `write_stream`；是否落位（魔数/大小/哈希是否符合预期）由 pipeline
runner（T7c）在 `commit` 前判断，本模块只提供机制，不做业务校验：

- `PartFileIO.write_stream`：流式写 `{tmp_dir}/{asset_id}.part`，边写边累加
  sha256 与字节数，不整块驻内存；对同一实例重复调用 = 覆盖重写（"wb" 模式天然
  截断到 0 长度再写），承接 adapter 因 TRANSIENT 重试 fetch 时无需更换实例的
  幂等语义。
- `PartFileIO.commit`：目标父目录 `mkdir(parents=True)` 后 `os.replace` 原子
  落位（同文件系统前提下）；`os.replace` 允许目标已存在并直接覆盖，故 commit
  对已有同名文件是覆盖而非报错。
- `PartFileIO.abort`：删 `.part`，不存在也不报错（幂等），供任意错误路径清理。
- `cleanup_tmp`：进程启动时清理残留 `.part`（"崩溃残留 *.part 启动时清理"）。
- `validate_pdf_magic`：expected_type=pdf 时的魔数校验（头部 5 字节 `%PDF-`）。
"""

import hashlib
import os
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from paper_crawler.types import FetchIO

_PDF_MAGIC = b"%PDF-"


class PartFileIO:
    """`FetchIO` 协议实现：流式写 `{tmp_dir}/{asset_id}.part`，供 pipeline 校验+提交。"""

    def __init__(self, tmp_dir: Path, asset_id: str) -> None:
        self._tmp_dir = tmp_dir
        self._asset_id = asset_id

    @property
    def part_path(self) -> Path:
        """本次下载的 `.part` 临时文件路径。"""
        return self._tmp_dir / f"{self._asset_id}.part"

    def write_stream(self, chunks: Iterable[bytes]) -> tuple[int, str]:
        """流式写入 `chunks` 到 `part_path`（覆盖重写），返回 `(bytes_written, sha256_hex)`。"""
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        bytes_written = 0
        with self.part_path.open("wb") as handle:
            for chunk in chunks:
                handle.write(chunk)
                digest.update(chunk)
                bytes_written += len(chunk)
        return bytes_written, digest.hexdigest()

    def commit(self, final_path: Path) -> None:
        """把 `part_path` 原子 rename 到 `final_path`（先建父目录；假定同文件系统）。"""
        final_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(self.part_path, final_path)

    def abort(self) -> None:
        """删除 `part_path`；不存在也不报错（幂等）。"""
        self.part_path.unlink(missing_ok=True)


if TYPE_CHECKING:
    # mypy 静态断言：PartFileIO 结构性满足 FetchIO 协议（write_stream 签名一致）。
    # `if TYPE_CHECKING` 块在运行时不执行、且被 pyproject.toml 的 coverage
    # exclude_also 排除，仅供 `mypy src`（make type）校验——FetchIO 未标
    # `@runtime_checkable`，无法用 isinstance 在运行时验证协议满足性。
    _: FetchIO = PartFileIO(Path(), "")


def validate_pdf_magic(path: Path) -> bool:
    """文件头 5 字节是否等于 PDF 魔数 `%PDF-`（design/05 §4 integrity 校验规则之一）。"""
    with path.open("rb") as handle:
        header = handle.read(len(_PDF_MAGIC))
    return header == _PDF_MAGIC


def cleanup_tmp(tmp_dir: Path) -> int:
    """删除 `tmp_dir` 下全部 `*.part`（启动清理，design/05 §5.2）；返回清理数量。

    `tmp_dir` 不存在（例如从未下载过任何东西的全新 home）视为"无残留"，返回 0
    而非报错——启动清理必须对全新环境静默通过。
    """
    if not tmp_dir.is_dir():
        return 0
    removed = 0
    for part_file in tmp_dir.glob("*.part"):
        part_file.unlink()
        removed += 1
    return removed


__all__ = ["PartFileIO", "cleanup_tmp", "validate_pdf_magic"]
