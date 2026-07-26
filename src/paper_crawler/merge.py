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
   随到达序摆动——故取观测级键集合。
   **这是向下收敛，不是超集（如实）**：原实现用的是**行态键**（当前 title_norm × 当前
   `_first_author`），二者可来自不同观测，能拼出"A 观测的标题 × B 观测的姓氏"这类**跨观测
   拼接键**；观测级键集合不含此类拼接，故对"只有拼接键才撞得上"的候审**漏标**。取舍依据：
   行态键随字段收敛漂移，其匹配面被证明**不可序无关化**（把行态键一并补记的"自然超集"修法
   已被审查实测证伪——行态键本身随到达序摆动，补记只是把顺序敏感搬进键集合）。漏标方向
   fail-safe（宁可漏标不误并，06 §3），且 identifier 证据到达时仍会强合并。
   `IngestResult.action` 口径不变（冻结件）：强合并路径即便顺带建了候审边仍报 `merged`，
   候审边只作为 DB 副作用记录；`candidate_flagged` 仍专指弱信号新建与跨 paper 冲突并入。
5. **candidate 端点定向与唯一性**：一对 paper 至多一条 `candidate_duplicate`（`_upsert_candidate`
   查双向后再落行——`(from,to,kind)` 主键不认方向，只查单向会因定向翻转落出第二行）。新边按
   两 paper 各自最小 identifier `(scheme,value)` 升序定向 from→to。
   **定向不是不变量（如实）**：该锚取自**建边时刻**的 identifier 集合快照，此后 paper 补进更小
   的 identifier 也不重定向（新旧实现同病）——故同一批观测的不同注入序可能落出方向相反的同一条
   边。语义上 `candidate_duplicate` 是**无序对**「这两篇疑似同一著作」，from/to 不承载方向语义：
   消费方（Phase 7 `dedupe review`、测试 dump）一律按无序对处理，比较/去重都不得依赖 from/to
   的字面顺序（`tests/helpers/dbdump.py::dump_paper_relations` 即按此归一）。
   既有边只在**未经人工裁决**且新证据强度不弱于既有时刷新（弱信号刷新共享键全交、identifier
   冲突可升级弱信号边，反向不降级）；**绝不删行**。
6. **幂等**：同一 stub 重复 ingest → identifier 已命中该 paper（强合并分支）、字段同值不覆盖、
   弱信号键已在集合内不重判、candidate 至多一行且证据不变则不写 → DB 终态不变。
7. **preprint_of 建边**（Phase 7 T10；检查单 #5；design/06 §3 单一事实源；机制见
   `repo.py::Repo._apply_preprint_clues`/`_upsert_preprint_relation`）：`Repo.upsert_paper`
   （pull 路径）与本引擎的 `Repo.merge_ingest`（aggregator/enrich 路径，含新建/强合并/冲突
   胜者三分支）在拿到 `paper_id` 后都消费本次观测 `meta` 里的线索——两条写路径共享同一
   机制，因为**真实携带线索的 adapter（arxiv/cvf/openreview）今天走的是 `upsert_paper`
   （pull 路径），并不经过 `MergeEngine.ingest`**（T10 grep 实况核实；仅在 `merge_ingest`
   一处接线不足以让该功能对现有数据生效，故双路径接线是本卡的既遂决定，非任务卡字面
   仅指 `MergeEngine.ingest()` 的原样落地——见 T10 任务报告 NEEDS_DECISION）。
   线索表（meta 键→(目标 identifier scheme, 自身角色)）目前两项：'doi'→自身=预印本
   （`from`，先例 arxiv 的 `journal_ref`/`doi` 回填字段，design/06 §3 原文）；'arxiv'→
   自身=发表版（`to`，先例 cvf/openreview 的 `arxiv` 线索键）。'journal_ref'（arxiv 专属
   自由文本）不可解析为 identifier、不可独立驱动查找，只在同 stub 也带 'doi' 时作为补充
   证据搭车进 `evidence_json`。design/06 §3 另列的"Crossref/OpenAlex 的 preprint 关系
   字段"与"SSRN→DOI 提示"两类：grep 实况核验现有三个 adapter 均未产出此类字段（如实见
   `repo.py` 线索表注释），暂无输入、不在表中——该缺口已在 design/06 §3 补一条注记
   （独立审查 P2-2：产出侧未实现、消费通道已预留、产出侧挂 P8 评估）。
   **方向是语义不变量、不是快照**（与 candidate_duplicate 相反）：from(预印本)→to(发表版)
   写死，同一 (from,to) 组合无论哪一侧线索先发现都落到同一方向，故不需要 candidate 那样
   的双向查询或无序对归一。**建边时机**＝ingest 消费到线索的当下、一次性尝试、不回溯：
   查不到目标端（线索悬空）→ DEBUG 记录后跳过、不建悬空边（controller 裁决③）——这是
   accepted 的顺序敏感/best-effort 语义，不同于弱信号候审的观测级键集合机制，本卡不为其
   补建等价的顺序无关性。`decided` 字段（controller 裁决⑤）：自动建边即生效，NULL 是
   "有效、待人工可选复核"而非 candidate_duplicate 的"待审阻塞"——不进 T13 dedupe review
   流程（那条流程只消费 candidate_duplicate）。**双条 paper 双份全文、不合并**（design/06
   §3 明文：preprint_of 是关联边不是去重合并）——不改动任何既有强合并/弱信号/冲突分支，
   `IngestResult.action` 口径不变（同第 4 条候审边的先例，纯 DB 副作用）。

   **独立审查三处 P1 修复（Opus 14 场景实测矩阵，回派）**：
   ①**双向矛盾环**（`repo.py::_upsert_preprint_relation`）：doi 与 arxiv 两条线索各自
   独立解析目标端，若目标 paper 已把两 scheme 聚合到同一行，会写出方向相反的两条边
   ——双向矛盾环。**首轮修复**（同调用内预判：先全量解析两条线索各自目标，相等则只留
   doi 方向）经 re-review 实测**REOPEN**：四步跨观测时序仍会成环——target 最初只有
   arxiv，self 首次观测（仅 arxiv 线索）建 `target→self`；target 随后经普通强合并聚合
   进 doi；self 再次观测、doi/arxiv 双线索都解析到同一 target，同调用内预判仍会建
   `self→target`，与步骤②遗留、"绝不删行"永存的旧边并存——同调用内预判只堵得住"两条
   线索出现在同一次 `_apply_preprint_clues` 调用"这个更窄的条件，堵不住跨越多次观测、
   target 中间状态发生变化的场景。**终修**：拆除同调用内预判，改在
   `_upsert_preprint_relation` 写入前查一次**反向行** `(to_paper, from_paper,
   kind='preprint_of')`，存在则 DEBUG 记录后跳过（不写、不删旧行——先到先得，方向
   争议留给未来人工 dedupe 流程仲裁）。这一处更底层的守卫同时覆盖同调用内冲突（此时
   "doi 先落地"只是 `_PREPRINT_CLUE_ROLES` 字典声明序的自然结果，不再需要专门预判）与
   跨观测冲突（任意时间间隔、任意中间状态变化都天然覆盖），`_apply_preprint_clues`
   因此简化为单趟循环、不再维护 `resolved` 预解析字典。
   ②**证据溯源字段缺失**：`evidence_json` 原先只记 `reason`/`clue_key`/`clue_value`，
   没有落 `source`（`merge_ingest` 侧 `incoming.source`）/`venue_id`（`upsert_paper` 侧
   同名参数）——controller 裁决③"openreview 历史 'doi' 字段语义存疑，需要靠 evidence
   溯源核实"的前提未落地，裁决即失效。修复：两条写路径各自把自己持有的 provenance
   传入 `_apply_preprint_clues`（关键字参数，互斥——pull 路径无 source、aggregator 路径
   venue-agnostic），写入 evidence（如实记录：不并集、不追加历史，见 P2-1；**latent P2**
   ——溯源字段本身也归"末次观测覆盖"简化族，若同一 paper 先后经两条写路径观测会随最近
   一次写路径翻转，今日不可达：三个线索 adapter 全走 pull 路径，从未经 `merge_ingest`）。
   ③**arxiv 线索归一链错位**：`_apply_preprint_clues` 原对 'arxiv' 线索走通用
   `normalize_identifier`（非 doi scheme 直通、零改动），但 `identifier(scheme='arxiv')`
   写入侧的规范形是**去版本号的 base id**（design/adapters/arxiv.md §3，
   `adapters.arxiv.ids.normalize`）——带版本（`2401.07v2`）/URL 形（cvf 兜底路径、
   openreview 自由文本字段均可能产出）/旧代（`hep-th/9901001v1`）线索值与库内裸 base id
   逐字比对必然不相等，静默悬空。修复：新增 `repo.py::_normalize_arxiv_clue`，复用
   `adapters.arxiv.ids.normalize` 同一条归一链（局部 import，见该函数 docstring 的层次
   纪律先例），解析失败（非法形态）降级为 None、按悬空语义处理，不传播异常炸 ingest。

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
