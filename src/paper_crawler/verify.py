"""DB↔文件双向对账（design/05 §5.4 基础版；AC-3.3 正式验收在 Phase 3，本模块为验收打底）。

`verify_store` 只读比对 `Repo` 中记录的 asset 与 `data_dir/pdf/**` 下的实际文件，检出
design/06 §7 AC-3.3 定义的三类不一致，每类给出固定的修复建议（本函数**不自动修复**——
design/05 §5.4 明确"输出修复建议"，动作留给人工或后续工具）：

- **missing_file**：某 asset 的 `state == "fetched"`（DB 认定"已取回"），但其 `file_path`
  为空、或指向的文件在磁盘上不存在 → suggestion `"re-fetch"`（记录声称已完成，证据缺失，
  唯一合理动作是重新下载）。
- **orphan_file**：`data_dir/pdf/` 子树下存在的文件，其路径未出现在任何 asset 的
  `file_path` 中（不论该 asset 处于什么 state）→ suggestion `"adopt"`（磁盘有实体但库中
  无记录，需人工认领或补建索引）。
- **hash_mismatch**：某 asset 的 `file_path` 指向的文件存在、且该 asset 的 `sha256` 非空，
  但对文件重新计算的 sha256 与记录值不同 → suggestion `"quarantine"`（内容与记录的取回
  证据不符，可能损坏或被篡改，先隔离防止污染下游再处理）。此项**不要求** `state ==
  "fetched"`（与 missing_file 不同）：只要"文件存在 + 有记录哈希可比对"就检查，避免遗漏
  例如已标记 `gone` 等状态但磁盘仍留有可疑旧文件的情形。

返回的 `VerifyIssue` 列表按 `(kind, file_path)` 排序，保证同一份输入产出稳定、可断言的
顺序。范围限定于 `data_dir/pdf/**`（design/06 §4 的主全文目录）；`si/fulltext/export/tmp`
等子目录留待 Phase 3 正式验收扩展。

`file_path` 兼容绝对/相对两种写法：绝对路径原样使用；相对路径按 `data_dir` 展开
（`Config.data_dir` 恒为绝对路径，但本函数不强制调用方传入绝对 `file_path`）。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from paper_crawler.storage.repo import Repo

_HASH_CHUNK_SIZE = 1 << 20  # 1 MiB 流式读取，避免大 PDF 占用过多内存


@dataclass(frozen=True)
class VerifyIssue:
    """一条对账不一致记录（接口冻结件：phase1-implementation-plan.md「执行期重排记录」）。"""

    kind: Literal["missing_file", "orphan_file", "hash_mismatch"]
    asset_id: str | None
    file_path: str
    suggestion: Literal["re-fetch", "adopt", "quarantine"]


def _resolve(data_dir: Path, raw_path: str) -> Path:
    """把 DB 记录的 file_path 解析为可 stat 的路径：绝对路径原样使用，相对路径挂在 data_dir 下。"""
    candidate = Path(raw_path)
    return candidate if candidate.is_absolute() else data_dir / candidate


def _sha256_of(path: Path) -> str:
    """流式计算文件的 sha256 十六进制摘要。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_store(repo: Repo, data_dir: Path) -> list[VerifyIssue]:
    """DB↔文件双向对账；只读，不写 DB 也不动磁盘文件（design/05 §5.4）。"""
    issues: list[VerifyIssue] = []
    recorded_paths: set[Path] = set()

    for asset in repo.list_assets():
        raw_path: str | None = asset["file_path"]
        asset_id = str(asset["id"])
        resolved: Path | None = _resolve(data_dir, raw_path) if raw_path else None
        if resolved is not None:
            recorded_paths.add(resolved.resolve())
        file_exists = resolved is not None and resolved.is_file()

        if asset["state"] == "fetched" and not file_exists:
            issues.append(
                VerifyIssue(
                    kind="missing_file",
                    asset_id=asset_id,
                    file_path=raw_path or "",
                    suggestion="re-fetch",
                )
            )
        elif resolved is not None and file_exists:
            recorded_sha256: str | None = asset["sha256"]
            if recorded_sha256 and _sha256_of(resolved) != recorded_sha256:
                issues.append(
                    VerifyIssue(
                        kind="hash_mismatch",
                        asset_id=asset_id,
                        file_path=raw_path or "",
                        suggestion="quarantine",
                    )
                )

    pdf_root = data_dir / "pdf"
    if pdf_root.is_dir():
        for path in pdf_root.rglob("*"):
            if path.is_file() and path.resolve() not in recorded_paths:
                issues.append(
                    VerifyIssue(
                        kind="orphan_file",
                        asset_id=None,
                        file_path=str(path),
                        suggestion="adopt",
                    )
                )

    return sorted(issues, key=lambda issue: (issue.kind, issue.file_path))
