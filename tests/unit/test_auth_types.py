"""`types.SessionHandle` 具体化 + 枚举单测（auth-framework §2.1 冻结签名；T1a）。

锁定面：字段名/序/默认值逐字对齐 §2.1；frozen + hashable（types.py 模块约定）；
枚举值精确；repr/str 无凭证形态（§2.1 值语义：handle 是指针，`payload_ref` 为
条目名非密文——安全断言）。
"""

import dataclasses
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from paper_crawler.types import HealthStatus, SessionBackend, SessionHandle

ESTABLISHED = datetime(2026, 7, 23, 12, 0, 0, tzinfo=UTC)


def _handle(**overrides: object) -> SessionHandle:
    kwargs: dict[str, object] = {
        "provider_id": "oup@campus",
        "backend": SessionBackend.HTTPX_COOKIES,
        "payload_ref": "oup_campus_state",
        "established_at": ESTABLISHED,
    }
    kwargs.update(overrides)
    return SessionHandle(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 枚举（§2.1 逐字）
# ---------------------------------------------------------------------------


def test_health_status_members_exact() -> None:
    assert {member.value for member in HealthStatus} == {"ok", "expired", "challenged"}
    assert len(list(HealthStatus)) == 3
    # StrEnum：成员即字符串值（provider 判定结果可直接入日志/报告文本）。
    assert HealthStatus.OK == "ok"
    assert f"{HealthStatus.CHALLENGED}" == "challenged"


def test_session_backend_members_exact() -> None:
    assert {member.value for member in SessionBackend} == {
        "httpx_cookies",
        "playwright_state",
        "bearer_token",
    }
    assert len(list(SessionBackend)) == 3
    assert SessionBackend.PLAYWRIGHT_STATE == "playwright_state"


# ---------------------------------------------------------------------------
# SessionHandle dataclass（§2.1 逐字：字段名/序/类型缺省）
# ---------------------------------------------------------------------------


def test_session_handle_field_order_and_defaults_frozen_signature() -> None:
    fields = dataclasses.fields(SessionHandle)
    assert [f.name for f in fields] == [
        "provider_id",
        "backend",
        "payload_ref",
        "established_at",
        "est_ttl",
    ]
    # 唯一有默认值的字段：est_ttl=None（其余必填）。
    assert fields[-1].default is None
    assert all(f.default is dataclasses.MISSING for f in fields[:-1])


def test_session_handle_is_frozen() -> None:
    handle = _handle()
    with pytest.raises(dataclasses.FrozenInstanceError):
        handle.payload_ref = "other"  # type: ignore[misc]


def test_session_handle_hashable_and_value_equal() -> None:
    left = _handle(est_ttl=timedelta(hours=24))
    right = _handle(est_ttl=timedelta(hours=24))
    assert left == right
    assert hash(left) == hash(right)
    assert {left, right} == {left}  # 可入 set/dict（types.py frozen 约定）


def test_session_handle_est_ttl_defaults_to_none() -> None:
    assert _handle().est_ttl is None


# ---------------------------------------------------------------------------
# 安全断言（任务卡）：repr/str 不含凭证形态——handle 只携 payload_ref 条目名
# ---------------------------------------------------------------------------


def test_session_handle_repr_carries_ref_name_not_credential_shapes() -> None:
    handle = _handle(
        provider_id="elsevier",
        backend=SessionBackend.BEARER_TOKEN,
        payload_ref="elsevier_apikey",
        est_ttl=timedelta(hours=12),
    )
    for rendered in (repr(handle), str(handle)):
        lowered = rendered.lower()
        assert "secret" not in lowered
        assert "token=" not in lowered
        assert "password" not in lowered
    # 条目引用名（非密文）允许出现——这正是 §2.1"可安全进日志"的值语义。
    assert "elsevier_apikey" in repr(handle)


def test_session_handle_has_no_slot_for_inline_credentials() -> None:
    # 冻结签名五字段之外无任何弹性载荷位（无 dict/meta 字段可夹带明文凭证）。
    assert len(dataclasses.fields(SessionHandle)) == 5


# ---------------------------------------------------------------------------
# AC-0.3：.gitignore 四条目生效验证（git check-ignore；无 git/非 repo 则 skip）
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]

GITIGNORED_CANDIDATES = [
    # auth/state/（仓库根锚定——config-home 误置仓库内的双保险）
    "auth/state/oup_campus_state.enc",
    # *.enc（任意层级）
    "stray.enc",
    "some/dir/session.enc",
    # .filekey（任意层级）
    ".filekey",
    "auth/state/.filekey",
    # profiles.toml（任意层级）
    "profiles.toml",
    "some/dir/profiles.toml",
]


@pytest.mark.parametrize("candidate", GITIGNORED_CANDIDATES)
def test_gitignore_covers_auth_credential_paths(candidate: str) -> None:
    try:
        proc = subprocess.run(  # noqa: S603 - 固定参数的本地 git 查询
            ["git", "-C", str(REPO_ROOT), "check-ignore", "-q", candidate],
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:  # pragma: no cover - CI 均有 git
        pytest.skip("git 不可用")
    if proc.returncode == 128:  # pragma: no cover - 非 git 环境（sdist 等）
        pytest.skip("非 git 工作区")
    assert proc.returncode == 0, f"{candidate} 未被 .gitignore 覆盖（AC-0.3 双保险缺口）"
