"""合并引擎核心（Phase 3 T1；接口冻结件 plan §2-1）。

`MergeEngine.ingest(stub, source=…)` 是 aggregator（crossref/dblp/openalex/s2）与 enrich
通道的**收敛入口**：把多源 `PaperStub` 收敛到 identifier 图上的 paper——强合并、字段级
来源优先级收敛（AC-3.4 顺序无关的实现基石）、弱信号候审、跨 paper identifier 冲突裁决。

## 与 `Repo.upsert_paper` 的分工（并存策略，controller 2026-07-22 批准）

- `Repo.upsert_paper(venue_id, issue_id, stub)`：Phase 1/2 **pull 枚举路径**——venue/issue
  绑定、identifier 强合并=补缺不覆盖（无 provenance）。存量保留、零回归。
- `MergeEngine.ingest(stub, *, source)`：Phase 3 **aggregator/enrich 路径**——venue-agnostic
  （冻结签名不带 venue/issue，新建 paper 的 venue_id=NULL），字段级 provenance 收敛 +
  弱信号候审 + 跨 paper 冲突裁决。收敛计划：Phase 3 内全部 aggregator/enrich 流量走本引擎。
- 两路已收敛的一点：identifier 写入均经 `ids.normalize_identifier`（DOI 归一），故混合双路
  （arxiv 经 upsert_paper + crossref 经 ingest）以同一 DOI 无条件强合并（AC-3.1）。

## 裁决点（权威说明，plan §2-1 冻结 + T1 任务卡）

1. **强合并**：stub 任一（归一后）identifier 命中恰一个既有 paper → 并入，字段按下条收敛，
   补 stub 其余 identifier。查→并→补在 `Repo.merge_ingest` 单事务内（防并发裂脑）。
2. **字段级来源优先级收敛**：优先级 `official > crossref > dblp > openalex > s2 > heuristic`
   （`SOURCE_PRIORITY`，D-021 冻结）。新值仅当①现值空 或 ②新源优先级**严格高于**现值来源
   时写入；同级不覆盖 → 任意到达顺序收敛到同一终态。provenance 记于
   `paper.meta_json._field_src`。**未记录来源的存量字段**（upsert_paper pull 路径所写）视为
   **最高优先**——只补空、绝不覆盖（保守保护官方 proceedings 数据）。
3. **跨 paper identifier 冲突**（stub 的 identifier 命中≥2 个不同既有 paper——06 未显写的
   边界）：**不自动合并两 paper**（等价弱信号升级场景）；stub 并入 identifier 数最多者
   （平局取 paper_id 字典序最小者——确定性），其余每个命中 paper 与胜者建
   `candidate_duplicate(evidence=identifier-conflict, decided=NULL)`。指向败者的 identifier
   原地不动、不迁移。**注**：此裁决使「同批 stub 不同注入顺序」可能得不同终态（迟到的桥接
   identifier 得 candidate 而非 merge），故其确定性由定向集成测试锁，不纳入随机顺序属性
   测试（见 tests 说明）。
4. **弱信号候审**：无 identifier 命中 → `title_norm` 精确匹配 + 首作者姓氏一致 → 新建 paper
   + 对每个匹配既有 paper 建 `candidate_duplicate(decided=NULL, confidence, evidence)`。
   **绝不自动合并**（06 §3）。「对每个匹配都建边」保证顺序无关（同簇终态=两两建边）。
5. **candidate 端点定向**：按两 paper 各自最小 identifier `(scheme,value)` 升序定向 from→to
   ——与到达顺序无关（AC-3.4 弱信号定向的确定性）。
6. **幂等**：同一 stub 重复 ingest → identifier 已命中该 paper（强合并分支）、字段同级不覆盖、
   candidate 主键 `ON CONFLICT DO NOTHING` → DB 终态不变。

首作者姓氏：`PaperStub.authors` 冻结为名字串组（types.py），不改 types——由 `authors[0]`
启发式取姓（逗号前段，或末词）再经 `normalize_title` 归一为比对键（best-effort 弱信号）。
"""

from __future__ import annotations

from dataclasses import dataclass

from paper_crawler.ids import normalize_identifier, normalize_title
from paper_crawler.storage.repo import IngestAction, MergeInput, Repo
from paper_crawler.types import PaperStub

# 字段级来源优先级（越大越强，D-021 冻结）。`source` 参数值域即此六枚举。
SOURCE_PRIORITY: dict[str, int] = {
    "official": 5,
    "crossref": 4,
    "dblp": 3,
    "openalex": 2,
    "s2": 1,
    "heuristic": 0,
}


@dataclass(frozen=True)
class IngestResult:
    """`MergeEngine.ingest` 的结果（接口冻结件 §2-1）。

    - `action`：`created`（纯新建，无命中无候审）/ `merged`（强合并入既有 paper）/
      `candidate_flagged`（建了 candidate_duplicate——弱信号新建或跨 paper 冲突并入）。
    - `matched_identifiers`：命中既有 paper 的 `"scheme:value"` 列表；created / 弱信号
      candidate 为空元组（无 identifier 命中），跨冲突 candidate 非空——二者据此可辨。
    """

    paper_id: str
    action: IngestAction
    matched_identifiers: tuple[str, ...]


def _first_author_surname(authors: tuple[str, ...]) -> str | None:
    """从 `authors[0]` 启发式取首作者姓氏并归一为弱信号比对键；无作者 → None。

    切分：含逗号 → 逗号前段（"Smith, Jane"→"Smith"，family-first）；否则末个空白分词
    （"Jane Q. Smith"→"Smith"）。再经 `normalize_title`（大小写/重音/标点折叠）得稳定键。
    best-effort——作者名形态千差万别，弱信号只作候审证据不自动合并，容忍误差。
    """
    if not authors:
        return None
    name = authors[0].strip()
    if not name:
        return None
    surname = name.split(",", 1)[0] if "," in name else name.split()[-1]
    return normalize_title(surname) or None


class MergeEngine:
    """多源 PaperStub 收敛引擎（接口冻结件 §2-1）。策略在此，SQL/事务在 `Repo.merge_ingest`。"""

    def __init__(self, repo: Repo) -> None:
        self._repo = repo

    def ingest(self, stub: PaperStub, *, source: str) -> IngestResult:
        """把一条 `PaperStub` 收敛入库；`source` 须为 `SOURCE_PRIORITY` 六枚举之一。

        归一 identifier（DOI 经 normalize_doi）与 title（弱信号键）、取首作者姓氏后，委托
        `Repo.merge_ingest` 在单事务内完成查/并/补/候审，返回结果包装为 `IngestResult`。
        """
        if source not in SOURCE_PRIORITY:
            raise ValueError(f"unknown source {source!r}; must be one of {sorted(SOURCE_PRIORITY)}")
        identifiers = tuple(
            normalize_identifier(scheme, value) for scheme, value in stub.identifiers
        )
        incoming = MergeInput(
            title=stub.title,
            title_norm=normalize_title(stub.title),
            first_author=_first_author_surname(stub.authors),
            abstract=stub.abstract,
            year=stub.year,
            pub_date=stub.pub_date,
            meta=stub.meta,
            source=source,
            priority=SOURCE_PRIORITY,
        )
        outcome = self._repo.merge_ingest(incoming, identifiers)
        return IngestResult(
            paper_id=outcome.paper_id,
            action=outcome.action,
            matched_identifiers=outcome.matched_identifiers,
        )


__all__ = ["IngestResult", "MergeEngine", "SOURCE_PRIORITY"]
