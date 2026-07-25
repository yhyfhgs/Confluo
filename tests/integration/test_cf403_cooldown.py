"""CF-403 判定演进（S-c）+ 挑战冷却键粒度（E-1）集成（D-030 裁决②③；11-browser-fetch §8）。

真 sqlite + 真冷却 JSON + `httpx.MockTransport`，零真实网络。覆盖：

- **T-6 集成面**：403 + `cf-mitigated: challenge` 经共享 `HttpClient` → `Challenged`
  → pipeline BLOCKED **且冷却 JSON 落盘**（单测面见 `tests/unit/test_http.py` T-6 段）；
- **T-7（修复判据载体）**：**open_access family** venue 命中 CHALLENGE → 写冷却 →
  **再次 drain 仍被 BLOCKED**。E-1 修复前冷却判定在 family 判别之后，open_access
  "写而不读"，第二次 drain 会照常取回成功 → **本测在修复前必失败**；
- **向前兼容**：预置上一版本格式的 `<adapter_id>.json` 冷却文件 → 新代码仍读得到；
- **键粒度**：写入用**域**键（asset URL host），无 asset 时退化 adapter 主域 → adapter_id；
  不同域互不连坐（aea `www.` / `pubs.` 双域异质的可测同构）。

环境构建器复用 `test_pipeline_e2e.make_env`（mock_platform = `family: open_access`，
恰是 E-1 缺口的受害面；`tests/` 无顶层包，按 helpers 先例以 `integration.` 顶层包名导入）。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from integration.test_pipeline_e2e import DEFAULT_QUIRKS, VENUE, PipelineEnv, make_env
from paper_crawler.errors import Challenged, CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.pipeline import Selector
from paper_crawler.pipeline.report import RunReport
from paper_crawler.types import utcnow_iso

_ADAPTER_KEY = "mock_platform"  # 旧格式冷却键（<adapter_id>.json）
_DOMAIN_KEY = "mock.local"  # 新格式冷却键（asset URL host）


@pytest.fixture
def env(tmp_path: Path) -> Iterator[PipelineEnv]:
    e = make_env(tmp_path)
    yield e
    e.close()


def _quirks_with(**extra: object) -> dict[str, object]:
    quirks = dict(DEFAULT_QUIRKS)
    quirks.update(extra)
    return quirks


def _challenge_on(indexes: list[int]) -> dict[str, object]:
    """mock_platform 故障注入：给定期内序号的 fetch 抛 `CrawlerError(CHALLENGE)`。"""
    return _quirks_with(fail_fetch={"error_class": "challenge", "paper_indexes": indexes})


def _cooldown_file(env: PipelineEnv, key: str) -> Path:
    return env.config.home / "state" / "cooldown" / f"{key}.json"


def _cooldown_files(env: PipelineEnv) -> list[str]:
    directory = env.config.home / "state" / "cooldown"
    return sorted(p.name for p in directory.glob("*.json")) if directory.is_dir() else []


def _seed_cooldown(env: PipelineEnv, key: str, *, hours: float = 12.0) -> None:
    """预置一份"上一次运行留下的"冷却文件（跨运行持久化语义）。"""
    path = _cooldown_file(env, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    until = (datetime.now(UTC) + timedelta(hours=hours)).isoformat()
    path.write_text(json.dumps({"until": until}), encoding="utf-8")


def _fetch_states(env: PipelineEnv) -> list[str]:
    rows = env.db.query("SELECT state FROM task WHERE kind = 'fetch' ORDER BY created_at, id")
    return [str(r["state"]) for r in rows]


def _one_asset_row(env: PipelineEnv) -> sqlite3.Row:
    return env.db.query("SELECT * FROM asset ORDER BY id LIMIT 1")[0]


# ---------------------------------------------------------------------------
# T-7：open_access family 冷却"写而不读"修复（E-1；**修复前必失败**）
# ---------------------------------------------------------------------------


def test_t7_open_access_challenge_cooldown_blocks_second_drain(env: PipelineEnv) -> None:
    """T-7：open_access venue 命中 CHALLENGE → 写冷却 → **第二次 drain 仍 BLOCKED**。

    第二次运行**用全新 runner**（新进程语义：运行态字典为空，只能从冷却 JSON 读回）
    且**故障注入已解除**——若冷却未被读到，5 篇会全部取回成功；断言"零成功、全 BLOCKED"
    即证明冷却在 open_access family 上真正生效（修复前此断言必失败）。
    """
    env.write_venue(_challenge_on([0]))
    first = env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))

    # 首次：注入者命中挑战 BLOCKED，其余 4 篇经冷却门连带 BLOCKED（AC-4.6"停止该平台全部队列"）
    assert first.blocked == 5 and first.succeeded == 0 and first.failed == 0
    assert _cooldown_file(env, _DOMAIN_KEY).is_file()

    # 人工 resume（冷却未满）+ 解除故障注入 → 新 runner 再次 drain
    env.write_venue(dict(DEFAULT_QUIRKS))
    assert env.queue.resume(all_blocked=True) == 5
    second = env.make_runner().drain()

    assert second.succeeded == 0  # 冷却期内一篇都不许取回
    assert second.blocked == 5
    assert _fetch_states(env) == ["BLOCKED"] * 5
    reasons = env.db.query(
        "SELECT blocked_reason FROM task WHERE kind = 'fetch' AND state = 'BLOCKED'"
    )
    assert all("挑战冷却期" in str(r["blocked_reason"]) for r in reasons)
    assert env.repo.counts(VENUE)["assets_fetched"] == 0


def test_t7_cooldown_expiry_releases_the_queue(env: PipelineEnv) -> None:
    """冷却过期后自然放行（不是永久拉黑）：预置一份**已过期**的冷却 → 正常取回。"""
    _seed_cooldown(env, _DOMAIN_KEY, hours=-1.0)
    report = env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))

    assert report.succeeded == 5 and report.blocked == 0


def test_t7_cooldown_is_not_written_for_other_block_classes(env: PipelineEnv) -> None:
    """只有 CHALLENGE 写冷却：CONFIG 等其余 BLOCKED 类不写，同批其余照常成功（无连坐）。"""
    env.write_venue(_quirks_with(fail_fetch={"error_class": "config", "paper_indexes": [0]}))
    report = env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))

    assert report.blocked == 1 and report.succeeded == 4
    assert _cooldown_files(env) == []


# ---------------------------------------------------------------------------
# 向前兼容：旧 `<adapter_id>.json` 键仍被读到（E-1 无迁移脚本的前提）
# ---------------------------------------------------------------------------


def test_legacy_adapter_id_cooldown_key_is_still_honoured(env: PipelineEnv) -> None:
    """预置上一版本落盘的 `<adapter_id>.json` → 新代码读时两键都查 → 仍 BLOCKED。"""
    _seed_cooldown(env, _ADAPTER_KEY)
    report = env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))

    assert report.succeeded == 0 and report.blocked == 5
    reasons = env.db.query(
        "SELECT blocked_reason FROM task WHERE kind = 'fetch' AND state = 'BLOCKED'"
    )
    assert all(_ADAPTER_KEY in str(r["blocked_reason"]) for r in reasons)


def test_unrelated_domain_cooldown_does_not_block(env: PipelineEnv) -> None:
    """他域的冷却不连坐（aea `pubs.` 判罚不该停 `www.` 的同构最小证）。"""
    _seed_cooldown(env, "pubs.other.local")
    report = env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))

    assert report.succeeded == 5 and report.blocked == 0


# ---------------------------------------------------------------------------
# 键粒度契约：域键在前、旧 adapter 键在后；写只用首键
# ---------------------------------------------------------------------------


def test_cooldown_key_order_domain_first_then_legacy(env: PipelineEnv) -> None:
    """`_cooldown_keys` 顺序契约：asset URL host → adapter 主域 → adapter_id（去重）。"""
    env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))
    runner = env.make_runner()
    asset = _one_asset_row(env)

    # 同域：host == domains[0] → 去重后只剩两键
    assert runner._cooldown_keys(VENUE, asset) == (_DOMAIN_KEY, _ADAPTER_KEY)
    # 无 asset（resolve 阶段抛挑战 / asset 行缺失）→ 退化到 adapter 主域
    assert runner._cooldown_keys(VENUE, None) == (_DOMAIN_KEY, _ADAPTER_KEY)
    # 异质子域（aea `pubs.aeaweb.org` 同构）：该 asset 的键集**不含**主域被判罚时的其他域
    env.db.execute(
        "UPDATE asset SET url = 'https://pubs.mock.local/pdf/x' WHERE id = ?", (asset["id"],)
    )
    assert runner._cooldown_keys(VENUE, _one_asset_row(env)) == (
        "pubs.mock.local",
        _DOMAIN_KEY,
        _ADAPTER_KEY,
    )


def test_challenge_writes_domain_key_not_adapter_key(env: PipelineEnv) -> None:
    """写入侧用**域**键：落盘文件名是 `<domain>.json`，不再是 `<adapter_id>.json`。"""
    env.write_venue(_challenge_on([0]))
    env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))

    assert _cooldown_files(env) == [f"{_DOMAIN_KEY}.json"]
    payload = json.loads(_cooldown_file(env, _DOMAIN_KEY).read_text(encoding="utf-8"))
    assert datetime.fromisoformat(str(payload["until"])) > datetime.now(UTC) + timedelta(hours=23)


def test_unknown_venue_yields_no_cooldown_keys(env: PipelineEnv) -> None:
    """未知/畸形 venue（registry 路由失败）且无 asset → 无键可写，静默不落盘（不崩）。"""
    runner = env.make_runner()
    assert runner._cooldown_keys("no_such_venue", None) == ()
    runner._enter_challenge_cooldown("no_such_venue", None)
    assert _cooldown_files(env) == []


def test_gate_passes_through_when_task_has_no_venue(env: PipelineEnv) -> None:
    """防御路径：fetch 任务无 venue → 无从判平台/冷却，直接放行（交 stage 自身路由）。

    冷却键推导恒需 venue（registry 路由入口），故该早返回必须在冷却判定**之前**。
    """
    env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))
    row = env.db.query("SELECT * FROM task WHERE kind = 'fetch' ORDER BY id LIMIT 1")[0]
    report = RunReport(command="drain", venue_id=None, started_at=utcnow_iso())

    assert env.make_runner()._auth_gate_fetch(row, None, report) is True
    assert report.blocked == 0


# ---------------------------------------------------------------------------
# T-6 集成面：真 CF-403 响应 → Challenged → BLOCKED + 冷却落盘（端到端接线）
# ---------------------------------------------------------------------------


def test_t6_cf403_through_http_client_reaches_cooldown(env: PipelineEnv) -> None:
    """403+`cf-mitigated: challenge` 经共享 `HttpClient` 抛 `Challenged`，其
    `error_class` 走 runner 既有 `_BLOCK_CLASSES` 路径 → BLOCKED + 域冷却落盘。

    S-c 与 E-1 的接线证据：`http.py` 端改判产出的异常，无需任何新增处置逻辑即被
    pipeline 冷却链路消费（11-browser-fetch §5.5-2"零新增处置逻辑"）。
    """
    client = HttpClient(
        user_agent="PaperCrawler/test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(403, headers={"cf-mitigated": "challenge"}, text="wait")
        ),
    )
    with pytest.raises(Challenged) as exc_info:
        client.get_bytes("https://mock.local/pdf/10.9999/x")
    assert exc_info.value.error_class is ErrorClass.CHALLENGE

    # 同一 error_class 注入 mock 故障通道 → 走完 runner 的 CHALLENGE 处置
    env.write_venue(_challenge_on([0]))
    report = env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))

    assert report.blocked == 5 and report.succeeded == 0
    assert _cooldown_file(env, _DOMAIN_KEY).is_file()


def test_plain_403_still_no_entitlement_end_to_end(env: PipelineEnv) -> None:
    """回归锁定：无 CF 头的 403 仍是 NO_ENTITLEMENT——**不写冷却、不 BLOCKED**、
    走 §8.5 独立终态（`report.no_entitlement` 单列计数，不计 failed）。"""
    client = HttpClient(
        user_agent="PaperCrawler/test",
        transport=httpx.MockTransport(lambda request: httpx.Response(403, text="forbidden")),
    )
    with pytest.raises(CrawlerError) as exc_info:
        client.get_bytes("https://api.wiley.com/tdm/v1/articles/x")
    assert exc_info.value.error_class is ErrorClass.NO_ENTITLEMENT

    env.write_venue(
        _quirks_with(fail_fetch={"error_class": "no_entitlement", "paper_indexes": [0]})
    )
    report = env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))

    assert report.no_entitlement == 1
    assert report.blocked == 0 and report.failed == 0 and report.succeeded == 4
    assert _cooldown_files(env) == []
