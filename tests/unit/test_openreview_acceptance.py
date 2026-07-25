"""逐届 accepted 规则单测（design/adapters/openreview.md §4④/§8；缺陷 C-D 修复）。

覆盖：parse 的决定帖/directReplies 判定纯函数（`accepted_forums` /
`accepted_notes_by_replies`）、三种 `AcceptanceRule` 策略（venueid / 决定帖 join /
directReplies）、`rule_for` 选取表、以及经 adapter + `httpx.MockTransport` 的 2018/2019
端到端 enumerate（版本判定 groups → 决定帖 join）。零真实网络（fixture bytes / MockTransport）。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from helpers import make_openreview_venue
from helpers.openreview_fixtures import fixture_bytes
from paper_crawler.adapters.openreview import acceptance, parse
from paper_crawler.adapters.openreview.adapter import OpenReviewAdapter
from paper_crawler.adapters.openreview.parse import ApiVersion
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.types import IssueRef

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"


def _bytes(obj: object) -> bytes:
    return json.dumps(obj).encode("utf-8")


def _forums(stubs: list[object]) -> list[str]:
    return sorted(
        f
        for s in stubs
        for scheme, f in s.identifiers
        if scheme == "openreview"  # type: ignore[attr-defined]
    )


# --- parse.accepted_forums（venue 级决定帖 → 接收 forum 集合）-------------------------------


def test_accepted_forums_v1_direct_accept_prefix() -> None:
    raw, _ = parse.raw_notes_envelope(fixture_bytes("12_v1_2018_decisions.json"))
    forums = parse.accepted_forums(
        raw, ApiVersion.V1, field="decision", accept_prefixes=("Accept",)
    )
    # 'Accept (Oral)' / 'Accept (Poster)' 接收；'Reject' / 'Invite to Workshop Track' 排除。
    assert forums == {"sub_oral", "sub_poster"}


def test_accepted_forums_v2_unwraps_value() -> None:
    raw = [
        {"id": "d1", "forum": "f1", "content": {"decision": {"value": "Accept (Poster)"}}},
        {"id": "d2", "forum": "f2", "content": {"decision": {"value": "Reject"}}},
    ]
    forums = parse.accepted_forums(
        raw, ApiVersion.V2, field="decision", accept_prefixes=("Accept",)
    )
    assert forums == {"f1"}


def test_accepted_forums_missing_forum_is_skipped() -> None:
    raw = [{"id": "d1", "content": {"decision": "Accept (Oral)"}}]  # 无 forum
    assert (
        parse.accepted_forums(raw, ApiVersion.V1, field="decision", accept_prefixes=("Accept",))
        == set()
    )


def test_accepted_forums_non_dict_entry_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.accepted_forums(["x"], ApiVersion.V1, field="decision", accept_prefixes=("Accept",))
    assert exc.value.error_class is ErrorClass.PARSE


def test_accepted_forums_missing_content_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.accepted_forums(
            [{"id": "d", "forum": "f"}],
            ApiVersion.V1,
            field="decision",
            accept_prefixes=("Accept",),
        )
    assert exc.value.error_class is ErrorClass.PARSE


def test_accepted_forums_version_mismatch_raises_parse() -> None:
    # v2 期望 {"value": ...}，拿到裸值 → 版本错配 PARSE（§6 canary）。
    raw = [{"id": "d", "forum": "f", "content": {"decision": "Accept (Oral)"}}]
    with pytest.raises(CrawlerError) as exc:
        parse.accepted_forums(raw, ApiVersion.V2, field="decision", accept_prefixes=("Accept",))
    assert exc.value.error_class is ErrorClass.PARSE


# --- parse.accepted_notes_by_replies（per-paper 决定帖 → 接收 Note）-------------------------


def test_accepted_notes_by_replies_picks_meta_review_accept() -> None:
    raw, _ = parse.raw_notes_envelope(fixture_bytes("14_v1_2019_submissions_directreplies.json"))
    notes = parse.accepted_notes_by_replies(
        raw,
        ApiVersion.V1,
        reply_invitation_contains="Meta_Review",
        field="recommendation",
        accept_prefixes=("Accept",),
    )
    assert [n.forum for n in notes] == ["m_accept"]  # reject / no-reply 排除
    assert notes[0].pdf is not None  # 提交帖本体映射（pdf 供 resolve）


def test_accepted_notes_by_replies_ignores_non_matching_invitation() -> None:
    # 只有 Official_Review（含 rating），无 Meta_Review → 非接收。
    raw = [
        {
            "id": "s",
            "forum": "s",
            "content": {"title": "t"},
            "details": {
                "directReplies": [
                    {
                        "id": "r",
                        "invitation": "x/-/Paper1/Official_Review",
                        "content": {"rating": "Accept-ish"},
                    }
                ]
            },
        }
    ]
    notes = parse.accepted_notes_by_replies(
        raw,
        ApiVersion.V1,
        reply_invitation_contains="Meta_Review",
        field="recommendation",
        accept_prefixes=("Accept",),
    )
    assert notes == []


def test_accepted_notes_by_replies_no_replies_is_not_accepted() -> None:
    raw = [{"id": "s", "forum": "s", "content": {"title": "t"}}]  # 无 details
    notes = parse.accepted_notes_by_replies(
        raw,
        ApiVersion.V1,
        reply_invitation_contains="Meta_Review",
        field="recommendation",
        accept_prefixes=("Accept",),
    )
    assert notes == []


def test_accepted_notes_by_replies_skips_malformed_replies() -> None:
    # 防御：directReplies 里的非 dict 帖 / content 非 dict 帖被跳过（不崩、不误判接收）。
    raw = [
        {
            "id": "s",
            "forum": "s",
            "content": {"title": "t"},
            "details": {
                "directReplies": [
                    "not-a-dict",
                    {"id": "r1", "invitation": "x/-/Paper1/Meta_Review", "content": "not-a-dict"},
                ]
            },
        }
    ]
    notes = parse.accepted_notes_by_replies(
        raw,
        ApiVersion.V1,
        reply_invitation_contains="Meta_Review",
        field="recommendation",
        accept_prefixes=("Accept",),
    )
    assert notes == []


def test_accepted_notes_by_replies_malformed_submission_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.accepted_notes_by_replies(
            [{"forum": "s", "content": {"title": "t"}}],  # 缺 id
            ApiVersion.V1,
            reply_invitation_contains="Meta_Review",
            field="recommendation",
            accept_prefixes=("Accept",),
        )
    assert exc.value.error_class is ErrorClass.PARSE


# --- rule_for 选取表 -------------------------------------------------------------------------


def test_rule_for_2018_is_decision_invitation_rule() -> None:
    rule = acceptance.rule_for(make_openreview_venue(), 2018)
    assert isinstance(rule, acceptance.DecisionInvitationRule)
    assert rule.decision_suffix == "Acceptance_Decision"
    assert rule.decision_field == "decision"


def test_rule_for_2019_is_direct_replies_rule() -> None:
    rule = acceptance.rule_for(make_openreview_venue(), 2019)
    assert isinstance(rule, acceptance.DirectRepliesRule)
    assert rule.reply_invitation_contains == "Meta_Review"
    assert rule.decision_field == "recommendation"


@pytest.mark.parametrize("year", [2013, 2014, 2017, 2020, 2024, 2026, None])
def test_rule_for_default_is_venueid_rule(year: int | None) -> None:
    # venueid 惯例外只登记 2018/2019；其余（含 2013/2014 的 arXiv 跨源 Phase-3 口径）走默认。
    assert isinstance(acceptance.rule_for(make_openreview_venue(), year), acceptance.VenueidRule)


def test_rule_for_unknown_venue_is_default() -> None:
    from paper_crawler.types import VenueSpec

    other = VenueSpec(
        id="neurips",
        kind="conference",
        names={"full": "NeurIPS"},
        field=["cs_ai"],
        metadata_source="openreview",
        fulltext_source="openreview",
    )
    # 未登记内置规则表的 venue —— 即便 year=2018 也走默认 venueid（规则表按 venue.id 键取）。
    assert isinstance(acceptance.rule_for(other, 2018), acceptance.VenueidRule)


# --- 规则策略（fake fetch 驱动 iter_accepted）-----------------------------------------------


def _fetch_map(mapping: dict[str, bytes]) -> Callable[[str], bytes]:
    def fetch(url: str) -> bytes:
        for key, data in mapping.items():
            if key in url:
                return data
        raise AssertionError(f"unexpected url in test fetch: {url}")

    return fetch


def _ctx(fetch: Callable[[str], bytes], *, venueid: str, year: int) -> acceptance.EnumContext:
    return acceptance.EnumContext(
        fetch=fetch,
        base="https://api.openreview.net",
        venueid=venueid,
        version=ApiVersion.V1,
        year=year,
        venue_id="iclr",
        issue_label=f"{year}",
        domain="api2.openreview.net",
    )


def test_decision_invitation_rule_joins_decisions_and_submissions() -> None:
    fetch = _fetch_map(
        {
            "Acceptance_Decision": fixture_bytes("12_v1_2018_decisions.json"),
            "Blind_Submission": fixture_bytes("13_v1_2018_submissions.json"),
        }
    )
    rule = acceptance.rule_for(make_openreview_venue(), 2018)
    stubs = list(rule.iter_accepted(_ctx(fetch, venueid="ICLR.cc/2018/Conference", year=2018)))
    assert _forums(stubs) == ["sub_oral", "sub_poster"]  # 缺陷 C-D：由 0 修为 2
    assert all(dict(s.meta).get(parse.META_PDF_PATH) for s in stubs)  # pdf 相对路径随 stub
    assert all(s.year == 2018 for s in stubs)


def test_direct_replies_rule_selects_accept_meta_reviews() -> None:
    fetch = _fetch_map(
        {"Blind_Submission": fixture_bytes("14_v1_2019_submissions_directreplies.json")}
    )
    rule = acceptance.rule_for(make_openreview_venue(), 2019)
    stubs = list(rule.iter_accepted(_ctx(fetch, venueid="ICLR.cc/2019/Conference", year=2019)))
    assert _forums(stubs) == ["m_accept"]  # 缺陷 C-D：由 0 修为 1
    assert dict(stubs[0].meta).get(parse.META_PDF_PATH)


# --- 多页翻页专测（F4 清账，S1 审计"2018/2019 规则多页翻页无专属测试"）-----------------------
#
# 上面两条端到端用例的 fixture 均为「count == 单页条数」的单页响应——`_iter_raw_pages` 的
# offset 翻页循环从未在 2018/2019 规则下被真正跑过两轮。这里用 count 大于单页条数的
# 构造响应，逐 offset 分派不同页体，钉死跨页聚合（决定帖 `accepted_forums` 的 `|=` 累积、
# 提交帖 join 覆盖全部页）确实正确，而不仅仅是"资源恰好一页装得下"的偶然巧合。


def _offset_of(url: str) -> int:
    return int(parse_qs(urlsplit(url).query).get("offset", ["0"])[0])


def test_decision_invitation_rule_aggregates_accepted_forums_across_multiple_pages() -> None:
    """2018 规则：决定帖查询与提交帖查询**各自**跨两页，聚合/join 结果与单页时逐字一致。"""
    decision_pages = {
        0: _bytes(
            {
                "notes": [
                    {"id": "d1", "forum": "sub_a", "content": {"decision": "Accept (Oral)"}},
                    {"id": "d2", "forum": "sub_b", "content": {"decision": "Reject"}},
                ],
                "count": 4,
            }
        ),
        2: _bytes(
            {
                "notes": [
                    {"id": "d3", "forum": "sub_c", "content": {"decision": "Accept (Poster)"}},
                    {"id": "d4", "forum": "sub_d", "content": {"decision": "Reject"}},
                ],
                "count": 4,
            }
        ),
    }
    submission_pages = {
        0: _bytes(
            {
                "notes": [
                    {"id": "sub_a", "forum": "sub_a", "content": {"title": "A"}},
                    {"id": "sub_b", "forum": "sub_b", "content": {"title": "B"}},
                ],
                "count": 4,
            }
        ),
        2: _bytes(
            {
                "notes": [
                    {"id": "sub_c", "forum": "sub_c", "content": {"title": "C"}},
                    {"id": "sub_d", "forum": "sub_d", "content": {"title": "D"}},
                ],
                "count": 4,
            }
        ),
    }

    def fetch(url: str) -> bytes:
        offset = _offset_of(url)
        if "Acceptance_Decision" in url:
            return decision_pages[offset]
        if "Blind_Submission" in url:
            return submission_pages[offset]
        raise AssertionError(f"unexpected url in test fetch: {url}")

    rule = acceptance.rule_for(make_openreview_venue(), 2018)
    stubs = list(rule.iter_accepted(_ctx(fetch, venueid="ICLR.cc/2018/Conference", year=2018)))
    # sub_a（页1接收）+ sub_c（页2接收）跨两页聚合命中；sub_b/sub_d（各自页内 Reject）排除。
    assert _forums(stubs) == ["sub_a", "sub_c"]


def test_direct_replies_rule_aggregates_accepted_across_multiple_submission_pages() -> None:
    """2019 规则：单一 submission+directReplies 查询跨两页，接收判定逐页独立生效。"""

    def _submission(forum: str, *, recommendation: str | None) -> dict[str, object]:
        replies: list[dict[str, object]] = []
        if recommendation is not None:
            replies.append(
                {
                    "id": f"r-{forum}",
                    "invitation": f"x/-/Paper/{forum}/Meta_Review",
                    "content": {"recommendation": recommendation},
                }
            )
        return {
            "id": forum,
            "forum": forum,
            "content": {"title": forum},
            "details": {"directReplies": replies},
        }

    pages = {
        0: _bytes(
            {
                "notes": [
                    _submission("s1", recommendation="Accept (Poster)"),
                    _submission("s2", recommendation="Reject"),
                ],
                "count": 4,
            }
        ),
        2: _bytes(
            {
                "notes": [
                    _submission("s3", recommendation="Accept (Oral)"),
                    _submission("s4", recommendation=None),  # 无 Meta_Review 回帖 → 非接收
                ],
                "count": 4,
            }
        ),
    }

    def fetch(url: str) -> bytes:
        return pages[_offset_of(url)]

    rule = acceptance.rule_for(make_openreview_venue(), 2019)
    stubs = list(rule.iter_accepted(_ctx(fetch, venueid="ICLR.cc/2019/Conference", year=2019)))
    # s1（页1接收）+ s3（页2接收）跨两页聚合命中；s2/s4 排除。
    assert _forums(stubs) == ["s1", "s3"]


def test_venueid_rule_matches_default_behavior() -> None:
    venueid = "ICLR.cc/2024/Conference"
    page = {
        "notes": [
            {
                "id": "a",
                "forum": "a",
                "content": {"title": {"value": "A"}, "venueid": {"value": venueid}},
            },
            {
                "id": "b",
                "forum": "b",
                "content": {"title": {"value": "B"}, "venueid": {"value": venueid + "/Submission"}},
            },
        ],
        "count": 2,
    }
    ctx = acceptance.EnumContext(
        fetch=lambda _url: _bytes(page),
        base="https://api2.openreview.net",
        venueid=venueid,
        version=ApiVersion.V2,
        year=2024,
        venue_id="iclr",
        issue_label="2024",
        domain="api2.openreview.net",
    )
    stubs = list(acceptance.VenueidRule().iter_accepted(ctx))
    assert _forums(stubs) == ["a"]  # 仅 venueid==gid 接收


# --- 经 adapter + MockTransport 的 2018/2019 端到端 enumerate（groups 判版本 → 决定帖 join）---


def _adapter(handler: Callable[[httpx.Request], httpx.Response]) -> OpenReviewAdapter:
    return OpenReviewAdapter(
        http=HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    )


def _v1_group(vid: str) -> httpx.Response:
    return httpx.Response(200, content=_bytes({"groups": [{"id": vid, "members": []}], "count": 1}))


def test_adapter_enumerate_2018_decision_join_end_to_end() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/groups" in request.url.path:
            return _v1_group("ICLR.cc/2018/Conference")  # 无 domain → v1
        assert request.url.host == "api.openreview.net"  # 决定帖/提交帖走 v1 端点
        inv = request.url.params.get("invitation", "")
        name = (
            "12_v1_2018_decisions.json"
            if "Acceptance_Decision" in inv
            else "13_v1_2018_submissions.json"
        )
        return httpx.Response(200, content=fixture_bytes(name))

    issue = IssueRef(venue_id="iclr", year=2018, label="2018")
    stubs = list(_adapter(handler).enumerate_issue(make_openreview_venue(), issue))
    assert _forums(stubs) == ["sub_oral", "sub_poster"]


def test_adapter_enumerate_2019_direct_replies_end_to_end() -> None:
    seen_details: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "/groups" in request.url.path:
            return _v1_group("ICLR.cc/2019/Conference")
        seen_details.append(request.url.params.get("details", ""))
        return httpx.Response(
            200, content=fixture_bytes("14_v1_2019_submissions_directreplies.json")
        )

    issue = IssueRef(venue_id="iclr", year=2019, label="2019")
    stubs = list(_adapter(handler).enumerate_issue(make_openreview_venue(), issue))
    assert _forums(stubs) == ["m_accept"]
    assert seen_details == ["directReplies"]  # 提交帖查询携 details=directReplies


def test_builtin_rules_keys_subset_of_venue_tables() -> None:
    """规则表↔届表护栏（F2 审查 L2）：规则只能挂在届表已知年份上。

    防拼写错年份的规则静默失联；反向（惯例外届漏配规则→默认 0）无法程序断言，
    由 anchor 表与年度 canary 兜底（acceptance.py 表旁注释）。
    """
    from paper_crawler.adapters.openreview.acceptance import _BUILTIN_RULES
    from paper_crawler.adapters.openreview.venues import _BUILTIN_TABLES

    for venue, rules in _BUILTIN_RULES.items():
        assert venue in _BUILTIN_TABLES, f"规则挂在未知 venue: {venue}"
        unknown = set(rules) - set(_BUILTIN_TABLES[venue])
        assert not unknown, f"{venue} 规则年份不在届表: {sorted(unknown)}"
