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
   （`SOURCE_PRIORITY`，D-021 冻结）。新值仅当①现值空、②新源优先级**严格高于**现值来源、
   或③**同级但值序更小**时写入。provenance 记于 `paper.meta_json._field_src`。**未记录来源的
   存量字段**（upsert_paper pull 路径所写）视为**最高优先**——只补空、绝不覆盖（保守保护官方
   proceedings 数据）。
   ③是 Phase 6 F1 修补的顺序敏感缝（审计 P3「同源二次观测异值先到胜」）：六枚举优先级两两
   互异，故"同级"只可能是**同一来源的二次观测**给出不同值；原实现同级一律不覆盖=先到者胜
   （顺序敏感）。改判为取值序更小者（`repo._prefers_on_tie`）——`min` 幂等+交换+结合，任意
   到达顺序收敛同一终值；跨源冲突仍完全由优先级表裁决，tie-break 不介入。
3. **跨 paper identifier 冲突**（stub 的 identifier 命中≥2 个不同既有 paper——06 未显写的
   边界）：**不自动合并两 paper**（等价弱信号升级场景）；stub 并入 identifier 数最多者
   （平局取 paper_id 字典序最小者——确定性），其余每个命中 paper 与胜者建
   `candidate_duplicate(evidence=identifier-conflict, decided=NULL)`。指向败者的 identifier
   原地不动、不迁移。
   **顺序敏感性（如实）**：本裁决使含"桥接 identifier"的输入类**顺序敏感**，同批 stub 不同
   注入序会产生**真实数据差**（非等价数据态）——①桥接 stub **先到**时该 stub 直接携多 id
   建成单 paper、**无任何候审痕迹**（保守侧、非不变量：宁可漏标不误并）；后到时才裂成两
   paper + 候审边。②平局胜者随 paper 创建序（ULID）摆动。差异体现在 paper 行数 / 桥字段
   落点 / 候审边有无。但这是既定语义的数学必然且**零丢失**：identifier 值集不变、绝不删行。
   故该输入类不纳入随机顺序属性测试，其确定性由定向集成测试（`test_merge`）单独锁。
4. **弱信号候审**：匹配键 = `(title_norm, 首作者姓氏)`，**观测级**——每次 ingest（新建/强合并/
   冲突并入三条路径全覆盖）都把本次观测的键并入该 paper 的**键集合**（schema v3
   `paper_weak_key` 表，单调只增、不被上条的字段收敛改写），新键触发重判：对每个曾观测到同一
   键的既有 paper 建 `candidate_duplicate(decided=NULL, confidence, evidence)`。**绝不自动合并**
   （06 §3）。终态候审边 = 「键集合有交的每一对 paper」——输入集合（而非到达序）的函数。
   键任一为空（无标题归一形/无首作者）不参与匹配，避免空键误配。
   **F1 修复的缝（审计 P1）**：原实现拿 paper 行的**当前** title_norm/`_first_author` 当键、且
   只在新建分支判定，后到的高优先源改写标题即抹掉匹配面——同一批观测按不同序注入得到不同
   候审边数（实测 A,B,C→1 边 / C,A,B→0 边）。方向 fail-safe（漏标不误并）但违反 AC-3.4。
   审计所列两个候选修法经反例检验均**不足**：仅「收敛改键后重判」漏掉"低优先观测的键先于
   对家出现"的历史匹配；「冻结 title_norm 不参与收敛」则把键钉在**建行观测**上，而建行者本身
   随到达序摆动——故取观测级键集合（两者的闭包）。
   `IngestResult.action` 口径不变（冻结件）：强合并路径即便顺带建了候审边仍报 `merged`，
   候审边只作为 DB 副作用记录；`candidate_flagged` 仍专指弱信号新建与跨 paper 冲突并入。
5. **candidate 端点定向与唯一性**：一对 paper 至多一条 `candidate_duplicate`（`_upsert_candidate`
   查双向后再落行——`(from,to,kind)` 主键不认方向，只查单向会因 identifier 集合增长导致的定向
   翻转落出第二行）。新边按两 paper 各自最小 identifier `(scheme,value)` 升序定向 from→to
   ——与到达顺序无关（AC-3.4 弱信号定向的确定性）。既有边只在**未经人工裁决**且新证据强度不弱
   于既有时刷新（弱信号刷新共享键全交、identifier 冲突可升级弱信号边，反向不降级）；**绝不删行**。
6. **幂等**：同一 stub 重复 ingest → identifier 已命中该 paper（强合并分支）、字段同值不覆盖、
   弱信号键已在集合内不重判、candidate 至多一行且证据不变则不写 → DB 终态不变。

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
