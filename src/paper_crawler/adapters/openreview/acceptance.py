"""逐届 accepted 判定规则（design/adapters/openreview.md §4④/§8；缺陷 C-D 修复）。

**问题**（[LIVE] 2026-07-22 实测，research/site-survey/openreview.md §11）：OpenReview 的
「接收论文」判定惯例**逐届异构**，默认的 ``content.venueid == 主会 id`` 只对 venueid 规约
成立的届（2017、2020-2026）有效。早届接收态另有出处：

- **2013/2014**：submission 帖自带 ``content.decision``（'accept…' 等），无独立决定帖。
- **2018**：submission（`Blind_Submission`）帖**无 venueid**；接收态在 venue 级决定帖
  ``ICLR.cc/2018/Conference/-/Acceptance_Decision`` 的 ``content.decision``（'Accept (Oral)'/
  'Accept (Poster)'/'Reject'/'Invite to Workshop Track'）。venueid 过滤枚举 **0 篇**（缺陷 C-D）。
- **2019**：submission 帖无 venueid；接收态在 per-paper 决定帖 ``…/Paper<N>/Meta_Review`` 的
  ``content.recommendation``（'Accept (…)'）。venueid 过滤同样枚举 **0 篇**。

**方案**：把「一届怎么枚举 accepted」抽象为 `AcceptanceRule`（策略对象），用**内置逐届规则表**
（`_ICLR_RULES`，与 `venues._ICLR_TABLE` 同一「内置常量表」模式）数据驱动选取——**禁止散落
if-else**。默认 `VENUEID`（保持既有行为、零回归）；2018/2019 走决定帖 join。2013/2014 仍走
默认（venueid→0）：其正文在 arXiv、跨源发现归 Phase 3（design §4 resolve），submission
`content.decision` 惯例已实证记档，待 Phase 3 补 `SubmissionDecisionRule`。

每个 `AcceptanceRule` 自带**分页**（offset 翻页至 `count`）与**日志**，与 adapter 解耦——adapter
只组 `EnumContext`（fetch/base/venueid/version/…）并委派。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

from paper_crawler.adapters.openreview import parse
from paper_crawler.obslog import log_event
from paper_crawler.types import PaperStub, VenueSpec

DEFAULT_PAGE_LIMIT = 1000  # 勘察 §5：limit≤1000，offset 翻页至 count


@dataclass(frozen=True)
class EnumContext:
    """一届 enumerate 的运行上下文（adapter 组装、规则消费）。"""

    fetch: Callable[[str], bytes]
    base: str
    venueid: str
    version: parse.ApiVersion
    year: int | None
    venue_id: str
    issue_label: str | None  # IssueRef.label（日志用；正常态由 discover 填 'YYYY'）
    domain: str
    page_limit: int = DEFAULT_PAGE_LIMIT


class AcceptanceRule(Protocol):
    """「一届怎么枚举 accepted」的策略协议。实现自带分页与日志。"""

    def iter_accepted(self, ctx: EnumContext) -> Iterator[PaperStub]:
        """yield 该届全部**接收**论文的 `PaperStub`。"""
        ...


# --- 分页与日志小工具 -------------------------------------------------------------------------


def _notes_url(
    base: str, params: dict[str, str], offset: int, limit: int, *, details: str | None = None
) -> str:
    """构造 `/notes` 翻页 URL（禁携 email 参数——robots `/*?*email=` 唯一禁则 + 隐私红线）。"""
    query = {**params, "limit": str(limit), "offset": str(offset)}
    if details is not None:
        query["details"] = details
    return f"{base}/notes?{urlencode(query)}"


def _iter_raw_pages(
    ctx: EnumContext, params: dict[str, str], *, details: str | None = None
) -> Iterator[list[object]]:
    """offset 翻页 `/notes?<params>` 至累计覆盖 `count`，逐页 yield 原始 note 条目列表。

    终止：累计已覆盖 `count`，或本页空（防御 count 与实际不符的死循环——既有行为一致）。
    """
    offset = 0
    while True:
        url = _notes_url(ctx.base, params, offset, ctx.page_limit, details=details)
        raw, count = parse.raw_notes_envelope(ctx.fetch(url))
        yield raw
        offset += len(raw)
        if offset >= count or not raw:
            break


def _log_summary(ctx: EnumContext, emitted: int, excluded: int, how: str) -> None:
    log_event(
        "INFO",
        f"enumerate {ctx.issue_label}: {emitted} accepted ({excluded} excluded; {how})",
        venue=ctx.venue_id,
        stage="enumerate",
        domain=ctx.domain,
    )


# --- 规则实现 ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class VenueidRule:
    """默认规则：`/notes?content.venueid=<gid>` 翻页，`venueid == gid` 即接收（§4④）。

    venueid 规约成立的届（2017、2020-2026；以及 2013/2014——其 venueid 缺席故枚举 0，符合
    design 的 arXiv 跨源 Phase 3 口径）。**与 C-D 修复前行为逐字一致**（零回归）。
    """

    def iter_accepted(self, ctx: EnumContext) -> Iterator[PaperStub]:
        emitted = excluded = 0
        for raw in _iter_raw_pages(ctx, {"content.venueid": ctx.venueid}):
            for note in parse.notes_from_raw(raw, ctx.version):
                if parse.is_accepted(note, ctx.venueid):
                    yield parse.to_paper_stub(note, year=ctx.year)
                    emitted += 1
                else:
                    excluded += 1
        _log_summary(ctx, emitted, excluded, "venueid filter")


@dataclass(frozen=True)
class DecisionInvitationRule:
    """venue 级决定帖 join（2018 形态）：决定帖 `content.<field>` 判接收 forum，再取 submission。

    两阶段：① 翻页 `<gid>/-/<decision_suffix>` 收集接收 forum 集合（`content.<decision_field>`
    以 `accept_prefixes` 开头）；② 翻页 `<gid>/-/<submission_suffix>`，forum ∈ 接收集的 submission
    产出 `PaperStub`（title/pdf 由 submission 帖映射）。
    """

    decision_suffix: str
    submission_suffix: str
    decision_field: str
    accept_prefixes: tuple[str, ...]

    def iter_accepted(self, ctx: EnumContext) -> Iterator[PaperStub]:
        decision_inv = f"{ctx.venueid}/-/{self.decision_suffix}"
        submission_inv = f"{ctx.venueid}/-/{self.submission_suffix}"
        accepted_forums: set[str] = set()
        for raw in _iter_raw_pages(ctx, {"invitation": decision_inv}):
            accepted_forums |= parse.accepted_forums(
                raw, ctx.version, field=self.decision_field, accept_prefixes=self.accept_prefixes
            )
        emitted = excluded = 0
        for raw in _iter_raw_pages(ctx, {"invitation": submission_inv}):
            for note in parse.notes_from_raw(raw, ctx.version):
                if note.forum in accepted_forums:
                    yield parse.to_paper_stub(note, year=ctx.year)
                    emitted += 1
                else:
                    excluded += 1
        _log_summary(ctx, emitted, excluded, f"decision-join {self.decision_suffix}")


@dataclass(frozen=True)
class DirectRepliesRule:
    """per-paper 决定帖 join（2019 形态）：submission + `details=directReplies` 一遍枚举 accepted。

    翻页 `<gid>/-/<submission_suffix>&details=directReplies`；submission 的 directReplies 里若有
    `invitation` 含 `reply_invitation_contains`（如 'Meta_Review'）且 `content.<field>`（如
    'recommendation'）以 `accept_prefixes` 开头，即接收。
    """

    submission_suffix: str
    reply_invitation_contains: str
    decision_field: str
    accept_prefixes: tuple[str, ...]

    def iter_accepted(self, ctx: EnumContext) -> Iterator[PaperStub]:
        submission_inv = f"{ctx.venueid}/-/{self.submission_suffix}"
        emitted = excluded = 0
        for raw in _iter_raw_pages(ctx, {"invitation": submission_inv}, details="directReplies"):
            accepted = parse.accepted_notes_by_replies(
                raw,
                ctx.version,
                reply_invitation_contains=self.reply_invitation_contains,
                field=self.decision_field,
                accept_prefixes=self.accept_prefixes,
            )
            for note in accepted:
                yield parse.to_paper_stub(note, year=ctx.year)
            emitted += len(accepted)
            excluded += len(raw) - len(accepted)
        _log_summary(ctx, emitted, excluded, f"directReplies {self.reply_invitation_contains}")


# --- 逐届规则表（内置常量，勘察 §11 [LIVE] 逐届实测；design §4④/§8）--------------------------
#
# 只登记「venueid 惯例外」的届；未登记的届走 `_DEFAULT_RULE`（venueid）。命名规约漂移 / 新届
# 出入随年度 canary 追加此表（与 `venues._ICLR_TABLE` 同一维护模式）。

_DEFAULT_RULE: AcceptanceRule = VenueidRule()

_ICLR_RULES: dict[int, AcceptanceRule] = {
    2018: DecisionInvitationRule(
        decision_suffix="Acceptance_Decision",  # venue 级决定帖
        submission_suffix="Blind_Submission",
        decision_field="decision",
        accept_prefixes=(
            "Accept",
        ),  # 'Accept (Oral)'/'Accept (Poster)'；排除 'Invite to…'/'Reject'
    ),
    2019: DirectRepliesRule(
        submission_suffix="Blind_Submission",
        reply_invitation_contains="Meta_Review",  # per-paper 决定帖
        decision_field="recommendation",
        accept_prefixes=("Accept",),
    ),
}

_BUILTIN_RULES: dict[str, dict[int, AcceptanceRule]] = {"iclr": _ICLR_RULES}


def rule_for(venue: VenueSpec, year: int | None) -> AcceptanceRule:
    """选取该 (venue, year) 的 accepted 判定规则（内置表命中→专属，否则→默认 venueid）。"""
    if year is None:
        return _DEFAULT_RULE
    return _BUILTIN_RULES.get(venue.id, {}).get(year, _DEFAULT_RULE)


__all__ = [
    "AcceptanceRule",
    "DecisionInvitationRule",
    "DirectRepliesRule",
    "EnumContext",
    "VenueidRule",
    "rule_for",
]
