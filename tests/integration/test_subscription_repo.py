"""`SubscriptionRepo` 走真 sqlite（Phase 6 T1；design/06 §2 subscription/subscription_run）。

覆盖：DDL 与设计文档的列级核对、CRUD 往返、改订阅不清 watermark、watermark 读写、
`last_run_at` 推进、run 记录（含熔断标记）、未知订阅名的响亮报错、级联删除。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from paper_crawler.errors import CrawlerError, ErrorClass, SubscriptionInvalid
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import SubscriptionRepo
from paper_crawler.subs.model import Subscription, load_subscription_file, parse_subscription

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "subs"


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[SubscriptionRepo]:
    database = Database(tmp_path / "subs.sqlite")
    database.migrate()
    yield SubscriptionRepo(database)
    database.close()


def _example(stem: str = "llm-agents") -> Subscription:
    return load_subscription_file(_FIXTURES / f"{stem}.yaml")


# 各 fixture 的 `sources:` YAML 声明序（P1-1 回归判据）。`asset-pricing-wp` 的声明序
# ssrn→arxiv→nber **非字母序**（字母序应为 arxiv→nber→ssrn）——若 `query_json`
# 序列化误用 `sort_keys=True`，`sources` 的键序会被打乱成字母序，此处能抓住。
_DECLARED_SOURCE_ORDER: dict[str, tuple[str, ...]] = {
    # R2b/P0-4：llm-agents fixture 的第二个源（openalex）已随 `SOURCE_FIELDS` 收缩删除。
    # 该 fixture 因此只剩单源，抓不到"误用 sort_keys 打乱声明序"——判据全靠下面的
    # asset-pricing-wp（三源、非字母序），它本就是这条回归的主承载。
    "llm-agents": ("arxiv",),
    "asset-pricing-wp": ("ssrn", "arxiv", "nber"),
}


# --- DDL 核对（design/06 §2 ↔ 0001_init.sql）--------------------------------


@pytest.mark.parametrize(
    ("table", "columns", "not_null"),
    [
        (
            "subscription",
            {"name", "query_json", "watermark_json", "guard_json", "created_at", "last_run_at"},
            {"query_json"},
        ),
        (
            "subscription_run",
            {
                "id",
                "name",
                "started_at",
                "new_count",
                "fetched_count",
                "truncated",
                "report_path",
            },
            set(),
        ),
    ],
)
def test_tables_match_design_06_ddl(
    repo: SubscriptionRepo, table: str, columns: set[str], not_null: set[str]
) -> None:
    """列集合等值自断言：0001 已建表与 design/06 §2 DDL 逐列一致（T1 核对义务的载体）。

    同时核对 NOT NULL 约束（PRAGMA `table_info` 的 `notnull` 列，P2#5 热修）：
    `query_json` 是 DSL 主体，`upsert` 恒写非空值——约束若被建表脚本悄悄丢掉，
    上面的列名集合断言看不出来（列还在，只是少了约束），得单独核对。
    """
    rows = repo.db.query(f"PRAGMA table_info({table})")
    assert {str(row["name"]) for row in rows} == columns
    assert {str(row["name"]) for row in rows if row["notnull"]} == not_null


def test_subscription_name_is_primary_key(repo: SubscriptionRepo) -> None:
    rows = repo.db.query("PRAGMA table_info(subscription)")
    primary = [str(row["name"]) for row in rows if row["pk"]]
    assert primary == ["name"]


# --- CRUD 往返 --------------------------------------------------------------


@pytest.mark.parametrize("stem", ["llm-agents", "asset-pricing-wp"])
def test_upsert_then_get_round_trips_every_field(repo: SubscriptionRepo, stem: str) -> None:
    original = _example(stem)
    repo.upsert(original)
    restored = repo.get(original.name)
    assert restored == original  # dataclass 值语义 → 逐字段等值
    assert restored is not None
    # P1-1 回归判据：见 `_DECLARED_SOURCE_ORDER` 注释——声明序必须逐位存活往返。
    assert restored.source_names() == _DECLARED_SOURCE_ORDER[stem]


def test_get_unknown_returns_none(repo: SubscriptionRepo) -> None:
    assert repo.get("absent") is None
    assert repo.exists("absent") is False


def test_upsert_is_idempotent_and_updates_dsl(repo: SubscriptionRepo) -> None:
    repo.upsert(_example())
    narrowed = parse_subscription(
        {
            "name": "llm-agents",
            "sources": {"arxiv": {"categories": ["cs.AI"]}},
            "guard": {"max_new_per_run": 50},
        }
    )
    repo.upsert(narrowed)

    assert repo.list_names() == ["llm-agents"]  # 仍是一行
    stored = repo.get("llm-agents")
    assert stored is not None
    assert stored.source_names() == ("arxiv",)
    assert stored.guard.max_new_per_run == 50


def test_upsert_does_not_reset_watermark_or_created_at(repo: SubscriptionRepo) -> None:
    """改订阅内容绝不能顺手清零增量游标——否则下次 watch 会重刷整个历史窗。"""
    repo.upsert(_example())
    created_at = str(repo.db.query("SELECT created_at FROM subscription")[0]["created_at"])
    repo.write_watermark("llm-agents", {"schema_ver": 1, "arxiv": {"until": "2026-07-25"}})
    repo.touch_last_run("llm-agents", at="2026-07-25T00:00:00+00:00")

    repo.upsert(_example("llm-agents"))  # 再次注册同名订阅

    assert repo.read_watermark("llm-agents") == {
        "schema_ver": 1,
        "arxiv": {"until": "2026-07-25"},
    }
    row = repo.db.query("SELECT created_at, last_run_at FROM subscription")[0]
    assert str(row["created_at"]) == created_at
    assert str(row["last_run_at"]) == "2026-07-25T00:00:00+00:00"


def test_all_and_list_names_sort_by_name(repo: SubscriptionRepo) -> None:
    repo.upsert(_example("llm-agents"))
    repo.upsert(_example("asset-pricing-wp"))
    assert repo.list_names() == ["asset-pricing-wp", "llm-agents"]
    assert [s.name for s in repo.all()] == ["asset-pricing-wp", "llm-agents"]


def test_corrupt_stored_dsl_fails_loud(repo: SubscriptionRepo) -> None:
    """库行被手改坏 → 响亮报错，不返回半截对象。"""
    repo.upsert(_example())
    repo.db.execute(
        "UPDATE subscription SET query_json = ? WHERE name = ?",
        (
            json.dumps({"name": "llm-agents", "sources": {"biorxiv": {"categories": ["x"]}}}),
            "llm-agents",
        ),
    )
    with pytest.raises(SubscriptionInvalid, match="未知源"):
        repo.get("llm-agents")


# --- watermark --------------------------------------------------------------


def test_watermark_starts_empty_and_round_trips(repo: SubscriptionRepo) -> None:
    repo.upsert(_example())
    assert repo.read_watermark("llm-agents") == {}  # 首跑语义

    payload: dict[str, object] = {
        "schema_ver": 1,
        "arxiv": {"until": "2026-07-25", "overlap_days": 1},
        "ssrn": {"ids": ["4001", "4002"]},
    }
    repo.write_watermark("llm-agents", payload)
    assert repo.read_watermark("llm-agents") == payload


def test_watermark_write_overwrites_wholesale(repo: SubscriptionRepo) -> None:
    """整体覆盖而非合并——退订的源不留幽灵游标。"""
    repo.upsert(_example())
    repo.write_watermark("llm-agents", {"arxiv": {"until": "d1"}, "ssrn": {"ids": []}})
    repo.write_watermark("llm-agents", {"arxiv": {"until": "d2"}})
    assert repo.read_watermark("llm-agents") == {"arxiv": {"until": "d2"}}


@pytest.mark.parametrize(
    ("payload", "needle"),
    [("[1, 2]", "顶层不是对象"), ("{截断", "解析失败")],
)
def test_corrupt_watermark_fails_loud_as_config(
    repo: SubscriptionRepo, payload: str, needle: str
) -> None:
    """畸形游标一律 CONFIG 分类、抛 `SubscriptionInvalid`（P2#1 热修：异常类型统一），
    绝不降级成"首跑"（那会静默重刷整个历史窗）。"""
    repo.upsert(_example())
    repo.db.execute(
        "UPDATE subscription SET watermark_json = ? WHERE name = ?", (payload, "llm-agents")
    )
    with pytest.raises(SubscriptionInvalid) as excinfo:
        repo.read_watermark("llm-agents")
    assert isinstance(excinfo.value, CrawlerError)  # 归入既有 errors 层级
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert needle in str(excinfo.value)


@pytest.mark.parametrize("blank", ["", "   "])
def test_watermark_blank_text_reads_as_first_run(repo: SubscriptionRepo, blank: str) -> None:
    repo.upsert(_example())
    repo.db.execute(
        "UPDATE subscription SET watermark_json = ? WHERE name = ?", (blank, "llm-agents")
    )
    assert repo.read_watermark("llm-agents") == {}


def test_unknown_subscription_operations_fail_loud(repo: SubscriptionRepo) -> None:
    """未知订阅名一律 CONFIG 报错，不静默无操作（"改了却没生效"最难自证）。"""
    for call in (
        lambda: repo.read_watermark("absent"),
        lambda: repo.write_watermark("absent", {}),
        lambda: repo.touch_last_run("absent"),
        lambda: repo.record_run(name="absent", started_at="t", new_count=0),
    ):
        with pytest.raises(CrawlerError) as excinfo:
            call()
        assert excinfo.value.error_class is ErrorClass.CONFIG
        assert "absent" in str(excinfo.value)


def test_touch_last_run_defaults_to_now(repo: SubscriptionRepo) -> None:
    repo.upsert(_example())
    assert repo.db.query("SELECT last_run_at FROM subscription")[0]["last_run_at"] is None
    repo.touch_last_run("llm-agents")
    stamped = str(repo.db.query("SELECT last_run_at FROM subscription")[0]["last_run_at"])
    assert stamped.endswith("+00:00")  # UTC ISO8601（Global Constraints §7）


# --- subscription_run -------------------------------------------------------


def test_record_run_and_read_back(repo: SubscriptionRepo) -> None:
    repo.upsert(_example())
    run_id = repo.record_run(
        name="llm-agents",
        started_at="2026-07-26T01:00:00+00:00",
        new_count=17,
        fetched_count=5,
        report_path="docs/reports/watch/daily-2026-07-26.md",
    )
    assert len(run_id) == 26  # ULID

    row = repo.last_run("llm-agents")
    assert row is not None
    assert str(row["id"]) == run_id
    assert (int(row["new_count"]), int(row["fetched_count"])) == (17, 5)
    assert int(row["truncated"]) == 0
    assert str(row["report_path"]).endswith("daily-2026-07-26.md")


def test_truncated_run_is_recorded_with_zero_ingest(repo: SubscriptionRepo) -> None:
    """熔断也落记录（truncated=1）——"跑过但被拦下"与"没跑"必须可区分。"""
    repo.upsert(_example())
    repo.record_run(
        name="llm-agents", started_at="t", new_count=980, fetched_count=0, truncated=True
    )
    row = repo.last_run("llm-agents")
    assert row is not None and int(row["truncated"]) == 1


def test_runs_are_newest_first_and_limitable(repo: SubscriptionRepo) -> None:
    repo.upsert(_example())
    for stamp in ("2026-07-24T00:00:00+00:00", "2026-07-25T00:00:00+00:00"):
        repo.record_run(name="llm-agents", started_at=stamp, new_count=1)
    stamps = [str(row["started_at"]) for row in repo.runs("llm-agents")]
    assert stamps == ["2026-07-25T00:00:00+00:00", "2026-07-24T00:00:00+00:00"]
    assert len(repo.runs("llm-agents", limit=1)) == 1


def test_runs_across_subscriptions(repo: SubscriptionRepo) -> None:
    repo.upsert(_example("llm-agents"))
    repo.upsert(_example("asset-pricing-wp"))
    repo.record_run(name="llm-agents", started_at="t1", new_count=1)
    repo.record_run(name="asset-pricing-wp", started_at="t2", new_count=2)
    assert len(repo.runs()) == 2
    assert len(repo.runs("llm-agents")) == 1
    assert repo.last_run("asset-pricing-wp") is not None


def test_last_run_none_before_any_run(repo: SubscriptionRepo) -> None:
    repo.upsert(_example())
    assert repo.last_run("llm-agents") is None


def test_delete_removes_runs_then_subscription(repo: SubscriptionRepo) -> None:
    """外键 ON：先删子行再删父行；返回值区分"删到了"与"本来就没有"。"""
    repo.upsert(_example())
    repo.record_run(name="llm-agents", started_at="t", new_count=1)

    assert repo.delete("llm-agents") is True
    assert repo.get("llm-agents") is None
    assert repo.runs() == []
    assert repo.delete("llm-agents") is False
