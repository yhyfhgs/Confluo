"""`auth/protocol.py` 单测（auth-framework §2.2 冻结签名；T1a）。

锁定面：`ProviderKind` 四值逐字；`AuthProvider` `@runtime_checkable` 甄别
（完整实现 isinstance True / 缺方法 False）；`AuthProviderBase` 恒等 rewrite +
invalidate 委托样板（store 逻辑归 T1b——抽象委托点未实现时 NotImplementedError）。
"""

from datetime import UTC, datetime
from typing import get_args

import pytest

from paper_crawler.auth import AuthProvider as AuthProviderViaPackage
from paper_crawler.auth.protocol import AuthProvider, AuthProviderBase, ProviderKind
from paper_crawler.types import HealthStatus, SessionBackend, SessionHandle

HANDLE = SessionHandle(
    provider_id="fake@test",
    backend=SessionBackend.HTTPX_COOKIES,
    payload_ref="fake_state",
    established_at=datetime(2026, 7, 23, tzinfo=UTC),
)


class FakeProvider(AuthProviderBase):
    """最小完整实现：基类 + 三方法覆盖 + 委托点（§2.2"四 provider 各覆盖"形态）。"""

    provider_id = "fake@test"
    kind: ProviderKind = "cookie_session"

    def __init__(self) -> None:
        self.deleted_refs: list[str] = []

    def ensure_session(self, *, interactive: bool = False) -> SessionHandle:
        return HANDLE

    def health_check(self, session: SessionHandle) -> HealthStatus:
        return HealthStatus.OK

    def refresh(self, session: SessionHandle) -> SessionHandle | None:
        return None

    def _delete_payload(self, payload_ref: str) -> None:
        self.deleted_refs.append(payload_ref)


class MissingHealthCheck:
    """缺 `health_check` 的伪 provider——runtime_checkable 必须判 False。"""

    provider_id = "broken"
    kind: ProviderKind = "api_key"

    def ensure_session(self, *, interactive: bool = False) -> SessionHandle:
        return HANDLE

    def refresh(self, session: SessionHandle) -> SessionHandle | None:
        return None

    def invalidate(self, session: SessionHandle) -> None:
        return None

    def rewrite_url(self, url: str) -> str:
        return url


# ---------------------------------------------------------------------------
# ProviderKind（§2.2 逐字四值）
# ---------------------------------------------------------------------------


def test_provider_kind_literal_values_exact() -> None:
    assert get_args(ProviderKind) == ("cookie_session", "ezproxy", "sso_flow", "api_key")


# ---------------------------------------------------------------------------
# runtime_checkable 甄别（沿 SourceAdapter/HttpClientConsumer 先例）
# ---------------------------------------------------------------------------


def test_complete_provider_satisfies_protocol() -> None:
    assert isinstance(FakeProvider(), AuthProvider)


def test_incomplete_provider_fails_protocol() -> None:
    assert not isinstance(MissingHealthCheck(), AuthProvider)
    assert not isinstance(object(), AuthProvider)


def test_package_reexports_protocol() -> None:
    # auth-framework §1：`auth/__init__.py` 导出 AuthProvider（T1a 子集）。
    assert AuthProviderViaPackage is AuthProvider


def test_protocol_declares_five_methods() -> None:
    for method in ("ensure_session", "health_check", "refresh", "invalidate", "rewrite_url"):
        assert callable(getattr(AuthProvider, method))


# ---------------------------------------------------------------------------
# AuthProviderBase：恒等 rewrite + invalidate 委托样板
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://academic.oup.com/qje/article/141/3/2205/8662148",
        "https://api.elsevier.com/content/article/doi/10.1016/j.jfineco.2011.03.021",
        "",
    ],
)
def test_base_rewrite_url_is_identity(url: str) -> None:
    assert FakeProvider().rewrite_url(url) == url


def test_base_invalidate_delegates_payload_ref_deletion() -> None:
    provider = FakeProvider()
    provider.invalidate(HANDLE)
    assert provider.deleted_refs == ["fake_state"]


def test_base_delete_payload_is_abstract_delegation_point() -> None:
    # store 删除逻辑归 T1b（auth-framework §2.3）——T1a 基类委托点未实现即显式报错。
    class BareBase(AuthProviderBase):
        provider_id = "bare"
        kind: ProviderKind = "ezproxy"

    with pytest.raises(NotImplementedError):
        BareBase().invalidate(HANDLE)
