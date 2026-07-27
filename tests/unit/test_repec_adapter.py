"""`adapters/repec/adapter.py` 单测：零网络锁定、快照加载/失效语义、未命中三分、healthcheck。

**本文件的核心资产是 `test_enrich_batch_makes_no_network_call_at_all`**——D-035 决策 3 把
repec 的"零网络"定为**结构事实**（唯一网络面在 `scripts/repec_snapshot.py`，src 之外），
本测试用比 `tests/conftest.py` 全局 socket 护栏**更强**的猴补（连 `socket.socket` 构造本身
都炸）机械证明该事实，而不是靠 adapter 自述。
"""

from __future__ import annotations

import hashlib
import json
import socket
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from paper_crawler.adapters.repec import parse
from paper_crawler.adapters.repec.adapter import RepecAdapter
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.types import Capability, RatePolicy

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "repec"
_REDIF_NAME = "nbr/nberwo/nberwo.rdf"


def _write_snapshot(
    root: Path,
    *,
    fetched_at: str | None = None,
    fixture: str = "01_nberwo_multi.rdf",
    files: list[dict[str, object]] | None = None,
    payload: bytes | None = None,
    record_count: int | None = None,
) -> Path:
    """在 `root` 下写一份最小可用快照（manifest + 一份 ReDIF 文件）。

    `sha256`/`bytes`/`record_count` **按实际内容算**——加载器会校验三者（P2-⑦），写假值等于
    在测试里模拟一份损坏快照。要专门测损坏，用 `files=`/`record_count=` 显式给出错值。
    """
    data = payload if payload is not None else (_FIXTURES / fixture).read_bytes()
    payload_path = root / _REDIF_NAME
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_bytes(data)
    manifest = {
        "schema": 1,
        "archive": "nbr",
        "series": ["nberwo"],
        "mirror": "www2.nber.org",
        "source_urls": ["https://www2.nber.org/RePEc/nbr/nberwo/"],
        "fetched_at": fetched_at or datetime.now(UTC).isoformat(),
        "files": files
        if files is not None
        else [
            {
                "name": _REDIF_NAME,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        ],
        "record_count": record_count if record_count is not None else len(parse.parse_redif(data)),
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


# --- 元数据面（D-035 决策 1 的结构性宣告）------------------------------------------------------


def test_adapter_declares_zero_network_metadata() -> None:
    adapter = RepecAdapter()
    assert adapter.adapter_id == "repec"
    assert adapter.family == "aggregator"
    assert adapter.capabilities == Capability(0)  # 空集：不进 pull 六阶段
    assert adapter.domains == ()  # 结构性宣告"本源无网络面"


def test_nominal_rate_policy_is_honest_about_being_a_placeholder() -> None:
    """`source_note` 如实注明占位名义，**不编造假出处**（D-035 明文，同否决占位域名）。"""
    rate: RatePolicy = RepecAdapter.default_rate
    assert rate.requests_per_minute > 0  # test_adapter_loading 的既有硬要求
    assert "零网络源" in rate.source_note
    assert "占位名义" in rate.source_note


def test_adapter_does_not_implement_http_client_consumer() -> None:
    """装配缝拿不到 client——"零网络"的第二道结构保证（第一道是 domains=()）。"""
    from paper_crawler.adapter import HttpClientConsumer

    assert not isinstance(RepecAdapter(), HttpClientConsumer)


# --- 零网络机械锁定（本文件核心资产）-----------------------------------------------------------


def test_enrich_batch_makes_no_network_call_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """socket 猴补：连 `socket.socket` **构造**都炸——`enrich_batch` 全程零网络才可能通过。

    比 `tests/conftest.py` 的全局 `socket.connect` 护栏更强：那道护栏允许创建 socket 只禁
    连接，本测试连创建都禁，故任何 HTTP 客户端的惰性自建也会当场爆炸。
    """
    root = _write_snapshot(tmp_path / "state" / "repec")

    def _explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("repec enrich_batch 触网了——零网络契约被破坏（D-035 决策 3/4）")

    monkeypatch.setattr(socket, "socket", _explode)
    monkeypatch.setattr(socket, "create_connection", _explode)
    monkeypatch.setattr(socket, "getaddrinfo", _explode)

    adapter = RepecAdapter()
    adapter.configure_snapshot(root)
    stubs = adapter.enrich_batch(["10.3386/w35506", "10.3386/w3210"])
    assert len(stubs) == 2


def test_healthcheck_makes_no_network_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """healthcheck 同样零网络零预算 ⇒ canary 高频调用无成本（与 openalex 的 credit 顾虑相反）。"""
    root = _write_snapshot(tmp_path / "state" / "repec")

    def _explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("repec healthcheck 触网了")

    monkeypatch.setattr(socket, "socket", _explode)
    adapter = RepecAdapter(root)
    assert adapter.healthcheck().healthy is True


# --- enrich_batch 本地 join 与未命中三分（D-035 决策 4）----------------------------------------


def test_enrich_batch_joins_snapshot_and_produces_both_identifiers(tmp_path: Path) -> None:
    adapter = RepecAdapter(_write_snapshot(tmp_path))
    (stub,) = adapter.enrich_batch(["10.3386/w35506"])
    assert stub.identifiers == (("doi", "10.3386/w35506"), ("repec", "RePEc:nbr:nberwo:35506"))
    assert json.loads(dict(stub.meta)["jel"]) == ["D1", "J13", "J15"]


def test_enrich_batch_counts_three_miss_kinds_separately(tmp_path: Path) -> None:
    """三分计数各自可见——混作一个数字会让"该刷快照了"与"本来就没 JEL"无法区分。"""
    adapter = RepecAdapter(_write_snapshot(tmp_path))
    stubs = adapter.enrich_batch(
        [
            "10.3386/w35506",  # 命中，有 JEL
            "10.3386/w3210",  # 命中，无 JEL（历史条目）
            "10.3386/w99999",  # (b) 前缀符但快照无该 handle → 覆盖缺口
            "10.2139/ssrn.1234567",  # (a) 非 10.3386 → 结构性不可寻址
            "10.1257/aer.20210001",  # (a) 同上
        ]
    )
    assert len(stubs) == 2
    stats = adapter.stats
    assert stats.matched == 2
    assert stats.no_jel == 1
    assert stats.missing_handle == 1
    assert stats.unaddressable == 2


def test_t_series_doi_is_unaddressable_and_never_joins_the_w_record(tmp_path: Path) -> None:
    """P1-R2：`t{n}` 不再借 `w{n}` 的 handle 取到记录——不产 stub，计入"不可寻址"。

    修复前 `series_id[1:]` 去首字母，`10.3386/t35506` 会 join 到 `RePEc:nbr:nberwo:35506`
    （= w35506 的记录）并产出一个**冠着 t 的 DOI、装着 w 的书目**的 stub。
    """
    adapter = RepecAdapter(_write_snapshot(tmp_path))
    stubs = adapter.enrich_batch(["10.3386/w35506", "10.3386/t35506"])
    assert [dict(s.identifiers)["doi"] for s in stubs] == ["10.3386/w35506"]
    assert adapter.stats.matched == 1
    assert adapter.stats.unaddressable == 1
    assert adapter.stats.missing_handle == 0  # t 不是"快照没这条"，是结构性不可寻址


def test_debug_miss_event_breaks_unaddressable_down_by_series_letter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`unaddressable` 内"合法 NBER 旁系"与"根本不是 NBER"在 DEBUG 上可辨（按字母分桶）。

    摘要行契约（三分计数）不变——细分只进 DEBUG 事件，不入 `SnapshotStats`。
    """
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.repec.adapter.log_event",
        lambda level, msg, **kw: events.append({"level": level, "msg": msg, **kw}),
    )
    adapter = RepecAdapter(_write_snapshot(tmp_path))
    adapter.enrich_batch(
        [
            "10.3386/t9001",  # 合法 NBER 旁系（t）——刻意不覆盖
            "10.3386/t9002",  # 同上，同字母累加
            "10.2139/ssrn.1234567",  # 根本不是 NBER
        ]
    )
    (event,) = [e for e in events if e["msg"] == "repec enrich_batch misses"]
    assert event["level"] == "DEBUG"
    assert event["unaddressable"] == 3
    assert event["uncovered_nber_series"] == {"t": 2}  # ssrn 那条不在细分里


def test_debug_miss_event_omits_series_breakdown_when_all_misses_are_non_nber(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """无旁系未命中时**不塞恒空字典**——空细分键会让 jsonl 每行都背一个无信息量的 `{}`。"""
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.repec.adapter.log_event",
        lambda level, msg, **kw: events.append({"level": level, "msg": msg, **kw}),
    )
    adapter = RepecAdapter(_write_snapshot(tmp_path))
    adapter.enrich_batch(["10.2139/ssrn.1234567"])
    (event,) = [e for e in events if e["msg"] == "repec enrich_batch misses"]
    assert event["uncovered_nber_series"] is None


def test_enrich_batch_still_emits_stub_when_jel_is_empty(tmp_path: Path) -> None:
    """(c) 增值为空**仍产 stub**：title/authors/year/abstract 照常回注，靠优先级最低位只补空。"""
    adapter = RepecAdapter(_write_snapshot(tmp_path))
    (stub,) = adapter.enrich_batch(["10.3386/w3210"])
    assert stub.title == "Endogenous Technological Change"
    assert "jel" not in dict(stub.meta)
    assert dict(stub.meta)["published_in"] == "Published in Oxford Economic Papers"


def test_enrich_batch_dedupes_and_skips_blanks(tmp_path: Path) -> None:
    adapter = RepecAdapter(_write_snapshot(tmp_path))
    stubs = adapter.enrich_batch(["10.3386/w35506", "10.3386/w35506", "", "  "])
    assert len(stubs) == 1
    assert adapter.stats.matched == 1


def test_enrich_batch_is_a_pure_function_of_dois_and_snapshot(tmp_path: Path) -> None:
    """对固定快照可重放（幂等性面与在线源相反）——同输入两次调用产出逐字段相等。"""
    adapter = RepecAdapter(_write_snapshot(tmp_path))
    first = adapter.enrich_batch(["10.3386/w35506", "10.3386/w3210"])
    second = adapter.enrich_batch(["10.3386/w35506", "10.3386/w3210"])
    assert first == second


def test_stats_accumulate_across_pages(tmp_path: Path) -> None:
    """外层分页（`_ENRICH_PAGE_SIZE`）逐页调用，计数须跨页累计，否则摘要行只报最后一页。"""
    adapter = RepecAdapter(_write_snapshot(tmp_path))
    adapter.enrich_batch(["10.3386/w35506"])
    adapter.enrich_batch(["10.3386/w3210", "10.2139/ssrn.1"])
    assert adapter.stats.matched == 2
    assert adapter.stats.unaddressable == 1


# --- 失效语义：缺失（响亮 CONFIG）/ 过期（响亮 WARNING + 继续）--------------------------------


def test_missing_snapshot_raises_config_with_actionable_hint(tmp_path: Path) -> None:
    """缺失 → CONFIG（经 `_run_enrich_source` 记"提前终止"，不崩其它 source）+ 刷新命令指引。"""
    adapter = RepecAdapter(tmp_path / "nonexistent")
    with pytest.raises(CrawlerError) as excinfo:
        adapter.enrich_batch(["10.3386/w35506"])
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert "快照缺失" in str(excinfo.value)
    assert "scripts/repec_snapshot.py" in str(excinfo.value)


def test_unconfigured_snapshot_root_raises_config_not_indexerror() -> None:
    adapter = RepecAdapter()
    with pytest.raises(CrawlerError) as excinfo:
        adapter.enrich_batch(["10.3386/w35506"])
    assert excinfo.value.error_class is ErrorClass.CONFIG


def test_manifest_referencing_missing_file_raises_config(tmp_path: Path) -> None:
    """快照**损坏**（manifest 记载的文件不在）响亮失败，不静默产出半份结果。"""
    root = _write_snapshot(
        tmp_path, files=[{"name": "nbr/nberwo/gone.rdf", "bytes": 1, "sha256": "cd" * 32}]
    )
    adapter = RepecAdapter(root)
    with pytest.raises(CrawlerError) as excinfo:
        adapter.enrich_batch(["10.3386/w35506"])
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert "快照损坏" in str(excinfo.value)


# --- P2-⑦ 完整性校验：sha256 / bytes / record_count 只写不校等于没校 --------------------------


def test_sha256_mismatch_raises_integrity(tmp_path: Path) -> None:
    """**等长**改动（字节数校验抓不到）由 sha256 抓——两道校验各有各的盲区，故都要有。"""
    root = _write_snapshot(tmp_path)
    original = (root / _REDIF_NAME).read_bytes()
    tampered = original.replace(b"Endogenous", b"ENDOGENOUS", 1)
    assert len(tampered) == len(original) and tampered != original
    (root / _REDIF_NAME).write_bytes(tampered)
    adapter = RepecAdapter(root)
    with pytest.raises(CrawlerError) as excinfo:
        adapter.enrich_batch(["10.3386/w35506"])
    assert excinfo.value.error_class is ErrorClass.INTEGRITY
    assert "sha256 不符" in str(excinfo.value)
    assert "scripts/repec_snapshot.py" in str(excinfo.value)


def test_byte_length_mismatch_raises_integrity(tmp_path: Path) -> None:
    """截断的快照必须响亮——半份数据静默入库比缺失更危险。"""
    data = (_FIXTURES / "01_nberwo_multi.rdf").read_bytes()
    root = _write_snapshot(tmp_path)
    (root / _REDIF_NAME).write_bytes(data[: len(data) // 2])
    with pytest.raises(CrawlerError) as excinfo:
        RepecAdapter(root).enrich_batch(["10.3386/w35506"])
    assert excinfo.value.error_class is ErrorClass.INTEGRITY
    assert "字节" in str(excinfo.value)


def test_record_count_mismatch_raises_integrity(tmp_path: Path) -> None:
    """字节没变而记录数变 ⇒ 本地解析口径已漂移；静默通过会让 join 覆盖率悄悄塌掉。"""
    root = _write_snapshot(tmp_path, record_count=999)
    with pytest.raises(CrawlerError) as excinfo:
        RepecAdapter(root).enrich_batch(["10.3386/w35506"])
    assert excinfo.value.error_class is ErrorClass.INTEGRITY
    assert "999" in str(excinfo.value)


_DUPLICATE_HANDLE_SNAPSHOT = (
    b"Template-Type: ReDIF-Paper 1.0\n"
    b"Title: First Copy\n"
    b"Classification-JEL: D1\n"
    b"Handle: RePEc:nbr:nberwo:35506\n"
    b"\n"
    b"Template-Type: ReDIF-Paper 1.0\n"
    b"Title: Duplicate Copy Of The Same Handle\n"
    b"Handle: RePEc:nbr:nberwo:35506\n"
    b"\n"
    b"Template-Type: ReDIF-Paper 1.0\n"
    b"Title: Another Paper\n"
    b"Handle: RePEc:nbr:nberwo:3210\n"
)


def test_duplicate_handles_do_not_trip_integrity(tmp_path: Path) -> None:
    """**回归锁**：含重复 handle 的**合法**快照曾被 `record_count` 校验判成损坏。

    根因＝两侧口径不一致：加载器按 handle 去重（`setdefault`，"同 handle 取首条"是明写的
    预期行为），而 `write_manifest` 记的是未去重条数。后果比"误报"更糟——**重取快照永远
    修不好**，因为重取会写回同一个未去重计数，每次都撞同一堵墙。现两侧统一取唯一 handle 数。
    """
    # record_count 按**唯一 handle** 计（3 个记录块、2 个唯一 handle），模拟 write_manifest 的口径
    root = _write_snapshot(tmp_path, payload=_DUPLICATE_HANDLE_SNAPSHOT, record_count=2)
    adapter = RepecAdapter(root)
    stubs = adapter.enrich_batch(["10.3386/w35506", "10.3386/w3210"])
    assert len(stubs) == 2
    # "同 handle 取首条"——后续重复块不挤掉首条
    assert stubs[0].title == "First Copy"
    assert adapter.stats.missing_handle == 0


def test_write_manifest_and_loader_agree_on_record_count(tmp_path: Path) -> None:
    """脚本侧写 manifest 与 adapter 侧校验必须口径同源（含重复 handle 时才看得出差别）。"""
    import importlib.util

    root = tmp_path / "state" / "repec"
    (root / _REDIF_NAME).parent.mkdir(parents=True, exist_ok=True)
    (root / _REDIF_NAME).write_bytes(_DUPLICATE_HANDLE_SNAPSHOT)

    spec = importlib.util.spec_from_file_location(
        "repec_snapshot_for_count",
        Path(__file__).resolve().parents[2] / "scripts" / "repec_snapshot.py",
    )
    assert spec is not None and spec.loader is not None
    script = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = script
    spec.loader.exec_module(script)

    entry = parse.SnapshotFile(
        name=_REDIF_NAME,
        bytes=len(_DUPLICATE_HANDLE_SNAPSHOT),
        sha256=hashlib.sha256(_DUPLICATE_HANDLE_SNAPSHOT).hexdigest(),
    )
    script.write_manifest(root, mirror="www2.nber.org", urls=["https://x/y.rdf"], files=[entry])
    written = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert written["record_count"] == 2  # 唯一 handle 数，非 3 个记录块

    # 脚本产出的 manifest 必须被加载器接受——这才是"口径同源"的实证
    assert RepecAdapter(root).healthcheck().healthy is True


def test_integrity_failure_surfaces_as_unhealthy_in_canary(tmp_path: Path) -> None:
    root = _write_snapshot(tmp_path, record_count=999)
    report = RepecAdapter(root).healthcheck()
    assert report.healthy is False


# --- P1-1：解析伪影作 PARSE 类观测，与三分计数分离 --------------------------------------------


def test_parse_artifacts_counted_separately_from_three_way_misses(tmp_path: Path) -> None:
    """页脚散文既不该污染 handle，也不该被记成"覆盖缺口"——两套计数各归各位。"""
    payload = (
        b"Template-Type: ReDIF-Paper 1.0\n"
        b"Title: Real Paper\n"
        b"Handle: RePEc:nbr:nberwo:35506\n"
        b"\n"
        b"-- end of archive listing --\n"
        b"Template-Type: ReDIF-Paper 1.0\n"
        b"Title: Bad Handle\n"
        b"Handle: garbage\n"
    )
    adapter = RepecAdapter(_write_snapshot(tmp_path, payload=payload))
    stubs = adapter.enrich_batch(["10.3386/w35506"])
    assert len(stubs) == 1  # handle 未被污染 ⇒ 正常命中
    stats = adapter.stats
    assert stats.matched == 1
    assert stats.missing_handle == 0  # 关键：伪影没有伪装成覆盖缺口
    assert stats.malformed_records == 1
    assert stats.stray_lines == 1


def test_parse_artifacts_emit_parse_class_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.repec.adapter.log_event",
        lambda level, msg, **kw: events.append((level, kw)),
    )
    payload = b"Template-Type: ReDIF-Paper 1.0\nTitle: Bad\nHandle: garbage\n"
    RepecAdapter(_write_snapshot(tmp_path, payload=payload, record_count=0)).enrich_batch([])
    warnings = [kw for level, kw in events if level == "WARNING"]
    assert warnings and warnings[0]["error_class"] == "parse"
    assert warnings[0]["malformed_records"] == 1


def test_summary_note_lists_parse_artifacts_outside_the_three_counts(tmp_path: Path) -> None:
    payload = b"Template-Type: ReDIF-Paper 1.0\nTitle: Bad\nHandle: garbage\n"
    adapter = RepecAdapter(_write_snapshot(tmp_path, payload=payload, record_count=0))
    adapter.enrich_batch([])
    note = adapter.summary_note()
    assert "解析伪影 handle 不合 1" in note
    assert "不计入上列三分" in note


def test_clean_snapshot_reports_no_parse_artifacts(tmp_path: Path) -> None:
    adapter = RepecAdapter(_write_snapshot(tmp_path))
    adapter.enrich_batch(["10.3386/w35506"])
    assert "解析伪影" not in adapter.summary_note()
    assert adapter.stats.malformed_records == 0


def test_stale_snapshot_warns_loudly_but_keeps_running(tmp_path: Path) -> None:
    """过期 → **警告 + 继续**（对 enrich-eval §2.7 DoD② 字面的有意收窄，D-035 决策 3 已入档）。"""
    stale_at = (datetime.now(UTC) - timedelta(days=47)).isoformat()
    adapter = RepecAdapter(_write_snapshot(tmp_path, fetched_at=stale_at))
    stubs = adapter.enrich_batch(["10.3386/w35506"])
    assert len(stubs) == 1  # 关键：过期不阻断


def test_stale_warning_is_actionable(tmp_path: Path) -> None:
    """警告必带 ①天数 ②`fetched_at` ③刷新命令——只喊"过期了"等于把响亮做成噪声。"""
    stale_at = (datetime.now(UTC) - timedelta(days=47)).isoformat()
    adapter = RepecAdapter(_write_snapshot(tmp_path, fetched_at=stale_at))
    adapter.enrich_batch(["10.3386/w35506"])
    note = adapter.summary_note()
    assert "47 天未刷新" in note
    assert stale_at in note
    assert "scripts/repec_snapshot.py" in note
    assert "阈值 30 天" in note


def test_fresh_snapshot_has_no_stale_warning(tmp_path: Path) -> None:
    adapter = RepecAdapter(_write_snapshot(tmp_path))
    adapter.enrich_batch(["10.3386/w35506"])
    assert "未刷新" not in adapter.summary_note()


def test_stale_threshold_boundary_is_inclusive_at_30_days(tmp_path: Path) -> None:
    """恰 30 天**不**告警（阈值语义＝"早于 30 天"才算过期），31 天告警。"""
    at_threshold = (datetime.now(UTC) - timedelta(days=30, hours=1)).isoformat()
    over_threshold = (datetime.now(UTC) - timedelta(days=31, hours=1)).isoformat()
    fresh = RepecAdapter(_write_snapshot(tmp_path / "a", fetched_at=at_threshold))
    fresh.enrich_batch([])
    assert "未刷新" not in fresh.summary_note()
    stale = RepecAdapter(_write_snapshot(tmp_path / "b", fetched_at=over_threshold))
    stale.enrich_batch([])
    assert "31 天未刷新" in stale.summary_note()


def test_stale_warning_emitted_once_per_load_not_per_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """加载时判一次——每页刷一遍会把一条运维提示变成噪声。"""
    events: list[str] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.repec.adapter.log_event",
        lambda level, msg, **kw: events.append(f"{level}:{msg}"),
    )
    stale_at = (datetime.now(UTC) - timedelta(days=47)).isoformat()
    adapter = RepecAdapter(_write_snapshot(tmp_path, fetched_at=stale_at))
    adapter.enrich_batch(["10.3386/w35506"])
    adapter.enrich_batch(["10.3386/w3210"])
    assert sum(1 for e in events if e.startswith("WARNING")) == 1


def test_summary_note_carries_freshness_and_three_way_counts(tmp_path: Path) -> None:
    """`fetched_at` **须在摘要行可见**——不说等于让用户对着可能半年前的数据做判断。"""
    adapter = RepecAdapter(_write_snapshot(tmp_path, fetched_at="2026-07-27T00:00:00+00:00"))
    adapter.enrich_batch(["10.3386/w35506", "10.3386/w99999", "10.2139/ssrn.1"])
    note = adapter.summary_note()
    assert "fetched_at=2026-07-27T00:00:00+00:00" in note
    assert "命中 1" in note
    assert "不可寻址 1" in note
    assert "覆盖缺口 1" in note


# --- healthcheck（快照缺失 → SKIP；在 → 健康带记录数/新鲜度）----------------------------------


def test_healthcheck_without_snapshot_raises_not_implemented_for_canary_skip() -> None:
    """无快照 → `NotImplementedError` → canary 既有 SKIP 分支（**零 canary 改动**）。"""
    with pytest.raises(NotImplementedError):
        RepecAdapter().healthcheck()


def test_healthcheck_with_snapshot_reports_record_count_and_fetched_at(tmp_path: Path) -> None:
    root = _write_snapshot(tmp_path, fetched_at="2026-07-27T00:00:00+00:00")
    report = RepecAdapter(root).healthcheck()
    assert report.healthy is True
    assert "record_count=3" in report.detail
    assert "fetched_at=2026-07-27T00:00:00+00:00" in report.detail


def test_healthcheck_surfaces_stale_warning_in_detail(tmp_path: Path) -> None:
    """过期快照在 canary 侧也须可见——运维跑 canary 时应当看到"该刷快照了"，而非只报健康。"""
    stale_at = (datetime.now(UTC) - timedelta(days=47)).isoformat()
    report = RepecAdapter(_write_snapshot(tmp_path, fetched_at=stale_at)).healthcheck()
    assert report.healthy is True  # 过期不等于不健康
    assert "47 天未刷新" in report.detail


def test_healthcheck_with_corrupt_snapshot_is_unhealthy_not_skip(tmp_path: Path) -> None:
    """损坏≠未配置：前者是真实故障，如实报不健康，不混进 SKIP。"""
    root = tmp_path / "state" / "repec"
    root.mkdir(parents=True)
    (root / "manifest.json").write_text("{not json", encoding="utf-8")
    report = RepecAdapter(root).healthcheck()
    assert report.healthy is False
    assert "快照损坏" in report.detail


def test_configure_snapshot_invalidates_cache(tmp_path: Path) -> None:
    """改根即弃缓存——不会读到上一份快照的残留。"""
    adapter = RepecAdapter(_write_snapshot(tmp_path / "first"))
    assert len(adapter.enrich_batch(["10.3386/w35506"])) == 1
    adapter.configure_snapshot(_write_snapshot(tmp_path / "second", fixture="02_malformed.rdf"))
    assert adapter.enrich_batch(["10.3386/w35506"]) == []
    assert len(adapter.enrich_batch(["10.3386/w8888"])) == 1
