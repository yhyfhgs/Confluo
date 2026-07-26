"""DB↔文件双向对账（design/05 §5.4 基础版 + design/12 §9.2 T14 全库扩展）。

`verify_store` 只读比对 `Repo` 中记录的行与磁盘上的实际文件，检出四类不一致
（前三类缺陷 + 第四类信息级，design/12 §9.2 T14 冻结口径），每类给出固定的修复
建议（本函数**不自动修复**——design/05 §5.4 明确"输出修复建议"，动作留给人工
或后续工具）：

## asset 表面（pdf/si 两种 kind，结构同构，design/12 §9.2 si 孤儿判定裁决）

- **missing_file**：某 asset 的 `state == "fetched"`（DB 认定"已取回"），但其 `file_path`
  为空、或指向的文件在磁盘上不存在 → suggestion `"re-fetch"`（记录声称已完成，证据缺失，
  唯一合理动作是重新下载）。
- **orphan_file**：`data_dir/{pdf,si}/` 子树下存在的文件，其路径未出现在任何 asset 的
  `file_path` 中（不论该 asset 处于什么 state）→ suggestion `"adopt"`（磁盘有实体但库中
  无记录，需人工认领或补建索引）。si 每 paper 一目录多文件的布局
  （`si/{venue}/{year}/{paper}/{原名}`，与 pdf 同构）按**文件级**逐个判孤儿——不做目录级
  判定，否则"同 paper 下多 si 文件里少了一个"会被目录内其余文件的存在掩盖。
- **hash_mismatch**：某 asset 的 `file_path` 指向的文件存在、且该 asset 的 `sha256` 非空，
  但对文件重新计算的 sha256 与记录值不同 → suggestion `"quarantine"`（内容与记录的取回
  证据不符，可能损坏或被篡改，先隔离防止污染下游再处理）。此项**不要求** `state ==
  "fetched"`（与 missing_file 不同）：只要"文件存在 + 有记录哈希可比对"就检查，避免遗漏
  例如已标记 `gone` 等状态但磁盘仍留有可疑旧文件的情形。

## fulltext 表面（`fulltext.text_path` 对账，design/12 §9.2）

`fulltext` 行是**本地派生产物**（由源 PDF 重新抽取即可恢复，无需网络）——故本表面的
missing_file/hash_mismatch suggestion 均为 `"re-extract"`（区别于 asset 表面的
`"re-fetch"`/`"quarantine"`）：

- **missing_file**：`text_path` 非空，但解析后文件不存在。
- **hash_mismatch**：文件存在且 `text_sha256` 非空，但实测 sha256 不符（覆盖 T7 设计
  登记的崩溃窗 2 同后缀覆写残留：旧行仍引用该路径、但盘上已是新内容，design/12 §5.5）。
- **orphan_file**：`data_dir/fulltext/**` 下的文件未被任何 `text_path` 引用 →
  suggestion `"prune"`（区别于 asset 侧的 `"adopt"`——孤儿产物可安全删除，下次 extract
  按幂等键重新生成；覆盖崩溃窗 2 换后缀/窗 3 场景的残留，design/12 §5.5）。
- **legacy 行不参与文件对账**：`text_path IS NULL`（涵盖 `state='noop'` 的 Phase 1
  占位行与 `state='extract_failed'` 的已判定失败行——两者均无文件侧）不触发以上三类。

## 第四类：`stale_fulltext`（信息级，design/12 §9.2 新增）

`fulltext.source_sha256` 非空且其 `asset_id` 所指 asset 行的**当前** `sha256` 与之不符
→ `severity="info"`、suggestion `"re-extract"`。语义：asset 被 re-fetch（同一 asset
身份，新文件内容）后，该 fulltext 行仍是**由旧 PDF 抽出的文本**——它自身完全自洽（文件
在、哈希对、路径对，前三类判据全绿），但全文与当前 PDF 已静默错配，没有这一类该错配
会永久隐身。它是可自愈的（下一次 extract 必然重抽取代），故不计入缺陷、不使 `verify`
判 FAIL——调用方（cli.py）须按 `severity` 与前三类分开呈现。`asset_id IS NULL` 的
legacy 行不参与本类判定（该行从未有真实 asset 关联，无当前 sha256 可比）。

返回的 `VerifyIssue` 列表按 `(kind, file_path)` 排序，保证同一份输入产出稳定、可断言的
顺序。范围：`data_dir/{pdf,si,fulltext}/**`；`export/tmp` 等子目录不产出对账产物，
仍留在扫描范围外。

`file_path`/`text_path` 兼容绝对/相对两种写法：绝对路径原样使用；相对路径按 `data_dir`
展开（`Config.data_dir` 恒为绝对路径，但本函数不强制调用方传入绝对路径；`fulltext.
text_path` 的相对形态本就写死为不含 `data/` 前缀，design/12 §5.4，与本模块既有
`_resolve` 语义天然兼容，零改造）。

## T7/T14 合并顺序兼容（design/12 §5.1 + phase7 计划 §5）

T14 可与 T7（真实 extract 落地，含 0004 迁移为 `fulltext` 表新增 asset_id/
source_sha256/text_sha256/state/note 五列）并行——不保证哪一个先合入 main。本模块对
这五列的读取一律经 `_optional_text`，缺列时按"无该信息"处理（如实退化）：
`state` 缺省视为 `"noop"`（Phase 1 `_stage_extract` 唯一产出形态，此时 `text_path`
恒为 NULL，三类文件面判据天然全不触发）；`asset_id`/`source_sha256`/`text_sha256`
缺省则对应的 hash_mismatch/stale_fulltext 判据无法求值、天然不产出（无基准可比，与
既有"`asset.sha256` 为空时不做哈希校验"同一纪律）。T7 合并后五列恒存在，本函数行为
自然收敛到"五列齐全"的完整判据，无需再改。
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from paper_crawler.storage.repo import Repo

_HASH_CHUNK_SIZE = 1 << 20  # 1 MiB 流式读取，避免大 PDF 占用过多内存

# asset 表面的孤儿扫描根（pdf/si 同构，design/12 §9.2）。
_ASSET_ORPHAN_ROOTS: tuple[str, ...] = ("pdf", "si")


@dataclass(frozen=True)
class VerifyIssue:
    """一条对账记录（接口冻结件：phase1-implementation-plan.md「执行期重排记录」；
    design/12 §9.2 追加 `stale_fulltext` kind + `prune`/`re-extract` suggestion +
    `severity` 字段——均为纯附加扩展，既有三类缺陷的字段值与含义不变）。

    `severity`：`"defect"`（默认，前三类）使 `verify` 判非零退出码；`"info"`
    （仅 `stale_fulltext`）是可自愈的提示，不计入缺陷、不影响退出码。
    """

    kind: Literal["missing_file", "orphan_file", "hash_mismatch", "stale_fulltext"]
    asset_id: str | None
    file_path: str
    suggestion: Literal["re-fetch", "adopt", "quarantine", "prune", "re-extract"]
    severity: Literal["defect", "info"] = "defect"


def _resolve(data_dir: Path, raw_path: str) -> Path:
    """把 DB 记录的路径解析为可 stat 的路径：绝对路径原样使用，相对路径挂在 data_dir 下。"""
    candidate = Path(raw_path)
    return candidate if candidate.is_absolute() else data_dir / candidate


def _sha256_of(path: Path) -> str:
    """流式计算文件的 sha256 十六进制摘要。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _optional_text(row: sqlite3.Row, column: str) -> str | None:
    """安全读取 `fulltext` 行的 T7 增量列（asset_id/source_sha256/text_sha256/state/note，
    design/12 §5.1 全为 TEXT）；列尚不存在（T7 的 0004 迁移未合并）时返回 None，使本模块
    在 T7 合并前后均可正确运行（模块 docstring「T7/T14 合并顺序兼容」一节）。
    """
    if column not in row.keys():
        return None
    value = row[column]
    return str(value) if value is not None else None


def _scan_asset_side(repo: Repo, data_dir: Path) -> tuple[list[VerifyIssue], set[Path]]:
    """`asset` 表对账（pdf/si 同构，kind 无关——`repo.list_assets()` 本不按 kind 过滤）。

    返回 (missing_file/hash_mismatch 问题列表, 已记录路径集合)；后者供孤儿扫描剔重。
    """
    issues: list[VerifyIssue] = []
    recorded: set[Path] = set()

    for asset in repo.list_assets():
        raw_path: str | None = asset["file_path"]
        asset_id = str(asset["id"])
        resolved: Path | None = _resolve(data_dir, raw_path) if raw_path else None
        if resolved is not None:
            recorded.add(resolved.resolve())
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

    return issues, recorded


def _scan_asset_orphans(data_dir: Path, recorded: set[Path]) -> list[VerifyIssue]:
    """`data_dir/{pdf,si}/**` 下未被任何 asset `file_path` 引用的文件 → orphan_file（文件级）。"""
    issues: list[VerifyIssue] = []
    for root_name in _ASSET_ORPHAN_ROOTS:
        root = data_dir / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.resolve() not in recorded:
                issues.append(
                    VerifyIssue(
                        kind="orphan_file",
                        asset_id=None,
                        file_path=str(path),
                        suggestion="adopt",
                    )
                )
    return issues


def _scan_fulltext_side(repo: Repo, data_dir: Path) -> tuple[list[VerifyIssue], set[Path]]:
    """`fulltext` 表对账：missing_file/hash_mismatch（suggestion 均 `re-extract`）+
    `stale_fulltext`（信息级）。返回 (问题列表, 已记录路径集合)；后者供孤儿扫描剔重。
    """
    issues: list[VerifyIssue] = []
    recorded: set[Path] = set()

    for row in repo.list_fulltext():
        raw_path: str | None = row["text_path"]
        if raw_path:
            resolved = _resolve(data_dir, raw_path)
            recorded.add(resolved.resolve())
            asset_id = _optional_text(row, "asset_id")
            if not resolved.is_file():
                issues.append(
                    VerifyIssue(
                        kind="missing_file",
                        asset_id=asset_id,
                        file_path=raw_path,
                        suggestion="re-extract",
                    )
                )
            else:
                text_sha256 = _optional_text(row, "text_sha256")
                if text_sha256 and _sha256_of(resolved) != text_sha256:
                    issues.append(
                        VerifyIssue(
                            kind="hash_mismatch",
                            asset_id=asset_id,
                            file_path=raw_path,
                            suggestion="re-extract",
                        )
                    )

        # stale_fulltext（信息级，design/12 §9.2 + §5.3 陈旧判据 rank -2 同一谓词）：
        # legacy 行（asset_id IS NULL）不参与——从未有真实 asset 关联，无当前 sha256 可比。
        asset_id = _optional_text(row, "asset_id")
        source_sha256 = _optional_text(row, "source_sha256")
        if asset_id and source_sha256:
            asset_row = repo.get_asset(asset_id)
            current_sha256 = asset_row["sha256"] if asset_row is not None else None
            if current_sha256 and current_sha256 != source_sha256:
                issues.append(
                    VerifyIssue(
                        kind="stale_fulltext",
                        asset_id=asset_id,
                        file_path=raw_path or "",
                        suggestion="re-extract",
                        severity="info",
                    )
                )

    return issues, recorded


def _scan_fulltext_orphans(data_dir: Path, recorded: set[Path]) -> list[VerifyIssue]:
    """`data_dir/fulltext/**` 下未被任何 `text_path` 引用的文件 → orphan_file，
    suggestion `prune`。
    """
    issues: list[VerifyIssue] = []
    root = data_dir / "fulltext"
    if root.is_dir():
        for path in root.rglob("*"):
            if path.is_file() and path.resolve() not in recorded:
                issues.append(
                    VerifyIssue(
                        kind="orphan_file",
                        asset_id=None,
                        file_path=str(path),
                        suggestion="prune",
                    )
                )
    return issues


def verify_store(repo: Repo, data_dir: Path) -> list[VerifyIssue]:
    """DB↔文件双向对账；只读，不写 DB 也不动磁盘文件（design/05 §5.4 + design/12 §9.2）。"""
    asset_issues, asset_recorded = _scan_asset_side(repo, data_dir)
    fulltext_issues, fulltext_recorded = _scan_fulltext_side(repo, data_dir)
    issues = [
        *asset_issues,
        *fulltext_issues,
        *_scan_asset_orphans(data_dir, asset_recorded),
        *_scan_fulltext_orphans(data_dir, fulltext_recorded),
    ]
    return sorted(issues, key=lambda issue: (issue.kind, issue.file_path))


def count_pending_extraction(repo: Repo) -> int:
    """`state='noop' AND text_path IS NULL` 的 `fulltext` 行数（design/12 §9.2 附注）。

    这些是 Phase 1 `_stage_extract`（noop 语义）留下的占位行——尚未经历一次真实抽取，
    **不是缺陷**（不产出 `VerifyIssue`），如实报为「未真实抽取」信息计数，供 cli.py
    在 `verify` 输出里旁述。`state` 列缺省（T7 迁移未合并）时按 `"noop"` 处理——该 schema
    版本下 `_stage_extract` 只有 noop 一种产出形态，全部行语义上即 noop。
    """
    count = 0
    for row in repo.list_fulltext():
        state = _optional_text(row, "state") or "noop"
        if state == "noop" and row["text_path"] is None:
            count += 1
    return count
