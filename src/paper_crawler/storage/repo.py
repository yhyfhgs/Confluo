"""仓储层：领域实体的读写与幂等 upsert（接口冻结件 §2.4 `Repo`）。

关键语义：
- `upsert_paper` 强合并（design/06 §3）：identifier (scheme,value) 命中 → 复用既有
  paper，字段仅补缺不覆盖非空。
- `upsert_issue` 幂等键 UNIQUE(venue_id,volume,number,label)。SQLite UNIQUE 视 NULL 互不相等
  （会议 issue volume/number 为 NULL），故在事务内以业务键 SELECT 后 INSERT（方言中性；
  Phase 1 串行 runner 天然并发安全，见风险表"WAL 单写者"）。
- `plan_asset` 幂等键 UNIQUE(paper_id,kind,version)，version 可空同样 NULL 语义，走查后插；
  已 fetched 的资产再 plan 不回退状态。
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from paper_crawler.errors import CrawlerError, ErrorClass, SubscriptionInvalid
from paper_crawler.ids import normalize_identifier, normalize_title
from paper_crawler.obslog import log_event, redact
from paper_crawler.storage.db import Database
from paper_crawler.types import (
    AssetPlan,
    IssueRef,
    PaperStub,
    VenueSpec,
    new_ulid,
    utcnow_iso,
)

if TYPE_CHECKING:  # 仅类型：运行期由 SubscriptionRepo 内的局部 import 承担（见其 docstring）
    from paper_crawler.subs.model import Subscription

# MergeEngine.ingest 的动作枚举（接口冻结件 §2-1）。定义在 repo 层，供 merge.py 复用其
# `IngestResult.action` 的类型——避免 repo→merge 反向导入形成环（merge 依赖 repo）。
IngestAction = Literal["created", "merged", "candidate_flagged"]

# 弱信号候审 / 跨 paper identifier 冲突的 candidate_duplicate 置信度（固定常量→确定性）。
_WEAK_SIGNAL_CONFIDENCE = 0.5
_IDENTIFIER_CONFLICT_CONFIDENCE = 0.9
# candidate_duplicate 的 evidence reason 标签与其"证据强度"序（越大越强）。同一对 paper 至多
# 一条 candidate_duplicate（见 `_upsert_candidate`）：证据不弱于既有者才刷新，弱者不覆盖强者。
# 未登记的 reason（如迁移写的 `doi-normalization-collision`）视为最强——绝不被覆盖。
_WEAK_SIGNAL_REASON = "weak-signal-title-author"
_IDENTIFIER_CONFLICT_REASON = "identifier-conflict"
_EVIDENCE_STRENGTH: dict[str, float] = {_WEAK_SIGNAL_REASON: 0.0, _IDENTIFIER_CONFLICT_REASON: 1.0}
# 未知来源（无 provenance 记录的存量字段，如 upsert_paper pull 路径所写）的优先级视为
# **最高**——只补空、绝不被覆盖，保守保护既有（多为官方 proceedings）数据。
_UNKNOWN_RANK = float("inf")
# 同级 tie-break 中按"值本身的自然序"取小的字段（year 为 int、pub_date 为 ISO 前缀可比字符串
# ——两者的 min 都等于"更早的那次观测"）。其余字段是自由文本，走"更长者胜"复合序，
# 见 `_prefers_on_tie`。
_ORDERED_SCALAR_FIELDS = frozenset({"year", "pub_date"})

# preprint_of 建边线索表（T10，检查单 #5；design/06 §3 单一事实源）。meta 键→(目标
# identifier scheme, 自身在边中的角色)。角色 "from"=自身是预印本、"to"=自身是发表版——
# 语义由线索键本身固定，与产出该线索的 adapter 无关：
#   - 'doi'：自身回填了发表版 DOI（先例：arxiv 的 `journal_ref`/`doi` 回填字段，design/06
#     §3 原文逐字；openreview 同键同语义，见 `adapters/openreview/parse.py` docstring
#     "跨源关联线索...Phase 3 ingest 建边——arxiv R3 裁决先例"）；
#   - 'arxiv'：自身链接了预印本的 arXiv id（先例：cvf `META_ARXIV`/openreview `arxiv` 线索键，
#     两处 adapter docstring 均明文"线索、不产 identifier——防跨源早合并，先例 arxiv/
#     openreview"）。
# 'journal_ref'（arxiv 专属自由文本，doi 回填的伴随字段）无法解析为 identifier，故不入本
# 表——只在同一 stub 也带 'doi' 时作为补充证据搭车进 evidence_json，不单独触发查找。
#
# **核验偏离（如实记录，T10 任务报告 NEEDS_DECISION 复述）**：design/06 §3 另列"Crossref/
# OpenAlex 的 preprint 关系字段"与"SSRN→DOI 提示"两类线索——grep 实况核验：现有
# `adapters/{crossref,openalex,ssrn}/parse.py` 均**未产出**此类字段（crossref meta 仅
# volume/issue；openalex meta 仅 is_oa/oa_status/oa_url/pdf_url；ssrn 是给同一 paper 补第
# 二 identifier `(ssrn, abstract_id)`，同一著作同一 paper 行，非跨 paper 线索）。本卡消费
# "已落地的线索"，不新增 adapter 解析能力，故这两类线索暂无输入、本表不含对应项。
_PREPRINT_CLUE_ROLES: dict[str, tuple[str, Literal["from", "to"]]] = {
    "doi": ("doi", "from"),
    "arxiv": ("arxiv", "to"),
}
# 线索均为归一 identifier 精确匹配（非启发式），强度对等、无 weak/strong 分级——故
# `_upsert_preprint_relation` 不需要 `_upsert_candidate` 那套 `_EVIDENCE_STRENGTH` 序，
# 刷新规则简化为"未裁决 + 证据有变化即刷新"（仍不覆盖已裁决行、不物理删行，同构于
# `_upsert_candidate` 的两条底线；证据终态取末次观测、非并集、可降级——与
# `_upsert_candidate` 的不降级族刻意分岔，见 `_upsert_preprint_relation` docstring）。
_PREPRINT_CLUE_CONFIDENCE = 1.0

# 'arxiv' 线索值的 URL 包装前缀（`https://arxiv.org/abs/...`、`http://www.arxiv.org/abs/...`
# 等）——独立审查 P1-3：cvf `_arxiv_id_from_href` 对不匹配形状的 href"原样返回（防御性）"、
# openreview `note.arxiv` 是用户自由填写字段，均可能把完整 URL 落入 meta，需在归一前剥离。
_ARXIV_CLUE_URL_PREFIX_RE = re.compile(r"^(?:https?://)?(?:www\.)?arxiv\.org/abs/", re.IGNORECASE)


def _normalize_arxiv_clue(raw_value: str) -> str | None:
    """'arxiv' 线索值 → 规范 base id（去版本号+去 URL 前缀+旧代小写）；解析失败→None。

    独立审查 P1-3（实测 #8/#9）：`_apply_preprint_clues` 原先对 'arxiv' 线索走通用
    `normalize_identifier`（非 doi scheme 直通、零改动），而 `identifier(scheme='arxiv')`
    的写入侧按 design/adapters/arxiv.md §3 是**去版本号的规范 base id**（`adapters.arxiv.
    ids.normalize`）——带版本（`2401.07v2`）/URL 形（`https://arxiv.org/abs/...`，cvf 兜底
    路径与 openreview 自由文本字段均可能产出）/旧代（`hep-th/9901001v1`）线索值与库内裸
    base id 逐字比对必然不相等，静默悬空、边建不出来。本函数复用 `adapters.arxiv.ids`
    同一条归一链（先剥 URL 前缀，再走该模块的去版本+旧代小写逻辑），使线索值与写入侧同
    规范形。

    局部 import（避免 storage 层顶层依赖 adapter 子包，沿 `_row_to_subscription`/
    `db.py::_backfill_title_norm` "局部 import 避免 storage 层顶层依赖上层模块"先例）。
    `adapters.arxiv.ids.normalize` 对非法形态 raise `CrawlerError(PARSE)`——该设计面向
    adapter 自身受控解析（细分类交 catalog 层），但线索值是自由文本 meta（非受控解析），
    坏值不应传播异常炸掉整个 ingest 事务，故此处捕获后降级为 None（调用方按"无法解析"
    处理，同悬空语义：DEBUG 记录、跳过、不建边）。
    """
    from paper_crawler.adapters.arxiv import ids as arxiv_ids

    stripped = _ARXIV_CLUE_URL_PREFIX_RE.sub("", raw_value.strip())
    try:
        return arxiv_ids.normalize(stripped)
    except CrawlerError:
        return None


@dataclass(frozen=True)
class IngestOutcome:
    """`Repo.merge_ingest` 的返回值——`MergeEngine.ingest` 原样包装为 `IngestResult`。

    与 `IngestResult` 字段一一对应，独立于 merge.py 存在以断开 repo↔merge 导入环。
    """

    paper_id: str
    action: IngestAction
    matched_identifiers: tuple[str, ...]


@dataclass(frozen=True)
class MergeInput:
    """`Repo.merge_ingest` 的入参字段包（merge↔repo 契约）——由 `MergeEngine` 构造并归一
    （identifiers/title_norm/first_author 归一、注入 `priority` 优先级表）后传入。打包成值
    对象避免长参数列表，并把「策略在 merge、机制在 repo」的边界物化为一个类型。"""

    title: str
    title_norm: str
    first_author: str | None
    abstract: str | None
    year: int | None
    pub_date: str | None
    meta: tuple[tuple[str, str], ...]
    source: str
    priority: Mapping[str, int]


@dataclass(frozen=True)
class FetchLogRow:
    """`finalize_fetch` 的 fetch_log 载荷（id/asset_id/ts 由 repo 生成，不在此）。

    与 `add_fetch_log` 的关键字参数一一对应，仅打包成一个不可变值对象，便于把"取回
    审计行"作为一个整体传给组合事务 API。`url` 由 repo 落库前统一经 `redact` 脱敏。
    """

    task_id: str | None
    domain: str
    url: str
    http_status: int | None
    bytes_: int
    elapsed_ms: int
    rate_wait_ms: int
    error_class: str | None = None


def _meta_to_json(meta: tuple[tuple[str, str], ...]) -> str | None:
    """把弹性 meta（tuple-of-tuples）序列化为 JSON 文本；空则 None。"""
    if not meta:
        return None
    return json.dumps(dict(meta), ensure_ascii=False, sort_keys=True)


def _null_safe_eq(column: str, value: object, params: list[object]) -> str:
    """生成方言中性的 NULL-安全等值子句：None → `col IS NULL`，否则 `col = ?`。

    避免 SQLite 专有的 `col IS ?`（PostgreSQL 需 `IS NOT DISTINCT FROM`）。
    """
    if value is None:
        return f"{column} IS NULL"
    params.append(value)
    return f"{column} = ?"


def _is_empty(value: object) -> bool:
    """字段级收敛的"空值"判定：None 或空串视为空（可被任意来源填补）。int 0 不算空。"""
    return value is None or value == ""


def _rank(priority: Mapping[str, int], source: str) -> float:
    """来源优先级排名（越大越强）。未知来源 → 最高（`_UNKNOWN_RANK`，只补空不覆盖）。

    "**未记录** provenance"（现值来自 upsert_paper pull 路径，`_field_src` 无该键）不走本函数
    ——由 `_converge_fields.better` 直接短路为"绝不覆盖"，见该处注释。
    """
    known = priority.get(source)
    return _UNKNOWN_RANK if known is None else float(known)


def _prefers_on_tie(field_key: str, incoming: object, current: object) -> bool:
    """**同级**来源（=同一来源的二次观测，七枚举优先级两两互异）异值时的确定性 tie-break。

    `SOURCE_PRIORITY`（D-021 决策 3，经 D-035 扩为七位重编号；design/06 §3 来源优先级表）
    只对**跨源**冲突定序；同源二次观测
    给出不同值时表无话可说，原实现落到「先到者胜」——即注入顺序决定终值（审计 P3
    「同源二次观测异值先到胜」）。此处按字段类别取两种**全序**，故 `min` 仍是幂等+交换+结合
    的格运算，同一批观测无论以何种顺序到达都收敛到同一终值（AC-3.4）：

    - **有序标量**（`_ORDERED_SCALAR_FIELDS`：year/pub_date）→ 纯 `min`，即"取更早的那次观测
      值"：保守，不让同源复查悄悄把发表时间往后推。
    - **文本**（title/abstract/首作者姓氏/meta 各键）→ **更长者胜，等长取字典序小者**（复合序
      `(-len, str)`，仍是全序）。纯字典序对文本有系统性偏向：前缀恒胜——`"A Study"` 恒压制
      `"A Study (Retracted)"`、摘要截断版恒压制完整版，而同源二次观测最常见的形态恰是**信息
      增补**（补全摘要、补副标题、补撤稿/勘误标记）。

    **剩余代价（具名披露）**：更长者胜会让"解析漂移带来的尾部垃圾"取胜——例如页面改版后
    abstract 抓进了导航栏/版权声明/参考文献尾巴、或重复段落拼接，这类值比正确值长，会顶掉
    干净值。取舍理由：①该形态是**偶发**的解析缺陷（另有 adapter 侧"宁缺勿污"约束兜底），而
    截断/前缀压制是**系统性**的——纯字典序下完整值恒输，且无从察觉；②被压制的一方可从
    `meta_json._field_tie` 取证（本次收敛记录了哪些字段发生过同源异值），Phase 7
    `dedupe review` 可据此复核；③两种取舍都不改变顺序无关性，此处只在"注定要丢一个值"时
    选丢失代价较小的一侧，不假装能判语义优劣。
    跨源冲突仍完全由优先级表裁决，本函数不参与。
    """
    if isinstance(incoming, int) and isinstance(current, int):
        return incoming < current
    incoming_text, current_text = str(incoming), str(current)
    if field_key in _ORDERED_SCALAR_FIELDS:
        return incoming_text < current_text
    return (-len(incoming_text), incoming_text) < (-len(current_text), current_text)


def _evidence_strength(reason: object) -> float:
    """candidate_duplicate 证据强度（越大越强）；未登记标签/读不出 → 最强（`_UNKNOWN_RANK`）。

    "最强"即"绝不被覆盖"——看不懂的证据（人工写入、未来新增标签、迁移写的
    `doi-normalization-collision`）一律保守留存。
    """
    if not isinstance(reason, str):
        return _UNKNOWN_RANK
    return _EVIDENCE_STRENGTH.get(reason, _UNKNOWN_RANK)


def _evidence_dict(evidence_json: object) -> dict[str, object]:
    """把 `evidence_json` 解析为 dict；空/非法 JSON/非对象一律降级为 `{}`（绝不抛）。

    审核工具是**只读诊断面**，读到人工手改坏的 evidence 时应照常列出该条候选（证据显示
    为空）而不是整张列表崩掉；写路径（`_upsert_candidate` 等）读它只为取 reason 判强度，
    读不出即"未知 reason"→ 视为最强不可覆盖（保守侧），与降级为 `{}` 完全一致。
    """
    if not isinstance(evidence_json, str) or not evidence_json:
        return {}
    try:
        parsed = json.loads(evidence_json)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _evidence_reason(evidence_json: object) -> object:
    """从既有边的 `evidence_json` 取 reason 标签；空/非 JSON 对象 → None（强度即最强）。"""
    return _evidence_dict(evidence_json).get("reason")


def _weak_key(incoming: MergeInput) -> tuple[str, str] | None:
    """本次观测的弱信号匹配键 `(title_norm, first_author)`；任一为空 → None（不参与匹配）。

    空键不匹配是既有判据（避免"无标题/无作者"的残缺观测互相误配），随键集合语义原样保留。
    """
    if not incoming.title_norm or not incoming.first_author:
        return None
    return (incoming.title_norm, incoming.first_author)


# ---------------------------------------------------------------------------
# dedupe review 与 `same_as(decided='merged')` 聚合语义（T13 冻结件；AC-7.3；
# design/06 §3「审核工具」：merge 保留两 paper 行 + 置边，物理不删行，查询层聚合，可回滚）
#
# 这是本卡冻结的**权威说明**（消费方 T14 verify / T16 preprint 报告按此对齐）。六条：
#
# 1. **kind 隔离——口径是"逐对"，不是"逐边"**（独立审查 P1-1 修复）：审核流程只认
#    `candidate_duplicate`（"这两篇疑似同一著作"，无序对）；`preprint_of` 的
#    `decided=NULL` 语义是"边已生效、可选复核"而非"待审阻塞"（merge.py 裁决 7），
#    不出现在待审列表、不能被 `decide_candidate` 裁决、不参与聚合。
#    **但"这条边不是 candidate_duplicate"还不够**：同一对 paper 完全可能**同时**挂两种
#    边——弱信号（标题+首作者相同）建 `candidate_duplicate`，随后 arxiv `journal_ref`/`doi`
#    回填又建 `preprint_of`（审查实测的真实链路）。此时若只按边判 kind，`decide … merge`
#    会照常成功、把预印本与刊发版聚合折叠，**直接违反 D-007「双条 paper 双份全文、不合并」
#    红线**。故判据下沉到**对**：`decide_candidate` 在 merge 前查该无序对是否存在任一方向的
#    `preprint_of` 边，存在即**响亮拒绝**（`CrawlerError(CONFIG)` → CLI 退出 2）。
#    - **不设 `--force` 旁路**（controller 裁决：红线不设旁路）。数据若真有矛盾（两条边并存
#      本身就是矛盾信号），处置是修正线索/删错边的独立动作，不是在 merge 上开后门。
#    - **`reject` 仍允许**：把误报的候审关掉是合法且无害的操作（只置 `decided='rejected'`，
#      不产生任何聚合），预印本对上的误报候审正该被 reject 掉。
#    - `review` 呈现面对这类 pair 显示 `preprint_of` 警示行（`DedupeCandidate.preprint_of`），
#      让人在裁决前就看见，而不是等 merge 被拒才知道。
#    - **残留面（如实记录，本卡未改）**：**先** merge、**后**才建 `preprint_of` 边的历史顺序
#      不被本守卫覆盖——`_upsert_preprint_relation` 不查 same_as，聚合侧也不因 preprint_of
#      的存在而解除既有折叠。今日不可达则不臆造机制（弱信号候审与线索回填谁先谁后由数据
#      决定），发现即由人工 `dedupe revert` 处置；若未来要结构性堵住，属 `merge.py` 建边
#      侧的裁决面（新增 ADR），不在本卡冻结件内。
#
# 2. **裁决落库**：`merge` → ①候审行 `decided='merged'`（出待审队列、留审计痕迹）
#    ②新增/复活 `same_as(decided='merged')` 行——**聚合的唯一载体是 same_as**，候审行
#    自身的 `decided` 不驱动任何聚合（否则"改判"就无处安放）。`reject` → 候审行
#    `decided='rejected'`，并把该对可能存在的 same_as 行降级（`decided=NULL`）。
#    `same_as` 端点按 paper_id 字典序定向（`(from,to,kind)` 主键唯一 ⇒ 同一对至多一行，
#    且不随 CLI 参数顺序摆动），`confidence=1.0`（人工裁决=确定），自动信号的原始强度与
#    reason 存进 `evidence_json` 备查。
#
# 3. **聚合 = 类**：`same_as(decided='merged')` 边的**无向连通分量**（传递闭包）即一篇
#    著作的全部行。必须取闭包：A~B 与 B~C 两次独立裁决若不并成一类，聚合视图会同时显示
#    A 与 C 两行，自相矛盾。
#
# 4. **主行（canonical）**：类内 `(-identifier 数, paper_id)` 最小者——identifier 最多者胜、
#    平局取 paper_id 字典序最小者，与 merge.py 裁决 3 的跨 paper 冲突胜者规则同构。它是
#    **当前库态的函数**：不看边方向（same_as 语义对称）、不看裁决顺序（AC-3.4 精神）。
#    **代价如实记**：paper 后续补进 identifier 可能让主行易主，故"主行"是显示层的当前
#    最佳代表、**不是稳定标识符**；需要稳定引用的消费方请引用整个类（`members`）。
#
# 5. **归并视图**：identifier 取类内并集（`(scheme,value)` 全局唯一，天然去重）、asset 取
#    类内全集（**不去重**：两行各自的 PDF 是两次独立取回、磁盘上是两个文件，verify 仍需
#    逐个对账）。**字段（title/abstract/year…）不跨行收敛、不回写 paper 行**——聚合纯粹
#    发生在查询层，写库的字段收敛另有 provenance 体系（design/06 §3），二者不得互相污染；
#    这也正是"可回滚"成立的根据。
#
# 6. **折叠是"结果集内"的，不是全局过滤**（`fold_merged`）：同类多行在**同一次查询结果**
#    里只保留一行代表（类主行若在结果集内则取之，否则取集内成员按同一序的最小者），
#    其余行删除、**不重排**幸存行。绝不写成"非主行一律过滤"——主行可能不在本次范围内
#    （如它属于另一个 venue/issue），那样会让一篇著作从某个清单里**整体消失**。
#    `list_papers(aggregate=…)` 默认 **False**：pull 级联（`runner._select_papers`）必须
#    看到全部行，否则被折叠的一侧永远拿不到 resolve/fetch——聚合是显示语义，不是数据过滤。
#
# **回滚**（AC-7.3）：`revert_candidate` 把候审行 `decided` 置回 NULL、same_as 行降级为
# NULL（`evidence_json` 记 `reverted_at` 留痕）。因为整条链从未改动 paper/identifier/asset
# 任何一行，回滚是**完全**的：聚合视图消失、候选回到待审队列、实体三表逐行不变
# （`tests/unit/test_dedupe.py` 以三表快照前后相等锁定）。关系行**绝不物理删除**——沿
# `_upsert_candidate`/`_upsert_preprint_relation` 的同一条底线。
# **注意**：回滚解除的是**这一条** same_as 边；若两 paper 还经其他已裁决边同属一个连通类
# （A~B、B~C 都 merge 过，回滚 A~B 后 A 与 C 仍同类），折叠不会解除——`revert_candidate`
# 的调用方应在出口处提示（`dedupe_cli` 已做），否则人会误以为"回滚了却没生效"。
#
# **`decided=NULL` 的语义重载（controller 裁决，独立审查 P2-1）**：same_as 行被回滚后
# `decided` 置回 NULL，与 schema 注释里的"null=待审"共用同一个值——今日无歧义，因为**没有
# 任何路径自动建 same_as 边**（自动建边只产 `candidate_duplicate` 与 `preprint_of`），
# same_as 行恒由本流程写出。**未来引入任何自动建 same_as 边的机制之前，必须先裁此语义**：
# 用 `evidence_json.reverted_at` 判别"回滚留痕 vs 真待审"，还是扩 `decided` 值域（如
# `reverted`）——后者动数据模型的取值域，**走 ADR**。在此之前不得默认 NULL 只有一种含义。
#
# **消费方性能提示（独立审查 P2-4）**：要遍历全部合并类请用 `merged_views()` / `merged_groups()`
# **一次取全**；`merged_view(paper_id)` / `merged_group(paper_id)` 每次都会重算整张索引
# （全表扫 same_as 边 + 重建连通分量），逐 paper 调用是 O(paper 数 × 全表)。单点查询用它，
# 批量报告（T16）用 `merged_views()`。
# ---------------------------------------------------------------------------

# `list_candidates(state=…)` 的取值域；"pending" = 待审（decided IS NULL）。
CANDIDATE_STATES: tuple[str, ...] = ("pending", "merged", "rejected", "all")
# `decide_candidate(decision=…)` 的取值域 → 落库的 `decided` 值。
DEDUPE_DECISIONS: dict[str, str] = {"merge": "merged", "reject": "rejected"}
_SAME_AS_MERGE_REASON = "dedupe-review-merge"
# 无序对查一条关系边（两个方向都查——`(from,to,kind)` 主键不认方向，而
# `candidate_duplicate` 的落行方向是建边时刻的快照，见 `_upsert_candidate`）。
# 读写两条路径共用同一条谓词，避免"只在一处加双向查"的漂移。
_RELATION_PAIR_SQL = (
    "SELECT from_paper, to_paper, confidence, evidence_json, decided FROM paper_relation "
    "WHERE kind = ? AND ((from_paper = ? AND to_paper = ?) OR (from_paper = ? AND to_paper = ?))"
)
# 人工裁决的 same_as 边置信度恒 1.0（自动信号的原始 confidence 另存 evidence_json）。
_SAME_AS_CONFIDENCE = 1.0
# 批量 IN 查询的参数分块上限（SQLite 默认 999 变量上限的保守分片）。
_SQL_PARAM_CHUNK = 400


@dataclass(frozen=True)
class PaperBrief:
    """dedupe 呈现用的一侧 paper 只读投影（`identifiers` 为 `"scheme:value"` 升序）。"""

    paper_id: str
    title: str
    venue_id: str | None
    year: int | None
    identifiers: tuple[str, ...]
    asset_count: int


@dataclass(frozen=True)
class DedupeCandidate:
    """一条 `candidate_duplicate`（无序对归一：`paper_a.paper_id < paper_b.paper_id`）。

    `preprint_of`：该**对**若另挂 `preprint_of` 边则为其 `(from, to)`（预印本→发表版），
    否则 None——呈现面据此给出"不可 merge（D-007）"警示（聚合语义 1 的逐对口径）。
    """

    paper_a: PaperBrief
    paper_b: PaperBrief
    confidence: float | None
    reason: str | None
    evidence: Mapping[str, object]
    decided: str | None
    preprint_of: tuple[str, str] | None = None


@dataclass(frozen=True)
class DecisionOutcome:
    """`decide_candidate`/`revert_candidate` 的结果；`changed=False` 即幂等重放。"""

    paper_a: str
    paper_b: str
    decided: str | None
    changed: bool


@dataclass(frozen=True)
class MergedGroup:
    """一个合并类：`members` 按 paper_id 升序（含 `canonical`），见上文聚合语义 3/4。"""

    canonical: str
    members: tuple[str, ...]


@dataclass(frozen=True)
class MergedView:
    """合并类的归并视图（上文聚合语义 5）：主行 + 全成员 + identifier 并集 + asset 全集。"""

    canonical: PaperBrief
    members: tuple[PaperBrief, ...]
    identifiers: tuple[str, ...]
    asset_count: int


class Repo:
    """领域仓储；所有写操作经 `Database` 的 autocommit / 事务上下文落库。"""

    def __init__(self, db: Database) -> None:
        self.db = db

    # -- venue ---------------------------------------------------------------

    def upsert_venue(self, spec: VenueSpec) -> None:
        """按 id 幂等写入 venue，附 VenueSpec 快照（审计）。就地 UPDATE，保留子行外键。"""
        self.db.execute(
            "INSERT INTO venue (id, kind, name, field_json, tier, spec_snapshot_json, status) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "  kind=excluded.kind, name=excluded.name, field_json=excluded.field_json, "
            "  tier=excluded.tier, spec_snapshot_json=excluded.spec_snapshot_json, "
            "  status=excluded.status",
            (
                spec.id,
                spec.kind,
                spec.names.full,
                json.dumps(spec.field, ensure_ascii=False),
                spec.tier,
                spec.model_dump_json(),
                spec.status,
            ),
        )

    # -- issue ---------------------------------------------------------------

    def upsert_issue(self, ref: IssueRef, source: str) -> str:
        """幂等写入 issue，返回 issue_id。业务键 (venue_id,volume,number,label) 查后插。"""
        with self.db.tx() as conn:
            params: list[object] = [ref.venue_id]
            where = " AND ".join(
                [
                    "venue_id = ?",
                    _null_safe_eq("volume", ref.volume, params),
                    _null_safe_eq("number", ref.number, params),
                    _null_safe_eq("label", ref.label, params),
                ]
            )
            existing = conn.execute(f"SELECT id FROM issue WHERE {where}", params).fetchone()
            if existing is not None:
                return str(existing["id"])
            issue_id = new_ulid()
            conn.execute(
                "INSERT INTO issue "
                "(id, venue_id, era_id, volume, number, year, label, pub_date, source, "
                " paper_count_claimed) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    issue_id,
                    ref.venue_id,
                    None,
                    ref.volume,
                    ref.number,
                    ref.year,
                    ref.label,
                    ref.pub_date,
                    source,
                    ref.paper_count_claimed,
                ),
            )
            return issue_id

    def list_issues(
        self,
        venue_id: str,
        *,
        volume: str | None = None,
        number: str | None = None,
        year: int | None = None,
    ) -> list[sqlite3.Row]:
        """列出某 venue 的 issue，可按 volume/number/year 过滤；按卷/期稳定排序。"""
        clauses = ["venue_id = ?"]
        params: list[object] = [venue_id]
        if volume is not None:
            clauses.append("volume = ?")
            params.append(volume)
        if number is not None:
            clauses.append("number = ?")
            params.append(number)
        if year is not None:
            clauses.append("year = ?")
            params.append(year)
        sql = (
            "SELECT * FROM issue WHERE "
            + " AND ".join(clauses)
            + " ORDER BY year, volume, number, label"
        )
        return self.db.query(sql, params)

    # -- paper ---------------------------------------------------------------

    def upsert_paper(self, venue_id: str, issue_id: str | None, stub: PaperStub) -> str:
        """强合并 upsert：identifier 命中 → 复用 paper 并补缺字段；否则新建。幂等建 issue 链。

        design/06 §3 强合并锚点：任一 (scheme,value) 命中既有 identifier → 返回该 paper_id，
        新字段仅填补空缺、不覆盖非空。

        **identifier 归一（D-裁决 2026-07-22）**：写入前经 `ids.normalize_identifier`
        （scheme=doi 的值小写化/剥前缀，其余原样）——与 `MergeEngine` 共用同一归一入口，
        使 pull 路径与 aggregator 路径的 DOI 键收敛到同一规范形（AC-3.1 混合双路无条件命中）。

        **title_norm 维护**：新建 paper 时一并写 `title_norm`（schema v2 列，`normalize_title`），
        与 0002 迁移的存量回填口径一致。title 是强合并锚点、恒不更新，故 title_norm 仅在建行时
        写、合并分支不动。
        **本列已不是弱信号匹配面**（Phase 6 F1）：候审匹配改由 `paper_weak_key`（观测级键集合，
        schema v3）承载，pull 路径不写该表——故 upsert_paper 建的 paper 仍**不进**弱信号匹配面，
        直到某次 `MergeEngine.ingest` 并入它时记下那次观测的键（与改造前"无 `_first_author` 即
        无从确认姓氏、保守不建 candidate"的实际行为一致）。`title_norm` 列现留两个用途：
        0003 迁移回填存量历史键的取数源，以及归一标题的展示/检索面（`idx_paper_title_norm`）。

        **preprint_of 建边（T10）**：拿到 `paper_id` 后同事务内消费 `stub.meta` 里的
        preprint 线索（`_apply_preprint_clues`）——真实携带 arxiv/cvf/openreview 等 adapter
        线索的 `PaperStub` 恰是经本方法（`_stage_enumerate` pull 路径）落库，故本调用点是
        该线索族的实际生效面；`merge_ingest` 分支树也调用同一方法（aggregator/enrich 路径
        对等覆盖），权威说明见 merge.py 裁决点 7。
        """
        identifiers = tuple(
            normalize_identifier(scheme, value) for scheme, value in stub.identifiers
        )
        with self.db.tx() as conn:
            paper_id: str | None = None
            for scheme, value in identifiers:
                hit = conn.execute(
                    "SELECT paper_id FROM identifier WHERE scheme = ? AND value = ?",
                    (scheme, value),
                ).fetchone()
                if hit is not None:
                    paper_id = str(hit["paper_id"])
                    break

            now = utcnow_iso()
            if paper_id is None:
                paper_id = new_ulid()
                conn.execute(
                    "INSERT INTO paper "
                    "(id, title, abstract, year, pub_date, venue_id, meta_json, title_norm, "
                    " ingest_state, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        paper_id,
                        stub.title,
                        stub.abstract,
                        stub.year,
                        stub.pub_date,
                        venue_id,
                        _meta_to_json(stub.meta),
                        normalize_title(stub.title),
                        "metadata_only",
                        now,
                        now,
                    ),
                )
            else:
                self._merge_paper_fields(conn, paper_id, stub, now)

            self._ensure_identifiers(conn, paper_id, identifiers)
            self._apply_preprint_clues(conn, paper_id, stub.meta, venue_id=venue_id)

            if issue_id is not None:
                conn.execute(
                    "INSERT INTO paper_issue_link (paper_id, issue_id) VALUES (?,?) "
                    "ON CONFLICT (paper_id, issue_id) DO NOTHING",
                    (paper_id, issue_id),
                )
            return paper_id

    @staticmethod
    def _merge_paper_fields(
        conn: sqlite3.Connection,
        paper_id: str,
        stub: PaperStub,
        now: str,
    ) -> None:
        """补缺不覆盖：仅当既有列为空/NULL 时用 stub 的非空值填充。

        合并的是跨源可残缺的字段（abstract/year/pub_date/meta）。title 是必填的强合并锚点
        （PaperStub 恒有值），venue_id 建 paper 时即由外键约束绑定，二者不参与补缺。
        """
        existing = conn.execute("SELECT * FROM paper WHERE id = ?", (paper_id,)).fetchone()
        updates: dict[str, object] = {}
        if not existing["abstract"] and stub.abstract:
            updates["abstract"] = stub.abstract
        if existing["year"] is None and stub.year is not None:
            updates["year"] = stub.year
        if not existing["pub_date"] and stub.pub_date:
            updates["pub_date"] = stub.pub_date
        if not existing["meta_json"] and stub.meta:
            updates["meta_json"] = _meta_to_json(stub.meta)
        if not updates:
            return
        updates["updated_at"] = now
        set_clause = ", ".join(f"{col} = ?" for col in updates)
        conn.execute(
            f"UPDATE paper SET {set_clause} WHERE id = ?",
            (*updates.values(), paper_id),
        )

    @staticmethod
    def _ensure_identifiers(
        conn: sqlite3.Connection, paper_id: str, identifiers: tuple[tuple[str, str], ...]
    ) -> None:
        """确保每个（已归一的）identifier 存在并指向 paper_id；已存在的保持不动（全局唯一锚点）。

        `is_primary` 单一性：一个 paper 至多一个 primary。仅当该 paper 尚无 primary 时，
        才把首个（index==0）**新增** identifier 标为 primary；合并进已有 primary 的
        paper 时新来者一律非 primary（否则合并路径会产生双 is_primary）。入参 `identifiers`
        已由调用方经 `ids.normalize_identifier` 归一。
        """
        has_primary = (
            conn.execute(
                "SELECT 1 FROM identifier WHERE paper_id = ? AND is_primary = 1 LIMIT 1",
                (paper_id,),
            ).fetchone()
            is not None
        )
        for index, (scheme, value) in enumerate(identifiers):
            present = conn.execute(
                "SELECT paper_id FROM identifier WHERE scheme = ? AND value = ?",
                (scheme, value),
            ).fetchone()
            if present is None:
                is_primary = 1 if (index == 0 and not has_primary) else 0
                conn.execute(
                    "INSERT INTO identifier (paper_id, scheme, value, is_primary) VALUES (?,?,?,?)",
                    (paper_id, scheme, value, is_primary),
                )
                if is_primary:
                    has_primary = True

    # -- merge engine 组合事务（Phase 3 T1；接口冻结件 §2-1） -----------------

    def merge_ingest(
        self, incoming: MergeInput, identifiers: tuple[tuple[str, str], ...]
    ) -> IngestOutcome:
        """`MergeEngine.ingest` 的原子机制载体（查→并→补 单事务；SQL/事务在 repo，策略注入）。

        沿 `finalize_fetch` 先例：整条「identifier 查重 → 分支（新建 / 强合并 / 跨 paper
        冲突 / 弱信号候审）→ 字段级来源优先级收敛 → 补 identifier / 建 candidate_duplicate /
        建 preprint_of（T10，`_apply_preprint_clues`）」在单个 `BEGIN IMMEDIATE` 事务内完成
        ——立即取写锁，读+写同一快照，杜绝并发裂脑（plan §2-1「防并发裂脑」）。`identifiers`
        已由 MergeEngine 经 `ids.normalize_identifier` 归一（含 doi）。裁决语义的**权威说明在
        merge.py docstring**（跨冲突取 identifier 多者/平局小 id、弱信号绝不自动合并、未知
        provenance 视最高、candidate 端点按最小 identifier 定向、preprint_of 线索表与方向
        约定见裁决点 7）；本方法只承载其 SQL 机制。返回 `IngestOutcome`，由 MergeEngine 包装为
        `IngestResult`。
        """
        with self.db.tx() as conn:
            matched: list[str] = []
            hit_papers: dict[str, None] = {}
            for scheme, value in identifiers:
                row = conn.execute(
                    "SELECT paper_id FROM identifier WHERE scheme = ? AND value = ?",
                    (scheme, value),
                ).fetchone()
                if row is not None:
                    hit_papers.setdefault(str(row["paper_id"]), None)
                    matched.append(f"{scheme}:{value}")

            distinct = list(hit_papers)
            if not distinct:
                return self._merge_ingest_no_hit(conn, incoming, identifiers)
            if len(distinct) == 1:
                paper_id = distinct[0]
                self._converge_fields(conn, paper_id, incoming)
                self._ensure_identifiers(conn, paper_id, identifiers)
                # 强合并分支也记本次观测的弱信号键并重判候审：键集合单调只增，故"高优先源
                # 改写标题"不再抹掉此前/此后的匹配面（审计 P1）。action 仍报 `merged`
                # ——`IngestResult` 三枚举是冻结件，候审边只作为 DB 副作用记录，不改口径。
                self._apply_weak_signal(conn, paper_id, incoming)
                # preprint_of 建边（T10）同为 DB 副作用，不改变 action 口径。
                self._apply_preprint_clues(conn, paper_id, incoming.meta, source=incoming.source)
                return IngestOutcome(paper_id, "merged", tuple(matched))
            return self._merge_ingest_conflict(
                conn, distinct, incoming, identifiers, tuple(matched)
            )

    def _merge_ingest_no_hit(
        self,
        conn: sqlite3.Connection,
        incoming: MergeInput,
        identifiers: tuple[tuple[str, str], ...],
    ) -> IngestOutcome:
        """无 identifier 命中：弱信号候审（title_norm 精确匹配 + 首作者姓氏一致）或纯新建。

        弱信号**绝不自动合并**（06 §3：WP↔刊发版标题常变，宁可两条待审）——新建 paper 后
        对**每个**曾观测到同一键的既有 paper 建 candidate_duplicate（`_apply_weak_signal`）。
        「对每个匹配都建边」而非「只对其一」是顺序无关的关键：任意注入顺序下，同键簇内的
        每对 paper 最终都被建边（后取得该键者对先持有者建边），终态 = 该簇全体两两 candidate。
        """
        new_id = self._create_paper(conn, incoming, identifiers)
        matches = self._apply_weak_signal(conn, new_id, incoming)
        # T10：DB 副作用，不改 action。
        self._apply_preprint_clues(conn, new_id, incoming.meta, source=incoming.source)
        if not matches:
            return IngestOutcome(new_id, "created", ())
        return IngestOutcome(new_id, "candidate_flagged", ())

    def _merge_ingest_conflict(
        self,
        conn: sqlite3.Connection,
        distinct: list[str],
        incoming: MergeInput,
        identifiers: tuple[tuple[str, str], ...],
        matched: tuple[str, ...],
    ) -> IngestOutcome:
        """跨 paper identifier 冲突（stub 的 identifier 命中≥2 个不同既有 paper）。

        裁决（plan §2-1 / merge.py docstring）：**不自动合并两 paper**；stub 并入 identifier
        数最多者（平局取 paper_id 字典序最小者——确定性），其余每个命中 paper 与胜者建
        candidate_duplicate(evidence=identifier-conflict) 留人审。stub 的 identifier 里指向
        败者的那些**原地不动**（`_ensure_identifiers` 只补库中尚不存在的孤儿 identifier，
        不重指既存者）——绝不物理迁移 identifier 行。
        """
        winner = min(distinct, key=lambda pid: (-self._identifier_count(conn, pid), pid))
        self._converge_fields(conn, winner, incoming)
        self._ensure_identifiers(conn, winner, identifiers)
        for other in distinct:
            if other != winner:
                self._upsert_candidate(
                    conn,
                    winner,
                    other,
                    _IDENTIFIER_CONFLICT_CONFIDENCE,
                    {"reason": _IDENTIFIER_CONFLICT_REASON, "identifiers": sorted(matched)},
                )
        # 冲突边先落（证据更强，见 `_upsert_candidate` 的强度序），再记本次观测的弱信号键。
        self._apply_weak_signal(conn, winner, incoming)
        # T10：DB 副作用，不改 action。
        self._apply_preprint_clues(conn, winner, incoming.meta, source=incoming.source)
        return IngestOutcome(winner, "candidate_flagged", matched)

    def _create_paper(
        self,
        conn: sqlite3.Connection,
        incoming: MergeInput,
        identifiers: tuple[tuple[str, str], ...],
    ) -> str:
        """新建 paper（venue-agnostic：venue_id=NULL，MergeEngine 冻结签名不带 venue）。

        建库时所有非空入参字段记 provenance=incoming.source（`_field_src`）；首作者姓氏存
        `meta_json._first_author`（弱信号比对锚，types.py PaperStub.authors 冻结为名字串组，
        不改 types——由现有字段推导）。`title_norm` 落 schema v2 列。
        """
        paper_id = new_ulid()
        now = utcnow_iso()
        meta_obj: dict[str, object] = dict(incoming.meta)
        field_src: dict[str, str] = {"title": incoming.source}
        if incoming.abstract:
            field_src["abstract"] = incoming.source
        if incoming.year is not None:
            field_src["year"] = incoming.source
        if incoming.pub_date:
            field_src["pub_date"] = incoming.source
        if incoming.first_author is not None:
            meta_obj["_first_author"] = incoming.first_author
            field_src["authors"] = incoming.source
        for key, _value in incoming.meta:
            field_src[f"meta:{key}"] = incoming.source
        meta_obj["_field_src"] = field_src
        conn.execute(
            "INSERT INTO paper "
            "(id, title, abstract, year, pub_date, venue_id, meta_json, title_norm, "
            " ingest_state, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                paper_id,
                incoming.title,
                incoming.abstract,
                incoming.year,
                incoming.pub_date,
                None,
                json.dumps(meta_obj, ensure_ascii=False, sort_keys=True),
                incoming.title_norm,
                "metadata_only",
                now,
                now,
            ),
        )
        self._ensure_identifiers(conn, paper_id, identifiers)
        return paper_id

    def _converge_fields(
        self, conn: sqlite3.Connection, paper_id: str, incoming: MergeInput
    ) -> None:
        """字段级来源优先级收敛（AC-3.4 基石）：新值仅当①现值空、②新源优先级严格高、或
        ③同级但值序更小（`_prefers_on_tie`）时写入。

        provenance 记于 `meta_json._field_src`（field_key→source）；未记录来源的存量字段
        （upsert_paper pull 路径所写）视为最高优先——只补空、绝不覆盖。收敛字段：title
        （连带 title_norm 列）/abstract/year/pub_date/首作者姓氏（`authors`→`_first_author`）/
        每个 meta 键（`meta:<k>`）。跨级由优先级表定序、同级由确定性 tie-break 定序，两者都
        与到达顺序无关，故任意注入顺序收敛到同一终态。

        **取证抓手** `meta_json._field_tie`（字段键集合）：标记"**当前生效来源**对该字段给出过
        互不相同的多个值、当前值是 `_prefers_on_tie` 择一的结果"，为 Phase 7 `dedupe review`
        留复核面（`_prefers_on_tie` docstring 具名披露的剩余代价即从这里取证）。维护规则两条：
        同级异值比较时**加**记号；该字段被**严格更高优先源**改写时**清**记号（旧记号属于已被
        取代的来源）。二者使记号恒等于"终局赢家来源自身给出过几个不同值"——只与输入集合有关：
        赢家来源的首个观测落库后，更低源再也改不动该字段，其后赢家的每个观测都必然走到同级
        比较，故赢家的自相矛盾在任意到达序下都会被记到；败者来源的自相矛盾则一律不记
        （它们的值本就被优先级表淘汰，不是 tie-break 丢的）。若只做"集合并、不清记号"，
        `[openalex_a, openalex_b, dblp]` 会留记号而 `[dblp, openalex_a, openalex_b]` 不会
        ——顺序敏感（补强后的 property 生成器实测捕获）。
        """
        row = conn.execute(
            "SELECT title, abstract, year, pub_date, meta_json FROM paper WHERE id = ?",
            (paper_id,),
        ).fetchone()
        meta_obj: dict[str, object] = json.loads(row["meta_json"]) if row["meta_json"] else {}
        raw_src = meta_obj.get("_field_src")
        field_src: dict[str, str] = dict(raw_src) if isinstance(raw_src, dict) else {}
        col_updates: dict[str, object] = {}
        tie_fields: set[str] = set()  # 本次同源异值 → 加取证记号
        upgraded_fields: set[str] = set()  # 本次被更高优先源改写 → 清旧取证记号

        def better(field_key: str, incoming_value: object, current_value: object) -> bool:
            if _is_empty(incoming_value):
                return False
            if _is_empty(current_value):
                return True
            current_source = field_src.get(field_key)
            if current_source is None:  # 无 provenance 的存量值（pull 路径）：只补空、绝不覆盖
                return False
            incoming_rank = _rank(incoming.priority, incoming.source)
            current_rank = _rank(incoming.priority, current_source)
            if incoming_rank > current_rank:
                upgraded_fields.add(field_key)
                return True
            if incoming_rank < current_rank:
                return False
            if incoming_value == current_value:  # 同源同值 = 幂等重复，非冲突
                return False
            tie_fields.add(field_key)  # 同源异值：无论谁胜都留取证痕迹
            return _prefers_on_tie(field_key, incoming_value, current_value)

        if better("title", incoming.title, row["title"]):
            col_updates["title"] = incoming.title
            col_updates["title_norm"] = incoming.title_norm
            field_src["title"] = incoming.source
        if better("abstract", incoming.abstract, row["abstract"]):
            col_updates["abstract"] = incoming.abstract
            field_src["abstract"] = incoming.source
        if better("year", incoming.year, row["year"]):
            col_updates["year"] = incoming.year
            field_src["year"] = incoming.source
        if better("pub_date", incoming.pub_date, row["pub_date"]):
            col_updates["pub_date"] = incoming.pub_date
            field_src["pub_date"] = incoming.source
        if incoming.first_author is not None and better(
            "authors", incoming.first_author, meta_obj.get("_first_author")
        ):
            meta_obj["_first_author"] = incoming.first_author
            field_src["authors"] = incoming.source
        for key, value in incoming.meta:
            if better(f"meta:{key}", value, meta_obj.get(key)):
                meta_obj[key] = value
                field_src[f"meta:{key}"] = incoming.source

        if field_src:
            meta_obj["_field_src"] = field_src
        if tie_fields or upgraded_fields:  # 加新记号、清被更高源取代的旧记号（见 docstring）
            previous_tie = meta_obj.get("_field_tie")
            known = {str(key) for key in previous_tie} if isinstance(previous_tie, list) else set()
            live_ties = (known - upgraded_fields) | tie_fields
            if live_ties:
                meta_obj["_field_tie"] = sorted(live_ties)  # 排序落盘使 JSON 稳定可比
            else:
                meta_obj.pop("_field_tie", None)
        new_meta_json = (
            json.dumps(meta_obj, ensure_ascii=False, sort_keys=True) if meta_obj else None
        )
        if col_updates or new_meta_json != row["meta_json"]:
            col_updates["meta_json"] = new_meta_json
            col_updates["updated_at"] = utcnow_iso()
            set_clause = ", ".join(f"{col} = ?" for col in col_updates)
            conn.execute(
                f"UPDATE paper SET {set_clause} WHERE id = ?",
                (*col_updates.values(), paper_id),
            )

    @staticmethod
    def _identifier_count(conn: sqlite3.Connection, paper_id: str) -> int:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM identifier WHERE paper_id = ?", (paper_id,)
        ).fetchone()
        return int(row["n"])

    # -- 弱信号键集合（AC-3.4 顺序无关的匹配面，schema v3 `paper_weak_key`） -------

    def _apply_weak_signal(
        self, conn: sqlite3.Connection, paper_id: str, incoming: MergeInput
    ) -> list[str]:
        """记下本次观测的弱信号键，并对**新键**重判候审；返回本次新配上的既有 paper（升序）。

        匹配键是**观测级**的：一个 paper 的键集合 = 它全部观测的 `(title_norm, first_author)`，
        单调只增、不被字段收敛改写。故终态候审边 = 「键集合有交的每一对 paper」——输入集合的
        函数，与到达顺序无关（AC-3.4）。原实现拿 paper 行的**当前** title_norm/`_first_author`
        当键，后到的高优先源改写标题即抹掉匹配面，同一批观测按不同序注入得到不同候审边数
        （审计 P1 实测 1 条 vs 0 条）——本方法是该缺陷的修复点。

        键对本 paper 已存在 → 直接返回：该键当时已与彼时所有持键 paper 建过边，此后取得该键
        的 paper 会在**自己那一侧**建边（增量算法的完备性论证），故无需重判，幂等亦由此保证。
        """
        key = _weak_key(incoming)
        if key is None:
            return []
        title_norm, first_author = key
        if not self._record_weak_key(conn, paper_id, title_norm, first_author):
            return []
        rows = conn.execute(
            "SELECT paper_id FROM paper_weak_key "
            "WHERE title_norm = ? AND first_author = ? AND paper_id <> ? ORDER BY paper_id",
            (title_norm, first_author, paper_id),
        ).fetchall()
        others = [str(row["paper_id"]) for row in rows]
        for other in others:
            self._upsert_candidate(
                conn,
                paper_id,
                other,
                _WEAK_SIGNAL_CONFIDENCE,
                {
                    "reason": _WEAK_SIGNAL_REASON,
                    "keys": self._shared_weak_keys(conn, paper_id, other),
                },
            )
        return others

    @staticmethod
    def _record_weak_key(
        conn: sqlite3.Connection, paper_id: str, title_norm: str, first_author: str
    ) -> bool:
        """把键并入该 paper 的键集合；返回是否为**新键**（已存在则不重判候审）。"""
        existing = conn.execute(
            "SELECT 1 FROM paper_weak_key "
            "WHERE paper_id = ? AND title_norm = ? AND first_author = ? LIMIT 1",
            (paper_id, title_norm, first_author),
        ).fetchone()
        if existing is not None:
            return False
        conn.execute(
            "INSERT INTO paper_weak_key (paper_id, title_norm, first_author) VALUES (?,?,?)",
            (paper_id, title_norm, first_author),
        )
        return True

    @staticmethod
    def _shared_weak_keys(conn: sqlite3.Connection, paper_a: str, paper_b: str) -> list[list[str]]:
        """两 paper 键集合的交（升序）——候审边的证据体。

        取**当前全交**而非"本次撞上的那一个键"：交集单调只增，且最后一次触碰该 pair 必然
        发生在最后一个共享键出现之时，故写入的证据恒为终态全交，与到达顺序无关。
        """
        rows = conn.execute(
            "SELECT ka.title_norm AS title_norm, ka.first_author AS first_author "
            "FROM paper_weak_key ka JOIN paper_weak_key kb "
            "  ON kb.title_norm = ka.title_norm AND kb.first_author = ka.first_author "
            "WHERE ka.paper_id = ? AND kb.paper_id = ? "
            "ORDER BY ka.title_norm, ka.first_author",
            (paper_a, paper_b),
        ).fetchall()
        return [[str(row["title_norm"]), str(row["first_author"])] for row in rows]

    @staticmethod
    def _paper_min_identifier(conn: sqlite3.Connection, paper_id: str) -> tuple[str, str]:
        """paper 名下按 (scheme,value) 字典序最小的 identifier；无则 ('','')。candidate 定向锚。"""
        row = conn.execute(
            "SELECT scheme, value FROM identifier WHERE paper_id = ? "
            "ORDER BY scheme, value LIMIT 1",
            (paper_id,),
        ).fetchone()
        return (str(row["scheme"]), str(row["value"])) if row is not None else ("", "")

    def _upsert_candidate(
        self,
        conn: sqlite3.Connection,
        paper_a: str,
        paper_b: str,
        confidence: float,
        evidence: dict[str, object],
    ) -> None:
        """建/刷新 candidate_duplicate(decided=NULL)：**一对 paper 至多一行**（任一方向）。

        - 新边：端点按各自最小 identifier 定向（`_paper_min_identifier`）。该锚是**建边时刻的
          快照、不是不变量**——此后 paper 补进更小的 identifier 也不重定向，故不同注入序可能
          落出方向相反的同一条边。`candidate_duplicate` 语义上是无序对，消费方按无序对处理
          （merge.py 裁决 5）。
        - 已有边：查两个方向后再决定——`(from,to,kind)` 主键不认方向，若只看单向，上述定向
          翻转会给同一对 paper 落出第二行。
        - 刷新规则：已人工裁决（`decided` 非空）的边**绝不动**；未裁决的边仅当新证据强度
          **不弱于**既有（`_EVIDENCE_STRENGTH`，未知 reason 视为最强不可覆盖）才写——弱信号
          刷新共享键全交、identifier 冲突可升级既有弱信号边，反向绝不降级。绝不删行。
        """
        evidence_json = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
        row = conn.execute(
            "SELECT from_paper, to_paper, evidence_json, decided FROM paper_relation "
            "WHERE kind = ? AND ((from_paper = ? AND to_paper = ?) "
            "                 OR (from_paper = ? AND to_paper = ?))",
            ("candidate_duplicate", paper_a, paper_b, paper_b, paper_a),
        ).fetchone()
        if row is None:
            if self._paper_min_identifier(conn, paper_a) <= self._paper_min_identifier(
                conn, paper_b
            ):
                from_paper, to_paper = paper_a, paper_b
            else:
                from_paper, to_paper = paper_b, paper_a
            conn.execute(
                "INSERT INTO paper_relation "
                "(from_paper, to_paper, kind, confidence, evidence_json, decided) "
                "VALUES (?,?,?,?,?,?) "
                "ON CONFLICT (from_paper, to_paper, kind) DO NOTHING",
                (from_paper, to_paper, "candidate_duplicate", confidence, evidence_json, None),
            )
            return
        if row["decided"] is not None or row["evidence_json"] == evidence_json:
            return
        if _evidence_strength(evidence.get("reason")) < _evidence_strength(
            _evidence_reason(row["evidence_json"])
        ):
            return
        conn.execute(
            "UPDATE paper_relation SET confidence = ?, evidence_json = ? "
            "WHERE from_paper = ? AND to_paper = ? AND kind = ?",
            (confidence, evidence_json, row["from_paper"], row["to_paper"], "candidate_duplicate"),
        )

    # -- preprint_of 建边（T10；检查单 #5，design/06 §3 单一事实源） --------

    def _apply_preprint_clues(
        self,
        conn: sqlite3.Connection,
        paper_id: str,
        meta: tuple[tuple[str, str], ...],
        *,
        source: str | None = None,
        venue_id: str | None = None,
    ) -> None:
        """消费本次观测 meta 里的 preprint 线索，建/刷新 preprint_of 边。

        逐键查 `_PREPRINT_CLUE_ROLES`（**迭代序即该 dict 字面量的声明序：doi 先于
        arxiv**——同调用内两线索撞同一 target 时"doi 先落地"单纯是这个声明序的自然结果，
        见下方"双向矛盾环守卫"段；打乱声明序会悄悄改变同调用内的胜出方，故不可无意间
        重排）：命中键→按其目标 scheme 归一（doi 走 `normalize_identifier`，与
        identifier 写入同一入口；arxiv 走 `_normalize_arxiv_clue`——独立审查 P1-3：
        通用 `normalize_identifier` 对非 doi scheme 直通，与 `identifier(scheme='arxiv')`
        写入侧"去版本号的规范 base id"链不同，带版本/URL 形/旧代线索值会静默悬空）→ 查
        `identifier` 表解析目标端。**建边时机**＝本次 ingest 消费到线索的当下、一次性
        尝试（controller 已裁决③）：查不到目标端（线索悬空）或线索值本身无法解析
        （P1-3：`_normalize_arxiv_clue` 返回 None）→ DEBUG 记录后跳过、不建边、
        **不回溯重判**——不同于弱信号候审的观测级键集合机制，本卡接受顺序敏感的
        best-effort 语义：目标端若晚于线索到达入库，这条线索就此错过，除非同一 paper 的
        后续观测重复携带该线索（下次 ingest 会重新尝试查找）。

        方向固定不看快照（controller 裁决①，与 `candidate_duplicate` 的定向快照/无序对语义
        不同——preprint_of 方向本身是语义不变量）：`role="from"` 即自身是预印本、目标是
        发表版；`role="to"` 反之。'journal_ref'（arxiv 专属自由文本）不可独立驱动查找，只在
        'doi' 线索命中时作为补充证据搭车进 evidence_json。

        **双向矛盾环守卫（独立审查 re-review #6，P1；取代旧 P1-1 的同调用内预判）**：
        本方法**不**自行判断"doi/arxiv 是否撞同一 target"——那只堵得住同一调用内的一半
        场景，堵不住跨观测的另一半（target 的 identifier 集合在两次 SELF 观测之间可能
        变化，见 `_upsert_preprint_relation` docstring 的四步时序）。真正的防线下沉到
        `_upsert_preprint_relation`：写入前查一次反向行是否已存在。本方法只管按线索表
        逐一尝试写入，冲突判定与拦截全权交给那一处更底层、覆盖面更广的守卫。

        `evidence_json` 溯源字段（独立审查 P1-2）：`merge_ingest`（`incoming.source`）与
        `upsert_paper`（`venue_id` 参数）分别传入各自持有的 provenance，供人工核实线索本
        身的语义是否如设想（如 openreview 历史 'doi' 字段可能指"同一著作的另一 DOI"而非
        真正预印本/发表版关系——见 merge.py NEEDS_DECISION）——不这样落证据，controller
        裁决③"靠 evidence 溯源核实"就无从执行。二者互斥（pull 路径无 source 概念、
        aggregator 路径 venue-agnostic），只按调用方实际持有的那个填。

        调用方（`upsert_paper` 与 `merge_ingest` 分支树）都在同一事务、拿到 `paper_id` 后
        调用本方法——两条写路径共享同一套判定，见 merge.py 裁决点 7。
        """
        meta_map = dict(meta)
        journal_ref = meta_map.get("journal_ref")
        for clue_key, (target_scheme, role) in _PREPRINT_CLUE_ROLES.items():
            raw_value = meta_map.get(clue_key)
            if not raw_value:
                continue
            if target_scheme == "arxiv":
                normalized_value = _normalize_arxiv_clue(raw_value)
                if normalized_value is None:
                    log_event(
                        "DEBUG",
                        f"preprint_of clue unparseable: {clue_key}={raw_value!r} is not a "
                        "recognizable arxiv id (even after URL/version stripping); skipped",
                        paper_id=paper_id,
                    )
                    continue
                scheme, value = target_scheme, normalized_value
            else:
                scheme, value = normalize_identifier(target_scheme, raw_value)
            row = conn.execute(
                "SELECT paper_id FROM identifier WHERE scheme = ? AND value = ?",
                (scheme, value),
            ).fetchone()
            if row is None:
                log_event(
                    "DEBUG",
                    f"preprint_of clue dangling: {clue_key}={raw_value!r} has no matching "
                    f"identifier (scheme={scheme!r}) yet; skipped, no edge built",
                    paper_id=paper_id,
                )
                continue
            target_id = str(row["paper_id"])
            if target_id == paper_id:
                continue  # 自指防御：正常数据不会出现，保守跳过（不建自环边）
            from_paper, to_paper = (
                (paper_id, target_id) if role == "from" else (target_id, paper_id)
            )
            evidence: dict[str, object] = {
                "reason": f"meta-clue:{clue_key}",
                "clue_key": clue_key,
                "clue_value": raw_value,
            }
            if source is not None:
                evidence["source"] = source
            if venue_id is not None:
                evidence["venue_id"] = venue_id
            if clue_key == "doi" and journal_ref:
                evidence["journal_ref"] = journal_ref
            self._upsert_preprint_relation(
                conn, from_paper, to_paper, _PREPRINT_CLUE_CONFIDENCE, evidence
            )

    @staticmethod
    def _upsert_preprint_relation(
        conn: sqlite3.Connection,
        from_paper: str,
        to_paper: str,
        confidence: float,
        evidence: dict[str, object],
    ) -> None:
        """建/刷新 preprint_of（from=预印本→to=发表版）；方向由角色表冻结、非任意快照定向。

        与 `_upsert_candidate` 的三点差异（其余同构，含"绝不删行"底线）：
        ①preprint_of 方向是**语义不变量**（controller 裁决①），故只按精确 `(from_paper,
        to_paper, kind)` 主键查/插，不需要 `_upsert_candidate` 那样的双向 OR 查询（那是
        `candidate_duplicate` 无序对+快照定向的产物，本 kind 不适用）；
        ②本 kind 的证据全部来自归一 identifier 精确匹配、强度对等，省去
        `_EVIDENCE_STRENGTH` 序，仅以"evidence_json 是否有变化"判断要不要刷新；
        ③`decided` 语义按表设计是"NULL=有效待复核"（controller 裁决⑤）而非
        `candidate_duplicate` 的"待审阻塞"——但仍尊重已人工裁决的行：已裁决（decided 非空）
        绝不覆盖，与 `_upsert_candidate` 同一底线。

        **反向行守卫（独立审查 re-review #6，P1；本 kind 唯一的双向矛盾环防线）**：写入
        前先查一次**反向行** `(to_paper, from_paper, kind='preprint_of')` 是否已存在——
        存在即 DEBUG 记录后跳过，不写本方向、也**不删旧行**（先到先得；方向争议是数据
        本身的矛盾信号，留给未来人工 dedupe 流程仲裁，本方法不越权物理改写）。本守卫
        同时覆盖两种成因，`_apply_preprint_clues` 侧不再需要（也确已移除）单独的预判：
        - **同一调用内**：doi 与 arxiv 两条线索若都解析到同一 target，会依次尝试写出
          方向相反的两条边——按 `_PREPRINT_CLUE_ROLES` 的字典声明序（doi 先于 arxiv），
          doi 方向先落地，arxiv 方向随后撞见反向行、被本守卫挡下。
        - **跨观测**（独立审查 re-review REOPEN #6，四步时序实测证伪了旧 P1-1 的同调用内
          预判"够用"的假设）：target 的 identifier 集合在两次 SELF 观测之间发生变化——
          例如 ①target 最初只有 arxiv；②self 首次观测（仅 arxiv 线索）建
          `target→self`；③target 经普通强合并（与 preprint_of 无关的另一条 stub）聚合
          进 doi；④self 再次观测、这次 doi 与 arxiv 两条线索都能解析到同一 target——若
          无本守卫会再建 `self→target`，与步骤②遗留、"绝不删行"永存的旧边 `target→self`
          构成矛盾对并存。写入前的反向查询天然覆盖这一间隔任意长、中间状态任意变化的
          跨观测场景，不依赖"两条线索是否同一调用处理"这个更窄的条件。

        独立审查 P2-1（如实记录既定简化，含反向行守卫落地后的补充）：证据终态取**末次
        观测**、非并集、可降级——同一 `(from,to)` 若先后被强度不同的观测触及（如首次带
        `journal_ref` 补充证据、二次观测缺失该字段），后者会整体覆盖前者、`journal_ref`
        随之丢失；**溯源字段（`venue_id`/`source`）同属此列、归同一族简化**——若同一
        `(from,to)` 先后经两条写路径观测（pull 路径带 venue_id、aggregator 路径带
        source），evidence 里的溯源字段会随最近一次写路径整体翻转、不保留历史来源
        （latent：今日不可达，三个线索 adapter arxiv/cvf/openreview 全走 pull 路径，
        从未经 `merge_ingest`；见 merge.py NEEDS_DECISION）。这与 `_upsert_candidate`
        的"新证据强度不弱于既有才刷新、反向不降级"刻意分岔：本 kind 无 weak/strong 分级
        （见 `_PREPRINT_CLUE_CONFIDENCE` 注释），"证据是否变化"是唯一刷新判据，没有强度
        序可比较、也就没有"防降级"的锚点可依附——取舍成本上界很小（evidence_json 只是审计
        辅助字段，不参与查询/去重语义，`decided` 才是真正需要保护的不变量）。
        """
        reverse = conn.execute(
            "SELECT 1 FROM paper_relation WHERE from_paper = ? AND to_paper = ? AND kind = ?",
            (to_paper, from_paper, "preprint_of"),
        ).fetchone()
        if reverse is not None:
            log_event(
                "DEBUG",
                f"preprint_of reverse edge already exists ({to_paper!r}->{from_paper!r}); "
                f"skipping {from_paper!r}->{to_paper!r} to avoid a bidirectional edge",
                from_paper=from_paper,
                to_paper=to_paper,
            )
            return
        evidence_json = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
        row = conn.execute(
            "SELECT evidence_json, decided FROM paper_relation "
            "WHERE from_paper = ? AND to_paper = ? AND kind = ?",
            (from_paper, to_paper, "preprint_of"),
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO paper_relation "
                "(from_paper, to_paper, kind, confidence, evidence_json, decided) "
                "VALUES (?,?,?,?,?,?) "
                "ON CONFLICT (from_paper, to_paper, kind) DO NOTHING",
                (from_paper, to_paper, "preprint_of", confidence, evidence_json, None),
            )
            return
        if row["decided"] is not None or row["evidence_json"] == evidence_json:
            return
        conn.execute(
            "UPDATE paper_relation SET confidence = ?, evidence_json = ? "
            "WHERE from_paper = ? AND to_paper = ? AND kind = ?",
            (confidence, evidence_json, from_paper, to_paper, "preprint_of"),
        )

    # -- preprint_of 关联报告查询（T16；AC-7.4 后半，design/06 §3 单一事实源）----

    def list_preprint_relations(self) -> list[sqlite3.Row]:
        """preprint_of 边的只读关联视图（T16；`preprint_report.build_preprint_report` 的
        唯一数据源）。

        逐边一行，双端各自 join 出 title/year/venue 名——venue 名可能为 `NULL`：
        aggregator 路径（`merge_ingest`→`_create_paper`）建的 paper `venue_id=NULL`
        （"venue-agnostic"，见该方法 docstring），两端各自独立可空，故用两次
        `LEFT JOIN`（而非 `JOIN`）venue，任一端缺 venue 都不丢该边。`kind='preprint_of'`
        固定；`decided` 原样返回（`None`=待复核，也可能是人工 `merged`/`rejected`——
        `_upsert_preprint_relation` docstring "decided 非空=已人工裁决"）：本查询不按
        `decided` 过滤，报告层如实展示全部边，不静默隐藏已裁决记录（AC-7.4"关联报告"
        的可审计性要求）。

        排序：published venue 名非空者优先、按名称升序（`(vb.name IS NULL)` 在 SQLite
        中假=0/真=1，ASC 下非空排前）、NULL venue 分组殿后；组内按 published year→
        published 标题→preprint 标题排序，末尾以两端 paper_id 兜底全确定性（同
        `list_papers` "ORDER BY title, id" 先例，防同标题同年份时输出顺序不稳定）。
        """
        return self.db.query(
            "SELECT "
            "  r.from_paper AS preprint_id, r.to_paper AS published_id, "
            "  r.confidence AS confidence, r.evidence_json AS evidence_json, "
            "  r.decided AS decided, "
            "  pp.title AS preprint_title, pp.year AS preprint_year, "
            "  vp.name AS preprint_venue, "
            "  pb.title AS published_title, pb.year AS published_year, "
            "  vb.name AS published_venue "
            "FROM paper_relation r "
            "JOIN paper pp ON pp.id = r.from_paper "
            "JOIN paper pb ON pb.id = r.to_paper "
            "LEFT JOIN venue vp ON vp.id = pp.venue_id "
            "LEFT JOIN venue vb ON vb.id = pb.venue_id "
            "WHERE r.kind = 'preprint_of' "
            "ORDER BY (vb.name IS NULL), vb.name, pb.year, pb.title, pp.title, "
            "         r.from_paper, r.to_paper"
        )

    # -- dedupe review（T13；AC-7.3）：候审列表 / 裁决 / 回滚 -------------------
    #
    # 语义总纲见本模块「dedupe review 与 same_as 聚合语义」注释块——那里是权威说明，
    # 以下方法只是它的机制载体（策略/呈现在 `dedupe_cli.py`，同 repo↔merge 的分工先例）。

    def list_candidates(
        self, *, state: str = "pending", limit: int | None = None
    ) -> list[DedupeCandidate]:
        """列出 `candidate_duplicate`（kind 隔离，语义 1），按证据强度降序、无序对字典序。

        `state`：`pending`（默认，`decided IS NULL`）/`merged`/`rejected`/`all`。
        排序在 Python 侧完成而非 SQL：无序对的"小端/大端"需要 `MIN/MAX(a,b)` 标量函数，
        SQLite 与 PostgreSQL 写法不同（后者是 `LEAST/GREATEST`），会破坏方言中性
        （D-001）；候审集是人工审核尺度（数十~数百条），Python 排序代价可忽略。
        `limit` 在排序**之后**截断，故"只看最强的 N 条"语义稳定。
        """
        if state not in CANDIDATE_STATES:
            raise CrawlerError(
                ErrorClass.CONFIG,
                f"未知的候选状态 {state!r}；可选：{', '.join(CANDIDATE_STATES)}",
            )
        sql = (
            "SELECT from_paper, to_paper, confidence, evidence_json, decided "
            "FROM paper_relation WHERE kind = ?"
        )
        params: list[object] = ["candidate_duplicate"]
        if state == "pending":
            sql += " AND decided IS NULL"
        elif state != "all":
            sql += " AND decided = ?"
            params.append(state)
        rows = self.db.query(sql, params)

        pairs: list[tuple[float, str, str, sqlite3.Row]] = []
        for row in rows:
            low, high = sorted((str(row["from_paper"]), str(row["to_paper"])))
            strength = float(row["confidence"]) if row["confidence"] is not None else 0.0
            pairs.append((-strength, low, high, row))
        pairs.sort(key=lambda item: item[:3])
        if limit is not None:
            pairs = pairs[:limit]
        out: list[DedupeCandidate] = []
        for _rank, low, high, row in pairs:
            evidence = _evidence_dict(row["evidence_json"])
            reason = evidence.get("reason")
            preprint = self._pair_relation(low, high, "preprint_of")
            out.append(
                DedupeCandidate(
                    paper_a=self._paper_brief(low),
                    paper_b=self._paper_brief(high),
                    confidence=row["confidence"],
                    reason=reason if isinstance(reason, str) else None,
                    evidence=evidence,
                    decided=row["decided"],
                    preprint_of=(
                        None
                        if preprint is None
                        else (str(preprint["from_paper"]), str(preprint["to_paper"]))
                    ),
                )
            )
        return out

    def count_candidates(self, *, state: str = "pending") -> int:
        """按 state 数候审对的条数（只 COUNT、不构造 brief——供 CLI 判断是否被 `--limit` 截断）。"""
        if state not in CANDIDATE_STATES:
            raise CrawlerError(
                ErrorClass.CONFIG,
                f"未知的候选状态 {state!r}；可选：{', '.join(CANDIDATE_STATES)}",
            )
        sql = "SELECT COUNT(*) AS n FROM paper_relation WHERE kind = ?"
        params: list[object] = ["candidate_duplicate"]
        if state == "pending":
            sql += " AND decided IS NULL"
        elif state != "all":
            sql += " AND decided = ?"
            params.append(state)
        return int(self.db.query(sql, params)[0]["n"])

    def _paper_brief(self, paper_id: str) -> PaperBrief:
        """paper 行 + identifier 列表 + asset 计数的只读投影（外键保证 paper 行存在）。"""
        row = self.db.query(
            "SELECT id, title, venue_id, year FROM paper WHERE id = ?", (paper_id,)
        )[0]
        identifiers = self.db.query(
            "SELECT scheme, value FROM identifier WHERE paper_id = ? ORDER BY scheme, value",
            (paper_id,),
        )
        assets = self.db.query("SELECT COUNT(*) AS n FROM asset WHERE paper_id = ?", (paper_id,))[0]
        return PaperBrief(
            paper_id=str(row["id"]),
            title=str(row["title"]),
            venue_id=row["venue_id"],
            year=row["year"],
            identifiers=tuple(f"{r['scheme']}:{r['value']}" for r in identifiers),
            asset_count=int(assets["n"]),
        )

    def decide_candidate(self, paper_a: str, paper_b: str, decision: str) -> DecisionOutcome:
        """人工裁决一对候审（语义 2）：`merge` 落 `same_as(decided='merged')`；`reject` 只置态。

        无序对：两个 paper_id 的给出顺序不影响结果（merge.py 裁决 5）。幂等：重复同一裁决
        不改库、`changed=False`。**可改判**：`merge` 后再 `reject` 会把 same_as 边降级
        （聚合撤销、行留痕），反之亦然——`decided` 是人的判断，不是一次性写死的墓碑。
        两 paper 之间没有 `candidate_duplicate` 边（含只有 `preprint_of` 的情形）→
        `CrawlerError(CONFIG)` 响亮拒绝：绝不凭空造 same_as，人工合并也必须有候审证据在先。

        **preprint_of 共存守卫（独立审查 P1-1，聚合语义 1 的逐对口径）**：该对若另挂任一
        方向的 `preprint_of` 边，`merge` **一律拒绝**（D-007 红线：预印本↔刊发版是两条
        独立著作记录，双份全文，不合并）——kind 隔离必须判到"对"，只判"这条边是不是
        candidate_duplicate"堵不住两种边并存的真实链路（弱信号候审 + arxiv 回填线索）。
        **无 `--force` 旁路**；`reject` 不受此限（关掉误报候审是合法操作）。
        """
        if decision not in DEDUPE_DECISIONS:
            raise CrawlerError(
                ErrorClass.CONFIG,
                f"未知裁决 {decision!r}；可选：{', '.join(DEDUPE_DECISIONS)}",
            )
        decided = DEDUPE_DECISIONS[decision]
        low, high = self._normalize_pair(paper_a, paper_b)
        with self.db.tx() as conn:
            self._require_paper(conn, low)
            self._require_paper(conn, high)
            row = self._find_relation(conn, low, high, "candidate_duplicate")
            if row is None:
                raise CrawlerError(
                    ErrorClass.CONFIG,
                    f"{low} 与 {high} 之间没有 candidate_duplicate 边"
                    "（preprint_of 边不进 dedupe 流程）",
                )
            if decision == "merge":
                preprint = self._find_relation(conn, low, high, "preprint_of")
                if preprint is not None:
                    raise CrawlerError(
                        ErrorClass.CONFIG,
                        f"该 pair 存在 preprint_of 关系（{preprint['from_paper']} → "
                        f"{preprint['to_paper']}，预印本→发表版）——预印本↔刊发版不是重复，"
                        "不可合并（D-007：双条 paper 双份全文）。若该候审属误报，用 reject 关闭。",
                    )
            changed = row["decided"] != decided
            if changed:
                conn.execute(
                    "UPDATE paper_relation SET decided = ? "
                    "WHERE from_paper = ? AND to_paper = ? AND kind = ?",
                    (decided, row["from_paper"], row["to_paper"], "candidate_duplicate"),
                )
            if decision == "merge":
                changed = self._promote_same_as(conn, low, high, row) or changed
            else:
                changed = self._demote_same_as(conn, low, high) or changed
        log_event(
            "INFO",
            f"dedupe decision {decision} for {low} ~ {high} (changed={changed})",
            paper_a=low,
            paper_b=high,
        )
        return DecisionOutcome(paper_a=low, paper_b=high, decided=decided, changed=changed)

    def revert_candidate(self, paper_a: str, paper_b: str) -> DecisionOutcome:
        """回滚一对已裁决的候审（AC-7.3）：候审行与 same_as 行的 `decided` 双双置回 NULL。

        聚合视图随之还原（语义 3 的谓词是 `decided='merged'`），paper/identifier/asset
        三表全程零改动。已是待审态 → `changed=False` 幂等空操作（不报错）；两 paper 之间
        本就没有候审边 → `CrawlerError(CONFIG)`（多半是 id 敲错，响亮好过静默成功）。
        """
        low, high = self._normalize_pair(paper_a, paper_b)
        with self.db.tx() as conn:
            self._require_paper(conn, low)
            self._require_paper(conn, high)
            row = self._find_relation(conn, low, high, "candidate_duplicate")
            if row is None:
                raise CrawlerError(
                    ErrorClass.CONFIG, f"{low} 与 {high} 之间没有 candidate_duplicate 边可回滚"
                )
            changed = row["decided"] is not None
            if changed:
                conn.execute(
                    "UPDATE paper_relation SET decided = NULL "
                    "WHERE from_paper = ? AND to_paper = ? AND kind = ?",
                    (row["from_paper"], row["to_paper"], "candidate_duplicate"),
                )
            changed = self._demote_same_as(conn, low, high) or changed
        log_event(
            "INFO",
            f"dedupe revert for {low} ~ {high} (changed={changed})",
            paper_a=low,
            paper_b=high,
        )
        return DecisionOutcome(paper_a=low, paper_b=high, decided=None, changed=changed)

    @staticmethod
    def _normalize_pair(paper_a: str, paper_b: str) -> tuple[str, str]:
        """无序对归一为 (小 id, 大 id)；自指对响亮拒绝。"""
        if paper_a == paper_b:
            raise CrawlerError(ErrorClass.CONFIG, f"不能把 paper {paper_a} 与自身裁决为重复")
        return (paper_a, paper_b) if paper_a < paper_b else (paper_b, paper_a)

    @staticmethod
    def _require_paper(conn: sqlite3.Connection, paper_id: str) -> None:
        row = conn.execute("SELECT 1 FROM paper WHERE id = ?", (paper_id,)).fetchone()
        if row is None:
            raise CrawlerError(ErrorClass.CONFIG, f"未知 paper id: {paper_id}")

    @staticmethod
    def _find_relation(
        conn: sqlite3.Connection, paper_a: str, paper_b: str, kind: str
    ) -> sqlite3.Row | None:
        """写事务内按无序对查一条关系边（谓词见 `_RELATION_PAIR_SQL`）。"""
        row: sqlite3.Row | None = conn.execute(
            _RELATION_PAIR_SQL, (kind, paper_a, paper_b, paper_b, paper_a)
        ).fetchone()
        return row

    def _pair_relation(self, paper_a: str, paper_b: str, kind: str) -> sqlite3.Row | None:
        """只读路径的同款无序对查询（`list_candidates` 的 preprint_of 共存探测用）。"""
        rows = self.db.query(_RELATION_PAIR_SQL, (kind, paper_a, paper_b, paper_b, paper_a))
        return rows[0] if rows else None

    def _promote_same_as(
        self, conn: sqlite3.Connection, low: str, high: str, candidate: sqlite3.Row
    ) -> bool:
        """建/复活 `same_as(decided='merged')`；返回是否改变了库态（幂等重放 → False）。

        **证据不整体覆写**（独立审查 P2-3，controller 裁：审计历史价值 > 字段整洁）：复活
        既有行时在其 `evidence_json` **上叠加**本次的四个键（reason/candidate_reason/
        candidate_confidence/decided_at），既有键（尤其上一次回滚写的 `reverted_at`）原样
        保留——"这条边曾被回滚过、又被重新合并"是审计时最该看见的事实，被一次覆写抹掉就
        再也追不回来（关系行本身绝不删，历史只存在于 evidence 里）。因此 `reverted_at` 的
        语义是"**最近一次**回滚时刻"，可能早于 `decided_at`（即已被重新合并）：读者按两个
        时间戳的先后判断当前是"合并生效"还是"已回滚"，`decided` 列才是权威态。
        """
        existing = self._find_relation(conn, low, high, "same_as")
        if existing is not None and existing["decided"] == "merged":
            return False
        history = _evidence_dict(existing["evidence_json"]) if existing is not None else {}
        history.update(
            {
                "reason": _SAME_AS_MERGE_REASON,
                "candidate_reason": _evidence_reason(candidate["evidence_json"]),
                "candidate_confidence": candidate["confidence"],
                "decided_at": utcnow_iso(),
            }
        )
        evidence = json.dumps(history, ensure_ascii=False, sort_keys=True)
        if existing is None:
            conn.execute(
                "INSERT INTO paper_relation "
                "(from_paper, to_paper, kind, confidence, evidence_json, decided) "
                "VALUES (?,?,?,?,?,?)",
                (low, high, "same_as", _SAME_AS_CONFIDENCE, evidence, "merged"),
            )
            return True
        conn.execute(
            "UPDATE paper_relation SET confidence = ?, evidence_json = ?, decided = ? "
            "WHERE from_paper = ? AND to_paper = ? AND kind = ?",
            (
                _SAME_AS_CONFIDENCE,
                evidence,
                "merged",
                existing["from_paper"],
                existing["to_paper"],
                "same_as",
            ),
        )
        return True

    def _demote_same_as(self, conn: sqlite3.Connection, low: str, high: str) -> bool:
        """把该对的 same_as 边降级为 `decided=NULL`（聚合撤销）；**绝不删行**，只留痕。"""
        existing = self._find_relation(conn, low, high, "same_as")
        if existing is None or existing["decided"] is None:
            return False
        evidence = _evidence_dict(existing["evidence_json"])
        evidence["reverted_at"] = utcnow_iso()
        conn.execute(
            "UPDATE paper_relation SET evidence_json = ?, decided = NULL "
            "WHERE from_paper = ? AND to_paper = ? AND kind = ?",
            (
                json.dumps(evidence, ensure_ascii=False, sort_keys=True),
                existing["from_paper"],
                existing["to_paper"],
                "same_as",
            ),
        )
        return True

    # -- same_as 聚合视图（T13 冻结件；消费方 T14/T16） -------------------------

    def merged_groups(self) -> list[MergedGroup]:
        """全部合并类（语义 3/4）：`same_as(decided='merged')` 的无向连通分量，按主行排序。"""
        return self._merged_index()[0]

    def merged_group(self, paper_id: str) -> MergedGroup | None:
        """该 paper 所属的合并类；未参与任何已裁决合并 → None（单元素不成类）。"""
        return next((g for g in self.merged_groups() if paper_id in g.members), None)

    def merged_view(self, paper_id: str) -> MergedView | None:
        """合并类的归并视图（语义 5）：主行 + 全成员 + identifier 并集 + asset 全集计数。"""
        group = self.merged_group(paper_id)
        return None if group is None else self._view_of(group)

    def merged_views(self) -> list[MergedView]:
        """全部合并类的归并视图（一次索引、逐类投影；T16 报告与 `dedupe groups` 的入口）。"""
        return [self._view_of(group) for group in self.merged_groups()]

    def _view_of(self, group: MergedGroup) -> MergedView:
        members = tuple(self._paper_brief(pid) for pid in group.members)
        return MergedView(
            canonical=next(m for m in members if m.paper_id == group.canonical),
            members=members,
            identifiers=tuple(sorted({i for m in members for i in m.identifiers})),
            asset_count=sum(m.asset_count for m in members),
        )

    def fold_merged(self, rows: Sequence[sqlite3.Row]) -> list[sqlite3.Row]:
        """**结果集内**按合并类折叠 paper 行（语义 6）：同类只留一行代表，幸存行不重排。

        代表 = 结果集内该类成员按 `(-identifier 数, paper_id)` 的最小者——类主行在集内时
        它自然就是代表；主行不在集内（如属于另一 venue/issue）时退化为集内最佳者，
        **绝不整类丢弃**。无任何已裁决合并时是恒等函数（零开销路径）。
        """
        groups, counts = self._merged_index()
        if not groups:
            return list(rows)
        group_of = {pid: index for index, group in enumerate(groups) for pid in group.members}
        present: dict[int, list[str]] = {}
        for row in rows:
            index = group_of.get(str(row["id"]))
            if index is not None:
                present.setdefault(index, []).append(str(row["id"]))
        representative = {
            index: min(members, key=lambda pid: (-counts.get(pid, 0), pid))
            for index, members in present.items()
        }
        out: list[sqlite3.Row] = []
        for row in rows:
            paper_id = str(row["id"])
            index = group_of.get(paper_id)
            if index is None or representative[index] == paper_id:
                out.append(row)
        return out

    def _merged_index(self) -> tuple[list[MergedGroup], dict[str, int]]:
        """合并类索引 + 类成员的 identifier 计数（主行判据的输入），一次算好两处复用。"""
        edges = self.db.query(
            "SELECT from_paper, to_paper FROM paper_relation WHERE kind = ? AND decided = ?",
            ("same_as", "merged"),
        )
        if not edges:
            return [], {}

        parent: dict[str, str] = {}

        def find(node: str) -> str:
            """并查集查根（**不做路径压缩**：合并类是人工裁决尺度的几个元素，链长天然极短，
            压缩只会换来一段几乎跑不到的分支；用 union-by-min 保证根的选取确定即可）。"""
            parent.setdefault(node, node)
            while parent[node] != node:
                node = parent[node]
            return node

        for edge in edges:
            root_a, root_b = find(str(edge["from_paper"])), find(str(edge["to_paper"]))
            if root_a != root_b:
                parent[max(root_a, root_b)] = min(root_a, root_b)

        components: dict[str, list[str]] = {}
        for node in list(parent):
            components.setdefault(find(node), []).append(node)
        counts = self._identifier_counts(sorted(parent))
        groups = [
            MergedGroup(
                canonical=min(members, key=lambda pid: (-counts.get(pid, 0), pid)),
                members=tuple(sorted(members)),
            )
            for members in components.values()
        ]
        groups.sort(key=lambda group: group.canonical)
        return groups, counts

    def _identifier_counts(self, paper_ids: Sequence[str]) -> dict[str, int]:
        """逐 paper 的 identifier 条数（分块 IN 查询，避开 SQLite 变量数上限）。"""
        counts: dict[str, int] = {}
        for start in range(0, len(paper_ids), _SQL_PARAM_CHUNK):
            chunk = list(paper_ids[start : start + _SQL_PARAM_CHUNK])
            placeholders = ",".join("?" * len(chunk))
            rows = self.db.query(
                "SELECT paper_id, COUNT(*) AS n FROM identifier "
                f"WHERE paper_id IN ({placeholders}) GROUP BY paper_id",
                chunk,
            )
            for row in rows:
                counts[str(row["paper_id"])] = int(row["n"])
        return counts

    def list_papers(
        self, venue_id: str, issue_id: str | None = None, *, aggregate: bool = False
    ) -> list[sqlite3.Row]:
        """列出某 venue 的 paper；给定 issue_id 时限定该期内（经 paper_issue_link）。按标题排序。

        `aggregate=True` 时对结果集施加 `same_as(decided='merged')` 折叠（`fold_merged`，
        T13 聚合语义 6）。**默认 False**：pull 级联（`runner._select_papers`）依赖本方法
        取全部行派生 resolve/fetch 任务，折叠会让被合并的一侧永远拿不到资产——聚合是
        显示层语义，绝不作为数据过滤器接进流水线。
        """
        if issue_id is not None:
            rows = self.db.query(
                "SELECT p.* FROM paper p "
                "JOIN paper_issue_link l ON p.id = l.paper_id "
                "WHERE p.venue_id = ? AND l.issue_id = ? "
                "ORDER BY p.title, p.id",
                (venue_id, issue_id),
            )
        else:
            rows = self.db.query(
                "SELECT * FROM paper WHERE venue_id = ? ORDER BY title, id", (venue_id,)
            )
        return self.fold_merged(rows) if aggregate else rows

    def set_paper_state(self, paper_id: str, ingest_state: str) -> None:
        """更新 paper.ingest_state（metadata_only|resolved|fetched|extracted）。"""
        self.db.execute(
            "UPDATE paper SET ingest_state = ?, updated_at = ? WHERE id = ?",
            (ingest_state, utcnow_iso(), paper_id),
        )

    def bind_paper_venue(self, paper_id: str, venue_id: str) -> None:
        """把**尚未绑定 venue** 的 paper 绑定到 venue_id（`grab` 单篇路径）。

        `MergeEngine.ingest`（crossref 等 aggregator 路径）建的 paper venue_id=NULL；grab 须
        绑定后 fetch 才可经 asset→paper→venue_id 路由到目标平台 adapter。`WHERE venue_id IS
        NULL` 保证幂等且**不改写既有归属**（保守——反查命中的已绑定 paper 不动）。
        """
        self.db.execute(
            "UPDATE paper SET venue_id = ?, updated_at = ? WHERE id = ? AND venue_id IS NULL",
            (venue_id, utcnow_iso(), paper_id),
        )

    # -- asset ---------------------------------------------------------------

    def plan_asset(self, paper_id: str, plan: AssetPlan, source_adapter: str) -> str:
        """幂等登记一个 planned asset，返回 asset_id。业务键 (paper_id,kind,version) 查后插；
        已存在（含已 fetched）则原样返回既有 id，不回退状态。"""
        with self.db.tx() as conn:
            params: list[object] = [paper_id, plan.kind.value]
            where = " AND ".join(
                [
                    "paper_id = ?",
                    "kind = ?",
                    _null_safe_eq("version", plan.version, params),
                ]
            )
            existing = conn.execute(f"SELECT id FROM asset WHERE {where}", params).fetchone()
            if existing is not None:
                return str(existing["id"])
            asset_id = new_ulid()
            conn.execute(
                "INSERT INTO asset "
                "(id, paper_id, kind, version, url, auth_needed, state, file_path, bytes, "
                " sha256, fetched_at, source_adapter) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    asset_id,
                    paper_id,
                    plan.kind.value,
                    plan.version,
                    plan.url,
                    plan.auth_needed.value,
                    "planned",
                    None,
                    None,
                    None,
                    None,
                    source_adapter,
                ),
            )
            return asset_id

    def refresh_asset_plan(self, asset_id: str, *, url: str, auth_needed: str) -> None:
        """fetch 前 re-resolve 后同步 asset 行的执行细节（T7c 追加设计裁决，phase1-plan）。

        asset 的幂等身份 = (paper, kind, version) 不变；url/auth_needed 属执行细节，
        fetch 子任务执行时现场 resolve 取最新值后经本方法落库再 fetch（signed url /
        entitlement 时效、mock 故障注入解除等场景）。**已 fetched 的不回退不改**；
        其余状态（planned/failed 等）只刷新这两列、不触碰状态机。asset 不存在时
        零行更新、静默返回（缺行由 fetch 阶段自身的 CONFIG 路由处理）。
        """
        self.db.execute(
            "UPDATE asset SET url = ?, auth_needed = ? WHERE id = ? AND state <> 'fetched'",
            (url, auth_needed, asset_id),
        )

    def list_assets(
        self, *, venue_id: str | None = None, state: str | None = None
    ) -> list[sqlite3.Row]:
        """列出 asset，可按 venue（经 paper 关联）与 state 过滤；稳定排序。"""
        sql = "SELECT a.* FROM asset a"
        clauses: list[str] = []
        params: list[object] = []
        if venue_id is not None:
            sql += " JOIN paper p ON a.paper_id = p.id"
            clauses.append("p.venue_id = ?")
            params.append(venue_id)
        if state is not None:
            clauses.append("a.state = ?")
            params.append(state)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY a.paper_id, a.kind, a.version"
        return self.db.query(sql, params)

    def get_asset(self, asset_id: str) -> sqlite3.Row | None:
        """按 id 取单个 asset；不存在返回 None。"""
        rows = self.db.query("SELECT * FROM asset WHERE id = ?", (asset_id,))
        return rows[0] if rows else None

    def mark_asset(
        self,
        asset_id: str,
        *,
        state: str,
        file_path: str | None = None,
        bytes_: int | None = None,
        sha256: str | None = None,
    ) -> None:
        """更新 asset 状态与下载产物字段；state='fetched' 时补记 fetched_at。"""
        updates: dict[str, object] = {"state": state}
        if file_path is not None:
            updates["file_path"] = file_path
        if bytes_ is not None:
            updates["bytes"] = bytes_
        if sha256 is not None:
            updates["sha256"] = sha256
        if state == "fetched":
            updates["fetched_at"] = utcnow_iso()
        set_clause = ", ".join(f"{col} = ?" for col in updates)
        self.db.execute(
            f"UPDATE asset SET {set_clause} WHERE id = ?",
            (*updates.values(), asset_id),
        )

    # -- fetch_log -----------------------------------------------------------

    def add_fetch_log(
        self,
        *,
        asset_id: str | None,
        task_id: str | None,
        domain: str,
        url: str,
        http_status: int | None,
        bytes_: int,
        elapsed_ms: int,
        rate_wait_ms: int,
        error_class: str | None = None,
    ) -> None:
        """追加一条取回审计记录（FetchLog；限速合规证据源，design/05 §7）。

        `url` 落库前经 `obslog.redact`（AC-0.4/NFR-8：fetch_log.url 不得含未脱敏凭证——
        Phase 2 起签名 URL/token 会进入此审计路径）。
        """
        self.db.execute(
            "INSERT INTO fetch_log "
            "(id, asset_id, task_id, domain, url, http_status, bytes, elapsed_ms, "
            " rate_wait_ms, error_class, ts) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                new_ulid(),
                asset_id,
                task_id,
                domain,
                redact(url),
                http_status,
                bytes_,
                elapsed_ms,
                rate_wait_ms,
                error_class,
                utcnow_iso(),
            ),
        )

    def finalize_fetch(
        self,
        asset_id: str,
        *,
        file_path: str,
        bytes_: int,
        sha256: str | None,
        fetch_log_row: FetchLogRow,
    ) -> None:
        """fetch 成功收尾的组合事务 API（Phase 2 T1；仓储层唯一的组合事务入口）。

        在单个 `BEGIN IMMEDIATE` 事务内原子完成两步：
          1. asset → state='fetched'（并补 file_path/bytes/sha256/fetched_at）；
          2. 追加一条成功 fetch_log 行（url 经 `redact` 脱敏，与 `add_fetch_log` 同源）。

        取代旧的 `mark_asset(fetched)` + `add_fetch_log` 两次独立提交——消除二者之间的
        SIGKILL 缝隙（AC-1.3："已 fetched 但成功日志缺失"的已知窗口）。**直接组合 SQL、
        不调用自带事务的 `mark_asset`/`add_fetch_log`**（repo 事务不可嵌套）。事务中途
        任何异常都整体 ROLLBACK（asset 状态与日志同进同退）。
        """
        now = utcnow_iso()
        with self.db.tx() as conn:
            conn.execute(
                "UPDATE asset SET state = 'fetched', file_path = ?, bytes = ?, sha256 = ?, "
                "fetched_at = ? WHERE id = ?",
                (file_path, bytes_, sha256, now, asset_id),
            )
            conn.execute(
                "INSERT INTO fetch_log "
                "(id, asset_id, task_id, domain, url, http_status, bytes, elapsed_ms, "
                " rate_wait_ms, error_class, ts) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    new_ulid(),
                    asset_id,
                    fetch_log_row.task_id,
                    fetch_log_row.domain,
                    redact(fetch_log_row.url),
                    fetch_log_row.http_status,
                    fetch_log_row.bytes_,
                    fetch_log_row.elapsed_ms,
                    fetch_log_row.rate_wait_ms,
                    fetch_log_row.error_class,
                    now,
                ),
            )

    def fetch_logs(self, *, domain: str | None = None) -> list[sqlite3.Row]:
        """取回 FetchLog，可按 domain 过滤；按时间戳稳定排序。"""
        if domain is not None:
            return self.db.query(
                "SELECT * FROM fetch_log WHERE domain = ? ORDER BY ts, id", (domain,)
            )
        return self.db.query("SELECT * FROM fetch_log ORDER BY ts, id")

    def count_fetch_today(self, domain: str) -> int:
        """某 domain **当日（UTC）fetch 尝试篇次**（auth-framework §8.3；AC-4.4 日配额对账）。

        口径统一为"fetch 尝试篇次"：fetch 阶段每次尝试落一行 fetch_log（design/05 §7），
        **成败均计**（失败行 error_class 非空同样计入，故不加 error_class 过滤）；resolve
        页请求不写 fetch_log、天然不计。`ts` 是 fetch_log 实名列，`DATE(ts)=DATE('now')`
        经索引 `idx_fetch_log_domain_ts` 支撑（`ts` 存 UTC ISO8601，SQLite DATE() 归一到
        UTC 日）。OA-fallback direct fetch 落第三方 OA host 域、非 auth 平台 domain，按本
        查询天然不占 auth 平台配额（§8.1 限速隔离的对账侧印证）。
        """
        rows = self.db.query(
            "SELECT COUNT(*) AS n FROM fetch_log WHERE domain = ? AND DATE(ts) = DATE('now')",
            (domain,),
        )
        return int(rows[0]["n"])

    def count_browser_fetch_today(self, venue_id: str, domain: str) -> int:
        """某 venue×域 **当日（UTC）fetch 尝试篇次**（11-browser-fetch §7.2 派生查询）。

        browser-fetch 日配额（§7.1 L3）的唯一数据源——**零新表、零新事实源**：venue 维度
        经 `fetch_log ⋈ task` 派生（`fetch_log` 无 venue 列但有 `task_id`，`task.venue_id`
        提供该维度）。口径与 `count_fetch_today` **一字不差**（成败均计、`DATE(ts)` UTC 日、
        resolve 页不计），只是多一个 venue 维度。

        ⚠ 该 join 依赖 `fetch_log.task_id` 非空（§11 开放问题④）：实码核实 `_stage_fetch`/
        `_fetch_oa_direct`/`_fetch_via_browser` 三条写入路径**恒填** task_id（stage handler
        的任务行 id）；`add_fetch_log` 签名允许 None（canary/直调场景），此类无 task 归属的
        行不计入 venue 维度——方向 fail-safe：它们同样不消耗 venue 配额，而域维度上限仍由
        `count_fetch_today` 语义的既有 auth 日配额兜住。
        """
        rows = self.db.query(
            "SELECT COUNT(*) AS n FROM fetch_log f JOIN task t ON t.id = f.task_id "
            "WHERE t.venue_id = ? AND f.domain = ? AND DATE(f.ts) = DATE('now')",
            (venue_id, domain),
        )
        return int(rows[0]["n"])

    def count_recent_fetch_failures(self, domain: str, *, limit: int = 3) -> int:
        """某域**当日最近 `limit` 条** fetch_log 里自最新起**连续失败**的条数（遇成功即止）。

        browser-fetch 熔断（11-browser-fetch §7.1 L4"连续非挑战失败 ≥3 → 该域当日停发"）的
        判据。**偏离登记**：§7.3 原文把它写作进程内运行态计数（`_new_report` 重置）；此处改由
        FetchLog 派生——① 与"唯一事实源 = FetchLog"（§3.4 维度 4）一致，零新状态；② "当日停发"
        本就是**日**语义，跨进程重启不该清零（运行态版本一重启即失效，比设计意图更松）；
        ③ 方向 fail-safe（更保守），且当日出现一次成功即自然解除。

        **`no_entitlement` 不计、亦不打断**（P2-2 审查修复）：NE 是项目里的**独立终态**、
        预期内、不计失败率（auth-framework §8.5 / AC-4.3），与 §7.1 L4"连续非挑战**失败**"的
        字面不符——把它当失败会让"三篇无订阅"误熔断整个域。故 SQL 侧直接**排除** NE 行：
        它既不累加 streak，也不作为"成功"打断 streak（对判据完全透明）。

        **跨通道计数取舍（P2-3，controller 已裁"接受为更保守"）**：本查询按**域**统计，不区分
        取回通道——同域的 httpx direct 失败同样计入 browser 熔断。理由：熔断保护的对象是
        **站点**而非通道，"这个域今天一直在失败"与是谁发的请求无关；且反向漏判（浏览器通道
        对已在失败的域继续敲门）在红线敏感面上代价更高。代价是可能提前停发浏览器通道——
        方向 fail-safe，且当日一次成功即解除。
        """
        rows = self.db.query(
            "SELECT error_class FROM fetch_log "
            "WHERE domain = ? AND DATE(ts) = DATE('now') "
            "AND (error_class IS NULL OR error_class <> 'no_entitlement') "
            "ORDER BY ts DESC, id DESC LIMIT ?",
            (domain, int(limit)),
        )
        streak = 0
        for row in rows:
            if row["error_class"] is None:
                break
            streak += 1
        return streak

    # -- 对账 ----------------------------------------------------------------

    def counts(self, venue_id: str) -> dict[str, int]:
        """AC-1.1 对账口径：某 venue 的 issue/paper 数，及 asset 计划总数与已取回数。

        `assets_planned` = 该 venue 全部 asset 行（每个 asset 建立即为已计划）；
        `assets_fetched` = 其中 state='fetched' 的行数。二者构成"计划 vs 完成"对账。
        """

        def scalar(sql: str) -> int:
            return int(self.db.query(sql, (venue_id,))[0]["n"])

        return {
            "issues": scalar("SELECT COUNT(*) AS n FROM issue WHERE venue_id = ?"),
            "papers": scalar("SELECT COUNT(*) AS n FROM paper WHERE venue_id = ?"),
            "assets_planned": scalar(
                "SELECT COUNT(*) AS n FROM asset a "
                "JOIN paper p ON a.paper_id = p.id WHERE p.venue_id = ?"
            ),
            "assets_fetched": scalar(
                "SELECT COUNT(*) AS n FROM asset a "
                "JOIN paper p ON a.paper_id = p.id "
                "WHERE p.venue_id = ? AND a.state = 'fetched'"
            ),
        }


class SubscriptionRepo:
    """订阅仓储（Phase 6 T1 冻结件）：`subscription` / `subscription_run` 两表 + watermark。

    与 `Repo` 并列而非合并——订阅是独立聚合根（design/06 §1 ER：Subscription 1─N
    SubscriptionRun），与论文/资产那套没有共享事务面；分开也让 T4/T5 的消费面只暴露
    它们真正需要的方法。

    **DSL 类型走局部 import**（沿 `db.py::_backfill_title_norm` 的先例："局部 import
    避免 storage 层顶层依赖上层模块"）：`subs.model` 反过来不依赖 storage，故本类
    与订阅域之间恒无导入环——即使 T5 之后把 `subs/watch.py`（依赖本类）导出到
    `subs/__init__.py` 也不会成环。

    表结构核对（design/06 §2 ↔ `migrations/0001_init.sql`）：两表逐列一致，本卡未改表。

    - `subscription(name PK, query_json NOT NULL, watermark_json, guard_json,
      created_at, last_run_at)`；
    - `subscription_run(id PK, name REFERENCES subscription, started_at, new_count,
      fetched_count, truncated, report_path)`。

    时间列一律 UTC ISO8601（`utcnow_iso`），`truncated` 用 0/1 整数（SQLite 无 bool，
    方言中性；读出时归一为 Python bool 由调用方按需转换）。
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    # -- subscription CRUD ---------------------------------------------------

    def upsert(self, subscription: Subscription) -> None:
        """按 name 幂等写入订阅（DSL 主体 + 护栏）。

        **只更新 `query_json`/`guard_json`**：`watermark_json`/`created_at`/`last_run_at`
        是运行期状态，改订阅内容（如收窄正则）绝不能顺手把增量游标清零——否则下一次
        watch 会把整个历史窗重刷一遍（design/09 §5 增量语义的基本要求）。
        """
        self.db.execute(
            "INSERT INTO subscription "
            "(name, query_json, watermark_json, guard_json, created_at, last_run_at) "
            "VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET "
            "  query_json=excluded.query_json, guard_json=excluded.guard_json",
            (
                subscription.name,
                # sort_keys=False：`to_query_dict()` 已是确定序，含 sources 声明序（P1-1）。
                _json_text(subscription.to_query_dict(), sort_keys=False),
                None,
                _json_text(subscription.guard.to_dict(), sort_keys=False),
                utcnow_iso(),
                None,
            ),
        )

    def get(self, name: str) -> Subscription | None:
        """按 name 取订阅并**还原为 `Subscription`**；不存在返回 None。

        还原走 `Subscription.from_stored`（= 文件加载的同一校验器）：库内存量若因
        手改/旧版本而不合法，此处响亮报错（`SubscriptionInvalid`），不返回半截对象。
        """
        rows = self.db.query("SELECT * FROM subscription WHERE name = ?", (name,))
        return self._row_to_subscription(rows[0]) if rows else None

    def all(self) -> list[Subscription]:
        """全部订阅，按 name 排序（确定性输出，`watch --all` 的遍历序）。"""
        rows = self.db.query("SELECT * FROM subscription ORDER BY name")
        return [self._row_to_subscription(row) for row in rows]

    @staticmethod
    def _row_to_subscription(row: sqlite3.Row) -> Subscription:
        """`subscription` 行 → `Subscription`（`get`/`all` 的单一还原路径）。"""
        from paper_crawler.subs.model import Subscription

        guard_json = row["guard_json"]
        return Subscription.from_stored(
            str(row["name"]),
            str(row["query_json"]),
            str(guard_json) if guard_json is not None else None,
        )

    def list_names(self) -> list[str]:
        """全部订阅名（升序）——不做 DSL 反序列化，供只需清单的调用方。"""
        rows = self.db.query("SELECT name FROM subscription ORDER BY name")
        return [str(row["name"]) for row in rows]

    def delete(self, name: str) -> bool:
        """删除订阅及其全部运行记录；返回是否真的删到（不存在 → False，非错误）。

        先删 `subscription_run` 子行再删父行——外键 `PRAGMA foreign_keys=ON`
        （`Database.__init__`）下顺序不可颠倒。单事务，同进同退。
        """
        with self.db.tx() as conn:
            conn.execute("DELETE FROM subscription_run WHERE name = ?", (name,))
            cursor = conn.execute("DELETE FROM subscription WHERE name = ?", (name,))
            return cursor.rowcount > 0

    def exists(self, name: str) -> bool:
        """订阅是否存在（不解析 DSL）。"""
        return bool(self.db.query("SELECT 1 FROM subscription WHERE name = ?", (name,)))

    # -- watermark（design/09 §5；格式归 T4）---------------------------------

    def read_watermark(self, name: str) -> dict[str, object]:
        """读 `watermark_json` → dict；未运行过（NULL）或空串 → `{}`（首跑语义）。

        本层不解释格式（`{source: {...}, "schema_ver": N}` 归 T4），只保证"存进去
        什么读出来什么"。未知订阅名 → `CrawlerError(CONFIG)`（与 `registry.get`
        对未知 venue_id 的处置同构），不返回 `{}` 假装首跑。

        **畸形 JSON 也归 CONFIG，且抛 `SubscriptionInvalid`**（P2#1 热修：异常类型
        统一，`error_class` 仍是 CONFIG，行为兼容——不让裸 `JSONDecodeError` 逃出
        错误分类学，也不再用泛型 `CrawlerError` 兜底；审计对 config TOML 同型缺口
        的 P1 教训）：损坏的游标若被当成"首跑"会静默重刷全窗。
        """
        rows = self.db.query("SELECT watermark_json FROM subscription WHERE name = ?", (name,))
        if not rows:
            raise _unknown_subscription(name)
        raw = rows[0]["watermark_json"]
        if raw is None or not str(raw).strip():
            return {}
        try:
            loaded = json.loads(str(raw))
        except json.JSONDecodeError as exc:
            raise SubscriptionInvalid(
                f"subscription {name!r} 的 watermark_json 解析失败: {exc}",
                detail=name,
            ) from None
        if not isinstance(loaded, dict):
            raise SubscriptionInvalid(
                f"subscription {name!r} 的 watermark_json 顶层不是对象",
                detail=type(loaded).__name__,
            )
        return {str(key): value for key, value in loaded.items()}

    def write_watermark(self, name: str, watermark: Mapping[str, object]) -> None:
        """覆盖写 `watermark_json`（T4 的推进出口）。未知订阅名 → `CrawlerError(CONFIG)`。

        整体覆盖而非合并：watermark 的"哪些源该留、该删"由 T4 按订阅当前 `sources`
        决定，仓储层做部分合并只会让退订的源留下幽灵游标。
        """
        with self.db.tx() as conn:
            cursor = conn.execute(
                "UPDATE subscription SET watermark_json = ? WHERE name = ?",
                # sort_keys=True：payload 是调用方 dict，键序不受本层控制（P1-1）。
                (_json_text(dict(watermark), sort_keys=True), name),
            )
            if cursor.rowcount == 0:
                raise _unknown_subscription(name)

    def touch_last_run(self, name: str, *, at: str | None = None) -> None:
        """推进 `last_run_at`（缺省取当前 UTC）。未知订阅名 → `CrawlerError(CONFIG)`。"""
        with self.db.tx() as conn:
            cursor = conn.execute(
                "UPDATE subscription SET last_run_at = ? WHERE name = ?",
                (at if at is not None else utcnow_iso(), name),
            )
            if cursor.rowcount == 0:
                raise _unknown_subscription(name)

    # -- subscription_run ----------------------------------------------------

    def record_run(
        self,
        *,
        name: str,
        started_at: str,
        new_count: int,
        fetched_count: int = 0,
        truncated: bool = False,
        report_path: str | None = None,
    ) -> str:
        """落一条运行记录，返回其 ULID。

        字段与 `subs.types.RunSummary` 一一对应（T5 直接从 summary 取值调用）。
        **熔断也要落记录**（`truncated=1` + 零入库，plan §4 T5 已裁决歧义②）——
        "跑过但被拦下"与"没跑"必须可区分。dry-run **不落**（T5 侧不调用本方法）。
        """
        if not self.exists(name):
            raise _unknown_subscription(name)
        run_id = new_ulid()
        self.db.execute(
            "INSERT INTO subscription_run "
            "(id, name, started_at, new_count, fetched_count, truncated, report_path) "
            "VALUES (?,?,?,?,?,?,?)",
            (run_id, name, started_at, new_count, fetched_count, int(truncated), report_path),
        )
        return run_id

    def runs(self, name: str | None = None, *, limit: int | None = None) -> list[sqlite3.Row]:
        """运行记录，按 `started_at` 降序（最近在前）；可限订阅、可限条数。"""
        sql = "SELECT * FROM subscription_run"
        params: list[object] = []
        if name is not None:
            sql += " WHERE name = ?"
            params.append(name)
        sql += " ORDER BY started_at DESC, id DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return self.db.query(sql, params)

    def last_run(self, name: str) -> sqlite3.Row | None:
        """某订阅最近一次运行记录；从未运行 → None。"""
        rows = self.runs(name, limit=1)
        return rows[0] if rows else None


def _json_text(payload: Mapping[str, object], *, sort_keys: bool) -> str:
    """订阅域 JSON 列的序列化（非 ASCII 原样）；`sort_keys` 按列语义显式选择
    （P1-1 热修——原先恒 `sort_keys=True` 会打乱 `sources` 的 YAML 声明序）。

    - `query_json`/`guard_json`：payload 来自 `to_query_dict()`/`Guard.to_dict()`，
      两者已按 DSL 字段序构造好确定序（含 `sources` 的**声明序**，编译计划步骤序
      的来源）——排序会把 `sources` 的键序打成字母序，破坏声明序往返（回归判据见
      `tests/integration/test_subscription_repo.py` 的 `asset-pricing-wp` 参数化，
      其声明序 ssrn→arxiv→nber 非字母序）。调用方须传 `sort_keys=False`。
    - `watermark_json`：payload 是调用方（T4）传入的 dict，键序不受本层控制，传
      `sort_keys=True` 换取确定性输出（可读 diff、可测试）。

    无默认值——强制每个调用点显式做出选择，不给"复制上一行却传错"留空子。
    """
    return json.dumps(dict(payload), ensure_ascii=False, sort_keys=sort_keys)


def _unknown_subscription(name: str) -> CrawlerError:
    """未知订阅名的统一错误（同 `registry.get` 对未知 venue_id 的 CONFIG 处置）。"""
    return CrawlerError(ErrorClass.CONFIG, f"unknown subscription: {name!r}")
