"""auth 测试共享工具（T1b）：假 keyring 模块 + 最小 Config 工厂。

**keyring 绝缘红线**：auth 相关测试一律经 `install_fake_keyring` / autouse fixture
把 `store._import_keyring` 替换掉——绝不触宿主 OS Keychain（读会弹授权、写会留
残留条目，均不可接受）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

import paper_crawler.auth.store as store_mod
from paper_crawler.config import Config


class FakeKeyring:
    """假 keyring 模块（get_keyring/get_password/set_password/delete_password）。"""

    def __init__(self, backend_module: str = "keyring.backends.macOS") -> None:
        self.entries: dict[tuple[str, str], str] = {}
        self.backend_module = backend_module
        self.get_password_calls: list[tuple[str, str]] = []

    def get_keyring(self) -> object:
        return type("Keyring", (), {"__module__": self.backend_module})()

    def get_password(self, service: str, entry: str) -> str | None:
        self.get_password_calls.append((service, entry))
        return self.entries.get((service, entry))

    def set_password(self, service: str, entry: str, value: str) -> None:
        self.entries[(service, entry)] = value

    def delete_password(self, service: str, entry: str) -> None:
        if (service, entry) not in self.entries:
            raise KeyError(entry)  # 仿 keyring.errors.PasswordDeleteError（缺条目即抛）
        del self.entries[(service, entry)]


def install_fake_keyring(monkeypatch: pytest.MonkeyPatch, fake: object) -> None:
    monkeypatch.setattr(store_mod, "_import_keyring", lambda: fake)


def make_config(home: Path, **overrides: object) -> Config:
    """最小 Config（绕开 Config.load 的 env/cwd 分层——测试直构，字段与 load 等价）。"""
    return Config(
        home=home,
        data_dir=home / "data",
        db_path=home / "catalog.sqlite",
        log_dir=home / "logs",
        reports_dir=home / "reports",
        venues_dirs=(),
        **overrides,  # type: ignore[arg-type]
    )
